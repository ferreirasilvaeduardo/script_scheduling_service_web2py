# -*- coding: utf-8 -*-
"""Tela de Saidas (CR-020a, README §5.9): navegacao pelas saidas dos tickets e download.

So GET; a regra fica em modules/output_browse_service.py. Fora do escopo, sem saida ou parametro
invalido: 404 (nunca 403, para nao revelar o que existe). Todo download e auditado (OUTPUT_DOWNLOAD).
"""
from urllib.parse import quote

import output_browse_service as browse
from output_browse_service import InvalidRequest
from repo_errors import RepoError, RepoNotFound

from webapp import security as _security
from webapp.context import HTTP, request, response
from webapp.security import client_ip as _client_ip
from webapp.security import not_found as _not_found
from webapp.security import require_func as _require_func
from webapp.security import require_method as _require_method
from webapp.security import text as _text

_log = _security.LOG

_FEATURE = "DOWNLOAD_OUTPUT"
_ACTION = "OUTPUT_DOWNLOAD"
_MSG_NOT_FOUND = u"Saída não encontrada."
_MSG_FAILED = u"Não foi possível carregar as saídas. Tente novamente em instantes."
_MSG_DOWNLOAD_FAILED = u"Não foi possível baixar a saída. Tente novamente em instantes."


def _var(name, limit):
    return _text(request.get_vars.get(name), limit)


def index():
    """Ambientes, scripts, dias ou tickets, conforme os parametros ja escolhidos."""
    _require_method("GET", "HEAD")
    ctx = _require_func(_FEATURE)
    response.title = u"Saídas — SSS"
    environment = _var("environment", 30)
    script_id = _var("script_id", 10)
    day = _var("day", 10)
    data = dict(level="environment", environment=environment, script_id=script_id, day=day, script_name=None,
                rows=[], result=None, error=None)
    try:
        if not environment:
            data["rows"] = browse.environments(ctx)
        elif not script_id:
            data.update(level="script", rows=browse.scripts(ctx, environment))
        elif not day:
            days = browse.days(ctx, environment, script_id)
            data.update(level="day", rows=days["days"], script_name=days["script_name"])
        else:
            result = browse.tickets(ctx, environment, script_id, day, _var("page", 6) or 1)
            data.update(level="ticket", result=result, rows=result["items"], script_name=result["script_name"])
    except (RepoNotFound, InvalidRequest):
        _not_found(_MSG_NOT_FOUND)
    except RepoError:
        _log.exception("falha ao carregar as saidas (login=%s)", ctx["login"], extra={"action": _ACTION})
        data["error"] = _MSG_FAILED
    return data


def files():
    """Arquivos dentro do zip de um ticket, com os botoes de download."""
    _require_method("GET", "HEAD")
    ctx = _require_func(_FEATURE)
    response.title = u"Saídas — SSS"
    try:
        result = browse.files(ctx, _var("ticket", 10), _var("page", 6) or 1)
    except (RepoNotFound, InvalidRequest):
        _not_found(_MSG_NOT_FOUND)
    except RepoError:
        _log.exception("falha ao ler o zip da saida (login=%s)", ctx["login"], extra={"action": _ACTION})
        return dict(result=None, error=_MSG_FAILED)
    return dict(result=result, error=None)


def _attachment(name):
    """Content-Disposition com nome ASCII e o nome UTF-8 (RFC 5987)."""
    ascii_name = "".join(c if 32 <= ord(c) < 127 else "_" for c in name)
    return "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (ascii_name, quote(name.encode("utf-8"), safe=""))


def _send(name, size, parts, content_type):
    response.headers["Content-Type"] = content_type
    response.headers["Content-Disposition"] = _attachment(name)
    response.headers["Content-Length"] = str(size)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Iteravel: o web2py o devolve ao WSGI como corpo em streaming, fatia a fatia.
    return parts


def download_zip():
    """Zip completo da saida do ticket (auditado)."""
    _require_method("GET", "HEAD")
    ctx = _require_func(_FEATURE)
    try:
        ticket_id, size, parts = browse.zip_download(ctx, _client_ip(), _text(request.args(0), 10))
    except (RepoNotFound, InvalidRequest):
        _not_found(_MSG_NOT_FOUND)
    except RepoError:
        _log.exception("falha ao iniciar o download do zip (login=%s)", ctx["login"], extra={"action": _ACTION})
        raise HTTP(503, _MSG_DOWNLOAD_FAILED, **response.headers)
    return _send("ticket_%d_saida.zip" % ticket_id, size, parts, "application/zip")


def download_file():
    """Um arquivo do zip, pelo nome exato do indice (auditado)."""
    _require_method("GET", "HEAD")
    ctx = _require_func(_FEATURE)
    try:
        name, size, parts = browse.file_download(ctx, _client_ip(), _text(request.args(0), 10),
                                                 _var("name", browse.NAME_MAX + 1))
    except (RepoNotFound, InvalidRequest):
        _not_found(_MSG_NOT_FOUND)
    except RepoError:
        _log.exception("falha ao iniciar o download do arquivo (login=%s)", ctx["login"], extra={"action": _ACTION})
        raise HTTP(503, _MSG_DOWNLOAD_FAILED, **response.headers)
    return _send(name, size, parts, "application/octet-stream")
