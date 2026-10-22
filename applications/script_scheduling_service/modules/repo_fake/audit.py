# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de auditoria (README §2.5, §4.4, §10)."""
import copy

from repo_audit import RepoAudit
from repo_fake.store import paginate


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
        lista = list(self._store.audit.values())

        ator_f = filters.get("actor")
        if ator_f:
            lista = [a for a in lista if ator_f.lower() in a.get("actor", "").lower()]

        acao_f = filters.get("action")
        if acao_f:
            lista = [a for a in lista if a.get("action") == acao_f]

        ent_f = filters.get("entity")
        if ent_f:
            lista = [a for a in lista if a.get("entity") == ent_f]

        ent_id_f = filters.get("entity_id")
        if ent_id_f is not None:
            lista = [a for a in lista if a.get("entity_id") == int(ent_id_f)]

        ip_f = filters.get("source_ip")
        if ip_f:
            lista = [a for a in lista if ip_f in (a.get("source_ip") or "")]

        dt_ini = filters.get("start_date")
        if dt_ini:
            lista = [a for a in lista if a.get("created_at") and a["created_at"] >= dt_ini]

        dt_fim = filters.get("end_date")
        if dt_fim:
            lista = [a for a in lista if a.get("created_at") and a["created_at"] <= dt_fim]

        id_max = filters.get("id_max")
        if id_max is not None:
            lista = [a for a in lista if a["id"] <= int(id_max)]

        lista.sort(key=lambda x: (x.get("created_at") or self._store.now(), x["id"]), reverse=True)
        return lista

    def list(self, filters=None, page=1, size=20):
        """Lista registros de auditoria ordenados por created_at DESC, id DESC."""
        with self._store.lock_audit:
            return paginate(self._filtrar(filters), page=page, size=size)

    def iterate(self, filters=None, limit=50000):
        """Iterador de copias, no maximo `limite` registros (no Oracle: cursor com arraysize, sem offset)."""
        with self._store.lock_audit:
            lista = copy.deepcopy(self._filtrar(filters)[:max(0, int(limit))])
        return iter(lista)
