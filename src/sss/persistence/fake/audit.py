# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de auditoria (README §2.5, §4.4, §10)."""
import copy

from sss.persistence.contracts.repo_audit import RepoAudit
from sss.persistence.fake.store import paginate


class RepoAuditFake(RepoAudit):
    """Implementacao em memoria com semantica Oracle para auditoria."""

    def __init__(self, store):
        self._store = store

    def reserve_id(self):
        """Simula seq.NEXTVAL da trilha."""
        with self._store.lock_audit:
            return self._store.next_id("tbsss_audit")

    def register(self, actor, ip, action, entity, entity_id=None, detail=None, id=None):
        """Registra um evento na trilha de auditoria (com o id reservado, se informado)."""
        return self._store.register_internal_audit(
            actor=actor,
            ip=ip,
            action=action,
            entity=entity,
            entity_id=entity_id,
            detail=detail,
            id=id,
        )

    def _filtrar(self, filters):
        """Registros que atendem aos filtros, ordenados por created_at DESC, id DESC (chamar sob o lock)."""
        filters = filters or {}
        items = list(self._store.audit.values())

        actor_f = filters.get("actor")
        if actor_f:
            items = [a for a in items if actor_f.lower() in a.get("actor", "").lower()]

        action_f = filters.get("action")
        if action_f:
            items = [a for a in items if a.get("action") == action_f]

        ent_f = filters.get("entity")
        if ent_f:
            items = [a for a in items if a.get("entity") == ent_f]

        ent_id_f = filters.get("entity_id")
        if ent_id_f is not None:
            items = [a for a in items if a.get("entity_id") == int(ent_id_f)]

        ip_f = filters.get("source_ip")
        if ip_f:
            items = [a for a in items if ip_f in (a.get("source_ip") or "")]

        dt_ini = filters.get("start_date")
        if dt_ini:
            items = [a for a in items if a.get("created_at") and a["created_at"] >= dt_ini]

        dt_end = filters.get("end_date")
        if dt_end:
            items = [a for a in items if a.get("created_at") and a["created_at"] <= dt_end]

        id_max = filters.get("id_max")
        if id_max is not None:
            items = [a for a in items if a["id"] <= int(id_max)]

        items.sort(key=lambda x: (x.get("created_at") or self._store.now(), x["id"]), reverse=True)
        return items

    def list(self, filters=None, page=1, size=20):
        """Lista registros de auditoria ordenados por created_at DESC, id DESC."""
        with self._store.lock_audit:
            return paginate(self._filtrar(filters), page=page, size=size)

    def count(self, filters=None, limit=50000):
        """Quantidade filtrada, no maximo `limite` (no Oracle: COUNT com ROWNUM)."""
        with self._store.lock_audit:
            return min(len(self._filtrar(filters)), max(0, int(limit)))

    def iterate(self, filters=None, limit=50000):
        """Iterador de copias, no maximo `limite` registros (no Oracle: cursor com arraysize, sem offset)."""
        with self._store.lock_audit:
            items = copy.deepcopy(self._filtrar(filters)[:max(0, int(limit))])
        return iter(items)
