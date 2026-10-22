# -*- coding: utf-8 -*-
"""Testes de admin_profiles_service.py no padrao de CRUD (docs/ADMIN_CRUD_PATTERN.md) e do CR-003 P4.

A matriz e a protecao do ultimo administrador tambem sao cobertas em test_rbac.py.
"""
import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

import admin_crud
import admin_profiles_service as perfis_mod
import auth_service
import repo_factory
import security
from admin_crud import GENERAL_FIELD, AccessDenied, OperationDenied
from admin_profiles_service import AdminProfilesService
from repo_errors import RepoConflict, RepoNotFound

IP = "10.7.7.7"
SESSIONS = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0},
    "op.prod": {"usuario_id": 2, "login": "op.prod", "perfil_id": 2, "perm_versao": 1, "sessao_epoch": 0},
    "consulta": {"usuario_id": 4, "login": "consulta", "perfil_id": 4, "perm_versao": 1, "sessao_epoch": 0},
}
# Seed FAKE: perfil 1 ADMINISTRADOR (unico admin, usuario admin), 4 CONSULTA (usuario consulta).
PERFIL_ADMIN, PERFIL_CONSULTA = 1, 4


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

        self.rbac_repo = repo_factory.get("rbac")
        self.users = repo_factory.get("users")
        self.audit = repo_factory.get("audit")
        self.log = logging.getLogger("sss_teste_perfis_service")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        auth = auth_service.AuthService(self.users, self.rbac_repo, repo_factory.get("catalog"),
                                        self.audit, 5, 900, self.log)
        self.ctx = dict((login, auth.revalidate(sessao)) for login, sessao in SESSIONS.items())
        self.ctx["gestor"] = dict(self.ctx["op.prod"], features=frozenset(["MANAGE_PROFILES"]))
        self.ctx["admin_externo"] = dict(self.ctx["admin"], profile_id=999)
        self.svc = AdminProfilesService(self.rbac_repo, repo_factory.get("catalog"), self.users, self.log)
        self.aud_base = max([a["id"] for a in self.audit.list(pagina=1, tamanho=1000)["itens"]] or [0])

    def _audits(self, acao):
        return [a for a in self.audit.list(filtros={"action": acao}, pagina=1, tamanho=100)["itens"]
                if a["entity"] == "tbsss_profiles" and a["id"] > self.aud_base]

    def _form(self, perfil_id, ator="admin"):
        return self.svc.form(self.ctx[ator], str(perfil_id))

    def _data(self, form, **mudancas):
        dados = {"name": form["name"], "description": form["description"], "is_admin": form["is_admin"],
                 "version": form["version"]}
        dados.update(mudancas)
        return dados

    def _new_admin_with_user(self):
        novo_id, erros = self.svc.save(self.ctx["admin"], IP, None, {"name": "ADMIN_RESERVA", "is_admin": "Y"})
        self.assertEqual(erros, {})
        u = self.users.get_by_login("op.hml")
        self.users.update(u["id"], {"profile_id": novo_id}, ator="teste")
        return novo_id


class TestRegistration(_Base):

    def test_inclusao_duplicado_e_invalidos(self):
        novo_id, erros = self.svc.save(self.ctx["admin"], IP, None, {"name": "OPERADOR_X", "description": "Teste"})
        self.assertEqual(erros, {})
        self.assertEqual(self.rbac_repo.profiles_get(novo_id)["name"], "OPERADOR_X")
        self.assertEqual(len(self._audits("CREATE")), 1)
        _id, erros = self.svc.save(self.ctx["admin"], IP, None, {"name": "OPERADOR_X"})
        self.assertEqual(erros, {"name": perfis_mod.MSG_NAME_DUPLICATE})
        _id, erros = self.svc.save(self.ctx["admin"], IP, None, {"name": "minusculo"})
        self.assertEqual(erros, {"name": perfis_mod.MSG_NAME_INVALID})

    def test_conflito_pela_versao_e_pelo_esperado(self):
        form = self._form(PERFIL_CONSULTA)
        self.rbac_repo.profiles_update(PERFIL_CONSULTA, {"description": "mudou por outro"}, ator="teste")
        _id, erros = self.svc.save(self.ctx["admin"], IP, str(PERFIL_CONSULTA), self._data(form, description="minha"))
        self.assertEqual(erros, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})
        form = self._form(PERFIL_CONSULTA)
        original = self.rbac_repo.profiles_update

        def corrida(*args, **kwargs):
            self.rbac_repo.profiles_update = original
            original(PERFIL_CONSULTA, {"description": "corrida"}, ator="teste")
            return original(*args, **kwargs)
        with mock.patch.object(self.rbac_repo, "profiles_update", side_effect=corrida):
            _id, erros = self.svc.save(self.ctx["admin"], IP, str(PERFIL_CONSULTA),
                                         self._data(form, description="minha"))
        self.assertEqual(erros, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})
        self.assertEqual(self.rbac_repo.profiles_get(PERFIL_CONSULTA)["description"], "corrida")

    def test_sem_funcionalidade_e_inexistente(self):
        with self.assertRaises(AccessDenied):
            self.svc.form(self.ctx["consulta"], str(PERFIL_CONSULTA))
        with self.assertRaises(RepoNotFound):
            self.svc.form(self.ctx["admin"], "999")


class TestDeactivationWithImpact(_Base):

    def test_formulario_lista_os_usuarios_afetados(self):
        # CR-003 P4: o modal mostra os logins (README §4.3.B.1).
        form = self._form(PERFIL_CONSULTA)
        self.assertEqual(form["usuarios_ativos"], 1)
        self.assertEqual(form["usuarios_afetados"], ["consulta"])
        self.assertFalse(form["proprio"])
        self.assertTrue(self._form(PERFIL_ADMIN)["proprio"])

    def test_lista_limitada_a_vinte_logins(self):
        for i in range(perfis_mod.AFFECTED_MAX + 3):
            self.users.insert({"login": "usr.%02d" % i, "name": "U %d" % i, "password_hash": "x",
                                   "profile_id": PERFIL_CONSULTA, "active": "Y"}, ator="teste")
        form = self._form(PERFIL_CONSULTA)
        self.assertEqual(form["usuarios_ativos"], perfis_mod.AFFECTED_MAX + 4)
        self.assertEqual(len(form["usuarios_afetados"]), perfis_mod.AFFECTED_MAX)

    def test_desativacao_audita_impacto(self):
        form = self._form(PERFIL_CONSULTA)
        alterado = self.svc.toggle_active(self.ctx["admin"], IP, str(PERFIL_CONSULTA), form["version"])
        self.assertEqual(alterado["active"], "N")
        aud = self._audits("DEACTIVATE")
        self.assertEqual(len(aud), 1)
        self.assertIn(u"usuários ativos afetados: 1", aud[0]["detail"])


class TestSelfProtection(_Base):
    """CR-003 P4 / D10: o usuario logado nao tira o is_admin nem desativa o proprio perfil."""

    def test_nao_remove_is_admin_do_proprio_perfil_mesmo_com_outro_admin(self):
        self._new_admin_with_user()
        form = self._form(PERFIL_ADMIN)
        _id, erros = self.svc.save(self.ctx["admin"], IP, str(PERFIL_ADMIN), self._data(form, is_admin=None))
        self.assertEqual(erros, {GENERAL_FIELD: perfis_mod.MSG_SELF_ADMIN})
        self.assertEqual(self.rbac_repo.profiles_get(PERFIL_ADMIN)["is_admin"], "Y")
        self.assertEqual(self._audits("UPDATE"), [])

    def test_nao_desativa_o_proprio_perfil_mesmo_com_outro_admin(self):
        self._new_admin_with_user()
        form = self._form(PERFIL_ADMIN)
        with self.assertRaises(OperationDenied) as cm:
            self.svc.toggle_active(self.ctx["admin"], IP, str(PERFIL_ADMIN), form["version"])
        self.assertEqual(cm.exception.mensagem, perfis_mod.MSG_SELF_DEACTIVATE)
        self.assertEqual(self.rbac_repo.profiles_get(PERFIL_ADMIN)["active"], "Y")
        self.assertEqual(self._audits("DEACTIVATE"), [])

    def test_outro_editor_pode_quando_ha_outro_admin(self):
        self._new_admin_with_user()
        form = self._form(PERFIL_ADMIN)
        _id, erros = self.svc.save(self.ctx["admin_externo"], IP, str(PERFIL_ADMIN), self._data(form, is_admin=None))
        self.assertEqual(erros, {})
        self.assertEqual(self.rbac_repo.profiles_get(PERFIL_ADMIN)["is_admin"], "N")

    def test_editar_o_proprio_perfil_sem_tirar_admin_e_permitido(self):
        form = self._form(PERFIL_ADMIN)
        _id, erros = self.svc.save(self.ctx["admin"], IP, str(PERFIL_ADMIN), self._data(form, description="Nova"))
        self.assertEqual(erros, {})
        self.assertEqual(self.rbac_repo.profiles_get(PERFIL_ADMIN)["description"], "Nova")



class TestWhoCan(_Base):
    """CR-004 U8 (README §4.3.B.2)."""

    def _names(self, lista):
        return dict((p["name"], p) for p in lista)

    def test_por_script_bate_com_pode_executar(self):
        import rbac
        q = self.svc.who_can(self.ctx["admin"], script_id="1")
        perfis = self._names(q["profiles"])
        self.assertEqual(perfis["ADMINISTRATOR"]["reason"], u"administrador")
        # Cada perfil listado tem um usuario cujo contexto can_execute no ambiente indicado.
        catalogo = self.svc._catalogo
        script = catalogo.scripts_get(1)
        ambs = dict((a["name"], a) for a in catalogo.environments_list(pagina=1, tamanho=50)["itens"])
        hom = catalogo.homologation_get(1)
        for login in ("op.prod", "consulta"):
            ctx = self.ctx[login]
            podem = set(n for n, a in ambs.items() if rbac.can_execute(ctx, script, a, hom)[0])
            nome = self.rbac_repo.profiles_get(ctx["profile_id"])["name"]
            self.assertEqual(set(perfis[nome]["detalhes"]) if nome in perfis else set(), podem, login)

    def test_por_ambiente_e_inativos(self):
        self.rbac_repo.profiles_update(PERFIL_CONSULTA, {"is_admin": "Y"}, ator="teste")
        self.rbac_repo.profiles_update(PERFIL_CONSULTA, {"active": "N"}, ator="teste")
        amb = [a for a in self.svc._catalogo.environments_list(pagina=1, tamanho=50)["itens"]
               if a["name"] == "HOMOLOGACAO"][0]
        q = self.svc.who_can(self.ctx["admin"], ambiente_id=str(amb["id"]))
        self.assertIn("READ_ONLY", self._names(q["inativos"]))
        self.assertNotIn("READ_ONLY", self._names(q["profiles"]))
        self.assertTrue(self._names(q["profiles"])["ADMINISTRATOR"]["detalhes"])

    def test_script_inativo_avisa_e_acesso(self):
        self.svc._catalogo.scripts_update(5, {"active": "N"}, ator="teste")
        self.assertIn(u"inativo", self.svc.who_can(self.ctx["admin"], script_id="5")["aviso"])
        with self.assertRaises(RepoNotFound):
            self.svc.who_can(self.ctx["admin"], script_id="999")
        with self.assertRaises(AccessDenied):
            self.svc.who_can(self.ctx["consulta"], script_id="1")
        vazio = self.svc.who_can(self.ctx["admin"])
        self.assertIsNone(vazio["script"])
        self.assertTrue(vazio["scripts"])


if __name__ == "__main__":
    unittest.main()
