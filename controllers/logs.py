# -*- coding: utf-8 -*-
"""Visualizador de log do ticket: leitura incremental por offset e download (README §8.10).

Regras de escopo ficam em modules/ticket_service.py; aqui so se valida a requisicao e se responde.
"""
import ticket_service
from repo_errors import RepoError, RepoNotFound
from ticket_service import InvalidOffset

from webapp import security as _security
from webapp.context import HTTP, request, response
from webapp.security import not_found as _not_found
from webapp.security import require_method as _require_method
from webapp.security import require_query as _require_query
from webapp.security import text as _text

_log = _security.LOG

_MSG_LOG_FAILED = u"Não foi possível ler o log. Tente novamente em instantes."
_MSG_NOT_FOUND = u"Ticket não encontrado."


def _ticket_id():
    return _text(request.get_vars.get("ticket_id"), 10)


def chunk():
    _require_method("GET", "HEAD")
    ctx = _require_query()
    response.headers["Cache-Control"] = "no-store"
    try:
        data = ticket_service.read_log(ctx, _ticket_id(), request.get_vars.get("offset"))
    except InvalidOffset:
        raise HTTP(400, u"Offset inválido.", **response.headers)
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except RepoError:
        _log.exception("falha na leitura incremental do log (login=%s ticket=%r)", ctx["login"], _ticket_id(),
                       extra={"action": "LOG_LER"})
        raise HTTP(503, _MSG_LOG_FAILED, **response.headers)
    return response.json(data)


def download():
    _require_method("GET", "HEAD")
    ctx = _require_query()
    try:
        ticket_id, blocks = ticket_service.log_chunks(ctx, _ticket_id())
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except RepoError:
        _log.exception("falha ao iniciar o download do log (login=%s ticket=%r)", ctx["login"], _ticket_id(),
                       extra={"action": "LOG_BAIXAR"})
        raise HTTP(503, _MSG_LOG_FAILED, **response.headers)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    response.headers["Content-Disposition"] = 'attachment; filename="ticket_%d.log"' % ticket_id
    response.headers["Cache-Control"] = "no-store"
    # Iteravel: o nucleo web (web/app.py) o devolve ao WSGI como corpo em streaming, bloco a bloco.
    return (block.encode("utf-8") for block in blocks)
