# -*- coding: utf-8 -*-
"""Contexto do processo: a configuracao carregada (CR-021c, no lugar do gluon.current).

A configuracao e uma so por processo: o bootstrap da web (models/00_config.py) ou um teste a grava aqui,
e services, repositorios e controllers a leem daqui. O contexto da requisicao (usuario logado) nao mora
neste modulo. Nao importa gluon (AGENTS §5.2).
"""
from typing import Any


_config = None


def set_config(cfg):
    """Grava a configuracao do processo; None desfaz (usado por testes ao restaurar o estado)."""
    global _config
    _config = cfg


def get_config():
    """Configuracao do processo, ou None se ainda nao foi carregada."""
    return _config


def require_config() -> Any:
    """Configuracao do processo; sem ela, falha na hora (AGENTS §6, fail-fast)."""
    if _config is None:
        raise RuntimeError("Configuracao ausente: carregue-a com app_context.set_config (models/00_config.py)")
    return _config
