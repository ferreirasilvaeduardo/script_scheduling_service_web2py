# -*- coding: utf-8 -*-
"""Testes de admin_parameters_service.py (F4.4) sobre o backend FAKE."""
import _testenv  # noqa: F401

import logging
import os
import unittest
from unittest import mock

import admin_crud
import admin_parameters_service as prm_mod
import auth_service
import repo_factory
import security
from admin_crud import GENERAL_FIELD, AccessDenied, OperationDenied
from admin_parameters_service import AdminParametersService
from repo_errors import RepoConflict, RepoNotFound, RepoViolation

IP = "10.3.3.3"
SESSIONS = {
    "admin": {"user_id": 1, "login": "admin", "profile_id": 1, "perm_version": 1, "session_epoch": 0},
    "op.prod": {"user_id": 2, "login": "op.prod", "profile_id": 2, "perm_version": 1, "session_epoch": 0},
}
# Seed FAKE: 1 data_ref (DATE, carga_diaria NOMEADO e relatorio_mensal SEQUENCIAL), 5 codigo_filial
# (TEXT com regex ^[0-9]{4}$, validacao_fiscal), 6 documento_cliente (TEXT sensivel), 10 descricao_lote (TEXT).
P_DATA_REF, P_FILIAL, P_CHAVE_API, P_DESCRICAO_LOTE = 1, 5, 6, 10


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
        self.log = logging.getLogger("sss_teste_parametros")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        auth = auth_service.AuthService(repo_factory.get("users"), repo_factory.get("rbac"), self.catalog,
                                        self.audit, 5, 900, self.log)
        self.ctx = dict((login, auth.revalidate(session)) for login, session in SESSIONS.items())
        # Gestor: perfil nao admin com MANAGE_PARAMETERS (como se a matriz o concedesse).
        self.ctx["gestor"] = dict(self.ctx["op.prod"], features=frozenset(["MANAGE_PARAMETERS"]))
        self.svc = AdminParametersService(self.catalog, self.log)
        self.aud_base = max([a["id"] for a in self.audit.list(page=1, size=1000)["itens"]] or [0])

    def _audits(self, action):
        return [a for a in self.audit.list(filters={"action": action}, page=1, size=100)["itens"]
                if a["entity"] == "tbsss_parameters" and a["id"] > self.aud_base]

    def _insert(self, actor="admin", **changes):
        date = {"code": "novo_param", "label": "Novo parametro", "component_type": "TEXT"}
        date.update(changes)
        return self.svc.save(self.ctx[actor], IP, None, date)

    def _edit(self, pid, actor="admin", **changes):
        f = self.svc.form(self.ctx[actor], str(pid))
        date = dict((k, f[k]) for k in ("param_flag", "label", "description", "component_type", "options_json",
                                          "default_value", "validation_regex", "version"))
        date["sensitive"] = f["sensitive"]
        date.update(changes)
        return self.svc.save(self.ctx[actor], IP, str(pid), date)


class TestRegistration(_Base):

    def test_sensivel_nunca_volta_a_nao_sensivel(self):
        # CR-007, R-20 (README §6.2): respostas ja gravadas passariam a aparecer em claro.
        self._edit(P_CHAVE_API, default_value="tok-guardado-1234")
        _pid, errors = self._edit(P_CHAVE_API, sensitive="N")
        self.assertEqual(errors["sensitive"], prm_mod.MSG_SENSITIVE_ONE_WAY)
        self._edit(P_CHAVE_API, remove_default="Y")
        _pid, errors = self._edit(P_CHAVE_API, sensitive="N")
        self.assertEqual(errors["sensitive"], prm_mod.MSG_SENSITIVE_ONE_WAY)
        self.assertEqual(self.catalog.parameters_get(P_CHAVE_API)["sensitive"], "Y")

    def test_inclusao_audita_descricao_e_rotulo_sem_controle(self):
        _pid, errors = self._insert(label="Rotulo\tcom tab")
        self.assertEqual(errors, {"label": admin_crud.MSG_CONTROL_CHARS})
        pid, errors = self._insert(description="Descricao do parametro")
        self.assertEqual(errors, {})
        self.assertIn("description: Descricao do parametro", self._audits("CREATE")[0]["detail"])

    def test_versao_nao_deriva_do_valor_sensivel(self):
        # CR-003 P1: a versao vai ao HTML; um sha256 sem sal do segredo permitiria adivinha-lo.
        self._edit(P_CHAVE_API, default_value="segredo-numero-um-111")
        v1 = self.svc.form(self.ctx["admin"], str(P_CHAVE_API))["version"]
        self._edit(P_CHAVE_API, default_value="segredo-numero-dois-222")
        f = self.svc.form(self.ctx["admin"], str(P_CHAVE_API))
        self.assertEqual(f["version"], v1)
        self.assertNotIn("segredo-numero-dois-222", repr(f))
        p = self.catalog.parameters_get(P_CHAVE_API)
        with_value = admin_crud.version(p, prm_mod.EDITABLE_FIELDS)
        self.assertNotEqual(f["version"], with_value)

    def test_versao_muda_com_valor_nao_sensivel(self):
        v1 = self.svc.form(self.ctx["admin"], str(P_DESCRICAO_LOTE))["version"]
        self._edit(P_DESCRICAO_LOTE, default_value="lote-a")
        self.assertNotEqual(self.svc.form(self.ctx["admin"], str(P_DESCRICAO_LOTE))["version"], v1)

    def test_sensivel_de_vazio_para_preenchido_gera_conflito(self):
        f = self.svc.form(self.ctx["admin"], str(P_CHAVE_API))
        self.assertFalse(f["tem_padrao"])
        self.catalog.parameters_update(P_CHAVE_API, {"default_value": "colocado-por-outro-333"}, actor="teste")
        date = dict((k, f[k]) for k in ("param_flag", "label", "description", "component_type", "options_json",
                                          "default_value", "validation_regex", "version", "sensitive"))
        _pid, errors = self.svc.save(self.ctx["admin"], IP, str(P_CHAVE_API), dict(date, label="Outro"))
        self.assertEqual(errors, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})

    def test_inclusao_de_cada_tipo(self):
        cases = (
            {"code": "p_text", "component_type": "TEXT", "validation_regex": "[A-Z]{2}", "default_value": "SP"},
            {"code": "p_number", "component_type": "NUMBER", "default_value": " -12.5 "},
            {"code": "p_date", "component_type": "DATE", "default_value": "2026-02-28"},
            {"code": "p_select", "component_type": "SELECT", "options_json": '{"A": "Alfa", "B": "Beta"}',
             "default_value": "B"},
            {"code": "p_check", "component_type": "CHECKBOX", "default_value": "1", "param_flag": "--active"},
        )
        expected = ("SP", "-12.5", "2026-02-28", "B", "true")
        for date, default in zip(cases, expected):
            pid, errors = self._insert(**date)
            self.assertEqual(errors, {}, date["code"])
            self.assertEqual(self.catalog.parameters_get(pid)["default_value"], default)
        self.assertEqual(self.catalog.parameters_get(pid)["param_flag"], "--active")
        self.assertEqual(len(self._audits("CREATE")), 5)

    def test_codigo_invalido_ou_duplicado(self):
        for code in ("Data", "a-b", "x" * 31, ""):
            _pid, errors = self._insert(code=code)
            self.assertIn("code", errors, code)
        _pid, errors = self._insert(code="data_ref")
        self.assertEqual(errors, {"code": prm_mod.MSG_CODE_DUPLICATE})

    def test_flag_invalida(self):
        _pid, errors = self._insert(param_flag="data")
        self.assertIn("param_flag", errors)

    def test_select_sem_opcoes_opcoes_em_outro_tipo_e_json_invalido(self):
        _pid, errors = self._insert(component_type="SELECT")
        self.assertIn("options_json", errors)
        _pid, errors = self._insert(component_type="TEXT", options_json='{"a": "b"}')
        self.assertEqual(errors, {"options_json": prm_mod.MSG_OPTIONS_FORBIDDEN})
        _pid, errors = self._insert(component_type="SELECT", options_json='{"a": ')
        self.assertIn("JSON", errors["options_json"])

    def test_padrao_invalido_para_o_tipo(self):
        for kind, default, extra in (("NUMBER", "abc", {}), ("DATE", "31/12/2026", {}), ("CHECKBOX", "talvez", {}),
                                    ("SELECT", "Z", {"options_json": '{"A": "Alfa"}'}),
                                    ("TEXT", "abc", {"validation_regex": "[0-9]+"})):
            date = dict(extra, component_type=kind, default_value=default)
            _pid, errors = self._insert(**date)
            self.assertIn("default_value", errors, kind)
        _pid, errors = self._insert(default_value="x" * 101)
        self.assertEqual(errors, {"default_value": prm_mod.MSG_DEFAULT_LENGTH})

    def test_regex_redos_e_regex_em_outro_tipo(self):
        _pid, errors = self._insert(validation_regex="(a+)+$")
        self.assertIn("recusada", errors["validation_regex"])
        _pid, errors = self._insert(validation_regex="(a|a)*b")
        self.assertIn("grupo entre parênteses repetido", errors["validation_regex"])
        _pid, errors = self._insert(validation_regex="[")
        self.assertIn("inválida", errors["validation_regex"])
        _pid, errors = self._insert(component_type="NUMBER", validation_regex="[0-9]+")
        self.assertEqual(errors, {"validation_regex": prm_mod.MSG_REGEX_TEXT_ONLY})

    def test_regex_por_nao_admin(self):
        _pid, errors = self._insert(actor="gestor", validation_regex="[0-9]+")
        self.assertEqual(errors, {"validation_regex": prm_mod.MSG_REGEX_ADMIN_ONLY})
        # Editar outros campos preserva a regex gravada; tentar trocar a regex ou o tipo e negado.
        _pid, errors = self._edit(P_FILIAL, actor="gestor", label="Filial (4 digitos)")
        self.assertEqual(errors, {})
        self.assertEqual(self.catalog.parameters_get(P_FILIAL)["validation_regex"], "^[0-9]{4}$")
        _pid, errors = self._edit(P_FILIAL, actor="gestor", validation_regex="[0-9]+")
        self.assertEqual(errors, {"validation_regex": prm_mod.MSG_REGEX_ADMIN_ONLY})
        _pid, errors = self._edit(P_DESCRICAO_LOTE, actor="admin", validation_regex="[A-Za-z ]+")
        self.assertEqual(errors, {})

    def test_codigo_imutavel_na_edicao(self):
        _pid, errors = self._edit(P_DESCRICAO_LOTE, code="outro_codigo", label="Lote")
        self.assertEqual(errors, {})
        self.assertEqual(self.catalog.parameters_get(P_DESCRICAO_LOTE)["code"], "descricao_lote")


class TestDependencies(_Base):

    def test_troca_de_tipo_com_vinculo_bloqueada_com_scripts(self):
        _pid, errors = self._edit(P_DATA_REF, component_type="TEXT")
        self.assertIn("carga_diaria", errors["component_type"])
        self.assertIn("relatorio_mensal", errors["component_type"])
        self.assertEqual(self.catalog.parameters_get(P_DATA_REF)["component_type"], "DATE")

    def test_troca_de_flag_com_script_nomeado_bloqueada(self):
        _pid, errors = self._edit(P_DATA_REF, param_flag="--data")
        self.assertIn("carga_diaria", errors["param_flag"])
        self.assertNotIn("relatorio_mensal", errors["param_flag"])

    def test_desativacao_com_vinculo_ativo_negada_listando_scripts(self):
        f = self.svc.form(self.ctx["admin"], str(P_DATA_REF))
        with self.assertRaises(OperationDenied) as cm:
            self.svc.toggle_active(self.ctx["admin"], IP, str(P_DATA_REF), f["version"])
        self.assertIn("carga_diaria", cm.exception.message)
        self.assertEqual(self.catalog.parameters_get(P_DATA_REF)["active"], "Y")
        self.assertEqual(self._audits("DEACTIVATE"), [])

    def test_desativacao_sem_vinculo_e_reativacao(self):
        pid, _ = self._insert()
        f = self.svc.form(self.ctx["admin"], str(pid))
        self.assertEqual(self.svc.toggle_active(self.ctx["admin"], IP, str(pid), f["version"])["active"], "N")
        f = self.svc.form(self.ctx["admin"], str(pid))
        self.assertEqual(self.svc.toggle_active(self.ctx["admin"], IP, str(pid), f["version"])["active"], "Y")
        with self.assertRaises(RepoConflict):
            self.svc.toggle_active(self.ctx["admin"], IP, str(pid), f["version"])

    def test_regras_atomicas_no_repositorio(self):
        for date, constraint in (({"component_type": "TEXT"}, "sss_prm_tipo_vinculado"),
                                  ({"param_flag": "--outra"}, "sss_prm_flag_nomeado"),
                                  ({"active": "N"}, "sss_prm_vinculo_ativo")):
            with self.assertRaises(RepoViolation) as cm:
                self.catalog.parameters_update(P_DATA_REF, date, actor="teste")
            self.assertEqual(cm.exception.constraint, constraint)

    def test_conflito_de_edicao(self):
        f = self.svc.form(self.ctx["admin"], str(P_DESCRICAO_LOTE))
        self._edit(P_DESCRICAO_LOTE, label="Primeira")
        date = dict((k, f[k]) for k in ("param_flag", "description", "component_type", "options_json",
                                          "default_value", "validation_regex", "version", "sensitive"))
        _pid, errors = self.svc.save(self.ctx["admin"], IP, str(P_DESCRICAO_LOTE), dict(date, label="Segunda"))
        self.assertEqual(errors, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})


class TestSensitiveAndTest(_Base):

    def test_padrao_sensivel_e_so_de_escrita_e_mascarado_na_auditoria(self):
        _pid, errors = self._edit(P_CHAVE_API, default_value="tok-padrao-secreto-1")
        self.assertEqual(errors, {})
        self.assertEqual(self.catalog.parameters_get(P_CHAVE_API)["default_value"], "tok-padrao-secreto-1")
        f = self.svc.form(self.ctx["admin"], str(P_CHAVE_API))
        self.assertEqual((f["default_value"], f["tem_padrao"]), ("", True))
        # Em branco mantem; marcar remover apaga.
        _pid, errors = self._edit(P_CHAVE_API, label="Token da API")
        self.assertEqual(self.catalog.parameters_get(P_CHAVE_API)["default_value"], "tok-padrao-secreto-1")
        _pid, errors = self._edit(P_CHAVE_API, remove_default="Y")
        self.assertIsNone(self.catalog.parameters_get(P_CHAVE_API)["default_value"])
        details = " | ".join(a["detail"] for a in self._audits("UPDATE"))
        self.assertNotIn("tok-padrao-secreto-1", details)
        self.assertIn("****", details)
        page = self.svc.list(self.ctx["admin"], {"code": "documento_cliente"}, 1, 20)
        self.assertNotIn("tok-padrao", repr(page))

    def test_testar_reflete_configuracao_em_edicao(self):
        cfg = {"component_type": "SELECT", "options_json": '{"X": "Xis"}'}
        self.assertEqual(self.svc.test_regex(self.ctx["admin"], None, cfg, "X"), {"ok": True, "valor": "X"})
        self.assertFalse(self.svc.test_regex(self.ctx["admin"], None, cfg, "Y")["ok"])
        self.assertEqual(self.svc.test_regex(self.ctx["admin"], None, {"component_type": "CHECKBOX"}, "1"),
                         {"ok": True, "valor": "true"})
        self.assertEqual(self.svc.test_regex(self.ctx["admin"], None, {"component_type": "DATE"}, "2026-02-30")["ok"], False)
        r = self.svc.test_regex(self.ctx["admin"], None, {"component_type": "TEXT", "validation_regex": "(a+)+$"}, "a")
        self.assertIn("recusada", r["erro"])
        self.assertEqual(self.svc.test_regex(self.ctx["admin"], None, {"component_type": "TEXT", "sensitive": "Y"}, "abcd"),
                         {"ok": True, "valor": "****"})
        self.assertFalse(self.svc.test_regex(self.ctx["admin"], None, {"component_type": "TEXT", "sensitive": "Y"}, "abc")["ok"])

    def test_testar_com_regex_exige_admin(self):
        r = self.svc.test_regex(self.ctx["gestor"], str(P_FILIAL), {"component_type": "TEXT"}, "1234")
        self.assertEqual(r, {"ok": False, "erro": prm_mod.MSG_REGEX_TEST_ADMIN})
        self.assertEqual(self.svc.test_regex(self.ctx["admin"], str(P_FILIAL),
                                         {"component_type": "TEXT", "validation_regex": "^[0-9]{4}$"}, "1234"),
                         {"ok": True, "valor": "1234"})

    def test_opcoes_em_pares_preserva_ordem_numerica(self):
        self.assertEqual(prm_mod.options_as_pairs('{"2":"Dois","1":"Um","10":"Dez"}'),
                         [["2", "Dois"], ["1", "Um"], ["10", "Dez"]])
        self.assertEqual(prm_mod.options_as_pairs(""), [])
        self.assertIsNone(prm_mod.options_as_pairs("{invalido"))
        self.assertIsNone(prm_mod.options_as_pairs("[1, 2]"))

    def test_lista_filtros_e_acesso(self):
        page = self.svc.list(self.ctx["admin"], {"component_type": "DATE"}, 1, 20)
        date_ref = [p for p in page["itens"] if p["code"] == "data_ref"][0]
        self.assertEqual(date_ref["qtd_scripts"], 2)
        self.assertEqual(prm_mod.normalize_filters({"code": "data", "component_type": "DATE", "active": "Y"}),
                         {"code": "data", "component_type": "DATE", "active": "Y"})
        self.assertEqual(prm_mod.normalize_filters({"code": "<x>", "component_type": "XML"}), {})
        for call in (lambda c: self.svc.list(c, {}, 1, 20), lambda c: self.svc.form(c),
                        lambda c: self.svc.test_regex(c, None, {}, "x"), lambda c: self.svc.toggle_active(c, IP, "1", "x")):
            with self.assertRaises(AccessDenied):
                call(self.ctx["op.prod"])
        with self.assertRaises(RepoNotFound):
            self.svc.form(self.ctx["admin"], "999")


if __name__ == "__main__":
    unittest.main()
