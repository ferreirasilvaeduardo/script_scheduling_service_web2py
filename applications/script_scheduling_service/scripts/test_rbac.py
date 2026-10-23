# -*- coding: utf-8 -*-
"""Testes de rbac.py (F2.2): can_execute, can_cancel, can_view_ticket, prioridade e has_feature."""
import _testenv  # noqa: F401

import logging
import os
import re
import unittest
from unittest import mock

import admin_crud
import admin_profiles_service as perfis_mod
import auth_service
import rbac
import repo_factory
import security
from admin_crud import GENERAL_FIELD, AccessDenied, OperationDenied
from admin_profiles_service import AdminProfilesService
from rbac import Reason
from repo_errors import RepoConflict, RepoNotFound, RepoViolation


def _ctx(is_admin=False, active_user="Y", active_profile="Y", features_ids=("EXEC_SCRIPT",),
         envs=("PRODUCAO",), scrs=(1,), login="op.prod"):
    return rbac.user_context({
        "user_id": 2, "login": login, "name": "Operador", "active_user": active_user,
        "profile_id": 2, "profile_name": "OPERADOR", "active_profile": active_profile,
        "is_admin": "Y" if is_admin else "N", "perm_version": 1,
        "features": features_ids, "environments": envs, "scripts": scrs,
    })


SCRIPT = {"id": 1, "name": "carga_diaria", "active": "Y"}
ENVIRONMENT = {"id": 1, "name": "PRODUCAO", "active": "Y"}
HOMOLOGATIONS = [1, 2]


class TestContext(unittest.TestCase):

    def test_formato(self):
        ctx = _ctx()
        for key in ("user_id", "login", "profile_id", "is_admin", "features",
                      "environments", "scripts", "perm_version"):
            self.assertIn(key, ctx)
        self.assertIsInstance(ctx["features"], frozenset)
        self.assertIs(ctx["is_admin"], False)

    def test_flag_n_nao_e_verdadeira(self):
        self.assertIs(_ctx(is_admin=False)["is_admin"], False)
        self.assertIs(_ctx(active_user="N")["active_user"], False)

    def test_modulo_puro_sem_gluon(self):
        with open(rbac.__file__, encoding="utf-8") as f:
            self.assertIsNone(re.search(r"^\s*(from|import)\s+gluon", f.read(), re.MULTILINE))


class TestCanExecute(unittest.TestCase):

    def assertDenied(self, result, reason):
        self.assertEqual(result, (False, reason))

    def test_caso_ok(self):
        self.assertEqual(rbac.can_execute(_ctx(), SCRIPT, ENVIRONMENT, HOMOLOGATIONS), (True, Reason.OK))

    def test_admin_dispensa_dimensoes(self):
        ctx = _ctx(is_admin=True, features_ids=(), envs=(), scrs=())
        self.assertEqual(rbac.can_execute(ctx, SCRIPT, ENVIRONMENT, HOMOLOGATIONS), (True, Reason.OK))

    def test_admin_com_perfil_inativo(self):
        ctx = _ctx(is_admin=True, active_profile="N")
        self.assertDenied(rbac.can_execute(ctx, SCRIPT, ENVIRONMENT, HOMOLOGATIONS), Reason.PROFILE_INACTIVE)

    def test_usuario_inativo(self):
        self.assertDenied(rbac.can_execute(_ctx(active_user="N"), SCRIPT, ENVIRONMENT, HOMOLOGATIONS),
                          Reason.USER_INACTIVE)

    def test_script_inativo(self):
        script = dict(SCRIPT, active="N")
        self.assertDenied(rbac.can_execute(_ctx(), script, ENVIRONMENT, HOMOLOGATIONS), Reason.SCRIPT_INACTIVE)
        self.assertDenied(rbac.can_execute(_ctx(is_admin=True), script, ENVIRONMENT, HOMOLOGATIONS),
                          Reason.SCRIPT_INACTIVE)

    def test_ambiente_inativo(self):
        environment = dict(ENVIRONMENT, active="N")
        self.assertDenied(rbac.can_execute(_ctx(), SCRIPT, environment, HOMOLOGATIONS), Reason.ENVIRONMENT_INACTIVE)
        self.assertDenied(rbac.can_execute(_ctx(is_admin=True), SCRIPT, environment, HOMOLOGATIONS),
                          Reason.ENVIRONMENT_INACTIVE)

    def test_sem_homologacao(self):
        self.assertDenied(rbac.can_execute(_ctx(), SCRIPT, ENVIRONMENT, [2]), Reason.NOT_HOMOLOGATED)
        self.assertDenied(rbac.can_execute(_ctx(is_admin=True), SCRIPT, ENVIRONMENT, []), Reason.NOT_HOMOLOGATED)
        self.assertDenied(rbac.can_execute(_ctx(), SCRIPT, ENVIRONMENT, None), Reason.NOT_HOMOLOGATED)

    def test_sem_exec_script(self):
        self.assertDenied(rbac.can_execute(_ctx(features_ids=("VIEW_LOGS",)), SCRIPT, ENVIRONMENT, HOMOLOGATIONS),
                          Reason.NO_FEATURE)

    def test_sem_ambiente(self):
        self.assertDenied(rbac.can_execute(_ctx(envs=("HOMOLOGACAO",)), SCRIPT, ENVIRONMENT, HOMOLOGATIONS),
                          Reason.NO_ENVIRONMENT)

    def test_sem_script(self):
        self.assertDenied(rbac.can_execute(_ctx(scrs=(2,)), SCRIPT, ENVIRONMENT, HOMOLOGATIONS),
                          Reason.NO_SCRIPT)

    def test_dados_invalidos(self):
        for script, environment in (
            (None, ENVIRONMENT),
            (SCRIPT, None),
            (dict(SCRIPT, id="1"), ENVIRONMENT),
            (dict(SCRIPT, id=True), ENVIRONMENT),
            (SCRIPT, dict(ENVIRONMENT, id=0)),
            (SCRIPT, dict(ENVIRONMENT, name="")),
        ):
            self.assertDenied(rbac.can_execute(_ctx(), script, environment, HOMOLOGATIONS), Reason.INVALID_DATA)
        self.assertDenied(rbac.can_execute(None, SCRIPT, ENVIRONMENT, HOMOLOGATIONS), Reason.INVALID_DATA)

    def test_flag_ativo_somente_s(self):
        for flag in ("", "n", None, "s", "SIM"):
            self.assertDenied(rbac.can_execute(_ctx(), dict(SCRIPT, active=flag), ENVIRONMENT, HOMOLOGATIONS),
                              Reason.SCRIPT_INACTIVE)


class TestHasFeature(unittest.TestCase):

    def test_admin_ativo(self):
        self.assertTrue(rbac.has_feature(_ctx(is_admin=True, features_ids=()), "MANAGE_USERS"))

    def test_admin_perfil_inativo(self):
        self.assertFalse(rbac.has_feature(_ctx(is_admin=True, active_profile="N"), "MANAGE_USERS"))

    def test_nao_admin(self):
        self.assertTrue(rbac.has_feature(_ctx(features_ids=("VIEW_LOGS",)), "VIEW_LOGS"))
        self.assertFalse(rbac.has_feature(_ctx(features_ids=("VIEW_LOGS",)), "MANAGE_USERS"))
        self.assertFalse(rbac.has_feature(None, "VIEW_LOGS"))


class TestTickets(unittest.TestCase):

    TICKET_OWN = {"id": 10, "environment": "PRODUCAO", "requested_by": "op.prod"}
    TICKET_THIRD_PARTY = {"id": 11, "environment": "PRODUCAO", "requested_by": "outro"}
    TICKET_OTHER_ENV = {"id": 12, "environment": "HOMOLOGACAO", "requested_by": "outro"}

    def test_cancelar_proprio_sem_canc_ticket(self):
        ctx = _ctx(features_ids=("EXEC_SCRIPT",))
        self.assertTrue(rbac.can_cancel(ctx, self.TICKET_OWN))
        self.assertFalse(rbac.can_cancel(ctx, self.TICKET_THIRD_PARTY))

    def test_cancelar_proprio_sem_exec_script(self):
        self.assertFalse(rbac.can_cancel(_ctx(features_ids=("VIEW_LOGS",)), self.TICKET_OWN))

    def test_cancelar_terceiro_com_canc_ticket(self):
        # CR-018a: terceiro exige CANCEL_TICKET e VIEW_LOGS no ambiente (quem cancela enxerga o ticket).
        ctx = _ctx(features_ids=("CANCEL_TICKET", "VIEW_LOGS"))
        self.assertTrue(rbac.can_cancel(ctx, self.TICKET_THIRD_PARTY))
        self.assertFalse(rbac.can_cancel(ctx, self.TICKET_OTHER_ENV))
        self.assertFalse(rbac.can_cancel(_ctx(features_ids=("CANCEL_TICKET",)), self.TICKET_THIRD_PARTY))

    def test_cancelar_admin(self):
        self.assertTrue(rbac.can_cancel(_ctx(is_admin=True, features_ids=(), envs=()), self.TICKET_OTHER_ENV))

    def test_cancelar_perfil_inativo(self):
        ctx = _ctx(features_ids=("CANCEL_TICKET", "EXEC_SCRIPT"), active_profile="N")
        self.assertFalse(rbac.can_cancel(ctx, self.TICKET_OWN))

    def test_cancelar_ticket_invalido(self):
        self.assertFalse(rbac.can_cancel(_ctx(), None))
        self.assertFalse(rbac.can_cancel(_ctx(), {"environment": "PRODUCAO", "requested_by": None}))

    def test_ver_ticket(self):
        ctx = _ctx(features_ids=("VIEW_LOGS",))
        self.assertTrue(rbac.can_view_ticket(ctx, self.TICKET_THIRD_PARTY))
        self.assertFalse(rbac.can_view_ticket(ctx, self.TICKET_OTHER_ENV))
        self.assertFalse(rbac.can_view_ticket(_ctx(features_ids=("EXEC_SCRIPT",)), self.TICKET_OWN))
        self.assertTrue(rbac.can_view_ticket(_ctx(is_admin=True, envs=()), self.TICKET_OTHER_ENV))

    def test_ver_ambiente(self):
        self.assertTrue(rbac.can_view_environment(_ctx(), {"name": "PRODUCAO"}))
        self.assertTrue(rbac.can_view_environment(_ctx(), "PRODUCAO"))
        self.assertFalse(rbac.can_view_environment(_ctx(), "HOMOLOGACAO"))
        self.assertFalse(rbac.can_view_environment(_ctx(), None))


class TestPriority(unittest.TestCase):

    def test_admin(self):
        for p in (1, 2, 3, 4):
            self.assertTrue(rbac.allowed_priority(_ctx(is_admin=True), p))

    def test_nao_admin(self):
        self.assertFalse(rbac.allowed_priority(_ctx(), 1))
        for p in (2, 3, 4):
            self.assertTrue(rbac.allowed_priority(_ctx(), p))

    def test_invalidas(self):
        for p in (0, 5, -1, True, "2", None, 2.0):
            self.assertFalse(rbac.allowed_priority(_ctx(is_admin=True), p))

    def test_perfil_inativo(self):
        self.assertFalse(rbac.allowed_priority(_ctx(active_profile="N"), 2))


# ---------------------------------------------------------------- F4.2: perfis e matriz (FAKE)

IP = "10.1.1.1"
SESSIONS = {
    "admin": {"user_id": 1, "login": "admin", "profile_id": 1, "perm_version": 1, "session_epoch": 0},
    "op.prod": {"user_id": 2, "login": "op.prod", "profile_id": 2, "perm_version": 1, "session_epoch": 0},
    "consulta": {"user_id": 4, "login": "consulta", "profile_id": 4, "perm_version": 1, "session_epoch": 0},
}
# Seed FAKE: perfil 1 ADMINISTRADOR (unico admin), 3 OPERATOR_HML (ambiente DESENV inativo associado),
# 4 CONSULTA (VIEW_LOGS; PRODUCAO e HOMOLOGACAO). Funcionalidades 1 EXEC_SCRIPT, 2 VIEW_LOGS, 3 CANCEL_TICKET.
PERFIL_ADMIN, PERFIL_HML, PERFIL_CONSULTA = 1, 3, 4
F_EXEC, F_VER_LOGS = 1, 2
AMB_PRODUCAO, AMB_HOMOLOGACAO, AMB_DESENV = 1, 2, 3


class _BaseProfiles(unittest.TestCase):

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

        self.rbac_repo = repo_factory.get("rbac")
        self.catalog = repo_factory.get("catalog")
        self.users = repo_factory.get("users")
        self.audit = repo_factory.get("audit")
        self.log = logging.getLogger("sss_teste_perfis")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        self.auth = auth_service.AuthService(self.users, self.rbac_repo, self.catalog, self.audit,
                                             5, 900, self.log)
        self.ctx = dict((login, self.auth.revalidate(session)) for login, session in SESSIONS.items())
        # Gestor: perfil nao admin com MANAGE_PROFILES; exercita o ultimo admin sem cair na autoprotecao.
        self.ctx["gestor"] = dict(self.ctx["op.prod"], features=frozenset(["MANAGE_PROFILES"]))
        # Administrador fora do perfil ADMINISTRADOR: exercita a protecao do ultimo admin pelo servico,
        # ja que quem nao e admin nao altera perfil de admin (CR-008, E1).
        self.ctx["admin_externo"] = dict(self.ctx["admin"], profile_id=999)
        self.svc = AdminProfilesService(self.rbac_repo, self.catalog, self.users, self.log)
        self.aud_base = max([a["id"] for a in self.audit.list(page=1, size=1000)["items"]] or [0])

    def _audits(self, action):
        return [a for a in self.audit.list(filters={"action": action}, page=1, size=100)["items"]
                if a["entity"] == "tbsss_profiles" and a["id"] > self.aud_base]

    def _version(self, profile_id):
        return self.rbac_repo.profiles_get(profile_id)["perm_version"]

    def _save_matrix(self, profile_id, features_ids, envs, scrs, version=None):
        version = self._version(profile_id) if version is None else version
        return self.svc.save_matrix(self.ctx["admin"], IP, str(profile_id), [str(x) for x in features_ids],
                                      [str(x) for x in envs], [str(x) for x in scrs], str(version))

    def _matrix(self, profile_id):
        return self.rbac_repo.matrix_get(profile_id)


class TestMatrix(_BaseProfiles):

    def test_diff_formato(self):
        labels = {"funcs": {1: "EXEC_SCRIPT", 2: "VIEW_LOGS"}, "ambs": {1: "PRODUCAO"}, "scrs": {7: "carga"}}
        diff = perfis_mod.matrix_diff({"funcs": {2}, "ambs": set(), "scrs": {7}},
                                      {"funcs": {1}, "ambs": {1}, "scrs": set()}, labels)
        self.assertEqual(diff, "+EXEC_SCRIPT, -VIEW_LOGS, +amb:PRODUCAO, -scr:carga")
        self.assertIsNone(perfis_mod.matrix_diff({"funcs": {1}}, {"funcs": {1}}, labels))

    def test_salvar_matriz_incrementa_versao_e_audita_diff(self):
        before = self._matrix(PERFIL_CONSULTA)
        version = self._version(PERFIL_CONSULTA)
        scrs = [x for x in before["scrs"] if x != 3]
        diff, errors = self._save_matrix(PERFIL_CONSULTA, [F_EXEC], before["ambs"], scrs)
        self.assertEqual(errors, {})
        self.assertEqual(diff, "+EXEC_SCRIPT, -VIEW_LOGS, -scr:cleanup_tmp")
        self.assertEqual(self._version(PERFIL_CONSULTA), version + 1)
        self.assertEqual(sorted(self._matrix(PERFIL_CONSULTA)["funcs"]), [F_EXEC])
        aud = self._audits("PERM_UPDATE")
        self.assertEqual(len(aud), 1)
        self.assertEqual((aud[0]["detail"], aud[0]["entity_id"], aud[0]["actor"]), (diff, PERFIL_CONSULTA, "admin"))

    def test_sem_mudanca_nao_incrementa_nem_audita(self):
        m = self._matrix(PERFIL_CONSULTA)
        version = self._version(PERFIL_CONSULTA)
        diff, errors = self._save_matrix(PERFIL_CONSULTA, m["funcs"], m["ambs"], m["scrs"])
        self.assertEqual((diff, errors), (None, {}))
        self.assertEqual(self._version(PERFIL_CONSULTA), version)
        self.assertEqual(self._audits("PERM_UPDATE"), [])

    def test_efeito_imediato_na_revalidacao(self):
        self.assertIn("VIEW_LOGS", self.ctx["consulta"]["features"])
        m = self._matrix(PERFIL_CONSULTA)
        self._save_matrix(PERFIL_CONSULTA, [], m["ambs"], m["scrs"])
        session = dict(SESSIONS["consulta"])
        ctx = self.auth.revalidate(session)
        self.assertNotIn("VIEW_LOGS", ctx["features"])
        self.assertEqual(ctx["perm_version"], self._version(PERFIL_CONSULTA))

    def test_id_inexistente_ou_invalido_rejeita_tudo(self):
        m = self._matrix(PERFIL_CONSULTA)
        version = self._version(PERFIL_CONSULTA)
        for features, envs, scrs in (([F_EXEC, 999], m["ambs"], m["scrs"]), (m["funcs"], [AMB_PRODUCAO, 77], m["scrs"]),
                                  (m["funcs"], m["ambs"], [1, 404])):
            diff, errors = self._save_matrix(PERFIL_CONSULTA, features, envs, scrs)
            self.assertEqual((diff, errors), (None, {GENERAL_FIELD: perfis_mod.MSG_MATRIX_ID_INVALID}))
        diff, errors = self.svc.save_matrix(self.ctx["admin"], IP, str(PERFIL_CONSULTA), ["1", "x"], [], [],
                                             str(version))
        self.assertEqual(errors, {GENERAL_FIELD: perfis_mod.MSG_MATRIX_ID_INVALID})
        self.assertEqual(self._matrix(PERFIL_CONSULTA), m)
        self.assertEqual(self._version(PERFIL_CONSULTA), version)

    def test_inativo_associado_pode_sair_e_novo_inativo_rejeitado(self):
        # CR-003 D9: associacao a item inativo pode ser removida; nunca readicionada.
        m = self._matrix(PERFIL_HML)
        self.assertIn(AMB_DESENV, m["ambs"])
        diff, errors = self._save_matrix(PERFIL_HML, m["funcs"], m["ambs"] + [AMB_PRODUCAO], m["scrs"])
        self.assertEqual((diff, errors), ("+amb:PRODUCAO", {}))
        self.assertIn(AMB_DESENV, self._matrix(PERFIL_HML)["ambs"])
        m = self._matrix(PERFIL_HML)
        without_dev = [a for a in m["ambs"] if a != AMB_DESENV]
        diff, errors = self._save_matrix(PERFIL_HML, m["funcs"], without_dev, m["scrs"])
        self.assertEqual((diff, errors), ("-amb:DESENV", {}))
        self.assertNotIn(AMB_DESENV, self._matrix(PERFIL_HML)["ambs"])
        diff, errors = self._save_matrix(PERFIL_HML, m["funcs"], without_dev + [AMB_DESENV], m["scrs"])
        self.assertEqual(errors, {GENERAL_FIELD: perfis_mod.MSG_MATRIX_INACTIVE})
        m = self._matrix(PERFIL_CONSULTA)
        diff, errors = self._save_matrix(PERFIL_CONSULTA, m["funcs"], m["ambs"] + [AMB_DESENV], m["scrs"])
        self.assertEqual(errors, {GENERAL_FIELD: perfis_mod.MSG_MATRIX_INACTIVE})

    def test_versao_desatualizada_gera_conflito(self):
        m = self._matrix(PERFIL_CONSULTA)
        old = self._version(PERFIL_CONSULTA)
        self._save_matrix(PERFIL_CONSULTA, [F_EXEC, F_VER_LOGS], m["ambs"], m["scrs"])
        diff, errors = self._save_matrix(PERFIL_CONSULTA, [], m["ambs"], m["scrs"], version=old)
        self.assertEqual(errors, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})
        self.assertEqual(sorted(self._matrix(PERFIL_CONSULTA)["funcs"]), [F_EXEC, F_VER_LOGS])

    def test_tela_da_matriz(self):
        screen = self.svc.matrix(self.ctx["admin"], str(PERFIL_HML))
        envs = [i for g in screen["ambs"] for i in g["items"]]
        dev = [i for i in envs if i["label"] == "DESENV"][0]
        self.assertTrue(dev["checked"] and dev["inactive"])
        self.assertEqual([g["script_group"] for g in screen["funcs"]], ["ADMIN", "OPERATION"])
        self.assertIsNone(screen["admin_warning"])
        self.assertEqual(self.svc.matrix(self.ctx["admin"], str(PERFIL_ADMIN))["admin_warning"], perfis_mod.ADMIN_WARNING)
        screen_query = self.svc.matrix(self.ctx["admin"], str(PERFIL_CONSULTA))
        self.assertNotIn("DESENV", [i["label"] for g in screen_query["ambs"] for i in g["items"]])


class TestLastAdmin(_BaseProfiles):

    def _form(self, profile_id):
        return self.svc.form(self.ctx["admin"], str(profile_id))

    def test_desativar_unico_perfil_admin_e_negado(self):
        form = self._form(PERFIL_ADMIN)
        with self.assertRaises(OperationDenied) as cm:
            self.svc.toggle_active(self.ctx["admin_externo"], IP, str(PERFIL_ADMIN), form["version"])
        self.assertEqual(cm.exception.message, perfis_mod.MSG_LAST_ADMIN)
        profile = self.rbac_repo.profiles_get(PERFIL_ADMIN)
        self.assertEqual((profile["active"], profile["perm_version"]), ("Y", 1))
        self.assertEqual(self._audits("DEACTIVATE"), [])

    def test_remover_is_admin_do_unico_perfil_admin_e_negado(self):
        form = self._form(PERFIL_ADMIN)
        _id, errors = self.svc.save(self.ctx["admin_externo"], IP, str(PERFIL_ADMIN),
                                     {"name": form["name"], "description": form["description"], "is_admin": None,
                                      "version": form["version"]})
        self.assertEqual(errors, {GENERAL_FIELD: perfis_mod.MSG_LAST_ADMIN})
        self.assertEqual(self.rbac_repo.profiles_get(PERFIL_ADMIN)["is_admin"], "Y")

    def test_com_outro_admin_ativo_a_operacao_passa(self):
        new_id, errors = self.svc.save(self.ctx["admin"], IP, None, {"name": "ADMIN_RESERVA", "is_admin": "Y"})
        self.assertEqual(errors, {})
        u = self.users.get_by_login("op.hml")
        self.users.update(u["id"], {"profile_id": new_id}, actor="teste")
        form = self._form(PERFIL_ADMIN)
        changed = self.svc.toggle_active(self.ctx["admin_externo"], IP, str(PERFIL_ADMIN), form["version"])
        self.assertEqual(changed["active"], "N")
        aud = self._audits("DEACTIVATE")
        self.assertEqual(len(aud), 1)
        self.assertIn(u"usuários ativos afetados: 1", aud[0]["detail"])

    def test_perfil_admin_sem_usuarios_nao_conta_como_admin_ativo(self):
        # Um segundo perfil admin sem usuarios nao livra o ultimo admin real.
        self.svc.save(self.ctx["admin"], IP, None, {"name": "ADMIN_VAZIO", "is_admin": "Y"})
        form = self._form(PERFIL_ADMIN)
        with self.assertRaises(OperationDenied) as cm:
            self.svc.toggle_active(self.ctx["admin_externo"], IP, str(PERFIL_ADMIN), form["version"])
        self.assertEqual(cm.exception.message, perfis_mod.MSG_LAST_ADMIN)

    def test_quem_nao_e_admin_nao_altera_perfil_admin(self):
        form = self._form(PERFIL_ADMIN)
        with self.assertRaises(OperationDenied) as cm:
            self.svc.toggle_active(self.ctx["gestor"], IP, str(PERFIL_ADMIN), form["version"])
        self.assertEqual(cm.exception.message, perfis_mod.MSG_ADMIN_ONLY)
        _id, errors = self.svc.save(self.ctx["gestor"], IP, str(PERFIL_ADMIN),
                                     {"name": form["name"], "description": form["description"], "is_admin": None,
                                      "version": form["version"]})
        self.assertEqual(errors, {GENERAL_FIELD: perfis_mod.MSG_ADMIN_ONLY})
        self.assertEqual(self.rbac_repo.profiles_get(PERFIL_ADMIN)["is_admin"], "Y")

    def test_protecao_e_atomica_no_repositorio(self):
        with self.assertRaises(RepoViolation) as cm:
            self.rbac_repo.profiles_update(PERFIL_ADMIN, {"active": "N"}, actor="teste")
        self.assertEqual(cm.exception.constraint, "sss_ultimo_admin")
        self.assertEqual(self.rbac_repo.lock_active_admins(), [1])


class TestProfileRegistration(_BaseProfiles):

    def test_inclusao_validacoes_e_auditoria(self):
        for name, msg in (("", perfis_mod.MSG_NAME_REQUIRED), ("auditor", perfis_mod.MSG_NAME_INVALID),
                          ("READ_ONLY", perfis_mod.MSG_NAME_DUPLICATE)):
            _id, errors = self.svc.save(self.ctx["admin"], IP, None, {"name": name})
            self.assertEqual(errors, {"name": msg}, name)
        pid, errors = self.svc.save(self.ctx["admin"], IP, None, {"name": "AUDITOR", "description": "Leitura"})
        self.assertEqual(errors, {})
        profile = self.rbac_repo.profiles_get(pid)
        self.assertEqual((profile["is_admin"], profile["active"], profile["perm_version"]), ("N", "Y", 1))
        self.assertIn("name: AUDITOR", self._audits("CREATE")[0]["detail"])

    def test_alteracao_concorrente_e_auditoria(self):
        aba1 = self.svc.form(self.ctx["admin"], str(PERFIL_CONSULTA))
        aba2 = self.svc.form(self.ctx["admin"], str(PERFIL_CONSULTA))
        self.assertEqual(aba1["active_users"], 1)
        _id, errors = self.svc.save(self.ctx["admin"], IP, str(PERFIL_CONSULTA),
                                     {"name": "CONSULTA_GERAL", "description": aba2["description"], "version": aba2["version"]})
        self.assertEqual(errors, {})
        _id, errors = self.svc.save(self.ctx["admin"], IP, str(PERFIL_CONSULTA),
                                     {"name": "READ_ONLY", "description": "x", "version": aba1["version"]})
        self.assertEqual(errors, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})
        aud = self._audits("UPDATE")
        self.assertEqual(len(aud), 1)
        self.assertIn(u"name: READ_ONLY \u2192 CONSULTA_GERAL", aud[0]["detail"])
        self.assertEqual(self._version(PERFIL_CONSULTA), 2)

    def test_reativar(self):
        form = self.svc.form(self.ctx["admin"], str(PERFIL_CONSULTA))
        self.svc.toggle_active(self.ctx["admin"], IP, str(PERFIL_CONSULTA), form["version"])
        form = self.svc.form(self.ctx["admin"], str(PERFIL_CONSULTA))
        with self.assertRaises(RepoConflict):
            self.svc.toggle_active(self.ctx["admin"], IP, str(PERFIL_CONSULTA), "x")
        self.assertEqual(self.svc.toggle_active(self.ctx["admin"], IP, str(PERFIL_CONSULTA), form["version"])["active"], "Y")

    def test_acesso_negado_e_nao_encontrado(self):
        for call in (lambda c: self.svc.list(c, {}, 1, 20), lambda c: self.svc.matrix(c, "1"),
                        lambda c: self.svc.save_matrix(c, IP, "4", [], [], [], "1"),
                        lambda c: self.svc.toggle_active(c, IP, "4", "x")):
            with self.assertRaises(AccessDenied):
                call(self.ctx["op.prod"])
        for pid in ("999", "abc", "0"):
            with self.assertRaises(RepoNotFound):
                self.svc.matrix(self.ctx["admin"], pid)

    def test_filtros(self):
        self.assertEqual(perfis_mod.normalize_filters({"name": "OPER", "active": "Y", "is_admin": "N"}),
                         {"name": "OPER", "active": "Y", "is_admin": "N"})
        self.assertEqual(perfis_mod.normalize_filters({"name": "<x>", "active": "?"}), {})


if __name__ == "__main__":
    unittest.main()
