# -*- coding: utf-8 -*-
"""Configuracao por processo (app_context, CR-021c) e contexto comum da requisicao. Nao abre conexao."""
import app_context
import sss_config

SSS_VERSION = "0.1.0"

app_context.set_config(sss_config.get_config("sss_web"))
# Sem UTF-8 no sistema de arquivos, nomes e valores com acento quebram (README §12.2, CR-007 R-17).
sss_config.check_encoding("sss_web", app_context.require_config().logging.log_dir)

response.sss_env = app_context.require_config().app.sss_env
response.sss_version = SSS_VERSION
response.sss_menu = []
