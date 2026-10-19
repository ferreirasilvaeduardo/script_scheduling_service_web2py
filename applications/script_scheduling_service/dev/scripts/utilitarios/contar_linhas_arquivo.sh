#!/bin/sh
# Utilitario SSS: Conta linhas, palavras e bytes de arquivo (modo SEQUENCIAL).
set -e

if [ $# -lt 1 ]; then
    echo "Uso: $0 <caminho_do_arquivo>" >&2
    exit 1
fi

ARQUIVO="$1"

if [ ! -f "$ARQUIVO" ]; then
    echo "ERRO: Arquivo nao encontrado: $ARQUIVO" >&2
    exit 2
fi

echo "Iniciando analise de metricas do arquivo:"
echo "  Arquivo: $ARQUIVO"

TOTAL_LINHAS=$(wc -l < "$ARQUIVO")
TOTAL_PALAVRAS=$(wc -w < "$ARQUIVO")
TOTAL_BYTES=$(wc -c < "$ARQUIVO")
LINHAS_NAO_VAZIAS=$(grep -c -v '^[[:space:]]*$' "$ARQUIVO" || true)

echo "Analise concluida com sucesso!"
echo "  Total de linhas:        $TOTAL_LINHAS"
echo "  Linhas preenchidas:     $LINHAS_NAO_VAZIAS"
echo "  Linhas vazias/espacos:  $((TOTAL_LINHAS - LINHAS_NAO_VAZIAS))"
echo "  Total de palavras:      $TOTAL_PALAVRAS"
echo "  Tamanho em bytes:       $TOTAL_BYTES"
exit 0
