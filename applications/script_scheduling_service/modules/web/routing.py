# -*- coding: utf-8 -*-
"""URLs da aplicacao e leitura do caminho da requisicao (CR-021d1, D4).

Formato mantido do web2py:
``/<aplicacao>/<controller>/<funcao>[.<extensao>]/<args...>?<vars>#<ancora>``. ``url`` gera
exatamente o que o ``gluon.html.URL`` gera para as formas usadas nas views (paridade conferida em
test_web_routing.py enquanto o gluon existe); ``parse_path`` faz o caminho inverso, recusando o que
nao e rota (travessia, funcao privada, caracteres de controle).

O caminho chega a ``parse_path`` JA DECODIFICADO: o servidor WSGI faz o unquote (o wsgiref, em
latin-1) e o app passa para UTF-8 (``decode_path_info``). Decodificar de novo aqui transformaria
``%252e%252e`` em ``..`` (dupla decodificacao, travessia).
"""
import re
import urllib.parse
from typing import (Any, Iterable, List, Mapping, NamedTuple, Optional, Tuple,
                    Union)

STATIC = "static"
DEFAULT_EXTENSION = "html"
EXTENSIONS = ("html", "json", "load")

_RE_NAME = re.compile(r"[a-z][a-z0-9_]*")
_RE_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

Route = NamedTuple("Route", [("controller", str), ("function", str), ("extension", str),
                             ("args", List[str])])
StaticRoute = NamedTuple("StaticRoute", [("path", str)])


class InvalidPath(ValueError):
    """Caminho que nao e uma rota da aplicacao (o app responde 404)."""


def _text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


def _query(variables: Mapping[str, Any]) -> str:
    """Como o web2py: chaves em ordem, lista vira chave repetida, demais valores por str()."""
    pairs: List[Tuple[str, str]] = []
    for key in sorted(variables):
        value = variables[key]
        if isinstance(value, (list, tuple)):
            pairs.extend((key, _text(item)) for item in value)
        else:
            pairs.append((key, _text(value)))
    return urllib.parse.urlencode(pairs)


# Espelha a assinatura do URL do web2py (CR-021e troca as chamadas sem reescreve-las).
def url(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        application: str, controller: str, function: str = "index",
        args: Union[Iterable[Any], Any, None] = None,
        variables: Optional[Mapping[str, Any]] = None,
        anchor: str = "", extension: Optional[str] = None) -> str:
    """URL de uma action, ou de um arquivo estatico quando ``controller`` e 'static'.

    ``extension`` e a da requisicao corrente ('html' ou None nao aparecem); o estatico nunca a
    recebe.
    """
    if controller == STATIC:
        return f"/{application}/{STATIC}/{function}"
    path = f"/{application}/{controller}/{function}"
    if extension and extension != DEFAULT_EXTENSION:
        path += "." + extension
    if args is not None:
        items = args if isinstance(args, (list, tuple)) else [args]
        for item in items:
            path += "/" + urllib.parse.quote(_text(item))
    if variables:
        path += "?" + _query(variables)
    if anchor:
        path += "#" + urllib.parse.quote(_text(anchor))
    return path


def _segment(value: str) -> str:
    """Um trecho do caminho, sem decodificar de novo; travessia e controle nao sao rota."""
    if value in ("", ".", "..") or "\\" in value or _RE_CONTROL.search(value):
        raise InvalidPath("trecho invalido no caminho")
    return value


def decode_path_info(path_info: str) -> str:
    """PATH_INFO do WSGI (bytes do URL em latin-1, PEP 3333) como texto UTF-8.

    UTF-8 invalido levanta InvalidPath.
    """
    try:
        return path_info.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError) as exc:
        raise InvalidPath("caminho com UTF-8 invalido") from exc


def parse_path(path: str, application: str) -> Union[Route, StaticRoute]:
    """Rota (controller, funcao, extensao, args) ou estatico a partir do PATH_INFO decodificado.

    Funcao que comeca com '_' nunca e rota (AGENTS §5.1). Levanta InvalidPath para todo o resto.
    """
    prefix = f"/{application}/"
    if not path.startswith(prefix) or "//" in path:
        raise InvalidPath("fora da aplicacao")
    parts = path[len(prefix):].split("/")
    if parts and parts[-1] == "":
        parts.pop()
    if not parts:
        raise InvalidPath("sem controller")
    if parts[0] == STATIC:
        return StaticRoute("/".join(_segment(item) for item in parts[1:]))
    controller = parts[0]
    function, _dot, extension = (parts[1] if len(parts) > 1 else "index").partition(".")
    extension = extension or DEFAULT_EXTENSION
    if not _RE_NAME.fullmatch(controller) or not _RE_NAME.fullmatch(function):
        raise InvalidPath("controller ou funcao fora do formato")
    if extension not in EXTENSIONS:
        raise InvalidPath("extensao desconhecida")
    return Route(controller, function, extension, [_segment(item) for item in parts[2:]])
