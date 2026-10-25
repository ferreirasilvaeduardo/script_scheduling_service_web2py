# -*- coding: utf-8 -*-
"""Testes de auth_service.py (F2.2) sobre o backend FAKE com relogio injetado."""
from tests.support import _testenv  # noqa: F401

import datetime
import hashlib
import io
import logging
import os
import re
import secrets
import threading
import unittest
from unittest import mock

import auth_service
import repo_factory
from sss.core import security
from auth_service import MSG_GENERIC

MAX = 5
LOCKOUT_S = 900
ITER_TESTE = 1000
START = datetime.datetime(2026, 10, 14, 9, 0, 0)


def _hash_with_iterations(password_value, iterations):
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password_value.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256$%d$%s$%s" % (iterations, salt.hex(), dk.hex())


class _Clock(object):

    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += datetime.timedelta(seconds=seconds)


class TestAuthService(unittest.TestCase):

    def setUp(self):
        # Iteracoes reduzidas apenas para o tempo de execucao; o fluxo e o mesmo do vigente.
        patcher = mock.patch.object(security, "ITERATIONS", ITER_TESTE)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.password = secrets.token_urlsafe(16)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_DEV_PASSWORD: self.password})
        env.start()
        self.addCleanup(env.stop)

        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configure, None)

        self.users = repo_factory.get("users")
        self.rbac = repo_factory.get("rbac")
        self.audit = repo_factory.get("audit")
        self.clock = _Clock(START)
        # O bloqueio usa o relogio do banco (README §4.2): o relogio de teste e o SYSDATE do FAKE.
        repo_factory._fake_store.set_clock(self.clock)
        log = logging.getLogger("test_auth_service")
        log.addHandler(logging.NullHandler())
        log.propagate = False
        self.service = auth_service.AuthService(
            users=self.users, rbac_repo=self.rbac, catalog=repo_factory.get("catalog"),
            audit=self.audit, max_attempts=MAX, lockout_s=LOCKOUT_S, log=log,
        )
        self.users.update(5, {"password_hash": security.hash_password(self.password)}, actor="teste")
        self.aud_base = max(a["id"] for a in self.audit.list(size=1000)["items"])

    def _actions(self, actor):
        items = self.audit.list({"actor": actor}, page=1, size=100)["items"]
        return [a["action"] for a in items if a["actor"] == actor and a["id"] > self.aud_base]

    def _fail_login(self, login, times):
        result = None
        for _ in range(times):
            result = self.service.authenticate(login, "senha-errada-123", "10.0.0.1")
        return result

    def test_rajada_paralela_nao_escapa_do_bloqueio(self):
        # Revisao de 2026-10-20: 10 tentativas leem o usuario antes de qualquer gravacao; o repositorio
        # decide o bloqueio sob a trava, e a conta fica bloqueada com a contagem certa.
        barrier = threading.Barrier(10)
        original = self.users.get_by_login

        def _lento(login):
            user = original(login)
            barrier.wait(5)
            return user

        answers = []
        with mock.patch.object(self.users, "get_by_login", side_effect=_lento):
            threads = [threading.Thread(target=lambda: answers.append(
                self.service.authenticate("admin", "senha-errada-123", "10.0.0.1")[1])) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(10)
        user = original("admin")
        self.assertEqual(len(answers), 10)
        self.assertIsNotNone(user["locked_until"], "a rajada nao pode escapar do bloqueio")
        self.assertEqual(user["failed_attempts"], 10)
        self.assertEqual(self._actions("admin").count("LOGIN_LOCKED"), 6, "uma por falha a partir do limite")
        self.assertIn(self.service.lockout_message, answers)
        _ctx, msg = self.service.authenticate("admin", self.password, "10.0.0.1")
        self.assertEqual(msg, self.service.lockout_message, "senha certa nao entra durante o bloqueio")

    def test_detalhe_da_falha_com_a_contagem_do_repositorio(self):
        self._fail_login("admin", 2)
        items = self.audit.list({"actor": "admin"}, page=1, size=100)["items"]
        details = sorted(a["detail"] for a in items if a["action"] == "LOGIN_FAILED" and a["id"] > self.aud_base)
        self.assertEqual(details, ["Falha de login: senha incorreta (tentativa 1 de 5)",
                                    "Falha de login: senha incorreta (tentativa 2 de 5)"])

    def test_sucesso(self):
        ctx, msg = self.service.authenticate("admin", self.password, "10.0.0.1")
        self.assertIsNone(msg)
        self.assertEqual(ctx["login"], "admin")
        self.assertTrue(ctx["is_admin"])
        self.assertIn("MANAGE_USERS", ctx["features"])
        u = self.users.get_by_id(1)
        self.assertEqual(u["last_login_at"], START)
        self.assertEqual(u["failed_attempts"], 0)
        self.assertEqual(self._actions("admin"), ["LOGIN_OK"])

    def test_mensagens_em_duas_partes(self):
        # CR-004 U1 (README §2.4.2): o que aconteceu + o que fazer agora; o bloqueio informa os minutos.
        self.assertEqual(MSG_GENERIC, u"Usuário ou senha incorretos. Confira o que digitou e tente de novo.")
        self.assertIn(u"Espere %d minutos" % max(1, -(-LOCKOUT_S // 60)), self.service.lockout_message)

    def test_login_normalizado(self):
        ctx, _ = self.service.authenticate("  ADMIN ", self.password, "10.0.0.1")
        self.assertEqual(ctx["login"], "admin")

    def test_ctx_nao_admin(self):
        ctx, _ = self.service.authenticate("consulta", self.password, "10.0.0.1")
        self.assertFalse(ctx["is_admin"])
        self.assertEqual(ctx["features"], frozenset(["VIEW_LOGS"]))
        self.assertEqual(ctx["environments"], frozenset(["PRODUCAO", "HOMOLOGACAO"]))

    def test_senha_errada(self):
        ctx, msg = self.service.authenticate("admin", "senha-errada-123", "10.0.0.1")
        self.assertIsNone(ctx)
        self.assertEqual(msg, MSG_GENERIC)
        self.assertEqual(self.users.get_by_id(1)["failed_attempts"], 1)
        self.assertEqual(self._actions("admin"), ["LOGIN_FAILED"])

    def test_inexistente_mesma_mensagem(self):
        ctx, msg = self.service.authenticate("naoexiste", self.password, "10.0.0.1")
        self.assertIsNone(ctx)
        self.assertEqual(msg, MSG_GENERIC)
        self.assertEqual(self._actions("naoexiste"), ["LOGIN_FAILED"])

    def test_entradas_invalidas(self):
        for login, password in ((None, self.password), ("a", self.password), ("x" * 200, self.password),
                             ("admin", None), ("admin", ""), ("admin", "x" * 5000), (["admin"], self.password)):
            self.assertEqual(self.service.authenticate(login, password, "10.0.0.1"), (None, MSG_GENERIC))

    def test_bloqueio_na_enesima_falha(self):
        self.assertEqual(self._fail_login("op.prod", MAX - 1), (None, MSG_GENERIC))
        self.assertEqual(self._fail_login("op.prod", 1), (None, self.service.lockout_message))
        u = self.users.get_by_id(2)
        self.assertEqual(u["failed_attempts"], MAX)
        self.assertEqual(u["locked_until"], START + datetime.timedelta(seconds=LOCKOUT_S))
        actions = self._actions("op.prod")
        self.assertEqual(actions.count("LOGIN_FAILED"), MAX)
        self.assertEqual(actions.count("LOGIN_LOCKED"), 1)

    def test_senha_correta_durante_bloqueio(self):
        self._fail_login("op.prod", MAX)
        self.clock.advance(LOCKOUT_S - 1)
        self.assertEqual(self.service.authenticate("op.prod", self.password, "10.0.0.1"), (None, self.service.lockout_message))
        # Tentativas durante o bloqueio nao o prolongam.
        u = self.users.get_by_id(2)
        self.assertEqual(u["locked_until"], START + datetime.timedelta(seconds=LOCKOUT_S))

    def test_desbloqueio_por_tempo(self):
        self._fail_login("op.prod", MAX)
        self.clock.advance(LOCKOUT_S)
        self.assertEqual(self._fail_login("op.prod", 1), (None, MSG_GENERIC))
        self.assertEqual(self.users.get_by_id(2)["failed_attempts"], 1)
        ctx, msg = self.service.authenticate("op.prod", self.password, "10.0.0.1")
        self.assertIsNone(msg)
        u = self.users.get_by_id(2)
        self.assertEqual((u["failed_attempts"], u["locked_until"]), (0, None))

    def test_inexistente_bloqueio_simulado(self):
        self.assertEqual(self._fail_login("fantasma", MAX - 1), (None, MSG_GENERIC))
        self.assertEqual(self._fail_login("fantasma", 1), (None, self.service.lockout_message))
        self.assertEqual(self._fail_login("fantasma", 1), (None, self.service.lockout_message))
        self.clock.advance(LOCKOUT_S)
        self.assertEqual(self._fail_login("fantasma", 1), (None, MSG_GENERIC))
        self.assertIn("LOGIN_LOCKED", self._actions("fantasma"))

    def test_seed_bloqueado(self):
        self.users.update(6, {"password_hash": security.hash_password(self.password),
                                  "locked_until": START + datetime.timedelta(minutes=5)}, actor="teste")
        self.assertEqual(self.service.authenticate("bloqueado", self.password, "10.0.0.1"), (None, self.service.lockout_message))

    def test_usuario_inativo(self):
        self.assertEqual(self.service.authenticate("inativo", self.password, "10.0.0.1"), (None, MSG_GENERIC))
        self.assertEqual(self.users.get_by_id(5)["failed_attempts"], 0)
        self.assertEqual(self._actions("inativo"), ["LOGIN_FAILED"])

    def test_perfil_inativo(self):
        self.rbac.profiles_update(4, {"active": "N"}, actor="teste")
        self.assertEqual(self.service.authenticate("consulta", self.password, "10.0.0.1"), (None, MSG_GENERIC))

    def test_hash_inutilizavel(self):
        self.users.update(3, {"password_hash": "!"}, actor="teste")
        self.assertEqual(self.service.authenticate("op.hml", "!", "10.0.0.1"), (None, MSG_GENERIC))

    def test_rehash(self):
        self.users.update(1, {"password_hash": _hash_with_iterations(self.password, ITER_TESTE // 2)}, actor="teste")
        before = self.users.get_by_id(1)["password_changed_at"]
        ctx, msg = self.service.authenticate("admin", self.password, "10.0.0.1")
        self.assertIsNone(msg)
        u = self.users.get_by_id(1)
        self.assertTrue(u["password_hash"].startswith("pbkdf2_sha256$%d$" % ITER_TESTE))
        self.assertFalse(security.needs_rehash(u["password_hash"]))
        self.assertTrue(security.verify_password(self.password, u["password_hash"]))
        self.assertEqual(u["password_changed_at"], before)

    def test_login_e_auditoria_numa_operacao_do_repositorio(self):
        # CR-003 P3: LOGIN_OK, LOGIN_FAILED e LOGIN_LOCKED vao pelo repositorio de usuarios, na mesma operacao.
        with mock.patch.object(self.audit, "register", side_effect=AssertionError("auditoria separada")):
            ctx, msg = self.service.authenticate("admin", self.password, "10.0.0.1")
            self.assertIsNone(msg)
            self.assertEqual(self._fail_login("op.prod", MAX), (None, self.service.lockout_message))
        self.assertEqual(self._actions("admin"), ["LOGIN_OK"])
        actions = self._actions("op.prod")
        self.assertEqual(actions.count("LOGIN_FAILED"), MAX)
        self.assertEqual(actions.count("LOGIN_LOCKED"), 1)

    def test_rehash_na_mesma_operacao_do_sucesso(self):
        self.users.update(1, {"password_hash": _hash_with_iterations(self.password, ITER_TESTE // 2)}, actor="teste")
        with mock.patch.object(self.users, "update", side_effect=AssertionError("rehash separado")):
            _ctx, msg = self.service.authenticate("admin", self.password, "10.0.0.1")
        self.assertIsNone(msg)
        self.assertFalse(security.needs_rehash(self.users.get_by_id(1)["password_hash"]))

    def test_minha_senha_reinicia_ciclo_apos_bloqueio_expirado(self):
        # CR-003 P3: bloqueio expirado zera as tentativas tambem em "Minha senha" (README §4.2).
        ctx, _ = self.service.authenticate("op.prod", self.password, "10.0.0.1")
        self._fail_login("op.prod", MAX)
        self.clock.advance(LOCKOUT_S + 1)
        result, _errors = self.service.change_password(ctx, "10.0.0.1", "senha-errada-123", "x", "x")
        self.assertEqual(result, "ERROR")
        u = self.users.get_by_id(2)
        self.assertEqual(u["failed_attempts"], 1)
        self.assertIsNone(u["locked_until"])

    def test_auditoria_sem_senha(self):
        self.service.authenticate("admin", self.password, "10.0.0.1")
        self.service.authenticate("admin", "senha-errada-123", "10.0.0.1")
        for reg in self.audit.list(size=1000)["items"]:
            self.assertNotIn(self.password, reg.get("detail") or "")
            self.assertNotIn("senha-errada-123", reg.get("detail") or "")
            self.assertNotIn("pbkdf2", reg.get("detail") or "")

    def test_logout_auditado(self):
        ctx, _ = self.service.authenticate("admin", self.password, "10.0.0.1")
        self.service.logout(ctx, "10.0.0.1")
        self.assertEqual(self._actions("admin"), ["LOGOUT", "LOGIN_OK"])

    # -------------------------------------------------------------- revalidar

    def _session(self, login):
        ctx, _ = self.service.authenticate(login, self.password, "10.0.0.1")
        return {"user_id": ctx["user_id"], "login": ctx["login"],
                "profile_id": ctx["profile_id"], "perm_version": ctx["perm_version"], "session_epoch": ctx["session_epoch"]}

    def test_revalidar_ok(self):
        session = self._session("consulta")
        ctx = self.service.revalidate(session)
        self.assertEqual(ctx["features"], frozenset(["VIEW_LOGS"]))

    def test_revalidar_recarrega_com_perm_versao(self):
        session = self._session("consulta")
        self.assertNotIn("EXEC_SCRIPT", self.service.revalidate(session)["features"])
        matrix = self.rbac.matrix_get(4)
        self.rbac.matrix_save(4, list(matrix["funcs"]) + [1], matrix["ambs"], matrix["scrs"], actor="teste")
        ctx = self.service.revalidate(session)
        self.assertIn("EXEC_SCRIPT", ctx["features"])
        self.assertGreater(ctx["perm_version"], session["perm_version"])

    def _last_logout(self, actor):
        items = [r for r in self.audit.list({"action": "LOGOUT"}, page=1, size=10)["items"]
                 if r["actor"] == actor and r["id"] > self.aud_base]
        return items[0] if items else None

    def test_revalidar_usuario_inativo(self):
        session = self._session("op.prod")
        self.users.update(2, {"active": "N"}, actor="teste")
        self.assertIsNone(self.service.revalidate(session, "10.9.9.9"))
        aud = self._last_logout("op.prod")
        self.assertEqual(aud["detail"], u"sessão encerrada pela revalidação: usuário inativo")
        self.assertEqual(aud["source_ip"], "10.9.9.9")

    def test_revalidar_perfil_inativo(self):
        session = self._session("consulta")
        self.rbac.profiles_update(4, {"active": "N"}, actor="teste")
        self.assertIsNone(self.service.revalidate(session))
        self.assertEqual(self._last_logout("consulta")["detail"],
                         u"sessão encerrada pela revalidação: perfil inativo")

    def test_revalidar_sessao_invalida_nao_audita(self):
        session = self._session("consulta")
        self.assertIsNone(self.service.revalidate(dict(session, user_id=999)))
        self.assertIsNone(self._last_logout("consulta"))

    def test_revalidar_sessao_invalida(self):
        session = self._session("consulta")
        self.assertIsNone(self.service.revalidate(dict(session, login="admin")))
        self.assertIsNone(self.service.revalidate(dict(session, user_id=999)))
        self.assertIsNone(self.service.revalidate(dict(session, user_id="4")))
        self.assertIsNone(self.service.revalidate({}))

    def test_mensagem_de_bloqueio_pela_funcao_do_modulo(self):
        # "Minha senha" bloqueada (controllers/default.py) usa a mesma mensagem do login.
        with mock.patch.object(auth_service, "_service", return_value=self.service):
            self.assertEqual(auth_service.lock_message(), self.service.lockout_message)

    def test_controllers_so_usam_nomes_existentes_do_auth_service(self):
        root = os.path.join(_testenv.APP_DIR, "controllers")
        for name in sorted(os.listdir(root)):
            if name.endswith(".py"):
                with io.open(os.path.join(root, name), encoding="utf-8") as f:
                    for attribute in re.findall(r"\bauth_service\.([A-Za-z_]\w*)", f.read()):
                        self.assertTrue(hasattr(auth_service, attribute), "%s: auth_service.%s" % (name, attribute))


class TestSeedDev(unittest.TestCase):

    def setUp(self):
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configure, None)
        patcher = mock.patch.object(security, "ITERATIONS", ITER_TESTE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _hashes(self):
        repo = repo_factory.get("users")
        return dict((u["login"], u["password_hash"]) for u in repo.list(size=100)["items"])

    def test_sem_variavel_logins_impossiveis(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(repo_factory.ENV_DEV_PASSWORD, None)
            with self.assertLogs("sss_web", level="WARNING"):
                hashes = self._hashes()
        self.assertTrue(all(h == "!" for h in hashes.values()))

    def test_com_variavel(self):
        password = secrets.token_urlsafe(16)
        with mock.patch.dict(os.environ, {repo_factory.ENV_DEV_PASSWORD: password}):
            hashes = self._hashes()
        for login in ("admin", "op.prod", "op.hml", "consulta"):
            self.assertTrue(security.verify_password(password, hashes[login]), login)
        self.assertEqual(hashes["inativo"], "!")
        self.assertEqual(hashes["bloqueado"], "!")
        self.assertNotEqual(hashes["admin"], hashes["consulta"])

    def test_variavel_fora_da_politica(self):
        with mock.patch.dict(os.environ, {repo_factory.ENV_DEV_PASSWORD: "curta"}):
            with self.assertLogs("sss_web", level="WARNING"):
                hashes = self._hashes()
        self.assertTrue(all(h == "!" for h in hashes.values()))


if __name__ == "__main__":
    unittest.main()
