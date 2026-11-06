#!/bin/sh
# Utilitario SSS: Ordena linhas de arquivo texto com opcoes configuraveis.
set -e

ORIGEM=""
DESTINO=""
NUMERICO="N"
REVERSO="N"

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
        --numerico)
            NUMERICO="$2"
            shift 2
            ;;
        --reverso)
            REVERSO="$2"
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

if [ ! -f "$ORIGEM" ]; then
    echo "ERRO: Arquivo de origem nao encontrado: $ORIGEM" >&2
    exit 2
fi

DEST_DIR=$(dirname "$DESTINO")
mkdir -p "$DEST_DIR"

SORT_FLAGS=""
if [ "$NUMERICO" = "S" ] || [ "$NUMERICO" = "s" ]; then
    SORT_FLAGS="$SORT_FLAGS -n"
fi
if [ "$REVERSO" = "S" ] || [ "$REVERSO" = "s" ]; then
    SORT_FLAGS="$SORT_FLAGS -r"
fi

echo "Iniciando ordenacao de arquivo:"
echo "  Origem:   $ORIGEM"
echo "  Destino:  $DESTINO"
echo "  Numerico: $NUMERICO"
echo "  Reverso:  $REVERSO"

# shellcheck disable=SC2086
sort $SORT_FLAGS "$ORIGEM" > "$DESTINO"

TOTAL_LINHAS=$(wc -l < "$DESTINO")

echo "Ordenacao concluida com sucesso!"
echo "  Linhas ordenadas: $TOTAL_LINHAS"
exit 0
