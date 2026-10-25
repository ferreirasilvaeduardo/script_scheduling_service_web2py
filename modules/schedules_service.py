# -*- coding: utf-8 -*-
"""Regras de agendamento recorrente (README §4.3.C MANAGE_SCHEDULES, §7, §10 tabela 12).

Segue docs/ADMIN_CRUD_PATTERN.md: nao importa gluon, recebe ctx e ip por parametro e o servico
padrao do processo web e criado sob demanda (_service). O relogio e injetado: na web, o
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
from sss.core import cron_parser
from sss.core import params_compiler
from sss.core import rbac
from sss.core import recurrence
import ui_helpers
from admin_crud import GENERAL_FIELD, OperationDenied
from sss.core.cron_parser import CronError
from sss.persistence.repo_errors import RepoConflict, RepoNotFound, RepoViolation
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
_IMPACT_NAMES = 5
_RULES_PAGE = 500
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


def _id(value):
    value = admin_crud.text(value, 11)
    if value is None or not _RE_ID.fullmatch(value) or int(value) < 1:
        return None
    return int(value)


def _last(value):
    if isinstance(value, (list, tuple)):
        return value[-1] if value else None
    return value


def _empty(value):
    return value is None or (isinstance(value, str) and value.strip() == "")


def _date(value):
    """(datetime sem microssegundos | None, invalido). Vazio e (None, False)."""
    text = admin_crud.text(value)
    if text is None:
        return None, False
    for format_value in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, format_value).replace(microsecond=0), False
        except ValueError:
            continue
    return None, True


def _weekdays(value):
    """Checkboxes (lista) ou texto '1,3,5' -> texto ISO ordenado sem repeticao; lixo segue para a validacao."""
    if isinstance(value, (list, tuple)):
        items = [v for v in value if isinstance(v, str)]
    elif isinstance(value, str):
        items = value.split(",")
    else:
        return None
    items = [i.strip() for i in items if i.strip()]
    if not items:
        return None
    if all(i.isdigit() and len(i) == 1 for i in items):
        return ",".join(str(n) for n in sorted(set(int(i) for i in items)))
    return ",".join(items)[:20]


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


def _day_label(day, today):
    """'Hoje', 'Amanhã' ou 'sexta-feira, 18/10' (README §7.7)."""
    if day == today:
        return u"Hoje"
    if day == today + datetime.timedelta(days=1):
        return u"Amanhã"
    return u"%s, %s" % (_DAY_NAMES[day.weekday()], day.strftime("%d/%m"))


def describe_rule(rule):
    """Descricao da recorrencia em portugues para a lista e a previa."""
    kind = rule.get("recurrence_type")
    hour = rule.get("run_time")
    if kind == "ONCE":
        return u"Uma vez, em %s" % format_date(rule.get("start_date"))
    if kind == "DAILY":
        return u"Todos os dias às %s" % hour
    if kind == "WEEKLY":
        days = [int(d) for d in (rule.get("week_days") or "").split(",") if d.strip().isdigit()]
        return u"Às %s, %s" % (hour, u", ".join(_DAY_ABBREV.get(d, "?") for d in days))
    if kind == "MONTHLY":
        return u"Às %s, no dia %s de cada mês" % (hour, rule.get("month_day"))
    if kind == "CRON":
        try:
            text = cron_parser.parse(rule.get("cron_expression")).describe()
        except CronError:
            return PAUSE_REASONS["INVALID_CRON"]
        return text[:1].upper() + text[1:]
    return u"-"


def rule_state(record):
    """(rotulo, motivo traduzido | None) da regra: Ativo ou Pausado + motivo."""
    if record.get("active") == "Y":
        return u"Ativo", None
    reason = record.get("pause_reason")
    if not reason:
        return u"Pausado", None
    return u"Pausado", PAUSE_REASONS.get(reason, u"Motivo não catalogado (%s)" % reason)


def normalize_filters(input_value):
    """Filtros da lista vindos de request.vars: name (trecho), environment e active ('Y' | 'N')."""
    input_value = input_value or {}
    filters = {}
    name = admin_crud.text(input_value.get("name"), NAME_MAX_LENGTH)
    if name:
        filters["name"] = name
    environment = admin_crud.text(input_value.get("environment"), 30)
    environment = environment.upper() if environment else None
    if environment and _RE_ENVIRONMENT.fullmatch(environment):
        filters["environment"] = environment
    active = admin_crud.text(input_value.get("active"), 1)
    if active in ("Y", "N"):
        filters["active"] = active
    return filters


def _parameters(record):
    try:
        obj = json.loads(record.get("params_json") or "{}")
    except ValueError:
        return {}
    return obj if isinstance(obj, dict) else {}


def _serialize(resolved):
    """JSON objeto {codigo do parametro: valor} com sort_keys; CHECKBOX vira 'true'/'false', como o formulario envia."""
    obj = {}
    for code, value in resolved.items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        obj[code] = value
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _state(record, sensitive=()):
    """Projecao serializavel dos campos da versao (datetime nao e serializavel em JSON).

    Respostas de parametros sensiveis em parametros_json entram pelo marcador (README §7.6, §10).
    """
    state = {}
    for field in VERSION_FIELDS:
        value = record.get(field)
        if isinstance(value, datetime.datetime):
            value = value.strftime("%Y-%m-%d %H:%M:%S")
        state[field] = value
    if sensitive:
        answers = _parameters(record)
        for code in sensitive:
            if code in answers:
                answers[code] = admin_crud.sensitive_marker(answers[code])
        state["params_json"] = json.dumps(answers, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return state


def version(record, sensitive=()):
    """Versao do formulario de edicao (sha256 dos campos editaveis, sem valor sensivel)."""
    return admin_crud.version(_state(record, sensitive), VERSION_FIELDS)


class SchedulesService(object):
    """Regras de agendamento com repositorios, servico de disparo, relogio e log injetados."""

    def __init__(self, schedules, catalog, users, trigger_service, clock, horizon_days, log,
                 tickets=None, rbac_repo=None, misfire_policy="RUN_ONCE", misfire_tolerance_s=300):
        self._schedules = schedules
        self._catalog = catalog
        self._users = users
        self._trigger_service = trigger_service
        self._clock = clock
        self._horizon = horizon_days
        self._log = log
        self._misfire_policy = (misfire_policy or "RUN_ONCE").upper()
        self._misfire_tolerance_s = int(misfire_tolerance_s if misfire_tolerance_s is not None else 300)
        if tickets is None or rbac_repo is None:
            from sss.persistence import repo_factory
            if tickets is None:
                tickets = repo_factory.get("tickets")
            if rbac_repo is None:
                rbac_repo = repo_factory.get("rbac")
        self._tickets = tickets
        self._rbac = rbac_repo

    # ------------------------------------------------------------- apoio

    def _overlap_warning(self, reg, prefix=u"A próxima vez pode ser pulada: a execução #"):
        tid = reg.get("last_ticket_id")
        if not tid or not self._tickets:
            return None
        try:
            tck = self._tickets.get(tid)
        except RepoNotFound:
            return None
        if tck and tck.get("status") in ("PENDING", "RUNNING"):
            label = ui_helpers.status_info(tck["status"])["label"].lower()
            return u"%s%s ainda está %s." % (prefix, tid, label)
        return None

    def _check_expansion_problem(self, reg, now):
        """Avalia se a regra sofreria pausa no desdobro (README §7.5 passos 2 e 5; CR-007 R-26).

        Retorna (codigo do motivo, texto do motivo) ou None se estiver apta.
        """
        try:
            state = self._users.get_session_state(reg["user_id"])
        except RepoNotFound:
            return "USER_INACTIVE", PAUSE_REASONS["USER_INACTIVE"]
        if state.get("active_user") != "Y":
            return "USER_INACTIVE", PAUSE_REASONS["USER_INACTIVE"]
        if state.get("active_profile") != "Y":
            return "NO_PERMISSION", PAUSE_REASONS["NO_PERMISSION"]

        try:
            script = self._catalog.scripts_get(reg["script_id"])
        except RepoNotFound:
            return "SCRIPT_INACTIVE", PAUSE_REASONS["SCRIPT_INACTIVE"]
        if script.get("active") != "Y":
            return "SCRIPT_INACTIVE", PAUSE_REASONS["SCRIPT_INACTIVE"]

        env = None
        for a in self._catalog.environments_list(size=1000)["items"]:
            if a.get("name") == reg.get("environment"):
                env = a
                break
        if env is None or env.get("active") != "Y":
            return "ENVIRONMENT_INACTIVE", PAUSE_REASONS["ENVIRONMENT_INACTIVE"]

        homologations = self._catalog.homologation_get(script["id"])
        if env["id"] not in frozenset(homologations or ()):
            return "NO_PERMISSION", PAUSE_REASONS["NO_PERMISSION"]

        rbac_repo = self._rbac
        matrix = rbac_repo.matrix_get(state["profile_id"])
        codes = dict(
            (f["id"], f["code"]) for f in rbac_repo.features_list() if f.get("active") == "Y"
        )
        features = frozenset(codes[fid] for fid in matrix.get("funcs", ()) if fid in codes)
        envs_names = []
        for aid in matrix.get("ambs", ()):
            try:
                envs_names.append(self._catalog.environments_get(aid)["name"])
            except RepoNotFound:
                continue
        data_ctx = dict(state, features=features, environments=frozenset(envs_names),
                         scripts=frozenset(matrix.get("scrs", ())))
        ctx_user = rbac.user_context(data_ctx)
        ok, reason_rbac = rbac.can_execute(ctx_user, script, env, homologations)
        if not ok:
            code = rbac.pause_reason_for(reason_rbac)
            return code, PAUSE_REASONS[code]

        try:
            answers = json.loads(reg.get("params_json") or "{}")
        except (TypeError, ValueError):
            return "INVALID_PARAM", PAUSE_REASONS["INVALID_PARAM"]
        if not isinstance(answers, dict):
            return "INVALID_PARAM", PAUSE_REASONS["INVALID_PARAM"]

        links = self._links(script["id"])
        _snap, _resolv, errors_param = params_compiler.compile_snapshot(script, links, answers, now)
        if errors_param:
            return "INVALID_PARAM", PAUSE_REASONS["INVALID_PARAM"]

        if reg.get("recurrence_type") == "CRON":
            try:
                recurrence.next_run(reg, now, self._horizon)
            except CronError:
                return "INVALID_CRON", PAUSE_REASONS["INVALID_CRON"]

        return None

    def filter_environments(self, ctx):
        """Ambientes do filtro da lista (CR-018b): os do escopo da lista (admin: todos os cadastrados)."""
        admin_crud.require_feature(ctx, FEATURE)
        if ctx.get("is_admin") is True:
            return sorted(a["name"] for a in self._catalog.environments_list(page=1, size=1000)["items"])
        return sorted(ctx.get("environments") or ())

    def active_rules(self, script_ids):
        """Regras ativas dos scripts (sem guarda de funcionalidade): [{id, name, script_id}] por nome.

        Usada pelos cadastros de parametros e de scripts para avisar quem edita (CR-018a).
        """
        ids = set(script_ids or ())
        found = []
        for sid in sorted(ids):
            page = 1
            while True:
                result = self._schedules.list(filters={"script_id": sid, "active": "Y"}, page=page, size=_RULES_PAGE)
                found.extend({"id": r["id"], "name": r["name"], "script_id": r["script_id"],
                              "_rule": r} for r in result["items"])
                if len(result["items"]) < _RULES_PAGE:
                    break
                page += 1
        return sorted(found, key=lambda r: (r["name"], r["id"]))

    def rules_at_risk(self, script_ids):
        """Regras ativas que o proximo desdobro vai pausar, com o motivo (a mesma checagem do agente, R-26).

        Retorna [{id, name, reason}]. Usada logo depois de salvar um parametro ou os vinculos de um
        script (CR-018a): a mudanca pode invalidar as respostas guardadas em params_json.
        """
        now = self._now()
        risky = []
        for r in self.active_rules(script_ids):
            problem = self._check_expansion_problem(r["_rule"], now)
            if problem is not None:
                risky.append({"id": r["id"], "name": r["name"], "reason": problem[1]})
        return risky

    def _now(self):
        return recurrence.without_microseconds(self._clock())

    def _get_visible(self, ctx, schedule_id):
        """Regra existente e de ambiente autorizado; fora do escopo e tratada como inexistente (404)."""
        aid = _id(schedule_id)
        if aid is None:
            raise RepoNotFound("agendamento invalido")
        record = self._schedules.get(aid)
        if not rbac.can_view_environment(ctx, record.get("environment")):
            self._log.warning("agendamento fora do escopo (login=%s agendamento=%s environment=%s)",
                              ctx.get("login"), aid, record.get("environment"), extra={"action": FEATURE})
            raise RepoNotFound("agendamento fora do escopo")
        return record

    def _authorize(self, ctx, script_id, environment):
        try:
            return self._trigger_service.authorize(ctx, script_id, environment)
        except DisparoNegado as exc:
            self._log.warning("agendamento negado ao editor (login=%s script_id=%r environment=%r reason=%s)",
                              ctx.get("login"), script_id, environment, exc.reason, extra={"action": FEATURE})
            raise OperationDenied(MSG_NO_PERMISSION)

    def _login(self, user_id, cache=None):
        if cache is not None and user_id in cache:
            return cache[user_id]
        try:
            login = self._users.get_by_id(user_id)["login"]
        except RepoNotFound:
            login = u"#%s" % user_id
        if cache is not None:
            cache[user_id] = login
        return login

    def _links(self, script_id):
        return [v for v in self._catalog.script_params_get(script_id) if v.get("active") == "Y"]

    def _sensitive_codes(self, script_id):
        # Todos os vinculos, ativos ou nao: parametros_json pode guardar resposta de parametro ja desativado.
        return frozenset(v["code"] for v in self._catalog.script_params_get(script_id)
                         if v.get("sensitive") == "Y")

    def _rule(self, data, now, errors):
        """Campos de recorrencia validados (README §7.2); so os do tipo escolhido sao mantidos."""
        kind = admin_crud.text(data.get("recurrence_type"), 10)
        rule = {"recurrence_type": kind, "cron_expression": None, "run_time": None,
                 "week_days": None, "month_day": None}
        if kind not in TYPE_LABELS:
            errors["recurrence_type"] = MSG_TYPE
        if kind in ("DAILY", "WEEKLY", "MONTHLY"):
            rule["run_time"] = admin_crud.text(data.get("run_time"), 5)
        if kind == "WEEKLY":
            rule["week_days"] = _weekdays(data.get("week_days"))
        if kind == "MONTHLY":
            rule["month_day"] = admin_crud.text(data.get("month_day"), 2)
        if kind == "CRON":
            rule["cron_expression"] = admin_crud.text(data.get("cron_expression"), 100)

        start, invalid = _date(data.get("start_date"))
        if invalid:
            errors["start_date"] = MSG_DATE_INVALID
        elif start is None:
            if kind == "ONCE":
                errors["start_date"] = MSG_ONCE_START
            else:
                # Decisao D3 do F5.2: sem inicio informado, a regra vale a partir de agora.
                start = recurrence.truncate_seconds(now)
        end, invalid = _date(data.get("end_date"))
        if kind == "ONCE":
            # data_fim nao se aplica a UNICA (README §7.2): ignorada e gravada nula.
            end, invalid = None, False
        if invalid:
            errors["end_date"] = MSG_DATE_INVALID
        rule["start_date"] = start
        rule["end_date"] = end

        if kind in TYPE_LABELS:
            for field, message in recurrence.validate_rule(rule, self._horizon).items():
                errors.setdefault(field, message)
        if rule["month_day"] is not None and "month_day" not in errors:
            rule["month_day"] = int(rule["month_day"])
        return rule

    def _next_run(self, rule, now, errors):
        try:
            next_value = recurrence.next_run(rule, now, self._horizon)
        except CronError as exc:
            errors["cron_expression"] = exc.message
            return None
        if next_value is None:
            errors[GENERAL_FIELD] = MSG_NO_NEXT_RUN
        return next_value

    def _priority(self, ctx, value, errors):
        text = admin_crud.text(_last(value), 2)
        if text is None:
            priority = DEFAULT_PRIORITY
        else:
            priority = int(text) if text.isdigit() else None
        if priority is not None and rbac.allowed_priority(ctx, priority):
            return priority
        errors["priority"] = MSG_PRIORITY_ADMIN if priority == rbac.ADMIN_PRIORITY else MSG_PRIORITY
        return None

    def _answers(self, links, answers, previous):
        """Respostas dos vinculos ativos; na edicao, sensivel vazio mantem o valor salvo (requisito 2)."""
        codes = set(v["code"] for v in links)
        if not isinstance(answers, dict):
            answers = {}
        cleaned = dict((k, _last(v)) for k, v in answers.items() if k in codes)
        for v in links:
            code = v["code"]
            if v.get("sensitive") == "Y" and _empty(cleaned.get(code)) and code in previous:
                cleaned[code] = previous[code]
        return cleaned

    def _audit_params(self, record, sensitive, compare_with=None):
        """Texto 'codigo=valor' ordenado com os sensiveis mascarados (README §4.4)."""
        params = _parameters(record)
        previous = _parameters(compare_with) if compare_with is not None else None
        parts = []
        for code in sorted(params):
            value = params[code]
            if code in sensitive:
                changed = previous is not None and previous.get(code) != value
                value = MASK + (u" (alterado)" if changed else u"")
            parts.append(u"%s=%s" % (code, value))
        return u", ".join(parts)

    def _auditable(self, record, sensitive, compare_with=None):
        aud = dict(record)
        aud["parameters"] = self._audit_params(record, sensitive, compare_with)
        for field in ("start_date", "end_date", "next_run_at"):
            if record.get(field) is not None:
                aud[field] = format_date(record[field])
        return aud

    # ------------------------------------------------------------ consulta

    def agenda(self, ctx):
        """Agenda (README §7.7, CR-004 T3): o que vai rodar de agora ate o fim do 7o dia seguinte.

        Retorna {delayed: [...], days: [{label, items}], total_warning, total}. Cada item: hour,
        rule_id, name, script, environment, recurrence, warning e, no ultimo item de uma regra com mais de
        AGENDA_PER_RULE ocorrencias, 'more' (quantas a mais no periodo). So leitura.
        """
        admin_crud.require_feature(ctx, FEATURE)
        now = recurrence.truncate_seconds(self._now())
        end = datetime.datetime.combine(now.date() + datetime.timedelta(days=8), datetime.time())
        scope = None if ctx.get("is_admin") is True else sorted(ctx.get("environments") or ())
        rules, page = [], 1
        while scope != []:
            res = self._schedules.list(filters={"active": "Y"}, page=page, size=_AGENDA_PAGE,
                                            environment_scope=scope)
            rules.extend(res["items"])
            if len(res["items"]) < _AGENDA_PAGE:
                break
            page += 1
        scripts = {}
        late, occurrences, problems = [], [], []
        for reg in rules:
            if reg["script_id"] not in scripts:
                try:
                    scripts[reg["script_id"]] = self._catalog.scripts_get(reg["script_id"])["name"]
                except RepoNotFound:
                    scripts[reg["script_id"]] = u"#%s" % reg["script_id"]
            warning_rule = self._overlap_warning(reg, prefix=u"Pode ser pulada: a execução #")
            if not warning_rule:
                prob = self._check_expansion_problem(reg, now)
                if prob:
                    warning_rule = u"Será pausada: %s." % prob[1]
            base = {"rule_id": reg["id"], "name": reg["name"], "script": scripts[reg["script_id"]],
                    "environment": reg["environment"], "recurrence": describe_rule(reg),
                    "warning": warning_rule}
            next_value = reg.get("next_run_at")
            if next_value is None:
                continue
            if next_value < now:
                delay_s = (now - next_value).total_seconds()
                if self._misfire_policy == "SKIP" and delay_s > self._misfire_tolerance_s:
                    phrase = u"passou do horário e será pulada (política de atraso: pular)"
                else:
                    phrase = (u"deveria ter rodado às %s; vai rodar assim que o servidor puder."
                             % next_value.strftime("%H:%M"))
                late.append(dict(base, hour=next_value.strftime("%d/%m %H:%M"), phrase=phrase))
            dates = []
            current = next_value if next_value >= now else None
            extra = 0
            try:
                next_computed = recurrence.next_run(reg, now, self._horizon)
                if current is None:
                    current = next_computed
                while current is not None and current < end:
                    if len(dates) < AGENDA_PER_RULE:
                        dates.append(current)
                    elif extra < _AGENDA_COUNT_MAX:
                        extra += 1
                    else:
                        break
                    current = recurrence.next_run(reg, current, self._horizon)
            except CronError as exc:
                if reg.get("recurrence_type") == "CRON":
                    problems.append(dict(base, problem=exc.message))
                continue
            for i, when in enumerate(dates):
                item = dict(base, when=when, hour=when.strftime("%H:%M"))
                if extra and i == len(dates) - 1:
                    item["more"] = extra
                occurrences.append(item)
        occurrences.sort(key=lambda o: (o["when"], o["rule_id"]))
        warning_total = None
        if len(occurrences) > AGENDA_TOTAL:
            warning_total = (u"Mostrando as primeiras %d execuções previstas; há mais no período." % AGENDA_TOTAL)
            occurrences = occurrences[:AGENDA_TOTAL]
        days = collections.OrderedDict()
        for o in occurrences:
            days.setdefault(o["when"].date(), []).append(o)
        return {"delayed": late, "total_warning": warning_total, "total": len(occurrences),
                "days": [{"label": _day_label(d, now.date()), "items": items} for d, items in days.items()],
                "problems": problems}

    def list(self, ctx, filters, page, size):
        """Pagina de regras dos ambientes autorizados (admin: todos), pronta para a tabela."""
        admin_crud.require_feature(ctx, FEATURE)
        scope = None
        if ctx.get("is_admin") is not True:
            scope = sorted(ctx.get("environments") or ())
            if not scope:
                return {"items": [], "total": 0, "page": 1, "size": size}
        result = self._schedules.list(filters=filters, page=page, size=size,
                                              environment_scope=scope)
        scripts = {}
        logins = {}
        items = []
        for reg in result["items"]:
            sid = reg["script_id"]
            if sid not in scripts:
                try:
                    scripts[sid] = self._catalog.scripts_get(sid)["name"]
                except RepoNotFound:
                    scripts[sid] = u"#%s" % sid
            label, reason = rule_state(reg)
            warning = None
            if reg.get("active") == "Y":
                warning = self._overlap_warning(reg, prefix=u"A próxima vez pode ser pulada: a execução #")
                if not warning:
                    prob = self._check_expansion_problem(reg, self._now())
                    if prob:
                        warning = u"Será pausada: %s." % prob[1]
            items.append({
                "id": reg["id"],
                "name": reg["name"],
                "script": scripts[sid],
                "environment": reg["environment"],
                "kind": TYPE_LABELS.get(reg["recurrence_type"], reg["recurrence_type"]),
                "recurrence": describe_rule(reg),
                "cron_expression": reg.get("cron_expression") if reg["recurrence_type"] == "CRON" else None,
                "next_run_at": format_date(reg.get("next_run_at")) if reg["active"] == "Y" else "-",
                "last_run_at": format_date(reg.get("last_run_at")),
                "last_ticket_id": reg.get("last_ticket_id"),
                "responsible": ui_helpers.visible_actor(self._login(reg["user_id"], logins), ctx),
                "active": reg["active"],
                "state": label,
                "reason": reason,
                "warning": warning,
            })
        return dict(result, items=items)

    def form(self, ctx, schedule_id=None, script_id=None, environment=None, submitted=None,
                   values=None, errors=None):
        """Dados do formulario. Inclusao em etapas (script -> ambiente -> regra) com os filtros do F3.2;
        na edicao, script e ambiente sao fixos (decisao D2 do F5.2).

        enviados/valores/erros (opcionais) reapresentam um POST com erro: campos da regra,
        respostas do questionario e mensagens por campo. Lanca RepoNotFound, AccessDenied
        e OperationDenied (editor sem can_execute).
        """
        admin_crud.require_feature(ctx, FEATURE)
        errors = errors or {}
        submitted = submitted or {}
        data = {"editing": False, "step": 1, "groups": [], "script": None, "environments": [], "form": None,
                 "rule": None, "errors": errors, "single_environment": False}
        current = None
        if schedule_id not in (None, ""):
            current = self._get_visible(ctx, schedule_id)
            script_id, environment = current["script_id"], current["environment"]
            data["editing"] = True
        elif not script_id:
            data["groups"] = self._trigger_service.available_scripts(ctx)
            return data
        try:
            if not data["editing"]:
                script, environments = self._trigger_service.available_environments(ctx, script_id)
                data.update(step=2, script=script, environments=environments,
                            single_environment=len(environments) == 1)
                if not environment and len(environments) == 1:
                    # Um ambiente so: vai direto a recorrencia e ao questionario, como no disparo (CR-017c).
                    environment = environments[0]["name"]
                if not environment:
                    return data
            previous = _parameters(current) if current else {}
            if values is None:
                values = previous
            form = self._trigger_service.prepare_form(ctx, script_id, environment, values, errors)
        except DisparoNegado as exc:
            if data["editing"]:
                self._log.warning("edicao de agendamento negada (login=%s agendamento=%s reason=%s)",
                                  ctx.get("login"), current["id"], exc.reason, extra={"action": FEATURE})
                raise OperationDenied(MSG_NO_PERMISSION)
            raise
        for field in form["fields"]:
            field["kept"] = field["sensitive"] and field["code"] in previous
        data.update(step=3, form=form, rule=self._form_rule(ctx, current, submitted))
        return data

    def _form_rule(self, ctx, current_value, submitted):
        base = current_value or {"recurrence_type": "DAILY", "priority": DEFAULT_PRIORITY}
        pause_warning = None
        if current_value and current_value.get("active") == "N":
            dt_pause = format_date(current_value.get("updated_at"))
            actor_pause = ui_helpers.actor_name(ui_helpers.record_info(current_value, ctx)["updated_by"])
            reason_txt = PAUSE_REASONS.get(current_value.get("pause_reason"), current_value.get("pause_reason")) or u"Desconhecido"
            pause_warning = (
                u"Pausada em %s por %s: %s. "
                u"Edite a regra para corrigir (ao salvar, ela passa a rodar com as suas permissões) e depois retome."
                % (dt_pause, actor_pause, reason_txt)
            )
        rule = {
            "id": base.get("id"),
            "name": base.get("name") or "",
            "recurrence_type": base.get("recurrence_type"),
            "cron_expression": base.get("cron_expression") or "",
            "run_time": base.get("run_time") or "",
            "week_days": [int(d) for d in (base.get("week_days") or "").split(",") if d.isdigit()],
            "month_day": base.get("month_day") or "",
            "start_date": _date_field_value(base.get("start_date")) if current_value else "",
            "end_date": _date_field_value(base.get("end_date")),
            "priority": base.get("priority") or DEFAULT_PRIORITY,
            "version": version(current_value, self._sensitive_codes(current_value["script_id"])) if current_value else "",
            "active": base.get("active", "Y"),
            "state": rule_state(current_value) if current_value else None,
            "responsible": ui_helpers.visible_actor(self._login(current_value["user_id"]), ctx) if current_value else None,
            "other_owner": bool(current_value) and current_value["user_id"] != ctx.get("user_id"),
            "record": ui_helpers.record_info(current_value, ctx) if current_value else None,
            "pause_warning": pause_warning,
        }
        for field in ("name", "recurrence_type", "cron_expression", "run_time", "month_day",
                      "start_date", "end_date", "priority", "version"):
            if field in submitted and submitted[field] is not None:
                rule[field] = submitted[field]
        if "week_days" in submitted:
            text = _weekdays(submitted["week_days"]) or ""
            rule["week_days"] = [int(d) for d in text.split(",") if d.isdigit()]
        return rule

    def preview(self, ctx, data):
        """Proximas PREVIEW_COUNT execucoes e a descricao da regra, sem gravar.

        Retorna {dates: [texto], description: texto | None, errors: {campo: mensagem}}.
        """
        admin_crud.require_feature(ctx, FEATURE)
        errors = collections.OrderedDict()
        now = self._now()
        rule = self._rule(data or {}, now, errors)
        if errors:
            return {"dates": [], "description": None, "errors": dict(errors)}
        try:
            dates = recurrence.next_runs(rule, now, PREVIEW_COUNT, self._horizon)
        except CronError as exc:
            return {"dates": [], "description": None, "errors": {"cron_expression": exc.message}}
        if not dates:
            return {"dates": [], "description": describe_rule(rule), "errors": {GENERAL_FIELD: MSG_NO_NEXT_RUN}}
        return {"dates": [format_preview(d) for d in dates], "description": describe_rule(rule), "errors": {}}

    # ----------------------------------------------------------- gravacao

    def save(self, ctx, ip, data):
        """Inclui (sem 'id') ou altera uma regra. Retorna (id | None, erros por campo).

        date (os dados do formulario): id, version, name, script_id e environment (so na inclusao),
        recurrence_type, cron_expression, run_time, week_days, month_day, start_date, end_date,
        priority e answers ({codigo do parametro: valor}). Lanca RepoNotFound, AccessDenied e OperationDenied
        (editor sem can_execute).
        """
        admin_crud.require_feature(ctx, FEATURE)
        current = None
        if data.get("id") not in (None, ""):
            current = self._get_visible(ctx, data.get("id"))
            script, env = self._authorize(ctx, current["script_id"], current["environment"])
        else:
            script, env = self._authorize(ctx, admin_crud.text(data.get("script_id"), 10),
                                          admin_crud.text(data.get("environment"), 30))
        now = self._now()
        errors = collections.OrderedDict()

        name = admin_crud.text(data.get("name"))
        if name is None:
            errors["name"] = MSG_NAME_REQUIRED
        elif len(name) > NAME_MAX_LENGTH:
            errors["name"] = MSG_NAME_LENGTH
        rule = self._rule(data, now, errors)
        priority = self._priority(ctx, data.get("priority"), errors)

        links = self._links(script["id"])
        previous = _parameters(current) if current else {}
        answers = self._answers(links, data.get("answers"), previous)
        # Compila o snapshot completo so para validar: o daemon recompila a cada desdobro (README §7.5 passo 5).
        _snapshot, resolved, errors_param = params_compiler.compile_snapshot(script, links, answers, now)
        for code, message in errors_param.items():
            errors.setdefault(code, message)

        next_value = None
        if not errors:
            next_value = self._next_run(rule, now, errors)
        if errors:
            self._log.info("validacao do agendamento com erros (login=%s agendamento=%s campos=%s)",
                           ctx.get("login"), current["id"] if current else None, ",".join(sorted(errors)),
                           extra={"action": FEATURE})
            return (current["id"] if current else None), dict(errors)

        record = dict(rule, name=name, script_id=script["id"], environment=env["name"],
                        user_id=ctx["user_id"], priority=priority,
                        params_json=_serialize(resolved), next_run_at=next_value)
        sensitive = set(v["code"] for v in links if v.get("sensitive") == "Y")
        if current is None:
            return self._insert(ctx, ip, record, sensitive)
        if admin_crud.text(data.get("version"), 64) != version(current, self._sensitive_codes(current["script_id"])):
            return current["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        return self._update(ctx, ip, current, record, sensitive)

    def _insert(self, ctx, ip, record, sensitive):
        new = dict(record, active="Y", pause_reason=None)
        detail = admin_crud.insert_detail(self._auditable(new, sensitive), _INSERT_FIELDS)
        try:
            created = self._schedules.insert(new, audit=admin_crud.audit_entry(ctx, ip, "CREATE", detail))
        except RepoViolation as exc:
            self._log.error("agendamento rejeitado pelo repositorio (login=%s constraint=%s)",
                            ctx.get("login"), exc.constraint, extra={"action": "CREATE"})
            return None, {GENERAL_FIELD: admin_crud.MSG_FAILURE}
        self._log.info("agendamento incluido (login=%s agendamento=%s script_id=%s environment=%s tipo=%s)",
                       ctx.get("login"), created["id"], created["script_id"], created["environment"],
                       created["recurrence_type"], extra={"action": "CREATE"})
        return created["id"], {}

    def _update(self, ctx, ip, current_value, record, sensitive):
        after = dict(current_value, **record)
        detail = admin_crud.changes_detail(self._auditable(current_value, sensitive),
                                                self._auditable(after, sensitive, current_value), AUDIT_FIELDS)
        swapped_owner = current_value["user_id"] != record["user_id"]
        if detail is None and not swapped_owner:
            return current_value["id"], {}
        # README §10: a edicao sempre registra o usuario_id anterior e o novo.
        owner = u"user_id: %s (%s)%s%s (%s)" % (
            current_value["user_id"], self._login(current_value["user_id"]), _ARROW,
            record["user_id"], ctx.get("login"))
        detail = admin_crud.free_detail(owner if detail is None else u"%s; %s" % (owner, detail))
        try:
            self._schedules.update(current_value["id"], record,
                                       expected=admin_crud.expected(current_value, _EXPECTED_FIELDS),
                                       audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detail))
        except RepoConflict:
            return current_value["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        except RepoViolation as exc:
            self._log.error("alteracao de agendamento rejeitada pelo repositorio (login=%s agendamento=%s "
                            "constraint=%s)", ctx.get("login"), current_value["id"], exc.constraint,
                            extra={"action": "UPDATE"})
            return current_value["id"], {GENERAL_FIELD: admin_crud.MSG_FAILURE}
        self._log.info("agendamento alterado (login=%s agendamento=%s user_id=%s->%s)",
                       ctx.get("login"), current_value["id"], current_value["user_id"], record["user_id"],
                       extra={"action": "UPDATE"})
        return current_value["id"], {}

    def pause(self, ctx, ip, schedule_id):
        """Pausa manual (pause_reason = 'MANUAL'), otimista sobre next_run (README §7.5 passo 7).

        Audita SCHEDULE_PAUSE. Lanca OperationDenied (ja pausada), RepoConflict, RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        current = self._get_visible(ctx, schedule_id)
        if current["active"] != "Y":
            raise OperationDenied(MSG_ALREADY_PAUSED)
        detail = admin_crud.changes_detail(current, dict(current, active="N", pause_reason="MANUAL"),
                                                ("active", "pause_reason"))
        changed = self._schedules.pause(current["id"], "MANUAL", old_date=current["next_run_at"],
                                             audit=admin_crud.audit_entry(ctx, ip, "SCHEDULE_PAUSE", detail))
        self._log.info("agendamento pausado (login=%s agendamento=%s reason=MANUAL)", ctx.get("login"),
                       current["id"], extra={"action": "SCHEDULE_PAUSE"})
        return changed

    def resume(self, ctx, ip, schedule_id):
        """Retoma a regra: revalida can_execute de quem retoma, recalcula next_run a partir
        de agora, limpa pausa_motivo e reativa. O responsavel (usuario_id) nao muda.

        Audita UPDATE. Lanca OperationDenied (ja ativa, sem permissao ou sem proxima execucao),
        RepoConflict, RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        current = self._get_visible(ctx, schedule_id)
        if current["active"] == "Y":
            raise OperationDenied(MSG_ALREADY_ACTIVE)
        now = self._now()
        problem = self._check_expansion_problem(current, now)
        if problem is not None:
            _code, cause = problem
            raise OperationDenied(u"%s. %s" % (cause, MSG_RESUME_GUIDANCE))
        self._authorize(ctx, current["script_id"], current["environment"])
        try:
            next_value = recurrence.next_run(current, now, self._horizon)
        except CronError as exc:
            raise OperationDenied(u"%s: %s" % (PAUSE_REASONS["INVALID_CRON"], exc.message))
        if next_value is None:
            raise OperationDenied(MSG_RESUME_NO_NEXT_RUN)
        before = {"active": current["active"], "pause_reason": current.get("pause_reason"),
                 "next_run_at": format_date(current.get("next_run_at"))}
        after = {"active": "Y", "pause_reason": None, "next_run_at": format_date(next_value)}
        detail = admin_crud.changes_detail(before, after, ("active", "pause_reason", "next_run_at"))
        changed = self._schedules.resume(
            current["id"], next_value, expected=admin_crud.expected(current, ("active", "pause_reason", "next_run_at")),
            audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detail))
        self._log.info("agendamento retomado (login=%s agendamento=%s proxima=%s)", ctx.get("login"),
                       current["id"], format_date(next_value), extra={"action": "UPDATE"})
        return changed


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from sss.config import app_context
            from sss.persistence import repo_factory
            from sss.config import sss_logging
            import ticket_service
            factory = repo_factory
            cfg = app_context.require_config()
            tickets = factory.get("tickets")
            _default = SchedulesService(
                schedules=factory.get("schedules"),
                catalog=factory.get("catalog"),
                users=factory.get("users"),
                trigger_service=ticket_service._service(),
                clock=tickets.now,
                horizon_days=cfg.agent.cron_horizon_days,
                log=sss_logging.get_logger("sss_web", cfg),
                tickets=tickets,
                rbac_repo=factory.get("rbac"),
                misfire_policy=cfg.agent.misfire_policy,
                misfire_tolerance_s=cfg.agent.misfire_tolerance_s,
            )
        return _default


def list_page(ctx, filters, page, size):
    """Pagina de regras (servico padrao)."""
    return _service().list(ctx, filters, page, size)


def impact_warning(rules, total_active):
    """Frase do aviso depois de salvar (CR-018a): regras que vao ser pausadas, ou None."""
    if not rules:
        return None
    names = u"; ".join(u"%s (%s)" % (r["name"], r["reason"].lower()) for r in rules[:_IMPACT_NAMES])
    more = u" e outras %d" % (len(rules) - _IMPACT_NAMES) if len(rules) > _IMPACT_NAMES else u""
    return (u"Atenção: %d de %d regra(s) de agendamento ativa(s) vão ser pausadas no próximo horário: %s%s. "
            u"Corrija as regras ou desfaça a mudança." % (len(rules), total_active, names, more))


def filter_environments(ctx):
    """Ambientes do filtro da lista de regras (servico padrao)."""
    return _service().filter_environments(ctx)


def active_rules(script_ids):
    """Regras ativas dos scripts (servico padrao)."""
    return _service().active_rules(script_ids)


def rules_at_risk(script_ids):
    """Regras ativas que o proximo desdobro vai pausar (servico padrao)."""
    return _service().rules_at_risk(script_ids)


def agenda(ctx):
    """Agenda dos proximos 7 dias (servico padrao)."""
    return _service().agenda(ctx)


def form(ctx, schedule_id=None, script_id=None, environment=None, submitted=None, values=None, errors=None):
    """Dados do formulario de regra (servico padrao)."""
    return _service().form(ctx, schedule_id, script_id, environment, submitted, values, errors)


def preview(ctx, data):
    """Proximas execucoes e descricao da regra (servico padrao)."""
    return _service().preview(ctx, data)


def save(ctx, ip, data):
    """Inclusao ou alteracao de regra (servico padrao)."""
    return _service().save(ctx, ip, data)


def pause(ctx, ip, schedule_id):
    """Pausa manual (servico padrao)."""
    return _service().pause(ctx, ip, schedule_id)


def resume(ctx, ip, schedule_id):
    """Retomada (servico padrao)."""
    return _service().resume(ctx, ip, schedule_id)
