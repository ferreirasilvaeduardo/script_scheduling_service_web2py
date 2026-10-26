# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de agentes (F7.3, agregado AUDITORIA_AGENTES; AGENTS §4).

Leituras do painel de agentes com a mesma semantica do repo_fake/agents.py (README §2.5, §8.7):
- tickets_running e running_without_pid usam a expressao CASE textualmente identica a de ix_tbsss_tck_run
  (AGENTS §4.8, importada do sql_ident) e nunca leem CLOB;
- unattended_queue agrupa os PENDING vencidos pelo interpretador do cadastro (JOIN em tbsss_scripts,
  o mesmo criterio do claim; CR-008, R-15), lendo so ix_tbsss_tck_queue (status, ambiente, script_id e o inicio
  da espera; CR-013); a comparacao com os agentes saudaveis fica em Python, como no FAKE;
- o SQL da fila e do rodando sem PID e o calculo dos pares atendidos vem do repo_oracle/health.py (F9.1b),
  o mesmo do scripts/health.py: a tela e o monitoramento nao divergem;
- binds de DATE como TIPO_DATE (README §7.5).
"""
import datetime

from sss.persistence import db_conn
from sss.core import sql_ident
from sss.persistence.contracts.repo_agents import RepoAgents
from sss.persistence.oracle import health as saude_sql
from sss.persistence.oracle.base import BaseRepoOracle

_COLS_AGT = ("id", "code", "hostname", "daemon_pid", "version", "environments", "platform",
             "script_base_dir", "status", "started_at", "heartbeat_at", "critical_config",
             "created_at", "created_by", "updated_at", "updated_by")
# Mesmas colunas sem CLOB do listar de tickets (contrato RepoTickets.listar).
_COLS_TCK = ("id", "script_id", "environment", "requested_by", "source_ip", "agent_id", "process_id",
             "process_start", "status", "priority", "cancel_requested", "status_reason",
             "parent_ticket_id", "schedule_id", "log_offset_chars", "log_truncated", "return_code",
             "scheduled_at", "started_at", "heartbeat_at", "finished_at",
             "created_at", "created_by", "updated_at", "updated_by")
_COLS_NO_PID = saude_sql.COLS_NO_PID

_RUN = "(" + sql_ident.FBI_TCK_RUN_AGENT_CASE + ")"


def _column_list(cols, alias=""):
    return ", ".join(alias + c for c in cols)


# {agt}, {tck} e {scr} recebem apenas nomes qualificados por sql_ident (validados).
_SQL_LIST = "SELECT " + _column_list(_COLS_AGT) + " FROM {agt} ORDER BY code, id"
_SQL_TICKETS_RUNNING = (
    "SELECT " + _column_list(_COLS_TCK) + " FROM {tck} WHERE " + _RUN + " = :code ORDER BY id"
)
_SQL_QUEUE = saude_sql.SQL_QUEUE
_SQL_RUNNING_NO_PID = saude_sql.SQL_RUNNING_NO_PID


class RepoAgentsOracle(BaseRepoOracle, RepoAgents):
    """Repositorio do painel de agentes com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, secrets=None):
        super(RepoAgentsOracle, self).__init__(cfg=cfg, secrets=secrets)
        self._idents = {
            "agt": self.qualify_table("agents"),
            "tck": self.qualify_table("tickets"),
            "scr": self.qualify_table("scripts"),
        }
        self._sql = {}
        for name, template in globals().items():
            if name.startswith("_SQL_"):
                self._sql[name[5:]] = template.format(**self._idents)

    def _ler(self, sql, binds=None, types=None, conn=None):
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                if types:
                    db_conn.set_input_types(cur, **types)
                if binds is None:
                    cur.execute(sql)
                else:
                    cur.execute(sql, binds)
                return cur.fetchall()
            finally:
                cur.close()

    def list(self, conn=None):
        """Agentes por codigo, id, com plataforma, pasta base e config_criticos."""
        return [self.tuple_to_dict(_COLS_AGT, r) for r in self._ler(self._sql["LIST"], conn=conn)]

    def tickets_running(self, code, conn=None):
        """Tickets RUNNING do agente pela expressao de ix_tbsss_tck_run, por id, sem CLOB."""
        rows = self._ler(self._sql["TICKETS_RUNNING"], {"code": code}, conn=conn)
        return [self.tuple_to_dict(_COLS_TCK, r) for r in rows]

    def unattended_queue(self, now, thresholds, conn=None):
        """Grupos de PENDING vencidos cujo ambiente nenhum agente OK/DELAYED atende (CR-026)."""
        served = saude_sql.served_pairs(self.list(conn=conn), now, thresholds)
        rows = self._ler(self._sql["QUEUE"], {"now": now}, {"now": db_conn.TIPO_DATE}, conn=conn)
        return saude_sql.unattended_queue(rows, served)

    def running_without_pid(self, now, minutes, conn=None):
        """RUNNING sem process_id ha mais de `minutos`, por started_at e id; so as colunas do contrato."""
        limit = now - datetime.timedelta(minutes=minutes)
        rows = self._ler(self._sql["RUNNING_NO_PID"], {"cutoff": limit}, {"cutoff": db_conn.TIPO_DATE},
                           conn=conn)
        return [self.tuple_to_dict(_COLS_NO_PID, r) for r in rows]
