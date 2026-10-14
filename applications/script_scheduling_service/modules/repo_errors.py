# -*- coding: utf-8 -*-
"""Excecoes de persistencia e contratos de repositorio do SSS (README §2.5).

Hierarquia de erros comuns consumida por UI, services, repo_fake e repo_oracle.
"""


class RepoErro(Exception):
    """Excecao base para erros da camada de persistencia."""
    pass


class RepoNaoEncontrado(RepoErro):
    """Entidade ou registro nao localizado pelo identificador fornecido."""
    pass


class RepoConflito(RepoErro):
    """Conflito de concorrencia otimista ou transicao de estado perdida (rowcount = 0)."""
    pass


class RepoViolacao(RepoErro):
    """Violacao de constraint (UK, CK, FK) ou regra de imutabilidade."""

    def __init__(self, mensagem, constraint=None):
        super(RepoViolacao, self).__init__(mensagem)
        self.constraint = constraint


class RepoIndisponivel(RepoErro):
    """Banco de dados inacessivel, timeout de conexao ou queda de sessao."""
    pass
