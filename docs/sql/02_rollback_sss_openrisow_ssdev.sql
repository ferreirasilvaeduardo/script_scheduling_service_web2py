-- ==============================================================================
-- Script Scheduling Service (SSS) - Rollback / Desinstalacao Oracle 11gR2+
-- Gerado automaticamente a partir do registro sql_ident.py
-- Owner: openrisow
-- Prefixo: ssdev_
-- ==============================================================================
SET DEFINE OFF;
SET SERVEROUTPUT ON;
WHENEVER SQLERROR CONTINUE;

-- ------------------------------------------------------------------------------
-- 1. DROP TRIGGERS
-- ------------------------------------------------------------------------------
DROP TRIGGER openrisow.tr_ssdev_idl_bi;
DROP TRIGGER openrisow.tr_ssdev_ils_bi;
DROP TRIGGER openrisow.tr_ssdev_iup_bi;
DROP TRIGGER openrisow.tr_ssdev_tout_bi;
DROP TRIGGER openrisow.tr_ssdev_tans_bi;
DROP TRIGGER openrisow.tr_ssdev_tck_bi;
DROP TRIGGER openrisow.tr_ssdev_sch_bi;
DROP TRIGGER openrisow.tr_ssdev_sprm_bi;
DROP TRIGGER openrisow.tr_ssdev_prm_bi;
DROP TRIGGER openrisow.tr_ssdev_senv_bi;
DROP TRIGGER openrisow.tr_ssdev_pscr_bi;
DROP TRIGGER openrisow.tr_ssdev_penv_bi;
DROP TRIGGER openrisow.tr_ssdev_pfea_bi;
DROP TRIGGER openrisow.tr_ssdev_scr_bi;
DROP TRIGGER openrisow.tr_ssdev_usr_bu;
DROP TRIGGER openrisow.tr_ssdev_usr_bi;
DROP TRIGGER openrisow.tr_ssdev_fea_bi;
DROP TRIGGER openrisow.tr_ssdev_prf_bi;
DROP TRIGGER openrisow.tr_ssdev_env_bu;
DROP TRIGGER openrisow.tr_ssdev_env_bi;
DROP TRIGGER openrisow.tr_ssdev_agt_bi;
DROP TRIGGER openrisow.tr_ssdev_aud_bi;
DROP TRIGGER openrisow.tr_ssdev_ctl_bi;

-- ------------------------------------------------------------------------------
-- 2. DROP TABELAS (CASCADE CONSTRAINTS PURGE)
-- ------------------------------------------------------------------------------
DROP TABLE openrisow.ssdev_input_delivery CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_input_listing CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_input_upload CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_ticket_output CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_ticket_answer CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_tickets CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_schedules CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_script_param CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_parameters CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_script_env CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_profile_script CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_profile_env CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_profile_feature CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_scripts CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_users CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_features CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_profiles CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_environments CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_agents CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_audit CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.ssdev_control CASCADE CONSTRAINTS PURGE;

-- ------------------------------------------------------------------------------
-- 3. DROP SEQUENCES
-- ------------------------------------------------------------------------------
DROP SEQUENCE openrisow.sq_ssdev_input_delivery;
DROP SEQUENCE openrisow.sq_ssdev_input_listing;
DROP SEQUENCE openrisow.sq_ssdev_input_upload;
DROP SEQUENCE openrisow.sq_ssdev_ticket_output;
DROP SEQUENCE openrisow.sq_ssdev_ticket_answer;
DROP SEQUENCE openrisow.sq_ssdev_tickets;
DROP SEQUENCE openrisow.sq_ssdev_schedules;
DROP SEQUENCE openrisow.sq_ssdev_script_param;
DROP SEQUENCE openrisow.sq_ssdev_parameters;
DROP SEQUENCE openrisow.sq_ssdev_script_env;
DROP SEQUENCE openrisow.sq_ssdev_profile_script;
DROP SEQUENCE openrisow.sq_ssdev_profile_env;
DROP SEQUENCE openrisow.sq_ssdev_profile_feature;
DROP SEQUENCE openrisow.sq_ssdev_scripts;
DROP SEQUENCE openrisow.sq_ssdev_users;
DROP SEQUENCE openrisow.sq_ssdev_features;
DROP SEQUENCE openrisow.sq_ssdev_profiles;
DROP SEQUENCE openrisow.sq_ssdev_environments;
DROP SEQUENCE openrisow.sq_ssdev_agents;
DROP SEQUENCE openrisow.sq_ssdev_audit;
DROP SEQUENCE openrisow.sq_ssdev_control;

PROMPT Rollback do SSS concluido com sucesso.
EXIT;
