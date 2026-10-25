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

from sss.persistence import db_conn
from sss.persistence import repo_errors
from sss.persistence.contracts.repo_catalog import RepoCatalog
from sss.persistence.oracle.base import BaseRepoOracle, write_audit, validate_record_actor

_RE_ENV_NAME = re.compile(r"^[A-Z0-9_]{1,30}$")
_RE_PRM_CODE = re.compile(r"^[a-z0-9_]{1,30}$")
_RE_PRM_FLAG = re.compile(r"^-{1,2}[A-Za-z0-9][A-Za-z0-9_-]{0,27}$")

_LIMIT_TOTAL = 10001
_BATCH_IN = 500

_COLS_ENV = ("id", "name", "description", "connection", "active", "is_production",
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
    "INSERT INTO {env} (id, name, description, connection, active, is_production, created_at, created_by, "
    "updated_at, updated_by) "
    "VALUES (:id, :name, :description, :connection, :active, :is_production, SYSDATE, :actor, NULL, NULL)"
)
_SQL_ENV_UPDATE = (
    "UPDATE {env} SET description = :description, connection = :connection, active = :active, "
    "is_production = :is_production, updated_at = SYSDATE, updated_by = :actor WHERE id = :id"
)

_SQL_SCR_GET = "SELECT " + _column_list(_COLS_SCR) + " FROM {scr} WHERE id = :id"
_SQL_SCR_GET_LOCK = _SQL_SCR_GET + " FOR UPDATE WAIT 5"
_SQL_SCR_LOCK = "SELECT id FROM {scr} WHERE id = :id FOR UPDATE WAIT 5"
# uk_tbsss_scr_name diferencia maiusculas (README §8.5): comparacao exata, sem UPPER/LOWER.
_SQL_SCR_NAME_IN_USE = "SELECT id FROM {scr} WHERE name = :name AND id <> :id"
_SQL_SCR_LIST = (
    "SELECT " + _column_list(_COLS_SCR, "s.") + ", "
    "(SELECT COUNT(*) FROM {sprm} sp WHERE sp.script_id = s.id) param_count "
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
    "(SELECT COUNT(*) FROM {sprm} sp WHERE sp.parameter_id = p.id) script_count "
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

# README §4.3.A: script ativo, homologado em ambiente ativo; o admin dispensa profile_script/profile_env.
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


def _like_contains(value, uppercase):
    """Trecho para LIKE ... ESCAPE '\\': '%' e '_' digitados contam como literais (como no FAKE)."""
    v = value.upper() if uppercase else value.lower()
    v = v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + v + "%"


def _page_size(page, size):
    # Valor nao numerico propaga ValueError/TypeError, como no FAKE: o controller valida antes.
    p = 1 if page is None else int(page)
    t = 20 if size is None else int(size)
    if p < 1:
        p = 1
    if t < 1:
        t = 20
    return p, t


def _equal(current_value, expected):
    """Comparacao nula-segura do 'esperado' ('' e NULL no Oracle; DATE sem fracao)."""
    if current_value == "":
        current_value = None
    if expected == "":
        expected = None
    if isinstance(current_value, datetime.datetime) and isinstance(expected, datetime.datetime):
        return current_value.replace(microsecond=0) == expected.replace(microsecond=0)
    return current_value == expected


class RepoCatalogOracle(BaseRepoOracle, RepoCatalog):
    """Repositorio de catalogo com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, secrets=None):
        super(RepoCatalogOracle, self).__init__(cfg=cfg, secrets=secrets)
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
        for name, template in globals().items():
            if name.startswith("_SQL_") and "{where" not in template and "{ids}" not in template:
                self._sql[name[5:]] = template.format(**self._idents)
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

    def _ck(self, entity, suffix):
        return self.constraint_name("ck", entity, suffix)

    def _sql_dinamico(self, template, **parts):
        """Completa um modelo com identificadores e clausulas fixas (allowlist) montadas pelo codigo."""
        values = dict(self._idents)
        values.update(parts)
        return template.format(**values)

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

    def _listar(self, conn, list_template, count_template, cols, clauses, binds, page, size, extras=()):
        """Paginacao ROWNUM (AGENTS §4.4) e COUNT limitado a 10.001 na mesma leitura."""
        p, t = _page_size(page, size)
        start = (p - 1) * t
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        where_count = " AND ".join(list(clauses) + ["ROWNUM <= " + str(_LIMIT_TOTAL)])
        sql_items = self._sql_dinamico(list_template, where=where)
        sql_page = (
            "SELECT * FROM (SELECT a.*, ROWNUM rn FROM (" + sql_items + ") a WHERE ROWNUM <= :end_ts) "
            "WHERE rn > :start_ts"
        )
        sql_count_tpl = self._sql_dinamico(count_template, where_count=where_count)
        cur = conn.cursor()
        try:
            cur.execute(sql_count_tpl, binds)
            raw = cur.fetchone()[0]
            binds_page = dict(binds)
            binds_page["start_ts"] = start
            binds_page["end_ts"] = start + t
            cur.execute(sql_page, binds_page)
            all_value = tuple(cols) + tuple(extras)
            items = [self.tuple_to_dict(all_value, r[:len(all_value)]) for r in cur.fetchall()]
        finally:
            cur.close()
        return {
            "items": items,
            "total": min(raw, _LIMIT_TOTAL),
            "page": p,
            "size": t,
            "total_capped": raw >= _LIMIT_TOTAL,
        }

    def _auditar(self, conn, audit, entity, entity_id):
        write_audit(conn, self._tbl_aud, self._seq_aud, audit, entity, entity_id)

    def _conferir_esperado(self, current_value, expected, label, id):
        for field, value in (expected or {}).items():
            if not _equal(current_value.get(field), value):
                raise repo_errors.RepoConflict("%s ID %s alterado por outra operacao (%s)" % (label, id, field))

    # -------------------------------------------------------------------------
    # Ambientes (tbsss_environments)
    # -------------------------------------------------------------------------

    def environments_list(self, filters=None, page=1, size=20, conn=None):
        """Lista ambientes paginados por nome ASC, id ASC."""
        filters = filters or {}
        clauses, binds = [], {}
        if filters.get("name"):
            clauses.append("UPPER(name) LIKE :name_f ESCAPE '\\'")
            binds["name_f"] = _like_contains(filters["name"], uppercase=True)
        if filters.get("active"):
            clauses.append("active = :active_f")
            binds["active_f"] = filters["active"]
        with self.read_context(conn=conn) as c:
            return self._listar(c, _SQL_ENV_LIST, _SQL_ENV_COUNT, _COLS_ENV, clauses, binds, page, size)

    def environments_get(self, id, conn=None):
        """Retorna dict do ambiente pelo ID ou lanca RepoNotFound."""
        with self.read_context(conn=conn) as c:
            reg = self._uma(c, self._sql["ENV_GET"], {"id": int(id)}, _COLS_ENV)
        if reg is None:
            raise repo_errors.RepoNotFound("Ambiente ID %s nao encontrado" % id)
        return reg

    def environments_insert(self, data, audit=None, actor=None, conn=None):
        """Insere ambiente (CKs, UK e DSN sem credencial) e audita na mesma transacao."""
        actor_clean = validate_record_actor(audit, actor)
        name = data.get("name")
        if not name or not _RE_ENV_NAME.match(name):
            raise repo_errors.RepoViolation("Nome de ambiente invalido (esperado: 1-30 chars [A-Z0-9_])",
                                           constraint=self._ck("environments", "name"))
        connection = data.get("connection")
        active = data.get("active", "Y")
        production = data.get("is_production", "N")

        with self.write_transaction(conn=conn) as c:
            # Mesma ordem do FAKE: UK antes das CKs. ck_..._amb_nome garante maiusculas, entao a
            # igualdade exata equivale a UK sem distincao de caixa.
            if self._existe(c, self._sql["ENV_BY_NAME"], {"name": name}):
                raise repo_errors.RepoViolation("Ambiente com nome '%s' ja existe" % name,
                                               constraint=self.constraint_name("uk", "environments", "name"))
            if connection and "@" in connection:
                raise repo_errors.RepoViolation("Conexao nao pode conter credencial (@)",
                                               constraint=self._ck("environments", "connection"))
            if active not in ("Y", "N"):
                raise repo_errors.RepoViolation("Flag ativo deve ser 'Y' ou 'N'",
                                               constraint=self._ck("environments", "active"))
            if production not in ("Y", "N"):
                raise repo_errors.RepoViolation("Flag producao deve ser 'Y' ou 'N'",
                                               constraint=self._ck("environments", "prod"))
            aid = db_conn.next_id(c, self._seq["environments"])
            cur = c.cursor()
            try:
                cur.execute(self._sql["ENV_INSERT"], {
                    "id": aid, "name": name, "description": data.get("description", ""),
                    "connection": connection, "active": active, "is_production": production,
                    "actor": actor_clean,
                })
            finally:
                cur.close()
            self._auditar(c, audit, "tbsss_environments", aid)
            return self.environments_get(aid, conn=c)

    def environments_update(self, id, data, expected=None, audit=None, actor=None, conn=None):
        """Altera ambiente (nome imutavel, tr_tbsss_env_bu), condicional a 'esperado'."""
        actor_clean = validate_record_actor(audit, actor)
        with self.write_transaction(conn=conn) as c:
            current = self._uma(c, self._sql["ENV_GET_LOCK"], {"id": int(id)}, _COLS_ENV)
            if current is None:
                raise repo_errors.RepoNotFound("Ambiente ID %s nao encontrado" % id)
            self._conferir_esperado(current, expected, "Ambiente", id)

            new_name = data.get("name")
            if new_name is not None and new_name != current["name"]:
                raise repo_errors.RepoViolation("Nome de ambiente e imutavel",
                                               constraint=self.trigger_name("environments", "bu"))
            new = dict(current)
            new_connection = data.get("connection")
            if new_connection is not None:
                if "@" in new_connection:
                    raise repo_errors.RepoViolation("Conexao nao pode conter credencial (@)",
                                                   constraint=self._ck("environments", "connection"))
                new["connection"] = new_connection
            elif "connection" in data:
                new["connection"] = None
            if "description" in data:
                new["description"] = data["description"]
            new_active = data.get("active")
            if new_active is not None:
                if new_active not in ("Y", "N"):
                    raise repo_errors.RepoViolation("Flag ativo deve ser 'Y' ou 'N'",
                                                   constraint=self._ck("environments", "active"))
                new["active"] = new_active
            new_production = data.get("is_production")
            if new_production is not None:
                if new_production not in ("Y", "N"):
                    raise repo_errors.RepoViolation("Flag producao deve ser 'Y' ou 'N'",
                                                   constraint=self._ck("environments", "prod"))
                new["is_production"] = new_production

            cur = c.cursor()
            try:
                cur.execute(self._sql["ENV_UPDATE"], {
                    "id": int(id), "description": new["description"], "connection": new["connection"],
                    "active": new["active"], "is_production": new["is_production"], "actor": actor_clean,
                })
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflict("Ambiente ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, audit, "tbsss_environments", int(id))
            return self.environments_get(id, conn=c)

    # -------------------------------------------------------------------------
    # Scripts (tbsss_scripts)
    # -------------------------------------------------------------------------

    def _homologados_por_script(self, conn, script_ids):
        """{script_id: [nomes em ordem alfabetica]} com IN por contagem controlada, em lotes."""
        result = dict((sid, []) for sid in script_ids)
        ids = list(script_ids)
        cur = conn.cursor()
        try:
            for i in range(0, len(ids), _BATCH_IN):
                batch = ids[i:i + _BATCH_IN]
                marks = ", ".join(":s%d" % n for n in range(len(batch)))
                binds = dict(("s%d" % n, v) for n, v in enumerate(batch))
                cur.execute(self._sql_dinamico(_SQL_SCR_HOMOLOGATED, ids=marks), binds)
                for sid, name in cur.fetchall():
                    result[sid].append(name)
        finally:
            cur.close()
        for names in result.values():
            names.sort()
        return result

    def scripts_list(self, filters=None, page=1, size=20, conn=None):
        """Lista scripts por nome ASC, id ASC, com homologated_environments e param_count."""
        filters = filters or {}
        clauses, binds = [], {}
        if filters.get("name"):
            clauses.append("LOWER(s.name) LIKE :name_f ESCAPE '\\'")
            binds["name_f"] = _like_contains(filters["name"], uppercase=False)
        for key in ("script_group", "category", "interpreter", "active"):
            if filters.get(key):
                clauses.append("s." + key + " = :" + key + "_f")
                binds[key + "_f"] = filters[key]
        with self.read_context(conn=conn) as c:
            page_ = self._listar(c, _SQL_SCR_LIST, _SQL_SCR_COUNT, _COLS_SCR, clauses, binds,
                                   page, size, extras=("param_count",))
            homolog = self._homologados_por_script(c, [it["id"] for it in page_["items"]])
        for item in page_["items"]:
            item["homologated_environments"] = homolog.get(item["id"], [])
        return page_

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

    def _nome_script_livre(self, conn, name, current_id):
        if self._existe(conn, self._sql["SCR_NAME_IN_USE"], {"name": name, "id": current_id}):
            raise repo_errors.RepoViolation("Script com nome '%s' ja existe" % name,
                                           constraint=self.constraint_name("uk", "scripts", "name"))

    def _flags_dos_parametros(self, conn, parameter_ids):
        """Trava os parametros (scripts -> parametros) e devolve {id: param_nomeado}; ausente = FK."""
        flags = {}
        for pid in parameter_ids:
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

    def _regras_tipo_param(self, param_type, flags):
        # README §6.3: NENHUM nao aceita vinculos; NOMEADO exige flag em todo parametro vinculado.
        if param_type == "NONE" and flags:
            raise repo_errors.RepoViolation("Script NENHUM com vinculos", constraint="sss_scr_nenhum_vinculado")
        if param_type == "NAMED":
            for pid in flags:
                if not flags[pid]:
                    raise repo_errors.RepoViolation("Parametro sem flag em script NOMEADO",
                                                   constraint="sss_scr_nomeado_sem_flag")

    def _binds_script(self, reg, actor):
        tmout = reg.get("timeout_s")
        return {
            "name": reg["name"], "description": reg.get("description"), "script_group": reg.get("script_group"),
            "category": reg.get("category"), "stage": reg.get("stage"),
            "interpreter": reg["interpreter"], "path_file": reg["path_file"],
            "param_type": reg.get("param_type", "NAMED"),
            "max_parallel_env": int(reg.get("max_parallel_env", 1)),
            "timeout_s": int(tmout) if tmout is not None else None,
            "active": reg.get("active", "Y"),
            "actor": actor,
        }

    def scripts_insert(self, data, audit=None, actor=None, conn=None):
        """Insere script (CKs, UK sensivel a maiusculas) e audita na mesma transacao."""
        actor_clean = validate_record_actor(audit, actor)
        base = dict(data)
        base.setdefault("description", "")
        self._validar_script(base)
        with self.write_transaction(conn=conn) as c:
            self._nome_script_livre(c, base["name"], 0)
            sid = db_conn.next_id(c, self._seq["scripts"])
            binds = self._binds_script(base, actor_clean)
            binds["id"] = sid
            cur = c.cursor()
            try:
                cur.execute(self._sql["SCR_INSERT"], binds)
            finally:
                cur.close()
            self._auditar(c, audit, "tbsss_scripts", sid)
            return self.scripts_get(sid, conn=c)

    def scripts_update(self, id, data, expected=None, audit=None, actor=None, conn=None):
        """Altera script (CKs, esperado nulo-seguro e regras de param_type x vinculos)."""
        actor_clean = validate_record_actor(audit, actor)
        with self.write_transaction(conn=conn) as c:
            current = self._uma(c, self._sql["SCR_GET_LOCK"], {"id": int(id)}, _COLS_SCR)
            if current is None:
                raise repo_errors.RepoNotFound("Script ID %s nao encontrado" % id)
            self._conferir_esperado(current, expected, "Script", id)

            changes = dict((k, data[k]) for k in _FIELDS_SCR_UPDATABLE if k in data)
            new = dict(current)
            new.update(changes)
            self._validar_script(new)
            if new["name"] != current["name"]:
                self._nome_script_livre(c, new["name"], int(id))
            if new["param_type"] != current["param_type"]:
                cur = c.cursor()
                try:
                    cur.execute(self._sql["SPRM_PARAMETERS"], {"script_id": int(id)})
                    linked = [r[0] for r in cur.fetchall()]
                finally:
                    cur.close()
                self._regras_tipo_param(new["param_type"], self._flags_dos_parametros(c, linked))

            binds = self._binds_script(new, actor_clean)
            binds["id"] = int(id)
            cur = c.cursor()
            try:
                cur.execute(self._sql["SCR_UPDATE"], binds)
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflict("Script ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, audit, "tbsss_scripts", int(id))
            return self.scripts_get(id, conn=c)

    # -------------------------------------------------------------------------
    # Homologacao de scripts por ambiente (tbsss_script_env)
    # -------------------------------------------------------------------------

    def homologation_get(self, script_id, conn=None):
        """Retorna lista ordenada de environment_id homologados para o script."""
        with self.read_context(conn=conn) as c:
            if not self._existe(c, self._sql["SCR_GET"], {"id": int(script_id)}):
                raise repo_errors.RepoNotFound("Script ID %s nao encontrado" % script_id)
            cur = c.cursor()
            try:
                cur.execute(self._sql["SENV_OF_SCRIPT"], {"script_id": int(script_id)})
                return sorted(r[1] for r in cur.fetchall())
            finally:
                cur.close()

    def homologation_save(self, script_id, environment_ids, expected=None, audit=None, actor=None, conn=None):
        """Substitui as homologacoes por diferenca (CR-006, R-f), sob o lock do script."""
        actor_clean = validate_record_actor(audit, actor)
        sid = int(script_id)
        ids = sorted(set(int(x) for x in (environment_ids or [])))
        with self.write_transaction(conn=conn) as c:
            if not self._existe(c, self._sql["SCR_LOCK"], {"id": sid}):
                raise repo_errors.RepoNotFound("Script ID %s nao encontrado" % script_id)
            cur = c.cursor()
            try:
                cur.execute(self._sql["SENV_OF_SCRIPT"], {"script_id": sid})
                current = dict((r[1], r[0]) for r in cur.fetchall())
            finally:
                cur.close()
            if expected is not None and sorted(int(x) for x in expected) != sorted(current):
                raise repo_errors.RepoConflict("Homologacao do script ID %s alterada por outra operacao" % script_id)
            for aid in ids:
                if not self._existe(c, self._sql["ENV_EXISTS"], {"id": aid}):
                    raise repo_errors.RepoViolation("Ambiente ID %s nao existe" % aid,
                                                   constraint=self.constraint_name("fk", "script_env", "env"))

            remove = [{"id": current[a]} for a in current if a not in ids]
            include = []
            for aid in ids:
                if aid not in current:
                    include.append({"id": db_conn.next_id(c, self._seq["script_env"]),
                                    "script_id": sid, "environment_id": aid, "actor": actor_clean})
            cur = c.cursor()
            try:
                if remove:
                    cur.executemany(self._sql["SENV_DELETE"], remove)
                if include:
                    cur.executemany(self._sql["SENV_INSERT"], include)
                if remove or include:
                    cur.execute(self._sql["SCR_STAMP"], {"id": sid, "actor": actor_clean})
            finally:
                cur.close()
            self._auditar(c, audit, "tbsss_scripts", sid)
            return self.homologation_get(sid, conn=c)

    # -------------------------------------------------------------------------
    # Parametros (tbsss_parameters)
    # -------------------------------------------------------------------------

    def parameters_list(self, filters=None, page=1, size=20, conn=None):
        """Lista parametros por codigo ASC, id ASC, com script_count na mesma consulta."""
        filters = filters or {}
        clauses, binds = [], {}
        if filters.get("code"):
            clauses.append("LOWER(p.code) LIKE :code_f ESCAPE '\\'")
            binds["code_f"] = _like_contains(filters["code"], uppercase=False)
        if filters.get("label"):
            clauses.append("LOWER(p.label) LIKE :label_f ESCAPE '\\'")
            binds["label_f"] = _like_contains(filters["label"], uppercase=False)
        for key in ("component_type", "active"):
            if filters.get(key):
                clauses.append("p." + key + " = :" + key + "_f")
                binds[key + "_f"] = filters[key]
        with self.read_context(conn=conn) as c:
            return self._listar(c, _SQL_PRM_LIST, _SQL_PRM_COUNT, _COLS_PRM, clauses, binds,
                                page, size, extras=("script_count",))

    def parameters_get(self, id, conn=None):
        """Retorna dict do parametro pelo ID ou lanca RepoNotFound."""
        with self.read_context(conn=conn) as c:
            reg = self._uma(c, self._sql["PRM_GET"], {"id": int(id)}, _COLS_PRM)
        if reg is None:
            raise repo_errors.RepoNotFound("Parametro ID %s nao encontrado" % id)
        return reg

    def _validar_flags_parametro(self, field, value):
        if value not in ("Y", "N"):
            suffix = "sens" if field == "sensitive" else "active"
            raise repo_errors.RepoViolation("Flag %s deve ser 'Y' ou 'N'" % field,
                                           constraint=self._ck("parameters", suffix))

    def _validar_tipo_componente(self, value):
        if value not in ("TEXT", "NUMBER", "DATE", "SELECT", "CHECKBOX"):
            raise repo_errors.RepoViolation("Tipo de componente invalido", constraint=self._ck("parameters", "ctype"))

    def _validar_flag_nomeado(self, flag):
        if flag is not None and not _RE_PRM_FLAG.match(flag):
            raise repo_errors.RepoViolation("Flag param_nomeado invalida", constraint=self._ck("parameters", "flag"))

    def parameters_insert(self, data, audit=None, actor=None, conn=None):
        """Insere parametro (CKs e UK) e audita na mesma transacao."""
        actor_clean = validate_record_actor(audit, actor)
        code = data.get("code")
        if not code or not _RE_PRM_CODE.match(code):
            raise repo_errors.RepoViolation("Codigo de parametro invalido (esperado: 1-30 chars [a-z0-9_])",
                                           constraint=self._ck("parameters", "code"))
        tcomp = data.get("component_type")
        flag = data.get("param_flag") or None
        sens = data.get("sensitive", "N")
        active = data.get("active", "Y")
        with self.write_transaction(conn=conn) as c:
            # Mesma ordem do FAKE: a UK e conferida antes das demais CKs.
            if self._existe(c, self._sql["PRM_BY_CODE"], {"code": code}):
                raise repo_errors.RepoViolation("Parametro com codigo '%s' ja existe" % code,
                                               constraint=self.constraint_name("uk", "parameters", "code"))
            self._validar_tipo_componente(tcomp)
            self._validar_flag_nomeado(flag)
            self._validar_flags_parametro("sensitive", sens)
            self._validar_flags_parametro("active", active)
            pid = db_conn.next_id(c, self._seq["parameters"])
            cur = c.cursor()
            try:
                cur.execute(self._sql["PRM_INSERT"], {
                    "id": pid, "code": code, "param_flag": flag, "label": data.get("label", ""),
                    "description": data.get("description", ""), "component_type": tcomp,
                    "options_json": data.get("options_json"), "default_value": data.get("default_value"),
                    "validation_regex": data.get("validation_regex"), "sensitive": sens, "active": active,
                    "actor": actor_clean,
                })
            finally:
                cur.close()
            self._auditar(c, audit, "tbsss_parameters", pid)
            return self.parameters_get(pid, conn=c)

    def parameters_update(self, id, data, expected=None, audit=None, actor=None, conn=None):
        """Altera parametro com as regras de dependencia de vinculo na mesma transacao."""
        actor_clean = validate_record_actor(audit, actor)
        with self.write_transaction(conn=conn) as c:
            current = self._uma(c, self._sql["PRM_GET_LOCK"], {"id": int(id)}, _COLS_PRM)
            if current is None:
                raise repo_errors.RepoNotFound("Parametro ID %s nao encontrado" % id)
            self._conferir_esperado(current, expected, "Parametro", id)

            changes = dict((k, data[k]) for k in ("label", "description", "options_json", "default_value",
                                                    "validation_regex") if k in data)
            if "param_flag" in data:
                flag = data["param_flag"] or None
                self._validar_flag_nomeado(flag)
                changes["param_flag"] = flag
            if "component_type" in data:
                self._validar_tipo_componente(data["component_type"])
                changes["component_type"] = data["component_type"]
            for field in ("sensitive", "active"):
                if field in data:
                    self._validar_flags_parametro(field, data[field])
                    changes[field] = data[field]

            # Regras de dependencia (README §10) sob o lock do parametro.
            cur = c.cursor()
            try:
                cur.execute(self._sql["PRM_SCRIPTS_LINKED"], {"parameter_id": int(id)})
                scripts = [{"param_type": r[0], "active": (r[1] or "").strip()} for r in cur.fetchall()]
            finally:
                cur.close()
            if scripts and changes.get("component_type", current["component_type"]) != current["component_type"]:
                raise repo_errors.RepoViolation("Tipo de componente com vinculos", constraint="sss_prm_tipo_vinculado")
            if "param_flag" in changes and changes["param_flag"] != current["param_flag"] \
                    and any(s["param_type"] == "NAMED" for s in scripts):
                raise repo_errors.RepoViolation("Flag com vinculo NOMEADO", constraint="sss_prm_flag_nomeado")
            if changes.get("active") == "N" and current["active"] == "Y" and any(s["active"] == "Y" for s in scripts):
                raise repo_errors.RepoViolation("Desativacao com vinculo a script ativo",
                                               constraint="sss_prm_vinculo_ativo")

            new = dict(current)
            new.update(changes)
            cur = c.cursor()
            try:
                cur.execute(self._sql["PRM_UPDATE"], {
                    "id": int(id), "param_flag": new["param_flag"], "label": new["label"],
                    "description": new["description"], "component_type": new["component_type"],
                    "options_json": new["options_json"], "default_value": new["default_value"],
                    "validation_regex": new["validation_regex"], "sensitive": new["sensitive"],
                    "active": new["active"], "actor": actor_clean,
                })
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflict("Parametro ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, audit, "tbsss_parameters", int(id))
            return self.parameters_get(id, conn=c)

    def parameter_links(self, parameter_id, conn=None):
        """Retorna os scripts vinculados ao parametro (verificacao de desativacao)."""
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["PRM_LINKS"], {"parameter_id": int(parameter_id)})
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
                rows = cur.fetchall()
            finally:
                cur.close()
        result = []
        cols = _COLS_PRM + ("sort_order", "required", "default_value_override")
        for r in rows:
            item = self.tuple_to_dict(cols, r)
            item["script_id"] = int(script_id)
            item["parameter_id"] = item["id"]
            result.append(item)
        return result

    def script_params_save(self, script_id, links, expected=None, audit=None, actor=None, conn=None):
        """Substitui os vinculos do script, preservando o created_* de quem continua (CR-006, R-f)."""
        actor_clean = validate_record_actor(audit, actor)
        sid = int(script_id)
        with self.write_transaction(conn=conn) as c:
            script = self._uma(c, self._sql["SCR_GET_LOCK"], {"id": sid}, _COLS_SCR)
            if script is None:
                raise repo_errors.RepoNotFound("Script ID %s nao encontrado" % script_id)
            cur = c.cursor()
            try:
                cur.execute(self._sql["SPRM_OF_SCRIPT"], {"script_id": sid})
                previous_items = [self.tuple_to_dict(_COLS_SPRM, r) for r in cur.fetchall()]
            finally:
                cur.close()
            if expected is not None:
                read = [(v["parameter_id"], v["sort_order"], v["required"], v.get("default_value_override"))
                         for v in previous_items]
                if [tuple(e) for e in expected] != read:
                    raise repo_errors.RepoConflict("Vinculos do script ID %s alterados por outra operacao" % script_id)

            params_seen, orders_seen, new = set(), set(), []
            for item in (links or []):
                pid = int(item["parameter_id"])
                if not self._existe(c, self._sql["PRM_EXISTS"], {"id": pid}):
                    raise repo_errors.RepoViolation("Parametro ID %s nao existe" % pid,
                                                   constraint=self.constraint_name("fk", "script_param", "prm"))
                if pid in params_seen:
                    raise repo_errors.RepoViolation("Parametro duplicado no script",
                                                   constraint=self.constraint_name("uk", "script_param", "scr_prm"))
                params_seen.add(pid)
                order = int(item["sort_order"])
                if order < 1:
                    raise repo_errors.RepoViolation("Ordem deve ser >= 1", constraint=self._ck("script_param", "sort_order"))
                if order in orders_seen:
                    raise repo_errors.RepoViolation("Ordem duplicada no script",
                                                   constraint=self.constraint_name("uk", "script_param", "scr_ord"))
                orders_seen.add(order)
                req = item.get("required", "Y")
                if req not in ("Y", "N"):
                    raise repo_errors.RepoViolation("obrigatorio deve ser 'Y' ou 'N'",
                                                   constraint=self._ck("script_param", "req"))
                new.append({"parameter_id": pid, "sort_order": order, "required": req,
                              "default_value_override": item.get("default_value_override")})

            # Flags lidas sob lock (scripts -> parametros), em ordem de id para evitar deadlock.
            flags = self._flags_dos_parametros(c, sorted(params_seen))
            self._regras_tipo_param(script["param_type"], flags)

            previous = dict((v["parameter_id"], v) for v in previous_items)
            changed = set(previous) != set(nv["parameter_id"] for nv in new)
            batch_new, batch_kept, batch_changed = [], [], []
            for nv in new:
                binds = {"id": db_conn.next_id(c, self._seq["script_param"]), "script_id": sid,
                         "parameter_id": nv["parameter_id"], "sort_order": nv["sort_order"],
                         "required": nv["required"], "default_value_override": nv["default_value_override"]}
                old = previous.get(nv["parameter_id"])
                if old is None:
                    binds["actor"] = actor_clean
                    batch_new.append(binds)
                    continue
                binds["created_at"] = old["created_at"]
                binds["created_by"] = old["created_by"]
                if any(not _equal(nv[k], old.get(k)) for k in ("sort_order", "required", "default_value_override")):
                    binds["actor"] = actor_clean
                    batch_changed.append(binds)
                    changed = True
                else:
                    binds["updated_at"] = old["updated_at"]
                    binds["updated_by"] = old["updated_by"]
                    batch_kept.append(binds)

            cur = c.cursor()
            try:
                cur.execute(self._sql["SPRM_DELETE_OF_SCRIPT"], {"script_id": sid})
                if batch_new:
                    cur.executemany(self._sql["SPRM_INSERT_NEW"], batch_new)
                if changed:
                    cur.execute(self._sql["SCR_STAMP"], {"id": sid, "actor": actor_clean})
            finally:
                cur.close()
            # Lotes com DATE lido do banco: bind TIPO_DATE (README §7.5), cada um no seu cursor para que
            # o setinputsizes nao alcance outro comando.
            for sql, batch, kinds in (
                (self._sql["SPRM_INSERT_CHANGED"], batch_changed, {"created_at": db_conn.TIPO_DATE}),
                (self._sql["SPRM_INSERT"], batch_kept,
                 {"created_at": db_conn.TIPO_DATE, "updated_at": db_conn.TIPO_DATE}),
            ):
                if not batch:
                    continue
                cur = c.cursor()
                try:
                    db_conn.set_input_types(cur, **kinds)
                    cur.executemany(sql, batch)
                finally:
                    cur.close()
            self._auditar(c, audit, "tbsss_scripts", sid)
            return self.script_params_get(sid, conn=c)

    # -------------------------------------------------------------------------
    # Scripts executaveis (README §4.3.A)
    # -------------------------------------------------------------------------

    def executable_scripts(self, user_ctx, conn=None):
        """Scripts que o usuario pode executar em ao menos um ambiente, numa unica consulta.

        Admin dispensa profile_script/profile_env (dimensoes 1 a 3), nunca a homologacao em ambiente ativo.
        Os demais exigem EXEC_SCRIPT no contexto; a matriz vem do banco pelo profile_id (README §4.3.A).
        """
        user_ctx = user_ctx or {}
        is_admin = user_ctx.get("is_admin") in ("Y", True)
        if is_admin:
            sql, binds = self._sql["EXEC_ADMIN"], None
        else:
            features = user_ctx.get("features") or set()
            profile_id = user_ctx.get("profile_id")
            if "EXEC_SCRIPT" not in features or profile_id is None:
                return []
            sql, binds = self._sql["EXEC_PROFILE"], {"profile_id": int(profile_id)}
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                self._executar(cur, sql, binds)
                return [self.tuple_to_dict(_COLS_SCR, r) for r in cur.fetchall()]
            finally:
                cur.close()
