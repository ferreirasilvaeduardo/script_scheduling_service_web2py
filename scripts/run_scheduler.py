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
sys.path.insert(0, os.path.join(_BASE, "src"))

from sss.core import masking  # noqa: E402
import os_platform  # noqa: E402
import scheduler_loop  # noqa: E402
from sss.config import sss_config  # noqa: E402
from sss.config import sss_logging  # noqa: E402

_DAEMON_LOGGERS = ("sss_db_conn", "sss_config")


def _wait(stop_event):
    """A unica espera do daemon, entre iteracoes (no maximo 1 s, README §8.1); volta logo se a parada chegar."""
    def esperar(seconds):
        if seconds > 0 and not stop_event.is_set():
            time.sleep(seconds)
    return esperar


def main(argv=None):
    parser = argparse.ArgumentParser(description="Daemon do agente do SSS (README §8.1)")
    parser.add_argument("--config", dest="config", default=None, help="config.ini do agente (padrao: instance/)")
    args = parser.parse_args(argv)
    try:
        cfg = sss_config.get_config(log_name="sss_scheduler", path=args.config)
    except sss_config.ConfigError:  # o CRITICAL ja foi registrado (README §12.1)
        return scheduler_loop.EXIT_CONFIG
    logger = sss_logging.configure("sss_scheduler", cfg)
    for name in _DAEMON_LOGGERS:
        other = logging.getLogger(name)
        other.setLevel(logger.level)
        for handler in logger.handlers:
            other.addHandler(handler)
    masking.install_filter_on_handlers()
    stop = threading.Event()
    os_platform.install_stop_handler(stop)
    agent = scheduler_loop.Agent(cfg=cfg)
    try:
        agent.initialize()
        return agent.run(stop, wait=_wait(stop))
    except scheduler_loop.StartupFailure as failure:
        return failure.code
    finally:
        agent.release_resources()


if __name__ == "__main__":
    sys.exit(main())
