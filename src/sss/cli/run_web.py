# -*- coding: utf-8 -*-
"""Inicia o servidor web do SSS (CR-021e), sem web2py.

Uso: python scripts/run_web.py [--config <config.ini>] [--host 127.0.0.1] [--port 8000] [--check]

So em 127.0.0.1 por padrao: os usuarios chegam pelo proxy reverso HTTPS ou por tunel (DEPLOYMENT
§10). SIGTERM e SIGINT so acionam a flag de parada; o servidor para de aceitar e espera as
requisicoes em andamento ate ``[web] socket_timeout_s``.

Com ``--check`` so confere configuracao, segredos e montagem da aplicacao, sem abrir a porta:
imprime ``CONFIG_OK sss_env=<ambiente>`` (usado pelo bin/start_local.sh e na implantacao).

Saida: 0 na parada normal ou no ``--check`` bem-sucedido; 2 configuracao ou segredos invalidos
(CRITICAL ja registrado); 3 endereco indisponivel (porta em uso ou sem permissao).
"""
import argparse
import sys
import threading
from typing import List, Optional

from sss.config import sss_config
from sss.platform import os_platform
from sss.web.app import bootstrap, security
from sss.web.framework import make_server, serve

EXIT_CONFIG = 2
EXIT_ADDRESS = 3


def main(argv: Optional[List[str]] = None) -> int:
    """Sobe o servidor e atende ate a parada; devolve o codigo de saida."""
    parser = argparse.ArgumentParser(description="Servidor web do SSS (CR-021e)")
    parser.add_argument("--config", default=None, help="config.ini do web (ou --name)")
    parser.add_argument("--name", default=None,
                        help="processo: instance/<nome>/config.ini (CR-028)")
    parser.add_argument("--host", default="127.0.0.1", help="endereco local (padrao: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="porta (padrao: 8000)")
    parser.add_argument("--check", action="store_true",
                        help="so confere configuracao e segredos, sem subir o servidor")
    args = parser.parse_args(argv)
    try:
        args.config = sss_config.config_path(args.config, args.name)
    except sss_config.ConfigError as exc:
        print("Configuracao invalida: %s" % exc, file=sys.stderr)
        return 2
    try:
        cfg = bootstrap.load_config(args.config)
        app = bootstrap.make_app(cfg)
    except sss_config.ConfigError:
        return EXIT_CONFIG
    if args.check:
        print(f"CONFIG_OK sss_env={cfg.app.sss_env}")
        return 0
    log = security.log()
    try:
        server = make_server(app, args.host, args.port, max_threads=cfg.web.max_threads,
                             socket_timeout_s=cfg.web.socket_timeout_s, log=log)
    except OSError as exc:
        log.critical("servidor web nao subiu em %s:%d: %s", args.host, args.port, exc,
                     extra={"action": "INICIO"})
        return EXIT_ADDRESS
    stop = threading.Event()
    os_platform.install_stop_handler(stop)
    log.info("servidor web no ar em %s:%d (max_threads=%d socket_timeout_s=%d)", args.host,
             args.port, cfg.web.max_threads, cfg.web.socket_timeout_s, extra={"action": "INICIO"})
    if not serve(server, stop, grace_s=cfg.web.socket_timeout_s):
        log.warning("parada com requisicoes ainda em andamento apos %d s",
                    cfg.web.socket_timeout_s, extra={"action": "PARADA"})
    log.info("servidor web parado", extra={"action": "PARADA"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
