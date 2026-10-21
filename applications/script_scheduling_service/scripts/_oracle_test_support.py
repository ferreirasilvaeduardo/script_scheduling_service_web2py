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

CHAVE = "SSS_TEST_ORACLE"
PREFIXO_OWNER_RESERVADO = "SSS_TEST_"
MODO_DESCARTAVEL = "DESCARTAVEL"
MODO_COMPARTILHADO = "COMPARTILHADO"
# Variaveis da versao anterior da guarda: recusadas para nao serem ignoradas em silencio.
VARIAVEIS_ANTIGAS = ("SSS_TEST_DSN", "SSS_TEST_OWNER", "SSS_TEST_CONFIG",
                     "SSS_TEST_SCHEMA_DISPOSABLE", "SSS_TEST_SCHEMA_COMPARTILHADO")
_RE_OWNER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,29}$")
_RE_OWNER_DESCARTAVEL = re.compile(r"^SSS_TEST_[A-Za-z0-9_]{1,21}$")

_modo_atual = None


class PrecondicaoSchemaErro(RuntimeError):
    """Lancado quando o banco ou o esquema nao atendem as garantias dos testes reais."""
    pass


def banco_real_configurado():
    """True quando os testes contra o Oracle real foram ligados (SSS_TEST_ORACLE=1)."""
    return os.environ.get(CHAVE) == "1"


def modo_do_owner(owner):
    """DESCARTAVEL para owner SSS_TEST_*; COMPARTILHADO para os demais."""
    return MODO_DESCARTAVEL if (owner or "").strip().upper().startswith(PREFIXO_OWNER_RESERVADO) \
        else MODO_COMPARTILHADO


def modo_schema():
    """Modo validado por preparar_schema_descartavel nesta execucao; None antes dela."""
    return _modo_atual


def _cfg_oracle(cfg, campo):
    return (getattr(getattr(cfg, "oracle", None), campo, None) or "").strip()


def verificar_precondicoes_ambiente(cfg=None):
    """Verifica a chave, o ambiente e o owner antes de qualquer conexao. Retorna (bool, motivo)."""
    if not banco_real_configurado():
        return False, "Testes Oracle reais desligados: defina %s=1" % CHAVE
    antigas = [v for v in VARIAVEIS_ANTIGAS if os.environ.get(v)]
    if antigas:
        return False, ("Variaveis antigas definidas (%s): owner, prefixo e DSN vem so do instance/config.ini; "
                       "use apenas %s=1" % (", ".join(antigas), CHAVE))
    if cfg is None:
        return True, ""

    if getattr(getattr(cfg, "app", None), "sss_env", None) != "DEV":
        return False, "Ambiente deve ser DEV para testes Oracle reais"
    if not _cfg_oracle(cfg, "dsn"):
        return False, "[oracle] dsn vazio no config"
    owner = _cfg_oracle(cfg, "owner").upper()
    if not _RE_OWNER.match(owner):
        return False, "[oracle] owner invalido no config"
    if modo_do_owner(owner) == MODO_DESCARTAVEL and not _RE_OWNER_DESCARTAVEL.match(owner):
        return False, "Owner descartavel '%s' invalido: caracteres invalidos ou comprimento excessivo" % owner
    return True, ""


def validar_schema_descartavel(conn, owner_configurado, usuario_sessao_esperado, prefixo="tbsss_"):
    """Confere a sessao real (USER) e, no modo compartilhado, o esquema SSS na versao do codigo.

    No modo descartavel, a conta de sessao nunca pode ser a dona do esquema.
    """
    owner = (owner_configurado or "").strip().upper()
    if not _RE_OWNER.match(owner):
        raise PrecondicaoSchemaErro("Owner configurado invalido")
    modo = modo_do_owner(owner)
    if modo == MODO_DESCARTAVEL and not _RE_OWNER_DESCARTAVEL.match(owner):
        raise PrecondicaoSchemaErro("Owner descartavel '%s' invalido" % owner)
    compartilhado = modo == MODO_COMPARTILHADO
    esperado = (usuario_sessao_esperado or "").strip().upper()

    if not compartilhado and esperado == owner:
        raise PrecondicaoSchemaErro(
            "Conta de sessao '%s' nao pode ser a conta dona do esquema descartavel '%s'"
            % (usuario_sessao_esperado, owner_configurado)
        )

    cur = conn.cursor()
    try:
        cur.execute("SELECT USER FROM DUAL")
        row = cur.fetchone()
        if not row:
            raise PrecondicaoSchemaErro("Nenhum usuario retornado por SELECT USER FROM DUAL")
        user_sessao = str(row[0]).strip().upper()
        if user_sessao != esperado:
            raise PrecondicaoSchemaErro(
                "Usuario de sessao real '%s' difere do esperado '%s'" % (user_sessao, usuario_sessao_esperado)
            )
        if user_sessao == owner and not compartilhado:
            raise PrecondicaoSchemaErro(
                "Sessao Oracle real esta conectada como owner '%s'; exigida conta de teste distinta" % owner
            )
        if compartilhado:
            _conferir_esquema_sss(cur, owner, prefixo)
    finally:
        cur.close()

    return owner


def _conferir_esquema_sss(cur, owner, prefixo):
    """Owner existente: so aceita se o esquema SSS estiver implantado na versao do codigo."""
    try:
        import sql_ident
    except ImportError:
        from modules import sql_ident
    tabela = sql_ident.table(owner, prefixo or "tbsss_", "control")
    try:
        cur.execute("SELECT schema_version FROM " + tabela)
        row = cur.fetchone()
    except Exception as exc:
        raise PrecondicaoSchemaErro("Esquema SSS ausente no owner '%s' (%s)" % (owner, type(exc).__name__))
    if not row or int(row[0]) != sql_ident.SCHEMA_VERSION:
        raise PrecondicaoSchemaErro(
            "Versao do esquema SSS em '%s' (%s) difere da do codigo (%s)"
            % (owner, row[0] if row else None, sql_ident.SCHEMA_VERSION)
        )


def preparar_schema_descartavel(papel="web", cfg=None, segredos=None):
    """Valida o banco real para o papel e devolve o cfg do instance/config.ini (ou o informado)."""
    global _modo_atual
    try:
        import sss_config
    except ImportError:
        from modules import sss_config

    ok, motivo = verificar_precondicoes_ambiente()
    if not ok:
        raise PrecondicaoSchemaErro(motivo)
    if cfg is None:
        cfg = sss_config.get_config()
    ok, motivo = verificar_precondicoes_ambiente(cfg=cfg)
    if not ok:
        raise PrecondicaoSchemaErro(motivo)

    cfg_owner = _cfg_oracle(cfg, "owner").upper()
    modo = modo_do_owner(cfg_owner)
    usuario_esperado = getattr(getattr(cfg, "oracle", None), "user", None)
    if papel == "purge":
        usuario_esperado = getattr(getattr(cfg, "retention", None), "purge_user", None)
    elif papel == "monitor":
        usuario_esperado = getattr(getattr(cfg, "monitor", None), "user", None)

    if modo == MODO_DESCARTAVEL and usuario_esperado and usuario_esperado.strip().upper() == cfg_owner:
        raise PrecondicaoSchemaErro("Usuario de teste '%s' nao pode ser o owner do esquema" % usuario_esperado)

    if segredos is None:
        segredos = sss_config.load_secrets(cfg.secrets.secrets_file, cfg=cfg, papel=papel)

    import sys
    try:
        import db_conn
    except ImportError:
        from modules import db_conn
    conn_mod = sys.modules.get("db_conn", db_conn)

    conn = conn_mod.connect(cfg, segredos, papel)
    try:
        prefixo = _cfg_oracle(cfg, "table_prefix") or "tbsss_"
        validar_schema_descartavel(conn, cfg_owner, usuario_esperado, prefixo=prefixo)
    finally:
        conn.close()

    _modo_atual = modo
    return cfg
