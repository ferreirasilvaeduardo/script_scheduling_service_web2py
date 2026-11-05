#!/bin/sh
# Diagnostico SSS (CR-019): confere a pasta de trabalho do ticket (SSS_WORK_DIR) e grava nela.
set -e

if [ -z "${SSS_WORK_DIR:-}" ]; then
    echo "ERRO: SSS_WORK_DIR nao definida (agente sem [agent] script_work_dir)" >&2
    exit 1
fi
if [ ! -d "$SSS_WORK_DIR" ]; then
    echo "ERRO: SSS_WORK_DIR nao existe: $SSS_WORK_DIR" >&2
    exit 2
fi

echo "Pasta de trabalho: $SSS_WORK_DIR"
echo "HOME: $HOME"
echo "Pasta corrente: $(pwd)"
{
    echo "ticket=${SSS_TICKET_ID}"
    echo "ambiente=${SSS_ENVIRONMENT}"
    echo "script=${SSS_SCRIPT_NAME}"
    echo "gravado_em=$(date '+%Y-%m-%d %H:%M:%S')"
} > "$SSS_WORK_DIR/diagnostico.txt"
mkdir -p "$SSS_WORK_DIR/sub"
echo "conteudo de teste" > "$SSS_WORK_DIR/sub/arquivo.txt"
echo "Arquivos gravados na pasta de trabalho:"
ls -lR "$SSS_WORK_DIR"
