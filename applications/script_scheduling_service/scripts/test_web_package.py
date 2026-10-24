# -*- coding: utf-8 -*-
"""Padrao do pacote modules/web/ (CR-021, D8), conferido por AST.

Linhas de ate 99 colunas; funcoes e metodos publicos com anotacoes de tipo e docstring; classes publicas
com docstring; imports entre modulos do pacote so relativos; nada fora da biblioteca padrao.
"""
import ast
import io
import os
import unittest

import _testenv  # noqa: F401 - ajusta sys.path sem importar gluon

PACKAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules", "web")
MAX_COLUMNS = 99
# Biblioteca padrao usada pelo pacote; modulo novo entra aqui de proposito (nunca dependencia de fora).
STDLIB = {
    "ast", "base64", "binascii", "datetime", "decimal", "email", "errno", "hashlib", "hmac", "html", "http",
    "io", "json", "logging", "mimetypes", "os", "posixpath", "re", "select", "signal", "socket",
    "socketserver", "stat", "sys", "tempfile", "threading", "time", "traceback", "typing", "urllib",
    "uuid", "wsgiref",
}


def _sources():
    """{nome do arquivo: (texto, arvore)} de todos os .py do pacote."""
    result = {}
    for name in sorted(os.listdir(PACKAGE_DIR)):
        if name.endswith(".py"):
            with io.open(os.path.join(PACKAGE_DIR, name), encoding="utf-8") as handle:
                text = handle.read()
            result[name] = (text, ast.parse(text, filename=name))
    return result


def _public_functions(tree):
    """(nome qualificado, no) das funcoes e metodos publicos (sem '_' no inicio; __init__ conta)."""
    found = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            found.append((node.name, node))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and (not item.name.startswith("_")
                                                          or item.name == "__init__"):
                    found.append(("%s.%s" % (node.name, item.name), item))
    return found


class PackageStyleTest(unittest.TestCase):
    """D8 no codigo novo do nucleo web."""

    def setUp(self):
        self.sources = _sources()
        self.assertIn("__init__.py", self.sources)

    def test_line_length(self):
        """Nenhuma linha passa de 99 colunas."""
        long_lines = ["%s:%d" % (name, number)
                      for name, (text, _tree) in self.sources.items()
                      for number, line in enumerate(text.splitlines(), 1) if len(line) > MAX_COLUMNS]
        self.assertEqual(long_lines, [])

    def test_public_api_is_typed_and_documented(self):
        """Toda funcao/metodo publico anota parametros e retorno e tem docstring (exceto __init__)."""
        problems = []
        for name, (_text, tree) in self.sources.items():
            for qualified, node in _public_functions(tree):
                args = node.args
                params = [a for a in args.args + args.kwonlyargs if a.arg not in ("self", "cls")]
                params += [a for a in (args.vararg, args.kwarg) if a is not None]
                if any(a.annotation is None for a in params) or node.returns is None:
                    problems.append("%s: %s sem anotacao" % (name, qualified))
                if not node.name.startswith("__") and ast.get_docstring(node) is None:
                    problems.append("%s: %s sem docstring" % (name, qualified))
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and not node.name.startswith("_") \
                        and ast.get_docstring(node) is None:
                    problems.append("%s: classe %s sem docstring" % (name, node.name))
            if ast.get_docstring(tree) is None:
                problems.append("%s: modulo sem docstring" % name)
        self.assertEqual(problems, [])

    def test_imports(self):
        """Dentro do pacote, so import relativo; de fora, so a biblioteca padrao (nunca gluon)."""
        problems = []
        for name, (_text, tree) in self.sources.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        continue
                    roots = [(node.module or "").split(".")[0]]
                else:
                    continue
                problems.extend("%s: import de %s" % (name, root) for root in roots if root not in STDLIB)
        self.assertEqual(problems, [])

    def test_all_matches_exports(self):
        """__all__ do pacote lista exatamente o que o __init__ importa."""
        _text, tree = self.sources["__init__.py"]
        imported = {alias.asname or alias.name for node in tree.body if isinstance(node, ast.ImportFrom)
                    for alias in node.names}
        declared = set()
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "__all__" for t in node.targets):
                declared = {elt.s for elt in node.value.elts}
        self.assertEqual(declared, imported)


if __name__ == "__main__":
    unittest.main()
