# -*- coding: utf-8 -*-
"""Camada de plataforma (README §8.0; CR-005: somente POSIX).

Toda primitiva dependente do sistema operacional fica aqui (AGENTS §3.2): o motor (executor, daemon,
startup check) chama apenas esta interface e nao conhece o SO. A implementacao e posix.py.
"""
import os
import sys

if os.name != "posix":
    raise ImportError("SSS: somente POSIX e suportado (CR-005)")

from plataforma.posix import (  # noqa: E402,F401
    NOME,
    HELPER,
    PASTAS_DO_SISTEMA,
    InstanciaJaEmExecucao,
    Processo,
    caminho_final,
    checar_cadeia,
    checar_item,
    criar_dir_trabalho,
    encerrar_ticket,
    espaco_livre_mb,
    gravar_estado,
    grupo_vivo,
    identidade_processo,
    iniciar_processo,
    instalar_parada,
    ler_estado,
    liberar_instancia,
    processo_existe,
    reabrir_grupo,
    sinalizar_grupo,
    travar_instancia,
    usuario_privilegiado,
    validar_arquivo_restrito,
    validar_caminho_script,
    validar_dir_restrito,
    validar_execucao,
    validar_interpretador_executavel,
)


def eh_macos():
    # type: () -> bool
    """Indica se a plataforma atual eh macOS (Darwin)."""
    return sys.platform == "darwin"


def obter_lib_dir_oracle(cfg):
    """Retorna lib_dir do Instant Client apenas se estiver no macOS (dev) com config definido."""
    if eh_macos() and cfg is not None and hasattr(cfg, "oracle") and cfg.oracle.oracle_client_lib_dir:
        return cfg.oracle.oracle_client_lib_dir
    return None
