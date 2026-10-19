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
DROP TRIGGER openrisow.tr_tbsss_trsp_bi;
DROP TRIGGER openrisow.tr_tbsss_tck_bi;
DROP TRIGGER openrisow.tr_tbsss_agd_bi;
DROP TRIGGER openrisow.tr_tbsss_sprm_bi;
DROP TRIGGER openrisow.tr_tbsss_prm_bi;
DROP TRIGGER openrisow.tr_tbsss_samb_bi;
DROP TRIGGER openrisow.tr_tbsss_pscr_bi;
DROP TRIGGER openrisow.tr_tbsss_pamb_bi;
DROP TRIGGER openrisow.tr_tbsss_pfnc_bi;
DROP TRIGGER openrisow.tr_tbsss_scr_bi;
DROP TRIGGER openrisow.tr_tbsss_usr_bu;
DROP TRIGGER openrisow.tr_tbsss_usr_bi;
DROP TRIGGER openrisow.tr_tbsss_fnc_bi;
DROP TRIGGER openrisow.tr_tbsss_per_bi;
DROP TRIGGER openrisow.tr_tbsss_amb_bu;
DROP TRIGGER openrisow.tr_tbsss_amb_bi;
DROP TRIGGER openrisow.tr_tbsss_agt_bi;
DROP TRIGGER openrisow.tr_tbsss_aud_bi;
DROP TRIGGER openrisow.tr_tbsss_ctl_bi;

-- ------------------------------------------------------------------------------
-- 2. DROP TABELAS (CASCADE CONSTRAINTS PURGE)
-- ------------------------------------------------------------------------------
DROP TABLE openrisow.tbsss_ticket_resp CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_tickets CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_agendamentos CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_script_param CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_parametros CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_script_amb CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_perfil_scr CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_perfil_amb CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_perfil_func CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_scripts CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_usuarios CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_funcionalidades CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_perfis CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_ambientes CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_agentes CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_auditoria CASCADE CONSTRAINTS PURGE;
DROP TABLE openrisow.tbsss_controle CASCADE CONSTRAINTS PURGE;

-- ------------------------------------------------------------------------------
-- 3. DROP SEQUENCES
-- ------------------------------------------------------------------------------
DROP SEQUENCE openrisow.sq_tbsss_ticket_resp;
DROP SEQUENCE openrisow.sq_tbsss_tickets;
DROP SEQUENCE openrisow.sq_tbsss_agendamentos;
DROP SEQUENCE openrisow.sq_tbsss_script_param;
DROP SEQUENCE openrisow.sq_tbsss_parametros;
DROP SEQUENCE openrisow.sq_tbsss_script_amb;
DROP SEQUENCE openrisow.sq_tbsss_perfil_scr;
DROP SEQUENCE openrisow.sq_tbsss_perfil_amb;
DROP SEQUENCE openrisow.sq_tbsss_perfil_func;
DROP SEQUENCE openrisow.sq_tbsss_scripts;
DROP SEQUENCE openrisow.sq_tbsss_usuarios;
DROP SEQUENCE openrisow.sq_tbsss_funcionalidades;
DROP SEQUENCE openrisow.sq_tbsss_perfis;
DROP SEQUENCE openrisow.sq_tbsss_ambientes;
DROP SEQUENCE openrisow.sq_tbsss_agentes;
DROP SEQUENCE openrisow.sq_tbsss_auditoria;
DROP SEQUENCE openrisow.sq_tbsss_controle;

PROMPT Rollback do SSS concluido com sucesso.
EXIT;
