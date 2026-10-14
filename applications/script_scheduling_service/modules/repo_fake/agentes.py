# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de agentes (README §2.5, §8.7, §10)."""
import copy

from repo_agentes import RepoAgentes


class RepoAgentesFake(RepoAgentes):
    """Implementacao em memoria com semantica Oracle para agentes."""

    def __init__(self, store):
        self._store = store

    def listar(self):
        """Retorna lista de todos os agentes ordenados por codigo ASC, id ASC."""
        with self._store.lock_agentes:
            lista = list(self._store.agentes.values())
            lista.sort(key=lambda x: (x.get("codigo", ""), x["id"]))
            return copy.deepcopy(lista)

    def tickets_running(self, codigo):
        """Retorna tickets em status RUNNING pertencentes ao agente informado."""
        with self._store.lock_tickets:
            running = [
                t for t in self._store.tickets.values()
                if t.get("status") == "RUNNING" and t.get("agente_id") == codigo
            ]
            running.sort(key=lambda x: x["id"])
            return copy.deepcopy(running)
