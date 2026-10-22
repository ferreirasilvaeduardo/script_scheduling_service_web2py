# -*- coding: utf-8 -*-
"""Inicia o daemon do agente (README §8.1, §8.12; F8.3).

Python puro, fora do web2py: o processo inteiro precisa ter uma unica thread antes do primeiro spawn (README §3.1,
C10). Uso: python scripts/run_scheduler.py [--config <config.ini>] (sem --config, instance/config.ini, como a
aplicacao; com ele, outro arquivo, por exemplo para dois agentes no mesmo servidor, README §12.2).

Saida: 0 na parada normal; 10 a 19 na falha de um passo da subida (README §8.12); 20 em REGISTRO_PERDIDO.
"""
import argparse
import logging
import os
import sys
import threading
import time

_BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_BASE, "modules"))

import masking  # noqa: E402
import os_platform  # noqa: E402
import scheduler_loop  # noqa: E402
import sss_config  # noqa: E402
import sss_logging  # noqa: E402

_DAEMON_LOGGERS = ("sss_db_conn", "sss_config")


def _wait(parada):
    """A unica espera do daemon, entre iteracoes (no maximo 1 s, README §8.1); volta logo se a parada chegar."""
    def esperar(segundos):
        if segundos > 0 and not parada.is_set():
            time.sleep(segundos)
    return esperar


def main(argv=None):
    parser = argparse.ArgumentParser(description="Daemon do agente do SSS (README §8.1)")
    parser.add_argument("--config", dest="config", default=None, help="config.ini do agente (padrao: instance/)")
    args = parser.parse_args(argv)
    try:
        cfg = sss_config.get_config(nome_log="sss_scheduler", caminho=args.config)
    except sss_config.ConfigError:  # o CRITICAL ja foi registrado (README §12.1)
        return scheduler_loop.EXIT_CONFIG
    logger = sss_logging.configure("sss_scheduler", cfg)
    for nome in _DAEMON_LOGGERS:
        outro = logging.getLogger(nome)
        outro.setLevel(logger.level)
        for handler in logger.handlers:
            outro.addHandler(handler)
    masking.install_filter_on_handlers()
    parada = threading.Event()
    os_platform.install_stop_handler(parada)
    agente = scheduler_loop.Agent(cfg=cfg)
    try:
        agente.initialize()
        return agente.run(parada, esperar=_wait(parada))
    except scheduler_loop.StartupFailure as falha:
        return falha.code
    finally:
        agente.release_resources()


if __name__ == "__main__":
    sys.exit(main())
