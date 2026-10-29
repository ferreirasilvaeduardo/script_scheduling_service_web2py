# -*- coding: utf-8 -*-
"""Leitura de multipart/form-data em fluxo (CR-021d1; o cgi nao existe no Python 3.13).

O corpo e lido em blocos, nunca alem do Content-Length (contado pelos bytes lidos, nao so pelo
cabecalho). Arquivo vai para um SpooledTemporaryFile; campo de texto fica em memoria ate
``max_field_bytes``. Corpo malformado ou truncado levanta HTTP 400; acima dos limites, HTTP 413. O
nome do arquivo e preservado como veio (a validacao do nome e do service, CR-020).
"""
import re
import tempfile
from typing import IO, BinaryIO, List, NamedTuple, Optional, Tuple, Union

from .errors import HTTP

CHUNK_BYTES = 65536

Limits = NamedTuple("Limits", [("max_body_bytes", int), ("max_parts", int),
                               ("max_header_bytes", int), ("max_field_bytes", int),
                               ("spool_memory_bytes", int), ("spool_dir", Optional[str])])

# spool_dir: pasta do temporario acima de spool_memory_bytes (None: a do sistema).
DEFAULT_LIMITS = Limits(max_body_bytes=1048576, max_parts=1000, max_header_bytes=8192,
                        max_field_bytes=1048576, spool_memory_bytes=1048576, spool_dir=None)

# RFC 2046 §5.1.1: 1 a 70 caracteres de bchars, sem espaco no fim.
_RE_BOUNDARY = re.compile(r"[0-9A-Za-z'()+_,\-./=:? ]{0,69}[0-9A-Za-z'()+_,\-./=:?]")
_RE_PARAM = re.compile(r';\s*([A-Za-z0-9_*-]+)\s*=\s*("(?:[^"\\]|\\.)*"|[^;]*)')


# Arquivo recebido: ``file`` posicionado no inicio, ``filename`` como o navegador mandou.
UploadedFile = NamedTuple("UploadedFile", [("name", str), ("filename", str),
                                           ("content_type", str), ("file", IO[bytes])])


Value = Union[str, UploadedFile]


def _bad(reason: str) -> HTTP:
    return HTTP(400, f"Pedido multipart invalido: {reason}.")


def _too_large(reason: str) -> HTTP:
    return HTTP(413, f"Pedido acima do limite: {reason}.")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return re.sub(r"\\(.)", r"\1", value[1:-1])
    return value


def header_params(value: str) -> Tuple[str, dict]:
    """Valor principal e parametros de um cabecalho.

    ``form-data; name="a"`` -> ``('form-data', {'name': 'a'})``.
    """
    main, _sep, rest = value.partition(";")
    params = {}
    for match in _RE_PARAM.finditer(";" + rest):
        params[match.group(1).lower()] = _unquote(match.group(2))
    return main.strip().lower(), params


def boundary_of(content_type: str) -> bytes:
    """Delimitador do Content-Type; ausente ou fora da RFC 2046 e pedido invalido."""
    kind, params = header_params(content_type or "")
    if kind != "multipart/form-data":
        raise _bad("tipo de conteudo")
    boundary = params.get("boundary", "")
    if not _RE_BOUNDARY.fullmatch(boundary):
        raise _bad("delimitador")
    return boundary.encode("ascii")


class _Scanner:
    """Busca de marcadores sobre o corpo em blocos.

    O marcador e achado mesmo quando cai entre dois blocos.
    """

    def __init__(self, stream: BinaryIO, length: int) -> None:
        self._stream = stream
        self._left = length
        self._buffer = b""

    def _fill(self) -> bool:
        """Le mais um bloco, nunca alem do Content-Length; EOF antes dele e corpo truncado."""
        if self._left <= 0:
            return False
        data = self._stream.read(min(CHUNK_BYTES, self._left))
        if not data:
            raise _bad("corpo truncado")
        self._left -= len(data)
        self._buffer += data
        return True

    def until(self, marker: bytes, limit: int) -> bytes:
        """Tudo ate ``marker``, que e consumido.

        Mais que ``limit`` bytes antes dele e pedido invalido (400).
        """
        while True:
            index = self._buffer.find(marker)
            # O limite vale tambem quando o marcador ja chegou no mesmo bloco que o trecho.
            if index > limit or (index < 0 and len(self._buffer) > limit + len(marker)):
                raise _bad("trecho longo demais")
            if index >= 0:
                head, self._buffer = self._buffer[:index], self._buffer[index + len(marker):]
                return head
            if not self._fill():
                raise _bad("corpo truncado")

    def stream_until(self, marker: bytes, sink: "_Sink") -> None:
        """Copia para ``sink`` tudo ate ``marker``, sem guardar mais que um bloco em memoria."""
        while True:
            index = self._buffer.find(marker)
            if index >= 0:
                sink.write(self._buffer[:index])
                self._buffer = self._buffer[index + len(marker):]
                return
            # Guarda o fim do buffer: o marcador pode estar comecando nele.
            keep = len(marker) - 1
            if len(self._buffer) > keep:
                sink.write(self._buffer[:len(self._buffer) - keep])
                self._buffer = self._buffer[len(self._buffer) - keep:]
            if not self._fill():
                raise _bad("corpo truncado")

    def take(self, size: int) -> bytes:
        """Os proximos ``size`` bytes do corpo."""
        while len(self._buffer) < size:
            if not self._fill():
                raise _bad("corpo truncado")
        head, self._buffer = self._buffer[:size], self._buffer[size:]
        return head

    def drain(self) -> None:
        """Le o epilogo ate o fim do Content-Length (o cliente nao fica com corpo pendente)."""
        while self._fill():
            self._buffer = b""


class _Sink:  # pylint: disable=too-few-public-methods
    """Destino de uma parte: memoria limitada (campo) ou arquivo temporario (upload)."""

    def __init__(self, limit: Optional[int], spool_bytes: int,
                 spool_dir: Optional[str] = None) -> None:
        self._limit = limit
        self.size = 0
        self.memory = bytearray() if limit is not None else None
        # Sem with de proposito: o arquivo passa ao UploadedFile e e fechado pelo Request.close().
        self.file = None
        if limit is None:
            self.file = tempfile.SpooledTemporaryFile(  # pylint: disable=R1732
                max_size=spool_bytes, dir=spool_dir)

    def write(self, data: bytes) -> None:
        """Acrescenta ``data``; campo de texto acima do limite e 413."""
        if not data:
            return
        self.size += len(data)
        if self.memory is not None:
            if self._limit is not None and self.size > self._limit:
                raise _too_large("campo de texto")
            self.memory.extend(data)
        else:
            self.file.write(data)


def _part_headers(raw: bytes) -> dict:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _bad("cabecalho da parte com UTF-8 invalido") from exc
    headers = {}
    for line in text.split("\r\n"):
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep or not name.strip():
            raise _bad("cabecalho da parte")
        headers[name.strip().lower()] = value.strip()
    return headers


def parse(stream: BinaryIO, content_type: str, content_length: int,
          limits: Limits = DEFAULT_LIMITS) -> List[Tuple[str, Value]]:
    """Campos e arquivos do corpo multipart, na ordem em que vieram."""
    if content_length > limits.max_body_bytes:
        raise _too_large("corpo")
    delimiter = b"--" + boundary_of(content_type)
    scanner = _Scanner(stream, content_length)
    scanner.until(delimiter, limits.max_header_bytes)
    fields: List[Tuple[str, Value]] = []
    while True:
        ending = scanner.take(2)
        if ending == b"--":
            scanner.drain()
            return fields
        if ending != b"\r\n":
            raise _bad("delimitador sem fim de linha")
        if len(fields) >= limits.max_parts:
            raise _too_large("partes demais")
        headers = _part_headers(scanner.until(b"\r\n\r\n", limits.max_header_bytes))
        kind, params = header_params(headers.get("content-disposition", ""))
        name = params.get("name")
        if kind != "form-data" or not name:
            raise _bad("parte sem nome")
        is_file = "filename" in params
        sink = _Sink(None if is_file else limits.max_field_bytes, limits.spool_memory_bytes,
                     limits.spool_dir)
        scanner.stream_until(b"\r\n" + delimiter, sink)
        if is_file:
            sink.file.seek(0)
            content_type = headers.get("content-type", "application/octet-stream")
            fields.append((name, UploadedFile(name, params["filename"], content_type, sink.file)))
        else:
            try:
                fields.append((name, bytes(sink.memory).decode("utf-8")))
            except UnicodeDecodeError as exc:
                raise _bad("campo com UTF-8 invalido") from exc
