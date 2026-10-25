# -*- coding: utf-8 -*-
"""Cadastro de perfis e matriz de permissoes (README §4.3, MANAGE_PROFILES). Padrao em docs/ADMIN_CRUD_PATTERN.md.

Regras ficam em modules/admin_profiles_service.py; CSRF e Origin de todo POST sao validados
em webapp/security.py. Nenhuma permissao e decidida no cliente: o POST da matriz e revalidado inteiro.
"""
from sss.services import admin_crud
from sss.services import admin_profiles_service as service
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

_FUNC = "MANAGE_PROFILES"
_SIZES = (20, 50, 100)
_MAX_IDS = 5000
_MSG_NOT_FOUND = u"Perfil não encontrado."
_MSG_LIST_FAILED = u"Não foi possível carregar os perfis. Tente novamente em instantes."
_MSG_TOGGLE_FAILED = u"Não foi possível alterar a situação do perfil. Tente novamente em instantes."
_MSG_MATRIX_FAILED = u"Não foi possível salvar a matriz. Tente novamente em instantes."
_JS_MATRIX = "js/app/matrix.js"


def _list(name):
    value = request.post_vars.get(name)
    if value is None:
        return []
    value = value if isinstance(value, list) else [value]
    return [v[:11] if isinstance(v, str) else v for v in value[:_MAX_IDS]]


def _form_page(ctx, data, errors=None):
    response.title = (u"Perfil %s — SSS" % data["name"]) if data.get("id") else u"Novo perfil — SSS"
    response.view = "admin_profiles/form.html"
    errors = errors or {}
    fields = [{"name": n, "error": errors.get(n)} for n in ("name", "description")]
    return dict(profile=data, errors=errors, general_error=errors.get(admin_crud.GENERAL_FIELD),
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
        _log.exception("falha ao listar perfis (login=%s)", ctx["login"], extra={"action": _FUNC})
        result = {"items": [], "total": 0, "page": 1, "size": size}
        error = _MSG_LIST_FAILED
    response.title = u"Perfis — SSS"
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
    profile_id = _text(request.post_vars.get("id"), 11)
    submitted = dict((c, _text(request.post_vars.get(c), 300)) for c in ("name", "description", "is_admin", "version"))
    try:
        saved_id, errors = service.save(ctx, _client_ip(), profile_id, submitted)
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    except RepoError:
        _log.exception("falha ao salvar perfil (login=%s id=%r)", ctx["login"], profile_id, extra={"action": _FUNC})
        saved_id, errors = None, {admin_crud.GENERAL_FIELD: admin_crud.MSG_FAILURE}
    if not errors:
        if not profile_id and saved_id:
            # Perfil novo nao faz nada sem permissoes: segue direto para a matriz (CR-018b).
            session.flash = {"kind": "success", "message": u"Perfil incluído. Agora marque o que ele pode fazer."}
            redirect(URL(c="admin_profiles", f="matrix", args=[saved_id]))
        session.flash = {"kind": "success", "message": u"Perfil salvo com sucesso."}
        redirect(URL(c="admin_profiles", f="index"))
    try:
        data = service.form(ctx, profile_id) if profile_id else service.form(ctx)
    except RepoError:
        data = {"id": None, "name": "", "description": "", "is_admin": "N", "active": "Y", "version": "",
                 "active_users": 0}
    if admin_crud.GENERAL_FIELD not in errors:
        data = dict(data, name=submitted["name"] or "", description=submitted["description"] or "",
                     is_admin="Y" if submitted["is_admin"] == "Y" else "N")
        if profile_id:
            data["version"] = submitted["version"] or ""
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"kind": "error", "message": errors.get(admin_crud.GENERAL_FIELD)
                      or ui_helpers.message("form_errors")}
    return _form_page(ctx, data, errors)


def toggle_active():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    profile_id = _text(request.post_vars.get("id"), 11)
    try:
        changed = service.toggle_active(ctx, _client_ip(), profile_id, _text(request.post_vars.get("version"), 64))
        action = u"desativado" if changed["active"] == "N" else u"reativado"
        session.flash = {"kind": "success", "message": u"Perfil %s %s." % (changed["name"], action)}
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    except OperationDenied as exc:
        session.flash = {"kind": "error", "message": exc.message}
    except RepoConflict:
        session.flash = {"kind": "warning", "message": admin_crud.MSG_CONFLICT}
    except RepoError:
        _log.exception("falha ao alternar perfil (login=%s id=%r)", ctx["login"], profile_id, extra={"action": _FUNC})
        session.flash = {"kind": "error", "message": _MSG_TOGGLE_FAILED}
    redirect(URL(c="admin_profiles", f="form", args=[profile_id]))


def who_can():
    """Quem pode o que (README §4.3.B.2): so leitura, por script ou por ambiente."""
    _require_method("GET", "HEAD")
    ctx = _require_func(_FUNC)
    try:
        data = service.who_can(ctx, _text(request.get_vars.get("script"), 11),
                                  _text(request.get_vars.get("environment"), 11))
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    response.title = u"Quem pode o quê — SSS"
    return dict(q=data)


def matrix():
    _require_method("GET", "HEAD")
    ctx = _require_func(_FUNC)
    try:
        data = service.matrix(ctx, _text(request.args(0), 11))
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    response.title = u"Permissões de %s — SSS" % data["profile"]["name"]
    response.sss_scripts = [_JS_MATRIX]
    return dict(matrix=data)


def save_matrix():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    profile_id = _text(request.post_vars.get("id"), 11)
    try:
        diff, errors = service.save_matrix(ctx, _client_ip(), profile_id, _list("funcs"), _list("ambs"),
                                            _list("scrs"), _text(request.post_vars.get("perm_version"), 11))
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except AccessDenied:
        _denied()
    except RepoError:
        _log.exception("falha ao salvar matriz (login=%s id=%r)", ctx["login"], profile_id, extra={"action": "PERM_UPDATE"})
        diff, errors = None, {admin_crud.GENERAL_FIELD: _MSG_MATRIX_FAILED}
    if errors:
        session.flash = {"kind": "error", "message": errors[admin_crud.GENERAL_FIELD]}
    elif diff:
        session.flash = {"kind": "success", "message": u"Permissões salvas: %s" % diff}
    else:
        session.flash = {"kind": "warning", "message": u"Nenhuma alteração para salvar."}
    redirect(URL(c="admin_profiles", f="matrix", args=[profile_id]))
