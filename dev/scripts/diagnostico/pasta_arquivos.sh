#!/bin/sh
# Diagnostico SSS (CR-037): le a pasta inputs da pasta de arquivos e grava na outputs.
set -e

for var in SSS_FILES_INPUTS_DIR SSS_FILES_OUTPUTS_DIR; do
    eval "dir=\${$var:-}"
    if [ -z "$dir" ] || [ ! -d "$dir" ]; then
        echo "ERRO: $var ausente ou inexistente: $dir" >&2
        exit 1
    fi
done

echo "inputs: $SSS_FILES_INPUTS_DIR"
echo "outputs: $SSS_FILES_OUTPUTS_DIR"
dest="$SSS_FILES_OUTPUTS_DIR/ticket_$SSS_TICKET_ID"
mkdir -p "$dest/copias"
n=0
for f in "$SSS_FILES_INPUTS_DIR"/*; do
    [ -f "$f" ] || continue
    cp "$f" "$dest/copias/"
    n=$((n + 1))
done
{
    echo "ticket=${SSS_TICKET_ID}"
    echo "arquivos_copiados=$n"
    echo "gravado_em=$(date '+%Y-%m-%d %H:%M:%S')"
} > "$dest/resumo.txt"
echo "arquivos copiados de inputs para outputs: $n"
