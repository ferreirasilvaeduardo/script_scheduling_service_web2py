# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de catalogo (F7.3, agregado CATALOGO; AGENTS §4).

Ambientes, scripts, homologacoes (tbsss_script_env), parametros e vinculos (tbsss_script_param),
com a mesma semantica do repo_fake/catalog.py (README §2.5):
- SQL estatico com binds; os modelos ficam nas constantes abaixo e recebem, uma vez por instancia,
  somente identificadores qualificados por sql_ident (owner e prefixo validados);
- paginacao ROWNUM com total limitado a 10.001 (CR-007, R-29) e sort_order binaria por name/code e id;
- CKs, UKs, FKs e regras de dependencia validadas antes do DML, com os nomes do FAKE;
- colunas de registro (CR-006): created_* no INSERT, updated_* so na alteracao de negocio;
- vinculos por diferenca (R-f); script_param preserva o created_* de cada parametro que continua.
Ordem de locks: tbsss_scripts -> tbsss_parameters (nunca o inverso).
"""
import datetime
import re

import db_conn
import repo_errors
from repo_catalog import RepoCatalog
from repo_oracle.base import BaseRepoOracle, write_audit, validate_record_actor

_RE_ENV_NAME = re.compile(r"^[A-Z0-9_]{1,30}$")
_RE_PRM_CODE = re.compile(r"^[a-z0-9_]{1,30}$")
_RE_PRM_FLAG = re.compile(r"^-{1,2}[A-Za-z0-9][A-Za-z0-9_-]{0,27}$")

_LIMIT_TOTAL = 10001
_BATCH_IN = 500

_COLS_ENV = ("id", "name", "description", "connection", "active",
             "created_at", "created_by", "updated_at", "updated_by")
_COLS_SCR = ("id", "name", "description", "script_group", "category", "stage", "interpreter", "path_file",
             "param_type", "max_parallel_env", "timeout_s", "active",
             "created_at", "created_by", "updated_at", "updated_by")
_COLS_PRM = ("id", "code", "param_flag", "label", "description", "component_type", "options_json",
             "default_value", "validation_regex", "sensitive", "active",
             "created_at", "created_by", "updated_at", "updated_by")
_COLS_SPRM = ("id", "parameter_id", "sort_order", "required", "default_value_override",
              "created_at", "created_by", "updated_at", "updated_by")

_FIELDS_SCR_UPDATABLE = ("name", "description", "script_group", "category", "stage", "interpreter", "path_file",
                          "param_type", "max_parallel_env", "timeout_s", "active")


def _column_list(cols, alias=""):
    return ", ".join(alias + c for c in cols)


# -----------------------------------------------------------------------------
# SQL estatico. {amb}, {scr}, {samb}, {prm}, {sprm}, {pscr} e {pamb} recebem apenas nomes
# qualificados por sql_ident (validados); todo valor entra por bind.
# -----------------------------------------------------------------------------

_SQL_ENV_GET = "SELECT " + _column_list(_COLS_ENV) + " FROM {env} WHERE id = :id"
_SQL_ENV_GET_LOCK = _SQL_ENV_GET + " FOR UPDATE WAIT 5"
_SQL_ENV_BY_NAME = "SELECT id FROM {env} WHERE name = :name"
_SQL_ENV_EXISTS = "SELECT id FROM {env} WHERE id = :id"
_SQL_ENV_LIST = (
    "SELECT " + _column_list(_COLS_ENV) + " FROM {env}{where} "
    "ORDER BY NLSSORT(name, 'NLS_SORT=BINARY'), id"
)
_SQL_ENV_COUNT = "SELECT COUNT(*) FROM (SELECT id FROM {env} WHERE {where_count})"
_SQL_ENV_INSERT = (
    "INSERT INTO {env} (id, name, description, connection, active, created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :name, :description, :connection, :active, SYSDATE, :actor, NULL, NULL)"
)
_SQL_ENV_UPDATE = (
    "UPDATE {env} SET description = :description, connection = :connection, active = :active, "
    "updated_at = SYSDATE, updated_by = :actor WHERE id = :id"
)

_SQL_SCR_GET = "SELECT " + _column_list(_COLS_SCR) + " FROM {scr} WHERE id = :id"
_SQL_SCR_GET_LOCK = _SQL_SCR_GET + " FOR UPDATE WAIT 5"
_SQL_SCR_LOCK = "SELECT id FROM {scr} WHERE id = :id FOR UPDATE WAIT 5"
# uk_tbsss_scr_name diferencia maiusculas (README §8.5): comparacao exata, sem UPPER/LOWER.
_SQL_SCR_NAME_IN_USE = "SELECT id FROM {scr} WHERE name = :name AND id <> :id"
_SQL_SCR_LIST = (
    "SELECT " + _column_list(_COLS_SCR, "s.") + ", "
    "(SELECT COUNT(*) FROM {sprm} sp WHERE sp.script_id = s.id) qtd_parametros "
    "FROM {scr} s{where} "
    "ORDER BY NLSSORT(s.name, 'NLS_SORT=BINARY'), s.id"
)
_SQL_SCR_COUNT = "SELECT COUNT(*) FROM (SELECT s.id FROM {scr} s WHERE {where_count})"
_SQL_SCR_INSERT = (
    "INSERT INTO {scr} (id, name, description, script_group, category, stage, interpreter, path_file, param_type, "
    "max_parallel_env, timeout_s, active, created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :name, :description, :script_group, :category, :stage, :interpreter, :path_file, :param_type, "
    ":max_parallel_env, :timeout_s, :active, SYSDATE, :actor, NULL, NULL)"
)
_SQL_SCR_UPDATE = (
    "UPDATE {scr} SET name = :name, description = :description, script_group = :script_group, category = :category, "
    "stage = :stage, interpreter = :interpreter, path_file = :path_file, param_type = :param_type, "
    "max_parallel_env = :max_parallel_env, timeout_s = :timeout_s, active = :active, "
    "updated_at = SYSDATE, updated_by = :actor WHERE id = :id"
)
_SQL_SCR_STAMP = "UPDATE {scr} SET updated_at = SYSDATE, updated_by = :actor WHERE id = :id"
_SQL_SCR_HOMOLOGATED = (
    "SELECT sa.script_id, a.name FROM {senv} sa JOIN {env} a ON a.id = sa.environment_id "
    "WHERE sa.script_id IN ({ids})"
)

_SQL_SENV_OF_SCRIPT = "SELECT id, environment_id FROM {senv} WHERE script_id = :script_id"
_SQL_SENV_DELETE = "DELETE FROM {senv} WHERE id = :id"
_SQL_SENV_INSERT = (
    "INSERT INTO {senv} (id, script_id, environment_id, created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :script_id, :environment_id, SYSDATE, :actor, NULL, NULL)"
)

_SQL_PRM_GET = "SELECT " + _column_list(_COLS_PRM) + " FROM {prm} WHERE id = :id"
_SQL_PRM_GET_LOCK = _SQL_PRM_GET + " FOR UPDATE WAIT 5"
_SQL_PRM_BY_CODE = "SELECT id FROM {prm} WHERE code = :code"
_SQL_PRM_EXISTS = "SELECT id FROM {prm} WHERE id = :id"
_SQL_PRM_LIST = (
    "SELECT " + _column_list(_COLS_PRM, "p.") + ", "
    "(SELECT COUNT(*) FROM {sprm} sp WHERE sp.parameter_id = p.id) qtd_scripts "
    "FROM {prm} p{where} "
    "ORDER BY NLSSORT(p.code, 'NLS_SORT=BINARY'), p.id"
)
_SQL_PRM_COUNT = "SELECT COUNT(*) FROM (SELECT p.id FROM {prm} p WHERE {where_count})"
_SQL_PRM_INSERT = (
    "INSERT INTO {prm} (id, code, param_flag, label, description, component_type, options_json, "
    "default_value, validation_regex, sensitive, active, created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :code, :param_flag, :label, :description, :component_type, :options_json, "
    ":default_value, :validation_regex, :sensitive, :active, SYSDATE, :actor, NULL, NULL)"
)
_SQL_PRM_UPDATE = (
    "UPDATE {prm} SET param_flag = :param_flag, label = :label, description = :description, "
    "component_type = :component_type, options_json = :options_json, default_value = :default_value, "
    "validation_regex = :validation_regex, sensitive = :sensitive, active = :active, "
    "updated_at = SYSDATE, updated_by = :actor WHERE id = :id"
)
_SQL_PRM_SCRIPTS_LINKED = (
    "SELECT s.param_type, s.active FROM {sprm} sp JOIN {scr} s ON s.id = sp.script_id "
    "WHERE sp.parameter_id = :parameter_id"
)
_SQL_PRM_LINKS = (
    "SELECT " + _column_list(_COLS_SCR, "s.") + " FROM {scr} s "
    "WHERE EXISTS (SELECT 1 FROM {sprm} sp WHERE sp.script_id = s.id AND sp.parameter_id = :parameter_id) "
    "ORDER BY NLSSORT(s.name, 'NLS_SORT=BINARY'), s.id"
)
# Ordem de locks: o script dono ja esta travado; os parametros vem depois (scripts -> parametros).
_SQL_PRM_LOCK_FLAG = "SELECT id, param_flag FROM {prm} WHERE id = :id FOR UPDATE WAIT 5"

_SQL_SPRM_OF_SCRIPT = (
    "SELECT " + _column_list(_COLS_SPRM) + " FROM {sprm} WHERE script_id = :script_id ORDER BY sort_order, id"
)
_SQL_SPRM_PARAMETERS = (
    "SELECT sp.parameter_id FROM {sprm} sp WHERE sp.script_id = :script_id"
)
_SQL_SPRM_GET = (
    "SELECT " + _column_list(_COLS_PRM, "p.") + ", sp.sort_order, sp.required, sp.default_value_override "
    "FROM {sprm} sp JOIN {prm} p ON p.id = sp.parameter_id "
    "WHERE sp.script_id = :script_id ORDER BY sp.sort_order, sp.id"
)
_SQL_SPRM_DELETE_OF_SCRIPT = "DELETE FROM {sprm} WHERE script_id = :script_id"
_SQL_SPRM_INSERT = (
    "INSERT INTO {sprm} (id, script_id, parameter_id, sort_order, required, default_value_override, "
    "created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :script_id, :parameter_id, :sort_order, :required, :default_value_override, "
    ":created_at, :created_by, :updated_at, :updated_by)"
)
# Vinculo novo ou alterado: o carimbo vem do relogio do banco (SYSDATE), nunca do no.
_SQL_SPRM_INSERT_NEW = (
    "INSERT INTO {sprm} (id, script_id, parameter_id, sort_order, required, default_value_override, "
    "created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :script_id, :parameter_id, :sort_order, :required, :default_value_override, "
    "SYSDATE, :actor, NULL, NULL)"
)
_SQL_SPRM_INSERT_CHANGED = (
    "INSERT INTO {sprm} (id, script_id, parameter_id, sort_order, required, default_value_override, "
    "created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :script_id, :parameter_id, :sort_order, :required, :default_value_override, "
    ":created_at, :created_by, SYSDATE, :actor)"
)

# README §4.3.A: script ativo, homologado em ambiente ativo; o admin dispensa perfil_scr/perfil_amb.
_SQL_EXEC_ADMIN = (
    "SELECT " + _column_list(_COLS_SCR, "s.") + " FROM {scr} s "
    "WHERE s.active = 'Y' "
    "AND EXISTS (SELECT 1 FROM {senv} sa JOIN {env} a ON a.id = sa.environment_id "
    "WHERE sa.script_id = s.id AND a.active = 'Y') "
    "ORDER BY NLSSORT(s.name, 'NLS_SORT=BINARY'), s.id"
)
_SQL_EXEC_PROFILE = (
    "SELECT " + _column_list(_COLS_SCR, "s.") + " FROM {scr} s "
    "WHERE s.active = 'Y' "
    "AND EXISTS (SELECT 1 FROM {pscr} ps WHERE ps.profile_id = :profile_id AND ps.script_id = s.id) "
    "AND EXISTS (SELECT 1 FROM {senv} sa JOIN {env} a ON a.id = sa.environment_id "
    "JOIN {penv} pa ON pa.environment_id = sa.environment_id AND pa.profile_id = :profile_id "
    "WHERE sa.script_id = s.id AND a.active = 'Y') "
    "ORDER BY NLSSORT(s.name, 'NLS_SORT=BINARY'), s.id"
)


def _like_contains(valor, maiusculas):
    """Trecho para LIKE ... ESCAPE '\\': '%' e '_' digitados contam como literais (como no FAKE)."""
    v = valor.upper() if maiusculas else valor.lower()
    v = v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + v + "%"


def _page_size(pagina, tamanho):
    # Valor nao numerico propaga ValueError/TypeError, como no FAKE: o controller valida antes.
    p = 1 if pagina is None else int(pagina)
    t = 20 if tamanho is None else int(tamanho)
    if p < 1:
        p = 1
    if t < 1:
        t = 20
    return p, t


def _equal(atual, esperado):
    """Comparacao nula-segura do 'esperado' ('' e NULL no Oracle; DATE sem fracao)."""
    if atual == "":
        atual = None
    if esperado == "":
        esperado = None
    if isinstance(atual, datetime.datetime) and isinstance(esperado, datetime.datetime):
        return atual.replace(microsecond=0) == esperado.replace(microsecond=0)
    return atual == esperado


class RepoCatalogOracle(BaseRepoOracle, RepoCatalog):
    """Repositorio de catalogo com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, segredos=None):
        super(RepoCatalogOracle, self).__init__(cfg=cfg, segredos=segredos)
        self._idents = {
            "env": self.qualify_table("environments"),
            "scr": self.qualify_table("scripts"),
            "senv": self.qualify_table("script_env"),
            "prm": self.qualify_table("parameters"),
            "sprm": self.qualify_table("script_param"),
            "pscr": self.qualify_table("profile_script"),
            "penv": self.qualify_table("profile_env"),
        }
        self._sql = {}
        for nome, modelo in globals().items():
            if nome.startswith("_SQL_") and "{where" not in modelo and "{ids}" not in modelo:
                self._sql[nome[5:]] = modelo.format(**self._idents)
        self._tbl_aud = self.qualify_table("audit")
        self._seq_aud = self.qualify_sequence("audit")
        self._seq = {
            "environments": self.qualify_sequence("environments"),
            "scripts": self.qualify_sequence("scripts"),
            "script_env": self.qualify_sequence("script_env"),
            "parameters": self.qualify_sequence("parameters"),
            "script_param": self.qualify_sequence("script_param"),
        }

    # -------------------------------------------------------------------------
    # Utilitarios
    # -------------------------------------------------------------------------

    def _ck(self, entidade, sufixo):
        return self.constraint_name("ck", entidade, sufixo)

    def _sql_dinamico(self, modelo, **partes):
        """Completa um modelo com identificadores e clausulas fixas (allowlist) montadas pelo codigo."""
        valores = dict(self._idents)
        valores.update(partes)
        return modelo.format(**valores)

    def _executar(self, cur, sql, binds=None):
        if binds is None:
            cur.execute(sql)
        else:
            cur.execute(sql, binds)

    def _uma(self, conn, sql, binds, cols):
        cur = conn.cursor()
        try:
            self._executar(cur, sql, binds)
            row = cur.fetchone()
            return self.tuple_to_dict(cols, row) if row else None
        finally:
            cur.close()

    def _existe(self, conn, sql, binds):
        cur = conn.cursor()
        try:
            self._executar(cur, sql, binds)
            return cur.fetchone() is not None
        finally:
            cur.close()

    def _listar(self, conn, modelo_lista, modelo_conta, cols, clausulas, binds, pagina, tamanho, extras=()):
        """Paginacao ROWNUM (AGENTS §4.4) e COUNT limitado a 10.001 na mesma leitura."""
        p, t = _page_size(pagina, tamanho)
        inicio = (p - 1) * t
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        where_count = " AND ".join(list(clausulas) + ["ROWNUM <= " + str(_LIMIT_TOTAL)])
        sql_lista = self._sql_dinamico(modelo_lista, where=where)
        sql_pag = (
            "SELECT * FROM (SELECT a.*, ROWNUM rn FROM (" + sql_lista + ") a WHERE ROWNUM <= :end_ts) "
            "WHERE rn > :start_ts"
        )
        sql_conta = self._sql_dinamico(modelo_conta, where_count=where_count)
        cur = conn.cursor()
        try:
            cur.execute(sql_conta, binds)
            bruto = cur.fetchone()[0]
            binds_pag = dict(binds)
            binds_pag["start_ts"] = inicio
            binds_pag["end_ts"] = inicio + t
            cur.execute(sql_pag, binds_pag)
            todas = tuple(cols) + tuple(extras)
            itens = [self.tuple_to_dict(todas, r[:len(todas)]) for r in cur.fetchall()]
        finally:
            cur.close()
        return {
            "itens": itens,
            "total": min(bruto, _LIMIT_TOTAL),
            "pagina": p,
            "tamanho": t,
            "total_limitado": bruto >= _LIMIT_TOTAL,
        }

    def _auditar(self, conn, auditoria, entidade, entidade_id):
        write_audit(conn, self._tbl_aud, self._seq_aud, auditoria, entidade, entidade_id)

    def _conferir_esperado(self, atual, esperado, rotulo, id):
        for campo, valor in (esperado or {}).items():
            if not _equal(atual.get(campo), valor):
                raise repo_errors.RepoConflict("%s ID %s alterado por outra operacao (%s)" % (rotulo, id, campo))

    # -------------------------------------------------------------------------
    # Ambientes (tbsss_environments)
    # -------------------------------------------------------------------------

    def environments_list(self, filtros=None, pagina=1, tamanho=20, conn=None):
        """Lista ambientes paginados por nome ASC, id ASC."""
        filtros = filtros or {}
        clausulas, binds = [], {}
        if filtros.get("name"):
            clausulas.append("UPPER(name) LIKE :name_f ESCAPE '\\'")
            binds["name_f"] = _like_contains(filtros["name"], maiusculas=True)
        if filtros.get("active"):
            clausulas.append("active = :active_f")
            binds["active_f"] = filtros["active"]
        with self.read_context(conn=conn) as c:
            return self._listar(c, _SQL_ENV_LIST, _SQL_ENV_COUNT, _COLS_ENV, clausulas, binds, pagina, tamanho)

    def environments_get(self, id, conn=None):
        """Retorna dict do ambiente pelo ID ou lanca RepoNotFound."""
        with self.read_context(conn=conn) as c:
            reg = self._uma(c, self._sql["ENV_GET"], {"id": int(id)}, _COLS_ENV)
        if reg is None:
            raise repo_errors.RepoNotFound("Ambiente ID %s nao encontrado" % id)
        return reg

    def environments_insert(self, dados, auditoria=None, ator=None, conn=None):
        """Insere ambiente (CKs, UK e DSN sem credencial) e audita na mesma transacao."""
        ator_limpo = validate_record_actor(auditoria, ator)
        nome = dados.get("name")
        if not nome or not _RE_ENV_NAME.match(nome):
            raise repo_errors.RepoViolation("Nome de ambiente invalido (esperado: 1-30 chars [A-Z0-9_])",
                                           constraint=self._ck("environments", "name"))
        conexao = dados.get("connection")
        ativo = dados.get("active", "Y")

        with self.write_transaction(conn=conn) as c:
            # Mesma ordem do FAKE: UK antes das CKs. ck_..._amb_nome garante maiusculas, entao a
            # igualdade exata equivale a UK sem distincao de caixa.
            if self._existe(c, self._sql["ENV_BY_NAME"], {"name": nome}):
                raise repo_errors.RepoViolation("Ambiente com nome '%s' ja existe" % nome,
                                               constraint=self.constraint_name("uk", "environments", "name"))
            if conexao and "@" in conexao:
                raise repo_errors.RepoViolation("Conexao nao pode conter credencial (@)",
                                               constraint=self._ck("environments", "connection"))
            if ativo not in ("Y", "N"):
                raise repo_errors.RepoViolation("Flag ativo deve ser 'Y' ou 'N'",
                                               constraint=self._ck("environments", "active"))
            aid = db_conn.next_id(c, self._seq["environments"])
            cur = c.cursor()
            try:
                cur.execute(self._sql["ENV_INSERT"], {
                    "id": aid, "name": nome, "description": dados.get("description", ""),
                    "connection": conexao, "active": ativo, "actor": ator_limpo,
                })
            finally:
                cur.close()
            self._auditar(c, auditoria, "tbsss_environments", aid)
            return self.environments_get(aid, conn=c)

    def environments_update(self, id, dados, esperado=None, auditoria=None, ator=None, conn=None):
        """Altera ambiente (nome imutavel, tr_tbsss_env_bu), condicional a 'esperado'."""
        ator_limpo = validate_record_actor(auditoria, ator)
        with self.write_transaction(conn=conn) as c:
            atual = self._uma(c, self._sql["ENV_GET_LOCK"], {"id": int(id)}, _COLS_ENV)
            if atual is None:
                raise repo_errors.RepoNotFound("Ambiente ID %s nao encontrado" % id)
            self._conferir_esperado(atual, esperado, "Ambiente", id)

            novo_nome = dados.get("name")
            if novo_nome is not None and novo_nome != atual["name"]:
                raise repo_errors.RepoViolation("Nome de ambiente e imutavel",
                                               constraint=self.trigger_name("environments", "bu"))
            novo = dict(atual)
            novo_conexao = dados.get("connection")
            if novo_conexao is not None:
                if "@" in novo_conexao:
                    raise repo_errors.RepoViolation("Conexao nao pode conter credencial (@)",
                                                   constraint=self._ck("environments", "connection"))
                novo["connection"] = novo_conexao
            elif "connection" in dados:
                novo["connection"] = None
            if "description" in dados:
                novo["description"] = dados["description"]
            novo_ativo = dados.get("active")
            if novo_ativo is not None:
                if novo_ativo not in ("Y", "N"):
                    raise repo_errors.RepoViolation("Flag ativo deve ser 'Y' ou 'N'",
                                                   constraint=self._ck("environments", "active"))
                novo["active"] = novo_ativo

            cur = c.cursor()
            try:
                cur.execute(self._sql["ENV_UPDATE"], {
                    "id": int(id), "description": novo["description"], "connection": novo["connection"],
                    "active": novo["active"], "actor": ator_limpo,
                })
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflict("Ambiente ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, auditoria, "tbsss_environments", int(id))
            return self.environments_get(id, conn=c)

    # -------------------------------------------------------------------------
    # Scripts (tbsss_scripts)
    # -------------------------------------------------------------------------

    def _homologados_por_script(self, conn, script_ids):
        """{script_id: [nomes em ordem alfabetica]} com IN por contagem controlada, em lotes."""
        resultado = dict((sid, []) for sid in script_ids)
        ids = list(script_ids)
        cur = conn.cursor()
        try:
            for i in range(0, len(ids), _BATCH_IN):
                lote = ids[i:i + _BATCH_IN]
                marcas = ", ".join(":s%d" % n for n in range(len(lote)))
                binds = dict(("s%d" % n, v) for n, v in enumerate(lote))
                cur.execute(self._sql_dinamico(_SQL_SCR_HOMOLOGATED, ids=marcas), binds)
                for sid, nome in cur.fetchall():
                    resultado[sid].append(nome)
        finally:
            cur.close()
        for nomes in resultado.values():
            nomes.sort()
        return resultado

    def scripts_list(self, filtros=None, pagina=1, tamanho=20, conn=None):
        """Lista scripts por nome ASC, id ASC, com ambientes_homologados e qtd_parametros."""
        filtros = filtros or {}
        clausulas, binds = [], {}
        if filtros.get("name"):
            clausulas.append("LOWER(s.name) LIKE :name_f ESCAPE '\\'")
            binds["name_f"] = _like_contains(filtros["name"], maiusculas=False)
        for chave in ("script_group", "category", "interpreter", "active"):
            if filtros.get(chave):
                clausulas.append("s." + chave + " = :" + chave + "_f")
                binds[chave + "_f"] = filtros[chave]
        with self.read_context(conn=conn) as c:
            pagina_ = self._listar(c, _SQL_SCR_LIST, _SQL_SCR_COUNT, _COLS_SCR, clausulas, binds,
                                   pagina, tamanho, extras=("qtd_parametros",))
            homolog = self._homologados_por_script(c, [it["id"] for it in pagina_["itens"]])
        for item in pagina_["itens"]:
            item["ambientes_homologados"] = homolog.get(item["id"], [])
        return pagina_

    def scripts_get(self, id, conn=None):
        """Retorna dict do script pelo ID ou lanca RepoNotFound."""
        with self.read_context(conn=conn) as c:
            reg = self._uma(c, self._sql["SCR_GET"], {"id": int(id)}, _COLS_SCR)
        if reg is None:
            raise repo_errors.RepoNotFound("Script ID %s nao encontrado" % id)
        return reg

    def _validar_script(self, base):
        """CKs da tabela 6 sobre o registro resultante, na ordem do FAKE (sem cortar nada)."""
        if not base.get("name"):
            raise repo_errors.RepoViolation("Nome de script e obrigatorio")
        if base.get("param_type", "NAMED") not in ("NAMED", "POSITIONAL", "NONE"):
            raise repo_errors.RepoViolation("Tipo de parametro invalido", constraint=self._ck("scripts", "ptype"))
        if base.get("active", "Y") not in ("Y", "N"):
            raise repo_errors.RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint=self._ck("scripts", "active"))
        if base.get("interpreter") not in ("PYTHON3", "BASH", "SH"):
            raise repo_errors.RepoViolation("Interpretador fora da allowlist", constraint=self._ck("scripts", "int"))
        pfile = base.get("path_file") or ""
        # ck_tbsss_scr_path (README §10, CR-005): absoluto, sem '..', '//' nem '\'; ate 500 caracteres.
        if (not pfile.startswith("/") or ".." in pfile or "//" in pfile or "\\" in pfile
                or len(pfile) > 500):
            raise repo_errors.RepoViolation("path_file deve ser absoluto e sem '..'",
                                           constraint=self._ck("scripts", "path"))
        if not (1 <= int(base.get("max_parallel_env", 1)) <= 999):
            raise repo_errors.RepoViolation("max_qtd_parallel_env deve estar entre 1 e 999",
                                           constraint=self._ck("scripts", "paral"))
        tmout = base.get("timeout_s")
        if tmout is not None and int(tmout) <= 0:
            raise repo_errors.RepoViolation("timeout_seg deve ser maior que zero",
                                           constraint=self._ck("scripts", "tmout"))

    def _nome_script_livre(self, conn, nome, id_atual):
        if self._existe(conn, self._sql["SCR_NAME_IN_USE"], {"name": nome, "id": id_atual}):
            raise repo_errors.RepoViolation("Script com nome '%s' ja existe" % nome,
                                           constraint=self.constraint_name("uk", "scripts", "name"))

    def _flags_dos_parametros(self, conn, parametro_ids):
        """Trava os parametros (scripts -> parametros) e devolve {id: param_nomeado}; ausente = FK."""
        flags = {}
        for pid in parametro_ids:
            cur = conn.cursor()
            try:
                cur.execute(self._sql["PRM_LOCK_FLAG"], {"id": pid})
                row = cur.fetchone()
            finally:
                cur.close()
            if row is None:
                raise repo_errors.RepoViolation("Parametro ID %s nao existe" % pid,
                                               constraint=self.constraint_name("fk", "script_param", "prm"))
            flags[pid] = row[1]
        return flags

    def _regras_tipo_param(self, tipo_param, flags):
        # README §6.3: NENHUM nao aceita vinculos; NOMEADO exige flag em todo parametro vinculado.
        if tipo_param == "NONE" and flags:
            raise repo_errors.RepoViolation("Script NENHUM com vinculos", constraint="sss_scr_nenhum_vinculado")
        if tipo_param == "NAMED":
            for pid in flags:
                if not flags[pid]:
                    raise repo_errors.RepoViolation("Parametro sem flag em script NOMEADO",
                                                   constraint="sss_scr_nomeado_sem_flag")

    def _binds_script(self, reg, ator):
        tmout = reg.get("timeout_s")
        return {
            "name": reg["name"], "description": reg.get("description"), "script_group": reg.get("script_group"),
            "category": reg.get("category"), "stage": reg.get("stage"),
            "interpreter": reg["interpreter"], "path_file": reg["path_file"],
            "param_type": reg.get("param_type", "NAMED"),
            "max_parallel_env": int(reg.get("max_parallel_env", 1)),
            "timeout_s": int(tmout) if tmout is not None else None,
            "active": reg.get("active", "Y"),
            "actor": ator,
        }

    def scripts_insert(self, dados, auditoria=None, ator=None, conn=None):
        """Insere script (CKs, UK sensivel a maiusculas) e audita na mesma transacao."""
        ator_limpo = validate_record_actor(auditoria, ator)
        base = dict(dados)
        base.setdefault("description", "")
        self._validar_script(base)
        with self.write_transaction(conn=conn) as c:
            self._nome_script_livre(c, base["name"], 0)
            sid = db_conn.next_id(c, self._seq["scripts"])
            binds = self._binds_script(base, ator_limpo)
            binds["id"] = sid
            cur = c.cursor()
            try:
                cur.execute(self._sql["SCR_INSERT"], binds)
            finally:
                cur.close()
            self._auditar(c, auditoria, "tbsss_scripts", sid)
            return self.scripts_get(sid, conn=c)

    def scripts_update(self, id, dados, esperado=None, auditoria=None, ator=None, conn=None):
        """Altera script (CKs, esperado nulo-seguro e regras de tipo_param x vinculos)."""
        ator_limpo = validate_record_actor(auditoria, ator)
        with self.write_transaction(conn=conn) as c:
            atual = self._uma(c, self._sql["SCR_GET_LOCK"], {"id": int(id)}, _COLS_SCR)
            if atual is None:
                raise repo_errors.RepoNotFound("Script ID %s nao encontrado" % id)
            self._conferir_esperado(atual, esperado, "Script", id)

            mudancas = dict((k, dados[k]) for k in _FIELDS_SCR_UPDATABLE if k in dados)
            novo = dict(atual)
            novo.update(mudancas)
            self._validar_script(novo)
            if novo["name"] != atual["name"]:
                self._nome_script_livre(c, novo["name"], int(id))
            if novo["param_type"] != atual["param_type"]:
                cur = c.cursor()
                try:
                    cur.execute(self._sql["SPRM_PARAMETERS"], {"script_id": int(id)})
                    vinculados = [r[0] for r in cur.fetchall()]
                finally:
                    cur.close()
                self._regras_tipo_param(novo["param_type"], self._flags_dos_parametros(c, vinculados))

            binds = self._binds_script(novo, ator_limpo)
            binds["id"] = int(id)
            cur = c.cursor()
            try:
                cur.execute(self._sql["SCR_UPDATE"], binds)
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflict("Script ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, auditoria, "tbsss_scripts", int(id))
            return self.scripts_get(id, conn=c)

    # -------------------------------------------------------------------------
    # Homologacao de scripts por ambiente (tbsss_script_env)
    # -------------------------------------------------------------------------

    def homologation_get(self, script_id, conn=None):
        """Retorna lista ordenada de ambiente_id homologados para o script."""
        with self.read_context(conn=conn) as c:
            if not self._existe(c, self._sql["SCR_GET"], {"id": int(script_id)}):
                raise repo_errors.RepoNotFound("Script ID %s nao encontrado" % script_id)
            cur = c.cursor()
            try:
                cur.execute(self._sql["SENV_OF_SCRIPT"], {"script_id": int(script_id)})
                return sorted(r[1] for r in cur.fetchall())
            finally:
                cur.close()

    def homologation_save(self, script_id, ambiente_ids, esperado=None, auditoria=None, ator=None, conn=None):
        """Substitui as homologacoes por diferenca (CR-006, R-f), sob o lock do script."""
        ator_limpo = validate_record_actor(auditoria, ator)
        sid = int(script_id)
        ids = sorted(set(int(x) for x in (ambiente_ids or [])))
        with self.write_transaction(conn=conn) as c:
            if not self._existe(c, self._sql["SCR_LOCK"], {"id": sid}):
                raise repo_errors.RepoNotFound("Script ID %s nao encontrado" % script_id)
            cur = c.cursor()
            try:
                cur.execute(self._sql["SENV_OF_SCRIPT"], {"script_id": sid})
                atuais = dict((r[1], r[0]) for r in cur.fetchall())
            finally:
                cur.close()
            if esperado is not None and sorted(int(x) for x in esperado) != sorted(atuais):
                raise repo_errors.RepoConflict("Homologacao do script ID %s alterada por outra operacao" % script_id)
            for aid in ids:
                if not self._existe(c, self._sql["ENV_EXISTS"], {"id": aid}):
                    raise repo_errors.RepoViolation("Ambiente ID %s nao existe" % aid,
                                                   constraint=self.constraint_name("fk", "script_env", "env"))

            remover = [{"id": atuais[a]} for a in atuais if a not in ids]
            incluir = []
            for aid in ids:
                if aid not in atuais:
                    incluir.append({"id": db_conn.next_id(c, self._seq["script_env"]),
                                    "script_id": sid, "environment_id": aid, "actor": ator_limpo})
            cur = c.cursor()
            try:
                if remover:
                    cur.executemany(self._sql["SENV_DELETE"], remover)
                if incluir:
                    cur.executemany(self._sql["SENV_INSERT"], incluir)
                if remover or incluir:
                    cur.execute(self._sql["SCR_STAMP"], {"id": sid, "actor": ator_limpo})
            finally:
                cur.close()
            self._auditar(c, auditoria, "tbsss_scripts", sid)
            return self.homologation_get(sid, conn=c)

    # -------------------------------------------------------------------------
    # Parametros (tbsss_parameters)
    # -------------------------------------------------------------------------

    def parameters_list(self, filtros=None, pagina=1, tamanho=20, conn=None):
        """Lista parametros por codigo ASC, id ASC, com qtd_scripts na mesma consulta."""
        filtros = filtros or {}
        clausulas, binds = [], {}
        if filtros.get("code"):
            clausulas.append("LOWER(p.code) LIKE :code_f ESCAPE '\\'")
            binds["code_f"] = _like_contains(filtros["code"], maiusculas=False)
        if filtros.get("label"):
            clausulas.append("LOWER(p.label) LIKE :label_f ESCAPE '\\'")
            binds["label_f"] = _like_contains(filtros["label"], maiusculas=False)
        for chave in ("component_type", "active"):
            if filtros.get(chave):
                clausulas.append("p." + chave + " = :" + chave + "_f")
                binds[chave + "_f"] = filtros[chave]
        with self.read_context(conn=conn) as c:
            return self._listar(c, _SQL_PRM_LIST, _SQL_PRM_COUNT, _COLS_PRM, clausulas, binds,
                                pagina, tamanho, extras=("qtd_scripts",))

    def parameters_get(self, id, conn=None):
        """Retorna dict do parametro pelo ID ou lanca RepoNotFound."""
        with self.read_context(conn=conn) as c:
            reg = self._uma(c, self._sql["PRM_GET"], {"id": int(id)}, _COLS_PRM)
        if reg is None:
            raise repo_errors.RepoNotFound("Parametro ID %s nao encontrado" % id)
        return reg

    def _validar_flags_parametro(self, campo, valor):
        if valor not in ("Y", "N"):
            sufixo = "sens" if campo == "sensitive" else "active"
            raise repo_errors.RepoViolation("Flag %s deve ser 'Y' ou 'N'" % campo,
                                           constraint=self._ck("parameters", sufixo))

    def _validar_tipo_componente(self, valor):
        if valor not in ("TEXT", "NUMBER", "DATE", "SELECT", "CHECKBOX"):
            raise repo_errors.RepoViolation("Tipo de componente invalido", constraint=self._ck("parameters", "ctype"))

    def _validar_flag_nomeado(self, flag):
        if flag is not None and not _RE_PRM_FLAG.match(flag):
            raise repo_errors.RepoViolation("Flag param_nomeado invalida", constraint=self._ck("parameters", "flag"))

    def parameters_insert(self, dados, auditoria=None, ator=None, conn=None):
        """Insere parametro (CKs e UK) e audita na mesma transacao."""
        ator_limpo = validate_record_actor(auditoria, ator)
        codigo = dados.get("code")
        if not codigo or not _RE_PRM_CODE.match(codigo):
            raise repo_errors.RepoViolation("Codigo de parametro invalido (esperado: 1-30 chars [a-z0-9_])",
                                           constraint=self._ck("parameters", "code"))
        tcomp = dados.get("component_type")
        flag = dados.get("param_flag") or None
        sens = dados.get("sensitive", "N")
        ativo = dados.get("active", "Y")
        with self.write_transaction(conn=conn) as c:
            # Mesma ordem do FAKE: a UK e conferida antes das demais CKs.
            if self._existe(c, self._sql["PRM_BY_CODE"], {"code": codigo}):
                raise repo_errors.RepoViolation("Parametro com codigo '%s' ja existe" % codigo,
                                               constraint=self.constraint_name("uk", "parameters", "code"))
            self._validar_tipo_componente(tcomp)
            self._validar_flag_nomeado(flag)
            self._validar_flags_parametro("sensitive", sens)
            self._validar_flags_parametro("active", ativo)
            pid = db_conn.next_id(c, self._seq["parameters"])
            cur = c.cursor()
            try:
                cur.execute(self._sql["PRM_INSERT"], {
                    "id": pid, "code": codigo, "param_flag": flag, "label": dados.get("label", ""),
                    "description": dados.get("description", ""), "component_type": tcomp,
                    "options_json": dados.get("options_json"), "default_value": dados.get("default_value"),
                    "validation_regex": dados.get("validation_regex"), "sensitive": sens, "active": ativo,
                    "actor": ator_limpo,
                })
            finally:
                cur.close()
            self._auditar(c, auditoria, "tbsss_parameters", pid)
            return self.parameters_get(pid, conn=c)

    def parameters_update(self, id, dados, esperado=None, auditoria=None, ator=None, conn=None):
        """Altera parametro com as regras de dependencia de vinculo na mesma transacao."""
        ator_limpo = validate_record_actor(auditoria, ator)
        with self.write_transaction(conn=conn) as c:
            atual = self._uma(c, self._sql["PRM_GET_LOCK"], {"id": int(id)}, _COLS_PRM)
            if atual is None:
                raise repo_errors.RepoNotFound("Parametro ID %s nao encontrado" % id)
            self._conferir_esperado(atual, esperado, "Parametro", id)

            mudancas = dict((k, dados[k]) for k in ("label", "description", "options_json", "default_value",
                                                    "validation_regex") if k in dados)
            if "param_flag" in dados:
                flag = dados["param_flag"] or None
                self._validar_flag_nomeado(flag)
                mudancas["param_flag"] = flag
            if "component_type" in dados:
                self._validar_tipo_componente(dados["component_type"])
                mudancas["component_type"] = dados["component_type"]
            for campo in ("sensitive", "active"):
                if campo in dados:
                    self._validar_flags_parametro(campo, dados[campo])
                    mudancas[campo] = dados[campo]

            # Regras de dependencia (README §10) sob o lock do parametro.
            cur = c.cursor()
            try:
                cur.execute(self._sql["PRM_SCRIPTS_LINKED"], {"parameter_id": int(id)})
                scripts = [{"param_type": r[0], "active": (r[1] or "").strip()} for r in cur.fetchall()]
            finally:
                cur.close()
            if scripts and mudancas.get("component_type", atual["component_type"]) != atual["component_type"]:
                raise repo_errors.RepoViolation("Tipo de componente com vinculos", constraint="sss_prm_tipo_vinculado")
            if "param_flag" in mudancas and mudancas["param_flag"] != atual["param_flag"] \
                    and any(s["param_type"] == "NAMED" for s in scripts):
                raise repo_errors.RepoViolation("Flag com vinculo NOMEADO", constraint="sss_prm_flag_nomeado")
            if mudancas.get("active") == "N" and atual["active"] == "Y" and any(s["active"] == "Y" for s in scripts):
                raise repo_errors.RepoViolation("Desativacao com vinculo a script ativo",
                                               constraint="sss_prm_vinculo_ativo")

            novo = dict(atual)
            novo.update(mudancas)
            cur = c.cursor()
            try:
                cur.execute(self._sql["PRM_UPDATE"], {
                    "id": int(id), "param_flag": novo["param_flag"], "label": novo["label"],
                    "description": novo["description"], "component_type": novo["component_type"],
                    "options_json": novo["options_json"], "default_value": novo["default_value"],
                    "validation_regex": novo["validation_regex"], "sensitive": novo["sensitive"],
                    "active": novo["active"], "actor": ator_limpo,
                })
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflict("Parametro ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, auditoria, "tbsss_parameters", int(id))
            return self.parameters_get(id, conn=c)

    def parameter_links(self, parametro_id, conn=None):
        """Retorna os scripts vinculados ao parametro (verificacao de desativacao)."""
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["PRM_LINKS"], {"parameter_id": int(parametro_id)})
                return [self.tuple_to_dict(_COLS_SCR, r) for r in cur.fetchall()]
            finally:
                cur.close()

    # -------------------------------------------------------------------------
    # Vinculos de parametros em scripts (tbsss_script_param)
    # -------------------------------------------------------------------------

    def script_params_get(self, script_id, conn=None):
        """Retorna os parametros vinculados ao script, por ordem, com os dados do vinculo."""
        with self.read_context(conn=conn) as c:
            if not self._existe(c, self._sql["SCR_GET"], {"id": int(script_id)}):
                raise repo_errors.RepoNotFound("Script ID %s nao encontrado" % script_id)
            cur = c.cursor()
            try:
                cur.execute(self._sql["SPRM_GET"], {"script_id": int(script_id)})
                linhas = cur.fetchall()
            finally:
                cur.close()
        resultado = []
        cols = _COLS_PRM + ("sort_order", "required", "default_value_override")
        for r in linhas:
            item = self.tuple_to_dict(cols, r)
            item["script_id"] = int(script_id)
            item["parameter_id"] = item["id"]
            resultado.append(item)
        return resultado

    def script_params_save(self, script_id, vinculos, esperado=None, auditoria=None, ator=None, conn=None):
        """Substitui os vinculos do script, preservando o created_* de quem continua (CR-006, R-f)."""
        ator_limpo = validate_record_actor(auditoria, ator)
        sid = int(script_id)
        with self.write_transaction(conn=conn) as c:
            script = self._uma(c, self._sql["SCR_GET_LOCK"], {"id": sid}, _COLS_SCR)
            if script is None:
                raise repo_errors.RepoNotFound("Script ID %s nao encontrado" % script_id)
            cur = c.cursor()
            try:
                cur.execute(self._sql["SPRM_OF_SCRIPT"], {"script_id": sid})
                anteriores_lista = [self.tuple_to_dict(_COLS_SPRM, r) for r in cur.fetchall()]
            finally:
                cur.close()
            if esperado is not None:
                lidos = [(v["parameter_id"], v["sort_order"], v["required"], v.get("default_value_override"))
                         for v in anteriores_lista]
                if [tuple(e) for e in esperado] != lidos:
                    raise repo_errors.RepoConflict("Vinculos do script ID %s alterados por outra operacao" % script_id)

            params_vistos, ordens_vistas, novos = set(), set(), []
            for item in (vinculos or []):
                pid = int(item["parameter_id"])
                if not self._existe(c, self._sql["PRM_EXISTS"], {"id": pid}):
                    raise repo_errors.RepoViolation("Parametro ID %s nao existe" % pid,
                                                   constraint=self.constraint_name("fk", "script_param", "prm"))
                if pid in params_vistos:
                    raise repo_errors.RepoViolation("Parametro duplicado no script",
                                                   constraint=self.constraint_name("uk", "script_param", "scr_prm"))
                params_vistos.add(pid)
                ordem = int(item["sort_order"])
                if ordem < 1:
                    raise repo_errors.RepoViolation("Ordem deve ser >= 1", constraint=self._ck("script_param", "sort_order"))
                if ordem in ordens_vistas:
                    raise repo_errors.RepoViolation("Ordem duplicada no script",
                                                   constraint=self.constraint_name("uk", "script_param", "scr_ord"))
                ordens_vistas.add(ordem)
                obrig = item.get("required", "Y")
                if obrig not in ("Y", "N"):
                    raise repo_errors.RepoViolation("obrigatorio deve ser 'Y' ou 'N'",
                                                   constraint=self._ck("script_param", "req"))
                novos.append({"parameter_id": pid, "sort_order": ordem, "required": obrig,
                              "default_value_override": item.get("default_value_override")})

            # Flags lidas sob lock (scripts -> parametros), em ordem de id para evitar deadlock.
            flags = self._flags_dos_parametros(c, sorted(params_vistos))
            self._regras_tipo_param(script["param_type"], flags)

            anteriores = dict((v["parameter_id"], v) for v in anteriores_lista)
            mudou = set(anteriores) != set(nv["parameter_id"] for nv in novos)
            lote_novo, lote_mantido, lote_alterado = [], [], []
            for nv in novos:
                binds = {"id": db_conn.next_id(c, self._seq["script_param"]), "script_id": sid,
                         "parameter_id": nv["parameter_id"], "sort_order": nv["sort_order"],
                         "required": nv["required"], "default_value_override": nv["default_value_override"]}
                velho = anteriores.get(nv["parameter_id"])
                if velho is None:
                    binds["actor"] = ator_limpo
                    lote_novo.append(binds)
                    continue
                binds["created_at"] = velho["created_at"]
                binds["created_by"] = velho["created_by"]
                if any(not _equal(nv[k], velho.get(k)) for k in ("sort_order", "required", "default_value_override")):
                    binds["actor"] = ator_limpo
                    lote_alterado.append(binds)
                    mudou = True
                else:
                    binds["updated_at"] = velho["updated_at"]
                    binds["updated_by"] = velho["updated_by"]
                    lote_mantido.append(binds)

            cur = c.cursor()
            try:
                cur.execute(self._sql["SPRM_DELETE_OF_SCRIPT"], {"script_id": sid})
                if lote_novo:
                    cur.executemany(self._sql["SPRM_INSERT_NEW"], lote_novo)
                if mudou:
                    cur.execute(self._sql["SCR_STAMP"], {"id": sid, "actor": ator_limpo})
            finally:
                cur.close()
            # Lotes com DATE lido do banco: bind TIPO_DATE (README §7.5), cada um no seu cursor para que
            # o setinputsizes nao alcance outro comando.
            for sql, lote, tipos in (
                (self._sql["SPRM_INSERT_CHANGED"], lote_alterado, {"created_at": db_conn.TIPO_DATE}),
                (self._sql["SPRM_INSERT"], lote_mantido,
                 {"created_at": db_conn.TIPO_DATE, "updated_at": db_conn.TIPO_DATE}),
            ):
                if not lote:
                    continue
                cur = c.cursor()
                try:
                    db_conn.set_input_types(cur, **tipos)
                    cur.executemany(sql, lote)
                finally:
                    cur.close()
            self._auditar(c, auditoria, "tbsss_scripts", sid)
            return self.script_params_get(sid, conn=c)

    # -------------------------------------------------------------------------
    # Scripts executaveis (README §4.3.A)
    # -------------------------------------------------------------------------

    def executable_scripts(self, usuario_ctx, conn=None):
        """Scripts que o usuario pode executar em ao menos um ambiente, numa unica consulta.

        Admin dispensa perfil_scr/perfil_amb (dimensoes 1 a 3), nunca a homologacao em ambiente ativo.
        Os demais exigem EXEC_SCRIPT no contexto; a matriz vem do banco pelo perfil_id (README §4.3.A).
        """
        usuario_ctx = usuario_ctx or {}
        is_admin = usuario_ctx.get("is_admin") in ("Y", True)
        if is_admin:
            sql, binds = self._sql["EXEC_ADMIN"], None
        else:
            funcs = usuario_ctx.get("features") or set()
            perfil_id = usuario_ctx.get("profile_id")
            if "EXEC_SCRIPT" not in funcs or perfil_id is None:
                return []
            sql, binds = self._sql["EXEC_PROFILE"], {"profile_id": int(perfil_id)}
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                self._executar(cur, sql, binds)
                return [self.tuple_to_dict(_COLS_SCR, r) for r in cur.fetchall()]
            finally:
                cur.close()
