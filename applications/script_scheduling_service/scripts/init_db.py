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
        logger.critical(msg, extra={"agente": "-", "ticket": "-", "acao": "CONFIG"})
    else:
        sss_logging.registrar_critico_inicial("sss_init_db", msg, log_dir)


def _conectar(cfg, usuario, senha):
    """Estabelece conexao Oracle com a conta informada usando db_conn.conectar (F7.2)."""
    import db_conn
    segredos_dummy = collections.namedtuple("SegredosDummy", ["oracle"])(
        oracle=collections.namedtuple("OracleDummy", ["password"])(password=senha)
    )
    return db_conn.conectar(cfg, segredos_dummy, papel="dono", user=usuario, password=senha)


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
        instrucoes = ddl_builder.gerar_instrucoes_ddl(owner, prefixo, lob_storage=lob_storage)

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
                logger.error(msg, extra={"agente": "-", "ticket": "-", "acao": "INIT_DB"})
                raise RuntimeError(msg)

        log_fn("DDL concluido: {} criados, {} ignorados (ja existiam)".format(sucesso_count, skip_count))
    finally:
        cursor.close()


def _executar_seed(conn, owner, prefixo, admin_login=None, admin_nome=None, admin_senha=None, log_fn=print):
    """Executa o seed idempotente via MERGE (Fase 7, README §4.3.D e §11.1)."""
    esquema = sql_ident.nomes(prefixo)
    cursor = conn.cursor()
    try:
        # 1. Catálogo de Funcionalidades
        tb_fnc = "{}.{}".format(owner, esquema["funcionalidades"]["tabela"])
        sq_fnc = "{}.{}".format(owner, esquema["funcionalidades"]["sequence"])
        sql_merge_fnc = """
        MERGE INTO {tb_fnc} dst
        USING (SELECT :codigo AS codigo FROM DUAL) src
        ON (dst.codigo = src.codigo)
        WHEN MATCHED THEN
          UPDATE SET dst.nome = :nome,
                     dst.modulo = :modulo,
                     dst.descricao = :descricao,
                     dst.ativo = 'S',
                     dst.updated_at = SYSDATE,
                     dst.updated_by = 'SYSTEM:init_db'
          WHERE dst.nome <> :nome
             OR dst.modulo <> :modulo
             OR dst.descricao <> :descricao
             OR dst.ativo <> 'S'
        WHEN NOT MATCHED THEN
          INSERT (id, codigo, nome, modulo, descricao, ativo, created_at, created_by)
          VALUES ({sq_fnc}.NEXTVAL, :codigo, :nome, :modulo, :descricao, 'S', SYSDATE, 'SYSTEM:init_db')
        """.format(tb_fnc=tb_fnc, sq_fnc=sq_fnc)

        for mod, cod, nom, desc in ddl_builder.CATALOGO_FUNCIONALIDADES:
            cursor.execute(sql_merge_fnc, {
                "codigo": cod,
                "nome": nom,
                "modulo": mod,
                "descricao": desc,
            })

        # 2. Perfil ADMINISTRADOR
        tb_per = "{}.{}".format(owner, esquema["perfis"]["tabela"])
        sq_per = "{}.{}".format(owner, esquema["perfis"]["sequence"])
        desc_perfil = "Perfil administrativo inicial do sistema"
        sql_merge_per = """
        MERGE INTO {tb_per} dst
        USING (SELECT 'ADMINISTRADOR' AS nome FROM DUAL) src
        ON (dst.nome = src.nome)
        WHEN MATCHED THEN
          UPDATE SET dst.descricao = :descricao,
                     dst.is_admin = 'S',
                     dst.ativo = 'S',
                     dst.updated_at = SYSDATE,
                     dst.updated_by = 'SYSTEM:init_db'
          WHERE dst.is_admin <> 'S'
             OR dst.ativo <> 'S'
             OR NVL(dst.descricao, '~') <> NVL(:descricao, '~')
        WHEN NOT MATCHED THEN
          INSERT (id, nome, descricao, is_admin, perm_versao, ativo, created_at, created_by)
          VALUES ({sq_per}.NEXTVAL, 'ADMINISTRADOR', :descricao, 'S', 1, 'S', SYSDATE, 'SYSTEM:init_db')
        """.format(tb_per=tb_per, sq_per=sq_per)
        cursor.execute(sql_merge_per, {"descricao": desc_perfil})

        # 3. Associações Perfil x Funcionalidades
        tb_pfnc = "{}.{}".format(owner, esquema["perfil_func"]["tabela"])
        sq_pfnc = "{}.{}".format(owner, esquema["perfil_func"]["sequence"])
        sql_merge_pfnc = """
        MERGE INTO {tb_pfnc} dst
        USING (
          SELECT p.id AS perfil_id, f.id AS funcionalidade_id
            FROM {tb_per} p, {tb_fnc} f
           WHERE p.nome = 'ADMINISTRADOR' AND f.codigo = :codigo
        ) src
        ON (dst.perfil_id = src.perfil_id AND dst.funcionalidade_id = src.funcionalidade_id)
        WHEN NOT MATCHED THEN
          INSERT (id, perfil_id, funcionalidade_id, created_at, created_by)
          VALUES ({sq_pfnc}.NEXTVAL, src.perfil_id, src.funcionalidade_id, SYSDATE, 'SYSTEM:init_db')
        """.format(tb_pfnc=tb_pfnc, sq_pfnc=sq_pfnc, tb_per=tb_per, tb_fnc=tb_fnc)

        for _, cod, _, _ in ddl_builder.CATALOGO_FUNCIONALIDADES:
            cursor.execute(sql_merge_pfnc, {"codigo": cod})

        # 4. Linha de tbsss_controle
        tb_ctl = "{}.{}".format(owner, esquema["controle"]["tabela"])
        sql_merge_ctl = """
        MERGE INTO {tb_ctl} dst
        USING (SELECT 1 AS id FROM DUAL) src
        ON (dst.id = src.id)
        WHEN NOT MATCHED THEN
          INSERT (id, versao_esquema, versao_aplicada_em, versao_aplicada_por)
          VALUES (1, :versao_esquema, SYSDATE, 'SYSTEM:init_db')
        """.format(tb_ctl=tb_ctl)
        cursor.execute(sql_merge_ctl, {"versao_esquema": sql_ident.VERSAO_ESQUEMA})

        # 5. Administrador inicial (se solicitado)
        if admin_login:
            tb_usr = "{}.{}".format(owner, esquema["usuarios"]["tabela"])
            sq_usr = "{}.{}".format(owner, esquema["usuarios"]["sequence"])

            cursor.execute("SELECT id FROM {tb_usr} WHERE login = :login".format(tb_usr=tb_usr), {"login": admin_login})
            usr_row = cursor.fetchone()
            if usr_row is None:
                cursor.execute("SELECT id FROM {tb_per} WHERE nome = 'ADMINISTRADOR'".format(tb_per=tb_per))
                per_row = cursor.fetchone()
                if not per_row:
                    raise RuntimeError("Perfil ADMINISTRADOR nao localizado para criacao do usuario admin")
                per_id = per_row[0]

                senha_hash = security.hash_senha(admin_senha)
                nome_admin = admin_nome or admin_login
                sql_ins_usr = """
                INSERT INTO {tb_usr} (
                  id, login, nome, senha_hash, perfil_id, ativo, sessao_epoch, tentativas_falha, created_at, created_by
                ) VALUES (
                  {sq_usr}.NEXTVAL, :login, :nome, :senha_hash, :perfil_id, 'S', 0, 0, SYSDATE, 'SYSTEM:init_db'
                )
                """.format(tb_usr=tb_usr, sq_usr=sq_usr)
                cursor.execute(sql_ins_usr, {
                    "login": admin_login,
                    "nome": nome_admin,
                    "senha_hash": senha_hash,
                    "perfil_id": per_id,
                })
                log_fn("Usuario administrador inicial '%s' criado com sucesso" % admin_login)
            else:
                log_fn("Usuario administrador '%s' ja existe (SKIP criacao)" % admin_login)

        conn.commit()
        log_fn("Seed concluido com sucesso")
    except Exception as exc:
        conn.rollback()
        msg = "Falha no seed: %s" % exc
        logger.error(msg, extra={"agente": "-", "ticket": "-", "acao": "INIT_DB"})
        raise RuntimeError(msg)
    finally:
        cursor.close()


def _coletar_estatisticas(conn, owner, prefixo, log_fn=print):
    """Coleta estatisticas apenas em tabelas com linhas (Fase 8, CR-007, R-29)."""
    cursor = conn.cursor()
    esquema = sql_ident.nomes(prefixo)
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
    esquema = sql_ident.nomes(prefixo)
    cursor = conn.cursor()
    divergencias = []

    try:
        # 1. Checagem de Objetos Invalidos
        cursor.execute(
            "SELECT OBJECT_TYPE, OBJECT_NAME FROM ALL_OBJECTS WHERE OWNER = :o AND STATUS = 'INVALID'",
            {"o": owner.upper()}
        )
        for obj_tipo, obj_nome in cursor.fetchall():
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
                    def_esperado = sql_ident.normalizar_expressao(col_info["default"])
                    def_real = sql_ident.normalizar_expressao(b_col["data_default"])
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
                if sql_ident.eh_ck_not_null_sistema(c_nome, s_cond):
                    continue
                cks_banco[c_nome.lower()] = s_cond

            for ck_esperada, ck_info in t["cks"].items():
                if ck_esperada not in cks_banco:
                    divergencias.append("Constraint CK ausente: {}.{}".format(t["tabela"], ck_esperada))
                    continue

                cond_real = sql_ident.normalizar_expressao(cks_banco[ck_esperada])
                cond_esp = sql_ident.normalizar_expressao(ck_info["expr"])
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
    """Faz o parse do argumento --grants-para web=u1,agente=u2,..."""
    papeis = {}
    if not arg_str:
        return papeis
    partes = arg_str.split(",")
    for p in partes:
        p = p.strip()
        if not p:
            continue
        if "=" not in p:
            raise ValueError("Formato invalido para --grants-para: '%s'. Use papel=usuario" % p)
        papel, usr = p.split("=", 1)
        papel = papel.strip().lower()
        usr = usr.strip()
        if papel not in ("web", "agente", "purge", "monitor"):
            raise ValueError("Papel desconhecido em --grants-para: '%s'" % papel)
        papeis[papel] = usr
    return papeis


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
    parser.add_argument("--usuario-dono", dest="usuario_dono", default=None, help="Usuario dono do esquema")
    parser.add_argument("--admin-login", dest="admin_login", default=None, help="Login do administrador inicial")
    parser.add_argument("--admin-nome", dest="admin_nome", default=None, help="Nome do administrador inicial")
    parser.add_argument("--stats", dest="stats", action="store_true", default=True, help="Coleta estatisticas")
    parser.add_argument("--no-stats", dest="stats", action="store_false", help="Nao coleta estatisticas")
    parser.add_argument("--grants-para", dest="grants_para", default=None, help="web=u1,agente=u2,purge=u3,monitor=u4")

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
    caminho_cfg = args.config or sss_config.caminho_config_padrao()
    if not os.path.isfile(caminho_cfg):
        exemplo = os.path.join(os.path.dirname(caminho_cfg), "config.ini.example")
        if os.path.isfile(exemplo):
            caminho_cfg = exemplo

    try:
        cfg = sss_config.carregar(caminho_cfg)
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
        sql_ident.validar_owner(owner)
        sql_ident.validar_prefixo(prefixo)
        sql_ident.validar_registro(prefixo)
    except Exception as exc:
        msg = "Falha de configuracao em identificadores Oracle: %s" % exc
        _registrar_critico_config(msg, cfg)
        print(msg, file=sys.stderr)
        return 2

    # Trata --grants-para se fornecido
    papeis_grants = None
    if args.grants_para:
        try:
            papeis_grants = _parse_grants_arg(args.grants_para)
        except Exception as exc:
            msg = "Configuracao invalida de grants: %s" % exc
            _registrar_critico_config(msg, cfg)
            print(msg, file=sys.stderr)
            return 2

    # Modo DRY-RUN: imprime DDL e/ou GRANTs e sai com 0
    if args.dry_run:
        script_ddl = ddl_builder.gerar_script_ddl(owner, prefixo, lob_storage=lob_storage)
        print(script_ddl)
        if papeis_grants:
            print("\n-- ==============================================================================")
            print("-- GRANTS POR PAPEL (README §11.1)")
            print("-- ==============================================================================")
            grants = ddl_builder.gerar_grants_por_papel(owner, prefixo, papeis_grants)
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

        valida, msg_pol = security.validar_politica_senha(admin_senha)
        if not valida:
            print("Senha do administrador viola politica de complexidade: %s" % msg_pol, file=sys.stderr)
            return 2

    try:
        conn = _conectar(cfg, usuario_dono, senha_dono)
    except Exception as exc:
        msg = "Falha de conexao com o banco Oracle: %s" % exc
        logger.critical(msg, extra={"agente": "-", "ticket": "-", "acao": "INIT_DB"})
        print(msg, file=sys.stderr)
        return 1

    try:
        # Validacao de protecao em DEV
        if getattr(cfg.app, "sss_env", "DEV") == "DEV":
            _validar_schema_descartavel_dev(cfg, usuario_dono, conn)

        # Checagem de versao do esquema atual
        esquema = sql_ident.nomes(prefixo)
        cursor = conn.cursor()
        tb_ctl = "{}.{}".format(owner, esquema["controle"]["tabela"])
        versao_banco = 0
        try:
            cursor.execute("SELECT versao_esquema FROM {} WHERE id = 1".format(tb_ctl))
            row = cursor.fetchone()
            if row:
                versao_banco = row[0]
        except Exception:
            # Tabela controle ainda nao existe -> versao 0 (base vazia)
            versao_banco = 0
        finally:
            cursor.close()

        if versao_banco > sql_ident.VERSAO_ESQUEMA:
            msg = "Versao do banco (%d) e maior que a versao suportada pelo codigo (%d)" % (
                versao_banco, sql_ident.VERSAO_ESQUEMA
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
            grants = ddl_builder.gerar_grants_por_papel(owner, prefixo, papeis_grants)
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
