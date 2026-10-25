# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de agendamentos (F7.3, agregado AGENDAMENTOS; AGENTS §4).

tbsss_schedules com a mesma semantica do repo_fake/schedules.py (README §2.5):
- SQL estatico com binds; os modelos ficam nas constantes abaixo e recebem, uma vez por instancia,
  somente identificadores qualificados por sql_ident (owner e prefixo validados);
- CKs e FKs conferidas antes do DML, na ordem do FAKE e com os mesmos nomes (sem gravacao parcial);
- pausar condicional a ativo = 'S' e, quando informada, a next_run lida (CR-007, R-19):
  rowcount = 0 vira RepoConflict; binds de DATE como TIPO_DATE (README §7.5), sem microssegundos;
- colunas de registro (CR-006, R-g): created_* e o criador original; alterar, pausar e retomar
  gravam updated_* com o ator;
- listar traz parametros_json (CLOB pequeno com as respostas): excecao documentada no README §2.5,
  porque o service avalia cada regra com ele; log_output nunca entra em listagem.
"""
import datetime
import re

from sss.persistence import db_conn
from sss.persistence import repo_errors
from sss.persistence.contracts.repo_schedules import RepoSchedules
from sss.persistence.oracle.base import BaseRepoOracle, write_audit, validate_record_actor

_LIMIT_TOTAL = 10001
_TYPES = ("ONCE", "DAILY", "WEEKLY", "MONTHLY", "CRON")
_REASONS_PAUSE = ("USER_INACTIVE", "NO_PERMISSION", "SCRIPT_INACTIVE", "ENVIRONMENT_INACTIVE",
                  "INVALID_PARAM", "INVALID_CRON", "COMPLETED", "MANUAL", "INTERNAL_ERROR")
_RE_TIME = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
_RE_WDAY = re.compile(r"^[1-7](,[1-7]){0,6}$")
_SIZE_NAME = 60

_COLS = ("id", "name", "script_id", "environment", "user_id", "priority", "recurrence_type",
         "cron_expression", "run_time", "week_days", "month_day", "params_json", "start_date",
         "end_date", "next_run_at", "last_run_at", "last_ticket_id", "pause_reason", "active",
         "created_at", "created_by", "updated_at", "updated_by")
_COLUMNS_UPDATABLE = ("name", "script_id", "environment", "user_id", "priority",
                       "recurrence_type", "cron_expression", "run_time", "week_days",
                       "month_day", "params_json", "start_date", "end_date",
                       "next_run_at", "last_run_at", "last_ticket_id",
                       "pause_reason", "active")
_DATES = ("start_date", "end_date", "next_run_at", "last_run_at")


def _column_list(cols, alias=""):
    return ", ".join(alias + c for c in cols)


# -----------------------------------------------------------------------------
# SQL estatico. {agd}, {scr}, {usr}, {amb} e {tck} recebem apenas nomes qualificados por sql_ident
# (validados); todo valor entra por bind.
# -----------------------------------------------------------------------------

_SQL_GET = "SELECT " + _column_list(_COLS) + " FROM {sch} WHERE id = :id"
_SQL_GET_LOCK = _SQL_GET + " FOR UPDATE WAIT 5"
_SQL_EXISTS = "SELECT id FROM {sch} WHERE id = :id"
_SQL_LIST = "SELECT " + _column_list(_COLS) + " FROM {sch}{where} ORDER BY next_run_at, id"
_SQL_COUNT = "SELECT COUNT(*) FROM (SELECT id FROM {sch} WHERE {where_count})"
_SQL_SCR_EXISTS = "SELECT id FROM {scr} WHERE id = :id"
_SQL_USR_EXISTS = "SELECT id FROM {usr} WHERE id = :id"
_SQL_ENV_EXISTS = "SELECT id FROM {env} WHERE name = :name"
_SQL_TICKET_STATUS = "SELECT status FROM {tck} WHERE id = :id"
_SQL_INSERT = (
    "INSERT INTO {sch} (id, name, script_id, environment, user_id, priority, recurrence_type, "
    "cron_expression, run_time, week_days, month_day, params_json, start_date, end_date, "
    "next_run_at, last_run_at, last_ticket_id, pause_reason, active, "
    "created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :name, :script_id, :environment, :user_id, :priority, :recurrence_type, "
    ":cron_expression, :run_time, :week_days, :month_day, :params_json, :start_date, :end_date, "
    ":next_run_at, :last_run_at, :last_ticket_id, :pause_reason, :active, "
    "SYSDATE, :actor, NULL, NULL)"
)
_SQL_UPDATE = (
    "UPDATE {sch} SET name = :name, script_id = :script_id, environment = :environment, user_id = :user_id, "
    "priority = :priority, recurrence_type = :recurrence_type, cron_expression = :cron_expression, "
    "run_time = :run_time, week_days = :week_days, month_day = :month_day, "
    "params_json = :params_json, start_date = :start_date, end_date = :end_date, "
    "next_run_at = :next_run_at, last_run_at = :last_run_at, "
    "last_ticket_id = :last_ticket_id, pause_reason = :pause_reason, active = :active, "
    "updated_at = SYSDATE, updated_by = :actor WHERE id = :id"
)
# CR-007, R-19: so pausa regra ativa e, com old_date, so se a next_run lida nao mudou.
_SQL_PAUSE = (
    "UPDATE {sch} SET active = 'N', pause_reason = :reason, updated_at = SYSDATE, updated_by = :actor "
    "WHERE id = :id AND active = 'Y'"
)
_SQL_PAUSE_OPTIMISTIC = _SQL_PAUSE + " AND next_run_at = :old_date"
_SQL_RESUME = (
    "UPDATE {sch} SET active = 'Y', pause_reason = NULL, next_run_at = :new_date, "
    "updated_at = SYSDATE, updated_by = :actor WHERE id = :id"
)


def _null(value):
    # O Oracle grava '' como NULL.
    return value is None or value == ""


def _equal(current_value, expected):
    """Comparacao nula-segura do 'esperado' ('' e NULL no Oracle; DATE sem fracao)."""
    if current_value == "":
        current_value = None
    if expected == "":
        expected = None
    if isinstance(current_value, datetime.datetime) and isinstance(expected, datetime.datetime):
        return current_value.replace(microsecond=0) == expected.replace(microsecond=0)
    return current_value == expected


def _read_lob(value):
    if value is not None and hasattr(value, "read"):
        return value.read()
    return value


class RepoSchedulesOracle(BaseRepoOracle, RepoSchedules):
    """Repositorio de agendamentos com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, secrets=None):
        super(RepoSchedulesOracle, self).__init__(cfg=cfg, secrets=secrets)
        self._idents = {
            "sch": self.qualify_table("schedules"),
            "scr": self.qualify_table("scripts"),
            "usr": self.qualify_table("users"),
            "env": self.qualify_table("environments"),
            "tck": self.qualify_table("tickets"),
        }
        self._sql = {}
        for name, template in globals().items():
            if name.startswith("_SQL_") and "{where" not in template:
                self._sql[name[5:]] = template.format(**self._idents)
        self._tbl_aud = self.qualify_table("audit")
        self._seq_aud = self.qualify_sequence("audit")
        self._seq_sch = self.qualify_sequence("schedules")

    # -------------------------------------------------------------------------
    # Utilitarios
    # -------------------------------------------------------------------------

    def _ck(self, suffix):
        return self.constraint_name("ck", "schedules", suffix)

    def _checar_cks(self, r):
        """Espelha NOT NULL e as CKs de tbsss_schedules (README §10, tabela 12), na ordem do FAKE."""
        name = r.get("name")
        if _null(name) or len(name) > _SIZE_NAME:
            # NOT NULL e tamanho da coluna nao sao constraints nomeadas (ORA-01400 / ORA-12899).
            raise repo_errors.RepoViolation("nome obrigatorio com ate %d caracteres" % _SIZE_NAME)
        trec = r.get("recurrence_type")
        if trec not in _TYPES:
            raise repo_errors.RepoViolation("tipo_recorrencia invalido", constraint=self._ck("rtype"))
        prio = r.get("priority")
        if isinstance(prio, bool) or not isinstance(prio, int) or not (1 <= prio <= 4):
            raise repo_errors.RepoViolation("prioridade deve estar entre 1 e 4", constraint=self._ck("prio"))
        if r.get("active") not in ("Y", "N"):
            raise repo_errors.RepoViolation("ativo deve ser 'Y' ou 'N'", constraint=self._ck("active"))
        day = r.get("month_day")
        if not _null(day) and (isinstance(day, bool) or not isinstance(day, int) or not (1 <= day <= 31)):
            raise repo_errors.RepoViolation("dia_mes deve estar entre 1 e 31", constraint=self._ck("day"))
        hour = r.get("run_time")
        if not _null(hour) and not _RE_TIME.match(hour):
            raise repo_errors.RepoViolation("hora_execucao fora do formato HH:MM", constraint=self._ck("time"))
        wday = r.get("week_days")
        if not _null(wday) and not _RE_WDAY.match(wday):
            raise repo_errors.RepoViolation("dias_semana fora do formato ISO 1-7", constraint=self._ck("wday"))
        if r.get("start_date") is None or r.get("next_run_at") is None:
            raise repo_errors.RepoViolation("data_inicio e proxima_execucao sao obrigatorias")
        if r.get("end_date") is not None and r["end_date"] < r["start_date"]:
            raise repo_errors.RepoViolation("data_fim anterior a data_inicio", constraint=self._ck("end"))
        if not _null(r.get("pause_reason")) and r["pause_reason"] not in _REASONS_PAUSE:
            raise repo_errors.RepoViolation("pausa_motivo invalido", constraint=self._ck("pause"))
        required = {"DAILY": ("run_time",), "WEEKLY": ("run_time", "week_days"),
                    "MONTHLY": ("run_time", "month_day"), "CRON": ("cron_expression",)}
        for column in required.get(trec, ()):
            if _null(r.get(column)):
                raise repo_errors.RepoViolation("%s obrigatorio para %s" % (column, trec),
                                               constraint=self._ck("fields"))

    def _existe(self, conn, sql, binds):
        cur = conn.cursor()
        try:
            cur.execute(sql, binds)
            return cur.fetchone() is not None
        finally:
            cur.close()

    def _checar_fks(self, conn, reg):
        for exists, suffix in (
            (self._existe(conn, self._sql["SCR_EXISTS"], {"id": int(reg["script_id"])}), "scr"),
            (self._existe(conn, self._sql["USR_EXISTS"], {"id": int(reg["user_id"])}), "usr"),
            (self._existe(conn, self._sql["ENV_EXISTS"], {"name": reg["environment"]}), "env"),
        ):
            if not exists:
                constraint = self.constraint_name("fk", "schedules", suffix)
                raise repo_errors.RepoViolation("Referencia inexistente (%s)" % constraint, constraint=constraint)

    def _linha(self, row):
        reg = self.tuple_to_dict(_COLS, row[:len(_COLS)])
        reg["params_json"] = _read_lob(reg["params_json"])
        return reg

    def _uma(self, conn, sql, binds):
        cur = conn.cursor()
        try:
            cur.execute(sql, binds)
            row = cur.fetchone()
            return self._linha(row) if row else None
        finally:
            cur.close()

    def _binds_registro(self, reg, actor):
        binds = dict((c, reg.get(c)) for c in _COLUMNS_UPDATABLE)
        binds["script_id"] = int(reg["script_id"])
        binds["user_id"] = int(reg["user_id"])
        binds["actor"] = actor
        return binds

    @staticmethod
    def _tipos(cur):
        kinds = dict((c, db_conn.TIPO_DATE) for c in _DATES)
        kinds["params_json"] = db_conn.TIPO_CLOB
        db_conn.set_input_types(cur, **kinds)

    def _auditar(self, conn, audit, id, default_action=None, default_detail=None, actor=None):
        if audit:
            write_audit(conn, self._tbl_aud, self._seq_aud, audit, "tbsss_schedules", id)
        elif default_action:
            write_audit(conn, self._tbl_aud, self._seq_aud,
                             {"actor": actor, "ip": None, "action": default_action, "detail": default_detail},
                             "tbsss_schedules", id)

    def _conferir_esperado(self, id, current_value, expected):
        for field, value in (expected or {}).items():
            if not _equal(current_value.get(field), value):
                raise repo_errors.RepoConflict("Agendamento ID %s alterado por outra operacao (%s)" % (id, field))

    # -------------------------------------------------------------------------
    # Leituras
    # -------------------------------------------------------------------------

    def list(self, filters=None, page=1, size=20, environment_scope=None, conn=None):
        """Lista por next_run, id, com total limitado a 10.001 (traz parametros_json, sem log)."""
        filters = filters or {}
        clauses, binds = [], {}
        if environment_scope is not None:
            envs = sorted(set(environment_scope))
            if not envs:
                clauses.append("1 = 0")
            else:
                marks = []
                for n, env in enumerate(envs):
                    binds["e%d" % n] = env
                    marks.append(":e%d" % n)
                clauses.append("environment IN (" + ", ".join(marks) + ")")
        if filters.get("active"):
            clauses.append("active = :active_f")
            binds["active_f"] = filters["active"]
        if filters.get("script_id") is not None:
            clauses.append("script_id = :script_id_f")
            binds["script_id_f"] = int(filters["script_id"])
        if filters.get("environment"):
            clauses.append("environment = :environment_f")
            binds["environment_f"] = filters["environment"]
        if filters.get("user_id") is not None:
            clauses.append("user_id = :user_id_f")
            binds["user_id_f"] = int(filters["user_id"])
        if filters.get("name"):
            # '%' e '_' digitados contam como literais, como o 'in' do FAKE.
            snippet = filters["name"].lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("LOWER(name) LIKE :name_f ESCAPE '\\'")
            binds["name_f"] = "%" + snippet + "%"

        p = 1 if page is None else int(page)
        t = 20 if size is None else int(size)
        if p < 1:
            p = 1
        if t < 1:
            t = 20
        start = (p - 1) * t
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        where_count = " AND ".join(clauses + ["ROWNUM <= " + str(_LIMIT_TOTAL)])
        sql_count_tpl = _SQL_COUNT.format(where_count=where_count, **self._idents)
        sql_page = (
            "SELECT * FROM (SELECT a.*, ROWNUM rn FROM (" + _SQL_LIST.format(where=where, **self._idents) + ") a "
            "WHERE ROWNUM <= :end_ts) WHERE rn > :start_ts"
        )
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql_count_tpl, binds)
                raw = cur.fetchone()[0]
                binds_page = dict(binds)
                binds_page["start_ts"] = start
                binds_page["end_ts"] = start + t
                cur.execute(sql_page, binds_page)
                items = [self._linha(r) for r in cur.fetchall()]
            finally:
                cur.close()
        return {
            "items": items,
            "total": min(raw, _LIMIT_TOTAL),
            "page": p,
            "size": t,
            "total_capped": raw >= _LIMIT_TOTAL,
        }

    def get(self, id, conn=None):
        """Agendamento pela PK ou RepoNotFound."""
        with self.read_context(conn=conn) as c:
            reg = self._uma(c, self._sql["GET"], {"id": int(id)})
        if reg is None:
            raise repo_errors.RepoNotFound("Agendamento ID %s nao encontrado" % id)
        return reg

    def ticket_status(self, ticket_id, conn=None):
        """Status atual do ticket ou None se inexistente (README §7.5 passo 4)."""
        if ticket_id is None:
            return None
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["TICKET_STATUS"], {"id": int(ticket_id)})
                row = cur.fetchone()
            finally:
                cur.close()
        return row[0].strip() if row and row[0] else None

    # -------------------------------------------------------------------------
    # Gravacoes
    # -------------------------------------------------------------------------

    def insert(self, data, audit=None, actor=None, conn=None):
        """Insere com as CKs e FKs conferidas antes do INSERT e a auditoria na mesma transacao."""
        actor_clean = validate_record_actor(audit, actor)
        with self.write_transaction(conn=conn) as c:
            now = db_conn.db_now(c)
            new = {
                "name": data.get("name"),
                "script_id": int(data["script_id"]),
                "environment": data["environment"],
                "user_id": int(data["user_id"]),
                "priority": data.get("priority", 2),
                "recurrence_type": data.get("recurrence_type"),
                "cron_expression": data.get("cron_expression"),
                "run_time": data.get("run_time"),
                "week_days": data.get("week_days"),
                "month_day": data.get("month_day"),
                "params_json": data.get("params_json", "{}"),
                "start_date": data.get("start_date") or now,
                "end_date": data.get("end_date"),
                "next_run_at": data.get("next_run_at") or now,
                "last_run_at": data.get("last_run_at"),
                "last_ticket_id": data.get("last_ticket_id"),
                "pause_reason": data.get("pause_reason"),
                "active": data.get("active", "Y"),
            }
            self._checar_cks(new)
            self._checar_fks(c, new)
            aid = db_conn.next_id(c, self._seq_sch)
            binds = self._binds_registro(new, actor_clean)
            binds["id"] = aid
            cur = c.cursor()
            try:
                self._tipos(cur)
                cur.execute(self._sql["INSERT"], binds)
            finally:
                cur.close()
            self._auditar(c, audit, aid)
            return self.get(aid, conn=c)

    def update(self, id, data, expected=None, audit=None, actor=None, conn=None):
        """Altera a regra (usuario_id do editor), condicional a 'esperado'; created_* nunca muda."""
        actor_clean = validate_record_actor(audit, actor)
        with self.write_transaction(conn=conn) as c:
            current = self._uma(c, self._sql["GET_LOCK"], {"id": int(id)})
            if current is None:
                raise repo_errors.RepoNotFound("Agendamento ID %s nao encontrado" % id)
            self._conferir_esperado(id, current, expected)
            result = dict(current)
            for k in _COLUMNS_UPDATABLE:
                if k in data:
                    result[k] = data[k]
            # Validacao completa antes do UPDATE: um UPDATE rejeitado nao altera nenhuma coluna.
            self._checar_cks(result)
            self._checar_fks(c, result)
            binds = self._binds_registro(result, actor_clean)
            binds["id"] = int(id)
            cur = c.cursor()
            try:
                self._tipos(cur)
                cur.execute(self._sql["UPDATE"], binds)
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflict("Agendamento ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, audit, int(id))
            return self.get(id, conn=c)

    def pause(self, id, reason, old_date=None, audit=None, actor=None, conn=None):
        """Pausa so regra ativa e, com old_date, so se a next_run nao mudou (CR-007, R-19)."""
        actor_clean = validate_record_actor(audit, actor)
        with self.write_transaction(conn=conn) as c:
            if not self._existe(c, self._sql["EXISTS"], {"id": int(id)}):
                raise repo_errors.RepoNotFound("Agendamento ID %s nao encontrado" % id)
            if reason not in _REASONS_PAUSE:
                raise repo_errors.RepoViolation("pausa_motivo invalido", constraint=self._ck("pause"))
            binds = {"id": int(id), "reason": reason, "actor": actor_clean}
            cur = c.cursor()
            try:
                if old_date is not None:
                    binds["old_date"] = old_date
                    # TIPO_DATE descarta a fracao: o valor lido mais microssegundos ainda casa (README §7.5).
                    db_conn.set_input_types(cur, old_date=db_conn.TIPO_DATE)
                    cur.execute(self._sql["PAUSE_OPTIMISTIC"], binds)
                else:
                    cur.execute(self._sql["PAUSE"], binds)
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflict(
                        "Agendamento %s nao esta ativo ou a proxima_execucao mudou (outra operacao)" % id)
            finally:
                cur.close()
            self._auditar(c, audit, int(id), "SCHEDULE_PAUSE", "Agendamento pausado: reason=%s" % reason,
                          actor_clean)
            return self.get(id, conn=c)

    def resume(self, id, new_date, expected=None, audit=None, actor=None, conn=None):
        """Retoma: ativo = 'S', pausa_motivo nulo e next_run = new_date, condicional a 'esperado'."""
        actor_clean = validate_record_actor(audit, actor)
        with self.write_transaction(conn=conn) as c:
            current = self._uma(c, self._sql["GET_LOCK"], {"id": int(id)})
            if current is None:
                raise repo_errors.RepoNotFound("Agendamento ID %s nao encontrado" % id)
            self._conferir_esperado(id, current, expected)
            if new_date is None:
                raise repo_errors.RepoViolation("proxima_execucao e obrigatoria")
            cur = c.cursor()
            try:
                db_conn.set_input_types(cur, new_date=db_conn.TIPO_DATE)
                cur.execute(self._sql["RESUME"], {"id": int(id), "new_date": new_date, "actor": actor_clean})
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflict("Agendamento ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, audit, int(id), "UPDATE",
                          "Agendamento retomado com next_run_at=%s" % new_date, actor_clean)
            return self.get(id, conn=c)
