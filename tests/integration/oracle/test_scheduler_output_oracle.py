# -*- coding: utf-8 -*-
"""Testes do repo_oracle.scheduler_output (CR-012; README §8.13 e §10, tabela 18)

Parte que precisa do Oracle real (SSS_TEST_ORACLE=1), separada de tests.unit.persistence.test_scheduler_output (CR-022b1)."""
from tests.support import _testenv  # noqa: F401
import json
import os
import subprocess
import sys
import unittest
from sss.persistence.oracle import scheduler_output
from sss.persistence.oracle.scheduler_output import RepoSchedulerOutput, OutputOffsetMismatch
from tests.unit.persistence.test_scheduler_output import _CHILD  # noqa: F401


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestSchedulerOutputOracle(unittest.TestCase):
    """Ciclo real da saida com massa propria; a web le pelo repositorio de tickets."""

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
        from sss.persistence.oracle.scheduler_queue import RepoSchedulerQueue
        self.contrato.setUp(self)
        self._fixtures = self.trc._Fixtures(self.obter_repo)
        self.c = self._fixtures.scenario()
        cat = self.obter_repo("catalog")
        self.queue = RepoSchedulerQueue(cat._owner, cat._prefixo)
        self.repo = RepoSchedulerOutput(cat._owner, cat._prefixo)
        self.agent = "tst-sai-%s" % self._fixtures.suf
        self.amb = self.c["amb1"]["name"]
        self.conn = cat._obter_conexao()
        self.addCleanup(self.conn.close)
        self.tickets = self.obter_repo("tickets")

    def tearDown(self):
        self.contrato.tearDown(self)

    def _agent_ticket(self):
        tid = self._fixtures.ticket(actor="teste", script_id=self.c["scr"]["id"], environment=self.amb,
                                 requested_by=self.c["login"])
        self.assertTrue(self.queue.claim(self.conn, tid, self.c["scr"]["id"], self.amb, self.agent)[0])
        self.assertTrue(self.queue.finalize(self.conn, tid, self.agent, "SUCCESS", "EXIT_OK", 0))
        return tid

    def test_ciclo_disponivel_e_leitura_pela_web(self):
        tid = self._agent_ticket()
        self.assertIsNone(self.tickets.output_get(tid))
        self.assertFalse(self.repo.start(self.conn, tid, "outro-agente"), "posse do ticket")
        self.conn.rollback()
        self.assertTrue(self.repo.start(self.conn, tid, self.agent))
        self.conn.commit()
        zip_ = bytes(bytearray(range(256))) * 5000  # 1,28 MB: duas partes
        p1, p2 = zip_[:scheduler_output.PART_MAX], zip_[scheduler_output.PART_MAX:]
        self.assertEqual(self.repo.append_chunk(self.conn, tid, self.agent, 0, p1), "WRITTEN")
        self.conn.commit()
        # COMMIT sem resposta: a mesma parte de novo e reconhecida
        self.assertEqual(self.repo.append_chunk(self.conn, tid, self.agent, 0, p1), "ALREADY_WRITTEN")
        with self.assertRaises(OutputOffsetMismatch):
            self.repo.append_chunk(self.conn, tid, self.agent, 10, p2)
        self.conn.rollback()
        self.assertEqual(self.repo.append_chunk(self.conn, tid, self.agent, len(p1), p2), "WRITTEN")
        self.assertEqual(self.tickets.output_get(tid)["state"], "WRITING")
        with self.assertRaises(self.trc.RepoNotFound):
            self.tickets.output_read(tid, 0, 10)
        self.assertFalse(self.repo.complete(self.conn, tid, self.agent, 2, len(zip_) + 1), "tamanho conferido")
        self.assertTrue(self.repo.complete(self.conn, tid, self.agent, 2, len(zip_)))
        self.conn.commit()
        meta = self.tickets.output_get(tid)
        self.assertEqual((meta["state"], meta["file_count"], meta["size_bytes"], meta["agent_id"]),
                         ("AVAILABLE", 2, len(zip_), self.agent))
        self.assertEqual(meta["updated_by"], "SYSTEM:%s" % self.agent)
        self.assertNotIn("content", meta)
        read, off = b"", 0
        while True:
            part = self.tickets.output_read(tid, off, 300000)
            if not part:
                break
            read += part
            off += len(part)
        self.assertEqual(read, zip_)
        self.assertEqual(self.repo.append_chunk(self.conn, tid, self.agent, len(zip_), b"x"), "OWNERSHIP_LOST",
                         "fora de GRAVANDO nada e anexado")
        self.assertFalse(self.repo.start(self.conn, tid, self.agent), "situacao final nao reabre")
        self.conn.rollback()

    def test_combinacoes_de_driver(self):
        # O filho poe src/ no caminho (_CHILD)
        src = os.path.join(_testenv.APP_DIR, "src")
        part = bytes(bytearray(range(256))) * 1200
        results = {}
        for mode in ("thin", "thick", "cx_oracle"):
            tid = self._agent_ticket()
            p = subprocess.run([sys.executable, "-c", _CHILD, src, mode, str(tid), self.agent],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
                               cwd=_testenv.APP_DIR)
            rows = [x for x in p.stdout.decode("utf-8", "replace").splitlines() if x.startswith("{")]
            self.assertTrue(rows, "%s: %s" % (mode, p.stderr.decode("utf-8", "replace")[-500:]))
            output = json.loads(rows[-1])
            results[mode] = output
            if "indisponivel" in output:
                continue
            self.assertEqual((output["candidate"], output["r"]), (mode, [True, "WRITTEN", "ALREADY_WRITTEN", True]), mode)
            self.assertEqual(self.tickets.output_read(tid, 0, len(part)), part, mode)
        print("\n[saida] combinacoes de driver: %s" % json.dumps(results))
        self.assertNotIn("indisponivel", results["thin"], "Thin e o driver padrao do ambiente")

    def test_excedeu_falhou_e_startup_check(self):
        t1, t2, t3 = self._agent_ticket(), self._agent_ticket(), self._agent_ticket()
        self.assertTrue(self.repo.register_without_content(self.conn, t1, self.agent, "EXCEEDED", "FILES", 1001))
        self.assertTrue(self.repo.start(self.conn, t2, self.agent))
        self.assertTrue(self.repo.register_without_content(self.conn, t2, self.agent, "FAILED", "DEADLINE"))
        self.assertTrue(self.repo.start(self.conn, t3, self.agent))
        self.conn.commit()
        self.assertEqual(self.repo.fail_agent_writing(self.conn, self.agent), 1)
        self.conn.commit()
        for tid, expected in ((t1, ("EXCEEDED", "FILES", 1001)), (t2, ("FAILED", "DEADLINE", None)),
                              (t3, ("FAILED", "ERROR", None))):
            meta = self.tickets.output_get(tid)
            self.assertEqual((meta["state"], meta["reason"], meta["file_count"]), expected)
            with self.assertRaises(self.trc.RepoNotFound):
                self.tickets.output_read(tid, 0, 10)
        self.assertEqual(self.repo.output_state(self.conn, t1), ("EXCEEDED", self.agent))
        self.assertFalse(self.repo.register_without_content(self.conn, t1, self.agent, "FAILED", "ERROR"))
        self.conn.rollback()


if __name__ == "__main__":
    unittest.main()
