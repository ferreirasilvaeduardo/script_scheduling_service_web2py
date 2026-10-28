# -*- coding: utf-8 -*-
"""Coerencia do docs/DEPLOYMENT.md (F9.1d): todo bin/... e scripts/....py citado existe, e toda referencia
interna (§n ou §n.m) do guia aponta para uma secao que existe. CR-032 (D15): o guia so tem o caminho real (um
usuario de SO e um de banco, sem root); os registros antigos foram para docs/architecture/DEPLOYMENT-history.md.
"""
from tests.support import _testenv  # noqa: F401

import io
import os
import re
import unittest

APP = _testenv.APP_DIR
ROOT = APP  # CR-022a: a aplicacao e a raiz do repositorio
GUIDE = os.path.join(APP, "docs", "DEPLOYMENT.md")


def _body():
    with io.open(GUIDE, encoding="utf-8") as f:
        text = f.read()
    return text


class TestDeploymentGuide(unittest.TestCase):

    def test_comandos_citados_existem(self):
        body = _body()
        missing = []
        for name in sorted(set(re.findall(r"\bbin/([A-Za-z0-9_.-]+\.sh)\b", body))):
            if not os.path.isfile(os.path.join(ROOT, "bin", name)):
                missing.append("bin/" + name)
        for folder in ("scripts", "tools"):
            for name in sorted(set(re.findall(r"\b%s/([A-Za-z0-9_]+\.py)\b" % folder, body))):
                if not os.path.isfile(os.path.join(APP, folder, name)):
                    missing.append(folder + "/" + name)
        # CR-024: <base>_<owner>_<prefixo>.sql; o 03_grants so existe com --grants-to (nao vai para docs/sql).
        for name in sorted(set(re.findall(r"\bdocs/sql/([0-9]{2}_[a-z_]+\.sql)\b", body))):
            if not os.path.isfile(os.path.join(APP, "docs", "sql", name)) and not name.startswith("03_grants_sss"):
                missing.append("docs/sql/" + name)
        self.assertEqual(missing, [])

    def test_referencias_internas_existem(self):
        body = _body()
        sections = set()
        for title in re.findall(r"(?m)^#{2,4} ([0-9]+(?:\.[0-9]+)*)\.? ", body):
            sections.add(title)
        # Referencias "§n" fora de "README §n", "AGENTS §n" e "CR-... §n".
        invalid = []
        for line in body.splitlines():
            clean = re.sub(r"(README(?:\.md)?|AGENTS(?:\.md)?|CR-\d+[^§]{0,12})\s*§[0-9.]+(?:\s*(?:e|a)\s*§?[0-9.]+)*", "", line)
            for ref in re.findall(r"§([0-9]+(?:\.[0-9]+)*)", clean):
                ref = ref.rstrip(".")
                if ref not in sections:
                    invalid.append((ref, line.strip()[:90]))
        self.assertEqual(invalid, [])

    def test_sem_procedimento_do_fake_no_corpo(self):
        body = _body()
        for term in ("SSS_DEV_SEED_PASSWORD", "data_backend = FAKE", "skipped=23"):
            self.assertNotIn(term, body)

    def test_cr032_guia_enxuto_e_raiz_compartilhada(self):
        """CR-032 (D15): sem systemd, sudo, helper nem o Apendice B; roteiro da raiz compartilhada com as regras."""
        body = _body()
        guide = body.split("### 18.2", 1)[0]
        for term in ("systemctl", "/etc/sudoers.d", "useradd", "sss-helper", "## Apêndice B"):
            self.assertFalse(term in guide, term)
        shared = body.split("### 4.1 Raiz compartilhada por vários servidores", 1)[1].split("### 4.2", 1)[0]
        for rule in ("Nome único por processo", "Cada agente roda sempre no mesmo servidor",
                     "Não mude um agente de servidor com ticket rodando", "Atualização com tudo parado em todos",
                     "`secrets.cfg` com todos os ambientes", "A mesma conta, com o mesmo UID",
                     "Webs com nome e porta próprios", "flock"):
            self.assertIn(rule, shared)
        history = os.path.join(APP, "docs", "architecture", "DEPLOYMENT-history.md")
        with io.open(history, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("## Parte 2. Apêndice B.", text)
        self.assertIn("Notas por versão (formato anterior ao CR-028)", text)


if __name__ == "__main__":
    unittest.main()
