# -*- coding: utf-8 -*-
"""Camada de plataforma (README §8.0; CR-005: somente POSIX).

Toda primitiva dependente do sistema operacional fica aqui (AGENTS §3.2): o motor (executor, daemon,
startup check) chama apenas esta interface e nao conhece o SO. A implementacao e posix.py.
"""
import os
import sys

if os.name != "posix":
    raise ImportError("SSS: somente POSIX e suportado (CR-005)")

from os_platform.posix import (  # noqa: E402,F401
    NAME,
    HELPER,
    PACKAGE_HELPER,
    SYSTEM_DIRS,
    DEFAULT_RLIMITS,
    OUTPUT_TOO_MANY_FILES,
    OUTPUT_TOO_MANY_BYTES,
    OUTPUT_EMPTY,
    INPUT_EXISTS,
    INPUT_SPACE,
    INPUT_HASH,
    FailureAfterSpawn,
    InstanceAlreadyRunning,
    Process,
    final_path,
    create_work_dir,
    create_input_dir,
    create_output_dir,
    create_script_work_dir,
    stop_ticket,
    free_space_mb,
    write_state,
    group_alive,
    process_identity,
    start_pack,
    start_put_input,
    list_input,
    start_process,
    install_stop_handler,
    read_state,
    release_instance,
    clean_script_dir,
    clean_output,
    locale_available,
    process_exists,
    purge_output,
    reopen_group,
    signal_group,
    lock_instance,
    is_privileged_user,
    validate_restricted_file,
    validate_script_path,
    validate_restricted_dir,
    validate_execution,
    validate_interpreter_executable,
    validate_output_dirs,
)


def is_macos():
    # type: () -> bool
    """Indica se a plataforma atual eh macOS (Darwin)."""
    return sys.platform == "darwin"


def get_oracle_lib_dir(cfg):
    """Retorna lib_dir do Instant Client apenas se estiver no macOS (dev) com config definido."""
    if is_macos() and cfg is not None and hasattr(cfg, "oracle") and cfg.oracle.oracle_client_lib_dir:
        return cfg.oracle.oracle_client_lib_dir
    return None
