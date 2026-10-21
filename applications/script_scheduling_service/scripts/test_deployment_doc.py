# -*- coding: utf-8 -*-
"""Coerencia do docs/DEPLOYMENT.md (F9.1d): todo bin/... e scripts/....py citado existe, e toda referencia
interna (§n ou §n.m) do corpo do guia aponta para uma secao que existe. O Apendice B (registros historicos) fica
de fora: as referencias dele sao da versao anterior do guia.
"""
import _testenv  # noqa: F401

import io
import os
import re
import unittest

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(_SCRIPTS)
RAIZ = os.path.dirname(os.path.dirname(APP))
GUIA = os.path.join(APP, "docs", "DEPLOYMENT.md")


def _corpo():
    with io.open(GUIA, encoding="utf-8") as f:
        texto = f.read()
    return texto.split("## Apêndice B.", 1)[0]


class TestGuiaDeImplantacao(unittest.TestCase):

    def test_comandos_citados_existem(self):
        corpo = _corpo()
        faltando = []
        for nome in sorted(set(re.findall(r"\bbin/([A-Za-z0-9_.-]+\.sh|sss-helper)\b", corpo))):
            if not os.path.isfile(os.path.join(RAIZ, "bin", nome)):
                faltando.append("bin/" + nome)
        for nome in sorted(set(re.findall(r"\bscripts/([A-Za-z0-9_]+\.py)\b", corpo))):
            if not os.path.isfile(os.path.join(APP, "scripts", nome)):
                faltando.append("scripts/" + nome)
        for nome in sorted(set(re.findall(r"\bdocs/sql/([0-9]{2}_[a-z_]+\.sql)\b", corpo))):
            if not os.path.isfile(os.path.join(APP, "docs", "sql", nome)) and nome != "03_grants_sss.sql":
                faltando.append("docs/sql/" + nome)
        self.assertEqual(faltando, [])

    def test_referencias_internas_existem(self):
        corpo = _corpo()
        secoes = set()
        for titulo in re.findall(r"(?m)^#{2,4} ([0-9]+(?:\.[0-9]+)*)\.? ", corpo):
            secoes.add(titulo)
        # Referencias "§n" fora de "README §n", "AGENTS §n" e "CR-... §n".
        invalidas = []
        for linha in corpo.splitlines():
            limpa = re.sub(r"(README(?:\.md)?|AGENTS(?:\.md)?|CR-\d+[^§]{0,12})\s*§[0-9.]+(?:\s*(?:e|a)\s*§?[0-9.]+)*", "", linha)
            for ref in re.findall(r"§([0-9]+(?:\.[0-9]+)*)", limpa):
                ref = ref.rstrip(".")
                if ref not in secoes:
                    invalidas.append((ref, linha.strip()[:90]))
        self.assertEqual(invalidas, [])

    def test_sem_procedimento_do_fake_no_corpo(self):
        corpo = _corpo()
        for termo in ("SSS_DEV_SEED_PASSWORD", "data_backend = FAKE", "skipped=23"):
            self.assertNotIn(termo, corpo)


if __name__ == "__main__":
    unittest.main()
