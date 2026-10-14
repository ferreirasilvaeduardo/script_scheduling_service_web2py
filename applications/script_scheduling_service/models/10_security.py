# -*- coding: utf-8 -*-
"""Sessao, CSRF + Origin em todo metodo que altera estado, cabecalhos de seguranca e mascaramento.

Roda antes de qualquer controller (README §4.2, AGENTS §3.4).
"""
import io
import time

import masking
import security
import sss_config
import sss_logging

_cfg = current.sss_cfg
_segredos = sss_config.obter_segredos()
_log = sss_logging.obter_logger("sss_web", _cfg)
masking.instalar_filtro_em_handlers()

response.headers.update({
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
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

if session.usuario_id:
    _agora = time.time()
    if security.sessao_expirada(session.ultimo_acesso, _agora, _cfg.web.session_idle_timeout_s):
        session.clear()
        session.csrf_token = security.gerar_token_csrf()
        session.flash = {"tipo": "aviso", "mensagem": u"Sua sessão expirou por inatividade. Entre novamente."}
        redirect(URL(c=_URL_LOGIN[0], f=_URL_LOGIN[1]))
    session.ultimo_acesso = _agora
    response.headers["Cache-Control"] = "no-store"

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
