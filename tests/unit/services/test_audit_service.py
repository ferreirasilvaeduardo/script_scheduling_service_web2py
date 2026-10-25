# -*- coding: utf-8 -*-
"""Testes de audit_service.py e agents_service.py (F6.1) sobre o backend FAKE com relogio injetado."""
from tests.support import _testenv  # noqa: F401

import csv
import datetime
import io
import json
import logging
import os
import unittest
from unittest import mock

import agents_service
import audit_service
import auth_service
from sss.core import masking
from sss.persistence import repo_factory
from sss.core import security
from admin_crud import AccessDenied
from agents_service import DELAYED, AT_RISK, OFFLINE, OK, Thresholds, AgentsService
from audit_service import InvalidFilters, AuditService
from ticket_service import TicketService

IP = "10.7.8.9"
DEV_PASSWORD = "senha-dev-de-teste-123"
SECRET = "tok-auditoria-secreto-91"
THRESHOLDS = Thresholds(10, 90, 180)
CRITICAL_CONFIG = ("hb=10;fence=90;offline=180;call=30;kill=5;"
                   "misfire=RUN_ONCE;tol=300;horizonte=1461;envelhecimento=60")
TODAY = datetime.date(2026, 10, 15)


def _read_csv(chunks):
    body = b"".join(chunks)
    text = body.decode("utf-8")
    return body, list(csv.reader(io.StringIO(text.lstrip(u"﻿")), delimiter=";"))


class _Base(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(security, "ITERATIONS", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_DEV_PASSWORD: DEV_PASSWORD})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configure, None)

        self.audit = repo_factory.get("audit")
        self.agents = repo_factory.get("agents")
        self.catalog = repo_factory.get("catalog")
        self.tickets = repo_factory.get("tickets")
        self.rbac = repo_factory.get("rbac")
        self.store = repo_factory._fake_store
        # Instante da carga do seed: o agt-host02 nasce com heartbeat congelado 30 s antes dele.
        self.base = self.store.agents[2]["heartbeat_at"] + datetime.timedelta(seconds=30)
        self.now = self.base
        self.store.set_clock(lambda: self.now)

        self.log = logging.getLogger("sss_teste_aud")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        auth = auth_service.AuthService(
            repo_factory.get("users"), self.rbac, self.catalog, self.audit, 5, 900, self.log)
        self.ctx = {}
        for uid, login, profile_id in ((1, "admin", 1), (2, "op.prod", 2), (4, "consulta", 4)):
            session = {"user_id": uid, "login": login, "profile_id": profile_id,
                      "perm_version": self.rbac.profiles_get(profile_id)["perm_version"], "session_epoch": 0}
            self.ctx[login] = auth.revalidate(session)
        self.svc = AuditService(self.audit, lambda: self.now, self.log)
        self.svc_agentes = AgentsService(self.agents, self.catalog, lambda: self.now, THRESHOLDS, self.log, CRITICAL_CONFIG)

    def _insert_row(self, created_at, actor="admin", action="UPDATE", entity="tbsss_scripts",
                 entity_id=1, detail="x", ip="127.0.0.1"):
        aid = self.store.next_id("tbsss_audit")
        self.store.audit[aid] = {"id": aid, "actor": actor, "source_ip": ip, "action": action, "entity": entity,
                                     "entity_id": entity_id, "detail": detail, "created_at": created_at}
        return aid

    def _exports(self):
        return self.audit.list(filters={"action": "AUDIT_EXPORT"}, page=1, size=100)["items"]


class TestFilters(unittest.TestCase):

    def test_periodo_padrao_ultimos_7_dias(self):
        filters, errors = audit_service.normalize_filters({}, TODAY)
        self.assertEqual(errors, {})
        self.assertEqual((filters["date_from"], filters["date_to"]), ("2026-10-09", "2026-10-15"))
        filters, _ = audit_service.normalize_filters({"date_to": "2026-09-30"}, TODAY)
        self.assertEqual(filters["date_from"], "2026-09-24")

    def test_periodo_maximo_90_dias(self):
        ok, errors = audit_service.normalize_filters({"date_from": "2026-07-18", "date_to": "2026-10-15"}, TODAY)
        self.assertEqual(errors, {})
        _, errors = audit_service.normalize_filters({"date_from": "2026-07-17", "date_to": "2026-10-15"}, TODAY)
        self.assertEqual(errors, {"date_from": audit_service.MSG_PERIOD})

    def test_periodo_longo_exige_filtro_seletivo(self):
        long = {"date_from": "2025-10-15", "date_to": "2026-10-15"}  # 366 dias
        for extra in ({"actor": "admin"}, {"entity": "tbsss_users", "entity_id": "6"}):
            with self.subTest(extra=extra):
                _, errors = audit_service.normalize_filters(dict(long, **extra), TODAY)
                self.assertEqual(errors, {})
        _, errors = audit_service.normalize_filters(dict(long, entity="tbsss_users"), TODAY)
        self.assertEqual(errors, {"date_from": audit_service.MSG_PERIOD})
        _, errors = audit_service.normalize_filters({"date_from": "2025-10-14", "date_to": "2026-10-15", "actor": "admin"},
                                                        TODAY)
        self.assertEqual(errors, {"date_from": audit_service.MSG_SELECTIVE_PERIOD})

    def test_datas_invalidas_ou_invertidas(self):
        _, errors = audit_service.normalize_filters({"date_from": "2026-02-30"}, TODAY)
        self.assertEqual(errors, {"date_from": audit_service.MSG_DATE})
        filters, errors = audit_service.normalize_filters({"date_from": "2026-10-10", "date_to": "2026-10-01"}, TODAY)
        self.assertEqual(errors, {"date_to": audit_service.MSG_RANGE})
        self.assertEqual(filters["date_to"], "2026-10-01")

    def test_allowlist_dos_demais_filtros(self):
        input_value = {"actor": "SYSTEM:agt-host01", "action": "LOGIN_OK", "entity": "tbsss_agents",
                   "entity_id": "12", "ip": "10.0.", "outro": "x"}
        filters, errors = audit_service.normalize_filters(input_value, TODAY)
        self.assertEqual(errors, {})
        self.assertEqual(list(filters), ["date_from", "date_to", "actor", "action", "entity", "entity_id", "ip"])
        self.assertEqual(filters["entity_id"], 12)
        invalid = {"actor": "a b", "action": "DROP", "entity": "dual", "entity_id": "-1", "ip": "1.1;x"}
        _, errors = audit_service.normalize_filters(invalid, TODAY)
        self.assertEqual(sorted(errors), ["action", "actor", "entity", "entity_id", "ip"])

    def test_filtros_repo_periodo_inclusivo(self):
        filters, _ = audit_service.normalize_filters({"date_from": "2026-10-01", "date_to": "2026-10-02", "ip": "127"}, TODAY)
        repo = audit_service.repo_filters(filters)
        self.assertEqual(repo["start_date"], datetime.datetime(2026, 10, 1))
        self.assertEqual(repo["end_date"], datetime.datetime(2026, 10, 2, 23, 59, 59))
        self.assertEqual(repo["source_ip"], "127")

    def test_catalogo_de_acoes(self):
        for action in ("LOGIN_OK", "PERM_UPDATE", "AGENT_STOP", "PURGE", "AUDIT_EXPORT"):
            self.assertIn(action, audit_service.ACTIONS)
        self.assertTrue(all(len(a) <= 30 for a in audit_service.ACTIONS))


class TestCsvNeutralization(unittest.TestCase):

    def test_prefixos_perigosos(self):
        for value in ("=CMD()", "+1", "-2", "@SUM(A1)", "\tx", "\rx"):
            with self.subTest(valor=value):
                self.assertEqual(audit_service.neutralize_csv(value), "'" + value)

    def test_valores_inofensivos(self):
        for value in ("a=b", "LOGIN_OK", "", 15, None):
            with self.subTest(valor=value):
                self.assertEqual(audit_service.neutralize_csv(value), value)


class TestList(_Base):

    def test_seed_nos_ultimos_7_dias_e_ordenacao(self):
        res = self.svc.list(self.ctx["admin"], {}, 1, 100)
        self.assertEqual(res["errors"], {})
        self.assertEqual(res["total"], 30)
        keys = [(i["created_at"], i["id"]) for i in res["items"]]
        self.assertEqual(keys, sorted(keys, reverse=True))

    def test_periodo_padrao_exclui_antigos(self):
        old = self._insert_row(self.base - datetime.timedelta(days=8))
        ids = [i["id"] for i in self.svc.list(self.ctx["admin"], {}, 1, 100)["items"]]
        self.assertNotIn(old, ids)
        of = (self.base - datetime.timedelta(days=8)).strftime("%Y-%m-%d")
        ids = [i["id"] for i in self.svc.list(self.ctx["admin"], {"date_from": of}, 1, 100)["items"]]
        self.assertIn(old, ids)

    def test_filtros(self):
        cases = (
            ({"action": "LOGIN_OK"}, 4),
            ({"actor": "op.prod"}, 3),
            ({"actor": "system:agt"}, 2),
            ({"entity": "tbsss_users", "entity_id": "6"}, 3),
            ({"ip": "127.0"}, 30),
            ({"ip": "10.9"}, 0),
        )
        for input_value, total in cases:
            with self.subTest(entrada=input_value):
                self.assertEqual(self.svc.list(self.ctx["admin"], input_value, 1, 100)["total"], total)

    def test_tamanho_maximo_100(self):
        for _ in range(130):
            self._insert_row(self.base)
        res = self.svc.list(self.ctx["admin"], {}, 1, 500)
        self.assertEqual((res["size"], len(res["items"])), (100, 100))

    def test_filtro_invalido_nao_consulta(self):
        with mock.patch.object(self.audit, "list") as list_value:
            res = self.svc.list(self.ctx["admin"], {"action": "XPTO"}, 1, 20)
        list_value.assert_not_called()
        self.assertEqual((res["total"], sorted(res["errors"])), (0, ["action"]))

    def test_rbac(self):
        for login in ("consulta", "op.prod"):
            with self.subTest(login=login):
                with self.assertRaises(AccessDenied):
                    self.svc.list(self.ctx[login], {}, 1, 20)

    def test_detalhe_truncado_e_mascarado(self):
        masking.register_secret(SECRET)
        long = u"campo: " + u"á" * 120
        aid_long = self._insert_row(self.base, detail=long)
        aid_seg = self._insert_row(self.base, detail=u"valor vazado %s" % SECRET)
        items = dict((i["id"], i) for i in self.svc.list(self.ctx["admin"], {}, 1, 100)["items"])
        self.assertTrue(items[aid_long]["truncated"])
        self.assertEqual(len(items[aid_long]["short_detail"]), audit_service.SHORT_DETAIL)
        self.assertEqual(items[aid_long]["detail"], long)
        self.assertNotIn(SECRET, items[aid_seg]["detail"])

    def test_seed_sem_segredos(self):
        res = self.svc.list(self.ctx["admin"], {}, 1, 100)
        for item in res["items"]:
            for value in item.values():
                if isinstance(value, str):
                    self.assertNotIn(DEV_PASSWORD, value)
                    self.assertNotIn("pbkdf2", value.lower())

    def test_link_entidade_respeita_permissao(self):
        admin, prod = self.ctx["admin"], self.ctx["op.prod"]
        link = audit_service.entity_link
        self.assertEqual(link(admin, "tbsss_tickets", 11, True), ("tickets", "detail", [11]))
        self.assertEqual(link(admin, "tbsss_users", 6, True), ("admin_users", "form", [6]))
        self.assertIsNone(link(prod, "tbsss_users", 6, True))
        self.assertIsNone(link(prod, "tbsss_tickets", 11, False))
        self.assertIsNone(link(admin, "tbsss_agents", 1, True))
        self.assertIsNone(link(admin, "tbsss_tickets", None, True))


class TestExport(_Base):

    def test_csv_injection_neutralizado(self):
        aid = self._insert_row(self.base, detail="=CMD()", actor="admin")
        self._insert_row(self.base, detail="-1+2", ip="@evil")
        _, rows, chunks = self.svc.export_csv(self.ctx["admin"], IP, {})
        body, table = _read_csv(chunks)
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(table[0], list(audit_service.CSV_HEADER))
        by_id = dict((r[0], r) for r in table[1:])
        self.assertEqual(by_id[str(aid)][7], "'=CMD()")
        details = [r[7] for r in table[1:]]
        self.assertIn("'-1+2", details)
        self.assertIn("'@evil", [r[3] for r in table[1:]])
        self.assertEqual(len(table) - 1, rows)

    def test_respeita_filtros(self):
        _, rows, chunks = self.svc.export_csv(self.ctx["admin"], IP, {"action": "LOGIN_OK"})
        _, table = _read_csv(chunks)
        self.assertEqual(rows, 4)
        self.assertEqual(set(r[4] for r in table[1:]), {"LOGIN_OK"})

    def test_exportacao_auditada_e_fora_do_proprio_arquivo(self):
        name, rows, chunks = self.svc.export_csv(self.ctx["admin"], IP, {"actor": "admin"})
        regs = self._exports()
        self.assertEqual(len(regs), 1)
        reg = regs[0]
        self.assertEqual((reg["actor"], reg["source_ip"], reg["entity"], reg["entity_id"]),
                         ("admin", IP, "tbsss_audit", None))
        self.assertIn("actor=admin", reg["detail"])
        self.assertIn("linhas: %d" % rows, reg["detail"])
        self.assertTrue(name.startswith("auditoria_") and name.endswith(".csv"))
        _, table = _read_csv(chunks)
        self.assertNotIn(str(reg["id"]), [r[0] for r in table[1:]])
        self.assertEqual(len(table) - 1, rows)

    def test_quantidade_registrada_e_a_do_recorte_exportado(self):
        # CR-003 P9 (README §4.4): linhas gravadas depois da reserva do id nao entram nem na contagem nem no arquivo.
        _name, rows, chunks = self.svc.export_csv(self.ctx["admin"], IP, {"actor": "admin"})
        self.audit.register("admin", IP, "UPDATE", "tbsss_environments", 1, "depois da exportacao")
        _, table = _read_csv(chunks)
        self.assertEqual(len(table) - 1, rows)
        self.assertIn("linhas: %d" % rows, self._exports()[0]["detail"])

    def test_limite_de_linhas(self):
        for _ in range(audit_service.EXPORT_LIMIT + 20):
            self._insert_row(self.base)
        result = self.audit.list(size=1)
        self.assertEqual(result["total"], 10001)
        self.assertTrue(result["total_capped"])
        _, rows, chunks = self.svc.export_csv(self.ctx["admin"], IP, {})
        _, table = _read_csv(chunks)
        self.assertEqual(rows, audit_service.EXPORT_LIMIT)
        self.assertEqual(len(table) - 1, audit_service.EXPORT_LIMIT)
        self.assertIn("limite %d" % audit_service.EXPORT_LIMIT, self._exports()[0]["detail"])

    def test_streaming_em_blocos(self):
        for _ in range(1200):
            self._insert_row(self.base)
        _, _, chunks = self.svc.export_csv(self.ctx["admin"], IP, {})
        self.assertGreaterEqual(len(list(chunks)), 3)

    def test_rbac_e_filtros_invalidos_nao_auditam(self):
        with self.assertRaises(AccessDenied):
            self.svc.export_csv(self.ctx["consulta"], IP, {})
        with self.assertRaises(InvalidFilters) as cm:
            self.svc.export_csv(self.ctx["admin"], IP, {"date_from": "2020-01-01"})
        self.assertIn("date_from", cm.exception.errors)
        self.assertEqual(self._exports(), [])


class TestAgentHealth(unittest.TestCase):

    NOW = datetime.datetime(2026, 10, 15, 12, 0, 0)

    def _health(self, age_s, status="ACTIVE"):
        hb = None if age_s is None else self.NOW - datetime.timedelta(seconds=age_s)
        return agents_service.health({"status": status, "heartbeat_at": hb}, self.NOW, THRESHOLDS)

    def test_quatro_limiares(self):
        cases = ((0, OK), (19, OK), (20, DELAYED), (90, DELAYED), (91, AT_RISK), (180, AT_RISK),
                 (181, OFFLINE), (-5, OK))
        for age, expected in cases:
            with self.subTest(idade=age):
                self.assertEqual(self._health(age), expected)

    def test_parado_ou_sem_heartbeat_offline(self):
        self.assertEqual(self._health(0, "STOPPED"), OFFLINE)
        self.assertEqual(self._health(None), OFFLINE)

    def test_info_e_legenda(self):
        self.assertEqual([i["code"] for i in agents_service.legend()], [OK, DELAYED, AT_RISK, OFFLINE])
        for info in agents_service.legend():
            self.assertTrue(info["label"] and info["css_class"] and info["icon"] and info["description"])

    def test_formatar_idade(self):
        self.assertEqual(agents_service.format_age(None), u"sem heartbeat")
        self.assertEqual(agents_service.format_age(42), u"há 42 s")
        self.assertEqual(agents_service.format_age(119), u"há 119 s")
        self.assertEqual(agents_service.format_age(600), u"há 10 min")
        self.assertEqual(agents_service.format_age(10800), u"há 3 h")
        self.assertEqual(agents_service.format_age(3 * 86400), u"há 3 dias")


class TestAgentsDashboard(_Base):

    def _healths(self, now=None):
        dashboard = self.svc_agentes.dashboard(self.ctx["admin"], now)
        return dict((a["code"], a["health"]["code"]) for a in dashboard["agents"])

    def test_seed_em_estados_diferentes_mudando_com_o_relogio(self):
        self.assertEqual(self._healths(), {"agt-host01": OK, "agt-host02": DELAYED})
        self.now = self.base + datetime.timedelta(seconds=70)
        self.assertEqual(self._healths(), {"agt-host01": OK, "agt-host02": AT_RISK})
        self.now = self.base + datetime.timedelta(seconds=160)
        self.assertEqual(self._healths(), {"agt-host01": OK, "agt-host02": OFFLINE})

    def test_campos_e_tickets_running(self):
        dashboard = self.svc_agentes.dashboard(self.ctx["admin"])
        self.assertEqual(dashboard["now"], self.base)
        ag = dashboard["agents"][0]
        for field in ("code", "hostname", "status", "version", "environments", "started_at", "heartbeat_at",
                      "health", "running", "ago"):
            self.assertIn(field, ag)
        for ag in dashboard["agents"]:
            expected = [t["id"] for t in self.agents.tickets_running(ag["code"])]
            self.assertEqual([t["id"] for t in ag["tickets"]], expected)
            self.assertEqual(ag["running"], len(expected))
        self.assertEqual(sum(dashboard["summary"].values()), 2)
        second = [a for a in dashboard["agents"] if a["code"] == "agt-host02"][0]
        self.assertEqual((second["age_s"], second["ago"]), (30, u"há 30 s"))

    def _queue_diagnostics(self):
        self.store.tickets.clear()
        self.store.agents_hb_simulated.clear()
        for tid, seconds, status in ((1, -300, "PENDING"), (2, 0, "PENDING"),
                                      (3, 1, "PENDING"), (4, -600, "SUCCESS")):
            # Script 3 (cleanup_tmp) e BASH no cadastro; o snapshot diz outra coisa e e ignorado (CR-008, R-15).
            self.store.tickets[tid] = {"id": tid, "status": status, "environment": "PRODUCAO", "script_id": 3,
                                      "scheduled_at": self.now + datetime.timedelta(seconds=seconds),
                                      "submitted_params": json.dumps({"interpreter": "SH"}),
                                      "log_output": object()}

    def test_fila_exige_um_agente_para_o_par_e_ignora_futuro(self):
        self._queue_diagnostics()
        self.store.agents[1].update(environments="PRODUCAO", interpreters="PYTHON3")
        self.store.agents[2].update(environments="HOMOLOGACAO", interpreters="BASH")
        result = self.agents.unattended_queue(self.now, THRESHOLDS)
        self.assertEqual(result, [{"environment": "PRODUCAO", "interpreter": "BASH", "quantity": 2,
                                     "oldest": self.now - datetime.timedelta(seconds=300)}])
        self.store.agents[2]["environments"] = "PRODUCAO"
        self.assertEqual(self.agents.unattended_queue(self.now, THRESHOLDS), [])

    def test_fila_limiares_e_agente_parado(self):
        self._queue_diagnostics()
        self.store.agents[2]["status"] = "STOPPED"
        for age, status, quantity in ((19, "ACTIVE", 0), (20, "ACTIVE", 0), (90, "ACTIVE", 0),
                                          (91, "ACTIVE", 1), (181, "ACTIVE", 1), (0, "STOPPED", 1)):
            self.store.agents[1].update(status=status,
                                        heartbeat_at=self.now - datetime.timedelta(seconds=age))
            self.assertEqual(len(self.agents.unattended_queue(self.now, THRESHOLDS)), quantity)
        self.store.agents[1].update(status="ACTIVE", heartbeat_at=None)
        self.assertEqual(len(self.agents.unattended_queue(self.now, THRESHOLDS)), 1)

    def test_sem_pid_usa_reserva_e_limite_estrito_sem_lob(self):
        self.store.tickets.clear()
        for tid, seconds, pid, status in ((1, 121, None, "RUNNING"), (2, 120, None, "RUNNING"),
                                          (3, 119, None, "RUNNING"), (4, 600, 42, "RUNNING"),
                                          (5, 600, None, "PENDING"), (6, 180, None, "RUNNING")):
            self.store.tickets[tid] = {"id": tid, "script_id": 1, "environment": "PRODUCAO", "status": status,
                                      "process_id": pid, "agent_id": "agt-host01",
                                      "started_at": self.now - datetime.timedelta(seconds=seconds),
                                      "created_at": self.now - datetime.timedelta(days=5),
                                      "log_output": object(), "submitted_params": object()}
        before = dict(self.store.audit)
        items = self.agents.running_without_pid(self.now, 2)
        self.assertEqual([t["id"] for t in items], [6, 1])
        self.assertEqual(set(items[0]), {"id", "script_id", "environment", "agent_id", "started_at"})
        self.assertEqual(self.store.audit, before)

    def test_diagnosticos_do_seed(self):
        """Dados de demonstracao: os tres quadros aparecem (UI_FREEZE, CR-007 R-18)."""
        dashboard = self.svc_agentes.dashboard(self.ctx["admin"])
        self.assertEqual([a["code"] for a in dashboard["config_mismatch"]], ["agt-host02"])
        self.assertIn("kill=10", dashboard["config_mismatch"][0]["critical_config"])
        self.assertEqual([t["id"] for t in dashboard["running_without_pid"]], [16])
        self.assertEqual(dashboard["unattended_queue"], [])  # agt-host02 ainda DELAYED
        self.now = self.base + datetime.timedelta(seconds=61)  # agt-host02 AT_RISK
        queue_value = self.svc_agentes.dashboard(self.ctx["admin"])["unattended_queue"]
        self.assertEqual([(g["environment"], g["interpreter"], g["quantity"]) for g in queue_value],
                         [("HOMOLOGACAO", "SH", 1)])
        self.assertEqual(queue_value[0]["oldest"], self.store.tickets[4]["scheduled_at"])

    def test_diagnosticos_config_divergente_e_parado(self):
        self.store.agents[2]["critical_config"] = CRITICAL_CONFIG
        self.assertEqual(self.svc_agentes.dashboard(self.ctx["admin"])["config_mismatch"], [])
        self.store.agents[2]["critical_config"] = CRITICAL_CONFIG.replace("hb=10", "hb=11")
        dashboard = self.svc_agentes.dashboard(self.ctx["admin"])
        self.assertEqual([a["code"] for a in dashboard["config_mismatch"]], ["agt-host02"])
        self.assertEqual(dashboard["config_web"], CRITICAL_CONFIG)
        self.store.agents[1]["critical_config"] = self.store.agents[2]["critical_config"]
        self.assertEqual(len(self.svc_agentes.dashboard(self.ctx["admin"])["config_mismatch"]), 2)
        self.store.agents[2]["status"] = "STOPPED"
        self.assertEqual(len(self.svc_agentes.dashboard(self.ctx["admin"])["config_mismatch"]), 1)

    def test_tickets_do_agente(self):
        items = self.svc_agentes.agent_tickets(self.ctx["admin"], "agt-host01")
        self.assertEqual([t["id"] for t in items], [11, 13, 15])
        self.assertTrue(all(t["script_name"] for t in items))
        self.assertEqual(self.svc_agentes.agent_tickets(self.ctx["admin"], "inexistente"), [])

    def test_somente_leitura_e_rbac(self):
        before = [dict(a) for a in self.store.agents.values() if a["code"] == "agt-host02"]
        self.svc_agentes.dashboard(self.ctx["admin"])
        after = [dict(a) for a in self.store.agents.values() if a["code"] == "agt-host02"]
        self.assertEqual(before, after)
        for login in ("consulta", "op.prod"):
            with self.subTest(login=login):
                with self.assertRaises(AccessDenied):
                    self.svc_agentes.dashboard(self.ctx[login])
                with self.assertRaises(AccessDenied):
                    self.svc_agentes.agent_tickets(self.ctx[login], "agt-host01")


class TestHomeSummary(_Base):

    def setUp(self):
        _Base.setUp(self)
        self.svc_tickets = TicketService(self.catalog, self.tickets, self.log)

    def test_escopo_por_perfil(self):
        admin = self.svc_tickets.home_summary(self.ctx["admin"])
        prod = self.svc_tickets.home_summary(self.ctx["op.prod"])
        query = self.svc_tickets.home_summary(self.ctx["consulta"])
        self.assertEqual([s for s, _ in admin["counts"]], ["PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED"])
        self.assertEqual(admin["since"], self.base - datetime.timedelta(hours=24))
        total_admin = sum(q for _, q in admin["counts"])
        self.assertGreater(total_admin, 0)
        self.assertLessEqual(sum(q for _, q in prod["counts"]), total_admin)
        self.assertLessEqual(len(admin["mine"]), 5)
        self.assertTrue(all(t["requested_by"] == "admin" for t in admin["mine"]))
        self.assertTrue(all(t["requested_by"] == u"você" for t in prod["mine"]))
        self.assertEqual(query["mine"], [])

    def test_contagem_igual_a_lista(self):
        summary = self.svc_tickets.home_summary(self.ctx["op.prod"])
        since = summary["since"]
        items = self.tickets.list(filters={"created_from": since}, page=1, size=1000,
                                    environment_scope=["HOMOLOGACAO", "PRODUCAO"])["items"]
        for status, count in summary["counts"]:
            with self.subTest(status=status):
                self.assertEqual(count, len([t for t in items if t["status"] == status]))

    def test_sem_consulta_retorna_none(self):
        without_feature = dict(self.ctx["consulta"], features=frozenset())
        self.assertIsNone(self.svc_tickets.home_summary(without_feature))


class TestLabels(unittest.TestCase):

    def test_toda_acao_e_entidade_tem_nome_simples(self):
        # CR-018b: a tela mostra o nome simples; o CSV continua com o codigo (csv_row nao muda).
        self.assertEqual(set(audit_service.ACTION_LABELS), set(audit_service.ACTIONS))
        self.assertEqual(set(audit_service.ENTITY_LABELS), set(audit_service.ENTITIES))
        self.assertEqual(audit_service.action_label("TICKET_CANCEL"), u"Cancelamento de ticket")
        self.assertEqual(audit_service.action_label("NOVA_ACAO"), "NOVA_ACAO")


if __name__ == "__main__":
    unittest.main()
