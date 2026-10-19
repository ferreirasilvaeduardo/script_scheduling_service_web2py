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

# UID fictício do agente: os arquivos de teste são do usuário do teste (CR-007, R-15).
AGENTE_FALSO = 2 ** 31 - 3

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
        self._travar(self.base)
        self.uids = (os.getuid(),)

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

    def _resolver(self, rel, uids=None, uid_agente=AGENTE_FALSO, dirs_sss=(), parar_em=None):
        # A arvore temporaria fica sob /tmp (escrita para todos): a cadeia para na base travada.
        return path_guard.resolver(self._p(rel), self.uids if uids is None else uids, uid_agente,
                                   dirs_sss, self.base if parar_em is None else parar_em)

    def _codigo(self, rel, **kw):
        with self.assertRaises(PathGuardErro) as ctx:
            self._resolver(rel, **kw)
        return ctx.exception.codigo

    def test_caminho_valido(self):
        self.assertEqual(self._resolver("sub/ok.py"), os.path.realpath(self._p("sub/ok.py")))
        self.assertEqual(self._resolver("sub/fundo/ok.sh"), os.path.realpath(self._p("sub/fundo/ok.sh")))

    def test_link_simbolico_e_recusado(self):
        # CR-007, R-14: quem grava na pasta do link troca o destino; o caminho precisa ser o realpath.
        self.assertEqual(self._codigo("link_ok.py"), Codigo.CAMINHO_COM_LINK)

    def test_symlink_para_pasta_insegura_e_recusado(self):
        self.assertEqual(self._codigo("link_fora.py"), Codigo.CAMINHO_COM_LINK)

    def test_pastas_do_sistema_digitadas_e_via_symlink(self):
        for caminho in ("/etc/passwd", "/usr/bin/python3", "/bin/sh", "/root/x.py", "/proc/self/status"):
            with self.subTest(caminho=caminho):
                with self.assertRaises(PathGuardErro) as ctx:
                    path_guard.resolver(caminho, self.uids)
                self.assertEqual(ctx.exception.codigo, Codigo.PASTA_DO_SISTEMA)
        self.assertEqual(self._codigo("link_etc.py"), Codigo.PASTA_DO_SISTEMA)
        self.assertEqual(self._codigo("link_usr/bin/env"), Codigo.PASTA_DO_SISTEMA)

    def test_prefixo_irmao_nao_e_pasta_do_sistema(self):
        # /usrx e /etcetera nao estao dentro de /usr e /etc (componente, nao prefixo de texto).
        for caminho in ("/usrx/a.py", "/etcetera/a.py", "/binarios/a.sh"):
            with self.subTest(caminho=caminho):
                with self.assertRaises(PathGuardErro) as ctx:
                    path_guard.resolver(caminho, self.uids)
                self.assertEqual(ctx.exception.codigo, Codigo.NAO_ENCONTRADO)

    def test_dentro_de_log_dir_ou_work_dir(self):
        self.assertEqual(self._codigo("sub/ok.py", dirs_sss=(self._p("sub"),)), Codigo.PASTA_DO_SSS)
        self.assertEqual(self._codigo("sub/fundo/ok.sh", dirs_sss=("/var/x", self._p("sub/fundo"))),
                         Codigo.PASTA_DO_SSS)
        self.assertTrue(self._resolver("sub/ok.py", dirs_sss=(self._p("sub/fundo"),)))

    def test_inexistente_e_diretorio(self):
        self.assertEqual(self._codigo("inexistente.py"), Codigo.NAO_ENCONTRADO)
        self.assertEqual(self._codigo("sub"), Codigo.NAO_E_ARQUIVO)

    def test_dono_invalido(self):
        self.assertEqual(self._codigo("sub/ok.py", uids=(os.getuid() + 1,)), Codigo.DONO_INVALIDO)

    def _codigo_com_modo(self, alvo, modo, **kw):
        original = os.stat(alvo).st_mode & 0o777
        os.chmod(alvo, modo)
        try:
            return self._codigo("sub/fundo/ok.sh", **kw)
        finally:
            os.chmod(alvo, original)

    def _alvos(self):
        return (self._p("sub/fundo/ok.sh"), self._p("sub/fundo"), self._p("sub"), self.base)

    def test_gravavel_por_grupo_ou_outros_no_arquivo_e_na_cadeia(self):
        for alvo in self._alvos():
            base_modo = MODO_DIR if os.path.isdir(alvo) else MODO_ARQ
            for bit in (0o020, 0o002):
                with self.subTest(alvo=alvo, bit=oct(bit)):
                    self.assertEqual(self._codigo_com_modo(alvo, base_modo | bit), Codigo.GRAVAVEL_GRUPO_OUTROS)

    def test_gravavel_pelo_agente_no_arquivo_e_na_cadeia(self):
        for alvo in self._alvos():
            base_modo = MODO_DIR if os.path.isdir(alvo) else MODO_ARQ
            with self.subTest(alvo=alvo):
                # O agente e o proprio processo (dono dos arquivos de teste).
                self.assertEqual(self._codigo_com_modo(alvo, base_modo | 0o200, uid_agente=None),
                                 Codigo.GRAVAVEL_PELO_AGENTE)

    def test_uid_agente_explicito(self):
        arq = self._p("sub/ok.py")
        os.chmod(arq, 0o644)
        try:
            # Outro UID nao e dono e grupo/outros nao escrevem: aceito.
            self.assertTrue(self._resolver("sub/ok.py", uid_agente=os.getuid() + 1))
            self.assertEqual(self._codigo("sub/ok.py", uid_agente=os.getuid()), Codigo.GRAVAVEL_PELO_AGENTE)
        finally:
            os.chmod(arq, MODO_ARQ)
        self.assertEqual(self._codigo("sub/ok.py", uid_agente=0), Codigo.GRAVAVEL_PELO_AGENTE)

    def test_cadeia_vai_ate_a_raiz(self):
        # Sem parar_em (producao), a cadeia sobe ate '/': a raiz temporaria do proprio agente e recusada.
        self.assertEqual(self._codigo("sub/ok.py", parar_em="/", uid_agente=None), Codigo.GRAVAVEL_PELO_AGENTE)
        tmp = os.path.dirname(self.raiz)
        st = os.stat(tmp)
        if not (st.st_mode & 0o002 and st.st_uid == 0):
            self.skipTest("pasta temporaria nao e do root com escrita para todos")
        # Com a raiz temporaria travada, a proxima pasta (o /tmp, 1777) e recusada mesmo com sticky bit.
        os.chmod(self.raiz, MODO_DIR)
        self.assertEqual(self._codigo("sub/ok.py", parar_em="/"), Codigo.GRAVAVEL_GRUPO_OUTROS)


@unittest.skipIf(os.geteuid() == 0, "root sempre passa em os.access(W_OK)")
class TestDonosProibidosEExecutavel(unittest.TestCase):
    """CR-007, R-14/R-15: dono igual ao agente ou a um usuario de execucao, SEM_ACESSO e executavel do interpretador."""

    setUp = TestResolver.setUp
    tearDown = TestResolver.tearDown
    _travar = TestResolver._travar
    _p = TestResolver._p
    _codigo = TestResolver._codigo

    def test_dono_agente_mesmo_sem_escrita(self):
        # Arquivo 0555 do proprio agente: o dono pode voltar o modo a qualquer momento.
        self.assertEqual(self._codigo("sub/ok.py", uid_agente=os.getuid()), Codigo.GRAVAVEL_PELO_AGENTE)

    def test_dono_usuario_de_execucao(self):
        self.assertEqual(self._codigo("sub/ok.py", uids_proibidos=(os.getuid(),)), Codigo.GRAVAVEL_PELO_EXECUTOR)

    def _resolver(self, rel, uids=None, uid_agente=AGENTE_FALSO, dirs_sss=(), parar_em=None, uids_proibidos=()):
        return path_guard.resolver(self._p(rel), self.uids if uids is None else uids, uid_agente,
                                   dirs_sss, self.base if parar_em is None else parar_em, uids_proibidos)

    def test_sem_acesso_e_diferente_de_nao_encontrado(self):
        fundo = self._p("sub/fundo")
        os.chmod(fundo, 0o000)
        try:
            self.assertEqual(self._codigo("sub/fundo/ok.sh"), Codigo.SEM_ACESSO)
        finally:
            os.chmod(fundo, MODO_DIR)

    def test_executavel_do_interpretador(self):
        sh = os.path.realpath("/bin/sh")
        self.assertEqual(path_guard.validar_executavel("/bin/sh", (0,), uid_agente=AGENTE_FALSO), sh)
        with self.assertRaises(PathGuardErro) as ctx:
            path_guard.validar_executavel("/nao/existe/python3", (0,), uid_agente=AGENTE_FALSO)
        self.assertEqual(ctx.exception.codigo, Codigo.NAO_ENCONTRADO)
        for caminho, kw in (("bin/sh", {}), ("/bin/sh", {"dirs_sss": (os.path.dirname(sh),)}),
                            ("/bin/sh", {"uids_proibidos": (0,)}),
                            (self._p("sub/ok.py"), {"parar_em": self.base})):
            with self.subTest(caminho=caminho, kw=kw):
                with self.assertRaises(PathGuardErro) as ctx:
                    path_guard.validar_executavel(caminho, (0, os.getuid()), uid_agente=AGENTE_FALSO, **kw)
                self.assertEqual(ctx.exception.codigo, Codigo.INTERPRETADOR_INSEGURO)

    def test_uids_de_usuarios(self):
        self.assertEqual(path_guard.uids_de_usuarios(["root", "usuario_que_nao_existe_sss"]), (0,))
        self.assertEqual(path_guard.uids_de_usuarios(None), ())


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
