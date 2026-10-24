# -*- coding: utf-8 -*-
"""Requisicao corrente por thread (CR-021e, D3): ``request``, ``response``, ``session`` e ``URL``.

Os controllers importam estes nomes no lugar dos globais que o web2py injetava; cada thread do
servidor atende uma requisicao por vez, e o hook inicial do app (``bind``) aponta os objetos para a
dela. So ``webapp/`` e ``controllers/`` importam este modulo: ``modules/`` nunca le a requisicao
(AGENTS §5).
"""
import re
import threading
from typing import Any, Dict, Iterable, Mapping, Optional

from web import HTTP, Context, Markup, redirect, url

__all__ = ["APPLICATION", "HTTP", "URL", "bind", "redirect", "request", "response", "session",
           "set_user", "user"]

APPLICATION = "script_scheduling_service"
_LOCAL = threading.local()
# O que sustenta o Markup do URL: nomes e caminho estatico sem nada que precise de escape.
_RE_NAME = re.compile(r"[a-z][a-z0-9_]*")
_RE_STATIC = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*")


def bind(context: Context) -> None:
    """Aponta request, response e session desta thread para a requisicao de ``context``."""
    _LOCAL.context = context
    _LOCAL.user = None


def _current() -> Context:
    context = getattr(_LOCAL, "context", None)
    if context is None:
        raise RuntimeError("request/response/session usados fora de uma requisicao")
    return context


def user() -> Optional[Dict[str, Any]]:
    """Usuario da requisicao, revalidado pelo hook de seguranca (None sem sessao valida)."""
    return getattr(_LOCAL, "user", None)


def set_user(context: Optional[Dict[str, Any]]) -> None:
    """Grava o usuario revalidado da requisicao corrente (so o hook de seguranca)."""
    _LOCAL.user = context


class _Proxy:
    """Repassa leitura e escrita ao objeto ``name`` da requisicao corrente desta thread."""

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        object.__setattr__(self, "_name", name)

    def _target(self) -> Any:
        return getattr(_current(), object.__getattribute__(self, "_name"))

    def __getattr__(self, key: str) -> Any:
        return getattr(self._target(), key)

    def __setattr__(self, key: str, value: Any) -> None:
        setattr(self._target(), key, value)

    def __delattr__(self, key: str) -> None:
        delattr(self._target(), key)

    def __getitem__(self, key: Any) -> Any:
        return self._target()[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        self._target()[key] = value

    def __contains__(self, key: Any) -> bool:
        return key in self._target()

    def __repr__(self) -> str:
        return f"<proxy {object.__getattribute__(self, '_name')}>"


request: Any = _Proxy("request")
response: Any = _Proxy("response")
session: Any = _Proxy("session")


def URL(  # pylint: disable=invalid-name,too-many-arguments,too-many-positional-arguments
        a: Optional[str] = None, c: Optional[str] = None, f: Optional[str] = None,
        args: Optional[Iterable[Any]] = None,
        vars: Optional[Mapping[str, Any]] = None,  # pylint: disable=redefined-builtin
        anchor: str = "", extension: Any = None) -> Markup:
    """URL com a assinatura e as regras do web2py.

    Posicionais como no web2py: um so e a funcao; dois sao controller e funcao (``URL('static',
    'img/x.svg')`` e ``URL('dev', 'components')``); com tres, o primeiro e a aplicacao. Sem
    ``extension``, herda a da requisicao corrente; ``extension=False`` nunca poe extensao. Sem
    controller ou funcao, usa os da requisicao corrente.

    Devolve ``Markup``, como o SafeString do web2py (o '&' das variaveis sai cru no HTML): toda
    parte variavel ja sai codificada pelo quote/urlencode, e controller e funcao seguem
    [a-z][a-z0-9_]*.
    """
    if a and not c and not f:
        a, f = None, a
    elif a and c and not f:
        a, c, f = None, a, c
    if a not in (None, APPLICATION):
        raise ValueError(f"URL: aplicacao desconhecida {a!r}")
    current = getattr(_LOCAL, "context", None)
    controller = c or (current.request.controller if current is not None else "default")
    function = f or (current.request.function if current is not None else "index")
    if controller == "static":
        if not _RE_STATIC.fullmatch(function) or ".." in function:
            raise ValueError(f"URL: caminho estatico fora do formato: {function!r}")
        return Markup(url(APPLICATION, "static", function))
    if not _RE_NAME.fullmatch(controller) or not _RE_NAME.fullmatch(function):
        raise ValueError(f"URL: controller ou funcao fora do formato: {controller!r}/{function!r}")
    if extension is False:
        ext = None
    elif extension is None:
        ext = current.request.extension if current is not None else None
    else:
        ext = extension
    return Markup(url(APPLICATION, controller, function, args, vars, anchor, ext))
