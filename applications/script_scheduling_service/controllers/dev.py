# -*- coding: utf-8 -*-
"""Vitrine do layout para desenvolvimento. Nao implantado em HML/PROD (README §12.2)."""
import datetime
import re

from gluon import current

import ui_helpers


def _exigir_dev():
    if current.sss_cfg.app.sss_env != "DEV":
        raise HTTP(404)


def shell():
    _exigir_login()
    _exigir_dev()
    response.title = u"Shell de desenvolvimento — SSS"

    base = datetime.datetime(2026, 10, 14, 9, 0, 0)
    amostras = (
        (1025, "carga_diaria.py", "PRODUCAO", "PENDING", None, None),
        (1024, "carga_diaria.py", "PRODUCAO", "RUNNING", base, None),
        (1023, "relatorio_mensal.py", "HOMOLOGACAO", "SUCCESS",
         base - datetime.timedelta(minutes=30), base - datetime.timedelta(minutes=27, seconds=15)),
        (1022, "sync_tabelas.sh", "PRODUCAO", "FAILED",
         base - datetime.timedelta(hours=3), base - datetime.timedelta(hours=1, minutes=44, seconds=18)),
        (1021, "limpeza_temp.sh", "HOMOLOGACAO", "CANCELLED",
         base - datetime.timedelta(hours=4), base - datetime.timedelta(hours=4) + datetime.timedelta(seconds=42)),
    )
    tickets = [{
        "id": tid,
        "script": script,
        "environment": amb,
        "status": ui_helpers.status_info(st),
        "inicio": ui_helpers.formatar_data(ini),
        "duracao": ui_helpers.formatar_duracao(ini, fim),
    } for tid, script, amb, st, ini, fim in amostras]

    return dict(tickets=tickets, status_desconhecido=ui_helpers.status_info("EM_ANALISE"))


_STATUS_DEMO = (
    ("PENDING", None),
    ("RUNNING", None),
    ("SUCCESS", "EXIT_OK"),
    ("FAILED", "TIMEOUT"),
    ("CANCELLED", "CANCEL_USER"),
    ("FAILED", "EXIT_ERROR"),
    ("SUCCESS", "EXIT_OK"),
)
_SCRIPTS_DEMO = ("carga_diaria.py", "relatorio_mensal.py", "sync_tabelas.sh", "limpeza_temp.sh")
_AMBIENTES_DEMO = ("PRODUCAO", "HOMOLOGACAO")
_RE_DATA_FILTRO = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"


def _texto_var(nome, limite=100):
    valor = request.vars.get(nome)
    if not isinstance(valor, str):
        return ""
    return valor.strip()[:limite]


def _tickets_demo():
    base = datetime.datetime(2026, 10, 14, 9, 0, 0)
    tickets = []
    for i in range(57):
        status, motivo = _STATUS_DEMO[i % len(_STATUS_DEMO)]
        inicio = base - datetime.timedelta(hours=i * 7)
        fim = None if status in ("PENDING", "RUNNING") else inicio + datetime.timedelta(seconds=37 * (i + 1))
        tickets.append({
            "id": 1100 - i,
            "script": _SCRIPTS_DEMO[i % len(_SCRIPTS_DEMO)],
            "environment": _AMBIENTES_DEMO[i % len(_AMBIENTES_DEMO)],
            "status": status,
            "status_reason": motivo,
            "data": inicio.strftime("%Y-%m-%d"),
            "inicio": ui_helpers.formatar_data(None if status == "PENDING" else inicio),
            "duracao": ui_helpers.formatar_duracao(None if status == "PENDING" else inicio, fim),
        })
    return tickets


def _formulario_demo():
    enviado = request.vars.get("ex_enviar") == "1"
    nome = _texto_var("ex_nome")
    timeout = _texto_var("ex_timeout", 9)
    prioridade = _texto_var("ex_prioridade", 1)
    campos = [
        {"name": "ex_nome", "rotulo": u"Nome do agendamento", "tipo": "text", "valor": nome,
         "ajuda": u"Identificador exibido nas listagens.", "required": True},
        {"name": "ex_timeout", "rotulo": u"Tempo limite (segundos)", "tipo": "number", "valor": timeout,
         "ajuda": u"Entre 1 e 86400.", "required": True},
        {"name": "ex_prioridade", "rotulo": u"Prioridade", "tipo": "select", "valor": prioridade or "2",
         "opcoes": [("2", u"2 — Normal"), ("3", u"3 — Baixa"), ("4", u"4 — Mínima")]},
        {"name": "ex_obs", "rotulo": u"Observação", "tipo": "textarea", "valor": _texto_var("ex_obs", 500)},
    ]
    # Validacao apenas ilustrativa do erro por campo; nao e regra de negocio.
    if enviado:
        if not nome:
            campos[0]["erro"] = u"Informe o nome do agendamento."
        if not (re.fullmatch(r"[0-9]{1,5}", timeout) and 1 <= int(timeout) <= 86400):
            campos[1]["erro"] = u"Informe um número inteiro entre 1 e 86400."
    return campos, enviado


def components():
    _exigir_login()
    _exigir_dev()
    # POST chega aqui ja validado (CSRF + Origin) por models/10_security.py.
    if request.env.request_method not in ("GET", "HEAD", "POST"):
        raise HTTP(405)
    response.title = u"Componentes — SSS"

    flash_demo = request.vars.get("flash")
    if request.env.request_method == "POST" and request.post_vars.get("ticket_id"):
        response.flash = {"tipo": "sucesso", "mensagem": u"Confirmação recebida (demonstração; nenhuma ação executada)."}
    if flash_demo in ("sucesso", "aviso", "erro"):
        response.flash = {
            "tipo": flash_demo,
            "mensagem": {
                "sucesso": u"Operação concluída com sucesso.",
                "aviso": u"Agendamento pausado após falhas consecutivas.",
                "erro": u"Não foi possível concluir a operação.",
            }[flash_demo],
        }

    q = _texto_var("q")
    status = _texto_var("status", 9)
    if status not in ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED"):
        status = ""
    de = _texto_var("de", 10)
    ate = _texto_var("ate", 10)
    de = de if re.fullmatch(_RE_DATA_FILTRO, de) else ""
    ate = ate if re.fullmatch(_RE_DATA_FILTRO, ate) else ""
    tamanho = ui_helpers.sanitizar_tamanho(request.vars.get("tamanho"))
    pagina = ui_helpers.sanitizar_pagina(request.vars.get("pagina"))

    tickets = [t for t in _tickets_demo()
               if (not q or q.lower() in t["script"].lower())
               and (not status or t["status"] == status)
               and (not de or t["data"] >= de)
               and (not ate or t["data"] <= ate)]
    pag = ui_helpers.paginacao_info(pagina, tamanho, len(tickets))
    inicio = (pag["pagina"] - 1) * pag["tamanho"]

    colunas = [
        {"chave": "id", "rotulo": u"Ticket", "tipo": "mono", "classe": "sss-col-id"},
        {"chave": "script", "rotulo": u"Script", "tipo": "mono"},
        {"chave": "environment", "rotulo": u"Ambiente"},
        {"chave": "status", "rotulo": u"Status", "tipo": "status"},
        {"chave": "inicio", "rotulo": u"Início", "tipo": "mono", "classe": "sss-col-data"},
        {"chave": "duracao", "rotulo": u"Duração", "tipo": "mono", "classe": "sss-col-num"},
    ]
    filtros_ativos = {"q": q, "status": status, "de": de, "ate": ate}
    campos_form, form_enviado = _formulario_demo()

    return dict(
        badges=[(s, m) for s, m in _STATUS_DEMO[:5]] + [("EM_ANALISE", None)],
        tabela={
            "legenda": u"Tickets fictícios",
            "colunas": colunas,
            "linhas": tickets[inicio:inicio + pag["tamanho"]],
        },
        tabela_vazia={"legenda": u"Tabela sem registros", "colunas": colunas[:4], "linhas": []},
        tabela_erro={"legenda": u"Tabela com erro", "colunas": colunas[:4], "linhas": [],
                     "erro": u"Não foi possível carregar os tickets. Tente novamente em instantes."},
        pagina=pag["pagina"],
        tamanho=pag["tamanho"],
        total=pag["total"],
        url_base=(request.controller, request.function),
        query_params=filtros_ativos,
        filtros={
            "id": "filtro-tickets",
            "url_base": (request.controller, request.function),
            "preservar": {"tamanho": pag["tamanho"]},
            "campos": [
                {"name": "q", "rotulo": u"Script", "tipo": "texto", "valor": q},
                {"name": "status", "rotulo": u"Status", "tipo": "select", "valor": status,
                 "opcoes": [("", u"Todos")] + [(c, ui_helpers.status_info(c)["rotulo"]) for c in
                                               ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED")]},
                {"name": "de", "rotulo": u"Data início", "tipo": "data", "valor": de},
                {"name": "ate", "rotulo": u"Data fim", "tipo": "data", "valor": ate},
            ],
        },
        tamanhos=(20, 50, 100),
        campos_form=campos_form,
        form_enviado=form_enviado,
        foco_campo=ui_helpers.primeiro_campo_invalido(campos_form),
        modais=[
            {"id": "modal-cancelar", "titulo": u"Cancelar ticket 1024?",
             "texto": u"O processo em execução será interrompido. Esta ação não pode ser desfeita.",
             "rotulo_gatilho": u"Cancelar ticket", "rotulo_confirmar": u"Sim, cancelar",
             "variante": "perigo", "acao": URL("dev", "components"), "campos_ocultos": {"ticket_id": 1024}},
            {"id": "modal-reexecutar", "titulo": u"Reexecutar ticket 1023?",
             "texto": u"Um novo ticket será criado com os mesmos parâmetros.",
             "rotulo_gatilho": u"Reexecutar", "rotulo_confirmar": u"Reexecutar",
             "variante": "normal", "acao": URL("dev", "components"), "campos_ocultos": {"ticket_id": 1023}},
        ],
        alertas=[ui_helpers.alerta_info({"tipo": t, "mensagem": m}) for t, m in (
            ("sucesso", u"Usuário salvo com sucesso."),
            ("aviso", u"O agente srv-linux-prod-02 está sem heartbeat há 2 minutos."),
            ("erro", u"Não foi possível salvar: o login já está em uso."),
        )],
        texto_copia=u"/opt/sss/scripts/carga_diaria.py --data 2026-10-14",
    )


def admin_test():
    _exigir_login()
    _exigir_dev()
    ctx = _exigir_func("MANAGE_USERS")
    response.title = u"Rota administrativa de teste — SSS"
    return dict(ctx=ctx)
