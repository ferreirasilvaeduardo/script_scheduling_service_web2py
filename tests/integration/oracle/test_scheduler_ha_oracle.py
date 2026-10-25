# -*- coding: utf-8 -*-
"""Agente em alta disponibilidade (F8.4): desdobro dos agendamentos (F8.4b; README §7.4 e §7.5)

Parte que precisa do Oracle real (SSS_TEST_ORACLE=1), separada de tests.unit.scheduler.test_scheduler_ha (CR-022b1)."""
from tests.support import _testenv  # noqa: F401
import datetime
import json
import unittest
import schedule_expansion
import os  # noqa: E402
from tests.unit.scheduler.test_scheduler_ha import _Cfg  # noqa: F401


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestExpansionOracle(unittest.TestCase):
    """Desdobro real (repositorios Oracle) com massa propria: ticket da regra vencida e pausa INVALID_PARAM."""

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
        from repo_oracle.scheduler_schedules import RepoSchedulerSchedules
        from repo_oracle.scheduler_queue import RepoSchedulerQueue
        self.contrato.setUp(self)
        self._fixtures = self.trc._Fixtures(self.obter_repo)
        self.c = self._fixtures.scenario()
        cat, self.rbac = self.obter_repo("catalog"), self.obter_repo("rbac")
        self.cat = cat
        features = [f["id"] for f in self.rbac.features_list() if f["code"] == "EXEC_SCRIPT"]
        self.rbac.matrix_save(self.c["profile"]["id"], features, [self.c["amb1"]["id"]], [self.c["scr"]["id"]],
                                actor=self._fixtures.actor)
        self.agent = "tst-ha-%s" % self._fixtures.suf
        self.des = schedule_expansion.Expansion(RepoSchedulerSchedules(cat._owner, cat._prefixo),
                                     RepoSchedulerQueue(cat._owner, cat._prefixo), self.agent, _Cfg(),
                                     lambda: 0.0)
        self.conn = cat._obter_conexao()
        self.addCleanup(self.conn.close)

    def tearDown(self):
        self.conn.rollback()
        cur = self.conn.cursor()
        sch, aud, tck = (self.cat.qualify_table(t) for t in ("schedules", "audit", "tickets"))
        for rid in self._fixtures.created["schedules"]:
            cur.execute("SELECT id FROM " + tck + " WHERE schedule_id = :id", id=rid)
            for (tid,) in cur.fetchall():
                self._fixtures.note("tickets", tid)
            cur.execute("DELETE FROM " + aud + " WHERE entity = 'tbsss_schedules' AND entity_id = :id", id=rid)
        self.conn.commit()
        self.rbac.matrix_save(self.c["profile"]["id"], [], [], [], actor=self._fixtures.actor)
        self.contrato.tearDown(self)

    def _rule(self, answers):
        next_value = datetime.datetime.now().replace(second=0, microsecond=0) - datetime.timedelta(minutes=2)
        return self._fixtures.schedule(self.c["scr"]["id"], self.c["amb1"]["name"], self.c["u1"]["id"],
                                       recurrence_type="DAILY", run_time=next_value.strftime("%H:%M"),
                                       start_date=next_value - datetime.timedelta(days=1), next_run_at=next_value,
                                       params_json=json.dumps(answers))

    def test_ticket_real_e_pausa_param_invalido(self):
        prm_a = self.c["prm_a"]["code"]
        ok = self._rule({prm_a: "valor-a"})
        bad = self._rule({})
        with self.assertLogs("sss_scheduler", "INFO"):
            self.assertEqual(self.des.process(self.conn, ok["id"]), "TICKET")
            self.assertEqual(self.des.process(self.conn, bad["id"]), "PAUSED")
        sch = self.obter_repo("schedules")
        r_ok, r_bad = sch.get(ok["id"]), sch.get(bad["id"])
        self.assertGreater(r_ok["next_run_at"], ok["next_run_at"])
        t = self.obter_repo("tickets").get(r_ok["last_ticket_id"])
        self.assertEqual((t["schedule_id"], t["requested_by"], t["created_by"], t["scheduled_at"], t["status"]),
                         (ok["id"], self.c["login"], "SYSTEM:%s" % self.agent, ok["next_run_at"], "PENDING"))
        snap = json.loads(t["submitted_params"])
        self.assertEqual((snap["version"], snap["path_file"]), (5, self.c["scr"]["path_file"]))
        self.assertEqual([x["answer_value"] for x in self.obter_repo("tickets").answers(t["id"])], ["valor-a"])
        self.assertEqual((r_bad["active"], r_bad["pause_reason"], r_bad["updated_by"]),
                         ("N", "INVALID_PARAM", "SYSTEM:%s" % self.agent))
        # A regra ja avancada nao e mais vencida; a pausada tambem nao.
        due = [rid for rid, _p in self.des.agenda.due_rules(self.conn, 1000)]
        self.conn.rollback()
        self.assertNotIn(ok["id"], due)
        self.assertNotIn(bad["id"], due)


if __name__ == "__main__":
    unittest.main()
