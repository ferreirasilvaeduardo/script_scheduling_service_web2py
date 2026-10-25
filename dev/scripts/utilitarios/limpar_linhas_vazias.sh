#!/bin/bash
# Utilitario SSS: Remove linhas vazias e espacos em branco excedentes.
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

if [ ! -f "$ORIGEM" ]; then
    echo "ERRO: Arquivo de origem nao encontrado: $ORIGEM" >&2
    exit 2
fi

DEST_DIR=$(dirname "$DESTINO")
mkdir -p "$DEST_DIR"

echo "Iniciando higienizacao de linhas vazias:"
echo "  Origem:  $ORIGEM"
echo "  Destino: $DESTINO"

TOTAL_ORIG=$(wc -l < "$ORIGEM")

# Remove espacos em branco no inicio e fim e filtra linhas nao vazias
sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' "$ORIGEM" | grep -v '^$' > "$DESTINO" || true

TOTAL_LIMPO=$(wc -l < "$DESTINO")
DESPERDICIO=$((TOTAL_ORIG - TOTAL_LIMPO))

echo "Higienizacao concluida com sucesso!"
echo "  Linhas originais:    $TOTAL_ORIG"
echo "  Linhas mantidas:     $TOTAL_LIMPO"
echo "  Linhas descartadas:  $DESPERDICIO"
exit 0
