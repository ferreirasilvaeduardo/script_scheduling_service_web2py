# -*- coding: utf-8 -*-
"""Testes de admin_parametros_service.py (F4.4) sobre o backend FAKE."""
import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

import admin_crud
import admin_parametros_service as prm_mod
import auth_service
import repo_factory
import security
from admin_crud import CAMPO_GERAL, AcessoNegado, OperacaoNegada
from admin_parametros_service import ServicoAdminParametros
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao

IP = "10.3.3.3"
SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1},
    "op.prod": {"usuario_id": 2, "login": "op.prod", "perfil_id": 2, "perm_versao": 1},
}
# Seed FAKE: 1 data_ref (DATE, carga_diaria NOMEADO e relatorio_mensal SEQUENCIAL), 5 codigo_filial
# (TEXT com regex ^[0-9]{4}$, validacao_fiscal), 6 chave_api (TEXT sensivel), 10 descricao_lote (TEXT).
P_DATA_REF, P_FILIAL, P_CHAVE_API, P_DESCRICAO_LOTE = 1, 5, 6, 10


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
        self.log = logging.getLogger("sss_teste_parametros")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        auth = auth_service.ServicoAuth(repo_factory.obter("usuarios"), repo_factory.obter("rbac"), self.catalogo,
                                        self.auditoria, 5, 900, self.log)
        self.ctx = dict((login, auth.revalidar(sessao)) for login, sessao in SESSOES.items())
        # Gestor: perfil nao admin com CAD_PARAMETROS (como se a matriz o concedesse).
        self.ctx["gestor"] = dict(self.ctx["op.prod"], funcionalidades=frozenset(["CAD_PARAMETROS"]))
        self.svc = ServicoAdminParametros(self.catalogo, self.log)
        self.aud_base = max([a["id"] for a in self.auditoria.listar(pagina=1, tamanho=1000)["itens"]] or [0])

    def _auditorias(self, acao):
        return [a for a in self.auditoria.listar(filtros={"acao": acao}, pagina=1, tamanho=100)["itens"]
                if a["entidade"] == "tbsss_parametros" and a["id"] > self.aud_base]

    def _incluir(self, ator="admin", **mudancas):
        dados = {"codigo": "novo_param", "label": "Novo parametro", "tipo_componente": "TEXT"}
        dados.update(mudancas)
        return self.svc.salvar(self.ctx[ator], IP, None, dados)

    def _editar(self, pid, ator="admin", **mudancas):
        f = self.svc.formulario(self.ctx[ator], str(pid))
        dados = dict((k, f[k]) for k in ("param_nomeado", "label", "descricao", "tipo_componente", "opcoes_json",
                                          "valor_padrao", "regex_validacao", "versao"))
        dados["sensivel"] = f["sensivel"]
        dados.update(mudancas)
        return self.svc.salvar(self.ctx[ator], IP, str(pid), dados)


class TestCadastro(_Base):

    def test_inclusao_de_cada_tipo(self):
        casos = (
            {"codigo": "p_text", "tipo_componente": "TEXT", "regex_validacao": "[A-Z]{2}", "valor_padrao": "SP"},
            {"codigo": "p_number", "tipo_componente": "NUMBER", "valor_padrao": " -12.5 "},
            {"codigo": "p_date", "tipo_componente": "DATE", "valor_padrao": "2026-02-28"},
            {"codigo": "p_select", "tipo_componente": "SELECT", "opcoes_json": '{"A": "Alfa", "B": "Beta"}',
             "valor_padrao": "B"},
            {"codigo": "p_check", "tipo_componente": "CHECKBOX", "valor_padrao": "1", "param_nomeado": "--ativo"},
        )
        esperados = ("SP", "-12.5", "2026-02-28", "B", "true")
        for dados, padrao in zip(casos, esperados):
            pid, erros = self._incluir(**dados)
            self.assertEqual(erros, {}, dados["codigo"])
            self.assertEqual(self.catalogo.parametros_obter(pid)["valor_padrao"], padrao)
        self.assertEqual(self.catalogo.parametros_obter(pid)["param_nomeado"], "--ativo")
        self.assertEqual(len(self._auditorias("CAD_INSERIR")), 5)

    def test_codigo_invalido_ou_duplicado(self):
        for codigo in ("Data", "a-b", "x" * 31, ""):
            _pid, erros = self._incluir(codigo=codigo)
            self.assertIn("codigo", erros, codigo)
        _pid, erros = self._incluir(codigo="data_ref")
        self.assertEqual(erros, {"codigo": prm_mod.MSG_CODIGO_DUPLICADO})

    def test_flag_invalida(self):
        _pid, erros = self._incluir(param_nomeado="data")
        self.assertIn("param_nomeado", erros)

    def test_select_sem_opcoes_opcoes_em_outro_tipo_e_json_invalido(self):
        _pid, erros = self._incluir(tipo_componente="SELECT")
        self.assertIn("opcoes_json", erros)
        _pid, erros = self._incluir(tipo_componente="TEXT", opcoes_json='{"a": "b"}')
        self.assertEqual(erros, {"opcoes_json": prm_mod.MSG_OPCOES_PROIBIDAS})
        _pid, erros = self._incluir(tipo_componente="SELECT", opcoes_json='{"a": ')
        self.assertIn("JSON", erros["opcoes_json"])

    def test_padrao_invalido_para_o_tipo(self):
        for tipo, padrao, extra in (("NUMBER", "abc", {}), ("DATE", "31/12/2026", {}), ("CHECKBOX", "talvez", {}),
                                    ("SELECT", "Z", {"opcoes_json": '{"A": "Alfa"}'}),
                                    ("TEXT", "abc", {"regex_validacao": "[0-9]+"})):
            dados = dict(extra, tipo_componente=tipo, valor_padrao=padrao)
            _pid, erros = self._incluir(**dados)
            self.assertIn("valor_padrao", erros, tipo)
        _pid, erros = self._incluir(valor_padrao="x" * 101)
        self.assertEqual(erros, {"valor_padrao": prm_mod.MSG_PADRAO_TAMANHO})

    def test_regex_redos_e_regex_em_outro_tipo(self):
        _pid, erros = self._incluir(regex_validacao="(a+)+$")
        self.assertIn("ReDoS", erros["regex_validacao"])
        _pid, erros = self._incluir(regex_validacao="[")
        self.assertIn("inválida", erros["regex_validacao"])
        _pid, erros = self._incluir(tipo_componente="NUMBER", regex_validacao="[0-9]+")
        self.assertEqual(erros, {"regex_validacao": prm_mod.MSG_REGEX_SO_TEXTO})

    def test_regex_por_nao_admin(self):
        _pid, erros = self._incluir(ator="gestor", regex_validacao="[0-9]+")
        self.assertEqual(erros, {"regex_validacao": prm_mod.MSG_REGEX_SO_ADMIN})
        # Editar outros campos preserva a regex gravada; tentar trocar a regex ou o tipo e negado.
        _pid, erros = self._editar(P_FILIAL, ator="gestor", label="Filial (4 digitos)")
        self.assertEqual(erros, {})
        self.assertEqual(self.catalogo.parametros_obter(P_FILIAL)["regex_validacao"], "^[0-9]{4}$")
        _pid, erros = self._editar(P_FILIAL, ator="gestor", regex_validacao="[0-9]+")
        self.assertEqual(erros, {"regex_validacao": prm_mod.MSG_REGEX_SO_ADMIN})
        _pid, erros = self._editar(P_DESCRICAO_LOTE, ator="admin", regex_validacao="[A-Za-z ]+")
        self.assertEqual(erros, {})

    def test_codigo_imutavel_na_edicao(self):
        _pid, erros = self._editar(P_DESCRICAO_LOTE, codigo="outro_codigo", label="Lote")
        self.assertEqual(erros, {})
        self.assertEqual(self.catalogo.parametros_obter(P_DESCRICAO_LOTE)["codigo"], "descricao_lote")


class TestDependencias(_Base):

    def test_troca_de_tipo_com_vinculo_bloqueada_com_scripts(self):
        _pid, erros = self._editar(P_DATA_REF, tipo_componente="TEXT")
        self.assertIn("carga_diaria", erros["tipo_componente"])
        self.assertIn("relatorio_mensal", erros["tipo_componente"])
        self.assertEqual(self.catalogo.parametros_obter(P_DATA_REF)["tipo_componente"], "DATE")

    def test_troca_de_flag_com_script_nomeado_bloqueada(self):
        _pid, erros = self._editar(P_DATA_REF, param_nomeado="--data")
        self.assertIn("carga_diaria", erros["param_nomeado"])
        self.assertNotIn("relatorio_mensal", erros["param_nomeado"])

    def test_desativacao_com_vinculo_ativo_negada_listando_scripts(self):
        f = self.svc.formulario(self.ctx["admin"], str(P_DATA_REF))
        with self.assertRaises(OperacaoNegada) as cm:
            self.svc.alternar_ativo(self.ctx["admin"], IP, str(P_DATA_REF), f["versao"])
        self.assertIn("carga_diaria", cm.exception.mensagem)
        self.assertEqual(self.catalogo.parametros_obter(P_DATA_REF)["ativo"], "S")
        self.assertEqual(self._auditorias("CAD_DESATIVAR"), [])

    def test_desativacao_sem_vinculo_e_reativacao(self):
        pid, _ = self._incluir()
        f = self.svc.formulario(self.ctx["admin"], str(pid))
        self.assertEqual(self.svc.alternar_ativo(self.ctx["admin"], IP, str(pid), f["versao"])["ativo"], "N")
        f = self.svc.formulario(self.ctx["admin"], str(pid))
        self.assertEqual(self.svc.alternar_ativo(self.ctx["admin"], IP, str(pid), f["versao"])["ativo"], "S")
        with self.assertRaises(RepoConflito):
            self.svc.alternar_ativo(self.ctx["admin"], IP, str(pid), f["versao"])

    def test_regras_atomicas_no_repositorio(self):
        for dados, constraint in (({"tipo_componente": "TEXT"}, "sss_prm_tipo_vinculado"),
                                  ({"param_nomeado": "--outra"}, "sss_prm_flag_nomeado"),
                                  ({"ativo": "N"}, "sss_prm_vinculo_ativo")):
            with self.assertRaises(RepoViolacao) as cm:
                self.catalogo.parametros_alterar(P_DATA_REF, dados)
            self.assertEqual(cm.exception.constraint, constraint)

    def test_conflito_de_edicao(self):
        f = self.svc.formulario(self.ctx["admin"], str(P_DESCRICAO_LOTE))
        self._editar(P_DESCRICAO_LOTE, label="Primeira")
        dados = dict((k, f[k]) for k in ("param_nomeado", "descricao", "tipo_componente", "opcoes_json",
                                          "valor_padrao", "regex_validacao", "versao", "sensivel"))
        _pid, erros = self.svc.salvar(self.ctx["admin"], IP, str(P_DESCRICAO_LOTE), dict(dados, label="Segunda"))
        self.assertEqual(erros, {CAMPO_GERAL: admin_crud.MSG_CONFLITO})


class TestSensivelETeste(_Base):

    def test_padrao_sensivel_e_so_de_escrita_e_mascarado_na_auditoria(self):
        _pid, erros = self._editar(P_CHAVE_API, valor_padrao="tok-padrao-secreto-1")
        self.assertEqual(erros, {})
        self.assertEqual(self.catalogo.parametros_obter(P_CHAVE_API)["valor_padrao"], "tok-padrao-secreto-1")
        f = self.svc.formulario(self.ctx["admin"], str(P_CHAVE_API))
        self.assertEqual((f["valor_padrao"], f["tem_padrao"]), ("", True))
        # Em branco mantem; marcar remover apaga.
        _pid, erros = self._editar(P_CHAVE_API, label="Token da API")
        self.assertEqual(self.catalogo.parametros_obter(P_CHAVE_API)["valor_padrao"], "tok-padrao-secreto-1")
        _pid, erros = self._editar(P_CHAVE_API, remover_padrao="S")
        self.assertIsNone(self.catalogo.parametros_obter(P_CHAVE_API)["valor_padrao"])
        detalhes = " | ".join(a["detalhe"] for a in self._auditorias("CAD_ALTERAR"))
        self.assertNotIn("tok-padrao-secreto-1", detalhes)
        self.assertIn("****", detalhes)
        pagina = self.svc.listar(self.ctx["admin"], {"codigo": "chave_api"}, 1, 20)
        self.assertNotIn("tok-padrao", repr(pagina))

    def test_testar_reflete_configuracao_em_edicao(self):
        cfg = {"tipo_componente": "SELECT", "opcoes_json": '{"X": "Xis"}'}
        self.assertEqual(self.svc.testar(self.ctx["admin"], None, cfg, "X"), {"ok": True, "valor": "X"})
        self.assertFalse(self.svc.testar(self.ctx["admin"], None, cfg, "Y")["ok"])
        self.assertEqual(self.svc.testar(self.ctx["admin"], None, {"tipo_componente": "CHECKBOX"}, "1"),
                         {"ok": True, "valor": "true"})
        self.assertEqual(self.svc.testar(self.ctx["admin"], None, {"tipo_componente": "DATE"}, "2026-02-30")["ok"], False)
        r = self.svc.testar(self.ctx["admin"], None, {"tipo_componente": "TEXT", "regex_validacao": "(a+)+$"}, "a")
        self.assertIn("ReDoS", r["erro"])
        self.assertEqual(self.svc.testar(self.ctx["admin"], None, {"tipo_componente": "TEXT", "sensivel": "S"}, "abc"),
                         {"ok": True, "valor": "****"})

    def test_testar_com_regex_exige_admin(self):
        r = self.svc.testar(self.ctx["gestor"], str(P_FILIAL), {"tipo_componente": "TEXT"}, "1234")
        self.assertEqual(r, {"ok": False, "erro": prm_mod.MSG_TESTE_REGEX_ADMIN})
        self.assertEqual(self.svc.testar(self.ctx["admin"], str(P_FILIAL),
                                         {"tipo_componente": "TEXT", "regex_validacao": "^[0-9]{4}$"}, "1234"),
                         {"ok": True, "valor": "1234"})

    def test_opcoes_em_pares_preserva_ordem_numerica(self):
        self.assertEqual(prm_mod.opcoes_em_pares('{"2":"Dois","1":"Um","10":"Dez"}'),
                         [["2", "Dois"], ["1", "Um"], ["10", "Dez"]])
        self.assertEqual(prm_mod.opcoes_em_pares(""), [])
        self.assertIsNone(prm_mod.opcoes_em_pares("{invalido"))
        self.assertIsNone(prm_mod.opcoes_em_pares("[1, 2]"))

    def test_lista_filtros_e_acesso(self):
        pagina = self.svc.listar(self.ctx["admin"], {"tipo_componente": "DATE"}, 1, 20)
        data_ref = [p for p in pagina["itens"] if p["codigo"] == "data_ref"][0]
        self.assertEqual(data_ref["qtd_scripts"], 2)
        self.assertEqual(prm_mod.normalizar_filtros({"codigo": "data", "tipo_componente": "DATE", "ativo": "S"}),
                         {"codigo": "data", "tipo_componente": "DATE", "ativo": "S"})
        self.assertEqual(prm_mod.normalizar_filtros({"codigo": "<x>", "tipo_componente": "XML"}), {})
        for chamada in (lambda c: self.svc.listar(c, {}, 1, 20), lambda c: self.svc.formulario(c),
                        lambda c: self.svc.testar(c, None, {}, "x"), lambda c: self.svc.alternar_ativo(c, IP, "1", "x")):
            with self.assertRaises(AcessoNegado):
                chamada(self.ctx["op.prod"])
        with self.assertRaises(RepoNaoEncontrado):
            self.svc.formulario(self.ctx["admin"], "999")


if __name__ == "__main__":
    unittest.main()
