# -*- coding: utf-8 -*-
"""Testes do scripts/package.py (README §12.2; F9.1c; CR-005; CR-003 P10).

Arvore falsa do web2py em diretorio temporario: pacote gerado, SHA256SUMS de fora conferindo com o tar.gz e o de
dentro com cada arquivo, tar reprodutivel, routes.py gerado, bin/sss-helper executavel, pastas de runtime do
web2py ausentes, runtime vazias presentes, DEV e testes fora; recusa (sem gravar nada e sem imprimir o valor) com
secrets.cfg, credencial fora do placeholder, bytecode, link simbolico e outra aplicacao.
"""
import _testenv  # noqa: F401

import hashlib
import io
import os
import shutil
import tarfile
import tempfile
import unittest

import package as empacotar

APP = empacotar.APP
SECRET = "valor-de-teste-nao-placeholder"


class TestPack(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sss_test_pacote_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.origem = os.path.join(self.root, "web2py")
        self.saida = os.path.join(self.root, "dist")
        files = {
            "web2py.py": "# web2py\n", "anyserver.py": "# anyserver\n", "routes.py": "# DEV\n",
            "gluon/__init__.py": "", "gluon/main.py": "# main\n", "gluon/tests/test_x.py": "",
            "gluon/packages/pydal/test-venv/bin/pip": "#!/x/python\n",
            "bin/sss-web.sh": "#!/bin/bash\n", "bin/sss-scheduler.sh": "#!/bin/bash\n",
            "bin/sss-stop.sh": "#!/bin/bash\n", "bin/sss-helper": "#!/usr/bin/env python3\n",
            "bin/start_local.sh": "#!/bin/bash\n", "CLAUDE.md": "x", "parameters_8000.py": "x",
            APP + "/controllers/default.py": "# default\n", APP + "/controllers/dev.py": "# dev\n",
            APP + "/views/dev/index.html": "x", APP + "/dev/scripts/a.py": "x",
            APP + "/modules/repo_fake/__init__.py": "x", APP + "/modules/sss_config.py": "x",
            APP + "/instance/config.ini": "[oracle]\nuser = sss_web\n",
            APP + "/instance/config.ini.example": "[retention]\npurge_user =                 ; vazio em DEV\n",
            APP + "/instance/secrets.cfg.example": "[oracle]\npassword = CHANGE_ME\n[web]\ncookie_key = CHANGE_ME\n"
                                                   "[purge]\npassword = ...\n",
            APP + "/scripts/purge.py": "x", APP + "/scripts/test_purge.py": "x", APP + "/scripts/_testenv.py": "x",
            APP + "/scripts/logs/a.log": "x", APP + "/applications/x.txt": "x", APP + "/deposit/x": "x",
            APP + "/logs/x": "x", APP + "/site-packages/x": "x", APP + "/sessions/abc": "x", APP + "/errors/e": "x",
            APP + "/work/sss-a.lock": "x", APP + "/docs/DEPLOYMENT.md": "# Implantacao\n",
        }
        for rel, text in files.items():
            self._write(rel, text)
        os.chmod(os.path.join(self.origem, "bin", "sss-helper"), 0o755)

    def _write(self, rel, text):
        path = os.path.join(self.origem, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        return path

    def _main(self):
        text = io.StringIO()
        code = empacotar.main(["--source", self.origem, "--out-dir", self.saida], output_text=text)
        return code, text.getvalue()

    def _package(self):
        return os.path.join(self.saida, "sss-%s.tar.gz" % empacotar.sss_config.SSS_VERSION)

    def _refused(self, snippet):
        code, text = self._main()
        self.assertEqual(code, 1, text)
        self.assertIn(snippet, text)
        self.assertNotIn(SECRET, text, "o valor nunca e impresso")
        self.assertFalse(os.path.exists(self.saida) and os.listdir(self.saida), "nada gravado")
        return text

    def test_pacote_e_sha256sums(self):
        code, text = self._main()
        self.assertEqual(code, 0, text)
        package = self._package()
        with open(package, "rb") as f:
            data = f.read()
        with open(os.path.join(self.saida, "SHA256SUMS")) as f:
            self.assertEqual(f.read(), "%s  %s\n" % (hashlib.sha256(data).hexdigest(), os.path.basename(package)))
        top = "sss-%s/" % empacotar.sss_config.SSS_VERSION
        with tarfile.open(package) as tar:
            members = dict((m.name[len(top):], m) for m in tar.getmembers() if m.name.startswith(top))
            sums = tar.extractfile(top + "SHA256SUMS").read().decode("utf-8")
            for line in sums.splitlines():
                hash_, rel = line.split("  ", 1)
                self.assertEqual(hashlib.sha256(tar.extractfile(top + rel).read()).hexdigest(), hash_, rel)
            routes = tar.extractfile(top + "routes.py").read().decode("utf-8")
        files = set(n for n, m in members.items() if m.isfile())
        self.assertIn('default_application = "script_scheduling_service"', routes)
        self.assertEqual(members["bin/sss-helper"].mode, 0o755, "helper executavel")
        self.assertEqual((members["bin/sss-helper"].uid, members["web2py.py"].mode), (0, 0o644))
        for rel in ("web2py.py", "anyserver.py", "gluon/main.py", "bin/sss-web.sh", "bin/sss-scheduler.sh",
                    "bin/sss-stop.sh", APP + "/controllers/default.py", APP + "/scripts/purge.py",
                    APP + "/instance/config.ini.example", APP + "/instance/secrets.cfg.example",
                    APP + "/docs/DEPLOYMENT.md"):
            self.assertIn(rel, files)
        for dir_value in empacotar.EMPTY_RUNTIME_DIRS:
            self.assertTrue(members[APP + "/" + dir_value].isdir(), dir_value)
        forbidden = [n for n in members if any(n == APP + "/" + p or n.startswith(APP + "/" + p + "/") for p in (
            "applications", "deposit", "logs", "site-packages", "scripts/logs", "work", "dev", "views/dev",
            "modules/repo_fake", "controllers/dev.py", "instance/config.ini", "scripts/test_purge.py",
            "scripts/_testenv.py", "sessions/abc", "errors/e"))]
        self.assertEqual(forbidden, [])
        self.assertFalse([n for n in members if "/tests/" in n or "test-venv" in n], "testes do upstream fora")
        self.assertFalse(set(("bin/start_local.sh", "CLAUDE.md", "parameters_8000.py")) & files)

    def test_tar_reprodutivel(self):
        self.assertEqual(self._main()[0], 0)
        with open(self._package(), "rb") as f:
            first = f.read()
        os.utime(os.path.join(self.origem, "web2py.py"), (1, 1))
        self.assertEqual(self._main()[0], 0)
        with open(self._package(), "rb") as f:
            self.assertEqual(f.read(), first)

    def test_falha_com_secrets_cfg_na_arvore(self):
        self._write(APP + "/instance/secrets.cfg", "[oracle]\npassword = %s\n" % SECRET)
        text = self._refused("instance/secrets.cfg: arquivo de segredos real")
        self.assertIn("instance/secrets.cfg:2: password", text)

    def test_exemplo_com_senha_que_nao_e_placeholder(self):
        self._write(APP + "/instance/secrets.cfg.example", "[oracle]\npassword = %s  ; teste\n" % SECRET)
        self._refused("secrets.cfg.example:2: password com valor que nao e o placeholder CHANGE_ME")

    def test_change_me_so_no_exemplo_de_segredos(self):
        self._write(APP + "/instance/outro.cfg.example", "[x]\npassword = CHANGE_ME\n")
        self._refused("instance/outro.cfg.example:2: password")

    def test_cookie_key_em_ini(self):
        self._write(APP + "/instance/config.ini.example", "[web]\ncookie_key = %s\n" % SECRET)
        self._refused("config.ini.example:2: cookie_key")

    def test_bytecode_link_e_outra_aplicacao(self):
        self._write(APP + "/modules/x.pyc", "x")
        self._write(APP + "/modules/__pycache__/y.cpython-36.pyc", "x")
        self._write("applications/admin/controllers/default.py", "x")
        os.symlink("/etc", os.path.join(self.origem, "gluon", "fora"))
        text = self._refused("modules/x.pyc: bytecode")
        self.assertIn("__pycache__/y.cpython-36.pyc: bytecode", text)
        self.assertIn("gluon/fora: link simbolico", text)

    def test_verificar_codigo_de_dev_e_admin(self):
        problems = empacotar.check([APP + "/controllers/dev.py", APP + "/modules/repo_fake/a.py",
                                        "applications/admin/x.py", APP + "/deposit/x"], lambda rel: b"")
        self.assertEqual(len(problems), 4, problems)

    def test_helper_ausente(self):
        os.remove(os.path.join(self.origem, "bin", "sss-helper"))
        self._refused("bin/sss-helper: ausente")

    def test_pacote_da_arvore_real_sem_segredo_nem_dev(self):
        # Coleta da propria arvore: as regras de inclusao nunca puxam DEV, testes nem runtime.
        files, _problems = empacotar.collect(empacotar.DEFAULT_ROOT)
        self.assertFalse([a for a in files if "/repo_fake/" in a or a.endswith("controllers/dev.py")
                          or "/scripts/test_" in a or a.endswith("instance/config.ini")])
        self.assertIn(APP + "/modules/repo_oracle/purge.py", files)


class TestPackageStartsWithoutDev(unittest.TestCase):
    """F9.1d (ensaio a partir do pacote): o repo_factory importava o repo_fake no topo e a aplicacao nao subia sem
    ele. Nenhum arquivo que vai no pacote importa no nivel do modulo algo que o pacote exclui."""

    def test_sem_import_de_topo_do_que_fica_fora(self):
        import ast
        files, _p = empacotar.collect(empacotar.DEFAULT_ROOT)
        excluded = ("repo_fake", "dev", "_testenv", "_oracle_test_support", "_output_memory")
        violations = []
        for rel in files:
            if not rel.startswith(APP + "/") or not rel.endswith(".py"):
                continue
            with open(os.path.join(empacotar.DEFAULT_ROOT, rel), encoding="utf-8") as f:
                tree = ast.parse(f.read(), rel)
            for no in tree.body:  # so o nivel do modulo; import tardio dentro de funcao e permitido
                names = []
                if isinstance(no, ast.Import):
                    names = [a.name for a in no.names]
                elif isinstance(no, ast.ImportFrom) and no.module:
                    names = [no.module]
                violations.extend("%s: %s" % (rel, n) for n in names
                                 if n.split(".")[0] in excluded or n.startswith("test_"))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
