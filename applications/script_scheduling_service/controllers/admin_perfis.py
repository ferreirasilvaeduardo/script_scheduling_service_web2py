# -*- coding: utf-8 -*-
"""Cadastro de perfis e matriz de permissoes (README §4.3, CAD_PERFIS). Padrao em docs/PADRAO_CRUD_ADMIN.md.

Regras ficam em modules/admin_perfis_service.py; CSRF e Origin de todo POST sao validados
em models/10_security.py. Nenhuma permissao e decidida no cliente: o POST da matriz e revalidado inteiro.
"""
import admin_crud
import admin_perfis_service as servico
import ui_helpers
from admin_crud import AcessoNegado, OperacaoNegada
from repo_errors import RepoConflito, RepoErro, RepoNaoEncontrado

_FUNC = "CAD_PERFIS"
_TAMANHOS = (20, 50, 100)
_MAX_IDS = 5000
_MSG_FALHA_LISTA = u"Não foi possível carregar os perfis. Tente novamente em instantes."
_MSG_FALHA_ALTERNAR = u"Não foi possível alterar a situação do perfil. Tente novamente em instantes."
_MSG_FALHA_MATRIZ = u"Não foi possível salvar a matriz. Tente novamente em instantes."
_JS_MATRIZ = "js/app/matriz.js"


def _exigir_metodo(*permitidos):
    if (request.env.request_method or "GET").upper() not in permitidos:
        raise HTTP(405, **response.headers)


def _negado():
    raise HTTP(403, u"Acesso negado.", **response.headers)


def _nao_encontrado():
    raise HTTP(404, u"Perfil não encontrado.", **response.headers)


def _texto(valor, limite):
    valor = valor[-1] if isinstance(valor, list) and valor else valor
    return valor[:limite] if isinstance(valor, str) else None


def _lista(nome):
    valor = request.post_vars.get(nome)
    if valor is None:
        return []
    valor = valor if isinstance(valor, list) else [valor]
    return [v[:11] if isinstance(v, str) else v for v in valor[:_MAX_IDS]]


def _pagina_form(ctx, dados, erros=None):
    response.title = (u"Perfil %s — SSS" % dados["nome"]) if dados.get("id") else u"Novo perfil — SSS"
    response.view = "admin_perfis/form.html"
    erros = erros or {}
    campos = [{"nome": n, "erro": erros.get(n)} for n in ("nome", "descricao")]
    return dict(perfil=dados, erros=erros, erro_geral=erros.get(admin_crud.CAMPO_GERAL),
                foco_campo=ui_helpers.primeiro_campo_invalido(campos),
                aviso_desativacao=servico.AVISO_DESATIVACAO)


def lista():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    filtros = servico.normalizar_filtros(request.get_vars)
    pagina = ui_helpers.sanitizar_pagina(_texto(request.get_vars.get("pagina"), 9))
    tamanho = ui_helpers.sanitizar_tamanho(_texto(request.get_vars.get("tamanho"), 3), _TAMANHOS)
    erro = None
    try:
        resultado = servico.listar(ctx, filtros, pagina, tamanho)
    except AcessoNegado:
        _negado()
    except RepoErro:
        _log.exception("falha ao listar perfis (login=%s)", ctx["login"], extra={"acao": _FUNC})
        resultado = {"itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        erro = _MSG_FALHA_LISTA
    response.title = u"Perfis — SSS"
    return dict(resultado=resultado, erro=erro, filtros_ativos=filtros, tamanho=tamanho,
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
    perfil_id = _texto(request.post_vars.get("id"), 11)
    enviados = dict((c, _texto(request.post_vars.get(c), 300)) for c in ("nome", "descricao", "is_admin", "versao"))
    try:
        salvo_id, erros = servico.salvar(ctx, _ip_origem(), perfil_id, enviados)
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except RepoErro:
        _log.exception("falha ao salvar perfil (login=%s id=%r)", ctx["login"], perfil_id, extra={"acao": _FUNC})
        salvo_id, erros = None, {admin_crud.CAMPO_GERAL: admin_crud.MSG_FALHA}
    if not erros:
        session.flash = {"tipo": "sucesso", "mensagem": u"Perfil salvo com sucesso."}
        redirect(URL(c="admin_perfis", f="lista"))
    try:
        dados = servico.formulario(ctx, perfil_id) if perfil_id else servico.formulario(ctx)
    except RepoErro:
        dados = {"id": None, "nome": "", "descricao": "", "is_admin": "N", "ativo": "S", "versao": "",
                 "usuarios_ativos": 0}
    if admin_crud.CAMPO_GERAL not in erros:
        dados = dict(dados, nome=enviados["nome"] or "", descricao=enviados["descricao"] or "",
                     is_admin="S" if enviados["is_admin"] == "S" else "N")
        if perfil_id:
            dados["versao"] = enviados["versao"] or ""
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"tipo": "erro", "mensagem": erros.get(admin_crud.CAMPO_GERAL)
                      or ui_helpers.mensagem("formulario")}
    return _pagina_form(ctx, dados, erros)


def alternar_ativo():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    perfil_id = _texto(request.post_vars.get("id"), 11)
    try:
        alterado = servico.alternar_ativo(ctx, _ip_origem(), perfil_id, _texto(request.post_vars.get("versao"), 64))
        acao = u"desativado" if alterado["ativo"] == "N" else u"reativado"
        session.flash = {"tipo": "sucesso", "mensagem": u"Perfil %s %s." % (alterado["nome"], acao)}
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except OperacaoNegada as exc:
        session.flash = {"tipo": "erro", "mensagem": exc.mensagem}
    except RepoConflito:
        session.flash = {"tipo": "aviso", "mensagem": admin_crud.MSG_CONFLITO}
    except RepoErro:
        _log.exception("falha ao alternar perfil (login=%s id=%r)", ctx["login"], perfil_id, extra={"acao": _FUNC})
        session.flash = {"tipo": "erro", "mensagem": _MSG_FALHA_ALTERNAR}
    redirect(URL(c="admin_perfis", f="form", args=[perfil_id]))


def quem_pode():
    """Quem pode o que (README §4.3.B.2): so leitura, por script ou por ambiente."""
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    try:
        dados = servico.quem_pode(ctx, _texto(request.get_vars.get("script"), 11),
                                  _texto(request.get_vars.get("ambiente"), 11))
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    response.title = u"Quem pode o quê — SSS"
    return dict(q=dados)


def matriz():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    try:
        dados = servico.matriz(ctx, _texto(request.args(0), 11))
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    response.title = u"Permissões de %s — SSS" % dados["perfil"]["nome"]
    response.sss_scripts = [_JS_MATRIZ]
    return dict(matriz=dados)


def salvar_matriz():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    perfil_id = _texto(request.post_vars.get("id"), 11)
    try:
        diff, erros = servico.salvar_matriz(ctx, _ip_origem(), perfil_id, _lista("funcs"), _lista("ambs"),
                                            _lista("scrs"), _texto(request.post_vars.get("perm_versao"), 11))
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except RepoErro:
        _log.exception("falha ao salvar matriz (login=%s id=%r)", ctx["login"], perfil_id, extra={"acao": "PERM_ALTERAR"})
        diff, erros = None, {admin_crud.CAMPO_GERAL: _MSG_FALHA_MATRIZ}
    if erros:
        session.flash = {"tipo": "erro", "mensagem": erros[admin_crud.CAMPO_GERAL]}
    elif diff:
        session.flash = {"tipo": "sucesso", "mensagem": u"Permissões salvas: %s" % diff}
    else:
        session.flash = {"tipo": "aviso", "mensagem": u"Nenhuma alteração para salvar."}
    redirect(URL(c="admin_perfis", f="matriz", args=[perfil_id]))
