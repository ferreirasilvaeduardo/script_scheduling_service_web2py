# -*- coding: utf-8 -*-
"""Trilha de auditoria e painel de agentes (README §4.3.D VIEW_AUDIT, §4.4, §13). Somente leitura:
nenhuma action altera agentes. Regras em modules/audit_service.py e modules/agents_service.py.

CSRF e Origin de todo POST sao validados em models/10_security.py.
"""
from gluon import current

import agents_service
import audit_service
import ticket_service
import ui_helpers
from admin_crud import AccessDenied
from audit_service import InvalidFilters
from repo_errors import RepoError

_FUNC = "VIEW_AUDIT"
_JS_AGENTES = "js/app/agents.js"
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
    return dict((c, _texto(fonte.get(c), 50)) for c in audit_service.FILTER_FIELDS)


def index():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    pagina = ui_helpers.sanitizar_pagina(_texto(request.get_vars.get("page"), 9))
    tamanho = ui_helpers.sanitizar_tamanho(_texto(request.get_vars.get("size"), 3), _TAMANHOS)
    entrada = _entrada(request.get_vars)
    erro = None
    try:
        resultado = audit_service.list_page(ctx, entrada, pagina, tamanho)
    except AccessDenied:
        _negado()
    except RepoError:
        _log.exception("falha ao listar a auditoria (login=%s)", ctx["login"], extra={"action": _FUNC})
        filtros, erros = audit_service.default_filters(entrada)
        resultado = {"filters": filtros, "errors": erros, "items": [], "total": 0, "page": 1,
                     "size": tamanho}
        erro = _MSG_FALHA_LISTA
    if resultado["errors"] and not erro:
        response.flash = {"kind": "error", "message": u"Corrija os filtros destacados."}
    pode_ver_tickets = ticket_service.can_query(ctx)
    for item in resultado["items"]:
        item["link"] = audit_service.entity_link(ctx, item["entity"], item["entity_id"],
                                                       pode_ver_tickets)
    response.title = u"Auditoria — SSS"
    return dict(result=resultado, error=erro, size=tamanho, active_filters=resultado["filters"],
                query_params=dict(resultado["filters"], size=tamanho),
                actions=audit_service.ACTIONS, entities=audit_service.ENTITIES,
                export_limit=audit_service.EXPORT_LIMIT)


def export():
    # POST com CSRF: a exportacao grava auditoria, e GET nunca altera estado (AGENTS §3.4).
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    entrada = _entrada(request.post_vars)
    voltar = URL(c="audit", f="index", vars=dict((k, v) for k, v in entrada.items() if v))
    try:
        nome, linhas, blocos = audit_service.export_csv(ctx, _ip_origem(), entrada)
    except AccessDenied:
        _negado()
    except InvalidFilters:
        session.flash = {"kind": "error", "message": _MSG_FILTROS_EXPORTAR}
        redirect(voltar)
    except RepoError:
        _log.exception("falha ao exportar a auditoria (login=%s)", ctx["login"], extra={"action": "AUDIT_EXPORT"})
        session.flash = {"kind": "error", "message": _MSG_FALHA_EXPORTAR}
        redirect(voltar)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = 'attachment; filename="%s"' % nome
    response.headers["Cache-Control"] = "no-store"
    # Iteravel: o web2py o devolve ao WSGI como corpo em streaming, bloco a bloco.
    return blocos


def agents():
    _exigir_metodo("GET", "HEAD")
    if request.extension not in _EXTENSOES_AGENTES:
        raise HTTP(404, **response.headers)
    ctx = _exigir_func(_FUNC)
    erro = None
    try:
        painel = agents_service.dashboard(ctx)
    except AccessDenied:
        _negado()
    except RepoError:
        _log.exception("falha ao montar o painel de agentes (login=%s)", ctx["login"], extra={"action": _FUNC})
        painel = {"agents": [], "summary": {}, "now": None}
        erro = _MSG_FALHA_AGENTES
    dados = dict(dashboard=painel, error=erro, fragment_url=URL(c="audit", f="agents", extension="load"),
                 interval_s=INTERVALO_AGENTES_S)
    if request.extension == "load":
        return dados
    response.title = u"Agentes — SSS"
    response.sss_scripts = [_JS_AGENTES]
    # A aba Agentes pertence ao item de menu Auditoria (audit/index).
    for secao in response.sss_menu or []:
        for item in secao["items"]:
            if item["route"] == ("audit", "index"):
                item["active"] = True
    dados["legend"] = agents_service.legend()
    dados["thresholds"] = current.sss_cfg.agent
    return dados
