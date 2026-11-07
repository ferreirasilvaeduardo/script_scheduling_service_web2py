# -*- coding: utf-8 -*-
"""Testes do utilitario scripts_ambiente/utilitarios/zipar_arquivos.py.

Referencia: docs/UTILITY_SCRIPTS.md §4.1.

O script roda como processo filho no mesmo Python da bateria (sys.executable): no 3.6
exercita o gravador proprio (_GravadorZip36), no 3.7+ o compresslevel do zipfile.
Confere: niveis 1 e 9 geram ZIP valido (zipfile e unzip -t, se existir) com conteudo
identico ao da origem, inclusive um arquivo de alguns MiB; o nivel 1 gera ZIP maior que
o nivel 9 num conteudo compressivel (o nivel e aplicado); nivel 0, 10 e "x" saem com 2
sem criar o ZIP. O gravador do 3.6 tambem e testado diretamente em qualquer versao,
importado num processo filho.
"""
from tests.support import _testenv  # noqa: F401

import filecmp
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

SCRIPT = os.path.join(_testenv.APP_DIR, "scripts_ambiente", "utilitarios", "zipar_arquivos.py")
UNZIP = shutil.which("unzip")


# Grava com o _GravadorZip36 do script, importado num processo filho
# (sem mexer no sys.path da bateria)
_GRAVADOR_DIRETO = """
import os, sys
sys.path.insert(0, os.path.dirname(sys.argv[1]))
import zipar_arquivos
origem, destino, nivel = sys.argv[2], sys.argv[3], int(sys.argv[4])
with zipar_arquivos._GravadorZip36(destino, nivel) as zf:
    for raiz, _, arquivos in os.walk(origem):
        for arq in arquivos:
            caminho = os.path.join(raiz, arq)
            zf.write(caminho, arcname=os.path.relpath(caminho, origem))
"""


def _texto_compressivel(tamanho, semente):
    """Texto de palavras sorteadas: comprime bem e de forma diferente entre os niveis 1 e 9."""
    rnd = random.Random(semente)
    palavras = ["registro", "arquivo", "agente", "ticket", "oracle", "saida", "entrada",
                "processo", "%05d", "valor", "total", "status", "linha", "campo"]
    partes = []
    total = 0
    while total < tamanho:
        palavra = rnd.choice(palavras)
        if "%" in palavra:
            palavra = palavra % rnd.randint(0, 99999)
        linha = ";".join([palavra] * rnd.randint(1, 4)) + " %d\n" % rnd.randint(0, 999)
        partes.append(linha)
        total += len(linha)
    return "".join(partes).encode("ascii")[:tamanho]


class TestZiparArquivos(unittest.TestCase):

    def setUp(self):
        self.raiz = os.path.realpath(tempfile.mkdtemp(prefix="sss_test_zipar_"))
        self.addCleanup(shutil.rmtree, self.raiz, True)
        self.origem = os.path.join(self.raiz, "origem")
        os.makedirs(os.path.join(self.origem, "sub", "interna"))
        self._gravar("pequeno.txt", b"linha 1\nlinha 2\n")
        self._gravar("vazio.dat", b"")
        grande = _texto_compressivel(3 * 1024 * 1024 + 123, 7)
        self._gravar(os.path.join("sub", "grande.csv"), grande)
        self._gravar(os.path.join("sub", "interna", "binario.bin"), os.urandom(70000))
        self._gravar(os.path.join("sub", "relatório.txt"), "ação\n".encode("utf-8") * 50)

    def _gravar(self, relativo, conteudo):
        with open(os.path.join(self.origem, relativo), "wb") as f:
            f.write(conteudo)

    def _rodar(self, destino, nivel):
        return subprocess.run(
            [sys.executable, SCRIPT, "--origem", self.origem, "--destino", destino,
             "--nivel", nivel],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=300)

    def _conferir_zip(self, destino):
        with zipfile.ZipFile(destino) as zf:
            self.assertIsNone(zf.testzip())
            for info in zf.infolist():
                self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED)
            extraido = os.path.join(self.raiz, "extraido_" + os.path.basename(destino))
            zf.extractall(extraido)
        comparacao = filecmp.dircmp(self.origem, extraido)
        self._sem_diferencas(comparacao)
        for raiz, _, arquivos in os.walk(self.origem):
            for arq in arquivos:
                caminho = os.path.join(raiz, arq)
                copia = os.path.join(extraido, os.path.relpath(caminho, self.origem))
                self.assertTrue(filecmp.cmp(caminho, copia, shallow=False), caminho)
        if UNZIP:
            res = subprocess.run([UNZIP, "-t", destino], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, universal_newlines=True)
            self.assertEqual(res.returncode, 0, res.stdout)

    def _sem_diferencas(self, comparacao):
        self.assertEqual(comparacao.left_only, [])
        self.assertEqual(comparacao.right_only, [])
        self.assertEqual(comparacao.diff_files, [])
        for sub in comparacao.subdirs.values():
            self._sem_diferencas(sub)

    def test_niveis_1_e_9_geram_zip_valido_e_nivel_aplicado(self):
        tamanhos = {}
        for nivel in ("1", "9"):
            destino = os.path.join(self.raiz, "saida", "nivel%s.zip" % nivel)
            res = self._rodar(destino, nivel)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("Nivel:   %s" % nivel, res.stdout)
            self.assertIn("Arquivos arquivados: 5", res.stdout)
            self._conferir_zip(destino)
            tamanhos[nivel] = os.path.getsize(destino)
        self.assertGreater(tamanhos["1"], tamanhos["9"])

    def test_nivel_invalido_sai_com_2_sem_criar_zip(self):
        for nivel in ("0", "10", "x"):
            destino = os.path.join(self.raiz, "saida_invalida", "nivel_%s.zip" % nivel)
            res = self._rodar(destino, nivel)
            self.assertEqual(res.returncode, 2, nivel)
            self.assertIn("nivel de compressao invalido", res.stderr)
            self.assertFalse(os.path.exists(destino), nivel)

    def test_gravador_do_36_direto(self):
        tamanhos = {}
        for nivel in (1, 9):
            destino = os.path.join(self.raiz, "direto%d.zip" % nivel)
            res = subprocess.run(
                [sys.executable, "-c", _GRAVADOR_DIRETO, SCRIPT, self.origem, destino, str(nivel)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                timeout=300)
            self.assertEqual(res.returncode, 0, res.stderr)
            self._conferir_zip(destino)
            tamanhos[nivel] = os.path.getsize(destino)
        self.assertGreater(tamanhos[1], tamanhos[9])


if __name__ == "__main__":
    unittest.main()
