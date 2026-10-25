# -*- coding: utf-8 -*-
"""Testes do repo_oracle.scheduler_schedules e das operacoes de no offline e fencing do scheduler_queue (F8.4a;
README §7.5, §8.8, §8.9; CR-006; CR-007 R-05, R-08, R-12, R-19, R-27; CR-008 R-03, R-10, R-19, R-31).

Sem banco: conexao roteirizada do test_scheduler_queue (SQL literal, binds de data sem microssegundos e com
TIPO_DATE, nenhuma operacao do agenda faz COMMIT/ROLLBACK). Com SSS_TEST_ORACLE=1: as operacoes reais no
owner do instance/config.ini com massa propria (inclusive o teste obrigatorio de microssegundos).
"""
from tests.support import _testenv  # noqa: F401

import datetime
import unittest
from unittest import mock

import db_conn
from repo_oracle import scheduler_schedules
from repo_oracle.scheduler_schedules import DuplicateOccurrence, RepoSchedulerSchedules
from repo_oracle.scheduler_queue import RepoSchedulerQueue
from tests.unit.persistence.test_scheduler_queue import _Conn, _Error

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


if __name__ == "__main__":
    unittest.main()
