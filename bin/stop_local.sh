#!/bin/bash
# ==============================================================================
# Script Scheduling Service (SSS) - Parada do Servico Web Local
# ==============================================================================
# Encerra graciosamente o servidor web do SSS local (scripts/run_web.py, CR-021e2).
#
# Uso:
#   bin/stop_local.sh
# ==============================================================================
set -euo pipefail

# 1. Recusar execucao como root
if [ "$(id -u)" -eq 0 ]; then
    echo "Erro: execucao como root nao e permitida." >&2
    exit 1
fi

# 2. Diretorio raiz do repositorio
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

APP_DIR="${REPO_ROOT}"
# CR-028: o web do DEV e o processo web0001 (var/web0001/); SSS_WEB_NAME troca o nome.
NAME="${SSS_WEB_NAME:-web0001}"
WORK_DIR="${APP_DIR}/var/${NAME}"
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

# Fallback: se nao encontrou no PID_FILE, procura o run_web.py deste repositorio, so entre processos
# python (o pgrep -f casaria tambem com o proprio shell que tem o padrao na linha de comando).
if [ -z "${PID}" ]; then
    for CANDIDATE in $(pgrep -f "script_scheduling_service/scripts/run_web.py" || true); do
        case "$(ps -o comm= -p "${CANDIDATE}" 2>/dev/null || true)" in
            python*)
                PID="${CANDIDATE}"
                break
                ;;
        esac
    done
fi

if [ -z "${PID}" ]; then
    echo "O SSS nao esta rodando."
    rm -f "${PID_FILE}"
    exit 0
fi

# 4. Validar se o processo realmente e o servidor web do SSS antes de enviar sinal
CMD_LINE="$(ps -p "${PID}" -o args= 2>/dev/null || true)"
if ! echo "${CMD_LINE}" | grep -q "run_web.py"; then
    echo "Aviso: O processo PID ${PID} nao parece ser o servidor web do SSS (comando: ${CMD_LINE})." >&2
    echo "Por seguranca, o processo nao sera encerrado automaticamente." >&2
    rm -f "${PID_FILE}"
    exit 1
fi

echo "Encerrando o SSS (PID: ${PID})..."

# 5. Encerramento gracioso com SIGTERM: o servidor para de aceitar conexoes e espera as requisicoes
#    em andamento ate [web] socket_timeout_s (padrao 30 s, maximo 300).
GRACE_S="${SSS_STOP_GRACE_S:-40}"
kill -TERM "${PID}" 2>/dev/null || true

STOPPED=0
for i in $(seq 1 "${GRACE_S}"); do
    if ! kill -0 "${PID}" 2>/dev/null; then
        STOPPED=1
        break
    fi
    sleep 1
done

# 6. Escalar para SIGKILL se ainda estiver rodando
if [ "${STOPPED}" -eq 0 ]; then
    echo "Processo nao encerrou em ${GRACE_S}s apos SIGTERM. Forcando encerramento (SIGKILL)..."
    kill -KILL "${PID}" 2>/dev/null || true
    sleep 1
fi

rm -f "${PID_FILE}"

if ! kill -0 "${PID}" 2>/dev/null; then
    if [ -f "${WORK_DIR}/logs/server.out" ]; then
        echo "=== Servidor parado em $(date '+%Y-%m-%d %H:%M:%S') (PID: ${PID}) ===" >> "${WORK_DIR}/logs/server.out" 2>/dev/null || true
    fi
    echo "SSS parado com sucesso."
else
    echo "Erro: Nao foi possivel encerrar o processo ${PID}." >&2
    exit 1
fi
