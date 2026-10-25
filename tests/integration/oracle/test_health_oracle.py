# -*- coding: utf-8 -*-
"""Testes do scripts/health.py e do repo_oracle/health.py (README §13; F9.1b; CR-007 R-18; CR-008 E3, R-15, R-16)

Parte que precisa do Oracle real (SSS_TEST_ORACLE=1), separada de tests.unit.cli.test_health (CR-022b1)."""
from tests.support import _testenv  # noqa: F401
import os
import re
import unittest
import health as saude_cli  # scripts/health.py (o repositorio e repo_oracle.health)
import sql_ident
import sss_config
from repo_oracle import health as saude_sql
from tests.unit.cli.test_health import _args  # noqa: F401


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestHealthOracle(unittest.TestCase):
    """As consultas do RepoHealth no Oracle real, so leitura, pela conta do owner (decisao 1a do F9.1)."""

    @classmethod
    def setUpClass(cls):
        from tests.support._oracle_test_support import prepare_disposable_schema
        import db_conn
        cls.cfg = prepare_disposable_schema("agent")
        secrets_value = sss_config.load_secrets(cls.cfg.secrets.secrets_file, cfg=cls.cfg, role="agent")
        cls.conn = db_conn.connect(cls.cfg, secrets_value, role="agent")
        cls.repo = saude_sql.RepoHealth.from_config(cls.cfg)

    @classmethod
    def tearDownClass(cls):
        cls.conn.rollback()
        cls.conn.close()

    def test_consultas_e_verificacao_completa(self):
        import db_conn
        now = db_conn.db_now(self.conn)
        self.assertEqual(self.repo.schema_version(self.conn), sql_ident.SCHEMA_VERSION)
        self.assertIsInstance(self.repo.agents(self.conn), list)
        self.assertIsInstance(self.repo.active_environments(self.conn), list)
        count, _old = self.repo.overdue_queue(self.conn, now)
        self.assertEqual(count, sum(int(r[2]) for r in self.repo.queue_by_pair(self.conn, now)))
        self.repo.running_without_pid(self.conn, now, 2)
        self.repo.last_purge(self.conn, now, 2)
        v = saude_cli.Check(self.cfg, self.conn, _args(), repo=self.repo)
        code = v.run()
        self.assertIn(code, (0, 1, 2))
        print("\n[F9.1b] saude no GFPR: %s" % v.output(code).splitlines()[0])

    def test_explain_sem_varredura_de_tickets_e_auditoria(self):
        # EXPLAIN PLAN nao aceita valores de bind no modo Thick (ORA-01036): os binds de data viram SYSDATE,
        # a mesma comparacao de data que os indices usam.
        for name in ("queue", "overdue_queue", "running_no_pid", "purge"):
            cur = self.conn.cursor()
            stmt = "SSS_F91B_%s" % name.upper()
            cur.execute("DELETE FROM plan_table WHERE statement_id = :s", {"s": stmt})
            sql = re.sub(r":(now|cutoff)\b", "SYSDATE", self.repo.sql(name))
            cur.execute("EXPLAIN PLAN SET STATEMENT_ID = '%s' FOR %s" % (stmt, sql))
            cur.execute("SELECT operation, options, object_name FROM plan_table WHERE statement_id = :s",
                        {"s": stmt})
            plan = cur.fetchall()
            cur.execute("DELETE FROM plan_table WHERE statement_id = :s", {"s": stmt})
            self.conn.commit()
            scans = [o for op, opt, o in plan if op == "TABLE ACCESS" and opt == "FULL"
                          and (o or "").upper() in ("TBSSS_TICKETS", "TBSSS_AUDIT")]
            self.assertEqual(scans, [], "%s: %s" % (name, plan))
            print("\n[F9.1b] EXPLAIN %s: %s" % (name, ", ".join("%s %s %s" % (op, opt or "", o or "")
                                                               for op, opt, o in plan)))


if __name__ == "__main__":
    unittest.main()
