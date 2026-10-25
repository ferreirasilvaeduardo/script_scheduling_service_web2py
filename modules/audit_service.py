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
from sss.core import masking
from sss.core import rbac
import ui_helpers
from admin_crud import AccessDenied  # noqa: F401  (reexportado para o controller)

FEATURE = "VIEW_AUDIT"

# Catalogo de acoes (README §10, tabela 16), mantido em codigo e sem CK para permitir extensao.
ACTIONS = (
    "LOGIN_OK", "LOGIN_FAILED", "LOGIN_LOCKED", "LOGOUT",
    "TICKET_CREATE", "TICKET_CANCEL", "TICKET_RERUN",
    "CREATE", "UPDATE", "DEACTIVATE", "PERM_UPDATE",
    "SCHEDULE_PAUSE", "AGENT_START", "AGENT_STOP", "PURGE",
    "AUDIT_EXPORT", "SCHEMA_MIGRATE", "OUTPUT_DOWNLOAD", "INPUT_UPLOAD", "INPUT_DELIVERY",
)
# Nomes simples das acoes e entidades na tela (CR-018b); o CSV e o banco continuam com os codigos.
ACTION_LABELS = {
    "LOGIN_OK": u"Entrada no sistema", "LOGIN_FAILED": u"Senha errada", "LOGIN_LOCKED": u"Conta bloqueada",
    "LOGOUT": u"Saída do sistema", "TICKET_CREATE": u"Ticket criado", "TICKET_CANCEL": u"Cancelamento de ticket",
    "TICKET_RERUN": u"Ticket rodado de novo", "CREATE": u"Inclusão", "UPDATE": u"Alteração",
    "DEACTIVATE": u"Desativação", "PERM_UPDATE": u"Permissões do perfil", "SCHEDULE_PAUSE": u"Regra pausada",
    "AGENT_START": u"Agente iniciado", "AGENT_STOP": u"Agente parado", "PURGE": u"Limpeza por retenção",
    "AUDIT_EXPORT": u"Exportação da auditoria", "SCHEMA_MIGRATE": u"Atualização do esquema",
    "OUTPUT_DOWNLOAD": u"Download de saída", "INPUT_UPLOAD": u"Envio para a entrada",
    "INPUT_DELIVERY": u"Entrega na entrada",
}
ENTITY_LABELS = {
    "tbsss_schedules": u"Regras de agendamento", "tbsss_agents": u"Agentes", "tbsss_environments": u"Ambientes",
    "tbsss_audit": u"Auditoria", "tbsss_control": u"Controle do esquema", "tbsss_parameters": u"Parâmetros",
    "tbsss_profiles": u"Perfis", "tbsss_scripts": u"Scripts", "tbsss_tickets": u"Tickets",
    "tbsss_users": u"Usuários", "tbsss_input_upload": u"Envios para a entrada",
}


def action_label(code):
    """Nome simples da acao para a tela; codigo desconhecido volta como veio."""
    return ACTION_LABELS.get(code, code)


def entity_label(code):
    """Nome simples da entidade para a tela; codigo desconhecido volta como veio."""
    return ENTITY_LABELS.get(code, code)


EXPORT_ACTION = "AUDIT_EXPORT"
AUDIT_ENTITY = "tbsss_audit"

ENTITIES = (
    "tbsss_schedules", "tbsss_agents", "tbsss_environments", "tbsss_audit", "tbsss_control",
    "tbsss_parameters", "tbsss_profiles", "tbsss_scripts", "tbsss_tickets", "tbsss_users", "tbsss_input_upload",
)

# Rota da tela de cada entidade e funcionalidade exigida para exibir o link (decisao D6 do F6.1).
# None na funcionalidade: tela de tickets, cuja consulta exige VIEW_LOGS ou EXEC_SCRIPT.
ENTITY_SCREENS = {
    "tbsss_tickets": ("tickets", "detail", None),
    "tbsss_schedules": ("schedules", "form", "MANAGE_SCHEDULES"),
    "tbsss_users": ("admin_users", "form", "MANAGE_USERS"),
    "tbsss_profiles": ("admin_profiles", "form", "MANAGE_PROFILES"),
    "tbsss_environments": ("admin_environments", "form", "MANAGE_ENVIRONMENTS"),
    "tbsss_scripts": ("admin_scripts", "form", "MANAGE_SCRIPTS"),
    "tbsss_parameters": ("admin_parameters", "form", "MANAGE_PARAMETERS"),
}

MAX_LENGTH = 100
DEFAULT_PERIOD_DAYS = 7
MAX_PERIOD_DAYS = 90
# Acima de MAX_PERIOD_DAYS so com filtro seletivo (ator, ou entidade + ID), ate este teto (decisao D4).
MAX_SELECTIVE_PERIOD_DAYS = 366
EXPORT_LIMIT = 50000
SHORT_DETAIL = 80
_LINES_PER_CHUNK = 500

FILTER_FIELDS = ("date_from", "date_to", "actor", "action", "entity", "entity_id", "ip")
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
    'date_from' e 'date_to' (padrao: os ultimos 7 dias ate `hoje`); erros mapeia campo -> mensagem.
    """
    input_value = input_value or {}
    filters = collections.OrderedDict()
    errors = {}

    raw = {}
    for key in ("date_from", "date_to"):
        raw[key] = _text(input_value.get(key), 10)
    of, until = _day(raw["date_from"]), _day(raw["date_to"])
    for key, value in (("date_from", of), ("date_to", until)):
        if raw[key] and value is None:
            errors[key] = MSG_DATE
    if until is None:
        until = today if of is None or of <= today else of
    if of is None:
        of = until - datetime.timedelta(days=DEFAULT_PERIOD_DAYS - 1)

    actor = _text(input_value.get("actor"), 41)
    if actor:
        if _RE_ACTOR.fullmatch(actor):
            filters["actor"] = actor
        else:
            errors["actor"] = MSG_ACTOR
    action = _text(input_value.get("action"), 30)
    if action:
        if action in ACTIONS:
            filters["action"] = action
        else:
            errors["action"] = MSG_ACTION
    entity = _text(input_value.get("entity"), 30)
    if entity:
        if entity in ENTITIES:
            filters["entity"] = entity
        else:
            errors["entity"] = MSG_ENTITY
    entity_id = _text(input_value.get("entity_id"), 11)
    if entity_id:
        if _RE_ID.fullmatch(entity_id) and int(entity_id) > 0:
            filters["entity_id"] = int(entity_id)
        else:
            errors["entity_id"] = MSG_ENTITY_ID
    ip = _text(input_value.get("ip"), 46)
    if ip:
        if _RE_IP.fullmatch(ip):
            filters["ip"] = ip
        else:
            errors["ip"] = MSG_IP

    if "date_from" not in errors and "date_to" not in errors:
        days = (until - of).days + 1
        selective = "actor" in filters or ("entity" in filters and "entity_id" in filters)
        if days < 1:
            errors["date_to"] = MSG_RANGE
        elif days > MAX_SELECTIVE_PERIOD_DAYS:
            errors["date_from"] = MSG_SELECTIVE_PERIOD
        elif days > MAX_PERIOD_DAYS and not selective:
            errors["date_from"] = MSG_PERIOD

    result = collections.OrderedDict()
    result["date_from"] = raw["date_from"] if "date_from" in errors and raw["date_from"] else of.strftime(_DAY_FORMAT)
    result["date_to"] = raw["date_to"] if "date_to" in errors and raw["date_to"] else until.strftime(_DAY_FORMAT)
    result.update(filters)
    return result, errors


def repo_filters(filters):
    """Traduz filtros validos para o contrato: periodo vira [de 00:00:00, ate 23:59:59]."""
    of = datetime.datetime.strptime(filters["date_from"], _DAY_FORMAT)
    until = datetime.datetime.strptime(filters["date_to"], _DAY_FORMAT)
    repo = {"start_date": of, "end_date": until + datetime.timedelta(days=1, seconds=-1)}
    for key, destination in (("actor", "actor"), ("action", "action"), ("entity", "entity"),
                           ("entity_id", "entity_id"), ("ip", "source_ip")):
        if key in filters:
            repo[destination] = filters[key]
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
    created = reg.get("created_at")
    values = (
        reg["id"],
        created.strftime(_CSV_FORMAT) if created else u"",
        reg.get("actor") or u"",
        reg.get("source_ip") or u"",
        reg.get("action") or u"",
        reg.get("entity") or u"",
        u"" if reg.get("entity_id") is None else reg["entity_id"],
        _mask(reg.get("detail")) or u"",
    )
    return [neutralize_csv(v) for v in values]


def entity_link(ctx, entity, entity_id, can_view_tickets):
    """(controller, funcao, args) da tela da entidade, ou None sem tela ou sem permissao (decisao D6)."""
    if entity_id is None:
        return None
    screen = ENTITY_SCREENS.get(entity)
    if screen is None:
        return None
    controller, function, feature = screen
    allowed = can_view_tickets if feature is None else rbac.has_feature(ctx, feature)
    if not allowed:
        return None
    return controller, function, [entity_id]


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
        filters, errors = self.normalize_filters(input_value)
        empty = {"filters": filters, "errors": errors, "items": [], "total": 0, "page": 1, "size": size}
        if errors:
            return empty
        repo_filters_dict = repo_filters(filters)
        result = self._audit.list(filters=repo_filters_dict, page=page, size=size)
        info = ui_helpers.pagination_info(page, size, result["total"],
                                         result.get("total_capped", False), len(result["items"]))
        if not result["items"] and info["page"] != result["page"]:
            result = self._audit.list(filters=repo_filters_dict, page=info["page"], size=size)
        items = []
        for reg in result["items"]:
            detail = _mask(reg.get("detail")) or u""
            items.append({
                "id": reg["id"],
                "created_at": reg.get("created_at"),
                "actor": reg.get("actor"),
                "source_ip": reg.get("source_ip"),
                "action": reg.get("action"),
                "entity": reg.get("entity"),
                "entity_id": reg.get("entity_id"),
                "detail": detail,
                "short_detail": detail if len(detail) <= SHORT_DETAIL else detail[:SHORT_DETAIL - 1] + u"…",
                "truncated": len(detail) > SHORT_DETAIL,
            })
        return dict(empty, items=items, total=result["total"], page=result["page"],
                    size=result["size"], total_capped=result.get("total_capped", False))

    def export_csv(self, ctx, ip, input_value):
        """Exportacao com os filtros e o RBAC da tela: retorna (nome do arquivo, linhas, blocos).

        blocos e um gerador de bytes UTF-8 (com BOM, separador ';') de no maximo
        EXPORT_LIMIT linhas. A exportacao e auditada (AUDIT_EXPORT) antes do streaming,
        e o conjunto exportado para no ID anterior ao da propria linha de auditoria.
        Filtros invalidos levantam InvalidFilters.
        """
        admin_crud.require_feature(ctx, FEATURE)
        filters, errors = self.normalize_filters(input_value)
        if errors:
            raise InvalidFilters(errors)
        repo_filters_dict = repo_filters(filters)
        # README §4.4 (D12): reserva o id, delimita id_max = id - 1, conta esse recorte e so entao grava a
        # linha; a quantidade registrada e o arquivo correspondem ao mesmo conjunto.
        aid = self._audit.reserve_id()
        repo_filters_dict["id_max"] = aid - 1
        # CR-018c: COUNT no banco, sem ler o conjunto duas vezes (a contagem e o arquivo usam o mesmo recorte).
        total = self._audit.count(filters=repo_filters_dict, limit=EXPORT_LIMIT)
        rows = min(total, EXPORT_LIMIT)
        detail = admin_crud.free_detail(u"filtros: %s; linhas: %d (limite %d)" % (
            _describe_filters(filters), rows, EXPORT_LIMIT))
        self._audit.register(ctx.get("login"), ip, EXPORT_ACTION, AUDIT_ENTITY, None, detail, id=aid)
        self._log.info("auditoria exportada (login=%s linhas=%d total=%d)", ctx.get("login"), rows, total,
                       extra={"action": EXPORT_ACTION})
        name = "auditoria_%s.csv" % self._clock().strftime("%Y%m%d_%H%M%S")
        return name, rows, self._chunks(repo_filters_dict, ctx.get("login"))

    def _chunks(self, repo_filters, login):
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        writer.writerow(CSV_HEADER)
        yield (u"﻿" + buffer.getvalue()).encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)
        pending = 0
        try:
            for reg in self._audit.iterate(filters=repo_filters, limit=EXPORT_LIMIT):
                writer.writerow(csv_row(reg))
                pending += 1
                if pending >= _LINES_PER_CHUNK:
                    yield buffer.getvalue().encode("utf-8")
                    buffer.seek(0)
                    buffer.truncate(0)
                    pending = 0
        except Exception:
            # A resposta ja comecou: so resta registrar e encerrar o arquivo incompleto.
            self._log.exception("falha durante a exportacao da auditoria (login=%s)", login,
                                extra={"action": EXPORT_ACTION})
            raise
        if pending:
            yield buffer.getvalue().encode("utf-8")


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from sss.config import app_context
            import repo_factory
            from sss.config import sss_logging
            factory = repo_factory
            _default = AuditService(
                audit=factory.get("audit"),
                clock=factory.get("tickets").now,
                log=sss_logging.get_logger("sss_web", app_context.require_config()),
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
