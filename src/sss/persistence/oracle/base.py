# -*- coding: utf-8 -*-
"""Base e utilitarios compartilhados para os repositorios Oracle 11gR2 (F7.3).

Garante que nenhum modulo de repo_oracle importe oracledb ou cx_Oracle diretamente:
todo acesso ao driver passa exclusivamente por db_conn.py (CR-002, AGENTS §2.2).
"""
import atexit
import collections
import contextlib
import datetime
import re
import threading

from sss.config import app_context
from sss.persistence import db_conn
from sss.persistence import repo_errors
from sss.core import sql_ident
from sss.config import sss_config

_RE_CONSTRAINT = re.compile(r"\((?:[A-Za-z0-9_]+\.)?([A-Za-z0-9_]+)\)")

# Um pool por processo para o papel web (README §2.3, CR-007 R-12): abrir conexao nova custa ~15x
# mais que reaproveitar (medido no GFPR), e as telas fazem dezenas de leituras por requisicao.
_POOLS = {}
_POOLS_LOCK = threading.Lock()


def _pool_web(cfg, secrets):
    key = (getattr(cfg.oracle, "dsn", ""), getattr(cfg.oracle, "user", ""))
    with _POOLS_LOCK:
        pool = _POOLS.get(key)
        if pool is None:
            pool = db_conn.pool(cfg, secrets, role="web")
            _POOLS[key] = pool
        return pool


def discard_pools():
    """Fecha e esquece os pools do processo (testes e troca de configuracao)."""
    with _POOLS_LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for pool in pools:
        try:
            pool.close(force=True)
        except Exception:
            pass


# O pool do python-oracledb (Thin) espera a propria thread no __del__ durante a finalizacao do
# interpretador e o processo nunca termina; fechar no atexit (antes da finalizacao) evita o impasse.
atexit.register(discard_pools)


def validate_record_actor(audit=None, actor=None):
    """Valida e extrai o ator obrigatorio de registro (CR-006, README §10, AGENTS §4.15).

    Lanca RepoViolation antes de qualquer SQL se o ator for nulo, vazio ou exceder 40 chars.
    """
    at = None
    if isinstance(audit, dict):
        at = audit.get("actor")
    if not at and actor:
        at = actor

    if not at or not isinstance(at, str) or not at.strip() or len(at) > 40:
        raise repo_errors.RepoViolation("Ator obrigatorio e deve ter ate 40 caracteres")
    return at.strip()


_ACTOR_MAX = 40
_DETAIL_MAX = 1000


def validate_audit_fields(actor, detail):
    """ator NOT NULL ate 40 e detalhe ate 1.000 (README §4.4), sem valor padrao nem corte."""
    if not actor:
        raise repo_errors.RepoViolation("ator da auditoria e obrigatorio")
    if len(actor) > _ACTOR_MAX or (detail is not None and len(detail) > _DETAIL_MAX):
        raise repo_errors.RepoViolation("auditoria excede o tamanho da coluna (ORA-12899)")


def translate_oracle_error(exc, constraint_padrao=None, prefix=None):
    """Traduz excecoes Oracle capturadas para a hierarquia de repo_errors."""
    if isinstance(exc, repo_errors.RepoError):
        return exc

    pfx, num = db_conn.classify_error(exc)
    msg = str(exc)

    m = _RE_CONSTRAINT.search(msg)
    constraint = m.group(1).lower() if m else (constraint_padrao.lower() if constraint_padrao else None)

    if pfx == "ORA":
        if num in (1, 2290, 2291, 2292, 1400, 12899, 1438, 20001):
            if num == 1438 and not constraint:
                constraint = "ck_{}usr_tent".format(sql_ident.LOGICAL_PREFIX)
            elif num == 20001 and not constraint:
                constraint = "tr_{}usr_bu".format(sql_ident.LOGICAL_PREFIX)
            # O ORA- traz o nome fisico (uk_<prefixo>...); o servico traduz pelo nome logico.
            return repo_errors.RepoViolation(msg, constraint=sql_ident.logical_object_name(constraint, prefix))
        if num in (54, 30006, 60, 3156):
            return repo_errors.RepoConflict(msg)
    elif pfx in ("DPY", "DPI"):
        if db_conn.is_timeout(exc):
            return repo_errors.RepoConflict(msg)

    if db_conn.is_network_error(exc):
        return repo_errors.RepoUnavailable(msg)

    return repo_errors.RepoError(msg)


def write_audit(conn, sql_tbl_aud, sql_seq_aud, audit, entity, entity_id):
    """Grava linha(s) em tbsss_audit na mesma transacao (README §4.4, §10).

    Nunca corta nem completa valores (paridade com o FAKE e o test_06b do test_repo_contract): actor required com ate 40
    caracteres e detail com ate 1.000; fora disso, RepoViolation antes do INSERT, e a transacao toda
    e desfeita.
    """
    if not audit:
        return
    items = [audit] if isinstance(audit, dict) else audit
    for item in items:
        if not isinstance(item, dict):
            continue
        validate_audit_fields(item.get("actor"), item.get("detail"))
    cur = conn.cursor()
    try:
        for item in items:
            if not isinstance(item, dict):
                continue
            aid = db_conn.next_id(conn, sql_seq_aud)
            cur.execute(
                "INSERT INTO " + sql_tbl_aud + " "
                "(id, actor, source_ip, action, entity, entity_id, detail, created_at) "
                "VALUES (:id, :actor, :source_ip, :action, :entity, :entity_id, :detail, SYSDATE)",
                {
                    "id": aid,
                    "actor": item.get("actor"),
                    "source_ip": item.get("ip") or item.get("source_ip"),
                    "action": item["action"],
                    "entity": entity,
                    "entity_id": entity_id,
                    "detail": item.get("detail"),
                }
            )
    finally:
        cur.close()


class BaseRepoOracle(object):
    """Classe base para repositorios Oracle 11gR2."""

    def __init__(self, cfg=None, secrets=None):
        self._cfg = cfg
        self._secrets = secrets
        self._owner = None
        self._prefixo = None
        self._resolver_config()

    def _resolver_config(self):
        if self._cfg is None:
            self._cfg = app_context.get_config()
        if self._cfg is None:
            try:
                self._cfg = sss_config.get_config()
            except Exception:
                pass

        if self._cfg is not None:
            self._owner = getattr(getattr(self._cfg, "oracle", None), "owner", "openrisow").strip()
            self._prefixo = getattr(getattr(self._cfg, "oracle", None), "table_prefix", "tbsss_").strip()
        else:
            self._owner = "openrisow"
            self._prefixo = "tbsss_"

    def _obter_conexao(self):
        self._resolver_config()
        if self._secrets is None and self._cfg is not None:
            try:
                self._secrets = sss_config.load_secrets(
                    self._cfg.secrets.secrets_file, cfg=self._cfg, role="web"
                )
            except Exception:
                pass
        # Conexao do pool do processo; conn.close() a devolve ao pool.
        conn = _pool_web(self._cfg, self._secrets).acquire()
        return db_conn.configure_session(conn, self._cfg, "web")

    @contextlib.contextmanager
    def write_transaction(self, conn=None):
        """Gerencia contexto de transacao com COMMIT/ROLLBACK para operacoes de escrita."""
        close = False
        if conn is None:
            conn = self._obter_conexao()
            close = True
        try:
            with db_conn.transaction(conn):
                yield conn
        except Exception as exc:
            raise translate_oracle_error(exc, prefix=self._prefixo)
        finally:
            if close:
                try:
                    conn.close()
                except Exception:
                    pass

    @contextlib.contextmanager
    def read_context(self, conn=None):
        """Gerencia contexto de conexao para operacoes de leitura."""
        close = False
        if conn is None:
            conn = self._obter_conexao()
            close = True
        try:
            yield conn
        except Exception as exc:
            raise translate_oracle_error(exc, prefix=self._prefixo)
        finally:
            if close:
                try:
                    conn.close()
                except Exception:
                    pass

    def qualify_table(self, entity):
        return sql_ident.table(self._owner, self._prefixo, entity)

    def qualify_sequence(self, entity):
        return sql_ident.sequence(self._owner, self._prefixo, entity)

    def constraint_name(self, kind, entity, suffix):
        """Nome logico da constraint/indice para o RepoViolation (sql_ident.LOGICAL_PREFIX, README §9.1)."""
        abbr = sql_ident.TABLES.get(entity, {}).get("abrev", entity[:3])
        return "{}_{}{}_{}".format(kind, sql_ident.LOGICAL_PREFIX, abbr, suffix)

    def trigger_name(self, entity, suffix="bu"):
        """Nome logico da trigger para o RepoViolation (sql_ident.LOGICAL_PREFIX, README §9.1)."""
        abbr = sql_ident.TABLES.get(entity, {}).get("abrev", entity[:3])
        return "tr_{}{}_{}".format(sql_ident.LOGICAL_PREFIX, abbr, suffix)

    def tuple_to_dict(self, columns, values):
        """Converte tupla de resultado em dict normalizado."""
        d = collections.OrderedDict()
        for col, val in zip(columns, values):
            k = col.lower()
            if isinstance(val, str) and len(val) == 1:
                val = val.strip()
            elif isinstance(val, datetime.datetime):
                val = val.replace(microsecond=0)
            d[k] = val
        return d
