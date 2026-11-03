#!/bin/bash
# Túnel fixo clone 7 -> 10.129.164.55 (Portas 18000 e 18001)
while true; do
    ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
        -L 127.0.0.1:18000:127.0.0.1:18000 \
        -L 127.0.0.1:18001:127.0.0.1:18001 \
        mastersafgf@10.129.164.55
    echo "$(date '+%F %T') túnel caiu (rc=$?); nova tentativa em 10 s"
    sleep 10
done