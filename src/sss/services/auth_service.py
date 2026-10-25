# -*- coding: utf-8 -*-
"""Autenticacao, bloqueio, revalidacao de sessao e logout (README §4.2, §4.4).

As mensagens devolvidas ao usuario sao sempre genericas; o motivo vai so para o log.
Senha e hash nunca sao registrados.
"""
import collections
import datetime
import re
import threading

from sss.core import rbac
from sss.core import security
from sss.ui import ui_helpers
from sss.persistence.repo_errors import RepoNotFound

# Mensagens-padrao em duas partes (README §2.4.2); o bloqueio informa os minutos configurados.
MSG_GENERIC = ui_helpers.message("login_failed")

ENTITY = "tbsss_users"
MSG_CURRENT_PASSWORD = u"A senha atual está incorreta."
MSG_CONFIRMATION = u"A confirmação não confere com a nova senha."
PASSWORD_MAX = 1024
MATRIX_CACHE_MAX = 64
SIMULATED_MAX = 1024

_RE_LOGIN = re.compile(r"[a-z0-9._-]{3,30}")


def _aud(login, ip, action, detail):
    return {"actor": login, "ip": ip, "action": action, "detail": detail}


class AuthService(object):
    """Servico de autenticacao com dependencias injetadas (repositorios, limites, relogio e log)."""

    def __init__(self, users, rbac_repo, catalog, audit, max_attempts, lockout_s,
                 log, clock=None):
        self._users = users
        self._rbac = rbac_repo
        self._catalog = catalog
        self._audit = audit
        self._max = int(max_attempts)
        self._lockout_s = int(lockout_s)
        self._lockout = datetime.timedelta(seconds=self._lockout_s)
        self.lockout_message = ui_helpers.message("account_locked", minutos=max(1, -(-self._lockout_s // 60)))
        self._log = log
        # Relogio do banco (README §4.2): o bloqueio nunca depende do relogio do no web.
        self._clock = clock or users.now
        self._lock = threading.Lock()
        self._matrix_cache = collections.OrderedDict()
        # Falhas de logins inexistentes: replica o bloqueio para nao revelar a existencia da conta.
        self._simulated = collections.OrderedDict()

    # ------------------------------------------------------------------ login

    def authenticate(self, login, password_value, ip):
        """Autentica login/senha. Retorna (ctx, None) no sucesso ou (None, mensagem generica)."""
        now = self._clock()
        login_norm = login.strip().lower() if isinstance(login, str) else ""
        password_ok_kind = isinstance(password_value, str) and 0 < len(password_value) <= PASSWORD_MAX
        password_txt = password_value if password_ok_kind else ""
        login_valid = bool(_RE_LOGIN.fullmatch(login_norm))

        user = self._users.get_by_login(login_norm) if login_valid else None
        if user is None:
            security.verify_password(password_txt, security.dummy_hash())
            return self._unknown_login(login_norm if login_valid else "?", ip, now)

        stored = user.get("password_hash")
        if security.is_known_hash(stored):
            password_matches = password_ok_kind and security.verify_password(password_txt, stored)
        else:
            security.verify_password(password_txt, security.dummy_hash())
            password_matches = False

        if self._is_locked(user, now):
            self._record_failure(user, ip, "conta bloqueada")
            return None, self.lockout_message
        user = self._reset_if_expired(user)

        if not password_matches:
            return self._wrong_password(user, ip)

        state = self._users.get_session_state(user["id"])
        if state.get("active_user") != "Y" or state.get("active_profile") != "Y":
            self._record_failure(user, ip, "usuario ou perfil inativo")
            return None, MSG_GENERIC

        new_hash = security.hash_password(password_txt) if security.needs_rehash(stored) else None
        # Sucesso, rehash e auditoria numa unica operacao do repositorio (README §4.2, §4.4).
        self._users.register_login_success(
            user["login"], new_hash=new_hash,
            audit=_aud(user["login"], ip, "LOGIN_OK", "Login bem-sucedido"))
        if new_hash is not None:
            self._log.info("hash de senha atualizado para as iteracoes vigentes (login=%s)",
                           user["login"], extra={"action": "LOGIN"})
        self._log.info("login ok (login=%s ip=%s)", user["login"], ip, extra={"action": "LOGIN"})
        return self._build_ctx(state), None

    @staticmethod
    def _is_locked(user, now):
        locked_until = user.get("locked_until")
        return locked_until is not None and locked_until > now

    def _reset_if_expired(self, user):
        # Bloqueio expirado (ou contador no limite): novo ciclo de tentativas, no login e na troca de senha.
        if user.get("locked_until") is not None or int(user.get("failed_attempts") or 0) >= self._max:
            return self._users.reset_attempts(user["id"])
        return user

    def _record_failure(self, user, ip, reason):
        self._audit.register(user["login"], ip, "LOGIN_FAILED", ENTITY, user["id"],
                                  "Falha de login: %s" % reason)
        self._log.warning("login falhou (login=%s ip=%s reason=%s)", user["login"], ip, reason,
                          extra={"action": "LOGIN"})

    def _wrong_password(self, user, ip):
        # O repositorio conta e decide o bloqueio sob a trava da linha: a contagem lida aqui pode estar
        # desatualizada quando ha tentativas em paralelo (revisao de 2026-10-20).
        reg = self._users.register_login_failure(
            user["login"], self._lockout_s, max_attempts=self._max,
            audit=_aud(user["login"], ip, "LOGIN_FAILED", "Falha de login: senha incorreta"),
            lock_audit=_aud(user["login"], ip, "LOGIN_LOCKED",
                                    "Conta bloqueada por %d falhas consecutivas" % self._max))
        attempts = int(reg.get("failed_attempts") or 0)
        lock = bool(reg.get("locked_now"))
        reason = "senha incorreta (tentativa %d de %d)" % (attempts, self._max)
        self._log.warning("login falhou (login=%s ip=%s reason=%s)", user["login"], ip, reason,
                          extra={"action": "LOGIN"})
        if not lock:
            return None, MSG_GENERIC
        self._log.warning("conta bloqueada (login=%s ip=%s)", user["login"], ip, extra={"action": "LOGIN"})
        return None, self.lockout_message

    def _unknown_login(self, login, ip, now):
        with self._lock:
            failures, locked_until = self._simulated.pop(login, (0, None))
            if locked_until is not None and locked_until > now:
                self._simulated[login] = (failures, locked_until)
                result = "bloqueado"
            else:
                if locked_until is not None:
                    failures = 0
                failures += 1
                locked_until = now + self._lockout if failures >= self._max else None
                self._simulated[login] = (failures, locked_until)
                result = "bloqueou" if locked_until is not None else "falha"
            while len(self._simulated) > SIMULATED_MAX:
                self._simulated.popitem(last=False)

        self._audit.register(login, ip, "LOGIN_FAILED", ENTITY, None,
                                  "Falha de login: usuario inexistente")
        self._log.warning("login falhou (login=%s ip=%s reason=usuario inexistente)", login, ip,
                          extra={"action": "LOGIN"})
        if result == "falha":
            return None, MSG_GENERIC
        if result == "bloqueou":
            self._audit.register(login, ip, "LOGIN_LOCKED", ENTITY, None,
                                      "Bloqueio simulado de login inexistente")
        return None, self.lockout_message

    # ------------------------------------------------------------ revalidacao

    def revalidate(self, sessao, ip=None):
        """Reconsulta usuario e perfil (README §4.2). Retorna ctx ou None se a sessao deve encerrar.

        Encerramento por usuario ou perfil inativo e auditado como LOGOUT (README §4.2, D13).
        """
        user_id = sessao.get("user_id")
        if not isinstance(user_id, int) or isinstance(user_id, bool):
            return None
        try:
            state = self._users.get_session_state(user_id)
        except RepoNotFound:
            self._log.warning("sessao encerrada: usuario inexistente (user_id=%s)", user_id,
                              extra={"action": "SESSAO"})
            return None
        if state.get("login") != sessao.get("login"):
            self._log.warning("sessao encerrada: login divergente (user_id=%s)", user_id,
                              extra={"action": "SESSAO"})
            return None
        if state.get("active_user") != "Y" or state.get("active_profile") != "Y":
            reason = u"usuário inativo" if state.get("active_user") != "Y" else u"perfil inativo"
            self._audit.register(state.get("login"), ip, "LOGOUT", ENTITY, user_id,
                                      u"sessão encerrada pela revalidação: %s" % reason)
            self._log.info("sessao encerrada: usuario ou perfil inativo (login=%s)", state.get("login"),
                           extra={"action": "SESSAO"})
            return None
        if state.get("session_epoch", 0) != sessao.get("session_epoch"):
            # Sessao revogada (CR-008, E2): logout em outro lugar, senha trocada ou redefinida, perfil
            # ou situacao do usuario alterados. Ja auditado na origem; aqui so o log.
            self._log.info("sessao encerrada: sessao revogada (login=%s)", state.get("login"),
                           extra={"action": "SESSAO"})
            return None
        if state.get("perm_version") != sessao.get("perm_version") \
                or state.get("profile_id") != sessao.get("profile_id"):
            self._log.info("permissoes recarregadas (login=%s profile_id=%s perm_version=%s)",
                           state.get("login"), state.get("profile_id"), state.get("perm_version"),
                           extra={"action": "SESSAO"})
        return self._build_ctx(state)

    def _build_ctx(self, state):
        features, envs, scrs = self._matrix(state["profile_id"], state["perm_version"])
        data = dict(state)
        data.update(features=features, environments=envs, scripts=scrs)
        return rbac.user_context(data)

    def _matrix(self, profile_id, perm_version):
        # perm_version muda em toda alteracao de matriz/perfil (README §4.3.A): a chave invalida o cache.
        key = (profile_id, perm_version)
        with self._lock:
            if key in self._matrix_cache:
                self._matrix_cache.move_to_end(key)
                return self._matrix_cache[key]

        matrix = self._rbac.matrix_get(profile_id)
        codes = dict(
            (f["id"], f["code"]) for f in self._rbac.features_list() if f.get("active") == "Y"
        )
        features = frozenset(codes[fid] for fid in matrix.get("funcs", ()) if fid in codes)
        names = []
        for aid in matrix.get("ambs", ()):
            try:
                names.append(self._catalog.environments_get(aid)["name"])
            except RepoNotFound:
                self._log.warning("ambiente da matriz inexistente (profile_id=%s environment_id=%s)",
                                  profile_id, aid, extra={"action": "SESSAO"})
        value = (features, frozenset(names), frozenset(matrix.get("scrs", ())))

        with self._lock:
            self._matrix_cache[key] = value
            while len(self._matrix_cache) > MATRIX_CACHE_MAX:
                self._matrix_cache.popitem(last=False)
        return value

    # ------------------------------------------------------- troca de senha

    def change_password(self, ctx, ip, current_value, new, confirmation):
        """Troca da propria senha (exige a atual). Retorna (resultado, erros por campo).

        resultado: 'OK' | 'ERROR' | 'LOCKED'. Senha atual errada conta como falha de login
        (mesmo limite e bloqueio do §4.2); ao bloquear, o chamador encerra a sessao.
        """
        now = self._clock()
        user = self._users.get_by_id(ctx["user_id"])
        if self._is_locked(user, now):
            self._record_failure(user, ip, "troca de senha com conta bloqueada")
            return "LOCKED", {"current_password": self.lockout_message}
        user = self._reset_if_expired(user)
        stored = user.get("password_hash")
        current_ok = (isinstance(current_value, str) and 0 < len(current_value) <= PASSWORD_MAX
                    and security.is_known_hash(stored) and security.verify_password(current_value, stored))
        if not current_ok:
            _ctx, message = self._wrong_password(user, ip)
            if message == self.lockout_message:
                return "LOCKED", {"current_password": self.lockout_message}
            return "ERROR", {"current_password": MSG_CURRENT_PASSWORD}
        errors = {}
        problems = security.validate_password_policy(new) if isinstance(new, str) and len(new) <= PASSWORD_MAX \
            else [u"Informe a nova senha."]
        if problems:
            errors["new_password"] = problems[0]
        elif confirmation != new:
            errors["confirmation"] = MSG_CONFIRMATION
        if errors:
            return "ERROR", errors
        self._users.set_password(user["id"], security.hash_password(new), now,
                                     audit={"actor": user["login"], "ip": ip, "action": "UPDATE",
                                                "detail": u"senha alterada pelo próprio usuário"})
        self._log.info("senha alterada pelo proprio usuario (login=%s ip=%s)", user["login"], ip,
                       extra={"action": "UPDATE"})
        return "OK", {}

    # ----------------------------------------------------------------- logout

    def session_epoch(self, user_id):
        """sessao_epoch vigente do usuario, para a sessao nova depois da troca de senha (CR-008, E2)."""
        return self._users.get_session_state(user_id).get("session_epoch", 0)

    def logout(self, ctx, ip):
        """Encerra todas as sessoes do usuario (session_epoch + 1) e audita LOGOUT na mesma operacao."""
        if not ctx:
            return
        self._users.end_sessions(ctx["user_id"], audit=_aud(ctx["login"], ip, "LOGOUT", "Logout"))
        self._log.info("logout (login=%s ip=%s)", ctx["login"], ip, extra={"action": "LOGIN"})


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from sss.config import app_context
            from sss.persistence import repo_factory
            from sss.config import sss_logging
            factory = repo_factory
            cfg = app_context.require_config()
            _default = AuthService(
                users=factory.get("users"),
                rbac_repo=factory.get("rbac"),
                catalog=factory.get("catalog"),
                audit=factory.get("audit"),
                max_attempts=cfg.web.login_max_attempts,
                lockout_s=cfg.web.login_lockout_s,
                log=sss_logging.get_logger("sss_web", cfg),
            )
        return _default


def authenticate(login, password_value, ip):
    """Autentica pelo servico padrao do processo web."""
    return _service().authenticate(login, password_value, ip)


def revalidate(sessao, ip=None):
    """Revalida a sessao pelo servico padrao do processo web."""
    return _service().revalidate(sessao, ip)


def session_epoch(user_id):
    """sessao_epoch vigente pelo servico padrao do processo web."""
    return _service().session_epoch(user_id)


def logout(ctx, ip):
    """Audita o logout pelo servico padrao do processo web."""
    return _service().logout(ctx, ip)


def change_password(ctx, ip, current_value, new, confirmation):
    """Troca da propria senha pelo servico padrao do processo web."""
    return _service().change_password(ctx, ip, current_value, new, confirmation)


def lock_message():
    """Mensagem de conta bloqueada (com os minutos configurados) do servico padrao do processo web."""
    return _service().lockout_message
