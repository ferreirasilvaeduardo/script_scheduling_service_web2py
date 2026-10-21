# -*- coding: utf-8 -*-
"""Construtor puro de DDL e seed Oracle 11gR2 a partir de sql_ident (F7.1).

Gera instrucoes DDL fase a fase, sem importar drivers Oracle nem depender do web2py.
Totalmente idempotente e aderente ao README §9, §10, §11.1 e AGENTS §4.
"""
import collections

import sql_ident

# Estrutura representativa de uma instrucao DDL
ItemDDL = collections.namedtuple("ItemDDL", [
    "fase", "tipo", "nome", "sql", "entidade"
])

# Catalogo canonico de funcionalidades (README §4.3.D)
# Tuplas: (modulo, codigo, nome_exibicao, finalidade)
CATALOGO_FUNCIONALIDADES = (
    ("OPERATION", "EXEC_SCRIPT", "Disparar Scripts", "Preencher questionários e abrir tickets"),
    ("OPERATION", "VIEW_LOGS", "Consultar Logs", "Visualizar logs e histórico em tempo quase real"),
    ("OPERATION", "CANCEL_TICKET", "Cancelar Tickets", "Cancelar tickets de terceiros em ambientes autorizados"),
    ("ADMIN", "MANAGE_USERS", "Gestão de Usuários", "Gerenciar operadores e credenciais"),
    ("ADMIN", "MANAGE_PROFILES", "Gestão de Perfis", "Gerenciar perfis e matrizes de permissão"),
    ("ADMIN", "MANAGE_ENVIRONMENTS", "Gestão de Ambientes", "Gerenciar ambientes e DSNs"),
    ("ADMIN", "MANAGE_SCRIPTS", "Gestão de Scripts", "Cadastrar rotinas e homologação por ambiente"),
    ("ADMIN", "MANAGE_PARAMETERS", "Dicionário de Parâmetros", "Gerenciar perguntas e flags reutilizáveis"),
    ("ADMIN", "MANAGE_SCHEDULES", "Regras de Agendamento", "Criar e gerenciar recorrências"),
    ("ADMIN", "VIEW_AUDIT", "Auditoria", "Consultar a trilha de auditoria e os agentes"),
)

# Catalogo padrao de ambientes atendidos (nome, descricao, conexao)
CATALOGO_AMBIENTES_PADRAO = (
    ("CLONE2", "BRTLVLTS1199PL (10.238.10.209)", "10.238.55.146/gfprod"),
    ("CLONE1", "BRTLVLTS1198PL (10.238.10.208)", "10.238.55.145/gfprod"),
    ("CLONE6", "BRTLVLTS3089SL (10.238.10.210)", "10.238.45.230/svc_gfprodc6"),
    ("CLONE7", "BRTLVLTS1216PL (10.238.10.109)", "10.238.45.230/svc_gfprodc7"),
    ("GFPREPROD", "BRTLVLTY3067SL (10.129.177.188)", "10.129.177.188/GFPR"),
)

# Catalogo padrao de perfis operacionais e administrativos (nome, descricao, is_admin, funcionalidades, ambientes)
CATALOGO_PERFIS_PADRAO = (
    ("ADMINISTRATOR", "Acesso irrestrito a todas as funcionalidades e ambientes", "Y", (
        "EXEC_SCRIPT", "VIEW_LOGS", "CANCEL_TICKET", "MANAGE_USERS", "MANAGE_PROFILES",
        "MANAGE_ENVIRONMENTS", "MANAGE_SCRIPTS", "MANAGE_PARAMETERS", "MANAGE_SCHEDULES", "VIEW_AUDIT"
    ), ("CLONE2", "CLONE1", "CLONE6", "CLONE7", "GFPREPROD")),
    ("OPERATOR_PROD", "Operador de Ambientes de Producao", "N", (
        "EXEC_SCRIPT", "VIEW_LOGS", "CANCEL_TICKET"
    ), ("CLONE2", "CLONE1", "CLONE6", "CLONE7", "GFPREPROD")),
    ("OPERATOR_HML", "Operador de Ambientes de Homologacao", "N", (
        "EXEC_SCRIPT", "VIEW_LOGS", "CANCEL_TICKET"
    ), ("CLONE6", "CLONE7", "GFPREPROD")),
    ("READ_ONLY", "Perfil de Apenas Leitura e Consulta", "N", (
        "VIEW_LOGS",
    ), ("CLONE2", "CLONE1", "CLONE6", "CLONE7", "GFPREPROD")),
)

# Catalogo padrao de usuarios de homologacao e demonstracao (login, nome, perfil_nome)
CATALOGO_USUARIOS_PADRAO = (
    ("admin", "Super Administrador", "ADMINISTRATOR"),
    ("op.prod", "Operador Producao", "OPERATOR_PROD"),
    ("op.hml", "Operador Homologacao", "OPERATOR_HML"),
    ("consulta", "Auditor e Consulta", "READ_ONLY"),
)

# Hash PBKDF2 da senha padrao de homologacao/demonstracao (senha: Sss@Homolog2026!)
HASH_SENHA_PADRAO_HOMOLOGACAO = "pbkdf2_sha256$200000$8007db1bd770663178d0f1b1a129140c$9d9604af27e21326e982e5e7c64bfdd868c0995a97181b5a9695149755852d63"

# Catalogo padrao de parametros reutilizaveis de utilitarios (codigo, param_nomeado, label, descricao, tipo, opcoes, vpadrao)
CATALOGO_PARAMETROS_PADRAO = (
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

# Catalogo padrao de scripts utilitarios de demonstracao (nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_paral, timeout_seg, params)
CATALOGO_SCRIPTS_PADRAO = (
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
COLUNAS_REGISTRO_DESCRICOES = {
    "created_at": "Data e hora da criacao do registro no banco de dados (imutavel)",
    "created_by": "Identificador do usuario ou servico responsavel pela criacao (imutavel)",
    "updated_at": "Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)",
    "updated_by": "Identificador do usuario ou servico responsavel pela ultima alteracao",
}

DICIONARIO_TABELAS = {
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

DICIONARIO_COLUNAS = {
    "environments": {
        "id": "Identificador unico sequencial do ambiente (chave primaria)",
        "name": "Nome mnemonico unico do ambiente em maiusculas (chave natural imutavel)",
        "description": "Descricao detalhada do ambiente, servidor host e finalidade",
        "connection": "String de conexao ou alias DSN/TNS sugerido para o banco de dados do ambiente",
        "active": "Indicador de vigencia do ambiente (Y=Ativo, N=Inativo)",
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


def _formatar_coluna(col_nome, col_info):
    """Formata a declaracao de uma coluna em CREATE TABLE."""
    partes = [col_nome, col_info["tipo"]]
    if col_info.get("default") is not None:
        partes.append("DEFAULT {}".format(col_info["default"]))
    if col_info.get("not_null"):
        partes.append("NOT NULL")
    return "    {}".format(" ".join(partes))


def gerar_instrucoes_ddl(owner, prefixo, lob_storage="SECUREFILE"):
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
    sql_ident.validate_prefix(prefixo)
    esquema = sql_ident.names(prefixo)
    instrucoes = []

    # -------------------------------------------------------------------------
    # FASE 1: Sequences
    # -------------------------------------------------------------------------
    for entidade, t in esquema.items():
        seq_nome = t["sequence"]
        sql = "CREATE SEQUENCE {}.{} START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE".format(
            owner, seq_nome
        )
        instrucoes.append(ItemDDL(1, "SEQUENCE", seq_nome, sql, entidade))

    # -------------------------------------------------------------------------
    # FASE 2: Tabelas
    # -------------------------------------------------------------------------
    for entidade, t in esquema.items():
        tabela_nome = t["tabela"]
        linhas_cols = [_formatar_coluna(c_nome, c_info) for c_nome, c_info in t["colunas"].items()]
        corpo = ",\n".join(linhas_cols)

        # Clausula LOB
        colunas_lob = t.get("colunas_lob", ())
        clausula_lob = ""
        if colunas_lob:
            lobs_str = ", ".join(colunas_lob)
            if lob_storage == "BASICFILE":
                clausula_lob = "\nLOB ({}) STORE AS BASICFILE".format(lobs_str)
            else:
                clausula_lob = "\nLOB ({}) STORE AS SECUREFILE (CACHE)".format(lobs_str)

        sql = "CREATE TABLE {}.{} (\n{}\n){}".format(owner, tabela_nome, corpo, clausula_lob)
        instrucoes.append(ItemDDL(2, "TABLE", tabela_nome, sql, entidade))

    # -------------------------------------------------------------------------
    # FASE 3: Constraints (PK, UK, CK)
    # -------------------------------------------------------------------------
    for entidade, t in esquema.items():
        tabela_nome = t["tabela"]

        # PK
        pk_nome = t["pk"]
        colunas_pk = ", ".join(sql_ident.TABLES[entidade]["pk"]["colunas"])
        sql_pk = "ALTER TABLE {}.{} ADD CONSTRAINT {} PRIMARY KEY ({})".format(
            owner, tabela_nome, pk_nome, colunas_pk
        )
        instrucoes.append(ItemDDL(3, "CONSTRAINT", pk_nome, sql_pk, entidade))

        # UKs
        for uk_nome, uk_def in t["uks"].items():
            colunas_uk = ", ".join(uk_def["colunas"])
            sql_uk = "ALTER TABLE {}.{} ADD CONSTRAINT {} UNIQUE ({})".format(
                owner, tabela_nome, uk_nome, colunas_uk
            )
            instrucoes.append(ItemDDL(3, "CONSTRAINT", uk_nome, sql_uk, entidade))

        # CKs
        for ck_nome, ck_def in t["cks"].items():
            expr_ck = ck_def["expr"]
            sql_ck = "ALTER TABLE {}.{} ADD CONSTRAINT {} CHECK ({})".format(
                owner, tabela_nome, ck_nome, expr_ck
            )
            instrucoes.append(ItemDDL(3, "CONSTRAINT", ck_nome, sql_ck, entidade))

    # -------------------------------------------------------------------------
    # FASE 4: Constraints (FK)
    # -------------------------------------------------------------------------
    for entidade, t in esquema.items():
        tabela_nome = t["tabela"]
        for fk_nome, fk_def in t["fks"].items():
            cols_fk = ", ".join(fk_def["colunas"])
            ref_tabela = fk_def["ref_tabela"]
            ref_cols = ", ".join(fk_def["ref_colunas"])
            on_del = " ON DELETE {}".format(fk_def["on_delete"]) if fk_def.get("on_delete") else ""
            sql_fk = "ALTER TABLE {}.{} ADD CONSTRAINT {} FOREIGN KEY ({}) REFERENCES {}.{} ({}){}".format(
                owner, tabela_nome, fk_nome, cols_fk, owner, ref_tabela, ref_cols, on_del
            )
            instrucoes.append(ItemDDL(4, "CONSTRAINT", fk_nome, sql_fk, entidade))

    # -------------------------------------------------------------------------
    # FASE 5: Indices
    # -------------------------------------------------------------------------
    for entidade, t in esquema.items():
        tabela_nome = t["tabela"]
        for ix_nome, ix_def in t["indices"].items():
            is_fbi = ix_def.get("fbi", False)
            is_unico = ix_def.get("unico", False)

            if is_fbi:
                expr = ix_def["expr"]
                if is_unico:
                    sql_ix = "CREATE UNIQUE INDEX {}.{} ON {}.{} {}".format(
                        owner, ix_nome, owner, tabela_nome, expr
                    )
                else:
                    sql_ix = "CREATE INDEX {}.{} ON {}.{} {}".format(
                        owner, ix_nome, owner, tabela_nome, expr
                    )
            else:
                cols_ix = ", ".join(ix_def["colunas"])
                sql_ix = "CREATE INDEX {}.{} ON {}.{} ({})".format(
                    owner, ix_nome, owner, tabela_nome, cols_ix
                )

            instrucoes.append(ItemDDL(5, "INDEX", ix_nome, sql_ix, entidade))

    # -------------------------------------------------------------------------
    # FASE 6: Triggers (_bi e _bu)
    # -------------------------------------------------------------------------
    for entidade, t in esquema.items():
        tabela_nome = t["tabela"]
        seq_nome = t["sequence"]
        tr_bi_nome = t["trigger_bi"]

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
            trigger_name=tr_bi_nome,
            table_name=tabela_nome,
            sequence_name=seq_nome,
        )
        instrucoes.append(ItemDDL(6, "TRIGGER", tr_bi_nome, sql_tr_bi, entidade))

        # Trigger BEFORE UPDATE imutavel (quando configurada) com cabecalho de governanca
        if t.get("trigger_bu") and t.get("trigger_extra"):
            tr_bu_nome = t["trigger_bu"]
            col_imutavel = t["trigger_extra"]["coluna_imutavel"]
            sql_tr_bu = (
                "-- ==============================================================================\n"
                "-- TRIGGER: {owner}.{trigger_name}\n"
                "-- TABELA ALVO: {owner}.{table_name}\n"
                "-- EVENTO: BEFORE UPDATE ON {owner}.{table_name} FOR EACH ROW\n"
                "-- FINALIDADE DE GOVERNANCA: Garante a imutabilidade estrita da chave natural '{coluna}'.\n"
                "-- Bloqueia qualquer alteracao posterior de valor para preservar integridade de FKs.\n"
                "-- REGRA: README §10 e AGENTS.md §4.\n"
                "-- ==============================================================================\n"
                "CREATE OR REPLACE TRIGGER {owner}.{trigger_name}\n"
                "BEFORE UPDATE ON {owner}.{table_name}\n"
                "FOR EACH ROW\n"
                "BEGIN\n"
                "    IF :NEW.{coluna} <> :OLD.{coluna} THEN\n"
                "        RAISE_APPLICATION_ERROR(-20001, '{coluna} é imutável');\n"
                "    END IF;\n"
                "END;"
            ).format(
                owner=owner,
                trigger_name=tr_bu_nome,
                table_name=tabela_nome,
                coluna=col_imutavel,
            )
            instrucoes.append(ItemDDL(6, "TRIGGER", tr_bu_nome, sql_tr_bu, entidade))

    return instrucoes


def gerar_instrucoes_comentarios(owner, prefixo):
    """Gera declaracoes COMMENT ON TABLE e COMMENT ON COLUMN para todas as tabelas e colunas."""
    sql_ident.validate_owner(owner)
    sql_ident.validate_prefix(prefixo)
    esquema = sql_ident.names(prefixo)
    comandos = []

    for entidade, t in esquema.items():
        tabela_nome = t["tabela"]
        desc_tab = DICIONARIO_TABELAS.get(entidade, "Tabela {}".format(tabela_nome))
        comandos.append("COMMENT ON TABLE {}.{} IS '{}';".format(
            owner, tabela_nome, _escape_sql(desc_tab)
        ))

        cols_entidade = DICIONARIO_COLUNAS.get(entidade, {})
        for c_nome in t["colunas"]:
            if c_nome in cols_entidade:
                desc_col = cols_entidade[c_nome]
            elif c_nome in COLUNAS_REGISTRO_DESCRICOES:
                desc_col = COLUNAS_REGISTRO_DESCRICOES[c_nome]
            else:
                desc_col = "Coluna {} da tabela {}".format(c_nome, tabela_nome)
            comandos.append("COMMENT ON COLUMN {}.{}.{} IS '{}';".format(
                owner, tabela_nome, c_nome, _escape_sql(desc_col)
            ))

    return comandos


def gerar_script_ddl(owner, prefixo, lob_storage="SECUREFILE", incluir_comentarios=True):
    """Gera script SQL completo pronto para visualizacao ou execucao via cliente."""
    instrucoes = gerar_instrucoes_ddl(owner, prefixo, lob_storage=lob_storage)
    fases_titulos = {
        1: "FASE 1: SEQUENCES",
        2: "FASE 2: TABELAS",
        3: "FASE 3: CONSTRAINTS (PK, UK, CK)",
        4: "FASE 4: CONSTRAINTS (FK)",
        5: "FASE 5: INDICES",
        6: "FASE 6: TRIGGERS",
    }

    linhas = [
        "-- ==============================================================================",
        "-- Script Scheduling Service (SSS) - DDL Oracle 11gR2",
        "-- Gerado automaticamente a partir do registro sql_ident.py (F7.1)",
        "-- Owner: {}".format(owner),
        "-- Prefixo: {}".format(prefixo),
        "-- LOB Storage: {}".format(lob_storage),
        "-- ==============================================================================",
        "",
    ]

    fase_atual = None
    for item in instrucoes:
        if item.fase != fase_atual:
            fase_atual = item.fase
            linhas.extend([
                "-- ------------------------------------------------------------------------------",
                "-- {}".format(fases_titulos.get(fase_atual, "FASE %d" % fase_atual)),
                "-- ------------------------------------------------------------------------------",
                "",
            ])

        if item.tipo == "TRIGGER":
            linhas.append(item.sql)
            linhas.append("/")
            linhas.append("")
        else:
            linhas.append(item.sql + ";")
            linhas.append("")

    if incluir_comentarios:
        comentarios = gerar_instrucoes_comentarios(owner, prefixo)
        if comentarios:
            linhas.extend([
                "-- ------------------------------------------------------------------------------",
                "-- FASE 7: DICIONARIO E GOVERNANCA DE DADOS (COMMENTS)",
                "-- ------------------------------------------------------------------------------",
                "",
            ])
            for c in comentarios:
                linhas.append(c)
            linhas.append("")

    return "\n".join(linhas)


PAPEIS_GRANT = ("web", "agent", "purge", "monitor")


def gerar_grants_por_papel(owner, prefixo, papeis_usuarios):
    """Gera comandos GRANT para os usuarios informados por papel (README §11.1).

    papeis_usuarios: dict com mapeamento papel -> usuario_oracle, ex:
      {'web': 'sss_web', 'agent': 'sss_agente', 'purge': 'sss_purge', 'monitor': 'sss_monitor'}

    Nunca concede a PUBLIC. A conta de cada papel e validada como identificador Oracle (entra no
    texto do GRANT). Papel sem conta ou cuja conta e a dona do esquema nao recebe GRANT: o owner ja
    tem todos os privilegios e GRANT para si mesmo falha (ORA-01749); fica um comentario no lugar.
    """
    sql_ident.validate_owner(owner)
    sql_ident.validate_prefix(prefixo)
    esquema = sql_ident.names(prefixo)
    comandos = []

    desconhecidos = sorted(set(papeis_usuarios or {}) - set(PAPEIS_GRANT))
    if desconhecidos:
        raise ValueError("Papel de GRANT desconhecido: {}".format(", ".join(desconhecidos)))
    papeis_usuarios = dict(papeis_usuarios or {})
    for papel in PAPEIS_GRANT:
        usr = papeis_usuarios.get(papel)
        if not usr:
            comandos.append("-- papel {}: conta nao informada; nenhum GRANT gerado".format(papel))
            continue
        try:
            sql_ident.validate_owner(usr)
        except ValueError:
            raise ValueError("Conta Oracle invalida para o papel {}".format(papel))
        if usr.upper() == "PUBLIC":
            raise ValueError("PUBLIC nao pode receber GRANT (papel {})".format(papel))
        if usr.upper() == owner.upper():
            comandos.append("-- papel {}: usa a conta dona do esquema ({}); nenhum GRANT necessario".format(
                papel, owner))
            papeis_usuarios[papel] = None

    # 1. PAPEL: web
    usr_web = papeis_usuarios.get("web")
    if usr_web:
        cadastros_e_agendamentos = (
            "environments", "profiles", "features", "scripts",
            "users", "parameters", "schedules"
        )
        for ent in cadastros_e_agendamentos:
            comandos.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
                owner, esquema[ent]["tabela"], usr_web
            ))

        associacoes = (
            "profile_feature", "profile_env", "profile_script", "script_env", "script_param"
        )
        for ent in associacoes:
            comandos.append("GRANT SELECT, INSERT, UPDATE, DELETE ON {}.{} TO {};".format(
                owner, esquema[ent]["tabela"], usr_web
            ))

        comandos.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
            owner, esquema["tickets"]["tabela"], usr_web
        ))
        comandos.append("GRANT SELECT, INSERT ON {}.{} TO {};".format(
            owner, esquema["ticket_answer"]["tabela"], usr_web
        ))
        comandos.append("GRANT SELECT, INSERT ON {}.{} TO {};".format(
            owner, esquema["audit"]["tabela"], usr_web
        ))
        comandos.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, esquema["agents"]["tabela"], usr_web
        ))
        comandos.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, esquema["control"]["tabela"], usr_web
        ))
        # Saida do ticket (CR-012): a web so le o zip para o download
        comandos.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, esquema["ticket_output"]["tabela"], usr_web
        ))

        # Sequences para web (todas exceto agentes, controle e ticket_saida, que a web nao insere)
        for ent, t in esquema.items():
            if ent not in ("agents", "control", "ticket_output"):
                comandos.append("GRANT SELECT ON {}.{} TO {};".format(
                    owner, t["sequence"], usr_web
                ))

    # 2. PAPEL: agente
    usr_agt = papeis_usuarios.get("agent")
    if usr_agt:
        cadastros_e_assoc = (
            "environments", "profiles", "features", "profile_feature", "profile_env",
            "scripts", "profile_script", "script_env", "users", "parameters", "script_param"
        )
        for ent in cadastros_e_assoc:
            comandos.append("GRANT SELECT ON {}.{} TO {};".format(
                owner, esquema[ent]["tabela"], usr_agt
            ))

        comandos.append("GRANT SELECT, UPDATE ON {}.{} TO {};".format(
            owner, esquema["schedules"]["tabela"], usr_agt
        ))
        comandos.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
            owner, esquema["tickets"]["tabela"], usr_agt
        ))
        comandos.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
            owner, esquema["agents"]["tabela"], usr_agt
        ))
        comandos.append("GRANT SELECT, INSERT ON {}.{} TO {};".format(
            owner, esquema["ticket_answer"]["tabela"], usr_agt
        ))
        comandos.append("GRANT INSERT ON {}.{} TO {};".format(
            owner, esquema["audit"]["tabela"], usr_agt
        ))
        comandos.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, esquema["control"]["tabela"], usr_agt
        ))
        comandos.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
            owner, esquema["ticket_output"]["tabela"], usr_agt
        ))

        # Sequences do agente: tickets, respostas, agentes, auditoria e saida (CR-012)
        for ent in ("tickets", "ticket_answer", "agents", "audit", "ticket_output"):
            comandos.append("GRANT SELECT ON {}.{} TO {};".format(
                owner, esquema[ent]["sequence"], usr_agt
            ))

    # 3. PAPEL: purge
    usr_purge = papeis_usuarios.get("purge")
    if usr_purge:
        comandos.append("GRANT SELECT, DELETE ON {}.{} TO {};".format(
            owner, esquema["tickets"]["tabela"], usr_purge
        ))
        comandos.append("GRANT SELECT, INSERT, DELETE ON {}.{} TO {};".format(
            owner, esquema["audit"]["tabela"], usr_purge
        ))
        comandos.append("GRANT SELECT, UPDATE (purge_owner, purge_lease_until) ON {}.{} TO {};".format(
            owner, esquema["control"]["tabela"], usr_purge
        ))
        comandos.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, esquema["audit"]["sequence"], usr_purge
        ))

    # 4. PAPEL: monitor (CR-008, E3/R-04)
    # Somente SELECT nas 7 tabelas que health.py consulta, zero sequences
    usr_mon = papeis_usuarios.get("monitor")
    if usr_mon:
        tabelas_monitor = (
            "agents", "tickets", "schedules", "scripts",
            "environments", "control", "audit"
        )
        for ent in tabelas_monitor:
            comandos.append("GRANT SELECT ON {}.{} TO {};".format(
                owner, esquema[ent]["tabela"], usr_mon
            ))

    return comandos


# -----------------------------------------------------------------------------
# DML Seed, Rollback e Script Completo de Implantacao
# -----------------------------------------------------------------------------

def _escape_sql(texto):
    """Escapa aspas simples em literais SQL Oracle."""
    if texto is None:
        return ""
    return str(texto).replace("'", "''")


def gerar_instrucoes_seed(owner, prefixo, admin_login=None, admin_nome=None, admin_senha_hash=None):
    """Gera declaracoes SQL de seed inicial (Fase 7) via MERGE idempotente e estatisticas (Fase 8)."""
    sql_ident.validate_owner(owner)
    sql_ident.validate_prefix(prefixo)
    esquema = sql_ident.names(prefixo)
    comandos = []

    # 1. Funcionalidades canonicas
    tb_fnc = "{}.{}".format(owner, esquema["features"]["tabela"])
    sq_fnc = "{}.{}".format(owner, esquema["features"]["sequence"])
    for mod, cod, nome_exib, finalidade in CATALOGO_FUNCIONALIDADES:
        sql = (
            "MERGE INTO {tb} dst\n"
            "USING (SELECT '{cod}' AS code FROM DUAL) src\n"
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
            "  VALUES ({sq}.NEXTVAL, '{cod}', '{mod}', '{name}', '{desc}', 'Y', SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb=tb_fnc,
            sq=sq_fnc,
            cod=_escape_sql(cod),
            mod=_escape_sql(mod),
            name=_escape_sql(nome_exib),
            desc=_escape_sql(finalidade),
        )
        comandos.append(sql)

    # 2. Ambientes padrao (inseridos antes dos perfis para permitir vinculo de perfil_amb)
    tb_amb = "{}.{}".format(owner, esquema["environments"]["tabela"])
    sq_amb = "{}.{}".format(owner, esquema["environments"]["sequence"])
    for amb_nome, amb_desc, amb_conn in CATALOGO_AMBIENTES_PADRAO:
        sql_amb = (
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
            "  INSERT (id, name, description, connection, active, created_at, created_by)\n"
            "  VALUES ({sq}.NEXTVAL, '{name}', '{desc}', '{conn}', 'Y', SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb=tb_amb,
            sq=sq_amb,
            name=_escape_sql(amb_nome),
            desc=_escape_sql(amb_desc),
            conn=_escape_sql(amb_conn),
        )
        comandos.append(sql_amb)

    # 3. Perfis padrao e matrizes de permissao (CATALOGO_PERFIS_PADRAO)
    tb_per = "{}.{}".format(owner, esquema["profiles"]["tabela"])
    sq_per = "{}.{}".format(owner, esquema["profiles"]["sequence"])
    tb_pfnc = "{}.{}".format(owner, esquema["profile_feature"]["tabela"])
    sq_pfnc = "{}.{}".format(owner, esquema["profile_feature"]["sequence"])
    tb_pamb = "{}.{}".format(owner, esquema["profile_env"]["tabela"])
    sq_pamb = "{}.{}".format(owner, esquema["profile_env"]["sequence"])

    for per_nome, per_desc, is_adm, per_funcs, per_ambs in CATALOGO_PERFIS_PADRAO:
        sql_per = (
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
            tb=tb_per, sq=sq_per, name=_escape_sql(per_nome),
            desc=_escape_sql(per_desc), is_adm=_escape_sql(is_adm)
        )
        comandos.append(sql_per)

        # 3a. Funcionalidades vinculadas ao perfil
        for f_cod in per_funcs:
            sql_pfnc = (
                "MERGE INTO {tb_pfnc} dst\n"
                "USING (\n"
                "  SELECT p.id AS profile_id, f.id AS feature_id\n"
                "    FROM {tb_per} p, {tb_fnc} f\n"
                "   WHERE p.name = '{per_nome}' AND f.code = '{f_cod}'\n"
                ") src\n"
                "ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, profile_id, feature_id, created_at, created_by)\n"
                "  VALUES ({sq_pfnc}.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');"
            ).format(
                tb_pfnc=tb_pfnc, sq_pfnc=sq_pfnc, tb_per=tb_per, tb_fnc=tb_fnc,
                per_nome=_escape_sql(per_nome), f_cod=_escape_sql(f_cod)
            )
            comandos.append(sql_pfnc)

        # 3b. Ambientes vinculados ao perfil
        for a_nome in per_ambs:
            sql_pamb = (
                "MERGE INTO {tb_pamb} dst\n"
                "USING (\n"
                "  SELECT p.id AS profile_id, a.id AS environment_id\n"
                "    FROM {tb_per} p, {tb_amb} a\n"
                "   WHERE p.name = '{per_nome}' AND a.name = '{a_nome}'\n"
                ") src\n"
                "ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, profile_id, environment_id, created_at, created_by)\n"
                "  VALUES ({sq_pamb}.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');"
            ).format(
                tb_pamb=tb_pamb, sq_pamb=sq_pamb, tb_per=tb_per, tb_amb=tb_amb,
                per_nome=_escape_sql(per_nome), a_nome=_escape_sql(a_nome)
            )
            comandos.append(sql_pamb)

    # 4. Parametros padrao reutilizaveis
    tb_prm = "{}.{}".format(owner, esquema["parameters"]["tabela"])
    sq_prm = "{}.{}".format(owner, esquema["parameters"]["sequence"])
    for cod, p_nom, lbl, desc, tcomp, opc, vpad in CATALOGO_PARAMETROS_PADRAO:
        pnom_sql = "'{}'".format(_escape_sql(p_nom)) if p_nom else "NULL"
        opc_sql = "'{}'".format(_escape_sql(opc)) if opc else "NULL"
        vpad_sql = "'{}'".format(_escape_sql(vpad)) if vpad else "NULL"
        sql_prm = (
            "MERGE INTO {tb} dst\n"
            "USING (SELECT '{cod}' AS code FROM DUAL) src\n"
            "ON (dst.code = src.code)\n"
            "WHEN MATCHED THEN\n"
            "  UPDATE SET dst.param_flag = {pnom},\n"
            "             dst.label = '{lbl}',\n"
            "             dst.description = '{desc}',\n"
            "             dst.component_type = '{tcomp}',\n"
            "             dst.options_json = {opc},\n"
            "             dst.default_value = {vpad},\n"
            "             dst.sensitive = 'N',\n"
            "             dst.active = 'Y',\n"
            "             dst.updated_at = SYSDATE,\n"
            "             dst.updated_by = 'SYSTEM:init_db'\n"
            "  WHERE dst.active <> 'Y'\n"
            "     OR NVL(dst.param_flag, '~') <> NVL({pnom}, '~')\n"
            "     OR dst.label <> '{lbl}'\n"
            "     OR NVL(dst.description, '~') <> '{desc}'\n"
            "     OR dst.component_type <> '{tcomp}'\n"
            "     OR NVL(dst.options_json, '~') <> NVL({opc}, '~')\n"
            "     OR NVL(dst.default_value, '~') <> NVL({vpad}, '~')\n"
            "WHEN NOT MATCHED THEN\n"
            "  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)\n"
            "  VALUES ({sq}.NEXTVAL, '{cod}', {pnom}, '{lbl}', '{desc}', '{tcomp}', {opc}, {vpad}, NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb=tb_prm, sq=sq_prm, cod=_escape_sql(cod), pnom=pnom_sql,
            lbl=_escape_sql(lbl), desc=_escape_sql(desc), tcomp=_escape_sql(tcomp),
            opc=opc_sql, vpad=vpad_sql
        )
        comandos.append(sql_prm)

    # 5. Scripts utilitarios padrao
    tb_scr = "{}.{}".format(owner, esquema["scripts"]["tabela"])
    sq_scr = "{}.{}".format(owner, esquema["scripts"]["sequence"])
    tb_samb = "{}.{}".format(owner, esquema["script_env"]["tabela"])
    sq_samb = "{}.{}".format(owner, esquema["script_env"]["sequence"])
    tb_pscr = "{}.{}".format(owner, esquema["profile_script"]["tabela"])
    sq_pscr = "{}.{}".format(owner, esquema["profile_script"]["sequence"])
    tb_sprm = "{}.{}".format(owner, esquema["script_param"]["tabela"])
    sq_sprm = "{}.{}".format(owner, esquema["script_param"]["sequence"])

    for s_nome, s_desc, s_grp, s_cat, s_etp, s_int, s_path, s_tpar, s_paral, s_tmout, s_params in CATALOGO_SCRIPTS_PADRAO:
        sql_scr = (
            "MERGE INTO {tb} dst\n"
            "USING (SELECT '{name}' AS name FROM DUAL) src\n"
            "ON (dst.name = src.name)\n"
            "WHEN MATCHED THEN\n"
            "  UPDATE SET dst.description = '{desc}',\n"
            "             dst.script_group = '{grp}',\n"
            "             dst.category = '{cat}',\n"
            "             dst.stage = '{etp}',\n"
            "             dst.interpreter = '{interp}',\n"
            "             dst.path_file = '{pfile}',\n"
            "             dst.param_type = '{tpar}',\n"
            "             dst.max_parallel_env = {paral},\n"
            "             dst.timeout_s = {tmout},\n"
            "             dst.active = 'Y',\n"
            "             dst.updated_at = SYSDATE,\n"
            "             dst.updated_by = 'SYSTEM:init_db'\n"
            "  WHERE dst.active <> 'Y'\n"
            "     OR NVL(dst.description, '~') <> '{desc}'\n"
            "     OR NVL(dst.script_group, '~') <> '{grp}'\n"
            "     OR NVL(dst.category, '~') <> '{cat}'\n"
            "     OR NVL(dst.stage, '~') <> '{etp}'\n"
            "     OR dst.interpreter <> '{interp}'\n"
            "     OR dst.path_file <> '{pfile}'\n"
            "     OR dst.param_type <> '{tpar}'\n"
            "     OR dst.max_parallel_env <> {paral}\n"
            "     OR NVL(dst.timeout_s, 0) <> {tmout}\n"
            "WHEN NOT MATCHED THEN\n"
            "  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)\n"
            "  VALUES ({sq}.NEXTVAL, '{name}', '{desc}', '{grp}', '{cat}', '{etp}', '{interp}', '{pfile}', '{tpar}', {paral}, {tmout}, 'Y', SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb=tb_scr, sq=sq_scr, name=_escape_sql(s_nome), desc=_escape_sql(s_desc),
            grp=_escape_sql(s_grp), cat=_escape_sql(s_cat), etp=_escape_sql(s_etp),
            interp=_escape_sql(s_int), pfile=_escape_sql(s_path), tpar=_escape_sql(s_tpar),
            paral=s_paral, tmout=s_tmout
        )
        comandos.append(sql_scr)

        # 5a. Homologacao do script nos 5 ambientes padrao
        for amb_nome, _, _ in CATALOGO_AMBIENTES_PADRAO:
            sql_samb = (
                "MERGE INTO {tb_samb} dst\n"
                "USING (\n"
                "  SELECT s.id AS script_id, a.id AS environment_id\n"
                "    FROM {tb_scr} s, {tb_amb} a\n"
                "   WHERE s.name = '{s_nome}' AND a.name = '{amb_nome}'\n"
                ") src\n"
                "ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, script_id, environment_id, created_at, created_by)\n"
                "  VALUES ({sq_samb}.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');"
            ).format(
                tb_samb=tb_samb, sq_samb=sq_samb, tb_scr=tb_scr, tb_amb=tb_amb,
                s_nome=_escape_sql(s_nome), amb_nome=_escape_sql(amb_nome)
            )
            comandos.append(sql_samb)

        # 5b. Permissao do script para os perfis operacionais e administradores
        for per_nome, _, _, _, _ in CATALOGO_PERFIS_PADRAO:
            sql_pscr = (
                "MERGE INTO {tb_pscr} dst\n"
                "USING (\n"
                "  SELECT p.id AS profile_id, s.id AS script_id\n"
                "    FROM {tb_per} p, {tb_scr} s\n"
                "   WHERE p.name = '{per_nome}' AND s.name = '{s_nome}'\n"
                ") src\n"
                "ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, profile_id, script_id, created_at, created_by)\n"
                "  VALUES ({sq_pscr}.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');"
            ).format(
                tb_pscr=tb_pscr, sq_pscr=sq_pscr, tb_per=tb_per, tb_scr=tb_scr,
                per_nome=_escape_sql(per_nome), s_nome=_escape_sql(s_nome)
            )
            comandos.append(sql_pscr)

        # 5c. Vinculo dos parametros ao script
        for p_cod, p_ord, p_obrig, p_vsub in s_params:
            vsub_sql = "'{}'".format(_escape_sql(p_vsub)) if p_vsub else "NULL"
            sql_sprm = (
                "MERGE INTO {tb_sprm} dst\n"
                "USING (\n"
                "  SELECT s.id AS script_id, p.id AS parameter_id\n"
                "    FROM {tb_scr} s, {tb_prm} p\n"
                "   WHERE s.name = '{s_nome}' AND p.code = '{p_cod}'\n"
                ") src\n"
                "ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)\n"
                "WHEN MATCHED THEN\n"
                "  UPDATE SET dst.sort_order = {sort_order},\n"
                "             dst.required = '{obrig}',\n"
                "             dst.default_value_override = {vsub},\n"
                "             dst.updated_at = SYSDATE,\n"
                "             dst.updated_by = 'SYSTEM:init_db'\n"
                "  WHERE dst.sort_order <> {sort_order}\n"
                "     OR dst.required <> '{obrig}'\n"
                "     OR NVL(dst.default_value_override, '~') <> NVL({vsub}, '~')\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)\n"
                "  VALUES ({sq_sprm}.NEXTVAL, src.script_id, src.parameter_id, {sort_order}, '{obrig}', {vsub}, SYSDATE, 'SYSTEM:init_db');"
            ).format(
                tb_sprm=tb_sprm, sq_sprm=sq_sprm, tb_scr=tb_scr, tb_prm=tb_prm,
                s_nome=_escape_sql(s_nome), p_cod=_escape_sql(p_cod),
                sort_order=p_ord, obrig=_escape_sql(p_obrig), vsub=vsub_sql
            )
            comandos.append(sql_sprm)

    # 6. Controle de versao
    tb_ctl = "{}.{}".format(owner, esquema["control"]["tabela"])
    sql_ctl = (
        "MERGE INTO {tb} dst\n"
        "USING (SELECT 1 AS id FROM DUAL) src\n"
        "ON (dst.id = src.id)\n"
        "WHEN NOT MATCHED THEN\n"
        "  INSERT (id, schema_version, version_applied_at, version_applied_by)\n"
        "  VALUES (1, {version}, SYSDATE, 'SYSTEM:init_db');"
    ).format(tb=tb_ctl, version=sql_ident.SCHEMA_VERSION)
    comandos.append(sql_ctl)

    # 7. Usuarios padrao da aplicacao e homologacao (CATALOGO_USUARIOS_PADRAO)
    tb_usr = "{}.{}".format(owner, esquema["users"]["tabela"])
    sq_usr = "{}.{}".format(owner, esquema["users"]["sequence"])

    for u_login, u_nome, u_perfil in CATALOGO_USUARIOS_PADRAO:
        nome_final = admin_nome if (u_login == "admin" and admin_nome) else u_nome
        hash_final = admin_senha_hash if (u_login == "admin" and admin_senha_hash) else HASH_SENHA_PADRAO_HOMOLOGACAO
        sql_usr = (
            "MERGE INTO {tb_usr} dst\n"
            "USING (\n"
            "  SELECT '{login}' AS login, p.id AS profile_id\n"
            "    FROM {tb_per} p\n"
            "   WHERE p.name = '{perfil}'\n"
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
            tb_per=tb_per,
            sq_usr=sq_usr,
            login=_escape_sql(u_login),
            name=_escape_sql(nome_final),
            perfil=_escape_sql(u_perfil),
            hash_s=_escape_sql(hash_final),
        )
        comandos.append(sql_usr)

    return comandos


def gerar_script_seed(owner, prefixo, admin_login=None, admin_nome=None, admin_senha_hash=None):
    """Gera script SQL puro com DML de seed, estatisticas e COMMIT pronto para SQL*Plus."""
    comandos = gerar_instrucoes_seed(
        owner, prefixo,
        admin_login=admin_login,
        admin_nome=admin_nome,
        admin_senha_hash=admin_senha_hash
    )
    esquema = sql_ident.names(prefixo)
    owner_u = owner.upper()

    tabelas_stats = [
        esquema["features"]["tabela"].upper(),
        esquema["profiles"]["tabela"].upper(),
        esquema["profile_feature"]["tabela"].upper(),
        esquema["profile_env"]["tabela"].upper(),
        esquema["environments"]["tabela"].upper(),
        esquema["parameters"]["tabela"].upper(),
        esquema["scripts"]["tabela"].upper(),
        esquema["script_env"]["tabela"].upper(),
        esquema["profile_script"]["tabela"].upper(),
        esquema["script_param"]["tabela"].upper(),
        esquema["control"]["tabela"].upper(),
        esquema["users"]["tabela"].upper(),
    ]

    linhas_stats = [
        "    DBMS_STATS.GATHER_TABLE_STATS(ownname => '{own}', tabname => '{tab}', cascade => TRUE);".format(
            own=owner_u, tab=t
        )
        for t in tabelas_stats
    ]

    linhas = [
        "-- ------------------------------------------------------------------------------",
        "-- FASE 7: SEED INICIAL (MERGE IDEMPOTENTE)",
        "-- ------------------------------------------------------------------------------",
        "",
    ]
    for cmd in comandos:
        linhas.append(cmd)
        linhas.append("")

    linhas.extend([
        "-- ------------------------------------------------------------------------------",
        "-- FASE 8: ESTATISTICAS INICIAIS DO OTIMIZADOR (CR-007, R-29)",
        "-- ------------------------------------------------------------------------------",
        "BEGIN",
    ])
    linhas.extend(linhas_stats)
    linhas.extend([
        "END;",
        "/",
        "",
        "COMMIT;",
        "",
    ])

    return "\n".join(linhas)


ORDEM_ROLLBACK_ENTIDADES = (
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


def gerar_instrucoes_rollback(owner, prefixo):
    """Gera lista de instrucoes DROP (Triggers, Tabelas com CASCADE PURGE e Sequences)."""
    sql_ident.validate_owner(owner)
    sql_ident.validate_prefix(prefixo)
    esquema = sql_ident.names(prefixo)
    instrucoes = []

    # 1. Triggers
    for entidade in ORDEM_ROLLBACK_ENTIDADES:
        t = esquema[entidade]
        if t.get("trigger_bu"):
            instrucoes.append(("TRIGGER", t["trigger_bu"], "DROP TRIGGER {}.{};".format(owner, t["trigger_bu"])))
        if t.get("trigger_bi"):
            instrucoes.append(("TRIGGER", t["trigger_bi"], "DROP TRIGGER {}.{};".format(owner, t["trigger_bi"])))

    # 2. Tabelas (Ordem reversa de dependencia com CASCADE CONSTRAINTS PURGE)
    for entidade in ORDEM_ROLLBACK_ENTIDADES:
        t = esquema[entidade]
        tabela = t["tabela"]
        instrucoes.append(("TABLE", tabela, "DROP TABLE {}.{} CASCADE CONSTRAINTS PURGE;".format(owner, tabela)))

    # 3. Sequences
    for entidade in ORDEM_ROLLBACK_ENTIDADES:
        t = esquema[entidade]
        seq = t["sequence"]
        instrucoes.append(("SEQUENCE", seq, "DROP SEQUENCE {}.{};".format(owner, seq)))

    return instrucoes


def gerar_script_rollback(owner, prefixo):
    """Gera script SQL puro para rollback total da implantacao no Oracle."""
    instrucoes = gerar_instrucoes_rollback(owner, prefixo)

    linhas = [
        "-- ==============================================================================",
        "-- Script Scheduling Service (SSS) - Rollback / Desinstalacao Oracle 11gR2+",
        "-- Gerado automaticamente a partir do registro sql_ident.py",
        "-- Owner: {}".format(owner),
        "-- Prefixo: {}".format(prefixo),
        "-- ==============================================================================",
        "SET DEFINE OFF;",
        "SET SERVEROUTPUT ON;",
        "WHENEVER SQLERROR CONTINUE;",
        "",
        "-- ------------------------------------------------------------------------------",
        "-- 1. DROP TRIGGERS",
        "-- ------------------------------------------------------------------------------",
    ]

    for tipo, nome, sql in instrucoes:
        if tipo == "TRIGGER":
            linhas.append(sql)

    linhas.extend([
        "",
        "-- ------------------------------------------------------------------------------",
        "-- 2. DROP TABELAS (CASCADE CONSTRAINTS PURGE)",
        "-- ------------------------------------------------------------------------------",
    ])
    for tipo, nome, sql in instrucoes:
        if tipo == "TABLE":
            linhas.append(sql)

    linhas.extend([
        "",
        "-- ------------------------------------------------------------------------------",
        "-- 3. DROP SEQUENCES",
        "-- ------------------------------------------------------------------------------",
    ])
    for tipo, nome, sql in instrucoes:
        if tipo == "SEQUENCE":
            linhas.append(sql)

    linhas.extend([
        "",
        "PROMPT Rollback do SSS concluido com sucesso.",
        "EXIT;",
        "",
    ])

    return "\n".join(linhas)


def _lista_literais(nomes):
    """Lista IN de literais com nomes do registro sql_ident (ja validados), em maiusculas.

    Quebra a cada 6 nomes: o SQL*Plus recusa linhas com mais de 2.499 caracteres (SP2-0027).
    """
    literais = ["'{}'".format(n.upper()) for n in nomes]
    grupos = [", ".join(literais[i:i + 6]) for i in range(0, len(literais), 6)]
    return ",\n      ".join(grupos)


def _linhas_seed_por_tabela(owner, prefixo):
    """Quantidade de MERGE do seed por tabela (minimo esperado logo apos a implantacao)."""
    esquema = sql_ident.names(prefixo)
    por_tabela = dict((t["tabela"].upper(), ent) for ent, t in esquema.items())
    contagem = collections.OrderedDict((ent, 0) for ent in esquema)
    marca = "MERGE INTO {}.".format(owner).upper()
    for cmd in gerar_instrucoes_seed(owner, prefixo):
        texto = cmd.lstrip()
        if texto.upper().startswith(marca):
            ent = por_tabela.get(texto[len(marca):].split(None, 1)[0].upper())
            if ent:
                contagem[ent] += 1
    return contagem


def gerar_script_validacao(owner, prefixo):
    """Gera o 99_validate_deploy.sql a partir do registro sql_ident (SQL*Plus, somente leitura).

    Compara esperado x encontrado: objetos (tabelas, sequences, triggers, constraints e indices pelos
    nomes do registro), objetos invalidos, GRANTs a PUBLIC (proibidos), versao do esquema e o minimo de
    linhas do seed. Cada verificacao sai com OK ou FALHA e um resumo final. Owner e prefixo vem dos
    parametros; nenhum hash de senha e exibido (AGENTS §3.3), so se a senha esta definida.
    """
    sql_ident.validate_owner(owner)
    sql_ident.validate_prefix(prefixo)
    esquema = sql_ident.names(prefixo)
    own = owner.upper()

    tabelas = [t["tabela"] for t in esquema.values()]
    sequences = [t["sequence"] for t in esquema.values()]
    triggers = []
    constraints = []
    indices = []
    for t in esquema.values():
        triggers.extend(n for n in (t.get("trigger_bi"), t.get("trigger_bu")) if n)
        constraints.append(t["pk"])
        for grupo in ("uks", "fks", "cks"):
            constraints.extend(t[grupo].keys())
        indices.extend(t["indices"].keys())
    objetos = tabelas + sequences + triggers + indices

    def chk(ordem, rotulo, regra, valor, sql_contagem):
        return ("SELECT {o} AS sort_order, '{r}' AS verificacao, '{g}' AS regra, {v} AS esperado, "
                "({s}) AS encontrado FROM DUAL").format(o=ordem, r=rotulo, g=regra, v=valor, s=sql_contagem)

    dicionario = [
        chk(1, "TABELAS", "=", len(tabelas),
            "SELECT COUNT(*) FROM all_tables WHERE owner = '{}' AND table_name IN ({})".format(
                own, _lista_literais(tabelas))),
        chk(2, "SEQUENCES", "=", len(sequences),
            "SELECT COUNT(*) FROM all_sequences WHERE sequence_owner = '{}' AND sequence_name IN ({})".format(
                own, _lista_literais(sequences))),
        chk(3, "TRIGGERS HABILITADAS", "=", len(triggers),
            "SELECT COUNT(*) FROM all_triggers WHERE owner = '{}' AND status = 'ENABLED' "
            "AND trigger_name IN ({})".format(own, _lista_literais(triggers))),
        chk(4, "CONSTRAINTS HABILITADAS", "=", len(constraints),
            "SELECT COUNT(*) FROM all_constraints WHERE owner = '{}' AND status = 'ENABLED' "
            "AND constraint_name IN ({})".format(own, _lista_literais(constraints))),
        chk(5, "INDICES VALIDOS", "=", len(indices),
            "SELECT COUNT(*) FROM all_indexes WHERE owner = '{}' AND status = 'VALID' "
            "AND index_name IN ({})".format(own, _lista_literais(indices))),
        chk(6, "OBJETOS INVALIDOS", "=", 0,
            "SELECT COUNT(*) FROM all_objects WHERE owner = '{}' AND status = 'INVALID' "
            "AND object_name IN ({})".format(own, _lista_literais(objetos))),
        chk(7, "GRANTS A PUBLIC", "=", 0,
            "SELECT COUNT(*) FROM all_tab_privs WHERE table_schema = '{}' AND grantee = 'PUBLIC' "
            "AND table_name IN ({})".format(own, _lista_literais(tabelas + sequences))),
    ]

    tab = dict((ent, "{}.{}".format(owner, t["tabela"])) for ent, t in esquema.items())
    dados = [
        chk(10, "VERSAO DO ESQUEMA", "=", sql_ident.SCHEMA_VERSION,
            "SELECT MAX(schema_version) FROM {}".format(tab["control"])),
    ]
    for n, (ent, minimo) in enumerate(_linhas_seed_por_tabela(owner, prefixo).items()):
        dados.append(chk(11 + n, "LINHAS " + esquema[ent]["tabela"].upper(), ">=", minimo,
                         "SELECT COUNT(*) FROM {}".format(tab[ent])))

    def relatorio(partes):
        uniao = "\n  UNION ALL ".join(partes)
        detalhe = (
            "WITH chk AS (\n  " + uniao + "\n)\n"
            "SELECT verificacao, regra || ' ' || esperado AS esperado, encontrado,\n"
            "       CASE WHEN (regra = '=' AND encontrado = esperado) OR (regra = '>=' AND encontrado >= esperado)\n"
            "            THEN 'OK' ELSE 'FALHA' END AS resultado\n"
            "  FROM chk ORDER BY sort_order;"
        )
        resumo = (
            "WITH chk AS (\n  " + uniao + "\n)\n"
            "SELECT CASE WHEN COUNT(*) = 0 THEN 'OK: nenhuma falha'\n"
            "            ELSE 'FALHA: ' || COUNT(*) || ' verificacao(oes) divergente(s)' END AS resumo\n"
            "  FROM chk\n"
            " WHERE NOT ((regra = '=' AND encontrado = esperado) OR (regra = '>=' AND encontrado >= esperado))\n"
            "    OR encontrado IS NULL;"
        )
        return [detalhe, "", resumo]

    linhas = [
        "-- ==============================================================================",
        "-- Script Scheduling Service (SSS) - Validacao da Implantacao Oracle 11gR2+",
        "-- Gerado automaticamente a partir do registro sql_ident.py (somente leitura)",
        "-- Owner: {}".format(owner),
        "-- Prefixo: {}".format(prefixo),
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
    linhas.extend(relatorio(dicionario))
    linhas.extend([
        "",
        "PROMPT ==============================================================================",
        "PROMPT 2. VERSAO DO ESQUEMA E MINIMO DE LINHAS DO SEED",
        "PROMPT (se as tabelas nao existirem, esta secao falha com ORA-00942: veja a secao 1)",
        "PROMPT ==============================================================================",
    ])
    linhas.extend(relatorio(dados))
    linhas.extend([
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
        " WHERE table_schema = '{}' AND table_name IN ({})".format(own, _lista_literais(tabelas + sequences)),
        " GROUP BY grantee, privilege",
        " ORDER BY grantee, privilege;",
        "SET FEEDBACK OFF",
        "",
        "PROMPT Fim da validacao do SSS.",
        "EXIT;",
        "",
    ])
    return "\n".join(linhas)


def gerar_script_implantacao_completo(owner, prefixo, lob_storage="SECUREFILE",
                                      admin_login=None, admin_nome=None, admin_senha_hash=None,
                                      papeis_usuarios=None):
    """Gera script SQL autocontido com DDL, DML Seed, Estatisticas e Grants para execucao direta.

    Para no primeiro erro (WHENEVER SQLERROR EXIT FAILURE ROLLBACK, revisao de 2026-10-20): um
    esquema parcial nunca e anunciado como sucesso. Reaplicar exige o 02_rollback antes (ciclo
    02 -> 01 -> 99). Os GRANTs seguem so os papeis do README §11.1; nada e concedido a PUBLIC
    (tbsss_users guarda senha_hash).
    """
    sql_ddl = gerar_script_ddl(owner, prefixo, lob_storage=lob_storage)
    sql_seed = gerar_script_seed(
        owner, prefixo,
        admin_login=admin_login,
        admin_nome=admin_nome,
        admin_senha_hash=admin_senha_hash
    )

    partes = [
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

    partes.extend([
        "-- ==============================================================================",
        "-- GRANTS POR PAPEL (README §11.1); nenhum GRANT a PUBLIC",
        "-- ==============================================================================",
        "",
    ])
    partes.extend(gerar_grants_por_papel(owner, prefixo, papeis_usuarios or {}))
    partes.append("")

    partes.extend([
        "PROMPT Implantacao do SSS concluida com sucesso!",
        "EXIT;",
        "",
    ])

    return "\n".join(partes)

