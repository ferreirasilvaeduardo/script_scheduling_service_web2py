# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de usuarios (F7.3, AGENTS §4).

SQL estatico com binds, paginacao via ROWNUM, protecao de ultimo admin,
colunas de registro (CR-006) e revogacao de sessao via sessao_epoch (CR-008, E2).
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



def _failed_login_audit(auditoria, tentativas, max_tentativas, bloqueou, auditoria_bloqueio):
    """Itens de auditoria da falha de login: a contagem vem do valor lido sob a trava (mesma regra do FAKE)."""
    itens = [] if not auditoria else ([auditoria] if isinstance(auditoria, dict) else list(auditoria))
    if max_tentativas is not None:
        itens = [dict(item, detail=u"%s (tentativa %d de %d)" % (item.get("detail") or u"", tentativas,
                                                                    int(max_tentativas)))
                 if isinstance(item, dict) and item.get("action") == "LOGIN_FAILED" else item for item in itens]
    if bloqueou and auditoria_bloqueio:
        itens.append(auditoria_bloqueio)
    return itens

class RepoUsersOracle(BaseRepoOracle, RepoUsers):
    """Repositorio de usuarios com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, segredos=None):
        super(RepoUsersOracle, self).__init__(cfg=cfg, segredos=segredos)

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

    def get_session_state(self, usuario_id, conn=None):
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
                cur.execute(sql, {"user_id": int(usuario_id)})
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNotFound("Usuario ID %s nao encontrado" % usuario_id)
                return {
                    "user_id": row[0],
                    "login": row[1],
                    "name": row[2],
                    "usuario_ativo": (row[3] or "").strip(),
                    "profile_id": row[4],
                    "perfil_nome": row[5],
                    "perfil_ativo": (row[6] or "").strip(),
                    "is_admin": (row[7] or "").strip(),
                    "perm_version": row[8],
                    "session_epoch": row[9],
                }
            finally:
                cur.close()

    def list(self, filtros=None, pagina=1, tamanho=20, conn=None):
        """Lista usuarios paginados com desempate deterministico por id."""
        filtros = filtros or {}
        clausulas = []
        binds = {}
        binds_data = {}

        login_f = filtros.get("login")
        if login_f:
            clausulas.append("LOWER(login) LIKE :login_f")
            binds["login_f"] = "%" + login_f.lower() + "%"

        nome_f = filtros.get("name")
        if nome_f:
            clausulas.append("LOWER(name) LIKE :nome_f")
            binds["nome_f"] = "%" + nome_f.lower() + "%"

        perfil_f = filtros.get("profile_id")
        if perfil_f is not None:
            clausulas.append("profile_id = :perfil_f")
            binds["perfil_f"] = int(perfil_f)

        ativo_f = filtros.get("active")
        if ativo_f:
            clausulas.append("active = :ativo_f")
            binds["ativo_f"] = str(ativo_f).strip().upper()

        bloq_f = filtros.get("bloqueado_em")
        if bloq_f is not None:
            clausulas.append("locked_until IS NOT NULL AND locked_until > :bloq_f")
            binds["bloq_f"] = bloq_f
            binds_data["bloq_f"] = db_conn.TIPO_DATE

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
            "SELECT id FROM " + self._tabela() + where_sql + " AND ROWNUM <= 10001"
            if where_sql
            else "SELECT COUNT(*) FROM (SELECT id FROM " + self._tabela() + " WHERE ROWNUM <= 10001"
        )
        sql_count += ")"

        sql_paginada = (
            "SELECT * FROM ("
            "SELECT a.*, ROWNUM rn FROM ("
            "SELECT id, login, name, password_hash, profile_id, failed_attempts, locked_until, "
            "last_login_at, password_changed_at, session_epoch, active, "
            "created_at, created_by, updated_at, updated_by "
            "FROM " + self._tabela() + where_sql + " "
            "ORDER BY login ASC, id ASC"
            ") a WHERE ROWNUM <= :fim"
            ") WHERE rn > :inicio"
        )

        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                if binds_data:
                    db_conn.set_input_types(cur, **binds_data)
                cur.execute(sql_count, binds)
                row_c = cur.fetchone()
                raw_count = row_c[0] if row_c else 0
                total = min(raw_count, 10001)
                total_limitado = raw_count >= 10001

                binds_pag = copy.deepcopy(binds)
                binds_pag["inicio"] = inicio
                binds_pag["fim"] = fim
                cur.execute(sql_paginada, binds_pag)
                itens = [self.tuple_to_dict(_COLS_USER, r[:-1]) for r in cur.fetchall()]

                return {
                    "itens": itens,
                    "total": total,
                    "pagina": p,
                    "tamanho": t,
                    "total_limitado": total_limitado,
                }
            finally:
                cur.close()

    def insert(self, dados, auditoria=None, ator=None, conn=None):
        """Insere novo usuario com validacoes e auditoria na mesma transacao."""
        ator_limpo = validate_record_actor(auditoria, ator)
        login = dados.get("login")
        if not login or not isinstance(login, str) or not _RE_LOGIN.fullmatch(login):
            raise repo_errors.RepoViolation(
                "Login invalido (esperado: 3-30 caracteres [a-z0-9._-])",
                constraint=self.constraint_name("ck", "users", "login"),
            )

        ativo = str(dados.get("active", "Y")).strip().upper()
        if ativo not in ("Y", "N"):
            raise repo_errors.RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint=self.constraint_name("ck", "users", "active"))

        tentativas = int(dados.get("failed_attempts", 0))
        if tentativas < 0:
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

                perfil_id = dados.get("profile_id")
                cur.execute("SELECT id FROM " + self._tabela_perfis() + " WHERE id = :pid", {"pid": int(perfil_id)})
                if not cur.fetchone():
                    raise repo_errors.RepoViolation("Perfil ID %s nao existe" % perfil_id, constraint=self.constraint_name("fk", "users", "prf"))

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
                        "name": dados.get("name", ""),
                        "password_hash": dados.get("password_hash", "!"),
                        "profile_id": int(perfil_id),
                        "failed_attempts": tentativas,
                        "locked_until": dados.get("locked_until"),
                        "last_login_at": dados.get("last_login_at"),
                        "password_changed_at": dados.get("password_changed_at"),
                        "active": ativo,
                        "created_at": dados.get("created_at"),
                        "actor": ator_limpo,
                    },
                )
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_users", uid)
            finally:
                cur.close()

            return self.get_by_id(uid, conn=c)

    def update(self, id, dados, esperado=None, auditoria=None, ator=None, conn=None):
        """Altera usuario (login imutavel) com protecao do ultimo admin (README §4.3.B)."""
        ator_limpo = validate_record_actor(auditoria, ator)
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

                atual = self.tuple_to_dict(_COLS_USER, row[:15])
                p_atual_ativo = (row[15] or "").strip()
                p_atual_is_admin = (row[16] or "").strip()

                for campo, val_esp in (esperado or {}).items():
                    val_atual = atual.get(campo)
                    if isinstance(val_atual, datetime.datetime) and isinstance(val_esp, datetime.datetime):
                        if val_atual.replace(microsecond=0) != val_esp.replace(microsecond=0):
                            raise repo_errors.RepoConflict("Usuario ID %s alterado por outra operacao (%s)" % (id, campo))
                    elif val_atual != val_esp:
                        raise repo_errors.RepoConflict("Usuario ID %s alterado por outra operacao (%s)" % (id, campo))

                novo_login = dados.get("login")
                if novo_login is not None and novo_login != atual["login"]:
                    raise repo_errors.RepoViolation("Login de usuario e imutavel", constraint=self.trigger_name("users", "bu"))

                novo_perfil = dados.get("profile_id")
                perfil_alterado = False
                p_novo_ativo = p_atual_ativo
                p_novo_is_admin = p_atual_is_admin
                if novo_perfil is not None:
                    novo_perfil = int(novo_perfil)
                    if novo_perfil != atual["profile_id"]:
                        cur.execute(
                            "SELECT active, is_admin FROM " + self._tabela_perfis() + " WHERE id = :pid",
                            {"pid": novo_perfil},
                        )
                        row_p = cur.fetchone()
                        if not row_p:
                            raise repo_errors.RepoViolation("Perfil ID %s nao existe" % novo_perfil, constraint=self.constraint_name("fk", "users", "prf"))
                        p_novo_ativo = (row_p[0] or "").strip()
                        p_novo_is_admin = (row_p[1] or "").strip()
                        perfil_alterado = True

                novo_ativo = dados.get("active")
                ativo_alterado = False
                if novo_ativo is not None:
                    novo_ativo = str(novo_ativo).strip().upper()
                    if novo_ativo not in ("Y", "N"):
                        raise repo_errors.RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint=self.constraint_name("ck", "users", "active"))
                    if novo_ativo != atual["active"]:
                        ativo_alterado = True

                # Protecao do ultimo administrador (README §4.3.B)
                era_admin_ativo = (
                    atual["active"] == "Y" and p_atual_ativo == "Y" and p_atual_is_admin == "Y"
                )
                sera_admin_ativo = (
                    (novo_ativo if novo_ativo is not None else atual["active"]) == "Y"
                    and p_novo_ativo == "Y"
                    and p_novo_is_admin == "Y"
                )

                if era_admin_ativo and not sera_admin_ativo:
                    cur.execute(
                        "SELECT u.id "
                        "FROM " + self._tabela() + " u "
                        "JOIN " + self._tabela_perfis() + " p ON p.id = u.profile_id "
                        "WHERE u.active = 'Y' AND p.active = 'Y' AND p.is_admin = 'Y' "
                        # Trava tambem os perfis: quem espera releia o is_admin alterado por outra
                        # transacao, e duas operacoes simultaneas nao deixam o sistema sem admin.
                        "FOR UPDATE OF u.active, p.is_admin WAIT 5"
                    )
                    admins_restantes = [r[0] for r in cur.fetchall() if r[0] != int(id)]
                    if not admins_restantes:
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
                    "name": dados.get("name", atual["name"]),
                    "profile_id": novo_perfil if novo_perfil is not None else atual["profile_id"],
                    "active": novo_ativo if novo_ativo is not None else atual["active"],
                    "actor": ator_limpo,
                }
                if "password_hash" in dados:
                    sets.append("password_hash = :password_hash")
                    params["password_hash"] = dados["password_hash"]
                if "failed_attempts" in dados:
                    tentativas = int(dados["failed_attempts"])
                    if tentativas < 0:
                        raise repo_errors.RepoViolation(
                            "Tentativas falhas nao podem ser negativas", constraint=self.constraint_name("ck", "users", "att")
                        )
                    sets.append("failed_attempts = :failed_attempts")
                    params["failed_attempts"] = tentativas
                if "locked_until" in dados:
                    sets.append("locked_until = :locked_until")
                    params["locked_until"] = dados["locked_until"]
                if "last_login_at" in dados:
                    sets.append("last_login_at = :last_login_at")
                    params["last_login_at"] = dados["last_login_at"]
                if "password_changed_at" in dados:
                    sets.append("password_changed_at = :password_changed_at")
                    params["password_changed_at"] = dados["password_changed_at"]

                if perfil_alterado or ativo_alterado:
                    sets.append("session_epoch = session_epoch + 1")

                sql_upd = "UPDATE " + self._tabela() + " SET " + ", ".join(sets) + " WHERE id = :id"
                # So os binds de data presentes no SET: o python-oracledb recusa tipo declarado para bind
                # ausente do SQL (DPY-4008), o que quebrava toda alteracao sem data (F7.3, bateria integrada).
                tipos = dict((c, db_conn.TIPO_DATE) for c in ("locked_until", "last_login_at", "password_changed_at")
                             if c in params)
                if tipos:
                    db_conn.set_input_types(cur, **tipos)
                cur.execute(sql_upd, params)

                # Incrementa perm_versao do perfil de origem e destino se aplicavel
                if perfil_alterado or ativo_alterado:
                    p_origem = atual["profile_id"]
                    p_destino = novo_perfil if novo_perfil is not None else p_origem
                    cur.execute(
                        "UPDATE " + self._tabela_perfis() + " "
                        "SET perm_version = perm_version + 1 "
                        "WHERE id = :origem",
                        {"origem": p_origem},
                    )
                    if p_destino != p_origem:
                        cur.execute(
                            "UPDATE " + self._tabela_perfis() + " "
                            "SET perm_version = perm_version + 1 "
                            "WHERE id = :destino",
                            {"destino": p_destino},
                        )

                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_users", int(id))
            finally:
                cur.close()

            return self.get_by_id(id, conn=c)

    def register_login_failure(self, login, bloqueio_s=None, auditoria=None, max_tentativas=None,
                              auditoria_bloqueio=None, conn=None):
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

                uid, tentativas = row[0], int(row[1] or 0)
                if tentativas + 1 > 99:
                    raise repo_errors.RepoViolation("tentativas_falha excede NUMBER(2)", constraint=self.constraint_name("ck", "users", "att"))
                if max_tentativas is not None:
                    bloquear = tentativas + 1 >= int(max_tentativas)
                else:
                    bloquear = bloqueio_s is not None

                if bloquear:
                    cur.execute(
                        "UPDATE " + self._tabela() + " "
                        "SET failed_attempts = failed_attempts + 1, "
                        "locked_until = SYSDATE + :bloqueio_s / 86400 "
                        "WHERE id = :id",
                        {"id": uid, "bloqueio_s": int(bloqueio_s)},
                    )
                else:
                    cur.execute(
                        "UPDATE " + self._tabela() + " "
                        "SET failed_attempts = failed_attempts + 1 "
                        "WHERE id = :id",
                        {"id": uid},
                    )
                itens = _failed_login_audit(auditoria, tentativas + 1, max_tentativas, bloquear, auditoria_bloqueio)
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), itens, "tbsss_users", uid)
            finally:
                cur.close()

            registro = self.get_by_id(uid, conn=c)
            registro["bloqueou"] = bool(bloquear)
            return registro

    def register_login_success(self, login, novo_hash=None, auditoria=None, conn=None):
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

                if novo_hash is not None:
                    cur.execute(
                        "UPDATE " + self._tabela() + " "
                        "SET failed_attempts = 0, locked_until = NULL, last_login_at = SYSDATE, password_hash = :h "
                        "WHERE id = :id",
                        {"id": uid, "h": novo_hash},
                    )
                else:
                    cur.execute(
                        "UPDATE " + self._tabela() + " "
                        "SET failed_attempts = 0, locked_until = NULL, last_login_at = SYSDATE "
                        "WHERE id = :id",
                        {"id": uid},
                    )
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_users", uid)
            finally:
                cur.close()

            return self.get_by_id(uid, conn=c)

    def unlock(self, id, auditoria=None, ator=None, conn=None):
        """Desbloqueia conta de usuario zerando tentativas (grava updated_*)."""
        ator_limpo = validate_record_actor(auditoria, ator)
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
                    {"id": int(id), "actor": ator_limpo},
                )
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_users", int(id))
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

    def set_password(self, id, senha_hash, agora=None, auditoria=None, ator=None, conn=None):
        """Atualiza a senha do usuario e incrementa sessao_epoch (grava updated_*)."""
        ator_limpo = validate_record_actor(auditoria, ator)
        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute("SELECT id FROM " + self._tabela() + " WHERE id = :id FOR UPDATE WAIT 5", {"id": int(id)})
                if not cur.fetchone():
                    raise repo_errors.RepoNotFound("Usuario ID %s nao encontrado" % id)

                sql = (
                    "UPDATE " + self._tabela() + " "
                    "SET password_hash = :password_hash, "
                    "password_changed_at = NVL(:agora, SYSDATE), "
                    "failed_attempts = 0, locked_until = NULL, "
                    "session_epoch = session_epoch + 1, "
                    "updated_at = SYSDATE, updated_by = :actor "
                    "WHERE id = :id"
                )
                db_conn.set_input_types(cur, agora=db_conn.TIPO_DATE)
                cur.execute(sql, {"id": int(id), "password_hash": senha_hash, "agora": agora, "actor": ator_limpo})
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_users", int(id))
            finally:
                cur.close()

            return self.get_by_id(id, conn=c)

    def end_sessions(self, id, auditoria=None, conn=None):
        """Logout: incrementa sessao_epoch (rotina tecnica, sem updated_*)."""
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
                write_audit(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_users", int(id))
            finally:
                cur.close()

            return self.get_by_id(id, conn=c)
