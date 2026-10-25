# -*- coding: utf-8 -*-
"""Verificacao do ambiente e dos pre-requisitos: involucro de sss.cli.check_env (CR-022b8).

Comando de operacao inalterado; uso, opcoes e saida no docstring de src/sss/cli/check_env.py.
"""
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, _SRC)

from sss.cli.check_env import main  # noqa: E402  # pylint: disable=wrong-import-position

if __name__ == "__main__":
    sys.exit(main())
