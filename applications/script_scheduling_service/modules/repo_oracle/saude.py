# -*- coding: utf-8 -*-
"""Repositorio interno do scripts/saude.py (README §13; F9.1b; CR-007 R-18; CR-008 E3, R-15).

Importado so pelo scripts/saude.py e, pelo SQL e pelo calculo dos pares atendidos, pelo repo_oracle/agentes.py
(a tela de agentes e o monitoramento nao divergem). Sem gluon (excecao do AGENTS §5.5). So leituras, nas
tabelas que a conta do papel monitor le (README §11.1); nenhum LOB e lido.
"""
import datetime

import db_conn
import sql_ident

_RUN = "(" + sql_ident.FBI_TCK_RUN_AGENTE_CASE + ")"
_INICIO = sql_ident.FBI_TCK_FILA_INICIO

COLS_AGENTE = ("code", "status", "heartbeat_at", "environments", "interpreters", "critical_config")
COLS_SEM_PID = ("id", "script_id", "environment", "agent_id", "started_at")

# {agt}, {tck}, {scr}, {amb}, {aud} e {ctl} recebem apenas nomes qualificados por sql_ident (validados).
# status = 'PENDING' na coluna lider de ix_tck_fila (CR-013): faixa so dos PENDING, lida so no indice
# (ambiente, script_id e o inicio da espera); o inicio <= :agora equivale a scheduled_at <= :agora, porque
# created_at nunca passa de agora. Agrupa por script antes do JOIN com o catalogo. Nenhum CLOB e lido.
SQL_FILA = (
    "SELECT g.environment, s.interpreter, SUM(g.n), MIN(g.inicio) FROM ("
    "SELECT environment, script_id, COUNT(*) n, MIN(" + _INICIO + ") inicio FROM {tck} "
    "WHERE status = 'PENDING' AND " + _INICIO + " <= :agora GROUP BY environment, script_id) g "
    "JOIN {scr} s ON s.id = g.script_id GROUP BY g.environment, s.interpreter"
)
# ">= CHR(1)" equivale a IS NOT NULL para o agent_id ([A-Za-z0-9._-], todos acima de CHR(1)), mas vira
# faixa de ix_tck_run (INDEX RANGE SCAN); com IS NOT NULL o otimizador varria a tabela (EXPLAIN, F7.3).
SQL_RODANDO_SEM_PID = (
    "SELECT " + ", ".join(COLS_SEM_PID) + " FROM {tck} "
    "WHERE " + _RUN + " >= CHR(1) AND status = 'RUNNING' AND process_id IS NULL "
    "AND started_at < :limite ORDER BY started_at, id"
)
_SQL_AGENTES = "SELECT " + ", ".join(COLS_AGENTE) + " FROM {agt} ORDER BY code"
_SQL_AMBIENTES = "SELECT name FROM {amb} WHERE active = 'Y' ORDER BY name"
# Fila vencida inteira, so no indice ix_tck_fila (mesma faixa do SQL_FILA).
_SQL_FILA_VENCIDA = ("SELECT COUNT(*), MIN(" + _INICIO + ") FROM {tck} WHERE status = 'PENDING' AND "
                     + _INICIO + " <= :agora")
# ator na coluna de ix_aud_ator: faixa so das linhas do purge.
_SQL_ULTIMO_PURGE = ("SELECT MAX(created_at) FROM {aud} WHERE actor = 'SYSTEM:purge' AND action = 'PURGE'"
                     " AND created_at >= :limite")
_SQL_VERSAO = "SELECT schema_version FROM {ctl} WHERE id = 1"


def pares_atendidos(agentes, agora, limiares):
    """(ambiente, interpretador) servidos por agente ATIVO com saude OK ou ATRASADO (README §13), com o mesmo
    arredondamento de agentes_service.saude."""
    atendidos = set()
    for ag in agentes:
        hb = ag.get("heartbeat_at")
        if ag.get("status") != "ACTIVE" or hb is None:
            continue
        idade = max(0, int((agora - hb).total_seconds()))
        if idade >= 2 * limiares.heartbeat_interval_s and idade > limiares.fence_timeout_s:
            continue
        atendidos.update((a.strip(), i.strip()) for a in (ag.get("environments") or "").split(",")
                         for i in (ag.get("interpreters") or "").split(",") if a.strip() and i.strip())
    return atendidos


def fila_sem_atendente(linhas_fila, atendidos):
    """Grupos (ambiente, interpretador) do SQL_FILA que nenhum par atendido cobre, por ambiente e interpretador."""
    grupos = [{"environment": amb, "interpreter": interp, "quantidade": int(qtd),
               "mais_antigo": antigo.replace(microsecond=0)}
              for amb, interp, qtd, antigo in linhas_fila if (amb, interp) not in atendidos]
    grupos.sort(key=lambda g: (g["environment"], g["interpreter"]))
    return grupos


class RepoSaude(object):
    """Owner e prefixo vem da configuracao; os nomes passam por sql_ident."""

    def __init__(self, owner, prefixo):
        nomes = {"agt": "agentes", "tck": "tickets", "scr": "scripts", "amb": "ambientes", "aud": "auditoria",
                 "ctl": "controle"}
        idents = dict((k, sql_ident.tabela(owner, prefixo, v)) for k, v in nomes.items())
        self._sql = dict((nome, modelo.format(**idents)) for nome, modelo in (
            ("agentes", _SQL_AGENTES), ("ambientes", _SQL_AMBIENTES), ("fila", SQL_FILA),
            ("fila_vencida", _SQL_FILA_VENCIDA), ("sem_pid", SQL_RODANDO_SEM_PID),
            ("purge", _SQL_ULTIMO_PURGE), ("version", _SQL_VERSAO)))

    @classmethod
    def da_config(cls, cfg):
        return cls(cfg.oracle.owner.strip(), cfg.oracle.table_prefix.strip())

    def sql(self, nome):
        return self._sql[nome]

    def _ler(self, conn, nome, datas=None):
        cur = conn.cursor()
        try:
            if datas:
                db_conn.definir_tipos_entrada(cur, **dict((k, db_conn.TIPO_DATE) for k in datas))
                cur.execute(self._sql[nome], datas)
            else:
                cur.execute(self._sql[nome])
            return cur.fetchall()
        finally:
            cur.close()

    def agentes(self, conn):
        return [dict(zip(COLS_AGENTE, r)) for r in self._ler(conn, "agentes")]

    def ambientes_ativos(self, conn):
        return [r[0] for r in self._ler(conn, "ambientes")]

    def fila_por_par(self, conn, agora):
        """Linhas (ambiente, interpretador, quantidade, mais_antigo) dos PENDING vencidos."""
        return self._ler(conn, "fila", {"agora": agora})

    def fila_vencida(self, conn, agora):
        """(quantidade, mais_antigo) dos PENDING vencidos; mais_antigo None sem fila."""
        qtd, antigo = self._ler(conn, "fila_vencida", {"agora": agora})[0]
        return int(qtd or 0), antigo

    def rodando_sem_pid(self, conn, agora, minutos):
        linhas = self._ler(conn, "sem_pid", {"limite": agora - datetime.timedelta(minutes=minutos)})
        return [dict(zip(COLS_SEM_PID, r)) for r in linhas]

    def ultimo_purge(self, conn, agora, dias):
        """created_at do PURGE mais recente desde agora - dias (inclusive 0 linhas, CR-008 R-16), ou None."""
        return self._ler(conn, "purge", {"limite": agora - datetime.timedelta(days=dias)})[0][0]

    def versao_esquema(self, conn):
        linhas = self._ler(conn, "version")
        return int(linhas[0][0]) if linhas else None
