# -*- coding: utf-8 -*-
"""Testes da logica por tras de logs/chunk e logs/baixar (F3.4): ticket_service.ler_log e blocos_log."""
import _testenv  # noqa: F401

import datetime
import logging
import os
import unittest
from unittest import mock

import auth_service
import repo_factory
import security
from repo_errors import RepoIndisponivel, RepoNaoEncontrado
from ticket_service import LOG_MAX_CHARS, MARCADOR_DOWNLOAD_INTERROMPIDO, OffsetInvalido, ServicoTicket

SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1},
    "op.hml": {"usuario_id": 3, "login": "op.hml", "perfil_id": 3, "perm_versao": 1},
    "consulta": {"usuario_id": 4, "login": "consulta", "perfil_id": 4, "perm_versao": 1},
}
# Seed FAKE: 13 RUNNING (PRODUCAO, op.prod, carga_diaria com documento_cliente sensivel, 8 s/etapa),
# 17 SUCCESS com log de ~2 MB, 35 FAILED/LOG_LIMIT com log_truncado = 'S'.
TCK_RUNNING, TCK_GRANDE, TCK_TRUNCADO = 13, 17, 35
PASSO_13_S = 8
ETAPAS = 50
SEGREDO_SEED = "00011122233"
# README §8.10.
MARCADOR_TRUNCADO = "[SSS] log truncado no banco; arquivo integral no agente\n"


class _Relogio(object):

    def __init__(self, instante):
        self.instante = instante

    def __call__(self):
        return self.instante

    def avancar(self, segundos):
        self.instante += datetime.timedelta(seconds=segundos)


class _BaseLog(unittest.TestCase):

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

        catalogo = repo_factory.obter("catalogo")
        self.tickets = repo_factory.obter("tickets")
        # Congela o relogio no instante da carga do seed (started_at do RUNNING + 5 min).
        inicio = self.tickets.obter(TCK_RUNNING)["started_at"]
        self.relogio = _Relogio(inicio + datetime.timedelta(minutes=5))
        repo_factory._fake_store.definir_relogio(self.relogio)

        self.log = logging.getLogger("sss_teste_logs")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        auth = auth_service.ServicoAuth(
            repo_factory.obter("usuarios"), repo_factory.obter("rbac"), catalogo,
            repo_factory.obter("auditoria"), 5, 900, self.log)
        self.ctx = dict((login, auth.revalidar(sessao)) for login, sessao in SESSOES.items())
        self.svc = ServicoTicket(catalogo, self.tickets, (os.geteuid(),), self.log)

    def _ler_tudo(self, login, ticket_id):
        partes = []
        offset = 0
        while True:
            r = self.svc.ler_log(self.ctx[login], str(ticket_id), str(offset))
            self.assertLessEqual(len(r["texto"]), LOG_MAX_CHARS)
            self.assertEqual(r["proximo_offset"], offset + len(r["texto"]))
            if not r["texto"]:
                return "".join(partes), r
            partes.append(r["texto"])
            offset = r["proximo_offset"]


class TestLerLogValidacao(_BaseLog):

    def test_offset_invalido(self):
        for invalido in ("-1", "x", "", "1.5", " 1", "12345678901", None, -1, True, 1.0, ["a"]):
            with self.assertRaises(OffsetInvalido, msg=repr(invalido)):
                self.svc.ler_log(self.ctx["admin"], "17", invalido)

    def test_offset_valido_em_lista_vale_o_ultimo(self):
        r = self.svc.ler_log(self.ctx["admin"], "17", ["0", "10"])
        self.assertEqual(r["proximo_offset"], 10 + len(r["texto"]))

    def test_ticket_inexistente_ou_id_invalido_e_404(self):
        for tid in ("999", "0", "abc", None, "-3"):
            with self.assertRaises(RepoNaoEncontrado, msg=repr(tid)):
                self.svc.ler_log(self.ctx["admin"], tid, "0")

    def test_fora_do_escopo_e_404(self):
        # op.hml enxerga HOMOLOGACAO/DESENV e seus proprios; o 13 e PRODUCAO de op.prod.
        with self.assertRaises(RepoNaoEncontrado):
            self.svc.ler_log(self.ctx["op.hml"], str(TCK_RUNNING), "0")
        with self.assertRaises(RepoNaoEncontrado):
            self.svc.blocos_log(self.ctx["op.hml"], str(TCK_RUNNING))

    def test_dentro_do_escopo(self):
        r = self.svc.ler_log(self.ctx["consulta"], str(TCK_RUNNING), "0")
        self.assertEqual(r["status"], "RUNNING")
        self.assertTrue(r["texto"])

    def test_offset_alem_do_fim_retorna_vazio(self):
        r = self.svc.ler_log(self.ctx["admin"], "35", "999999")
        self.assertEqual((r["texto"], r["proximo_offset"]), ("", 999999))
        self.assertTrue(r["terminal"])


class TestLerLogConteudo(_BaseLog):

    def test_formato_da_resposta(self):
        r = self.svc.ler_log(self.ctx["admin"], "17", "0")
        self.assertEqual(sorted(r), ["proximo_offset", "status", "terminal", "texto", "truncado"])

    def test_limite_de_64k_e_reconstrucao_do_log_de_2mb(self):
        integral = self.tickets.obter(TCK_GRANDE)["log_output"]
        self.assertGreaterEqual(len(integral.encode("utf-8")), 2 * 1024 * 1024)
        r = self.svc.ler_log(self.ctx["admin"], str(TCK_GRANDE), "0")
        self.assertEqual(len(r["texto"]), LOG_MAX_CHARS)
        self.assertEqual(LOG_MAX_CHARS, 65536)
        self.assertTrue(r["terminal"])
        texto, ultima = self._ler_tudo("admin", TCK_GRANDE)
        self.assertEqual(texto, integral)
        self.assertEqual(ultima["proximo_offset"], len(integral))
        self.assertEqual(ultima["status"], "SUCCESS")

    def test_truncado_com_marcador_final(self):
        texto, ultima = self._ler_tudo("admin", TCK_TRUNCADO)
        self.assertTrue(ultima["truncado"])
        self.assertTrue(ultima["terminal"])
        self.assertTrue(texto.endswith(MARCADOR_TRUNCADO))
        self.assertFalse(self.svc.ler_log(self.ctx["admin"], "17", "0")["truncado"])

    def test_running_cresce_com_o_relogio_e_termina(self):
        texto1, r1 = self._ler_tudo("admin", TCK_RUNNING)
        self.assertFalse(r1["terminal"])
        self.assertEqual(r1["status"], "RUNNING")
        etapa_atual = 300 // PASSO_13_S
        self.assertIn("etapa %d/%d processada" % (etapa_atual, ETAPAS), texto1)
        self.assertNotIn("etapa %d/%d" % (etapa_atual + 1, ETAPAS), texto1)

        # Sem avanco do relogio, nada novo.
        r = self.svc.ler_log(self.ctx["admin"], str(TCK_RUNNING), str(r1["proximo_offset"]))
        self.assertEqual(r["texto"], "")

        self.relogio.avancar(PASSO_13_S)
        r2 = self.svc.ler_log(self.ctx["admin"], str(TCK_RUNNING), str(r1["proximo_offset"]))
        self.assertIn("etapa %d/%d processada" % (etapa_atual + 1, ETAPAS), r2["texto"])
        self.assertFalse(r2["terminal"])

        self.relogio.avancar(ETAPAS * PASSO_13_S)
        r3 = self.svc.ler_log(self.ctx["admin"], str(TCK_RUNNING), str(r2["proximo_offset"]))
        self.assertTrue(r3["terminal"])
        self.assertEqual(r3["status"], "SUCCESS")
        self.assertIn("etapa %d/%d processada" % (ETAPAS, ETAPAS), r3["texto"])
        self.assertIn("Script concluido com retorno 0.", r3["texto"])
        ticket = self.tickets.obter(TCK_RUNNING)
        self.assertEqual((ticket["status_motivo"], ticket["return_code"]), ("EXIT_OK", 0))
        self.assertEqual(ticket["finished_at"], self.relogio())

        # Terminal e imutavel: o log nao cresce mais.
        self.relogio.avancar(3600)
        r4 = self.svc.ler_log(self.ctx["admin"], str(TCK_RUNNING), str(r3["proximo_offset"]))
        self.assertEqual((r4["texto"], r4["terminal"]), ("", True))

    def test_running_com_cancelamento_sinalizado_termina_cancelado(self):
        self.assertEqual(self.tickets.solicitar_cancelamento(TCK_RUNNING, "admin", "10.0.0.1"), "SINALIZADO")
        texto, ultima = self._ler_tudo("admin", TCK_RUNNING)
        self.assertTrue(ultima["terminal"])
        self.assertEqual(ultima["status"], "CANCELLED")
        self.assertIn("cancelamento", texto)
        self.assertEqual(self.tickets.obter(TCK_RUNNING)["status_motivo"], "CANCEL_USER")

    def test_segredo_mascarado(self):
        texto, _ = self._ler_tudo("admin", TCK_RUNNING)
        self.assertIn("conectando com documento_cliente=****", texto)
        self.assertNotIn(SEGREDO_SEED, texto)
        self.assertNotIn(SEGREDO_SEED, self.tickets.obter(TCK_RUNNING)["log_output"])

    def test_html_preservado_como_texto(self):
        # O servidor entrega o texto cru; o escape e responsabilidade do x-text no cliente.
        texto, _ = self._ler_tudo("admin", TCK_RUNNING)
        self.assertIn("<script>alert(1)</script>", texto)


class TestBlocosLog(_BaseLog):

    def test_download_integro_do_log_de_2mb(self):
        integral = self.tickets.obter(TCK_GRANDE)["log_output"]
        tid, blocos = self.svc.blocos_log(self.ctx["admin"], str(TCK_GRANDE))
        self.assertEqual(tid, TCK_GRANDE)
        lista = list(blocos)
        self.assertGreater(len(lista), 1)
        self.assertTrue(all(len(b) <= LOG_MAX_CHARS for b in lista))
        bruto = b"".join(b.encode("utf-8") for b in lista)
        self.assertEqual(bruto.decode("utf-8"), integral)

    def test_escopo_validado_antes_do_streaming(self):
        with mock.patch.object(self.tickets, "log_ler") as log_ler:
            with self.assertRaises(RepoNaoEncontrado):
                self.svc.blocos_log(self.ctx["op.hml"], str(TCK_RUNNING))
            log_ler.assert_not_called()

    def test_falha_no_meio_encerra_com_marcador(self):
        original = self.tickets.log_ler
        chamadas = []

        def falhar_na_segunda(*args, **kwargs):
            chamadas.append(args)
            if len(chamadas) == 2:
                raise RepoIndisponivel("indisponivel")
            return original(*args, **kwargs)

        _tid, blocos = self.svc.blocos_log(self.ctx["admin"], str(TCK_GRANDE))
        with mock.patch.object(self.tickets, "log_ler", side_effect=falhar_na_segunda):
            lista = list(blocos)
        self.assertEqual(len(lista), 2)
        self.assertEqual(lista[-1], MARCADOR_DOWNLOAD_INTERROMPIDO)


if __name__ == "__main__":
    unittest.main()
