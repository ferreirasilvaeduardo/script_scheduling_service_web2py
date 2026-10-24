# -*- coding: utf-8 -*-
"""Trilha de auditoria e painel de agentes (README §4.3.D VIEW_AUDIT, §4.4, §13). Somente leitura:
nenhuma action altera agentes. Regras em modules/audit_service.py e modules/agents_service.py.

CSRF e Origin de todo POST sao validados em models/10_security.py.
"""
import agents_service
import app_context
import audit_service
import ticket_service
import ui_helpers
from admin_crud import AccessDenied
from audit_service import InvalidFilters
from repo_errors import RepoError

_FUNC = "VIEW_AUDIT"
_JS_AGENTS = "js/app/agents.js"
_SIZES = (20, 50, 100)
_AGENTS_EXTENSIONS = ("html", "load")
_MSG_LIST_FAILED = u"Não foi possível carregar a trilha de auditoria. Tente novamente em instantes."
_MSG_EXPORT_FAILED = u"Não foi possível exportar a trilha de auditoria. Tente novamente em instantes."
_MSG_EXPORT_FILTERS = u"Corrija os filtros antes de exportar."
_MSG_AGENTS_FAILED = u"Não foi possível carregar os agentes. Tente novamente em instantes."
# Intervalo da atualizacao automatica do painel de agentes (F6.1).
AGENTS_INTERVAL_S = 15


def _entry(source):
    return dict((c, _text(source.get(c), 50)) for c in audit_service.FILTER_FIELDS)


def index():
    _require_method("GET", "HEAD")
    ctx = _require_func(_FUNC)
    page = ui_helpers.sanitize_page(_text(request.get_vars.get("page"), 9))
    size = ui_helpers.sanitize_size(_text(request.get_vars.get("size"), 3), _SIZES)
    entry = _entry(request.get_vars)
    error = None
    try:
        result = audit_service.list_page(ctx, entry, page, size)
    except AccessDenied:
        _denied()
    except RepoError:
        _log.exception("falha ao listar a auditoria (login=%s)", ctx["login"], extra={"action": _FUNC})
        filters, errors = audit_service.default_filters(entry)
        result = {"filters": filters, "errors": errors, "items": [], "total": 0, "page": 1,
                     "size": size}
        error = _MSG_LIST_FAILED
    if result["errors"] and not error:
        response.flash = {"kind": "error", "message": u"Corrija os filtros destacados."}
    can_view_tickets = ticket_service.can_query(ctx)
    for item in result["items"]:
        item["link"] = audit_service.entity_link(ctx, item["entity"], item["entity_id"],
                                                       can_view_tickets)
    response.title = u"Auditoria — SSS"
    return dict(result=result, error=error, size=size, active_filters=result["filters"],
                query_params=dict(result["filters"], size=size),
                actions=audit_service.ACTIONS, entities=audit_service.ENTITIES,
                export_limit=audit_service.EXPORT_LIMIT)


def export():
    # POST com CSRF: a exportacao grava auditoria, e GET nunca altera estado (AGENTS §3.4).
    _require_method("POST")
    ctx = _require_func(_FUNC)
    entry = _entry(request.post_vars)
    back = URL(c="audit", f="index", vars=dict((k, v) for k, v in entry.items() if v))
    try:
        name, rows, blocks = audit_service.export_csv(ctx, _client_ip(), entry)
    except AccessDenied:
        _denied()
    except InvalidFilters:
        session.flash = {"kind": "error", "message": _MSG_EXPORT_FILTERS}
        redirect(back)
    except RepoError:
        _log.exception("falha ao exportar a auditoria (login=%s)", ctx["login"], extra={"action": "AUDIT_EXPORT"})
        session.flash = {"kind": "error", "message": _MSG_EXPORT_FAILED}
        redirect(back)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = 'attachment; filename="%s"' % name
    response.headers["Cache-Control"] = "no-store"
    # Iteravel: o web2py o devolve ao WSGI como corpo em streaming, bloco a bloco.
    return blocks


def agents():
    _require_method("GET", "HEAD")
    if request.extension not in _AGENTS_EXTENSIONS:
        raise HTTP(404, **response.headers)
    ctx = _require_func(_FUNC)
    error = None
    try:
        panel = agents_service.dashboard(ctx)
    except AccessDenied:
        _denied()
    except RepoError:
        _log.exception("falha ao montar o painel de agentes (login=%s)", ctx["login"], extra={"action": _FUNC})
        panel = {"agents": [], "summary": {}, "now": None}
        error = _MSG_AGENTS_FAILED
    data = dict(dashboard=panel, error=error, fragment_url=URL(c="audit", f="agents", extension="load"),
                 interval_s=AGENTS_INTERVAL_S)
    if request.extension == "load":
        return data
    response.title = u"Agentes — SSS"
    response.sss_scripts = [_JS_AGENTS]
    data["legend"] = agents_service.legend()
    data["thresholds"] = app_context.require_config().agent
    return data
