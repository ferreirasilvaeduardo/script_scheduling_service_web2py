# -*- coding: utf-8 -*-
"""Testes de permissions_service.py: tela "O que eu posso fazer" (README §4.3.E, CR-004 U3) sobre o FAKE."""
from tests.support import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

from sss.services import auth_service
from sss.services import permissions_service as svc_mod
from sss.persistence import repo_factory
from sss.core import security
from sss.services.permissions_service import PermissionsService
from sss.services.ticket_service import TicketService

SESSIONS = {
    "admin": {"user_id": 1, "login": "admin", "profile_id": 1, "perm_version": 1, "session_epoch": 0},
    "op.hml": {"user_id": 3, "login": "op.hml", "profile_id": 3, "perm_version": 1, "session_epoch": 0},
    "consulta": {"user_id": 4, "login": "consulta", "profile_id": 4, "perm_version": 1, "session_epoch": 0},
}


class TestPermissions(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(security, "ITERATIONS", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_DEV_PASSWORD: "senha-dev-de-teste-123"})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configure({"app": {"data_backend": "FAKE"}})
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
        self.ctx = dict((login, auth.revalidate(session)) for login, session in SESSIONS.items())
        trigger = TicketService(self.catalog, repo_factory.get("tickets"), log)
        self.svc = PermissionsService(self.rbac_repo, self.catalog, trigger, log)
        self.trigger = trigger
        self.n_audit = repo_factory.get("audit").list(page=1, size=1)["total"]

    def test_admin_ve_frase_e_todas_as_telas(self):
        d = self.svc.build(self.ctx["admin"])
        self.assertEqual(d["admin_phrase"], svc_mod.ADMIN_PHRASE)
        self.assertEqual(len(d["screens"]), 12)
        self.assertEqual(d["absent"], [])
        routes = dict((t["code"], t["route"]) for t in d["screens"])
        self.assertEqual(routes["DOWNLOAD_OUTPUT"], ("outputs", "index"), "Saidas no menu (CR-020a)")
        self.assertEqual(routes["UPLOAD_INPUT"], ("inputs", "index"), "Entrada no menu (CR-020d)")
        self.assertEqual(routes["MANAGE_PROFILES"], ("admin_profiles", "index"))
        self.assertIsNone(routes["CANCEL_TICKET"])  # acao, nao tela
        # CR-017b: Rodar Scripts leva aos cartoes de Rodar um script; Consultar Tickets, a lista de tickets.
        self.assertEqual(routes["EXEC_SCRIPT"], ("tickets", "catalog"))
        self.assertEqual(routes["VIEW_LOGS"], ("tickets", "index"))

    def test_sem_exec_script_mostra_frase_e_motivo(self):
        d = self.svc.build(self.ctx["consulta"])
        self.assertFalse(d["can_execute"])
        self.assertEqual(d["no_runs_phrase"], svc_mod.NO_EXEC_PHRASE)
        self.assertEqual(d["scripts"], [])
        self.assertTrue(all(a["reason"] == u"seu perfil não tem Rodar Scripts" for a in d["absent"]))
        self.assertEqual([t["code"] for t in d["screens"]], ["VIEW_LOGS"])

    def test_scripts_iguais_aos_do_disparo(self):
        # CR-018b: a tela so conta os scripts; os ambientes de cada um ficam nos cartoes de Rodar um script.
        ctx = self.ctx["op.hml"]
        d = self.svc.build(ctx)
        expected = sorted(s["id"] for g in self.trigger.available_scripts(ctx) for s in g["scripts"])
        self.assertEqual(sorted(s["id"] for s in d["scripts"]), expected)
        self.assertTrue(all(set(s) == {"id", "name"} for s in d["scripts"]))

    def test_motivos_e_catalogo_nao_vazado(self):
        ctx = dict(self.ctx["op.hml"])
        # Script do perfil desativado e script do perfil sem homologacao nos ambientes dele.
        sid_inactive = sorted(ctx["scripts"])[0]
        self.catalog.scripts_update(sid_inactive, {"active": "N"}, actor="teste")
        new = self.catalog.scripts_insert({"name": "So em PRODUCAO", "interpreter": "python3",
                                              "path_file": "/opt/scripts/x.py",
                                              "param_type": "NONE"}, actor="teste")["id"]
        prod = [a for a in self.catalog.environments_list(page=1, size=50)["items"] if a["name"] == "PRODUCAO"][0]
        self.catalog.homologation_save(new, [prod["id"]], actor="teste")
        ctx["scripts"] = frozenset(ctx["scripts"]) | frozenset([new])
        ctx["environments"] = frozenset(a for a in ctx["environments"] if a != "PRODUCAO")
        d = self.svc.build(ctx)
        reasons = dict((a["name"], a["reason"]) for a in d["absent"])
        name_inactive = self.catalog.scripts_get(sid_inactive)["name"]
        self.assertEqual(reasons[name_inactive], svc_mod.REASON_SCRIPT_INACTIVE)
        self.assertEqual(reasons["So em PRODUCAO"], svc_mod.REASON_NOT_HOMOLOGATED)
        outside = set(s["name"] for s in self.catalog.scripts_list(page=1, size=100)["items"]
                   if s["id"] not in ctx["scripts"])
        self.assertFalse(outside & set(reasons))
        self.assertFalse(outside & set(s["name"] for s in d["scripts"]))

    def test_nao_grava_nem_audita(self):
        self.svc.build(self.ctx["op.hml"])
        self.assertEqual(repo_factory.get("audit").list(page=1, size=1)["total"], self.n_audit)


if __name__ == "__main__":
    unittest.main()
