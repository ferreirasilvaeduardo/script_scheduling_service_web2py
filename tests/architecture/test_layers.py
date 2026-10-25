# -*- coding: utf-8 -*-
"""Ordem das camadas de src/sss (CR-022 §2b, conferida por AST; CR-022b9).

platform < core < config < persistence < ui < services < web; scheduler acima de persistence
(nao importa ui, services nem web); cli no topo. Uma camada so importa as de baixo, inclusive
dentro de funcao e por import relativo.
"""
import ast
import io
import os
import unittest

from tests.support import _testenv

SRC = os.path.join(_testenv.APP_DIR, "src")
_BASE = ("platform", "core", "config", "persistence")
ALLOWED = {
    "platform": set(),
    "core": {"platform"},
    "config": {"platform", "core"},
    "persistence": {"platform", "core", "config"},
    "ui": set(_BASE),
    "services": set(_BASE) | {"ui"},
    "scheduler": set(_BASE),
    "web": set(_BASE) | {"ui", "services"},
    "cli": set(_BASE) | {"ui", "services", "scheduler", "web"},
}


def _layer(module):
    """Camada de um modulo qualificado (sss.<camada>...), ou None fora de sss."""
    parts = module.split(".")
    return parts[1] if parts[0] == "sss" and len(parts) > 1 else None


def _imports(path, module):
    """Modulos absolutos importados pelo arquivo (inclusive os relativos, resolvidos)."""
    with io.open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    package = module if path.endswith("__init__.py") else module.rsplit(".", 1)[0]
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[:len(base) - (node.level - 1)]
                tail = [node.module] if node.module else []
                found.append((node.lineno, ".".join(base + tail)))
            else:
                found.append((node.lineno, node.module or ""))
    return found


def _violations(src_dir):
    problems = []
    for base, _dirs, files in os.walk(os.path.join(src_dir, "sss")):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, src_dir)
            module = rel[:-3].replace(os.sep, ".")
            if module.endswith(".__init__"):
                module = module[:-9]
            layer = _layer(module)
            if layer is None:
                continue
            for line, target in _imports(path, module):
                other = _layer(target)
                if other and other != layer and other not in ALLOWED.get(layer, set()):
                    problems.append("%s:%d: %s -> %s" % (rel, line, layer, other))
    return problems


class LayersTest(unittest.TestCase):

    def test_toda_camada_esta_no_mapa(self):
        layers = {d for d in os.listdir(os.path.join(SRC, "sss"))
                  if os.path.isdir(os.path.join(SRC, "sss", d)) and d != "__pycache__"}
        self.assertEqual(layers, set(ALLOWED))

    def test_camada_so_importa_as_de_baixo(self):
        self.assertEqual(_violations(SRC), [])

    def test_detector_negativo(self):
        """Caso negativo: import em funcao, relativo e de topo para camada de cima sao achados."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cases = (("sss/core", {"a.py": "def f():\n    from sss.services import x\n"}),
                     ("sss/scheduler", {"b.py": "from ..web import app\n"}),
                     ("sss/persistence", {"c.py": "import sss.ui.ui_helpers\n"}),
                     ("sss/services", {"d.py": "from sss.ui import ui_helpers\n"}))
            for folder, files in cases:
                os.makedirs(os.path.join(tmp, folder))
                for name, text in files.items():
                    with io.open(os.path.join(tmp, folder, name), "w", encoding="utf-8") as f:
                        f.write(text)
            found = sorted(p.split(": ", 1)[1] for p in _violations(tmp))
            self.assertEqual(found, ["core -> services", "persistence -> ui", "scheduler -> web"])


if __name__ == "__main__":
    unittest.main()
