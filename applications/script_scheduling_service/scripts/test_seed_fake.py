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
CATALOG = {
    "EXEC_SCRIPT": u"Rodar Scripts", "VIEW_LOGS": u"Consultar Tickets", "CANCEL_TICKET": u"Cancelar Tickets",
    "MANAGE_USERS": u"Gestão de Usuários", "MANAGE_PROFILES": u"Gestão de Perfis", "MANAGE_ENVIRONMENTS": u"Gestão de Ambientes",
    "MANAGE_SCRIPTS": u"Gestão de Scripts", "MANAGE_PARAMETERS": u"Dicionário de Parâmetros",
    "MANAGE_SCHEDULES": u"Regras de Agendamento", "VIEW_AUDIT": u"Auditoria",
    "DOWNLOAD_OUTPUT": u"Baixar Saídas", "UPLOAD_INPUT": u"Enviar Arquivos",
}
_CREDENTIAL_WORDS = ("senha", "password", "token", "chave", "api", "secret", "credencial")


class TestSeedFake(unittest.TestCase):

    def setUp(self):
        env = mock.patch.dict(os.environ, {repo_factory.ENV_DEV_PASSWORD: "senha-dev-de-teste-123"})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configure, None)
        repo_factory.get("tickets")  # carrega o seed
        self.store = repo_factory._fake_store
        self.now = self.store.now()

    def test_funcionalidades_com_os_nomes_do_readme(self):
        names = dict((f["code"], f["name"]) for f in self.store.features.values())
        self.assertEqual(names, CATALOG)

    def test_nenhum_parametro_de_credencial(self):
        for p in self.store.parameters.values():
            text = (p["code"] + " " + (p.get("label") or "") + " " + (p.get("param_flag") or "")).lower()
            for word in _CREDENTIAL_WORDS:
                self.assertNotIn(word, text, p["code"])

    def test_prioridade_1_so_para_admin_e_created_at_nunca_no_futuro(self):
        admins = set(u["login"] for u in self.store.users.values()
                     if self.store.profiles[u["profile_id"]]["is_admin"] == "Y")
        for t in self.store.tickets.values():
            if t["priority"] == 1:
                self.assertIn(t["requested_by"], admins, t["id"])
            self.assertLessEqual(t["created_at"], self.now, t["id"])

    def test_snapshot_e_respostas_compativeis_com_o_script(self):
        for t in self.store.tickets.values():
            snap = json.loads(t["submitted_params"])
            self.assertEqual(snap["version"], params_compiler.SNAPSHOT_VERSION, t["id"])
            links = [v for v in self.store.script_param.values() if v["script_id"] == t["script_id"]]
            codes = set(self.store.parameters[v["parameter_id"]]["code"] for v in links)
            self.assertEqual(set(snap["answers"]), codes, t["id"])
            resp = [r for r in self.store.ticket_answer.values() if r["ticket_id"] == t["id"]]
            self.assertTrue(set(r["parameter_id"] for r in resp) <= set(v["parameter_id"] for v in links), t["id"])

    def test_agendamentos_alinhados_ao_minuto_e_a_regra(self):
        for a in self.store.schedules.values():
            self.assertEqual((a["next_run_at"].second, a["next_run_at"].microsecond), (0, 0), a["id"])
            expected = recurrence.next_run(a, recurrence.truncate_seconds(self.now), 1461)
            self.assertEqual(a["next_run_at"], expected, a["id"])
            answers = json.loads(a["params_json"])
            required = [self.store.parameters[v["parameter_id"]]["code"] for v in self.store.script_param.values()
                            if v["script_id"] == a["script_id"] and v["required"] == "Y"]
            for code in required:
                self.assertIn(code, answers, a["id"])

    def test_linha_de_controle_na_versao_do_codigo(self):
        import sql_ident
        self.assertIn(1, self.store.control)
        ctl = self.store.control[1]
        self.assertEqual(ctl["id"], 1)
        self.assertEqual(ctl["schema_version"], sql_ident.SCHEMA_VERSION)


class TestSeedRecordColumns(unittest.TestCase):
    """Colunas de registro do seed coerentes com o README §10 e §2.5 (CR-006)."""

    setUp = TestSeedFake.setUp

    def test_toda_linha_com_registro_coerente(self):
        import sql_ident
        for entity in sql_ident.TABLES:
            rows = list(getattr(self.store, entity).values())
            self.assertTrue(rows, entity)
            for r in rows:
                if entity in sql_ident.TABLES_WITHOUT_RECORD:
                    self.assertNotIn("created_by", r)
                    continue
                self.assertTrue(r["created_by"] and len(r["created_by"]) <= sql_ident.ACTOR_MAX, (entity, r["id"]))
                self.assertLessEqual(r["created_at"], self.now, (entity, r["id"]))
                self.assertEqual(r["updated_at"] is None, r["updated_by"] is None, (entity, r["id"]))
                if r["updated_at"] is not None:
                    self.assertTrue(r["created_at"] <= r["updated_at"] <= self.now, (entity, r["id"]))

    def test_autoria_por_tipo_de_registro(self):
        for name in ("environments", "profiles", "features", "scripts", "users", "parameters",
                     "profile_feature", "script_env", "script_param"):
            for r in getattr(self.store, name).values():
                self.assertEqual(r["created_by"], "SYSTEM:seed", name)
                self.assertEqual(r["updated_by"] is not None, r.get("active") == "N", (name, r["id"]))
        for a in self.store.agents.values():
            self.assertEqual(a["created_by"], "SYSTEM:%s" % a["code"])
        for a in self.store.schedules.values():
            if a["active"] == "N" and a["pause_reason"] == "MANUAL":
                self.assertEqual(a["updated_by"], self.store.users[a["user_id"]]["login"])
        for t in self.store.tickets.values():
            if t["schedule_id"] is None:
                self.assertEqual(t["created_by"], t["requested_by"], t["id"])
            else:
                self.assertTrue(t["created_by"].startswith("SYSTEM:agt-"), t["id"])
            self.assertEqual(t["updated_by"] is None, t["status"] == "PENDING", t["id"])
            if t["status"] in ("RUNNING", "SUCCESS", "FAILED"):
                self.assertEqual(t["updated_by"], "SYSTEM:%s" % t["agent_id"], t["id"])
        for r in self.store.ticket_answer.values():
            self.assertEqual(r["created_by"], self.store.tickets[r["ticket_id"]]["created_by"])


if __name__ == "__main__":
    unittest.main()
