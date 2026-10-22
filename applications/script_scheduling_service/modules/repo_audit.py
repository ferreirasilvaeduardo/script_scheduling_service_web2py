# -*- coding: utf-8 -*-
"""Contrato de persistencia para trilha de auditoria (tbsss_audit)."""


class RepoAudit(object):
    """Contrato abstrato para registro e consulta de auditoria do sistema."""

    def reserve_id(self):
        """Proximo id da trilha (seq.NEXTVAL, README §2.7), usado antes de gravar a linha (README §4.4)."""
        raise NotImplementedError

    def register(self, actor, ip, action, entity, entity_id=None, detail=None, id=None):
        """Registra uma linha na trilha de auditoria e retorna o registro criado.

        id: opcional, o reservado por reserve_id (a aplicacao sempre informa o id, README §2.7).
        """
        raise NotImplementedError

    def list(self, filters=None, page=1, size=20):
        """Lista registros de auditoria ordenados por created_at DESC, id DESC.

        Chaves de filtros: ator (trecho, sem distinguir caixa), acao, entidade, entity_id,
        client_ip (trecho), data_inicio e data_fim (inclusivos) e id_max (inclusivo).
        """
        raise NotImplementedError

    def iterate(self, filters=None, limit=50000):
        """Iterador de no maximo `limite` registros, na ordem e com os filtros de listar (exportacao em streaming)."""
        raise NotImplementedError
