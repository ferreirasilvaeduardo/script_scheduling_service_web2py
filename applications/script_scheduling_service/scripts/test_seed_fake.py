# -*- coding: utf-8 -*-
"""O seed do FAKE segue as regras de negocio (README §2.5, CR-003 P8): ele tambem e a demonstracao da homologacao."""
import _testenv  # noqa: F401

import json
import os
import unittest
from unittest import mock

import params_compiler
import recurrence
import repo_factory

# README §4.3.D, texto exato.
CATALOGO = {
    "EXEC_SCRIPT": u"Disparar Scripts", "VIEW_LOGS": u"Consultar Logs", "CANCEL_TICKET": u"Cancelar Tickets",
    "MANAGE_USERS": u"Gestão de Usuários", "MANAGE_PROFILES": u"Gestão de Perfis", "MANAGE_ENVIRONMENTS": u"Gestão de Ambientes",
    "MANAGE_SCRIPTS": u"Gestão de Scripts", "MANAGE_PARAMETERS": u"Dicionário de Parâmetros",
    "MANAGE_SCHEDULES": u"Regras de Agendamento", "VIEW_AUDIT": u"Auditoria",
}
_PALAVRAS_CREDENCIAL = ("senha", "password", "token", "chave", "api", "secret", "credencial")


class TestSeedFake(unittest.TestCase):

    def setUp(self):
        env = mock.patch.dict(os.environ, {repo_factory.ENV_SENHA_DEV: "senha-dev-de-teste-123"})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configurar, None)
        repo_factory.obter("tickets")  # carrega o seed
        self.store = repo_factory._fake_store
        self.agora = self.store.agora()

    def test_funcionalidades_com_os_nomes_do_readme(self):
        nomes = dict((f["code"], f["name"]) for f in self.store.funcionalidades.values())
        self.assertEqual(nomes, CATALOGO)

    def test_nenhum_parametro_de_credencial(self):
        for p in self.store.parametros.values():
            texto = (p["code"] + " " + (p.get("label") or "") + " " + (p.get("param_flag") or "")).lower()
            for palavra in _PALAVRAS_CREDENCIAL:
                self.assertNotIn(palavra, texto, p["code"])

    def test_prioridade_1_so_para_admin_e_created_at_nunca_no_futuro(self):
        admins = set(u["login"] for u in self.store.usuarios.values()
                     if self.store.perfis[u["profile_id"]]["is_admin"] == "Y")
        for t in self.store.tickets.values():
            if t["priority"] == 1:
                self.assertIn(t["requested_by"], admins, t["id"])
            self.assertLessEqual(t["created_at"], self.agora, t["id"])

    def test_snapshot_e_respostas_compativeis_com_o_script(self):
        for t in self.store.tickets.values():
            snap = json.loads(t["submitted_params"])
            self.assertEqual(snap["version"], params_compiler.VERSAO_SNAPSHOT, t["id"])
            vinculos = [v for v in self.store.script_param.values() if v["script_id"] == t["script_id"]]
            codigos = set(self.store.parametros[v["parameter_id"]]["code"] for v in vinculos)
            self.assertEqual(set(snap["respostas"]), codigos, t["id"])
            resp = [r for r in self.store.ticket_resp.values() if r["ticket_id"] == t["id"]]
            self.assertTrue(set(r["parameter_id"] for r in resp) <= set(v["parameter_id"] for v in vinculos), t["id"])

    def test_agendamentos_alinhados_ao_minuto_e_a_regra(self):
        for a in self.store.agendamentos.values():
            self.assertEqual((a["next_run_at"].second, a["next_run_at"].microsecond), (0, 0), a["id"])
            esperado = recurrence.proxima_execucao(a, recurrence.truncar_segundos(self.agora), 1461)
            self.assertEqual(a["next_run_at"], esperado, a["id"])
            respostas = json.loads(a["params_json"])
            obrigatorios = [self.store.parametros[v["parameter_id"]]["code"] for v in self.store.script_param.values()
                            if v["script_id"] == a["script_id"] and v["required"] == "Y"]
            for codigo in obrigatorios:
                self.assertIn(codigo, respostas, a["id"])

    def test_linha_de_controle_na_versao_do_codigo(self):
        import sql_ident
        self.assertIn(1, self.store.controle)
        ctl = self.store.controle[1]
        self.assertEqual(ctl["id"], 1)
        self.assertEqual(ctl["schema_version"], sql_ident.VERSAO_ESQUEMA)


class TestSeedColunasRegistro(unittest.TestCase):
    """Colunas de registro do seed coerentes com o README §10 e §2.5 (CR-006)."""

    setUp = TestSeedFake.setUp

    def test_toda_linha_com_registro_coerente(self):
        import sql_ident
        for entidade in sql_ident.TABELAS:
            linhas = list(getattr(self.store, entidade).values())
            self.assertTrue(linhas, entidade)
            for r in linhas:
                if entidade in sql_ident.TABELAS_SEM_REGISTRO:
                    self.assertNotIn("created_by", r)
                    continue
                self.assertTrue(r["created_by"] and len(r["created_by"]) <= sql_ident.ATOR_MAX, (entidade, r["id"]))
                self.assertLessEqual(r["created_at"], self.agora, (entidade, r["id"]))
                self.assertEqual(r["updated_at"] is None, r["updated_by"] is None, (entidade, r["id"]))
                if r["updated_at"] is not None:
                    self.assertTrue(r["created_at"] <= r["updated_at"] <= self.agora, (entidade, r["id"]))

    def test_autoria_por_tipo_de_registro(self):
        for nome in ("ambientes", "perfis", "funcionalidades", "scripts", "usuarios", "parametros",
                     "perfil_func", "script_amb", "script_param"):
            for r in getattr(self.store, nome).values():
                self.assertEqual(r["created_by"], "SYSTEM:seed", nome)
                self.assertEqual(r["updated_by"] is not None, r.get("active") == "N", (nome, r["id"]))
        for a in self.store.agentes.values():
            self.assertEqual(a["created_by"], "SYSTEM:%s" % a["code"])
        for a in self.store.agendamentos.values():
            if a["active"] == "N" and a["pause_reason"] == "MANUAL":
                self.assertEqual(a["updated_by"], self.store.usuarios[a["user_id"]]["login"])
        for t in self.store.tickets.values():
            if t["schedule_id"] is None:
                self.assertEqual(t["created_by"], t["requested_by"], t["id"])
            else:
                self.assertTrue(t["created_by"].startswith("SYSTEM:agt-"), t["id"])
            self.assertEqual(t["updated_by"] is None, t["status"] == "PENDING", t["id"])
            if t["status"] in ("RUNNING", "SUCCESS", "FAILED"):
                self.assertEqual(t["updated_by"], "SYSTEM:%s" % t["agent_id"], t["id"])
        for r in self.store.ticket_resp.values():
            self.assertEqual(r["created_by"], self.store.tickets[r["ticket_id"]]["created_by"])


if __name__ == "__main__":
    unittest.main()
