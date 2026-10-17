# -*- coding: utf-8 -*-
"""Testes de permissoes_service.py: tela "O que eu posso fazer" (README §4.3.E, CR-004 U3) sobre o FAKE."""
import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

import auth_service
import permissoes_service as svc_mod
import repo_factory
import security
from permissoes_service import ServicoPermissoes
from ticket_service import ServicoTicket

SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1},
    "op.hml": {"usuario_id": 3, "login": "op.hml", "perfil_id": 3, "perm_versao": 1},
    "consulta": {"usuario_id": 4, "login": "consulta", "perfil_id": 4, "perm_versao": 1},
}


class TestPermissoes(unittest.TestCase):

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
        self.catalogo = repo_factory.obter("catalogo")
        self.rbac_repo = repo_factory.obter("rbac")
        log = logging.getLogger("sss_teste_permissoes")
        log.addHandler(logging.NullHandler())
        log.propagate = False
        auth = auth_service.ServicoAuth(repo_factory.obter("usuarios"), self.rbac_repo, self.catalogo,
                                        repo_factory.obter("auditoria"), 5, 900, log)
        self.ctx = dict((login, auth.revalidar(sessao)) for login, sessao in SESSOES.items())
        disparo = ServicoTicket(self.catalogo, repo_factory.obter("tickets"), (0,), log)
        self.svc = ServicoPermissoes(self.rbac_repo, self.catalogo, disparo, log)
        self.disparo = disparo
        self.n_auditoria = repo_factory.obter("auditoria").listar(pagina=1, tamanho=1)["total"]

    def test_admin_ve_frase_e_todas_as_telas(self):
        d = self.svc.montar(self.ctx["admin"])
        self.assertEqual(d["frase_admin"], svc_mod.FRASE_ADMIN)
        self.assertEqual(len(d["telas"]), 10)
        self.assertEqual(d["ausentes"], [])
        rotas = dict((t["codigo"], t["rota"]) for t in d["telas"])
        self.assertEqual(rotas["CAD_PERFIS"], ("admin_perfis", "lista"))
        self.assertIsNone(rotas["CANC_TICKET"])  # acao, nao tela

    def test_sem_exec_script_mostra_frase_e_motivo(self):
        d = self.svc.montar(self.ctx["consulta"])
        self.assertFalse(d["pode_executar"])
        self.assertEqual(d["frase_sem_exec"], svc_mod.FRASE_SEM_EXEC)
        self.assertEqual(d["scripts"], [])
        self.assertTrue(all(a["motivo"] == svc_mod.MOTIVO_SEM_FUNC for a in d["ausentes"]))
        self.assertEqual([t["codigo"] for t in d["telas"]], ["VER_LOGS"])

    def test_scripts_e_ambientes_iguais_aos_do_disparo(self):
        ctx = self.ctx["op.hml"]
        d = self.svc.montar(ctx)
        esperado = sorted(s["id"] for g in self.disparo.scripts_disponiveis(ctx) for s in g["scripts"])
        self.assertEqual(sorted(s["id"] for s in d["scripts"]), esperado)
        for s in d["scripts"]:
            self.assertTrue(s["ambientes"])
            self.assertTrue(set(s["ambientes"]) <= set(ctx["ambientes"]))

    def test_motivos_e_catalogo_nao_vazado(self):
        ctx = dict(self.ctx["op.hml"])
        # Script do perfil desativado e script do perfil sem homologacao nos ambientes dele.
        sid_inativo = sorted(ctx["scripts"])[0]
        self.catalogo.scripts_alterar(sid_inativo, {"ativo": "N"}, ator="teste")
        novo = self.catalogo.scripts_inserir({"nome": "So em PRODUCAO", "interpretador": "PYTHON3",
                                              "path_file": "/opt/scripts/x.py",
                                              "tipo_param": "NENHUM"}, ator="teste")["id"]
        prod = [a for a in self.catalogo.ambientes_listar(pagina=1, tamanho=50)["itens"] if a["nome"] == "PRODUCAO"][0]
        self.catalogo.homologacao_salvar(novo, [prod["id"]], ator="teste")
        ctx["scripts"] = frozenset(ctx["scripts"]) | frozenset([novo])
        ctx["ambientes"] = frozenset(a for a in ctx["ambientes"] if a != "PRODUCAO")
        d = self.svc.montar(ctx)
        motivos = dict((a["nome"], a["motivo"]) for a in d["ausentes"])
        nome_inativo = self.catalogo.scripts_obter(sid_inativo)["nome"]
        self.assertEqual(motivos[nome_inativo], svc_mod.MOTIVO_SCRIPT_INATIVO)
        self.assertEqual(motivos["So em PRODUCAO"], svc_mod.MOTIVO_SEM_HOMOLOGACAO)
        fora = set(s["nome"] for s in self.catalogo.scripts_listar(pagina=1, tamanho=100)["itens"]
                   if s["id"] not in ctx["scripts"])
        self.assertFalse(fora & set(motivos))
        self.assertFalse(fora & set(s["nome"] for s in d["scripts"]))

    def test_nao_grava_nem_audita(self):
        self.svc.montar(self.ctx["op.hml"])
        self.assertEqual(repo_factory.obter("auditoria").listar(pagina=1, tamanho=1)["total"], self.n_auditoria)


if __name__ == "__main__":
    unittest.main()
