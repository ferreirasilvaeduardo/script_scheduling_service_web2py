# -*- coding: utf-8 -*-
"""Servidor web proprio com o backend FAKE, para o harness de navegador (somente DEV, CR-021e).

Uso: SSS_DEV_SEED_PASSWORD=<senha> python dev/others/web_harness/run_fake_web.py [--port 8791]

Usa o instance/config.ini do DEV (log, segredos e limites) e injeta o FAKE no repo_factory, como os
testes; o seed FAKE so existe com sss_env = DEV. Nunca vai no pacote de implantacao.
"""
import argparse
import os
import sys
from typing import List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(_APP_DIR, "src"))

from sss.persistence import repo_factory  # noqa: E402
from sss.cli import run_web  # noqa: E402


def main(argv: Optional[List[str]] = None) -> int:
    """Sobe o servidor com o FAKE; a senha do seed vem de SSS_DEV_SEED_PASSWORD."""
    parser = argparse.ArgumentParser(description="SSS com backend FAKE (harness, DEV)")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)
    if not os.environ.get(repo_factory.ENV_DEV_PASSWORD):
        sys.stderr.write("Defina %s (senha do seed FAKE).\n" % repo_factory.ENV_DEV_PASSWORD)
        return 2
    repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
    forwarded = ["--port", str(args.port)] + (["--config", args.config] if args.config else [])
    return run_web.main(forwarded)


if __name__ == "__main__":
    sys.exit(main())
