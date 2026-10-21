# -*- coding: utf-8 -*-
"""Quadro Registro nos servicos (CR-006, README §10): formularios de edicao e detalhe do ticket."""
import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

import auth_service
import repo_factory
import security
import ui_helpers
from admin_environments_service import AdminEnvironmentsService
from admin_parameters_service import AdminParametersService
from admin_profiles_service import AdminProfilesService
from admin_scripts_service import AdminScriptsService
from admin_users_service import AdminUsersService
from schedules_service import SchedulesService
from ticket_service import TicketService

IP = "10.9.8.7"
SESSAO_ADMIN = {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0}


class TestRegistroNosServicos(unittest.TestCase):

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
        self.ctx = auth.revalidate(SESSAO_ADMIN)
        tickets = r("tickets")
        self.ticket = TicketService(catalogo=r("catalog"), tickets=tickets, log=log)
        self.servicos = {
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
        for nome, (svc, rid, ler) in self.servicos.items():
            self.assertIsNone(svc.form(self.ctx)["registro"], nome)
            self.assertEqual(svc.form(self.ctx, str(rid))["registro"], ui_helpers.registro(ler(), self.ctx), nome)
            self.assertEqual(svc.form(self.ctx, str(rid))["registro"]["created_by"], "SYSTEM:seed", nome)

    def test_registro_sem_auditoria_nos_servicos_e_aviso_de_pausa(self):
        ctx = dict(self.ctx, is_admin=False, login="op.prod", user_id=2,
                   features=frozenset(f for f in self.ctx["features"] if f != "VIEW_AUDIT"),
                   environments=frozenset(("PRODUCAO", "HOMOLOGACAO")), scripts=frozenset((1, 2, 3, 4, 5, 6)))
        store = repo_factory._fake_store
        for tabela, rid in (("environments", 1), ("profiles", 2), ("users", 2), ("parameters", 1),
                            ("scripts", 1), ("schedules", 5), ("tickets", 17)):
            registro = getattr(store, tabela)[rid]
            registro["created_by"] = "editor.privado"
            registro["updated_by"] = "op.prod"
            registro["updated_at"] = store.now()
        for nome, (svc, rid, ler) in self.servicos.items():
            registro = svc.form(ctx, str(rid))["registro"]
            self.assertEqual((registro["created_by"], registro["updated_by"]),
                             (u"outra pessoa", u"você"), nome)
        regra = self.schedules.form(ctx, "5")["regra"]
        self.assertEqual(regra["registro"]["created_by"], u"outra pessoa")
        self.assertIn(u"por você", regra["pausa_aviso"])
        detalhe = self.ticket.detail(ctx, 17)
        self.assertEqual(detalhe["registro"]["created_by"], u"outra pessoa")
        self.assertNotIn("editor.privado", str(detalhe["registro"]))

    def test_edicao_pela_tela_grava_o_editor(self):
        svc, rid, ler = self.servicos["environments"]
        form = svc.form(self.ctx, str(rid))
        _id, erros = svc.save(self.ctx, IP, str(rid), {"description": "Editada", "connection": form["connection"],
                                                         "version": form["version"]})
        self.assertEqual(erros, {})
        reg = svc.form(self.ctx, str(rid))["registro"]
        self.assertEqual((reg["created_by"], reg["updated_by"]), ("SYSTEM:seed", "admin"))
        self.assertEqual(svc.form(self.ctx, str(rid))["version"] != form["version"], True)

    def test_agendamento_e_ticket(self):
        regra = self.schedules.form(self.ctx, "5")["regra"]
        self.assertEqual(regra["registro"], ui_helpers.registro(self.r("schedules").get(5), self.ctx))
        self.assertEqual(regra["registro"]["created_by"], "SYSTEM:seed")
        self.assertEqual(regra["registro"]["updated_by"], "admin")
        detalhe = self.ticket.detail(self.ctx, 17)
        bruto = self.r("tickets").get(17)
        self.assertEqual(detalhe["registro"], ui_helpers.registro(bruto, self.ctx))
        self.assertTrue(detalhe["registro"]["updated_by"].startswith("SYSTEM:agt-"))


if __name__ == "__main__":
    unittest.main()
