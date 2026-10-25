# -*- coding: utf-8 -*-
"""Suporte a testes reais e contratos Oracle (F7.2, F7.3; README §2.5, "Testes Oracle reais").

Uma chave so: SSS_TEST_ORACLE=1. Owner, prefixo, DSN e conta vem do instance/config.ini, os mesmos
da aplicacao; nada e repetido em variaveis de ambiente. Garante que nenhuma operacao real rode fora
de DEV ou sobre um esquema nao autorizado. O modo e deduzido do owner:
- DESCARTAVEL (owner SSS_TEST_*): owner dedicado e conta de teste distinta do owner;
- COMPARTILHADO (qualquer outro owner, ex.: openrisow no GFPR): owner existente onde nao e possivel
  criar outro. Aceita a conta igual ao owner, mas exige o esquema SSS na versao do codigo
  (tbsss_control); os testes so gravam registros proprios e limpam apenas os proprios IDs.
O data_backend do config nao importa aqui: ele e escolha da aplicacao; os testes usam a secao [oracle].
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

KEY = "SSS_TEST_ORACLE"
RESERVED_OWNER_PREFIX = "SSS_TEST_"
DISPOSABLE_MODE = "DESCARTAVEL"
SHARED_MODE = "COMPARTILHADO"
# Variaveis da versao anterior da guarda: recusadas para nao serem ignoradas em silencio.
OLD_VARIABLES = ("SSS_TEST_DSN", "SSS_TEST_OWNER", "SSS_TEST_CONFIG",
                     "SSS_TEST_SCHEMA_DISPOSABLE", "SSS_TEST_SCHEMA_COMPARTILHADO")
_RE_OWNER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,29}$")
_RE_DISPOSABLE_OWNER = re.compile(r"^SSS_TEST_[A-Za-z0-9_]{1,21}$")

_current_mode = None


class SchemaPreconditionError(RuntimeError):
    """Lancado quando o banco ou o esquema nao atendem as garantias dos testes reais."""
    pass


def real_db_configured():
    """True quando os testes contra o Oracle real foram ligados (SSS_TEST_ORACLE=1)."""
    return os.environ.get(KEY) == "1"


def owner_mode(owner):
    """DESCARTAVEL para owner SSS_TEST_*; COMPARTILHADO para os demais."""
    return DISPOSABLE_MODE if (owner or "").strip().upper().startswith(RESERVED_OWNER_PREFIX) \
        else SHARED_MODE


def schema_mode():
    """Modo validado por prepare_disposable_schema nesta execucao; None antes dela."""
    return _current_mode


def _cfg_oracle(cfg, field):
    return (getattr(getattr(cfg, "oracle", None), field, None) or "").strip()


def check_environment_preconditions(cfg=None):
    """Verifica a chave, o ambiente e o owner antes de qualquer conexao. Retorna (bool, motivo)."""
    if not real_db_configured():
        return False, "Testes Oracle reais desligados: defina %s=1" % KEY
    old = [v for v in OLD_VARIABLES if os.environ.get(v)]
    if old:
        return False, ("Variaveis antigas definidas (%s): owner, prefixo e DSN vem so do instance/config.ini; "
                       "use apenas %s=1" % (", ".join(old), KEY))
    if cfg is None:
        return True, ""

    if getattr(getattr(cfg, "app", None), "sss_env", None) != "DEV":
        return False, "Ambiente deve ser DEV para testes Oracle reais"
    if not _cfg_oracle(cfg, "dsn"):
        return False, "[oracle] dsn vazio no config"
    owner = _cfg_oracle(cfg, "owner").upper()
    if not _RE_OWNER.match(owner):
        return False, "[oracle] owner invalido no config"
    if owner_mode(owner) == DISPOSABLE_MODE and not _RE_DISPOSABLE_OWNER.match(owner):
        return False, "Owner descartavel '%s' invalido: caracteres invalidos ou comprimento excessivo" % owner
    return True, ""


def validate_disposable_schema(conn, configured_owner, expected_session_user, prefix="tbsss_"):
    """Confere a sessao real (USER) e, no modo compartilhado, o esquema SSS na versao do codigo.

    No modo descartavel, a conta de sessao nunca pode ser a dona do esquema.
    """
    owner = (configured_owner or "").strip().upper()
    if not _RE_OWNER.match(owner):
        raise SchemaPreconditionError("Owner configurado invalido")
    mode = owner_mode(owner)
    if mode == DISPOSABLE_MODE and not _RE_DISPOSABLE_OWNER.match(owner):
        raise SchemaPreconditionError("Owner descartavel '%s' invalido" % owner)
    shared = mode == SHARED_MODE
    expected = (expected_session_user or "").strip().upper()

    if not shared and expected == owner:
        raise SchemaPreconditionError(
            "Conta de sessao '%s' nao pode ser a conta dona do esquema descartavel '%s'"
            % (expected_session_user, configured_owner)
        )

    cur = conn.cursor()
    try:
        cur.execute("SELECT USER FROM DUAL")
        row = cur.fetchone()
        if not row:
            raise SchemaPreconditionError("Nenhum usuario retornado por SELECT USER FROM DUAL")
        user_session = str(row[0]).strip().upper()
        if user_session != expected:
            raise SchemaPreconditionError(
                "Usuario de sessao real '%s' difere do esperado '%s'" % (user_session, expected_session_user)
            )
        if user_session == owner and not shared:
            raise SchemaPreconditionError(
                "Sessao Oracle real esta conectada como owner '%s'; exigida conta de teste distinta" % owner
            )
        if shared:
            _check_sss_schema(cur, owner, prefix)
    finally:
        cur.close()

    return owner


def _check_sss_schema(cur, owner, prefix):
    """Owner existente: so aceita se o esquema SSS estiver implantado na versao do codigo."""
    try:
        import sql_ident
    except ImportError:
        from modules import sql_ident
    table = sql_ident.table(owner, prefix or "tbsss_", "control")
    try:
        cur.execute("SELECT schema_version FROM " + table)
        row = cur.fetchone()
    except Exception as exc:
        raise SchemaPreconditionError("Esquema SSS ausente no owner '%s' (%s)" % (owner, type(exc).__name__))
    if not row or int(row[0]) != sql_ident.SCHEMA_VERSION:
        raise SchemaPreconditionError(
            "Versao do esquema SSS em '%s' (%s) difere da do codigo (%s)"
            % (owner, row[0] if row else None, sql_ident.SCHEMA_VERSION)
        )


def prepare_disposable_schema(role="web", cfg=None, secrets=None):
    """Valida o banco real para o papel e devolve o cfg do instance/config.ini (ou o informado)."""
    global _current_mode
    try:
        import sss_config
    except ImportError:
        from modules import sss_config

    ok, reason = check_environment_preconditions()
    if not ok:
        raise SchemaPreconditionError(reason)
    if cfg is None:
        cfg = sss_config.get_config()
    ok, reason = check_environment_preconditions(cfg=cfg)
    if not ok:
        raise SchemaPreconditionError(reason)

    cfg_owner = _cfg_oracle(cfg, "owner").upper()
    mode = owner_mode(cfg_owner)
    user_expected = getattr(getattr(cfg, "oracle", None), "user", None)
    if role == "purge":
        user_expected = getattr(getattr(cfg, "retention", None), "purge_user", None)
    elif role == "monitor":
        user_expected = getattr(getattr(cfg, "monitor", None), "user", None)

    if mode == DISPOSABLE_MODE and user_expected and user_expected.strip().upper() == cfg_owner:
        raise SchemaPreconditionError("Usuario de teste '%s' nao pode ser o owner do esquema" % user_expected)

    if secrets is None:
        secrets = sss_config.load_secrets(cfg.secrets.secrets_file, cfg=cfg, role=role)

    import sys
    try:
        import db_conn
    except ImportError:
        from modules import db_conn
    conn_mod = sys.modules.get("db_conn", db_conn)

    conn = conn_mod.connect(cfg, secrets, role)
    try:
        prefix = _cfg_oracle(cfg, "table_prefix") or "tbsss_"
        validate_disposable_schema(conn, cfg_owner, user_expected, prefix=prefix)
    finally:
        conn.close()

    _current_mode = mode
    return cfg
