# -*- coding: utf-8 -*-
"""Cadastro de scripts, homologacao e vinculo de parametros (README §4.3.A, §6.3, §8.5, MANAGE_SCRIPTS).

Padrao em docs/ADMIN_CRUD_PATTERN.md. Regras ficam em modules/admin_scripts_service.py; CSRF e Origin
de todo POST sao validados em models/10_security.py. Listas enviadas pelo cliente sao revalidadas inteiras.
"""
import admin_crud
import admin_scripts_service as servico
import path_guard
import ui_helpers
from admin_crud import AccessDenied, OperationDenied
from repo_errors import RepoConflict, RepoError, RepoNotFound

_FUNC = "MANAGE_SCRIPTS"
_TAMANHOS = (20, 50, 100)
_CAMPOS = ("name", "description", "script_group", "category", "stage", "interpreter", "path_file", "param_type",
           "max_parallel_env", "timeout_s", "version")
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
    return {"id": None, "name": "", "description": "", "script_group": "", "category": "", "stage": "",
            "interpreter": path_guard.ALLOWLIST[0], "path_file": "",
            "param_type": "NAMED",
            "max_parallel_env": 1, "timeout_s": "", "active": "Y", "version": "", "agendamentos_ativos": 0,
            "obs_validacao": servico.VALIDATION_NOTE}


def _pagina_form(ctx, dados, erros=None):
    response.title = (u"Script %s — SSS" % dados["name"]) if dados.get("id") else u"Novo script — SSS"
    response.view = "admin_scripts/form.html"
    erros = erros or {}
    campos = [{"name": n, "erro": erros.get(n)} for n in ("name", "description", "script_group", "category", "stage",
                                                          "interpreter", "path_file", "param_type",
                                                          "max_parallel_env", "timeout_s")]
    return dict(scr=dados, erros=erros, erro_geral=erros.get(admin_crud.GENERAL_FIELD), interpretadores=servico.INTERPRETER_LABELS,
                tipos_param=servico.PARAM_TYPE_LABELS, foco_campo=ui_helpers.primeiro_campo_invalido(campos),
                aviso_desativacao=servico.DEACTIVATION_WARNING)


def index():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    filtros = servico.normalize_filters(request.get_vars)
    pagina = ui_helpers.sanitizar_pagina(_texto(request.get_vars.get("pagina"), 9))
    tamanho = ui_helpers.sanitizar_tamanho(_texto(request.get_vars.get("tamanho"), 3), _TAMANHOS)
    erro = None
    try:
        resultado = servico.list_page(ctx, filtros, pagina, tamanho)
    except AccessDenied:
        _negado()
    except RepoError:
        _log.exception("falha ao listar scripts (login=%s)", ctx["login"], extra={"action": _FUNC})
        resultado = {"itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        erro = _MSG_FALHA_LISTA
    response.title = u"Scripts — SSS"
    return dict(resultado=resultado, erro=erro, filtros_ativos=filtros, tamanho=tamanho, interpretadores=servico.INTERPRETER_LABELS,
                query_params=dict(filtros, tamanho=tamanho))


def form():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    try:
        dados = servico.form(ctx, _texto(request.args(0), 11))
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    return _pagina_form(ctx, dados)


def save():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    script_id = _texto(request.post_vars.get("id"), 11)
    # Teto acima do maior limite do service (path_file: 500), para que o excesso seja recusado (AGENTS §3.4).
    enviados = dict((c, _texto(request.post_vars.get(c), 600)) for c in _CAMPOS)
    aviso = None
    try:
        salvo_id, erros, aviso = servico.save(ctx, _ip_origem(), script_id, enviados)
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except OperationDenied as exc:
        salvo_id, erros = None, {admin_crud.GENERAL_FIELD: str(exc)}
    except RepoError:
        _log.exception("falha ao salvar script (login=%s id=%r)", ctx["login"], script_id, extra={"action": _FUNC})
        salvo_id, erros = None, {admin_crud.GENERAL_FIELD: admin_crud.MSG_FAILURE}
    if not erros:
        mensagem = u"Script salvo com sucesso." + (u" " + aviso if aviso else u"")
        session.flash = {"tipo": "aviso" if aviso else "sucesso", "mensagem": mensagem}
        redirect(URL(c="admin_scripts", f="form", args=[salvo_id]))
    try:
        dados = servico.form(ctx, script_id) if script_id else servico.form(ctx)
    except RepoError:
        dados = _vazio_form(ctx)
    if admin_crud.GENERAL_FIELD not in erros:
        dados = dict(dados, **dict((c, enviados[c] or "") for c in _CAMPOS if c != "version"))
        if script_id:
            dados["version"] = enviados["version"] or ""
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"tipo": "erro", "mensagem": erros.get(admin_crud.GENERAL_FIELD)
                      or ui_helpers.mensagem("formulario")}
    return _pagina_form(ctx, dados, erros)


def toggle_active():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    script_id = _texto(request.post_vars.get("id"), 11)
    try:
        alterado = servico.toggle_active(ctx, _ip_origem(), script_id, _texto(request.post_vars.get("version"), 64))
        acao = u"desativado" if alterado["active"] == "N" else u"reativado"
        session.flash = {"tipo": "sucesso", "mensagem": u"Script %s %s." % (alterado["name"], acao)}
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except OperationDenied as exc:
        session.flash = {"tipo": "erro", "mensagem": exc.message}
    except RepoConflict:
        session.flash = {"tipo": "aviso", "mensagem": admin_crud.MSG_CONFLICT}
    except RepoError:
        _log.exception("falha ao alternar script (login=%s id=%r)", ctx["login"], script_id, extra={"action": _FUNC})
        session.flash = {"tipo": "erro", "mensagem": _MSG_FALHA_ACAO}
    redirect(URL(c="admin_scripts", f="form", args=[script_id]))


def homologation():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    try:
        dados = servico.homologation(ctx, _texto(request.args(0), 11))
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    response.title = u"Homologação de %s — SSS" % dados["script"]["name"]
    response.sss_scripts = [_JS]
    return dict(homolog=dados)


def save_homologation():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    script_id = _texto(request.post_vars.get("id"), 11)
    ids = request.post_vars.get("environments")
    ids = (ids if isinstance(ids, list) else ([] if ids is None else [ids]))[:_MAX_IDS]
    try:
        diff, erros = servico.save_homologation(ctx, _ip_origem(), script_id, ids,
                                                 _texto(request.post_vars.get("version"), 64))
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except RepoError:
        _log.exception("falha ao salvar homologacao (login=%s id=%r)", ctx["login"], script_id, extra={"action": _FUNC})
        diff, erros = None, {admin_crud.GENERAL_FIELD: _MSG_FALHA_ACAO}
    if erros:
        session.flash = {"tipo": "erro", "mensagem": erros[admin_crud.GENERAL_FIELD]}
    elif diff:
        session.flash = {"tipo": "sucesso", "mensagem": u"Homologação salva: %s" % diff}
    else:
        session.flash = {"tipo": "aviso", "mensagem": u"Nenhuma alteração para salvar."}
    redirect(URL(c="admin_scripts", f="homologation", args=[script_id]))


def parameters():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    try:
        dados = servico.parameters(ctx, _texto(request.args(0), 11))
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    response.title = u"Parâmetros de %s — SSS" % dados["script"]["name"]
    response.sss_scripts = [_JS]
    return dict(vinc=dados)


def save_parameters():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    script_id = _texto(request.post_vars.get("id"), 11)
    try:
        descricao, erros = servico.save_parameters(ctx, _ip_origem(), script_id,
                                                     _texto(request.post_vars.get("vinculos_json"), _MAX_JSON),
                                                     _texto(request.post_vars.get("version"), 64))
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except RepoError:
        _log.exception("falha ao salvar vinculos (login=%s id=%r)", ctx["login"], script_id, extra={"action": _FUNC})
        descricao, erros = None, {admin_crud.GENERAL_FIELD: _MSG_FALHA_ACAO}
    if erros:
        mensagem = erros.get(admin_crud.GENERAL_FIELD) or u" ".join(sorted(erros.values()))
        session.flash = {"tipo": "erro", "mensagem": mensagem}
    elif descricao:
        session.flash = {"tipo": "sucesso", "mensagem": u"Parâmetros salvos: %s" % descricao}
    else:
        session.flash = {"tipo": "aviso", "mensagem": u"Nenhuma alteração para salvar."}
    redirect(URL(c="admin_scripts", f="parameters", args=[script_id]))


def preview():
    # POST: a configuracao em edicao (e eventuais valores sigilosos) nunca vai para a URL.
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    response.headers["Cache-Control"] = "no-store"
    vinculos_json = request.post_vars.get("vinculos_json")
    try:
        resultado = servico.preview(ctx, _texto(request.post_vars.get("id"), 11),
                                   _texto(vinculos_json, _MAX_JSON) if vinculos_json is not None else None)
    except RepoNotFound:
        response.status = 404
        return response.json({"argv": None, "erros": {admin_crud.GENERAL_FIELD: u"Script não encontrado."}})
    except AccessDenied:
        response.status = 403
        return response.json({"argv": None, "erros": {admin_crud.GENERAL_FIELD: u"Acesso negado."}})
    return response.json(resultado)
