# -*- coding: utf-8 -*-
"""Testes dos launchers POSIX bin/sss-web.sh, bin/sss-scheduler.sh e bin/sss-stop.sh (README §12.2; F9.1c, CR-021e2).

Os launchers sao copiados para uma raiz falsa do web2py; um python3 falso registra argv, diretorio e ambiente, um
id falso simula root e um ldconfig falso diz se o Instant Client esta registrado. Confere: sintaxe, recusa de root,
so o run_web.py do SSS (web2py.py, outro script ou comando: codigo 2), exec a partir da raiz, LD_LIBRARY_PATH so sem o Instant Client no
ldconfig, umask 077, locale e TZ, e o .stop 0600 no work_dir do config.ini.
"""
from tests.support import _testenv  # noqa: F401

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

BIN = os.path.join(_testenv.APP_DIR, "bin")
LAUNCHERS = ("sss-web.sh", "sss-scheduler.sh", "sss-stop.sh")
LOCAL_SCRIPTS = ("start_local.sh", "stop_local.sh")

_FAKE_PYTHON = """#!%s
import json, os, sys
with open(os.environ["SSS_TESTE_SAIDA"], "w") as f:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "umask": oct(os.umask(0)),
               "ld": os.environ.get("LD_LIBRARY_PATH"), "tz": os.environ.get("TZ"),
               "lang": os.environ.get("LANG"), "lc_all": os.environ.get("LC_ALL")}, f)
""" % sys.executable


class TestLaunchers(unittest.TestCase):

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="sss_test_launch_"))
        self.addCleanup(shutil.rmtree, self.root, True)
        os.mkdir(os.path.join(self.root, "bin"))
        for name in LAUNCHERS:
            shutil.copy2(os.path.join(BIN, name), os.path.join(self.root, "bin", name))
        self.fakes = os.path.join(self.root, "falsos")
        os.mkdir(self.fakes)
        self.python = self._executable("python3", _FAKE_PYTHON)
        self.registro = os.path.join(self.root, "registro.json")

    def _executable(self, name, body):
        path = os.path.join(self.fakes, name)
        with open(path, "w") as f:
            f.write(body)
        os.chmod(path, 0o755)
        return path

    def _run_loop(self, launcher, *args, **env_extra):
        env = {"PATH": self.fakes + os.pathsep + os.environ.get("PATH", ""), "PYTHON": self.python,
               "SSS_TESTE_SAIDA": self.registro, "HOME": self.root}
        env.update(env_extra)
        p = subprocess.run([os.path.join(self.root, "bin", launcher)] + list(args), env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd="/", timeout=30)
        record = None
        if os.path.exists(self.registro):
            with open(self.registro) as f:
                record = json.load(f)
            os.remove(self.registro)
        return p.returncode, record, p.stderr.decode("utf-8", "replace")

    def test_sintaxe(self):
        for name in LAUNCHERS + ("sss-helper",):
            path = os.path.join(BIN, name)
            self.assertTrue(os.stat(path).st_mode & 0o111, name)
            if name.endswith(".sh"):
                self.assertEqual(subprocess.run(["bash", "-n", path]).returncode, 0, name)
                with open(path, encoding="utf-8") as f:
                    source = f.read()
                self.assertNotIn('exec "$@"\n', source.split("case \"$2\" in")[0], "sem exec livre antes das checagens")

    def test_scripts_locais_sem_web2py(self):
        """start_local/stop_local (so DEV) com sintaxe valida; nenhum script do bin/ sobe o web2py (CR-021e2)."""
        for name in LAUNCHERS + LOCAL_SCRIPTS:
            path = os.path.join(BIN, name)
            if name in LOCAL_SCRIPTS:
                self.assertEqual(subprocess.run(["bash", "-n", path]).returncode, 0, name)
            with open(path, encoding="utf-8") as f:
                source = f.read()
            for forbidden in ("web2py.py", "anyserver.py", " -S script_scheduling_service", "httpserver.pid"):
                self.assertNotIn(forbidden, source, "%s: %s" % (name, forbidden))
        for name in ("sss-web.sh", "start_local.sh", "stop_local.sh"):
            with open(os.path.join(BIN, name), encoding="utf-8") as f:
                self.assertIn("run_web.py", f.read(), name)

    def test_recusa_root(self):
        self._executable("id", "#!/bin/sh\necho 0\n")
        for name in LAUNCHERS:
            code, record, error = self._run_loop(name)
            self.assertEqual((code, record), (1, None), name)
            self.assertIn("root", error)

    def test_web_tres_formas_e_recusa(self):
        """Sempre o run_web.py (CR-021e2): sem argumentos, so opcoes, ou interpretador e opcoes."""
        server = "scripts/run_web.py"
        code, reg, _e = self._run_loop("sss-web.sh")
        self.assertEqual((code, reg["argv"]), (0, [server]))
        self.assertEqual((reg["cwd"], reg["umask"]), (self.root, "0o77"), "raiz do repositorio e umask 077")
        self.assertEqual(self._run_loop("sss-web.sh", "--port", "9000")[1]["argv"], [server, "--port", "9000"])
        code, reg, _e = self._run_loop("sss-web.sh", self.python, "--port", "8001", "--check")
        self.assertEqual((code, reg["argv"]), (0, [server, "--port", "8001", "--check"]))
        code, reg, _e = self._run_loop("sss-web.sh", self.python)
        self.assertEqual((code, reg["argv"]), (0, [server]))
        # Opcao do interpretador nunca chega a ele: vem depois do script e o argparse do run_web.py recusa.
        self.assertEqual(self._run_loop("sss-web.sh", "-c", "import os")[1]["argv"], [server, "-c", "import os"])

    def test_web_recusa_web2py_e_outros_comandos(self):
        """web2py.py, anyserver.py, outro script ou outro executavel: codigo 2, nada executado."""
        for args in (("/bin/sh", "-c", "id"), (self.python, "outro.py"), (self.python, "web2py.py", "-p", "8000"),
                     ("anyserver.py",), ("--port", "8000", "web2py.py")):
            code, reg, error = self._run_loop("sss-web.sh", *args)
            self.assertEqual((code, reg), (2, None), args)
            self.assertIn("Erro", error)

    def test_scheduler_so_a_linha_do_daemon(self):
        daemon = "scripts/run_scheduler.py"
        code, reg, _e = self._run_loop("sss-scheduler.sh")
        self.assertEqual((code, reg["argv"], reg["cwd"]), (0, [daemon], self.root))
        code, reg, _e = self._run_loop("sss-scheduler.sh", "--config", "/etc/sss/agente_b.ini")
        self.assertEqual(reg["argv"], [daemon, "--config", "/etc/sss/agente_b.ini"])
        for args in (("--config",), ("--config", ""), ("-c", "x"), ("/bin/sh",), ("--config", "a", "b")):
            code, reg, _e = self._run_loop("sss-scheduler.sh", *args)
            self.assertEqual((code, reg), (2, None), args)

    def test_cr028_subida_pelo_nome_do_processo(self):
        # CR-028 (D7): o nome vira --name (instance/<nome>/config.ini); o interpretador continua opcional.
        code, reg, _e = self._run_loop("sss-scheduler.sh", "agente0001")
        self.assertEqual((code, reg["argv"]), (0, ["scripts/run_scheduler.py", "--name", "agente0001"]))
        code, reg, _e = self._run_loop("sss-web.sh", "web0001", "--port", "8000")
        self.assertEqual((code, reg["argv"]), (0, ["scripts/run_web.py", "--name", "web0001", "--port", "8000"]))
        code, reg, _e = self._run_loop("sss-web.sh", self.python, "web0001")
        self.assertEqual((code, reg["argv"]), (0, ["scripts/run_web.py", "--name", "web0001"]))
        for launcher, args in (("sss-scheduler.sh", ("Agente 1",)), ("sss-scheduler.sh", ("a/b",)),
                               ("sss-web.sh", ("Web0001",))):
            code, reg, _e = self._run_loop(launcher, *args)
            self.assertEqual((code, reg), (2, None), args)

    def test_cr028_stop_pelo_nome_com_pastas_derivadas(self):
        folder = os.path.join(self.root, "instance", "agente0001")
        os.makedirs(folder)
        os.makedirs(os.path.join(self.root, "var", "agente0001", "work"))
        with open(os.path.join(folder, "config.ini"), "w") as f:
            f.write("[app]\nname = agente0001\n[agent]\nenvironments = PRODUCAO\n")
        code, _r, error = self._run_loop("sss-stop.sh", "agente0001", PYTHON=sys.executable)
        self.assertEqual(code, 0, error)
        self.assertTrue(os.path.exists(os.path.join(self.root, "var", "agente0001", "work", "sss-agente0001.stop")))

    def test_cr028_stop_recusa_name_diferente_da_pasta(self):
        """Revisao do CR-028 (A2): instance/agente0002/ copiada sem trocar o name nao para o agente0001."""
        folder = os.path.join(self.root, "instance", "agente0002")
        os.makedirs(folder)
        os.makedirs(os.path.join(self.root, "var", "agente0001", "work"))
        with open(os.path.join(folder, "config.ini"), "w") as f:
            f.write("[app]\nname = agente0001\n[agent]\nenvironments = PRODUCAO\n")
        code, _r, error = self._run_loop("sss-stop.sh", "agente0002", PYTHON=sys.executable)
        self.assertEqual(code, 2, error)
        self.assertIn("diferente da pasta", error)
        self.assertFalse(os.path.exists(os.path.join(self.root, "var", "agente0001", "work", "sss-agente0001.stop")))

    def test_instant_client_so_sem_ldconfig(self):
        self._executable("ldconfig", "#!/bin/sh\necho '\tlibclntsh.so.19.1 (libc6,x86-64) => /opt/ic/libclntsh.so'\n")
        for name in ("sss-web.sh", "sss-scheduler.sh"):
            _c, reg, _e = self._run_loop(name, SSS_IC_DIR="/opt/ic19", SSS_TZ="America/Sao_Paulo")
            self.assertEqual((reg["ld"], reg["tz"], reg["lang"], reg["lc_all"]),
                             (None, "America/Sao_Paulo", "C.UTF-8", "C.UTF-8"), name)
        self._executable("ldconfig", "#!/bin/sh\necho '\tlibc.so.6 (libc6,x86-64) => /lib/libc.so.6'\n")
        for name in ("sss-web.sh", "sss-scheduler.sh"):
            _c, reg, _e = self._run_loop(name, SSS_IC_DIR="/opt/ic19", SSS_LOCALE="pt_BR.UTF-8")
            self.assertEqual((reg["ld"], reg["lang"]), ("/opt/ic19", "pt_BR.UTF-8"), name)
        _c, reg, _e = self._run_loop("sss-web.sh")
        self.assertIsNone(reg["ld"], "sem SSS_IC_DIR nada e exportado")

    def _config(self, agent_id="srv-a", work=None):
        work = work if work is not None else os.path.join(self.root, "work")
        os.makedirs(os.path.join(self.root, "work"), exist_ok=True)
        path = os.path.join(self.root, "agente.ini")
        with open(path, "w") as f:
            f.write("[agent]\nagent_id = %s   ; comentario\nwork_dir = %s\n" % (agent_id, work))
        return path

    def test_stop_cria_o_arquivo_no_work_dir(self):
        code, _r, error = self._run_loop("sss-stop.sh", "--config", self._config(), PYTHON=sys.executable)
        self.assertEqual(code, 0, error)
        stop = os.path.join(self.root, "work", "sss-srv-a.stop")
        self.assertEqual(os.stat(stop).st_mode & 0o777, 0o600)
        self.assertEqual(self._run_loop("sss-stop.sh", "--config", self._config(), PYTHON=sys.executable)[0], 0,
                         "idempotente")

    def test_stop_recusa_configuracao_invalida(self):
        cases = [("--config", self._config(agent_id="purge")), ("--config", self._config(work="relativo/work")),
                 ("--config", self._config(work=os.path.join(self.root, "nao_existe"))),
                 ("--config", os.path.join(self.root, "sem_arquivo.ini")), ("--outro",)]
        for args in cases:
            code, _r, error = self._run_loop("sss-stop.sh", *args, PYTHON=sys.executable)
            self.assertEqual(code, 2, (args, error))
        self.assertEqual(os.listdir(os.path.join(self.root, "work")), [])


if __name__ == "__main__":
    unittest.main()
