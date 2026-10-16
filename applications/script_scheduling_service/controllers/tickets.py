# -*- coding: utf-8 -*-
"""Disparo de script e tickets (README §5). Regras de negocio ficam em modules/ticket_service.py.

CSRF e Origin de todo POST sao validados em models/10_security.py.
"""
from gluon import current

import ticket_service
import ui_helpers
from repo_errors import RepoErro, RepoNaoEncontrado
from ticket_service import AcessoNegado, ErroReexecucao

_PREFIXO_PARAM = "p_"
_JS_DISPARO = "js/app/disparo.js"
_JS_TICKETS = "js/app/tickets.js"
_JS_LOG = "js/app/log_viewer.js"
_TAMANHOS = (20, 50, 100)
_EXTENSOES_LISTA = ("html", "load")
_MSG_FALHA_LISTA = u"Não foi possível carregar os tickets. Tente novamente em instantes."
_MSG_FALHA_CANCELAR = u"Não foi possível cancelar o ticket. Tente novamente em instantes."
_MSG_REEXECUCAO_REVISAR = (u"Não foi possível reexecutar automaticamente: o cadastro do script pode ter mudado "
                           u"desde a execução original. Revise os campos destacados e crie o ticket novamente.")
_TIPO_FLASH_CANCELAMENTO = {"TERMINAL": "aviso", "CANCELADO": "sucesso", "SINALIZADO": "sucesso",
                            "JA_SINALIZADO": "aviso"}


def _metodo():
    return (request.env.request_method or "GET").upper()


def _exigir_metodo(*permitidos):
    if _metodo() not in permitidos:
        raise HTTP(405, **response.headers)


def _negado():
    raise HTTP(403, u"Acesso negado.", **response.headers)


def _nao_encontrado():
    raise HTTP(404, u"Ticket não encontrado.", **response.headers)


def _exigir_consulta():
    ctx = _exigir_login()
    if not ticket_service.pode_consultar(ctx):
        _log.warning("acesso negado (login=%s funcionalidade=VER_LOGS|EXEC_SCRIPT caminho=%s ip=%s)",
                     ctx["login"], request.env.path_info, _ip_origem(), extra={"acao": "RBAC"})
        _negado()
    return ctx


def _texto(valor, limite):
    valor = valor[-1] if isinstance(valor, list) and valor else valor
    return valor[:limite] if isinstance(valor, str) else None


def _respostas_post():
    respostas = {}
    for chave, valor in request.post_vars.items():
        if isinstance(chave, str) and chave.startswith(_PREFIXO_PARAM):
            respostas[chave[len(_PREFIXO_PARAM):]] = valor
    return respostas


def _pagina_novo(ctx, script_id, ambiente, valores=None, erros=None, prioridade=None, scheduled_at=None,
                 reexecucao_de=None, avisos=None):
    response.title = u"Disparar script — SSS"
    response.sss_scripts = [_JS_DISPARO]
    erros = erros or {}
    dados = dict(etapa=1, grupos=[], script=None, ambientes=[], form=None, erros=erros,
                 erro_geral=erros.get(ticket_service.CAMPO_GERAL), prioridade=prioridade,
                 scheduled_at=scheduled_at or "", foco_campo=None, reexecucao_de=reexecucao_de,
                 tem_ultima=False, usou_ultima=avisos is not None)
    if not script_id:
        dados["grupos"] = ticket_service.scripts_disponiveis(ctx)
        return dados
    script, ambientes = ticket_service.ambientes_disponiveis(ctx, script_id)
    dados.update(etapa=2, script=script, ambientes=ambientes)
    if not ambiente:
        return dados
    form = ticket_service.preparar_formulario(ctx, script_id, ambiente, valores, erros, avisos)
    dados["tem_ultima"] = not reexecucao_de and ticket_service.tem_ultima_execucao(ctx, script_id, ambiente)
    campos = [{"nome": c["nome"], "erro": c["erro"]} for c in form["campos"]]
    campos.append({"nome": "prioridade", "erro": erros.get(ticket_service.CAMPO_PRIORIDADE)})
    campos.append({"nome": "scheduled_at", "erro": erros.get(ticket_service.CAMPO_AGENDAMENTO)})
    dados.update(etapa=3, form=form, foco_campo=ui_helpers.primeiro_campo_invalido(campos))
    return dados


def novo():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func("EXEC_SCRIPT")
    reexecucao = _texto(request.get_vars.get("reexecucao"), 10)
    try:
        if reexecucao:
            dados = ticket_service.preparar_reexecucao(ctx, reexecucao)
            return _pagina_novo(ctx, dados["script_id"], dados["ambiente"], dados["valores"], dados["erros"],
                                dados["prioridade"], reexecucao_de=dados["ticket_id"])
        script_id = _texto(request.get_vars.get("script_id"), 10)
        ambiente = _texto(request.get_vars.get("ambiente"), 30)
        if script_id and ambiente and request.get_vars.get("ultima") == "1":
            # README §5.4: respostas da ultima execucao propria, sem sensiveis; nada e gravado.
            valores, avisos = ticket_service.ultimas_respostas(ctx, script_id, ambiente)
            return _pagina_novo(ctx, script_id, ambiente, valores, avisos=avisos)
        return _pagina_novo(ctx, script_id, ambiente)
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()


def criar():
    _exigir_metodo("POST")
    ctx = _exigir_func("EXEC_SCRIPT")
    script_id = _texto(request.post_vars.get("script_id"), 10)
    ambiente = _texto(request.post_vars.get("ambiente"), 30)
    prioridade = _texto(request.post_vars.get("prioridade"), 10)
    scheduled_at = _texto(request.post_vars.get("scheduled_at"), 40)
    reexecucao_de = _texto(request.post_vars.get("reexecucao_de"), 10)
    respostas = _respostas_post()
    try:
        ticket_id, erros = ticket_service.criar_ticket(ctx, _ip_origem(), script_id, ambiente, respostas,
                                                       prioridade, scheduled_at, reexecucao_de)
        if ticket_id is not None:
            session.flash = {"tipo": "sucesso", "mensagem": u"Ticket #%s criado com sucesso." % ticket_id}
            redirect(URL(c="tickets", f="detalhe", args=[ticket_id]))
        # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
        response.flash = {"tipo": "erro", "mensagem": ui_helpers.mensagem("formulario")}
        response.view = "tickets/novo.html"
        return _pagina_novo(ctx, script_id, ambiente, respostas, erros, prioridade, scheduled_at,
                            reexecucao_de or None)
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()


def previa():
    # POST porque o corpo pode conter valores sensiveis: nunca na URL nem no log de acesso.
    _exigir_metodo("POST")
    ctx = _exigir_func("EXEC_SCRIPT")
    respostas = request.post_vars.get("respostas")
    try:
        # Mesmo endpoint da previa do comando e do resumo em frase do modal (README §5.4).
        dados = ticket_service.resumo_disparo(ctx, _texto(request.post_vars.get("script_id"), 10),
                                              _texto(request.post_vars.get("ambiente"), 30),
                                              respostas if isinstance(respostas, dict) else {},
                                              _texto(request.post_vars.get("prioridade"), 10),
                                              _texto(request.post_vars.get("scheduled_at"), 40))
    except AcessoNegado:
        response.status = 403
        return response.json({"erro": ui_helpers.mensagem("sem_permissao")})
    return response.json(dados)


def lista():
    _exigir_metodo("GET", "HEAD")
    if request.extension not in _EXTENSOES_LISTA:
        raise HTTP(404, **response.headers)
    ctx = _exigir_consulta()
    filtros = ticket_service.normalizar_filtros(request.get_vars)
    pagina = ui_helpers.sanitizar_pagina(_texto(request.get_vars.get("pagina"), 9))
    tamanho = ui_helpers.sanitizar_tamanho(_texto(request.get_vars.get("tamanho"), 3), _TAMANHOS)
    erro = None
    try:
        resultado = ticket_service.listar(ctx, filtros, pagina, tamanho)
    except AcessoNegado:
        _negado()
    except RepoErro:
        _log.exception("falha ao listar tickets (login=%s)", ctx["login"], extra={"acao": "TICKET_LISTAR"})
        resultado = {"itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        erro = _MSG_FALHA_LISTA
    query_params = dict(filtros, tamanho=tamanho)
    dados = dict(resultado=resultado, erro=erro, pagina=resultado["pagina"], tamanho=tamanho,
                 query_params=query_params,
                 url_fragmento=URL(c="tickets", f="lista", extension="load",
                                   vars=dict(query_params, pagina=resultado["pagina"])))
    if request.extension == "load":
        return dados
    response.title = u"Tickets — SSS"
    response.sss_scripts = [_JS_TICKETS]
    dados["filtros_ativos"] = filtros
    dados["opcoes"] = ticket_service.opcoes_filtro(ctx)
    return dados


def detalhe():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_consulta()
    try:
        ticket = ticket_service.detalhe(ctx, request.args(0))
    except RepoNaoEncontrado:
        _nao_encontrado()
    response.title = u"Ticket #%s — SSS" % ticket["id"]
    response.sss_scripts = [_JS_TICKETS, _JS_LOG]
    visor_log = {
        "url_chunk": URL(c="logs", f="chunk", vars={"ticket_id": ticket["id"]}),
        "url_baixar": URL(c="logs", f="baixar", vars={"ticket_id": ticket["id"]}),
        "intervalo_s": current.sss_cfg.web.log_poll_interval_s,
        "max_chars": ticket_service.LOG_MAX_CHARS,
    }
    return dict(ticket=ticket, visor_log=visor_log)


def cancelar():
    _exigir_metodo("POST")
    ctx = _exigir_login()
    ticket_id = _texto(request.post_vars.get("ticket_id"), 10)
    try:
        resultado = ticket_service.cancelar(ctx, _ip_origem(), ticket_id)
        session.flash = {"tipo": _TIPO_FLASH_CANCELAMENTO[resultado],
                         "mensagem": ticket_service.MSG_CANCELAMENTO[resultado]}
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except RepoErro:
        session.flash = {"tipo": "erro", "mensagem": _MSG_FALHA_CANCELAR}
    # CANC_TICKET sem VER_LOGS cancela sem poder ver o ticket (README §4.3.C): volta ao painel.
    if ticket_service.visivel(ctx, ticket_id):
        redirect(URL(c="tickets", f="detalhe", args=[ticket_id]))
    redirect(URL(c="default", f="index"))


def reexecutar():
    _exigir_metodo("POST")
    ctx = _exigir_func("EXEC_SCRIPT")
    ticket_id = _texto(request.post_vars.get("ticket_id"), 10)
    try:
        novo_id = ticket_service.reexecutar(ctx, _ip_origem(), ticket_id)
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except ErroReexecucao as e:
        session.flash = {"tipo": "aviso", "mensagem": _MSG_REEXECUCAO_REVISAR}
        redirect(URL(c="tickets", f="novo", vars={"reexecucao": e.ticket_id}))
    session.flash = {"tipo": "sucesso",
                     "mensagem": u"Ticket #%s criado como reexecução do ticket #%s." % (novo_id, ticket_id)}
    redirect(URL(c="tickets", f="detalhe", args=[novo_id]))
