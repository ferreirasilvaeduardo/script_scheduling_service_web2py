# -*- coding: utf-8 -*-
"""Pontos de entrada (CR-022b8, D6): scripts/*.py sao involucros de sss.cli e o unico codigo da aplicacao que
mexe no sys.path.

Cada scripts/<nome>.py, conferido por AST: docstring, ``import os`` e ``import sys``, o caminho de src/ calculado
a partir do proprio arquivo, um ``sys.path.insert``, ``from sss.cli.<nome> import main`` e
``sys.exit(main())`` sob ``if __name__ == "__main__"``. Todo modulo de src/sss/cli/ tem o seu involucro. Nenhum
.py de src/ toca o sys.path.
"""
import ast
import io
import os
import unittest

from tests.support import _testenv

SCRIPTS_DIR = os.path.join(_testenv.APP_DIR, "scripts")
CLI_DIR = os.path.join(_testenv.APP_DIR, "src", "sss", "cli")
SRC_DIR = os.path.join(_testenv.APP_DIR, "src")


def _parse(path):
    with io.open(path, encoding="utf-8") as handle:
        return ast.parse(handle.read(), filename=path)


def _dump(node):
    return ast.dump(node, annotate_fields=False)


def _expected_body(name):
    """Corpo esperado do involucro de ``name``, sem a docstring."""
    source = (
        "import os\n"
        "import sys\n"
        "_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')\n"
        "sys.path.insert(0, _SRC)\n"
        "from sss.cli.%s import main\n"
        "if __name__ == '__main__':\n"
        "    sys.exit(main())\n" % name)
    return [_dump(node) for node in ast.parse(source).body]


def _touches_sys_path(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "path" \
                and isinstance(node.value, ast.Name) and node.value.id == "sys":
            return True
    return False


class EntryPointsTest(unittest.TestCase):

    def setUp(self):
        self.wrappers = sorted(f[:-3] for f in os.listdir(SCRIPTS_DIR) if f.endswith(".py"))
        self.cli = sorted(f[:-3] for f in os.listdir(CLI_DIR) if f.endswith(".py") and f != "__init__.py")

    def test_um_involucro_por_ferramenta(self):
        """scripts/ e src/sss/cli/ tem os mesmos nomes; scripts/ so tem .py de involucro."""
        self.assertTrue(self.cli, "src/sss/cli/ sem ferramentas")
        self.assertEqual(self.wrappers, self.cli)
        others = sorted(f for f in os.listdir(SCRIPTS_DIR) if not f.endswith(".py") and f != "__pycache__")
        self.assertEqual(others, [])

    def test_involucro_tem_a_forma_fixa(self):
        problems = []
        for name in self.wrappers:
            tree = _parse(os.path.join(SCRIPTS_DIR, name + ".py"))
            if ast.get_docstring(tree) is None:
                problems.append("%s: sem docstring" % name)
            body = [_dump(node) for node in tree.body[1:]]
            if body != _expected_body(name):
                problems.append("%s: corpo fora do padrao do involucro" % name)
        self.assertEqual(problems, [])

    def test_nenhum_modulo_de_src_mexe_no_sys_path(self):
        offenders = []
        for base, _dirs, files in os.walk(SRC_DIR):
            for name in files:
                if name.endswith(".py") and _touches_sys_path(_parse(os.path.join(base, name))):
                    offenders.append(os.path.relpath(os.path.join(base, name), _testenv.APP_DIR))
        self.assertEqual(sorted(offenders), [])

    def test_detector_negativo(self):
        """Caso negativo: involucro com import a mais e modulo que mexe no sys.path sao achados."""
        extra = ast.parse('"""d"""\nimport os\nimport sys\nimport json\n')
        self.assertNotEqual([_dump(n) for n in extra.body[1:]], _expected_body("health"))
        self.assertTrue(_touches_sys_path(ast.parse("import sys\nsys.path.append('x')\n")))
        self.assertFalse(_touches_sys_path(ast.parse("import os\nos.path.join('a')\n")))


if __name__ == "__main__":
    unittest.main()
