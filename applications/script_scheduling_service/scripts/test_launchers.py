# -*- coding: utf-8 -*-
"""Testes dos launchers POSIX bin/sss-web.sh, bin/sss-scheduler.sh e bin/sss-stop.sh (README §12.2; F9.1c).

Os launchers sao copiados para uma raiz falsa do web2py; um python3 falso registra argv, diretorio e ambiente, um
id falso simula root e um ldconfig falso diz se o Instant Client esta registrado. Confere: sintaxe, recusa de root,
so o processo do SSS (outro comando: codigo 2), exec a partir da raiz, LD_LIBRARY_PATH so sem o Instant Client no
ldconfig, umask 077, locale e TZ, e o .stop 0600 no work_dir do config.ini.
"""
import _testenv  # noqa: F401

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

BIN = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "bin"))
LAUNCHERS = ("sss-web.sh", "sss-scheduler.sh", "sss-stop.sh")

_PYTHON_FALSO = """#!%s
import json, os, sys
with open(os.environ["SSS_TESTE_SAIDA"], "w") as f:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "umask": oct(os.umask(0)),
               "ld": os.environ.get("LD_LIBRARY_PATH"), "tz": os.environ.get("TZ"),
               "lang": os.environ.get("LANG"), "lc_all": os.environ.get("LC_ALL")}, f)
""" % sys.executable


class TestLaunchers(unittest.TestCase):

    def setUp(self):
        self.raiz = os.path.realpath(tempfile.mkdtemp(prefix="sss_test_launch_"))
        self.addCleanup(shutil.rmtree, self.raiz, True)
        os.mkdir(os.path.join(self.raiz, "bin"))
        for nome in LAUNCHERS:
            shutil.copy2(os.path.join(BIN, nome), os.path.join(self.raiz, "bin", nome))
        self.falsos = os.path.join(self.raiz, "falsos")
        os.mkdir(self.falsos)
        self.python = self._executavel("python3", _PYTHON_FALSO)
        self.registro = os.path.join(self.raiz, "registro.json")

    def _executavel(self, nome, corpo):
        caminho = os.path.join(self.falsos, nome)
        with open(caminho, "w") as f:
            f.write(corpo)
        os.chmod(caminho, 0o755)
        return caminho

    def _rodar(self, launcher, *args, **env_extra):
        env = {"PATH": self.falsos + os.pathsep + os.environ.get("PATH", ""), "PYTHON": self.python,
               "SSS_TESTE_SAIDA": self.registro, "HOME": self.raiz}
        env.update(env_extra)
        p = subprocess.run([os.path.join(self.raiz, "bin", launcher)] + list(args), env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd="/", timeout=30)
        registro = None
        if os.path.exists(self.registro):
            with open(self.registro) as f:
                registro = json.load(f)
            os.remove(self.registro)
        return p.returncode, registro, p.stderr.decode("utf-8", "replace")

    def test_sintaxe(self):
        for nome in LAUNCHERS + ("sss-helper",):
            caminho = os.path.join(BIN, nome)
            self.assertTrue(os.stat(caminho).st_mode & 0o111, nome)
            if nome.endswith(".sh"):
                self.assertEqual(subprocess.run(["bash", "-n", caminho]).returncode, 0, nome)
                with open(caminho, encoding="utf-8") as f:
                    fonte = f.read()
                self.assertNotIn('exec "$@"\n', fonte.split("case \"$2\" in")[0], "sem exec livre antes das checagens")

    def test_recusa_root(self):
        self._executavel("id", "#!/bin/sh\necho 0\n")
        for nome in LAUNCHERS:
            codigo, registro, erro = self._rodar(nome)
            self.assertEqual((codigo, registro), (1, None), nome)
            self.assertIn("root", erro)

    def test_web_tres_formas_e_recusa(self):
        codigo, reg, _e = self._rodar("sss-web.sh")
        self.assertEqual(codigo, 0)
        self.assertEqual(reg["argv"], ["anyserver.py", "-s", "wsgiref", "-i", "127.0.0.1", "-p", "8000"])
        self.assertEqual((reg["cwd"], reg["umask"]), (self.raiz, "0o77"), "raiz do web2py e umask 077")
        self.assertEqual(self._rodar("sss-web.sh", "-p", "9000")[1]["argv"], ["anyserver.py", "-p", "9000"])
        codigo, reg, _e = self._rodar("sss-web.sh", self.python, "web2py.py", "-p", "8001")
        self.assertEqual((codigo, reg["argv"]), (0, ["web2py.py", "-p", "8001"]))
        for args in (("/bin/sh", "-c", "id"), (self.python, "outro.py"), (self.python,)):
            codigo, reg, _e = self._rodar("sss-web.sh", *args)
            self.assertEqual((codigo, reg), (2, None), args)

    def test_scheduler_so_a_linha_do_daemon(self):
        daemon = "applications/script_scheduling_service/scripts/run_scheduler.py"
        codigo, reg, _e = self._rodar("sss-scheduler.sh")
        self.assertEqual((codigo, reg["argv"], reg["cwd"]), (0, [daemon], self.raiz))
        codigo, reg, _e = self._rodar("sss-scheduler.sh", "--config", "/etc/sss/agente_b.ini")
        self.assertEqual(reg["argv"], [daemon, "--config", "/etc/sss/agente_b.ini"])
        for args in (("--config",), ("--config", ""), ("-c", "x"), ("/bin/sh",), ("--config", "a", "b")):
            codigo, reg, _e = self._rodar("sss-scheduler.sh", *args)
            self.assertEqual((codigo, reg), (2, None), args)

    def test_instant_client_so_sem_ldconfig(self):
        self._executavel("ldconfig", "#!/bin/sh\necho '\tlibclntsh.so.19.1 (libc6,x86-64) => /opt/ic/libclntsh.so'\n")
        for nome in ("sss-web.sh", "sss-scheduler.sh"):
            _c, reg, _e = self._rodar(nome, SSS_IC_DIR="/opt/ic19", SSS_TZ="America/Sao_Paulo")
            self.assertEqual((reg["ld"], reg["tz"], reg["lang"], reg["lc_all"]),
                             (None, "America/Sao_Paulo", "C.UTF-8", "C.UTF-8"), nome)
        self._executavel("ldconfig", "#!/bin/sh\necho '\tlibc.so.6 (libc6,x86-64) => /lib/libc.so.6'\n")
        for nome in ("sss-web.sh", "sss-scheduler.sh"):
            _c, reg, _e = self._rodar(nome, SSS_IC_DIR="/opt/ic19", SSS_LOCALE="pt_BR.UTF-8")
            self.assertEqual((reg["ld"], reg["lang"]), ("/opt/ic19", "pt_BR.UTF-8"), nome)
        _c, reg, _e = self._rodar("sss-web.sh")
        self.assertIsNone(reg["ld"], "sem SSS_IC_DIR nada e exportado")

    def _config(self, agent_id="srv-a", work=None):
        work = work if work is not None else os.path.join(self.raiz, "work")
        os.makedirs(os.path.join(self.raiz, "work"), exist_ok=True)
        caminho = os.path.join(self.raiz, "agente.ini")
        with open(caminho, "w") as f:
            f.write("[agent]\nagent_id = %s   ; comentario\nwork_dir = %s\n" % (agent_id, work))
        return caminho

    def test_stop_cria_o_arquivo_no_work_dir(self):
        codigo, _r, erro = self._rodar("sss-stop.sh", "--config", self._config(), PYTHON=sys.executable)
        self.assertEqual(codigo, 0, erro)
        stop = os.path.join(self.raiz, "work", "sss-srv-a.stop")
        self.assertEqual(os.stat(stop).st_mode & 0o777, 0o600)
        self.assertEqual(self._rodar("sss-stop.sh", "--config", self._config(), PYTHON=sys.executable)[0], 0,
                         "idempotente")

    def test_stop_recusa_configuracao_invalida(self):
        casos = [("--config", self._config(agent_id="purge")), ("--config", self._config(work="relativo/work")),
                 ("--config", self._config(work=os.path.join(self.raiz, "nao_existe"))),
                 ("--config", os.path.join(self.raiz, "sem_arquivo.ini")), ("--outro",)]
        for args in casos:
            codigo, _r, erro = self._rodar("sss-stop.sh", *args, PYTHON=sys.executable)
            self.assertEqual(codigo, 2, (args, erro))
        self.assertEqual(os.listdir(os.path.join(self.raiz, "work")), [])


if __name__ == "__main__":
    unittest.main()
