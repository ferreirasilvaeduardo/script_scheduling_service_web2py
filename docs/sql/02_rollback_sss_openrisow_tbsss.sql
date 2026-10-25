-- ==============================================================================
-- Script Scheduling Service (SSS) - Rollback / Desinstalacao Oracle 11gR2+
-- Gerado automaticamente a partir do registro sql_ident.py
-- Owner: openrisow
-- Prefixo: tbsss_
-- ==============================================================================
SET DEFINE OFF;
SET SERVEROUTPUT ON;
WHENEVER SQLERROR CONTINUE;

-- ------------------------------------------------------------------------------
-- 1. DROP TRIGGERS
-- ------------------------------------------------------------------------------
DROP TRIGGER openrisow.tr_tbsss_idl_bi;
DROP TRIGGER openrisow.tr_tbsss_ils_bi;
DROP TRIGGER openrisow.tr_tbsss_iup_bi;
DROP TRIGGER openrisow.tr_tbsss_tout_bi;
DROP TRIGGER openrisow.tr_tbsss_tans_bi;
DROP TRIGGER openrisow.tr_tbsss_tck_bi;
DROP TRIGGER openrisow.tr_tbsss_sch_bi;
DROP TRIGGER openrisow.tr_tbsss_sprm_bi;
DROP TRIGGER openrisow.tr_tbsss_prm_bi;
DROP TRIGGER openrisow.tr_tbsss_senv_bi;
DROP TRIGGER openrisow.tr_tbsss_pscr_bi;
DROP TRIGGER openrisow.tr_tbsss_penv_bi;
DROP TRIGGER openrisow.tr_tbsss_pfea_bi;
DROP TRIGGER openrisow.tr_tbsss_scr_bi;
DROP TRIGGER openrisow.tr_tbsss_usr_bu;
DROP TRIGGER openrisow.tr_tbsss_usr_bi;
DROP TRIGGER openrisow.tr_tbsss_fea_bi;
DROP TRIGGER openrisow.tr_tbsss_prf_bi;
DROP TRIGGER openrisow.tr_tbsss_env_bu;
DROP TRIGGER openrisow.tr_tbsss_env_bi;
DROP TRIGGER openrisow.tr_tbsss_agt_bi;
DROP TRIGGER openrisow.tr_tbsss_aud_bi;
DROP TRIGGER openrisow.tr_tbsss_ctl_bi;

-- ------------------------------------------------------------------------------
-- 2. DROP TABELAS (CASCADE CONSTRAINTS PURGE)
-- ------------------------------------------------------------------------------
DROP TABLE openrisow.tbsss_input_delivery CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_input_listing CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_input_upload CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_ticket_output CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_ticket_answer CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_tickets CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_schedules CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_script_param CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_parameters CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_script_env CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_profile_script CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_profile_env CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_profile_feature CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_scripts CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_users CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_features CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_profiles CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_environments CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_agents CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_audit CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_control CASCADE CONSTRAINTS PURGE;

-- ------------------------------------------------------------------------------
-- 3. DROP SEQUENCES
-- ------------------------------------------------------------------------------
DROP SEQUENCE openrisow.sq_tbsss_input_delivery;
DROP SEQUENCE openrisow.sq_tbsss_input_listing;
DROP SEQUENCE openrisow.sq_tbsss_input_upload;
DROP SEQUENCE openrisow.sq_tbsss_ticket_output;
DROP SEQUENCE openrisow.sq_tbsss_ticket_answer;
DROP SEQUENCE openrisow.sq_tbsss_tickets;
DROP SEQUENCE openrisow.sq_tbsss_schedules;
DROP SEQUENCE openrisow.sq_tbsss_script_param;
DROP SEQUENCE openrisow.sq_tbsss_parameters;
DROP SEQUENCE openrisow.sq_tbsss_script_env;
DROP SEQUENCE openrisow.sq_tbsss_profile_script;
DROP SEQUENCE openrisow.sq_tbsss_profile_env;
DROP SEQUENCE openrisow.sq_tbsss_profile_feature;
DROP SEQUENCE openrisow.sq_tbsss_scripts;
DROP SEQUENCE openrisow.sq_tbsss_users;
DROP SEQUENCE openrisow.sq_tbsss_features;
DROP SEQUENCE openrisow.sq_tbsss_profiles;
DROP SEQUENCE openrisow.sq_tbsss_environments;
DROP SEQUENCE openrisow.sq_tbsss_agents;
DROP SEQUENCE openrisow.sq_tbsss_audit;
DROP SEQUENCE openrisow.sq_tbsss_control;

PROMPT Rollback do SSS concluido com sucesso.
EXIT;
