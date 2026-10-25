# -*- coding: utf-8 -*-
"""Padrao D8 do codigo novo do CR-021, conferido por AST: src/sss/web/framework/ (nucleo), src/sss/web/app/
(montagem) e scripts/run_web.py (CR-022b7; antes modules/web/ e webapp/).

Linhas de ate 99 colunas; funcoes e metodos publicos com anotacoes de tipo e docstring; classes publicas
com docstring; imports entre modulos de um pacote so relativos. O nucleo so usa a biblioteca padrao; a
montagem e o run_web.py usam tambem as camadas abaixo da web e o nucleo, pelo modulo qualificado.
"""
import ast
import io
import os
import unittest

from tests.support import _testenv  # noqa: F401 - ajusta sys.path sem importar gluon

APP_DIR = _testenv.APP_DIR
PACKAGE_DIR = os.path.join(_testenv.WEB_DIR, "framework")
WEBAPP_DIR = os.path.join(_testenv.WEB_DIR, "app")
RUN_WEB = os.path.join(APP_DIR, "scripts", "run_web.py")
MAX_COLUMNS = 99
# Biblioteca padrao usada pelo pacote; modulo novo entra aqui de proposito (nunca dependencia de fora).
STDLIB = {
    "argparse", "ast", "base64", "binascii", "datetime", "decimal", "email", "errno", "hashlib", "hmac", "html", "http",
    "inspect", "io", "json", "logging", "mimetypes", "os", "posixpath", "re", "select", "signal", "socket",
    "socketserver", "stat", "sys", "tempfile", "threading", "time", "traceback", "types", "typing", "urllib",
    "uuid", "wsgiref",
}


# Camadas abaixo da web que a montagem usa (README §3.2, CR-022 §2b) e o nucleo web.
BELOW_WEB = {"sss.config", "sss.core", "sss.platform", "sss.persistence", "sss.ui", "sss.services",
             "sss.web.framework"}


def _allowed(name):
    """Modulos de import permitidos para o arquivo ``name`` (relativo): o proprio ou um prefixo dele."""
    if name.startswith("framework/"):
        return STDLIB
    if name.startswith("app/"):
        # O bootstrap registra os controllers por import explicito.
        return STDLIB | BELOW_WEB | {"sss.web.controllers"}
    return STDLIB | BELOW_WEB | {"sss.web.app"}


def _is_allowed(module, allowed):
    return any(module == prefix or module.startswith(prefix + ".") for prefix in allowed)


def _parse(path, key, result):
    with io.open(path, encoding="utf-8") as handle:
        text = handle.read()
    result[key] = (text, ast.parse(text, filename=key))


def _sources():
    """{caminho relativo: (texto, arvore)} do codigo novo do CR-021."""
    result = {}
    for prefix, folder in (("framework/", PACKAGE_DIR), ("app/", WEBAPP_DIR)):
        for name in sorted(os.listdir(folder)):
            if name.endswith(".py"):
                _parse(os.path.join(folder, name), prefix + name, result)
    _parse(RUN_WEB, "scripts/run_web.py", result)
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
        self.assertIn("framework/__init__.py", self.sources)
        self.assertIn("app/__init__.py", self.sources)

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
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        continue
                    modules = [node.module or ""]
                else:
                    continue
                allowed = _allowed(name)
                problems.extend("%s: import de %s" % (name, module) for module in modules
                                if not _is_allowed(module, allowed))
        self.assertEqual(problems, [])

    def test_all_matches_exports(self):
        """__all__ do pacote lista exatamente o que o __init__ importa."""
        _text, tree = self.sources["framework/__init__.py"]
        imported = {alias.asname or alias.name for node in tree.body if isinstance(node, ast.ImportFrom)
                    for alias in node.names}
        declared = set()
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "__all__" for t in node.targets):
                declared = {elt.s for elt in node.value.elts}
        self.assertEqual(declared, imported)


if __name__ == "__main__":
    unittest.main()
