# -*- coding: utf-8 -*-
"""Testes de audit_service.py e agents_service.py (F6.1) sobre o backend FAKE com relogio injetado."""
import _testenv  # noqa: F401

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
import masking
import repo_factory
import security
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
    corpo = b"".join(chunks)
    texto = corpo.decode("utf-8")
    return corpo, list(csv.reader(io.StringIO(texto.lstrip(u"﻿")), delimiter=";"))


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
        for uid, login, perfil_id in ((1, "admin", 1), (2, "op.prod", 2), (4, "consulta", 4)):
            sessao = {"usuario_id": uid, "login": login, "perfil_id": perfil_id,
                      "perm_versao": self.rbac.profiles_get(perfil_id)["perm_version"], "sessao_epoch": 0}
            self.ctx[login] = auth.revalidate(sessao)
        self.svc = AuditService(self.audit, lambda: self.now, self.log)
        self.svc_agentes = AgentsService(self.agents, self.catalog, lambda: self.now, THRESHOLDS, self.log, CRITICAL_CONFIG)

    def _insert_row(self, created_at, actor="admin", action="UPDATE", entity="tbsss_scripts",
                 entity_id=1, detail="x", ip="127.0.0.1"):
        aid = self.store.next_id("tbsss_audit")
        self.store.audit[aid] = {"id": aid, "actor": actor, "source_ip": ip, "action": action, "entity": entity,
                                     "entity_id": entity_id, "detail": detail, "created_at": created_at}
        return aid

    def _exports(self):
        return self.audit.list(filters={"action": "AUDIT_EXPORT"}, page=1, size=100)["itens"]


class TestFilters(unittest.TestCase):

    def test_periodo_padrao_ultimos_7_dias(self):
        filtros, erros = audit_service.normalize_filters({}, TODAY)
        self.assertEqual(erros, {})
        self.assertEqual((filtros["de"], filtros["ate"]), ("2026-10-09", "2026-10-15"))
        filtros, _ = audit_service.normalize_filters({"ate": "2026-09-30"}, TODAY)
        self.assertEqual(filtros["de"], "2026-09-24")

    def test_periodo_maximo_90_dias(self):
        ok, erros = audit_service.normalize_filters({"de": "2026-07-18", "ate": "2026-10-15"}, TODAY)
        self.assertEqual(erros, {})
        _, erros = audit_service.normalize_filters({"de": "2026-07-17", "ate": "2026-10-15"}, TODAY)
        self.assertEqual(erros, {"de": audit_service.MSG_PERIOD})

    def test_periodo_longo_exige_filtro_seletivo(self):
        longo = {"de": "2025-10-15", "ate": "2026-10-15"}  # 366 dias
        for extra in ({"actor": "admin"}, {"entity": "tbsss_users", "entity_id": "6"}):
            with self.subTest(extra=extra):
                _, erros = audit_service.normalize_filters(dict(longo, **extra), TODAY)
                self.assertEqual(erros, {})
        _, erros = audit_service.normalize_filters(dict(longo, entity="tbsss_users"), TODAY)
        self.assertEqual(erros, {"de": audit_service.MSG_PERIOD})
        _, erros = audit_service.normalize_filters({"de": "2025-10-14", "ate": "2026-10-15", "actor": "admin"},
                                                        TODAY)
        self.assertEqual(erros, {"de": audit_service.MSG_SELECTIVE_PERIOD})

    def test_datas_invalidas_ou_invertidas(self):
        _, erros = audit_service.normalize_filters({"de": "2026-02-30"}, TODAY)
        self.assertEqual(erros, {"de": audit_service.MSG_DATE})
        filtros, erros = audit_service.normalize_filters({"de": "2026-10-10", "ate": "2026-10-01"}, TODAY)
        self.assertEqual(erros, {"ate": audit_service.MSG_RANGE})
        self.assertEqual(filtros["ate"], "2026-10-01")

    def test_allowlist_dos_demais_filtros(self):
        entrada = {"actor": "SYSTEM:agt-host01", "action": "LOGIN_OK", "entity": "tbsss_agents",
                   "entity_id": "12", "ip": "10.0.", "outro": "x"}
        filtros, erros = audit_service.normalize_filters(entrada, TODAY)
        self.assertEqual(erros, {})
        self.assertEqual(list(filtros), ["de", "ate", "actor", "action", "entity", "entity_id", "ip"])
        self.assertEqual(filtros["entity_id"], 12)
        invalidos = {"actor": "a b", "action": "DROP", "entity": "dual", "entity_id": "-1", "ip": "1.1;x"}
        _, erros = audit_service.normalize_filters(invalidos, TODAY)
        self.assertEqual(sorted(erros), ["action", "actor", "entity", "entity_id", "ip"])

    def test_filtros_repo_periodo_inclusivo(self):
        filtros, _ = audit_service.normalize_filters({"de": "2026-10-01", "ate": "2026-10-02", "ip": "127"}, TODAY)
        repo = audit_service.repo_filters(filtros)
        self.assertEqual(repo["start_date"], datetime.datetime(2026, 10, 1))
        self.assertEqual(repo["end_date"], datetime.datetime(2026, 10, 2, 23, 59, 59))
        self.assertEqual(repo["source_ip"], "127")

    def test_catalogo_de_acoes(self):
        for acao in ("LOGIN_OK", "PERM_UPDATE", "AGENT_STOP", "PURGE", "AUDIT_EXPORT"):
            self.assertIn(acao, audit_service.ACTIONS)
        self.assertTrue(all(len(a) <= 30 for a in audit_service.ACTIONS))


class TestCsvNeutralization(unittest.TestCase):

    def test_prefixos_perigosos(self):
        for valor in ("=CMD()", "+1", "-2", "@SUM(A1)", "\tx", "\rx"):
            with self.subTest(valor=valor):
                self.assertEqual(audit_service.neutralize_csv(valor), "'" + valor)

    def test_valores_inofensivos(self):
        for valor in ("a=b", "LOGIN_OK", "", 15, None):
            with self.subTest(valor=valor):
                self.assertEqual(audit_service.neutralize_csv(valor), valor)


class TestList(_Base):

    def test_seed_nos_ultimos_7_dias_e_ordenacao(self):
        res = self.svc.list(self.ctx["admin"], {}, 1, 100)
        self.assertEqual(res["erros"], {})
        self.assertEqual(res["total"], 30)
        chaves = [(i["created_at"], i["id"]) for i in res["itens"]]
        self.assertEqual(chaves, sorted(chaves, reverse=True))

    def test_periodo_padrao_exclui_antigos(self):
        antigo = self._insert_row(self.base - datetime.timedelta(days=8))
        ids = [i["id"] for i in self.svc.list(self.ctx["admin"], {}, 1, 100)["itens"]]
        self.assertNotIn(antigo, ids)
        de = (self.base - datetime.timedelta(days=8)).strftime("%Y-%m-%d")
        ids = [i["id"] for i in self.svc.list(self.ctx["admin"], {"de": de}, 1, 100)["itens"]]
        self.assertIn(antigo, ids)

    def test_filtros(self):
        casos = (
            ({"action": "LOGIN_OK"}, 4),
            ({"actor": "op.prod"}, 3),
            ({"actor": "system:agt"}, 2),
            ({"entity": "tbsss_users", "entity_id": "6"}, 3),
            ({"ip": "127.0"}, 30),
            ({"ip": "10.9"}, 0),
        )
        for entrada, total in casos:
            with self.subTest(entrada=entrada):
                self.assertEqual(self.svc.list(self.ctx["admin"], entrada, 1, 100)["total"], total)

    def test_tamanho_maximo_100(self):
        for _ in range(130):
            self._insert_row(self.base)
        res = self.svc.list(self.ctx["admin"], {}, 1, 500)
        self.assertEqual((res["tamanho"], len(res["itens"])), (100, 100))

    def test_filtro_invalido_nao_consulta(self):
        with mock.patch.object(self.audit, "list") as listar:
            res = self.svc.list(self.ctx["admin"], {"action": "XPTO"}, 1, 20)
        listar.assert_not_called()
        self.assertEqual((res["total"], sorted(res["erros"])), (0, ["action"]))

    def test_rbac(self):
        for login in ("consulta", "op.prod"):
            with self.subTest(login=login):
                with self.assertRaises(AccessDenied):
                    self.svc.list(self.ctx[login], {}, 1, 20)

    def test_detalhe_truncado_e_mascarado(self):
        masking.register_secret(SECRET)
        longo = u"campo: " + u"á" * 120
        aid_longo = self._insert_row(self.base, detail=longo)
        aid_seg = self._insert_row(self.base, detail=u"valor vazado %s" % SECRET)
        itens = dict((i["id"], i) for i in self.svc.list(self.ctx["admin"], {}, 1, 100)["itens"])
        self.assertTrue(itens[aid_longo]["truncado"])
        self.assertEqual(len(itens[aid_longo]["detalhe_curto"]), audit_service.SHORT_DETAIL)
        self.assertEqual(itens[aid_longo]["detail"], longo)
        self.assertNotIn(SECRET, itens[aid_seg]["detail"])

    def test_seed_sem_segredos(self):
        res = self.svc.list(self.ctx["admin"], {}, 1, 100)
        for item in res["itens"]:
            for valor in item.values():
                if isinstance(valor, str):
                    self.assertNotIn(DEV_PASSWORD, valor)
                    self.assertNotIn("pbkdf2", valor.lower())

    def test_link_entidade_respeita_permissao(self):
        admin, prod = self.ctx["admin"], self.ctx["op.prod"]
        link = audit_service.entity_link
        self.assertEqual(link(admin, "tbsss_tickets", 11, True), ("tickets", "detalhe", [11]))
        self.assertEqual(link(admin, "tbsss_users", 6, True), ("admin_usuarios", "form", [6]))
        self.assertIsNone(link(prod, "tbsss_users", 6, True))
        self.assertIsNone(link(prod, "tbsss_tickets", 11, False))
        self.assertIsNone(link(admin, "tbsss_agents", 1, True))
        self.assertIsNone(link(admin, "tbsss_tickets", None, True))


class TestExport(_Base):

    def test_csv_injection_neutralizado(self):
        aid = self._insert_row(self.base, detail="=CMD()", actor="admin")
        self._insert_row(self.base, detail="-1+2", ip="@evil")
        _, linhas, blocos = self.svc.export_csv(self.ctx["admin"], IP, {})
        corpo, tabela = _read_csv(blocos)
        self.assertTrue(corpo.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(tabela[0], list(audit_service.CSV_HEADER))
        por_id = dict((r[0], r) for r in tabela[1:])
        self.assertEqual(por_id[str(aid)][7], "'=CMD()")
        detalhes = [r[7] for r in tabela[1:]]
        self.assertIn("'-1+2", detalhes)
        self.assertIn("'@evil", [r[3] for r in tabela[1:]])
        self.assertEqual(len(tabela) - 1, linhas)

    def test_respeita_filtros(self):
        _, linhas, blocos = self.svc.export_csv(self.ctx["admin"], IP, {"action": "LOGIN_OK"})
        _, tabela = _read_csv(blocos)
        self.assertEqual(linhas, 4)
        self.assertEqual(set(r[4] for r in tabela[1:]), {"LOGIN_OK"})

    def test_exportacao_auditada_e_fora_do_proprio_arquivo(self):
        nome, linhas, blocos = self.svc.export_csv(self.ctx["admin"], IP, {"actor": "admin"})
        regs = self._exports()
        self.assertEqual(len(regs), 1)
        reg = regs[0]
        self.assertEqual((reg["actor"], reg["source_ip"], reg["entity"], reg["entity_id"]),
                         ("admin", IP, "tbsss_audit", None))
        self.assertIn("actor=admin", reg["detail"])
        self.assertIn("linhas: %d" % linhas, reg["detail"])
        self.assertTrue(nome.startswith("auditoria_") and nome.endswith(".csv"))
        _, tabela = _read_csv(blocos)
        self.assertNotIn(str(reg["id"]), [r[0] for r in tabela[1:]])
        self.assertEqual(len(tabela) - 1, linhas)

    def test_quantidade_registrada_e_a_do_recorte_exportado(self):
        # CR-003 P9 (README §4.4): linhas gravadas depois da reserva do id nao entram nem na contagem nem no arquivo.
        _nome, linhas, blocos = self.svc.export_csv(self.ctx["admin"], IP, {"actor": "admin"})
        self.audit.register("admin", IP, "UPDATE", "tbsss_environments", 1, "depois da exportacao")
        _, tabela = _read_csv(blocos)
        self.assertEqual(len(tabela) - 1, linhas)
        self.assertIn("linhas: %d" % linhas, self._exports()[0]["detail"])

    def test_limite_de_linhas(self):
        for _ in range(audit_service.EXPORT_LIMIT + 20):
            self._insert_row(self.base)
        resultado = self.audit.list(size=1)
        self.assertEqual(resultado["total"], 10001)
        self.assertTrue(resultado["total_limitado"])
        _, linhas, blocos = self.svc.export_csv(self.ctx["admin"], IP, {})
        _, tabela = _read_csv(blocos)
        self.assertEqual(linhas, audit_service.EXPORT_LIMIT)
        self.assertEqual(len(tabela) - 1, audit_service.EXPORT_LIMIT)
        self.assertIn("limite %d" % audit_service.EXPORT_LIMIT, self._exports()[0]["detail"])

    def test_streaming_em_blocos(self):
        for _ in range(1200):
            self._insert_row(self.base)
        _, _, blocos = self.svc.export_csv(self.ctx["admin"], IP, {})
        self.assertGreaterEqual(len(list(blocos)), 3)

    def test_rbac_e_filtros_invalidos_nao_auditam(self):
        with self.assertRaises(AccessDenied):
            self.svc.export_csv(self.ctx["consulta"], IP, {})
        with self.assertRaises(InvalidFilters) as cm:
            self.svc.export_csv(self.ctx["admin"], IP, {"de": "2020-01-01"})
        self.assertIn("de", cm.exception.errors)
        self.assertEqual(self._exports(), [])


class TestAgentHealth(unittest.TestCase):

    NOW = datetime.datetime(2026, 10, 15, 12, 0, 0)

    def _health(self, age_s, status="ACTIVE"):
        hb = None if age_s is None else self.NOW - datetime.timedelta(seconds=age_s)
        return agents_service.health({"status": status, "heartbeat_at": hb}, self.NOW, THRESHOLDS)

    def test_quatro_limiares(self):
        casos = ((0, OK), (19, OK), (20, DELAYED), (90, DELAYED), (91, AT_RISK), (180, AT_RISK),
                 (181, OFFLINE), (-5, OK))
        for idade, esperado in casos:
            with self.subTest(idade=idade):
                self.assertEqual(self._health(idade), esperado)

    def test_parado_ou_sem_heartbeat_offline(self):
        self.assertEqual(self._health(0, "STOPPED"), OFFLINE)
        self.assertEqual(self._health(None), OFFLINE)

    def test_info_e_legenda(self):
        self.assertEqual([i["code"] for i in agents_service.legend()], [OK, DELAYED, AT_RISK, OFFLINE])
        for info in agents_service.legend():
            self.assertTrue(info["rotulo"] and info["classe"] and info["icone"] and info["description"])

    def test_formatar_idade(self):
        self.assertEqual(agents_service.format_age(None), u"sem heartbeat")
        self.assertEqual(agents_service.format_age(42), u"há 42 s")
        self.assertEqual(agents_service.format_age(119), u"há 119 s")
        self.assertEqual(agents_service.format_age(600), u"há 10 min")
        self.assertEqual(agents_service.format_age(10800), u"há 3 h")
        self.assertEqual(agents_service.format_age(3 * 86400), u"há 3 dias")


class TestAgentsDashboard(_Base):

    def _healths(self, now=None):
        painel = self.svc_agentes.dashboard(self.ctx["admin"], now)
        return dict((a["code"], a["saude"]["code"]) for a in painel["agents"])

    def test_seed_em_estados_diferentes_mudando_com_o_relogio(self):
        self.assertEqual(self._healths(), {"agt-host01": OK, "agt-host02": DELAYED})
        self.now = self.base + datetime.timedelta(seconds=70)
        self.assertEqual(self._healths(), {"agt-host01": OK, "agt-host02": AT_RISK})
        self.now = self.base + datetime.timedelta(seconds=160)
        self.assertEqual(self._healths(), {"agt-host01": OK, "agt-host02": OFFLINE})

    def test_campos_e_tickets_running(self):
        painel = self.svc_agentes.dashboard(self.ctx["admin"])
        self.assertEqual(painel["agora"], self.base)
        ag = painel["agents"][0]
        for campo in ("code", "hostname", "status", "version", "environments", "started_at", "heartbeat_at",
                      "saude", "running", "ha"):
            self.assertIn(campo, ag)
        for ag in painel["agents"]:
            esperado = [t["id"] for t in self.agents.tickets_running(ag["code"])]
            self.assertEqual([t["id"] for t in ag["tickets"]], esperado)
            self.assertEqual(ag["running"], len(esperado))
        self.assertEqual(sum(painel["resumo"].values()), 2)
        segundo = [a for a in painel["agents"] if a["code"] == "agt-host02"][0]
        self.assertEqual((segundo["idade_s"], segundo["ha"]), (30, u"há 30 s"))

    def _queue_diagnostics(self):
        self.store.tickets.clear()
        self.store.agents_hb_simulated.clear()
        for tid, segundos, status in ((1, -300, "PENDING"), (2, 0, "PENDING"),
                                      (3, 1, "PENDING"), (4, -600, "SUCCESS")):
            # Script 3 (cleanup_tmp) e BASH no cadastro; o snapshot diz outra coisa e e ignorado (CR-008, R-15).
            self.store.tickets[tid] = {"id": tid, "status": status, "environment": "PRODUCAO", "script_id": 3,
                                      "scheduled_at": self.now + datetime.timedelta(seconds=segundos),
                                      "submitted_params": json.dumps({"interpreter": "SH"}),
                                      "log_output": object()}

    def test_fila_exige_um_agente_para_o_par_e_ignora_futuro(self):
        self._queue_diagnostics()
        self.store.agents[1].update(environments="PRODUCAO", interpreters="PYTHON3")
        self.store.agents[2].update(environments="HOMOLOGACAO", interpreters="BASH")
        resultado = self.agents.unattended_queue(self.now, THRESHOLDS)
        self.assertEqual(resultado, [{"environment": "PRODUCAO", "interpreter": "BASH", "quantidade": 2,
                                     "mais_antigo": self.now - datetime.timedelta(seconds=300)}])
        self.store.agents[2]["environments"] = "PRODUCAO"
        self.assertEqual(self.agents.unattended_queue(self.now, THRESHOLDS), [])

    def test_fila_limiares_e_agente_parado(self):
        self._queue_diagnostics()
        self.store.agents[2]["status"] = "STOPPED"
        for idade, status, quantidade in ((19, "ACTIVE", 0), (20, "ACTIVE", 0), (90, "ACTIVE", 0),
                                          (91, "ACTIVE", 1), (181, "ACTIVE", 1), (0, "STOPPED", 1)):
            self.store.agents[1].update(status=status,
                                        heartbeat_at=self.now - datetime.timedelta(seconds=idade))
            self.assertEqual(len(self.agents.unattended_queue(self.now, THRESHOLDS)), quantidade)
        self.store.agents[1].update(status="ACTIVE", heartbeat_at=None)
        self.assertEqual(len(self.agents.unattended_queue(self.now, THRESHOLDS)), 1)

    def test_sem_pid_usa_reserva_e_limite_estrito_sem_lob(self):
        self.store.tickets.clear()
        for tid, segundos, pid, status in ((1, 121, None, "RUNNING"), (2, 120, None, "RUNNING"),
                                          (3, 119, None, "RUNNING"), (4, 600, 42, "RUNNING"),
                                          (5, 600, None, "PENDING"), (6, 180, None, "RUNNING")):
            self.store.tickets[tid] = {"id": tid, "script_id": 1, "environment": "PRODUCAO", "status": status,
                                      "process_id": pid, "agent_id": "agt-host01",
                                      "started_at": self.now - datetime.timedelta(seconds=segundos),
                                      "created_at": self.now - datetime.timedelta(days=5),
                                      "log_output": object(), "submitted_params": object()}
        antes = dict(self.store.audit)
        itens = self.agents.running_without_pid(self.now, 2)
        self.assertEqual([t["id"] for t in itens], [6, 1])
        self.assertEqual(set(itens[0]), {"id", "script_id", "environment", "agent_id", "started_at"})
        self.assertEqual(self.store.audit, antes)

    def test_diagnosticos_do_seed(self):
        """Dados de demonstracao: os tres quadros aparecem (UI_FREEZE, CR-007 R-18)."""
        painel = self.svc_agentes.dashboard(self.ctx["admin"])
        self.assertEqual([a["code"] for a in painel["config_divergente"]], ["agt-host02"])
        self.assertIn("kill=10", painel["config_divergente"][0]["critical_config"])
        self.assertEqual([t["id"] for t in painel["rodando_sem_pid"]], [16])
        self.assertEqual(painel["fila_sem_atendente"], [])  # agt-host02 ainda DELAYED
        self.now = self.base + datetime.timedelta(seconds=61)  # agt-host02 AT_RISK
        fila = self.svc_agentes.dashboard(self.ctx["admin"])["fila_sem_atendente"]
        self.assertEqual([(g["environment"], g["interpreter"], g["quantidade"]) for g in fila],
                         [("HOMOLOGACAO", "SH", 1)])
        self.assertEqual(fila[0]["mais_antigo"], self.store.tickets[4]["scheduled_at"])

    def test_diagnosticos_config_divergente_e_parado(self):
        self.store.agents[2]["critical_config"] = CRITICAL_CONFIG
        self.assertEqual(self.svc_agentes.dashboard(self.ctx["admin"])["config_divergente"], [])
        self.store.agents[2]["critical_config"] = CRITICAL_CONFIG.replace("hb=10", "hb=11")
        painel = self.svc_agentes.dashboard(self.ctx["admin"])
        self.assertEqual([a["code"] for a in painel["config_divergente"]], ["agt-host02"])
        self.assertEqual(painel["config_web"], CRITICAL_CONFIG)
        self.store.agents[1]["critical_config"] = self.store.agents[2]["critical_config"]
        self.assertEqual(len(self.svc_agentes.dashboard(self.ctx["admin"])["config_divergente"]), 2)
        self.store.agents[2]["status"] = "STOPPED"
        self.assertEqual(len(self.svc_agentes.dashboard(self.ctx["admin"])["config_divergente"]), 1)

    def test_tickets_do_agente(self):
        itens = self.svc_agentes.agent_tickets(self.ctx["admin"], "agt-host01")
        self.assertEqual([t["id"] for t in itens], [11, 13, 15])
        self.assertTrue(all(t["script_nome"] for t in itens))
        self.assertEqual(self.svc_agentes.agent_tickets(self.ctx["admin"], "inexistente"), [])

    def test_somente_leitura_e_rbac(self):
        antes = [dict(a) for a in self.store.agents.values() if a["code"] == "agt-host02"]
        self.svc_agentes.dashboard(self.ctx["admin"])
        depois = [dict(a) for a in self.store.agents.values() if a["code"] == "agt-host02"]
        self.assertEqual(antes, depois)
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
        consulta = self.svc_tickets.home_summary(self.ctx["consulta"])
        self.assertEqual([s for s, _ in admin["contagem"]], ["PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED"])
        self.assertEqual(admin["desde"], self.base - datetime.timedelta(hours=24))
        total_admin = sum(q for _, q in admin["contagem"])
        self.assertGreater(total_admin, 0)
        self.assertLessEqual(sum(q for _, q in prod["contagem"]), total_admin)
        self.assertLessEqual(len(admin["meus"]), 5)
        self.assertTrue(all(t["requested_by"] == "admin" for t in admin["meus"]))
        self.assertTrue(all(t["requested_by"] == u"você" for t in prod["meus"]))
        self.assertEqual(consulta["meus"], [])

    def test_contagem_igual_a_lista(self):
        resumo = self.svc_tickets.home_summary(self.ctx["op.prod"])
        desde = resumo["desde"]
        itens = self.tickets.list(filters={"criado_inicio": desde}, page=1, size=1000,
                                    environment_scope=["HOMOLOGACAO", "PRODUCAO"])["itens"]
        for status, qtd in resumo["contagem"]:
            with self.subTest(status=status):
                self.assertEqual(qtd, len([t for t in itens if t["status"] == status]))

    def test_sem_consulta_retorna_none(self):
        sem_func = dict(self.ctx["consulta"], features=frozenset())
        self.assertIsNone(self.svc_tickets.home_summary(sem_func))


if __name__ == "__main__":
    unittest.main()
