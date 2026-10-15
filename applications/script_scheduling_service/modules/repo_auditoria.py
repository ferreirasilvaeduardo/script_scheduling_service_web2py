# -*- coding: utf-8 -*-
"""Contrato de persistencia para trilha de auditoria (tbsss_auditoria)."""


class RepoAuditoria(object):
    """Contrato abstrato para registro e consulta de auditoria do sistema."""

    def registrar(self, ator, ip, acao, entidade, entidade_id=None, detalhe=None):
        """Registra uma linha na trilha de auditoria e retorna o registro criado."""
        raise NotImplementedError

    def listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista registros de auditoria ordenados por created_at DESC, id DESC.

        Chaves de filtros: ator (trecho, sem distinguir caixa), acao, entidade, entidade_id,
        ip_origem (trecho), data_inicio e data_fim (inclusivos) e id_max (inclusivo).
        """
        raise NotImplementedError

    def iterar(self, filtros=None, limite=50000):
        """Iterador de no maximo `limite` registros, na ordem e com os filtros de listar (exportacao em streaming)."""
        raise NotImplementedError
