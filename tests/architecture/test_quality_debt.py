# -*- coding: utf-8 -*-
"""Catraca da divida de lint e de tipos (CR-022b9, D7): a lista so diminui.

* .flake8: 99 colunas; cada arquivo de per-file-ignores existe e, se ignora E501, ainda tem linha
  acima de 99 colunas (arquivo limpo sai da lista).
* pyproject.toml: mypy estrito; cada modulo da lista de divida (ignore_errors) existe.
* Os tetos abaixo so descem: ao pagar divida, apague a linha da lista e baixe o teto no mesmo
  commit.

O flake8 e o mypy nao rodam aqui (so existem no Python 3.11 da maquina de desenvolvimento): o
portao e o make lint e o make type-check com zero achados.
"""
import configparser
import io
import os
import re
import unittest

from tests.support import _testenv

APP_DIR = _testenv.APP_DIR
MAX_COLUMNS = 99
# Tetos medidos no CR-022b9 (2026-10-25); so podem descer.
FLAKE8_DEBT_MAX = 200
MYPY_DEBT_MAX = 107


def _flake8_debt(path=os.path.join(APP_DIR, ".flake8")):
    """(max-line-length, {arquivo: {codigos}}) do .flake8."""
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    section = parser["flake8"]
    debt = {}
    for line in section.get("per-file-ignores", "").splitlines():
        if line.strip():
            name, codes = line.split(":", 1)
            debt[name.strip()] = {c.strip() for c in codes.split(",") if c.strip()}
    return int(section["max-line-length"]), debt


def _mypy_config(path=os.path.join(APP_DIR, "pyproject.toml")):
    """(texto da secao [tool.mypy], modulos da lista de divida) do pyproject.toml."""
    with io.open(path, encoding="utf-8") as handle:
        text = handle.read()
    pattern = r"\[\[tool\.mypy\.overrides\]\]\s*module = \[(.*?)\]\s*ignore_errors = true"
    block = re.search(pattern, text, re.S)
    modules = re.findall(r'"([\w.]+)"', block.group(1)) if block else []
    return text, modules


def _has_long_line(path):
    with io.open(path, encoding="utf-8") as handle:
        return any(len(line.rstrip("\r\n")) > MAX_COLUMNS for line in handle)


def _module_exists(module):
    base = os.path.join(APP_DIR, "src", *module.split("."))
    return os.path.isfile(base + ".py") or os.path.isfile(os.path.join(base, "__init__.py"))


class QualityDebtTest(unittest.TestCase):

    def test_flake8_em_99_colunas_e_divida_real(self):
        max_length, debt = _flake8_debt()
        self.assertEqual(max_length, MAX_COLUMNS)
        self.assertLessEqual(len(debt), FLAKE8_DEBT_MAX, "a lista de divida do .flake8 so diminui")
        missing = sorted(name for name in debt if not os.path.isfile(os.path.join(APP_DIR, name)))
        self.assertEqual(missing, [], "arquivo inexistente na lista: apague a linha")
        paid = sorted(name for name, codes in debt.items()
                      if "E501" in codes and os.path.isfile(os.path.join(APP_DIR, name))
                      and not _has_long_line(os.path.join(APP_DIR, name)))
        self.assertEqual(paid, [], "sem linha acima de 99 colunas: tire o E501 do .flake8")

    def test_mypy_estrito_e_divida_real(self):
        text, modules = _mypy_config()
        self.assertRegex(text, r"(?m)^strict = true$")
        self.assertEqual(text.count("ignore_errors"), 1, "uma unica lista de divida do mypy")
        self.assertTrue(modules, "lista de divida do mypy nao encontrada no pyproject.toml")
        self.assertLessEqual(len(modules), MYPY_DEBT_MAX, "a lista de divida do mypy so diminui")
        self.assertEqual(sorted(m for m in modules if not _module_exists(m)), [],
                         "modulo inexistente na lista: apague a linha")
        self.assertEqual(len(modules), len(set(modules)))

    def test_detector_negativo(self):
        """Caso negativo: arquivo sem linha longa e acusado; o .flake8 de exemplo e lido."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            curto = os.path.join(tmp, "curto.py")
            longo = os.path.join(tmp, "longo.py")
            with io.open(curto, "w", encoding="utf-8") as f:
                f.write("x = 1\n")
            with io.open(longo, "w", encoding="utf-8") as f:
                f.write("x = '%s'\n" % ("a" * 100))
            self.assertFalse(_has_long_line(curto))
            self.assertTrue(_has_long_line(longo))
            cfg = os.path.join(tmp, ".flake8")
            with io.open(cfg, "w", encoding="utf-8") as f:
                f.write("[flake8]\nmax-line-length = 99\n"
                        "per-file-ignores =\n    a.py: E501,E127\n")
            self.assertEqual(_flake8_debt(cfg), (99, {"a.py": {"E501", "E127"}}))


if __name__ == "__main__":
    unittest.main()
