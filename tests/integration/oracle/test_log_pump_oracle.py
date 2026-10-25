# -*- coding: utf-8 -*-
"""Testes do log_pump e do repo_oracle.scheduler_log (README §8.10; AGENTS §4.13; CR-007 R-25; CR-008 R-11)

Parte que precisa do Oracle real (SSS_TEST_ORACLE=1), separada de tests.unit.scheduler.test_log_pump (CR-022b1)."""
from tests.support import _testenv  # noqa: F401
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from sss.persistence import db_conn
from sss.scheduler import log_pump
from sss.scheduler.log_pump import Pump
from sss.persistence.oracle.scheduler_log import (WRITTEN, ALREADY_WRITTEN, OWNERSHIP_LOST, LogOffsetMismatch,
                                                  RepoSchedulerLog)
from tests.unit.scheduler.test_log_pump import MB, _CHILD  # noqa: F401


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestSchedulerLogOracle(unittest.TestCase):
    """WRITEAPPEND real num ticket proprio (modo compartilhado ou descartavel), limpo no tearDown."""

    AGENT = "tst-pump-01"

    @classmethod
    def setUpClass(cls):
        from tests.unit.persistence import test_repo_contract as trc
        cls.trc = trc
        cls.contrato = trc._OracleContract
        cls.contrato.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.contrato.tearDownClass.__func__(cls)

    def setUp(self):
        self.contrato.setUp(self)
        self._fixtures = self.trc._Fixtures(self.obter_repo)
        c = self._fixtures.scenario()
        self.ticket_id = self._fixtures.ticket(actor="teste", script_id=c["scr"]["id"], environment=c["amb1"]["name"],
                                            requested_by=c["login"])
        self.catalog = self.obter_repo("catalog")
        self.repo = RepoSchedulerLog(self.catalog._owner, self.catalog._prefixo)
        self.tck = self.catalog.qualify_table("tickets")
        conn = self.catalog._obter_conexao()
        try:
            self.unit = self.repo.supplementary_unit(conn)
        finally:
            conn.close()
        # Estado que o claim (F8.3) deixa: RUNNING deste agente, CLOB vazio e offset 0.
        self._sql("UPDATE " + self.tck + " SET status = 'RUNNING', agent_id = :a, started_at = SYSDATE, "
                  "heartbeat_at = SYSDATE, log_output = EMPTY_CLOB(), log_offset_chars = 0 WHERE id = :id",
                  a=self.AGENT, id=self.ticket_id)

    def tearDown(self):
        self.contrato.tearDown(self)

    def obter_repo(self, name):
        return self.contrato.obter_repo(self, name)

    def _clean_fixtures(self):
        return self.contrato._clean_fixtures(self)

    def _sql(self, sql, **binds):
        conn = self.catalog._obter_conexao()
        try:
            cur = conn.cursor()
            cur.execute(sql, **binds)
            conn.commit()
        finally:
            conn.close()

    def _as_db(self, text):
        """O texto como o charset do banco o guarda (caractere fora dele vira o de substituicao)."""
        conn = self.catalog._obter_conexao()
        try:
            cur = conn.cursor()
            db_conn.set_input_types(cur, x=db_conn.TIPO_CLOB)
            cur.execute("SELECT TO_CLOB(:x) FROM DUAL", x=text)
            return cur.fetchone()[0].read()
        finally:
            conn.close()

    def _state(self):
        conn = self.catalog._obter_conexao()
        try:
            cur = conn.cursor()
            cur.execute("SELECT log_output, log_offset_chars, log_truncated FROM " + self.tck + " WHERE id = :id",
                        id=self.ticket_id)
            lob, off, trunc = cur.fetchone()
            return (lob.read() if lob is not None and lob.size() else ""), int(off), trunc
        finally:
            conn.close()

    def test_append_idempotente_rollback_e_divergencia(self):
        conn = self.catalog._obter_conexao()
        try:
            chunk = "ação \U0001F600 linha 1\n"
            units = log_pump.clob_units(chunk, self.unit)
            saved = self._as_db(chunk)
            # Rollback antes do primeiro COMMIT: a nova tentativa grava (WRITTEN).
            self.assertEqual(self.repo.append_chunk(conn, self.ticket_id, self.AGENT, 0, chunk), WRITTEN)
            conn.rollback()
            self.assertEqual(self.repo.append_chunk(conn, self.ticket_id, self.AGENT, 0, chunk), WRITTEN)
            conn.commit()
            # Mesma operacao depois do COMMIT: ALREADY_WRITTEN, sem segundo WRITEAPPEND.
            self.assertEqual(self.repo.append_chunk(conn, self.ticket_id, self.AGENT, 0, chunk), ALREADY_WRITTEN)
            conn.commit()
            self.assertEqual(self._state(), (saved, units, "N"))
            # Offset divergente e conteudo diferente: LogOffsetMismatch sem alterar o CLOB.
            for offset, other in ((units + 5, "x"), (0, "ação \U0001F600 linha 2\n"), (1, chunk)):
                with self.assertRaises(LogOffsetMismatch):
                    self.repo.append_chunk(conn, self.ticket_id, self.AGENT, offset, other)
                conn.rollback()
            self.assertEqual(self._state(), (saved, units, "N"))
            # Outro agente: OWNERSHIP_LOST.
            self.assertEqual(self.repo.append_chunk(conn, self.ticket_id, "outro-agente", units, "z"), OWNERSHIP_LOST)
            conn.rollback()
            self.assertTrue(self.repo.mark_truncated(conn, self.ticket_id, self.AGENT))
            conn.commit()
            self.assertEqual(self._state()[2], "Y")
        finally:
            conn.close()

    def test_bomba_completa_mascarada_uma_vez(self):
        root = tempfile.mkdtemp(prefix="sss_pump_ora_")
        self.addCleanup(shutil.rmtree, root, True)
        path = os.path.join(root, "ticket.log")
        rows = "".join("linha %05d ação \U0001F600 senha=SegredoDoTicket\n" % i for i in range(700))
        with open(path, "wb") as f:
            f.write(rows.encode("utf-8"))
        m = log_pump.ticket_masker(["SegredoDoTicket"])
        b = Pump(path, self.ticket_id, m, 5 * MB, 50 * MB, supplementary_unit=self.unit)
        conn = self.catalog._obter_conexao()
        try:
            self.assertEqual(log_pump.final_flush(b, conn, self.repo, self.AGENT), log_pump.OK)
        finally:
            conn.close()
        expected = rows.replace("SegredoDoTicket", "****")
        text, offset, _trunc = self._state()
        self.assertEqual(text, self._as_db(expected))
        self.assertEqual(text.count("****"), 700)
        self.assertNotIn("SegredoDoTicket", text)
        self.assertEqual(offset, log_pump.clob_units(expected, self.unit))
        self.assertGreater(len(expected), 8000, "mais de um bloco")

    def test_combinacoes_de_driver(self):
        # O filho poe modules/ e src/ (irmao de modules/) no caminho (_CHILD)
        modules = os.path.join(_testenv.APP_DIR, "modules")
        offset = 0
        results = {}
        for mode in ("thin", "thick", "cx_oracle"):
            chunk = "driver %s ação \U0001F600\n" % mode
            p = subprocess.run([sys.executable, "-c", _CHILD, modules, mode, str(self.ticket_id), self.AGENT,
                                str(offset), chunk], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=180, cwd=os.path.dirname(modules),
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            output_txt = p.stdout.decode("utf-8", "replace")
            rows = [x for x in output_txt.splitlines() if x.startswith("{")]
            self.assertTrue(rows, "%s: %s" % (mode, p.stderr.decode("utf-8", "replace")[-500:]))
            output = json.loads(rows[-1])
            results[mode] = output
            if "indisponivel" in output:
                continue
            self.assertEqual((output["candidate"], output["r"]), (mode, [WRITTEN, ALREADY_WRITTEN]), mode)
            offset += log_pump.clob_units(chunk, self.unit)
        print("\n[log_pump] combinacoes de driver: %s" % json.dumps(results, ensure_ascii=False))
        text, off, _trunc = self._state()
        expected = "".join("driver %s ação \U0001F600\n" % m for m in ("thin", "thick", "cx_oracle")
                           if "indisponivel" not in results[m])
        self.assertEqual((text, off), (self._as_db(expected), offset), "cada bloco uma unica vez")
        self.assertNotIn("indisponivel", results["thin"], "Thin e o driver padrao do ambiente")


if __name__ == "__main__":
    unittest.main()
