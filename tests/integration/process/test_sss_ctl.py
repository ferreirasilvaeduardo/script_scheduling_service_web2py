# -*- coding: utf-8 -*-
"""bin/sss-ctl.sh: status, stop, start e o bloco do crontab de uma raiz (DEPLOYMENT-SERVER,
passos 12, 14 e 15)."""
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import unittest

from tests.support import _testenv

BIN = os.path.join(_testenv.APP_DIR, "bin")
# Agente falso: cria o works/ (como o real, na subida) e sai quando o sss-stop.sh cria o .stop.
_AGENT = ("import os, sys, time\n"
          "name = sys.argv[sys.argv.index('--name') + 1]\n"
          "stop = os.path.join('var', name, 'works', 'sss-%s.stop' % name)\n"
          "os.makedirs(os.path.dirname(stop), exist_ok=True)\n"
          "for _ in range(600):\n"
          "    if os.path.exists(stop):\n"
          "        os.remove(stop)\n"
          "        sys.exit(0)\n"
          "    time.sleep(0.1)\n")
_WEB = "import time\ntime.sleep(60)\n"
# crontab falso: -l le e "-" grava o arquivo de CRONTAB_FILE (o crontab da conta de quem roda os
# testes nao e tocado).
_CRONTAB = ('#!/bin/bash\n'
            'if [ "$1" = "-l" ]; then\n'
            '    [ -f "$CRONTAB_FILE" ] || exit 1; cat "$CRONTAB_FILE"; exit 0\n'
            'fi\n'
            'if [ "$1" = "-" ]; then cat > "$CRONTAB_FILE"; exit 0; fi\n'
            'exit 2\n')


def _write(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    if mode:
        os.chmod(path, mode)


@unittest.skipIf(os.geteuid() == 0, "o comando recusa root")
class TestSssCtl(unittest.TestCase):

    def setUp(self):
        self.base = os.path.realpath(tempfile.mkdtemp(prefix="sss_test_ctl_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        # <base>/DEV/script_scheduling_service: o tipo vem da pasta acima da raiz.
        self.root = os.path.join(self.base, "DEV", "script_scheduling_service")
        for name in ("sss-ctl.sh", "sss-keepalive.sh", "sss-scheduler.sh", "sss-web.sh",
                     "sss-stop.sh"):
            os.makedirs(os.path.join(self.root, "bin"), exist_ok=True)
            shutil.copy2(os.path.join(BIN, name), os.path.join(self.root, "bin", name))
        _write(os.path.join(self.root, "scripts", "run_scheduler.py"), _AGENT)
        _write(os.path.join(self.root, "scripts", "run_web.py"), _WEB)
        _write(os.path.join(self.root, "instance", "web0001", "config.ini"),
               "[app]\nname = web0001\n[web]\nallowed_origins = http://127.0.0.1:18997 ; local\n")
        for name, env in (("agente0001", "GFPREPROD"), ("agente0002", "CLONE2")):
            _write(os.path.join(self.root, "instance", name, "config.ini"),
                   "[app]\nname = %s\n[agent]\nenvironments = %s\n" % (name, env))
        self.fakebin = os.path.join(self.base, "fakebin")
        _write(os.path.join(self.fakebin, "crontab"), _CRONTAB, stat.S_IRWXU)
        self.cron_file = os.path.join(self.base, "crontab.txt")
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

    def _run(self, *args, **env_extra):
        env = dict(os.environ, PYTHON=sys.executable, SSS_STOP_WAIT_S="20",
                   CRONTAB_FILE=self.cron_file,
                   PATH=self.fakebin + os.pathsep + os.environ.get("PATH", ""))
        env.update(env_extra)
        p = subprocess.run([os.path.join(self.root, "bin", "sss-ctl.sh")] + list(args), cwd="/",
                           env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
        out, err = (b.decode("utf-8", "replace") for b in (p.stdout, p.stderr))
        return p.returncode, out, err

    def _keepalive_log(self):
        path = os.path.join(self.root, "var", "web0001", "logs", "keepalive.log")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def _crontab(self):
        if not os.path.exists(self.cron_file):
            return ""
        with open(self.cron_file, encoding="utf-8") as f:
            return f.read()

    def test_start_status_stop_e_start_de_novo(self):
        code, out, err = self._run("status")
        self.assertEqual(code, 0, err)
        self.assertIn("tipo=DEV", out)
        for name in ("web0001", "agente0001", "agente0002"):
            self.assertRegex(out, r"%s\s+parado" % name)
        code, _out, err = self._run("start")
        self.assertEqual(code, 0, err)
        self.assertIn("--host 127.0.0.1 --port 18997", self._keepalive_log(),
                      "porta do allowed_origins, so local")
        code, out, _err = self._run("status")
        for name in ("web0001", "agente0001", "agente0002"):
            self.assertRegex(out, r"%s\s+no ar \(pid \d+\)" % name)
        self.assertEqual(self._run("start")[0], 0, "ja no ar: nada a subir")
        self.assertEqual(out.count("no ar"), self._run("status")[1].count("no ar"),
                         "sem processo em dobro")
        code, out, err = self._run("stop")
        self.assertEqual(code, 0, err)
        self.assertIn("parado:", out)
        code, out, _err = self._run("status")
        for name in ("web0001", "agente0001", "agente0002"):
            self.assertRegex(out, r"%s\s+parado, pausado" % name)
        self.assertEqual(self._run("start")[0], 0)
        self.assertEqual(self._run("status")[1].count("no ar"), 3, "a pausa sai no start")

    def test_web_em_outro_endereco_e_sem_porta(self):
        code, _out, err = self._run("start", SSS_WEB_HOST="0.0.0.0")
        self.assertEqual(code, 0, err)
        self.assertIn("--host 0.0.0.0 --port 18997", self._keepalive_log())
        self._kill_all()
        _write(os.path.join(self.root, "instance", "web0001", "config.ini"),
               "[app]\nname = web0001\n[web]\nallowed_origins = http://sss.empresa.local\n")
        code, _out, err = self._run("status")
        self.assertEqual(code, 2)
        self.assertIn("sem porta no [web] allowed_origins", err)

    def test_cron_show_install_e_remove(self):
        _write(self.cron_file, "# tarefa de outro sistema\n0 1 * * * /opt/outro/job.sh\n")
        code, block, err = self._run("cron", "show", SSS_IC_DIR="/opt/oracle/lib",
                                     SSS_LOCALE="en_US.utf8")
        self.assertEqual(code, 0, err)
        self.assertTrue(block.startswith("# --- SSS DEV ---"), block)
        self.assertTrue(block.rstrip().endswith("# --- fim SSS DEV ---"), block)
        self.assertIn("PATH=%s:/usr/local/bin:/usr/bin:/bin" % os.path.dirname(sys.executable),
                      block)
        self.assertIn("LD_LIBRARY_PATH=/opt/oracle/lib", block)
        self.assertIn("SSS_LOCALE=en_US.utf8", block)
        self.assertIn("bin/sss-keepalive.sh web0001:18997 agente0001 agente0002", block)
        self.assertIn("> var/agente0001/logs/health.txt 2> var/agente0001/logs/health.err", block)
        for _ in range(2):
            code, out, err = self._run("cron", "install")
            self.assertEqual(code, 0, err)
        self.assertIn("ja existe o bloco do SSS DEV", out, "a segunda vez nao repete")
        text = self._crontab()
        self.assertEqual(text.count("# --- SSS DEV ---"), 1)
        self.assertIn("/opt/outro/job.sh", text, "o resto do crontab fica")
        saved = os.path.join(self.root, "var", "crontab_sss", "crontab_sss.txt")
        self.assertEqual(stat.S_IMODE(os.stat(saved).st_mode), 0o600)
        code, _out, err = self._run("cron", "remove")
        self.assertEqual(code, 0, err)
        self.assertEqual(self._crontab(),
                         "# tarefa de outro sistema\n0 1 * * * /opt/outro/job.sh\n")
        self.assertIn("nada retirado", self._run("cron", "remove")[1])

    def test_uso_invalido(self):
        for args in ((), ("parar",), ("cron",), ("cron", "apagar"), ("status", "x")):
            self.assertEqual(self._run(*args)[0], 2, args)


if __name__ == "__main__":
    unittest.main()
