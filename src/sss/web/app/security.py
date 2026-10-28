# -*- coding: utf-8 -*-
"""Sessao, revalidacao, CSRF + Origin, cabecalhos de seguranca e guardas (README §4.2).

Era o models/10_security.py do web2py (CR-021e). ``before_request`` roda antes de toda action, na
mesma ordem de antes: valores da tela, sessao (expiracao e revalidacao, que podem mandar ao login),
token CSRF, tamanho do POST (413 sem ler o corpo) e Origin + CSRF. ``after_request`` poe os
cabecalhos de seguranca em toda resposta dinamica, inclusive de erro. As guardas sao as mesmas dos
controllers (CR-018f).
"""
import logging
import time
from typing import Any, Dict, Optional

from sss.config import app_context
from sss.services import auth_service
from sss.core import rbac
from sss.core import security
from sss.config import sss_config
from sss.config import sss_logging
from sss.ui import ui_helpers
from sss.ui import ui_menu
from sss.persistence.repo_errors import RepoUnavailable
from sss.web.framework import HTTP, Context, Markup, decode_path_info, escape, redirect

from . import context
from .context import URL, request, response, session

LOGIN = ("default", "login")
# CR-020d: folga do formulario multipart sobre o maior envio da tela de Entrada.
POST_MARGIN_BYTES = 65536
_SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # 'no-referrer' faz o navegador enviar "Origin: null" em POST de formulario (spec Fetch), o que
    # derruba a checagem de Origin; 'same-origin' omite o Referer para fora do site.
    "Referrer-Policy": "same-origin",
}


# O mesmo objeto que o sss_logging configura (logging.getLogger do nome); os handlers entram na
# subida, por log(). Os controllers o usam no import, sem precisar da configuracao carregada.
LOG = logging.getLogger("sss_web")


def log() -> logging.Logger:
    """Logger da aplicacao web, configurado na primeira chamada (uma vez por processo)."""
    return sss_logging.get_logger("sss_web", app_context.require_config())


def max_body_bytes() -> int:
    """Maior corpo de POST aceito: o maior envio da tela de Entrada mais a folga do multipart."""
    return app_context.require_config().web.input_upload_max_bytes + POST_MARGIN_BYTES


def secure_cookie(req: Any) -> bool:
    """Secure so quando a requisicao chega por HTTPS: sobre HTTP o navegador descartaria o
    cookie (README §4.2; CR-032, D11: o mesmo em DEV e PROD)."""
    return bool(req.is_https)


def path_info() -> str:
    """Caminho da requisicao em texto (o PATH_INFO do WSGI vem em latin-1)."""
    return decode_path_info(str(request.env.path_info or ""))


def client_ip() -> str:
    """IP do cliente (README §4.2): X-Forwarded-For so quando remote_addr e proxy confiavel."""
    return security.client_ip(request.env.remote_addr, request.env.http_x_forwarded_for,
                              app_context.require_config().web.trusted_proxies)


def csrf_field() -> Markup:
    """Campo oculto '_csrf' dos formularios POST (o mesmo HTML que o INPUT do web2py gerava)."""
    return Markup(f'<input name="_csrf" type="hidden" value="{escape(session.csrf_token)}" />')


# ---------------------------------------------------------------------- hooks


def before_request(ctx: Context) -> None:
    """Antes de toda action: liga a requisicao a thread e aplica sessao, CSRF e limites."""
    context.bind(ctx)
    cfg = app_context.require_config()
    response.env_label = sss_config.env_label()
    # Mesma versao do pacote e do log do agente (CR-022a; antes, um 0.1.0 fixo herdado do web2py).
    response.sss_version = sss_config.SSS_VERSION
    response.sss_menu = []
    _revalidate(cfg)
    if not session.csrf_token:
        session.csrf_token = security.generate_csrf_token()
    if request.method not in _SAFE_METHODS:
        _check_size()
        _check_origin_and_csrf(cfg)


def after_request(ctx: Context) -> None:  # pylint: disable=unused-argument
    """Cabecalhos de seguranca em toda resposta dinamica; no-store com usuario logado."""
    response.headers.update(SECURITY_HEADERS)
    if context.user():
        response.headers["Cache-Control"] = "no-store"


# Funcoes que sempre levantam HTTP anotam "-> None": o tipo "nunca retorna" do typing so existe
# a partir do 3.6.2, e o minimo do projeto e o 3.6.0 (AGENTS §2.1).
def _end_session(message: str) -> None:
    """Encerra a sessao e manda ao login com o aviso (sempre levanta o redirect)."""
    session.clear()
    session.csrf_token = security.generate_csrf_token()
    session.flash = {"kind": "warning", "message": message}
    redirect(URL(c=LOGIN[0], f=LOGIN[1]))


def _revalidate(cfg: Any) -> None:
    """Expiracao por inatividade e vida maxima (so log) e revalidacao no banco (README §4.2)."""
    if not session.user_id:
        return
    now = time.time()
    if security.is_session_expired(session.last_access, now, cfg.web.session_idle_timeout_s):
        log().info("sessao expirada por inatividade (login=%s)", session.login,
                   extra={"action": "SESSAO"})
        _end_session(ui_helpers.message("session_expired"))
    if security.is_session_expired(session.login_at, now, cfg.web.session_max_hours * 3600):
        log().info("sessao encerrada pela vida maxima (login=%s)", session.login,
                   extra={"action": "SESSAO"})
        _end_session(ui_helpers.message("session_max_age"))
    try:
        revalidated = auth_service.revalidate(session, client_ip())
    except RepoUnavailable as exc:
        log().exception("revalidacao de sessao indisponivel (usuario_id=%s caminho=%s)",
                        session.user_id, path_info(), extra={"action": "SESSAO"})
        raise HTTP(503) from exc
    if revalidated is None:
        _end_session("Seu acesso mudou e a sessão foi encerrada. Entre de novo para continuar.")
    context.set_user(revalidated)
    session.profile_id = revalidated["profile_id"]
    session.perm_version = revalidated["perm_version"]
    session.last_access = now
    response.sss_menu = ui_menu.build_menu(revalidated["features"], revalidated["is_admin"],
                                           (request.controller, request.function))


def _check_size() -> None:
    """CR-020d: corpo acima do maior envio permitido e recusado antes de ser lido."""
    raw = request.env.content_length or "0"
    try:
        size = int(raw)
    except ValueError:
        size = -1
    if size < 0 or size > max_body_bytes():
        log().warning("requisicao rejeitada (motivo=tamanho bytes=%s caminho=%s ip=%s)", raw,
                      path_info(), request.env.remote_addr, extra={"action": "CSRF"})
        raise HTTP(413)


def _allowed_origins(cfg: Any) -> list:
    """As allowed_origins mais o proprio Host da requisicao (CR-032, D11: igual em DEV e PROD)."""
    sources = list(cfg.web.allowed_origins)
    if request.env.http_host:
        sources.append(f"{request.env.wsgi_url_scheme}://{request.env.http_host}")
    return sources


def _reject(reason: str) -> None:
    source = request.env.http_origin or request.env.http_referer or ""
    log().warning("requisicao rejeitada (motivo=%s metodo=%s caminho=%s origem=%r ip=%s)",
                  reason, request.method, path_info(), source[:200], request.env.remote_addr,
                  extra={"action": "CSRF"})
    raise HTTP(403)


def _check_origin_and_csrf(cfg: Any) -> None:
    if not security.is_allowed_origin(request.env.http_origin, request.env.http_referer,
                                      _allowed_origins(cfg)):
        _reject("origem")
    token = request.post_vars.get("_csrf")
    if not isinstance(token, str) or not token:
        token = request.env.http_x_csrf_token
    if not security.validate_csrf_token(session.csrf_token, token):
        _reject("csrf")


# ---------------------------------------------------------------------- guardas (CR-018f)


def _current_target() -> Optional[str]:
    path = path_info()
    if request.env.query_string:
        path = f"{path}?{request.env.query_string}"
    return security.validate_next(path)


def require_login() -> Dict[str, Any]:
    """Guarda de autenticacao: sem sessao valida, vai ao login com 'next' local validado."""
    revalidated = context.user()
    if not revalidated:
        target = _current_target() if request.method in ("GET", "HEAD") else None
        redirect(URL(c=LOGIN[0], f=LOGIN[1], vars={"next": target} if target else {}))
        raise AssertionError("redirect nao retornou")  # pragma: no cover
    return revalidated


def require_func(code: str) -> Dict[str, Any]:
    """Guarda de autorizacao: exige login e a funcionalidade; sem ela, 403 com log WARN."""
    revalidated = require_login()
    if not rbac.has_feature(revalidated, code):
        log().warning("acesso negado (login=%s funcionalidade=%s caminho=%s ip=%s)",
                      # require_login nunca devolve None: sem usuario, levanta o redirect.
                      revalidated["login"],  # pylint: disable=unsubscriptable-object
                      code, path_info(), client_ip(), extra={"action": "RBAC"})
        denied()
    return revalidated


def require_method(*allowed: str) -> None:
    """405 quando o metodo HTTP nao e um dos aceitos pela action."""
    if request.method not in allowed:
        raise HTTP(405)


def denied() -> None:
    """403; a pagina de erro mostra a mensagem-padrao de sem permissao (README §2.4.2)."""
    raise HTTP(403)


def not_found(message: str) -> None:
    """404; fora do escopo tambem e 404, nunca 403 (a mensagem fica no log de quem chamou)."""
    raise HTTP(404, message)


def text(value: Any, limit: int) -> Optional[str]:
    """Ultimo valor de um parametro (repetido vira lista), cortado em ``limit`` so por memoria."""
    value = value[-1] if isinstance(value, list) and value else value
    return value[:limit] if isinstance(value, str) else None


def require_query() -> Dict[str, Any]:
    """Guarda da lista, do detalhe e do log dos tickets (README §4.3.C).

    Exige VIEW_LOGS ou EXEC_SCRIPT.
    """
    from sss.services import ticket_service  # pylint: disable=import-outside-toplevel
    revalidated = require_login()
    if not ticket_service.can_query(revalidated):
        log().warning("acesso negado (login=%s funcionalidade=VIEW_LOGS|EXEC_SCRIPT caminho=%s "
                      "ip=%s)",
                      # require_login nunca devolve None: sem usuario, levanta o redirect.
                      revalidated["login"],  # pylint: disable=unsubscriptable-object
                      path_info(), client_ip(), extra={"action": "RBAC"})
        denied()
    return revalidated
