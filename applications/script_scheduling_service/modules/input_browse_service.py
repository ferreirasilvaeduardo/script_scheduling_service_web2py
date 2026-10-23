# -*- coding: utf-8 -*-
"""Tela de Entrada (CR-020d, README §5.10): navegar pela pasta de entrada dos scripts e enviar arquivos para ela.

A pasta existe so no servidor de cada agente; a tela mostra o retrato que cada agente publicou
(tbsss_input_listing) e o envio vai pelo banco para todos os agentes vivos do ambiente (repositorio inputs).
Permissao: UPLOAD_INPUT, o ambiente e o script no perfil (admin: todos), so script ativo homologado em
ambiente ativo. Fora disso, RepoNotFound (404, nunca 403). Nome e subpasta seguem a regra do helper put-input.
"""
import hashlib
import json
import re
import threading

import admin_crud
import ui_helpers
from repo_errors import RepoNotFound
from repo_inputs import NoLiveAgent

FEATURE = "UPLOAD_INPUT"
UPLOADS_PAGE = 20
DEPTH_MAX = 10
GENERAL_FIELD = "_geral"
_RE_PART = re.compile(r"^[^/\x00-\x1f\x7f]{1,255}$")
_CATALOG_MAX = 1000

MSG_FILE = u"Escolha um arquivo para enviar."
MSG_SIZE = u"O arquivo passa do tamanho máximo de %s."
MSG_NAME = (u"Use um nome de até 255 caracteres, sem barra, sem caractere de controle e sem ponto no início.")
MSG_FOLDER = (u"Escreva a subpasta como nomes separados por /, até 10 níveis, sem '..', sem ponto no início de "
              u"um nível e sem caractere de controle.")
MSG_NO_AGENT = u"Nenhum servidor deste ambiente está no ar agora. Tente de novo mais tarde."
STATE_LABELS = {"PENDING": u"Aguardando", "DELIVERED": u"Entregue", "FAILED": u"Falhou"}
REASON_LABELS = {
    "EXISTS": u"já existia um arquivo com esse nome (não foi substituído)",
    "NAME": u"o servidor recusou o nome ou a pasta",
    "SPACE": u"o servidor está sem espaço",
    "HASH": u"o arquivo chegou diferente do enviado",
    "ERROR": u"erro no servidor",
}


class InvalidRequest(Exception):
    """Parametro de navegacao fora do formato (o controller responde 404)."""


def valid_part(text):
    """Um nivel da subpasta ou o nome do arquivo, como o helper put-input confere."""
    return isinstance(text, str) and bool(_RE_PART.match(text)) and not text.startswith(".")


def normalize_folder(text):
    """Subpasta digitada ou da URL: '' (a propria pasta do script) ou 'a/b'; None se fora do formato."""
    text = (text or "").strip().strip("/")
    if not text:
        return ""
    parts = text.split("/")
    if len(parts) > DEPTH_MAX or not all(valid_part(p) for p in parts):
        return None
    return "/".join(parts)


def upload_name(filename):
    """So o ultimo nivel do nome enviado pelo navegador (alguns mandam o caminho do computador)."""
    return re.split(r"[\\/]", filename or "")[-1].strip()


class InputBrowseService(object):
    """Leituras e gravacoes da tela de Entrada sobre o catalogo e o repositorio inputs."""

    def __init__(self, catalog, inputs, log, max_bytes, live_seconds):
        self._catalog = catalog
        self._inputs = inputs
        self._log = log
        self.max_bytes = int(max_bytes)
        self._live_seconds = int(live_seconds)

    # ------------------------------------------------------------------ escopo

    def _view(self, ctx):
        """Ambientes ativos e scripts ativos do escopo, com a homologacao (uma leitura de cada)."""
        admin_crud.require_feature(ctx, FEATURE)
        admin = ctx.get("is_admin") is True
        envs = [a for a in self._catalog.environments_list(page=1, size=_CATALOG_MAX)["items"]
                if a.get("active") == "Y" and (admin or a["name"] in (ctx.get("environments") or ()))]
        scripts = [s for s in self._catalog.scripts_list(page=1, size=_CATALOG_MAX)["items"]
                   if s.get("active") == "Y" and (admin or s["id"] in (ctx.get("scripts") or ()))]
        return envs, scripts

    def environments(self, ctx):
        envs, _scripts = self._view(ctx)
        return sorted(({"name": a["name"], "description": a.get("description")} for a in envs),
                      key=lambda a: a["name"])

    def scripts(self, ctx, environment):
        envs, scripts = self._view(ctx)
        if environment not in [a["name"] for a in envs]:
            raise RepoNotFound("ambiente fora do escopo")
        return sorted(({"id": s["id"], "name": s["name"], "description": s.get("description")} for s in scripts
                       if environment in (s.get("homologated_environments") or ())), key=lambda s: s["name"])

    def _require(self, ctx, environment, script_id):
        try:
            sid = int(str(script_id))
        except (TypeError, ValueError):
            raise InvalidRequest("script invalido")
        for s in self.scripts(ctx, environment):
            if s["id"] == sid:
                return s
        self._log.warning("entrada: script fora do escopo (login=%s ambiente=%r script=%r)", ctx.get("login"),
                          environment, script_id, extra={"action": "ENTRADA"})
        raise RepoNotFound("script fora do escopo")

    # ------------------------------------------------------------------ pasta

    def folder(self, ctx, environment, script_id, folder="", page=1):
        """Conteudo da pasta (folder relativo a pasta do script) montado pelos retratos dos agentes."""
        script = self._require(ctx, environment, script_id)
        current = normalize_folder(folder)
        if current is None:
            raise InvalidRequest("pasta invalida")
        prefix = current + "/" if current else ""
        subfolders, files, listings = {}, {}, []
        for row in self._inputs.listings(environment, script["id"]):
            listings.append({"agent_id": row["agent_id"], "listed_at": row["listed_at"],
                             "refresh_requested_at": row["refresh_requested_at"],
                             "file_count": row["file_count"], "truncated": row["truncated"] == "Y"})
            try:
                items = json.loads(row["listing"]) if row["listing"] else []
            except ValueError:
                self._log.warning("entrada: retrato ilegivel (agente=%s)", row["agent_id"], extra={"action": "ENTRADA"})
                items = []
            for item in items:
                path = item.get("path") or ""
                if not path.startswith(prefix):
                    continue
                rest = path[len(prefix):]
                if "/" in rest:
                    name = rest.split("/", 1)[0]
                    subfolders[name] = prefix + name
                    continue
                entry = files.setdefault(rest, {"name": rest, "size": item.get("size"), "mtime": item.get("mtime"),
                                                "agents": []})
                entry["agents"].append(row["agent_id"])
        uploads = self._inputs.uploads(environment, script["id"], page=max(1, int(page or 1)), size=UPLOADS_PAGE)
        for u in uploads["items"]:
            u["created_by"] = ui_helpers.visible_actor(u.get("created_by"), ctx)
            u["target"] = "/".join(x for x in (u.get("relative_dir"), u["file_name"]) if x)
            for d in u["deliveries"]:
                d["state_label"] = STATE_LABELS.get(d["state"], d["state"])
                d["reason_label"] = REASON_LABELS.get(d["reason"]) if d.get("reason") else None
        crumbs, acc = [], []
        for part in current.split("/") if current else []:
            acc.append(part)
            crumbs.append({"name": part, "path": "/".join(acc)})
        return {"script": script, "environment": environment, "folder": current, "crumbs": crumbs,
                "subfolders": [{"name": n, "path": p} for n, p in sorted(subfolders.items())],
                "files": [files[n] for n in sorted(files)], "listings": listings, "uploads": uploads,
                "max_bytes": self.max_bytes}

    def refresh(self, ctx, environment, script_id):
        """Pede um retrato novo a cada agente vivo do ambiente. Devolve quantos foram avisados."""
        script = self._require(ctx, environment, script_id)
        return self._inputs.request_listing(environment, script["id"], ctx["login"], self._live_seconds)

    # ------------------------------------------------------------------ envio

    def upload(self, ctx, ip, environment, script_id, folder, file_name, stream, replace):
        """Valida e grava o envio. Retorna (resultado {id, agents} ou None, erros por campo)."""
        script = self._require(ctx, environment, script_id)
        errors = {}
        current = normalize_folder(folder)
        if current is None:
            errors["relative_dir"] = MSG_FOLDER
        name = upload_name(file_name)
        if not name:
            errors["file"] = MSG_FILE
        elif not valid_part(name):
            errors["file"] = MSG_NAME
        content = b""
        if stream is None:
            errors.setdefault("file", MSG_FILE)
        else:
            content = stream.read(self.max_bytes + 1)
            if len(content) > self.max_bytes:
                errors["file"] = MSG_SIZE % ui_helpers.readable_size(self.max_bytes)
        if errors:
            return None, errors
        data = {"environment": environment, "script_id": script["id"], "relative_dir": current or None,
                "file_name": name, "sha256": hashlib.sha256(content).hexdigest(),
                "replace_existing": "Y" if replace else "N"}
        try:
            result = self._inputs.create_upload(data, content, ctx["login"], ip, self._live_seconds)
        except NoLiveAgent:
            return None, {GENERAL_FIELD: MSG_NO_AGENT}
        self._log.info("envio para a entrada (login=%s ambiente=%s script=%s arquivo=%s bytes=%d agentes=%d)",
                       ctx.get("login"), environment, script["name"], name, len(content), len(result["agents"]),
                       extra={"action": "ENTRADA"})
        return result, {}


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from gluon import current
            import sss_logging
            factory = current.repo_factory
            cfg = current.sss_cfg
            _default = InputBrowseService(catalog=factory.get("catalog"), inputs=factory.get("inputs"),
                                          log=sss_logging.get_logger("sss_web", cfg),
                                          max_bytes=cfg.web.input_upload_max_bytes,
                                          live_seconds=cfg.agent.node_offline_timeout_s)
        return _default


def environments(ctx):
    return _service().environments(ctx)


def scripts(ctx, environment):
    return _service().scripts(ctx, environment)


def folder(ctx, environment, script_id, folder_value="", page=1):
    return _service().folder(ctx, environment, script_id, folder_value, page)


def refresh(ctx, environment, script_id):
    return _service().refresh(ctx, environment, script_id)


def upload(ctx, ip, environment, script_id, folder_value, file_name, stream, replace):
    return _service().upload(ctx, ip, environment, script_id, folder_value, file_name, stream, replace)


def max_bytes():
    return _service().max_bytes
