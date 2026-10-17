# -*- coding: utf-8 -*-
"""CR-008 R1: administrador so por administrador (E1), sessao revogavel (E2) e regex com quantificador largo (R-06)."""
import _testenv  # noqa: F401

import datetime
import logging
import os
import re
import time
import unittest
from unittest import mock

import admin_perfis_service as perfis_mod
import admin_usuarios_service as usr_mod
import auth_service
import params_compiler
import repo_factory
import security
from admin_crud import CAMPO_GERAL, OperacaoNegada
from admin_perfis_service import ServicoAdminPerfis
from admin_usuarios_service import ServicoAdminUsuarios
from params_compiler import ParamErro

IP = "10.8.8.8"
SENHA_DEV = "senha-dev-de-teste-123"
SENHA_NOVA = "Nova-Senha-Forte-2026"
AGORA = datetime.datetime(2026, 10, 17, 9, 0, 0)
U_ADMIN, U_OPPROD, U_OPHML = 1, 2, 3
P_ADMIN, P_OPPROD, P_CONSULTA = 1, 2, 4


def _sessao(uid, login, perfil_id):
    return {"usuario_id": uid, "login": login, "perfil_id": perfil_id, "perm_versao": 1, "sessao_epoch": 0}


class _Base(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(security, "ITERACOES", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_SENHA_DEV: SENHA_DEV})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configurar, None)
        self.usuarios = repo_factory.obter("usuarios")
        self.rbac_repo = repo_factory.obter("rbac")
        self.auditoria = repo_factory.obter("auditoria")
        self.log = logging.getLogger("sss_teste_cr008")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        self.auth = auth_service.ServicoAuth(self.usuarios, self.rbac_repo, repo_factory.obter("catalogo"),
                                             self.auditoria, 5, 900, self.log, relogio=lambda: AGORA)
        self.ctx = {"admin": self.auth.revalidar(_sessao(U_ADMIN, "admin", P_ADMIN)),
                    "op.prod": self.auth.revalidar(_sessao(U_OPPROD, "op.prod", P_OPPROD))}
        # Gestor sem perfil de administrador, com as funcionalidades de cadastro (CR-008, F-05).
        self.ctx["gestor"] = dict(self.ctx["op.prod"], funcionalidades=frozenset(["CAD_USUARIOS", "CAD_PERFIS"]))
        self.svc_usr = ServicoAdminUsuarios(self.usuarios, self.rbac_repo, self.log, relogio=lambda: AGORA)
        self.svc_per = ServicoAdminPerfis(self.rbac_repo, repo_factory.obter("catalogo"), self.usuarios, self.log)


class TestAdminSoPorAdmin(_Base):

    def test_gestor_nao_cria_usuario_admin(self):
        dados = {"login": "novo.admin", "nome": "Novo", "perfil_id": str(P_ADMIN),
                 "senha": SENHA_NOVA, "confirmacao": SENHA_NOVA}
        uid, erros = self.svc_usr.salvar(self.ctx["gestor"], IP, None, dados)
        self.assertEqual((uid, erros), (None, {"perfil_id": usr_mod.MSG_SO_ADMIN}))
        self.assertIsNone(self.usuarios.obter_por_login("novo.admin"))
        uid, erros = self.svc_usr.salvar(self.ctx["gestor"], IP, None, dict(dados, perfil_id=str(P_CONSULTA)))
        self.assertEqual(erros, {})

    def test_gestor_nao_se_promove_nem_altera_admin(self):
        form = self.svc_usr.formulario(self.ctx["gestor"], str(U_OPPROD))
        _id, erros = self.svc_usr.salvar(self.ctx["gestor"], IP, str(U_OPPROD),
                                         {"nome": form["nome"], "perfil_id": str(P_ADMIN), "versao": form["versao"]})
        self.assertEqual(erros, {CAMPO_GERAL: usr_mod.MSG_SO_ADMIN})
        self.assertEqual(self.usuarios.obter_por_id(U_OPPROD)["perfil_id"], P_OPPROD)
        form = self.svc_usr.formulario(self.ctx["gestor"], str(U_ADMIN))
        _id, erros = self.svc_usr.salvar(self.ctx["gestor"], IP, str(U_ADMIN),
                                         {"nome": "Outro", "perfil_id": str(P_ADMIN), "versao": form["versao"]})
        self.assertEqual(erros, {CAMPO_GERAL: usr_mod.MSG_SO_ADMIN})
        for acao in (lambda: self.svc_usr.redefinir_senha(self.ctx["gestor"], IP, str(U_ADMIN), SENHA_NOVA, SENHA_NOVA),
                     lambda: self.svc_usr.desbloquear(self.ctx["gestor"], IP, str(U_ADMIN)),
                     lambda: self.svc_usr.alternar_ativo(self.ctx["gestor"], IP, str(U_ADMIN), form["versao"])):
            with self.assertRaises(OperacaoNegada) as cm:
                acao()
            self.assertEqual(cm.exception.mensagem, usr_mod.MSG_SO_ADMIN)
        admin = self.usuarios.obter_por_id(U_ADMIN)
        self.assertEqual((admin["ativo"], admin["sessao_epoch"]), ("S", 0))

    def test_gestor_altera_usuario_comum_e_admin_altera_admin(self):
        self.assertEqual(self.svc_usr.redefinir_senha(self.ctx["gestor"], IP, str(U_OPHML), SENHA_NOVA, SENHA_NOVA), {})
        form = self.svc_usr.formulario(self.ctx["admin"], str(U_OPHML))
        _id, erros = self.svc_usr.salvar(self.ctx["admin"], IP, str(U_OPHML),
                                         {"nome": form["nome"], "perfil_id": str(P_ADMIN), "versao": form["versao"]})
        self.assertEqual(erros, {})

    def test_gestor_nao_marca_admin_nem_mexe_no_proprio_perfil(self):
        _id, erros = self.svc_per.salvar(self.ctx["gestor"], IP, None, {"nome": "SUPORTE", "is_admin": "S"})
        self.assertEqual(erros, {CAMPO_GERAL: perfis_mod.MSG_SO_ADMIN})
        form = self.svc_per.formulario(self.ctx["gestor"], str(P_OPPROD))
        _id, erros = self.svc_per.salvar(self.ctx["gestor"], IP, str(P_OPPROD),
                                         {"nome": form["nome"], "descricao": "nova", "versao": form["versao"]})
        self.assertEqual(erros, {CAMPO_GERAL: perfis_mod.MSG_SO_ADMIN})
        matriz = self.rbac_repo.matriz_obter(P_OPPROD)
        todas = [f["id"] for f in self.rbac_repo.funcionalidades_listar()]
        diff, erros = self.svc_per.salvar_matriz(self.ctx["gestor"], IP, str(P_OPPROD), [str(i) for i in todas],
                                                 [str(i) for i in matriz["ambs"]], [str(i) for i in matriz["scrs"]],
                                                 str(self.rbac_repo.perfis_obter(P_OPPROD)["perm_versao"]))
        self.assertEqual((diff, erros), (None, {CAMPO_GERAL: perfis_mod.MSG_SO_ADMIN}))
        self.assertEqual(self.rbac_repo.matriz_obter(P_OPPROD), matriz)
        # Perfil comum de outra pessoa continua editavel pelo gestor.
        form = self.svc_per.formulario(self.ctx["gestor"], str(P_CONSULTA))
        _id, erros = self.svc_per.salvar(self.ctx["gestor"], IP, str(P_CONSULTA),
                                         {"nome": form["nome"], "descricao": "leitura", "versao": form["versao"]})
        self.assertEqual(erros, {})


class TestSessaoRevogavel(_Base):

    def _epoch(self, uid):
        return self.usuarios.obter_por_id(uid)["sessao_epoch"]

    def test_eventos_que_revogam(self):
        sessao = _sessao(U_OPHML, "op.hml", 3)
        self.assertIsNotNone(self.auth.revalidar(sessao))
        self.svc_usr.redefinir_senha(self.ctx["admin"], IP, str(U_OPHML), SENHA_NOVA, SENHA_NOVA)
        self.assertEqual(self._epoch(U_OPHML), 1)
        self.assertIsNone(self.auth.revalidar(sessao))
        sessao["sessao_epoch"] = 1
        self.assertIsNotNone(self.auth.revalidar(sessao))
        form = self.svc_usr.formulario(self.ctx["admin"], str(U_OPHML))
        self.svc_usr.salvar(self.ctx["admin"], IP, str(U_OPHML),
                            {"nome": "Outro nome", "perfil_id": str(3), "versao": form["versao"]})
        self.assertEqual(self._epoch(U_OPHML), 1, "so o nome mudou")
        self.svc_usr.salvar(self.ctx["admin"], IP, str(U_OPHML),
                            {"nome": "Outro nome", "perfil_id": str(P_CONSULTA),
                             "versao": self.svc_usr.formulario(self.ctx["admin"], str(U_OPHML))["versao"]})
        self.assertEqual(self._epoch(U_OPHML), 2)

    def test_logout_derruba_todas_as_sessoes_e_audita(self):
        outra = _sessao(U_OPPROD, "op.prod", P_OPPROD)
        self.auth.logout(self.ctx["op.prod"], IP)
        self.assertEqual(self._epoch(U_OPPROD), 1)
        self.assertIsNone(self.auth.revalidar(outra))
        logout = [a for a in self.auditoria.listar(filtros={"acao": "LOGOUT"}, pagina=1, tamanho=10)["itens"]
                  if a["ator"] == "op.prod"]
        self.assertEqual((logout[0]["entidade"], logout[0]["entidade_id"], logout[0]["ip_origem"]),
                         ("tbsss_usuarios", U_OPPROD, IP))
        u = self.usuarios.obter_por_id(U_OPPROD)
        self.assertIsNone(u.get("updated_by"), "logout e rotina tecnica, sem updated_*")

    def test_troca_da_propria_senha_mantem_a_sessao_nova(self):
        self.usuarios.definir_senha(U_OPPROD, security.hash_senha(SENHA_DEV), AGORA, ator="teste")
        epoch = self._epoch(U_OPPROD)
        resultado, erros = self.auth.trocar_senha(self.ctx["op.prod"], IP, SENHA_DEV, SENHA_NOVA, SENHA_NOVA)
        self.assertEqual((resultado, erros), ("OK", {}))
        self.assertEqual(self.auth.sessao_epoch(U_OPPROD), epoch + 1)
        self.assertIsNotNone(self.auth.revalidar(dict(_sessao(U_OPPROD, "op.prod", P_OPPROD), sessao_epoch=epoch + 1)))
        self.assertIsNone(self.auth.revalidar(dict(_sessao(U_OPPROD, "op.prod", P_OPPROD), sessao_epoch=epoch)))

    def test_sessao_sem_epoch_e_encerrada(self):
        sessao = _sessao(U_OPPROD, "op.prod", P_OPPROD)
        del sessao["sessao_epoch"]
        self.assertIsNone(self.auth.revalidar(sessao))

    def test_vida_maxima(self):
        agora = time.time()
        self.assertFalse(security.sessao_expirada(agora - 11 * 3600, agora, 12 * 3600))
        self.assertTrue(security.sessao_expirada(agora - 13 * 3600, agora, 12 * 3600))
        self.assertTrue(security.sessao_expirada(None, agora, 12 * 3600))


class TestRegexQuantificadorLargo(unittest.TestCase):

    def _recusada(self, padrao):
        with self.assertRaises(ParamErro):
            params_compiler.validar_regex_cadastro(padrao)

    def test_largo_conta_como_ilimitado(self):
        self._recusada(r"\w{0,100}\w{0,100}\w{0,100}x")
        self._recusada(r"\w*\w{0,11}\w+x")
        params_compiler.validar_regex_cadastro(r"\w{0,100}\w{0,100}x")
        params_compiler.validar_regex_cadastro(r"^\d{1,11}$")
        params_compiler.validar_regex_cadastro(r"^[A-Z]{2}\d{0,10}$")

    def test_teto_de_escolhas_com_ilimitado(self):
        self._recusada(r"\w*" + r"\d{0,10}" * 4 + "x")
        self._recusada(r"\d?\d?\d?\d?\w*")
        params_compiler.validar_regex_cadastro(r"\w*" + r"\d{0,10}" * 3 + "x")
        params_compiler.validar_regex_cadastro(r"\w{0,10}" * 6 + "x")

    def test_pior_caso_aceito_e_rapido(self):
        for padrao in (r"\w*\w*" + r"\w{0,10}" * 2 + "@", r"\w{0,10}" * 6 + "x", r"\w{0,500}\w{0,500}x"):
            params_compiler.validar_regex_cadastro(padrao)
            inicio = time.time()
            for valor in ("1" * params_compiler.TAMANHO_MAXIMO, "a" * (params_compiler.TAMANHO_MAXIMO - 1) + "!"):
                re.fullmatch(padrao, valor)
            self.assertLess(time.time() - inicio, 1.0, padrao)


if __name__ == "__main__":
    unittest.main()
