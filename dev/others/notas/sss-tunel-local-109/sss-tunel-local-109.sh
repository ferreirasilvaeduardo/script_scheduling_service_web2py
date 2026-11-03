#!/bin/bash
# Tunel da maquina local para a clone 7 (10.238.10.109)
# Permite acessar o SSS pelo navegador local em:
# DEV:  http://127.0.0.1:18000/script_scheduling_service/default/login
# PROD: http://127.0.0.1:18001/script_scheduling_service/default/login
# Este script cria um tunel SSH da maquina local para a clone 7, redirecionando as portas especificadas.
# Uso:
#   ./sss-tunel-local-109.sh start|stop|status
set -u

CLONE7=mastersafgf@10.238.10.109
PORTAS="18000 18001"
DIR=$HOME/.sss-tunel-local-109
PID_FILE=$DIR/tunel.pid
LOG=$DIR/tunel.log

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3
          -o ExitOnForwardFailure=yes)

_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

_loop() {
    local local_fwd=() p
    for p in $PORTAS; do
        local_fwd+=(-L "127.0.0.1:$p:127.0.0.1:$p")
    done

    while :; do
        echo "$(date '+%F %T') abrindo tunel local -> clone 7 ($PORTAS)"
        ssh -N "${SSH_OPTS[@]}" "${local_fwd[@]}" "$CLONE7"
        echo "$(date '+%F %T') conexao com clone 7 caiu (rc=$?); tentando em 10 s"
        sleep 10
    done
}

case "${1:-}" in
    start)
        if _running; then echo "ja ativo (pid $(cat "$PID_FILE"))"; exit 0; fi
        mkdir -m 0700 -p "$DIR"
        setsid nohup "$0" _loop >>"$LOG" 2>&1 < /dev/null &
        echo $! > "$PID_FILE"
        sleep 2
        "$0" status
        ;;
    stop)
        if ! _running; then echo "fora do ar"; rm -f "$PID_FILE"; exit 0; fi
        kill -TERM -- "-$(cat "$PID_FILE")" 2>/dev/null
        rm -f "$PID_FILE"
        echo "tunel parado"
        ;;
    status)
        if _running; then 
            echo "tunel ativo (pid $(cat "$PID_FILE")); log: $LOG"
        else 
            echo "fora do ar"
        fi
        for p in $PORTAS; do
            curl -s -o /dev/null -m 3 -w "porta $p: HTTP %{http_code}\n" \
                "http://127.0.0.1:$p/script_scheduling_service/default/login" || echo "porta $p: sem resposta"
        done
        ;;
    _loop)
        _loop
        ;;
    *)
        echo "uso: $0 start | stop | status" >&2
        exit 2
        ;;
esac