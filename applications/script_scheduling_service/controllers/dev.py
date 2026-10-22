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
        "start": ui_helpers.formatar_data(ini),
        "duration": ui_helpers.formatar_duracao(ini, fim),
    } for tid, script, amb, st, ini, fim in amostras]

    return dict(tickets=tickets, unknown_status=ui_helpers.status_info("EM_ANALISE"))


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
            "start": ui_helpers.formatar_data(None if status == "PENDING" else inicio),
            "duration": ui_helpers.formatar_duracao(None if status == "PENDING" else inicio, fim),
        })
    return tickets


def _formulario_demo():
    enviado = request.vars.get("demo_submit") == "1"
    nome = _texto_var("ex_nome")
    timeout = _texto_var("demo_timeout", 9)
    prioridade = _texto_var("ex_prioridade", 1)
    campos = [
        {"name": "ex_nome", "label": u"Nome do agendamento", "kind": "text", "value": nome,
         "help": u"Identificador exibido nas listagens.", "required": True},
        {"name": "demo_timeout", "label": u"Tempo limite (segundos)", "kind": "number", "value": timeout,
         "help": u"Entre 1 e 86400.", "required": True},
        {"name": "ex_prioridade", "label": u"Prioridade", "kind": "select", "value": prioridade or "2",
         "options": [("2", u"2 — Normal"), ("3", u"3 — Baixa"), ("4", u"4 — Mínima")]},
        {"name": "ex_obs", "label": u"Observação", "kind": "textarea", "value": _texto_var("ex_obs", 500)},
    ]
    # Validacao apenas ilustrativa do erro por campo; nao e regra de negocio.
    if enviado:
        if not nome:
            campos[0]["error"] = u"Informe o nome do agendamento."
        if not (re.fullmatch(r"[0-9]{1,5}", timeout) and 1 <= int(timeout) <= 86400):
            campos[1]["error"] = u"Informe um número inteiro entre 1 e 86400."
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
        response.flash = {"kind": "success", "message": u"Confirmação recebida (demonstração; nenhuma ação executada)."}
    if flash_demo in ("success", "warning", "error"):
        response.flash = {
            "kind": flash_demo,
            "message": {
                "success": u"Operação concluída com sucesso.",
                "warning": u"Agendamento pausado após falhas consecutivas.",
                "error": u"Não foi possível concluir a operação.",
            }[flash_demo],
        }

    q = _texto_var("q")
    status = _texto_var("status", 9)
    if status not in ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED"):
        status = ""
    de = _texto_var("date_from", 10)
    ate = _texto_var("date_to", 10)
    de = de if re.fullmatch(_RE_DATA_FILTRO, de) else ""
    ate = ate if re.fullmatch(_RE_DATA_FILTRO, ate) else ""
    tamanho = ui_helpers.sanitizar_tamanho(request.vars.get("size"))
    pagina = ui_helpers.sanitizar_pagina(request.vars.get("page"))

    tickets = [t for t in _tickets_demo()
               if (not q or q.lower() in t["script"].lower())
               and (not status or t["status"] == status)
               and (not de or t["data"] >= de)
               and (not ate or t["data"] <= ate)]
    pag = ui_helpers.paginacao_info(pagina, tamanho, len(tickets))
    inicio = (pag["page"] - 1) * pag["size"]

    colunas = [
        {"key": "id", "label": u"Ticket", "kind": "mono", "css_class": "sss-col-id"},
        {"key": "script", "label": u"Script", "kind": "mono"},
        {"key": "environment", "label": u"Ambiente"},
        {"key": "status", "label": u"Status", "kind": "status"},
        {"key": "start", "label": u"Início", "kind": "mono", "css_class": "sss-col-data"},
        {"key": "duration", "label": u"Duração", "kind": "mono", "css_class": "sss-col-num"},
    ]
    filtros_ativos = {"q": q, "status": status, "date_from": de, "date_to": ate}
    campos_form, form_enviado = _formulario_demo()

    return dict(
        badges=[(s, m) for s, m in _STATUS_DEMO[:5]] + [("EM_ANALISE", None)],
        table={
            "caption": u"Tickets fictícios",
            "columns": colunas,
            "rows": tickets[inicio:inicio + pag["size"]],
        },
        empty_table={"caption": u"Tabela sem registros", "columns": colunas[:4], "rows": []},
        error_table={"caption": u"Tabela com erro", "columns": colunas[:4], "rows": [],
                     "error": u"Não foi possível carregar os tickets. Tente novamente em instantes."},
        page=pag["page"],
        size=pag["size"],
        total=pag["total"],
        url_base=(request.controller, request.function),
        query_params=filtros_ativos,
        filters={
            "id": "filtro-tickets",
            "url_base": (request.controller, request.function),
            "keep": {"size": pag["size"]},
            "fields": [
                {"name": "q", "label": u"Script", "kind": "text", "value": q},
                {"name": "status", "label": u"Status", "kind": "select", "value": status,
                 "options": [("", u"Todos")] + [(c, ui_helpers.status_info(c)["label"]) for c in
                                               ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED")]},
                {"name": "date_from", "label": u"Data início", "kind": "date", "value": de},
                {"name": "date_to", "label": u"Data fim", "kind": "date", "value": ate},
            ],
        },
        sizes=(20, 50, 100),
        form_fields=campos_form,
        form_sent=form_enviado,
        focus_field=ui_helpers.primeiro_campo_invalido(campos_form),
        modals=[
            {"id": "modal-cancelar", "title": u"Cancelar ticket 1024?",
             "text": u"O processo em execução será interrompido. Esta ação não pode ser desfeita.",
             "trigger_label": u"Cancelar ticket", "confirm_label": u"Sim, cancelar",
             "variant": "danger", "action": URL("dev", "components"), "hidden_fields": {"ticket_id": 1024}},
            {"id": "modal-reexecutar", "title": u"Reexecutar ticket 1023?",
             "text": u"Um novo ticket será criado com os mesmos parâmetros.",
             "trigger_label": u"Reexecutar", "confirm_label": u"Reexecutar",
             "variant": "normal", "action": URL("dev", "components"), "hidden_fields": {"ticket_id": 1023}},
        ],
        alerts=[ui_helpers.alerta_info({"kind": t, "message": m}) for t, m in (
            ("success", u"Usuário salvo com sucesso."),
            ("warning", u"O agente srv-linux-prod-02 está sem heartbeat há 2 minutos."),
            ("error", u"Não foi possível salvar: o login já está em uso."),
        )],
        copy_text=u"/opt/sss/scripts/carga_diaria.py --data 2026-10-14",
    )


def admin_test():
    _exigir_login()
    _exigir_dev()
    ctx = _exigir_func("MANAGE_USERS")
    response.title = u"Rota administrativa de teste — SSS"
    return dict(ctx=ctx)
