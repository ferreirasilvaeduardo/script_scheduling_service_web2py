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

_PRIO = sql_ident.FBI_TCK_FILA_PRIO_CASE
_SCHED = sql_ident.FBI_TCK_FILA_SCHED_CASE
_RUN = sql_ident.FBI_TCK_RUN_AGENTE_CASE

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
    """COMMIT no sucesso e ROLLBACK em excecao, como db_conn.transacao, mas sem registrar como erro de banco os
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
        with db_conn.transacao(self.conn):
            raise valor


def _ler_lob(valor):
    return valor.read() if hasattr(valor, "read") else valor


class RepoSchedulerFila(object):

    def __init__(self, owner, prefixo):
        t = lambda nome: sql_ident.qualificar(owner, prefixo + nome, prefixo=prefixo)  # noqa: E731
        self._p = prefixo
        self._tck, self._scr, self._amb = t("tickets"), t("scripts"), t("ambientes")
        self._agt, self._aud, self._usr, self._per = t("agentes"), t("auditoria"), t("usuarios"), t("perfis")
        self._pfunc, self._pamb, self._pscr = t("perfil_func"), t("perfil_amb"), t("perfil_scr")
        self._func, self._samb, self._agd = t("funcionalidades"), t("script_amb"), t("agendamentos")
        self._seq_agt = sql_ident.qualificar(owner, "sq_%sagentes" % prefixo, prefixo=prefixo)
        self._seq_aud = sql_ident.qualificar(owner, "sq_%sauditoria" % prefixo, prefixo=prefixo)

    @classmethod
    def da_config(cls, cfg):
        return cls(cfg.oracle.owner.strip(), cfg.oracle.table_prefix.strip())

    # -------------------------------------------------------------------------
    # Auditoria (mesma transacao da operacao; README §4.4)
    # -------------------------------------------------------------------------

    def _auditar(self, cur, conn, ator, acao, entidade_id, detalhe):
        if not ator or len(ator) > ATOR_MAX or (detalhe is not None and len(detalhe) > DETALHE_MAX):
            raise ValueError("ator ou detalhe de auditoria fora do limite")
        cur.execute("INSERT INTO " + self._aud + " (id, ator, ip_origem, acao, entidade, entidade_id, detalhe, "
                    "created_at) VALUES (:id, :ator, NULL, :acao, :entidade, :entidade_id, :detalhe, SYSDATE)",
                    id=db_conn.proximo_id(conn, self._seq_aud), ator=ator, acao=acao,
                    entidade="tbsss_agentes", entidade_id=entidade_id, detalhe=detalhe)

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
            cur.execute("SELECT nome, ativo FROM " + self._amb + " WHERE nome IN (" + ph + ")", binds)
            achados = dict((r[0], (r[1] or "").strip()) for r in cur.fetchall())
        finally:
            cur.close()
        return [n for n in nomes if achados.get(n) == "S"], [n for n in nomes if n not in achados]

    def candidatos(self, conn, ambientes, interpretadores, lote, envelhecimento_min):
        """Lote de tickets PENDING vencidos, pela prioridade efetiva (README §8.2; CR-007 R-07; CR-008 R-20)."""
        if not ambientes or not interpretadores or lote < 1:
            return []
        ph_amb, binds = _placeholders("amb", list(ambientes))
        ph_int, b_int = _placeholders("int", list(interpretadores))
        binds.update(b_int)
        binds.update(env_min=int(envelhecimento_min), lote=int(lote))
        sql = (
            "SELECT id, script_id, ambiente FROM ("
            " SELECT t.id, t.script_id, t.ambiente"
            " FROM " + self._tck + " t"
            " JOIN " + self._scr + " s ON s.id = t.script_id"
            " WHERE (" + _PRIO + ") IS NOT NULL"
            " AND (" + _SCHED + ") <= SYSDATE"
            " AND t.ambiente IN (" + ph_amb + ")"
            " AND s.interpretador IN (" + ph_int + ")"
            " AND t.cancel_requested = 'N'"
            " AND s.max_qtd_parallel_env > (SELECT COUNT(*) FROM " + self._tck + " r"
            " WHERE r.script_id = t.script_id AND r.ambiente = t.ambiente AND r.status = 'RUNNING')"
            " ORDER BY GREATEST(1, (" + _PRIO + ")"
            " - CASE WHEN :env_min > 0"
            " THEN FLOOR((SYSDATE - GREATEST((" + _SCHED + "), t.created_at)) * 1440 / :env_min)"
            " ELSE 0 END),"
            " (" + _SCHED + "),"
            " t.id"
            ") WHERE ROWNUM <= :lote"
        )
        cur = conn.cursor()
        try:
            cur.execute(sql, binds)
            return [{"id": r[0], "script_id": r[1], "ambiente": r[2]} for r in cur.fetchall()]
        finally:
            cur.close()

    def claim(self, conn, ticket_id, script_id, ambiente, agente_id):
        """Claim em tres passos numa transacao (README §8.3). (True, None, started_at) ou (False, motivo, None)
        com motivo 'LOCK' (ORA-30006/54), 'TETO' ou 'PERDIDO'. Ordem de locks: scripts -> tickets."""
        cur = conn.cursor()
        try:
            try:
                cur.execute("SELECT id, max_qtd_parallel_env FROM " + self._scr + " WHERE id = :script_id "
                            "FOR UPDATE WAIT 5", script_id=int(script_id))
                linha = cur.fetchone()
            except Exception as exc:
                conn.rollback()
                if db_conn.eh_lock(exc):
                    return False, "LOCK", None
                raise
            if linha is None:
                conn.rollback()
                return False, "PERDIDO", None
            cur.execute("SELECT COUNT(*) FROM " + self._tck + " WHERE script_id = :script_id AND ambiente = :ambiente "
                        "AND status = 'RUNNING'", script_id=int(script_id), ambiente=ambiente)
            if cur.fetchone()[0] >= int(linha[1]):
                conn.rollback()
                return False, "TETO", None
            started = db_conn.variavel_saida(cur, db_conn.TIPO_DATE)
            cur.execute("UPDATE " + self._tck + " SET status = 'RUNNING', agente_id = :agente_id, "
                        "started_at = SYSDATE, heartbeat_at = SYSDATE, log_output = EMPTY_CLOB(), "
                        "log_offset_chars = 0, updated_at = SYSDATE, updated_by = :ator "
                        "WHERE id = :ticket_id AND status = 'PENDING' AND cancel_requested = 'N' "
                        "RETURNING started_at INTO :started_at",
                        agente_id=agente_id, ator=ator_sistema(agente_id), ticket_id=int(ticket_id),
                        started_at=started)
            if cur.rowcount != 1:
                conn.rollback()
                return False, "PERDIDO", None
            valor = db_conn.valor_saida(started)
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
            cur.execute("SELECT id, script_id, ambiente, solicitante, status, prioridade, cancel_requested, "
                        "agente_id, process_id, process_start, parent_ticket_id, agendamento_id, scheduled_at, "
                        "started_at, created_at, log_offset_chars, parametros_enviados FROM " + self._tck +
                        " WHERE id = :id",
                        id=int(ticket_id))
            r = cur.fetchone()
            if r is None:
                return None
            nomes = ("id", "script_id", "ambiente", "solicitante", "status", "prioridade", "cancel_requested",
                     "agente_id", "process_id", "process_start", "parent_ticket_id", "agendamento_id",
                     "scheduled_at", "started_at", "created_at", "log_offset_chars", "parametros_enviados")
            dados = dict(zip(nomes, r))
            dados["parametros_enviados"] = _ler_lob(dados["parametros_enviados"])
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
            cur.execute("SELECT id, nome, interpretador, path_file, ativo, timeout_seg "
                        "FROM " + self._scr + " WHERE id = :id", id=int(ticket["script_id"]))
            r = cur.fetchone()
            script = None if r is None else dict(zip(
                ("id", "nome", "interpretador", "path_file", "ativo", "timeout_seg"), r))
            cur.execute("SELECT id, nome, descricao, conexao, ativo FROM " + self._amb + " WHERE nome = :nome",
                        nome=ticket["ambiente"])
            r = cur.fetchone()
            ambiente = None if r is None else dict(zip(("id", "nome", "descricao", "conexao", "ativo"), r))
            homologacoes = frozenset()
            if script is not None:
                cur.execute("SELECT ambiente_id FROM " + self._samb + " WHERE script_id = :id", id=script["id"])
                homologacoes = frozenset(x[0] for x in cur.fetchall())
            ctx = self._ctx_solicitante(cur, ticket.get("solicitante"))
            agendamento = None
            if ticket.get("agendamento_id") is not None:
                cur.execute("SELECT nome, tipo_recorrencia FROM " + self._agd + " WHERE id = :id",
                            id=int(ticket["agendamento_id"]))
                r = cur.fetchone()
                agendamento = None if r is None else {"nome": r[0], "tipo_recorrencia": (r[1] or "").strip()}
        finally:
            cur.close()
        for d in (script, ambiente):
            if d is not None:
                d["ativo"] = (d.get("ativo") or "").strip()
        return {"script": script, "ambiente": ambiente, "homologacoes": homologacoes, "ctx": ctx,
                "agendamento": agendamento}

    def _ctx_solicitante(self, cur, login):
        """Contexto RBAC do solicitante (o mesmo da web: rbac.contexto_usuario), ou None se ele nao existe."""
        if not login:
            return None
        cur.execute("SELECT u.id, u.login, u.nome, u.perfil_id, u.ativo, u.sessao_epoch, p.nome, p.is_admin, "
                    "p.ativo, p.perm_versao FROM " + self._usr + " u JOIN " + self._per + " p ON p.id = u.perfil_id "
                    "WHERE u.login = :login", login=login)
        r = cur.fetchone()
        if r is None:
            return None
        estado = {"usuario_id": r[0], "login": r[1], "nome": r[2], "perfil_id": r[3],
                  "usuario_ativo": (r[4] or "").strip(), "sessao_epoch": r[5], "perfil_nome": r[6],
                  "is_admin": (r[7] or "").strip(), "perfil_ativo": (r[8] or "").strip(), "perm_versao": r[9]}
        cur.execute("SELECT f.codigo FROM " + self._pfunc + " pf JOIN " + self._func + " f ON f.id = pf.funcionalidade_id "
                    "WHERE pf.perfil_id = :p AND f.ativo = 'S'", p=estado["perfil_id"])
        estado["funcionalidades"] = [x[0] for x in cur.fetchall()]
        cur.execute("SELECT a.nome FROM " + self._pamb + " pa JOIN " + self._amb + " a ON a.id = pa.ambiente_id "
                    "WHERE pa.perfil_id = :p", p=estado["perfil_id"])
        estado["ambientes"] = [x[0] for x in cur.fetchall()]
        cur.execute("SELECT script_id FROM " + self._pscr + " WHERE perfil_id = :p", p=estado["perfil_id"])
        estado["scripts"] = [x[0] for x in cur.fetchall()]
        return rbac.contexto_usuario(estado)

    def script_ativo_homologado(self, conn, script_id, ambiente):
        """Script ativo e homologado para o ambiente (README §8.4 passo 1)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM " + self._scr + " s JOIN " + self._samb + " sa ON sa.script_id = s.id "
                        "JOIN " + self._amb + " a ON a.id = sa.ambiente_id "
                        "WHERE s.id = :script_id AND s.ativo = 'S' AND a.nome = :ambiente",
                        script_id=int(script_id), ambiente=ambiente)
            return cur.fetchone()[0] > 0
        finally:
            cur.close()

    def cancelamento_pedido(self, conn, ticket_id):
        """cancel_requested pela PK, sem lock (CR-007, R-28)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT cancel_requested FROM " + self._tck + " WHERE id = :id", id=int(ticket_id))
            r = cur.fetchone()
            return r is not None and (r[0] or "").strip() == "S"
        finally:
            cur.close()

    # -------------------------------------------------------------------------
    # Transicoes do ticket (§5.1, §8.4 passo 5, §8.7)
    # -------------------------------------------------------------------------

    def registrar_pid(self, conn, ticket_id, agente_id, pid, process_start):
        """PID e identidade do processo (README §8.4 passo 5). Rotina tecnica, sem updated_*.
        False = posse perdida (OWNERSHIP_LOST)."""
        with db_conn.transacao(conn):
            cur = conn.cursor()
            try:
                cur.execute("UPDATE " + self._tck + " SET process_id = :pid, process_start = :process_start "
                            "WHERE id = :ticket_id AND agente_id = :agente_id AND status = 'RUNNING'",
                            pid=int(pid), process_start=process_start, ticket_id=int(ticket_id), agente_id=agente_id)
                return cur.rowcount == 1
            finally:
                cur.close()

    def devolver(self, conn, ticket_id, agente_id):
        """RUNNING -> PENDING para script nunca iniciado (CR-007 R-03); com cancelamento pedido, CANCELLED/
        CANCEL_USER/-1 na mesma transacao (CR-008 R-02). 'DEVOLVIDO' | 'CANCELADO' | 'PERDIDO'."""
        ator = ator_sistema(agente_id)
        with db_conn.transacao(conn):
            cur = conn.cursor()
            try:
                cur.execute("UPDATE " + self._tck + " SET status = 'PENDING', agente_id = NULL, started_at = NULL, "
                            "heartbeat_at = NULL, log_output = NULL, log_offset_chars = 0, "
                            "updated_at = SYSDATE, updated_by = :ator WHERE id = :ticket_id AND status = 'RUNNING' "
                            "AND agente_id = :agente_id AND process_id IS NULL AND cancel_requested = 'N'",
                            ator=ator, ticket_id=int(ticket_id), agente_id=agente_id)
                if cur.rowcount == 1:
                    return "DEVOLVIDO"
                cur.execute("UPDATE " + self._tck + " SET status = 'CANCELLED', status_motivo = 'CANCEL_USER', "
                            "return_code = -1, finished_at = SYSDATE, updated_at = SYSDATE, updated_by = :ator "
                            "WHERE id = :ticket_id AND status = 'RUNNING' AND agente_id = :agente_id "
                            "AND process_id IS NULL AND cancel_requested = 'S'",
                            ator=ator, ticket_id=int(ticket_id), agente_id=agente_id)
                return "CANCELADO" if cur.rowcount == 1 else "PERDIDO"
            finally:
                cur.close()

    def finalizar(self, conn, ticket_id, agente_id, status, motivo, rc):
        """Finalizacao pelo agente dono (README §8.7 passo 4). False = posse perdida (rowcount 0)."""
        if status not in TERMINAIS:
            raise ValueError("status terminal invalido: %r" % (status,))
        with db_conn.transacao(conn):
            cur = conn.cursor()
            try:
                cur.execute("UPDATE " + self._tck + " SET status = :status, status_motivo = :motivo, "
                            "return_code = :rc, finished_at = SYSDATE, updated_at = SYSDATE, updated_by = :ator "
                            "WHERE id = :ticket_id AND agente_id = :agente_id AND status = 'RUNNING'",
                            status=status, motivo=motivo, rc=rc, ator=ator_sistema(agente_id),
                            ticket_id=int(ticket_id), agente_id=agente_id)
                return cur.rowcount == 1
            finally:
                cur.close()

    def varredura_propria(self, conn, agente_id):
        """{ticket_id: cancel_requested} dos RUNNING deste agente (README §8.7; ix_tck_run)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT id, cancel_requested FROM " + self._tck + " WHERE (" + _RUN + ") = :agente_id",
                        agente_id=agente_id)
            return dict((r[0], (r[1] or "").strip()) for r in cur.fetchall())
        finally:
            cur.close()

    def tickets_running_do_agente(self, conn, agente_id):
        """RUNNING deste agente para o startup check (README §8.12 passo 9)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT id, process_id, process_start, cancel_requested FROM " + self._tck +
                        " WHERE (" + _RUN + ") = :agente_id ORDER BY id", agente_id=agente_id)
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
                                    "AND agente_id = :agente_id AND status = 'RUNNING'",
                                    [{"id": i, "agente_id": agente_id} for i in ids], arraydmlrowcounts=True)
                    contagens = cur.getarraydmlrowcounts()
                    perdidos = [i for i, n in zip(ids, contagens) if n == 0]
                cur.execute("UPDATE " + self._agt + " SET heartbeat_at = SYSDATE WHERE codigo = :agente_id "
                            "AND hostname = :hostname AND pid_daemon = :pid AND status = 'ATIVO'",
                            agente_id=agente_id, hostname=hostname, pid=int(pid))
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
            cur.execute("SELECT codigo, config_criticos FROM " + self._agt + " WHERE status = 'ATIVO' "
                        "AND codigo <> :agente_id AND heartbeat_at > SYSDATE - :offline_s / 86400 "
                        "AND (config_criticos IS NULL OR config_criticos <> :config) ORDER BY codigo",
                        agente_id=agente_id, offline_s=int(node_offline_timeout_s), config=config_criticos)
            return [(r[0], r[1]) for r in cur.fetchall()]
        finally:
            cur.close()

    def registrar_agente(self, conn, dados, processo_existe, tentativas=2):
        """Registro do agente sob FOR UPDATE WAIT 5 (README §8.12 passo 7; CR-007 R-11). Devolve o id.

        dados: codigo, hostname, pid, versao, ambientes, plataforma, interpretadores, config_criticos,
        node_offline_timeout_s. processo_existe: plataforma.processo_existe (o repositorio nao conhece o SO).
        Duplicidade: AgenteDuplicado. Corrida na inclusao (uk_<prefixo>agt_codigo): ROLLBACK e nova tentativa.
        """
        for tentativa in range(tentativas):
            try:
                return self._registrar_agente(conn, dados, processo_existe)
            except Exception as exc:
                if tentativa + 1 < tentativas and db_conn.classificar_erro(exc) == ("ORA", 1):
                    continue  # ORA-00001 em uk_<prefixo>agt_codigo: outro processo incluiu antes; relê
                raise

    def _registrar_agente(self, conn, d, processo_existe):
        ator = ator_sistema(d["codigo"])
        with _Transacao(conn):
            cur = conn.cursor()
            try:
                cur.execute("SELECT id, hostname, pid_daemon, status, "
                            "CASE WHEN heartbeat_at > SYSDATE - :offline_s / 86400 THEN 'S' ELSE 'N' END "
                            "FROM " + self._agt + " WHERE codigo = :codigo FOR UPDATE WAIT 5",
                            codigo=d["codigo"], offline_s=int(d["node_offline_timeout_s"]))
                r = cur.fetchone()
                if r is not None and (r[3] or "").strip() == "ATIVO" and r[4] == "S":
                    outro_host = r[1] != d["hostname"]
                    outro_pid = r[2] is not None and int(r[2]) != int(d["pid"]) and processo_existe(int(r[2]))
                    if outro_host or outro_pid:
                        raise AgenteDuplicado("agent_id %s ativo em %s (pid %s)" % (d["codigo"], r[1], r[2]))
                binds = dict(codigo=d["codigo"], hostname=d["hostname"], pid=int(d["pid"]), versao=d["versao"],
                             ambientes=d["ambientes"], plataforma=d["plataforma"],
                             interpretadores=d["interpretadores"], config=d["config_criticos"], ator=ator)
                cur.execute(
                    "MERGE INTO " + self._agt + " a USING (SELECT :codigo AS codigo FROM DUAL) s "
                    "ON (a.codigo = s.codigo) "
                    "WHEN MATCHED THEN UPDATE SET a.status = 'ATIVO', a.hostname = :hostname, a.pid_daemon = :pid, "
                    "a.versao = :versao, a.ambientes = :ambientes, a.plataforma = :plataforma, "
                    "a.interpretadores = :interpretadores, a.iniciado_em = SYSDATE, a.heartbeat_at = SYSDATE, "
                    "a.config_criticos = :config, a.updated_at = SYSDATE, a.updated_by = :ator "
                    "WHEN NOT MATCHED THEN INSERT (id, codigo, hostname, pid_daemon, versao, ambientes, plataforma, "
                    "interpretadores, status, iniciado_em, heartbeat_at, config_criticos, created_at, created_by) "
                    "VALUES (" + self._seq_agt + ".NEXTVAL, :codigo, :hostname, :pid, :versao, :ambientes, "
                    ":plataforma, :interpretadores, 'ATIVO', SYSDATE, SYSDATE, :config, SYSDATE, :ator)", binds)
                if cur.rowcount != 1:
                    raise RuntimeError("MERGE do agente sem efeito")
                cur.execute("SELECT id FROM " + self._agt + " WHERE codigo = :codigo", codigo=d["codigo"])
                aid = cur.fetchone()[0]
                self._auditar(cur, conn, ator, "AGENTE_INICIO", aid,
                              "Agente iniciado em %s (pid %s, versao %s)" % (d["hostname"], d["pid"], d["versao"]))
                return aid
            finally:
                cur.close()

    def encerrar_agente(self, conn, agente_id, hostname, pid, modo):
        """status = 'PARADO' com updated_* e AGENTE_FIM, com o filtro de hostname/pid do heartbeat (README
        §8.11). False se o registro ja nao era deste processo."""
        ator = ator_sistema(agente_id)
        with db_conn.transacao(conn):
            cur = conn.cursor()
            try:
                cur.execute("UPDATE " + self._agt + " SET status = 'PARADO', updated_at = SYSDATE, updated_by = :ator "
                            "WHERE codigo = :agente_id AND hostname = :hostname AND pid_daemon = :pid "
                            "AND status = 'ATIVO'", ator=ator, agente_id=agente_id, hostname=hostname, pid=int(pid))
                if cur.rowcount != 1:
                    return False
                cur.execute("SELECT id FROM " + self._agt + " WHERE codigo = :agente_id", agente_id=agente_id)
                self._auditar(cur, conn, ator, "AGENTE_FIM", cur.fetchone()[0], "Agente parado (%s)" % modo)
                return True
            finally:
                cur.close()
