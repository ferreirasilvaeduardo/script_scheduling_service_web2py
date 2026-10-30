# -*- coding: utf-8 -*-
"""Makefile como porta unica da automacao (2026-10-30): todo script de automacao tem alvo,
todo alvo tem descricao (make help) e todo arquivo que um alvo chama existe.
"""
from tests.support import _testenv  # noqa: F401

import os
import re
import unittest

MAKEFILE = os.path.join(_testenv.APP_DIR, "Makefile")
HOMOLOG_TOOLS = os.path.join(_testenv.APP_DIR, "dev", "others", "homologation", "tools")
# Chamados pelo sss-ctl.sh e pelo cron no servidor, onde nao ha Makefile (o pacote nao o leva).
SERVER_LAUNCHERS = ("bin/sss-web.sh", "bin/sss-scheduler.sh", "bin/sss-stop.sh",
                    "bin/sss-keepalive.sh", "bin/sss-update.sh")
# Envolvidos pelos launchers: run_web pelo dev-start (start_local.sh) e pelo sss-web.sh;
# run_scheduler pelo sss-scheduler.sh.
WRAPPED_ENTRY_POINTS = ("scripts/run_web.py", "scripts/run_scheduler.py")
_RE_RULE = re.compile(r"^([a-zA-Z0-9_-]+):(?!=)(.*)$")
# O package chama a copia temporaria ("$$TMP/tools/package.py"): a barra antes e aceita.
_RE_PATH = re.compile(r"(?<![\w.$])((?:bin|scripts|tools|dev)/[\w./-]+\.(?:sh|py|js))")


def _read():
    with open(MAKEFILE, encoding="utf-8") as f:
        return f.read()


class TestMakefile(unittest.TestCase):

    def setUp(self):
        self.text = _read()
        # So as linhas de receita (com tab): a descricao ## tambem cita o script e nao conta.
        recipes = "\n".join(line for line in self.text.splitlines() if line.startswith("\t"))
        self.text_paths = recipes.replace("$(HOMOLOG_TOOLS)", "dev/others/homologation/tools")

    def test_todo_alvo_phony_tem_regra_com_descricao(self):
        phony = set()
        for line in self.text.splitlines():
            if line.startswith(".PHONY:"):
                phony.update(line.split(":", 1)[1].split())
        rules = {}
        for line in self.text.splitlines():
            m = _RE_RULE.match(line)
            if m:
                rules[m.group(1)] = m.group(2)
        self.assertTrue(phony)
        for target in sorted(phony):
            self.assertIn(target, rules, "alvo .PHONY sem regra: %s" % target)
            self.assertIn("## ", rules[target], "alvo sem descricao para o make help: %s" % target)

    def test_arquivos_chamados_existem(self):
        paths = set(_RE_PATH.findall(self.text_paths))
        self.assertIn("bin/sss-ctl.sh", paths)
        for rel in sorted(paths):
            self.assertTrue(os.path.isfile(os.path.join(_testenv.APP_DIR, rel)), rel)
        tools = re.findall(r"cd \$\(HOMOLOG_TOOLS\) && (?:node|\$\(PYTHON\)) ([\w.]+)", self.text)
        self.assertEqual(sorted(tools), ["build_evidence_docx.py", "capture_evidence.js"])
        for name in tools:
            self.assertTrue(os.path.isfile(os.path.join(HOMOLOG_TOOLS, name)), name)

    def test_todo_script_de_automacao_tem_alvo(self):
        referenced = set(_RE_PATH.findall(self.text_paths))
        candidates = []
        for folder, ext in (("bin", ".sh"), ("scripts", ".py"), ("tools", ".py")):
            for name in os.listdir(os.path.join(_testenv.APP_DIR, folder)):
                if name.endswith(ext):
                    candidates.append("%s/%s" % (folder, name))
        justified = SERVER_LAUNCHERS + WRAPPED_ENTRY_POINTS
        missing = [rel for rel in sorted(candidates)
                   if rel not in referenced and rel not in justified]
        self.assertEqual(missing, [], "script sem alvo no Makefile (nem na lista justificada)")

    def test_parametros_nao_vem_do_ambiente(self):
        # NAME e comum no ambiente (nome da maquina): com ?= o make o pegaria no lugar do processo.
        # A atribuicao simples do make vai em duas partes (o test_py36_compat a leria como walrus).
        simple = ":" + "="
        for var in ("NAME", "CMD", "OWNER", "PREFIX"):
            self.assertRegex(self.text, r"(?m)^%s %s " % (var, simple), var)


if __name__ == "__main__":
    unittest.main()
