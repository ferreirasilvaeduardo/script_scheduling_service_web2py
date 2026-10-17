# -*- coding: utf-8 -*-
"""Quadro Registro nos servicos (CR-006, README §10): formularios de edicao e detalhe do ticket."""
import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

import auth_service
import repo_factory
import security
import ui_helpers
from admin_ambientes_service import ServicoAdminAmbientes
from admin_parametros_service import ServicoAdminParametros
from admin_perfis_service import ServicoAdminPerfis
from admin_scripts_service import ServicoAdminScripts
from admin_usuarios_service import ServicoAdminUsuarios
from agendamentos_service import ServicoAgendamentos
from ticket_service import ServicoTicket

IP = "10.9.8.7"
SESSAO_ADMIN = {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0}


class TestRegistroNosServicos(unittest.TestCase):

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
        log = logging.getLogger("sss_teste_registro")
        log.addHandler(logging.NullHandler())
        log.propagate = False
        r = repo_factory.obter
        self.r = r
        auth = auth_service.ServicoAuth(r("usuarios"), r("rbac"), r("catalogo"), r("auditoria"), 5, 900, log)
        self.ctx = auth.revalidar(SESSAO_ADMIN)
        tickets = r("tickets")
        self.ticket = ServicoTicket(catalogo=r("catalogo"), tickets=tickets, script_owner_uids=(0,), log=log,
                                    dirs_sss=("/nao/existe/log", "/nao/existe/work"))
        self.servicos = {
            "ambientes": (ServicoAdminAmbientes(r("catalogo"), r("agendamentos"), log), 1,
                          lambda: r("catalogo").ambientes_obter(1)),
            "perfis": (ServicoAdminPerfis(r("rbac"), r("catalogo"), r("usuarios"), log), 2,
                       lambda: r("rbac").perfis_obter(2)),
            "usuarios": (ServicoAdminUsuarios(r("usuarios"), r("rbac"), log), 2,
                         lambda: r("usuarios").obter_por_id(2)),
            "parametros": (ServicoAdminParametros(r("catalogo"), log), 1,
                           lambda: r("catalogo").parametros_obter(1)),
            "scripts": (ServicoAdminScripts(r("catalogo"), r("agendamentos"), (0,), "DEV", log, tickets.agora,
                                            ("/nao/existe/log", "/nao/existe/work")), 1,
                        lambda: r("catalogo").scripts_obter(1)),
        }
        self.agendamentos = ServicoAgendamentos(r("agendamentos"), r("catalogo"), r("usuarios"), self.ticket,
                                                tickets.agora, 1461, log)

    def test_formularios_de_inclusao_sem_registro_e_de_edicao_com_as_quatro_colunas(self):
        for nome, (svc, rid, ler) in self.servicos.items():
            self.assertIsNone(svc.formulario(self.ctx)["registro"], nome)
            self.assertEqual(svc.formulario(self.ctx, str(rid))["registro"], ui_helpers.registro(ler(), self.ctx), nome)
            self.assertEqual(svc.formulario(self.ctx, str(rid))["registro"]["created_by"], "SYSTEM:seed", nome)

    def test_registro_sem_auditoria_nos_servicos_e_aviso_de_pausa(self):
        ctx = dict(self.ctx, is_admin=False, login="op.prod", usuario_id=2,
                   funcionalidades=frozenset(f for f in self.ctx["funcionalidades"] if f != "VER_AUDITORIA"),
                   ambientes=frozenset(("PRODUCAO", "HOMOLOGACAO")), scripts=frozenset((1, 2, 3, 4, 5, 6)))
        store = repo_factory._fake_store
        for tabela, rid in (("ambientes", 1), ("perfis", 2), ("usuarios", 2), ("parametros", 1),
                            ("scripts", 1), ("agendamentos", 5), ("tickets", 17)):
            registro = getattr(store, tabela)[rid]
            registro["created_by"] = "editor.privado"
            registro["updated_by"] = "op.prod"
            registro["updated_at"] = store.agora()
        for nome, (svc, rid, ler) in self.servicos.items():
            registro = svc.formulario(ctx, str(rid))["registro"]
            self.assertEqual((registro["created_by"], registro["updated_by"]),
                             (u"outra pessoa", u"você"), nome)
        regra = self.agendamentos.formulario(ctx, "5")["regra"]
        self.assertEqual(regra["registro"]["created_by"], u"outra pessoa")
        self.assertIn(u"por você", regra["pausa_aviso"])
        detalhe = self.ticket.detalhe(ctx, 17)
        self.assertEqual(detalhe["registro"]["created_by"], u"outra pessoa")
        self.assertNotIn("editor.privado", str(detalhe["registro"]))

    def test_edicao_pela_tela_grava_o_editor(self):
        svc, rid, ler = self.servicos["ambientes"]
        form = svc.formulario(self.ctx, str(rid))
        _id, erros = svc.salvar(self.ctx, IP, str(rid), {"descricao": "Editada", "conexao": form["conexao"],
                                                         "versao": form["versao"]})
        self.assertEqual(erros, {})
        reg = svc.formulario(self.ctx, str(rid))["registro"]
        self.assertEqual((reg["created_by"], reg["updated_by"]), ("SYSTEM:seed", "admin"))
        self.assertEqual(svc.formulario(self.ctx, str(rid))["versao"] != form["versao"], True)

    def test_agendamento_e_ticket(self):
        regra = self.agendamentos.formulario(self.ctx, "5")["regra"]
        self.assertEqual(regra["registro"], ui_helpers.registro(self.r("agendamentos").obter(5), self.ctx))
        self.assertEqual(regra["registro"]["created_by"], "SYSTEM:seed")
        self.assertEqual(regra["registro"]["updated_by"], "admin")
        detalhe = self.ticket.detalhe(self.ctx, 17)
        bruto = self.r("tickets").obter(17)
        self.assertEqual(detalhe["registro"], ui_helpers.registro(bruto, self.ctx))
        self.assertTrue(detalhe["registro"]["updated_by"].startswith("SYSTEM:agt-"))


if __name__ == "__main__":
    unittest.main()
