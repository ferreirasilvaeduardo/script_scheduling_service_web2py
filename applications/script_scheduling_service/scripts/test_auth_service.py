# -*- coding: utf-8 -*-
"""Testes de auth_service.py (F2.2) sobre o backend FAKE com relogio injetado."""
import _testenv  # noqa: F401

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
import security
from auth_service import MSG_GENERIC

MAX = 5
BLOQUEIO_S = 900
ITER_TESTE = 1000
INICIO = datetime.datetime(2026, 10, 14, 9, 0, 0)


def _hash_com_iteracoes(senha, iteracoes):
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, iteracoes)
    return "pbkdf2_sha256$%d$%s$%s" % (iteracoes, salt.hex(), dk.hex())


class _Relogio(object):

    def __init__(self, agora):
        self.now = agora

    def __call__(self):
        return self.now

    def avancar(self, segundos):
        self.now += datetime.timedelta(seconds=segundos)


class TestAuthService(unittest.TestCase):

    def setUp(self):
        # Iteracoes reduzidas apenas para o tempo de execucao; o fluxo e o mesmo do vigente.
        patcher = mock.patch.object(security, "ITERATIONS", ITER_TESTE)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.senha = secrets.token_urlsafe(16)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_DEV_PASSWORD: self.senha})
        env.start()
        self.addCleanup(env.stop)

        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configure, None)

        self.users = repo_factory.get("users")
        self.rbac = repo_factory.get("rbac")
        self.audit = repo_factory.get("audit")
        self.relogio = _Relogio(INICIO)
        # O bloqueio usa o relogio do banco (README §4.2): o relogio de teste e o SYSDATE do FAKE.
        repo_factory._fake_store.set_clock(self.relogio)
        log = logging.getLogger("test_auth_service")
        log.addHandler(logging.NullHandler())
        log.propagate = False
        self.servico = auth_service.AuthService(
            usuarios=self.users, rbac_repo=self.rbac, catalogo=repo_factory.get("catalog"),
            auditoria=self.audit, max_tentativas=MAX, bloqueio_s=BLOQUEIO_S, log=log,
        )
        self.users.update(5, {"password_hash": security.hash_password(self.senha)}, ator="teste")
        self.aud_base = max(a["id"] for a in self.audit.list(tamanho=1000)["itens"])

    def _acoes(self, ator):
        itens = self.audit.list({"actor": ator}, pagina=1, tamanho=100)["itens"]
        return [a["action"] for a in itens if a["actor"] == ator and a["id"] > self.aud_base]

    def _errar(self, login, vezes):
        resultado = None
        for _ in range(vezes):
            resultado = self.servico.authenticate(login, "senha-errada-123", "10.0.0.1")
        return resultado

    def test_rajada_paralela_nao_escapa_do_bloqueio(self):
        # Revisao de 2026-10-20: 10 tentativas leem o usuario antes de qualquer gravacao; o repositorio
        # decide o bloqueio sob a trava, e a conta fica bloqueada com a contagem certa.
        barreira = threading.Barrier(10)
        original = self.users.get_by_login

        def _lento(login):
            usuario = original(login)
            barreira.wait(5)
            return usuario

        respostas = []
        with mock.patch.object(self.users, "get_by_login", side_effect=_lento):
            threads = [threading.Thread(target=lambda: respostas.append(
                self.servico.authenticate("admin", "senha-errada-123", "10.0.0.1")[1])) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(10)
        usuario = original("admin")
        self.assertEqual(len(respostas), 10)
        self.assertIsNotNone(usuario["locked_until"], "a rajada nao pode escapar do bloqueio")
        self.assertEqual(usuario["failed_attempts"], 10)
        self.assertEqual(self._acoes("admin").count("LOGIN_LOCKED"), 6, "uma por falha a partir do limite")
        self.assertIn(self.servico.msg_bloqueio, respostas)
        _ctx, msg = self.servico.authenticate("admin", self.senha, "10.0.0.1")
        self.assertEqual(msg, self.servico.msg_bloqueio, "senha certa nao entra durante o bloqueio")

    def test_detalhe_da_falha_com_a_contagem_do_repositorio(self):
        self._errar("admin", 2)
        itens = self.audit.list({"actor": "admin"}, pagina=1, tamanho=100)["itens"]
        detalhes = sorted(a["detail"] for a in itens if a["action"] == "LOGIN_FAILED" and a["id"] > self.aud_base)
        self.assertEqual(detalhes, ["Falha de login: senha incorreta (tentativa 1 de 5)",
                                    "Falha de login: senha incorreta (tentativa 2 de 5)"])

    def test_sucesso(self):
        ctx, msg = self.servico.authenticate("admin", self.senha, "10.0.0.1")
        self.assertIsNone(msg)
        self.assertEqual(ctx["login"], "admin")
        self.assertTrue(ctx["is_admin"])
        self.assertIn("MANAGE_USERS", ctx["features"])
        u = self.users.get_by_id(1)
        self.assertEqual(u["last_login_at"], INICIO)
        self.assertEqual(u["failed_attempts"], 0)
        self.assertEqual(self._acoes("admin"), ["LOGIN_OK"])

    def test_mensagens_em_duas_partes(self):
        # CR-004 U1 (README §2.4.2): o que aconteceu + o que fazer agora; o bloqueio informa os minutos.
        self.assertEqual(MSG_GENERIC, u"Usuário ou senha incorretos. Confira o que digitou e tente de novo.")
        self.assertIn(u"Espere %d minutos" % max(1, -(-BLOQUEIO_S // 60)), self.servico.msg_bloqueio)

    def test_login_normalizado(self):
        ctx, _ = self.servico.authenticate("  ADMIN ", self.senha, "10.0.0.1")
        self.assertEqual(ctx["login"], "admin")

    def test_ctx_nao_admin(self):
        ctx, _ = self.servico.authenticate("consulta", self.senha, "10.0.0.1")
        self.assertFalse(ctx["is_admin"])
        self.assertEqual(ctx["features"], frozenset(["VIEW_LOGS"]))
        self.assertEqual(ctx["environments"], frozenset(["PRODUCAO", "HOMOLOGACAO"]))

    def test_senha_errada(self):
        ctx, msg = self.servico.authenticate("admin", "senha-errada-123", "10.0.0.1")
        self.assertIsNone(ctx)
        self.assertEqual(msg, MSG_GENERIC)
        self.assertEqual(self.users.get_by_id(1)["failed_attempts"], 1)
        self.assertEqual(self._acoes("admin"), ["LOGIN_FAILED"])

    def test_inexistente_mesma_mensagem(self):
        ctx, msg = self.servico.authenticate("naoexiste", self.senha, "10.0.0.1")
        self.assertIsNone(ctx)
        self.assertEqual(msg, MSG_GENERIC)
        self.assertEqual(self._acoes("naoexiste"), ["LOGIN_FAILED"])

    def test_entradas_invalidas(self):
        for login, senha in ((None, self.senha), ("a", self.senha), ("x" * 200, self.senha),
                             ("admin", None), ("admin", ""), ("admin", "x" * 5000), (["admin"], self.senha)):
            self.assertEqual(self.servico.authenticate(login, senha, "10.0.0.1"), (None, MSG_GENERIC))

    def test_bloqueio_na_enesima_falha(self):
        self.assertEqual(self._errar("op.prod", MAX - 1), (None, MSG_GENERIC))
        self.assertEqual(self._errar("op.prod", 1), (None, self.servico.msg_bloqueio))
        u = self.users.get_by_id(2)
        self.assertEqual(u["failed_attempts"], MAX)
        self.assertEqual(u["locked_until"], INICIO + datetime.timedelta(seconds=BLOQUEIO_S))
        acoes = self._acoes("op.prod")
        self.assertEqual(acoes.count("LOGIN_FAILED"), MAX)
        self.assertEqual(acoes.count("LOGIN_LOCKED"), 1)

    def test_senha_correta_durante_bloqueio(self):
        self._errar("op.prod", MAX)
        self.relogio.avancar(BLOQUEIO_S - 1)
        self.assertEqual(self.servico.authenticate("op.prod", self.senha, "10.0.0.1"), (None, self.servico.msg_bloqueio))
        # Tentativas durante o bloqueio nao o prolongam.
        u = self.users.get_by_id(2)
        self.assertEqual(u["locked_until"], INICIO + datetime.timedelta(seconds=BLOQUEIO_S))

    def test_desbloqueio_por_tempo(self):
        self._errar("op.prod", MAX)
        self.relogio.avancar(BLOQUEIO_S)
        self.assertEqual(self._errar("op.prod", 1), (None, MSG_GENERIC))
        self.assertEqual(self.users.get_by_id(2)["failed_attempts"], 1)
        ctx, msg = self.servico.authenticate("op.prod", self.senha, "10.0.0.1")
        self.assertIsNone(msg)
        u = self.users.get_by_id(2)
        self.assertEqual((u["failed_attempts"], u["locked_until"]), (0, None))

    def test_inexistente_bloqueio_simulado(self):
        self.assertEqual(self._errar("fantasma", MAX - 1), (None, MSG_GENERIC))
        self.assertEqual(self._errar("fantasma", 1), (None, self.servico.msg_bloqueio))
        self.assertEqual(self._errar("fantasma", 1), (None, self.servico.msg_bloqueio))
        self.relogio.avancar(BLOQUEIO_S)
        self.assertEqual(self._errar("fantasma", 1), (None, MSG_GENERIC))
        self.assertIn("LOGIN_LOCKED", self._acoes("fantasma"))

    def test_seed_bloqueado(self):
        self.users.update(6, {"password_hash": security.hash_password(self.senha),
                                  "locked_until": INICIO + datetime.timedelta(minutes=5)}, ator="teste")
        self.assertEqual(self.servico.authenticate("bloqueado", self.senha, "10.0.0.1"), (None, self.servico.msg_bloqueio))

    def test_usuario_inativo(self):
        self.assertEqual(self.servico.authenticate("inativo", self.senha, "10.0.0.1"), (None, MSG_GENERIC))
        self.assertEqual(self.users.get_by_id(5)["failed_attempts"], 0)
        self.assertEqual(self._acoes("inativo"), ["LOGIN_FAILED"])

    def test_perfil_inativo(self):
        self.rbac.profiles_update(4, {"active": "N"}, ator="teste")
        self.assertEqual(self.servico.authenticate("consulta", self.senha, "10.0.0.1"), (None, MSG_GENERIC))

    def test_hash_inutilizavel(self):
        self.users.update(3, {"password_hash": "!"}, ator="teste")
        self.assertEqual(self.servico.authenticate("op.hml", "!", "10.0.0.1"), (None, MSG_GENERIC))

    def test_rehash(self):
        self.users.update(1, {"password_hash": _hash_com_iteracoes(self.senha, ITER_TESTE // 2)}, ator="teste")
        antes = self.users.get_by_id(1)["password_changed_at"]
        ctx, msg = self.servico.authenticate("admin", self.senha, "10.0.0.1")
        self.assertIsNone(msg)
        u = self.users.get_by_id(1)
        self.assertTrue(u["password_hash"].startswith("pbkdf2_sha256$%d$" % ITER_TESTE))
        self.assertFalse(security.needs_rehash(u["password_hash"]))
        self.assertTrue(security.verify_password(self.senha, u["password_hash"]))
        self.assertEqual(u["password_changed_at"], antes)

    def test_login_e_auditoria_numa_operacao_do_repositorio(self):
        # CR-003 P3: LOGIN_OK, LOGIN_FAILED e LOGIN_LOCKED vao pelo repositorio de usuarios, na mesma operacao.
        with mock.patch.object(self.audit, "register", side_effect=AssertionError("auditoria separada")):
            ctx, msg = self.servico.authenticate("admin", self.senha, "10.0.0.1")
            self.assertIsNone(msg)
            self.assertEqual(self._errar("op.prod", MAX), (None, self.servico.msg_bloqueio))
        self.assertEqual(self._acoes("admin"), ["LOGIN_OK"])
        acoes = self._acoes("op.prod")
        self.assertEqual(acoes.count("LOGIN_FAILED"), MAX)
        self.assertEqual(acoes.count("LOGIN_LOCKED"), 1)

    def test_rehash_na_mesma_operacao_do_sucesso(self):
        self.users.update(1, {"password_hash": _hash_com_iteracoes(self.senha, ITER_TESTE // 2)}, ator="teste")
        with mock.patch.object(self.users, "update", side_effect=AssertionError("rehash separado")):
            _ctx, msg = self.servico.authenticate("admin", self.senha, "10.0.0.1")
        self.assertIsNone(msg)
        self.assertFalse(security.needs_rehash(self.users.get_by_id(1)["password_hash"]))

    def test_minha_senha_reinicia_ciclo_apos_bloqueio_expirado(self):
        # CR-003 P3: bloqueio expirado zera as tentativas tambem em "Minha senha" (README §4.2).
        ctx, _ = self.servico.authenticate("op.prod", self.senha, "10.0.0.1")
        self._errar("op.prod", MAX)
        self.relogio.avancar(BLOQUEIO_S + 1)
        resultado, _erros = self.servico.change_password(ctx, "10.0.0.1", "senha-errada-123", "x", "x")
        self.assertEqual(resultado, "ERRO")
        u = self.users.get_by_id(2)
        self.assertEqual(u["failed_attempts"], 1)
        self.assertIsNone(u["locked_until"])

    def test_auditoria_sem_senha(self):
        self.servico.authenticate("admin", self.senha, "10.0.0.1")
        self.servico.authenticate("admin", "senha-errada-123", "10.0.0.1")
        for reg in self.audit.list(tamanho=1000)["itens"]:
            self.assertNotIn(self.senha, reg.get("detail") or "")
            self.assertNotIn("senha-errada-123", reg.get("detail") or "")
            self.assertNotIn("pbkdf2", reg.get("detail") or "")

    def test_logout_auditado(self):
        ctx, _ = self.servico.authenticate("admin", self.senha, "10.0.0.1")
        self.servico.logout(ctx, "10.0.0.1")
        self.assertEqual(self._acoes("admin"), ["LOGOUT", "LOGIN_OK"])

    # -------------------------------------------------------------- revalidar

    def _sessao(self, login):
        ctx, _ = self.servico.authenticate(login, self.senha, "10.0.0.1")
        return {"usuario_id": ctx["user_id"], "login": ctx["login"],
                "perfil_id": ctx["profile_id"], "perm_versao": ctx["perm_version"], "sessao_epoch": ctx["session_epoch"]}

    def test_revalidar_ok(self):
        sessao = self._sessao("consulta")
        ctx = self.servico.revalidate(sessao)
        self.assertEqual(ctx["features"], frozenset(["VIEW_LOGS"]))

    def test_revalidar_recarrega_com_perm_versao(self):
        sessao = self._sessao("consulta")
        self.assertNotIn("EXEC_SCRIPT", self.servico.revalidate(sessao)["features"])
        matriz = self.rbac.matrix_get(4)
        self.rbac.matrix_save(4, list(matriz["funcs"]) + [1], matriz["ambs"], matriz["scrs"], ator="teste")
        ctx = self.servico.revalidate(sessao)
        self.assertIn("EXEC_SCRIPT", ctx["features"])
        self.assertGreater(ctx["perm_version"], sessao["perm_versao"])

    def _ultimo_logout(self, ator):
        itens = [r for r in self.audit.list({"action": "LOGOUT"}, pagina=1, tamanho=10)["itens"]
                 if r["actor"] == ator and r["id"] > self.aud_base]
        return itens[0] if itens else None

    def test_revalidar_usuario_inativo(self):
        sessao = self._sessao("op.prod")
        self.users.update(2, {"active": "N"}, ator="teste")
        self.assertIsNone(self.servico.revalidate(sessao, "10.9.9.9"))
        aud = self._ultimo_logout("op.prod")
        self.assertEqual(aud["detail"], u"sessão encerrada pela revalidação: usuário inativo")
        self.assertEqual(aud["source_ip"], "10.9.9.9")

    def test_revalidar_perfil_inativo(self):
        sessao = self._sessao("consulta")
        self.rbac.profiles_update(4, {"active": "N"}, ator="teste")
        self.assertIsNone(self.servico.revalidate(sessao))
        self.assertEqual(self._ultimo_logout("consulta")["detail"],
                         u"sessão encerrada pela revalidação: perfil inativo")

    def test_revalidar_sessao_invalida_nao_audita(self):
        sessao = self._sessao("consulta")
        self.assertIsNone(self.servico.revalidate(dict(sessao, usuario_id=999)))
        self.assertIsNone(self._ultimo_logout("consulta"))

    def test_revalidar_sessao_invalida(self):
        sessao = self._sessao("consulta")
        self.assertIsNone(self.servico.revalidate(dict(sessao, login="admin")))
        self.assertIsNone(self.servico.revalidate(dict(sessao, usuario_id=999)))
        self.assertIsNone(self.servico.revalidate(dict(sessao, usuario_id="4")))
        self.assertIsNone(self.servico.revalidate({}))

    def test_mensagem_de_bloqueio_pela_funcao_do_modulo(self):
        # "Minha senha" bloqueada (controllers/default.py) usa a mesma mensagem do login.
        with mock.patch.object(auth_service, "_service", return_value=self.servico):
            self.assertEqual(auth_service.lock_message(), self.servico.msg_bloqueio)

    def test_controllers_so_usam_nomes_existentes_do_auth_service(self):
        raiz = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "controllers")
        for nome in sorted(os.listdir(raiz)):
            if nome.endswith(".py"):
                with io.open(os.path.join(raiz, nome), encoding="utf-8") as f:
                    for atributo in re.findall(r"\bauth_service\.([A-Za-z_]\w*)", f.read()):
                        self.assertTrue(hasattr(auth_service, atributo), "%s: auth_service.%s" % (nome, atributo))


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
        return dict((u["login"], u["password_hash"]) for u in repo.list(tamanho=100)["itens"])

    def test_sem_variavel_logins_impossiveis(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(repo_factory.ENV_DEV_PASSWORD, None)
            with self.assertLogs("sss_web", level="WARNING"):
                hashes = self._hashes()
        self.assertTrue(all(h == "!" for h in hashes.values()))

    def test_com_variavel(self):
        senha = secrets.token_urlsafe(16)
        with mock.patch.dict(os.environ, {repo_factory.ENV_DEV_PASSWORD: senha}):
            hashes = self._hashes()
        for login in ("admin", "op.prod", "op.hml", "consulta"):
            self.assertTrue(security.verify_password(senha, hashes[login]), login)
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
