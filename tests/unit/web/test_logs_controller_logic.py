# -*- coding: utf-8 -*-
"""Testes da logica por tras de logs/chunk e logs/download (F3.4): ticket_service.read_log e log_chunks."""
from tests.support import _testenv  # noqa: F401

import datetime
import logging
import os
import unittest
from unittest import mock

import auth_service
from sss.persistence import repo_factory
from sss.core import security
from sss.persistence.repo_errors import RepoUnavailable, RepoNotFound
from ticket_service import LOG_MAX_CHARS, DOWNLOAD_INTERRUPTED_MARKER, InvalidOffset, TicketService

SESSIONS = {
    "admin": {"user_id": 1, "login": "admin", "profile_id": 1, "perm_version": 1, "session_epoch": 0},
    "op.hml": {"user_id": 3, "login": "op.hml", "profile_id": 3, "perm_version": 1, "session_epoch": 0},
    "consulta": {"user_id": 4, "login": "consulta", "profile_id": 4, "perm_version": 1, "session_epoch": 0},
}
# Seed FAKE: 13 RUNNING (PRODUCAO, op.prod, carga_diaria com documento_cliente sensivel, 8 s/etapa),
# 17 SUCCESS com log de ~2 MB, 35 FAILED/LOG_LIMIT com log_truncated = 'Y'.
TCK_RUNNING, TCK_GRANDE, TCK_TRUNCADO = 13, 17, 35
STEP_13_S = 8
STAGES = 50
SEED_SECRET = "00011122233"
# README §8.10.
MARKER_TRUNCATED = "[SSS] log truncado no banco; arquivo integral no agente\n"


class _Clock(object):

    def __init__(self, instant):
        self.instant = instant

    def __call__(self):
        return self.instant

    def advance(self, seconds):
        self.instant += datetime.timedelta(seconds=seconds)


class _BaseLog(unittest.TestCase):

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

        catalog = repo_factory.get("catalog")
        self.tickets = repo_factory.get("tickets")
        # Congela o relogio no instante da carga do seed (started_at do RUNNING + 5 min).
        start = self.tickets.get(TCK_RUNNING)["started_at"]
        self.clock = _Clock(start + datetime.timedelta(minutes=5))
        repo_factory._fake_store.set_clock(self.clock)

        self.log = logging.getLogger("sss_teste_logs")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        auth = auth_service.AuthService(
            repo_factory.get("users"), repo_factory.get("rbac"), catalog,
            repo_factory.get("audit"), 5, 900, self.log)
        self.ctx = dict((login, auth.revalidate(session)) for login, session in SESSIONS.items())
        self.svc = TicketService(catalog, self.tickets, self.log)

    def _full_log(self, ticket_id):
        """Log inteiro lido do repositorio em fatias, pelo contrato (obter nao traz log_output)."""
        parts, offset = [], 0
        while True:
            text, offset, _terminal, _truncated = self.tickets.log_read(ticket_id, offset, 65536)
            if not text:
                return "".join(parts)
            parts.append(text)

    def _read_all(self, login, ticket_id):
        parts = []
        offset = 0
        while True:
            r = self.svc.read_log(self.ctx[login], str(ticket_id), str(offset))
            self.assertLessEqual(len(r["text"]), LOG_MAX_CHARS)
            self.assertEqual(r["next_offset"], offset + len(r["text"]))
            if not r["text"]:
                return "".join(parts), r
            parts.append(r["text"])
            offset = r["next_offset"]


class TestReadLogValidation(_BaseLog):

    def test_offset_invalido(self):
        for invalid in ("-1", "x", "", "1.5", " 1", "12345678901", None, -1, True, 1.0, ["a"]):
            with self.assertRaises(InvalidOffset, msg=repr(invalid)):
                self.svc.read_log(self.ctx["admin"], "17", invalid)

    def test_offset_valido_em_lista_vale_o_ultimo(self):
        r = self.svc.read_log(self.ctx["admin"], "17", ["0", "10"])
        self.assertEqual(r["next_offset"], 10 + len(r["text"]))

    def test_ticket_inexistente_ou_id_invalido_e_404(self):
        for tid in ("999", "0", "abc", None, "-3"):
            with self.assertRaises(RepoNotFound, msg=repr(tid)):
                self.svc.read_log(self.ctx["admin"], tid, "0")

    def test_fora_do_escopo_e_404(self):
        # op.hml enxerga HOMOLOGACAO/DESENV e seus proprios; o 13 e PRODUCAO de op.prod.
        with self.assertRaises(RepoNotFound):
            self.svc.read_log(self.ctx["op.hml"], str(TCK_RUNNING), "0")
        with self.assertRaises(RepoNotFound):
            self.svc.log_chunks(self.ctx["op.hml"], str(TCK_RUNNING))

    def test_dentro_do_escopo(self):
        r = self.svc.read_log(self.ctx["consulta"], str(TCK_RUNNING), "0")
        self.assertEqual(r["status"], "RUNNING")
        self.assertTrue(r["text"])

    def test_offset_alem_do_fim_retorna_vazio(self):
        r = self.svc.read_log(self.ctx["admin"], "35", "999999")
        self.assertEqual((r["text"], r["next_offset"]), ("", 999999))
        self.assertTrue(r["terminal"])


class TestReadLogContent(_BaseLog):

    def test_formato_da_resposta(self):
        r = self.svc.read_log(self.ctx["admin"], "17", "0")
        self.assertEqual(sorted(r), ["next_offset", "status", "terminal", "text", "truncated"])

    def test_limite_de_64k_e_reconstrucao_do_log_de_2mb(self):
        full = self._full_log(TCK_GRANDE)
        self.assertGreaterEqual(len(full.encode("utf-8")), 2 * 1024 * 1024)
        r = self.svc.read_log(self.ctx["admin"], str(TCK_GRANDE), "0")
        self.assertEqual(len(r["text"]), LOG_MAX_CHARS)
        self.assertEqual(LOG_MAX_CHARS, 65536)
        self.assertTrue(r["terminal"])
        text, last = self._read_all("admin", TCK_GRANDE)
        self.assertEqual(text, full)
        self.assertEqual(last["next_offset"], len(full))
        self.assertEqual(last["status"], "SUCCESS")

    def test_truncado_com_marcador_final(self):
        text, last = self._read_all("admin", TCK_TRUNCADO)
        self.assertTrue(last["truncated"])
        self.assertTrue(last["terminal"])
        self.assertTrue(text.endswith(MARKER_TRUNCATED))
        self.assertFalse(self.svc.read_log(self.ctx["admin"], "17", "0")["truncated"])

    def test_running_cresce_com_o_relogio_e_termina(self):
        text1, r1 = self._read_all("admin", TCK_RUNNING)
        self.assertFalse(r1["terminal"])
        self.assertEqual(r1["status"], "RUNNING")
        stage_current = 300 // STEP_13_S
        self.assertIn("etapa %d/%d processada" % (stage_current, STAGES), text1)
        self.assertNotIn("etapa %d/%d" % (stage_current + 1, STAGES), text1)

        # Sem avanco do relogio, nada novo.
        r = self.svc.read_log(self.ctx["admin"], str(TCK_RUNNING), str(r1["next_offset"]))
        self.assertEqual(r["text"], "")

        self.clock.advance(STEP_13_S)
        r2 = self.svc.read_log(self.ctx["admin"], str(TCK_RUNNING), str(r1["next_offset"]))
        self.assertIn("etapa %d/%d processada" % (stage_current + 1, STAGES), r2["text"])
        self.assertFalse(r2["terminal"])

        self.clock.advance(STAGES * STEP_13_S)
        r3 = self.svc.read_log(self.ctx["admin"], str(TCK_RUNNING), str(r2["next_offset"]))
        self.assertTrue(r3["terminal"])
        self.assertEqual(r3["status"], "SUCCESS")
        self.assertIn("etapa %d/%d processada" % (STAGES, STAGES), r3["text"])
        self.assertIn("Script concluido com retorno 0.", r3["text"])
        ticket = self.tickets.get(TCK_RUNNING)
        self.assertEqual((ticket["status_reason"], ticket["return_code"]), ("EXIT_OK", 0))
        self.assertEqual(ticket["finished_at"], self.clock())

        # Terminal e imutavel: o log nao cresce mais.
        self.clock.advance(3600)
        r4 = self.svc.read_log(self.ctx["admin"], str(TCK_RUNNING), str(r3["next_offset"]))
        self.assertEqual((r4["text"], r4["terminal"]), ("", True))

    def test_running_com_cancelamento_sinalizado_termina_cancelado(self):
        self.assertEqual(self.tickets.request_cancel(TCK_RUNNING, "admin", "10.0.0.1"), "SINALIZADO")
        text, last = self._read_all("admin", TCK_RUNNING)
        self.assertTrue(last["terminal"])
        self.assertEqual(last["status"], "CANCELLED")
        self.assertIn("cancelamento", text)
        self.assertEqual(self.tickets.get(TCK_RUNNING)["status_reason"], "CANCEL_USER")

    def test_segredo_mascarado(self):
        text, _ = self._read_all("admin", TCK_RUNNING)
        self.assertIn("conectando com documento_cliente=****", text)
        self.assertNotIn(SEED_SECRET, text)
        self.assertNotIn(SEED_SECRET, self._full_log(TCK_RUNNING))

    def test_html_preservado_como_texto(self):
        # O servidor entrega o texto cru; o cliente o exibe so por textContent (logViewer).
        text, _ = self._read_all("admin", TCK_RUNNING)
        self.assertIn("<script>alert(1)</script>", text)


class TestLogChunks(_BaseLog):

    def test_download_integro_do_log_de_2mb(self):
        full = self._full_log(TCK_GRANDE)
        tid, chunks = self.svc.log_chunks(self.ctx["admin"], str(TCK_GRANDE))
        self.assertEqual(tid, TCK_GRANDE)
        items = list(chunks)
        self.assertGreater(len(items), 1)
        self.assertTrue(all(len(b) <= LOG_MAX_CHARS for b in items))
        raw = b"".join(b.encode("utf-8") for b in items)
        self.assertEqual(raw.decode("utf-8"), full)

    def test_escopo_validado_antes_do_streaming(self):
        with mock.patch.object(self.tickets, "log_read") as log_read:
            with self.assertRaises(RepoNotFound):
                self.svc.log_chunks(self.ctx["op.hml"], str(TCK_RUNNING))
            log_read.assert_not_called()

    def test_falha_no_meio_encerra_com_marcador(self):
        original = self.tickets.log_read
        calls = []

        def falhar_na_segunda(*args, **kwargs):
            calls.append(args)
            if len(calls) == 2:
                raise RepoUnavailable("indisponivel")
            return original(*args, **kwargs)

        _tid, chunks = self.svc.log_chunks(self.ctx["admin"], str(TCK_GRANDE))
        with mock.patch.object(self.tickets, "log_read", side_effect=falhar_na_segunda):
            items = list(chunks)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[-1], DOWNLOAD_INTERRUPTED_MARKER)


if __name__ == "__main__":
    unittest.main()
