# -*- coding: utf-8 -*-
"""Disparo de script e tickets (README §5). Regras de negocio ficam em modules/ticket_service.py.

CSRF e Origin de todo POST sao validados em models/10_security.py.
"""
from gluon import current

import ticket_service
import ui_helpers
from repo_errors import RepoError, RepoNotFound
from ticket_service import AccessDenied, RerunError

_PREFIXO_PARAM = "p_"
_JS_DISPARO = "js/app/disparo.js"
_JS_TICKETS = "js/app/tickets.js"
_JS_LOG = "js/app/log_viewer.js"
_TAMANHOS = (20, 50, 100)
_EXTENSOES_LISTA = ("html", "load")
_MSG_FALHA_LISTA = u"Não foi possível carregar os tickets. Tente novamente em instantes."
_MSG_FALHA_CANCELAR = u"Não foi possível cancelar o ticket. Tente novamente em instantes."
_MSG_FALHA_SAIDA = u"Não foi possível baixar a saída. Tente novamente em instantes."
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
    if not ticket_service.can_query(ctx):
        _log.warning("acesso negado (login=%s funcionalidade=VIEW_LOGS|EXEC_SCRIPT caminho=%s ip=%s)",
                     ctx["login"], request.env.path_info, _ip_origem(), extra={"action": "RBAC"})
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
                 erro_geral=erros.get(ticket_service.GENERAL_FIELD), prioridade=prioridade,
                 scheduled_at=scheduled_at or "", foco_campo=None, reexecucao_de=reexecucao_de,
                 tem_ultima=False, usou_ultima=avisos is not None)
    if not script_id:
        dados["grupos"] = ticket_service.available_scripts(ctx)
        return dados
    script, ambientes = ticket_service.available_environments(ctx, script_id)
    dados.update(etapa=2, script=script, ambientes=ambientes)
    if not ambiente:
        return dados
    form = ticket_service.prepare_form(ctx, script_id, ambiente, valores, erros, avisos)
    dados["tem_ultima"] = not reexecucao_de and ticket_service.has_last_run(ctx, script_id, ambiente)
    campos = [{"name": c["name"], "erro": c["erro"]} for c in form["campos"]]
    campos.append({"name": "priority", "erro": erros.get(ticket_service.PRIORITY_FIELD)})
    campos.append({"name": "scheduled_at", "erro": erros.get(ticket_service.SCHEDULED_AT_FIELD)})
    dados.update(etapa=3, form=form, foco_campo=ui_helpers.primeiro_campo_invalido(campos))
    return dados


def novo():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func("EXEC_SCRIPT")
    reexecucao = _texto(request.get_vars.get("reexecucao"), 10)
    try:
        if reexecucao:
            dados = ticket_service.prepare_rerun(ctx, reexecucao)
            return _pagina_novo(ctx, dados["script_id"], dados["environment"], dados["valores"], dados["erros"],
                                dados["priority"], reexecucao_de=dados["ticket_id"])
        script_id = _texto(request.get_vars.get("script_id"), 10)
        ambiente = _texto(request.get_vars.get("environment"), 30)
        if script_id and ambiente and request.get_vars.get("ultima") == "1":
            # README §5.4: respostas da ultima execucao propria, sem sensiveis; nada e gravado.
            valores, avisos = ticket_service.last_answers(ctx, script_id, ambiente)
            return _pagina_novo(ctx, script_id, ambiente, valores, avisos=avisos)
        return _pagina_novo(ctx, script_id, ambiente)
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()


def catalogo():
    """Rotinas disponiveis (README §5.8): so leitura, para quem tem EXEC_SCRIPT."""
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func("EXEC_SCRIPT")
    response.title = u"Rotinas disponíveis — SSS"
    response.sss_scripts = [_JS_DISPARO]
    try:
        return dict(grupos=ticket_service.routine_catalog(ctx), erro=None)
    except RepoError:
        _log.exception("falha ao montar o catalogo de rotinas (login=%s)", ctx["login"], extra={"action": "CATALOGO"})
        return dict(grupos=[], erro=ui_helpers.mensagem("falha_interna"))


def historico():
    """Historico do script (README §5.8): so leitura, para quem tem EXEC_SCRIPT."""
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func("EXEC_SCRIPT")
    try:
        dados = ticket_service.script_history(ctx, _texto(request.args(0), 10))
    except RepoNotFound:
        _nao_encontrado()
    response.title = u"Histórico de %s — SSS" % dados["script"]["name"]
    return dict(h=dados)


def criar():
    _exigir_metodo("POST")
    ctx = _exigir_func("EXEC_SCRIPT")
    script_id = _texto(request.post_vars.get("script_id"), 10)
    ambiente = _texto(request.post_vars.get("environment"), 30)
    prioridade = _texto(request.post_vars.get("priority"), 10)
    scheduled_at = _texto(request.post_vars.get("scheduled_at"), 40)
    reexecucao_de = _texto(request.post_vars.get("reexecucao_de"), 10)
    respostas = _respostas_post()
    try:
        ticket_id, erros = ticket_service.create_ticket(ctx, _ip_origem(), script_id, ambiente, respostas,
                                                       prioridade, scheduled_at, reexecucao_de)
        if ticket_id is not None:
            session.flash = {"tipo": "sucesso", "mensagem": u"Ticket #%s criado com sucesso." % ticket_id}
            redirect(URL(c="tickets", f="detalhe", args=[ticket_id]))
        # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
        response.flash = {"tipo": "erro", "mensagem": ui_helpers.mensagem("formulario")}
        response.view = "tickets/novo.html"
        return _pagina_novo(ctx, script_id, ambiente, respostas, erros, prioridade, scheduled_at,
                            reexecucao_de or None)
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()


def previa():
    # POST porque o corpo pode conter valores sensiveis: nunca na URL nem no log de acesso.
    _exigir_metodo("POST")
    ctx = _exigir_func("EXEC_SCRIPT")
    respostas = request.post_vars.get("respostas")
    try:
        # Mesmo endpoint da previa do comando e do resumo em frase do modal (README §5.4).
        dados = ticket_service.trigger_summary(ctx, _texto(request.post_vars.get("script_id"), 10),
                                              _texto(request.post_vars.get("environment"), 30),
                                              respostas if isinstance(respostas, dict) else {},
                                              _texto(request.post_vars.get("priority"), 10),
                                              _texto(request.post_vars.get("scheduled_at"), 40))
    except AccessDenied:
        response.status = 403
        return response.json({"erro": ui_helpers.mensagem("sem_permissao")})
    return response.json(dados)


def lista():
    _exigir_metodo("GET", "HEAD")
    if request.extension not in _EXTENSOES_LISTA:
        raise HTTP(404, **response.headers)
    ctx = _exigir_consulta()
    filtros = ticket_service.normalize_filters(request.get_vars)
    pagina = ui_helpers.sanitizar_pagina(_texto(request.get_vars.get("pagina"), 9))
    tamanho = ui_helpers.sanitizar_tamanho(_texto(request.get_vars.get("tamanho"), 3), _TAMANHOS)
    erro = None
    try:
        resultado = ticket_service.list_page(ctx, filtros, pagina, tamanho)
    except AccessDenied:
        _negado()
    except RepoError:
        _log.exception("falha ao listar tickets (login=%s)", ctx["login"], extra={"action": "TICKET_LISTAR"})
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
    dados["opcoes"] = ticket_service.filter_options(ctx)
    return dados


def detalhe():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_consulta()
    try:
        ticket = ticket_service.detail(ctx, request.args(0))
    except RepoNotFound:
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


def saida():
    """Download do zip da pasta de saida (CR-012, README §8.13): GET, regra de leitura do log, so DISPONIVEL."""
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_consulta()
    try:
        ticket_id, tamanho, partes = ticket_service.output_chunks(ctx, request.args(0))
    except RepoNotFound:
        _nao_encontrado()
    except RepoError:
        _log.exception("falha ao iniciar o download da saida (login=%s ticket=%r)", ctx["login"], request.args(0),
                       extra={"action": "SAIDA_BAIXAR"})
        raise HTTP(503, _MSG_FALHA_SAIDA, **response.headers)
    response.headers["Content-Type"] = "application/zip"
    response.headers["Content-Disposition"] = 'attachment; filename="ticket_%d_saida.zip"' % ticket_id
    response.headers["Content-Length"] = str(tamanho)
    response.headers["Cache-Control"] = "no-store"
    # Iteravel: o web2py o devolve ao WSGI como corpo em streaming, fatia a fatia.
    return partes


def cancelar():
    _exigir_metodo("POST")
    ctx = _exigir_login()
    ticket_id = _texto(request.post_vars.get("ticket_id"), 10)
    try:
        resultado = ticket_service.cancel(ctx, _ip_origem(), ticket_id)
        session.flash = {"tipo": _TIPO_FLASH_CANCELAMENTO[resultado],
                         "mensagem": ticket_service.MSG_CANCEL[resultado]}
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except RepoError:
        session.flash = {"tipo": "erro", "mensagem": _MSG_FALHA_CANCELAR}
    # CANCEL_TICKET sem VIEW_LOGS cancela sem poder ver o ticket (README §4.3.C): volta ao painel.
    if ticket_service.is_visible(ctx, ticket_id):
        redirect(URL(c="tickets", f="detalhe", args=[ticket_id]))
    redirect(URL(c="default", f="index"))


def reexecutar():
    _exigir_metodo("POST")
    ctx = _exigir_func("EXEC_SCRIPT")
    ticket_id = _texto(request.post_vars.get("ticket_id"), 10)
    try:
        novo_id = ticket_service.rerun(ctx, _ip_origem(), ticket_id)
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except RerunError as e:
        session.flash = {"tipo": "aviso", "mensagem": _MSG_REEXECUCAO_REVISAR}
        redirect(URL(c="tickets", f="novo", vars={"reexecucao": e.ticket_id}))
    session.flash = {"tipo": "sucesso",
                     "mensagem": u"Ticket #%s criado como reexecução do ticket #%s." % (novo_id, ticket_id)}
    redirect(URL(c="tickets", f="detalhe", args=[novo_id]))
