# -*- coding: utf-8 -*-
"""Testes de auth_service.py (F2.2) sobre o backend FAKE com relogio injetado."""
import _testenv  # noqa: F401

import datetime
import hashlib
import logging
import os
import secrets
import unittest
from unittest import mock

import auth_service
import repo_factory
import security
from auth_service import MSG_BLOQUEIO, MSG_GENERICA

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
        self.agora = agora

    def __call__(self):
        return self.agora

    def avancar(self, segundos):
        self.agora += datetime.timedelta(seconds=segundos)


class TestAuthService(unittest.TestCase):

    def setUp(self):
        # Iteracoes reduzidas apenas para o tempo de execucao; o fluxo e o mesmo do vigente.
        patcher = mock.patch.object(security, "ITERACOES", ITER_TESTE)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.senha = secrets.token_urlsafe(16)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_SENHA_DEV: self.senha})
        env.start()
        self.addCleanup(env.stop)

        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configurar, None)

        self.usuarios = repo_factory.obter("usuarios")
        self.rbac = repo_factory.obter("rbac")
        self.auditoria = repo_factory.obter("auditoria")
        self.relogio = _Relogio(INICIO)
        log = logging.getLogger("test_auth_service")
        log.addHandler(logging.NullHandler())
        log.propagate = False
        self.servico = auth_service.ServicoAuth(
            usuarios=self.usuarios, rbac_repo=self.rbac, catalogo=repo_factory.obter("catalogo"),
            auditoria=self.auditoria, max_tentativas=MAX, bloqueio_s=BLOQUEIO_S, log=log,
            relogio=self.relogio,
        )
        self.usuarios.alterar(5, {"senha_hash": security.hash_senha(self.senha)})
        self.aud_base = max(a["id"] for a in self.auditoria.listar(tamanho=1000)["itens"])

    def _acoes(self, ator):
        itens = self.auditoria.listar({"ator": ator}, pagina=1, tamanho=100)["itens"]
        return [a["acao"] for a in itens if a["ator"] == ator and a["id"] > self.aud_base]

    def _errar(self, login, vezes):
        resultado = None
        for _ in range(vezes):
            resultado = self.servico.autenticar(login, "senha-errada-123", "10.0.0.1")
        return resultado

    def test_sucesso(self):
        ctx, msg = self.servico.autenticar("admin", self.senha, "10.0.0.1")
        self.assertIsNone(msg)
        self.assertEqual(ctx["login"], "admin")
        self.assertTrue(ctx["is_admin"])
        self.assertIn("CAD_USUARIOS", ctx["funcionalidades"])
        u = self.usuarios.obter_por_id(1)
        self.assertEqual(u["ultimo_login"], INICIO)
        self.assertEqual(u["tentativas_falha"], 0)
        self.assertEqual(self._acoes("admin"), ["LOGIN_OK"])

    def test_login_normalizado(self):
        ctx, _ = self.servico.autenticar("  ADMIN ", self.senha, "10.0.0.1")
        self.assertEqual(ctx["login"], "admin")

    def test_ctx_nao_admin(self):
        ctx, _ = self.servico.autenticar("consulta", self.senha, "10.0.0.1")
        self.assertFalse(ctx["is_admin"])
        self.assertEqual(ctx["funcionalidades"], frozenset(["VER_LOGS"]))
        self.assertEqual(ctx["ambientes"], frozenset(["PRODUCAO", "HOMOLOGACAO"]))

    def test_senha_errada(self):
        ctx, msg = self.servico.autenticar("admin", "senha-errada-123", "10.0.0.1")
        self.assertIsNone(ctx)
        self.assertEqual(msg, MSG_GENERICA)
        self.assertEqual(self.usuarios.obter_por_id(1)["tentativas_falha"], 1)
        self.assertEqual(self._acoes("admin"), ["LOGIN_FALHA"])

    def test_inexistente_mesma_mensagem(self):
        ctx, msg = self.servico.autenticar("naoexiste", self.senha, "10.0.0.1")
        self.assertIsNone(ctx)
        self.assertEqual(msg, MSG_GENERICA)
        self.assertEqual(self._acoes("naoexiste"), ["LOGIN_FALHA"])

    def test_entradas_invalidas(self):
        for login, senha in ((None, self.senha), ("a", self.senha), ("x" * 200, self.senha),
                             ("admin", None), ("admin", ""), ("admin", "x" * 5000), (["admin"], self.senha)):
            self.assertEqual(self.servico.autenticar(login, senha, "10.0.0.1"), (None, MSG_GENERICA))

    def test_bloqueio_na_enesima_falha(self):
        self.assertEqual(self._errar("op.prod", MAX - 1), (None, MSG_GENERICA))
        self.assertEqual(self._errar("op.prod", 1), (None, MSG_BLOQUEIO))
        u = self.usuarios.obter_por_id(2)
        self.assertEqual(u["tentativas_falha"], MAX)
        self.assertEqual(u["bloqueado_ate"], INICIO + datetime.timedelta(seconds=BLOQUEIO_S))
        acoes = self._acoes("op.prod")
        self.assertEqual(acoes.count("LOGIN_FALHA"), MAX)
        self.assertEqual(acoes.count("LOGIN_BLOQUEIO"), 1)

    def test_senha_correta_durante_bloqueio(self):
        self._errar("op.prod", MAX)
        self.relogio.avancar(BLOQUEIO_S - 1)
        self.assertEqual(self.servico.autenticar("op.prod", self.senha, "10.0.0.1"), (None, MSG_BLOQUEIO))
        # Tentativas durante o bloqueio nao o prolongam.
        u = self.usuarios.obter_por_id(2)
        self.assertEqual(u["bloqueado_ate"], INICIO + datetime.timedelta(seconds=BLOQUEIO_S))

    def test_desbloqueio_por_tempo(self):
        self._errar("op.prod", MAX)
        self.relogio.avancar(BLOQUEIO_S)
        self.assertEqual(self._errar("op.prod", 1), (None, MSG_GENERICA))
        self.assertEqual(self.usuarios.obter_por_id(2)["tentativas_falha"], 1)
        ctx, msg = self.servico.autenticar("op.prod", self.senha, "10.0.0.1")
        self.assertIsNone(msg)
        u = self.usuarios.obter_por_id(2)
        self.assertEqual((u["tentativas_falha"], u["bloqueado_ate"]), (0, None))

    def test_inexistente_bloqueio_simulado(self):
        self.assertEqual(self._errar("fantasma", MAX - 1), (None, MSG_GENERICA))
        self.assertEqual(self._errar("fantasma", 1), (None, MSG_BLOQUEIO))
        self.assertEqual(self._errar("fantasma", 1), (None, MSG_BLOQUEIO))
        self.relogio.avancar(BLOQUEIO_S)
        self.assertEqual(self._errar("fantasma", 1), (None, MSG_GENERICA))
        self.assertIn("LOGIN_BLOQUEIO", self._acoes("fantasma"))

    def test_seed_bloqueado(self):
        self.usuarios.alterar(6, {"senha_hash": security.hash_senha(self.senha),
                                  "bloqueado_ate": INICIO + datetime.timedelta(minutes=5)})
        self.assertEqual(self.servico.autenticar("bloqueado", self.senha, "10.0.0.1"), (None, MSG_BLOQUEIO))

    def test_usuario_inativo(self):
        self.assertEqual(self.servico.autenticar("inativo", self.senha, "10.0.0.1"), (None, MSG_GENERICA))
        self.assertEqual(self.usuarios.obter_por_id(5)["tentativas_falha"], 0)
        self.assertEqual(self._acoes("inativo"), ["LOGIN_FALHA"])

    def test_perfil_inativo(self):
        self.rbac.perfis_alterar(4, {"ativo": "N"})
        self.assertEqual(self.servico.autenticar("consulta", self.senha, "10.0.0.1"), (None, MSG_GENERICA))

    def test_hash_inutilizavel(self):
        self.usuarios.alterar(3, {"senha_hash": "!"})
        self.assertEqual(self.servico.autenticar("op.hml", "!", "10.0.0.1"), (None, MSG_GENERICA))

    def test_rehash(self):
        self.usuarios.alterar(1, {"senha_hash": _hash_com_iteracoes(self.senha, ITER_TESTE // 2)})
        antes = self.usuarios.obter_por_id(1)["senha_alterada_em"]
        ctx, msg = self.servico.autenticar("admin", self.senha, "10.0.0.1")
        self.assertIsNone(msg)
        u = self.usuarios.obter_por_id(1)
        self.assertTrue(u["senha_hash"].startswith("pbkdf2_sha256$%d$" % ITER_TESTE))
        self.assertFalse(security.precisa_rehash(u["senha_hash"]))
        self.assertTrue(security.verificar_senha(self.senha, u["senha_hash"]))
        self.assertEqual(u["senha_alterada_em"], antes)

    def test_auditoria_sem_senha(self):
        self.servico.autenticar("admin", self.senha, "10.0.0.1")
        self.servico.autenticar("admin", "senha-errada-123", "10.0.0.1")
        for reg in self.auditoria.listar(tamanho=1000)["itens"]:
            self.assertNotIn(self.senha, reg.get("detalhe") or "")
            self.assertNotIn("senha-errada-123", reg.get("detalhe") or "")
            self.assertNotIn("pbkdf2", reg.get("detalhe") or "")

    def test_logout_auditado(self):
        ctx, _ = self.servico.autenticar("admin", self.senha, "10.0.0.1")
        self.servico.logout(ctx, "10.0.0.1")
        self.assertEqual(self._acoes("admin"), ["LOGOUT", "LOGIN_OK"])

    # -------------------------------------------------------------- revalidar

    def _sessao(self, login):
        ctx, _ = self.servico.autenticar(login, self.senha, "10.0.0.1")
        return {"usuario_id": ctx["usuario_id"], "login": ctx["login"],
                "perfil_id": ctx["perfil_id"], "perm_versao": ctx["perm_versao"]}

    def test_revalidar_ok(self):
        sessao = self._sessao("consulta")
        ctx = self.servico.revalidar(sessao)
        self.assertEqual(ctx["funcionalidades"], frozenset(["VER_LOGS"]))

    def test_revalidar_recarrega_com_perm_versao(self):
        sessao = self._sessao("consulta")
        self.assertNotIn("EXEC_SCRIPT", self.servico.revalidar(sessao)["funcionalidades"])
        matriz = self.rbac.matriz_obter(4)
        self.rbac.matriz_salvar(4, list(matriz["funcs"]) + [1], matriz["ambs"], matriz["scrs"])
        ctx = self.servico.revalidar(sessao)
        self.assertIn("EXEC_SCRIPT", ctx["funcionalidades"])
        self.assertGreater(ctx["perm_versao"], sessao["perm_versao"])

    def test_revalidar_usuario_inativo(self):
        sessao = self._sessao("op.prod")
        self.usuarios.alterar(2, {"ativo": "N"})
        self.assertIsNone(self.servico.revalidar(sessao))

    def test_revalidar_perfil_inativo(self):
        sessao = self._sessao("consulta")
        self.rbac.perfis_alterar(4, {"ativo": "N"})
        self.assertIsNone(self.servico.revalidar(sessao))

    def test_revalidar_sessao_invalida(self):
        sessao = self._sessao("consulta")
        self.assertIsNone(self.servico.revalidar(dict(sessao, login="admin")))
        self.assertIsNone(self.servico.revalidar(dict(sessao, usuario_id=999)))
        self.assertIsNone(self.servico.revalidar(dict(sessao, usuario_id="4")))
        self.assertIsNone(self.servico.revalidar({}))


class TestSeedDev(unittest.TestCase):

    def setUp(self):
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configurar, None)
        patcher = mock.patch.object(security, "ITERACOES", ITER_TESTE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _hashes(self):
        repo = repo_factory.obter("usuarios")
        return dict((u["login"], u["senha_hash"]) for u in repo.listar(tamanho=100)["itens"])

    def test_sem_variavel_logins_impossiveis(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(repo_factory.ENV_SENHA_DEV, None)
            with self.assertLogs("sss_web", level="WARNING"):
                hashes = self._hashes()
        self.assertTrue(all(h == "!" for h in hashes.values()))

    def test_com_variavel(self):
        senha = secrets.token_urlsafe(16)
        with mock.patch.dict(os.environ, {repo_factory.ENV_SENHA_DEV: senha}):
            hashes = self._hashes()
        for login in ("admin", "op.prod", "op.hml", "consulta"):
            self.assertTrue(security.verificar_senha(senha, hashes[login]), login)
        self.assertEqual(hashes["inativo"], "!")
        self.assertEqual(hashes["bloqueado"], "!")
        self.assertNotEqual(hashes["admin"], hashes["consulta"])

    def test_variavel_fora_da_politica(self):
        with mock.patch.dict(os.environ, {repo_factory.ENV_SENHA_DEV: "curta"}):
            with self.assertLogs("sss_web", level="WARNING"):
                hashes = self._hashes()
        self.assertTrue(all(h == "!" for h in hashes.values()))


if __name__ == "__main__":
    unittest.main()
