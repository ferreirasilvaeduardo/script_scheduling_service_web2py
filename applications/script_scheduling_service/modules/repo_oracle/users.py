# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de usuarios (F7.3, AGENTS §4).

SQL estatico com binds, paginacao via ROWNUM, protecao de ultimo admin,
colunas de registro (CR-006) e revogacao de sessao via session_epoch (CR-008, E2).
"""
import copy
import datetime
import re

import db_conn
import repo_errors
from repo_oracle.base import (
    BaseRepoOracle,
    write_audit,
    translate_oracle_error,
    validate_record_actor,
)
from repo_users import RepoUsers

_RE_LOGIN = re.compile(r"^[a-z0-9._-]{3,30}$")

_COLS_USER = (
    "id",
    "login",
    "name",
    "password_hash",
    "profile_id",
    "failed_attempts",
    "locked_until",
    "last_login_at",
    "password_changed_at",
    "session_epoch",
    "active",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
)



def _failed_login_audit(audit, attempts, max_attempts, locked, lock_audit):
    """Itens de auditoria da falha de login: a contagem vem do valor lido sob a trava (mesma regra do FAKE)."""
    items = [] if not audit else ([audit] if isinstance(audit, dict) else list(audit))
    if max_attempts is not None:
        items = [dict(item, detail=u"%s (tentativa %d de %d)" % (item.get("detail") or u"", attempts,
                                                                    int(max_attempts)))
                 if isinstance(item, dict) and item.get("action") == "LOGIN_FAILED" else item for item in items]
    if locked and lock_audit:
        items.append(lock_audit)
    return items

class RepoUsersOracle(BaseRepoOracle, RepoUsers):
    """Repositorio de usuarios com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, secrets=None):
        super(RepoUsersOracle, self).__init__(cfg=cfg, secrets=secrets)

    def _tabela(self):
        return self.qualify_table("users")

    def _tabela_perfis(self):
        return self.qualify_table("profiles")

    def _tabela_auditoria(self):
        return self.qualify_table("audit")

    def _seq_usuarios(self):
        return self.qualify_sequence("users")

    def _seq_auditoria(self):
        return self.qualify_sequence("audit")

    def now(self):
        """Instante atual do banco (SYSDATE), sem microssegundos (README §4.2)."""
        with self.read_context() as conn:
            return db_conn.db_now(conn)

    def get_by_login(self, login, conn=None):
        """Retorna dict com dados do usuario ou None se nao encontrado."""
        sql = (
            "SELECT id, login, name, password_hash, profile_id, failed_attempts, locked_until, "
            "last_login_at, password_changed_at, session_epoch, active, "
            "created_at, created_by, updated_at, updated_by "
            "FROM " + self._tabela() + " WHERE login = :login"
        )
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql, {"login": login})
                row = cur.fetchone()
                if not row:
                    return None
                return self.tuple_to_dict(_COLS_USER, row)
            finally:
                cur.close()

    def get_by_id(self, id, conn=None):
        """Retorna dict com dados do usuario pelo ID ou lanca RepoNotFound."""
        sql = (
            "SELECT id, login, name, password_hash, profile_id, failed_attempts, locked_until, "
            "last_login_at, password_changed_at, session_epoch, active, "
            "created_at, created_by, updated_at, updated_by "
            "FROM " + self._tabela() + " WHERE id = :id"
        )
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql, {"id": int(id)})
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNotFound("Usuario ID %s nao encontrado" % id)
                return self.tuple_to_dict(_COLS_USER, row)
            finally:
                cur.close()

    def get_session_state(self, user_id, conn=None):
        """Retorna estado composto de sessao em uma query por PK (join usuario + perfil)."""
        sql = (
            "SELECT u.id, u.login, u.name, u.active, "
            "p.id, p.name, p.active, p.is_admin, p.perm_version, u.session_epoch "
            "FROM " + self._tabela() + " u "
            "JOIN " + self._tabela_perfis() + " p ON p.id = u.profile_id "
            "WHERE u.id = :user_id"
        )
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql, {"user_id": int(user_id)})
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNotFound("Usuario ID %s nao encontrado" % user_id)
                return {
                    "user_id": row[0],
                    "login": row[1],
                    "name": row[2],
                    "active_user": (row[3] or "").strip(),
                    "profile_id": row[4],
                    "profile_name": row[5],
                    "active_profile": (row[6] or "").strip(),
                    "is_admin": (row[7] or "").strip(),
                    "perm_version": row[8],
                    "session_epoch": row[9],
                }
            finally:
                cur.close()

    def list(self, filters=None, page=1, size=20, conn=None):
        """Lista usuarios paginados com desempate deterministico por id."""
        filters = filters or {}
        clauses = []
        binds = {}
        binds_date = {}

        login_f = filters.get("login")
        if login_f:
            clauses.append("LOWER(login) LIKE :login_f")
            binds["login_f"] = "%" + login_f.lower() + "%"

        name_f = filters.get("name")
        if name_f:
            clauses.append("LOWER(name) LIKE :name_f")
            binds["name_f"] = "%" + name_f.lower() + "%"

        profile_f = filters.get("profile_id")
        if profile_f is not None:
            clauses.append("profile_id = :profile_f")
            binds["profile_f"] = int(profile_f)

        active_f = filters.get("active")
        if active_f:
            clauses.append("active = :active_f")
            binds["active_f"] = str(active_f).strip().upper()

        locked_f = filters.get("locked_at")
        if locked_f is not None:
            clauses.append("locked_until IS NOT NULL AND locked_until > :locked_f")
            binds["locked_f"] = locked_f
            binds_date["locked_f"] = db_conn.TIPO_DATE

        where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""

        p = 1 if page is None else int(page)
        t = 20 if size is None else int(size)
        if p < 1:
            p = 1
        if t < 1:
            t = 20
        start = (p - 1) * t
        end = start + t

        sql_count = (
            "SELECT COUNT(*) FROM ("
            "SELECT id FROM " + self._tabela() + where_sql + " AND ROWNUM <= 10001"
            if where_sql
            else "SELECT COUNT(*) FROM (SELECT id FROM " + self._tabela() + " WHERE ROWNUM <= 10001"
        )
        sql_count += ")"

        sql_paged = (
            "SELECT * FROM ("
            "SELECT a.*, ROWNUM rn FROM ("
            "SELECT id, login, name, password_hash, profile_id, failed_attempts, locked_until, "
            "last_login_at, password_changed_at, session_epoch, active, "
            "created_at, created_by, updated_at, updated_by "
            "FROM " + self._tabela() + where_sql + " "
            "ORDER BY login ASC, id ASC"
            ") a WHERE ROWNUM <= :end_ts"
            ") WHERE rn > :start_ts"
        )

        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                if binds_date:
                    db_conn.set_input_types(cur, **binds_date)
                cur.execute(sql_count, binds)
                row_c = cur.fetchone()
                raw_count = row_c[0] if row_c else 0
                total = min(raw_count, 10001)
                total_capped = raw_count >= 10001

                binds_page = copy.deepcopy(binds)
                binds_page["start_ts"] = start
                binds_page["end_ts"] = end
                cur.execute(sql_paged, binds_page)
                items = [self.tuple_to_dict(_COLS_USER, r[:-1]) for r in cur.fetchall()]

                return {
                    "items": items,
                    "total": total,
                    "page": p,
                    "size": t,
                    "total_capped": total_capped,
                }
            finally:
                cur.close()

    def insert(self, date, audit=None, actor=None, conn=None):
        """Insere novo usuario com validacoes e auditoria na mesma transacao."""
        actor_clean = validate_record_actor(audit, actor)
        login = date.get("login")
        if not login or not isinstance(login, str) or not _RE_LOGIN.fullmatch(login):
            raise repo_errors.RepoViolation(
                "Login invalido (esperado: 3-30 caracteres [a-z0-9._-])",
                constraint=self.constraint_name("ck", "users", "login"),
            )

        active = str(date.get("active", "Y")).strip().upper()
        if active not in ("Y", "N"):
            raise repo_errors.RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint=self.constraint_name("ck", "users", "active"))

        attempts = int(date.get("failed_attempts", 0))
        if attempts < 0:
            raise repo_errors.RepoViolation(
                "Tentativas falhas nao podem ser negativas", constraint=self.constraint_name("ck", "users", "att")
            )

        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                # Checa duplicidade do login
                cur.execute("SELECT id FROM " + self._tabela() + " WHERE login = :login", {"login": login})
                if cur.fetchone():
                    raise repo_errors.RepoViolation("Login '%s' ja existe" % login, constraint=self.constraint_name("uk", "users", "login"))

                profile_id = date.get("profile_id")
                cur.execute("SELECT id FROM " + self._tabela_perfis() + " WHERE id = :pid", {"pid": int(profile_id)})
                if not cur.fetchone():
                    raise repo_errors.RepoViolation("Perfil ID %s nao existe" % profile_id, constraint=self.constraint_name("fk", "users", "prf"))

                uid = db_conn.next_id(c, self._seq_usuarios())
                sql_ins = (
                    "INSERT INTO " + self._tabela() + " "
                    "(id, login, name, password_hash, profile_id, failed_attempts, "
                    "locked_until, last_login_at, password_changed_at, session_epoch, active, "
                    "created_at, created_by, updated_at, updated_by) "
                    "VALUES (:id, :login, :name, :password_hash, :profile_id, :failed_attempts, "
                    ":locked_until, :last_login_at, :password_changed_at, 0, :active, "
                    "NVL(:created_at, SYSDATE), :actor, NULL, NULL)"
                )
                db_conn.set_input_types(
                    cur,
                    locked_until=db_conn.TIPO_DATE,
                    last_login_at=db_conn.TIPO_DATE,
                    password_changed_at=db_conn.TIPO_DATE,
                    created_at=db_conn.TIPO_DATE,
                )
                cur.execute(
                    sql_ins,
                    {
                        "id": uid,
                        "login": login,
                        "name": date.get("name", ""),
                        "password_hash": date.get("password_hash", "!"),
                        "profile_id": int(profile_id),
                        "failed_attempts": attempts,
                        "locked_until": date.get("locked_until"),
                        "last_login_at": date.get("last_login_at"),
                        "password_changed_at": date.get("password_changed_at"),
                        "active": active,
                        "created_at": date.get("created_at"),
                        "actor": actor_clean,
                    },
                )
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), audit, "tbsss_users", uid)
            finally:
                cur.close()

            return self.get_by_id(uid, conn=c)

    def update(self, id, date, expected=None, audit=None, actor=None, conn=None):
        """Altera usuario (login imutavel) com protecao do ultimo admin (README §4.3.B)."""
        actor_clean = validate_record_actor(audit, actor)
        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(
                    "SELECT u.id, u.login, u.name, u.password_hash, u.profile_id, u.failed_attempts, "
                    "u.locked_until, u.last_login_at, u.password_changed_at, u.session_epoch, u.active, "
                    "u.created_at, u.created_by, u.updated_at, u.updated_by, "
                    "p.active, p.is_admin "
                    "FROM " + self._tabela() + " u "
                    "JOIN " + self._tabela_perfis() + " p ON p.id = u.profile_id "
                    "WHERE u.id = :id FOR UPDATE OF u.active WAIT 5",
                    {"id": int(id)},
                )
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNotFound("Usuario ID %s nao encontrado" % id)

                current = self.tuple_to_dict(_COLS_USER, row[:15])
                p_current_active = (row[15] or "").strip()
                p_current_is_admin = (row[16] or "").strip()

                for field, expected_val in (expected or {}).items():
                    val_current = current.get(field)
                    if isinstance(val_current, datetime.datetime) and isinstance(expected_val, datetime.datetime):
                        if val_current.replace(microsecond=0) != expected_val.replace(microsecond=0):
                            raise repo_errors.RepoConflict("Usuario ID %s alterado por outra operacao (%s)" % (id, field))
                    elif val_current != expected_val:
                        raise repo_errors.RepoConflict("Usuario ID %s alterado por outra operacao (%s)" % (id, field))

                new_login = date.get("login")
                if new_login is not None and new_login != current["login"]:
                    raise repo_errors.RepoViolation("Login de usuario e imutavel", constraint=self.trigger_name("users", "bu"))

                new_profile = date.get("profile_id")
                profile_changed = False
                p_new_active = p_current_active
                p_new_is_admin = p_current_is_admin
                if new_profile is not None:
                    new_profile = int(new_profile)
                    if new_profile != current["profile_id"]:
                        cur.execute(
                            "SELECT active, is_admin FROM " + self._tabela_perfis() + " WHERE id = :pid",
                            {"pid": new_profile},
                        )
                        row_p = cur.fetchone()
                        if not row_p:
                            raise repo_errors.RepoViolation("Perfil ID %s nao existe" % new_profile, constraint=self.constraint_name("fk", "users", "prf"))
                        p_new_active = (row_p[0] or "").strip()
                        p_new_is_admin = (row_p[1] or "").strip()
                        profile_changed = True

                new_active = date.get("active")
                active_changed = False
                if new_active is not None:
                    new_active = str(new_active).strip().upper()
                    if new_active not in ("Y", "N"):
                        raise repo_errors.RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint=self.constraint_name("ck", "users", "active"))
                    if new_active != current["active"]:
                        active_changed = True

                # Protecao do ultimo administrador (README §4.3.B)
                was_admin_active = (
                    current["active"] == "Y" and p_current_active == "Y" and p_current_is_admin == "Y"
                )
                will_be_admin_active = (
                    (new_active if new_active is not None else current["active"]) == "Y"
                    and p_new_active == "Y"
                    and p_new_is_admin == "Y"
                )

                if was_admin_active and not will_be_admin_active:
                    cur.execute(
                        "SELECT u.id "
                        "FROM " + self._tabela() + " u "
                        "JOIN " + self._tabela_perfis() + " p ON p.id = u.profile_id "
                        "WHERE u.active = 'Y' AND p.active = 'Y' AND p.is_admin = 'Y' "
                        # Trava tambem os perfis: quem espera releia o is_admin alterado por outra
                        # transacao, e duas operacoes simultaneas nao deixam o sistema sem admin.
                        "FOR UPDATE OF u.active, p.is_admin WAIT 5"
                    )
                    admins_remaining = [r[0] for r in cur.fetchall() if r[0] != int(id)]
                    if not admins_remaining:
                        raise repo_errors.RepoViolation(
                            "Operacao deixaria o sistema sem administrador ativo",
                            constraint="sss_ultimo_admin",
                        )

                sets = [
                    "name = :name",
                    "profile_id = :profile_id",
                    "active = :active",
                    "updated_at = SYSDATE",
                    "updated_by = :actor",
                ]
                params = {
                    "id": int(id),
                    "name": date.get("name", current["name"]),
                    "profile_id": new_profile if new_profile is not None else current["profile_id"],
                    "active": new_active if new_active is not None else current["active"],
                    "actor": actor_clean,
                }
                if "password_hash" in date:
                    sets.append("password_hash = :password_hash")
                    params["password_hash"] = date["password_hash"]
                if "failed_attempts" in date:
                    attempts = int(date["failed_attempts"])
                    if attempts < 0:
                        raise repo_errors.RepoViolation(
                            "Tentativas falhas nao podem ser negativas", constraint=self.constraint_name("ck", "users", "att")
                        )
                    sets.append("failed_attempts = :failed_attempts")
                    params["failed_attempts"] = attempts
                if "locked_until" in date:
                    sets.append("locked_until = :locked_until")
                    params["locked_until"] = date["locked_until"]
                if "last_login_at" in date:
                    sets.append("last_login_at = :last_login_at")
                    params["last_login_at"] = date["last_login_at"]
                if "password_changed_at" in date:
                    sets.append("password_changed_at = :password_changed_at")
                    params["password_changed_at"] = date["password_changed_at"]

                if profile_changed or active_changed:
                    sets.append("session_epoch = session_epoch + 1")

                sql_upd = "UPDATE " + self._tabela() + " SET " + ", ".join(sets) + " WHERE id = :id"
                # So os binds de data presentes no SET: o python-oracledb recusa tipo declarado para bind
                # ausente do SQL (DPY-4008), o que quebrava toda alteracao sem data (F7.3, bateria integrada).
                kinds = dict((c, db_conn.TIPO_DATE) for c in ("locked_until", "last_login_at", "password_changed_at")
                             if c in params)
                if kinds:
                    db_conn.set_input_types(cur, **kinds)
                cur.execute(sql_upd, params)

                # Incrementa perm_versao do perfil de origem e destino se aplicavel
                if profile_changed or active_changed:
                    p_source = current["profile_id"]
                    p_destination = new_profile if new_profile is not None else p_source
                    cur.execute(
                        "UPDATE " + self._tabela_perfis() + " "
                        "SET perm_version = perm_version + 1 "
                        "WHERE id = :source",
                        {"source": p_source},
                    )
                    if p_destination != p_source:
                        cur.execute(
                            "UPDATE " + self._tabela_perfis() + " "
                            "SET perm_version = perm_version + 1 "
                            "WHERE id = :target",
                            {"target": p_destination},
                        )

                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), audit, "tbsss_users", int(id))
            finally:
                cur.close()

            return self.get_by_id(id, conn=c)

    def register_login_failure(self, login, lockout_s=None, audit=None, max_attempts=None,
                              lock_audit=None, conn=None):
        """Incrementa tentativas_falha e decide o bloqueio sob a trava da linha (contrato em RepoUsers).

        Rotina tecnica, sem updated_*. A contagem usada e a lida com a linha travada: tentativas
        paralelas de login nunca escapam do limite (revisao de 2026-10-20).
        """
        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(
                    "SELECT id, failed_attempts FROM " + self._tabela() + " WHERE login = :login FOR UPDATE WAIT 5",
                    {"login": login},
                )
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNotFound("Usuario com login '%s' nao encontrado" % login)

                uid, attempts = row[0], int(row[1] or 0)
                if attempts + 1 > 99:
                    raise repo_errors.RepoViolation("tentativas_falha excede NUMBER(2)", constraint=self.constraint_name("ck", "users", "att"))
                if max_attempts is not None:
                    lock = attempts + 1 >= int(max_attempts)
                else:
                    lock = lockout_s is not None

                if lock:
                    cur.execute(
                        "UPDATE " + self._tabela() + " "
                        "SET failed_attempts = failed_attempts + 1, "
                        "locked_until = SYSDATE + :lockout_s / 86400 "
                        "WHERE id = :id",
                        {"id": uid, "lockout_s": int(lockout_s)},
                    )
                else:
                    cur.execute(
                        "UPDATE " + self._tabela() + " "
                        "SET failed_attempts = failed_attempts + 1 "
                        "WHERE id = :id",
                        {"id": uid},
                    )
                items = _failed_login_audit(audit, attempts + 1, max_attempts, lock, lock_audit)
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), items, "tbsss_users", uid)
            finally:
                cur.close()

            record = self.get_by_id(uid, conn=c)
            record["locked_now"] = bool(lock)
            return record

    def register_login_success(self, login, new_hash=None, audit=None, conn=None):
        """Zera falhas e grava ultimo_login (rotina tecnica, sem updated_*)."""
        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(
                    "SELECT id FROM " + self._tabela() + " WHERE login = :login FOR UPDATE WAIT 5",
                    {"login": login},
                )
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNotFound("Usuario com login '%s' nao encontrado" % login)
                uid = row[0]

                if new_hash is not None:
                    cur.execute(
                        "UPDATE " + self._tabela() + " "
                        "SET failed_attempts = 0, locked_until = NULL, last_login_at = SYSDATE, password_hash = :h "
                        "WHERE id = :id",
                        {"id": uid, "h": new_hash},
                    )
                else:
                    cur.execute(
                        "UPDATE " + self._tabela() + " "
                        "SET failed_attempts = 0, locked_until = NULL, last_login_at = SYSDATE "
                        "WHERE id = :id",
                        {"id": uid},
                    )
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), audit, "tbsss_users", uid)
            finally:
                cur.close()

            return self.get_by_id(uid, conn=c)

    def unlock(self, id, audit=None, actor=None, conn=None):
        """Desbloqueia conta de usuario zerando tentativas (grava updated_*)."""
        actor_clean = validate_record_actor(audit, actor)
        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute("SELECT id FROM " + self._tabela() + " WHERE id = :id FOR UPDATE WAIT 5", {"id": int(id)})
                if not cur.fetchone():
                    raise repo_errors.RepoNotFound("Usuario ID %s nao encontrado" % id)

                cur.execute(
                    "UPDATE " + self._tabela() + " "
                    "SET failed_attempts = 0, locked_until = NULL, updated_at = SYSDATE, updated_by = :actor "
                    "WHERE id = :id",
                    {"id": int(id), "actor": actor_clean},
                )
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), audit, "tbsss_users", int(id))
            finally:
                cur.close()

            return self.get_by_id(id, conn=c)

    def reset_attempts(self, id, conn=None):
        """Rotina tecnica do login: bloqueio vencido zera contadores sem updated_* nem auditoria."""
        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute("SELECT id FROM " + self._tabela() + " WHERE id = :id FOR UPDATE WAIT 5", {"id": int(id)})
                if not cur.fetchone():
                    raise repo_errors.RepoNotFound("Usuario ID %s nao encontrado" % id)

                cur.execute(
                    "UPDATE " + self._tabela() + " "
                    "SET failed_attempts = 0, locked_until = NULL "
                    "WHERE id = :id",
                    {"id": int(id)},
                )
            finally:
                cur.close()

            return self.get_by_id(id, conn=c)

    def set_password(self, id, password_hash, now=None, audit=None, actor=None, conn=None):
        """Atualiza a senha do usuario e incrementa session_epoch (grava updated_*)."""
        actor_clean = validate_record_actor(audit, actor)
        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute("SELECT id FROM " + self._tabela() + " WHERE id = :id FOR UPDATE WAIT 5", {"id": int(id)})
                if not cur.fetchone():
                    raise repo_errors.RepoNotFound("Usuario ID %s nao encontrado" % id)

                sql = (
                    "UPDATE " + self._tabela() + " "
                    "SET password_hash = :password_hash, "
                    "password_changed_at = NVL(:now, SYSDATE), "
                    "failed_attempts = 0, locked_until = NULL, "
                    "session_epoch = session_epoch + 1, "
                    "updated_at = SYSDATE, updated_by = :actor "
                    "WHERE id = :id"
                )
                db_conn.set_input_types(cur, now=db_conn.TIPO_DATE)
                cur.execute(sql, {"id": int(id), "password_hash": password_hash, "now": now, "actor": actor_clean})
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), audit, "tbsss_users", int(id))
            finally:
                cur.close()

            return self.get_by_id(id, conn=c)

    def end_sessions(self, id, audit=None, conn=None):
        """Logout: incrementa session_epoch (rotina tecnica, sem updated_*)."""
        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute("SELECT id FROM " + self._tabela() + " WHERE id = :id FOR UPDATE WAIT 5", {"id": int(id)})
                if not cur.fetchone():
                    raise repo_errors.RepoNotFound("Usuario ID %s nao encontrado" % id)

                cur.execute(
                    "UPDATE " + self._tabela() + " "
                    "SET session_epoch = session_epoch + 1 "
                    "WHERE id = :id",
                    {"id": int(id)},
                )
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), audit, "tbsss_users", int(id))
            finally:
                cur.close()

            return self.get_by_id(id, conn=c)
