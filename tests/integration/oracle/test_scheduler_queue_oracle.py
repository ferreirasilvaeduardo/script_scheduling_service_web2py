# -*- coding: utf-8 -*-
"""Testes do repo_oracle.scheduler_queue (F8.3a; README §5.1, §5.6, §8.2-§8.4, §8.7, §8.12; CR-006; CR-007;

Parte que precisa do Oracle real (SSS_TEST_ORACLE=1), separada de tests.unit.persistence.test_scheduler_queue (CR-022b1)."""
from tests.support import _testenv  # noqa: F401
import datetime
import os
import unittest
from sss.persistence.oracle.scheduler_queue import DuplicateAgent, RegistrationLost, RepoSchedulerQueue


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestSchedulerQueueOracle(unittest.TestCase):
    """Operacoes reais no owner do config.ini, com massa propria e agent_id de teste."""

    @classmethod
    def setUpClass(cls):
        from tests.unit.persistence import test_repo_contract as trc
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
            "script_base_dir": "/opt/tst/base", "node_offline_timeout_s": 120}, lambda p: False)

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
        # CR-023 (D6): caminho real executado gravado junto com o PID; acima de 1000 caracteres, o final.
        self.assertTrue(self.repo.register_pid(self.conn, tid, self.agent, 4321, 777,
                                               script_path="/opt/tst/" + "d/" * 600 + "fim.sh"))
        stored = self.repo.get_ticket(self.conn, tid)["script_path"]
        self.assertEqual((len(stored), stored[:3], stored[-6:]), (1000, "...", "fim.sh"))
        lost, now = self.repo.heartbeat(self.conn, self.agent, "host-teste", os.getpid(), [tid])
        self.assertEqual(lost, [])
        self.assertIsInstance(now, datetime.datetime)
        self.assertEqual(self.repo.return_to_queue(self.conn, tid, self.agent), "PERDIDO", "com PID nunca volta a fila")
        self.assertTrue(self.repo.finalize(self.conn, tid, self.agent, "SUCCESS", "EXIT_OK", 0))
        self.assertFalse(self.repo.finalize(self.conn, tid, self.agent, "FAILED", "EXIT_ERROR", 1))
        t = self.repo.get_ticket(self.conn, tid)
        self.assertEqual((t["status"], t["process_id"], t["process_start"]), ("SUCCESS", 4321, 777))
        cur = self.conn.cursor()
        cur.execute("SELECT script_base_dir FROM " + self.catalog.qualify_table("agents") + " WHERE code = :c",
                    c=self.agent)
        self.assertEqual(cur.fetchone()[0], "/opt/tst/base", "CR-023 (D7): base publicada no registro")
        cur.close()
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
