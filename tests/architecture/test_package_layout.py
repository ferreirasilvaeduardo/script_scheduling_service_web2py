# -*- coding: utf-8 -*-
"""Migracao para o pacote src/sss/ (CR-022b; docs/architecture/CR-022-standard-structure.md §2b).

Um modulo que ja esta em src/sss/ so e importado pelo nome qualificado (``from sss.core import masking``):
importado tambem pelo nome curto, ele seria carregado duas vezes, com classes de excecao duplicadas.
"""
from tests.support import _testenv  # noqa: F401 - ajusta sys.path

import ast
import io
import os
import re
import unittest

APP_DIR = _testenv.APP_DIR
SRC = os.path.join(APP_DIR, "src", "sss")
# Codigo que roda ou que testa (docs/ guarda historico; dev/scripts/ sao os scripts de exemplo do seed)
SKIP_DIRS = {".git", "__pycache__", "docs", "node_modules"}
_RE_TEMPLATE_IMPORT = re.compile(r"\{\{\s*(?:import|from)\s+([A-Za-z_]\w*)")


# Pastas que so agrupam modulos (as camadas e os contratos dos repositorios); qualquer outra pasta e um pacote
# que era importado pelo proprio nome (os_platform) ou pelo nome antigo (repo_oracle, repo_fake), e o que esta
# dentro dele nunca foi importavel pelo nome curto (oracle/health.py era repo_oracle.health).
GROUPING_DIRS = {"config", "core", "platform", "persistence", "contracts", "ui", "services", "scheduler", "web", "cli"}
OLD_PACKAGE_NAMES = {"oracle": "repo_oracle", "fake": "repo_fake", "framework": "web", "app": "webapp"}


def _moved_modules():
    """Nome curto (de antes do CR-022b) de todo modulo e pacote que ja esta em src/sss/."""
    names = set()
    for base, dirs, files in os.walk(SRC):
        packages = [d for d in dirs if d != "__pycache__" and d not in GROUPING_DIRS]
        names.update(OLD_PACKAGE_NAMES.get(d, d) for d in packages)
        dirs[:] = [d for d in dirs if d in GROUPING_DIRS]
        if base != SRC:
            names.update(os.path.splitext(f)[0] for f in files if f.endswith(".py") and f != "__init__.py")
    return names


def _code_files():
    for base, dirs, files in os.walk(APP_DIR):
        rel = os.path.relpath(base, APP_DIR).replace(os.sep, "/")
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not (rel == "dev" and d == "scripts")]
        for name in files:
            if name.endswith((".py", ".html", ".load")):
                yield os.path.join(base, name)


def _short_imports(path, moved):
    """(linha, nome) de todo import absoluto cuja raiz e um modulo ja movido para src/sss/."""
    with io.open(path, encoding="utf-8") as f:
        text = f.read()
    found = []
    if path.endswith(".py"):
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                roots = [(node.module or "").split(".")[0]]
                if roots == ["modules"]:
                    roots = [alias.name for alias in node.names]
            else:
                continue
            found.extend((node.lineno, root) for root in roots if root in moved)
    else:
        for num, line in enumerate(text.splitlines(), 1):
            found.extend((num, m) for m in _RE_TEMPLATE_IMPORT.findall(line) if m in moved)
    return found


class TestPackageLayout(unittest.TestCase):

    def test_modulo_movido_so_pelo_nome_qualificado(self):
        moved = _moved_modules()
        self.assertIn("sss_config", moved)
        offenders = []
        for path in _code_files():
            rel = os.path.relpath(path, APP_DIR).replace(os.sep, "/")
            offenders.extend("%s:%d: %s" % (rel, line, name) for line, name in _short_imports(path, moved))
        self.assertEqual(offenders, [])

    def test_modulo_em_um_lugar_so(self):
        """As pastas de antes do CR-022b nao voltam: o codigo da aplicacao fica so em src/sss/."""
        old = ("modules", "webapp", "controllers", "views", "static")
        self.assertEqual([d for d in old if os.path.exists(os.path.join(APP_DIR, d))], [])

    def test_nomes_antigos_registrados(self):
        """Regressao do CR-022b8: web e webapp (022b7) e as ferramentas de scripts/ (022b8) sao nomes movidos."""
        moved = _moved_modules()
        for name in ("web", "webapp", "controllers", "repo_oracle", "health", "purge", "init_db", "run_web"):
            self.assertIn(name, moved)

    def test_detector_pega_import_curto(self):
        """Caso negativo: o detector acha import, from, fallback de modules/ e import de template."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            py = os.path.join(tmp, "a.py")
            with io.open(py, "w", encoding="utf-8") as f:
                f.write("import os\nimport masking\nfrom sss_config import X\nfrom modules import rbac\n"
                        "from sss.core import masking as m\nfrom . import security\n")
            html = os.path.join(tmp, "a.html")
            with io.open(html, "w", encoding="utf-8") as f:
                f.write("<p>{{import masking\n}}</p>\n")
            moved = {"masking", "sss_config", "rbac", "security"}
            self.assertEqual(_short_imports(py, moved), [(2, "masking"), (3, "sss_config"), (4, "rbac")])
            self.assertEqual(_short_imports(html, moved), [(1, "masking")])


if __name__ == "__main__":
    unittest.main()
