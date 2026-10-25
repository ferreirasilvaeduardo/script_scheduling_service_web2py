# -*- coding: utf-8 -*-
"""Entrega da pasta de entrada pela tela no agente (CR-020c, README §8.14): input_phase com repositorio falso e o
helper put-input de verdade (em DEV, com o proprio usuario)."""
from tests.support import _testenv  # noqa: F401
import hashlib
import os
import shutil
import tempfile
import time
import unittest

import input_phase
from sss.platform import os_platform
from sss.persistence.repo_errors import RepoNotFound

DATA = b"cliente;valor\n" + b"1;10\n" * 300000  # ~1,5 MiB: mais de uma parte


class _Repo(object):
    def __init__(self, data):
        self.data = data
        self.reads = []
        self.marks = []

    def read_content(self, upload_id, offset, size, conn=None):
        if self.data is None:
            raise RepoNotFound("sem conteudo")
        self.reads.append(offset)
        return self.data[offset:offset + size]

    def mark_delivery(self, delivery_id, agent_id, state, reason=None, conn=None):
        self.marks.append((delivery_id, agent_id, state, reason))
        return True


def _row(data, **extra):
    return dict({"id": 7, "upload_id": 3, "environment": "PRODUCAO", "script_id": 1, "script_name": "carga_diaria",
                 "relative_dir": "lotes", "file_name": u"relatório.csv", "size_bytes": len(data),
                 "sha256": hashlib.sha256(data).hexdigest(), "replace_existing": "N"}, **extra)


class TestInputPhase(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sss_entrada_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.work = os.path.join(self.root, "work")
        os.makedirs(self.work, 0o700)
        self.base = os.path.join(self.root, "input", "producao")
        os.makedirs(self.base, 0o700)
        input_phase.clean_leftovers(self.work)

    def _run(self, delivery, repo, deadline=30):
        """Avanca como o laco do agente: baixar, gravar (poll) e marcar."""
        limit = time.monotonic() + deadline
        while delivery.step == input_phase.DOWNLOAD:
            input_phase.download(delivery, None, repo)
        if delivery.step == input_phase.WRITE:
            input_phase.start_write(delivery, os_platform, self.base, "carga_diaria", None, time.monotonic())
            while delivery.step == input_phase.WRITE and not input_phase.advance_write(delivery, os_platform,
                                                                                       time.monotonic()):
                self.assertLess(time.monotonic(), limit)
                time.sleep(0.05)
        self.assertEqual(delivery.step, input_phase.MARK)
        self.assertTrue(input_phase.mark(delivery, None, repo, "agt"))
        input_phase.discard(delivery, os_platform)

    def test_baixa_em_partes_grava_pelo_helper_e_marca(self):
        repo = _Repo(DATA)
        d = input_phase.Delivery(_row(DATA), self.work)
        self._run(d, repo)
        self.assertEqual(repo.marks, [(7, "agt", "DELIVERED", None)])
        self.assertEqual(repo.reads[:2], [0, input_phase.PART_SIZE], "partes de 1 MiB")
        with open(os.path.join(self.base, "carga_diaria", "lotes", u"relatório.csv"), "rb") as f:
            self.assertEqual(f.read(), DATA)
        self.assertFalse(os.path.exists(d.part_path), "temporario apagado")

    def test_ja_existe_sem_substituir(self):
        self._run(input_phase.Delivery(_row(b"um"), self.work), _Repo(b"um"))
        repo = _Repo(b"dois")
        self._run(input_phase.Delivery(_row(b"dois", id=8), self.work), repo)
        self.assertEqual(repo.marks, [(8, "agt", "FAILED", "EXISTS")])
        repo = _Repo(b"dois")
        self._run(input_phase.Delivery(_row(b"dois", id=9, replace_existing="Y"), self.work), repo)
        self.assertEqual(repo.marks, [(9, "agt", "DELIVERED", None)])

    def test_hash_do_banco_divergente_nao_chega_ao_helper(self):
        repo = _Repo(b"conteudo alterado")
        d = input_phase.Delivery(_row(b"conteudo original"), self.work)
        self._run(d, repo)
        self.assertEqual(repo.marks, [(7, "agt", "FAILED", "HASH")])
        self.assertFalse(os.path.exists(os.path.join(self.base, "carga_diaria")))

    def test_nome_recusado_pelo_helper_e_conteudo_esvaziado(self):
        repo = _Repo(b"x")
        self._run(input_phase.Delivery(_row(b"x", relative_dir="../fora"), self.work), repo)
        self.assertEqual(repo.marks[-1][2:], ("FAILED", "NAME"))
        repo = _Repo(None)
        self._run(input_phase.Delivery(_row(b"x", id=10), self.work), repo)
        self.assertEqual(repo.marks[-1], (10, "agt", "FAILED", "ERROR"))

    def test_temporarios_que_sobraram_sao_apagados(self):
        folder = input_phase.work_folder(self.work)
        for name in ("delivery_1.part", "delivery_2.part", "outro.txt"):
            open(os.path.join(folder, name), "w").close()
        self.assertEqual(input_phase.clean_leftovers(self.work), 2)
        self.assertEqual(os.listdir(folder), ["outro.txt"])


class TestDaemonSemWeb2py(unittest.TestCase):

    def test_o_daemon_importa_a_entrada_sem_gluon(self):
        """Regressao do ensaio do CR-020c: o agente nao sobe se o repositorio da entrada carregar o web2py."""
        import subprocess
        import sys
        paths = [os.path.join(_testenv.APP_DIR, "modules"), os.path.join(_testenv.APP_DIR, "src")]
        code = ("import sys; sys.path[:0] = %r; import scheduler_loop, sss.persistence.oracle.scheduler_input; "
                "sys.exit(1 if 'gluon' in sys.modules else 0)" % paths)
        p = subprocess.run([sys.executable, "-I", "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace")[-500:])


if __name__ == "__main__":
    unittest.main()
