# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de auditoria (README §2.5, §4.4, §10)."""
import copy

from repo_auditoria import RepoAuditoria
from repo_fake.store import paginar


class RepoAuditoriaFake(RepoAuditoria):
    """Implementacao em memoria com semantica Oracle para auditoria."""

    def __init__(self, store):
        self._store = store

    def reservar_id(self):
        """Simula seq.NEXTVAL da trilha."""
        with self._store.lock_auditoria:
            return self._store.proximo_id("tbsss_auditoria")

    def registrar(self, ator, ip, acao, entidade, entidade_id=None, detalhe=None, id=None):
        """Registra um evento na trilha de auditoria (com o id reservado, se informado)."""
        return self._store.registrar_auditoria_interno(
            ator=ator,
            ip=ip,
            acao=acao,
            entidade=entidade,
            entidade_id=entidade_id,
            detalhe=detalhe,
            id=id,
        )

    def _filtrar(self, filtros):
        """Registros que atendem aos filtros, ordenados por created_at DESC, id DESC (chamar sob o lock)."""
        filtros = filtros or {}
        lista = list(self._store.auditoria.values())

        ator_f = filtros.get("ator")
        if ator_f:
            lista = [a for a in lista if ator_f.lower() in a.get("ator", "").lower()]

        acao_f = filtros.get("acao")
        if acao_f:
            lista = [a for a in lista if a.get("acao") == acao_f]

        ent_f = filtros.get("entidade")
        if ent_f:
            lista = [a for a in lista if a.get("entidade") == ent_f]

        ent_id_f = filtros.get("entidade_id")
        if ent_id_f is not None:
            lista = [a for a in lista if a.get("entidade_id") == int(ent_id_f)]

        ip_f = filtros.get("ip_origem")
        if ip_f:
            lista = [a for a in lista if ip_f in (a.get("ip_origem") or "")]

        dt_ini = filtros.get("data_inicio")
        if dt_ini:
            lista = [a for a in lista if a.get("created_at") and a["created_at"] >= dt_ini]

        dt_fim = filtros.get("data_fim")
        if dt_fim:
            lista = [a for a in lista if a.get("created_at") and a["created_at"] <= dt_fim]

        id_max = filtros.get("id_max")
        if id_max is not None:
            lista = [a for a in lista if a["id"] <= int(id_max)]

        lista.sort(key=lambda x: (x.get("created_at") or self._store.agora(), x["id"]), reverse=True)
        return lista

    def listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista registros de auditoria ordenados por created_at DESC, id DESC."""
        with self._store.lock_auditoria:
            return paginar(self._filtrar(filtros), pagina=pagina, tamanho=tamanho)

    def iterar(self, filtros=None, limite=50000):
        """Iterador de copias, no maximo `limite` registros (no Oracle: cursor com arraysize, sem offset)."""
        with self._store.lock_auditoria:
            lista = copy.deepcopy(self._filtrar(filtros)[:max(0, int(limite))])
        return iter(lista)
