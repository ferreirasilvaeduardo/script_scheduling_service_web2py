# -*- coding: utf-8 -*-
"""Dicionario de parametros (README §6, MANAGE_PARAMETERS). Padrao em docs/ADMIN_CRUD_PATTERN.md.

Regras ficam em modules/admin_parameters_service.py; CSRF e Origin de todo POST sao validados em
models/10_security.py. O editor de opcoes do cliente e conveniencia: o servidor revalida tudo.
"""
import admin_crud
import admin_parameters_service as service
import ui_helpers
from admin_crud import AccessDenied, OperationDenied
from repo_errors import RepoConflict, RepoError, RepoNotFound

_FUNC = "MANAGE_PARAMETERS"
_SIZES = (20, 50, 100)
_FIELDS = ("code", "param_flag", "label", "description", "component_type", "options_json", "default_value",
           "remove_default", "validation_regex", "sensitive", "version")
_JS = "js/app/parameters.js"
_MSG_NOT_FOUND = u"Parâmetro não encontrado."
_MSG_LIST_FAILED = u"Não foi possível carregar os parâmetros. Tente novamente em instantes."
_MSG_ACTION_FAILED = u"Não foi possível concluir a operação. Tente novamente em instantes."


def _submitted():
    return dict((c, _text(request.post_vars.get(c), 1000)) for c in _FIELDS)


def _form_page(ctx, data, errors=None):
    response.title = (u"Parâmetro %s — SSS" % data["code"]) if data.get("id") else u"Novo parâmetro — SSS"
    response.view = "admin_parameters/form.html"
    response.sss_scripts = [_JS]
    errors = errors or {}
    fields = [{"name": n, "error": errors.get(n)} for n in ("code", "param_flag", "label", "description",
                                                          "component_type", "options_json", "validation_regex",
                                                          "default_value")]
    return dict(prm=data, errors=errors, general_error=errors.get(admin_crud.GENERAL_FIELD),
                focus_field=ui_helpers.first_invalid_field(fields), types=service.TYPE_LABELS,
                sensitive_warning=service.SENSITIVE_WARNING)


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
        _log.exception("falha ao listar parametros (login=%s)", ctx["login"], extra={"action": _FUNC})
        result = {"items": [], "total": 0, "page": 1, "size": size}
        error = _MSG_LIST_FAILED
    response.title = u"Parâmetros — SSS"
    return dict(result=result, error=error, active_filters=filters, size=size, types=service.TYPE_LABELS,
                query_params=dict(filters, size=size))


def form():
    _require_method("GET", "HEAD")
    ctx = _require_func(_FUNC)
    try:
        data = service.form(ctx, _text(request.args(0), 11))
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    return _form_page(ctx, data)


def _rules_warning(ctx, parameter_id):
    """Regras que vao ser pausadas (CR-018a); so na alteracao, e uma falha nao desfaz o que foi salvo."""
    if not parameter_id:
        return None
    try:
        return service.rules_warning(ctx, parameter_id)
    except RepoError:
        _log.exception("falha ao conferir as regras afetadas (login=%s id=%r)", ctx["login"], parameter_id,
                       extra={"action": _FUNC})
        return None


def save():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    parameter_id = _text(request.post_vars.get("id"), 11)
    submitted = _submitted()
    try:
        _saved, errors = service.save(ctx, _client_ip(), parameter_id, submitted)
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    except RepoError:
        _log.exception("falha ao salvar parametro (login=%s id=%r)", ctx["login"], parameter_id, extra={"action": _FUNC})
        errors = {admin_crud.GENERAL_FIELD: admin_crud.MSG_FAILURE}
    if not errors:
        warning = _rules_warning(ctx, parameter_id)
        session.flash = {"kind": "warning" if warning else "success",
                         "message": u"Parâmetro salvo com sucesso." + (u" " + warning if warning else u"")}
        redirect(URL(c="admin_parameters", f="index"))
    try:
        data = service.form(ctx, parameter_id) if parameter_id else service.form(ctx)
    except RepoError:
        data = {"id": None, "code": "", "param_flag": "", "label": "", "description": "",
                 "component_type": "TEXT", "options_json": "", "default_value": "", "has_default": False,
                 "validation_regex": "", "sensitive": "N", "active": "Y", "version": "", "links": [],
                 "can_regex": ctx.get("is_admin") is True}
    if admin_crud.GENERAL_FIELD not in errors:
        redisplay = dict((c, submitted[c] or "") for c in ("param_flag", "label", "description", "component_type",
                                                             "options_json", "validation_regex"))
        redisplay["sensitive"] = "Y" if submitted["sensitive"] == "Y" else "N"
        # Padrao de parametro sensivel nunca volta ao HTML.
        redisplay["default_value"] = "" if redisplay["sensitive"] == "Y" else (submitted["default_value"] or "")
        if not data.get("can_regex"):
            redisplay.pop("validation_regex")
        data = dict(data, **redisplay)
        if not parameter_id:
            data["code"] = submitted["code"] or ""
        else:
            data["version"] = submitted["version"] or ""
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"kind": "error", "message": errors.get(admin_crud.GENERAL_FIELD)
                      or ui_helpers.message("form_errors")}
    return _form_page(ctx, data, errors)


def toggle_active():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    parameter_id = _text(request.post_vars.get("id"), 11)
    try:
        changed = service.toggle_active(ctx, _client_ip(), parameter_id, _text(request.post_vars.get("version"), 64))
        action = u"desativado" if changed["active"] == "N" else u"reativado"
        session.flash = {"kind": "success", "message": u"Parâmetro %s %s." % (changed["code"], action)}
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    except OperationDenied as exc:
        session.flash = {"kind": "error", "message": exc.message}
    except RepoConflict:
        session.flash = {"kind": "warning", "message": admin_crud.MSG_CONFLICT}
    except RepoError:
        _log.exception("falha ao alternar parametro (login=%s id=%r)", ctx["login"], parameter_id, extra={"action": _FUNC})
        session.flash = {"kind": "error", "message": _MSG_ACTION_FAILED}
    redirect(URL(c="admin_parameters", f="form", args=[parameter_id]))


def test_regex():
    # POST: a configuracao em edicao e o valor de teste nunca vao para a URL nem para o log de acesso.
    _require_method("POST")
    ctx = _require_func(_FUNC)
    response.headers["Cache-Control"] = "no-store"
    try:
        result = service.test_regex(ctx, _text(request.post_vars.get("id"), 11), _submitted(),
                                   _text(request.post_vars.get("test_value"), 1000))
    except RepoNotFound:
        response.status = 404
        return response.json({"ok": False, "error": u"Parâmetro não encontrado."})
    except AccessDenied:
        response.status = 403
        return response.json({"ok": False, "error": u"Acesso negado."})
    return response.json(result)
