# -*- coding: utf-8 -*-
"""Autenticacao, bloqueio, revalidacao de sessao e logout (README §4.2, §4.4).

As mensagens devolvidas ao usuario sao sempre genericas; o motivo vai so para o log.
Senha e hash nunca sao registrados.
"""
import collections
import datetime
import re
import threading

import rbac
import security
import ui_helpers
from repo_errors import RepoNotFound

# Mensagens-padrao em duas partes (README §2.4.2); o bloqueio informa os minutos configurados.
MSG_GENERIC = ui_helpers.mensagem("login_incorreto")

ENTITY = "tbsss_users"
MSG_CURRENT_PASSWORD = u"A senha atual está incorreta."
MSG_CONFIRMATION = u"A confirmação não confere com a nova senha."
PASSWORD_MAX = 1024
MATRIX_CACHE_MAX = 64
SIMULATED_MAX = 1024

_RE_LOGIN = re.compile(r"[a-z0-9._-]{3,30}")


def _aud(login, ip, acao, detalhe):
    return {"actor": login, "ip": ip, "action": acao, "detail": detalhe}


class AuthService(object):
    """Servico de autenticacao com dependencias injetadas (repositorios, limites, relogio e log)."""

    def __init__(self, usuarios, rbac_repo, catalogo, auditoria, max_tentativas, bloqueio_s,
                 log, relogio=None):
        self._usuarios = usuarios
        self._rbac = rbac_repo
        self._catalogo = catalogo
        self._auditoria = auditoria
        self._max = int(max_tentativas)
        self._bloqueio_s = int(bloqueio_s)
        self._bloqueio = datetime.timedelta(seconds=self._bloqueio_s)
        self.msg_bloqueio = ui_helpers.mensagem("conta_bloqueada", minutos=max(1, -(-self._bloqueio_s // 60)))
        self._log = log
        # Relogio do banco (README §4.2): o bloqueio nunca depende do relogio do no web.
        self._relogio = relogio or usuarios.now
        self._lock = threading.Lock()
        self._cache_matriz = collections.OrderedDict()
        # Falhas de logins inexistentes: replica o bloqueio para nao revelar a existencia da conta.
        self._simulados = collections.OrderedDict()

    # ------------------------------------------------------------------ login

    def authenticate(self, login, senha, ip):
        """Autentica login/senha. Retorna (ctx, None) no sucesso ou (None, mensagem_generica)."""
        agora = self._relogio()
        login_norm = login.strip().lower() if isinstance(login, str) else ""
        senha_ok_tipo = isinstance(senha, str) and 0 < len(senha) <= PASSWORD_MAX
        senha_txt = senha if senha_ok_tipo else ""
        login_valido = bool(_RE_LOGIN.fullmatch(login_norm))

        usuario = self._usuarios.get_by_login(login_norm) if login_valido else None
        if usuario is None:
            security.verify_password(senha_txt, security.dummy_hash())
            return self._unknown_login(login_norm if login_valido else "?", ip, agora)

        armazenado = usuario.get("password_hash")
        if security.is_known_hash(armazenado):
            senha_confere = senha_ok_tipo and security.verify_password(senha_txt, armazenado)
        else:
            security.verify_password(senha_txt, security.dummy_hash())
            senha_confere = False

        if self._is_locked(usuario, agora):
            self._record_failure(usuario, ip, "conta bloqueada")
            return None, self.msg_bloqueio
        usuario = self._reset_if_expired(usuario)

        if not senha_confere:
            return self._wrong_password(usuario, ip)

        estado = self._usuarios.get_session_state(usuario["id"])
        if estado.get("usuario_ativo") != "Y" or estado.get("perfil_ativo") != "Y":
            self._record_failure(usuario, ip, "usuario ou perfil inativo")
            return None, MSG_GENERIC

        novo_hash = security.hash_password(senha_txt) if security.needs_rehash(armazenado) else None
        # Sucesso, rehash e auditoria numa unica operacao do repositorio (README §4.2, §4.4).
        self._usuarios.register_login_success(
            usuario["login"], novo_hash=novo_hash,
            auditoria=_aud(usuario["login"], ip, "LOGIN_OK", "Login bem-sucedido"))
        if novo_hash is not None:
            self._log.info("hash de senha atualizado para as iteracoes vigentes (login=%s)",
                           usuario["login"], extra={"action": "LOGIN"})
        self._log.info("login ok (login=%s ip=%s)", usuario["login"], ip, extra={"action": "LOGIN"})
        return self._build_ctx(estado), None

    @staticmethod
    def _is_locked(usuario, agora):
        bloqueado_ate = usuario.get("locked_until")
        return bloqueado_ate is not None and bloqueado_ate > agora

    def _reset_if_expired(self, usuario):
        # Bloqueio expirado (ou contador no limite): novo ciclo de tentativas, no login e na troca de senha.
        if usuario.get("locked_until") is not None or int(usuario.get("failed_attempts") or 0) >= self._max:
            return self._usuarios.reset_attempts(usuario["id"])
        return usuario

    def _record_failure(self, usuario, ip, motivo):
        self._auditoria.register(usuario["login"], ip, "LOGIN_FAILED", ENTITY, usuario["id"],
                                  "Falha de login: %s" % motivo)
        self._log.warning("login falhou (login=%s ip=%s reason=%s)", usuario["login"], ip, motivo,
                          extra={"action": "LOGIN"})

    def _wrong_password(self, usuario, ip):
        # O repositorio conta e decide o bloqueio sob a trava da linha: a contagem lida aqui pode estar
        # desatualizada quando ha tentativas em paralelo (revisao de 2026-10-20).
        reg = self._usuarios.register_login_failure(
            usuario["login"], self._bloqueio_s, max_tentativas=self._max,
            auditoria=_aud(usuario["login"], ip, "LOGIN_FAILED", "Falha de login: senha incorreta"),
            auditoria_bloqueio=_aud(usuario["login"], ip, "LOGIN_LOCKED",
                                    "Conta bloqueada por %d falhas consecutivas" % self._max))
        tentativas = int(reg.get("failed_attempts") or 0)
        bloquear = bool(reg.get("bloqueou"))
        motivo = "senha incorreta (tentativa %d de %d)" % (tentativas, self._max)
        self._log.warning("login falhou (login=%s ip=%s reason=%s)", usuario["login"], ip, motivo,
                          extra={"action": "LOGIN"})
        if not bloquear:
            return None, MSG_GENERIC
        self._log.warning("conta bloqueada (login=%s ip=%s)", usuario["login"], ip, extra={"action": "LOGIN"})
        return None, self.msg_bloqueio

    def _unknown_login(self, login, ip, agora):
        with self._lock:
            falhas, bloqueado_ate = self._simulados.pop(login, (0, None))
            if bloqueado_ate is not None and bloqueado_ate > agora:
                self._simulados[login] = (falhas, bloqueado_ate)
                resultado = "bloqueado"
            else:
                if bloqueado_ate is not None:
                    falhas = 0
                falhas += 1
                bloqueado_ate = agora + self._bloqueio if falhas >= self._max else None
                self._simulados[login] = (falhas, bloqueado_ate)
                resultado = "bloqueou" if bloqueado_ate is not None else "falha"
            while len(self._simulados) > SIMULATED_MAX:
                self._simulados.popitem(last=False)

        self._auditoria.register(login, ip, "LOGIN_FAILED", ENTITY, None,
                                  "Falha de login: usuario inexistente")
        self._log.warning("login falhou (login=%s ip=%s reason=usuario inexistente)", login, ip,
                          extra={"action": "LOGIN"})
        if resultado == "falha":
            return None, MSG_GENERIC
        if resultado == "bloqueou":
            self._auditoria.register(login, ip, "LOGIN_LOCKED", ENTITY, None,
                                      "Bloqueio simulado de login inexistente")
        return None, self.msg_bloqueio

    # ------------------------------------------------------------ revalidacao

    def revalidate(self, sessao, ip=None):
        """Reconsulta usuario e perfil (README §4.2). Retorna ctx ou None se a sessao deve encerrar.

        Encerramento por usuario ou perfil inativo e auditado como LOGOUT (README §4.2, D13).
        """
        usuario_id = sessao.get("usuario_id")
        if not isinstance(usuario_id, int) or isinstance(usuario_id, bool):
            return None
        try:
            estado = self._usuarios.get_session_state(usuario_id)
        except RepoNotFound:
            self._log.warning("sessao encerrada: usuario inexistente (user_id=%s)", usuario_id,
                              extra={"action": "SESSAO"})
            return None
        if estado.get("login") != sessao.get("login"):
            self._log.warning("sessao encerrada: login divergente (user_id=%s)", usuario_id,
                              extra={"action": "SESSAO"})
            return None
        if estado.get("usuario_ativo") != "Y" or estado.get("perfil_ativo") != "Y":
            motivo = u"usuário inativo" if estado.get("usuario_ativo") != "Y" else u"perfil inativo"
            self._auditoria.register(estado.get("login"), ip, "LOGOUT", ENTITY, usuario_id,
                                      u"sessão encerrada pela revalidação: %s" % motivo)
            self._log.info("sessao encerrada: usuario ou perfil inativo (login=%s)", estado.get("login"),
                           extra={"action": "SESSAO"})
            return None
        if estado.get("session_epoch", 0) != sessao.get("sessao_epoch"):
            # Sessao revogada (CR-008, E2): logout em outro lugar, senha trocada ou redefinida, perfil
            # ou situacao do usuario alterados. Ja auditado na origem; aqui so o log.
            self._log.info("sessao encerrada: sessao revogada (login=%s)", estado.get("login"),
                           extra={"action": "SESSAO"})
            return None
        if estado.get("perm_version") != sessao.get("perm_versao") \
                or estado.get("profile_id") != sessao.get("perfil_id"):
            self._log.info("permissoes recarregadas (login=%s profile_id=%s perm_version=%s)",
                           estado.get("login"), estado.get("profile_id"), estado.get("perm_version"),
                           extra={"action": "SESSAO"})
        return self._build_ctx(estado)

    def _build_ctx(self, estado):
        funcs, ambs, scrs = self._matrix(estado["profile_id"], estado["perm_version"])
        dados = dict(estado)
        dados.update(features=funcs, environments=ambs, scripts=scrs)
        return rbac.user_context(dados)

    def _matrix(self, perfil_id, perm_versao):
        # perm_versao muda em toda alteracao de matriz/perfil (README §4.3.A): a chave invalida o cache.
        chave = (perfil_id, perm_versao)
        with self._lock:
            if chave in self._cache_matriz:
                self._cache_matriz.move_to_end(chave)
                return self._cache_matriz[chave]

        matriz = self._rbac.matrix_get(perfil_id)
        codigos = dict(
            (f["id"], f["code"]) for f in self._rbac.features_list() if f.get("active") == "Y"
        )
        funcs = frozenset(codigos[fid] for fid in matriz.get("funcs", ()) if fid in codigos)
        nomes = []
        for aid in matriz.get("ambs", ()):
            try:
                nomes.append(self._catalogo.environments_get(aid)["name"])
            except RepoNotFound:
                self._log.warning("ambiente da matriz inexistente (profile_id=%s environment_id=%s)",
                                  perfil_id, aid, extra={"action": "SESSAO"})
        valor = (funcs, frozenset(nomes), frozenset(matriz.get("scrs", ())))

        with self._lock:
            self._cache_matriz[chave] = valor
            while len(self._cache_matriz) > MATRIX_CACHE_MAX:
                self._cache_matriz.popitem(last=False)
        return valor

    # ------------------------------------------------------- troca de senha

    def change_password(self, ctx, ip, atual, nova, confirmacao):
        """Troca da propria senha (exige a atual). Retorna (resultado, erros por campo).

        resultado: 'OK' | 'ERRO' | 'BLOQUEADO'. Senha atual errada conta como falha de login
        (mesmo limite e bloqueio do §4.2); ao bloquear, o chamador encerra a sessao.
        """
        agora = self._relogio()
        usuario = self._usuarios.get_by_id(ctx["user_id"])
        if self._is_locked(usuario, agora):
            self._record_failure(usuario, ip, "troca de senha com conta bloqueada")
            return "BLOQUEADO", {"senha_atual": self.msg_bloqueio}
        usuario = self._reset_if_expired(usuario)
        armazenado = usuario.get("password_hash")
        atual_ok = (isinstance(atual, str) and 0 < len(atual) <= PASSWORD_MAX
                    and security.is_known_hash(armazenado) and security.verify_password(atual, armazenado))
        if not atual_ok:
            _ctx, mensagem = self._wrong_password(usuario, ip)
            if mensagem == self.msg_bloqueio:
                return "BLOQUEADO", {"senha_atual": self.msg_bloqueio}
            return "ERRO", {"senha_atual": MSG_CURRENT_PASSWORD}
        erros = {}
        problemas = security.validate_password_policy(nova) if isinstance(nova, str) and len(nova) <= PASSWORD_MAX \
            else [u"Informe a nova senha."]
        if problemas:
            erros["nova"] = problemas[0]
        elif confirmacao != nova:
            erros["confirmacao"] = MSG_CONFIRMATION
        if erros:
            return "ERRO", erros
        self._usuarios.set_password(usuario["id"], security.hash_password(nova), agora,
                                     auditoria={"actor": usuario["login"], "ip": ip, "action": "UPDATE",
                                                "detail": u"senha alterada pelo próprio usuário"})
        self._log.info("senha alterada pelo proprio usuario (login=%s ip=%s)", usuario["login"], ip,
                       extra={"action": "UPDATE"})
        return "OK", {}

    # ----------------------------------------------------------------- logout

    def session_epoch(self, usuario_id):
        """sessao_epoch vigente do usuario, para a sessao nova depois da troca de senha (CR-008, E2)."""
        return self._usuarios.get_session_state(usuario_id).get("session_epoch", 0)

    def logout(self, ctx, ip):
        """Encerra todas as sessoes do usuario (session_epoch + 1) e audita LOGOUT na mesma operacao."""
        if not ctx:
            return
        self._usuarios.end_sessions(ctx["user_id"], auditoria=_aud(ctx["login"], ip, "LOGOUT", "Logout"))
        self._log.info("logout (login=%s ip=%s)", ctx["login"], ip, extra={"action": "LOGIN"})


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from gluon import current
            import sss_logging
            fabrica = current.repo_factory
            cfg = current.sss_cfg
            _default = AuthService(
                usuarios=fabrica.get("users"),
                rbac_repo=fabrica.get("rbac"),
                catalogo=fabrica.get("catalog"),
                auditoria=fabrica.get("audit"),
                max_tentativas=cfg.web.login_max_attempts,
                bloqueio_s=cfg.web.login_lockout_s,
                log=sss_logging.get_logger("sss_web", cfg),
            )
        return _default


def authenticate(login, senha, ip):
    """Autentica pelo servico padrao do processo web."""
    return _service().authenticate(login, senha, ip)


def revalidate(sessao, ip=None):
    """Revalida a sessao pelo servico padrao do processo web."""
    return _service().revalidate(sessao, ip)


def session_epoch(usuario_id):
    """sessao_epoch vigente pelo servico padrao do processo web."""
    return _service().session_epoch(usuario_id)


def logout(ctx, ip):
    """Audita o logout pelo servico padrao do processo web."""
    return _service().logout(ctx, ip)


def change_password(ctx, ip, atual, nova, confirmacao):
    """Troca da propria senha pelo servico padrao do processo web."""
    return _service().change_password(ctx, ip, atual, nova, confirmacao)
