#!/bin/bash
# Script de exemplo DEV (SSS): com --falhar sai com 3; caso contrario, 0. Nao remove nada.
for a in "$@"; do
    if [ "$a" = "--falhar" ]; then
        echo "limpeza: falha simulada"
        exit 3
    fi
done
echo "limpeza: nada a fazer (simulacao)"
exit 0
