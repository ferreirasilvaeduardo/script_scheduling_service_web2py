# -*- coding: utf-8 -*-
"""Testes de admin_environments_service.py e admin_crud.py (F4.1) sobre o backend FAKE."""
import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

import admin_environments_service as svc_mod
import admin_crud
import auth_service
import masking
import repo_factory
import security
from admin_environments_service import AdminEnvironmentsService
from admin_crud import GENERAL_FIELD, AccessDenied
from repo_errors import RepoConflict, RepoNotFound

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
        patcher = mock.patch.object(security, "ITERATIONS", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_DEV_PASSWORD: "senha-dev-de-teste-123"})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configure, None)

        self.catalog = repo_factory.get("catalog")
        self.audit = repo_factory.get("audit")
        self.log = logging.getLogger("sss_teste_admin_amb")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        auth = auth_service.AuthService(
            repo_factory.get("users"), repo_factory.get("rbac"), self.catalog, self.audit,
            5, 900, self.log)
        self.ctx = dict((login, auth.revalidate(sessao)) for login, sessao in SESSOES.items())
        self.svc = AdminEnvironmentsService(self.catalog, repo_factory.get("schedules"), self.log)
        # O seed ja tem auditorias de environments: so contam as gravadas pelo teste.
        self.aud_base = max([a["id"] for a in self.audit.list(pagina=1, tamanho=1000)["itens"]] or [0])

    def _auditorias(self, acao):
        return [a for a in self.audit.list(filtros={"action": acao}, pagina=1, tamanho=100)["itens"]
                if a["entity"] == "tbsss_environments" and a["id"] > self.aud_base]

    def _insert(self, name="QA_01", description="Ambiente de QA", connection="db-qa.local:1521/svc"):
        return self.svc.save(self.ctx["admin"], IP, None,
                               {"name": name, "description": description, "connection": connection})


class TestInclusao(_Base):

    def test_identificador_com_espacos_e_descricao_com_controle_recusados(self):
        # CR-003 C2 (README §10): identificador nao recebe strip; texto livre recusa controle.
        _id, erros = self._insert(name=" QA_02 ")
        self.assertEqual(erros, {"name": admin_crud.MSG_SPACES})
        _id, erros = self._insert(name="QA_02", description="linha 1\nlinha 2")
        self.assertEqual(erros, {"description": admin_crud.MSG_CONTROL_CHARS})

    def test_auditoria_de_inclusao_omite_campos_vazios(self):
        # CR-003 P6 (README §4.4): so os campos preenchidos.
        _id, erros = self._insert(name="QA_03", description="", connection="")
        self.assertEqual(erros, {})
        self.assertEqual(self._auditorias("CREATE")[0]["detail"], "name: QA_03")

    def test_inclusao_com_auditoria(self):
        aid, erros = self._insert()
        self.assertEqual(erros, {})
        amb = self.catalog.environments_get(aid)
        self.assertEqual((amb["name"], amb["description"], amb["connection"], amb["active"]),
                         ("QA_01", "Ambiente de QA", "db-qa.local:1521/svc", "Y"))
        aud = self._auditorias("CREATE")
        self.assertEqual(len(aud), 1)
        self.assertEqual((aud[0]["actor"], aud[0]["source_ip"], aud[0]["entity_id"]), ("admin", IP, aid))
        self.assertIn("name: QA_01", aud[0]["detail"])
        self.assertIn("connection: db-qa.local:1521/svc", aud[0]["detail"])

    def test_inclusao_com_alias_tns_e_campos_opcionais_vazios(self):
        aid, erros = self._insert(name="TNS_X", description="  ", connection="PRODDB_ALIAS")
        self.assertEqual(erros, {})
        self.assertEqual(self.catalog.environments_get(aid)["connection"], "PRODDB_ALIAS")
        aid2, erros2 = self._insert(name="SEM_DSN", description="", connection="")
        self.assertEqual(erros2, {})
        self.assertIsNone(self.catalog.environments_get(aid2)["connection"])

    def test_nome_duplicado(self):
        aid, erros = self._insert(name="PRODUCAO")
        self.assertIsNone(aid)
        self.assertEqual(erros, {"name": svc_mod.MSG_NAME_DUPLICATE})
        self.assertEqual(self._auditorias("CREATE"), [])

    def test_nome_interno_reservado(self):
        # CR-009: 'internal' e a pasta de log sem ambiente (logs da aplicacao).
        aid, erros = self._insert(name="INTERNAL")
        self.assertIsNone(aid)
        self.assertEqual(erros, {"name": svc_mod.MSG_NAME_RESERVED})
        self.assertEqual(self._auditorias("CREATE"), [])
        aid, erros = self._insert(name="INTERNAL_2")
        self.assertEqual(erros, {})
        self.assertIsNotNone(aid)

    def test_nome_invalido(self):
        for nome in ("producao", "PROD-1", "PROD 1", "A" * 31, u"PRODUÇÃO"):
            aid, erros = self._insert(name=nome)
            self.assertIsNone(aid, nome)
            self.assertEqual(erros, {"name": svc_mod.MSG_NAME_INVALID}, nome)
        aid, erros = self._insert(name="")
        self.assertEqual(erros, {"name": svc_mod.MSG_NAME_REQUIRED})
        self.assertEqual(self.catalog.environments_list(pagina=1, tamanho=100)["total"], 8)

    def test_dsn_com_credencial_rejeitado(self):
        for dsn in ("usuario/senha@host", "app/s3cr3t@db01:1521/svc", "@db"):
            aid, erros = self._insert(connection=dsn)
            self.assertIsNone(aid)
            self.assertEqual(erros, {"connection": svc_mod.MSG_CONNECTION_CREDENTIAL})
        self.assertEqual(self._auditorias("CREATE"), [])

    def test_dsn_e_descricao_invalidos(self):
        _aid, erros = self._insert(connection="host:porta/svc")
        self.assertEqual(erros, {"connection": svc_mod.MSG_CONNECTION_INVALID})
        _aid, erros = self._insert(connection="a" * 251)
        self.assertEqual(erros, {"connection": svc_mod.MSG_CONNECTION_LENGTH})
        _aid, erros = self._insert(description="d" * 101)
        self.assertEqual(erros, {"description": svc_mod.MSG_DESCRIPTION_LENGTH})

    def test_validar_conexao(self):
        for ok in (None, "db01.local:1521/svc", "localhost:2424/servico_homolog", "ALIAS_TNS", "a.b-c_d"):
            self.assertIsNone(svc_mod.validate_connection(ok), ok)
        for ruim in ("db01:1521", "db01:123456/svc", "db 01:1521/svc", "(DESCRIPTION=(ADDRESS=...))"):
            self.assertEqual(svc_mod.validate_connection(ruim), svc_mod.MSG_CONNECTION_INVALID, ruim)


class TestEdicao(_Base):

    def _form(self, aid=AMB_HOMOLOGACAO):
        return self.svc.form(self.ctx["admin"], str(aid))

    def _salvar(self, form, **mudancas):
        dados = {"name": form["name"], "description": form["description"], "connection": form["connection"],
                 "version": form["version"]}
        dados.update(mudancas)
        return self.svc.save(self.ctx["admin"], IP, str(form["id"]), dados)

    def test_alteracao_auditada_campo_antigo_novo(self):
        form = self._form()
        antigo = form["connection"]
        _id, erros = self._salvar(form, description="Nova descricao", connection="db-hml2.local:1521/svc")
        self.assertEqual(erros, {})
        amb = self.catalog.environments_get(AMB_HOMOLOGACAO)
        self.assertEqual((amb["description"], amb["connection"]), ("Nova descricao", "db-hml2.local:1521/svc"))
        aud = self._auditorias("UPDATE")
        self.assertEqual(len(aud), 1)
        self.assertIn(u"connection: %s%sdb-hml2.local:1521/svc" % (antigo, SETA), aud[0]["detail"])
        self.assertIn(u"description: ", aud[0]["detail"])
        self.assertEqual(aud[0]["entity_id"], AMB_HOMOLOGACAO)

    def test_tentativa_de_alterar_nome_e_ignorada(self):
        form = self._form()
        _id, erros = self._salvar(form, name="OUTRO_NOME", description="x")
        self.assertEqual(erros, {})
        self.assertEqual(self.catalog.environments_get(AMB_HOMOLOGACAO)["name"], "HOMOLOGACAO")
        self.assertNotIn("name", self._auditorias("UPDATE")[0]["detail"])

    def test_sem_mudanca_nao_audita(self):
        _id, erros = self._salvar(self._form())
        self.assertEqual(erros, {})
        self.assertEqual(self._auditorias("UPDATE"), [])

    def test_edicao_concorrente_gera_conflito(self):
        aba1 = self._form()
        aba2 = self._form()
        self.assertEqual(self._salvar(aba2, description="Salva pela aba 2")[1], {})
        _id, erros = self._salvar(aba1, description="Salva pela aba 1")
        self.assertEqual(erros, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})
        self.assertEqual(self.catalog.environments_get(AMB_HOMOLOGACAO)["description"], "Salva pela aba 2")
        self.assertEqual(len(self._auditorias("UPDATE")), 1)

    def test_conflito_entre_leitura_e_escrita_e_detectado_pelo_repositorio(self):
        form = self._form()
        original = self.catalog.environments_get

        def obter_e_concorrer(aid):
            lido = original(aid)
            # Outra sessao grava depois da leitura do service e antes do UPDATE condicional.
            self.catalog.environments_update(aid, {"description": "Concorrente"}, ator="teste")
            return lido

        with mock.patch.object(self.catalog, "environments_get", side_effect=obter_e_concorrer):
            _id, erros = self._salvar(form, description="Minha")
        self.assertEqual(erros, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})
        self.assertEqual(self.catalog.environments_get(AMB_HOMOLOGACAO)["description"], "Concorrente")
        self.assertEqual(self._auditorias("UPDATE"), [])

    def test_versao_ausente_ou_adulterada_gera_conflito(self):
        for versao in (None, "", "0" * 64):
            _id, erros = self._salvar(self._form(), version=versao, description="x")
            self.assertEqual(erros, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})

    def test_dsn_com_credencial_na_edicao(self):
        _id, erros = self._salvar(self._form(), connection="app/senha@db:1521/svc")
        self.assertEqual(erros, {"connection": svc_mod.MSG_CONNECTION_CREDENTIAL})
        self.assertNotIn("@", self.catalog.environments_get(AMB_HOMOLOGACAO)["connection"])

    def test_id_inexistente_ou_invalido(self):
        for aid in ("999", "abc", "0", "-1"):
            with self.assertRaises(RepoNotFound):
                self.svc.form(self.ctx["admin"], aid)
            with self.assertRaises(RepoNotFound):
                self.svc.save(self.ctx["admin"], IP, aid, {"version": "x"})


class TestDesativacao(_Base):

    def test_formulario_mostra_agendamentos_ativos(self):
        self.assertEqual(self.svc.form(self.ctx["admin"], str(AMB_PRODUCAO))["agendamentos_ativos"], 2)

    def test_desativacao_com_contagem_e_reativacao(self):
        form = self.svc.form(self.ctx["admin"], str(AMB_PRODUCAO))
        alterado = self.svc.toggle_active(self.ctx["admin"], IP, str(AMB_PRODUCAO), form["version"])
        self.assertEqual(alterado["active"], "N")
        aud = self._auditorias("DEACTIVATE")
        self.assertEqual(len(aud), 1)
        # CR-003 C6: o impacto tambem conta os scripts homologados no ambiente.
        self.assertEqual(aud[0]["detail"],
                         u"active: Y%sN; agendamentos ativos afetados: 2; scripts homologados afetados: 4" % SETA)

        form = self.svc.form(self.ctx["admin"], str(AMB_PRODUCAO))
        self.assertEqual(self.svc.toggle_active(self.ctx["admin"], IP, str(AMB_PRODUCAO), form["version"])["active"], "Y")
        aud = self._auditorias("UPDATE")
        self.assertEqual(aud[0]["detail"], u"active: N%sY" % SETA)

    def test_alternar_com_versao_antiga_gera_conflito(self):
        form = self.svc.form(self.ctx["admin"], str(AMB_PRODUCAO))
        self.svc.toggle_active(self.ctx["admin"], IP, str(AMB_PRODUCAO), form["version"])
        with self.assertRaises(RepoConflict):
            self.svc.toggle_active(self.ctx["admin"], IP, str(AMB_PRODUCAO), form["version"])
        self.assertEqual(self.catalog.environments_get(AMB_PRODUCAO)["active"], "N")


class TestAcessoEAuditoria(_Base):

    def test_perfil_sem_cad_ambientes(self):
        ctx = self.ctx["op.prod"]
        with self.assertRaises(AccessDenied):
            self.svc.list(ctx, {}, 1, 20)
        with self.assertRaises(AccessDenied):
            self.svc.form(ctx)
        with self.assertRaises(AccessDenied):
            self.svc.save(ctx, IP, None, {"name": "X"})
        with self.assertRaises(AccessDenied):
            self.svc.toggle_active(ctx, IP, "1", "v")

    def test_detalhe_mascara_credencial_e_limita_tamanho(self):
        segredo = "segredo-registrado-xyz"
        with mock.patch.object(masking, "MASKER", masking.Masker()):
            masking.MASKER.register(segredo)
            detalhe = admin_crud.changes_detail({"description": "a"}, {"description": "usa " + segredo},
                                                    ("description",))
            self.assertNotIn(segredo, detalhe)
            self.assertIn(masking.MASK, detalhe)
            detalhe = admin_crud.changes_detail({"connection": None}, {"connection": "app/senha@db"}, ("connection",))
            self.assertNotIn("senha", detalhe)
        longo = admin_crud.changes_detail({"description": "a"}, {"description": "b" * 2000}, ("description",))
        self.assertEqual(len(longo), admin_crud.DETAIL_LIMIT)
        self.assertIsNone(admin_crud.changes_detail({"description": ""}, {"description": None}, ("description",)))

    def test_versao_estavel_e_sensivel_aos_campos(self):
        reg = {"description": "x", "connection": None, "active": "Y"}
        campos = svc_mod.EDITABLE_FIELDS
        self.assertEqual(admin_crud.version(reg, campos), admin_crud.version(dict(reg, connection=""), campos))
        self.assertNotEqual(admin_crud.version(reg, campos), admin_crud.version(dict(reg, active="N"), campos))

    def test_listar_e_filtros(self):
        self.assertEqual(svc_mod.normalize_filters({"name": "prod", "active": "Y"}), {"name": "prod", "active": "Y"})
        self.assertEqual(svc_mod.normalize_filters({"name": "<x>", "active": "Z"}), {})
        pagina = self.svc.list(self.ctx["admin"], {"active": "N"}, 1, 20)
        self.assertEqual([a["name"] for a in pagina["itens"]], ["DESENV"])


if __name__ == "__main__":
    unittest.main()
