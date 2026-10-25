# -*- coding: utf-8 -*-
"""Testes do tools/package.py (README §12.2; F9.1c; CR-005; CR-003 P10).

Arvore falsa do repositorio em diretorio temporario: pacote gerado, SHA256SUMS de fora conferindo com o tar.gz e o
de dentro com cada arquivo, tar reprodutivel, bin/sss-helper executavel, sem nada do web2py (CR-021f), DEV, testes
e pastas de execucao fora; recusa (sem gravar nada e sem imprimir o valor) com secrets.cfg, credencial fora do
placeholder, bytecode, link simbolico, outra aplicacao e resto do web2py na raiz.
"""
from tests.support import _testenv  # noqa: F401

import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

import package as empacotar

SECRET = "valor-de-teste-nao-placeholder"


class TestPack(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sss_test_pacote_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.origem = os.path.join(self.root, "repo")
        self.saida = os.path.join(self.root, "dist")
        files = {
            "bin/sss-web.sh": "#!/bin/bash\n", "bin/sss-scheduler.sh": "#!/bin/bash\n",
            "bin/sss-stop.sh": "#!/bin/bash\n", "bin/sss-helper": "#!/usr/bin/env python3\n",
            "bin/start_local.sh": "#!/bin/bash\n", "CLAUDE.md": "x", "parameters_8000.py": "x",
            "controllers/default.py": "# default\n", "controllers/dev.py": "# dev\n",
            "scripts/run_web.py": "# servidor\n", "webapp/bootstrap.py": "# web\n",
            "views/dev/index.html": "x", "dev/scripts/a.py": "x",
            "modules/repo_fake/__init__.py": "x", "modules/sss_config.py": "x",
            "instance/config.ini": "[oracle]\nuser = sss_web\n",
            "instance/config.ini.example": "[retention]\npurge_user =                 ; vazio em DEV\n",
            "instance/secrets.cfg.example": "[oracle]\npassword = CHANGE_ME\n[web]\ncookie_key = CHANGE_ME\n"
                                                   "[purge]\npassword = ...\n",
            "scripts/purge.py": "x", "scripts/test_purge.py": "x",
            "tests/__init__.py": "x", "tests/unit/test_purge.py": "x", "tests/support/_testenv.py": "x",
            "tools/package.py": "x",
            "scripts/logs/a.log": "x", "deposit/x": "x",
            "logs/x": "x", "site-packages/x": "x", "sessions/abc": "x", "errors/e": "x",
            "work/sss-a.lock": "x", "docs/DEPLOYMENT.md": "# Implantacao\n",
            # CR-022a: a aplicacao e a raiz; o que e so da maquina de desenvolvimento fica fora
            "AGENTS.md": "# regras\n", "README.md": "# SSS\n", "Makefile": "x", "LEIA-ME.TXT": "x",
            ".git/config": "x", ".gitignore": "x", "input/a.txt": "x", "output/b.zip": "x", "script_work/c": "x",
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
        files = set(n for n, m in members.items() if m.isfile())
        self.assertEqual(members["bin/sss-helper"].mode, 0o755, "helper executavel")
        self.assertEqual((members["bin/sss-helper"].uid, members["scripts/run_web.py"].mode),
                         (0, 0o644))
        for rel in ("bin/sss-web.sh", "bin/sss-scheduler.sh", "bin/sss-stop.sh",
                    "controllers/default.py", "scripts/run_web.py",
                    "webapp/bootstrap.py", "scripts/purge.py",
                    "instance/config.ini.example", "instance/secrets.cfg.example",
                    "docs/DEPLOYMENT.md"):
            self.assertIn(rel, files)
        forbidden = [n for n in members if any(n == p or n.startswith(p + "/") for p in (
            "applications", "deposit", "logs", "site-packages", "scripts/logs", "work", "dev", "views/dev",
            "modules/repo_fake", "controllers/dev.py", "instance/config.ini", "scripts/test_purge.py",
            "tests", "tools", "sessions", "errors"))]
        self.assertEqual(forbidden, [])
        # CR-021f: nada do web2py, nem pasta de runtime vazia
        self.assertFalse([n for n in members
                          if n.split("/", maxsplit=1)[0] in empacotar.WEB2PY_ROOT_LEFTOVERS])
        self.assertFalse(set(("bin/start_local.sh", "CLAUDE.md", "parameters_8000.py", "Makefile", "LEIA-ME.TXT",
                              ".gitignore")) & files)
        self.assertFalse([n for n in members if n.split("/", maxsplit=1)[0] in (".git", "input", "output", "script_work")])
        self.assertIn("AGENTS.md", files)

    def test_tar_reprodutivel(self):
        self.assertEqual(self._main()[0], 0)
        with open(self._package(), "rb") as f:
            first = f.read()
        os.utime(os.path.join(self.origem, "scripts", "run_web.py"), (1, 1))
        self.assertEqual(self._main()[0], 0)
        with open(self._package(), "rb") as f:
            self.assertEqual(f.read(), first)

    def test_falha_com_secrets_cfg_na_arvore(self):
        self._write("instance/secrets.cfg", "[oracle]\npassword = %s\n" % SECRET)
        text = self._refused("instance/secrets.cfg: arquivo de segredos real")
        self.assertIn("instance/secrets.cfg:2: password", text)

    def test_exemplo_com_senha_que_nao_e_placeholder(self):
        self._write("instance/secrets.cfg.example", "[oracle]\npassword = %s  ; teste\n" % SECRET)
        self._refused("secrets.cfg.example:2: password com valor que nao e o placeholder CHANGE_ME")

    def test_change_me_so_no_exemplo_de_segredos(self):
        self._write("instance/outro.cfg.example", "[x]\npassword = CHANGE_ME\n")
        self._refused("instance/outro.cfg.example:2: password")

    def test_cookie_key_em_ini(self):
        self._write("instance/config.ini.example", "[web]\ncookie_key = %s\n" % SECRET)
        self._refused("config.ini.example:2: cookie_key")

    def test_bytecode_link_e_outra_aplicacao(self):
        self._write("modules/x.pyc", "x")
        self._write("modules/__pycache__/y.cpython-36.pyc", "x")
        self._write("applications/admin/controllers/default.py", "x")
        os.symlink("/etc", os.path.join(self.origem, "modules", "fora"))
        text = self._refused("modules/x.pyc: bytecode")
        self.assertIn("__pycache__/y.cpython-36.pyc: bytecode", text)
        self.assertIn("modules/fora: link simbolico", text)

    def test_resto_do_web2py_na_raiz_recusa(self):
        """CR-021f: gluon/, web2py.py, anyserver.py ou routes.py na origem recusam o pacote."""
        for rel in ("gluon/main.py", "web2py.py", "anyserver.py", "routes.py"):
            with self.subTest(rel=rel):
                self._write(rel, "x")
                top = rel.split("/", maxsplit=1)[0]
                self._refused(f"{top}: resto do web2py na raiz")
                path = os.path.join(self.origem, top)
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
        self.assertEqual(self._main()[0], 0, "sem os restos, o pacote sai")

    def test_verificar_codigo_de_dev_e_admin(self):
        problems = empacotar.check(["controllers/dev.py", "modules/repo_fake/a.py",
                                        "applications/admin/x.py", "deposit/x", "sessions/s",
                                        "gluon/main.py", "web2py.py"], lambda rel: b"")
        self.assertEqual(len(problems), 7, problems)

    def test_rodando_de_dentro_da_copia_que_empacota(self):
        """Regressao do ensaio do CR-021f3: o package.py da copia limpa importava o sss_config e gravava
        modules/__pycache__ na propria copia, e o pacote era recusado por bytecode."""
        with open(os.path.join(_testenv.APP_DIR, "tools", "package.py"), encoding="utf-8") as f:
            self._write("tools/package.py", f.read())
        self._write("modules/sss_config.py",
                    f"SSS_VERSION = {empacotar.sss_config.SSS_VERSION!r}\n")
        p = subprocess.run([sys.executable, os.path.join(self.origem, "tools", "package.py"),
                            "--source", self.origem, "--out-dir", self.saida], check=False,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout.decode("utf-8", "replace"))
        self.assertFalse(os.path.exists(os.path.join(self.origem, "modules", "__pycache__")))

    def test_helper_ausente(self):
        os.remove(os.path.join(self.origem, "bin", "sss-helper"))
        self._refused("bin/sss-helper: ausente")

    def test_pacote_da_arvore_real_sem_segredo_nem_dev(self):
        # Coleta da propria arvore: as regras de inclusao nunca puxam DEV, testes nem runtime.
        files, _problems = empacotar.collect(empacotar.DEFAULT_ROOT)
        self.assertFalse([a for a in files if "/repo_fake/" in a or a.endswith("controllers/dev.py")
                          or a.startswith(("tests/", "tools/", "scripts/test_")) or a.endswith("instance/config.ini")])
        self.assertIn("modules/repo_oracle/purge.py", files)
        self.assertIn("scripts/run_web.py", files)
        self.assertEqual(_problems, [], "a arvore real nao tem resto do web2py nem link (CR-021f)")


class TestPackageStartsWithoutDev(unittest.TestCase):
    """F9.1d (ensaio a partir do pacote): o repo_factory importava o repo_fake no topo e a aplicacao nao subia sem
    ele. Nenhum arquivo que vai no pacote importa no nivel do modulo algo que o pacote exclui."""

    def test_sem_import_de_topo_do_que_fica_fora(self):
        import ast
        files, _p = empacotar.collect(empacotar.DEFAULT_ROOT)
        excluded = ("repo_fake", "dev", "tests", "_testenv", "_oracle_test_support", "_output_memory")
        violations = []
        for rel in files:
            if rel.startswith("bin/") or not rel.endswith(".py"):
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
