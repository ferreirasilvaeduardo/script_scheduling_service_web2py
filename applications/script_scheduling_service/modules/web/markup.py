# -*- coding: utf-8 -*-
"""Escape da saida das views e o unico jeito de marcar HTML confiavel (CR-021d2).

``escape`` segue o ``{{=x}}`` do web2py: None vira texto vazio e o resto passa por ``str()`` e
``html.escape(quote=True)``. So um ``Markup`` (ou objeto com ``__html__``) sai sem escape; o
``.xml()`` generico do web2py NAO e aceito, para nenhum objeto entrar cru no HTML por acaso (AGENTS
§3.4).
"""
import html
from typing import Any


class Markup(str):
    """Texto HTML ja seguro, montado pelo codigo (nunca a partir de dado sem escape)."""

    __slots__ = ()

    def __html__(self) -> str:
        """Protocolo de HTML confiavel: o proprio texto."""
        return str(self)


def escape(value: Any) -> str:
    """Texto pronto para ir ao HTML, como o ``{{=x}}`` do web2py."""
    if value is None:
        return ""
    trusted = getattr(value, "__html__", None)
    if callable(trusted):
        return trusted()
    return html.escape(value if isinstance(value, str) else str(value), quote=True)
