#!/bin/bash
# Operacao de uma raiz do SSS em um comando (DEPLOYMENT-SERVER, passos 12, 14 e 15): os processos saem do
# instance/ desta raiz (web: [web] sem o [agent] de um agente; agente: o resto) e a porta do web, da URL do
# [web] allowed_origins. Sobe e mantem pelo bin/sss-keepalive.sh; para pelo bin/sss-stop.sh e por SIGTERM.
#
# Uso: sss-ctl.sh status                 cada processo: no ar (pid), parado ou pausado; e o estado do health
#      sss-ctl.sh stop                   pausa todos, para os agentes e o web desta raiz e espera sair
#      sss-ctl.sh start                  retira a pausa e roda o keepalive
#      sss-ctl.sh restart                stop e start
#      sss-ctl.sh cron show|install|remove   bloco do crontab deste tipo (passo 14): mostra, instala (so se
#                                            ainda nao estiver la) ou retira (so o bloco deste tipo)
#
# Variaveis: PYTHON (padrao python3) e as dos launchers (SSS_TZ, SSS_IC_DIR, SSS_LOCALE, ORACLE_HOME), em geral
# do sss_vars.sh; SSS_WEB_HOST (IPv4) faz o web atender nesse endereco (padrao: so 127.0.0.1).
# Codigos: 0 ok; 1 root; 2 uso invalido ou configuracao; 3 processo que nao subiu ou nao parou.
# Sem -u: no bash 4.1 (CentOS 6) uma lista vazia ("${AGENTS[@]}" sem agentes) daria "unbound variable".
set -o pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Erro: execucao como root nao e permitida." >&2
    exit 1
fi
umask 077

# Caminho fisico (pwd -P): e o que /proc/<pid>/cwd mostra.
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "${REPO_ROOT}" || exit 2
TIPO="$(basename "$(dirname "${REPO_ROOT}")")"
PYTHON="${PYTHON:-python3}"
PYTHON_BASE="$(basename "${PYTHON}")"
STOP_WAIT_S="${SSS_STOP_WAIT_S:-45}"

_usage() {
    echo "Erro: uso: sss-ctl.sh status | stop | start | restart | cron show|install|remove" >&2
    exit 2
}

# Mesma regra do sss-keepalive.sh (e do sss_config.load): [web] presente e, se houver [agent], sem environments
# nem max_parallel_jobs.
_is_web() {
    grep -q '^\[web\]' "$1" || return 1
    ! awk '/^\[/{sec=$0; next} sec=="[agent]" && /^[[:space:]]*(environments|max_parallel_jobs)[[:space:]]*=/{found=1}
           END{exit !found}' "$1"
}

WEBS=()
AGENTS=()
for config in instance/*/config.ini; do
    [ -f "${config}" ] || continue
    name="$(basename "$(dirname "${config}")")"
    [ "${name}" = "exemplos" ] && continue
    if _is_web "${config}"; then WEBS+=("${name}"); else AGENTS+=("${name}"); fi
done
if [ "${#WEBS[@]}" -eq 0 ] && [ "${#AGENTS[@]}" -eq 0 ]; then
    echo "Erro: nenhum processo em ${REPO_ROOT}/instance/." >&2
    exit 2
fi

# <nome>:<porta> (ou <nome>:<SSS_WEB_HOST>:<porta>) com a porta da primeira URL do [web] allowed_origins.
_web_spec() {
    local url port
    url="$(sed -n 's/^[[:space:]]*allowed_origins[[:space:]]*=[[:space:]]*\([^ ,;]*\).*/\1/p' "instance/$1/config.ini" | head -1)"
    port="$(printf '%s' "${url}" | sed -n 's#^[a-z]*://[^/:]*:\([0-9][0-9]*\).*#\1#p')"
    if [ -z "${port}" ]; then
        echo "Erro: instance/$1/config.ini sem porta no [web] allowed_origins (ex.: http://127.0.0.1:18000)." >&2
        return 1
    fi
    if [ -n "${SSS_WEB_HOST:-}" ]; then echo "$1:${SSS_WEB_HOST}:${port}"; else echo "$1:${port}"; fi
}

SPECS=()
for name in "${WEBS[@]}"; do
    spec="$(_web_spec "${name}")" || exit 2
    SPECS+=("${spec}")
done
SPECS+=("${AGENTS[@]}")

# PIDs de um processo desta raiz: python* (ou o executavel do PYTHON) rodando <script> --name <nome>.
_pids() {
    local name="$1" script="$2" proc args arg sss prev
    for proc in /proc/[0-9]*; do
        [ "$(readlink "${proc}/cwd" 2>/dev/null)" = "${REPO_ROOT}" ] || continue
        args=()
        while IFS= read -r -d '' arg; do args+=("${arg}"); done < <(cat "${proc}/cmdline" 2>/dev/null || true)
        [ "${#args[@]}" -ge 3 ] || continue
        case "$(basename "${args[0]}")" in python*|"${PYTHON_BASE}") ;; *) continue ;; esac
        sss=""
        prev=""
        for arg in "${args[@]:1}"; do
            [ "${arg}" = "${script}" ] && sss="${sss}s"
            [ "${prev}" = "--name" ] && [ "${arg}" = "${name}" ] && sss="${sss}n"
            prev="${arg}"
        done
        case "${sss}" in *s*n*|*n*s*) echo "${proc#/proc/}" ;; esac
    done
}

_script_of() {
    local n
    for n in "${WEBS[@]}"; do [ "$n" = "$1" ] && { echo "scripts/run_web.py"; return; }; done
    echo "scripts/run_scheduler.py"
}

_status() {
    local name pids state health
    echo "tipo=${TIPO} raiz=${REPO_ROOT}"
    for name in "${WEBS[@]}" "${AGENTS[@]}"; do
        pids="$(_pids "${name}" "$(_script_of "${name}")" | tr '\n' ' ')"
        if [ -n "${pids}" ]; then state="no ar (pid ${pids% })"; else state="parado"; fi
        [ -f "var/${name}/keepalive.pause" ] && state="${state}, pausado"
        printf '%-12s %s\n' "${name}" "${state}"
    done
    if [ "${#AGENTS[@]}" -gt 0 ]; then
        health="var/${AGENTS[0]}/logs/health.txt"
        if [ -f "${health}" ]; then
            echo "health ($(date -r "${health}" '+%Y-%m-%d %H:%M:%S')): $(head -1 "${health}")"
        else
            echo "health: sem ${health} (o crontab do passo 14 o grava a cada 5 minutos)"
        fi
    fi
}

_stop() {
    local name waited left
    for name in "${WEBS[@]}" "${AGENTS[@]}"; do bin/sss-keepalive.sh --pause "${name}" >/dev/null; done
    for name in "${AGENTS[@]}"; do
        [ -n "$(_pids "${name}" scripts/run_scheduler.py)" ] && bin/sss-stop.sh "${name}" >/dev/null
    done
    for name in "${WEBS[@]}"; do
        for pid in $(_pids "${name}" scripts/run_web.py); do kill -TERM "${pid}" 2>/dev/null; done
    done
    waited=0
    while :; do
        left=""
        for name in "${WEBS[@]}" "${AGENTS[@]}"; do
            [ -n "$(_pids "${name}" "$(_script_of "${name}")")" ] && left="${left} ${name}"
        done
        [ -z "${left}" ] && { echo "parado: ${WEBS[*]} ${AGENTS[*]} (pausados no keepalive)"; return 0; }
        if [ "${waited}" -ge "${STOP_WAIT_S}" ]; then
            echo "Erro: ainda no ar depois de ${STOP_WAIT_S} s:${left} (os agentes encerram os scripts em ate 30 s)." >&2
            return 3
        fi
        sleep 1
        waited=$((waited + 1))
    done
}

_start() {
    local name
    for name in "${WEBS[@]}" "${AGENTS[@]}"; do rm -f "var/${name}/keepalive.pause"; done
    bin/sss-keepalive.sh "${SPECS[@]}"
}

# Bloco do crontab deste tipo (DEPLOYMENT-SERVER, passo 14), entre as marcas de inicio e fim.
_cron_block() {
    local py_abs health_agent
    py_abs="$(command -v "${PYTHON}" 2>/dev/null)" || true
    if [ -z "${py_abs}" ]; then
        echo "Erro: PYTHON=${PYTHON} nao encontrado (carregue o sss_vars.sh)." >&2
        return 2
    fi
    health_agent="${AGENTS[0]:-}"
    echo "# --- SSS ${TIPO} --- (sss-ctl.sh, gerado em $(date '+%Y-%m-%d %H:%M'))"
    echo "PYTHON=${py_abs}"
    [ -n "${SSS_TZ:-}" ] && echo "SSS_TZ=${SSS_TZ}"
    echo "PATH=$(dirname "${py_abs}"):/usr/local/bin:/usr/bin:/bin"
    [ -n "${ORACLE_HOME:-}" ] && echo "ORACLE_HOME=${ORACLE_HOME}"
    [ -n "${SSS_IC_DIR:-}" ] && { echo "SSS_IC_DIR=${SSS_IC_DIR}"; echo "LD_LIBRARY_PATH=${SSS_IC_DIR}"; }
    [ -n "${SSS_LOCALE:-}" ] && echo "SSS_LOCALE=${SSS_LOCALE}"
    echo "@reboot      cd ${REPO_ROOT} && bin/sss-keepalive.sh ${SPECS[*]}"
    echo "*/5 * * * *  cd ${REPO_ROOT} && bin/sss-keepalive.sh ${SPECS[*]}"
    if [ -n "${health_agent}" ]; then
        echo "*/5 * * * *  cd ${REPO_ROOT} && \$PYTHON scripts/health.py --name ${health_agent}" \
             "> var/${health_agent}/logs/health.txt 2> var/${health_agent}/logs/health.err"
    fi
    echo "# --- fim SSS ${TIPO} ---"
}

_cron() {
    local file="var/crontab_sss/crontab_sss.txt" current
    case "${1:-}" in
        show)
            _cron_block
            ;;
        install)
            # Primeiro o crontab: com o bloco ja la, a copia tambem fica como esta (e a do bloco instalado).
            current="$(crontab -l 2>/dev/null || true)"
            if printf '%s\n' "${current}" | grep -q "^# --- SSS ${TIPO} ---"; then
                echo "ja existe o bloco do SSS ${TIPO} no crontab (nada acrescentado; para trocar: cron remove e cron install)"
                return 0
            fi
            mkdir -m 0700 -p var/crontab_sss
            _cron_block > "${file}.tmp" || { rm -f "${file}.tmp"; return 2; }
            chmod 0600 "${file}.tmp" && mv "${file}.tmp" "${file}"
            { [ -n "${current}" ] && printf '%s\n' "${current}"; cat "${file}"; } | crontab - || return 3
            echo "bloco do SSS ${TIPO} acrescentado ao crontab (copia em ${REPO_ROOT}/${file})"
            ;;
        remove)
            current="$(crontab -l 2>/dev/null || true)"
            if ! printf '%s\n' "${current}" | grep -q "^# --- SSS ${TIPO} ---"; then
                echo "o crontab nao tem o bloco do SSS ${TIPO} (nada retirado)"
                return 0
            fi
            printf '%s\n' "${current}" | sed "/^# --- SSS ${TIPO} ---/,/^# --- fim SSS ${TIPO} ---/d" | crontab - || return 3
            echo "bloco do SSS ${TIPO} retirado do crontab"
            ;;
        *)
            _usage
            ;;
    esac
}

case "${1:-}" in
    status) [ "$#" -eq 1 ] || _usage; _status ;;
    stop) [ "$#" -eq 1 ] || _usage; _stop ;;
    start) [ "$#" -eq 1 ] || _usage; _start ;;
    restart) [ "$#" -eq 1 ] || _usage; _stop && _start ;;
    cron) [ "$#" -eq 2 ] || _usage; _cron "$2" ;;
    *) _usage ;;
esac
