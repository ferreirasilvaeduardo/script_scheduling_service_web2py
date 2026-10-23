# -*- coding: utf-8 -*-
"""Disparo de script e tickets (README §5). Regras de negocio ficam em modules/ticket_service.py.

CSRF e Origin de todo POST sao validados em models/10_security.py.
"""
from gluon import current

import ticket_service
import ui_helpers
from repo_errors import RepoError, RepoNotFound
from ticket_service import AccessDenied, RerunError

_PARAM_PREFIX = "p_"
_JS_TRIGGER = "js/app/trigger.js"
_JS_TICKETS = "js/app/tickets.js"
_JS_LOG = "js/app/log_viewer.js"
_SIZES = (20, 50, 100)
_LIST_EXTENSIONS = ("html", "load")
_MSG_NOT_FOUND = u"Ticket não encontrado."
_MSG_LIST_FAILED = u"Não foi possível carregar os tickets. Tente novamente em instantes."
_MSG_CANCEL_FAILED = u"Não foi possível cancelar o ticket. Tente novamente em instantes."
_MSG_OUTPUT_FAILED = u"Não foi possível baixar a saída. Tente novamente em instantes."
_MSG_RERUN_REVIEW = (u"Não foi possível reexecutar automaticamente: o cadastro do script pode ter mudado "
                           u"desde a execução original. Revise os campos destacados e crie o ticket novamente.")
_CANCEL_FLASH_KIND = {"TERMINAL": "warning", "CANCELADO": "success", "SINALIZADO": "success",
                            "JA_SINALIZADO": "warning"}


def _post_answers():
    answers = {}
    for key, value in request.post_vars.items():
        if isinstance(key, str) and key.startswith(_PARAM_PREFIX):
            answers[key[len(_PARAM_PREFIX):]] = value
    return answers


def _new_page(ctx, script_id, environment, values=None, errors=None, priority=None, scheduled_at=None,
                 rerun_of=None, warnings=None):
    response.title = u"Disparar script — SSS"
    response.sss_scripts = [_JS_TRIGGER]
    errors = errors or {}
    data = dict(step=1, script=None, environments=[], form=None, errors=errors,
                 general_error=errors.get(ticket_service.GENERAL_FIELD), priority=priority,
                 scheduled_at=scheduled_at or "", focus_field=None, rerun_of=rerun_of,
                 has_last=False, used_last=warnings is not None, single_environment=False,
                 aging_min=current.sss_cfg.agent.queue_aging_min)
    if not script_id:
        return data
    script, environments = ticket_service.available_environments(ctx, script_id)
    data.update(step=2, script=script, environments=environments,
                single_environment=len(environments) == 1)
    if not environment and len(environments) == 1:
        # Um ambiente so: a escolha nao tem o que decidir (CR-017b).
        environment = environments[0]["name"]
    if not environment:
        return data
    form = ticket_service.prepare_form(ctx, script_id, environment, values, errors, warnings)
    data["has_last"] = not rerun_of and ticket_service.has_last_run(ctx, script_id, environment)
    fields = [{"name": c["name"], "error": c["error"]} for c in form["fields"]]
    fields.append({"name": "priority", "error": errors.get(ticket_service.PRIORITY_FIELD)})
    fields.append({"name": "scheduled_at", "error": errors.get(ticket_service.SCHEDULED_AT_FIELD)})
    data.update(step=3, form=form, focus_field=ui_helpers.first_invalid_field(fields))
    return data


def new():
    _require_method("GET", "HEAD")
    ctx = _require_func("EXEC_SCRIPT")
    rerun = _text(request.get_vars.get("rerun"), 10)
    if not rerun and not _text(request.get_vars.get("script_id"), 10):
        # A escolha do script e feita nos cartoes de Rodar um script (CR-017b).
        redirect(URL(c="tickets", f="catalog"))
    try:
        if rerun:
            data = ticket_service.prepare_rerun(ctx, rerun)
            return _new_page(ctx, data["script_id"], data["environment"], data["values"], data["errors"],
                                data["priority"], rerun_of=data["ticket_id"])
        script_id = _text(request.get_vars.get("script_id"), 10)
        environment = _text(request.get_vars.get("environment"), 30)
        if script_id and environment and request.get_vars.get("last") == "1":
            # README §5.4: respostas da ultima execucao propria, sem sensiveis; nada e gravado.
            values, warnings = ticket_service.last_answers(ctx, script_id, environment)
            return _new_page(ctx, script_id, environment, values, warnings=warnings)
        return _new_page(ctx, script_id, environment)
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()


def catalog():
    """Rotinas disponiveis (README §5.8): so leitura, para quem tem EXEC_SCRIPT."""
    _require_method("GET", "HEAD")
    ctx = _require_func("EXEC_SCRIPT")
    response.title = u"Rodar um script — SSS"
    can_schedule = ticket_service.can_schedule(ctx)
    try:
        return dict(groups=ticket_service.routine_catalog(ctx), error=None, can_schedule=can_schedule)
    except RepoError:
        _log.exception("falha ao montar o catalogo de rotinas (login=%s)", ctx["login"], extra={"action": "CATALOGO"})
        return dict(groups=[], error=ui_helpers.message("internal_error"), can_schedule=can_schedule)


def history():
    """Historico do script (README §5.8): so leitura, para quem tem EXEC_SCRIPT."""
    _require_method("GET", "HEAD")
    ctx = _require_func("EXEC_SCRIPT")
    try:
        data = ticket_service.script_history(ctx, _text(request.args(0), 10))
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    response.title = u"Histórico de %s — SSS" % data["script"]["name"]
    return dict(h=data)


def create():
    _require_method("POST")
    ctx = _require_func("EXEC_SCRIPT")
    script_id = _text(request.post_vars.get("script_id"), 10)
    environment = _text(request.post_vars.get("environment"), 30)
    priority = _text(request.post_vars.get("priority"), 10)
    scheduled_at = _text(request.post_vars.get("scheduled_at"), 40)
    rerun_of = _text(request.post_vars.get("rerun_of"), 10)
    answers = _post_answers()
    try:
        ticket_id, errors = ticket_service.create_ticket(ctx, _client_ip(), script_id, environment, answers,
                                                       priority, scheduled_at, rerun_of)
        if ticket_id is not None:
            session.flash = {"kind": "success", "message": u"Ticket #%s criado com sucesso." % ticket_id}
            redirect(URL(c="tickets", f="detail", args=[ticket_id]))
        # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
        response.flash = {"kind": "error", "message": ui_helpers.message("form_errors")}
        response.view = "tickets/new.html"
        return _new_page(ctx, script_id, environment, answers, errors, priority, scheduled_at,
                            rerun_of or None)
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()


def preview():
    # POST porque o corpo pode conter valores sensiveis: nunca na URL nem no log de acesso.
    _require_method("POST")
    ctx = _require_func("EXEC_SCRIPT")
    answers = request.post_vars.get("answers")
    try:
        # Mesmo endpoint da previa do comando e do resumo em frase do modal (README §5.4).
        data = ticket_service.trigger_summary(ctx, _text(request.post_vars.get("script_id"), 10),
                                              _text(request.post_vars.get("environment"), 30),
                                              answers if isinstance(answers, dict) else {},
                                              _text(request.post_vars.get("priority"), 10),
                                              _text(request.post_vars.get("scheduled_at"), 40))
    except AccessDenied:
        response.status = 403
        return response.json({"error": ui_helpers.message("no_permission")})
    return response.json(data)


def index():
    _require_method("GET", "HEAD")
    if request.extension not in _LIST_EXTENSIONS:
        raise HTTP(404, **response.headers)
    ctx = _require_query()
    filters = ticket_service.allowed_filters(ctx, ticket_service.normalize_filters(request.get_vars))
    page = ui_helpers.sanitize_page(_text(request.get_vars.get("page"), 9))
    size = ui_helpers.sanitize_size(_text(request.get_vars.get("size"), 3), _SIZES)
    error = None
    try:
        result = ticket_service.list_page(ctx, filters, page, size)
    except AccessDenied:
        _denied()
    except RepoError:
        _log.exception("falha ao listar tickets (login=%s)", ctx["login"], extra={"action": "TICKET_LISTAR"})
        result = {"items": [], "total": 0, "page": 1, "size": size}
        error = _MSG_LIST_FAILED
    query_params = dict(filters, size=size)
    data = dict(result=result, error=error, page=result["page"], size=size,
                 query_params=query_params,
                 fragment_url=URL(c="tickets", f="index", extension="load",
                                   vars=dict(query_params, page=result["page"])))
    if request.extension == "load":
        return data
    response.title = u"Tickets — SSS"
    response.sss_scripts = [_JS_TICKETS]
    data["active_filters"] = filters
    data["options"] = ticket_service.filter_options(ctx)
    data["can_filter_requester"] = ui_helpers.sees_actors(ctx)
    return data


def detail():
    _require_method("GET", "HEAD")
    ctx = _require_query()
    try:
        ticket = ticket_service.detail(ctx, request.args(0))
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    response.title = u"Ticket #%s — SSS" % ticket["id"]
    response.sss_scripts = [_JS_TICKETS, _JS_LOG]
    log_viewer = {
        "url_chunk": URL(c="logs", f="chunk", vars={"ticket_id": ticket["id"]}),
        "download_url": URL(c="logs", f="download", vars={"ticket_id": ticket["id"]}),
        "interval_s": current.sss_cfg.web.log_poll_interval_s,
        "max_chars": ticket_service.LOG_MAX_CHARS,
    }
    return dict(ticket=ticket, log_viewer=log_viewer)


def output():
    """Download do zip da pasta de saida (CR-012, README §8.13): GET, regra de leitura do log, so DISPONIVEL."""
    _require_method("GET", "HEAD")
    ctx = _require_query()
    try:
        ticket_id, size, parts = ticket_service.output_chunks(ctx, request.args(0))
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except RepoError:
        _log.exception("falha ao iniciar o download da saida (login=%s ticket=%r)", ctx["login"], request.args(0),
                       extra={"action": "SAIDA_BAIXAR"})
        raise HTTP(503, _MSG_OUTPUT_FAILED, **response.headers)
    response.headers["Content-Type"] = "application/zip"
    response.headers["Content-Disposition"] = 'attachment; filename="ticket_%d_saida.zip"' % ticket_id
    response.headers["Content-Length"] = str(size)
    response.headers["Cache-Control"] = "no-store"
    # Iteravel: o web2py o devolve ao WSGI como corpo em streaming, fatia a fatia.
    return parts


def cancel():
    _require_method("POST")
    ctx = _require_login()
    ticket_id = _text(request.post_vars.get("ticket_id"), 10)
    try:
        result = ticket_service.cancel(ctx, _client_ip(), ticket_id)
        session.flash = {"kind": _CANCEL_FLASH_KIND[result],
                         "message": ticket_service.MSG_CANCEL[result]}
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    except RepoError:
        session.flash = {"kind": "error", "message": _MSG_CANCEL_FAILED}
    # So cancela quem enxerga o ticket (CR-018a): volta sempre ao detalhe.
    redirect(URL(c="tickets", f="detail", args=[ticket_id]))


def rerun():
    _require_method("POST")
    ctx = _require_func("EXEC_SCRIPT")
    ticket_id = _text(request.post_vars.get("ticket_id"), 10)
    try:
        new_id = ticket_service.rerun(ctx, _client_ip(), ticket_id)
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    except RerunError as e:
        session.flash = {"kind": "warning", "message": _MSG_RERUN_REVIEW}
        redirect(URL(c="tickets", f="new", vars={"rerun": e.ticket_id}))
    session.flash = {"kind": "success",
                     "message": u"Ticket #%s criado como reexecução do ticket #%s." % (new_id, ticket_id)}
    redirect(URL(c="tickets", f="detail", args=[new_id]))
