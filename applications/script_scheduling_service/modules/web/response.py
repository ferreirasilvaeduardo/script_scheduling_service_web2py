# -*- coding: utf-8 -*-
"""Resposta da requisicao (CR-021d1).

Atributos livres como no web2py (``response.title``, ``response.flash``, ``response.sss_*``),
mais ``status``, ``headers``, cookies e ``json()``. O JSON sai seguro para HTML: '&', '<' e '>'
viram \\u0026, \\u003c e \\u003e (como o JSONEncoderForHTML do web2py). Cabecalho com quebra
de linha e recusado (injecao de cabecalho).
"""
import datetime
import decimal
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .storage import Storage

_RE_COOKIE_NAME = re.compile(r"[A-Za-z0-9_.-]+")
_RE_COOKIE_VALUE = re.compile(r"[A-Za-z0-9!#$%&'()*+\-./:<=>?@\[\]^_`{|}~]*")
SAME_SITE = ("Lax", "Strict")


def _json_default(value: Any) -> Any:
    """Tipos que o json nao conhece, no formato do web2py (datas sem o 'T' e sem fracao)."""
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()[:19].replace("T", " ")
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8")
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError(f"{value!r} nao e serializavel em JSON")


def json_for_html(data: Any) -> str:
    """JSON que pode ir dentro de HTML sem abrir tag nem entidade."""
    text = json.dumps(data, default=_json_default)
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def _check_header(name: str, value: str) -> None:
    if not name or any(ch in name + value for ch in "\r\n\x00"):
        raise ValueError(f"cabecalho invalido: {name!r}")


# Atributos do cookie da RFC 6265, so por nome (nunca trocados por posicao).
def cookie_header(  # pylint: disable=too-many-arguments
        name: str, value: str, *, path: str, secure: bool, same_site: str = "Lax",
        max_age: Optional[int] = None) -> str:
    """Valor de um Set-Cookie, sempre HttpOnly (o JavaScript nunca le cookie do SSS).

    SameSite e escrito aqui: o http.cookies do 3.6 nao o aceita. Atributos so por nome, para nunca
    trocar ``secure`` por outro sem perceber.
    """
    if not _RE_COOKIE_NAME.fullmatch(name) or not _RE_COOKIE_VALUE.fullmatch(value):
        raise ValueError("nome ou valor de cookie fora do formato")
    if same_site not in SAME_SITE:
        raise ValueError(f"SameSite invalido: {same_site!r}")
    parts = [f"{name}={value}", f"Path={path}", f"SameSite={same_site}"]
    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    parts.append("HttpOnly")
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


class Response(Storage):
    """Resposta corrente: atributos livres mais status, cabecalhos, cookies e corpo."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__()
        self.status = 200
        self.headers: Dict[str, str] = {}
        self.cookies: Dict[str, str] = {}

    def json(self, data: Any) -> str:
        """Serializa ``data`` e marca o Content-Type (se a action ainda nao o marcou)."""
        self.headers.setdefault("Content-Type", "application/json")
        return json_for_html(data)

    def set_cookie(self, name: str, value: str, *,  # pylint: disable=too-many-arguments
                   path: str, secure: bool,
                   same_site: str = "Lax", max_age: Optional[int] = None) -> None:
        """Grava (ou troca) o cookie ``name`` nesta resposta."""
        self.cookies[name] = cookie_header(name, value, path=path, secure=secure,
                                           same_site=same_site, max_age=max_age)

    def delete_cookie(self, name: str, *, path: str, secure: bool) -> None:
        """Pede ao navegador para apagar o cookie (valor vazio e Max-Age=0)."""
        self.set_cookie(name, "", path=path, secure=secure, max_age=0)

    def wsgi_headers(self) -> List[Tuple[str, str]]:
        """Cabecalhos para o start_response, com um Set-Cookie por cookie.

        Quebra de linha em nome ou valor e recusada (ValueError).
        """
        result: List[Tuple[str, str]] = []
        for name, value in self.headers.items():
            value = str(value)
            _check_header(name, value)
            result.append((name, value))
        for value in self.cookies.values():
            _check_header("Set-Cookie", value)
            result.append(("Set-Cookie", value))
        return result
