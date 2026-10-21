# -*- coding: utf-8 -*-
"""Contrato de persistencia para o agregado de usuarios (tbsss_users)."""


class RepoUsuarios(object):
    """Contrato abstrato para gestao de usuarios e credenciais.

    Colunas de registro (CR-006, README §10): toda gravacao de negocio exige o actor, por
    auditoria['actor'] ou pelo parametro actor=; o INSERT grava created_*, a alteracao grava updated_*.
    Sem actor, RepoViolacao sem gravar nada.
    """

    def obter_por_login(self, login):
        """Retorna dict com dados do usuario ou None se nao encontrado."""
        raise NotImplementedError

    def obter_por_id(self, id):
        """Retorna dict com dados do usuario pelo ID ou lanca RepoNaoEncontrado."""
        raise NotImplementedError

    def obter_estado_sessao(self, usuario_id):
        """Retorna dict de sessao com usuario, perfil, perm_versao e sessao_epoch (CR-008, E2)."""
        raise NotImplementedError

    def listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista usuarios paginados com formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}.

        Ordem: login ASC, id ASC. Filtros (opcionais, combinados com E): login e nome (trecho, sem
        diferenciar maiusculas), perfil_id, ativo e bloqueado_em (bloqueado_ate > valor).
        """
        raise NotImplementedError

    def inserir(self, dados, auditoria=None, ator=None):
        """Insere novo usuario e retorna dict com o registro criado.

        auditoria: opcional, {'ator', 'ip', 'acao', 'detalhe'}; gravada na mesma transacao
        (entidade tbsss_users, entidade_id = novo id).
        """
        raise NotImplementedError

    def alterar(self, id, dados, esperado=None, auditoria=None, ator=None):
        """Atualiza campos do usuario pelo ID e retorna o registro. Login e imutavel.

        esperado: opcional, dict campo -> valor lido; divergencia lanca RepoConflito sem alterar nada.
        Mudar perfil_id ou ativo incrementa sessao_epoch (CR-008, E2): as sessoes abertas caem.
        Desativar o usuario ou mover para perfil nao administrativo bloqueia os admins ativos na
        mesma operacao (README §4.3.B); conjunto resultante vazio lanca
        RepoViolacao(constraint='sss_ultimo_admin'). auditoria: opcional, na mesma transacao.
        """
        raise NotImplementedError

    def agora(self):
        """Instante atual do banco (SYSDATE), sem microssegundos (README §4.2: relogio do banco)."""
        raise NotImplementedError

    def registrar_falha_login(self, login, bloqueio_s=None, auditoria=None, max_tentativas=None,
                              auditoria_bloqueio=None):
        """Incrementa tentativas_falha numa unica operacao (README §4.2, §4.4). Rotina tecnica: sem updated_*.

        Com max_tentativas (uso do login), a decisao de bloquear e tomada aqui, sobre a contagem lida sob a
        trava da linha: tentativas paralelas nunca escapam do limite (revisao de 2026-10-20). Ao atingir o
        limite, bloqueado_ate = SYSDATE + bloqueio_s/86400 (relogio do banco) e auditoria_bloqueio
        (LOGIN_LOCKED) e gravada; o detalhe de auditoria (LOGIN_FAILED) ganha " (tentativa N de M)".
        Sem max_tentativas: bloqueia se bloqueio_s for informado (testes e rotinas tecnicas).
        auditoria: dict ou lista de dicts {'ator', 'ip', 'acao', 'detalhe'} na mesma transacao.
        Retorna o registro atualizado, com a chave 'bloqueou' (bool).
        """
        raise NotImplementedError

    def registrar_sucesso_login(self, login, novo_hash=None, auditoria=None):
        """Zera tentativas_falha e bloqueado_ate e grava ultimo_login = SYSDATE numa unica operacao.

        Rotina tecnica do login: nao grava updated_* (CR-006).

        novo_hash: rehash da senha (iteracoes abaixo do vigente), gravado na mesma transacao.
        auditoria: dict ou lista (LOGIN_OK), na mesma transacao. Retorna o registro atualizado.
        """
        raise NotImplementedError

    def desbloquear(self, id, auditoria=None, ator=None):
        """Desbloqueio pelo administrador: zera tentativas_falha e bloqueado_ate e grava updated_*.

        auditoria: opcional, na mesma transacao. O ator (auditoria['ator'] ou ator=) e obrigatorio (CR-006).
        """
        raise NotImplementedError

    def reiniciar_tentativas(self, id):
        """Rotina tecnica do login (README §4.2): bloqueio vencido zera tentativas_falha e bloqueado_ate.

        Nao grava updated_* nem auditoria (CR-006, README §10). Retorna o registro atualizado.
        """
        raise NotImplementedError

    def definir_senha(self, id, senha_hash, agora=None, auditoria=None, ator=None):
        """Atualiza password_hash e password_changed_at, zera failed_attempts e locked_until e incrementa
        session_epoch (CR-008, E2), tudo no mesmo UPDATE.

        auditoria: opcional, na mesma transacao; o detail nunca contem senha nem hash.
        """
        raise NotImplementedError

    def encerrar_sessoes(self, id, auditoria=None):
        """Logout (CR-008, E2): session_epoch = session_epoch + 1 num UPDATE, sem updated_* (rotina tecnica).

        auditoria: opcional (LOGOUT), na mesma transacao. Retorna o registro atualizado.
        """
        raise NotImplementedError
