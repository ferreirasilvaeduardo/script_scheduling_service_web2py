#!/bin/bash
# ==============================================================================
# Script Scheduling Service (SSS) - Parada do Servico Web Local
# ==============================================================================
# Encerra graciosamente o processo web2py do SSS local.
#
# Uso:
#   bin/parar_servico.sh
# ==============================================================================
set -euo pipefail

# 1. Recusar execucao como root
if [ "$(id -u)" -eq 0 ]; then
    echo "Erro: execucao como root nao e permitida." >&2
    exit 1
fi

# 2. Diretorio raiz do web2py
WEB2PY_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${WEB2PY_ROOT}"

APP_DIR="${WEB2PY_ROOT}/applications/script_scheduling_service"
WORK_DIR="${APP_DIR}/work"
PID_FILE="${WORK_DIR}/sss_web.pid"

PID=""

# 3. Localizar o PID do servico
if [ -f "${PID_FILE}" ]; then
    CANDIDATE="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [ -n "${CANDIDATE}" ] && kill -0 "${CANDIDATE}" 2>/dev/null; then
        PID="${CANDIDATE}"
    else
        rm -f "${PID_FILE}"
    fi
fi

# Fallback: se nao encontrou no PID_FILE, procura processo web2py deste diretorio
if [ -z "${PID}" ]; then
    CANDIDATE="$(pgrep -f "web2py.py.*script_scheduling_service" || pgrep -f "${WEB2PY_ROOT}/web2py.py" || true)"
    if [ -n "${CANDIDATE}" ]; then
        PID="$(echo "${CANDIDATE}" | head -n 1)"
    fi
fi

if [ -z "${PID}" ]; then
    echo "O SSS nao esta rodando."
    rm -f "${PID_FILE}" "${WEB2PY_ROOT}/httpserver.pid"
    exit 0
fi

# 4. Validar se o processo realmente e o web2py antes de enviar sinal
CMD_LINE="$(ps -p "${PID}" -o args= 2>/dev/null || true)"
if ! echo "${CMD_LINE}" | grep -qE "web2py|anyserver"; then
    echo "Aviso: O processo PID ${PID} nao parece ser o web2py (comando: ${CMD_LINE})." >&2
    echo "Por seguranca, o processo nao sera encerrado automaticamente." >&2
    rm -f "${PID_FILE}"
    exit 1
fi

echo "Encerrando o SSS (PID: ${PID})..."

# 5. Encerramento gracioso com SIGINT (Rocket do web2py trata SIGINT)
kill -INT "${PID}" 2>/dev/null || true

PAROU=0
for i in $(seq 1 10); do
    if ! kill -0 "${PID}" 2>/dev/null; then
        PAROU=1
        break
    fi
    sleep 1
done

# 6. Escalar para SIGTERM se nao encerrou apos 10s
if [ "${PAROU}" -eq 0 ]; then
    echo "Processo nao encerrou com SIGINT. Enviando SIGTERM..."
    kill -TERM "${PID}" 2>/dev/null || true
    for i in $(seq 1 5); do
        if ! kill -0 "${PID}" 2>/dev/null; then
            PAROU=1
            break
        fi
        sleep 1
    done
fi

# 7. Escalar para SIGKILL se ainda estiver rodando
if [ "${PAROU}" -eq 0 ]; then
    echo "Processo nao respondeu a SIGTERM. Forcando encerramento (SIGKILL)..."
    kill -KILL "${PID}" 2>/dev/null || true
    sleep 1
fi

rm -f "${PID_FILE}" "${WEB2PY_ROOT}/httpserver.pid"

if ! kill -0 "${PID}" 2>/dev/null; then
    if [ -f "${APP_DIR}/logs/servidor.out" ]; then
        echo "=== Servidor parado em $(date '+%Y-%m-%d %H:%M:%S') (PID: ${PID}) ===" >> "${APP_DIR}/logs/servidor.out" 2>/dev/null || true
    fi
    echo "SSS parado com sucesso."
else
    echo "Erro: Nao foi possivel encerrar o processo ${PID}." >&2
    exit 1
fi
