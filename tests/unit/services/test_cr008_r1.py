# -*- coding: utf-8 -*-
"""CR-008 R1: administrador so por administrador (E1), sessao revogavel (E2) e regex com quantificador largo (R-06)."""
from tests.support import _testenv  # noqa: F401

import datetime
import logging
import os
import re
import time
import unittest
from unittest import mock

from sss.services import admin_profiles_service as perfis_mod
from sss.services import admin_users_service as usr_mod
from sss.services import auth_service
from sss.core import params_compiler
from sss.persistence import repo_factory
from sss.core import security
from sss.services.admin_crud import GENERAL_FIELD, OperationDenied
from sss.services.admin_profiles_service import AdminProfilesService
from sss.services.admin_users_service import AdminUsersService
from sss.core.params_compiler import ParamError

IP = "10.8.8.8"
DEV_PASSWORD = "senha-dev-de-teste-123"
NEW_PASSWORD = "Nova-Senha-Forte-2026"
NOW = datetime.datetime(2026, 10, 17, 9, 0, 0)
U_ADMIN, U_OPPROD, U_OPHML = 1, 2, 3
P_ADMIN, P_OPPROD, P_CONSULTA = 1, 2, 4


def _session(uid, login, profile_id):
    return {"user_id": uid, "login": login, "profile_id": profile_id, "perm_version": 1, "session_epoch": 0}


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
        self.users = repo_factory.get("users")
        self.rbac_repo = repo_factory.get("rbac")
        self.audit = repo_factory.get("audit")
        self.log = logging.getLogger("sss_teste_cr008")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        self.auth = auth_service.AuthService(self.users, self.rbac_repo, repo_factory.get("catalog"),
                                             self.audit, 5, 900, self.log, clock=lambda: NOW)
        self.ctx = {"admin": self.auth.revalidate(_session(U_ADMIN, "admin", P_ADMIN)),
                    "op.prod": self.auth.revalidate(_session(U_OPPROD, "op.prod", P_OPPROD))}
        # Gestor sem perfil de administrador, com as funcionalidades de cadastro (CR-008, F-05).
        self.ctx["gestor"] = dict(self.ctx["op.prod"], features=frozenset(["MANAGE_USERS", "MANAGE_PROFILES"]))
        self.svc_usr = AdminUsersService(self.users, self.rbac_repo, self.log, clock=lambda: NOW)
        self.svc_per = AdminProfilesService(self.rbac_repo, repo_factory.get("catalog"), self.users, self.log)


class TestAdminOnlyByAdmin(_Base):

    def test_gestor_nao_cria_usuario_admin(self):
        data = {"login": "novo.admin", "name": "Novo", "profile_id": str(P_ADMIN),
                 "password": NEW_PASSWORD, "confirmation": NEW_PASSWORD}
        uid, errors = self.svc_usr.save(self.ctx["gestor"], IP, None, data)
        self.assertEqual((uid, errors), (None, {"profile_id": usr_mod.MSG_ADMIN_ONLY}))
        self.assertIsNone(self.users.get_by_login("novo.admin"))
        uid, errors = self.svc_usr.save(self.ctx["gestor"], IP, None, dict(data, profile_id=str(P_CONSULTA)))
        self.assertEqual(errors, {})

    def test_gestor_nao_se_promove_nem_altera_admin(self):
        form = self.svc_usr.form(self.ctx["gestor"], str(U_OPPROD))
        _id, errors = self.svc_usr.save(self.ctx["gestor"], IP, str(U_OPPROD),
                                         {"name": form["name"], "profile_id": str(P_ADMIN), "version": form["version"]})
        self.assertEqual(errors, {GENERAL_FIELD: usr_mod.MSG_ADMIN_ONLY})
        self.assertEqual(self.users.get_by_id(U_OPPROD)["profile_id"], P_OPPROD)
        form = self.svc_usr.form(self.ctx["gestor"], str(U_ADMIN))
        _id, errors = self.svc_usr.save(self.ctx["gestor"], IP, str(U_ADMIN),
                                         {"name": "Outro", "profile_id": str(P_ADMIN), "version": form["version"]})
        self.assertEqual(errors, {GENERAL_FIELD: usr_mod.MSG_ADMIN_ONLY})
        for action in (lambda: self.svc_usr.reset_password(self.ctx["gestor"], IP, str(U_ADMIN), NEW_PASSWORD, NEW_PASSWORD),
                     lambda: self.svc_usr.unlock(self.ctx["gestor"], IP, str(U_ADMIN)),
                     lambda: self.svc_usr.toggle_active(self.ctx["gestor"], IP, str(U_ADMIN), form["version"])):
            with self.assertRaises(OperationDenied) as cm:
                action()
            self.assertEqual(cm.exception.message, usr_mod.MSG_ADMIN_ONLY)
        admin = self.users.get_by_id(U_ADMIN)
        self.assertEqual((admin["active"], admin["session_epoch"]), ("Y", 0))

    def test_gestor_altera_usuario_comum_e_admin_altera_admin(self):
        self.assertEqual(self.svc_usr.reset_password(self.ctx["gestor"], IP, str(U_OPHML), NEW_PASSWORD, NEW_PASSWORD), {})
        form = self.svc_usr.form(self.ctx["admin"], str(U_OPHML))
        _id, errors = self.svc_usr.save(self.ctx["admin"], IP, str(U_OPHML),
                                         {"name": form["name"], "profile_id": str(P_ADMIN), "version": form["version"]})
        self.assertEqual(errors, {})

    def test_gestor_nao_marca_admin_nem_mexe_no_proprio_perfil(self):
        _id, errors = self.svc_per.save(self.ctx["gestor"], IP, None, {"name": "SUPORTE", "is_admin": "Y"})
        self.assertEqual(errors, {GENERAL_FIELD: perfis_mod.MSG_ADMIN_ONLY})
        form = self.svc_per.form(self.ctx["gestor"], str(P_OPPROD))
        _id, errors = self.svc_per.save(self.ctx["gestor"], IP, str(P_OPPROD),
                                         {"name": form["name"], "description": "nova", "version": form["version"]})
        self.assertEqual(errors, {GENERAL_FIELD: perfis_mod.MSG_ADMIN_ONLY})
        matrix = self.rbac_repo.matrix_get(P_OPPROD)
        all_value = [f["id"] for f in self.rbac_repo.features_list()]
        diff, errors = self.svc_per.save_matrix(self.ctx["gestor"], IP, str(P_OPPROD), [str(i) for i in all_value],
                                                 [str(i) for i in matrix["ambs"]], [str(i) for i in matrix["scrs"]],
                                                 str(self.rbac_repo.profiles_get(P_OPPROD)["perm_version"]))
        self.assertEqual((diff, errors), (None, {GENERAL_FIELD: perfis_mod.MSG_ADMIN_ONLY}))
        self.assertEqual(self.rbac_repo.matrix_get(P_OPPROD), matrix)
        # Perfil comum de outra pessoa continua editavel pelo gestor.
        form = self.svc_per.form(self.ctx["gestor"], str(P_CONSULTA))
        _id, errors = self.svc_per.save(self.ctx["gestor"], IP, str(P_CONSULTA),
                                         {"name": form["name"], "description": "leitura", "version": form["version"]})
        self.assertEqual(errors, {})


class TestRevocableSession(_Base):

    def _epoch(self, uid):
        return self.users.get_by_id(uid)["session_epoch"]

    def test_eventos_que_revogam(self):
        session = _session(U_OPHML, "op.hml", 3)
        self.assertIsNotNone(self.auth.revalidate(session))
        self.svc_usr.reset_password(self.ctx["admin"], IP, str(U_OPHML), NEW_PASSWORD, NEW_PASSWORD)
        self.assertEqual(self._epoch(U_OPHML), 1)
        self.assertIsNone(self.auth.revalidate(session))
        session["session_epoch"] = 1
        self.assertIsNotNone(self.auth.revalidate(session))
        form = self.svc_usr.form(self.ctx["admin"], str(U_OPHML))
        self.svc_usr.save(self.ctx["admin"], IP, str(U_OPHML),
                            {"name": "Outro nome", "profile_id": str(3), "version": form["version"]})
        self.assertEqual(self._epoch(U_OPHML), 1, "so o nome mudou")
        self.svc_usr.save(self.ctx["admin"], IP, str(U_OPHML),
                            {"name": "Outro nome", "profile_id": str(P_CONSULTA),
                             "version": self.svc_usr.form(self.ctx["admin"], str(U_OPHML))["version"]})
        self.assertEqual(self._epoch(U_OPHML), 2)

    def test_logout_derruba_todas_as_sessoes_e_audita(self):
        other = _session(U_OPPROD, "op.prod", P_OPPROD)
        self.auth.logout(self.ctx["op.prod"], IP)
        self.assertEqual(self._epoch(U_OPPROD), 1)
        self.assertIsNone(self.auth.revalidate(other))
        logout = [a for a in self.audit.list(filters={"action": "LOGOUT"}, page=1, size=10)["items"]
                  if a["actor"] == "op.prod"]
        self.assertEqual((logout[0]["entity"], logout[0]["entity_id"], logout[0]["source_ip"]),
                         ("tbsss_users", U_OPPROD, IP))
        u = self.users.get_by_id(U_OPPROD)
        self.assertIsNone(u.get("updated_by"), "logout e rotina tecnica, sem updated_*")

    def test_troca_da_propria_senha_mantem_a_sessao_nova(self):
        self.users.set_password(U_OPPROD, security.hash_password(DEV_PASSWORD), NOW, actor="teste")
        epoch = self._epoch(U_OPPROD)
        result, errors = self.auth.change_password(self.ctx["op.prod"], IP, DEV_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)
        self.assertEqual((result, errors), ("OK", {}))
        self.assertEqual(self.auth.session_epoch(U_OPPROD), epoch + 1)
        self.assertIsNotNone(self.auth.revalidate(dict(_session(U_OPPROD, "op.prod", P_OPPROD), session_epoch=epoch + 1)))
        self.assertIsNone(self.auth.revalidate(dict(_session(U_OPPROD, "op.prod", P_OPPROD), session_epoch=epoch)))

    def test_sessao_sem_epoch_e_encerrada(self):
        session = _session(U_OPPROD, "op.prod", P_OPPROD)
        del session["session_epoch"]
        self.assertIsNone(self.auth.revalidate(session))

    def test_vida_maxima(self):
        now = time.time()
        self.assertFalse(security.is_session_expired(now - 11 * 3600, now, 12 * 3600))
        self.assertTrue(security.is_session_expired(now - 13 * 3600, now, 12 * 3600))
        self.assertTrue(security.is_session_expired(None, now, 12 * 3600))


class TestWideQuantifierRegex(unittest.TestCase):

    def _refused_f(self, default_value):
        with self.assertRaises(ParamError):
            params_compiler.validate_registry_regex(default_value)

    def test_largo_conta_como_ilimitado(self):
        self._refused_f(r"\w{0,100}\w{0,100}\w{0,100}x")
        self._refused_f(r"\w*\w{0,11}\w+x")
        params_compiler.validate_registry_regex(r"\w{0,100}\w{0,100}x")
        params_compiler.validate_registry_regex(r"^\d{1,11}$")
        params_compiler.validate_registry_regex(r"^[A-Z]{2}\d{0,10}$")

    def test_teto_de_escolhas_com_ilimitado(self):
        self._refused_f(r"\w*" + r"\d{0,10}" * 4 + "x")
        self._refused_f(r"\d?\d?\d?\d?\w*")
        params_compiler.validate_registry_regex(r"\w*" + r"\d{0,10}" * 3 + "x")
        params_compiler.validate_registry_regex(r"\w{0,10}" * 6 + "x")

    def test_pior_caso_aceito_e_rapido(self):
        for default in (r"\w*\w*" + r"\w{0,10}" * 2 + "@", r"\w{0,10}" * 6 + "x", r"\w{0,500}\w{0,500}x"):
            params_compiler.validate_registry_regex(default)
            start = time.time()
            for value in ("1" * params_compiler.MAX_LENGTH, "a" * (params_compiler.MAX_LENGTH - 1) + "!"):
                re.fullmatch(default, value)
            self.assertLess(time.time() - start, 1.0, default)


if __name__ == "__main__":
    unittest.main()
