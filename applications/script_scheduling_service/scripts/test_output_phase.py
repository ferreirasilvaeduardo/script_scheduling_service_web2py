# -*- coding: utf-8 -*-
"""Fase de saida do agente (CR-012; README §8.7 e §8.13): maquina de estados com dubles e o laco real em DEV.

Sem banco: RepoSaidaMemoria segue o contrato do repo_oracle.scheduler_output (posse, offset esperado, parte ja
gravada, situacao final). O laco real roda scripts /bin/sh com o helper do pacote (sem sudo).
"""
import _testenv  # noqa: F401

import io
import os
import signal
import unittest
import zipfile
from unittest import mock

import output_phase
from _output_memory import RepoSaidaMemoria
from repo_oracle import scheduler_output

AGENTE = "srv-t"


class _Conn(object):
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _Popen(object):
    def __init__(self, rc=None):
        self.rc = rc

    def poll(self):
        return self.rc


class _Proc(object):
    def __init__(self, rc=None):
        self.popen = _Popen(rc)


class _Plat(object):
    SAIDA_VAZIA = 6
    SAIDA_EXCEDE_ARQUIVOS = 7
    SAIDA_EXCEDE_BYTES = 8

    def __init__(self, conteudo=None, rc=0):
        self.conteudo = conteudo
        self.rc = rc
        self.sinais = []
        self.limpas = []
        self.proc = None

    def iniciar_empacotar(self, base, relativo, max_bytes, max_arquivos, fd, usuario):
        if self.conteudo is not None:
            os.write(fd, self.conteudo)
        self.proc = _Proc(None)
        return self.proc

    def sinalizar_grupo(self, processo, sinal):
        self.sinais.append(sinal)
        return True

    def limpar_saida(self, base, relativo, usuario):
        self.limpas.append((base, relativo, usuario))


def _zip(arquivos):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    return buf.getvalue()


class TestMaquina(unittest.TestCase):

    def setUp(self):
        import tempfile
        import shutil
        self.work = tempfile.mkdtemp(prefix="sss_fase_")
        self.addCleanup(shutil.rmtree, self.work, True)
        self.saida = output_phase.Saida(7, "/s/producao", "carga/2026/10/20/14/05/ticket_7", None, self.work)
        self.repo = RepoSaidaMemoria({7: {"agent_id": AGENTE}})
        self.conn = _Conn()

    def _empacotar(self, plat, rc):
        output_phase.iniciar_empacotar(self.saida, plat, 1048576, 10, 100.0)
        self.assertFalse(output_phase.avancar_empacotar(self.saida, plat, 101.0), "ainda rodando: sem esperar")
        plat.proc.popen.rc = rc
        self.assertTrue(output_phase.avancar_empacotar(self.saida, plat, 102.0))

    def test_zip_gravado_em_partes_e_concluido(self):
        conteudo = _zip({"a.txt": os.urandom(5 * 1024 * 1024), "b.txt": b"x"})
        plat = _Plat(conteudo)
        self._empacotar(plat, 0)
        self.assertEqual((self.saida.resultado, self.saida.qtd_arquivos), (output_phase.ZIP, 2))
        self.assertEqual(self.saida.tamanho, len(conteudo))
        self.assertIsNone(output_phase.linha_log(self.saida, AGENTE, 10, 1048576))
        voltas = 0
        while True:
            voltas += 1
            desfecho = output_phase.gravar(self.saida, self.conn, self.repo, AGENTE)
            if desfecho != output_phase.CONTINUA:
                break
        self.assertEqual(desfecho, output_phase.CONCLUIDA)
        self.assertEqual(voltas, 2, "5 MiB em partes de 1 MiB, ate 4 por volta")
        linha = self.repo.linhas[7]
        self.assertEqual((linha["state"], linha["file_count"], linha["content"]), ("AVAILABLE", 2, conteudo))
        self.assertTrue(output_phase.deve_remover_pasta(self.saida))

    def test_vazia_excedeu_e_falhou(self):
        for rc, esperado in ((6, (output_phase.VAZIA, None)), (7, (output_phase.EXCEDEU, "FILES")),
                             (8, (output_phase.EXCEDEU, "BYTES")), (4, (output_phase.FALHOU, "ERROR"))):
            self.saida = output_phase.Saida(7, "/s/p", "c/2026/10/20/14/05/ticket_7", None, self.work)
            self.repo = RepoSaidaMemoria({7: {"agent_id": AGENTE}})
            with self.assertLogs("sss_scheduler", "WARNING") if rc == 4 else _nada():
                self._empacotar(_Plat(b""), rc)
            self.assertEqual((self.saida.resultado, self.saida.motivo), esperado, rc)
            self.assertEqual(output_phase.gravar(self.saida, self.conn, self.repo, AGENTE), output_phase.CONCLUIDA)
            if rc == 6:
                self.assertEqual(self.repo.linhas, {}, "pasta vazia nao grava linha")
                self.assertTrue(output_phase.deve_remover_pasta(self.saida))
            else:
                self.assertEqual(self.repo.linhas[7]["state"], esperado[0])
                self.assertFalse(output_phase.deve_remover_pasta(self.saida), "a pasta fica no disco")
        self.assertEqual(output_phase.linha_log(self.saida, AGENTE, 10, 1048576),
                         "saida nao empacotada: falha (agente srv-t)")
        s = output_phase.Saida(7, "/s", "c/2026/10/20/14/05/ticket_7", None, self.work)
        s.resultado, s.motivo = output_phase.EXCEDEU, "BYTES"
        self.assertEqual(output_phase.linha_log(s, AGENTE, 1000, 20 * 1024 * 1024),
                         "saida nao empacotada: excede o limite de 20 MiB (agente srv-t)")
        s.motivo = "FILES"
        self.assertIn("1000 arquivos", output_phase.linha_log(s, AGENTE, 1000, 20 * 1024 * 1024))

    def test_prazo_encerra_o_helper_sem_esperar(self):
        plat = _Plat(b"")
        output_phase.iniciar_empacotar(self.saida, plat, 1048576, 10, 0.0)
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertFalse(output_phase.avancar_empacotar(self.saida, plat, output_phase.PRAZO_EMPACOTAR_S + 1))
        self.assertEqual(plat.sinais, [signal.SIGKILL])
        self.assertFalse(output_phase.avancar_empacotar(self.saida, plat, output_phase.PRAZO_EMPACOTAR_S + 2))
        self.assertEqual(plat.sinais, [signal.SIGKILL], "um sinal so")
        plat.proc.popen.rc = -9
        self.assertTrue(output_phase.avancar_empacotar(self.saida, plat, output_phase.PRAZO_EMPACOTAR_S + 3))
        self.assertEqual((self.saida.resultado, self.saida.motivo), (output_phase.FALHOU, "DEADLINE"))

    def test_zip_ilegivel_e_falha_ao_iniciar(self):
        with self.assertLogs("sss_scheduler", "WARNING"):
            self._empacotar(_Plat(b"nao e zip"), 0)
        self.assertEqual((self.saida.resultado, self.saida.motivo), (output_phase.FALHOU, "ERROR"))
        s = output_phase.Saida(8, "/s", "c/2026/10/20/14/05/ticket_8", None, os.path.join(self.work, "nao_existe"))
        with self.assertLogs("sss_scheduler", "WARNING"):
            output_phase.iniciar_empacotar(s, _Plat(b""), 1, 1, 0.0)
        self.assertEqual((s.resultado, s.motivo), (output_phase.FALHOU, "ERROR"))

    def test_posse_perdida_e_commit_sem_resposta(self):
        plat = _Plat(_zip({"a": b"1"}))
        self._empacotar(plat, 0)
        self.repo.tickets[7]["agent_id"] = "outro"
        self.assertEqual(output_phase.gravar(self.saida, self.conn, self.repo, AGENTE), output_phase.POSSE_PERDIDA)
        # COMMIT do concluir sem resposta: a linha ja esta DISPONIVEL deste agente -> CONCLUIDA.
        self.repo.tickets[7]["agent_id"] = AGENTE
        self.repo.linhas[7] = {"state": "AVAILABLE", "agent_id": AGENTE}
        self.assertEqual(output_phase.gravar(self.saida, self.conn, self.repo, AGENTE), output_phase.CONCLUIDA)

    def test_erro_de_banco_rollback_e_retomada(self):
        conteudo = _zip({"a.txt": os.urandom(3 * 1024 * 1024)})
        self._empacotar(_Plat(conteudo), 0)
        self.repo.falhas = [("anexar", RuntimeError("ORA-03113"))]
        with self.assertRaises(RuntimeError):
            output_phase.gravar(self.saida, self.conn, self.repo, AGENTE)
        self.assertEqual(self.conn.rollbacks, 1)
        self.assertEqual(output_phase.gravar(self.saida, self.conn, self.repo, AGENTE), output_phase.CONCLUIDA)
        self.assertEqual(self.repo.linhas[7]["content"], conteudo)
        # Divergencia de offset: recomeca do inicio (o iniciar zera a gravacao deste agente).
        self.saida.iniciada, self.saida.offset = True, 0
        self.repo.linhas[7] = {"state": "WRITING", "agent_id": AGENTE, "content": b"xx"}
        with self.assertRaises(scheduler_output.SaidaOffsetInconsistente):
            output_phase.gravar(self.saida, self.conn, self.repo, AGENTE)
        self.assertFalse(self.saida.iniciada)
        self.assertEqual(output_phase.gravar(self.saida, self.conn, self.repo, AGENTE), output_phase.CONCLUIDA)
        self.assertEqual(self.repo.linhas[7]["content"], conteudo)

    def test_abandonar_encerra_o_helper(self):
        plat = _Plat(b"")
        output_phase.iniciar_empacotar(self.saida, plat, 1, 1, 0.0)
        output_phase.abandonar(self.saida, plat)
        self.assertEqual(plat.sinais, [signal.SIGKILL])
        self.assertEqual(self.saida.resultado, output_phase.ABANDONADA)
        self.assertFalse(output_phase.deve_remover_pasta(self.saida))


class _nada(object):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ---------------------------------------------------------------------------- laco real (DEV, helper do pacote)

import test_scheduler_claim as tsc  # noqa: E402


class TestLacoComSaida(tsc._Base):

    def setUp(self):
        tsc._Base.setUp(self)
        self.output_dir = os.path.join(self.raiz, "saida")
        os.mkdir(self.output_dir, 0o755)
        self.repo_saida = RepoSaidaMemoria(self.banco.tickets)

    def subir(self, **mudancas):
        mudancas.setdefault("output_dir", self.output_dir)
        mudancas.setdefault("output_max_files", 5)
        mudancas.setdefault("output_max_bytes", 1048576)
        return tsc._Base.subir(self, **mudancas)

    def _pasta_do_ticket(self, tid):
        for raiz, dirs, _arqs in os.walk(self.output_dir):
            if "ticket_%d" % tid in dirs:
                return os.path.join(raiz, "ticket_%d" % tid)
        return None

    def concluido(self, tid):
        return lambda: self.terminado(tid)() and tid not in self.ag.saidas

    def test_saida_disponivel_e_pasta_removida(self):
        sid = self.banco.script("echo resultado > \"$SSS_OUTPUT_DIR/r.txt\"\nmkdir \"$SSS_OUTPUT_DIR/sub\"\n"
                                "echo x > \"$SSS_OUTPUT_DIR/sub/y.csv\"\necho fim\n")
        tid = self.banco.ticket(sid)
        self.subir()
        self.rodar(self.concluido(tid))
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0))
        linha = self.repo_saida.linhas[tid]
        self.assertEqual((linha["state"], linha["file_count"]), ("AVAILABLE", 2))
        z = zipfile.ZipFile(io.BytesIO(linha["content"]))
        self.assertEqual(sorted(z.namelist()), ["r.txt", "sub/y.csv"])
        self.assertIsNone(self._pasta_do_ticket(tid), "pasta removida depois do zip gravado")
        self.assertNotIn("saida nao empacotada", self.banco.tickets[tid]["log"])
        self.assertFalse(os.path.exists(os.path.join(self.work, "ticket_%d" % tid)), "work_dir limpo no fim")

    def test_sem_arquivos_nada_e_gravado(self):
        tid = self.banco.ticket(self.banco.script("echo \"[$SSS_OUTPUT_DIR]\"\n"))
        self.subir()
        self.rodar(self.concluido(tid))
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0))
        self.assertNotIn(tid, self.repo_saida.linhas)
        self.assertIsNone(self._pasta_do_ticket(tid))
        self.assertIn("[%s/" % self.output_dir, self.banco.tickets[tid]["log"])

    def test_excesso_nao_muda_o_resultado_e_mantem_a_pasta(self):
        sid = self.banco.script("for i in 1 2 3 4 5 6; do echo $i > \"$SSS_OUTPUT_DIR/f$i\"; done\nexit 3\n")
        tid = self.banco.ticket(sid)
        self.subir()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.rodar(self.concluido(tid))
        self.assertEqual(self.final(tid), ("FAILED", "EXIT_ERROR", 3), "o resultado do script prevalece")
        self.assertEqual((self.repo_saida.linhas[tid]["state"], self.repo_saida.linhas[tid]["reason"]),
                         ("EXCEEDED", "FILES"))
        self.assertIn("[SSS] saida nao empacotada: excede o limite de 5 arquivos (agente srv-t)\n",
                      self.banco.tickets[tid]["log"])
        pasta = self._pasta_do_ticket(tid)
        self.assertEqual(len(os.listdir(pasta)), 6, "a pasta fica no disco do agente")

    def test_sem_saida_dir_sem_variavel(self):
        tid = self.banco.ticket(self.banco.script("echo \"[${SSS_OUTPUT_DIR:-ausente}]\"\n"))
        self.subir(output_dir=None)
        self.rodar(self.terminado(tid))
        self.assertIn("[ausente]", self.banco.tickets[tid]["log"])
        self.assertEqual(self.repo_saida.linhas, {})

    def test_erro_de_banco_na_gravacao_e_refeito(self):
        tid = self.banco.ticket(self.banco.script("echo r > \"$SSS_OUTPUT_DIR/r.txt\"\n"))
        self.repo_saida.falhas = [("iniciar", RuntimeError("ORA-03113"))]
        self.subir()
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.rodar(self.concluido(tid))
        self.assertTrue(any("gravacao da saida pendente" in l for l in logs.output))
        self.assertEqual(self.repo_saida.linhas[tid]["state"], "AVAILABLE")

    def test_parada_abandona_e_startup_marca_falhou(self):
        tid = self.banco.ticket(self.banco.script("echo r > \"$SSS_OUTPUT_DIR/r.txt\"\n"))
        self.repo_saida.falhas = [("anexar", RuntimeError("ORA-03113"))] * 50
        self.subir()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.rodar(lambda: self.terminado(tid)() and tid in self.repo_saida.linhas)
            self.assertEqual(self.repo_saida.linhas[tid]["state"], "WRITING")
            self.ag.encerrar_tudo("TERMINATE")
        self.assertEqual(self.ag.saidas, {})
        self.assertIsNotNone(self._pasta_do_ticket(tid), "pasta fica no disco")
        self.assertEqual(self.repo_saida.falhar_gravando_do_agente(None, "srv-t"), 1)
        self.assertEqual(self.repo_saida.linhas[tid]["state"], "FAILED")


if __name__ == "__main__":
    unittest.main()
