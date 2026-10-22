# -*- coding: utf-8 -*-
"""Configuracao por processo e contexto comum da requisicao. Nao abre conexao."""
from gluon import current

import repo_factory
import sss_config

SSS_VERSION = "0.1.0"

current.sss_cfg = sss_config.get_config("sss_web")
# Sem UTF-8 no sistema de arquivos, nomes e valores com acento quebram (README §12.2, CR-007 R-17).
sss_config.check_encoding("sss_web", current.sss_cfg.logging.log_dir)
current.repo_factory = repo_factory

response.sss_env = current.sss_cfg.app.sss_env
response.sss_version = SSS_VERSION
response.sss_menu = []
