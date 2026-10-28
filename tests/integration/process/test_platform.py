# -*- coding: utf-8 -*-
"""Testes de src/sss/platform/os_platform (README §8.0, AGENTS §3.2 e §7): processos reais em grupo proprio, trava,
estado local, validacoes de arquivos e caminhos e o ticket_files. Somente POSIX (CR-005)."""
from tests.support import _testenv  # noqa: F401

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

from sss.platform import os_platform
from sss.platform.os_platform import posix

NONEXISTENT_PID = 2 ** 31 - 2


def _wait(condition, deadline=10.0):
    limit = time.monotonic() + deadline
    while time.monotonic() < limit:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def _content(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def _read_pid(path, deadline=10.0):
    _wait(lambda: _content(path).isdigit(), deadline)
    return int(_content(path))


def _alive(pid):
    """Vivo e nao zumbi (o zumbi ainda responde a kill(pid, 0))."""
    try:
        with open("/proc/%d/stat" % pid) as f:
            content = f.read()
    except OSError:
        return False
    return content[content.rindex(")") + 2:].split()[0] != "Z"


class _WithProcesses(unittest.TestCase):
    """Garante que nenhum grupo iniciado pelo teste sobrevive (criterio de aceite: sem 'sleep 300')."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sss_plat_")
        self.groups = []
        self.popens = []

    def tearDown(self):
        for pgid in self.groups:
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
        for current, dirs, _arqs in os.walk(self.root):
            for d in dirs:
                os.chmod(os.path.join(current, d), 0o700)
        shutil.rmtree(self.root, ignore_errors=True)

    def start(self, code, cwd=None):
        """Script Python em grupo proprio pela plataforma (DEV, sem usuario de execucao)."""
        log = open(os.path.join(self.root, "log_%d.txt" % len(self.groups)), "wb")
        try:
            proc = os_platform.start_process({"argv": [sys.executable, "-c", code], "cwd": cwd or self.root,
                                                "env": {}}, log.fileno())
        finally:
            log.close()
        self.groups.append(proc.pgid)
        self.popens.append(proc.popen)
        return proc


@unittest.skipIf(os.geteuid() == 0, "root sinaliza qualquer processo")
class TestProcesses(_WithProcesses):

    def test_sinalizar_nao_bloqueia_com_processo_que_ignora_sigterm(self):
        ready = os.path.join(self.root, "pronto")
        proc = self.start("import signal,time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                            "open(%r,'w').write('1')\ntime.sleep(300)\n" % ready)
        self.assertTrue(_wait(lambda: os.path.exists(ready)))
        start = time.monotonic()
        self.assertTrue(os_platform.signal_group(proc, signal.SIGTERM))
        self.assertLess(time.monotonic() - start, 0.5)
        time.sleep(0.2)
        self.assertTrue(os_platform.group_alive(proc))
        self.assertTrue(os_platform.signal_group(proc, signal.SIGKILL))
        self.assertTrue(_wait(lambda: not os_platform.group_alive(proc)))

    def test_neto_vivo_depois_do_lider_e_ciclo_nao_bloqueante(self):
        grandchild_pid = os.path.join(self.root, "neto.pid")
        proc = self.start("import subprocess\np = subprocess.Popen(['sleep', '300'])\n"
                            "open(%r,'w').write(str(p.pid))\n" % grandchild_pid)
        grandchild = _read_pid(grandchild_pid)
        proc.popen.wait(10)
        self.assertTrue(os_platform.group_alive(proc), "o neto continua no grupo depois da saida do lider")
        # Ciclo do executor (F8.1): SIGTERM, consultas sem esperar, SIGKILL se preciso.
        state, limit = "TERM", time.monotonic() + 10
        while os_platform.group_alive(proc) and time.monotonic() < limit:
            if state == "TERM":
                self.assertFalse(proc.popen.poll() is None)
                start = time.monotonic()
                os_platform.signal_group(proc, signal.SIGTERM)
                self.assertLess(time.monotonic() - start, 0.5)
                state, deadline = "AGUARDA", time.monotonic() + 2
            elif state == "AGUARDA" and time.monotonic() > deadline:
                os_platform.signal_group(proc, signal.SIGKILL)
                state = "KILL"
            time.sleep(0.05)
        self.assertFalse(os_platform.group_alive(proc))
        self.assertFalse(_alive(grandchild))
        self.assertFalse(os_platform.signal_group(proc, signal.SIGTERM), "ESRCH = grupo vazio")

    def test_identidade_estavel_e_diferente_para_outro_pid(self):
        proc = self.start("import time\ntime.sleep(300)\n")
        my = os_platform.process_identity(os.getpid())
        self.assertIsNotNone(my)
        self.assertEqual(my, os_platform.process_identity(os.getpid()))
        self.assertEqual(proc.identity, os_platform.process_identity(proc.pid))
        self.assertNotEqual((os.getpid(), my), (proc.pid, proc.identity))
        self.assertTrue(os_platform.process_exists(proc.pid))

    def test_pid_inexistente(self):
        self.assertFalse(os_platform.process_exists(NONEXISTENT_PID))
        self.assertIsNone(os_platform.process_identity(NONEXISTENT_PID))
        self.assertIsNone(os_platform.reopen_group({"pid": NONEXISTENT_PID, "process_start": 1}))

    def test_starttime_com_parenteses_no_nome_do_comando(self):
        fields = ["Y"] + [str(i) for i in range(4, 60)]
        content = "4242 (meu ) script) (x)) " + " ".join(fields)
        self.assertEqual(posix._linux_starttime(content), 22)

    def test_identidade_divergente_nao_sinaliza(self):
        proc = self.start("import time\ntime.sleep(300)\n")
        fake = os_platform.Process(proc.pid, proc.identity + 1)
        self.assertFalse(os_platform.signal_group(fake, signal.SIGTERM))
        self.assertTrue(_alive(proc.pid))

    def test_reabrir_grupo(self):
        proc = self.start("import time\ntime.sleep(300)\n")
        state = {"pid": proc.pid, "process_start": proc.identity}
        reopened = os_platform.reopen_group(state)
        self.assertEqual((reopened.pid, reopened.identity, reopened.popen), (proc.pid, proc.identity, None))
        self.assertIsNone(os_platform.reopen_group(dict(state, process_start=proc.identity + 1)))
        with mock.patch.object(posix, "process_identity", return_value=None), \
                self.assertLogs("sss_scheduler", "WARNING") as logs:
            without = os_platform.reopen_group(state)
        self.assertIn("ORFAO_SEM_IDENTIDADE", logs.output[0])
        self.assertTrue(without.no_identity)
        self.assertFalse(os_platform.signal_group(without, signal.SIGKILL), "sem identidade nunca recebe sinal")
        self.assertTrue(_alive(proc.pid))

    def test_encerrar_ticket_dev_so_na_pasta_do_ticket(self):
        dir_value = os.path.join(self.root, "exec", "ticket_7")
        os.makedirs(os.path.join(dir_value, "tmp"))
        grandchild_pid = os.path.join(self.root, "neto.pid")
        inside = self.start("import subprocess,time,os\nos.chdir('tmp')\n"
                              "p = subprocess.Popen(['sleep', '300'])\n"
                              "open(%r,'w').write(str(p.pid))\ntime.sleep(300)\n" % grandchild_pid, cwd=dir_value)
        grandchild = _read_pid(grandchild_pid)
        neighbor = os.path.join(self.root, "exec", "ticket_70")
        os.makedirs(neighbor)
        outside = self.start("import time\ntime.sleep(300)\n", cwd=neighbor)
        self.assertEqual(os_platform.stop_ticket(os.path.join(self.root, "exec"), 7, 2), "OK")
        self.assertTrue(_wait(lambda: not _alive(inside.pid) and not _alive(grandchild)))
        self.assertTrue(_alive(outside.pid), "processo do mesmo usuario fora da pasta do ticket")

    def test_iniciar_processo_aplica_umask_limites_e_entrada_nula(self):
        output = os.path.join(self.root, "saida.txt")
        proc = self.start("import os,resource,sys\nm = os.umask(0)\n"
                            "open(%r,'w').write('%%o %%d %%d %%r' %% (m, resource.getrlimit(resource.RLIMIT_CORE)[0],"
                            " resource.getrlimit(resource.RLIMIT_NOFILE)[0], sys.stdin.read()))\n" % output)
        proc.popen.wait(10)
        with open(output) as f:
            self.assertEqual(f.read(), "77 0 1024 ''")
        self.assertFalse(os_platform.group_alive(proc))


class TestOutputDir(unittest.TestCase):
    """CR-012 (README §8.13): o ticket_files.py com a conta do agente (CR-032, D7)."""

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="sss_saida_"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.base = os.path.join(self.root, "output", "producao")
        self.rel = "carga/2026/10/20/14/05/ticket_5"

    def test_argv_do_ticket_files(self):
        self.assertEqual(posix._files_argv("clean-output", ["/b", 7]),
                         [sys.executable, "-I", posix.TICKET_FILES, "clean-output", "/b", "7"])
        self.assertTrue(os.path.isfile(posix.TICKET_FILES), posix.TICKET_FILES)

    def test_iniciar_empacotar_nao_espera(self):
        fake = mock.MagicMock(pid=4400)
        with mock.patch.object(posix.subprocess, "Popen", return_value=fake) as popen, \
                mock.patch.object(posix, "process_identity", return_value=55):
            proc = os_platform.start_pack(self.base, self.rel, 1048576, 10, 9)
        self.assertEqual(popen.call_args[0][0], [sys.executable, "-I", posix.TICKET_FILES, "pack",
                                                 self.base, self.rel, "1048576", "10"])
        kw = popen.call_args[1]
        self.assertEqual((kw["shell"], kw["start_new_session"], kw["stdout"], kw["env"]),
                         (False, True, 9, posix._ENV_MINIMAL))
        fake.wait.assert_not_called()
        self.assertEqual((proc.pid, proc.identity), (4400, 55))

    def test_limpar_saida_falha(self):
        with mock.patch.object(posix, "_run_short", return_value=(0, "")) as ex:
            os_platform.clean_output(self.base, self.rel)
        self.assertEqual(ex.call_args_list[0][0][0][-3:], ["clean-output", self.base, self.rel])
        self.assertFalse(hasattr(os_platform, "purge_output"), "CR-030: sem purge")
        with mock.patch.object(posix, "_run_short", return_value=(4, "")):
            with self.assertRaises(RuntimeError):
                os_platform.clean_output(self.base, self.rel)

    def test_dev_cria_empacota_e_limpa_com_o_proprio_usuario(self):
        import io
        import zipfile
        dir_value = os_platform.create_output_dir(self.base, self.rel)
        self.assertEqual(dir_value, os.path.join(self.base, self.rel))
        self.assertEqual(os.stat(dir_value).st_mode & 0o777, 0o700)
        self.assertEqual(os_platform.create_output_dir(self.base, self.rel), dir_value, "idempotente")
        with open(os.path.join(dir_value, "r.txt"), "w") as f:
            f.write("resultado")
        destination = os.path.join(self.root, "output.zip")
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            proc = os_platform.start_pack(self.base, self.rel, 1048576, 10, fd)
        finally:
            os.close(fd)
        self.assertEqual(proc.popen.wait(30), 0)
        with open(destination, "rb") as f:
            self.assertEqual(zipfile.ZipFile(io.BytesIO(f.read())).read("r.txt"), b"resultado")
        os_platform.clean_output(self.base, self.rel)
        self.assertFalse(os.path.exists(dir_value))

    def test_cr014_dev_cria_a_entrada_e_preserva_a_existente(self):
        base = os.path.join(self.root, "input", "producao")
        dir_value = os_platform.create_input_dir(base, "carga")
        self.assertEqual((dir_value, os.stat(dir_value).st_mode & 0o777), (os.path.join(base, "carga"), 0o700))
        with open(os.path.join(dir_value, "lote.csv"), "w") as f:
            f.write("1;2\n")
        os.chmod(dir_value, 0o750)
        self.assertEqual(os_platform.create_input_dir(base, "carga"), dir_value, "idempotente")
        self.assertEqual(os.stat(dir_value).st_mode & 0o777, 0o750, "a existente fica como esta")
        self.assertEqual(os.listdir(dir_value), ["lote.csv"], "conteudo permanente")
        outside = os.path.join(self.root, "fora_entrada")
        os.mkdir(outside)
        os.symlink(outside, os.path.join(base, "ligada"))
        with self.assertRaises(RuntimeError):
            os_platform.create_input_dir(base, "ligada")

    def test_cr019_dev_cria_a_pasta_de_trabalho(self):
        base = os.path.join(self.root, "work_scripts", "producao")
        dir_value = os_platform.create_script_work_dir(base, self.rel)
        self.assertEqual((dir_value, os.stat(dir_value).st_mode & 0o777), (os.path.join(base, self.rel), 0o700))
        self.assertEqual(os_platform.create_script_work_dir(base, self.rel), dir_value, "idempotente")
        outside = os.path.join(self.root, "fora_trabalho")
        os.mkdir(outside)
        os.symlink(outside, os.path.join(base, "ligada"))
        with self.assertRaises(RuntimeError) as ctx:
            os_platform.create_script_work_dir(base, "ligada/2026/10/20/14/05/ticket_12")
        self.assertIn("pasta de trabalho", str(ctx.exception))
        self.assertEqual(os.listdir(outside), [])

    def test_dev_recusa_link_no_caminho(self):
        os.makedirs(self.base)
        outside = os.path.join(self.root, "fora")
        os.mkdir(outside)
        os.symlink(outside, os.path.join(self.base, "carga"))
        with self.assertRaises(RuntimeError):
            os_platform.create_output_dir(self.base, self.rel)
        self.assertEqual(os.listdir(outside), [])


class TestLockStopPrivilege(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sss_plat_")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_segunda_trava_falha(self):
        path = os.path.join(self.root, "agente.lock")
        lock = os_platform.lock_instance(path)
        try:
            # Outro processo (flock e por descricao de arquivo aberto).
            code = ("import sys\nsys.path.insert(0, %r)\nfrom sss.platform.os_platform import posix\n"
                      "try:\n    posix.lock_instance(%r)\nexcept posix.InstanceAlreadyRunning:\n    sys.exit(7)\n"
                      % (os.path.join(_testenv.APP_DIR, "src"), path))
            self.assertEqual(subprocess.call([sys.executable, "-c", code]), 7)
            with self.assertRaises(os_platform.InstanceAlreadyRunning):
                os_platform.lock_instance(path)
        finally:
            os_platform.release_instance(lock)
        os_platform.release_instance(os_platform.lock_instance(path))

    def test_usuario_privilegiado(self):
        with mock.patch.object(posix.os, "geteuid", return_value=0):
            self.assertTrue(os_platform.is_privileged_user())
        with mock.patch.object(posix.os, "geteuid", return_value=1000):
            self.assertFalse(os_platform.is_privileged_user())

    def test_parada_por_sinal_so_seta_a_flag(self):
        old = (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT))
        try:
            for signal_value in (signal.SIGTERM, signal.SIGINT):
                flag = threading.Event()
                os_platform.install_stop_handler(flag)
                os.kill(os.getpid(), signal_value)
                self.assertTrue(_wait(flag.is_set, 2))
        finally:
            signal.signal(signal.SIGTERM, old[0])
            signal.signal(signal.SIGINT, old[1])


class TestStateAndDirectories(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sss_plat_")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_gravar_e_ler_estado_atomicos(self):
        for name in (".sss_spawn", ".sss_proc", ".sss_result"):
            path = os.path.join(self.root, name)
            self.assertIsNone(os_platform.read_state(path))
            os_platform.write_state(path, {"ticket_id": 5, "fase": name})
            os_platform.write_state(path, {"ticket_id": 5, "fase": name, "v": 2})
            self.assertEqual(os_platform.read_state(path), {"ticket_id": 5, "fase": name, "v": 2})
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertEqual(sorted(os.listdir(self.root)), [".sss_proc", ".sss_result", ".sss_spawn"])

    def test_gravar_estado_com_falha_nao_deixa_temporario_nem_troca_o_anterior(self):
        path = os.path.join(self.root, ".sss_proc")
        os_platform.write_state(path, {"pid": 1})
        with self.assertRaises(TypeError):
            os_platform.write_state(path, {"pid": object()})
        self.assertEqual(os_platform.read_state(path), {"pid": 1})
        self.assertEqual(os.listdir(self.root), [".sss_proc"])

    def test_criar_dir_trabalho_0700(self):
        path = os.path.join(self.root, "work", "ticket_1")
        old = os.umask(0)
        try:
            os_platform.create_work_dir(path)
        finally:
            os.umask(old)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o700)

    def test_espaco_livre_com_statvfs_simulado(self):
        st = mock.Mock(f_bavail=3 * 1024, f_frsize=4096)
        with mock.patch.object(posix.os, "statvfs", return_value=st) as sv:
            self.assertEqual(os_platform.free_space_mb("/srv/sss"), 12)
        sv.assert_called_once_with("/srv/sss")

    def test_caminho_final(self):
        target = os.path.join(self.root, "alvo")
        os.mkdir(target)
        os.symlink(target, os.path.join(self.root, "link"))
        self.assertEqual(os_platform.final_path(os.path.join(self.root, "link")), os.path.realpath(target))

    @unittest.skipIf(os.geteuid() == 0, "root sempre tem escrita")
    def test_validar_dir_restrito(self):
        self.assertIsNone(os_platform.validate_restricted_dir(self.root))
        os.chmod(self.root, 0o750)
        self.assertIsNone(os_platform.validate_restricted_dir(self.root), "0750 aceito (log_dir)")
        self.assertEqual(os_platform.validate_restricted_dir("relativo/x"), "RELATIVE_PATH")
        self.assertEqual(os_platform.validate_restricted_dir("/usr/local/sss"), "SYSTEM_DIR")
        os.symlink("/etc", os.path.join(self.root, "etc_link"))
        self.assertEqual(os_platform.validate_restricted_dir(os.path.join(self.root, "etc_link")), "SYSTEM_DIR")
        self.assertEqual(os_platform.validate_restricted_dir(os.path.join(self.root, "nao")), "NOT_FOUND")
        file = os.path.join(self.root, "arq")
        open(file, "w").close()
        self.assertEqual(os_platform.validate_restricted_dir(file), "NAO_E_DIRETORIO")
        only_read = os.path.join(self.root, "ro")
        os.mkdir(only_read, 0o500)
        try:
            self.assertEqual(os_platform.validate_restricted_dir(only_read), "SEM_ESCRITA")
        finally:
            os.chmod(only_read, 0o700)


@unittest.skipIf(os.geteuid() == 0, "root sempre passa em os.access(W_OK)")
class TestPathValidations(unittest.TestCase):

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="sss_plat_"))
        self.base = os.path.join(self.root, "scripts")
        os.makedirs(os.path.join(self.base, "sub"))
        self.script = os.path.join(self.base, "sub", "ok.py")
        with open(self.script, "w") as f:
            f.write("print(1)\n")
        os.symlink(self.script, os.path.join(self.base, "link.py"))
        os.chmod(self.script, 0o444)
        os.chmod(os.path.join(self.base, "sub"), 0o555)
        os.chmod(self.base, 0o555)
        os.chmod(self.root, 0o555)

    def tearDown(self):
        for current, dirs, _arqs in os.walk(self.root):
            os.chmod(current, 0o700)
            for d in dirs:
                os.chmod(os.path.join(current, d), 0o700)
        os.chmod(self.root, 0o700)
        os.chmod(self.base, 0o700)
        shutil.rmtree(self.root, ignore_errors=True)

    def validate(self, path):
        return os_platform.validate_script_path(path)

    def test_script_valido(self):
        self.assertIsNone(self.validate(self.script))

    def test_link_simbolico_vale_o_arquivo_real(self):
        # CR-011: o link e aceito e as checagens valem para o destino.
        self.assertIsNone(self.validate(os.path.join(self.base, "link.py")))
        os.chmod(self.script, 0o666)
        self.assertEqual(self.validate(os.path.join(self.base, "link.py")), "GROUP_OTHER_WRITABLE",
                         "modo conferido no arquivo real")

    def test_sem_acesso(self):
        os.chmod(os.path.join(self.base, "sub"), 0o000)
        self.assertEqual(self.validate(self.script), "NO_ACCESS")

    def test_so_o_arquivo_e_conferido(self):
        # CR-011 (S2): pasta gravavel nao e conferida; o arquivo gravavel por grupo ou outros e recusado.
        os.chmod(os.path.join(self.base, "sub"), 0o777)
        self.assertIsNone(self.validate(self.script))
        os.chmod(self.script, 0o464)
        self.assertEqual(self.validate(self.script), "GROUP_OTHER_WRITABLE")

    def test_ciclo_de_links(self):
        os.chmod(self.base, 0o755)
        os.symlink("ciclo_b", os.path.join(self.base, "ciclo_a"))
        os.symlink("ciclo_a", os.path.join(self.base, "ciclo_b"))
        self.assertEqual(self.validate(os.path.join(self.base, "ciclo_a")), "NOT_FOUND")

    def test_inexistente_e_nao_arquivo(self):
        self.assertEqual(self.validate(os.path.join(self.base, "nao.py")), "NOT_FOUND")
        self.assertEqual(self.validate(os.path.join(self.base, "sub")), "NOT_A_FILE")


class TestRestrictedFile(unittest.TestCase):

    def setUp(self):
        fd, self.path = tempfile.mkstemp(prefix="sss_plat_")
        os.close(fd)

    def tearDown(self):
        os.unlink(self.path)

    def test_ok_e_rejeitado(self):
        os.chmod(self.path, 0o600)
        self.assertIsNone(os_platform.validate_restricted_file(self.path)[0])
        os.chmod(self.path, 0o400)
        self.assertIsNone(os_platform.validate_restricted_file(self.path)[0])
        for mode in (0o640, 0o604, 0o660):
            os.chmod(self.path, mode)
            self.assertEqual(os_platform.validate_restricted_file(self.path)[0], "PERMISSAO_INSEGURA")
        os.chmod(self.path, 0o600)
        with mock.patch.object(posix.os, "geteuid", return_value=os.geteuid() + 1):
            self.assertEqual(os_platform.validate_restricted_file(self.path)[0], "DONO_INVALIDO")
        self.assertEqual(os_platform.validate_restricted_file(os.path.dirname(self.path))[0], "NAO_REGULAR")


class TestInterface(unittest.TestCase):

    def test_exporta_a_interface_do_readme(self):
        for name in ("NAME", "Process", "start_process", "signal_group", "group_alive",
                     "write_state", "read_state", "stop_ticket", "free_space_mb", "process_identity",
                     "process_exists", "reopen_group", "lock_instance", "release_instance",
                     "is_privileged_user", "validate_restricted_file", "validate_restricted_dir",
                     "validate_script_path", "final_path", "create_work_dir", "install_stop_handler",
                     "create_output_dir", "start_pack", "clean_output", "TICKET_FILES"):
            self.assertTrue(hasattr(os_platform, name), name)
        for name in ("validate_execution", "validate_output_dirs", "set_helper", "clean_script_dir", "HELPER",
                     "FailureAfterSpawn"):
            self.assertFalse(hasattr(os_platform, name), "CR-032 (D7): sem sudo nem helper (%s)" % name)
        self.assertIn(os_platform.NAME, ("LINUX", "UNIX"))
        self.assertFalse(hasattr(os_platform, "encerrar_grupo"), "encerramento escalonado e do executor (F8.1)")


if __name__ == "__main__":
    unittest.main()
