# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de RBAC e perfis (F7.3, AGENTS §4).

SQL estatico com binds, paginacao via ROWNUM, protecao de ultimo admin,
matriz por diferenca com preservacao de created_* (CR-006, R-f) e versao de permissao.
"""
import copy
import datetime

from sss.persistence import db_conn
from sss.persistence import repo_errors
from sss.persistence.oracle.base import (
                                         BaseRepoOracle,
                                         write_audit,
                                         translate_oracle_error,
                                         validate_record_actor,
                                         )
from sss.persistence.contracts.repo_rbac import RepoRbac

_COLS_PROFILE = (
    "id",
    "name",
    "description",
    "is_admin",
    "perm_version",
    "active",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
)

_COLS_FUNC = (
    "id",
    "code",
    "name",
    "module",
    "description",
    "active",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
)


class RepoRbacOracle(BaseRepoOracle, RepoRbac):
    """Repositorio de perfis e RBAC com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, secrets=None):
        super(RepoRbacOracle, self).__init__(cfg=cfg, secrets=secrets)

    def _tabela_perfis(self):
        return self.qualify_table("profiles")

    def _tabela_usuarios(self):
        return self.qualify_table("users")

    def _tabela_funcionalidades(self):
        return self.qualify_table("features")

    def _tabela_perfil_func(self):
        return self.qualify_table("profile_feature")

    def _tabela_perfil_amb(self):
        return self.qualify_table("profile_env")

    def _tabela_perfil_scr(self):
        return self.qualify_table("profile_script")

    def _tabela_ambientes(self):
        return self.qualify_table("environments")

    def _tabela_scripts(self):
        return self.qualify_table("scripts")

    def _tabela_auditoria(self):
        return self.qualify_table("audit")

    def _seq_perfis(self):
        return self.qualify_sequence("profiles")

    def _seq_perfil_func(self):
        return self.qualify_sequence("profile_feature")

    def _seq_perfil_amb(self):
        return self.qualify_sequence("profile_env")

    def _seq_perfil_scr(self):
        return self.qualify_sequence("profile_script")

    def _seq_auditoria(self):
        return self.qualify_sequence("audit")

    def profiles_list(self, filters=None, page=1, size=20, conn=None):
        """Lista perfis com paginacao e desempate deterministico por id."""
        filters = filters or {}
        clauses = []
        binds = {}

        name_f = filters.get("name")
        if name_f:
            clauses.append("LOWER(name) LIKE :name_f")
            binds["name_f"] = "%" + name_f.lower() + "%"

        active_f = filters.get("active")
        if active_f:
            clauses.append("active = :active_f")
            binds["active_f"] = str(active_f).strip().upper()

        is_admin_f = filters.get("is_admin")
        if is_admin_f:
            clauses.append("is_admin = :is_admin_f")
            binds["is_admin_f"] = str(is_admin_f).strip().upper()

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
            "SELECT id FROM " + self._tabela_perfis() + where_sql + " AND ROWNUM <= 10001"
            if where_sql
            else "SELECT COUNT(*) FROM (SELECT id FROM " + self._tabela_perfis() + " WHERE ROWNUM <= 10001"
        )
        sql_count += ")"

        sql_paged = (
            "SELECT * FROM ("
            "SELECT a.*, ROWNUM rn FROM ("
            "SELECT id, name, description, is_admin, perm_version, active, "
            "created_at, created_by, updated_at, updated_by "
            "FROM " + self._tabela_perfis() + where_sql + " "
            "ORDER BY name ASC, id ASC"
            ") a WHERE ROWNUM <= :end_ts"
            ") WHERE rn > :start_ts"
        )

        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql_count, binds)
                row_c = cur.fetchone()
                raw_count = row_c[0] if row_c else 0
                total = min(raw_count, 10001)
                total_capped = raw_count >= 10001

                binds_page = copy.deepcopy(binds)
                binds_page["start_ts"] = start
                binds_page["end_ts"] = end
                cur.execute(sql_paged, binds_page)
                items = [self.tuple_to_dict(_COLS_PROFILE, r[:-1]) for r in cur.fetchall()]

                return {
                    "items": items,
                    "total": total,
                    "page": p,
                    "size": t,
                    "total_capped": total_capped,
                }
            finally:
                cur.close()

    def profiles_get(self, id, conn=None):
        """Retorna dict com dados do perfil pelo ID ou lanca RepoNotFound."""
        sql = (
            "SELECT id, name, description, is_admin, perm_version, active, "
            "created_at, created_by, updated_at, updated_by "
            "FROM " + self._tabela_perfis() + " WHERE id = :id"
        )
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql, {"id": int(id)})
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNotFound("Perfil ID %s nao encontrado" % id)
                return self.tuple_to_dict(_COLS_PROFILE, row)
            finally:
                cur.close()

    def profiles_insert(self, data, audit=None, actor=None, conn=None):
        """Insere novo perfil com validacoes de UK e CKs e auditoria na mesma transacao."""
        actor_clean = validate_record_actor(audit, actor)
        name = data.get("name")
        if not name or not str(name).strip():
            raise repo_errors.RepoViolation("Nome de perfil e obrigatorio")

        is_admin = str(data.get("is_admin", "N")).strip().upper()
        if is_admin not in ("Y", "N"):
            raise repo_errors.RepoViolation("Flag is_admin deve ser 'Y' ou 'N'", constraint=self.constraint_name("ck", "profiles", "adm"))

        active = str(data.get("active", "Y")).strip().upper()
        if active not in ("Y", "N"):
            raise repo_errors.RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint=self.constraint_name("ck", "profiles", "active"))

        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(
                    "SELECT id FROM " + self._tabela_perfis() + " WHERE UPPER(name) = :user_name",
                    {"user_name": name.strip().upper()},
                )
                if cur.fetchone():
                    raise repo_errors.RepoViolation("Perfil com nome '%s' ja existe" % name, constraint=self.constraint_name("uk", "profiles", "name"))

                pid = db_conn.next_id(c, self._seq_perfis())
                perm_version = int(data.get("perm_version", 1))

                sql_ins = (
                    "INSERT INTO " + self._tabela_perfis() + " "
                    "(id, name, description, is_admin, perm_version, active, "
                    "created_at, created_by, updated_at, updated_by) "
                    "VALUES (:id, :name, :description, :is_admin, :perm_version, :active, "
                    "SYSDATE, :actor, NULL, NULL)"
                )
                cur.execute(
                    sql_ins,
                    {
                        "id": pid,
                        "name": name.strip(),
                        "description": data.get("description", ""),
                        "is_admin": is_admin,
                        "perm_version": perm_version,
                        "active": active,
                        "actor": actor_clean,
                    },
                )
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), audit, "tbsss_profiles", pid)
            finally:
                cur.close()

            return self.profiles_get(pid, conn=c)

    def profiles_update(self, id, data, expected=None, audit=None, actor=None, conn=None):
        """Altera perfil e incrementa perm_version com protecao do ultimo admin (§4.3.B)."""
        actor_clean = validate_record_actor(audit, actor)
        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(
                    "SELECT id, name, description, is_admin, perm_version, active, "
                    "created_at, created_by, updated_at, updated_by "
                    "FROM " + self._tabela_perfis() + " WHERE id = :id FOR UPDATE WAIT 5",
                    {"id": int(id)},
                )
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNotFound("Perfil ID %s nao encontrado" % id)

                current = self.tuple_to_dict(_COLS_PROFILE, row)

                for field, expected_val in (expected or {}).items():
                    val_current = current.get(field)
                    if isinstance(val_current, datetime.datetime) and isinstance(expected_val, datetime.datetime):
                        if val_current.replace(microsecond=0) != expected_val.replace(microsecond=0):
                            raise repo_errors.RepoConflict("Perfil ID %s alterado por outra operacao (%s)" % (id, field))
                    elif val_current != expected_val:
                        raise repo_errors.RepoConflict("Perfil ID %s alterado por outra operacao (%s)" % (id, field))

                new_name = data.get("name")
                if new_name and new_name.strip().upper() != current["name"].upper():
                    cur.execute(
                        "SELECT id FROM " + self._tabela_perfis() + " WHERE UPPER(name) = :n AND id != :id",
                        {"n": new_name.strip().upper(), "id": int(id)},
                    )
                    if cur.fetchone():
                        raise repo_errors.RepoViolation("Perfil com nome '%s' ja existe" % new_name, constraint=self.constraint_name("uk", "profiles", "name"))

                new_is_admin = data.get("is_admin")
                if new_is_admin is not None:
                    new_is_admin = str(new_is_admin).strip().upper()
                    if new_is_admin not in ("Y", "N"):
                        raise repo_errors.RepoViolation("Flag is_admin deve ser 'Y' ou 'N'", constraint=self.constraint_name("ck", "profiles", "adm"))

                new_active = data.get("active")
                if new_active is not None:
                    new_active = str(new_active).strip().upper()
                    if new_active not in ("Y", "N"):
                        raise repo_errors.RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint=self.constraint_name("ck", "profiles", "active"))

                # Protecao do ultimo administrador (README §4.3.B)
                is_admin_effective = new_is_admin if new_is_admin is not None else current["is_admin"]
                active_effective = new_active if new_active is not None else current["active"]
                reduces_admin = (current["is_admin"] == "Y" and current["active"] == "Y") and (
                    is_admin_effective == "N" or active_effective == "N"
                )

                if reduces_admin:
                    cur.execute(
                        "SELECT u.id, u.profile_id "
                        "FROM " + self._tabela_usuarios() + " u "
                        "JOIN " + self._tabela_perfis() + " p ON p.id = u.profile_id "
                        "WHERE u.active = 'Y' AND p.active = 'Y' AND p.is_admin = 'Y' "
                        # Trava tambem os perfis: quem espera releia o is_admin alterado por outra
                        # transacao, e duas operacoes simultaneas nao deixam o sistema sem admin.
                        "FOR UPDATE OF u.active, p.is_admin WAIT 5"
                    )
                    admins_others = [r[0] for r in cur.fetchall() if r[1] != int(id)]
                    if not admins_others:
                        raise repo_errors.RepoViolation(
                            "Operacao deixaria o sistema sem administrador ativo",
                            constraint="sss_ultimo_admin",
                        )

                sets = [
                    "name = :name",
                    "description = :description",
                    "is_admin = :is_admin",
                    "active = :active",
                    "perm_version = perm_version + 1",
                    "updated_at = SYSDATE",
                    "updated_by = :actor",
                ]
                params = {
                    "id": int(id),
                    "name": new_name.strip() if new_name else current["name"],
                    "description": data.get("description", current["description"]),
                    "is_admin": is_admin_effective,
                    "active": active_effective,
                    "actor": actor_clean,
                }
                sql_upd = "UPDATE " + self._tabela_perfis() + " SET " + ", ".join(sets) + " WHERE id = :id"
                cur.execute(sql_upd, params)
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), audit, "tbsss_profiles", int(id))
            finally:
                cur.close()

            return self.profiles_get(id, conn=c)

    def matrix_get(self, profile_id, conn=None):
        """Retorna dict com {'funcs': [...], 'ambs': [...], 'scrs': [...]} ordenados."""
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute("SELECT id FROM " + self._tabela_perfis() + " WHERE id = :id", {"id": int(profile_id)})
                if not cur.fetchone():
                    raise repo_errors.RepoNotFound("Perfil ID %s nao encontrado" % profile_id)

                cur.execute(
                    "SELECT feature_id FROM " + self._tabela_perfil_func() + " "
                    "WHERE profile_id = :id ORDER BY feature_id ASC",
                    {"id": int(profile_id)},
                )
                features = [r[0] for r in cur.fetchall()]

                cur.execute(
                    "SELECT environment_id FROM " + self._tabela_perfil_amb() + " "
                    "WHERE profile_id = :id ORDER BY environment_id ASC",
                    {"id": int(profile_id)},
                )
                envs = [r[0] for r in cur.fetchall()]

                cur.execute(
                    "SELECT script_id FROM " + self._tabela_perfil_scr() + " "
                    "WHERE profile_id = :id ORDER BY script_id ASC",
                    {"id": int(profile_id)},
                )
                scrs = [r[0] for r in cur.fetchall()]

                return {
                    "funcs": features,
                    "ambs": envs,
                    "scrs": scrs,
                }
            finally:
                cur.close()

    def matrix_save(self, profile_id, features_ids, envs, scrs, expected_perm_version=None, audit=None, actor=None, conn=None):
        """Substitui associacoes por diferenca preservando created_* (CR-006, R-f)."""
        actor_clean = validate_record_actor(audit, actor)
        pid = int(profile_id)
        feature_id_list = sorted(set(int(x) for x in (features_ids or [])))
        envs_ids = sorted(set(int(x) for x in (envs or [])))
        scrs_ids = sorted(set(int(x) for x in (scrs or [])))

        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(
                    "SELECT perm_version FROM " + self._tabela_perfis() + " WHERE id = :id FOR UPDATE WAIT 5",
                    {"id": pid},
                )
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNotFound("Perfil ID %s nao encontrado" % pid)
                perm_version_current = row[0]

                if expected_perm_version is not None and perm_version_current != int(expected_perm_version):
                    raise repo_errors.RepoConflict("Matriz do perfil ID %s alterada por outra operacao" % pid)

                # Validacao previa das Foreign Keys
                for fid in feature_id_list:
                    cur.execute("SELECT id FROM " + self._tabela_funcionalidades() + " WHERE id = :x", {"x": fid})
                    if not cur.fetchone():
                        raise repo_errors.RepoViolation("ID %s inexistente" % fid, constraint=self.constraint_name("fk", "profile_feature", "fea"))

                for aid in envs_ids:
                    cur.execute("SELECT id FROM " + self._tabela_ambientes() + " WHERE id = :x", {"x": aid})
                    if not cur.fetchone():
                        raise repo_errors.RepoViolation("ID %s inexistente" % aid, constraint=self.constraint_name("fk", "profile_env", "env"))

                for sid in scrs_ids:
                    cur.execute("SELECT id FROM " + self._tabela_scripts() + " WHERE id = :x", {"x": sid})
                    if not cur.fetchone():
                        raise repo_errors.RepoViolation("ID %s inexistente" % sid, constraint=self.constraint_name("fk", "profile_script", "scr"))

                changed = False

                # 1. Funcionalidades
                cur.execute(
                    "SELECT id, feature_id FROM " + self._tabela_perfil_func() + " WHERE profile_id = :id",
                    {"id": pid},
                )
                f_current = dict((r[1], r[0]) for r in cur.fetchall())
                f_del = [f_current[f] for f in f_current if f not in feature_id_list]
                f_ins = [f for f in feature_id_list if f not in f_current]
                for rid in f_del:
                    cur.execute("DELETE FROM " + self._tabela_perfil_func() + " WHERE id = :rid", {"rid": rid})
                for fid in f_ins:
                    nid = db_conn.next_id(c, self._seq_perfil_func())
                    cur.execute(
                        "INSERT INTO " + self._tabela_perfil_func() + " "
                        "(id, profile_id, feature_id, created_at, created_by, updated_at, updated_by) "
                        "VALUES (:id, :pid, :fid, SYSDATE, :actor, NULL, NULL)",
                        {"id": nid, "pid": pid, "fid": fid, "actor": actor_clean},
                    )
                if f_del or f_ins:
                    changed = True

                # 2. Ambientes
                cur.execute(
                    "SELECT id, environment_id FROM " + self._tabela_perfil_amb() + " WHERE profile_id = :id",
                    {"id": pid},
                )
                a_current = dict((r[1], r[0]) for r in cur.fetchall())
                a_del = [a_current[a] for a in a_current if a not in envs_ids]
                a_ins = [a for a in envs_ids if a not in a_current]
                for rid in a_del:
                    cur.execute("DELETE FROM " + self._tabela_perfil_amb() + " WHERE id = :rid", {"rid": rid})
                for aid in a_ins:
                    nid = db_conn.next_id(c, self._seq_perfil_amb())
                    cur.execute(
                        "INSERT INTO " + self._tabela_perfil_amb() + " "
                        "(id, profile_id, environment_id, created_at, created_by, updated_at, updated_by) "
                        "VALUES (:id, :pid, :aid, SYSDATE, :actor, NULL, NULL)",
                        {"id": nid, "pid": pid, "aid": aid, "actor": actor_clean},
                    )
                if a_del or a_ins:
                    changed = True

                # 3. Scripts
                cur.execute(
                    "SELECT id, script_id FROM " + self._tabela_perfil_scr() + " WHERE profile_id = :id",
                    {"id": pid},
                )
                s_current = dict((r[1], r[0]) for r in cur.fetchall())
                s_del = [s_current[s] for s in s_current if s not in scrs_ids]
                s_ins = [s for s in scrs_ids if s not in s_current]
                for rid in s_del:
                    cur.execute("DELETE FROM " + self._tabela_perfil_scr() + " WHERE id = :rid", {"rid": rid})
                for sid in s_ins:
                    nid = db_conn.next_id(c, self._seq_perfil_scr())
                    cur.execute(
                        "INSERT INTO " + self._tabela_perfil_scr() + " "
                        "(id, profile_id, script_id, created_at, created_by, updated_at, updated_by) "
                        "VALUES (:id, :pid, :sid, SYSDATE, :actor, NULL, NULL)",
                        {"id": nid, "pid": pid, "sid": sid, "actor": actor_clean},
                    )
                if s_del or s_ins:
                    changed = True

                # Incrementa perm_version do perfil
                if changed:
                    cur.execute(
                        "UPDATE " + self._tabela_perfis() + " "
                        "SET perm_version = perm_version + 1, updated_at = SYSDATE, updated_by = :actor "
                        "WHERE id = :id",
                        {"id": pid, "actor": actor_clean},
                    )
                else:
                    cur.execute(
                        "UPDATE " + self._tabela_perfis() + " "
                        "SET perm_version = perm_version + 1 "
                        "WHERE id = :id",
                        {"id": pid},
                    )

                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), audit, "tbsss_profiles", pid)
            finally:
                cur.close()

            return self.matrix_get(pid, conn=c)

    def lock_active_admins(self, conn=None):
        """Executa lock dos usuarios administradores ativos (README §4.3.B) e retorna IDs."""
        sql = (
            "SELECT u.id "
            "FROM " + self._tabela_usuarios() + " u "
            "JOIN " + self._tabela_perfis() + " p ON p.id = u.profile_id "
            "WHERE u.active = 'Y' AND p.active = 'Y' AND p.is_admin = 'Y' "
            "FOR UPDATE OF u.active, p.is_admin WAIT 5"
        )
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql)
                return sorted(r[0] for r in cur.fetchall())
            finally:
                cur.close()

    def features_list(self, conn=None):
        """Retorna lista do catalogo canonico de funcionalidades ativas."""
        sql = (
            "SELECT id, code, name, module, description, active, "
            "created_at, created_by, updated_at, updated_by "
            "FROM " + self._tabela_funcionalidades() + " "
            "ORDER BY module ASC, code ASC, id ASC"
        )
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql)
                return [self.tuple_to_dict(_COLS_FUNC, r) for r in cur.fetchall()]
            finally:
                cur.close()
