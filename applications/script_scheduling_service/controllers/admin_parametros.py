# -*- coding: utf-8 -*-
"""Dicionario de parametros (README §6, MANAGE_PARAMETERS). Padrao em docs/ADMIN_CRUD_PATTERN.md.

Regras ficam em modules/admin_parameters_service.py; CSRF e Origin de todo POST sao validados em
models/10_security.py. O editor de opcoes do cliente e conveniencia: o servidor revalida tudo.
"""
import admin_crud
import admin_parameters_service as servico
import ui_helpers
from admin_crud import AccessDenied, OperationDenied
from repo_errors import RepoConflict, RepoError, RepoNotFound

_FUNC = "MANAGE_PARAMETERS"
_TAMANHOS = (20, 50, 100)
_CAMPOS = ("code", "param_flag", "label", "description", "component_type", "options_json", "default_value",
           "remover_padrao", "validation_regex", "sensitive", "version")
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
    response.title = (u"Parâmetro %s — SSS" % dados["code"]) if dados.get("id") else u"Novo parâmetro — SSS"
    response.view = "admin_parametros/form.html"
    response.sss_scripts = [_JS]
    erros = erros or {}
    campos = [{"name": n, "erro": erros.get(n)} for n in ("code", "param_flag", "label", "description",
                                                          "component_type", "options_json", "validation_regex",
                                                          "default_value")]
    return dict(prm=dados, erros=erros, erro_geral=erros.get(admin_crud.GENERAL_FIELD),
                foco_campo=ui_helpers.primeiro_campo_invalido(campos), tipos=servico.TYPE_LABELS,
                aviso_sensivel=servico.SENSITIVE_WARNING)


def lista():
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
        _log.exception("falha ao listar parametros (login=%s)", ctx["login"], extra={"action": _FUNC})
        resultado = {"itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        erro = _MSG_FALHA_LISTA
    response.title = u"Parâmetros — SSS"
    return dict(resultado=resultado, erro=erro, filtros_ativos=filtros, tamanho=tamanho, tipos=servico.TYPE_LABELS,
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


def salvar():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    parametro_id = _texto(request.post_vars.get("id"), 11)
    enviados = _enviados()
    try:
        _salvo, erros = servico.save(ctx, _ip_origem(), parametro_id, enviados)
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except RepoError:
        _log.exception("falha ao salvar parametro (login=%s id=%r)", ctx["login"], parametro_id, extra={"action": _FUNC})
        erros = {admin_crud.GENERAL_FIELD: admin_crud.MSG_FAILURE}
    if not erros:
        session.flash = {"tipo": "sucesso", "mensagem": u"Parâmetro salvo com sucesso."}
        redirect(URL(c="admin_parametros", f="lista"))
    try:
        dados = servico.form(ctx, parametro_id) if parametro_id else servico.form(ctx)
    except RepoError:
        dados = {"id": None, "code": "", "param_flag": "", "label": "", "description": "",
                 "component_type": "TEXT", "options_json": "", "default_value": "", "tem_padrao": False,
                 "validation_regex": "", "sensitive": "N", "active": "Y", "version": "", "vinculos": [],
                 "pode_regex": ctx.get("is_admin") is True}
    if admin_crud.GENERAL_FIELD not in erros:
        reapresentar = dict((c, enviados[c] or "") for c in ("param_flag", "label", "description", "component_type",
                                                             "options_json", "validation_regex"))
        reapresentar["sensitive"] = "Y" if enviados["sensitive"] == "Y" else "N"
        # Padrao de parametro sensivel nunca volta ao HTML.
        reapresentar["default_value"] = "" if reapresentar["sensitive"] == "Y" else (enviados["default_value"] or "")
        if not dados.get("pode_regex"):
            reapresentar.pop("validation_regex")
        dados = dict(dados, **reapresentar)
        if not parametro_id:
            dados["code"] = enviados["code"] or ""
        else:
            dados["version"] = enviados["version"] or ""
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"tipo": "erro", "mensagem": erros.get(admin_crud.GENERAL_FIELD)
                      or ui_helpers.mensagem("formulario")}
    return _pagina_form(ctx, dados, erros)


def alternar_ativo():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    parametro_id = _texto(request.post_vars.get("id"), 11)
    try:
        alterado = servico.toggle_active(ctx, _ip_origem(), parametro_id, _texto(request.post_vars.get("version"), 64))
        acao = u"desativado" if alterado["active"] == "N" else u"reativado"
        session.flash = {"tipo": "sucesso", "mensagem": u"Parâmetro %s %s." % (alterado["code"], acao)}
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except OperationDenied as exc:
        session.flash = {"tipo": "erro", "mensagem": exc.message}
    except RepoConflict:
        session.flash = {"tipo": "aviso", "mensagem": admin_crud.MSG_CONFLICT}
    except RepoError:
        _log.exception("falha ao alternar parametro (login=%s id=%r)", ctx["login"], parametro_id, extra={"action": _FUNC})
        session.flash = {"tipo": "erro", "mensagem": _MSG_FALHA_ACAO}
    redirect(URL(c="admin_parametros", f="form", args=[parametro_id]))


def testar():
    # POST: a configuracao em edicao e o valor de teste nunca vao para a URL nem para o log de acesso.
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    response.headers["Cache-Control"] = "no-store"
    try:
        resultado = servico.test_regex(ctx, _texto(request.post_vars.get("id"), 11), _enviados(),
                                   _texto(request.post_vars.get("valor_teste"), 1000))
    except RepoNotFound:
        response.status = 404
        return response.json({"ok": False, "erro": u"Parâmetro não encontrado."})
    except AccessDenied:
        response.status = 403
        return response.json({"ok": False, "erro": u"Acesso negado."})
    return response.json(resultado)
