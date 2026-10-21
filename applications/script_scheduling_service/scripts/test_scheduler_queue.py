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

AGENTE = "srv-01"
ATOR = "SYSTEM:srv-01"


class _Erro(Exception):
    """Erro de driver simulado (classificado pelo texto ORA-nnnnn)."""


class _Var(object):
    def __init__(self, valor=None):
        self.valor = valor

    def getvalue(self):
        return self.valor


class _Cursor(object):
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0
        self._linhas = []
        self._contagens = []

    def var(self, tipo, size=None):
        return _Var()

    def setinputsizes(self, **tipos):
        pass

    def _responder(self, sql, binds):
        self.conn.executados.append((sql, binds))
        for trecho, resposta in self.conn.roteiro:
            if trecho in sql:
                if isinstance(resposta, Exception):
                    raise resposta
                rowcount, linhas = resposta[0], resposta[1]
                self.rowcount, self._linhas = rowcount, list(linhas)
                if len(resposta) > 2:  # valor da variavel de saida (RETURNING)
                    for v in binds.values():
                        if isinstance(v, _Var):
                            v.valor = [resposta[2]]
                return
        if ".NEXTVAL FROM DUAL" in sql:
            self.conn.seq += 1
            self.rowcount, self._linhas = 1, [(self.conn.seq,)]
            return
        self.rowcount, self._linhas = 0, []

    def execute(self, sql, binds=None, **kw):
        self._responder(sql, dict(binds or {}, **kw))

    def executemany(self, sql, linhas, arraydmlrowcounts=False):
        self.conn.executados.append((sql, linhas))
        self._contagens = [self.conn.contagens.get(l["id"], 1) for l in linhas]

    def getarraydmlrowcounts(self):
        return self._contagens

    def fetchone(self):
        return self._linhas[0] if self._linhas else None

    def fetchall(self):
        return list(self._linhas)

    def close(self):
        pass


class _Conn(object):
    def __init__(self, roteiro, contagens=None):
        self.roteiro = roteiro
        self.contagens = contagens or {}
        self.executados = []
        self.commits = 0
        self.rollbacks = 0
        self.seq = 500

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def sql(self, trecho):
        return [s for s, _b in self.executados if trecho in s]


class TestSemBanco(unittest.TestCase):

    def setUp(self):
        self.repo = RepoSchedulerQueue("OWN_X", "pfx_")

    def test_candidatos_sql_literal_e_binds_gerados(self):
        # CR-013: catalogo do agente, RUNNING por par e a janela por ambiente x prioridade em ix_tck_fila.
        conn = _Conn([("FROM OWN_X.pfx_scripts WHERE interpreter IN", (3, [(3, 2), (4, 1), (5, 1)])),
                      ("WHERE status = 'RUNNING' AND environment IN", (1, [(4, "PRD", 1)])),
                      ("UNION ALL", (2, [(7, 3, "PRD"), (8, 4, "HML")]))])
        itens = self.repo.candidates(conn, ["PRD", "HML"], ["PYTHON3", "SH"], 10, 30)
        self.assertEqual(itens, [{"id": 7, "script_id": 3, "environment": "PRD"}, {"id": 8, "script_id": 4, "environment": "HML"}])
        (sql_scr, b_scr), (sql_run, b_run), (sql, binds) = conn.executados
        self.assertIn("interpreter IN (:int0, :int1)", sql_scr)
        self.assertEqual(b_scr, {"int0": "PYTHON3", "int1": "SH"})
        self.assertIn("environment IN (:amb0, :amb1) GROUP BY script_id, environment", sql_run)
        self.assertEqual(b_run, {"amb0": "PRD", "amb1": "HML"})
        inicio = sql_ident.FBI_TCK_QUEUE_START
        self.assertEqual(sql.count("SELECT id, script_id, environment, prio, inicio FROM (SELECT id, script_id"), 8,
                         "2 environments x 4 prioridades")
        self.assertNotIn("SELECT *", sql, "AGENTS §4.12")
        for trecho in ("WHERE status = 'PENDING' AND environment = :amb0 AND priority = 1 AND %s <= SYSDATE" % inicio,
                       "ORDER BY %s, id) WHERE ROWNUM <= :lote" % inicio,
                       "c.status = 'PENDING' AND c.cancel_requested = 'N'",
                       "j.inicio, j.id", "OWN_X.pfx_tickets"):
            self.assertIn(trecho, sql)
        self.assertNotIn("tbsss_", sql)
        # O script 4 esta no teto em PRD (1 de 1): fica fora so da janela de PRD.
        self.assertIn("(script_id IN (:s0_0, :s0_1))", sql)
        self.assertEqual((binds["s0_0"], binds["s0_1"]), (3, 5))
        self.assertIn("(script_id IN (:s1_0, :s1_1, :s1_2))", sql)
        self.assertEqual((binds["lote"], binds["env_min"], binds["amb0"], binds["amb1"]), (10, 30, "PRD", "HML"))
        self.assertEqual(self.repo.candidates(conn, [], ["SH"], 10, 0), [])
        self.assertEqual(self.repo.candidates(conn, ["PRD"], [], 10, 0), [])

    def test_candidatos_sem_script_elegivel_nao_le_a_fila(self):
        conn = _Conn([("FROM OWN_X.pfx_scripts WHERE interpreter IN", (1, [(4, 1)])),
                      ("WHERE status = 'RUNNING' AND environment IN", (1, [(4, "PRD", 1)]))])
        self.assertEqual(self.repo.candidates(conn, ["PRD"], ["SH"], 10, 30), [])
        self.assertEqual(len(conn.executados), 2, "todos no teto: sem a janela")
        conn = _Conn([])
        self.assertEqual(self.repo.candidates(conn, ["PRD"], ["PERL"], 10, 30), [])
        self.assertEqual(len(conn.executados), 1, "nenhum script do interpreter: so o catalogo")

    def test_candidatos_lista_longa_vira_or_de_listas(self):
        conn = _Conn([("FROM OWN_X.pfx_scripts WHERE interpreter IN", (1, [(i, 1) for i in range(1, 1902)])),
                      ("UNION ALL", (0, []))])
        self.repo.candidates(conn, ["PRD"], ["SH"], 10, 30)
        sql = conn.executados[-1][0]
        bloco = sql[sql.index("AND (script_id IN"):sql.index(") ORDER BY")]
        self.assertEqual(bloco.count("script_id IN ("), 3, "1.901 scripts: listas de ate 900 (ORA-01795)")

    def test_claim_ok(self):
        inicio = datetime.datetime(2026, 10, 20, 14, 5, 33)
        conn = _Conn([("FOR UPDATE WAIT 5", (1, [(3, 2)])), ("SELECT COUNT(*)", (1, [(1,)])),
                      ("RETURNING started_at", (1, [], inicio))])
        self.assertEqual(self.repo.claim(conn, 7, 3, "PRD", AGENTE), (True, None, inicio))
        self.assertEqual((conn.commits, conn.rollbacks), (1, 0))
        upd, binds = [x for x in conn.executados if "RETURNING" in x[0]][0]
        for trecho in ("status = 'RUNNING'", "log_output = EMPTY_CLOB()", "log_offset_chars = 0",
                       "updated_at = SYSDATE, updated_by = :actor", "status = 'PENDING' AND cancel_requested = 'N'"):
            self.assertIn(trecho, upd)
        self.assertEqual(binds["actor"], ATOR)
        # Ordem de locks (README §8.3): scripts antes de tickets.
        self.assertIn("OWN_X.pfx_scripts", conn.executados[0][0])

    def test_claim_lock_teto_e_perdido(self):
        casos = (
            ([("FOR UPDATE WAIT 5", _Erro("ORA-30006: resource busy; acquire with WAIT timeout expired"))],
             ("LOCK", "ORA-30006")),
            ([("FOR UPDATE WAIT 5", _Erro("ORA-00054: resource busy"))], ("LOCK", "ORA-00054")),
            ([("FOR UPDATE WAIT 5", (1, [(3, 2)])), ("SELECT COUNT(*)", (1, [(2,)]))], "TETO"),
            ([("FOR UPDATE WAIT 5", (1, [(3, 2)])), ("SELECT COUNT(*)", (1, [(0,)])),
              ("RETURNING started_at", (0, [], None))], "PERDIDO"),
            ([("FOR UPDATE WAIT 5", (0, []))], "PERDIDO"),
        )
        for roteiro, motivo in casos:
            motivo, extra = motivo if isinstance(motivo, tuple) else (motivo, None)
            conn = _Conn(roteiro)
            self.assertEqual(self.repo.claim(conn, 7, 3, "PRD", AGENTE), (False, motivo, extra), motivo)
            self.assertEqual(conn.commits, 0)
            self.assertGreaterEqual(conn.rollbacks, 1)
        with self.assertRaises(_Erro):
            self.repo.claim(_Conn([("FOR UPDATE WAIT 5", _Erro("ORA-01031: insufficient privileges"))]),
                            7, 3, "PRD", AGENTE)

    def test_registrar_pid_e_heartbeat_sem_updated(self):
        conn = _Conn([("SET process_id", (1, []))])
        self.assertTrue(self.repo.register_pid(conn, 7, AGENTE, 4321, 99))
        self.assertNotIn("updated_", conn.executados[0][0])
        self.assertFalse(self.repo.register_pid(_Conn([("SET process_id", (0, []))]), 7, AGENTE, 1, 1))
        agora = datetime.datetime(2026, 10, 20, 15, 0, 0)
        conn = _Conn([("UPDATE OWN_X.pfx_agents", (1, [])), ("SELECT SYSDATE", (1, [(agora,)]))], contagens={8: 0})
        self.assertEqual(self.repo.heartbeat(conn, AGENTE, "host", 77, [7, 8]), ([8], agora))
        self.assertEqual(conn.commits, 1)
        for sql, _b in conn.executados:
            self.assertNotIn("updated_", sql)
        self.assertIn("hostname = :hostname AND daemon_pid = :pid AND status = 'ACTIVE'",
                      conn.sql("pfx_agents")[0])

    def test_heartbeat_sem_tickets_e_registro_perdido(self):
        agora = datetime.datetime(2026, 10, 20, 15, 0, 0)
        conn = _Conn([("UPDATE OWN_X.pfx_agents", (1, [])), ("SELECT SYSDATE", (1, [(agora,)]))])
        self.assertEqual(self.repo.heartbeat(conn, AGENTE, "host", 77, []), ([], agora))
        self.assertEqual(conn.sql("pfx_tickets"), [], "executemany vazio pulado; o do agente nao (R-28)")
        conn = _Conn([("UPDATE OWN_X.pfx_agents", (0, []))])
        with self.assertRaises(RegistrationLost):
            self.repo.heartbeat(conn, AGENTE, "host", 77, [7])
        self.assertEqual((conn.commits, conn.rollbacks), (0, 1))

    def test_devolver_tres_desfechos(self):
        casos = (([("SET status = 'PENDING'", (1, []))], "DEVOLVIDO"),
                 ([("SET status = 'PENDING'", (0, [])), ("SET status = 'CANCELLED'", (1, []))], "CANCELADO"),
                 ([("SET status = 'PENDING'", (0, [])), ("SET status = 'CANCELLED'", (0, []))], "PERDIDO"))
        for roteiro, esperado in casos:
            conn = _Conn(roteiro)
            self.assertEqual(self.repo.return_to_queue(conn, 7, AGENTE), esperado)
            self.assertEqual(conn.commits, 1)
        sqls = [s for s, _b in conn.executados]
        self.assertIn("process_id IS NULL AND cancel_requested = 'N'", sqls[0])
        self.assertIn("process_id IS NULL AND cancel_requested = 'Y'", sqls[1])
        self.assertIn("status_reason = 'CANCEL_USER', return_code = -1", sqls[1])
        for s in sqls:
            self.assertIn("updated_at = SYSDATE, updated_by = :actor", s)

    def test_finalizar(self):
        conn = _Conn([("finished_at = SYSDATE", (1, []))])
        self.assertTrue(self.repo.finalize(conn, 7, AGENTE, "FAILED", "TIMEOUT", -3))
        sql, binds = conn.executados[0]
        self.assertIn("WHERE id = :ticket_id AND agent_id = :agent_id AND status = 'RUNNING'", sql)
        self.assertEqual((binds["status"], binds["reason"], binds["rc"], binds["actor"]), ("FAILED", "TIMEOUT", -3, ATOR))
        self.assertFalse(self.repo.finalize(_Conn([("finished_at", (0, []))]), 7, AGENTE, "SUCCESS", "EXIT_OK", 0))
        with self.assertRaises(ValueError):
            self.repo.finalize(conn, 7, AGENTE, "RUNNING", None, None)

    def test_varredura_e_running_usam_a_expressao_do_indice(self):
        conn = _Conn([("SELECT id, cancel_requested", (2, [(7, "N"), (8, "Y")]))])
        self.assertEqual(self.repo.own_sweep(conn, AGENTE), {7: "N", 8: "Y"})
        self.assertIn("(" + sql_ident.FBI_TCK_RUN_AGENT_CASE + ") = :agent_id", conn.executados[0][0])
        conn = _Conn([("SELECT id, process_id", (1, [(7, None, None, "N")]))])
        self.assertEqual(self.repo.tickets_running_do_agente(conn, AGENTE),
                         [{"id": 7, "process_id": None, "process_start": None, "cancel_requested": "N"}])

    def _dados_agente(self, **mudancas):
        d = {"code": AGENTE, "hostname": "host-a", "pid": 100, "version": "1.0", "environments": "PRD",
             "platform": "LINUX", "interpreters": "PYTHON3,SH", "critical_config": "hb=10",
             "node_offline_timeout_s": 120}
        d.update(mudancas)
        return d

    def test_registrar_agente_merge_e_auditoria(self):
        conn = _Conn([("FOR UPDATE WAIT 5", (0, [])), ("MERGE INTO", (1, [])), ("SELECT id FROM", (1, [(42,)]))])
        self.assertEqual(self.repo.register_agent(conn, self._dados_agente(), lambda pid: False), 42)
        merge, binds = [x for x in conn.executados if "MERGE INTO" in x[0]][0]
        self.assertIn("a.updated_at = SYSDATE, a.updated_by = :actor", merge)
        self.assertIn("created_at, created_by", merge)
        self.assertIn("sq_pfx_agents.NEXTVAL", merge)
        self.assertEqual(binds["actor"], ATOR)
        aud = [x for x in conn.executados if "INSERT INTO OWN_X.pfx_audit" in x[0]][0]
        self.assertEqual((aud[1]["action"], aud[1]["entity"], aud[1]["entity_id"], aud[1]["actor"]),
                         ("AGENT_START", "tbsss_agents", 42, ATOR))
        self.assertEqual(conn.commits, 1)

    def test_registrar_agente_duplicidade(self):
        def roteiro(host, pid, status="ACTIVE", recente="Y"):
            return [("FOR UPDATE WAIT 5", (1, [(42, host, pid, status, recente)])), ("MERGE INTO", (1, [])),
                    ("SELECT id FROM", (1, [(42,)]))]
        with self.assertRaises(DuplicateAgent):
            self.repo.register_agent(_Conn(roteiro("host-b", 100)), self._dados_agente(), lambda pid: False)
        with self.assertRaises(DuplicateAgent):
            self.repo.register_agent(_Conn(roteiro("host-a", 99)), self._dados_agente(), lambda pid: True)
        # Mesmo host com PID antigo morto, heartbeat antigo ou PARADO: religacao segue.
        for r in (roteiro("host-a", 99), roteiro("host-b", 99, recente="N"), roteiro("host-b", 99, "STOPPED")):
            self.assertEqual(self.repo.register_agent(_Conn(r), self._dados_agente(), lambda pid: False), 42)

    def test_registrar_agente_corrida_na_inclusao(self):
        estado = {"n": 0}

        class _ConnCorrida(_Conn):
            def cursor(conn_self):
                cur = _Cursor(conn_self)
                original = cur.execute

                def execute(sql, binds=None, **kw):
                    if "MERGE INTO" in sql and estado["n"] == 0:
                        estado["n"] += 1
                        raise _Erro("ORA-00001: unique constraint (OWN_X.UK_PFX_AGT_CODE) violated")
                    return original(sql, binds, **kw)
                cur.execute = execute
                return cur

        conn = _ConnCorrida([("FOR UPDATE WAIT 5", (0, [])), ("MERGE INTO", (1, [])), ("SELECT id FROM", (1, [(42,)]))])
        with mock.patch.object(db_conn.logger, "error"):
            self.assertEqual(self.repo.register_agent(conn, self._dados_agente(), lambda pid: False), 42)
        self.assertEqual((conn.rollbacks, conn.commits), (1, 1))

    def test_encerrar_agente(self):
        conn = _Conn([("SET status = 'STOPPED'", (1, [])), ("SELECT id FROM", (1, [(42,)]))])
        self.assertTrue(self.repo.stop_agent(conn, AGENTE, "host-a", 100, "TERMINATE"))
        self.assertIn("updated_at = SYSDATE, updated_by = :actor", conn.executados[0][0])
        self.assertIn("AGENT_STOP", [b.get("action") for _s, b in conn.executados if isinstance(b, dict)])
        self.assertFalse(self.repo.stop_agent(_Conn([("SET status", (0, []))]), AGENTE, "h", 1, "TERMINATE"))

    def test_conferir_config_e_ambientes_ativos(self):
        conn = _Conn([("critical_config <> :config", (1, [("srv-02", "hb=20")]))])
        self.assertEqual(self.repo.check_config(conn, AGENTE, "hb=10", 120), [("srv-02", "hb=20")])
        conn = _Conn([("SELECT name, active", (2, [("PRD", "Y"), ("HML", "N")]))])
        self.assertEqual(self.repo.active_environments(conn, ["PRD", "HML", "DEV"]), (["PRD"], ["DEV"]))
        self.assertEqual(conn.executados[0][1], {"amb0": "DEV", "amb1": "HML", "amb2": "PRD"})

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
        self.assertEqual(ctx["homologacoes"], frozenset({5}))
        self.assertEqual(ctx["agendamento"], {"name": "Noturna", "recurrence_type": "DAILY"})
        import rbac
        self.assertEqual(rbac.pode_executar(ctx["ctx"], ctx["script"], ctx["environment"], ctx["homologacoes"]),
                         (True, rbac.Motivo.OK))

    def test_sql_sem_prefixo_fixo(self):
        with open(scheduler_queue.__file__, encoding="utf-8") as f:
            fonte = f.read()
        self.assertNotIn("tbsss_tickets", fonte)
        self.assertNotIn("import gluon", fonte)
        self.assertNotIn("from gluon", fonte)


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestSchedulerFilaOracle(unittest.TestCase):
    """Operacoes reais no owner do config.ini, com massa propria e agent_id de teste."""

    @classmethod
    def setUpClass(cls):
        import test_repo_contract as trc
        cls.trc = trc
        cls.contrato = trc._OracleContrato
        cls.contrato.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.contrato.tearDownClass.__func__(cls)

    def obter_repo(self, nome):
        return self.contrato.obter_repo(self, nome)

    def _limpar_massa(self):
        return self.contrato._limpar_massa(self)

    def setUp(self):
        self.contrato.setUp(self)
        self.addCleanup(self._limpar_agentes)
        self._massa = self.trc._Massa(self.obter_repo)
        self.c = self._massa.cenario()
        self.catalog = self.obter_repo("catalog")
        self.repo = RepoSchedulerQueue(self.catalog._owner, self.catalog._prefixo)
        self.agente = "tst-f83-%s" % self._massa.suf
        self.amb = self.c["amb1"]["name"]
        self.conn = self.catalog._obter_conexao()
        self.addCleanup(self.conn.close)

    def tearDown(self):
        self.contrato.tearDown(self)

    def _limpar_agentes(self):
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
        return self._massa.ticket(actor="teste", script_id=self.c["scr"]["id"], environment=self.amb,
                                  requested_by=self.c["login"])

    def _registrar(self, pid=None):
        return self.repo.register_agent(self.conn, {
            "code": self.agente, "hostname": "host-teste", "pid": pid or os.getpid(), "version": "teste",
            "environments": self.amb, "platform": "LINUX", "interpreters": "SH", "critical_config": "hb=10",
            "node_offline_timeout_s": 120}, lambda p: False)

    def test_ordem_da_fila_igual_a_ordenacao_completa(self):
        """CR-013: a janela por prioridade devolve o lote exato da ordem (efetiva, inicio, id), sem os scripts
        no teto nem os de outro interpretador; inicio = GREATEST(scheduled_at, created_at) (misfire)."""
        cat = self.catalog
        scr_sh = self.c["scr"]
        scr_teto = self._massa.script("teto", max_parallel_env=1)
        scr_py = self._massa.script("py", interpreter="PYTHON3", path_file="/opt/tst/%s_py.py" % self._massa.suf)
        cur = self.conn.cursor()
        tck = cat.qualify_table("tickets")
        casos = []
        # (script, prioridade, minutos de scheduled_at atras, minutos de created_at atras)
        for i, (sid, prio, sched, crt) in enumerate((
                (scr_sh["id"], 4, 600, 601), (scr_sh["id"], 1, 5, 6), (scr_sh["id"], 2, 90, 91),
                (scr_sh["id"], 3, 300, 2),      # misfire: agendado ha 5 h, criado ha 2 min (espera curta)
                (scr_sh["id"], 2, 30, 31), (scr_sh["id"], 4, 30, 31), (scr_sh["id"], 1, 240, 241),
                (scr_sh["id"], 3, 61, 62), (scr_sh["id"], 2, 120, 121), (scr_teto["id"], 1, 900, 901),
                (scr_py["id"], 1, 900, 901), (scr_sh["id"], 3, -60, 1))):    # o ultimo e do futuro
            tid = self._massa.ticket(actor="teste", script_id=sid, environment=self.amb, requested_by=self.c["login"],
                                     priority=prio)
            cur.execute("UPDATE " + tck + " SET scheduled_at = SYSDATE - :s / 1440, created_at = SYSDATE - :c / 1440"
                        " WHERE id = :id", s=sched, c=crt, id=tid)
            casos.append((tid, sid, prio, sched, crt))
        # O script do teto ja tem um RUNNING no ambiente.
        rodando = self._massa.ticket(actor="teste", script_id=scr_teto["id"], environment=self.amb,
                                     requested_by=self.c["login"])
        cur.execute("UPDATE " + tck + " SET status = 'RUNNING', agent_id = 'tst-outro' WHERE id = :id", id=rodando)
        self.conn.commit()
        env = 60

        def chave(caso):
            tid, _sid, prio, sched, crt = caso
            espera = min(sched, crt)  # minutos desde GREATEST(scheduled_at, created_at)
            return (max(1, prio - espera // env), -espera, tid)
        esperado = [c[0] for c in sorted((c for c in casos if c[1] == scr_sh["id"] and c[3] >= 0), key=chave)]
        for lote in (1, 3, 20):
            obtidos = [x["id"] for x in self.repo.candidates(self.conn, [self.amb], ["SH"], lote, env)]
            self.assertEqual(obtidos, esperado[:lote], "lote %d" % lote)
        sem_env = [x["id"] for x in self.repo.candidates(self.conn, [self.amb], ["SH"], 20, 0)]
        self.assertEqual(sem_env, [c[0] for c in sorted((c for c in casos if c[1] == scr_sh["id"] and c[3] >= 0),
                                                        key=lambda c: (c[2], -min(c[3], c[4]), c[0]))])
        com_py = [x["id"] for x in self.repo.candidates(self.conn, [self.amb], ["SH", "PYTHON3"], 20, env)]
        self.assertIn(casos[10][0], com_py, "PYTHON3 entra com o interpretador")
        self.assertNotIn(casos[9][0], com_py, "script no teto fica fora")
        self.assertNotIn(casos[11][0], com_py, "agendado no futuro fica fora")

    def test_ciclo_completo_do_ticket(self):
        aid = self._registrar()
        self.assertIsInstance(aid, int)
        tid = self._ticket()
        candidatos = self.repo.candidates(self.conn, [self.amb], ["SH"], 10, 30)
        self.assertIn(tid, [c["id"] for c in candidatos])
        ok, motivo, inicio = self.repo.claim(self.conn, tid, self.c["scr"]["id"], self.amb, self.agente)
        self.assertEqual((ok, motivo), (True, None))
        self.assertIsInstance(inicio, datetime.datetime)
        self.assertEqual(self.repo.claim(self.conn, tid, self.c["scr"]["id"], self.amb, self.agente)[:2],
                         (False, "TETO"), "max_qtd_parallel_env = 1 com o ticket RUNNING")
        self.assertEqual(self.repo.own_sweep(self.conn, self.agente), {tid: "N"})
        ctx = self.repo.execution_context(self.conn, self.repo.get_ticket(self.conn, tid))
        self.assertEqual(ctx["ctx"]["login"], self.c["login"])
        self.assertTrue(self.repo.active_homologated_script(self.conn, self.c["scr"]["id"], self.amb))
        self.assertTrue(self.repo.register_pid(self.conn, tid, self.agente, 4321, 777))
        perdidos, agora = self.repo.heartbeat(self.conn, self.agente, "host-teste", os.getpid(), [tid])
        self.assertEqual(perdidos, [])
        self.assertIsInstance(agora, datetime.datetime)
        self.assertEqual(self.repo.return_to_queue(self.conn, tid, self.agente), "PERDIDO", "com PID nunca volta a fila")
        self.assertTrue(self.repo.finalize(self.conn, tid, self.agente, "SUCCESS", "EXIT_OK", 0))
        self.assertFalse(self.repo.finalize(self.conn, tid, self.agente, "FAILED", "EXIT_ERROR", 1))
        t = self.repo.get_ticket(self.conn, tid)
        self.assertEqual((t["status"], t["process_id"], t["process_start"]), ("SUCCESS", 4321, 777))
        tickets = self.obter_repo("tickets")
        self.assertEqual(tickets.get(tid)["updated_by"], "SYSTEM:%s" % self.agente)
        self.assertTrue(self.repo.stop_agent(self.conn, self.agente, "host-teste", os.getpid(), "TERMINATE"))
        with self.assertRaises(RegistrationLost):
            self.repo.heartbeat(self.conn, self.agente, "host-teste", os.getpid(), [])

    def test_devolucao_e_cancelamento_pedido(self):
        self._registrar()
        t1, t2 = self._ticket(), self._ticket()
        self.assertTrue(self.repo.claim(self.conn, t1, self.c["scr"]["id"], self.amb, self.agente)[0])
        self.assertEqual(self.repo.return_to_queue(self.conn, t1, self.agente), "DEVOLVIDO")
        self.assertEqual(self.repo.get_ticket(self.conn, t1)["status"], "PENDING")
        self.assertTrue(self.repo.claim(self.conn, t2, self.c["scr"]["id"], self.amb, self.agente)[0])
        self.obter_repo("tickets").request_cancel(t2, "teste", None)
        self.assertTrue(self.repo.is_cancel_requested(self.conn, t2))
        self.assertEqual(self.repo.return_to_queue(self.conn, t2, self.agente), "CANCELADO")
        t = self.repo.get_ticket(self.conn, t2)
        self.assertEqual(t["status"], "CANCELLED")
        self.assertEqual(self.repo.tickets_running_do_agente(self.conn, self.agente), [])

    def test_duplicidade_e_heartbeat_de_ticket_alheio(self):
        self._registrar()
        with self.assertRaises(DuplicateAgent):
            self.repo.register_agent(self.conn, {
                "code": self.agente, "hostname": "outro-host", "pid": 1, "version": "t", "environments": self.amb,
                "platform": "LINUX", "interpreters": "SH", "critical_config": "hb=10",
                "node_offline_timeout_s": 120}, lambda p: False)
        tid = self._ticket()
        perdidos, _agora = self.repo.heartbeat(self.conn, self.agente, "host-teste", os.getpid(), [tid])
        self.assertEqual(perdidos, [tid], "ticket que nao e RUNNING deste agente")
        self.assertEqual(self.repo.check_config(self.conn, self.agente, "hb=10", 120),
                         [x for x in self.repo.check_config(self.conn, self.agente, "hb=10", 120)
                          if x[0] != self.agente])


if __name__ == "__main__":
    unittest.main()
