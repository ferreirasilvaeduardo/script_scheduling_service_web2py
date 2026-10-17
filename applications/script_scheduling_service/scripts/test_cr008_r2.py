# -*- coding: utf-8 -*-
"""CR-008 R2: ator mascarado fora do quadro Registro (E5), registro do esquema (R-13, R-28) e regras de agendamento."""
import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

import auth_service
import rbac
import repo_factory
import security
import sql_ident
import ui_helpers
from agendamentos_service import ServicoAgendamentos
from ticket_service import ServicoTicket

SESSAO_ADMIN = {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0}


class TestAtorVisivel(unittest.TestCase):

    def test_regras(self):
        sem = {"login": "op.prod", "funcionalidades": frozenset(["VER_LOGS"])}
        self.assertEqual(ui_helpers.ator_visivel("op.prod", sem), u"você")
        self.assertEqual(ui_helpers.ator_visivel("admin", sem), u"outra pessoa")
        self.assertEqual(ui_helpers.ator_visivel("SYSTEM:agt-host01", sem), "SYSTEM:agt-host01")
        self.assertIsNone(ui_helpers.ator_visivel(None, sem))
        self.assertEqual(ui_helpers.ator_visivel("admin", dict(sem, funcionalidades=frozenset(["VER_AUDITORIA"]))),
                         "admin")
        self.assertEqual(ui_helpers.ator_visivel("admin", {"is_admin": True}), "admin")


class TestResponsavelMascarado(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(security, "ITERACOES", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_SENHA_DEV: "senha-dev-de-teste-123"})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configurar, None)
        log = logging.getLogger("sss_teste_cr008_r2")
        log.addHandler(logging.NullHandler())
        log.propagate = False
        r = repo_factory.obter
        auth = auth_service.ServicoAuth(r("usuarios"), r("rbac"), r("catalogo"), r("auditoria"), 5, 900, log)
        self.admin = auth.revalidar(SESSAO_ADMIN)
        tickets = r("tickets")
        ticket = ServicoTicket(catalogo=r("catalogo"), tickets=tickets, script_owner_uids=(0,), log=log,
                               dirs_sss=("/nao/existe/log", "/nao/existe/work"))
        self.svc = ServicoAgendamentos(r("agendamentos"), r("catalogo"), r("usuarios"), ticket, tickets.agora, 1461, log)
        # op.prod com o necessario para ver as regras, mas sem VER_AUDITORIA.
        self.operador = dict(self.admin, usuario_id=2, login="op.prod", is_admin=False,
                             funcionalidades=frozenset(f for f in self.admin["funcionalidades"] if f != "VER_AUDITORIA"))

    def test_lista_e_formulario(self):
        responsaveis = set(i["responsavel"] for i in self.svc.listar(self.operador, {}, 1, 100)["itens"])
        self.assertTrue(responsaveis)
        self.assertTrue(responsaveis <= {u"você", u"outra pessoa"}, responsaveis)
        self.assertEqual(self.svc.formulario(self.operador, "2")["regra"]["responsavel"], u"você")
        self.assertEqual(self.svc.formulario(self.admin, "2")["regra"]["responsavel"], "op.prod")


class TestMotivoPausa(unittest.TestCase):

    def test_traducao_unica(self):
        # CR-008, R-33: a mesma funcao pura na web e no daemon (README §7.5).
        M = rbac.Motivo
        for motivo in (M.USUARIO_INATIVO, M.SCRIPT_INATIVO, M.AMBIENTE_INATIVO):
            self.assertEqual(rbac.motivo_pausa(motivo), motivo)
        for motivo in (M.PERFIL_INATIVO, M.SEM_HOMOLOGACAO, M.SEM_FUNC, M.SEM_AMBIENTE, M.SEM_SCRIPT,
                       M.DADO_INVALIDO):
            self.assertEqual(rbac.motivo_pausa(motivo), "SEM_PERMISSAO")


class TestRegistroEsquema(unittest.TestCase):

    def test_colunas_novas_e_ampliadas(self):
        usr = sql_ident.TABELAS["usuarios"]["colunas"]["sessao_epoch"]
        self.assertEqual((usr["tipo"], usr["not_null"], usr["default"]), ("NUMBER(10)", True, "0"))
        self.assertEqual(sql_ident.TABELAS["agentes"]["colunas"]["pid_daemon"]["tipo"], "NUMBER(10)")
        self.assertEqual(sql_ident.VERSAO_ESQUEMA, 1)

    def test_prefixo_so_minusculo(self):
        self.assertRegex("tbsss_", sql_ident.PADRAO_PREFIXO)
        self.assertNotRegex("TBSSS_", sql_ident.PADRAO_PREFIXO)


if __name__ == "__main__":
    unittest.main()
