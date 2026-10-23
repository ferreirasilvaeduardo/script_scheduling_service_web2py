# -*- coding: utf-8 -*-
"""Painel inicial, login e logout (README §4.2). CSRF e Origin de todo POST sao validados em models/10_security.py."""
import time

from gluon import current

import schedules_service
import agents_service
import auth_service
import permissions_service
import rbac
import security
import ticket_service
import ui_helpers
from repo_errors import RepoError

_MSG_CARD_FAILED = u"Não foi possível carregar este quadro. Tente novamente em instantes."


def _post_text(name, limit):
    value = request.post_vars.get(name)
    if not isinstance(value, str):
        return ""
    return value[:limit]


def _card(ctx, name, func):
    """Executa a consulta de um cartao; falha de repositorio vira mensagem no proprio cartao."""
    try:
        return func(), None
    except RepoError:
        _log.exception("falha ao montar o cartao %s do painel inicial (login=%s)", name, ctx["login"],
                       extra={"action": "PAINEL"})
        return None, _MSG_CARD_FAILED


def index():
    ctx = _require_login()
    response.title = u"Início — SSS"
    cards = {}
    # Cada cartao so existe para quem tem a funcionalidade (F6.1); o escopo e o das telas de origem.
    if ticket_service.can_query(ctx):
        cards["tickets"] = _card(ctx, "tickets", lambda: ticket_service.home_summary(ctx))
    if rbac.has_feature(ctx, "MANAGE_SCHEDULES"):
        cards["schedules"] = _card(
            ctx, "schedules", lambda: schedules_service.list_page(ctx, {"active": "Y"}, 1, 5)["items"])
    if rbac.has_feature(ctx, "VIEW_AUDIT"):
        cards["agents"] = _card(ctx, "agents", lambda: agents_service.dashboard(ctx))
    return dict(ctx=ctx, menu=response.sss_menu, cards=cards)


def login():
    method = (request.env.request_method or "GET").upper()
    if method not in ("GET", "HEAD", "POST"):
        raise HTTP(405)
    response.title = u"Entrar — SSS"
    target = security.validate_next(request.vars.get("next"))
    if current.sss_ctx:
        redirect(target or URL(c="default", f="index"))

    message = None
    typed_login = ""
    if method == "POST":
        typed_login = _post_text("login", 30).strip()
        password = security.strip_passwords((request.post_vars, request.vars), ("password",))["password"]
        ctx, message = auth_service.authenticate(typed_login, password, _client_ip())
        if ctx is not None:
            # Em sessao por cookie, renew() apenas limpa: o cookie e regravado com conteudo novo.
            session.renew(clear_session=True)
            session.csrf_token = security.generate_csrf_token()
            session.user_id = ctx["user_id"]
            session.login = ctx["login"]
            session.profile_id = ctx["profile_id"]
            session.perm_version = ctx["perm_version"]
            session.session_epoch = ctx["session_epoch"]
            session.last_access = session.login_at = time.time()
            redirect(target or URL(c="default", f="index"))
    return dict(message=message, typed_login=typed_login, next_url=target or "")


def logout():
    if (request.env.request_method or "GET").upper() != "POST":
        raise HTTP(405)
    if current.sss_ctx:
        auth_service.logout(current.sss_ctx, _client_ip())
    session.clear()
    session.csrf_token = security.generate_csrf_token()
    session.flash = {"kind": "success", "message": u"Você saiu do sistema."}
    redirect(URL(c="default", f="login"))


_MY_PASSWORD_FIELDS = ("current_password", "new_password", "confirmation")


def permissions():
    """O que eu posso fazer (README §4.3.E): so leitura, para qualquer usuario logado."""
    if (request.env.request_method or "GET").upper() not in ("GET", "HEAD"):
        raise HTTP(405, **response.headers)
    ctx = _require_login()
    response.title = u"O que eu posso fazer — SSS"
    try:
        data = permissions_service.build(ctx)
        error = None
    except RepoError:
        _log.exception("falha ao montar permissoes (login=%s)", ctx["login"], extra={"action": "PERMISSOES"})
        data, error = None, ui_helpers.message("internal_error")
    return dict(data=data, error=error)


def my_password():
    method = (request.env.request_method or "GET").upper()
    if method not in ("GET", "HEAD", "POST"):
        raise HTTP(405, **response.headers)
    ctx = _require_login()
    response.title = u"Minha senha — SSS"
    errors = {}
    if method == "POST":
        passwords = security.strip_passwords((request.post_vars, request.vars), _MY_PASSWORD_FIELDS)
        result, errors = auth_service.change_password(ctx, _client_ip(), passwords["current_password"], passwords["new_password"],
                                                     passwords["confirmation"])
        if result == "LOCKED":
            session.clear()
            session.csrf_token = security.generate_csrf_token()
            session.flash = {"kind": "warning", "message": auth_service.lock_message()}
            redirect(URL(c="default", f="login"))
        if result == "OK":
            # Nova senha, nova sessao: o cookie e regravado com conteudo novo e outro token CSRF.
            session.renew(clear_session=True)
            session.csrf_token = security.generate_csrf_token()
            session.user_id = ctx["user_id"]
            session.login = ctx["login"]
            session.profile_id = ctx["profile_id"]
            session.perm_version = ctx["perm_version"]
            # A troca incrementou session_epoch (CR-008, E2): as outras sessoes caem, esta continua.
            session.session_epoch = auth_service.session_epoch(ctx["user_id"])
            session.last_access = session.login_at = time.time()
            session.flash = {"kind": "success", "message": u"Senha alterada com sucesso."}
            redirect(URL(c="default", f="index"))
        response.flash = {"kind": "error", "message": u"A senha não foi alterada. Veja os campos destacados."}
    fields = [{"name": n, "error": errors.get(n)} for n in _MY_PASSWORD_FIELDS]
    return dict(errors=errors, focus_field=ui_helpers.first_invalid_field(fields),
                password_help=u"Mínimo de %d caracteres. A senha nunca é exibida nem registrada." % security.PASSWORD_MIN)
