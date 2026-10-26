# -*- coding: utf-8 -*-
"""Pastas do config.ini com dono e modo: involucro de sss.cli.prepare_dirs (CR-026e).

Uso, opcoes e codigos de saida no docstring de src/sss/cli/prepare_dirs.py.
"""
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, _SRC)

from sss.cli.prepare_dirs import main  # noqa: E402  # pylint: disable=wrong-import-position

if __name__ == "__main__":
    sys.exit(main())
