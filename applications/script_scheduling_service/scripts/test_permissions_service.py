# -*- coding: utf-8 -*-
"""Testes de permissions_service.py: tela "O que eu posso fazer" (README §4.3.E, CR-004 U3) sobre o FAKE."""
import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

import auth_service
import permissions_service as svc_mod
import repo_factory
import security
from permissions_service import PermissionsService
from ticket_service import TicketService

SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0},
    "op.hml": {"usuario_id": 3, "login": "op.hml", "perfil_id": 3, "perm_versao": 1, "sessao_epoch": 0},
    "consulta": {"usuario_id": 4, "login": "consulta", "perfil_id": 4, "perm_versao": 1, "sessao_epoch": 0},
}


class TestPermissoes(unittest.TestCase):

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
        self.rbac_repo = repo_factory.get("rbac")
        log = logging.getLogger("sss_teste_permissoes")
        log.addHandler(logging.NullHandler())
        log.propagate = False
        auth = auth_service.AuthService(repo_factory.get("users"), self.rbac_repo, self.catalog,
                                        repo_factory.get("audit"), 5, 900, log)
        self.ctx = dict((login, auth.revalidate(sessao)) for login, sessao in SESSOES.items())
        disparo = TicketService(self.catalog, repo_factory.get("tickets"), log)
        self.svc = PermissionsService(self.rbac_repo, self.catalog, disparo, log)
        self.disparo = disparo
        self.n_auditoria = repo_factory.get("audit").list(pagina=1, tamanho=1)["total"]

    def test_admin_ve_frase_e_todas_as_telas(self):
        d = self.svc.build(self.ctx["admin"])
        self.assertEqual(d["frase_admin"], svc_mod.ADMIN_PHRASE)
        self.assertEqual(len(d["telas"]), 10)
        self.assertEqual(d["ausentes"], [])
        rotas = dict((t["code"], t["rota"]) for t in d["telas"])
        self.assertEqual(rotas["MANAGE_PROFILES"], ("admin_perfis", "lista"))
        self.assertIsNone(rotas["CANCEL_TICKET"])  # acao, nao tela

    def test_sem_exec_script_mostra_frase_e_motivo(self):
        d = self.svc.build(self.ctx["consulta"])
        self.assertFalse(d["pode_executar"])
        self.assertEqual(d["frase_sem_exec"], svc_mod.NO_EXEC_PHRASE)
        self.assertEqual(d["scripts"], [])
        self.assertTrue(all(a["reason"] == svc_mod.REASON_NO_FEATURE for a in d["ausentes"]))
        self.assertEqual([t["code"] for t in d["telas"]], ["VIEW_LOGS"])

    def test_scripts_e_ambientes_iguais_aos_do_disparo(self):
        ctx = self.ctx["op.hml"]
        d = self.svc.build(ctx)
        esperado = sorted(s["id"] for g in self.disparo.available_scripts(ctx) for s in g["scripts"])
        self.assertEqual(sorted(s["id"] for s in d["scripts"]), esperado)
        for s in d["scripts"]:
            self.assertTrue(s["environments"])
            self.assertTrue(set(s["environments"]) <= set(ctx["environments"]))

    def test_motivos_e_catalogo_nao_vazado(self):
        ctx = dict(self.ctx["op.hml"])
        # Script do perfil desativado e script do perfil sem homologacao nos ambientes dele.
        sid_inativo = sorted(ctx["scripts"])[0]
        self.catalog.scripts_update(sid_inativo, {"active": "N"}, ator="teste")
        novo = self.catalog.scripts_insert({"name": "So em PRODUCAO", "interpreter": "PYTHON3",
                                              "path_file": "/opt/scripts/x.py",
                                              "param_type": "NONE"}, ator="teste")["id"]
        prod = [a for a in self.catalog.environments_list(pagina=1, tamanho=50)["itens"] if a["name"] == "PRODUCAO"][0]
        self.catalog.homologation_save(novo, [prod["id"]], ator="teste")
        ctx["scripts"] = frozenset(ctx["scripts"]) | frozenset([novo])
        ctx["environments"] = frozenset(a for a in ctx["environments"] if a != "PRODUCAO")
        d = self.svc.build(ctx)
        motivos = dict((a["name"], a["reason"]) for a in d["ausentes"])
        nome_inativo = self.catalog.scripts_get(sid_inativo)["name"]
        self.assertEqual(motivos[nome_inativo], svc_mod.REASON_SCRIPT_INACTIVE)
        self.assertEqual(motivos["So em PRODUCAO"], svc_mod.REASON_NOT_HOMOLOGATED)
        fora = set(s["name"] for s in self.catalog.scripts_list(pagina=1, tamanho=100)["itens"]
                   if s["id"] not in ctx["scripts"])
        self.assertFalse(fora & set(motivos))
        self.assertFalse(fora & set(s["name"] for s in d["scripts"]))

    def test_nao_grava_nem_audita(self):
        self.svc.build(self.ctx["op.hml"])
        self.assertEqual(repo_factory.get("audit").list(pagina=1, tamanho=1)["total"], self.n_auditoria)


if __name__ == "__main__":
    unittest.main()
