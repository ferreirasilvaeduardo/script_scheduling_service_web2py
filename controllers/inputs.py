# -*- coding: utf-8 -*-
"""Tela de Entrada (CR-020d, README §5.10): navegar pela pasta de entrada dos scripts e enviar arquivos.

A regra fica em modules/input_browse_service.py. CSRF, Origin e o tamanho maximo do POST sao validados em
webapp/security.py (o POST acima do limite e recusado com 413 antes de o corpo ser lido). Fora do escopo ou
com parametro invalido: 404. Envio e pedido de retrato sao POST com redirecionamento para a pasta.
"""
from sss.services import input_browse_service as browse
from sss.services.input_browse_service import InvalidRequest
from sss.persistence.repo_errors import RepoError, RepoNotFound

from webapp import security as _security
from webapp.context import URL, redirect, request, response, session
from webapp.security import client_ip as _client_ip
from webapp.security import not_found as _not_found
from webapp.security import require_func as _require_func
from webapp.security import require_method as _require_method
from webapp.security import text as _text

_log = _security.LOG

_FEATURE = "UPLOAD_INPUT"
_ACTION = "ENTRADA"
_JS = "js/app/inputs.js"
_MSG_NOT_FOUND = u"Pasta não encontrada."
_MSG_FAILED = u"Não foi possível carregar a pasta. Tente novamente em instantes."
_MSG_UPLOAD_FAILED = u"Não foi possível enviar o arquivo. Tente novamente em instantes."


def _var(source, name, limit):
    return _text(source.get(name), limit)


def _back(environment, script_id, folder):
    vars_ = dict((k, v) for k, v in (("environment", environment), ("script_id", script_id), ("dir", folder)) if v)
    redirect(URL(c="inputs", f="index", vars=vars_))


def index():
    """Ambientes, scripts do ambiente ou a pasta do script (retratos, envio e ultimos envios)."""
    _require_method("GET", "HEAD")
    ctx = _require_func(_FEATURE)
    response.title = u"Entrada — SSS"
    response.sss_scripts = [_JS]
    environment = _var(request.get_vars, "environment", 30)
    script_id = _var(request.get_vars, "script_id", 10)
    data = dict(level="environment", environment=environment, rows=[], view=None, error=None)
    try:
        if not environment:
            data["rows"] = browse.environments(ctx)
        elif not script_id:
            data.update(level="script", rows=browse.scripts(ctx, environment))
        else:
            data.update(level="folder", view=browse.folder(ctx, environment, script_id,
                                                           _var(request.get_vars, "dir", 4200) or "",
                                                           _var(request.get_vars, "page", 6) or 1))
    except (RepoNotFound, InvalidRequest, ValueError):
        _not_found(_MSG_NOT_FOUND)
    except RepoError:
        _log.exception("falha ao carregar a pasta de entrada (login=%s)", ctx["login"], extra={"action": _ACTION})
        data["error"] = _MSG_FAILED
    return data


def upload():
    """Envio de um arquivo para a pasta (POST multipart)."""
    _require_method("POST")
    ctx = _require_func(_FEATURE)
    environment = _var(request.post_vars, "environment", 30)
    script_id = _var(request.post_vars, "script_id", 10)
    folder = _var(request.post_vars, "relative_dir", 4200)
    current = _var(request.post_vars, "dir", 4200)
    field = request.post_vars.get("file")
    stream = getattr(field, "file", None)
    filename = getattr(field, "filename", None) if stream is not None else None
    try:
        result, errors = browse.upload(ctx, _client_ip(), environment, script_id, folder, filename, stream,
                                       request.post_vars.get("replace") == "Y")
    except (RepoNotFound, InvalidRequest):
        _not_found(_MSG_NOT_FOUND)
    except RepoError:
        _log.exception("falha ao gravar o envio (login=%s)", ctx["login"], extra={"action": _ACTION})
        session.flash = {"kind": "error", "message": _MSG_UPLOAD_FAILED}
        _back(environment, script_id, current)
    if errors:
        session.flash = {"kind": "error", "message": u" ".join(errors[k] for k in sorted(errors))}
    else:
        session.flash = {"kind": "success", "message": u"Arquivo enviado para %d servidor(es): %s. A entrega aparece "
                                                       u"em Últimos envios." % (len(result["agents"]),
                                                                                 ", ".join(result["agents"]))}
    _back(environment, script_id, current)


def refresh():
    """Pede um retrato novo da pasta a cada servidor no ar do ambiente (POST)."""
    _require_method("POST")
    ctx = _require_func(_FEATURE)
    environment = _var(request.post_vars, "environment", 30)
    script_id = _var(request.post_vars, "script_id", 10)
    current = _var(request.post_vars, "dir", 4200)
    try:
        count = browse.refresh(ctx, environment, script_id)
    except (RepoNotFound, InvalidRequest):
        _not_found(_MSG_NOT_FOUND)
    except RepoError:
        _log.exception("falha ao pedir o retrato (login=%s)", ctx["login"], extra={"action": _ACTION})
        session.flash = {"kind": "error", "message": _MSG_FAILED}
        _back(environment, script_id, current)
    if count:
        session.flash = {"kind": "success", "message": u"Pedimos um retrato novo a %d servidor(es). Atualize a página "
                                                       u"em alguns segundos." % count}
    else:
        session.flash = {"kind": "warning", "message": browse.MSG_NO_AGENT}
    _back(environment, script_id, current)
