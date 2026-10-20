# -*- coding: utf-8 -*-
"""Testes de modules/plataforma (README §8.0, AGENTS §3.2 e §7): processos reais em grupo proprio, trava,
estado local, validacoes de arquivos e caminhos e dubles do sudo/helper. Somente POSIX (CR-005)."""
import _testenv  # noqa: F401

import collections
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import path_guard
import plataforma
from plataforma import posix

AGENTE_FALSO = 2 ** 31 - 3
PID_INEXISTENTE = 2 ** 31 - 2

_Stat = collections.namedtuple("_Stat", "st_uid st_mode")
_Pw = collections.namedtuple("_Pw", "pw_name pw_uid")


def _esperar(condicao, prazo=10.0):
    limite = time.monotonic() + prazo
    while time.monotonic() < limite:
        if condicao():
            return True
        time.sleep(0.05)
    return condicao()


def _conteudo(caminho):
    try:
        with open(caminho) as f:
            return f.read().strip()
    except OSError:
        return ""


def _ler_pid(caminho, prazo=10.0):
    _esperar(lambda: _conteudo(caminho).isdigit(), prazo)
    return int(_conteudo(caminho))


def _vivo(pid):
    """Vivo e nao zumbi (o zumbi ainda responde a kill(pid, 0))."""
    try:
        with open("/proc/%d/stat" % pid) as f:
            conteudo = f.read()
    except OSError:
        return False
    return conteudo[conteudo.rindex(")") + 2:].split()[0] != "Z"


class _ComProcessos(unittest.TestCase):
    """Garante que nenhum grupo iniciado pelo teste sobrevive (criterio de aceite: sem 'sleep 300')."""

    def setUp(self):
        self.raiz = tempfile.mkdtemp(prefix="sss_plat_")
        self.grupos = []
        self.popens = []

    def tearDown(self):
        for pgid in self.grupos:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except OSError:
                pass
        for p in self.popens:
            try:
                p.kill()
            except OSError:
                pass
            p.wait()
        for atual, dirs, _arqs in os.walk(self.raiz):
            for d in dirs:
                os.chmod(os.path.join(atual, d), 0o700)
        shutil.rmtree(self.raiz, ignore_errors=True)

    def iniciar(self, codigo, cwd=None):
        """Script Python em grupo proprio pela plataforma (DEV, sem usuario de execucao)."""
        log = open(os.path.join(self.raiz, "log_%d.txt" % len(self.grupos)), "wb")
        try:
            proc = plataforma.iniciar_processo({"argv": [sys.executable, "-c", codigo], "cwd": cwd or self.raiz,
                                                "env": {}}, log.fileno())
        finally:
            log.close()
        self.grupos.append(proc.pgid)
        self.popens.append(proc.popen)
        return proc


@unittest.skipIf(os.geteuid() == 0, "root sinaliza qualquer processo")
class TestProcessos(_ComProcessos):

    def test_sinalizar_nao_bloqueia_com_processo_que_ignora_sigterm(self):
        pronto = os.path.join(self.raiz, "pronto")
        proc = self.iniciar("import signal,time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                            "open(%r,'w').write('1')\ntime.sleep(300)\n" % pronto)
        self.assertTrue(_esperar(lambda: os.path.exists(pronto)))
        inicio = time.monotonic()
        self.assertTrue(plataforma.sinalizar_grupo(proc, signal.SIGTERM))
        self.assertLess(time.monotonic() - inicio, 0.5)
        time.sleep(0.2)
        self.assertTrue(plataforma.grupo_vivo(proc))
        self.assertTrue(plataforma.sinalizar_grupo(proc, signal.SIGKILL))
        self.assertTrue(_esperar(lambda: not plataforma.grupo_vivo(proc)))

    def test_neto_vivo_depois_do_lider_e_ciclo_nao_bloqueante(self):
        neto_pid = os.path.join(self.raiz, "neto.pid")
        proc = self.iniciar("import subprocess\np = subprocess.Popen(['sleep', '300'])\n"
                            "open(%r,'w').write(str(p.pid))\n" % neto_pid)
        neto = _ler_pid(neto_pid)
        proc.popen.wait(10)
        self.assertTrue(plataforma.grupo_vivo(proc), "o neto continua no grupo depois da saida do lider")
        # Ciclo do executor (F8.1): SIGTERM, consultas sem esperar, SIGKILL se preciso.
        estado, limite = "TERM", time.monotonic() + 10
        while plataforma.grupo_vivo(proc) and time.monotonic() < limite:
            if estado == "TERM":
                self.assertFalse(proc.popen.poll() is None)
                inicio = time.monotonic()
                plataforma.sinalizar_grupo(proc, signal.SIGTERM)
                self.assertLess(time.monotonic() - inicio, 0.5)
                estado, prazo = "AGUARDA", time.monotonic() + 2
            elif estado == "AGUARDA" and time.monotonic() > prazo:
                plataforma.sinalizar_grupo(proc, signal.SIGKILL)
                estado = "KILL"
            time.sleep(0.05)
        self.assertFalse(plataforma.grupo_vivo(proc))
        self.assertFalse(_vivo(neto))
        self.assertFalse(plataforma.sinalizar_grupo(proc, signal.SIGTERM), "ESRCH = grupo vazio")

    def test_identidade_estavel_e_diferente_para_outro_pid(self):
        proc = self.iniciar("import time\ntime.sleep(300)\n")
        minha = plataforma.identidade_processo(os.getpid())
        self.assertIsNotNone(minha)
        self.assertEqual(minha, plataforma.identidade_processo(os.getpid()))
        self.assertEqual(proc.identidade, plataforma.identidade_processo(proc.pid))
        self.assertNotEqual((os.getpid(), minha), (proc.pid, proc.identidade))
        self.assertTrue(plataforma.processo_existe(proc.pid))

    def test_pid_inexistente(self):
        self.assertFalse(plataforma.processo_existe(PID_INEXISTENTE))
        self.assertIsNone(plataforma.identidade_processo(PID_INEXISTENTE))
        self.assertIsNone(plataforma.reabrir_grupo({"pid": PID_INEXISTENTE, "process_start": 1}))

    def test_starttime_com_parenteses_no_nome_do_comando(self):
        campos = ["S"] + [str(i) for i in range(4, 60)]
        conteudo = "4242 (meu ) script) (x)) " + " ".join(campos)
        self.assertEqual(posix._starttime_linux(conteudo), 22)

    def test_identidade_divergente_nao_sinaliza(self):
        proc = self.iniciar("import time\ntime.sleep(300)\n")
        falso = plataforma.Processo(proc.pid, proc.identidade + 1)
        self.assertFalse(plataforma.sinalizar_grupo(falso, signal.SIGTERM))
        self.assertTrue(_vivo(proc.pid))

    def test_reabrir_grupo(self):
        proc = self.iniciar("import time\ntime.sleep(300)\n")
        estado = {"pid": proc.pid, "process_start": proc.identidade, "usuario_execucao": None}
        reaberto = plataforma.reabrir_grupo(estado)
        self.assertEqual((reaberto.pid, reaberto.identidade, reaberto.popen), (proc.pid, proc.identidade, None))
        self.assertIsNone(plataforma.reabrir_grupo(dict(estado, process_start=proc.identidade + 1)))
        with mock.patch.object(posix, "identidade_processo", return_value=None), \
                self.assertLogs("sss_scheduler", "WARNING") as logs:
            sem = plataforma.reabrir_grupo(estado)
        self.assertIn("ORFAO_SEM_IDENTIDADE", logs.output[0])
        self.assertTrue(sem.sem_identidade)
        self.assertFalse(plataforma.sinalizar_grupo(sem, signal.SIGKILL), "sem identidade nunca recebe sinal")
        self.assertTrue(_vivo(proc.pid))

    def test_encerrar_ticket_dev_so_na_pasta_do_ticket(self):
        pasta = os.path.join(self.raiz, "exec", "ticket_7")
        os.makedirs(os.path.join(pasta, "tmp"))
        neto_pid = os.path.join(self.raiz, "neto.pid")
        dentro = self.iniciar("import subprocess,time,os\nos.chdir('tmp')\n"
                              "p = subprocess.Popen(['sleep', '300'])\n"
                              "open(%r,'w').write(str(p.pid))\ntime.sleep(300)\n" % neto_pid, cwd=pasta)
        neto = _ler_pid(neto_pid)
        vizinha = os.path.join(self.raiz, "exec", "ticket_70")
        os.makedirs(vizinha)
        fora = self.iniciar("import time\ntime.sleep(300)\n", cwd=vizinha)
        self.assertEqual(plataforma.encerrar_ticket(os.path.join(self.raiz, "exec"), 7, None, 2), "OK")
        self.assertTrue(_esperar(lambda: not _vivo(dentro.pid) and not _vivo(neto)))
        self.assertTrue(_vivo(fora.pid), "processo do mesmo usuario fora da pasta do ticket")

    def test_iniciar_processo_aplica_umask_limites_e_entrada_nula(self):
        saida = os.path.join(self.raiz, "saida.txt")
        proc = self.iniciar("import os,resource,sys\nm = os.umask(0)\n"
                            "open(%r,'w').write('%%o %%d %%d %%r' %% (m, resource.getrlimit(resource.RLIMIT_CORE)[0],"
                            " resource.getrlimit(resource.RLIMIT_NOFILE)[0], sys.stdin.read()))\n" % saida)
        proc.popen.wait(10)
        with open(saida) as f:
            self.assertEqual(f.read(), "77 0 1024 ''")
        self.assertFalse(plataforma.grupo_vivo(proc))


class TestDublesHelper(unittest.TestCase):
    """Usuario de execucao: o Popen e o do sudo + helper (dubles, sem sudo real)."""

    def setUp(self):
        posix._pedidos_helper[:] = []

    def test_iniciar_processo_com_usuario_manda_especificacao_pela_entrada(self):
        falso = mock.MagicMock(pid=4321)
        with mock.patch.object(posix.subprocess, "Popen", return_value=falso) as popen, \
                mock.patch.object(posix, "identidade_processo", return_value=99):
            proc = plataforma.iniciar_processo({"ticket_id": 3, "argv": ["/bin/true"]}, 7, usuario_execucao="exec1")
        argv = popen.call_args[0][0]
        self.assertEqual(argv, [posix.SUDO, "-n", "-u", "exec1", "--", posix.HELPER, "run"])
        kw = popen.call_args[1]
        self.assertEqual((kw["shell"], kw["start_new_session"], kw["stdout"]), (False, True, 7))
        self.assertNotIn("preexec_fn", kw)
        self.assertEqual(kw["env"], posix._ENV_HELPER)
        falso.stdin.write.assert_called_once_with(b'{"argv": ["/bin/true"], "ticket_id": 3}')
        falso.stdin.close.assert_called_once_with()
        self.assertEqual((proc.pid, proc.identidade, proc.usuario_execucao), (4321, 99, "exec1"))

    def test_sinalizar_pelo_helper_nao_espera(self):
        lento = mock.MagicMock()
        lento.poll.return_value = None
        with mock.patch.object(posix.subprocess, "Popen", return_value=lento) as popen:
            inicio = time.monotonic()
            ok = plataforma.sinalizar_grupo(plataforma.Processo(500, 77, usuario_execucao="exec1"), signal.SIGKILL)
            self.assertLess(time.monotonic() - inicio, 0.5)
        self.assertTrue(ok)
        self.assertEqual(popen.call_args[0][0], [posix.SUDO, "-n", "-u", "exec1", "--", posix.HELPER, "kill",
                                                 "500", "77"])
        lento.wait.assert_not_called()
        self.assertEqual(len(posix._pedidos_helper), 1)
        lento.poll.return_value = 3
        with self.assertLogs("sss_scheduler", "WARNING"):
            posix._colher_pedidos_helper()
        self.assertEqual(posix._pedidos_helper, [])

    def test_falha_ao_entregar_a_especificacao_devolve_o_processo(self):
        falso = mock.MagicMock(pid=4322)
        falso.stdin.write.side_effect = BrokenPipeError(32, "Broken pipe")
        with mock.patch.object(posix.subprocess, "Popen", return_value=falso), \
                mock.patch.object(posix, "identidade_processo", return_value=7):
            with self.assertRaises(plataforma.FalhaAposSpawn) as ctx:
                plataforma.iniciar_processo({"ticket_id": 3, "argv": ["/bin/true"]}, 7, usuario_execucao="exec1")
        self.assertEqual((ctx.exception.processo.pid, ctx.exception.processo.identidade), (4322, 7))
        self.assertIsInstance(ctx.exception.causa, BrokenPipeError)
        falso.stdin.close.assert_called_once_with()

    def test_limpar_dir_script_pelo_helper(self):
        with mock.patch.object(posix, "_executar_curto", return_value=(0, "")) as ex:
            plataforma.limpar_dir_script("/srv/exec/exec1", 9, "exec1")
        self.assertEqual(ex.call_args[0][0], [posix.SUDO, "-n", "-u", "exec1", "--", posix.HELPER, "limpar",
                                              "/srv/exec/exec1", "9"])
        with mock.patch.object(posix, "_executar_curto", return_value=(2, "")):
            with self.assertRaises(RuntimeError):
                plataforma.limpar_dir_script("/srv/exec/exec1", 9, "exec1")

    def test_encerrar_ticket_pelo_helper(self):
        for codigo, esperado in ((0, "OK"), (5, "NAO_SUPORTADO")):
            with mock.patch.object(posix, "_executar_curto", return_value=(codigo, "")) as ex:
                self.assertEqual(plataforma.encerrar_ticket("/srv/exec/exec1", 9, "exec1", 10), esperado)
            self.assertEqual(ex.call_args[0][0], [posix.SUDO, "-n", "-u", "exec1", "--", posix.HELPER,
                                                  "encerrar-ticket", "/srv/exec/exec1", "9", "10"])
        with mock.patch.object(posix, "_executar_curto", return_value=(4, "")):
            with self.assertRaises(RuntimeError):
                plataforma.encerrar_ticket("/srv/exec/exec1", 9, "exec1", 10)


class TestTravaParadaPrivilegio(unittest.TestCase):

    def setUp(self):
        self.raiz = tempfile.mkdtemp(prefix="sss_plat_")

    def tearDown(self):
        shutil.rmtree(self.raiz, ignore_errors=True)

    def test_segunda_trava_falha(self):
        caminho = os.path.join(self.raiz, "agente.lock")
        trava = plataforma.travar_instancia(caminho)
        try:
            # Outro processo (flock e por descricao de arquivo aberto).
            codigo = ("import sys\nsys.path.insert(0, %r)\nfrom plataforma import posix\n"
                      "try:\n    posix.travar_instancia(%r)\nexcept posix.InstanciaJaEmExecucao:\n    sys.exit(7)\n"
                      % (os.path.dirname(os.path.dirname(posix.__file__)), caminho))
            self.assertEqual(subprocess.call([sys.executable, "-c", codigo]), 7)
            with self.assertRaises(plataforma.InstanciaJaEmExecucao):
                plataforma.travar_instancia(caminho)
        finally:
            plataforma.liberar_instancia(trava)
        plataforma.liberar_instancia(plataforma.travar_instancia(caminho))

    def test_usuario_privilegiado(self):
        with mock.patch.object(posix.os, "geteuid", return_value=0):
            self.assertTrue(plataforma.usuario_privilegiado())
        with mock.patch.object(posix.os, "geteuid", return_value=1000):
            self.assertFalse(plataforma.usuario_privilegiado())

    def test_parada_por_sinal_so_seta_a_flag(self):
        antigos = (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT))
        try:
            for sinal in (signal.SIGTERM, signal.SIGINT):
                flag = threading.Event()
                plataforma.instalar_parada(flag)
                os.kill(os.getpid(), sinal)
                self.assertTrue(_esperar(flag.is_set, 2))
        finally:
            signal.signal(signal.SIGTERM, antigos[0])
            signal.signal(signal.SIGINT, antigos[1])


class TestEstadoEDiretorios(unittest.TestCase):

    def setUp(self):
        self.raiz = tempfile.mkdtemp(prefix="sss_plat_")

    def tearDown(self):
        shutil.rmtree(self.raiz, ignore_errors=True)

    def test_gravar_e_ler_estado_atomicos(self):
        for nome in (".sss_spawn", ".sss_proc", ".sss_result"):
            caminho = os.path.join(self.raiz, nome)
            self.assertIsNone(plataforma.ler_estado(caminho))
            plataforma.gravar_estado(caminho, {"ticket_id": 5, "fase": nome})
            plataforma.gravar_estado(caminho, {"ticket_id": 5, "fase": nome, "v": 2})
            self.assertEqual(plataforma.ler_estado(caminho), {"ticket_id": 5, "fase": nome, "v": 2})
            self.assertEqual(os.stat(caminho).st_mode & 0o777, 0o600)
        self.assertEqual(sorted(os.listdir(self.raiz)), [".sss_proc", ".sss_result", ".sss_spawn"])

    def test_gravar_estado_com_falha_nao_deixa_temporario_nem_troca_o_anterior(self):
        caminho = os.path.join(self.raiz, ".sss_proc")
        plataforma.gravar_estado(caminho, {"pid": 1})
        with self.assertRaises(TypeError):
            plataforma.gravar_estado(caminho, {"pid": object()})
        self.assertEqual(plataforma.ler_estado(caminho), {"pid": 1})
        self.assertEqual(os.listdir(self.raiz), [".sss_proc"])

    def test_criar_dir_trabalho_0700(self):
        caminho = os.path.join(self.raiz, "work", "ticket_1")
        old = os.umask(0)
        try:
            plataforma.criar_dir_trabalho(caminho)
        finally:
            os.umask(old)
        self.assertEqual(os.stat(caminho).st_mode & 0o777, 0o700)

    def test_espaco_livre_com_statvfs_simulado(self):
        st = mock.Mock(f_bavail=3 * 1024, f_frsize=4096)
        with mock.patch.object(posix.os, "statvfs", return_value=st) as sv:
            self.assertEqual(plataforma.espaco_livre_mb("/srv/sss"), 12)
        sv.assert_called_once_with("/srv/sss")

    def test_caminho_final(self):
        alvo = os.path.join(self.raiz, "alvo")
        os.mkdir(alvo)
        os.symlink(alvo, os.path.join(self.raiz, "link"))
        self.assertEqual(plataforma.caminho_final(os.path.join(self.raiz, "link")), os.path.realpath(alvo))

    @unittest.skipIf(os.geteuid() == 0, "root sempre tem escrita")
    def test_validar_dir_restrito(self):
        self.assertIsNone(plataforma.validar_dir_restrito(self.raiz))
        os.chmod(self.raiz, 0o750)
        self.assertIsNone(plataforma.validar_dir_restrito(self.raiz), "0750 aceito (log_dir)")
        self.assertEqual(plataforma.validar_dir_restrito("relativo/x"), "CAMINHO_RELATIVO")
        self.assertEqual(plataforma.validar_dir_restrito("/usr/local/sss"), "PASTA_DO_SISTEMA")
        os.symlink("/etc", os.path.join(self.raiz, "etc_link"))
        self.assertEqual(plataforma.validar_dir_restrito(os.path.join(self.raiz, "etc_link")), "PASTA_DO_SISTEMA")
        self.assertEqual(plataforma.validar_dir_restrito(os.path.join(self.raiz, "nao")), "NAO_ENCONTRADO")
        arq = os.path.join(self.raiz, "arq")
        open(arq, "w").close()
        self.assertEqual(plataforma.validar_dir_restrito(arq), "NAO_E_DIRETORIO")
        so_leitura = os.path.join(self.raiz, "ro")
        os.mkdir(so_leitura, 0o500)
        try:
            self.assertEqual(plataforma.validar_dir_restrito(so_leitura), "SEM_ESCRITA")
        finally:
            os.chmod(so_leitura, 0o700)


@unittest.skipIf(os.geteuid() == 0, "root sempre passa em os.access(W_OK)")
class TestValidacoesDeCaminho(unittest.TestCase):

    def setUp(self):
        self.raiz = os.path.realpath(tempfile.mkdtemp(prefix="sss_plat_"))
        self.base = os.path.join(self.raiz, "scripts")
        os.makedirs(os.path.join(self.base, "sub"))
        self.script = os.path.join(self.base, "sub", "ok.py")
        with open(self.script, "w") as f:
            f.write("print(1)\n")
        os.symlink(self.script, os.path.join(self.base, "link.py"))
        os.chmod(self.script, 0o444)
        os.chmod(os.path.join(self.base, "sub"), 0o555)
        os.chmod(self.base, 0o555)
        os.chmod(self.raiz, 0o555)
        self.eu = (os.getuid(),)

    def tearDown(self):
        for atual, dirs, _arqs in os.walk(self.raiz):
            os.chmod(atual, 0o700)
            for d in dirs:
                os.chmod(os.path.join(atual, d), 0o700)
        os.chmod(self.raiz, 0o700)
        os.chmod(self.base, 0o700)
        shutil.rmtree(self.raiz, ignore_errors=True)

    def validar(self, caminho, donos=None, uids_proibidos=()):
        return plataforma.validar_caminho_script(caminho, donos or self.eu, uids_proibidos=uids_proibidos,
                                                 uid_agente=AGENTE_FALSO, parar_em=self.raiz)

    def test_script_valido(self):
        self.assertIsNone(self.validar(self.script))

    def test_link_simbolico(self):
        self.assertEqual(self.validar(os.path.join(self.base, "link.py")), "CAMINHO_COM_LINK")

    def test_sem_acesso(self):
        os.chmod(os.path.join(self.base, "sub"), 0o000)
        self.assertEqual(self.validar(self.script), "SEM_ACESSO")

    def test_dono_proibido_e_dono_fora_da_lista(self):
        self.assertEqual(self.validar(self.script, uids_proibidos=self.eu), "GRAVAVEL_PELO_EXECUTOR")
        self.assertEqual(self.validar(self.script, donos=(AGENTE_FALSO - 1,)), "DONO_INVALIDO")

    def test_item_da_arvore_gravavel_rejeitado(self):
        os.chmod(os.path.join(self.base, "sub"), 0o775)
        self.assertEqual(self.validar(self.script), "GRAVAVEL_GRUPO_OUTROS")
        os.chmod(os.path.join(self.base, "sub"), 0o555)
        self.assertEqual(plataforma.validar_caminho_script(self.script, self.eu, parar_em=self.raiz),
                         "GRAVAVEL_PELO_AGENTE", "arquivo do proprio agente")

    def test_inexistente_e_nao_arquivo(self):
        self.assertEqual(self.validar(os.path.join(self.base, "nao.py")), "NAO_ENCONTRADO")
        self.assertEqual(self.validar(os.path.join(self.base, "sub")), "NAO_E_ARQUIVO")

    def test_interpretador_pelo_validar_executavel(self):
        real = plataforma.validar_interpretador_executavel("/bin/sh", (0,), uid_agente=AGENTE_FALSO)
        self.assertEqual(real, os.path.realpath("/bin/sh"))
        with mock.patch.object(path_guard, "validar_executavel", return_value="/x") as ve:
            plataforma.validar_interpretador_executavel("/usr/bin/python3", (0, 5), uid_agente=9,
                                                        uids_proibidos=(8,), dirs_sss=("/srv",))
        ve.assert_called_once_with("/usr/bin/python3", (0, 5), uid_agente=9, uids_proibidos=(8,), dirs_sss=("/srv",))
        with self.assertRaises(path_guard.PathGuardErro):
            plataforma.validar_interpretador_executavel("bin/sh", (0,), uid_agente=AGENTE_FALSO)


class TestArquivoRestrito(unittest.TestCase):

    def setUp(self):
        fd, self.caminho = tempfile.mkstemp(prefix="sss_plat_")
        os.close(fd)

    def tearDown(self):
        os.unlink(self.caminho)

    def test_ok_e_rejeitado(self):
        os.chmod(self.caminho, 0o600)
        self.assertIsNone(plataforma.validar_arquivo_restrito(self.caminho)[0])
        os.chmod(self.caminho, 0o400)
        self.assertIsNone(plataforma.validar_arquivo_restrito(self.caminho)[0])
        for modo in (0o640, 0o604, 0o660):
            os.chmod(self.caminho, modo)
            self.assertEqual(plataforma.validar_arquivo_restrito(self.caminho)[0], "PERMISSAO_INSEGURA")
        os.chmod(self.caminho, 0o600)
        with mock.patch.object(posix.os, "geteuid", return_value=os.geteuid() + 1):
            self.assertEqual(plataforma.validar_arquivo_restrito(self.caminho)[0], "DONO_INVALIDO")
        self.assertEqual(plataforma.validar_arquivo_restrito(os.path.dirname(self.caminho))[0], "NAO_REGULAR")


class TestValidarExecucao(unittest.TestCase):
    """Dubles do helper (stat), dos usuarios (pwd) e do sudo -n -l."""

    HELPER = "/opt/sss/bin/sss-helper"
    EXEC = "/srv/sss/exec"
    UID_EXEC = 2001

    def setUp(self):
        self.stats = {
            self.HELPER: _Stat(0, 0o100755),
            "/opt/sss/bin": _Stat(0, 0o040755),
            os.path.join(self.EXEC, "exec1"): _Stat(self.UID_EXEC, 0o040700),
        }
        self.usuarios = {"exec1": _Pw("exec1", self.UID_EXEC), "root": _Pw("root", 0),
                         "agente": _Pw("agente", os.geteuid())}
        self.sudo = {"exec1": (0, "%s\n" % self.HELPER)}
        self.chamadas = []

    def _stat(self, caminho, *a, **k):
        if caminho in self.stats:
            return self.stats[caminho]
        raise FileNotFoundError(caminho)

    def _getpwnam(self, nome):
        return self.usuarios[nome]

    def _executar(self, argv):
        self.chamadas.append(argv)
        return self.sudo.get(argv[4], (1, "Sorry, user may not run sudo"))

    def validar(self, usuarios=("exec1",), owner_uids=(1500,)):
        with mock.patch.object(posix.os, "stat", side_effect=self._stat), \
                mock.patch.object(posix.pwd, "getpwnam", side_effect=self._getpwnam):
            return plataforma.validar_execucao([("PROD", u) for u in usuarios], self.EXEC, owner_uids,
                                               helper=self.HELPER, executar=self._executar, usuario_agente="agente")

    def test_tudo_certo(self):
        self.assertEqual(self.validar(), [])
        self.assertEqual(self.chamadas, [["/usr/bin/sudo", "-n", "-l", "-u", "exec1", self.HELPER]])

    def test_helper(self):
        self.stats[self.HELPER] = _Stat(1000, 0o100755)
        self.assertIn("nao pertence ao root", " ".join(self.validar()))
        self.stats[self.HELPER] = _Stat(0, 0o100775)
        self.assertIn("modo 0755", " ".join(self.validar()))
        self.stats[self.HELPER] = _Stat(0, 0o100755)
        self.stats["/opt/sss/bin"] = _Stat(0, 0o040775)
        self.assertIn("so do root", " ".join(self.validar()))
        del self.stats[self.HELPER]
        self.assertIn("nao encontrado", " ".join(self.validar()))

    def test_usuarios_invalidos(self):
        self.assertIn("nao existe", " ".join(self.validar(usuarios=("fantasma",))))
        self.assertIn("nao pode ser root", " ".join(self.validar(usuarios=("root",))))
        self.assertIn("proprio usuario do agente", " ".join(self.validar(usuarios=("agente",))))
        self.assertIn("script_owner_uids", " ".join(self.validar(owner_uids=(self.UID_EXEC,))))

    def test_sudo_sem_regra_e_pasta(self):
        self.sudo["exec1"] = (0, "/usr/bin/outro\n")
        self.assertIn("sem a regra do helper", " ".join(self.validar()))
        self.sudo["exec1"] = (0, self.HELPER)
        self.stats[os.path.join(self.EXEC, "exec1")] = _Stat(self.UID_EXEC, 0o040750)
        self.assertIn("modo 0700", " ".join(self.validar()))
        del self.stats[os.path.join(self.EXEC, "exec1")]
        self.assertIn("nao existe", " ".join(self.validar()))


class TestInterface(unittest.TestCase):

    def test_exporta_a_interface_do_readme(self):
        for nome in ("NOME", "Processo", "iniciar_processo", "sinalizar_grupo", "grupo_vivo", "validar_execucao",
                     "gravar_estado", "ler_estado", "encerrar_ticket", "espaco_livre_mb", "identidade_processo",
                     "processo_existe", "reabrir_grupo", "travar_instancia", "liberar_instancia",
                     "usuario_privilegiado", "validar_arquivo_restrito", "validar_dir_restrito",
                     "validar_caminho_script", "caminho_final", "criar_dir_trabalho", "instalar_parada"):
            self.assertTrue(hasattr(plataforma, nome), nome)
        self.assertIn(plataforma.NOME, ("LINUX", "UNIX"))
        self.assertFalse(hasattr(plataforma, "encerrar_grupo"), "encerramento escalonado e do executor (F8.1)")


if __name__ == "__main__":
    unittest.main()
