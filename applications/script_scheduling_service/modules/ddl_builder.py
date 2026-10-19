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
    ("OPERACAO", "EXEC_SCRIPT", "Disparar Scripts", "Preencher questionários e abrir tickets"),
    ("OPERACAO", "VER_LOGS", "Consultar Logs", "Visualizar logs e histórico em tempo quase real"),
    ("OPERACAO", "CANC_TICKET", "Cancelar Tickets", "Cancelar tickets de terceiros em ambientes autorizados"),
    ("ADMIN", "CAD_USUARIOS", "Gestão de Usuários", "Gerenciar operadores e credenciais"),
    ("ADMIN", "CAD_PERFIS", "Gestão de Perfis", "Gerenciar perfis e matrizes de permissão"),
    ("ADMIN", "CAD_AMBIENTES", "Gestão de Ambientes", "Gerenciar ambientes e DSNs"),
    ("ADMIN", "CAD_SCRIPTS", "Gestão de Scripts", "Cadastrar rotinas e homologação por ambiente"),
    ("ADMIN", "CAD_PARAMETROS", "Dicionário de Parâmetros", "Gerenciar perguntas e flags reutilizáveis"),
    ("ADMIN", "CAD_AGENDAMENTOS", "Regras de Agendamento", "Criar e gerenciar recorrências"),
    ("ADMIN", "VER_AUDITORIA", "Auditoria", "Consultar a trilha de auditoria e os agentes"),
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
    ("ADMINISTRADOR", "Acesso irrestrito a todas as funcionalidades e ambientes", "S", (
        "EXEC_SCRIPT", "VER_LOGS", "CANC_TICKET", "CAD_USUARIOS", "CAD_PERFIS",
        "CAD_AMBIENTES", "CAD_SCRIPTS", "CAD_PARAMETROS", "CAD_AGENDAMENTOS", "VER_AUDITORIA"
    ), ("CLONE2", "CLONE1", "CLONE6", "CLONE7", "GFPREPROD")),
    ("OPERADOR_PROD", "Operador de Ambientes de Producao", "N", (
        "EXEC_SCRIPT", "VER_LOGS", "CANC_TICKET"
    ), ("CLONE2", "CLONE1", "CLONE6", "CLONE7", "GFPREPROD")),
    ("OPERADOR_HML", "Operador de Ambientes de Homologacao", "N", (
        "EXEC_SCRIPT", "VER_LOGS", "CANC_TICKET"
    ), ("CLONE6", "CLONE7", "GFPREPROD")),
    ("CONSULTA", "Perfil de Apenas Leitura e Consulta", "N", (
        "VER_LOGS",
    ), ("CLONE2", "CLONE1", "CLONE6", "CLONE7", "GFPREPROD")),
)

# Catalogo padrao de usuarios de homologacao e demonstracao (login, nome, perfil_nome)
CATALOGO_USUARIOS_PADRAO = (
    ("admin", "Super Administrador", "ADMINISTRADOR"),
    ("op.prod", "Operador Producao", "OPERADOR_PROD"),
    ("op.hml", "Operador Homologacao", "OPERADOR_HML"),
    ("consulta", "Auditor e Consulta", "CONSULTA"),
)

# Hash PBKDF2 da senha padrao de homologacao/demonstracao (senha: Sss@Homolog2026!)
HASH_SENHA_PADRAO_HOMOLOGACAO = "pbkdf2_sha256$200000$f9fb31dc39b754d083af236a880dfa6e$2229f3f8a694a9c45be82d9c3bd38110f8b474d2a0aa0ee7f691d405738a4cd8"

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
    ("zipar_arquivos", "Compacta arquivo ou pasta em formato ZIP", "UTILITARIOS", "ARQUIVOS", "COMPACTACAO", "PYTHON3", "/opt/automacoes/scripts/utilitarios/zipar_arquivos.py", "NOMEADO", 2, 1800, (
        ("arq_origem", 1, "S", None),
        ("arq_destino", 2, "S", None),
        ("nivel_compressao", 3, "N", "6"),
    )),
    ("descompactar_zip", "Extrai arquivos de pacote ZIP para pasta destino com protecao segura", "UTILITARIOS", "ARQUIVOS", "DESCOMPACTACAO", "PYTHON3", "/opt/automacoes/scripts/utilitarios/descompactar_zip.py", "NOMEADO", 2, 1800, (
        ("arq_zip", 1, "S", None),
        ("arq_destino", 2, "S", None),
    )),
    ("quebrar_arquivo", "Divide arquivo texto em partes menores por quantidade de linhas", "UTILITARIOS", "ARQUIVOS", "DIVISAO", "PYTHON3", "/opt/automacoes/scripts/utilitarios/quebrar_arquivo.py", "NOMEADO", 2, 1800, (
        ("arq_origem", 1, "S", None),
        ("linhas_por_parte", 2, "N", "1000"),
        ("prefixo_saida", 3, "N", "/tmp/parte_"),
    )),
    ("juntar_arquivos", "Concatena blocos de arquivos ordenados em arquivo consolidado final", "UTILITARIOS", "ARQUIVOS", "CONCATENACAO", "PYTHON3", "/opt/automacoes/scripts/utilitarios/juntar_arquivos.py", "NOMEADO", 2, 1800, (
        ("padrao_origem", 1, "S", "/tmp/parte_*"),
        ("arq_destino", 2, "S", None),
    )),
    ("converter_encoding", "Converte codificacao de caracteres de arquivo texto (ex: ISO-8859-1 para UTF-8)", "UTILITARIOS", "ARQUIVOS", "CONVERSAO", "PYTHON3", "/opt/automacoes/scripts/utilitarios/converter_encoding.py", "NOMEADO", 2, 1800, (
        ("arq_origem", 1, "S", None),
        ("arq_destino", 2, "S", None),
        ("enc_origem", 3, "N", "ISO-8859-1"),
        ("enc_destino", 4, "N", "UTF-8"),
    )),
    ("substituir_texto", "Localiza e substitui texto em arquivo gerando copia atualizada", "UTILITARIOS", "ARQUIVOS", "TRANSFORMACAO", "PYTHON3", "/opt/automacoes/scripts/utilitarios/substituir_texto.py", "NOMEADO", 2, 1800, (
        ("arq_origem", 1, "S", None),
        ("arq_destino", 2, "S", None),
        ("termo_busca", 3, "S", None),
        ("termo_substituicao", 4, "S", None),
    )),
    ("remover_duplicadas", "Remove linhas duplicadas de arquivo texto preservando ordem ou ordenando", "UTILITARIOS", "ARQUIVOS", "HIGIENIZACAO", "PYTHON3", "/opt/automacoes/scripts/utilitarios/remover_duplicadas.py", "NOMEADO", 2, 1800, (
        ("arq_origem", 1, "S", None),
        ("arq_destino", 2, "S", None),
        ("flag_ordenar", 3, "N", "S"),
    )),
    ("gerar_hash_arquivo", "Calcula hash criptografico (SHA256, MD5, SHA1) para conferencia de integridade", "UTILITARIOS", "ARQUIVOS", "AUDITORIA", "PYTHON3", "/opt/automacoes/scripts/utilitarios/gerar_hash_arquivo.py", "NOMEADO", 2, 1800, (
        ("arq_origem", 1, "S", None),
        ("tipo_hash", 2, "N", "sha256"),
    )),
    ("compactar_targz", "Cria pacote compactado .tar.gz a partir de arquivo ou pasta", "UTILITARIOS", "ARQUIVOS", "COMPACTACAO", "BASH", "/opt/automacoes/scripts/utilitarios/compactar_targz.sh", "NOMEADO", 2, 1800, (
        ("arq_origem", 1, "S", None),
        ("arq_destino", 2, "S", None),
    )),
    ("descompactar_targz", "Extrai pacote compactado .tar.gz para pasta destino com verificacao", "UTILITARIOS", "ARQUIVOS", "DESCOMPACTACAO", "BASH", "/opt/automacoes/scripts/utilitarios/descompactar_targz.sh", "NOMEADO", 2, 1800, (
        ("arq_tar", 1, "S", None),
        ("arq_destino", 2, "S", None),
    )),
    ("contar_linhas_arquivo", "Conta linhas, palavras e bytes de arquivo texto (modo posicional/sequencial)", "UTILITARIOS", "ARQUIVOS", "ANALISE", "SH", "/opt/automacoes/scripts/utilitarios/contar_linhas_arquivo.sh", "SEQUENCIAL", 2, 600, (
        ("caminho_arquivo", 1, "S", None),
    )),
    ("filtrar_linhas", "Filtra linhas de arquivo baseado em padrao de texto com opcao de inverter", "UTILITARIOS", "ARQUIVOS", "FILTRAGEM", "BASH", "/opt/automacoes/scripts/utilitarios/filtrar_linhas.sh", "NOMEADO", 2, 1800, (
        ("arq_origem", 1, "S", None),
        ("arq_destino", 2, "S", None),
        ("termo_filtro", 3, "S", None),
        ("flag_inverter", 4, "N", "N"),
    )),
    ("ordenar_arquivo", "Ordena linhas de arquivo texto com opcoes numerica e reversa", "UTILITARIOS", "ARQUIVOS", "ORGANIZACAO", "SH", "/opt/automacoes/scripts/utilitarios/ordenar_arquivo.sh", "NOMEADO", 2, 1800, (
        ("arq_origem", 1, "S", None),
        ("arq_destino", 2, "S", None),
        ("flag_numerico", 3, "N", "N"),
        ("flag_reverso", 4, "N", "N"),
    )),
    ("limpar_linhas_vazias", "Remove espacos em branco excedentes e linhas vazias de arquivo texto", "UTILITARIOS", "ARQUIVOS", "HIGIENIZACAO", "BASH", "/opt/automacoes/scripts/utilitarios/limpar_linhas_vazias.sh", "NOMEADO", 2, 1800, (
        ("arq_origem", 1, "S", None),
        ("arq_destino", 2, "S", None),
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
    "ambientes": "Cadastro de ambientes operacionais para execucao de rotinas (PRODUCAO, HOMOLOGACAO, CLONES)",
    "perfis": "Perfis de acesso para autorizacao baseada em papeis (RBAC)",
    "funcionalidades": "Catalogo canonico de permissoes e operacoes controladas pelo sistema",
    "perfil_func": "Matriz associativa de permissoes que vincula perfis a funcionalidades autorizadas",
    "perfil_amb": "Associacao que delimita os ambientes onde cada perfil possui autorizacao",
    "scripts": "Catalogo de rotinas e scripts homologados para execucao automatizada",
    "perfil_scr": "Associacao que define quais rotinas cada perfil tem permissao para disparar",
    "script_amb": "Homologacao tecnica que associa rotinas aos ambientes onde podem rodar",
    "usuarios": "Cadastro de operadores do sistema, credenciais e controle de sessao",
    "parametros": "Dicionario de perguntas, variaveis e flags reutilizaveis em scripts",
    "script_param": "Composicao e ordenacao dos parametros exigidos por cada rotina",
    "agendamentos": "Regras de execucao periodica automatica ou avulsa de rotinas",
    "tickets": "Fila de execucao, ciclo de vida e historico de execucao de scripts",
    "ticket_resp": "Valores individuais preenchidos para cada parametro no disparo do ticket",
    "agentes": "Registro, versao e sinais de vida dos daemons executores instalados",
    "auditoria": "Trilha de auditoria imutavel para conformidade e rastreabilidade",
    "controle": "Parametros de controle global, versao de esquema e concessao de limpeza",
}

DICIONARIO_COLUNAS = {
    "ambientes": {
        "id": "Identificador unico sequencial do ambiente (chave primaria)",
        "nome": "Nome mnemonico unico do ambiente em maiusculas (chave natural imutavel)",
        "descricao": "Descricao detalhada do ambiente, servidor host e finalidade",
        "conexao": "String de conexao ou alias DSN/TNS sugerido para o banco de dados do ambiente",
        "ativo": "Indicador de vigencia do ambiente (S=Ativo, N=Inativo)",
    },
    "perfis": {
        "id": "Identificador unico sequencial do perfil (chave primaria)",
        "nome": "Nome unico de identificacao do perfil (ex: ADMINISTRADOR, OPERADOR)",
        "descricao": "Finalidade e escopo de atuacao dos usuarios vinculados ao perfil",
        "is_admin": "Indicador de perfil com poderes administrativos plenos (S/N)",
        "perm_versao": "Versao incremental das permissoes para invalidacao de sessoes ativas",
        "ativo": "Indicador de vigencia do perfil no sistema (S=Ativo, N=Inativo)",
    },
    "funcionalidades": {
        "id": "Identificador unico sequencial da funcionalidade (chave primaria)",
        "codigo": "Codigo mnemonico unico da operacao (ex: EXEC_SCRIPT, VER_LOGS, CANC_TICKET)",
        "modulo": "Modulo funcional do sistema ao qual a operacao pertence (OPERACAO, ADMIN)",
        "nome": "Nome amigavel de exibicao da funcionalidade na interface",
        "descricao": "Descricao clara das acoes permitidas por esta funcionalidade",
        "ativo": "Indicador de vigencia da funcionalidade no sistema (S/N)",
    },
    "perfil_func": {
        "id": "Identificador unico sequencial do vinculo (chave primaria)",
        "perfil_id": "Identificador do perfil associado (FK para tbsss_perfis)",
        "funcionalidade_id": "Identificador da funcionalidade autorizada (FK para tbsss_funcionalidades)",
    },
    "perfil_amb": {
        "id": "Identificador unico sequencial do vinculo (chave primaria)",
        "perfil_id": "Identificador do perfil autorizado (FK para tbsss_perfis)",
        "ambiente_id": "Identificador do ambiente autorizado (FK para tbsss_ambientes)",
    },
    "scripts": {
        "id": "Identificador unico sequencial do script (chave primaria)",
        "nome": "Nome unico da rotina (ex: carga_diaria, relatorio_mensal)",
        "descricao": "Detalhamento da finalidade, regras e impacto da execucao do script",
        "interpretador": "Interpretador utilizado para execucao (PYTHON3, BASH, SH)",
        "path_file": "Caminho absoluto normalizado do script no sistema de arquivos do servidor",
        "timeout_segundos": "Tempo limite em segundos para execucao antes de encerramento forcado",
        "permite_concorrente": "Indicador se permite execucoes simultaneas no mesmo ambiente (S/N)",
        "categoria": "Categoria de negocio ou agrupador funcional da rotina",
        "ativo": "Indicador de disponibilidade da rotina para novas execucoes (S/N)",
    },
    "perfil_scr": {
        "id": "Identificador unico sequencial do vinculo (chave primaria)",
        "perfil_id": "Identificador do perfil autorizado (FK para tbsss_perfis)",
        "script_id": "Identificador da rotina homologada (FK para tbsss_scripts)",
    },
    "script_amb": {
        "id": "Identificador unico sequencial da homologacao (chave primaria)",
        "script_id": "Identificador do script homologado (FK para tbsss_scripts)",
        "ambiente_id": "Identificador do ambiente onde a rotina e permitida (FK para tbsss_ambientes)",
    },
    "usuarios": {
        "id": "Identificador unico sequencial do usuario (chave primaria)",
        "login": "Identificador de login do usuario (chave natural imutavel)",
        "nome": "Nome completo do operador para identificacao",
        "email": "Endereco de correio eletronico corporativo do operador",
        "senha_hash": "Hash criptografico da senha gerado via PBKDF2-SHA256 (200k iteracoes)",
        "perfil_id": "Identificador do perfil de acesso atribuido (FK para tbsss_perfis)",
        "ativo": "Indicador se o usuario esta ativo (S=Ativo, N=Bloqueado/Inativo)",
        "sessao_epoch": "Contador de revogacao de sessoes ativas para seguranca",
        "tentativas_falha": "Numero de tentativas consecutivas de autenticacao incorretas",
        "bloqueado_ate": "Data e hora limite de bloqueio temporario por excesso de falhas",
    },
    "parametros": {
        "id": "Identificador unico sequencial do parametro (chave primaria)",
        "codigo": "Codigo mnemonico unico do parametro (ex: DATA_REF, FORMATO)",
        "label": "Rotulo de exibicao amigavel apresentado no formulario ao usuario",
        "tipo_componente": "Tipo de componente visual (TEXTO, NUMERO, DATA, SELECT, RADIO, CHECKBOX)",
        "descricao": "Texto explicativo de orientacao ao operador",
        "regex_validacao": "Expressao regular segura para validacao do valor inserido",
        "opcoes_json": "Opcoes selecionaveis em formato JSON para componentes do tipo lista",
        "valor_padrao": "Valor pre-definido padrao sugerido no formulario",
        "flag_comando": "Flag de linha de comando associada (ex: --data, -f)",
        "sensivel": "Indicador se o dado e confidencial e deve ser mascarado em logs (S/N)",
        "ativo": "Indicador de vigencia do parametro no sistema (S/N)",
    },
    "script_param": {
        "id": "Identificador unico sequencial da associacao (chave primaria)",
        "script_id": "Identificador do script (FK para tbsss_scripts)",
        "parametro_id": "Identificador do parametro associado (FK para tbsss_parametros)",
        "ordem": "Posicao de apresentacao do campo no questionario de execucao",
        "obrigatorio": "Indicador se o preenchimento e mandatorio para esta rotina (S/N)",
        "valor_padrao_sub": "Valor padrao especifico que sobrescreve o valor do parametro para este script",
        "grupo": "Agrupador ou secao visual no formulario",
        "etapa": "Etapa de preenchimento em formularios com multiplos passos",
    },
    "agendamentos": {
        "id": "Identificador unico sequencial do agendamento (chave primaria)",
        "nome": "Titulo descritivo da regra de agendamento",
        "script_id": "Identificador da rotina a ser executada (FK para tbsss_scripts)",
        "ambiente": "Nome do ambiente onde a rotina deve ser disparada (FK para tbsss_ambientes)",
        "usuario_id": "Operador responsavel pelo agendamento (FK para tbsss_usuarios)",
        "prioridade": "Nivel de prioridade da execucao (1=Critico a 4=Baixa)",
        "tipo_recorrencia": "Tipo de periodicidade (UNICA, DIARIA, SEMANAL, MENSAL, CRON)",
        "expressao_cron": "Expressao cron no formato padrao de 5 campos (minuto hora dia mes dsem)",
        "hora_execucao": "Horario de disparo no formato HH:MM para recorrencias diarias/semanais/mensais",
        "dias_semana": "Dias da semana selecionados (1=Dom a 7=Sab) para agendamento semanal",
        "dia_mes": "Dia do mes (1 a 31) para agendamento mensal",
        "parametros_json": "Parametros congelados configurados para o agendamento em JSON (CLOB)",
        "data_inicio": "Data inicial de vigencia do agendamento",
        "data_fim": "Data final limite para expiracao do agendamento",
        "proxima_execucao": "Data e hora exatas calculadas para o proximo disparo",
        "ultima_execucao": "Data e hora em que ocorreu o ultimo disparo",
        "ultimo_ticket_id": "Identificador do ticket mais recente gerado por esta regra",
        "pausa_motivo": "Motivo formal em caso de suspensao da regra (ex: USUARIO_INATIVO, MANUAL)",
        "ativo": "Indicador de vigencia da regra (S=Ativo, N=Pausado/Concluido)",
    },
    "tickets": {
        "id": "Identificador unico sequencial do ticket de execucao (chave primaria)",
        "script_id": "Identificador da rotina solicitada (FK para tbsss_scripts)",
        "ambiente": "Nome do ambiente alvo da execucao (FK para tbsss_ambientes)",
        "solicitante": "Login do operador que solicitou a execucao (FK para tbsss_usuarios)",
        "ip_origem": "Endereco IP do cliente que originou o pedido",
        "agente_id": "Identificador do daemon do agente que executou o ticket",
        "status": "Situacao da execucao (PENDING, RUNNING, SUCCESS, FAILED, CANCELLED)",
        "prioridade": "Prioridade de atendimento na fila (1=Critico, 2=Alta, 3=Normal, 4=Baixa)",
        "cancel_requested": "Indicador se o cancelamento foi requisitado pelo operador (S/N)",
        "process_id": "Identificador do processo (PID) no sistema operacional do servidor",
        "exit_code": "Codigo numerico de retorno do processo (0=Sucesso, >0=Erro)",
        "scheduled_at": "Data e hora agendadas para o processamento",
        "started_at": "Data e hora efetivas do inicio da execucao pelo agente",
        "finished_at": "Data e hora de conclusao ou encerramento da execucao",
        "heartbeat_at": "Data e hora da ultima confirmacao de atividade do processo",
        "log_output": "Saida completa de execucao capturada de stdout/stderr (CLOB)",
        "log_truncado": "Indicador se o log excedeu o limite maximo de tamanho (S/N)",
        "log_offset_chars": "Controle tecnico de caracteres confirmados gravados no log",
        "parent_ticket_id": "Identificador do ticket pai em caso de reexecucao",
        "agendamento_id": "Identificador da regra de agendamento de origem (se houver)",
        "status_motivo": "Codigo tecnico do motivo de falha ou cancelamento",
        "parametros_enviados": "Copia fiel dos parametros de entrada fornecidos na solicitacao (CLOB)",
        "script_sha256": "Hash criptografico SHA-256 do arquivo executavel na data do disparo",
    },
    "ticket_resp": {
        "id": "Identificador unico sequencial da resposta (chave primaria)",
        "ticket_id": "Identificador do ticket correspondente (FK para tbsss_tickets)",
        "parametro_id": "Identificador do parametro respondido (FK para tbsss_parametros)",
        "valor": "Valor fornecido pelo operador para este parametro",
    },
    "agentes": {
        "id": "Identificador unico sequencial do agente (chave primaria)",
        "codigo": "Codigo identificador unico do agente (ex: agt-node01)",
        "hostname": "Nome de rede (hostname) da maquina servidora do agente",
        "pid_daemon": "Identificador de processo (PID) do daemon no servidor",
        "versao": "Versao do software do servico em execucao no agente",
        "ambientes": "Lista separada por virgulas dos ambientes atendidos por este no",
        "plataforma": "Sistema operacional da maquina servidora (POSIX)",
        "interpretadores": "Interpretadores homologados disponiveis no servidor (PYTHON3, BASH, SH)",
        "status": "Estado de operacao do no (ATIVO, INATIVO, DRAIN)",
        "iniciado_em": "Data e hora de inicializacao do daemon",
        "heartbeat_at": "Data e hora do sinal periodico de disponibilidade mais recente",
    },
    "auditoria": {
        "id": "Identificador unico sequencial do evento de auditoria (chave primaria)",
        "created_at": "Data e hora exatas da realizacao do evento auditado",
        "ator": "Identificador do operador ou servico que executou a acao",
        "ip_origem": "Endereco IP do cliente que solicitou a operacao",
        "acao": "Codigo mnemonico da acao executada (ex: CAD_INSERIR, TICKET_CRIAR)",
        "entidade": "Nome da tabela ou entidade alvo afetada",
        "entidade_id": "Identificador numerico do registro alvo afetado",
        "detalhe": "Texto descritivo ou dados em formato estruturado sobre o evento",
    },
    "controle": {
        "id": "Identificador unico da linha de controle global (sempre 1)",
        "versao_esquema": "Numero da versao estrutural do banco de dados atualmente instalada",
        "versao_aplicada_em": "Data e hora de aplicacao da versao de esquema atual",
        "versao_aplicada_por": "Identificador de quem realizou a aplicacao do esquema",
        "purge_dono": "Identificador do no que detem a concessao de purga de dados",
        "purge_concessao_ate": "Data e hora limite de expiracao da concessao de purga",
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
    sql_ident.validar_owner(owner)
    sql_ident.validar_prefixo(prefixo)
    esquema = sql_ident.nomes(prefixo)
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
        colunas_pk = ", ".join(sql_ident.TABELAS[entidade]["pk"]["colunas"])
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
    sql_ident.validar_owner(owner)
    sql_ident.validar_prefixo(prefixo)
    esquema = sql_ident.nomes(prefixo)
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


def gerar_grants_por_papel(owner, prefixo, papeis_usuarios):
    """Gera comandos GRANT para os usuarios informados por papel (README §11.1).

    papeis_usuarios: dict com mapeamento papel -> usuario_oracle, ex:
      {'web': 'sss_web', 'agente': 'sss_agente', 'purge': 'sss_purge', 'monitor': 'sss_monitor'}
    """
    sql_ident.validar_owner(owner)
    sql_ident.validar_prefixo(prefixo)
    esquema = sql_ident.nomes(prefixo)
    comandos = []

    # 1. PAPEL: web
    usr_web = papeis_usuarios.get("web")
    if usr_web:
        cadastros_e_agendamentos = (
            "ambientes", "perfis", "funcionalidades", "scripts",
            "usuarios", "parametros", "agendamentos"
        )
        for ent in cadastros_e_agendamentos:
            comandos.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
                owner, esquema[ent]["tabela"], usr_web
            ))

        associacoes = (
            "perfil_func", "perfil_amb", "perfil_scr", "script_amb", "script_param"
        )
        for ent in associacoes:
            comandos.append("GRANT SELECT, INSERT, UPDATE, DELETE ON {}.{} TO {};".format(
                owner, esquema[ent]["tabela"], usr_web
            ))

        comandos.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
            owner, esquema["tickets"]["tabela"], usr_web
        ))
        comandos.append("GRANT SELECT, INSERT ON {}.{} TO {};".format(
            owner, esquema["ticket_resp"]["tabela"], usr_web
        ))
        comandos.append("GRANT SELECT, INSERT ON {}.{} TO {};".format(
            owner, esquema["auditoria"]["tabela"], usr_web
        ))
        comandos.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, esquema["agentes"]["tabela"], usr_web
        ))
        comandos.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, esquema["controle"]["tabela"], usr_web
        ))

        # Sequences para web (todas exceto agentes e controle)
        for ent, t in esquema.items():
            if ent not in ("agentes", "controle"):
                comandos.append("GRANT SELECT ON {}.{} TO {};".format(
                    owner, t["sequence"], usr_web
                ))

    # 2. PAPEL: agente
    usr_agt = papeis_usuarios.get("agente")
    if usr_agt:
        cadastros_e_assoc = (
            "ambientes", "perfis", "funcionalidades", "perfil_func", "perfil_amb",
            "scripts", "perfil_scr", "script_amb", "usuarios", "parametros", "script_param"
        )
        for ent in cadastros_e_assoc:
            comandos.append("GRANT SELECT ON {}.{} TO {};".format(
                owner, esquema[ent]["tabela"], usr_agt
            ))

        comandos.append("GRANT SELECT, UPDATE ON {}.{} TO {};".format(
            owner, esquema["agendamentos"]["tabela"], usr_agt
        ))
        comandos.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
            owner, esquema["tickets"]["tabela"], usr_agt
        ))
        comandos.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
            owner, esquema["agentes"]["tabela"], usr_agt
        ))
        comandos.append("GRANT SELECT, INSERT ON {}.{} TO {};".format(
            owner, esquema["ticket_resp"]["tabela"], usr_agt
        ))
        comandos.append("GRANT INSERT ON {}.{} TO {};".format(
            owner, esquema["auditoria"]["tabela"], usr_agt
        ))
        comandos.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, esquema["controle"]["tabela"], usr_agt
        ))

        # Sequences do agente: tickets, respostas, agentes e auditoria
        for ent in ("tickets", "ticket_resp", "agentes", "auditoria"):
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
            owner, esquema["auditoria"]["tabela"], usr_purge
        ))
        comandos.append("GRANT SELECT, UPDATE (purge_dono, purge_concessao_ate) ON {}.{} TO {};".format(
            owner, esquema["controle"]["tabela"], usr_purge
        ))
        comandos.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, esquema["auditoria"]["sequence"], usr_purge
        ))

    # 4. PAPEL: monitor (CR-008, E3/R-04)
    # Somente SELECT nas 7 tabelas que saude.py consulta, zero sequences
    usr_mon = papeis_usuarios.get("monitor")
    if usr_mon:
        tabelas_monitor = (
            "agentes", "tickets", "agendamentos", "scripts",
            "ambientes", "controle", "auditoria"
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
    sql_ident.validar_owner(owner)
    sql_ident.validar_prefixo(prefixo)
    esquema = sql_ident.nomes(prefixo)
    comandos = []

    # 1. Funcionalidades canonicas
    tb_fnc = "{}.{}".format(owner, esquema["funcionalidades"]["tabela"])
    sq_fnc = "{}.{}".format(owner, esquema["funcionalidades"]["sequence"])
    for mod, cod, nome_exib, finalidade in CATALOGO_FUNCIONALIDADES:
        sql = (
            "MERGE INTO {tb} dst\n"
            "USING (SELECT '{cod}' AS codigo FROM DUAL) src\n"
            "ON (dst.codigo = src.codigo)\n"
            "WHEN MATCHED THEN\n"
            "  UPDATE SET dst.nome = '{nome}',\n"
            "             dst.modulo = '{mod}',\n"
            "             dst.descricao = '{desc}',\n"
            "             dst.ativo = 'S',\n"
            "             dst.updated_at = SYSDATE,\n"
            "             dst.updated_by = 'SYSTEM:init_db'\n"
            "  WHERE dst.ativo <> 'S'\n"
            "     OR dst.nome <> '{nome}'\n"
            "     OR dst.modulo <> '{mod}'\n"
            "     OR dst.descricao <> '{desc}'\n"
            "WHEN NOT MATCHED THEN\n"
            "  INSERT (id, codigo, modulo, nome, descricao, ativo, created_at, created_by)\n"
            "  VALUES ({sq}.NEXTVAL, '{cod}', '{mod}', '{nome}', '{desc}', 'S', SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb=tb_fnc,
            sq=sq_fnc,
            cod=_escape_sql(cod),
            mod=_escape_sql(mod),
            nome=_escape_sql(nome_exib),
            desc=_escape_sql(finalidade),
        )
        comandos.append(sql)

    # 2. Ambientes padrao (inseridos antes dos perfis para permitir vinculo de perfil_amb)
    tb_amb = "{}.{}".format(owner, esquema["ambientes"]["tabela"])
    sq_amb = "{}.{}".format(owner, esquema["ambientes"]["sequence"])
    for amb_nome, amb_desc, amb_conn in CATALOGO_AMBIENTES_PADRAO:
        sql_amb = (
            "MERGE INTO {tb} dst\n"
            "USING (SELECT '{nome}' AS nome FROM DUAL) src\n"
            "ON (dst.nome = src.nome)\n"
            "WHEN MATCHED THEN\n"
            "  UPDATE SET dst.descricao = '{desc}',\n"
            "             dst.conexao = '{conn}',\n"
            "             dst.ativo = 'S',\n"
            "             dst.updated_at = SYSDATE,\n"
            "             dst.updated_by = 'SYSTEM:init_db'\n"
            "  WHERE dst.ativo <> 'S'\n"
            "     OR NVL(dst.descricao, '~') <> '{desc}'\n"
            "     OR NVL(dst.conexao, '~') <> '{conn}'\n"
            "WHEN NOT MATCHED THEN\n"
            "  INSERT (id, nome, descricao, conexao, ativo, created_at, created_by)\n"
            "  VALUES ({sq}.NEXTVAL, '{nome}', '{desc}', '{conn}', 'S', SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb=tb_amb,
            sq=sq_amb,
            nome=_escape_sql(amb_nome),
            desc=_escape_sql(amb_desc),
            conn=_escape_sql(amb_conn),
        )
        comandos.append(sql_amb)

    # 3. Perfis padrao e matrizes de permissao (CATALOGO_PERFIS_PADRAO)
    tb_per = "{}.{}".format(owner, esquema["perfis"]["tabela"])
    sq_per = "{}.{}".format(owner, esquema["perfis"]["sequence"])
    tb_pfnc = "{}.{}".format(owner, esquema["perfil_func"]["tabela"])
    sq_pfnc = "{}.{}".format(owner, esquema["perfil_func"]["sequence"])
    tb_pamb = "{}.{}".format(owner, esquema["perfil_amb"]["tabela"])
    sq_pamb = "{}.{}".format(owner, esquema["perfil_amb"]["sequence"])

    for per_nome, per_desc, is_adm, per_funcs, per_ambs in CATALOGO_PERFIS_PADRAO:
        sql_per = (
            "MERGE INTO {tb} dst\n"
            "USING (SELECT '{nome}' AS nome FROM DUAL) src\n"
            "ON (dst.nome = src.nome)\n"
            "WHEN MATCHED THEN\n"
            "  UPDATE SET dst.descricao = '{desc}',\n"
            "             dst.is_admin = '{is_adm}',\n"
            "             dst.ativo = 'S',\n"
            "             dst.updated_at = SYSDATE,\n"
            "             dst.updated_by = 'SYSTEM:init_db'\n"
            "  WHERE dst.is_admin <> '{is_adm}'\n"
            "     OR dst.ativo <> 'S'\n"
            "     OR NVL(dst.descricao, '~') <> '{desc}'\n"
            "WHEN NOT MATCHED THEN\n"
            "  INSERT (id, nome, descricao, is_admin, perm_versao, ativo, created_at, created_by)\n"
            "  VALUES ({sq}.NEXTVAL, '{nome}', '{desc}', '{is_adm}', 1, 'S', SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb=tb_per, sq=sq_per, nome=_escape_sql(per_nome),
            desc=_escape_sql(per_desc), is_adm=_escape_sql(is_adm)
        )
        comandos.append(sql_per)

        # 3a. Funcionalidades vinculadas ao perfil
        for f_cod in per_funcs:
            sql_pfnc = (
                "MERGE INTO {tb_pfnc} dst\n"
                "USING (\n"
                "  SELECT p.id AS perfil_id, f.id AS funcionalidade_id\n"
                "    FROM {tb_per} p, {tb_fnc} f\n"
                "   WHERE p.nome = '{per_nome}' AND f.codigo = '{f_cod}'\n"
                ") src\n"
                "ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)\n"
                "  VALUES ({sq_pfnc}.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');"
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
                "  SELECT p.id AS perfil_id, a.id AS ambiente_id\n"
                "    FROM {tb_per} p, {tb_amb} a\n"
                "   WHERE p.nome = '{per_nome}' AND a.nome = '{a_nome}'\n"
                ") src\n"
                "ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, perfil_id, ambiente_id, created_at, created_by)\n"
                "  VALUES ({sq_pamb}.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');"
            ).format(
                tb_pamb=tb_pamb, sq_pamb=sq_pamb, tb_per=tb_per, tb_amb=tb_amb,
                per_nome=_escape_sql(per_nome), a_nome=_escape_sql(a_nome)
            )
            comandos.append(sql_pamb)

    # 4. Parametros padrao reutilizaveis
    tb_prm = "{}.{}".format(owner, esquema["parametros"]["tabela"])
    sq_prm = "{}.{}".format(owner, esquema["parametros"]["sequence"])
    for cod, p_nom, lbl, desc, tcomp, opc, vpad in CATALOGO_PARAMETROS_PADRAO:
        pnom_sql = "'{}'".format(_escape_sql(p_nom)) if p_nom else "NULL"
        opc_sql = "'{}'".format(_escape_sql(opc)) if opc else "NULL"
        vpad_sql = "'{}'".format(_escape_sql(vpad)) if vpad else "NULL"
        sql_prm = (
            "MERGE INTO {tb} dst\n"
            "USING (SELECT '{cod}' AS codigo FROM DUAL) src\n"
            "ON (dst.codigo = src.codigo)\n"
            "WHEN MATCHED THEN\n"
            "  UPDATE SET dst.param_nomeado = {pnom},\n"
            "             dst.label = '{lbl}',\n"
            "             dst.descricao = '{desc}',\n"
            "             dst.tipo_componente = '{tcomp}',\n"
            "             dst.opcoes_json = {opc},\n"
            "             dst.valor_padrao = {vpad},\n"
            "             dst.sensivel = 'N',\n"
            "             dst.ativo = 'S',\n"
            "             dst.updated_at = SYSDATE,\n"
            "             dst.updated_by = 'SYSTEM:init_db'\n"
            "  WHERE dst.ativo <> 'S'\n"
            "     OR NVL(dst.param_nomeado, '~') <> NVL({pnom}, '~')\n"
            "     OR dst.label <> '{lbl}'\n"
            "     OR NVL(dst.descricao, '~') <> '{desc}'\n"
            "     OR dst.tipo_componente <> '{tcomp}'\n"
            "     OR NVL(dst.opcoes_json, '~') <> NVL({opc}, '~')\n"
            "     OR NVL(dst.valor_padrao, '~') <> NVL({vpad}, '~')\n"
            "WHEN NOT MATCHED THEN\n"
            "  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)\n"
            "  VALUES ({sq}.NEXTVAL, '{cod}', {pnom}, '{lbl}', '{desc}', '{tcomp}', {opc}, {vpad}, NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb=tb_prm, sq=sq_prm, cod=_escape_sql(cod), pnom=pnom_sql,
            lbl=_escape_sql(lbl), desc=_escape_sql(desc), tcomp=_escape_sql(tcomp),
            opc=opc_sql, vpad=vpad_sql
        )
        comandos.append(sql_prm)

    # 5. Scripts utilitarios padrao
    tb_scr = "{}.{}".format(owner, esquema["scripts"]["tabela"])
    sq_scr = "{}.{}".format(owner, esquema["scripts"]["sequence"])
    tb_samb = "{}.{}".format(owner, esquema["script_amb"]["tabela"])
    sq_samb = "{}.{}".format(owner, esquema["script_amb"]["sequence"])
    tb_pscr = "{}.{}".format(owner, esquema["perfil_scr"]["tabela"])
    sq_pscr = "{}.{}".format(owner, esquema["perfil_scr"]["sequence"])
    tb_sprm = "{}.{}".format(owner, esquema["script_param"]["tabela"])
    sq_sprm = "{}.{}".format(owner, esquema["script_param"]["sequence"])

    for s_nome, s_desc, s_grp, s_cat, s_etp, s_int, s_path, s_tpar, s_paral, s_tmout, s_params in CATALOGO_SCRIPTS_PADRAO:
        sql_scr = (
            "MERGE INTO {tb} dst\n"
            "USING (SELECT '{nome}' AS nome FROM DUAL) src\n"
            "ON (dst.nome = src.nome)\n"
            "WHEN MATCHED THEN\n"
            "  UPDATE SET dst.descricao = '{desc}',\n"
            "             dst.grupo = '{grp}',\n"
            "             dst.categoria = '{cat}',\n"
            "             dst.etapa = '{etp}',\n"
            "             dst.interpretador = '{interp}',\n"
            "             dst.path_file = '{pfile}',\n"
            "             dst.tipo_param = '{tpar}',\n"
            "             dst.max_qtd_parallel_env = {paral},\n"
            "             dst.timeout_seg = {tmout},\n"
            "             dst.ativo = 'S',\n"
            "             dst.updated_at = SYSDATE,\n"
            "             dst.updated_by = 'SYSTEM:init_db'\n"
            "  WHERE dst.ativo <> 'S'\n"
            "     OR NVL(dst.descricao, '~') <> '{desc}'\n"
            "     OR NVL(dst.grupo, '~') <> '{grp}'\n"
            "     OR NVL(dst.categoria, '~') <> '{cat}'\n"
            "     OR NVL(dst.etapa, '~') <> '{etp}'\n"
            "     OR dst.interpretador <> '{interp}'\n"
            "     OR dst.path_file <> '{pfile}'\n"
            "     OR dst.tipo_param <> '{tpar}'\n"
            "     OR dst.max_qtd_parallel_env <> {paral}\n"
            "     OR NVL(dst.timeout_seg, 0) <> {tmout}\n"
            "WHEN NOT MATCHED THEN\n"
            "  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)\n"
            "  VALUES ({sq}.NEXTVAL, '{nome}', '{desc}', '{grp}', '{cat}', '{etp}', '{interp}', '{pfile}', '{tpar}', {paral}, {tmout}, 'S', SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb=tb_scr, sq=sq_scr, nome=_escape_sql(s_nome), desc=_escape_sql(s_desc),
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
                "  SELECT s.id AS script_id, a.id AS ambiente_id\n"
                "    FROM {tb_scr} s, {tb_amb} a\n"
                "   WHERE s.nome = '{s_nome}' AND a.nome = '{amb_nome}'\n"
                ") src\n"
                "ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, script_id, ambiente_id, created_at, created_by)\n"
                "  VALUES ({sq_samb}.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');"
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
                "  SELECT p.id AS perfil_id, s.id AS script_id\n"
                "    FROM {tb_per} p, {tb_scr} s\n"
                "   WHERE p.nome = '{per_nome}' AND s.nome = '{s_nome}'\n"
                ") src\n"
                "ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, perfil_id, script_id, created_at, created_by)\n"
                "  VALUES ({sq_pscr}.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');"
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
                "  SELECT s.id AS script_id, p.id AS parametro_id\n"
                "    FROM {tb_scr} s, {tb_prm} p\n"
                "   WHERE s.nome = '{s_nome}' AND p.codigo = '{p_cod}'\n"
                ") src\n"
                "ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)\n"
                "WHEN MATCHED THEN\n"
                "  UPDATE SET dst.ordem = {ordem},\n"
                "             dst.obrigatorio = '{obrig}',\n"
                "             dst.valor_padrao_sub = {vsub},\n"
                "             dst.updated_at = SYSDATE,\n"
                "             dst.updated_by = 'SYSTEM:init_db'\n"
                "  WHERE dst.ordem <> {ordem}\n"
                "     OR dst.obrigatorio <> '{obrig}'\n"
                "     OR NVL(dst.valor_padrao_sub, '~') <> NVL({vsub}, '~')\n"
                "WHEN NOT MATCHED THEN\n"
                "  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)\n"
                "  VALUES ({sq_sprm}.NEXTVAL, src.script_id, src.parametro_id, {ordem}, '{obrig}', {vsub}, SYSDATE, 'SYSTEM:init_db');"
            ).format(
                tb_sprm=tb_sprm, sq_sprm=sq_sprm, tb_scr=tb_scr, tb_prm=tb_prm,
                s_nome=_escape_sql(s_nome), p_cod=_escape_sql(p_cod),
                ordem=p_ord, obrig=_escape_sql(p_obrig), vsub=vsub_sql
            )
            comandos.append(sql_sprm)

    # 6. Controle de versao
    tb_ctl = "{}.{}".format(owner, esquema["controle"]["tabela"])
    sql_ctl = (
        "MERGE INTO {tb} dst\n"
        "USING (SELECT 1 AS id FROM DUAL) src\n"
        "ON (dst.id = src.id)\n"
        "WHEN NOT MATCHED THEN\n"
        "  INSERT (id, versao_esquema, versao_aplicada_em, versao_aplicada_por)\n"
        "  VALUES (1, {versao}, SYSDATE, 'SYSTEM:init_db');"
    ).format(tb=tb_ctl, versao=sql_ident.VERSAO_ESQUEMA)
    comandos.append(sql_ctl)

    # 7. Usuarios padrao da aplicacao e homologacao (CATALOGO_USUARIOS_PADRAO)
    tb_usr = "{}.{}".format(owner, esquema["usuarios"]["tabela"])
    sq_usr = "{}.{}".format(owner, esquema["usuarios"]["sequence"])

    for u_login, u_nome, u_perfil in CATALOGO_USUARIOS_PADRAO:
        nome_final = admin_nome if (u_login == "admin" and admin_nome) else u_nome
        hash_final = admin_senha_hash if (u_login == "admin" and admin_senha_hash) else HASH_SENHA_PADRAO_HOMOLOGACAO
        sql_usr = (
            "MERGE INTO {tb_usr} dst\n"
            "USING (\n"
            "  SELECT '{login}' AS login, p.id AS perfil_id\n"
            "    FROM {tb_per} p\n"
            "   WHERE p.nome = '{perfil}'\n"
            ") src\n"
            "ON (dst.login = src.login)\n"
            "WHEN MATCHED THEN\n"
            "  UPDATE SET dst.nome = '{nome}',\n"
            "             dst.perfil_id = src.perfil_id,\n"
            "             dst.ativo = 'S',\n"
            "             dst.updated_at = SYSDATE,\n"
            "             dst.updated_by = 'SYSTEM:init_db'\n"
            "  WHERE dst.nome <> '{nome}'\n"
            "     OR dst.perfil_id <> src.perfil_id\n"
            "     OR dst.ativo <> 'S'\n"
            "WHEN NOT MATCHED THEN\n"
            "  INSERT (id, login, nome, senha_hash, perfil_id, ativo, sessao_epoch, tentativas_falha, created_at, created_by)\n"
            "  VALUES ({sq_usr}.NEXTVAL, '{login}', '{nome}', '{hash_s}', src.perfil_id, 'S', 0, 0, SYSDATE, 'SYSTEM:init_db');"
        ).format(
            tb_usr=tb_usr,
            tb_per=tb_per,
            sq_usr=sq_usr,
            login=_escape_sql(u_login),
            nome=_escape_sql(nome_final),
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
    esquema = sql_ident.nomes(prefixo)
    owner_u = owner.upper()

    tabelas_stats = [
        esquema["funcionalidades"]["tabela"].upper(),
        esquema["perfis"]["tabela"].upper(),
        esquema["perfil_func"]["tabela"].upper(),
        esquema["perfil_amb"]["tabela"].upper(),
        esquema["ambientes"]["tabela"].upper(),
        esquema["parametros"]["tabela"].upper(),
        esquema["scripts"]["tabela"].upper(),
        esquema["script_amb"]["tabela"].upper(),
        esquema["perfil_scr"]["tabela"].upper(),
        esquema["script_param"]["tabela"].upper(),
        esquema["controle"]["tabela"].upper(),
        esquema["usuarios"]["tabela"].upper(),
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
    "ticket_resp",
    "tickets",
    "agendamentos",
    "script_param",
    "parametros",
    "script_amb",
    "perfil_scr",
    "perfil_amb",
    "perfil_func",
    "scripts",
    "usuarios",
    "funcionalidades",
    "perfis",
    "ambientes",
    "agentes",
    "auditoria",
    "controle",
)


def gerar_instrucoes_rollback(owner, prefixo):
    """Gera lista de instrucoes DROP (Triggers, Tabelas com CASCADE PURGE e Sequences)."""
    sql_ident.validar_owner(owner)
    sql_ident.validar_prefixo(prefixo)
    esquema = sql_ident.nomes(prefixo)
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


def gerar_grants_public(owner, prefixo):
    """Gera comandos GRANT SELECT para todos (PUBLIC) em todas as tabelas e sequences do SSS."""
    sql_ident.validar_owner(owner)
    sql_ident.validar_prefixo(prefixo)
    esquema = sql_ident.nomes(prefixo)
    comandos = []

    # Tabelas
    for ent, t in esquema.items():
        comandos.append("GRANT SELECT ON {}.{} TO PUBLIC;".format(owner, t["tabela"]))

    # Sequences
    for ent, t in esquema.items():
        comandos.append("GRANT SELECT ON {}.{} TO PUBLIC;".format(owner, t["sequence"]))

    return comandos


def gerar_script_implantacao_completo(owner, prefixo, lob_storage="SECUREFILE",
                                      admin_login=None, admin_nome=None, admin_senha_hash=None,
                                      papeis_usuarios=None, grant_public=True):
    """Gera script SQL autocontido com DDL, DML Seed, Estatisticas e Grants para execucao direta.

    Aplica fallback WHENEVER SQLERROR CONTINUE para que a execucao passe por cima de erros
    caso objetos ou constraints ja existam no banco de dados.
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
        "-- Em caso de erro (ex: objeto ou constraint ja existente), o SQL*Plus continua a execucao (fallback/passa por cima)",
        "WHENEVER SQLERROR CONTINUE;",
        "",
        sql_ddl,
        "",
        sql_seed,
    ]

    if grant_public:
        grants_pub = gerar_grants_public(owner, prefixo)
        partes.extend([
            "-- ==============================================================================",
            "-- GRANTS DE LEITURA PARA TODOS (PUBLIC)",
            "-- ==============================================================================",
            "",
        ])
        partes.extend(grants_pub)
        partes.append("")

    if papeis_usuarios:
        grants = gerar_grants_por_papel(owner, prefixo, papeis_usuarios)
        if grants:
            partes.extend([
                "-- ==============================================================================",
                "-- GRANTS POR PAPEL (README §11.1)",
                "-- ==============================================================================",
                "",
            ])
            partes.extend(grants)
            partes.append("")

    partes.extend([
        "PROMPT Implantacao do SSS concluida com sucesso!",
        "EXIT;",
        "",
    ])

    return "\n".join(partes)

