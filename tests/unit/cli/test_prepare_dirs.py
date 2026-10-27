# -*- coding: utf-8 -*-
"""scripts/prepare_dirs.py (CR-026e): pastas do config.ini com dono e modo."""
import contextlib
import io
import os
import pwd
import shutil
import stat
import tempfile
import unittest
from unittest import mock

from tests.support import _testenv  # noqa: F401
from sss.cli import prepare_dirs
from sss.config import sss_config

ME = pwd.getpwuid(os.getuid()).pw_name


class TestPrepareDirs(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sss_prep_")
        self.addCleanup(shutil.rmtree, self.root)

    def _p(self, *parts):
        return os.path.join(self.root, *parts)

    def _ini(self, env="DEV", extra=""):
        path = self._p("config.ini")
        lines = [
            "[app]", "sss_env = %s" % env,
            "[oracle]", "user = sss_app", "dsn = x:1/y", "owner = own", "table_prefix = tbsss_",
            "[agent]", "agent_id = a1", "environments = PRODUCAO,Homologação",
            "work_dir = %s" % self._p("work"), "max_parallel_jobs = 2",
            "output_dir = %s" % self._p("out"),
            "script_base_dir = %s" % self._p("base", "scripts"),
            extra.rstrip("\n"),
            "[logging]", "log_dir = %s" % self._p("logs"),
            "[web]", "allowed_origins = http://x",
            "[retention]", "purge_user = sss_purge"]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path

    def _exec(self):
        users = "exec_users = PRODUCAO=sssprd,Homologação=ssshml\n"
        return users + "exec_work_dir = %s\n" % self._p("exec")

    def _run(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = prepare_dirs.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def _mode(self, *parts):
        return stat.S_IMODE(os.stat(self._p(*parts)).st_mode)

    def test_dev_sem_root_cria_com_o_modo_e_repete_sem_mudar(self):
        ini = self._ini()
        code, out, _err = self._run("--config", ini, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("faria: log_dir", out)
        self.assertFalse(os.path.exists(self._p("logs")), "--dry-run nao cria nada")
        code, out, _err = self._run("--config", ini)
        self.assertEqual(code, 0, out)
        names = ("logs", "work", "out", "base/scripts")
        modes = dict((name, self._mode(*name.split("/"))) for name in names)
        self.assertEqual(modes, {"logs": 0o750, "work": 0o700, "out": 0o755,
                                 "base/scripts": 0o755})
        self.assertEqual(out.count("criada"), 4)
        os.chmod(self._p("work"), 0o777)
        code, out, _err = self._run("--config", ini)
        self.assertEqual((code, out.count("criada"), out.count("ajustada")), (0, 0, 1))
        self.assertEqual(self._mode("work"), 0o700, "pasta existente tem o modo ajustado")

    def test_arquivo_ou_link_no_lugar_da_pasta_e_falha_sem_parar_as_demais(self):
        ini = self._ini()
        with open(self._p("logs"), "w") as f:
            f.write("x")
        os.makedirs(self._p("real"))
        os.symlink(self._p("real"), self._p("work"))
        code, out, err = self._run("--config", ini)
        self.assertEqual(code, prepare_dirs.EXIT_FAILURE)
        self.assertIn("existe e nao e pasta", err)
        self.assertIn("link simbolico", err)
        self.assertTrue(os.path.isdir(self._p("out")), "as demais pastas sao criadas")

    def test_fora_de_dev_exige_root(self):
        ini = self._ini("PROD", self._exec())
        with mock.patch.object(prepare_dirs.os, "geteuid", return_value=1000):
            code, _out, err = self._run("--config", ini)
        self.assertEqual(code, prepare_dirs.EXIT_NOT_ROOT)
        self.assertIn("rode como root", err)

    def test_plano_como_root_com_donos_e_pastas_de_ambiente(self):
        ini = self._ini("PROD", self._exec())
        plan = prepare_dirs.plan(sss_config.load(ini), "sss", as_root=True)
        got = [(os.path.relpath(f.path, self.root), f.owner, oct(f.mode)) for f in plan]
        self.assertEqual(got, [
            ("logs", "sss", "0o750"), ("work", "sss", "0o700"), ("exec", "root", "0o755"),
            ("exec/ssshml", "ssshml", "0o700"), ("exec/sssprd", "sssprd", "0o700"),
            ("out", "sss", "0o755"), ("out/producao", "sssprd", "0o700"),
            ("out/homologacao", "ssshml", "0o700"),
            ("base/scripts", "sss", "0o755")])

    def test_cr028_pastas_de_var_do_usuario_do_servico(self):
        """Revisao do CR-028 (M2): var/, var/<nome>/ e var/update/ primeiro, do servico."""
        var = self._p("var")
        ini = self._ini("PROD", self._exec())
        with open(ini, encoding="utf-8") as f:
            text = f.read()
        for key, sub in (("log_dir", "logs"), ("work_dir", "work"), ("output_dir", "out"),
                         ("exec_work_dir", "exec")):
            new = os.path.join(var, "a1" if sub != "exec" else "", sub)
            text = text.replace("%s = %s" % (key, self._p(sub)), "%s = %s" % (key, new))
        with open(ini, "w", encoding="utf-8") as f:
            f.write(text)
        plan = prepare_dirs.plan(sss_config.load(ini), "sss", as_root=True, var_dir=var)
        got = [(os.path.relpath(f.path, self.root), f.owner, oct(f.mode)) for f in plan[:3]]
        self.assertEqual(got, [("var", "sss", "0o755"), ("var/a1", "sss", "0o755"),
                               ("var/update", "sss", "0o755")])
        self.assertEqual(plan[3].key, "log_dir")
        self.assertNotIn("var/exec", [os.path.relpath(f.path, self.root) for f in plan[:3]],
                         "var/exec continua do root, na lista do config")

    def test_usuario_inexistente_nao_cria_nada(self):
        users = "exec_users = PRODUCAO=%s,Homologação=usuario_que_nao_existe\n" % ME
        ini = self._ini("PROD", users + "exec_work_dir = %s\n" % self._p("exec"))
        with mock.patch.object(prepare_dirs.os, "geteuid", return_value=0):
            code, _out, err = self._run("--config", ini, "--service-user", ME)
        self.assertEqual(code, prepare_dirs.EXIT_INVALID)
        self.assertIn("usuario_que_nao_existe", err)
        self.assertNotIn("root", err, "root existe; so o usuario inexistente e citado")
        self.assertFalse(os.path.exists(self._p("logs")))

    def test_cr028_web_so_cria_o_log_dir(self):
        path = self._p("web.ini")
        with open(path, "w", encoding="utf-8") as f:
            f.write("[app]\nsss_env = DEV\n[oracle]\nuser = u\ndsn = x:1/y\nowner = o\n"
                    "table_prefix = tbsss_\n[logging]\nlog_dir = %s\n"
                    "[web]\nallowed_origins = http://x\n" % self._p("weblogs"))
        code, out, _err = self._run("--config", path)
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("criada"), 1)
        self.assertEqual(self._mode("weblogs"), 0o750)

    def test_configuracao_invalida(self):
        path = self._p("ruim.ini")
        with open(path, "w") as f:
            f.write("[app]\nsss_env = XPTO\n")
        self.assertEqual(self._run("--config", path)[0], prepare_dirs.EXIT_INVALID)


if __name__ == "__main__":
    unittest.main()
