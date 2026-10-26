# -*- coding: utf-8 -*-
"""Contrato do repositorio da pasta de entrada (CR-020b; README §10 tabelas 19 a 21), contra o FAKE (sempre) e o

Parte que precisa do Oracle real (SSS_TEST_ORACLE=1), separada de tests.unit.persistence.test_repo_inputs (CR-022b1)."""
from tests.support import _testenv  # noqa: F401
import os
import unittest
from sss.persistence import repo_factory
from tests.unit.persistence.test_repo_contract import _OracleContract
from tests.unit.persistence.test_repo_inputs import BaseInputsContract  # noqa: F401


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestRepoInputsOracle(_OracleContract, unittest.TestCase, BaseInputsContract):
    """Mesma bateria no Oracle do config.ini; agentes registrados pelo repositorio do daemon."""

    def setUp(self):
        _OracleContract.setUp(self)
        self._agents = []
        self.setUp_scenario()
        self._fixtures = self.m

    def obter_repo(self, name):
        return repo_factory.get(name)

    def agent(self, code, environments, stale=False):
        from sss.persistence.oracle.scheduler_queue import RepoSchedulerQueue
        catalog = self.obter_repo("catalog")
        queue = RepoSchedulerQueue(catalog._owner, catalog._prefixo)
        conn = catalog._obter_conexao()
        try:
            queue.register_agent(conn, {"code": code, "hostname": "tst-host", "pid": 1, "version": "t",
                                        "environments": environments, "platform": "LINUX",
                                        "critical_config": None, "node_offline_timeout_s": 60},
                                 process_exists=lambda pid: False)
            if stale:
                cur = conn.cursor()
                cur.execute("UPDATE " + catalog.qualify_table("agents") + " SET heartbeat_at = SYSDATE - 1 "
                            "WHERE code = :code", {"code": code})
                cur.close()
                conn.commit()
        finally:
            conn.close()
        self._agents.append(code)

    def tearDown(self):
        catalog = self.obter_repo("catalog")
        conn = catalog._obter_conexao()
        try:
            cur = conn.cursor()
            envs = ["TST_%s_%s" % (self.m.suf, x) for x in "ABC"]
            for env in envs:
                cur.execute("DELETE FROM " + catalog.qualify_table("input_listing") + " WHERE environment = :e",
                            {"e": env})
                cur.execute("DELETE FROM " + catalog.qualify_table("input_upload") + " WHERE environment = :e",
                            {"e": env})
            for code in self._agents:
                cur.execute("DELETE FROM " + catalog.qualify_table("agents") + " WHERE code = :c", {"c": code})
            cur.close()
            conn.commit()
        finally:
            conn.close()
        _OracleContract.tearDown(self)


if __name__ == "__main__":
    unittest.main()
