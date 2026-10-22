# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de usuarios (README §2.5, §4.2, §10)."""
import copy
import datetime
import re

from repo_errors import RepoConflict, RepoNotFound, RepoViolation
from repo_fake.store import paginate
from repo_users import RepoUsers

_RE_LOGIN = re.compile(r"^[a-z0-9._-]{3,30}$")



def _failed_login_audit(audit, attempts, max_attempts, locked, lock_audit):
    """Itens de auditoria da falha de login: a contagem vem do valor lido sob o lock (mesma regra do Oracle)."""
    items = [] if not audit else ([audit] if isinstance(audit, dict) else list(audit))
    if max_attempts is not None:
        items = [dict(item, detail=u"%s (tentativa %d de %d)" % (item.get("detail") or u"", attempts,
                                                                    int(max_attempts)))
                 if isinstance(item, dict) and item.get("action") == "LOGIN_FAILED" else item for item in items]
    if locked and lock_audit:
        items.append(lock_audit)
    return items

class RepoUsersFake(RepoUsers):
    """Implementacao em memoria com semantica Oracle para usuarios."""

    def __init__(self, store):
        self._store = store

    def get_by_login(self, login):
        """Retorna dict com dados do usuario ou None se nao encontrado."""
        with self._store.lock_users:
            for u in self._store.users.values():
                if u["login"] == login:
                    return copy.deepcopy(u)
            return None

    def get_by_id(self, id):
        """Retorna dict com dados do usuario pelo ID ou lanca RepoNotFound."""
        with self._store.lock_users:
            if id not in self._store.users:
                raise RepoNotFound("Usuario ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.users[id])

    def get_session_state(self, user_id):
        """Retorna estado composto de sessao (usuario + perfil + perm_version)."""
        with self._store.lock_rbac:
            with self._store.lock_users:
                if user_id not in self._store.users:
                    raise RepoNotFound("Usuario ID %s nao encontrado" % user_id)
                u = self._store.users[user_id]
                profile_id = u["profile_id"]
                if profile_id not in self._store.profiles:
                    raise RepoNotFound("Perfil ID %s nao encontrado" % profile_id)
                p = self._store.profiles[profile_id]

                return {
                    "user_id": u["id"],
                    "login": u["login"],
                    "name": u["name"],
                    "active_user": u["active"],
                    "profile_id": p["id"],
                    "profile_name": p["name"],
                    "active_profile": p["active"],
                    "is_admin": p["is_admin"],
                    "perm_version": p["perm_version"],
                    "session_epoch": u.get("session_epoch", 0),
                }

    def list(self, filters=None, page=1, size=20):
        """Lista usuarios paginados com desempate por id."""
        filters = filters or {}
        with self._store.lock_users:
            items = list(self._store.users.values())

            login_f = filters.get("login")
            if login_f:
                items = [u for u in items if login_f.lower() in u["login"].lower()]

            name_f = filters.get("name")
            if name_f:
                items = [u for u in items if name_f.lower() in u["name"].lower()]

            profile_f = filters.get("profile_id")
            if profile_f is not None:
                items = [u for u in items if u["profile_id"] == int(profile_f)]

            active_f = filters.get("active")
            if active_f:
                items = [u for u in items if u["active"] == active_f]

            locked_f = filters.get("locked_at")
            if locked_f is not None:
                items = [u for u in items if u.get("locked_until") is not None and u["locked_until"] > locked_f]

            # Ordenacao estavel: login ASC, id ASC
            items.sort(key=lambda x: (x.get("login", ""), x["id"]))
            return paginate(items, page=page, size=size)

    def _auditar(self, audit, user_id):
        for item in ([audit] if isinstance(audit, dict) else (audit or ())):
            self._store.register_internal_audit(
                actor=item.get("actor"),
                ip=item.get("ip"),
                action=item["action"],
                entity="tbsss_users",
                entity_id=user_id,
                detail=item.get("detail"),
            )

    def now(self):
        """SYSDATE simulado pelo relogio do store."""
        return self._store.now()

    def _eh_admin_ativo(self, user):
        p = self._store.profiles.get(user["profile_id"])
        return user["active"] == "Y" and p is not None and p["active"] == "Y" and p["is_admin"] == "Y"

    def insert(self, date, audit=None, actor=None):
        """Insere novo usuario com validacoes de integridade, auditando na mesma operacao."""
        # Ordem de locks unica no FAKE: rbac e depois usuarios (como lock_active_admins).
        with self._store.lock_rbac:
            with self._store.lock_users:
                actor = self._store.record_actor(audit, actor)
                login = date.get("login")
                if not login or not _RE_LOGIN.fullmatch(login):
                    raise RepoViolation("Login invalido (esperado: 3-30 caracteres [a-z0-9._-])", constraint="ck_tbsss_usr_login")

                for u in self._store.users.values():
                    if u["login"] == login:
                        raise RepoViolation("Login '%s' ja existe" % login, constraint="uk_tbsss_usr_login")

                profile_id = date.get("profile_id")
                if profile_id not in self._store.profiles:
                    raise RepoViolation("Perfil ID %s nao existe" % profile_id, constraint="fk_tbsss_usr_prf")

                active = date.get("active", "Y")
                if active not in ("Y", "N"):
                    raise RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_usr_active")

                attempts = int(date.get("failed_attempts", 0))
                if attempts < 0:
                    raise RepoViolation("Tentativas falhas nao podem ser negativas", constraint="ck_tbsss_usr_att")

                uid = self._store.next_id("tbsss_users")
                new = {
                    "id": uid,
                    "login": login,
                    "name": date.get("name", ""),
                    "password_hash": date.get("password_hash", "!"),
                    "profile_id": profile_id,
                    "failed_attempts": attempts,
                    "locked_until": date.get("locked_until"),
                    "last_login_at": date.get("last_login_at"),
                    "password_changed_at": date.get("password_changed_at"),
                    "session_epoch": 0,
                    "active": active,
                    "created_at": date.get("created_at"),
                }
                self._store.stamp_insert(new, actor)
                self._store.users[uid] = copy.deepcopy(new)
                self._auditar(audit, uid)
                return copy.deepcopy(new)

    def update(self, id, date, expected=None, audit=None, actor=None):
        """Altera usuario (login imutavel), condicional a 'esperado' e com protecao do ultimo admin."""
        with self._store.lock_rbac:
            with self._store.lock_users:
                actor = self._store.record_actor(audit, actor)
                if id not in self._store.users:
                    raise RepoNotFound("Usuario ID %s nao encontrado" % id)

                current = self._store.users[id]
                for field, value in (expected or {}).items():
                    if current.get(field) != value:
                        raise RepoConflict("Usuario ID %s alterado por outra operacao (%s)" % (id, field))

                # Imutabilidade do login (README §10 trigger tr_tbsss_usr_bu)
                new_login = date.get("login")
                if new_login is not None and new_login != current["login"]:
                    raise RepoViolation("Login de usuario e imutavel", constraint="tr_tbsss_usr_bu")

                new_profile = date.get("profile_id")
                if new_profile is not None and new_profile not in self._store.profiles:
                    raise RepoViolation("Perfil ID %s nao existe" % new_profile, constraint="fk_tbsss_usr_prf")
                profile_changed = new_profile is not None and new_profile != current["profile_id"]

                new_active = date.get("active")
                if new_active is not None and new_active not in ("Y", "N"):
                    raise RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_usr_active")
                active_changed = new_active is not None and new_active != current["active"]

                changes = dict((k, v) for k, v in date.items()
                                if k in ("name", "profile_id", "password_hash", "failed_attempts", "locked_until",
                                         "last_login_at", "password_changed_at", "active"))
                if int(changes.get("failed_attempts", 0) or 0) < 0:
                    raise RepoViolation("Tentativas falhas nao podem ser negativas", constraint="ck_tbsss_usr_att")

                # README §4.3.B: lock dos admins e validacao do conjunto resultante na mesma operacao.
                if self._eh_admin_ativo(current) and not self._eh_admin_ativo(dict(current, **changes)):
                    remaining = [u for uid, u in self._store.users.items()
                                 if uid != id and self._eh_admin_ativo(u)]
                    if not remaining:
                        raise RepoViolation("Operacao deixaria o sistema sem administrador ativo",
                                           constraint="sss_ultimo_admin")

                previous = current["profile_id"]
                current.update(changes)
                if profile_changed or active_changed:
                    _revoke_sessions(current)
                self._store.stamp_update(current, actor)

                # Incrementa perm_version do perfil se houver alteracao de perfil ou ativo
                if profile_changed or active_changed:
                    if previous in self._store.profiles:
                        self._store.profiles[previous]["perm_version"] += 1
                    if profile_changed:
                        self._store.profiles[new_profile]["perm_version"] += 1

                self._auditar(audit, id)
                return copy.deepcopy(current)

    def _por_login(self, login):
        for u in self._store.users.values():
            if u["login"] == login:
                return u
        raise RepoNotFound("Usuario com login '%s' nao encontrado" % login)

    def register_login_failure(self, login, lockout_s=None, audit=None, max_attempts=None,
                              lock_audit=None):
        """Incrementa as falhas e decide o bloqueio sob o lock (contrato em RepoUsers); auditoria junto."""
        with self._store.lock_users:
            u = self._por_login(login)
            attempts = int(u.get("failed_attempts", 0)) + 1
            if attempts > 99:
                raise RepoViolation("tentativas_falha excede NUMBER(2)", constraint="ck_tbsss_usr_att")
            lock = (attempts >= int(max_attempts)) if max_attempts is not None else lockout_s is not None
            u["failed_attempts"] = attempts
            if lock:
                u["locked_until"] = self._store.now() + datetime.timedelta(seconds=int(lockout_s))
            self._auditar(_failed_login_audit(audit, attempts, max_attempts, lock, lock_audit),
                          u["id"])
            record = copy.deepcopy(u)
            record["locked_now"] = bool(lock)
            return record

    def register_login_success(self, login, new_hash=None, audit=None):
        """Zera falhas, grava last_login_at (SYSDATE) e o rehash, com a auditoria, numa operacao."""
        with self._store.lock_users:
            u = self._por_login(login)
            u["failed_attempts"] = 0
            u["locked_until"] = None
            u["last_login_at"] = self._store.now()
            if new_hash is not None:
                u["password_hash"] = new_hash
            self._auditar(audit, u["id"])
            return copy.deepcopy(u)

    def unlock(self, id, audit=None, actor=None):
        """Desbloqueia conta de usuario zerando tentativas (alteracao de negocio: grava updated_*)."""
        with self._store.lock_users:
            actor = self._store.record_actor(audit, actor)
            if id not in self._store.users:
                raise RepoNotFound("Usuario ID %s nao encontrado" % id)
            u = self._store.users[id]
            u["failed_attempts"] = 0
            u["locked_until"] = None
            self._store.stamp_update(u, actor)
            self._auditar(audit, id)
            return copy.deepcopy(u)

    def reset_attempts(self, id):
        """Bloqueio vencido: novo ciclo de tentativas, sem updated_* nem auditoria (rotina tecnica)."""
        with self._store.lock_users:
            if id not in self._store.users:
                raise RepoNotFound("Usuario ID %s nao encontrado" % id)
            u = self._store.users[id]
            u["failed_attempts"] = 0
            u["locked_until"] = None
            return copy.deepcopy(u)

    def set_password(self, id, password_hash, now=None, audit=None, actor=None):
        """Atualiza a senha do usuario e zera contadores de bloqueio (grava updated_*)."""
        with self._store.lock_users:
            actor = self._store.record_actor(audit, actor)
            if id not in self._store.users:
                raise RepoNotFound("Usuario ID %s nao encontrado" % id)
            u = self._store.users[id]
            u["password_hash"] = password_hash
            u["password_changed_at"] = now or self._store.now()
            u["failed_attempts"] = 0
            u["locked_until"] = None
            _revoke_sessions(u)
            self._store.stamp_update(u, actor)
            self._auditar(audit, id)
            return copy.deepcopy(u)

    def end_sessions(self, id, audit=None):
        """Logout: incrementa session_epoch (rotina tecnica, sem updated_*), com a auditoria na mesma operacao."""
        with self._store.lock_users:
            if id not in self._store.users:
                raise RepoNotFound("Usuario ID %s nao encontrado" % id)
            u = self._store.users[id]
            _revoke_sessions(u)
            self._auditar(audit, id)
            return copy.deepcopy(u)


def _revoke_sessions(user):
    """Incrementa session_epoch: todas as sessoes abertas do usuario deixam de valer (CR-008, E2)."""
    new = int(user.get("session_epoch") or 0) + 1
    if new > 9999999999:
        raise RepoViolation("sessao_epoch excede NUMBER(10)", constraint="ck_tbsss_usr_epoch")
    user["session_epoch"] = new
