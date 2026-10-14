#!/bin/sh
# Script de exemplo DEV (SSS): imprime os argumentos recebidos e sai com 0.
echo "script=$0"
i=0
for a in "$@"; do
    i=$((i + 1))
    echo "arg[$i]=$a"
done
exit 0
