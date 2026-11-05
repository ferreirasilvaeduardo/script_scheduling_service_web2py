#!/bin/sh
# Diagnostico SSS (CR-020a): grava arquivos na pasta de saida do ticket (SSS_OUTPUT_DIR) para a tela de Saidas.
set -e

if [ -z "${SSS_OUTPUT_DIR:-}" ]; then
    echo "ERRO: SSS_OUTPUT_DIR nao definida (agente sem [agent] output_dir)" >&2
    exit 1
fi

mkdir -p "$SSS_OUTPUT_DIR/detalhes"
{
    echo "ticket=${SSS_TICKET_ID}"
    echo "ambiente=${SSS_ENVIRONMENT}"
    echo "gerado_em=$(date '+%Y-%m-%d %H:%M:%S')"
} > "$SSS_OUTPUT_DIR/resumo.txt"
printf 'linha;valor\n1;10\n2;20\n' > "$SSS_OUTPUT_DIR/detalhes/relatório de testes.csv"
echo "Arquivos gerados na pasta de saida:"
ls -lR "$SSS_OUTPUT_DIR"
