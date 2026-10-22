# -*- coding: utf-8 -*-
"""Regras de agendamento recorrente (README §4.3.C MANAGE_SCHEDULES, §7, §10 tabela 12).

Segue docs/ADMIN_CRUD_PATTERN.md: nao importa gluon, recebe ctx e ip por parametro e o servico
padrao do processo web e criado sob demanda (_servico). O relogio e injetado: na web, o
SYSDATE do repositorio de tickets; nos testes, um relogio fixo.

A regra roda sob os privilegios de quem a definiu por ultimo (README §10): toda inclusao ou
edicao grava usuario_id = editor, que precisa de can_execute vigente para o script e o
ambiente. Valores de parametros sensiveis nunca vao para o log, a auditoria ou o HTML.
"""
import collections
import datetime
import json
import re
import threading

import admin_crud
import cron_parser
import params_compiler
import rbac
import recurrence
import ui_helpers
from admin_crud import GENERAL_FIELD, OperationDenied
from cron_parser import CronError
from repo_errors import RepoConflict, RepoNotFound, RepoViolation
from ticket_service import AccessDenied as DisparoNegado

FEATURE = "MANAGE_SCHEDULES"
NAME_MAX_LENGTH = 60
PREVIEW_COUNT = 5
DEFAULT_PRIORITY = 2
MASK = u"******"
DATE_FIELD_FORMAT = "%Y-%m-%dT%H:%M"

TYPE_LABELS = collections.OrderedDict((
    ("ONCE", u"Única"),
    ("DAILY", u"Diária"),
    ("WEEKLY", u"Semanal"),
    ("MONTHLY", u"Mensal"),
    ("CRON", u"Expressão CRON"),
))
# ISO 1-7 (1 = segunda), README §7.2.
WEEKDAYS = ((1, u"seg", u"Segunda"), (2, u"ter", u"Terça"), (3, u"qua", u"Quarta"),
               (4, u"qui", u"Quinta"), (5, u"sex", u"Sexta"), (6, u"sáb", u"Sábado"),
               (7, u"dom", u"Domingo"))
_DAY_ABBREV = dict((n, abrev) for n, abrev, _nome in WEEKDAYS)

# Textos dos motivos de pausa (decisao D4 do F5.2; README §7.5).
PAUSE_REASONS = {
    "MANUAL": u"Pausado manualmente",
    "COMPLETED": u"Concluída",
    "USER_INACTIVE": u"Responsável inativo",
    "NO_PERMISSION": u"Responsável sem permissão",
    "SCRIPT_INACTIVE": u"Script inativo",
    "ENVIRONMENT_INACTIVE": u"Ambiente inativo",
    "INVALID_PARAM": u"Parâmetros inválidos",
    "INVALID_CRON": u"Expressão CRON inválida",
    "INTERNAL_ERROR": u"Erro interno",
}

MSG_NAME_REQUIRED = u"Informe o nome da regra."
MSG_NAME_LENGTH = u"O nome deve ter no máximo %d caracteres." % NAME_MAX_LENGTH
MSG_TYPE = u"Selecione o tipo de recorrência."
MSG_DATE_INVALID = u"Informe uma data e hora válidas."
MSG_ONCE_START = u"Informe a data e hora da execução."
MSG_PRIORITY = u"Selecione uma prioridade entre 1 e 4."
MSG_PRIORITY_ADMIN = u"A prioridade 1 é exclusiva de administradores."
MSG_NO_NEXT_RUN = (u"A regra não tem próxima execução. Confira a data de início, a data de fim "
                   u"e a recorrência.")
MSG_NO_PERMISSION = (u"Você não tem permissão para executar este script neste ambiente. "
                     u"A regra roda com as permissões de quem a salva; ela não foi alterada.")
MSG_ALREADY_PAUSED = u"A regra já está pausada."
MSG_ALREADY_ACTIVE = u"A regra já está ativa."
MSG_RESUME_NO_NEXT_RUN = (u"A regra não tem próxima execução e não pode ser retomada. "
                           u"Edite as datas ou a recorrência.")
MSG_RESUME_GUIDANCE = (u"Edite a regra para corrigir (ao salvar, ela passa a rodar com as suas permissões) "
                          u"e depois retome.")

# Campos editaveis que compoem a versao do formulario (concorrencia otimista, README §10).
VERSION_FIELDS = ("name", "priority", "recurrence_type", "cron_expression", "run_time",
                 "week_days", "month_day", "params_json", "start_date", "end_date",
                 "user_id", "active", "pause_reason")
_EXPECTED_FIELDS = VERSION_FIELDS + ("next_run_at",)
AUDIT_FIELDS = ("name", "script_id", "environment", "priority", "recurrence_type",
                    "cron_expression", "run_time", "week_days", "month_day", "parameters",
                    "start_date", "end_date")
_INSERT_FIELDS = AUDIT_FIELDS + ("user_id", "next_run_at")

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_ENVIRONMENT = re.compile(r"[A-Z0-9_]{1,30}")
# Precisao de minuto (README §7.2/§7.6): segundos ou fracoes sao recusados, nunca cortados.
_DATE_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M")
_ARROW = u" → "


def _id(valor):
    valor = admin_crud.text(valor, 11)
    if valor is None or not _RE_ID.fullmatch(valor) or int(valor) < 1:
        return None
    return int(valor)


def _last(valor):
    if isinstance(valor, (list, tuple)):
        return valor[-1] if valor else None
    return valor


def _empty(valor):
    return valor is None or (isinstance(valor, str) and valor.strip() == "")


def _date(valor):
    """(datetime sem microssegundos | None, invalido). Vazio e (None, False)."""
    texto = admin_crud.text(valor)
    if texto is None:
        return None, False
    for formato in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(texto, formato).replace(microsecond=0), False
        except ValueError:
            continue
    return None, True


def _weekdays(valor):
    """Checkboxes (lista) ou texto '1,3,5' -> texto ISO ordenado sem repeticao; lixo segue para a validacao."""
    if isinstance(valor, (list, tuple)):
        itens = [v for v in valor if isinstance(v, str)]
    elif isinstance(valor, str):
        itens = valor.split(",")
    else:
        return None
    itens = [i.strip() for i in itens if i.strip()]
    if not itens:
        return None
    if all(i.isdigit() and len(i) == 1 for i in itens):
        return ",".join(str(n) for n in sorted(set(int(i) for i in itens)))
    return ",".join(itens)[:20]


def format_date(dt):
    """dd/mm/aaaa HH:MM; None vira '-'."""
    return dt.strftime("%d/%m/%Y %H:%M") if dt is not None else "-"


def format_preview(dt):
    """Data da previa com o dia da semana (ex.: 'qui, 30/04/2026 03:00')."""
    return u"%s, %s" % (_DAY_ABBREV[dt.isoweekday()], format_date(dt))


def _date_field_value(dt):
    return dt.strftime(DATE_FIELD_FORMAT) if dt is not None else ""


AGENDA_PER_RULE = 20
AGENDA_TOTAL = 500
_AGENDA_PAGE = 100
_AGENDA_COUNT_MAX = 5000
_DAY_NAMES = (u"segunda-feira", u"terça-feira", u"quarta-feira", u"quinta-feira", u"sexta-feira", u"sábado",
              u"domingo")


def _day_label(dia, hoje):
    """'Hoje', 'Amanhã' ou 'sexta-feira, 18/10' (README §7.7)."""
    if dia == hoje:
        return u"Hoje"
    if dia == hoje + datetime.timedelta(days=1):
        return u"Amanhã"
    return u"%s, %s" % (_DAY_NAMES[dia.weekday()], dia.strftime("%d/%m"))


def describe_rule(regra):
    """Descricao da recorrencia em portugues para a lista e a previa."""
    tipo = regra.get("recurrence_type")
    hora = regra.get("run_time")
    if tipo == "ONCE":
        return u"Uma vez, em %s" % format_date(regra.get("start_date"))
    if tipo == "DAILY":
        return u"Todos os dias às %s" % hora
    if tipo == "WEEKLY":
        dias = [int(d) for d in (regra.get("week_days") or "").split(",") if d.strip().isdigit()]
        return u"Às %s, %s" % (hora, u", ".join(_DAY_ABBREV.get(d, "?") for d in dias))
    if tipo == "MONTHLY":
        return u"Às %s, no dia %s de cada mês" % (hora, regra.get("month_day"))
    if tipo == "CRON":
        try:
            texto = cron_parser.parse(regra.get("cron_expression")).describe()
        except CronError:
            return PAUSE_REASONS["INVALID_CRON"]
        return texto[:1].upper() + texto[1:]
    return u"-"


def rule_state(registro):
    """(rotulo, motivo traduzido | None) da regra: Ativo ou Pausado + motivo."""
    if registro.get("active") == "Y":
        return u"Ativo", None
    motivo = registro.get("pause_reason")
    if not motivo:
        return u"Pausado", None
    return u"Pausado", PAUSE_REASONS.get(motivo, u"Motivo não catalogado (%s)" % motivo)


def normalize_filters(entrada):
    """Filtros da lista vindos de request.vars: nome (trecho), ambiente e ativo ('S' | 'N')."""
    entrada = entrada or {}
    filtros = {}
    nome = admin_crud.text(entrada.get("name"), NAME_MAX_LENGTH)
    if nome:
        filtros["name"] = nome
    ambiente = admin_crud.text(entrada.get("environment"), 30)
    ambiente = ambiente.upper() if ambiente else None
    if ambiente and _RE_ENVIRONMENT.fullmatch(ambiente):
        filtros["environment"] = ambiente
    ativo = admin_crud.text(entrada.get("active"), 1)
    if ativo in ("Y", "N"):
        filtros["active"] = ativo
    return filtros


def _parameters(registro):
    try:
        obj = json.loads(registro.get("params_json") or "{}")
    except ValueError:
        return {}
    return obj if isinstance(obj, dict) else {}


def _serialize(resolvidos):
    """JSON objeto {codigo: valor} com sort_keys; CHECKBOX vira 'true'/'false', como o formulario envia."""
    obj = {}
    for codigo, valor in resolvidos.items():
        if valor is None:
            continue
        if isinstance(valor, bool):
            valor = "true" if valor else "false"
        obj[codigo] = valor
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _state(registro, sensiveis=()):
    """Projecao serializavel dos campos da versao (datetime nao e serializavel em JSON).

    Respostas de parametros sensiveis em parametros_json entram pelo marcador (README §7.6, §10).
    """
    estado = {}
    for campo in VERSION_FIELDS:
        valor = registro.get(campo)
        if isinstance(valor, datetime.datetime):
            valor = valor.strftime("%Y-%m-%d %H:%M:%S")
        estado[campo] = valor
    if sensiveis:
        respostas = _parameters(registro)
        for codigo in sensiveis:
            if codigo in respostas:
                respostas[codigo] = admin_crud.sensitive_marker(respostas[codigo])
        estado["params_json"] = json.dumps(respostas, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return estado


def version(registro, sensiveis=()):
    """Versao do formulario de edicao (sha256 dos campos editaveis, sem valor sensivel)."""
    return admin_crud.version(_state(registro, sensiveis), VERSION_FIELDS)


class SchedulesService(object):
    """Regras de agendamento com repositorios, servico de disparo, relogio e log injetados."""

    def __init__(self, agendamentos, catalogo, usuarios, disparo, relogio, horizonte_dias, log,
                 tickets=None, rbac_repo=None, misfire_policy="RUN_ONCE", misfire_tolerance_s=300):
        self._schedules = agendamentos
        self._catalog = catalogo
        self._users = usuarios
        self._trigger_service = disparo
        self._clock = relogio
        self._horizon = horizonte_dias
        self._log = log
        self._misfire_policy = (misfire_policy or "RUN_ONCE").upper()
        self._misfire_tolerance_s = int(misfire_tolerance_s if misfire_tolerance_s is not None else 300)
        if tickets is None or rbac_repo is None:
            import repo_factory
            if tickets is None:
                tickets = repo_factory.get("tickets")
            if rbac_repo is None:
                rbac_repo = repo_factory.get("rbac")
        self._tickets = tickets
        self._rbac = rbac_repo

    # ------------------------------------------------------------- apoio

    def _overlap_warning(self, reg, prefixo=u"A próxima vez pode ser pulada: a execução #"):
        tid = reg.get("last_ticket_id")
        if not tid or not self._tickets:
            return None
        try:
            tck = self._tickets.get(tid)
        except RepoNotFound:
            return None
        if tck and tck.get("status") in ("PENDING", "RUNNING"):
            rotulo = ui_helpers.status_info(tck["status"])["rotulo"].lower()
            return u"%s%s ainda está %s." % (prefixo, tid, rotulo)
        return None

    def _check_expansion_problem(self, reg, agora):
        """Avalia se a regra sofreria pausa no desdobro (README §7.5 passos 2 e 5; CR-007 R-26).

        Retorna (codigo_motivo, texto_motivo) ou None se estiver apta.
        """
        try:
            estado = self._users.get_session_state(reg["user_id"])
        except RepoNotFound:
            return "USER_INACTIVE", PAUSE_REASONS["USER_INACTIVE"]
        if estado.get("usuario_ativo") != "Y":
            return "USER_INACTIVE", PAUSE_REASONS["USER_INACTIVE"]
        if estado.get("perfil_ativo") != "Y":
            return "NO_PERMISSION", PAUSE_REASONS["NO_PERMISSION"]

        try:
            script = self._catalog.scripts_get(reg["script_id"])
        except RepoNotFound:
            return "SCRIPT_INACTIVE", PAUSE_REASONS["SCRIPT_INACTIVE"]
        if script.get("active") != "Y":
            return "SCRIPT_INACTIVE", PAUSE_REASONS["SCRIPT_INACTIVE"]

        amb = None
        for a in self._catalog.environments_list(tamanho=1000)["itens"]:
            if a.get("name") == reg.get("environment"):
                amb = a
                break
        if amb is None or amb.get("active") != "Y":
            return "ENVIRONMENT_INACTIVE", PAUSE_REASONS["ENVIRONMENT_INACTIVE"]

        homologacoes = self._catalog.homologation_get(script["id"])
        if amb["id"] not in frozenset(homologacoes or ()):
            return "NO_PERMISSION", PAUSE_REASONS["NO_PERMISSION"]

        rbac_repo = self._rbac
        matriz = rbac_repo.matrix_get(estado["profile_id"])
        codigos = dict(
            (f["id"], f["code"]) for f in rbac_repo.features_list() if f.get("active") == "Y"
        )
        funcs = frozenset(codigos[fid] for fid in matriz.get("funcs", ()) if fid in codigos)
        ambs_nomes = []
        for aid in matriz.get("ambs", ()):
            try:
                ambs_nomes.append(self._catalog.environments_get(aid)["name"])
            except RepoNotFound:
                continue
        dados_ctx = dict(estado, features=funcs, environments=frozenset(ambs_nomes),
                         scripts=frozenset(matriz.get("scrs", ())))
        ctx_usuario = rbac.user_context(dados_ctx)
        ok, motivo_rbac = rbac.can_execute(ctx_usuario, script, amb, homologacoes)
        if not ok:
            codigo = rbac.pause_reason_for(motivo_rbac)
            return codigo, PAUSE_REASONS[codigo]

        try:
            respostas = json.loads(reg.get("params_json") or "{}")
        except (TypeError, ValueError):
            return "INVALID_PARAM", PAUSE_REASONS["INVALID_PARAM"]
        if not isinstance(respostas, dict):
            return "INVALID_PARAM", PAUSE_REASONS["INVALID_PARAM"]

        vinculos = self._links(script["id"])
        _snap, _resolv, erros_param = params_compiler.compile_snapshot(script, vinculos, respostas, agora)
        if erros_param:
            return "INVALID_PARAM", PAUSE_REASONS["INVALID_PARAM"]

        if reg.get("recurrence_type") == "CRON":
            try:
                recurrence.next_run(reg, agora, self._horizon)
            except CronError:
                return "INVALID_CRON", PAUSE_REASONS["INVALID_CRON"]

        return None

    def _now(self):
        return recurrence.without_microseconds(self._clock())

    def _get_visible(self, ctx, agendamento_id):
        """Regra existente e de ambiente autorizado; fora do escopo e tratada como inexistente (404)."""
        aid = _id(agendamento_id)
        if aid is None:
            raise RepoNotFound("agendamento invalido")
        registro = self._schedules.get(aid)
        if not rbac.can_view_environment(ctx, registro.get("environment")):
            self._log.warning("agendamento fora do escopo (login=%s agendamento=%s environment=%s)",
                              ctx.get("login"), aid, registro.get("environment"), extra={"action": FEATURE})
            raise RepoNotFound("agendamento fora do escopo")
        return registro

    def _authorize(self, ctx, script_id, ambiente):
        try:
            return self._trigger_service.authorize(ctx, script_id, ambiente)
        except DisparoNegado as exc:
            self._log.warning("agendamento negado ao editor (login=%s script_id=%r environment=%r reason=%s)",
                              ctx.get("login"), script_id, ambiente, exc.reason, extra={"action": FEATURE})
            raise OperationDenied(MSG_NO_PERMISSION)

    def _login(self, usuario_id, cache=None):
        if cache is not None and usuario_id in cache:
            return cache[usuario_id]
        try:
            login = self._users.get_by_id(usuario_id)["login"]
        except RepoNotFound:
            login = u"#%s" % usuario_id
        if cache is not None:
            cache[usuario_id] = login
        return login

    def _links(self, script_id):
        return [v for v in self._catalog.script_params_get(script_id) if v.get("active") == "Y"]

    def _sensitive_codes(self, script_id):
        # Todos os vinculos, ativos ou nao: parametros_json pode guardar resposta de parametro ja desativado.
        return frozenset(v["code"] for v in self._catalog.script_params_get(script_id)
                         if v.get("sensitive") == "Y")

    def _rule(self, dados, agora, erros):
        """Campos de recorrencia validados (README §7.2); so os do tipo escolhido sao mantidos."""
        tipo = admin_crud.text(dados.get("recurrence_type"), 10)
        regra = {"recurrence_type": tipo, "cron_expression": None, "run_time": None,
                 "week_days": None, "month_day": None}
        if tipo not in TYPE_LABELS:
            erros["recurrence_type"] = MSG_TYPE
        if tipo in ("DAILY", "WEEKLY", "MONTHLY"):
            regra["run_time"] = admin_crud.text(dados.get("run_time"), 5)
        if tipo == "WEEKLY":
            regra["week_days"] = _weekdays(dados.get("week_days"))
        if tipo == "MONTHLY":
            regra["month_day"] = admin_crud.text(dados.get("month_day"), 2)
        if tipo == "CRON":
            regra["cron_expression"] = admin_crud.text(dados.get("cron_expression"), 100)

        inicio, invalido = _date(dados.get("start_date"))
        if invalido:
            erros["start_date"] = MSG_DATE_INVALID
        elif inicio is None:
            if tipo == "ONCE":
                erros["start_date"] = MSG_ONCE_START
            else:
                # Decisao D3 do F5.2: sem inicio informado, a regra vale a partir de agora.
                inicio = recurrence.truncate_seconds(agora)
        fim, invalido = _date(dados.get("end_date"))
        if tipo == "ONCE":
            # data_fim nao se aplica a UNICA (README §7.2): ignorada e gravada nula.
            fim, invalido = None, False
        if invalido:
            erros["end_date"] = MSG_DATE_INVALID
        regra["start_date"] = inicio
        regra["end_date"] = fim

        if tipo in TYPE_LABELS:
            for campo, mensagem in recurrence.validate_rule(regra, self._horizon).items():
                erros.setdefault(campo, mensagem)
        if regra["month_day"] is not None and "month_day" not in erros:
            regra["month_day"] = int(regra["month_day"])
        return regra

    def _next_run(self, regra, agora, erros):
        try:
            proxima = recurrence.next_run(regra, agora, self._horizon)
        except CronError as exc:
            erros["cron_expression"] = exc.message
            return None
        if proxima is None:
            erros[GENERAL_FIELD] = MSG_NO_NEXT_RUN
        return proxima

    def _priority(self, ctx, valor, erros):
        texto = admin_crud.text(_last(valor), 2)
        if texto is None:
            prioridade = DEFAULT_PRIORITY
        else:
            prioridade = int(texto) if texto.isdigit() else None
        if prioridade is not None and rbac.allowed_priority(ctx, prioridade):
            return prioridade
        erros["priority"] = MSG_PRIORITY_ADMIN if prioridade == rbac.ADMIN_PRIORITY else MSG_PRIORITY
        return None

    def _answers(self, vinculos, respostas, anteriores):
        """Respostas dos vinculos ativos; na edicao, sensivel vazio mantem o valor salvo (requisito 2)."""
        codigos = set(v["code"] for v in vinculos)
        if not isinstance(respostas, dict):
            respostas = {}
        limpas = dict((k, _last(v)) for k, v in respostas.items() if k in codigos)
        for v in vinculos:
            codigo = v["code"]
            if v.get("sensitive") == "Y" and _empty(limpas.get(codigo)) and codigo in anteriores:
                limpas[codigo] = anteriores[codigo]
        return limpas

    def _audit_params(self, registro, sensiveis, comparar_com=None):
        """Texto 'codigo=valor' ordenado com os sensiveis mascarados (README §4.4)."""
        params = _parameters(registro)
        anteriores = _parameters(comparar_com) if comparar_com is not None else None
        partes = []
        for codigo in sorted(params):
            valor = params[codigo]
            if codigo in sensiveis:
                alterado = anteriores is not None and anteriores.get(codigo) != valor
                valor = MASK + (u" (alterado)" if alterado else u"")
            partes.append(u"%s=%s" % (codigo, valor))
        return u", ".join(partes)

    def _auditable(self, registro, sensiveis, comparar_com=None):
        aud = dict(registro)
        aud["parameters"] = self._audit_params(registro, sensiveis, comparar_com)
        for campo in ("start_date", "end_date", "next_run_at"):
            if registro.get(campo) is not None:
                aud[campo] = format_date(registro[campo])
        return aud

    # ------------------------------------------------------------ consulta

    def agenda(self, ctx):
        """Agenda (README §7.7, CR-004 T3): o que vai rodar de agora ate o fim do 7o dia seguinte.

        Retorna {atrasados: [...], dias: [{rotulo, itens}], aviso_total, ocorrencias}. Cada item:
        hora, regra_id, nome, script, ambiente, recorrencia e, no ultimo item de uma regra com mais de
        AGENDA_PER_RULE ocorrencias, 'mais' (quantas a mais no periodo). So leitura.
        """
        admin_crud.require_feature(ctx, FEATURE)
        agora = recurrence.truncate_seconds(self._now())
        fim = datetime.datetime.combine(agora.date() + datetime.timedelta(days=8), datetime.time())
        escopo = None if ctx.get("is_admin") is True else sorted(ctx.get("environments") or ())
        regras, pagina = [], 1
        while escopo != []:
            res = self._schedules.list(filtros={"active": "Y"}, pagina=pagina, tamanho=_AGENDA_PAGE,
                                            escopo_ambientes=escopo)
            regras.extend(res["itens"])
            if len(res["itens"]) < _AGENDA_PAGE:
                break
            pagina += 1
        scripts = {}
        atrasados, ocorrencias, problemas = [], [], []
        for reg in regras:
            if reg["script_id"] not in scripts:
                try:
                    scripts[reg["script_id"]] = self._catalog.scripts_get(reg["script_id"])["name"]
                except RepoNotFound:
                    scripts[reg["script_id"]] = u"#%s" % reg["script_id"]
            aviso_regra = self._overlap_warning(reg, prefixo=u"Pode ser pulada: a execução #")
            if not aviso_regra:
                prob = self._check_expansion_problem(reg, agora)
                if prob:
                    aviso_regra = u"Será pausada: %s." % prob[1]
            base = {"regra_id": reg["id"], "name": reg["name"], "script": scripts[reg["script_id"]],
                    "environment": reg["environment"], "recorrencia": describe_rule(reg),
                    "aviso": aviso_regra}
            prox = reg.get("next_run_at")
            if prox is None:
                continue
            if prox < agora:
                atraso_s = (agora - prox).total_seconds()
                if self._misfire_policy == "SKIP" and atraso_s > self._misfire_tolerance_s:
                    frase = u"passou do horário e será pulada (política de atraso: pular)"
                else:
                    frase = (u"deveria ter rodado às %s; vai rodar assim que o servidor puder."
                             % prox.strftime("%H:%M"))
                atrasados.append(dict(base, hora=prox.strftime("%d/%m %H:%M"), frase=frase))
            datas = []
            atual = prox if prox >= agora else None
            extra = 0
            try:
                proxima_calculada = recurrence.next_run(reg, agora, self._horizon)
                if atual is None:
                    atual = proxima_calculada
                while atual is not None and atual < fim:
                    if len(datas) < AGENDA_PER_RULE:
                        datas.append(atual)
                    elif extra < _AGENDA_COUNT_MAX:
                        extra += 1
                    else:
                        break
                    atual = recurrence.next_run(reg, atual, self._horizon)
            except CronError as exc:
                if reg.get("recurrence_type") == "CRON":
                    problemas.append(dict(base, problema=exc.message))
                continue
            for i, quando in enumerate(datas):
                item = dict(base, quando=quando, hora=quando.strftime("%H:%M"))
                if extra and i == len(datas) - 1:
                    item["mais"] = extra
                ocorrencias.append(item)
        ocorrencias.sort(key=lambda o: (o["quando"], o["regra_id"]))
        aviso_total = None
        if len(ocorrencias) > AGENDA_TOTAL:
            aviso_total = (u"Mostrando as primeiras %d execuções previstas; há mais no período." % AGENDA_TOTAL)
            ocorrencias = ocorrencias[:AGENDA_TOTAL]
        dias = collections.OrderedDict()
        for o in ocorrencias:
            dias.setdefault(o["quando"].date(), []).append(o)
        return {"atrasados": atrasados, "aviso_total": aviso_total, "total": len(ocorrencias),
                "dias": [{"rotulo": _day_label(d, agora.date()), "itens": itens} for d, itens in dias.items()],
                "problemas": problemas}

    def list(self, ctx, filtros, pagina, tamanho):
        """Pagina de regras dos ambientes autorizados (admin: todos), pronta para a tabela."""
        admin_crud.require_feature(ctx, FEATURE)
        escopo = None
        if ctx.get("is_admin") is not True:
            escopo = sorted(ctx.get("environments") or ())
            if not escopo:
                return {"itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        resultado = self._schedules.list(filtros=filtros, pagina=pagina, tamanho=tamanho,
                                              escopo_ambientes=escopo)
        scripts = {}
        logins = {}
        itens = []
        for reg in resultado["itens"]:
            sid = reg["script_id"]
            if sid not in scripts:
                try:
                    scripts[sid] = self._catalog.scripts_get(sid)["name"]
                except RepoNotFound:
                    scripts[sid] = u"#%s" % sid
            rotulo, motivo = rule_state(reg)
            aviso = None
            if reg.get("active") == "Y":
                aviso = self._overlap_warning(reg, prefixo=u"A próxima vez pode ser pulada: a execução #")
                if not aviso:
                    prob = self._check_expansion_problem(reg, self._now())
                    if prob:
                        aviso = u"Será pausada: %s." % prob[1]
            itens.append({
                "id": reg["id"],
                "name": reg["name"],
                "script": scripts[sid],
                "environment": reg["environment"],
                "tipo": TYPE_LABELS.get(reg["recurrence_type"], reg["recurrence_type"]),
                "recorrencia": describe_rule(reg),
                "cron_expression": reg.get("cron_expression") if reg["recurrence_type"] == "CRON" else None,
                "next_run_at": format_date(reg.get("next_run_at")) if reg["active"] == "Y" else "-",
                "last_run_at": format_date(reg.get("last_run_at")),
                "last_ticket_id": reg.get("last_ticket_id"),
                "responsavel": ui_helpers.ator_visivel(self._login(reg["user_id"], logins), ctx),
                "active": reg["active"],
                "state": rotulo,
                "reason": motivo,
                "aviso": aviso,
            })
        return dict(resultado, itens=itens)

    def form(self, ctx, agendamento_id=None, script_id=None, ambiente=None, enviados=None,
                   valores=None, erros=None):
        """Dados do formulario. Inclusao em etapas (script -> ambiente -> regra) com os filtros do F3.2;
        na edicao, script e ambiente sao fixos (decisao D2 do F5.2).

        enviados/valores/erros (opcionais) reapresentam um POST com erro: campos da regra,
        respostas do questionario e mensagens por campo. Lanca RepoNotFound, AccessDenied
        e OperationDenied (editor sem can_execute).
        """
        admin_crud.require_feature(ctx, FEATURE)
        erros = erros or {}
        enviados = enviados or {}
        dados = {"edicao": False, "etapa": 1, "grupos": [], "script": None, "ambientes": [], "form": None,
                 "regra": None, "erros": erros}
        atual = None
        if agendamento_id not in (None, ""):
            atual = self._get_visible(ctx, agendamento_id)
            script_id, ambiente = atual["script_id"], atual["environment"]
            dados["edicao"] = True
        elif not script_id:
            dados["grupos"] = self._trigger_service.available_scripts(ctx)
            return dados
        try:
            if not dados["edicao"]:
                script, ambientes = self._trigger_service.available_environments(ctx, script_id)
                dados.update(etapa=2, script=script, ambientes=ambientes)
                if not ambiente:
                    return dados
            anteriores = _parameters(atual) if atual else {}
            if valores is None:
                valores = anteriores
            form = self._trigger_service.prepare_form(ctx, script_id, ambiente, valores, erros)
        except DisparoNegado as exc:
            if dados["edicao"]:
                self._log.warning("edicao de agendamento negada (login=%s agendamento=%s reason=%s)",
                                  ctx.get("login"), atual["id"], exc.reason, extra={"action": FEATURE})
                raise OperationDenied(MSG_NO_PERMISSION)
            raise
        for campo in form["campos"]:
            campo["mantido"] = campo["sensitive"] and campo["code"] in anteriores
        dados.update(etapa=3, form=form, regra=self._form_rule(ctx, atual, enviados))
        return dados

    def _form_rule(self, ctx, atual, enviados):
        base = atual or {"recurrence_type": "DAILY", "priority": DEFAULT_PRIORITY}
        pausa_aviso = None
        if atual and atual.get("active") == "N":
            dt_pausa = format_date(atual.get("updated_at"))
            ator_pausa = ui_helpers.nome_ator(ui_helpers.registro(atual, ctx)["updated_by"])
            motivo_txt = PAUSE_REASONS.get(atual.get("pause_reason"), atual.get("pause_reason")) or u"Desconhecido"
            pausa_aviso = (
                u"Pausada em %s por %s: %s. "
                u"Edite a regra para corrigir (ao salvar, ela passa a rodar com as suas permissões) e depois retome."
                % (dt_pausa, ator_pausa, motivo_txt)
            )
        regra = {
            "id": base.get("id"),
            "name": base.get("name") or "",
            "recurrence_type": base.get("recurrence_type"),
            "cron_expression": base.get("cron_expression") or "",
            "run_time": base.get("run_time") or "",
            "week_days": [int(d) for d in (base.get("week_days") or "").split(",") if d.isdigit()],
            "month_day": base.get("month_day") or "",
            "start_date": _date_field_value(base.get("start_date")) if atual else "",
            "end_date": _date_field_value(base.get("end_date")),
            "priority": base.get("priority") or DEFAULT_PRIORITY,
            "version": version(atual, self._sensitive_codes(atual["script_id"])) if atual else "",
            "active": base.get("active", "Y"),
            "state": rule_state(atual) if atual else None,
            "responsavel": ui_helpers.ator_visivel(self._login(atual["user_id"]), ctx) if atual else None,
            "outro_responsavel": bool(atual) and atual["user_id"] != ctx.get("user_id"),
            "registro": ui_helpers.registro(atual, ctx) if atual else None,
            "pausa_aviso": pausa_aviso,
        }
        for campo in ("name", "recurrence_type", "cron_expression", "run_time", "month_day",
                      "start_date", "end_date", "priority", "version"):
            if campo in enviados and enviados[campo] is not None:
                regra[campo] = enviados[campo]
        if "week_days" in enviados:
            texto = _weekdays(enviados["week_days"]) or ""
            regra["week_days"] = [int(d) for d in texto.split(",") if d.isdigit()]
        return regra

    def preview(self, ctx, dados):
        """Proximas PREVIEW_COUNT execucoes e a descricao da regra, sem gravar.

        Retorna {datas: [texto], descricao: texto | None, erros: {campo: mensagem}}.
        """
        admin_crud.require_feature(ctx, FEATURE)
        erros = collections.OrderedDict()
        agora = self._now()
        regra = self._rule(dados or {}, agora, erros)
        if erros:
            return {"datas": [], "description": None, "erros": dict(erros)}
        try:
            datas = recurrence.next_runs(regra, agora, PREVIEW_COUNT, self._horizon)
        except CronError as exc:
            return {"datas": [], "description": None, "erros": {"cron_expression": exc.message}}
        if not datas:
            return {"datas": [], "description": describe_rule(regra), "erros": {GENERAL_FIELD: MSG_NO_NEXT_RUN}}
        return {"datas": [format_preview(d) for d in datas], "description": describe_rule(regra), "erros": {}}

    # ----------------------------------------------------------- gravacao

    def save(self, ctx, ip, dados):
        """Inclui (sem 'id') ou altera uma regra. Retorna (id | None, erros_por_campo).

        dados: id, versao, nome, script_id e ambiente (so na inclusao), tipo_recorrencia,
        expressao_cron, hora_execucao, weekdays, dia_mes, data_inicio, data_fim, prioridade e
        respostas ({codigo: valor}). Lanca RepoNotFound, AccessDenied e OperationDenied
        (editor sem can_execute).
        """
        admin_crud.require_feature(ctx, FEATURE)
        atual = None
        if dados.get("id") not in (None, ""):
            atual = self._get_visible(ctx, dados.get("id"))
            script, amb = self._authorize(ctx, atual["script_id"], atual["environment"])
        else:
            script, amb = self._authorize(ctx, admin_crud.text(dados.get("script_id"), 10),
                                          admin_crud.text(dados.get("environment"), 30))
        agora = self._now()
        erros = collections.OrderedDict()

        nome = admin_crud.text(dados.get("name"))
        if nome is None:
            erros["name"] = MSG_NAME_REQUIRED
        elif len(nome) > NAME_MAX_LENGTH:
            erros["name"] = MSG_NAME_LENGTH
        regra = self._rule(dados, agora, erros)
        prioridade = self._priority(ctx, dados.get("priority"), erros)

        vinculos = self._links(script["id"])
        anteriores = _parameters(atual) if atual else {}
        respostas = self._answers(vinculos, dados.get("respostas"), anteriores)
        # Compila o snapshot completo so para validar: o daemon recompila a cada desdobro (README §7.5 passo 5).
        _snapshot, resolvidos, erros_param = params_compiler.compile_snapshot(script, vinculos, respostas, agora)
        for codigo, mensagem in erros_param.items():
            erros.setdefault(codigo, mensagem)

        proxima = None
        if not erros:
            proxima = self._next_run(regra, agora, erros)
        if erros:
            self._log.info("validacao do agendamento com erros (login=%s agendamento=%s campos=%s)",
                           ctx.get("login"), atual["id"] if atual else None, ",".join(sorted(erros)),
                           extra={"action": FEATURE})
            return (atual["id"] if atual else None), dict(erros)

        registro = dict(regra, name=nome, script_id=script["id"], environment=amb["name"],
                        user_id=ctx["user_id"], priority=prioridade,
                        params_json=_serialize(resolvidos), next_run_at=proxima)
        sensiveis = set(v["code"] for v in vinculos if v.get("sensitive") == "Y")
        if atual is None:
            return self._insert(ctx, ip, registro, sensiveis)
        if admin_crud.text(dados.get("version"), 64) != version(atual, self._sensitive_codes(atual["script_id"])):
            return atual["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        return self._update(ctx, ip, atual, registro, sensiveis)

    def _insert(self, ctx, ip, registro, sensiveis):
        novo = dict(registro, active="Y", pause_reason=None)
        detalhe = admin_crud.insert_detail(self._auditable(novo, sensiveis), _INSERT_FIELDS)
        try:
            criado = self._schedules.insert(novo, auditoria=admin_crud.audit_entry(ctx, ip, "CREATE", detalhe))
        except RepoViolation as exc:
            self._log.error("agendamento rejeitado pelo repositorio (login=%s constraint=%s)",
                            ctx.get("login"), exc.constraint, extra={"action": "CREATE"})
            return None, {GENERAL_FIELD: admin_crud.MSG_FAILURE}
        self._log.info("agendamento incluido (login=%s agendamento=%s script_id=%s environment=%s tipo=%s)",
                       ctx.get("login"), criado["id"], criado["script_id"], criado["environment"],
                       criado["recurrence_type"], extra={"action": "CREATE"})
        return criado["id"], {}

    def _update(self, ctx, ip, atual, registro, sensiveis):
        depois = dict(atual, **registro)
        detalhe = admin_crud.changes_detail(self._auditable(atual, sensiveis),
                                                self._auditable(depois, sensiveis, atual), AUDIT_FIELDS)
        trocou_responsavel = atual["user_id"] != registro["user_id"]
        if detalhe is None and not trocou_responsavel:
            return atual["id"], {}
        # README §10: a edicao sempre registra o usuario_id anterior e o novo.
        responsavel = u"user_id: %s (%s)%s%s (%s)" % (
            atual["user_id"], self._login(atual["user_id"]), _ARROW,
            registro["user_id"], ctx.get("login"))
        detalhe = admin_crud.free_detail(responsavel if detalhe is None else u"%s; %s" % (responsavel, detalhe))
        try:
            self._schedules.update(atual["id"], registro,
                                       esperado=admin_crud.expected(atual, _EXPECTED_FIELDS),
                                       auditoria=admin_crud.audit_entry(ctx, ip, "UPDATE", detalhe))
        except RepoConflict:
            return atual["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        except RepoViolation as exc:
            self._log.error("alteracao de agendamento rejeitada pelo repositorio (login=%s agendamento=%s "
                            "constraint=%s)", ctx.get("login"), atual["id"], exc.constraint,
                            extra={"action": "UPDATE"})
            return atual["id"], {GENERAL_FIELD: admin_crud.MSG_FAILURE}
        self._log.info("agendamento alterado (login=%s agendamento=%s user_id=%s->%s)",
                       ctx.get("login"), atual["id"], atual["user_id"], registro["user_id"],
                       extra={"action": "UPDATE"})
        return atual["id"], {}

    def pause(self, ctx, ip, agendamento_id):
        """Pausa manual (pause_reason = 'MANUAL'), otimista sobre next_run (README §7.5 passo 7).

        Audita SCHEDULE_PAUSE. Lanca OperationDenied (ja pausada), RepoConflict, RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        atual = self._get_visible(ctx, agendamento_id)
        if atual["active"] != "Y":
            raise OperationDenied(MSG_ALREADY_PAUSED)
        detalhe = admin_crud.changes_detail(atual, dict(atual, active="N", pause_reason="MANUAL"),
                                                ("active", "pause_reason"))
        alterado = self._schedules.pause(atual["id"], "MANUAL", antiga_data=atual["next_run_at"],
                                             auditoria=admin_crud.audit_entry(ctx, ip, "SCHEDULE_PAUSE", detalhe))
        self._log.info("agendamento pausado (login=%s agendamento=%s reason=MANUAL)", ctx.get("login"),
                       atual["id"], extra={"action": "SCHEDULE_PAUSE"})
        return alterado

    def resume(self, ctx, ip, agendamento_id):
        """Retoma a regra: revalida can_execute de quem retoma, recalcula next_run a partir
        de agora, limpa pausa_motivo e reativa. O responsavel (usuario_id) nao muda.

        Audita UPDATE. Lanca OperationDenied (ja ativa, sem permissao ou sem proxima execucao),
        RepoConflict, RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        atual = self._get_visible(ctx, agendamento_id)
        if atual["active"] == "Y":
            raise OperationDenied(MSG_ALREADY_ACTIVE)
        agora = self._now()
        problema = self._check_expansion_problem(atual, agora)
        if problema is not None:
            _cod, causa = problema
            raise OperationDenied(u"%s. %s" % (causa, MSG_RESUME_GUIDANCE))
        self._authorize(ctx, atual["script_id"], atual["environment"])
        try:
            proxima = recurrence.next_run(atual, agora, self._horizon)
        except CronError as exc:
            raise OperationDenied(u"%s: %s" % (PAUSE_REASONS["INVALID_CRON"], exc.message))
        if proxima is None:
            raise OperationDenied(MSG_RESUME_NO_NEXT_RUN)
        antes = {"active": atual["active"], "pause_reason": atual.get("pause_reason"),
                 "next_run_at": format_date(atual.get("next_run_at"))}
        depois = {"active": "Y", "pause_reason": None, "next_run_at": format_date(proxima)}
        detalhe = admin_crud.changes_detail(antes, depois, ("active", "pause_reason", "next_run_at"))
        alterado = self._schedules.resume(
            atual["id"], proxima, esperado=admin_crud.expected(atual, ("active", "pause_reason", "next_run_at")),
            auditoria=admin_crud.audit_entry(ctx, ip, "UPDATE", detalhe))
        self._log.info("agendamento retomado (login=%s agendamento=%s proxima=%s)", ctx.get("login"),
                       atual["id"], format_date(proxima), extra={"action": "UPDATE"})
        return alterado


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from gluon import current
            import sss_logging
            import ticket_service
            fabrica = current.repo_factory
            cfg = current.sss_cfg
            tickets = fabrica.get("tickets")
            _default = SchedulesService(
                agendamentos=fabrica.get("schedules"),
                catalogo=fabrica.get("catalog"),
                usuarios=fabrica.get("users"),
                disparo=ticket_service._service(),
                relogio=tickets.now,
                horizonte_dias=cfg.agent.cron_horizon_days,
                log=sss_logging.get_logger("sss_web", cfg),
                tickets=tickets,
                rbac_repo=fabrica.get("rbac"),
                misfire_policy=cfg.agent.misfire_policy,
                misfire_tolerance_s=cfg.agent.misfire_tolerance_s,
            )
        return _default


def list_page(ctx, filtros, pagina, tamanho):
    """Pagina de regras (servico padrao)."""
    return _service().list(ctx, filtros, pagina, tamanho)


def agenda(ctx):
    """Agenda dos proximos 7 dias (servico padrao)."""
    return _service().agenda(ctx)


def form(ctx, agendamento_id=None, script_id=None, ambiente=None, enviados=None, valores=None, erros=None):
    """Dados do formulario de regra (servico padrao)."""
    return _service().form(ctx, agendamento_id, script_id, ambiente, enviados, valores, erros)


def preview(ctx, dados):
    """Proximas execucoes e descricao da regra (servico padrao)."""
    return _service().preview(ctx, dados)


def save(ctx, ip, dados):
    """Inclusao ou alteracao de regra (servico padrao)."""
    return _service().save(ctx, ip, dados)


def pause(ctx, ip, agendamento_id):
    """Pausa manual (servico padrao)."""
    return _service().pause(ctx, ip, agendamento_id)


def resume(ctx, ip, agendamento_id):
    """Retomada (servico padrao)."""
    return _service().resume(ctx, ip, agendamento_id)
