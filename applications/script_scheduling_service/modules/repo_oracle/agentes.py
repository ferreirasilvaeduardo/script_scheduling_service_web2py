# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de agentes (F7.3, agregado AUDITORIA_AGENTES; AGENTS §4).

Leituras do painel de agentes com a mesma semantica do repo_fake/agentes.py (README §2.5, §8.7):
- tickets_running e rodando_sem_pid usam a expressao CASE textualmente identica a de ix_tck_run
  (AGENTS §4.8, importada do sql_ident) e nunca leem CLOB;
- fila_sem_atendente agrupa os PENDING vencidos pelo interpretador do cadastro (JOIN em tbsss_scripts,
  o mesmo criterio do claim; CR-008, R-15), lendo so ix_tck_fila (status, ambiente, script_id e o inicio
  da espera; CR-013); a comparacao com os agentes saudaveis fica em Python, como no FAKE;
- o SQL da fila e do rodando sem PID e o calculo dos pares atendidos vem do repo_oracle/saude.py (F9.1b),
  o mesmo do scripts/saude.py: a tela e o monitoramento nao divergem;
- binds de DATE como TIPO_DATE (README §7.5).
"""
import datetime

import db_conn
import sql_ident
from repo_agentes import RepoAgentes
from repo_oracle import saude as saude_sql
from repo_oracle.base import BaseRepoOracle

_COLS_AGT = ("id", "code", "hostname", "daemon_pid", "version", "environments", "platform", "interpreters",
             "status", "started_at", "heartbeat_at", "critical_config",
             "created_at", "created_by", "updated_at", "updated_by")
# Mesmas colunas sem CLOB do listar de tickets (contrato RepoTickets.listar).
_COLS_TCK = ("id", "script_id", "environment", "requested_by", "source_ip", "agent_id", "process_id",
             "process_start", "status", "priority", "cancel_requested", "status_reason",
             "parent_ticket_id", "schedule_id", "log_offset_chars", "log_truncated", "return_code",
             "scheduled_at", "started_at", "heartbeat_at", "finished_at",
             "created_at", "created_by", "updated_at", "updated_by")
_COLS_SEM_PID = saude_sql.COLS_SEM_PID

_RUN = "(" + sql_ident.FBI_TCK_RUN_AGENTE_CASE + ")"


def _lista(cols, alias=""):
    return ", ".join(alias + c for c in cols)


# {agt}, {tck} e {scr} recebem apenas nomes qualificados por sql_ident (validados).
_SQL_LISTAR = "SELECT " + _lista(_COLS_AGT) + " FROM {agt} ORDER BY code, id"
_SQL_TICKETS_RUNNING = (
    "SELECT " + _lista(_COLS_TCK) + " FROM {tck} WHERE " + _RUN + " = :code ORDER BY id"
)
_SQL_FILA = saude_sql.SQL_FILA
_SQL_RODANDO_SEM_PID = saude_sql.SQL_RODANDO_SEM_PID


class RepoAgentesOracle(BaseRepoOracle, RepoAgentes):
    """Repositorio do painel de agentes com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, segredos=None):
        super(RepoAgentesOracle, self).__init__(cfg=cfg, segredos=segredos)
        self._idents = {
            "agt": self.qualificar_tabela("agentes"),
            "tck": self.qualificar_tabela("tickets"),
            "scr": self.qualificar_tabela("scripts"),
        }
        self._sql = {}
        for nome, modelo in globals().items():
            if nome.startswith("_SQL_"):
                self._sql[nome[5:]] = modelo.format(**self._idents)

    def _ler(self, sql, binds=None, tipos=None, conn=None):
        with self.contexto_leitura(conn=conn) as c:
            cur = c.cursor()
            try:
                if tipos:
                    db_conn.definir_tipos_entrada(cur, **tipos)
                if binds is None:
                    cur.execute(sql)
                else:
                    cur.execute(sql, binds)
                return cur.fetchall()
            finally:
                cur.close()

    def listar(self, conn=None):
        """Agentes por codigo, id, com plataforma, interpretadores e config_criticos."""
        return [self.tupla_para_dict(_COLS_AGT, r) for r in self._ler(self._sql["LISTAR"], conn=conn)]

    def tickets_running(self, codigo, conn=None):
        """Tickets RUNNING do agente pela expressao de ix_tck_run, por id, sem CLOB."""
        linhas = self._ler(self._sql["TICKETS_RUNNING"], {"code": codigo}, conn=conn)
        return [self.tupla_para_dict(_COLS_TCK, r) for r in linhas]

    def fila_sem_atendente(self, agora, limiares, conn=None):
        """Grupos de PENDING vencidos sem agente OK/ATRASADO para o par ambiente/interpretador."""
        atendidos = saude_sql.pares_atendidos(self.listar(conn=conn), agora, limiares)
        linhas = self._ler(self._sql["FILA"], {"agora": agora}, {"agora": db_conn.TIPO_DATE}, conn=conn)
        return saude_sql.fila_sem_atendente(linhas, atendidos)

    def rodando_sem_pid(self, agora, minutos, conn=None):
        """RUNNING sem process_id ha mais de `minutos`, por started_at e id; so as colunas do contrato."""
        limite = agora - datetime.timedelta(minutes=minutos)
        linhas = self._ler(self._sql["RODANDO_SEM_PID"], {"limite": limite}, {"limite": db_conn.TIPO_DATE},
                           conn=conn)
        return [self.tupla_para_dict(_COLS_SEM_PID, r) for r in linhas]
