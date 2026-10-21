# -*- coding: utf-8 -*-
"""Repositorio interno do daemon: fila, claim, posse e registro do agente (README §5.1, §5.6, §8.2-§8.4, §8.7,
§8.12; CR-007; CR-008 R-02, R-07, R-08, R-09, R-20).

Fora do contrato da UI e sem gluon (o daemon roda em Python puro, F8.3): owner e prefixo vem da configuracao e
todo identificador passa por sql_ident. SQL do README literal, com as expressoes CASE do sql_ident (sem alias).
Cada operacao de escrita e uma transacao propria (COMMIT no sucesso, ROLLBACK em qualquer excecao) e confere
rowcount (AGENTS §4.11). Ator de toda gravacao: 'SYSTEM:<agent_id>' (CR-006); updated_* so nas alteracoes de
negocio (transicoes de status, registro e parada do agente), nunca no heartbeat nem no registro do PID.
"""
import db_conn
import rbac
import sql_ident

_INICIO = sql_ident.FBI_TCK_QUEUE_START
_RUN = sql_ident.FBI_TCK_RUN_AGENT_CASE
PRIORIDADES = (1, 2, 3, 4)
# Limite de itens de uma lista IN do Oracle (ORA-01795 acima de 1.000): listas maiores viram OR de listas.
_IN_MAX = 900

TERMINAIS = ("SUCCESS", "FAILED", "CANCELLED")
DETALHE_MAX = 1000
ATOR_MAX = 40


class RegistroPerdido(RuntimeError):
    """Heartbeat do agente com rowcount 0: outro processo assumiu o registro deste agent_id (CR-007, R-11)."""


class AgenteDuplicado(RuntimeError):
    """Outro processo ativo com o mesmo agent_id (README §8.12, passo 7)."""


def ator_sistema(agente_id):
    return "SYSTEM:%s" % agente_id


def _placeholders(prefixo, valores):
    """(':p0, :p1', {'p0': v0, 'p1': v1}): placeholders gerados por contagem; valores sempre em bind."""
    nomes = ["%s%d" % (prefixo, i) for i in range(len(valores))]
    return ", ".join(":" + n for n in nomes), dict(zip(nomes, valores))


class _Transacao(object):
    """COMMIT no sucesso e ROLLBACK em excecao, como db_conn.transaction, mas sem registrar como erro de banco os
    desfechos de regra (AgenteDuplicado, RegistroPerdido): quem chama decide o nivel do log."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, tipo, valor, tb):
        if tipo is None:
            self.conn.commit()
            return False
        if issubclass(tipo, (AgenteDuplicado, RegistroPerdido)):
            self.conn.rollback()
            return False
        with db_conn.transaction(self.conn):
            raise valor


def _ler_lob(valor):
    return valor.read() if hasattr(valor, "read") else valor


class RepoSchedulerFila(object):

    def __init__(self, owner, prefixo):
        t = lambda nome: sql_ident.table(owner, prefixo, nome)  # noqa: E731
        self._p = prefixo
        self._tck, self._scr, self._amb = t("tickets"), t("scripts"), t("ambientes")
        self._agt, self._aud, self._usr, self._per = t("agentes"), t("auditoria"), t("usuarios"), t("perfis")
        self._pfunc, self._pamb, self._pscr = t("perfil_func"), t("perfil_amb"), t("perfil_scr")
        self._func, self._samb, self._agd = t("funcionalidades"), t("script_amb"), t("agendamentos")
        self._seq_agt = sql_ident.sequence(owner, prefixo, "agentes")
        self._seq_aud = sql_ident.sequence(owner, prefixo, "auditoria")

    @classmethod
    def da_config(cls, cfg):
        return cls(cfg.oracle.owner.strip(), cfg.oracle.table_prefix.strip())

    # -------------------------------------------------------------------------
    # Auditoria (mesma transacao da operacao; README §4.4)
    # -------------------------------------------------------------------------

    def _auditar(self, cur, conn, ator, acao, entidade_id, detalhe):
        if not ator or len(ator) > ATOR_MAX or (detalhe is not None and len(detalhe) > DETALHE_MAX):
            raise ValueError("ator ou detalhe de auditoria fora do limite")
        cur.execute("INSERT INTO " + self._aud + " (id, actor, source_ip, action, entity, entity_id, detail, "
                    "created_at) VALUES (:id, :actor, NULL, :action, :entity, :entity_id, :detail, SYSDATE)",
                    id=db_conn.next_id(conn, self._seq_aud), actor=ator, action=acao,
                    entity="tbsss_agents", entity_id=entidade_id, detail=detalhe)

    # -------------------------------------------------------------------------
    # Selecao de candidatos (§8.2) e claim (§8.3)
    # -------------------------------------------------------------------------

    def ambientes_ativos(self, conn, atendidos):
        """(ativos, inexistentes) entre os ambientes atendidos, relidos a cada ciclo do orquestrador (D2)."""
        nomes = sorted(set(atendidos or ()))
        if not nomes:
            return [], []
        ph, binds = _placeholders("amb", nomes)
        cur = conn.cursor()
        try:
            cur.execute("SELECT name, active FROM " + self._amb + " WHERE name IN (" + ph + ")", binds)
            achados = dict((r[0], (r[1] or "").strip()) for r in cur.fetchall())
        finally:
            cur.close()
        return [n for n in nomes if achados.get(n) == "Y"], [n for n in nomes if n not in achados]

    def candidatos(self, conn, ambientes, interpretadores, lote, envelhecimento_min):
        """Lote de tickets PENDING vencidos, pela prioridade efetiva (README §8.2; CR-007 R-07; CR-008 R-20;
        CR-013).

        Tres leituras curtas, sem varrer a fila: (1) os scripts dos interpretadores do agente e o teto;
        (2) os RUNNING por script e ambiente; (3) a janela: para cada ambiente e prioridade original, os
        `lote` primeiros por (inicio, id) em ix_tck_fila, so dos scripts abaixo do teto, juntados e ordenados
        por (prioridade efetiva, inicio, id). Dentro de uma prioridade, a efetiva so cai com a espera, entao
        a janela contem o lote exato da ordem completa (inicio = GREATEST(scheduled_at, created_at)).
        """
        if not ambientes or not interpretadores or lote < 1:
            return []
        ambientes = list(ambientes)
        cur = conn.cursor()
        try:
            ph_int, b_int = _placeholders("int", list(interpretadores))
            cur.execute("SELECT id, max_parallel_env FROM " + self._scr + " WHERE interpreter IN ("
                        + ph_int + ")", b_int)
            tetos = dict((int(sid), int(teto or 0)) for sid, teto in cur.fetchall())
            if not tetos:
                return []
            ph_amb, b_amb = _placeholders("amb", ambientes)
            cur.execute("SELECT script_id, environment, COUNT(*) FROM " + self._tck + " WHERE status = 'RUNNING'"
                        " AND environment IN (" + ph_amb + ") GROUP BY script_id, environment", b_amb)
            rodando = dict(((int(sid), amb), int(n)) for sid, amb, n in cur.fetchall())
            blocos, binds = [], {"lote": int(lote), "env_min": int(envelhecimento_min)}
            for i, amb in enumerate(ambientes):
                elegiveis = sorted(sid for sid, teto in tetos.items() if rodando.get((sid, amb), 0) < teto)
                if not elegiveis:
                    continue
                binds["amb%d" % i] = amb
                nomes = []
                for k, sid in enumerate(elegiveis):
                    binds["s%d_%d" % (i, k)] = sid
                    nomes.append(":s%d_%d" % (i, k))
                filtro = " OR ".join("script_id IN (" + ", ".join(nomes[x:x + _IN_MAX]) + ")"
                                     for x in range(0, len(nomes), _IN_MAX))
                for prio in PRIORIDADES:
                    blocos.append(
                        "SELECT id, script_id, environment, prio, inicio FROM ("
                        "SELECT id, script_id, :amb%d environment, %d prio, %s inicio FROM %s"
                        " WHERE status = 'PENDING' AND environment = :amb%d AND priority = %d AND %s <= SYSDATE"
                        " AND (%s) ORDER BY %s, id) WHERE ROWNUM <= :lote"
                        % (i, prio, _INICIO, self._tck, i, prio, _INICIO, filtro, _INICIO))
            if not blocos:
                return []
            sql = (
                "SELECT id, script_id, environment FROM ("
                " SELECT j.id, j.script_id, j.environment FROM (" + " UNION ALL ".join(blocos) + ") j"
                " JOIN " + self._tck + " c ON c.id = j.id"
                " WHERE c.status = 'PENDING' AND c.cancel_requested = 'N'"
                " ORDER BY GREATEST(1, j.prio - CASE WHEN :env_min > 0"
                " THEN FLOOR((SYSDATE - j.inicio) * 1440 / :env_min) ELSE 0 END),"
                " j.inicio, j.id"
                ") WHERE ROWNUM <= :lote"
            )
            cur.execute(sql, binds)
            return [{"id": r[0], "script_id": r[1], "environment": r[2]} for r in cur.fetchall()]
        finally:
            cur.close()

    def claim(self, conn, ticket_id, script_id, ambiente, agente_id):
        """Claim em tres passos numa transacao (README §8.3). (True, None, started_at) ou (False, motivo, extra)
        com motivo 'LOCK' (extra = o codigo, ORA-30006 ou ORA-00054, para o WARN do laco; README §13, CR-007
        R-32), 'TETO' ou 'PERDIDO' (extra None). Ordem de locks: scripts -> tickets."""
        cur = conn.cursor()
        try:
            try:
                cur.execute("SELECT id, max_parallel_env FROM " + self._scr + " WHERE id = :script_id "
                            "FOR UPDATE WAIT 5", script_id=int(script_id))
                linha = cur.fetchone()
            except Exception as exc:
                conn.rollback()
                if db_conn.is_lock(exc):
                    pfx, num = db_conn.classify_error(exc)
                    return False, "LOCK", ("%s-%05d" % (pfx, num)) if pfx else exc.__class__.__name__
                raise
            if linha is None:
                conn.rollback()
                return False, "PERDIDO", None
            cur.execute("SELECT COUNT(*) FROM " + self._tck + " WHERE script_id = :script_id AND environment = :environment "
                        "AND status = 'RUNNING'", script_id=int(script_id), environment=ambiente)
            if cur.fetchone()[0] >= int(linha[1]):
                conn.rollback()
                return False, "TETO", None
            started = db_conn.output_variable(cur, db_conn.TIPO_DATE)
            cur.execute("UPDATE " + self._tck + " SET status = 'RUNNING', agent_id = :agent_id, "
                        "started_at = SYSDATE, heartbeat_at = SYSDATE, log_output = EMPTY_CLOB(), "
                        "log_offset_chars = 0, updated_at = SYSDATE, updated_by = :actor "
                        "WHERE id = :ticket_id AND status = 'PENDING' AND cancel_requested = 'N' "
                        "RETURNING started_at INTO :started_at",
                        agent_id=agente_id, actor=ator_sistema(agente_id), ticket_id=int(ticket_id),
                        started_at=started)
            if cur.rowcount != 1:
                conn.rollback()
                return False, "PERDIDO", None
            valor = db_conn.output_value(started)
            conn.commit()
            return True, None, valor[0] if isinstance(valor, list) else valor
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

    def obter_ticket(self, conn, ticket_id):
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
            nomes = ("id", "script_id", "environment", "requested_by", "status", "priority", "cancel_requested",
                     "agent_id", "process_id", "process_start", "parent_ticket_id", "schedule_id",
                     "scheduled_at", "started_at", "created_at", "log_offset_chars", "submitted_params")
            dados = dict(zip(nomes, r))
            dados["submitted_params"] = _ler_lob(dados["submitted_params"])
            for chave in ("status", "cancel_requested"):
                dados[chave] = (dados[chave] or "").strip()
            return dados
        finally:
            cur.close()

    def contexto_execucao(self, conn, ticket):
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
            cur.execute("SELECT id, name, description, connection, active FROM " + self._amb + " WHERE name = :name",
                        name=ticket["environment"])
            r = cur.fetchone()
            ambiente = None if r is None else dict(zip(("id", "name", "description", "connection", "active"), r))
            homologacoes = frozenset()
            if script is not None:
                cur.execute("SELECT environment_id FROM " + self._samb + " WHERE script_id = :id", id=script["id"])
                homologacoes = frozenset(x[0] for x in cur.fetchall())
            ctx = self._ctx_solicitante(cur, ticket.get("requested_by"))
            agendamento = None
            if ticket.get("schedule_id") is not None:
                cur.execute("SELECT name, recurrence_type FROM " + self._agd + " WHERE id = :id",
                            id=int(ticket["schedule_id"]))
                r = cur.fetchone()
                agendamento = None if r is None else {"name": r[0], "recurrence_type": (r[1] or "").strip()}
        finally:
            cur.close()
        for d in (script, ambiente):
            if d is not None:
                d["active"] = (d.get("active") or "").strip()
        return {"script": script, "environment": ambiente, "homologacoes": homologacoes, "ctx": ctx,
                "agendamento": agendamento}

    def _ctx_solicitante(self, cur, login):
        """Contexto RBAC do solicitante (o mesmo da web: rbac.contexto_usuario), ou None se ele nao existe."""
        if not login:
            return None
        cur.execute("SELECT u.id, u.login, u.name, u.profile_id, u.active, u.session_epoch, p.name, p.is_admin, "
                    "p.active, p.perm_version FROM " + self._usr + " u JOIN " + self._per + " p ON p.id = u.profile_id "
                    "WHERE u.login = :login", login=login)
        r = cur.fetchone()
        if r is None:
            return None
        estado = {"user_id": r[0], "login": r[1], "name": r[2], "profile_id": r[3],
                  "usuario_ativo": (r[4] or "").strip(), "session_epoch": r[5], "perfil_nome": r[6],
                  "is_admin": (r[7] or "").strip(), "perfil_ativo": (r[8] or "").strip(), "perm_version": r[9]}
        cur.execute("SELECT f.code FROM " + self._pfunc + " pf JOIN " + self._func + " f ON f.id = pf.feature_id "
                    "WHERE pf.profile_id = :p AND f.active = 'Y'", p=estado["profile_id"])
        estado["funcionalidades"] = [x[0] for x in cur.fetchall()]
        cur.execute("SELECT a.name FROM " + self._pamb + " pa JOIN " + self._amb + " a ON a.id = pa.environment_id "
                    "WHERE pa.profile_id = :p", p=estado["profile_id"])
        estado["ambientes"] = [x[0] for x in cur.fetchall()]
        cur.execute("SELECT script_id FROM " + self._pscr + " WHERE profile_id = :p", p=estado["profile_id"])
        estado["scripts"] = [x[0] for x in cur.fetchall()]
        return rbac.contexto_usuario(estado)

    def script_ativo_homologado(self, conn, script_id, ambiente):
        """Script ativo e homologado para o ambiente (README §8.4 passo 1)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM " + self._scr + " s JOIN " + self._samb + " sa ON sa.script_id = s.id "
                        "JOIN " + self._amb + " a ON a.id = sa.environment_id "
                        "WHERE s.id = :script_id AND s.active = 'Y' AND a.name = :environment",
                        script_id=int(script_id), environment=ambiente)
            return cur.fetchone()[0] > 0
        finally:
            cur.close()

    def cancelamento_pedido(self, conn, ticket_id):
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

    def registrar_pid(self, conn, ticket_id, agente_id, pid, process_start):
        """PID e identidade do processo (README §8.4 passo 5). Rotina tecnica, sem updated_*.
        False = posse perdida (OWNERSHIP_LOST)."""
        with db_conn.transaction(conn):
            cur = conn.cursor()
            try:
                cur.execute("UPDATE " + self._tck + " SET process_id = :pid, process_start = :process_start "
                            "WHERE id = :ticket_id AND agent_id = :agent_id AND status = 'RUNNING'",
                            pid=int(pid), process_start=process_start, ticket_id=int(ticket_id), agent_id=agente_id)
                return cur.rowcount == 1
            finally:
                cur.close()

    def devolver(self, conn, ticket_id, agente_id):
        """RUNNING -> PENDING para script nunca iniciado (CR-007 R-03); com cancelamento pedido, CANCELLED/
        CANCEL_USER/-1 na mesma transacao (CR-008 R-02). 'DEVOLVIDO' | 'CANCELADO' | 'PERDIDO'."""
        ator = ator_sistema(agente_id)
        with db_conn.transaction(conn):
            cur = conn.cursor()
            try:
                cur.execute("UPDATE " + self._tck + " SET status = 'PENDING', agent_id = NULL, started_at = NULL, "
                            "heartbeat_at = NULL, log_output = NULL, log_offset_chars = 0, "
                            "updated_at = SYSDATE, updated_by = :actor WHERE id = :ticket_id AND status = 'RUNNING' "
                            "AND agent_id = :agent_id AND process_id IS NULL AND cancel_requested = 'N'",
                            actor=ator, ticket_id=int(ticket_id), agent_id=agente_id)
                if cur.rowcount == 1:
                    return "DEVOLVIDO"
                cur.execute("UPDATE " + self._tck + " SET status = 'CANCELLED', status_reason = 'CANCEL_USER', "
                            "return_code = -1, finished_at = SYSDATE, updated_at = SYSDATE, updated_by = :actor "
                            "WHERE id = :ticket_id AND status = 'RUNNING' AND agent_id = :agent_id "
                            "AND process_id IS NULL AND cancel_requested = 'Y'",
                            actor=ator, ticket_id=int(ticket_id), agent_id=agente_id)
                return "CANCELADO" if cur.rowcount == 1 else "PERDIDO"
            finally:
                cur.close()

    def finalizar(self, conn, ticket_id, agente_id, status, motivo, rc):
        """Finalizacao pelo agente dono (README §8.7 passo 4). False = posse perdida (rowcount 0)."""
        if status not in TERMINAIS:
            raise ValueError("status terminal invalido: %r" % (status,))
        with db_conn.transaction(conn):
            cur = conn.cursor()
            try:
                cur.execute("UPDATE " + self._tck + " SET status = :status, status_reason = :reason, "
                            "return_code = :rc, finished_at = SYSDATE, updated_at = SYSDATE, updated_by = :actor "
                            "WHERE id = :ticket_id AND agent_id = :agent_id AND status = 'RUNNING'",
                            status=status, reason=motivo, rc=rc, actor=ator_sistema(agente_id),
                            ticket_id=int(ticket_id), agent_id=agente_id)
                return cur.rowcount == 1
            finally:
                cur.close()

    def marcar_node_offline(self, conn, agente_id, node_offline_timeout_s, salto_de_relogio):
        """Deteccao de no offline (README §8.8, literal, em duas etapas; CR-007 R-12; CR-008 R-10).

        Na mesma transacao: SYSDATE primeiro e salto_de_relogio(sysdate) -> True aborta sem marcar nada
        (devolve None; quem chama ja iniciou a suspensao). Depois, os RUNNING de OUTROS agentes com heartbeat
        vencido, FOR UPDATE SKIP LOCKED (linhas travadas ficam para o ciclo seguinte), e o UPDATE por
        executemany com updated_* do agente que detectou (CR-006). Devolve os ids marcados.
        """
        ator = ator_sistema(agente_id)
        with db_conn.transaction(conn):
            cur = conn.cursor()
            try:
                cur.execute("SELECT SYSDATE FROM DUAL")
                if salto_de_relogio(cur.fetchone()[0]):
                    return None
                cur.execute("SELECT id FROM " + self._tck + " WHERE (" + _RUN + ") IS NOT NULL"
                            " AND (" + _RUN + ") <> :agent_id"
                            " AND heartbeat_at < SYSDATE - :node_offline_timeout_s * INTERVAL '1' SECOND"
                            " FOR UPDATE SKIP LOCKED",
                            agent_id=agente_id, node_offline_timeout_s=int(node_offline_timeout_s))
                ids = [int(r[0]) for r in cur.fetchall()]
                if ids:
                    cur.executemany("UPDATE " + self._tck + " SET status = 'FAILED', status_reason = 'NODE_OFFLINE',"
                                    " return_code = -2, finished_at = SYSDATE, updated_at = SYSDATE, updated_by = :actor"
                                    " WHERE id = :id AND status = 'RUNNING'",
                                    [{"actor": ator, "id": i} for i in ids], arraydmlrowcounts=True)
                    contagens = cur.getarraydmlrowcounts()
                    ids = [i for i, n in zip(ids, contagens) if n == 1]
                return ids
            finally:
                cur.close()

    def finalizar_fenced(self, conn, ticket_id, agente_id):
        """Recuperacao do fencing sem .sss_result (README §8.9): FAILED/FENCED/-2 so se o ticket ainda for deste
        agente e RUNNING. False e esperado se outro no ja o marcou NODE_OFFLINE."""
        return self.finalizar(conn, ticket_id, agente_id, "FAILED", "FENCED", -2)

    def varredura_propria(self, conn, agente_id):
        """{ticket_id: cancel_requested} dos RUNNING deste agente (README §8.7; ix_tck_run)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT id, cancel_requested FROM " + self._tck + " WHERE (" + _RUN + ") = :agent_id",
                        agent_id=agente_id)
            return dict((r[0], (r[1] or "").strip()) for r in cur.fetchall())
        finally:
            cur.close()

    def tickets_running_do_agente(self, conn, agente_id):
        """RUNNING deste agente para o startup check (README §8.12 passo 9)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT id, process_id, process_start, cancel_requested FROM " + self._tck +
                        " WHERE (" + _RUN + ") = :agent_id ORDER BY id", agent_id=agente_id)
            return [{"id": r[0], "process_id": r[1], "process_start": r[2],
                     "cancel_requested": (r[3] or "").strip()} for r in cur.fetchall()]
        finally:
            cur.close()

    def heartbeat(self, conn, agente_id, hostname, pid, ids):
        """Heartbeat dos tickets (executemany, arraydmlrowcounts) e do agente numa transacao, com o SYSDATE
        (README §8.7; CR-007 R-11, R-28). Devolve (ids_perdidos, sysdate). Rotina tecnica: sem updated_*.
        rowcount 0 no agente: ROLLBACK e RegistroPerdido. O chamador captura o instante monotonico ANTES desta
        chamada e o promove so se ela voltar (CR-008, R-09)."""
        ids = [int(i) for i in ids]
        with _Transacao(conn):
            cur = conn.cursor()
            try:
                perdidos = []
                if ids:
                    cur.executemany("UPDATE " + self._tck + " SET heartbeat_at = SYSDATE WHERE id = :id "
                                    "AND agent_id = :agent_id AND status = 'RUNNING'",
                                    [{"id": i, "agent_id": agente_id} for i in ids], arraydmlrowcounts=True)
                    contagens = cur.getarraydmlrowcounts()
                    perdidos = [i for i, n in zip(ids, contagens) if n == 0]
                cur.execute("UPDATE " + self._agt + " SET heartbeat_at = SYSDATE WHERE code = :agent_id "
                            "AND hostname = :hostname AND daemon_pid = :pid AND status = 'ACTIVE'",
                            agent_id=agente_id, hostname=hostname, pid=int(pid))
                if cur.rowcount != 1:
                    raise RegistroPerdido("registro do agente %s assumido por outro processo" % agente_id)
                cur.execute("SELECT SYSDATE FROM DUAL")
                agora = cur.fetchone()[0]
                return perdidos, agora
            finally:
                cur.close()

    # -------------------------------------------------------------------------
    # Registro, conferencia e parada do agente (§8.11, §8.12 passo 7)
    # -------------------------------------------------------------------------

    def conferir_config(self, conn, agente_id, config_criticos, node_offline_timeout_s):
        """[(codigo, config_criticos)] dos outros agentes ATIVO com heartbeat recente e configuracao diferente
        (CR-007, R-23)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT code, critical_config FROM " + self._agt + " WHERE status = 'ACTIVE' "
                        "AND code <> :agent_id AND heartbeat_at > SYSDATE - :offline_s / 86400 "
                        "AND (critical_config IS NULL OR critical_config <> :config) ORDER BY code",
                        agent_id=agente_id, offline_s=int(node_offline_timeout_s), config=config_criticos)
            return [(r[0], r[1]) for r in cur.fetchall()]
        finally:
            cur.close()

    def registrar_agente(self, conn, dados, processo_existe, tentativas=2):
        """Registro do agente sob FOR UPDATE WAIT 5 (README §8.12 passo 7; CR-007 R-11). Devolve o id.

        dados: code, hostname, pid, version, environments, platform, interpreters, critical_config,
        node_offline_timeout_s. processo_existe: platform.processo_existe (o repositorio nao conhece o SO).
        Duplicidade: AgenteDuplicado. Corrida na inclusao (uk_<prefixo>agt_codigo): ROLLBACK e nova tentativa.
        """
        for tentativa in range(tentativas):
            try:
                return self._registrar_agente(conn, dados, processo_existe)
            except Exception as exc:
                if tentativa + 1 < tentativas and db_conn.classify_error(exc) == ("ORA", 1):
                    continue  # ORA-00001 em uk_<prefixo>agt_codigo: outro processo incluiu antes; relê
                raise

    def _registrar_agente(self, conn, d, processo_existe):
        ator = ator_sistema(d["code"])
        with _Transacao(conn):
            cur = conn.cursor()
            try:
                cur.execute("SELECT id, hostname, daemon_pid, status, "
                            "CASE WHEN heartbeat_at > SYSDATE - :offline_s / 86400 THEN 'Y' ELSE 'N' END "
                            "FROM " + self._agt + " WHERE code = :code FOR UPDATE WAIT 5",
                            code=d["code"], offline_s=int(d["node_offline_timeout_s"]))
                r = cur.fetchone()
                if r is not None and (r[3] or "").strip() == "ACTIVE" and r[4] == "Y":
                    outro_host = r[1] != d["hostname"]
                    outro_pid = r[2] is not None and int(r[2]) != int(d["pid"]) and processo_existe(int(r[2]))
                    if outro_host or outro_pid:
                        raise AgenteDuplicado("agent_id %s ativo em %s (pid %s)" % (d["code"], r[1], r[2]))
                binds = dict(code=d["code"], hostname=d["hostname"], pid=int(d["pid"]), version=d["version"],
                             environments=d["environments"], platform=d["platform"],
                             interpreters=d["interpreters"], config=d["critical_config"], actor=ator)
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
                self._auditar(cur, conn, ator, "AGENT_START", aid,
                              "Agente iniciado em %s (pid %s, versao %s)" % (d["hostname"], d["pid"], d["version"]))
                return aid
            finally:
                cur.close()

    def encerrar_agente(self, conn, agente_id, hostname, pid, modo):
        """status = 'PARADO' com updated_* e AGENT_STOP, com o filtro de hostname/pid do heartbeat (README
        §8.11). False se o registro ja nao era deste processo."""
        ator = ator_sistema(agente_id)
        with db_conn.transaction(conn):
            cur = conn.cursor()
            try:
                cur.execute("UPDATE " + self._agt + " SET status = 'STOPPED', updated_at = SYSDATE, updated_by = :actor "
                            "WHERE code = :agent_id AND hostname = :hostname AND daemon_pid = :pid "
                            "AND status = 'ACTIVE'", actor=ator, agent_id=agente_id, hostname=hostname, pid=int(pid))
                if cur.rowcount != 1:
                    return False
                cur.execute("SELECT id FROM " + self._agt + " WHERE code = :agent_id", agent_id=agente_id)
                self._auditar(cur, conn, ator, "AGENT_STOP", cur.fetchone()[0], "Agente parado (%s)" % modo)
                return True
            finally:
                cur.close()
