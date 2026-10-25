# -*- coding: utf-8 -*-
"""Interrupcao da requisicao com um status HTTP (CR-021d1): HTTP e redirect.

Mesma forma de uso do web2py (``raise HTTP(404)``, ``redirect(url)``), para os controllers mudarem
pouco no CR-021e. O corpo e sempre texto simples; a pagina de erro da aplicacao e montada pelo app.
"""
from typing import Dict, Optional

# Frases curtas do proprio status; a pagina de erro da aplicacao traz o texto ao usuario.
REASONS = {
    200: "OK",
    303: "See Other",
    304: "Not Modified",
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    413: "Payload Too Large",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


def status_line(status: int) -> str:
    """Linha de status do WSGI ('404 Not Found')."""
    return f"{status} {REASONS.get(status, 'Unknown')}"


class HTTP(Exception):
    """Interrompe a requisicao com ``status``, um corpo de texto e cabecalhos extras."""

    def __init__(self, status: int, body: str = "", **headers: str) -> None:
        super().__init__(status, body)
        if not 100 <= int(status) <= 599:
            raise ValueError(f"status HTTP fora da faixa: {status!r}")
        self.status = int(status)
        self.body = body or ""
        self.headers: Dict[str, str] = dict(headers)

    def __repr__(self) -> str:
        return f"HTTP({self.status})"


def redirect(location: str, how: int = 303, headers: Optional[Dict[str, str]] = None) -> None:
    """Interrompe a requisicao com um redirecionamento (303 por padrao: o proximo pedido e GET)."""
    if not location or "\r" in location or "\n" in location:
        raise ValueError("destino de redirecionamento invalido")
    extra = dict(headers or {})
    extra["Location"] = location
    raise HTTP(how, "", **extra)
