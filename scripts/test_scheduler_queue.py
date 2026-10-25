# -*- coding: utf-8 -*-
"""Testes do repo_oracle.scheduler_queue (F8.3a; README §5.1, §5.6, §8.2-§8.4, §8.7, §8.12; CR-006; CR-007;
CR-008 R-02, R-07, R-08, R-09, R-20).

Sem banco: conexao roteirizada (SQL literal, binds gerados por contagem, rowcount, transacoes e updated_*).
Com SSS_TEST_ORACLE=1: as mesmas operacoes no owner e prefixo do instance/config.ini, com massa propria
(ambientes, perfil, usuarios, script e tickets do teste) e um agent_id de teste; tudo removido no fim.
"""
import _testenv  # noqa: F401

import datetime
import os
import unittest
from unittest import mock

import db_conn
import sql_ident
from repo_oracle import scheduler_queue
from repo_oracle.scheduler_queue import DuplicateAgent, RegistrationLost, RepoSchedulerQueue

AGENT = "srv-01"
ACTOR = "SYSTEM:srv-01"


class _Error(Exception):
    """Erro de driver simulado (classificado pelo texto ORA-nnnnn)."""


class _Var(object):
    def __init__(self, value=None):
        self.value = value

    def getvalue(self):
        return self.value


class _Cursor(object):
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0
        self._lines = []
        self._counts = []

    def var(self, kind, size=None):
        return _Var()

    def setinputsizes(self, **types):
        pass

    def _reply(self, sql, binds):
        self.conn.executed.append((sql, binds))
        for snippet, answer in self.conn.script_steps:
            if snippet in sql:
                if isinstance(answer, Exception):
                    raise answer
                rowcount, rows = answer[0], answer[1]
                self.rowcount, self._lines = rowcount, list(rows)
                if len(answer) > 2:  # valor da variavel de saida (RETURNING)
                    for v in binds.values():
                        if isinstance(v, _Var):
                            v.value = [answer[2]]
                return
        if ".NEXTVAL FROM DUAL" in sql:
            self.conn.seq += 1
            self.rowcount, self._lines = 1, [(self.conn.seq,)]
            return
        self.rowcount, self._lines = 0, []

    def execute(self, sql, binds=None, **kw):
        self._reply(sql, dict(binds or {}, **kw))

    def executemany(self, sql, rows, arraydmlrowcounts=False):
        self.conn.executed.append((sql, rows))
        self._counts = [self.conn.counts.get(l["id"], 1) for l in rows]

    def getarraydmlrowcounts(self):
        return self._counts

    def fetchone(self):
        return self._lines[0] if self._lines else None

    def fetchall(self):
        return list(self._lines)

    def close(self):
        pass


class _Conn(object):
    def __init__(self, script_steps, counts=None):
        self.script_steps = script_steps
        self.counts = counts or {}
        self.executed = []
        self.commits = 0
        self.rollbacks = 0
        self.seq = 500

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def sql(self, snippet):
        return [s for s, _b in self.executed if snippet in s]


class TestWithoutDb(unittest.TestCase):

    def setUp(self):
        self.repo = RepoSchedulerQueue("OWN_X", "pfx_")

    def test_candidatos_sql_literal_e_binds_gerados(self):
        # CR-013: catalogo do agente, RUNNING por par e a janela por ambiente x prioridade em ix_tbsss_tck_queue.
        conn = _Conn([("FROM OWN_X.pfx_scripts WHERE interpreter IN", (3, [(3, 2), (4, 1), (5, 1)])),
                      ("WHERE status = 'RUNNING' AND environment IN", (1, [(4, "PRD", 1)])),
                      ("UNION ALL", (2, [(7, 3, "PRD"), (8, 4, "HML")]))])
        items = self.repo.candidates(conn, ["PRD", "HML"], ["PYTHON3", "SH"], 10, 30)
        self.assertEqual(items, [{"id": 7, "script_id": 3, "environment": "PRD"}, {"id": 8, "script_id": 4, "environment": "HML"}])
        (sql_scr, b_scr), (sql_run, b_run), (sql, binds) = conn.executed
        self.assertIn("interpreter IN (:int0, :int1)", sql_scr)
        self.assertEqual(b_scr, {"int0": "PYTHON3", "int1": "SH"})
        self.assertIn("environment IN (:env0, :env1) GROUP BY script_id, environment", sql_run)
        self.assertEqual(b_run, {"env0": "PRD", "env1": "HML"})
        start = sql_ident.FBI_TCK_QUEUE_START
        self.assertEqual(sql.count("SELECT id, script_id, environment, prio, inicio FROM (SELECT id, script_id"), 8,
                         "2 environments x 4 prioridades")
        self.assertNotIn("SELECT *", sql, "AGENTS §4.12")
        for snippet in ("WHERE status = 'PENDING' AND environment = :env0 AND priority = 1 AND %s <= SYSDATE" % start,
                       "ORDER BY %s, id) WHERE ROWNUM <= :batch_size" % start,
                       "c.status = 'PENDING' AND c.cancel_requested = 'N'",
                       "j.inicio, j.id", "OWN_X.pfx_tickets"):
            self.assertIn(snippet, sql)
        self.assertNotIn("tbsss_", sql)
        # O script 4 esta no teto em PRD (1 de 1): fica fora so da janela de PRD.
        self.assertIn("(script_id IN (:s0_0, :s0_1))", sql)
        self.assertEqual((binds["s0_0"], binds["s0_1"]), (3, 5))
        self.assertIn("(script_id IN (:s1_0, :s1_1, :s1_2))", sql)
        self.assertEqual((binds["batch_size"], binds["env_min"], binds["env0"], binds["env1"]), (10, 30, "PRD", "HML"))
        self.assertEqual(self.repo.candidates(conn, [], ["SH"], 10, 0), [])
        self.assertEqual(self.repo.candidates(conn, ["PRD"], [], 10, 0), [])

    def test_candidatos_sem_script_elegivel_nao_le_a_fila(self):
        conn = _Conn([("FROM OWN_X.pfx_scripts WHERE interpreter IN", (1, [(4, 1)])),
                      ("WHERE status = 'RUNNING' AND environment IN", (1, [(4, "PRD", 1)]))])
        self.assertEqual(self.repo.candidates(conn, ["PRD"], ["SH"], 10, 30), [])
        self.assertEqual(len(conn.executed), 2, "todos no teto: sem a janela")
        conn = _Conn([])
        self.assertEqual(self.repo.candidates(conn, ["PRD"], ["PERL"], 10, 30), [])
        self.assertEqual(len(conn.executed), 1, "nenhum script do interpreter: so o catalogo")

    def test_candidatos_lista_longa_vira_or_de_listas(self):
        conn = _Conn([("FROM OWN_X.pfx_scripts WHERE interpreter IN", (1, [(i, 1) for i in range(1, 1902)])),
                      ("UNION ALL", (0, []))])
        self.repo.candidates(conn, ["PRD"], ["SH"], 10, 30)
        sql = conn.executed[-1][0]
        chunk = sql[sql.index("AND (script_id IN"):sql.index(") ORDER BY")]
        self.assertEqual(chunk.count("script_id IN ("), 3, "1.901 scripts: listas de ate 900 (ORA-01795)")

    def test_claim_ok(self):
        start = datetime.datetime(2026, 10, 20, 14, 5, 33)
        conn = _Conn([("FOR UPDATE WAIT 5", (1, [(3, 2)])), ("SELECT COUNT(*)", (1, [(1,)])),
                      ("RETURNING started_at", (1, [], start))])
        self.assertEqual(self.repo.claim(conn, 7, 3, "PRD", AGENT), (True, None, start))
        self.assertEqual((conn.commits, conn.rollbacks), (1, 0))
        upd, binds = [x for x in conn.executed if "RETURNING" in x[0]][0]
        for snippet in ("status = 'RUNNING'", "log_output = EMPTY_CLOB()", "log_offset_chars = 0",
                       "updated_at = SYSDATE, updated_by = :actor", "status = 'PENDING' AND cancel_requested = 'N'"):
            self.assertIn(snippet, upd)
        self.assertEqual(binds["actor"], ACTOR)
        # Ordem de locks (README §8.3): scripts antes de tickets.
        self.assertIn("OWN_X.pfx_scripts", conn.executed[0][0])

    def test_claim_lock_teto_e_perdido(self):
        cases = (
            ([("FOR UPDATE WAIT 5", _Error("ORA-30006: resource busy; acquire with WAIT timeout expired"))],
             ("LOCK", "ORA-30006")),
            ([("FOR UPDATE WAIT 5", _Error("ORA-00054: resource busy"))], ("LOCK", "ORA-00054")),
            ([("FOR UPDATE WAIT 5", (1, [(3, 2)])), ("SELECT COUNT(*)", (1, [(2,)]))], "TETO"),
            ([("FOR UPDATE WAIT 5", (1, [(3, 2)])), ("SELECT COUNT(*)", (1, [(0,)])),
              ("RETURNING started_at", (0, [], None))], "PERDIDO"),
            ([("FOR UPDATE WAIT 5", (0, []))], "PERDIDO"),
        )
        for script_steps, reason in cases:
            reason, extra = reason if isinstance(reason, tuple) else (reason, None)
            conn = _Conn(script_steps)
            self.assertEqual(self.repo.claim(conn, 7, 3, "PRD", AGENT), (False, reason, extra), reason)
            self.assertEqual(conn.commits, 0)
            self.assertGreaterEqual(conn.rollbacks, 1)
        with self.assertRaises(_Error):
            self.repo.claim(_Conn([("FOR UPDATE WAIT 5", _Error("ORA-01031: insufficient privileges"))]),
                            7, 3, "PRD", AGENT)

    def test_registrar_pid_e_heartbeat_sem_updated(self):
        conn = _Conn([("SET process_id", (1, []))])
        self.assertTrue(self.repo.register_pid(conn, 7, AGENT, 4321, 99))
        self.assertNotIn("updated_", conn.executed[0][0])
        self.assertFalse(self.repo.register_pid(_Conn([("SET process_id", (0, []))]), 7, AGENT, 1, 1))
        now = datetime.datetime(2026, 10, 20, 15, 0, 0)
        conn = _Conn([("UPDATE OWN_X.pfx_agents", (1, [])), ("SELECT SYSDATE", (1, [(now,)]))], counts={8: 0})
        self.assertEqual(self.repo.heartbeat(conn, AGENT, "host", 77, [7, 8]), ([8], now))
        self.assertEqual(conn.commits, 1)
        for sql, _b in conn.executed:
            self.assertNotIn("updated_", sql)
        self.assertIn("hostname = :hostname AND daemon_pid = :pid AND status = 'ACTIVE'",
                      conn.sql("pfx_agents")[0])

    def test_heartbeat_sem_tickets_e_registro_perdido(self):
        now = datetime.datetime(2026, 10, 20, 15, 0, 0)
        conn = _Conn([("UPDATE OWN_X.pfx_agents", (1, [])), ("SELECT SYSDATE", (1, [(now,)]))])
        self.assertEqual(self.repo.heartbeat(conn, AGENT, "host", 77, []), ([], now))
        self.assertEqual(conn.sql("pfx_tickets"), [], "executemany vazio pulado; o do agente nao (R-28)")
        conn = _Conn([("UPDATE OWN_X.pfx_agents", (0, []))])
        with self.assertRaises(RegistrationLost):
            self.repo.heartbeat(conn, AGENT, "host", 77, [7])
        self.assertEqual((conn.commits, conn.rollbacks), (0, 1))

    def test_devolver_tres_desfechos(self):
        cases = (([("SET status = 'PENDING'", (1, []))], "DEVOLVIDO"),
                 ([("SET status = 'PENDING'", (0, [])), ("SET status = 'CANCELLED'", (1, []))], "CANCELADO"),
                 ([("SET status = 'PENDING'", (0, [])), ("SET status = 'CANCELLED'", (0, []))], "PERDIDO"))
        for script_steps, expected in cases:
            conn = _Conn(script_steps)
            self.assertEqual(self.repo.return_to_queue(conn, 7, AGENT), expected)
            self.assertEqual(conn.commits, 1)
        sqls = [s for s, _b in conn.executed]
        self.assertIn("process_id IS NULL AND cancel_requested = 'N'", sqls[0])
        self.assertIn("process_id IS NULL AND cancel_requested = 'Y'", sqls[1])
        self.assertIn("status_reason = 'CANCEL_USER', return_code = -1", sqls[1])
        for s in sqls:
            self.assertIn("updated_at = SYSDATE, updated_by = :actor", s)

    def test_finalizar(self):
        conn = _Conn([("finished_at = SYSDATE", (1, []))])
        self.assertTrue(self.repo.finalize(conn, 7, AGENT, "FAILED", "TIMEOUT", -3))
        sql, binds = conn.executed[0]
        self.assertIn("WHERE id = :ticket_id AND agent_id = :agent_id AND status = 'RUNNING'", sql)
        self.assertEqual((binds["status"], binds["reason"], binds["rc"], binds["actor"]), ("FAILED", "TIMEOUT", -3, ACTOR))
        self.assertFalse(self.repo.finalize(_Conn([("finished_at", (0, []))]), 7, AGENT, "SUCCESS", "EXIT_OK", 0))
        with self.assertRaises(ValueError):
            self.repo.finalize(conn, 7, AGENT, "RUNNING", None, None)

    def test_varredura_e_running_usam_a_expressao_do_indice(self):
        conn = _Conn([("SELECT id, cancel_requested", (2, [(7, "N"), (8, "Y")]))])
        self.assertEqual(self.repo.own_sweep(conn, AGENT), {7: "N", 8: "Y"})
        self.assertIn("(" + sql_ident.FBI_TCK_RUN_AGENT_CASE + ") = :agent_id", conn.executed[0][0])
        conn = _Conn([("SELECT id, process_id", (1, [(7, None, None, "N")]))])
        self.assertEqual(self.repo.agent_running_tickets(conn, AGENT),
                         [{"id": 7, "process_id": None, "process_start": None, "cancel_requested": "N"}])

    def _agent_data(self, **changes):
        d = {"code": AGENT, "hostname": "host-a", "pid": 100, "version": "1.0", "environments": "PRD",
             "platform": "LINUX", "interpreters": "PYTHON3,SH", "critical_config": "hb=10",
             "node_offline_timeout_s": 120}
        d.update(changes)
        return d

    def test_registrar_agente_merge_e_auditoria(self):
        conn = _Conn([("FOR UPDATE WAIT 5", (0, [])), ("MERGE INTO", (1, [])), ("SELECT id FROM", (1, [(42,)]))])
        self.assertEqual(self.repo.register_agent(conn, self._agent_data(), lambda pid: False), 42)
        merge, binds = [x for x in conn.executed if "MERGE INTO" in x[0]][0]
        self.assertIn("a.updated_at = SYSDATE, a.updated_by = :actor", merge)
        self.assertIn("created_at, created_by", merge)
        self.assertIn("sq_pfx_agents.NEXTVAL", merge)
        self.assertEqual(binds["actor"], ACTOR)
        aud = [x for x in conn.executed if "INSERT INTO OWN_X.pfx_audit" in x[0]][0]
        self.assertEqual((aud[1]["action"], aud[1]["entity"], aud[1]["entity_id"], aud[1]["actor"]),
                         ("AGENT_START", "tbsss_agents", 42, ACTOR))
        self.assertEqual(conn.commits, 1)

    def test_registrar_agente_duplicidade(self):
        def roteiro(host, pid, status="ACTIVE", recent="Y"):
            return [("FOR UPDATE WAIT 5", (1, [(42, host, pid, status, recent)])), ("MERGE INTO", (1, [])),
                    ("SELECT id FROM", (1, [(42,)]))]
        with self.assertRaises(DuplicateAgent):
            self.repo.register_agent(_Conn(roteiro("host-b", 100)), self._agent_data(), lambda pid: False)
        with self.assertRaises(DuplicateAgent):
            self.repo.register_agent(_Conn(roteiro("host-a", 99)), self._agent_data(), lambda pid: True)
        # Mesmo host com PID antigo morto, heartbeat antigo ou PARADO: religacao segue.
        for r in (roteiro("host-a", 99), roteiro("host-b", 99, recent="N"), roteiro("host-b", 99, "STOPPED")):
            self.assertEqual(self.repo.register_agent(_Conn(r), self._agent_data(), lambda pid: False), 42)

    def test_registrar_agente_corrida_na_inclusao(self):
        state = {"n": 0}

        class _ConnCorrida(_Conn):
            def cursor(conn_self):
                cur = _Cursor(conn_self)
                original = cur.execute

                def execute(sql, binds=None, **kw):
                    if "MERGE INTO" in sql and state["n"] == 0:
                        state["n"] += 1
                        raise _Error("ORA-00001: unique constraint (OWN_X.UK_PFX_AGT_CODE) violated")
                    return original(sql, binds, **kw)
                cur.execute = execute
                return cur

        conn = _ConnCorrida([("FOR UPDATE WAIT 5", (0, [])), ("MERGE INTO", (1, [])), ("SELECT id FROM", (1, [(42,)]))])
        with mock.patch.object(db_conn.logger, "error"):
            self.assertEqual(self.repo.register_agent(conn, self._agent_data(), lambda pid: False), 42)
        self.assertEqual((conn.rollbacks, conn.commits), (1, 1))

    def test_encerrar_agente(self):
        conn = _Conn([("SET status = 'STOPPED'", (1, [])), ("SELECT id FROM", (1, [(42,)]))])
        self.assertTrue(self.repo.stop_agent(conn, AGENT, "host-a", 100, "TERMINATE"))
        self.assertIn("updated_at = SYSDATE, updated_by = :actor", conn.executed[0][0])
        self.assertIn("AGENT_STOP", [b.get("action") for _s, b in conn.executed if isinstance(b, dict)])
        self.assertFalse(self.repo.stop_agent(_Conn([("SET status", (0, []))]), AGENT, "h", 1, "TERMINATE"))

    def test_conferir_config_e_ambientes_ativos(self):
        conn = _Conn([("critical_config <> :config", (1, [("srv-02", "hb=20")]))])
        self.assertEqual(self.repo.check_config(conn, AGENT, "hb=10", 120), [("srv-02", "hb=20")])
        conn = _Conn([("SELECT name, active", (2, [("PRD", "Y"), ("HML", "N")]))])
        self.assertEqual(self.repo.active_environments(conn, ["PRD", "HML", "DEV"]), (["PRD"], ["DEV"]))
        self.assertEqual(conn.executed[0][1], {"env0": "DEV", "env1": "HML", "env2": "PRD"})

    def test_contexto_execucao_monta_o_ctx_rbac(self):
        conn = _Conn([
            ("FROM OWN_X.pfx_scripts WHERE id", (1, [(3, "carga", "SH", "/opt/x.sh", "Y", 60)])),
            ("FROM OWN_X.pfx_environments WHERE name", (1, [(5, "PRD", "Producao", "db:1/x", "Y")])),
            ("SELECT environment_id FROM", (1, [(5,)])),
            ("JOIN OWN_X.pfx_profiles p", (1, [(9, "ana", "Ana", 2, "Y", 0, "Op", "N", "Y", 4)])),
            ("SELECT f.code", (1, [("EXEC_SCRIPT",)])),
            ("SELECT a.name FROM", (1, [("PRD",)])),
            ("SELECT script_id FROM", (1, [(3,)])),
            ("SELECT name, recurrence_type", (1, [("Noturna", "DAILY")])),
        ])
        ctx = self.repo.execution_context(conn, {"script_id": 3, "environment": "PRD", "requested_by": "ana",
                                                 "schedule_id": 12})
        self.assertEqual(ctx["script"]["path_file"], "/opt/x.sh")
        self.assertEqual(ctx["environment"]["description"], "Producao")
        self.assertEqual(ctx["homologations"], frozenset({5}))
        self.assertEqual(ctx["schedule"], {"name": "Noturna", "recurrence_type": "DAILY"})
        import rbac
        self.assertEqual(rbac.can_execute(ctx["ctx"], ctx["script"], ctx["environment"], ctx["homologations"]),
                         (True, rbac.Reason.OK))

    def test_sql_sem_prefixo_fixo(self):
        with open(scheduler_queue.__file__, encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("tbsss_tickets", source)
        self.assertNotIn("import gluon", source)
        self.assertNotIn("from gluon", source)


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestSchedulerQueueOracle(unittest.TestCase):
    """Operacoes reais no owner do config.ini, com massa propria e agent_id de teste."""

    @classmethod
    def setUpClass(cls):
        import test_repo_contract as trc
        cls.trc = trc
        cls.contrato = trc._OracleContract
        cls.contrato.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.contrato.tearDownClass.__func__(cls)

    def obter_repo(self, name):
        return self.contrato.obter_repo(self, name)

    def _clean_fixtures(self):
        return self.contrato._clean_fixtures(self)

    def setUp(self):
        self.contrato.setUp(self)
        self.addCleanup(self._clean_agents)
        self._fixtures = self.trc._Fixtures(self.obter_repo)
        self.c = self._fixtures.scenario()
        self.catalog = self.obter_repo("catalog")
        self.repo = RepoSchedulerQueue(self.catalog._owner, self.catalog._prefixo)
        self.agent = "tst-f83-%s" % self._fixtures.suf
        self.amb = self.c["amb1"]["name"]
        self.conn = self.catalog._obter_conexao()
        self.addCleanup(self.conn.close)

    def tearDown(self):
        self.contrato.tearDown(self)

    def _clean_agents(self):
        conn = self.catalog._obter_conexao()
        try:
            cur = conn.cursor()
            agt, aud = self.catalog.qualify_table("agents"), self.catalog.qualify_table("audit")
            cur.execute("SELECT id FROM " + agt + " WHERE code LIKE 'tst-f83-%'")
            for (aid,) in cur.fetchall():
                cur.execute("DELETE FROM " + aud + " WHERE entity = 'tbsss_agents' AND entity_id = :id", id=aid)
                cur.execute("DELETE FROM " + agt + " WHERE id = :id", id=aid)
            conn.commit()
        finally:
            conn.close()

    def _ticket(self):
        return self._fixtures.ticket(actor="teste", script_id=self.c["scr"]["id"], environment=self.amb,
                                  requested_by=self.c["login"])

    def _register(self, pid=None):
        return self.repo.register_agent(self.conn, {
            "code": self.agent, "hostname": "host-teste", "pid": pid or os.getpid(), "version": "teste",
            "environments": self.amb, "platform": "LINUX", "interpreters": "SH", "critical_config": "hb=10",
            "node_offline_timeout_s": 120}, lambda p: False)

    def test_ordem_da_fila_igual_a_ordenacao_completa(self):
        """CR-013: a janela por prioridade devolve o lote exato da ordem (efetiva, inicio, id), sem os scripts
        no teto nem os de outro interpretador; inicio = GREATEST(scheduled_at, created_at) (misfire)."""
        cat = self.catalog
        scr_sh = self.c["scr"]
        scr_cap = self._fixtures.script("teto", max_parallel_env=1)
        scr_py = self._fixtures.script("py", interpreter="PYTHON3", path_file="/opt/tst/%s_py.py" % self._fixtures.suf)
        cur = self.conn.cursor()
        tck = cat.qualify_table("tickets")
        cases = []
        # (script, prioridade, minutos de scheduled_at atras, minutos de created_at atras)
        for i, (sid, prio, sched, crt) in enumerate((
                (scr_sh["id"], 4, 600, 601), (scr_sh["id"], 1, 5, 6), (scr_sh["id"], 2, 90, 91),
                (scr_sh["id"], 3, 300, 2),      # misfire: agendado ha 5 h, criado ha 2 min (espera curta)
                (scr_sh["id"], 2, 30, 31), (scr_sh["id"], 4, 30, 31), (scr_sh["id"], 1, 240, 241),
                (scr_sh["id"], 3, 61, 62), (scr_sh["id"], 2, 120, 121), (scr_cap["id"], 1, 900, 901),
                (scr_py["id"], 1, 900, 901), (scr_sh["id"], 3, -60, 1))):    # o ultimo e do futuro
            tid = self._fixtures.ticket(actor="teste", script_id=sid, environment=self.amb, requested_by=self.c["login"],
                                     priority=prio)
            cur.execute("UPDATE " + tck + " SET scheduled_at = SYSDATE - :s / 1440, created_at = SYSDATE - :c / 1440"
                        " WHERE id = :id", s=sched, c=crt, id=tid)
            cases.append((tid, sid, prio, sched, crt))
        # O script do teto ja tem um RUNNING no ambiente.
        running = self._fixtures.ticket(actor="teste", script_id=scr_cap["id"], environment=self.amb,
                                     requested_by=self.c["login"])
        cur.execute("UPDATE " + tck + " SET status = 'RUNNING', agent_id = 'tst-outro' WHERE id = :id", id=running)
        self.conn.commit()
        env = 60

        def chave(case):
            tid, _sid, prio, sched, crt = case
            wait = min(sched, crt)  # minutos desde GREATEST(scheduled_at, created_at)
            return (max(1, prio - wait // env), -wait, tid)
        expected = [c[0] for c in sorted((c for c in cases if c[1] == scr_sh["id"] and c[3] >= 0), key=chave)]
        for batch in (1, 3, 20):
            got = [x["id"] for x in self.repo.candidates(self.conn, [self.amb], ["SH"], batch, env)]
            self.assertEqual(got, expected[:batch], "lote %d" % batch)
        without_env = [x["id"] for x in self.repo.candidates(self.conn, [self.amb], ["SH"], 20, 0)]
        self.assertEqual(without_env, [c[0] for c in sorted((c for c in cases if c[1] == scr_sh["id"] and c[3] >= 0),
                                                        key=lambda c: (c[2], -min(c[3], c[4]), c[0]))])
        with_py = [x["id"] for x in self.repo.candidates(self.conn, [self.amb], ["SH", "PYTHON3"], 20, env)]
        self.assertIn(cases[10][0], with_py, "PYTHON3 entra com o interpretador")
        self.assertNotIn(cases[9][0], with_py, "script no teto fica fora")
        self.assertNotIn(cases[11][0], with_py, "agendado no futuro fica fora")

    def test_ciclo_completo_do_ticket(self):
        aid = self._register()
        self.assertIsInstance(aid, int)
        tid = self._ticket()
        candidates = self.repo.candidates(self.conn, [self.amb], ["SH"], 10, 30)
        self.assertIn(tid, [c["id"] for c in candidates])
        ok, reason, start = self.repo.claim(self.conn, tid, self.c["scr"]["id"], self.amb, self.agent)
        self.assertEqual((ok, reason), (True, None))
        self.assertIsInstance(start, datetime.datetime)
        self.assertEqual(self.repo.claim(self.conn, tid, self.c["scr"]["id"], self.amb, self.agent)[:2],
                         (False, "TETO"), "max_qtd_parallel_env = 1 com o ticket RUNNING")
        self.assertEqual(self.repo.own_sweep(self.conn, self.agent), {tid: "N"})
        ctx = self.repo.execution_context(self.conn, self.repo.get_ticket(self.conn, tid))
        self.assertEqual(ctx["ctx"]["login"], self.c["login"])
        self.assertTrue(self.repo.active_homologated_script(self.conn, self.c["scr"]["id"], self.amb))
        self.assertTrue(self.repo.register_pid(self.conn, tid, self.agent, 4321, 777))
        lost, now = self.repo.heartbeat(self.conn, self.agent, "host-teste", os.getpid(), [tid])
        self.assertEqual(lost, [])
        self.assertIsInstance(now, datetime.datetime)
        self.assertEqual(self.repo.return_to_queue(self.conn, tid, self.agent), "PERDIDO", "com PID nunca volta a fila")
        self.assertTrue(self.repo.finalize(self.conn, tid, self.agent, "SUCCESS", "EXIT_OK", 0))
        self.assertFalse(self.repo.finalize(self.conn, tid, self.agent, "FAILED", "EXIT_ERROR", 1))
        t = self.repo.get_ticket(self.conn, tid)
        self.assertEqual((t["status"], t["process_id"], t["process_start"]), ("SUCCESS", 4321, 777))
        tickets = self.obter_repo("tickets")
        self.assertEqual(tickets.get(tid)["updated_by"], "SYSTEM:%s" % self.agent)
        self.assertTrue(self.repo.stop_agent(self.conn, self.agent, "host-teste", os.getpid(), "TERMINATE"))
        with self.assertRaises(RegistrationLost):
            self.repo.heartbeat(self.conn, self.agent, "host-teste", os.getpid(), [])

    def test_devolucao_e_cancelamento_pedido(self):
        self._register()
        t1, t2 = self._ticket(), self._ticket()
        self.assertTrue(self.repo.claim(self.conn, t1, self.c["scr"]["id"], self.amb, self.agent)[0])
        self.assertEqual(self.repo.return_to_queue(self.conn, t1, self.agent), "DEVOLVIDO")
        self.assertEqual(self.repo.get_ticket(self.conn, t1)["status"], "PENDING")
        self.assertTrue(self.repo.claim(self.conn, t2, self.c["scr"]["id"], self.amb, self.agent)[0])
        self.obter_repo("tickets").request_cancel(t2, "teste", None)
        self.assertTrue(self.repo.is_cancel_requested(self.conn, t2))
        self.assertEqual(self.repo.return_to_queue(self.conn, t2, self.agent), "CANCELADO")
        t = self.repo.get_ticket(self.conn, t2)
        self.assertEqual(t["status"], "CANCELLED")
        self.assertEqual(self.repo.agent_running_tickets(self.conn, self.agent), [])

    def test_duplicidade_e_heartbeat_de_ticket_alheio(self):
        self._register()
        with self.assertRaises(DuplicateAgent):
            self.repo.register_agent(self.conn, {
                "code": self.agent, "hostname": "outro-host", "pid": 1, "version": "t", "environments": self.amb,
                "platform": "LINUX", "interpreters": "SH", "critical_config": "hb=10",
                "node_offline_timeout_s": 120}, lambda p: False)
        tid = self._ticket()
        lost, _now = self.repo.heartbeat(self.conn, self.agent, "host-teste", os.getpid(), [tid])
        self.assertEqual(lost, [tid], "ticket que nao e RUNNING deste agente")
        self.assertEqual(self.repo.check_config(self.conn, self.agent, "hb=10", 120),
                         [x for x in self.repo.check_config(self.conn, self.agent, "hb=10", 120)
                          if x[0] != self.agent])


if __name__ == "__main__":
    unittest.main()
