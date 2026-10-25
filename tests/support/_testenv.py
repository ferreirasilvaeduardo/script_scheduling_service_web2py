# -*- coding: utf-8 -*-
"""Configuracao do ambiente de execucao para testes unitarios.

Insere dinamicamente em sys.path a raiz da aplicacao (que e a raiz do repositorio desde o
CR-022a), modules/, scripts/ e tools/, calculadas a partir de __file__ (tests/support/, CR-022b1).
A raiz do repositorio nao entra por este modulo: o unittest a poe no caminho (``-t .``).
"""
import os
import sys

_support_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(os.path.dirname(_support_dir))
APP_DIR = _app_dir
_modules_dir = os.path.join(_app_dir, "modules")
# Ferramentas de operacao (health, purge, init_db...) importadas pelos testes ate o CR-022b8 (sss.cli)
_scripts_dir = os.path.join(_app_dir, "scripts")
# Ferramentas de build (package.py, CR-022b2)
_tools_dir = os.path.join(_app_dir, "tools")

for _p in (_app_dir, _modules_dir, _scripts_dir, _tools_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)
