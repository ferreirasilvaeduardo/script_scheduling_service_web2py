#!/bin/bash
# Parada controlada do agente sem sinal (README §8.11, §12.2): cria work_dir/sss-<agent_id>.stop.
# Uso: sss-stop.sh <nome> | --config <config.ini>  (CR-028: instance/<nome>/config.ini; CR-029: sem padrao)
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Erro: execucao como root nao e permitida." >&2
    exit 1
fi
umask 077

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"
PYTHON="${PYTHON:-python3}"

if [ "$#" -eq 2 ] && [ "$1" = "--config" ] && [ -n "$2" ]; then
    CONFIG="$2"
elif [ "$#" -eq 1 ] && [[ "$1" =~ ^[a-z][a-z0-9_-]{0,29}$ ]]; then
    CONFIG="instance/$1/config.ini"
else
    # CR-029: sem config padrao; lista os processos de instance/ (menos os modelos de exemplos/).
    found="$(for f in instance/*/config.ini; do d="${f%/config.ini}"; d="${d#instance/}"
             if [ -f "${f}" ] && [ "${d}" != "exemplos" ]; then printf '%s ' "${d}"; fi; done)"
    echo "Erro: uso: sss-stop.sh <nome> | --config <config.ini> (em instance/: ${found:-nenhum})" >&2
    exit 2
fi

# Biblioteca padrao, sem importar a aplicacao: so o [app] name (mesmas regras do sss_config; CR-032, D4: agent_id e
# work_dir saem sempre do nome, e as linhas antigas [agent] agent_id/work_dir sao ignoradas, como no agente).
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
    # CR-032 (D4, 032e): o agent_id e o nome, e o work_dir e var/<nome>/works.
    nome = cp["app"].get("name", "").strip() if cp.has_section("app") else ""
    pasta = os.path.dirname(os.path.realpath(caminho))
    if (nome and os.path.dirname(pasta) == os.path.realpath(os.path.join(os.getcwd(), "instance"))
            and os.path.basename(pasta) != nome):
        # Revisao do CR-028 (A2): pasta copiada sem trocar o name pararia outro agente.
        sys.stderr.write("Erro: [app] name (%s) diferente da pasta instance/%s/\n" % (nome, os.path.basename(pasta)))
        sys.exit(2)
    if not cp.has_section("agent"):
        raise KeyError("agent")
    if not nome:
        raise KeyError("name")
    agente = nome
    work = os.path.join(os.getcwd(), "var", nome, "works")
except (OSError, KeyError, configparser.Error) as exc:
    sys.stderr.write("Erro: config.ini invalido (%s): %s\n" % (caminho, exc.__class__.__name__))
    sys.exit(2)
if not re.match(r"^(?!(?:init_db|seed|purge)$)[A-Za-z0-9._-]{1,30}$", agente):
    sys.stderr.write("Erro: [app] name invalido\n")
    sys.exit(2)
if not os.path.isabs(work) or not os.path.isdir(work):
    sys.stderr.write("Erro: %s nao existe (o agente nunca subiu com este nome?)\n" % work)
    sys.exit(2)
stop = os.path.join(work, "sss-%s.stop" % agente)
fd = os.open(stop, os.O_WRONLY | os.O_CREAT, 0o600)
os.close(fd)
sys.stdout.write("parada solicitada: %s\n" % stop)
PY
