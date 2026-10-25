# -*- coding: utf-8 -*-
"""Dicionario com acesso por atributo (CR-021d1), com a semantica do Storage do web2py.

``request.vars.x``, ``session.flash`` e ``response.title`` leem None quando a chave nao existe, e
gravar o atributo grava a chave. Os controllers e as views usam essa forma desde o web2py.
"""
from typing import Any


class Storage(dict):
    """dict em que ``obj.chave`` le (None se ausente), grava e apaga a chave."""

    __slots__ = ()

    def __getattr__(self, key: str) -> Any:
        if key.startswith("__"):
            raise AttributeError(key)
        return self.get(key)

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    def __delattr__(self, key: str) -> None:
        self.pop(key, None)

    def __repr__(self) -> str:
        return f"<Storage {dict.__repr__(self)}>"
