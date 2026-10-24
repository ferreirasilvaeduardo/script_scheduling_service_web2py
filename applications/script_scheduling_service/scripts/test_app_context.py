# -*- coding: utf-8 -*-
"""Contexto do processo (CR-021c): app_context no lugar do gluon.current.

Confere o comportamento do modulo e as regras de arquitetura: nenhum arquivo de modules/ importa
gluon, nem dentro de funcao (AGENTS §5.2); desde o CR-021f, nenhum .py da aplicacao (scripts,
testes e dev/ inclusive) nem dos launchers.
"""
import ast
import io
import os
import re
import unittest

import _testenv  # noqa: F401 - ajusta sys.path sem importar gluon
import app_context

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES_DIR = os.path.join(APP_DIR, "modules")
REPO_ROOT = os.path.dirname(os.path.dirname(APP_DIR))
# Codigo que roda: a aplicacao (sem docs/, que guarda o historico) e os launchers da raiz.
CODE_DIRS = (os.path.join(REPO_ROOT, "bin"),) + tuple(
    os.path.join(APP_DIR, name) for name in ("controllers", "modules", "scripts", "views", "webapp"))
_RE_OLD_CONTEXT = re.compile(r"\bcurrent\.(?:sss_cfg|repo_factory)\b")


def _imported_roots(source):
    """Devolve o primeiro nome de todo modulo importado no codigo, em qualquer nivel da AST."""
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
    return roots


class AppContextTest(unittest.TestCase):
    """Gravar, ler e exigir a configuracao do processo."""

    def setUp(self):
        self._previous = app_context.get_config()
        self.addCleanup(app_context.set_config, self._previous)

    def test_get_returns_what_was_set(self):
        """get_config devolve o objeto gravado, e None depois de desfeito."""
        cfg = object()
        app_context.set_config(cfg)
        self.assertIs(app_context.get_config(), cfg)
        app_context.set_config(None)
        self.assertIsNone(app_context.get_config())

    def test_require_fails_fast_without_config(self):
        """require_config sem configuracao interrompe com a causa na mensagem."""
        app_context.set_config(None)
        with self.assertRaises(RuntimeError) as ctx:
            app_context.require_config()
        self.assertIn("Configuracao ausente", str(ctx.exception))

    def test_require_returns_config(self):
        """require_config devolve a configuracao gravada."""
        cfg = {"app": {"sss_env": "DEV"}}
        app_context.set_config(cfg)
        self.assertIs(app_context.require_config(), cfg)


class ModulesWithoutGluonTest(unittest.TestCase):
    """Regra de arquitetura do CR-021c: modules/ nao depende do web2py."""

    def test_no_module_imports_gluon(self):
        """Nenhum .py de modules/ (inclusive subpacotes) importa gluon, nem dentro de funcao."""
        offenders = []
        for base, _dirs, files in os.walk(MODULES_DIR):
            for name in files:
                if name.endswith(".py"):
                    path = os.path.join(base, name)
                    with io.open(path, encoding="utf-8") as handle:
                        source = handle.read()
                    if "gluon" in _imported_roots(source):
                        offenders.append(os.path.relpath(path, MODULES_DIR))
        self.assertEqual(sorted(offenders), [])

    def test_no_python_file_imports_gluon(self):
        """CR-021f: sem web2py no repositorio; nenhum .py da aplicacao nem do bin/ importa gluon."""
        offenders = []
        roots = [(APP_DIR, ("docs",)), (os.path.join(REPO_ROOT, "bin"), ())]
        for top, skipped in roots:
            for base, dirs, files in os.walk(top):
                dirs[:] = [d for d in dirs
                           if not (base == top and d in skipped) and d != "__pycache__"]
                for name in files:
                    path = os.path.join(base, name)
                    if not (name.endswith(".py") or name == "sss-helper"):
                        continue
                    with io.open(path, encoding="utf-8") as handle:
                        source = handle.read()
                    if "gluon" in _imported_roots(source):
                        offenders.append(os.path.relpath(path, REPO_ROOT))
        self.assertEqual(sorted(offenders), [])

    def test_detector_finds_import_inside_function(self):
        """O detector acha o import tardio, que era a forma usada pelos services antes do CR-021c."""
        source = "def _service():\n    from gluon import current\n    return current\n"
        self.assertIn("gluon", _imported_roots(source))
        self.assertIn("gluon", _imported_roots("import gluon.utils\n"))
        self.assertNotIn("gluon", _imported_roots("from . import gluon_like\nimport app_context\n"))

    def test_no_code_reads_the_old_context(self):
        """Regressao: o bin/start_local.sh ainda lia current.sss_cfg depois do CR-021c e nao subia."""
        offenders = []
        this_file = os.path.abspath(__file__)
        for top in CODE_DIRS:
            for base, _dirs, files in os.walk(top):
                for name in files:
                    path = os.path.join(base, name)
                    if path == this_file or not name.endswith((".py", ".sh", ".html", ".load")):
                        continue
                    with io.open(path, encoding="utf-8", errors="replace") as handle:
                        if _RE_OLD_CONTEXT.search(handle.read()):
                            offenders.append(os.path.relpath(path, REPO_ROOT))
        self.assertEqual(sorted(offenders), [])


if __name__ == "__main__":
    unittest.main()
