# -*- coding: utf-8 -*-
"""Vitrine do layout para desenvolvimento. Nao vai no pacote de implantacao (README §12.2; CR-032, D11)."""
import datetime
import re

from sss.config import sss_config
from sss.ui import ui_helpers

from sss.web.app.context import HTTP, URL, request, response
from sss.web.app.security import require_func as _require_func
from sss.web.app.security import require_login as _require_login


def _require_dev():
    if not sss_config.has_dev_dir():
        raise HTTP(404)


def shell():
    _require_login()
    _require_dev()
    response.title = u"Shell de desenvolvimento — SSS"

    base = datetime.datetime(2026, 10, 14, 9, 0, 0)
    samples = (
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
        "environment": env,
        "status": ui_helpers.status_info(st),
        "start": ui_helpers.format_date(ini),
        "duration": ui_helpers.format_duration(ini, end),
    } for tid, script, env, st, ini, end in samples]

    return dict(tickets=tickets, unknown_status=ui_helpers.status_info("EM_ANALISE"))


_DEMO_STATUS = (
    ("PENDING", None),
    ("RUNNING", None),
    ("SUCCESS", "EXIT_OK"),
    ("FAILED", "TIMEOUT"),
    ("CANCELLED", "CANCEL_USER"),
    ("FAILED", "EXIT_ERROR"),
    ("SUCCESS", "EXIT_OK"),
)
_DEMO_SCRIPTS = ("carga_diaria.py", "relatorio_mensal.py", "sync_tabelas.sh", "limpeza_temp.sh")
_DEMO_ENVIRONMENTS = ("PRODUCAO", "HOMOLOGACAO")
_RE_FILTER_DATE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"


def _var_text(name, limit=100):
    value = request.vars.get(name)
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _demo_tickets():
    base = datetime.datetime(2026, 10, 14, 9, 0, 0)
    tickets = []
    for i in range(57):
        status, reason = _DEMO_STATUS[i % len(_DEMO_STATUS)]
        start = base - datetime.timedelta(hours=i * 7)
        end = None if status in ("PENDING", "RUNNING") else start + datetime.timedelta(seconds=37 * (i + 1))
        tickets.append({
            "id": 1100 - i,
            "script": _DEMO_SCRIPTS[i % len(_DEMO_SCRIPTS)],
            "environment": _DEMO_ENVIRONMENTS[i % len(_DEMO_ENVIRONMENTS)],
            "status": status,
            "status_reason": reason,
            "data": start.strftime("%Y-%m-%d"),
            "start": ui_helpers.format_date(None if status == "PENDING" else start),
            "duration": ui_helpers.format_duration(None if status == "PENDING" else start, end),
        })
    return tickets


def _demo_form():
    submitted = request.vars.get("demo_submit") == "1"
    name = _var_text("ex_nome")
    timeout = _var_text("demo_timeout", 9)
    priority = _var_text("ex_prioridade", 1)
    fields = [
        {"name": "ex_nome", "label": u"Nome do agendamento", "kind": "text", "value": name,
         "help": u"Identificador exibido nas listagens.", "required": True},
        {"name": "demo_timeout", "label": u"Tempo limite (segundos)", "kind": "number", "value": timeout,
         "help": u"Entre 1 e 86400.", "required": True},
        {"name": "ex_prioridade", "label": u"Prioridade", "kind": "select", "value": priority or "2",
         "options": [("2", u"2 — Normal"), ("3", u"3 — Baixa"), ("4", u"4 — Mínima")]},
        {"name": "ex_obs", "label": u"Observação", "kind": "textarea", "value": _var_text("ex_obs", 500)},
    ]
    # Validacao apenas ilustrativa do erro por campo; nao e regra de negocio.
    if submitted:
        if not name:
            fields[0]["error"] = u"Informe o nome do agendamento."
        if not (re.fullmatch(r"[0-9]{1,5}", timeout) and 1 <= int(timeout) <= 86400):
            fields[1]["error"] = u"Informe um número inteiro entre 1 e 86400."
    return fields, submitted


def components():
    _require_login()
    _require_dev()
    # POST chega aqui ja validado (CSRF + Origin) por app/security.py.
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

    q = _var_text("q")
    status = _var_text("status", 9)
    if status not in ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED"):
        status = ""
    date_from = _var_text("date_from", 10)
    date_to = _var_text("date_to", 10)
    date_from = date_from if re.fullmatch(_RE_FILTER_DATE, date_from) else ""
    date_to = date_to if re.fullmatch(_RE_FILTER_DATE, date_to) else ""
    size = ui_helpers.sanitize_size(request.vars.get("size"))
    page = ui_helpers.sanitize_page(request.vars.get("page"))

    tickets = [t for t in _demo_tickets()
               if (not q or q.lower() in t["script"].lower())
               and (not status or t["status"] == status)
               and (not date_from or t["data"] >= date_from)
               and (not date_to or t["data"] <= date_to)]
    pg = ui_helpers.pagination_info(page, size, len(tickets))
    start = (pg["page"] - 1) * pg["size"]

    columns = [
        {"key": "id", "label": u"Ticket", "kind": "mono", "css_class": "sss-col-id"},
        {"key": "script", "label": u"Script", "kind": "mono"},
        {"key": "environment", "label": u"Ambiente"},
        {"key": "status", "label": u"Status", "kind": "status"},
        {"key": "start", "label": u"Início", "kind": "mono", "css_class": "sss-col-data"},
        {"key": "duration", "label": u"Duração", "kind": "mono", "css_class": "sss-col-num"},
    ]
    active_filters = {"q": q, "status": status, "date_from": date_from, "date_to": date_to}
    form_fields, form_submitted = _demo_form()

    return dict(
        badges=[(s, m) for s, m in _DEMO_STATUS[:5]] + [("EM_ANALISE", None)],
        table={
            "caption": u"Tickets fictícios",
            "columns": columns,
            "rows": tickets[start:start + pg["size"]],
        },
        empty_table={"caption": u"Tabela sem registros", "columns": columns[:4], "rows": []},
        error_table={"caption": u"Tabela com erro", "columns": columns[:4], "rows": [],
                     "error": u"Não foi possível carregar os tickets. Tente novamente em instantes."},
        page=pg["page"],
        size=pg["size"],
        total=pg["total"],
        url_base=(request.controller, request.function),
        query_params=active_filters,
        filters={
            "id": "filter-tickets",
            "url_base": (request.controller, request.function),
            "keep": {"size": pg["size"]},
            "fields": [
                {"name": "q", "label": u"Script", "kind": "text", "value": q},
                {"name": "status", "label": u"Status", "kind": "select", "value": status,
                 "options": [("", u"Todos")] + [(c, ui_helpers.status_info(c)["label"]) for c in
                                               ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED")]},
                {"name": "date_from", "label": u"Data início", "kind": "date", "value": date_from},
                {"name": "date_to", "label": u"Data fim", "kind": "date", "value": date_to},
            ],
        },
        sizes=(20, 50, 100),
        form_fields=form_fields,
        form_sent=form_submitted,
        focus_field=ui_helpers.first_invalid_field(form_fields),
        modals=[
            {"id": "modal-cancel", "title": u"Cancelar ticket 1024?",
             "text": u"O processo em execução será interrompido. Esta ação não pode ser desfeita.",
             "trigger_label": u"Cancelar ticket", "confirm_label": u"Sim, cancelar",
             "variant": "danger", "action": URL("dev", "components"), "hidden_fields": {"ticket_id": 1024}},
            {"id": "modal-reexecutar", "title": u"Reexecutar ticket 1023?",
             "text": u"Um novo ticket será criado com os mesmos parâmetros.",
             "trigger_label": u"Reexecutar", "confirm_label": u"Reexecutar",
             "variant": "normal", "action": URL("dev", "components"), "hidden_fields": {"ticket_id": 1023}},
        ],
        alerts=[ui_helpers.alert_info({"kind": t, "message": m}) for t, m in (
            ("success", u"Usuário salvo com sucesso."),
            ("warning", u"O agente srv-linux-prod-02 está sem heartbeat há 2 minutos."),
            ("error", u"Não foi possível salvar: o login já está em uso."),
        )],
        copy_text=u"/opt/sss/scripts/carga_diaria.py --data 2026-10-14",
    )


def admin_test():
    _require_login()
    _require_dev()
    ctx = _require_func("MANAGE_USERS")
    response.title = u"Rota administrativa de teste — SSS"
    return dict(ctx=ctx)
