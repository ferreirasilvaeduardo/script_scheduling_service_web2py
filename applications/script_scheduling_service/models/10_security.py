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
from repo_errors import RepoIndisponivel

_cfg = current.sss_cfg
_segredos = sss_config.obter_segredos("sss_web")
_log = sss_logging.obter_logger("sss_web", _cfg)
masking.instalar_filtro_em_handlers()

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
_cookies = security.CookiesSeguros(secure=_cookie_secure)
_cookies.adotar(response.cookies)
response.cookies = _cookies

# O secure_loads deste web2py exige bytes, mas o cookie chega como str (defeito no Python 3).
security.adaptar_cookie_sessao(request.cookies, "session_data_%s" % request.application.lower())
session.connect(request, response, cookie_key=_segredos.cookie_key)

_URL_LOGIN = ("default", "login")


def _encerrar_sessao(mensagem):
    session.clear()
    session.csrf_token = security.gerar_token_csrf()
    session.flash = {"tipo": "aviso", "mensagem": mensagem}
    redirect(URL(c=_URL_LOGIN[0], f=_URL_LOGIN[1]))


current.sss_ctx = None
if session.usuario_id:
    _agora = time.time()
    if security.sessao_expirada(session.ultimo_acesso, _agora, _cfg.web.session_idle_timeout_s):
        # Expiracao por inatividade: so log, sem auditoria (README §4.2).
        _log.info("sessao expirada por inatividade (login=%s)", session.login, extra={"acao": "SESSAO"})
        _encerrar_sessao(ui_helpers.mensagem("sessao_expirada"))
    if security.sessao_expirada(session.login_em, _agora, _cfg.web.sessao_max_horas * 3600):
        # Vida maxima desde o login (CR-008, E2), mesmo com uso continuo: so log.
        _log.info("sessao encerrada pela vida maxima (login=%s)", session.login, extra={"acao": "SESSAO"})
        _encerrar_sessao(ui_helpers.mensagem("sessao_max"))
    try:
        _ctx = auth_service.revalidar(session, security.ip_origem(
            request.env.remote_addr, request.env.http_x_forwarded_for, _cfg.web.trusted_proxies))
    except RepoIndisponivel:
        _log.exception("revalidacao de sessao indisponivel (usuario_id=%s caminho=%s)",
                       session.usuario_id, request.env.path_info, extra={"acao": "SESSAO"})
        raise HTTP(503)
    if _ctx is None:
        _encerrar_sessao(u"Seu acesso mudou e a sessão foi encerrada. Entre de novo para continuar.")
    current.sss_ctx = _ctx
    session.perfil_id = _ctx["perfil_id"]
    session.perm_versao = _ctx["perm_versao"]
    session.ultimo_acesso = _agora
    response.headers["Cache-Control"] = "no-store"
    response.sss_menu = ui_menu.montar_menu(
        _ctx["funcionalidades"], _ctx["is_admin"], (request.controller, request.function))

if not session.csrf_token:
    session.csrf_token = security.gerar_token_csrf()


def csrf_campo():
    """Campo oculto '_csrf' para formularios POST."""
    return INPUT(_type="hidden", _name="_csrf", _value=session.csrf_token)


def _origens_permitidas():
    origens = list(_cfg.web.allowed_origins)
    if _cfg.app.sss_env == "DEV" and request.env.http_host:
        origens.append("%s://%s" % (request.env.wsgi_url_scheme, request.env.http_host))
    return origens


def _rejeitar(motivo):
    origem = request.env.http_origin or request.env.http_referer or ""
    _log.warning(
        "requisicao rejeitada (motivo=%s metodo=%s caminho=%s origem=%r ip=%s)",
        motivo, request.env.request_method, request.env.path_info, origem[:200],
        request.env.remote_addr, extra={"acao": "CSRF"},
    )
    raise HTTP(403, u"Requisição recusada.", **response.headers)


# Reprocessamento de routes_onerror reaproveita o environ (metodo e corpo ja consumido);
# a chave nao pode ser injetada pelo cliente, pois cabecalhos chegam com prefixo HTTP_.
_reprocessando_erro = bool(request.env.get("__routes_onerror__"))
if _reprocessando_erro:
    # Sem isto, o web2py tentaria ler de novo o wsgi.input pelo CONTENT_LENGTH herdado e bloquearia.
    request._body = io.BytesIO()

if (request.env.request_method or "GET").upper() not in ("GET", "HEAD", "OPTIONS") \
        and not _reprocessando_erro:
    if not security.origem_permitida(request.env.http_origin, request.env.http_referer, _origens_permitidas()):
        _rejeitar("origem")
    _token = request.post_vars.get("_csrf")
    if not isinstance(_token, str) or not _token:
        _token = request.env.http_x_csrf_token
    if not security.validar_token_csrf(session.csrf_token, _token):
        _rejeitar("csrf")


def _ip_origem():
    """IP do cliente (README §4.2): X-Forwarded-For so quando remote_addr e proxy confiavel."""
    return security.ip_origem(request.env.remote_addr, request.env.http_x_forwarded_for,
                              _cfg.web.trusted_proxies)


def _destino_atual():
    caminho = request.env.path_info or ""
    if request.env.query_string:
        caminho = "%s?%s" % (caminho, request.env.query_string)
    return security.validar_next(caminho)


def _exigir_login():
    """Guarda de autenticacao: sem sessao valida, redireciona ao login com 'next' local validado."""
    ctx = current.sss_ctx
    if ctx:
        return ctx
    destino = None
    if (request.env.request_method or "GET").upper() in ("GET", "HEAD"):
        destino = _destino_atual()
    redirect(URL(c=_URL_LOGIN[0], f=_URL_LOGIN[1], vars={"next": destino} if destino else {}))


def _exigir_func(codigo):
    """Guarda de autorizacao: exige login e a funcionalidade; sem ela, 403 com log WARN."""
    ctx = _exigir_login()
    if not rbac.tem_func(ctx, codigo):
        _log.warning(
            "acesso negado (login=%s funcionalidade=%s caminho=%s ip=%s)",
            ctx["login"], codigo, request.env.path_info, _ip_origem(), extra={"acao": "RBAC"},
        )
        raise HTTP(403, u"Acesso negado.", **response.headers)
    return ctx
