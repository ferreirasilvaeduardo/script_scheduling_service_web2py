# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio da pasta de entrada (CR-020b), com a semantica do Oracle."""
import copy
import datetime

import repo_inputs
from repo_errors import RepoNotFound, RepoViolation
from repo_inputs import NoLiveAgent, RepoInputs


def _actor_agent(agent_id):
    return "SYSTEM:%s" % agent_id


class RepoInputsFake(RepoInputs):
    """Envios, entregas e retratos no FakeDataStore, sob lock_inputs."""

    def __init__(self, store):
        self._store = store

    def _live_agents(self, environment, live_seconds):
        limit = self._store.now() - datetime.timedelta(seconds=int(live_seconds))
        with self._store.lock_agents:
            codes = []
            for a in self._store.agents.values():
                envs = [e.strip() for e in (a.get("environments") or "").split(",")]
                if a.get("status") == "ACTIVE" and environment in envs and a.get("heartbeat_at") \
                        and a["heartbeat_at"] >= limit:
                    codes.append(a["code"])
        return sorted(codes)

    def _check_refs(self, environment, script_id):
        self._store.check_fk(self._store.environment_exists(environment), "fk_tbsss_iup_env")
        self._store.check_fk(int(script_id) in self._store.scripts, "fk_tbsss_iup_scr")

    # ------------------------------------------------------------------ web

    def create_upload(self, data, content, actor, ip, live_seconds):
        actor = self._store.record_actor(actor=actor)
        if data.get("replace_existing") not in ("Y", "N"):
            raise RepoViolation("replace_existing invalido", constraint="ck_tbsss_iup_repl")
        if len(data.get("sha256") or "") != 64:
            raise RepoViolation("sha256 invalido", constraint="ck_tbsss_iup_sha")
        content = bytes(content or b"")
        with self._store.lock_inputs:
            # Mesma ordem do Oracle: os agentes vivos antes das FKs (ambiente inexistente nao tem agente).
            agents = self._live_agents(data["environment"], live_seconds)
            if not agents:
                raise NoLiveAgent("nenhum agente vivo atende o ambiente %s" % data["environment"])
            self._check_refs(data["environment"], data["script_id"])
            uid = self._store.next_id("tbsss_input_upload")
            reg = {"id": uid, "environment": data["environment"], "script_id": int(data["script_id"]),
                   "relative_dir": data.get("relative_dir") or None, "file_name": data["file_name"],
                   "size_bytes": len(content), "sha256": data["sha256"],
                   "replace_existing": data["replace_existing"], "source_ip": ip, "content": content}
            self._store.input_upload[uid] = self._store.stamp_insert(reg, actor)
            for code in agents:
                did = self._store.next_id("tbsss_input_delivery")
                self._store.input_delivery[did] = self._store.stamp_insert(
                    {"id": did, "upload_id": uid, "agent_id": code, "state": "PENDING", "reason": None,
                     "delivered_at": None}, actor)
            detail = u"envio de %s (%d bytes) para %s/script %s; agentes: %s" % (
                data["file_name"], len(content), data["environment"], data["script_id"], ", ".join(agents))
            self._store.register_internal_audit(actor, ip, repo_inputs.ACTION_UPLOAD, repo_inputs.AUDIT_ENTITY,
                                                uid, detail[:1000])
        return {"id": uid, "agents": agents}

    def uploads(self, environment, script_id, page=1, size=20):
        with self._store.lock_inputs:
            rows = [u for u in self._store.input_upload.values()
                    if u["environment"] == environment and u["script_id"] == int(script_id)]
            rows.sort(key=lambda u: (u["created_at"], u["id"]), reverse=True)
            p = max(1, int(page or 1))
            t = int(size or 20)
            t = 20 if t < 1 else t
            items = []
            for u in rows[(p - 1) * t:p * t]:
                item = dict((k, v) for k, v in u.items() if k != "content")
                item["deliveries"] = sorted(
                    ({"agent_id": d["agent_id"], "state": d["state"], "reason": d["reason"],
                      "delivered_at": d["delivered_at"]}
                     for d in self._store.input_delivery.values() if d["upload_id"] == u["id"]),
                    key=lambda d: d["agent_id"])
                items.append(item)
        return {"items": items, "total": len(rows), "page": p, "size": t}

    def listings(self, environment, script_id):
        with self._store.lock_inputs:
            rows = [copy.deepcopy(r) for r in self._store.input_listing.values()
                    if r["environment"] == environment and r["script_id"] == int(script_id)]
        keys = ("agent_id", "listing", "file_count", "truncated", "listed_at", "refresh_requested_at")
        return [dict((k, r.get(k)) for k in keys) for r in sorted(rows, key=lambda r: r["agent_id"])]

    def _listing_row(self, agent_id, environment, script_id):
        for r in self._store.input_listing.values():
            if r["agent_id"] == agent_id and r["environment"] == environment and r["script_id"] == int(script_id):
                return r
        return None

    def request_listing(self, environment, script_id, actor, live_seconds):
        actor = self._store.record_actor(actor=actor)
        with self._store.lock_inputs:
            agents = self._live_agents(environment, live_seconds)
            if agents:
                self._check_refs(environment, script_id)
            now = self._store.now()
            for code in agents:
                row = self._listing_row(code, environment, script_id)
                if row is None:
                    lid = self._store.next_id("tbsss_input_listing")
                    self._store.input_listing[lid] = self._store.stamp_insert(
                        {"id": lid, "agent_id": code, "environment": environment, "script_id": int(script_id),
                         "listing": None, "file_count": None, "truncated": "N", "listed_at": None,
                         "refresh_requested_at": now}, actor)
                else:
                    # Pedido de retrato: rotina tecnica, sem updated_* (README §10, tabela 21).
                    row["refresh_requested_at"] = now
        return len(agents)

    # ------------------------------------------------------------------ agente

    def pending_deliveries(self, agent_id, limit=10):
        with self._store.lock_inputs:
            pend = sorted((d for d in self._store.input_delivery.values()
                           if d["agent_id"] == agent_id and d["state"] == "PENDING"), key=lambda d: d["id"])
            result = []
            for d in pend[:int(limit)]:
                u = self._store.input_upload[d["upload_id"]]
                result.append({"id": d["id"], "upload_id": u["id"], "environment": u["environment"],
                               "script_id": u["script_id"], "relative_dir": u["relative_dir"],
                               "file_name": u["file_name"], "size_bytes": u["size_bytes"], "sha256": u["sha256"],
                               "replace_existing": u["replace_existing"]})
        return result

    def read_content(self, upload_id, offset, size):
        off, size_n = int(offset), int(size)
        if off < 0 or size_n < 1 or size_n > repo_inputs.PART_MAX:
            raise RepoViolation("Parte do envio invalida")
        with self._store.lock_inputs:
            u = self._store.input_upload.get(int(upload_id))
            if u is None or u.get("content") is None:
                raise RepoNotFound("Conteudo do envio %s indisponivel" % upload_id)
            return bytes(u["content"][off:off + size_n])

    def mark_delivery(self, delivery_id, agent_id, state, reason=None):
        if state not in ("DELIVERED", "FAILED") or (state == "FAILED") != (reason is not None) \
                or (reason is not None and reason not in repo_inputs.FAILURE_REASONS):
            raise RepoViolation("Situacao ou motivo da entrega invalido", constraint="ck_tbsss_idl_rsn")
        actor = _actor_agent(agent_id)
        with self._store.lock_inputs:
            d = self._store.input_delivery.get(int(delivery_id))
            if d is None or d["agent_id"] != agent_id or d["state"] != "PENDING":
                return False
            d.update(state=state, reason=reason, delivered_at=self._store.now())
            self._store.stamp_update(d, actor)
            u = self._store.input_upload[d["upload_id"]]
            detail = u"entrega de %s em %s: %s%s" % (u["file_name"], agent_id, state,
                                                     " (%s)" % reason if reason else "")
            self._store.register_internal_audit(actor, None, repo_inputs.ACTION_DELIVERY, repo_inputs.AUDIT_ENTITY,
                                                u["id"], detail[:1000])
        return True

    def listings_due(self, agent_id):
        with self._store.lock_inputs:
            return [{"environment": r["environment"], "script_id": r["script_id"]}
                    for r in sorted(self._store.input_listing.values(), key=lambda r: r["id"])
                    if r["agent_id"] == agent_id and r["refresh_requested_at"] is not None
                    and (r["listed_at"] is None or r["refresh_requested_at"] >= r["listed_at"])]

    def save_listing(self, agent_id, environment, script_id, listing, file_count, truncated):
        if truncated not in ("Y", "N"):
            raise RepoViolation("truncated invalido", constraint="ck_tbsss_ils_trunc")
        actor = _actor_agent(agent_id)
        with self._store.lock_inputs:
            self._check_refs(environment, script_id)
            row = self._listing_row(agent_id, environment, script_id)
            if row is None:
                lid = self._store.next_id("tbsss_input_listing")
                row = self._store.stamp_insert({"id": lid, "agent_id": agent_id, "environment": environment,
                                                "script_id": int(script_id), "refresh_requested_at": None}, actor)
                self._store.input_listing[lid] = row
            # Retrato: rotina tecnica do agente, sem updated_* (README §10, tabela 21).
            row.update(listing=listing, file_count=int(file_count), truncated=truncated,
                       listed_at=self._store.now())
