# -*- coding: utf-8 -*-
"""Fase de saida do agente (CR-012; README §8.7 e §8.13): maquina de estados com dubles e o laco real em DEV.

Sem banco: RepoOutputMemory segue o contrato do repo_oracle.scheduler_output (posse, offset esperado, parte ja
gravada, situacao final). O laco real roda scripts /bin/sh com o helper do pacote (sem sudo).
"""
from tests.support import _testenv  # noqa: F401

import io
import os
import signal
import unittest
import zipfile
from unittest import mock

from sss.scheduler import output_phase
from tests.support._output_memory import RepoOutputMemory
from sss.persistence.oracle import scheduler_output

AGENT = "srv-t"


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
    OUTPUT_EMPTY = 6
    OUTPUT_TOO_MANY_FILES = 7
    OUTPUT_TOO_MANY_BYTES = 8

    def __init__(self, content=None, rc=0):
        self.content = content
        self.rc = rc
        self.signals = []
        self.cleaned = []
        self.proc = None

    def start_pack(self, base, relative, max_bytes, max_files, fd):
        if self.content is not None:
            os.write(fd, self.content)
        self.proc = _Proc(None)
        return self.proc

    def signal_group(self, process, signal_value):
        self.signals.append(signal_value)
        return True

    def clean_output(self, base, relative):
        self.cleaned.append((base, relative))


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


class TestStateMachine(unittest.TestCase):

    def setUp(self):
        import tempfile
        import shutil
        self.work = tempfile.mkdtemp(prefix="sss_fase_")
        self.addCleanup(shutil.rmtree, self.work, True)
        self.output = output_phase.Output(7, "/s/producao", "carga/2026/10/20/14/05/ticket_7", self.work)
        self.repo = RepoOutputMemory({7: {"agent_id": AGENT}})
        self.conn = _Conn()

    def _pack(self, plat, rc):
        output_phase.start_pack(self.output, plat, 1048576, 10, 100.0)
        self.assertFalse(output_phase.advance_pack(self.output, plat, 101.0), "ainda rodando: sem esperar")
        plat.proc.popen.rc = rc
        self.assertTrue(output_phase.advance_pack(self.output, plat, 102.0))

    def test_zip_gravado_em_partes_e_concluido(self):
        content = _zip({"a.txt": os.urandom(5 * 1024 * 1024), "b.txt": b"x"})
        plat = _Plat(content)
        self._pack(plat, 0)
        self.assertEqual((self.output.result, self.output.file_count), (output_phase.ZIP, 2))
        self.assertEqual(self.output.size, len(content))
        self.assertIsNone(output_phase.log_line(self.output, AGENT, 10, 1048576))
        rounds = 0
        while True:
            rounds += 1
            outcome = output_phase.write(self.output, self.conn, self.repo, AGENT)
            if outcome != output_phase.CONTINUE:
                break
        self.assertEqual(outcome, output_phase.DONE)
        self.assertEqual(rounds, 2, "5 MiB em partes de 1 MiB, ate 4 por volta")
        line = self.repo.rows[7]
        self.assertEqual((line["state"], line["file_count"], line["content"]), ("AVAILABLE", 2, content))
        self.assertTrue(output_phase.should_remove_dir(self.output))

    def test_vazia_excedeu_e_falhou(self):
        for rc, expected in ((6, (output_phase.EMPTY, None)), (7, (output_phase.EXCEEDED, "FILES")),
                             (8, (output_phase.EXCEEDED, "BYTES")), (4, (output_phase.FAILED, "ERROR"))):
            self.output = output_phase.Output(7, "/s/p", "c/2026/10/20/14/05/ticket_7", self.work)
            self.repo = RepoOutputMemory({7: {"agent_id": AGENT}})
            with self.assertLogs("sss_scheduler", "WARNING") if rc == 4 else _nothing():
                self._pack(_Plat(b""), rc)
            self.assertEqual((self.output.result, self.output.reason), expected, rc)
            self.assertEqual(output_phase.write(self.output, self.conn, self.repo, AGENT), output_phase.DONE)
            if rc == 6:
                self.assertEqual(self.repo.rows, {}, "pasta vazia nao grava linha")
                self.assertTrue(output_phase.should_remove_dir(self.output))
            else:
                self.assertEqual(self.repo.rows[7]["state"], expected[0])
                self.assertFalse(output_phase.should_remove_dir(self.output), "a pasta fica no disco")
        self.assertEqual(output_phase.log_line(self.output, AGENT, 10, 1048576),
                         "saida nao empacotada: falha (agente srv-t)")
        s = output_phase.Output(7, "/s", "c/2026/10/20/14/05/ticket_7", self.work)
        s.result, s.reason = output_phase.EXCEEDED, "BYTES"
        self.assertEqual(output_phase.log_line(s, AGENT, 1000, 20 * 1024 * 1024),
                         "saida nao empacotada: excede o limite de 20 MiB (agente srv-t)")
        s.reason = "FILES"
        self.assertIn("1000 arquivos", output_phase.log_line(s, AGENT, 1000, 20 * 1024 * 1024))

    def test_prazo_encerra_o_helper_sem_esperar(self):
        plat = _Plat(b"")
        output_phase.start_pack(self.output, plat, 1048576, 10, 0.0)
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertFalse(output_phase.advance_pack(self.output, plat, output_phase.PACK_DEADLINE_S + 1))
        self.assertEqual(plat.signals, [signal.SIGKILL])
        self.assertFalse(output_phase.advance_pack(self.output, plat, output_phase.PACK_DEADLINE_S + 2))
        self.assertEqual(plat.signals, [signal.SIGKILL], "um sinal so")
        plat.proc.popen.rc = -9
        self.assertTrue(output_phase.advance_pack(self.output, plat, output_phase.PACK_DEADLINE_S + 3))
        self.assertEqual((self.output.result, self.output.reason), (output_phase.FAILED, "DEADLINE"))

    def test_zip_ilegivel_e_falha_ao_iniciar(self):
        with self.assertLogs("sss_scheduler", "WARNING"):
            self._pack(_Plat(b"nao e zip"), 0)
        self.assertEqual((self.output.result, self.output.reason), (output_phase.FAILED, "ERROR"))
        s = output_phase.Output(8, "/s", "c/2026/10/20/14/05/ticket_8", os.path.join(self.work, "nao_existe"))
        with self.assertLogs("sss_scheduler", "WARNING"):
            output_phase.start_pack(s, _Plat(b""), 1, 1, 0.0)
        self.assertEqual((s.result, s.reason), (output_phase.FAILED, "ERROR"))

    def test_posse_perdida_e_commit_sem_resposta(self):
        plat = _Plat(_zip({"a": b"1"}))
        self._pack(plat, 0)
        self.repo.tickets[7]["agent_id"] = "outro"
        self.assertEqual(output_phase.write(self.output, self.conn, self.repo, AGENT), output_phase.OWNERSHIP_LOST)
        # COMMIT do concluir sem resposta: a linha ja esta DISPONIVEL deste agente -> CONCLUIDA.
        self.repo.tickets[7]["agent_id"] = AGENT
        self.repo.rows[7] = {"state": "AVAILABLE", "agent_id": AGENT}
        self.assertEqual(output_phase.write(self.output, self.conn, self.repo, AGENT), output_phase.DONE)

    def test_erro_de_banco_rollback_e_retomada(self):
        content = _zip({"a.txt": os.urandom(3 * 1024 * 1024)})
        self._pack(_Plat(content), 0)
        self.repo.failures = [("append_chunk", RuntimeError("ORA-03113"))]
        with self.assertRaises(RuntimeError):
            output_phase.write(self.output, self.conn, self.repo, AGENT)
        self.assertEqual(self.conn.rollbacks, 1)
        self.assertEqual(output_phase.write(self.output, self.conn, self.repo, AGENT), output_phase.DONE)
        self.assertEqual(self.repo.rows[7]["content"], content)
        # Divergencia de offset: recomeca do inicio (o iniciar zera a gravacao deste agente).
        self.output.started, self.output.offset = True, 0
        self.repo.rows[7] = {"state": "WRITING", "agent_id": AGENT, "content": b"xx"}
        with self.assertRaises(scheduler_output.OutputOffsetMismatch):
            output_phase.write(self.output, self.conn, self.repo, AGENT)
        self.assertFalse(self.output.started)
        self.assertEqual(output_phase.write(self.output, self.conn, self.repo, AGENT), output_phase.DONE)
        self.assertEqual(self.repo.rows[7]["content"], content)

    def test_abandonar_encerra_o_helper(self):
        plat = _Plat(b"")
        output_phase.start_pack(self.output, plat, 1, 1, 0.0)
        output_phase.abandon(self.output, plat)
        self.assertEqual(plat.signals, [signal.SIGKILL])
        self.assertEqual(self.output.result, output_phase.ABANDONED)
        self.assertFalse(output_phase.should_remove_dir(self.output))


class _nothing(object):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ---------------------------------------------------------------------------- laco real (DEV, helper do pacote)

from tests.unit.scheduler import test_scheduler_claim as tsc  # noqa: E402


class TestLoopWithOutput(tsc._Base):

    def setUp(self):
        tsc._Base.setUp(self)
        self.output_dir = os.path.join(self.root, "saida")
        os.mkdir(self.output_dir, 0o755)
        self.repo_output = RepoOutputMemory(self.db.tickets)

    def start_agent(self, **changes):
        changes.setdefault("output_dir", self.output_dir)
        changes.setdefault("output_max_files", 5)
        changes.setdefault("output_max_bytes", 1048576)
        return tsc._Base.start_agent(self, **changes)

    def _ticket_dir(self, tid):
        for root, dirs, _arqs in os.walk(self.output_dir):
            if "ticket_%d" % tid in dirs:
                return os.path.join(root, "ticket_%d" % tid)
        return None

    def completed(self, tid):
        return lambda: self.finished(tid)() and tid not in self.ag.outputs

    def test_saida_disponivel_e_pasta_removida(self):
        sid = self.db.script("echo resultado > \"$SSS_OUTPUT_DIR/r.txt\"\nmkdir \"$SSS_OUTPUT_DIR/sub\"\n"
                                "echo x > \"$SSS_OUTPUT_DIR/sub/y.csv\"\necho fim\n")
        tid = self.db.ticket(sid)
        self.start_agent()
        self.run_loop(self.completed(tid))
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0))
        line = self.repo_output.rows[tid]
        self.assertEqual((line["state"], line["file_count"]), ("AVAILABLE", 2))
        z = zipfile.ZipFile(io.BytesIO(line["content"]))
        self.assertEqual(sorted(z.namelist()), ["r.txt", "sub/y.csv"])
        self.assertIsNone(self._ticket_dir(tid), "pasta removida depois do zip gravado")
        self.assertNotIn("saida nao empacotada", self.db.tickets[tid]["log"])
        self.assertFalse(os.path.exists(os.path.join(self.work, "ticket_%d" % tid)), "work_dir limpo no fim")

    def test_sem_arquivos_nada_e_gravado(self):
        tid = self.db.ticket(self.db.script("echo \"[$SSS_OUTPUT_DIR]\"\n"))
        self.start_agent()
        self.run_loop(self.completed(tid))
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0))
        self.assertNotIn(tid, self.repo_output.rows)
        self.assertIsNone(self._ticket_dir(tid))
        self.assertIn("[%s/" % self.output_dir, self.db.tickets[tid]["log"])

    def test_excesso_nao_muda_o_resultado_e_mantem_a_pasta(self):
        sid = self.db.script("for i in 1 2 3 4 5 6; do echo $i > \"$SSS_OUTPUT_DIR/f$i\"; done\nexit 3\n")
        tid = self.db.ticket(sid)
        self.start_agent()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.run_loop(self.completed(tid))
        self.assertEqual(self.final(tid), ("FAILED", "EXIT_ERROR", 3), "o resultado do script prevalece")
        self.assertEqual((self.repo_output.rows[tid]["state"], self.repo_output.rows[tid]["reason"]),
                         ("EXCEEDED", "FILES"))
        self.assertIn("[SSS] saida nao empacotada: excede o limite de 5 arquivos (agente srv-t)\n",
                      self.db.tickets[tid]["log"])
        dir_value = self._ticket_dir(tid)
        self.assertEqual(len(os.listdir(dir_value)), 6, "a pasta fica no disco do agente")

    def test_sem_saida_dir_sem_variavel(self):
        tid = self.db.ticket(self.db.script("echo \"[${SSS_OUTPUT_DIR:-ausente}]\"\n"))
        self.start_agent(output_dir=None)
        self.run_loop(self.finished(tid))
        self.assertIn("[ausente]", self.db.tickets[tid]["log"])
        self.assertEqual(self.repo_output.rows, {})

    def test_erro_de_banco_na_gravacao_e_refeito(self):
        tid = self.db.ticket(self.db.script("echo r > \"$SSS_OUTPUT_DIR/r.txt\"\n"))
        self.repo_output.failures = [("start", RuntimeError("ORA-03113"))]
        self.start_agent()
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.run_loop(self.completed(tid))
        self.assertTrue(any("gravacao da saida pendente" in l for l in logs.output))
        self.assertEqual(self.repo_output.rows[tid]["state"], "AVAILABLE")

    def test_parada_abandona_e_startup_marca_falhou(self):
        tid = self.db.ticket(self.db.script("echo r > \"$SSS_OUTPUT_DIR/r.txt\"\n"))
        self.repo_output.failures = [("append_chunk", RuntimeError("ORA-03113"))] * 50
        self.start_agent()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.run_loop(lambda: self.finished(tid)() and tid in self.repo_output.rows)
            self.assertEqual(self.repo_output.rows[tid]["state"], "WRITING")
            self.ag.stop_all("TERMINATE")
        self.assertEqual(self.ag.outputs, {})
        self.assertIsNotNone(self._ticket_dir(tid), "pasta fica no disco")
        self.assertEqual(self.repo_output.fail_agent_writing(None, "srv-t"), 1)
        self.assertEqual(self.repo_output.rows[tid]["state"], "FAILED")


if __name__ == "__main__":
    unittest.main()
