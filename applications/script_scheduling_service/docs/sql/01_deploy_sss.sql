SET DEFINE OFF;
SET SERVEROUTPUT ON;
-- Qualquer erro interrompe a implantacao com codigo de saida diferente de zero e sem a mensagem de
-- sucesso. Para reaplicar sobre um esquema existente, rode antes o 02_rollback_sss.sql.
WHENEVER SQLERROR EXIT FAILURE ROLLBACK;
WHENEVER OSERROR EXIT FAILURE ROLLBACK;

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

CREATE SEQUENCE openrisow.sq_tbsss_environments START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_profiles START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_features START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_profile_feature START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_profile_env START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_scripts START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_profile_script START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_script_env START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_users START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_parameters START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_script_param START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_schedules START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_tickets START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_ticket_answer START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_agents START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_audit START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_control START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_ticket_output START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_input_upload START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_input_delivery START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

CREATE SEQUENCE openrisow.sq_tbsss_input_listing START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;

-- ------------------------------------------------------------------------------
-- FASE 2: TABELAS
-- ------------------------------------------------------------------------------

CREATE TABLE openrisow.tbsss_environments (
    id NUMBER(10) NOT NULL,
    name VARCHAR2(30 CHAR) NOT NULL,
    description VARCHAR2(100 CHAR),
    connection VARCHAR2(250 CHAR),
    active CHAR(1) DEFAULT 'Y' NOT NULL,
    is_production CHAR(1) DEFAULT 'N' NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_profiles (
    id NUMBER(10) NOT NULL,
    name VARCHAR2(30 CHAR) NOT NULL,
    description VARCHAR2(100 CHAR),
    is_admin CHAR(1) DEFAULT 'N' NOT NULL,
    perm_version NUMBER(10) DEFAULT 1 NOT NULL,
    active CHAR(1) DEFAULT 'Y' NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_features (
    id NUMBER(10) NOT NULL,
    code VARCHAR2(30 CHAR) NOT NULL,
    name VARCHAR2(60 CHAR) NOT NULL,
    module VARCHAR2(30 CHAR) NOT NULL,
    description VARCHAR2(150 CHAR),
    active CHAR(1) DEFAULT 'Y' NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_profile_feature (
    id NUMBER(10) NOT NULL,
    profile_id NUMBER(10) NOT NULL,
    feature_id NUMBER(10) NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_profile_env (
    id NUMBER(10) NOT NULL,
    profile_id NUMBER(10) NOT NULL,
    environment_id NUMBER(10) NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_scripts (
    id NUMBER(10) NOT NULL,
    name VARCHAR2(60 CHAR) NOT NULL,
    description VARCHAR2(200 CHAR),
    script_group VARCHAR2(30 CHAR),
    category VARCHAR2(30 CHAR),
    stage VARCHAR2(30 CHAR),
    interpreter VARCHAR2(15 CHAR) NOT NULL,
    path_file VARCHAR2(500 CHAR) NOT NULL,
    param_type VARCHAR2(15 CHAR) DEFAULT 'NAMED' NOT NULL,
    max_parallel_env NUMBER(3) DEFAULT 1 NOT NULL,
    timeout_s NUMBER(7),
    active CHAR(1) DEFAULT 'Y' NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_profile_script (
    id NUMBER(10) NOT NULL,
    profile_id NUMBER(10) NOT NULL,
    script_id NUMBER(10) NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_script_env (
    id NUMBER(10) NOT NULL,
    script_id NUMBER(10) NOT NULL,
    environment_id NUMBER(10) NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_users (
    id NUMBER(10) NOT NULL,
    login VARCHAR2(30 CHAR) NOT NULL,
    name VARCHAR2(60 CHAR) NOT NULL,
    password_hash VARCHAR2(256 CHAR) NOT NULL,
    profile_id NUMBER(10) NOT NULL,
    failed_attempts NUMBER(2) DEFAULT 0 NOT NULL,
    locked_until DATE,
    last_login_at DATE,
    password_changed_at DATE,
    session_epoch NUMBER(10) DEFAULT 0 NOT NULL,
    active CHAR(1) DEFAULT 'Y' NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_parameters (
    id NUMBER(10) NOT NULL,
    code VARCHAR2(30 CHAR) NOT NULL,
    param_flag VARCHAR2(30 CHAR),
    label VARCHAR2(60 CHAR) NOT NULL,
    description VARCHAR2(150 CHAR),
    component_type VARCHAR2(20 CHAR) NOT NULL,
    options_json VARCHAR2(500 CHAR),
    default_value VARCHAR2(100 CHAR),
    validation_regex VARCHAR2(150 CHAR),
    sensitive CHAR(1) DEFAULT 'N' NOT NULL,
    active CHAR(1) DEFAULT 'Y' NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_script_param (
    id NUMBER(10) NOT NULL,
    script_id NUMBER(10) NOT NULL,
    parameter_id NUMBER(10) NOT NULL,
    sort_order NUMBER(3) NOT NULL,
    required CHAR(1) DEFAULT 'Y' NOT NULL,
    default_value_override VARCHAR2(100 CHAR),
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_schedules (
    id NUMBER(10) NOT NULL,
    name VARCHAR2(60 CHAR) NOT NULL,
    script_id NUMBER(10) NOT NULL,
    environment VARCHAR2(30 CHAR) NOT NULL,
    user_id NUMBER(10) NOT NULL,
    priority NUMBER(1) DEFAULT 2 NOT NULL,
    recurrence_type VARCHAR2(15 CHAR) NOT NULL,
    cron_expression VARCHAR2(60 CHAR),
    run_time VARCHAR2(5 CHAR),
    week_days VARCHAR2(20 CHAR),
    month_day NUMBER(2),
    params_json CLOB,
    start_date DATE NOT NULL,
    end_date DATE,
    next_run_at DATE NOT NULL,
    last_run_at DATE,
    last_ticket_id NUMBER(10),
    pause_reason VARCHAR2(30 CHAR),
    active CHAR(1) DEFAULT 'Y' NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
)
LOB (params_json) STORE AS SECUREFILE (CACHE);

CREATE TABLE openrisow.tbsss_tickets (
    id NUMBER(10) NOT NULL,
    script_id NUMBER(10) NOT NULL,
    environment VARCHAR2(30 CHAR) NOT NULL,
    requested_by VARCHAR2(30 CHAR) NOT NULL,
    source_ip VARCHAR2(45 CHAR),
    agent_id VARCHAR2(30 CHAR),
    process_id NUMBER(10),
    process_start NUMBER(20),
    status VARCHAR2(15 CHAR) DEFAULT 'PENDING' NOT NULL,
    priority NUMBER(1) DEFAULT 2 NOT NULL,
    cancel_requested CHAR(1) DEFAULT 'N' NOT NULL,
    status_reason VARCHAR2(30 CHAR),
    parent_ticket_id NUMBER(10),
    schedule_id NUMBER(10),
    submitted_params CLOB NOT NULL,
    log_output CLOB,
    log_offset_chars NUMBER(20) DEFAULT 0 NOT NULL,
    log_truncated CHAR(1) DEFAULT 'N' NOT NULL,
    return_code NUMBER(6),
    scheduled_at DATE DEFAULT SYSDATE NOT NULL,
    started_at DATE,
    heartbeat_at DATE,
    finished_at DATE,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
)
LOB (submitted_params, log_output) STORE AS SECUREFILE (CACHE);

CREATE TABLE openrisow.tbsss_ticket_answer (
    id NUMBER(10) NOT NULL,
    ticket_id NUMBER(10) NOT NULL,
    parameter_id NUMBER(10) NOT NULL,
    answer_value VARCHAR2(500 CHAR),
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_agents (
    id NUMBER(10) NOT NULL,
    code VARCHAR2(30 CHAR) NOT NULL,
    hostname VARCHAR2(255 CHAR) NOT NULL,
    daemon_pid NUMBER(10),
    version VARCHAR2(20 CHAR),
    environments VARCHAR2(1000 CHAR),
    platform VARCHAR2(10 CHAR),
    interpreters VARCHAR2(100 CHAR),
    status VARCHAR2(10 CHAR) DEFAULT 'ACTIVE' NOT NULL,
    started_at DATE,
    heartbeat_at DATE,
    critical_config VARCHAR2(400 CHAR),
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_audit (
    id NUMBER(10) NOT NULL,
    actor VARCHAR2(40 CHAR) NOT NULL,
    source_ip VARCHAR2(45 CHAR),
    action VARCHAR2(30 CHAR) NOT NULL,
    entity VARCHAR2(30 CHAR) NOT NULL,
    entity_id NUMBER(10),
    detail VARCHAR2(1000 CHAR),
    created_at DATE DEFAULT SYSDATE NOT NULL
);

CREATE TABLE openrisow.tbsss_control (
    id NUMBER(10) NOT NULL,
    schema_version NUMBER(6) NOT NULL,
    version_applied_at DATE NOT NULL,
    version_applied_by VARCHAR2(40 CHAR) NOT NULL,
    purge_owner VARCHAR2(40 CHAR),
    purge_lease_until DATE
);

CREATE TABLE openrisow.tbsss_ticket_output (
    id NUMBER(10) NOT NULL,
    ticket_id NUMBER(10) NOT NULL,
    state VARCHAR2(10 CHAR) NOT NULL,
    reason VARCHAR2(10 CHAR),
    agent_id VARCHAR2(30 CHAR) NOT NULL,
    file_count NUMBER(10),
    size_bytes NUMBER(12),
    content BLOB,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
)
LOB (content) STORE AS SECUREFILE (CACHE);

CREATE TABLE openrisow.tbsss_input_upload (
    id NUMBER(10) NOT NULL,
    environment VARCHAR2(30 CHAR) NOT NULL,
    script_id NUMBER(10) NOT NULL,
    relative_dir VARCHAR2(400 CHAR),
    file_name VARCHAR2(255 CHAR) NOT NULL,
    size_bytes NUMBER(12) NOT NULL,
    sha256 VARCHAR2(64 CHAR) NOT NULL,
    replace_existing CHAR(1) DEFAULT 'N' NOT NULL,
    source_ip VARCHAR2(45 CHAR),
    content BLOB,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
)
LOB (content) STORE AS SECUREFILE (CACHE);

CREATE TABLE openrisow.tbsss_input_delivery (
    id NUMBER(10) NOT NULL,
    upload_id NUMBER(10) NOT NULL,
    agent_id VARCHAR2(30 CHAR) NOT NULL,
    state VARCHAR2(10 CHAR) DEFAULT 'PENDING' NOT NULL,
    reason VARCHAR2(10 CHAR),
    delivered_at DATE,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
);

CREATE TABLE openrisow.tbsss_input_listing (
    id NUMBER(10) NOT NULL,
    agent_id VARCHAR2(30 CHAR) NOT NULL,
    environment VARCHAR2(30 CHAR) NOT NULL,
    script_id NUMBER(10) NOT NULL,
    listing CLOB,
    file_count NUMBER(10),
    truncated CHAR(1) DEFAULT 'N' NOT NULL,
    listed_at DATE,
    refresh_requested_at DATE,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    created_by VARCHAR2(40 CHAR) NOT NULL,
    updated_at DATE,
    updated_by VARCHAR2(40 CHAR)
)
LOB (listing) STORE AS SECUREFILE (CACHE);

-- ------------------------------------------------------------------------------
-- FASE 3: CONSTRAINTS (PK, UK, CK)
-- ------------------------------------------------------------------------------

ALTER TABLE openrisow.tbsss_environments ADD CONSTRAINT pk_tbsss_environments PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_environments ADD CONSTRAINT uk_tbsss_env_name UNIQUE (name);

ALTER TABLE openrisow.tbsss_environments ADD CONSTRAINT ck_tbsss_env_active CHECK (active IN ('Y', 'N'));

ALTER TABLE openrisow.tbsss_environments ADD CONSTRAINT ck_tbsss_env_prod CHECK (is_production IN ('Y', 'N'));

ALTER TABLE openrisow.tbsss_environments ADD CONSTRAINT ck_tbsss_env_name CHECK (REGEXP_LIKE(name, '^[A-Z0-9_]{1,30}$'));

ALTER TABLE openrisow.tbsss_environments ADD CONSTRAINT ck_tbsss_env_connection CHECK (connection IS NULL OR INSTR(connection, '@') = 0);

ALTER TABLE openrisow.tbsss_environments ADD CONSTRAINT ck_tbsss_env_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_profiles ADD CONSTRAINT pk_tbsss_profiles PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_profiles ADD CONSTRAINT uk_tbsss_prf_name UNIQUE (name);

ALTER TABLE openrisow.tbsss_profiles ADD CONSTRAINT ck_tbsss_prf_adm CHECK (is_admin IN ('Y', 'N'));

ALTER TABLE openrisow.tbsss_profiles ADD CONSTRAINT ck_tbsss_prf_active CHECK (active IN ('Y', 'N'));

ALTER TABLE openrisow.tbsss_profiles ADD CONSTRAINT ck_tbsss_prf_version CHECK (perm_version >= 1);

ALTER TABLE openrisow.tbsss_profiles ADD CONSTRAINT ck_tbsss_prf_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_features ADD CONSTRAINT pk_tbsss_features PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_features ADD CONSTRAINT uk_tbsss_fea_code UNIQUE (code);

ALTER TABLE openrisow.tbsss_features ADD CONSTRAINT ck_tbsss_fea_active CHECK (active IN ('Y', 'N'));

ALTER TABLE openrisow.tbsss_features ADD CONSTRAINT ck_tbsss_fea_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_profile_feature ADD CONSTRAINT pk_tbsss_profile_feature PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_profile_feature ADD CONSTRAINT uk_tbsss_pfea_prf_fea UNIQUE (profile_id, feature_id);

ALTER TABLE openrisow.tbsss_profile_feature ADD CONSTRAINT ck_tbsss_pfea_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_profile_env ADD CONSTRAINT pk_tbsss_profile_env PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_profile_env ADD CONSTRAINT uk_tbsss_penv_prf_env UNIQUE (profile_id, environment_id);

ALTER TABLE openrisow.tbsss_profile_env ADD CONSTRAINT ck_tbsss_penv_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT pk_tbsss_scripts PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT uk_tbsss_scr_name UNIQUE (name);

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_ptype CHECK (param_type IN ('NAMED','POSITIONAL','NONE'));

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_active CHECK (active IN ('Y', 'N'));

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_paral CHECK (max_parallel_env BETWEEN 1 AND 999);

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_int CHECK (interpreter IN ('PYTHON3','BASH','SH'));

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_path CHECK (SUBSTR(path_file, 1, 1) = '/' AND INSTR(path_file, '..') = 0 AND INSTR(path_file, '//') = 0 AND INSTR(path_file, '\') = 0);

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_tmout CHECK (timeout_s IS NULL OR timeout_s > 0);

ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_profile_script ADD CONSTRAINT pk_tbsss_profile_script PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_profile_script ADD CONSTRAINT uk_tbsss_pscr_prf_scr UNIQUE (profile_id, script_id);

ALTER TABLE openrisow.tbsss_profile_script ADD CONSTRAINT ck_tbsss_pscr_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_script_env ADD CONSTRAINT pk_tbsss_script_env PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_script_env ADD CONSTRAINT uk_tbsss_senv_scr_env UNIQUE (script_id, environment_id);

ALTER TABLE openrisow.tbsss_script_env ADD CONSTRAINT ck_tbsss_senv_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_users ADD CONSTRAINT pk_tbsss_users PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_users ADD CONSTRAINT uk_tbsss_usr_login UNIQUE (login);

ALTER TABLE openrisow.tbsss_users ADD CONSTRAINT ck_tbsss_usr_active CHECK (active IN ('Y', 'N'));

ALTER TABLE openrisow.tbsss_users ADD CONSTRAINT ck_tbsss_usr_login CHECK (REGEXP_LIKE(login, '^[a-z0-9._-]{3,30}$'));

ALTER TABLE openrisow.tbsss_users ADD CONSTRAINT ck_tbsss_usr_att CHECK (failed_attempts >= 0);

ALTER TABLE openrisow.tbsss_users ADD CONSTRAINT ck_tbsss_usr_epoch CHECK (session_epoch >= 0);

ALTER TABLE openrisow.tbsss_users ADD CONSTRAINT ck_tbsss_usr_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_parameters ADD CONSTRAINT pk_tbsss_parameters PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_parameters ADD CONSTRAINT uk_tbsss_prm_code UNIQUE (code);

ALTER TABLE openrisow.tbsss_parameters ADD CONSTRAINT ck_tbsss_prm_ctype CHECK (component_type IN ('TEXT','NUMBER','DATE','SELECT','CHECKBOX'));

ALTER TABLE openrisow.tbsss_parameters ADD CONSTRAINT ck_tbsss_prm_active CHECK (active IN ('Y', 'N'));

ALTER TABLE openrisow.tbsss_parameters ADD CONSTRAINT ck_tbsss_prm_sens CHECK (sensitive IN ('Y','N'));

ALTER TABLE openrisow.tbsss_parameters ADD CONSTRAINT ck_tbsss_prm_code CHECK (REGEXP_LIKE(code, '^[a-z0-9_]{1,30}$'));

ALTER TABLE openrisow.tbsss_parameters ADD CONSTRAINT ck_tbsss_prm_flag CHECK (param_flag IS NULL OR REGEXP_LIKE(param_flag, '^-{1,2}[A-Za-z0-9][A-Za-z0-9_-]{0,27}$'));

ALTER TABLE openrisow.tbsss_parameters ADD CONSTRAINT ck_tbsss_prm_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT pk_tbsss_script_param PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT uk_tbsss_sprm_scr_prm UNIQUE (script_id, parameter_id);

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT uk_tbsss_sprm_scr_ord UNIQUE (script_id, sort_order);

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT ck_tbsss_sprm_req CHECK (required IN ('Y', 'N'));

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT ck_tbsss_sprm_sort_order CHECK (sort_order >= 1);

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT ck_tbsss_sprm_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_schedules ADD CONSTRAINT pk_tbsss_schedules PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_schedules ADD CONSTRAINT ck_tbsss_sch_rtype CHECK (recurrence_type IN ('ONCE','DAILY','WEEKLY','MONTHLY','CRON'));

ALTER TABLE openrisow.tbsss_schedules ADD CONSTRAINT ck_tbsss_sch_prio CHECK (priority BETWEEN 1 AND 4);

ALTER TABLE openrisow.tbsss_schedules ADD CONSTRAINT ck_tbsss_sch_active CHECK (active IN ('Y', 'N'));

ALTER TABLE openrisow.tbsss_schedules ADD CONSTRAINT ck_tbsss_sch_day CHECK (month_day IS NULL OR month_day BETWEEN 1 AND 31);

ALTER TABLE openrisow.tbsss_schedules ADD CONSTRAINT ck_tbsss_sch_time CHECK (run_time IS NULL OR REGEXP_LIKE(run_time, '^([01][0-9]|2[0-3]):[0-5][0-9]$'));

ALTER TABLE openrisow.tbsss_schedules ADD CONSTRAINT ck_tbsss_sch_wday CHECK (week_days IS NULL OR REGEXP_LIKE(week_days, '^[1-7](,[1-7]){0,6}$'));

ALTER TABLE openrisow.tbsss_schedules ADD CONSTRAINT ck_tbsss_sch_end CHECK (end_date IS NULL OR end_date >= start_date);

ALTER TABLE openrisow.tbsss_schedules ADD CONSTRAINT ck_tbsss_sch_pause CHECK (pause_reason IS NULL OR pause_reason IN ('USER_INACTIVE','NO_PERMISSION','SCRIPT_INACTIVE','ENVIRONMENT_INACTIVE','INVALID_PARAM','INVALID_CRON','COMPLETED','MANUAL','INTERNAL_ERROR'));

ALTER TABLE openrisow.tbsss_schedules ADD CONSTRAINT ck_tbsss_sch_fields CHECK ((recurrence_type = 'ONCE') OR (recurrence_type = 'DAILY' AND run_time IS NOT NULL) OR (recurrence_type = 'WEEKLY' AND run_time IS NOT NULL AND week_days IS NOT NULL) OR (recurrence_type = 'MONTHLY' AND run_time IS NOT NULL AND month_day IS NOT NULL) OR (recurrence_type = 'CRON' AND cron_expression IS NOT NULL));

ALTER TABLE openrisow.tbsss_schedules ADD CONSTRAINT ck_tbsss_sch_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT pk_tbsss_tickets PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_stat CHECK (status IN ('PENDING','RUNNING','SUCCESS','FAILED','CANCELLED'));

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_prio CHECK (priority BETWEEN 1 AND 4);

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_cancreq CHECK (cancel_requested IN ('Y','N'));

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_logtr CHECK (log_truncated IN ('Y','N'));

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_logoff CHECK (log_offset_chars >= 0);

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_reason CHECK (status_reason IS NULL OR status_reason IN ('EXIT_OK','EXIT_ERROR','KILLED_SIGNAL','TIMEOUT','NODE_OFFLINE','ORPHAN_PROCESS','FENCED','PRECHECK_FAILED','SPAWN_ERROR','LOG_LIMIT','SHUTDOWN','CANCEL_USER'));

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT ck_tbsss_tck_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_ticket_answer ADD CONSTRAINT pk_tbsss_ticket_answer PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_ticket_answer ADD CONSTRAINT uk_tbsss_tans_tck_prm UNIQUE (ticket_id, parameter_id);

ALTER TABLE openrisow.tbsss_ticket_answer ADD CONSTRAINT ck_tbsss_tans_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_agents ADD CONSTRAINT pk_tbsss_agents PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_agents ADD CONSTRAINT uk_tbsss_agt_code UNIQUE (code);

ALTER TABLE openrisow.tbsss_agents ADD CONSTRAINT ck_tbsss_agt_stat CHECK (status IN ('ACTIVE','STOPPED'));

ALTER TABLE openrisow.tbsss_agents ADD CONSTRAINT ck_tbsss_agt_plat CHECK (platform IS NULL OR platform IN ('LINUX','UNIX'));

ALTER TABLE openrisow.tbsss_agents ADD CONSTRAINT ck_tbsss_agt_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_audit ADD CONSTRAINT pk_tbsss_audit PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_control ADD CONSTRAINT pk_tbsss_control PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_control ADD CONSTRAINT ck_tbsss_ctl_id CHECK (id = 1);

ALTER TABLE openrisow.tbsss_control ADD CONSTRAINT ck_tbsss_ctl_version CHECK (schema_version >= 1);

ALTER TABLE openrisow.tbsss_ticket_output ADD CONSTRAINT pk_tbsss_ticket_output PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_ticket_output ADD CONSTRAINT uk_tbsss_tout_tck UNIQUE (ticket_id);

ALTER TABLE openrisow.tbsss_ticket_output ADD CONSTRAINT ck_tbsss_tout_state CHECK (state IN ('WRITING','AVAILABLE','EXCEEDED','FAILED'));

ALTER TABLE openrisow.tbsss_ticket_output ADD CONSTRAINT ck_tbsss_tout_rsn CHECK (reason IS NULL OR reason IN ('FILES','BYTES','DEADLINE','ERROR'));

ALTER TABLE openrisow.tbsss_ticket_output ADD CONSTRAINT ck_tbsss_tout_size CHECK ((file_count IS NULL OR file_count >= 0) AND (size_bytes IS NULL OR size_bytes >= 0));

ALTER TABLE openrisow.tbsss_ticket_output ADD CONSTRAINT ck_tbsss_tout_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_input_upload ADD CONSTRAINT pk_tbsss_input_upload PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_input_upload ADD CONSTRAINT ck_tbsss_iup_repl CHECK (replace_existing IN ('Y','N'));

ALTER TABLE openrisow.tbsss_input_upload ADD CONSTRAINT ck_tbsss_iup_size CHECK (size_bytes >= 0);

ALTER TABLE openrisow.tbsss_input_upload ADD CONSTRAINT ck_tbsss_iup_sha CHECK (LENGTH(sha256) = 64);

ALTER TABLE openrisow.tbsss_input_upload ADD CONSTRAINT ck_tbsss_iup_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_input_delivery ADD CONSTRAINT pk_tbsss_input_delivery PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_input_delivery ADD CONSTRAINT uk_tbsss_idl_upl_agt UNIQUE (upload_id, agent_id);

ALTER TABLE openrisow.tbsss_input_delivery ADD CONSTRAINT ck_tbsss_idl_state CHECK (state IN ('PENDING','DELIVERED','FAILED'));

ALTER TABLE openrisow.tbsss_input_delivery ADD CONSTRAINT ck_tbsss_idl_rsn CHECK ((state = 'FAILED' AND reason IN ('EXISTS','NAME','SPACE','HASH','ERROR')) OR (state <> 'FAILED' AND reason IS NULL));

ALTER TABLE openrisow.tbsss_input_delivery ADD CONSTRAINT ck_tbsss_idl_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

ALTER TABLE openrisow.tbsss_input_listing ADD CONSTRAINT pk_tbsss_input_listing PRIMARY KEY (id);

ALTER TABLE openrisow.tbsss_input_listing ADD CONSTRAINT uk_tbsss_ils_agt UNIQUE (agent_id, environment, script_id);

ALTER TABLE openrisow.tbsss_input_listing ADD CONSTRAINT ck_tbsss_ils_trunc CHECK (truncated IN ('Y','N'));

ALTER TABLE openrisow.tbsss_input_listing ADD CONSTRAINT ck_tbsss_ils_count CHECK (file_count IS NULL OR file_count >= 0);

ALTER TABLE openrisow.tbsss_input_listing ADD CONSTRAINT ck_tbsss_ils_upd CHECK ((updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL));

-- ------------------------------------------------------------------------------
-- FASE 4: CONSTRAINTS (FK)
-- ------------------------------------------------------------------------------

ALTER TABLE openrisow.tbsss_profile_feature ADD CONSTRAINT fk_tbsss_pfea_prf FOREIGN KEY (profile_id) REFERENCES openrisow.tbsss_profiles (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_profile_feature ADD CONSTRAINT fk_tbsss_pfea_fea FOREIGN KEY (feature_id) REFERENCES openrisow.tbsss_features (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_profile_env ADD CONSTRAINT fk_tbsss_penv_prf FOREIGN KEY (profile_id) REFERENCES openrisow.tbsss_profiles (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_profile_env ADD CONSTRAINT fk_tbsss_penv_env FOREIGN KEY (environment_id) REFERENCES openrisow.tbsss_environments (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_profile_script ADD CONSTRAINT fk_tbsss_pscr_prf FOREIGN KEY (profile_id) REFERENCES openrisow.tbsss_profiles (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_profile_script ADD CONSTRAINT fk_tbsss_pscr_scr FOREIGN KEY (script_id) REFERENCES openrisow.tbsss_scripts (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_script_env ADD CONSTRAINT fk_tbsss_senv_scr FOREIGN KEY (script_id) REFERENCES openrisow.tbsss_scripts (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_script_env ADD CONSTRAINT fk_tbsss_senv_env FOREIGN KEY (environment_id) REFERENCES openrisow.tbsss_environments (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_users ADD CONSTRAINT fk_tbsss_usr_prf FOREIGN KEY (profile_id) REFERENCES openrisow.tbsss_profiles (id);

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT fk_tbsss_sprm_scr FOREIGN KEY (script_id) REFERENCES openrisow.tbsss_scripts (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_script_param ADD CONSTRAINT fk_tbsss_sprm_prm FOREIGN KEY (parameter_id) REFERENCES openrisow.tbsss_parameters (id);

ALTER TABLE openrisow.tbsss_schedules ADD CONSTRAINT fk_tbsss_sch_scr FOREIGN KEY (script_id) REFERENCES openrisow.tbsss_scripts (id);

ALTER TABLE openrisow.tbsss_schedules ADD CONSTRAINT fk_tbsss_sch_usr FOREIGN KEY (user_id) REFERENCES openrisow.tbsss_users (id);

ALTER TABLE openrisow.tbsss_schedules ADD CONSTRAINT fk_tbsss_sch_env FOREIGN KEY (environment) REFERENCES openrisow.tbsss_environments (name);

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT fk_tbsss_tck_scr FOREIGN KEY (script_id) REFERENCES openrisow.tbsss_scripts (id);

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT fk_tbsss_tck_env FOREIGN KEY (environment) REFERENCES openrisow.tbsss_environments (name);

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT fk_tbsss_tck_usr FOREIGN KEY (requested_by) REFERENCES openrisow.tbsss_users (login);

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT fk_tbsss_tck_parent FOREIGN KEY (parent_ticket_id) REFERENCES openrisow.tbsss_tickets (id) ON DELETE SET NULL;

ALTER TABLE openrisow.tbsss_tickets ADD CONSTRAINT fk_tbsss_tck_sch FOREIGN KEY (schedule_id) REFERENCES openrisow.tbsss_schedules (id) ON DELETE SET NULL;

ALTER TABLE openrisow.tbsss_ticket_answer ADD CONSTRAINT fk_tbsss_tans_tck FOREIGN KEY (ticket_id) REFERENCES openrisow.tbsss_tickets (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_ticket_answer ADD CONSTRAINT fk_tbsss_tans_prm FOREIGN KEY (parameter_id) REFERENCES openrisow.tbsss_parameters (id);

ALTER TABLE openrisow.tbsss_ticket_output ADD CONSTRAINT fk_tbsss_tout_tck FOREIGN KEY (ticket_id) REFERENCES openrisow.tbsss_tickets (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_input_upload ADD CONSTRAINT fk_tbsss_iup_env FOREIGN KEY (environment) REFERENCES openrisow.tbsss_environments (name);

ALTER TABLE openrisow.tbsss_input_upload ADD CONSTRAINT fk_tbsss_iup_scr FOREIGN KEY (script_id) REFERENCES openrisow.tbsss_scripts (id);

ALTER TABLE openrisow.tbsss_input_delivery ADD CONSTRAINT fk_tbsss_idl_upl FOREIGN KEY (upload_id) REFERENCES openrisow.tbsss_input_upload (id) ON DELETE CASCADE;

ALTER TABLE openrisow.tbsss_input_listing ADD CONSTRAINT fk_tbsss_ils_env FOREIGN KEY (environment) REFERENCES openrisow.tbsss_environments (name);

ALTER TABLE openrisow.tbsss_input_listing ADD CONSTRAINT fk_tbsss_ils_scr FOREIGN KEY (script_id) REFERENCES openrisow.tbsss_scripts (id);

-- ------------------------------------------------------------------------------
-- FASE 5: INDICES
-- ------------------------------------------------------------------------------

CREATE INDEX openrisow.ix_tbsss_pfea_fea ON openrisow.tbsss_profile_feature (feature_id);

CREATE INDEX openrisow.ix_tbsss_penv_env ON openrisow.tbsss_profile_env (environment_id);

CREATE INDEX openrisow.ix_tbsss_pscr_scr ON openrisow.tbsss_profile_script (script_id);

CREATE INDEX openrisow.ix_tbsss_senv_env ON openrisow.tbsss_script_env (environment_id);

CREATE INDEX openrisow.ix_tbsss_usr_prf ON openrisow.tbsss_users (profile_id);

CREATE INDEX openrisow.ix_tbsss_sprm_prm ON openrisow.tbsss_script_param (parameter_id);

CREATE INDEX openrisow.ix_tbsss_sch_scr ON openrisow.tbsss_schedules (script_id);

CREATE INDEX openrisow.ix_tbsss_sch_usr ON openrisow.tbsss_schedules (user_id);

CREATE INDEX openrisow.ix_tbsss_sch_env ON openrisow.tbsss_schedules (environment);

CREATE INDEX openrisow.ix_tbsss_sch_next ON openrisow.tbsss_schedules (active, next_run_at, id);

CREATE INDEX openrisow.ix_tbsss_tck_scr ON openrisow.tbsss_tickets (script_id, environment, status);

CREATE INDEX openrisow.ix_tbsss_tck_env ON openrisow.tbsss_tickets (environment);

CREATE INDEX openrisow.ix_tbsss_tck_usr ON openrisow.tbsss_tickets (requested_by);

CREATE INDEX openrisow.ix_tbsss_tck_par ON openrisow.tbsss_tickets (parent_ticket_id);

CREATE INDEX openrisow.ix_tbsss_tck_sch ON openrisow.tbsss_tickets (schedule_id);

CREATE INDEX openrisow.ix_tbsss_tck_crt ON openrisow.tbsss_tickets (created_at, id);

CREATE INDEX openrisow.ix_tbsss_tck_hist ON openrisow.tbsss_tickets (script_id, created_at);

CREATE INDEX openrisow.ix_tbsss_tck_queue ON openrisow.tbsss_tickets (status, environment, priority, GREATEST(scheduled_at, created_at), id, script_id);

CREATE INDEX openrisow.ix_tbsss_tck_run ON openrisow.tbsss_tickets ((CASE WHEN status = 'RUNNING' THEN agent_id END));

CREATE UNIQUE INDEX openrisow.ix_tbsss_tck_occur ON openrisow.tbsss_tickets ((CASE WHEN schedule_id IS NOT NULL THEN schedule_id END), (CASE WHEN schedule_id IS NOT NULL THEN scheduled_at END));

CREATE INDEX openrisow.ix_tbsss_tans_prm ON openrisow.tbsss_ticket_answer (parameter_id);

CREATE INDEX openrisow.ix_tbsss_aud_crt ON openrisow.tbsss_audit (created_at);

CREATE INDEX openrisow.ix_tbsss_aud_ent ON openrisow.tbsss_audit (entity, entity_id);

CREATE INDEX openrisow.ix_tbsss_aud_actor ON openrisow.tbsss_audit (actor);

CREATE INDEX openrisow.ix_tbsss_tout_write ON openrisow.tbsss_ticket_output ((CASE WHEN state = 'WRITING' THEN agent_id END));

CREATE INDEX openrisow.ix_tbsss_iup_env ON openrisow.tbsss_input_upload (environment, script_id, created_at);

CREATE INDEX openrisow.ix_tbsss_iup_scr ON openrisow.tbsss_input_upload (script_id);

CREATE INDEX openrisow.ix_tbsss_iup_crt ON openrisow.tbsss_input_upload (created_at, id);

CREATE INDEX openrisow.ix_tbsss_idl_pend ON openrisow.tbsss_input_delivery ((CASE WHEN state = 'PENDING' THEN agent_id END));

CREATE INDEX openrisow.ix_tbsss_ils_env ON openrisow.tbsss_input_listing (environment, script_id);

CREATE INDEX openrisow.ix_tbsss_ils_scr ON openrisow.tbsss_input_listing (script_id);

-- ------------------------------------------------------------------------------
-- FASE 6: TRIGGERS
-- ------------------------------------------------------------------------------

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_env_bi
-- TABELA ALVO: openrisow.tbsss_environments
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_environments FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_environments. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_env_bi
BEFORE INSERT ON openrisow.tbsss_environments
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_environments.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_env_bu
-- TABELA ALVO: openrisow.tbsss_environments
-- EVENTO: BEFORE UPDATE ON openrisow.tbsss_environments FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Garante a imutabilidade estrita da chave natural 'name'.
-- Bloqueia qualquer alteracao posterior de valor para preservar integridade de FKs.
-- REGRA: README §10 e AGENTS.md §4.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_env_bu
BEFORE UPDATE ON openrisow.tbsss_environments
FOR EACH ROW
BEGIN
    IF :NEW.name <> :OLD.name THEN
        RAISE_APPLICATION_ERROR(-20001, 'name é imutável');
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_prf_bi
-- TABELA ALVO: openrisow.tbsss_profiles
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_profiles FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_profiles. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_prf_bi
BEFORE INSERT ON openrisow.tbsss_profiles
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_profiles.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_fea_bi
-- TABELA ALVO: openrisow.tbsss_features
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_features FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_features. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_fea_bi
BEFORE INSERT ON openrisow.tbsss_features
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_features.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_pfea_bi
-- TABELA ALVO: openrisow.tbsss_profile_feature
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_profile_feature FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_profile_feature. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_pfea_bi
BEFORE INSERT ON openrisow.tbsss_profile_feature
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_profile_feature.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_penv_bi
-- TABELA ALVO: openrisow.tbsss_profile_env
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_profile_env FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_profile_env. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_penv_bi
BEFORE INSERT ON openrisow.tbsss_profile_env
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_profile_env.NEXTVAL INTO :NEW.id FROM DUAL;
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
-- TABELA ALVO: openrisow.tbsss_profile_script
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_profile_script FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_profile_script. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_pscr_bi
BEFORE INSERT ON openrisow.tbsss_profile_script
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_profile_script.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_senv_bi
-- TABELA ALVO: openrisow.tbsss_script_env
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_script_env FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_script_env. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_senv_bi
BEFORE INSERT ON openrisow.tbsss_script_env
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_script_env.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_usr_bi
-- TABELA ALVO: openrisow.tbsss_users
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_users FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_users. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_usr_bi
BEFORE INSERT ON openrisow.tbsss_users
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_users.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_usr_bu
-- TABELA ALVO: openrisow.tbsss_users
-- EVENTO: BEFORE UPDATE ON openrisow.tbsss_users FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Garante a imutabilidade estrita da chave natural 'login'.
-- Bloqueia qualquer alteracao posterior de valor para preservar integridade de FKs.
-- REGRA: README §10 e AGENTS.md §4.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_usr_bu
BEFORE UPDATE ON openrisow.tbsss_users
FOR EACH ROW
BEGIN
    IF :NEW.login <> :OLD.login THEN
        RAISE_APPLICATION_ERROR(-20001, 'login é imutável');
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_prm_bi
-- TABELA ALVO: openrisow.tbsss_parameters
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_parameters FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_parameters. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_prm_bi
BEFORE INSERT ON openrisow.tbsss_parameters
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_parameters.NEXTVAL INTO :NEW.id FROM DUAL;
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
-- TRIGGER: openrisow.tr_tbsss_sch_bi
-- TABELA ALVO: openrisow.tbsss_schedules
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_schedules FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_schedules. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_sch_bi
BEFORE INSERT ON openrisow.tbsss_schedules
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_schedules.NEXTVAL INTO :NEW.id FROM DUAL;
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
-- TRIGGER: openrisow.tr_tbsss_tans_bi
-- TABELA ALVO: openrisow.tbsss_ticket_answer
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_ticket_answer FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_ticket_answer. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_tans_bi
BEFORE INSERT ON openrisow.tbsss_ticket_answer
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_ticket_answer.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_agt_bi
-- TABELA ALVO: openrisow.tbsss_agents
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_agents FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_agents. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_agt_bi
BEFORE INSERT ON openrisow.tbsss_agents
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_agents.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_aud_bi
-- TABELA ALVO: openrisow.tbsss_audit
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_audit FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_audit. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_aud_bi
BEFORE INSERT ON openrisow.tbsss_audit
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_audit.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_ctl_bi
-- TABELA ALVO: openrisow.tbsss_control
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_control FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_control. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_ctl_bi
BEFORE INSERT ON openrisow.tbsss_control
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_control.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_tout_bi
-- TABELA ALVO: openrisow.tbsss_ticket_output
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_ticket_output FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_ticket_output. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_tout_bi
BEFORE INSERT ON openrisow.tbsss_ticket_output
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_ticket_output.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_iup_bi
-- TABELA ALVO: openrisow.tbsss_input_upload
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_input_upload FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_input_upload. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_iup_bi
BEFORE INSERT ON openrisow.tbsss_input_upload
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_input_upload.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_idl_bi
-- TABELA ALVO: openrisow.tbsss_input_delivery
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_input_delivery FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_input_delivery. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_idl_bi
BEFORE INSERT ON openrisow.tbsss_input_delivery
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_input_delivery.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ==============================================================================
-- TRIGGER: openrisow.tr_tbsss_ils_bi
-- TABELA ALVO: openrisow.tbsss_input_listing
-- EVENTO: BEFORE INSERT ON openrisow.tbsss_input_listing FOR EACH ROW
-- FINALIDADE DE GOVERNANCA: Atribuicao automatica condicional de PK via sequence
-- openrisow.sq_tbsss_input_listing. Preserva ID explicitamente informado (migracoes/carga).
-- REGRA: AGENTS.md §4.2 e README §10.
-- ==============================================================================
CREATE OR REPLACE TRIGGER openrisow.tr_tbsss_ils_bi
BEFORE INSERT ON openrisow.tbsss_input_listing
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT openrisow.sq_tbsss_input_listing.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ------------------------------------------------------------------------------
-- FASE 7: DICIONARIO E GOVERNANCA DE DADOS (COMMENTS)
-- ------------------------------------------------------------------------------

COMMENT ON TABLE openrisow.tbsss_environments IS 'Cadastro de ambientes operacionais para execucao de rotinas (PRODUCAO, HOMOLOGACAO, CLONES)';
COMMENT ON COLUMN openrisow.tbsss_environments.id IS 'Identificador unico sequencial do ambiente (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_environments.name IS 'Nome mnemonico unico do ambiente em maiusculas (chave natural imutavel)';
COMMENT ON COLUMN openrisow.tbsss_environments.description IS 'Descricao detalhada do ambiente, servidor host e finalidade';
COMMENT ON COLUMN openrisow.tbsss_environments.connection IS 'String de conexao ou alias DSN/TNS sugerido para o banco de dados do ambiente';
COMMENT ON COLUMN openrisow.tbsss_environments.active IS 'Indicador de vigencia do ambiente (Y=Ativo, N=Inativo)';
COMMENT ON COLUMN openrisow.tbsss_environments.is_production IS 'Ambiente de producao: o disparo mostra alerta e confirmacao em vermelho (Y/N)';
COMMENT ON COLUMN openrisow.tbsss_environments.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_environments.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_environments.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_environments.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_profiles IS 'Perfis de acesso para autorizacao baseada em papeis (RBAC)';
COMMENT ON COLUMN openrisow.tbsss_profiles.id IS 'Identificador unico sequencial do perfil (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_profiles.name IS 'Nome unico de identificacao do perfil (ex: ADMINISTRATOR, OPERADOR)';
COMMENT ON COLUMN openrisow.tbsss_profiles.description IS 'Finalidade e escopo de atuacao dos usuarios vinculados ao perfil';
COMMENT ON COLUMN openrisow.tbsss_profiles.is_admin IS 'Indicador de perfil com poderes administrativos plenos (Y/N)';
COMMENT ON COLUMN openrisow.tbsss_profiles.perm_version IS 'Versao incremental das permissoes para invalidacao de sessoes ativas';
COMMENT ON COLUMN openrisow.tbsss_profiles.active IS 'Indicador de vigencia do perfil no sistema (Y=Ativo, N=Inativo)';
COMMENT ON COLUMN openrisow.tbsss_profiles.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_profiles.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_profiles.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_profiles.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_features IS 'Catalogo canonico de permissoes e operacoes controladas pelo sistema';
COMMENT ON COLUMN openrisow.tbsss_features.id IS 'Identificador unico sequencial da funcionalidade (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_features.code IS 'Codigo mnemonico unico da operacao (ex: EXEC_SCRIPT, VIEW_LOGS, CANCEL_TICKET)';
COMMENT ON COLUMN openrisow.tbsss_features.name IS 'Nome amigavel de exibicao da funcionalidade na interface';
COMMENT ON COLUMN openrisow.tbsss_features.module IS 'Modulo funcional do sistema ao qual a operacao pertence (OPERATION, ADMIN)';
COMMENT ON COLUMN openrisow.tbsss_features.description IS 'Descricao clara das acoes permitidas por esta funcionalidade';
COMMENT ON COLUMN openrisow.tbsss_features.active IS 'Indicador de vigencia da funcionalidade no sistema (Y/N)';
COMMENT ON COLUMN openrisow.tbsss_features.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_features.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_features.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_features.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_profile_feature IS 'Matriz associativa de permissoes que vincula perfis a funcionalidades autorizadas';
COMMENT ON COLUMN openrisow.tbsss_profile_feature.id IS 'Identificador unico sequencial do vinculo (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_profile_feature.profile_id IS 'Identificador do perfil associado (FK para tbsss_profiles)';
COMMENT ON COLUMN openrisow.tbsss_profile_feature.feature_id IS 'Identificador da funcionalidade autorizada (FK para tbsss_features)';
COMMENT ON COLUMN openrisow.tbsss_profile_feature.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_profile_feature.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_profile_feature.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_profile_feature.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_profile_env IS 'Associacao que delimita os ambientes onde cada perfil possui autorizacao';
COMMENT ON COLUMN openrisow.tbsss_profile_env.id IS 'Identificador unico sequencial do vinculo (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_profile_env.profile_id IS 'Identificador do perfil autorizado (FK para tbsss_profiles)';
COMMENT ON COLUMN openrisow.tbsss_profile_env.environment_id IS 'Identificador do ambiente autorizado (FK para tbsss_environments)';
COMMENT ON COLUMN openrisow.tbsss_profile_env.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_profile_env.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_profile_env.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_profile_env.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_scripts IS 'Catalogo de rotinas e scripts homologados para execucao automatizada';
COMMENT ON COLUMN openrisow.tbsss_scripts.id IS 'Identificador unico sequencial do script (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_scripts.name IS 'Nome unico da rotina (ex: carga_diaria, relatorio_mensal)';
COMMENT ON COLUMN openrisow.tbsss_scripts.description IS 'Detalhamento da finalidade, regras e impacto da execucao do script';
COMMENT ON COLUMN openrisow.tbsss_scripts.script_group IS 'Coluna script_group da tabela tbsss_scripts';
COMMENT ON COLUMN openrisow.tbsss_scripts.category IS 'Categoria de negocio ou agrupador funcional da rotina';
COMMENT ON COLUMN openrisow.tbsss_scripts.stage IS 'Coluna stage da tabela tbsss_scripts';
COMMENT ON COLUMN openrisow.tbsss_scripts.interpreter IS 'Interpretador utilizado para execucao (PYTHON3, BASH, SH)';
COMMENT ON COLUMN openrisow.tbsss_scripts.path_file IS 'Caminho absoluto normalizado do script no sistema de arquivos do servidor';
COMMENT ON COLUMN openrisow.tbsss_scripts.param_type IS 'Coluna param_type da tabela tbsss_scripts';
COMMENT ON COLUMN openrisow.tbsss_scripts.max_parallel_env IS 'Coluna max_parallel_env da tabela tbsss_scripts';
COMMENT ON COLUMN openrisow.tbsss_scripts.timeout_s IS 'Coluna timeout_s da tabela tbsss_scripts';
COMMENT ON COLUMN openrisow.tbsss_scripts.active IS 'Indicador de disponibilidade da rotina para novas execucoes (Y/N)';
COMMENT ON COLUMN openrisow.tbsss_scripts.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_scripts.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_scripts.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_scripts.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_profile_script IS 'Associacao que define quais rotinas cada perfil tem permissao para disparar';
COMMENT ON COLUMN openrisow.tbsss_profile_script.id IS 'Identificador unico sequencial do vinculo (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_profile_script.profile_id IS 'Identificador do perfil autorizado (FK para tbsss_profiles)';
COMMENT ON COLUMN openrisow.tbsss_profile_script.script_id IS 'Identificador da rotina homologada (FK para tbsss_scripts)';
COMMENT ON COLUMN openrisow.tbsss_profile_script.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_profile_script.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_profile_script.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_profile_script.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_script_env IS 'Homologacao tecnica que associa rotinas aos ambientes onde podem rodar';
COMMENT ON COLUMN openrisow.tbsss_script_env.id IS 'Identificador unico sequencial da homologacao (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_script_env.script_id IS 'Identificador do script homologado (FK para tbsss_scripts)';
COMMENT ON COLUMN openrisow.tbsss_script_env.environment_id IS 'Identificador do ambiente onde a rotina e permitida (FK para tbsss_environments)';
COMMENT ON COLUMN openrisow.tbsss_script_env.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_script_env.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_script_env.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_script_env.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_users IS 'Cadastro de operadores do sistema, credenciais e controle de sessao';
COMMENT ON COLUMN openrisow.tbsss_users.id IS 'Identificador unico sequencial do usuario (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_users.login IS 'Identificador de login do usuario (chave natural imutavel)';
COMMENT ON COLUMN openrisow.tbsss_users.name IS 'Nome completo do operador para identificacao';
COMMENT ON COLUMN openrisow.tbsss_users.password_hash IS 'Hash criptografico da senha gerado via PBKDF2-SHA256 (200k iteracoes)';
COMMENT ON COLUMN openrisow.tbsss_users.profile_id IS 'Identificador do perfil de acesso atribuido (FK para tbsss_profiles)';
COMMENT ON COLUMN openrisow.tbsss_users.failed_attempts IS 'Numero de tentativas consecutivas de autenticacao incorretas';
COMMENT ON COLUMN openrisow.tbsss_users.locked_until IS 'Data e hora limite de bloqueio temporario por excesso de falhas';
COMMENT ON COLUMN openrisow.tbsss_users.last_login_at IS 'Coluna last_login_at da tabela tbsss_users';
COMMENT ON COLUMN openrisow.tbsss_users.password_changed_at IS 'Coluna password_changed_at da tabela tbsss_users';
COMMENT ON COLUMN openrisow.tbsss_users.session_epoch IS 'Contador de revogacao de sessoes ativas para seguranca';
COMMENT ON COLUMN openrisow.tbsss_users.active IS 'Indicador se o usuario esta ativo (Y=Ativo, N=Bloqueado/Inativo)';
COMMENT ON COLUMN openrisow.tbsss_users.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_users.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_users.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_users.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_parameters IS 'Dicionario de perguntas, variaveis e flags reutilizaveis em scripts';
COMMENT ON COLUMN openrisow.tbsss_parameters.id IS 'Identificador unico sequencial do parametro (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_parameters.code IS 'Codigo mnemonico unico do parametro (ex: DATA_REF, FORMATO)';
COMMENT ON COLUMN openrisow.tbsss_parameters.param_flag IS 'Coluna param_flag da tabela tbsss_parameters';
COMMENT ON COLUMN openrisow.tbsss_parameters.label IS 'Rotulo de exibicao amigavel apresentado no formulario ao usuario';
COMMENT ON COLUMN openrisow.tbsss_parameters.description IS 'Texto explicativo de orientacao ao operador';
COMMENT ON COLUMN openrisow.tbsss_parameters.component_type IS 'Tipo de componente visual (TEXTO, NUMERO, DATA, SELECT, RADIO, CHECKBOX)';
COMMENT ON COLUMN openrisow.tbsss_parameters.options_json IS 'Opcoes selecionaveis em formato JSON para componentes do tipo lista';
COMMENT ON COLUMN openrisow.tbsss_parameters.default_value IS 'Valor pre-definido padrao sugerido no formulario';
COMMENT ON COLUMN openrisow.tbsss_parameters.validation_regex IS 'Expressao regular segura para validacao do valor inserido';
COMMENT ON COLUMN openrisow.tbsss_parameters.sensitive IS 'Indicador se o dado e confidencial e deve ser mascarado em logs (Y/N)';
COMMENT ON COLUMN openrisow.tbsss_parameters.active IS 'Indicador de vigencia do parametro no sistema (Y/N)';
COMMENT ON COLUMN openrisow.tbsss_parameters.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_parameters.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_parameters.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_parameters.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_script_param IS 'Composicao e ordenacao dos parametros exigidos por cada rotina';
COMMENT ON COLUMN openrisow.tbsss_script_param.id IS 'Identificador unico sequencial da associacao (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_script_param.script_id IS 'Identificador do script (FK para tbsss_scripts)';
COMMENT ON COLUMN openrisow.tbsss_script_param.parameter_id IS 'Identificador do parametro associado (FK para tbsss_parameters)';
COMMENT ON COLUMN openrisow.tbsss_script_param.sort_order IS 'Posicao de apresentacao do campo no questionario de execucao';
COMMENT ON COLUMN openrisow.tbsss_script_param.required IS 'Indicador se o preenchimento e mandatorio para esta rotina (Y/N)';
COMMENT ON COLUMN openrisow.tbsss_script_param.default_value_override IS 'Valor padrao especifico que sobrescreve o valor do parametro para este script';
COMMENT ON COLUMN openrisow.tbsss_script_param.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_script_param.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_script_param.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_script_param.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_schedules IS 'Regras de execucao periodica automatica ou avulsa de rotinas';
COMMENT ON COLUMN openrisow.tbsss_schedules.id IS 'Identificador unico sequencial do agendamento (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_schedules.name IS 'Titulo descritivo da regra de agendamento';
COMMENT ON COLUMN openrisow.tbsss_schedules.script_id IS 'Identificador da rotina a ser executada (FK para tbsss_scripts)';
COMMENT ON COLUMN openrisow.tbsss_schedules.environment IS 'Nome do ambiente onde a rotina deve ser disparada (FK para tbsss_environments)';
COMMENT ON COLUMN openrisow.tbsss_schedules.user_id IS 'Operador responsavel pelo agendamento (FK para tbsss_users)';
COMMENT ON COLUMN openrisow.tbsss_schedules.priority IS 'Nivel de prioridade da execucao (1=Critico a 4=Baixa)';
COMMENT ON COLUMN openrisow.tbsss_schedules.recurrence_type IS 'Tipo de periodicidade (ONCE, DAILY, WEEKLY, MONTHLY, CRON)';
COMMENT ON COLUMN openrisow.tbsss_schedules.cron_expression IS 'Expressao cron no formato padrao de 5 campos (minuto hora dia mes dsem)';
COMMENT ON COLUMN openrisow.tbsss_schedules.run_time IS 'Horario de disparo no formato HH:MM para recorrencias diarias/semanais/mensais';
COMMENT ON COLUMN openrisow.tbsss_schedules.week_days IS 'Dias da semana selecionados (1=Dom a 7=Sab) para agendamento semanal';
COMMENT ON COLUMN openrisow.tbsss_schedules.month_day IS 'Dia do mes (1 a 31) para agendamento mensal';
COMMENT ON COLUMN openrisow.tbsss_schedules.params_json IS 'Parametros congelados configurados para o agendamento em JSON (CLOB)';
COMMENT ON COLUMN openrisow.tbsss_schedules.start_date IS 'Data inicial de vigencia do agendamento';
COMMENT ON COLUMN openrisow.tbsss_schedules.end_date IS 'Data final limite para expiracao do agendamento';
COMMENT ON COLUMN openrisow.tbsss_schedules.next_run_at IS 'Data e hora exatas calculadas para o proximo disparo';
COMMENT ON COLUMN openrisow.tbsss_schedules.last_run_at IS 'Data e hora em que ocorreu o ultimo disparo';
COMMENT ON COLUMN openrisow.tbsss_schedules.last_ticket_id IS 'Identificador do ticket mais recente gerado por esta regra';
COMMENT ON COLUMN openrisow.tbsss_schedules.pause_reason IS 'Motivo formal em caso de suspensao da regra (ex: USER_INACTIVE, MANUAL)';
COMMENT ON COLUMN openrisow.tbsss_schedules.active IS 'Indicador de vigencia da regra (Y=Ativo, N=Pausado/Concluido)';
COMMENT ON COLUMN openrisow.tbsss_schedules.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_schedules.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_schedules.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_schedules.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_tickets IS 'Fila de execucao, ciclo de vida e historico de execucao de scripts';
COMMENT ON COLUMN openrisow.tbsss_tickets.id IS 'Identificador unico sequencial do ticket de execucao (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_tickets.script_id IS 'Identificador da rotina solicitada (FK para tbsss_scripts)';
COMMENT ON COLUMN openrisow.tbsss_tickets.environment IS 'Nome do ambiente alvo da execucao (FK para tbsss_environments)';
COMMENT ON COLUMN openrisow.tbsss_tickets.requested_by IS 'Login do operador que solicitou a execucao (FK para tbsss_users)';
COMMENT ON COLUMN openrisow.tbsss_tickets.source_ip IS 'Endereco IP do cliente que originou o pedido';
COMMENT ON COLUMN openrisow.tbsss_tickets.agent_id IS 'Identificador do daemon do agente que executou o ticket';
COMMENT ON COLUMN openrisow.tbsss_tickets.process_id IS 'Identificador do processo (PID) no sistema operacional do servidor';
COMMENT ON COLUMN openrisow.tbsss_tickets.process_start IS 'Coluna process_start da tabela tbsss_tickets';
COMMENT ON COLUMN openrisow.tbsss_tickets.status IS 'Situacao da execucao (PENDING, RUNNING, SUCCESS, FAILED, CANCELLED)';
COMMENT ON COLUMN openrisow.tbsss_tickets.priority IS 'Prioridade de atendimento na fila (1=Critico, 2=Alta, 3=Normal, 4=Baixa)';
COMMENT ON COLUMN openrisow.tbsss_tickets.cancel_requested IS 'Indicador se o cancelamento foi requisitado pelo operador (Y/N)';
COMMENT ON COLUMN openrisow.tbsss_tickets.status_reason IS 'Codigo tecnico do motivo de falha ou cancelamento';
COMMENT ON COLUMN openrisow.tbsss_tickets.parent_ticket_id IS 'Identificador do ticket pai em caso de reexecucao';
COMMENT ON COLUMN openrisow.tbsss_tickets.schedule_id IS 'Identificador da regra de agendamento de origem (se houver)';
COMMENT ON COLUMN openrisow.tbsss_tickets.submitted_params IS 'Copia fiel dos parametros de entrada fornecidos na solicitacao (CLOB)';
COMMENT ON COLUMN openrisow.tbsss_tickets.log_output IS 'Saida completa de execucao capturada de stdout/stderr (CLOB)';
COMMENT ON COLUMN openrisow.tbsss_tickets.log_offset_chars IS 'Controle tecnico de caracteres confirmados gravados no log';
COMMENT ON COLUMN openrisow.tbsss_tickets.log_truncated IS 'Indicador se o log excedeu o limite maximo de tamanho (Y/N)';
COMMENT ON COLUMN openrisow.tbsss_tickets.return_code IS 'Coluna return_code da tabela tbsss_tickets';
COMMENT ON COLUMN openrisow.tbsss_tickets.scheduled_at IS 'Data e hora agendadas para o processamento';
COMMENT ON COLUMN openrisow.tbsss_tickets.started_at IS 'Data e hora efetivas do inicio da execucao pelo agente';
COMMENT ON COLUMN openrisow.tbsss_tickets.heartbeat_at IS 'Data e hora da ultima confirmacao de atividade do processo';
COMMENT ON COLUMN openrisow.tbsss_tickets.finished_at IS 'Data e hora de conclusao ou encerramento da execucao';
COMMENT ON COLUMN openrisow.tbsss_tickets.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_tickets.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_tickets.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_tickets.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_ticket_answer IS 'Valores individuais preenchidos para cada parametro no disparo do ticket';
COMMENT ON COLUMN openrisow.tbsss_ticket_answer.id IS 'Identificador unico sequencial da resposta (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_ticket_answer.ticket_id IS 'Identificador do ticket correspondente (FK para tbsss_tickets)';
COMMENT ON COLUMN openrisow.tbsss_ticket_answer.parameter_id IS 'Identificador do parametro respondido (FK para tbsss_parameters)';
COMMENT ON COLUMN openrisow.tbsss_ticket_answer.answer_value IS 'Coluna answer_value da tabela tbsss_ticket_answer';
COMMENT ON COLUMN openrisow.tbsss_ticket_answer.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_ticket_answer.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_ticket_answer.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_ticket_answer.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_agents IS 'Registro, versao e sinais de vida dos daemons executores instalados';
COMMENT ON COLUMN openrisow.tbsss_agents.id IS 'Identificador unico sequencial do agente (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_agents.code IS 'Codigo identificador unico do agente (ex: agt-node01)';
COMMENT ON COLUMN openrisow.tbsss_agents.hostname IS 'Nome de rede (hostname) da maquina servidora do agente';
COMMENT ON COLUMN openrisow.tbsss_agents.daemon_pid IS 'Identificador de processo (PID) do daemon no servidor';
COMMENT ON COLUMN openrisow.tbsss_agents.version IS 'Versao do software do servico em execucao no agente';
COMMENT ON COLUMN openrisow.tbsss_agents.environments IS 'Lista separada por virgulas dos ambientes atendidos por este no';
COMMENT ON COLUMN openrisow.tbsss_agents.platform IS 'Sistema operacional da maquina servidora (POSIX)';
COMMENT ON COLUMN openrisow.tbsss_agents.interpreters IS 'Interpretadores homologados disponiveis no servidor (PYTHON3, BASH, SH)';
COMMENT ON COLUMN openrisow.tbsss_agents.status IS 'Estado de operacao do no (ACTIVE, STOPPED)';
COMMENT ON COLUMN openrisow.tbsss_agents.started_at IS 'Data e hora de inicializacao do daemon';
COMMENT ON COLUMN openrisow.tbsss_agents.heartbeat_at IS 'Data e hora do sinal periodico de disponibilidade mais recente';
COMMENT ON COLUMN openrisow.tbsss_agents.critical_config IS 'Coluna critical_config da tabela tbsss_agents';
COMMENT ON COLUMN openrisow.tbsss_agents.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_agents.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_agents.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_agents.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_audit IS 'Trilha de auditoria imutavel para conformidade e rastreabilidade';
COMMENT ON COLUMN openrisow.tbsss_audit.id IS 'Identificador unico sequencial do evento de auditoria (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_audit.actor IS 'Identificador do operador ou servico que executou a acao';
COMMENT ON COLUMN openrisow.tbsss_audit.source_ip IS 'Endereco IP do cliente que solicitou a operacao';
COMMENT ON COLUMN openrisow.tbsss_audit.action IS 'Codigo mnemonico da acao executada (ex: CREATE, TICKET_CREATE)';
COMMENT ON COLUMN openrisow.tbsss_audit.entity IS 'Nome da tabela ou entidade alvo afetada';
COMMENT ON COLUMN openrisow.tbsss_audit.entity_id IS 'Identificador numerico do registro alvo afetado';
COMMENT ON COLUMN openrisow.tbsss_audit.detail IS 'Texto descritivo ou dados em formato estruturado sobre o evento';
COMMENT ON COLUMN openrisow.tbsss_audit.created_at IS 'Data e hora exatas da realizacao do evento auditado';
COMMENT ON TABLE openrisow.tbsss_control IS 'Parametros de controle global, versao de esquema e concessao de limpeza';
COMMENT ON COLUMN openrisow.tbsss_control.id IS 'Identificador unico da linha de controle global (sempre 1)';
COMMENT ON COLUMN openrisow.tbsss_control.schema_version IS 'Numero da versao estrutural do banco de dados atualmente instalada';
COMMENT ON COLUMN openrisow.tbsss_control.version_applied_at IS 'Data e hora de aplicacao da versao de esquema atual';
COMMENT ON COLUMN openrisow.tbsss_control.version_applied_by IS 'Identificador de quem realizou a aplicacao do esquema';
COMMENT ON COLUMN openrisow.tbsss_control.purge_owner IS 'Identificador do no que detem a concessao de purga de dados';
COMMENT ON COLUMN openrisow.tbsss_control.purge_lease_until IS 'Data e hora limite de expiracao da concessao de purga';
COMMENT ON TABLE openrisow.tbsss_ticket_output IS 'Zip da pasta de saida de cada ticket, gravado pelo agente (CR-012)';
COMMENT ON COLUMN openrisow.tbsss_ticket_output.id IS 'Identificador unico sequencial da saida (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_ticket_output.ticket_id IS 'Ticket dono da saida (FK para tbsss_tickets, removida em cascata)';
COMMENT ON COLUMN openrisow.tbsss_ticket_output.state IS 'Situacao do zip (WRITING, AVAILABLE, EXCEEDED, FAILED)';
COMMENT ON COLUMN openrisow.tbsss_ticket_output.reason IS 'Motivo de EXCEEDED ou FAILED (FILES, BYTES, DEADLINE, ERROR)';
COMMENT ON COLUMN openrisow.tbsss_ticket_output.agent_id IS 'Agente que executou o ticket e em cujo servidor a pasta de saida ficou';
COMMENT ON COLUMN openrisow.tbsss_ticket_output.file_count IS 'Quantidade de arquivos no zip';
COMMENT ON COLUMN openrisow.tbsss_ticket_output.size_bytes IS 'Tamanho do zip em bytes';
COMMENT ON COLUMN openrisow.tbsss_ticket_output.content IS 'Zip da pasta de saida do script (BLOB)';
COMMENT ON COLUMN openrisow.tbsss_ticket_output.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_ticket_output.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_ticket_output.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_ticket_output.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_input_upload IS 'Arquivos enviados pela tela para a pasta de entrada dos scripts (CR-020)';
COMMENT ON COLUMN openrisow.tbsss_input_upload.id IS 'Identificador unico sequencial do envio (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_input_upload.environment IS 'Ambiente de destino (FK para tbsss_environments)';
COMMENT ON COLUMN openrisow.tbsss_input_upload.script_id IS 'Script dono da pasta de entrada de destino (FK para tbsss_scripts)';
COMMENT ON COLUMN openrisow.tbsss_input_upload.relative_dir IS 'Subpasta dentro da pasta do script; nulo e a propria pasta';
COMMENT ON COLUMN openrisow.tbsss_input_upload.file_name IS 'Nome do arquivo na pasta de entrada';
COMMENT ON COLUMN openrisow.tbsss_input_upload.size_bytes IS 'Tamanho do arquivo em bytes';
COMMENT ON COLUMN openrisow.tbsss_input_upload.sha256 IS 'Hash SHA-256 do conteudo, conferido pelo agente na entrega';
COMMENT ON COLUMN openrisow.tbsss_input_upload.replace_existing IS 'Se pode substituir um arquivo com o mesmo nome (Y ou N)';
COMMENT ON COLUMN openrisow.tbsss_input_upload.source_ip IS 'Endereco IP de quem enviou';
COMMENT ON COLUMN openrisow.tbsss_input_upload.content IS 'Conteudo do arquivo (BLOB), esvaziado pelo purge depois das entregas';
COMMENT ON COLUMN openrisow.tbsss_input_upload.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_input_upload.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_input_upload.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_input_upload.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_input_delivery IS 'Entrega de cada envio a cada agente que atende o ambiente (CR-020)';
COMMENT ON COLUMN openrisow.tbsss_input_delivery.id IS 'Identificador unico sequencial da entrega (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_input_delivery.upload_id IS 'Envio entregue (FK para tbsss_input_upload, removida em cascata)';
COMMENT ON COLUMN openrisow.tbsss_input_delivery.agent_id IS 'Agente que deve gravar o arquivo na sua pasta de entrada';
COMMENT ON COLUMN openrisow.tbsss_input_delivery.state IS 'Situacao da entrega (PENDING, DELIVERED, FAILED)';
COMMENT ON COLUMN openrisow.tbsss_input_delivery.reason IS 'Motivo da falha (EXISTS, NAME, SPACE, HASH, ERROR)';
COMMENT ON COLUMN openrisow.tbsss_input_delivery.delivered_at IS 'Data e hora em que o agente concluiu a entrega';
COMMENT ON COLUMN openrisow.tbsss_input_delivery.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_input_delivery.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_input_delivery.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_input_delivery.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';
COMMENT ON TABLE openrisow.tbsss_input_listing IS 'Retrato das pastas de entrada gerado por cada agente (CR-020)';
COMMENT ON COLUMN openrisow.tbsss_input_listing.id IS 'Identificador unico sequencial do retrato (chave primaria)';
COMMENT ON COLUMN openrisow.tbsss_input_listing.agent_id IS 'Agente que gerou o retrato da sua pasta de entrada';
COMMENT ON COLUMN openrisow.tbsss_input_listing.environment IS 'Ambiente da pasta (FK para tbsss_environments)';
COMMENT ON COLUMN openrisow.tbsss_input_listing.script_id IS 'Script dono da pasta (FK para tbsss_scripts)';
COMMENT ON COLUMN openrisow.tbsss_input_listing.listing IS 'Arquivos da pasta em JSON (caminho, tamanho e data), com teto de itens';
COMMENT ON COLUMN openrisow.tbsss_input_listing.file_count IS 'Quantidade de arquivos na pasta';
COMMENT ON COLUMN openrisow.tbsss_input_listing.truncated IS 'Se a lista passou do teto de itens (Y ou N)';
COMMENT ON COLUMN openrisow.tbsss_input_listing.listed_at IS 'Data e hora do retrato';
COMMENT ON COLUMN openrisow.tbsss_input_listing.refresh_requested_at IS 'Data e hora em que a tela pediu um retrato novo';
COMMENT ON COLUMN openrisow.tbsss_input_listing.created_at IS 'Data e hora da criacao do registro no banco de dados (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_input_listing.created_by IS 'Identificador do usuario ou servico responsavel pela criacao (imutavel)';
COMMENT ON COLUMN openrisow.tbsss_input_listing.updated_at IS 'Data e hora da ultima alteracao de negocio (nulo ate a primeira alteracao)';
COMMENT ON COLUMN openrisow.tbsss_input_listing.updated_by IS 'Identificador do usuario ou servico responsavel pela ultima alteracao';


-- ------------------------------------------------------------------------------
-- FASE 7: SEED INICIAL (MERGE IDEMPOTENTE)
-- ------------------------------------------------------------------------------

MERGE INTO openrisow.tbsss_features dst
USING (SELECT 'EXEC_SCRIPT' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Rodar Scripts',
             dst.module = 'OPERATION',
             dst.description = 'Preencher questionários e abrir tickets',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR dst.name <> 'Rodar Scripts'
     OR dst.module <> 'OPERATION'
     OR dst.description <> 'Preencher questionários e abrir tickets'
WHEN NOT MATCHED THEN
  INSERT (id, code, module, name, description, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_features.NEXTVAL, 'EXEC_SCRIPT', 'OPERATION', 'Rodar Scripts', 'Preencher questionários e abrir tickets', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_features dst
USING (SELECT 'VIEW_LOGS' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Consultar Tickets',
             dst.module = 'OPERATION',
             dst.description = 'Acompanhar os tickets e ler o log em tempo quase real',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR dst.name <> 'Consultar Tickets'
     OR dst.module <> 'OPERATION'
     OR dst.description <> 'Acompanhar os tickets e ler o log em tempo quase real'
WHEN NOT MATCHED THEN
  INSERT (id, code, module, name, description, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_features.NEXTVAL, 'VIEW_LOGS', 'OPERATION', 'Consultar Tickets', 'Acompanhar os tickets e ler o log em tempo quase real', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_features dst
USING (SELECT 'CANCEL_TICKET' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Cancelar Tickets',
             dst.module = 'OPERATION',
             dst.description = 'Cancelar tickets de terceiros nos ambientes consultados (com Consultar Tickets)',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR dst.name <> 'Cancelar Tickets'
     OR dst.module <> 'OPERATION'
     OR dst.description <> 'Cancelar tickets de terceiros nos ambientes consultados (com Consultar Tickets)'
WHEN NOT MATCHED THEN
  INSERT (id, code, module, name, description, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_features.NEXTVAL, 'CANCEL_TICKET', 'OPERATION', 'Cancelar Tickets', 'Cancelar tickets de terceiros nos ambientes consultados (com Consultar Tickets)', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_features dst
USING (SELECT 'DOWNLOAD_OUTPUT' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Baixar Saídas',
             dst.module = 'OPERATION',
             dst.description = 'Navegar pelas saídas dos tickets nos ambientes do perfil e baixar o zip ou um arquivo',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR dst.name <> 'Baixar Saídas'
     OR dst.module <> 'OPERATION'
     OR dst.description <> 'Navegar pelas saídas dos tickets nos ambientes do perfil e baixar o zip ou um arquivo'
WHEN NOT MATCHED THEN
  INSERT (id, code, module, name, description, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_features.NEXTVAL, 'DOWNLOAD_OUTPUT', 'OPERATION', 'Baixar Saídas', 'Navegar pelas saídas dos tickets nos ambientes do perfil e baixar o zip ou um arquivo', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_features dst
USING (SELECT 'MANAGE_USERS' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Gestão de Usuários',
             dst.module = 'ADMIN',
             dst.description = 'Gerenciar operadores e credenciais',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR dst.name <> 'Gestão de Usuários'
     OR dst.module <> 'ADMIN'
     OR dst.description <> 'Gerenciar operadores e credenciais'
WHEN NOT MATCHED THEN
  INSERT (id, code, module, name, description, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_features.NEXTVAL, 'MANAGE_USERS', 'ADMIN', 'Gestão de Usuários', 'Gerenciar operadores e credenciais', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_features dst
USING (SELECT 'MANAGE_PROFILES' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Gestão de Perfis',
             dst.module = 'ADMIN',
             dst.description = 'Gerenciar perfis e matrizes de permissão',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR dst.name <> 'Gestão de Perfis'
     OR dst.module <> 'ADMIN'
     OR dst.description <> 'Gerenciar perfis e matrizes de permissão'
WHEN NOT MATCHED THEN
  INSERT (id, code, module, name, description, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_features.NEXTVAL, 'MANAGE_PROFILES', 'ADMIN', 'Gestão de Perfis', 'Gerenciar perfis e matrizes de permissão', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_features dst
USING (SELECT 'MANAGE_ENVIRONMENTS' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Gestão de Ambientes',
             dst.module = 'ADMIN',
             dst.description = 'Gerenciar ambientes e DSNs',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR dst.name <> 'Gestão de Ambientes'
     OR dst.module <> 'ADMIN'
     OR dst.description <> 'Gerenciar ambientes e DSNs'
WHEN NOT MATCHED THEN
  INSERT (id, code, module, name, description, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_features.NEXTVAL, 'MANAGE_ENVIRONMENTS', 'ADMIN', 'Gestão de Ambientes', 'Gerenciar ambientes e DSNs', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_features dst
USING (SELECT 'MANAGE_SCRIPTS' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Gestão de Scripts',
             dst.module = 'ADMIN',
             dst.description = 'Cadastrar rotinas e homologação por ambiente',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR dst.name <> 'Gestão de Scripts'
     OR dst.module <> 'ADMIN'
     OR dst.description <> 'Cadastrar rotinas e homologação por ambiente'
WHEN NOT MATCHED THEN
  INSERT (id, code, module, name, description, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_features.NEXTVAL, 'MANAGE_SCRIPTS', 'ADMIN', 'Gestão de Scripts', 'Cadastrar rotinas e homologação por ambiente', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_features dst
USING (SELECT 'MANAGE_PARAMETERS' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Dicionário de Parâmetros',
             dst.module = 'ADMIN',
             dst.description = 'Gerenciar perguntas e flags reutilizáveis',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR dst.name <> 'Dicionário de Parâmetros'
     OR dst.module <> 'ADMIN'
     OR dst.description <> 'Gerenciar perguntas e flags reutilizáveis'
WHEN NOT MATCHED THEN
  INSERT (id, code, module, name, description, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_features.NEXTVAL, 'MANAGE_PARAMETERS', 'ADMIN', 'Dicionário de Parâmetros', 'Gerenciar perguntas e flags reutilizáveis', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_features dst
USING (SELECT 'MANAGE_SCHEDULES' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Regras de Agendamento',
             dst.module = 'ADMIN',
             dst.description = 'Criar e gerenciar recorrências',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR dst.name <> 'Regras de Agendamento'
     OR dst.module <> 'ADMIN'
     OR dst.description <> 'Criar e gerenciar recorrências'
WHEN NOT MATCHED THEN
  INSERT (id, code, module, name, description, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_features.NEXTVAL, 'MANAGE_SCHEDULES', 'ADMIN', 'Regras de Agendamento', 'Criar e gerenciar recorrências', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_features dst
USING (SELECT 'VIEW_AUDIT' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Auditoria',
             dst.module = 'ADMIN',
             dst.description = 'Consultar a trilha de auditoria e os agentes',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR dst.name <> 'Auditoria'
     OR dst.module <> 'ADMIN'
     OR dst.description <> 'Consultar a trilha de auditoria e os agentes'
WHEN NOT MATCHED THEN
  INSERT (id, code, module, name, description, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_features.NEXTVAL, 'VIEW_AUDIT', 'ADMIN', 'Auditoria', 'Consultar a trilha de auditoria e os agentes', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_environments dst
USING (SELECT 'CLONE2' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'BRTLVLTS1199PL (10.238.10.209)',
             dst.connection = '10.238.55.146/gfprod',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'BRTLVLTS1199PL (10.238.10.209)'
     OR NVL(dst.connection, '~') <> '10.238.55.146/gfprod'
WHEN NOT MATCHED THEN
  INSERT (id, name, description, connection, active, is_production, created_at, created_by)
  VALUES (openrisow.sq_tbsss_environments.NEXTVAL, 'CLONE2', 'BRTLVLTS1199PL (10.238.10.209)', '10.238.55.146/gfprod', 'Y', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_environments dst
USING (SELECT 'CLONE1' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'BRTLVLTS1198PL (10.238.10.208)',
             dst.connection = '10.238.55.145/gfprod',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'BRTLVLTS1198PL (10.238.10.208)'
     OR NVL(dst.connection, '~') <> '10.238.55.145/gfprod'
WHEN NOT MATCHED THEN
  INSERT (id, name, description, connection, active, is_production, created_at, created_by)
  VALUES (openrisow.sq_tbsss_environments.NEXTVAL, 'CLONE1', 'BRTLVLTS1198PL (10.238.10.208)', '10.238.55.145/gfprod', 'Y', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_environments dst
USING (SELECT 'CLONE6' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'BRTLVLTS3089SL (10.238.10.210)',
             dst.connection = '10.238.45.230/svc_gfprodc6',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'BRTLVLTS3089SL (10.238.10.210)'
     OR NVL(dst.connection, '~') <> '10.238.45.230/svc_gfprodc6'
WHEN NOT MATCHED THEN
  INSERT (id, name, description, connection, active, is_production, created_at, created_by)
  VALUES (openrisow.sq_tbsss_environments.NEXTVAL, 'CLONE6', 'BRTLVLTS3089SL (10.238.10.210)', '10.238.45.230/svc_gfprodc6', 'Y', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_environments dst
USING (SELECT 'CLONE7' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'BRTLVLTS1216PL (10.238.10.109)',
             dst.connection = '10.238.45.230/svc_gfprodc7',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'BRTLVLTS1216PL (10.238.10.109)'
     OR NVL(dst.connection, '~') <> '10.238.45.230/svc_gfprodc7'
WHEN NOT MATCHED THEN
  INSERT (id, name, description, connection, active, is_production, created_at, created_by)
  VALUES (openrisow.sq_tbsss_environments.NEXTVAL, 'CLONE7', 'BRTLVLTS1216PL (10.238.10.109)', '10.238.45.230/svc_gfprodc7', 'Y', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_environments dst
USING (SELECT 'GFPREPROD' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'BRTLVLTY3067SL (10.129.177.188)',
             dst.connection = '10.129.177.188/GFPR',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'BRTLVLTY3067SL (10.129.177.188)'
     OR NVL(dst.connection, '~') <> '10.129.177.188/GFPR'
WHEN NOT MATCHED THEN
  INSERT (id, name, description, connection, active, is_production, created_at, created_by)
  VALUES (openrisow.sq_tbsss_environments.NEXTVAL, 'GFPREPROD', 'BRTLVLTY3067SL (10.129.177.188)', '10.129.177.188/GFPR', 'Y', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profiles dst
USING (SELECT 'ADMINISTRATOR' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Acesso irrestrito a todas as funcionalidades e ambientes',
             dst.is_admin = 'Y',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.is_admin <> 'Y'
     OR dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Acesso irrestrito a todas as funcionalidades e ambientes'
WHEN NOT MATCHED THEN
  INSERT (id, name, description, is_admin, perm_version, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profiles.NEXTVAL, 'ADMINISTRATOR', 'Acesso irrestrito a todas as funcionalidades e ambientes', 'Y', 1, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'ADMINISTRATOR' AND f.code = 'EXEC_SCRIPT'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'ADMINISTRATOR' AND f.code = 'VIEW_LOGS'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'ADMINISTRATOR' AND f.code = 'CANCEL_TICKET'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'ADMINISTRATOR' AND f.code = 'DOWNLOAD_OUTPUT'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'ADMINISTRATOR' AND f.code = 'MANAGE_USERS'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'ADMINISTRATOR' AND f.code = 'MANAGE_PROFILES'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'ADMINISTRATOR' AND f.code = 'MANAGE_ENVIRONMENTS'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'ADMINISTRATOR' AND f.code = 'MANAGE_SCRIPTS'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'ADMINISTRATOR' AND f.code = 'MANAGE_PARAMETERS'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'ADMINISTRATOR' AND f.code = 'MANAGE_SCHEDULES'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'ADMINISTRATOR' AND f.code = 'VIEW_AUDIT'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'ADMINISTRATOR' AND a.name = 'CLONE2'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'ADMINISTRATOR' AND a.name = 'CLONE1'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'ADMINISTRATOR' AND a.name = 'CLONE6'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'ADMINISTRATOR' AND a.name = 'CLONE7'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'ADMINISTRATOR' AND a.name = 'GFPREPROD'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profiles dst
USING (SELECT 'OPERATOR_PROD' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Operador de Ambientes de Producao',
             dst.is_admin = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.is_admin <> 'N'
     OR dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Operador de Ambientes de Producao'
WHEN NOT MATCHED THEN
  INSERT (id, name, description, is_admin, perm_version, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profiles.NEXTVAL, 'OPERATOR_PROD', 'Operador de Ambientes de Producao', 'N', 1, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'OPERATOR_PROD' AND f.code = 'EXEC_SCRIPT'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'OPERATOR_PROD' AND f.code = 'VIEW_LOGS'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'OPERATOR_PROD' AND f.code = 'CANCEL_TICKET'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'OPERATOR_PROD' AND f.code = 'DOWNLOAD_OUTPUT'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'OPERATOR_PROD' AND a.name = 'CLONE2'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'OPERATOR_PROD' AND a.name = 'CLONE1'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'OPERATOR_PROD' AND a.name = 'CLONE6'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'OPERATOR_PROD' AND a.name = 'CLONE7'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'OPERATOR_PROD' AND a.name = 'GFPREPROD'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profiles dst
USING (SELECT 'OPERATOR_HML' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Operador de Ambientes de Homologacao',
             dst.is_admin = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.is_admin <> 'N'
     OR dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Operador de Ambientes de Homologacao'
WHEN NOT MATCHED THEN
  INSERT (id, name, description, is_admin, perm_version, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profiles.NEXTVAL, 'OPERATOR_HML', 'Operador de Ambientes de Homologacao', 'N', 1, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'OPERATOR_HML' AND f.code = 'EXEC_SCRIPT'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'OPERATOR_HML' AND f.code = 'VIEW_LOGS'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'OPERATOR_HML' AND f.code = 'CANCEL_TICKET'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'OPERATOR_HML' AND f.code = 'DOWNLOAD_OUTPUT'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'OPERATOR_HML' AND a.name = 'CLONE6'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'OPERATOR_HML' AND a.name = 'CLONE7'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'OPERATOR_HML' AND a.name = 'GFPREPROD'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profiles dst
USING (SELECT 'READ_ONLY' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Perfil de Apenas Leitura e Consulta',
             dst.is_admin = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.is_admin <> 'N'
     OR dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Perfil de Apenas Leitura e Consulta'
WHEN NOT MATCHED THEN
  INSERT (id, name, description, is_admin, perm_version, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profiles.NEXTVAL, 'READ_ONLY', 'Perfil de Apenas Leitura e Consulta', 'N', 1, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_feature dst
USING (
  SELECT p.id AS profile_id, f.id AS feature_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_features f
   WHERE p.name = 'READ_ONLY' AND f.code = 'VIEW_LOGS'
) src
ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, feature_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_feature.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'READ_ONLY' AND a.name = 'CLONE2'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'READ_ONLY' AND a.name = 'CLONE1'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'READ_ONLY' AND a.name = 'CLONE6'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'READ_ONLY' AND a.name = 'CLONE7'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_env dst
USING (
  SELECT p.id AS profile_id, a.id AS environment_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_environments a
   WHERE p.name = 'READ_ONLY' AND a.name = 'GFPREPROD'
) src
ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_env.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'arq_origem' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--origem',
             dst.label = 'Arquivo ou Pasta de Origem',
             dst.description = 'Caminho do arquivo ou pasta a ser processado',
             dst.component_type = 'TEXT',
             dst.options_json = NULL,
             dst.default_value = NULL,
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--origem', '~')
     OR dst.label <> 'Arquivo ou Pasta de Origem'
     OR NVL(dst.description, '~') <> 'Caminho do arquivo ou pasta a ser processado'
     OR dst.component_type <> 'TEXT'
     OR NVL(dst.options_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.default_value, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'arq_origem', '--origem', 'Arquivo ou Pasta de Origem', 'Caminho do arquivo ou pasta a ser processado', 'TEXT', NULL, NULL, NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'arq_destino' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--destino',
             dst.label = 'Arquivo ou Pasta de Destino',
             dst.description = 'Caminho do arquivo de saida ou diretorio destino',
             dst.component_type = 'TEXT',
             dst.options_json = NULL,
             dst.default_value = NULL,
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--destino', '~')
     OR dst.label <> 'Arquivo ou Pasta de Destino'
     OR NVL(dst.description, '~') <> 'Caminho do arquivo de saida ou diretorio destino'
     OR dst.component_type <> 'TEXT'
     OR NVL(dst.options_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.default_value, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'arq_destino', '--destino', 'Arquivo ou Pasta de Destino', 'Caminho do arquivo de saida ou diretorio destino', 'TEXT', NULL, NULL, NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'arq_zip' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--arquivo-zip',
             dst.label = 'Arquivo ZIP',
             dst.description = 'Caminho do pacote compactado .zip',
             dst.component_type = 'TEXT',
             dst.options_json = NULL,
             dst.default_value = NULL,
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--arquivo-zip', '~')
     OR dst.label <> 'Arquivo ZIP'
     OR NVL(dst.description, '~') <> 'Caminho do pacote compactado .zip'
     OR dst.component_type <> 'TEXT'
     OR NVL(dst.options_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.default_value, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'arq_zip', '--arquivo-zip', 'Arquivo ZIP', 'Caminho do pacote compactado .zip', 'TEXT', NULL, NULL, NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'arq_tar' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--arquivo-tar',
             dst.label = 'Arquivo TAR.GZ',
             dst.description = 'Caminho do pacote compactado .tar.gz',
             dst.component_type = 'TEXT',
             dst.options_json = NULL,
             dst.default_value = NULL,
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--arquivo-tar', '~')
     OR dst.label <> 'Arquivo TAR.GZ'
     OR NVL(dst.description, '~') <> 'Caminho do pacote compactado .tar.gz'
     OR dst.component_type <> 'TEXT'
     OR NVL(dst.options_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.default_value, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'arq_tar', '--arquivo-tar', 'Arquivo TAR.GZ', 'Caminho do pacote compactado .tar.gz', 'TEXT', NULL, NULL, NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'nivel_compressao' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--nivel',
             dst.label = 'Nivel de Compressao (1-9)',
             dst.description = 'Nivel de compactacao zlib de 1 (rapido) a 9 (maximo)',
             dst.component_type = 'NUMBER',
             dst.options_json = NULL,
             dst.default_value = '6',
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--nivel', '~')
     OR dst.label <> 'Nivel de Compressao (1-9)'
     OR NVL(dst.description, '~') <> 'Nivel de compactacao zlib de 1 (rapido) a 9 (maximo)'
     OR dst.component_type <> 'NUMBER'
     OR NVL(dst.options_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.default_value, '~') <> NVL('6', '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'nivel_compressao', '--nivel', 'Nivel de Compressao (1-9)', 'Nivel de compactacao zlib de 1 (rapido) a 9 (maximo)', 'NUMBER', NULL, '6', NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'linhas_por_parte' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--linhas-por-parte',
             dst.label = 'Linhas por Parte',
             dst.description = 'Quantidade maxima de linhas em cada parte dividida',
             dst.component_type = 'NUMBER',
             dst.options_json = NULL,
             dst.default_value = '1000',
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--linhas-por-parte', '~')
     OR dst.label <> 'Linhas por Parte'
     OR NVL(dst.description, '~') <> 'Quantidade maxima de linhas em cada parte dividida'
     OR dst.component_type <> 'NUMBER'
     OR NVL(dst.options_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.default_value, '~') <> NVL('1000', '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'linhas_por_parte', '--linhas-por-parte', 'Linhas por Parte', 'Quantidade maxima de linhas em cada parte dividida', 'NUMBER', NULL, '1000', NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'prefixo_saida' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--prefixo-saida',
             dst.label = 'Prefixo dos Arquivos Gerados',
             dst.description = 'Prefixo do caminho das partes geradas',
             dst.component_type = 'TEXT',
             dst.options_json = NULL,
             dst.default_value = '/tmp/parte_',
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--prefixo-saida', '~')
     OR dst.label <> 'Prefixo dos Arquivos Gerados'
     OR NVL(dst.description, '~') <> 'Prefixo do caminho das partes geradas'
     OR dst.component_type <> 'TEXT'
     OR NVL(dst.options_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.default_value, '~') <> NVL('/tmp/parte_', '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'prefixo_saida', '--prefixo-saida', 'Prefixo dos Arquivos Gerados', 'Prefixo do caminho das partes geradas', 'TEXT', NULL, '/tmp/parte_', NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'padrao_origem' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--padrao-origem',
             dst.label = 'Padrao de Origem (Glob)',
             dst.description = 'Mascara glob dos arquivos a serem juntados (ex: /tmp/parte_*)',
             dst.component_type = 'TEXT',
             dst.options_json = NULL,
             dst.default_value = '/tmp/parte_*',
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--padrao-origem', '~')
     OR dst.label <> 'Padrao de Origem (Glob)'
     OR NVL(dst.description, '~') <> 'Mascara glob dos arquivos a serem juntados (ex: /tmp/parte_*)'
     OR dst.component_type <> 'TEXT'
     OR NVL(dst.options_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.default_value, '~') <> NVL('/tmp/parte_*', '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'padrao_origem', '--padrao-origem', 'Padrao de Origem (Glob)', 'Mascara glob dos arquivos a serem juntados (ex: /tmp/parte_*)', 'TEXT', NULL, '/tmp/parte_*', NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'enc_origem' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--enc-origem',
             dst.label = 'Codificacao de Origem',
             dst.description = 'Codificacao de caracteres atual do arquivo',
             dst.component_type = 'SELECT',
             dst.options_json = '{"ISO-8859-1":"ISO-8859-1 (Latin1)","UTF-8":"UTF-8","CP1252":"Windows CP1252","ASCII":"ASCII"}',
             dst.default_value = 'ISO-8859-1',
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--enc-origem', '~')
     OR dst.label <> 'Codificacao de Origem'
     OR NVL(dst.description, '~') <> 'Codificacao de caracteres atual do arquivo'
     OR dst.component_type <> 'SELECT'
     OR NVL(dst.options_json, '~') <> NVL('{"ISO-8859-1":"ISO-8859-1 (Latin1)","UTF-8":"UTF-8","CP1252":"Windows CP1252","ASCII":"ASCII"}', '~')
     OR NVL(dst.default_value, '~') <> NVL('ISO-8859-1', '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'enc_origem', '--enc-origem', 'Codificacao de Origem', 'Codificacao de caracteres atual do arquivo', 'SELECT', '{"ISO-8859-1":"ISO-8859-1 (Latin1)","UTF-8":"UTF-8","CP1252":"Windows CP1252","ASCII":"ASCII"}', 'ISO-8859-1', NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'enc_destino' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--enc-destino',
             dst.label = 'Codificacao de Destino',
             dst.description = 'Nova codificacao de caracteres desejada',
             dst.component_type = 'SELECT',
             dst.options_json = '{"UTF-8":"UTF-8","ISO-8859-1":"ISO-8859-1 (Latin1)","CP1252":"Windows CP1252"}',
             dst.default_value = 'UTF-8',
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--enc-destino', '~')
     OR dst.label <> 'Codificacao de Destino'
     OR NVL(dst.description, '~') <> 'Nova codificacao de caracteres desejada'
     OR dst.component_type <> 'SELECT'
     OR NVL(dst.options_json, '~') <> NVL('{"UTF-8":"UTF-8","ISO-8859-1":"ISO-8859-1 (Latin1)","CP1252":"Windows CP1252"}', '~')
     OR NVL(dst.default_value, '~') <> NVL('UTF-8', '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'enc_destino', '--enc-destino', 'Codificacao de Destino', 'Nova codificacao de caracteres desejada', 'SELECT', '{"UTF-8":"UTF-8","ISO-8859-1":"ISO-8859-1 (Latin1)","CP1252":"Windows CP1252"}', 'UTF-8', NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'termo_busca' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--busca',
             dst.label = 'Texto a Localizar',
             dst.description = 'String ou termo a ser pesquisado nas linhas',
             dst.component_type = 'TEXT',
             dst.options_json = NULL,
             dst.default_value = NULL,
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--busca', '~')
     OR dst.label <> 'Texto a Localizar'
     OR NVL(dst.description, '~') <> 'String ou termo a ser pesquisado nas linhas'
     OR dst.component_type <> 'TEXT'
     OR NVL(dst.options_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.default_value, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'termo_busca', '--busca', 'Texto a Localizar', 'String ou termo a ser pesquisado nas linhas', 'TEXT', NULL, NULL, NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'termo_substituicao' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--substituicao',
             dst.label = 'Texto Substituto',
             dst.description = 'Nova string que substituira o texto localizado',
             dst.component_type = 'TEXT',
             dst.options_json = NULL,
             dst.default_value = NULL,
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--substituicao', '~')
     OR dst.label <> 'Texto Substituto'
     OR NVL(dst.description, '~') <> 'Nova string que substituira o texto localizado'
     OR dst.component_type <> 'TEXT'
     OR NVL(dst.options_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.default_value, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'termo_substituicao', '--substituicao', 'Texto Substituto', 'Nova string que substituira o texto localizado', 'TEXT', NULL, NULL, NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'flag_ordenar' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--ordenar',
             dst.label = 'Ordenar Resultado',
             dst.description = 'Indica se deve ordenar alfabeticamente ou manter ordem',
             dst.component_type = 'SELECT',
             dst.options_json = '{"S":"Sim (Ordenar)","N":"Nao (Preservar ordem)"}',
             dst.default_value = 'S',
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--ordenar', '~')
     OR dst.label <> 'Ordenar Resultado'
     OR NVL(dst.description, '~') <> 'Indica se deve ordenar alfabeticamente ou manter ordem'
     OR dst.component_type <> 'SELECT'
     OR NVL(dst.options_json, '~') <> NVL('{"S":"Sim (Ordenar)","N":"Nao (Preservar ordem)"}', '~')
     OR NVL(dst.default_value, '~') <> NVL('S', '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'flag_ordenar', '--ordenar', 'Ordenar Resultado', 'Indica se deve ordenar alfabeticamente ou manter ordem', 'SELECT', '{"S":"Sim (Ordenar)","N":"Nao (Preservar ordem)"}', 'S', NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'tipo_hash' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--algoritmo',
             dst.label = 'Algoritmo de Hash',
             dst.description = 'Algoritmo criptografico de integridade',
             dst.component_type = 'SELECT',
             dst.options_json = '{"sha256":"SHA-256 (Recomendado)","md5":"MD5","sha1":"SHA-1"}',
             dst.default_value = 'sha256',
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--algoritmo', '~')
     OR dst.label <> 'Algoritmo de Hash'
     OR NVL(dst.description, '~') <> 'Algoritmo criptografico de integridade'
     OR dst.component_type <> 'SELECT'
     OR NVL(dst.options_json, '~') <> NVL('{"sha256":"SHA-256 (Recomendado)","md5":"MD5","sha1":"SHA-1"}', '~')
     OR NVL(dst.default_value, '~') <> NVL('sha256', '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'tipo_hash', '--algoritmo', 'Algoritmo de Hash', 'Algoritmo criptografico de integridade', 'SELECT', '{"sha256":"SHA-256 (Recomendado)","md5":"MD5","sha1":"SHA-1"}', 'sha256', NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'termo_filtro' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--padrao',
             dst.label = 'Padrao de Filtragem',
             dst.description = 'Texto a ser filtrado nas linhas do arquivo',
             dst.component_type = 'TEXT',
             dst.options_json = NULL,
             dst.default_value = NULL,
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--padrao', '~')
     OR dst.label <> 'Padrao de Filtragem'
     OR NVL(dst.description, '~') <> 'Texto a ser filtrado nas linhas do arquivo'
     OR dst.component_type <> 'TEXT'
     OR NVL(dst.options_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.default_value, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'termo_filtro', '--padrao', 'Padrao de Filtragem', 'Texto a ser filtrado nas linhas do arquivo', 'TEXT', NULL, NULL, NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'flag_inverter' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--inverter',
             dst.label = 'Inverter Selecao',
             dst.description = 'Se ativado, seleciona as linhas que nao possuem o padrao',
             dst.component_type = 'SELECT',
             dst.options_json = '{"N":"Nao (Manter correspondencias)","S":"Sim (Excluir correspondencias)"}',
             dst.default_value = 'N',
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--inverter', '~')
     OR dst.label <> 'Inverter Selecao'
     OR NVL(dst.description, '~') <> 'Se ativado, seleciona as linhas que nao possuem o padrao'
     OR dst.component_type <> 'SELECT'
     OR NVL(dst.options_json, '~') <> NVL('{"N":"Nao (Manter correspondencias)","S":"Sim (Excluir correspondencias)"}', '~')
     OR NVL(dst.default_value, '~') <> NVL('N', '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'flag_inverter', '--inverter', 'Inverter Selecao', 'Se ativado, seleciona as linhas que nao possuem o padrao', 'SELECT', '{"N":"Nao (Manter correspondencias)","S":"Sim (Excluir correspondencias)"}', 'N', NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'flag_numerico' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--numerico',
             dst.label = 'Ordenacao Numerica',
             dst.description = 'Trata o inicio das linhas como valor numerico',
             dst.component_type = 'SELECT',
             dst.options_json = '{"N":"Nao (Alfanumerica)","S":"Sim (Numerica)"}',
             dst.default_value = 'N',
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--numerico', '~')
     OR dst.label <> 'Ordenacao Numerica'
     OR NVL(dst.description, '~') <> 'Trata o inicio das linhas como valor numerico'
     OR dst.component_type <> 'SELECT'
     OR NVL(dst.options_json, '~') <> NVL('{"N":"Nao (Alfanumerica)","S":"Sim (Numerica)"}', '~')
     OR NVL(dst.default_value, '~') <> NVL('N', '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'flag_numerico', '--numerico', 'Ordenacao Numerica', 'Trata o inicio das linhas como valor numerico', 'SELECT', '{"N":"Nao (Alfanumerica)","S":"Sim (Numerica)"}', 'N', NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'flag_reverso' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = '--reverso',
             dst.label = 'Ordem Reversa (Decrescente)',
             dst.description = 'Ordena de tras para frente',
             dst.component_type = 'SELECT',
             dst.options_json = '{"N":"Nao (Crescente)","S":"Sim (Decrescente)"}',
             dst.default_value = 'N',
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL('--reverso', '~')
     OR dst.label <> 'Ordem Reversa (Decrescente)'
     OR NVL(dst.description, '~') <> 'Ordena de tras para frente'
     OR dst.component_type <> 'SELECT'
     OR NVL(dst.options_json, '~') <> NVL('{"N":"Nao (Crescente)","S":"Sim (Decrescente)"}', '~')
     OR NVL(dst.default_value, '~') <> NVL('N', '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'flag_reverso', '--reverso', 'Ordem Reversa (Decrescente)', 'Ordena de tras para frente', 'SELECT', '{"N":"Nao (Crescente)","S":"Sim (Decrescente)"}', 'N', NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_parameters dst
USING (SELECT 'caminho_arquivo' AS code FROM DUAL) src
ON (dst.code = src.code)
WHEN MATCHED THEN
  UPDATE SET dst.param_flag = NULL,
             dst.label = 'Caminho do Arquivo',
             dst.description = 'Caminho do arquivo a ser analisado',
             dst.component_type = 'TEXT',
             dst.options_json = NULL,
             dst.default_value = NULL,
             dst.sensitive = 'N',
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.param_flag, '~') <> NVL(NULL, '~')
     OR dst.label <> 'Caminho do Arquivo'
     OR NVL(dst.description, '~') <> 'Caminho do arquivo a ser analisado'
     OR dst.component_type <> 'TEXT'
     OR NVL(dst.options_json, '~') <> NVL(NULL, '~')
     OR NVL(dst.default_value, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_parameters.NEXTVAL, 'caminho_arquivo', NULL, 'Caminho do Arquivo', 'Caminho do arquivo a ser analisado', 'TEXT', NULL, NULL, NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'zipar_arquivos' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Compacta arquivo ou pasta em formato ZIP',
             dst.script_group = 'UTILITARIOS',
             dst.category = 'ARQUIVOS',
             dst.stage = 'COMPACTACAO',
             dst.interpreter = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/zipar_arquivos.py',
             dst.param_type = 'NAMED',
             dst.max_parallel_env = 2,
             dst.timeout_s = 1800,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Compacta arquivo ou pasta em formato ZIP'
     OR NVL(dst.script_group, '~') <> 'UTILITARIOS'
     OR NVL(dst.category, '~') <> 'ARQUIVOS'
     OR NVL(dst.stage, '~') <> 'COMPACTACAO'
     OR dst.interpreter <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/zipar_arquivos.py'
     OR dst.param_type <> 'NAMED'
     OR dst.max_parallel_env <> 2
     OR NVL(dst.timeout_s, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'zipar_arquivos', 'Compacta arquivo ou pasta em formato ZIP', 'UTILITARIOS', 'ARQUIVOS', 'COMPACTACAO', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/zipar_arquivos.py', 'NAMED', 2, 1800, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'zipar_arquivos' AND a.name = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'zipar_arquivos' AND a.name = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'zipar_arquivos' AND a.name = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'zipar_arquivos' AND a.name = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'zipar_arquivos' AND a.name = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'ADMINISTRATOR' AND s.name = 'zipar_arquivos'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_PROD' AND s.name = 'zipar_arquivos'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_HML' AND s.name = 'zipar_arquivos'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'READ_ONLY' AND s.name = 'zipar_arquivos'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'zipar_arquivos' AND p.code = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 1,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 1
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 1, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'zipar_arquivos' AND p.code = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 2,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 2
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 2, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'zipar_arquivos' AND p.code = 'nivel_compressao'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 3,
             dst.required = 'N',
             dst.default_value_override = '6',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 3
     OR dst.required <> 'N'
     OR NVL(dst.default_value_override, '~') <> NVL('6', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 3, 'N', '6', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'descompactar_zip' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Extrai arquivos de pacote ZIP para pasta destino com protecao segura',
             dst.script_group = 'UTILITARIOS',
             dst.category = 'ARQUIVOS',
             dst.stage = 'DESCOMPACTACAO',
             dst.interpreter = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/descompactar_zip.py',
             dst.param_type = 'NAMED',
             dst.max_parallel_env = 2,
             dst.timeout_s = 1800,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Extrai arquivos de pacote ZIP para pasta destino com protecao segura'
     OR NVL(dst.script_group, '~') <> 'UTILITARIOS'
     OR NVL(dst.category, '~') <> 'ARQUIVOS'
     OR NVL(dst.stage, '~') <> 'DESCOMPACTACAO'
     OR dst.interpreter <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/descompactar_zip.py'
     OR dst.param_type <> 'NAMED'
     OR dst.max_parallel_env <> 2
     OR NVL(dst.timeout_s, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'descompactar_zip', 'Extrai arquivos de pacote ZIP para pasta destino com protecao segura', 'UTILITARIOS', 'ARQUIVOS', 'DESCOMPACTACAO', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/descompactar_zip.py', 'NAMED', 2, 1800, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'descompactar_zip' AND a.name = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'descompactar_zip' AND a.name = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'descompactar_zip' AND a.name = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'descompactar_zip' AND a.name = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'descompactar_zip' AND a.name = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'ADMINISTRATOR' AND s.name = 'descompactar_zip'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_PROD' AND s.name = 'descompactar_zip'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_HML' AND s.name = 'descompactar_zip'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'READ_ONLY' AND s.name = 'descompactar_zip'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'descompactar_zip' AND p.code = 'arq_zip'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 1,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 1
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 1, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'descompactar_zip' AND p.code = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 2,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 2
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 2, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'quebrar_arquivo' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Divide arquivo texto em partes menores por quantidade de linhas',
             dst.script_group = 'UTILITARIOS',
             dst.category = 'ARQUIVOS',
             dst.stage = 'DIVISAO',
             dst.interpreter = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/quebrar_arquivo.py',
             dst.param_type = 'NAMED',
             dst.max_parallel_env = 2,
             dst.timeout_s = 1800,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Divide arquivo texto em partes menores por quantidade de linhas'
     OR NVL(dst.script_group, '~') <> 'UTILITARIOS'
     OR NVL(dst.category, '~') <> 'ARQUIVOS'
     OR NVL(dst.stage, '~') <> 'DIVISAO'
     OR dst.interpreter <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/quebrar_arquivo.py'
     OR dst.param_type <> 'NAMED'
     OR dst.max_parallel_env <> 2
     OR NVL(dst.timeout_s, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'quebrar_arquivo', 'Divide arquivo texto em partes menores por quantidade de linhas', 'UTILITARIOS', 'ARQUIVOS', 'DIVISAO', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/quebrar_arquivo.py', 'NAMED', 2, 1800, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'quebrar_arquivo' AND a.name = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'quebrar_arquivo' AND a.name = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'quebrar_arquivo' AND a.name = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'quebrar_arquivo' AND a.name = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'quebrar_arquivo' AND a.name = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'ADMINISTRATOR' AND s.name = 'quebrar_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_PROD' AND s.name = 'quebrar_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_HML' AND s.name = 'quebrar_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'READ_ONLY' AND s.name = 'quebrar_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'quebrar_arquivo' AND p.code = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 1,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 1
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 1, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'quebrar_arquivo' AND p.code = 'linhas_por_parte'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 2,
             dst.required = 'N',
             dst.default_value_override = '1000',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 2
     OR dst.required <> 'N'
     OR NVL(dst.default_value_override, '~') <> NVL('1000', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 2, 'N', '1000', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'quebrar_arquivo' AND p.code = 'prefixo_saida'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 3,
             dst.required = 'N',
             dst.default_value_override = '/tmp/parte_',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 3
     OR dst.required <> 'N'
     OR NVL(dst.default_value_override, '~') <> NVL('/tmp/parte_', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 3, 'N', '/tmp/parte_', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'juntar_arquivos' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Concatena blocos de arquivos ordenados em arquivo consolidado final',
             dst.script_group = 'UTILITARIOS',
             dst.category = 'ARQUIVOS',
             dst.stage = 'CONCATENACAO',
             dst.interpreter = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/juntar_arquivos.py',
             dst.param_type = 'NAMED',
             dst.max_parallel_env = 2,
             dst.timeout_s = 1800,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Concatena blocos de arquivos ordenados em arquivo consolidado final'
     OR NVL(dst.script_group, '~') <> 'UTILITARIOS'
     OR NVL(dst.category, '~') <> 'ARQUIVOS'
     OR NVL(dst.stage, '~') <> 'CONCATENACAO'
     OR dst.interpreter <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/juntar_arquivos.py'
     OR dst.param_type <> 'NAMED'
     OR dst.max_parallel_env <> 2
     OR NVL(dst.timeout_s, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'juntar_arquivos', 'Concatena blocos de arquivos ordenados em arquivo consolidado final', 'UTILITARIOS', 'ARQUIVOS', 'CONCATENACAO', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/juntar_arquivos.py', 'NAMED', 2, 1800, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'juntar_arquivos' AND a.name = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'juntar_arquivos' AND a.name = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'juntar_arquivos' AND a.name = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'juntar_arquivos' AND a.name = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'juntar_arquivos' AND a.name = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'ADMINISTRATOR' AND s.name = 'juntar_arquivos'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_PROD' AND s.name = 'juntar_arquivos'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_HML' AND s.name = 'juntar_arquivos'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'READ_ONLY' AND s.name = 'juntar_arquivos'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'juntar_arquivos' AND p.code = 'padrao_origem'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 1,
             dst.required = 'Y',
             dst.default_value_override = '/tmp/parte_*',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 1
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL('/tmp/parte_*', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 1, 'Y', '/tmp/parte_*', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'juntar_arquivos' AND p.code = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 2,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 2
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 2, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'converter_encoding' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Converte codificacao de caracteres de arquivo texto (ex: ISO-8859-1 para UTF-8)',
             dst.script_group = 'UTILITARIOS',
             dst.category = 'ARQUIVOS',
             dst.stage = 'CONVERSAO',
             dst.interpreter = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/converter_encoding.py',
             dst.param_type = 'NAMED',
             dst.max_parallel_env = 2,
             dst.timeout_s = 1800,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Converte codificacao de caracteres de arquivo texto (ex: ISO-8859-1 para UTF-8)'
     OR NVL(dst.script_group, '~') <> 'UTILITARIOS'
     OR NVL(dst.category, '~') <> 'ARQUIVOS'
     OR NVL(dst.stage, '~') <> 'CONVERSAO'
     OR dst.interpreter <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/converter_encoding.py'
     OR dst.param_type <> 'NAMED'
     OR dst.max_parallel_env <> 2
     OR NVL(dst.timeout_s, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'converter_encoding', 'Converte codificacao de caracteres de arquivo texto (ex: ISO-8859-1 para UTF-8)', 'UTILITARIOS', 'ARQUIVOS', 'CONVERSAO', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/converter_encoding.py', 'NAMED', 2, 1800, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'converter_encoding' AND a.name = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'converter_encoding' AND a.name = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'converter_encoding' AND a.name = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'converter_encoding' AND a.name = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'converter_encoding' AND a.name = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'ADMINISTRATOR' AND s.name = 'converter_encoding'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_PROD' AND s.name = 'converter_encoding'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_HML' AND s.name = 'converter_encoding'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'READ_ONLY' AND s.name = 'converter_encoding'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'converter_encoding' AND p.code = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 1,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 1
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 1, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'converter_encoding' AND p.code = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 2,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 2
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 2, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'converter_encoding' AND p.code = 'enc_origem'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 3,
             dst.required = 'N',
             dst.default_value_override = 'ISO-8859-1',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 3
     OR dst.required <> 'N'
     OR NVL(dst.default_value_override, '~') <> NVL('ISO-8859-1', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 3, 'N', 'ISO-8859-1', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'converter_encoding' AND p.code = 'enc_destino'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 4,
             dst.required = 'N',
             dst.default_value_override = 'UTF-8',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 4
     OR dst.required <> 'N'
     OR NVL(dst.default_value_override, '~') <> NVL('UTF-8', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 4, 'N', 'UTF-8', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'substituir_texto' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Localiza e substitui texto em arquivo gerando copia atualizada',
             dst.script_group = 'UTILITARIOS',
             dst.category = 'ARQUIVOS',
             dst.stage = 'TRANSFORMACAO',
             dst.interpreter = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/substituir_texto.py',
             dst.param_type = 'NAMED',
             dst.max_parallel_env = 2,
             dst.timeout_s = 1800,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Localiza e substitui texto em arquivo gerando copia atualizada'
     OR NVL(dst.script_group, '~') <> 'UTILITARIOS'
     OR NVL(dst.category, '~') <> 'ARQUIVOS'
     OR NVL(dst.stage, '~') <> 'TRANSFORMACAO'
     OR dst.interpreter <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/substituir_texto.py'
     OR dst.param_type <> 'NAMED'
     OR dst.max_parallel_env <> 2
     OR NVL(dst.timeout_s, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'substituir_texto', 'Localiza e substitui texto em arquivo gerando copia atualizada', 'UTILITARIOS', 'ARQUIVOS', 'TRANSFORMACAO', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/substituir_texto.py', 'NAMED', 2, 1800, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'substituir_texto' AND a.name = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'substituir_texto' AND a.name = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'substituir_texto' AND a.name = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'substituir_texto' AND a.name = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'substituir_texto' AND a.name = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'ADMINISTRATOR' AND s.name = 'substituir_texto'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_PROD' AND s.name = 'substituir_texto'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_HML' AND s.name = 'substituir_texto'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'READ_ONLY' AND s.name = 'substituir_texto'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'substituir_texto' AND p.code = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 1,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 1
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 1, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'substituir_texto' AND p.code = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 2,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 2
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 2, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'substituir_texto' AND p.code = 'termo_busca'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 3,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 3
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 3, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'substituir_texto' AND p.code = 'termo_substituicao'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 4,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 4
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 4, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'remover_duplicadas' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Remove linhas duplicadas de arquivo texto preservando ordem ou ordenando',
             dst.script_group = 'UTILITARIOS',
             dst.category = 'ARQUIVOS',
             dst.stage = 'HIGIENIZACAO',
             dst.interpreter = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/remover_duplicadas.py',
             dst.param_type = 'NAMED',
             dst.max_parallel_env = 2,
             dst.timeout_s = 1800,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Remove linhas duplicadas de arquivo texto preservando ordem ou ordenando'
     OR NVL(dst.script_group, '~') <> 'UTILITARIOS'
     OR NVL(dst.category, '~') <> 'ARQUIVOS'
     OR NVL(dst.stage, '~') <> 'HIGIENIZACAO'
     OR dst.interpreter <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/remover_duplicadas.py'
     OR dst.param_type <> 'NAMED'
     OR dst.max_parallel_env <> 2
     OR NVL(dst.timeout_s, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'remover_duplicadas', 'Remove linhas duplicadas de arquivo texto preservando ordem ou ordenando', 'UTILITARIOS', 'ARQUIVOS', 'HIGIENIZACAO', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/remover_duplicadas.py', 'NAMED', 2, 1800, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'remover_duplicadas' AND a.name = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'remover_duplicadas' AND a.name = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'remover_duplicadas' AND a.name = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'remover_duplicadas' AND a.name = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'remover_duplicadas' AND a.name = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'ADMINISTRATOR' AND s.name = 'remover_duplicadas'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_PROD' AND s.name = 'remover_duplicadas'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_HML' AND s.name = 'remover_duplicadas'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'READ_ONLY' AND s.name = 'remover_duplicadas'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'remover_duplicadas' AND p.code = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 1,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 1
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 1, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'remover_duplicadas' AND p.code = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 2,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 2
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 2, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'remover_duplicadas' AND p.code = 'flag_ordenar'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 3,
             dst.required = 'N',
             dst.default_value_override = 'S',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 3
     OR dst.required <> 'N'
     OR NVL(dst.default_value_override, '~') <> NVL('S', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 3, 'N', 'S', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'gerar_hash_arquivo' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Calcula hash criptografico (SHA256, MD5, SHA1) para conferencia de integridade',
             dst.script_group = 'UTILITARIOS',
             dst.category = 'ARQUIVOS',
             dst.stage = 'AUDITORIA',
             dst.interpreter = 'PYTHON3',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/gerar_hash_arquivo.py',
             dst.param_type = 'NAMED',
             dst.max_parallel_env = 2,
             dst.timeout_s = 1800,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Calcula hash criptografico (SHA256, MD5, SHA1) para conferencia de integridade'
     OR NVL(dst.script_group, '~') <> 'UTILITARIOS'
     OR NVL(dst.category, '~') <> 'ARQUIVOS'
     OR NVL(dst.stage, '~') <> 'AUDITORIA'
     OR dst.interpreter <> 'PYTHON3'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/gerar_hash_arquivo.py'
     OR dst.param_type <> 'NAMED'
     OR dst.max_parallel_env <> 2
     OR NVL(dst.timeout_s, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'gerar_hash_arquivo', 'Calcula hash criptografico (SHA256, MD5, SHA1) para conferencia de integridade', 'UTILITARIOS', 'ARQUIVOS', 'AUDITORIA', 'PYTHON3', '/opt/automacoes/scripts/utilitarios/gerar_hash_arquivo.py', 'NAMED', 2, 1800, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'gerar_hash_arquivo' AND a.name = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'gerar_hash_arquivo' AND a.name = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'gerar_hash_arquivo' AND a.name = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'gerar_hash_arquivo' AND a.name = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'gerar_hash_arquivo' AND a.name = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'ADMINISTRATOR' AND s.name = 'gerar_hash_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_PROD' AND s.name = 'gerar_hash_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_HML' AND s.name = 'gerar_hash_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'READ_ONLY' AND s.name = 'gerar_hash_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'gerar_hash_arquivo' AND p.code = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 1,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 1
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 1, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'gerar_hash_arquivo' AND p.code = 'tipo_hash'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 2,
             dst.required = 'N',
             dst.default_value_override = 'sha256',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 2
     OR dst.required <> 'N'
     OR NVL(dst.default_value_override, '~') <> NVL('sha256', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 2, 'N', 'sha256', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'compactar_targz' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Cria pacote compactado .tar.gz a partir de arquivo ou pasta',
             dst.script_group = 'UTILITARIOS',
             dst.category = 'ARQUIVOS',
             dst.stage = 'COMPACTACAO',
             dst.interpreter = 'BASH',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/compactar_targz.sh',
             dst.param_type = 'NAMED',
             dst.max_parallel_env = 2,
             dst.timeout_s = 1800,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Cria pacote compactado .tar.gz a partir de arquivo ou pasta'
     OR NVL(dst.script_group, '~') <> 'UTILITARIOS'
     OR NVL(dst.category, '~') <> 'ARQUIVOS'
     OR NVL(dst.stage, '~') <> 'COMPACTACAO'
     OR dst.interpreter <> 'BASH'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/compactar_targz.sh'
     OR dst.param_type <> 'NAMED'
     OR dst.max_parallel_env <> 2
     OR NVL(dst.timeout_s, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'compactar_targz', 'Cria pacote compactado .tar.gz a partir de arquivo ou pasta', 'UTILITARIOS', 'ARQUIVOS', 'COMPACTACAO', 'BASH', '/opt/automacoes/scripts/utilitarios/compactar_targz.sh', 'NAMED', 2, 1800, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'compactar_targz' AND a.name = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'compactar_targz' AND a.name = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'compactar_targz' AND a.name = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'compactar_targz' AND a.name = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'compactar_targz' AND a.name = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'ADMINISTRATOR' AND s.name = 'compactar_targz'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_PROD' AND s.name = 'compactar_targz'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_HML' AND s.name = 'compactar_targz'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'READ_ONLY' AND s.name = 'compactar_targz'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'compactar_targz' AND p.code = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 1,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 1
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 1, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'compactar_targz' AND p.code = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 2,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 2
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 2, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'descompactar_targz' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Extrai pacote compactado .tar.gz para pasta destino com verificacao',
             dst.script_group = 'UTILITARIOS',
             dst.category = 'ARQUIVOS',
             dst.stage = 'DESCOMPACTACAO',
             dst.interpreter = 'BASH',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/descompactar_targz.sh',
             dst.param_type = 'NAMED',
             dst.max_parallel_env = 2,
             dst.timeout_s = 1800,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Extrai pacote compactado .tar.gz para pasta destino com verificacao'
     OR NVL(dst.script_group, '~') <> 'UTILITARIOS'
     OR NVL(dst.category, '~') <> 'ARQUIVOS'
     OR NVL(dst.stage, '~') <> 'DESCOMPACTACAO'
     OR dst.interpreter <> 'BASH'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/descompactar_targz.sh'
     OR dst.param_type <> 'NAMED'
     OR dst.max_parallel_env <> 2
     OR NVL(dst.timeout_s, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'descompactar_targz', 'Extrai pacote compactado .tar.gz para pasta destino com verificacao', 'UTILITARIOS', 'ARQUIVOS', 'DESCOMPACTACAO', 'BASH', '/opt/automacoes/scripts/utilitarios/descompactar_targz.sh', 'NAMED', 2, 1800, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'descompactar_targz' AND a.name = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'descompactar_targz' AND a.name = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'descompactar_targz' AND a.name = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'descompactar_targz' AND a.name = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'descompactar_targz' AND a.name = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'ADMINISTRATOR' AND s.name = 'descompactar_targz'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_PROD' AND s.name = 'descompactar_targz'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_HML' AND s.name = 'descompactar_targz'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'READ_ONLY' AND s.name = 'descompactar_targz'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'descompactar_targz' AND p.code = 'arq_tar'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 1,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 1
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 1, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'descompactar_targz' AND p.code = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 2,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 2
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 2, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'contar_linhas_arquivo' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Conta linhas, palavras e bytes de arquivo texto (modo posicional/sequencial)',
             dst.script_group = 'UTILITARIOS',
             dst.category = 'ARQUIVOS',
             dst.stage = 'ANALISE',
             dst.interpreter = 'SH',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/contar_linhas_arquivo.sh',
             dst.param_type = 'POSITIONAL',
             dst.max_parallel_env = 2,
             dst.timeout_s = 600,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Conta linhas, palavras e bytes de arquivo texto (modo posicional/sequencial)'
     OR NVL(dst.script_group, '~') <> 'UTILITARIOS'
     OR NVL(dst.category, '~') <> 'ARQUIVOS'
     OR NVL(dst.stage, '~') <> 'ANALISE'
     OR dst.interpreter <> 'SH'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/contar_linhas_arquivo.sh'
     OR dst.param_type <> 'POSITIONAL'
     OR dst.max_parallel_env <> 2
     OR NVL(dst.timeout_s, 0) <> 600
WHEN NOT MATCHED THEN
  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'contar_linhas_arquivo', 'Conta linhas, palavras e bytes de arquivo texto (modo posicional/sequencial)', 'UTILITARIOS', 'ARQUIVOS', 'ANALISE', 'SH', '/opt/automacoes/scripts/utilitarios/contar_linhas_arquivo.sh', 'POSITIONAL', 2, 600, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'contar_linhas_arquivo' AND a.name = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'contar_linhas_arquivo' AND a.name = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'contar_linhas_arquivo' AND a.name = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'contar_linhas_arquivo' AND a.name = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'contar_linhas_arquivo' AND a.name = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'ADMINISTRATOR' AND s.name = 'contar_linhas_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_PROD' AND s.name = 'contar_linhas_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_HML' AND s.name = 'contar_linhas_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'READ_ONLY' AND s.name = 'contar_linhas_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'contar_linhas_arquivo' AND p.code = 'caminho_arquivo'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 1,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 1
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 1, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'filtrar_linhas' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Filtra linhas de arquivo baseado em padrao de texto com opcao de inverter',
             dst.script_group = 'UTILITARIOS',
             dst.category = 'ARQUIVOS',
             dst.stage = 'FILTRAGEM',
             dst.interpreter = 'BASH',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/filtrar_linhas.sh',
             dst.param_type = 'NAMED',
             dst.max_parallel_env = 2,
             dst.timeout_s = 1800,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Filtra linhas de arquivo baseado em padrao de texto com opcao de inverter'
     OR NVL(dst.script_group, '~') <> 'UTILITARIOS'
     OR NVL(dst.category, '~') <> 'ARQUIVOS'
     OR NVL(dst.stage, '~') <> 'FILTRAGEM'
     OR dst.interpreter <> 'BASH'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/filtrar_linhas.sh'
     OR dst.param_type <> 'NAMED'
     OR dst.max_parallel_env <> 2
     OR NVL(dst.timeout_s, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'filtrar_linhas', 'Filtra linhas de arquivo baseado em padrao de texto com opcao de inverter', 'UTILITARIOS', 'ARQUIVOS', 'FILTRAGEM', 'BASH', '/opt/automacoes/scripts/utilitarios/filtrar_linhas.sh', 'NAMED', 2, 1800, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'filtrar_linhas' AND a.name = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'filtrar_linhas' AND a.name = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'filtrar_linhas' AND a.name = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'filtrar_linhas' AND a.name = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'filtrar_linhas' AND a.name = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'ADMINISTRATOR' AND s.name = 'filtrar_linhas'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_PROD' AND s.name = 'filtrar_linhas'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_HML' AND s.name = 'filtrar_linhas'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'READ_ONLY' AND s.name = 'filtrar_linhas'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'filtrar_linhas' AND p.code = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 1,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 1
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 1, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'filtrar_linhas' AND p.code = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 2,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 2
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 2, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'filtrar_linhas' AND p.code = 'termo_filtro'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 3,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 3
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 3, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'filtrar_linhas' AND p.code = 'flag_inverter'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 4,
             dst.required = 'N',
             dst.default_value_override = 'N',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 4
     OR dst.required <> 'N'
     OR NVL(dst.default_value_override, '~') <> NVL('N', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 4, 'N', 'N', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'ordenar_arquivo' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Ordena linhas de arquivo texto com opcoes numerica e reversa',
             dst.script_group = 'UTILITARIOS',
             dst.category = 'ARQUIVOS',
             dst.stage = 'ORGANIZACAO',
             dst.interpreter = 'SH',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/ordenar_arquivo.sh',
             dst.param_type = 'NAMED',
             dst.max_parallel_env = 2,
             dst.timeout_s = 1800,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Ordena linhas de arquivo texto com opcoes numerica e reversa'
     OR NVL(dst.script_group, '~') <> 'UTILITARIOS'
     OR NVL(dst.category, '~') <> 'ARQUIVOS'
     OR NVL(dst.stage, '~') <> 'ORGANIZACAO'
     OR dst.interpreter <> 'SH'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/ordenar_arquivo.sh'
     OR dst.param_type <> 'NAMED'
     OR dst.max_parallel_env <> 2
     OR NVL(dst.timeout_s, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'ordenar_arquivo', 'Ordena linhas de arquivo texto com opcoes numerica e reversa', 'UTILITARIOS', 'ARQUIVOS', 'ORGANIZACAO', 'SH', '/opt/automacoes/scripts/utilitarios/ordenar_arquivo.sh', 'NAMED', 2, 1800, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'ordenar_arquivo' AND a.name = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'ordenar_arquivo' AND a.name = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'ordenar_arquivo' AND a.name = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'ordenar_arquivo' AND a.name = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'ordenar_arquivo' AND a.name = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'ADMINISTRATOR' AND s.name = 'ordenar_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_PROD' AND s.name = 'ordenar_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_HML' AND s.name = 'ordenar_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'READ_ONLY' AND s.name = 'ordenar_arquivo'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'ordenar_arquivo' AND p.code = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 1,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 1
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 1, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'ordenar_arquivo' AND p.code = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 2,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 2
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 2, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'ordenar_arquivo' AND p.code = 'flag_numerico'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 3,
             dst.required = 'N',
             dst.default_value_override = 'N',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 3
     OR dst.required <> 'N'
     OR NVL(dst.default_value_override, '~') <> NVL('N', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 3, 'N', 'N', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'ordenar_arquivo' AND p.code = 'flag_reverso'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 4,
             dst.required = 'N',
             dst.default_value_override = 'N',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 4
     OR dst.required <> 'N'
     OR NVL(dst.default_value_override, '~') <> NVL('N', '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 4, 'N', 'N', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_scripts dst
USING (SELECT 'limpar_linhas_vazias' AS name FROM DUAL) src
ON (dst.name = src.name)
WHEN MATCHED THEN
  UPDATE SET dst.description = 'Remove espacos em branco excedentes e linhas vazias de arquivo texto',
             dst.script_group = 'UTILITARIOS',
             dst.category = 'ARQUIVOS',
             dst.stage = 'HIGIENIZACAO',
             dst.interpreter = 'BASH',
             dst.path_file = '/opt/automacoes/scripts/utilitarios/limpar_linhas_vazias.sh',
             dst.param_type = 'NAMED',
             dst.max_parallel_env = 2,
             dst.timeout_s = 1800,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.active <> 'Y'
     OR NVL(dst.description, '~') <> 'Remove espacos em branco excedentes e linhas vazias de arquivo texto'
     OR NVL(dst.script_group, '~') <> 'UTILITARIOS'
     OR NVL(dst.category, '~') <> 'ARQUIVOS'
     OR NVL(dst.stage, '~') <> 'HIGIENIZACAO'
     OR dst.interpreter <> 'BASH'
     OR dst.path_file <> '/opt/automacoes/scripts/utilitarios/limpar_linhas_vazias.sh'
     OR dst.param_type <> 'NAMED'
     OR dst.max_parallel_env <> 2
     OR NVL(dst.timeout_s, 0) <> 1800
WHEN NOT MATCHED THEN
  INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
  VALUES (openrisow.sq_tbsss_scripts.NEXTVAL, 'limpar_linhas_vazias', 'Remove espacos em branco excedentes e linhas vazias de arquivo texto', 'UTILITARIOS', 'ARQUIVOS', 'HIGIENIZACAO', 'BASH', '/opt/automacoes/scripts/utilitarios/limpar_linhas_vazias.sh', 'NAMED', 2, 1800, 'Y', SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'limpar_linhas_vazias' AND a.name = 'CLONE2'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'limpar_linhas_vazias' AND a.name = 'CLONE1'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'limpar_linhas_vazias' AND a.name = 'CLONE6'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'limpar_linhas_vazias' AND a.name = 'CLONE7'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_env dst
USING (
  SELECT s.id AS script_id, a.id AS environment_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_environments a
   WHERE s.name = 'limpar_linhas_vazias' AND a.name = 'GFPREPROD'
) src
ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
WHEN NOT MATCHED THEN
  INSERT (id, script_id, environment_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_env.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'ADMINISTRATOR' AND s.name = 'limpar_linhas_vazias'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_PROD' AND s.name = 'limpar_linhas_vazias'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'OPERATOR_HML' AND s.name = 'limpar_linhas_vazias'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_profile_script dst
USING (
  SELECT p.id AS profile_id, s.id AS script_id
    FROM openrisow.tbsss_profiles p, openrisow.tbsss_scripts s
   WHERE p.name = 'READ_ONLY' AND s.name = 'limpar_linhas_vazias'
) src
ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
WHEN NOT MATCHED THEN
  INSERT (id, profile_id, script_id, created_at, created_by)
  VALUES (openrisow.sq_tbsss_profile_script.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'limpar_linhas_vazias' AND p.code = 'arq_origem'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 1,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 1
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 1, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_script_param dst
USING (
  SELECT s.id AS script_id, p.id AS parameter_id
    FROM openrisow.tbsss_scripts s, openrisow.tbsss_parameters p
   WHERE s.name = 'limpar_linhas_vazias' AND p.code = 'arq_destino'
) src
ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
WHEN MATCHED THEN
  UPDATE SET dst.sort_order = 2,
             dst.required = 'Y',
             dst.default_value_override = NULL,
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.sort_order <> 2
     OR dst.required <> 'Y'
     OR NVL(dst.default_value_override, '~') <> NVL(NULL, '~')
WHEN NOT MATCHED THEN
  INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
  VALUES (openrisow.sq_tbsss_script_param.NEXTVAL, src.script_id, src.parameter_id, 2, 'Y', NULL, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_control dst
USING (SELECT 1 AS id FROM DUAL) src
ON (dst.id = src.id)
WHEN NOT MATCHED THEN
  INSERT (id, schema_version, version_applied_at, version_applied_by)
  VALUES (1, 1, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_users dst
USING (
  SELECT 'admin' AS login, p.id AS profile_id
    FROM openrisow.tbsss_profiles p
   WHERE p.name = 'ADMINISTRATOR'
) src
ON (dst.login = src.login)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Super Administrador',
             dst.profile_id = src.profile_id,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.name <> 'Super Administrador'
     OR dst.profile_id <> src.profile_id
     OR dst.active <> 'Y'
WHEN NOT MATCHED THEN
  INSERT (id, login, name, password_hash, profile_id, active, session_epoch, failed_attempts, created_at, created_by)
  VALUES (openrisow.sq_tbsss_users.NEXTVAL, 'admin', 'Super Administrador', 'pbkdf2_sha256$200000$8007db1bd770663178d0f1b1a129140c$9d9604af27e21326e982e5e7c64bfdd868c0995a97181b5a9695149755852d63', src.profile_id, 'Y', 0, 0, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_users dst
USING (
  SELECT 'op.prod' AS login, p.id AS profile_id
    FROM openrisow.tbsss_profiles p
   WHERE p.name = 'OPERATOR_PROD'
) src
ON (dst.login = src.login)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Operador Producao',
             dst.profile_id = src.profile_id,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.name <> 'Operador Producao'
     OR dst.profile_id <> src.profile_id
     OR dst.active <> 'Y'
WHEN NOT MATCHED THEN
  INSERT (id, login, name, password_hash, profile_id, active, session_epoch, failed_attempts, created_at, created_by)
  VALUES (openrisow.sq_tbsss_users.NEXTVAL, 'op.prod', 'Operador Producao', 'pbkdf2_sha256$200000$8007db1bd770663178d0f1b1a129140c$9d9604af27e21326e982e5e7c64bfdd868c0995a97181b5a9695149755852d63', src.profile_id, 'Y', 0, 0, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_users dst
USING (
  SELECT 'op.hml' AS login, p.id AS profile_id
    FROM openrisow.tbsss_profiles p
   WHERE p.name = 'OPERATOR_HML'
) src
ON (dst.login = src.login)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Operador Homologacao',
             dst.profile_id = src.profile_id,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.name <> 'Operador Homologacao'
     OR dst.profile_id <> src.profile_id
     OR dst.active <> 'Y'
WHEN NOT MATCHED THEN
  INSERT (id, login, name, password_hash, profile_id, active, session_epoch, failed_attempts, created_at, created_by)
  VALUES (openrisow.sq_tbsss_users.NEXTVAL, 'op.hml', 'Operador Homologacao', 'pbkdf2_sha256$200000$8007db1bd770663178d0f1b1a129140c$9d9604af27e21326e982e5e7c64bfdd868c0995a97181b5a9695149755852d63', src.profile_id, 'Y', 0, 0, SYSDATE, 'SYSTEM:init_db');

MERGE INTO openrisow.tbsss_users dst
USING (
  SELECT 'consulta' AS login, p.id AS profile_id
    FROM openrisow.tbsss_profiles p
   WHERE p.name = 'READ_ONLY'
) src
ON (dst.login = src.login)
WHEN MATCHED THEN
  UPDATE SET dst.name = 'Auditor e Consulta',
             dst.profile_id = src.profile_id,
             dst.active = 'Y',
             dst.updated_at = SYSDATE,
             dst.updated_by = 'SYSTEM:init_db'
  WHERE dst.name <> 'Auditor e Consulta'
     OR dst.profile_id <> src.profile_id
     OR dst.active <> 'Y'
WHEN NOT MATCHED THEN
  INSERT (id, login, name, password_hash, profile_id, active, session_epoch, failed_attempts, created_at, created_by)
  VALUES (openrisow.sq_tbsss_users.NEXTVAL, 'consulta', 'Auditor e Consulta', 'pbkdf2_sha256$200000$8007db1bd770663178d0f1b1a129140c$9d9604af27e21326e982e5e7c64bfdd868c0995a97181b5a9695149755852d63', src.profile_id, 'Y', 0, 0, SYSDATE, 'SYSTEM:init_db');

-- ------------------------------------------------------------------------------
-- FASE 8: ESTATISTICAS INICIAIS DO OTIMIZADOR (CR-007, R-29)
-- ------------------------------------------------------------------------------
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_FEATURES', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_PROFILES', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_PROFILE_FEATURE', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_PROFILE_ENV', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_ENVIRONMENTS', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_PARAMETERS', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_SCRIPTS', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_SCRIPT_ENV', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_PROFILE_SCRIPT', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_SCRIPT_PARAM', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_CONTROL', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(ownname => 'OPENRISOW', tabname => 'TBSSS_USERS', cascade => TRUE);
END;
/

COMMIT;

-- ==============================================================================
-- GRANTS POR PAPEL (README §11.1); nenhum GRANT a PUBLIC
-- ==============================================================================

-- papel web: usa a conta dona do esquema (openrisow); nenhum GRANT necessario
-- papel agent: usa a conta dona do esquema (openrisow); nenhum GRANT necessario
-- papel purge: conta nao informada; nenhum GRANT gerado
-- papel monitor: conta nao informada; nenhum GRANT gerado

PROMPT Implantacao do SSS concluida com sucesso!
EXIT;
