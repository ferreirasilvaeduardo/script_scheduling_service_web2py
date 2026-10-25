#!/bin/bash
# Parada controlada do agente sem sinal (README §8.11, §12.2): cria work_dir/sss-<agent_id>.stop.
# Uso: sss-stop.sh [--config <config.ini>]  (padrao: instance/config.ini da aplicacao)
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Erro: execucao como root nao e permitida." >&2
    exit 1
fi
umask 077

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"
PYTHON="${PYTHON:-python3}"

CONFIG="instance/config.ini"
if [ "$#" -eq 2 ] && [ "$1" = "--config" ] && [ -n "$2" ]; then
    CONFIG="$2"
elif [ "$#" -ne 0 ]; then
    echo "Erro: uso: sss-stop.sh [--config <config.ini>]" >&2
    exit 2
fi

# Biblioteca padrao, sem importar a aplicacao: so [agent] agent_id e work_dir (mesmas regras do sss_config).
exec "${PYTHON}" -I - "${CONFIG}" <<'PY'
import configparser
import os
import re
import sys

caminho = sys.argv[1]
cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
try:
    with open(caminho, encoding="utf-8") as f:
        cp.read_file(f)
    agente = cp["agent"]["agent_id"].strip()
    work = cp["agent"]["work_dir"].strip()
except (OSError, KeyError, configparser.Error) as exc:
    sys.stderr.write("Erro: config.ini invalido (%s): %s\n" % (caminho, exc.__class__.__name__))
    sys.exit(2)
if not re.match(r"^(?!(?:init_db|seed|purge)$)[A-Za-z0-9._-]{1,30}$", agente):
    sys.stderr.write("Erro: [agent] agent_id invalido\n")
    sys.exit(2)
if not os.path.isabs(work) or not os.path.isdir(work):
    sys.stderr.write("Erro: [agent] work_dir deve ser um diretorio absoluto existente\n")
    sys.exit(2)
stop = os.path.join(work, "sss-%s.stop" % agente)
fd = os.open(stop, os.O_WRONLY | os.O_CREAT, 0o600)
os.close(fd)
sys.stdout.write("parada solicitada: %s\n" % stop)
PY
