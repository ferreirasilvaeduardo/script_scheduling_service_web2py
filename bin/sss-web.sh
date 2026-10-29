#!/bin/bash
# Launcher do no web do SSS (README §12.2): inicia somente o servidor web proprio (scripts/run_web.py).
set -euo pipefail

# 1. Recusar execucao como root
if [ "$(id -u)" -eq 0 ]; then
    echo "Erro: execucao como root nao e permitida." >&2
    exit 1
fi

# 2. Mascara de criacao restritiva
umask 077

# 3. Instant Client 19 (so quando nao estiver no ldconfig) e fuso (README §12.2)
_ic_no_ldconfig() {
    local cmd
    for cmd in ldconfig /sbin/ldconfig /usr/sbin/ldconfig; do
        if command -v "${cmd}" >/dev/null 2>&1; then
            "${cmd}" -p 2>/dev/null | grep 'libclntsh\.so' >/dev/null && return 0
            return 1
        fi
    done
    return 1
}
if [ -n "${SSS_IC_DIR:-}" ] && ! _ic_no_ldconfig; then
    export LD_LIBRARY_PATH="${SSS_IC_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
fi

if [ -n "${SSS_TZ:-}" ]; then
    export TZ="${SSS_TZ}"
fi

# Codificacao UTF-8 obrigatoria (README §12.2, CR-007 R-17): o processo aborta sem ela.
export LANG="${SSS_LOCALE:-C.UTF-8}"
export LC_ALL="${SSS_LOCALE:-C.UTF-8}"

# 4. Sempre a partir da raiz do repositorio (README §12.2)
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

PYTHON="${PYTHON:-python3}"
SERVER="scripts/run_web.py"

# 5. Executar SOMENTE o servidor web do SSS (README §12.2): nunca um comando arbitrario.
#    Formas aceitas (as opcoes sao as do run_web.py: --name, --config, --host, --port, --check):
#      sss-web.sh                         -> run_web.py sai com 2 e lista os processos (CR-029: sem config padrao)
#      sss-web.sh --opcoes...             -> run_web.py com as opcoes (padrao 127.0.0.1:8000)
#      sss-web.sh <python3[.x]> [--opcoes...]  -> o mesmo, com o interpretador escolhido
#      sss-web.sh [<python3[.x]>] <nome> [--opcoes...]  -> CR-028: --name <nome> (instance/<nome>/config.ini)
if [ "$#" -gt 0 ]; then
    case "$1" in
        -*) ;;
        *)
            case "$(basename "$1")" in
                python3|python3.[0-9]|python3.[0-9][0-9])
                    PYTHON="$1"
                    shift
                    ;;
                *)
                    if ! [[ "$1" =~ ^[a-z][a-z0-9_-]{0,29}$ ]]; then
                        echo "Erro: o primeiro argumento deve ser um interpretador python3, o nome do processo (ex.: web0001) ou uma opcao (recebido: $(basename "$1"))." >&2
                        exit 2
                    fi
                    ;;
            esac
            ;;
    esac
fi
# CR-028 (D7): o nome do processo vira --name (instance/<nome>/config.ini).
if [ "$#" -gt 0 ] && [[ "$1" =~ ^[a-z][a-z0-9_-]{0,29}$ ]]; then
    NAME="$1"
    shift
    set -- --name "${NAME}" "$@"
fi
for arg in "$@"; do
    case "${arg}" in
        *.py)
            echo "Erro: o launcher so inicia o ${SERVER}; ${arg} nao e aceito (CR-021e2)." >&2
            exit 2
            ;;
    esac
done
exec "${PYTHON}" "${SERVER}" "$@"
