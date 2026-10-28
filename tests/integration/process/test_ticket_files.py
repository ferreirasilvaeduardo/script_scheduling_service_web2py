# -*- coding: utf-8 -*-
"""Testes do ticket_files.py (CR-012, CR-014, CR-020c; CR-032, D7), executado como o agente o chama: validacao de
argumentos, pasta base, pack e clean-output sem seguir links, put-input e list-input."""
from tests.support import _testenv  # noqa: F401

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from sss.platform.os_platform import ticket_files as helper_module
from sss.platform.os_platform import TICKET_FILES as HELPER


def _load_helper():
    return helper_module


def _helper(*args, **kw):
    """Executa o ticket_files.py; devolve (codigo, stderr)."""
    p = subprocess.run([sys.executable, "-I", HELPER] + [str(a) for a in args], input=kw.get("entrada", b""),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    return p.returncode, p.stderr.decode("utf-8", "replace")


@unittest.skipIf(os.geteuid() == 0, "roda com a conta do agente, nunca root")
class TestTicketFiles(unittest.TestCase):

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="sss_ticket_files_"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # -- uso invalido ---------------------------------------------------------

    def test_uso_invalido(self):
        """CR-032 (D7): sem run, term, kill, clean nem stop-ticket (nao ha mais usuario de execucao)."""
        base = self._output_base()
        for args in ((), ("xyz",), ("run",), ("term", "100", "1"), ("kill", "100", "1"), ("clean", base, "1"),
                     ("stop-ticket", base, "1", "1"), ("list-input", base), ("put-input", base)):
            code, error = _helper(*args)
            self.assertEqual(code, 2, args)
            self.assertTrue(error.startswith("ticket_files: "), error)
            self.assertNotIn("Traceback", error)

    # -- pasta base -------------------------------------------------------------

    def test_pasta_base_invalida(self):
        base = self._output_base()
        link = os.path.join(self.root, "link_base")
        os.symlink(base, link)
        file = os.path.join(self.root, "arquivo")
        open(file, "w").close()
        rel = "carga/2026/10/20/14/05/ticket_4"
        os.makedirs(os.path.join(base, rel))
        for dir_value in ("producao", base + "/", os.path.join(base, "..", "producao"), link,
                          os.path.join(self.root, "nao_existe"), file, "/"):
            self.assertEqual(self._helper_output("clean-output", dir_value, rel)[0], 2, dir_value)
            self.assertEqual(self._helper_output("list-input", dir_value, "carga", 10)[0], 2, dir_value)
        self.assertTrue(os.path.isdir(os.path.join(base, rel)), "nada removido pela pasta recusada")

    def test_pasta_base_de_outro_dono(self):
        helper = _load_helper()
        with mock.patch.object(helper.os, "geteuid", return_value=os.geteuid() + 1):
            with self.assertRaises(helper.Failure) as ctx:
                helper._base_dir(self._output_base())
        self.assertEqual(ctx.exception.code, 2)

    def _output_base(self):
        base = os.path.join(self.root, "output", "producao")
        os.makedirs(base, 0o700)
        return base

    def _helper_output(self, *args):
        """Executa com a saida padrao capturada; devolve (codigo, stdout, stderr)."""
        p = subprocess.run([sys.executable, "-I", HELPER] + [str(a) for a in args], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=60)
        return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace")

    # ------------------------------------------------------------ CR-020c: put-input e list-input

    def _input_base(self):
        base = os.path.join(self.root, "input", "producao")
        os.makedirs(base, 0o700, exist_ok=True)
        return base

    def _put(self, base, data, relative="lotes/2026", name="cliente.csv", replace="N", sha=None, size=None):
        import hashlib
        sha = sha or hashlib.sha256(data).hexdigest()
        return _helper("put-input", base, "carga_diaria", relative, name, replace, sha,
                       len(data) if size is None else size, entrada=data)

    def test_cr020_put_input_grava_cria_subpastas_e_nao_substitui(self):
        base = self._input_base()
        code, error = self._put(base, b"a;b\n1;2\n")
        self.assertEqual(code, 0, error)
        final = os.path.join(base, "carga_diaria", "lotes", "2026", "cliente.csv")
        with open(final, "rb") as f:
            self.assertEqual(f.read(), b"a;b\n1;2\n")
        self.assertEqual(os.stat(final).st_mode & 0o777, 0o600)
        for folder in ("carga_diaria", "carga_diaria/lotes", "carga_diaria/lotes/2026"):
            self.assertEqual(os.stat(os.path.join(base, folder)).st_mode & 0o777, 0o700, folder)
        # sem substituir: o existente fica, codigo 9
        self.assertEqual(self._put(base, b"novo")[0], 9)
        with open(final, "rb") as f:
            self.assertEqual(f.read(), b"a;b\n1;2\n")
        # substituindo
        self.assertEqual(self._put(base, b"novo", replace="Y")[0], 0)
        with open(final, "rb") as f:
            self.assertEqual(f.read(), b"novo")
        # sem subpasta
        self.assertEqual(self._put(base, b"x", relative="-", name="raiz.txt")[0], 0)
        self.assertTrue(os.path.isfile(os.path.join(base, "carga_diaria", "raiz.txt")))
        leftovers = [n for n in os.listdir(os.path.join(base, "carga_diaria", "lotes", "2026")) if n.startswith(".")]
        self.assertEqual(leftovers, [], "nenhum temporario fica no destino")

    def test_cr020_put_input_hash_tamanho_e_nomes_invalidos(self):
        base = self._input_base()
        self.assertEqual(self._put(base, b"conteudo", sha="0" * 64)[0], 11, "hash divergente")
        self.assertEqual(self._put(base, b"conteudo", size=3)[0], 11, "tamanho divergente")
        self.assertFalse(os.path.exists(os.path.join(base, "carga_diaria", "lotes", "2026", "cliente.csv")))
        for relative, name in (("../fora", "a.txt"), ("lotes", "../a.txt"), ("lotes", ".oculto"),
                               ("a/./b", "x.txt"), ("lotes", "a\tb"), ("/".join(["n"] * 11), "x.txt"),
                               ("lotes", "x" * 256)):
            self.assertEqual(self._put(base, b"x", relative=relative, name=name)[0], 2, (relative, name))
        self.assertEqual(_helper("put-input", base, "Maiuscula", "-", "a.txt", "N", "0" * 64, 1, entrada=b"x")[0], 2)
        self.assertEqual(_helper("put-input", base, "carga_diaria", "-", "a.txt", "S", "0" * 64, 1, entrada=b"x")[0], 2)

    def test_cr020_put_input_recusa_link_e_destino_que_nao_e_arquivo(self):
        base = self._input_base()
        outside = os.path.join(self.root, "fora_entrada_tela")
        os.mkdir(outside)
        os.makedirs(os.path.join(base, "carga_diaria"), 0o700)
        os.symlink(outside, os.path.join(base, "carga_diaria", "ligada"))
        self.assertEqual(self._put(base, b"x", relative="ligada")[0], 2, "link na subpasta")
        self.assertEqual(os.listdir(outside), [])
        os.makedirs(os.path.join(base, "carga_diaria", "pasta.txt"))
        self.assertEqual(self._put(base, b"x", relative="-", name="pasta.txt", replace="Y")[0], 2,
                         "substituir uma pasta")
        self.assertEqual(self._put(base, b"x", relative="-", name="pasta.txt")[0], 9, "sem substituir: ja existe")

    def test_cr020_list_input_sem_links_sem_temporarios_e_com_teto(self):
        import json
        base = self._input_base()
        self.assertEqual(json.loads(self._helper_output("list-input", base, "carga_diaria", 10)[1]),
                         {"files": [], "count": 0, "truncated": False}, "pasta ainda inexistente")
        folder = os.path.join(base, "carga_diaria")
        os.makedirs(os.path.join(folder, "sub"), 0o700)
        for name in ("a.txt", "sub/b.txt", ".sss_upload_99.tmp", "c.txt"):
            with open(os.path.join(folder, name), "w") as f:
                f.write("12345")
        outside = os.path.join(self.root, "fora_lista")
        os.makedirs(outside)
        open(os.path.join(outside, "segredo.txt"), "w").close()
        os.symlink(outside, os.path.join(folder, "ligada"))
        os.symlink(os.path.join(outside, "segredo.txt"), os.path.join(folder, "link.txt"))
        code, out, error = self._helper_output("list-input", base, "carga_diaria", 10)
        self.assertEqual(code, 0, error)
        data = json.loads(out)
        self.assertEqual([f["path"] for f in data["files"]], ["a.txt", "c.txt", "sub/b.txt"])
        self.assertEqual((data["count"], data["truncated"], data["files"][0]["size"]), (3, False, 5))
        data = json.loads(self._helper_output("list-input", base, "carga_diaria", 2)[1])
        self.assertEqual((len(data["files"]), data["count"], data["truncated"]), (2, 3, True))
        self.assertEqual(self._helper_output("list-input", base, "carga_diaria", 0)[0], 2)

    def _fill(self, base, rel, files):
        dir_value = os.path.join(base, rel)
        os.makedirs(dir_value, 0o700)
        for name, data in files.items():
            path = os.path.join(dir_value, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        return dir_value

    def test_relativo_de_pastas_log_passa(self):
        import datetime
        from sss.config import log_paths
        helper = _load_helper()
        dt = datetime.datetime(2026, 1, 2, 3, 4)
        for name in (u"Carga Diária", u"-x-", u"a.b_c", u"!!!", u"x" * 60, u"Relatório 2026 (v2)"):
            _base, rel = log_paths.output_dir("/s", "PRODUCAO", name, dt, 99, script_id=5)
            self.assertEqual(len(helper._relative_parts(rel)), 7, rel)

    def test_empacotar_so_arquivos_regulares_sem_seguir_links(self):
        import io
        import zipfile
        base = self._output_base()
        rel = "carga/2026/10/20/14/05/ticket_7"
        dir_value = self._fill(base, rel, {"a.txt": b"um", "sub/b.csv": b"x;y\n" * 1000})
        secret = os.path.join(self.root, "segredo.txt")
        with open(secret, "w") as f:
            f.write("nao pode sair")
        os.symlink(secret, os.path.join(dir_value, "link.txt"))
        os.symlink(self.root, os.path.join(dir_value, "link_pasta"))
        os.mkfifo(os.path.join(dir_value, "fifo"))
        code, zip_, error = self._helper_output("pack", base, rel, 1048576, 10)
        self.assertEqual(code, 0, error)
        z = zipfile.ZipFile(io.BytesIO(zip_))
        self.assertEqual(sorted(z.namelist()), ["a.txt", "sub/b.csv"])
        self.assertEqual(z.read("sub/b.csv"), b"x;y\n" * 1000)
        self.assertIsNone(z.testzip())

    def test_empacotar_vazia_e_limites(self):
        base = self._output_base()
        rel = "carga/2026/10/20/14/05/ticket_8"
        self.assertEqual(self._helper_output("pack", base, rel, 1048576, 10)[0], 6, "inexistente")
        dir_value = self._fill(base, rel, {})
        os.makedirs(os.path.join(dir_value, "so_pastas"))
        self.assertEqual(self._helper_output("pack", base, rel, 1048576, 10)[0], 6, "vazia")
        self._fill(base, "carga/2026/10/20/14/05/ticket_9", dict(("f%02d" % i, b"x") for i in range(11)))
        code, _zip, error = self._helper_output("pack", base, "carga/2026/10/20/14/05/ticket_9", 1048576, 10)
        self.assertEqual(code, 7, error)
        self.assertIn("arquivos", error)
        self.assertEqual(self._helper_output("pack", base, "carga/2026/10/20/14/05/ticket_9", 1048576, 11)[0], 0)
        self._fill(base, "carga/2026/10/20/14/05/ticket_10", {"grande.bin": os.urandom(2 * 1024 * 1024)})
        code, _zip, error = self._helper_output("pack", base, "carga/2026/10/20/14/05/ticket_10", 1048576, 10)
        self.assertEqual(code, 8, error)
        self.assertIn("bytes", error)
        for args in (("pack", base, rel, 0, 10), ("pack", base, rel, 1048576, 0),
                     ("pack", base, rel, 209715201, 10), ("pack", base, rel, 1, 10001),
                     ("pack", base, "../x/2026/10/20/14/05/ticket_8", 1048576, 10),
                     ("pack", base, rel, 1048576), ("clean-output", base), ("purge-output", base, "0"),
                     ("purge-output", base, "7", "remover")):
            self.assertEqual(self._helper_output(*args)[0], 2, args)

    def test_limpar_saida_sem_seguir_links(self):
        base = self._output_base()
        rel = "carga/2026/10/20/14/05/ticket_11"
        dir_value = self._fill(base, rel, {"a.txt": b"1"})
        outside = os.path.join(self.root, "fora2")
        os.mkdir(outside)
        with open(os.path.join(outside, "manter.txt"), "w") as f:
            f.write("x")
        os.symlink(outside, os.path.join(dir_value, "link"))
        self.assertEqual(self._helper_output("clean-output", base, rel)[0], 0)
        self.assertFalse(os.path.exists(dir_value))
        self.assertTrue(os.path.exists(os.path.join(outside, "manter.txt")))
        self.assertTrue(os.path.isdir(os.path.dirname(dir_value)), "as pastas acima ficam (limpeza manual, README §11.3)")
        self.assertEqual(self._helper_output("clean-output", base, rel)[0], 0, "ja removida")

    def test_cr030_sem_purge_output(self):
        """CR-030: o subcomando purge-output saiu (limpeza manual, README §11.3)."""
        code, _out = self._helper_output("purge-output", self._output_base(), "7")[:2]
        self.assertEqual(code, 2)

    def test_compila_e_nao_importa_a_aplicacao(self):
        with open(HELPER, encoding="utf-8") as f:
            source = f.read()
        compile(source, HELPER, "exec")
        for forbidden in ("import gluon", "import sss_", "from sss", "import sss", "import os_platform", "config.ini\""):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
