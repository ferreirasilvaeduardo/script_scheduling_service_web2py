# -*- coding: utf-8 -*-
"""Testes do scripts/purge.py e do repo_oracle/purge.py (README §11.3; F9.1a; CR-005; CR-007 R-21, R-22, R-32;

Parte que precisa do Oracle real (SSS_TEST_ORACLE=1), separada de tests.unit.cli.test_purge (CR-022b1)."""
from tests.support import _testenv  # noqa: F401
import csv
import io
import logging
import os
import shutil
import tempfile
import types
import unittest
import purge as purge_cli  # scripts/purge.py (o repositorio e repo_oracle.purge)
from repo_oracle.purge import RepoPurge


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestPurgeOracle(unittest.TestCase):
    """Purge real contra o Oracle (decisao 1a): conta do owner, so quando nada fora da fixture e elegivel."""

    DAYS = 30  # retencao dos tickets no teste; a auditoria usa o minimo, 365

    @classmethod
    def setUpClass(cls):
        from tests.unit.persistence import test_repo_contract as trc
        cls.trc = trc
        cls.contrato = trc._OracleContract
        cls.contrato.setUpClass.__func__(cls)
        from tests.support._oracle_test_support import prepare_disposable_schema
        prepare_disposable_schema("agent")

    @classmethod
    def tearDownClass(cls):
        cls.contrato.tearDownClass.__func__(cls)

    def obter_repo(self, name):
        return self.contrato.obter_repo(self, name)

    def setUp(self):
        self.contrato.setUp(self)
        self._fixtures = self.trc._Fixtures(self.obter_repo)
        self.cat = self.obter_repo("catalog")
        self.conn = self.cat._obter_conexao()
        self.addCleanup(self.conn.close)  # LIFO: fecha depois da limpeza
        self.addCleanup(self._clean)
        self.tck, self.aud = self.cat.qualify_table("tickets"), self.cat.qualify_table("audit")
        self.aud_fixture = []
        self.tck_fixture = []  # todos os tickets da fixture, inclusive o que o purge apaga (auditoria deles)
        self.purges = []

    def _clean(self):
        cur = self.conn.cursor()
        for aid in self.aud_fixture + self.purges:
            cur.execute("DELETE FROM " + self.aud + " WHERE id = :id", {"id": aid})
        # Auditoria dos tickets da fixture, inclusive o que o purge apagou (no compartilhado nao sobra nada).
        for tid in self.tck_fixture:
            cur.execute("DELETE FROM " + self.aud + " WHERE entity = 'tbsss_tickets' AND entity_id = :id", {"id": tid})
        self.conn.commit()
        self.contrato._clean_fixtures(self)

    def _one(self, sql, **binds):
        cur = self.conn.cursor()
        cur.execute(sql, binds)
        return cur.fetchone()[0]

    def _executar(self, sql, **binds):
        cur = self.conn.cursor()
        cur.execute(sql, binds)
        self.conn.commit()

    def test_purge_real_so_dos_tickets_e_auditoria_da_fixture(self):
        m = self._fixtures
        env, scr = m.environment("P"), m.script("p")
        login = m.usuario(m.profile("P")["id"], "u")["login"]
        base = {"script_id": scr["id"], "environment": env["name"], "requested_by": login, "priority": 2,
                "status": "PENDING", "submitted_params": "{}"}
        old_ok, old_pend, new_ok = (m.ticket(actor=login, **base) for _ in range(3))
        self.tck_fixture = [old_ok, old_pend, new_ok]
        for tid, status, days in ((old_ok, "SUCCESS", 40), (old_pend, "PENDING", 40), (new_ok, "SUCCESS", 5)):
            self._executar("UPDATE " + self.tck + " SET status = :s, created_at = SYSDATE - :d WHERE id = :id",
                           s=status, d=days, id=tid)
        aid = self._one("SELECT " + RepoPurge.from_config(self.oracle_cfg)._seq_aud + ".NEXTVAL FROM DUAL")
        self._executar("INSERT INTO " + self.aud + " (id, actor, action, entity, detail, created_at)"
                       " VALUES (:id, :a, 'LOGIN', 'tbsss_users', 'fixture F9.1a', SYSDATE - 400)", id=aid, a=m.actor)
        self.aud_fixture.append(aid)
        # Guarda (decisao 1a): nada fora da fixture pode ser elegivel no esquema compartilhado.
        foreign_tck = self._one("SELECT COUNT(*) FROM " + self.tck + " WHERE created_at < SYSDATE - :d"
                               " AND status IN ('SUCCESS','FAILED','CANCELLED') AND id <> :id", d=self.DAYS, id=old_ok)
        foreign_aud = self._one("SELECT COUNT(*) FROM " + self.aud + " WHERE created_at < SYSDATE - 365 AND id <> :id",
                               id=aid)
        if foreign_tck or foreign_aud:
            self.skipTest("%d tickets e %d linhas de auditoria fora da fixture seriam elegiveis"
                          % (foreign_tck, foreign_aud))
        cfg = self.oracle_cfg
        owner = "tst-f91a-%s" % m.suf
        cfg_purge = types.SimpleNamespace(
            agent=types.SimpleNamespace(agent_id=owner), oracle=cfg.oracle,
            retention=types.SimpleNamespace(ticket_retention_days=self.DAYS, audit_retention_days=365,
                                           purge_batch_size=1))
        mark = self._one("SELECT NVL(MAX(id), 0) FROM " + self.aud)
        logger = logging.getLogger("sss_test_purge_oracle")
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        # Dry-run primeiro: conta a fixture, nada muda.
        p = purge_cli.Purge(cfg_purge, self.conn, logger=logger)
        self.assertEqual(p.run(("tickets", "audit"), dry_run=True), 0)
        self.assertEqual(p.summary, ["tickets: 1 linhas elegiveis (estimativa)",
                                    "audit: 1 linhas elegiveis (estimativa)"])
        dir_value = tempfile.mkdtemp(prefix="sss_test_purge_csv_")
        self.addCleanup(shutil.rmtree, dir_value, True)
        p = purge_cli.Purge(cfg_purge, self.conn, logger=logger)
        code = p.run(("tickets", "audit"), export=dir_value)
        self.purges = [r[0] for r in self.conn.cursor().execute(
            "SELECT id FROM " + self.aud + " WHERE id > :m AND actor = 'SYSTEM:purge'", {"m": mark}).fetchall()]
        if p.summary and "pulado" in p.summary[0]:
            self.skipTest("concessao com outro no: %s" % p.summary)
        self.assertEqual(code, 0)
        remaining = dict(self.conn.cursor().execute(
            "SELECT id, status FROM " + self.tck + " WHERE id IN (:a, :b, :c)",
            {"a": old_ok, "b": old_pend, "c": new_ok}).fetchall())
        self.assertEqual(remaining, {old_pend: "PENDING", new_ok: "SUCCESS"})
        self.assertEqual(self._one("SELECT COUNT(*) FROM " + self.aud + " WHERE id = :id", id=aid), 0)
        with io.open(os.path.join(dir_value, os.listdir(dir_value)[0]), encoding="utf-8-sig", newline="") as f:
            self.assertEqual([l[0] for l in csv.reader(f, delimiter=";")][1:], [str(aid)], "exportada antes de sair")
        rows = self.conn.cursor().execute(
            "SELECT entity, detail, entity_id FROM " + self.aud + " WHERE id > :m AND actor = 'SYSTEM:purge'"
            " ORDER BY id", {"m": mark}).fetchall()
        self.assertEqual(rows, [("tbsss_tickets", "1 linhas", None), ("tbsss_audit", "1 linhas", None)])
        ctl = self.conn.cursor().execute("SELECT purge_owner, purge_lease_until FROM "
                                         + self.cat.qualify_table("control") + " WHERE id = 1").fetchone()
        self.assertEqual(tuple(ctl), (None, None), "concessao liberada (CR-008, R-27)")
        self._fixtures.created["tickets"].remove(old_ok)
        self.aud_fixture.remove(aid)
        print("\n[F9.1a] purge real: %s" % "; ".join(p.summary))


if __name__ == "__main__":
    unittest.main()
