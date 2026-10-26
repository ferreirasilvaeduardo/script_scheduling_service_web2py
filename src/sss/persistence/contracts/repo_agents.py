# -*- coding: utf-8 -*-
"""Contrato de persistencia para monitoramento de agentes (tbsss_agents)."""


class RepoAgents(object):
    """Contrato abstrato para consulta de agentes e execucoes em andamento."""

    def list(self):
        """Todos os agentes, por codigo e id, com plataforma, pasta base e config_criticos."""
        raise NotImplementedError

    def tickets_running(self, code):
        """Tickets RUNNING do agente informado, por id, sem CLOB (sem log_output nem submitted_params)."""
        raise NotImplementedError

    def unattended_queue(self, now, thresholds):
        """PENDING com scheduled_at <= agora sem agente OK/DELAYED para o par ambiente/interpretador.

        Retorna grupos ordenados por ambiente e interpretador: ambiente, interpretador,
        quantity e oldest (menor inicio da espera, GREATEST(scheduled_at, created_at); CR-013). O interpretador e o do cadastro
        (tbsss_scripts.interpretador, join), o mesmo criterio do claim (CR-008, R-15); nenhum
        CLOB e lido (nem submitted_params nem log_output).
        """
        raise NotImplementedError

    def running_without_pid(self, now, minutes):
        """RUNNING sem process_id com started_at < agora - minutos, por started_at e id.

        Retorna apenas id, script_id, ambiente, agent_id e started_at, sem LOB.
        """
        raise NotImplementedError
