# -*- coding: utf-8 -*-
"""Disparo manual de script e consulta de tickets (README §4.3.C, §5, §6).

O servidor e a autoridade: script, ambiente e homologacao sao sempre recarregados do
repositorio e reautorizados com rbac.can_execute. Valores de parametros nunca vao para
o log; so codigos de campo.
"""
import collections
import datetime
import json
import re
import shlex
import threading

import params_compiler
import path_guard
import rbac
import ui_helpers
from repo_errors import RepoError, RepoNotFound

GENERAL_FIELD = params_compiler.GENERAL_KEY
PRIORITY_FIELD = "priority"
SCHEDULED_AT_FIELD = "scheduled_at"
DEFAULT_PRIORITY = 2
PRODUCTION_ENVIRONMENT = "PRODUCAO"

MSG_SCRIPT_UNAVAILABLE = (u"O script não está disponível para execução neste servidor. "
                           u"Contate o administrador.")
MSG_CREATE_FAILED = u"Não foi possível criar o ticket. Tente novamente em instantes."

HISTORY_DAYS = 30
HISTORY_LIMIT = 5000
MSG_LAST_SENSITIVE = u"Por segurança, digite de novo."
MSG_LAST_CHANGED = u"Esta resposta mudou desde a última vez; preencha de novo."
PRIORITY_LABELS = {
    1: u"1 — Urgente (exclusiva de administradores)",
    2: u"2 — Normal (padrão)",
    3: u"3 — Baixa",
    4: u"4 — Mínima",
}

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_ENVIRONMENT = re.compile(r"[A-Z0-9_]{1,30}")
_SCHEDULED_AT_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S")
_ENVIRONMENTS_MAX = 1000
_SCRIPTS_MAX = 1000
_CHILDREN_MAX = 100

STATUS_TICKET = ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED")
TERMINAL_STATUSES = ("SUCCESS", "FAILED", "CANCELLED")
CANCELLABLE_STATUSES = ("PENDING", "RUNNING")
SOURCES = (("manual", u"Manual"), ("agendamento", u"Agendamento"))
FILTERS = ("status", "environment", "script", "requested_by", "created_from", "created_to", "source")

MSG_CANCEL = {
    "TERMINAL": u"O ticket já estava encerrado.",
    "CANCELADO": u"Ticket cancelado.",
    "SINALIZADO": u"Cancelamento solicitado ao agente; ele vai encerrar a execução.",
    "JA_SINALIZADO": u"O cancelamento já havia sido solicitado.",
}

_RE_LOGIN = re.compile(r"[a-z0-9._-]{3,30}")
_DAY_FORMAT = "%Y-%m-%d"

# Teto por chamada do visualizador e tamanho do bloco do download (README §8.10).
LOG_MAX_CHARS = 65536
# Fatia do download da saida (CR-012): 256 KiB por leitura do BLOB, nunca o zip inteiro em memoria.
OUTPUT_SLICE_BYTES = 256 * 1024
_RE_OFFSET = re.compile(r"[0-9]{1,10}")
DOWNLOAD_INTERRUPTED_MARKER = u"\n[SSS] download interrompido por falha na leitura do log\n"


class AccessDenied(Exception):
    """Execucao nao autorizada; o motivo (rbac.Reason) e destinado apenas ao log."""

    def __init__(self, reason):
        Exception.__init__(self, reason)
        self.reason = reason


class RerunError(Exception):
    """Reexecucao nao gravada (recompilacao invalida ou falha de persistencia).

    erros: dict codigo_campo -> mensagem, ja seguro para exibicao (sem valores).
    """

    def __init__(self, ticket_id, errors):
        Exception.__init__(self, ",".join(sorted(errors)))
        self.ticket_id = ticket_id
        self.errors = errors


class InvalidOffset(ValueError):
    """Offset de leitura do log ausente, negativo ou nao inteiro."""


def _offset(value):
    value = _last(value)
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 10 ** 10:
        return value
    if isinstance(value, str) and _RE_OFFSET.fullmatch(value):
        return int(value)
    raise InvalidOffset("offset invalido")


def _id(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and _RE_ID.fullmatch(value):
        number = int(value)
        return number if number > 0 else None
    return None


def _last(value):
    # Campo repetido no POST (hidden + checkbox): vale o ultimo enviado.
    if isinstance(value, (list, tuple)):
        return value[-1] if value else None
    return value


def _options(parameter):
    try:
        options = json.loads(parameter.get("options_json") or "", object_pairs_hook=collections.OrderedDict)
    except ValueError:
        return []
    if not isinstance(options, dict):
        return []
    return [(str(k), str(v)) for k, v in options.items()]


def _sorted_items(links):
    return sorted(links, key=lambda v: int(v["sort_order"]))


def _answer_text(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    return value


def _typical_duration(median):
    """Duracao tipica do historico: 'cerca de 4 minutos'; abaixo de 1 minuto, so 'menos de 1 minuto'."""
    if median is None:
        return u"-"
    text = ui_helpers.simple_time(median)
    return text if text.startswith(u"menos de") else u"cerca de %s" % text


def _day(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.datetime.strptime(value.strip(), _DAY_FORMAT)
    except ValueError:
        return None


def normalize_filters(input_value):
    """Allowlist de chaves e valores dos filtros da lista de tickets (querystring).

    Retorna OrderedDict apenas com os filtros validos, na forma de exibicao/URL: status
    (lista na ordem canonica), environment, script (int), requested_by, created_from/created_to
    ('YYYY-MM-DD') e source. Chaves desconhecidas e valores invalidos sao descartados.
    """
    input_value = input_value or {}
    cleaned = collections.OrderedDict()
    status = input_value.get("status")
    if isinstance(status, str):
        status = [status]
    if isinstance(status, (list, tuple)):
        marked = [st for st in STATUS_TICKET if st in status]
        if marked:
            cleaned["status"] = marked
    environment = _last(input_value.get("environment"))
    if isinstance(environment, str) and _RE_ENVIRONMENT.fullmatch(environment):
        cleaned["environment"] = environment
    script = _id(_last(input_value.get("script")))
    if script is not None:
        cleaned["script"] = script
    requester = _last(input_value.get("requested_by"))
    if isinstance(requester, str):
        requester = requester.strip().lower()
        if _RE_LOGIN.fullmatch(requester):
            cleaned["requested_by"] = requester
    for key in ("created_from", "created_to"):
        day = _day(_last(input_value.get(key)))
        if day is not None:
            cleaned[key] = day.strftime(_DAY_FORMAT)
    source = _last(input_value.get("source"))
    if source in dict(SOURCES):
        cleaned["source"] = source
    return cleaned


def _repo_filters(cleaned):
    """Traduz filtros normalizados para as chaves do contrato; periodo vira [inicio, fim + 1 dia)."""
    repo = {}
    if "status" in cleaned:
        repo["status"] = list(cleaned["status"])
    if "environment" in cleaned:
        repo["environment"] = cleaned["environment"]
    if "script" in cleaned:
        repo["script_id"] = cleaned["script"]
    if "requested_by" in cleaned:
        repo["requested_by"] = cleaned["requested_by"]
    if "source" in cleaned:
        repo["source"] = cleaned["source"]
    if "created_from" in cleaned:
        repo["created_from"] = _day(cleaned["created_from"])
    if "created_to" in cleaned:
        repo["created_to"] = _day(cleaned["created_to"]) + datetime.timedelta(days=1)
    return repo


def _duration(ticket, now):
    end = ticket.get("finished_at")
    if end is None and ticket.get("status") == "RUNNING":
        end = now
    return ui_helpers.format_duration(ticket.get("started_at"), end)


def _snapshot(ticket):
    try:
        snap = json.loads(ticket.get("submitted_params") or "")
    except (TypeError, ValueError):
        return None
    return snap if isinstance(snap, dict) else None


def _display_argv(snap):
    # Snapshot ilegivel ou de versao anterior ao CR-005 (v1 a v3) nao tem argv exibivel.
    if snap is None or snap.get("version") != params_compiler.SNAPSHOT_VERSION:
        return None
    try:
        return params_compiler.display_argv(snap)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


class TicketService(object):
    """Servico de disparo com dependencias injetadas (repositorios, arvore de scripts e log)."""

    def __init__(self, catalog, tickets, log):
        self._catalog = catalog
        self._tickets = tickets
        self._log = log

    # ------------------------------------------------------------ autorizacao

    def _deny(self, ctx, reason, script_id, environment):
        self._log.warning("disparo negado (login=%s script_id=%r environment=%r reason=%s)",
                          (ctx or {}).get("login"), script_id, environment, reason,
                          extra={"action": "RBAC"})
        raise AccessDenied(reason)

    def _script(self, ctx, script_id):
        sid = _id(script_id)
        if sid is None:
            self._deny(ctx, rbac.Reason.INVALID_DATA, script_id, None)
        try:
            return self._catalog.scripts_get(sid)
        except RepoNotFound:
            self._deny(ctx, rbac.Reason.INVALID_DATA, script_id, None)

    def _environment_by_name(self, name):
        if not isinstance(name, str) or not _RE_ENVIRONMENT.fullmatch(name):
            return None
        page = self._catalog.environments_list(filters={"name": name}, page=1, size=_ENVIRONMENTS_MAX)
        for env in page["items"]:
            if env.get("name") == name:
                return env
        return None

    def _authorize(self, ctx, script_id, environment):
        """Recarrega script, ambiente e homologacao do repositorio e aplica can_execute."""
        script = self._script(ctx, script_id)
        env = self._environment_by_name(environment)
        if env is None:
            self._deny(ctx, rbac.Reason.INVALID_DATA, script_id, environment)
        homologations = self._catalog.homologation_get(script["id"])
        ok, reason = rbac.can_execute(ctx, script, env, homologations)
        if not ok:
            self._deny(ctx, reason, script["id"], env["name"])
        return script, env

    def authorize(self, ctx, script_id, environment):
        """(script, ambiente) recarregados do repositorio e autorizados por can_execute; lanca AccessDenied."""
        return self._authorize(ctx, script_id, environment)

    def _executable_environments(self, ctx, script):
        environments = []
        for aid in self._catalog.homologation_get(script["id"]):
            try:
                env = self._catalog.environments_get(aid)
            except RepoNotFound:
                continue
            ok, _reason = rbac.can_execute(ctx, script, env, (aid,))
            if ok:
                environments.append(env)
        environments.sort(key=lambda a: a["name"])
        return environments

    # ----------------------------------------------------------- formulario

    def available_scripts(self, ctx):
        """Scripts executaveis pelo usuario em ao menos um ambiente, agrupados por grupo/categoria.

        Retorna lista ordenada de {script_group, category, scripts: [{id, name, description, stage}]}.
        """
        if not rbac.has_feature(ctx, "EXEC_SCRIPT"):
            return []
        groups = collections.OrderedDict()
        candidates = sorted(self._catalog.executable_scripts(ctx),
                            key=lambda s: ((s.get("script_group") or ""), (s.get("category") or ""), s["name"]))
        for script in candidates:
            if not self._executable_environments(ctx, script):
                continue
            key = (script.get("script_group") or u"Sem grupo", script.get("category") or u"Sem categoria")
            groups.setdefault(key, []).append({
                "id": script["id"],
                "name": script["name"],
                "description": script.get("description") or "",
                "stage": script.get("stage") or "",
            })
        return [{"script_group": g, "category": c, "scripts": items} for (g, c), items in groups.items()]

    def available_environments(self, ctx, script_id):
        """Script e ambientes homologados E autorizados para ele; lanca AccessDenied se nenhum."""
        script = self._script(ctx, script_id)
        environments = self._executable_environments(ctx, script)
        if not environments:
            self._deny(ctx, rbac.Reason.NO_ENVIRONMENT, script["id"], None)
        return script, [{"id": a["id"], "name": a["name"], "description": a.get("description") or ""}
                        for a in environments]

    def _links(self, script_id):
        return [v for v in self._catalog.script_params_get(script_id) if v.get("active") == "Y"]

    def _display_default(self, link):
        for source in (link.get("default_value_override"), link.get("default_value")):
            if source is None or (isinstance(source, str) and source.strip() == ""):
                continue
            try:
                return params_compiler.validate_value(link, source)
            except params_compiler.ParamError:
                return None
        return None

    def _example(self, link):
        """Texto de ajuda gerado pelo tipo (README §5.4, "Clareza no disparo"); sem coluna nova."""
        kind = link.get("component_type")
        if kind == "DATE":
            return u"Use o formato AAAA-MM-DD, por exemplo %s." % self._tickets.now().strftime("%Y-%m-%d")
        if kind == "NUMBER":
            return u"Use só números, com ponto para decimais, por exemplo 10 ou 2.5."
        if kind == "SELECT":
            return u"Escolha uma das opções da lista."
        if kind == "CHECKBOX":
            return u"Marque para sim; deixe desmarcado para não."
        if kind == "TEXT" and link.get("validation_regex"):
            return u"Siga o formato pedido pelo cadastro."
        return None

    def prepare_form(self, ctx, script_id, environment, values=None, errors=None, warnings=None):
        """Vinculos ordenados com padroes resolvidos para exibicao; valida can_execute.

        valores/erros (opcionais) reapresentam um POST com erro; avisos (opcional) sao notas por campo
        (ex.: resposta da ultima execucao que mudou). Valores e padroes sensiveis nunca sao devolvidos.
        """
        script, env = self._authorize(ctx, script_id, environment)
        values = values or {}
        errors = errors or {}
        warnings = warnings or {}
        fields = []
        for v in _sorted_items(self._links(script["id"])):
            code = v["code"]
            sensitive = v.get("sensitive") == "Y"
            kind = v.get("component_type")
            options = _options(v) if kind == "SELECT" else []
            default_real = self._display_default(v)
            default = None if sensitive else default_real
            sent = _last(values.get(code))
            if kind == "CHECKBOX":
                if code in values:
                    marked = isinstance(sent, str) and sent.strip().lower() in ("true", "1")
                else:
                    marked = default is True
                default_text = None if default is None else (u"Marcado" if default else u"Desmarcado")
                value = None
            else:
                marked = False
                default_text = dict(options).get(default, default) if default is not None else None
                value = None if sensitive or not isinstance(sent, str) else sent
            fields.append({
                "code": code,
                "name": "p_" + code,
                "label": v.get("label") or code,
                "description": v.get("description") or "",
                "kind": kind,
                "required": v.get("required") == "Y",
                "sensitive": sensitive,
                "options": options,
                "default": default,
                "has_default": default_real is not None,
                "default_text": default_text,
                "value": value,
                "checked": marked,
                "error": errors.get(code),
                "example": self._example(v),
                "warning": warnings.get(code),
            })
        priorities = [(p, PRIORITY_LABELS[p]) for p in rbac.PRIORITIES if rbac.allowed_priority(ctx, p)]
        return {
            "script": {"id": script["id"], "name": script["name"], "description": script.get("description") or "",
                       "param_type": script["param_type"]},
            "environment": {"id": env["id"], "name": env["name"], "description": env.get("description") or "",
                         "production": env["name"] == PRODUCTION_ENVIRONMENT},
            "fields": fields,
            "priorities": priorities,
        }

    # ------------------------------------------------------------- validacao

    def _priority(self, ctx, value, errors):
        value = _last(value)
        if value is None or value == "":
            priority = DEFAULT_PRIORITY
        else:
            priority = _id(value.strip() if isinstance(value, str) else value)
        if priority is not None and rbac.allowed_priority(ctx, priority):
            return priority
        if priority == rbac.ADMIN_PRIORITY:
            errors[PRIORITY_FIELD] = u"A prioridade 1 é exclusiva de administradores."
        else:
            errors[PRIORITY_FIELD] = u"Selecione uma prioridade entre 1 e 4."
        return None

    def _scheduled_at(self, value, now, errors):
        value = _last(value)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return None
        date = None
        if isinstance(value, str):
            for format_value in _SCHEDULED_AT_FORMATS:
                try:
                    date = datetime.datetime.strptime(value.strip(), format_value)
                    break
                except ValueError:
                    continue
        if date is None:
            errors[SCHEDULED_AT_FIELD] = u"Informe uma data e hora válidas para o agendamento."
            return None
        # README §5.4 passo 4: >= SYSDATE exato, sem tolerancia de minuto.
        if date < now:
            errors[SCHEDULED_AT_FIELD] = (u"O horário escolhido já passou. "
                                        u"Escolha um horário futuro, ou deixe em branco para rodar agora.")
            return None
        limit = now + datetime.timedelta(days=366)
        if date > limit:
            errors[SCHEDULED_AT_FIELD] = u"Escolha uma data até %s." % limit.strftime("%d/%m/%Y")
            return None
        return date.replace(microsecond=0)

    def _compile(self, ctx, script, env, answers, now, errors):
        """Confere o formato do caminho e compila o snapshot v4, acumulando erros por campo."""
        links = self._links(script["id"])
        codes = set(v["code"] for v in links)
        if not isinstance(answers, dict):
            answers = {}
        answers = dict((k, _last(v)) for k, v in answers.items() if k in codes)

        # CR-011 (README §5.4, §8.5): o web confere so o formato do caminho e as pastas do sistema; o arquivo
        # e conferido pelo agente, no servidor onde ele roda (README §8.4).
        try:
            path_guard.validate_registration(script["path_file"])
            path_guard.check_forbidden_dirs(script["path_file"])
        except path_guard.PathGuardError as e:
            self._log.warning("caminho do script recusado (login=%s script_id=%s code=%s)",
                              ctx["login"], script["id"], e.code, extra={"action": "TICKET_CREATE"})
            errors[GENERAL_FIELD] = MSG_SCRIPT_UNAVAILABLE

        snapshot, resolved, errors_param = params_compiler.compile_snapshot(
            script, links, answers, now)
        for code, message in errors_param.items():
            errors.setdefault(code, message)
        if errors:
            self._log.info("validacao do disparo com erros (login=%s script_id=%s ambiente=%s campos=%s)",
                           ctx["login"], script["id"], env["name"], ",".join(sorted(errors)),
                           extra={"action": "TICKET_CREATE"})
            return None, None, links
        return snapshot, resolved, links

    # --------------------------------------------------------------- acoes

    def preview(self, ctx, script_id, environment, answers):
        """Compila sem gravar e devolve (argv_exibicao | None, erros_por_campo); sensiveis mascarados."""
        script, env = self._authorize(ctx, script_id, environment)
        errors = collections.OrderedDict()
        snapshot, _resolved, _links = self._compile(ctx, script, env, answers,
                                                          self._tickets.now(), errors)
        if snapshot is None:
            return None, dict(errors)
        return params_compiler.display_argv(json.loads(snapshot)), {}

    def trigger_summary(self, ctx, script_id, environment, answers, priority=None, scheduled_at=None):
        """Resumo em frase do modal de confirmacao (README §5.4), montado pelo servidor; nao grava nada.

        Retorna {argv, errors, summary} com summary = {script, environment, when, priority, answers:
        [{label, value}], phrase}. Sensiveis aparecem como '****'; vazios como '(sem resposta)'.
        """
        script, env = self._authorize(ctx, script_id, environment)
        now = self._tickets.now()
        errors = collections.OrderedDict()
        prio = self._priority(ctx, priority, errors)
        sched = self._scheduled_at(scheduled_at, now, errors)
        snapshot, resolved, links = self._compile(ctx, script, env, answers, now, errors)
        if snapshot is None or errors:
            return {"argv": None, "errors": dict(errors), "summary": None}
        rows = []
        for v in _sorted_items(links):
            value = resolved.get(v["code"])
            if v.get("sensitive") == "Y" and value not in (None, ""):
                text = params_compiler.MASK
            elif value is None or value == "":
                text = u"(sem resposta)"
            elif isinstance(value, bool):
                text = u"sim" if value else u"não"
            else:
                text = dict(_options(v)).get(value, value) if v.get("component_type") == "SELECT" else value
            rows.append({"label": v.get("label") or v["code"], "value": text})
        when = u"agora" if sched is None else u"em %s às %s" % (sched.strftime("%d/%m/%Y"), sched.strftime("%H:%M"))
        phrase = u"Vamos rodar %s no ambiente %s %s, com prioridade %d." % (script["name"], env["name"], when, prio)
        if rows:
            phrase += u" Respostas: " + u"; ".join(u"%s = %s" % (l["label"], l["value"]) for l in rows) + u"."
        return {"argv": params_compiler.display_argv(json.loads(snapshot)),
                "errors": {},
                "summary": {"script": script["name"], "environment": env["name"], "when": when, "priority": prio,
                           "answers": rows, "phrase": phrase}}

    def _last_ticket(self, ctx, script_id, environment):
        sid = _id(script_id)
        if sid is None or not environment:
            return None
        items = self._tickets.list(filters={"requested_by": ctx.get("login"), "script_id": sid,
                                              "environment": environment}, page=1, size=1)["items"]
        return items[0] if items else None

    def has_last_run(self, ctx, script_id, environment):
        """True se o proprio usuario ja pediu este script neste ambiente (botao do README §5.4)."""
        return self._last_ticket(ctx, script_id, environment) is not None

    def last_answers(self, ctx, script_id, environment):
        """(valores, avisos) da ultima execucao propria: so nao sensiveis e ainda validas (README §5.4).

        Nada e gravado. Sensivel fica vazio com o aviso de digitar de novo; resposta que nao vale mais
        no catalogo atual fica vazia com o aviso de que mudou.
        """
        script, _env = self._authorize(ctx, script_id, environment)
        ticket = self._last_ticket(ctx, script["id"], environment)
        values, warnings_value = {}, {}
        if ticket is None:
            return values, warnings_value
        by_id = dict((r["parameter_id"], r.get("answer_value")) for r in self._tickets.answers(ticket["id"]))
        for v in self._links(script["id"]):
            if v["parameter_id"] not in by_id:
                continue
            if v.get("sensitive") == "Y":
                warnings_value[v["code"]] = MSG_LAST_SENSITIVE
                continue
            raw = by_id[v["parameter_id"]]
            try:
                params_compiler.validate_value(v, raw)
            except params_compiler.ParamError:
                warnings_value[v["code"]] = MSG_LAST_CHANGED
                continue
            values[v["code"]] = raw
        return values, warnings_value

    def create_ticket(self, ctx, ip, script_id, environment, answers, priority, scheduled_at,
                     rerun_of=None):
        """Cria o ticket (README §5.4). Retorna (ticket_id | None, erros_por_campo).

        rerun_of (opcional) vincula o novo ticket ao original (README §5.5), exigindo
        as mesmas regras de reexecutar e o mesmo script/environment. Lanca AccessDenied quando
        can_execute nega. A auditoria e gravada pelo repositorio na mesma transacao do INSERT.
        """
        parent_id = None
        if rerun_of not in (None, ""):
            original = self._rerunnable_ticket(ctx, rerun_of)
            if str(original["script_id"]) != str(script_id) or original["environment"] != environment:
                self._deny(ctx, "REEXECUCAO_DIVERGENTE", script_id, environment)
            parent_id = original["id"]
        script, env = self._authorize(ctx, script_id, environment)
        now = self._tickets.now()
        errors = collections.OrderedDict()
        prio = self._priority(ctx, priority, errors)
        sched = self._scheduled_at(scheduled_at, now, errors)
        snapshot, resolved, links = self._compile(ctx, script, env, answers, now, errors)
        if errors:
            return None, dict(errors)
        return self._save(ctx, ip, script, env, prio, sched, snapshot, resolved, links, parent_id)

    def _save(self, ctx, ip, script, env, prio, sched, snapshot, resolved, links, parent_id):
        action = "TICKET_CREATE" if parent_id is None else "TICKET_RERUN"
        ticket = {
            "script_id": script["id"],
            "environment": env["name"],
            "requested_by": ctx["login"],
            "source_ip": ip,
            "status": "PENDING",
            "priority": prio,
            "submitted_params": snapshot,
            "scheduled_at": sched,
            "parent_ticket_id": parent_id,
        }
        rows = []
        for v in _sorted_items(links):
            value = resolved.get(v["code"])
            if value is not None:
                rows.append({"parameter_id": v["parameter_id"], "answer_value": _answer_text(value)})
        try:
            ticket_id = self._tickets.create(ticket, rows)
        except RepoError:
            self._log.exception("falha ao gravar ticket (login=%s script_id=%s environment=%s pai=%s)",
                                ctx["login"], script["id"], env["name"], parent_id, extra={"action": action})
            return None, {GENERAL_FIELD: MSG_CREATE_FAILED}
        self._log.info("ticket criado (ticket=%s login=%s script_id=%s environment=%s priority=%s pai=%s ip=%s)",
                       ticket_id, ctx["login"], script["id"], env["name"], prio, parent_id, ip,
                       extra={"action": action})
        return ticket_id, {}

    # ------------------------------------------------------------ consulta

    def can_query(self, ctx):
        """Acesso a lista de tickets: VIEW_LOGS (escopo de ambientes) ou EXEC_SCRIPT (proprios)."""
        return rbac.has_feature(ctx, "VIEW_LOGS") or rbac.has_feature(ctx, "EXEC_SCRIPT")

    def _is_own(self, ctx, ticket):
        return rbac.has_feature(ctx, "EXEC_SCRIPT") and ticket.get("requested_by") == ctx.get("login")

    def _can_view(self, ctx, ticket):
        return self._is_own(ctx, ticket) or rbac.can_view_ticket(ctx, ticket)

    def is_visible(self, ctx, ticket_id):
        """True se o ticket existe e pode ser visto (destino do redirecionamento apos cancelar)."""
        tid = _id(ticket_id)
        try:
            return tid is not None and self._can_view(ctx, self._tickets.get(tid))
        except RepoNotFound:
            return False

    def _visible_ticket(self, ctx, ticket_id, action):
        """Ticket existente e visivel; fora do escopo e tratado como inexistente (404, nao 403)."""
        tid = _id(ticket_id)
        if tid is None:
            raise RepoNotFound("ticket invalido")
        ticket = self._tickets.get(tid)
        if not self._can_view(ctx, ticket):
            self._log.warning("ticket fora do escopo (login=%s ticket=%s environment=%s)",
                              ctx.get("login"), tid, ticket.get("environment"), extra={"action": action})
            raise RepoNotFound("ticket fora do escopo")
        return ticket

    def _script_names(self):
        page = self._catalog.scripts_list(page=1, size=_SCRIPTS_MAX)
        return dict((s["id"], s["name"]) for s in page["items"])

    def filter_options(self, ctx):
        """Opcoes dos selects de filtro: ambientes visiveis ao perfil e scripts do catalogo."""
        if rbac.has_feature(ctx, "VIEW_LOGS") and ctx.get("is_admin") is True:
            page = self._catalog.environments_list(page=1, size=_ENVIRONMENTS_MAX)
            environments = sorted(a["name"] for a in page["items"])
        else:
            environments = sorted(ctx.get("environments") or ())
        scripts = sorted(self._script_names().items(), key=lambda pair: (pair[1], pair[0]))
        return {"environments": environments, "scripts": scripts, "status": list(STATUS_TICKET),
                "sources": list(SOURCES)}

    def _query_scope(self, ctx, repo_filters):
        """(visivel, environment_scope) da consulta; sem VIEW_LOGS fixa o solicitante em repo_filters_dict.

        Com VIEW_LOGS: ambientes autorizados (admin: todos, escopo None). Sem VIEW_LOGS: apenas
        os tickets do proprio solicitante. visivel False: nada a consultar.
        """
        if rbac.has_feature(ctx, "VIEW_LOGS"):
            if ctx.get("is_admin") is True:
                return True, None
            scope = sorted(ctx.get("environments") or ())
            return bool(scope), scope
        if repo_filters.get("requested_by", ctx["login"]) != ctx["login"]:
            return False, None
        repo_filters["requested_by"] = ctx["login"]
        return True, None

    def _runs_scope(self, ctx):
        """(environment_scope, solicitante) da ultima execucao/historico: o mesmo da lista (README §5.8)."""
        if rbac.has_feature(ctx, "VIEW_LOGS"):
            return (None if ctx.get("is_admin") is True else sorted(ctx.get("environments") or ())), None
        return None, ctx["login"]

    def routine_catalog(self, ctx):
        """Rotinas disponiveis (README §5.8, CR-004 T2): cartoes por grupo dos scripts que o usuario pode rodar.

        Cada cartao: id, name, description, script_group, category, questions [{label, required}],
        environments (nomes) e last_run (None ou {id, state, css_class, icon, when}). So leitura.
        """
        groups = self.available_scripts(ctx)
        ids = [s["id"] for g in groups for s in g["scripts"]]
        scope, requester = self._runs_scope(ctx)
        recent_runs = self._tickets.last_runs(ids, scope, requester) if ids else {}
        now = self._tickets.now()
        result = []
        for g in groups:
            cards = []
            for s in g["scripts"]:
                _script, environments = self.available_environments(ctx, s["id"])
                questions = [{"label": v.get("label") or v["code"], "required": v.get("required") == "Y"}
                             for v in _sorted_items(self._links(s["id"]))]
                last = None
                if s["id"] in recent_runs:
                    u = recent_runs[s["id"]]
                    info = ui_helpers.status_info(u["status"])
                    last = {"id": u["id"], "state": info["label"], "css_class": info["css_class"],
                              "icon": info["icon"],
                              "when": u"há %s" % ui_helpers.simple_time((now - u["created_at"]).total_seconds())}
                cards.append(dict(s, script_group=g["script_group"], category=g["category"], questions=questions,
                                    environments=[a["name"] for a in environments], last_run=last))
            result.append({"script_group": g["script_group"], "category": g["category"], "cards": cards})
        return result

    def script_history(self, ctx, script_id):
        """Historico do script nos ultimos 30 dias (README §5.8, CR-004 T4). So leitura.

        Abre so para um script das Rotinas disponiveis do usuario; senao RepoNotFound (404).
        """
        sid = _id(script_id)
        available = dict((s["id"], s) for g in self.available_scripts(ctx) for s in g["scripts"])
        if sid is None or sid not in available:
            raise RepoNotFound("script fora das rotinas disponiveis")
        now = self._tickets.now()
        since = now - datetime.timedelta(days=HISTORY_DAYS)
        scope, requester = self._runs_scope(ctx)
        items = self._tickets.script_history(sid, since, scope, requester, HISTORY_LIMIT)
        groups = {"SUCCESS": "succeeded", "FAILED": "error", "CANCELLED": "cancelled"}
        count = dict((c, 0) for c, _r in ui_helpers.HISTORY_SERIES)
        days = collections.OrderedDict()
        for i in range(HISTORY_DAYS - 1, -1, -1):
            day = (now - datetime.timedelta(days=i)).date()
            days[day] = dict((c, 0) for c, _r in ui_helpers.HISTORY_SERIES)
        durations, reasons = [], collections.Counter()
        for t in items:
            key = groups.get(t["status"], "in_progress")
            count[key] += 1
            if t["created_at"].date() in days:
                days[t["created_at"].date()][key] += 1
            if t["status"] == "FAILED":
                reasons[t.get("status_reason") or "-"] += 1
            if key != "in_progress" and t.get("started_at") and t.get("finished_at"):
                durations.append((t["finished_at"] - t["started_at"]).total_seconds())
        finished = count["succeeded"] + count["error"] + count["cancelled"]
        rate = int(round(100.0 * count["succeeded"] / finished)) if finished else None
        durations.sort()
        median = None
        if durations:
            middle = len(durations) // 2
            median = durations[middle] if len(durations) % 2 else (durations[middle - 1] + durations[middle]) / 2.0
        series = [dict(v, label=d.strftime("%d/%m")) for d, v in days.items()]
        return {
            "script": {"id": sid, "name": available[sid]["name"]},
            "total": len(items),
            "counts": count,
            "rate": rate,
            "rate_phrase": (u"De cada 10 vezes, %d deram certo." % int(round(rate / 10.0))) if rate is not None
            else u"Ainda não há execuções terminadas no período.",
            "typical_duration": _typical_duration(median),
            "max_duration": ui_helpers.simple_time(durations[-1]) if durations else u"-",
            "reasons": [{"reason": m, "name": ui_helpers.REASON_NAMES.get(m, m), "quantity": q}
                        for m, q in sorted(reasons.items(), key=lambda x: (-x[1], x[0]))],
            "days": series,
            "chart": ui_helpers.stacked_bars(series),
            "limit_warning": (u"Mostrando os %d pedidos mais recentes." % HISTORY_LIMIT)
            if len(items) >= HISTORY_LIMIT else None,
            "list_filter": {"script": sid, "created_from": since.strftime("%Y-%m-%d")},
        }

    def home_summary(self, ctx, hours=24, latest=5):
        """Cartoes do painel inicial no escopo da lista de tickets; None sem acesso a consulta.

        Retorna {"counts": [(status, quantidade)], "since": datetime, "mine": [itens da lista]}:
        quantidade por status dos tickets criados nas ultimas `horas` e os `ultimos` tickets do
        proprio usuario.
        """
        if not self.can_query(ctx):
            return None
        now = self._tickets.now()
        since = now - datetime.timedelta(hours=hours)
        count = []
        for status in STATUS_TICKET:
            repo_filters = {"status": [status], "created_from": since}
            visible, scope = self._query_scope(ctx, repo_filters)
            total = 0
            if visible:
                total = self._tickets.list(filters=repo_filters, page=1, size=1,
                                             environment_scope=scope)["total"]
            count.append((status, total))
        mine = self.list(ctx, {"requested_by": ctx["login"]}, 1, latest)["items"]
        return {"counts": count, "since": since, "mine": mine}

    def list(self, ctx, filters, page, size):
        """Lista paginada no escopo do perfil (README §4.3.C).

        Com VIEW_LOGS: ambientes autorizados (admin: todos). Sem VIEW_LOGS: apenas os
        tickets do proprio solicitante. filtros passa por normalize_filters.
        """
        if not self.can_query(ctx):
            self._deny(ctx, rbac.Reason.NO_FEATURE, None, None)
        repo_filters = _repo_filters(normalize_filters(filters))
        empty = {"items": [], "total": 0, "page": 1, "size": size}
        visible, scope = self._query_scope(ctx, repo_filters)
        if not visible:
            return empty
        result = self._tickets.list(filters=repo_filters, page=page, size=size,
                                         environment_scope=scope)
        info = ui_helpers.pagination_info(page, size, result["total"],
                                         result.get("total_capped", False), len(result["items"]))
        if not result["items"] and info["page"] != result["page"]:
            result = self._tickets.list(filters=repo_filters, page=info["page"], size=size,
                                             environment_scope=scope)
        now = self._tickets.now()
        names = self._script_names()
        items = []
        for t in result["items"]:
            items.append({
                "id": t["id"],
                "script_name": names.get(t["script_id"], "#%s" % t["script_id"]),
                "environment": t["environment"],
                "status": t["status"],
                "status_reason": t.get("status_reason"),
                "reason_description": ui_helpers.reason_description(t.get("status_reason")),
                "cancel_requested": t.get("cancel_requested") == "Y",
                "priority": t["priority"],
                "requested_by": ui_helpers.visible_actor(t["requested_by"], ctx),
                "source": "agendamento" if t.get("schedule_id") is not None else "manual",
                "created_at": t.get("created_at"),
                "started_at": t.get("started_at"),
                "duration": _duration(t, now),
            })
        return {"items": items, "total": result["total"], "page": result["page"],
                "size": result["size"], "total_capped": result.get("total_capped", False)}

    def _display_answers(self, ticket_id, snap):
        sensitive = set((snap or {}).get("sensitive") or ())
        rows = []
        for r in self._tickets.answers(ticket_id):
            try:
                prm = self._catalog.parameters_get(r["parameter_id"])
                code, label = prm["code"], prm.get("label") or prm["code"]
                is_sensitive = prm.get("sensitive") == "Y" or code in sensitive
            except RepoNotFound:
                code = label = "#%s" % r["parameter_id"]
                is_sensitive = True
            value = r.get("answer_value")
            rows.append({"code": code, "label": label, "sensitive": is_sensitive,
                           "value": params_compiler.MASK if is_sensitive and value not in (None, "") else value})
        return rows

    def _can_rerun_by_rule(self, ctx, ticket):
        # README §4.3.C: EXEC_SCRIPT reexecuta tickets proprios; admin, qualquer ticket visivel.
        return (ctx.get("is_admin") is True and rbac.has_feature(ctx, "EXEC_SCRIPT")) or self._is_own(ctx, ticket)

    def _can_execute_now(self, ctx, ticket):
        try:
            script = self._catalog.scripts_get(ticket["script_id"])
        except RepoNotFound:
            return False
        env = self._environment_by_name(ticket["environment"])
        if env is None:
            return False
        ok, _reason = rbac.can_execute(ctx, script, env, self._catalog.homologation_get(script["id"]))
        return ok

    def detail(self, ctx, ticket_id):
        """Ticket visivel com snapshot (sensiveis mascarados), respostas, cadeia e acoes permitidas.

        Lanca RepoNotFound se nao existir ou estiver fora do escopo do perfil.
        """
        ticket = self._visible_ticket(ctx, ticket_id, "TICKET_DETALHE")
        snap = _snapshot(ticket)
        try:
            script_name = self._catalog.scripts_get(ticket["script_id"])["name"]
        except RepoNotFound:
            script_name = (snap or {}).get("script_name") or "#%s" % ticket["script_id"]

        parent = None
        if ticket.get("parent_ticket_id") is not None:
            try:
                original = self._tickets.get(ticket["parent_ticket_id"])
            except RepoNotFound:
                original = None
            if original is not None and self._can_view(ctx, original):
                parent = {"id": original["id"], "status": original["status"]}
        children = [{"id": f["id"], "status": f["status"]}
                  for f in self._tickets.list(filters={"parent_ticket_id": ticket["id"]}, page=1,
                                                size=_CHILDREN_MAX)["items"]
                  if self._can_view(ctx, f)]
        children.sort(key=lambda f: f["id"])

        status = ticket["status"]
        cancel_requested = ticket.get("cancel_requested") == "Y"
        can_cancel = (status in CANCELLABLE_STATUSES and not cancel_requested
                         and rbac.can_cancel(ctx, ticket))
        can_rerun = (status in TERMINAL_STATUSES and self._can_rerun_by_rule(ctx, ticket)
                           and self._can_execute_now(ctx, ticket))
        argv = _display_argv(snap)
        now = self._tickets.now()
        try:
            timeout_s = self._catalog.scripts_get(ticket["script_id"]).get("timeout_s")
        except RepoNotFound:
            timeout_s = None
        snapshot = None
        if snap is not None:
            # Caminho completo para todos (README §8.5, CR-005 D8).
            snapshot = dict((k, snap.get(k)) for k in ("version", "interpreter", "path_file", "param_type"))
            snapshot["compiled_at"] = snap.get("compiled_at")  # chave de tela (CR-016d)
        return {
            "id": ticket["id"],
            "script_id": ticket["script_id"],
            "script_name": script_name,
            "environment": ticket["environment"],
            "status": status,
            "status_reason": ticket.get("status_reason"),
            "reason_description": ui_helpers.reason_description(ticket.get("status_reason")),
            "return_code": ticket.get("return_code"),
            "cancel_requested": cancel_requested,
            "priority": ticket["priority"],
            "requested_by": ui_helpers.visible_actor(ticket["requested_by"], ctx),
            "source": "agendamento" if ticket.get("schedule_id") is not None else "manual",
            "schedule_id": ticket.get("schedule_id"),
            "agent_id": ticket.get("agent_id"),
            "process_id": ticket.get("process_id"),
            "created_at": ticket.get("created_at"),
            "scheduled_at": ticket.get("scheduled_at"),
            "started_at": ticket.get("started_at"),
            "heartbeat_at": ticket.get("heartbeat_at"),
            "finished_at": ticket.get("finished_at"),
            "duration": _duration(ticket, now),
            # CR-004 U2 (README §5.7): frase "o que aconteceu / o que fazer" e barra de etapas.
            "explanation": ui_helpers.ticket_explanation(ticket, now, timeout_s),
            "steps": ui_helpers.ticket_steps(ticket, now),
            "log_truncated": ticket.get("log_truncated") == "Y",
            "snapshot": snapshot,
            "display_argv": argv,
            "display_command": " ".join(shlex.quote(str(t)) for t in argv) if argv else None,
            "answers": self._display_answers(ticket["id"], snap),
            "parent": parent,
            "children": children,
            "record": ui_helpers.record_info(ticket, ctx),
            # CR-012 (README §8.13): quadro Saida, com a mesma regra de leitura do log (ticket visivel).
            "output": ui_helpers.output_panel(self._tickets.output_get(ticket["id"]), now),
            "can_cancel": can_cancel,
            "can_rerun": can_rerun,
        }

    # ------------------------------------------------------------------ log

    def read_log(self, ctx, ticket_id, offset):
        """Bloco do log a partir de offset (caracteres, base 0), no maximo LOG_MAX_CHARS.

        Retorna {text, next_offset, terminal, truncated, status}. Lanca InvalidOffset e
        RepoNotFound (inexistente ou fora do escopo do perfil).
        """
        off = _offset(offset)
        ticket = self._visible_ticket(ctx, ticket_id, "LOG_LER")
        text, next_value, terminal, truncated = self._tickets.log_read(ticket["id"], off, LOG_MAX_CHARS)
        status = ticket["status"]
        if terminal and status not in TERMINAL_STATUSES:
            # O ticket terminou entre a checagem de escopo e a leitura.
            status = self._tickets.get(ticket["id"])["status"]
        return {"text": text, "next_offset": next_value, "terminal": bool(terminal),
                "truncated": bool(truncated), "status": status}

    def output_chunks(self, ctx, ticket_id):
        """Valida o escopo (regra do log) e a situacao DISPONIVEL; retorna (id, tamanho, gerador de fatias).

        Lanca RepoNotFound fora do escopo, sem saida ou fora de DISPONIVEL. Uma falha de leitura no meio
        encerra o gerador: com Content-Length, o navegador acusa o download incompleto (o zip nao e reparado).
        """
        ticket = self._visible_ticket(ctx, ticket_id, "SAIDA_BAIXAR")
        tid = ticket["id"]
        output = self._tickets.output_get(tid)
        if not output or output.get("state") != "AVAILABLE" or not output.get("size_bytes"):
            raise RepoNotFound("saida do ticket indisponivel")
        size = int(output["size_bytes"])
        self._log.info("download da saida (login=%s ticket=%s bytes=%s)", ctx.get("login"), tid, size,
                       extra={"action": "SAIDA_BAIXAR"})

        def gerar():
            off = 0
            while off < size:
                try:
                    part = self._tickets.output_read(tid, off, OUTPUT_SLICE_BYTES)
                except RepoError:
                    self._log.exception("falha na leitura da saida para download (ticket=%s offset=%s)", tid, off,
                                        extra={"action": "SAIDA_BAIXAR"})
                    return
                if not part:
                    return
                off += len(part)
                yield part

        return tid, size, gerar()

    def log_chunks(self, ctx, ticket_id):
        """Valida o escopo e retorna (id, gerador de blocos do log integral via log_ler).

        A validacao ocorre antes do streaming; uma falha de leitura no meio encerra o
        gerador com DOWNLOAD_INTERRUPTED_MARKER, para o arquivo nao parecer completo.
        """
        ticket = self._visible_ticket(ctx, ticket_id, "LOG_BAIXAR")
        tid = ticket["id"]
        self._log.info("download de log (login=%s ticket=%s)", ctx.get("login"), tid,
                       extra={"action": "LOG_BAIXAR"})

        def gerar():
            off = 0
            while True:
                try:
                    text, off, _terminal, _truncated = self._tickets.log_read(tid, off, LOG_MAX_CHARS)
                except RepoError:
                    self._log.exception("falha na leitura do log para download (ticket=%s offset=%s)", tid, off,
                                        extra={"action": "LOG_BAIXAR"})
                    yield DOWNLOAD_INTERRUPTED_MARKER
                    return
                if not text:
                    return
                yield text

        return tid, gerar()

    # --------------------------------------------------- cancelar/reexecutar

    def cancel(self, ctx, ip, ticket_id):
        """Cancelamento pelo no web (README §5.6) com auditoria TICKET_CANCEL no repositorio.

        Retorna 'TERMINAL' | 'CANCELADO' | 'SINALIZADO' | 'JA_SINALIZADO' (mensagens em MSG_CANCEL);
        toda solicitacao e auditada (README §5.6). CANCEL_TICKET nao exige VIEW_LOGS (README §4.3.C).
        Lanca RepoNotFound (fora do escopo) e AccessDenied (sem CANCEL_TICKET/proprio).
        """
        tid = _id(ticket_id)
        if tid is None:
            raise RepoNotFound("ticket invalido")
        ticket = self._tickets.get(tid)
        if not (self._can_view(ctx, ticket) or rbac.can_cancel(ctx, ticket)):
            self._log.warning("ticket fora do escopo (login=%s ticket=%s environment=%s)",
                              ctx.get("login"), tid, ticket.get("environment"), extra={"action": "TICKET_CANCEL"})
            raise RepoNotFound("ticket fora do escopo")
        if not rbac.can_cancel(ctx, ticket):
            self._deny(ctx, "SEM_CANCELAMENTO", ticket["script_id"], ticket["environment"])
        try:
            result = self._tickets.request_cancel(ticket["id"], ctx["login"], ip)
        except RepoError:
            self._log.exception("falha ao cancelar ticket (ticket=%s login=%s)", ticket["id"], ctx["login"],
                                extra={"action": "TICKET_CANCEL"})
            raise
        self._log.info("cancelamento de ticket (ticket=%s login=%s resultado=%s ip=%s)",
                       ticket["id"], ctx["login"], result, ip, extra={"action": "TICKET_CANCEL"})
        return result

    def _rerunnable_ticket(self, ctx, ticket_id):
        ticket = self._visible_ticket(ctx, ticket_id, "TICKET_RERUN")
        if ticket["status"] not in TERMINAL_STATUSES:
            self._deny(ctx, "TICKET_NAO_TERMINAL", ticket["script_id"], ticket["environment"])
        if not self._can_rerun_by_rule(ctx, ticket):
            self._deny(ctx, rbac.Reason.NO_FEATURE, ticket["script_id"], ticket["environment"])
        return ticket

    def _original_answers(self, ticket, links):
        """Respostas resolvidas do original (tbsss_ticket_answer) indexadas pelo codigo vigente."""
        codes = dict((v["parameter_id"], v["code"]) for v in links)
        answers = {}
        for r in self._tickets.answers(ticket["id"]):
            code = codes.get(r["parameter_id"])
            if code is not None and r.get("answer_value") is not None:
                answers[code] = r["answer_value"]
        return answers

    def _recompile(self, ctx, ticket):
        script, env = self._authorize(ctx, ticket["script_id"], ticket["environment"])
        answers = self._original_answers(ticket, self._links(script["id"]))
        now = self._tickets.now()
        errors = collections.OrderedDict()
        prio = self._priority(ctx, str(ticket["priority"]), errors)
        snapshot, resolved, links = self._compile(ctx, script, env, answers, now, errors)
        return script, env, prio, answers, snapshot, resolved, links, errors

    def rerun(self, ctx, ip, ticket_id):
        """Novo ticket com parent_ticket_id, recompilado contra o catalogo vigente (README §5.5).

        Retorna o novo ID. Lanca RepoNotFound (fora do escopo), AccessDenied (regra de
        reexecucao ou can_execute vigente) e RerunError (recompilacao ou gravacao).
        """
        original = self._rerunnable_ticket(ctx, ticket_id)
        script, env, prio, _resp, snapshot, resolved, links, errors = self._recompile(ctx, original)
        if errors:
            raise RerunError(original["id"], dict(errors))
        new_id, errors = self._save(ctx, ip, script, env, prio, None, snapshot, resolved, links,
                                      original["id"])
        if new_id is None:
            raise RerunError(original["id"], errors)
        return new_id

    def prepare_rerun(self, ctx, ticket_id):
        """Dados para reabrir o questionario a partir de um ticket (fallback da reexecucao).

        Retorna {ticket_id, script_id, environment, priority, values, errors}; valores de
        parametros sensiveis nunca sao devolvidos.
        """
        original = self._rerunnable_ticket(ctx, ticket_id)
        script, env, prio, answers, _snap, _resolv, links, errors = self._recompile(ctx, original)
        sensitive = set(v["code"] for v in links if v.get("sensitive") == "Y")
        return {
            "ticket_id": original["id"],
            "script_id": script["id"],
            "environment": env["name"],
            "priority": str(prio if prio is not None else DEFAULT_PRIORITY),
            "values": dict((k, v) for k, v in answers.items() if k not in sensitive),
            "errors": dict(errors),
        }

_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from gluon import current
            import sss_logging
            factory = current.repo_factory
            cfg = current.sss_cfg
            _default = TicketService(
                catalog=factory.get("catalog"),
                tickets=factory.get("tickets"),
                log=sss_logging.get_logger("sss_web", cfg),
            )
        return _default


def available_scripts(ctx):
    """Scripts executaveis agrupados (servico padrao do processo web)."""
    return _service().available_scripts(ctx)


def available_environments(ctx, script_id):
    """Ambientes homologados e autorizados para o script (servico padrao)."""
    return _service().available_environments(ctx, script_id)


def prepare_form(ctx, script_id, environment, values=None, errors=None, warnings=None):
    """Questionario do script no ambiente (servico padrao)."""
    return _service().prepare_form(ctx, script_id, environment, values, errors, warnings)


def trigger_summary(ctx, script_id, environment, answers, priority=None, scheduled_at=None):
    """Resumo em frase do disparo (servico padrao)."""
    return _service().trigger_summary(ctx, script_id, environment, answers, priority, scheduled_at)


def script_history(ctx, script_id):
    """Historico de 30 dias do script (servico padrao)."""
    return _service().script_history(ctx, script_id)


def routine_catalog(ctx):
    """Rotinas disponiveis (servico padrao)."""
    return _service().routine_catalog(ctx)


def has_last_run(ctx, script_id, environment):
    """Ha execucao propria anterior deste script neste ambiente (servico padrao)."""
    return _service().has_last_run(ctx, script_id, environment)


def last_answers(ctx, script_id, environment):
    """Respostas reutilizaveis da ultima execucao propria (servico padrao)."""
    return _service().last_answers(ctx, script_id, environment)


def preview(ctx, script_id, environment, answers):
    """Previa do argv mascarado (servico padrao)."""
    return _service().preview(ctx, script_id, environment, answers)


def create_ticket(ctx, ip, script_id, environment, answers, priority, scheduled_at, rerun_of=None):
    """Criacao do ticket (servico padrao)."""
    return _service().create_ticket(ctx, ip, script_id, environment, answers, priority, scheduled_at,
                                   rerun_of)


def can_query(ctx):
    """Acesso a lista de tickets (servico padrao)."""
    return _service().can_query(ctx)


def filter_options(ctx):
    """Opcoes dos filtros da lista de tickets (servico padrao)."""
    return _service().filter_options(ctx)


def list_page(ctx, filters, page, size):
    """Lista de tickets no escopo do perfil (servico padrao)."""
    return _service().list(ctx, filters, page, size)


def home_summary(ctx):
    """Cartoes de tickets do painel inicial (servico padrao)."""
    return _service().home_summary(ctx)


def detail(ctx, ticket_id):
    """Detalhe do ticket visivel (servico padrao)."""
    return _service().detail(ctx, ticket_id)


def is_visible(ctx, ticket_id):
    """Ticket visivel ao usuario (servico padrao)."""
    return _service().is_visible(ctx, ticket_id)


def cancel(ctx, ip, ticket_id):
    """Cancelamento pelo no web (servico padrao)."""
    return _service().cancel(ctx, ip, ticket_id)


def rerun(ctx, ip, ticket_id):
    """Reexecucao do ticket (servico padrao)."""
    return _service().rerun(ctx, ip, ticket_id)


def prepare_rerun(ctx, ticket_id):
    """Questionario pre-preenchido para reexecucao com erro (servico padrao)."""
    return _service().prepare_rerun(ctx, ticket_id)


def read_log(ctx, ticket_id, offset):
    """Bloco incremental do log do ticket visivel (servico padrao)."""
    return _service().read_log(ctx, ticket_id, offset)


def log_chunks(ctx, ticket_id):
    """Gerador do log integral do ticket visivel para download (servico padrao)."""
    return _service().log_chunks(ctx, ticket_id)


def output_chunks(ctx, ticket_id):
    """(id, tamanho, gerador) do zip da saida do ticket visivel e DISPONIVEL (servico padrao, CR-012)."""
    return _service().output_chunks(ctx, ticket_id)
