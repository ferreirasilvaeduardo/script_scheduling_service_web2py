# -*- coding: utf-8 -*-
"""Configuracao por processo e contexto comum da requisicao. Nao abre conexao."""
from gluon import current

import repo_factory
import sss_config

SSS_VERSAO = "0.1.0"

current.sss_cfg = sss_config.obter_config()
current.repo_factory = repo_factory

response.sss_env = current.sss_cfg.app.sss_env
response.sss_versao = SSS_VERSAO
response.sss_menu = []

# Antecipa a CSP do README §4.2; os demais cabecalhos de seguranca entram no F2.1 (models/10_security.py).
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; frame-ancestors 'none'"
)
