# -*- coding: utf-8 -*-
"""Testes da tela de Entrada (CR-020d, README §5.10) sobre o FAKE: escopo, pasta pelos retratos, envio e retrato."""
from tests.support import _testenv  # noqa: F401
import datetime
import io
import logging
import os
import unittest
from unittest import mock

import admin_crud
import auth_service
import input_browse_service as browse
import repo_factory
from sss.core import security
from input_browse_service import InputBrowseService, InvalidRequest
from repo_errors import RepoNotFound

IP = "10.1.2.3"
SESSIONS = {
    "admin": {"user_id": 1, "login": "admin", "profile_id": 1, "perm_version": 1, "session_epoch": 0},
    "op.prod": {"user_id": 2, "login": "op.prod", "profile_id": 2, "perm_version": 1, "session_epoch": 0},
    "op.hml": {"user_id": 3, "login": "op.hml", "profile_id": 3, "perm_version": 1, "session_epoch": 0},
    "consulta": {"user_id": 4, "login": "consulta", "profile_id": 4, "perm_version": 1, "session_epoch": 0},
}
# Seed FAKE: carga_diaria (id 1) homologado em PRODUCAO; retrato do agt-host01 com lotes/clientes_outubro.csv.
ENV, SID = "PRODUCAO", 1


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
        log = logging.getLogger("sss_teste_entrada")
        log.addHandler(logging.NullHandler())
        log.propagate = False
        self.audit = repo_factory.get("audit")
        auth = auth_service.AuthService(repo_factory.get("users"), repo_factory.get("rbac"),
                                        repo_factory.get("catalog"), self.audit, 5, 900, log)
        self.ctx = dict((login, auth.revalidate(session)) for login, session in SESSIONS.items())
        self.inputs = repo_factory.get("inputs")
        self.svc = InputBrowseService(repo_factory.get("catalog"), self.inputs, log, 1024, 300)


class TestNavegacao(_Base):

    def test_ambientes_scripts_e_escopo(self):
        self.assertIn(ENV, [a["name"] for a in self.svc.environments(self.ctx["op.prod"])])
        scripts = [s["name"] for s in self.svc.scripts(self.ctx["op.prod"], ENV)]
        self.assertIn("carga_diaria", scripts)
        self.assertNotIn("sync_tabelas", scripts, "fora do perfil do op.prod")
        with self.assertRaises(RepoNotFound):
            self.svc.scripts(self.ctx["op.hml"], ENV)  # ambiente fora do perfil
        with self.assertRaises(RepoNotFound):
            self.svc.folder(self.ctx["op.prod"], ENV, 4)  # script fora do perfil
        with self.assertRaises(admin_crud.AccessDenied):
            self.svc.environments(self.ctx["consulta"])

    def test_pasta_montada_pelos_retratos(self):
        root = self.svc.folder(self.ctx["op.prod"], ENV, SID)
        self.assertEqual([s["path"] for s in root["subfolders"]], ["lotes"])
        self.assertEqual(root["files"], [])
        self.assertEqual([(l["agent_id"], l["truncated"]) for l in root["listings"]], [("agt-host01", False)])
        sub = self.svc.folder(self.ctx["op.prod"], ENV, SID, "lotes")
        self.assertEqual([(f["name"], f["size"], f["agents"]) for f in sub["files"]],
                         [("clientes_outubro.csv", 22, ["agt-host01"])])
        self.assertEqual([c["path"] for c in sub["crumbs"]], ["lotes"])
        up = sub["uploads"]["items"][0]
        self.assertEqual((up["target"], up["created_by"]), ("lotes/clientes_outubro.csv", u"você"))
        self.assertEqual((up["deliveries"][0]["state_label"], up["deliveries"][0]["reason_label"]), (u"Entregue", None))
        for bad in ("../x", "a/.oculta", "/".join(["n"] * 11)):
            with self.assertRaises(InvalidRequest):
                self.svc.folder(self.ctx["op.prod"], ENV, SID, bad)

    def test_motivo_da_falha_em_linguagem_simples(self):
        hml = self.svc.folder(self.ctx["admin"], "HOMOLOGACAO", 2)
        reasons = dict((d["agent_id"], (d["state_label"], d["reason_label"]))
                       for d in hml["uploads"]["items"][0]["deliveries"])
        self.assertEqual(reasons["agt-host02"], (u"Falhou", browse.REASON_LABELS["EXISTS"]))
        self.assertEqual(reasons["agt-host01"], (u"Aguardando", None))


class TestEnvio(_Base):

    def test_envio_para_os_agentes_vivos_com_auditoria(self):
        result, errors = self.svc.upload(self.ctx["op.prod"], IP, ENV, SID, " novos/2026/ ", "C:\\Users\\ana\\a.csv",
                                         io.BytesIO(b"x;y\n"), False)
        self.assertEqual(errors, {})
        self.assertEqual(result["agents"], ["agt-host01"])
        page = self.inputs.uploads(ENV, SID)["items"][0]
        self.assertEqual((page["relative_dir"], page["file_name"], page["size_bytes"], page["replace_existing"],
                          page["created_by"]), ("novos/2026", "a.csv", 4, "N", "op.prod"))
        audit = self.audit.list(filters={"action": "INPUT_UPLOAD"}, page=1, size=5)["items"]
        self.assertEqual((audit[0]["actor"], audit[0]["source_ip"], audit[0]["entity_id"]), ("op.prod", IP, result["id"]))

    def test_erros_por_campo_sem_gravar(self):
        total = self.inputs.uploads(ENV, SID)["total"]
        cases = (
            ("", ".oculto.csv", b"x", "file"),
            ("../fora", "a.csv", b"x", "relative_dir"),
            ("", "a.csv", b"x" * 1025, "file"),
            ("", "", b"x", "file"),
        )
        for folder, name, data, field in cases:
            result, errors = self.svc.upload(self.ctx["op.prod"], IP, ENV, SID, folder, name, io.BytesIO(data), False)
            self.assertIsNone(result)
            self.assertIn(field, errors, (folder, name))
        _r, errors = self.svc.upload(self.ctx["op.prod"], IP, ENV, SID, "", None, None, False)
        self.assertEqual(errors, {"file": browse.MSG_FILE})
        self.assertEqual(self.inputs.uploads(ENV, SID)["total"], total)

    def test_sem_servidor_no_ar(self):
        store = self.inputs._store
        store.agents_hb_simulated.discard("agt-host01")
        for a in store.agents.values():
            a["heartbeat_at"] = store.now() - datetime.timedelta(hours=1)
        result, errors = self.svc.upload(self.ctx["op.prod"], IP, ENV, SID, "", "a.csv", io.BytesIO(b"x"), True)
        self.assertEqual((result, errors), (None, {browse.GENERAL_FIELD: browse.MSG_NO_AGENT}))
        self.assertEqual(self.svc.refresh(self.ctx["op.prod"], ENV, SID), 0)

    def test_pedido_de_retrato(self):
        self.assertEqual(self.svc.refresh(self.ctx["op.prod"], ENV, SID), 1)
        self.assertIn(SID, [d["script_id"] for d in self.inputs.listings_due("agt-host01")])
        with self.assertRaises(RepoNotFound):
            self.svc.refresh(self.ctx["op.hml"], ENV, SID)

    def test_nome_enviado_pelo_navegador(self):
        self.assertEqual(browse.upload_name("C:\\pasta\\relatório.csv"), u"relatório.csv")
        self.assertEqual(browse.upload_name("/home/ana/a.txt"), "a.txt")
        self.assertEqual(browse.normalize_folder(" /a/b/ "), "a/b")
        self.assertEqual(browse.normalize_folder(""), "")
        self.assertIsNone(browse.normalize_folder("a//b"))


if __name__ == "__main__":
    unittest.main()
