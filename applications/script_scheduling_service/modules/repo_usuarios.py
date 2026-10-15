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
        """Lista usuarios paginados com formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}.

        Ordem: login ASC, id ASC. Filtros (opcionais, combinados com E): login e nome (trecho, sem
        diferenciar maiusculas), perfil_id, ativo e bloqueado_em (bloqueado_ate > valor).
        """
        raise NotImplementedError

    def inserir(self, dados, auditoria=None):
        """Insere novo usuario e retorna dict com o registro criado.

        auditoria: opcional, {'ator', 'ip', 'acao', 'detalhe'}; gravada na mesma transacao
        (entidade tbsss_usuarios, entidade_id = novo id).
        """
        raise NotImplementedError

    def alterar(self, id, dados, esperado=None, auditoria=None):
        """Atualiza campos do usuario pelo ID e retorna o registro. Login e imutavel.

        esperado: opcional, dict campo -> valor lido; divergencia lanca RepoConflito sem alterar nada.
        Desativar o usuario ou mover para perfil nao administrativo bloqueia os admins ativos na
        mesma operacao (README §4.3.B); conjunto resultante vazio lanca
        RepoViolacao(constraint='sss_ultimo_admin'). auditoria: opcional, na mesma transacao.
        """
        raise NotImplementedError

    def registrar_falha_login(self, login, bloqueio_ate=None):
        """Incrementa tentativas_falha e atualiza bloqueado_ate se fornecido."""
        raise NotImplementedError

    def registrar_sucesso_login(self, login, agora=None):
        """Zera tentativas_falha e bloqueado_ate, e atualiza ultimo_login."""
        raise NotImplementedError

    def desbloquear(self, id, auditoria=None):
        """Zera tentativas_falha e remove bloqueado_ate do usuario pelo ID (auditoria opcional na mesma transacao)."""
        raise NotImplementedError

    def definir_senha(self, id, senha_hash, agora=None, auditoria=None):
        """Atualiza senha_hash e senha_alterada_em, zera tentativas_falha e bloqueado_ate.

        auditoria: opcional, na mesma transacao; o detalhe nunca contem senha nem hash.
        """
        raise NotImplementedError
