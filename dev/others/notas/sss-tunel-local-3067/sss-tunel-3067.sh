#!/bin/bash
# Tunel do navegador ate o web do SSS no 3067 (DEPLOYMENT-SERVER, passo 13), em segundo plano (nohup).
# Duas pernas: esta maquina -> bastion (porta + 10000) -> 3067 (127.0.0.1:porta). So com chave (BatchMode):
# em segundo plano nao ha onde digitar senha. Se a conexao cair, reabre em 10 s.
#
# Uso: sss-tunel-3067.sh start | stop | status
# Navegador: http://127.0.0.1:18000/ (DEV) e http://127.0.0.1:18001/ (PROD).
set -u

BASTION=mastersafgf@10.238.10.109
DESTINO=mastersafgf@10.129.164.55
PORTAS="18000 18001"            # portas do web no 3067 (DEV e PROD); as mesmas nesta maquina
DESLOCAMENTO=10000              # porta intermediaria no bastion: porta + 10000 (28000, 28001)
DIR=$HOME/.sss_tunel
PID_FILE=$DIR/tunel.pid
LOG=$DIR/tunel.log

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3
          -o ExitOnForwardFailure=yes -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa)

_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

_loop() {
    local local_fwd=() remote_fwd="" p
    for p in $PORTAS; do
        local_fwd+=(-L "127.0.0.1:$p:127.0.0.1:$((p + DESLOCAMENTO))")
        remote_fwd="$remote_fwd -L 127.0.0.1:$((p + DESLOCAMENTO)):127.0.0.1:$p"
    done
    while :; do
        echo "$(date '+%F %T') abrindo o tunel ($PORTAS)"
        # -tt: o ssh do bastion recebe SIGHUP quando esta conexao cai e libera as portas intermediarias.
        ssh -tt "${SSH_OPTS[@]}" "${local_fwd[@]}" "$BASTION" \
            "ssh -o BatchMode=yes -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -N$remote_fwd $DESTINO"
        echo "$(date '+%F %T') tunel caiu (codigo $?); nova tentativa em 10 s"
        sleep 10
    done
}

case "${1:-}" in
    start)
        if _running; then echo "ja no ar (pid $(cat "$PID_FILE"))"; exit 0; fi
        mkdir -m 0700 -p "$DIR"
        # setsid: grupo de processos proprio, para o stop derrubar o laco e o ssh juntos.
        setsid nohup "$0" _loop >>"$LOG" 2>&1 < /dev/null &
        echo $! > "$PID_FILE"
        sleep 5
        "$0" status
        ;;
    stop)
        if ! _running; then echo "fora do ar"; rm -f "$PID_FILE"; exit 0; fi
        kill -TERM -- "-$(cat "$PID_FILE")" 2>/dev/null
        rm -f "$PID_FILE"
        echo "tunel parado"
        ;;
    status)
        if _running; then echo "laco no ar (pid $(cat "$PID_FILE")); log: $LOG"; else echo "fora do ar"; fi
        for p in $PORTAS; do
            curl -s -o /dev/null -m 10 -w "porta $p: HTTP %{http_code}\n" \
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
