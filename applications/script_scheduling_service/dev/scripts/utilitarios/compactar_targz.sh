#!/bin/bash
# Utilitario SSS: Cria arquivo compactado .tar.gz a partir de origem.
set -e

ORIGEM=""
DESTINO=""

while [ $# -gt 0 ]; do
    case "$1" in
        --origem)
            ORIGEM="$2"
            shift 2
            ;;
        --destino)
            DESTINO="$2"
            shift 2
            ;;
        *)
            echo "Parametro desconhecido: $1" >&2
            exit 1
            ;;
    esac
done

if [ -z "$ORIGEM" ] || [ -z "$DESTINO" ]; then
    echo "ERRO: Parametros --origem e --destino sao obrigatorios." >&2
    exit 1
fi

if [ ! -e "$ORIGEM" ]; then
    echo "ERRO: Caminho de origem nao existe: $ORIGEM" >&2
    exit 2
fi

DEST_DIR=$(dirname "$DESTINO")
mkdir -p "$DEST_DIR"

echo "Iniciando compactacao TAR.GZ:"
echo "  Origem:  $ORIGEM"
echo "  Destino: $DESTINO"

BASE_DIR=$(dirname "$ORIGEM")
ITEM=$(basename "$ORIGEM")

tar -czf "$DESTINO" -C "$BASE_DIR" "$ITEM"

TAM_ORIG=$(du -sb "$ORIGEM" 2>/dev/null | cut -f1 || du -sk "$ORIGEM" | cut -f1)
TAM_DEST=$(du -sb "$DESTINO" 2>/dev/null | cut -f1 || du -sk "$DESTINO" | cut -f1)

echo "Compactacao TAR.GZ concluida com sucesso!"
echo "  Origem:  $TAM_ORIG bytes"
echo "  Destino: $TAM_DEST bytes"
exit 0
