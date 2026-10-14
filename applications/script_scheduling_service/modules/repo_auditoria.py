# -*- coding: utf-8 -*-
"""Contrato de persistencia para trilha de auditoria (tbsss_auditoria)."""


class RepoAuditoria(object):
    """Contrato abstrato para registro e consulta de auditoria do sistema."""

    def registrar(self, ator, ip, acao, entidade, entidade_id=None, detalhe=None):
        """Registra uma linha na trilha de auditoria e retorna o registro criado."""
        raise NotImplementedError

    def listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista registros de auditoria ordenados por created_at DESC, id DESC."""
        raise NotImplementedError
