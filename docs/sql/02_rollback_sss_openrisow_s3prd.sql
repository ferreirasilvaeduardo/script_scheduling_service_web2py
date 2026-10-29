-- ==============================================================================
-- Script Scheduling Service (SSS) - Rollback / Desinstalacao Oracle 11gR2+
-- Gerado automaticamente a partir do registro sql_ident.py
-- Owner: openrisow
-- Prefixo: s3prd_
-- ==============================================================================
SET DEFINE OFF;
SET SERVEROUTPUT ON;
WHENEVER SQLERROR CONTINUE;

-- ------------------------------------------------------------------------------
-- 1. DROP TRIGGERS
-- ------------------------------------------------------------------------------
DROP TRIGGER openrisow.tr_s3prd_idl_bi;
DROP TRIGGER openrisow.tr_s3prd_ils_bi;
DROP TRIGGER openrisow.tr_s3prd_iup_bi;
DROP TRIGGER openrisow.tr_s3prd_tout_bi;
DROP TRIGGER openrisow.tr_s3prd_tans_bi;
DROP TRIGGER openrisow.tr_s3prd_tck_bi;
DROP TRIGGER openrisow.tr_s3prd_sch_bi;
DROP TRIGGER openrisow.tr_s3prd_sprm_bi;
DROP TRIGGER openrisow.tr_s3prd_prm_bi;
DROP TRIGGER openrisow.tr_s3prd_senv_bi;
DROP TRIGGER openrisow.tr_s3prd_pscr_bi;
DROP TRIGGER openrisow.tr_s3prd_penv_bi;
DROP TRIGGER openrisow.tr_s3prd_pfea_bi;
DROP TRIGGER openrisow.tr_s3prd_scr_bi;
DROP TRIGGER openrisow.tr_s3prd_usr_bu;
DROP TRIGGER openrisow.tr_s3prd_usr_bi;
DROP TRIGGER openrisow.tr_s3prd_fea_bi;
DROP TRIGGER openrisow.tr_s3prd_prf_bi;
DROP TRIGGER openrisow.tr_s3prd_env_bu;
DROP TRIGGER openrisow.tr_s3prd_env_bi;
DROP TRIGGER openrisow.tr_s3prd_agt_bi;
DROP TRIGGER openrisow.tr_s3prd_aud_bi;
DROP TRIGGER openrisow.tr_s3prd_ctl_bi;

-- ------------------------------------------------------------------------------
-- 2. DROP TABELAS (CASCADE CONSTRAINTS PURGE)
-- ------------------------------------------------------------------------------
DROP TABLE openrisow.s3prd_input_delivery CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_input_listing CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_input_upload CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_ticket_output CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_ticket_answer CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_tickets CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_schedules CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_script_param CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_parameters CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_script_env CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_profile_script CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_profile_env CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_profile_feature CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_scripts CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_users CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_features CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_profiles CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_environments CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_agents CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_audit CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.s3prd_control CASCADE CONSTRAINTS PURGE;

-- ------------------------------------------------------------------------------
-- 3. DROP SEQUENCES
-- ------------------------------------------------------------------------------
DROP SEQUENCE openrisow.sq_s3prd_input_delivery;
DROP SEQUENCE openrisow.sq_s3prd_input_listing;
DROP SEQUENCE openrisow.sq_s3prd_input_upload;
DROP SEQUENCE openrisow.sq_s3prd_ticket_output;
DROP SEQUENCE openrisow.sq_s3prd_ticket_answer;
DROP SEQUENCE openrisow.sq_s3prd_tickets;
DROP SEQUENCE openrisow.sq_s3prd_schedules;
DROP SEQUENCE openrisow.sq_s3prd_script_param;
DROP SEQUENCE openrisow.sq_s3prd_parameters;
DROP SEQUENCE openrisow.sq_s3prd_script_env;
DROP SEQUENCE openrisow.sq_s3prd_profile_script;
DROP SEQUENCE openrisow.sq_s3prd_profile_env;
DROP SEQUENCE openrisow.sq_s3prd_profile_feature;
DROP SEQUENCE openrisow.sq_s3prd_scripts;
DROP SEQUENCE openrisow.sq_s3prd_users;
DROP SEQUENCE openrisow.sq_s3prd_features;
DROP SEQUENCE openrisow.sq_s3prd_profiles;
DROP SEQUENCE openrisow.sq_s3prd_environments;
DROP SEQUENCE openrisow.sq_s3prd_agents;
DROP SEQUENCE openrisow.sq_s3prd_audit;
DROP SEQUENCE openrisow.sq_s3prd_control;

PROMPT Rollback do SSS concluido com sucesso.
EXIT;
