# -*- coding: utf-8 -*-
"""Camada de plataforma (README §8.0; CR-005: somente POSIX).

Toda primitiva dependente do sistema operacional fica aqui (AGENTS §3.2): o motor (executor, daemon,
startup check) chama apenas esta interface e nao conhece o SO. A implementacao e posix.py.
"""
import os

if os.name != "posix":
    raise ImportError("SSS: somente POSIX e suportado (CR-005)")

from sss.platform.os_platform.posix import (  # noqa: E402,F401
                                            NAME,
                                            TICKET_FILES,
                                            SYSTEM_DIRS,
                                            DEFAULT_RLIMITS,
                                            OUTPUT_TOO_MANY_FILES,
                                            OUTPUT_TOO_MANY_BYTES,
                                            OUTPUT_EMPTY,
                                            INPUT_EXISTS,
                                            INPUT_SPACE,
                                            INPUT_HASH,
                                            InstanceAlreadyRunning,
                                            Process,
                                            final_path,
                                            create_work_dir,
                                            create_input_dir,
                                            create_output_dir,
                                            create_script_work_dir,
                                            create_files_dirs,
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
                                            clean_output,
                                            locale_available,
                                            pick_child_locale,
                                            process_exists,
                                            reopen_group,
                                            signal_group,
                                            lock_instance,
                                            is_privileged_user,
                                            validate_restricted_file,
                                            validate_script_path,
                                            validate_restricted_dir,
                                            ensure_dir,
                                            )
