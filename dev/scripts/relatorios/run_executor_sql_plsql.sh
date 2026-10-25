#!/bin/bash
# v.1.0.1.0029
# Script para executar SQL/PL/SQL parametrizável em ambiente Oracle.
# Suporta execução direta via argumentos, leitura de arquivos .ini e exportação CSV.
# Mantém logs centralizados e validações básicas de conexão e arquivos.
# set -euo pipefail

if [ -t 1 ] && command -v clear >/dev/null 2>&1; then
        clear
fi

fc_valida_conexao() {
        ###############################################################
        # fc_valida_conexao
        # Valida diretório|arquivo e conexão Oracle antes de executar SQL.
        #
        # Retorno:
        #   0 - Sucesso (conexão validada e funcionando)
        #   1 - Erro (diretório/arquivo não existe|vazio ou conexão falhou)
        ###############################################################
        if [ -z "${BD_CONN+x}" ]; then
                BD_CONN=""
        fi
        BD_CONN="$(fc_trim "$BD_CONN")"
        export BD_CONN
        fc_log "Validando conexão com o banco de dados."
        if [ -z "$BD_CONN" ]; then
                # BD_CONN não foi fornecido via -cx|busca em arquivo
                if [ ! -d "$BD_CONN_DIR" ]; then
                        fc_log "[ERRO] Diretório de conexão BD_CONN_DIR não existe: $BD_CONN_DIR"
                        return 1
                fi
                fc_log "Diretório de conexão BD_CONN_DIR existe: $BD_CONN_DIR"
                if [ ! -f "$BD_CONN_FILE" ]; then
                        fc_log "[ERRO] Arquivo de conexão BD_CONN_FILE não existe: $BD_CONN_FILE"
                        return 1
                fi
                fc_log "Arquivo de conexão existe: $BD_CONN_FILE"
                if [ ! -s "$BD_CONN_FILE" ]; then
                        fc_log "[ERRO] Arquivo de conexão está vazio: $BD_CONN_FILE"
                        return 1
                fi
                fc_log "Arquivo de conexão possui registros: $BD_CONN_FILE"
                BD_CONN="$(cat "$BD_CONN_FILE")"
                BD_CONN="$(fc_trim "$BD_CONN")"
                export BD_CONN
        else
                fc_log "Usando conexão recebida pelo parâmetro -cx (senha mascarada)."
        fi
        if [ -z "$BD_CONN" ]; then
                fc_log "[ERRO] String de conexão BD_CONN está vazia após validação."
                return 1
        fi
        # Testa conexão efetiva com o banco
        fc_log "Testando conexão com o banco Oracle..."
        local current_datetime="$(date +%Y%m%d%H%M%S)_$((RANDOM % 1001))"
        local sql_conn_test_out="${LOGS_DIR}/conn_test_${current_datetime}.out"
        local sql_bd_conn_masked=""
        sql_bd_conn_masked="$(printf '%s' "$BD_CONN" | sed -E 's#^([^/]+)/([^@]+)@#\1/****@#')"
        fc_log "Conexao SQL (senha mascarada): $sql_bd_conn_masked"
        # -L evita novas tentativas interativas quando a autenticação falha.
        timeout 30 sqlplus -L -silent /nolog > "$sql_conn_test_out" 2>&1 << EOF
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
WHENEVER OSERROR EXIT FAILURE ROLLBACK
CONNECT ${BD_CONN}
SET PAGESIZE 0 FEEDBACK OFF VERIFY OFF HEADING OFF ECHO OFF
SELECT 1 FROM DUAL;
EXIT SUCCESS
EOF
        local status=$?
        if [ $status -eq 124 ]; then
                fc_log "[ERRO] Timeout (30s) ao conectar ao banco."
                fc_log "Saída do teste de conexão:"
                # Mascara qualquer credencial que eventualmente tenha sido impressa no output antes de jogar no log
                sed -E 's#([^[:space:]/]+)/[^[:space:]@]+@#\1/****@#g' "$sql_conn_test_out" | while IFS= read -r linha_saida; do
                        fc_log "  $linha_saida"
                done
                rm -f "$sql_conn_test_out"
                return 1
        # Valida retorno do processo e captura padrões de erro padrão Oracle
        elif [ $status -ne 0 ] || grep -E -q '(^|[[:space:]])(ORA-|SP2-|PLS-)[0-9]+' "$sql_conn_test_out"; then
                fc_log "[ERRO] Falha na conexão com o banco. Encerrando execução."
                fc_log "Saída do teste de conexão:"
                # Mascara qualquer credencial que eventualmente tenha sido impressa no output antes de jogar no log
                sed -E 's#([^[:space:]/]+)/[^[:space:]@]+@#\1/****@#g' "$sql_conn_test_out" | while IFS= read -r linha_saida; do
                        fc_log "  $linha_saida"
                done
                rm -f "$sql_conn_test_out"
                return 1
        fi
        rm -f "$sql_conn_test_out"
        fc_log "Conexão com o banco validada com sucesso."
        return 0
}

fc_remover_linha_branco_csv() {
    ###############################################################
    # fc_remover_linha_branco_csv
    # Remove a primeira linha se estiver em branco no arquivo CSV
    # Otimizado para arquivos grandes (O(1) - apenas primeira linha)
    #
    # Parâmetros:
    #   $1 - arquivo: Caminho do arquivo CSV
    #
    # Retorno:
    #   0 - Sucesso
    #   1 - Erro
    ###############################################################
    local arquivo="$1"
    
    if [ ! -f "$arquivo" ] || [ ! -s "$arquivo" ]; then
        return 0
    fi
    
    # Verifica apenas a PRIMEIRA linha (não lê o arquivo inteiro)
    local primeira_linha=$(head -n 1 "$arquivo" 2>/dev/null)
    
    # Se a primeira linha estiver vazia ou só tiver espaços|remove
    if [[ -z "$primeira_linha" ]] || [[ "$primeira_linha" =~ ^[[:space:]]*$ ]]; then
        fc_log "Removendo linha em branco do início do CSV: $(basename "$arquivo")"
        # sed -i '1d' é O(1) - remove apenas a primeira linha|não processa o resto
        if sed -i '1d' "$arquivo" 2>/dev/null; then
            fc_log "Linha em branco removida com sucesso"
            return 0
        else
            # Fallback para sistemas sem sed -i
            fc_log "[ALERTA] Fallback: usando tail para remover primeira linha"
            if tail -n +2 "$arquivo" > "${arquivo}.tmp" 2>/dev/null && [ -s "${arquivo}.tmp" ]; then
                mv -f "${arquivo}.tmp" "$arquivo"
                return $?
            else
                rm -f "${arquivo}.tmp"
                return 1
            fi
        fi
    fi
    
    return 0
}

fc_retira_ultimo_caractere() {
    ###############################################################
    # fc_retira_ultimo_caractere
    # Remove o último byte do arquivo informado.
    # É útil para remover o caractere '/' de final de PL/SQL quando
    # o script gera um terminador redundante.
    #
    # Parâmetros:
    #   $1 - arquivo: Caminho do arquivo a ajustar
    #
    # Retorno:
    #   0 - Sucesso
    #   1 - Erro
    ###############################################################
    local arquivo="${1:-}"

    if [ -z "$arquivo" ]; then
        fc_log "[ERRO] Arquivo não informado para remover o último caractere."
        return 1
    fi

    if [ ! -f "$arquivo" ]; then
        fc_log "[ERRO] Arquivo não encontrado para remover o último caractere: $arquivo"
        return 1
    fi

    local tamanho
    tamanho="$(wc -c < "$arquivo" 2>/dev/null | tr -d '[:space:]')"
    if [ -z "$tamanho" ] || [ "$tamanho" -le 0 ]; then
        fc_log "[ALERTA] Arquivo vazio, nada a remover: $arquivo"
        return 0
    fi

    # Linha de comando simples e direta: elimina o último byte do arquivo.
    if truncate -s -1 "$arquivo" 2>/dev/null; then
        fc_log "Último caractere removido do arquivo: $arquivo"
        return 0
    fi

    # Fallback em caso de truncate indisponível.
    local arquivo_tmp="${arquivo}.tmp"
    if dd if="$arquivo" bs=1 count=$((tamanho - 1)) of="$arquivo_tmp" 2>/dev/null && mv -f "$arquivo_tmp" "$arquivo" 2>/dev/null; then
        fc_log "Último caractere removido pelo fallback: $arquivo"
        return 0
    fi

    rm -f "$arquivo_tmp"
    fc_log "[ERRO] Falha ao remover o último caractere do arquivo: $arquivo"
    return 1
}

fc_verificar_erros_oracle_inicio_fim_arquivo() {
    ###############################################################
    # fc_verificar_erros_oracle_inicio_fim_arquivo
    # Verifica se há erros do Oracle nas primeiras e últimas 10 linhas do arquivo
    # Otimizado para arquivos grandes (O(1) - apenas primeiras e últimas 10 linhas)
    #
    # Parâmetros:
    #   $1 - arquivo: Caminho do arquivo CSV
    #
    # Retorno:
    #   0 - Sucesso
    #   1 - Erro
    ###############################################################     
        local arquivo="$1" 
        if [ ! -f "$arquivo" ] || [ ! -s "$arquivo" ]; then
                return 0
        fi
        if head -10 "$arquivo" | grep -E -q '(^|[[:space:]])(ORA-|SP2-|PLS-)[0-9]+'; then
            return 1
        fi
        if tail -10 "$arquivo" | grep -E -q '(^|[[:space:]])(ORA-|SP2-|PLS-)[0-9]+'; then
            return 1
        fi
        return 0
}

fc_validar_espaco_disco() {
        ###############################################################
        # fc_validar_espaco_disco
        # Verifica se o sistema de arquivos de um diretório possui o
        # espaço mínimo necessário para gerar os artefatos da execução.
        #
        # Parâmetros:
        #   $1 - dir: Diretório cujo sistema de arquivos será verificado
        #
        # Retorno:
        #   0 - Espaço disponível suficiente
        #   1 - Diretório inválido|df falhou ou espaço insuficiente
        ###############################################################
                local dir="$1"
                local espaco_necessario_mb=100  # Ajuste conforme necessidade
        local espaco_disponivel
        espaco_disponivel="$(df -Pm "$dir" 2>/dev/null | awk 'NR==2 {print $4}')"
        if ! [[ "$espaco_disponivel" =~ ^[0-9]+$ ]]; then
                fc_log "[ERRO] Não foi possível determinar o espaço em disco em $dir"
                return 1
        elif [ "$espaco_disponivel" -lt "$espaco_necessario_mb" ]; then
                fc_log "[ERRO] Espaço em disco insuficiente em $dir"
                fc_log "Disponível: ${espaco_disponivel}MB|Necessário: ${espaco_necessario_mb}MB"
                return 1
        fi
        return 0
}

fc_comprimir_arquivo_zip() {
    ###############################################################
    # fc_comprimir_arquivo_zip
    # Comprime um arquivo no formato ZIP (padrão Windows)
    # 
    # Parâmetros:
    #   $1 - arquivo: Caminho completo do arquivo a comprimir
    #   $2 - manter_original: "S" mantém o original|"N" remove (opcional|padrão "N")
    #
    # Retorno:
    #   0 - Sucesso na compressão
    #   1 - Erro (arquivo não existe|zip não disponível|etc.)
    #
    # Uso: fc_comprimir_arquivo_zip "/path/to/arquivo.csv" "S"
    ###############################################################
    local arquivo="$1"
    local manter_original="${2:-N}"
    local arquivo_zip="${arquivo}.zip"    
    # Verifica se o arquivo existe
    if [ ! -f "$arquivo" ]; then
        fc_log "[ERRO] Arquivo não encontrado para compressão: $arquivo"
        return 1
    fi
    # Verifica se o comando zip está disponível
    if ! command -v zip >/dev/null 2>&1; then
        fc_log "[ERRO] Comando 'zip' não encontrado. Instale com:"
        fc_log "  Debian/Ubuntu: apt-get install zip"
        fc_log "  RHEL/CentOS:   yum install zip"
        fc_log "  Windows (Git Bash): já vem instalado"
        return 1
    fi
    ## # Verifica o tamanho do arquivo (opcional - só comprime se > 10MB)
    ## local tamanho_minimo_mb=10
    ## local tamanho_arquivo=$(stat -c%s "$arquivo" 2>/dev/null || stat -f%z "$arquivo" 2>/dev/null)
    ## local tamanho_minimo_bytes=$((tamanho_minimo_mb * 1024 * 1024))
    ## if [ -n "$tamanho_arquivo" ] && [ "$tamanho_arquivo" -lt "$tamanho_minimo_bytes" ]; then
    ##     fc_log "Arquivo menor que ${tamanho_minimo_mb}MB (${tamanho_arquivo} bytes). Compressão opcional ignorada."
    ##     # Comprime mesmo assim? Se quiser comprimir sempre|remova este bloco
    ##     # return 0
    ## fi
    # Remove arquivo zip antigo se existir
    rm -f "$arquivo_zip" 2>/dev/null
    fc_log "Comprimindo arquivo: $arquivo -> $arquivo_zip"
    # Comprime com zip (formato Windows)
    # -j = não inclui caminhos (junk paths)
    # -q = modo quieto (menos saída)
    # -9 = máxima compressão
    zip -j -q -9 "$arquivo_zip" "$arquivo" 2>/dev/null
    local status=$?
    if [ $status -ne 0 ] || [ ! -f "$arquivo_zip" ]; then
        fc_log "[ERRO] Falha ao comprimir arquivo: $arquivo"
        return 1
    fi
    local tamanho_zip=$(stat -c%s "$arquivo_zip" 2>/dev/null || stat -f%z "$arquivo_zip" 2>/dev/null)
    fc_log "Arquivo comprimido com sucesso: $arquivo_zip (${tamanho_zip} bytes)"
    # Remove o arquivo original se solicitado
    if [ "$manter_original" = "N" ]; then
        rm -f "$arquivo" 2>/dev/null
        fc_log "Arquivo original removido: $arquivo"
    fi
    return 0
}

fc_log() {
        ###############################################################
        # fc_log
        # Sistema centralizado de logging com formatação padronizada.
        # Registra mensagens com timestamp, PID e ID do processo.
        # Suporta diferentes níveis de log e destaca erros/alertas.
        #
        # Parâmetros:
        #   $1 - msg: Mensagem a ser logada.
        #   $2 - logfile: Arquivo de log opcional; usa LOGS_PADRAO quando vazio.
        #
        # Retorno:
        #   0 - Sempre retorna sucesso.
        #
        # Uso:
        #   fc_log "Processando arquivo" "/path/to/log"
        #   fc_log "[ERRO] Falha na operação"
        #
        # Observações:
        #   - Adiciona [INFO] automaticamente quando a mensagem não tem prefixo.
        #   - Prefixos reconhecidos: [INFO], [ERRO], [ERR], [ALERTA], [AVISO], [ATENÇÃO], [DEBUG].
        #   - Erros e alertas são destacados com bordas visuais.
        #   - Formato: [YYYY-MM-DD HH:MM:SS] [PID:$$] [ID:processo] mensagem
        ###############################################################
        local msg="$1"
        # Se não houver arquivo explícito, usa a variável global LOGS_PADRAO.
        local logfile
        fc_init_var logfile LOGS_PADRAO "/dev/stdout" "${2:-}"
        local process_id
        fc_init_var process_id PROCESS_ID "NA"

        # Garante que o diretório do arquivo de log exista antes de escrever.
        # Isso evita falhas silenciosas quando a pasta de logs ainda não foi criada
        # ou quando o usuário informa um caminho personalizado fora do padrão.
        local logfile_dir
        logfile_dir="$(dirname "$logfile")"
        if [ -n "$logfile_dir" ] && [ "$logfile_dir" != "." ]; then
                mkdir -p "$logfile_dir" 2>/dev/null || true
        fi

        # Mensagens vazias servem apenas como separadores visuais.
        if [[ "$msg" =~ ^[[:space:]]*$ ]]; then
                printf '\n' | tee -a "$logfile"
                return 0
        fi

        # Adiciona prefixo padrão quando a mensagem não começa com um nível válido.
        case "$msg" in
                \[INFO\]*|\[ERRO\]*|\[ERR\]*|\[ALERTA\]*|\[AVISO\]*|\[ATENÇÃO\]*|\[DEBUG\]*)
                        ;;
                *)
                        msg="[INFO] $msg"
                        ;;
        esac

        local logfmt="[$(date '+%Y-%m-%d %H:%M:%S')] [PID:$$] [ID:$process_id] $msg"

        case "$msg" in
                \[ERRO\]*|\[ERR\]*)
                        printf '\n\n' | tee -a "$logfile"
                        printf '%s\n' " ----- ATENÇÃO [ERRO] ------ " "$logfmt" " ----------- " | tee -a "$logfile"
                        printf '\n\n' | tee -a "$logfile"
                        ;;
                \[ALERTA\]*|\[ATENÇÃO\]*|\[AVISO\]*)
                        printf '\n\n' | tee -a "$logfile"
                        printf '%s\n' " ----- ATENÇÃO [ALERTA] ------ " "$logfmt" " ----------- " | tee -a "$logfile"
                        printf '\n\n' | tee -a "$logfile"
                        ;;
                \[DEBUG\]*)
                        printf '%s\n' "$logfmt" | tee -a "$logfile"
                        ;;
                *)
                        printf '%s\n' "$logfmt" | tee -a "$logfile"
                        ;;
        esac
        return 0
}

fc_log_separador() {
        fc_log "" "${1:-}"
}

fc_trim() {
        ###############################################################
        # fc_trim
        # Remove espaços em branco do início e fim de uma string.
        # Entrada: string com possíveis espaços em branco no início e fim
        # Saída: string sem espaços em branco no início e fim
        ###############################################################
        local str="$1"
        # Remove espaços em branco do início e fim (puro Bash, sem subprocesso)
        str="${str#"${str%%[![:space:]]*}"}"
        str="${str%"${str##*[![:space:]]}"}"
        printf '%s\n' "$str"
}

fc_init_var() {
    ###############################################################
    # fc_init_var
    # Inicializa uma variável local a partir de uma variável global,
    # valor padrão ou valor opcional. Garante inicialização segura e flexível.
    #
    # Parâmetros:
        #   $1 - nome_variavel_destino: Variável que receberá o valor resolvido
        #   $2 - nome_variavel_origem: Variável global usada como alternativa
        #   $3 - valor_padrao: Valor usado quando a origem não estiver preenchida
        #   $4 - valor_prioritario: Valor opcional com maior prioridade
    #
    # Retorno: 0 (sempre bem-sucedida)
    #
    # Exemplo de uso:
    #   fc_init_var log_file LOGS_PADRAO "/dev/stdout" "$custom_log"
    #
    # Observações:
    #   - valor_prioritario tem precedência sobre a variável de origem
    #   - A variável de origem tem precedência sobre o valor padrão
    #   - Compatível com Bash 4.x+
    ###############################################################
        local nome_variavel_destino="$1"
        local nome_variavel_origem="$2"
        local valor_padrao="$3"
        local valor_prioritario="${4:-}"
        local valor_resolvido
        if [ -n "$valor_prioritario" ]; then
                valor_resolvido="$valor_prioritario"
        elif [ -n "${!nome_variavel_origem+x}" ] && [ -n "${!nome_variavel_origem}" ]; then
                valor_resolvido="${!nome_variavel_origem}"
        else
                valor_resolvido="$valor_padrao"
        fi
        printf -v "$nome_variavel_destino" '%s' "$valor_resolvido"
}

fc_criar_diretorio() {
        ###############################################################
        # fc_criar_diretorio
        # Cria um diretório de forma básica, sem validações avançadas.
        # Funciona como utilitário simples para garantir a existência de
        # caminhos de saída, logs e arquivos temporários.
        #
        # Parâmetros:
        #   $1 - dir_path: Caminho absoluto do diretório a ser criado.
        #
        # Retorno:
        #   0 - Sucesso (diretório criado ou já existia).
        #   1 - Erro (parâmetro vazio ou falha na criação).
        #
        # Exemplo de uso:
        #   fc_criar_diretorio "/path/to/directory"
        #
        # Observações:
        #   - Usa mkdir -p para criar diretórios pai automaticamente.
        #   - Não valida permissões, espaço em disco ou conteúdo existente.
        #   - Compatível com Bash 3.x+.
        ###############################################################
        local dir_path="$1"
        if [ -z "$dir_path" ]; then
                return 1
        fi
        if [ ! -d "$dir_path" ]; then
                mkdir -p "$dir_path" || return 1
                [ -d "$dir_path" ] || return 1
        fi
        return 0
}

fc_init_variaveis_globais() {
        #################################################
        # VARIÁVEIS GLOBAIS E DEFINIÇÕES DE AMBIENTE
        #################################################
        # ===== CONFIGURAÇÕES ORACLE =====
        export NLS_LANG=AMERICAN_AMERICA.AL32UTF8
        export NLS_DATE_FORMAT="YYYY-MM-DD HH24:MI:SS"
        export NLS_TIMESTAMP_FORMAT="YYYY-MM-DD HH24:MI:SS.FF"
        #################################################
        # VARIÁVEIS GLOBAIS E DEFINIÇÕES DE AMBIENTE
        # Função para inicializar variáveis globais e diretórios
        #################################################
        # Identificador curto do processo para rastreio em log.
        # Exemplo: a1b2c3d4
        PROCESS_ID="NA"
        # Status de execução do processo (0 = sucesso inicial).
        # Exemplo: 0
        PROCESS_STATUS=0
        # Data e hora completas em formato compacto YYYYMMDDHHMMSS.
        # Exemplo: 20260805142359
        CURRENT_DATETIME=$(date +%Y%m%d%H%M%S)
        # Horário atual HHMMSS para compor nomes únicos.
        # Exemplo: 142359
        CURRENT_HHMMSS=$(date +%H%M%S)
        # Data atual YYYYMMDD para particionar logs por dia.
        # Exemplo: 20260805
        CURRENT_DATE=$(date +%Y%m%d)
        if command -v uuidgen >/dev/null 2>&1; then
                # PROCESS_ID derivado de UUID (8 primeiros caracteres).
                # Exemplo: 7f3d9a1c
                PROCESS_ID=$(uuidgen | cut -c1-8)
        else
                # Fallback para ambientes sem uuidgen.
                # Exemplo: e4b21d90
                PROCESS_ID="$(printf '%04x%04x' "$RANDOM" "$RANDOM")"
        fi
        # Subdiretório da execução: hora + id curto.
        # Exemplo: 142359_7f3d9a1c
        PROCESS_SUBDIR="${CURRENT_HHMMSS}_${PROCESS_ID}"
        # Nome completo da execução: data + hora + id.
        # Exemplo: 20260805_142359_7f3d9a1c
        PROCESS_FULL="${CURRENT_DATE}_${CURRENT_HHMMSS}_${PROCESS_ID}"
        # Arquivos de parâmetros encontrados.
        # Exemplo: ("RB_RELATORIO_01.ini" "RB_RELATORIO 02.ini")
        INPUTS=()
        # Lista geral de arquivos|mantida por compatibilidade.
        ARQUIVOS_GERADOS=()
        # Vetor de arquivos processados com sucesso.
        # Exemplo: ("RB_RELATORIO_01.ini" "RB_RELATORIO_02.ini")
        ARQUIVOS_OK=()
        # Vetor de arquivos com erro durante processamento.
        # Exemplo: ("RB_RELATORIO_03.ini")
        ARQUIVOS_ERRO=()
        FLAG_NOME_ARQUIVO_SQL_DEFINIDO=0
        FLAG_SAIDA_ARQUIVO_DESTINO_DEFINIDO=0
        # Parâmetros de substituição no formato [chave];valor.
        LISTA_PARAMETROS=()
        # Nome do script em execução (com extensão).
        # Exemplo: run_executor_relatorio_csv_sql.sh
        SCRIPT_NAME="$(basename "$0")"
        # Caminho absoluto do diretório onde o script atual está.
        # Exemplo: /arquivos/RPA_SUSTENTACAO/RUNBOOK/scripts
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        # Diretório base um nível acima de SCRIPT_DIR.
        # Exemplo: /arquivos/RPA_SUSTENTACAO/RUNBOOK
        BASE_DIR="$(dirname "$SCRIPT_DIR")"
        # Nome do script sem extensão.
        # Exemplo: run_executor_relatorio_csv_sql
        SCRIPT_NAME_NO_EXT="$(echo "${SCRIPT_NAME%.*}" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
        SCRIPT_NAME_NO_UPPERCASE="$(echo "${SCRIPT_NAME%.*}" | tr '[:lower:]' '[:upper:]' | tr -d '[:space:]')"
        if [[ "$SCRIPT_NAME" == *.* ]]; then
                # Extensão do script sem ponto.
                # Exemplo: sh
                SCRIPT_EXT="${SCRIPT_NAME##*.}"
        else
                # Script sem extensão.
                # Exemplo: ""
                SCRIPT_EXT=""
        fi
        ARQUIVO_CONFIGURACAO_LOCAL="${SCRIPT_DIR}/${SCRIPT_NAME_NO_EXT}.ini"
        FLAG_SQL_PLSQL="SQL"
        FLAG_CONFIGURACAO_LOCAL=0
        if [ -f "$ARQUIVO_CONFIGURACAO_LOCAL" ]; then
                FLAG_CONFIGURACAO_LOCAL="$(cat "$ARQUIVO_CONFIGURACAO_LOCAL")"
                FLAG_CONFIGURACAO_LOCAL="$(echo "${FLAG_CONFIGURACAO_LOCAL}" | tr '[:lower:]' '[:upper:]' | tr -d '[:space:]')" # Converte para maiúsculas e remove espaços em branco.
                if [ "$FLAG_CONFIGURACAO_LOCAL" == "TRUE" ] || [ "$FLAG_CONFIGURACAO_LOCAL" == "1" ]; then
                        FLAG_CONFIGURACAO_LOCAL=1
                else
                        FLAG_CONFIGURACAO_LOCAL=0
                fi
        fi
        export FLAG_CONFIGURACAO_LOCAL
        export ARQUIVO_CONFIGURACAO_LOCAL
        CTL_DIR="${SCRIPT_DIR}"
        TIPO_CTL="input"
        if [ "$FLAG_CONFIGURACAO_LOCAL" -eq 0 ]; then
                BASE_DIR_LOG="${BASE_DIR}/logs/${SCRIPT_NAME_NO_EXT}/${CURRENT_DATE}/${CURRENT_HHMMSS}/${PROCESS_ID}"
                BASE_DIR_OUTPUT="${BASE_DIR}/saida/${SCRIPT_NAME_NO_EXT}/${CURRENT_DATE}/${CURRENT_HHMMSS}/${PROCESS_ID}"
                DATA_DIR="${BASE_DIR}/entrada"
                DATA_CONF="${BASE_DIR}/config"
                BASE_DIR_SQL="${BASE_DIR}/sql"
        
        else
                BASE_DIR_LOG="${SCRIPT_DIR}/logs/${SCRIPT_NAME_NO_EXT}/${CURRENT_DATE}/${CURRENT_HHMMSS}/${PROCESS_ID}"
                BASE_DIR_OUTPUT="${SCRIPT_DIR}/saida/${SCRIPT_NAME_NO_EXT}/${CURRENT_DATE}/${CURRENT_HHMMSS}/${PROCESS_ID}"
                DATA_DIR="${SCRIPT_DIR}"
                DATA_CONF="${SCRIPT_DIR}"
                BASE_DIR_SQL="${SCRIPT_DIR}"
        fi
        BASE_DIR_SQL_PADRAO="${BASE_DIR_SQL}"
        DESTINO_DIR="${BASE_DIR_OUTPUT}"
        # Diretório com configurações externas de conexão.
        BD_CONN_DIR="arquivos/CONNET_SH/"
        # Arquivo padrão de conexão.
        BD_CONN_FILE="${BD_CONN_DIR}/DB_conn.txt"
        # Prefixo/padrão inicial dos arquivos de configuração a buscar.
        NOME_INICIAL_ARQUIVO_PADRAO="${SCRIPT_NAME_NO_UPPERCASE}"
        # Não é readonly: pode ser sobrescrita via argumento de linha de comando
        NOME_INICIAL_ARQUIVO="${NOME_INICIAL_ARQUIVO_PADRAO}"
        # Nome padrão do arquivo de log da execução.
        # Exemplo: run_executor_relatorio_csv_sql.log
        LOGS_NOME_PADRAO="${SCRIPT_NAME_NO_EXT}.log"
        # Caminho completo do log principal.
        LOGS_PADRAO="${BASE_DIR_LOG}/${LOGS_NOME_PADRAO}"
        # Alias para log geral (ponto central para funções de log).
        # Exemplo: mesmo valor de LOGS_PADRAO
        LOGS_GERAL="${LOGS_PADRAO}"
        # Diretório de logs do processo|porém pode ser modificado
        LOGS_DIR="${BASE_DIR_LOG}"
        # Nome do log|porém pode ser modificado
        LOGS_NAME="${LOGS_NOME_PADRAO}"
        # Criação dos diretórios principais do processo
        for dir in "$BASE_DIR_LOG" "$BASE_DIR_OUTPUT" "$DATA_DIR" "$DATA_CONF" "$BASE_DIR_SQL"; do # "$CTL_DIR" "$BASE_DIR_SQL" "$BASE_DIR_BAD"; do
            if ! fc_criar_diretorio "$dir"; then
                fc_log "[ERRO] Falha ao criar diretório: $dir" "/dev/stdout"
                return 1
            fi
        done
        # Inicialização de parâmetros de entrada com valores padrão ou vazios
        NOME_ARQUIVO_SQL="${SCRIPT_NAME_NO_EXT}.sql" # Nome do arquivo SQL a ser executado
        SAIDA_ARQUIVO_DESTINO="${NOME_ARQUIVO_SQL}.csv"
        # String de conexão
        BD_CONN=""
        STRICT_TAGS=0
        DEBUG_SQL=0
        COMPRESS_CSV="N"
        MANTER_ARQUIVO_ORIGINAL="N"
        DELIMITADOR=';'
        export PROCESS_ID PROCESS_STATUS CURRENT_DATETIME CURRENT_HHMMSS CURRENT_DATE PROCESS_SUBDIR PROCESS_FULL SCRIPT_NAME SCRIPT_DIR BASE_DIR SCRIPT_NAME_NO_EXT SCRIPT_NAME_NO_UPPERCASE SCRIPT_EXT BASE_DIR_SQL BASE_DIR_LOG BASE_DIR_OUTPUT BD_CONN_DIR BD_CONN_FILE LOGS_NOME_PADRAO LOGS_PADRAO LOGS_GERAL LOGS_DIR LOGS_NAME NOME_ARQUIVO_SQL BD_CONN DATA_DIR DATA_CONF NOME_INICIAL_ARQUIVO_PADRAO NOME_INICIAL_ARQUIVO STRICT_TAGS DEBUG_SQL FLAG_NOME_ARQUIVO_SQL_DEFINIDO FLAG_SAIDA_ARQUIVO_DESTINO_DEFINIDO DESTINO_DIR SAIDA_ARQUIVO_DESTINO COMPRESS_CSV MANTER_ARQUIVO_ORIGINAL DELIMITADOR TIPO_CTL FLAG_SQL_PLSQL BASE_DIR_SQL_PADRAO
        return 0
}

fc_adicionar_erro_arquivo() {
        ###############################################################
        # fc_adicionar_erro_arquivo
        # Gerencia array global de arquivos com erro no processamento.
        # Remove arquivo de sucesso (se existir) e adiciona ao array de erros.
        # Atualiza status global do processo para indicar falha.
        # 
        # Parâmetros:
        #   $1 - arquivo: Nome/caminho do arquivo com erro
        # 
        # Retorno: 
        #   0 - Sempre retorna 0 (sucesso operacional)
        # 
        # Uso: fc_adicionar_erro_arquivo "/path/to/file.ini"
        # 
        # Observações:
        #   - Inicializa arrays globais se não existirem
        #   - Remove arquivo de ARQUIVOS_OK se presente (evita duplicata)
        #   - Adiciona a ARQUIVOS_ERRO (evita duplicatas com busca linear)
        #   - Define PROCESS_STATUS=1 (indica erro global)
        #   - Arrays globais: ARQUIVOS_OK|ARQUIVOS_ERRO|PROCESS_STATUS
        ###############################################################
        local arquivo="$1"
        # Garante que ARQUIVOS_OK e ARQUIVOS_ERRO existam como arrays globais
        if [ -z "${ARQUIVOS_OK+x}" ]; then
                ARQUIVOS_OK=()
        fi
        if [ -z "${ARQUIVOS_ERRO+x}" ]; then
                ARQUIVOS_ERRO=()
        fi
        # Remove do ARQUIVOS_OK se existir - compatível Bash 3.x
        if [ ${#ARQUIVOS_OK[@]} -gt 0 ]; then
                temp_array=()
                for element in "${ARQUIVOS_OK[@]}"; do
                        if [ "$element" != "$arquivo" ]; then
                                temp_array[${#temp_array[@]}]="$element"
                        fi
                done
                ARQUIVOS_OK=("${temp_array[@]}")
        fi
        # Adiciona ao ARQUIVOS_ERRO se não existir
        for f in "${ARQUIVOS_ERRO[@]}"; do
                [ "$f" = "$arquivo" ] && return 0
        done
        ARQUIVOS_ERRO[${#ARQUIVOS_ERRO[@]}]="$arquivo"
        PROCESS_STATUS=1
        export PROCESS_STATUS
        return 0
}

fc_adicionar_ok_arquivo() {
        ###############################################################
        # fc_adicionar_ok_arquivo
        # Gerencia array global de arquivos processados com sucesso.
        # Adiciona arquivo ao array de sucesso|evitando duplicatas e conflitos.
        # 
        # Parâmetros:
        #   $1 - arquivo: Nome/caminho do arquivo processado com sucesso
        # 
        # Retorno: 
        #   0 - Arquivo já estava em algum array ou foi adicionado
        #   1 - (não usado - função sempre termina com sucesso)
        # 
        # Uso: fc_adicionar_ok_arquivo "/path/to/file.ini"
        # 
        # Observações:
        #   - Inicializa arrays globais se não existirem  
        #   - Não adiciona se já está em ARQUIVOS_OK (evita duplicatas)
        #   - Não adiciona se está em ARQUIVOS_ERRO (conflito)
        #   - Prioriza arquivos com erro sobre sucesso
        #   - Arrays: ARQUIVOS_OK|ARQUIVOS_ERRO
        ###############################################################
        local arquivo="$1"
        # Garante que ARQUIVOS_OK e ARQUIVOS_ERRO existam como arrays globais
        if [ -z "${ARQUIVOS_OK+x}" ]; then
                ARQUIVOS_OK=()
        fi
        if [ -z "${ARQUIVOS_ERRO+x}" ]; then
                ARQUIVOS_ERRO=()
        fi
        # Não adiciona se já está em ARQUIVOS_OK
        for f in "${ARQUIVOS_OK[@]}"; do
                [ "$f" = "$arquivo" ] && return 0
        done
        # Não adiciona se está em ARQUIVOS_ERRO
        for f in "${ARQUIVOS_ERRO[@]}"; do
                [ "$f" = "$arquivo" ] && return 0
        done
        ARQUIVOS_OK[${#ARQUIVOS_OK[@]}]="$arquivo"
        return 0
}        

fc_adicionar_arquivos_gerados() {
        ###############################################################
        # fc_adicionar_arquivos_gerados
        # Gerencia array global de arquivos processados com sucesso.
        # Adiciona arquivo ao array de sucesso|evitando duplicatas e conflitos.
        # 
        # Parâmetros:
        #   $1 - arquivo: Nome/caminho do arquivo processado com sucesso
        # 
        # Retorno: 
        #   0 - Arquivo já estava em algum array ou foi adicionado
        #   1 - (não usado - função sempre termina com sucesso)
        # 
        # Uso: fc_adicionar_arquivos_gerados "/path/to/file.ini"
        # 
        # Observações:
        #   - Inicializa arrays globais se não existirem  
        #   - Não adiciona se já está em ARQUIVOS_GERADOS (evita duplicatas)
        #   - Prioriza arquivos com erro sobre sucesso
        #   - Arrays: ARQUIVOS_GERADOS
        ###############################################################
        local arquivo="$1"
        # Garante que ARQUIVOS_GERADOS existam como arrays globais
        if [ -z "${ARQUIVOS_GERADOS+x}" ]; then
                ARQUIVOS_GERADOS=()
        fi
        # Não adiciona se já está em ARQUIVOS_GERADOS
        for f in "${ARQUIVOS_GERADOS[@]}"; do
                [ "$f" = "$arquivo" ] && return 0
        done
        ARQUIVOS_GERADOS[${#ARQUIVOS_GERADOS[@]}]="$arquivo"
        return 0
}

fc_processa_parametro() {
        ###############################################################################
        # fc_processa_parametro 
        # Processa uma linha de parâmetro|extraindo chave e valor|normalizando e armazenando. 
        # Suporta comentários|espaços em branco e diferentes formatos de chave-valor. 
        # Parâmetros:  
        #   $1 - origem: Identificador da origem do parâmetro (ex: "Linha"|"Argumento")
        #   $2 - identificacao: Identificador da linha ou argumento (ex: número da linha)
        #   $3 - linha_lida: Conteúdo da linha lida
        # Retorno:
        #   0 - Parâmetro processado ou linha ignorada
        ###############################################################################
        local origem="$1"
        local identificacao="$2"
        local linha_lida="$3"
        local linha_sem_comentario opt_key_raw opt_value opt_key parametro_normalizado
        # Remove caracteres de retorno de carro (\r)
        linha_lida="${linha_lida%$'\r'}"
        if [[ -z "$linha_lida" || "$linha_lida" =~ ^[[:space:]]*# ]]; then
                # Linha vazia ou comentário|ignora
                return 0
        fi
        if [[ "$origem" == "Argumento" ]]; then
                linha_sem_comentario="${linha_lida}"
        else
                # Remove comentário inline somente quando # é precedido por espaço.
                # Assim|valores como senhas e identificadores podem conter #.
                linha_sem_comentario="${linha_lida}"
                if [[ "$linha_sem_comentario" =~ ^(.*[^[:space:]])[[:space:]]+#.*$ ]]; then
                        linha_sem_comentario="${BASH_REMATCH[1]}"
                fi
        fi
        # Remove espaços em branco desnecessários
        linha_sem_comentario="$(fc_trim "$linha_sem_comentario")"
        # Ignora conteúdo vazio após limpeza
        [ -n "$linha_sem_comentario" ] || return 0
        # Em arquivos de configuração|aceita os formatos "chave=valor" e
        # "chave:valor". A chave não pode conter espaços|':' ou '='; isso
        # evita que separadores presentes no início da linha sejam confundidos
        # com parte do nome do parâmetro. O valor|por outro lado|é capturado
        # integralmente|inclusive se contiver espaços ou outros separadores.
        if [[ "$origem" != "Argumento" && "$linha_sem_comentario" =~ ^([^[:space:]:=]+)[[:space:]]*[:=][[:space:]]*(.*)$ ]]; then
                # BASH_REMATCH[1] contém o texto antes do separador (= ou :),
                # correspondente ao nome da opção.
                opt_key_raw="${BASH_REMATCH[1]}"
                # BASH_REMATCH[2] contém todo o texto depois do separador,
                # que será normalizado mais adiante antes de ser armazenado.
                opt_value="${BASH_REMATCH[2]}"
        else
                # Para argumentos de linha de comando (ou linhas sem '='/':'),
                # usa a primeira palavra como chave e o restante como valor.
                # Essa alternativa preserva o tratamento de opções no formato
                # "--chave valor".
                opt_key_raw="${linha_sem_comentario%%[[:space:]]*}"
                # Remove a chave do início e mantém o conteúdo restante para
                # que ele possa ser aparado e validado abaixo.
                opt_value="${linha_sem_comentario#"$opt_key_raw"}"
        fi
        # Remove espaços em branco da chave extraída
        opt_key_raw="$(fc_trim "$opt_key_raw")"
        # Remove espaços em branco do valor extraído
        opt_value="$(fc_trim "$opt_value")"
        if [ -z "$opt_key_raw" ] || [ -z "$opt_value" ]; then
                fc_log "[ALERTA] Parâmetro inválido (${origem} ${identificacao}): '$linha_lida'"
                return 0
        fi
        opt_key="$(printf '%s' "$opt_key_raw" | tr '[:upper:]' '[:lower:]')"
        # Remove hífens do início para normalizar opções curtas e longas.
        while [[ "$opt_key" == -* ]]; do
                opt_key="${opt_key#-}"
        done
        opt_key="${opt_key%%[[:space:]]*}"
        # Remove colchetes literais da chave (evita duplicar em "[$opt_key]")
        opt_key="${opt_key//[\[\]]/}"
        if [ "$opt_key" = "cx" ] || [ "$opt_key" = "conexao" ] || [ "$opt_key" = "cxoracle" ] || [ "$opt_key" = "conexao-oracle" ] || [ "$opt_key" = "conexao_oracle" ] || [ "$opt_key" = "conexaooracle" ]; then
                fc_log "${origem} ${identificacao}: Chave='$opt_key_raw'|Valor='****'"
        else
                fc_log "${origem} ${identificacao}: Chave='$opt_key_raw'"
        fi
        # Formato armazenado: [chave];valor (tag entre colchetes usada no sed do SQL)
        parametro_normalizado="[$opt_key];$opt_value"
        if [[ "$opt_key" != -* ]]; then
                opt_key="-$opt_key"
        fi
        # Palavras reservadas: são tratadas pelo executor e não viram tags SQL.
        # Todas as demais chaves são armazenadas em LISTA_PARAMETROS para
        # substituir tags no formato [chave] dentro do arquivo SQL.
        #
        # Conexão e execução:
        #   -cx|-conexao|-cxoracle|-conexao-oracle|-conexao_oracle|-conexaooracle -->> Formato: owner/senha@servidor/serviço(SID)
        #   -st|-strict-tags|-stricttags|-strict_tags -->> Se True, todas as TAGs do script SQL terão que ser substituidas. Senão gera ERRO.
        #   -compress|-zip -->> DEFAULT = False
		#   -kp|-keep-original|-keep -->> Qdo "-compress = True", mantem o CSV original
        #   -dl|-delimiter|-delim|-delimitador -->> Delimitador DEFAULT = "|"
		#   -nls-lang
		#   -debug
        #
        # Diretórios e arquivos:
        #   -dirsql|-origemsql|-base-dir-sql|-basedirsql|-base_dir_sql  -->> Diretorio script SQL
        #   -sql|-sql-file|-sqlfile|-filesql  -->> Nome script SQL a ser executado
        #   -out|-output|-outdir|-output-dir|-destino-dir|-destino  -->> Diretorio destino aquivo CSV
        #   -outfile|-outputfile|-output-file|-saida-arquivo-destino|-saida-arquivo|-saidaarquivo  -->> No Arquivo CSV 
        #
        # Comandos reservados da linha de comando:
        #   -input|--input
        #   -h|--help
        case "$opt_key" in
				-out|-output|-outdir|-output-dir|-destino-dir|-destino)
                        DESTINO_DIR="$opt_value"
                        if [ -d "$DESTINO_DIR" ]; then
                                fc_log "Diretório de destino existe: '$DESTINO_DIR'"
                        else
                                fc_log "Diretório de destino não existe: '$DESTINO_DIR'"
                                fc_criar_diretorio "$DESTINO_DIR"
                                if [ $? -ne 0 ]; then
                                    fc_log "[ERRO] Falha ao criar diretório: $DESTINO_DIR pois não existe!"
                                    return 1
                                fi
                        fi
                        ;;
				-dirsql|-origemsql|-base-dir-sql|-basedirsql|-base_dir_sql)
                        BASE_DIR_SQL="$opt_value"
                        if [ -d "$BASE_DIR_SQL" ]; then
                                fc_log "Diretório base SQL existe: '$BASE_DIR_SQL'"
                        else
                                fc_log "ERRO: Diretório base SQL não existe: '$BASE_DIR_SQL'"
                                return 1
                        fi                        
                        ;;
				-outfile|-outputfile|-output-file|-saida-arquivo-destino|-saida-arquivo|-saidaarquivo)
                        case "$opt_value" in
                                ""|*/*|*\\*|*$'\n'*|*$'\r'*|*\"*|*[[:space:]]*)
                                        fc_log "[ERRO] Nome de arquivo de saída inválido: $opt_value"
                                        return 1
                                        ;;
                        esac
                        SAIDA_ARQUIVO_DESTINO="$opt_value"
                        FLAG_SAIDA_ARQUIVO_DESTINO_DEFINIDO=1
                        ;;
				-sql|-sql-file|-sqlfile|-filesql)
                        case "$opt_value" in
                                ""|*/*|*\\*|*$'\n'*|*$'\r'*|*\"*|*[[:space:]]*)
                                        fc_log "[ERRO] Nome de arquivo SQL inválido: $opt_value"
                                        return 1
                                        ;;
                        esac
                        NOME_ARQUIVO_SQL="$opt_value"
                        FLAG_NOME_ARQUIVO_SQL_DEFINIDO=1
                        ;;
				-cx|-conexao|-cxoracle|-conexao-oracle|-conexao_oracle|-conexaooracle)
                        BD_CONN="$opt_value"
                        ;;
                -st|-strict-tags|-stricttags|-strict_tags)
                        case "$(printf '%s' "$opt_value" | tr '[:lower:]' '[:upper:]')" in
                                1|S|SIM|T|TRUE)
                                        STRICT_TAGS=1
                                        ;;
                                0|N|NAO|NÃO|F|FALSE)
                                        STRICT_TAGS=0
                                        ;;
                                *)
                                        fc_log "[ERRO] Valor inválido para strict-tags: '$opt_value'. Use S ou N."
                                        return 1
                                        ;;
                        esac
                        ;;
                -debug)
                        case "$(printf '%s' "$opt_value" | tr '[:lower:]' '[:upper:]')" in
                                1|S|SIM|T|TRUE|YES) DEBUG_SQL=1 ;;
                                0|N|NAO|NÃO|F|FALSE|NO) DEBUG_SQL=0 ;;
                                *)
                                        fc_log "[ERRO] Valor inválido para debug: '$opt_value'. Use S ou N."
                                        return 1
                                        ;;
                        esac
                        ;;
                -compress|-zip)
                        case "$(printf '%s' "$opt_value" | tr '[:lower:]' '[:upper:]')" in
                            1|S|SIM|T|TRUE|YES)
                                COMPRESS_CSV="S"
                                ;;
                            0|N|NAO|NÃO|F|FALSE|NO)
                                COMPRESS_CSV="N"
                                ;;
                            *)
                                fc_log "[ERRO] Valor inválido para compress: '$opt_value'. Use S ou N."
                                return 1
                                ;;
                        esac
                        ;;
				-kp|-keep-original|-keep)
                        case "$(printf '%s' "$opt_value" | tr '[:lower:]' '[:upper:]')" in
                            1|S|SIM|T|TRUE|YES)
                                MANTER_ARQUIVO_ORIGINAL="S"
                                ;;
                            0|N|NAO|NÃO|F|FALSE|NO)
                                MANTER_ARQUIVO_ORIGINAL="N"
                                ;;
                            *)
                                fc_log "[ERRO] Valor inválido para keep-original: '$opt_value'. Use S ou N."
                                return 1
                                ;;
                        esac
                        ;;
				-dl|-delimiter|-delim|-delimitador)
                    # Valida se tem apenas 1 caractere (suporte a UTF-8)
                    local delim_length=$(printf '%s' "$opt_value" | LC_ALL=C.UTF-8 wc -m | tr -d ' ')
                    if [ "$delim_length" -ne 1 ]; then
                        fc_log "[ERRO] O delimitador deve ter apenas 1 caractere: '$opt_value'"
                        fc_log "Use um único caractere como: '|'|';'|','|'|'|etc."
                        return 1
                    fi
                    DELIMITADOR="$opt_value"
                    fc_log "Delimitador definido como: '$DELIMITADOR'"
                    ;;
                -nls-lang)
                        NLS_LANG="$opt_value"
                        export NLS_LANG="$NLS_LANG"
                        export NLS_DATE_FORMAT="YYYY-MM-DD HH24:MI:SS"
                        export NLS_TIMESTAMP_FORMAT="YYYY-MM-DD HH24:MI:SS.FF"
                        fc_log "NLS_LANG definido como: '$NLS_LANG'"
                        ;;
                -tipo-sql|-tipo-plsql|-tipo-sql-plsql)
                        fc_log "Processando opção de tipo SQL/PLSQL: '$opt_value'"
                        local opt_value_upper
                        opt_value_upper="$(printf '%s' "$opt_value" | tr '[:lower:]' '[:upper:]')"
                        opt_value_upper="${opt_value_upper//_/}"
                        opt_value_upper="${opt_value_upper// /}"
                        case "$opt_value_upper" in
                            SQL)
                                FLAG_SQL_PLSQL="SQL"
                                ;;
                            PLSQL)
                                FLAG_SQL_PLSQL="PLSQL"
                                ;;
                            *)
                                fc_log "[ERRO] Valor inválido para tipo: '$opt_value_upper'. Use SQL ou PLSQL."
                                return 1
                                ;;
                        esac
                        fc_log "Tipo de SQL/PLSQL definido como: '$FLAG_SQL_PLSQL'"
                        ;;
                *)
                        LISTA_PARAMETROS+=("$parametro_normalizado")
                        ;;
        esac
        export NOME_ARQUIVO_SQL BD_CONN STRICT_TAGS DEBUG_SQL FLAG_NOME_ARQUIVO_SQL_DEFINIDO FLAG_SAIDA_ARQUIVO_DESTINO_DEFINIDO DESTINO_DIR SAIDA_ARQUIVO_DESTINO BASE_DIR_SQL COMPRESS_CSV MANTER_ARQUIVO_ORIGINAL DELIMITADOR NLS_LANG FLAG_SQL_PLSQL
        return 0
}

fc_processa_argumentos_linha_comando() {
        ###############################################################
        # fc_processa_argumentos_linha_comando
        # Processa ajuda|seleção do prefixo de arquivos e pares de opções.
        #
        # Parâmetros:
        #   $@ - Todos os argumentos da linha de comando
        #
        # Retorno:
        #   0 - Pares de opções processados para execução SQL direta
        #   100 - Argumento é ajuda (-h ou --help)
        #   200 - Nenhum argumento fornecido
        #   210 - Prefixo de arquivos definido com -input ou --input
        ###############################################################
        if [ $# -eq 0 ]; then
                # Nenhum argumento fornecido|usa default
                fc_log "Nenhum argumento fornecido."
                return 200
        fi
        FLAG_NOME_ARQUIVO_SQL_DEFINIDO=0
        FLAG_SAIDA_ARQUIVO_DESTINO_DEFINIDO=0
        LISTA_PARAMETROS=()
        local primeiro_arg
        primeiro_arg="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
        primeiro_arg="${primeiro_arg// /}" # Remove todos os espaços
        local segundo_arg="${2-$NOME_INICIAL_ARQUIVO_PADRAO}"
        segundo_arg="${segundo_arg// /}" # Remove todos os espaços
        # Verifica se é pedido de ajuda
        if [ "$primeiro_arg" = "-h" ] || [ "$primeiro_arg" = "--help" ]; then
                fc_log "USO DO SCRIPT:"
                fc_log "  ${SCRIPT_NAME}"
                fc_log "  ${SCRIPT_NAME} -input [PREFIXO_ARQUIVO]"
                fc_log "  ${SCRIPT_NAME} -config [PREFIXO_ARQUIVO]"
                fc_log "  ${SCRIPT_NAME} -sql ARQUIVO.sql [-cx USUARIO/SENHA@BANCO] [-chave valor ...]"
                fc_log ""
                fc_log "DESCRIÇÃO:"
                fc_log "  Executa SQL parametrizado no Oracle diretamente ou a partir de arquivos .ini."
                fc_log ""
                fc_log "OPÇÕES:"
                fc_log "  -input|--input | --inputs | -config | --config | --configs [PREFIXO]  Processa arquivos PREFIXO*.ini"
                fc_log "                                     Padrão: ${NOME_INICIAL_ARQUIVO_PADRAO}"
                fc_log "  -sql|--sql ARQUIVO.sql            Define o arquivo SQL a executar"
                fc_log "  -cx|--conexao CONEXAO             Define a conexão Oracle"
                fc_log "  -debug S|N                          Exibe ou oculta o SQL gerado no log"
                fc_log "  -strict-tags S|N                    Rejeita tags não substituídas"
                fc_log "  -compress S|N                      Comprime CSV em ZIP (padrão Windows)"
                fc_log "  -keep-original S|N                 Mantém original após compressão"
                fc_log "  -delimiter CARACTERE               Define delimitador do CSV (padrão: |)"
                fc_log "  -chave valor                       Substitui [chave] no SQL"
                fc_log "  -h|--help                          Exibe esta ajuda"
                fc_log "  -tipo-sql|-tipo-plsql|-tipo-sql-plsql           Define o tipo de SQL a ser executado"
                fc_log ""
                fc_log ""
                return 100
        fi
        if [ "$primeiro_arg" = "-input" ] || [ "$primeiro_arg" = "--input" ] || [ "$primeiro_arg" = "--inputs" ] || [ "$primeiro_arg" = "-config" ] || [ "$primeiro_arg" = "--config" ] || [ "$primeiro_arg" = "--configs" ]; then
                fc_log "Prefixo definido para busca de arquivos .ini: $segundo_arg"
                if [ -z "$segundo_arg" ]; then
                        fc_log "[ERRO] Prefixo de arquivo não fornecido após 'input' ou 'config'."
                        return 1
                fi
                NOME_INICIAL_ARQUIVO="$segundo_arg"
                export NOME_INICIAL_ARQUIVO
                TIPO_CTL="input"
                if [ "$primeiro_arg" = "-config" ] || [ "$primeiro_arg" = "--config" ] || [ "$primeiro_arg" = "--configs" ]; then
                        TIPO_CTL="config"
                        fc_log "Tipo de controle definido como 'config'"
                fi        
                export TIPO_CTL
                return 210
        fi
        # Leitura dos parâmetros repassados diretamente ao script (sobrepõem o arquivo).
        # Todos os argumentos devem ser informados em pares: parâmetro e valor.
        if [ "$#" -gt 0 ]; then
                if [ $(( $# % 2 )) -ne 0 ]; then
                        fc_log "[ERRO] Os parâmetros da linha de comando devem ser informados em pares: -p1 valor -p2 valor2"
                        return 1
                fi
                fc_log "Extraindo parâmetros informados na linha de comando"
                local indice_arg=0
                while [ "$#" -gt 0 ]; do
                        indice_arg=$((indice_arg + 1))
                        if ! fc_processa_parametro "Argumento" "$indice_arg" "$1 $2"; then
                                fc_log "[ERRO] Falha ao processar argumento ${indice_arg}: '$1'"
                                return 1
                        fi
                        shift 2
                done
                if [ "${#LISTA_PARAMETROS[@]}" -gt 0 ]; then
                        fc_log "Parâmetros de substituição fornecidos na linha de comando:"
                        for p in "${LISTA_PARAMETROS[@]}"; do
                                fc_log "  ${p%%;*}"
                        done
                else
                        fc_log "Nenhum parâmetro de substituição foi fornecido."
                fi
                if [ "$FLAG_NOME_ARQUIVO_SQL_DEFINIDO" -eq 1 ]; then
                        fc_log "Arquivo SQL definido: $NOME_ARQUIVO_SQL"
                else
                        fc_log "[ERRO] Nenhum arquivo SQL definido. O script não executará SQL."
                        return 1
                fi
        fi              
        return 0
}

fc_processa_argumentos_linha_arquivo() {
        #######################################################################
        # fc_processa_argumentos_linha_arquivo
        # Processa argumentos lidos de um arquivo de parâmetros.
        # Cada linha do arquivo é tratada como um argumento|podendo conter
        # comentários|espaços em branco e diferentes formatos de chave-valor.
        #
        # Parâmetros:
        #   $1 - arquivo_diretorio: Caminho completo do arquivo de parâmetros
        #
        # Retorno:
        #   0 - Sucesso (todos os parâmetros processados)
        #   1 - Erro (arquivo não encontrado|vazio ou falha no processamento)
        ####################################################################### 

        local arquivo_diretorio="$1"

        if [ -z "$arquivo_diretorio" ]; then
                # Verifica se o caminho do arquivo não foi informado ou está vazio.
                fc_log "[ERRO] Caminho do arquivo de parâmetros não informado."
                # Registra o erro para o log.
                return 1
                # Interrompe a função indicando falha.
        fi
        # Encerra a validação do caminho vazio.
        if [ ! -f "$arquivo_diretorio" ]; then
                # Verifica se o caminho informado não corresponde a um arquivo regular existente.
                fc_log "[ERRO] Arquivo de parâmetros não encontrado: $arquivo_diretorio"
                # Registra o caminho do arquivo ausente.
                return 1
                # Interrompe a função indicando falha.
        fi
        # Encerra a validação da existência do arquivo.
        if [ ! -s "$arquivo_diretorio" ]; then
                # Verifica se o arquivo existe|mas não contém dados.
                fc_log "[ERRO] Arquivo de parâmetros está vazio: $arquivo_diretorio"
                # Registra o caminho do arquivo vazio.
                return 1
                # Interrompe a função indicando falha.
        fi
        # Encerra a validação do conteúdo do arquivo.
        ###############################################################
        # Separa visualmente a etapa de validações da inicialização dos valores padrão.
        # O bloco abaixo zera o estado do processamento atual para evitar que um
        # arquivo .ini anterior ou uma execução direta influencie o próximo arquivo.
        NOME_ARQUIVO_SQL="${SCRIPT_NAME_NO_EXT}.sql" # Nome do arquivo SQL a ser executado
        BASE_DIR_SQL="${BASE_DIR_SQL_PADRAO}"
        SAIDA_ARQUIVO_DESTINO="${NOME_ARQUIVO_SQL}.csv"
        DESTINO_DIR="${BASE_DIR_OUTPUT}" # Diretório de destino padrão|caso não seja especificado
        STRICT_TAGS=0
        DEBUG_SQL=0
        COMPRESS_CSV="N"
        MANTER_ARQUIVO_ORIGINAL="N"
        DELIMITADOR=';'
        BD_CONN=""
        FLAG_SQL_PLSQL="SQL"
        FLAG_NOME_ARQUIVO_SQL_DEFINIDO=0
        FLAG_SAIDA_ARQUIVO_DESTINO_DEFINIDO=0
        # Cria uma lista vazia para armazenar os parâmetros processados.
        LISTA_PARAMETROS=() # Inicializa lista de parâmetros como vazia
        # Exporta as variáveis para que também estejam disponíveis a processos descendentes.
        export FLAG_NOME_ARQUIVO_SQL_DEFINIDO FLAG_SAIDA_ARQUIVO_DESTINO_DEFINIDO NOME_ARQUIVO_SQL STRICT_TAGS DEBUG_SQL DESTINO_DIR SAIDA_ARQUIVO_DESTINO BASE_DIR_SQL COMPRESS_CSV MANTER_ARQUIVO_ORIGINAL DELIMITADOR BD_CONN FLAG_SQL_PLSQL
        export NLS_LANG=AMERICAN_AMERICA.AL32UTF8
        export NLS_DATE_FORMAT="YYYY-MM-DD HH24:MI:SS"
        export NLS_TIMESTAMP_FORMAT="YYYY-MM-DD HH24:MI:SS.FF"
        # Inicializa o contador de argumentos processados.
        local indice_arg=0
        # Reserva uma variável local para o argumento sem o caractere de retorno de carro.
        local argumento
        # Reserva uma variável local para cada linha lida do arquivo.
        local linha_bruta
        # Lê o arquivo linha a linha|preservando espaços e caracteres especiais.
        while IFS= read -r linha_bruta || [ -n "$linha_bruta" ]; do
                # Remove um eventual caractere CR no final da linha|comum em arquivos Windows (CRLF).
                # Remove caracteres de retorno de carro (\r) da linha bruta
                argumento="${linha_bruta%$'\r'}"
                # Ignora linhas vazias depois da remoção do caractere CR.
                # Pula para próxima iteração se a linha ficar vazia após limpeza
                [ -n "$argumento" ] || continue
                # Incrementa o índice lógico do argumento atual.
                indice_arg=$((indice_arg + 1))
                # Envia a origem|a posição e o valor do argumento para a rotina de processamento.
                # Verifica se a rotina solicitou interrupção|por exemplo ao processar ajuda ou erro.
                if ! fc_processa_parametro "Linha" "$indice_arg" "$argumento"; then
                        # Interrompe o processamento e propaga o código de falha.
                        return 1
                        # Retorna imediatamente sem ler as linhas restantes.
                fi
                # Continua a leitura quando o processamento do argumento foi aceito.
        done < "$arquivo_diretorio"
        if [ "${#LISTA_PARAMETROS[@]}" -gt 0 ]; then
                fc_log "Parâmetros de substituição lidos do arquivo: $arquivo_diretorio"
                for p in "${LISTA_PARAMETROS[@]}"; do
                        fc_log "  ${p%%;*}"
                done
        else
                fc_log "Nenhum parâmetro de substituição encontrado no arquivo: $arquivo_diretorio"
        fi
        if [ "$FLAG_NOME_ARQUIVO_SQL_DEFINIDO" -eq 1 ]; then
                fc_log "Arquivo SQL definido: $NOME_ARQUIVO_SQL"
        else
                fc_log "[ERRO] Nenhum arquivo SQL definido. O script não executará SQL."
                return 1
        fi
        fc_log "Arquivo de parâmetros processado com sucesso: $arquivo_diretorio (linhas lidas: $indice_arg)"
        # O laço acima também processa a última linha quando ela não termina
        # com newline; chegar aqui indica que todas as linhas foram aceitas.
        return 0
}

fc_busca_e_copia_arquivos_ini_para_output() {
        ###############################################################
        # fc_busca_e_copia_arquivos_ini_para_output
        # Busca arquivos .ini com o prefixo NOME_INICIAL_ARQUIVO
        # no diretório DATA_DIR|armazena nomes em INPUTS e copia cada arquivo
        # para BASE_DIR_OUTPUT.
        #
        # Padrão de busca: ${NOME_INICIAL_ARQUIVO}* (ex: RB_RUN_EXECUTOR_RELATORIO_CSV_SQL*.ini)
        #
        # Retorno:
        #   0 - Sucesso (nenhum arquivo encontrado ou todos copiados)
        #   1 - Erro com algum arquivo
        #
        # Variáveis globais utilizadas:
        #   DATA_DIR - Diretório de entrada
        #   BASE_DIR_OUTPUT - Diretório de saída
        #   NOME_INICIAL_ARQUIVO - Prefixo do padrão de busca (ex: RB_RUN_EXECUTOR_RELATORIO_CSV_SQL*.ini)
        #   INPUTS - Array com nomes de arquivos (atualizado pela função)
        ###############################################################
        local arquivo_encontrado=""
        local nome_arquivo=""
        local contador=0
        INPUTS=()
        if [ -z "$TIPO_CTL" ]; then
                fc_log "[ERRO] Tipo de controle não definido. Use -input ou -config."
                return 1
        fi
        if [ "$TIPO_CTL" = "config" ]; then
                fc_log "Tipo de controle definido como 'config'"
        fi
        if [ "$TIPO_CTL" = "input" ]; then
                fc_log "Tipo de controle definido como 'input'"
        fi
        local diretorio_entrada="$DATA_DIR"
        if [ "$TIPO_CTL" = "config" ]; then
                fc_log "Tipo de controle definido como 'config' : usando diretório de configuração $DATA_CONF"
                diretorio_entrada="$DATA_CONF"
        fi
        if [ "$TIPO_CTL" = "input" ]; then
                fc_log "Tipo de controle definido como 'input' : usando diretório de entrada $DATA_DIR"
                diretorio_entrada="$DATA_DIR"
        fi
        
        if [ ! -d "$diretorio_entrada" ]; then
                fc_log "[ALERTA] Diretório de entrada não encontrado: $diretorio_entrada"
                return 0
        fi
        if [ ! -d "$BASE_DIR_OUTPUT" ]; then
                fc_log "[ALERTA] Diretório de saída não encontrado: $BASE_DIR_OUTPUT"
                return 1
        fi        
        fc_log "Buscando arquivos ${NOME_INICIAL_ARQUIVO}*.ini em $diretorio_entrada (ignorando maiúsculas/minúsculas)"
        while IFS= read -r -d '' arquivo_encontrado; do
                [ -n "$arquivo_encontrado" ] || continue
                nome_arquivo="$(basename "$arquivo_encontrado")"
                if [ "$ARQUIVO_CONFIGURACAO_LOCAL" == "$arquivo_encontrado" ]; then
                        fc_log "[ALERTA] Ignorando arquivo de configuração local: $arquivo_encontrado"
                        continue
                fi
                if [ "$SCRIPT_NAME" == "$nome_arquivo" ]; then
                        fc_log "[ALERTA] Ignorando arquivo com o mesmo nome do script: $arquivo_encontrado"
                        continue
                fi
                if ! cp -f -- "$arquivo_encontrado" "$BASE_DIR_OUTPUT/"; then
                        fc_log "[ERRO] Falha ao copiar arquivo: $arquivo_encontrado -> $BASE_DIR_OUTPUT"
                        return 1
                fi
                fc_log "Arquivo copiado para saída: $nome_arquivo"
                INPUTS+=("$nome_arquivo")
                contador=$((contador + 1))
                if [ "$TIPO_CTL" = "input" ]; then
                        if ! rm -f -- "$arquivo_encontrado"; then
                                fc_log "[ERRO] Falha ao remover arquivo do diretório de entrada: $arquivo_encontrado"
                                return 1
                        else
                                fc_log "Arquivo removido do diretório de entrada: $arquivo_encontrado"
                        fi
                fi
        done < <(find "$diretorio_entrada" -maxdepth 1 -type f -iname "${NOME_INICIAL_ARQUIVO}*" -print0 | sort -zf)
        if [ "$contador" -eq 0 ]; then
                fc_log "[ALERTA] Nenhum arquivo ${NOME_INICIAL_ARQUIVO}* encontrado em $diretorio_entrada"
        else
                fc_log "Quantidade de arquivos ${NOME_INICIAL_ARQUIVO}* encontrados: $contador"
        fi
        return 0
}

fc_imprimir_local_arquivo(){
        ###############################################################
        # fc_imprimir_local_arquivo
        # Registra no log o caminho|o diretório e o nome de um arquivo.
        # Não altera o arquivo nem falha a execução quando ele não existe;
        # nesse caso|registra apenas a ausência.
        #
        # Parâmetros:
        #   $1 - arquivo: Caminho completo do arquivo a localizar
        #
        # Retorno:
        #   0 - Sempre retorna sucesso após registrar a informação
        ###############################################################
        local arquivo="$1"
        fc_log_separador
        if [ -f "$arquivo" ]; then
                fc_log "O arquivo está localizado em: $arquivo"
                fc_log "[DOWLOADER_DIRETORIO]: $(dirname "$arquivo")"
                fc_log "[DOWLOADER_NOME]: $(basename "$arquivo")"
        else
                fc_log "O arquivo não foi encontrado: $arquivo"
        fi
        fc_log_separador
}

fc_garantir_terminador_sql() {
    ###############################################################
    # fc_garantir_terminador_sql
    # Garante que o arquivo SQL/PLSQL termine com o terminador
    # esperado pelo SQL*Plus:
    #   - SQL   : termina com ';' (executa o buffer)
    #   - PLSQL : termina com '/' (executa bloco anônimo)
    #
    # IMPORTANTE: o SQL*Plus interpreta uma linha em branco como
    # fim de comando. Se houver linha em branco entre a última
    # linha do SQL e o terminador, o SQL*Plus NÃO executa o SQL
    # e imprime o buffer no SPOOL (CSV fica com o próprio SQL).
    #
    # Esta função:
    #   1) Remove TODAS as linhas em branco do final do arquivo
    #      (usa somente sed, sem depender de awk/perl).
    #   2) Garante exatamente UM newline no final.
    #   3) Adiciona o terminador correto SEM newline extra antes.
    #
    # Parâmetros:
    #   $1 - arquivo: Caminho do arquivo .sql/.out.sql já com tags substituídas
    #   $2 - tipo:    "SQL" ou "PLSQL" (default: SQL)
    #
    # Retorno:
    #   0 - Terminador garantido (já existia ou foi adicionado)
    #   1 - Erro (arquivo inexistente, vazio, ou falha de escrita)
    ###############################################################
    local arquivo="${1:-}"
    local tipo="${2:-SQL}"

    if [ -z "$arquivo" ]; then
        fc_log "[ERRO] fc_garantir_terminador_sql: arquivo não informado."
        return 1
    fi
    if [ ! -f "$arquivo" ]; then
        fc_log "[ERRO] fc_garantir_terminador_sql: arquivo não existe: $arquivo"
        return 1
    fi
    if [ ! -s "$arquivo" ]; then
        fc_log "[ERRO] fc_garantir_terminador_sql: arquivo vazio: $arquivo"
        return 1
    fi

    # ------------------------------------------------------------------
    # PASSO 1: remove TODAS as linhas em branco (ou só espaços) do FINAL.
    # Usa somente sed — portável em qualquer ambiente que já tem o resto
    # do script funcionando (o script já usa sed em outras partes).
    #
    # O comando abaixo é o idiom clássico para remover linhas vazias
    # do final de um arquivo com sed:
    #   :a                 - label 'a'
    #   /^\n*$/{$d;N;ba}   - se a linha é vazia E é a última ($), apaga e
    #                        reinicia; senão, junta com a próxima (N)
    #                        e volta para 'a' (ba)
    # ------------------------------------------------------------------
    local tmp="${arquivo}.sem_branco_final.tmp"
    sed -e :a -e '/^[[:space:]]*$/{$d;N;ba' -e '}' "$arquivo" > "$tmp" 2>/dev/null

    if [ ! -s "$tmp" ]; then
        rm -f "$tmp"
        fc_log "[ERRO] fc_garantir_terminador_sql: falha ao limpar linhas em branco finais de $arquivo"
        return 1
    fi
    mv -f "$tmp" "$arquivo"

    # ------------------------------------------------------------------
    # PASSO 2: descobre o último caractere significativo
    # (ignora \r, \n e espaços).
    # ------------------------------------------------------------------
    local conteudo_sem_fim
    conteudo_sem_fim="$(tr -d '\r\n[:space:]' < "$arquivo")"
    if [ -z "$conteudo_sem_fim" ]; then
        fc_log "[ERRO] fc_garantir_terminador_sql: arquivo sem conteúdo útil: $arquivo"
        return 1
    fi
    local ultimo_char="${conteudo_sem_fim: -1}"

    # ------------------------------------------------------------------
    # PASSO 3: garante exatamente UM newline no final.
    # O sed do passo 1 já deixou o arquivo terminando em \n.
    # Se por algum motivo não tiver, adiciona.
    # ------------------------------------------------------------------
    if [ -n "$(tail -c 1 "$arquivo" 2>/dev/null)" ]; then
        printf '\n' >> "$arquivo" || {
            fc_log "[ERRO] fc_garantir_terminador_sql: falha ao adicionar newline em $arquivo"
            return 1
        }
        fc_log "[DEBUG] Newline adicionado ao final de: $arquivo"
    fi

    # ------------------------------------------------------------------
    # PASSO 4: adiciona o terminador correto SEM newline antes dele.
    # O newline já foi garantido no passo 3, então o terminador
    # fica imediatamente depois da última linha válida:
    #
    #   tipo_faturamento
    #   ;
    #
    # E NÃO:
    #
    #   tipo_faturamento
    #   <-- linha vazia (o que quebra o SQL*Plus)
    #   ;
    # ------------------------------------------------------------------
    case "$tipo" in
        PLSQL)
            if [ "$ultimo_char" = "/" ]; then
                fc_log "[DEBUG] Terminador '/' já presente no final do PL/SQL: $arquivo"
                return 0
            fi
            fc_log "[ALERTA] PL/SQL sem '/' no final. Adicionando automaticamente: $arquivo"
            printf '/\n' >> "$arquivo" || {
                fc_log "[ERRO] fc_garantir_terminador_sql: falha ao adicionar '/' em $arquivo"
                return 1
            }
            ;;
        SQL|*)
            if [ "$ultimo_char" = ";" ] || [ "$ultimo_char" = "/" ]; then
                fc_log "[DEBUG] Terminador '$ultimo_char' já presente no final do SQL: $arquivo"
                return 0
            fi
            fc_log "[ALERTA] SQL sem ';' ou '/' no final. Adicionando ';' automaticamente: $arquivo"
            printf ';\n' >> "$arquivo" || {
                fc_log "[ERRO] fc_garantir_terminador_sql: falha ao adicionar ';' em $arquivo"
                return 1
            }
            ;;
    esac
    return 0
}

fc_executa_sql() {
        ###############################################################
        # fc_executa_sql
        # Executa um script SQL/PL/SQL em ambiente Oracle usando sqlplus.
        # O fluxo inclui cópia do script, substituição de tags, validação
        # de diretório, execução, leitura do log e tratamento do CSV gerado.
        #
        # Retorno:
        #   0 - Sucesso na execução do script
        #   1 - Falha na execução do script ou na geração dos artefatos
        ###############################################################
        local extensao_saida_arquivo="csv"
        if [ "$FLAG_SAIDA_ARQUIVO_DESTINO_DEFINIDO" -eq 0 ]; then
                SAIDA_ARQUIVO_DESTINO="${NOME_ARQUIVO_SQL}.${extensao_saida_arquivo}"
                export SAIDA_ARQUIVO_DESTINO
        else
                extensao_saida_arquivo="${SAIDA_ARQUIVO_DESTINO##*.}"
        fi
        local sem_extensao_saida_arquivo="$(echo "${SAIDA_ARQUIVO_DESTINO%.*}" | tr -d '[:space:]')"
        local current_datetime="$(date +%Y%m%d%H%M%S)_$((RANDOM % 1001))"
        local sql_file="${BASE_DIR_SQL}/${NOME_ARQUIVO_SQL}"
        local sql_log_file="${BASE_DIR_OUTPUT}/${current_datetime}.log"
        local sql_file_output="${BASE_DIR_OUTPUT}/${current_datetime}.sql"
        # local sql_file_output="${BASE_DIR_OUTPUT}/${NOME_ARQUIVO_SQL}_${current_datetime}.out.sql"
        local sql_export_file="${DESTINO_DIR}/${sem_extensao_saida_arquivo}_${current_datetime}.${extensao_saida_arquivo}"
        fc_log "[DEBUG] Flags de execução: strict_tags=$STRICT_TAGS | debug=$DEBUG_SQL | compress=$COMPRESS_CSV | keep_original=$MANTER_ARQUIVO_ORIGINAL | tipo_sql=$FLAG_SQL_PLSQL"
        fc_log "Verificando o arquivo SQL: $sql_file"
        if [ ! -f "$sql_file" ]; then
                if [ -f "${SCRIPT_DIR}/${NOME_ARQUIVO_SQL}" ]; then
                        sql_file="${SCRIPT_DIR}/${NOME_ARQUIVO_SQL}"
                        fc_log "Arquivo SQL encontrado em SCRIPT_DIR: $sql_file"
                elif [ -f "${DATA_DIR}/${NOME_ARQUIVO_SQL}" ]; then
                        sql_file="${DATA_DIR}/${NOME_ARQUIVO_SQL}"
                        fc_log "Arquivo SQL encontrado em DATA_DIR: $sql_file"
                else
                        fc_log "[ERRO] Arquivo SQL não encontrado: $sql_file"
                        return 1
                fi
        fi
        if [ ! -s "$sql_file" ]; then
                fc_log "[ERRO] Arquivo SQL está vazio: $sql_file"
                return 1
        fi
        fc_log "Arquivo SQL original: $sql_file copiado para: $sql_file_output"
        cp "$sql_file" "$sql_file_output" 2>/dev/null
        if [ $? -ne 0 ] || [ ! -f "$sql_file_output" ]; then
                fc_log "[ERRO] Falha ao copiar SQL de $sql_file para $sql_file_output."
                return 1
        fi
        cp "$sql_file" "$sql_file_output.original.bak.$current_datetime" 2>/dev/null
        if [ $? -ne 0 ] || [ ! -f "$sql_file_output.original.bak.$current_datetime" ]; then
                fc_log "[ERRO] Falha ao copiar SQL de $sql_file para $sql_file_output.original.bak.$current_datetime."
                return 1
        fi
        fc_log "Cópia do SQL realizada: $sql_file_output"
        # Substitui tags no SQL copiado|iterando sobre LISTA_PARAMETROS no formato [chave];valor.
        if [ "${#LISTA_PARAMETROS[@]}" -gt 0 ]; then
                local parametro tag_bruta valor_bruto tag_escapada valor_escapado
                fc_log "[DEBUG] Aplicando ${#LISTA_PARAMETROS[@]} substituições de tags no script SQL."
                for parametro in "${LISTA_PARAMETROS[@]}"; do
                        tag_bruta="${parametro%%;*}"
                        valor_bruto="${parametro#*;}"
                        fc_log "Substituindo tag $tag_bruta no SQL copiado."
                        if ! grep -F -q "$tag_bruta" "$sql_file_output"; then
                                # rm -f "${sql_file_output}.bak"
                                fc_log "[ERRO] Tag informada não encontrada no SQL: $tag_bruta"
                                return 1
                        fi
                        # Escapa metacaracteres de regex e o delimitador do sed.
                        tag_escapada="$(printf '%s' "$tag_bruta" | sed 's/[][\\.^$*|]/\\&/g')"
                        fc_log "Tag escapada para substituição no sed: $tag_escapada"
                        valor_escapado="$(printf '%s' "$valor_bruto" | sed -e 's/\\/\\\\/g' -e 's/|/\\|/g' -e 's/&/\\&/g' -e ':a;N;$!ba;s/\n/\\n/g')"
                        sed -i -e "s|${tag_escapada}|${valor_escapado}|g" "$sql_file_output"
                        if [ $? -ne 0 ]; then
                                fc_log "[ERRO] Falha ao substituir tag $tag_bruta no SQL copiado: $sql_file_output"
                                return 1
                        fi
                        # rm -f "${sql_file_output}.bak"
                        fc_log "Tag substituída no SQL copiado: $tag_bruta"
                done
        fi
        if [ "$STRICT_TAGS" -eq 1 ]; then
                fc_log "Verificando tags estritas no SQL copiado: $sql_file_output"
                # Aceita tags com letras maiúsculas ou minúsculas e underscore, que são os
                # formatos típicos usados pela aplicação após normalização das chaves.
                fc_log "[DEBUG] Strict-tags ativado: validando se ainda restam placeholders no SQL gerado."
                if grep -E -q '\[[[:alpha:]_][[:alnum:]_]*\]' "$sql_file_output"; then
                        fc_log "[ERRO] O SQL gerado ainda contém tags sem substituição:"
                        grep -E -o '\[[[:alpha:]_][[:alnum:]_]*\]' "$sql_file_output" | sort -u | while IFS= read -r tag_pendente; do
                                fc_log "  $tag_pendente"
                        done
                        return 1
                fi
        fi
        fc_log "Substituição de tags concluída no SQL copiado: $sql_file_output"
        if [ "$FLAG_SQL_PLSQL" = "SQL" ]; then
                # Valida o delimitador antes de executar
                fc_log "Validando delimitador: $DELIMITADOR"
                local delim_length=$(printf '%s' "$DELIMITADOR" | wc -m | tr -d ' ')
                if [ "$delim_length" -ne 1 ]; then
                    fc_log "[ERRO] Delimitador inválido: '$DELIMITADOR' (deve ter 1 caractere)"
                    fc_log "Usando delimitador padrão '|'"
                    DELIMITADOR='|'
                    export DELIMITADOR
                fi
        fi
        fc_log "Executando SQL para exportação: $sql_file_output"
        fc_log "Arquivo CSV de saída: $sql_export_file"
        fc_log "Log técnico do SQL*Plus: $sql_log_file"
        fc_log "[DEBUG] Destino final do export: $sql_export_file | base_do_sql: $sql_file"
        if ! fc_validar_espaco_disco "$(dirname "$sql_export_file")"; then
                fc_log "[ERRO] Espaço em disco insuficiente no diretório: $(dirname "$sql_export_file")"
                return 1
        fi
        ### # A regra do terminador '/' vale apenas para PL/SQL.
        ### # SQL simples não exige esse caractere final, e a validação deve ser
        ### # ignorada para evitar falso positivo em scripts de consulta/SELECT.
        ### if [ "$FLAG_SQL_PLSQL" = "PLSQL" ]; then
        ###         local sql_ultimo_caracter_efetivo
        ###         sql_ultimo_caracter_efetivo="$(tr -d '\r\n[:space:]' < "$sql_file_output")"
        ###         if [ -z "$sql_ultimo_caracter_efetivo" ]; then
        ###                 fc_log "[ERRO] Arquivo PL/SQL gerado vazio ou sem conteúdo útil: $sql_file_output"
        ###                 return 1
        ###         fi
        ###         local sql_ultimo_char="${sql_ultimo_caracter_efetivo: -1}"
        ###         if [ "$sql_ultimo_char" != "/" ]; then
        ###                 fc_log "[ALERTA] O arquivo PL/SQL gerado não termina com '/' como último caractere significativo. Ajustando automaticamente: $sql_file_output"
        ###                 printf '\n/\n' >> "$sql_file_output"
        ###                 if [ $? -ne 0 ]; then
        ###                         fc_log "[ERRO] Falha ao inserir o terminador '/' no final do PL/SQL gerado: $sql_file_output"
        ###                         return 1
        ###                 fi
        ###                 fc_log "[DEBUG] Terminador '/' inserido automaticamente."
        ###         else
        ###                 fc_log "[DEBUG] Terminador '/' já presente no final do PL/SQL."
        ###         fi
        ### else
        ###         fc_log "[DEBUG] Modo SQL simples: validação do terminador '/' ignorada."
        ### fi

        # Garante terminador correto antes de chamar o SQL*Plus.
        # - SQL   : precisa terminar com ';' (ou '/') para o buffer ser executado
        # - PLSQL : precisa terminar com '/' para o bloco anônimo ser executado
        # Sem isso, o SPOOL OFF aborta o buffer sem executar e o CSV fica vazio.
        fc_log "[DEBUG] Últimas 5 linhas antes do terminador ($FLAG_SQL_PLSQL):"
        tail -5 "$sql_file_output" | while IFS= read -r linha_dbg; do
                fc_log "  [SQL] $linha_dbg"
        done
        if ! fc_garantir_terminador_sql "$sql_file_output" "$FLAG_SQL_PLSQL"; then
                fc_log "[ERRO] Falha ao garantir terminador ($FLAG_SQL_PLSQL) no arquivo: $sql_file_output"
                return 1
        fi
        # Guarda o diretório atual para restaurar depois
        local cwd_original
        cwd_original="$(pwd)"
        # Navega para o diretório do arquivo .out.sql
        local sql_out_dir
        sql_out_dir="$(dirname "$sql_file_output")"
        local sql_out_base
        sql_out_base="$(basename "$sql_file_output")"
        local log_out_dir
        log_out_dir="$(dirname "$sql_log_file")"
        local log_out_base
        log_out_base="$(basename "$sql_log_file")"
        if ! cd "$sql_out_dir"; then
                fc_log "[ERRO] Falha ao entrar no diretório: $sql_out_dir"
                return 1
        fi
        fc_log "[DEBUG] Diretório de execução: $(pwd)"
        fc_log "[DEBUG] Arquivo a executar: $sql_out_base"
        rm -f "$sql_export_file" "$sql_log_file"
        local status
        if [ "$FLAG_SQL_PLSQL" = "SQL" ]; then
                fc_log "Executando como SQL : $sql_file_output e gerando a saída do arquivo de exportação: $sql_export_file"
                if [ "${DEBUG_SQL:-0}" -eq 1 ]; then
                        fc_log "Conteúdo do SQL gerado: $sql_file_output"
                        while IFS= read -r linha_sql || [ -n "$linha_sql" ]; do
                                fc_log "$linha_sql"
                        done < "$sql_file_output"
                        fc_log "[DEBUG] BD_CONN limpo (mascarado): $(printf '%s' "$BD_CONN" | sed -E 's#^([^/]+)/([^@]+)@#\1/****@#')"
                fi
                # Configura o SQL*Plus para gerar CSV e limitar mensagens interativas.
                sqlplus -silent /nolog > "$log_out_base" 2>&1 << EOF
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
WHENEVER OSERROR EXIT 1 ROLLBACK
CONNECT ${BD_CONN}
SET NEWPAGE NONE
SET PAGESIZE 0
SET ARRAYSIZE 5000
SET ROWPREFETCH 5000
SET LONG 1000000
SET LONGCHUNKSIZE 1000000
SET LINESIZE 32767
SET TRIMSPOOL ON
SET TRIMOUT ON
SET UNDERLINE OFF
SET COLSEP ''
SET TERMOUT OFF
SET FEEDBACK OFF
SET VERIFY OFF
SET ECHO OFF
SET HEADING ON
SET SERVEROUTPUT OFF
SET MARKUP CSV ON DELIMITER "${DELIMITADOR}" QUOTE ON
SPOOL "${sql_export_file}"
@"$sql_out_base"
SPOOL OFF
EXIT SUCCESS
EOF
                status=$?
                echo "SQL*Plus exit status: $status" >> "$log_out_base"
        elif [ "$FLAG_SQL_PLSQL" = "PLSQL" ]; then
                fc_log "Executando como PLSQL : $sql_file_output e gerando a saída do arquivo de exportação: $sql_export_file"
                # Remove \r e espaços do BD_CONN
                # BD_CONN="$(printf '%s' "$BD_CONN" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
                # export BD_CONN
                # fc_log "[DEBUG] BD_CONN limpo (mascarado): $(printf '%s' "$BD_CONN" | sed -E 's#^([^/]+)/([^@]+)@#\1/****@#')"
                # Garante que o arquivo .out.sql termina com / (obrigatório para PL/SQL anônimo)
                if [ -f "$sql_file_output" ]; then
                        local ultima_linha
                        ultima_linha="$(tail -n 1 "$sql_file_output" | tr -d '[:space:]')"
                        if [ "$ultima_linha" != "/" ]; then
                                fc_log "[ALERTA] .out.sql não termina com /. Adicionando automaticamente."
                                printf '\n/\n' >> "$sql_file_output"
                        else
                                fc_log "[DEBUG] .out.sql termina com / corretamente."
                        fi
                fi
                if [ "${DEBUG_SQL:-0}" -eq 1 ]; then
                        fc_log "Conteúdo do SQL gerado: $sql_file_output"
                        while IFS= read -r linha_sql || [ -n "$linha_sql" ]; do
                                fc_log "$linha_sql"
                        done < "$sql_file_output"
                        fc_log "[DEBUG] BD_CONN limpo (mascarado): $(printf '%s' "$BD_CONN" | sed -E 's#^([^/]+)/([^@]+)@#\1/****@#')"
                fi
                ## Com isso:
                ## 
                ## > /dev/null descarta o DBMS_OUTPUT ecoado (que já está no CSV via SPOOL).
                ## 
                ## 2> "$log_out_base" captura stderr (erros do SQL*Plus).
                ## 
                ## O CSV continua sendo gerado corretamente pelo SPOOL.
                ## 
                ## Porém, o PL/SQL procedure successfully completed. é stdout, então ele será descartado com /dev/null. Ótimo — não vai poluir nem o LOG nem o CSV.
                sqlplus -silent /nolog > /dev/null 2> "$log_out_base" << EOF
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
WHENEVER OSERROR EXIT 1 ROLLBACK                
CONNECT ${BD_CONN}
SET SERVEROUTPUT ON SIZE UNLIMITED
SET LINESIZE 32767
SET TRIMSPOOL ON
SET TRIMOUT ON
SET PAGESIZE 0
SET FEEDBACK OFF
SET VERIFY OFF
SET ECHO OFF
SET HEADING OFF
SET MARKUP CSV OFF
SPOOL "${sql_export_file}"
@"$sql_out_base"
SPOOL OFF
EXIT SUCCESS
EOF
                status=$?
                echo "SQL*Plus exit status: $status" >> "$log_out_base"
        else    
                fc_log "[ERRO] Tipo de execução inválido: '$FLAG_SQL_PLSQL'"
                return 1
        fi
        # Volta ao diretório original
        cd "$cwd_original" >/dev/null 2>&1
        # Sempre lê o log primeiro
        if [ ! -f "$sql_log_file" ]; then
                fc_log "[ERRO] O arquivo de log do SQL não foi gerado: $sql_log_file"
                return 1
        fi
        fc_log "LOG do SQL executado: $sql_log_file . Saida do SQL: $status"
        # while IFS= read -r linha_erro || [ -n "$linha_erro" ]; do
        #         fc_log "$linha_erro"
        # done < "$sql_log_file"
        fc_log_separador
        fc_log "Primeiras 10 linhas do arquivo de LOG do SQL:"
        head -10 "$sql_log_file" | while IFS= read -r line; do
            fc_log "  $line"
        done
        fc_log_separador
        fc_log "Últimas 10 linhas do arquivo de LOG do SQL:"
        tail -15 "$sql_log_file" | while IFS= read -r line; do
            fc_log "  $line"
        done
        fc_log_separador
        if grep -E -q '(^|[[:space:]])(ORA-|SP2-|PLS-)[0-9]+' "$sql_log_file" 2>/dev/null; then
                fc_log "[ERRO] Falha na execução do SQL: $sql_file_output (ver log $sql_log_file)"
                return 1
        fi
        if [ ! -f "$sql_export_file" ]; then
                if [ "$FLAG_SQL_PLSQL" = "SQL" ]; then
                        fc_log "[ERRO] O SQL foi executado|mas o arquivo de exportação não foi gerado : $sql_export_file"
                        return 1
                fi
                fc_log "[ALERTA] PL/SQL executado sem gerar arquivo de exportação (esperado para DML puro): $sql_export_file"
        else
                # Remove a mensagem de conclusão do PL/SQL e linhas vazias do CSV
                if [ -f "$sql_export_file" ]; then
                    sed -i '/^PL\/SQL procedure successfully completed\.$/d' "$sql_export_file"
                    sed -i '/^[[:space:]]*$/d' "$sql_export_file"
                    fc_log "Linhas residuais do SQL*Plus removidas do CSV."
                fi
                fc_log_separador
                fc_log "Primeiras 10 linhas do arquivo de exportação:"
                head -10 "$sql_export_file" | while IFS= read -r line; do
                    fc_log "  $line"
                done
                fc_log_separador
                fc_log "Últimas 10 linhas do arquivo de exportação:"
                tail -15 "$sql_export_file" | while IFS= read -r line; do
                    fc_log "  $line"
                done
                fc_log_separador
                fc_verificar_erros_oracle_inicio_fim_arquivo "$sql_export_file"
                if [ $? -ne 0 ]; then
                        fc_log "[ERRO] Falha na execução do SQL: $sql_file_output gerado pelo export $sql_export_file"
                        return 1
                fi
                fc_log_separador
                if [ ! -s "$sql_export_file" ]; then
                        fc_log "O SQL foi executado|mas o arquivo de exportação está vazio: $sql_export_file"
                        fc_log_separador
                        fc_imprimir_local_arquivo "$sql_export_file" 
                        fc_log_separador
                else
                        fc_log "O SQL foi executado e o arquivo de exportação foi gerado : $sql_export_file"
                        fc_log_separador
                        # Só mostra a contagem de linhas se for pequeno
                        # Versão sem contar linhas para arquivos grandes
                        local tamanho_arquivo=$(stat -c%s "$sql_export_file" 2>/dev/null || stat -f%z "$sql_export_file" 2>/dev/null)
                        if [ "$tamanho_arquivo" -lt 1048576 ]; then  # < 1MB
                            local total_linhas=$(wc -l < "$sql_export_file" 2>/dev/null)
                            fc_log "Quantidade de linhas: $total_linhas"
                        else
                            fc_log "Arquivo grande (${tamanho_arquivo} bytes) - contagem de linhas omitida"
                        fi
                        fc_log_separador
                        if [ "$FLAG_SQL_PLSQL" = "SQL" ]; then
                                fc_log "Removendo linha em branco do início do arquivo de exportação|se existir"
                                fc_remover_linha_branco_csv "$sql_export_file"
                                if [ $? -eq 0 ]; then
                                    fc_log "Linha em branco removida com sucesso do início do arquivo de exportação"
                                else
                                    fc_log "[ALERTA] Falha ao remover linha em branco do início do arquivo de exportação"
                                fi
                                fc_log_separador
                        fi
                        # Verifica se a compressão está habilitada (via variável global)
                        if [ "${COMPRESS_CSV:-N}" = "S" ]; then
                            fc_comprimir_arquivo_zip "$sql_export_file" "${MANTER_ARQUIVO_ORIGINAL:-N}"
                            if [ $? -eq 0 ]; then
                                fc_log "Arquivo de exportação comprimido com sucesso no formato ZIP (Windows)"
                                local arquivo_zip="${sql_export_file}.zip"   
                                fc_adicionar_arquivos_gerados "$arquivo_zip"
                                fc_log_separador
                                fc_imprimir_local_arquivo "$arquivo_zip" 
                                fc_log_separador
                            else
                                fc_log "[ALERTA] Falha na compressão do arquivo de exportação|mantendo arquivo original"
                                fc_adicionar_arquivos_gerados "$sql_export_file"
                                fc_log_separador
                                fc_imprimir_local_arquivo "$sql_export_file" 
                                fc_log_separador
                            fi
                        else
                                fc_log_separador
                                fc_imprimir_local_arquivo "$sql_export_file" 
                                fc_adicionar_arquivos_gerados "$sql_export_file"
                                fc_log_separador
                        fi
                        fc_log_separador
                fi
                fc_log_separador
        fi
        if [ $status -ne 0 ]; then
                # rm -f "$sql_export_file"
                fc_log "[ERRO] Falha na execução do SQL: $sql_file_output"
                return 1
        fi        
        if [ -f "$sql_export_file" ]; then
                fc_log "Exportação CSV concluída com sucesso: $sql_export_file"
        elif [ -f "${sql_export_file}.zip" ]; then
                fc_log "Exportação CSV concluída com sucesso (comprimida): ${sql_export_file}.zip"
        else
                fc_log "Execução concluída com sucesso (sem CSV gerado): $NOME_ARQUIVO_SQL"
        fi
        return 0
}

fc_inicio() {
        # Função para iniciar o processo
        ###############################################################
        # fc_inicio
        # Inicializa contexto de execução|valida dependências e registra variáveis principais do processo.
        # Parâmetros:
        #   $@ - Ajuda|seleção de prefixo ou pares de opções para execução direta
        # Retorno: 
        #   0 - Sucesso
        #   1 - Erro crítico
        ###############################################################
        PROCESS_STATUS=0
        # Inicializa variáveis globais|diretórios|timestamps e configurações
        # Retorna erro se houver falha na criação de diretórios críticos
        fc_init_variaveis_globais
        if [ $? -ne 0 ]; then
                PROCESS_STATUS=1
                fc_log "[ERRO] Falha ao inicializar variáveis globais necessárias para o funcionamento do script"
                fc_log "Fim da execução do script. Código de retorno: $PROCESS_STATUS"
                return $PROCESS_STATUS                
        fi
        fc_log_separador
        fc_log "* Diretórios utilizados:"
        fc_log "  - LOGS:  $BASE_DIR_LOG"
        fc_log "  - OUTPUT_DIR: $BASE_DIR_OUTPUT"
        fc_log "  - DATA_DIR:   $DATA_DIR"
        fc_log "  - DATA_CONF:  $DATA_CONF"
        fc_log "* Arquivo de log : ${LOGS_NOME_PADRAO}"
        fc_log "* Data Hora: ${CURRENT_DATE} ${CURRENT_HHMMSS} "
        fc_log "* ID PROCESSO: ${PROCESS_ID} "
        fc_log_separador
        # Processa a ajuda e os argumentos antes de validar dependências externas.
        fc_processa_argumentos_linha_comando "$@"
        local ret_args=$?
        fc_log "* Código de retorno do processamento de argumentos: $ret_args"
        if [ $ret_args -eq 100 ] || [ $ret_args -eq 200 ]; then
                PROCESS_STATUS=0
                fc_log "[DEBUG] Encerrando execução por ajuda ou ausência de argumentos. Retorno: $ret_args"
                fc_log "Fim da execução do script. Código de retorno: $PROCESS_STATUS"
                return $PROCESS_STATUS
        fi
        if [ $ret_args -ne 0 ] && [ $ret_args -ne 210 ]; then
                PROCESS_STATUS=1
                fc_log "[ERRO] Falha no processamento dos argumentos da linha de comando."
                fc_log "[DEBUG] Código de retorno do parser: $ret_args"
                fc_log "Fim da execução do script. Código de retorno: $PROCESS_STATUS"
                return $PROCESS_STATUS
        fi
        fc_log "[DEBUG] Processamento de argumentos concluído com retorno: $ret_args"
        # Checagem de dependências essenciais
        for bin in sqlplus timeout sed grep head; do
                if ! command -v "$bin" >/dev/null 2>&1; then
                        PROCESS_STATUS=1
                        fc_log "[ERRO] Dependência obrigatória não encontrada no PATH: $bin"
                        if [ "$bin" = "sqlplus" ]; then
                                fc_log "Instale o Oracle Instant Client e adicione $bin ao PATH."
                        else
                                fc_log "Para instalar $bin|execute (como root):"
                                fc_log "  Debian/Ubuntu: apt-get install $bin"
                                fc_log "  RHEL/CentOS:   yum install $bin"
                        fi
                        fc_log "Fim da execução do script. Código de retorno: $PROCESS_STATUS"
                        return $PROCESS_STATUS
                fi
        done
        fc_log_separador
        if [ $ret_args -eq 0 ]; then
                fc_log_separador
                fc_log "Processando a execução SQL direta com os parâmetros informados."
                fc_log "[DEBUG] Execução direta: sql=$NOME_ARQUIVO_SQL | destino=$DESTINO_DIR | base_sql=$BASE_DIR_SQL | strict_tags=$STRICT_TAGS"
                fc_log_separador
                fc_valida_conexao
                if [ $? -ne 0 ]; then
                        PROCESS_STATUS=1
                        fc_log "[ERRO] Falha ao validar a conexão com o banco de dados."
                        fc_log "Fim da execução do script. Código de retorno: $PROCESS_STATUS"
                        return $PROCESS_STATUS
                fi 
                # Executa o SQL principal e trata retorno.
                fc_executa_sql
                if [ $? -ne 0 ]; then
                        PROCESS_STATUS=1
                        fc_log "[ERRO] Falha na execução do SQL principal: $NOME_ARQUIVO_SQL"
                        fc_log "Fim da execução do script. Código de retorno: $PROCESS_STATUS"
                        return $PROCESS_STATUS
                else
                        fc_log "SQL executado com sucesso: $NOME_ARQUIVO_SQL"
                fi
                fc_log_separador
        else
                fc_log_separador
                fc_log "Processando arquivos com o prefixo informado: ${NOME_INICIAL_ARQUIVO}"
                fc_log "[DEBUG] Execução em lote ativa: prefixo=${NOME_INICIAL_ARQUIVO} | tipo_ctl=${TIPO_CTL} | diretório_entrada=${DATA_DIR}"
                fc_log_separador
                #
                # Busca arquivos .ini na entrada|armazena em INPUTS e move para saída.
                fc_busca_e_copia_arquivos_ini_para_output
                if [ $? -ne 0 ]; then
                        PROCESS_STATUS=1
                        fc_log "[ERRO] Falha ao buscar ou mover arquivos .ini do diretório de entrada."
                        if [ "${#INPUTS[@]}" -gt 0 ]; then
                                for f in "${INPUTS[@]}"; do
                                        local nome_arquivo="$f"
                                        local arquivo_movido="${BASE_DIR_OUTPUT}/${f}"
                                        if [ "$TIPO_CTL" = "input" ]; then
                                                local arquivo_diretorio_origem="${DATA_DIR}/${f}"
                                        else
                                                local arquivo_diretorio_origem="${DATA_CONF}/${f}"
                                        fi
                                        if [ "$TIPO_CTL" = "input" ]; then
                                                fc_log "Copiando arquivo de volta para o diretório de origem: $arquivo_movido -> $arquivo_diretorio_origem"
                                                if ! cp -f -- "$arquivo_movido" "$arquivo_diretorio_origem"; then
                                                        fc_log "[ERRO] Falha ao copiar arquivo para o diretorio de origem: $arquivo_movido -> $arquivo_diretorio_origem"
                                                fi
                                                fc_log "Arquivo copiado de volta para o diretório de origem: $nome_arquivo"
                                        fi
                                done
                        fi
                        fc_log "Fim da execução do script. Código de retorno: $PROCESS_STATUS"
                        return $PROCESS_STATUS
                fi
                if [ "${#INPUTS[@]}" -eq 0 ]; then
                        PROCESS_STATUS=0
                        fc_log "[ALERTA] Nenhum arquivo .ini encontrado no diretório de entrada: $DATA_DIR. Encerrando execução."
                        fc_log "Fim da execução do script. Código de retorno: $PROCESS_STATUS"
                        return $PROCESS_STATUS
                fi
                fc_log_separador
                fc_log "Arquivos de parâmetros encontrados: ${INPUTS[*]}"
                fc_log "Iniciando o processamento dos arquivos de parâmetros:"
                for f in "${INPUTS[@]}"; do
                        fc_log_separador
                        fc_log " ###############################################  "
                        fc_log "  Arquivo em processamento: $f"
                        fc_log "[DEBUG] Iniciando ciclo do lote para arquivo: $f | total_em_lote=${#INPUTS[@]}"
                        arquivo_movido="${BASE_DIR_OUTPUT}/${f}"
                        if [ -f "$arquivo_movido" ]; then
                                fc_log "Arquivo de parâmetros disponível em ${BASE_DIR_OUTPUT}: $f"
                        else
                                fc_log "[ERRO] Arquivo de parâmetros não encontrado em ${BASE_DIR_OUTPUT}: $f"
                                PROCESS_STATUS=1
                                fc_adicionar_erro_arquivo "$arquivo_movido"
                                continue
                        fi
                        # Verifica se arquivo tem algum conteúdo
                        if [ ! -s "$arquivo_movido" ]; then
                                fc_log "[ALERTA] Arquivo de parâmetros vazio: $arquivo_movido"
                                PROCESS_STATUS=1
                                fc_adicionar_erro_arquivo "$arquivo_movido"
                                continue
                        fi
                        fc_processa_argumentos_linha_arquivo "$arquivo_movido"
                        if [ $? -ne 0 ]; then
                                PROCESS_STATUS=1
                                fc_log "[ERRO] Falha ao processar os parâmetros do arquivo: $arquivo_movido"
                                fc_adicionar_erro_arquivo "$arquivo_movido"
                                continue
                        fi
                        fc_valida_conexao
                        if [ $? -ne 0 ]; then
                                PROCESS_STATUS=1
                                fc_log "[ERRO] Falha ao validar a conexão para o arquivo: $arquivo_movido"
                                fc_adicionar_erro_arquivo "$arquivo_movido"
                                continue
                        fi
                        fc_log "[DEBUG] Conexão validada com sucesso para o arquivo: $arquivo_movido"
                        # Executa o SQL principal e trata retorno.
                        fc_executa_sql
                        if [ $? -ne 0 ]; then
                                PROCESS_STATUS=1
                                fc_log "[ERRO] Falha na execução do SQL principal: $NOME_ARQUIVO_SQL"
                                fc_adicionar_erro_arquivo "$arquivo_movido"
                        else
                                fc_log "SQL executado com sucesso: $NOME_ARQUIVO_SQL"
                                fc_adicionar_ok_arquivo "$arquivo_movido"
                        fi
                        BD_CONN=""
                        export BD_CONN
                        fc_log "[DEBUG] Estado de conexão limpo após o ciclo do arquivo: $f"
                        fc_log_separador
                        fc_log " ###############################################  "
                done
                fc_log_separador
                # RESUMO FINAL
                fc_log "==================== RESUMO FINAL ===================="
                fc_log "Arquivos encontrados no lote: ${#INPUTS[@]}"
                fc_log "Arquivos processados com sucesso:"
                for f in "${ARQUIVOS_OK[@]}"; do
                        fc_log "  OK: $f"
                done
                fc_log "Arquivos com erro ou alerta:"
                for f in "${ARQUIVOS_ERRO[@]}"; do
                        fc_log "  ARQUIVO COM ERRO: $f"
                done
                # Contagem rigorosa
                local total_ok=${#ARQUIVOS_OK[@]}
                local total_erro=${#ARQUIVOS_ERRO[@]}
                fc_log "Total de arquivos OK: $total_ok"
                fc_log "Total de arquivos com erro: $total_erro"
                if [ ${#ARQUIVOS_OK[@]} -eq 0 ]; then
                        fc_log "Nenhum arquivo processado com sucesso."
                fi
                if [ ${#ARQUIVOS_ERRO[@]} -eq 0 ]; then
                        fc_log "Nenhum arquivo apresentou erro ou alerta."
                fi
                if [ "$PROCESS_STATUS" -eq 0 ]; then
                        fc_log "Status final do lote: SUCESSO"
                else
                        fc_log "Status final do lote: FALHA"
                fi
        fi
        fc_log_separador
        fc_log "==================== RESUMO ARQUIVOS GERADOS ===================="
        fc_log "Arquivos gerados:"
        for f in "${ARQUIVOS_GERADOS[@]}"; do
                fc_log "  GERADO: $f"
        done                
        fc_log "Fim da execução do script. Código de retorno: $PROCESS_STATUS"
        return $PROCESS_STATUS
}

if [ "${BASH_SOURCE[0]:-$0}" = "${0}" ]; then
        ################################ INICIO ##########################################
        # -------------------------------------------------------------------------------
        # Este bloco verifica se o script está sendo executado diretamente ou sendo 
        # "sourced". Se for executado diretamente (${BASH_SOURCE[0]} == ${0})|
        # -------------------------------------------------------------------------------
        ###############################################################
        # Ponto de entrada principal do script
        # Se o script está sendo executado diretamente (não via source),
        # aciona a função principal fc_inicio para iniciar todo o fluxo.
        # Isso garante que as rotinas só sejam executadas quando o script
        # for chamado como programa|evitando execuções indesejadas.
        ###############################################################
        # Inicia o processamento principal do runbook|passando todos os parâmetros recebidos
        fc_inicio "$@"
        if [ $? -ne 0 ]; then
                exit 1
        else
                exit 0
        fi

fi