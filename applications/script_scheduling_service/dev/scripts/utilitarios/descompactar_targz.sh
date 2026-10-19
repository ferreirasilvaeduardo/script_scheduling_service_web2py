#!/bin/bash
# Utilitario SSS: Extrai arquivo compactado .tar.gz para pasta destino.
set -e

ARQ_TAR=""
DESTINO=""

while [ $# -gt 0 ]; do
    case "$1" in
        --arquivo-tar)
            ARQ_TAR="$2"
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

if [ -z "$ARQ_TAR" ] || [ -z "$DESTINO" ]; then
    echo "ERRO: Parametros --arquivo-tar e --destino sao obrigatorios." >&2
    exit 1
fi

if [ ! -f "$ARQ_TAR" ]; then
    echo "ERRO: Arquivo .tar.gz nao encontrado: $ARQ_TAR" >&2
    exit 2
fi

mkdir -p "$DESTINO"

echo "Iniciando descompactacao TAR.GZ:"
echo "  Arquivo: $ARQ_TAR"
echo "  Destino: $DESTINO"

# Teste de integridade do arquivo antes de extrair
tar -tzf "$ARQ_TAR" >/dev/null

# Extracao segura
tar -xzf "$ARQ_TAR" -C "$DESTINO"

QTD_ITENS=$(tar -tzf "$ARQ_TAR" | wc -l)
echo "Descompactacao concluida com sucesso!"
echo "  Itens extraidos: $QTD_ITENS"
exit 0
