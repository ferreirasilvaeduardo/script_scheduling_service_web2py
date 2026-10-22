# -*- coding: utf-8 -*-
"""Testes de admin_users_service.py e auth_service.change_password (F4.3) sobre o backend FAKE."""
import _testenv  # noqa: F401

import datetime
import logging
import os
import unittest
from unittest import mock

import admin_crud
import admin_users_service as usr_mod
import auth_service
import repo_factory
import security
from admin_crud import GENERAL_FIELD, AccessDenied, OperationDenied
from admin_users_service import AdminUsersService
from repo_errors import RepoConflict, RepoNotFound, RepoViolation

IP = "10.2.2.2"
DEV_PASSWORD = "senha-dev-de-teste-123"
NEW_PASSWORD = "Nova-Senha-Forte-2026"
SESSIONS = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0},
    "op.prod": {"usuario_id": 2, "login": "op.prod", "perfil_id": 2, "perm_versao": 1, "sessao_epoch": 0},
}
# Seed FAKE: admin (1, perfil ADMINISTRADOR, unico admin), op.prod (2), op.hml (3), consulta (4),
# inativo (5) e bloqueado (6, 5 tentativas, bloqueado por 30 min). Perfis 1-4 ativos.
U_ADMIN, U_OPPROD, U_BLOQUEADO = 1, 2, 6
P_ADMIN, P_OPPROD, P_CONSULTA = 1, 2, 4
NOW = datetime.datetime(2026, 10, 15, 9, 0, 0)


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
        self.log = logging.getLogger("sss_teste_usuarios")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        self.auth = auth_service.AuthService(self.users, self.rbac_repo, repo_factory.get("catalog"),
                                             self.audit, 5, 900, self.log, clock=lambda: NOW)
        self.ctx = dict((login, self.auth.revalidate(session)) for login, session in SESSIONS.items())
        # O seed usa o relogio real: o bloqueio do usuario 'bloqueado' e reposicionado a partir de AGORA.
        self.users.update(U_BLOQUEADO, {"locked_until": NOW + datetime.timedelta(minutes=30)}, actor="teste")
        self.svc = AdminUsersService(self.users, self.rbac_repo, self.log, clock=lambda: NOW)
        self.aud_base = max([a["id"] for a in self.audit.list(page=1, size=1000)["itens"]] or [0])

    def _audits(self, action=None):
        filters = {"action": action} if action else None
        return [a for a in self.audit.list(filters=filters, page=1, size=200)["itens"]
                if a["entity"] == "tbsss_users" and a["id"] > self.aud_base]

    def _insert(self, **changes):
        date = {"login": "maria.silva", "name": "Maria Silva", "profile_id": str(P_CONSULTA),
                 "senha": NEW_PASSWORD, "confirmacao": NEW_PASSWORD}
        date.update(changes)
        return self.svc.save(self.ctx["admin"], IP, None, date)

    def _form(self, uid, actor="admin"):
        return self.svc.form(self.ctx[actor], str(uid))

    def _edit(self, uid, actor="admin", **changes):
        f = self._form(uid, actor)
        date = {"name": f["name"], "profile_id": str(f["profile_id"]), "version": f["version"]}
        date.update(changes)
        return self.svc.save(self.ctx[actor], IP, str(uid), date)

    def _without_secret(self, text, *secrets):
        for s in secrets:
            self.assertNotIn(s, text)
        self.assertNotIn("pbkdf2", text)


class TestInsert(_Base):

    def test_auditoria_mostra_perfil_pelo_nome_e_login_sem_espacos(self):
        # CR-003 P6 (README §4.4) e C2.
        _id, errors = self._insert(login=" maria.silva")
        self.assertEqual(errors, {"login": admin_crud.MSG_SPACES})
        uid, errors = self._insert()
        self.assertEqual(errors, {})
        detail = [a for a in self._audits("CREATE") if a["entity_id"] == uid][0]["detail"]
        self.assertIn("perfil: READ_ONLY", detail)
        self.assertNotIn("profile_id", detail)

    def test_inclusao_ok_com_hash_e_auditoria_sem_senha(self):
        uid, errors = self._insert()
        self.assertEqual(errors, {})
        u = self.users.get_by_id(uid)
        self.assertEqual((u["login"], u["name"], u["profile_id"], u["active"]), ("maria.silva", "Maria Silva", P_CONSULTA, "Y"))
        self.assertTrue(security.verify_password(NEW_PASSWORD, u["password_hash"]))
        self.assertEqual(u["password_changed_at"], NOW)
        aud = self._audits("CREATE")
        self.assertEqual(len(aud), 1)
        self.assertIn("login: maria.silva", aud[0]["detail"])
        self._without_secret(aud[0]["detail"], NEW_PASSWORD, u["password_hash"])

    def test_login_invalido_ou_duplicado(self):
        for login in ("Maria", "ab", "a" * 31, "maria silva", u"joão"):
            _uid, errors = self._insert(login=login)
            self.assertEqual(errors.get("login"), usr_mod.MSG_LOGIN_INVALID, login)
        _uid, errors = self._insert(login="op.prod")
        self.assertEqual(errors, {"login": usr_mod.MSG_LOGIN_DUPLICATE})
        self.assertEqual(self._audits("CREATE"), [])

    def test_senha_fraca_e_confirmacao_divergente(self):
        _uid, errors = self._insert(senha="curta", confirmacao="curta")
        self.assertEqual(errors, {"senha": security.validate_password_policy("curta")[0]})
        _uid, errors = self._insert(confirmacao=NEW_PASSWORD + "x")
        self.assertEqual(errors, {"confirmacao": usr_mod.MSG_CONFIRMATION})
        _uid, errors = self._insert(senha="", confirmacao="")
        self.assertEqual(errors, {"senha": usr_mod.MSG_PASSWORD_REQUIRED})

    def test_perfil_inativo_ou_inexistente(self):
        form = self.rbac_repo.profiles_get(P_CONSULTA)
        self.rbac_repo.profiles_update(P_CONSULTA, {"active": "N"}, actor="teste")
        _uid, errors = self._insert()
        self.assertEqual(errors, {"profile_id": usr_mod.MSG_PROFILE_INVALID})
        _uid, errors = self._insert(profile_id="999")
        self.assertEqual(errors, {"profile_id": usr_mod.MSG_PROFILE_INVALID})
        self.assertEqual(form["name"], "READ_ONLY")


class TestEditAndLastAdmin(_Base):

    def test_edicao_ignora_login_e_audita(self):
        _uid, errors = self._edit(U_OPPROD, name="Operador Prod Novo", login="hacker")
        self.assertEqual(errors, {})
        u = self.users.get_by_id(U_OPPROD)
        self.assertEqual((u["login"], u["name"]), ("op.prod", "Operador Prod Novo"))
        self.assertIn("name: Operador Producao", self._audits("UPDATE")[0]["detail"])

    def test_nao_admin_nao_troca_o_proprio_perfil(self):
        # Revisao de 2026-10-20 (CR-008 E1): MANAGE_USERS sem admin nao muda as proprias permissoes.
        manager = dict(self.ctx["op.prod"], features=frozenset({"MANAGE_USERS"}))
        f = self.svc.form(manager, str(U_OPPROD))
        _uid, errors = self.svc.save(manager, IP, str(U_OPPROD),
                                      {"name": f["name"], "profile_id": str(P_CONSULTA), "version": f["version"]})
        self.assertEqual(errors, {usr_mod.GENERAL_FIELD: usr_mod.MSG_ADMIN_ONLY})
        self.assertEqual(self.users.get_by_id(U_OPPROD)["profile_id"], P_OPPROD)
        # O proprio nome, sem trocar de perfil, continua permitido.
        _uid, errors = self.svc.save(manager, IP, str(U_OPPROD),
                                      {"name": "Operador Producao", "profile_id": str(P_OPPROD), "version": f["version"]})
        self.assertEqual(errors, {})
        # O administrador continua trocando o perfil de outros usuarios.
        self.assertEqual(self._edit(U_BLOQUEADO, profile_id=str(P_CONSULTA))[1], {})

    def test_troca_de_perfil_do_ultimo_admin_negada(self):
        # Outro administrador nao pode tirar o unico admin do perfil admin: novo admin cria o cenario.
        new, _ = self._insert(login="admin2", profile_id=str(P_ADMIN))
        self.users.update(new, {"active": "N"}, actor="teste")
        ctx2 = dict(self.ctx["admin"], user_id=new, login="admin2")
        f = self.svc.form(ctx2, str(U_ADMIN))
        _uid, errors = self.svc.save(ctx2, IP, str(U_ADMIN), {"name": f["name"], "profile_id": str(P_CONSULTA),
                                                               "version": f["version"]})
        self.assertEqual(errors, {GENERAL_FIELD: usr_mod.MSG_LAST_ADMIN})
        self.assertEqual(self.users.get_by_id(U_ADMIN)["profile_id"], P_ADMIN)

    def test_desativacao_do_ultimo_admin_negada(self):
        new, _ = self._insert(login="gestor", profile_id=str(P_OPPROD))
        ctx_manager = dict(self.ctx["admin"], user_id=new, login="gestor")
        f = self.svc.form(ctx_manager, str(U_ADMIN))
        with self.assertRaises(OperationDenied) as cm:
            self.svc.toggle_active(ctx_manager, IP, str(U_ADMIN), f["version"])
        self.assertEqual(cm.exception.message, usr_mod.MSG_LAST_ADMIN)
        self.assertEqual(self.users.get_by_id(U_ADMIN)["active"], "Y")
        self.assertEqual(self._audits("DEACTIVATE"), [])

    def test_com_dois_admins_desativar_um_passa(self):
        new, _ = self._insert(login="admin2", profile_id=str(P_ADMIN))
        f = self._form(new)
        changed = self.svc.toggle_active(self.ctx["admin"], IP, str(new), f["version"])
        self.assertEqual(changed["active"], "N")
        self.assertNotIn("password_hash", changed)
        self.assertEqual(len(self._audits("DEACTIVATE")), 1)

    def test_autodesativacao_e_autoperfil_negados(self):
        new, _ = self._insert(login="admin2", profile_id=str(P_ADMIN))
        with self.assertRaises(OperationDenied) as cm:
            self.svc.toggle_active(self.ctx["admin"], IP, str(U_ADMIN), self._form(U_ADMIN)["version"])
        self.assertEqual(cm.exception.message, usr_mod.MSG_SELF_DEACTIVATE)
        _uid, errors = self._edit(U_ADMIN, profile_id=str(P_CONSULTA))
        self.assertEqual(errors, {GENERAL_FIELD: usr_mod.MSG_SELF_PROFILE})
        _uid, errors = self._edit(U_ADMIN, name="Admin Renomeado")
        self.assertEqual(errors, {})
        self.assertEqual(new, self.users.get_by_login("admin2")["id"])

    def test_desativado_tem_sessao_encerrada_na_revalidacao(self):
        f = self._form(U_OPPROD)
        self.svc.toggle_active(self.ctx["admin"], IP, str(U_OPPROD), f["version"])
        self.assertIsNone(self.auth.revalidate(dict(SESSIONS["op.prod"])))

    def test_conflito_de_edicao(self):
        f = self._form(U_OPPROD)
        self._edit(U_OPPROD, name="Primeira")
        _uid, errors = self.svc.save(self.ctx["admin"], IP, str(U_OPPROD),
                                      {"name": "Segunda", "profile_id": str(P_OPPROD), "version": f["version"]})
        self.assertEqual(errors, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})
        with self.assertRaises(RepoConflict):
            self.svc.toggle_active(self.ctx["admin"], IP, str(U_OPPROD), f["version"])

    def test_ultimo_admin_atomico_no_repositorio(self):
        with self.assertRaises(RepoViolation) as cm:
            self.users.update(U_ADMIN, {"profile_id": P_CONSULTA}, actor="teste")
        self.assertEqual(cm.exception.constraint, "sss_ultimo_admin")
        with self.assertRaises(RepoViolation):
            self.users.update(U_ADMIN, {"active": "N"}, actor="teste")


class TestPasswordAndLock(_Base):

    def test_redefinicao_zera_bloqueio_e_audita_sem_senha(self):
        self.assertTrue(self._form(U_BLOQUEADO)["bloqueado"])
        errors = self.svc.reset_password(self.ctx["admin"], IP, str(U_BLOQUEADO), NEW_PASSWORD, NEW_PASSWORD)
        self.assertEqual(errors, {})
        u = self.users.get_by_id(U_BLOQUEADO)
        self.assertEqual((u["failed_attempts"], u["locked_until"], u["password_changed_at"]), (0, None, NOW))
        self.assertTrue(security.verify_password(NEW_PASSWORD, u["password_hash"]))
        aud = self._audits("UPDATE")
        self.assertEqual([a["detail"] for a in aud], ["senha redefinida"])
        self._without_secret(repr(self.audit.list(page=1, size=1000)), NEW_PASSWORD, u["password_hash"])

    def test_redefinicao_valida_politica_e_confirmacao(self):
        self.assertEqual(self.svc.reset_password(self.ctx["admin"], IP, str(U_OPPROD), "fraca", "fraca"),
                         {"senha": security.validate_password_policy("fraca")[0]})
        self.assertEqual(self.svc.reset_password(self.ctx["admin"], IP, str(U_OPPROD), NEW_PASSWORD, "x"),
                         {"confirmacao": usr_mod.MSG_CONFIRMATION})

    def test_redefinir_a_propria_senha_pela_administracao_negado(self):
        with self.assertRaises(OperationDenied) as cm:
            self.svc.reset_password(self.ctx["admin"], IP, str(U_ADMIN), NEW_PASSWORD, NEW_PASSWORD)
        self.assertEqual(cm.exception.message, usr_mod.MSG_SELF_PASSWORD)

    def test_desbloquear(self):
        changed = self.svc.unlock(self.ctx["admin"], IP, str(U_BLOQUEADO))
        self.assertEqual((changed["failed_attempts"], changed["locked_until"]), (0, None))
        self.assertTrue(self._audits("UPDATE")[0]["detail"].startswith("desbloqueado"))

    def test_minha_senha_com_atual_errada(self):
        res, errors = self.auth.change_password(self.ctx["op.prod"], IP, "errada-errada-1", NEW_PASSWORD, NEW_PASSWORD)
        self.assertEqual((res, errors), ("ERRO", {"senha_atual": auth_service.MSG_CURRENT_PASSWORD}))
        u = self.users.get_by_id(U_OPPROD)
        self.assertEqual(u["failed_attempts"], 1)
        self.assertTrue(security.verify_password(DEV_PASSWORD, u["password_hash"]))
        failures = [a for a in self.audit.list(filters={"action": "LOGIN_FAILED"}, page=1, size=50)["itens"]
                  if a["id"] > self.aud_base]
        self.assertEqual(len(failures), 1)

    def test_minha_senha_bloqueia_apos_limite(self):
        for _ in range(4):
            self.assertEqual(self.auth.change_password(self.ctx["op.prod"], IP, "errada-errada-1", NEW_PASSWORD,
                                                    NEW_PASSWORD)[0], "ERRO")
        res, _errors = self.auth.change_password(self.ctx["op.prod"], IP, "errada-errada-1", NEW_PASSWORD, NEW_PASSWORD)
        self.assertEqual(res, "BLOQUEADO")
        self.assertIsNotNone(self.users.get_by_id(U_OPPROD)["locked_until"])
        # Mesmo com a senha certa, a conta bloqueada nao troca a senha.
        self.assertEqual(self.auth.change_password(self.ctx["op.prod"], IP, DEV_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)[0],
                         "BLOQUEADO")

    def test_minha_senha_ok_e_validacoes(self):
        res, errors = self.auth.change_password(self.ctx["op.prod"], IP, DEV_PASSWORD, "curta", "curta")
        self.assertEqual(res, "ERRO")
        self.assertIn("nova", errors)
        res, errors = self.auth.change_password(self.ctx["op.prod"], IP, DEV_PASSWORD, NEW_PASSWORD, "outra")
        self.assertEqual(errors, {"confirmacao": auth_service.MSG_CONFIRMATION})
        res, errors = self.auth.change_password(self.ctx["op.prod"], IP, DEV_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)
        self.assertEqual((res, errors), ("OK", {}))
        u = self.users.get_by_id(U_OPPROD)
        self.assertTrue(security.verify_password(NEW_PASSWORD, u["password_hash"]))
        aud = self._audits("UPDATE")
        self.assertEqual((aud[0]["actor"], aud[0]["detail"]), ("op.prod", u"senha alterada pelo próprio usuário"))


class TestListAndAccess(_Base):

    def test_relogio_padrao_e_o_do_banco(self):
        # CR-003 P3: sem relogio injetado, o service usa o SYSDATE do repositorio (nunca o do no web).
        svc = AdminUsersService(self.users, self.rbac_repo, self.log)
        future = self.users.now() + datetime.timedelta(minutes=5)
        self.assertTrue(svc.is_locked({"locked_until": future}))
        self.assertFalse(svc.is_locked({"locked_until": self.users.now() - datetime.timedelta(seconds=1)}))

    def test_lista_sem_hash_com_bloqueio_e_filtros(self):
        page = self.svc.list(self.ctx["admin"], {}, 1, 20)
        self.assertEqual(page["total"], 6)
        for item in page["itens"]:
            self.assertNotIn("password_hash", item)
        locked = [i for i in page["itens"] if i["login"] == "bloqueado"][0]
        self.assertTrue(locked["bloqueado"])
        self.assertEqual(locked["perfil_nome"], "OPERATOR_PROD")
        self.assertEqual([i["login"] for i in self.svc.list(self.ctx["admin"], {"state": "B"}, 1, 20)["itens"]],
                         ["bloqueado"])
        self.assertEqual([i["login"] for i in self.svc.list(self.ctx["admin"], {"state": "N"}, 1, 20)["itens"]],
                         ["inativo"])
        self.assertNotIn("password_hash", self._form(U_OPPROD))
        self.assertEqual(usr_mod.normalize_filters({"login": "op", "profile_id": "2", "state": "B"}),
                         {"login": "op", "profile_id": 2, "state": "B"})
        self.assertEqual(usr_mod.normalize_filters({"login": "<x>", "profile_id": "a", "state": "Z"}), {})

    def test_acesso_negado_e_nao_encontrado(self):
        ctx = self.ctx["op.prod"]
        for call in (lambda: self.svc.list(ctx, {}, 1, 20), lambda: self.svc.form(ctx),
                        lambda: self.svc.save(ctx, IP, None, {}), lambda: self.svc.unlock(ctx, IP, "6"),
                        lambda: self.svc.reset_password(ctx, IP, "6", NEW_PASSWORD, NEW_PASSWORD),
                        lambda: self.svc.toggle_active(ctx, IP, "6", "x")):
            with self.assertRaises(AccessDenied):
                call()
        for uid in ("999", "abc", "0"):
            with self.assertRaises(RepoNotFound):
                self.svc.form(self.ctx["admin"], uid)


if __name__ == "__main__":
    unittest.main()
