#!/bin/bash
# Utilitario SSS: Filtra linhas de arquivo baseado em padrao de texto.
set -e

ORIGEM=""
DESTINO=""
PADRAO=""
INVERTER="N"

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
        --padrao)
            PADRAO="$2"
            shift 2
            ;;
        --inverter)
            INVERTER="$2"
            shift 2
            ;;
        *)
            echo "Parametro desconhecido: $1" >&2
            exit 1
            ;;
    esac
done

if [ -z "$ORIGEM" ] || [ -z "$DESTINO" ] || [ -z "$PADRAO" ]; then
    echo "ERRO: Parametros --origem, --destino e --padrao sao obrigatorios." >&2
    exit 1
fi

if [ ! -f "$ORIGEM" ]; then
    echo "ERRO: Arquivo de origem nao encontrado: $ORIGEM" >&2
    exit 2
fi

DEST_DIR=$(dirname "$DESTINO")
mkdir -p "$DEST_DIR"

echo "Iniciando filtragem de linhas:"
echo "  Origem:   $ORIGEM"
echo "  Destino:  $DESTINO"
echo "  Padrao:   $PADRAO"
echo "  Inverter: $INVERTER"

TOTAL_ORIG=$(wc -l < "$ORIGEM")

if [ "$INVERTER" = "S" ] || [ "$INVERTER" = "s" ]; then
    grep -v -- "$PADRAO" "$ORIGEM" > "$DESTINO" || true
else
    grep -- "$PADRAO" "$ORIGEM" > "$DESTINO" || true
fi

TOTAL_FILTRADO=$(wc -l < "$DESTINO")

echo "Filtragem concluida com sucesso!"
echo "  Linhas originais: $TOTAL_ORIG"
echo "  Linhas retidas:   $TOTAL_FILTRADO"
exit 0
