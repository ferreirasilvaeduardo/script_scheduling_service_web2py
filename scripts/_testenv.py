# -*- coding: utf-8 -*-
"""Configuracao do ambiente de execucao para testes unitarios.

Insere dinamicamente em sys.path a raiz da aplicacao (que e a raiz do repositorio desde o
CR-022a) e modules/, calculadas a partir de __file__.
A raiz do repositorio nao entra: desde o CR-021f nao ha web2py nela.
"""
import os
import sys

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(_scripts_dir)
_modules_dir = os.path.join(_app_dir, "modules")

for _p in (_app_dir, _modules_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)
