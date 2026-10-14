# -*- coding: utf-8 -*-
"""Disparo de script e tickets (README §5.4). Regras de negocio ficam em modules/ticket_service.py.

CSRF e Origin de todo POST sao validados em models/10_security.py.
"""
import ticket_service
import ui_helpers
from repo_errors import RepoNaoEncontrado
from ticket_service import AcessoNegado

_PREFIXO_PARAM = "p_"
_JS_DISPARO = "js/app/disparo.js"


def _metodo():
    return (request.env.request_method or "GET").upper()


def _exigir_metodo(*permitidos):
    if _metodo() not in permitidos:
        raise HTTP(405, **response.headers)


def _negado():
    raise HTTP(403, u"Acesso negado.", **response.headers)


def _texto(valor, limite):
    valor = valor[-1] if isinstance(valor, list) and valor else valor
    return valor[:limite] if isinstance(valor, str) else None


def _respostas_post():
    respostas = {}
    for chave, valor in request.post_vars.items():
        if isinstance(chave, str) and chave.startswith(_PREFIXO_PARAM):
            respostas[chave[len(_PREFIXO_PARAM):]] = valor
    return respostas


def _pagina_novo(ctx, script_id, ambiente, valores=None, erros=None, prioridade=None, scheduled_at=None):
    response.title = u"Disparar script — SSS"
    response.sss_scripts = [_JS_DISPARO]
    erros = erros or {}
    dados = dict(etapa=1, grupos=[], script=None, ambientes=[], form=None, erros=erros,
                 erro_geral=erros.get(ticket_service.CAMPO_GERAL), prioridade=prioridade,
                 scheduled_at=scheduled_at or "", foco_campo=None)
    if not script_id:
        dados["grupos"] = ticket_service.scripts_disponiveis(ctx)
        return dados
    script, ambientes = ticket_service.ambientes_disponiveis(ctx, script_id)
    dados.update(etapa=2, script=script, ambientes=ambientes)
    if not ambiente:
        return dados
    form = ticket_service.preparar_formulario(ctx, script_id, ambiente, valores, erros)
    campos = [{"nome": c["nome"], "erro": c["erro"]} for c in form["campos"]]
    campos.append({"nome": "prioridade", "erro": erros.get(ticket_service.CAMPO_PRIORIDADE)})
    campos.append({"nome": "scheduled_at", "erro": erros.get(ticket_service.CAMPO_AGENDAMENTO)})
    dados.update(etapa=3, form=form, foco_campo=ui_helpers.primeiro_campo_invalido(campos))
    return dados


def novo():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func("EXEC_SCRIPT")
    try:
        return _pagina_novo(ctx, _texto(request.get_vars.get("script_id"), 10),
                            _texto(request.get_vars.get("ambiente"), 30))
    except AcessoNegado:
        _negado()


def criar():
    _exigir_metodo("POST")
    ctx = _exigir_func("EXEC_SCRIPT")
    script_id = _texto(request.post_vars.get("script_id"), 10)
    ambiente = _texto(request.post_vars.get("ambiente"), 30)
    prioridade = _texto(request.post_vars.get("prioridade"), 2)
    scheduled_at = _texto(request.post_vars.get("scheduled_at"), 19)
    respostas = _respostas_post()
    try:
        ticket_id, erros = ticket_service.criar_ticket(ctx, _ip_origem(), script_id, ambiente, respostas,
                                                       prioridade, scheduled_at)
        if ticket_id is not None:
            session.flash = {"tipo": "sucesso", "mensagem": u"Ticket #%s criado com sucesso." % ticket_id}
            redirect(URL(c="tickets", f="detalhe", args=[ticket_id]))
        # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
        response.flash = {"tipo": "erro", "mensagem": u"Corrija os campos destacados e envie novamente."}
        response.view = "tickets/novo.html"
        return _pagina_novo(ctx, script_id, ambiente, respostas, erros, prioridade, scheduled_at)
    except AcessoNegado:
        _negado()


def previa():
    # POST porque o corpo pode conter valores sensiveis: nunca na URL nem no log de acesso.
    _exigir_metodo("POST")
    ctx = _exigir_func("EXEC_SCRIPT")
    respostas = request.post_vars.get("respostas")
    try:
        argv, erros = ticket_service.previa(ctx, _texto(request.post_vars.get("script_id"), 10),
                                            _texto(request.post_vars.get("ambiente"), 30),
                                            respostas if isinstance(respostas, dict) else {})
    except AcessoNegado:
        response.status = 403
        return response.json({"erro": u"Acesso negado."})
    return response.json({"argv": argv, "erros": erros})


def detalhe():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_login()
    try:
        ticket = ticket_service.ticket_resumo(ctx, request.args(0))
    except RepoNaoEncontrado:
        raise HTTP(404, u"Ticket não encontrado.", **response.headers)
    except AcessoNegado:
        _negado()
    response.title = u"Ticket #%s — SSS" % ticket["id"]
    return dict(ticket=ticket)
