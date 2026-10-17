# -*- coding: utf-8 -*-
"""Cadastro de scripts, homologacao e vinculo de parametros (README §4.3.A, §6.3, §8.5, CAD_SCRIPTS).

Padrao em docs/PADRAO_CRUD_ADMIN.md. Regras ficam em modules/admin_scripts_service.py; CSRF e Origin
de todo POST sao validados em models/10_security.py. Listas enviadas pelo cliente sao revalidadas inteiras.
"""
import admin_crud
import admin_scripts_service as servico
import path_guard
import ui_helpers
from admin_crud import AcessoNegado, OperacaoNegada
from repo_errors import RepoConflito, RepoErro, RepoNaoEncontrado

_FUNC = "CAD_SCRIPTS"
_TAMANHOS = (20, 50, 100)
_CAMPOS = ("nome", "descricao", "grupo", "categoria", "etapa", "interpretador", "path_file", "tipo_param",
           "max_qtd_parallel_env", "timeout_seg", "versao", "registrar_conteudo_atual", "sha256_informado")
_JS = "js/app/scripts_admin.js"
_MAX_JSON = 50000
_MAX_IDS = 1000
_MSG_FALHA_LISTA = u"Não foi possível carregar os scripts. Tente novamente em instantes."
_MSG_FALHA_ACAO = u"Não foi possível concluir a operação. Tente novamente em instantes."


def _exigir_metodo(*permitidos):
    if (request.env.request_method or "GET").upper() not in permitidos:
        raise HTTP(405, **response.headers)


def _negado():
    raise HTTP(403, u"Acesso negado.", **response.headers)


def _nao_encontrado():
    raise HTTP(404, u"Script não encontrado.", **response.headers)


def _texto(valor, limite):
    valor = valor[-1] if isinstance(valor, list) and valor else valor
    return valor[:limite] if isinstance(valor, str) else None


def _vazio_form(ctx):
    # Fallback quando nem o formulario pode ser lido (falha de repositorio): so os campos que a view usa.
    return {"id": None, "nome": "", "descricao": "", "grupo": "", "categoria": "", "etapa": "",
            "interpretador": path_guard.ALLOWLIST[0], "path_file": "",
            "tipo_param": "NOMEADO",
            "max_qtd_parallel_env": 1, "timeout_seg": "", "ativo": "S", "versao": "", "agendamentos_ativos": 0,
            "obs_validacao": servico.OBS_VALIDACAO}


def _pagina_form(ctx, dados, erros=None):
    response.title = (u"Script %s — SSS" % dados["nome"]) if dados.get("id") else u"Novo script — SSS"
    response.view = "admin_scripts/form.html"
    erros = erros or {}
    campos = [{"nome": n, "erro": erros.get(n)} for n in ("nome", "descricao", "grupo", "categoria", "etapa",
                                                          "interpretador", "path_file", "tipo_param",
                                                          "max_qtd_parallel_env", "timeout_seg")]
    return dict(scr=dados, erros=erros, erro_geral=erros.get(admin_crud.CAMPO_GERAL), interpretadores=servico.ROTULOS_INTERPRETADOR,
                tipos_param=servico.ROTULOS_TIPO_PARAM, foco_campo=ui_helpers.primeiro_campo_invalido(campos),
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
        _log.exception("falha ao listar scripts (login=%s)", ctx["login"], extra={"acao": _FUNC})
        resultado = {"itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        erro = _MSG_FALHA_LISTA
    response.title = u"Scripts — SSS"
    return dict(resultado=resultado, erro=erro, filtros_ativos=filtros, tamanho=tamanho, interpretadores=servico.ROTULOS_INTERPRETADOR,
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
    script_id = _texto(request.post_vars.get("id"), 11)
    # Teto acima do maior limite do service (path_file: 500), para que o excesso seja recusado (AGENTS §3.4).
    enviados = dict((c, _texto(request.post_vars.get(c), 600)) for c in _CAMPOS)
    aviso = None
    try:
        salvo_id, erros, aviso = servico.salvar(ctx, _ip_origem(), script_id, enviados)
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except OperacaoNegada as exc:
        salvo_id, erros = None, {admin_crud.CAMPO_GERAL: str(exc)}
    except RepoErro:
        _log.exception("falha ao salvar script (login=%s id=%r)", ctx["login"], script_id, extra={"acao": _FUNC})
        salvo_id, erros = None, {admin_crud.CAMPO_GERAL: admin_crud.MSG_FALHA}
    if not erros:
        mensagem = u"Script salvo com sucesso." + (u" " + aviso if aviso else u"")
        session.flash = {"tipo": "aviso" if aviso else "sucesso", "mensagem": mensagem}
        redirect(URL(c="admin_scripts", f="form", args=[salvo_id]))
    try:
        dados = servico.formulario(ctx, script_id) if script_id else servico.formulario(ctx)
    except RepoErro:
        dados = _vazio_form(ctx)
    if admin_crud.CAMPO_GERAL not in erros:
        dados = dict(dados, **dict((c, enviados[c] or "") for c in _CAMPOS if c != "versao"))
        if script_id:
            dados["versao"] = enviados["versao"] or ""
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"tipo": "erro", "mensagem": erros.get(admin_crud.CAMPO_GERAL)
                      or ui_helpers.mensagem("formulario")}
    return _pagina_form(ctx, dados, erros)


def alternar_ativo():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    script_id = _texto(request.post_vars.get("id"), 11)
    try:
        alterado = servico.alternar_ativo(ctx, _ip_origem(), script_id, _texto(request.post_vars.get("versao"), 64))
        acao = u"desativado" if alterado["ativo"] == "N" else u"reativado"
        session.flash = {"tipo": "sucesso", "mensagem": u"Script %s %s." % (alterado["nome"], acao)}
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except OperacaoNegada as exc:
        session.flash = {"tipo": "erro", "mensagem": exc.mensagem}
    except RepoConflito:
        session.flash = {"tipo": "aviso", "mensagem": admin_crud.MSG_CONFLITO}
    except RepoErro:
        _log.exception("falha ao alternar script (login=%s id=%r)", ctx["login"], script_id, extra={"acao": _FUNC})
        session.flash = {"tipo": "erro", "mensagem": _MSG_FALHA_ACAO}
    redirect(URL(c="admin_scripts", f="form", args=[script_id]))


def homologacao():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    try:
        dados = servico.homologacao(ctx, _texto(request.args(0), 11))
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    response.title = u"Homologação de %s — SSS" % dados["script"]["nome"]
    response.sss_scripts = [_JS]
    return dict(homolog=dados)


def salvar_homologacao():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    script_id = _texto(request.post_vars.get("id"), 11)
    ids = request.post_vars.get("ambientes")
    ids = (ids if isinstance(ids, list) else ([] if ids is None else [ids]))[:_MAX_IDS]
    try:
        diff, erros = servico.salvar_homologacao(ctx, _ip_origem(), script_id, ids,
                                                 _texto(request.post_vars.get("versao"), 64))
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except RepoErro:
        _log.exception("falha ao salvar homologacao (login=%s id=%r)", ctx["login"], script_id, extra={"acao": _FUNC})
        diff, erros = None, {admin_crud.CAMPO_GERAL: _MSG_FALHA_ACAO}
    if erros:
        session.flash = {"tipo": "erro", "mensagem": erros[admin_crud.CAMPO_GERAL]}
    elif diff:
        session.flash = {"tipo": "sucesso", "mensagem": u"Homologação salva: %s" % diff}
    else:
        session.flash = {"tipo": "aviso", "mensagem": u"Nenhuma alteração para salvar."}
    redirect(URL(c="admin_scripts", f="homologacao", args=[script_id]))


def parametros():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    try:
        dados = servico.parametros(ctx, _texto(request.args(0), 11))
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    response.title = u"Parâmetros de %s — SSS" % dados["script"]["nome"]
    response.sss_scripts = [_JS]
    return dict(vinc=dados)


def salvar_parametros():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    script_id = _texto(request.post_vars.get("id"), 11)
    try:
        descricao, erros = servico.salvar_parametros(ctx, _ip_origem(), script_id,
                                                     _texto(request.post_vars.get("vinculos_json"), _MAX_JSON),
                                                     _texto(request.post_vars.get("versao"), 64))
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except RepoErro:
        _log.exception("falha ao salvar vinculos (login=%s id=%r)", ctx["login"], script_id, extra={"acao": _FUNC})
        descricao, erros = None, {admin_crud.CAMPO_GERAL: _MSG_FALHA_ACAO}
    if erros:
        mensagem = erros.get(admin_crud.CAMPO_GERAL) or u" ".join(sorted(erros.values()))
        session.flash = {"tipo": "erro", "mensagem": mensagem}
    elif descricao:
        session.flash = {"tipo": "sucesso", "mensagem": u"Parâmetros salvos: %s" % descricao}
    else:
        session.flash = {"tipo": "aviso", "mensagem": u"Nenhuma alteração para salvar."}
    redirect(URL(c="admin_scripts", f="parametros", args=[script_id]))


def previa():
    # POST: a configuracao em edicao (e eventuais valores sigilosos) nunca vai para a URL.
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    response.headers["Cache-Control"] = "no-store"
    vinculos_json = request.post_vars.get("vinculos_json")
    try:
        resultado = servico.previa(ctx, _texto(request.post_vars.get("id"), 11),
                                   _texto(vinculos_json, _MAX_JSON) if vinculos_json is not None else None)
    except RepoNaoEncontrado:
        response.status = 404
        return response.json({"argv": None, "erros": {admin_crud.CAMPO_GERAL: u"Script não encontrado."}})
    except AcessoNegado:
        response.status = 403
        return response.json({"argv": None, "erros": {admin_crud.CAMPO_GERAL: u"Acesso negado."}})
    return response.json(resultado)
