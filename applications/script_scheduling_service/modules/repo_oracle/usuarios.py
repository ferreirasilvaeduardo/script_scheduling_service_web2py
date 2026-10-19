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
    gravar_auditoria,
    traduzir_erro_oracle,
    validar_ator_registro,
)
from repo_usuarios import RepoUsuarios

_RE_LOGIN = re.compile(r"^[a-z0-9._-]{3,30}$")

_COLS_USUARIO = (
    "id",
    "login",
    "nome",
    "senha_hash",
    "perfil_id",
    "tentativas_falha",
    "bloqueado_ate",
    "ultimo_login",
    "senha_alterada_em",
    "sessao_epoch",
    "ativo",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
)


class RepoUsuariosOracle(BaseRepoOracle, RepoUsuarios):
    """Repositorio de usuarios com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, segredos=None):
        super(RepoUsuariosOracle, self).__init__(cfg=cfg, segredos=segredos)

    def _tabela(self):
        return self.qualificar_tabela("usuarios")

    def _tabela_perfis(self):
        return self.qualificar_tabela("perfis")

    def _tabela_auditoria(self):
        return self.qualificar_tabela("auditoria")

    def _seq_usuarios(self):
        return self.qualificar_sequence("usuarios")

    def _seq_auditoria(self):
        return self.qualificar_sequence("auditoria")

    def agora(self):
        """Instante atual do banco (SYSDATE), sem microssegundos (README §4.2)."""
        with self.contexto_leitura() as conn:
            return db_conn.agora_banco(conn)

    def obter_por_login(self, login, conn=None):
        """Retorna dict com dados do usuario ou None se nao encontrado."""
        sql = (
            "SELECT id, login, nome, senha_hash, perfil_id, tentativas_falha, bloqueado_ate, "
            "ultimo_login, senha_alterada_em, sessao_epoch, ativo, "
            "created_at, created_by, updated_at, updated_by "
            "FROM " + self._tabela() + " WHERE login = :login"
        )
        with self.contexto_leitura(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql, {"login": login})
                row = cur.fetchone()
                if not row:
                    return None
                return self.tupla_para_dict(_COLS_USUARIO, row)
            finally:
                cur.close()

    def obter_por_id(self, id, conn=None):
        """Retorna dict com dados do usuario pelo ID ou lanca RepoNaoEncontrado."""
        sql = (
            "SELECT id, login, nome, senha_hash, perfil_id, tentativas_falha, bloqueado_ate, "
            "ultimo_login, senha_alterada_em, sessao_epoch, ativo, "
            "created_at, created_by, updated_at, updated_by "
            "FROM " + self._tabela() + " WHERE id = :id"
        )
        with self.contexto_leitura(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql, {"id": int(id)})
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)
                return self.tupla_para_dict(_COLS_USUARIO, row)
            finally:
                cur.close()

    def obter_estado_sessao(self, usuario_id, conn=None):
        """Retorna estado composto de sessao em uma query por PK (join usuario + perfil)."""
        sql = (
            "SELECT u.id, u.login, u.nome, u.ativo, "
            "p.id, p.nome, p.ativo, p.is_admin, p.perm_versao, u.sessao_epoch "
            "FROM " + self._tabela() + " u "
            "JOIN " + self._tabela_perfis() + " p ON p.id = u.perfil_id "
            "WHERE u.id = :usuario_id"
        )
        with self.contexto_leitura(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql, {"usuario_id": int(usuario_id)})
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNaoEncontrado("Usuario ID %s nao encontrado" % usuario_id)
                return {
                    "usuario_id": row[0],
                    "login": row[1],
                    "nome": row[2],
                    "usuario_ativo": (row[3] or "").strip(),
                    "perfil_id": row[4],
                    "perfil_nome": row[5],
                    "perfil_ativo": (row[6] or "").strip(),
                    "is_admin": (row[7] or "").strip(),
                    "perm_versao": row[8],
                    "sessao_epoch": row[9],
                }
            finally:
                cur.close()

    def listar(self, filtros=None, pagina=1, tamanho=20, conn=None):
        """Lista usuarios paginados com desempate deterministico por id."""
        filtros = filtros or {}
        clausulas = []
        binds = {}
        binds_data = {}

        login_f = filtros.get("login")
        if login_f:
            clausulas.append("LOWER(login) LIKE :login_f")
            binds["login_f"] = "%" + login_f.lower() + "%"

        nome_f = filtros.get("nome")
        if nome_f:
            clausulas.append("LOWER(nome) LIKE :nome_f")
            binds["nome_f"] = "%" + nome_f.lower() + "%"

        perfil_f = filtros.get("perfil_id")
        if perfil_f is not None:
            clausulas.append("perfil_id = :perfil_f")
            binds["perfil_f"] = int(perfil_f)

        ativo_f = filtros.get("ativo")
        if ativo_f:
            clausulas.append("ativo = :ativo_f")
            binds["ativo_f"] = str(ativo_f).strip().upper()

        bloq_f = filtros.get("bloqueado_em")
        if bloq_f is not None:
            clausulas.append("bloqueado_ate IS NOT NULL AND bloqueado_ate > :bloq_f")
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
            "SELECT id, login, nome, senha_hash, perfil_id, tentativas_falha, bloqueado_ate, "
            "ultimo_login, senha_alterada_em, sessao_epoch, ativo, "
            "created_at, created_by, updated_at, updated_by "
            "FROM " + self._tabela() + where_sql + " "
            "ORDER BY login ASC, id ASC"
            ") a WHERE ROWNUM <= :fim"
            ") WHERE rn > :inicio"
        )

        with self.contexto_leitura(conn=conn) as c:
            cur = c.cursor()
            try:
                if binds_data:
                    db_conn.definir_tipos_entrada(cur, **binds_data)
                cur.execute(sql_count, binds)
                row_c = cur.fetchone()
                raw_count = row_c[0] if row_c else 0
                total = min(raw_count, 10001)
                total_limitado = raw_count >= 10001

                binds_pag = copy.deepcopy(binds)
                binds_pag["inicio"] = inicio
                binds_pag["fim"] = fim
                cur.execute(sql_paginada, binds_pag)
                itens = [self.tupla_para_dict(_COLS_USUARIO, r[:-1]) for r in cur.fetchall()]

                return {
                    "itens": itens,
                    "total": total,
                    "pagina": p,
                    "tamanho": t,
                    "total_limitado": total_limitado,
                }
            finally:
                cur.close()

    def inserir(self, dados, auditoria=None, ator=None, conn=None):
        """Insere novo usuario com validacoes e auditoria na mesma transacao."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        login = dados.get("login")
        if not login or not isinstance(login, str) or not _RE_LOGIN.fullmatch(login):
            raise repo_errors.RepoViolacao(
                "Login invalido (esperado: 3-30 caracteres [a-z0-9._-])",
                constraint=self.nome_constraint("ck", "usuarios", "login"),
            )

        ativo = str(dados.get("ativo", "S")).strip().upper()
        if ativo not in ("S", "N"):
            raise repo_errors.RepoViolacao("Flag ativo deve ser 'S' ou 'N'", constraint=self.nome_constraint("ck", "usuarios", "ativo"))

        tentativas = int(dados.get("tentativas_falha", 0))
        if tentativas < 0:
            raise repo_errors.RepoViolacao(
                "Tentativas falhas nao podem ser negativas", constraint=self.nome_constraint("ck", "usuarios", "tent")
            )

        with self.transacao_escrita(conn=conn) as c:
            cur = c.cursor()
            try:
                # Checa duplicidade do login
                cur.execute("SELECT id FROM " + self._tabela() + " WHERE login = :login", {"login": login})
                if cur.fetchone():
                    raise repo_errors.RepoViolacao("Login '%s' ja existe" % login, constraint=self.nome_constraint("uk", "usuarios", "login"))

                perfil_id = dados.get("perfil_id")
                cur.execute("SELECT id FROM " + self._tabela_perfis() + " WHERE id = :pid", {"pid": int(perfil_id)})
                if not cur.fetchone():
                    raise repo_errors.RepoViolacao("Perfil ID %s nao existe" % perfil_id, constraint=self.nome_constraint("fk", "usuarios", "per"))

                uid = db_conn.proximo_id(c, self._seq_usuarios())
                sql_ins = (
                    "INSERT INTO " + self._tabela() + " "
                    "(id, login, nome, senha_hash, perfil_id, tentativas_falha, "
                    "bloqueado_ate, ultimo_login, senha_alterada_em, sessao_epoch, ativo, "
                    "created_at, created_by, updated_at, updated_by) "
                    "VALUES (:id, :login, :nome, :senha_hash, :perfil_id, :tentativas_falha, "
                    ":bloqueado_ate, :ultimo_login, :senha_alterada_em, 0, :ativo, "
                    "NVL(:created_at, SYSDATE), :ator, NULL, NULL)"
                )
                db_conn.definir_tipos_entrada(
                    cur,
                    bloqueado_ate=db_conn.TIPO_DATE,
                    ultimo_login=db_conn.TIPO_DATE,
                    senha_alterada_em=db_conn.TIPO_DATE,
                    created_at=db_conn.TIPO_DATE,
                )
                cur.execute(
                    sql_ins,
                    {
                        "id": uid,
                        "login": login,
                        "nome": dados.get("nome", ""),
                        "senha_hash": dados.get("senha_hash", "!"),
                        "perfil_id": int(perfil_id),
                        "tentativas_falha": tentativas,
                        "bloqueado_ate": dados.get("bloqueado_ate"),
                        "ultimo_login": dados.get("ultimo_login"),
                        "senha_alterada_em": dados.get("senha_alterada_em"),
                        "ativo": ativo,
                        "created_at": dados.get("created_at"),
                        "ator": ator_limpo,
                    },
                )
                gravar_auditoria(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_usuarios", uid)
            finally:
                cur.close()

            return self.obter_por_id(uid, conn=c)

    def alterar(self, id, dados, esperado=None, auditoria=None, ator=None, conn=None):
        """Altera usuario (login imutavel) com protecao do ultimo admin (README §4.3.B)."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        with self.transacao_escrita(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(
                    "SELECT u.id, u.login, u.nome, u.senha_hash, u.perfil_id, u.tentativas_falha, "
                    "u.bloqueado_ate, u.ultimo_login, u.senha_alterada_em, u.sessao_epoch, u.ativo, "
                    "u.created_at, u.created_by, u.updated_at, u.updated_by, "
                    "p.ativo, p.is_admin "
                    "FROM " + self._tabela() + " u "
                    "JOIN " + self._tabela_perfis() + " p ON p.id = u.perfil_id "
                    "WHERE u.id = :id FOR UPDATE OF u.ativo WAIT 5",
                    {"id": int(id)},
                )
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)

                atual = self.tupla_para_dict(_COLS_USUARIO, row[:15])
                p_atual_ativo = (row[15] or "").strip()
                p_atual_is_admin = (row[16] or "").strip()

                for campo, val_esp in (esperado or {}).items():
                    val_atual = atual.get(campo)
                    if isinstance(val_atual, datetime.datetime) and isinstance(val_esp, datetime.datetime):
                        if val_atual.replace(microsecond=0) != val_esp.replace(microsecond=0):
                            raise repo_errors.RepoConflito("Usuario ID %s alterado por outra operacao (%s)" % (id, campo))
                    elif val_atual != val_esp:
                        raise repo_errors.RepoConflito("Usuario ID %s alterado por outra operacao (%s)" % (id, campo))

                novo_login = dados.get("login")
                if novo_login is not None and novo_login != atual["login"]:
                    raise repo_errors.RepoViolacao("Login de usuario e imutavel", constraint=self.nome_trigger("usuarios", "bu"))

                novo_perfil = dados.get("perfil_id")
                perfil_alterado = False
                p_novo_ativo = p_atual_ativo
                p_novo_is_admin = p_atual_is_admin
                if novo_perfil is not None:
                    novo_perfil = int(novo_perfil)
                    if novo_perfil != atual["perfil_id"]:
                        cur.execute(
                            "SELECT ativo, is_admin FROM " + self._tabela_perfis() + " WHERE id = :pid",
                            {"pid": novo_perfil},
                        )
                        row_p = cur.fetchone()
                        if not row_p:
                            raise repo_errors.RepoViolacao("Perfil ID %s nao existe" % novo_perfil, constraint=self.nome_constraint("fk", "usuarios", "per"))
                        p_novo_ativo = (row_p[0] or "").strip()
                        p_novo_is_admin = (row_p[1] or "").strip()
                        perfil_alterado = True

                novo_ativo = dados.get("ativo")
                ativo_alterado = False
                if novo_ativo is not None:
                    novo_ativo = str(novo_ativo).strip().upper()
                    if novo_ativo not in ("S", "N"):
                        raise repo_errors.RepoViolacao("Flag ativo deve ser 'S' ou 'N'", constraint=self.nome_constraint("ck", "usuarios", "ativo"))
                    if novo_ativo != atual["ativo"]:
                        ativo_alterado = True

                # Protecao do ultimo administrador (README §4.3.B)
                era_admin_ativo = (
                    atual["ativo"] == "S" and p_atual_ativo == "S" and p_atual_is_admin == "S"
                )
                sera_admin_ativo = (
                    (novo_ativo if novo_ativo is not None else atual["ativo"]) == "S"
                    and p_novo_ativo == "S"
                    and p_novo_is_admin == "S"
                )

                if era_admin_ativo and not sera_admin_ativo:
                    cur.execute(
                        "SELECT u.id "
                        "FROM " + self._tabela() + " u "
                        "JOIN " + self._tabela_perfis() + " p ON p.id = u.perfil_id "
                        "WHERE u.ativo = 'S' AND p.ativo = 'S' AND p.is_admin = 'S' "
                        "FOR UPDATE OF u.ativo WAIT 5"
                    )
                    admins_restantes = [r[0] for r in cur.fetchall() if r[0] != int(id)]
                    if not admins_restantes:
                        raise repo_errors.RepoViolacao(
                            "Operacao deixaria o sistema sem administrador ativo",
                            constraint="sss_ultimo_admin",
                        )

                sets = [
                    "nome = :nome",
                    "perfil_id = :perfil_id",
                    "ativo = :ativo",
                    "updated_at = SYSDATE",
                    "updated_by = :ator",
                ]
                params = {
                    "id": int(id),
                    "nome": dados.get("nome", atual["nome"]),
                    "perfil_id": novo_perfil if novo_perfil is not None else atual["perfil_id"],
                    "ativo": novo_ativo if novo_ativo is not None else atual["ativo"],
                    "ator": ator_limpo,
                }
                if "senha_hash" in dados:
                    sets.append("senha_hash = :senha_hash")
                    params["senha_hash"] = dados["senha_hash"]
                if "tentativas_falha" in dados:
                    tentativas = int(dados["tentativas_falha"])
                    if tentativas < 0:
                        raise repo_errors.RepoViolacao(
                            "Tentativas falhas nao podem ser negativas", constraint=self.nome_constraint("ck", "usuarios", "tent")
                        )
                    sets.append("tentativas_falha = :tentativas_falha")
                    params["tentativas_falha"] = tentativas
                if "bloqueado_ate" in dados:
                    sets.append("bloqueado_ate = :bloqueado_ate")
                    params["bloqueado_ate"] = dados["bloqueado_ate"]
                if "ultimo_login" in dados:
                    sets.append("ultimo_login = :ultimo_login")
                    params["ultimo_login"] = dados["ultimo_login"]
                if "senha_alterada_em" in dados:
                    sets.append("senha_alterada_em = :senha_alterada_em")
                    params["senha_alterada_em"] = dados["senha_alterada_em"]

                if perfil_alterado or ativo_alterado:
                    sets.append("sessao_epoch = sessao_epoch + 1")

                sql_upd = "UPDATE " + self._tabela() + " SET " + ", ".join(sets) + " WHERE id = :id"
                db_conn.definir_tipos_entrada(
                    cur,
                    bloqueado_ate=db_conn.TIPO_DATE,
                    ultimo_login=db_conn.TIPO_DATE,
                    senha_alterada_em=db_conn.TIPO_DATE,
                )
                cur.execute(sql_upd, params)

                # Incrementa perm_versao do perfil de origem e destino se aplicavel
                if perfil_alterado or ativo_alterado:
                    p_origem = atual["perfil_id"]
                    p_destino = novo_perfil if novo_perfil is not None else p_origem
                    cur.execute(
                        "UPDATE " + self._tabela_perfis() + " "
                        "SET perm_versao = perm_versao + 1 "
                        "WHERE id = :origem",
                        {"origem": p_origem},
                    )
                    if p_destino != p_origem:
                        cur.execute(
                            "UPDATE " + self._tabela_perfis() + " "
                            "SET perm_versao = perm_versao + 1 "
                            "WHERE id = :destino",
                            {"destino": p_destino},
                        )

                gravar_auditoria(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_usuarios", int(id))
            finally:
                cur.close()

            return self.obter_por_id(id, conn=c)

    def registrar_falha_login(self, login, bloqueio_s=None, auditoria=None, conn=None):
        """Incrementa tentativas_falha (rotina tecnica, sem updated_*)."""
        with self.transacao_escrita(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(
                    "SELECT id, tentativas_falha FROM " + self._tabela() + " WHERE login = :login FOR UPDATE WAIT 5",
                    {"login": login},
                )
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNaoEncontrado("Usuario com login '%s' nao encontrado" % login)

                uid, tentativas = row[0], row[1]
                if tentativas + 1 > 99:
                    raise repo_errors.RepoViolacao("tentativas_falha excede NUMBER(2)", constraint=self.nome_constraint("ck", "usuarios", "tent"))

                if bloqueio_s is not None:
                    cur.execute(
                        "UPDATE " + self._tabela() + " "
                        "SET tentativas_falha = tentativas_falha + 1, "
                        "bloqueado_ate = SYSDATE + :bloqueio_s / 86400 "
                        "WHERE id = :id",
                        {"id": uid, "bloqueio_s": int(bloqueio_s)},
                    )
                else:
                    cur.execute(
                        "UPDATE " + self._tabela() + " "
                        "SET tentativas_falha = tentativas_falha + 1 "
                        "WHERE id = :id",
                        {"id": uid},
                    )
                gravar_auditoria(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_usuarios", uid)
            finally:
                cur.close()

            return self.obter_por_id(uid, conn=c)

    def registrar_sucesso_login(self, login, novo_hash=None, auditoria=None, conn=None):
        """Zera falhas e grava ultimo_login (rotina tecnica, sem updated_*)."""
        with self.transacao_escrita(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(
                    "SELECT id FROM " + self._tabela() + " WHERE login = :login FOR UPDATE WAIT 5",
                    {"login": login},
                )
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNaoEncontrado("Usuario com login '%s' nao encontrado" % login)
                uid = row[0]

                if novo_hash is not None:
                    cur.execute(
                        "UPDATE " + self._tabela() + " "
                        "SET tentativas_falha = 0, bloqueado_ate = NULL, ultimo_login = SYSDATE, senha_hash = :h "
                        "WHERE id = :id",
                        {"id": uid, "h": novo_hash},
                    )
                else:
                    cur.execute(
                        "UPDATE " + self._tabela() + " "
                        "SET tentativas_falha = 0, bloqueado_ate = NULL, ultimo_login = SYSDATE "
                        "WHERE id = :id",
                        {"id": uid},
                    )
                gravar_auditoria(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_usuarios", uid)
            finally:
                cur.close()

            return self.obter_por_id(uid, conn=c)

    def desbloquear(self, id, auditoria=None, ator=None, conn=None):
        """Desbloqueia conta de usuario zerando tentativas (grava updated_*)."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        with self.transacao_escrita(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute("SELECT id FROM " + self._tabela() + " WHERE id = :id FOR UPDATE WAIT 5", {"id": int(id)})
                if not cur.fetchone():
                    raise repo_errors.RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)

                cur.execute(
                    "UPDATE " + self._tabela() + " "
                    "SET tentativas_falha = 0, bloqueado_ate = NULL, updated_at = SYSDATE, updated_by = :ator "
                    "WHERE id = :id",
                    {"id": int(id), "ator": ator_limpo},
                )
                gravar_auditoria(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_usuarios", int(id))
            finally:
                cur.close()

            return self.obter_por_id(id, conn=c)

    def reiniciar_tentativas(self, id, conn=None):
        """Rotina tecnica do login: bloqueio vencido zera contadores sem updated_* nem auditoria."""
        with self.transacao_escrita(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute("SELECT id FROM " + self._tabela() + " WHERE id = :id FOR UPDATE WAIT 5", {"id": int(id)})
                if not cur.fetchone():
                    raise repo_errors.RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)

                cur.execute(
                    "UPDATE " + self._tabela() + " "
                    "SET tentativas_falha = 0, bloqueado_ate = NULL "
                    "WHERE id = :id",
                    {"id": int(id)},
                )
            finally:
                cur.close()

            return self.obter_por_id(id, conn=c)

    def definir_senha(self, id, senha_hash, agora=None, auditoria=None, ator=None, conn=None):
        """Atualiza a senha do usuario e incrementa sessao_epoch (grava updated_*)."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        with self.transacao_escrita(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute("SELECT id FROM " + self._tabela() + " WHERE id = :id FOR UPDATE WAIT 5", {"id": int(id)})
                if not cur.fetchone():
                    raise repo_errors.RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)

                sql = (
                    "UPDATE " + self._tabela() + " "
                    "SET senha_hash = :senha_hash, "
                    "senha_alterada_em = NVL(:agora, SYSDATE), "
                    "tentativas_falha = 0, bloqueado_ate = NULL, "
                    "sessao_epoch = sessao_epoch + 1, "
                    "updated_at = SYSDATE, updated_by = :ator "
                    "WHERE id = :id"
                )
                db_conn.definir_tipos_entrada(cur, agora=db_conn.TIPO_DATE)
                cur.execute(sql, {"id": int(id), "senha_hash": senha_hash, "agora": agora, "ator": ator_limpo})
                gravar_auditoria(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_usuarios", int(id))
            finally:
                cur.close()

            return self.obter_por_id(id, conn=c)

    def encerrar_sessoes(self, id, auditoria=None, conn=None):
        """Logout: incrementa sessao_epoch (rotina tecnica, sem updated_*)."""
        with self.transacao_escrita(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute("SELECT id FROM " + self._tabela() + " WHERE id = :id FOR UPDATE WAIT 5", {"id": int(id)})
                if not cur.fetchone():
                    raise repo_errors.RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)

                cur.execute(
                    "UPDATE " + self._tabela() + " "
                    "SET sessao_epoch = sessao_epoch + 1 "
                    "WHERE id = :id",
                    {"id": int(id)},
                )
                gravar_auditoria(c, self._tabela_auditoria(), self._seq_auditoria(), auditoria, "tbsss_usuarios", int(id))
            finally:
                cur.close()

            return self.obter_por_id(id, conn=c)
