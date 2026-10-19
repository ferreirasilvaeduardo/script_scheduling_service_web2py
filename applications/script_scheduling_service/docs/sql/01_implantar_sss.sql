SET DEFINE OFF;
SET SERVEROUTPUT ON;
-- Em caso de erro (ex: objeto ou constraint ja existente), o SQL*Plus continua a execucao (fallback/passa por cima)
WHENEVER SQLERROR CONTINUE;

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
)
LOB (parametros_json) STORE AS SECUREFILE (CACHE);

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
)
LOB (parametros_enviados, log_output) STORE AS SECUREFILE (CACHE);

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

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_amb_bi
-- TABELA ALVO: openrisow.tbsss_ambientes
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_ambientes FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_ambientes. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_amb_bi
BEFORE INSERT ON openrisow.tbsss_ambientes
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_ambientes.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_amb_bu
-- TABELA ALVO: openrisow.tbsss_ambientes
-- EVENTO: BEFORE UPDATE ON openrisow.tbsss_ambientes FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Garante a imutabilidade estrita da chave natural 'nome'.
-- Bloqueia qualquer alteracao posterior de valor para preservar integridade de FKs.
-- REGRA: README §10 e AGENTS.md §4.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_amb_bu
BEFORE UPDATE ON openrisow.tbsss_ambientes
FOR EACH ROW
BEGIN
    IF :NEW.nome <> :OLD.nome THEN
        RAISE_APPLICATION_ERROR(-20001, 'nome é imutável');
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_per_bi
-- TABELA ALVO: openrisow.tbsss_perfis
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_perfis FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_perfis. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_per_bi
BEFORE INSERT ON openrisow.tbsss_perfis
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_perfis.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_fnc_bi
-- TABELA ALVO: openrisow.tbsss_funcionalidades
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_funcionalidades FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_funcionalidades. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_fnc_bi
BEFORE INSERT ON openrisow.tbsss_funcionalidades
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_funcionalidades.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_pfnc_bi
-- TABELA ALVO: openrisow.tbsss_perfil_func
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_perfil_func FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_perfil_func. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_pfnc_bi
BEFORE INSERT ON openrisow.tbsss_perfil_func
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_perfil_func.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_pamb_bi
-- TABELA ALVO: openrisow.tbsss_perfil_amb
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_perfil_amb FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_perfil_amb. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_pamb_bi
BEFORE INSERT ON openrisow.tbsss_perfil_amb
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_perfil_amb.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_scr_bi
-- TABELA ALVO: openrisow.tbsss_scripts
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_scripts FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_scripts. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_scr_bi
BEFORE INSERT ON openrisow.tbsss_scripts
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_scripts.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_pscr_bi
-- TABELA ALVO: openrisow.tbsss_perfil_scr
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_perfil_scr FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_perfil_scr. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_pscr_bi
BEFORE INSERT ON openrisow.tbsss_perfil_scr
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_perfil_scr.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_samb_bi
-- TABELA ALVO: openrisow.tbsss_script_amb
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_script_amb FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_script_amb. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_samb_bi
BEFORE INSERT ON openrisow.tbsss_script_amb
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_script_amb.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_usr_bi
-- TABELA ALVO: openrisow.tbsss_usuarios
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_usuarios FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_usuarios. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_usr_bi
BEFORE INSERT ON openrisow.tbsss_usuarios
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_usuarios.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_usr_bu
-- TABELA ALVO: openrisow.tbsss_usuarios
-- EVENTO: BEFORE UPDATE ON openrisow.tbsss_usuarios FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Garante a imutabilidade estrita da chave natural 'login'.
-- Bloqueia qualquer alteracao posterior de valor para preservar integridade de FKs.
-- REGRA: README §10 e AGENTS.md §4.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_usr_bu
BEFORE UPDATE ON openrisow.tbsss_usuarios
FOR EACH ROW
BEGIN
    IF :NEW.login <> :OLD.login THEN
        RAISE_APPLICATION_ERROR(-20001, 'login é imutável');
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_prm_bi
-- TABELA ALVO: openrisow.tbsss_parametros
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_parametros FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_parametros. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_prm_bi
BEFORE INSERT ON openrisow.tbsss_parametros
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_parametros.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_sprm_bi
-- TABELA ALVO: openrisow.tbsss_script_param
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_script_param FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_script_param. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_sprm_bi
BEFORE INSERT ON openrisow.tbsss_script_param
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_script_param.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_agd_bi
-- TABELA ALVO: openrisow.tbsss_agendamentos
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_agendamentos FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_agendamentos. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_agd_bi
BEFORE INSERT ON openrisow.tbsss_agendamentos
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_agendamentos.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_tck_bi
-- TABELA ALVO: openrisow.tbsss_tickets
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_tickets FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_tickets. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_tck_bi
BEFORE INSERT ON openrisow.tbsss_tickets
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_tickets.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_trsp_bi
-- TABELA ALVO: openrisow.tbsss_ticket_resp
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_ticket_resp FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_ticket_resp. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_trsp_bi
BEFORE INSERT ON openrisow.tbsss_ticket_resp
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_ticket_resp.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_agt_bi
-- TABELA ALVO: openrisow.tbsss_agentes
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_agentes FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_agentes. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_agt_bi
BEFORE INSERT ON openrisow.tbsss_agentes
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_agentes.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_aud_bi
-- TABELA ALVO: openrisow.tbsss_auditoria
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_auditoria FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_auditoria. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_aud_bi
BEFORE INSERT ON openrisow.tbsss_auditoria
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_auditoria.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_ctl_bi
-- TABELA ALVO: openrisow.tbsss_controle
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_controle FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_controle. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_ctl_bi
BEFORE INSERT ON openrisow.tbsss_controle
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_controle.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ------------------------------------------------------------------------------
-- FASE 7: DICIONARIO E GOVERNANCA DE DADOS (COMMENTS)
-- ------------------------------------------------------------------------------

COMMENT ON TABLE openrisow.tbsss_ambientes IS 'Cadastro de ambientes operacionais para execucao de rotinas (PRODUCAO, HOMOLOGACAO, CLONES)';
COMMENT ON COLUMN openrisow.tbsss_ambientes.id IS 'Identificador unico sequencial do ambiente (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_ambientes.nome IS 'Nome mnemonico unico do ambiente em maiusculas (chave natural imutavel)';
COMMENT ON COLUMN openrisow.tbsss_ambientes.descricao IS 'Descricao detalhada do ambiente, servidor host e finalidade';
COMMENT ON COLUMN openrisow.tbsss_ambientes.conexao IS 'String de conexao ou alias DSN/TNS sugerido para o banco de dados do ambiente';
COMMENT ON COLUMN openrisow.tbsss_ambientes.ativo IS 'Indicador de vigencia do ambiente (S=Ativo, N=Inativo)';
COMMENT ON COLUMN openrisow.tbsss_ambientes.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_ambientes.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_ambientes.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_ambientes.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_perfis IS 'Perfis de acesso para autorizacao baseada em papeis (RBAC)';
COMMENT ON COLUMN openrisow.tbsss_perfis.id IS 'Identificador unico sequencial do perfil (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_perfis.nome IS 'Nome unico de identificacao do perfil (ex: ADMINISTRADOR, OPERADOR)';
COMMENT ON COLUMN openrisow.tbsss_perfis.descricao IS 'Finalidade e escopo de atuacao dos usuarios vinculados ao perfil';
COMMENT ON COLUMN openrisow.tbsss_perfis.is_admin IS 'Indicador de perfil com poderes administrativos plenos (S/N)';
COMMENT ON COLUMN openrisow.tbsss_perfis.perm_versao IS 'Versao incremental das permissoes para invalidacao de sessoes ativas';
COMMENT ON COLUMN openrisow.tbsss_perfis.ativo IS 'Indicador de vigencia do perfil no sistema (S=Ativo, N=Inativo)';
COMMENT ON COLUMN openrisow.tbsss_perfis.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_perfis.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_perfis.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_perfis.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_funcionalidades IS 'Catalogo canonico de permissoes e operacoes controladas pelo sistema';
COMMENT ON COLUMN openrisow.tbsss_funcionalidades.id IS 'Identificador unico sequencial da funcionalidade (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_funcionalidades.codigo IS 'Codigo mnemonico unico da operacao (ex: EXEC_SCRIPT, VER_LOGS, CANC_TICKET)';
COMMENT ON COLUMN openrisow.tbsss_funcionalidades.nome IS 'Nome amigavel de exibicao da funcionalidade na interface';
COMMENT ON COLUMN openrisow.tbsss_funcionalidades.modulo IS 'Modulo funcional do sistema ao qual a operacao pertence (OPERACAO, ADMIN)';
COMMENT ON COLUMN openrisow.tbsss_funcionalidades.descricao IS 'Descricao clara das acoes permitidas por esta funcionalidade';
COMMENT ON COLUMN openrisow.tbsss_funcionalidades.ativo IS 'Indicador de vigencia da funcionalidade no sistema (S/N)';
COMMENT ON COLUMN openrisow.tbsss_funcionalidades.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_funcionalidades.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_funcionalidades.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_funcionalidades.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_perfil_func IS 'Matriz associativa de permissoes que vincula perfis a funcionalidades autorizadas';
COMMENT ON COLUMN openrisow.tbsss_perfil_func.id IS 'Identificador unico sequencial do vinculo (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_perfil_func.perfil_id IS 'Identificador do perfil associado (FK para tbsss_perfis)';
COMMENT ON COLUMN openrisow.tbsss_perfil_func.funcionalidade_id IS 'Identificador da funcionalidade autorizada (FK para tbsss_funcionalidades)';
COMMENT ON COLUMN openrisow.tbsss_perfil_func.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_perfil_func.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_perfil_func.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_perfil_func.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_perfil_amb IS 'Associacao que delimita os ambientes onde cada perfil possui autorizacao';
COMMENT ON COLUMN openrisow.tbsss_perfil_amb.id IS 'Identificador unico sequencial do vinculo (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_perfil_amb.perfil_id IS 'Identificador do perfil autorizado (FK para tbsss_perfis)';
COMMENT ON COLUMN openrisow.tbsss_perfil_amb.ambiente_id IS 'Identificador do ambiente autorizado (FK para tbsss_ambientes)';
COMMENT ON COLUMN openrisow.tbsss_perfil_amb.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_perfil_amb.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_perfil_amb.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_perfil_amb.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_scripts IS 'Catalogo de rotinas e scripts homologados para execucao automatizada';
COMMENT ON COLUMN openrisow.tbsss_scripts.id IS 'Identificador unico sequencial do script (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_scripts.nome IS 'Nome unico da rotina (ex: carga_diaria, relatorio_mensal)';
COMMENT ON COLUMN openrisow.tbsss_scripts.descricao IS 'Detalhamento da finalidade, regras e impacto da execucao do script';
COMMENT ON COLUMN openrisow.tbsss_scripts.grupo IS 'Coluna grupo da tabela tbsss_scripts';
COMMENT ON COLUMN openrisow.tbsss_scripts.categoria IS 'Categoria de negocio ou agrupador funcional da rotina';
COMMENT ON COLUMN openrisow.tbsss_scripts.etapa IS 'Coluna etapa da tabela tbsss_scripts';
COMMENT ON COLUMN openrisow.tbsss_scripts.interpretador IS 'Interpretador utilizado para execucao (PYTHON3, BASH, SH)';
COMMENT ON COLUMN openrisow.tbsss_scripts.path_file IS 'Caminho absoluto normalizado do script no sistema de arquivos do servidor';
COMMENT ON COLUMN openrisow.tbsss_scripts.tipo_param IS 'Coluna tipo_param da tabela tbsss_scripts';
COMMENT ON COLUMN openrisow.tbsss_scripts.max_qtd_parallel_env IS 'Coluna max_qtd_parallel_env da tabela tbsss_scripts';
COMMENT ON COLUMN openrisow.tbsss_scripts.timeout_seg IS 'Coluna timeout_seg da tabela tbsss_scripts';
COMMENT ON COLUMN openrisow.tbsss_scripts.ativo IS 'Indicador de disponibilidade da rotina para novas execucoes (S/N)';
COMMENT ON COLUMN openrisow.tbsss_scripts.sha256_homologado IS 'Coluna sha256_homologado da tabela tbsss_scripts';
COMMENT ON COLUMN openrisow.tbsss_scripts.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_scripts.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_scripts.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_scripts.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_perfil_scr IS 'Associacao que define quais rotinas cada perfil tem permissao para disparar';
COMMENT ON COLUMN openrisow.tbsss_perfil_scr.id IS 'Identificador unico sequencial do vinculo (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_perfil_scr.perfil_id IS 'Identificador do perfil autorizado (FK para tbsss_perfis)';
COMMENT ON COLUMN openrisow.tbsss_perfil_scr.script_id IS 'Identificador da rotina homologada (FK para tbsss_scripts)';
COMMENT ON COLUMN openrisow.tbsss_perfil_scr.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_perfil_scr.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_perfil_scr.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_perfil_scr.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_script_amb IS 'Homologacao tecnica que associa rotinas aos ambientes onde podem rodar';
COMMENT ON COLUMN openrisow.tbsss_script_amb.id IS 'Identificador unico sequencial da homologacao (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_script_amb.script_id IS 'Identificador do script homologado (FK para tbsss_scripts)';
COMMENT ON COLUMN openrisow.tbsss_script_amb.ambiente_id IS 'Identificador do ambiente onde a rotina e permitida (FK para tbsss_ambientes)';
COMMENT ON COLUMN openrisow.tbsss_script_amb.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_script_amb.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_script_amb.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_script_amb.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_usuarios IS 'Cadastro de operadores do sistema, credenciais e controle de sessao';
COMMENT ON COLUMN openrisow.tbsss_usuarios.id IS 'Identificador unico sequencial do usuario (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_usuarios.login IS 'Identificador de login do usuario (chave natural imutavel)';
COMMENT ON COLUMN openrisow.tbsss_usuarios.nome IS 'Nome completo do operador para identificacao';
COMMENT ON COLUMN openrisow.tbsss_usuarios.senha_hash IS 'Hash criptografico da senha gerado via PBKDF2-SHA256 (200k iteracoes)';
COMMENT ON COLUMN openrisow.tbsss_usuarios.perfil_id IS 'Identificador do perfil de acesso atribuido (FK para tbsss_perfis)';
COMMENT ON COLUMN openrisow.tbsss_usuarios.tentativas_falha IS 'Numero de tentativas consecutivas de autenticacao incorretas';
COMMENT ON COLUMN openrisow.tbsss_usuarios.bloqueado_ate IS 'Data e hora limite de bloqueio temporario por excesso de falhas';
COMMENT ON COLUMN openrisow.tbsss_usuarios.ultimo_login IS 'Coluna ultimo_login da tabela tbsss_usuarios';
COMMENT ON COLUMN openrisow.tbsss_usuarios.senha_alterada_em IS 'Coluna senha_alterada_em da tabela tbsss_usuarios';
COMMENT ON COLUMN openrisow.tbsss_usuarios.sessao_epoch IS 'Contador de revogacao de sessoes ativas para seguranca';
COMMENT ON COLUMN openrisow.tbsss_usuarios.ativo IS 'Indicador se o usuario esta ativo (S=Ativo, N=Bloqueado/Inativo)';
COMMENT ON COLUMN openrisow.tbsss_usuarios.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_usuarios.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_usuarios.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_usuarios.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_parametros IS 'Dicionario de perguntas, variaveis e flags reutilizaveis em scripts';
COMMENT ON COLUMN openrisow.tbsss_parametros.id IS 'Identificador unico sequencial do parametro (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_parametros.codigo IS 'Codigo mnemonico unico do parametro (ex: DATA_REF, FORMATO)';
COMMENT ON COLUMN openrisow.tbsss_parametros.param_nomeado IS 'Coluna param_nomeado da tabela tbsss_parametros';
COMMENT ON COLUMN openrisow.tbsss_parametros.label IS 'Rotulo de exibicao amigavel apresentado no formulario ao usuario';
COMMENT ON COLUMN openrisow.tbsss_parametros.descricao IS 'Texto explicativo de orientacao ao operador';
COMMENT ON COLUMN openrisow.tbsss_parametros.tipo_componente IS 'Tipo de componente visual (TEXTO, NUMERO, DATA, SELECT, RADIO, CHECKBOX)';
COMMENT ON COLUMN openrisow.tbsss_parametros.opcoes_json IS 'Opcoes selecionaveis em formato JSON para componentes do tipo lista';
COMMENT ON COLUMN openrisow.tbsss_parametros.valor_padrao IS 'Valor pre-definido padrao sugerido no formulario';
COMMENT ON COLUMN openrisow.tbsss_parametros.regex_validacao IS 'Expressao regular segura para validacao do valor inserido';
COMMENT ON COLUMN openrisow.tbsss_parametros.sensivel IS 'Indicador se o dado e confidencial e deve ser mascarado em logs (S/N)';
COMMENT ON COLUMN openrisow.tbsss_parametros.ativo IS 'Indicador de vigencia do parametro no sistema (S/N)';
COMMENT ON COLUMN openrisow.tbsss_parametros.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_parametros.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_parametros.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_parametros.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_script_param IS 'Composicao e ordenacao dos parametros exigidos por cada rotina';
COMMENT ON COLUMN openrisow.tbsss_script_param.id IS 'Identificador unico sequencial da associacao (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_script_param.script_id IS 'Identificador do script (FK para tbsss_scripts)';
COMMENT ON COLUMN openrisow.tbsss_script_param.parametro_id IS 'Identificador do parametro associado (FK para tbsss_parametros)';
COMMENT ON COLUMN openrisow.tbsss_script_param.ordem IS 'Posicao de apresentacao do campo no questionario de execucao';
COMMENT ON COLUMN openrisow.tbsss_script_param.obrigatorio IS 'Indicador se o preenchimento e mandatorio para esta rotina (S/N)';
COMMENT ON COLUMN openrisow.tbsss_script_param.valor_padrao_sub IS 'Valor padrao especifico que sobrescreve o valor do parametro para este script';
COMMENT ON COLUMN openrisow.tbsss_script_param.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_script_param.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_script_param.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_script_param.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_agendamentos IS 'Regras de execucao periodica automatica ou avulsa de rotinas';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.id IS 'Identificador unico sequencial do agendamento (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.nome IS 'Titulo descritivo da regra de agendamento';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.script_id IS 'Identificador da rotina a ser executada (FK para tbsss_scripts)';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.ambiente IS 'Nome do ambiente onde a rotina deve ser disparada (FK para tbsss_ambientes)';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.usuario_id IS 'Operador responsavel pelo agendamento (FK para tbsss_usuarios)';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.prioridade IS 'Nivel de prioridade da execucao (1=Critico a 4=Baixa)';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.tipo_recorrencia IS 'Tipo de periodicidade (UNICA, DIARIA, SEMANAL, MENSAL, CRON)';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.expressao_cron IS 'Expressao cron no formato padrao de 5 campos (minuto hora dia mes dsem)';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.hora_execucao IS 'Horario de disparo no formato HH:MM para recorrencias diarias/semanais/mensais';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.dias_semana IS 'Dias da semana selecionados (1=Dom a 7=Sab) para agendamento semanal';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.dia_mes IS 'Dia do mes (1 a 31) para agendamento mensal';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.parametros_json IS 'Parametros congelados configurados para o agendamento em JSON (CLOB)';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.data_inicio IS 'Data inicial de vigencia do agendamento';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.data_fim IS 'Data final limite para expiracao do agendamento';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.proxima_execucao IS 'Data e hora exatas calculadas para o proximo disparo';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.ultima_execucao IS 'Data e hora em que ocorreu o ultimo disparo';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.ultimo_ticket_id IS 'Identificador do ticket mais recente gerado por esta regra';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.pausa_motivo IS 'Motivo formal em caso de suspensao da regra (ex: USUARIO_INATIVO, MANUAL)';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.ativo IS 'Indicador de vigencia da regra (S=Ativo, N=Pausado/Concluido)';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_agendamentos.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_tickets IS 'Fila de execucao, ciclo de vida e historico de execucao de scripts';
COMMENT ON COLUMN openrisow.tbsss_tickets.id IS 'Identificador unico sequencial do ticket de execucao (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_tickets.script_id IS 'Identificador da rotina solicitada (FK para tbsss_scripts)';
COMMENT ON COLUMN openrisow.tbsss_tickets.ambiente IS 'Nome do ambiente alvo da execucao (FK para tbsss_ambientes)';
COMMENT ON COLUMN openrisow.tbsss_tickets.solicitante IS 'Login do operador que solicitou a execucao (FK para tbsss_usuarios)';
COMMENT ON COLUMN openrisow.tbsss_tickets.ip_origem IS 'Endereco IP do cliente que originou o pedido';
COMMENT ON COLUMN openrisow.tbsss_tickets.agente_id IS 'Identificador do daemon do agente que executou o ticket';
COMMENT ON COLUMN openrisow.tbsss_tickets.process_id IS 'Identificador do processo (PID) no sistema operacional do servidor';
COMMENT ON COLUMN openrisow.tbsss_tickets.process_start IS 'Coluna process_start da tabela tbsss_tickets';
COMMENT ON COLUMN openrisow.tbsss_tickets.status IS 'Situacao da execucao (PENDING, RUNNING, SUCCESS, FAILED, CANCELLED)';
COMMENT ON COLUMN openrisow.tbsss_tickets.prioridade IS 'Prioridade de atendimento na fila (1=Critico, 2=Alta, 3=Normal, 4=Baixa)';
COMMENT ON COLUMN openrisow.tbsss_tickets.cancel_requested IS 'Indicador se o cancelamento foi requisitado pelo operador (S/N)';
COMMENT ON COLUMN openrisow.tbsss_tickets.status_motivo IS 'Codigo tecnico do motivo de falha ou cancelamento';
COMMENT ON COLUMN openrisow.tbsss_tickets.parent_ticket_id IS 'Identificador do ticket pai em caso de reexecucao';
COMMENT ON COLUMN openrisow.tbsss_tickets.agendamento_id IS 'Identificador da regra de agendamento de origem (se houver)';
COMMENT ON COLUMN openrisow.tbsss_tickets.parametros_enviados IS 'Copia fiel dos parametros de entrada fornecidos na solicitacao (CLOB)';
COMMENT ON COLUMN openrisow.tbsss_tickets.log_output IS 'Saida completa de execucao capturada de stdout/stderr (CLOB)';
COMMENT ON COLUMN openrisow.tbsss_tickets.log_offset_chars IS 'Controle tecnico de caracteres confirmados gravados no log';
COMMENT ON COLUMN openrisow.tbsss_tickets.log_truncado IS 'Indicador se o log excedeu o limite maximo de tamanho (S/N)';
COMMENT ON COLUMN openrisow.tbsss_tickets.return_code IS 'Coluna return_code da tabela tbsss_tickets';
COMMENT ON COLUMN openrisow.tbsss_tickets.arquivo_sha256 IS 'Coluna arquivo_sha256 da tabela tbsss_tickets';
COMMENT ON COLUMN openrisow.tbsss_tickets.scheduled_at IS 'Data e hora agendadas para o processamento';
COMMENT ON COLUMN openrisow.tbsss_tickets.started_at IS 'Data e hora efetivas do inicio da execucao pelo agente';
COMMENT ON COLUMN openrisow.tbsss_tickets.heartbeat_at IS 'Data e hora da ultima confirmacao de atividade do processo';
COMMENT ON COLUMN openrisow.tbsss_tickets.finished_at IS 'Data e hora de conclusao ou encerramento da execucao';
COMMENT ON COLUMN openrisow.tbsss_tickets.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_tickets.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_tickets.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_tickets.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_ticket_resp IS 'Valores individuais preenchidos para cada parametro no disparo do ticket';
COMMENT ON COLUMN openrisow.tbsss_ticket_resp.id IS 'Identificador unico sequencial da resposta (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_ticket_resp.ticket_id IS 'Identificador do ticket correspondente (FK para tbsss_tickets)';
COMMENT ON COLUMN openrisow.tbsss_ticket_resp.parametro_id IS 'Identificador do parametro respondido (FK para tbsss_parametros)';
COMMENT ON COLUMN openrisow.tbsss_ticket_resp.valor_resposta IS 'Coluna valor_resposta da tabela tbsss_ticket_resp';
COMMENT ON COLUMN openrisow.tbsss_ticket_resp.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_ticket_resp.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_ticket_resp.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_ticket_resp.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_agentes IS 'Registro, versao e sinais de vida dos daemons executores instalados';
COMMENT ON COLUMN openrisow.tbsss_agentes.id IS 'Identificador unico sequencial do agente (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_agentes.codigo IS 'Codigo identificador unico do agente (ex: agt-node01)';
COMMENT ON COLUMN openrisow.tbsss_agentes.hostname IS 'Nome de rede (hostname) da maquina servidora do agente';
COMMENT ON COLUMN openrisow.tbsss_agentes.pid_daemon IS 'Identificador de processo (PID) do daemon no servidor';
COMMENT ON COLUMN openrisow.tbsss_agentes.versao IS 'Versao do software do servico em execucao no agente';
COMMENT ON COLUMN openrisow.tbsss_agentes.ambientes IS 'Lista separada por virgulas dos ambientes atendidos por este no';
COMMENT ON COLUMN openrisow.tbsss_agentes.plataforma IS 'Sistema operacional da maquina servidora (POSIX)';
COMMENT ON COLUMN openrisow.tbsss_agentes.interpretadores IS 'Interpretadores homologados disponiveis no servidor (PYTHON3, BASH, SH)';
COMMENT ON COLUMN openrisow.tbsss_agentes.status IS 'Estado de operacao do no (ATIVO, INATIVO, DRAIN)';
COMMENT ON COLUMN openrisow.tbsss_agentes.iniciado_em IS 'Data e hora de inicializacao do daemon';
COMMENT ON COLUMN openrisow.tbsss_agentes.heartbeat_at IS 'Data e hora do sinal periodico de disponibilidade mais recente';
COMMENT ON COLUMN openrisow.tbsss_agentes.config_criticos IS 'Coluna config_criticos da tabela tbsss_agentes';
COMMENT ON COLUMN openrisow.tbsss_agentes.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_agentes.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_agentes.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_agentes.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_auditoria IS 'Trilha de auditoria imutavel para conformidade e rastreabilidade';
COMMENT ON COLUMN openrisow.tbsss_auditoria.id IS 'Identificador unico sequencial do evento de auditoria (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_auditoria.ator IS 'Identificador do operador ou servico que executou a acao';
COMMENT ON COLUMN openrisow.tbsss_auditoria.ip_origem IS 'Endereco IP do cliente que solicitou a operacao';
COMMENT ON COLUMN openrisow.tbsss_auditoria.acao IS 'Codigo mnemonico da acao executada (ex: CAD_INSERIR, TICKET_CRIAR)';
COMMENT ON COLUMN openrisow.tbsss_auditoria.entidade IS 'Nome da tabela ou entidade alvo afetada';
COMMENT ON COLUMN openrisow.tbsss_auditoria.entidade_id IS 'Identificador numerico do registro alvo afetado';
COMMENT ON COLUMN openrisow.tbsss_auditoria.detalhe IS 'Texto descritivo ou dados em formato estruturado sobre o evento';
COMMENT ON COLUMN openrisow.tbsss_auditoria.created_at IS 'Data e hora exatas da realizacao do evento auditado';
COMMENT ON TABLE openrisow.tbsss_controle IS 'Parametros de controle global, versao de esquema e concessao de limpeza';
COMMENT ON COLUMN openrisow.tbsss_controle.id IS 'Identificador unico da linha de controle global (sempre 1)';
COMMENT ON COLUMN openrisow.tbsss_controle.versao_esquema IS 'Numero da versao estrutural do banco de dados atualmente instalada';
COMMENT ON COLUMN openrisow.tbsss_controle.versao_aplicada_em IS 'Data e hora de aplicacao da versao de esquema atual';
COMMENT ON COLUMN openrisow.tbsss_controle.versao_aplicada_por IS 'Identificador de quem realizou a aplicacao do esquema';
COMMENT ON COLUMN openrisow.tbsss_controle.purge_dono IS 'Identificador do no que detem a concessao de purga de dados';
COMMENT ON COLUMN openrisow.tbsss_controle.purge_concessao_ate IS 'Data e hora limite de expiracao da concessao de purga';


-- ------------------------------------------------------------------------------
-- FASE 7: SEED INICIAL (MERGE IDEMPOTENTE)
-- ------------------------------------------------------------------------------

MERGE INTO openrisow.tbsss_funcionalidades dst
USING (SELECT 'EXEC_SCRIPT' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.nome = 'Disparar Scripts',
             dst.modulo = 'OPERACAO',
             dst.descricao = 'Preencher questionários e abrir tickets',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR dst.nome <> 'Disparar Scripts'
     OR dst.modulo <> 'OPERACAO'
     OR dst.descricao <> 'Preencher questionários e abrir tickets'
WHEN NOT MATCHED THEN
  INSERT (id, codigo, modulo, nome, descricao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_funcionalidades.NEXTVAL, 'EXEC_SCRIPT', 'OPERACAO', 'Disparar Scripts', 'Preencher questionários e abrir tickets', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_funcionalidades dst
USING (SELECT 'VER_LOGS' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.nome = 'Consultar Logs',
             dst.modulo = 'OPERACAO',
             dst.descricao = 'Visualizar logs e histórico em tempo quase real',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR dst.nome <> 'Consultar Logs'
     OR dst.modulo <> 'OPERACAO'
     OR dst.descricao <> 'Visualizar logs e histórico em tempo quase real'
WHEN NOT MATCHED THEN
  INSERT (id, codigo, modulo, nome, descricao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_funcionalidades.NEXTVAL, 'VER_LOGS', 'OPERACAO', 'Consultar Logs', 'Visualizar logs e histórico em tempo quase real', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_funcionalidades dst
USING (SELECT 'CANC_TICKET' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.nome = 'Cancelar Tickets',
             dst.modulo = 'OPERACAO',
             dst.descricao = 'Cancelar tickets de terceiros em ambientes autorizados',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR dst.nome <> 'Cancelar Tickets'
     OR dst.modulo <> 'OPERACAO'
     OR dst.descricao <> 'Cancelar tickets de terceiros em ambientes autorizados'
WHEN NOT MATCHED THEN
  INSERT (id, codigo, modulo, nome, descricao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_funcionalidades.NEXTVAL, 'CANC_TICKET', 'OPERACAO', 'Cancelar Tickets', 'Cancelar tickets de terceiros em ambientes autorizados', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_funcionalidades dst
USING (SELECT 'CAD_USUARIOS' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.nome = 'Gestão de Usuários',
             dst.modulo = 'ADMIN',
             dst.descricao = 'Gerenciar operadores e credenciais',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR dst.nome <> 'Gestão de Usuários'
     OR dst.modulo <> 'ADMIN'
     OR dst.descricao <> 'Gerenciar operadores e credenciais'
WHEN NOT MATCHED THEN
  INSERT (id, codigo, modulo, nome, descricao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_funcionalidades.NEXTVAL, 'CAD_USUARIOS', 'ADMIN', 'Gestão de Usuários', 'Gerenciar operadores e credenciais', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_funcionalidades dst
USING (SELECT 'CAD_PERFIS' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.nome = 'Gestão de Perfis',
             dst.modulo = 'ADMIN',
             dst.descricao = 'Gerenciar perfis e matrizes de permissão',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR dst.nome <> 'Gestão de Perfis'
     OR dst.modulo <> 'ADMIN'
     OR dst.descricao <> 'Gerenciar perfis e matrizes de permissão'
WHEN NOT MATCHED THEN
  INSERT (id, codigo, modulo, nome, descricao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_funcionalidades.NEXTVAL, 'CAD_PERFIS', 'ADMIN', 'Gestão de Perfis', 'Gerenciar perfis e matrizes de permissão', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_funcionalidades dst
USING (SELECT 'CAD_AMBIENTES' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.nome = 'Gestão de Ambientes',
             dst.modulo = 'ADMIN',
             dst.descricao = 'Gerenciar ambientes e DSNs',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR dst.nome <> 'Gestão de Ambientes'
     OR dst.modulo <> 'ADMIN'
     OR dst.descricao <> 'Gerenciar ambientes e DSNs'
WHEN NOT MATCHED THEN
  INSERT (id, codigo, modulo, nome, descricao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_funcionalidades.NEXTVAL, 'CAD_AMBIENTES', 'ADMIN', 'Gestão de Ambientes', 'Gerenciar ambientes e DSNs', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_funcionalidades dst
USING (SELECT 'CAD_SCRIPTS' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.nome = 'Gestão de Scripts',
             dst.modulo = 'ADMIN',
             dst.descricao = 'Cadastrar rotinas e homologação por ambiente',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR dst.nome <> 'Gestão de Scripts'
     OR dst.modulo <> 'ADMIN'
     OR dst.descricao <> 'Cadastrar rotinas e homologação por ambiente'
WHEN NOT MATCHED THEN
  INSERT (id, codigo, modulo, nome, descricao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_funcionalidades.NEXTVAL, 'CAD_SCRIPTS', 'ADMIN', 'Gestão de Scripts', 'Cadastrar rotinas e homologação por ambiente', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_funcionalidades dst
USING (SELECT 'CAD_PARAMETROS' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.nome = 'Dicionário de Parâmetros',
             dst.modulo = 'ADMIN',
             dst.descricao = 'Gerenciar perguntas e flags reutilizáveis',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR dst.nome <> 'Dicionário de Parâmetros'
     OR dst.modulo <> 'ADMIN'
     OR dst.descricao <> 'Gerenciar perguntas e flags reutilizáveis'
WHEN NOT MATCHED THEN
  INSERT (id, codigo, modulo, nome, descricao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_funcionalidades.NEXTVAL, 'CAD_PARAMETROS', 'ADMIN', 'Dicionário de Parâmetros', 'Gerenciar perguntas e flags reutilizáveis', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_funcionalidades dst
USING (SELECT 'CAD_AGENDAMENTOS' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.nome = 'Regras de Agendamento',
             dst.modulo = 'ADMIN',
             dst.descricao = 'Criar e gerenciar recorrências',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR dst.nome <> 'Regras de Agendamento'
     OR dst.modulo <> 'ADMIN'
     OR dst.descricao <> 'Criar e gerenciar recorrências'
WHEN NOT MATCHED THEN
  INSERT (id, codigo, modulo, nome, descricao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_funcionalidades.NEXTVAL, 'CAD_AGENDAMENTOS', 'ADMIN', 'Regras de Agendamento', 'Criar e gerenciar recorrências', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_funcionalidades dst
USING (SELECT 'VER_AUDITORIA' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.nome = 'Auditoria',
             dst.modulo = 'ADMIN',
             dst.descricao = 'Consultar a trilha de auditoria e os agentes',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR dst.nome <> 'Auditoria'
     OR dst.modulo <> 'ADMIN'
     OR dst.descricao <> 'Consultar a trilha de auditoria e os agentes'
WHEN NOT MATCHED THEN
  INSERT (id, codigo, modulo, nome, descricao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_funcionalidades.NEXTVAL, 'VER_AUDITORIA', 'ADMIN', 'Auditoria', 'Consultar a trilha de auditoria e os agentes', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_ambientes dst
USING (SELECT 'CLONE2' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'BRTLVLTS1199PL (10.238.10.209)',
             dst.conexao = '10.238.55.146/gfprod',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'BRTLVLTS1199PL (10.238.10.209)'
     OR NVL(dst.conexao, '~') <> '10.238.55.146/gfprod'
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, conexao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_ambientes.NEXTVAL, 'CLONE2', 'BRTLVLTS1199PL (10.238.10.209)', '10.238.55.146/gfprod', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_ambientes dst
USING (SELECT 'CLONE1' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'BRTLVLTS1198PL (10.238.10.208)',
             dst.conexao = '10.238.55.145/gfprod',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'BRTLVLTS1198PL (10.238.10.208)'
     OR NVL(dst.conexao, '~') <> '10.238.55.145/gfprod'
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, conexao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_ambientes.NEXTVAL, 'CLONE1', 'BRTLVLTS1198PL (10.238.10.208)', '10.238.55.145/gfprod', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_ambientes dst
USING (SELECT 'CLONE6' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'BRTLVLTS3089SL (10.238.10.210)',
             dst.conexao = '10.238.45.230/svc_gfprodc6',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'BRTLVLTS3089SL (10.238.10.210)'
     OR NVL(dst.conexao, '~') <> '10.238.45.230/svc_gfprodc6'
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, conexao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_ambientes.NEXTVAL, 'CLONE6', 'BRTLVLTS3089SL (10.238.10.210)', '10.238.45.230/svc_gfprodc6', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_ambientes dst
USING (SELECT 'CLONE7' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'BRTLVLTS1216PL (10.238.10.109)',
             dst.conexao = '10.238.45.230/svc_gfprodc7',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'BRTLVLTS1216PL (10.238.10.109)'
     OR NVL(dst.conexao, '~') <> '10.238.45.230/svc_gfprodc7'
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, conexao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_ambientes.NEXTVAL, 'CLONE7', 'BRTLVLTS1216PL (10.238.10.109)', '10.238.45.230/svc_gfprodc7', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_ambientes dst
USING (SELECT 'GFPREPROD' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'BRTLVLTY3067SL (10.129.177.188)',
             dst.conexao = '10.129.177.188/GFPR',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'BRTLVLTY3067SL (10.129.177.188)'
     OR NVL(dst.conexao, '~') <> '10.129.177.188/GFPR'
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, conexao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_ambientes.NEXTVAL, 'GFPREPROD', 'BRTLVLTY3067SL (10.129.177.188)', '10.129.177.188/GFPR', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfis dst
USING (SELECT 'ADMINISTRADOR' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Acesso irrestrito a todas as funcionalidades e ambientes',
             dst.is_admin = 'S',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.is_admin <> 'S'
     OR dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Acesso irrestrito a todas as funcionalidades e ambientes'
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, is_admin, perm_versao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfis.NEXTVAL, 'ADMINISTRADOR', 'Acesso irrestrito a todas as funcionalidades e ambientes', 'S', 1, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'ADMINISTRADOR' AND f.codigo = 'EXEC_SCRIPT'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'ADMINISTRADOR' AND f.codigo = 'VER_LOGS'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'ADMINISTRADOR' AND f.codigo = 'CANC_TICKET'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'ADMINISTRADOR' AND f.codigo = 'CAD_USUARIOS'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'ADMINISTRADOR' AND f.codigo = 'CAD_PERFIS'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'ADMINISTRADOR' AND f.codigo = 'CAD_AMBIENTES'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'ADMINISTRADOR' AND f.codigo = 'CAD_SCRIPTS'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'ADMINISTRADOR' AND f.codigo = 'CAD_PARAMETROS'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'ADMINISTRADOR' AND f.codigo = 'CAD_AGENDAMENTOS'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'ADMINISTRADOR' AND f.codigo = 'VER_AUDITORIA'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'ADMINISTRADOR' AND a.nome = 'CLONE2'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'ADMINISTRADOR' AND a.nome = 'CLONE1'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'ADMINISTRADOR' AND a.nome = 'CLONE6'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'ADMINISTRADOR' AND a.nome = 'CLONE7'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'ADMINISTRADOR' AND a.nome = 'GFPREPROD'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfis dst
USING (SELECT 'OPERADOR_PROD' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Operador de Ambientes de Producao',
             dst.is_admin = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.is_admin <> 'N'
     OR dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Operador de Ambientes de Producao'
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, is_admin, perm_versao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfis.NEXTVAL, 'OPERADOR_PROD', 'Operador de Ambientes de Producao', 'N', 1, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'OPERADOR_PROD' AND f.codigo = 'EXEC_SCRIPT'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'OPERADOR_PROD' AND f.codigo = 'VER_LOGS'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'OPERADOR_PROD' AND f.codigo = 'CANC_TICKET'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'OPERADOR_PROD' AND a.nome = 'CLONE2'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'OPERADOR_PROD' AND a.nome = 'CLONE1'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'OPERADOR_PROD' AND a.nome = 'CLONE6'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'OPERADOR_PROD' AND a.nome = 'CLONE7'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'OPERADOR_PROD' AND a.nome = 'GFPREPROD'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfis dst
USING (SELECT 'OPERADOR_HML' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Operador de Ambientes de Homologacao',
             dst.is_admin = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.is_admin <> 'N'
     OR dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Operador de Ambientes de Homologacao'
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, is_admin, perm_versao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfis.NEXTVAL, 'OPERADOR_HML', 'Operador de Ambientes de Homologacao', 'N', 1, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'OPERADOR_HML' AND f.codigo = 'EXEC_SCRIPT'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'OPERADOR_HML' AND f.codigo = 'VER_LOGS'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'OPERADOR_HML' AND f.codigo = 'CANC_TICKET'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'OPERADOR_HML' AND a.nome = 'CLONE6'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'OPERADOR_HML' AND a.nome = 'CLONE7'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'OPERADOR_HML' AND a.nome = 'GFPREPROD'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfis dst
USING (SELECT 'CONSULTA' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Perfil de Apenas Leitura e Consulta',
             dst.is_admin = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.is_admin <> 'N'
     OR dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Perfil de Apenas Leitura e Consulta'
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, is_admin, perm_versao, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfis.NEXTVAL, 'CONSULTA', 'Perfil de Apenas Leitura e Consulta', 'N', 1, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_func dst
USING (
  SELECT p.id AS perfil_id, f.id AS funcionalidade_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_funcionalidades f
   WHERE p.nome = 'CONSULTA' AND f.codigo = 'VER_LOGS'
) src
ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_func.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'CONSULTA' AND a.nome = 'CLONE2'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'CONSULTA' AND a.nome = 'CLONE1'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'CONSULTA' AND a.nome = 'CLONE6'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'CONSULTA' AND a.nome = 'CLONE7'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_amb dst
USING (
  SELECT p.id AS perfil_id, a.id AS ambiente_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_ambientes a
   WHERE p.nome = 'CONSULTA' AND a.nome = 'GFPREPROD'
) src
ON (dst.perfil_id = src.perfil_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_amb.NEXTVAL, src.perfil_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'arq_origem' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--origem',
             dst.label = 'Arquivo ou Pasta de Origem',
             dst.descricao = 'Caminho do arquivo ou pasta a ser processado',
             dst.tipo_componente = 'TEXT',
             dst.opcoes_json = NULL,
             dst.valor_padrao = NULL,
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--origem', '~')
     OR dst.label <> 'Arquivo ou Pasta de Origem'
     OR NVL(dst.descricao, '~') <> 'Caminho do arquivo ou pasta a ser processado'
     OR dst.tipo_componente <> 'TEXT'
     OR NVL(dst.opcoes_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.valor_padrao, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'arq_origem', '--origem', 'Arquivo ou Pasta de Origem', 'Caminho do arquivo ou pasta a ser processado', 'TEXT', NULL, NULL, NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'arq_destino' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--destino',
             dst.label = 'Arquivo ou Pasta de Destino',
             dst.descricao = 'Caminho do arquivo de saida ou diretorio destino',
             dst.tipo_componente = 'TEXT',
             dst.opcoes_json = NULL,
             dst.valor_padrao = NULL,
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--destino', '~')
     OR dst.label <> 'Arquivo ou Pasta de Destino'
     OR NVL(dst.descricao, '~') <> 'Caminho do arquivo de saida ou diretorio destino'
     OR dst.tipo_componente <> 'TEXT'
     OR NVL(dst.opcoes_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.valor_padrao, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'arq_destino', '--destino', 'Arquivo ou Pasta de Destino', 'Caminho do arquivo de saida ou diretorio destino', 'TEXT', NULL, NULL, NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'arq_zip' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--arquivo-zip',
             dst.label = 'Arquivo ZIP',
             dst.descricao = 'Caminho do pacote compactado .zip',
             dst.tipo_componente = 'TEXT',
             dst.opcoes_json = NULL,
             dst.valor_padrao = NULL,
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--arquivo-zip', '~')
     OR dst.label <> 'Arquivo ZIP'
     OR NVL(dst.descricao, '~') <> 'Caminho do pacote compactado .zip'
     OR dst.tipo_componente <> 'TEXT'
     OR NVL(dst.opcoes_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.valor_padrao, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'arq_zip', '--arquivo-zip', 'Arquivo ZIP', 'Caminho do pacote compactado .zip', 'TEXT', NULL, NULL, NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'arq_tar' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--arquivo-tar',
             dst.label = 'Arquivo TAR.GZ',
             dst.descricao = 'Caminho do pacote compactado .tar.gz',
             dst.tipo_componente = 'TEXT',
             dst.opcoes_json = NULL,
             dst.valor_padrao = NULL,
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--arquivo-tar', '~')
     OR dst.label <> 'Arquivo TAR.GZ'
     OR NVL(dst.descricao, '~') <> 'Caminho do pacote compactado .tar.gz'
     OR dst.tipo_componente <> 'TEXT'
     OR NVL(dst.opcoes_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.valor_padrao, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'arq_tar', '--arquivo-tar', 'Arquivo TAR.GZ', 'Caminho do pacote compactado .tar.gz', 'TEXT', NULL, NULL, NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'nivel_compressao' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--nivel',
             dst.label = 'Nivel de Compressao (1-9)',
             dst.descricao = 'Nivel de compactacao zlib de 1 (rapido) a 9 (maximo)',
             dst.tipo_componente = 'NUMBER',
             dst.opcoes_json = NULL,
             dst.valor_padrao = '6',
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--nivel', '~')
     OR dst.label <> 'Nivel de Compressao (1-9)'
     OR NVL(dst.descricao, '~') <> 'Nivel de compactacao zlib de 1 (rapido) a 9 (maximo)'
     OR dst.tipo_componente <> 'NUMBER'
     OR NVL(dst.opcoes_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.valor_padrao, '~') <> NVL('6', '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'nivel_compressao', '--nivel', 'Nivel de Compressao (1-9)', 'Nivel de compactacao zlib de 1 (rapido) a 9 (maximo)', 'NUMBER', NULL, '6', NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'linhas_por_parte' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--linhas-por-parte',
             dst.label = 'Linhas por Parte',
             dst.descricao = 'Quantidade maxima de linhas em cada parte dividida',
             dst.tipo_componente = 'NUMBER',
             dst.opcoes_json = NULL,
             dst.valor_padrao = '1000',
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--linhas-por-parte', '~')
     OR dst.label <> 'Linhas por Parte'
     OR NVL(dst.descricao, '~') <> 'Quantidade maxima de linhas em cada parte dividida'
     OR dst.tipo_componente <> 'NUMBER'
     OR NVL(dst.opcoes_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.valor_padrao, '~') <> NVL('1000', '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'linhas_por_parte', '--linhas-por-parte', 'Linhas por Parte', 'Quantidade maxima de linhas em cada parte dividida', 'NUMBER', NULL, '1000', NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'prefixo_saida' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--prefixo-saida',
             dst.label = 'Prefixo dos Arquivos Gerados',
             dst.descricao = 'Prefixo do caminho das partes geradas',
             dst.tipo_componente = 'TEXT',
             dst.opcoes_json = NULL,
             dst.valor_padrao = '/tmp/parte_',
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--prefixo-saida', '~')
     OR dst.label <> 'Prefixo dos Arquivos Gerados'
     OR NVL(dst.descricao, '~') <> 'Prefixo do caminho das partes geradas'
     OR dst.tipo_componente <> 'TEXT'
     OR NVL(dst.opcoes_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.valor_padrao, '~') <> NVL('/tmp/parte_', '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'prefixo_saida', '--prefixo-saida', 'Prefixo dos Arquivos Gerados', 'Prefixo do caminho das partes geradas', 'TEXT', NULL, '/tmp/parte_', NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'padrao_origem' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--padrao-origem',
             dst.label = 'Padrao de Origem (Glob)',
             dst.descricao = 'Mascara glob dos arquivos a serem juntados (ex: /tmp/parte_*)',
             dst.tipo_componente = 'TEXT',
             dst.opcoes_json = NULL,
             dst.valor_padrao = '/tmp/parte_*',
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--padrao-origem', '~')
     OR dst.label <> 'Padrao de Origem (Glob)'
     OR NVL(dst.descricao, '~') <> 'Mascara glob dos arquivos a serem juntados (ex: /tmp/parte_*)'
     OR dst.tipo_componente <> 'TEXT'
     OR NVL(dst.opcoes_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.valor_padrao, '~') <> NVL('/tmp/parte_*', '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'padrao_origem', '--padrao-origem', 'Padrao de Origem (Glob)', 'Mascara glob dos arquivos a serem juntados (ex: /tmp/parte_*)', 'TEXT', NULL, '/tmp/parte_*', NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'enc_origem' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--enc-origem',
             dst.label = 'Codificacao de Origem',
             dst.descricao = 'Codificacao de caracteres atual do arquivo',
             dst.tipo_componente = 'SELECT',
             dst.opcoes_json = '{"ISO-8859-1":"ISO-8859-1 (Latin1)","UTF-8":"UTF-8","CP1252":"Windows CP1252","ASCII":"ASCII"}',
             dst.valor_padrao = 'ISO-8859-1',
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--enc-origem', '~')
     OR dst.label <> 'Codificacao de Origem'
     OR NVL(dst.descricao, '~') <> 'Codificacao de caracteres atual do arquivo'
     OR dst.tipo_componente <> 'SELECT'
     OR NVL(dst.opcoes_json, '~') <> NVL('{"ISO-8859-1":"ISO-8859-1 (Latin1)","UTF-8":"UTF-8","CP1252":"Windows CP1252","ASCII":"ASCII"}', '~')
     OR NVL(dst.valor_padrao, '~') <> NVL('ISO-8859-1', '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'enc_origem', '--enc-origem', 'Codificacao de Origem', 'Codificacao de caracteres atual do arquivo', 'SELECT', '{"ISO-8859-1":"ISO-8859-1 (Latin1)","UTF-8":"UTF-8","CP1252":"Windows CP1252","ASCII":"ASCII"}', 'ISO-8859-1', NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'enc_destino' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--enc-destino',
             dst.label = 'Codificacao de Destino',
             dst.descricao = 'Nova codificacao de caracteres desejada',
             dst.tipo_componente = 'SELECT',
             dst.opcoes_json = '{"UTF-8":"UTF-8","ISO-8859-1":"ISO-8859-1 (Latin1)","CP1252":"Windows CP1252"}',
             dst.valor_padrao = 'UTF-8',
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--enc-destino', '~')
     OR dst.label <> 'Codificacao de Destino'
     OR NVL(dst.descricao, '~') <> 'Nova codificacao de caracteres desejada'
     OR dst.tipo_componente <> 'SELECT'
     OR NVL(dst.opcoes_json, '~') <> NVL('{"UTF-8":"UTF-8","ISO-8859-1":"ISO-8859-1 (Latin1)","CP1252":"Windows CP1252"}', '~')
     OR NVL(dst.valor_padrao, '~') <> NVL('UTF-8', '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'enc_destino', '--enc-destino', 'Codificacao de Destino', 'Nova codificacao de caracteres desejada', 'SELECT', '{"UTF-8":"UTF-8","ISO-8859-1":"ISO-8859-1 (Latin1)","CP1252":"Windows CP1252"}', 'UTF-8', NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'termo_busca' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--busca',
             dst.label = 'Texto a Localizar',
             dst.descricao = 'String ou termo a ser pesquisado nas linhas',
             dst.tipo_componente = 'TEXT',
             dst.opcoes_json = NULL,
             dst.valor_padrao = NULL,
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--busca', '~')
     OR dst.label <> 'Texto a Localizar'
     OR NVL(dst.descricao, '~') <> 'String ou termo a ser pesquisado nas linhas'
     OR dst.tipo_componente <> 'TEXT'
     OR NVL(dst.opcoes_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.valor_padrao, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'termo_busca', '--busca', 'Texto a Localizar', 'String ou termo a ser pesquisado nas linhas', 'TEXT', NULL, NULL, NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'termo_substituicao' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--substituicao',
             dst.label = 'Texto Substituto',
             dst.descricao = 'Nova string que substituira o texto localizado',
             dst.tipo_componente = 'TEXT',
             dst.opcoes_json = NULL,
             dst.valor_padrao = NULL,
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--substituicao', '~')
     OR dst.label <> 'Texto Substituto'
     OR NVL(dst.descricao, '~') <> 'Nova string que substituira o texto localizado'
     OR dst.tipo_componente <> 'TEXT'
     OR NVL(dst.opcoes_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.valor_padrao, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'termo_substituicao', '--substituicao', 'Texto Substituto', 'Nova string que substituira o texto localizado', 'TEXT', NULL, NULL, NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'flag_ordenar' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--ordenar',
             dst.label = 'Ordenar Resultado',
             dst.descricao = 'Indica se deve ordenar alfabeticamente ou manter ordem',
             dst.tipo_componente = 'SELECT',
             dst.opcoes_json = '{"S":"Sim (Ordenar)","N":"Nao (Preservar ordem)"}',
             dst.valor_padrao = 'S',
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--ordenar', '~')
     OR dst.label <> 'Ordenar Resultado'
     OR NVL(dst.descricao, '~') <> 'Indica se deve ordenar alfabeticamente ou manter ordem'
     OR dst.tipo_componente <> 'SELECT'
     OR NVL(dst.opcoes_json, '~') <> NVL('{"S":"Sim (Ordenar)","N":"Nao (Preservar ordem)"}', '~')
     OR NVL(dst.valor_padrao, '~') <> NVL('S', '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'flag_ordenar', '--ordenar', 'Ordenar Resultado', 'Indica se deve ordenar alfabeticamente ou manter ordem', 'SELECT', '{"S":"Sim (Ordenar)","N":"Nao (Preservar ordem)"}', 'S', NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'tipo_hash' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--algoritmo',
             dst.label = 'Algoritmo de Hash',
             dst.descricao = 'Algoritmo criptografico de integridade',
             dst.tipo_componente = 'SELECT',
             dst.opcoes_json = '{"sha256":"SHA-256 (Recomendado)","md5":"MD5","sha1":"SHA-1"}',
             dst.valor_padrao = 'sha256',
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--algoritmo', '~')
     OR dst.label <> 'Algoritmo de Hash'
     OR NVL(dst.descricao, '~') <> 'Algoritmo criptografico de integridade'
     OR dst.tipo_componente <> 'SELECT'
     OR NVL(dst.opcoes_json, '~') <> NVL('{"sha256":"SHA-256 (Recomendado)","md5":"MD5","sha1":"SHA-1"}', '~')
     OR NVL(dst.valor_padrao, '~') <> NVL('sha256', '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'tipo_hash', '--algoritmo', 'Algoritmo de Hash', 'Algoritmo criptografico de integridade', 'SELECT', '{"sha256":"SHA-256 (Recomendado)","md5":"MD5","sha1":"SHA-1"}', 'sha256', NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'termo_filtro' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--padrao',
             dst.label = 'Padrao de Filtragem',
             dst.descricao = 'Texto a ser filtrado nas linhas do arquivo',
             dst.tipo_componente = 'TEXT',
             dst.opcoes_json = NULL,
             dst.valor_padrao = NULL,
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--padrao', '~')
     OR dst.label <> 'Padrao de Filtragem'
     OR NVL(dst.descricao, '~') <> 'Texto a ser filtrado nas linhas do arquivo'
     OR dst.tipo_componente <> 'TEXT'
     OR NVL(dst.opcoes_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.valor_padrao, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'termo_filtro', '--padrao', 'Padrao de Filtragem', 'Texto a ser filtrado nas linhas do arquivo', 'TEXT', NULL, NULL, NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'flag_inverter' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--inverter',
             dst.label = 'Inverter Selecao',
             dst.descricao = 'Se ativado, seleciona as linhas que nao possuem o padrao',
             dst.tipo_componente = 'SELECT',
             dst.opcoes_json = '{"N":"Nao (Manter correspondencias)","S":"Sim (Excluir correspondencias)"}',
             dst.valor_padrao = 'N',
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--inverter', '~')
     OR dst.label <> 'Inverter Selecao'
     OR NVL(dst.descricao, '~') <> 'Se ativado, seleciona as linhas que nao possuem o padrao'
     OR dst.tipo_componente <> 'SELECT'
     OR NVL(dst.opcoes_json, '~') <> NVL('{"N":"Nao (Manter correspondencias)","S":"Sim (Excluir correspondencias)"}', '~')
     OR NVL(dst.valor_padrao, '~') <> NVL('N', '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'flag_inverter', '--inverter', 'Inverter Selecao', 'Se ativado, seleciona as linhas que nao possuem o padrao', 'SELECT', '{"N":"Nao (Manter correspondencias)","S":"Sim (Excluir correspondencias)"}', 'N', NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'flag_numerico' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--numerico',
             dst.label = 'Ordenacao Numerica',
             dst.descricao = 'Trata o inicio das linhas como valor numerico',
             dst.tipo_componente = 'SELECT',
             dst.opcoes_json = '{"N":"Nao (Alfanumerica)","S":"Sim (Numerica)"}',
             dst.valor_padrao = 'N',
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--numerico', '~')
     OR dst.label <> 'Ordenacao Numerica'
     OR NVL(dst.descricao, '~') <> 'Trata o inicio das linhas como valor numerico'
     OR dst.tipo_componente <> 'SELECT'
     OR NVL(dst.opcoes_json, '~') <> NVL('{"N":"Nao (Alfanumerica)","S":"Sim (Numerica)"}', '~')
     OR NVL(dst.valor_padrao, '~') <> NVL('N', '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'flag_numerico', '--numerico', 'Ordenacao Numerica', 'Trata o inicio das linhas como valor numerico', 'SELECT', '{"N":"Nao (Alfanumerica)","S":"Sim (Numerica)"}', 'N', NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'flag_reverso' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = '--reverso',
             dst.label = 'Ordem Reversa (Decrescente)',
             dst.descricao = 'Ordena de tras para frente',
             dst.tipo_componente = 'SELECT',
             dst.opcoes_json = '{"N":"Nao (Crescente)","S":"Sim (Decrescente)"}',
             dst.valor_padrao = 'N',
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL('--reverso', '~')
     OR dst.label <> 'Ordem Reversa (Decrescente)'
     OR NVL(dst.descricao, '~') <> 'Ordena de tras para frente'
     OR dst.tipo_componente <> 'SELECT'
     OR NVL(dst.opcoes_json, '~') <> NVL('{"N":"Nao (Crescente)","S":"Sim (Decrescente)"}', '~')
     OR NVL(dst.valor_padrao, '~') <> NVL('N', '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'flag_reverso', '--reverso', 'Ordem Reversa (Decrescente)', 'Ordena de tras para frente', 'SELECT', '{"N":"Nao (Crescente)","S":"Sim (Decrescente)"}', 'N', NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parametros dst
USING (SELECT 'caminho_arquivo' AS codigo FROM DUAL) src
ON (dst.codigo = src.codigo)
WHEN MATCHED THEN
  UPDATE SET dst.param_nomeado = NULL,
             dst.label = 'Caminho do Arquivo',
             dst.descricao = 'Caminho do arquivo a ser analisado',
             dst.tipo_componente = 'TEXT',
             dst.opcoes_json = NULL,
             dst.valor_padrao = NULL,
             dst.sensivel = 'N',
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.param_nomeado, '~') <> NVL(NULL, '~')
     OR dst.label <> 'Caminho do Arquivo'
     OR NVL(dst.descricao, '~') <> 'Caminho do arquivo a ser analisado'
     OR dst.tipo_componente <> 'TEXT'
     OR NVL(dst.opcoes_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.valor_padrao, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parametros.NEXTVAL, 'caminho_arquivo', NULL, 'Caminho do Arquivo', 'Caminho do arquivo a ser analisado', 'TEXT', NULL, NULL, NULL, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'zipar_arquivos' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Compacta arquivo ou pasta em formato ZIP',
             dst.grupo = 'UTILITARIOS',
             dst.categoria = 'ARQUIVOS',
             dst.etapa = 'COMPACTACAO',
             dst.interpretador = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/zipar_arquivos.py',
             dst.tipo_param = 'NOMEADO',
             dst.max_qtd_parallel_env = 2,
             dst.timeout_seg = 1800,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Compacta arquivo ou pasta em formato ZIP'
     OR NVL(dst.grupo, '~') <> 'UTILITARIOS'
     OR NVL(dst.categoria, '~') <> 'ARQUIVOS'
     OR NVL(dst.etapa, '~') <> 'COMPACTACAO'
     OR dst.interpretador <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/zipar_arquivos.py'
     OR dst.tipo_param <> 'NOMEADO'
     OR dst.max_qtd_parallel_env <> 2
     OR NVL(dst.timeout_seg, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'zipar_arquivos', 'Compacta arquivo ou pasta em formato ZIP', 'UTILITARIOS', 'ARQUIVOS', 'COMPACTACAO', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/zipar_arquivos.py', 'NOMEADO', 2, 1800, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'zipar_arquivos' AND a.nome = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'zipar_arquivos' AND a.nome = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'zipar_arquivos' AND a.nome = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'zipar_arquivos' AND a.nome = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'zipar_arquivos' AND a.nome = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'ADMINISTRADOR' AND s.nome = 'zipar_arquivos'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_PROD' AND s.nome = 'zipar_arquivos'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_HML' AND s.nome = 'zipar_arquivos'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'CONSULTA' AND s.nome = 'zipar_arquivos'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'zipar_arquivos' AND p.codigo = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 1,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 1
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 1, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'zipar_arquivos' AND p.codigo = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 2,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 2
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 2, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'zipar_arquivos' AND p.codigo = 'nivel_compressao'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 3,
             dst.obrigatorio = 'N',
             dst.valor_padrao_sub = '6',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 3
     OR dst.obrigatorio <> 'N'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL('6', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 3, 'N', '6', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'descompactar_zip' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Extrai arquivos de pacote ZIP para pasta destino com protecao segura',
             dst.grupo = 'UTILITARIOS',
             dst.categoria = 'ARQUIVOS',
             dst.etapa = 'DESCOMPACTACAO',
             dst.interpretador = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/descompactar_zip.py',
             dst.tipo_param = 'NOMEADO',
             dst.max_qtd_parallel_env = 2,
             dst.timeout_seg = 1800,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Extrai arquivos de pacote ZIP para pasta destino com protecao segura'
     OR NVL(dst.grupo, '~') <> 'UTILITARIOS'
     OR NVL(dst.categoria, '~') <> 'ARQUIVOS'
     OR NVL(dst.etapa, '~') <> 'DESCOMPACTACAO'
     OR dst.interpretador <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/descompactar_zip.py'
     OR dst.tipo_param <> 'NOMEADO'
     OR dst.max_qtd_parallel_env <> 2
     OR NVL(dst.timeout_seg, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'descompactar_zip', 'Extrai arquivos de pacote ZIP para pasta destino com protecao segura', 'UTILITARIOS', 'ARQUIVOS', 'DESCOMPACTACAO', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/descompactar_zip.py', 'NOMEADO', 2, 1800, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'descompactar_zip' AND a.nome = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'descompactar_zip' AND a.nome = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'descompactar_zip' AND a.nome = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'descompactar_zip' AND a.nome = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'descompactar_zip' AND a.nome = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'ADMINISTRADOR' AND s.nome = 'descompactar_zip'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_PROD' AND s.nome = 'descompactar_zip'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_HML' AND s.nome = 'descompactar_zip'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'CONSULTA' AND s.nome = 'descompactar_zip'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'descompactar_zip' AND p.codigo = 'arq_zip'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 1,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 1
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 1, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'descompactar_zip' AND p.codigo = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 2,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 2
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 2, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'quebrar_arquivo' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Divide arquivo texto em partes menores por quantidade de linhas',
             dst.grupo = 'UTILITARIOS',
             dst.categoria = 'ARQUIVOS',
             dst.etapa = 'DIVISAO',
             dst.interpretador = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/quebrar_arquivo.py',
             dst.tipo_param = 'NOMEADO',
             dst.max_qtd_parallel_env = 2,
             dst.timeout_seg = 1800,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Divide arquivo texto em partes menores por quantidade de linhas'
     OR NVL(dst.grupo, '~') <> 'UTILITARIOS'
     OR NVL(dst.categoria, '~') <> 'ARQUIVOS'
     OR NVL(dst.etapa, '~') <> 'DIVISAO'
     OR dst.interpretador <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/quebrar_arquivo.py'
     OR dst.tipo_param <> 'NOMEADO'
     OR dst.max_qtd_parallel_env <> 2
     OR NVL(dst.timeout_seg, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'quebrar_arquivo', 'Divide arquivo texto em partes menores por quantidade de linhas', 'UTILITARIOS', 'ARQUIVOS', 'DIVISAO', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/quebrar_arquivo.py', 'NOMEADO', 2, 1800, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'quebrar_arquivo' AND a.nome = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'quebrar_arquivo' AND a.nome = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'quebrar_arquivo' AND a.nome = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'quebrar_arquivo' AND a.nome = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'quebrar_arquivo' AND a.nome = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'ADMINISTRADOR' AND s.nome = 'quebrar_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_PROD' AND s.nome = 'quebrar_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_HML' AND s.nome = 'quebrar_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'CONSULTA' AND s.nome = 'quebrar_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'quebrar_arquivo' AND p.codigo = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 1,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 1
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 1, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'quebrar_arquivo' AND p.codigo = 'linhas_por_parte'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 2,
             dst.obrigatorio = 'N',
             dst.valor_padrao_sub = '1000',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 2
     OR dst.obrigatorio <> 'N'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL('1000', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 2, 'N', '1000', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'quebrar_arquivo' AND p.codigo = 'prefixo_saida'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 3,
             dst.obrigatorio = 'N',
             dst.valor_padrao_sub = '/tmp/parte_',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 3
     OR dst.obrigatorio <> 'N'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL('/tmp/parte_', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 3, 'N', '/tmp/parte_', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'juntar_arquivos' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Concatena blocos de arquivos ordenados em arquivo consolidado final',
             dst.grupo = 'UTILITARIOS',
             dst.categoria = 'ARQUIVOS',
             dst.etapa = 'CONCATENACAO',
             dst.interpretador = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/juntar_arquivos.py',
             dst.tipo_param = 'NOMEADO',
             dst.max_qtd_parallel_env = 2,
             dst.timeout_seg = 1800,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Concatena blocos de arquivos ordenados em arquivo consolidado final'
     OR NVL(dst.grupo, '~') <> 'UTILITARIOS'
     OR NVL(dst.categoria, '~') <> 'ARQUIVOS'
     OR NVL(dst.etapa, '~') <> 'CONCATENACAO'
     OR dst.interpretador <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/juntar_arquivos.py'
     OR dst.tipo_param <> 'NOMEADO'
     OR dst.max_qtd_parallel_env <> 2
     OR NVL(dst.timeout_seg, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'juntar_arquivos', 'Concatena blocos de arquivos ordenados em arquivo consolidado final', 'UTILITARIOS', 'ARQUIVOS', 'CONCATENACAO', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/juntar_arquivos.py', 'NOMEADO', 2, 1800, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'juntar_arquivos' AND a.nome = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'juntar_arquivos' AND a.nome = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'juntar_arquivos' AND a.nome = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'juntar_arquivos' AND a.nome = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'juntar_arquivos' AND a.nome = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'ADMINISTRADOR' AND s.nome = 'juntar_arquivos'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_PROD' AND s.nome = 'juntar_arquivos'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_HML' AND s.nome = 'juntar_arquivos'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'CONSULTA' AND s.nome = 'juntar_arquivos'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'juntar_arquivos' AND p.codigo = 'padrao_origem'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 1,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = '/tmp/parte_*',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 1
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL('/tmp/parte_*', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 1, 'S', '/tmp/parte_*', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'juntar_arquivos' AND p.codigo = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 2,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 2
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 2, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'converter_encoding' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Converte codificacao de caracteres de arquivo texto (ex: ISO-8859-1 para UTF-8)',
             dst.grupo = 'UTILITARIOS',
             dst.categoria = 'ARQUIVOS',
             dst.etapa = 'CONVERSAO',
             dst.interpretador = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/converter_encoding.py',
             dst.tipo_param = 'NOMEADO',
             dst.max_qtd_parallel_env = 2,
             dst.timeout_seg = 1800,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Converte codificacao de caracteres de arquivo texto (ex: ISO-8859-1 para UTF-8)'
     OR NVL(dst.grupo, '~') <> 'UTILITARIOS'
     OR NVL(dst.categoria, '~') <> 'ARQUIVOS'
     OR NVL(dst.etapa, '~') <> 'CONVERSAO'
     OR dst.interpretador <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/converter_encoding.py'
     OR dst.tipo_param <> 'NOMEADO'
     OR dst.max_qtd_parallel_env <> 2
     OR NVL(dst.timeout_seg, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'converter_encoding', 'Converte codificacao de caracteres de arquivo texto (ex: ISO-8859-1 para UTF-8)', 'UTILITARIOS', 'ARQUIVOS', 'CONVERSAO', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/converter_encoding.py', 'NOMEADO', 2, 1800, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'converter_encoding' AND a.nome = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'converter_encoding' AND a.nome = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'converter_encoding' AND a.nome = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'converter_encoding' AND a.nome = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'converter_encoding' AND a.nome = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'ADMINISTRADOR' AND s.nome = 'converter_encoding'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_PROD' AND s.nome = 'converter_encoding'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_HML' AND s.nome = 'converter_encoding'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'CONSULTA' AND s.nome = 'converter_encoding'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'converter_encoding' AND p.codigo = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 1,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 1
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 1, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'converter_encoding' AND p.codigo = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 2,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 2
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 2, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'converter_encoding' AND p.codigo = 'enc_origem'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 3,
             dst.obrigatorio = 'N',
             dst.valor_padrao_sub = 'ISO-8859-1',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 3
     OR dst.obrigatorio <> 'N'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL('ISO-8859-1', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 3, 'N', 'ISO-8859-1', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'converter_encoding' AND p.codigo = 'enc_destino'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 4,
             dst.obrigatorio = 'N',
             dst.valor_padrao_sub = 'UTF-8',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 4
     OR dst.obrigatorio <> 'N'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL('UTF-8', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 4, 'N', 'UTF-8', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'substituir_texto' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Localiza e substitui texto em arquivo gerando copia atualizada',
             dst.grupo = 'UTILITARIOS',
             dst.categoria = 'ARQUIVOS',
             dst.etapa = 'TRANSFORMACAO',
             dst.interpretador = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/substituir_texto.py',
             dst.tipo_param = 'NOMEADO',
             dst.max_qtd_parallel_env = 2,
             dst.timeout_seg = 1800,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Localiza e substitui texto em arquivo gerando copia atualizada'
     OR NVL(dst.grupo, '~') <> 'UTILITARIOS'
     OR NVL(dst.categoria, '~') <> 'ARQUIVOS'
     OR NVL(dst.etapa, '~') <> 'TRANSFORMACAO'
     OR dst.interpretador <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/substituir_texto.py'
     OR dst.tipo_param <> 'NOMEADO'
     OR dst.max_qtd_parallel_env <> 2
     OR NVL(dst.timeout_seg, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'substituir_texto', 'Localiza e substitui texto em arquivo gerando copia atualizada', 'UTILITARIOS', 'ARQUIVOS', 'TRANSFORMACAO', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/substituir_texto.py', 'NOMEADO', 2, 1800, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'substituir_texto' AND a.nome = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'substituir_texto' AND a.nome = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'substituir_texto' AND a.nome = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'substituir_texto' AND a.nome = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'substituir_texto' AND a.nome = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'ADMINISTRADOR' AND s.nome = 'substituir_texto'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_PROD' AND s.nome = 'substituir_texto'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_HML' AND s.nome = 'substituir_texto'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'CONSULTA' AND s.nome = 'substituir_texto'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'substituir_texto' AND p.codigo = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 1,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 1
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 1, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'substituir_texto' AND p.codigo = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 2,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 2
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 2, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'substituir_texto' AND p.codigo = 'termo_busca'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 3,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 3
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 3, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'substituir_texto' AND p.codigo = 'termo_substituicao'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 4,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 4
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 4, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'remover_duplicadas' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Remove linhas duplicadas de arquivo texto preservando ordem ou ordenando',
             dst.grupo = 'UTILITARIOS',
             dst.categoria = 'ARQUIVOS',
             dst.etapa = 'HIGIENIZACAO',
             dst.interpretador = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/remover_duplicadas.py',
             dst.tipo_param = 'NOMEADO',
             dst.max_qtd_parallel_env = 2,
             dst.timeout_seg = 1800,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Remove linhas duplicadas de arquivo texto preservando ordem ou ordenando'
     OR NVL(dst.grupo, '~') <> 'UTILITARIOS'
     OR NVL(dst.categoria, '~') <> 'ARQUIVOS'
     OR NVL(dst.etapa, '~') <> 'HIGIENIZACAO'
     OR dst.interpretador <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/remover_duplicadas.py'
     OR dst.tipo_param <> 'NOMEADO'
     OR dst.max_qtd_parallel_env <> 2
     OR NVL(dst.timeout_seg, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'remover_duplicadas', 'Remove linhas duplicadas de arquivo texto preservando ordem ou ordenando', 'UTILITARIOS', 'ARQUIVOS', 'HIGIENIZACAO', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/remover_duplicadas.py', 'NOMEADO', 2, 1800, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'remover_duplicadas' AND a.nome = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'remover_duplicadas' AND a.nome = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'remover_duplicadas' AND a.nome = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'remover_duplicadas' AND a.nome = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'remover_duplicadas' AND a.nome = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'ADMINISTRADOR' AND s.nome = 'remover_duplicadas'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_PROD' AND s.nome = 'remover_duplicadas'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_HML' AND s.nome = 'remover_duplicadas'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'CONSULTA' AND s.nome = 'remover_duplicadas'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'remover_duplicadas' AND p.codigo = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 1,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 1
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 1, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'remover_duplicadas' AND p.codigo = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 2,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 2
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 2, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'remover_duplicadas' AND p.codigo = 'flag_ordenar'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 3,
             dst.obrigatorio = 'N',
             dst.valor_padrao_sub = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 3
     OR dst.obrigatorio <> 'N'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL('S', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 3, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'gerar_hash_arquivo' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Calcula hash criptografico (SHA256, MD5, SHA1) para conferencia de integridade',
             dst.grupo = 'UTILITARIOS',
             dst.categoria = 'ARQUIVOS',
             dst.etapa = 'AUDITORIA',
             dst.interpretador = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/gerar_hash_arquivo.py',
             dst.tipo_param = 'NOMEADO',
             dst.max_qtd_parallel_env = 2,
             dst.timeout_seg = 1800,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Calcula hash criptografico (SHA256, MD5, SHA1) para conferencia de integridade'
     OR NVL(dst.grupo, '~') <> 'UTILITARIOS'
     OR NVL(dst.categoria, '~') <> 'ARQUIVOS'
     OR NVL(dst.etapa, '~') <> 'AUDITORIA'
     OR dst.interpretador <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/gerar_hash_arquivo.py'
     OR dst.tipo_param <> 'NOMEADO'
     OR dst.max_qtd_parallel_env <> 2
     OR NVL(dst.timeout_seg, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'gerar_hash_arquivo', 'Calcula hash criptografico (SHA256, MD5, SHA1) para conferencia de integridade', 'UTILITARIOS', 'ARQUIVOS', 'AUDITORIA', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/gerar_hash_arquivo.py', 'NOMEADO', 2, 1800, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'gerar_hash_arquivo' AND a.nome = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'gerar_hash_arquivo' AND a.nome = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'gerar_hash_arquivo' AND a.nome = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'gerar_hash_arquivo' AND a.nome = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'gerar_hash_arquivo' AND a.nome = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'ADMINISTRADOR' AND s.nome = 'gerar_hash_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_PROD' AND s.nome = 'gerar_hash_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_HML' AND s.nome = 'gerar_hash_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'CONSULTA' AND s.nome = 'gerar_hash_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'gerar_hash_arquivo' AND p.codigo = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 1,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 1
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 1, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'gerar_hash_arquivo' AND p.codigo = 'tipo_hash'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 2,
             dst.obrigatorio = 'N',
             dst.valor_padrao_sub = 'sha256',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 2
     OR dst.obrigatorio <> 'N'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL('sha256', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 2, 'N', 'sha256', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'compactar_targz' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Cria pacote compactado .tar.gz a partir de arquivo ou pasta',
             dst.grupo = 'UTILITARIOS',
             dst.categoria = 'ARQUIVOS',
             dst.etapa = 'COMPACTACAO',
             dst.interpretador = 'BASH',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/compactar_targz.sh',
             dst.tipo_param = 'NOMEADO',
             dst.max_qtd_parallel_env = 2,
             dst.timeout_seg = 1800,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Cria pacote compactado .tar.gz a partir de arquivo ou pasta'
     OR NVL(dst.grupo, '~') <> 'UTILITARIOS'
     OR NVL(dst.categoria, '~') <> 'ARQUIVOS'
     OR NVL(dst.etapa, '~') <> 'COMPACTACAO'
     OR dst.interpretador <> 'BASH'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/compactar_targz.sh'
     OR dst.tipo_param <> 'NOMEADO'
     OR dst.max_qtd_parallel_env <> 2
     OR NVL(dst.timeout_seg, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'compactar_targz', 'Cria pacote compactado .tar.gz a partir de arquivo ou pasta', 'UTILITARIOS', 'ARQUIVOS', 'COMPACTACAO', 'BASH', '/opt/automacoes/scripts/utilitarios/compactar_targz.sh', 'NOMEADO', 2, 1800, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'compactar_targz' AND a.nome = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'compactar_targz' AND a.nome = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'compactar_targz' AND a.nome = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'compactar_targz' AND a.nome = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'compactar_targz' AND a.nome = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'ADMINISTRADOR' AND s.nome = 'compactar_targz'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_PROD' AND s.nome = 'compactar_targz'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_HML' AND s.nome = 'compactar_targz'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'CONSULTA' AND s.nome = 'compactar_targz'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'compactar_targz' AND p.codigo = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 1,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 1
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 1, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'compactar_targz' AND p.codigo = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 2,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 2
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 2, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'descompactar_targz' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Extrai pacote compactado .tar.gz para pasta destino com verificacao',
             dst.grupo = 'UTILITARIOS',
             dst.categoria = 'ARQUIVOS',
             dst.etapa = 'DESCOMPACTACAO',
             dst.interpretador = 'BASH',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/descompactar_targz.sh',
             dst.tipo_param = 'NOMEADO',
             dst.max_qtd_parallel_env = 2,
             dst.timeout_seg = 1800,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Extrai pacote compactado .tar.gz para pasta destino com verificacao'
     OR NVL(dst.grupo, '~') <> 'UTILITARIOS'
     OR NVL(dst.categoria, '~') <> 'ARQUIVOS'
     OR NVL(dst.etapa, '~') <> 'DESCOMPACTACAO'
     OR dst.interpretador <> 'BASH'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/descompactar_targz.sh'
     OR dst.tipo_param <> 'NOMEADO'
     OR dst.max_qtd_parallel_env <> 2
     OR NVL(dst.timeout_seg, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'descompactar_targz', 'Extrai pacote compactado .tar.gz para pasta destino com verificacao', 'UTILITARIOS', 'ARQUIVOS', 'DESCOMPACTACAO', 'BASH', '/opt/automacoes/scripts/utilitarios/descompactar_targz.sh', 'NOMEADO', 2, 1800, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'descompactar_targz' AND a.nome = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'descompactar_targz' AND a.nome = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'descompactar_targz' AND a.nome = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'descompactar_targz' AND a.nome = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'descompactar_targz' AND a.nome = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'ADMINISTRADOR' AND s.nome = 'descompactar_targz'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_PROD' AND s.nome = 'descompactar_targz'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_HML' AND s.nome = 'descompactar_targz'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'CONSULTA' AND s.nome = 'descompactar_targz'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'descompactar_targz' AND p.codigo = 'arq_tar'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 1,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 1
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 1, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'descompactar_targz' AND p.codigo = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 2,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 2
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 2, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'contar_linhas_arquivo' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Conta linhas, palavras e bytes de arquivo texto (modo posicional/sequencial)',
             dst.grupo = 'UTILITARIOS',
             dst.categoria = 'ARQUIVOS',
             dst.etapa = 'ANALISE',
             dst.interpretador = 'SH',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/contar_linhas_arquivo.sh',
             dst.tipo_param = 'SEQUENCIAL',
             dst.max_qtd_parallel_env = 2,
             dst.timeout_seg = 600,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Conta linhas, palavras e bytes de arquivo texto (modo posicional/sequencial)'
     OR NVL(dst.grupo, '~') <> 'UTILITARIOS'
     OR NVL(dst.categoria, '~') <> 'ARQUIVOS'
     OR NVL(dst.etapa, '~') <> 'ANALISE'
     OR dst.interpretador <> 'SH'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/contar_linhas_arquivo.sh'
     OR dst.tipo_param <> 'SEQUENCIAL'
     OR dst.max_qtd_parallel_env <> 2
     OR NVL(dst.timeout_seg, 0) <> 600
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'contar_linhas_arquivo', 'Conta linhas, palavras e bytes de arquivo texto (modo posicional/sequencial)', 'UTILITARIOS', 'ARQUIVOS', 'ANALISE', 'SH', '/opt/automacoes/scripts/utilitarios/contar_linhas_arquivo.sh', 'SEQUENCIAL', 2, 600, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'contar_linhas_arquivo' AND a.nome = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'contar_linhas_arquivo' AND a.nome = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'contar_linhas_arquivo' AND a.nome = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'contar_linhas_arquivo' AND a.nome = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'contar_linhas_arquivo' AND a.nome = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'ADMINISTRADOR' AND s.nome = 'contar_linhas_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_PROD' AND s.nome = 'contar_linhas_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_HML' AND s.nome = 'contar_linhas_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'CONSULTA' AND s.nome = 'contar_linhas_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'contar_linhas_arquivo' AND p.codigo = 'caminho_arquivo'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 1,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 1
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 1, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'filtrar_linhas' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Filtra linhas de arquivo baseado em padrao de texto com opcao de inverter',
             dst.grupo = 'UTILITARIOS',
             dst.categoria = 'ARQUIVOS',
             dst.etapa = 'FILTRAGEM',
             dst.interpretador = 'BASH',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/filtrar_linhas.sh',
             dst.tipo_param = 'NOMEADO',
             dst.max_qtd_parallel_env = 2,
             dst.timeout_seg = 1800,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Filtra linhas de arquivo baseado em padrao de texto com opcao de inverter'
     OR NVL(dst.grupo, '~') <> 'UTILITARIOS'
     OR NVL(dst.categoria, '~') <> 'ARQUIVOS'
     OR NVL(dst.etapa, '~') <> 'FILTRAGEM'
     OR dst.interpretador <> 'BASH'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/filtrar_linhas.sh'
     OR dst.tipo_param <> 'NOMEADO'
     OR dst.max_qtd_parallel_env <> 2
     OR NVL(dst.timeout_seg, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'filtrar_linhas', 'Filtra linhas de arquivo baseado em padrao de texto com opcao de inverter', 'UTILITARIOS', 'ARQUIVOS', 'FILTRAGEM', 'BASH', '/opt/automacoes/scripts/utilitarios/filtrar_linhas.sh', 'NOMEADO', 2, 1800, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'filtrar_linhas' AND a.nome = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'filtrar_linhas' AND a.nome = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'filtrar_linhas' AND a.nome = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'filtrar_linhas' AND a.nome = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'filtrar_linhas' AND a.nome = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'ADMINISTRADOR' AND s.nome = 'filtrar_linhas'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_PROD' AND s.nome = 'filtrar_linhas'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_HML' AND s.nome = 'filtrar_linhas'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'CONSULTA' AND s.nome = 'filtrar_linhas'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'filtrar_linhas' AND p.codigo = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 1,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 1
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 1, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'filtrar_linhas' AND p.codigo = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 2,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 2
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 2, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'filtrar_linhas' AND p.codigo = 'termo_filtro'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 3,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 3
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 3, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'filtrar_linhas' AND p.codigo = 'flag_inverter'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 4,
             dst.obrigatorio = 'N',
             dst.valor_padrao_sub = 'N',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 4
     OR dst.obrigatorio <> 'N'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL('N', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 4, 'N', 'N', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'ordenar_arquivo' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Ordena linhas de arquivo texto com opcoes numerica e reversa',
             dst.grupo = 'UTILITARIOS',
             dst.categoria = 'ARQUIVOS',
             dst.etapa = 'ORGANIZACAO',
             dst.interpretador = 'SH',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/ordenar_arquivo.sh',
             dst.tipo_param = 'NOMEADO',
             dst.max_qtd_parallel_env = 2,
             dst.timeout_seg = 1800,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Ordena linhas de arquivo texto com opcoes numerica e reversa'
     OR NVL(dst.grupo, '~') <> 'UTILITARIOS'
     OR NVL(dst.categoria, '~') <> 'ARQUIVOS'
     OR NVL(dst.etapa, '~') <> 'ORGANIZACAO'
     OR dst.interpretador <> 'SH'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/ordenar_arquivo.sh'
     OR dst.tipo_param <> 'NOMEADO'
     OR dst.max_qtd_parallel_env <> 2
     OR NVL(dst.timeout_seg, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'ordenar_arquivo', 'Ordena linhas de arquivo texto com opcoes numerica e reversa', 'UTILITARIOS', 'ARQUIVOS', 'ORGANIZACAO', 'SH', '/opt/automacoes/scripts/utilitarios/ordenar_arquivo.sh', 'NOMEADO', 2, 1800, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'ordenar_arquivo' AND a.nome = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'ordenar_arquivo' AND a.nome = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'ordenar_arquivo' AND a.nome = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'ordenar_arquivo' AND a.nome = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'ordenar_arquivo' AND a.nome = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'ADMINISTRADOR' AND s.nome = 'ordenar_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_PROD' AND s.nome = 'ordenar_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_HML' AND s.nome = 'ordenar_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'CONSULTA' AND s.nome = 'ordenar_arquivo'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'ordenar_arquivo' AND p.codigo = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 1,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 1
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 1, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'ordenar_arquivo' AND p.codigo = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 2,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 2
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 2, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'ordenar_arquivo' AND p.codigo = 'flag_numerico'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 3,
             dst.obrigatorio = 'N',
             dst.valor_padrao_sub = 'N',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 3
     OR dst.obrigatorio <> 'N'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL('N', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 3, 'N', 'N', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'ordenar_arquivo' AND p.codigo = 'flag_reverso'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 4,
             dst.obrigatorio = 'N',
             dst.valor_padrao_sub = 'N',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 4
     OR dst.obrigatorio <> 'N'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL('N', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 4, 'N', 'N', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'limpar_linhas_vazias' AS nome FROM DUAL) src
ON (dst.nome = src.nome)
WHEN MATCHED THEN
  UPDATE SET dst.descricao = 'Remove espacos em branco excedentes e linhas vazias de arquivo texto',
             dst.grupo = 'UTILITARIOS',
             dst.categoria = 'ARQUIVOS',
             dst.etapa = 'HIGIENIZACAO',
             dst.interpretador = 'BASH',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/limpar_linhas_vazias.sh',
             dst.tipo_param = 'NOMEADO',
             dst.max_qtd_parallel_env = 2,
             dst.timeout_seg = 1800,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ativo <> 'S'
     OR NVL(dst.descricao, '~') <> 'Remove espacos em branco excedentes e linhas vazias de arquivo texto'
     OR NVL(dst.grupo, '~') <> 'UTILITARIOS'
     OR NVL(dst.categoria, '~') <> 'ARQUIVOS'
     OR NVL(dst.etapa, '~') <> 'HIGIENIZACAO'
     OR dst.interpretador <> 'BASH'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/limpar_linhas_vazias.sh'
     OR dst.tipo_param <> 'NOMEADO'
     OR dst.max_qtd_parallel_env <> 2
     OR NVL(dst.timeout_seg, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, max_qtd_parallel_env, timeout_seg, ativo, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'limpar_linhas_vazias', 'Remove espacos em branco excedentes e linhas vazias de arquivo texto', 'UTILITARIOS', 'ARQUIVOS', 'HIGIENIZACAO', 'BASH', '/opt/automacoes/scripts/utilitarios/limpar_linhas_vazias.sh', 'NOMEADO', 2, 1800, 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'limpar_linhas_vazias' AND a.nome = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'limpar_linhas_vazias' AND a.nome = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'limpar_linhas_vazias' AND a.nome = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'limpar_linhas_vazias' AND a.nome = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_amb dst
USING (
  SELECT s.id AS script_id, a.id AS ambiente_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_ambientes a
   WHERE s.nome = 'limpar_linhas_vazias' AND a.nome = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.ambiente_id = src.ambiente_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, ambiente_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_amb.NEXTVAL, src.script_id, src.ambiente_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'ADMINISTRADOR' AND s.nome = 'limpar_linhas_vazias'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_PROD' AND s.nome = 'limpar_linhas_vazias'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'OPERADOR_HML' AND s.nome = 'limpar_linhas_vazias'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_perfil_scr dst
USING (
  SELECT p.id AS perfil_id, s.id AS script_id
    FROM openrisow.tbsss_perfis p, openrisow.tbsss_scripts s
   WHERE p.nome = 'CONSULTA' AND s.nome = 'limpar_linhas_vazias'
) src
ON (dst.perfil_id = src.perfil_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, perfil_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_perfil_scr.NEXTVAL, src.perfil_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'limpar_linhas_vazias' AND p.codigo = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 1,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 1
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 1, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parametro_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parametros p
   WHERE s.nome = 'limpar_linhas_vazias' AND p.codigo = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parametro_id = src.parametro_id)
WHEN MATCHED THEN
  UPDATE SET dst.ordem = 2,
             dst.obrigatorio = 'S',
             dst.valor_padrao_sub = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.ordem <> 2
     OR dst.obrigatorio <> 'S'
     OR NVL(dst.valor_padrao_sub, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parametro_id, 2, 'S', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_controle dst
USING (SELECT 1 AS id FROM DUAL) src
ON (dst.id = src.id)
WHEN NOT MATCHED THEN
  INSERT (id, versao_esquema, versao_aplicada_em, versao_aplicada_por)
  VALUES (1, 1, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_usuarios dst
USING (
  SELECT 'admin' AS login, p.id AS perfil_id
    FROM openrisow.tbsss_perfis p
   WHERE p.nome = 'ADMINISTRADOR'
) src
ON (dst.login = src.login)
WHEN MATCHED THEN
  UPDATE SET dst.nome = 'Super Administrador',
             dst.perfil_id = src.perfil_id,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.nome <> 'Super Administrador'
     OR dst.perfil_id <> src.perfil_id
     OR dst.ativo <> 'S'
WHEN NOT MATCHED THEN
  INSERT (id, login, nome, senha_hash, perfil_id, ativo, sessao_epoch, tentativas_falha, created_at, created_by)
  VALUES (openrisow.sq_tbsss_usuarios.NEXTVAL, 'admin', 'Super Administrador', 'pbkdf2_sha256$200000$f9fb31dc39b754d083af236a880dfa6e$2229f3f8a694a9c45be82d9c3bd38110f8b474d2a0aa0ee7f691d405738a4cd8', src.perfil_id, 'S', 0, 0, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_usuarios dst
USING (
  SELECT 'op.prod' AS login, p.id AS perfil_id
    FROM openrisow.tbsss_perfis p
   WHERE p.nome = 'OPERADOR_PROD'
) src
ON (dst.login = src.login)
WHEN MATCHED THEN
  UPDATE SET dst.nome = 'Operador Producao',
             dst.perfil_id = src.perfil_id,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.nome <> 'Operador Producao'
     OR dst.perfil_id <> src.perfil_id
     OR dst.ativo <> 'S'
WHEN NOT MATCHED THEN
  INSERT (id, login, nome, senha_hash, perfil_id, ativo, sessao_epoch, tentativas_falha, created_at, created_by)
  VALUES (openrisow.sq_tbsss_usuarios.NEXTVAL, 'op.prod', 'Operador Producao', 'pbkdf2_sha256$200000$f9fb31dc39b754d083af236a880dfa6e$2229f3f8a694a9c45be82d9c3bd38110f8b474d2a0aa0ee7f691d405738a4cd8', src.perfil_id, 'S', 0, 0, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_usuarios dst
USING (
  SELECT 'op.hml' AS login, p.id AS perfil_id
    FROM openrisow.tbsss_perfis p
   WHERE p.nome = 'OPERADOR_HML'
) src
ON (dst.login = src.login)
WHEN MATCHED THEN
  UPDATE SET dst.nome = 'Operador Homologacao',
             dst.perfil_id = src.perfil_id,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.nome <> 'Operador Homologacao'
     OR dst.perfil_id <> src.perfil_id
     OR dst.ativo <> 'S'
WHEN NOT MATCHED THEN
  INSERT (id, login, nome, senha_hash, perfil_id, ativo, sessao_epoch, tentativas_falha, created_at, created_by)
  VALUES (openrisow.sq_tbsss_usuarios.NEXTVAL, 'op.hml', 'Operador Homologacao', 'pbkdf2_sha256$200000$f9fb31dc39b754d083af236a880dfa6e$2229f3f8a694a9c45be82d9c3bd38110f8b474d2a0aa0ee7f691d405738a4cd8', src.perfil_id, 'S', 0, 0, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_usuarios dst
USING (
  SELECT 'consulta' AS login, p.id AS perfil_id
    FROM openrisow.tbsss_perfis p
   WHERE p.nome = 'CONSULTA'
) src
ON (dst.login = src.login)
WHEN MATCHED THEN
  UPDATE SET dst.nome = 'Auditor e Consulta',
             dst.perfil_id = src.perfil_id,
             dst.ativo = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.nome <> 'Auditor e Consulta'
     OR dst.perfil_id <> src.perfil_id
     OR dst.ativo <> 'S'
WHEN NOT MATCHED THEN
  INSERT (id, login, nome, senha_hash, perfil_id, ativo, sessao_epoch, tentativas_falha, created_at, created_by)
  VALUES (openrisow.sq_tbsss_usuarios.NEXTVAL, 'consulta', 'Auditor e Consulta', 'pbkdf2_sha256$200000$f9fb31dc39b754d083af236a880dfa6e$2229f3f8a694a9c45be82d9c3bd38110f8b474d2a0aa0ee7f691d405738a4cd8', src.perfil_id, 'S', 0, 0, SYSDATE, 'SYSTEM:init_db');

-- ------------------------------------------------------------------------------
-- FASE 8: ESTATISTICAS INICIAIS DO OTIMIZADOR (CR-007, R-29)
-- ------------------------------------------------------------------------------
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_FUNCIONALIDADES', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_PERFIS', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_PERFIL_FUNC', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_PERFIL_AMB', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_AMBIENTES', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_PARAMETROS', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_SCRIPTS', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_SCRIPT_AMB', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_PERFIL_SCR', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_SCRIPT_PARAM', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_CONTROLE', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_USUARIOS', cascade => TRUE);
END;
/

COMMIT;

-- ==============================================================================
-- GRANTS DE LEITURA PARA TODOS (PUBLIC)
-- ==============================================================================

GRANT SELECT ON openrisow.tbsss_ambientes TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_perfis TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_funcionalidades TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_perfil_func TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_perfil_amb TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_scripts TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_perfil_scr TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_script_amb TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_usuarios TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_parametros TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_script_param TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_agendamentos TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_tickets TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_ticket_resp TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_agentes TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_auditoria TO PUBLIC;
GRANT SELECT ON openrisow.tbsss_controle TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_ambientes TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_perfis TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_funcionalidades TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_perfil_func TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_perfil_amb TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_scripts TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_perfil_scr TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_script_amb TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_usuarios TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_parametros TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_script_param TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_agendamentos TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_tickets TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_ticket_resp TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_agentes TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_auditoria TO PUBLIC;
GRANT SELECT ON openrisow.sq_tbsss_controle TO PUBLIC;

PROMPT Implantacao do SSS concluida com sucesso!
EXIT;
