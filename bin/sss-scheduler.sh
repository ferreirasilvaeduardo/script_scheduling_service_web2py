#!/bin/bash
# Launcher do daemon do agente (README §3.1, §12.2): somente scripts/run_scheduler.py [--config <config.ini>].
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

# 5. Somente a linha do daemon (README §3.1): sem argumentos ou --config <arquivo>; outro comando: codigo 2.
DAEMON="applications/script_scheduling_service/scripts/run_scheduler.py"
if [ "$#" -eq 0 ]; then
    exec "${PYTHON}" "${DAEMON}"
fi
if [ "$#" -eq 2 ] && [ "$1" = "--config" ] && [ -n "$2" ]; then
    exec "${PYTHON}" "${DAEMON}" --config "$2"
fi
echo "Erro: uso: sss-scheduler.sh [--config <config.ini>]" >&2
exit 2
