# -*- coding: utf-8 -*-
"""CR-008 R2: ator mascarado fora do quadro Registro (E5), registro do esquema (R-13, R-28) e regras de agendamento."""
import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

import auth_service
import rbac
import repo_factory
import security
import sql_ident
import ui_helpers
from schedules_service import SchedulesService
from ticket_service import TicketService

ADMIN_SESSION = {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0}


class TestVisibleActor(unittest.TestCase):

    def test_regras(self):
        sem = {"login": "op.prod", "features": frozenset(["VIEW_LOGS"])}
        self.assertEqual(ui_helpers.ator_visivel("op.prod", sem), u"você")
        self.assertEqual(ui_helpers.ator_visivel("admin", sem), u"outra pessoa")
        self.assertEqual(ui_helpers.ator_visivel("SYSTEM:agt-host01", sem), "SYSTEM:agt-host01")
        self.assertIsNone(ui_helpers.ator_visivel(None, sem))
        self.assertEqual(ui_helpers.ator_visivel("admin", dict(sem, features=frozenset(["VIEW_AUDIT"]))),
                         "admin")
        self.assertEqual(ui_helpers.ator_visivel("admin", {"is_admin": True}), "admin")


class TestMaskedOwner(unittest.TestCase):

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
        log = logging.getLogger("sss_teste_cr008_r2")
        log.addHandler(logging.NullHandler())
        log.propagate = False
        r = repo_factory.get
        auth = auth_service.AuthService(r("users"), r("rbac"), r("catalog"), r("audit"), 5, 900, log)
        self.admin = auth.revalidate(ADMIN_SESSION)
        tickets = r("tickets")
        ticket = TicketService(catalogo=r("catalog"), tickets=tickets, log=log)
        self.svc = SchedulesService(r("schedules"), r("catalog"), r("users"), ticket, tickets.now, 1461, log)
        # op.prod com o necessario para ver as regras, mas sem VIEW_AUDIT.
        self.operator = dict(self.admin, user_id=2, login="op.prod", is_admin=False,
                             features=frozenset(f for f in self.admin["features"] if f != "VIEW_AUDIT"))

    def test_lista_e_formulario(self):
        responsaveis = set(i["responsavel"] for i in self.svc.list(self.operator, {}, 1, 100)["itens"])
        self.assertTrue(responsaveis)
        self.assertTrue(responsaveis <= {u"você", u"outra pessoa"}, responsaveis)
        self.assertEqual(self.svc.form(self.operator, "2")["regra"]["responsavel"], u"você")
        self.assertEqual(self.svc.form(self.admin, "2")["regra"]["responsavel"], "op.prod")


class TestPauseReason(unittest.TestCase):

    def test_traducao_unica(self):
        # CR-008, R-33: a mesma funcao pura na web e no daemon (README §7.5).
        M = rbac.Reason
        for motivo in (M.USER_INACTIVE, M.SCRIPT_INACTIVE, M.ENVIRONMENT_INACTIVE):
            self.assertEqual(rbac.pause_reason_for(motivo), motivo)
        for motivo in (M.PROFILE_INACTIVE, M.NOT_HOMOLOGATED, M.NO_FEATURE, M.NO_ENVIRONMENT, M.NO_SCRIPT,
                       M.INVALID_DATA):
            self.assertEqual(rbac.pause_reason_for(motivo), "NO_PERMISSION")


class TestSchemaRegistry(unittest.TestCase):

    def test_colunas_novas_e_ampliadas(self):
        usr = sql_ident.TABLES["users"]["colunas"]["session_epoch"]
        self.assertEqual((usr["tipo"], usr["not_null"], usr["default"]), ("NUMBER(10)", True, "0"))
        self.assertEqual(sql_ident.TABLES["agents"]["colunas"]["daemon_pid"]["tipo"], "NUMBER(10)")
        self.assertEqual(sql_ident.SCHEMA_VERSION, 1)

    def test_prefixo_so_minusculo(self):
        self.assertRegex("tbsss_", sql_ident.PREFIX_PATTERN)
        self.assertNotRegex("TBSSS_", sql_ident.PREFIX_PATTERN)


if __name__ == "__main__":
    unittest.main()
