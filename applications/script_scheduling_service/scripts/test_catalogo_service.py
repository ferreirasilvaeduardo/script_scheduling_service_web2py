# -*- coding: utf-8 -*-
"""Rotinas disponiveis e historico do script (README §5.8, CR-004 U5/U7) sobre o FAKE."""
import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

import auth_service
import repo_factory
import security
from ticket_service import ServicoTicket

SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1},
    "op.hml": {"usuario_id": 3, "login": "op.hml", "perfil_id": 3, "perm_versao": 1},
}


class _Base(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(security, "ITERACOES", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_SENHA_DEV: "senha-dev-de-teste-123"})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configurar, None)
        self.catalogo = repo_factory.obter("catalogo")
        self.tickets = repo_factory.obter("tickets")
        log = logging.getLogger("sss_teste_catalogo")
        log.addHandler(logging.NullHandler())
        log.propagate = False
        auth = auth_service.ServicoAuth(repo_factory.obter("usuarios"), repo_factory.obter("rbac"), self.catalogo,
                                        repo_factory.obter("auditoria"), 5, 900, log)
        self.ctx = dict((login, auth.revalidar(sessao)) for login, sessao in SESSOES.items())
        self.svc = ServicoTicket(self.catalogo, self.tickets, {"ROTINAS": "/nao/usado"}, (0,), log)

    def _sem(self, login, *funcs):
        ctx = dict(self.ctx[login])
        ctx["funcionalidades"] = frozenset(ctx["funcionalidades"] - set(funcs))
        return ctx


class TestUltimasExecucoes(_Base):

    def test_contrato_ultimo_por_script_no_escopo(self):
        todos = self.tickets.listar(pagina=1, tamanho=100)["itens"]
        esperado = {}
        for t in todos:
            if t["ambiente"] == "HOMOLOGACAO":
                atual = esperado.get(t["script_id"])
                if atual is None or (t["created_at"], t["id"]) > (atual["created_at"], atual["id"]):
                    esperado[t["script_id"]] = t
        r = self.tickets.ultimas_execucoes([1, 2, 3, 4], ["HOMOLOGACAO"])
        self.assertEqual(dict((k, v["id"]) for k, v in r.items()), dict((k, v["id"]) for k, v in esperado.items()))
        self.assertNotIn("log_output", list(r.values())[0])
        so_meus = self.tickets.ultimas_execucoes([1, 2, 3, 4], None, "op.hml")
        for sid, u in so_meus.items():
            self.assertEqual(self.tickets.obter(u["id"])["solicitante"], "op.hml")
        self.assertEqual(self.tickets.ultimas_execucoes([], None), {})


class TestCatalogoRotinas(_Base):

    def test_cartoes_iguais_ao_disparo_e_ultima_no_escopo(self):
        ctx = self.ctx["op.hml"]
        grupos = self.svc.catalogo_rotinas(ctx)
        ids = sorted(c["id"] for g in grupos for c in g["cartoes"])
        self.assertEqual(ids, sorted(s["id"] for g in self.svc.scripts_disponiveis(ctx) for s in g["scripts"]))
        for g in grupos:
            for c in g["cartoes"]:
                self.assertTrue(c["ambientes"])
                if c["ultima"]:
                    t = self.tickets.obter(c["ultima"]["id"])
                    self.assertIn(t["ambiente"], ctx["ambientes"])
                    self.assertTrue(c["ultima"]["quando"].startswith(u"há "))

    def test_sem_ver_logs_so_os_proprios(self):
        ctx = self._sem("op.hml", "VER_LOGS")
        for g in self.svc.catalogo_rotinas(ctx):
            for c in g["cartoes"]:
                if c["ultima"]:
                    self.assertEqual(self.tickets.obter(c["ultima"]["id"])["solicitante"], "op.hml")

    def test_perguntas_com_obrigatorio(self):
        cartoes = dict((c["nome"], c) for g in self.svc.catalogo_rotinas(self.ctx["admin"]) for c in g["cartoes"])
        perguntas = cartoes["carga_diaria"]["perguntas"]
        self.assertIn({"rotulo": u"Data de Referencia", "obrigatorio": True}, perguntas)

    def test_sem_exec_script_vazio(self):
        self.assertEqual(self.svc.catalogo_rotinas(self._sem("op.hml", "EXEC_SCRIPT")), [])


if __name__ == "__main__":
    unittest.main()
