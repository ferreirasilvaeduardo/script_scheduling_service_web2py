# -*- coding: utf-8 -*-
"""Configuracao do ambiente de execucao para testes unitarios.

Insere dinamicamente em sys.path a raiz da aplicacao (que e a raiz do repositorio desde o
CR-022a), src/ (pacote sss, inclusive as ferramentas de operacao em sss.cli desde o CR-022b8) e tools/,
calculadas a partir de __file__ (tests/support/, CR-022b1).
A raiz do repositorio nao entra por este modulo: o unittest a poe no caminho (``-t .``).
"""
import os
import sys

_support_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(os.path.dirname(_support_dir))
APP_DIR = _app_dir
# Camada web (CR-022b7): controllers, templates e estaticos ficam em src/sss/web/
WEB_DIR = os.path.join(_app_dir, "src", "sss", "web")
# Pacote da aplicacao (CR-022b3): imports qualificados (from sss.core import masking)
_src_dir = os.path.join(_app_dir, "src")
# Ferramentas de build (package.py, CR-022b2)
_tools_dir = os.path.join(_app_dir, "tools")

for _p in (_app_dir, _src_dir, _tools_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)
