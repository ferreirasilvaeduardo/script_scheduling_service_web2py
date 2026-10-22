# -*- coding: utf-8 -*-
"""Rotinas disponiveis e historico do script (README §5.8, CR-004 U5/U7) sobre o FAKE."""
import _testenv  # noqa: F401

import datetime
import logging
import os
import unittest
from unittest import mock

import auth_service
import repo_factory
import security
from ticket_service import TicketService

SESSIONS = {
    "admin": {"user_id": 1, "login": "admin", "profile_id": 1, "perm_version": 1, "session_epoch": 0},
    "op.hml": {"user_id": 3, "login": "op.hml", "profile_id": 3, "perm_version": 1, "session_epoch": 0},
}


class _Base(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(security, "ITERATIONS", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_DEV_PASSWORD: "senha-dev-de-teste-123"})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configure, None)
        self.catalog = repo_factory.get("catalog")
        self.tickets = repo_factory.get("tickets")
        log = logging.getLogger("sss_teste_catalogo")
        log.addHandler(logging.NullHandler())
        log.propagate = False
        auth = auth_service.AuthService(repo_factory.get("users"), repo_factory.get("rbac"), self.catalog,
                                        repo_factory.get("audit"), 5, 900, log)
        self.ctx = dict((login, auth.revalidate(session)) for login, session in SESSIONS.items())
        self.svc = TicketService(self.catalog, self.tickets, log)

    def _without(self, login, *features_ids):
        ctx = dict(self.ctx[login])
        ctx["features"] = frozenset(ctx["features"] - set(features_ids))
        return ctx


class TestLastRuns(_Base):

    def test_contrato_ultimo_por_script_no_escopo(self):
        all_value = self.tickets.list(page=1, size=100)["items"]
        expected = {}
        for t in all_value:
            if t["environment"] == "HOMOLOGACAO":
                current = expected.get(t["script_id"])
                if current is None or (t["created_at"], t["id"]) > (current["created_at"], current["id"]):
                    expected[t["script_id"]] = t
        r = self.tickets.last_runs([1, 2, 3, 4], ["HOMOLOGACAO"])
        self.assertEqual(dict((k, v["id"]) for k, v in r.items()), dict((k, v["id"]) for k, v in expected.items()))
        self.assertNotIn("log_output", list(r.values())[0])
        only_mine = self.tickets.last_runs([1, 2, 3, 4], None, "op.hml")
        for sid, u in only_mine.items():
            self.assertEqual(self.tickets.get(u["id"])["requested_by"], "op.hml")
        self.assertEqual(self.tickets.last_runs([], None), {})


class TestRoutineCatalog(_Base):

    def test_cartoes_iguais_ao_disparo_e_ultima_no_escopo(self):
        ctx = self.ctx["op.hml"]
        groups = self.svc.routine_catalog(ctx)
        ids = sorted(c["id"] for g in groups for c in g["cards"])
        self.assertEqual(ids, sorted(s["id"] for g in self.svc.available_scripts(ctx) for s in g["scripts"]))
        for g in groups:
            for c in g["cards"]:
                self.assertTrue(c["environments"])
                if c["last_run"]:
                    t = self.tickets.get(c["last_run"]["id"])
                    self.assertIn(t["environment"], ctx["environments"])
                    self.assertTrue(c["last_run"]["when"].startswith(u"há "))

    def test_sem_ver_logs_so_os_proprios(self):
        ctx = self._without("op.hml", "VIEW_LOGS")
        for g in self.svc.routine_catalog(ctx):
            for c in g["cards"]:
                if c["last_run"]:
                    self.assertEqual(self.tickets.get(c["last_run"]["id"])["requested_by"], "op.hml")

    def test_perguntas_com_obrigatorio(self):
        cards = dict((c["name"], c) for g in self.svc.routine_catalog(self.ctx["admin"]) for c in g["cards"])
        questions = cards["carga_diaria"]["questions"]
        self.assertIn({"label": u"Data de Referencia", "required": True}, questions)

    def test_sem_exec_script_vazio(self):
        self.assertEqual(self.svc.routine_catalog(self._without("op.hml", "EXEC_SCRIPT")), [])



class TestScriptHistory(_Base):
    """CR-004 U7 (README §5.8)."""

    def test_contrato_sem_lob_ordenado_e_limitado(self):
        since = self.tickets.now() - datetime.timedelta(days=30)
        items = self.tickets.script_history(1, since)
        self.assertTrue(items)
        self.assertEqual(set(items[0]), {"id", "status", "status_reason", "created_at", "started_at", "finished_at"})
        self.assertEqual(items, sorted(items, key=lambda t: (t["created_at"], t["id"])))
        self.assertEqual(len(self.tickets.script_history(1, since, limit=2)), 2)
        self.assertTrue(all(self.tickets.get(t["id"])["environment"] == "HOMOLOGACAO"
                            for t in self.tickets.script_history(1, since, ["HOMOLOGACAO"])))

    def test_numeros_batem_com_o_grafico_e_a_taxa(self):
        h = self.svc.script_history(self.ctx["admin"], "1")
        c = h["counts"]
        self.assertEqual(sum(c.values()), h["total"])
        by_day = sum(sum(d[k] for k in c) for d in h["days"])
        self.assertEqual(by_day, h["total"])
        self.assertEqual(len(h["days"]), 30)
        finished = c["succeeded"] + c["error"] + c["cancelled"]
        if finished:
            self.assertEqual(h["rate"], int(round(100.0 * c["succeeded"] / finished)))
            self.assertTrue(h["rate_phrase"].startswith(u"De cada 10 vezes,"))
        self.assertEqual(h["list_filter"]["script"], 1)

    def test_fora_das_rotinas_e_404(self):
        from repo_errors import RepoNotFound
        with self.assertRaises(RepoNotFound):
            self.svc.script_history(self.ctx["op.hml"], "5")  # backup_extra: inativo
        with self.assertRaises(RepoNotFound):
            self.svc.script_history(self._without("op.hml", "EXEC_SCRIPT"), "1")

    def test_escopo_sem_ver_logs_so_os_proprios(self):
        h = self.svc.script_history(self._without("op.hml", "VIEW_LOGS"), "1")
        since = self.tickets.now() - datetime.timedelta(days=30)
        self.assertEqual(h["total"], len(self.tickets.script_history(1, since, None, "op.hml")))


class TestStackedBars(unittest.TestCase):

    def test_geometria(self):
        import ui_helpers
        days = [{"label": "01/10", "succeeded": 2, "error": 1, "cancelled": 0, "in_progress": 0},
                {"label": "02/10", "succeeded": 0, "error": 0, "cancelled": 0, "in_progress": 0}]
        g = ui_helpers.barras_empilhadas(days, width=200, height=100)
        self.assertEqual(g["maximum"], 3)
        self.assertEqual([b["css_class"] for b in g["bars"]], ["sss-graf-succeeded", "sss-graf-error"])
        right, error = g["bars"]
        self.assertLess(error["y"], right["y"])  # empilhado de baixo para cima
        self.assertIn(u"01/10: Deu erro — 1", error["title"])
        self.assertEqual(ui_helpers.barras_empilhadas([], 200, 100)["bars"], [])


if __name__ == "__main__":
    unittest.main()
