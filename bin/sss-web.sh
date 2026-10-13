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

# 4. Diretorio raiz do web2py
WEB2PY_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${WEB2PY_ROOT}"

PYTHON="${PYTHON:-python3}"

# 5. Executar processo web (README §3.1: web2py sob WSGI)
if [ "$#" -gt 0 ]; then
    case "$1" in
        -*)
            exec "${PYTHON}" anyserver.py "$@"
            ;;
        *)
            exec "$@"
            ;;
    esac
else
    exec "${PYTHON}" anyserver.py -s wsgiref -i 127.0.0.1 -p 8000
fi
