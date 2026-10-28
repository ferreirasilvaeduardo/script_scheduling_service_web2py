#!/bin/bash
# Mantem os processos do SSS no ar sem root nem systemd (CR-030, P2; DEPLOYMENT §10.6): para o cron da conta
# que roda o SSS, com @reboot e a cada 5 minutos. Para cada nome, confere se o processo esta no ar e, se nao
# estiver, sobe pelo launcher em segundo plano.
#
# Uso: sss-keepalive.sh <processo>...             web: <nome>:<porta> (ex.: web0001:18000, em 127.0.0.1) ou
#                                                 <nome>:<endereco IPv4>:<porta> (ex.: web0001:0.0.0.0:18000,
#                                                 todas as interfaces; CR-032); agente: <nome>
#      sss-keepalive.sh --pause <nome>            nao sobe mais o processo (parada de proposito)
#      sss-keepalive.sh --resume <nome>           volta a subir
#
# O papel vem do config (instance/<nome>/config.ini com [web] e sem [agent]: web). Sem endereco, o web atende so em
# 127.0.0.1; com outro endereco, a tela fica exposta na rede (sem HTTPS, a senha trafega aberta: README §14).
# Log: var/<nome>/logs/keepalive.log (uma linha por subida, recusa ou falha); a saida do processo vai para
# var/<nome>/logs/<nome>.out. Variaveis: PYTHON (padrao python3), SSS_TZ, SSS_IC_DIR (as dos launchers).
# Codigos: 0 ok (inclusive "ja no ar" e "em pausa"); 1 root; 2 uso invalido; 3 algum processo nao subiu.
set -uo pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Erro: execucao como root nao e permitida." >&2
    exit 1
fi
umask 077

# Caminho fisico (pwd -P): e o que /proc/<pid>/cwd mostra.
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "${REPO_ROOT}" || exit 2
RE_NAME='^[a-z][a-z0-9_-]{0,29}$'

_usage() {
    echo "Erro: uso: sss-keepalive.sh <nome>[:[<endereco>:]<porta>]... | --pause <nome> | --resume <nome>" >&2
    exit 2
}

_log() {
    # _log <nome> <mensagem>
    mkdir -p "var/$1/logs" 2>/dev/null
    printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$2" >> "var/$1/logs/keepalive.log"
}

_valid_ipv4() {
    local part
    [[ "$1" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]] || return 1
    for part in ${1//./ }; do
        [ "$((10#${part}))" -le 255 ] || return 1
    done
    return 0
}

# Algum python rodando scripts/<comando>.py --name <nome> a partir desta raiz?
_running() {
    local name="$1" script="$2" proc args arg sss prev cwd
    for proc in /proc/[0-9]*; do
        args=()
        while IFS= read -r -d '' arg; do args+=("${arg}"); done < <(cat "${proc}/cmdline" 2>/dev/null || true)
        [ "${#args[@]}" -ge 3 ] || continue
        case "$(basename "${args[0]}")" in python*) ;; *) continue ;; esac
        sss=""
        prev=""
        for arg in "${args[@]:1}"; do
            [ "${arg}" = "${script}" ] && sss="${sss}s"
            [ "${prev}" = "--name" ] && [ "${arg}" = "${name}" ] && sss="${sss}n"
            prev="${arg}"
        done
        case "${sss}" in *s*n*|*n*s*) ;; *) continue ;; esac
        cwd="$(readlink "${proc}/cwd" 2>/dev/null || true)"
        [ "${cwd}" = "${REPO_ROOT}" ] && return 0
    done
    return 1
}

if [ "$#" -eq 2 ] && { [ "$1" = "--pause" ] || [ "$1" = "--resume" ]; }; then
    [[ "$2" =~ ${RE_NAME} ]] || _usage
    mkdir -p "var/$2"
    if [ "$1" = "--pause" ]; then
        : > "var/$2/keepalive.pause"
        _log "$2" "pausa: o keepalive nao sobe mais $2 (sss-keepalive.sh --resume $2 volta)"
        echo "pausa: $2 (pare o processo com bin/sss-stop.sh ou SIGTERM)"
    else
        rm -f "var/$2/keepalive.pause"
        _log "$2" "pausa retirada: o keepalive volta a subir $2"
        echo "pausa retirada: $2"
    fi
    exit 0
fi
[ "$#" -ge 1 ] || _usage

status=0
for item in "$@"; do
    name="${item%%:*}"
    port=""
    host="127.0.0.1"
    [ "${item}" != "${name}" ] && port="${item#*:}"
    if [[ "${port}" == *:* ]]; then
        # CR-032: <nome>:<endereco>:<porta>; so IPv4 com cada parte de 0 a 255.
        host="${port%:*}"
        port="${port##*:}"
    fi
    [[ "${name}" =~ ${RE_NAME} ]] || _usage
    config="instance/${name}/config.ini"
    if [ ! -f "${config}" ]; then
        _log "${name}" "recusado: ${config} nao existe"
        echo "Erro: ${config} nao existe." >&2
        status=3
        continue
    fi
    if grep -q '^\[web\]' "${config}" && ! grep -q '^\[agent\]' "${config}"; then
        script="scripts/run_web.py"
        if ! [[ "${port}" =~ ^[0-9]{2,5}$ ]]; then
            _log "${name}" "recusado: o web precisa da porta (${name}:<porta>)"
            echo "Erro: o web precisa da porta: ${name}:<porta>." >&2
            status=3
            continue
        fi
        if ! _valid_ipv4 "${host}"; then
            _log "${name}" "recusado: endereco invalido ${host} (use IPv4, ex.: ${name}:0.0.0.0:${port})"
            echo "Erro: endereco invalido: ${host} (use IPv4, ex.: ${name}:0.0.0.0:${port})." >&2
            status=3
            continue
        fi
        command=(bin/sss-web.sh "${name}" --host "${host}" --port "${port}")
    else
        script="scripts/run_scheduler.py"
        command=(bin/sss-scheduler.sh "${name}")
    fi
    if [ -f "var/${name}/keepalive.pause" ]; then
        continue
    fi
    if _running "${name}" "${script}"; then
        continue
    fi
    mkdir -p "var/${name}/logs"
    nohup "${command[@]}" >> "var/${name}/logs/${name}.out" 2>&1 < /dev/null &
    pid=$!
    sleep 3
    if kill -0 "${pid}" 2>/dev/null; then
        _log "${name}" "subiu: pid ${pid} (${command[*]})"
    else
        _log "${name}" "falhou ao subir: veja var/${name}/logs/${name}.out e o log da aplicacao"
        echo "Erro: ${name} nao subiu; veja var/${name}/logs/${name}.out." >&2
        status=3
    fi
done
exit "${status}"
