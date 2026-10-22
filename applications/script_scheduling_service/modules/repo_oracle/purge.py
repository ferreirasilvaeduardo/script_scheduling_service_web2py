# -*- coding: utf-8 -*-
"""Repositorio interno do purge (README §11.3; F9.1a; CR-007 R-21, R-22, R-32; CR-008 R-16, R-27).

Importado so pelo scripts/purge.py (excecao do AGENTS §5.5), sem gluon. SQL literal do README §11.3, com owner e
prefixo da configuracao e identificadores por sql_ident. As operacoes de lote NAO fazem COMMIT: o purge confirma
um lote por vez junto com a renovacao da concessao (a excecao de COMMIT em laco do AGENTS §4.9). Ator de toda
gravacao: 'SYSTEM:purge'.
"""
import json

import db_conn
import sql_ident

ACTOR = "SYSTEM:purge"
TERMINAL_STATUSES = ("SUCCESS", "FAILED", "CANCELLED")
_COLS_AUD = ("id", "created_at", "actor", "source_ip", "action", "entity", "entity_id", "detail")


def _read_lob(valor):
    return valor.read() if hasattr(valor, "read") else valor


class RepoPurge(object):
    """Owner e prefixo vem da configuracao (nunca fixos); os nomes passam por sql_ident."""

    def __init__(self, owner, prefixo):
        t = lambda nome: sql_ident.table(owner, prefixo, nome)  # noqa: E731
        self._tck, self._aud, self._ctl, self._scr = t("tickets"), t("audit"), t("control"), t("scripts")
        self._seq_aud = sql_ident.sequence(owner, prefixo, "audit")
        self._prefixo = prefixo

    @classmethod
    def from_config(cls, cfg):
        return cls(cfg.oracle.owner.strip(), cfg.oracle.table_prefix.strip())

    def _executar(self, conn, sql, binds, datas=()):
        cur = conn.cursor()
        try:
            if datas:
                db_conn.set_input_types(cur, **dict((d, db_conn.TIPO_DATE) for d in datas))
            cur.execute(sql, binds)
            return cur.rowcount
        finally:
            cur.close()

    def _contar(self, conn, sql, binds):
        cur = conn.cursor()
        try:
            db_conn.set_input_types(cur, cutoff=db_conn.TIPO_DATE)
            cur.execute(sql, binds)
            return int(cur.fetchone()[0])
        finally:
            cur.close()

    # ------------------------------------------------------------------ concessao (tbsss_control)

    def take_lease(self, conn, dono):
        """Toma ou renova a concessao por 1 hora (README §11.3). False: outro no esta purgando. Sem COMMIT."""
        return self._executar(conn, "UPDATE " + self._ctl + " SET purge_owner = :owner, purge_lease_until = SYSDATE + 1/24"
                              " WHERE id = 1 AND (purge_lease_until IS NULL OR purge_lease_until < SYSDATE"
                              " OR purge_owner = :owner)", {"owner": dono}) == 1

    def release_lease(self, conn, dono):
        """Libera dono e prazo (CR-008, R-27), so se a concessao ainda for deste no. Sem COMMIT."""
        return self._executar(conn, "UPDATE " + self._ctl + " SET purge_owner = NULL, purge_lease_until = NULL"
                              " WHERE id = 1 AND purge_owner = :owner", {"owner": dono}) == 1

    # ------------------------------------------------------------------ tickets

    def count_tickets(self, conn, limite):
        return self._contar(conn, "SELECT COUNT(*) FROM " + self._tck + " WHERE created_at < :cutoff"
                            " AND status IN ('SUCCESS','FAILED','CANCELLED')", {"cutoff": limite})

    def delete_tickets(self, conn, limite, lote):
        """Um lote do DELETE literal do README §11.3 (so terminais; respostas e saidas em cascata). Sem COMMIT."""
        return self._executar(conn, "DELETE FROM " + self._tck + " WHERE created_at < :cutoff"
                              " AND status IN ('SUCCESS','FAILED','CANCELLED') AND ROWNUM <= :batch_size",
                              {"cutoff": limite, "batch_size": int(lote)}, datas=("cutoff",))

    # ------------------------------------------------------------------ auditoria

    def count_audit(self, conn, limite):
        return self._contar(conn, "SELECT COUNT(*) FROM " + self._aud + " WHERE created_at < :cutoff",
                            {"cutoff": limite})

    def delete_audit(self, conn, limite, lote):
        """Um lote do DELETE da auditoria (mesmo padrao, audit_retention_days). Sem COMMIT."""
        return self._executar(conn, "DELETE FROM " + self._aud + " WHERE created_at < :cutoff AND ROWNUM <= :batch_size",
                              {"cutoff": limite, "batch_size": int(lote)}, datas=("cutoff",))

    def read_and_delete_audit(self, conn, limite, lote):
        """Com --export-audit (CR-007, R-22): trava e devolve as linhas do lote e as apaga pelo id, para o
        CSV ter exatamente o que saiu. Devolve a lista de dicts (vazia no fim). Sem COMMIT."""
        cur = conn.cursor()
        try:
            db_conn.set_input_types(cur, cutoff=db_conn.TIPO_DATE)
            cur.execute("SELECT " + ", ".join(_COLS_AUD) + " FROM " + self._aud + " WHERE created_at < :cutoff"
                        " AND ROWNUM <= :batch_size FOR UPDATE WAIT 5", {"cutoff": limite, "batch_size": int(lote)})
            linhas = [dict(zip(_COLS_AUD, r)) for r in cur.fetchall()]
            if linhas:
                cur.executemany("DELETE FROM " + self._aud + " WHERE id = :id", [{"id": l["id"]} for l in linhas])
            return linhas
        finally:
            cur.close()

    def audit(self, conn, tabela, apagadas):
        """PURGE com uma linha por tabela purgada, entidade = a tabela, entidade_id nulo (README §4.4; CR-008 R-16:
        tambem com 0 linhas). Sem COMMIT."""
        self._executar(conn, "INSERT INTO " + self._aud + " (id, actor, source_ip, action, entity, entity_id, detail,"
                       " created_at) VALUES (:id, :actor, NULL, 'PURGE', :entity, NULL, :detail, SYSDATE)",
                       {"id": db_conn.next_id(conn, self._seq_aud), "actor": ACTOR,
                        "entity": self._prefixo_padrao(tabela), "detail": "%d linhas" % int(apagadas)})

    def _prefixo_padrao(self, tabela):
        # A entidade da auditoria usa o nome tbsss_<tabela fisica> (README §4.4), como as demais acoes.
        return "tbsss_%s" % sql_ident.physical(tabela)

    # ------------------------------------------------------------------ logs de tickets RUNNING

    def running_for_logs(self, conn):
        """(ambiente, script_nome, script_id, started_at) dos RUNNING, para manter a pasta de minuto do log deles
        (CR-007, R-32). O nome vem do snapshot (o da epoca do disparo), como no caminho do log (README §8.4)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT t.environment, t.script_id, t.started_at, t.submitted_params FROM " + self._tck + " t"
                        " WHERE t.status = 'RUNNING' AND t.started_at IS NOT NULL")
            saida = []
            for amb, sid, inicio, snap in cur.fetchall():
                try:
                    nome = json.loads(_read_lob(snap) or "{}").get("script_name")
                except ValueError:
                    nome = None
                saida.append((amb, nome, sid, inicio))
            return saida
        finally:
            cur.close()
