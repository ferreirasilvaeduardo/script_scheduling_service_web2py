# -*- coding: utf-8 -*-
"""Configuracao do ambiente de execucao para testes unitarios.

Insere dinamicamente em sys.path a raiz da aplicacao
(applications/script_scheduling_service) e a raiz do web2py,
calculadas a partir de __file__.
Nao importa gluon.
"""
import os
import sys

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(_scripts_dir)
_modules_dir = os.path.join(_app_dir, "modules")
_web2py_root = os.path.dirname(os.path.dirname(_app_dir))

for _p in (_app_dir, _modules_dir, _web2py_root):
    if _p not in sys.path:
        sys.path.insert(0, _p)
