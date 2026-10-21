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

SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0},
    "op.hml": {"usuario_id": 3, "login": "op.hml", "perfil_id": 3, "perm_versao": 1, "sessao_epoch": 0},
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
        self.ctx = dict((login, auth.revalidate(sessao)) for login, sessao in SESSOES.items())
        self.svc = TicketService(self.catalog, self.tickets, log)

    def _sem(self, login, *funcs):
        ctx = dict(self.ctx[login])
        ctx["features"] = frozenset(ctx["features"] - set(funcs))
        return ctx


class TestUltimasExecucoes(_Base):

    def test_contrato_ultimo_por_script_no_escopo(self):
        todos = self.tickets.list(pagina=1, tamanho=100)["itens"]
        esperado = {}
        for t in todos:
            if t["environment"] == "HOMOLOGACAO":
                atual = esperado.get(t["script_id"])
                if atual is None or (t["created_at"], t["id"]) > (atual["created_at"], atual["id"]):
                    esperado[t["script_id"]] = t
        r = self.tickets.last_runs([1, 2, 3, 4], ["HOMOLOGACAO"])
        self.assertEqual(dict((k, v["id"]) for k, v in r.items()), dict((k, v["id"]) for k, v in esperado.items()))
        self.assertNotIn("log_output", list(r.values())[0])
        so_meus = self.tickets.last_runs([1, 2, 3, 4], None, "op.hml")
        for sid, u in so_meus.items():
            self.assertEqual(self.tickets.get(u["id"])["requested_by"], "op.hml")
        self.assertEqual(self.tickets.last_runs([], None), {})


class TestCatalogoRotinas(_Base):

    def test_cartoes_iguais_ao_disparo_e_ultima_no_escopo(self):
        ctx = self.ctx["op.hml"]
        grupos = self.svc.routine_catalog(ctx)
        ids = sorted(c["id"] for g in grupos for c in g["cartoes"])
        self.assertEqual(ids, sorted(s["id"] for g in self.svc.available_scripts(ctx) for s in g["scripts"]))
        for g in grupos:
            for c in g["cartoes"]:
                self.assertTrue(c["environments"])
                if c["ultima"]:
                    t = self.tickets.get(c["ultima"]["id"])
                    self.assertIn(t["environment"], ctx["environments"])
                    self.assertTrue(c["ultima"]["quando"].startswith(u"há "))

    def test_sem_ver_logs_so_os_proprios(self):
        ctx = self._sem("op.hml", "VIEW_LOGS")
        for g in self.svc.routine_catalog(ctx):
            for c in g["cartoes"]:
                if c["ultima"]:
                    self.assertEqual(self.tickets.get(c["ultima"]["id"])["requested_by"], "op.hml")

    def test_perguntas_com_obrigatorio(self):
        cartoes = dict((c["name"], c) for g in self.svc.routine_catalog(self.ctx["admin"]) for c in g["cartoes"])
        perguntas = cartoes["carga_diaria"]["perguntas"]
        self.assertIn({"rotulo": u"Data de Referencia", "required": True}, perguntas)

    def test_sem_exec_script_vazio(self):
        self.assertEqual(self.svc.routine_catalog(self._sem("op.hml", "EXEC_SCRIPT")), [])



class TestHistoricoScript(_Base):
    """CR-004 U7 (README §5.8)."""

    def test_contrato_sem_lob_ordenado_e_limitado(self):
        desde = self.tickets.now() - datetime.timedelta(days=30)
        itens = self.tickets.script_history(1, desde)
        self.assertTrue(itens)
        self.assertEqual(set(itens[0]), {"id", "status", "status_reason", "created_at", "started_at", "finished_at"})
        self.assertEqual(itens, sorted(itens, key=lambda t: (t["created_at"], t["id"])))
        self.assertEqual(len(self.tickets.script_history(1, desde, limite=2)), 2)
        self.assertTrue(all(self.tickets.get(t["id"])["environment"] == "HOMOLOGACAO"
                            for t in self.tickets.script_history(1, desde, ["HOMOLOGACAO"])))

    def test_numeros_batem_com_o_grafico_e_a_taxa(self):
        h = self.svc.script_history(self.ctx["admin"], "1")
        c = h["contagem"]
        self.assertEqual(sum(c.values()), h["total"])
        por_dia = sum(sum(d[k] for k in c) for d in h["dias"])
        self.assertEqual(por_dia, h["total"])
        self.assertEqual(len(h["dias"]), 30)
        terminados = c["certo"] + c["erro"] + c["cancelado"]
        if terminados:
            self.assertEqual(h["taxa"], int(round(100.0 * c["certo"] / terminados)))
            self.assertTrue(h["frase_taxa"].startswith(u"De cada 10 vezes,"))
        self.assertEqual(h["filtro_lista"]["script"], 1)

    def test_fora_das_rotinas_e_404(self):
        from repo_errors import RepoNotFound
        with self.assertRaises(RepoNotFound):
            self.svc.script_history(self.ctx["op.hml"], "5")  # backup_extra: inativo
        with self.assertRaises(RepoNotFound):
            self.svc.script_history(self._sem("op.hml", "EXEC_SCRIPT"), "1")

    def test_escopo_sem_ver_logs_so_os_proprios(self):
        h = self.svc.script_history(self._sem("op.hml", "VIEW_LOGS"), "1")
        desde = self.tickets.now() - datetime.timedelta(days=30)
        self.assertEqual(h["total"], len(self.tickets.script_history(1, desde, None, "op.hml")))


class TestBarrasEmpilhadas(unittest.TestCase):

    def test_geometria(self):
        import ui_helpers
        dias = [{"rotulo": "01/10", "certo": 2, "erro": 1, "cancelado": 0, "andamento": 0},
                {"rotulo": "02/10", "certo": 0, "erro": 0, "cancelado": 0, "andamento": 0}]
        g = ui_helpers.barras_empilhadas(dias, largura=200, altura=100)
        self.assertEqual(g["maximo"], 3)
        self.assertEqual([b["classe"] for b in g["barras"]], ["sss-graf-certo", "sss-graf-erro"])
        certo, erro = g["barras"]
        self.assertLess(erro["y"], certo["y"])  # empilhado de baixo para cima
        self.assertIn(u"01/10: Deu erro — 1", erro["titulo"])
        self.assertEqual(ui_helpers.barras_empilhadas([], 200, 100)["barras"], [])


if __name__ == "__main__":
    unittest.main()
