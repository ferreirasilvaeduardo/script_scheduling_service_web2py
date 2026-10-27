# -*- coding: utf-8 -*-
"""bin/sss-keepalive.sh (CR-030, P2): mantem os processos no ar pelo cron, sem root nem systemd."""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from tests.support import _testenv

BIN = os.path.join(_testenv.APP_DIR, "bin")
_SLEEPER = "import time\ntime.sleep(60)\n"


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


@unittest.skipIf(os.geteuid() == 0, "o comando recusa root")
class TestKeepalive(unittest.TestCase):

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="sss_test_keepalive_"))
        self.addCleanup(shutil.rmtree, self.root, True)
        for name in ("sss-keepalive.sh", "sss-scheduler.sh", "sss-web.sh"):
            os.makedirs(os.path.join(self.root, "bin"), exist_ok=True)
            shutil.copy2(os.path.join(BIN, name), os.path.join(self.root, "bin", name))
        _write(os.path.join(self.root, "scripts", "run_scheduler.py"), _SLEEPER)
        _write(os.path.join(self.root, "scripts", "run_web.py"), _SLEEPER)
        _write(os.path.join(self.root, "instance", "agente0001", "config.ini"), "[app]\n[agent]\n")
        _write(os.path.join(self.root, "instance", "web0001", "config.ini"), "[app]\n[web]\n")
        self.addCleanup(self._kill_all)

    def _kill_all(self):
        for proc in os.listdir("/proc"):
            if not proc.isdigit():
                continue
            try:
                if os.readlink("/proc/%s/cwd" % proc) == self.root:
                    os.kill(int(proc), signal.SIGKILL)
            except OSError:
                pass

    def _run(self, *args):
        env = dict(os.environ, PYTHON=sys.executable)
        command = [os.path.join(self.root, "bin", "sss-keepalive.sh")] + list(args)
        p = subprocess.run(command, cwd="/", env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=60)
        out, err = (b.decode("utf-8", "replace") for b in (p.stdout, p.stderr))
        return p.returncode, out, err

    def _log(self, name):
        path = os.path.join(self.root, "var", name, "logs", "keepalive.log")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return f.read().splitlines()

    def test_sobe_uma_vez_e_depois_so_confere(self):
        code, _out, err = self._run("agente0001", "web0001:18999")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self._log("agente0001")), 1)
        self.assertIn("subiu: pid", self._log("agente0001")[0])
        self.assertIn("--port 18999", self._log("web0001")[0])
        code, _out, err = self._run("agente0001", "web0001:18999")
        self.assertEqual(code, 0, err)
        self.assertEqual((len(self._log("agente0001")), len(self._log("web0001"))), (1, 1),
                         "ja no ar: nada a subir")

    def test_pausa_e_retomada(self):
        self.assertEqual(self._run("--pause", "agente0001")[0], 0)
        self.assertEqual(self._run("agente0001")[0], 0)
        self.assertFalse(any("subiu" in line for line in self._log("agente0001")))
        self.assertEqual(self._run("--resume", "agente0001")[0], 0)
        self.assertEqual(self._run("agente0001")[0], 0)
        self.assertIn("subiu: pid", self._log("agente0001")[-1])

    def test_recusas(self):
        self.assertEqual(self._run()[0], 2)
        self.assertEqual(self._run("Nome Ruim")[0], 2)
        code, _out, err = self._run("web0001")
        self.assertEqual(code, 3)
        self.assertIn("precisa da porta", err)
        code, _out, err = self._run("agente0009")
        self.assertEqual(code, 3)
        self.assertIn("nao existe", err)

    def test_processo_que_nao_sobe(self):
        _write(os.path.join(self.root, "scripts", "run_scheduler.py"), "import sys\nsys.exit(2)\n")
        code, _out, err = self._run("agente0001")
        self.assertEqual(code, 3, err)
        self.assertIn("falhou ao subir", self._log("agente0001")[-1])
        time.sleep(0.1)


if __name__ == "__main__":
    unittest.main()
