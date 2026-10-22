# -*- coding: utf-8 -*-
"""Duble em memoria do repo_oracle.scheduler_output (CR-012) para os testes do agente."""
from repo_oracle import scheduler_output


class RepoOutputMemory(object):
    """Contrato do RepoSchedulerOutput em memoria. tickets: {id: {'agent_id': ...}} para a posse."""

    def __init__(self, tickets=None):
        self.tickets = tickets if tickets is not None else {}
        self.rows = {}
        self.failures = []
        self.calls = []

    def _owner(self, tid, agent_id):
        t = self.tickets.get(tid)
        return t is not None and t.get("agent_id") == agent_id

    def _fail(self, name):
        self.calls.append(name)
        if self.failures and self.failures[0][0] == name:
            raise self.failures.pop(0)[1]

    def start(self, conn, tid, agent_id):
        self._fail("start")
        line = self.rows.get(tid)
        if line is not None:
            if line["state"] == "WRITING" and line["agent_id"] == agent_id:
                line.update(content=b"", file_count=None, size_bytes=None)
                return True
            return False
        if not self._owner(tid, agent_id):
            return False
        self.rows[tid] = {"state": "WRITING", "reason": None, "agent_id": agent_id, "content": b"",
                            "file_count": None, "size_bytes": None}
        return True

    def append_chunk(self, conn, tid, agent_id, offset, part):
        self._fail("append_chunk")
        line = self.rows.get(tid)
        if line is None or line["state"] != "WRITING" or line["agent_id"] != agent_id:
            return scheduler_output.OWNERSHIP_LOST
        current = len(line["content"])
        if current == offset:
            line["content"] += part
            return scheduler_output.WRITTEN
        if current == offset + len(part) and line["content"][offset:] == part:
            return scheduler_output.ALREADY_WRITTEN
        raise scheduler_output.OutputOffsetMismatch(tid, offset, len(part))

    def complete(self, conn, tid, agent_id, count_n, size):
        self._fail("complete")
        line = self.rows.get(tid)
        if line is None or line["state"] != "WRITING" or line["agent_id"] != agent_id \
                or len(line["content"]) != size:
            return False
        line.update(state="AVAILABLE", file_count=count_n, size_bytes=size)
        return True

    def register_without_content(self, conn, tid, agent_id, state_value, reason, count_n=None):
        self._fail("register_without_content")
        line = self.rows.get(tid)
        if line is not None:
            if line["state"] != "WRITING" or line["agent_id"] != agent_id:
                return False
        elif not self._owner(tid, agent_id):
            return False
        self.rows[tid] = {"state": state_value, "reason": reason, "agent_id": agent_id, "content": None,
                            "file_count": count_n, "size_bytes": None}
        return True

    def fail_agent_writing(self, conn, agent_id):
        self._fail("fail_agent_writing")
        n = 0
        for line in self.rows.values():
            if line["state"] == "WRITING" and line["agent_id"] == agent_id:
                line.update(state="FAILED", reason="ERROR", content=None)
                n += 1
        return n

    def output_state(self, conn, tid):
        line = self.rows.get(tid)
        return (line["state"], line["agent_id"]) if line else None
