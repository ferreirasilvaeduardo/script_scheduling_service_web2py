# -*- coding: utf-8 -*-
"""Sessao, revalidacao, guardas de acesso, CSRF + Origin, cabecalhos de seguranca e mascaramento.

Roda antes de qualquer controller (README §4.2, AGENTS §3.4).
"""
import io
import time

import auth_service
import masking
import rbac
import security
import sss_config
import sss_logging
import ui_helpers
import ui_menu
from repo_errors import RepoUnavailable

_cfg = current.sss_cfg
_secrets = sss_config.get_secrets("sss_web")
_log = sss_logging.get_logger("sss_web", _cfg)
masking.install_filter_on_handlers()

response.headers.update({
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # 'no-referrer' faz o navegador enviar "Origin: null" em POST de formulario (spec Fetch),
    # o que derruba a checagem de Origin abaixo; 'same-origin' omite o Referer para fora do site.
    "Referrer-Policy": "same-origin",
})

# O web2py recria o cookie de dados da sessao sem HttpOnly/Secure apos o controller;
# o container de cookies aplica os atributos em toda atribuicao.
_cookie_secure = not (_cfg.app.sss_env == "DEV" and not request.is_https)
_cookies = security.SecureCookies(secure=_cookie_secure)
_cookies.adopt(response.cookies)
response.cookies = _cookies

# O secure_loads deste web2py exige bytes, mas o cookie chega como str (defeito no Python 3).
security.adapt_session_cookie(request.cookies, "session_data_%s" % request.application.lower())
session.connect(request, response, cookie_key=_secrets.cookie_key)

_LOGIN_URL = ("default", "login")


def _end_session(message):
    session.clear()
    session.csrf_token = security.generate_csrf_token()
    session.flash = {"kind": "warning", "message": message}
    redirect(URL(c=_LOGIN_URL[0], f=_LOGIN_URL[1]))


current.sss_ctx = None
if session.user_id:
    _now = time.time()
    if security.is_session_expired(session.last_access, _now, _cfg.web.session_idle_timeout_s):
        # Expiracao por inatividade: so log, sem auditoria (README §4.2).
        _log.info("sessao expirada por inatividade (login=%s)", session.login, extra={"action": "SESSAO"})
        _end_session(ui_helpers.message("session_expired"))
    if security.is_session_expired(session.login_at, _now, _cfg.web.session_max_hours * 3600):
        # Vida maxima desde o login (CR-008, E2), mesmo com uso continuo: so log.
        _log.info("sessao encerrada pela vida maxima (login=%s)", session.login, extra={"action": "SESSAO"})
        _end_session(ui_helpers.message("session_max_age"))
    try:
        _ctx = auth_service.revalidate(session, security.client_ip(
            request.env.remote_addr, request.env.http_x_forwarded_for, _cfg.web.trusted_proxies))
    except RepoUnavailable:
        _log.exception("revalidacao de sessao indisponivel (usuario_id=%s caminho=%s)",
                       session.user_id, request.env.path_info, extra={"action": "SESSAO"})
        raise HTTP(503)
    if _ctx is None:
        _end_session(u"Seu acesso mudou e a sessão foi encerrada. Entre de novo para continuar.")
    current.sss_ctx = _ctx
    session.profile_id = _ctx["profile_id"]
    session.perm_version = _ctx["perm_version"]
    session.last_access = _now
    response.headers["Cache-Control"] = "no-store"
    response.sss_menu = ui_menu.build_menu(
        _ctx["features"], _ctx["is_admin"], (request.controller, request.function))

if not session.csrf_token:
    session.csrf_token = security.generate_csrf_token()


def csrf_field():
    """Campo oculto '_csrf' para formularios POST."""
    return INPUT(_type="hidden", _name="_csrf", _value=session.csrf_token)


def _allowed_origins():
    sources = list(_cfg.web.allowed_origins)
    if _cfg.app.sss_env == "DEV" and request.env.http_host:
        sources.append("%s://%s" % (request.env.wsgi_url_scheme, request.env.http_host))
    return sources


def _reject(reason):
    source = request.env.http_origin or request.env.http_referer or ""
    _log.warning(
        "requisicao rejeitada (motivo=%s metodo=%s caminho=%s origem=%r ip=%s)",
        reason, request.env.request_method, request.env.path_info, source[:200],
        request.env.remote_addr, extra={"action": "CSRF"},
    )
    raise HTTP(403, u"Requisição recusada.", **response.headers)


# Reprocessamento de routes_onerror reaproveita o environ (metodo e corpo ja consumido);
# a chave nao pode ser injetada pelo cliente, pois cabecalhos chegam com prefixo HTTP_.
_rerouting_error = bool(request.env.get("__routes_onerror__"))
if _rerouting_error:
    # Sem isto, o web2py tentaria ler de novo o wsgi.input pelo CONTENT_LENGTH herdado e bloquearia.
    request._body = io.BytesIO()

if (request.env.request_method or "GET").upper() not in ("GET", "HEAD", "OPTIONS") \
        and not _rerouting_error:
    if not security.is_allowed_origin(request.env.http_origin, request.env.http_referer, _allowed_origins()):
        _reject("origem")
    _token = request.post_vars.get("_csrf")
    if not isinstance(_token, str) or not _token:
        _token = request.env.http_x_csrf_token
    if not security.validate_csrf_token(session.csrf_token, _token):
        _reject("csrf")


def _client_ip():
    """IP do cliente (README §4.2): X-Forwarded-For so quando remote_addr e proxy confiavel."""
    return security.client_ip(request.env.remote_addr, request.env.http_x_forwarded_for,
                              _cfg.web.trusted_proxies)


def _current_target():
    path = request.env.path_info or ""
    if request.env.query_string:
        path = "%s?%s" % (path, request.env.query_string)
    return security.validate_next(path)


def _require_login():
    """Guarda de autenticacao: sem sessao valida, redireciona ao login com 'next' local validado."""
    ctx = current.sss_ctx
    if ctx:
        return ctx
    target = None
    if (request.env.request_method or "GET").upper() in ("GET", "HEAD"):
        target = _current_target()
    redirect(URL(c=_LOGIN_URL[0], f=_LOGIN_URL[1], vars={"next": target} if target else {}))


def _require_func(code):
    """Guarda de autorizacao: exige login e a funcionalidade; sem ela, 403 com log WARN."""
    ctx = _require_login()
    if not rbac.has_feature(ctx, code):
        _log.warning(
            "acesso negado (login=%s funcionalidade=%s caminho=%s ip=%s)",
            ctx["login"], code, request.env.path_info, _client_ip(), extra={"action": "RBAC"},
        )
        raise HTTP(403, u"Acesso negado.", **response.headers)
    return ctx
