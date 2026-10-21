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
SENHA_DEV = "senha-dev-de-teste-123"
SENHA_NOVA = "Nova-Senha-Forte-2026"
SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0},
    "op.prod": {"usuario_id": 2, "login": "op.prod", "perfil_id": 2, "perm_versao": 1, "sessao_epoch": 0},
}
# Seed FAKE: admin (1, perfil ADMINISTRADOR, unico admin), op.prod (2), op.hml (3), consulta (4),
# inativo (5) e bloqueado (6, 5 tentativas, bloqueado por 30 min). Perfis 1-4 ativos.
U_ADMIN, U_OPPROD, U_BLOQUEADO = 1, 2, 6
P_ADMIN, P_OPPROD, P_CONSULTA = 1, 2, 4
AGORA = datetime.datetime(2026, 10, 15, 9, 0, 0)


class _Base(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(security, "ITERATIONS", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_DEV_PASSWORD: SENHA_DEV})
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
                                             self.audit, 5, 900, self.log, relogio=lambda: AGORA)
        self.ctx = dict((login, self.auth.revalidate(sessao)) for login, sessao in SESSOES.items())
        # O seed usa o relogio real: o bloqueio do usuario 'bloqueado' e reposicionado a partir de AGORA.
        self.users.update(U_BLOQUEADO, {"locked_until": AGORA + datetime.timedelta(minutes=30)}, ator="teste")
        self.svc = AdminUsersService(self.users, self.rbac_repo, self.log, relogio=lambda: AGORA)
        self.aud_base = max([a["id"] for a in self.audit.list(pagina=1, tamanho=1000)["itens"]] or [0])

    def _auditorias(self, acao=None):
        filtros = {"action": acao} if acao else None
        return [a for a in self.audit.list(filtros=filtros, pagina=1, tamanho=200)["itens"]
                if a["entity"] == "tbsss_users" and a["id"] > self.aud_base]

    def _insert(self, **mudancas):
        dados = {"login": "maria.silva", "name": "Maria Silva", "profile_id": str(P_CONSULTA),
                 "senha": SENHA_NOVA, "confirmacao": SENHA_NOVA}
        dados.update(mudancas)
        return self.svc.save(self.ctx["admin"], IP, None, dados)

    def _form(self, uid, ator="admin"):
        return self.svc.form(self.ctx[ator], str(uid))

    def _editar(self, uid, actor="admin", **mudancas):
        f = self._form(uid, actor)
        dados = {"name": f["name"], "profile_id": str(f["profile_id"]), "version": f["version"]}
        dados.update(mudancas)
        return self.svc.save(self.ctx[actor], IP, str(uid), dados)

    def _sem_segredo(self, texto, *segredos):
        for s in segredos:
            self.assertNotIn(s, texto)
        self.assertNotIn("pbkdf2", texto)


class TestInclusao(_Base):

    def test_auditoria_mostra_perfil_pelo_nome_e_login_sem_espacos(self):
        # CR-003 P6 (README §4.4) e C2.
        _id, erros = self._insert(login=" maria.silva")
        self.assertEqual(erros, {"login": admin_crud.MSG_SPACES})
        uid, erros = self._insert()
        self.assertEqual(erros, {})
        detalhe = [a for a in self._auditorias("CREATE") if a["entity_id"] == uid][0]["detail"]
        self.assertIn("perfil: READ_ONLY", detalhe)
        self.assertNotIn("profile_id", detalhe)

    def test_inclusao_ok_com_hash_e_auditoria_sem_senha(self):
        uid, erros = self._insert()
        self.assertEqual(erros, {})
        u = self.users.get_by_id(uid)
        self.assertEqual((u["login"], u["name"], u["profile_id"], u["active"]), ("maria.silva", "Maria Silva", P_CONSULTA, "Y"))
        self.assertTrue(security.verify_password(SENHA_NOVA, u["password_hash"]))
        self.assertEqual(u["password_changed_at"], AGORA)
        aud = self._auditorias("CREATE")
        self.assertEqual(len(aud), 1)
        self.assertIn("login: maria.silva", aud[0]["detail"])
        self._sem_segredo(aud[0]["detail"], SENHA_NOVA, u["password_hash"])

    def test_login_invalido_ou_duplicado(self):
        for login in ("Maria", "ab", "a" * 31, "maria silva", u"joão"):
            _uid, erros = self._insert(login=login)
            self.assertEqual(erros.get("login"), usr_mod.MSG_LOGIN_INVALID, login)
        _uid, erros = self._insert(login="op.prod")
        self.assertEqual(erros, {"login": usr_mod.MSG_LOGIN_DUPLICATE})
        self.assertEqual(self._auditorias("CREATE"), [])

    def test_senha_fraca_e_confirmacao_divergente(self):
        _uid, erros = self._insert(senha="curta", confirmacao="curta")
        self.assertEqual(erros, {"senha": security.validate_password_policy("curta")[0]})
        _uid, erros = self._insert(confirmacao=SENHA_NOVA + "x")
        self.assertEqual(erros, {"confirmacao": usr_mod.MSG_CONFIRMATION})
        _uid, erros = self._insert(senha="", confirmacao="")
        self.assertEqual(erros, {"senha": usr_mod.MSG_PASSWORD_REQUIRED})

    def test_perfil_inativo_ou_inexistente(self):
        form = self.rbac_repo.profiles_get(P_CONSULTA)
        self.rbac_repo.profiles_update(P_CONSULTA, {"active": "N"}, ator="teste")
        _uid, erros = self._insert()
        self.assertEqual(erros, {"profile_id": usr_mod.MSG_PROFILE_INVALID})
        _uid, erros = self._insert(profile_id="999")
        self.assertEqual(erros, {"profile_id": usr_mod.MSG_PROFILE_INVALID})
        self.assertEqual(form["name"], "READ_ONLY")


class TestEdicaoEUltimoAdmin(_Base):

    def test_edicao_ignora_login_e_audita(self):
        _uid, erros = self._editar(U_OPPROD, name="Operador Prod Novo", login="hacker")
        self.assertEqual(erros, {})
        u = self.users.get_by_id(U_OPPROD)
        self.assertEqual((u["login"], u["name"]), ("op.prod", "Operador Prod Novo"))
        self.assertIn("name: Operador Producao", self._auditorias("UPDATE")[0]["detail"])

    def test_nao_admin_nao_troca_o_proprio_perfil(self):
        # Revisao de 2026-10-20 (CR-008 E1): MANAGE_USERS sem admin nao muda as proprias permissoes.
        gestor = dict(self.ctx["op.prod"], features=frozenset({"MANAGE_USERS"}))
        f = self.svc.form(gestor, str(U_OPPROD))
        _uid, erros = self.svc.save(gestor, IP, str(U_OPPROD),
                                      {"name": f["name"], "profile_id": str(P_CONSULTA), "version": f["version"]})
        self.assertEqual(erros, {usr_mod.GENERAL_FIELD: usr_mod.MSG_ADMIN_ONLY})
        self.assertEqual(self.users.get_by_id(U_OPPROD)["profile_id"], P_OPPROD)
        # O proprio nome, sem trocar de perfil, continua permitido.
        _uid, erros = self.svc.save(gestor, IP, str(U_OPPROD),
                                      {"name": "Operador Producao", "profile_id": str(P_OPPROD), "version": f["version"]})
        self.assertEqual(erros, {})
        # O administrador continua trocando o perfil de outros usuarios.
        self.assertEqual(self._editar(U_BLOQUEADO, profile_id=str(P_CONSULTA))[1], {})

    def test_troca_de_perfil_do_ultimo_admin_negada(self):
        # Outro administrador nao pode tirar o unico admin do perfil admin: novo admin cria o cenario.
        novo, _ = self._insert(login="admin2", profile_id=str(P_ADMIN))
        self.users.update(novo, {"active": "N"}, ator="teste")
        ctx2 = dict(self.ctx["admin"], user_id=novo, login="admin2")
        f = self.svc.form(ctx2, str(U_ADMIN))
        _uid, erros = self.svc.save(ctx2, IP, str(U_ADMIN), {"name": f["name"], "profile_id": str(P_CONSULTA),
                                                               "version": f["version"]})
        self.assertEqual(erros, {GENERAL_FIELD: usr_mod.MSG_LAST_ADMIN})
        self.assertEqual(self.users.get_by_id(U_ADMIN)["profile_id"], P_ADMIN)

    def test_desativacao_do_ultimo_admin_negada(self):
        novo, _ = self._insert(login="gestor", profile_id=str(P_OPPROD))
        ctx_gestor = dict(self.ctx["admin"], user_id=novo, login="gestor")
        f = self.svc.form(ctx_gestor, str(U_ADMIN))
        with self.assertRaises(OperationDenied) as cm:
            self.svc.toggle_active(ctx_gestor, IP, str(U_ADMIN), f["version"])
        self.assertEqual(cm.exception.mensagem, usr_mod.MSG_LAST_ADMIN)
        self.assertEqual(self.users.get_by_id(U_ADMIN)["active"], "Y")
        self.assertEqual(self._auditorias("DEACTIVATE"), [])

    def test_com_dois_admins_desativar_um_passa(self):
        novo, _ = self._insert(login="admin2", profile_id=str(P_ADMIN))
        f = self._form(novo)
        alterado = self.svc.toggle_active(self.ctx["admin"], IP, str(novo), f["version"])
        self.assertEqual(alterado["active"], "N")
        self.assertNotIn("password_hash", alterado)
        self.assertEqual(len(self._auditorias("DEACTIVATE")), 1)

    def test_autodesativacao_e_autoperfil_negados(self):
        novo, _ = self._insert(login="admin2", profile_id=str(P_ADMIN))
        with self.assertRaises(OperationDenied) as cm:
            self.svc.toggle_active(self.ctx["admin"], IP, str(U_ADMIN), self._form(U_ADMIN)["version"])
        self.assertEqual(cm.exception.mensagem, usr_mod.MSG_SELF_DEACTIVATE)
        _uid, erros = self._editar(U_ADMIN, profile_id=str(P_CONSULTA))
        self.assertEqual(erros, {GENERAL_FIELD: usr_mod.MSG_SELF_PROFILE})
        _uid, erros = self._editar(U_ADMIN, name="Admin Renomeado")
        self.assertEqual(erros, {})
        self.assertEqual(novo, self.users.get_by_login("admin2")["id"])

    def test_desativado_tem_sessao_encerrada_na_revalidacao(self):
        f = self._form(U_OPPROD)
        self.svc.toggle_active(self.ctx["admin"], IP, str(U_OPPROD), f["version"])
        self.assertIsNone(self.auth.revalidate(dict(SESSOES["op.prod"])))

    def test_conflito_de_edicao(self):
        f = self._form(U_OPPROD)
        self._editar(U_OPPROD, name="Primeira")
        _uid, erros = self.svc.save(self.ctx["admin"], IP, str(U_OPPROD),
                                      {"name": "Segunda", "profile_id": str(P_OPPROD), "version": f["version"]})
        self.assertEqual(erros, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})
        with self.assertRaises(RepoConflict):
            self.svc.toggle_active(self.ctx["admin"], IP, str(U_OPPROD), f["version"])

    def test_ultimo_admin_atomico_no_repositorio(self):
        with self.assertRaises(RepoViolation) as cm:
            self.users.update(U_ADMIN, {"profile_id": P_CONSULTA}, ator="teste")
        self.assertEqual(cm.exception.constraint, "sss_ultimo_admin")
        with self.assertRaises(RepoViolation):
            self.users.update(U_ADMIN, {"active": "N"}, ator="teste")


class TestSenhaEBloqueio(_Base):

    def test_redefinicao_zera_bloqueio_e_audita_sem_senha(self):
        self.assertTrue(self._form(U_BLOQUEADO)["bloqueado"])
        erros = self.svc.reset_password(self.ctx["admin"], IP, str(U_BLOQUEADO), SENHA_NOVA, SENHA_NOVA)
        self.assertEqual(erros, {})
        u = self.users.get_by_id(U_BLOQUEADO)
        self.assertEqual((u["failed_attempts"], u["locked_until"], u["password_changed_at"]), (0, None, AGORA))
        self.assertTrue(security.verify_password(SENHA_NOVA, u["password_hash"]))
        aud = self._auditorias("UPDATE")
        self.assertEqual([a["detail"] for a in aud], ["senha redefinida"])
        self._sem_segredo(repr(self.audit.list(pagina=1, tamanho=1000)), SENHA_NOVA, u["password_hash"])

    def test_redefinicao_valida_politica_e_confirmacao(self):
        self.assertEqual(self.svc.reset_password(self.ctx["admin"], IP, str(U_OPPROD), "fraca", "fraca"),
                         {"senha": security.validate_password_policy("fraca")[0]})
        self.assertEqual(self.svc.reset_password(self.ctx["admin"], IP, str(U_OPPROD), SENHA_NOVA, "x"),
                         {"confirmacao": usr_mod.MSG_CONFIRMATION})

    def test_redefinir_a_propria_senha_pela_administracao_negado(self):
        with self.assertRaises(OperationDenied) as cm:
            self.svc.reset_password(self.ctx["admin"], IP, str(U_ADMIN), SENHA_NOVA, SENHA_NOVA)
        self.assertEqual(cm.exception.mensagem, usr_mod.MSG_SELF_PASSWORD)

    def test_desbloquear(self):
        alterado = self.svc.unlock(self.ctx["admin"], IP, str(U_BLOQUEADO))
        self.assertEqual((alterado["failed_attempts"], alterado["locked_until"]), (0, None))
        self.assertTrue(self._auditorias("UPDATE")[0]["detail"].startswith("desbloqueado"))

    def test_minha_senha_com_atual_errada(self):
        res, erros = self.auth.change_password(self.ctx["op.prod"], IP, "errada-errada-1", SENHA_NOVA, SENHA_NOVA)
        self.assertEqual((res, erros), ("ERRO", {"senha_atual": auth_service.MSG_CURRENT_PASSWORD}))
        u = self.users.get_by_id(U_OPPROD)
        self.assertEqual(u["failed_attempts"], 1)
        self.assertTrue(security.verify_password(SENHA_DEV, u["password_hash"]))
        falhas = [a for a in self.audit.list(filtros={"action": "LOGIN_FAILED"}, pagina=1, tamanho=50)["itens"]
                  if a["id"] > self.aud_base]
        self.assertEqual(len(falhas), 1)

    def test_minha_senha_bloqueia_apos_limite(self):
        for _ in range(4):
            self.assertEqual(self.auth.change_password(self.ctx["op.prod"], IP, "errada-errada-1", SENHA_NOVA,
                                                    SENHA_NOVA)[0], "ERRO")
        res, _erros = self.auth.change_password(self.ctx["op.prod"], IP, "errada-errada-1", SENHA_NOVA, SENHA_NOVA)
        self.assertEqual(res, "BLOQUEADO")
        self.assertIsNotNone(self.users.get_by_id(U_OPPROD)["locked_until"])
        # Mesmo com a senha certa, a conta bloqueada nao troca a senha.
        self.assertEqual(self.auth.change_password(self.ctx["op.prod"], IP, SENHA_DEV, SENHA_NOVA, SENHA_NOVA)[0],
                         "BLOQUEADO")

    def test_minha_senha_ok_e_validacoes(self):
        res, erros = self.auth.change_password(self.ctx["op.prod"], IP, SENHA_DEV, "curta", "curta")
        self.assertEqual(res, "ERRO")
        self.assertIn("nova", erros)
        res, erros = self.auth.change_password(self.ctx["op.prod"], IP, SENHA_DEV, SENHA_NOVA, "outra")
        self.assertEqual(erros, {"confirmacao": auth_service.MSG_CONFIRMATION})
        res, erros = self.auth.change_password(self.ctx["op.prod"], IP, SENHA_DEV, SENHA_NOVA, SENHA_NOVA)
        self.assertEqual((res, erros), ("OK", {}))
        u = self.users.get_by_id(U_OPPROD)
        self.assertTrue(security.verify_password(SENHA_NOVA, u["password_hash"]))
        aud = self._auditorias("UPDATE")
        self.assertEqual((aud[0]["actor"], aud[0]["detail"]), ("op.prod", u"senha alterada pelo próprio usuário"))


class TestListaEAcesso(_Base):

    def test_relogio_padrao_e_o_do_banco(self):
        # CR-003 P3: sem relogio injetado, o service usa o SYSDATE do repositorio (nunca o do no web).
        svc = AdminUsersService(self.users, self.rbac_repo, self.log)
        futuro = self.users.now() + datetime.timedelta(minutes=5)
        self.assertTrue(svc.is_locked({"locked_until": futuro}))
        self.assertFalse(svc.is_locked({"locked_until": self.users.now() - datetime.timedelta(seconds=1)}))

    def test_lista_sem_hash_com_bloqueio_e_filtros(self):
        pagina = self.svc.list(self.ctx["admin"], {}, 1, 20)
        self.assertEqual(pagina["total"], 6)
        for item in pagina["itens"]:
            self.assertNotIn("password_hash", item)
        bloq = [i for i in pagina["itens"] if i["login"] == "bloqueado"][0]
        self.assertTrue(bloq["bloqueado"])
        self.assertEqual(bloq["perfil_nome"], "OPERATOR_PROD")
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
        for chamada in (lambda: self.svc.list(ctx, {}, 1, 20), lambda: self.svc.form(ctx),
                        lambda: self.svc.save(ctx, IP, None, {}), lambda: self.svc.unlock(ctx, IP, "6"),
                        lambda: self.svc.reset_password(ctx, IP, "6", SENHA_NOVA, SENHA_NOVA),
                        lambda: self.svc.toggle_active(ctx, IP, "6", "x")):
            with self.assertRaises(AccessDenied):
                chamada()
        for uid in ("999", "abc", "0"):
            with self.assertRaises(RepoNotFound):
                self.svc.form(self.ctx["admin"], uid)


if __name__ == "__main__":
    unittest.main()
