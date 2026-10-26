# -*- coding: utf-8 -*-
"""Testes de path_guard.py: README §8.5 e AGENTS §7.4 (CR-005: caminho absoluto livre, somente POSIX),
com arvore temporaria e symlinks reais."""
from tests.support import _testenv  # noqa: F401

import os
import shutil
import tempfile
import unittest

from sss.platform import path_guard
from sss.platform.path_guard import Code, PathGuardError



FILE_MODE = 0o444
DIR_MODE = 0o555


@unittest.skipIf(os.geteuid() == 0, "root sempre passa em os.access(W_OK)")
class TestResolver(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sss_pg_")
        self.base = os.path.join(self.root, "scripts")
        self.down = os.path.join(self.root, "fora.py")
        os.makedirs(os.path.join(self.base, "sub", "fundo"))
        for p in (os.path.join(self.base, "sub", "ok.py"),
                  os.path.join(self.base, "sub", "fundo", "ok.sh"),
                  self.down):
            with open(p, "w") as f:
                f.write("print(1)\n")
        os.symlink(self.down, os.path.join(self.base, "link_fora.py"))
        os.symlink(os.path.join(self.base, "sub", "ok.py"), os.path.join(self.base, "link_ok.py"))
        os.symlink("/etc/hostname", os.path.join(self.base, "link_etc.py"))
        os.symlink("/usr", os.path.join(self.base, "link_usr"))
        os.symlink(os.path.join(self.base, "sub"), os.path.join(self.base, "link_sub"))
        os.symlink("ciclo_b", os.path.join(self.base, "ciclo_a"))
        os.symlink("ciclo_a", os.path.join(self.base, "ciclo_b"))
        self._lock(self.base)

    def tearDown(self):
        os.chmod(self.root, 0o755)
        for root, dirs, files in os.walk(self.root):
            os.chmod(root, 0o755)
        shutil.rmtree(self.root)

    def _lock(self, top):
        for root, dirs, files in os.walk(top):
            os.chmod(root, DIR_MODE)
            for f in files:
                p = os.path.join(root, f)
                if not os.path.islink(p):
                    os.chmod(p, FILE_MODE)

    def _p(self, rel):
        return os.path.join(self.base, rel)

    def _resolver(self, rel, sss_dirs=()):
        return path_guard.resolve(self._p(rel), sss_dirs)

    def _code(self, rel, **kw):
        with self.assertRaises(PathGuardError) as ctx:
            self._resolver(rel, **kw)
        return ctx.exception.code

    def test_caminho_valido(self):
        self.assertEqual(self._resolver("sub/ok.py"), os.path.realpath(self._p("sub/ok.py")))
        self.assertEqual(self._resolver("sub/fundo/ok.sh"), os.path.realpath(self._p("sub/fundo/ok.sh")))

    def test_link_simbolico_aceito_pelo_arquivo_real(self):
        # CR-011: o link e aceito; vale o arquivo real, que e o devolvido (e o executado).
        real = os.path.realpath(self._p("sub/ok.py"))
        self.assertEqual(self._resolver("link_ok.py"), real)
        self.assertEqual(self._resolver("link_sub/ok.py"), real, "link numa pasta do caminho")

    def test_link_para_destino_inseguro_e_recusado(self):
        # CR-011 (S2): vale o arquivo real; gravavel por grupo ou outros e recusado, mesmo via link.
        self.assertTrue(self._resolver("link_fora.py"), "destino fora da arvore, mas nao gravavel: aceito")
        os.chmod(self.down, 0o666)
        self.assertEqual(self._code("link_fora.py"), Code.GROUP_OTHER_WRITABLE)

    def test_ciclo_de_links(self):
        self.assertEqual(self._code("ciclo_a"), Code.NOT_FOUND)

    def test_pastas_do_sistema_digitadas_e_via_symlink(self):
        for path in ("/etc/passwd", "/usr/bin/python3", "/bin/sh", "/root/x.py", "/proc/self/status"):
            with self.subTest(caminho=path):
                with self.assertRaises(PathGuardError) as ctx:
                    path_guard.resolve(path)
                self.assertEqual(ctx.exception.code, Code.SYSTEM_DIR)
        self.assertEqual(self._code("link_etc.py"), Code.SYSTEM_DIR)
        self.assertEqual(self._code("link_usr/bin/env"), Code.SYSTEM_DIR)

    def test_prefixo_irmao_nao_e_pasta_do_sistema(self):
        # /usrx e /etcetera nao estao dentro de /usr e /etc (componente, nao prefixo de texto).
        for path in ("/usrx/a.py", "/etcetera/a.py", "/binarios/a.sh"):
            with self.subTest(caminho=path):
                with self.assertRaises(PathGuardError) as ctx:
                    path_guard.resolve(path)
                self.assertEqual(ctx.exception.code, Code.NOT_FOUND)

    def test_dentro_de_log_dir_ou_work_dir(self):
        self.assertEqual(self._code("sub/ok.py", sss_dirs=(self._p("sub"),)), Code.SSS_DIR)
        self.assertEqual(self._code("sub/fundo/ok.sh", sss_dirs=("/var/x", self._p("sub/fundo"))),
                         Code.SSS_DIR)
        self.assertTrue(self._resolver("sub/ok.py", sss_dirs=(self._p("sub/fundo"),)))

    def test_inexistente_e_diretorio(self):
        self.assertEqual(self._code("inexistente.py"), Code.NOT_FOUND)
        self.assertEqual(self._code("sub"), Code.NOT_A_FILE)

    def test_gravavel_por_grupo_ou_outros_so_no_arquivo(self):
        # CR-011 (S2): o ambiente controla o conteudo; o SSS confere so o proprio arquivo, nao as pastas.
        file = self._p("sub/fundo/ok.sh")
        for bit in (0o020, 0o002):
            os.chmod(file, FILE_MODE | bit)
            try:
                self.assertEqual(self._code("sub/fundo/ok.sh"), Code.GROUP_OTHER_WRITABLE, oct(bit))
            finally:
                os.chmod(file, FILE_MODE)
        os.chmod(self._p("sub/fundo"), 0o777)
        try:
            self.assertTrue(self._resolver("sub/fundo/ok.sh"), "pasta gravavel nao e conferida")
        finally:
            os.chmod(self._p("sub/fundo"), DIR_MODE)

    def test_dono_e_indiferente(self):
        # Sem script_owner_uids (CR-011): o arquivo do proprio usuario, sem escrita de grupo/outros, e aceito.
        self.assertTrue(self._resolver("sub/ok.py"))


@unittest.skipIf(os.geteuid() == 0, "root sempre passa nas checagens de acesso")
class TestAccessAndExecutable(unittest.TestCase):
    """NO_ACCESS e o executavel do interpretador (CR-011, S3)."""

    setUp = TestResolver.setUp
    tearDown = TestResolver.tearDown
    _lock = TestResolver._lock
    _p = TestResolver._p
    _code = TestResolver._code
    _resolver = TestResolver._resolver

    def test_sem_acesso_e_diferente_de_nao_encontrado(self):
        background = self._p("sub/fundo")
        os.chmod(background, 0o000)
        try:
            self.assertEqual(self._code("sub/fundo/ok.sh"), Code.NO_ACCESS)
        finally:
            os.chmod(background, DIR_MODE)

    def test_executavel_do_interpretador(self):
        sh = os.path.realpath("/bin/sh")
        self.assertEqual(path_guard.validate_executable("/bin/sh"), sh)
        with self.assertRaises(PathGuardError) as ctx:
            path_guard.validate_executable("/nao/existe/python3")
        self.assertEqual(ctx.exception.code, Code.NOT_FOUND)
        for path, kw in (("bin/sh", {}), ("/bin/sh", {"sss_dirs": (os.path.dirname(sh),)}),
                            (self._p("sub/ok.py"), {}), (self._p("sub"), {})):
            with self.subTest(caminho=path, kw=kw):
                with self.assertRaises(PathGuardError) as ctx:
                    path_guard.validate_executable(path, **kw)
                self.assertEqual(ctx.exception.code, Code.INTERPRETER_UNSAFE)


@unittest.skipIf(os.geteuid() == 0, "root sempre passa em os.access(W_OK)")
class TestBaseDir(unittest.TestCase):
    """CR-023: caminho relativo junto de [agent] script_base_dir; o real pode ficar fora da base (D3)."""

    setUp = TestResolver.setUp
    tearDown = TestResolver.tearDown
    _lock = TestResolver._lock
    _p = TestResolver._p

    def test_relativo_junto_da_base(self):
        real = os.path.realpath(self._p("sub/ok.py"))
        self.assertEqual(path_guard.resolve("sub/ok.py", base_dir=self.base), real)
        self.assertEqual(path_guard.resolve("link_ok.py", base_dir=self.base), real)

    def test_link_para_fora_da_base_e_aceito(self):
        self.assertEqual(path_guard.resolve("link_fora.py", base_dir=self.base), os.path.realpath(self.down))

    def test_pastas_proibidas_valem_para_o_relativo(self):
        cases = (("link_etc.py", Code.SYSTEM_DIR), ("nao_existe.py", Code.NOT_FOUND),
                 ("sub", Code.NOT_A_FILE), ("ciclo_a", Code.NOT_FOUND))
        for rel, code in cases:
            with self.subTest(caminho=rel):
                with self.assertRaises(PathGuardError) as ctx:
                    path_guard.resolve(rel, base_dir=self.base)
                self.assertEqual(ctx.exception.code, code)
        with self.assertRaises(PathGuardError) as ctx:
            path_guard.resolve("sub/ok.py", sss_dirs=(self.base,), base_dir=self.base)
        self.assertEqual(ctx.exception.code, Code.SSS_DIR)

    def test_relativo_sem_base(self):
        for base in (None, ""):
            with self.assertRaises(PathGuardError) as ctx:
                path_guard.resolve("sub/ok.py", base_dir=base)
            self.assertEqual(ctx.exception.code, Code.NO_BASE_DIR)

    def test_absoluto_ignora_a_base(self):
        real = os.path.realpath(self._p("sub/ok.py"))
        self.assertEqual(path_guard.resolve(self._p("sub/ok.py"), base_dir="/nao/existe"), real)

    def test_juntar_com_a_base(self):
        self.assertEqual(path_guard.join_base("a/b.py", "/opt/s"), "/opt/s/a/b.py")
        self.assertEqual(path_guard.join_base("/x/b.py", "/opt/s"), "/x/b.py")
        self.assertEqual(path_guard.join_base("/x/b.py", None), "/x/b.py")
        self.assertTrue(path_guard.is_relative("a.py"))
        self.assertFalse(path_guard.is_relative("/a.py"))
        self.assertFalse(path_guard.is_relative(""))


class TestAppDir(unittest.TestCase):
    """CR-023 (D8): script dentro da pasta da aplicacao e recusado; no DEV, dev/ e a excecao."""

    def test_pasta_da_aplicacao(self):
        inside = os.path.join(path_guard.APP_DIR, "src", "x.py")
        for dev in (False, True):
            with self.assertRaises(PathGuardError) as ctx:
                path_guard.check_forbidden_dirs(inside, dev=dev)
            self.assertEqual(ctx.exception.code, Code.APP_DIR)
        in_dev = os.path.join(path_guard.APP_DIR, "dev", "scripts", "x.py")
        path_guard.check_forbidden_dirs(in_dev, dev=True)
        with self.assertRaises(PathGuardError) as ctx:
            path_guard.check_forbidden_dirs(in_dev)
        self.assertEqual(ctx.exception.code, Code.APP_DIR)

    def test_link_para_dentro_da_aplicacao(self):
        root = tempfile.mkdtemp(prefix="sss_pg_app_")
        self.addCleanup(shutil.rmtree, root)
        link = os.path.join(root, "app.py")
        os.symlink(os.path.join(path_guard.APP_DIR, "README.md"), link)
        with self.assertRaises(PathGuardError) as ctx:
            path_guard.check_forbidden_dirs(link, dev=True)
        self.assertEqual(ctx.exception.code, Code.APP_DIR)

    def test_relativo_nao_e_conferido_no_cadastro(self):
        path_guard.check_forbidden_dirs("relatorios/x.py")


class TestInterpreterCr025(unittest.TestCase):
    """CR-025: interpretador digitado no disparo (caminho ou nome no PATH do agente) e o #! do script."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sss_pg_int_")
        self.addCleanup(shutil.rmtree, self.root)
        self.bin = os.path.join(self.root, "bin")
        os.mkdir(self.bin)
        self.exe = os.path.join(self.bin, "python3.99")
        with open(self.exe, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(self.exe, 0o755)
        self.not_exec = os.path.join(self.bin, "sem_x")
        with open(self.not_exec, "w") as f:
            f.write("x\n")
        os.chmod(self.not_exec, 0o644)

    def _script(self, first_line):
        path = os.path.join(self.root, "s.py")
        with open(path, "wb") as f:
            f.write(first_line + b"\nprint(1)\n")
        return path

    def test_formato_do_digitado(self):
        for ok in ("/opt/py311/bin/python3", "python3.13", "bash", "python3+x", "/opt/a b/python"):
            path_guard.validate_override(ok)
        for bad in ("", None, "py thon", "bin/python3", "python3;id", "a\x00", "x" * 501, "python3 -c"):
            with self.subTest(valor=bad):
                with self.assertRaises(PathGuardError) as ctx:
                    path_guard.validate_override(bad)
                self.assertEqual(ctx.exception.code, Code.INTERPRETER_INVALID)

    def test_busca_por_caminho_e_por_nome(self):
        self.assertEqual(path_guard.find_executable(self.exe, None), os.path.realpath(self.exe))
        self.assertEqual(path_guard.find_executable("python3.99", self.bin), os.path.realpath(self.exe))
        for text, search in (("python3.99", "/nao/existe"), (self.not_exec, None), ("sem_x", self.bin),
                             (os.path.join(self.bin, "nada"), None)):
            with self.subTest(texto=text):
                with self.assertRaises(PathGuardError) as ctx:
                    path_guard.find_executable(text, search)
                self.assertEqual(ctx.exception.code, Code.INTERPRETER_NOT_FOUND)

    def test_shebang(self):
        self.assertEqual(path_guard.read_shebang(self._script(b"#!/opt/py311/bin/python3")),
                         ("/opt/py311/bin/python3", None))
        self.assertEqual(path_guard.read_shebang(self._script(b"#! /bin/bash -e")), ("/bin/bash", "-e"))
        self.assertEqual(path_guard.read_shebang(self._script(b"#!/usr/bin/env python3")),
                         ("/usr/bin/env", "python3"))
        for first in (b"print(1)", b"#!", b"#!python3", b"# !/bin/sh", b"#!\xff\xfe"):
            with self.subTest(linha=first):
                with self.assertRaises(PathGuardError) as ctx:
                    path_guard.read_shebang(self._script(first))
                self.assertEqual(ctx.exception.code, Code.NO_SHEBANG)

    def test_opcoes_do_cadastro(self):
        self.assertEqual(path_guard.ALLOWLIST,
                         ("PYTHON3", "PYTHON", "BASH", "SH", "PYTHON_SCRIPT", "SHELL_SCRIPT"))
        self.assertEqual(path_guard.FIXED_ARGS["PYTHON3"], ("-I",))
        for key in ("PYTHON", "PYTHON_SCRIPT"):
            self.assertEqual(path_guard.FIXED_ARGS[key], ("-E", "-s"))


class TestTextValidations(unittest.TestCase):

    def test_validar_cadastro(self):
        path_guard.validate_registration("/opt/automacoes/scripts/faturamento/carga_faturas.py")
        path_guard.validate_registration("/opt/a b/script com espaço.py")
        # CR-023: relativo a [agent] script_base_dir
        for value in ("faturamento/carga.py", "a.py", "x y/script com espaço.sh"):
            path_guard.validate_registration(value)
        cases = (("", Code.PATH_NOT_NORMALIZED),
                 (None, Code.PATH_NOT_NORMALIZED),
                 ("./a.py", Code.PATH_NOT_NORMALIZED),
                 (".", Code.PATH_NOT_NORMALIZED),
                 ("a//b.py", Code.PATH_NOT_NORMALIZED),
                 ("a/b/", Code.PATH_NOT_NORMALIZED),
                 ("a/../b.py", Code.HAS_DOTS),
                 ("../b.py", Code.HAS_DOTS),
                 ("a\\b.py", Code.INVALID_SEPARATOR),
                 ("a\x00.py", Code.INVALID_CHARACTER),
                 ("/opt/../etc/passwd", Code.HAS_DOTS),
                 ("/opt/a..b.py", Code.HAS_DOTS),
                 ("/opt\\a.py", Code.INVALID_SEPARATOR),
                 ("/opt/a\x00.py", Code.INVALID_CHARACTER),
                 ("/opt/a\n.py", Code.INVALID_CHARACTER),
                 ("/opt//a.py", Code.PATH_NOT_NORMALIZED),
                 ("//opt/a.py", Code.PATH_NOT_NORMALIZED),
                 ("/opt/./a.py", Code.PATH_NOT_NORMALIZED),
                 ("/opt/scripts/", Code.PATH_NOT_NORMALIZED),
                 ("/", Code.PATH_NOT_NORMALIZED))
        for value, code in cases:
            with self.subTest(valor=value):
                with self.assertRaises(PathGuardError) as ctx:
                    path_guard.validate_registration(value)
                self.assertEqual(ctx.exception.code, code)

    def test_checar_pastas_proibidas_sem_o_arquivo(self):
        # Vale mesmo se o arquivo nao existe neste servidor (README §8.5, D4).
        for path in ("/etc/nao_existe.py", "/lib64/x.sh", "/sys/x", "/dev/null", "/boot/a.py"):
            with self.subTest(caminho=path):
                with self.assertRaises(PathGuardError) as ctx:
                    path_guard.check_forbidden_dirs(path)
                self.assertEqual(ctx.exception.code, Code.SYSTEM_DIR)
        path_guard.check_forbidden_dirs("/opt/automacoes/nao_existe.py")
        with self.assertRaises(PathGuardError) as ctx:
            path_guard.check_forbidden_dirs("/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs/x.py", ("/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs", "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/work"))
        self.assertEqual(ctx.exception.code, Code.SSS_DIR)

    def test_interpretador_na_allowlist(self):
        for cmd in ("PYTHON3", "BASH", "SH"):
            path_guard.validate_interpreter(cmd)
        # CR-005: somente POSIX; POWERSHELL e cmd ficam fora da allowlist.
        for cmd in ("POWERSHELL", "CMD", "python3"):
            with self.assertRaises(PathGuardError) as ctx:
                path_guard.validate_interpreter(cmd)
            self.assertEqual(ctx.exception.code, Code.INTERPRETER_NOT_ALLOWED)
        self.assertNotIn("POWERSHELL", path_guard.FIXED_ARGS)
        self.assertEqual(path_guard.FIXED_ARGS["PYTHON3"], ("-I",))

    def test_interpretador_fora_da_allowlist(self):
        # Caminhos absolutos (modelo anterior ao CR-001) e cmd/.bat (D2) tambem sao rejeitados.
        for cmd in ("/usr/bin/python3", "/bin/bash", "/bin/zsh", "", None, "PYTHON3 ", "python3", "CMD", "cmd.exe",
                    "BAT", "SH -c"):
            with self.subTest(cmd=cmd):
                with self.assertRaises(PathGuardError) as ctx:
                    path_guard.validate_interpreter(cmd)
                self.assertEqual(ctx.exception.code, Code.INTERPRETER_NOT_ALLOWED)

    def test_sem_startswith(self):
        with open(path_guard.__file__, "r", encoding="utf-8") as f:
            self.assertNotIn("startswith", f.read())


if __name__ == "__main__":
    unittest.main()
