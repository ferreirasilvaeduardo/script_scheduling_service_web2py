# -*- coding: utf-8 -*-
"""Testes de path_guard.py: README §8.5 e AGENTS §7.4 (CR-005: caminho absoluto livre, somente POSIX),
com arvore temporaria e symlinks reais."""
import _testenv  # noqa: F401

import os
import shutil
import tempfile
import unittest

import path_guard
from path_guard import Codigo, PathGuardErro



MODO_ARQ = 0o444
MODO_DIR = 0o555


@unittest.skipIf(os.geteuid() == 0, "root sempre passa em os.access(W_OK)")
class TestResolver(unittest.TestCase):

    def setUp(self):
        self.raiz = tempfile.mkdtemp(prefix="sss_pg_")
        self.base = os.path.join(self.raiz, "scripts")
        self.fora = os.path.join(self.raiz, "fora.py")
        os.makedirs(os.path.join(self.base, "sub", "fundo"))
        for p in (os.path.join(self.base, "sub", "ok.py"),
                  os.path.join(self.base, "sub", "fundo", "ok.sh"),
                  self.fora):
            with open(p, "w") as f:
                f.write("print(1)\n")
        os.symlink(self.fora, os.path.join(self.base, "link_fora.py"))
        os.symlink(os.path.join(self.base, "sub", "ok.py"), os.path.join(self.base, "link_ok.py"))
        os.symlink("/etc/hostname", os.path.join(self.base, "link_etc.py"))
        os.symlink("/usr", os.path.join(self.base, "link_usr"))
        os.symlink(os.path.join(self.base, "sub"), os.path.join(self.base, "link_sub"))
        os.symlink("ciclo_b", os.path.join(self.base, "ciclo_a"))
        os.symlink("ciclo_a", os.path.join(self.base, "ciclo_b"))
        self._travar(self.base)

    def tearDown(self):
        os.chmod(self.raiz, 0o755)
        for raiz, dirs, files in os.walk(self.raiz):
            os.chmod(raiz, 0o755)
        shutil.rmtree(self.raiz)

    def _travar(self, topo):
        for raiz, dirs, files in os.walk(topo):
            os.chmod(raiz, MODO_DIR)
            for f in files:
                p = os.path.join(raiz, f)
                if not os.path.islink(p):
                    os.chmod(p, MODO_ARQ)

    def _p(self, rel):
        return os.path.join(self.base, rel)

    def _resolver(self, rel, dirs_sss=()):
        return path_guard.resolver(self._p(rel), dirs_sss)

    def _codigo(self, rel, **kw):
        with self.assertRaises(PathGuardErro) as ctx:
            self._resolver(rel, **kw)
        return ctx.exception.codigo

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
        os.chmod(self.fora, 0o666)
        self.assertEqual(self._codigo("link_fora.py"), Codigo.GRAVAVEL_GRUPO_OUTROS)

    def test_ciclo_de_links(self):
        self.assertEqual(self._codigo("ciclo_a"), Codigo.NAO_ENCONTRADO)

    def test_pastas_do_sistema_digitadas_e_via_symlink(self):
        for caminho in ("/etc/passwd", "/usr/bin/python3", "/bin/sh", "/root/x.py", "/proc/self/status"):
            with self.subTest(caminho=caminho):
                with self.assertRaises(PathGuardErro) as ctx:
                    path_guard.resolver(caminho)
                self.assertEqual(ctx.exception.codigo, Codigo.PASTA_DO_SISTEMA)
        self.assertEqual(self._codigo("link_etc.py"), Codigo.PASTA_DO_SISTEMA)
        self.assertEqual(self._codigo("link_usr/bin/env"), Codigo.PASTA_DO_SISTEMA)

    def test_prefixo_irmao_nao_e_pasta_do_sistema(self):
        # /usrx e /etcetera nao estao dentro de /usr e /etc (componente, nao prefixo de texto).
        for caminho in ("/usrx/a.py", "/etcetera/a.py", "/binarios/a.sh"):
            with self.subTest(caminho=caminho):
                with self.assertRaises(PathGuardErro) as ctx:
                    path_guard.resolver(caminho)
                self.assertEqual(ctx.exception.codigo, Codigo.NAO_ENCONTRADO)

    def test_dentro_de_log_dir_ou_work_dir(self):
        self.assertEqual(self._codigo("sub/ok.py", dirs_sss=(self._p("sub"),)), Codigo.PASTA_DO_SSS)
        self.assertEqual(self._codigo("sub/fundo/ok.sh", dirs_sss=("/var/x", self._p("sub/fundo"))),
                         Codigo.PASTA_DO_SSS)
        self.assertTrue(self._resolver("sub/ok.py", dirs_sss=(self._p("sub/fundo"),)))

    def test_inexistente_e_diretorio(self):
        self.assertEqual(self._codigo("inexistente.py"), Codigo.NAO_ENCONTRADO)
        self.assertEqual(self._codigo("sub"), Codigo.NAO_E_ARQUIVO)

    def test_gravavel_por_grupo_ou_outros_so_no_arquivo(self):
        # CR-011 (S2): o ambiente controla o conteudo; o SSS confere so o proprio arquivo, nao as pastas.
        arq = self._p("sub/fundo/ok.sh")
        for bit in (0o020, 0o002):
            os.chmod(arq, MODO_ARQ | bit)
            try:
                self.assertEqual(self._codigo("sub/fundo/ok.sh"), Codigo.GRAVAVEL_GRUPO_OUTROS, oct(bit))
            finally:
                os.chmod(arq, MODO_ARQ)
        os.chmod(self._p("sub/fundo"), 0o777)
        try:
            self.assertTrue(self._resolver("sub/fundo/ok.sh"), "pasta gravavel nao e conferida")
        finally:
            os.chmod(self._p("sub/fundo"), MODO_DIR)

    def test_dono_e_indiferente(self):
        # Sem script_owner_uids (CR-011): o arquivo do proprio usuario, sem escrita de grupo/outros, e aceito.
        self.assertTrue(self._resolver("sub/ok.py"))


@unittest.skipIf(os.geteuid() == 0, "root sempre passa nas checagens de acesso")
class TestAcessoEExecutavel(unittest.TestCase):
    """SEM_ACESSO e o executavel do interpretador (CR-011, S3)."""

    setUp = TestResolver.setUp
    tearDown = TestResolver.tearDown
    _travar = TestResolver._travar
    _p = TestResolver._p
    _codigo = TestResolver._codigo
    _resolver = TestResolver._resolver

    def test_sem_acesso_e_diferente_de_nao_encontrado(self):
        fundo = self._p("sub/fundo")
        os.chmod(fundo, 0o000)
        try:
            self.assertEqual(self._codigo("sub/fundo/ok.sh"), Codigo.SEM_ACESSO)
        finally:
            os.chmod(fundo, MODO_DIR)

    def test_executavel_do_interpretador(self):
        sh = os.path.realpath("/bin/sh")
        self.assertEqual(path_guard.validar_executavel("/bin/sh"), sh)
        with self.assertRaises(PathGuardErro) as ctx:
            path_guard.validar_executavel("/nao/existe/python3")
        self.assertEqual(ctx.exception.codigo, Codigo.NAO_ENCONTRADO)
        for caminho, kw in (("bin/sh", {}), ("/bin/sh", {"dirs_sss": (os.path.dirname(sh),)}),
                            (self._p("sub/ok.py"), {}), (self._p("sub"), {})):
            with self.subTest(caminho=caminho, kw=kw):
                with self.assertRaises(PathGuardErro) as ctx:
                    path_guard.validar_executavel(caminho, **kw)
                self.assertEqual(ctx.exception.codigo, Codigo.INTERPRETADOR_INSEGURO)


class TestValidacoesTextuais(unittest.TestCase):

    def test_validar_cadastro(self):
        path_guard.validar_cadastro("/opt/automacoes/scripts/faturamento/carga_faturas.py")
        path_guard.validar_cadastro("/opt/a b/script com espaço.py")
        casos = (("faturamento/carga.py", Codigo.CAMINHO_RELATIVO),
                 ("", Codigo.CAMINHO_RELATIVO),
                 (None, Codigo.CAMINHO_RELATIVO),
                 ("./a.py", Codigo.CAMINHO_RELATIVO),
                 ("/opt/../etc/passwd", Codigo.CONTEM_PONTOS),
                 ("/opt/a..b.py", Codigo.CONTEM_PONTOS),
                 ("/opt\\a.py", Codigo.SEPARADOR_INVALIDO),
                 ("/opt/a\x00.py", Codigo.CARACTERE_INVALIDO),
                 ("/opt/a\n.py", Codigo.CARACTERE_INVALIDO),
                 ("/opt//a.py", Codigo.CAMINHO_NAO_NORMALIZADO),
                 ("//opt/a.py", Codigo.CAMINHO_NAO_NORMALIZADO),
                 ("/opt/./a.py", Codigo.CAMINHO_NAO_NORMALIZADO),
                 ("/opt/scripts/", Codigo.CAMINHO_NAO_NORMALIZADO),
                 ("/", Codigo.CAMINHO_NAO_NORMALIZADO))
        for valor, codigo in casos:
            with self.subTest(valor=valor):
                with self.assertRaises(PathGuardErro) as ctx:
                    path_guard.validar_cadastro(valor)
                self.assertEqual(ctx.exception.codigo, codigo)

    def test_checar_pastas_proibidas_sem_o_arquivo(self):
        # Vale mesmo se o arquivo nao existe neste servidor (README §8.5, D4).
        for caminho in ("/etc/nao_existe.py", "/lib64/x.sh", "/sys/x", "/dev/null", "/boot/a.py"):
            with self.subTest(caminho=caminho):
                with self.assertRaises(PathGuardErro) as ctx:
                    path_guard.checar_pastas_proibidas(caminho)
                self.assertEqual(ctx.exception.codigo, Codigo.PASTA_DO_SISTEMA)
        path_guard.checar_pastas_proibidas("/opt/automacoes/nao_existe.py")
        with self.assertRaises(PathGuardErro) as ctx:
            path_guard.checar_pastas_proibidas("/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs/x.py", ("/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs", "/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/work"))
        self.assertEqual(ctx.exception.codigo, Codigo.PASTA_DO_SSS)

    def test_interpretador_na_allowlist(self):
        for cmd in ("PYTHON3", "BASH", "SH"):
            path_guard.validar_interpretador(cmd)
        # CR-005: somente POSIX; POWERSHELL e cmd ficam fora da allowlist.
        for cmd in ("POWERSHELL", "CMD", "python3"):
            with self.assertRaises(PathGuardErro) as ctx:
                path_guard.validar_interpretador(cmd)
            self.assertEqual(ctx.exception.codigo, Codigo.INTERPRETADOR_NAO_PERMITIDO)
        self.assertNotIn("POWERSHELL", path_guard.ARGS_FIXOS)
        self.assertEqual(path_guard.ARGS_FIXOS["PYTHON3"], ("-I",))

    def test_interpretador_fora_da_allowlist(self):
        # Caminhos absolutos (modelo anterior ao CR-001) e cmd/.bat (D2) tambem sao rejeitados.
        for cmd in ("/usr/bin/python3", "/bin/bash", "/bin/zsh", "", None, "PYTHON3 ", "python3", "CMD", "cmd.exe",
                    "BAT", "SH -c"):
            with self.subTest(cmd=cmd):
                with self.assertRaises(PathGuardErro) as ctx:
                    path_guard.validar_interpretador(cmd)
                self.assertEqual(ctx.exception.codigo, Codigo.INTERPRETADOR_NAO_PERMITIDO)

    def test_sem_startswith(self):
        with open(path_guard.__file__, "r", encoding="utf-8") as f:
            self.assertNotIn("startswith", f.read())


if __name__ == "__main__":
    unittest.main()
