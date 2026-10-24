# -*- coding: utf-8 -*-
"""Arquivos estaticos (CR-021d1b): so GET e HEAD, sempre dentro de static/.

Segunda linha de defesa depois do roteador: o caminho real (``realpath``, que resolve links)
precisa ficar dentro da pasta estatica real. Arquivo oculto (trecho que comeca com '.'), pasta e o
que nao for arquivo regular dao 404, sem listagem. Revalidacao por ETag e Last-Modified (304);
``Cache-Control: no-cache`` faz o navegador conferir a cada uso, porque o nome do arquivo nao muda
entre versoes.
"""
import email.utils
import mimetypes
import os
import stat
from typing import BinaryIO, Iterator, Mapping, Optional

from .errors import HTTP
from .response import Response

CHUNK_BYTES = 65536
# Tipos que o mimetypes do 3.6 nao conhece ou erra; o resto vem do mimetypes.
_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".map": "application/json",
    ".txt": "text/plain; charset=utf-8",
}


def content_type(path: str) -> str:
    """Content-Type pelo sufixo; desconhecido e application/octet-stream (com nosniff)."""
    suffix = os.path.splitext(path)[1].lower()
    if suffix in _TYPES:
        return _TYPES[suffix]
    guessed, _encoding = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def _resolve(root: str, relative: str) -> str:
    """Caminho real do arquivo dentro de ``root``; fora dele, oculto ou nao regular e 404."""
    parts = relative.split("/") if relative else []
    if not parts or any(not part or part.startswith(".") for part in parts):
        raise HTTP(404)
    real_root = os.path.realpath(root)
    real = os.path.realpath(os.path.join(real_root, *parts))
    if os.path.commonpath([real_root, real]) != real_root:
        raise HTTP(404)
    try:
        info = os.stat(real)
    except OSError as exc:
        raise HTTP(404) from exc
    if not stat.S_ISREG(info.st_mode):
        raise HTTP(404)
    return real


class FileChunks:
    """Corpo da resposta lido do arquivo em blocos.

    ``close()`` fecha o arquivo mesmo que a leitura nem tenha comecado (o servidor WSGI sempre
    chama close; o finally de um gerador que nunca iniciou nao rodaria).
    """

    def __init__(self, handle: BinaryIO) -> None:
        self._handle = handle

    def __iter__(self) -> Iterator[bytes]:
        """Blocos de ate CHUNK_BYTES ate o fim do arquivo."""
        while True:
            data = self._handle.read(CHUNK_BYTES)
            if not data:
                return
            yield data

    def close(self) -> None:
        """Fecha o arquivo (chamado pelo servidor WSGI no fim da resposta)."""
        self._handle.close()


def _not_modified(headers: Mapping[str, Optional[str]], etag: str, mtime: int) -> bool:
    """If-None-Match tem prioridade sobre If-Modified-Since (RFC 7232 §6)."""
    if_none_match = headers.get("if_none_match")
    if if_none_match:
        return etag in [item.strip() for item in if_none_match.split(",")] or if_none_match == "*"
    since = headers.get("if_modified_since")
    if since:
        try:
            parsed = email.utils.parsedate_to_datetime(since)
        except (TypeError, ValueError):
            return False
        return parsed is not None and int(parsed.timestamp()) >= mtime
    return False


def serve(root: str, relative: str, method: str,
          headers: Mapping[str, Optional[str]]) -> Response:
    """Resposta para ``relative`` dentro de ``root``.

    ``headers`` sao os do pedido no formato do env (``if_none_match``, ``if_modified_since``).
    """
    if method not in ("GET", "HEAD"):
        raise HTTP(405, "", Allow="GET, HEAD")
    path = _resolve(root, relative)
    info = os.stat(path)
    mtime = int(info.st_mtime)
    etag = f'"{info.st_size:x}-{info.st_mtime_ns:x}"'
    response = Response()
    response.headers.update({
        "ETag": etag,
        "Last-Modified": email.utils.formatdate(mtime, usegmt=True),
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
    })
    if _not_modified(headers, etag, mtime):
        response.status = 304
        response.body = b""
        return response
    response.headers["Content-Type"] = content_type(path)
    response.headers["Content-Length"] = str(info.st_size)
    # Sem with de proposito: o arquivo passa ao FileChunks, que o servidor fecha ao terminar.
    # pylint: disable-next=consider-using-with
    response.body = b"" if method == "HEAD" else FileChunks(open(path, "rb"))
    return response
