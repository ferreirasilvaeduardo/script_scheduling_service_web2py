# -*- coding: utf-8 -*-
"""Cadastro de ambientes (README §4.3.D MANAGE_ENVIRONMENTS). Padrao em docs/ADMIN_CRUD_PATTERN.md.

Regras ficam em modules/admin_environments_service.py; CSRF e Origin de todo POST sao validados
em app/security.py.
"""
from sss.services import admin_crud
from sss.services import admin_environments_service as service
from sss.ui import ui_helpers
from sss.services.admin_crud import AccessDenied
from sss.persistence.repo_errors import RepoConflict, RepoError, RepoNotFound

from sss.web.app import security as _security
from sss.web.app.context import URL, redirect, request, response, session
from sss.web.app.security import client_ip as _client_ip
from sss.web.app.security import denied as _denied
from sss.web.app.security import not_found as _not_found
from sss.web.app.security import require_func as _require_func
from sss.web.app.security import require_method as _require_method
from sss.web.app.security import text as _text

_log = _security.LOG

_FUNC = "MANAGE_ENVIRONMENTS"
_SIZES = (20, 50, 100)
_MSG_NOT_FOUND = u"Ambiente não encontrado."
_MSG_LIST_FAILED = u"Não foi possível carregar os ambientes. Tente novamente em instantes."
_MSG_TOGGLE_FAILED = u"Não foi possível alterar a situação do ambiente. Tente novamente em instantes."


def _form_page(ctx, data, errors=None):
    response.title = (u"Ambiente %s — SSS" % data["name"]) if data.get("id") else u"Novo ambiente — SSS"
    response.view = "admin_environments/form.html"
    errors = errors or {}
    fields = [{"name": n, "error": errors.get(n)} for n in ("name", "description", "connection")]
    return dict(env=data, errors=errors, general_error=errors.get(admin_crud.GENERAL_FIELD),
                focus_field=ui_helpers.first_invalid_field(fields),
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
        _log.exception("falha ao listar ambientes (login=%s)", ctx["login"], extra={"action": _FUNC})
        result = {"items": [], "total": 0, "page": 1, "size": size}
        error = _MSG_LIST_FAILED
    response.title = u"Ambientes — SSS"
    return dict(result=result, error=error, active_filters=filters, size=size,
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
    environment_id = _text(request.post_vars.get("id"), 11)
    submitted = dict((c, _text(request.post_vars.get(c), 300)) for c in ("name", "description", "connection", "is_production",
                                                                         "version"))
    try:
        saved_id, errors = service.save(ctx, _client_ip(), environment_id, submitted)
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    except RepoError:
        _log.exception("falha ao salvar ambiente (login=%s id=%r)", ctx["login"], environment_id, extra={"action": _FUNC})
        saved_id, errors = None, {admin_crud.GENERAL_FIELD: admin_crud.MSG_FAILURE}
    if not errors:
        session.flash = {"kind": "success", "message": u"Ambiente salvo com sucesso."}
        redirect(URL(c="admin_environments", f="index"))
    # Reapresenta o que foi digitado; na edicao o nome e a versao continuam os do registro.
    try:
        data = service.form(ctx, environment_id) if environment_id else service.form(ctx)
    except RepoError:
        data = {"id": None, "name": "", "is_production": "N", "active": "Y", "version": "", "active_schedules": 0,
                "homologated_scripts": 0}
    if admin_crud.GENERAL_FIELD not in errors:
        connection = submitted["connection"] or ""
        # Nunca devolve ao HTML um DSN com credencial digitado por engano.
        data = dict(data, description=submitted["description"] or "", connection="" if "@" in connection else connection,
                    is_production="Y" if submitted["is_production"] == "Y" else "N")
        if not environment_id:
            data["name"] = submitted["name"] or ""
        else:
            data["version"] = submitted["version"] or ""
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"kind": "error", "message": errors.get(admin_crud.GENERAL_FIELD)
                      or ui_helpers.message("form_errors")}
    return _form_page(ctx, data, errors)


def toggle_active():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    environment_id = _text(request.post_vars.get("id"), 11)
    try:
        changed = service.toggle_active(ctx, _client_ip(), environment_id, _text(request.post_vars.get("version"), 64))
        if changed["active"] == "N":
            session.flash = {"kind": "success", "message": u"Ambiente %s desativado." % changed["name"]}
        else:
            session.flash = {"kind": "success", "message": u"Ambiente %s reativado." % changed["name"]}
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    except RepoConflict:
        session.flash = {"kind": "warning", "message": admin_crud.MSG_CONFLICT}
    except RepoError:
        _log.exception("falha ao alternar ambiente (login=%s id=%r)", ctx["login"], environment_id, extra={"action": _FUNC})
        session.flash = {"kind": "error", "message": _MSG_TOGGLE_FAILED}
    redirect(URL(c="admin_environments", f="form", args=[environment_id]))
