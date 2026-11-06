#!/bin/bash
# Script de exemplo DEV (SSS): gera N linhas de saida (N = $1, padrao 10).
n="${1:-10}"
case "$n" in
    ''|*[!0-9]*) echo "N invalido" >&2; exit 2 ;;
esac
i=1
while [ "$i" -le "$n" ]; do
    echo "conciliacao linha $i de $n"
    i=$((i + 1))
done
exit 0
