# -*- coding: utf-8 -*-
"""Regras de agendamento (README §4.3.C CAD_AGENDAMENTOS, §7). Regras de negocio ficam em
modules/agendamentos_service.py; padrao de telas em docs/PADRAO_CRUD_ADMIN.md.

CSRF e Origin de todo POST sao validados em models/10_security.py.
"""
import admin_crud
import agendamentos_service as servico
import ui_helpers
from admin_crud import AcessoNegado, OperacaoNegada
from repo_errors import RepoConflito, RepoErro, RepoNaoEncontrado
from ticket_service import AcessoNegado as DisparoNegado

_FUNC = "CAD_AGENDAMENTOS"
_PREFIXO_PARAM = "p_"
_JS = "js/app/agendamentos.js"
_TAMANHOS = (20, 50, 100)
_CAMPOS_REGRA = ("nome", "tipo_recorrencia", "expressao_cron", "hora_execucao", "dia_mes", "data_inicio",
                 "data_fim", "prioridade", "versao")
_LIMITES = {"nome": 300, "expressao_cron": 100, "hora_execucao": 8, "dia_mes": 4, "data_inicio": 19,
            "data_fim": 19, "prioridade": 2, "versao": 64, "tipo_recorrencia": 10}
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
    valor = fonte.get("dias_semana")
    if isinstance(valor, list):
        return [v[:2] for v in valor[:7] if isinstance(v, str)]
    return _texto(valor, 20)


def _regra_post(fonte):
    dados = dict((c, _texto(fonte.get(c), _LIMITES[c])) for c in _CAMPOS_REGRA)
    dados["dias_semana"] = _dias_post(fonte)
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
        response.title = u"Regra %s — SSS" % regra.get("nome", "")
    else:
        response.title = u"Nova regra de agendamento — SSS"
    response.view = "agendamentos/form.html"
    response.sss_scripts = [_JS]
    erros = dados["erros"]
    foco = None
    if dados.get("form"):
        campos = [{"nome": n, "erro": erros.get(n)} for n in ("nome", "tipo_recorrencia", "data_inicio", "data_fim",
                                                               "hora_execucao", "dias_semana", "dia_mes",
                                                               "expressao_cron")]
        campos.extend({"nome": c["nome"], "erro": c["erro"]} for c in dados["form"]["campos"])
        campos.append({"nome": "prioridade", "erro": erros.get("prioridade")})
        foco = ui_helpers.primeiro_campo_invalido(campos)
    return dict(dados, erro_geral=erros.get(admin_crud.CAMPO_GERAL), foco_campo=foco,
                rotulos_tipo=servico.ROTULOS_TIPO, dias_semana=servico.DIAS_SEMANA)


def _redirecionar_lista(tipo, mensagem):
    session.flash = {"tipo": tipo, "mensagem": mensagem}
    redirect(URL(c="agendamentos", f="lista"))


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
        _log.exception("falha ao listar agendamentos (login=%s)", ctx["login"], extra={"acao": _FUNC})
        resultado = {"itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        erro = _MSG_FALHA_LISTA
    response.title = u"Regras de agendamento — SSS"
    response.sss_scripts = [_JS]
    return dict(resultado=resultado, erro=erro, filtros_ativos=filtros, tamanho=tamanho,
                query_params=dict(filtros, tamanho=tamanho))


def form():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    try:
        dados = servico.formulario(ctx, _texto(request.args(0), 11),
                                   _texto(request.get_vars.get("script_id"), 10),
                                   _texto(request.get_vars.get("ambiente"), 30))
    except RepoNaoEncontrado:
        _nao_encontrado()
    except (AcessoNegado, DisparoNegado):
        _negado()
    except OperacaoNegada as exc:
        _redirecionar_lista("erro", exc.mensagem)
    return _pagina_form(dados)


def salvar():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    agendamento_id = _texto(request.post_vars.get("id"), 11)
    script_id = _texto(request.post_vars.get("script_id"), 10)
    ambiente = _texto(request.post_vars.get("ambiente"), 30)
    enviados = _regra_post(request.post_vars)
    respostas = _respostas_post()
    try:
        salvo_id, erros = servico.salvar(ctx, _ip_origem(), dict(enviados, id=agendamento_id, script_id=script_id,
                                                                  ambiente=ambiente, respostas=respostas))
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except OperacaoNegada as exc:
        _redirecionar_lista("erro", exc.mensagem)
    except RepoErro:
        _log.exception("falha ao salvar agendamento (login=%s id=%r)", ctx["login"], agendamento_id,
                       extra={"acao": _FUNC})
        salvo_id, erros = None, {admin_crud.CAMPO_GERAL: admin_crud.MSG_FALHA}
    if not erros:
        _redirecionar_lista("sucesso", u"Regra de agendamento salva com sucesso.")
    conflito = erros.get(admin_crud.CAMPO_GERAL) == admin_crud.MSG_CONFLITO
    try:
        # No conflito, o formulario volta com os dados atuais e uma nova versao (PADRAO_CRUD_ADMIN).
        dados = servico.formulario(ctx, agendamento_id, script_id, ambiente,
                                   enviados=None if conflito else enviados,
                                   valores=None if conflito else respostas, erros=erros)
    except RepoNaoEncontrado:
        _nao_encontrado()
    except (AcessoNegado, DisparoNegado):
        _negado()
    except OperacaoNegada as exc:
        _redirecionar_lista("erro", exc.mensagem)
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"tipo": "erro", "mensagem": erros.get(admin_crud.CAMPO_GERAL)
                      or u"Corrija os campos destacados e envie novamente."}
    return _pagina_form(dados)


def _acao_estado(funcao, sucesso):
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    agendamento_id = _texto(request.post_vars.get("id"), 11)
    try:
        alterado = funcao(ctx, _ip_origem(), agendamento_id)
        session.flash = {"tipo": "sucesso", "mensagem": sucesso % alterado["nome"]}
    except RepoNaoEncontrado:
        _nao_encontrado()
    except AcessoNegado:
        _negado()
    except OperacaoNegada as exc:
        session.flash = {"tipo": "aviso", "mensagem": exc.mensagem}
    except RepoConflito:
        session.flash = {"tipo": "aviso", "mensagem": admin_crud.MSG_CONFLITO}
    except RepoErro:
        _log.exception("falha ao alterar a situacao do agendamento (login=%s id=%r)", ctx["login"],
                       agendamento_id, extra={"acao": _FUNC})
        session.flash = {"tipo": "erro", "mensagem": _MSG_FALHA_ACAO}
    redirect(URL(c="agendamentos", f="lista"))


def pausar():
    _acao_estado(servico.pausar, u"Regra %s pausada.")


def retomar():
    _acao_estado(servico.retomar, u"Regra %s retomada.")


def previa():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    dados = _regra_post(request.post_vars)
    try:
        resultado = servico.previa(ctx, dados)
    except AcessoNegado:
        response.status = 403
        return response.json({"erro": u"Acesso negado."})
    return response.json(resultado)
