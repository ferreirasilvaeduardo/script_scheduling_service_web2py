# -*- coding: utf-8 -*-
"""Construtor puro de DDL e seed Oracle 11gR2 a partir de sql_ident (F7.1).

Gera instrucoes DDL fase a fase, sem importar drivers Oracle nem depender do web2py.
Totalmente idempotente e aderente ao README §9, §10, §11.1 e AGENTS §4.
"""
import collections

import sql_ident

# Estrutura representativa de uma instrucao DDL
DDLItem = collections.namedtuple("DDLItem", [
    "phase", "kind", "name", "sql", "entity"
])

# Catalogo canonico de funcionalidades (README §4.3.D)
# Tuplas: (modulo, codigo, nome de exibicao, finalidade)
FEATURE_CATALOG = (
    ("OPERATION", "EXEC_SCRIPT", "Rodar Scripts", "Preencher questionários e abrir tickets"),
    ("OPERATION", "VIEW_LOGS", "Consultar Tickets", "Acompanhar os tickets e ler o log em tempo quase real"),
    ("OPERATION", "CANCEL_TICKET", "Cancelar Tickets", "Cancelar tickets de terceiros nos ambientes consultados (com Consultar Tickets)"),
    ("OPERATION", "DOWNLOAD_OUTPUT", "Baixar Saídas", "Navegar pelas saídas dos tickets nos ambientes do perfil e baixar o zip ou um arquivo"),
    ("ADMIN", "MANAGE_USERS", "Gestão de Usuários", "Gerenciar operadores e credenciais"),
    ("ADMIN", "MANAGE_PROFILES", "Gestão de Perfis", "Gerenciar perfis e matrizes de permissão"),
    ("ADMIN", "MANAGE_ENVIRONMENTS", "Gestão de Ambientes", "Gerenciar ambientes e DSNs"),
    ("ADMIN", "MANAGE_SCRIPTS", "Gestão de Scripts", "Cadastrar rotinas e homologação por ambiente"),
    ("ADMIN", "MANAGE_PARAMETERS", "Dicionário de Parâmetros", "Gerenciar perguntas e flags reutilizáveis"),
    ("ADMIN", "MANAGE_SCHEDULES", "Regras de Agendamento", "Criar e gerenciar recorrências"),
    ("ADMIN", "VIEW_AUDIT", "Auditoria", "Consultar a trilha de auditoria e os agentes"),
)

# Catalogo padrao de ambientes atendidos (nome, descricao, conexao)
# (nome, descricao, conexao, is_production). is_production so vale na inclusao: o MERGE nao desfaz o cadastro (CR-017).
DEFAULT_ENVIRONMENTS = (
    ("CLONE2", "BRTLVLTS1199PL (10.238.10.209)", "10.238.55.146/gfprod", "Y"),
    ("CLONE1", "BRTLVLTS1198PL (10.238.10.208)", "10.238.55.145/gfprod", "Y"),
    ("CLONE6", "BRTLVLTS3089SL (10.238.10.210)", "10.238.45.230/svc_gfprodc6", "Y"),
    ("CLONE7", "BRTLVLTS1216PL (10.238.10.109)", "10.238.45.230/svc_gfprodc7", "Y"),
    ("GFPREPROD", "BRTLVLTY3067SL (10.129.177.188)", "10.129.177.188/GFPR", "Y"),
)

# Catalogo padrao de perfis operacionais e administrativos (nome, descricao, is_admin, funcionalidades, ambientes)
DEFAULT_PROFILES = (
    ("ADMINISTRATOR", "Acesso irrestrito a todas as funcionalidades e ambientes", "Y", (
        "EXEC_SCRIPT", "VIEW_LOGS", "CANCEL_TICKET", "DOWNLOAD_OUTPUT", "MANAGE_USERS", "MANAGE_PROFILES",
        "MANAGE_ENVIRONMENTS", "MANAGE_SCRIPTS", "MANAGE_PARAMETERS", "MANAGE_SCHEDULES", "VIEW_AUDIT"
    ), ("CLONE2", "CLONE1", "CLONE6", "CLONE7", "GFPREPROD")),
    ("OPERATOR_PROD", "Operador de Ambientes de Producao", "N", (
        "EXEC_SCRIPT", "VIEW_LOGS", "CANCEL_TICKET", "DOWNLOAD_OUTPUT"
    ), ("CLONE2", "CLONE1", "CLONE6", "CLONE7", "GFPREPROD")),
    ("OPERATOR_HML", "Operador de Ambientes de Homologacao", "N", (
        "EXEC_SCRIPT", "VIEW_LOGS", "CANCEL_TICKET", "DOWNLOAD_OUTPUT"
    ), ("CLONE6", "CLONE7", "GFPREPROD")),
    ("READ_ONLY", "Perfil de Apenas Leitura e Consulta", "N", (
        "VIEW_LOGS",
    ), ("CLONE2", "CLONE1", "CLONE6", "CLONE7", "GFPREPROD")),
)

# Catalogo padrao de usuarios de homologacao e demonstracao (login, nome, nome do perfil)
DEFAULT_USERS = (
    ("admin", "Super Administrador", "ADMINISTRATOR"),
    ("op.prod", "Operador Producao", "OPERATOR_PROD"),
    ("op.hml", "Operador Homologacao", "OPERATOR_HML"),
    ("consulta", "Auditor e Consulta", "READ_ONLY"),
)

# Hash PBKDF2 da senha padrao de homologacao/demonstracao (senha: Sss@Homolog2026!)
HOMOLOGATION_DEFAULT_PASSWORD_HASH = "pbkdf2_sha256$200000$8007db1bd770663178d0f1b1a129140c$9d9604af27e21326e982e5e7c64bfdd868c0995a97181b5a9695149755852d63"

# Catalogo padrao de parametros reutilizaveis de utilitarios (codigo, param_nomeado, label, descricao, tipo, opcoes, vpadrao)
DEFAULT_PARAMETERS = (
    ("arq_origem", "--origem", "Arquivo ou Pasta de Origem", "Caminho do arquivo ou pasta a ser processado", "TEXT", None, None),
    ("arq_destino", "--destino", "Arquivo ou Pasta de Destino", "Caminho do arquivo de saida ou diretorio destino", "TEXT", None, None),
    ("arq_zip", "--arquivo-zip", "Arquivo ZIP", "Caminho do pacote compactado .zip", "TEXT", None, None),
    ("arq_tar", "--arquivo-tar", "Arquivo TAR.GZ", "Caminho do pacote compactado .tar.gz", "TEXT", None, None),
    ("nivel_compressao", "--nivel", "Nivel de Compressao (1-9)", "Nivel de compactacao zlib de 1 (rapido) a 9 (maximo)", "NUMBER", None, "6"),
    ("linhas_por_parte", "--linhas-por-parte", "Linhas por Parte", "Quantidade maxima de linhas em cada parte dividida", "NUMBER", None, "1000"),
    ("prefixo_saida", "--prefixo-saida", "Prefixo dos Arquivos Gerados", "Prefixo do caminho das partes geradas", "TEXT", None, "/tmp/parte_"),
    ("padrao_origem", "--padrao-origem", "Padrao de Origem (Glob)", "Mascara glob dos arquivos a serem juntados (ex: /tmp/parte_*)", "TEXT", None, "/tmp/parte_*"),
    ("enc_origem", "--enc-origem", "Codificacao de Origem", "Codificacao de caracteres atual do arquivo", "SELECT", '{"ISO-8859-1":"ISO-8859-1 (Latin1)","UTF-8":"UTF-8","CP1252":"Windows CP1252","ASCII":"ASCII"}', "ISO-8859-1"),
    ("enc_destino", "--enc-destino", "Codificacao de Destino", "Nova codificacao de caracteres desejada", "SELECT", '{"UTF-8":"UTF-8","ISO-8859-1":"ISO-8859-1 (Latin1)","CP1252":"Windows CP1252"}', "UTF-8"),
    ("termo_busca", "--busca", "Texto a Localizar", "String ou termo a ser pesquisado nas linhas", "TEXT", None, None),
    ("termo_substituicao", "--substituicao", "Texto Substituto", "Nova string que substituira o texto localizado", "TEXT", None, None),
    ("flag_ordenar", "--ordenar", "Ordenar Resultado", "Indica se deve ordenar alfabeticamente ou manter ordem", "SELECT", '{"S":"Sim (Ordenar)","N":"Nao (Preservar ordem)"}', "S"),
    ("tipo_hash", "--algoritmo", "Algoritmo de Hash", "Algoritmo criptografico de integridade", "SELECT", '{"sha256":"SHA-256 (Recomendado)","md5":"MD5","sha1":"SHA-1"}', "sha256"),
    ("termo_filtro", "--padrao", "Padrao de Filtragem", "Texto a ser filtrado nas linhas do arquivo", "TEXT", None, None),
    ("flag_inverter", "--inverter", "Inverter Selecao", "Se ativado, seleciona as linhas que nao possuem o padrao", "SELECT", '{"N":"Nao (Manter correspondencias)","S":"Sim (Excluir correspondencias)"}', "N"),
    ("flag_numerico", "--numerico", "Ordenacao Numerica", "Trata o inicio das linhas como valor numerico", "SELECT", '{"N":"Nao (Alfanumerica)","S":"Sim (Numerica)"}', "N"),
    ("flag_reverso", "--reverso", "Ordem Reversa (Decrescente)", "Ordena de tras para frente", "SELECT", '{"N":"Nao (Crescente)","S":"Sim (Decrescente)"}', "N"),
    ("caminho_arquivo", None, "Caminho do Arquivo", "Caminho do arquivo a ser analisado", "TEXT", None, None),
)

# Catalogo padrao de scripts utilitarios de demonstracao (nome, descricao, grupo, categoria, etapa, interpretador, path_file, param_type, max_par, timeout_seg, params)
DEFAULT_SCRIPTS = (
    ("zipar_arquivos", "Compacta arquivo ou pasta em formato ZIP", "UTILITARIOS", "ARQUIVOS", "COMPACTACAO", "PYTHON3", "/opt/automacoes/scripts/utilitarios/zipar_arquivos.py", "NAMED", 2, 1800, (
        ("arq_origem", 1, "Y", None),
        ("arq_destino", 2, "Y", None),
        ("nivel_compressao", 3, "N", "6"),
    )),
    ("descompactar_zip", "Extrai arquivos de pacote ZIP para pasta destino com protecao segura", "UTILITARIOS", "ARQUIVOS", "DESCOMPACTACAO", "PYTHON3", "/opt/automacoes/scripts/utilitarios/descompactar_zip.py", "NAMED", 2, 1800, (
        ("arq_zip", 1, "Y", None),
        ("arq_destino", 2, "Y", None),
    )),
    ("quebrar_arquivo", "Divide arquivo texto em partes menores por quantidade de linhas", "UTILITARIOS", "ARQUIVOS", "DIVISAO", "PYTHON3", "/opt/automacoes/scripts/utilitarios/quebrar_arquivo.py", "NAMED", 2, 1800, (
        ("arq_origem", 1, "Y", None),
        ("linhas_por_parte", 2, "N", "1000"),
        ("prefixo_saida", 3, "N", "/tmp/parte_"),
    )),
    ("juntar_arquivos", "Concatena blocos de arquivos ordenados em arquivo consolidado final", "UTILITARIOS", "ARQUIVOS", "CONCATENACAO", "PYTHON3", "/opt/automacoes/scripts/utilitarios/juntar_arquivos.py", "NAMED", 2, 1800, (
        ("padrao_origem", 1, "Y", "/tmp/parte_*"),
        ("arq_destino", 2, "Y", None),
    )),
    ("converter_encoding", "Converte codificacao de caracteres de arquivo texto (ex: ISO-8859-1 para UTF-8)", "UTILITARIOS", "ARQUIVOS", "CONVERSAO", "PYTHON3", "/opt/automacoes/scripts/utilitarios/converter_encoding.py", "NAMED", 2, 1800, (
        ("arq_origem", 1, "Y", None),
        ("arq_destino", 2, "Y", None),
        ("enc_origem", 3, "N", "ISO-8859-1"),
        ("enc_destino", 4, "N", "UTF-8"),
    )),
    ("substituir_texto", "Localiza e substitui texto em arquivo gerando copia atualizada", "UTILITARIOS", "ARQUIVOS", "TRANSFORMACAO", "PYTHON3", "/opt/automacoes/scripts/utilitarios/substituir_texto.py", "NAMED", 2, 1800, (
        ("arq_origem", 1, "Y", None),
        ("arq_destino", 2, "Y", None),
        ("termo_busca", 3, "Y", None),
        ("termo_substituicao", 4, "Y", None),
    )),
    ("remover_duplicadas", "Remove linhas duplicadas de arquivo texto preservando ordem ou ordenando", "UTILITARIOS", "ARQUIVOS", "HIGIENIZACAO", "PYTHON3", "/opt/automacoes/scripts/utilitarios/remover_duplicadas.py", "NAMED", 2, 1800, (
        ("arq_origem", 1, "Y", None),
        ("arq_destino", 2, "Y", None),
        ("flag_ordenar", 3, "N", "S"),
    )),
    ("gerar_hash_arquivo", "Calcula hash criptografico (SHA256, MD5, SHA1) para conferencia de integridade", "UTILITARIOS", "ARQUIVOS", "AUDITORIA", "PYTHON3", "/opt/automacoes/scripts/utilitarios/gerar_hash_arquivo.py", "NAMED", 2, 1800, (
        ("arq_origem", 1, "Y", None),
        ("tipo_hash", 2, "N", "sha256"),
    )),
    ("compactar_targz", "Cria pacote compactado .tar.gz a partir de arquivo ou pasta", "UTILITARIOS", "ARQUIVOS", "COMPACTACAO", "BASH", "/opt/automacoes/scripts/utilitarios/compactar_targz.sh", "NAMED", 2, 1800, (
        ("arq_origem", 1, "Y", None),
        ("arq_destino", 2, "Y", None),
    )),
    ("descompactar_targz", "Extrai pacote compactado .tar.gz para pasta destino com verificacao", "UTILITARIOS", "ARQUIVOS", "DESCOMPACTACAO", "BASH", "/opt/automacoes/scripts/utilitarios/descompactar_targz.sh", "NAMED", 2, 1800, (
        ("arq_tar", 1, "Y", None),
        ("arq_destino", 2, "Y", None),
    )),
    ("contar_linhas_arquivo", "Conta linhas, palavras e bytes de arquivo texto (modo posicional/sequencial)", "UTILITARIOS", "ARQUIVOS", "ANALISE", "SH", "/opt/automacoes/scripts/utilitarios/contar_linhas_arquivo.sh", "POSITIONAL", 2, 600, (
        ("caminho_arquivo", 1, "Y", None),
    )),
    ("filtrar_linhas", "Filtra linhas de arquivo baseado em padrao de texto com opcao de inverter", "UTILITARIOS", "ARQUIVOS", "FILTRAGEM", "BASH", "/opt/automacoes/scripts/utilitarios/filtrar_linhas.sh", "NAMED", 2, 1800, (
        ("arq_origem", 1, "Y", None),
        ("arq_destino", 2, "Y", None),
        ("termo_filtro", 3, "Y", None),
        ("flag_inverter", 4, "N", "N"),
    )),
    ("ordenar_arquivo", "Ordena linhas de arquivo texto com opcoes numerica e reversa", "UTILITARIOS", "ARQUIVOS", "ORGANIZACAO", "SH", "/opt/automacoes/scripts/utilitarios/ordenar_arquivo.sh", "NAMED", 2, 1800, (
        ("arq_origem", 1, "Y", None),
        ("arq_destino", 2, "Y", None),
        ("flag_numerico", 3, "N", "N"),
        ("flag_reverso", 4, "N", "N"),
    )),
    ("limpar_linhas_vazias", "Remove espacos em branco excedentes e linhas vazias de arquivo texto", "UTILITARIOS", "ARQUIVOS", "HIGIENIZACAO", "BASH", "/opt/automacoes/scripts/utilitarios/limpar_linhas_vazias.sh", "NAMED", 2, 1800, (
        ("arq_origem", 1, "Y", None),
        ("arq_destino", 2, "Y", None),
    )),
)

# -----------------------------------------------------------------------------
# Dicionario de Governanca de Dados (Metadados para COMMENT ON TABLE/COLUMN)
# -----------------------------------------------------------------------------
RECORD_COLUMN_DESCRIPTIONS = {
    "created_at": "Data e hora da criacao do registro no banco de dados (imutavel)",
    "created_by": "Identificador do usuario ou servico responsavel pela criacao (imutavel)",
    "updated_at": "Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)",
    "updated_by": "Identificador do usuario ou servico responsavel pela ultima alteracao",
}

TABLE_COMMENTS = {
    "environments": "Cadastro de ambientes operacionais para execucao de rotinas (PRODUCAO, HOMOLOGACAO, CLONES)",
    "profiles": "Perfis de acesso para autorizacao baseada em papeis (RBAC)",
    "features": "Catalogo canonico de permissoes e operacoes controladas pelo sistema",
    "profile_feature": "Matriz associativa de permissoes que vincula perfis a funcionalidades autorizadas",
    "profile_env": "Associacao que delimita os ambientes onde cada perfil possui autorizacao",
    "scripts": "Catalogo de rotinas e scripts homologados para execucao automatizada",
    "profile_script": "Associacao que define quais rotinas cada perfil tem permissao para disparar",
    "script_env": "Homologacao tecnica que associa rotinas aos ambientes onde podem rodar",
    "users": "Cadastro de operadores do sistema, credenciais e controle de sessao",
    "parameters": "Dicionario de perguntas, variaveis e flags reutilizaveis em scripts",
    "script_param": "Composicao e ordenacao dos parametros exigidos por cada rotina",
    "schedules": "Regras de execucao periodica automatica ou avulsa de rotinas",
    "tickets": "Fila de execucao, ciclo de vida e historico de execucao de scripts",
    "ticket_answer": "Valores individuais preenchidos para cada parametro no disparo do ticket",
    "agents": "Registro, versao e sinais de vida dos daemons executores instalados",
    "audit": "Trilha de auditoria imutavel para conformidade e rastreabilidade",
    "control": "Parametros de controle global, versao de esquema e concessao de limpeza",
}

COLUMN_COMMENTS = {
    "environments": {
        "id": "Identificador unico sequencial do ambiente (chave primaria)",
        "name": "Nome mnemonico unico do ambiente em maiusculas (chave natural imutavel)",
        "description": "Descricao detalhada do ambiente, servidor host e finalidade",
        "connection": "String de conexao ou alias DSN/TNS sugerido para o banco de dados do ambiente",
        "active": "Indicador de vigencia do ambiente (Y=Ativo, N=Inativo)",
        "is_production": "Ambiente de producao: o disparo mostra alerta e confirmacao em vermelho (Y/N)",
    },
    "profiles": {
        "id": "Identificador unico sequencial do perfil (chave primaria)",
        "name": "Nome unico de identificacao do perfil (ex: ADMINISTRATOR, OPERADOR)",
        "description": "Finalidade e escopo de atuacao dos usuarios vinculados ao perfil",
        "is_admin": "Indicador de perfil com poderes administrativos plenos (Y/N)",
        "perm_version": "Versao incremental das permissoes para invalidacao de sessoes ativas",
        "active": "Indicador de vigencia do perfil no sistema (Y=Ativo, N=Inativo)",
    },
    "features": {
        "id": "Identificador unico sequencial da funcionalidade (chave primaria)",
        "code": "Codigo mnemonico unico da operacao (ex: EXEC_SCRIPT, VIEW_LOGS, CANCEL_TICKET)",
        "module": "Modulo funcional do sistema ao qual a operacao pertence (OPERATION, ADMIN)",
        "name": "Nome amigavel de exibicao da funcionalidade na interface",
        "description": "Descricao clara das acoes permitidas por esta funcionalidade",
        "active": "Indicador de vigencia da funcionalidade no sistema (Y/N)",
    },
    "profile_feature": {
        "id": "Identificador unico sequencial do vinculo (chave primaria)",
        "profile_id": "Identificador do perfil associado (FK para tbsss_profiles)",
        "feature_id": "Identificador da funcionalidade autorizada (FK para tbsss_features)",
    },
    "profile_env": {
        "id": "Identificador unico sequencial do vinculo (chave primaria)",
        "profile_id": "Identificador do perfil autorizado (FK para tbsss_profiles)",
        "environment_id": "Identificador do ambiente autorizado (FK para tbsss_environments)",
    },
    "scripts": {
        "id": "Identificador unico sequencial do script (chave primaria)",
        "name": "Nome unico da rotina (ex: carga_diaria, relatorio_mensal)",
        "description": "Detalhamento da finalidade, regras e impacto da execucao do script",
        "interpreter": "Interpretador utilizado para execucao (PYTHON3, BASH, SH)",
        "path_file": "Caminho absoluto normalizado do script no sistema de arquivos do servidor",
        "timeout_segundos": "Tempo limite em segundos para execucao antes de encerramento forcado",
        "permite_concorrente": "Indicador se permite execucoes simultaneas no mesmo ambiente (Y/N)",
        "category": "Categoria de negocio ou agrupador funcional da rotina",
        "active": "Indicador de disponibilidade da rotina para novas execucoes (Y/N)",
    },
    "profile_script": {
        "id": "Identificador unico sequencial do vinculo (chave primaria)",
        "profile_id": "Identificador do perfil autorizado (FK para tbsss_profiles)",
        "script_id": "Identificador da rotina homologada (FK para tbsss_scripts)",
    },
    "script_env": {
        "id": "Identificador unico sequencial da homologacao (chave primaria)",
        "script_id": "Identificador do script homologado (FK para tbsss_scripts)",
        "environment_id": "Identificador do ambiente onde a rotina e permitida (FK para tbsss_environments)",
    },
    "users": {
        "id": "Identificador unico sequencial do usuario (chave primaria)",
        "login": "Identificador de login do usuario (chave natural imutavel)",
        "name": "Nome completo do operador para identificacao",
        "email": "Endereco de correio eletronico corporativo do operador",
        "password_hash": "Hash criptografico da senha gerado via PBKDF2-SHA256 (200k iteracoes)",
        "profile_id": "Identificador do perfil de acesso atribuido (FK para tbsss_profiles)",
        "active": "Indicador se o usuario esta ativo (Y=Ativo, N=Bloqueado/Inativo)",
        "session_epoch": "Contador de revogacao de sessoes ativas para seguranca",
        "failed_attempts": "Numero de tentativas consecutivas de autenticacao incorretas",
        "locked_until": "Data e hora limite de bloqueio temporario por excesso de falhas",
    },
    "parameters": {
        "id": "Identificador unico sequencial do parametro (chave primaria)",
        "code": "Codigo mnemonico unico do parametro (ex: DATA_REF, FORMATO)",
        "label": "Rotulo de exibicao amigavel apresentado no formulario ao usuario",
        "component_type": "Tipo de componente visual (TEXTO, NUMERO, DATA, SELECT, RADIO, CHECKBOX)",
        "description": "Texto explicativo de orientacao ao operador",
        "validation_regex": "Expressao regular segura para validacao do valor inserido",
        "options_json": "Opcoes selecionaveis em formato JSON para componentes do tipo lista",
        "default_value": "Valor pre-definido padrao sugerido no formulario",
        "flag_comando": "Flag de linha de comando associada (ex: --data, -f)",
        "sensitive": "Indicador se o dado e confidencial e deve ser mascarado em logs (Y/N)",
        "active": "Indicador de vigencia do parametro no sistema (Y/N)",
    },
    "script_param": {
        "id": "Identificador unico sequencial da associacao (chave primaria)",
        "script_id": "Identificador do script (FK para tbsss_scripts)",
        "parameter_id": "Identificador do parametro associado (FK para tbsss_parameters)",
        "sort_order": "Posicao de apresentacao do campo no questionario de execucao",
        "required": "Indicador se o preenchimento e mandatorio para esta rotina (Y/N)",
        "default_value_override": "Valor padrao especifico que sobrescreve o valor do parametro para este script",
        "script_group": "Agrupador ou secao visual no formulario",
        "stage": "Etapa de preenchimento em formularios com multiplos passos",
    },
    "schedules": {
        "id": "Identificador unico sequencial do agendamento (chave primaria)",
        "name": "Titulo descritivo da regra de agendamento",
        "script_id": "Identificador da rotina a ser executada (FK para tbsss_scripts)",
        "environment": "Nome do ambiente onde a rotina deve ser disparada (FK para tbsss_environments)",
        "user_id": "Operador responsavel pelo agendamento (FK para tbsss_users)",
        "priority": "Nivel de prioridade da execucao (1=Critico a 4=Baixa)",
        "recurrence_type": "Tipo de periodicidade (ONCE, DAILY, WEEKLY, MONTHLY, CRON)",
        "cron_expression": "Expressao cron no formato padrao de 5 campos (minuto hora dia mes dsem)",
        "run_time": "Horario de disparo no formato HH:MM para recorrencias diarias/semanais/mensais",
        "week_days": "Dias da semana selecionados (1=Dom a 7=Sab) para agendamento semanal",
        "month_day": "Dia do mes (1 a 31) para agendamento mensal",
        "params_json": "Parametros congelados configurados para o agendamento em JSON (CLOB)",
        "start_date": "Data inicial de vigencia do agendamento",
        "end_date": "Data final limite para expiracao do agendamento",
        "next_run_at": "Data e hora exatas calculadas para o proximo disparo",
        "last_run_at": "Data e hora em que ocorreu o ultimo disparo",
        "last_ticket_id": "Identificador do ticket mais recente gerado por esta regra",
        "pause_reason": "Motivo formal em caso de suspensao da regra (ex: USER_INACTIVE, MANUAL)",
        "active": "Indicador de vigencia da regra (Y=Ativo, N=Pausado/Concluido)",
    },
    "tickets": {
        "id": "Identificador unico sequencial do ticket de execucao (chave primaria)",
        "script_id": "Identificador da rotina solicitada (FK para tbsss_scripts)",
        "environment": "Nome do ambiente alvo da execucao (FK para tbsss_environments)",
        "requested_by": "Login do operador que solicitou a execucao (FK para tbsss_users)",
        "source_ip": "Endereco IP do cliente que originou o pedido",
        "agent_id": "Identificador do daemon do agente que executou o ticket",
        "status": "Situacao da execucao (PENDING, RUNNING, SUCCESS, FAILED, CANCELLED)",
        "priority": "Prioridade de atendimento na fila (1=Critico, 2=Alta, 3=Normal, 4=Baixa)",
        "cancel_requested": "Indicador se o cancelamento foi requisitado pelo operador (Y/N)",
        "process_id": "Identificador do processo (PID) no sistema operacional do servidor",
        "exit_code": "Codigo numerico de retorno do processo (0=Sucesso, >0=Erro)",
        "scheduled_at": "Data e hora agendadas para o processamento",
        "started_at": "Data e hora efetivas do inicio da execucao pelo agente",
        "finished_at": "Data e hora de conclusao ou encerramento da execucao",
        "heartbeat_at": "Data e hora da ultima confirmacao de atividade do processo",
        "log_output": "Saida completa de execucao capturada de stdout/stderr (CLOB)",
        "log_truncated": "Indicador se o log excedeu o limite maximo de tamanho (Y/N)",
        "log_offset_chars": "Controle tecnico de caracteres confirmados gravados no log",
        "parent_ticket_id": "Identificador do ticket pai em caso de reexecucao",
        "schedule_id": "Identificador da regra de agendamento de origem (se houver)",
        "status_reason": "Codigo tecnico do motivo de falha ou cancelamento",
        "submitted_params": "Copia fiel dos parametros de entrada fornecidos na solicitacao (CLOB)",
    },
    "ticket_answer": {
        "id": "Identificador unico sequencial da resposta (chave primaria)",
        "ticket_id": "Identificador do ticket correspondente (FK para tbsss_tickets)",
        "parameter_id": "Identificador do parametro respondido (FK para tbsss_parameters)",
        "valor": "Valor fornecido pelo operador para este parametro",
    },
    "agents": {
        "id": "Identificador unico sequencial do agente (chave primaria)",
        "code": "Codigo identificador unico do agente (ex: agt-node01)",
        "hostname": "Nome de rede (hostname) da maquina servidora do agente",
        "daemon_pid": "Identificador de processo (PID) do daemon no servidor",
        "version": "Versao do software do servico em execucao no agente",
        "environments": "Lista separada por virgulas dos ambientes atendidos por este no",
        "platform": "Sistema operacional da maquina servidora (POSIX)",
        "interpreters": "Interpretadores homologados disponiveis no servidor (PYTHON3, BASH, SH)",
        "status": "Estado de operacao do no (ACTIVE, STOPPED)",
        "started_at": "Data e hora de inicializacao do daemon",
        "heartbeat_at": "Data e hora do sinal periodico de disponibilidade mais recente",
    },
    "audit": {
        "id": "Identificador unico sequencial do evento de auditoria (chave primaria)",
        "created_at": "Data e hora exatas da realizacao do evento auditado",
        "actor": "Identificador do operador ou servico que executou a acao",
        "source_ip": "Endereco IP do cliente que solicitou a operacao",
        "action": "Codigo mnemonico da acao executada (ex: CREATE, TICKET_CREATE)",
        "entity": "Nome da tabela ou entidade alvo afetada",
        "entity_id": "Identificador numerico do registro alvo afetado",
        "detail": "Texto descritivo ou dados em formato estruturado sobre o evento",
    },
    "control": {
        "id": "Identificador unico da linha de controle global (sempre 1)",
        "schema_version": "Numero da versao estrutural do banco de dados atualmente instalada",
        "version_applied_at": "Data e hora de aplicacao da versao de esquema atual",
        "version_applied_by": "Identificador de quem realizou a aplicacao do esquema",
        "purge_owner": "Identificador do no que detem a concessao de purga de dados",
        "purge_lease_until": "Data e hora limite de expiracao da concessao de purga",
    },
    "ticket_output": {
        "id": "Identificador unico sequencial da saida (chave primaria)",
        "ticket_id": "Ticket dono da saida (FK para tbsss_tickets, removida em cascata)",
        "state": "Situacao do zip (WRITING, AVAILABLE, EXCEEDED, FAILED)",
        "reason": "Motivo de EXCEEDED ou FAILED (FILES, BYTES, DEADLINE, ERROR)",
        "agent_id": "Agente que executou o ticket e em cujo servidor a pasta de saida ficou",
        "file_count": "Quantidade de arquivos no zip",
        "size_bytes": "Tamanho do zip em bytes",
        "content": "Zip da pasta de saida do script (BLOB)",
    },
}


def _format_column(col_name, col_info):
    """Formata a declaracao de uma coluna em CREATE TABLE."""
    parts = [col_name, col_info["tipo"]]
    if col_info.get("default") is not None:
        parts.append("DEFAULT {}".format(col_info["default"]))
    if col_info.get("not_null"):
        parts.append("NOT NULL")
    return "    {}".format(" ".join(parts))


def build_ddl_statements(owner, prefix, lob_storage="SECUREFILE"):
    """Gera todas as instrucoes DDL em ordem estrita de fases (README §11.1).

    Fases:
      1. Sequences (sq_*)
      2. Tabelas sem FK (com LOB configurado)
      3. PK, UK e CK
      4. FKs
      5. Indices (incluindo FBIs e UNIQUE FBIs)
      6. Triggers (_bi e _bu de imutabilidade)

    Retorna lista de ItemDDL(fase, tipo, nome, sql, entidade).
    """
    sql_ident.validate_owner(owner)
    sql_ident.validate_prefix(prefix)
    schema = sql_ident.names(prefix)
    statements = []

    # -------------------------------------------------------------------------
    # FASE 1: Sequences
    # -------------------------------------------------------------------------
    for entity, t in schema.items():
        seq_name = t["sequence"]
        sql = "CREATE SEQUENCE {}.{} START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE".format(
            owner, seq_name
        )
        statements.append(DDLItem(1, "SEQUENCE", seq_name, sql, entity))

    # -------------------------------------------------------------------------
    # FASE 2: Tabelas
    # -------------------------------------------------------------------------
    for entity, t in schema.items():
        table_name = t["tabela"]
        rows_cols = [_format_column(c_name, c_info) for c_name, c_info in t["colunas"].items()]
        body = ",\n".join(rows_cols)

        # Clausula LOB
        columns_lob = t.get("colunas_lob", ())
        clause_lob = ""
        if columns_lob:
            lobs_str = ", ".join(columns_lob)
            if lob_storage == "BASICFILE":
                clause_lob = "\nLOB ({}) STORE AS BASICFILE".format(lobs_str)
            else:
                clause_lob = "\nLOB ({}) STORE AS SECUREFILE (CACHE)".format(lobs_str)

        sql = "CREATE TABLE {}.{} (\n{}\n){}".format(owner, table_name, body, clause_lob)
        statements.append(DDLItem(2, "TABLE", table_name, sql, entity))

    # -------------------------------------------------------------------------
    # FASE 3: Constraints (PK, UK, CK)
    # -------------------------------------------------------------------------
    for entity, t in schema.items():
        table_name = t["tabela"]

        # PK
        pk_name = t["pk"]
        columns_pk = ", ".join(sql_ident.TABLES[entity]["pk"]["colunas"])
        sql_pk = "ALTER TABLE {}.{} ADD CONSTRAINT {} PRIMARY KEY ({})".format(
            owner, table_name, pk_name, columns_pk
        )
        statements.append(DDLItem(3, "CONSTRAINT", pk_name, sql_pk, entity))

        # UKs
        for uk_name, uk_def in t["uks"].items():
            columns_uk = ", ".join(uk_def["colunas"])
            sql_uk = "ALTER TABLE {}.{} ADD CONSTRAINT {} UNIQUE ({})".format(
                owner, table_name, uk_name, columns_uk
            )
            statements.append(DDLItem(3, "CONSTRAINT", uk_name, sql_uk, entity))

        # CKs
        for ck_name, ck_def in t["cks"].items():
            expr_ck = ck_def["expr"]
            sql_ck = "ALTER TABLE {}.{} ADD CONSTRAINT {} CHECK ({})".format(
                owner, table_name, ck_name, expr_ck
            )
            statements.append(DDLItem(3, "CONSTRAINT", ck_name, sql_ck, entity))

    # -------------------------------------------------------------------------
    # FASE 4: Constraints (FK)
    # -------------------------------------------------------------------------
    for entity, t in schema.items():
        table_name = t["tabela"]
        for fk_name, fk_def in t["fks"].items():
            cols_fk = ", ".join(fk_def["colunas"])
            ref_table = fk_def["ref_tabela"]
            ref_cols = ", ".join(fk_def["ref_colunas"])
            on_del = " ON DELETE {}".format(fk_def["on_delete"]) if fk_def.get("on_delete") else ""
            sql_fk = "ALTER TABLE {}.{} ADD CONSTRAINT {} FOREIGN KEY ({}) REFERENCES {}.{} ({}){}".format(
                owner, table_name, fk_name, cols_fk, owner, ref_table, ref_cols, on_del
            )
            statements.append(DDLItem(4, "CONSTRAINT", fk_name, sql_fk, entity))

    # -------------------------------------------------------------------------
    # FASE 5: Indices
    # -------------------------------------------------------------------------
    for entity, t in schema.items():
        table_name = t["tabela"]
        for ix_name, ix_def in t["indices"].items():
            is_fbi = ix_def.get("fbi", False)
            is_single = ix_def.get("unico", False)

            if is_fbi:
                expr = ix_def["expr"]
                if is_single:
                    sql_ix = "CREATE UNIQUE INDEX {}.{} ON {}.{} {}".format(
                        owner, ix_name, owner, table_name, expr
                    )
                else:
                    sql_ix = "CREATE INDEX {}.{} ON {}.{} {}".format(
                        owner, ix_name, owner, table_name, expr
                    )
            else:
                cols_ix = ", ".join(ix_def["colunas"])
                sql_ix = "CREATE INDEX {}.{} ON {}.{} ({})".format(
                    owner, ix_name, owner, table_name, cols_ix
                )

            statements.append(DDLItem(5, "INDEX", ix_name, sql_ix, entity))

    # -------------------------------------------------------------------------
    # FASE 6: Triggers (_bi e _bu)
    # -------------------------------------------------------------------------
    for entity, t in schema.items():
        table_name = t["tabela"]
        seq_name = t["sequence"]
        tr_bi_name = t["trigger_bi"]

        # Trigger BEFORE INSERT condicional (template literal AGENTS §4.2) com cabecalho de governanca
        sql_tr_bi = (
            "-- ==============================================================================\n"
            "-- TRIGGER: {owner}.{trigger_name}\n"
            "-- TABELA ALVO: {owner}.{table_name}\n"
            "-- EVENTO: BEFORE INSERT ON {owner}.{table_name} FOR EACH ROW\n"
            "-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence\n"
            "-- {owner}.{sequence_name}. Preserva ID explicitamente informado (migracoes/carga).\n"
            "-- REGRA: AGENTS.md §4.2 e README §10.\n"
            "-- ==============================================================================\n"
            "CREATE OR REPLACE TRIGGER {owner}.{trigger_name}\n"
            "BEFORE INSERT ON {owner}.{table_name}\n"
            "FOR EACH ROW\n"
            "BEGIN\n"
            "    IF :NEW.id IS NULL THEN\n"
            "        SELECT {owner}.{sequence_name}.NEXTVAL INTO :NEW.id FROM DUAL;\n"
            "    END IF;\n"
            "END;"
        ).format(
            owner=owner,
            trigger_name=tr_bi_name,
            table_name=table_name,
            sequence_name=seq_name,
        )
        statements.append(DDLItem(6, "TRIGGER", tr_bi_name, sql_tr_bi, entity))

        # Trigger BEFORE UPDATE imutavel (quando configurada) com cabecalho de governanca
        if t.get("trigger_bu") and t.get("trigger_extra"):
            tr_bu_name = t["trigger_bu"]
            col_immutable = t["trigger_extra"]["coluna_imutavel"]
            sql_tr_bu = (
                "-- ==============================================================================\n"
                "-- TRIGGER: {owner}.{trigger_name}\n"
                "-- TABELA ALVO: {owner}.{table_name}\n"
                "-- EVENTO: BEFORE UPDATE ON {owner}.{table_name} FOR EACH ROW\n"
                "-- FINALIDADE DE GOVERNANCA: Garante a imutabilidade estrita da chave natural '{column}'.\n"
                "-- Bloqueia qualquer alteracao posterior de valor para preservar integridade de FKs.\n"
                "-- REGRA: README §10 e AGENTS.md §4.\n"
                "-- ==============================================================================\n"
                "CREATE OR REPLACE TRIGGER {owner}.{trigger_name}\n"
                "BEFORE UPDATE ON {owner}.{table_name}\n"
                "FOR EACH ROW\n"
                "BEGIN\n"
                "    IF :NEW.{column} <> :OLD.{column} THEN\n"
                "        RAISE_APPLICATION_ERROR(-20001, '{column} é imutável');\n"
                "    END IF;\n"
                "END;"
            ).format(
                owner=owner,
                trigger_name=tr_bu_name,
                table_name=table_name,
                column=col_immutable,
            )
            statements.append(DDLItem(6, "TRIGGER", tr_bu_name, sql_tr_bu, entity))

    return statements


def build_comment_statements(owner, prefix):
    """Gera declaracoes COMMENT ON TABLE e COMMENT ON COLUMN para todas as tabelas e colunas."""
    sql_ident.validate_owner(owner)
    sql_ident.validate_prefix(prefix)
    schema = sql_ident.names(prefix)
    commands = []

    for entity, t in schema.items():
        table_name = t["tabela"]
        desc_tab = TABLE_COMMENTS.get(entity, "Tabela {}".format(table_name))
        commands.append("COMMENT ON TABLE {}.{} IS '{}';".format(
            owner, table_name, _escape_sql(desc_tab)
        ))

        cols_entity = COLUMN_COMMENTS.get(entity, {})
        for c_name in t["colunas"]:
            if c_name in cols_entity:
                desc_col = cols_entity[c_name]
            elif c_name in RECORD_COLUMN_DESCRIPTIONS:
                desc_col = RECORD_COLUMN_DESCRIPTIONS[c_name]
            else:
                desc_col = "Coluna {} da tabela {}".format(c_name, table_name)
            commands.append("COMMENT ON COLUMN {}.{}.{} IS '{}';".format(
                owner, table_name, c_name, _escape_sql(desc_col)
            ))

    return commands


def build_ddl_script(owner, prefix, lob_storage="SECUREFILE", include_comments=True):
    """Gera script SQL completo pronto para visualizacao ou execucao via cliente."""
    statements = build_ddl_statements(owner, prefix, lob_storage=lob_storage)
    phases_titles = {
        1: "FASE 1: SEQUENCES",
        2: "FASE 2: TABELAS",
        3: "FASE 3: CONSTRAINTS (PK, UK, CK)",
        4: "FASE 4: CONSTRAINTS (FK)",
        5: "FASE 5: INDICES",
        6: "FASE 6: TRIGGERS",
    }

    rows = [
        "-- ==============================================================================",
        "-- Script Scheduling Service (SSS) - DDL Oracle 11gR2",
        "-- Gerado automaticamente a partir do registro sql_ident.py (F7.1)",
        "-- Owner: {}".format(owner),
        "-- Prefixo: {}".format(prefix),
        "-- LOB Storage: {}".format(lob_storage),
        "-- ==============================================================================",
        "",
    ]

    phase_current = None
    for item in statements:
        if item.phase != phase_current:
            phase_current = item.phase
            rows.extend([
                "-- ------------------------------------------------------------------------------",
                "-- {}".format(phases_titles.get(phase_current, "FASE %d" % phase_current)),
                "-- ------------------------------------------------------------------------------",
                "",
            ])

        if item.kind == "TRIGGER":
            rows.append(item.sql)
            rows.append("/")
            rows.append("")
        else:
            rows.append(item.sql + ";")
            rows.append("")

    if include_comments:
        comments = build_comment_statements(owner, prefix)
        if comments:
            rows.extend([
                "-- ------------------------------------------------------------------------------",
                "-- FASE 7: DICIONARIO E GOVERNANCA DE DADOS (COMMENTS)",
                "-- ------------------------------------------------------------------------------",
                "",
            ])
            for c in comments:
                rows.append(c)
            rows.append("")

    return "\n".join(rows)


GRANT_ROLES = ("web", "agent", "purge", "monitor")


def build_grants_by_role(owner, prefix, user_roles):
    """Gera comandos GRANT para os usuarios informados por papel (README §11.1).

    user_roles: dict com mapeamento papel -> usuario Oracle, ex:
      {'web': 'sss_web', 'agent': 'sss_agente', 'purge': 'sss_purge', 'monitor': 'sss_monitor'}

    Nunca concede a PUBLIC. A conta de cada papel e validada como identificador Oracle (entra no
    texto do GRANT). Papel sem conta ou cuja conta e a dona do esquema nao recebe GRANT: o owner ja
    tem todos os privilegios e GRANT para si mesmo falha (ORA-01749); fica um comentario no lugar.
    """
    sql_ident.validate_owner(owner)
    sql_ident.validate_prefix(prefix)
    schema = sql_ident.names(prefix)
    commands = []

    unknown = sorted(set(user_roles or {}) - set(GRANT_ROLES))
    if unknown:
        raise ValueError("Papel de GRANT desconhecido: {}".format(", ".join(unknown)))
    user_roles = dict(user_roles or {})
    for role in GRANT_ROLES:
        usr = user_roles.get(role)
        if not usr:
            commands.append("-- papel {}: conta nao informada; nenhum GRANT gerado".format(role))
            continue
        try:
            sql_ident.validate_owner(usr)
        except ValueError:
            raise ValueError("Conta Oracle invalida para o papel {}".format(role))
        if usr.upper() == "PUBLIC":
            raise ValueError("PUBLIC nao pode receber GRANT (papel {})".format(role))
        if usr.upper() == owner.upper():
            commands.append("-- papel {}: usa a conta dona do esquema ({}); nenhum GRANT necessario".format(
                role, owner))
            user_roles[role] = None

    # 1. PAPEL: web
    usr_web = user_roles.get("web")
    if usr_web:
        registries_and_schedules = (
            "environments", "profiles", "features", "scripts",
            "users", "parameters", "schedules"
        )
        for ent in registries_and_schedules:
            commands.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
                owner, schema[ent]["tabela"], usr_web
            ))

        associations = (
            "profile_feature", "profile_env", "profile_script", "script_env", "script_param"
        )
        for ent in associations:
            commands.append("GRANT SELECT, INSERT, UPDATE, DELETE ON {}.{} TO {};".format(
                owner, schema[ent]["tabela"], usr_web
            ))

        commands.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
            owner, schema["tickets"]["tabela"], usr_web
        ))
        commands.append("GRANT SELECT, INSERT ON {}.{} TO {};".format(
            owner, schema["ticket_answer"]["tabela"], usr_web
        ))
        commands.append("GRANT SELECT, INSERT ON {}.{} TO {};".format(
            owner, schema["audit"]["tabela"], usr_web
        ))
        commands.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, schema["agents"]["tabela"], usr_web
        ))
        commands.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, schema["control"]["tabela"], usr_web
        ))
        # Saida do ticket (CR-012): a web so le o zip para o download
        commands.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, schema["ticket_output"]["tabela"], usr_web
        ))

        # Sequences para web (todas exceto agentes, controle e ticket_output, que a web nao insere)
        for ent, t in schema.items():
            if ent not in ("agents", "control", "ticket_output"):
                commands.append("GRANT SELECT ON {}.{} TO {};".format(
                    owner, t["sequence"], usr_web
                ))

    # 2. PAPEL: agente
    usr_agt = user_roles.get("agent")
    if usr_agt:
        registries_and_assoc = (
            "environments", "profiles", "features", "profile_feature", "profile_env",
            "scripts", "profile_script", "script_env", "users", "parameters", "script_param"
        )
        for ent in registries_and_assoc:
            commands.append("GRANT SELECT ON {}.{} TO {};".format(
                owner, schema[ent]["tabela"], usr_agt
            ))

        commands.append("GRANT SELECT, UPDATE ON {}.{} TO {};".format(
            owner, schema["schedules"]["tabela"], usr_agt
        ))
        commands.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
            owner, schema["tickets"]["tabela"], usr_agt
        ))
        commands.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
            owner, schema["agents"]["tabela"], usr_agt
        ))
        commands.append("GRANT SELECT, INSERT ON {}.{} TO {};".format(
            owner, schema["ticket_answer"]["tabela"], usr_agt
        ))
        commands.append("GRANT INSERT ON {}.{} TO {};".format(
            owner, schema["audit"]["tabela"], usr_agt
        ))
        commands.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, schema["control"]["tabela"], usr_agt
        ))
        commands.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
            owner, schema["ticket_output"]["tabela"], usr_agt
        ))

        # Sequences do agente: tickets, respostas, agentes, auditoria e saida (CR-012)
        for ent in ("tickets", "ticket_answer", "agents", "audit", "ticket_output"):
            commands.append("GRANT SELECT ON {}.{} TO {};".format(
                owner, schema[ent]["sequence"], usr_agt
            ))

    # 3. PAPEL: purge
    usr_purge = user_roles.get("purge")
    if usr_purge:
        commands.append("GRANT SELECT, DELETE ON {}.{} TO {};".format(
            owner, schema["tickets"]["tabela"], usr_purge
        ))
        commands.append("GRANT SELECT, INSERT, DELETE ON {}.{} TO {};".format(
            owner, schema["audit"]["tabela"], usr_purge
        ))
        commands.append("GRANT SELECT, UPDATE (purge_owner, purge_lease_until) ON {}.{} TO {};".format(
            owner, schema["control"]["tabela"], usr_purge
        ))
        commands.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, schema["audit"]["sequence"], usr_purge
        ))

    # 4. PAPEL: monitor (CR-008, E3/R-04)
    # Somente SELECT nas 7 tabelas que health.py consulta, zero sequences
    usr_mon = user_roles.get("monitor")
    if usr_mon:
        tables_monitor = (
            "agents", "tickets", "schedules", "scripts",
            "environments", "control", "audit"
        )
        for ent in tables_monitor:
            commands.append("GRANT SELECT ON {}.{} TO {};".format(
                owner, schema[ent]["tabela"], usr_mon
            ))

    return commands


# -----------------------------------------------------------------------------
# DML Seed, Rollback e Script Completo de Implantacao
# -----------------------------------------------------------------------------

def _escape_sql(text):
    """Escapa aspas simples em literais SQL Oracle."""
    if text is None:
        return ""
    return str(text).replace("'", "''")


def build_seed_statements(owner, prefix, admin_login=None, admin_name=None, admin_password_hash=None):
    """Gera declaracoes SQL de seed inicial (Fase 7) via MERGE idempotente e estatisticas (Fase 8)."""
    sql_ident.validate_owner(owner)
    sql_ident.validate_prefix(prefix)
    schema = sql_ident.names(prefix)
    commands = []

    # 1. Funcionalidades canonicas
    tb_fea = "{}.{}".format(owner, schema["features"]["tabela"])
    sq_fea = "{}.{}".format(owner, schema["features"]["sequence"])
    for mod, code, name_disp, purpose in FEATURE_CATALOG:
        sql = (
            "MERGE INTO {tb} dst\n"
            "USING (SELECT '{code}' AS code FROM DUAL) src\n"
            "ON (dst.code = src.code)\n"
            "WHEN MATCHED THEN\n"
            "  UPDATE SET dst.name = '{name}',\n"
            "             dst.module = '{mod}',\n"
            "             dst.description = '{desc}',\n"
            "             dst.active = 'Y',\n"
            "             dst.updated_at = SYSDATE,\n"
            "             dst.updated_by = 'SYSTEM:init_db'\n"
            "  WHERE dst.active <> 'Y'\n"
            "     OR dst.name <> '{name}'\n"
            "     OR dst.module <> '{mod}'\n"
            "     OR dst.description <> '{desc}'\n"
            "WHEN NOT MATCHED THEN\n"
            "  INSERT (id, code, module, name, description, active, created_at, created_by)\n"
            "  VALUES ({sq}.NEXTVAL, '{code}', '{mod}', '{name}', '{desc}', 'Y', SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb=tb_fea,
            sq=sq_fea,
            code=_escape_sql(code),
            mod=_escape_sql(mod),
            name=_escape_sql(name_disp),
            desc=_escape_sql(purpose),
        )
        commands.append(sql)

    # 2. Ambientes padrao (inseridos antes dos perfis para permitir vinculo de profile_env)
    tb_env = "{}.{}".format(owner, schema["environments"]["tabela"])
    sq_env = "{}.{}".format(owner, schema["environments"]["sequence"])
    for env_name, env_desc, env_conn, env_prod in DEFAULT_ENVIRONMENTS:
        sql_env = (
            "MERGE INTO {tb} dst\n"
            "USING (SELECT '{name}' AS name FROM DUAL) src\n"
            "ON (dst.name = src.name)\n"
            "WHEN MATCHED THEN\n"
            "  UPDATE SET dst.description = '{desc}',\n"
            "             dst.connection = '{conn}',\n"
            "             dst.active = 'Y',\n"
            "             dst.updated_at = SYSDATE,\n"
            "             dst.updated_by = 'SYSTEM:init_db'\n"
            "  WHERE dst.active <> 'Y'\n"
            "     OR NVL(dst.description, '~') <> '{desc}'\n"
            "     OR NVL(dst.connection, '~') <> '{conn}'\n"
            "WHEN NOT MATCHED THEN\n"
            "  INSERT (id, name, description, connection, active, is_production, created_at, created_by)\n"
            "  VALUES ({sq}.NEXTVAL, '{name}', '{desc}', '{conn}', 'Y', '{prod}', SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb=tb_env,
            sq=sq_env,
            name=_escape_sql(env_name),
            desc=_escape_sql(env_desc),
            conn=_escape_sql(env_conn),
            prod=_escape_sql(env_prod),
        )
        commands.append(sql_env)

    # 3. Perfis padrao e matrizes de permissao (DEFAULT_PROFILES)
    tb_prf = "{}.{}".format(owner, schema["profiles"]["tabela"])
    sq_prf = "{}.{}".format(owner, schema["profiles"]["sequence"])
    tb_pfea = "{}.{}".format(owner, schema["profile_feature"]["tabela"])
    sq_pfea = "{}.{}".format(owner, schema["profile_feature"]["sequence"])
    tb_penv = "{}.{}".format(owner, schema["profile_env"]["tabela"])
    sq_penv = "{}.{}".format(owner, schema["profile_env"]["sequence"])

    for prf_name, prf_desc, is_adm, prf_features, prf_envs in DEFAULT_PROFILES:
        sql_prf = (
            "MERGE INTO {tb} dst\n"
            "USING (SELECT '{name}' AS name FROM DUAL) src\n"
            "ON (dst.name = src.name)\n"
            "WHEN MATCHED THEN\n"
            "  UPDATE SET dst.description = '{desc}',\n"
            "             dst.is_admin = '{is_adm}',\n"
            "             dst.active = 'Y',\n"
            "             dst.updated_at = SYSDATE,\n"
            "             dst.updated_by = 'SYSTEM:init_db'\n"
            "  WHERE dst.is_admin <> '{is_adm}'\n"
            "     OR dst.active <> 'Y'\n"
            "     OR NVL(dst.description, '~') <> '{desc}'\n"
            "WHEN NOT MATCHED THEN\n"
            "  INSERT (id, name, description, is_admin, perm_version, active, created_at, created_by)\n"
            "  VALUES ({sq}.NEXTVAL, '{name}', '{desc}', '{is_adm}', 1, 'Y', SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb=tb_prf, sq=sq_prf, name=_escape_sql(prf_name),
            desc=_escape_sql(prf_desc), is_adm=_escape_sql(is_adm)
        )
        commands.append(sql_prf)

        # 3a. Funcionalidades vinculadas ao perfil
        for f_code in prf_features:
            sql_pfea = (
                "MERGE INTO {tb_pfea} dst\n"
                "USING (\n"
                "  SELECT p.id AS profile_id, f.id AS feature_id\n"
                "    FROM {tb_prf} p, {tb_fea} f\n"
                "   WHERE p.name = '{prf_name}' AND f.code = '{f_code}'\n"
                ") src\n"
                "ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, profile_id, feature_id, created_at, created_by)\n"
                "  VALUES ({sq_pfea}.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');"
            ).format(
                tb_pfea=tb_pfea, sq_pfea=sq_pfea, tb_prf=tb_prf, tb_fea=tb_fea,
                prf_name=_escape_sql(prf_name), f_code=_escape_sql(f_code)
            )
            commands.append(sql_pfea)

        # 3b. Ambientes vinculados ao perfil
        for a_name in prf_envs:
            sql_penv = (
                "MERGE INTO {tb_penv} dst\n"
                "USING (\n"
                "  SELECT p.id AS profile_id, a.id AS environment_id\n"
                "    FROM {tb_prf} p, {tb_env} a\n"
                "   WHERE p.name = '{prf_name}' AND a.name = '{env_name}'\n"
                ") src\n"
                "ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, profile_id, environment_id, created_at, created_by)\n"
                "  VALUES ({sq_penv}.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');"
            ).format(
                tb_penv=tb_penv, sq_penv=sq_penv, tb_prf=tb_prf, tb_env=tb_env,
                prf_name=_escape_sql(prf_name), env_name=_escape_sql(a_name)
            )
            commands.append(sql_penv)

    # 4. Parametros padrao reutilizaveis
    tb_prm = "{}.{}".format(owner, schema["parameters"]["tabela"])
    sq_prm = "{}.{}".format(owner, schema["parameters"]["sequence"])
    for code, p_nom, lbl, desc, tcomp, opts, vpad in DEFAULT_PARAMETERS:
        pnom_sql = "'{}'".format(_escape_sql(p_nom)) if p_nom else "NULL"
        opts_sql = "'{}'".format(_escape_sql(opts)) if opts else "NULL"
        vpad_sql = "'{}'".format(_escape_sql(vpad)) if vpad else "NULL"
        sql_prm = (
            "MERGE INTO {tb} dst\n"
            "USING (SELECT '{code}' AS code FROM DUAL) src\n"
            "ON (dst.code = src.code)\n"
            "WHEN MATCHED THEN\n"
            "  UPDATE SET dst.param_flag = {pname},\n"
            "             dst.label = '{lbl}',\n"
            "             dst.description = '{desc}',\n"
            "             dst.component_type = '{ctype}',\n"
            "             dst.options_json = {opts},\n"
            "             dst.default_value = {vdef},\n"
            "             dst.sensitive = 'N',\n"
            "             dst.active = 'Y',\n"
            "             dst.updated_at = SYSDATE,\n"
            "             dst.updated_by = 'SYSTEM:init_db'\n"
            "  WHERE dst.active <> 'Y'\n"
            "     OR NVL(dst.param_flag, '~') <> NVL({pname}, '~')\n"
            "     OR dst.label <> '{lbl}'\n"
            "     OR NVL(dst.description, '~') <> '{desc}'\n"
            "     OR dst.component_type <> '{ctype}'\n"
            "     OR NVL(dst.options_json, '~') <> NVL({opts}, '~')\n"
            "     OR NVL(dst.default_value, '~') <> NVL({vdef}, '~')\n"
            "WHEN NOT MATCHED THEN\n"
            "  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)\n"
            "  VALUES ({sq}.NEXTVAL, '{code}', {pname}, '{lbl}', '{desc}', '{ctype}', {opts}, {vdef}, NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb=tb_prm, sq=sq_prm, code=_escape_sql(code), pname=pnom_sql,
            lbl=_escape_sql(lbl), desc=_escape_sql(desc), ctype=_escape_sql(tcomp),
            opts=opts_sql, vdef=vpad_sql
        )
        commands.append(sql_prm)

    # 5. Scripts utilitarios padrao
    tb_scr = "{}.{}".format(owner, schema["scripts"]["tabela"])
    sq_scr = "{}.{}".format(owner, schema["scripts"]["sequence"])
    tb_senv = "{}.{}".format(owner, schema["script_env"]["tabela"])
    sq_senv = "{}.{}".format(owner, schema["script_env"]["sequence"])
    tb_pscr = "{}.{}".format(owner, schema["profile_script"]["tabela"])
    sq_pscr = "{}.{}".format(owner, schema["profile_script"]["sequence"])
    tb_sprm = "{}.{}".format(owner, schema["script_param"]["tabela"])
    sq_sprm = "{}.{}".format(owner, schema["script_param"]["sequence"])

    for s_name, s_desc, s_grp, s_cat, s_etp, s_int, s_path, s_tpar, s_paral, s_tmout, s_params in DEFAULT_SCRIPTS:
        sql_scr = (
            "MERGE INTO {tb} dst\n"
            "USING (SELECT '{name}' AS name FROM DUAL) src\n"
            "ON (dst.name = src.name)\n"
            "WHEN MATCHED THEN\n"
            "  UPDATE SET dst.description = '{desc}',\n"
            "             dst.script_group = '{grp}',\n"
            "             dst.category = '{cat}',\n"
            "             dst.stage = '{stage}',\n"
            "             dst.interpreter = '{interp}',\n"
            "             dst.path_file = '{pfile}',\n"
            "             dst.param_type = '{ptype}',\n"
            "             dst.max_parallel_env = {par},\n"
            "             dst.timeout_s = {tmout},\n"
            "             dst.active = 'Y',\n"
            "             dst.updated_at = SYSDATE,\n"
            "             dst.updated_by = 'SYSTEM:init_db'\n"
            "  WHERE dst.active <> 'Y'\n"
            "     OR NVL(dst.description, '~') <> '{desc}'\n"
            "     OR NVL(dst.script_group, '~') <> '{grp}'\n"
            "     OR NVL(dst.category, '~') <> '{cat}'\n"
            "     OR NVL(dst.stage, '~') <> '{stage}'\n"
            "     OR dst.interpreter <> '{interp}'\n"
            "     OR dst.path_file <> '{pfile}'\n"
            "     OR dst.param_type <> '{ptype}'\n"
            "     OR dst.max_parallel_env <> {par}\n"
            "     OR NVL(dst.timeout_s, 0) <> {tmout}\n"
            "WHEN NOT MATCHED THEN\n"
            "  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)\n"
            "  VALUES ({sq}.NEXTVAL, '{name}', '{desc}', '{grp}', '{cat}', '{stage}', '{interp}', '{pfile}', '{ptype}', {par}, {tmout}, 'Y', SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb=tb_scr, sq=sq_scr, name=_escape_sql(s_name), desc=_escape_sql(s_desc),
            grp=_escape_sql(s_grp), cat=_escape_sql(s_cat), stage=_escape_sql(s_etp),
            interp=_escape_sql(s_int), pfile=_escape_sql(s_path), ptype=_escape_sql(s_tpar),
            par=s_paral, tmout=s_tmout
        )
        commands.append(sql_scr)

        # 5a. Homologacao do script nos 5 ambientes padrao
        for env_name, _, _, _ in DEFAULT_ENVIRONMENTS:
            sql_senv = (
                "MERGE INTO {tb_senv} dst\n"
                "USING (\n"
                "  SELECT s.id AS script_id, a.id AS environment_id\n"
                "    FROM {tb_scr} s, {tb_env} a\n"
                "   WHERE s.name = '{scr_name}' AND a.name = '{env_name}'\n"
                ") src\n"
                "ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, script_id, environment_id, created_at, created_by)\n"
                "  VALUES ({sq_senv}.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');"
            ).format(
                tb_senv=tb_senv, sq_senv=sq_senv, tb_scr=tb_scr, tb_env=tb_env,
                scr_name=_escape_sql(s_name), env_name=_escape_sql(env_name)
            )
            commands.append(sql_senv)

        # 5b. Permissao do script para os perfis operacionais e administradores
        for prf_name, _, _, _, _ in DEFAULT_PROFILES:
            sql_pscr = (
                "MERGE INTO {tb_pscr} dst\n"
                "USING (\n"
                "  SELECT p.id AS profile_id, s.id AS script_id\n"
                "    FROM {tb_prf} p, {tb_scr} s\n"
                "   WHERE p.name = '{prf_name}' AND s.name = '{scr_name}'\n"
                ") src\n"
                "ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, profile_id, script_id, created_at, created_by)\n"
                "  VALUES ({sq_pscr}.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');"
            ).format(
                tb_pscr=tb_pscr, sq_pscr=sq_pscr, tb_prf=tb_prf, tb_scr=tb_scr,
                prf_name=_escape_sql(prf_name), scr_name=_escape_sql(s_name)
            )
            commands.append(sql_pscr)

        # 5c. Vinculo dos parametros ao script
        for p_code, p_ord, p_req, p_vsub in s_params:
            vsub_sql = "'{}'".format(_escape_sql(p_vsub)) if p_vsub else "NULL"
            sql_sprm = (
                "MERGE INTO {tb_sprm} dst\n"
                "USING (\n"
                "  SELECT s.id AS script_id, p.id AS parameter_id\n"
                "    FROM {tb_scr} s, {tb_prm} p\n"
                "   WHERE s.name = '{scr_name}' AND p.code = '{p_code}'\n"
                ") src\n"
                "ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)\n"
                "WHEN MATCHED THEN\n"
                "  UPDATE SET dst.sort_order = {sort_order},\n"
                "             dst.required = '{req}',\n"
                "             dst.default_value_override = {vovr},\n"
                "             dst.updated_at = SYSDATE,\n"
                "             dst.updated_by = 'SYSTEM:init_db'\n"
                "  WHERE dst.sort_order <> {sort_order}\n"
                "     OR dst.required <> '{req}'\n"
                "     OR NVL(dst.default_value_override, '~') <> NVL({vovr}, '~')\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)\n"
                "  VALUES ({sq_sprm}.NEXTVAL, src.script_id, src.parameter_id, {sort_order}, '{req}', {vovr}, SYSDATE, 'SYSTEM:init_db');"
            ).format(
                tb_sprm=tb_sprm, sq_sprm=sq_sprm, tb_scr=tb_scr, tb_prm=tb_prm,
                scr_name=_escape_sql(s_name), p_code=_escape_sql(p_code),
                sort_order=p_ord, req=_escape_sql(p_req), vovr=vsub_sql
            )
            commands.append(sql_sprm)

    # 6. Controle de versao
    tb_ctl = "{}.{}".format(owner, schema["control"]["tabela"])
    sql_ctl = (
        "MERGE INTO {tb} dst\n"
        "USING (SELECT 1 AS id FROM DUAL) src\n"
        "ON (dst.id = src.id)\n"
        "WHEN NOT MATCHED THEN\n"
        "  INSERT (id, schema_version, version_applied_at, version_applied_by)\n"
        "  VALUES (1, {version}, SYSDATE, 'SYSTEM:init_db');"
    ).format(tb=tb_ctl, version=sql_ident.SCHEMA_VERSION)
    commands.append(sql_ctl)

    # 7. Usuarios padrao da aplicacao e homologacao (DEFAULT_USERS)
    tb_usr = "{}.{}".format(owner, schema["users"]["tabela"])
    sq_usr = "{}.{}".format(owner, schema["users"]["sequence"])

    for u_login, u_name, u_profile in DEFAULT_USERS:
        name_final = admin_name if (u_login == "admin" and admin_name) else u_name
        hash_final = admin_password_hash if (u_login == "admin" and admin_password_hash) else HOMOLOGATION_DEFAULT_PASSWORD_HASH
        sql_usr = (
            "MERGE INTO {tb_usr} dst\n"
            "USING (\n"
            "  SELECT '{login}' AS login, p.id AS profile_id\n"
            "    FROM {tb_prf} p\n"
            "   WHERE p.name = '{profile}'\n"
            ") src\n"
            "ON (dst.login = src.login)\n"
            "WHEN MATCHED THEN\n"
            "  UPDATE SET dst.name = '{name}',\n"
            "             dst.profile_id = src.profile_id,\n"
            "             dst.active = 'Y',\n"
            "             dst.updated_at = SYSDATE,\n"
            "             dst.updated_by = 'SYSTEM:init_db'\n"
            "  WHERE dst.name <> '{name}'\n"
            "     OR dst.profile_id <> src.profile_id\n"
            "     OR dst.active <> 'Y'\n"
            "WHEN NOT MATCHED THEN\n"
            "  INSERT (id, login, name, password_hash, profile_id, active, session_epoch, failed_attempts, created_at, created_by)\n"
            "  VALUES ({sq_usr}.NEXTVAL, '{login}', '{name}', '{hash_s}', src.profile_id, 'Y', 0, 0, SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb_usr=tb_usr,
            tb_prf=tb_prf,
            sq_usr=sq_usr,
            login=_escape_sql(u_login),
            name=_escape_sql(name_final),
            profile=_escape_sql(u_profile),
            hash_s=_escape_sql(hash_final),
        )
        commands.append(sql_usr)

    return commands


def build_seed_script(owner, prefix, admin_login=None, admin_name=None, admin_password_hash=None):
    """Gera script SQL puro com DML de seed, estatisticas e COMMIT pronto para SQL*Plus."""
    commands = build_seed_statements(
        owner, prefix,
        admin_login=admin_login,
        admin_name=admin_name,
        admin_password_hash=admin_password_hash
    )
    schema = sql_ident.names(prefix)
    owner_u = owner.upper()

    tables_stats = [
        schema["features"]["tabela"].upper(),
        schema["profiles"]["tabela"].upper(),
        schema["profile_feature"]["tabela"].upper(),
        schema["profile_env"]["tabela"].upper(),
        schema["environments"]["tabela"].upper(),
        schema["parameters"]["tabela"].upper(),
        schema["scripts"]["tabela"].upper(),
        schema["script_env"]["tabela"].upper(),
        schema["profile_script"]["tabela"].upper(),
        schema["script_param"]["tabela"].upper(),
        schema["control"]["tabela"].upper(),
        schema["users"]["tabela"].upper(),
    ]

    rows_stats = [
        "    DBMS_STATS.GATHER_TABLE_STATS(ownname => '{own}', tabname => '{tab}', cascade => TRUE);".format(
            own=owner_u, tab=t
        )
        for t in tables_stats
    ]

    rows = [
        "-- ------------------------------------------------------------------------------",
        "-- FASE 7: SEED INICIAL (MERGE IDEMPOTENTE)",
        "-- ------------------------------------------------------------------------------",
        "",
    ]
    for cmd in commands:
        rows.append(cmd)
        rows.append("")

    rows.extend([
        "-- ------------------------------------------------------------------------------",
        "-- FASE 8: ESTATISTICAS INICIAIS DO OTIMIZADOR (CR-007, R-29)",
        "-- ------------------------------------------------------------------------------",
        "BEGIN",
    ])
    rows.extend(rows_stats)
    rows.extend([
        "END;",
        "/",
        "",
        "COMMIT;",
        "",
    ])

    return "\n".join(rows)


ROLLBACK_ENTITY_ORDER = (
    "ticket_output",
    "ticket_answer",
    "tickets",
    "schedules",
    "script_param",
    "parameters",
    "script_env",
    "profile_script",
    "profile_env",
    "profile_feature",
    "scripts",
    "users",
    "features",
    "profiles",
    "environments",
    "agents",
    "audit",
    "control",
)


def build_rollback_statements(owner, prefix):
    """Gera lista de instrucoes DROP (Triggers, Tabelas com CASCADE PURGE e Sequences)."""
    sql_ident.validate_owner(owner)
    sql_ident.validate_prefix(prefix)
    schema = sql_ident.names(prefix)
    statements = []

    # 1. Triggers
    for entity in ROLLBACK_ENTITY_ORDER:
        t = schema[entity]
        if t.get("trigger_bu"):
            statements.append(("TRIGGER", t["trigger_bu"], "DROP TRIGGER {}.{};".format(owner, t["trigger_bu"])))
        if t.get("trigger_bi"):
            statements.append(("TRIGGER", t["trigger_bi"], "DROP TRIGGER {}.{};".format(owner, t["trigger_bi"])))

    # 2. Tabelas (Ordem reversa de dependencia com CASCADE CONSTRAINTS PURGE)
    for entity in ROLLBACK_ENTITY_ORDER:
        t = schema[entity]
        table = t["tabela"]
        statements.append(("TABLE", table, "DROP TABLE {}.{} CASCADE CONSTRAINTS PURGE;".format(owner, table)))

    # 3. Sequences
    for entity in ROLLBACK_ENTITY_ORDER:
        t = schema[entity]
        seq = t["sequence"]
        statements.append(("SEQUENCE", seq, "DROP SEQUENCE {}.{};".format(owner, seq)))

    return statements


def build_rollback_script(owner, prefix):
    """Gera script SQL puro para rollback total da implantacao no Oracle."""
    statements = build_rollback_statements(owner, prefix)

    rows = [
        "-- ==============================================================================",
        "-- Script Scheduling Service (SSS) - Rollback / Desinstalacao Oracle 11gR2+",
        "-- Gerado automaticamente a partir do registro sql_ident.py",
        "-- Owner: {}".format(owner),
        "-- Prefixo: {}".format(prefix),
        "-- ==============================================================================",
        "SET DEFINE OFF;",
        "SET SERVEROUTPUT ON;",
        "WHENEVER SQLERROR CONTINUE;",
        "",
        "-- ------------------------------------------------------------------------------",
        "-- 1. DROP TRIGGERS",
        "-- ------------------------------------------------------------------------------",
    ]

    for kind, name, sql in statements:
        if kind == "TRIGGER":
            rows.append(sql)

    rows.extend([
        "",
        "-- ------------------------------------------------------------------------------",
        "-- 2. DROP TABELAS (CASCADE CONSTRAINTS PURGE)",
        "-- ------------------------------------------------------------------------------",
    ])
    for kind, name, sql in statements:
        if kind == "TABLE":
            rows.append(sql)

    rows.extend([
        "",
        "-- ------------------------------------------------------------------------------",
        "-- 3. DROP SEQUENCES",
        "-- ------------------------------------------------------------------------------",
    ])
    for kind, name, sql in statements:
        if kind == "SEQUENCE":
            rows.append(sql)

    rows.extend([
        "",
        "PROMPT Rollback do SSS concluido com sucesso.",
        "EXIT;",
        "",
    ])

    return "\n".join(rows)


def _literal_list(names):
    """Lista IN de literais com nomes do registro sql_ident (ja validados), em maiusculas.

    Quebra a cada 6 nomes: o SQL*Plus recusa linhas com mais de 2.499 caracteres (SP2-0027).
    """
    literals = ["'{}'".format(n.upper()) for n in names]
    groups = [", ".join(literals[i:i + 6]) for i in range(0, len(literals), 6)]
    return ",\n      ".join(groups)


def _seed_rows_by_table(owner, prefix):
    """Quantidade de MERGE do seed por tabela (minimo esperado logo apos a implantacao)."""
    schema = sql_ident.names(prefix)
    by_table = dict((t["tabela"].upper(), ent) for ent, t in schema.items())
    count = collections.OrderedDict((ent, 0) for ent in schema)
    mark = "MERGE INTO {}.".format(owner).upper()
    for cmd in build_seed_statements(owner, prefix):
        text = cmd.lstrip()
        if text.upper().startswith(mark):
            ent = by_table.get(text[len(mark):].split(None, 1)[0].upper())
            if ent:
                count[ent] += 1
    return count


def build_validation_script(owner, prefix):
    """Gera o 99_validate_deploy.sql a partir do registro sql_ident (SQL*Plus, somente leitura).

    Compara esperado x encontrado: objetos (tabelas, sequences, triggers, constraints e indices pelos
    nomes do registro), objetos invalidos, GRANTs a PUBLIC (proibidos), versao do esquema e o minimo de
    linhas do seed. Cada verificacao sai com OK ou FALHA e um resumo final. Owner e prefixo vem dos
    parametros; nenhum hash de senha e exibido (AGENTS §3.3), so se a senha esta definida.
    """
    sql_ident.validate_owner(owner)
    sql_ident.validate_prefix(prefix)
    schema = sql_ident.names(prefix)
    own = owner.upper()

    tables = [t["tabela"] for t in schema.values()]
    sequences = [t["sequence"] for t in schema.values()]
    triggers = []
    constraints = []
    indexes = []
    for t in schema.values():
        triggers.extend(n for n in (t.get("trigger_bi"), t.get("trigger_bu")) if n)
        constraints.append(t["pk"])
        for group in ("uks", "fks", "cks"):
            constraints.extend(t[group].keys())
        indexes.extend(t["indices"].keys())
    objects = tables + sequences + triggers + indexes

    def chk(order, label, rule, value, sql_contagem):
        return ("SELECT {o} AS sort_order, '{r}' AS verificacao, '{g}' AS regra, {v} AS esperado, "
                "({s}) AS encontrado FROM DUAL").format(o=order, r=label, g=rule, v=value, s=sql_contagem)

    mapping = [
        chk(1, "TABELAS", "=", len(tables),
            "SELECT COUNT(*) FROM all_tables WHERE owner = '{}' AND table_name IN ({})".format(
                own, _literal_list(tables))),
        chk(2, "SEQUENCES", "=", len(sequences),
            "SELECT COUNT(*) FROM all_sequences WHERE sequence_owner = '{}' AND sequence_name IN ({})".format(
                own, _literal_list(sequences))),
        chk(3, "TRIGGERS HABILITADAS", "=", len(triggers),
            "SELECT COUNT(*) FROM all_triggers WHERE owner = '{}' AND status = 'ENABLED' "
            "AND trigger_name IN ({})".format(own, _literal_list(triggers))),
        chk(4, "CONSTRAINTS HABILITADAS", "=", len(constraints),
            "SELECT COUNT(*) FROM all_constraints WHERE owner = '{}' AND status = 'ENABLED' "
            "AND constraint_name IN ({})".format(own, _literal_list(constraints))),
        chk(5, "INDICES VALIDOS", "=", len(indexes),
            "SELECT COUNT(*) FROM all_indexes WHERE owner = '{}' AND status = 'VALID' "
            "AND index_name IN ({})".format(own, _literal_list(indexes))),
        chk(6, "OBJETOS INVALIDOS", "=", 0,
            "SELECT COUNT(*) FROM all_objects WHERE owner = '{}' AND status = 'INVALID' "
            "AND object_name IN ({})".format(own, _literal_list(objects))),
        chk(7, "GRANTS A PUBLIC", "=", 0,
            "SELECT COUNT(*) FROM all_tab_privs WHERE table_schema = '{}' AND grantee = 'PUBLIC' "
            "AND table_name IN ({})".format(own, _literal_list(tables + sequences))),
    ]

    tab = dict((ent, "{}.{}".format(owner, t["tabela"])) for ent, t in schema.items())
    data = [
        chk(10, "VERSAO DO ESQUEMA", "=", sql_ident.SCHEMA_VERSION,
            "SELECT MAX(schema_version) FROM {}".format(tab["control"])),
    ]
    for n, (ent, min_value) in enumerate(_seed_rows_by_table(owner, prefix).items()):
        data.append(chk(11 + n, "LINHAS " + schema[ent]["tabela"].upper(), ">=", min_value,
                         "SELECT COUNT(*) FROM {}".format(tab[ent])))

    def relatorio(parts):
        union = "\n  UNION ALL ".join(parts)
        detail = (
            "WITH chk AS (\n  " + union + "\n)\n"
            "SELECT verificacao, regra || ' ' || esperado AS esperado, encontrado,\n"
            "       CASE WHEN (regra = '=' AND encontrado = esperado) OR (regra = '>=' AND encontrado >= esperado)\n"
            "            THEN 'OK' ELSE 'FALHA' END AS resultado\n"
            "  FROM chk ORDER BY sort_order;"
        )
        summary = (
            "WITH chk AS (\n  " + union + "\n)\n"
            "SELECT CASE WHEN COUNT(*) = 0 THEN 'OK: nenhuma falha'\n"
            "            ELSE 'FALHA: ' || COUNT(*) || ' verificacao(oes) divergente(s)' END AS resumo\n"
            "  FROM chk\n"
            " WHERE NOT ((regra = '=' AND encontrado = esperado) OR (regra = '>=' AND encontrado >= esperado))\n"
            "    OR encontrado IS NULL;"
        )
        return [detail, "", summary]

    rows = [
        "-- ==============================================================================",
        "-- Script Scheduling Service (SSS) - Validacao da Implantacao Oracle 11gR2+",
        "-- Gerado automaticamente a partir do registro sql_ident.py (somente leitura)",
        "-- Owner: {}".format(owner),
        "-- Prefixo: {}".format(prefix),
        "-- Cada verificacao mostra OK ou FALHA; procure tambem ORA-/SP2- no SPOOL.",
        "-- ==============================================================================",
        "SET DEFINE OFF;",
        "SET LINESIZE 200 PAGESIZE 200 FEEDBACK OFF VERIFY OFF ECHO OFF TRIMSPOOL ON;",
        "WHENEVER SQLERROR CONTINUE;",
        "COLUMN verificacao FORMAT A40",
        "COLUMN esperado FORMAT A12",
        "COLUMN encontrado FORMAT 999999999",
        "COLUMN resultado FORMAT A9",
        "COLUMN resumo FORMAT A60",
        "",
        "PROMPT ==============================================================================",
        "PROMPT 1. OBJETOS NO DICIONARIO (esperado pelo registro x encontrado)",
        "PROMPT ==============================================================================",
    ]
    rows.extend(relatorio(mapping))
    rows.extend([
        "",
        "PROMPT ==============================================================================",
        "PROMPT 2. VERSAO DO ESQUEMA E MINIMO DE LINHAS DO SEED",
        "PROMPT (se as tabelas nao existirem, esta secao falha com ORA-00942: veja a secao 1)",
        "PROMPT ==============================================================================",
    ])
    rows.extend(relatorio(data))
    rows.extend([
        "",
        "PROMPT ==============================================================================",
        "PROMPT 3. USUARIOS E PERFIS (sem hash de senha)",
        "PROMPT ==============================================================================",
        "COLUMN login FORMAT A20",
        "COLUMN name FORMAT A30",
        "COLUMN perfil FORMAT A20",
        "COLUMN admin FORMAT A5",
        "COLUMN active FORMAT A5",
        "COLUMN senha_definida FORMAT A14",
        "SELECT u.id, u.login, u.name, p.name AS perfil, p.is_admin AS admin, u.active,",
        "       CASE WHEN u.password_hash IS NULL THEN 'N' ELSE 'Y' END AS senha_definida",
        "  FROM {} u JOIN {} p ON p.id = u.profile_id".format(tab["users"], tab["profiles"]),
        " ORDER BY u.id;",
        "",
        "PROMPT ==============================================================================",
        "PROMPT 4. SCRIPTS CADASTRADOS",
        "PROMPT ==============================================================================",
        "COLUMN name FORMAT A25",
        "COLUMN interpreter FORMAT A8",
        "COLUMN param_type FORMAT A10",
        "COLUMN path_file FORMAT A70",
        "SELECT id, name, interpreter, param_type, max_parallel_env AS paral, timeout_s AS tmout,",
        "       active, path_file",
        "  FROM {}".format(tab["scripts"]),
        " ORDER BY id;",
        "",
        "PROMPT ==============================================================================",
        "PROMPT 5. ACESSO POR PERFIL (funcionalidades, ambientes e scripts liberados)",
        "PROMPT ==============================================================================",
        "COLUMN perfil FORMAT A20",
        "SELECT p.name AS perfil, p.is_admin AS admin, p.active,",
        "       (SELECT COUNT(*) FROM {} x WHERE x.profile_id = p.id) AS funcionalidades,".format(tab["profile_feature"]),
        "       (SELECT COUNT(*) FROM {} x WHERE x.profile_id = p.id) AS environments,".format(tab["profile_env"]),
        "       (SELECT COUNT(*) FROM {} x WHERE x.profile_id = p.id) AS scripts".format(tab["profile_script"]),
        "  FROM {} p".format(tab["profiles"]),
        " ORDER BY p.name;",
        "",
        "PROMPT ==============================================================================",
        "PROMPT 6. GRANTS NOS OBJETOS DO SSS (README 11.1: so contas dos papeis; nunca PUBLIC)",
        "PROMPT ==============================================================================",
        "SET FEEDBACK ON",
        "COLUMN grantee FORMAT A30",
        "COLUMN privilege FORMAT A12",
        "SELECT grantee, privilege, COUNT(*) AS objetos",
        "  FROM all_tab_privs",
        " WHERE table_schema = '{}' AND table_name IN ({})".format(own, _literal_list(tables + sequences)),
        " GROUP BY grantee, privilege",
        " ORDER BY grantee, privilege;",
        "SET FEEDBACK OFF",
        "",
        "PROMPT Fim da validacao do SSS.",
        "EXIT;",
        "",
    ])
    return "\n".join(rows)


def build_full_deploy_script(owner, prefix, lob_storage="SECUREFILE",
                                      admin_login=None, admin_name=None, admin_password_hash=None,
                                      user_roles=None):
    """Gera script SQL autocontido com DDL, DML Seed, Estatisticas e Grants para execucao direta.

    Para no primeiro erro (WHENEVER SQLERROR EXIT FAILURE ROLLBACK, revisao de 2026-10-20): um
    esquema parcial nunca e anunciado como sucesso. Reaplicar exige o 02_rollback antes (ciclo
    02 -> 01 -> 99). Os GRANTs seguem so os papeis do README §11.1; nada e concedido a PUBLIC
    (tbsss_users guarda password_hash).
    """
    sql_ddl = build_ddl_script(owner, prefix, lob_storage=lob_storage)
    sql_seed = build_seed_script(
        owner, prefix,
        admin_login=admin_login,
        admin_name=admin_name,
        admin_password_hash=admin_password_hash
    )

    parts = [
        "SET DEFINE OFF;",
        "SET SERVEROUTPUT ON;",
        "-- Qualquer erro interrompe a implantacao com codigo de saida diferente de zero e sem a mensagem de",
        "-- sucesso. Para reaplicar sobre um esquema existente, rode antes o 02_rollback_sss.sql.",
        "WHENEVER SQLERROR EXIT FAILURE ROLLBACK;",
        "WHENEVER OSERROR EXIT FAILURE ROLLBACK;",
        "",
        sql_ddl,
        "",
        sql_seed,
    ]

    parts.extend([
        "-- ==============================================================================",
        "-- GRANTS POR PAPEL (README §11.1); nenhum GRANT a PUBLIC",
        "-- ==============================================================================",
        "",
    ])
    parts.extend(build_grants_by_role(owner, prefix, user_roles or {}))
    parts.append("")

    parts.extend([
        "PROMPT Implantacao do SSS concluida com sucesso!",
        "EXIT;",
        "",
    ])

    return "\n".join(parts)

