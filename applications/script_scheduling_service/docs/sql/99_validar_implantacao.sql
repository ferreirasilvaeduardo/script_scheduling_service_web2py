-- ==============================================================================
-- Validacao da Implantacao do SSS no Oracle 11gR2+
-- ==============================================================================
SET LINESIZE 220 PAGESIZE 100 COLSEP ' | ' FEEDBACK OFF VERIFY OFF ECHO OFF;

PROMPT ==============================================================================
PROMPT 1. OBJETOS FISICOS CRIADOS NO ESQUEMA
PROMPT ==============================================================================
SELECT 'TABELAS_TBSSS' AS objeto, count(*) AS quantidade FROM user_tables WHERE table_name LIKE 'TBSSS_%'
UNION ALL
SELECT 'SEQUENCES_TBSSS', count(*) FROM user_sequences WHERE sequence_name LIKE 'SQ_TBSSS_%'
UNION ALL
SELECT 'TRIGGERS_TBSSS', count(*) FROM user_triggers WHERE trigger_name LIKE 'TR_TBSSS_%'
UNION ALL
SELECT 'OBJETOS_INVALIDOS', count(*) FROM user_objects WHERE status = 'INVALID' AND object_name LIKE '%TBSSS_%';

PROMPT
PROMPT ==============================================================================
PROMPT 2. CONTAGEM DE REGISTROS POR TABELA DE CATALOGO E SEED
PROMPT ==============================================================================
SELECT 'tbsss_ambientes' AS tabela, count(*) AS total_registros FROM tbsss_ambientes
UNION ALL SELECT 'tbsss_perfis', count(*) FROM tbsss_perfis
UNION ALL SELECT 'tbsss_funcionalidades', count(*) FROM tbsss_funcionalidades
UNION ALL SELECT 'tbsss_perfil_func', count(*) FROM tbsss_perfil_func
UNION ALL SELECT 'tbsss_perfil_amb', count(*) FROM tbsss_perfil_amb
UNION ALL SELECT 'tbsss_scripts', count(*) FROM tbsss_scripts
UNION ALL SELECT 'tbsss_perfil_scr', count(*) FROM tbsss_perfil_scr
UNION ALL SELECT 'tbsss_script_amb', count(*) FROM tbsss_script_amb
UNION ALL SELECT 'tbsss_usuarios', count(*) FROM tbsss_usuarios
UNION ALL SELECT 'tbsss_parametros', count(*) FROM tbsss_parametros
UNION ALL SELECT 'tbsss_script_param', count(*) FROM tbsss_script_param
UNION ALL SELECT 'tbsss_controle', count(*) FROM tbsss_controle;

PROMPT
PROMPT ==============================================================================
PROMPT 3. USUARIOS CADASTRADOS E PERFIS
PROMPT ==============================================================================
SELECT u.id, u.login, u.nome, p.nome AS perfil, p.is_admin AS admin_perfil, u.ativo, SUBSTR(u.senha_hash, 1, 35) || '...' AS hash_prefix
FROM tbsss_usuarios u
JOIN tbsss_perfis p ON p.id = u.perfil_id
ORDER BY u.id;

PROMPT
PROMPT ==============================================================================
PROMPT 4. SCRIPTS UTILITARIOS HOMOLOGADOS (14 ROTINAS)
PROMPT ==============================================================================
SELECT id, nome, interpretador, tipo_param, max_qtd_parallel_env AS paral, timeout_seg AS tmout, SUBSTR(path_file, 1, 55) AS caminho
FROM tbsss_scripts
ORDER BY id;

PROMPT
PROMPT ==============================================================================
PROMPT 5. PERMISSOES DE SCRIPTS POR PERFIL
PROMPT ==============================================================================
SELECT p.nome AS perfil, count(ps.script_id) AS total_scripts_liberados
FROM tbsss_perfis p
LEFT JOIN tbsss_perfil_scr ps ON ps.perfil_id = p.id
GROUP BY p.nome
ORDER BY p.nome;

EXIT;
