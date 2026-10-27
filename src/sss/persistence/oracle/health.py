# -*- coding: utf-8 -*-
"""Repositorio interno do scripts/health.py (README §13; F9.1b; CR-007 R-18; CR-008 E3, R-15).

Importado so pelo scripts/health.py e, pelo SQL e pelo calculo dos pares atendidos, pelo repo_oracle/agents.py
(a tela de agentes e o monitoramento nao divergem). Sem gluon (excecao do AGENTS §5.5). So leituras, nas
tabelas que a conta do papel monitor le (README §11.1); nenhum LOB e lido.
"""
import datetime

from sss.persistence import db_conn
from sss.core import sql_ident

_RUN = "(" + sql_ident.FBI_TCK_RUN_AGENT_CASE + ")"
_START = sql_ident.FBI_TCK_QUEUE_START

COLS_AGENT = ("code", "status", "heartbeat_at", "environments", "critical_config")
COLS_NO_PID = ("id", "script_id", "environment", "agent_id", "started_at")

# {agt}, {tck}, {scr}, {amb}, {aud} e {ctl} recebem apenas nomes qualificados por sql_ident (validados).
# status = 'PENDING' na coluna lider de ix_tbsss_tck_queue (CR-013): faixa so dos PENDING, lida so no indice
# (ambiente, script_id e o inicio da espera); o inicio <= :agora equivale a scheduled_at <= :agora, porque
# created_at nunca passa de agora. Agrupa por script antes do JOIN com o catalogo. Nenhum CLOB e lido.
SQL_QUEUE = (
    "SELECT g.environment, s.interpreter, SUM(g.n), MIN(g.inicio) FROM ("
    "SELECT environment, script_id, COUNT(*) n, MIN(" + _START + ") inicio FROM {tck} "
    "WHERE status = 'PENDING' AND " + _START + " <= :now GROUP BY environment, script_id) g "
    "JOIN {scr} s ON s.id = g.script_id GROUP BY g.environment, s.interpreter"
)
# ">= CHR(1)" equivale a IS NOT NULL para o agent_id ([A-Za-z0-9._-], todos acima de CHR(1)), mas vira
# faixa de ix_tbsss_tck_run (INDEX RANGE SCAN); com IS NOT NULL o otimizador varria a tabela (EXPLAIN, F7.3).
SQL_RUNNING_NO_PID = (
    "SELECT " + ", ".join(COLS_NO_PID) + " FROM {tck} "
    "WHERE " + _RUN + " >= CHR(1) AND status = 'RUNNING' AND process_id IS NULL "
    "AND started_at < :cutoff ORDER BY started_at, id"
)
_SQL_AGENTS = "SELECT " + ", ".join(COLS_AGENT) + " FROM {agt} ORDER BY code"
_SQL_ENVIRONMENTS = "SELECT name FROM {env} WHERE active = 'Y' ORDER BY name"
# Fila vencida inteira, so no indice ix_tbsss_tck_queue (mesma faixa do SQL_QUEUE).
_SQL_QUEUE_OVERDUE = ("SELECT COUNT(*), MIN(" + _START + ") FROM {tck} WHERE status = 'PENDING' AND "
                     + _START + " <= :now")
_SQL_VERSION = "SELECT schema_version FROM {ctl} WHERE id = 1"


def served_pairs(agents, now, thresholds):
    """Ambientes servidos por agente ATIVO com saude OK ou DELAYED (README §13), com o mesmo arredondamento de
    agents_service.health. CR-026: o agente atende qualquer interpretador; o par virou so o ambiente."""
    served = set()
    for ag in agents:
        hb = ag.get("heartbeat_at")
        if ag.get("status") != "ACTIVE" or hb is None:
            continue
        age = max(0, int((now - hb).total_seconds()))
        if age >= 2 * thresholds.heartbeat_interval_s and age > thresholds.fence_timeout_s:
            continue
        served.update(a.strip() for a in (ag.get("environments") or "").split(",") if a.strip())
    return served


def unattended_queue(queue_rows, served):
    """Grupos (ambiente, interpretador) do SQL_QUEUE cujo ambiente nenhum agente saudavel atende."""
    groups = [{"environment": env, "interpreter": interp, "quantity": int(count),
               "oldest": old.replace(microsecond=0)}
              for env, interp, count, old in queue_rows if env not in served]
    groups.sort(key=lambda g: (g["environment"], g["interpreter"]))
    return groups


class RepoHealth(object):
    """Owner e prefixo vem da configuracao; os nomes passam por sql_ident."""

    def __init__(self, owner, prefix):
        names = {"agt": "agents", "tck": "tickets", "scr": "scripts", "env": "environments", "aud": "audit",
                 "ctl": "control"}
        idents = dict((k, sql_ident.table(owner, prefix, v)) for k, v in names.items())
        self._sql = dict((name, template.format(**idents)) for name, template in (
            ("agents", _SQL_AGENTS), ("environments", _SQL_ENVIRONMENTS), ("queue", SQL_QUEUE),
            ("overdue_queue", _SQL_QUEUE_OVERDUE), ("running_no_pid", SQL_RUNNING_NO_PID),
            ("version", _SQL_VERSION)))

    @classmethod
    def from_config(cls, cfg):
        return cls(cfg.oracle.owner.strip(), cfg.oracle.table_prefix.strip())

    def sql(self, name):
        return self._sql[name]

    def _ler(self, conn, name, dates=None):
        cur = conn.cursor()
        try:
            if dates:
                db_conn.set_input_types(cur, **dict((k, db_conn.TIPO_DATE) for k in dates))
                cur.execute(self._sql[name], dates)
            else:
                cur.execute(self._sql[name])
            return cur.fetchall()
        finally:
            cur.close()

    def agents(self, conn):
        return [dict(zip(COLS_AGENT, r)) for r in self._ler(conn, "agents")]

    def active_environments(self, conn):
        return [r[0] for r in self._ler(conn, "environments")]

    def queue_by_pair(self, conn, now):
        """Linhas (environment, interpreter, quantity, oldest) dos PENDING vencidos."""
        return self._ler(conn, "queue", {"now": now})

    def overdue_queue(self, conn, now):
        """(quantidade, mais antigo) dos PENDING vencidos; o mais antigo e None sem fila."""
        count, old = self._ler(conn, "overdue_queue", {"now": now})[0]
        return int(count or 0), old

    def running_without_pid(self, conn, now, minutes):
        rows = self._ler(conn, "running_no_pid", {"cutoff": now - datetime.timedelta(minutes=minutes)})
        return [dict(zip(COLS_NO_PID, r)) for r in rows]

    def schema_version(self, conn):
        rows = self._ler(conn, "version")
        return int(rows[0][0]) if rows else None
