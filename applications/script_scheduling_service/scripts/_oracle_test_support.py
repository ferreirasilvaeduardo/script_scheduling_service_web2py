# -*- coding: utf-8 -*-
"""Suporte a testes reais e contratos Oracle com schemas descartaveis (F7.2, F7.3).

Garante que nenhuma operacao real rode fora de DEV ou sobre esquemas nao descartaveis.
O helper nao importa drivers diretamente: toda conexao passa por db_conn.
"""
import os
import re

try:
    import _testenv  # noqa: F401
except ImportError:
    pass

try:
    import db_conn
except ImportError:
    from modules import db_conn

PREFIXO_OWNER_RESERVADO = "SSS_TEST_"


class PrecondicaoSchemaErro(RuntimeError):
    """Lancado quando um schema nao atende as garantias estritas de descartabilidade."""
    pass


def verificar_precondicoes_ambiente(cfg=None, owner_configurado=None):
    """Verifica se as pre-condicoes de ambiente para testes Oracle estao atendidas.

    Retorna tupla (bool, str).
    """
    dsn_env = os.environ.get("SSS_TEST_DSN")
    owner_env = os.environ.get("SSS_TEST_OWNER")
    disp_env = os.environ.get("SSS_TEST_SCHEMA_DISPOSABLE")

    if not dsn_env or not owner_env or not disp_env:
        return False, "Sinalizadores de teste ausentes ou incompletos (SSS_TEST_DSN/OWNER/DISPOSABLE)"

    if disp_env != "1":
        return False, "SSS_TEST_SCHEMA_DISPOSABLE deve ser exatamente '1'"

    owner_limpo = owner_env.strip().upper()
    if not owner_limpo.startswith(PREFIXO_OWNER_RESERVADO):
        return False, (
            "SSS_TEST_OWNER '%s' invalido: deve ter o prefixo reservado '%s'"
            % (owner_env, PREFIXO_OWNER_RESERVADO)
        )

    if not re.match(r"^SSS_TEST_[A-Za-z0-9_]{1,21}$", owner_limpo):
        return False, "SSS_TEST_OWNER '%s' invalido: caracteres invalidos ou comprimento excessivo" % owner_env

    if owner_configurado:
        if (owner_configurado or "").strip().upper() != owner_limpo:
            return False, "Owner configurado '%s' difere de SSS_TEST_OWNER '%s'" % (owner_configurado, owner_env)

    if cfg is not None:
        if getattr(getattr(cfg, "app", None), "sss_env", None) != "DEV":
            return False, "Ambiente deve ser DEV para testes Oracle descartaveis"
        if getattr(getattr(cfg, "app", None), "data_backend", None) != "ORACLE":
            return False, "data_backend deve ser ORACLE para testes Oracle descartaveis"

        cfg_dsn = getattr(getattr(cfg, "oracle", None), "dsn", "").strip()
        if cfg_dsn != dsn_env.strip():
            return False, "DSN em cfg '%s' difere de SSS_TEST_DSN '%s'" % (cfg_dsn, dsn_env)

        cfg_owner = getattr(getattr(cfg, "oracle", None), "owner", "").strip().upper()
        if cfg_owner != owner_limpo:
            return False, "Owner em cfg '%s' difere de SSS_TEST_OWNER '%s'" % (cfg_owner, owner_env)

    return True, ""


def validar_schema_descartavel(conn, owner_configurado, usuario_sessao_esperado):
    """Valida as pre-condicoes e confere a identidade da sessao real contra o esperado."""
    disposable = os.environ.get("SSS_TEST_SCHEMA_DISPOSABLE")
    if disposable != "1":
        raise PrecondicaoSchemaErro("SSS_TEST_SCHEMA_DISPOSABLE deve ser exatamente '1'")

    owner_env = os.environ.get("SSS_TEST_OWNER")
    if not owner_env:
        raise PrecondicaoSchemaErro("Variavel de ambiente SSS_TEST_OWNER nao configurada")

    owner_limpo = owner_env.strip().upper()
    if not owner_limpo.startswith(PREFIXO_OWNER_RESERVADO) or not re.match(r"^SSS_TEST_[A-Za-z0-9_]{1,21}$", owner_limpo):
        raise PrecondicaoSchemaErro(
            "SSS_TEST_OWNER '%s' invalido: deve iniciar com '%s' e conter apenas caracteres seguros"
            % (owner_env, PREFIXO_OWNER_RESERVADO)
        )

    if (owner_configurado or "").strip().upper() != owner_limpo:
        raise PrecondicaoSchemaErro(
            "Owner configurado '%s' difere de SSS_TEST_OWNER '%s'" % (owner_configurado, owner_env)
        )

    if (usuario_sessao_esperado or "").strip().upper() == owner_limpo:
        raise PrecondicaoSchemaErro(
            "Conta de sessao '%s' nao pode ser a conta dona do esquema '%s'"
            % (usuario_sessao_esperado, owner_configurado)
        )

    cur = conn.cursor()
    try:
        cur.execute("SELECT USER FROM DUAL")
        row = cur.fetchone()
        if not row:
            raise PrecondicaoSchemaErro("Nenhum usuario retornado por SELECT USER FROM DUAL")
        user_sessao = str(row[0]).strip().upper()
        if user_sessao != (usuario_sessao_esperado or "").strip().upper():
            raise PrecondicaoSchemaErro(
                "Usuario de sessao real '%s' difere do esperado '%s'"
                % (user_sessao, usuario_sessao_esperado)
            )
        if user_sessao == owner_limpo:
            raise PrecondicaoSchemaErro(
                "Sessao Oracle real esta conectada como owner '%s'; exigida conta de teste distinta"
                % owner_limpo
            )
    finally:
        cur.close()

    return owner_limpo


def preparar_schema_descartavel(papel="web", cfg=None, segredos=None):
    """Prepara e valida a conexao com o schema descartavel para o papel solicitado."""
    try:
        import sss_config
    except ImportError:
        from modules import sss_config

    if cfg is None:
        cfg = sss_config.obter_config()

    ok, motivo = verificar_precondicoes_ambiente(cfg=cfg)
    if not ok:
        raise PrecondicaoSchemaErro(motivo)

    cfg_owner = getattr(getattr(cfg, "oracle", None), "owner", "").strip().upper()
    usuario_esperado = getattr(getattr(cfg, "oracle", None), "user", None)
    if papel == "purge":
        usuario_esperado = getattr(getattr(cfg, "retencao", None), "purge_user", None)
    elif papel == "monitor":
        usuario_esperado = getattr(getattr(cfg, "monitor", None), "user", None)

    if usuario_esperado and usuario_esperado.strip().upper() == cfg_owner:
        raise PrecondicaoSchemaErro("Usuario de teste '%s' nao pode ser o owner do esquema" % usuario_esperado)

    if segredos is None:
        segredos = sss_config.carregar_segredos(cfg.secrets.secrets_file, cfg=cfg, papel=papel)

    import sys
    try:
        import db_conn
    except ImportError:
        from modules import db_conn
    conn_mod = sys.modules.get("db_conn", db_conn)

    conn = conn_mod.conectar(cfg, segredos, papel)
    try:
        validar_schema_descartavel(conn, cfg_owner, usuario_esperado)
    finally:
        conn.close()

    return cfg