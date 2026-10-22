# -*- coding: utf-8 -*-
"""Visualizador de log do ticket: leitura incremental por offset e download (README §8.10).

Regras de escopo ficam em modules/ticket_service.py; aqui so se valida a requisicao e se responde.
"""
import ticket_service
from repo_errors import RepoError, RepoNotFound
from ticket_service import InvalidOffset

_MSG_LOG_FAILED = u"Não foi possível ler o log. Tente novamente em instantes."


def _require_get():
    if (request.env.request_method or "GET").upper() not in ("GET", "HEAD"):
        raise HTTP(405, **response.headers)


def _require_query():
    ctx = _require_login()
    if not ticket_service.can_query(ctx):
        _log.warning("acesso negado (login=%s funcionalidade=VIEW_LOGS|EXEC_SCRIPT caminho=%s ip=%s)",
                     ctx["login"], request.env.path_info, _client_ip(), extra={"action": "RBAC"})
        raise HTTP(403, u"Acesso negado.", **response.headers)
    return ctx


def _ticket_id():
    value = request.get_vars.get("ticket_id")
    value = value[-1] if isinstance(value, list) and value else value
    return value[:10] if isinstance(value, str) else None


def chunk():
    _require_get()
    ctx = _require_query()
    response.headers["Cache-Control"] = "no-store"
    try:
        data = ticket_service.read_log(ctx, _ticket_id(), request.get_vars.get("offset"))
    except InvalidOffset:
        raise HTTP(400, u"Offset inválido.", **response.headers)
    except RepoNotFound:
        raise HTTP(404, u"Ticket não encontrado.", **response.headers)
    except RepoError:
        _log.exception("falha na leitura incremental do log (login=%s ticket=%r)", ctx["login"], _ticket_id(),
                       extra={"action": "LOG_LER"})
        raise HTTP(503, _MSG_LOG_FAILED, **response.headers)
    return response.json(data)


def download():
    _require_get()
    ctx = _require_query()
    try:
        ticket_id, blocks = ticket_service.log_chunks(ctx, _ticket_id())
    except RepoNotFound:
        raise HTTP(404, u"Ticket não encontrado.", **response.headers)
    except RepoError:
        _log.exception("falha ao iniciar o download do log (login=%s ticket=%r)", ctx["login"], _ticket_id(),
                       extra={"action": "LOG_BAIXAR"})
        raise HTTP(503, _MSG_LOG_FAILED, **response.headers)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    response.headers["Content-Disposition"] = 'attachment; filename="ticket_%d.log"' % ticket_id
    response.headers["Cache-Control"] = "no-store"
    # Iteravel: o web2py o devolve ao WSGI como corpo em streaming, bloco a bloco.
    return (block.encode("utf-8") for block in blocks)
