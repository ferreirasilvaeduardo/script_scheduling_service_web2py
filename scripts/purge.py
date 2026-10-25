# -*- coding: utf-8 -*-
"""Retencao de dados (cron do agente): involucro de sss.cli.purge (CR-022b8).

Comando de operacao inalterado; uso, opcoes e saida no docstring de src/sss/cli/purge.py.
"""
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, _SRC)

from sss.cli.purge import main  # noqa: E402  # pylint: disable=wrong-import-position

if __name__ == "__main__":
    sys.exit(main())
