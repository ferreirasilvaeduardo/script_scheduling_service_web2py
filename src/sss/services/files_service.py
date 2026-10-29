# -*- coding: utf-8 -*-
"""Pasta de Arquivos (CR-037, README §5.11 e §8.16): inputs e outputs por ambiente e script.

O conteudo nunca vai ao banco: o web le e grava direto em var/<agente>/files/<ambiente>/<script>/
(o banco guarda so a auditoria). inputs exige FILES_UPLOAD (ver e enviar, com substituicao
confirmada); outputs exige FILES_DOWNLOAD (navegar e baixar um arquivo ou a pasta em zip). Ambiente
e script do perfil (admin: todos), script ativo homologado em ambiente ativo. O agente vem do
cadastro de agentes que atendem o ambiente e tem a pasta neste servidor; com mais de um, a tela
pede a escolha. Fora disso, RepoNotFound (404, nunca 403). Nome e subpasta seguem a regra da tela
de Entrada (input_browse_service).
"""
import os
import threading
import time
import zipfile
from typing import IO, Any, BinaryIO, Dict, Iterator, List, Optional, Tuple, cast

from sss.config import log_paths
from sss.core import rbac
from sss.persistence.repo_errors import RepoNotFound
from sss.platform import files_area
from sss.services import admin_crud
from sss.services.input_browse_service import normalize_folder, upload_name, valid_part
from sss.ui import ui_helpers

FEATURE_UPLOAD = "FILES_UPLOAD"
FEATURE_DOWNLOAD = "FILES_DOWNLOAD"
AREAS = {"inputs": FEATURE_UPLOAD, "outputs": FEATURE_DOWNLOAD}
AUDIT_ENTITY = "files"
SEND_BYTES = 1048576
_CATALOG_MAX = 1000
_ZIP64_FROM = 1 << 30
_MTIME_MIN = 315532800.0  # 1980-01-01: o zip nao guarda datas anteriores
_LOG_ACTION = {"action": "ARQUIVOS"}

MSG_FILE = u"Escolha um arquivo para enviar."
MSG_SIZE = u"O arquivo passa do tamanho máximo de %s."
MSG_NAME = (u"Use um nome de até 255 caracteres, sem barra, sem caractere de controle e sem ponto "
            u"no início.")
MSG_FOLDER = (u"Escreva a subpasta como nomes separados por /, até 10 níveis, sem '..', sem ponto "
              u"no início de um nível e sem caractere de controle.")
MSG_EXISTS = (u"Já existe um arquivo com esse nome nessa pasta. Marque \"Substituir se já "
              u"existir\" para trocá-lo.")
MSG_NO_AGENT = u"Nenhum servidor deste ambiente tem a pasta de arquivos neste servidor web."

Ctx = Dict[str, Any]
Area = Tuple[Dict[str, Any], str, str, List[str]]


class InvalidRequest(Exception):
    """Parametro de navegacao fora do formato (o controller responde 404)."""


class NoAgent(Exception):
    """Nenhum agente do ambiente tem a pasta neste servidor (a tela mostra MSG_NO_AGENT)."""


def _parts(folder: str) -> List[str]:
    return folder.split("/") if folder else []


def _folder(folder: Optional[str]) -> str:
    current = normalize_folder(folder)
    if current is None:
        raise InvalidRequest("pasta invalida")
    return current


class FilesService(object):
    """Leituras e gravacoes da Pasta de Arquivos: catalogo, agentes, auditoria e disco."""

    def __init__(self, catalog: Any, agents: Any, audit: Any, log: Any, max_bytes: int,
                 var_dir: str) -> None:
        self._catalog = catalog
        self._agents = agents
        self._audit = audit
        self._log = log
        self.max_bytes = int(max_bytes)
        self._var_dir = var_dir

    # ------------------------------------------------------------------ escopo

    @staticmethod
    def areas(ctx: Ctx) -> List[str]:
        """As pastas que o perfil abre: inputs (FILES_UPLOAD) e outputs (FILES_DOWNLOAD)."""
        return [a for a in ("inputs", "outputs") if rbac.has_feature(ctx, AREAS[a])]

    def _view(self, ctx: Ctx) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if not self.areas(ctx):
            admin_crud.require_feature(ctx, FEATURE_UPLOAD)
        admin = ctx.get("is_admin") is True
        envs = [a for a in self._catalog.environments_list(page=1, size=_CATALOG_MAX)["items"]
                if a.get("active") == "Y"
                and (admin or a["name"] in (ctx.get("environments") or ()))]
        scripts = [s for s in self._catalog.scripts_list(page=1, size=_CATALOG_MAX)["items"]
                   if s.get("active") == "Y" and (admin or s["id"] in (ctx.get("scripts") or ()))]
        return envs, scripts

    def environments(self, ctx: Ctx) -> List[Dict[str, Any]]:
        """Ambientes ativos do perfil."""
        envs, _scripts = self._view(ctx)
        return sorted(({"name": a["name"], "description": a.get("description")} for a in envs),
                      key=lambda a: str(a["name"]))

    def scripts(self, ctx: Ctx, environment: str) -> List[Dict[str, Any]]:
        """Scripts ativos do perfil homologados no ambiente."""
        envs, scripts = self._view(ctx)
        if environment not in [a["name"] for a in envs]:
            raise RepoNotFound("ambiente fora do escopo")
        return sorted(({"id": s["id"], "name": s["name"], "description": s.get("description")}
                       for s in scripts
                       if environment in (s.get("homologated_environments") or ())),
                      key=lambda s: str(s["name"]))

    def _script(self, ctx: Ctx, environment: str, script_id: Any) -> Dict[str, Any]:
        try:
            sid = int(str(script_id))
        except (TypeError, ValueError):
            raise InvalidRequest("script invalido")
        for s in self.scripts(ctx, environment):
            if s["id"] == sid:
                return s
        self._log.warning("pasta de arquivos: script fora do escopo (login=%s ambiente=%r "
                          "script=%r)", ctx.get("login"), environment, script_id,
                          extra=_LOG_ACTION)
        raise RepoNotFound("script fora do escopo")

    def agents(self, environment: str) -> List[str]:
        """Agentes que atendem o ambiente e tem var/<agente>/files neste servidor (D2)."""
        found = set()
        for row in self._agents.list():
            served = [e.strip() for e in (row.get("environments") or "").split(",")]
            code = row.get("code") or ""
            if environment in served and code \
                    and os.path.isdir(os.path.join(self._var_dir, code, "files")):
                found.add(code)
        return sorted(found)

    def _area(self, ctx: Ctx, environment: str, script_id: Any, area: str,
              agent: Optional[str]) -> Area:
        """(script, agente, raiz da area, agentes), conferidos permissao, escopo e agente."""
        if area not in AREAS:
            raise InvalidRequest("area invalida")
        if area not in self.areas(ctx):
            raise RepoNotFound("area fora do perfil")
        script = self._script(ctx, environment, script_id)
        agents = self.agents(environment)
        if not agents:
            raise NoAgent(environment)
        chosen = agent or (agents[0] if len(agents) == 1 else None)
        if chosen is None or chosen not in agents:
            raise InvalidRequest("agente nao escolhido ou fora do ambiente")
        files_dir = os.path.join(self._var_dir, chosen, "files")
        _base, _rel, inputs, outputs = log_paths.files_dirs(files_dir, environment, script["name"],
                                                            script["id"])
        return script, chosen, inputs if area == "inputs" else outputs, agents

    def _audit_line(self, ctx: Ctx, ip: str, action: str, detail: str) -> None:
        self._audit.register(ctx.get("login"), ip, action, AUDIT_ENTITY, None,
                             admin_crud.free_detail(detail))

    # ------------------------------------------------------------------ pasta

    def folder(self, ctx: Ctx, environment: str, script_id: Any, area: str, agent: Optional[str],
               folder: Optional[str] = "") -> Dict[str, Any]:
        """Conteudo da pasta (subpastas e arquivos). Pasta que ainda nao existe aparece vazia."""
        script, chosen, root, agents = self._area(ctx, environment, script_id, area, agent)
        current = _folder(folder)
        try:
            path = files_area.walk_dirs(root, _parts(current))
        except files_area.AreaError:
            raise RepoNotFound("pasta fora do formato")
        folders, files = files_area.list_dir(path) if path else ([], [])
        crumbs, acc = [], []
        for part in _parts(current):
            acc.append(part)
            crumbs.append({"name": part, "path": "/".join(acc)})
        prefix = current + "/" if current else ""
        return {"script": script, "environment": environment, "area": area, "agent": chosen,
                "agents": agents, "areas": self.areas(ctx), "folder": current, "crumbs": crumbs,
                "subfolders": [{"name": n, "path": prefix + n} for n in folders],
                "files": [{"name": f.name, "path": prefix + f.name, "size": f.size,
                           "mtime": time.strftime("%d/%m/%Y %H:%M", time.localtime(f.mtime))}
                          for f in files],
                "max_bytes": self.max_bytes}

    # ------------------------------------------------------------------ envio (inputs)

    def upload(self, ctx: Ctx, ip: str, environment: str, script_id: Any, agent: Optional[str],
               folder: Optional[str], file_name: Optional[str], stream: Optional[BinaryIO],
               replace: bool) -> Tuple[Optional[Dict[str, Any]], Dict[str, str]]:
        """Grava o arquivo em inputs. Devolve (resultado {path, size, agent} ou None, erros)."""
        script, chosen, root, _agents = self._area(ctx, environment, script_id, "inputs", agent)
        errors = {}
        current = normalize_folder(folder)
        if current is None:
            errors["relative_dir"] = MSG_FOLDER
        name = upload_name(file_name)
        if not name:
            errors["file"] = MSG_FILE
        elif not valid_part(name):
            errors["file"] = MSG_NAME
        if stream is None:
            errors.setdefault("file", MSG_FILE)
        if errors or stream is None or current is None:
            return None, errors
        try:
            target = files_area.walk_dirs(root, _parts(current), create=True)
            size, digest = files_area.write_file(str(target), name, stream, self.max_bytes,
                                                 replace)
        except files_area.FileExists:
            return None, {"file": MSG_EXISTS}
        except files_area.TooLarge:
            return None, {"file": MSG_SIZE % ui_helpers.readable_size(self.max_bytes)}
        except files_area.AreaError:
            raise RepoNotFound("pasta fora do formato")
        path = "/".join(p for p in (current, name) if p)
        detail = u"%s/%s/inputs/%s (%d bytes, sha256 %s%s; agente %s)" % (
            environment, script["name"], path, size, digest, u", substituído" if replace else u"",
            chosen)
        self._audit_line(ctx, ip, "FILES_UPLOAD", detail)
        self._log.info("envio para a pasta de arquivos (login=%s ambiente=%s script=%s arquivo=%s "
                       "bytes=%d agente=%s)", ctx.get("login"), environment, script["name"], path,
                       size, chosen, extra=_LOG_ACTION)
        return {"path": path, "size": size, "agent": chosen}, {}

    # ------------------------------------------------------------------ download (outputs)

    def download(self, ctx: Ctx, ip: str, environment: str, script_id: Any, agent: Optional[str],
                 path: Optional[str]) -> Tuple[str, int, Iterator[bytes]]:
        """(nome, tamanho, fatias) de um arquivo de outputs; audita antes do envio."""
        script, chosen, root, _agents = self._area(ctx, environment, script_id, "outputs", agent)
        current = _folder(path)
        parts = _parts(current)
        if not parts:
            raise InvalidRequest("arquivo nao informado")
        try:
            folder = files_area.walk_dirs(root, parts[:-1])
            if folder is None:
                raise RepoNotFound("arquivo inexistente")
            handle, size = files_area.open_file(folder, parts[-1])
        except files_area.AreaError:
            raise RepoNotFound("arquivo inexistente")
        self._audit_line(ctx, ip, "FILES_DOWNLOAD", u"%s/%s/outputs/%s (%d bytes; agente %s)" % (
            environment, script["name"], current, size, chosen))
        return parts[-1], size, _file_chunks(handle)

    def download_zip(self, ctx: Ctx, ip: str, environment: str, script_id: Any,
                     agent: Optional[str], folder: Optional[str]) -> Tuple[str, Iterator[bytes]]:
        """(nome do zip, fatias) da pasta de outputs, montado em fluxo; audita antes do envio."""
        script, chosen, root, _agents = self._area(ctx, environment, script_id, "outputs", agent)
        current = _folder(folder)
        try:
            path = files_area.walk_dirs(root, _parts(current))
        except files_area.AreaError:
            raise RepoNotFound("pasta fora do formato")
        if path is None:
            raise RepoNotFound("pasta inexistente")
        detail = u"%s/%s/outputs/%s (zip da pasta; agente %s)" % (
            environment, script["name"], current or ".", chosen)
        self._audit_line(ctx, ip, "FILES_DOWNLOAD", detail)
        label = "_".join(p for p in (script["name"], current.replace("/", "_")) if p)
        return u"%s_outputs.zip" % label, _zip_stream(path)


def _file_chunks(handle: BinaryIO) -> Iterator[bytes]:
    with handle:
        while True:
            part = handle.read(SEND_BYTES)
            if not part:
                return
            yield part


class _Collector(object):
    """Saida sem seek do zipfile: guarda os bytes escritos ate o gerador entrega-los."""

    def __init__(self) -> None:
        self._parts: List[bytes] = []
        self._written = 0

    def write(self, data: bytes) -> int:
        self._parts.append(bytes(data))
        self._written += len(data)
        return len(data)

    def tell(self) -> int:
        return self._written

    def flush(self) -> None:
        return None

    def take(self) -> bytes:
        data, self._parts = b"".join(self._parts), []
        return data


def _zip_stream(folder: str) -> Iterator[bytes]:
    """Zip (ZIP_DEFLATED) dos arquivos comuns da pasta, gerado em fatias enquanto e enviado."""
    out = _Collector()
    with zipfile.ZipFile(cast(IO[bytes], out), "w", zipfile.ZIP_DEFLATED) as z:
        for path, name in files_area.tree_files(folder):
            try:
                handle, size = files_area.open_file(os.path.dirname(path), os.path.basename(path))
            except files_area.AreaError:  # fluxo previsto: apagado ou virou link durante o zip
                continue
            with handle:
                mtime = max(os.fstat(handle.fileno()).st_mtime, _MTIME_MIN)
                info = zipfile.ZipInfo(name, time.localtime(mtime)[:6])
                info.compress_type = zipfile.ZIP_DEFLATED
                with z.open(info, "w", force_zip64=size >= _ZIP64_FROM) as dst:
                    while True:
                        chunk = handle.read(SEND_BYTES)
                        if not chunk:
                            break
                        dst.write(chunk)
                        data = out.take()
                        if data:
                            yield data
            data = out.take()
            if data:
                yield data
    data = out.take()
    if data:
        yield data


_default: Optional[FilesService] = None
_default_lock = threading.Lock()


def _service() -> FilesService:
    global _default
    with _default_lock:
        if _default is None:
            from sss.config import app_context
            from sss.config import sss_config
            from sss.config import sss_logging
            from sss.persistence import repo_factory
            cfg = app_context.require_config()
            _default = FilesService(catalog=repo_factory.get("catalog"),
                                    agents=repo_factory.get("agents"),
                                    audit=repo_factory.get("audit"),
                                    log=sss_logging.get_logger("sss_web", cfg),
                                    max_bytes=cfg.web.files_upload_max_bytes,
                                    var_dir=sss_config.VAR_DIR)
        return _default


def areas(ctx: Ctx) -> List[str]:
    return FilesService.areas(ctx)


def environments(ctx: Ctx) -> List[Dict[str, Any]]:
    return _service().environments(ctx)


def scripts(ctx: Ctx, environment: str) -> List[Dict[str, Any]]:
    return _service().scripts(ctx, environment)


def agents(environment: str) -> List[str]:
    return _service().agents(environment)


def folder(ctx: Ctx, environment: str, script_id: Any, area: str, agent: Optional[str],
           folder_value: Optional[str] = "") -> Dict[str, Any]:
    return _service().folder(ctx, environment, script_id, area, agent, folder_value)


def upload(ctx: Ctx, ip: str, environment: str, script_id: Any, agent: Optional[str],
           folder_value: Optional[str], file_name: Optional[str], stream: Optional[BinaryIO],
           replace: bool) -> Tuple[Optional[Dict[str, Any]], Dict[str, str]]:
    return _service().upload(ctx, ip, environment, script_id, agent, folder_value, file_name,
                             stream, replace)


def download(ctx: Ctx, ip: str, environment: str, script_id: Any, agent: Optional[str],
             path: Optional[str]) -> Tuple[str, int, Iterator[bytes]]:
    return _service().download(ctx, ip, environment, script_id, agent, path)


def download_zip(ctx: Ctx, ip: str, environment: str, script_id: Any, agent: Optional[str],
                 folder_value: Optional[str]) -> Tuple[str, Iterator[bytes]]:
    return _service().download_zip(ctx, ip, environment, script_id, agent, folder_value)


def max_bytes() -> int:
    return _service().max_bytes
