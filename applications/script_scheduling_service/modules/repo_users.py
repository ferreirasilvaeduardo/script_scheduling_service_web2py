# -*- coding: utf-8 -*-
"""Contrato de persistencia para o agregado de usuarios (tbsss_users)."""


class RepoUsers(object):
    """Contrato abstrato para gestao de usuarios e credenciais.

    Colunas de registro (CR-006, README §10): toda gravacao de negocio exige o actor, por
    audit['actor'] ou pelo parametro actor=; o INSERT grava created_*, a alteracao grava updated_*.
    Sem actor, RepoViolation sem gravar nada.
    """

    def get_by_login(self, login):
        """Retorna dict com dados do usuario ou None se nao encontrado."""
        raise NotImplementedError

    def get_by_id(self, id):
        """Retorna dict com dados do usuario pelo ID ou lanca RepoNotFound."""
        raise NotImplementedError

    def get_session_state(self, user_id):
        """Retorna dict de sessao com usuario, perfil, perm_version e session_epoch (CR-008, E2)."""
        raise NotImplementedError

    def list(self, filters=None, page=1, size=20):
        """Lista usuarios paginados com formato {'items': [...], 'total': n, 'page': p, 'size': t}.

        Ordem: login ASC, id ASC. Filtros (opcionais, combinados com E): login e nome (trecho, sem
        diferenciar maiusculas), profile_id, active e locked_at (locked_until > valor).
        """
        raise NotImplementedError

    def insert(self, date, audit=None, actor=None):
        """Insere novo usuario e retorna dict com o registro criado.

        audit: opcional, {'actor', 'ip', 'action', 'detail'}; gravada na mesma transacao
        (entidade tbsss_users, entity_id = novo id).
        """
        raise NotImplementedError

    def update(self, id, date, expected=None, audit=None, actor=None):
        """Atualiza campos do usuario pelo ID e retorna o registro. Login e imutavel.

        expected: opcional, dict campo -> valor lido; divergencia lanca RepoConflict sem alterar nada.
        Mudar profile_id ou ativo incrementa session_epoch (CR-008, E2): as sessoes abertas caem.
        Desativar o usuario ou mover para perfil nao administrativo bloqueia os admins ativos na
        mesma operacao (README §4.3.B); conjunto resultante vazio lanca
        RepoViolation(constraint='sss_ultimo_admin'). audit: opcional, na mesma transacao.
        """
        raise NotImplementedError

    def now(self):
        """Instante atual do banco (SYSDATE), sem microssegundos (README §4.2: relogio do banco)."""
        raise NotImplementedError

    def register_login_failure(self, login, lockout_s=None, audit=None, max_attempts=None,
                              lock_audit=None):
        """Incrementa failed_attempts numa unica operacao (README §4.2, §4.4). Rotina tecnica: sem updated_*.

        Com max_attempts (uso do login), a decisao de bloquear e tomada aqui, sobre a contagem lida sob a
        trava da linha: tentativas paralelas nunca escapam do limite (revisao de 2026-10-20). Ao atingir o
        limite, locked_until = SYSDATE + lockout_s/86400 (relogio do banco) e lock_audit
        (LOGIN_LOCKED) e gravada; o detalhe de auditoria (LOGIN_FAILED) ganha " (tentativa N de M)".
        Sem max_attempts: bloqueia se lockout_s for informado (testes e rotinas tecnicas).
        audit: dict ou lista de dicts {'actor', 'ip', 'action', 'detail'} na mesma transacao.
        Retorna o registro atualizado, com a chave 'locked_now' (bool).
        """
        raise NotImplementedError

    def register_login_success(self, login, new_hash=None, audit=None):
        """Zera failed_attempts e locked_until e grava last_login_at = SYSDATE numa unica operacao.

        Rotina tecnica do login: nao grava updated_* (CR-006).

        new_hash: rehash da senha (iteracoes abaixo do vigente), gravado na mesma transacao.
        audit: dict ou lista (LOGIN_OK), na mesma transacao. Retorna o registro atualizado.
        """
        raise NotImplementedError

    def unlock(self, id, audit=None, actor=None):
        """Desbloqueio pelo administrador: zera failed_attempts e locked_until e grava updated_*.

        audit: opcional, na mesma transacao. O ator (audit['actor'] ou actor=) e obrigatorio (CR-006).
        """
        raise NotImplementedError

    def reset_attempts(self, id):
        """Rotina tecnica do login (README §4.2): bloqueio vencido zera failed_attempts e locked_until.

        Nao grava updated_* nem auditoria (CR-006, README §10). Retorna o registro atualizado.
        """
        raise NotImplementedError

    def set_password(self, id, password_hash, now=None, audit=None, actor=None):
        """Atualiza password_hash e password_changed_at, zera failed_attempts e locked_until e incrementa
        session_epoch (CR-008, E2), tudo no mesmo UPDATE.

        audit: opcional, na mesma transacao; o detail nunca contem senha nem hash.
        """
        raise NotImplementedError

    def end_sessions(self, id, audit=None):
        """Logout (CR-008, E2): session_epoch = session_epoch + 1 num UPDATE, sem updated_* (rotina tecnica).

        audit: opcional (LOGOUT), na mesma transacao. Retorna o registro atualizado.
        """
        raise NotImplementedError
