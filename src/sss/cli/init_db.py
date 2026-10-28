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

from sss.persistence import ddl_builder
from sss.core import security
from sss.core import sql_ident
from sss.config import sss_config
from sss.config import sss_logging

logger = logging.getLogger("sss_init_db")


def _log_critical_config(msg, cfg=None):
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


def _connect(cfg, user, password_value):
    """Estabelece conexao Oracle com a conta informada usando db_conn.connect (F7.2)."""
    from sss.persistence import db_conn
    secrets_dummy = collections.namedtuple("SegredosDummy", ["oracle"])(
        oracle=collections.namedtuple("OracleDummy", ["password"])(password=password_value)
    )
    return db_conn.connect(cfg, secrets_dummy, role="dono", user=user, password=password_value)


def _validate_disposable_schema_dev(cfg, owner_user, conn):
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
        user_db = row[0] if row else ""
        if user_db.upper() != owner_user.upper():
            raise RuntimeError(
                "Usuario conectado no Oracle ('%s') diverge do usuario dono ('%s')"
                % (user_db, owner_user)
            )
    finally:
        cursor.close()


def _query_existence(cursor, owner):
    """Le todos os objetos, constraints e indices existentes do owner em conjuntos indexados."""
    v_owner = owner.upper()

    # 1. ALL_OBJECTS (Sequences, Tables, Triggers)
    cursor.execute(
        "SELECT OBJECT_TYPE, OBJECT_NAME FROM ALL_OBJECTS WHERE OWNER = :o",
        {"o": v_owner}
    )
    objects = set()
    for row in cursor.fetchall():
        kind, name = row[0], row[1]
        objects.add((kind.upper(), name.lower()))

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
    indexes = set()
    for row in cursor.fetchall():
        indexes.add(row[0].lower())

    return {
        "objetos": objects,
        "constraints": constraints,
        "indices": indexes,
    }


def _object_exists(kind, name, existence_map):
    """Verifica se um determinado objeto ja existe no dicionario de dados."""
    name_low = name.lower()
    if kind in ("SEQUENCE", "TABLE", "TRIGGER"):
        return (kind, name_low) in existence_map["objetos"]
    elif kind == "CONSTRAINT":
        return name_low in existence_map["constraints"]
    elif kind == "INDEX":
        return name_low in existence_map["indices"]
    return False


def _run_ddl_phases(conn, owner, prefix, lob_storage="SECUREFILE", log_fn=print):
    """Aplica o DDL fase a fase de forma idempotente (1 a 6)."""
    cursor = conn.cursor()
    try:
        map_value = _query_existence(cursor, owner)
        statements = ddl_builder.build_ddl_statements(owner, prefix, lob_storage=lob_storage)

        total = len(statements)
        success_count = 0
        skip_count = 0

        for idx, item in enumerate(statements, start=1):
            if _object_exists(item.kind, item.name, map_value):
                skip_count += 1
                log_fn("  [{}/{}] SKIP: {} {} ja existe".format(idx, total, item.kind, item.name))
                continue

            log_fn("  [{}/{}] CRIANDO: {} {}...".format(idx, total, item.kind, item.name))
            try:
                cursor.execute(item.sql)
                success_count += 1
            except Exception as exc:
                msg = "Fase {} - Falha ao criar {} {}: {}".format(item.phase, item.kind, item.name, exc)
                logger.error(msg, extra={"agent": "-", "ticket": "-", "action": "INIT_DB"})
                raise RuntimeError(msg)

        log_fn("DDL concluido: {} criados, {} ignorados (ja existiam)".format(success_count, skip_count))
    finally:
        cursor.close()


def _run_seed(conn, owner, prefix, admin_login=None, admin_name=None, admin_password=None, log_fn=print):
    """Executa o seed idempotente via MERGE (Fase 7, README §4.3.D e §11.1)."""
    schema = sql_ident.names(prefix)
    cursor = conn.cursor()
    try:
        # 1. Catálogo de Funcionalidades
        tb_fea = "{}.{}".format(owner, schema["features"]["tabela"])
        sq_fea = "{}.{}".format(owner, schema["features"]["sequence"])
        sql_merge_fea = """
        MERGE INTO {tb_fea} dst
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
          VALUES ({sq_fea}.NEXTVAL, :code, :name, :module, :description, 'Y', SYSDATE, 'SYSTEM:init_db')
        """.format(tb_fea=tb_fea, sq_fea=sq_fea)

        for mod, code, nom, desc in ddl_builder.FEATURE_CATALOG:
            cursor.execute(sql_merge_fea, {
                "code": code,
                "name": nom,
                "module": mod,
                "description": desc,
            })

        # 2. Ambientes padrão do sistema (antes dos perfis: a matriz perfil x ambiente liga pelo nome)
        tb_env = "{}.{}".format(owner, schema["environments"]["tabela"])
        sq_env = "{}.{}".format(owner, schema["environments"]["sequence"])
        sql_merge_env = """
        MERGE INTO {tb_env} dst
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
          INSERT (id, name, description, connection, active, is_production, created_at, created_by)
          VALUES ({sq_env}.NEXTVAL, :name, :description, :connection, 'Y', :is_production, SYSDATE,
                  'SYSTEM:init_db')
        """.format(tb_env=tb_env, sq_env=sq_env)

        for env_name, env_desc, env_conn, env_prod in ddl_builder.DEFAULT_ENVIRONMENTS:
            cursor.execute(sql_merge_env, {
                "name": env_name,
                "description": env_desc,
                "connection": env_conn,
                "is_production": env_prod,
            })

        # 3. Perfis padrao e matrizes de permissao (DEFAULT_PROFILES)
        tb_prf = "{}.{}".format(owner, schema["profiles"]["tabela"])
        sq_prf = "{}.{}".format(owner, schema["profiles"]["sequence"])
        tb_pfea = "{}.{}".format(owner, schema["profile_feature"]["tabela"])
        sq_pfea = "{}.{}".format(owner, schema["profile_feature"]["sequence"])
        tb_penv = "{}.{}".format(owner, schema["profile_env"]["tabela"])
        sq_penv = "{}.{}".format(owner, schema["profile_env"]["sequence"])

        sql_merge_prf = """
        MERGE INTO {tb_prf} dst
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
          VALUES ({sq_prf}.NEXTVAL, :name, :description, :is_admin, 1, 'Y', SYSDATE, 'SYSTEM:init_db')
        """.format(tb_prf=tb_prf, sq_prf=sq_prf)

        sql_merge_pfea = """
        MERGE INTO {tb_pfea} dst
        USING (
          SELECT p.id AS profile_id, f.id AS feature_id
            FROM {tb_prf} p, {tb_fea} f
           WHERE p.name = :prf_name AND f.code = :code
        ) src
        ON (dst.profile_id = src.profile_id AND dst.feature_id = src.feature_id)
        WHEN NOT MATCHED THEN
          INSERT (id, profile_id, feature_id, created_at, created_by)
          VALUES ({sq_pfea}.NEXTVAL, src.profile_id, src.feature_id, SYSDATE, 'SYSTEM:init_db')
        """.format(tb_pfea=tb_pfea, sq_pfea=sq_pfea, tb_prf=tb_prf, tb_fea=tb_fea)

        sql_merge_penv = """
        MERGE INTO {tb_penv} dst
        USING (
          SELECT p.id AS profile_id, a.id AS environment_id
            FROM {tb_prf} p, {tb_env} a
           WHERE p.name = :prf_name AND a.name = :env_name
        ) src
        ON (dst.profile_id = src.profile_id AND dst.environment_id = src.environment_id)
        WHEN NOT MATCHED THEN
          INSERT (id, profile_id, environment_id, created_at, created_by)
          VALUES ({sq_penv}.NEXTVAL, src.profile_id, src.environment_id, SYSDATE, 'SYSTEM:init_db')
        """.format(tb_penv=tb_penv, sq_penv=sq_penv, tb_prf=tb_prf, tb_env=tb_env)

        for prf_name, prf_desc, is_adm, prf_features, prf_envs in ddl_builder.DEFAULT_PROFILES:
            cursor.execute(sql_merge_prf, {
                "name": prf_name,
                "description": prf_desc,
                "is_admin": is_adm,
            })
            for f_code in prf_features:
                cursor.execute(sql_merge_pfea, {"prf_name": prf_name, "code": f_code})
            for a_name in prf_envs:
                cursor.execute(sql_merge_penv, {"prf_name": prf_name, "env_name": a_name})

        # 4. Parametros padrao reutilizaveis
        tb_prm = "{}.{}".format(owner, schema["parameters"]["tabela"])
        sq_prm = "{}.{}".format(owner, schema["parameters"]["sequence"])
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

        for code, p_nom, lbl, desc, tcomp, opts, vpad in ddl_builder.DEFAULT_PARAMETERS:
            cursor.execute(sql_merge_prm, {
                "code": code,
                "param_flag": p_nom,
                "label": lbl,
                "description": desc,
                "component_type": tcomp,
                "options_json": opts,
                "default_value": vpad,
            })

        # 5. Scripts utilitarios padrao e associacoes
        tb_scr = "{}.{}".format(owner, schema["scripts"]["tabela"])
        sq_scr = "{}.{}".format(owner, schema["scripts"]["sequence"])
        tb_senv = "{}.{}".format(owner, schema["script_env"]["tabela"])
        sq_senv = "{}.{}".format(owner, schema["script_env"]["sequence"])
        tb_pscr = "{}.{}".format(owner, schema["profile_script"]["tabela"])
        sq_pscr = "{}.{}".format(owner, schema["profile_script"]["sequence"])
        tb_sprm = "{}.{}".format(owner, schema["script_param"]["tabela"])
        sq_sprm = "{}.{}".format(owner, schema["script_param"]["sequence"])

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
                     dst.max_parallel_env = :max_par,
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
             OR dst.max_parallel_env <> :max_par
             OR NVL(dst.timeout_s, 0) <> NVL(:timeout_s, 0)
        WHEN NOT MATCHED THEN
          INSERT (id, name, description, script_group, category, stage, interpreter, path_file, param_type, max_parallel_env, timeout_s, active, created_at, created_by)
          VALUES ({sq_scr}.NEXTVAL, :name, :description, :script_group, :category, :stage, :interpreter, :path_file, :param_type, :max_par, :timeout_s, 'Y', SYSDATE, 'SYSTEM:init_db')
        """.format(tb_scr=tb_scr, sq_scr=sq_scr)

        sql_merge_senv = """
        MERGE INTO {tb_senv} dst
        USING (
          SELECT s.id AS script_id, a.id AS environment_id
            FROM {tb_scr} s, {tb_env} a
           WHERE s.name = :scr_name AND a.name = :env_name
        ) src
        ON (dst.script_id = src.script_id AND dst.environment_id = src.environment_id)
        WHEN NOT MATCHED THEN
          INSERT (id, script_id, environment_id, created_at, created_by)
          VALUES ({sq_senv}.NEXTVAL, src.script_id, src.environment_id, SYSDATE, 'SYSTEM:init_db')
        """.format(tb_senv=tb_senv, sq_senv=sq_senv, tb_scr=tb_scr, tb_env=tb_env)

        sql_merge_pscr = """
        MERGE INTO {tb_pscr} dst
        USING (
          SELECT p.id AS profile_id, s.id AS script_id
            FROM {tb_prf} p, {tb_scr} s
           WHERE p.name = :prf_name AND s.name = :scr_name
        ) src
        ON (dst.profile_id = src.profile_id AND dst.script_id = src.script_id)
        WHEN NOT MATCHED THEN
          INSERT (id, profile_id, script_id, created_at, created_by)
          VALUES ({sq_pscr}.NEXTVAL, src.profile_id, src.script_id, SYSDATE, 'SYSTEM:init_db')
        """.format(tb_pscr=tb_pscr, sq_pscr=sq_pscr, tb_prf=tb_prf, tb_scr=tb_scr)

        sql_merge_sprm = """
        MERGE INTO {tb_sprm} dst
        USING (
          SELECT s.id AS script_id, p.id AS parameter_id
            FROM {tb_scr} s, {tb_prm} p
           WHERE s.name = :scr_name AND p.code = :p_code
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

        for s_name, s_desc, s_grp, s_cat, s_etp, s_int, s_path, s_tpar, s_paral, s_tmout, s_params in ddl_builder.DEFAULT_SCRIPTS:
            cursor.execute(sql_merge_scr, {
                "name": s_name,
                "description": s_desc,
                "script_group": s_grp,
                "category": s_cat,
                "stage": s_etp,
                "interpreter": s_int,
                "path_file": s_path,
                "param_type": s_tpar,
                "max_par": s_paral,
                "timeout_s": s_tmout,
            })

            for env_name, _, _, _ in ddl_builder.DEFAULT_ENVIRONMENTS:
                cursor.execute(sql_merge_senv, {"scr_name": s_name, "env_name": env_name})

            for prf_name, _, _, _, _ in ddl_builder.DEFAULT_PROFILES:
                cursor.execute(sql_merge_pscr, {"prf_name": prf_name, "scr_name": s_name})

            for p_code, p_ord, p_req, p_vsub in s_params:
                cursor.execute(sql_merge_sprm, {
                    "scr_name": s_name,
                    "p_code": p_code,
                    "sort_order": p_ord,
                    "required": p_req,
                    "vsub": p_vsub,
                })

        # 6. Linha de tbsss_control
        tb_ctl = "{}.{}".format(owner, schema["control"]["tabela"])
        sql_merge_ctl = """
        MERGE INTO {tb_ctl} dst
        USING (SELECT 1 AS id FROM DUAL) src
        ON (dst.id = src.id)
        WHEN NOT MATCHED THEN
          INSERT (id, schema_version, version_applied_at, version_applied_by)
          VALUES (1, :schema_version, SYSDATE, 'SYSTEM:init_db')
        """.format(tb_ctl=tb_ctl)
        cursor.execute(sql_merge_ctl, {"schema_version": sql_ident.SCHEMA_VERSION})

        # 7. Usuarios padrao da aplicacao e homologacao (DEFAULT_USERS)
        tb_usr = "{}.{}".format(owner, schema["users"]["tabela"])
        sq_usr = "{}.{}".format(owner, schema["users"]["sequence"])

        sql_merge_usr = """
        MERGE INTO {tb_usr} dst
        USING (
          SELECT :login AS login, p.id AS profile_id
            FROM {tb_prf} p
           WHERE p.name = :profile
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
        """.format(tb_usr=tb_usr, sq_usr=sq_usr, tb_prf=tb_prf)

        for u_login, u_name, u_profile in ddl_builder.DEFAULT_USERS:
            name_final = admin_name if (u_login == "admin" and admin_name) else u_name
            if u_login == "admin" and admin_password:
                hash_final = security.hash_password(admin_password)
            else:
                hash_final = ddl_builder.HOMOLOGATION_DEFAULT_PASSWORD_HASH

            cursor.execute(sql_merge_usr, {
                "login": u_login,
                "name": name_final,
                "profile": u_profile,
                "password_hash": hash_final,
            })
            log_fn("Usuario '%s' homologado no perfil '%s'" % (u_login, u_profile))

        conn.commit()
        log_fn("Seed concluido com sucesso")
    except Exception as exc:
        conn.rollback()
        msg = "Falha no seed: %s" % exc
        logger.error(msg, extra={"agent": "-", "ticket": "-", "action": "INIT_DB"})
        raise RuntimeError(msg)
    finally:
        cursor.close()


def _gather_statistics(conn, owner, prefix, log_fn=print):
    """Coleta estatisticas apenas em tabelas com linhas (Fase 8, CR-007, R-29)."""
    cursor = conn.cursor()
    schema = sql_ident.names(prefix)
    try:
        for entity, t in schema.items():
            table_name = t["tabela"]
            # Checa se possui linhas
            cursor.execute("SELECT COUNT(*) FROM {}.{} WHERE ROWNUM = 1".format(owner, table_name))
            row = cursor.fetchone()
            has_rows = (row and row[0] > 0)
            if has_rows:
                log_fn("  Coletando estatisticas para {}.{}...".format(owner, table_name))
                sql_stats = """
                BEGIN
                    DBMS_STATS.GATHER_TABLE_STATS(
                        ownname => :own,
                        tabname => :tab,
                        cascade => TRUE
                    );
                END;
                """
                cursor.execute(sql_stats, {"own": owner.upper(), "tab": table_name.upper()})
            else:
                log_fn("  {}.{} vazia (pula estatisticas para nao fixar planos ruins)".format(owner, table_name))
    finally:
        cursor.close()


def _check_schema(conn, owner, prefix, log_fn=print):
    """Confere esquema real do banco contra o registro sql_ident (README §11.1, CR-008, R-14)."""
    schema = sql_ident.names(prefix)
    cursor = conn.cursor()
    divergences = []

    try:
        # 1. Checagem de Objetos Invalidos (apenas objetos pertencentes ao SSS)
        idents_sss = {i.upper() for i in schema.all_identifiers(include_columns=False)}
        cursor.execute(
            "SELECT OBJECT_TYPE, OBJECT_NAME FROM ALL_OBJECTS WHERE OWNER = :o AND STATUS = 'INVALID'",
            {"o": owner.upper()}
        )
        for obj_kind, obj_name in cursor.fetchall():
            name_u = obj_name.upper()
            if name_u in idents_sss or name_u.startswith(prefix.upper()) or name_u.startswith("SQ_" + prefix.upper()) or name_u.startswith("TR_" + prefix.upper()):
                cursor.execute(
                    "SELECT LINE, POSITION, TEXT FROM ALL_ERRORS WHERE OWNER = :o AND NAME = :n",
                    {"o": owner.upper(), "n": obj_name}
                )
                errors = [r[2].strip() for r in cursor.fetchall()]
                detail_errors = "; ".join(errors) if errors else "Sem detalhes em ALL_ERRORS"
                divergences.append("Objeto invalido: {} {} ({})".format(obj_kind, obj_name, detail_errors))

        # 2. Checagem de Colunas e Tipos
        for entity, t in schema.items():
            table_name = t["tabela"].upper()
            cursor.execute("""
                SELECT COLUMN_NAME, DATA_TYPE, CHAR_LENGTH, DATA_PRECISION, DATA_SCALE, NULLABLE, DATA_DEFAULT
                  FROM ALL_TAB_COLUMNS
                 WHERE OWNER = :o AND TABLE_NAME = :t
                 ORDER BY COLUMN_ID
            """, {"o": owner.upper(), "t": table_name})
            columns_db = {}
            for row in cursor.fetchall():
                c_name = row[0].lower()
                columns_db[c_name] = {
                    "data_type": row[1],
                    "char_length": row[2],
                    "precision": row[3],
                    "scale": row[4],
                    "nullable": row[5],
                    "data_default": row[6],
                }

            # Verifica se colunas esperadas existem
            for col_expected, col_info in t["colunas"].items():
                if col_expected not in columns_db:
                    divergences.append("Coluna ausente: {}.{}".format(t["tabela"], col_expected))
                    continue

                b_col = columns_db[col_expected]
                # Valida Nullable
                expected_null = "N" if col_info.get("not_null") else "Y"
                if b_col["nullable"] != expected_null:
                    divergences.append(
                        "Coluna {}.{} divergencia de NULLABLE (esperado: {}, real: {})".format(
                            t["tabela"], col_expected, expected_null, b_col["nullable"]
                        )
                    )

                # Valida Default (normalizado)
                if col_info.get("default") is not None:
                    expected_def = sql_ident.normalize_expression(col_info["default"])
                    real_def = sql_ident.normalize_expression(b_col["data_default"])
                    if expected_def != real_def:
                        divergences.append(
                            "Coluna {}.{} divergencia de DEFAULT (esperado: '{}', real: '{}')".format(
                                t["tabela"], col_expected, expected_def, real_def
                            )
                        )

            # Verifica colunas sobressalentes
            for c_name in columns_db:
                if c_name not in t["colunas"]:
                    divergences.append("Coluna extra nao registrada: {}.{}".format(t["tabela"], c_name))

        # 3. Checagem de CKs (normalizadas, ignorando SYS_C% de NOT NULL)
        for entity, t in schema.items():
            table_name = t["tabela"].upper()
            cursor.execute("""
                SELECT CONSTRAINT_NAME, SEARCH_CONDITION
                  FROM ALL_CONSTRAINTS
                 WHERE OWNER = :o AND TABLE_NAME = :t AND CONSTRAINT_TYPE = 'C'
            """, {"o": owner.upper(), "t": table_name})
            cks_db = {}
            for c_name, s_cond in cursor.fetchall():
                # Ignora SYS_C% que apenas validam IS NOT NULL
                if sql_ident.is_system_not_null_ck(c_name, s_cond):
                    continue
                cks_db[c_name.lower()] = s_cond

            for ck_expected, ck_info in t["cks"].items():
                if ck_expected not in cks_db:
                    divergences.append("Constraint CK ausente: {}.{}".format(t["tabela"], ck_expected))
                    continue

                real_cond = sql_ident.normalize_expression(cks_db[ck_expected])
                expected_cond = sql_ident.normalize_expression(ck_info["expr"])
                if real_cond != expected_cond:
                    divergences.append(
                        "Constraint CK {}.{} condicao divergente (esperado: '{}', real: '{}')".format(
                            t["tabela"], ck_expected, expected_cond, real_cond
                        )
                    )

        # 4. Checagem de Indices
        for entity, t in schema.items():
            for ix_expected, ix_info in t["indices"].items():
                cursor.execute("""
                    SELECT INDEX_NAME, UNIQUENESS
                      FROM ALL_INDEXES
                     WHERE OWNER = :o AND INDEX_NAME = :i
                """, {"o": owner.upper(), "i": ix_expected.upper()})
                row = cursor.fetchone()
                if not row:
                    divergences.append("Indice ausente: {}".format(ix_expected))
                    continue

                is_unique = (row[1] == "UNIQUE")
                expected_unique = bool(ix_info.get("unico", False))
                if is_unique != expected_unique:
                    divergences.append(
                        "Indice {} divergencia de unicidade (esperado: {}, real: {})".format(
                            ix_expected, expected_unique, is_unique
                        )
                    )

        if divergences:
            log_fn("Divergencias detectadas na conferencia de esquema (total: %d):" % len(divergences))
            for d in divergences:
                log_fn("  - " + d)
            return False, divergences

        log_fn("Conferencia de esquema: 100% compativel com o registro sql_ident")
        return True, []
    finally:
        cursor.close()


def _parse_grants_arg(arg_str):
    """Faz o parse do argumento --grants-to web=u1,agente=u2,..."""
    roles = {}
    if not arg_str:
        return roles
    parts = arg_str.split(",")
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if "=" not in p:
            raise ValueError("Formato invalido para --grants-to: '%s'. Use papel=usuario" % p)
        role, usr = p.split("=", 1)
        role = role.strip().lower()
        usr = usr.strip()
        if role not in ("web", "agent"):
            raise ValueError("Papel desconhecido em --grants-to: '%s'" % role)
        roles[role] = usr
    return roles


def _schema_1_exists(conn, owner, prefix):
    """Tabela de controle do esquema anterior ao CR-016a presente: o esquema novo nao convive com ele."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM all_tables WHERE owner = :o AND table_name = :t",
                       o=owner.upper(), t=(prefix + sql_ident.LEGACY_CONTROL_TABLE).upper())
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
    parser.add_argument("--config", dest="config", default=None, help="Caminho do config.ini (ou --name)")
    parser.add_argument("--name", dest="name", default=None,
                        help="processo: instance/<nome>/config.ini (CR-029)")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Imprime o DDL sem conectar")
    parser.add_argument("--lob-basicfile", dest="lob_basicfile", action="store_true", help="Fallback LOB BASICFILE")
    parser.add_argument("--owner-user", dest="usuario_dono", default=None, help="Usuario dono do esquema")
    parser.add_argument("--admin-login", dest="admin_login", default=None, help="Login do administrador inicial")
    parser.add_argument("--admin-name", dest="admin_nome", default=None, help="Nome do administrador inicial")
    parser.add_argument("--stats", dest="stats", action="store_true", default=True, help="Coleta estatisticas")
    parser.add_argument("--no-stats", dest="stats", action="store_false", help="Nao coleta estatisticas")
    parser.add_argument("--grants-to", dest="grants_para", default=None, help="web=u1,agent=u2")
    parser.add_argument("--real-schema", dest="schema_real", action="store_true", default=False, help="Permite aplicacao em schema real de banco sem exigir prefixo SSS_TEST_")
    parser.add_argument("--generate-sql", dest="gerar_sql", default=None, help="Diretorio de saida para salvar os arquivos .sql de implantacao e rollback")

    # Rejeita argumentos desconhecidos
    try:
        args, unknown = parser.parse_known_args(argv)
        if unknown:
            msg = "Argumentos nao suportados: %s" % (" ".join(unknown))
            _log_critical_config(msg)
            print(msg, file=sys.stderr)
            return 2
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2

    # Carrega configuracao
    cfg = None
    try:
        # CR-029: sem config padrao; --name <processo> ou --config <arquivo>.
        path_cfg = sss_config.config_path(args.config, args.name)
        cfg = sss_config.load(path_cfg)
    except Exception as exc:
        msg = "Falha ao carregar configuracao: %s" % exc
        _log_critical_config(msg)
        print(msg, file=sys.stderr)
        return 2

    owner = cfg.oracle.owner
    prefix = cfg.oracle.table_prefix
    lob_storage = "BASICFILE" if args.lob_basicfile else "SECUREFILE"

    # Valida owner e prefixo antes de qualquer acao
    try:
        sql_ident.validate_owner(owner)
        sql_ident.validate_prefix(prefix)
        sql_ident.validate_registry(prefix)
    except Exception as exc:
        msg = "Falha de configuracao em identificadores Oracle: %s" % exc
        _log_critical_config(msg, cfg)
        print(msg, file=sys.stderr)
        return 2

    # Trata --grants-to se fornecido
    roles_grants = None
    if args.grants_para:
        try:
            roles_grants = _parse_grants_arg(args.grants_para)
        except Exception as exc:
            msg = "Configuracao invalida de grants: %s" % exc
            _log_critical_config(msg, cfg)
            print(msg, file=sys.stderr)
            return 2

    # Modo GERAR-SQL: gera arquivos SQL em disco para aplicacao por DBA em producao
    if args.gerar_sql:
        from sss.cli import generate_sql as gerar_scripts_sql
        args_generate = [
            "--owner", owner,
            "--prefix", prefix,
            "--out-dir", args.gerar_sql,
        ]
        if lob_storage == "BASICFILE":
            args_generate.append("--lob-basicfile")
        if args.grants_para:
            args_generate.extend(["--grants-to", args.grants_para])
        if args.admin_login:
            args_generate.extend(["--admin-login", args.admin_login])
        if args.admin_nome:
            args_generate.extend(["--admin-name", args.admin_nome])
        return gerar_scripts_sql.main(args_generate)

    # Modo DRY-RUN: imprime DDL e/ou GRANTs e sai com 0
    if args.dry_run:
        script_ddl = ddl_builder.build_ddl_script(owner, prefix, lob_storage=lob_storage)
        print(script_ddl)
        if roles_grants:
            print("\n-- ==============================================================================")
            print("-- GRANTS POR PAPEL (README §11.1)")
            print("-- ==============================================================================")
            grants = ddl_builder.build_grants_by_role(owner, prefix, roles_grants)
            for g in grants:
                print(g)
        return 0

    # Modo Real: Conecta ao Oracle
    user_owner = args.usuario_dono or owner
    password_owner = os.environ.get("SSS_INIT_DB_PASSWORD")
    if not password_owner:
        try:
            password_owner = getpass.getpass("Senha do dono do esquema Oracle (%s): " % user_owner)
        except (KeyboardInterrupt, EOFError):
            print("\nOperacao cancelada.", file=sys.stderr)
            return 2

    # Senha do admin inicial (se solicitado)
    admin_password = None
    if args.admin_login:
        admin_password = os.environ.get("SSS_BOOTSTRAP_ADMIN_PASSWORD")
        if not admin_password:
            try:
                p1 = getpass.getpass("Senha para o administrador inicial '%s': " % args.admin_login)
                p2 = getpass.getpass("Confirme a senha: ")
                if p1 != p2:
                    print("As senhas nao coincidem.", file=sys.stderr)
                    return 2
                admin_password = p1
            except (KeyboardInterrupt, EOFError):
                print("\nOperacao cancelada.", file=sys.stderr)
                return 2

        valid, msg_pol = security.validate_password_policy(admin_password)
        if not valid:
            print("Senha do administrador viola politica de complexidade: %s" % msg_pol, file=sys.stderr)
            return 2

    try:
        conn = _connect(cfg, user_owner, password_owner)
    except Exception as exc:
        msg = "Falha de conexao com o banco Oracle: %s" % exc
        logger.critical(msg, extra={"agent": "-", "ticket": "-", "action": "INIT_DB"})
        print(msg, file=sys.stderr)
        return 1

    try:
        # Protecao do esquema (CR-032, D11): sem --real-schema, so o esquema descartavel de teste.
        if not args.schema_real:
            _validate_disposable_schema_dev(cfg, user_owner, conn)
        elif args.schema_real:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT USER FROM DUAL")
                row = cursor.fetchone()
                user_db = row[0] if row else ""
                if user_db.upper() != user_owner.upper():
                    raise RuntimeError(
                        "Usuario conectado no Oracle ('%s') diverge do usuario dono ('%s')"
                        % (user_db, user_owner)
                    )
            finally:
                cursor.close()

        # Checagem de versao do esquema atual
        schema = sql_ident.names(prefix)
        cursor = conn.cursor()
        tb_ctl = "{}.{}".format(owner, schema["control"]["tabela"])
        version_db = 0
        try:
            cursor.execute("SELECT schema_version FROM {} WHERE id = 1".format(tb_ctl))
            row = cursor.fetchone()
            if row:
                version_db = row[0]
        except Exception:
            # Tabela controle ainda nao existe -> versao 0 (base vazia)
            version_db = 0
        finally:
            cursor.close()

        if version_db == 0 and _schema_1_exists(conn, owner, prefix):
            print("Esquema anterior ao CR-016a (nomes em portugues) encontrado em %s: aplique o 02_rollback_sss.sql "
                  "da versao anterior antes de criar o novo" % owner, file=sys.stderr)
            return 3

        if version_db > sql_ident.SCHEMA_VERSION:
            msg = "Versao do banco (%d) e maior que a versao suportada pelo codigo (%d)" % (
                version_db, sql_ident.SCHEMA_VERSION
            )
            print(msg, file=sys.stderr)
            return 3

        # Executa Fases 1 a 6 (DDL)
        print("Iniciando aplicacao do DDL (Fases 1 a 6)...")
        _run_ddl_phases(conn, owner, prefix, lob_storage=lob_storage, log_fn=print)

        # Executa Fase 7 (Seed)
        print("Iniciando seed inicial (Fase 7)...")
        _run_seed(
            conn, owner, prefix,
            admin_login=args.admin_login,
            admin_name=args.admin_nome,
            admin_password=admin_password,
            log_fn=print,
        )

        # Executa Fase 8 (Estatisticas)
        if args.stats:
            print("Coletando estatisticas (Fase 8)...")
            _gather_statistics(conn, owner, prefix, log_fn=print)

        # Conferencia de esquema (Fase 9)
        print("Conferindo integridade do esquema...")
        ok, divergences = _check_schema(conn, owner, prefix, log_fn=print)
        if not ok:
            return 3

        # Exibe GRANTs se solicitado
        if roles_grants:
            print("\nGRANTs para os papeis solicitados:")
            grants = ddl_builder.build_grants_by_role(owner, prefix, roles_grants)
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
