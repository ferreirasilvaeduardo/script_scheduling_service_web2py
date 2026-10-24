# -*- coding: utf-8 -*-
"""Requisicao a partir do environ WSGI (CR-021d1).

Mesmos nomes que os controllers usam desde o web2py: ``env`` (chaves do environ em minusculas, com
'.' trocado por '_'), ``get_vars``, ``post_vars`` e ``vars`` (chave repetida vira lista; ``vars``
junta os dois como o web2py), ``args``, ``cookies`` e ``is_https``. O corpo so e lido quando
``post_vars`` e usado, nunca alem do Content-Length nem do limite: acima dele, HTTP 413 sem ler;
truncado ou malformado, 400. Corpo application/json com um objeto vai para ``post_vars``, como no
web2py (o fetch das previas manda assim); JSON invalido e 400 (o web2py o ignorava em silencio).
"""
import http.cookies
import json
import urllib.parse
from typing import Any, BinaryIO, Iterable, List, Mapping, Optional, Tuple

from . import multipart
from .errors import HTTP
from .routing import Route
from .storage import Storage

MAX_FIELDS = 10000
_BODY_METHODS = ("POST", "PUT", "PATCH", "DELETE")
_FORM_TYPE = "application/x-www-form-urlencoded"
_JSON_TYPE = "application/json"


def _bad(reason: str) -> HTTP:
    return HTTP(400, f"Pedido invalido: {reason}.")


def _environ_name(key: str) -> str:
    return key.lower().replace(".", "_")


def _collect(pairs: Iterable[Tuple[str, Any]]) -> Storage:
    """Chave unica fica com o valor; chave repetida vira lista, na ordem em que veio."""
    result = Storage()
    for key, value in pairs:
        if key in result:
            previous = result[key]
            if isinstance(previous, list):
                previous.append(value)
            else:
                result[key] = [previous, value]
        else:
            result[key] = value
    return result


def parse_query(text: str) -> Storage:
    """Pares de ``a=1&b=2``; UTF-8 invalido e 400.

    So '&' separa, igual em todas as versoes do Python (o ';' deixou de separar no 3.6.13).
    """
    pairs: List[Tuple[str, str]] = []
    for chunk in text.split("&") if text else []:
        if not chunk:
            continue
        if len(pairs) >= MAX_FIELDS:
            raise HTTP(413, "Pedido acima do limite: campos demais.")
        key, _sep, value = chunk.partition("=")
        try:
            pairs.append((urllib.parse.unquote_plus(key, errors="strict"),
                          urllib.parse.unquote_plus(value, errors="strict")))
        except UnicodeDecodeError as exc:
            raise _bad("UTF-8 invalido na consulta") from exc
    return _collect(pairs)


def _read_exactly(stream: BinaryIO, length: int) -> bytes:
    chunks = []
    left = length
    while left > 0:
        data = stream.read(min(multipart.CHUNK_BYTES, left))
        if not data:
            raise _bad("corpo truncado")
        chunks.append(data)
        left -= len(data)
    return b"".join(chunks)


class Request:  # pylint: disable=too-many-instance-attributes
    """Requisicao corrente; o corpo e lido sob demanda, no primeiro acesso a ``post_vars``."""

    def __init__(self, environ: Mapping[str, Any], route: Route, max_body_bytes: int,
                 limits: multipart.Limits = multipart.DEFAULT_LIMITS) -> None:
        self.environ = environ
        self.env = Storage((_environ_name(key), value) for key, value in environ.items())
        self.method = str(environ.get("REQUEST_METHOD") or "GET").upper()
        self.controller = route.controller
        self.function = route.function
        self.extension = route.extension
        self.args = list(route.args)
        self.max_body_bytes = max_body_bytes
        self._limits = limits._replace(max_body_bytes=max_body_bytes)
        self._get_vars: Optional[Storage] = None
        self._post_vars: Optional[Storage] = None
        self._vars: Optional[Storage] = None
        self._uploads: List[multipart.UploadedFile] = []
        self.body = b""
        self.cookies = self._parse_cookies(environ.get("HTTP_COOKIE") or "")

    @staticmethod
    def _parse_cookies(header: str) -> http.cookies.SimpleCookie:
        cookies = http.cookies.SimpleCookie()
        try:
            cookies.load(header)
        except http.cookies.CookieError:
            # Cabecalho malformado: segue sem cookies (sessao vazia), como um navegador sem sessao.
            return http.cookies.SimpleCookie()
        return cookies

    @property
    def is_https(self) -> bool:
        """Como no web2py: esquema do WSGI, HTTPS=on ou X-Forwarded-Proto do proxy."""
        return (self.env.wsgi_url_scheme == "https" or self.env.https == "on"
                or self.env.http_x_forwarded_proto == "https")

    def content_length(self) -> int:
        """Content-Length declarado; ausente e 0, invalido ou negativo e 400."""
        raw = self.environ.get("CONTENT_LENGTH") or "0"
        try:
            length = int(raw)
        except ValueError as exc:
            raise _bad("Content-Length") from exc
        if length < 0:
            raise _bad("Content-Length")
        return length

    @property
    def get_vars(self) -> Storage:
        """Variaveis da consulta (lidas uma vez, no primeiro acesso)."""
        if self._get_vars is None:
            self._get_vars = parse_query(str(self.environ.get("QUERY_STRING") or ""))
        return self._get_vars

    @property
    def post_vars(self) -> Storage:
        """Variaveis do corpo; o corpo so e lido aqui, no primeiro acesso, dentro dos limites."""
        if self._post_vars is None:
            self._post_vars = self._parse_body()
        return self._post_vars

    @property
    def vars(self) -> Storage:
        """GET e POST juntos, como o web2py: chave dos dois vira lista (GET primeiro)."""
        if self._vars is None:
            merged = Storage(self.get_vars)
            for key, value in self.post_vars.items():
                if key not in merged:
                    merged[key] = value
                    continue
                if not isinstance(merged[key], list):
                    merged[key] = [merged[key]]
                merged[key] = merged[key] + (value if isinstance(value, list) else [value])
            self._vars = merged
        return self._vars

    def _parse_body(self) -> Storage:
        if self.method not in _BODY_METHODS:
            return Storage()
        length = self.content_length()
        if length > self.max_body_bytes:
            raise HTTP(413, "Pedido acima do limite: corpo.")
        if length == 0:
            return Storage()
        stream = self.environ["wsgi.input"]
        content_type = str(self.environ.get("CONTENT_TYPE") or "")
        kind, _params = multipart.header_params(content_type)
        if kind == "multipart/form-data":
            fields = multipart.parse(stream, content_type, length, self._limits)
            self._uploads.extend(v for _k, v in fields if isinstance(v, multipart.UploadedFile))
            return _collect(fields)
        body = _read_exactly(stream, length)
        if kind == _JSON_TYPE:
            try:
                data = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise _bad("JSON invalido") from exc
            # Como no web2py: so um objeto JSON vira post_vars; lista ou valor solto fica de fora.
            return Storage(data) if isinstance(data, dict) else Storage()
        if kind != _FORM_TYPE:
            # Outro tipo de corpo fica em ``body``; post_vars vem vazio, como no web2py.
            self.body = body
            return Storage()
        try:
            text = body.decode("ascii")
        except UnicodeDecodeError as exc:
            raise _bad("corpo urlencoded fora de ASCII") from exc
        return parse_query(text)

    def close(self) -> None:
        """Fecha os arquivos temporarios dos uploads (fim da requisicao)."""
        for upload in self._uploads:
            upload.file.close()
        self._uploads = []
