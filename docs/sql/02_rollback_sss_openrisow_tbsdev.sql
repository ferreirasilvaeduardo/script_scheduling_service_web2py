-- ==============================================================================
-- Script Scheduling Service (SSS) - Rollback / Desinstalacao Oracle 11gR2+
-- Gerado automaticamente a partir do registro sql_ident.py
-- Owner: openrisow
-- Prefixo: tbsdev_
-- ==============================================================================
SET DEFINE OFF;
SET SERVEROUTPUT ON;
WHENEVER SQLERROR CONTINUE;

-- ------------------------------------------------------------------------------
-- 1. DROP TRIGGERS
-- ------------------------------------------------------------------------------
DROP TRIGGER openrisow.tr_tbsdev_idl_bi;
DROP TRIGGER openrisow.tr_tbsdev_ils_bi;
DROP TRIGGER openrisow.tr_tbsdev_iup_bi;
DROP TRIGGER openrisow.tr_tbsdev_tout_bi;
DROP TRIGGER openrisow.tr_tbsdev_tans_bi;
DROP TRIGGER openrisow.tr_tbsdev_tck_bi;
DROP TRIGGER openrisow.tr_tbsdev_sch_bi;
DROP TRIGGER openrisow.tr_tbsdev_sprm_bi;
DROP TRIGGER openrisow.tr_tbsdev_prm_bi;
DROP TRIGGER openrisow.tr_tbsdev_senv_bi;
DROP TRIGGER openrisow.tr_tbsdev_pscr_bi;
DROP TRIGGER openrisow.tr_tbsdev_penv_bi;
DROP TRIGGER openrisow.tr_tbsdev_pfea_bi;
DROP TRIGGER openrisow.tr_tbsdev_scr_bi;
DROP TRIGGER openrisow.tr_tbsdev_usr_bu;
DROP TRIGGER openrisow.tr_tbsdev_usr_bi;
DROP TRIGGER openrisow.tr_tbsdev_fea_bi;
DROP TRIGGER openrisow.tr_tbsdev_prf_bi;
DROP TRIGGER openrisow.tr_tbsdev_env_bu;
DROP TRIGGER openrisow.tr_tbsdev_env_bi;
DROP TRIGGER openrisow.tr_tbsdev_agt_bi;
DROP TRIGGER openrisow.tr_tbsdev_aud_bi;
DROP TRIGGER openrisow.tr_tbsdev_ctl_bi;

-- ------------------------------------------------------------------------------
-- 2. DROP TABELAS (CASCADE CONSTRAINTS PURGE)
-- ------------------------------------------------------------------------------
DROP TABLE openrisow.tbsdev_input_delivery CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_input_listing CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_input_upload CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_ticket_output CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_ticket_answer CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_tickets CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_schedules CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_script_param CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_parameters CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_script_env CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_profile_script CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_profile_env CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_profile_feature CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_scripts CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_users CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_features CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_profiles CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_environments CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_agents CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_audit CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsdev_control CASCADE CONSTRAINTS PURGE;

-- ------------------------------------------------------------------------------
-- 3. DROP SEQUENCES
-- ------------------------------------------------------------------------------
DROP SEQUENCE openrisow.sq_tbsdev_input_delivery;
DROP SEQUENCE openrisow.sq_tbsdev_input_listing;
DROP SEQUENCE openrisow.sq_tbsdev_input_upload;
DROP SEQUENCE openrisow.sq_tbsdev_ticket_output;
DROP SEQUENCE openrisow.sq_tbsdev_ticket_answer;
DROP SEQUENCE openrisow.sq_tbsdev_tickets;
DROP SEQUENCE openrisow.sq_tbsdev_schedules;
DROP SEQUENCE openrisow.sq_tbsdev_script_param;
DROP SEQUENCE openrisow.sq_tbsdev_parameters;
DROP SEQUENCE openrisow.sq_tbsdev_script_env;
DROP SEQUENCE openrisow.sq_tbsdev_profile_script;
DROP SEQUENCE openrisow.sq_tbsdev_profile_env;
DROP SEQUENCE openrisow.sq_tbsdev_profile_feature;
DROP SEQUENCE openrisow.sq_tbsdev_scripts;
DROP SEQUENCE openrisow.sq_tbsdev_users;
DROP SEQUENCE openrisow.sq_tbsdev_features;
DROP SEQUENCE openrisow.sq_tbsdev_profiles;
DROP SEQUENCE openrisow.sq_tbsdev_environments;
DROP SEQUENCE openrisow.sq_tbsdev_agents;
DROP SEQUENCE openrisow.sq_tbsdev_audit;
DROP SEQUENCE openrisow.sq_tbsdev_control;

PROMPT Rollback do SSS concluido com sucesso.
EXIT;
