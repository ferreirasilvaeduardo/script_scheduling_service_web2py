# -*- coding: utf-8 -*-
"""Testes da tela de Saidas (CR-020a, README §5.9) sobre o backend FAKE: navegacao, escopo e downloads."""
from tests.support import _testenv  # noqa: F401
import datetime
import io
import logging
import os
import unittest
import zipfile
from unittest import mock

import admin_crud
import auth_service
import output_browse_service as browse
import repo_factory
import security
from output_browse_service import BlobReader, InvalidRequest, OutputBrowseService
from repo_errors import RepoNotFound

IP = "10.1.2.3"
SESSIONS = {
    "admin": {"user_id": 1, "login": "admin", "profile_id": 1, "perm_version": 1, "session_epoch": 0},
    "op.prod": {"user_id": 2, "login": "op.prod", "profile_id": 2, "perm_version": 1, "session_epoch": 0},
    "op.hml": {"user_id": 3, "login": "op.hml", "profile_id": 3, "perm_version": 1, "session_epoch": 0},
    "consulta": {"user_id": 4, "login": "consulta", "profile_id": 4, "perm_version": 1, "session_epoch": 0},
}
# Seed FAKE: o ticket 17 (carga_diaria em PRODUCAO, do op.prod) tem a unica saida AVAILABLE.
TID, SID, ENV = 17, 1, "PRODUCAO"


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
        self.tickets = repo_factory.get("tickets")
        self.audit = repo_factory.get("audit")
        log = logging.getLogger("sss_teste_saidas")
        log.addHandler(logging.NullHandler())
        log.propagate = False
        auth = auth_service.AuthService(repo_factory.get("users"), repo_factory.get("rbac"),
                                        repo_factory.get("catalog"), self.audit, 5, 900, log)
        self.ctx = dict((login, auth.revalidate(session)) for login, session in SESSIONS.items())
        self.svc = OutputBrowseService(self.tickets, repo_factory.get("catalog"), self.audit, log)
        # O seed monta as datas a partir de store.now(): o dia da saida vem do started_at do ticket (README §5.9).
        self.day_start = self.tickets.get(TID)["started_at"].replace(hour=0, minute=0, second=0, microsecond=0)
        self.day = self.day_start.strftime("%Y-%m-%d")

    def _audits(self):
        return [a for a in self.audit.list(page=1, size=100)["items"] if a["action"] == browse.AUDIT_ACTION]


class TestNavegacao(_Base):

    def test_niveis_ambiente_script_dia_ticket(self):
        envs = self.svc.environments(self.ctx["op.prod"])
        self.assertEqual([(e["environment"], e["count"]) for e in envs], [(ENV, 1)])
        scripts = self.svc.scripts(self.ctx["op.prod"], ENV)
        self.assertEqual([(s["script_id"], s["script_name"], s["count"]) for s in scripts], [(SID, "carga_diaria", 1)])
        days = self.svc.days(self.ctx["op.prod"], ENV, str(SID))
        self.assertEqual(days["script_name"], "carga_diaria")
        self.assertEqual([d["day"] for d in days["days"]], [self.day_start])
        result = self.svc.tickets(self.ctx["op.prod"], ENV, str(SID), self.day)
        self.assertEqual(([t["id"] for t in result["items"]], result["total"]), ([TID], 1))
        self.assertEqual(result["items"][0]["file_count"], 2)
        self.assertEqual(result["items"][0]["requested_by"], u"você", "solicitante mascarado sem VIEW_AUDIT")
        self.assertEqual(self.svc.tickets(self.ctx["admin"], ENV, SID, self.day)["items"][0]["requested_by"], "op.prod")
        other_day = (self.day_start - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        self.assertEqual(self.svc.tickets(self.ctx["op.prod"], ENV, SID, other_day)["total"], 0, "outro dia")

    def test_so_saidas_disponiveis(self):
        # Os tickets 29 (EXCEEDED) e 30 (FAILED) do seed nao entram em nenhum nivel.
        everything = self.svc.environments(self.ctx["admin"])
        self.assertEqual(sum(e["count"] for e in everything), 1)

    def test_escopo_e_funcionalidade(self):
        # op.hml nao tem PRODUCAO: nada a listar e 404 (nunca 403) ao forcar o ambiente ou o ticket.
        self.assertEqual(self.svc.environments(self.ctx["op.hml"]), [])
        for call in (lambda: self.svc.scripts(self.ctx["op.hml"], ENV),
                     lambda: self.svc.days(self.ctx["op.hml"], ENV, SID),
                     lambda: self.svc.tickets(self.ctx["op.hml"], ENV, SID, self.day),
                     lambda: self.svc.files(self.ctx["op.hml"], TID),
                     lambda: self.svc.zip_download(self.ctx["op.hml"], IP, TID),
                     lambda: self.svc.file_download(self.ctx["op.hml"], IP, TID, "resumo.txt")):
            with self.assertRaises(RepoNotFound):
                call()
        # consulta (READ_ONLY) nao tem Baixar Saidas.
        with self.assertRaises(admin_crud.AccessDenied):
            self.svc.environments(self.ctx["consulta"])

    def test_parametros_fora_do_formato(self):
        for day in ("22/10/2026", "2026-13-01", "", None):
            with self.assertRaises(InvalidRequest):
                self.svc.tickets(self.ctx["op.prod"], ENV, SID, day)
        for value in ("x", "0", "-1", None):
            with self.assertRaises(InvalidRequest):
                self.svc.files(self.ctx["op.prod"], value)
        with self.assertRaises(RepoNotFound):
            self.svc.files(self.ctx["op.prod"], 1)  # ticket sem saida
        with self.assertRaises(RepoNotFound):
            self.svc.files(self.ctx["admin"], 29)  # saida EXCEEDED, so no disco do agente


class TestArquivosEDownloads(_Base):

    def test_indice_do_zip_sem_pastas(self):
        result = self.svc.files(self.ctx["op.prod"], str(TID))
        self.assertEqual(result["total"], 2)
        self.assertEqual([(f["folder"], f["base"]) for f in result["items"]],
                         [("rejeitados", "linhas_rejeitadas.csv"), ("", "resumo.txt")])
        self.assertEqual(result["ticket"]["script_name"], "carga_diaria")
        self.assertEqual(self._audits(), [], "navegar nao audita")

    def test_zip_completo_auditado(self):
        tid, size, parts = self.svc.zip_download(self.ctx["op.prod"], IP, TID)
        data = b"".join(parts)
        self.assertEqual((tid, len(data)), (TID, size))
        self.assertEqual(sorted(zipfile.ZipFile(io.BytesIO(data)).namelist()),
                         ["rejeitados/linhas_rejeitadas.csv", "resumo.txt"])
        audits = self._audits()
        self.assertEqual(len(audits), 1)
        self.assertEqual((audits[0]["actor"], audits[0]["entity"], audits[0]["entity_id"], audits[0]["source_ip"]),
                         ("op.prod", "tbsss_tickets", TID, IP))
        self.assertIn("zip completo", audits[0]["detail"])

    def test_um_arquivo_pelo_nome_exato_do_indice(self):
        name, size, parts = self.svc.file_download(self.ctx["op.prod"], IP, TID, "rejeitados/linhas_rejeitadas.csv")
        data = b"".join(parts)
        self.assertEqual((name, size, data), ("linhas_rejeitadas.csv", len(data),
                                              b"linha;motivo\n17;data invalida\n42;valor negativo\n"))
        self.assertIn("rejeitados/linhas_rejeitadas.csv", self._audits()[0]["detail"])

    def test_nome_fora_do_indice_e_recusado_sem_auditar(self):
        for name in ("../resumo.txt", "/resumo.txt", "rejeitados", "rejeitados/", "nao_existe.txt", "Resumo.txt"):
            with self.assertRaises((RepoNotFound, InvalidRequest)):
                self.svc.file_download(self.ctx["op.prod"], IP, TID, name)
        for name in ("", None, "x" * (browse.NAME_MAX + 1)):
            with self.assertRaises(InvalidRequest):
                self.svc.file_download(self.ctx["op.prod"], IP, TID, name)
        self.assertEqual(self._audits(), [])

    def test_nome_para_download(self):
        self.assertEqual(browse.download_name("a/b/rel\"at;o\\rio.csv"), "relatorio.csv")
        self.assertEqual(browse.download_name("pasta/"), "arquivo")
        self.assertEqual(browse.download_name(u"saída/relatório.txt"), u"relatório.txt")


class TestBlobReader(_Base):

    def test_leitura_em_blocos_com_seek(self):
        content = bytes(range(256)) * 40  # 10.240 bytes
        calls = []

        class _Repo(object):
            def output_read(self, tid, off, size):
                calls.append(off)
                return content[off:off + size]
        with mock.patch.object(browse, "BLOCK_BYTES", 1000):
            r = BlobReader(_Repo(), 5, len(content))
            self.assertEqual(r.read(10), content[:10])
            r.seek(-20, 2)
            self.assertEqual(r.read(), content[-20:])
            r.seek(995)
            self.assertEqual(r.read(10), content[995:1005], "atravessa dois blocos")
            self.assertEqual(r.tell(), 1005)
            r.seek(5000)
            self.assertEqual(r.read(0), b"")
            r.seek(len(content) + 3)
            self.assertEqual(r.read(5), b"", "depois do fim")
        self.assertTrue(all(off % 1000 == 0 for off in calls), "so leituras alinhadas ao bloco")
        with self.assertRaises(ValueError):
            BlobReader(_Repo(), 5, 10).seek(-1)


if __name__ == "__main__":
    unittest.main()
