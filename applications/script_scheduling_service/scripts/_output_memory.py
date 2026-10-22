# -*- coding: utf-8 -*-
"""Duble em memoria do repo_oracle.scheduler_output (CR-012) para os testes do agente."""
from repo_oracle import scheduler_output


class RepoOutputMemory(object):
    """Contrato do RepoSchedulerOutput em memoria. tickets: {id: {'agente_id': ...}} para a posse."""

    def __init__(self, tickets=None):
        self.tickets = tickets if tickets is not None else {}
        self.rows = {}
        self.falhas = []
        self.calls = []

    def _owner(self, tid, agente_id):
        t = self.tickets.get(tid)
        return t is not None and t.get("agent_id") == agente_id

    def _fail(self, nome):
        self.calls.append(nome)
        if self.falhas and self.falhas[0][0] == nome:
            raise self.falhas.pop(0)[1]

    def start(self, conn, tid, agente_id):
        self._fail("start")
        linha = self.rows.get(tid)
        if linha is not None:
            if linha["state"] == "WRITING" and linha["agent_id"] == agente_id:
                linha.update(content=b"", file_count=None, size_bytes=None)
                return True
            return False
        if not self._owner(tid, agente_id):
            return False
        self.rows[tid] = {"state": "WRITING", "reason": None, "agent_id": agente_id, "content": b"",
                            "file_count": None, "size_bytes": None}
        return True

    def append_chunk(self, conn, tid, agente_id, offset, parte):
        self._fail("append_chunk")
        linha = self.rows.get(tid)
        if linha is None or linha["state"] != "WRITING" or linha["agent_id"] != agente_id:
            return scheduler_output.OWNERSHIP_LOST
        atual = len(linha["content"])
        if atual == offset:
            linha["content"] += parte
            return scheduler_output.WRITTEN
        if atual == offset + len(parte) and linha["content"][offset:] == parte:
            return scheduler_output.ALREADY_WRITTEN
        raise scheduler_output.OutputOffsetMismatch(tid, offset, len(parte))

    def complete(self, conn, tid, agente_id, qtd, tamanho):
        self._fail("complete")
        linha = self.rows.get(tid)
        if linha is None or linha["state"] != "WRITING" or linha["agent_id"] != agente_id \
                or len(linha["content"]) != tamanho:
            return False
        linha.update(state="AVAILABLE", file_count=qtd, size_bytes=tamanho)
        return True

    def register_without_content(self, conn, tid, agente_id, situacao, motivo, qtd=None):
        self._fail("register_without_content")
        linha = self.rows.get(tid)
        if linha is not None:
            if linha["state"] != "WRITING" or linha["agent_id"] != agente_id:
                return False
        elif not self._owner(tid, agente_id):
            return False
        self.rows[tid] = {"state": situacao, "reason": motivo, "agent_id": agente_id, "content": None,
                            "file_count": qtd, "size_bytes": None}
        return True

    def fail_agent_writing(self, conn, agente_id):
        self._fail("fail_agent_writing")
        n = 0
        for linha in self.rows.values():
            if linha["state"] == "WRITING" and linha["agent_id"] == agente_id:
                linha.update(state="FAILED", reason="ERROR", content=None)
                n += 1
        return n

    def output_state(self, conn, tid):
        linha = self.rows.get(tid)
        return (linha["state"], linha["agent_id"]) if linha else None
