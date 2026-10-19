# -*- coding: utf-8 -*-
"""Camada de plataforma para primitivas dependentes de sistema operacional."""
import sys


def eh_macos():
    # type: () -> bool
    """Indica se a plataforma atual eh macOS (Darwin)."""
    return sys.platform == "darwin"


def obter_lib_dir_oracle(cfg):
    """Retorna lib_dir do Instant Client apenas se estiver no macOS (dev) com config definido."""
    if eh_macos() and cfg is not None and hasattr(cfg, "oracle") and cfg.oracle.oracle_client_lib_dir:
        return cfg.oracle.oracle_client_lib_dir
    return None
