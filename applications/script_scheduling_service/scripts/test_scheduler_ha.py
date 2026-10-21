# -*- coding: utf-8 -*-
"""Agente em alta disponibilidade (F8.4): desdobro dos agendamentos (F8.4b; README §7.4 e §7.5).

Repositorio da agenda em memoria com a semantica do contrato (rowcount pela antiga_data, SKIP LOCKED, ROLLBACK
que desfaz a regra, DuplicateOccurrence), contexto RBAC em memoria e as funcoes reais de recurrence, rbac e
params_compiler. Relogio do banco (agora_banco) e monotonico injetaveis.
"""
import _testenv  # noqa: F401

import copy
import datetime
import json
import logging
import unittest
from unittest import mock

import db_conn
import schedule_expansion
import rbac
import sql_ident
from repo_oracle.scheduler_schedules import DuplicateOccurrence
from test_scheduler_queue import _Erro

AGENTE = "srv-ha"
AGORA = datetime.datetime(2026, 10, 20, 10, 0, 0)
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

    def __init__(self, agenda):
        self.agenda = agenda
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1
        self.agenda._antes = None

    def rollback(self):
        self.rollbacks += 1
        if self.agenda._antes is not None:
            self.agenda.regras, self.agenda.tickets, self.agenda.audit = self.agenda._antes
            self.agenda._antes = None


class _Agenda(object):
    """Contrato do RepoSchedulerSchedules em memoria."""

    def __init__(self):
        self.regras = {}
        self.tickets = {}
        self.audit = []
        self.travadas_por_outro = set()
        self.falhas = []
        self.duplicar = set()
        self.seq = 1000
        self._antes = None
        self.scripts = {}
        self.links = {}

    def _escrever(self, nome):
        if self.falhas and self.falhas[0][0] == nome:
            raise self.falhas.pop(0)[1]
        if self._antes is None:
            self._antes = (copy.deepcopy(self.regras), copy.deepcopy(self.tickets), list(self.audit))

    def due_rules(self, conn, lote, ult_prox=None, ult_id=0):
        vencidas = sorted((r["next_run_at"], r["id"]) for r in self.regras.values()
                          if r["active"] == "Y" and r["next_run_at"] <= AGORA)
        if ult_prox is not None:
            vencidas = [v for v in vencidas if v > (ult_prox, ult_id)]
        return [(rid, prox) for prox, rid in vencidas[:lote]]

    def lock_rule(self, conn, rid):
        r = self.regras.get(rid)
        return rid not in self.travadas_por_outro and r is not None and r["active"] == "Y"

    def load_rule(self, conn, rid):
        if self.falhas and self.falhas[0][0] == "load_rule":
            raise self.falhas.pop(0)[1]
        return copy.deepcopy(self.regras.get(rid))

    def user_login(self, conn, usuario_id):
        return LOGIN

    def script_and_links(self, conn, script_id):
        return copy.deepcopy(self.scripts.get(script_id)), copy.deepcopy(self.links.get(script_id, []))

    def get_ticket_status(self, conn, tid):
        t = self.tickets.get(tid)
        return (t["status"], t["created_at"]) if t else None

    def next_ticket_id(self, conn):
        self.seq += 1
        return self.seq

    def _regra_ok(self, rid, antiga):
        r = self.regras[rid]
        return r["active"] == "Y" and r["next_run_at"] == antiga

    def _ticket(self, regra, tid, ticket, linhas):
        self._escrever("inserir_ticket")
        if (regra["id"], ticket["scheduled_at"]) in self.duplicar:
            raise DuplicateOccurrence("ix_tck_ocor")
        self.tickets[tid] = dict(ticket, id=tid, status="PENDING", schedule_id=regra["id"], created_at=AGORA,
                                 created_by="SYSTEM:%s" % AGENTE, respostas=list(linhas))

    def reserve_and_create_ticket(self, conn, regra, antiga, nova, tid, ticket, linhas, agente_id):
        self._escrever("reservar")
        if not self._regra_ok(regra["id"], antiga):
            return False
        self.regras[regra["id"]].update(next_run_at=nova, last_run_at=AGORA, last_ticket_id=tid)
        self._ticket(regra, tid, ticket, linhas)
        return True

    def complete_with_ticket(self, conn, regra, antiga, tid, ticket, linhas, agente_id):
        self._escrever("complete")
        if not self._regra_ok(regra["id"], antiga):
            return False
        self.regras[regra["id"]].update(active="N", pause_reason="COMPLETED", last_run_at=AGORA,
                                        last_ticket_id=tid, updated_by="SYSTEM:%s" % agente_id)
        self._ticket(regra, tid, ticket, linhas)
        self.audit.append((regra["id"], "pause_reason: COMPLETED"))
        return True

    def complete_without_ticket(self, conn, rid, antiga, agente_id):
        self._escrever("complete")
        if not self._regra_ok(rid, antiga):
            return False
        self.regras[rid].update(active="N", pause_reason="COMPLETED", updated_by="SYSTEM:%s" % agente_id)
        self.audit.append((rid, "pause_reason: COMPLETED"))
        return True

    def advance_without_ticket(self, conn, rid, antiga, nova):
        self._escrever("avancar")
        if not self._regra_ok(rid, antiga):
            return False
        self.regras[rid]["next_run_at"] = nova
        return True

    def pause(self, conn, rid, antiga, motivo, detalhe, agente_id):
        self._escrever("pause")
        if not self._regra_ok(rid, antiga):
            return False
        self.regras[rid].update(active="N", pause_reason=motivo, updated_by="SYSTEM:%s" % agente_id)
        self.audit.append((rid, "pause_reason: %s%s" % (motivo, "; " + detalhe if detalhe else "")))
        return True

    def pause_cron_error(self, conn, regra, antiga, tid, ticket, linhas, detalhe, agente_id):
        self._escrever("pause")
        if not self._regra_ok(regra["id"], antiga):
            return False
        r = self.regras[regra["id"]]
        r.update(active="N", pause_reason="INVALID_CRON", updated_by="SYSTEM:%s" % agente_id)
        if tid is not None:
            r.update(last_run_at=AGORA, last_ticket_id=tid)
            self._ticket(regra, tid, ticket, linhas)
        self.audit.append((regra["id"], "pause_reason: INVALID_CRON"))
        return True

    def pause_internal_error(self, conn, rid, detalhe, agente_id):
        self._escrever("pause_internal_error")
        r = self.regras[rid]
        if r["active"] != "Y":
            return False
        r.update(active="N", pause_reason="INTERNAL_ERROR", updated_by="SYSTEM:%s" % agente_id)
        self.audit.append((rid, "pause_reason: INTERNAL_ERROR; %s" % detalhe))
        return True


class _Fila(object):
    """contexto_execucao do RepoSchedulerQueue em memoria (o mesmo ctx RBAC da web)."""

    def __init__(self):
        self.usuario = {"user_id": 7, "login": LOGIN, "profile_id": 2, "usuario_ativo": "Y", "perfil_ativo": "Y",
                        "is_admin": "N", "perm_version": 1, "features": ["EXEC_SCRIPT"], "environments": ["PRD"],
                        "scripts": [3]}
        self.script = {"id": 3, "name": "carga", "interpreter": "SH", "path_file": "/opt/x/carga.sh", "active": "Y",
                       "timeout_s": 600}
        self.ambiente = {"id": 1, "name": "PRD", "description": "Producao", "connection": None, "active": "Y"}
        self.homologacoes = frozenset([1])

    def execution_context(self, conn, ticket):
        return {"script": dict(self.script), "environment": dict(self.ambiente), "homologacoes": self.homologacoes,
                "ctx": rbac.user_context(dict(self.usuario)) if self.usuario else None, "agendamento": None}


def _vinculo():
    return {"parameter_id": 11, "id": 11, "code": "data_ref", "param_flag": "--data", "label": "Data",
            "description": None, "component_type": "TEXT", "options_json": None, "default_value": None,
            "validation_regex": None, "sensitive": "N", "active": "Y", "sort_order": 1, "required": "Y",
            "default_value_override": None, "script_id": 3}


class _Base(unittest.TestCase):

    def setUp(self):
        self.agenda = _Agenda()
        self.fila = _Fila()
        self.agenda.scripts[3] = {"id": 3, "name": "carga", "interpreter": "SH", "path_file": "/opt/x/carga.sh",
                                  "param_type": "NAMED", "max_parallel_env": 2, "timeout_s": 600, "active": "Y"}
        self.agenda.links[3] = [_vinculo()]
        self.conn = _Conn(self.agenda)
        self.now = AGORA
        p = mock.patch.object(db_conn, "db_now", lambda conn: self.now)
        p.start()
        self.addCleanup(p.stop)
        self.monotonico = [0.0]
        self.cfg = _Cfg()
        self.horizonte = None

    def des(self):
        return schedule_expansion.Expansion(self.agenda, self.fila, AGENTE, self.cfg, lambda: self.monotonico[0],
                                 horizonte_dias=self.horizonte)

    def regra(self, rid=1, **kw):
        base = {"id": rid, "name": "R%d" % rid, "script_id": 3, "environment": "PRD", "user_id": 7, "priority": 2,
                "recurrence_type": "DAILY", "cron_expression": None, "run_time": "09:55", "week_days": None,
                "month_day": None, "params_json": json.dumps({"data_ref": "2026-10-20"}),
                "start_date": datetime.datetime(2026, 1, 1), "end_date": None,
                "next_run_at": datetime.datetime(2026, 10, 20, 9, 55), "last_run_at": None,
                "last_ticket_id": None, "pause_reason": None, "active": "Y"}
        base.update(kw)
        self.agenda.regras[rid] = base
        return base

    def process(self, rid=1):
        return self.des().process(self.conn, rid)


class TestDesdobro(_Base):

    def test_ticket_com_ocorrencia_snapshot_v4_e_um_commit(self):
        self.regra()
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            self.assertEqual(self.process(), "TICKET")
        self.assertEqual(self.conn.commits, 1, "COMMIT unico por regra")
        r = self.agenda.regras[1]
        t = self.agenda.tickets[r["last_ticket_id"]]
        self.assertEqual(r["next_run_at"], datetime.datetime(2026, 10, 21, 9, 55))
        self.assertEqual((t["scheduled_at"], t["requested_by"], t["priority"], t["created_by"]),
                         (datetime.datetime(2026, 10, 20, 9, 55), LOGIN, 2, "SYSTEM:" + AGENTE),
                         "scheduled_at = ocorrencia coberta (R-27, R-03)")
        snap = json.loads(t["submitted_params"])
        self.assertEqual((snap["version"], snap["path_file"], snap["args"]), (4, "/opt/x/carga.sh", ["--data", "2026-10-20"]))
        self.assertNotIn("pasta_base", snap)
        self.assertEqual(t["respostas"], [{"parameter_id": 11, "answer_value": "2026-10-20"}])
        self.assertTrue(any("agendamento 1: ticket %d gerado" % t["id"] in l for l in logs.output))

    def test_corrida_e_outro_agente(self):
        self.regra()
        self.agenda.reserve_and_create_ticket = lambda *a: False
        self.assertEqual(self.process(), "CORRIDA")
        self.assertEqual((self.agenda.tickets, self.conn.commits), ({}, 0))
        self.agenda.travadas_por_outro.add(1)
        self.assertEqual(self.process(), "OUTRO_AGENTE")

    def test_pausas_pelo_rbac_com_a_traducao_unica(self):
        casos = (("usuario_ativo", "N", "USER_INACTIVE"), ("perfil_ativo", "N", "NO_PERMISSION"),
                 ("scripts", [], "NO_PERMISSION"), ("environments", [], "NO_PERMISSION"),
                 ("features", [], "NO_PERMISSION"))
        for i, (campo, valor, motivo) in enumerate(casos, 1):
            self.setUp()
            self.regra(i)
            self.fila.usuario[campo] = valor
            with self.assertLogs("sss_scheduler", "WARNING"):
                self.assertEqual(self.process(i), "PAUSADA", campo)
            self.assertEqual(self.agenda.regras[i]["pause_reason"], motivo, campo)
            self.assertEqual(self.agenda.regras[i]["updated_by"], "SYSTEM:" + AGENTE)
        for chave, motivo in ((("script", "active"), "SCRIPT_INACTIVE"), (("ambiente", "active"), "ENVIRONMENT_INACTIVE")):
            self.setUp()
            self.regra()
            getattr(self.fila, chave[0])[chave[1]] = "N"
            with self.assertLogs("sss_scheduler", "WARNING"):
                self.process()
            self.assertEqual(self.agenda.regras[1]["pause_reason"], motivo)

    def test_r33_todo_motivo_do_rbac_cabe_na_ck(self):
        aceitos = sql_ident.TABLES["schedules"]["cks"]["pause"]["expr"]
        for nome in dir(rbac.Reason):
            if nome.startswith("_") or nome == "OK":
                continue
            self.assertIn("'%s'" % rbac.pause_reason_for(getattr(rbac.Reason, nome)), aceitos, nome)

    def test_prioridade_rebaixada(self):
        self.regra(priority=1)
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.process()
        t = self.agenda.tickets[self.agenda.regras[1]["last_ticket_id"]]
        self.assertEqual((t["priority"], self.agenda.regras[1]["priority"]), (2, 1), "a regra nao muda")
        self.assertTrue(any("PRIORIDADE_REBAIXADA" in l for l in logs.output))
        self.setUp()
        self.regra(priority=1)
        self.fila.usuario["is_admin"] = "Y"
        self.process()
        self.assertEqual(self.agenda.tickets[self.agenda.regras[1]["last_ticket_id"]]["priority"], 1)

    def test_sobreposicao_avanca_sem_ticket_e_preso(self):
        self.regra(last_ticket_id=50)
        self.agenda.tickets[50] = {"status": "RUNNING", "created_at": AGORA - datetime.timedelta(minutes=5)}
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            self.assertEqual(self.process(), "AVANCADA")
        r = self.agenda.regras[1]
        self.assertEqual((r["last_ticket_id"], r["next_run_at"], r["last_run_at"]),
                         (50, datetime.datetime(2026, 10, 21, 9, 55), None), "R-05: sem mexer no ultimo ticket")
        self.assertTrue(any("SKIP_OVERLAP: o ticket 50 ainda esta RUNNING" in l for l in logs.output))
        self.setUp()
        self.regra(last_ticket_id=50)
        self.agenda.tickets[50] = {"status": "PENDING", "created_at": AGORA - datetime.timedelta(hours=2)}
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.process()
        self.assertTrue(any("SKIP_OVERLAP_PRESO: o ticket 50" in l for l in logs.output), "600 + 180 s < 2 h")
        for livre in (None, "SUCCESS"):
            self.setUp()
            self.regra(last_ticket_id=50)
            if livre:
                self.agenda.tickets[50] = {"status": livre, "created_at": AGORA}
            self.assertEqual(self.process(), "TICKET", "inexistente (purgado) ou terminal e livre")

    def test_misfire_run_once_e_skip(self):
        tres_dias = datetime.datetime(2026, 10, 17, 9, 55)
        self.regra(next_run_at=tres_dias)
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.assertEqual(self.process(), "TICKET")
        self.assertEqual(len(self.agenda.tickets), 1, "RUN_ONCE: um ticket apos o downtime")
        self.assertEqual(list(self.agenda.tickets.values())[0]["scheduled_at"], datetime.datetime(2026, 10, 20, 9, 55))
        self.assertTrue(any("MISFIRE: 3 ocorrencia(s) perdida(s)" in l for l in logs.output))
        self.setUp()
        self.cfg = _Cfg(misfire_policy="SKIP")
        self.regra(next_run_at=tres_dias, run_time="09:00")
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(self.process(), "AVANCADA")
        self.assertEqual((self.agenda.tickets, self.agenda.regras[1]["next_run_at"]),
                         ({}, datetime.datetime(2026, 10, 21, 9, 0)))
        # R-21: SKIP com a vencida mais recente dentro da tolerancia gera o ticket dela.
        self.setUp()
        self.cfg = _Cfg(misfire_policy="SKIP")
        self.regra(next_run_at=tres_dias)
        with self.assertLogs("sss_scheduler", "INFO"):
            self.assertEqual(self.process(), "TICKET")

    def test_perdidas_dentro_da_tolerancia_em_info(self):
        self.regra(recurrence_type="CRON", cron_expression="* * * * *", run_time=None,
                   next_run_at=AGORA - datetime.timedelta(minutes=3))
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            self.process()
        self.assertTrue(any("ocorrencia(s) coalescida(s) dentro da tolerancia" in l for l in logs.output))
        self.assertFalse(any("WARNING" in l for l in logs.output))

    def test_unica_conclui_com_e_sem_ticket(self):
        self.regra(recurrence_type="ONCE", run_time=None)
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            self.assertEqual(self.process(), "CONCLUIDA_COM_TICKET")
        r = self.agenda.regras[1]
        self.assertEqual((r["active"], r["pause_reason"], r["next_run_at"]),
                         ("N", "COMPLETED", datetime.datetime(2026, 10, 20, 9, 55)), "proxima_execucao mantida (D1)")
        self.assertEqual(len(self.agenda.tickets), 1)
        self.assertEqual(self.agenda.audit, [(1, "pause_reason: COMPLETED")])
        self.assertFalse(any("WARNING" in l for l in logs.output), "conclusao e INFO")
        self.setUp()
        self.cfg = _Cfg(misfire_policy="SKIP")
        self.regra(recurrence_type="ONCE", run_time=None, next_run_at=datetime.datetime(2026, 10, 19, 9, 0))
        with self.assertLogs("sss_scheduler", "INFO"):
            self.assertEqual(self.process(), "CONCLUIDA_SEM_TICKET")
        self.assertEqual((self.agenda.tickets, self.agenda.regras[1]["last_ticket_id"]), ({}, None))

    def test_data_fim_conclui_com_o_ticket_da_ocorrencia(self):
        self.regra(end_date=datetime.datetime(2026, 10, 20, 23, 59))
        self.assertEqual(self.process(), "CONCLUIDA_COM_TICKET")
        self.assertEqual(self.agenda.regras[1]["pause_reason"], "COMPLETED")

    def test_sobreposicao_numa_regra_que_conclui(self):
        self.regra(recurrence_type="ONCE", run_time=None, last_ticket_id=50)
        self.agenda.tickets[50] = {"status": "RUNNING", "created_at": AGORA}
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            self.assertEqual(self.process(), "CONCLUIDA_SEM_TICKET")
        self.assertTrue(any("SKIP_OVERLAP: regra concluida sem ticket; ocorrencias perdidas: 1" in l
                            for l in logs.output))
        self.assertEqual(len(self.agenda.tickets), 1)

    def test_param_invalido_e_cron_invalido(self):
        self.regra(params_json=json.dumps({}))
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(self.process(), "PAUSADA")
        self.assertEqual(self.agenda.regras[1]["pause_reason"], "INVALID_PARAM")
        detalhe = self.agenda.audit[0][1]
        self.assertTrue(detalhe.startswith("pause_reason: INVALID_PARAM; data_ref: "), detalhe)
        self.setUp()
        self.regra(params_json="{nao json")
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.process()
        self.assertEqual(self.agenda.regras[1]["pause_reason"], "INVALID_PARAM")
        self.setUp()
        self.regra(recurrence_type="CRON", cron_expression="99 * * * *", run_time=None)
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(self.process(), "PAUSADA")
        self.assertEqual((self.agenda.regras[1]["pause_reason"], self.agenda.tickets), ("INVALID_CRON", {}))

    def test_r19_cron_sem_proxima_no_horizonte(self):
        # 29/02 so em 2028; com horizonte de 30 dias (injetado), a proxima nao existe.
        self.horizonte = 30
        self.regra(recurrence_type="CRON", cron_expression="0 10 29 2 *", run_time=None,
                   next_run_at=datetime.datetime(2026, 10, 20, 9, 55))
        self.agenda.regras[1]["cron_expression"] = "55 9 * * *"
        with mock.patch("recurrence.next_run", side_effect=schedule_expansion.recurrence.CronError("sem ocorrencia")):
            with self.assertLogs("sss_scheduler", "WARNING"):
                self.assertEqual(self.process(), "CRON_INVALIDO_COM_TICKET")
        r = self.agenda.regras[1]
        self.assertEqual((r["pause_reason"], r["next_run_at"]), ("INVALID_CRON", datetime.datetime(2026, 10, 20, 9, 55)))
        self.assertEqual(len(self.agenda.tickets), 1, "o ticket da vencida e gerado antes de pausar")
        self.setUp()
        self.regra(recurrence_type="CRON", cron_expression="55 9 * * *", run_time=None, last_ticket_id=50)
        self.agenda.tickets[50] = {"status": "RUNNING", "created_at": AGORA}
        with mock.patch("recurrence.next_run", side_effect=schedule_expansion.recurrence.CronError("sem ocorrencia")):
            with self.assertLogs("sss_scheduler", "WARNING"):
                self.assertEqual(self.process(), "INVALID_CRON")
        self.assertEqual(len(self.agenda.tickets), 1, "sobreposicao: sem ticket novo")

    def test_r31_ocorrencia_duplicada_avanca_numa_nova_transacao(self):
        self.regra()
        self.agenda.duplicar.add((1, datetime.datetime(2026, 10, 20, 9, 55)))
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.assertEqual(self.process(), "OCORRENCIA_DUPLICADA")
        r = self.agenda.regras[1]
        self.assertEqual((r["next_run_at"], r["last_ticket_id"]), (datetime.datetime(2026, 10, 21, 9, 55), None))
        self.assertEqual((self.conn.rollbacks, self.conn.commits), (1, 1))
        self.assertTrue(any("OCORRENCIA_DUPLICADA" in l for l in logs.output))
        self.assertEqual(self.agenda.due_rules(self.conn, 50), [], "nao e reprocessada no ciclo seguinte")

    def test_r22_erro_de_banco_tres_vezes_e_erro_interno(self):
        self.regra()
        d = self.des()
        espaco = _Erro("ORA-01653: unable to extend table")
        for n in (1, 2):
            self.agenda.falhas = [("inserir_ticket", espaco)]
            with self.assertLogs("sss_scheduler", "WARNING") as logs:
                self.assertEqual(d.process(self.conn, 1), "ERRO_BANCO")
            self.assertTrue(any("DESDOBRO_ERRO_BANCO: ORA-01653 (falha %d de 3 seguidas)" % n in l for l in logs.output))
            self.assertEqual((self.agenda.regras[1]["active"], self.agenda.tickets), ("Y", {}), "sem pausar")
        self.agenda.falhas = [("inserir_ticket", espaco)]
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(d.process(self.conn, 1), "INTERNAL_ERROR")
        self.assertEqual(self.agenda.regras[1]["pause_reason"], "INTERNAL_ERROR")
        self.assertIn("3 falhas seguidas de banco (ORA-01653)", self.agenda.audit[-1][1])
        # Sucesso zera o contador.
        self.setUp()
        self.regra()
        d = self.des()
        self.agenda.falhas = [("inserir_ticket", espaco)]
        with self.assertLogs("sss_scheduler", "WARNING"):
            d.process(self.conn, 1)
        self.assertEqual(d.process(self.conn, 1), "TICKET")
        self.assertEqual(d.falhas, {})
        # Excecao que nao e de banco pausa na primeira, em transacao separada (R-08).
        self.setUp()
        self.regra()
        self.agenda.falhas = [("load_rule", ValueError("dado incoerente"))]
        with self.assertLogs("sss_scheduler", "ERROR"):
            self.assertEqual(self.process(), "INTERNAL_ERROR")
        self.assertEqual(self.agenda.regras[1]["pause_reason"], "INTERNAL_ERROR")
        self.assertEqual(self.agenda.audit[-1][1], "pause_reason: INTERNAL_ERROR; ValueError")

    def test_pausa_que_falha_ignora_a_regra_no_ciclo(self):
        self.regra(1)
        self.regra(2, next_run_at=datetime.datetime(2026, 10, 20, 9, 56))
        self.agenda.falhas = [("load_rule", ValueError("x")), ("pause_internal_error", ValueError("y"))]
        with self.assertLogs("sss_scheduler", "ERROR"):
            stats = self.des().run(self.conn)
        self.assertEqual(stats["tickets"], 1, "a regra 2 segue")
        self.assertEqual(self.agenda.regras[1]["active"], "Y")

    def test_paginacao_e_orcamento(self):
        for i in range(1, 6):
            self.regra(i, next_run_at=datetime.datetime(2026, 10, 20, 9, 50 + i))
        self.cfg = _Cfg(schedule_batch_size=2)
        paginas = []
        original = self.agenda.due_rules
        self.agenda.due_rules = lambda *a: paginas.append(a[2:]) or original(*a)
        self.assertEqual(self.des().run(self.conn)["tickets"], 5)
        self.assertEqual(len(paginas), 3, "2 + 2 + 1")
        self.assertEqual(paginas[0], (None, 0))
        self.assertEqual(paginas[1], (datetime.datetime(2026, 10, 20, 9, 52), 2))
        # Orcamento (heartbeat / 2 = 5 s) estourado: o resto fica para o proximo ciclo.
        self.setUp()
        for i in range(1, 6):
            self.regra(i, next_run_at=datetime.datetime(2026, 10, 20, 9, 50 + i))
        d = self.des()
        original_proc = d.process

        def lento(conn, rid):
            self.monotonico[0] += 2.0
            return original_proc(conn, rid)
        d.process = lento
        self.assertEqual(d.run(self.conn)["tickets"], 3)
        self.assertEqual(sum(1 for r in self.agenda.regras.values() if r["last_ticket_id"]), 3)

    def test_continuar_falso_interrompe_entre_regras(self):
        self.regra(1)
        self.regra(2)
        self.assertEqual(self.des().run(self.conn, continuar=lambda: False)["regras"], 0)


if __name__ == "__main__":
    unittest.main()


import os  # noqa: E402


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestDesdobroOracle(unittest.TestCase):
    """Desdobro real (repositorios Oracle) com massa propria: ticket da regra vencida e pausa INVALID_PARAM."""

    @classmethod
    def setUpClass(cls):
        import test_repo_contract as trc
        cls.trc = trc
        cls.contrato = trc._OracleContrato
        cls.contrato.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.contrato.tearDownClass.__func__(cls)

    def obter_repo(self, nome):
        return self.contrato.obter_repo(self, nome)

    def _limpar_massa(self):
        return self.contrato._limpar_massa(self)

    def setUp(self):
        from repo_oracle.scheduler_schedules import RepoSchedulerSchedules
        from repo_oracle.scheduler_queue import RepoSchedulerQueue
        self.contrato.setUp(self)
        self._massa = self.trc._Massa(self.obter_repo)
        self.c = self._massa.cenario()
        cat, self.rbac = self.obter_repo("catalog"), self.obter_repo("rbac")
        self.cat = cat
        funcs = [f["id"] for f in self.rbac.features_list() if f["code"] == "EXEC_SCRIPT"]
        self.rbac.matrix_save(self.c["perfil"]["id"], funcs, [self.c["amb1"]["id"]], [self.c["scr"]["id"]],
                                ator=self._massa.ator)
        self.agente = "tst-ha-%s" % self._massa.suf
        self.des = schedule_expansion.Expansion(RepoSchedulerSchedules(cat._owner, cat._prefixo),
                                     RepoSchedulerQueue(cat._owner, cat._prefixo), self.agente, _Cfg(),
                                     lambda: 0.0)
        self.conn = cat._obter_conexao()
        self.addCleanup(self.conn.close)

    def tearDown(self):
        self.conn.rollback()
        cur = self.conn.cursor()
        agd, aud, tck = (self.cat.qualify_table(t) for t in ("schedules", "audit", "tickets"))
        for rid in self._massa.criados["schedules"]:
            cur.execute("SELECT id FROM " + tck + " WHERE schedule_id = :id", id=rid)
            for (tid,) in cur.fetchall():
                self._massa.anotar("tickets", tid)
            cur.execute("DELETE FROM " + aud + " WHERE entity = 'tbsss_schedules' AND entity_id = :id", id=rid)
        self.conn.commit()
        self.rbac.matrix_save(self.c["perfil"]["id"], [], [], [], ator=self._massa.ator)
        self.contrato.tearDown(self)

    def _rule(self, respostas):
        proxima = datetime.datetime.now().replace(second=0, microsecond=0) - datetime.timedelta(minutes=2)
        return self._massa.agendamento(self.c["scr"]["id"], self.c["amb1"]["name"], self.c["u1"]["id"],
                                       recurrence_type="DAILY", run_time=proxima.strftime("%H:%M"),
                                       start_date=proxima - datetime.timedelta(days=1), next_run_at=proxima,
                                       params_json=json.dumps(respostas))

    def test_ticket_real_e_pausa_param_invalido(self):
        prm_a = self.c["prm_a"]["code"]
        ok = self._rule({prm_a: "valor-a"})
        ruim = self._rule({})
        with self.assertLogs("sss_scheduler", "INFO"):
            self.assertEqual(self.des.process(self.conn, ok["id"]), "TICKET")
            self.assertEqual(self.des.process(self.conn, ruim["id"]), "PAUSADA")
        agd = self.obter_repo("schedules")
        r_ok, r_ruim = agd.get(ok["id"]), agd.get(ruim["id"])
        self.assertGreater(r_ok["next_run_at"], ok["next_run_at"])
        t = self.obter_repo("tickets").get(r_ok["last_ticket_id"])
        self.assertEqual((t["schedule_id"], t["requested_by"], t["created_by"], t["scheduled_at"], t["status"]),
                         (ok["id"], self.c["login"], "SYSTEM:%s" % self.agente, ok["next_run_at"], "PENDING"))
        snap = json.loads(t["submitted_params"])
        self.assertEqual((snap["version"], snap["path_file"]), (4, self.c["scr"]["path_file"]))
        self.assertEqual([x["answer_value"] for x in self.obter_repo("tickets").answers(t["id"])], ["valor-a"])
        self.assertEqual((r_ruim["active"], r_ruim["pause_reason"], r_ruim["updated_by"]),
                         ("N", "INVALID_PARAM", "SYSTEM:%s" % self.agente))
        # A regra ja avancada nao e mais vencida; a pausada tambem nao.
        vencidas = [rid for rid, _p in self.des.agenda.due_rules(self.conn, 1000)]
        self.conn.rollback()
        self.assertNotIn(ok["id"], vencidas)
        self.assertNotIn(ruim["id"], vencidas)


# ---------------------------------------------------------------------------- F8.4c: fencing e NODE_OFFLINE

import os as _os  # noqa: E402
import time as _time  # noqa: E402

import test_scheduler_claim as tsc  # noqa: E402


class TestFencing(tsc._Base):
    """Self-fencing (README §8.9) com o laco real, scripts /bin/sh e o banco em memoria do test_scheduler_claim."""

    def _rodando(self, tid):
        return lambda: self.banco.tickets[tid]["status"] == "RUNNING" and self.banco.tickets[tid]["process_id"]

    def test_fence_no_limiar_encerra_e_recupera_como_fenced(self):
        tid = self.banco.ticket(self.banco.script("sleep 300\n"))
        self.subir(fence_timeout_s=1.5)
        self.rodar(self._rodando(tid))
        pid = self.banco.tickets[tid]["process_id"]
        self.conexao.fora = True
        inicio = _time.monotonic()
        with self.assertLogs("sss_scheduler", "CRITICAL") as logs:
            self.rodar(lambda: self.ag.cercado, limite=10)
        self.assertGreaterEqual(_time.monotonic() - inicio, 1.0, "nao antes do limiar")
        self.assertTrue(any("FENCED: sem heartbeat confirmado" in l for l in logs.output))
        # Em modo cercado: sem claims nem desdobro, mesmo com ticket novo na fila.
        novo = self.banco.ticket(self.banco.script("echo novo\n"))
        self.rodar(lambda: not tsc._vivo(pid), limite=10)
        self.assertFalse(tsc._vivo(pid), "o grupo foi encerrado no fence")
        self.assertEqual(self.banco.tickets[novo]["status"], "PENDING")
        self.conexao.fora = False
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.rodar(lambda: self.terminado(tid)() and not self.ag.cercado, limite=10)
        self.assertEqual(self.final(tid), ("FAILED", "FENCED", -2))
        self.assertTrue(any("FENCED encerrado" in l for l in logs.output))
        self.rodar(self.terminado(novo), limite=15)
        self.assertEqual(self.final(novo), ("SUCCESS", "EXIT_OK", 0), "claims voltam depois do heartbeat")

    def test_r12_resultado_local_prevalece_sobre_fenced(self):
        tid = self.banco.ticket(self.banco.script("sleep 0.5\nexit 0\n"))
        self.subir(fence_timeout_s=2.0)
        self.rodar(self._rodando(tid))
        self.conexao.fora = True
        with self.assertLogs("sss_scheduler", "CRITICAL"):
            self.rodar(lambda: self.ag.cercado, limite=10)
        self.conexao.fora = False
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.rodar(lambda: self.terminado(tid)() and not self.ag.cercado, limite=10)
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0), "o script terminou antes do fence")

    def test_30_execucoes_encerradas_de_uma_vez_sem_bloquear(self):
        sid = self.banco.script("sleep 300\n", max_par=30)
        tids = [self.banco.ticket(sid) for _i in range(30)]
        self.subir(fence_timeout_s=1.5, max_parallel_jobs=30)
        self.rodar(lambda: all(self._rodando(t)() for t in tids), limite=30)
        self.conexao.fora = True
        _time.sleep(1.6)
        inicio = _time.monotonic()
        with self.assertLogs("sss_scheduler", "CRITICAL"):
            self.ag._conferir_fence()
        self.assertLess(_time.monotonic() - inicio, 1.0, "os 30 pedidos sem esperar nenhum grupo")
        self.assertTrue(all(i.phase == "ENCERRANDO" for i in self.ag.execucoes.values()))
        self.conexao.fora = False
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.rodar(lambda: all(self.terminado(t)() for t in tids), limite=30)
        self.assertEqual(set(self.final(t) for t in tids), {("FAILED", "FENCED", -2)})


class TestNodeOffline(tsc._Base):
    """NODE_OFFLINE (README §8.8): marca os tickets de outro agente; nunca com o proprio heartbeat velho nem
    durante a suspensao por salto de relogio (CR-007 D3, CR-008 R-10)."""

    def _ticket_de_outro(self):
        tid = self.banco.ticket(self.banco.script("echo x\n"))
        self.banco.tickets[tid].update(status="RUNNING", agent_id="outro-agente")
        self.banco.offline.add(tid)
        return tid

    def test_marca_os_de_outro_agente(self):
        tid = self._ticket_de_outro()
        self.subir()
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            self.rodar(lambda: self.banco.tickets[tid]["status"] == "FAILED", limite=10)
        self.assertEqual((self.banco.tickets[tid]["status_reason"], self.banco.tickets[tid]["updated_by"]),
                         ("NODE_OFFLINE", "SYSTEM:srv-t"))
        self.assertTrue(any("NODE_OFFLINE: ticket(s) %d marcado(s)" % tid in l for l in logs.output))

    def test_heartbeat_proprio_velho_nao_detecta(self):
        self._ticket_de_outro()
        self.subir()
        self.ag.ultimo_hb_ok = self.ag.relogio() - 25  # fence 40: 25 > 20 (fence / 2)
        self.ag._node_offline()
        self.assertEqual(self.banco.node_offline_chamadas, 0)

    def test_salto_de_relogio_suspende_a_deteccao(self):
        tid = self._ticket_de_outro()
        self.banco.offline.clear()
        self.subir()
        self.rodar(lambda: self.banco.heartbeats, limite=5)
        self.banco.sysdate_deslocamento_s = 120  # o SYSDATE saltou 2 minutos
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.rodar(lambda: self.ag._node_offline_suspenso_ate is not None, limite=5)
        self.assertTrue(any("SALTO_RELOGIO" in l for l in logs.output))
        self.banco.offline.add(tid)
        chamadas = self.banco.node_offline_chamadas
        self.rodar(lambda: False, limite=1)
        self.assertEqual(self.banco.node_offline_chamadas, chamadas, "suspenso por node_offline_timeout_s")
        self.assertEqual(self.banco.tickets[tid]["status"], "RUNNING")

    def test_salto_detectado_na_propria_transacao(self):
        # R-10: o salto chega entre dois heartbeats; a transacao do NODE_OFFLINE nao marca nada.
        tid = self._ticket_de_outro()
        self.banco.offline.clear()
        self.subir()
        self.rodar(lambda: self.banco.heartbeats, limite=5)
        self.banco.offline.add(tid)
        self.ag._ref_relogio = (self.banco.sysdate() - datetime.timedelta(seconds=300), self.ag.relogio())
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.ag._node_offline()
        self.assertEqual(self.banco.tickets[tid]["status"], "RUNNING")
        self.assertIsNotNone(self.ag._node_offline_suspenso_ate)


# ---------------------------------------------------------------------------- F8.4d: parada DRAIN e TERMINATE

import signal as _signal  # noqa: E402
import threading as _threading  # noqa: E402

import os_platform as _plataforma  # noqa: E402


class TestParada(tsc._Base):
    """README §8.11: DRAIN aguarda os filhos com o laco normal; TERMINATE encerra todos; os dois terminam com
    PARADO, AGENT_STOP (encerrar_agente), .stop removido e saida 0."""

    def _stop(self):
        caminho = _os.path.join(self.work, "sss-srv-t.stop")
        open(caminho, "w").close()
        return caminho

    def test_drain_pelo_stop_termina_os_filhos_e_mantem_heartbeat_e_saida(self):
        output_dir = _os.path.join(self.raiz, "output")
        _os.mkdir(output_dir, 0o755)
        tid = self.banco.ticket(self.banco.script("echo r > \"$SSS_OUTPUT_DIR/r.txt\"\nsleep 1\necho fim\n"))
        self.subir(shutdown_mode="DRAIN", shutdown_grace_s=30, output_dir=output_dir, output_max_bytes=1048576,
                   output_max_files=10)
        self.rodar(lambda: self.banco.tickets[tid]["status"] == "RUNNING" and self.banco.tickets[tid]["process_id"])
        novo = self.banco.ticket(self.banco.script("echo novo\n"))
        stop = self._stop()
        heartbeats = len(self.banco.heartbeats)
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            codigo = self.rodar(lambda: False, limite=20)
        self.assertEqual(codigo, 0)
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0), "DRAIN deixa o script terminar")
        self.assertEqual(self.banco.tickets[novo]["status"], "PENDING", "sem claim na drenagem")
        self.assertGreater(len(self.banco.heartbeats), heartbeats, "heartbeat mantido")
        self.assertEqual(self.repo_saida.linhas[tid]["state"], "AVAILABLE", "a saida segue no DRAIN")
        self.assertEqual(self.banco.encerrou, "DRAIN")
        self.assertFalse(_os.path.exists(stop), ".stop removido")
        self.assertTrue(any("DRAIN: parada pedida" in l for l in logs.output))

    def test_drain_com_prazo_vencido_vira_terminate(self):
        tid = self.banco.ticket(self.banco.script("sleep 300\n"))
        self.subir(shutdown_mode="DRAIN", shutdown_grace_s=1)
        self.rodar(lambda: self.banco.tickets[tid]["status"] == "RUNNING" and self.banco.tickets[tid]["process_id"])
        pid = self.banco.tickets[tid]["process_id"]
        self.parada.set()
        inicio = _time.monotonic()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(self.rodar(lambda: False, limite=20), 0)
        self.assertGreaterEqual(_time.monotonic() - inicio, 1.0, "aguardou shutdown_grace_s")
        self.assertEqual(self.final(tid), ("FAILED", "SHUTDOWN", -6))
        self.assertFalse(tsc._vivo(pid))
        self.assertEqual(self.banco.encerrou, "DRAIN")

    def test_terminate_pela_flag(self):
        tid = self.banco.ticket(self.banco.script("sleep 300\n"))
        self.subir()
        self.rodar(lambda: self.banco.tickets[tid]["status"] == "RUNNING" and self.banco.tickets[tid]["process_id"])
        self.parada.set()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(self.rodar(lambda: False, limite=20), 0)
        self.assertEqual((self.final(tid), self.banco.encerrou), (("FAILED", "SHUTDOWN", -6), "TERMINATE"))


class TestSinalDeParada(unittest.TestCase):

    def test_sigterm_e_sigint_so_acionam_a_flag(self):
        anteriores = (_signal.getsignal(_signal.SIGTERM), _signal.getsignal(_signal.SIGINT))
        self.addCleanup(_signal.signal, _signal.SIGTERM, anteriores[0])
        self.addCleanup(_signal.signal, _signal.SIGINT, anteriores[1])
        for sinal in (_signal.SIGTERM, _signal.SIGINT):
            flag = _threading.Event()
            _plataforma.install_stop_handler(flag)
            _os.kill(_os.getpid(), sinal)
            self.assertTrue(flag.wait(2), sinal)
