# -*- coding: utf-8 -*-
"""Testes de verificacao do esqueleto do repositorio e ambiente (F0.1)."""
import os
import subprocess
import sys
import unittest

import _testenv


class TestEnvSkeleton(unittest.TestCase):
    """Bateria de testes para estrutura de diretorios, _testenv e check_env."""

    def setUp(self):
        self.scripts_dir = os.path.dirname(os.path.abspath(__file__))
        self.app_dir = os.path.dirname(self.scripts_dir)
        self.web2py_root = os.path.dirname(os.path.dirname(self.app_dir))

    def test_sys_path_configured(self):
        """Verifica se _testenv configurou app_dir e web2py_root em sys.path."""
        self.assertIn(self.app_dir, sys.path)
        self.assertIn(self.web2py_root, sys.path)

    def test_directory_skeleton_exists(self):
        """Verifica presenca de todos os diretorios requeridos pelo README §3.2."""
        expected_dirs = [
            os.path.join(self.web2py_root, "bin"),
            os.path.join(self.app_dir, "controllers"),
            os.path.join(self.app_dir, "models"),
            os.path.join(self.app_dir, "modules"),
            os.path.join(self.app_dir, "modules", "repo_fake"),
            os.path.join(self.app_dir, "modules", "repo_oracle"),
            os.path.join(self.app_dir, "scripts"),
            os.path.join(self.app_dir, "views"),
            os.path.join(self.app_dir, "views", "components"),
            os.path.join(self.app_dir, "static", "css"),
            os.path.join(self.app_dir, "static", "img"),
            os.path.join(self.app_dir, "static", "js", "app"),
            os.path.join(self.app_dir, "static", "fonts"),
            os.path.join(self.app_dir, "dev", "scripts"),
            os.path.join(self.app_dir, "instance"),
        ]
        for d in expected_dirs:
            self.assertTrue(os.path.isdir(d), "Diretorio ausente: %s" % d)

    def test_init_files_exist(self):
        """Verifica se pacotes python possuem __init__.py."""
        expected_inits = [
            os.path.join(self.app_dir, "modules", "__init__.py"),
            os.path.join(self.app_dir, "modules", "repo_fake", "__init__.py"),
            os.path.join(self.app_dir, "modules", "repo_oracle", "__init__.py"),
        ]
        for f in expected_inits:
            self.assertTrue(os.path.isfile(f), "Arquivo __init__.py ausente: %s" % f)

    def test_gitkeep_in_empty_dirs(self):
        """Verifica presenca de .gitkeep nos diretorios vazios requeridos."""
        expected_gitkeeps = [
            os.path.join(self.web2py_root, "bin", ".gitkeep"),
            os.path.join(self.app_dir, "controllers", ".gitkeep"),
            os.path.join(self.app_dir, "models", ".gitkeep"),
            os.path.join(self.app_dir, "views", "components", ".gitkeep"),
            os.path.join(self.app_dir, "static", "css", ".gitkeep"),
            os.path.join(self.app_dir, "static", "img", ".gitkeep"),
            os.path.join(self.app_dir, "static", "js", "app", ".gitkeep"),
            os.path.join(self.app_dir, "static", "fonts", ".gitkeep"),
            os.path.join(self.app_dir, "dev", "scripts", ".gitkeep"),
            os.path.join(self.app_dir, "instance", ".gitkeep"),
        ]
        for f in expected_gitkeeps:
            self.assertTrue(os.path.isfile(f), "Arquivo .gitkeep ausente: %s" % f)

    def test_gitignore_contains_required_rules(self):
        """Verifica regras obrigatorias no .gitignore da raiz."""
        gitignore_path = os.path.join(self.web2py_root, ".gitignore")
        self.assertTrue(os.path.isfile(gitignore_path), ".gitignore nao encontrado na raiz")
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()

        required_patterns = [
            "*.pyc",
            "__pycache__/",
            "applications/script_scheduling_service/sessions/",
            "applications/script_scheduling_service/errors/",
            "applications/script_scheduling_service/cache/",
            "applications/script_scheduling_service/databases/",
            "applications/script_scheduling_service/log/",
            "applications/script_scheduling_service/instance/config.ini",
            "*.log",
            "secrets.cfg",
            ".env",
        ]
        for p in required_patterns:
            self.assertIn(p, content, "Padrao ausente no .gitignore: %s" % p)

    def test_ambiente_dev_has_no_cdn(self):
        """Verifica se docs/AMBIENTE_DEV.md existe e nao contem URLs externas/CDN."""
        doc_path = os.path.join(self.app_dir, "docs", "AMBIENTE_DEV.md")
        self.assertTrue(os.path.isfile(doc_path), "docs/AMBIENTE_DEV.md ausente")
        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read()
        import re
        urls = re.findall(r"https?://[^\s)]+", content)
        self.assertEqual(urls, [], "URLs externas encontradas em AMBIENTE_DEV.md: %s" % urls)

    def test_check_env_success(self):
        """Executa check_env.py e verifica retorno 0 e presenca de OK."""
        cmd = [sys.executable, os.path.join(self.scripts_dir, "check_env.py")]
        proc = subprocess.Popen(
            cmd,
            cwd=self.app_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = proc.communicate()
        self.assertEqual(proc.returncode, 0, "check_env.py falhou: %s" % err.decode("utf-8", "replace"))
        out_str = out.decode("utf-8", "replace")
        self.assertIn("Versao do Python (3.6)", out_str)
        self.assertIn("Build CSP do Alpine.js", out_str)
        self.assertNotIn("FALHA", out_str)


if __name__ == "__main__":
    unittest.main()
