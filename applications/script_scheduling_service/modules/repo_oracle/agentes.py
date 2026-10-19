# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de agentes (F7.3, agregado AUDITORIA_AGENTES; AGENTS §4).

Leituras do painel de agentes com a mesma semantica do repo_fake/agentes.py (README §2.5, §8.7):
- tickets_running e rodando_sem_pid usam a expressao CASE textualmente identica a de ix_tck_run
  (AGENTS §4.8, importada do sql_ident) e nunca leem CLOB;
- fila_sem_atendente agrupa os PENDING vencidos pelo interpretador do cadastro (JOIN em tbsss_scripts,
  o mesmo criterio do claim; CR-008, R-15), pelas expressoes de ix_tck_fila; a comparacao com os
  agentes saudaveis fica em Python, como no FAKE;
- binds de DATE como TIPO_DATE (README §7.5).
"""
import datetime

import db_conn
import sql_ident
from repo_agentes import RepoAgentes
from repo_oracle.base import BaseRepoOracle

_COLS_AGT = ("id", "codigo", "hostname", "pid_daemon", "versao", "ambientes", "plataforma", "interpretadores",
             "status", "iniciado_em", "heartbeat_at", "config_criticos",
             "created_at", "created_by", "updated_at", "updated_by")
# Mesmas colunas sem CLOB do listar de tickets (contrato RepoTickets.listar).
_COLS_TCK = ("id", "script_id", "ambiente", "solicitante", "ip_origem", "agente_id", "process_id",
             "process_start", "status", "prioridade", "cancel_requested", "status_motivo",
             "parent_ticket_id", "agendamento_id", "log_offset_chars", "log_truncado", "return_code",
             "arquivo_sha256", "scheduled_at", "started_at", "heartbeat_at", "finished_at",
             "created_at", "created_by", "updated_at", "updated_by")
_COLS_SEM_PID = ("id", "script_id", "ambiente", "agente_id", "started_at")

_RUN = "(" + sql_ident.FBI_TCK_RUN_AGENTE_CASE + ")"
_FILA_PRIO = "(" + sql_ident.FBI_TCK_FILA_PRIO_CASE + ")"
_FILA_SCHED = "(" + sql_ident.FBI_TCK_FILA_SCHED_CASE + ")"


def _lista(cols, alias=""):
    return ", ".join(alias + c for c in cols)


# {agt}, {tck} e {scr} recebem apenas nomes qualificados por sql_ident (validados).
_SQL_LISTAR = "SELECT " + _lista(_COLS_AGT) + " FROM {agt} ORDER BY codigo, id"
_SQL_TICKETS_RUNNING = (
    "SELECT " + _lista(_COLS_TCK) + " FROM {tck} WHERE " + _RUN + " = :codigo ORDER BY id"
)
# A faixa de prioridade (1 a 4, ck_tck_prio) na coluna lider deixa o acesso por ix_tck_fila em RANGE SCAN;
# a expressao de scheduled_at limita aos PENDING vencidos. Nenhum CLOB e lido.
_SQL_FILA = (
    "SELECT t.ambiente, s.interpretador, COUNT(*), MIN(t.scheduled_at) "
    "FROM {tck} t JOIN {scr} s ON s.id = t.script_id "
    "WHERE " + _FILA_PRIO + " BETWEEN 1 AND 4 AND " + _FILA_SCHED + " <= :agora "
    "GROUP BY t.ambiente, s.interpretador"
)
# ">= CHR(1)" equivale a IS NOT NULL para o agent_id ([A-Za-z0-9._-], todos acima de CHR(1)), mas vira
# faixa de ix_tck_run (INDEX RANGE SCAN); com IS NOT NULL o otimizador varria a tabela (EXPLAIN, F7.3).
_SQL_RODANDO_SEM_PID = (
    "SELECT " + _lista(_COLS_SEM_PID) + " FROM {tck} "
    "WHERE " + _RUN + " >= CHR(1) AND status = 'RUNNING' AND process_id IS NULL "
    "AND started_at < :limite ORDER BY started_at, id"
)


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
        linhas = self._ler(self._sql["TICKETS_RUNNING"], {"codigo": codigo}, conn=conn)
        return [self.tupla_para_dict(_COLS_TCK, r) for r in linhas]

    def fila_sem_atendente(self, agora, limiares, conn=None):
        """Grupos de PENDING vencidos sem agente OK/ATRASADO para o par ambiente/interpretador."""
        atendidos = set()
        for ag in self.listar(conn=conn):
            hb = ag.get("heartbeat_at")
            if ag.get("status") != "ATIVO" or hb is None:
                continue
            idade = max(0, int((agora - hb).total_seconds()))  # mesmo arredondamento de agentes_service.saude
            if idade >= 2 * limiares.heartbeat_interval_s and idade > limiares.fence_timeout_s:
                continue
            atendidos.update((a.strip(), i.strip()) for a in (ag.get("ambientes") or "").split(",")
                             for i in (ag.get("interpretadores") or "").split(",") if a.strip() and i.strip())
        grupos = []
        for ambiente, interpretador, quantidade, mais_antigo in self._ler(
                self._sql["FILA"], {"agora": agora}, {"agora": db_conn.TIPO_DATE}, conn=conn):
            if (ambiente, interpretador) in atendidos:
                continue
            grupos.append({"ambiente": ambiente, "interpretador": interpretador,
                           "quantidade": int(quantidade), "mais_antigo": mais_antigo.replace(microsecond=0)})
        grupos.sort(key=lambda g: (g["ambiente"], g["interpretador"]))
        return grupos

    def rodando_sem_pid(self, agora, minutos, conn=None):
        """RUNNING sem process_id ha mais de `minutos`, por started_at e id; so as colunas do contrato."""
        limite = agora - datetime.timedelta(minutes=minutos)
        linhas = self._ler(self._sql["RODANDO_SEM_PID"], {"limite": limite}, {"limite": db_conn.TIPO_DATE},
                           conn=conn)
        return [self.tupla_para_dict(_COLS_SEM_PID, r) for r in linhas]
