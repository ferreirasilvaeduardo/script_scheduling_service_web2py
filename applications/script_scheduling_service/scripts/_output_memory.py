# -*- coding: utf-8 -*-
"""Duble em memoria do repo_oracle.scheduler_output (CR-012) para os testes do agente."""
from repo_oracle import scheduler_output


class RepoSaidaMemoria(object):
    """Contrato do RepoSchedulerOutput em memoria. tickets: {id: {'agente_id': ...}} para a posse."""

    def __init__(self, tickets=None):
        self.tickets = tickets if tickets is not None else {}
        self.linhas = {}
        self.falhas = []
        self.chamadas = []

    def _dono(self, tid, agente_id):
        t = self.tickets.get(tid)
        return t is not None and t.get("agent_id") == agente_id

    def _falhar(self, nome):
        self.chamadas.append(nome)
        if self.falhas and self.falhas[0][0] == nome:
            raise self.falhas.pop(0)[1]

    def start(self, conn, tid, agente_id):
        self._falhar("start")
        linha = self.linhas.get(tid)
        if linha is not None:
            if linha["state"] == "WRITING" and linha["agent_id"] == agente_id:
                linha.update(content=b"", file_count=None, size_bytes=None)
                return True
            return False
        if not self._dono(tid, agente_id):
            return False
        self.linhas[tid] = {"state": "WRITING", "reason": None, "agent_id": agente_id, "content": b"",
                            "file_count": None, "size_bytes": None}
        return True

    def append_chunk(self, conn, tid, agente_id, offset, parte):
        self._falhar("append_chunk")
        linha = self.linhas.get(tid)
        if linha is None or linha["state"] != "WRITING" or linha["agent_id"] != agente_id:
            return scheduler_output.OWNERSHIP_LOST
        atual = len(linha["content"])
        if atual == offset:
            linha["content"] += parte
            return scheduler_output.WRITTEN
        if atual == offset + len(parte) and linha["content"][offset:] == parte:
            return scheduler_output.ALREADY_WRITTEN
        raise scheduler_output.OutputOffsetMismatch(tid, offset, len(parte))

    def concluir(self, conn, tid, agente_id, qtd, tamanho):
        self._falhar("concluir")
        linha = self.linhas.get(tid)
        if linha is None or linha["state"] != "WRITING" or linha["agent_id"] != agente_id \
                or len(linha["content"]) != tamanho:
            return False
        linha.update(state="AVAILABLE", file_count=qtd, size_bytes=tamanho)
        return True

    def register_without_content(self, conn, tid, agente_id, situacao, motivo, qtd=None):
        self._falhar("register_without_content")
        linha = self.linhas.get(tid)
        if linha is not None:
            if linha["state"] != "WRITING" or linha["agent_id"] != agente_id:
                return False
        elif not self._dono(tid, agente_id):
            return False
        self.linhas[tid] = {"state": situacao, "reason": motivo, "agent_id": agente_id, "content": None,
                            "file_count": qtd, "size_bytes": None}
        return True

    def fail_agent_writing(self, conn, agente_id):
        self._falhar("fail_agent_writing")
        n = 0
        for linha in self.linhas.values():
            if linha["state"] == "WRITING" and linha["agent_id"] == agente_id:
                linha.update(state="FAILED", reason="ERROR", content=None)
                n += 1
        return n

    def output_state(self, conn, tid):
        linha = self.linhas.get(tid)
        return (linha["state"], linha["agent_id"]) if linha else None
