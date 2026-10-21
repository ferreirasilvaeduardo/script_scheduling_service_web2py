# -*- coding: utf-8 -*-
"""Testes de admin_perfis_service.py no padrao de CRUD (docs/PADRAO_CRUD_ADMIN.md) e do CR-003 P4.

A matriz e a protecao do ultimo administrador tambem sao cobertas em test_rbac.py.
"""
import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

import admin_crud
import admin_perfis_service as perfis_mod
import auth_service
import repo_factory
import security
from admin_crud import CAMPO_GERAL, AcessoNegado, OperacaoNegada
from admin_perfis_service import ServicoAdminPerfis
from repo_errors import RepoConflito, RepoNaoEncontrado

IP = "10.7.7.7"
SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0},
    "op.prod": {"usuario_id": 2, "login": "op.prod", "perfil_id": 2, "perm_versao": 1, "sessao_epoch": 0},
    "consulta": {"usuario_id": 4, "login": "consulta", "perfil_id": 4, "perm_versao": 1, "sessao_epoch": 0},
}
# Seed FAKE: perfil 1 ADMINISTRADOR (unico admin, usuario admin), 4 CONSULTA (usuario consulta).
PERFIL_ADMIN, PERFIL_CONSULTA = 1, 4


class _Base(unittest.TestCase):

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

        self.rbac_repo = repo_factory.obter("rbac")
        self.usuarios = repo_factory.obter("usuarios")
        self.auditoria = repo_factory.obter("auditoria")
        self.log = logging.getLogger("sss_teste_perfis_service")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        auth = auth_service.ServicoAuth(self.usuarios, self.rbac_repo, repo_factory.obter("catalogo"),
                                        self.auditoria, 5, 900, self.log)
        self.ctx = dict((login, auth.revalidar(sessao)) for login, sessao in SESSOES.items())
        self.ctx["gestor"] = dict(self.ctx["op.prod"], funcionalidades=frozenset(["MANAGE_PROFILES"]))
        self.ctx["admin_externo"] = dict(self.ctx["admin"], profile_id=999)
        self.svc = ServicoAdminPerfis(self.rbac_repo, repo_factory.obter("catalogo"), self.usuarios, self.log)
        self.aud_base = max([a["id"] for a in self.auditoria.listar(pagina=1, tamanho=1000)["itens"]] or [0])

    def _auditorias(self, acao):
        return [a for a in self.auditoria.listar(filtros={"action": acao}, pagina=1, tamanho=100)["itens"]
                if a["entity"] == "tbsss_profiles" and a["id"] > self.aud_base]

    def _form(self, perfil_id, ator="admin"):
        return self.svc.formulario(self.ctx[ator], str(perfil_id))

    def _dados(self, form, **mudancas):
        dados = {"name": form["name"], "description": form["description"], "is_admin": form["is_admin"],
                 "version": form["version"]}
        dados.update(mudancas)
        return dados

    def _novo_admin_com_usuario(self):
        novo_id, erros = self.svc.salvar(self.ctx["admin"], IP, None, {"name": "ADMIN_RESERVA", "is_admin": "Y"})
        self.assertEqual(erros, {})
        u = self.usuarios.obter_por_login("op.hml")
        self.usuarios.alterar(u["id"], {"profile_id": novo_id}, ator="teste")
        return novo_id


class TestCadastro(_Base):

    def test_inclusao_duplicado_e_invalidos(self):
        novo_id, erros = self.svc.salvar(self.ctx["admin"], IP, None, {"name": "OPERADOR_X", "description": "Teste"})
        self.assertEqual(erros, {})
        self.assertEqual(self.rbac_repo.perfis_obter(novo_id)["name"], "OPERADOR_X")
        self.assertEqual(len(self._auditorias("CREATE")), 1)
        _id, erros = self.svc.salvar(self.ctx["admin"], IP, None, {"name": "OPERADOR_X"})
        self.assertEqual(erros, {"name": perfis_mod.MSG_NOME_DUPLICADO})
        _id, erros = self.svc.salvar(self.ctx["admin"], IP, None, {"name": "minusculo"})
        self.assertEqual(erros, {"name": perfis_mod.MSG_NOME_INVALIDO})

    def test_conflito_pela_versao_e_pelo_esperado(self):
        form = self._form(PERFIL_CONSULTA)
        self.rbac_repo.perfis_alterar(PERFIL_CONSULTA, {"description": "mudou por outro"}, ator="teste")
        _id, erros = self.svc.salvar(self.ctx["admin"], IP, str(PERFIL_CONSULTA), self._dados(form, description="minha"))
        self.assertEqual(erros, {CAMPO_GERAL: admin_crud.MSG_CONFLITO})
        form = self._form(PERFIL_CONSULTA)
        original = self.rbac_repo.perfis_alterar

        def corrida(*args, **kwargs):
            self.rbac_repo.perfis_alterar = original
            original(PERFIL_CONSULTA, {"description": "corrida"}, ator="teste")
            return original(*args, **kwargs)
        with mock.patch.object(self.rbac_repo, "perfis_alterar", side_effect=corrida):
            _id, erros = self.svc.salvar(self.ctx["admin"], IP, str(PERFIL_CONSULTA),
                                         self._dados(form, description="minha"))
        self.assertEqual(erros, {CAMPO_GERAL: admin_crud.MSG_CONFLITO})
        self.assertEqual(self.rbac_repo.perfis_obter(PERFIL_CONSULTA)["description"], "corrida")

    def test_sem_funcionalidade_e_inexistente(self):
        with self.assertRaises(AcessoNegado):
            self.svc.formulario(self.ctx["consulta"], str(PERFIL_CONSULTA))
        with self.assertRaises(RepoNaoEncontrado):
            self.svc.formulario(self.ctx["admin"], "999")


class TestDesativacaoComImpacto(_Base):

    def test_formulario_lista_os_usuarios_afetados(self):
        # CR-003 P4: o modal mostra os logins (README §4.3.B.1).
        form = self._form(PERFIL_CONSULTA)
        self.assertEqual(form["usuarios_ativos"], 1)
        self.assertEqual(form["usuarios_afetados"], ["consulta"])
        self.assertFalse(form["proprio"])
        self.assertTrue(self._form(PERFIL_ADMIN)["proprio"])

    def test_lista_limitada_a_vinte_logins(self):
        for i in range(perfis_mod.AFETADOS_MAX + 3):
            self.usuarios.inserir({"login": "usr.%02d" % i, "name": "U %d" % i, "password_hash": "x",
                                   "profile_id": PERFIL_CONSULTA, "active": "Y"}, ator="teste")
        form = self._form(PERFIL_CONSULTA)
        self.assertEqual(form["usuarios_ativos"], perfis_mod.AFETADOS_MAX + 4)
        self.assertEqual(len(form["usuarios_afetados"]), perfis_mod.AFETADOS_MAX)

    def test_desativacao_audita_impacto(self):
        form = self._form(PERFIL_CONSULTA)
        alterado = self.svc.alternar_ativo(self.ctx["admin"], IP, str(PERFIL_CONSULTA), form["version"])
        self.assertEqual(alterado["active"], "N")
        aud = self._auditorias("DEACTIVATE")
        self.assertEqual(len(aud), 1)
        self.assertIn(u"usuários ativos afetados: 1", aud[0]["detail"])


class TestAutoprotecao(_Base):
    """CR-003 P4 / D10: o usuario logado nao tira o is_admin nem desativa o proprio perfil."""

    def test_nao_remove_is_admin_do_proprio_perfil_mesmo_com_outro_admin(self):
        self._novo_admin_com_usuario()
        form = self._form(PERFIL_ADMIN)
        _id, erros = self.svc.salvar(self.ctx["admin"], IP, str(PERFIL_ADMIN), self._dados(form, is_admin=None))
        self.assertEqual(erros, {CAMPO_GERAL: perfis_mod.MSG_AUTO_ADMIN})
        self.assertEqual(self.rbac_repo.perfis_obter(PERFIL_ADMIN)["is_admin"], "Y")
        self.assertEqual(self._auditorias("UPDATE"), [])

    def test_nao_desativa_o_proprio_perfil_mesmo_com_outro_admin(self):
        self._novo_admin_com_usuario()
        form = self._form(PERFIL_ADMIN)
        with self.assertRaises(OperacaoNegada) as cm:
            self.svc.alternar_ativo(self.ctx["admin"], IP, str(PERFIL_ADMIN), form["version"])
        self.assertEqual(cm.exception.mensagem, perfis_mod.MSG_AUTO_DESATIVAR)
        self.assertEqual(self.rbac_repo.perfis_obter(PERFIL_ADMIN)["active"], "Y")
        self.assertEqual(self._auditorias("DEACTIVATE"), [])

    def test_outro_editor_pode_quando_ha_outro_admin(self):
        self._novo_admin_com_usuario()
        form = self._form(PERFIL_ADMIN)
        _id, erros = self.svc.salvar(self.ctx["admin_externo"], IP, str(PERFIL_ADMIN), self._dados(form, is_admin=None))
        self.assertEqual(erros, {})
        self.assertEqual(self.rbac_repo.perfis_obter(PERFIL_ADMIN)["is_admin"], "N")

    def test_editar_o_proprio_perfil_sem_tirar_admin_e_permitido(self):
        form = self._form(PERFIL_ADMIN)
        _id, erros = self.svc.salvar(self.ctx["admin"], IP, str(PERFIL_ADMIN), self._dados(form, description="Nova"))
        self.assertEqual(erros, {})
        self.assertEqual(self.rbac_repo.perfis_obter(PERFIL_ADMIN)["description"], "Nova")



class TestQuemPode(_Base):
    """CR-004 U8 (README §4.3.B.2)."""

    def _nomes(self, lista):
        return dict((p["name"], p) for p in lista)

    def test_por_script_bate_com_pode_executar(self):
        import rbac
        q = self.svc.quem_pode(self.ctx["admin"], script_id="1")
        perfis = self._nomes(q["perfis"])
        self.assertEqual(perfis["ADMINISTRATOR"]["reason"], u"administrador")
        # Cada perfil listado tem um usuario cujo contexto pode_executar no ambiente indicado.
        catalogo = self.svc._catalogo
        script = catalogo.scripts_obter(1)
        ambs = dict((a["name"], a) for a in catalogo.ambientes_listar(pagina=1, tamanho=50)["itens"])
        hom = catalogo.homologacao_obter(1)
        for login in ("op.prod", "consulta"):
            ctx = self.ctx[login]
            podem = set(n for n, a in ambs.items() if rbac.pode_executar(ctx, script, a, hom)[0])
            nome = self.rbac_repo.perfis_obter(ctx["profile_id"])["name"]
            self.assertEqual(set(perfis[nome]["detalhes"]) if nome in perfis else set(), podem, login)

    def test_por_ambiente_e_inativos(self):
        self.rbac_repo.perfis_alterar(PERFIL_CONSULTA, {"is_admin": "Y"}, ator="teste")
        self.rbac_repo.perfis_alterar(PERFIL_CONSULTA, {"active": "N"}, ator="teste")
        amb = [a for a in self.svc._catalogo.ambientes_listar(pagina=1, tamanho=50)["itens"]
               if a["name"] == "HOMOLOGACAO"][0]
        q = self.svc.quem_pode(self.ctx["admin"], ambiente_id=str(amb["id"]))
        self.assertIn("READ_ONLY", self._nomes(q["inativos"]))
        self.assertNotIn("READ_ONLY", self._nomes(q["perfis"]))
        self.assertTrue(self._nomes(q["perfis"])["ADMINISTRATOR"]["detalhes"])

    def test_script_inativo_avisa_e_acesso(self):
        self.svc._catalogo.scripts_alterar(5, {"active": "N"}, ator="teste")
        self.assertIn(u"inativo", self.svc.quem_pode(self.ctx["admin"], script_id="5")["aviso"])
        with self.assertRaises(RepoNaoEncontrado):
            self.svc.quem_pode(self.ctx["admin"], script_id="999")
        with self.assertRaises(AcessoNegado):
            self.svc.quem_pode(self.ctx["consulta"], script_id="1")
        vazio = self.svc.quem_pode(self.ctx["admin"])
        self.assertIsNone(vazio["script"])
        self.assertTrue(vazio["scripts"])


if __name__ == "__main__":
    unittest.main()
