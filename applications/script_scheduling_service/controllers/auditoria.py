# -*- coding: utf-8 -*-
"""Trilha de auditoria e painel de agentes (README §4.3.D VIEW_AUDIT, §4.4, §13). Somente leitura:
nenhuma action altera agentes. Regras em modules/auditoria_service.py e modules/agentes_service.py.

CSRF e Origin de todo POST sao validados em models/10_security.py.
"""
from gluon import current

import agentes_service
import auditoria_service
import ticket_service
import ui_helpers
from admin_crud import AcessoNegado
from auditoria_service import FiltrosInvalidos
from repo_errors import RepoErro

_FUNC = "VIEW_AUDIT"
_JS_AGENTES = "js/app/agentes.js"
_TAMANHOS = (20, 50, 100)
_EXTENSOES_AGENTES = ("html", "load")
_MSG_FALHA_LISTA = u"Não foi possível carregar a trilha de auditoria. Tente novamente em instantes."
_MSG_FALHA_EXPORTAR = u"Não foi possível exportar a trilha de auditoria. Tente novamente em instantes."
_MSG_FILTROS_EXPORTAR = u"Corrija os filtros antes de exportar."
_MSG_FALHA_AGENTES = u"Não foi possível carregar os agentes. Tente novamente em instantes."
# Intervalo da atualizacao automatica do painel de agentes (F6.1).
INTERVALO_AGENTES_S = 15


def _exigir_metodo(*permitidos):
    if (request.env.request_method or "GET").upper() not in permitidos:
        raise HTTP(405, **response.headers)


def _negado():
    raise HTTP(403, u"Acesso negado.", **response.headers)


def _texto(valor, limite):
    valor = valor[-1] if isinstance(valor, list) and valor else valor
    return valor[:limite] if isinstance(valor, str) else None


def _entrada(fonte):
    return dict((c, _texto(fonte.get(c), 50)) for c in auditoria_service.CAMPOS_FILTRO)


def lista():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    pagina = ui_helpers.sanitizar_pagina(_texto(request.get_vars.get("pagina"), 9))
    tamanho = ui_helpers.sanitizar_tamanho(_texto(request.get_vars.get("tamanho"), 3), _TAMANHOS)
    entrada = _entrada(request.get_vars)
    erro = None
    try:
        resultado = auditoria_service.listar(ctx, entrada, pagina, tamanho)
    except AcessoNegado:
        _negado()
    except RepoErro:
        _log.exception("falha ao listar a auditoria (login=%s)", ctx["login"], extra={"acao": _FUNC})
        filtros, erros = auditoria_service.filtros_padrao(entrada)
        resultado = {"filtros": filtros, "erros": erros, "itens": [], "total": 0, "pagina": 1,
                     "tamanho": tamanho}
        erro = _MSG_FALHA_LISTA
    if resultado["erros"] and not erro:
        response.flash = {"tipo": "erro", "mensagem": u"Corrija os filtros destacados."}
    pode_ver_tickets = ticket_service.pode_consultar(ctx)
    for item in resultado["itens"]:
        item["link"] = auditoria_service.link_entidade(ctx, item["entity"], item["entity_id"],
                                                       pode_ver_tickets)
    response.title = u"Auditoria — SSS"
    return dict(resultado=resultado, erro=erro, tamanho=tamanho, filtros_ativos=resultado["filtros"],
                query_params=dict(resultado["filtros"], tamanho=tamanho),
                acoes=auditoria_service.ACOES, entidades=auditoria_service.ENTIDADES,
                limite_exportacao=auditoria_service.LIMITE_EXPORTACAO)


def exportar():
    # POST com CSRF: a exportacao grava auditoria, e GET nunca altera estado (AGENTS §3.4).
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    entrada = _entrada(request.post_vars)
    voltar = URL(c="auditoria", f="lista", vars=dict((k, v) for k, v in entrada.items() if v))
    try:
        nome, linhas, blocos = auditoria_service.exportar_csv(ctx, _ip_origem(), entrada)
    except AcessoNegado:
        _negado()
    except FiltrosInvalidos:
        session.flash = {"tipo": "erro", "mensagem": _MSG_FILTROS_EXPORTAR}
        redirect(voltar)
    except RepoErro:
        _log.exception("falha ao exportar a auditoria (login=%s)", ctx["login"], extra={"acao": "AUDIT_EXPORT"})
        session.flash = {"tipo": "erro", "mensagem": _MSG_FALHA_EXPORTAR}
        redirect(voltar)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = 'attachment; filename="%s"' % nome
    response.headers["Cache-Control"] = "no-store"
    # Iteravel: o web2py o devolve ao WSGI como corpo em streaming, bloco a bloco.
    return blocos


def agentes():
    _exigir_metodo("GET", "HEAD")
    if request.extension not in _EXTENSOES_AGENTES:
        raise HTTP(404, **response.headers)
    ctx = _exigir_func(_FUNC)
    erro = None
    try:
        painel = agentes_service.painel(ctx)
    except AcessoNegado:
        _negado()
    except RepoErro:
        _log.exception("falha ao montar o painel de agentes (login=%s)", ctx["login"], extra={"acao": _FUNC})
        painel = {"agentes": [], "resumo": {}, "agora": None}
        erro = _MSG_FALHA_AGENTES
    dados = dict(painel=painel, erro=erro, url_fragmento=URL(c="auditoria", f="agentes", extension="load"),
                 intervalo_s=INTERVALO_AGENTES_S)
    if request.extension == "load":
        return dados
    response.title = u"Agentes — SSS"
    response.sss_scripts = [_JS_AGENTES]
    # A aba Agentes pertence ao item de menu Auditoria (auditoria/lista).
    for secao in response.sss_menu or []:
        for item in secao["itens"]:
            if item["rota"] == ("auditoria", "lista"):
                item["active"] = True
    dados["legenda"] = agentes_service.legenda()
    dados["limiares"] = current.sss_cfg.agent
    return dados
