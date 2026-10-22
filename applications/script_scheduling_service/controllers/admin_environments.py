# -*- coding: utf-8 -*-
"""Cadastro de ambientes (README §4.3.D MANAGE_ENVIRONMENTS). Padrao em docs/ADMIN_CRUD_PATTERN.md.

Regras ficam em modules/admin_environments_service.py; CSRF e Origin de todo POST sao validados
em models/10_security.py.
"""
import admin_environments_service as servico
import admin_crud
import ui_helpers
from admin_crud import AccessDenied
from repo_errors import RepoConflict, RepoError, RepoNotFound

_FUNC = "MANAGE_ENVIRONMENTS"
_TAMANHOS = (20, 50, 100)
_MSG_FALHA_LISTA = u"Não foi possível carregar os ambientes. Tente novamente em instantes."
_MSG_FALHA_ALTERNAR = u"Não foi possível alterar a situação do ambiente. Tente novamente em instantes."


def _exigir_metodo(*permitidos):
    if (request.env.request_method or "GET").upper() not in permitidos:
        raise HTTP(405, **response.headers)


def _negado():
    raise HTTP(403, u"Acesso negado.", **response.headers)


def _nao_encontrado():
    raise HTTP(404, u"Ambiente não encontrado.", **response.headers)


def _texto(valor, limite):
    valor = valor[-1] if isinstance(valor, list) and valor else valor
    return valor[:limite] if isinstance(valor, str) else None


def _pagina_form(ctx, dados, erros=None):
    response.title = (u"Ambiente %s — SSS" % dados["name"]) if dados.get("id") else u"Novo ambiente — SSS"
    response.view = "admin_environments/form.html"
    erros = erros or {}
    campos = [{"name": n, "error": erros.get(n)} for n in ("name", "description", "connection")]
    return dict(amb=dados, erros=erros, erro_geral=erros.get(admin_crud.GENERAL_FIELD),
                foco_campo=ui_helpers.primeiro_campo_invalido(campos),
                aviso_desativacao=servico.DEACTIVATION_WARNING)


def index():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    filtros = servico.normalize_filters(request.get_vars)
    pagina = ui_helpers.sanitizar_pagina(_texto(request.get_vars.get("page"), 9))
    tamanho = ui_helpers.sanitizar_tamanho(_texto(request.get_vars.get("size"), 3), _TAMANHOS)
    erro = None
    try:
        resultado = servico.list_page(ctx, filtros, pagina, tamanho)
    except AccessDenied:
        _negado()
    except RepoError:
        _log.exception("falha ao listar ambientes (login=%s)", ctx["login"], extra={"action": _FUNC})
        resultado = {"itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        erro = _MSG_FALHA_LISTA
    response.title = u"Ambientes — SSS"
    return dict(resultado=resultado, erro=erro, filtros_ativos=filtros, tamanho=tamanho,
                query_params=dict(filtros, size=tamanho))


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
    ambiente_id = _texto(request.post_vars.get("id"), 11)
    enviados = dict((c, _texto(request.post_vars.get(c), 300)) for c in ("name", "description", "connection", "version"))
    try:
        salvo_id, erros = servico.save(ctx, _ip_origem(), ambiente_id, enviados)
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except RepoError:
        _log.exception("falha ao salvar ambiente (login=%s id=%r)", ctx["login"], ambiente_id, extra={"action": _FUNC})
        salvo_id, erros = None, {admin_crud.GENERAL_FIELD: admin_crud.MSG_FAILURE}
    if not erros:
        session.flash = {"kind": "success", "message": u"Ambiente salvo com sucesso."}
        redirect(URL(c="admin_environments", f="index"))
    # Reapresenta o que foi digitado; na edicao o nome e a versao continuam os do registro.
    try:
        dados = servico.form(ctx, ambiente_id) if ambiente_id else servico.form(ctx)
    except RepoError:
        dados = {"id": None, "name": "", "active": "Y", "version": "", "agendamentos_ativos": 0, "scripts_homologados": 0}
    if admin_crud.GENERAL_FIELD not in erros:
        conexao = enviados["connection"] or ""
        # Nunca devolve ao HTML um DSN com credencial digitado por engano.
        dados = dict(dados, description=enviados["description"] or "", connection="" if "@" in conexao else conexao)
        if not ambiente_id:
            dados["name"] = enviados["name"] or ""
        else:
            dados["version"] = enviados["version"] or ""
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"kind": "error", "message": erros.get(admin_crud.GENERAL_FIELD)
                      or ui_helpers.mensagem("form_errors")}
    return _pagina_form(ctx, dados, erros)


def toggle_active():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    ambiente_id = _texto(request.post_vars.get("id"), 11)
    try:
        alterado = servico.toggle_active(ctx, _ip_origem(), ambiente_id, _texto(request.post_vars.get("version"), 64))
        if alterado["active"] == "N":
            session.flash = {"kind": "success", "message": u"Ambiente %s desativado." % alterado["name"]}
        else:
            session.flash = {"kind": "success", "message": u"Ambiente %s reativado." % alterado["name"]}
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except RepoConflict:
        session.flash = {"kind": "warning", "message": admin_crud.MSG_CONFLICT}
    except RepoError:
        _log.exception("falha ao alternar ambiente (login=%s id=%r)", ctx["login"], ambiente_id, extra={"action": _FUNC})
        session.flash = {"kind": "error", "message": _MSG_FALHA_ALTERNAR}
    redirect(URL(c="admin_environments", f="form", args=[ambiente_id]))
