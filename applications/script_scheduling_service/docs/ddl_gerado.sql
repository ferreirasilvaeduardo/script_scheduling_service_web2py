-- ==============================================================================
-- Script Scheduling Service (SSS) - DDL Oracle 11gR2
-- Gerado automaticamente a partir do registro sql_ident.py (F7.1)
-- Owner: openrisow
-- Prefixo: tbsss_
-- LOB Storage: SECUREFILE
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- FASE 1: SEQUENCES
-- ------------------------------------------------------------------------------

CREATE SEQUENCE openrisow.sq_tbsss_ambientes START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_perfis START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_funcionalidades START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_perfil_func START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_perfil_amb START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_scripts START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_perfil_scr START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_script_amb START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_usuarios START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_parametros START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_script_param START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_agendamentos START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_tickets START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_ticket_resp START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_agentes START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_auditoria START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_controle START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

-- ------------------------------------------------------------------------------
-- FASE 2: TABELAS
-- ------------------------------------------------------------------------------

CREATE TABLE openrisow.tbsss_ambientes (
    id NUMBER(10) NOT NULL,
    nome VARCHAR2(30 CHAR) NOT NULL,
    descricao VARCHAR2(100 CHAR),
    conexao VARCHAR2(250 CHAR),
    ativo CHAR(1) DEFAULT 'S' NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_perfis (
    id NUMBER(10) NOT NULL,
    nome VARCHAR2(30 CHAR) NOT NULL,
    descricao VARCHAR2(100 CHAR),
    is_admin CHAR(1) DEFAULT 'N' NOT NULL,
    perm_versao NUMBER(10) DEFAULT 1 NOT NULL,
    ativo CHAR(1) DEFAULT 'S' NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_funcionalidades (
    id NUMBER(10) NOT NULL,
    codigo VARCHAR2(30 CHAR) NOT NULL,
    nome VARCHAR2(60 CHAR) NOT NULL,
    modulo VARCHAR2(30 CHAR) NOT NULL,
    descricao VARCHAR2(150 CHAR),
    ativo CHAR(1) DEFAULT 'S' NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_perfil_func (
    id NUMBER(10) NOT NULL,
    perfil_id NUMBER(10) NOT NULL,
    funcionalidade_id NUMBER(10) NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_perfil_amb (
    id NUMBER(10) NOT NULL,
    perfil_id NUMBER(10) NOT NULL,
    ambiente_id NUMBER(10) NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_scripts (
    id NUMBER(10) NOT NULL,
    nome VARCHAR2(60 CHAR) NOT NULL,
    descricao VARCHAR2(200 CHAR),
    grupo VARCHAR2(30 CHAR),
    categoria VARCHAR2(30 CHAR),
    etapa VARCHAR2(30 CHAR),
    interpretador VARCHAR2(15 CHAR) NOT NULL,
    path_file VARCHAR2(500 CHAR) NOT NULL,
    tipo_param VARCHAR2(15 CHAR) DEFAULT 'NOMEADO' NOT NULL,
    max_qtd_parallel_env NUMBER(3) DEFAULT 1 NOT NULL,
    timeout_seg NUMBER(7),
    ativo CHAR(1) DEFAULT 'S' NOT NULL,
    sha256_homologado VARCHAR2(64 CHAR),
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_perfil_scr (
    id NUMBER(10) NOT NULL,
    perfil_id NUMBER(10) NOT NULL,
    script_id NUMBER(10) NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_script_amb (
    id NUMBER(10) NOT NULL,
    script_id NUMBER(10) NOT NULL,
    ambiente_id NUMBER(10) NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_usuarios (
    id NUMBER(10) NOT NULL,
    login VARCHAR2(30 CHAR) NOT NULL,
    nome VARCHAR2(60 CHAR) NOT NULL,
    senha_hash VARCHAR2(256 CHAR) NOT NULL,
    perfil_id NUMBER(10) NOT NULL,
    tentativas_falha NUMBER(2) DEFAULT 0 NOT NULL,
    bloqueado_ate DATE,
    ultimo_login DATE,
    senha_alterada_em DATE,
    sessao_epoch NUMBER(10) DEFAULT 0 NOT NULL,
    ativo CHAR(1) DEFAULT 'S' NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_parametros (
    id NUMBER(10) NOT NULL,
    codigo VARCHAR2(30 CHAR) NOT NULL,
    param_nomeado VARCHAR2(30 CHAR),
    label VARCHAR2(60 CHAR) NOT NULL,
    descricao VARCHAR2(150 CHAR),
    tipo_componente VARCHAR2(20 CHAR) NOT NULL,
    opcoes_json VARCHAR2(500 CHAR),
    valor_padrao VARCHAR2(100 CHAR),
    regex_validacao VARCHAR2(150 CHAR),
    sensivel CHAR(1) DEFAULT 'N' NOT NULL,
    ativo CHAR(1) DEFAULT 'S' NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_script_param (
    id NUMBER(10) NOT NULL,
    script_id NUMBER(10) NOT NULL,
    parametro_id NUMBER(10) NOT NULL,
    ordem NUMBER(3) NOT NULL,
    obrigatorio CHAR(1) DEFAULT 'S' NOT NULL,
    valor_padrao_sub VARCHAR2(100 CHAR),
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_agendamentos (
    id NUMBER(10) NOT NULL,
    nome VARCHAR2(60 CHAR) NOT NULL,
    script_id NUMBER(10) NOT NULL,
    ambiente VARCHAR2(30 CHAR) NOT NULL,
    usuario_id NUMBER(10) NOT NULL,
    prioridade NUMBER(1) DEFAULT 2 NOT NULL,
    tipo_recorrencia VARCHAR2(15 CHAR) NOT NULL,
    expressao_cron VARCHAR2(60 CHAR),
    hora_execucao VARCHAR2(5 CHAR),
    dias_semana VARCHAR2(20 CHAR),
    dia_mes NUMBER(2),
    parametros_json CLOB,
    data_inicio DATE NOT NULL,
    data_fim DATE,
    proxima_execucao DATE NOT NULL,
    ultima_execucao DATE,
    ultimo_ticket_id NUMBER(10),
    pausa_motivo VARCHAR2(30 CHAR),
    ativo CHAR(1) DEFAULT 'S' NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
LOB (parametros_json) STORE AS SECUREFILE (CACHE)
);

CREATE TABLE openrisow.tbsss_tickets (
    id NUMBER(10) NOT NULL,
    script_id NUMBER(10) NOT NULL,
    ambiente VARCHAR2(30 CHAR) NOT NULL,
    solicitante VARCHAR2(30 CHAR) NOT NULL,
    ip_origem VARCHAR2(45 CHAR),
    agente_id VARCHAR2(30 CHAR),
    process_id NUMBER(10),
    process_start NUMBER(20),
    status VARCHAR2(15 CHAR) DEFAULT 'PENDING' NOT NULL,
    prioridade NUMBER(1) DEFAULT 2 NOT NULL,
    cancel_requested CHAR(1) DEFAULT 'N' NOT NULL,
    status_motivo VARCHAR2(30 CHAR),
    parent_ticket_id NUMBER(10),
    agendamento_id NUMBER(10),
    parametros_enviados CLOB NOT NULL,
    log_output CLOB,
    log_offset_chars NUMBER(20) DEFAULT 0 NOT NULL,
    log_truncado CHAR(1) DEFAULT 'N' NOT NULL,
    return_code NUMBER(6),
    arquivo_sha256 VARCHAR2(64 CHAR),
    scheduled_at DATE DEFAULT SYSDATE NOT NULL,
    started_at DATE,
    heartbeat_at DATE,
    finished_at DATE,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
LOB (parametros_enviados, log_output) STORE AS SECUREFILE (CACHE)
);

CREATE TABLE openrisow.tbsss_ticket_resp (
    id NUMBER(10) NOT NULL,
    ticket_id NUMBER(10) NOT NULL,
    parametro_id NUMBER(10) NOT NULL,
    valor_resposta VARCHAR2(500 CHAR),
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_agentes (
    id NUMBER(10) NOT NULL,
    codigo VARCHAR2(30 CHAR) NOT NULL,
    hostname VARCHAR2(255 CHAR) NOT NULL,
    pid_daemon NUMBER(10),
    versao VARCHAR2(20 CHAR),
    ambientes VARCHAR2(1000 CHAR),
    plataforma VARCHAR2(10 CHAR),
    interpretadores VARCHAR2(100 CHAR),
    status VARCHAR2(10 CHAR) DEFAULT 'ATIVO' NOT NULL,
    iniciado_em DATE,
    heartbeat_at DATE,
    config_criticos VARCHAR2(400 CHAR),
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_auditoria (
    id NUMBER(10) NOT NULL,
    ator VARCHAR2(40 CHAR) NOT NULL,
    ip_origem VARCHAR2(45 CHAR),
    acao VARCHAR2(30 CHAR) NOT NULL,
    entidade VARCHAR2(30 CHAR) NOT NULL,
    entidade_id NUMBER(10),
    detalhe VARCHAR2(1000 CHAR),
    created_at DATE DEFAULT SYSDATE NOT NULL
);

CREATE TABLE openrisow.tbsss_controle (
    id NUMBER(10) NOT NULL,
    versao_esquema NUMBER(6) NOT NULL,
    versao_aplicada_em DATE NOT NULL,
    versao_aplicada_por VARCHAR2(40 CHAR) NOT NULL,
    purge_dono VARCHAR2(40 CHAR),
    purge_concessao_ate DATE
);

-- ------------------------------------------------------------------------------
-- FASE 3: CONSTRAINTS (PK, UK, CK)
-- ------------------------------------------------------------------------------

ALTER TABLE openrisow.tbsss_ambientes ADD CONSTRAINT pk_tbsss_ambientes PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_ambientes ADD CONSTRAINT uk_tbsss_amb_nome UNIQUE (nome);

ALTER TABLE openrisow.tbsss_ambientes ADD CONSTRAINT ck_tbsss_amb_ativo CHECK (ativo IN ('S', 'N'));

ALTER TABLE openrisow.tbsss_ambientes ADD CONSTRAINT ck_tbsss_amb_nome CHECK (REGEXP_LIKE(nome, '^[A-Z0-9_]{1,30}$'));

ALTER TABLE openrisow.tbsss_ambientes ADD CONSTRAINT ck_tbsss_amb_conexao CHECK (conexao IS NULL OR INSTR(conexao, '@') = 0);

ALTER TABLE openrisow.tbsss_ambientes ADD CONSTRAINT ck_tbsss_amb_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_perfis ADD CONSTRAINT pk_tbsss_perfis PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_perfis ADD CONSTRAINT uk_tbsss_per_nome UNIQUE (nome);

ALTER TABLE openrisow.tbsss_perfis ADD CONSTRAINT ck_tbsss_per_adm CHECK (is_admin IN ('S', 'N'));

ALTER TABLE openrisow.tbsss_perfis ADD CONSTRAINT ck_tbsss_per_ativo CHECK (ativo IN ('S', 'N'));

ALTER TABLE openrisow.tbsss_perfis ADD CONSTRAINT ck_tbsss_per_versao CHECK (perm_versao >= 1);

ALTER TABLE openrisow.tbsss_perfis ADD CONSTRAINT ck_tbsss_per_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_funcionalidades ADD CONSTRAINT pk_tbsss_funcionalidades PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_funcionalidades ADD CONSTRAINT uk_tbsss_fnc_codigo UNIQUE (codigo);

ALTER TABLE openrisow.tbsss_funcionalidades ADD CONSTRAINT ck_tbsss_fnc_ativo CHECK (ativo IN ('S', 'N'));

ALTER TABLE openrisow.tbsss_funcionalidades ADD CONSTRAINT ck_tbsss_fnc_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_perfil_func ADD CONSTRAINT pk_tbsss_perfil_func PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_perfil_func ADD CONSTRAINT uk_tbsss_pfnc_per_fnc UNIQUE (perfil_id, funcionalidade_id);

ALTER TABLE openrisow.tbsss_perfil_func ADD CONSTRAINT ck_tbsss_pfnc_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_perfil_amb ADD CONSTRAINT pk_tbsss_perfil_amb PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_perfil_amb ADD CONSTRAINT uk_tbsss_pamb_per_amb UNIQUE (perfil_id, ambiente_id);

ALTER TABLE openrisow.tbsss_perfil_amb ADD CONSTRAINT ck_tbsss_pamb_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT pk_tbsss_scripts PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT uk_tbsss_scr_nome UNIQUE (nome);

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_tparam CHECK (tipo_param IN ('NOMEADO','SEQUENCIAL','NENHUM'));

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_ativo CHECK (ativo IN ('S', 'N'));

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_paral CHECK (max_qtd_parallel_env BETWEEN 1 AND 999);

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_int CHECK (interpretador IN ('PYTHON3','BASH','SH'));

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_path CHECK (SUBSTR(path_file, 1, 1) = '/' AND INSTR(path_file, '..') = 0 AND INSTR(path_file, '//') = 0 AND INSTR(path_file, '\') = 0);

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_tmout CHECK (timeout_seg IS NULL OR timeout_seg > 0);

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_sha CHECK (sha256_homologado IS NULL OR REGEXP_LIKE(sha256_homologado, '^[0-9a-f]{64}$'));

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_perfil_scr ADD CONSTRAINT pk_tbsss_perfil_scr PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_perfil_scr ADD CONSTRAINT uk_tbsss_pscr_per_scr UNIQUE (perfil_id, script_id);

ALTER TABLE openrisow.tbsss_perfil_scr ADD CONSTRAINT ck_tbsss_pscr_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_script_amb ADD CONSTRAINT pk_tbsss_script_amb PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_script_amb ADD CONSTRAINT uk_tbsss_samb_scr_amb UNIQUE (script_id, ambiente_id);

ALTER TABLE openrisow.tbsss_script_amb ADD CONSTRAINT ck_tbsss_samb_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_usuarios ADD CONSTRAINT pk_tbsss_usuarios PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_usuarios ADD CONSTRAINT uk_tbsss_usr_login UNIQUE (login);

ALTER TABLE openrisow.tbsss_usuarios ADD CONSTRAINT ck_tbsss_usr_ativo CHECK (ativo IN ('S', 'N'));

ALTER TABLE openrisow.tbsss_usuarios ADD CONSTRAINT ck_tbsss_usr_login CHECK (REGEXP_LIKE(login, '^[a-z0-9._-]{3,30}$'));

ALTER TABLE openrisow.tbsss_usuarios ADD CONSTRAINT ck_tbsss_usr_tent CHECK (tentativas_falha >= 0);

ALTER TABLE openrisow.tbsss_usuarios ADD CONSTRAINT ck_tbsss_usr_epoch CHECK (sessao_epoch >= 0);

ALTER TABLE openrisow.tbsss_usuarios ADD CONSTRAINT ck_tbsss_usr_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_parametros ADD CONSTRAINT pk_tbsss_parametros PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_parametros ADD CONSTRAINT uk_tbsss_prm_codigo UNIQUE (codigo);

ALTER TABLE openrisow.tbsss_parametros ADD CONSTRAINT ck_tbsss_prm_tcomp CHECK (tipo_componente IN ('TEXT','NUMBER','DATE','SELECT','CHECKBOX'));

ALTER TABLE openrisow.tbsss_parametros ADD CONSTRAINT ck_tbsss_prm_ativo CHECK (ativo IN ('S', 'N'));

ALTER TABLE openrisow.tbsss_parametros ADD CONSTRAINT ck_tbsss_prm_sens CHECK (sensivel IN ('S','N'));

ALTER TABLE openrisow.tbsss_parametros ADD CONSTRAINT ck_tbsss_prm_codigo CHECK (REGEXP_LIKE(codigo, '^[a-z0-9_]{1,30}$'));

ALTER TABLE openrisow.tbsss_parametros ADD CONSTRAINT ck_tbsss_prm_flag CHECK (param_nomeado IS NULL OR REGEXP_LIKE(param_nomeado, '^-{1,2}[A-Za-z0-9][A-Za-z0-9_-]{0,27}$'));

ALTER TABLE openrisow.tbsss_parametros ADD CONSTRAINT ck_tbsss_prm_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT pk_tbsss_script_param PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT uk_tbsss_sprm_scr_prm UNIQUE (script_id, parametro_id);

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT uk_tbsss_sprm_scr_ord UNIQUE (script_id, ordem);

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT ck_tbsss_sprm_obrig CHECK (obrigatorio IN ('S', 'N'));

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT ck_tbsss_sprm_ordem CHECK (ordem >= 1);

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT ck_tbsss_sprm_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_agendamentos ADD CONSTRAINT pk_tbsss_agendamentos PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_agendamentos ADD CONSTRAINT ck_tbsss_agd_trec CHECK (tipo_recorrencia IN ('UNICA','DIARIA','SEMANAL','MENSAL','CRON'));

ALTER TABLE openrisow.tbsss_agendamentos ADD CONSTRAINT ck_tbsss_agd_prio CHECK (prioridade BETWEEN 1 AND 4);

ALTER TABLE openrisow.tbsss_agendamentos ADD CONSTRAINT ck_tbsss_agd_ativo CHECK (ativo IN ('S', 'N'));

ALTER TABLE openrisow.tbsss_agendamentos ADD CONSTRAINT ck_tbsss_agd_dia CHECK (dia_mes IS NULL OR dia_mes BETWEEN 1 AND 31);

ALTER TABLE openrisow.tbsss_agendamentos ADD CONSTRAINT ck_tbsss_agd_hora CHECK (hora_execucao IS NULL OR REGEXP_LIKE(hora_execucao, '^([01][0-9]|2[0-3]):[0-5][0-9]$'));

ALTER TABLE openrisow.tbsss_agendamentos ADD CONSTRAINT ck_tbsss_agd_dsem CHECK (dias_semana IS NULL OR REGEXP_LIKE(dias_semana, '^[1-7](,[1-7]){0,6}$'));

ALTER TABLE openrisow.tbsss_agendamentos ADD CONSTRAINT ck_tbsss_agd_fim CHECK (data_fim IS NULL OR data_fim >= data_inicio);

ALTER TABLE openrisow.tbsss_agendamentos ADD CONSTRAINT ck_tbsss_agd_pausa CHECK (pausa_motivo IS NULL OR pausa_motivo IN ('USUARIO_INATIVO','SEM_PERMISSAO','SCRIPT_INATIVO','AMBIENTE_INATIVO','PARAM_INVALIDO','CRON_INVALIDO','CONCLUIDO','MANUAL','ERRO_INTERNO'));

ALTER TABLE openrisow.tbsss_agendamentos ADD CONSTRAINT ck_tbsss_agd_campos CHECK ((tipo_recorrencia = 'UNICA') OR (tipo_recorrencia = 'DIARIA' AND hora_execucao IS NOT NULL) OR (tipo_recorrencia = 'SEMANAL' AND hora_execucao IS NOT NULL AND dias_semana IS NOT NULL) OR (tipo_recorrencia = 'MENSAL' AND hora_execucao IS NOT NULL AND dia_mes IS NOT NULL) OR (tipo_recorrencia = 'CRON' AND expressao_cron IS NOT NULL));

ALTER TABLE openrisow.tbsss_agendamentos ADD CONSTRAINT ck_tbsss_agd_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT pk_tbsss_tickets PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_stat CHECK (status IN ('PENDING','RUNNING','SUCCESS','FAILED','CANCELLED'));

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_prio CHECK (prioridade BETWEEN 1 AND 4);

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_cancreq CHECK (cancel_requested IN ('S','N'));

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_logtr CHECK (log_truncado IN ('S','N'));

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_logoff CHECK (log_offset_chars >= 0);

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_motivo CHECK (status_motivo IS NULL OR status_motivo IN ('EXIT_OK','EXIT_ERROR','KILLED_SIGNAL','TIMEOUT','NODE_OFFLINE','ORPHAN_PROCESS','FENCED','PRECHECK_FAILED','SPAWN_ERROR','LOG_LIMIT','SHUTDOWN','CANCEL_USER'));

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_sha CHECK (arquivo_sha256 IS NULL OR REGEXP_LIKE(arquivo_sha256, '^[0-9a-f]{64}$'));

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_ticket_resp ADD CONSTRAINT pk_tbsss_ticket_resp PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_ticket_resp ADD CONSTRAINT uk_tbsss_trsp_tck_prm UNIQUE (ticket_id, parametro_id);

ALTER TABLE openrisow.tbsss_ticket_resp ADD CONSTRAINT ck_tbsss_trsp_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_agentes ADD CONSTRAINT pk_tbsss_agentes PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_agentes ADD CONSTRAINT uk_tbsss_agt_codigo UNIQUE (codigo);

ALTER TABLE openrisow.tbsss_agentes ADD CONSTRAINT ck_tbsss_agt_stat CHECK (status IN ('ATIVO','PARADO'));

ALTER TABLE openrisow.tbsss_agentes ADD CONSTRAINT ck_tbsss_agt_plat CHECK (plataforma IS NULL OR plataforma IN ('LINUX','UNIX'));

ALTER TABLE openrisow.tbsss_agentes ADD CONSTRAINT ck_tbsss_agt_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_auditoria ADD CONSTRAINT pk_tbsss_auditoria PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_controle ADD CONSTRAINT pk_tbsss_controle PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_controle ADD CONSTRAINT ck_tbsss_ctl_id CHECK (id = 1);

ALTER TABLE openrisow.tbsss_controle ADD CONSTRAINT ck_tbsss_ctl_versao CHECK (versao_esquema >= 1);

-- ------------------------------------------------------------------------------
-- FASE 4: CONSTRAINTS (FK)
-- ------------------------------------------------------------------------------

ALTER TABLE openrisow.tbsss_perfil_func ADD CONSTRAINT fk_tbsss_pfnc_per FOREIGN KEY (perfil_id) REFERENCES openrisow.tbsss_perfis (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_perfil_func ADD CONSTRAINT fk_tbsss_pfnc_fnc FOREIGN KEY (funcionalidade_id) REFERENCES openrisow.tbsss_funcionalidades (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_perfil_amb ADD CONSTRAINT fk_tbsss_pamb_per FOREIGN KEY (perfil_id) REFERENCES openrisow.tbsss_perfis (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_perfil_amb ADD CONSTRAINT fk_tbsss_pamb_amb FOREIGN KEY (ambiente_id) REFERENCES openrisow.tbsss_ambientes (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_perfil_scr ADD CONSTRAINT fk_tbsss_pscr_per FOREIGN KEY (perfil_id) REFERENCES openrisow.tbsss_perfis (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_perfil_scr ADD CONSTRAINT fk_tbsss_pscr_scr FOREIGN KEY (script_id) REFERENCES openrisow.tbsss_scripts (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_script_amb ADD CONSTRAINT fk_tbsss_samb_scr FOREIGN KEY (script_id) REFERENCES openrisow.tbsss_scripts (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_script_amb ADD CONSTRAINT fk_tbsss_samb_amb FOREIGN KEY (ambiente_id) REFERENCES openrisow.tbsss_ambientes (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_usuarios ADD CONSTRAINT fk_tbsss_usr_per FOREIGN KEY (perfil_id) REFERENCES openrisow.tbsss_perfis (id);

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT fk_tbsss_sprm_scr FOREIGN KEY (script_id) REFERENCES openrisow.tbsss_scripts (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT fk_tbsss_sprm_prm FOREIGN KEY (parametro_id) REFERENCES openrisow.tbsss_parametros (id);

ALTER TABLE openrisow.tbsss_agendamentos ADD CONSTRAINT fk_tbsss_agd_scr FOREIGN KEY (script_id) REFERENCES openrisow.tbsss_scripts (id);

ALTER TABLE openrisow.tbsss_agendamentos ADD CONSTRAINT fk_tbsss_agd_usr FOREIGN KEY (usuario_id) REFERENCES openrisow.tbsss_usuarios (id);

ALTER TABLE openrisow.tbsss_agendamentos ADD CONSTRAINT fk_tbsss_agd_amb FOREIGN KEY (ambiente) REFERENCES openrisow.tbsss_ambientes (nome);

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT fk_tbsss_tck_scr FOREIGN KEY (script_id) REFERENCES openrisow.tbsss_scripts (id);

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT fk_tbsss_tck_amb FOREIGN KEY (ambiente) REFERENCES openrisow.tbsss_ambientes (nome);

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT fk_tbsss_tck_usr FOREIGN KEY (solicitante) REFERENCES openrisow.tbsss_usuarios (login);

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT fk_tbsss_tck_parent FOREIGN KEY (parent_ticket_id) REFERENCES openrisow.tbsss_tickets (id) ON DELETE SET NULL;

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT fk_tbsss_tck_agd FOREIGN KEY (agendamento_id) REFERENCES openrisow.tbsss_agendamentos (id) ON DELETE SET NULL;

ALTER TABLE openrisow.tbsss_ticket_resp ADD CONSTRAINT fk_tbsss_trsp_tck FOREIGN KEY (ticket_id) REFERENCES openrisow.tbsss_tickets (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_ticket_resp ADD CONSTRAINT fk_tbsss_trsp_prm FOREIGN KEY (parametro_id) REFERENCES openrisow.tbsss_parametros (id);

-- ------------------------------------------------------------------------------
-- FASE 5: INDICES
-- ------------------------------------------------------------------------------

CREATE INDEX openrisow.ix_tbsss_pfnc_fnc ON openrisow.tbsss_perfil_func (funcionalidade_id);

CREATE INDEX openrisow.ix_tbsss_pamb_amb ON openrisow.tbsss_perfil_amb (ambiente_id);

CREATE INDEX openrisow.ix_tbsss_pscr_scr ON openrisow.tbsss_perfil_scr (script_id);

CREATE INDEX openrisow.ix_tbsss_samb_amb ON openrisow.tbsss_script_amb (ambiente_id);

CREATE INDEX openrisow.ix_tbsss_usr_per ON openrisow.tbsss_usuarios (perfil_id);

CREATE INDEX openrisow.ix_tbsss_sprm_prm ON openrisow.tbsss_script_param (parametro_id);

CREATE INDEX openrisow.ix_tbsss_agd_scr ON openrisow.tbsss_agendamentos (script_id);

CREATE INDEX openrisow.ix_tbsss_agd_usr ON openrisow.tbsss_agendamentos (usuario_id);

CREATE INDEX openrisow.ix_tbsss_agd_amb ON openrisow.tbsss_agendamentos (ambiente);

CREATE INDEX openrisow.ix_tbsss_agd_prox ON openrisow.tbsss_agendamentos (ativo, proxima_execucao, id);

CREATE INDEX openrisow.ix_tbsss_tck_scr ON openrisow.tbsss_tickets (script_id, ambiente, status);

CREATE INDEX openrisow.ix_tbsss_tck_amb ON openrisow.tbsss_tickets (ambiente);

CREATE INDEX openrisow.ix_tbsss_tck_usr ON openrisow.tbsss_tickets (solicitante);

CREATE INDEX openrisow.ix_tbsss_tck_par ON openrisow.tbsss_tickets (parent_ticket_id);

CREATE INDEX openrisow.ix_tbsss_tck_agd ON openrisow.tbsss_tickets (agendamento_id);

CREATE INDEX openrisow.ix_tbsss_tck_crt ON openrisow.tbsss_tickets (created_at);

CREATE INDEX openrisow.ix_tbsss_tck_hist ON openrisow.tbsss_tickets (script_id, created_at);

CREATE INDEX openrisow.ix_tbsss_tck_fila ON openrisow.tbsss_tickets ((CASE WHEN status = 'PENDING' THEN prioridade END), (CASE WHEN status = 'PENDING' THEN scheduled_at END));

CREATE INDEX openrisow.ix_tbsss_tck_run ON openrisow.tbsss_tickets ((CASE WHEN status = 'RUNNING' THEN agente_id END));

CREATE UNIQUE INDEX openrisow.ix_tbsss_tck_ocor ON openrisow.tbsss_tickets ((CASE WHEN agendamento_id IS NOT NULL THEN agendamento_id END), (CASE WHEN agendamento_id IS NOT NULL THEN scheduled_at END));

CREATE INDEX openrisow.ix_tbsss_trsp_prm ON openrisow.tbsss_ticket_resp (parametro_id);

CREATE INDEX openrisow.ix_tbsss_aud_crt ON openrisow.tbsss_auditoria (created_at);

CREATE INDEX openrisow.ix_tbsss_aud_ent ON openrisow.tbsss_auditoria (entidade, entidade_id);

CREATE INDEX openrisow.ix_tbsss_aud_ator ON openrisow.tbsss_auditoria (ator);

-- ------------------------------------------------------------------------------
-- FASE 6: TRIGGERS
-- ------------------------------------------------------------------------------

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_amb_bi
BEFORE INSERT ON openrisow.tbsss_ambientes
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_ambientes.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_amb_bu
BEFORE UPDATE ON openrisow.tbsss_ambientes
FOR EACH ROW
BEGIN
    IF :NEW.nome <> :OLD.nome THEN
        RAISE_APPLICATION_ERROR(-20001, 'nome é imutável');
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_per_bi
BEFORE INSERT ON openrisow.tbsss_perfis
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_perfis.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_fnc_bi
BEFORE INSERT ON openrisow.tbsss_funcionalidades
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_funcionalidades.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_pfnc_bi
BEFORE INSERT ON openrisow.tbsss_perfil_func
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_perfil_func.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_pamb_bi
BEFORE INSERT ON openrisow.tbsss_perfil_amb
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_perfil_amb.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_scr_bi
BEFORE INSERT ON openrisow.tbsss_scripts
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_scripts.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_pscr_bi
BEFORE INSERT ON openrisow.tbsss_perfil_scr
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_perfil_scr.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_samb_bi
BEFORE INSERT ON openrisow.tbsss_script_amb
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_script_amb.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_usr_bi
BEFORE INSERT ON openrisow.tbsss_usuarios
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_usuarios.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_usr_bu
BEFORE UPDATE ON openrisow.tbsss_usuarios
FOR EACH ROW
BEGIN
    IF :NEW.login <> :OLD.login THEN
        RAISE_APPLICATION_ERROR(-20001, 'login é imutável');
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_prm_bi
BEFORE INSERT ON openrisow.tbsss_parametros
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_parametros.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_sprm_bi
BEFORE INSERT ON openrisow.tbsss_script_param
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_script_param.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_agd_bi
BEFORE INSERT ON openrisow.tbsss_agendamentos
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_agendamentos.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_tck_bi
BEFORE INSERT ON openrisow.tbsss_tickets
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_tickets.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_trsp_bi
BEFORE INSERT ON openrisow.tbsss_ticket_resp
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_ticket_resp.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_agt_bi
BEFORE INSERT ON openrisow.tbsss_agentes
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_agentes.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_aud_bi
BEFORE INSERT ON openrisow.tbsss_auditoria
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_auditoria.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_ctl_bi
BEFORE INSERT ON openrisow.tbsss_controle
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_controle.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

