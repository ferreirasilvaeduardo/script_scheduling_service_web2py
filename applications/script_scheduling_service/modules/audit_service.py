# -*- coding: utf-8 -*-
"""Consulta e exportacao da trilha de auditoria (README §4.3.D VIEW_AUDIT, §4.4, §10 tabela 16).

O detalhe ja e gravado sem segredos (README §4.4); na leitura ele passa de novo pelo
mascarador do processo, como defesa em profundidade. A exportacao CSV usa os mesmos
filtros e o mesmo RBAC da tela, neutraliza CSV injection e e ela propria auditada.
"""
import collections
import csv
import datetime
import io
import re
import threading

import admin_crud
import masking
import rbac
import ui_helpers
from admin_crud import AccessDenied  # noqa: F401  (reexportado para o controller)

FEATURE = "VIEW_AUDIT"

# Catalogo de acoes (README §10, tabela 16), mantido em codigo e sem CK para permitir extensao.
ACTIONS = (
    "LOGIN_OK", "LOGIN_FAILED", "LOGIN_LOCKED", "LOGOUT",
    "TICKET_CREATE", "TICKET_CANCEL", "TICKET_RERUN",
    "CREATE", "UPDATE", "DEACTIVATE", "PERM_UPDATE",
    "SCHEDULE_PAUSE", "AGENT_START", "AGENT_STOP", "PURGE",
    "AUDIT_EXPORT", "SCHEMA_MIGRATE",
)
EXPORT_ACTION = "AUDIT_EXPORT"
AUDIT_ENTITY = "tbsss_audit"

ENTITIES = (
    "tbsss_schedules", "tbsss_agents", "tbsss_environments", "tbsss_audit", "tbsss_control",
    "tbsss_parameters", "tbsss_profiles", "tbsss_scripts", "tbsss_tickets", "tbsss_users",
)

# Rota da tela de cada entidade e funcionalidade exigida para exibir o link (decisao D6 do F6.1).
# None na funcionalidade: tela de tickets, cuja consulta exige VIEW_LOGS ou EXEC_SCRIPT.
ENTITY_SCREENS = {
    "tbsss_tickets": ("tickets", "detalhe", None),
    "tbsss_schedules": ("agendamentos", "form", "MANAGE_SCHEDULES"),
    "tbsss_users": ("admin_usuarios", "form", "MANAGE_USERS"),
    "tbsss_profiles": ("admin_perfis", "form", "MANAGE_PROFILES"),
    "tbsss_environments": ("admin_ambientes", "form", "MANAGE_ENVIRONMENTS"),
    "tbsss_scripts": ("admin_scripts", "form", "MANAGE_SCRIPTS"),
    "tbsss_parameters": ("admin_parametros", "form", "MANAGE_PARAMETERS"),
}

MAX_LENGTH = 100
DEFAULT_PERIOD_DAYS = 7
MAX_PERIOD_DAYS = 90
# Acima de MAX_PERIOD_DAYS so com filtro seletivo (ator, ou entidade + ID), ate este teto (decisao D4).
MAX_SELECTIVE_PERIOD_DAYS = 366
EXPORT_LIMIT = 50000
SHORT_DETAIL = 80
_LINES_PER_CHUNK = 500

FILTER_FIELDS = ("de", "ate", "actor", "action", "entity", "entity_id", "ip")
CSV_HEADER = (u"ID", u"Data/hora", u"Ator", u"IP de origem", u"Ação", u"Entidade", u"ID da entidade",
                 u"Detalhe")
# Prefixos que planilhas interpretam como formula (CSV injection).
_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_DAY_FORMAT = "%Y-%m-%d"
_CSV_FORMAT = "%Y-%m-%d %H:%M:%S"
_RE_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_RE_ACTOR = re.compile(r"[A-Za-z0-9._:@-]{1,40}")
_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_IP = re.compile(r"[0-9A-Fa-f.:]{1,45}")

MSG_DATE = u"Informe uma data válida (AAAA-MM-DD)."
MSG_RANGE = u"A data final deve ser igual ou posterior à inicial."
MSG_PERIOD = (u"O período máximo é de %d dias. Para consultar até %d dias, filtre também pelo ator "
               u"ou pela entidade e ID." % (MAX_PERIOD_DAYS, MAX_SELECTIVE_PERIOD_DAYS))
MSG_SELECTIVE_PERIOD = u"O período máximo, mesmo com filtro por ator ou entidade, é de %d dias." % (
    MAX_SELECTIVE_PERIOD_DAYS)
MSG_ACTOR = u"Use até 40 caracteres: letras, números e . _ : @ -"
MSG_ACTION = u"Ação desconhecida."
MSG_ENTITY = u"Entidade desconhecida."
MSG_ENTITY_ID = u"Informe um número inteiro positivo."
MSG_IP = u"Informe um endereço IPv4 ou IPv6 (ou parte dele)."


class InvalidFilters(ValueError):
    """Filtros recusados; erros: dict campo -> mensagem segura para exibicao."""

    def __init__(self, errors):
        ValueError.__init__(self, ",".join(sorted(errors)))
        self.errors = errors


def _text(value, limit):
    return admin_crud.text(value, limit)


def _day(value):
    if not value or not _RE_DAY.fullmatch(value):
        return None
    try:
        return datetime.datetime.strptime(value, _DAY_FORMAT).date()
    except ValueError:
        return None


def normalize_filters(input_value, today):
    """Allowlist dos filtros (querystring ou POST da exportacao).

    Retorna (filtros, erros): filtros e um OrderedDict na forma de exibicao/URL, sempre com
    'de' e 'ate' (padrao: os ultimos 7 dias ate `hoje`); erros mapeia campo -> mensagem.
    """
    input_value = input_value or {}
    filtros = collections.OrderedDict()
    erros = {}

    brutos = {}
    for chave in ("de", "ate"):
        brutos[chave] = _text(input_value.get(chave), 10)
    de, ate = _day(brutos["de"]), _day(brutos["ate"])
    for chave, valor in (("de", de), ("ate", ate)):
        if brutos[chave] and valor is None:
            erros[chave] = MSG_DATE
    if ate is None:
        ate = today if de is None or de <= today else de
    if de is None:
        de = ate - datetime.timedelta(days=DEFAULT_PERIOD_DAYS - 1)

    ator = _text(input_value.get("actor"), 41)
    if ator:
        if _RE_ACTOR.fullmatch(ator):
            filtros["actor"] = ator
        else:
            erros["actor"] = MSG_ACTOR
    acao = _text(input_value.get("action"), 30)
    if acao:
        if acao in ACTIONS:
            filtros["action"] = acao
        else:
            erros["action"] = MSG_ACTION
    entidade = _text(input_value.get("entity"), 30)
    if entidade:
        if entidade in ENTITIES:
            filtros["entity"] = entidade
        else:
            erros["entity"] = MSG_ENTITY
    entidade_id = _text(input_value.get("entity_id"), 11)
    if entidade_id:
        if _RE_ID.fullmatch(entidade_id) and int(entidade_id) > 0:
            filtros["entity_id"] = int(entidade_id)
        else:
            erros["entity_id"] = MSG_ENTITY_ID
    ip = _text(input_value.get("ip"), 46)
    if ip:
        if _RE_IP.fullmatch(ip):
            filtros["ip"] = ip
        else:
            erros["ip"] = MSG_IP

    if "de" not in erros and "ate" not in erros:
        dias = (ate - de).days + 1
        seletivo = "actor" in filtros or ("entity" in filtros and "entity_id" in filtros)
        if dias < 1:
            erros["ate"] = MSG_RANGE
        elif dias > MAX_SELECTIVE_PERIOD_DAYS:
            erros["de"] = MSG_SELECTIVE_PERIOD
        elif dias > MAX_PERIOD_DAYS and not seletivo:
            erros["de"] = MSG_PERIOD

    resultado = collections.OrderedDict()
    resultado["de"] = brutos["de"] if "de" in erros and brutos["de"] else de.strftime(_DAY_FORMAT)
    resultado["ate"] = brutos["ate"] if "ate" in erros and brutos["ate"] else ate.strftime(_DAY_FORMAT)
    resultado.update(filtros)
    return resultado, erros


def repo_filters(filters):
    """Traduz filtros validos para o contrato: periodo vira [de 00:00:00, ate 23:59:59]."""
    de = datetime.datetime.strptime(filters["de"], _DAY_FORMAT)
    ate = datetime.datetime.strptime(filters["ate"], _DAY_FORMAT)
    repo = {"start_date": de, "end_date": ate + datetime.timedelta(days=1, seconds=-1)}
    for chave, destino in (("actor", "actor"), ("action", "action"), ("entity", "entity"),
                           ("entity_id", "entity_id"), ("ip", "source_ip")):
        if chave in filters:
            repo[destino] = filters[chave]
    return repo


def neutralize_csv(value):
    """Prefixa com ' o texto que uma planilha leria como formula (= + - @ TAB CR no inicio)."""
    if isinstance(value, str) and value.startswith(_DANGEROUS_PREFIXES):
        return u"'" + value
    return value


def _mask(text):
    return masking.MASKER.mask(text) if text else text


def csv_row(reg):
    """Uma linha da exportacao (README §4.4); tambem a do --export-audit do purge (CR-007, R-22)."""
    criado = reg.get("created_at")
    valores = (
        reg["id"],
        criado.strftime(_CSV_FORMAT) if criado else u"",
        reg.get("actor") or u"",
        reg.get("source_ip") or u"",
        reg.get("action") or u"",
        reg.get("entity") or u"",
        u"" if reg.get("entity_id") is None else reg["entity_id"],
        _mask(reg.get("detail")) or u"",
    )
    return [neutralize_csv(v) for v in valores]


def entity_link(ctx, entity, entity_id, can_view_tickets):
    """(controller, funcao, args) da tela da entidade, ou None sem tela ou sem permissao (decisao D6)."""
    if entity_id is None:
        return None
    tela = ENTITY_SCREENS.get(entity)
    if tela is None:
        return None
    controller, funcao, func = tela
    permitido = can_view_tickets if func is None else rbac.has_feature(ctx, func)
    if not permitido:
        return None
    return controller, funcao, [entity_id]


def _describe_filters(filters):
    return u", ".join(u"%s=%s" % (k, filters[k]) for k in FILTER_FIELDS if k in filters)


class AuditService(object):
    """Consulta e exportacao da trilha, com repositorio, relogio e log injetados."""

    def __init__(self, audit, clock, log):
        self._audit = audit
        self._clock = clock
        self._log = log

    def _today(self):
        return self._clock().date()

    def normalize_filters(self, input_value):
        """Filtros e erros com o periodo padrao calculado pelo relogio do banco."""
        return normalize_filters(input_value, self._today())

    def list(self, ctx, input_value, page, size):
        """Pagina da trilha (tamanho <= 100), ordenada por created_at DESC, id DESC.

        Retorna dict com filtros, erros, itens, total, pagina e tamanho. Com erros de filtro
        nada e consultado.
        """
        admin_crud.require_feature(ctx, FEATURE)
        size = max(1, min(int(size or 20), MAX_LENGTH))
        filtros, erros = self.normalize_filters(input_value)
        vazio = {"filtros": filtros, "erros": erros, "itens": [], "total": 0, "pagina": 1, "tamanho": size}
        if erros:
            return vazio
        repo_filtros = repo_filters(filtros)
        resultado = self._audit.list(filters=repo_filtros, page=page, size=size)
        info = ui_helpers.paginacao_info(page, size, resultado["total"],
                                         resultado.get("total_limitado", False), len(resultado["itens"]))
        if not resultado["itens"] and info["pagina"] != resultado["pagina"]:
            resultado = self._audit.list(filters=repo_filtros, page=info["pagina"], size=size)
        itens = []
        for reg in resultado["itens"]:
            detalhe = _mask(reg.get("detail")) or u""
            itens.append({
                "id": reg["id"],
                "created_at": reg.get("created_at"),
                "actor": reg.get("actor"),
                "source_ip": reg.get("source_ip"),
                "action": reg.get("action"),
                "entity": reg.get("entity"),
                "entity_id": reg.get("entity_id"),
                "detail": detalhe,
                "detalhe_curto": detalhe if len(detalhe) <= SHORT_DETAIL else detalhe[:SHORT_DETAIL - 1] + u"…",
                "truncado": len(detalhe) > SHORT_DETAIL,
            })
        return dict(vazio, itens=itens, total=resultado["total"], pagina=resultado["pagina"],
                    tamanho=resultado["tamanho"], total_limitado=resultado.get("total_limitado", False))

    def export_csv(self, ctx, ip, input_value):
        """Exportacao com os filtros e o RBAC da tela: retorna (nome_arquivo, linhas, blocos).

        blocos e um gerador de bytes UTF-8 (com BOM, separador ';') de no maximo
        EXPORT_LIMIT linhas. A exportacao e auditada (AUDIT_EXPORT) antes do streaming,
        e o conjunto exportado para no ID anterior ao da propria linha de auditoria.
        Filtros invalidos levantam InvalidFilters.
        """
        admin_crud.require_feature(ctx, FEATURE)
        filtros, erros = self.normalize_filters(input_value)
        if erros:
            raise InvalidFilters(erros)
        repo_filtros = repo_filters(filtros)
        # README §4.4 (D12): reserva o id, delimita id_max = id - 1, conta esse recorte e so entao grava a
        # linha; a quantidade registrada e o arquivo correspondem ao mesmo conjunto.
        aid = self._audit.reserve_id()
        repo_filtros["id_max"] = aid - 1
        total = sum(1 for _ in self._audit.iterate(filters=repo_filtros, limit=EXPORT_LIMIT))
        linhas = min(total, EXPORT_LIMIT)
        detalhe = admin_crud.free_detail(u"filtros: %s; linhas: %d (limite %d)" % (
            _describe_filters(filtros), linhas, EXPORT_LIMIT))
        self._audit.register(ctx.get("login"), ip, EXPORT_ACTION, AUDIT_ENTITY, None, detalhe, id=aid)
        self._log.info("auditoria exportada (login=%s linhas=%d total=%d)", ctx.get("login"), linhas, total,
                       extra={"action": EXPORT_ACTION})
        nome = "auditoria_%s.csv" % self._clock().strftime("%Y%m%d_%H%M%S")
        return nome, linhas, self._chunks(repo_filtros, ctx.get("login"))

    def _chunks(self, repo_filters, login):
        buffer = io.StringIO()
        escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        escritor.writerow(CSV_HEADER)
        yield (u"﻿" + buffer.getvalue()).encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)
        pendentes = 0
        try:
            for reg in self._audit.iterate(filters=repo_filters, limit=EXPORT_LIMIT):
                escritor.writerow(csv_row(reg))
                pendentes += 1
                if pendentes >= _LINES_PER_CHUNK:
                    yield buffer.getvalue().encode("utf-8")
                    buffer.seek(0)
                    buffer.truncate(0)
                    pendentes = 0
        except Exception:
            # A resposta ja comecou: so resta registrar e encerrar o arquivo incompleto.
            self._log.exception("falha durante a exportacao da auditoria (login=%s)", login,
                                extra={"action": EXPORT_ACTION})
            raise
        if pendentes:
            yield buffer.getvalue().encode("utf-8")


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from gluon import current
            import sss_logging
            fabrica = current.repo_factory
            _default = AuditService(
                audit=fabrica.get("audit"),
                clock=fabrica.get("tickets").now,
                log=sss_logging.get_logger("sss_web", current.sss_cfg),
            )
        return _default


def default_filters(input_value):
    """Filtros e erros normalizados com o relogio do banco (servico padrao)."""
    return _service().normalize_filters(input_value)


def list_page(ctx, input_value, page, size):
    """Pagina da trilha de auditoria (servico padrao)."""
    return _service().list(ctx, input_value, page, size)


def export_csv(ctx, ip, input_value):
    """Exportacao CSV auditada (servico padrao)."""
    return _service().export_csv(ctx, ip, input_value)
