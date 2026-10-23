# -*- coding: utf-8 -*-
"""Tela de Saidas (CR-020a, README §5.9): navegacao pelas saidas dos tickets e download do zip ou de um arquivo.

A navegacao segue as partes da pasta de saida (ambiente, script, dia, ticket), montada a partir do banco:
so saidas AVAILABLE, que estao em tbsss_ticket_output (as EXCEEDED e FAILED ficaram so no disco do agente).
Permissao: DOWNLOAD_OUTPUT e o ambiente no perfil (tickets de outras pessoas incluidos, como em VIEW_LOGS).
O zip e lido do BLOB por um leitor com seek: o zipfile le so o diretorio central e o item pedido.
Todo download grava OUTPUT_DOWNLOAD na auditoria antes do envio.
"""
import datetime
import threading
import zipfile

import admin_crud
import rbac
import ui_helpers
from repo_errors import RepoNotFound

FEATURE = "DOWNLOAD_OUTPUT"
AUDIT_ACTION = "OUTPUT_DOWNLOAD"
AUDIT_ENTITY = "tbsss_tickets"
TICKETS_PAGE = 20
FILES_PAGE = 100
BLOCK_BYTES = 256 * 1024
SEND_BYTES = 256 * 1024
NAME_MAX = 500


class InvalidRequest(Exception):
    """Parametro de navegacao fora do formato (o controller responde 404, sem revelar o motivo)."""


class BlobReader(object):
    """Arquivo somente leitura sobre o BLOB da saida (repo.output_read), em blocos de 256 KiB com cache.

    Tem read, seek e tell, o que basta ao zipfile para ler o diretorio central do fim do zip e um item.
    """

    def __init__(self, tickets, ticket_id, size):
        self._tickets = tickets
        self._tid = int(ticket_id)
        self._size = int(size)
        self._pos = 0
        self._block_start = None
        self._block = b""

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self._pos

    def seek(self, offset, whence=0):
        if whence == 0:
            target = offset
        elif whence == 1:
            target = self._pos + offset
        elif whence == 2:
            target = self._size + offset
        else:
            raise ValueError("whence invalido")
        if target < 0:
            raise ValueError("posicao negativa")
        self._pos = target
        return self._pos

    def _load(self, start):
        start = (start // BLOCK_BYTES) * BLOCK_BYTES
        if self._block_start != start:
            self._block = self._tickets.output_read(self._tid, start, BLOCK_BYTES) or b""
            self._block_start = start

    def read(self, n=-1):
        if n is None or n < 0:
            n = self._size - self._pos
        parts = []
        while n > 0 and self._pos < self._size:
            self._load(self._pos)
            inside = self._pos - self._block_start
            piece = self._block[inside:inside + n]
            if not piece:
                break
            parts.append(piece)
            self._pos += len(piece)
            n -= len(piece)
        return b"".join(parts)

    def close(self):
        self._block = b""


def _day(value):
    """'AAAA-MM-DD' da URL em datetime a 00:00, ou InvalidRequest."""
    try:
        return datetime.datetime.strptime(str(value or ""), "%Y-%m-%d")
    except ValueError:
        raise InvalidRequest("dia invalido")


def _int(value):
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        raise InvalidRequest("numero invalido")
    if number < 1:
        raise InvalidRequest("numero invalido")
    return number


def download_name(name):
    """Nome do arquivo para o Content-Disposition: so o ultimo nivel, sem aspas, barra nem controle."""
    base = (name or "").rsplit("/", 1)[-1]
    clean = "".join(c for c in base if c.isprintable() and c not in '"\\;')
    return clean or "arquivo"


class OutputBrowseService(object):
    """Leituras da tela de Saidas sobre o repositorio de tickets e a auditoria."""

    def __init__(self, tickets, catalog, audit, log):
        self._tickets = tickets
        self._catalog = catalog
        self._audit = audit
        self._log = log

    # ------------------------------------------------------------------ escopo

    @staticmethod
    def _scope(ctx):
        admin_crud.require_feature(ctx, FEATURE)
        if ctx.get("is_admin") is True:
            return None
        return tuple(ctx.get("environments") or ())

    def _require_environment(self, ctx, environment):
        if not isinstance(environment, str) or not environment or not rbac.can_view_environment(ctx, environment):
            self._log.warning("saidas: ambiente fora do escopo (login=%s ambiente=%r)", ctx.get("login"), environment,
                              extra={"action": AUDIT_ACTION})
            raise RepoNotFound("ambiente fora do escopo")

    def _ticket_output(self, ctx, ticket_id):
        """Ticket visivel com saida AVAILABLE: (ticket, saida); fora disso, RepoNotFound (404, nao 403)."""
        scope = self._scope(ctx)
        ticket = self._tickets.get(_int(ticket_id))
        if scope is not None and ticket.get("environment") not in scope:
            self._log.warning("saidas: ticket fora do escopo (login=%s ticket=%s)", ctx.get("login"), ticket["id"],
                              extra={"action": AUDIT_ACTION})
            raise RepoNotFound("ticket fora do escopo")
        output = self._tickets.output_get(ticket["id"])
        if not output or output.get("state") != "AVAILABLE" or not output.get("size_bytes"):
            raise RepoNotFound("saida indisponivel")
        return ticket, output

    def _script_name(self, script_id):
        try:
            return self._catalog.scripts_get(int(script_id))["name"]
        except RepoNotFound:
            return u"script %s" % script_id

    # ------------------------------------------------------------------ navegacao

    def environments(self, ctx):
        """[{environment, count, last_at}] com saida disponivel no escopo."""
        return self._tickets.output_summary("environment", environment_scope=self._scope(ctx))

    def scripts(self, ctx, environment):
        scope = self._scope(ctx)
        self._require_environment(ctx, environment)
        return self._tickets.output_summary("script", environment_scope=scope, environment=environment)

    def days(self, ctx, environment, script_id):
        scope = self._scope(ctx)
        self._require_environment(ctx, environment)
        sid = _int(script_id)
        return {"script_name": self._script_name(sid),
                "days": self._tickets.output_summary("day", environment_scope=scope, environment=environment,
                                                     script_id=sid)}

    def tickets(self, ctx, environment, script_id, day, page=1):
        scope = self._scope(ctx)
        self._require_environment(ctx, environment)
        sid = _int(script_id)
        start = _day(day)
        result = self._tickets.output_tickets(environment, sid, start, start + datetime.timedelta(days=1),
                                              page=_int(page or 1), size=TICKETS_PAGE, environment_scope=scope)
        for item in result["items"]:
            item["requested_by"] = ui_helpers.visible_actor(item.get("requested_by"), ctx)
        result["script_name"] = self._script_name(sid)
        return result

    def files(self, ctx, ticket_id, page=1):
        """Ticket, saida e os arquivos do zip (sem as pastas), por nome, em paginas de FILES_PAGE."""
        ticket, output = self._ticket_output(ctx, ticket_id)
        entries = self._entries(ticket["id"], output["size_bytes"])
        p = _int(page or 1)
        info = {"id": ticket["id"], "environment": ticket["environment"], "script_id": ticket["script_id"],
                "script_name": self._script_name(ticket["script_id"]), "started_at": ticket.get("started_at"),
                "requested_by": ui_helpers.visible_actor(ticket.get("requested_by"), ctx)}
        return {"ticket": info, "output": output, "total": len(entries), "page": p, "size": FILES_PAGE,
                "items": entries[(p - 1) * FILES_PAGE:p * FILES_PAGE]}

    def _entries(self, ticket_id, size):
        reader = BlobReader(self._tickets, ticket_id, size)
        try:
            with zipfile.ZipFile(reader) as z:
                items = []
                for info in z.infolist():
                    if info.filename.endswith("/"):
                        continue
                    folder, _sep, base = info.filename.rpartition("/")
                    items.append({"name": info.filename, "folder": folder, "base": base,
                                  "size": info.file_size, "date": datetime.datetime(*info.date_time)})
        except zipfile.BadZipFile:
            self._log.error("saidas: zip ilegivel no banco (ticket=%s)", ticket_id, extra={"action": AUDIT_ACTION})
            raise RepoNotFound("zip ilegivel")
        return sorted(items, key=lambda e: e["name"])

    # ------------------------------------------------------------------ downloads

    def _register(self, ctx, ip, ticket_id, what):
        detail = admin_crud.free_detail(u"saída do ticket #%s: %s" % (ticket_id, what))
        self._audit.register(ctx.get("login"), ip, AUDIT_ACTION, AUDIT_ENTITY, ticket_id, detail)
        self._log.info("download de saida (login=%s ticket=%s %s)", ctx.get("login"), ticket_id, what,
                       extra={"action": AUDIT_ACTION})

    def zip_download(self, ctx, ip, ticket_id):
        """(ticket_id, tamanho, gerador de fatias) do zip inteiro; audita antes do envio."""
        ticket, output = self._ticket_output(ctx, ticket_id)
        tid, size = ticket["id"], int(output["size_bytes"])
        self._register(ctx, ip, tid, u"zip completo (%d bytes)" % size)
        return tid, size, self._zip_chunks(tid, size)

    def _zip_chunks(self, tid, size):
        off = 0
        while off < size:
            part = self._tickets.output_read(tid, off, SEND_BYTES)
            if not part:
                return
            off += len(part)
            yield part

    def file_download(self, ctx, ip, ticket_id, name):
        """(nome para download, tamanho, gerador) de um arquivo do zip; o nome tem de estar no indice."""
        if not isinstance(name, str) or not name or len(name) > NAME_MAX or name.endswith("/"):
            raise InvalidRequest("nome invalido")
        ticket, output = self._ticket_output(ctx, ticket_id)
        tid = ticket["id"]
        reader = BlobReader(self._tickets, tid, output["size_bytes"])
        try:
            z = zipfile.ZipFile(reader)
        except zipfile.BadZipFile:
            self._log.error("saidas: zip ilegivel no banco (ticket=%s)", tid, extra={"action": AUDIT_ACTION})
            raise RepoNotFound("zip ilegivel")
        try:
            info = z.getinfo(name)
        except KeyError:
            z.close()
            raise RepoNotFound("arquivo fora do zip")
        self._register(ctx, ip, tid, u"arquivo %s (%d bytes)" % (name, info.file_size))
        return download_name(name), info.file_size, self._file_chunks(z, info)

    @staticmethod
    def _file_chunks(z, info):
        try:
            with z.open(info) as member:
                while True:
                    part = member.read(SEND_BYTES)
                    if not part:
                        return
                    yield part
        finally:
            z.close()


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from gluon import current
            import sss_logging
            factory = current.repo_factory
            _default = OutputBrowseService(tickets=factory.get("tickets"), catalog=factory.get("catalog"),
                                           audit=factory.get("audit"),
                                           log=sss_logging.get_logger("sss_web", current.sss_cfg))
        return _default


def environments(ctx):
    return _service().environments(ctx)


def scripts(ctx, environment):
    return _service().scripts(ctx, environment)


def days(ctx, environment, script_id):
    return _service().days(ctx, environment, script_id)


def tickets(ctx, environment, script_id, day, page=1):
    return _service().tickets(ctx, environment, script_id, day, page)


def files(ctx, ticket_id, page=1):
    return _service().files(ctx, ticket_id, page)


def zip_download(ctx, ip, ticket_id):
    return _service().zip_download(ctx, ip, ticket_id)


def file_download(ctx, ip, ticket_id, name):
    return _service().file_download(ctx, ip, ticket_id, name)
