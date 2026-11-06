-- ==============================================================================
-- Script Scheduling Service (SSS) - Rollback / Desinstalacao Oracle 11gR2+
-- Gerado automaticamente a partir do registro sql_ident.py
-- Owner: openrisow
-- Prefixo: tbsprd_
-- ==============================================================================
SET DEFINE OFF;
SET SERVEROUTPUT ON;
WHENEVER SQLERROR CONTINUE;

-- ------------------------------------------------------------------------------
-- 1. DROP TRIGGERS
-- ------------------------------------------------------------------------------
DROP TRIGGER openrisow.tr_tbsprd_idl_bi;
DROP TRIGGER openrisow.tr_tbsprd_ils_bi;
DROP TRIGGER openrisow.tr_tbsprd_iup_bi;
DROP TRIGGER openrisow.tr_tbsprd_tout_bi;
DROP TRIGGER openrisow.tr_tbsprd_tans_bi;
DROP TRIGGER openrisow.tr_tbsprd_tck_bi;
DROP TRIGGER openrisow.tr_tbsprd_sch_bi;
DROP TRIGGER openrisow.tr_tbsprd_sprm_bi;
DROP TRIGGER openrisow.tr_tbsprd_prm_bi;
DROP TRIGGER openrisow.tr_tbsprd_senv_bi;
DROP TRIGGER openrisow.tr_tbsprd_pscr_bi;
DROP TRIGGER openrisow.tr_tbsprd_penv_bi;
DROP TRIGGER openrisow.tr_tbsprd_pfea_bi;
DROP TRIGGER openrisow.tr_tbsprd_scr_bi;
DROP TRIGGER openrisow.tr_tbsprd_usr_bu;
DROP TRIGGER openrisow.tr_tbsprd_usr_bi;
DROP TRIGGER openrisow.tr_tbsprd_fea_bi;
DROP TRIGGER openrisow.tr_tbsprd_prf_bi;
DROP TRIGGER openrisow.tr_tbsprd_env_bu;
DROP TRIGGER openrisow.tr_tbsprd_env_bi;
DROP TRIGGER openrisow.tr_tbsprd_agt_bi;
DROP TRIGGER openrisow.tr_tbsprd_aud_bi;
DROP TRIGGER openrisow.tr_tbsprd_ctl_bi;

-- ------------------------------------------------------------------------------
-- 2. DROP TABELAS (CASCADE CONSTRAINTS PURGE)
-- ------------------------------------------------------------------------------
DROP TABLE openrisow.tbsprd_input_delivery CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_input_listing CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_input_upload CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_ticket_output CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_ticket_answer CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_tickets CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_schedules CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_script_param CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_parameters CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_script_env CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_profile_script CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_profile_env CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_profile_feature CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_scripts CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_users CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_features CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_profiles CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_environments CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_agents CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_audit CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsprd_control CASCADE CONSTRAINTS PURGE;

-- ------------------------------------------------------------------------------
-- 3. DROP SEQUENCES
-- ------------------------------------------------------------------------------
DROP SEQUENCE openrisow.sq_tbsprd_input_delivery;
DROP SEQUENCE openrisow.sq_tbsprd_input_listing;
DROP SEQUENCE openrisow.sq_tbsprd_input_upload;
DROP SEQUENCE openrisow.sq_tbsprd_ticket_output;
DROP SEQUENCE openrisow.sq_tbsprd_ticket_answer;
DROP SEQUENCE openrisow.sq_tbsprd_tickets;
DROP SEQUENCE openrisow.sq_tbsprd_schedules;
DROP SEQUENCE openrisow.sq_tbsprd_script_param;
DROP SEQUENCE openrisow.sq_tbsprd_parameters;
DROP SEQUENCE openrisow.sq_tbsprd_script_env;
DROP SEQUENCE openrisow.sq_tbsprd_profile_script;
DROP SEQUENCE openrisow.sq_tbsprd_profile_env;
DROP SEQUENCE openrisow.sq_tbsprd_profile_feature;
DROP SEQUENCE openrisow.sq_tbsprd_scripts;
DROP SEQUENCE openrisow.sq_tbsprd_users;
DROP SEQUENCE openrisow.sq_tbsprd_features;
DROP SEQUENCE openrisow.sq_tbsprd_profiles;
DROP SEQUENCE openrisow.sq_tbsprd_environments;
DROP SEQUENCE openrisow.sq_tbsprd_agents;
DROP SEQUENCE openrisow.sq_tbsprd_audit;
DROP SEQUENCE openrisow.sq_tbsprd_control;

PROMPT Rollback do SSS concluido com sucesso.
EXIT;
