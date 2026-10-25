# -*- coding: utf-8 -*-
"""Cadastro de scripts, homologacao e vinculo de parametros (README §4.3.A, §6.3, §8.5, MANAGE_SCRIPTS).

Padrao em docs/ADMIN_CRUD_PATTERN.md. Regras ficam em modules/admin_scripts_service.py; CSRF e Origin
de todo POST sao validados em webapp/security.py. Listas enviadas pelo cliente sao revalidadas inteiras.
"""
from sss.services import admin_crud
from sss.services import admin_scripts_service as service
from sss.platform import path_guard
from sss.ui import ui_helpers
from sss.services.admin_crud import AccessDenied, OperationDenied
from sss.persistence.repo_errors import RepoConflict, RepoError, RepoNotFound

from webapp import security as _security
from webapp.context import URL, redirect, request, response, session
from webapp.security import client_ip as _client_ip
from webapp.security import denied as _denied
from webapp.security import not_found as _not_found
from webapp.security import require_func as _require_func
from webapp.security import require_method as _require_method
from webapp.security import text as _text

_log = _security.LOG

_FUNC = "MANAGE_SCRIPTS"
_SIZES = (20, 50, 100)
_FIELDS = ("name", "description", "script_group", "category", "stage", "interpreter", "path_file", "param_type",
           "max_parallel_env", "timeout_s", "version")
_JS = "js/app/scripts_admin.js"
_MAX_JSON = 50000
_MAX_IDS = 1000
_MSG_NOT_FOUND = u"Script não encontrado."
_MSG_LIST_FAILED = u"Não foi possível carregar os scripts. Tente novamente em instantes."
_MSG_ACTION_FAILED = u"Não foi possível concluir a operação. Tente novamente em instantes."


def _empty_form(ctx):
    # Fallback quando nem o formulario pode ser lido (falha de repositorio): so os campos que a view usa.
    return {"id": None, "name": "", "description": "", "script_group": "", "category": "", "stage": "",
            "interpreter": path_guard.ALLOWLIST[0], "path_file": "",
            "param_type": "NAMED",
            "max_parallel_env": 1, "timeout_s": "", "active": "Y", "version": "", "active_schedules": 0,
            "validation_note": service.VALIDATION_NOTE}


def _form_page(ctx, data, errors=None):
    response.title = (u"Script %s — SSS" % data["name"]) if data.get("id") else u"Novo script — SSS"
    response.view = "admin_scripts/form.html"
    errors = errors or {}
    fields = [{"name": n, "error": errors.get(n)} for n in ("name", "description", "script_group", "category", "stage",
                                                          "interpreter", "path_file", "param_type",
                                                          "max_parallel_env", "timeout_s")]
    return dict(scr=data, errors=errors, general_error=errors.get(admin_crud.GENERAL_FIELD), interpreters=service.INTERPRETER_LABELS,
                param_types=service.PARAM_TYPE_LABELS, focus_field=ui_helpers.first_invalid_field(fields),
                deactivation_warning=service.DEACTIVATION_WARNING)


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
        _log.exception("falha ao listar scripts (login=%s)", ctx["login"], extra={"action": _FUNC})
        result = {"items": [], "total": 0, "page": 1, "size": size}
        error = _MSG_LIST_FAILED
    response.title = u"Scripts — SSS"
    return dict(result=result, error=error, active_filters=filters, size=size, interpreters=service.INTERPRETER_LABELS,
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


def save():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    script_id = _text(request.post_vars.get("id"), 11)
    # Teto acima do maior limite do service (path_file: 500), para que o excesso seja recusado (AGENTS §3.4).
    submitted = dict((c, _text(request.post_vars.get(c), 600)) for c in _FIELDS)
    warning = None
    try:
        saved_id, errors, warning = service.save(ctx, _client_ip(), script_id, submitted)
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    except OperationDenied as exc:
        saved_id, errors = None, {admin_crud.GENERAL_FIELD: str(exc)}
    except RepoError:
        _log.exception("falha ao salvar script (login=%s id=%r)", ctx["login"], script_id, extra={"action": _FUNC})
        saved_id, errors = None, {admin_crud.GENERAL_FIELD: admin_crud.MSG_FAILURE}
    if not errors:
        message = u"Script salvo com sucesso." + (u" " + warning if warning else u"")
        session.flash = {"kind": "warning" if warning else "success", "message": message}
        redirect(URL(c="admin_scripts", f="form", args=[saved_id]))
    try:
        data = service.form(ctx, script_id) if script_id else service.form(ctx)
    except RepoError:
        data = _empty_form(ctx)
    if admin_crud.GENERAL_FIELD not in errors:
        data = dict(data, **dict((c, submitted[c] or "") for c in _FIELDS if c != "version"))
        if script_id:
            data["version"] = submitted["version"] or ""
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"kind": "error", "message": errors.get(admin_crud.GENERAL_FIELD)
                      or ui_helpers.message("form_errors")}
    return _form_page(ctx, data, errors)


def toggle_active():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    script_id = _text(request.post_vars.get("id"), 11)
    try:
        changed = service.toggle_active(ctx, _client_ip(), script_id, _text(request.post_vars.get("version"), 64))
        action = u"desativado" if changed["active"] == "N" else u"reativado"
        session.flash = {"kind": "success", "message": u"Script %s %s." % (changed["name"], action)}
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    except OperationDenied as exc:
        session.flash = {"kind": "error", "message": exc.message}
    except RepoConflict:
        session.flash = {"kind": "warning", "message": admin_crud.MSG_CONFLICT}
    except RepoError:
        _log.exception("falha ao alternar script (login=%s id=%r)", ctx["login"], script_id, extra={"action": _FUNC})
        session.flash = {"kind": "error", "message": _MSG_ACTION_FAILED}
    redirect(URL(c="admin_scripts", f="form", args=[script_id]))


def homologation():
    _require_method("GET", "HEAD")
    ctx = _require_func(_FUNC)
    try:
        data = service.homologation(ctx, _text(request.args(0), 11))
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    response.title = u"Homologação de %s — SSS" % data["script"]["name"]
    response.sss_scripts = [_JS]
    return dict(homologation=data)


def save_homologation():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    script_id = _text(request.post_vars.get("id"), 11)
    ids = request.post_vars.get("environments")
    ids = (ids if isinstance(ids, list) else ([] if ids is None else [ids]))[:_MAX_IDS]
    try:
        diff, errors = service.save_homologation(ctx, _client_ip(), script_id, ids,
                                                 _text(request.post_vars.get("version"), 64))
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    except RepoError:
        _log.exception("falha ao salvar homologacao (login=%s id=%r)", ctx["login"], script_id, extra={"action": _FUNC})
        diff, errors = None, {admin_crud.GENERAL_FIELD: _MSG_ACTION_FAILED}
    if errors:
        session.flash = {"kind": "error", "message": errors[admin_crud.GENERAL_FIELD]}
    elif diff:
        session.flash = {"kind": "success", "message": u"Homologação salva: %s" % diff}
    else:
        session.flash = {"kind": "warning", "message": u"Nenhuma alteração para salvar."}
    redirect(URL(c="admin_scripts", f="homologation", args=[script_id]))


def parameters():
    _require_method("GET", "HEAD")
    ctx = _require_func(_FUNC)
    try:
        data = service.parameters(ctx, _text(request.args(0), 11))
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    response.title = u"Parâmetros de %s — SSS" % data["script"]["name"]
    response.sss_scripts = [_JS]
    return dict(links_page=data)


def save_parameters():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    script_id = _text(request.post_vars.get("id"), 11)
    try:
        description, errors = service.save_parameters(ctx, _client_ip(), script_id,
                                                     _text(request.post_vars.get("links_json"), _MAX_JSON),
                                                     _text(request.post_vars.get("version"), 64))
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    except RepoError:
        _log.exception("falha ao salvar vinculos (login=%s id=%r)", ctx["login"], script_id, extra={"action": _FUNC})
        description, errors = None, {admin_crud.GENERAL_FIELD: _MSG_ACTION_FAILED}
    if errors:
        message = errors.get(admin_crud.GENERAL_FIELD) or u" ".join(sorted(errors.values()))
        session.flash = {"kind": "error", "message": message}
    elif description:
        try:
            warning = service.rules_warning(ctx, script_id)
        except RepoError:
            # O que foi salvo continua valendo; so o aviso deixa de aparecer.
            _log.exception("falha ao conferir as regras afetadas (login=%s id=%r)", ctx["login"], script_id,
                           extra={"action": _FUNC})
            warning = None
        session.flash = {"kind": "warning" if warning else "success",
                         "message": u"Parâmetros salvos: %s" % description + (u" " + warning if warning else u"")}
    else:
        session.flash = {"kind": "warning", "message": u"Nenhuma alteração para salvar."}
    redirect(URL(c="admin_scripts", f="parameters", args=[script_id]))


def preview():
    # POST: a configuracao em edicao (e eventuais valores sigilosos) nunca vai para a URL.
    _require_method("POST")
    ctx = _require_func(_FUNC)
    response.headers["Cache-Control"] = "no-store"
    links_json = request.post_vars.get("links_json")
    try:
        result = service.preview(ctx, _text(request.post_vars.get("id"), 11),
                                   _text(links_json, _MAX_JSON) if links_json is not None else None)
    except RepoNotFound:
        response.status = 404
        return response.json({"argv": None, "errors": {admin_crud.GENERAL_FIELD: u"Script não encontrado."}})
    except AccessDenied:
        response.status = 403
        return response.json({"argv": None, "errors": {admin_crud.GENERAL_FIELD: u"Acesso negado."}})
    return response.json(result)
