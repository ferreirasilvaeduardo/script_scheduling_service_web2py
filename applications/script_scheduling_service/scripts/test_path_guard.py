# -*- coding: utf-8 -*-
"""Testes de path_guard.py (F3.1): README §8.5 e AGENTS §7.4, com arvore temporaria e symlinks reais."""
import _testenv  # noqa: F401

import os
import shutil
import tempfile
import unittest
from unittest import mock

import path_guard
from path_guard import Codigo, PathGuardErro

MODO_ARQ = 0o444
MODO_DIR = 0o555


@unittest.skipIf(os.geteuid() == 0, "root sempre passa em os.access(W_OK)")
class TestResolver(unittest.TestCase):

    def setUp(self):
        self.raiz = tempfile.mkdtemp(prefix="sss_pg_")
        self.base = os.path.join(self.raiz, "scripts")
        self.evil = os.path.join(self.raiz, "scripts_evil")
        self.fora = os.path.join(self.raiz, "fora.py")
        os.makedirs(os.path.join(self.base, "sub", "fundo"))
        os.makedirs(self.evil)
        for p in (os.path.join(self.base, "sub", "ok.py"),
                  os.path.join(self.base, "sub", "fundo", "ok.sh"),
                  os.path.join(self.evil, "x.py"),
                  self.fora):
            with open(p, "w") as f:
                f.write("print(1)\n")
        os.symlink(self.fora, os.path.join(self.base, "link_fora.py"))
        os.symlink(os.path.join(self.evil, "x.py"), os.path.join(self.base, "link_evil.py"))
        os.symlink(self.base, os.path.join(self.base, "link_base"))
        os.symlink(os.path.join(self.base, "sub", "ok.py"), os.path.join(self.base, "link_ok.py"))
        self._travar(self.base)
        self.uids = (os.getuid(),)

    def tearDown(self):
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

    def _resolver(self, path_file, uids=None, uid_agente=None):
        return path_guard.resolver(self.base, path_file, self.uids if uids is None else uids, uid_agente)

    def _codigo(self, path_file, **kw):
        with self.assertRaises(PathGuardErro) as ctx:
            self._resolver(path_file, **kw)
        return ctx.exception.codigo

    def test_caminho_valido(self):
        esperado = os.path.realpath(os.path.join(self.base, "sub", "ok.py"))
        self.assertEqual(self._resolver("sub/ok.py"), esperado)
        self.assertEqual(self._resolver("sub/fundo/ok.sh"),
                         os.path.realpath(os.path.join(self.base, "sub", "fundo", "ok.sh")))

    def test_symlink_interno_resolve_para_alvo_real(self):
        self.assertEqual(self._resolver("link_ok.py"),
                         os.path.realpath(os.path.join(self.base, "sub", "ok.py")))

    def test_escape_com_pontos(self):
        self.assertEqual(self._codigo("../fora.py"), Codigo.CONTEM_PONTOS)
        self.assertEqual(self._codigo("sub/../../fora.py"), Codigo.CONTEM_PONTOS)

    def test_caminho_absoluto(self):
        self.assertEqual(self._codigo(self.fora), Codigo.CAMINHO_ABSOLUTO)
        self.assertEqual(self._codigo(""), Codigo.CAMINHO_ABSOLUTO)

    def test_symlink_para_fora_da_base(self):
        self.assertEqual(self._codigo("link_fora.py"), Codigo.FORA_DA_BASE)

    def test_prefixo_irmao(self):
        # /x/scripts_evil comeca com /x/scripts, mas nao esta dentro dele.
        self.assertEqual(self._codigo("link_evil.py"), Codigo.FORA_DA_BASE)

    def test_commonpath_value_error_e_fora_da_base(self):
        with mock.patch("path_guard.os.path.commonpath", side_effect=ValueError):
            self.assertEqual(self._codigo("sub/ok.py"), Codigo.FORA_DA_BASE)

    def test_igual_a_base(self):
        self.assertEqual(self._codigo("."), Codigo.IGUAL_A_BASE)
        self.assertEqual(self._codigo("link_base"), Codigo.IGUAL_A_BASE)

    def test_diretorio_em_vez_de_arquivo(self):
        self.assertEqual(self._codigo("sub"), Codigo.NAO_E_ARQUIVO)
        self.assertEqual(self._codigo("inexistente.py"), Codigo.NAO_E_ARQUIVO)

    def test_dono_invalido(self):
        self.assertEqual(self._codigo("sub/ok.py", uids=(os.getuid() + 1,)), Codigo.DONO_INVALIDO)

    def _codigo_com_modo(self, alvo, modo):
        original = os.stat(alvo).st_mode & 0o777
        os.chmod(alvo, modo)
        try:
            return self._codigo("sub/fundo/ok.sh")
        finally:
            os.chmod(alvo, original)

    def _alvos(self):
        return (os.path.join(self.base, "sub", "fundo", "ok.sh"),
                os.path.join(self.base, "sub", "fundo"),
                os.path.join(self.base, "sub"),
                self.base)

    def test_gravavel_por_grupo_ou_outros(self):
        for alvo in self._alvos():
            base_modo = MODO_DIR if os.path.isdir(alvo) else MODO_ARQ
            for bit in (0o020, 0o002):
                with self.subTest(alvo=alvo, bit=oct(bit)):
                    self.assertEqual(self._codigo_com_modo(alvo, base_modo | bit),
                                     Codigo.GRAVAVEL_GRUPO_OUTROS)

    def test_gravavel_pelo_agente(self):
        for alvo in self._alvos():
            base_modo = MODO_DIR if os.path.isdir(alvo) else MODO_ARQ
            with self.subTest(alvo=alvo):
                self.assertEqual(self._codigo_com_modo(alvo, base_modo | 0o200),
                                 Codigo.GRAVAVEL_PELO_AGENTE)

    def test_uid_agente_explicito(self):
        arq = os.path.join(self.base, "sub", "ok.py")
        os.chmod(arq, 0o644)
        try:
            # Outro UID nao e dono e grupo/outros nao escrevem: aceito.
            self.assertTrue(self._resolver("sub/ok.py", uid_agente=os.getuid() + 1))
            self.assertEqual(self._codigo("sub/ok.py", uid_agente=os.getuid()), Codigo.GRAVAVEL_PELO_AGENTE)
        finally:
            os.chmod(arq, MODO_ARQ)
        self.assertEqual(self._codigo("sub/ok.py", uid_agente=0), Codigo.GRAVAVEL_PELO_AGENTE)


class TestValidacoesTextuais(unittest.TestCase):

    def test_pasta_base_e_regra_do_no_web(self):
        # CR-003 D16/D4 (README §8.5).
        path_guard.validar_pasta("ROTINAS")
        for nome in ("rotinas", "1X", "", None, "A" * 31, "RO-TINAS"):
            with self.assertRaises(PathGuardErro) as ctx:
                path_guard.validar_pasta(nome)
            self.assertEqual(ctx.exception.codigo, Codigo.PASTA_INVALIDA, nome)
        pastas = {"ROTINAS": "/opt/x", "SO_AGENTE": None}
        with self.assertRaises(PathGuardErro) as ctx:
            path_guard.resolver_pasta(pastas, "SO_AGENTE", "a.py", (0,))
        self.assertEqual(ctx.exception.codigo, Codigo.PASTA_NAO_MAPEADA)
        with self.assertRaises(PathGuardErro) as ctx:
            path_guard.resolver_pasta(pastas, "OUTRA", "a.py", (0,))
        self.assertEqual(ctx.exception.codigo, Codigo.PASTA_NAO_MAPEADA)
        self.assertIsNone(path_guard.motivo_sem_etapa2(pastas, "ROTINAS", "PYTHON3", "POSIX"))
        self.assertEqual(path_guard.motivo_sem_etapa2(pastas, "ROTINAS", "POWERSHELL", "POSIX"),
                         path_guard.OUTRA_PLATAFORMA)
        self.assertEqual(path_guard.motivo_sem_etapa2(pastas, "ROTINAS", "BASH", "WINDOWS"),
                         path_guard.OUTRA_PLATAFORMA)
        self.assertEqual(path_guard.motivo_sem_etapa2(pastas, "SO_AGENTE", "PYTHON3", "POSIX"),
                         path_guard.PASTA_NAO_DISPONIVEL)

    def test_validar_cadastro(self):
        path_guard.validar_cadastro("faturamento/carga_faturas.py")
        casos = (("/etc/passwd", Codigo.CAMINHO_ABSOLUTO),
                 ("", Codigo.CAMINHO_ABSOLUTO),
                 (None, Codigo.CAMINHO_ABSOLUTO),
                 ("a/../b.py", Codigo.CONTEM_PONTOS),
                 ("a..b.py", Codigo.CONTEM_PONTOS))
        for valor, codigo in casos:
            with self.subTest(valor=valor):
                with self.assertRaises(PathGuardErro) as ctx:
                    path_guard.validar_cadastro(valor)
                self.assertEqual(ctx.exception.codigo, codigo)

    def test_interpretador_na_allowlist(self):
        for cmd in ("PYTHON3", "BASH", "SH", "POWERSHELL"):
            path_guard.validar_interpretador(cmd)
        self.assertEqual(path_guard.POR_PLATAFORMA["WINDOWS"], ("PYTHON3", "POWERSHELL"))
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
