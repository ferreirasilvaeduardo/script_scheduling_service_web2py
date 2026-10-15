# -*- coding: utf-8 -*-
"""Dicionario de parametros (README §6, CAD_PARAMETROS). Padrao em docs/PADRAO_CRUD_ADMIN.md.

Regras ficam em modules/admin_parametros_service.py; CSRF e Origin de todo POST sao validados em
models/10_security.py. O editor de opcoes do cliente e conveniencia: o servidor revalida tudo.
"""
import admin_crud
import admin_parametros_service as servico
import ui_helpers
from admin_crud import AcessoNegado, OperacaoNegada
from repo_errors import RepoConflito, RepoErro, RepoNaoEncontrado

_FUNC = "CAD_PARAMETROS"
_TAMANHOS = (20, 50, 100)
_CAMPOS = ("codigo", "param_nomeado", "label", "descricao", "tipo_componente", "opcoes_json", "valor_padrao",
           "remover_padrao", "regex_validacao", "sensivel", "versao")
_JS = "js/app/parametros.js"
_MSG_FALHA_LISTA = u"Não foi possível carregar os parâmetros. Tente novamente em instantes."
_MSG_FALHA_ACAO = u"Não foi possível concluir a operação. Tente novamente em instantes."


def _exigir_metodo(*permitidos):
    if (request.env.request_method or "GET").upper() not in permitidos:
        raise HTTP(405, **response.headers)


def _negado():
    raise HTTP(403, u"Acesso negado.", **response.headers)


def _nao_encontrado():
    raise HTTP(404, u"Parâmetro não encontrado.", **response.headers)


def _texto(valor, limite):
    valor = valor[-1] if isinstance(valor, list) and valor else valor
    return valor[:limite] if isinstance(valor, str) else None


def _enviados():
    return dict((c, _texto(request.post_vars.get(c), 1000)) for c in _CAMPOS)


def _pagina_form(ctx, dados, erros=None):
    response.title = (u"Parâmetro %s — SSS" % dados["codigo"]) if dados.get("id") else u"Novo parâmetro — SSS"
    response.view = "admin_parametros/form.html"
    response.sss_scripts = [_JS]
    erros = erros or {}
    campos = [{"nome": n, "erro": erros.get(n)} for n in ("codigo", "param_nomeado", "label", "descricao",
                                                          "tipo_componente", "opcoes_json", "regex_validacao",
                                                          "valor_padrao")]
    return dict(prm=dados, erros=erros, erro_geral=erros.get(admin_crud.CAMPO_GERAL),
                foco_campo=ui_helpers.primeiro_campo_invalido(campos), tipos=servico.ROTULOS_TIPO,
                aviso_sensivel=servico.AVISO_SENSIVEL)


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
        _log.exception("falha ao listar parametros (login=%s)", ctx["login"], extra={"acao": _FUNC})
        resultado = {"itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        erro = _MSG_FALHA_LISTA
    response.title = u"Parâmetros — SSS"
    return dict(resultado=resultado, erro=erro, filtros_ativos=filtros, tamanho=tamanho, tipos=servico.ROTULOS_TIPO,
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
    parametro_id = _texto(request.post_vars.get("id"), 11)
    enviados = _enviados()
    try:
        _salvo, erros = servico.salvar(ctx, _ip_origem(), parametro_id, enviados)
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except RepoErro:
        _log.exception("falha ao salvar parametro (login=%s id=%r)", ctx["login"], parametro_id, extra={"acao": _FUNC})
        erros = {admin_crud.CAMPO_GERAL: admin_crud.MSG_FALHA}
    if not erros:
        session.flash = {"tipo": "sucesso", "mensagem": u"Parâmetro salvo com sucesso."}
        redirect(URL(c="admin_parametros", f="lista"))
    try:
        dados = servico.formulario(ctx, parametro_id) if parametro_id else servico.formulario(ctx)
    except RepoErro:
        dados = {"id": None, "codigo": "", "param_nomeado": "", "label": "", "descricao": "",
                 "tipo_componente": "TEXT", "opcoes_json": "", "valor_padrao": "", "tem_padrao": False,
                 "regex_validacao": "", "sensivel": "N", "ativo": "S", "versao": "", "vinculos": [],
                 "pode_regex": ctx.get("is_admin") is True}
    if admin_crud.CAMPO_GERAL not in erros:
        reapresentar = dict((c, enviados[c] or "") for c in ("param_nomeado", "label", "descricao", "tipo_componente",
                                                             "opcoes_json", "regex_validacao"))
        reapresentar["sensivel"] = "S" if enviados["sensivel"] == "S" else "N"
        # Padrao de parametro sensivel nunca volta ao HTML.
        reapresentar["valor_padrao"] = "" if reapresentar["sensivel"] == "S" else (enviados["valor_padrao"] or "")
        if not dados.get("pode_regex"):
            reapresentar.pop("regex_validacao")
        dados = dict(dados, **reapresentar)
        if not parametro_id:
            dados["codigo"] = enviados["codigo"] or ""
        else:
            dados["versao"] = enviados["versao"] or ""
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"tipo": "erro", "mensagem": erros.get(admin_crud.CAMPO_GERAL)
                      or u"Corrija os campos destacados e envie novamente."}
    return _pagina_form(ctx, dados, erros)


def alternar_ativo():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    parametro_id = _texto(request.post_vars.get("id"), 11)
    try:
        alterado = servico.alternar_ativo(ctx, _ip_origem(), parametro_id, _texto(request.post_vars.get("versao"), 64))
        acao = u"desativado" if alterado["ativo"] == "N" else u"reativado"
        session.flash = {"tipo": "sucesso", "mensagem": u"Parâmetro %s %s." % (alterado["codigo"], acao)}
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except OperacaoNegada as exc:
        session.flash = {"tipo": "erro", "mensagem": exc.mensagem}
    except RepoConflito:
        session.flash = {"tipo": "aviso", "mensagem": admin_crud.MSG_CONFLITO}
    except RepoErro:
        _log.exception("falha ao alternar parametro (login=%s id=%r)", ctx["login"], parametro_id, extra={"acao": _FUNC})
        session.flash = {"tipo": "erro", "mensagem": _MSG_FALHA_ACAO}
    redirect(URL(c="admin_parametros", f="form", args=[parametro_id]))


def testar():
    # POST: a configuracao em edicao e o valor de teste nunca vao para a URL nem para o log de acesso.
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    response.headers["Cache-Control"] = "no-store"
    try:
        resultado = servico.testar(ctx, _texto(request.post_vars.get("id"), 11), _enviados(),
                                   _texto(request.post_vars.get("valor_teste"), 1000))
    except RepoNaoEncontrado:
        response.status = 404
        return response.json({"ok": False, "erro": u"Parâmetro não encontrado."})
    except AcessoNegado:
        response.status = 403
        return response.json({"ok": False, "erro": u"Acesso negado."})
    return response.json(resultado)
