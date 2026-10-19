# -*- coding: utf-8 -*-
"""Testes progressivos para os repositorios Oracle 11gR2 (F7.3).

Executa a validacao do agregado ativo selecionado por SSS_TEST_REPO_AGREGADO:
1. RBAC_USUARIOS -> TestOracleRbacUsuarios
2. CATALOGO -> TestOracleCatalogo
3. TICKETS -> TestOracleTickets
4. AGENDAMENTOS -> TestOracleAgendamentos
5. AUDITORIA_AGENTES -> TestOracleAuditoriaAgentes
"""
import datetime
import os
import unittest
from unittest import mock

import _oracle_test_support
import _testenv  # noqa: F401
import db_conn
import repo_errors
import repo_factory
from repo_rbac import RepoRbac
from repo_usuarios import RepoUsuarios


class TestOracleRbacUsuarios(unittest.TestCase):
    """Testes de conformidade e integridade para o agregado RBAC_USUARIOS no Oracle."""

    @classmethod
    def setUpClass(cls):
        agregado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if agregado != "RBAC_USUARIOS":
            raise unittest.SkipTest("Execucao restrita ao agregado RBAC_USUARIOS (atual: %s)" % agregado)

        cls.dsn = os.environ.get("SSS_TEST_DSN")
        cls.owner = os.environ.get("SSS_TEST_OWNER")
        cls.disp = os.environ.get("SSS_TEST_SCHEMA_DISPOSABLE")
        cls.tem_banco_real = bool(cls.dsn and cls.owner and cls.disp == "1")

        if cls.tem_banco_real:
            cls.cfg = _oracle_test_support.preparar_schema_descartavel("web")
            repo_factory.configurar({"app": {"data_backend": "ORACLE", "sss_env": "DEV"}})
        else:
            repo_factory.configurar({"app": {"data_backend": "ORACLE", "sss_env": "DEV"}})

    @classmethod
    def tearDownClass(cls):
        repo_factory.configurar(None)
        repo_factory.reset_singletons()

    def setUp(self):
        repo_factory.reset_singletons()
        self.usr = repo_factory.obter("usuarios")
        self.rbac = repo_factory.obter("rbac")

    def test_instancias_corretas_do_agregado(self):
        """Valida que repo_factory devolve as implementacoes Oracle corretas."""
        self.assertIsInstance(self.usr, RepoUsuarios)
        self.assertIsInstance(self.rbac, RepoRbac)
        self.assertEqual(self.usr.__class__.__name__, "RepoUsuariosOracle")
        self.assertEqual(self.rbac.__class__.__name__, "RepoRbacOracle")

    def test_agregados_seguintes_ainda_nao_implementados(self):
        """Garante que catalogo, tickets, agendamentos e auditoria continuam bloqueados."""
        for agg in ("catalogo", "tickets", "agendamentos", "auditoria", "agentes"):
            with self.assertRaises(NotImplementedError) as ctx:
                repo_factory.obter(agg)
            self.assertIn("Backend ORACLE ainda nao implementado", str(ctx.exception))

    def test_ator_obrigatorio_usuarios_e_perfis(self):
        """Valida que insercao e alteracao sem ator ou com ator longo lancam RepoViolacao."""
        for ator_invalido in (None, "", "   ", "x" * 41):
            with self.assertRaises(repo_errors.RepoViolacao):
                self.usr.inserir({"login": "novo.user", "perfil_id": 1}, ator=ator_invalido)
            with self.assertRaises(repo_errors.RepoViolacao):
                self.rbac.perfis_inserir({"nome": "Novo Perfil"}, ator=ator_invalido)
            with self.assertRaises(repo_errors.RepoViolacao):
                self.usr.desbloquear(1, ator=ator_invalido)

    def test_login_invalido_recusado(self):
        """Valida regex de login em tbsss_usuarios."""
        for log_inv in ("ab", "AB_USER", "user com espaco", "u" * 31, "usr@dominio"):
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.usr.inserir({"login": log_inv, "perfil_id": 1}, ator="admin")
            self.assertEqual(ctx.exception.constraint, self.usr.nome_constraint("ck", "usuarios", "login"))

    def test_banco_real_rbac_usuarios(self):
        """Executa ciclo completo no banco Oracle real quando configurado em DEV descartavel."""
        if not self.tem_banco_real:
            self.skipTest("Banco descartavel real nao configurado (marcado como NAO TESTADO)")

        ator_teste = "teste_agregado"
        prefixo = "tst_%d" % int(datetime.datetime.now().strftime("%H%M%S"))

        # 1. Cria perfil
        nome_perfil = ("P_%s" % prefixo)[:30]
        per = self.rbac.perfis_inserir({
            "nome": nome_perfil,
            "descricao": "Perfil temporario de teste progressivo",
            "is_admin": "N",
            "ativo": "S",
        }, ator=ator_teste)
        self.assertIsNotNone(per.get("id"))
        pid = per["id"]

        try:
            # 2. Cria usuario associado
            login = ("u_%s" % prefixo)[:30].lower()
            usr = self.usr.inserir({
                "login": login,
                "nome": "Usuario de Teste",
                "senha_hash": "hash_fake_123",
                "perfil_id": pid,
                "ativo": "S",
            }, ator=ator_teste)
            self.assertIsNotNone(usr.get("id"))
            uid = usr["id"]

            # 3. Teste do relogio do banco sem microssegundos
            dt_banco = self.usr.agora()
            self.assertEqual(dt_banco.microsecond, 0)

            # 4. Estado da sessao
            sess = self.usr.obter_estado_sessao(uid)
            self.assertEqual(sess["login"], login)
            self.assertEqual(sess["perfil_id"], pid)
            self.assertEqual(sess["sessao_epoch"], 0)

            # 5. Logout incrementa sessao_epoch
            self.usr.encerrar_sessoes(uid, auditoria={"ator": ator_teste, "acao": "LOGOUT"})
            sess2 = self.usr.obter_estado_sessao(uid)
            self.assertEqual(sess2["sessao_epoch"], 1)

            # 6. Falha e sucesso de login
            self.usr.registrar_falha_login(login, bloqueio_s=300)
            u_falha = self.usr.obter_por_id(uid)
            self.assertEqual(u_falha["tentativas_falha"], 1)
            self.assertIsNotNone(u_falha["bloqueado_ate"])

            self.usr.registrar_sucesso_login(login, novo_hash="hash_rehash_456")
            u_ok = self.usr.obter_por_id(uid)
            self.assertEqual(u_ok["tentativas_falha"], 0)
            self.assertIsNone(u_ok["bloqueado_ate"])
            self.assertEqual(u_ok["senha_hash"], "hash_rehash_456")

            # 7. Imutabilidade do login
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.usr.alterar(uid, {"login": "outro_login"}, ator=ator_teste)
            self.assertEqual(ctx.exception.constraint, "tr_tbsss_usr_bu")

            # 8. Unicidade de UKs
            with self.assertRaises(repo_errors.RepoViolacao):
                self.usr.inserir({"login": login, "perfil_id": pid}, ator=ator_teste)
            with self.assertRaises(repo_errors.RepoViolacao):
                self.rbac.perfis_inserir({"nome": nome_perfil}, ator=ator_teste)

        finally:
            # Limpeza cirurgica no schema descartavel
            conn = self.usr._obter_conexao()
            try:
                cur = conn.cursor()
                try:
                    cur.execute("DELETE FROM " + self.usr._tabela() + " WHERE id = :id", {"id": uid})
                    cur.execute("DELETE FROM " + self.rbac._tabela_perfis() + " WHERE id = :id", {"id": pid})
                    conn.commit()
                finally:
                    cur.close()
            finally:
                conn.close()


class TestOracleCatalogo(unittest.TestCase):
    """Testes para o agregado CATALOGO no Oracle (passo 2 do F7.3)."""

    def test_pendente(self):
        agregado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if agregado != "CATALOGO":
            self.skipTest("Agregado CATALOGO sera implementado no passo 2 do F7.3")


class TestOracleTickets(unittest.TestCase):
    """Testes para o agregado TICKETS no Oracle (passo 3 do F7.3)."""

    def test_pendente(self):
        agregado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if agregado != "TICKETS":
            self.skipTest("Agregado TICKETS sera implementado no passo 3 do F7.3")


class TestOracleAgendamentos(unittest.TestCase):
    """Testes para o agregado AGENDAMENTOS no Oracle (passo 4 do F7.3)."""

    def test_pendente(self):
        agregado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if agregado != "AGENDAMENTOS":
            self.skipTest("Agregado AGENDAMENTOS sera implementado no passo 4 do F7.3")


class TestOracleAuditoriaAgentes(unittest.TestCase):
    """Testes para o agregado AUDITORIA_AGENTES no Oracle (passo 5 do F7.3)."""

    def test_pendente(self):
        agregado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if agregado != "AUDITORIA_AGENTES":
            self.skipTest("Agregado AUDITORIA_AGENTES sera implementado no passo 5 do F7.3")


if __name__ == "__main__":
    unittest.main()
