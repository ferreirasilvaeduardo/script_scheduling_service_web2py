# -*- coding: utf-8 -*-
"""Testes de verificacao do esqueleto do repositorio e ambiente (F0.1)."""
import os
import subprocess
import sys
import unittest

from tests.support import _testenv


TEST_PACKAGES = ("", "support", "unit", "unit/cli", "unit/config", "unit/core", "unit/persistence", "unit/platform",
                 "unit/scheduler", "unit/services", "unit/tools", "unit/ui", "unit/web", "integration",
                 "integration/oracle", "integration/process", "functional", "architecture")


class TestEnvSkeleton(unittest.TestCase):
    """Bateria de testes para estrutura de diretorios, _testenv e check_env."""

    def setUp(self):
        self.app_dir = _testenv.APP_DIR
        self.repo_root = self.app_dir  # CR-022a: a aplicacao e a raiz do repositorio

    def test_sys_path_configured(self):
        """_testenv poe app_dir, src/ e tools/ em sys.path; scripts/ so tem involucros (CR-022b8)."""
        self.assertIn(self.app_dir, sys.path)
        self.assertIn(os.path.join(self.app_dir, "src"), sys.path)
        self.assertIn(os.path.join(self.app_dir, "tools"), sys.path)
        self.assertNotIn(os.path.join(self.app_dir, "scripts"), sys.path)
        self.assertNotIn(os.path.join(self.app_dir, "modules"), sys.path)

    def test_directory_skeleton_exists(self):
        """Verifica presenca de todos os diretorios requeridos pelo README §3.2."""
        expected_dirs = [
            os.path.join(self.repo_root, "bin"),
            os.path.join(self.app_dir, "src", "sss", "web", "controllers"),
            os.path.join(self.app_dir, "src", "sss", "web", "app"),
            os.path.join(self.app_dir, "src", "sss", "cli"),
            os.path.join(self.app_dir, "src", "sss", "persistence", "fake"),
            os.path.join(self.app_dir, "src", "sss", "persistence", "oracle"),
            os.path.join(self.app_dir, "scripts"),
            os.path.join(self.app_dir, "tests"),
            os.path.join(self.app_dir, "tools"),
            os.path.join(self.app_dir, "src", "sss", "web", "templates"),
            os.path.join(self.app_dir, "src", "sss", "web", "templates", "components"),
            os.path.join(self.app_dir, "src", "sss", "web", "static", "css"),
            os.path.join(self.app_dir, "src", "sss", "web", "static", "img"),
            os.path.join(self.app_dir, "src", "sss", "web", "static", "js", "app"),
            os.path.join(self.app_dir, "src", "sss", "web", "static", "fonts"),
            os.path.join(self.app_dir, "dev", "scripts"),
            os.path.join(self.app_dir, "instance"),
        ]
        for d in expected_dirs:
            self.assertTrue(os.path.isdir(d), "Diretorio ausente: %s" % d)

    def test_init_files_exist(self):
        """Verifica se pacotes python possuem __init__.py."""
        expected_inits = [
            os.path.join(self.app_dir, "src", "sss", "cli", "__init__.py"),
            os.path.join(self.app_dir, "src", "sss", "persistence", "fake", "__init__.py"),
            os.path.join(self.app_dir, "src", "sss", "persistence", "oracle", "__init__.py"),
        ]
        # CR-022b1: no Python 3.6 o unittest so descobre testes em subpastas que sao pacotes
        expected_inits += [os.path.join(self.app_dir, "tests", d, "__init__.py") for d in TEST_PACKAGES]
        for f in expected_inits:
            self.assertTrue(os.path.isfile(f), "Arquivo __init__.py ausente: %s" % f)

    def test_gitkeep_in_empty_dirs(self):
        """Verifica presenca de .gitkeep nos diretorios vazios requeridos."""
        expected_gitkeeps = [
            os.path.join(self.repo_root, "bin", ".gitkeep"),
            os.path.join(self.app_dir, "src", "sss", "web", "controllers", ".gitkeep"),
            os.path.join(self.app_dir, "src", "sss", "web", "templates", "components", ".gitkeep"),
            os.path.join(self.app_dir, "src", "sss", "web", "static", "css", ".gitkeep"),
            os.path.join(self.app_dir, "src", "sss", "web", "static", "img", ".gitkeep"),
            os.path.join(self.app_dir, "src", "sss", "web", "static", "js", "app", ".gitkeep"),
            os.path.join(self.app_dir, "src", "sss", "web", "static", "fonts", ".gitkeep"),
            os.path.join(self.app_dir, "dev", "scripts", ".gitkeep"),
            os.path.join(self.app_dir, "instance", ".gitkeep"),
        ]
        for f in expected_gitkeeps:
            self.assertTrue(os.path.isfile(f), "Arquivo .gitkeep ausente: %s" % f)

    def test_gitignore_contains_required_rules(self):
        """Verifica regras obrigatorias no .gitignore da raiz."""
        gitignore_path = os.path.join(self.repo_root, ".gitignore")
        self.assertTrue(os.path.isfile(gitignore_path), ".gitignore nao encontrado na raiz")
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()

        required_patterns = [
            "*.pyc",
            "__pycache__/",
            "/instance/config.ini",
            "/instance/web.env",
            "/logs/",
            "/work/",
            # Sobras do web2py numa copia antiga (CR-021f): o hash da senha do painel dele
            "/parameters_*.py",
            "*.log",
            "secrets.cfg",
            ".env",
        ]
        for p in required_patterns:
            self.assertIn(p, content, "Padrao ausente no .gitignore: %s" % p)

    def test_ambiente_dev_has_no_cdn(self):
        """Verifica se docs/DEV_ENVIRONMENT.md existe e nao contem URLs externas/CDN."""
        doc_path = os.path.join(self.app_dir, "docs", "DEV_ENVIRONMENT.md")
        self.assertTrue(os.path.isfile(doc_path), "docs/DEV_ENVIRONMENT.md ausente")
        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read()
        import re
        urls = re.findall(r"https?://[^\s)]+", content)
        self.assertEqual(urls, [], "URLs externas encontradas em DEV_ENVIRONMENT.md: %s" % urls)

    def test_check_env_success(self):
        """Executa check_env.py e verifica retorno 0 e presenca de OK."""
        cmd = [sys.executable, os.path.join(self.app_dir, "scripts", "check_env.py")]
        proc = subprocess.Popen(
            cmd,
            cwd=self.app_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = proc.communicate()
        self.assertEqual(proc.returncode, 0, "check_env.py falhou: %s" % err.decode("utf-8", "replace"))
        out_str = out.decode("utf-8", "replace")
        self.assertIn("Versao do Python (>= 3.6.0)", out_str)
        self.assertIn("bootstrap.bundle.min.js", out_str)
        self.assertNotIn("FALHA", out_str)


if __name__ == "__main__":
    unittest.main()
