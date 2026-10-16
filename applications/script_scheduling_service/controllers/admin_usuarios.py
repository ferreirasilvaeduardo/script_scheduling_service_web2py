# -*- coding: utf-8 -*-
"""Cadastro de usuarios (README §4.2, §4.3.B, CAD_USUARIOS). Padrao em docs/PADRAO_CRUD_ADMIN.md.

Regras ficam em modules/admin_usuarios_service.py; CSRF e Origin de todo POST sao validados em
models/10_security.py. Senhas sao retiradas de request.vars assim que lidas: o ticket de erro do
web2py grava as variaveis da requisicao.
"""
import admin_crud
import admin_usuarios_service as servico
import security
import ui_helpers
from admin_crud import AcessoNegado, OperacaoNegada
from repo_errors import RepoConflito, RepoErro, RepoNaoEncontrado

_FUNC = "CAD_USUARIOS"
_TAMANHOS = (20, 50, 100)
_CAMPOS_SENHA = ("senha", "confirmacao")
_MSG_FALHA_LISTA = u"Não foi possível carregar os usuários. Tente novamente em instantes."
_MSG_FALHA_ACAO = u"Não foi possível concluir a operação. Tente novamente em instantes."


def _exigir_metodo(*permitidos):
    if (request.env.request_method or "GET").upper() not in permitidos:
        raise HTTP(405, **response.headers)


def _negado():
    raise HTTP(403, u"Acesso negado.", **response.headers)


def _nao_encontrado():
    raise HTTP(404, u"Usuário não encontrado.", **response.headers)


def _texto(valor, limite):
    valor = valor[-1] if isinstance(valor, list) and valor else valor
    return valor[:limite] if isinstance(valor, str) else None


def _retirar_senhas():
    return security.retirar_senhas((request.post_vars, request.vars), _CAMPOS_SENHA)


def _inteiro(valor):
    return int(valor) if isinstance(valor, str) and valor.isdigit() and len(valor) <= 10 else None


def _pagina_form(ctx, dados, erros=None, erros_senha=None):
    response.title = (u"Usuário %s — SSS" % dados["login"]) if dados.get("id") else u"Novo usuário — SSS"
    response.view = "admin_usuarios/form.html"
    erros = erros or {}
    campos = [{"nome": n, "erro": erros.get(n)} for n in ("login", "nome", "perfil_id", "senha", "confirmacao")]
    perfis = [p for p in servico.perfis() if p["ativo"] == "S" or p["id"] == dados.get("perfil_id")]
    return dict(usuario=dados, erros=erros, erro_geral=erros.get(admin_crud.CAMPO_GERAL),
                erros_senha=erros_senha or {}, perfis=perfis,
                foco_campo=ui_helpers.primeiro_campo_invalido(campos), ajuda_senha=servico.AJUDA_POLITICA,
                aviso_desativacao=servico.AVISO_DESATIVACAO)


def lista():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    filtros = servico.normalizar_filtros(request.get_vars)
    pagina = ui_helpers.sanitizar_pagina(_texto(request.get_vars.get("pagina"), 9))
    tamanho = ui_helpers.sanitizar_tamanho(_texto(request.get_vars.get("tamanho"), 3), _TAMANHOS)
    erro = None
    perfis = []
    try:
        resultado = servico.listar(ctx, filtros, pagina, tamanho)
        perfis = servico.perfis()
    except AcessoNegado:
        _negado()
    except RepoErro:
        _log.exception("falha ao listar usuarios (login=%s)", ctx["login"], extra={"acao": _FUNC})
        resultado = {"itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        erro = _MSG_FALHA_LISTA
    response.title = u"Usuários — SSS"
    return dict(resultado=resultado, erro=erro, filtros_ativos=filtros, tamanho=tamanho, perfis=perfis,
                query_params=dict(filtros, tamanho=tamanho))


def form():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    try:
        dados = servico.formulario(ctx, _texto(request.args(0), 11))
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    return _pagina_form(ctx, dados)


def salvar():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    senhas = _retirar_senhas()
    usuario_id = _texto(request.post_vars.get("id"), 11)
    enviados = dict((c, _texto(request.post_vars.get(c), 300)) for c in ("login", "nome", "perfil_id", "versao"))
    enviados.update(senhas)
    try:
        _salvo, erros = servico.salvar(ctx, _ip_origem(), usuario_id, enviados)
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except RepoErro:
        _log.exception("falha ao salvar usuario (login=%s id=%r)", ctx["login"], usuario_id, extra={"acao": _FUNC})
        erros = {admin_crud.CAMPO_GERAL: admin_crud.MSG_FALHA}
    if not erros:
        session.flash = {"tipo": "sucesso", "mensagem": u"Usuário salvo com sucesso."}
        redirect(URL(c="admin_usuarios", f="lista"))
    try:
        dados = servico.formulario(ctx, usuario_id) if usuario_id else servico.formulario(ctx)
    except RepoErro:
        dados = {"id": None, "login": "", "nome": "", "perfil_id": None, "ativo": "S", "versao": "",
                 "bloqueado": False, "bloqueado_ate": None, "tentativas_falha": 0, "proprio": False}
    if admin_crud.CAMPO_GERAL not in erros:
        dados = dict(dados, nome=enviados["nome"] or "", perfil_id=_inteiro(enviados["perfil_id"]))
        if not usuario_id:
            dados["login"] = enviados["login"] or ""
        else:
            dados["versao"] = enviados["versao"] or ""
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"tipo": "erro", "mensagem": erros.get(admin_crud.CAMPO_GERAL)
                      or ui_helpers.mensagem("formulario")}
    return _pagina_form(ctx, dados, erros)


def alternar_ativo():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    usuario_id = _texto(request.post_vars.get("id"), 11)
    try:
        alterado = servico.alternar_ativo(ctx, _ip_origem(), usuario_id, _texto(request.post_vars.get("versao"), 64))
        acao = u"desativado" if alterado["ativo"] == "N" else u"reativado"
        session.flash = {"tipo": "sucesso", "mensagem": u"Usuário %s %s." % (alterado["login"], acao)}
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except OperacaoNegada as exc:
        session.flash = {"tipo": "erro", "mensagem": exc.mensagem}
    except RepoConflito:
        session.flash = {"tipo": "aviso", "mensagem": admin_crud.MSG_CONFLITO}
    except RepoErro:
        _log.exception("falha ao alternar usuario (login=%s id=%r)", ctx["login"], usuario_id, extra={"acao": _FUNC})
        session.flash = {"tipo": "erro", "mensagem": _MSG_FALHA_ACAO}
    redirect(URL(c="admin_usuarios", f="form", args=[usuario_id]))


def redefinir_senha():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    senhas = _retirar_senhas()
    usuario_id = _texto(request.post_vars.get("id"), 11)
    try:
        erros = servico.redefinir_senha(ctx, _ip_origem(), usuario_id, senhas["senha"], senhas["confirmacao"])
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except OperacaoNegada as exc:
        session.flash = {"tipo": "erro", "mensagem": exc.mensagem}
        redirect(URL(c="admin_usuarios", f="form", args=[usuario_id]))
    except RepoErro:
        _log.exception("falha ao redefinir senha (login=%s id=%r)", ctx["login"], usuario_id, extra={"acao": _FUNC})
        session.flash = {"tipo": "erro", "mensagem": _MSG_FALHA_ACAO}
        redirect(URL(c="admin_usuarios", f="form", args=[usuario_id]))
    if not erros:
        session.flash = {"tipo": "sucesso", "mensagem": u"Senha redefinida. Tentativas e bloqueio foram zerados."}
        redirect(URL(c="admin_usuarios", f="form", args=[usuario_id]))
    response.flash = {"tipo": "erro", "mensagem": u"A nova senha não foi aceita. Veja o campo destacado."}
    return _pagina_form(ctx, servico.formulario(ctx, usuario_id), erros_senha=erros)


def desbloquear():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    usuario_id = _texto(request.post_vars.get("id"), 11)
    try:
        alterado = servico.desbloquear(ctx, _ip_origem(), usuario_id)
        session.flash = {"tipo": "sucesso", "mensagem": u"Usuário %s desbloqueado." % alterado["login"]}
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except RepoErro:
        _log.exception("falha ao desbloquear (login=%s id=%r)", ctx["login"], usuario_id, extra={"acao": _FUNC})
        session.flash = {"tipo": "erro", "mensagem": _MSG_FALHA_ACAO}
    redirect(URL(c="admin_usuarios", f="form", args=[usuario_id]))
