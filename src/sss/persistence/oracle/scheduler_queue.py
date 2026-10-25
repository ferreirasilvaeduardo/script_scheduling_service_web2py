# -*- coding: utf-8 -*-
"""Repositorio interno do daemon: fila, claim, posse e registro do agente (README §5.1, §5.6, §8.2-§8.4, §8.7,
§8.12; CR-007; CR-008 R-02, R-07, R-08, R-09, R-20).

Fora do contrato da UI e sem gluon (o daemon roda em Python puro, F8.3): owner e prefixo vem da configuracao e
todo identificador passa por sql_ident. SQL do README literal, com as expressoes CASE do sql_ident (sem alias).
Cada operacao de escrita e uma transacao propria (COMMIT no sucesso, ROLLBACK em qualquer excecao) e confere
rowcount (AGENTS §4.11). Ator de toda gravacao: 'SYSTEM:<agent_id>' (CR-006); updated_* so nas alteracoes de
negocio (transicoes de status, registro e parada do agente), nunca no heartbeat nem no registro do PID.
"""
from sss.persistence import db_conn
from sss.core import rbac
from sss.core import sql_ident

_START = sql_ident.FBI_TCK_QUEUE_START
_RUN = sql_ident.FBI_TCK_RUN_AGENT_CASE
PRIORITIES = (1, 2, 3, 4)
# Limite de itens de uma lista IN do Oracle (ORA-01795 acima de 1.000): listas maiores viram OR de listas.
_IN_MAX = 900

TERMINAL_STATUSES = ("SUCCESS", "FAILED", "CANCELLED")
DETAIL_MAX = 1000
ACTOR_MAX = 40


class RegistrationLost(RuntimeError):
    """Heartbeat do agente com rowcount 0: outro processo assumiu o registro deste agent_id (CR-007, R-11)."""


class DuplicateAgent(RuntimeError):
    """Outro processo ativo com o mesmo agent_id (README §8.12, passo 7)."""


def system_actor(agent_id):
    return "SYSTEM:%s" % agent_id


def _placeholders(prefix, values):
    """(':p0, :p1', {'p0': v0, 'p1': v1}): placeholders gerados por contagem; valores sempre em bind."""
    names = ["%s%d" % (prefix, i) for i in range(len(values))]
    return ", ".join(":" + n for n in names), dict(zip(names, values))


class _Transaction(object):
    """COMMIT no sucesso e ROLLBACK em excecao, como db_conn.transaction, mas sem registrar como erro de banco os
    desfechos de regra (DuplicateAgent, RegistrationLost): quem chama decide o nivel do log."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, kind, value, tb):
        if kind is None:
            self.conn.commit()
            return False
        if issubclass(kind, (DuplicateAgent, RegistrationLost)):
            self.conn.rollback()
            return False
        with db_conn.transaction(self.conn):
            raise value


def _read_lob(value):
    return value.read() if hasattr(value, "read") else value


class RepoSchedulerQueue(object):

    def __init__(self, owner, prefix):
        t = lambda name: sql_ident.table(owner, prefix, name)  # noqa: E731
        self._p = prefix
        self._tck, self._scr, self._env = t("tickets"), t("scripts"), t("environments")
        self._agt, self._aud, self._usr, self._prf = t("agents"), t("audit"), t("users"), t("profiles")
        self._pfea, self._penv, self._pscr = t("profile_feature"), t("profile_env"), t("profile_script")
        self._fea, self._senv, self._sch = t("features"), t("script_env"), t("schedules")
        self._seq_agt = sql_ident.sequence(owner, prefix, "agents")
        self._seq_aud = sql_ident.sequence(owner, prefix, "audit")

    @classmethod
    def from_config(cls, cfg):
        return cls(cfg.oracle.owner.strip(), cfg.oracle.table_prefix.strip())

    # -------------------------------------------------------------------------
    # Auditoria (mesma transacao da operacao; README §4.4)
    # -------------------------------------------------------------------------

    def _auditar(self, cur, conn, actor, action, entity_id, detail):
        if not actor or len(actor) > ACTOR_MAX or (detail is not None and len(detail) > DETAIL_MAX):
            raise ValueError("ator ou detalhe de auditoria fora do limite")
        cur.execute("INSERT INTO " + self._aud + " (id, actor, source_ip, action, entity, entity_id, detail, "
                    "created_at) VALUES (:id, :actor, NULL, :action, :entity, :entity_id, :detail, SYSDATE)",
                    id=db_conn.next_id(conn, self._seq_aud), actor=actor, action=action,
                    entity="tbsss_agents", entity_id=entity_id, detail=detail)

    # -------------------------------------------------------------------------
    # Selecao de candidatos (§8.2) e claim (§8.3)
    # -------------------------------------------------------------------------

    def active_environments(self, conn, served):
        """(ativos, inexistentes) entre os ambientes atendidos, relidos a cada ciclo do orquestrador (D2)."""
        names = sorted(set(served or ()))
        if not names:
            return [], []
        ph, binds = _placeholders("env", names)
        cur = conn.cursor()
        try:
            cur.execute("SELECT name, active FROM " + self._env + " WHERE name IN (" + ph + ")", binds)
            found = dict((r[0], (r[1] or "").strip()) for r in cur.fetchall())
        finally:
            cur.close()
        return [n for n in names if found.get(n) == "Y"], [n for n in names if n not in found]

    def candidates(self, conn, environments, interpreters, batch, aging_min):
        """Lote de tickets PENDING vencidos, pela prioridade efetiva (README §8.2; CR-007 R-07; CR-008 R-20;
        CR-013).

        Tres leituras curtas, sem varrer a fila: (1) os scripts dos interpretadores do agente e o teto;
        (2) os RUNNING por script e ambiente; (3) a janela: para cada ambiente e prioridade original, os
        `lote` primeiros por (inicio, id) em ix_tbsss_tck_queue, so dos scripts abaixo do teto, juntados e ordenados
        por (prioridade efetiva, inicio, id). Dentro de uma prioridade, a efetiva so cai com a espera, entao
        a janela contem o lote exato da ordem completa (inicio = GREATEST(scheduled_at, created_at)).
        """
        if not environments or not interpreters or batch < 1:
            return []
        environments = list(environments)
        cur = conn.cursor()
        try:
            ph_int, b_int = _placeholders("int", list(interpreters))
            cur.execute("SELECT id, max_parallel_env FROM " + self._scr + " WHERE interpreter IN ("
                        + ph_int + ")", b_int)
            caps = dict((int(sid), int(cap or 0)) for sid, cap in cur.fetchall())
            if not caps:
                return []
            ph_env, b_env = _placeholders("env", environments)
            cur.execute("SELECT script_id, environment, COUNT(*) FROM " + self._tck + " WHERE status = 'RUNNING'"
                        " AND environment IN (" + ph_env + ") GROUP BY script_id, environment", b_env)
            running = dict(((int(sid), env), int(n)) for sid, env, n in cur.fetchall())
            chunks, binds = [], {"batch_size": int(batch), "env_min": int(aging_min)}
            for i, env in enumerate(environments):
                eligible = sorted(sid for sid, cap in caps.items() if running.get((sid, env), 0) < cap)
                if not eligible:
                    continue
                binds["env%d" % i] = env
                names = []
                for k, sid in enumerate(eligible):
                    binds["s%d_%d" % (i, k)] = sid
                    names.append(":s%d_%d" % (i, k))
                filter_value = " OR ".join("script_id IN (" + ", ".join(names[x:x + _IN_MAX]) + ")"
                                     for x in range(0, len(names), _IN_MAX))
                for prio in PRIORITIES:
                    chunks.append(
                        "SELECT id, script_id, environment, prio, inicio FROM ("
                        "SELECT id, script_id, :env%d environment, %d prio, %s inicio FROM %s"
                        " WHERE status = 'PENDING' AND environment = :env%d AND priority = %d AND %s <= SYSDATE"
                        " AND (%s) ORDER BY %s, id) WHERE ROWNUM <= :batch_size"
                        % (i, prio, _START, self._tck, i, prio, _START, filter_value, _START))
            if not chunks:
                return []
            sql = (
                "SELECT id, script_id, environment FROM ("
                " SELECT j.id, j.script_id, j.environment FROM (" + " UNION ALL ".join(chunks) + ") j"
                " JOIN " + self._tck + " c ON c.id = j.id"
                " WHERE c.status = 'PENDING' AND c.cancel_requested = 'N'"
                " ORDER BY GREATEST(1, j.prio - CASE WHEN :env_min > 0"
                " THEN FLOOR((SYSDATE - j.inicio) * 1440 / :env_min) ELSE 0 END),"
                " j.inicio, j.id"
                ") WHERE ROWNUM <= :batch_size"
            )
            cur.execute(sql, binds)
            return [{"id": r[0], "script_id": r[1], "environment": r[2]} for r in cur.fetchall()]
        finally:
            cur.close()

    def claim(self, conn, ticket_id, script_id, environment, agent_id):
        """Claim em tres passos numa transacao (README §8.3). (True, None, started_at) ou (False, motivo, extra)
        com motivo 'LOCK' (extra = o codigo, ORA-30006 ou ORA-00054, para o WARN do laco; README §13, CR-007
        R-32), 'TETO' ou 'PERDIDO' (extra None). Ordem de locks: scripts -> tickets."""
        cur = conn.cursor()
        try:
            try:
                cur.execute("SELECT id, max_parallel_env FROM " + self._scr + " WHERE id = :script_id "
                            "FOR UPDATE WAIT 5", script_id=int(script_id))
                line = cur.fetchone()
            except Exception as exc:
                conn.rollback()
                if db_conn.is_lock(exc):
                    pfx, num = db_conn.classify_error(exc)
                    return False, "LOCK", ("%s-%05d" % (pfx, num)) if pfx else exc.__class__.__name__
                raise
            if line is None:
                conn.rollback()
                return False, "PERDIDO", None
            cur.execute("SELECT COUNT(*) FROM " + self._tck + " WHERE script_id = :script_id AND environment = :environment "
                        "AND status = 'RUNNING'", script_id=int(script_id), environment=environment)
            if cur.fetchone()[0] >= int(line[1]):
                conn.rollback()
                return False, "TETO", None
            started = db_conn.output_variable(cur, db_conn.TIPO_DATE)
            cur.execute("UPDATE " + self._tck + " SET status = 'RUNNING', agent_id = :agent_id, "
                        "started_at = SYSDATE, heartbeat_at = SYSDATE, log_output = EMPTY_CLOB(), "
                        "log_offset_chars = 0, updated_at = SYSDATE, updated_by = :actor "
                        "WHERE id = :ticket_id AND status = 'PENDING' AND cancel_requested = 'N' "
                        "RETURNING started_at INTO :started_at",
                        agent_id=agent_id, actor=system_actor(agent_id), ticket_id=int(ticket_id),
                        started_at=started)
            if cur.rowcount != 1:
                conn.rollback()
                return False, "PERDIDO", None
            value = db_conn.output_value(started)
            conn.commit()
            return True, None, value[0] if isinstance(value, list) else value
        except Exception:
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001 - fluxo previsto (AGENTS §6): a excecao original sobe
                pass
            raise
        finally:
            cur.close()

    # -------------------------------------------------------------------------
    # Leituras do ticket e do contexto (§8.4 passo 1)
    # -------------------------------------------------------------------------

    def get_ticket(self, conn, ticket_id):
        """Ticket pela PK, com o snapshot (CLOB lido), ou None."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT id, script_id, environment, requested_by, status, priority, cancel_requested, "
                        "agent_id, process_id, process_start, parent_ticket_id, schedule_id, scheduled_at, "
                        "started_at, created_at, log_offset_chars, submitted_params FROM " + self._tck +
                        " WHERE id = :id",
                        id=int(ticket_id))
            r = cur.fetchone()
            if r is None:
                return None
            names = ("id", "script_id", "environment", "requested_by", "status", "priority", "cancel_requested",
                     "agent_id", "process_id", "process_start", "parent_ticket_id", "schedule_id",
                     "scheduled_at", "started_at", "created_at", "log_offset_chars", "submitted_params")
            data = dict(zip(names, r))
            data["submitted_params"] = _read_lob(data["submitted_params"])
            for key in ("status", "cancel_requested"):
                data[key] = (data[key] or "").strip()
            return data
        finally:
            cur.close()

    def execution_context(self, conn, ticket):
        """Cadastro atual do script, ambiente, homologacao, contexto RBAC do solicitante e agendamento (CR-007 D2,
        R-24; CR-010). Chaves: script, ambiente (None se inexistente), homologacoes, ctx (None se o solicitante
        nao existe), agendamento (None se manual ou inexistente)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT id, name, interpreter, path_file, active, timeout_s "
                        "FROM " + self._scr + " WHERE id = :id", id=int(ticket["script_id"]))
            r = cur.fetchone()
            script = None if r is None else dict(zip(
                ("id", "name", "interpreter", "path_file", "active", "timeout_s"), r))
            cur.execute("SELECT id, name, description, connection, active FROM " + self._env + " WHERE name = :name",
                        name=ticket["environment"])
            r = cur.fetchone()
            environment = None if r is None else dict(zip(("id", "name", "description", "connection", "active"), r))
            homologations = frozenset()
            if script is not None:
                cur.execute("SELECT environment_id FROM " + self._senv + " WHERE script_id = :id", id=script["id"])
                homologations = frozenset(x[0] for x in cur.fetchall())
            ctx = self._ctx_solicitante(cur, ticket.get("requested_by"))
            schedule = None
            if ticket.get("schedule_id") is not None:
                cur.execute("SELECT name, recurrence_type FROM " + self._sch + " WHERE id = :id",
                            id=int(ticket["schedule_id"]))
                r = cur.fetchone()
                schedule = None if r is None else {"name": r[0], "recurrence_type": (r[1] or "").strip()}
        finally:
            cur.close()
        for d in (script, environment):
            if d is not None:
                d["active"] = (d.get("active") or "").strip()
        return {"script": script, "environment": environment, "homologations": homologations, "ctx": ctx,
                "schedule": schedule}

    def _ctx_solicitante(self, cur, login):
        """Contexto RBAC do solicitante (o mesmo da web: rbac.user_context), ou None se ele nao existe."""
        if not login:
            return None
        cur.execute("SELECT u.id, u.login, u.name, u.profile_id, u.active, u.session_epoch, p.name, p.is_admin, "
                    "p.active, p.perm_version FROM " + self._usr + " u JOIN " + self._prf + " p ON p.id = u.profile_id "
                    "WHERE u.login = :login", login=login)
        r = cur.fetchone()
        if r is None:
            return None
        state = {"user_id": r[0], "login": r[1], "name": r[2], "profile_id": r[3],
                  "active_user": (r[4] or "").strip(), "session_epoch": r[5], "profile_name": r[6],
                  "is_admin": (r[7] or "").strip(), "active_profile": (r[8] or "").strip(), "perm_version": r[9]}
        cur.execute("SELECT f.code FROM " + self._pfea + " pf JOIN " + self._fea + " f ON f.id = pf.feature_id "
                    "WHERE pf.profile_id = :p AND f.active = 'Y'", p=state["profile_id"])
        state["features"] = [x[0] for x in cur.fetchall()]
        cur.execute("SELECT a.name FROM " + self._penv + " pa JOIN " + self._env + " a ON a.id = pa.environment_id "
                    "WHERE pa.profile_id = :p", p=state["profile_id"])
        state["environments"] = [x[0] for x in cur.fetchall()]
        cur.execute("SELECT script_id FROM " + self._pscr + " WHERE profile_id = :p", p=state["profile_id"])
        state["scripts"] = [x[0] for x in cur.fetchall()]
        return rbac.user_context(state)

    def active_homologated_script(self, conn, script_id, environment):
        """Script ativo e homologado para o ambiente (README §8.4 passo 1)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM " + self._scr + " s JOIN " + self._senv + " sa ON sa.script_id = s.id "
                        "JOIN " + self._env + " a ON a.id = sa.environment_id "
                        "WHERE s.id = :script_id AND s.active = 'Y' AND a.name = :environment",
                        script_id=int(script_id), environment=environment)
            return cur.fetchone()[0] > 0
        finally:
            cur.close()

    def is_cancel_requested(self, conn, ticket_id):
        """cancel_requested pela PK, sem lock (CR-007, R-28)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT cancel_requested FROM " + self._tck + " WHERE id = :id", id=int(ticket_id))
            r = cur.fetchone()
            return r is not None and (r[0] or "").strip() == "Y"
        finally:
            cur.close()

    # -------------------------------------------------------------------------
    # Transicoes do ticket (§5.1, §8.4 passo 5, §8.7)
    # -------------------------------------------------------------------------

    def register_pid(self, conn, ticket_id, agent_id, pid, process_start):
        """PID e identidade do processo (README §8.4 passo 5). Rotina tecnica, sem updated_*.
        False = posse perdida (OWNERSHIP_LOST)."""
        with db_conn.transaction(conn):
            cur = conn.cursor()
            try:
                cur.execute("UPDATE " + self._tck + " SET process_id = :pid, process_start = :process_start "
                            "WHERE id = :ticket_id AND agent_id = :agent_id AND status = 'RUNNING'",
                            pid=int(pid), process_start=process_start, ticket_id=int(ticket_id), agent_id=agent_id)
                return cur.rowcount == 1
            finally:
                cur.close()

    def return_to_queue(self, conn, ticket_id, agent_id):
        """RUNNING -> PENDING para script nunca iniciado (CR-007 R-03); com cancelamento pedido, CANCELLED/
        CANCEL_USER/-1 na mesma transacao (CR-008 R-02). 'DEVOLVIDO' | 'CANCELADO' | 'PERDIDO'."""
        actor = system_actor(agent_id)
        with db_conn.transaction(conn):
            cur = conn.cursor()
            try:
                cur.execute("UPDATE " + self._tck + " SET status = 'PENDING', agent_id = NULL, started_at = NULL, "
                            "heartbeat_at = NULL, log_output = NULL, log_offset_chars = 0, "
                            "updated_at = SYSDATE, updated_by = :actor WHERE id = :ticket_id AND status = 'RUNNING' "
                            "AND agent_id = :agent_id AND process_id IS NULL AND cancel_requested = 'N'",
                            actor=actor, ticket_id=int(ticket_id), agent_id=agent_id)
                if cur.rowcount == 1:
                    return "DEVOLVIDO"
                cur.execute("UPDATE " + self._tck + " SET status = 'CANCELLED', status_reason = 'CANCEL_USER', "
                            "return_code = -1, finished_at = SYSDATE, updated_at = SYSDATE, updated_by = :actor "
                            "WHERE id = :ticket_id AND status = 'RUNNING' AND agent_id = :agent_id "
                            "AND process_id IS NULL AND cancel_requested = 'Y'",
                            actor=actor, ticket_id=int(ticket_id), agent_id=agent_id)
                return "CANCELADO" if cur.rowcount == 1 else "PERDIDO"
            finally:
                cur.close()

    def finalize(self, conn, ticket_id, agent_id, status, reason, rc):
        """Finalizacao pelo agente dono (README §8.7 passo 4). False = posse perdida (rowcount 0)."""
        if status not in TERMINAL_STATUSES:
            raise ValueError("status terminal invalido: %r" % (status,))
        with db_conn.transaction(conn):
            cur = conn.cursor()
            try:
                cur.execute("UPDATE " + self._tck + " SET status = :status, status_reason = :reason, "
                            "return_code = :rc, finished_at = SYSDATE, updated_at = SYSDATE, updated_by = :actor "
                            "WHERE id = :ticket_id AND agent_id = :agent_id AND status = 'RUNNING'",
                            status=status, reason=reason, rc=rc, actor=system_actor(agent_id),
                            ticket_id=int(ticket_id), agent_id=agent_id)
                return cur.rowcount == 1
            finally:
                cur.close()

    def mark_node_offline(self, conn, agent_id, node_offline_timeout_s, clock_jump):
        """Deteccao de no offline (README §8.8, literal, em duas etapas; CR-007 R-12; CR-008 R-10).

        Na mesma transacao: SYSDATE primeiro e clock_jump(sysdate) -> True aborta sem marcar nada
        (devolve None; quem chama ja iniciou a suspensao). Depois, os RUNNING de OUTROS agentes com heartbeat
        vencido, FOR UPDATE SKIP LOCKED (linhas travadas ficam para o ciclo seguinte), e o UPDATE por
        executemany com updated_* do agente que detectou (CR-006). Devolve os ids marcados.
        """
        actor = system_actor(agent_id)
        with db_conn.transaction(conn):
            cur = conn.cursor()
            try:
                cur.execute("SELECT SYSDATE FROM DUAL")
                if clock_jump(cur.fetchone()[0]):
                    return None
                cur.execute("SELECT id FROM " + self._tck + " WHERE (" + _RUN + ") IS NOT NULL"
                            " AND (" + _RUN + ") <> :agent_id"
                            " AND heartbeat_at < SYSDATE - :node_offline_timeout_s * INTERVAL '1' SECOND"
                            " FOR UPDATE SKIP LOCKED",
                            agent_id=agent_id, node_offline_timeout_s=int(node_offline_timeout_s))
                ids = [int(r[0]) for r in cur.fetchall()]
                if ids:
                    cur.executemany("UPDATE " + self._tck + " SET status = 'FAILED', status_reason = 'NODE_OFFLINE',"
                                    " return_code = -2, finished_at = SYSDATE, updated_at = SYSDATE, updated_by = :actor"
                                    " WHERE id = :id AND status = 'RUNNING'",
                                    [{"actor": actor, "id": i} for i in ids], arraydmlrowcounts=True)
                    counts = cur.getarraydmlrowcounts()
                    ids = [i for i, n in zip(ids, counts) if n == 1]
                return ids
            finally:
                cur.close()

    def finalize_fenced(self, conn, ticket_id, agent_id):
        """Recuperacao do fencing sem .sss_result (README §8.9): FAILED/FENCED/-2 so se o ticket ainda for deste
        agente e RUNNING. False e esperado se outro no ja o marcou NODE_OFFLINE."""
        return self.finalize(conn, ticket_id, agent_id, "FAILED", "FENCED", -2)

    def own_sweep(self, conn, agent_id):
        """{ticket_id: cancel_requested} dos RUNNING deste agente (README §8.7; ix_tbsss_tck_run)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT id, cancel_requested FROM " + self._tck + " WHERE (" + _RUN + ") = :agent_id",
                        agent_id=agent_id)
            return dict((r[0], (r[1] or "").strip()) for r in cur.fetchall())
        finally:
            cur.close()

    def agent_running_tickets(self, conn, agent_id):
        """RUNNING deste agente para o startup check (README §8.12 passo 9)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT id, process_id, process_start, cancel_requested FROM " + self._tck +
                        " WHERE (" + _RUN + ") = :agent_id ORDER BY id", agent_id=agent_id)
            return [{"id": r[0], "process_id": r[1], "process_start": r[2],
                     "cancel_requested": (r[3] or "").strip()} for r in cur.fetchall()]
        finally:
            cur.close()

    def heartbeat(self, conn, agent_id, hostname, pid, ids):
        """Heartbeat dos tickets (executemany, arraydmlrowcounts) e do agente numa transacao, com o SYSDATE
        (README §8.7; CR-007 R-11, R-28). Devolve (ids perdidos, sysdate). Rotina tecnica: sem updated_*.
        rowcount 0 no agente: ROLLBACK e RegistrationLost. O chamador captura o instante monotonico ANTES desta
        chamada e o promove so se ela voltar (CR-008, R-09)."""
        ids = [int(i) for i in ids]
        with _Transaction(conn):
            cur = conn.cursor()
            try:
                lost = []
                if ids:
                    cur.executemany("UPDATE " + self._tck + " SET heartbeat_at = SYSDATE WHERE id = :id "
                                    "AND agent_id = :agent_id AND status = 'RUNNING'",
                                    [{"id": i, "agent_id": agent_id} for i in ids], arraydmlrowcounts=True)
                    counts = cur.getarraydmlrowcounts()
                    lost = [i for i, n in zip(ids, counts) if n == 0]
                cur.execute("UPDATE " + self._agt + " SET heartbeat_at = SYSDATE WHERE code = :agent_id "
                            "AND hostname = :hostname AND daemon_pid = :pid AND status = 'ACTIVE'",
                            agent_id=agent_id, hostname=hostname, pid=int(pid))
                if cur.rowcount != 1:
                    raise RegistrationLost("registro do agente %s assumido por outro processo" % agent_id)
                cur.execute("SELECT SYSDATE FROM DUAL")
                now = cur.fetchone()[0]
                return lost, now
            finally:
                cur.close()

    # -------------------------------------------------------------------------
    # Registro, conferencia e parada do agente (§8.11, §8.12 passo 7)
    # -------------------------------------------------------------------------

    def check_config(self, conn, agent_id, config_criticos, node_offline_timeout_s):
        """[(codigo, config_criticos)] dos outros agentes ATIVO com heartbeat recente e configuracao diferente
        (CR-007, R-23)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT code, critical_config FROM " + self._agt + " WHERE status = 'ACTIVE' "
                        "AND code <> :agent_id AND heartbeat_at > SYSDATE - :offline_s / 86400 "
                        "AND (critical_config IS NULL OR critical_config <> :config) ORDER BY code",
                        agent_id=agent_id, offline_s=int(node_offline_timeout_s), config=config_criticos)
            return [(r[0], r[1]) for r in cur.fetchall()]
        finally:
            cur.close()

    def register_agent(self, conn, data, process_exists, attempts=2):
        """Registro do agente sob FOR UPDATE WAIT 5 (README §8.12 passo 7; CR-007 R-11). Devolve o id.

        dados: code, hostname, pid, version, environments, platform, interpreters, critical_config,
        node_offline_timeout_s. process_exists: os_platform.process_exists (o repositorio nao conhece o SO).
        Duplicidade: DuplicateAgent. Corrida na inclusao (uk_<prefixo>agt_code): ROLLBACK e nova tentativa.
        """
        for attempt in range(attempts):
            try:
                return self._registrar_agente(conn, data, process_exists)
            except Exception as exc:
                if attempt + 1 < attempts and db_conn.classify_error(exc) == ("ORA", 1):
                    continue  # ORA-00001 em uk_<prefixo>agt_code: outro processo incluiu antes; relê
                raise

    def _registrar_agente(self, conn, d, process_exists):
        actor = system_actor(d["code"])
        with _Transaction(conn):
            cur = conn.cursor()
            try:
                cur.execute("SELECT id, hostname, daemon_pid, status, "
                            "CASE WHEN heartbeat_at > SYSDATE - :offline_s / 86400 THEN 'Y' ELSE 'N' END "
                            "FROM " + self._agt + " WHERE code = :code FOR UPDATE WAIT 5",
                            code=d["code"], offline_s=int(d["node_offline_timeout_s"]))
                r = cur.fetchone()
                if r is not None and (r[3] or "").strip() == "ACTIVE" and r[4] == "Y":
                    other_host = r[1] != d["hostname"]
                    other_pid = r[2] is not None and int(r[2]) != int(d["pid"]) and process_exists(int(r[2]))
                    if other_host or other_pid:
                        raise DuplicateAgent("agent_id %s ativo em %s (pid %s)" % (d["code"], r[1], r[2]))
                binds = dict(code=d["code"], hostname=d["hostname"], pid=int(d["pid"]), version=d["version"],
                             environments=d["environments"], platform=d["platform"],
                             interpreters=d["interpreters"], config=d["critical_config"], actor=actor)
                cur.execute(
                    "MERGE INTO " + self._agt + " a USING (SELECT :code AS code FROM DUAL) s "
                    "ON (a.code = s.code) "
                    "WHEN MATCHED THEN UPDATE SET a.status = 'ACTIVE', a.hostname = :hostname, a.daemon_pid = :pid, "
                    "a.version = :version, a.environments = :environments, a.platform = :platform, "
                    "a.interpreters = :interpreters, a.started_at = SYSDATE, a.heartbeat_at = SYSDATE, "
                    "a.critical_config = :config, a.updated_at = SYSDATE, a.updated_by = :actor "
                    "WHEN NOT MATCHED THEN INSERT (id, code, hostname, daemon_pid, version, environments, platform, "
                    "interpreters, status, started_at, heartbeat_at, critical_config, created_at, created_by) "
                    "VALUES (" + self._seq_agt + ".NEXTVAL, :code, :hostname, :pid, :version, :environments, "
                    ":platform, :interpreters, 'ACTIVE', SYSDATE, SYSDATE, :config, SYSDATE, :actor)", binds)
                if cur.rowcount != 1:
                    raise RuntimeError("MERGE do agente sem efeito")
                cur.execute("SELECT id FROM " + self._agt + " WHERE code = :code", code=d["code"])
                aid = cur.fetchone()[0]
                self._auditar(cur, conn, actor, "AGENT_START", aid,
                              "Agente iniciado em %s (pid %s, versao %s)" % (d["hostname"], d["pid"], d["version"]))
                return aid
            finally:
                cur.close()

    def stop_agent(self, conn, agent_id, hostname, pid, mode):
        """status = 'PARADO' com updated_* e AGENT_STOP, com o filtro de hostname/pid do heartbeat (README
        §8.11). False se o registro ja nao era deste processo."""
        actor = system_actor(agent_id)
        with db_conn.transaction(conn):
            cur = conn.cursor()
            try:
                cur.execute("UPDATE " + self._agt + " SET status = 'STOPPED', updated_at = SYSDATE, updated_by = :actor "
                            "WHERE code = :agent_id AND hostname = :hostname AND daemon_pid = :pid "
                            "AND status = 'ACTIVE'", actor=actor, agent_id=agent_id, hostname=hostname, pid=int(pid))
                if cur.rowcount != 1:
                    return False
                cur.execute("SELECT id FROM " + self._agt + " WHERE code = :agent_id", agent_id=agent_id)
                self._auditar(cur, conn, actor, "AGENT_STOP", cur.fetchone()[0], "Agente parado (%s)" % mode)
                return True
            finally:
                cur.close()
