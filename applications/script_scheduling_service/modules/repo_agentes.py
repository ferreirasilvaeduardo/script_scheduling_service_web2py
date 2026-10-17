# -*- coding: utf-8 -*-
"""Contrato de persistencia para monitoramento de agentes (tbsss_agentes)."""


class RepoAgentes(object):
    """Contrato abstrato para consulta de agentes e execucoes em andamento."""

    def listar(self):
        """Retorna lista de dicts com todos os agentes registrados."""
        raise NotImplementedError

    def tickets_running(self, codigo):
        """Retorna lista de tickets em status RUNNING pertencentes ao agente informado."""
        raise NotImplementedError

    def fila_sem_atendente(self, agora, limiares):
        """PENDING com scheduled_at <= agora sem agente OK/ATRASADO para o par ambiente/interpretador.

        Retorna grupos ordenados por ambiente e interpretador: ambiente, interpretador,
        quantidade e mais_antigo (menor scheduled_at). O interpretador e o do cadastro
        (tbsss_scripts.interpretador, join), o mesmo criterio do claim (CR-008, R-15); nenhum
        CLOB e lido (nem parametros_enviados nem log_output).
        """
        raise NotImplementedError

    def rodando_sem_pid(self, agora, minutos):
        """RUNNING sem process_id com started_at < agora - minutos, por started_at e id.

        Retorna apenas id, script_id, ambiente, agente_id e started_at, sem LOB.
        """
        raise NotImplementedError
