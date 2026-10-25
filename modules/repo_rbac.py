# -*- coding: utf-8 -*-
"""Contrato de persistencia para RBAC e perfis (tbsss_profiles, tbsss_features, matrizes)."""


class RepoRbac(object):
    """Contrato abstrato para gestao de perfis, matrizes de permissao e RBAC.

    Colunas de registro (CR-006, README §10): toda gravacao de negocio exige o actor, por
    audit['actor'] ou pelo parametro actor=; o INSERT grava created_*, a alteracao grava updated_*.
    Sem actor, RepoViolation sem gravar nada.
    """

    def profiles_list(self, filters=None, page=1, size=20):
        """Lista perfis paginados com formato {'items': [...], 'total': n, 'page': p, 'size': t}."""
        raise NotImplementedError

    def profiles_get(self, id):
        """Retorna dict com dados do perfil ou lanca RepoNotFound."""
        raise NotImplementedError

    def profiles_insert(self, data, audit=None, actor=None):
        """Insere novo perfil e retorna dict com o registro criado.

        audit: opcional, {'actor', 'ip', 'action', 'detail'}; gravada na mesma transacao
        (entidade tbsss_profiles, entity_id = novo id).
        """
        raise NotImplementedError

    def profiles_update(self, id, data, expected=None, audit=None, actor=None):
        """Atualiza perfil, incrementa perm_version e retorna o registro, tudo na mesma transacao.

        expected: opcional, dict campo -> valor lido; divergencia lanca RepoConflict sem alterar nada.
        Se a alteracao reduz administradores (ativo ou is_admin de 'S' para 'N'), a mesma operacao
        bloqueia os admins ativos (README §4.3.B) e, se o conjunto resultante ficar vazio, lanca
        RepoViolation(constraint='sss_ultimo_admin') com ROLLBACK.
        audit: opcional, como em profiles_insert.
        """
        raise NotImplementedError

    def matrix_get(self, profile_id):
        """Retorna dict {'funcs': [...], 'ambs': [...], 'scrs': [...]} com IDs associados."""
        raise NotImplementedError

    def matrix_save(self, profile_id, features_ids, envs, scrs, expected_perm_version=None, audit=None, actor=None):
        """Substitui a matriz do perfil e incrementa perm_version atomicamente; retorna a nova matriz.

        expected_perm_version: opcional; se o perm_version atual divergir, lanca RepoConflict sem alterar.
        IDs inexistentes violam as FKs (RepoViolation). audit: opcional, gravada na mesma transacao.
        """
        raise NotImplementedError

    def lock_active_admins(self):
        """Executa lock dos usuarios administradores ativos e retorna lista de IDs (README §4.3.B)."""
        raise NotImplementedError

    def features_list(self):
        """Retorna lista de dicts com o catalogo canonico de funcionalidades ativas."""
        raise NotImplementedError
