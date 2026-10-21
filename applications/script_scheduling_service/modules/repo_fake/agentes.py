# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de agentes (README §2.5, §8.7, §10)."""
import copy
import datetime

from repo_agentes import RepoAgentes


class RepoAgentesFake(RepoAgentes):
    """Implementacao em memoria com semantica Oracle para agentes."""

    def __init__(self, store):
        self._store = store

    def listar(self):
        """Retorna lista de todos os agentes ordenados por codigo ASC, id ASC."""
        with self._store.lock_agentes:
            agora = self._store.agora()
            for ag in self._store.agentes.values():
                if ag.get("code") in self._store.agentes_hb_sim and ag.get("status") == "ACTIVE":
                    ag["heartbeat_at"] = agora
            lista = list(self._store.agentes.values())
            lista.sort(key=lambda x: (x.get("code", ""), x["id"]))
            return copy.deepcopy(lista)

    def tickets_running(self, codigo):
        """Retorna tickets em status RUNNING pertencentes ao agente informado."""
        with self._store.lock_tickets:
            running = [
                t for t in self._store.tickets.values()
                if t.get("status") == "RUNNING" and t.get("agent_id") == codigo
            ]
            running.sort(key=lambda x: x["id"])
            # Sem CLOB, como no Oracle (contrato RepoAgentes.tickets_running).
            return [dict((k, copy.deepcopy(v)) for k, v in t.items()
                         if k not in ("submitted_params", "log_output")) for t in running]

    def fila_sem_atendente(self, agora, limiares):
        """Agrupa a fila vencida sem agente saudavel para o ambiente e o interpretador."""
        atendidos = set()
        for ag in self.listar():
            hb = ag.get("heartbeat_at")
            if ag.get("status") != "ACTIVE" or hb is None:
                continue
            idade = max(0, int((agora - hb).total_seconds()))  # mesmo arredondamento de agentes_service.saude
            if idade >= 2 * limiares.heartbeat_interval_s and idade > limiares.fence_timeout_s:
                continue
            atendidos.update((a.strip(), i.strip()) for a in (ag.get("environments") or "").split(",")
                             for i in (ag.get("interpreters") or "").split(",") if a.strip() and i.strip())
        grupos = {}
        interpretadores = dict((sid, s.get("interpreter")) for sid, s in self._store.scripts.items())
        with self._store.lock_tickets:
            for t in self._store.tickets.values():
                if t["status"] != "PENDING" or t["scheduled_at"] > agora:
                    continue
                # Inicio da espera (CR-013): o mesmo de ix_tck_fila e do envelhecimento da fila.
                inicio = max(t["scheduled_at"], t.get("created_at") or t["scheduled_at"])
                # Mesmo criterio do claim: interpretador do cadastro, sem ler o snapshot (CR-008, R-15).
                chave = (t["environment"], interpretadores.get(t["script_id"]))
                if chave in atendidos:
                    continue
                grupo = grupos.setdefault(chave, {"environment": chave[0], "interpreter": chave[1],
                                                  "quantidade": 0, "mais_antigo": inicio})
                grupo["quantidade"] += 1
                grupo["mais_antigo"] = min(grupo["mais_antigo"], inicio)
        return [grupos[chave] for chave in sorted(grupos)]

    def rodando_sem_pid(self, agora, minutos):
        """Tickets reservados ha mais de minutos, ainda sem PID, sem ler o log."""
        limite = agora - datetime.timedelta(minutes=minutos)
        campos = ("id", "script_id", "environment", "agent_id", "started_at")
        with self._store.lock_tickets:
            itens = [dict((c, t.get(c)) for c in campos) for t in self._store.tickets.values()
                     if t["status"] == "RUNNING" and t.get("process_id") is None
                     and t.get("started_at") is not None and t["started_at"] < limite]
        return sorted(itens, key=lambda t: (t["started_at"], t["id"]))
