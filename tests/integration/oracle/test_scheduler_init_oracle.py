# -*- coding: utf-8 -*-
"""Testes da inicializacao do agente (F8.3b; README §8.12 passos 1-9; CR-007 R-01, R-11, R-17, R-23; CR-008 R-01,

Parte que precisa do Oracle real (SSS_TEST_ORACLE=1), separada de tests.unit.scheduler.test_scheduler_init (CR-022b1)."""
from tests.support import _testenv  # noqa: F401
import os
import time
import unittest
import scheduler_loop as sl
from sss.config import sss_config
from tests.unit.scheduler.test_scheduler_init import _Base  # noqa: F401


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestStartupOracle(_Base):
    """Subida real no owner do config.ini, com agent_id de teste e pastas temporarias; registro removido no fim."""

    def setUp(self):
        _Base.setUp(self)
        from tests.support._oracle_test_support import prepare_disposable_schema
        self.cfg_real = prepare_disposable_schema("agent")
        self.code = "tst-f83b-%d" % (int(time.time() * 1000) % 100000000)
        self.addCleanup(self._clean_registration)

    def _clean_registration(self):
        from sss.persistence import db_conn
        from sss.core import sql_ident
        seg = sss_config.load_secrets(self.cfg_real.secrets.secrets_file, cfg=self.cfg_real, role="agent")
        conn = db_conn.connect(self.cfg_real, seg, "agent")
        try:
            o, p = self.cfg_real.oracle.owner.strip(), self.cfg_real.oracle.table_prefix.strip()
            agt = sql_ident.table(o, p, "agents")
            aud = sql_ident.table(o, p, "audit")
            cur = conn.cursor()
            cur.execute("SELECT id FROM " + agt + " WHERE code = :c", c=self.code)
            for (aid,) in cur.fetchall():
                cur.execute("DELETE FROM " + aud + " WHERE entity = 'tbsss_agents' AND entity_id = :id", id=aid)
                cur.execute("DELETE FROM " + agt + " WHERE id = :id", id=aid)
            conn.commit()
        finally:
            conn.close()

    def test_subida_real_e_parada(self):
        from sss.persistence import db_conn
        from sss.persistence.oracle.scheduler_queue import RepoSchedulerQueue
        cfg = self.cfg_real
        seg = sss_config.load_secrets(cfg.secrets.secrets_file, cfg=cfg, role="agent")
        conn = db_conn.connect(cfg, seg, "agent")
        try:
            from sss.persistence import ddl_builder
            active, _ = RepoSchedulerQueue.from_config(cfg).active_environments(
                conn, [a[0] for a in ddl_builder.DEFAULT_ENVIRONMENTS])
        finally:
            conn.close()
        self.assertTrue(active, "o seed precisa de um ambiente ativo")
        agent = cfg.agent._replace(agent_id=self.code, environments=tuple(active[:1]), work_dir=self.work,
                                    interpreters=(("SH", "/bin/sh"),))
        cfg = cfg._replace(agent=agent, logging=cfg.logging._replace(log_dir=self.logs))
        ag = sl.Agent(cfg=cfg, secrets=seg, hostname="host-tst", pid=os.getpid())
        self.agents.append(ag)
        with self.assertLogs("sss_scheduler", "INFO"):
            ag.initialize()
        self.assertIsInstance(ag.agent_db_id, int)
        self.assertIn(ag.supplementary_unit, (1, 2))
        self.assertEqual(ag.active_environments, list(active[:1]))
        # Segunda subida do mesmo agent_id, de outro host, enquanto o primeiro esta ativo: recusada.
        other = sl.Agent(cfg=cfg._replace(agent=agent._replace(work_dir=self.root)), secrets=seg,
                          hostname="outro-host", pid=os.getpid())
        self.agents.append(other)
        os.makedirs(os.path.join(self.root, "logs2"), exist_ok=True)
        self.failure(sl.EXIT_REGISTRATION, other)
        self.assertTrue(ag.repo.stop_agent(ag.connection.get_connection(), self.code, "host-tst", os.getpid(),
                                                "TERMINATE"))


if __name__ == "__main__":
    unittest.main()
