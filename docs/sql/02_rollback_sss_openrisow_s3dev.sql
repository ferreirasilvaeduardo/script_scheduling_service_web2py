-- ==============================================================================
-- Script Scheduling Service (SSS) - Rollback / Desinstalacao Oracle 11gR2+
-- Gerado automaticamente a partir do registro sql_ident.py
-- Owner: openrisow
-- Prefixo: s3dev_
-- ==============================================================================
SET DEFINE OFF;
SET SERVEROUTPUT ON;
WHENEVER SQLERROR CONTINUE;

-- ------------------------------------------------------------------------------
-- 1. DROP TRIGGERS
-- ------------------------------------------------------------------------------
DROP TRIGGER openrisow.tr_s3dev_idl_bi;
DROP TRIGGER openrisow.tr_s3dev_ils_bi;
DROP TRIGGER openrisow.tr_s3dev_iup_bi;
DROP TRIGGER openrisow.tr_s3dev_tout_bi;
DROP TRIGGER openrisow.tr_s3dev_tans_bi;
DROP TRIGGER openrisow.tr_s3dev_tck_bi;
DROP TRIGGER openrisow.tr_s3dev_sch_bi;
DROP TRIGGER openrisow.tr_s3dev_sprm_bi;
DROP TRIGGER openrisow.tr_s3dev_prm_bi;
DROP TRIGGER openrisow.tr_s3dev_senv_bi;
DROP TRIGGER openrisow.tr_s3dev_pscr_bi;
DROP TRIGGER openrisow.tr_s3dev_penv_bi;
DROP TRIGGER openrisow.tr_s3dev_pfea_bi;
DROP TRIGGER openrisow.tr_s3dev_scr_bi;
DROP TRIGGER openrisow.tr_s3dev_usr_bu;
DROP TRIGGER openrisow.tr_s3dev_usr_bi;
DROP TRIGGER openrisow.tr_s3dev_fea_bi;
DROP TRIGGER openrisow.tr_s3dev_prf_bi;
DROP TRIGGER openrisow.tr_s3dev_env_bu;
DROP TRIGGER openrisow.tr_s3dev_env_bi;
DROP TRIGGER openrisow.tr_s3dev_agt_bi;
DROP TRIGGER openrisow.tr_s3dev_aud_bi;
DROP TRIGGER openrisow.tr_s3dev_ctl_bi;

-- ------------------------------------------------------------------------------
-- 2. DROP TABELAS (CASCADE CONSTRAINTS PURGE)
-- ------------------------------------------------------------------------------
DROP TABLE openrisow.s3dev_input_delivery CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_input_listing CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_input_upload CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_ticket_output CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_ticket_answer CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_tickets CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_schedules CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_script_param CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_parameters CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_script_env CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_profile_script CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_profile_env CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_profile_feature CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_scripts CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_users CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_features CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_profiles CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_environments CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_agents CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_audit CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3dev_control CASCADE CONSTRAINTS PURGE;

-- ------------------------------------------------------------------------------
-- 3. DROP SEQUENCES
-- ------------------------------------------------------------------------------
DROP SEQUENCE openrisow.sq_s3dev_input_delivery;
DROP SEQUENCE openrisow.sq_s3dev_input_listing;
DROP SEQUENCE openrisow.sq_s3dev_input_upload;
DROP SEQUENCE openrisow.sq_s3dev_ticket_output;
DROP SEQUENCE openrisow.sq_s3dev_ticket_answer;
DROP SEQUENCE openrisow.sq_s3dev_tickets;
DROP SEQUENCE openrisow.sq_s3dev_schedules;
DROP SEQUENCE openrisow.sq_s3dev_script_param;
DROP SEQUENCE openrisow.sq_s3dev_parameters;
DROP SEQUENCE openrisow.sq_s3dev_script_env;
DROP SEQUENCE openrisow.sq_s3dev_profile_script;
DROP SEQUENCE openrisow.sq_s3dev_profile_env;
DROP SEQUENCE openrisow.sq_s3dev_profile_feature;
DROP SEQUENCE openrisow.sq_s3dev_scripts;
DROP SEQUENCE openrisow.sq_s3dev_users;
DROP SEQUENCE openrisow.sq_s3dev_features;
DROP SEQUENCE openrisow.sq_s3dev_profiles;
DROP SEQUENCE openrisow.sq_s3dev_environments;
DROP SEQUENCE openrisow.sq_s3dev_agents;
DROP SEQUENCE openrisow.sq_s3dev_audit;
DROP SEQUENCE openrisow.sq_s3dev_control;

PROMPT Rollback do SSS concluido com sucesso.
EXIT;
