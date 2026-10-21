# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de tickets (F7.3, agregado TICKETS; AGENTS §4).

tbsss_tickets e tbsss_ticket_answer com a mesma semantica do repo_fake/tickets.py (README §2.5):
- SQL estatico com binds; os modelos ficam nas constantes abaixo e recebem, uma vez por instancia,
  somente identificadores qualificados por sql_ident (owner e prefixo validados);
- listagens e leituras do CR-004 nunca selecionam CLOB; obter traz parametros_enviados, nunca
  log_output, que so sai em fatias por log_ler (locator, offset base 0 na API e base 1 no LOB);
- cancelamento com os dois UPDATEs literais do README §5.6 e o residuo PENDING com cancel_requested
  = 'S' (CR-008, R-02), travando so a linha do proprio ticket (nao altera a ordem de locks do §8.3);
- binds de DATE declarados como TIPO_DATE (README §7.5) e "agora" pelo SYSDATE do banco.
"""
import db_conn
import repo_errors
from repo_oracle.base import BaseRepoOracle, write_audit, validate_record_actor
from repo_tickets import RepoTickets

_LIMIT_TOTAL = 10001
_BATCH_IN = 500
_LOG_MAX_CHARS = 65536
_STATUS = ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED")
_TERMINAL = ("SUCCESS", "FAILED", "CANCELLED")

# Colunas sem CLOB (listagens); obter acrescenta parametros_enviados.
_COLS_TCK = ("id", "script_id", "environment", "requested_by", "source_ip", "agent_id", "process_id",
             "process_start", "status", "priority", "cancel_requested", "status_reason",
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
    "FROM {tck} t WHERE t.script_id IN ({ids}){escopo}"
    ") WHERE rn = 1"
)
_SQL_HISTORY = (
    "SELECT " + _column_list(_COLS_HIST) + " FROM {tck} t "
    "WHERE t.script_id = :script_id AND t.created_at >= :desde{escopo} "
    "ORDER BY t.created_at DESC, t.id DESC"
)
_SQL_ANSWERS = (
    "SELECT " + _column_list(_COLS_ANS) + " FROM {resp} WHERE ticket_id = :ticket_id ORDER BY id"
)
_SQL_SCR_EXISTS = "SELECT id FROM {scr} WHERE id = :id"
_SQL_ENV_EXISTS = "SELECT id FROM {amb} WHERE name = :name"
_SQL_USR_EXISTS = "SELECT id FROM {usr} WHERE login = :login"
_SQL_PRM_EXISTS = "SELECT id FROM {prm} WHERE id = :id"
_SQL_TCK_EXISTS = "SELECT id FROM {tck} WHERE id = :id"
_SQL_INSERT = (
    "INSERT INTO {tck} (id, script_id, environment, requested_by, source_ip, agent_id, process_id, "
    "process_start, status, priority, cancel_requested, status_reason, parent_ticket_id, schedule_id, "
    "submitted_params, log_output, log_truncated, return_code, scheduled_at, started_at, "
    "heartbeat_at, finished_at, created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :script_id, :environment, :requested_by, :source_ip, :agent_id, :process_id, "
    ":process_start, :status, :priority, :cancel_requested, :status_reason, :parent_ticket_id, "
    ":schedule_id, :submitted_params, :log_output, :log_truncated, :return_code, "
    "NVL(:scheduled_at, SYSDATE), :started_at, :heartbeat_at, :finished_at, SYSDATE, :actor, NULL, NULL)"
)
_SQL_INSERT_ANS = (
    "INSERT INTO {resp} (id, ticket_id, parameter_id, answer_value, created_at, created_by, "
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
_SQL_OUTPUT = "SELECT " + _column_list(_COLS_OUTPUT) + " FROM {sai} WHERE ticket_id = :ticket_id"
_SQL_OUTPUT_CONTENT = "SELECT state, content FROM {sai} WHERE ticket_id = :ticket_id"
OUTPUT_SLICE_MAX = 1024 * 1024


def _read_lob(valor):
    """CLOB lido pelo driver (locator) ou ja como texto."""
    if valor is None:
        return None
    if hasattr(valor, "read"):
        return valor.read()
    return valor


class RepoTicketsOracle(BaseRepoOracle, RepoTickets):
    """Repositorio de tickets com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, segredos=None):
        super(RepoTicketsOracle, self).__init__(cfg=cfg, segredos=segredos)
        self._idents = {
            "tck": self.qualify_table("tickets"),
            "resp": self.qualify_table("ticket_answer"),
            "scr": self.qualify_table("scripts"),
            "amb": self.qualify_table("environments"),
            "usr": self.qualify_table("users"),
            "prm": self.qualify_table("parameters"),
            "sai": self.qualify_table("ticket_output"),
        }
        self._sql = {}
        for nome, modelo in globals().items():
            if nome.startswith("_SQL_") and "{where" not in modelo and "{ids}" not in modelo \
                    and "{escopo}" not in modelo:
                self._sql[nome[5:]] = modelo.format(**self._idents)
        self._tbl_aud = self.qualify_table("audit")
        self._seq_aud = self.qualify_sequence("audit")
        self._seq_tck = self.qualify_sequence("tickets")
        self._seq_resp = self.qualify_sequence("ticket_answer")

    # -------------------------------------------------------------------------
    # Utilitarios
    # -------------------------------------------------------------------------

    def _sql_dinamico(self, modelo, **partes):
        """Completa um modelo com identificadores e clausulas fixas (allowlist) montadas pelo codigo."""
        valores = dict(self._idents)
        valores.update(partes)
        return modelo.format(**valores)

    def _existe(self, conn, sql, binds):
        cur = conn.cursor()
        try:
            cur.execute(sql, binds)
            return cur.fetchone() is not None
        finally:
            cur.close()

    def _fk(self, existe, sufixo, entidade="tickets"):
        if not existe:
            constraint = self.constraint_name("fk", entidade, sufixo)
            raise repo_errors.RepoViolation("Referencia inexistente (%s)" % constraint, constraint=constraint)

    @staticmethod
    def _marcas(prefixo, valores, binds):
        """Placeholders :<prefixo>0..N por contagem controlada; os valores vao so como binds."""
        marcas = []
        for n, v in enumerate(valores):
            nome = "%s%d" % (prefixo, n)
            binds[nome] = v
            marcas.append(":" + nome)
        return ", ".join(marcas)

    def _escopo(self, alias, escopo_ambientes, solicitante, binds):
        """Clausulas de escopo (ambientes autorizados e solicitante), iguais as do listar."""
        clausulas = []
        if escopo_ambientes is not None:
            ambs = sorted(set(escopo_ambientes))
            if not ambs:
                clausulas.append("1 = 0")
            else:
                clausulas.append(alias + "environment IN (" + self._marcas("e", ambs, binds) + ")")
        if solicitante is not None:
            clausulas.append(alias + "requested_by = :requested_by")
            binds["requested_by"] = solicitante
        return clausulas

    # -------------------------------------------------------------------------
    # Leituras
    # -------------------------------------------------------------------------

    def now(self):
        """Instante corrente do banco (SYSDATE), sem microssegundos."""
        with self.read_context() as conn:
            return db_conn.db_now(conn)

    def get(self, id, conn=None):
        """Ticket pela PK, com parametros_enviados e sem log_output (que sai por log_ler)."""
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

    def list(self, filtros=None, pagina=1, tamanho=20, escopo_ambientes=None, conn=None):
        """Lista tickets por created_at DESC, id DESC, sem CLOB, com total limitado a 10.001."""
        filtros = filtros or {}
        clausulas, binds, datas = [], {}, {}
        clausulas.extend(self._escopo("", escopo_ambientes, None, binds))

        stat_f = filtros.get("status")
        if stat_f:
            valores = sorted(set(stat_f)) if isinstance(stat_f, (list, tuple, set, frozenset)) else [stat_f]
            clausulas.append("status IN (" + self._marcas("s", valores, binds) + ")")
        if filtros.get("environment"):
            clausulas.append("environment = :ambiente_f")
            binds["ambiente_f"] = filtros["environment"]
        if filtros.get("script_id") is not None:
            clausulas.append("script_id = :script_id_f")
            binds["script_id_f"] = int(filtros["script_id"])
        if filtros.get("requested_by"):
            clausulas.append("requested_by = :solicitante_f")
            binds["solicitante_f"] = filtros["requested_by"]
        if filtros.get("parent_ticket_id") is not None:
            clausulas.append("parent_ticket_id = :parent_f")
            binds["parent_f"] = int(filtros["parent_ticket_id"])
        origem = filtros.get("origem")
        if origem == "manual":
            clausulas.append("schedule_id IS NULL")
        elif origem == "agendamento":
            clausulas.append("schedule_id IS NOT NULL")
        # Periodo sempre por intervalo, sem TRUNC (AGENTS §4.12); binds DATE (README §7.5).
        if filtros.get("criado_inicio"):
            clausulas.append("created_at >= :criado_inicio")
            binds["criado_inicio"] = filtros["criado_inicio"]
            datas["criado_inicio"] = db_conn.TIPO_DATE
        if filtros.get("criado_fim"):
            clausulas.append("created_at < :criado_fim")
            binds["criado_fim"] = filtros["criado_fim"]
            datas["criado_fim"] = db_conn.TIPO_DATE

        p = 1 if pagina is None else int(pagina)
        t = 20 if tamanho is None else int(tamanho)
        if p < 1:
            p = 1
        if t < 1:
            t = 20
        inicio = (p - 1) * t
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        where_count = " AND ".join(clausulas + ["ROWNUM <= " + str(_LIMIT_TOTAL)])
        sql_conta = self._sql_dinamico(_SQL_COUNT, where_count=where_count)
        sql_pag = (
            "SELECT * FROM (SELECT a.*, ROWNUM rn FROM (" + self._sql_dinamico(_SQL_LIST, where=where) + ") a "
            "WHERE ROWNUM <= :fim) WHERE rn > :inicio"
        )
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                if datas:
                    db_conn.set_input_types(cur, **datas)
                cur.execute(sql_conta, binds)
                bruto = cur.fetchone()[0]
            finally:
                cur.close()
            binds_pag = dict(binds)
            binds_pag["inicio"] = inicio
            binds_pag["fim"] = inicio + t
            cur = c.cursor()
            try:
                if datas:
                    db_conn.set_input_types(cur, **datas)
                cur.execute(sql_pag, binds_pag)
                itens = [self.tuple_to_dict(_COLS_TCK, r[:len(_COLS_TCK)]) for r in cur.fetchall()]
            finally:
                cur.close()
        return {
            "itens": itens,
            "total": min(bruto, _LIMIT_TOTAL),
            "pagina": p,
            "tamanho": t,
            "total_limitado": bruto >= _LIMIT_TOTAL,
        }

    def last_runs(self, script_ids, escopo_ambientes=None, solicitante=None, conn=None):
        """Ticket mais recente de cada script no escopo, numa consulta por lote (ROW_NUMBER, sem LOB)."""
        ids = sorted(set(int(i) for i in script_ids))
        resultado = {}
        if not ids:
            return resultado
        with self.read_context(conn=conn) as c:
            for i in range(0, len(ids), _BATCH_IN):
                binds = {}
                marcas = self._marcas("s", ids[i:i + _BATCH_IN], binds)
                escopo = self._escopo("t.", escopo_ambientes, solicitante, binds)
                sql = self._sql_dinamico(_SQL_LAST, ids=marcas,
                                         escopo="".join(" AND " + x for x in escopo))
                cur = c.cursor()
                try:
                    cur.execute(sql, binds)
                    for r in cur.fetchall():
                        reg = self.tuple_to_dict(_COLS_LAST, r)
                        sid = reg.pop("script_id")
                        resultado[sid] = reg
                finally:
                    cur.close()
        return resultado

    def script_history(self, script_id, desde, escopo_ambientes=None, solicitante=None, limite=5000,
                         conn=None):
        """Tickets do script desde a data, no escopo, sem LOB: os `limite` mais recentes, em ordem crescente."""
        binds = {"script_id": int(script_id), "desde": desde}
        escopo = self._escopo("t.", escopo_ambientes, solicitante, binds)
        sql = self._sql_dinamico(_SQL_HISTORY, escopo="".join(" AND " + x for x in escopo))
        if limite:
            sql = "SELECT " + _column_list(_COLS_HIST) + " FROM (" + sql + ") WHERE ROWNUM <= :limite"
            binds["limite"] = int(limite)
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                db_conn.set_input_types(cur, desde=db_conn.TIPO_DATE)
                cur.execute(sql, binds)
                linhas = [self.tuple_to_dict(_COLS_HIST, r) for r in cur.fetchall()]
            finally:
                cur.close()
        linhas.reverse()
        return linhas

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
                status, log_truncado, lob = row
                # Valor nao numerico propaga ValueError/TypeError, como no FAKE.
                off = int(offset)
                if off < 0:
                    off = 0
                mc = int(max_chars)
                if mc < 1:
                    mc = _LOG_MAX_CHARS
                texto = ""
                if lob is not None:
                    if hasattr(lob, "read"):
                        if off < lob.size():
                            texto = lob.read(off + 1, mc) or ""
                    else:
                        texto = lob[off:off + mc]
            finally:
                cur.close()
        return (texto, off + len(texto), (status or "").strip() in _TERMINAL, (log_truncado or "").strip() == "Y")

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

    def output_read(self, ticket_id, offset, tamanho, conn=None):
        """Fatia do zip por locator (offset base 0 na API, offset + 1 no LOB); so DISPONIVEL."""
        off = int(offset)
        tam = int(tamanho)
        if off < 0 or tam < 1 or tam > OUTPUT_SLICE_MAX:
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
                    return (lob.read(off + 1, tam) or b"") if off < lob.size() else b""
                return bytes(lob[off:off + tam])
            finally:
                cur.close()

    # -------------------------------------------------------------------------
    # Gravacoes
    # -------------------------------------------------------------------------

    def create(self, ticket, respostas, ator=None, conn=None):
        """Ticket, respostas e auditoria numa transacao, sem gravacao parcial; retorna o ID criado."""
        script_id = int(ticket.get("script_id", 0))
        ambiente = ticket.get("environment")
        solicitante = ticket.get("requested_by")
        ator_limpo = validate_record_actor(ator=ator or solicitante)
        if not script_id:
            raise repo_errors.RepoViolation("script_id e obrigatorio")
        if not ambiente:
            raise repo_errors.RepoViolation("ambiente e obrigatorio")
        if not solicitante:
            raise repo_errors.RepoViolation("solicitante e obrigatorio")
        prio = int(ticket.get("priority", 2))
        if not (1 <= prio <= 4):
            raise repo_errors.RepoViolation("prioridade deve estar entre 1 e 4",
                                           constraint=self.constraint_name("ck", "tickets", "prio"))
        status = ticket.get("status", "PENDING")
        if status not in _STATUS:
            raise repo_errors.RepoViolation("Status invalido", constraint=self.constraint_name("ck", "tickets", "stat"))
        parent_id = ticket.get("parent_ticket_id")
        agd_id = ticket.get("schedule_id")

        with self.write_transaction(conn=conn) as c:
            # FKs e UK conferidas antes de gravar qualquer linha, na ordem do FAKE (README §2.5).
            if parent_id is not None:
                self._fk(self._existe(c, self._sql["TCK_EXISTS"], {"id": int(parent_id)}), "parent")
            self._fk(self._existe(c, self._sql["SCR_EXISTS"], {"id": script_id}), "scr")
            self._fk(self._existe(c, self._sql["ENV_EXISTS"], {"name": ambiente}), "env")
            self._fk(self._existe(c, self._sql["USR_EXISTS"], {"login": solicitante}), "usr")
            vistos = set()
            for resp in (respostas or []):
                pid = int(resp["parameter_id"])
                self._fk(self._existe(c, self._sql["PRM_EXISTS"], {"id": pid}), "prm", entidade="ticket_answer")
                if pid in vistos:
                    raise repo_errors.RepoViolation(
                        "resposta repetida para o parametro %s" % pid,
                        constraint=self.constraint_name("uk", "ticket_answer", "tck_prm"))
                vistos.add(pid)

            tid = db_conn.next_id(c, self._seq_tck)
            binds = {
                "id": tid, "script_id": script_id, "environment": ambiente, "requested_by": solicitante,
                "source_ip": ticket.get("source_ip"), "agent_id": ticket.get("agent_id"),
                "process_id": ticket.get("process_id"), "process_start": ticket.get("process_start"),
                "status": status, "priority": prio, "cancel_requested": ticket.get("cancel_requested", "N"),
                "status_reason": ticket.get("status_reason"),
                "parent_ticket_id": int(parent_id) if parent_id is not None else None,
                "schedule_id": int(agd_id) if agd_id is not None else None,
                "submitted_params": ticket.get("submitted_params", "{}"),
                "log_output": ticket.get("log_output") or None,
                "log_truncated": ticket.get("log_truncated", "N"), "return_code": ticket.get("return_code"),
                "actor": ator_limpo,
            }
            for campo in _DATES_TCK:
                binds[campo] = ticket.get(campo)
            tipos = dict((campo, db_conn.TIPO_DATE) for campo in _DATES_TCK)
            tipos.update(submitted_params=db_conn.TIPO_CLOB, log_output=db_conn.TIPO_CLOB)
            cur = c.cursor()
            try:
                db_conn.set_input_types(cur, **tipos)
                # Ocorrencia repetida do agendamento: ORA-00001 em ix_<prefixo>tck_ocor (RepoViolation).
                cur.execute(self._sql["INSERT"], binds)
            finally:
                cur.close()

            lote = []
            for resp in (respostas or []):
                lote.append({"id": db_conn.next_id(c, self._seq_resp), "ticket_id": tid,
                             "parameter_id": int(resp["parameter_id"]),
                             "answer_value": resp.get("answer_value"), "actor": ator_limpo})
            if lote:
                cur = c.cursor()
                try:
                    cur.executemany(self._sql["INSERT_ANS"], lote)
                finally:
                    cur.close()

            if parent_id is None:
                acao, detalhe = "TICKET_CREATE", "Ticket criado para script %s em %s" % (script_id, ambiente)
            else:
                acao = "TICKET_RERUN"
                detalhe = "Reexecucao do ticket %s para script %s em %s" % (parent_id, script_id, ambiente)
            write_audit(c, self._tbl_aud, self._seq_aud,
                             {"actor": solicitante, "ip": ticket.get("source_ip"), "action": acao, "detail": detalhe},
                             "tbsss_tickets", tid)
            return tid

    def request_cancel(self, id, ator, ip, conn=None):
        """Os dois UPDATEs do README §5.6 e a auditoria TICKET_CANCEL numa transacao."""
        ator_limpo = validate_record_actor(ator=ator)
        tid = int(id)
        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["CANCEL_SIGNAL"], {"id": tid, "actor": ator_limpo})
                sinalizou = cur.rowcount == 1
                if sinalizou:
                    cur.execute(self._sql["CANCEL_PENDING"], {"id": tid, "actor": ator_limpo})
                    retorno = "CANCELADO" if cur.rowcount == 1 else "SINALIZADO"
                else:
                    # Terminal, ja sinalizado ou PENDING residual com 'S' (CR-008, R-02): so a propria linha.
                    cur.execute(self._sql["CANCEL_READ"], {"id": tid})
                    row = cur.fetchone()
                    if not row:
                        raise repo_errors.RepoNotFound("Ticket ID %s nao encontrado" % id)
                    status, pedido = (row[0] or "").strip(), (row[1] or "").strip()
                    if status == "PENDING":
                        cur.execute(self._sql["CANCEL_PENDING"], {"id": tid, "actor": ator_limpo})
                        if cur.rowcount != 1:
                            raise repo_errors.RepoConflict("Ticket ID %s alterado por outra operacao" % id)
                        retorno = "CANCELADO"
                    elif status == "RUNNING" and pedido == "Y":
                        retorno = "JA_SINALIZADO"
                    else:
                        retorno = "TERMINAL"
            finally:
                cur.close()
            resultado = {
                "CANCELADO": u"cancelado", "SINALIZADO": u"sinalizado",
                "JA_SINALIZADO": u"já sinalizado", "TERMINAL": u"sem efeito: ticket encerrado",
            }[retorno]
            write_audit(c, self._tbl_aud, self._seq_aud,
                             {"actor": ator_limpo, "ip": ip, "action": "TICKET_CANCEL",
                              "detail": u"resultado: %s" % resultado},
                             "tbsss_tickets", tid)
            return retorno
