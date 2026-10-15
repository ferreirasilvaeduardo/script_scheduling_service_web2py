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

    def perfis_inserir(self, dados, auditoria=None):
        """Insere novo perfil e retorna dict com o registro criado.

        auditoria: opcional, {'ator', 'ip', 'acao', 'detalhe'}; gravada na mesma transacao
        (entidade tbsss_perfis, entidade_id = novo id).
        """
        raise NotImplementedError

    def perfis_alterar(self, id, dados, esperado=None, auditoria=None):
        """Atualiza perfil, incrementa perm_versao e retorna o registro, tudo na mesma transacao.

        esperado: opcional, dict campo -> valor lido; divergencia lanca RepoConflito sem alterar nada.
        Se a alteracao reduz administradores (ativo ou is_admin de 'S' para 'N'), a mesma operacao
        bloqueia os admins ativos (README §4.3.B) e, se o conjunto resultante ficar vazio, lanca
        RepoViolacao(constraint='sss_ultimo_admin') com ROLLBACK.
        auditoria: opcional, como em perfis_inserir.
        """
        raise NotImplementedError

    def matriz_obter(self, perfil_id):
        """Retorna dict {'funcs': [...], 'ambs': [...], 'scrs': [...]} com IDs associados."""
        raise NotImplementedError

    def matriz_salvar(self, perfil_id, funcs, ambs, scrs, perm_versao_esperada=None, auditoria=None):
        """Substitui a matriz do perfil e incrementa perm_versao atomicamente; retorna a nova matriz.

        perm_versao_esperada: opcional; se o perm_versao atual divergir, lanca RepoConflito sem alterar.
        IDs inexistentes violam as FKs (RepoViolacao). auditoria: opcional, gravada na mesma transacao.
        """
        raise NotImplementedError

    def admins_ativos_bloquear(self):
        """Executa lock dos usuarios administradores ativos e retorna lista de IDs (README §4.3.B)."""
        raise NotImplementedError

    def funcionalidades_listar(self):
        """Retorna lista de dicts com o catalogo canonico de funcionalidades ativas."""
        raise NotImplementedError
