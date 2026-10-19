# -*- coding: utf-8 -*-
"""Suporte a testes reais e contratos Oracle com schemas descartaveis (F7.2, F7.3).

Garante que nenhuma operacao real rode fora de DEV ou sobre esquemas nao autorizados.
Dois modos, sempre explicitos e mutuamente exclusivos (README §2.5, "Testes Oracle reais"):
- DESCARTAVEL (SSS_TEST_SCHEMA_DISPOSABLE=1): owner SSS_TEST_* dedicado e conta de teste distinta;
- COMPARTILHADO (SSS_TEST_SCHEMA_COMPARTILHADO=1): owner existente onde nao e possivel criar outro
  (ex.: openrisow no GFPR). Aceita a conta igual ao owner, mas exige o esquema SSS na versao do
  codigo (tbsss_controle); os testes so gravam registros proprios e limpam apenas os proprios IDs.
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
MODO_DESCARTAVEL = "DESCARTAVEL"
MODO_COMPARTILHADO = "COMPARTILHADO"
_RE_OWNER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,29}$")


class PrecondicaoSchemaErro(RuntimeError):
    """Lancado quando um schema nao atende as garantias estritas de descartabilidade."""
    pass


def modo_schema():
    """Modo de teste Oracle declarado no ambiente; None se ausente, invalido ou ambiguo."""
    disp = os.environ.get("SSS_TEST_SCHEMA_DISPOSABLE")
    comp = os.environ.get("SSS_TEST_SCHEMA_COMPARTILHADO")
    if disp and comp:
        return None
    if comp == "1":
        return MODO_COMPARTILHADO
    if disp == "1":
        return MODO_DESCARTAVEL
    return None


def banco_real_configurado():
    """True quando DSN, owner e exatamente um modo valido foram declarados."""
    return bool(os.environ.get("SSS_TEST_DSN") and os.environ.get("SSS_TEST_OWNER") and modo_schema())


def _validar_owner_do_modo(modo, owner_env):
    """Devolve (owner normalizado, motivo da recusa ou '')."""
    owner_limpo = owner_env.strip().upper()
    if modo == MODO_COMPARTILHADO:
        if not _RE_OWNER.match(owner_limpo):
            return owner_limpo, "SSS_TEST_OWNER '%s' invalido: caracteres invalidos ou comprimento excessivo" % owner_env
        return owner_limpo, ""
    if not owner_limpo.startswith(PREFIXO_OWNER_RESERVADO):
        return owner_limpo, (
            "SSS_TEST_OWNER '%s' invalido: deve ter o prefixo reservado '%s'"
            % (owner_env, PREFIXO_OWNER_RESERVADO)
        )
    if not re.match(r"^SSS_TEST_[A-Za-z0-9_]{1,21}$", owner_limpo):
        return owner_limpo, "SSS_TEST_OWNER '%s' invalido: caracteres invalidos ou comprimento excessivo" % owner_env
    return owner_limpo, ""


def verificar_precondicoes_ambiente(cfg=None, owner_configurado=None):
    """Verifica se as pre-condicoes de ambiente para testes Oracle estao atendidas.

    Retorna tupla (bool, str).
    """
    dsn_env = os.environ.get("SSS_TEST_DSN")
    owner_env = os.environ.get("SSS_TEST_OWNER")
    disp_env = os.environ.get("SSS_TEST_SCHEMA_DISPOSABLE")
    comp_env = os.environ.get("SSS_TEST_SCHEMA_COMPARTILHADO")

    if not dsn_env or not owner_env or not (disp_env or comp_env):
        return False, "Sinalizadores de teste ausentes ou incompletos (SSS_TEST_DSN/OWNER/DISPOSABLE)"

    if disp_env and comp_env:
        return False, "Declare um so modo: SSS_TEST_SCHEMA_DISPOSABLE ou SSS_TEST_SCHEMA_COMPARTILHADO"
    if disp_env and disp_env != "1":
        return False, "SSS_TEST_SCHEMA_DISPOSABLE deve ser exatamente '1'"
    if comp_env and comp_env != "1":
        return False, "SSS_TEST_SCHEMA_COMPARTILHADO deve ser exatamente '1'"

    owner_limpo, motivo = _validar_owner_do_modo(modo_schema(), owner_env)
    if motivo:
        return False, motivo

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


def validar_schema_descartavel(conn, owner_configurado, usuario_sessao_esperado, prefixo="tbsss_"):
    """Valida as pre-condicoes e confere a identidade da sessao real contra o esperado.

    No modo COMPARTILHADO, a conta pode ser o proprio owner, mas o esquema SSS precisa existir
    na versao do codigo (tbsss_controle.versao_esquema = sql_ident.VERSAO_ESQUEMA).
    """
    modo = modo_schema()
    if modo is None:
        raise PrecondicaoSchemaErro(
            "SSS_TEST_SCHEMA_DISPOSABLE deve ser exatamente '1' (ou, num owner existente, "
            "SSS_TEST_SCHEMA_COMPARTILHADO=1; nunca os dois)"
        )

    owner_env = os.environ.get("SSS_TEST_OWNER")
    if not owner_env:
        raise PrecondicaoSchemaErro("Variavel de ambiente SSS_TEST_OWNER nao configurada")

    owner_limpo, motivo = _validar_owner_do_modo(modo, owner_env)
    if motivo:
        raise PrecondicaoSchemaErro(motivo)
    compartilhado = modo == MODO_COMPARTILHADO

    if (owner_configurado or "").strip().upper() != owner_limpo:
        raise PrecondicaoSchemaErro(
            "Owner configurado '%s' difere de SSS_TEST_OWNER '%s'" % (owner_configurado, owner_env)
        )

    if not compartilhado and (usuario_sessao_esperado or "").strip().upper() == owner_limpo:
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
        if user_sessao == owner_limpo and not compartilhado:
            raise PrecondicaoSchemaErro(
                "Sessao Oracle real esta conectada como owner '%s'; exigida conta de teste distinta"
                % owner_limpo
            )
        if compartilhado:
            _conferir_esquema_sss(cur, owner_limpo, prefixo)
    finally:
        cur.close()

    return owner_limpo


def _conferir_esquema_sss(cur, owner, prefixo):
    """Owner existente: so aceita se o esquema SSS estiver implantado na versao do codigo."""
    try:
        import sql_ident
    except ImportError:
        from modules import sql_ident
    tabela = sql_ident.qualificar(owner, (prefixo or "tbsss_") + "controle", prefixo=prefixo or "tbsss_")
    try:
        cur.execute("SELECT versao_esquema FROM " + tabela)
        row = cur.fetchone()
    except Exception as exc:
        raise PrecondicaoSchemaErro("Esquema SSS ausente no owner '%s' (%s)" % (owner, type(exc).__name__))
    if not row or int(row[0]) != sql_ident.VERSAO_ESQUEMA:
        raise PrecondicaoSchemaErro(
            "Versao do esquema SSS em '%s' (%s) difere da do codigo (%s)"
            % (owner, row[0] if row else None, sql_ident.VERSAO_ESQUEMA)
        )


def preparar_schema_descartavel(papel="web", cfg=None, segredos=None):
    """Prepara e valida a conexao com o schema descartavel para o papel solicitado."""
    try:
        import sss_config
    except ImportError:
        from modules import sss_config

    if cfg is None:
        # SSS_TEST_CONFIG: config.ini so dos testes (ex.: data_backend = ORACLE), sem mexer no instance/.
        caminho_teste = os.environ.get("SSS_TEST_CONFIG")
        cfg = sss_config.carregar(caminho_teste) if caminho_teste else sss_config.obter_config()

    ok, motivo = verificar_precondicoes_ambiente(cfg=cfg)
    if not ok:
        raise PrecondicaoSchemaErro(motivo)

    cfg_owner = getattr(getattr(cfg, "oracle", None), "owner", "").strip().upper()
    usuario_esperado = getattr(getattr(cfg, "oracle", None), "user", None)
    if papel == "purge":
        usuario_esperado = getattr(getattr(cfg, "retencao", None), "purge_user", None)
    elif papel == "monitor":
        usuario_esperado = getattr(getattr(cfg, "monitor", None), "user", None)

    if (modo_schema() != MODO_COMPARTILHADO and usuario_esperado
            and usuario_esperado.strip().upper() == cfg_owner):
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
        prefixo = getattr(getattr(cfg, "oracle", None), "table_prefix", None) or "tbsss_"
        validar_schema_descartavel(conn, cfg_owner, usuario_esperado, prefixo=prefixo)
    finally:
        conn.close()

    return cfg