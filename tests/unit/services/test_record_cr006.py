# -*- coding: utf-8 -*-
"""Quadro Registro nos servicos (CR-006, README §10): formularios de edicao e detalhe do ticket."""
from tests.support import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

from sss.services import auth_service
from sss.persistence import repo_factory
from sss.core import security
from sss.ui import ui_helpers
from sss.services.admin_environments_service import AdminEnvironmentsService
from sss.services.admin_parameters_service import AdminParametersService
from sss.services.admin_profiles_service import AdminProfilesService
from sss.services.admin_scripts_service import AdminScriptsService
from sss.services.admin_users_service import AdminUsersService
from sss.services.schedules_service import SchedulesService
from sss.services.ticket_service import TicketService

IP = "10.9.8.7"
ADMIN_SESSION = {"user_id": 1, "login": "admin", "profile_id": 1, "perm_version": 1, "session_epoch": 0}


class TestRecordInServices(unittest.TestCase):

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
        log = logging.getLogger("sss_teste_registro")
        log.addHandler(logging.NullHandler())
        log.propagate = False
        r = repo_factory.get
        self.r = r
        auth = auth_service.AuthService(r("users"), r("rbac"), r("catalog"), r("audit"), 5, 900, log)
        self.ctx = auth.revalidate(ADMIN_SESSION)
        tickets = r("tickets")
        self.ticket = TicketService(catalog=r("catalog"), tickets=tickets, log=log)
        self.services = {
            "environments": (AdminEnvironmentsService(r("catalog"), r("schedules"), log), 1,
                          lambda: r("catalog").environments_get(1)),
            "profiles": (AdminProfilesService(r("rbac"), r("catalog"), r("users"), log), 2,
                       lambda: r("rbac").profiles_get(2)),
            "users": (AdminUsersService(r("users"), r("rbac"), log), 2,
                         lambda: r("users").get_by_id(2)),
            "parameters": (AdminParametersService(r("catalog"), log), 1,
                           lambda: r("catalog").parameters_get(1)),
            "scripts": (AdminScriptsService(r("catalog"), r("schedules"), "DEV", log, tickets.now), 1,
                        lambda: r("catalog").scripts_get(1)),
        }
        self.schedules = SchedulesService(r("schedules"), r("catalog"), r("users"), self.ticket,
                                                tickets.now, 1461, log)

    def test_formularios_de_inclusao_sem_registro_e_de_edicao_com_as_quatro_colunas(self):
        for name, (svc, rid, read) in self.services.items():
            self.assertIsNone(svc.form(self.ctx)["record"], name)
            self.assertEqual(svc.form(self.ctx, str(rid))["record"], ui_helpers.record_info(read(), self.ctx), name)
            self.assertEqual(svc.form(self.ctx, str(rid))["record"]["created_by"], "SYSTEM:seed", name)

    def test_registro_sem_auditoria_nos_servicos_e_aviso_de_pausa(self):
        ctx = dict(self.ctx, is_admin=False, login="op.prod", user_id=2,
                   features=frozenset(f for f in self.ctx["features"] if f != "VIEW_AUDIT"),
                   environments=frozenset(("PRODUCAO", "HOMOLOGACAO")), scripts=frozenset((1, 2, 3, 4, 5, 6)))
        store = repo_factory._fake_store
        for table, rid in (("environments", 1), ("profiles", 2), ("users", 2), ("parameters", 1),
                            ("scripts", 1), ("schedules", 5), ("tickets", 17)):
            record = getattr(store, table)[rid]
            record["created_by"] = "editor.privado"
            record["updated_by"] = "op.prod"
            record["updated_at"] = store.now()
        for name, (svc, rid, read) in self.services.items():
            record = svc.form(ctx, str(rid))["record"]
            self.assertEqual((record["created_by"], record["updated_by"]),
                             (u"outra pessoa", u"você"), name)
        rule = self.schedules.form(ctx, "5")["rule"]
        self.assertEqual(rule["record"]["created_by"], u"outra pessoa")
        self.assertIn(u"por você", rule["pause_warning"])
        detail = self.ticket.detail(ctx, 17)
        self.assertEqual(detail["record"]["created_by"], u"outra pessoa")
        self.assertNotIn("editor.privado", str(detail["record"]))

    def test_edicao_pela_tela_grava_o_editor(self):
        svc, rid, read = self.services["environments"]
        form = svc.form(self.ctx, str(rid))
        _id, errors = svc.save(self.ctx, IP, str(rid), {"description": "Editada", "connection": form["connection"],
                                                         "version": form["version"]})
        self.assertEqual(errors, {})
        reg = svc.form(self.ctx, str(rid))["record"]
        self.assertEqual((reg["created_by"], reg["updated_by"]), ("SYSTEM:seed", "admin"))
        self.assertEqual(svc.form(self.ctx, str(rid))["version"] != form["version"], True)

    def test_agendamento_e_ticket(self):
        rule = self.schedules.form(self.ctx, "5")["rule"]
        self.assertEqual(rule["record"], ui_helpers.record_info(self.r("schedules").get(5), self.ctx))
        self.assertEqual(rule["record"]["created_by"], "SYSTEM:seed")
        self.assertEqual(rule["record"]["updated_by"], "admin")
        detail = self.ticket.detail(self.ctx, 17)
        raw = self.r("tickets").get(17)
        self.assertEqual(detail["record"], ui_helpers.record_info(raw, self.ctx))
        self.assertTrue(detail["record"]["updated_by"].startswith("SYSTEM:agt-"))


if __name__ == "__main__":
    unittest.main()
