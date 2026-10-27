#!/usr/bin/env bash
# Atualizacao no lugar (CR-028, D10; DEPLOYMENT §18): troca so o codigo da aplicacao pelo de um pacote do
# tools/package.py e preserva instance/, var/ e scripts_ambiente/. Guarda o codigo atual num pacote de
# retorno, no mesmo formato, que o proprio comando aplica para voltar.
#
# Uso: sss-update.sh <sss-<versao>.tar.gz> [<SHA256SUMS>]   (padrao: o SHA256SUMS ao lado do pacote)
#
# Com o web e todos os agentes PARADOS (sss-stop.sh / systemctl stop). Codigos de saida: 0 ok; 1 root;
# 2 uso ou pacote invalido (nada mudou); 3 processo do SSS em execucao nesta pasta (nada mudou);
# 4 falha no meio da troca (o codigo anterior fica em <raiz>/.update-<data>/anterior/; ver DEPLOYMENT §18).
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Erro: execucao como root nao e permitida (rode com o usuario dono da aplicacao)." >&2
    exit 1
fi
umask 077

# Caminho fisico (pwd -P): e o que /proc/<pid>/cwd mostra, mesmo com link simbolico no caminho da raiz.
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
# Partes trocadas pela atualizacao: o resto (instance/<nome>/, var/, scripts_ambiente/, dev/...) fica.
CODE_DIRS=(bin docs scripts src)
CODE_FILES=(AGENTS.md README.md SHA256SUMS)

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "Erro: uso: sss-update.sh <sss-<versao>.tar.gz> [<SHA256SUMS>]" >&2
    exit 2
fi
if [ ! -f "$1" ]; then
    echo "Erro: pacote nao encontrado ($1)." >&2
    exit 2
fi
PACKAGE="$(cd "$(dirname "$1")" && pwd -P)/$(basename "$1")"
SUMS="${2:-$(dirname "${PACKAGE}")/SHA256SUMS}"
if [ ! -f "${SUMS}" ]; then
    echo "Erro: SHA256SUMS nao encontrado (${SUMS})." >&2
    exit 2
fi

# 1. Nada do SSS rodando a partir desta pasta: um python cujo argumento e um dos comandos do SSS (os launchers
# fazem exec de "<python> scripts/<comando>.py"), com o cwd na raiz.
for proc in /proc/[0-9]*; do
    args=()
    while IFS= read -r -d '' arg; do args+=("${arg}"); done < <(cat "${proc}/cmdline" 2>/dev/null || true)
    [ "${#args[@]}" -ge 2 ] || continue
    case "$(basename "${args[0]}")" in python*) ;; *) continue ;; esac
    sss=""
    for arg in "${args[@]:1}"; do
        case "${arg}" in
            scripts/run_web.py|scripts/run_scheduler.py|"${REPO_ROOT}"/scripts/*.py) sss=1 ;;
        esac
    done
    [ -n "${sss}" ] || continue
    cwd="$(readlink "${proc}/cwd" 2>/dev/null || true)"
    if [ -z "${cwd}" ]; then
        echo "Aviso: nao foi possivel conferir o processo ${proc#/proc/} (${args[*]}): pertence a outro usuario?" >&2
    elif [ "${cwd}" = "${REPO_ROOT}" ]; then
        echo "Erro: processo do SSS em execucao nesta pasta (pid ${proc#/proc/}); pare o web e os agentes." >&2
        exit 3
    fi
done

# 2. Pacote conferido pelo SHA256SUMS externo e pelo interno.
expected="$(awk -v f="$(basename "${PACKAGE}")" '$2 == f || $2 == "*" f {print $1}' "${SUMS}")"
if [ -z "${expected}" ] || [ "$(sha256sum "${PACKAGE}" | awk '{print $1}')" != "${expected}" ]; then
    echo "Erro: o pacote nao confere com o SHA256SUMS (${SUMS})." >&2
    exit 2
fi
STAMP="$(date +%Y%m%d_%H%M%S)"
# Extracao e codigo anterior numa pasta da propria raiz (mesma particao: os mv da troca sao renomeacoes, mesmo
# com var/ em particao propria); so o pacote de retorno fica em var/update/<data>/.
WORK="${REPO_ROOT}/.update-${STAMP}"
BACK_DIR="${REPO_ROOT}/var/update/${STAMP}"
if ! mkdir -p "${WORK}/novo" "${BACK_DIR}" 2>/dev/null; then
    echo "Erro: sem permissao para criar ${WORK} ou ${BACK_DIR} (dono da raiz e de var/: o usuario do servico)." >&2
    rm -rf "${WORK}" "${BACK_DIR}"
    exit 2
fi
tar -xzf "${PACKAGE}" -C "${WORK}/novo"
tops=("${WORK}/novo"/*)
if [ "${#tops[@]}" -ne 1 ] || [ ! -d "${tops[0]}" ] || [ ! -f "${tops[0]}/SHA256SUMS" ]; then
    echo "Erro: o pacote deve ter uma unica pasta sss-<versao>/ com SHA256SUMS." >&2
    rm -rf "${WORK}" "${BACK_DIR}"
    exit 2
fi
NEW="${tops[0]}"
if ! (cd "${NEW}" && sha256sum -c --quiet SHA256SUMS >/dev/null 2>&1); then
    echo "Erro: o conteudo do pacote nao confere com o SHA256SUMS interno." >&2
    rm -rf "${WORK}" "${BACK_DIR}"
    exit 2
fi
for d in "${CODE_DIRS[@]}"; do
    if [ ! -d "${NEW}/${d}" ]; then
        echo "Erro: o pacote nao tem a pasta ${d}/." >&2
        rm -rf "${WORK}" "${BACK_DIR}"
        exit 2
    fi
done

# 3. Pacote de retorno com o codigo atual, no mesmo formato (pasta unica + SHA256SUMS interno e externo).
BACK="sss-retorno-${STAMP}"
mkdir -p "${WORK}/retorno/${BACK}/instance"
for d in "${CODE_DIRS[@]}"; do
    [ -d "${REPO_ROOT}/${d}" ] && cp -a "${REPO_ROOT}/${d}" "${WORK}/retorno/${BACK}/"
done
for f in "${CODE_FILES[@]}"; do
    [ -f "${REPO_ROOT}/${f}" ] && cp -a "${REPO_ROOT}/${f}" "${WORK}/retorno/${BACK}/"
done
[ -d "${REPO_ROOT}/instance/exemplos" ] && cp -a "${REPO_ROOT}/instance/exemplos" "${WORK}/retorno/${BACK}/instance/"
(cd "${WORK}/retorno/${BACK}" && rm -f SHA256SUMS \
    && find . -type f ! -name SHA256SUMS -printf '%P\n' | LC_ALL=C sort | xargs -r -d '\n' sha256sum > SHA256SUMS)
(cd "${WORK}/retorno" && tar -czf "${BACK}.tar.gz" "${BACK}" && sha256sum "${BACK}.tar.gz" > SHA256SUMS \
    && rm -rf "${BACK}")
mv "${WORK}/retorno/${BACK}.tar.gz" "${WORK}/retorno/SHA256SUMS" "${BACK_DIR}/"

# 4. Troca: o codigo atual vai para anterior/; o novo entra. instance/<nome>/, var/ e scripts_ambiente/ ficam.
mkdir -p "${WORK}/anterior/instance"
trocar() {
    # Dentro de "if ! trocar" o set -e nao vale: cada passo confere o proprio resultado.
    local d f
    for d in "${CODE_DIRS[@]}"; do
        if [ -e "${REPO_ROOT}/${d}" ]; then mv "${REPO_ROOT}/${d}" "${WORK}/anterior/${d}" || return 1; fi
        mv "${NEW}/${d}" "${REPO_ROOT}/${d}" || return 1
    done
    for f in "${CODE_FILES[@]}"; do
        if [ -e "${REPO_ROOT}/${f}" ]; then mv "${REPO_ROOT}/${f}" "${WORK}/anterior/${f}" || return 1; fi
        if [ -e "${NEW}/${f}" ]; then mv "${NEW}/${f}" "${REPO_ROOT}/${f}" || return 1; fi
    done
    mkdir -p "${REPO_ROOT}/instance" || return 1
    if [ -d "${REPO_ROOT}/instance/exemplos" ]; then
        mv "${REPO_ROOT}/instance/exemplos" "${WORK}/anterior/instance/" || return 1
    fi
    if [ -d "${NEW}/instance/exemplos" ]; then mv "${NEW}/instance/exemplos" "${REPO_ROOT}/instance/" || return 1; fi
    return 0
}
if ! trocar; then
    echo "Erro: falha no meio da troca; o codigo anterior esta em ${WORK}/anterior/ e o retorno em" \
         "${BACK_DIR}/${BACK}.tar.gz (DEPLOYMENT §18)." >&2
    exit 4
fi
rm -rf "${WORK}"

echo "Atualizado a partir de $(basename "${PACKAGE}"). instance/, var/ e scripts_ambiente/ preservados."
echo "Retorno: ${REPO_ROOT}/bin/sss-update.sh ${BACK_DIR}/${BACK}.tar.gz"
