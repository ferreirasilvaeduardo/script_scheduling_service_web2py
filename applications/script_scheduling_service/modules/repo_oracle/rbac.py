# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de RBAC e perfis (F7.3, AGENTS §4).

SQL estatico com binds, paginacao via ROWNUM, protecao de ultimo admin,
matriz por diferenca com preservacao de created_* (CR-006, R-f) e versao de permissao.
"""
import copy
import datetime

import db_conn
import repo_errors
from repo_oracle.base import (
    BaseRepoOracle,
    write_audit,
    translate_oracle_error,
    validate_record_actor,
)
from repo_rbac import RepoRbac

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

    def __init__(self, cfg=None, segredos=None):
        super(RepoRbacOracle, self).__init__(cfg=cfg, segredos=segredos)

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

    def profiles_list(self, filtros=None, pagina=1, tamanho=20, conn=None):
        """Lista perfis com paginacao e desempate deterministico por id."""
        filtros = filtros or {}
        clausulas = []
        binds = {}

        nome_f = filtros.get("name")
        if nome_f:
            clausulas.append("LOWER(name) LIKE :nome_f")
            binds["nome_f"] = "%" + nome_f.lower() + "%"

        ativo_f = filtros.get("active")
        if ativo_f:
            clausulas.append("active = :ativo_f")
            binds["ativo_f"] = str(ativo_f).strip().upper()

        is_admin_f = filtros.get("is_admin")
        if is_admin_f:
            clausulas.append("is_admin = :is_admin_f")
            binds["is_admin_f"] = str(is_admin_f).strip().upper()

        where_sql = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""

        p = 1 if pagina is None else int(pagina)
        t = 20 if tamanho is None else int(tamanho)
        if p < 1:
            p = 1
        if t < 1:
            t = 20
        inicio = (p - 1) * t
        fim = inicio + t

        sql_count = (
            "SELECT COUNT(*) FROM ("
            "SELECT id FROM " + self._tabela_perfis() + where_sql + " AND ROWNUM <= 10001"
            if where_sql
            else "SELECT COUNT(*) FROM (SELECT id FROM " + self._tabela_perfis() + " WHERE ROWNUM <= 10001"
        )
        sql_count += ")"

        sql_paginada = (
            "SELECT * FROM ("
            "SELECT a.*, ROWNUM rn FROM ("
            "SELECT id, name, description, is_admin, perm_version, active, "
            "created_at, created_by, updated_at, updated_by "
            "FROM " + self._tabela_perfis() + where_sql + " "
            "ORDER BY name ASC, id ASC"
            ") a WHERE ROWNUM <= :fim"
            ") WHERE rn > :inicio"
        )

        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql_count, binds)
                row_c = cur.fetchone()
                raw_count = row_c[0] if row_c else 0
                total = min(raw_count, 10001)
                total_limitado = raw_count >= 10001

                binds_pag = copy.deepcopy(binds)
                binds_pag["inicio"] = inicio
                binds_pag["fim"] = fim
                cur.execute(sql_paginada, binds_pag)
                itens = [self.tuple_to_dict(_COLS_PROFILE, r[:-1]) for r in cur.fetchall()]

                return {
                    "itens": itens,
                    "total": total,
                    "pagina": p,
                    "tamanho": t,
                    "total_limitado": total_limitado,
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

    def profiles_insert(self, dados, auditoria=None, ator=None, conn=None):
        """Insere novo perfil com validacoes de UK e CKs e auditoria na mesma transacao."""
        ator_limpo = validate_record_actor(auditoria, ator)
        nome = dados.get("name")
        if not nome or not str(nome).strip():
            raise repo_errors.RepoViolation("Nome de perfil e obrigatorio")

        is_admin = str(dados.get("is_admin", "N")).strip().upper()
        if is_admin not in ("Y", "N"):
            raise repo_errors.RepoViolation("Flag is_admin deve ser 'Y' ou 'N'", constraint=self.constraint_name("ck", "profiles", "adm"))

        ativo = str(dados.get("active", "Y")).strip().upper()
        if ativo not in ("Y", "N"):
            raise repo_errors.RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint=self.constraint_name("ck", "profiles", "active"))

        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(
                    "SELECT id FROM " + self._tabela_perfis() + " WHERE UPPER(name) = :nome_u",
                    {"nome_u": nome.strip().upper()},
                )
                if cur.fetchone():
                    raise repo_errors.RepoViolation("Perfil com nome '%s' ja existe" % nome, constraint=self.constraint_name("uk", "profiles", "name"))

                pid = db_conn.next_id(c, self._seq_perfis())
                perm_versao = int(dados.get("perm_version", 1))

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
                        "name": nome.strip(),
                        "description": dados.get("description", ""),
                        "is_admin": is_admin,
                        "perm_version": perm_versao,
                        "active": ativo,
                        "actor": ator_limpo,
                    },
                )
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_profiles", pid)
            finally:
                cur.close()

            return self.profiles_get(pid, conn=c)

    def profiles_update(self, id, dados, esperado=None, auditoria=None, ator=None, conn=None):
        """Altera perfil e incrementa perm_versao com protecao do ultimo admin (§4.3.B)."""
        ator_limpo = validate_record_actor(auditoria, ator)
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

                atual = self.tuple_to_dict(_COLS_PROFILE, row)

                for campo, val_esp in (esperado or {}).items():
                    val_atual = atual.get(campo)
                    if isinstance(val_atual, datetime.datetime) and isinstance(val_esp, datetime.datetime):
                        if val_atual.replace(microsecond=0) != val_esp.replace(microsecond=0):
                            raise repo_errors.RepoConflict("Perfil ID %s alterado por outra operacao (%s)" % (id, campo))
                    elif val_atual != val_esp:
                        raise repo_errors.RepoConflict("Perfil ID %s alterado por outra operacao (%s)" % (id, campo))

                novo_nome = dados.get("name")
                if novo_nome and novo_nome.strip().upper() != atual["name"].upper():
                    cur.execute(
                        "SELECT id FROM " + self._tabela_perfis() + " WHERE UPPER(name) = :n AND id != :id",
                        {"n": novo_nome.strip().upper(), "id": int(id)},
                    )
                    if cur.fetchone():
                        raise repo_errors.RepoViolation("Perfil com nome '%s' ja existe" % novo_nome, constraint=self.constraint_name("uk", "profiles", "name"))

                novo_is_admin = dados.get("is_admin")
                if novo_is_admin is not None:
                    novo_is_admin = str(novo_is_admin).strip().upper()
                    if novo_is_admin not in ("Y", "N"):
                        raise repo_errors.RepoViolation("Flag is_admin deve ser 'Y' ou 'N'", constraint=self.constraint_name("ck", "profiles", "adm"))

                novo_ativo = dados.get("active")
                if novo_ativo is not None:
                    novo_ativo = str(novo_ativo).strip().upper()
                    if novo_ativo not in ("Y", "N"):
                        raise repo_errors.RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint=self.constraint_name("ck", "profiles", "active"))

                # Protecao do ultimo administrador (README §4.3.B)
                is_admin_efetivo = novo_is_admin if novo_is_admin is not None else atual["is_admin"]
                ativo_efetivo = novo_ativo if novo_ativo is not None else atual["active"]
                reduz_admin = (atual["is_admin"] == "Y" and atual["active"] == "Y") and (
                    is_admin_efetivo == "N" or ativo_efetivo == "N"
                )

                if reduz_admin:
                    cur.execute(
                        "SELECT u.id, u.profile_id "
                        "FROM " + self._tabela_usuarios() + " u "
                        "JOIN " + self._tabela_perfis() + " p ON p.id = u.profile_id "
                        "WHERE u.active = 'Y' AND p.active = 'Y' AND p.is_admin = 'Y' "
                        # Trava tambem os perfis: quem espera releia o is_admin alterado por outra
                        # transacao, e duas operacoes simultaneas nao deixam o sistema sem admin.
                        "FOR UPDATE OF u.active, p.is_admin WAIT 5"
                    )
                    admins_outros = [r[0] for r in cur.fetchall() if r[1] != int(id)]
                    if not admins_outros:
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
                    "name": novo_nome.strip() if novo_nome else atual["name"],
                    "description": dados.get("description", atual["description"]),
                    "is_admin": is_admin_efetivo,
                    "active": ativo_efetivo,
                    "actor": ator_limpo,
                }
                sql_upd = "UPDATE " + self._tabela_perfis() + " SET " + ", ".join(sets) + " WHERE id = :id"
                cur.execute(sql_upd, params)
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_profiles", int(id))
            finally:
                cur.close()

            return self.profiles_get(id, conn=c)

    def matrix_get(self, perfil_id, conn=None):
        """Retorna dict com {'funcs': [...], 'ambs': [...], 'scrs': [...]} ordenados."""
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute("SELECT id FROM " + self._tabela_perfis() + " WHERE id = :id", {"id": int(perfil_id)})
                if not cur.fetchone():
                    raise repo_errors.RepoNotFound("Perfil ID %s nao encontrado" % perfil_id)

                cur.execute(
                    "SELECT feature_id FROM " + self._tabela_perfil_func() + " "
                    "WHERE profile_id = :id ORDER BY feature_id ASC",
                    {"id": int(perfil_id)},
                )
                funcs = [r[0] for r in cur.fetchall()]

                cur.execute(
                    "SELECT environment_id FROM " + self._tabela_perfil_amb() + " "
                    "WHERE profile_id = :id ORDER BY environment_id ASC",
                    {"id": int(perfil_id)},
                )
                ambs = [r[0] for r in cur.fetchall()]

                cur.execute(
                    "SELECT script_id FROM " + self._tabela_perfil_scr() + " "
                    "WHERE profile_id = :id ORDER BY script_id ASC",
                    {"id": int(perfil_id)},
                )
                scrs = [r[0] for r in cur.fetchall()]

                return {
                    "funcs": funcs,
                    "ambs": ambs,
                    "scrs": scrs,
                }
            finally:
                cur.close()

    def matrix_save(self, perfil_id, funcs, ambs, scrs, perm_versao_esperada=None, auditoria=None, ator=None, conn=None):
        """Substitui associacoes por diferenca preservando created_* (CR-006, R-f)."""
        ator_limpo = validate_record_actor(auditoria, ator)
        pid = int(perfil_id)
        funcs_ids = sorted(set(int(x) for x in (funcs or [])))
        ambs_ids = sorted(set(int(x) for x in (ambs or [])))
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
                perm_versao_atual = row[0]

                if perm_versao_esperada is not None and perm_versao_atual != int(perm_versao_esperada):
                    raise repo_errors.RepoConflict("Matriz do perfil ID %s alterada por outra operacao" % pid)

                # Validacao previa das Foreign Keys
                for fid in funcs_ids:
                    cur.execute("SELECT id FROM " + self._tabela_funcionalidades() + " WHERE id = :x", {"x": fid})
                    if not cur.fetchone():
                        raise repo_errors.RepoViolation("ID %s inexistente" % fid, constraint=self.constraint_name("fk", "profile_feature", "fea"))

                for aid in ambs_ids:
                    cur.execute("SELECT id FROM " + self._tabela_ambientes() + " WHERE id = :x", {"x": aid})
                    if not cur.fetchone():
                        raise repo_errors.RepoViolation("ID %s inexistente" % aid, constraint=self.constraint_name("fk", "profile_env", "env"))

                for sid in scrs_ids:
                    cur.execute("SELECT id FROM " + self._tabela_scripts() + " WHERE id = :x", {"x": sid})
                    if not cur.fetchone():
                        raise repo_errors.RepoViolation("ID %s inexistente" % sid, constraint=self.constraint_name("fk", "profile_script", "scr"))

                mudou = False

                # 1. Funcionalidades
                cur.execute(
                    "SELECT id, feature_id FROM " + self._tabela_perfil_func() + " WHERE profile_id = :id",
                    {"id": pid},
                )
                f_atuais = dict((r[1], r[0]) for r in cur.fetchall())
                f_del = [f_atuais[f] for f in f_atuais if f not in funcs_ids]
                f_ins = [f for f in funcs_ids if f not in f_atuais]
                for rid in f_del:
                    cur.execute("DELETE FROM " + self._tabela_perfil_func() + " WHERE id = :rid", {"rid": rid})
                for fid in f_ins:
                    nid = db_conn.next_id(c, self._seq_perfil_func())
                    cur.execute(
                        "INSERT INTO " + self._tabela_perfil_func() + " "
                        "(id, profile_id, feature_id, created_at, created_by, updated_at, updated_by) "
                        "VALUES (:id, :pid, :fid, SYSDATE, :actor, NULL, NULL)",
                        {"id": nid, "pid": pid, "fid": fid, "actor": ator_limpo},
                    )
                if f_del or f_ins:
                    mudou = True

                # 2. Ambientes
                cur.execute(
                    "SELECT id, environment_id FROM " + self._tabela_perfil_amb() + " WHERE profile_id = :id",
                    {"id": pid},
                )
                a_atuais = dict((r[1], r[0]) for r in cur.fetchall())
                a_del = [a_atuais[a] for a in a_atuais if a not in ambs_ids]
                a_ins = [a for a in ambs_ids if a not in a_atuais]
                for rid in a_del:
                    cur.execute("DELETE FROM " + self._tabela_perfil_amb() + " WHERE id = :rid", {"rid": rid})
                for aid in a_ins:
                    nid = db_conn.next_id(c, self._seq_perfil_amb())
                    cur.execute(
                        "INSERT INTO " + self._tabela_perfil_amb() + " "
                        "(id, profile_id, environment_id, created_at, created_by, updated_at, updated_by) "
                        "VALUES (:id, :pid, :aid, SYSDATE, :actor, NULL, NULL)",
                        {"id": nid, "pid": pid, "aid": aid, "actor": ator_limpo},
                    )
                if a_del or a_ins:
                    mudou = True

                # 3. Scripts
                cur.execute(
                    "SELECT id, script_id FROM " + self._tabela_perfil_scr() + " WHERE profile_id = :id",
                    {"id": pid},
                )
                s_atuais = dict((r[1], r[0]) for r in cur.fetchall())
                s_del = [s_atuais[s] for s in s_atuais if s not in scrs_ids]
                s_ins = [s for s in scrs_ids if s not in s_atuais]
                for rid in s_del:
                    cur.execute("DELETE FROM " + self._tabela_perfil_scr() + " WHERE id = :rid", {"rid": rid})
                for sid in s_ins:
                    nid = db_conn.next_id(c, self._seq_perfil_scr())
                    cur.execute(
                        "INSERT INTO " + self._tabela_perfil_scr() + " "
                        "(id, profile_id, script_id, created_at, created_by, updated_at, updated_by) "
                        "VALUES (:id, :pid, :sid, SYSDATE, :actor, NULL, NULL)",
                        {"id": nid, "pid": pid, "sid": sid, "actor": ator_limpo},
                    )
                if s_del or s_ins:
                    mudou = True

                # Incrementa perm_versao do perfil
                if mudou:
                    cur.execute(
                        "UPDATE " + self._tabela_perfis() + " "
                        "SET perm_version = perm_version + 1, updated_at = SYSDATE, updated_by = :actor "
                        "WHERE id = :id",
                        {"id": pid, "actor": ator_limpo},
                    )
                else:
                    cur.execute(
                        "UPDATE " + self._tabela_perfis() + " "
                        "SET perm_version = perm_version + 1 "
                        "WHERE id = :id",
                        {"id": pid},
                    )

                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_profiles", pid)
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
