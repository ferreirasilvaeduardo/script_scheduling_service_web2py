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
