# -*- coding: utf-8 -*-
"""Cadastro de usuarios (README §4.2, §4.3.B, MANAGE_USERS). Padrao em docs/ADMIN_CRUD_PATTERN.md.

Regras ficam em modules/admin_users_service.py; CSRF e Origin de todo POST sao validados em
models/10_security.py. Senhas sao retiradas de request.vars assim que lidas: o ticket de erro do
web2py grava as variaveis da requisicao.
"""
import admin_crud
import admin_users_service as service
import security
import ui_helpers
from admin_crud import AccessDenied, OperationDenied
from repo_errors import RepoConflict, RepoError, RepoNotFound

_FUNC = "MANAGE_USERS"
_SIZES = (20, 50, 100)
_PASSWORD_FIELDS = ("password", "confirmation")
_MSG_LIST_FAILED = u"Não foi possível carregar os usuários. Tente novamente em instantes."
_MSG_ACTION_FAILED = u"Não foi possível concluir a operação. Tente novamente em instantes."


def _require_method(*permitidos):
    if (request.env.request_method or "GET").upper() not in permitidos:
        raise HTTP(405, **response.headers)


def _denied():
    raise HTTP(403, u"Acesso negado.", **response.headers)


def _not_found():
    raise HTTP(404, u"Usuário não encontrado.", **response.headers)


def _text(value, limit):
    value = value[-1] if isinstance(value, list) and value else value
    return value[:limit] if isinstance(value, str) else None


def _strip_passwords():
    return security.strip_passwords((request.post_vars, request.vars), _PASSWORD_FIELDS)


def _int(value):
    return int(value) if isinstance(value, str) and value.isdigit() and len(value) <= 10 else None


def _form_page(ctx, data, errors=None, password_errors=None):
    response.title = (u"Usuário %s — SSS" % data["login"]) if data.get("id") else u"Novo usuário — SSS"
    response.view = "admin_users/form.html"
    errors = errors or {}
    fields = [{"name": n, "error": errors.get(n)} for n in ("login", "name", "profile_id", "password", "confirmation")]
    # Perfil de administrador so e oferecido a administrador (CR-008, E1), salvo o perfil atual.
    profiles = [p for p in service.profiles()
              if p["id"] == data.get("profile_id") or (p["active"] == "Y" and (ctx["is_admin"] or p["is_admin"] != "Y"))]
    return dict(user=data, errors=errors, general_error=errors.get(admin_crud.GENERAL_FIELD),
                password_errors=password_errors or {}, profiles=profiles,
                focus_field=ui_helpers.first_invalid_field(fields), password_help=service.POLICY_HELP,
                deactivation_warning=service.DEACTIVATION_WARNING)


def index():
    _require_method("GET", "HEAD")
    ctx = _require_func(_FUNC)
    filters = service.normalize_filters(request.get_vars)
    page = ui_helpers.sanitize_page(_text(request.get_vars.get("page"), 9))
    size = ui_helpers.sanitize_size(_text(request.get_vars.get("size"), 3), _SIZES)
    error = None
    profiles = []
    try:
        result = service.list_page(ctx, filters, page, size)
        profiles = service.profiles()
    except AccessDenied:
        _denied()
    except RepoError:
        _log.exception("falha ao listar usuarios (login=%s)", ctx["login"], extra={"action": _FUNC})
        result = {"items": [], "total": 0, "page": 1, "size": size}
        error = _MSG_LIST_FAILED
    response.title = u"Usuários — SSS"
    return dict(result=result, error=error, active_filters=filters, size=size, profiles=profiles,
                query_params=dict(filters, size=size))


def form():
    _require_method("GET", "HEAD")
    ctx = _require_func(_FUNC)
    try:
        data = service.form(ctx, _text(request.args(0), 11))
    except RepoNotFound:
        _not_found()
    except AccessDenied:
        _denied()
    return _form_page(ctx, data)


def save():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    passwords = _strip_passwords()
    user_id = _text(request.post_vars.get("id"), 11)
    submitted = dict((c, _text(request.post_vars.get(c), 300)) for c in ("login", "name", "profile_id", "version"))
    submitted.update(passwords)
    try:
        _saved, errors = service.save(ctx, _client_ip(), user_id, submitted)
    except RepoNotFound:
        _not_found()
    except AccessDenied:
        _denied()
    except RepoError:
        _log.exception("falha ao salvar usuario (login=%s id=%r)", ctx["login"], user_id, extra={"action": _FUNC})
        errors = {admin_crud.GENERAL_FIELD: admin_crud.MSG_FAILURE}
    if not errors:
        session.flash = {"kind": "success", "message": u"Usuário salvo com sucesso."}
        redirect(URL(c="admin_users", f="index"))
    try:
        data = service.form(ctx, user_id) if user_id else service.form(ctx)
    except RepoError:
        data = {"id": None, "login": "", "name": "", "profile_id": None, "active": "Y", "version": "",
                 "locked": False, "locked_until": None, "failed_attempts": 0, "own": False}
    if admin_crud.GENERAL_FIELD not in errors:
        data = dict(data, name=submitted["name"] or "", profile_id=_int(submitted["profile_id"]))
        if not user_id:
            data["login"] = submitted["login"] or ""
        else:
            data["version"] = submitted["version"] or ""
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"kind": "error", "message": errors.get(admin_crud.GENERAL_FIELD)
                      or ui_helpers.message("form_errors")}
    return _form_page(ctx, data, errors)


def toggle_active():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    user_id = _text(request.post_vars.get("id"), 11)
    try:
        changed = service.toggle_active(ctx, _client_ip(), user_id, _text(request.post_vars.get("version"), 64))
        action = u"desativado" if changed["active"] == "N" else u"reativado"
        session.flash = {"kind": "success", "message": u"Usuário %s %s." % (changed["login"], action)}
    except RepoNotFound:
        _not_found()
    except AccessDenied:
        _denied()
    except OperationDenied as exc:
        session.flash = {"kind": "error", "message": exc.message}
    except RepoConflict:
        session.flash = {"kind": "warning", "message": admin_crud.MSG_CONFLICT}
    except RepoError:
        _log.exception("falha ao alternar usuario (login=%s id=%r)", ctx["login"], user_id, extra={"action": _FUNC})
        session.flash = {"kind": "error", "message": _MSG_ACTION_FAILED}
    redirect(URL(c="admin_users", f="form", args=[user_id]))


def reset_password():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    passwords = _strip_passwords()
    user_id = _text(request.post_vars.get("id"), 11)
    try:
        errors = service.reset_password(ctx, _client_ip(), user_id, passwords["password"], passwords["confirmation"])
    except RepoNotFound:
        _not_found()
    except AccessDenied:
        _denied()
    except OperationDenied as exc:
        session.flash = {"kind": "error", "message": exc.message}
        redirect(URL(c="admin_users", f="form", args=[user_id]))
    except RepoError:
        _log.exception("falha ao redefinir senha (login=%s id=%r)", ctx["login"], user_id, extra={"action": _FUNC})
        session.flash = {"kind": "error", "message": _MSG_ACTION_FAILED}
        redirect(URL(c="admin_users", f="form", args=[user_id]))
    if not errors:
        session.flash = {"kind": "success", "message": u"Senha redefinida. Tentativas e bloqueio foram zerados."}
        redirect(URL(c="admin_users", f="form", args=[user_id]))
    response.flash = {"kind": "error", "message": u"A nova senha não foi aceita. Veja o campo destacado."}
    return _form_page(ctx, service.form(ctx, user_id), password_errors=errors)


def unlock():
    _require_method("POST")
    ctx = _require_func(_FUNC)
    user_id = _text(request.post_vars.get("id"), 11)
    try:
        changed = service.unlock(ctx, _client_ip(), user_id)
        session.flash = {"kind": "success", "message": u"Usuário %s desbloqueado." % changed["login"]}
    except RepoNotFound:
        _not_found()
    except AccessDenied:
        _denied()
    except OperationDenied as exc:
        session.flash = {"kind": "error", "message": exc.message}
    except RepoError:
        _log.exception("falha ao desbloquear (login=%s id=%r)", ctx["login"], user_id, extra={"action": _FUNC})
        session.flash = {"kind": "error", "message": _MSG_ACTION_FAILED}
    redirect(URL(c="admin_users", f="form", args=[user_id]))
