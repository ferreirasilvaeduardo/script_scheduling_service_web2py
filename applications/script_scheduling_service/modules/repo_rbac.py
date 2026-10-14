# -*- coding: utf-8 -*-
"""Contrato de persistencia para RBAC e perfis (tbsss_perfis, tbsss_funcionalidades, matrizes)."""


class RepoRbac(object):
    """Contrato abstrato para gestao de perfis, matrizes de permissao e RBAC."""

    def perfis_listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista perfis paginados com formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}."""
        raise NotImplementedError

    def perfis_obter(self, id):
        """Retorna dict com dados do perfil ou lanca RepoNaoEncontrado."""
        raise NotImplementedError

    def perfis_inserir(self, dados):
        """Insere novo perfil e retorna dict com o registro criado."""
        raise NotImplementedError

    def perfis_alterar(self, id, dados):
        """Atualiza perfil e incrementa perm_versao."""
        raise NotImplementedError

    def matriz_obter(self, perfil_id):
        """Retorna dict {'funcs': [...], 'ambs': [...], 'scrs': [...]} com IDs associados."""
        raise NotImplementedError

    def matriz_salvar(self, perfil_id, funcs, ambs, scrs):
        """Salva a matriz tridimensional do perfil e incrementa perm_versao atomicamente."""
        raise NotImplementedError

    def admins_ativos_bloquear(self):
        """Executa lock dos usuarios administradores ativos e retorna lista de IDs (README §4.3.B)."""
        raise NotImplementedError

    def funcionalidades_listar(self):
        """Retorna lista de dicts com o catalogo canonico de funcionalidades ativas."""
        raise NotImplementedError
