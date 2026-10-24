# -*- coding: utf-8 -*-
"""Contexto do processo (CR-021c): app_context no lugar do gluon.current.

Confere o comportamento do modulo e a regra de arquitetura: nenhum arquivo de modules/ importa gluon,
nem dentro de funcao (AGENTS §5.2).
"""
import ast
import io
import os
import unittest

import _testenv  # noqa: F401 - ajusta sys.path sem importar gluon
import app_context

MODULES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules")


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

    def test_detector_finds_import_inside_function(self):
        """O detector acha o import tardio, que era a forma usada pelos services antes do CR-021c."""
        source = "def _service():\n    from gluon import current\n    return current\n"
        self.assertIn("gluon", _imported_roots(source))
        self.assertIn("gluon", _imported_roots("import gluon.utils\n"))
        self.assertNotIn("gluon", _imported_roots("from . import gluon_like\nimport app_context\n"))


if __name__ == "__main__":
    unittest.main()
