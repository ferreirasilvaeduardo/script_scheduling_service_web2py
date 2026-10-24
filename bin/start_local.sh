#!/bin/bash
# ==============================================================================
# Script Scheduling Service (SSS) - Inicializador de Ambiente Local (DEV)
# ==============================================================================
# Inicia o servidor web do SSS (scripts/run_web.py, CR-021e2) em modo local (DEV) com o Oracle do [oracle] do config.ini
# (owner e table_prefix). O Python precisa ter o driver Oracle: PYTHON=<python> bin/...
#
# Uso:
#   bin/start_local.sh               # Inicia em segundo plano na porta 8000
#   bin/start_local.sh 18000         # Inicia na porta 18000
#   bin/start_local.sh -f            # Inicia em primeiro plano (Ctrl+C para sair)
#   PORT=8000 bin/start_local.sh     # Define porta por variavel de ambiente
# ==============================================================================
set -euo pipefail

# 1. Recusar execucao como root (README §12.2)
if [ "$(id -u)" -eq 0 ]; then
    echo "Erro: execucao como root nao e permitida." >&2
    exit 1
fi

# 2. Mascara restritiva
umask 077

# 3. Diretorio raiz do repositorio
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

APP_DIR="${REPO_ROOT}/applications/script_scheduling_service"
WORK_DIR="${APP_DIR}/work"
LOG_DIR="${APP_DIR}/logs"
PID_FILE="${WORK_DIR}/sss_web.pid"
DATE_TIME="$(date +%F_%H-%M-%S)"
LOG_FILE_DATED="${LOG_DIR}/server-${DATE_TIME}.log"
SERVER_OUT="${LOG_FILE:-${LOG_FILE_DATED}}"
SERVER_LINK="${LOG_DIR}/server.out"

mkdir -p -m 700 "${WORK_DIR}"
mkdir -p -m 750 "${LOG_DIR}"

# 4. Tratar argumentos (porta e modo foreground)
PORT="${PORT:-${SSS_PORT:-8000}}"
FOREGROUND=0

for arg in "$@"; do
    case "$arg" in
        -f|--foreground)
            FOREGROUND=1
            ;;
        -h|--help)
            echo "Uso: $0 [porta] [-f|--foreground]"
            echo "  porta         Porta TCP do servidor (padrao: 8000)"
            echo "  -f, --foreground  Executa no terminal (sem nohup/segundo plano)"
            exit 0
            ;;
        [0-9]*)
            PORT="$arg"
            ;;
        *)
            echo "Opcao desconhecida: $arg" >&2
            echo "Uso: $0 [porta] [-f|--foreground]" >&2
            exit 2
            ;;
    esac
done

# 5. Verificar se ja esta rodando
if [ -f "${PID_FILE}" ]; then
    OLD_PID="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [ -n "${OLD_PID}" ] && kill -0 "${OLD_PID}" 2>/dev/null; then
        if ps -p "${OLD_PID}" -o args= 2>/dev/null | grep -q "run_web.py"; then
            echo "O SSS ja esta rodando (PID: ${OLD_PID})."
            echo "URL: http://127.0.0.1:${PORT}/script_scheduling_service"
            exit 0
        fi
    fi
    rm -f "${PID_FILE}"
fi

# 6. Carregar segredos e variaveis de ambiente
if [ -f "${APP_DIR}/instance/web.env" ]; then
    set -a
    eval "$(tr -d '\r' < "${APP_DIR}/instance/web.env")"
    set +a
elif [ -f "${HOME}/.sss/web.env" ]; then
    set -a
    eval "$(tr -d '\r' < "${HOME}/.sss/web.env")"
    set +a
fi

export SSS_TZ="${SSS_TZ:-America/Sao_Paulo}"
export TZ="${SSS_TZ}"
export LANG="${SSS_LOCALE:-C.UTF-8}"
export LC_ALL="${SSS_LOCALE:-C.UTF-8}"

PYTHON="${PYTHON:-python3}"
if ! command -v "${PYTHON}" >/dev/null 2>&1; then
    echo "Erro: interpretador Python '${PYTHON}' nao encontrado no PATH." >&2
    exit 1
fi

# 7. Validacao rapida da configuracao (diagnostico antes de subir): run_web.py --check confere
#    config.ini e segredos sem abrir a porta; aqui ainda se exige DEV e o driver Oracle neste Python.
SERVER="${APP_DIR}/scripts/run_web.py"
DIAG_ERRORS="$("${PYTHON}" "${SERVER}" --check 2>&1 || true)"
if echo "${DIAG_ERRORS}" | grep -q "^CONFIG_OK"; then
    if ! echo "${DIAG_ERRORS}" | grep -q "^CONFIG_OK sss_env=DEV$"; then
        DIAG_ERRORS="ERRO: sss_env deve ser DEV para ambiente local."
    elif ! "${PYTHON}" -c "import oracledb" >/dev/null 2>&1 && ! "${PYTHON}" -c "import cx_Oracle" >/dev/null 2>&1; then
        # A aplicacao usa sempre o Oracle: o Python escolhido precisa ter oracledb ou cx_Oracle.
        DIAG_ERRORS="ERRO: driver Oracle (oracledb ou cx_Oracle) ausente neste Python; use PYTHON=<python com driver>"
    fi
else
    DIAG_ERRORS="ERRO: configuracao ou segredos invalidos (detalhes no log do SSS).
${DIAG_ERRORS}"
fi

if ! echo "${DIAG_ERRORS}" | grep -q "CONFIG_OK"; then
    echo "Erro ao validar configuracao do SSS:" >&2
    echo "${DIAG_ERRORS}" | grep -E "ERRO|ConfigErro|Traceback" >&2 || echo "${DIAG_ERRORS}" >&2
    exit 1
fi

# 8. Verificar se a porta pretendida esta livre
PORT_OCCUPIED="$("${PYTHON}" -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.settimeout(1.0)
    res = s.connect_ex(('127.0.0.1', int('${PORT}')))
    print(1 if res == 0 else 0)
finally:
    s.close()
" 2>/dev/null || echo 0)"

if [ "${PORT_OCCUPIED}" -eq 1 ]; then
    echo "Erro: A porta ${PORT} ja esta ocupada por outro processo." >&2
    exit 1
fi

# 9. Execucao
LAUNCHER="${REPO_ROOT}/bin/sss-web.sh"
if [ ! -x "${LAUNCHER}" ]; then
    chmod +x "${LAUNCHER}"
fi

if [ "${FOREGROUND}" -eq 1 ]; then
    echo "Iniciando SSS em primeiro plano na porta ${PORT}..."
    echo "Acesse: http://127.0.0.1:${PORT}/script_scheduling_service"
    echo "Pressione Ctrl+C para parar."
    exec "${LAUNCHER}" "${PYTHON}" --host 127.0.0.1 --port "${PORT}"
else
    echo "Iniciando SSS em segundo plano na porta ${PORT}..."
    echo "=== Servidor iniciado em $(date '+%Y-%m-%d %H:%M:%S') (Porta: ${PORT}) ===" >> "${SERVER_OUT}"
    nohup "${LAUNCHER}" "${PYTHON}" --host 127.0.0.1 --port "${PORT}" >> "${SERVER_OUT}" 2>&1 < /dev/null &
    SRV_PID=$!
    echo "${SRV_PID}" > "${PID_FILE}"
    chmod 600 "${PID_FILE}"
    ln -sf "$(basename "${SERVER_OUT}")" "${SERVER_LINK}"

    # 10. Aguarda subida e valida HTTP 200
    echo -n "Aguardando inicializacao do servico..."
    READY=0
    for i in $(seq 1 20); do
        if ! kill -0 "${SRV_PID}" 2>/dev/null; then
            echo
            echo "Erro: O servidor web do SSS parou logo apos a inicializacao." >&2
            echo "Ultimas mensagens do log (${SERVER_OUT}):" >&2
            tail -n 25 "${SERVER_OUT}" >&2
            rm -f "${PID_FILE}"
            exit 1
        fi

        HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PORT}/script_scheduling_service/default/login" 2>/dev/null || echo "000")"
        if [ "${HTTP_CODE}" = "200" ]; then
            READY=1
            break
        fi
        echo -n "."
        sleep 1
    done
    echo

    if [ "${READY}" -eq 1 ]; then
        echo "================================================================="
        echo " SSS iniciado com sucesso!"
        echo " PID:         ${SRV_PID}"
        echo " Porta:       ${PORT}"
        echo " URL:         http://127.0.0.1:${PORT}/script_scheduling_service"
        echo " Log c/ data: ${SERVER_OUT}"
        echo " Log atual:   ${SERVER_LINK}"
        echo " Para parar:  ${REPO_ROOT}/bin/stop_local.sh"
        echo "================================================================="
    else
        echo "Aviso: O processo esta rodando (PID: ${SRV_PID}), mas a pagina de login nao respondeu 200 dentro de 20s."
        echo "Verifique os logs em: ${SERVER_OUT}"
    fi
fi
