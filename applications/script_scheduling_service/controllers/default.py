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

_MSG_FALHA_CARTAO = u"Não foi possível carregar este quadro. Tente novamente em instantes."


def _texto_post(nome, limite):
    valor = request.post_vars.get(nome)
    if not isinstance(valor, str):
        return ""
    return valor[:limite]


def _cartao(ctx, nome, funcao):
    """Executa a consulta de um cartao; falha de repositorio vira mensagem no proprio cartao."""
    try:
        return funcao(), None
    except RepoError:
        _log.exception("falha ao montar o cartao %s do painel inicial (login=%s)", nome, ctx["login"],
                       extra={"action": "PAINEL"})
        return None, _MSG_FALHA_CARTAO


def index():
    ctx = _exigir_login()
    response.title = u"Início — SSS"
    cartoes = {}
    # Cada cartao so existe para quem tem a funcionalidade (F6.1); o escopo e o das telas de origem.
    if ticket_service.can_query(ctx):
        cartoes["tickets"] = _cartao(ctx, "tickets", lambda: ticket_service.home_summary(ctx))
    if rbac.has_feature(ctx, "MANAGE_SCHEDULES"):
        cartoes["schedules"] = _cartao(
            ctx, "schedules", lambda: schedules_service.list_page(ctx, {"active": "Y"}, 1, 5)["itens"])
    if rbac.has_feature(ctx, "VIEW_AUDIT"):
        cartoes["agents"] = _cartao(ctx, "agents", lambda: agents_service.dashboard(ctx))
    return dict(ctx=ctx, menu=response.sss_menu, pode_disparar=rbac.has_feature(ctx, "EXEC_SCRIPT"),
                cartoes=cartoes)


def login():
    metodo = (request.env.request_method or "GET").upper()
    if metodo not in ("GET", "HEAD", "POST"):
        raise HTTP(405)
    response.title = u"Entrar — SSS"
    destino = security.validate_next(request.vars.get("next"))
    if current.sss_ctx:
        redirect(destino or URL(c="default", f="index"))

    mensagem = None
    login_digitado = ""
    if metodo == "POST":
        login_digitado = _texto_post("login", 30).strip()
        senha = security.strip_passwords((request.post_vars, request.vars), ("senha",))["senha"]
        ctx, mensagem = auth_service.authenticate(login_digitado, senha, _ip_origem())
        if ctx is not None:
            # Em sessao por cookie, renew() apenas limpa: o cookie e regravado com conteudo novo.
            session.renew(clear_session=True)
            session.csrf_token = security.generate_csrf_token()
            session.usuario_id = ctx["user_id"]
            session.login = ctx["login"]
            session.perfil_id = ctx["profile_id"]
            session.perm_versao = ctx["perm_version"]
            session.sessao_epoch = ctx["session_epoch"]
            session.ultimo_acesso = session.login_em = time.time()
            redirect(destino or URL(c="default", f="index"))
    return dict(mensagem=mensagem, login_digitado=login_digitado, destino=destino or "")


def logout():
    if (request.env.request_method or "GET").upper() != "POST":
        raise HTTP(405)
    if current.sss_ctx:
        auth_service.logout(current.sss_ctx, _ip_origem())
    session.clear()
    session.csrf_token = security.generate_csrf_token()
    session.flash = {"tipo": "sucesso", "mensagem": u"Você saiu do sistema."}
    redirect(URL(c="default", f="login"))


_CAMPOS_MINHA_SENHA = ("senha_atual", "nova", "confirmacao")


def permissoes():
    """O que eu posso fazer (README §4.3.E): so leitura, para qualquer usuario logado."""
    if (request.env.request_method or "GET").upper() not in ("GET", "HEAD"):
        raise HTTP(405, **response.headers)
    ctx = _exigir_login()
    response.title = u"O que eu posso fazer — SSS"
    try:
        dados = permissions_service.build(ctx)
        erro = None
    except RepoError:
        _log.exception("falha ao montar permissoes (login=%s)", ctx["login"], extra={"action": "PERMISSOES"})
        dados, erro = None, ui_helpers.mensagem("falha_interna")
    return dict(dados=dados, erro=erro)


def minha_senha():
    metodo = (request.env.request_method or "GET").upper()
    if metodo not in ("GET", "HEAD", "POST"):
        raise HTTP(405, **response.headers)
    ctx = _exigir_login()
    response.title = u"Minha senha — SSS"
    erros = {}
    if metodo == "POST":
        senhas = security.strip_passwords((request.post_vars, request.vars), _CAMPOS_MINHA_SENHA)
        resultado, erros = auth_service.change_password(ctx, _ip_origem(), senhas["senha_atual"], senhas["nova"],
                                                     senhas["confirmacao"])
        if resultado == "BLOQUEADO":
            session.clear()
            session.csrf_token = security.generate_csrf_token()
            session.flash = {"tipo": "aviso", "mensagem": auth_service.lock_message()}
            redirect(URL(c="default", f="login"))
        if resultado == "OK":
            # Nova senha, nova sessao: o cookie e regravado com conteudo novo e outro token CSRF.
            session.renew(clear_session=True)
            session.csrf_token = security.generate_csrf_token()
            session.usuario_id = ctx["user_id"]
            session.login = ctx["login"]
            session.perfil_id = ctx["profile_id"]
            session.perm_versao = ctx["perm_version"]
            # A troca incrementou session_epoch (CR-008, E2): as outras sessoes caem, esta continua.
            session.sessao_epoch = auth_service.session_epoch(ctx["user_id"])
            session.ultimo_acesso = session.login_em = time.time()
            session.flash = {"tipo": "sucesso", "mensagem": u"Senha alterada com sucesso."}
            redirect(URL(c="default", f="index"))
        response.flash = {"tipo": "erro", "mensagem": u"A senha não foi alterada. Veja os campos destacados."}
    campos = [{"name": n, "erro": erros.get(n)} for n in _CAMPOS_MINHA_SENHA]
    return dict(erros=erros, foco_campo=ui_helpers.primeiro_campo_invalido(campos),
                ajuda_senha=u"Mínimo de %d caracteres. A senha nunca é exibida nem registrada." % security.PASSWORD_MIN)
