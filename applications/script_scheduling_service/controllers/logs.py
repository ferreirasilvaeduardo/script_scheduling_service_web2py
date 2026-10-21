# -*- coding: utf-8 -*-
"""Visualizador de log do ticket: leitura incremental por offset e download (README §8.10).

Regras de escopo ficam em modules/ticket_service.py; aqui so se valida a requisicao e se responde.
"""
import ticket_service
from repo_errors import RepoError, RepoNotFound
from ticket_service import OffsetInvalido

_MSG_FALHA_LOG = u"Não foi possível ler o log. Tente novamente em instantes."


def _exigir_get():
    if (request.env.request_method or "GET").upper() not in ("GET", "HEAD"):
        raise HTTP(405, **response.headers)


def _exigir_consulta():
    ctx = _exigir_login()
    if not ticket_service.pode_consultar(ctx):
        _log.warning("acesso negado (login=%s funcionalidade=VIEW_LOGS|EXEC_SCRIPT caminho=%s ip=%s)",
                     ctx["login"], request.env.path_info, _ip_origem(), extra={"action": "RBAC"})
        raise HTTP(403, u"Acesso negado.", **response.headers)
    return ctx


def _ticket_id():
    valor = request.get_vars.get("ticket_id")
    valor = valor[-1] if isinstance(valor, list) and valor else valor
    return valor[:10] if isinstance(valor, str) else None


def chunk():
    _exigir_get()
    ctx = _exigir_consulta()
    response.headers["Cache-Control"] = "no-store"
    try:
        dados = ticket_service.ler_log(ctx, _ticket_id(), request.get_vars.get("offset"))
    except OffsetInvalido:
        raise HTTP(400, u"Offset inválido.", **response.headers)
    except RepoNotFound:
        raise HTTP(404, u"Ticket não encontrado.", **response.headers)
    except RepoError:
        _log.exception("falha na leitura incremental do log (login=%s ticket=%r)", ctx["login"], _ticket_id(),
                       extra={"action": "LOG_LER"})
        raise HTTP(503, _MSG_FALHA_LOG, **response.headers)
    return response.json(dados)


def baixar():
    _exigir_get()
    ctx = _exigir_consulta()
    try:
        ticket_id, blocos = ticket_service.blocos_log(ctx, _ticket_id())
    except RepoNotFound:
        raise HTTP(404, u"Ticket não encontrado.", **response.headers)
    except RepoError:
        _log.exception("falha ao iniciar o download do log (login=%s ticket=%r)", ctx["login"], _ticket_id(),
                       extra={"action": "LOG_BAIXAR"})
        raise HTTP(503, _MSG_FALHA_LOG, **response.headers)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    response.headers["Content-Disposition"] = 'attachment; filename="ticket_%d.log"' % ticket_id
    response.headers["Cache-Control"] = "no-store"
    # Iteravel: o web2py o devolve ao WSGI como corpo em streaming, bloco a bloco.
    return (bloco.encode("utf-8") for bloco in blocos)
