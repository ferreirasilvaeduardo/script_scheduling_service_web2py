# -*- coding: utf-8 -*-
"""Regras de agendamento (README §4.3.C MANAGE_SCHEDULES, §7). Regras de negocio ficam em
modules/schedules_service.py; padrao de telas em docs/ADMIN_CRUD_PATTERN.md.

CSRF e Origin de todo POST sao validados em models/10_security.py.
"""
import admin_crud
import schedules_service as servico
import ui_helpers
from admin_crud import AccessDenied, OperationDenied
from repo_errors import RepoConflict, RepoError, RepoNotFound
from ticket_service import AccessDenied as DisparoNegado

_FUNC = "MANAGE_SCHEDULES"
_PREFIXO_PARAM = "p_"
_JS = "js/app/schedules.js"
_TAMANHOS = (20, 50, 100)
_CAMPOS_REGRA = ("name", "recurrence_type", "cron_expression", "run_time", "month_day", "start_date",
                 "end_date", "priority", "version")
# Protecao de memoria acima dos limites do service, que recusa o excesso (README §7.6, AGENTS §3.4).
_LIMITES = {"name": 300, "cron_expression": 300, "run_time": 40, "month_day": 40, "start_date": 40,
            "end_date": 40, "priority": 10, "version": 100, "recurrence_type": 40}
_MSG_FALHA_LISTA = u"Não foi possível carregar as regras. Tente novamente em instantes."
_MSG_FALHA_ACAO = u"Não foi possível concluir a operação. Tente novamente em instantes."


def _exigir_metodo(*permitidos):
    if (request.env.request_method or "GET").upper() not in permitidos:
        raise HTTP(405, **response.headers)


def _negado():
    raise HTTP(403, u"Acesso negado.", **response.headers)


def _nao_encontrado():
    raise HTTP(404, u"Regra de agendamento não encontrada.", **response.headers)


def _texto(valor, limite):
    valor = valor[-1] if isinstance(valor, list) and valor else valor
    return valor[:limite] if isinstance(valor, str) else None


def _dias_post(fonte):
    valor = fonte.get("week_days")
    if isinstance(valor, list):
        return [v[:2] for v in valor[:7] if isinstance(v, str)]
    return _texto(valor, 20)


def _regra_post(fonte):
    dados = dict((c, _texto(fonte.get(c), _LIMITES[c])) for c in _CAMPOS_REGRA)
    dados["week_days"] = _dias_post(fonte)
    return dados


def _respostas_post():
    respostas = {}
    for chave, valor in request.post_vars.items():
        if isinstance(chave, str) and chave.startswith(_PREFIXO_PARAM):
            respostas[chave[len(_PREFIXO_PARAM):]] = valor
    return respostas


def _pagina_form(dados):
    regra = dados.get("regra") or {}
    if dados["edicao"]:
        response.title = u"Regra %s — SSS" % regra.get("name", "")
    else:
        response.title = u"Nova regra de agendamento — SSS"
    response.view = "schedules/form.html"
    response.sss_scripts = [_JS]
    erros = dados["erros"]
    foco = None
    if dados.get("form"):
        campos = [{"name": n, "erro": erros.get(n)} for n in ("name", "recurrence_type", "start_date", "end_date",
                                                               "run_time", "week_days", "month_day",
                                                               "cron_expression")]
        campos.extend({"name": c["name"], "erro": c["erro"]} for c in dados["form"]["campos"])
        campos.append({"name": "priority", "erro": erros.get("priority")})
        foco = ui_helpers.primeiro_campo_invalido(campos)
    return dict(dados, erro_geral=erros.get(admin_crud.GENERAL_FIELD), foco_campo=foco,
                rotulos_tipo=servico.TYPE_LABELS, dias_semana=servico.WEEKDAYS)


def _redirecionar_lista(tipo, mensagem):
    session.flash = {"tipo": tipo, "mensagem": mensagem}
    redirect(URL(c="schedules", f="index"))


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
        _log.exception("falha ao listar agendamentos (login=%s)", ctx["login"], extra={"action": _FUNC})
        resultado = {"itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        erro = _MSG_FALHA_LISTA
    response.title = u"Regras de agendamento — SSS"
    response.sss_scripts = [_JS]
    return dict(resultado=resultado, erro=erro, filtros_ativos=filtros, tamanho=tamanho,
                query_params=dict(filtros, tamanho=tamanho))


def agenda():
    """Agenda (README §7.7): o que vai rodar hoje e nos proximos 7 dias; so leitura."""
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    response.title = u"Agenda — SSS"
    try:
        return dict(dados=servico.agenda(ctx), erro=None)
    except AccessDenied:
        _negado()
    except RepoError:
        _log.exception("falha ao montar a agenda (login=%s)", ctx["login"], extra={"action": _FUNC})
        return dict(dados=None, erro=ui_helpers.mensagem("falha_interna"))


def form():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    try:
        dados = servico.form(ctx, _texto(request.args(0), 11),
                                   _texto(request.get_vars.get("script_id"), 10),
                                   _texto(request.get_vars.get("environment"), 30))
    except RepoNotFound:
        _nao_encontrado()
    except (AccessDenied, DisparoNegado):
        _negado()
    except OperationDenied as exc:
        _redirecionar_lista("erro", exc.message)
    return _pagina_form(dados)


def save():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    agendamento_id = _texto(request.post_vars.get("id"), 11)
    script_id = _texto(request.post_vars.get("script_id"), 10)
    ambiente = _texto(request.post_vars.get("environment"), 30)
    enviados = _regra_post(request.post_vars)
    respostas = _respostas_post()
    try:
        salvo_id, erros = servico.save(ctx, _ip_origem(), dict(enviados, id=agendamento_id, script_id=script_id,
                                                                  environment=ambiente, respostas=respostas))
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except OperationDenied as exc:
        _redirecionar_lista("erro", exc.message)
    except RepoError:
        _log.exception("falha ao salvar agendamento (login=%s id=%r)", ctx["login"], agendamento_id,
                       extra={"action": _FUNC})
        salvo_id, erros = None, {admin_crud.GENERAL_FIELD: admin_crud.MSG_FAILURE}
    if not erros:
        _redirecionar_lista("sucesso", u"Regra de agendamento salva com sucesso.")
    conflito = erros.get(admin_crud.GENERAL_FIELD) == admin_crud.MSG_CONFLICT
    try:
        # No conflito, o formulario volta com os dados atuais e uma nova versao (PADRAO_CRUD_ADMIN).
        dados = servico.form(ctx, agendamento_id, script_id, ambiente,
                                   submitted=None if conflito else enviados,
                                   values=None if conflito else respostas, errors=erros)
    except RepoNotFound:
        _nao_encontrado()
    except (AccessDenied, DisparoNegado):
        _negado()
    except OperationDenied as exc:
        _redirecionar_lista("erro", exc.message)
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"tipo": "erro", "mensagem": erros.get(admin_crud.GENERAL_FIELD)
                      or ui_helpers.mensagem("formulario")}
    return _pagina_form(dados)


def _acao_estado(funcao, sucesso):
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    agendamento_id = _texto(request.post_vars.get("id"), 11)
    try:
        alterado = funcao(ctx, _ip_origem(), agendamento_id)
        session.flash = {"tipo": "sucesso", "mensagem": sucesso % alterado["name"]}
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except OperationDenied as exc:
        session.flash = {"tipo": "aviso", "mensagem": exc.message}
    except RepoConflict:
        session.flash = {"tipo": "aviso", "mensagem": admin_crud.MSG_CONFLICT}
    except RepoError:
        _log.exception("falha ao alterar a situacao do agendamento (login=%s id=%r)", ctx["login"],
                       agendamento_id, extra={"action": _FUNC})
        session.flash = {"tipo": "erro", "mensagem": _MSG_FALHA_ACAO}
    redirect(URL(c="schedules", f="index"))


def pause():
    _acao_estado(servico.pause, u"Regra %s pausada.")


def resume():
    _acao_estado(servico.resume, u"Regra %s retomada.")


def preview():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    dados = _regra_post(request.post_vars)
    try:
        resultado = servico.preview(ctx, dados)
    except AccessDenied:
        response.status = 403
        return response.json({"erro": u"Acesso negado."})
    return response.json(resultado)
