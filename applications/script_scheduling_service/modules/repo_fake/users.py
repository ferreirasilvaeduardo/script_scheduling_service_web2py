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
    itens = [] if not audit else ([audit] if isinstance(audit, dict) else list(audit))
    if max_attempts is not None:
        itens = [dict(item, detail=u"%s (tentativa %d de %d)" % (item.get("detail") or u"", attempts,
                                                                    int(max_attempts)))
                 if isinstance(item, dict) and item.get("action") == "LOGIN_FAILED" else item for item in itens]
    if locked and lock_audit:
        itens.append(lock_audit)
    return itens

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
        """Retorna estado composto de sessao (usuario + perfil + perm_versao)."""
        with self._store.lock_rbac:
            with self._store.lock_users:
                if user_id not in self._store.users:
                    raise RepoNotFound("Usuario ID %s nao encontrado" % user_id)
                u = self._store.users[user_id]
                perfil_id = u["profile_id"]
                if perfil_id not in self._store.profiles:
                    raise RepoNotFound("Perfil ID %s nao encontrado" % perfil_id)
                p = self._store.profiles[perfil_id]

                return {
                    "user_id": u["id"],
                    "login": u["login"],
                    "name": u["name"],
                    "usuario_ativo": u["active"],
                    "profile_id": p["id"],
                    "perfil_nome": p["name"],
                    "perfil_ativo": p["active"],
                    "is_admin": p["is_admin"],
                    "perm_version": p["perm_version"],
                    "session_epoch": u.get("session_epoch", 0),
                }

    def list(self, filters=None, page=1, size=20):
        """Lista usuarios paginados com desempate por id."""
        filters = filters or {}
        with self._store.lock_users:
            lista = list(self._store.users.values())

            login_f = filters.get("login")
            if login_f:
                lista = [u for u in lista if login_f.lower() in u["login"].lower()]

            nome_f = filters.get("name")
            if nome_f:
                lista = [u for u in lista if nome_f.lower() in u["name"].lower()]

            perfil_f = filters.get("profile_id")
            if perfil_f is not None:
                lista = [u for u in lista if u["profile_id"] == int(perfil_f)]

            ativo_f = filters.get("active")
            if ativo_f:
                lista = [u for u in lista if u["active"] == ativo_f]

            bloq_f = filters.get("bloqueado_em")
            if bloq_f is not None:
                lista = [u for u in lista if u.get("locked_until") is not None and u["locked_until"] > bloq_f]

            # Ordenacao estavel: login ASC, id ASC
            lista.sort(key=lambda x: (x.get("login", ""), x["id"]))
            return paginate(lista, page=page, size=size)

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
        # Ordem de locks unica no FAKE: rbac e depois usuarios (como admins_ativos_bloquear).
        with self._store.lock_rbac:
            with self._store.lock_users:
                actor = self._store.record_actor(audit, actor)
                login = date.get("login")
                if not login or not _RE_LOGIN.fullmatch(login):
                    raise RepoViolation("Login invalido (esperado: 3-30 caracteres [a-z0-9._-])", constraint="ck_tbsss_usr_login")

                for u in self._store.users.values():
                    if u["login"] == login:
                        raise RepoViolation("Login '%s' ja existe" % login, constraint="uk_tbsss_usr_login")

                perfil_id = date.get("profile_id")
                if perfil_id not in self._store.profiles:
                    raise RepoViolation("Perfil ID %s nao existe" % perfil_id, constraint="fk_tbsss_usr_prf")

                ativo = date.get("active", "Y")
                if ativo not in ("Y", "N"):
                    raise RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_usr_active")

                tentativas = int(date.get("failed_attempts", 0))
                if tentativas < 0:
                    raise RepoViolation("Tentativas falhas nao podem ser negativas", constraint="ck_tbsss_usr_att")

                uid = self._store.next_id("tbsss_users")
                novo = {
                    "id": uid,
                    "login": login,
                    "name": date.get("name", ""),
                    "password_hash": date.get("password_hash", "!"),
                    "profile_id": perfil_id,
                    "failed_attempts": tentativas,
                    "locked_until": date.get("locked_until"),
                    "last_login_at": date.get("last_login_at"),
                    "password_changed_at": date.get("password_changed_at"),
                    "session_epoch": 0,
                    "active": ativo,
                    "created_at": date.get("created_at"),
                }
                self._store.stamp_insert(novo, actor)
                self._store.users[uid] = copy.deepcopy(novo)
                self._auditar(audit, uid)
                return copy.deepcopy(novo)

    def update(self, id, date, expected=None, audit=None, actor=None):
        """Altera usuario (login imutavel), condicional a 'esperado' e com protecao do ultimo admin."""
        with self._store.lock_rbac:
            with self._store.lock_users:
                actor = self._store.record_actor(audit, actor)
                if id not in self._store.users:
                    raise RepoNotFound("Usuario ID %s nao encontrado" % id)

                atual = self._store.users[id]
                for campo, valor in (expected or {}).items():
                    if atual.get(campo) != valor:
                        raise RepoConflict("Usuario ID %s alterado por outra operacao (%s)" % (id, campo))

                # Imutabilidade do login (README §10 trigger tr_tbsss_usr_bu)
                novo_login = date.get("login")
                if novo_login is not None and novo_login != atual["login"]:
                    raise RepoViolation("Login de usuario e imutavel", constraint="tr_tbsss_usr_bu")

                novo_perfil = date.get("profile_id")
                if novo_perfil is not None and novo_perfil not in self._store.profiles:
                    raise RepoViolation("Perfil ID %s nao existe" % novo_perfil, constraint="fk_tbsss_usr_prf")
                perfil_alterado = novo_perfil is not None and novo_perfil != atual["profile_id"]

                novo_ativo = date.get("active")
                if novo_ativo is not None and novo_ativo not in ("Y", "N"):
                    raise RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_usr_active")
                ativo_alterado = novo_ativo is not None and novo_ativo != atual["active"]

                mudancas = dict((k, v) for k, v in date.items()
                                if k in ("name", "profile_id", "password_hash", "failed_attempts", "locked_until",
                                         "last_login_at", "password_changed_at", "active"))
                if int(mudancas.get("failed_attempts", 0) or 0) < 0:
                    raise RepoViolation("Tentativas falhas nao podem ser negativas", constraint="ck_tbsss_usr_att")

                # README §4.3.B: lock dos admins e validacao do conjunto resultante na mesma operacao.
                if self._eh_admin_ativo(atual) and not self._eh_admin_ativo(dict(atual, **mudancas)):
                    restantes = [u for uid, u in self._store.users.items()
                                 if uid != id and self._eh_admin_ativo(u)]
                    if not restantes:
                        raise RepoViolation("Operacao deixaria o sistema sem administrador ativo",
                                           constraint="sss_ultimo_admin")

                anterior = atual["profile_id"]
                atual.update(mudancas)
                if perfil_alterado or ativo_alterado:
                    _revoke_sessions(atual)
                self._store.stamp_update(atual, actor)

                # Incrementa perm_versao do perfil se houver alteracao de perfil ou ativo
                if perfil_alterado or ativo_alterado:
                    if anterior in self._store.profiles:
                        self._store.profiles[anterior]["perm_version"] += 1
                    if perfil_alterado:
                        self._store.profiles[novo_perfil]["perm_version"] += 1

                self._auditar(audit, id)
                return copy.deepcopy(atual)

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
            tentativas = int(u.get("failed_attempts", 0)) + 1
            if tentativas > 99:
                raise RepoViolation("tentativas_falha excede NUMBER(2)", constraint="ck_tbsss_usr_att")
            bloquear = (tentativas >= int(max_attempts)) if max_attempts is not None else lockout_s is not None
            u["failed_attempts"] = tentativas
            if bloquear:
                u["locked_until"] = self._store.now() + datetime.timedelta(seconds=int(lockout_s))
            self._auditar(_failed_login_audit(audit, tentativas, max_attempts, bloquear, lock_audit),
                          u["id"])
            registro = copy.deepcopy(u)
            registro["bloqueou"] = bool(bloquear)
            return registro

    def register_login_success(self, login, new_hash=None, audit=None):
        """Zera falhas, grava ultimo_login (SYSDATE) e o rehash, com a auditoria, numa operacao."""
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
    novo = int(user.get("session_epoch") or 0) + 1
    if novo > 9999999999:
        raise RepoViolation("sessao_epoch excede NUMBER(10)", constraint="ck_tbsss_usr_epoch")
    user["session_epoch"] = novo
