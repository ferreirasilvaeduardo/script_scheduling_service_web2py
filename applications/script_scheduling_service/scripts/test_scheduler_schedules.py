# -*- coding: utf-8 -*-
"""Testes do repo_oracle.scheduler_schedules e das operacoes de no offline e fencing do scheduler_queue (F8.4a;
README §7.5, §8.8, §8.9; CR-006; CR-007 R-05, R-08, R-12, R-19, R-27; CR-008 R-03, R-10, R-19, R-31).

Sem banco: conexao roteirizada do test_scheduler_queue (SQL literal, binds de data sem microssegundos e com
TIPO_DATE, nenhuma operacao do agenda faz COMMIT/ROLLBACK). Com SSS_TEST_ORACLE=1: as operacoes reais no
owner do instance/config.ini com massa propria (inclusive o teste obrigatorio de microssegundos).
"""
import _testenv  # noqa: F401

import datetime
import os
import unittest
from unittest import mock

import db_conn
from repo_oracle import scheduler_schedules
from repo_oracle.scheduler_schedules import DuplicateOccurrence, RepoSchedulerSchedules
from repo_oracle.scheduler_queue import RepoSchedulerQueue
from test_scheduler_queue import _Conn, _Error

AGENT = "srv-01"
ACTOR = "SYSTEM:srv-01"
OLD = datetime.datetime(2026, 10, 20, 3, 0, 0)
NEW = datetime.datetime(2026, 10, 21, 3, 0, 0, 123456)
RULE = {"id": 9, "script_id": 3, "environment": "PRD"}
TICKET = {"requested_by": "ana", "priority": 2, "submitted_params": "{\"versao\": 4}",
          "scheduled_at": datetime.datetime(2026, 10, 20, 3, 0, 0, 999999)}


class _Types(object):
    """Captura os setinputsizes por cursor (set_input_types)."""

    def __init__(self):
        self.calls = []

    def __call__(self, cursor, **mapping):
        self.calls.append(dict(mapping))


class TestAgendaWithoutDb(unittest.TestCase):

    def setUp(self):
        self.repo = RepoSchedulerSchedules("OWN_X", "pfx_")
        self.types = _Types()
        p = mock.patch.object(db_conn, "set_input_types", self.types)
        p.start()
        self.addCleanup(p.stop)

    def _without_transaction(self, conn):
        self.assertEqual((conn.commits, conn.rollbacks), (0, 0), "o COMMIT unico e de quem chama (passo 8)")

    def test_pagina_e_trava(self):
        conn = _Conn([("ROWNUM <= :batch_size", (2, [(5, OLD), (7, OLD)])), ("SKIP LOCKED", (1, [(5,)]))])
        self.assertEqual(self.repo.due_rules(conn, 50), [(5, OLD), (7, OLD)])
        sql, binds = conn.executed[0]
        for snippet in ("WHERE active = 'Y' AND next_run_at <= SYSDATE",
                       "(next_run_at > :last_next OR (next_run_at = :last_next AND id > :last_id))",
                       "ORDER BY next_run_at, id", "OWN_X.pfx_schedules"):
            self.assertIn(snippet, sql)
        self.assertEqual(binds, {"last_next": scheduler_schedules.DATE_INITIAL, "last_id": 0, "batch_size": 50})
        self.repo.due_rules(conn, 50, last_next=NEW, last_id=5)
        self.assertEqual(conn.executed[1][1]["last_next"], NEW.replace(microsecond=0))
        self.assertEqual(self.types.calls[0], {"last_next": db_conn.TIPO_DATE})
        self.assertTrue(self.repo.lock_rule(conn, 5))
        self.assertIn("FOR UPDATE SKIP LOCKED", conn.executed[-1][0])
        self.assertFalse(self.repo.lock_rule(_Conn([]), 5), "sem linha: outro agente a processa")
        self._without_transaction(conn)

    def test_reserva_sem_updated_e_ticket_com_ocorrencia(self):
        conn = _Conn([("SET next_run_at = :new_date, last_run_at = SYSDATE", (1, []))])
        self.assertTrue(self.repo.reserve_and_create_ticket(conn, RULE, OLD, NEW, 501, TICKET,
                                                          [{"parameter_id": 4, "answer_value": "x"}], AGENT))
        upd, b_upd = conn.executed[0]
        self.assertNotIn("updated_", upd, "a reserva e rotina tecnica (CR-006)")
        self.assertIn("WHERE id = :id AND active = 'Y' AND next_run_at = :old_date", upd)
        self.assertEqual((b_upd["new_date"], b_upd["old_date"], b_upd["ticket_id"]),
                         (NEW.replace(microsecond=0), OLD, 501))
        self.assertIn({"new_date": db_conn.TIPO_DATE, "old_date": db_conn.TIPO_DATE}, self.types.calls)
        ins = [e for e in conn.executed if e[0].startswith("INSERT INTO OWN_X.pfx_tickets")][0]
        self.assertIn("NULL, 'PENDING'", ins[0], "ip_origem nulo")
        self.assertEqual((ins[1]["scheduled_at"], ins[1]["actor"], ins[1]["schedule_id"], ins[1]["id"]),
                         (TICKET["scheduled_at"].replace(microsecond=0), ACTOR, 9, 501))
        resp = [e for e in conn.executed if e[0].startswith("INSERT INTO OWN_X.pfx_ticket_answer")][0]
        self.assertEqual((resp[1]["ticket_id"], resp[1]["actor"], resp[1]["value"]), (501, ACTOR, "x"))
        self._without_transaction(conn)
        race = _Conn([])
        self.assertFalse(self.repo.reserve_and_create_ticket(race, RULE, OLD, NEW, 502, TICKET, [], AGENT))
        self.assertEqual(race.sql("INSERT"), [], "rowcount 0: nenhum ticket")

    def test_ocorrencia_duplicada(self):
        error = _Error("ORA-00001: unique constraint (OWN_X.IX_PFX_TCK_OCCUR) violated")
        conn = _Conn([("SET next_run_at = :new_date", (1, [])), ("INSERT INTO OWN_X.pfx_tickets", error)])
        with self.assertRaises(DuplicateOccurrence):
            self.repo.reserve_and_create_ticket(conn, RULE, OLD, NEW, 503, TICKET, [], AGENT)
        other = _Error("ORA-00001: unique constraint (OWN_X.PK_PFX_TICKETS) violated")
        conn = _Conn([("SET next_run_at = :new_date", (1, [])), ("INSERT INTO OWN_X.pfx_tickets", other)])
        with self.assertRaises(_Error):
            self.repo.reserve_and_create_ticket(conn, RULE, OLD, NEW, 503, TICKET, [], AGENT)

    def test_conclusoes_mantem_proxima_execucao(self):
        conn = _Conn([("pause_reason = 'COMPLETED'", (1, []))])
        self.assertTrue(self.repo.complete_with_ticket(conn, RULE, OLD, 601, TICKET, [], AGENT))
        upd, b = conn.executed[0]
        self.assertIn("last_run_at = SYSDATE, last_ticket_id = :ticket_id, updated_at = SYSDATE", upd)
        self.assertNotIn("next_run_at =", upd.split("WHERE")[0], "nao grava NULL nem muda a data (D1)")
        self.assertEqual((b["old_date"], b["actor"]), (OLD, ACTOR))
        aud = [e for e in conn.executed if "SCHEDULE_PAUSE" in e[0]][0]
        self.assertEqual(aud[1]["detail"], "pause_reason: COMPLETED")
        self.assertTrue(conn.sql("INSERT INTO OWN_X.pfx_tickets"))
        conn = _Conn([("pause_reason = 'COMPLETED'", (1, []))])
        self.assertTrue(self.repo.complete_without_ticket(conn, 9, OLD, AGENT))
        upd = conn.executed[0][0]
        self.assertNotIn("last_run_at", upd)
        self.assertNotIn("last_ticket_id", upd)
        self.assertEqual(conn.sql("INSERT INTO OWN_X.pfx_tickets"), [])
        self.assertFalse(self.repo.complete_without_ticket(_Conn([]), 9, OLD, AGENT))
        self._without_transaction(conn)

    def test_avanco_pausa_cron_erro_e_erro_interno(self):
        conn = _Conn([("SET next_run_at = :new_date WHERE id", (1, []))])
        self.assertTrue(self.repo.advance_without_ticket(conn, 9, OLD, NEW))
        upd = conn.executed[0][0]
        for missing in ("last_run_at", "last_ticket_id", "updated_"):
            self.assertNotIn(missing, upd, "R-05")
        conn = _Conn([("pause_reason = :reason", (1, []))])
        self.assertTrue(self.repo.pause(conn, 9, OLD, "NO_PERMISSION", "solicitante sem acesso", AGENT))
        self.assertIn("AND active = 'Y' AND next_run_at = :old_date", conn.executed[0][0], "R-19")
        aud = [e for e in conn.executed if "SCHEDULE_PAUSE" in e[0]][0][1]
        self.assertEqual((aud["detail"], aud["rid"], aud["actor"]),
                         ("pause_reason: NO_PERMISSION; solicitante sem acesso", 9, ACTOR))
        already = _Conn([])
        self.assertFalse(self.repo.pause(already, 9, OLD, "NO_PERMISSION", None, AGENT))
        self.assertEqual(already.sql("SCHEDULE_PAUSE"), [], "rowcount 0: sem auditoria")
        for ticket_id in (None, 701):
            conn = _Conn([("pause_reason = 'INVALID_CRON'", (1, []))])
            self.assertTrue(self.repo.pause_cron_error(conn, RULE, OLD, ticket_id, TICKET, [], "horizonte", AGENT))
            upd, b = conn.executed[0]
            self.assertIn("NVL(:ticket_id, last_ticket_id)", upd)
            self.assertNotIn("SET next_run_at", upd)
            self.assertEqual(b["ticket_id"], ticket_id)
            self.assertEqual(bool(conn.sql("INSERT INTO OWN_X.pfx_tickets")), ticket_id is not None)
        conn = _Conn([("pause_reason = 'INTERNAL_ERROR'", (1, []))])
        self.assertTrue(self.repo.pause_internal_error(conn, 9, "ValueError", AGENT))
        self.assertIn("WHERE id = :id AND active = 'Y'", conn.executed[0][0])
        with self.assertRaises(ValueError):
            self.repo.pause(_Conn([("pause_reason = :reason", (1, []))]), 9, OLD, "INVALID_PARAM", "x" * 1000,
                             AGENT)
        self._without_transaction(conn)

    def test_prefixo_e_owner_parametrizados(self):
        conn = _Conn([])
        RepoSchedulerSchedules("outro", "abcdefg_").due_rules(conn, 10)
        self.assertIn("outro.abcdefg_schedules", conn.executed[0][0])
        self.assertNotIn("tbsss_", conn.executed[0][0])


class TestQueueNodeOfflineWithoutDb(unittest.TestCase):

    def setUp(self):
        self.repo = RepoSchedulerQueue("OWN_X", "pfx_")

    def test_duas_etapas_sem_os_proprios_e_com_ator(self):
        conn = _Conn([("SELECT SYSDATE FROM DUAL", (1, [(OLD,)])), ("FOR UPDATE SKIP LOCKED", (2, [(4,), (5,)]))],
                     counts={4: 1, 5: 0})
        seen = []
        ids = self.repo.mark_node_offline(conn, AGENT, 180, lambda now: seen.append(now) or False)
        self.assertEqual((ids, seen), ([4], [OLD]), "a linha ja finalizada (rowcount 0) nao conta")
        sel = [s for s in conn.sql("SKIP LOCKED")][0]
        self.assertIn("<> :agent_id", sel)
        self.assertIn("heartbeat_at < SYSDATE - :node_offline_timeout_s * INTERVAL '1' SECOND", sel)
        upd, rows = [e for e in conn.executed if "NODE_OFFLINE" in e[0]][0]
        self.assertIn("updated_at = SYSDATE, updated_by = :actor", upd)
        self.assertEqual(rows[0], {"actor": ACTOR, "id": 4})
        self.assertEqual(conn.commits, 1)

    def test_salto_de_relogio_aborta_sem_marcar(self):
        conn = _Conn([("SELECT SYSDATE FROM DUAL", (1, [(OLD,)]))])
        self.assertIsNone(self.repo.mark_node_offline(conn, AGENT, 180, lambda now: True))
        self.assertEqual(conn.sql("SKIP LOCKED"), [], "R-10: nada lido nem marcado")

    def test_finalizar_fenced(self):
        conn = _Conn([("status_reason = :reason", (1, []))])
        self.assertTrue(self.repo.finalize_fenced(conn, 7, AGENT))
        self.assertEqual(conn.executed[0][1]["reason"], "FENCED")
        self.assertFalse(self.repo.finalize_fenced(_Conn([]), 7, AGENT), "ja NODE_OFFLINE: rowcount 0")


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestAgendaOracle(unittest.TestCase):
    """Operacoes reais com massa propria (README §2.5)."""

    @classmethod
    def setUpClass(cls):
        import test_repo_contract as trc
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
