#!/bin/bash
set -euo pipefail

# 1. Recusar execucao como root
if [ "$(id -u)" -eq 0 ]; then
    echo "Erro: execucao como root nao e permitida." >&2
    exit 1
fi

# 2. Mascara de criacao restritiva
umask 077

# 3. Exportar bibliotecas Oracle Instant Client e Timezone
if [ -n "${SSS_IC_DIR:-}" ]; then
    export LD_LIBRARY_PATH="${SSS_IC_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
fi

if [ -n "${SSS_TZ:-}" ]; then
    export TZ="${SSS_TZ}"
fi

# Codificacao UTF-8 obrigatoria (README §12.2, CR-007 R-17): o processo aborta sem ela.
export LANG="${SSS_LOCALE:-C.UTF-8}"
export LC_ALL="${SSS_LOCALE:-C.UTF-8}"

# 4. Diretorio raiz do web2py
WEB2PY_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${WEB2PY_ROOT}"

PYTHON="${PYTHON:-python3}"

# 5. Executar daemon do scheduler (README §3.1)
exec "${PYTHON}" web2py.py -S script_scheduling_service -M -R applications/script_scheduling_service/scripts/run_scheduler.py "$@"
