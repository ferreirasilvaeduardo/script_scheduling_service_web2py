# -*- coding: utf-8 -*-
"""Script de inicializacao de banco Oracle, DDL, seed e auditoria do SSS (F7.1).

Executa as 8 fases de inicializacao de forma idempotente, segura e auditavel
a partir do registro unico sql_ident.py.
"""
import argparse
import collections
import getpass
import json
import logging
import os
import re
import sys

# Ajusta sys.path para importar modulos do SSS
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(_scripts_dir)
_modules_dir = os.path.join(_app_dir, "modules")
for _p in (_app_dir, _modules_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ddl_builder  # noqa: E402
import security  # noqa: E402
import sql_ident  # noqa: E402
import sss_config  # noqa: E402
import sss_logging  # noqa: E402

logger = logging.getLogger("sss_init_db")


def _registrar_critico_config(msg, cfg=None):
    """Emite log de nivel CRITICAL conforme README §13 e AGENTS §3.1."""
    log_dir = None
    if cfg and hasattr(cfg, "logging") and hasattr(cfg.logging, "log_dir"):
        log_dir = cfg.logging.log_dir
    elif cfg and hasattr(cfg, "log_dir"):
        log_dir = getattr(cfg, "log_dir")

    # Garante envio para o logger e/ou stderr se ainda nao configurado
    if logger.handlers or logging.getLogger().handlers:
        logger.critical(msg, extra={"agent": "-", "ticket": "-", "action": "CONFIG"})
    else:
        sss_logging.log_initial_critical("sss_init_db", msg, log_dir)


def _conectar(cfg, usuario, senha):
    """Estabelece conexao Oracle com a conta informada usando db_conn.connect (F7.2)."""
    import db_conn
    segredos_dummy = collections.namedtuple("SegredosDummy", ["oracle"])(
        oracle=collections.namedtuple("OracleDummy", ["password"])(password=senha)
    )
    return db_conn.connect(cfg, segredos_dummy, papel="dono", user=usuario, password=senha)


def _validar_schema_descartavel_dev(cfg, usuario_dono, conn):
    """Valida requisitos de seguranca para schema descartavel em DEV (F7.1)."""
    dsn_env = os.environ.get("SSS_TEST_DSN")
    owner_env = os.environ.get("SSS_TEST_OWNER")
    disposable = os.environ.get("SSS_TEST_SCHEMA_DISPOSABLE")

    if not dsn_env or not owner_env or disposable != "1":
        raise RuntimeError(
            "Execucao de DDL real exige ambiente DEV com SSS_TEST_DSN, "
            "SSS_TEST_OWNER (prefixo SSS_TEST_) e SSS_TEST_SCHEMA_DISPOSABLE=1"
        )

    if not owner_env.startswith("SSS_TEST_"):
        raise RuntimeError("SSS_TEST_OWNER deve comecar com o prefixo 'SSS_TEST_'")

    if cfg.oracle.dsn != dsn_env:
        raise RuntimeError(
            "DSN configurado ('%s') diverge de SSS_TEST_DSN ('%s')" % (cfg.oracle.dsn, dsn_env)
        )

    if cfg.oracle.owner != owner_env:
        raise RuntimeError(
            "Owner configurado ('%s') diverge de SSS_TEST_OWNER ('%s')" % (cfg.oracle.owner, owner_env)
        )

    cursor = conn.cursor()
    try:
        cursor.execute("SELECT USER FROM DUAL")
        row = cursor.fetchone()
        usuario_banco = row[0] if row else ""
        if usuario_banco.upper() != usuario_dono.upper():
            raise RuntimeError(
                "Usuario conectado no Oracle ('%s') diverge do usuario dono ('%s')"
                % (usuario_banco, usuario_dono)
            )
    finally:
        cursor.close()


def _consultar_existencia(cursor, owner):
    """Le todos os objetos, constraints e indices existentes do owner em conjuntos indexados."""
    v_owner = owner.upper()

    # 1. ALL_OBJECTS (Sequences, Tables, Triggers)
    cursor.execute(
        "SELECT OBJECT_TYPE, OBJECT_NAME FROM ALL_OBJECTS WHERE OWNER = :o",
        {"o": v_owner}
    )
    objetos = set()
    for row in cursor.fetchall():
        tipo, nome = row[0], row[1]
        objetos.add((tipo.upper(), nome.lower()))

    # 2. ALL_CONSTRAINTS
    cursor.execute(
        "SELECT CONSTRAINT_NAME FROM ALL_CONSTRAINTS WHERE OWNER = :o",
        {"o": v_owner}
    )
    constraints = set()
    for row in cursor.fetchall():
        constraints.add(row[0].lower())

    # 3. ALL_INDEXES
    cursor.execute(
        "SELECT INDEX_NAME FROM ALL_INDEXES WHERE OWNER = :o",
        {"o": v_owner}
    )
    indices = set()
    for row in cursor.fetchall():
        indices.add(row[0].lower())

    return {
        "objetos": objetos,
        "constraints": constraints,
        "indices": indices,
    }


def _objeto_existe(tipo, nome, mapa_existencia):
    """Verifica se um determinado objeto ja existe no dicionario de dados."""
    nome_low = nome.lower()
    if tipo in ("SEQUENCE", "TABLE", "TRIGGER"):
        return (tipo, nome_low) in mapa_existencia["objetos"]
    elif tipo == "CONSTRAINT":
        return nome_low in mapa_existencia["constraints"]
    elif tipo == "INDEX":
        return nome_low in mapa_existencia["indices"]
    return False


def _executar_ddl_fases(conn, owner, prefixo, lob_storage="SECUREFILE", log_fn=print):
    """Aplica o DDL fase a fase de forma idempotente (1 a 6)."""
    cursor = conn.cursor()
    try:
        mapa = _consultar_existencia(cursor, owner)
        instrucoes = ddl_builder.build_ddl_statements(owner, prefixo, lob_storage=lob_storage)

        total = len(instrucoes)
        sucesso_count = 0
        skip_count = 0

        for idx, item in enumerate(instrucoes, start=1):
            if _objeto_existe(item.tipo, item.nome, mapa):
                skip_count += 1
                log_fn("  [{}/{}] SKIP: {} {} ja existe".format(idx, total, item.tipo, item.nome))
                continue

            log_fn("  [{}/{}] CRIANDO: {} {}...".format(idx, total, item.tipo, item.nome))
            try:
                cursor.execute(item.sql)
                sucesso_count += 1
            except Exception as exc:
                msg = "Fase {} - Falha ao criar {} {}: {}".format(item.fase, item.tipo, item.nome, exc)
                logger.error(msg, extra={"agent": "-", "ticket": "-", "action": "INIT_DB"})
                raise RuntimeError(msg)

        log_fn("DDL concluido: {} criados, {} ignorados (ja existiam)".format(sucesso_count, skip_count))
    finally:
        cursor.close()


def _executar_seed(conn, owner, prefixo, admin_login=None, admin_nome=None, admin_senha=None, log_fn=print):
    """Executa o seed idempotente via MERGE (Fase 7, README §4.3.D e §11.1)."""
    esquema = sql_ident.names(prefixo)
    cursor = conn.cursor()
    try:
        # 1. Catálogo de Funcionalidades
        tb_fnc = "{}.{}".format(owner, esquema["features"]["tabela"])
        sq_fnc = "{}.{}".format(owner, esquema["features"]["sequence"])
        sql_merge_fnc = """
        MERGE INTO {tb_fnc} dst
        USING (SELECT :code AS code FROM DUAL) src
        ON (dst.code = src.code)
        WHEN MATCHED THEN
          UPDATE SET dst.name = :name,
                     dst.module = :module,
                     dst.description = :description,
                     dst.active = 'Y',
                     dst.updated_at = SYSDATE,
                     dst.updated_by = 'SYSTEM:init_db'
          WHERE dst.name <> :name
             OR dst.module <> :module
             OR dst.description <> :description
             OR dst.active <> 'Y'
        WHEN NOT MATCHED THEN
          INSERT (id, code, name, module, description, active, created_at, created_by)
          VALUES ({sq_fnc}.NEXTVAL, :code, :name, :module, :description, 'Y', SYSDATE, 'SYSTEM:init_db')
        """.format(tb_fnc=tb_fnc, sq_fnc=sq_fnc)

        for mod, cod, nom, desc in ddl_builder.FEATURE_CATALOG:
            cursor.execute(sql_merge_fnc, {
                "code": cod,
                "name": nom,
                "module": mod,
                "description": desc,
            })

        # 2. Perfis padrao e matrizes de permissao (DEFAULT_PROFILES)
        tb_per = "{}.{}".format(owner, esquema["profiles"]["tabela"])
        sq_per = "{}.{}".format(owner, esquema["profiles"]["sequence"])
        tb_pfnc = "{}.{}".format(owner, esquema["profile_feature"]["tabela"])
        sq_pfnc = "{}.{}".format(owner, esquema["profile_feature"]["sequence"])
        tb_pamb = "{}.{}".format(owner, esquema["profile_env"]["tabela"])
        sq_pamb = "{}.{}".format(owner, esquema["profile_env"]["sequence"])

        sql_merge_per = """
        MERGE INTO {tb_per} dst
        USING (SELECT :name AS name FROM DUAL) src
        ON (dst.name = src.name)
        WHEN MATCHED THEN
          UPDATE SET dst.description = :description,
                     dst.is_admin = :is_admin,
                     dst.active = 'Y',
                     dst.updated_at = SYSDATE,
                     dst.updated_by = 'SYSTEM:init_db'
          WHERE dst.is_admin <> :is_admin
             OR dst.active <> 'Y'
             OR NVL(dst.description, '~') <> :description
        WHEN NOT MATCHED THEN
          INSERT (id, name, description, is_admin, perm_version, active, created_at, created_by)
          VALUES ({sq_per}.NEXTVAL, :name, :description, :is_admin, 1, 'Y', SYSDATE, 'SYSTEM:init_db')
        """.format(tb_per=tb_per, sq_per=sq_per)

        sql_merge_pfnc = """
        MERGE INTO {tb_pfnc} dst
        USING (
          SELECT p.id AS profile_id, f.id AS feature_id
            FROM {tb_per} p, {tb_fnc} f
           WHERE p.name = :per_nome AND f.code = :code
        ) src
        ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
        WHEN NOT MATCHED THEN
          INSERT (id, profile_id, feature_id, created_at, created_by)
          VALUES ({sq_pfnc}.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db')
        """.format(tb_pfnc=tb_pfnc, sq_pfnc=sq_pfnc, tb_per=tb_per, tb_fnc=tb_fnc)

        sql_merge_pamb = """
        MERGE INTO {tb_pamb} dst
        USING (
          SELECT p.id AS profile_id, a.id AS environment_id
            FROM {tb_per} p, {tb_amb} a
           WHERE p.name = :per_nome AND a.name = :a_nome
        ) src
        ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
        WHEN NOT MATCHED THEN
          INSERT (id, profile_id, environment_id, created_at, created_by)
          VALUES ({sq_pamb}.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db')
        """.format(tb_pamb=tb_pamb, sq_pamb=sq_pamb, tb_per=tb_per, tb_amb=tb_amb)

        for per_nome, per_desc, is_adm, per_funcs, per_ambs in ddl_builder.DEFAULT_PROFILES:
            cursor.execute(sql_merge_per, {
                "name": per_nome,
                "description": per_desc,
                "is_admin": is_adm,
            })
            for f_cod in per_funcs:
                cursor.execute(sql_merge_pfnc, {"per_nome": per_nome, "code": f_cod})
            for a_nome in per_ambs:
                cursor.execute(sql_merge_pamb, {"per_nome": per_nome, "a_nome": a_nome})

        # 4. Ambientes padrão do sistema
        tb_amb = "{}.{}".format(owner, esquema["environments"]["tabela"])
        sq_amb = "{}.{}".format(owner, esquema["environments"]["sequence"])
        sql_merge_amb = """
        MERGE INTO {tb_amb} dst
        USING (SELECT :name AS name FROM DUAL) src
        ON (dst.name = src.name)
        WHEN MATCHED THEN
          UPDATE SET dst.description = :description,
                     dst.connection = :connection,
                     dst.active = 'Y',
                     dst.updated_at = SYSDATE,
                     dst.updated_by = 'SYSTEM:init_db'
          WHERE dst.active <> 'Y'
             OR NVL(dst.description, '~') <> NVL(:description, '~')
             OR NVL(dst.connection, '~') <> NVL(:connection, '~')
        WHEN NOT MATCHED THEN
          INSERT (id, name, description, connection, active, created_at, created_by)
          VALUES ({sq_amb}.NEXTVAL, :name, :description, :connection, 'Y', SYSDATE, 'SYSTEM:init_db')
        """.format(tb_amb=tb_amb, sq_amb=sq_amb)

        for amb_nome, amb_desc, amb_conn in ddl_builder.DEFAULT_ENVIRONMENTS:
            cursor.execute(sql_merge_amb, {
                "name": amb_nome,
                "description": amb_desc,
                "connection": amb_conn,
            })

        # 5. Parametros padrao reutilizaveis
        tb_prm = "{}.{}".format(owner, esquema["parameters"]["tabela"])
        sq_prm = "{}.{}".format(owner, esquema["parameters"]["sequence"])
        sql_merge_prm = """
        MERGE INTO {tb_prm} dst
        USING (SELECT :code AS code FROM DUAL) src
        ON (dst.code = src.code)
        WHEN MATCHED THEN
          UPDATE SET dst.param_flag = :param_flag,
                     dst.label = :label,
                     dst.description = :description,
                     dst.component_type = :component_type,
                     dst.options_json = :options_json,
                     dst.default_value = :default_value,
                     dst.sensitive = 'N',
                     dst.active = 'Y',
                     dst.updated_at = SYSDATE,
                     dst.updated_by = 'SYSTEM:init_db'
          WHERE dst.active <> 'Y'
             OR NVL(dst.param_flag, '~') <> NVL(:param_flag, '~')
             OR dst.label <> :label
             OR NVL(dst.description, '~') <> NVL(:description, '~')
             OR dst.component_type <> :component_type
             OR NVL(dst.options_json, '~') <> NVL(:options_json, '~')
             OR NVL(dst.default_value, '~') <> NVL(:default_value, '~')
        WHEN NOT MATCHED THEN
          INSERT (id, code, param_flag, label, description, component_type, options_json, default_value, validation_regex, sensitive, active, created_at, created_by)
          VALUES ({sq_prm}.NEXTVAL, :code, :param_flag, :label, :description, :component_type, :options_json, :default_value, NULL, 'N', 'Y', SYSDATE, 'SYSTEM:init_db')
        """.format(tb_prm=tb_prm, sq_prm=sq_prm)

        for cod, p_nom, lbl, desc, tcomp, opc, vpad in ddl_builder.DEFAULT_PARAMETERS:
            cursor.execute(sql_merge_prm, {
                "code": cod,
                "param_flag": p_nom,
                "label": lbl,
                "description": desc,
                "component_type": tcomp,
                "options_json": opc,
                "default_value": vpad,
            })

        # 6. Scripts utilitarios padrao e associacoes
        tb_scr = "{}.{}".format(owner, esquema["scripts"]["tabela"])
        sq_scr = "{}.{}".format(owner, esquema["scripts"]["sequence"])
        tb_samb = "{}.{}".format(owner, esquema["script_env"]["tabela"])
        sq_samb = "{}.{}".format(owner, esquema["script_env"]["sequence"])
        tb_pscr = "{}.{}".format(owner, esquema["profile_script"]["tabela"])
        sq_pscr = "{}.{}".format(owner, esquema["profile_script"]["sequence"])
        tb_sprm = "{}.{}".format(owner, esquema["script_param"]["tabela"])
        sq_sprm = "{}.{}".format(owner, esquema["script_param"]["sequence"])

        sql_merge_scr = """
        MERGE INTO {tb_scr} dst
        USING (SELECT :name AS name FROM DUAL) src
        ON (dst.name = src.name)
        WHEN MATCHED THEN
          UPDATE SET dst.description = :description,
                     dst.script_group = :script_group,
                     dst.category = :category,
                     dst.stage = :stage,
                     dst.interpreter = :interpreter,
                     dst.path_file = :path_file,
                     dst.param_type = :param_type,
                     dst.max_parallel_env = :max_paral,
                     dst.timeout_s = :timeout_s,
                     dst.active = 'Y',
                     dst.updated_at = SYSDATE,
                     dst.updated_by = 'SYSTEM:init_db'
          WHERE dst.active <> 'Y'
             OR NVL(dst.description, '~') <> NVL(:description, '~')
             OR NVL(dst.script_group, '~') <> NVL(:script_group, '~')
             OR NVL(dst.category, '~') <> NVL(:category, '~')
             OR NVL(dst.stage, '~') <> NVL(:stage, '~')
             OR dst.interpreter <> :interpreter
             OR dst.path_file <> :path_file
             OR dst.param_type <> :param_type
             OR dst.max_parallel_env <> :max_paral
             OR NVL(dst.timeout_s, 0) <> NVL(:timeout_s, 0)
        WHEN NOT MATCHED THEN
          INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
          VALUES ({sq_scr}.NEXTVAL, :name, :description, :script_group, :category, :stage, :interpreter, :path_file, :param_type, :max_paral, :timeout_s, 'Y', SYSDATE, 'SYSTEM:init_db')
        """.format(tb_scr=tb_scr, sq_scr=sq_scr)

        sql_merge_samb = """
        MERGE INTO {tb_samb} dst
        USING (
          SELECT s.id AS script_id, a.id AS environment_id
            FROM {tb_scr} s, {tb_amb} a
           WHERE s.name = :s_nome AND a.name = :amb_nome
        ) src
        ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
        WHEN NOT MATCHED THEN
          INSERT (id, script_id, environment_id, created_at, created_by)
          VALUES ({sq_samb}.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db')
        """.format(tb_samb=tb_samb, sq_samb=sq_samb, tb_scr=tb_scr, tb_amb=tb_amb)

        sql_merge_pscr = """
        MERGE INTO {tb_pscr} dst
        USING (
          SELECT p.id AS profile_id, s.id AS script_id
            FROM {tb_per} p, {tb_scr} s
           WHERE p.name = :per_nome AND s.name = :s_nome
        ) src
        ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
        WHEN NOT MATCHED THEN
          INSERT (id, profile_id, script_id, created_at, created_by)
          VALUES ({sq_pscr}.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db')
        """.format(tb_pscr=tb_pscr, sq_pscr=sq_pscr, tb_per=tb_per, tb_scr=tb_scr)

        sql_merge_sprm = """
        MERGE INTO {tb_sprm} dst
        USING (
          SELECT s.id AS script_id, p.id AS parameter_id
            FROM {tb_scr} s, {tb_prm} p
           WHERE s.name = :s_nome AND p.code = :p_cod
        ) src
        ON (dst.script_id = src.script_id AND dst.parameter_id = src.parameter_id)
        WHEN MATCHED THEN
          UPDATE SET dst.sort_order = :sort_order,
                     dst.required = :required,
                     dst.default_value_override = :vsub,
                     dst.updated_at = SYSDATE,
                     dst.updated_by = 'SYSTEM:init_db'
          WHERE dst.sort_order <> :sort_order
             OR dst.required <> :required
             OR NVL(dst.default_value_override, '~') <> NVL(:vsub, '~')
        WHEN NOT MATCHED THEN
          INSERT (id, script_id, parameter_id, sort_order, required, default_value_override, created_at, created_by)
          VALUES ({sq_sprm}.NEXTVAL, src.script_id, src.parameter_id, :sort_order, :required, :vsub, SYSDATE, 'SYSTEM:init_db')
        """.format(tb_sprm=tb_sprm, sq_sprm=sq_sprm, tb_scr=tb_scr, tb_prm=tb_prm)

        for s_nome, s_desc, s_grp, s_cat, s_etp, s_int, s_path, s_tpar, s_paral, s_tmout, s_params in ddl_builder.DEFAULT_SCRIPTS:
            cursor.execute(sql_merge_scr, {
                "name": s_nome,
                "description": s_desc,
                "script_group": s_grp,
                "category": s_cat,
                "stage": s_etp,
                "interpreter": s_int,
                "path_file": s_path,
                "param_type": s_tpar,
                "max_paral": s_paral,
                "timeout_s": s_tmout,
            })

            for amb_nome, _, _ in ddl_builder.DEFAULT_ENVIRONMENTS:
                cursor.execute(sql_merge_samb, {"s_nome": s_nome, "amb_nome": amb_nome})

            for per_nome, _, _, _, _ in ddl_builder.DEFAULT_PROFILES:
                cursor.execute(sql_merge_pscr, {"per_nome": per_nome, "s_nome": s_nome})

            for p_cod, p_ord, p_obrig, p_vsub in s_params:
                cursor.execute(sql_merge_sprm, {
                    "s_nome": s_nome,
                    "p_cod": p_cod,
                    "sort_order": p_ord,
                    "required": p_obrig,
                    "vsub": p_vsub,
                })

        # 7. Linha de tbsss_control
        tb_ctl = "{}.{}".format(owner, esquema["control"]["tabela"])
        sql_merge_ctl = """
        MERGE INTO {tb_ctl} dst
        USING (SELECT 1 AS id FROM DUAL) src
        ON (dst.id = src.id)
        WHEN NOT MATCHED THEN
          INSERT (id, schema_version, version_applied_at, version_applied_by)
          VALUES (1, :schema_version, SYSDATE, 'SYSTEM:init_db')
        """.format(tb_ctl=tb_ctl)
        cursor.execute(sql_merge_ctl, {"schema_version": sql_ident.SCHEMA_VERSION})

        # 8. Usuarios padrao da aplicacao e homologacao (DEFAULT_USERS)
        tb_usr = "{}.{}".format(owner, esquema["users"]["tabela"])
        sq_usr = "{}.{}".format(owner, esquema["users"]["sequence"])

        sql_merge_usr = """
        MERGE INTO {tb_usr} dst
        USING (
          SELECT :login AS login, p.id AS profile_id
            FROM {tb_per} p
           WHERE p.name = :perfil
        ) src
        ON (dst.login = src.login)
        WHEN MATCHED THEN
          UPDATE SET dst.name = :name,
                     dst.profile_id = src.profile_id,
                     dst.active = 'Y',
                     dst.updated_at = SYSDATE,
                     dst.updated_by = 'SYSTEM:init_db'
          WHERE dst.name <> :name
             OR dst.profile_id <> src.profile_id
             OR dst.active <> 'Y'
        WHEN NOT MATCHED THEN
          INSERT (id, login, name, password_hash, profile_id, active, session_epoch, failed_attempts, created_at, created_by)
          VALUES ({sq_usr}.NEXTVAL, :login, :name, :password_hash, src.profile_id, 'Y', 0, 0, SYSDATE, 'SYSTEM:init_db')
        """.format(tb_usr=tb_usr, sq_usr=sq_usr, tb_per=tb_per)

        for u_login, u_nome, u_perfil in ddl_builder.DEFAULT_USERS:
            nome_final = admin_nome if (u_login == "admin" and admin_nome) else u_nome
            if u_login == "admin" and admin_senha:
                hash_final = security.hash_password(admin_senha)
            else:
                hash_final = ddl_builder.HOMOLOGATION_DEFAULT_PASSWORD_HASH

            cursor.execute(sql_merge_usr, {
                "login": u_login,
                "name": nome_final,
                "perfil": u_perfil,
                "password_hash": hash_final,
            })
            log_fn("Usuario '%s' homologado no perfil '%s'" % (u_login, u_perfil))

        conn.commit()
        log_fn("Seed concluido com sucesso")
    except Exception as exc:
        conn.rollback()
        msg = "Falha no seed: %s" % exc
        logger.error(msg, extra={"agent": "-", "ticket": "-", "action": "INIT_DB"})
        raise RuntimeError(msg)
    finally:
        cursor.close()


def _coletar_estatisticas(conn, owner, prefixo, log_fn=print):
    """Coleta estatisticas apenas em tabelas com linhas (Fase 8, CR-007, R-29)."""
    cursor = conn.cursor()
    esquema = sql_ident.names(prefixo)
    try:
        for entidade, t in esquema.items():
            tabela_nome = t["tabela"]
            # Checa se possui linhas
            cursor.execute("SELECT COUNT(*) FROM {}.{} WHERE ROWNUM = 1".format(owner, tabela_nome))
            row = cursor.fetchone()
            has_rows = (row and row[0] > 0)
            if has_rows:
                log_fn("  Coletando estatisticas para {}.{}...".format(owner, tabela_nome))
                sql_stats = """
                BEGIN
                    DBMS_STATS.GATHER_TABLE_STATS(
                        ownname => :own,
                        tabname => :tab,
                        cascade => TRUE
                    );
                END;
                """
                cursor.execute(sql_stats, {"own": owner.upper(), "tab": tabela_nome.upper()})
            else:
                log_fn("  {}.{} vazia (pula estatisticas para nao fixar planos ruins)".format(owner, tabela_nome))
    finally:
        cursor.close()


def _conferir_esquema(conn, owner, prefixo, log_fn=print):
    """Confere esquema real do banco contra o registro sql_ident (README §11.1, CR-008, R-14)."""
    esquema = sql_ident.names(prefixo)
    cursor = conn.cursor()
    divergencias = []

    try:
        # 1. Checagem de Objetos Invalidos (apenas objetos pertencentes ao SSS)
        idents_sss = {i.upper() for i in esquema.all_identifiers(incluir_colunas=False)}
        cursor.execute(
            "SELECT OBJECT_TYPE, OBJECT_NAME FROM ALL_OBJECTS WHERE OWNER = :o AND STATUS = 'INVALID'",
            {"o": owner.upper()}
        )
        for obj_tipo, obj_nome in cursor.fetchall():
            nome_u = obj_nome.upper()
            if nome_u in idents_sss or nome_u.startswith(prefixo.upper()) or nome_u.startswith("SQ_" + prefixo.upper()) or nome_u.startswith("TR_" + prefixo.upper()):
                cursor.execute(
                    "SELECT LINE, POSITION, TEXT FROM ALL_ERRORS WHERE OWNER = :o AND NAME = :n",
                    {"o": owner.upper(), "n": obj_nome}
                )
                erros = [r[2].strip() for r in cursor.fetchall()]
                detalhe_erros = "; ".join(erros) if erros else "Sem detalhes em ALL_ERRORS"
                divergencias.append("Objeto invalido: {} {} ({})".format(obj_tipo, obj_nome, detalhe_erros))

        # 2. Checagem de Colunas e Tipos
        for entidade, t in esquema.items():
            tabela_nome = t["tabela"].upper()
            cursor.execute("""
                SELECT COLUMN_NAME, DATA_TYPE, CHAR_LENGTH, DATA_PRECISION, DATA_SCALE, NULLABLE, DATA_DEFAULT
                  FROM ALL_TAB_COLUMNS
                 WHERE OWNER = :o AND TABLE_NAME = :t
                 ORDER BY COLUMN_ID
            """, {"o": owner.upper(), "t": tabela_nome})
            colunas_banco = {}
            for row in cursor.fetchall():
                c_nome = row[0].lower()
                colunas_banco[c_nome] = {
                    "data_type": row[1],
                    "char_length": row[2],
                    "precision": row[3],
                    "scale": row[4],
                    "nullable": row[5],
                    "data_default": row[6],
                }

            # Verifica se colunas esperadas existem
            for col_esperada, col_info in t["colunas"].items():
                if col_esperada not in colunas_banco:
                    divergencias.append("Coluna ausente: {}.{}".format(t["tabela"], col_esperada))
                    continue

                b_col = colunas_banco[col_esperada]
                # Valida Nullable
                esperado_null = "N" if col_info.get("not_null") else "Y"
                if b_col["nullable"] != esperado_null:
                    divergencias.append(
                        "Coluna {}.{} divergencia de NULLABLE (esperado: {}, real: {})".format(
                            t["tabela"], col_esperada, esperado_null, b_col["nullable"]
                        )
                    )

                # Valida Default (normalizado)
                if col_info.get("default") is not None:
                    def_esperado = sql_ident.normalize_expression(col_info["default"])
                    def_real = sql_ident.normalize_expression(b_col["data_default"])
                    if def_esperado != def_real:
                        divergencias.append(
                            "Coluna {}.{} divergencia de DEFAULT (esperado: '{}', real: '{}')".format(
                                t["tabela"], col_esperada, def_esperado, def_real
                            )
                        )

            # Verifica colunas sobressalentes
            for c_nome in colunas_banco:
                if c_nome not in t["colunas"]:
                    divergencias.append("Coluna extra nao registrada: {}.{}".format(t["tabela"], c_nome))

        # 3. Checagem de CKs (normalizadas, ignorando SYS_C% de NOT NULL)
        for entidade, t in esquema.items():
            tabela_nome = t["tabela"].upper()
            cursor.execute("""
                SELECT CONSTRAINT_NAME, SEARCH_CONDITION
                  FROM ALL_CONSTRAINTS
                 WHERE OWNER = :o AND TABLE_NAME = :t AND CONSTRAINT_TYPE = 'C'
            """, {"o": owner.upper(), "t": tabela_nome})
            cks_banco = {}
            for c_nome, s_cond in cursor.fetchall():
                # Ignora SYS_C% que apenas validam IS NOT NULL
                if sql_ident.is_system_not_null_ck(c_nome, s_cond):
                    continue
                cks_banco[c_nome.lower()] = s_cond

            for ck_esperada, ck_info in t["cks"].items():
                if ck_esperada not in cks_banco:
                    divergencias.append("Constraint CK ausente: {}.{}".format(t["tabela"], ck_esperada))
                    continue

                cond_real = sql_ident.normalize_expression(cks_banco[ck_esperada])
                cond_esp = sql_ident.normalize_expression(ck_info["expr"])
                if cond_real != cond_esp:
                    divergencias.append(
                        "Constraint CK {}.{} condicao divergente (esperado: '{}', real: '{}')".format(
                            t["tabela"], ck_esperada, cond_esp, cond_real
                        )
                    )

        # 4. Checagem de Indices
        for entidade, t in esquema.items():
            for ix_esperado, ix_info in t["indices"].items():
                cursor.execute("""
                    SELECT INDEX_NAME, UNIQUENESS
                      FROM ALL_INDEXES
                     WHERE OWNER = :o AND INDEX_NAME = :i
                """, {"o": owner.upper(), "i": ix_esperado.upper()})
                row = cursor.fetchone()
                if not row:
                    divergencias.append("Indice ausente: {}".format(ix_esperado))
                    continue

                is_unique = (row[1] == "UNIQUE")
                esperado_unique = bool(ix_info.get("unico", False))
                if is_unique != esperado_unique:
                    divergencias.append(
                        "Indice {} divergencia de unicidade (esperado: {}, real: {})".format(
                            ix_esperado, esperado_unique, is_unique
                        )
                    )

        if divergencias:
            log_fn("Divergencias detectadas na conferencia de esquema (total: %d):" % len(divergencias))
            for d in divergencias:
                log_fn("  - " + d)
            return False, divergencias

        log_fn("Conferencia de esquema: 100% compativel com o registro sql_ident")
        return True, []
    finally:
        cursor.close()


def _parse_grants_arg(arg_str):
    """Faz o parse do argumento --grants-to web=u1,agente=u2,..."""
    papeis = {}
    if not arg_str:
        return papeis
    partes = arg_str.split(",")
    for p in partes:
        p = p.strip()
        if not p:
            continue
        if "=" not in p:
            raise ValueError("Formato invalido para --grants-to: '%s'. Use papel=usuario" % p)
        papel, usr = p.split("=", 1)
        papel = papel.strip().lower()
        usr = usr.strip()
        if papel not in ("web", "agent", "purge", "monitor"):
            raise ValueError("Papel desconhecido em --grants-to: '%s'" % papel)
        papeis[papel] = usr
    return papeis


def _existe_esquema_1(conn, owner, prefixo):
    """Tabela de controle do esquema anterior ao CR-016a presente: o esquema novo nao convive com ele."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM all_tables WHERE owner = :o AND table_name = :t",
                       o=owner.upper(), t=(prefixo + sql_ident.LEGACY_CONTROL_TABLE).upper())
        return int(cursor.fetchone()[0]) > 0
    finally:
        cursor.close()


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        description="Bootstrap de DDL e seed Oracle 11gR2 do SSS (F7.1)",
        add_help=True,
    )
    parser.add_argument("--config", dest="config", default=None, help="Caminho do config.ini")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Imprime o DDL sem conectar")
    parser.add_argument("--lob-basicfile", dest="lob_basicfile", action="store_true", help="Fallback LOB BASICFILE")
    parser.add_argument("--owner-user", dest="usuario_dono", default=None, help="Usuario dono do esquema")
    parser.add_argument("--admin-login", dest="admin_login", default=None, help="Login do administrador inicial")
    parser.add_argument("--admin-name", dest="admin_nome", default=None, help="Nome do administrador inicial")
    parser.add_argument("--stats", dest="stats", action="store_true", default=True, help="Coleta estatisticas")
    parser.add_argument("--no-stats", dest="stats", action="store_false", help="Nao coleta estatisticas")
    parser.add_argument("--grants-to", dest="grants_para", default=None, help="web=u1,agent=u2,purge=u3,monitor=u4")
    parser.add_argument("--real-schema", dest="schema_real", action="store_true", default=False, help="Permite aplicacao em schema real de banco sem exigir prefixo SSS_TEST_")
    parser.add_argument("--generate-sql", dest="gerar_sql", default=None, help="Diretorio de saida para salvar os arquivos .sql de implantacao e rollback")

    # Rejeita argumentos desconhecidos
    try:
        args, desconhecidos = parser.parse_known_args(argv)
        if desconhecidos:
            msg = "Argumentos nao suportados: %s" % (" ".join(desconhecidos))
            _registrar_critico_config(msg)
            print(msg, file=sys.stderr)
            return 2
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2

    # Carrega configuracao
    cfg = None
    caminho_cfg = args.config or sss_config.default_config_path()
    if not os.path.isfile(caminho_cfg):
        exemplo = os.path.join(os.path.dirname(caminho_cfg), "config.ini.example")
        if os.path.isfile(exemplo):
            caminho_cfg = exemplo

    try:
        cfg = sss_config.load(caminho_cfg)
    except Exception as exc:
        msg = "Falha ao carregar configuracao: %s" % exc
        _registrar_critico_config(msg)
        print(msg, file=sys.stderr)
        return 2

    owner = cfg.oracle.owner
    prefixo = cfg.oracle.table_prefix
    lob_storage = "BASICFILE" if args.lob_basicfile else "SECUREFILE"

    # Valida owner e prefixo antes de qualquer acao
    try:
        sql_ident.validate_owner(owner)
        sql_ident.validate_prefix(prefixo)
        sql_ident.validate_registry(prefixo)
    except Exception as exc:
        msg = "Falha de configuracao em identificadores Oracle: %s" % exc
        _registrar_critico_config(msg, cfg)
        print(msg, file=sys.stderr)
        return 2

    # Trata --grants-to se fornecido
    papeis_grants = None
    if args.grants_para:
        try:
            papeis_grants = _parse_grants_arg(args.grants_para)
        except Exception as exc:
            msg = "Configuracao invalida de grants: %s" % exc
            _registrar_critico_config(msg, cfg)
            print(msg, file=sys.stderr)
            return 2

    # Modo GERAR-SQL: gera arquivos SQL em disco para aplicacao por DBA em producao
    if args.gerar_sql:
        import generate_sql as gerar_scripts_sql
        args_gerar = [
            "--owner", owner,
            "--prefix", prefixo,
            "--out-dir", args.gerar_sql,
        ]
        if lob_storage == "BASICFILE":
            args_gerar.append("--lob-basicfile")
        if args.grants_para:
            args_gerar.extend(["--grants-to", args.grants_para])
        if args.admin_login:
            args_gerar.extend(["--admin-login", args.admin_login])
        if args.admin_nome:
            args_gerar.extend(["--admin-name", args.admin_nome])
        return gerar_scripts_sql.main(args_gerar)

    # Modo DRY-RUN: imprime DDL e/ou GRANTs e sai com 0
    if args.dry_run:
        script_ddl = ddl_builder.build_ddl_script(owner, prefixo, lob_storage=lob_storage)
        print(script_ddl)
        if papeis_grants:
            print("\n-- ==============================================================================")
            print("-- GRANTS POR PAPEL (README §11.1)")
            print("-- ==============================================================================")
            grants = ddl_builder.build_grants_by_role(owner, prefixo, papeis_grants)
            for g in grants:
                print(g)
        return 0

    # Modo Real: Conecta ao Oracle
    usuario_dono = args.usuario_dono or owner
    senha_dono = os.environ.get("SSS_INIT_DB_PASSWORD")
    if not senha_dono:
        try:
            senha_dono = getpass.getpass("Senha do dono do esquema Oracle (%s): " % usuario_dono)
        except (KeyboardInterrupt, EOFError):
            print("\nOperacao cancelada.", file=sys.stderr)
            return 2

    # Senha do admin inicial (se solicitado)
    admin_senha = None
    if args.admin_login:
        admin_senha = os.environ.get("SSS_BOOTSTRAP_ADMIN_PASSWORD")
        if not admin_senha:
            try:
                p1 = getpass.getpass("Senha para o administrador inicial '%s': " % args.admin_login)
                p2 = getpass.getpass("Confirme a senha: ")
                if p1 != p2:
                    print("As senhas nao coincidem.", file=sys.stderr)
                    return 2
                admin_senha = p1
            except (KeyboardInterrupt, EOFError):
                print("\nOperacao cancelada.", file=sys.stderr)
                return 2

        valida, msg_pol = security.validate_password_policy(admin_senha)
        if not valida:
            print("Senha do administrador viola politica de complexidade: %s" % msg_pol, file=sys.stderr)
            return 2

    try:
        conn = _conectar(cfg, usuario_dono, senha_dono)
    except Exception as exc:
        msg = "Falha de conexao com o banco Oracle: %s" % exc
        logger.critical(msg, extra={"agent": "-", "ticket": "-", "action": "INIT_DB"})
        print(msg, file=sys.stderr)
        return 1

    try:
        # Validacao de protecao em DEV
        if getattr(cfg.app, "sss_env", "DEV") == "DEV" and not args.schema_real:
            _validar_schema_descartavel_dev(cfg, usuario_dono, conn)
        elif args.schema_real:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT USER FROM DUAL")
                row = cursor.fetchone()
                usuario_banco = row[0] if row else ""
                if usuario_banco.upper() != usuario_dono.upper():
                    raise RuntimeError(
                        "Usuario conectado no Oracle ('%s') diverge do usuario dono ('%s')"
                        % (usuario_banco, usuario_dono)
                    )
            finally:
                cursor.close()

        # Checagem de versao do esquema atual
        esquema = sql_ident.names(prefixo)
        cursor = conn.cursor()
        tb_ctl = "{}.{}".format(owner, esquema["control"]["tabela"])
        versao_banco = 0
        try:
            cursor.execute("SELECT schema_version FROM {} WHERE id = 1".format(tb_ctl))
            row = cursor.fetchone()
            if row:
                versao_banco = row[0]
        except Exception:
            # Tabela controle ainda nao existe -> versao 0 (base vazia)
            versao_banco = 0
        finally:
            cursor.close()

        if versao_banco == 0 and _existe_esquema_1(conn, owner, prefixo):
            print("Esquema anterior ao CR-016a (nomes em portugues) encontrado em %s: aplique o 02_rollback_sss.sql "
                  "da versao anterior antes de criar o novo" % owner, file=sys.stderr)
            return 3

        if versao_banco > sql_ident.SCHEMA_VERSION:
            msg = "Versao do banco (%d) e maior que a versao suportada pelo codigo (%d)" % (
                versao_banco, sql_ident.SCHEMA_VERSION
            )
            print(msg, file=sys.stderr)
            return 3

        # Executa Fases 1 a 6 (DDL)
        print("Iniciando aplicacao do DDL (Fases 1 a 6)...")
        _executar_ddl_fases(conn, owner, prefixo, lob_storage=lob_storage, log_fn=print)

        # Executa Fase 7 (Seed)
        print("Iniciando seed inicial (Fase 7)...")
        _executar_seed(
            conn, owner, prefixo,
            admin_login=args.admin_login,
            admin_nome=args.admin_nome,
            admin_senha=admin_senha,
            log_fn=print,
        )

        # Executa Fase 8 (Estatisticas)
        if args.stats:
            print("Coletando estatisticas (Fase 8)...")
            _coletar_estatisticas(conn, owner, prefixo, log_fn=print)

        # Conferencia de esquema (Fase 9)
        print("Conferindo integridade do esquema...")
        ok, divergencias = _conferir_esquema(conn, owner, prefixo, log_fn=print)
        if not ok:
            return 3

        # Exibe GRANTs se solicitado
        if papeis_grants:
            print("\nGRANTs para os papeis solicitados:")
            grants = ddl_builder.build_grants_by_role(owner, prefixo, papeis_grants)
            for g in grants:
                print("  " + g)

        print("\nOperacao concluida com sucesso (0).")
        return 0

    except Exception as exc:
        msg = "Erro fatal durante init_db: %s" % exc
        print(msg, file=sys.stderr)
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
