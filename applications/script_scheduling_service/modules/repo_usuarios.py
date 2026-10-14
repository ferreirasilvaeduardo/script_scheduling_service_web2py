# -*- coding: utf-8 -*-
"""Contrato de persistencia para o agregado de usuarios (tbsss_usuarios)."""


class RepoUsuarios(object):
    """Contrato abstrato para gestao de usuarios e credenciais."""

    def obter_por_login(self, login):
        """Retorna dict com dados do usuario ou None se nao encontrado."""
        raise NotImplementedError

    def obter_por_id(self, id):
        """Retorna dict com dados do usuario pelo ID ou lanca RepoNaoEncontrado."""
        raise NotImplementedError

    def obter_estado_sessao(self, usuario_id):
        """Retorna dict de sessao com usuario, perfil e perm_versao."""
        raise NotImplementedError

    def listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista usuarios paginados com formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}."""
        raise NotImplementedError

    def inserir(self, dados):
        """Insere novo usuario e retorna dict com o registro criado."""
        raise NotImplementedError

    def alterar(self, id, dados):
        """Atualiza campos do usuario pelo ID. Login e imutavel."""
        raise NotImplementedError

    def registrar_falha_login(self, login, bloqueio_ate=None):
        """Incrementa tentativas_falha e atualiza bloqueado_ate se fornecido."""
        raise NotImplementedError

    def registrar_sucesso_login(self, login, agora=None):
        """Zera tentativas_falha e bloqueado_ate, e atualiza ultimo_login."""
        raise NotImplementedError

    def desbloquear(self, id):
        """Zera tentativas_falha e remove bloqueado_ate do usuario pelo ID."""
        raise NotImplementedError

    def definir_senha(self, id, senha_hash, agora=None):
        """Atualiza senha_hash, senha_alterada_em e zera tentativas_falha."""
        raise NotImplementedError
