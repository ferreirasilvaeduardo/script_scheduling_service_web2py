# -*- coding: utf-8 -*-
"""Tela Pasta de Arquivos (CR-037, README §5.11): inputs e outputs por ambiente e script.

O conteudo fica so em disco; a regra esta em services/files_service.py. CSRF, Origin e o tamanho
maximo do POST sao validados em app/security.py (o envio acima de files_upload_max_bytes e recusado
com 413 antes de o corpo ser lido). Fora do escopo ou com parametro invalido: 404. O envio e POST
com redirecionamento para a pasta; os downloads sao GET, auditados (FILES_DOWNLOAD).
"""
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

from sss.core import rbac
from sss.services import files_service as files
from sss.services.files_service import InvalidRequest, NoAgent
from sss.persistence.repo_errors import RepoError, RepoNotFound

from sss.web.app import security as _security
from sss.web.app.context import HTTP, URL, redirect, request, response, session
from sss.web.app.security import client_ip as _client_ip
from sss.web.app.security import not_found as _not_found
from sss.web.app.security import require_func as _require_func
from sss.web.app.security import require_method as _require_method
from sss.web.app.security import text as _text

_log = _security.LOG

_FEATURES = ("FILES_UPLOAD", "FILES_DOWNLOAD")
_ACTION = "ARQUIVOS"
_JS = "js/app/inputs.js"
_MSG_NOT_FOUND = u"Pasta não encontrada."
_MSG_FAILED = u"Não foi possível carregar a pasta. Tente novamente em instantes."
_MSG_UPLOAD_FAILED = u"Não foi possível enviar o arquivo. Tente novamente em instantes."
_MSG_DOWNLOAD_FAILED = u"Não foi possível baixar o arquivo. Tente novamente em instantes."

Location = Tuple[str, str, Optional[str]]


def _var(source: Any, name: str, limit: int) -> str:
    return str(_text(source.get(name), limit) or "")


def _ctx() -> Dict[str, Any]:
    """A tela abre com FILES_UPLOAD ou FILES_DOWNLOAD (sem as duas, 403 com um WARN so); a area
    de cada uma o service reconfirma."""
    revalidated = _security.require_login()
    if not any(rbac.has_feature(revalidated, code) for code in _FEATURES):
        _log.warning("acesso negado (login=%s funcionalidade=%s caminho=%s ip=%s)",
                     revalidated["login"], "|".join(_FEATURES), _security.path_info(),
                     _client_ip(), extra={"action": "RBAC"})
        _security.denied()
    return revalidated


def _location(source: Any) -> Location:
    return (_var(source, "environment", 30), _var(source, "script_id", 10),
            _var(source, "agent", 30) or None)


def _back(environment: str, script_id: str, agent: Optional[str], folder: str) -> None:
    pairs = (("environment", environment), ("script_id", script_id), ("area", "inputs"),
             ("agent", agent), ("dir", folder))
    redirect(URL(c="files", f="index", vars=dict((k, v) for k, v in pairs if v)))


def _agents_or_404(ctx: Dict[str, Any], environment: str) -> List[str]:
    """Agentes para a escolha (so quando ha mais de um); senao 404."""
    found: List[str] = []
    try:
        files.scripts(ctx, environment)
        found = files.agents(environment)
    except (RepoNotFound, InvalidRequest, NoAgent):
        _not_found(_MSG_NOT_FOUND)
    if len(found) < 2:
        _not_found(_MSG_NOT_FOUND)
    return found


def index() -> Dict[str, Any]:
    """Ambientes, scripts do ambiente, a escolha do agente ou a pasta (inputs ou outputs)."""
    _require_method("GET", "HEAD")
    ctx = _ctx()
    response.title = u"Pasta de Arquivos — SSS"
    response.sss_scripts = [_JS]
    environment, script_id, agent = _location(request.get_vars)
    areas = files.areas(ctx)
    area = _var(request.get_vars, "area", 10) or (areas[0] if areas else "")
    data: Dict[str, Any] = dict(level="environment", environment=environment, rows=[], view=None,
                                error=None, areas=areas, agents=[], script_id=script_id, area=area)
    try:
        if not environment:
            data["rows"] = files.environments(ctx)
        elif not script_id:
            data.update(level="script", rows=files.scripts(ctx, environment))
        else:
            data.update(level="folder", view=files.folder(
                ctx, environment, script_id, area, agent, _var(request.get_vars, "dir", 4200)))
    except InvalidRequest:
        if not (environment and script_id and not agent):
            _not_found(_MSG_NOT_FOUND)
        # Mais de um agente no ambiente: a tela pede a escolha (D2).
        data.update(level="agent", agents=_agents_or_404(ctx, environment))
    except NoAgent:
        data["error"] = files.MSG_NO_AGENT
    except RepoNotFound:
        _not_found(_MSG_NOT_FOUND)
    except RepoError:
        _log.exception("falha ao carregar a pasta de arquivos (login=%s)", ctx["login"],
                       extra={"action": _ACTION})
        data["error"] = _MSG_FAILED
    return data


def upload() -> None:
    """Envio de um arquivo para inputs (POST multipart)."""
    _require_method("POST")
    ctx = _require_func("FILES_UPLOAD")
    environment, script_id, agent = _location(request.post_vars)
    folder = _var(request.post_vars, "relative_dir", 4200)
    current = _var(request.post_vars, "dir", 4200)
    field = request.post_vars.get("file")
    stream = getattr(field, "file", None)
    filename = getattr(field, "filename", None) if stream is not None else None
    result: Optional[Dict[str, Any]] = None
    errors: Dict[str, str] = {}
    try:
        result, errors = files.upload(ctx, _client_ip(), environment, script_id, agent, folder,
                                      filename, stream, request.post_vars.get("replace") == "Y")
    except (RepoNotFound, InvalidRequest):
        _not_found(_MSG_NOT_FOUND)
    except NoAgent:
        session.flash = {"kind": "error", "message": files.MSG_NO_AGENT}
        _back(environment, script_id, agent, current)
    except (RepoError, OSError):
        _log.exception("falha ao gravar na pasta de arquivos (login=%s)", ctx["login"],
                       extra={"action": _ACTION})
        session.flash = {"kind": "error", "message": _MSG_UPLOAD_FAILED}
        _back(environment, script_id, agent, current)
    if errors or result is None:
        session.flash = {"kind": "error", "message": u" ".join(errors[k] for k in sorted(errors))}
    else:
        path, agent_code = result["path"], result["agent"]
        message = u"Arquivo gravado em inputs/%s (servidor %s)." % (path, agent_code)
        if result.get("audit_failed"):
            warn = message + u" Mas a auditoria falhou; avise o administrador."
            session.flash = {"kind": "warning", "message": warn}
        else:
            session.flash = {"kind": "success", "message": message}
    _back(environment, script_id, agent, current)


def _attachment(name: str) -> str:
    """Content-Disposition com nome ASCII e o nome UTF-8 (RFC 5987)."""
    ascii_name = "".join(c if 32 <= ord(c) < 127 else "_" for c in name)
    encoded = quote(name.encode("utf-8"), safe="")
    return "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (ascii_name, encoded)


def _send(name: str, size: Optional[int], parts: Iterable[bytes],
          content_type: str) -> Iterable[bytes]:
    response.headers["Content-Type"] = content_type
    response.headers["Content-Disposition"] = _attachment(name)
    if size is not None:
        response.headers["Content-Length"] = str(size)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Iteravel: o nucleo web o devolve ao WSGI como corpo em streaming, fatia a fatia. Sem
    # Content-Length (zip em fluxo), o corpo termina no fechamento da conexao (HTTP/1.0).
    return parts


def _download_failed(ctx: Dict[str, Any], what: str) -> None:
    _log.exception("falha ao iniciar %s da pasta de arquivos (login=%s)", what, ctx["login"],
                   extra={"action": _ACTION})
    raise HTTP(503, _MSG_DOWNLOAD_FAILED, **response.headers)


def download() -> Iterable[bytes]:
    """Um arquivo de outputs (auditado)."""
    _require_method("GET", "HEAD")
    ctx = _require_func("FILES_DOWNLOAD")
    environment, script_id, agent = _location(request.get_vars)
    try:
        name, size, parts = files.download(ctx, _client_ip(), environment, script_id, agent,
                                           _var(request.get_vars, "path", 4200))
    except (RepoNotFound, InvalidRequest, NoAgent):
        _not_found(_MSG_NOT_FOUND)
        raise
    except (RepoError, OSError):
        _download_failed(ctx, "o download")
        raise
    return _send(name, size, parts, "application/octet-stream")


def download_zip() -> Iterable[bytes]:
    """A pasta de outputs (ou uma subpasta) em zip, montado em fluxo (auditado)."""
    _require_method("GET", "HEAD")
    ctx = _require_func("FILES_DOWNLOAD")
    environment, script_id, agent = _location(request.get_vars)
    try:
        name, parts = files.download_zip(ctx, _client_ip(), environment, script_id, agent,
                                         _var(request.get_vars, "dir", 4200))
    except (RepoNotFound, InvalidRequest, NoAgent):
        _not_found(_MSG_NOT_FOUND)
        raise
    except (RepoError, OSError):
        _download_failed(ctx, "o zip")
        raise
    return _send(name, None, parts, "application/zip")
