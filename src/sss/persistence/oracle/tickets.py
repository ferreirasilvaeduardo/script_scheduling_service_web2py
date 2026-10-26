# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de tickets (F7.3, agregado TICKETS; AGENTS §4).

tbsss_tickets e tbsss_ticket_answer com a mesma semantica do repo_fake/tickets.py (README §2.5):
- SQL estatico com binds; os modelos ficam nas constantes abaixo e recebem, uma vez por instancia,
  somente identificadores qualificados por sql_ident (owner e prefixo validados);
- listagens e leituras do CR-004 nunca selecionam CLOB; obter traz submitted_params, nunca
  log_output, que so sai em fatias por log_ler (locator, offset base 0 na API e base 1 no LOB);
- cancelamento com os dois UPDATEs literais do README §5.6 e o residuo PENDING com cancel_requested
  = 'Y' (CR-008, R-02), travando so a linha do proprio ticket (nao altera a ordem de locks do §8.3);
- binds de DATE declarados como TIPO_DATE (README §7.5) e "agora" pelo SYSDATE do banco.
"""
from sss.persistence import db_conn
from sss.persistence import repo_errors
from sss.persistence.oracle.base import BaseRepoOracle, write_audit, validate_record_actor
from sss.persistence.contracts.repo_tickets import RepoTickets

_LIMIT_TOTAL = 10001
_BATCH_IN = 500
_LOG_MAX_CHARS = 65536
_STATUS = ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED")
_TERMINAL = ("SUCCESS", "FAILED", "CANCELLED")

# Colunas sem CLOB (listagens); obter acrescenta submitted_params.
_COLS_TCK = ("id", "script_id", "environment", "requested_by", "source_ip", "agent_id", "process_id",
             "process_start", "script_path", "interpreter_path", "interpreter_used", "status", "priority",
             "cancel_requested",
             "status_reason",
             "parent_ticket_id", "schedule_id", "log_offset_chars", "log_truncated", "return_code",
             "scheduled_at", "started_at", "heartbeat_at", "finished_at",
             "created_at", "created_by", "updated_at", "updated_by")
_COLS_ANS = ("id", "ticket_id", "parameter_id", "answer_value",
              "created_at", "created_by", "updated_at", "updated_by")
_COLS_LAST = ("id", "script_id", "status", "status_reason", "created_at", "finished_at")
_COLS_HIST = ("id", "status", "status_reason", "created_at", "started_at", "finished_at")
_DATES_TCK = ("scheduled_at", "started_at", "heartbeat_at", "finished_at")


def _column_list(cols, alias=""):
    return ", ".join(alias + c for c in cols)


# -----------------------------------------------------------------------------
# SQL estatico. {tck}, {resp}, {scr}, {amb}, {usr} e {prm} recebem apenas nomes qualificados por
# sql_ident (validados); todo valor entra por bind.
# -----------------------------------------------------------------------------

_SQL_GET = (
    "SELECT " + _column_list(_COLS_TCK) + ", submitted_params FROM {tck} WHERE id = :id"
)
_SQL_LIST = (
    "SELECT " + _column_list(_COLS_TCK) + " FROM {tck}{where} ORDER BY created_at DESC, id DESC"
)
_SQL_COUNT = "SELECT COUNT(*) FROM (SELECT id FROM {tck} WHERE {where_count})"
_SQL_LAST = (
    "SELECT " + _column_list(_COLS_LAST) + " FROM ("
    "SELECT " + _column_list(_COLS_LAST, "t.") + ", "
    "ROW_NUMBER() OVER (PARTITION BY t.script_id ORDER BY t.created_at DESC, t.id DESC) rn "
    "FROM {tck} t WHERE t.script_id IN ({ids}){scope}"
    ") WHERE rn = 1"
)
_SQL_HISTORY = (
    "SELECT " + _column_list(_COLS_HIST) + " FROM {tck} t "
    "WHERE t.script_id = :script_id AND t.created_at >= :since{scope} "
    "ORDER BY t.created_at DESC, t.id DESC"
)
_SQL_ANSWERS = (
    "SELECT " + _column_list(_COLS_ANS) + " FROM {tans} WHERE ticket_id = :ticket_id ORDER BY id"
)
_SQL_SCR_EXISTS = "SELECT id FROM {scr} WHERE id = :id"
_SQL_ENV_EXISTS = "SELECT id FROM {env} WHERE name = :name"
_SQL_USR_EXISTS = "SELECT id FROM {usr} WHERE login = :login"
_SQL_PRM_EXISTS = "SELECT id FROM {prm} WHERE id = :id"
_SQL_TCK_EXISTS = "SELECT id FROM {tck} WHERE id = :id"
_SQL_INSERT = (
    "INSERT INTO {tck} (id, script_id, environment, requested_by, source_ip, agent_id, process_id, "
    "process_start, script_path, interpreter_path, status, priority, cancel_requested, status_reason, "
    "parent_ticket_id, "
    "schedule_id, "
    "submitted_params, log_output, log_truncated, return_code, scheduled_at, started_at, "
    "heartbeat_at, finished_at, created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :script_id, :environment, :requested_by, :source_ip, :agent_id, :process_id, "
    ":process_start, :script_path, :interpreter_path, :status, :priority, :cancel_requested, :status_reason, "
    ":parent_ticket_id, "
    ":schedule_id, :submitted_params, :log_output, :log_truncated, :return_code, "
    "NVL(:scheduled_at, SYSDATE), :started_at, :heartbeat_at, :finished_at, SYSDATE, :actor, NULL, NULL)"
)
_SQL_INSERT_ANS = (
    "INSERT INTO {tans} (id, ticket_id, parameter_id, answer_value, created_at, created_by, "
    "updated_at, updated_by) VALUES (:id, :ticket_id, :parameter_id, :answer_value, SYSDATE, :actor, NULL, NULL)"
)
# README §5.6, literais (no do web, uma transacao).
_SQL_CANCEL_SIGNAL = (
    "UPDATE {tck} SET cancel_requested = 'Y', updated_at = SYSDATE, updated_by = :actor "
    "WHERE id = :id AND status IN ('PENDING', 'RUNNING') AND cancel_requested = 'N'"
)
_SQL_CANCEL_PENDING = (
    "UPDATE {tck} SET status = 'CANCELLED', status_reason = 'CANCEL_USER', return_code = -1, "
    "finished_at = SYSDATE, updated_at = SYSDATE, updated_by = :actor "
    "WHERE id = :id AND status = 'PENDING'"
)
_SQL_CANCEL_READ = "SELECT status, cancel_requested FROM {tck} WHERE id = :id FOR UPDATE WAIT 5"
_SQL_LOG = "SELECT status, log_truncated, log_output FROM {tck} WHERE id = :id"
# Saida do ticket (CR-012): metadados sem o BLOB; o conteudo so em fatias, como o log.
_COLS_OUTPUT = ("state", "reason", "agent_id", "file_count", "size_bytes",
               "created_at", "created_by", "updated_at", "updated_by")
_SQL_OUTPUT = "SELECT " + _column_list(_COLS_OUTPUT) + " FROM {tout} WHERE ticket_id = :ticket_id"
_SQL_OUTPUT_CONTENT = "SELECT state, content FROM {tout} WHERE ticket_id = :ticket_id"
OUTPUT_SLICE_MAX = 1024 * 1024
# Tela de Saidas (CR-020a): so saidas AVAILABLE, por nivel; {scope} e {extra} sao clausulas fixas do codigo.
_SQL_OUTPUT_ENVIRONMENTS = (
    "SELECT t.environment, COUNT(*), MAX(t.started_at) FROM {tck} t JOIN {tout} o ON o.ticket_id = t.id "
    "WHERE o.state = 'AVAILABLE'{scope} GROUP BY t.environment ORDER BY t.environment"
)
_SQL_OUTPUT_SCRIPTS = (
    "SELECT t.script_id, s.name, COUNT(*), MAX(t.started_at) FROM {tck} t JOIN {tout} o ON o.ticket_id = t.id "
    "JOIN {scr} s ON s.id = t.script_id WHERE o.state = 'AVAILABLE' AND t.environment = :environment_f{scope} "
    "GROUP BY t.script_id, s.name ORDER BY s.name, t.script_id"
)
_SQL_OUTPUT_DAYS = (
    "SELECT TRUNC(t.started_at), COUNT(*) FROM {tck} t JOIN {tout} o ON o.ticket_id = t.id "
    "WHERE o.state = 'AVAILABLE' AND t.environment = :environment_f AND t.script_id = :script_id_f{scope} "
    "GROUP BY TRUNC(t.started_at) ORDER BY 1 DESC"
)
_COLS_OUTPUT_TCK = ("id", "environment", "script_id", "requested_by", "status", "started_at", "finished_at",
                    "file_count", "size_bytes")
_SQL_OUTPUT_TICKETS = (
    "SELECT t.id, t.environment, t.script_id, t.requested_by, t.status, t.started_at, t.finished_at, "
    "o.file_count, o.size_bytes FROM {tck} t JOIN {tout} o ON o.ticket_id = t.id "
    "WHERE o.state = 'AVAILABLE' AND t.environment = :environment_f AND t.script_id = :script_id_f "
    "AND t.started_at >= :day_from AND t.started_at < :day_to{scope} ORDER BY t.started_at DESC, t.id DESC"
)
_OUTPUT_SUMMARY_MAX = 1000


def _read_lob(value):
    """CLOB lido pelo driver (locator) ou ja como texto."""
    if value is None:
        return None
    if hasattr(value, "read"):
        return value.read()
    return value


class RepoTicketsOracle(BaseRepoOracle, RepoTickets):
    """Repositorio de tickets com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, secrets=None):
        super(RepoTicketsOracle, self).__init__(cfg=cfg, secrets=secrets)
        self._idents = {
            "tck": self.qualify_table("tickets"),
            "tans": self.qualify_table("ticket_answer"),
            "scr": self.qualify_table("scripts"),
            "env": self.qualify_table("environments"),
            "usr": self.qualify_table("users"),
            "prm": self.qualify_table("parameters"),
            "tout": self.qualify_table("ticket_output"),
        }
        self._sql = {}
        for name, template in globals().items():
            if name.startswith("_SQL_") and "{where" not in template and "{ids}" not in template \
                    and "{scope}" not in template and "{extra}" not in template:
                self._sql[name[5:]] = template.format(**self._idents)
        self._tbl_aud = self.qualify_table("audit")
        self._seq_aud = self.qualify_sequence("audit")
        self._seq_tck = self.qualify_sequence("tickets")
        self._seq_tans = self.qualify_sequence("ticket_answer")

    # -------------------------------------------------------------------------
    # Utilitarios
    # -------------------------------------------------------------------------

    def _sql_dinamico(self, template, **parts):
        """Completa um modelo com identificadores e clausulas fixas (allowlist) montadas pelo codigo."""
        values = dict(self._idents)
        values.update(parts)
        return template.format(**values)

    def _existe(self, conn, sql, binds):
        cur = conn.cursor()
        try:
            cur.execute(sql, binds)
            return cur.fetchone() is not None
        finally:
            cur.close()

    def _fk(self, exists, suffix, entity="tickets"):
        if not exists:
            constraint = self.constraint_name("fk", entity, suffix)
            raise repo_errors.RepoViolation("Referencia inexistente (%s)" % constraint, constraint=constraint)

    @staticmethod
    def _marcas(prefix, values, binds):
        """Placeholders :<prefixo>0..N por contagem controlada; os valores vao so como binds."""
        marks = []
        for n, v in enumerate(values):
            name = "%s%d" % (prefix, n)
            binds[name] = v
            marks.append(":" + name)
        return ", ".join(marks)

    def _escopo(self, alias, environment_scope, requester, binds):
        """Clausulas de escopo (ambientes autorizados e solicitante), iguais as do listar."""
        clauses = []
        if environment_scope is not None:
            envs = sorted(set(environment_scope))
            if not envs:
                clauses.append("1 = 0")
            else:
                clauses.append(alias + "environment IN (" + self._marcas("e", envs, binds) + ")")
        if requester is not None:
            clauses.append(alias + "requested_by = :requested_by")
            binds["requested_by"] = requester
        return clauses

    # -------------------------------------------------------------------------
    # Leituras
    # -------------------------------------------------------------------------

    def now(self):
        """Instante corrente do banco (SYSDATE), sem microssegundos."""
        with self.read_context() as conn:
            return db_conn.db_now(conn)

    def get(self, id, conn=None):
        """Ticket pela PK, com submitted_params e sem log_output (que sai por log_ler)."""
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["GET"], {"id": int(id)})
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNotFound("Ticket ID %s nao encontrado" % id)
                reg = self.tuple_to_dict(_COLS_TCK, row[:len(_COLS_TCK)])
                reg["submitted_params"] = _read_lob(row[len(_COLS_TCK)])
                return reg
            finally:
                cur.close()

    def list(self, filters=None, page=1, size=20, environment_scope=None, conn=None):
        """Lista tickets por created_at DESC, id DESC, sem CLOB, com total limitado a 10.001."""
        filters = filters or {}
        clauses, binds, dates = [], {}, {}
        clauses.extend(self._escopo("", environment_scope, None, binds))

        stat_f = filters.get("status")
        if stat_f:
            values = sorted(set(stat_f)) if isinstance(stat_f, (list, tuple, set, frozenset)) else [stat_f]
            clauses.append("status IN (" + self._marcas("s", values, binds) + ")")
        if filters.get("environment"):
            clauses.append("environment = :environment_f")
            binds["environment_f"] = filters["environment"]
        if filters.get("script_id") is not None:
            clauses.append("script_id = :script_id_f")
            binds["script_id_f"] = int(filters["script_id"])
        if filters.get("requested_by"):
            clauses.append("requested_by = :requester_f")
            binds["requester_f"] = filters["requested_by"]
        if filters.get("parent_ticket_id") is not None:
            clauses.append("parent_ticket_id = :parent_f")
            binds["parent_f"] = int(filters["parent_ticket_id"])
        source = filters.get("source")
        if source == "manual":
            clauses.append("schedule_id IS NULL")
        elif source == "agendamento":
            clauses.append("schedule_id IS NOT NULL")
        # Periodo sempre por intervalo, sem TRUNC (AGENTS §4.12); binds DATE (README §7.5).
        if filters.get("created_from"):
            clauses.append("created_at >= :created_from")
            binds["created_from"] = filters["created_from"]
            dates["created_from"] = db_conn.TIPO_DATE
        if filters.get("created_to"):
            clauses.append("created_at < :created_to")
            binds["created_to"] = filters["created_to"]
            dates["created_to"] = db_conn.TIPO_DATE

        p = 1 if page is None else int(page)
        t = 20 if size is None else int(size)
        if p < 1:
            p = 1
        if t < 1:
            t = 20
        start = (p - 1) * t
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        where_count = " AND ".join(clauses + ["ROWNUM <= " + str(_LIMIT_TOTAL)])
        sql_count_tpl = self._sql_dinamico(_SQL_COUNT, where_count=where_count)
        sql_page = (
            "SELECT * FROM (SELECT a.*, ROWNUM rn FROM (" + self._sql_dinamico(_SQL_LIST, where=where) + ") a "
            "WHERE ROWNUM <= :end_ts) WHERE rn > :start_ts"
        )
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                if dates:
                    db_conn.set_input_types(cur, **dates)
                cur.execute(sql_count_tpl, binds)
                raw = cur.fetchone()[0]
            finally:
                cur.close()
            binds_page = dict(binds)
            binds_page["start_ts"] = start
            binds_page["end_ts"] = start + t
            cur = c.cursor()
            try:
                if dates:
                    db_conn.set_input_types(cur, **dates)
                cur.execute(sql_page, binds_page)
                items = [self.tuple_to_dict(_COLS_TCK, r[:len(_COLS_TCK)]) for r in cur.fetchall()]
            finally:
                cur.close()
        return {
            "items": items,
            "total": min(raw, _LIMIT_TOTAL),
            "page": p,
            "size": t,
            "total_capped": raw >= _LIMIT_TOTAL,
        }

    def last_runs(self, script_ids, environment_scope=None, requester=None, conn=None):
        """Ticket mais recente de cada script no escopo, numa consulta por lote (ROW_NUMBER, sem LOB)."""
        ids = sorted(set(int(i) for i in script_ids))
        result = {}
        if not ids:
            return result
        with self.read_context(conn=conn) as c:
            for i in range(0, len(ids), _BATCH_IN):
                binds = {}
                marks = self._marcas("s", ids[i:i + _BATCH_IN], binds)
                scope = self._escopo("t.", environment_scope, requester, binds)
                sql = self._sql_dinamico(_SQL_LAST, ids=marks,
                                         scope="".join(" AND " + x for x in scope))
                cur = c.cursor()
                try:
                    cur.execute(sql, binds)
                    for r in cur.fetchall():
                        reg = self.tuple_to_dict(_COLS_LAST, r)
                        sid = reg.pop("script_id")
                        result[sid] = reg
                finally:
                    cur.close()
        return result

    def script_history(self, script_id, since, environment_scope=None, requester=None, limit=5000,
                         conn=None):
        """Tickets do script desde a data, no escopo, sem LOB: os `limite` mais recentes, em ordem crescente."""
        binds = {"script_id": int(script_id), "since": since}
        scope = self._escopo("t.", environment_scope, requester, binds)
        sql = self._sql_dinamico(_SQL_HISTORY, scope="".join(" AND " + x for x in scope))
        if limit:
            sql = "SELECT " + _column_list(_COLS_HIST) + " FROM (" + sql + ") WHERE ROWNUM <= :cutoff"
            binds["cutoff"] = int(limit)
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                db_conn.set_input_types(cur, since=db_conn.TIPO_DATE)
                cur.execute(sql, binds)
                rows = [self.tuple_to_dict(_COLS_HIST, r) for r in cur.fetchall()]
            finally:
                cur.close()
        rows.reverse()
        return rows

    def answers(self, ticket_id, conn=None):
        """Respostas resolvidas do ticket, por id."""
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["ANSWERS"], {"ticket_id": int(ticket_id)})
                return [self.tuple_to_dict(_COLS_ANS, r) for r in cur.fetchall()]
            finally:
                cur.close()

    def log_read(self, id, offset, max_chars, conn=None):
        """Fatia do log por locator: offset base 0 na API, offset + 1 no LOB, ate 65.536 caracteres."""
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["LOG"], {"id": int(id)})
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNotFound("Ticket ID %s nao encontrado" % id)
                status, log_truncated, lob = row
                # Valor nao numerico propaga ValueError/TypeError, como no FAKE.
                off = int(offset)
                if off < 0:
                    off = 0
                mc = int(max_chars)
                if mc < 1:
                    mc = _LOG_MAX_CHARS
                text = ""
                if lob is not None:
                    if hasattr(lob, "read"):
                        if off < lob.size():
                            text = lob.read(off + 1, mc) or ""
                    else:
                        text = lob[off:off + mc]
            finally:
                cur.close()
        return (text, off + len(text), (status or "").strip() in _TERMINAL, (log_truncated or "").strip() == "Y")

    def output_get(self, ticket_id, conn=None):
        """Metadados da saida do ticket (CR-012), sem ler o BLOB; None sem saida."""
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["OUTPUT"], {"ticket_id": int(ticket_id)})
                row = cur.fetchone()
            finally:
                cur.close()
        return self.tuple_to_dict(_COLS_OUTPUT, row) if row else None

    def output_summary(self, level, environment_scope=None, environment=None, script_id=None, conn=None):
        """Resumo das saidas AVAILABLE por ambiente, script ou dia (CR-020a), sem ler o BLOB."""
        binds = {}
        if level == "environment":
            template, cols = _SQL_OUTPUT_ENVIRONMENTS, ("environment", "count", "last_at")
        elif level == "script":
            template, cols = _SQL_OUTPUT_SCRIPTS, ("script_id", "script_name", "count", "last_at")
            binds["environment_f"] = environment
        elif level == "day":
            template, cols = _SQL_OUTPUT_DAYS, ("day", "count")
            binds["environment_f"] = environment
            binds["script_id_f"] = int(script_id)
        else:
            raise repo_errors.RepoViolation("Nivel do resumo de saidas invalido")
        scope = "".join(" AND " + c for c in self._escopo("t.", environment_scope, None, binds))
        sql = self._sql_dinamico(template, scope=scope)
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql, binds)
                rows = cur.fetchmany(_OUTPUT_SUMMARY_MAX)
            finally:
                cur.close()
        return [self.tuple_to_dict(cols, r) for r in rows]

    def output_tickets(self, environment, script_id, day_from, day_to, page=1, size=20, environment_scope=None,
                       conn=None):
        """Tickets com saida AVAILABLE do ambiente e script no intervalo de started_at (CR-020a)."""
        binds = {"environment_f": environment, "script_id_f": int(script_id), "day_from": day_from,
                 "day_to": day_to}
        scope = "".join(" AND " + c for c in self._escopo("t.", environment_scope, None, binds))
        base = self._sql_dinamico(_SQL_OUTPUT_TICKETS, scope=scope)
        p = max(1, int(page or 1))
        t = int(size or 20)
        t = 20 if t < 1 else t
        start = (p - 1) * t
        sql_count = "SELECT COUNT(*) FROM (" + base + ")"
        sql_page = ("SELECT * FROM (SELECT a.*, ROWNUM rn FROM (" + base + ") a WHERE ROWNUM <= :end_ts) "
                    "WHERE rn > :start_ts")
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                db_conn.set_input_types(cur, day_from=db_conn.TIPO_DATE, day_to=db_conn.TIPO_DATE)
                cur.execute(sql_count, binds)
                total = cur.fetchone()[0]
            finally:
                cur.close()
            cur = c.cursor()
            try:
                db_conn.set_input_types(cur, day_from=db_conn.TIPO_DATE, day_to=db_conn.TIPO_DATE)
                cur.execute(sql_page, dict(binds, start_ts=start, end_ts=start + t))
                items = [self.tuple_to_dict(_COLS_OUTPUT_TCK, r[:len(_COLS_OUTPUT_TCK)]) for r in cur.fetchall()]
            finally:
                cur.close()
        return {"items": items, "total": total, "page": p, "size": t}

    def output_read(self, ticket_id, offset, size, conn=None):
        """Fatia do zip por locator (offset base 0 na API, offset + 1 no LOB); so DISPONIVEL."""
        off = int(offset)
        size_n = int(size)
        if off < 0 or size_n < 1 or size_n > OUTPUT_SLICE_MAX:
            raise repo_errors.RepoViolation("Fatia da saida invalida")
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["OUTPUT_CONTENT"], {"ticket_id": int(ticket_id)})
                row = cur.fetchone()
                if not row or (row[0] or "").strip() != "AVAILABLE" or row[1] is None:
                    raise repo_errors.RepoNotFound("Saida do ticket %s indisponivel" % ticket_id)
                lob = row[1]
                if hasattr(lob, "read"):
                    return (lob.read(off + 1, size_n) or b"") if off < lob.size() else b""
                return bytes(lob[off:off + size_n])
            finally:
                cur.close()

    # -------------------------------------------------------------------------
    # Gravacoes
    # -------------------------------------------------------------------------

    def create(self, ticket, answers, actor=None, conn=None):
        """Ticket, respostas e auditoria numa transacao, sem gravacao parcial; retorna o ID criado."""
        script_id = int(ticket.get("script_id", 0))
        environment = ticket.get("environment")
        requester = ticket.get("requested_by")
        actor_clean = validate_record_actor(actor=actor or requester)
        if not script_id:
            raise repo_errors.RepoViolation("script_id e obrigatorio")
        if not environment:
            raise repo_errors.RepoViolation("ambiente e obrigatorio")
        if not requester:
            raise repo_errors.RepoViolation("solicitante e obrigatorio")
        prio = int(ticket.get("priority", 2))
        if not (1 <= prio <= 4):
            raise repo_errors.RepoViolation("prioridade deve estar entre 1 e 4",
                                           constraint=self.constraint_name("ck", "tickets", "prio"))
        status = ticket.get("status", "PENDING")
        if status not in _STATUS:
            raise repo_errors.RepoViolation("Status invalido", constraint=self.constraint_name("ck", "tickets", "stat"))
        parent_id = ticket.get("parent_ticket_id")
        sch_id = ticket.get("schedule_id")

        with self.write_transaction(conn=conn) as c:
            # FKs e UK conferidas antes de gravar qualquer linha, na ordem do FAKE (README §2.5).
            if parent_id is not None:
                self._fk(self._existe(c, self._sql["TCK_EXISTS"], {"id": int(parent_id)}), "parent")
            self._fk(self._existe(c, self._sql["SCR_EXISTS"], {"id": script_id}), "scr")
            self._fk(self._existe(c, self._sql["ENV_EXISTS"], {"name": environment}), "env")
            self._fk(self._existe(c, self._sql["USR_EXISTS"], {"login": requester}), "usr")
            seen = set()
            for resp in (answers or []):
                pid = int(resp["parameter_id"])
                self._fk(self._existe(c, self._sql["PRM_EXISTS"], {"id": pid}), "prm", entity="ticket_answer")
                if pid in seen:
                    raise repo_errors.RepoViolation(
                        "resposta repetida para o parametro %s" % pid,
                        constraint=self.constraint_name("uk", "ticket_answer", "tck_prm"))
                seen.add(pid)

            tid = db_conn.next_id(c, self._seq_tck)
            binds = {
                "id": tid, "script_id": script_id, "environment": environment, "requested_by": requester,
                "source_ip": ticket.get("source_ip"), "agent_id": ticket.get("agent_id"),
                "process_id": ticket.get("process_id"), "process_start": ticket.get("process_start"),
                "script_path": ticket.get("script_path"), "interpreter_path": ticket.get("interpreter_path"),
                "status": status, "priority": prio, "cancel_requested": ticket.get("cancel_requested", "N"),
                "status_reason": ticket.get("status_reason"),
                "parent_ticket_id": int(parent_id) if parent_id is not None else None,
                "schedule_id": int(sch_id) if sch_id is not None else None,
                "submitted_params": ticket.get("submitted_params", "{}"),
                "log_output": ticket.get("log_output") or None,
                "log_truncated": ticket.get("log_truncated", "N"), "return_code": ticket.get("return_code"),
                "actor": actor_clean,
            }
            for field in _DATES_TCK:
                binds[field] = ticket.get(field)
            kinds = dict((field, db_conn.TIPO_DATE) for field in _DATES_TCK)
            kinds.update(submitted_params=db_conn.TIPO_CLOB, log_output=db_conn.TIPO_CLOB)
            cur = c.cursor()
            try:
                db_conn.set_input_types(cur, **kinds)
                # Ocorrencia repetida do agendamento: ORA-00001 em ix_<prefixo>tck_occur (RepoViolation).
                cur.execute(self._sql["INSERT"], binds)
            finally:
                cur.close()

            batch = []
            for resp in (answers or []):
                batch.append({"id": db_conn.next_id(c, self._seq_tans), "ticket_id": tid,
                             "parameter_id": int(resp["parameter_id"]),
                             "answer_value": resp.get("answer_value"), "actor": actor_clean})
            if batch:
                cur = c.cursor()
                try:
                    cur.executemany(self._sql["INSERT_ANS"], batch)
                finally:
                    cur.close()

            if parent_id is None:
                action, detail = "TICKET_CREATE", "Ticket criado para script %s em %s" % (script_id, environment)
            else:
                action = "TICKET_RERUN"
                detail = "Reexecucao do ticket %s para script %s em %s" % (parent_id, script_id, environment)
            if ticket.get("interpreter_override"):
                # CR-025: o interpretador digitado no disparo fica na trilha.
                detail += "; interpretador informado: %s" % ticket["interpreter_override"]
            write_audit(c, self._tbl_aud, self._seq_aud,
                             {"actor": requester, "ip": ticket.get("source_ip"), "action": action, "detail": detail},
                             "tbsss_tickets", tid)
            return tid

    def request_cancel(self, id, actor, ip, conn=None):
        """Os dois UPDATEs do README §5.6 e a auditoria TICKET_CANCEL numa transacao."""
        actor_clean = validate_record_actor(actor=actor)
        tid = int(id)
        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["CANCEL_SIGNAL"], {"id": tid, "actor": actor_clean})
                signaled = cur.rowcount == 1
                if signaled:
                    cur.execute(self._sql["CANCEL_PENDING"], {"id": tid, "actor": actor_clean})
                    return_value = "CANCELADO" if cur.rowcount == 1 else "SINALIZADO"
                else:
                    # Terminal, ja sinalizado ou PENDING residual com 'S' (CR-008, R-02): so a propria linha.
                    cur.execute(self._sql["CANCEL_READ"], {"id": tid})
                    row = cur.fetchone()
                    if not row:
                        raise repo_errors.RepoNotFound("Ticket ID %s nao encontrado" % id)
                    status, request = (row[0] or "").strip(), (row[1] or "").strip()
                    if status == "PENDING":
                        cur.execute(self._sql["CANCEL_PENDING"], {"id": tid, "actor": actor_clean})
                        if cur.rowcount != 1:
                            raise repo_errors.RepoConflict("Ticket ID %s alterado por outra operacao" % id)
                        return_value = "CANCELADO"
                    elif status == "RUNNING" and request == "Y":
                        return_value = "JA_SINALIZADO"
                    else:
                        return_value = "TERMINAL"
            finally:
                cur.close()
            result = {
                "CANCELADO": u"cancelado", "SINALIZADO": u"sinalizado",
                "JA_SINALIZADO": u"já sinalizado", "TERMINAL": u"sem efeito: ticket encerrado",
            }[return_value]
            write_audit(c, self._tbl_aud, self._seq_aud,
                             {"actor": actor_clean, "ip": ip, "action": "TICKET_CANCEL",
                              "detail": u"resultado: %s" % result},
                             "tbsss_tickets", tid)
            return return_value
