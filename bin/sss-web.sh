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

# 5. Executar SOMENTE o processo Python do SSS (README §12.2): nunca um comando arbitrario.
#    Formas aceitas:
#      sss-web.sh                                   -> anyserver.py padrao
#      sss-web.sh -opcoes...                        -> anyserver.py com as opcoes
#      sss-web.sh <python3[.x]> web2py.py|anyserver.py [args...]
if [ "$#" -eq 0 ]; then
    exec "${PYTHON}" anyserver.py -s wsgiref -i 127.0.0.1 -p 8000
fi
case "$1" in
    -*)
        exec "${PYTHON}" anyserver.py "$@"
        ;;
esac
INTERPRETADOR="$1"
case "$(basename "${INTERPRETADOR}")" in
    python3|python3.[0-9]|python3.[0-9][0-9]) ;;
    *)
        echo "Erro: o primeiro argumento deve ser um interpretador python3 (recebido: $(basename "${INTERPRETADOR}"))." >&2
        exit 2
        ;;
esac
if [ "$#" -lt 2 ]; then
    echo "Erro: informe web2py.py ou anyserver.py depois do interpretador." >&2
    exit 2
fi
case "$2" in
    web2py.py|anyserver.py) ;;
    *)
        echo "Erro: so web2py.py ou anyserver.py podem ser iniciados pelo launcher." >&2
        exit 2
        ;;
esac
exec "$@"
