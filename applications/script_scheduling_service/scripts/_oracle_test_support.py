# -*- coding: utf-8 -*-
"""Preflight de seguranca para testes Oracle com escrita."""
import os
import re


_RE_TEST_OWNER = re.compile(r"^SSS_TEST_[A-Z0-9_]{1,21}$", re.IGNORECASE)


def _owner_esperado():
    owner = os.environ.get("SSS_TEST_OWNER")
    if os.environ.get("SSS_TEST_SCHEMA_DISPOSABLE") != "1" or not owner:
        raise RuntimeError("Defina SSS_TEST_OWNER e SSS_TEST_SCHEMA_DISPOSABLE=1 para testes Oracle")
    if not _RE_TEST_OWNER.match(owner):
        raise RuntimeError("SSS_TEST_OWNER deve usar o prefixo reservado SSS_TEST_")
    return owner.upper()


def validar_schema_descartavel(conn, owner_configurado, usuario_sessao_esperado):
    """Confere o opt-in, o owner alvo e a conta Oracle efetivamente conectada."""
    owner = _owner_esperado()
    if str(owner_configurado).upper() != owner:
        raise RuntimeError("SSS_TEST_OWNER difere do owner configurado")
    if not usuario_sessao_esperado:
        raise RuntimeError("Usuario Oracle esperado nao configurado para o teste")

    cursor = conn.cursor()
    try:
        cursor.execute("SELECT USER FROM DUAL")
        row = cursor.fetchone()
        if row is None or not row[0]:
            raise RuntimeError("Oracle nao retornou o usuario da sessao")
        if str(row[0]).upper() != str(usuario_sessao_esperado).upper():
            raise RuntimeError("Usuario Oracle da sessao difere da conta configurada")
    finally:
        cursor.close()
    return owner


def preparar_schema_descartavel(papel):
    """Abre, valida e fecha uma conexao de preflight sem executar DML."""
    if papel not in ("web", "agente", "purge"):
        raise RuntimeError("Papel Oracle nao suportado para teste")
    owner = _owner_esperado()
    dsn_teste = os.environ.get("SSS_TEST_DSN")
    if not dsn_teste:
        raise RuntimeError("SSS_TEST_DSN obrigatorio para testes Oracle")

    import db_conn
    import sss_config

    cfg = sss_config.obter_config()
    if str(cfg.app.data_backend).upper() != "ORACLE":
        raise RuntimeError("Testes Oracle exigem data_backend=ORACLE na configuracao")
    if str(cfg.app.sss_env).upper() != "DEV":
        raise RuntimeError("Testes Oracle com escrita exigem sss_env=DEV")
    if str(cfg.oracle.owner).upper() != owner:
        raise RuntimeError("SSS_TEST_OWNER difere do owner configurado")
    if str(cfg.oracle.user).upper() == owner:
        raise RuntimeError("Conta de teste deve ser distinta do owner do schema")
    if cfg.oracle.dsn != dsn_teste:
        raise RuntimeError("SSS_TEST_DSN difere do DSN configurado")

    papel_segredos = "agente" if papel == "purge" else papel
    segredos = sss_config.carregar_segredos(
        cfg.secrets.secrets_file, cfg=cfg, papel=papel_segredos
    )
    if papel == "purge":
        usuario_esperado = cfg.retencao.purge_user
    else:
        usuario_esperado = cfg.oracle.user

    conn = db_conn.conectar(cfg, segredos, papel)
    try:
        validar_schema_descartavel(conn, cfg.oracle.owner, usuario_esperado)
    finally:
        conn.close()
    return cfg