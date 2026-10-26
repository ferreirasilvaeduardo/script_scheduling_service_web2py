# -*- coding: utf-8 -*-
"""Agente em alta disponibilidade (F8.4): desdobro dos agendamentos (F8.4b; README §7.4 e §7.5).

Repositorio da agenda em memoria com a semantica do contrato (rowcount pela old_date, SKIP LOCKED, ROLLBACK
que desfaz a regra, DuplicateOccurrence), contexto RBAC em memoria e as funcoes reais de recurrence, rbac e
params_compiler. Relogio do banco (agora_banco) e monotonico injetaveis.
"""
from tests.support import _testenv  # noqa: F401

import copy
import datetime
import json
import unittest
from unittest import mock

from sss.persistence import db_conn
from sss.scheduler import schedule_expansion
from sss.core import rbac
from sss.core import sql_ident
from sss.persistence.oracle.scheduler_schedules import DuplicateOccurrence
from tests.unit.persistence.test_scheduler_queue import _Error

AGENT = "srv-ha"
NOW = datetime.datetime(2026, 10, 20, 10, 0, 0)
LOGIN = "ana"


class _Cfg(object):
    misfire_policy = "RUN_ONCE"
    misfire_tolerance_s = 300
    cron_horizon_days = 1461
    heartbeat_interval_s = 10
    schedule_batch_size = 50
    script_timeout_s = 3600
    node_offline_timeout_s = 180

    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Conn(object):
    """Transacao em memoria: a primeira escrita guarda o estado; ROLLBACK o devolve; COMMIT o confirma."""

    def __init__(self, schedule_repo):
        self.agenda = schedule_repo
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1
        self.agenda._before = None

    def rollback(self):
        self.rollbacks += 1
        if self.agenda._before is not None:
            self.agenda.rules, self.agenda.tickets, self.agenda.audit = self.agenda._before
            self.agenda._before = None


class _Agenda(object):
    """Contrato do RepoSchedulerSchedules em memoria."""

    def __init__(self):
        self.rules = {}
        self.tickets = {}
        self.audit = []
        self.locked_by_other = set()
        self.failures = []
        self.duplicate = set()
        self.seq = 1000
        self._before = None
        self.scripts = {}
        self.links = {}

    def _write(self, name):
        if self.failures and self.failures[0][0] == name:
            raise self.failures.pop(0)[1]
        if self._before is None:
            self._before = (copy.deepcopy(self.rules), copy.deepcopy(self.tickets), list(self.audit))

    def due_rules(self, conn, batch, last_next=None, last_id=0):
        due = sorted((r["next_run_at"], r["id"]) for r in self.rules.values()
                          if r["active"] == "Y" and r["next_run_at"] <= NOW)
        if last_next is not None:
            due = [v for v in due if v > (last_next, last_id)]
        return [(rid, next_value) for next_value, rid in due[:batch]]

    def lock_rule(self, conn, rid):
        r = self.rules.get(rid)
        return rid not in self.locked_by_other and r is not None and r["active"] == "Y"

    def load_rule(self, conn, rid):
        if self.failures and self.failures[0][0] == "load_rule":
            raise self.failures.pop(0)[1]
        return copy.deepcopy(self.rules.get(rid))

    def user_login(self, conn, user_id):
        return LOGIN

    def script_and_links(self, conn, script_id):
        return copy.deepcopy(self.scripts.get(script_id)), copy.deepcopy(self.links.get(script_id, []))

    def get_ticket_status(self, conn, tid):
        t = self.tickets.get(tid)
        return (t["status"], t["created_at"]) if t else None

    def next_ticket_id(self, conn):
        self.seq += 1
        return self.seq

    def _rule_ok(self, rid, old):
        r = self.rules[rid]
        return r["active"] == "Y" and r["next_run_at"] == old

    def _ticket(self, rule, tid, ticket, rows):
        self._write("inserir_ticket")
        if (rule["id"], ticket["scheduled_at"]) in self.duplicate:
            raise DuplicateOccurrence("ix_tck_ocor")
        self.tickets[tid] = dict(ticket, id=tid, status="PENDING", schedule_id=rule["id"], created_at=NOW,
                                 created_by="SYSTEM:%s" % AGENT, answers=list(rows))

    def reserve_and_create_ticket(self, conn, rule, old, new, tid, ticket, rows, agent_id):
        self._write("reservar")
        if not self._rule_ok(rule["id"], old):
            return False
        self.rules[rule["id"]].update(next_run_at=new, last_run_at=NOW, last_ticket_id=tid)
        self._ticket(rule, tid, ticket, rows)
        return True

    def complete_with_ticket(self, conn, rule, old, tid, ticket, rows, agent_id):
        self._write("complete")
        if not self._rule_ok(rule["id"], old):
            return False
        self.rules[rule["id"]].update(active="N", pause_reason="COMPLETED", last_run_at=NOW,
                                        last_ticket_id=tid, updated_by="SYSTEM:%s" % agent_id)
        self._ticket(rule, tid, ticket, rows)
        self.audit.append((rule["id"], "pause_reason: COMPLETED"))
        return True

    def complete_without_ticket(self, conn, rid, old, agent_id):
        self._write("complete")
        if not self._rule_ok(rid, old):
            return False
        self.rules[rid].update(active="N", pause_reason="COMPLETED", updated_by="SYSTEM:%s" % agent_id)
        self.audit.append((rid, "pause_reason: COMPLETED"))
        return True

    def advance_without_ticket(self, conn, rid, old, new):
        self._write("avancar")
        if not self._rule_ok(rid, old):
            return False
        self.rules[rid]["next_run_at"] = new
        return True

    def pause(self, conn, rid, old, reason, detail, agent_id):
        self._write("pause")
        if not self._rule_ok(rid, old):
            return False
        self.rules[rid].update(active="N", pause_reason=reason, updated_by="SYSTEM:%s" % agent_id)
        self.audit.append((rid, "pause_reason: %s%s" % (reason, "; " + detail if detail else "")))
        return True

    def pause_cron_error(self, conn, rule, old, tid, ticket, rows, detail, agent_id):
        self._write("pause")
        if not self._rule_ok(rule["id"], old):
            return False
        r = self.rules[rule["id"]]
        r.update(active="N", pause_reason="INVALID_CRON", updated_by="SYSTEM:%s" % agent_id)
        if tid is not None:
            r.update(last_run_at=NOW, last_ticket_id=tid)
            self._ticket(rule, tid, ticket, rows)
        self.audit.append((rule["id"], "pause_reason: INVALID_CRON"))
        return True

    def pause_internal_error(self, conn, rid, detail, agent_id):
        self._write("pause_internal_error")
        r = self.rules[rid]
        if r["active"] != "Y":
            return False
        r.update(active="N", pause_reason="INTERNAL_ERROR", updated_by="SYSTEM:%s" % agent_id)
        self.audit.append((rid, "pause_reason: INTERNAL_ERROR; %s" % detail))
        return True


class _Queue(object):
    """execution_context do RepoSchedulerQueue em memoria (o mesmo ctx RBAC da web)."""

    def __init__(self):
        self.usuario = {"user_id": 7, "login": LOGIN, "profile_id": 2, "active_user": "Y", "active_profile": "Y",
                        "is_admin": "N", "perm_version": 1, "features": ["EXEC_SCRIPT"], "environments": ["PRD"],
                        "scripts": [3]}
        self.script = {"id": 3, "name": "carga", "interpreter": "SH", "path_file": "/opt/x/carga.sh", "active": "Y",
                       "timeout_s": 600}
        self.environment = {"id": 1, "name": "PRD", "description": "Producao", "connection": None, "active": "Y"}
        self.homologations = frozenset([1])

    def execution_context(self, conn, ticket):
        return {"script": dict(self.script), "environment": dict(self.environment), "homologations": self.homologations,
                "ctx": rbac.user_context(dict(self.usuario)) if self.usuario else None, "schedule": None}


def _link():
    return {"parameter_id": 11, "id": 11, "code": "data_ref", "param_flag": "--data", "label": "Data",
            "description": None, "component_type": "TEXT", "options_json": None, "default_value": None,
            "validation_regex": None, "sensitive": "N", "active": "Y", "sort_order": 1, "required": "Y",
            "default_value_override": None, "script_id": 3}


class _Base(unittest.TestCase):

    def setUp(self):
        self.agenda = _Agenda()
        self.queue = _Queue()
        self.agenda.scripts[3] = {"id": 3, "name": "carga", "interpreter": "SH", "path_file": "/opt/x/carga.sh",
                                  "param_type": "NAMED", "max_parallel_env": 2, "timeout_s": 600, "active": "Y"}
        self.agenda.links[3] = [_link()]
        self.conn = _Conn(self.agenda)
        self.now = NOW
        p = mock.patch.object(db_conn, "db_now", lambda conn: self.now)
        p.start()
        self.addCleanup(p.stop)
        self.monotonic = [0.0]
        self.cfg = _Cfg()
        self.horizon = None

    def des(self):
        return schedule_expansion.Expansion(self.agenda, self.queue, AGENT, self.cfg, lambda: self.monotonic[0],
                                 horizon_days=self.horizon)

    def rule(self, rid=1, **kw):
        base = {"id": rid, "name": "R%d" % rid, "script_id": 3, "environment": "PRD", "user_id": 7, "priority": 2,
                "recurrence_type": "DAILY", "cron_expression": None, "run_time": "09:55", "week_days": None,
                "month_day": None, "params_json": json.dumps({"data_ref": "2026-10-20"}),
                "start_date": datetime.datetime(2026, 1, 1), "end_date": None,
                "next_run_at": datetime.datetime(2026, 10, 20, 9, 55), "last_run_at": None,
                "last_ticket_id": None, "pause_reason": None, "active": "Y"}
        base.update(kw)
        self.agenda.rules[rid] = base
        return base

    def process(self, rid=1):
        return self.des().process(self.conn, rid)


class TestExpansion(_Base):

    def test_ticket_com_ocorrencia_snapshot_v5_e_um_commit(self):
        self.rule()
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            self.assertEqual(self.process(), "TICKET")
        self.assertEqual(self.conn.commits, 1, "COMMIT unico por regra")
        r = self.agenda.rules[1]
        t = self.agenda.tickets[r["last_ticket_id"]]
        self.assertEqual(r["next_run_at"], datetime.datetime(2026, 10, 21, 9, 55))
        self.assertEqual((t["scheduled_at"], t["requested_by"], t["priority"], t["created_by"]),
                         (datetime.datetime(2026, 10, 20, 9, 55), LOGIN, 2, "SYSTEM:" + AGENT),
                         "scheduled_at = ocorrencia coberta (R-27, R-03)")
        snap = json.loads(t["submitted_params"])
        self.assertEqual((snap["version"], snap["path_file"], snap["args"]), (6, "/opt/x/carga.sh", ["--data", "2026-10-20"]))
        self.assertNotIn("pasta_base", snap)
        self.assertEqual(t["answers"], [{"parameter_id": 11, "answer_value": "2026-10-20"}])
        self.assertTrue(any("agendamento 1: ticket %d gerado" % t["id"] in l for l in logs.output))

    def test_corrida_e_outro_agente(self):
        self.rule()
        self.agenda.reserve_and_create_ticket = lambda *a: False
        self.assertEqual(self.process(), "RACE")
        self.assertEqual((self.agenda.tickets, self.conn.commits), ({}, 0))
        self.agenda.locked_by_other.add(1)
        self.assertEqual(self.process(), "OTHER_AGENT")

    def test_pausas_pelo_rbac_com_a_traducao_unica(self):
        cases = (("active_user", "N", "USER_INACTIVE"), ("active_profile", "N", "NO_PERMISSION"),
                 ("scripts", [], "NO_PERMISSION"), ("environments", [], "NO_PERMISSION"),
                 ("features", [], "NO_PERMISSION"))
        for i, (field, value, reason) in enumerate(cases, 1):
            self.setUp()
            self.rule(i)
            self.queue.usuario[field] = value
            with self.assertLogs("sss_scheduler", "WARNING"):
                self.assertEqual(self.process(i), "PAUSED", field)
            self.assertEqual(self.agenda.rules[i]["pause_reason"], reason, field)
            self.assertEqual(self.agenda.rules[i]["updated_by"], "SYSTEM:" + AGENT)
        for key, reason in ((("script", "active"), "SCRIPT_INACTIVE"), (("environment", "active"), "ENVIRONMENT_INACTIVE")):
            self.setUp()
            self.rule()
            getattr(self.queue, key[0])[key[1]] = "N"
            with self.assertLogs("sss_scheduler", "WARNING"):
                self.process()
            self.assertEqual(self.agenda.rules[1]["pause_reason"], reason)

    def test_r33_todo_motivo_do_rbac_cabe_na_ck(self):
        accepted = sql_ident.TABLES["schedules"]["cks"]["pause"]["expr"]
        for name in dir(rbac.Reason):
            if name.startswith("_") or name == "OK":
                continue
            self.assertIn("'%s'" % rbac.pause_reason_for(getattr(rbac.Reason, name)), accepted, name)

    def test_prioridade_rebaixada(self):
        self.rule(priority=1)
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.process()
        t = self.agenda.tickets[self.agenda.rules[1]["last_ticket_id"]]
        self.assertEqual((t["priority"], self.agenda.rules[1]["priority"]), (2, 1), "a regra nao muda")
        self.assertTrue(any("PRIORIDADE_REBAIXADA" in l for l in logs.output))
        self.setUp()
        self.rule(priority=1)
        self.queue.usuario["is_admin"] = "Y"
        self.process()
        self.assertEqual(self.agenda.tickets[self.agenda.rules[1]["last_ticket_id"]]["priority"], 1)

    def test_sobreposicao_avanca_sem_ticket_e_preso(self):
        self.rule(last_ticket_id=50)
        self.agenda.tickets[50] = {"status": "RUNNING", "created_at": NOW - datetime.timedelta(minutes=5)}
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            self.assertEqual(self.process(), "ADVANCED")
        r = self.agenda.rules[1]
        self.assertEqual((r["last_ticket_id"], r["next_run_at"], r["last_run_at"]),
                         (50, datetime.datetime(2026, 10, 21, 9, 55), None), "R-05: sem mexer no ultimo ticket")
        self.assertTrue(any("SKIP_OVERLAP: o ticket 50 ainda esta RUNNING" in l for l in logs.output))
        self.setUp()
        self.rule(last_ticket_id=50)
        self.agenda.tickets[50] = {"status": "PENDING", "created_at": NOW - datetime.timedelta(hours=2)}
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.process()
        self.assertTrue(any("SKIP_OVERLAP_PRESO: o ticket 50" in l for l in logs.output), "600 + 180 s < 2 h")
        for free in (None, "SUCCESS"):
            self.setUp()
            self.rule(last_ticket_id=50)
            if free:
                self.agenda.tickets[50] = {"status": free, "created_at": NOW}
            self.assertEqual(self.process(), "TICKET", "inexistente (purgado) ou terminal e livre")

    def test_misfire_run_once_e_skip(self):
        three_days = datetime.datetime(2026, 10, 17, 9, 55)
        self.rule(next_run_at=three_days)
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.assertEqual(self.process(), "TICKET")
        self.assertEqual(len(self.agenda.tickets), 1, "RUN_ONCE: um ticket apos o downtime")
        self.assertEqual(list(self.agenda.tickets.values())[0]["scheduled_at"], datetime.datetime(2026, 10, 20, 9, 55))
        self.assertTrue(any("MISFIRE: 3 ocorrencia(s) perdida(s)" in l for l in logs.output))
        self.setUp()
        self.cfg = _Cfg(misfire_policy="SKIP")
        self.rule(next_run_at=three_days, run_time="09:00")
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(self.process(), "ADVANCED")
        self.assertEqual((self.agenda.tickets, self.agenda.rules[1]["next_run_at"]),
                         ({}, datetime.datetime(2026, 10, 21, 9, 0)))
        # R-21: SKIP com a vencida mais recente dentro da tolerancia gera o ticket dela.
        self.setUp()
        self.cfg = _Cfg(misfire_policy="SKIP")
        self.rule(next_run_at=three_days)
        with self.assertLogs("sss_scheduler", "INFO"):
            self.assertEqual(self.process(), "TICKET")

    def test_perdidas_dentro_da_tolerancia_em_info(self):
        self.rule(recurrence_type="CRON", cron_expression="* * * * *", run_time=None,
                   next_run_at=NOW - datetime.timedelta(minutes=3))
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            self.process()
        self.assertTrue(any("ocorrencia(s) coalescida(s) dentro da tolerancia" in l for l in logs.output))
        self.assertFalse(any("WARNING" in l for l in logs.output))

    def test_unica_conclui_com_e_sem_ticket(self):
        self.rule(recurrence_type="ONCE", run_time=None)
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            self.assertEqual(self.process(), "COMPLETED_WITH_TICKET")
        r = self.agenda.rules[1]
        self.assertEqual((r["active"], r["pause_reason"], r["next_run_at"]),
                         ("N", "COMPLETED", datetime.datetime(2026, 10, 20, 9, 55)), "proxima_execucao mantida (D1)")
        self.assertEqual(len(self.agenda.tickets), 1)
        self.assertEqual(self.agenda.audit, [(1, "pause_reason: COMPLETED")])
        self.assertFalse(any("WARNING" in l for l in logs.output), "conclusao e INFO")
        self.setUp()
        self.cfg = _Cfg(misfire_policy="SKIP")
        self.rule(recurrence_type="ONCE", run_time=None, next_run_at=datetime.datetime(2026, 10, 19, 9, 0))
        with self.assertLogs("sss_scheduler", "INFO"):
            self.assertEqual(self.process(), "COMPLETED_WITHOUT_TICKET")
        self.assertEqual((self.agenda.tickets, self.agenda.rules[1]["last_ticket_id"]), ({}, None))

    def test_data_fim_conclui_com_o_ticket_da_ocorrencia(self):
        self.rule(end_date=datetime.datetime(2026, 10, 20, 23, 59))
        self.assertEqual(self.process(), "COMPLETED_WITH_TICKET")
        self.assertEqual(self.agenda.rules[1]["pause_reason"], "COMPLETED")

    def test_sobreposicao_numa_regra_que_conclui(self):
        self.rule(recurrence_type="ONCE", run_time=None, last_ticket_id=50)
        self.agenda.tickets[50] = {"status": "RUNNING", "created_at": NOW}
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            self.assertEqual(self.process(), "COMPLETED_WITHOUT_TICKET")
        self.assertTrue(any("SKIP_OVERLAP: regra concluida sem ticket; ocorrencias perdidas: 1" in l
                            for l in logs.output))
        self.assertEqual(len(self.agenda.tickets), 1)

    def test_param_invalido_e_cron_invalido(self):
        self.rule(params_json=json.dumps({}))
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(self.process(), "PAUSED")
        self.assertEqual(self.agenda.rules[1]["pause_reason"], "INVALID_PARAM")
        detail = self.agenda.audit[0][1]
        self.assertTrue(detail.startswith("pause_reason: INVALID_PARAM; data_ref: "), detail)
        self.setUp()
        self.rule(params_json="{nao json")
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.process()
        self.assertEqual(self.agenda.rules[1]["pause_reason"], "INVALID_PARAM")
        self.setUp()
        self.rule(recurrence_type="CRON", cron_expression="99 * * * *", run_time=None)
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(self.process(), "PAUSED")
        self.assertEqual((self.agenda.rules[1]["pause_reason"], self.agenda.tickets), ("INVALID_CRON", {}))

    def test_r19_cron_sem_proxima_no_horizonte(self):
        # 29/02 so em 2028; com horizonte de 30 dias (injetado), a proxima nao existe.
        self.horizon = 30
        self.rule(recurrence_type="CRON", cron_expression="0 10 29 2 *", run_time=None,
                   next_run_at=datetime.datetime(2026, 10, 20, 9, 55))
        self.agenda.rules[1]["cron_expression"] = "55 9 * * *"
        with mock.patch("sss.core.recurrence.next_run", side_effect=schedule_expansion.recurrence.CronError("sem ocorrencia")):
            with self.assertLogs("sss_scheduler", "WARNING"):
                self.assertEqual(self.process(), "INVALID_CRON_WITH_TICKET")
        r = self.agenda.rules[1]
        self.assertEqual((r["pause_reason"], r["next_run_at"]), ("INVALID_CRON", datetime.datetime(2026, 10, 20, 9, 55)))
        self.assertEqual(len(self.agenda.tickets), 1, "o ticket da vencida e gerado antes de pausar")
        self.setUp()
        self.rule(recurrence_type="CRON", cron_expression="55 9 * * *", run_time=None, last_ticket_id=50)
        self.agenda.tickets[50] = {"status": "RUNNING", "created_at": NOW}
        with mock.patch("sss.core.recurrence.next_run", side_effect=schedule_expansion.recurrence.CronError("sem ocorrencia")):
            with self.assertLogs("sss_scheduler", "WARNING"):
                self.assertEqual(self.process(), "INVALID_CRON")
        self.assertEqual(len(self.agenda.tickets), 1, "sobreposicao: sem ticket novo")

    def test_r31_ocorrencia_duplicada_avanca_numa_nova_transacao(self):
        self.rule()
        self.agenda.duplicate.add((1, datetime.datetime(2026, 10, 20, 9, 55)))
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.assertEqual(self.process(), "DUPLICATE_OCCURRENCE")
        r = self.agenda.rules[1]
        self.assertEqual((r["next_run_at"], r["last_ticket_id"]), (datetime.datetime(2026, 10, 21, 9, 55), None))
        self.assertEqual((self.conn.rollbacks, self.conn.commits), (1, 1))
        self.assertTrue(any("DUPLICATE_OCCURRENCE" in l for l in logs.output))
        self.assertEqual(self.agenda.due_rules(self.conn, 50), [], "nao e reprocessada no ciclo seguinte")

    def test_r22_erro_de_banco_tres_vezes_e_erro_interno(self):
        self.rule()
        d = self.des()
        space = _Error("ORA-01653: unable to extend table")
        for n in (1, 2):
            self.agenda.failures = [("inserir_ticket", space)]
            with self.assertLogs("sss_scheduler", "WARNING") as logs:
                self.assertEqual(d.process(self.conn, 1), "DB_ERROR")
            self.assertTrue(any("DESDOBRO_ERRO_BANCO: ORA-01653 (falha %d de 3 seguidas)" % n in l for l in logs.output))
            self.assertEqual((self.agenda.rules[1]["active"], self.agenda.tickets), ("Y", {}), "sem pausar")
        self.agenda.failures = [("inserir_ticket", space)]
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(d.process(self.conn, 1), "INTERNAL_ERROR")
        self.assertEqual(self.agenda.rules[1]["pause_reason"], "INTERNAL_ERROR")
        self.assertIn("3 falhas seguidas de banco (ORA-01653)", self.agenda.audit[-1][1])
        # Sucesso zera o contador.
        self.setUp()
        self.rule()
        d = self.des()
        self.agenda.failures = [("inserir_ticket", space)]
        with self.assertLogs("sss_scheduler", "WARNING"):
            d.process(self.conn, 1)
        self.assertEqual(d.process(self.conn, 1), "TICKET")
        self.assertEqual(d.failures, {})
        # Excecao que nao e de banco pausa na primeira, em transacao separada (R-08).
        self.setUp()
        self.rule()
        self.agenda.failures = [("load_rule", ValueError("dado incoerente"))]
        with self.assertLogs("sss_scheduler", "ERROR"):
            self.assertEqual(self.process(), "INTERNAL_ERROR")
        self.assertEqual(self.agenda.rules[1]["pause_reason"], "INTERNAL_ERROR")
        self.assertEqual(self.agenda.audit[-1][1], "pause_reason: INTERNAL_ERROR; ValueError")

    def test_pausa_que_falha_ignora_a_regra_no_ciclo(self):
        self.rule(1)
        self.rule(2, next_run_at=datetime.datetime(2026, 10, 20, 9, 56))
        self.agenda.failures = [("load_rule", ValueError("x")), ("pause_internal_error", ValueError("y"))]
        with self.assertLogs("sss_scheduler", "ERROR"):
            stats = self.des().run(self.conn)
        self.assertEqual(stats["tickets"], 1, "a regra 2 segue")
        self.assertEqual(self.agenda.rules[1]["active"], "Y")

    def test_paginacao_e_orcamento(self):
        for i in range(1, 6):
            self.rule(i, next_run_at=datetime.datetime(2026, 10, 20, 9, 50 + i))
        self.cfg = _Cfg(schedule_batch_size=2)
        pages = []
        original = self.agenda.due_rules
        self.agenda.due_rules = lambda *a: pages.append(a[2:]) or original(*a)
        self.assertEqual(self.des().run(self.conn)["tickets"], 5)
        self.assertEqual(len(pages), 3, "2 + 2 + 1")
        self.assertEqual(pages[0], (None, 0))
        self.assertEqual(pages[1], (datetime.datetime(2026, 10, 20, 9, 52), 2))
        # Orcamento (heartbeat / 2 = 5 s) estourado: o resto fica para o proximo ciclo.
        self.setUp()
        for i in range(1, 6):
            self.rule(i, next_run_at=datetime.datetime(2026, 10, 20, 9, 50 + i))
        d = self.des()
        original_proc = d.process

        def lento(conn, rid):
            self.monotonic[0] += 2.0
            return original_proc(conn, rid)
        d.process = lento
        self.assertEqual(d.run(self.conn)["tickets"], 3)
        self.assertEqual(sum(1 for r in self.agenda.rules.values() if r["last_ticket_id"]), 3)

    def test_continuar_falso_interrompe_entre_regras(self):
        self.rule(1)
        self.rule(2)
        self.assertEqual(self.des().run(self.conn, keep_going=lambda: False)["regras"], 0)


if __name__ == "__main__":
    unittest.main()


import os  # noqa: E402


# ---------------------------------------------------------------------------- F8.4c: fencing e NODE_OFFLINE

import os as _os  # noqa: E402
import time as _time  # noqa: E402

from tests.unit.scheduler import test_scheduler_claim as tsc  # noqa: E402


class TestFencing(tsc._Base):
    """Self-fencing (README §8.9) com o laco real, scripts /bin/sh e o banco em memoria do test_scheduler_claim."""

    def _running(self, tid):
        return lambda: self.db.tickets[tid]["status"] == "RUNNING" and self.db.tickets[tid]["process_id"]

    def test_fence_no_limiar_encerra_e_recupera_como_fenced(self):
        tid = self.db.ticket(self.db.script("sleep 300\n"))
        self.start_agent(fence_timeout_s=1.5)
        self.run_loop(self._running(tid))
        pid = self.db.tickets[tid]["process_id"]
        self.connection.down = True
        start = _time.monotonic()
        with self.assertLogs("sss_scheduler", "CRITICAL") as logs:
            self.run_loop(lambda: self.ag.fenced, limit=10)
        self.assertGreaterEqual(_time.monotonic() - start, 1.0, "nao antes do limiar")
        self.assertTrue(any("FENCED: sem heartbeat confirmado" in l for l in logs.output))
        # Em modo cercado: sem claims nem desdobro, mesmo com ticket novo na fila.
        new = self.db.ticket(self.db.script("echo novo\n"))
        self.run_loop(lambda: not tsc._alive(pid), limit=10)
        self.assertFalse(tsc._alive(pid), "o grupo foi encerrado no fence")
        self.assertEqual(self.db.tickets[new]["status"], "PENDING")
        self.connection.down = False
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.run_loop(lambda: self.finished(tid)() and not self.ag.fenced, limit=10)
        self.assertEqual(self.final(tid), ("FAILED", "FENCED", -2))
        self.assertTrue(any("FENCED encerrado" in l for l in logs.output))
        self.run_loop(self.finished(new), limit=15)
        self.assertEqual(self.final(new), ("SUCCESS", "EXIT_OK", 0), "claims voltam depois do heartbeat")

    def test_r12_resultado_local_prevalece_sobre_fenced(self):
        tid = self.db.ticket(self.db.script("sleep 0.5\nexit 0\n"))
        self.start_agent(fence_timeout_s=2.0)
        self.run_loop(self._running(tid))
        self.connection.down = True
        with self.assertLogs("sss_scheduler", "CRITICAL"):
            self.run_loop(lambda: self.ag.fenced, limit=10)
        self.connection.down = False
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.run_loop(lambda: self.finished(tid)() and not self.ag.fenced, limit=10)
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0), "o script terminou antes do fence")

    def test_30_execucoes_encerradas_de_uma_vez_sem_bloquear(self):
        sid = self.db.script("sleep 300\n", max_par=30)
        tids = [self.db.ticket(sid) for _i in range(30)]
        self.start_agent(fence_timeout_s=1.5, max_parallel_jobs=30)
        self.run_loop(lambda: all(self._running(t)() for t in tids), limit=30)
        self.connection.down = True
        _time.sleep(1.6)
        start = _time.monotonic()
        with self.assertLogs("sss_scheduler", "CRITICAL"):
            self.ag._check_fence()
        self.assertLess(_time.monotonic() - start, 1.0, "os 30 pedidos sem esperar nenhum grupo")
        self.assertTrue(all(i.phase == "ENCERRANDO" for i in self.ag.executions.values()))
        self.connection.down = False
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.run_loop(lambda: all(self.finished(t)() for t in tids), limit=30)
        self.assertEqual(set(self.final(t) for t in tids), {("FAILED", "FENCED", -2)})


class TestNodeOffline(tsc._Base):
    """NODE_OFFLINE (README §8.8): marca os tickets de outro agente; nunca com o proprio heartbeat velho nem
    durante a suspensao por salto de relogio (CR-007 D3, CR-008 R-10)."""

    def _other_ticket(self):
        tid = self.db.ticket(self.db.script("echo x\n"))
        self.db.tickets[tid].update(status="RUNNING", agent_id="outro-agente")
        self.db.offline.add(tid)
        return tid

    def test_marca_os_de_outro_agente(self):
        tid = self._other_ticket()
        self.start_agent()
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            self.run_loop(lambda: self.db.tickets[tid]["status"] == "FAILED", limit=10)
        self.assertEqual((self.db.tickets[tid]["status_reason"], self.db.tickets[tid]["updated_by"]),
                         ("NODE_OFFLINE", "SYSTEM:srv-t"))
        self.assertTrue(any("NODE_OFFLINE: ticket(s) %d marcado(s)" % tid in l for l in logs.output))

    def test_heartbeat_proprio_velho_nao_detecta(self):
        self._other_ticket()
        self.start_agent()
        self.ag.last_hb_ok = self.ag.clock() - 25  # fence 40: 25 > 20 (fence / 2)
        self.ag._node_offline()
        self.assertEqual(self.db.node_offline_calls, 0)

    def test_salto_de_relogio_suspende_a_deteccao(self):
        tid = self._other_ticket()
        self.db.offline.clear()
        self.start_agent()
        self.run_loop(lambda: self.db.heartbeats, limit=5)
        self.db.sysdate_offset_s = 120  # o SYSDATE saltou 2 minutos
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.run_loop(lambda: self.ag._node_offline_suspended_until is not None, limit=5)
        self.assertTrue(any("SALTO_RELOGIO" in l for l in logs.output))
        self.db.offline.add(tid)
        calls = self.db.node_offline_calls
        self.run_loop(lambda: False, limit=1)
        self.assertEqual(self.db.node_offline_calls, calls, "suspenso por node_offline_timeout_s")
        self.assertEqual(self.db.tickets[tid]["status"], "RUNNING")

    def test_salto_detectado_na_propria_transacao(self):
        # R-10: o salto chega entre dois heartbeats; a transacao do NODE_OFFLINE nao marca nada.
        tid = self._other_ticket()
        self.db.offline.clear()
        self.start_agent()
        self.run_loop(lambda: self.db.heartbeats, limit=5)
        self.db.offline.add(tid)
        self.ag._clock_ref = (self.db.sysdate() - datetime.timedelta(seconds=300), self.ag.clock())
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.ag._node_offline()
        self.assertEqual(self.db.tickets[tid]["status"], "RUNNING")
        self.assertIsNotNone(self.ag._node_offline_suspended_until)


# ---------------------------------------------------------------------------- F8.4d: parada DRAIN e TERMINATE

import signal as _signal  # noqa: E402
import threading as _threading  # noqa: E402

from sss.platform import os_platform as _plataforma  # noqa: E402


class TestShutdown(tsc._Base):
    """README §8.11: DRAIN aguarda os filhos com o laco normal; TERMINATE encerra todos; os dois terminam com
    PARADO, AGENT_STOP (stop_agent), .stop removido e saida 0."""

    def _stop(self):
        path = _os.path.join(self.work, "sss-srv-t.stop")
        open(path, "w").close()
        return path

    def test_drain_pelo_stop_termina_os_filhos_e_mantem_heartbeat_e_saida(self):
        output_dir = _os.path.join(self.root, "output")
        _os.mkdir(output_dir, 0o755)
        tid = self.db.ticket(self.db.script("echo r > \"$SSS_OUTPUT_DIR/r.txt\"\nsleep 1\necho fim\n"))
        self.start_agent(shutdown_mode="DRAIN", shutdown_grace_s=30, output_dir=output_dir, output_max_bytes=1048576,
                   output_max_files=10)
        self.run_loop(lambda: self.db.tickets[tid]["status"] == "RUNNING" and self.db.tickets[tid]["process_id"])
        new = self.db.ticket(self.db.script("echo novo\n"))
        stop = self._stop()
        heartbeats = len(self.db.heartbeats)
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            code = self.run_loop(lambda: False, limit=20)
        self.assertEqual(code, 0)
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0), "DRAIN deixa o script terminar")
        self.assertEqual(self.db.tickets[new]["status"], "PENDING", "sem claim na drenagem")
        self.assertGreater(len(self.db.heartbeats), heartbeats, "heartbeat mantido")
        self.assertEqual(self.repo_output.rows[tid]["state"], "AVAILABLE", "a saida segue no DRAIN")
        self.assertEqual(self.db.stopped_flag, "DRAIN")
        self.assertFalse(_os.path.exists(stop), ".stop removido")
        self.assertTrue(any("DRAIN: parada pedida" in l for l in logs.output))

    def _assert_stop_before_claim(self, mode):
        """Regressao: com a parada ja pedida, a primeira volta (orquestrador vencido) nao faz claim nem
        desdobro; antes, o pedido so era conferido depois dos ciclos (README §8.11)."""
        tid = self.db.ticket(self.db.script("echo nao devia rodar\n"))
        self.start_agent(shutdown_mode=mode)
        self._stop()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(self.run_loop(lambda: False, limit=20), 0)
        ticket = self.db.tickets[tid]
        self.assertEqual((ticket["status"], ticket["process_id"]), ("PENDING", None), "sem claim depois da parada")
        self.assertIsNone(self.ag.expansion, "sem desdobro depois da parada")
        self.assertEqual(self.db.stopped_flag, mode)

    def test_parada_pedida_antes_da_volta_drain_nao_faz_claim(self):
        self._assert_stop_before_claim("DRAIN")

    def test_parada_pedida_antes_da_volta_terminate_nao_faz_claim(self):
        self._assert_stop_before_claim("TERMINATE")

    def test_drain_com_prazo_vencido_vira_terminate(self):
        tid = self.db.ticket(self.db.script("sleep 300\n"))
        self.start_agent(shutdown_mode="DRAIN", shutdown_grace_s=1)
        self.run_loop(lambda: self.db.tickets[tid]["status"] == "RUNNING" and self.db.tickets[tid]["process_id"])
        pid = self.db.tickets[tid]["process_id"]
        self.stopped.set()
        start = _time.monotonic()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(self.run_loop(lambda: False, limit=20), 0)
        self.assertGreaterEqual(_time.monotonic() - start, 1.0, "aguardou shutdown_grace_s")
        self.assertEqual(self.final(tid), ("FAILED", "SHUTDOWN", -6))
        self.assertFalse(tsc._alive(pid))
        self.assertEqual(self.db.stopped_flag, "DRAIN")

    def test_terminate_pela_flag(self):
        tid = self.db.ticket(self.db.script("sleep 300\n"))
        self.start_agent()
        self.run_loop(lambda: self.db.tickets[tid]["status"] == "RUNNING" and self.db.tickets[tid]["process_id"])
        self.stopped.set()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(self.run_loop(lambda: False, limit=20), 0)
        self.assertEqual((self.final(tid), self.db.stopped_flag), (("FAILED", "SHUTDOWN", -6), "TERMINATE"))


class TestStopSignal(unittest.TestCase):

    def test_sigterm_e_sigint_so_acionam_a_flag(self):
        previous = (_signal.getsignal(_signal.SIGTERM), _signal.getsignal(_signal.SIGINT))
        self.addCleanup(_signal.signal, _signal.SIGTERM, previous[0])
        self.addCleanup(_signal.signal, _signal.SIGINT, previous[1])
        for signal_value in (_signal.SIGTERM, _signal.SIGINT):
            flag = _threading.Event()
            _plataforma.install_stop_handler(flag)
            _os.kill(_os.getpid(), signal_value)
            self.assertTrue(flag.wait(2), signal_value)
