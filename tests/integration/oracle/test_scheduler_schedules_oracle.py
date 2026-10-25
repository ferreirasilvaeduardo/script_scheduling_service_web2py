# -*- coding: utf-8 -*-
"""Testes do repo_oracle.scheduler_schedules e das operacoes de no offline e fencing do scheduler_queue (F8.4a;

Parte que precisa do Oracle real (SSS_TEST_ORACLE=1), separada de tests.unit.persistence.test_scheduler_schedules (CR-022b1)."""
from tests.support import _testenv  # noqa: F401
import datetime
import os
import unittest
from sss.persistence.oracle.scheduler_schedules import DuplicateOccurrence, RepoSchedulerSchedules
from sss.persistence.oracle.scheduler_queue import RepoSchedulerQueue


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestAgendaOracle(unittest.TestCase):
    """Operacoes reais com massa propria (README §2.5)."""

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
        self._fixtures = self.trc._Fixtures(self.obter_repo)
        self.c = self._fixtures.scenario()
        cat = self.obter_repo("catalog")
        self.cat = cat
        self.repo = RepoSchedulerSchedules(cat._owner, cat._prefixo)
        self.queue = RepoSchedulerQueue(cat._owner, cat._prefixo)
        self.conn = cat._obter_conexao()
        self.addCleanup(self.conn.close)
        self.agent = "tst-agd-%s" % self._fixtures.suf
        self.actor = "SYSTEM:%s" % self.agent

    def tearDown(self):
        self.conn.rollback()
        cur = self.conn.cursor()
        aud = self.cat.qualify_table("audit")
        for rid in self._fixtures.created["schedules"]:
            cur.execute("DELETE FROM " + aud + " WHERE entity = 'tbsss_schedules' AND entity_id = :id", id=rid)
        self.conn.commit()
        self.contrato.tearDown(self)

    def _rule(self, minutes_ago=10, **extra):
        next_value = datetime.datetime.now().replace(second=0, microsecond=0) - datetime.timedelta(minutes=minutes_ago)
        return self._fixtures.schedule(self.c["scr"]["id"], self.c["amb1"]["name"], self.c["u1"]["id"],
                                       next_run_at=next_value, **extra)

    def _ticket(self, rule, scheduled):
        return {"requested_by": self.c["login"], "priority": 2, "submitted_params": "{\"versao\": 4}",
                "scheduled_at": scheduled}

    def _linha(self, rid):
        return self.repo.load_rule(self.conn, rid)

    def test_microssegundos_nao_travam_a_reserva(self):
        """Teste obrigatorio (README §7.5): antiga/nova com microssegundos nao resultam em rowcount 0."""
        rule = self._rule()
        read = self._linha(rule["id"])
        old = read["next_run_at"].replace(microsecond=654321)
        new = (read["next_run_at"] + datetime.timedelta(days=1)).replace(microsecond=123456)
        tid = self.repo.next_ticket_id(self.conn)
        self.assertIn((rule["id"], read["next_run_at"]), self.repo.due_rules(self.conn, 1000))
        self.assertTrue(self.repo.lock_rule(self.conn, rule["id"]))
        self.assertTrue(self.repo.reserve_and_create_ticket(self.conn, read, old, new, tid,
                                                          self._ticket(read, old), [], self.agent))
        self.conn.commit()
        self._fixtures.note("tickets", tid)
        after = self._linha(rule["id"])
        self.assertEqual((after["next_run_at"], after["last_ticket_id"]), (new.replace(microsecond=0), tid))
        self.assertIsNone(after["updated_at"], "reserva sem updated_* (CR-006)")
        t = self.obter_repo("tickets").get(tid)
        self.assertEqual((t["schedule_id"], t["created_by"], t["scheduled_at"], t["source_ip"]),
                         (rule["id"], self.actor, old.replace(microsecond=0), None))
        # A mesma ocorrencia de novo: ix_tck_ocor recusa (CR-008, R-31).
        tid2 = self.repo.next_ticket_id(self.conn)
        with self.assertRaises(DuplicateOccurrence):
            self.repo._inserir_ticket(self.conn, read, tid2, self._ticket(read, old), [], self.actor)
        self.conn.rollback()

    def test_unica_concluida_mantem_a_data(self):
        rule = self._rule(recurrence_type="ONCE", run_time=None)
        read = self._linha(rule["id"])
        tid = self.repo.next_ticket_id(self.conn)
        self.assertTrue(self.repo.lock_rule(self.conn, rule["id"]))
        self.assertTrue(self.repo.complete_with_ticket(self.conn, read, read["next_run_at"], tid,
                                                      self._ticket(read, read["next_run_at"]), [], self.agent))
        self.conn.commit()
        self._fixtures.note("tickets", tid)
        after = self._linha(rule["id"])
        self.assertEqual((after["active"], after["pause_reason"], after["next_run_at"], after["last_ticket_id"]),
                         ("N", "COMPLETED", read["next_run_at"], tid))
        self.assertEqual(after["updated_by"], self.actor)
        self.assertFalse(self.repo.pause(self.conn, rule["id"], read["next_run_at"], "NO_PERMISSION", None,
                                          self.agent), "pausa sobre regra concluida: rowcount 0")
        self.conn.rollback()

    def test_pausa_avanco_cron_erro_e_erro_interno(self):
        r1, r2, r3, r4 = self._rule(), self._rule(), self._rule(), self._rule()
        l1, l2, l3 = self._linha(r1["id"]), self._linha(r2["id"]), self._linha(r3["id"])
        new = l2["next_run_at"] + datetime.timedelta(days=1)
        self.assertTrue(self.repo.pause(self.conn, r1["id"], l1["next_run_at"], "INVALID_PARAM",
                                         "data_ref: formato", self.agent))
        self.assertTrue(self.repo.advance_without_ticket(self.conn, r2["id"], l2["next_run_at"], new))
        self.assertTrue(self.repo.pause_cron_error(self.conn, l3, l3["next_run_at"], None, None, [], "horizonte",
                                                   self.agent))
        self.assertTrue(self.repo.pause_internal_error(self.conn, r4["id"], "ValueError", self.agent))
        self.conn.commit()
        d1, d2, d3, d4 = (self._linha(r["id"]) for r in (r1, r2, r3, r4))
        self.assertEqual((d1["active"], d1["pause_reason"], d1["updated_by"]), ("N", "INVALID_PARAM", self.actor))
        self.assertEqual((d2["active"], d2["next_run_at"], d2["updated_at"], d2["last_ticket_id"]),
                         ("Y", new, None, l2["last_ticket_id"]))
        self.assertEqual((d3["pause_reason"], d3["next_run_at"]), ("INVALID_CRON", l3["next_run_at"]))
        self.assertEqual(d4["pause_reason"], "INTERNAL_ERROR")
        cur = self.conn.cursor()
        cur.execute("SELECT detail FROM " + self.cat.qualify_table("audit") + " WHERE action = 'SCHEDULE_PAUSE'"
                    " AND entity_id = :id", id=r1["id"])
        self.assertEqual([x[0] for x in cur.fetchall()], ["pause_reason: INVALID_PARAM; data_ref: formato"])

    def test_node_offline_e_fenced(self):
        other, my = "tst-agd-%s-o" % self._fixtures.suf, self.agent
        t_other, t_my = (self._fixtures.ticket(actor="teste", script_id=self.c["scr"]["id"], environment=self.c["amb1"]["name"],
                                             requested_by=self.c["login"]) for _i in range(2))
        cur = self.conn.cursor()
        tck = self.cat.qualify_table("tickets")
        for tid, ag in ((t_other, other), (t_my, my)):
            cur.execute("UPDATE " + tck + " SET status = 'RUNNING', agent_id = :a, heartbeat_at = SYSDATE - 1"
                        " WHERE id = :id", a=ag, id=tid)
        self.conn.commit()
        self.assertIsNone(self.queue.mark_node_offline(self.conn, my, 180, lambda now: True), "salto: nada")
        marked = self.queue.mark_node_offline(self.conn, my, 180, lambda now: False)
        self.assertIn(t_other, marked)
        self.assertNotIn(t_my, marked, "nunca os proprios")
        t = self.obter_repo("tickets").get(t_other)
        self.assertEqual((t["status"], t["status_reason"], t["return_code"], t["updated_by"]),
                         ("FAILED", "NODE_OFFLINE", -2, "SYSTEM:%s" % my))
        self.assertTrue(self.queue.finalize_fenced(self.conn, t_my, my))
        self.assertEqual(self.obter_repo("tickets").get(t_my)["status_reason"], "FENCED")
        self.assertFalse(self.queue.finalize_fenced(self.conn, t_other, other), "ja NODE_OFFLINE")


if __name__ == "__main__":
    unittest.main()
