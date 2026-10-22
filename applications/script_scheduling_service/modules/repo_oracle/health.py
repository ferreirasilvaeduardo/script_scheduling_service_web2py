# -*- coding: utf-8 -*-
"""Repositorio interno do scripts/health.py (README §13; F9.1b; CR-007 R-18; CR-008 E3, R-15).

Importado so pelo scripts/health.py e, pelo SQL e pelo calculo dos pares atendidos, pelo repo_oracle/agents.py
(a tela de agentes e o monitoramento nao divergem). Sem gluon (excecao do AGENTS §5.5). So leituras, nas
tabelas que a conta do papel monitor le (README §11.1); nenhum LOB e lido.
"""
import datetime

import db_conn
import sql_ident

_RUN = "(" + sql_ident.FBI_TCK_RUN_AGENT_CASE + ")"
_START = sql_ident.FBI_TCK_QUEUE_START

COLS_AGENT = ("code", "status", "heartbeat_at", "environments", "interpreters", "critical_config")
COLS_NO_PID = ("id", "script_id", "environment", "agent_id", "started_at")

# {agt}, {tck}, {scr}, {amb}, {aud} e {ctl} recebem apenas nomes qualificados por sql_ident (validados).
# status = 'PENDING' na coluna lider de ix_tck_fila (CR-013): faixa so dos PENDING, lida so no indice
# (ambiente, script_id e o inicio da espera); o inicio <= :agora equivale a scheduled_at <= :agora, porque
# created_at nunca passa de agora. Agrupa por script antes do JOIN com o catalogo. Nenhum CLOB e lido.
SQL_QUEUE = (
    "SELECT g.environment, s.interpreter, SUM(g.n), MIN(g.inicio) FROM ("
    "SELECT environment, script_id, COUNT(*) n, MIN(" + _START + ") inicio FROM {tck} "
    "WHERE status = 'PENDING' AND " + _START + " <= :now GROUP BY environment, script_id) g "
    "JOIN {scr} s ON s.id = g.script_id GROUP BY g.environment, s.interpreter"
)
# ">= CHR(1)" equivale a IS NOT NULL para o agent_id ([A-Za-z0-9._-], todos acima de CHR(1)), mas vira
# faixa de ix_tck_run (INDEX RANGE SCAN); com IS NOT NULL o otimizador varria a tabela (EXPLAIN, F7.3).
SQL_RUNNING_NO_PID = (
    "SELECT " + ", ".join(COLS_NO_PID) + " FROM {tck} "
    "WHERE " + _RUN + " >= CHR(1) AND status = 'RUNNING' AND process_id IS NULL "
    "AND started_at < :cutoff ORDER BY started_at, id"
)
_SQL_AGENTS = "SELECT " + ", ".join(COLS_AGENT) + " FROM {agt} ORDER BY code"
_SQL_ENVIRONMENTS = "SELECT name FROM {env} WHERE active = 'Y' ORDER BY name"
# Fila vencida inteira, so no indice ix_tck_fila (mesma faixa do SQL_QUEUE).
_SQL_QUEUE_OVERDUE = ("SELECT COUNT(*), MIN(" + _START + ") FROM {tck} WHERE status = 'PENDING' AND "
                     + _START + " <= :now")
# ator na coluna de ix_aud_ator: faixa so das linhas do purge.
_SQL_LAST_PURGE = ("SELECT MAX(created_at) FROM {aud} WHERE actor = 'SYSTEM:purge' AND action = 'PURGE'"
                     " AND created_at >= :cutoff")
_SQL_VERSION = "SELECT schema_version FROM {ctl} WHERE id = 1"


def served_pairs(agents, now, thresholds):
    """(ambiente, interpretador) servidos por agente ATIVO com saude OK ou DELAYED (README §13), com o mesmo
    arredondamento de agents_service.health."""
    atendidos = set()
    for ag in agents:
        hb = ag.get("heartbeat_at")
        if ag.get("status") != "ACTIVE" or hb is None:
            continue
        idade = max(0, int((now - hb).total_seconds()))
        if idade >= 2 * thresholds.heartbeat_interval_s and idade > thresholds.fence_timeout_s:
            continue
        atendidos.update((a.strip(), i.strip()) for a in (ag.get("environments") or "").split(",")
                         for i in (ag.get("interpreters") or "").split(",") if a.strip() and i.strip())
    return atendidos


def unattended_queue(queue_rows, served):
    """Grupos (ambiente, interpretador) do SQL_QUEUE que nenhum par atendido cobre, por ambiente e interpretador."""
    grupos = [{"environment": amb, "interpreter": interp, "quantidade": int(qtd),
               "mais_antigo": antigo.replace(microsecond=0)}
              for amb, interp, qtd, antigo in queue_rows if (amb, interp) not in served]
    grupos.sort(key=lambda g: (g["environment"], g["interpreter"]))
    return grupos


class RepoHealth(object):
    """Owner e prefixo vem da configuracao; os nomes passam por sql_ident."""

    def __init__(self, owner, prefix):
        nomes = {"agt": "agents", "tck": "tickets", "scr": "scripts", "env": "environments", "aud": "audit",
                 "ctl": "control"}
        idents = dict((k, sql_ident.table(owner, prefix, v)) for k, v in nomes.items())
        self._sql = dict((nome, modelo.format(**idents)) for nome, modelo in (
            ("agents", _SQL_AGENTS), ("environments", _SQL_ENVIRONMENTS), ("queue", SQL_QUEUE),
            ("overdue_queue", _SQL_QUEUE_OVERDUE), ("running_no_pid", SQL_RUNNING_NO_PID),
            ("purge", _SQL_LAST_PURGE), ("version", _SQL_VERSION)))

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
        """Linhas (ambiente, interpretador, quantidade, mais_antigo) dos PENDING vencidos."""
        return self._ler(conn, "queue", {"now": now})

    def overdue_queue(self, conn, now):
        """(quantidade, mais_antigo) dos PENDING vencidos; mais_antigo None sem fila."""
        qtd, antigo = self._ler(conn, "overdue_queue", {"now": now})[0]
        return int(qtd or 0), antigo

    def running_without_pid(self, conn, now, minutes):
        linhas = self._ler(conn, "running_no_pid", {"cutoff": now - datetime.timedelta(minutes=minutes)})
        return [dict(zip(COLS_NO_PID, r)) for r in linhas]

    def last_purge(self, conn, now, days):
        """created_at do PURGE mais recente desde agora - dias (inclusive 0 linhas, CR-008 R-16), ou None."""
        return self._ler(conn, "purge", {"cutoff": now - datetime.timedelta(days=days)})[0][0]

    def schema_version(self, conn):
        linhas = self._ler(conn, "version")
        return int(linhas[0][0]) if linhas else None
