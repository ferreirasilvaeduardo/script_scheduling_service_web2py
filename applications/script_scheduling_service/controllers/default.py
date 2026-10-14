# -*- coding: utf-8 -*-
"""Painel inicial, login e logout (README §4.2). CSRF e Origin de todo POST sao validados em models/10_security.py."""
import time

from gluon import current

import auth_service
import security


def _texto_post(nome, limite):
    valor = request.post_vars.get(nome)
    if not isinstance(valor, str):
        return ""
    return valor[:limite]


def index():
    ctx = _exigir_login()
    response.title = u"Início — SSS"
    return dict(ctx=ctx, menu=response.sss_menu)


def login():
    metodo = (request.env.request_method or "GET").upper()
    if metodo not in ("GET", "HEAD", "POST"):
        raise HTTP(405)
    response.title = u"Entrar — SSS"
    destino = security.validar_next(request.vars.get("next"))
    if current.sss_ctx:
        redirect(destino or URL(c="default", f="index"))

    mensagem = None
    login_digitado = ""
    if metodo == "POST":
        login_digitado = _texto_post("login", 30).strip()
        ctx, mensagem = auth_service.autenticar(login_digitado, request.post_vars.get("senha"), _ip_origem())
        if ctx is not None:
            # Em sessao por cookie, renew() apenas limpa: o cookie e regravado com conteudo novo.
            session.renew(clear_session=True)
            session.csrf_token = security.gerar_token_csrf()
            session.usuario_id = ctx["usuario_id"]
            session.login = ctx["login"]
            session.perfil_id = ctx["perfil_id"]
            session.perm_versao = ctx["perm_versao"]
            session.ultimo_acesso = time.time()
            redirect(destino or URL(c="default", f="index"))
    return dict(mensagem=mensagem, login_digitado=login_digitado, destino=destino or "")


def logout():
    if (request.env.request_method or "GET").upper() != "POST":
        raise HTTP(405)
    if current.sss_ctx:
        auth_service.logout(current.sss_ctx, _ip_origem())
    session.clear()
    session.csrf_token = security.gerar_token_csrf()
    session.flash = {"tipo": "sucesso", "mensagem": u"Você saiu do sistema."}
    redirect(URL(c="default", f="login"))
