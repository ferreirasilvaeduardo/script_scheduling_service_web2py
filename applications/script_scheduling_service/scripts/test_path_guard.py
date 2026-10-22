# -*- coding: utf-8 -*-
"""Testes de path_guard.py: README §8.5 e AGENTS §7.4 (CR-005: caminho absoluto livre, somente POSIX),
com arvore temporaria e symlinks reais."""
import _testenv  # noqa: F401

import os
import shutil
import tempfile
import unittest

import path_guard
from path_guard import Code, PathGuardError



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
                self.assertEqual(ctx.exception.code, Code.INTERPRETADOR_INSEGURO)


class TestTextValidations(unittest.TestCase):

    def test_validar_cadastro(self):
        path_guard.validate_registration("/opt/automacoes/scripts/faturamento/carga_faturas.py")
        path_guard.validate_registration("/opt/a b/script com espaço.py")
        cases = (("faturamento/carga.py", Code.RELATIVE_PATH),
                 ("", Code.RELATIVE_PATH),
                 (None, Code.RELATIVE_PATH),
                 ("./a.py", Code.RELATIVE_PATH),
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
            path_guard.check_forbidden_dirs("/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs/x.py", ("/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs", "/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/work"))
        self.assertEqual(ctx.exception.code, Code.SSS_DIR)

    def test_interpretador_na_allowlist(self):
        for cmd in ("PYTHON3", "BASH", "SH"):
            path_guard.validate_interpreter(cmd)
        # CR-005: somente POSIX; POWERSHELL e cmd ficam fora da allowlist.
        for cmd in ("POWERSHELL", "CMD", "python3"):
            with self.assertRaises(PathGuardError) as ctx:
                path_guard.validate_interpreter(cmd)
            self.assertEqual(ctx.exception.code, Code.INTERPRETADOR_NAO_PERMITIDO)
        self.assertNotIn("POWERSHELL", path_guard.FIXED_ARGS)
        self.assertEqual(path_guard.FIXED_ARGS["PYTHON3"], ("-I",))

    def test_interpretador_fora_da_allowlist(self):
        # Caminhos absolutos (modelo anterior ao CR-001) e cmd/.bat (D2) tambem sao rejeitados.
        for cmd in ("/usr/bin/python3", "/bin/bash", "/bin/zsh", "", None, "PYTHON3 ", "python3", "CMD", "cmd.exe",
                    "BAT", "SH -c"):
            with self.subTest(cmd=cmd):
                with self.assertRaises(PathGuardError) as ctx:
                    path_guard.validate_interpreter(cmd)
                self.assertEqual(ctx.exception.code, Code.INTERPRETADOR_NAO_PERMITIDO)

    def test_sem_startswith(self):
        with open(path_guard.__file__, "r", encoding="utf-8") as f:
            self.assertNotIn("startswith", f.read())


if __name__ == "__main__":
    unittest.main()
