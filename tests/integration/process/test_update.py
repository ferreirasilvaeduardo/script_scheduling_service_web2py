# -*- coding: utf-8 -*-
"""bin/sss-update.sh (CR-028, D10): atualizacao no lugar.

Preserva instance/<nome>/, var/ e scripts_ambiente/."""
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest

from tests.support import _testenv

UPDATE = os.path.join(_testenv.APP_DIR, "bin", "sss-update.sh")


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


@unittest.skipIf(os.geteuid() == 0, "o comando recusa root")
class TestUpdate(unittest.TestCase):

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sss_test_update_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.app = os.path.join(self.tmp, "script_scheduling_service")
        self._code(self.app, "v1")
        shutil.copy2(UPDATE, os.path.join(self.app, "bin", "sss-update.sh"))
        _write(os.path.join(self.app, "instance", "agente0001", "config.ini"), "LOCAL\n")
        _write(os.path.join(self.app, "instance", "agente0001", "secrets.cfg"), "SEGREDO\n")
        _write(os.path.join(self.app, "var", "agente0001", "logs", "a.log"), "LOG\n")
        _write(os.path.join(self.app, "scripts_ambiente", "carga.py"), "SCRIPT\n")

    def _code(self, root, version):
        for rel in ("src/sss/versao.txt", "scripts/run_web.py", "docs/DEPLOYMENT.md", "README.md",
                    "AGENTS.md", "bin/sss-web.sh", "instance/config.ini.example",
                    "instance/exemplos/web0001/config.ini.example"):
            _write(os.path.join(root, rel), "%s %s\n" % (rel, version))

    def _package(self, version):
        """Pacote no formato do tools/package.py: sss-<versao>/, SHA256SUMS interno e externo."""
        dist = os.path.join(self.tmp, "dist_" + version)
        top = os.path.join(dist, "sss-" + version)
        self._code(top, version)
        shutil.copy2(UPDATE, os.path.join(top, "bin", "sss-update.sh"))
        lines = []
        for folder, _dirs, files in os.walk(top):
            for name in files:
                full = os.path.join(folder, name)
                lines.append("%s  %s" % (_sha(full), os.path.relpath(full, top)))
        lines.sort(key=lambda x: x.split("  ")[1])
        _write(os.path.join(top, "SHA256SUMS"), "\n".join(lines) + "\n")
        tar = os.path.join(dist, "sss-%s.tar.gz" % version)
        with tarfile.open(tar, "w:gz") as t:
            t.add(top, arcname="sss-" + version)
        shutil.rmtree(top)
        _write(os.path.join(dist, "SHA256SUMS"), "%s  %s\n" % (_sha(tar), os.path.basename(tar)))
        return tar

    def _run(self, *args):
        p = subprocess.run([os.path.join(self.app, "bin", "sss-update.sh")] + list(args),
                           cwd="/", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        out, err = (b.decode("utf-8", "replace") for b in (p.stdout, p.stderr))
        return p.returncode, out, err

    def _preserved(self):
        expected = {("instance", "agente0001", "config.ini"): "LOCAL\n",
                    ("instance", "agente0001", "secrets.cfg"): "SEGREDO\n",
                    ("var", "agente0001", "logs", "a.log"): "LOG\n",
                    ("scripts_ambiente", "carga.py"): "SCRIPT\n"}
        for parts, text in expected.items():
            self.assertEqual(_read(os.path.join(self.app, *parts)), text, parts)

    def test_atualiza_preserva_e_volta_pelo_pacote_de_retorno(self):
        code, out, err = self._run(self._package("v2"))
        self.assertEqual(code, 0, err)
        for rel in ("src/sss/versao.txt", "README.md", "instance/config.ini.example",
                    "instance/exemplos/web0001/config.ini.example"):
            self.assertIn("v2", _read(os.path.join(self.app, rel)), rel)
        self._preserved()
        back = out.strip().splitlines()[-1].split()[-1]
        self.assertTrue(back.endswith(".tar.gz") and os.path.isfile(back), out)
        self.assertTrue(back.startswith(os.path.join(self.app, "var", "update")))
        code, _out, err = self._run(back)
        self.assertEqual(code, 0, err)
        self.assertIn("v1", _read(os.path.join(self.app, "src", "sss", "versao.txt")))
        self.assertIn("v1", _read(os.path.join(self.app, "instance", "config.ini.example")))
        self._preserved()

    def test_pacote_que_nao_confere_nao_muda_nada(self):
        tar = self._package("v2")
        sums = os.path.join(os.path.dirname(tar), "SHA256SUMS")
        _write(sums, "%s  %s\n" % ("0" * 64, os.path.basename(tar)))
        code, _out, err = self._run(tar)
        self.assertEqual(code, 2)
        self.assertIn("nao confere", err)
        self.assertIn("v1", _read(os.path.join(self.app, "src", "sss", "versao.txt")))
        self.assertEqual(self._run("/nao/existe.tar.gz")[0], 2)

    def test_retorno_absoluto_e_sem_pasta_temporaria(self):
        """Revisao do CR-028 (M3, B5): retorno absoluto em var/update; .update-<data> removida."""
        code, out, err = self._run(self._package("v2"))
        self.assertEqual(code, 0, err)
        line = out.strip().splitlines()[-1]
        self.assertTrue(line.startswith("Retorno: %s/bin/sss-update.sh " % self.app), line)
        self.assertEqual([n for n in os.listdir(self.app) if n.startswith(".update-")], [])

    def test_sha256sums_interno_divergente_e_pasta_inexistente(self):
        """SHA256SUMS interno divergente: codigo 2, nada muda; pasta do pacote inexistente: 2."""
        tar = self._package("v2")
        work = os.path.join(self.tmp, "mexido")
        with tarfile.open(tar) as t:
            t.extractall(work)
        _write(os.path.join(work, "sss-v2", "README.md"), "alterado\n")
        with tarfile.open(tar, "w:gz") as t:
            t.add(os.path.join(work, "sss-v2"), arcname="sss-v2")
        _write(os.path.join(os.path.dirname(tar), "SHA256SUMS"),
               "%s  %s\n" % (_sha(tar), os.path.basename(tar)))
        code, _out, err = self._run(tar)
        self.assertEqual(code, 2, err)
        self.assertIn("SHA256SUMS interno", err)
        self.assertIn("v1", _read(os.path.join(self.app, "README.md")))
        self.assertEqual(self._run("/nao/existe/pacote.tar.gz")[0], 2)

    def test_raiz_por_link_simbolico_ainda_detecta_processo(self):
        """Revisao do CR-028 (M1): chamado por um link para a raiz, o processo e detectado."""
        link = os.path.join(self.tmp, "atalho")
        os.symlink(self.app, link)
        _write(os.path.join(self.app, "scripts", "run_web.py"), "import time\ntime.sleep(30)\n")
        proc = subprocess.Popen([sys.executable, "scripts/run_web.py"], cwd=self.app)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        time.sleep(0.5)
        p = subprocess.run([os.path.join(link, "bin", "sss-update.sh"), self._package("v2")],
                           cwd="/",
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        self.assertEqual(p.returncode, 3, p.stderr)

    def test_outro_programa_com_o_nome_do_script_nao_bloqueia(self):
        """Revisao do CR-028 (B6): so um python rodando o comando conta ('tail' do arquivo nao)."""
        proc = subprocess.Popen(["tail", "-f", "scripts/run_web.py"], cwd=self.app,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        time.sleep(0.3)
        code, _out, err = self._run(self._package("v2"))
        self.assertEqual(code, 0, err)

    def test_recusa_com_processo_do_sss_rodando_na_pasta(self):
        _write(os.path.join(self.app, "scripts", "run_web.py"), "import time\ntime.sleep(30)\n")
        proc = subprocess.Popen([sys.executable, "scripts/run_web.py"], cwd=self.app)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        time.sleep(0.5)
        code, _out, err = self._run(self._package("v2"))
        self.assertEqual(code, 3, err)
        self.assertIn("processo do SSS em execucao", err)
        self.assertIn("v1", _read(os.path.join(self.app, "src", "sss", "versao.txt")))


if __name__ == "__main__":
    unittest.main()
