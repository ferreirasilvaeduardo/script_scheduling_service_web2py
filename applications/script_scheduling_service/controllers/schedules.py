# -*- coding: utf-8 -*-
"""Regras de agendamento (README §4.3.C MANAGE_SCHEDULES, §7). Regras de negocio ficam em
modules/schedules_service.py; padrao de telas em docs/ADMIN_CRUD_PATTERN.md.

CSRF e Origin de todo POST sao validados em models/10_security.py.
"""
import admin_crud
import schedules_service as service
import ui_helpers
from admin_crud import AccessDenied, OperationDenied
from repo_errors import RepoConflict, RepoError, RepoNotFound
from ticket_service import AccessDenied as TriggerDenied

_FUNC = "MANAGE_SCHEDULES"
_PARAM_PREFIX = "p_"
_JS = "js/app/schedules.js"
_SIZES = (20, 50, 100)
_RULE_FIELDS = ("name", "recurrence_type", "cron_expression", "run_time", "month_day", "start_date",
                 "end_date", "priority", "version")
# Protecao de memoria acima dos limites do service, que recusa o excesso (README §7.6, AGENTS §3.4).
_LIMITS = {"name": 300, "cron_expression": 300, "run_time": 40, "month_day": 40, "start_date": 40,
            "end_date": 40, "priority": 10, "version": 100, "recurrence_type": 40}
_MSG_LIST_FAILED = u"Não foi possível carregar as regras. Tente novamente em instantes."
_MSG_ACTION_FAILED = u"Não foi possível concluir a operação. Tente novamente em instantes."


def _require_method(*permitidos):
    if (request.env.request_method or "GET").upper() not in permitidos:
        raise HTTP(405, **response.headers)


def _denied():
    raise HTTP(403, u"Acesso negado.", **response.headers)


def _not_found():
    raise HTTP(404, u"Regra de agendamento não encontrada.", **response.headers)


def _text(value, limit):
    value = value[-1] if isinstance(value, list) and value else value
    return value[:limit] if isinstance(value, str) else None


def _post_days(source):
    value = source.get("week_days")
    if isinstance(value, list):
        return [v[:2] for v in value[:7] if isinstance(v, str)]
    return _text(value, 20)


def _post_rule(source):
    data = dict((c, _text(source.get(c), _LIMITS[c])) for c in _RULE_FIELDS)
    data["week_days"] = _post_days(source)
    return data


def _post_answers():
    answers = {}
    for key, value in request.post_vars.items():
        if isinstance(key, str) and key.startswith(_PARAM_PREFIX):
            answers[key[len(_PARAM_PREFIX):]] = value
    return answers


def _form_page(data):
    rule = data.get("rule") or {}
    if data["editing"]:
        response.title = u"Regra %s — SSS" % rule.get("name", "")
    else:
        response.title = u"Nova regra de agendamento — SSS"
    response.view = "schedules/form.html"
    response.sss_scripts = [_JS]
    errors = data["errors"]
    focus = None
    if data.get("form"):
        fields = [{"name": n, "error": errors.get(n)} for n in ("name", "recurrence_type", "start_date", "end_date",
                                                               "run_time", "week_days", "month_day",
                                                               "cron_expression")]
        fields.extend({"name": c["name"], "error": c["error"]} for c in data["form"]["fields"])
        fields.append({"name": "priority", "error": errors.get("priority")})
        focus = ui_helpers.first_invalid_field(fields)
    return dict(data, errors=errors, general_error=errors.get(admin_crud.GENERAL_FIELD), focus_field=focus,
                type_labels=service.TYPE_LABELS, weekdays=service.WEEKDAYS)


def _redirect_to_list(kind, message):
    session.flash = {"kind": kind, "message": message}
    redirect(URL(c="schedules", f="index"))


def index():
    _require_method("GET", "HEAD")
    ctx = _require_func(_FUNC)
    filters = service.normalize_filters(request.get_vars)
    page = ui_helpers.sanitize_page(_text(request.get_vars.get("page"), 9))
    size = ui_helpers.sanitize_size(_text(request.get_vars.get("size"), 3), _SIZES)
    error = None
    try:
        result = service.list_page(ctx, filters, page, size)
    except AccessDenied:
        _denied()
    except RepoError:
        _log.exception("falha ao listar agendamentos (login=%s)", ctx["login"], extra={"action": _FUNC})
        result = {"items": [], "total": 0, "page": 1, "size": size}
        error = _MSG_LIST_FAILED
    response.title = u"Regras de agendamento — SSS"
    response.sss_scripts = [_JS]
    return dict(result=result, error=error, active_filters=filters, size=size,
                query_params=dict(filters, size=size))


def agenda():
    """Agenda (README §7.7): o que vai rodar hoje e nos proximos 7 dias; so leitura."""
    _require_method("GET", "HEAD")
    ctx = _require_func(_FUNC)
    response.title = u"Agenda — SSS"
    try:
        return dict(data=service.agenda(ctx), error=None)
    except AccessDenied:
        _denied()
    except RepoError:
        _log.exception("falha ao montar a agenda (login=%s)", ctx["login"], extra={"action": _FUNC})
        return dict(data=None, error=ui_helpers.message("internal_error"))


def form():
    _require_method("GET", "HEAD")
    ctx = _require_func(_FUNC)
    try:
        data = service.form(ctx, _text(request.args(0), 11),
                                   _text(request.get_vars.get("script_id"), 10),
                                   _text(request.get_vars.get("environment"), 30))
    except RepoNotFound:
        _not_found()
    except (AccessDenied, TriggerDenied):
        _denied()
    except OperationDenied as exc:
        _redirect_to_list("error", exc.message)
    return _form_page(data)


def save():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    schedule_id = _text(request.post_vars.get("id"), 11)
    script_id = _text(request.post_vars.get("script_id"), 10)
    environment = _text(request.post_vars.get("environment"), 30)
    submitted = _post_rule(request.post_vars)
    answers = _post_answers()
    try:
        saved_id, errors = service.save(ctx, _client_ip(), dict(submitted, id=schedule_id, script_id=script_id,
                                                                  environment=environment, answers=answers))
    except RepoNotFound:
        _not_found()
    except AccessDenied:
        _denied()
    except OperationDenied as exc:
        _redirect_to_list("error", exc.message)
    except RepoError:
        _log.exception("falha ao salvar agendamento (login=%s id=%r)", ctx["login"], schedule_id,
                       extra={"action": _FUNC})
        saved_id, errors = None, {admin_crud.GENERAL_FIELD: admin_crud.MSG_FAILURE}
    if not errors:
        _redirect_to_list("success", u"Regra de agendamento salva com sucesso.")
    conflict = errors.get(admin_crud.GENERAL_FIELD) == admin_crud.MSG_CONFLICT
    try:
        # No conflito, o formulario volta com os dados atuais e uma nova versao (PADRAO_CRUD_ADMIN).
        data = service.form(ctx, schedule_id, script_id, environment,
                                   submitted=None if conflict else submitted,
                                   values=None if conflict else answers, errors=errors)
    except RepoNotFound:
        _not_found()
    except (AccessDenied, TriggerDenied):
        _denied()
    except OperationDenied as exc:
        _redirect_to_list("error", exc.message)
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"kind": "error", "message": errors.get(admin_crud.GENERAL_FIELD)
                      or ui_helpers.message("form_errors")}
    return _form_page(data)


def _state_action(func, success):
    _require_method("POST")
    ctx = _require_func(_FUNC)
    schedule_id = _text(request.post_vars.get("id"), 11)
    try:
        changed = func(ctx, _client_ip(), schedule_id)
        session.flash = {"kind": "success", "message": success % changed["name"]}
    except RepoNotFound:
        _not_found()
    except AccessDenied:
        _denied()
    except OperationDenied as exc:
        session.flash = {"kind": "warning", "message": exc.message}
    except RepoConflict:
        session.flash = {"kind": "warning", "message": admin_crud.MSG_CONFLICT}
    except RepoError:
        _log.exception("falha ao alterar a situacao do agendamento (login=%s id=%r)", ctx["login"],
                       schedule_id, extra={"action": _FUNC})
        session.flash = {"kind": "error", "message": _MSG_ACTION_FAILED}
    redirect(URL(c="schedules", f="index"))


def pause():
    _state_action(service.pause, u"Regra %s pausada.")


def resume():
    _state_action(service.resume, u"Regra %s retomada.")


def preview():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    data = _post_rule(request.post_vars)
    try:
        result = service.preview(ctx, data)
    except AccessDenied:
        response.status = 403
        return response.json({"error": u"Acesso negado."})
    return response.json(result)
