# -*- coding: utf-8 -*-
"""Sessao em cookie assinado (CR-021, D1; README §4.2).

Formato ``v1.<payload>.<assinatura>``: payload JSON em base64url (nunca objeto Python serializado)
e HMAC-SHA256 com uma chave derivada do ``cookie_key`` so para este fim. O conteudo pode ser LIDO
por quem tem o cookie, mas nao alterado: a revogacao continua pelo ``session_epoch`` (CR-008, E2).
Cookie invalido (assinatura, versao, tamanho, base64 ou JSON) vira sessao vazia, e o motivo volta
para o app registrar.
"""
import base64
import binascii
import hashlib
import hmac
import json
from typing import Any, Mapping, Optional, Tuple

from .storage import Storage

COOKIE_NAME = "sss_session"
VERSION = "v1"
MAX_COOKIE_BYTES = 4096
MIN_KEY_CHARS = 16
_KEY_PURPOSE = b"sss-session-cookie-v1"


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Session(Storage):
    """Conteudo da sessao.

    ``renew(clear_session=True)`` limpa, como no web2py com sessao em cookie.
    """

    __slots__ = ()

    def renew(self, clear_session: bool = False) -> None:
        """Em sessao por cookie nao ha id a trocar: o cookie sai regravado.

        Com ``clear_session``, sai vazio.
        """
        if clear_session:
            self.clear()


class _Refused(Exception):
    """Cookie recusado; ``args[0]`` e o motivo registrado pelo app."""


class SessionCodec:
    """Assina e confere o cookie de sessao com a chave derivada do ``cookie_key``."""

    def __init__(self, cookie_key: str) -> None:
        if not isinstance(cookie_key, str) or len(cookie_key) < MIN_KEY_CHARS:
            raise ValueError("cookie_key ausente ou curto demais")
        # Separacao de dominio: a chave do cookie nunca e o cookie_key cru.
        self._key = hmac.new(cookie_key.encode("utf-8"), _KEY_PURPOSE, hashlib.sha256).digest()

    def _signature(self, payload: str) -> str:
        message = f"{VERSION}.{payload}".encode("ascii")
        return _b64encode(hmac.new(self._key, message, hashlib.sha256).digest())

    def dumps(self, data: Mapping[str, Any]) -> str:
        """Valor do cookie para ``data``.

        Acima de MAX_COOKIE_BYTES e erro de programacao (ValueError), nunca um cookie cortado.
        """
        text = json.dumps(dict(data), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        payload = _b64encode(text.encode("ascii"))
        value = f"{VERSION}.{payload}.{self._signature(payload)}"
        if len(value) > MAX_COOKIE_BYTES:
            raise ValueError(f"sessao maior que {MAX_COOKIE_BYTES} bytes")
        return value

    def _verified(self, value: str) -> dict:
        """Conteudo do cookie conferido; levanta _Refused com o motivo."""
        if len(value) > MAX_COOKIE_BYTES:
            raise _Refused("tamanho")
        parts = value.split(".")
        if len(parts) != 3 or parts[0] != VERSION:
            raise _Refused("versao")
        _version, payload, signature = parts
        if not hmac.compare_digest(signature.encode("ascii", "replace"),
                                   self._signature(payload).encode("ascii")):
            raise _Refused("assinatura")
        try:
            data = json.loads(_b64decode(payload).decode("ascii"))
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            raise _Refused("conteudo") from exc
        if not isinstance(data, dict):
            raise _Refused("conteudo")
        return data

    def loads(self, value: Optional[str]) -> Tuple[Session, Optional[str]]:
        """(sessao, motivo da recusa). Sem cookie: sessao vazia e motivo None."""
        if not value:
            return Session(), None
        try:
            return Session(self._verified(value)), None
        except _Refused as refused:
            return Session(), refused.args[0]


def connect(cookie_value: Optional[str], codec: SessionCodec,
            response: Storage) -> Tuple[Session, Optional[str], str]:
    """Abre a sessao da requisicao: (sessao, motivo da recusa, retrato serializado do inicio).

    Como o session.connect do web2py, move o ``session.flash`` para o ``response.flash``. O retrato
    permite ao app regravar o cookie so quando a sessao mudou.
    """
    session, reason = codec.loads(cookie_value)
    if session.flash:
        response.flash, session.flash = session.flash, None
        del session.flash
    return session, reason, codec.dumps(session)
