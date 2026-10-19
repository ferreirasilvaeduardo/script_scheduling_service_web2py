# -*- coding: utf-8 -*-
"""Base e utilitarios compartilhados para os repositorios Oracle 11gR2 (F7.3).

Garante que nenhum modulo de repo_oracle importe oracledb ou cx_Oracle diretamente:
todo acesso ao driver passa exclusivamente por db_conn.py (CR-002, AGENTS §2.2).
"""
import collections
import contextlib
import datetime
import re

from gluon import current

import db_conn
import repo_errors
import sql_ident
import sss_config

_RE_CONSTRAINT = re.compile(r"\((?:[A-Za-z0-9_]+\.)?([A-Za-z0-9_]+)\)")


def validar_ator_registro(auditoria=None, ator=None):
    """Valida e extrai o ator obrigatorio de registro (CR-006, README §10, AGENTS §4.15).

    Lanca RepoViolacao antes de qualquer SQL se o ator for nulo, vazio ou exceder 40 chars.
    """
    at = None
    if isinstance(auditoria, dict):
        at = auditoria.get("ator")
    if not at and ator:
        at = ator

    if not at or not isinstance(at, str) or not at.strip() or len(at) > 40:
        raise repo_errors.RepoViolacao("Ator obrigatorio e deve ter ate 40 caracteres")
    return at.strip()


def traduzir_erro_oracle(exc, constraint_padrao=None, prefixo=None):
    """Traduz excecoes Oracle capturadas para a hierarquia de repo_errors."""
    if isinstance(exc, repo_errors.RepoErro):
        return exc

    pfx, num = db_conn.classificar_erro(exc)
    msg = str(exc)

    m = _RE_CONSTRAINT.search(msg)
    constraint = m.group(1).lower() if m else (constraint_padrao.lower() if constraint_padrao else None)

    pfx_real = prefixo or "tbsss_"
    if pfx == "ORA":
        if num in (1, 2290, 2291, 2292, 1400, 12899, 1438, 20001):
            if num == 1438 and not constraint:
                constraint = "ck_{}usr_tent".format(pfx_real)
            elif num == 20001 and not constraint:
                constraint = "tr_{}usr_bu".format(pfx_real)
            return repo_errors.RepoViolacao(msg, constraint=constraint)
        if num in (54, 30006, 60, 3156):
            return repo_errors.RepoConflito(msg)
    elif pfx in ("DPY", "DPI"):
        if db_conn.eh_tempo_esgotado(exc):
            return repo_errors.RepoConflito(msg)

    if db_conn.eh_erro_rede(exc):
        return repo_errors.RepoIndisponivel(msg)

    return repo_errors.RepoErro(msg)


def gravar_auditoria(conn, sql_tbl_aud, sql_seq_aud, auditoria, entidade, entidade_id):
    """Grava linha(s) em tbsss_auditoria na mesma transacao (README §4.4, §10)."""
    if not auditoria:
        return
    itens = [auditoria] if isinstance(auditoria, dict) else auditoria
    cur = conn.cursor()
    try:
        for item in itens:
            if not isinstance(item, dict):
                continue
            aid = db_conn.proximo_id(conn, sql_seq_aud)
            cur.execute(
                "INSERT INTO " + sql_tbl_aud + " "
                "(id, ator, ip_origem, acao, entidade, entidade_id, detalhe, created_at) "
                "VALUES (:id, :ator, :ip_origem, :acao, :entidade, :entidade_id, :detalhe, SYSDATE)",
                {
                    "id": aid,
                    "ator": (item.get("ator") or "SYSTEM")[:40],
                    "ip_origem": (item.get("ip") or item.get("ip_origem") or "")[:45],
                    "acao": item["acao"][:30],
                    "entidade": entidade[:30],
                    "entidade_id": entidade_id,
                    "detalhe": (item.get("detalhe") or "")[:1000] if item.get("detalhe") else None,
                }
            )
    finally:
        cur.close()


class BaseRepoOracle(object):
    """Classe base para repositorios Oracle 11gR2."""

    def __init__(self, cfg=None, segredos=None):
        self._cfg = cfg
        self._segredos = segredos
        self._owner = None
        self._prefixo = None
        self._resolver_config()

    def _resolver_config(self):
        if self._cfg is None:
            self._cfg = getattr(current, "sss_cfg", None)
        if self._cfg is None:
            try:
                self._cfg = sss_config.obter_config()
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
        if self._segredos is None and self._cfg is not None:
            try:
                self._segredos = sss_config.carregar_segredos(
                    self._cfg.secrets.secrets_file, cfg=self._cfg, papel="web"
                )
            except Exception:
                pass
        return db_conn.conectar(self._cfg, self._segredos, papel="web")

    @contextlib.contextmanager
    def transacao_escrita(self, conn=None):
        """Gerencia contexto de transacao com COMMIT/ROLLBACK para operacoes de escrita."""
        fechar = False
        if conn is None:
            conn = self._obter_conexao()
            fechar = True
        try:
            with db_conn.transacao(conn):
                yield conn
        except Exception as exc:
            raise traduzir_erro_oracle(exc, prefixo=self._prefixo)
        finally:
            if fechar:
                try:
                    conn.close()
                except Exception:
                    pass

    @contextlib.contextmanager
    def contexto_leitura(self, conn=None):
        """Gerencia contexto de conexao para operacoes de leitura."""
        fechar = False
        if conn is None:
            conn = self._obter_conexao()
            fechar = True
        try:
            yield conn
        except Exception as exc:
            raise traduzir_erro_oracle(exc, prefixo=self._prefixo)
        finally:
            if fechar:
                try:
                    conn.close()
                except Exception:
                    pass

    def qualificar_tabela(self, entidade):
        return sql_ident.qualificar(self._owner, self._prefixo + entidade, prefixo=self._prefixo)

    def qualificar_sequence(self, entidade):
        return sql_ident.qualificar(self._owner, "sq_" + self._prefixo + entidade, prefixo=self._prefixo)

    def nome_constraint(self, tipo, entidade, sufixo):
        """Retorna o nome da constraint/indice para o prefixo configurado (README §9.1)."""
        abrev = sql_ident.TABELAS.get(entidade, {}).get("abrev", entidade[:3])
        return "{}_{}{}_{}".format(tipo, self._prefixo, abrev, sufixo)

    def nome_trigger(self, entidade, sufixo="bu"):
        """Retorna o nome da trigger para o prefixo configurado (README §9.1)."""
        abrev = sql_ident.TABELAS.get(entidade, {}).get("abrev", entidade[:3])
        return "tr_{}{}_{}".format(self._prefixo, abrev, sufixo)

    def tupla_para_dict(self, colunas, valores):
        """Converte tupla de resultado em dict normalizado."""
        d = collections.OrderedDict()
        for col, val in zip(colunas, valores):
            k = col.lower()
            if isinstance(val, str) and len(val) == 1:
                val = val.strip()
            elif isinstance(val, datetime.datetime):
                val = val.replace(microsecond=0)
            d[k] = val
        return d
