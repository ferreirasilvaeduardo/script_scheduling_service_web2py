# -*- coding: utf-8 -*-
"""Testes de admin_ambientes_service.py e admin_crud.py (F4.1) sobre o backend FAKE."""
import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

import admin_ambientes_service as svc_mod
import admin_crud
import auth_service
import masking
import repo_factory
import security
from admin_ambientes_service import ServicoAdminAmbientes
from admin_crud import CAMPO_GERAL, AcessoNegado
from repo_errors import RepoConflito, RepoNaoEncontrado

IP = "10.9.8.7"
SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0},
    "op.prod": {"usuario_id": 2, "login": "op.prod", "perfil_id": 2, "perm_versao": 1, "sessao_epoch": 0},
}
# Seed FAKE: PRODUCAO (id 1) com os agendamentos 1 e 3 ativos e o 5 inativo; HOMOLOGACAO (id 2).
AMB_PRODUCAO, AMB_HOMOLOGACAO = 1, 2
SETA = u" → "


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

        self.catalogo = repo_factory.obter("catalogo")
        self.auditoria = repo_factory.obter("auditoria")
        self.log = logging.getLogger("sss_teste_admin_amb")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        auth = auth_service.ServicoAuth(
            repo_factory.obter("usuarios"), repo_factory.obter("rbac"), self.catalogo, self.auditoria,
            5, 900, self.log)
        self.ctx = dict((login, auth.revalidar(sessao)) for login, sessao in SESSOES.items())
        self.svc = ServicoAdminAmbientes(self.catalogo, repo_factory.obter("agendamentos"), self.log)
        # O seed ja tem auditorias de ambientes: so contam as gravadas pelo teste.
        self.aud_base = max([a["id"] for a in self.auditoria.listar(pagina=1, tamanho=1000)["itens"]] or [0])

    def _auditorias(self, acao):
        return [a for a in self.auditoria.listar(filtros={"acao": acao}, pagina=1, tamanho=100)["itens"]
                if a["entidade"] == "tbsss_ambientes" and a["id"] > self.aud_base]

    def _incluir(self, nome="QA_01", descricao="Ambiente de QA", conexao="db-qa.local:1521/svc"):
        return self.svc.salvar(self.ctx["admin"], IP, None,
                               {"nome": nome, "descricao": descricao, "conexao": conexao})


class TestInclusao(_Base):

    def test_identificador_com_espacos_e_descricao_com_controle_recusados(self):
        # CR-003 C2 (README §10): identificador nao recebe strip; texto livre recusa controle.
        _id, erros = self._incluir(nome=" QA_02 ")
        self.assertEqual(erros, {"nome": admin_crud.MSG_ESPACOS})
        _id, erros = self._incluir(nome="QA_02", descricao="linha 1\nlinha 2")
        self.assertEqual(erros, {"descricao": admin_crud.MSG_CONTROLE})

    def test_auditoria_de_inclusao_omite_campos_vazios(self):
        # CR-003 P6 (README §4.4): so os campos preenchidos.
        _id, erros = self._incluir(nome="QA_03", descricao="", conexao="")
        self.assertEqual(erros, {})
        self.assertEqual(self._auditorias("CAD_INSERIR")[0]["detalhe"], "nome: QA_03")

    def test_inclusao_com_auditoria(self):
        aid, erros = self._incluir()
        self.assertEqual(erros, {})
        amb = self.catalogo.ambientes_obter(aid)
        self.assertEqual((amb["nome"], amb["descricao"], amb["conexao"], amb["ativo"]),
                         ("QA_01", "Ambiente de QA", "db-qa.local:1521/svc", "S"))
        aud = self._auditorias("CAD_INSERIR")
        self.assertEqual(len(aud), 1)
        self.assertEqual((aud[0]["ator"], aud[0]["ip_origem"], aud[0]["entidade_id"]), ("admin", IP, aid))
        self.assertIn("nome: QA_01", aud[0]["detalhe"])
        self.assertIn("conexao: db-qa.local:1521/svc", aud[0]["detalhe"])

    def test_inclusao_com_alias_tns_e_campos_opcionais_vazios(self):
        aid, erros = self._incluir(nome="TNS_X", descricao="  ", conexao="PRODDB_ALIAS")
        self.assertEqual(erros, {})
        self.assertEqual(self.catalogo.ambientes_obter(aid)["conexao"], "PRODDB_ALIAS")
        aid2, erros2 = self._incluir(nome="SEM_DSN", descricao="", conexao="")
        self.assertEqual(erros2, {})
        self.assertIsNone(self.catalogo.ambientes_obter(aid2)["conexao"])

    def test_nome_duplicado(self):
        aid, erros = self._incluir(nome="PRODUCAO")
        self.assertIsNone(aid)
        self.assertEqual(erros, {"nome": svc_mod.MSG_NOME_DUPLICADO})
        self.assertEqual(self._auditorias("CAD_INSERIR"), [])

    def test_nome_invalido(self):
        for nome in ("producao", "PROD-1", "PROD 1", "A" * 31, u"PRODUÇÃO"):
            aid, erros = self._incluir(nome=nome)
            self.assertIsNone(aid, nome)
            self.assertEqual(erros, {"nome": svc_mod.MSG_NOME_INVALIDO}, nome)
        aid, erros = self._incluir(nome="")
        self.assertEqual(erros, {"nome": svc_mod.MSG_NOME_OBRIGATORIO})
        self.assertEqual(self.catalogo.ambientes_listar(pagina=1, tamanho=100)["total"], 3)

    def test_dsn_com_credencial_rejeitado(self):
        for dsn in ("usuario/senha@host", "app/s3cr3t@db01:1521/svc", "@db"):
            aid, erros = self._incluir(conexao=dsn)
            self.assertIsNone(aid)
            self.assertEqual(erros, {"conexao": svc_mod.MSG_CONEXAO_CREDENCIAL})
        self.assertEqual(self._auditorias("CAD_INSERIR"), [])

    def test_dsn_e_descricao_invalidos(self):
        _aid, erros = self._incluir(conexao="host:porta/svc")
        self.assertEqual(erros, {"conexao": svc_mod.MSG_CONEXAO_INVALIDA})
        _aid, erros = self._incluir(conexao="a" * 251)
        self.assertEqual(erros, {"conexao": svc_mod.MSG_CONEXAO_TAMANHO})
        _aid, erros = self._incluir(descricao="d" * 101)
        self.assertEqual(erros, {"descricao": svc_mod.MSG_DESCRICAO_TAMANHO})

    def test_validar_conexao(self):
        for ok in (None, "db01.local:1521/svc", "localhost:2424/servico_homolog", "ALIAS_TNS", "a.b-c_d"):
            self.assertIsNone(svc_mod.validar_conexao(ok), ok)
        for ruim in ("db01:1521", "db01:123456/svc", "db 01:1521/svc", "(DESCRIPTION=(ADDRESS=...))"):
            self.assertEqual(svc_mod.validar_conexao(ruim), svc_mod.MSG_CONEXAO_INVALIDA, ruim)


class TestEdicao(_Base):

    def _form(self, aid=AMB_HOMOLOGACAO):
        return self.svc.formulario(self.ctx["admin"], str(aid))

    def _salvar(self, form, **mudancas):
        dados = {"nome": form["nome"], "descricao": form["descricao"], "conexao": form["conexao"],
                 "versao": form["versao"]}
        dados.update(mudancas)
        return self.svc.salvar(self.ctx["admin"], IP, str(form["id"]), dados)

    def test_alteracao_auditada_campo_antigo_novo(self):
        form = self._form()
        antigo = form["conexao"]
        _id, erros = self._salvar(form, descricao="Nova descricao", conexao="db-hml2.local:1521/svc")
        self.assertEqual(erros, {})
        amb = self.catalogo.ambientes_obter(AMB_HOMOLOGACAO)
        self.assertEqual((amb["descricao"], amb["conexao"]), ("Nova descricao", "db-hml2.local:1521/svc"))
        aud = self._auditorias("CAD_ALTERAR")
        self.assertEqual(len(aud), 1)
        self.assertIn(u"conexao: %s%sdb-hml2.local:1521/svc" % (antigo, SETA), aud[0]["detalhe"])
        self.assertIn(u"descricao: ", aud[0]["detalhe"])
        self.assertEqual(aud[0]["entidade_id"], AMB_HOMOLOGACAO)

    def test_tentativa_de_alterar_nome_e_ignorada(self):
        form = self._form()
        _id, erros = self._salvar(form, nome="OUTRO_NOME", descricao="x")
        self.assertEqual(erros, {})
        self.assertEqual(self.catalogo.ambientes_obter(AMB_HOMOLOGACAO)["nome"], "HOMOLOGACAO")
        self.assertNotIn("nome", self._auditorias("CAD_ALTERAR")[0]["detalhe"])

    def test_sem_mudanca_nao_audita(self):
        _id, erros = self._salvar(self._form())
        self.assertEqual(erros, {})
        self.assertEqual(self._auditorias("CAD_ALTERAR"), [])

    def test_edicao_concorrente_gera_conflito(self):
        aba1 = self._form()
        aba2 = self._form()
        self.assertEqual(self._salvar(aba2, descricao="Salva pela aba 2")[1], {})
        _id, erros = self._salvar(aba1, descricao="Salva pela aba 1")
        self.assertEqual(erros, {CAMPO_GERAL: admin_crud.MSG_CONFLITO})
        self.assertEqual(self.catalogo.ambientes_obter(AMB_HOMOLOGACAO)["descricao"], "Salva pela aba 2")
        self.assertEqual(len(self._auditorias("CAD_ALTERAR")), 1)

    def test_conflito_entre_leitura_e_escrita_e_detectado_pelo_repositorio(self):
        form = self._form()
        original = self.catalogo.ambientes_obter

        def obter_e_concorrer(aid):
            lido = original(aid)
            # Outra sessao grava depois da leitura do service e antes do UPDATE condicional.
            self.catalogo.ambientes_alterar(aid, {"descricao": "Concorrente"}, ator="teste")
            return lido

        with mock.patch.object(self.catalogo, "ambientes_obter", side_effect=obter_e_concorrer):
            _id, erros = self._salvar(form, descricao="Minha")
        self.assertEqual(erros, {CAMPO_GERAL: admin_crud.MSG_CONFLITO})
        self.assertEqual(self.catalogo.ambientes_obter(AMB_HOMOLOGACAO)["descricao"], "Concorrente")
        self.assertEqual(self._auditorias("CAD_ALTERAR"), [])

    def test_versao_ausente_ou_adulterada_gera_conflito(self):
        for versao in (None, "", "0" * 64):
            _id, erros = self._salvar(self._form(), versao=versao, descricao="x")
            self.assertEqual(erros, {CAMPO_GERAL: admin_crud.MSG_CONFLITO})

    def test_dsn_com_credencial_na_edicao(self):
        _id, erros = self._salvar(self._form(), conexao="app/senha@db:1521/svc")
        self.assertEqual(erros, {"conexao": svc_mod.MSG_CONEXAO_CREDENCIAL})
        self.assertNotIn("@", self.catalogo.ambientes_obter(AMB_HOMOLOGACAO)["conexao"])

    def test_id_inexistente_ou_invalido(self):
        for aid in ("999", "abc", "0", "-1"):
            with self.assertRaises(RepoNaoEncontrado):
                self.svc.formulario(self.ctx["admin"], aid)
            with self.assertRaises(RepoNaoEncontrado):
                self.svc.salvar(self.ctx["admin"], IP, aid, {"versao": "x"})


class TestDesativacao(_Base):

    def test_formulario_mostra_agendamentos_ativos(self):
        self.assertEqual(self.svc.formulario(self.ctx["admin"], str(AMB_PRODUCAO))["agendamentos_ativos"], 2)

    def test_desativacao_com_contagem_e_reativacao(self):
        form = self.svc.formulario(self.ctx["admin"], str(AMB_PRODUCAO))
        alterado = self.svc.alternar_ativo(self.ctx["admin"], IP, str(AMB_PRODUCAO), form["versao"])
        self.assertEqual(alterado["ativo"], "N")
        aud = self._auditorias("CAD_DESATIVAR")
        self.assertEqual(len(aud), 1)
        # CR-003 C6: o impacto tambem conta os scripts homologados no ambiente.
        self.assertEqual(aud[0]["detalhe"],
                         u"ativo: S%sN; agendamentos ativos afetados: 2; scripts homologados afetados: 4" % SETA)

        form = self.svc.formulario(self.ctx["admin"], str(AMB_PRODUCAO))
        self.assertEqual(self.svc.alternar_ativo(self.ctx["admin"], IP, str(AMB_PRODUCAO), form["versao"])["ativo"], "S")
        aud = self._auditorias("CAD_ALTERAR")
        self.assertEqual(aud[0]["detalhe"], u"ativo: N%sS" % SETA)

    def test_alternar_com_versao_antiga_gera_conflito(self):
        form = self.svc.formulario(self.ctx["admin"], str(AMB_PRODUCAO))
        self.svc.alternar_ativo(self.ctx["admin"], IP, str(AMB_PRODUCAO), form["versao"])
        with self.assertRaises(RepoConflito):
            self.svc.alternar_ativo(self.ctx["admin"], IP, str(AMB_PRODUCAO), form["versao"])
        self.assertEqual(self.catalogo.ambientes_obter(AMB_PRODUCAO)["ativo"], "N")


class TestAcessoEAuditoria(_Base):

    def test_perfil_sem_cad_ambientes(self):
        ctx = self.ctx["op.prod"]
        with self.assertRaises(AcessoNegado):
            self.svc.listar(ctx, {}, 1, 20)
        with self.assertRaises(AcessoNegado):
            self.svc.formulario(ctx)
        with self.assertRaises(AcessoNegado):
            self.svc.salvar(ctx, IP, None, {"nome": "X"})
        with self.assertRaises(AcessoNegado):
            self.svc.alternar_ativo(ctx, IP, "1", "v")

    def test_detalhe_mascara_credencial_e_limita_tamanho(self):
        segredo = "segredo-registrado-xyz"
        with mock.patch.object(masking, "MASCARADOR", masking.Mascarador()):
            masking.MASCARADOR.registrar(segredo)
            detalhe = admin_crud.detalhe_alteracoes({"descricao": "a"}, {"descricao": "usa " + segredo},
                                                    ("descricao",))
            self.assertNotIn(segredo, detalhe)
            self.assertIn(masking.MASCARA, detalhe)
            detalhe = admin_crud.detalhe_alteracoes({"conexao": None}, {"conexao": "app/senha@db"}, ("conexao",))
            self.assertNotIn("senha", detalhe)
        longo = admin_crud.detalhe_alteracoes({"descricao": "a"}, {"descricao": "b" * 2000}, ("descricao",))
        self.assertEqual(len(longo), admin_crud.LIMITE_DETALHE)
        self.assertIsNone(admin_crud.detalhe_alteracoes({"descricao": ""}, {"descricao": None}, ("descricao",)))

    def test_versao_estavel_e_sensivel_aos_campos(self):
        reg = {"descricao": "x", "conexao": None, "ativo": "S"}
        campos = svc_mod.CAMPOS_EDITAVEIS
        self.assertEqual(admin_crud.versao(reg, campos), admin_crud.versao(dict(reg, conexao=""), campos))
        self.assertNotEqual(admin_crud.versao(reg, campos), admin_crud.versao(dict(reg, ativo="N"), campos))

    def test_listar_e_filtros(self):
        self.assertEqual(svc_mod.normalizar_filtros({"nome": "prod", "ativo": "S"}), {"nome": "prod", "ativo": "S"})
        self.assertEqual(svc_mod.normalizar_filtros({"nome": "<x>", "ativo": "Z"}), {})
        pagina = self.svc.listar(self.ctx["admin"], {"ativo": "N"}, 1, 20)
        self.assertEqual([a["nome"] for a in pagina["itens"]], ["DESENV"])


if __name__ == "__main__":
    unittest.main()
