# -*- coding: utf-8 -*-
"""Testes do executor (README §8.4, §8.7; AGENTS §3.2 e §7.4; CR-007 R-01 a R-04, R-17; CR-008 R-01, R-26, R-36).

Spawn real (POSIX, DEV sem usuario de execucao) em diretorio temporario. As esperas deste arquivo sao so do
harness de teste (_esperar): o executor nunca espera. Todo processo e encerrado no tearDown pela mesma
maquina de estados (request_stop/advance_stop).
"""
from tests.support import _testenv  # noqa: F401

import collections
import datetime
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import env_builder
import executor
from sss.core import params_compiler as pc
from sss.platform import path_guard
from sss.platform import os_platform
from sss.config.sss_config import Secrets

FAKE_AGENT = 2 ** 31 - 3
STARTED_AT = datetime.datetime(2026, 10, 16, 14, 5, 33)
SH = "/bin/sh"

_AgentStub = collections.namedtuple("_Agente", "agent_id child_locale env_passthrough exec_users exec_work_dir")
_Cfg = collections.namedtuple("_Cfg", "agent")
_CfgSnap = collections.namedtuple("_CfgSnap", "interpreters")


def _wait(condition, deadline=10.0):
    """So do harness de teste."""
    limit = time.monotonic() + deadline
    while time.monotonic() < limit:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


def _alive(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            content = f.read()
    except OSError:
        return False
    return content[content.rindex(")") + 2:].split()[0] != "Z"


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


@unittest.skipIf(os.geteuid() == 0, "o agente nunca roda como root")
class _Base(unittest.TestCase):

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="sss_exec_"))
        self.work = os.path.join(self.root, "work")
        self.logs = os.path.join(self.root, "logs")
        os.mkdir(self.work, 0o700)
        os.mkdir(self.logs, 0o750)
        self.execs = []
        self.extras = []

    def tearDown(self):
        for ex in self.execs:
            if ex.process is None:
                continue
            ex.phase = None if ex.phase == executor.PHASE_END else ex.phase
            executor.request_stop(ex, time.monotonic(), grace_s=0)
            _wait(lambda: executor.advance_stop(ex, time.monotonic()), 5)
            if ex.process.popen is not None:
                ex.process.popen.wait(5)
        for p in self.extras:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            p.wait()
        for current, dirs, _arqs in os.walk(self.root):
            for d in dirs:
                os.chmod(os.path.join(current, d), 0o700)
        shutil.rmtree(self.root, ignore_errors=True)

    def start(self, command, ticket_id=1, argv=None, env=None, label=None):
        wd = executor.prepare_directory(self.work, ticket_id)
        fd, _partial = executor.open_log(self.logs, "DEV", "Teste Script", STARTED_AT, ticket_id)
        ex = executor.start(ticket_id, argv or [SH, "-c", command], fd, env or {"PATH": "/usr/bin:/bin"}, wd,
                              None, None, os_platform.DEFAULT_RLIMITS, label or "SSS-srv-01-%d" % ticket_id)
        self.execs.append(ex)
        return ex

    def dir_log(self):
        return os.path.join(self.logs, "dev", "teste_script", "2026", "10", "16", "14", "05")

    def until_exit(self, ex, deadline=10):
        self.assertTrue(_wait(lambda: executor.check(ex) is not None, deadline), "o script nao terminou")
        return ex.returncode

    def stop(self, ex, grace_s=1, deadline=10):
        """Ciclo do laco do daemon: cada chamada volta logo; o harness so repete ate o grupo acabar."""
        start = time.monotonic()
        executor.request_stop(ex, time.monotonic(), grace_s=grace_s)
        self.assertLess(time.monotonic() - start, 0.5)

        def _passo():
            t = time.monotonic()
            end = executor.advance_stop(ex, time.monotonic())
            self.assertLess(time.monotonic() - t, 0.5, "avancar_encerramento nao pode bloquear")
            return end
        self.assertTrue(_wait(_passo, deadline), "o grupo nao acabou")
        return time.monotonic() - start


class TestLogAndOutput(_Base):

    def test_log_por_minuto_rename_e_permissoes(self):
        old = os.umask(0o077)
        try:
            ex = self.start("echo ola")
        finally:
            os.umask(old)
        self.assertEqual(self.until_exit(ex), 0)
        final = os.path.join(self.dir_log(), "ticket_1_%d.log" % ex.pid)
        self.assertEqual(ex.log_path, final)
        self.assertEqual(_read(final), "ola\n")
        self.assertFalse(os.path.exists(os.path.join(self.dir_log(), "ticket_1.log.parcial")), "rename atomico")
        self.assertEqual(os.stat(final).st_mode & 0o777, 0o600)
        dir_value = self.logs
        for level in ("dev", "teste_script", "2026", "10", "16", "14", "05"):
            dir_value = os.path.join(dir_value, level)
            self.assertEqual(os.stat(dir_value).st_mode & 0o777, 0o750, dir_value)
        self.stop(ex)

    def test_log_com_o_excl(self):
        fd, path = executor.open_log(self.logs, "DEV", "Teste Script", STARTED_AT, 9)
        try:
            with self.assertRaises(FileExistsError):
                executor.open_log(self.logs, "DEV", "Teste Script", STARTED_AT, 9)
        finally:
            executor._open_logs.pop(fd, None)
            os.close(fd)
        self.assertTrue(path.endswith("/ticket_9.log.parcial"))

    def test_saida_de_2_mb_sem_travar(self):
        ex = self.start("head -c 2097152 /dev/zero | tr '\\000' a")
        self.assertEqual(self.until_exit(ex, 20), 0)
        self.assertEqual(os.path.getsize(ex.log_path), 2097152)
        self.stop(ex)

    def test_abrir_log_exige_ambiente(self):
        for empty in (None, "", "INTERNAL"):
            with self.assertRaises(ValueError):
                executor.open_log(self.logs, empty, "Teste Script", STARTED_AT, 30)
        self.assertEqual(os.listdir(self.logs), [], "nada criado sem ambiente")

    def test_stdin_nulo(self):
        ex = self.start("cat; echo fim")
        self.assertEqual(self.until_exit(ex), 0)
        self.assertEqual(_read(ex.log_path), "fim\n")
        self.stop(ex)


class TestStop(_Base):

    def test_neto_morre_com_o_principal_ja_terminado(self):
        grandchild = os.path.join(self.root, "neto.pid")
        ex = self.start("sleep 300 & echo $! > %s" % grandchild)
        self.assertEqual(self.until_exit(ex), 0)
        pid_grandchild = int(_read(grandchild).strip())
        self.assertTrue(_alive(pid_grandchild))
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.stop(ex)
        self.assertIn("NETOS_ENCERRADOS", logs.output[0])
        self.assertTrue(_wait(lambda: not _alive(pid_grandchild)))

    def test_neto_morre_com_o_principal_vivo(self):
        grandchild = os.path.join(self.root, "neto.pid")
        ex = self.start("sleep 300 & echo $! > %s; sleep 300" % grandchild)
        self.assertTrue(_wait(lambda: _read(grandchild).strip().isdigit()))
        pid_grandchild = int(_read(grandchild).strip())
        self.stop(ex)
        self.assertFalse(_alive(ex.pid))
        self.assertTrue(_wait(lambda: not _alive(pid_grandchild)))
        self.assertEqual(executor.check(ex), -signal.SIGTERM)

    def test_grupo_que_ignora_sigterm_morre_dentro_de_grace_mais_1(self):
        ready = os.path.join(self.root, "pronto")
        ex = self.start("trap '' TERM; touch %s; sleep 300 & sleep 300" % ready)
        self.assertTrue(_wait(lambda: os.path.exists(ready)))
        duration = self.stop(ex, grace_s=1, deadline=5)
        self.assertLess(duration, 2.0)
        self.assertEqual(ex.phase, executor.PHASE_END)
        self.assertEqual(executor.check(ex), -signal.SIGKILL)

    def test_timeout_pelo_laco(self):
        ex = self.start("sleep 300")
        limit = time.monotonic() + 0.3
        # Laco do daemon: verificar a cada volta; passou do tempo, pede o encerramento.
        while executor.check(ex) is None and ex.phase is None:
            if time.monotonic() >= limit:
                executor.request_stop(ex, time.monotonic(), grace_s=1)
            time.sleep(0.02)
        self.assertTrue(_wait(lambda: executor.advance_stop(ex, time.monotonic())))
        self.assertEqual(executor.check(ex), -signal.SIGTERM)

    def test_avancar_sem_pedido(self):
        ex = self.start("sleep 300")
        with self.assertRaises(RuntimeError):
            executor.advance_stop(ex, time.monotonic())

    def test_sem_identidade_nao_recebe_sinal_e_termina_a_maquina(self):
        # Revisao F8.0-F8.2 (A2): ORFAO_SEM_IDENTIDADE nao fica preso em KILL; a pasta e preservada.
        ex = self.start("sleep 300", ticket_id=40)
        ex.process.no_identity = True
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            executor.request_stop(ex, time.monotonic(), grace_s=0)
        self.assertIn("ORFAO_SEM_IDENTIDADE", logs.output[0])
        self.assertTrue(ex.no_identity)
        self.assertTrue(executor.advance_stop(ex, time.monotonic() + 100))
        self.assertTrue(_alive(ex.pid), "nenhum sinal enviado")
        with self.assertRaises(RuntimeError):
            executor.clean(ex)
        self.assertTrue(os.path.isdir(ex.work_dir_ticket), "pasta preservada (CR-008, R-26)")
        ex.process.no_identity = False
        ex.phase = None

    def test_grupo_que_nao_morre_gera_erro_uma_vez(self):
        # Revisao F8.0-F8.2 (M3): grupo vivo depois do SIGKILL e de mais um prazo.
        ex = self.start("sleep 300", ticket_id=41)
        with mock.patch.object(os_platform, "group_alive", return_value=True), \
                mock.patch.object(os_platform, "signal_group", return_value=True):
            executor.request_stop(ex, 0.0, grace_s=2)
            self.assertFalse(executor.advance_stop(ex, 2.0))
            self.assertEqual(ex.phase, executor.PHASE_KILL)
            self.assertFalse(executor.advance_stop(ex, 3.0))
            self.assertFalse(ex.stuck)
            with self.assertLogs("sss_scheduler", "ERROR") as logs:
                self.assertFalse(executor.advance_stop(ex, 4.0))
                self.assertFalse(executor.advance_stop(ex, 9.0))
        self.assertEqual(len(logs.output), 1)
        self.assertIn("GRUPO_NAO_ENCERRA", logs.output[0])
        self.assertTrue(ex.stuck)
        ex.phase = None

    def test_traduzir_retorno(self):
        self.assertEqual(executor.translate_return(0, "LINUX"), ("SUCCESS", "EXIT_OK", 0))
        self.assertEqual(executor.translate_return(3, "LINUX"), ("FAILED", "EXIT_ERROR", 3))
        self.assertEqual(executor.translate_return(-9, "UNIX"), ("FAILED", "KILLED_SIGNAL", 137))
        self.assertEqual(executor.translate_return(-15, "LINUX"), ("FAILED", "KILLED_SIGNAL", 143))
        with self.assertRaises(ValueError):
            executor.translate_return(0, "WINDOWS")


class TestLocalState(_Base):

    def test_marcadores_spawn_proc_result(self):
        original = os_platform.start_process
        seen = {}

        def _confere(spec, log_fd, user):
            wd = os.path.join(self.work, "ticket_3")
            seen["spawn"] = os_platform.read_state(os.path.join(wd, executor.SPAWN))
            seen["proc"] = os.path.exists(os.path.join(wd, executor.PROC))
            seen["spec"] = spec
            return original(spec, log_fd, user)

        with mock.patch.object(os_platform, "start_process", side_effect=_confere):
            ex = self.start("sleep 300", ticket_id=3)
        self.assertEqual((seen["spawn"]["ticket_id"], seen["spawn"]["exec_user"]), (3, None))
        self.assertIn("monotonic", seen["spawn"])
        self.assertFalse(seen["proc"], ".sss_proc so depois do Popen")
        self.assertEqual(seen["spec"]["cwd"], os.path.join(self.work, "ticket_3", "exec"))
        proc = os_platform.read_state(os.path.join(ex.work_dir_ticket, executor.PROC))
        self.assertEqual(proc, {"ticket_id": 3, "pid": ex.pid, "pgid": ex.pid, "process_start": ex.identity,
                                "exec_user": None})
        self.assertIsNotNone(ex.identity)
        self.stop(ex)
        self.assertFalse(os.path.exists(os.path.join(ex.work_dir_ticket, executor.RESULT)))
        executor.record_result(ex, "FAILED", "TIMEOUT", -3)
        self.assertEqual(os_platform.read_state(os.path.join(ex.work_dir_ticket, executor.RESULT)),
                         {"ticket_id": 3, "status": "FAILED", "status_reason": "TIMEOUT", "return_code": -3})
        executor.clean(ex)
        self.assertFalse(os.path.exists(ex.work_dir_ticket))

    def test_diretorio_com_marcador_e_preservado(self):
        wd = os.path.join(self.work, "ticket_5")
        for marker in executor.MARKERS:
            os.makedirs(wd, exist_ok=True)
            with open(os.path.join(wd, marker), "w") as f:
                f.write("{}")
            for startup in (False, True):
                with self.assertRaises(executor.PreservedDirectory):
                    executor.prepare_directory(self.work, 5, startup_concluido=startup)
            self.assertTrue(os.path.exists(os.path.join(wd, marker)), "rastro nunca apagado")
            os.unlink(os.path.join(wd, marker))

    def test_diretorio_sem_marcador_so_apos_startup(self):
        wd = os.path.join(self.work, "ticket_6")
        os.makedirs(os.path.join(wd, "exec"))
        with open(os.path.join(wd, "exec", "velho.txt"), "w") as f:
            f.write("x")
        with self.assertRaises(executor.PreservedDirectory):
            executor.prepare_directory(self.work, 6)
        self.assertTrue(os.path.exists(os.path.join(wd, "exec", "velho.txt")))
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(executor.prepare_directory(self.work, 6, startup_concluido=True), wd)
        self.assertEqual(sorted(os.listdir(wd)), ["tmp"])
        self.assertEqual(os.stat(wd).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(os.path.join(wd, "tmp")).st_mode & 0o777, 0o700)

    def test_diretorio_que_e_link_e_preservado(self):
        outside = os.path.join(self.root, "fora")
        os.mkdir(outside)
        os.symlink(outside, os.path.join(self.work, "ticket_8"))
        with self.assertRaises(executor.PreservedDirectory):
            executor.prepare_directory(self.work, 8, startup_concluido=True)
        self.assertTrue(os.path.isdir(outside))

    def test_limpar_com_grupo_vivo_recusa(self):
        ex = self.start("sleep 300", ticket_id=4)
        with self.assertRaises(RuntimeError):
            executor.clean(ex)
        self.assertTrue(os.path.isdir(ex.work_dir_ticket))
        self.stop(ex)
        executor.clean(ex)
        self.assertFalse(os.path.exists(ex.work_dir_ticket))

    def test_limpar_com_usuario_chama_o_helper(self):
        wd = executor.prepare_directory(self.work, 11)
        ex = executor.Execution(11, wd, "sssprd", "/srv/exec/sssprd", None)
        with mock.patch.object(os_platform, "clean_script_dir") as helper:
            executor.clean(ex)
        helper.assert_called_once_with("/srv/exec/sssprd", 11, "sssprd")
        self.assertFalse(os.path.exists(wd))


class TestSpawnFailures(_Base):

    def test_falha_no_proc_depois_do_popen_real(self):
        grandchild = os.path.join(self.root, "neto.pid")
        original = os_platform.write_state

        def _grava(path, data):
            if path.endswith(executor.PROC):
                raise OSError(28, "No space left on device")
            return original(path, data)

        with mock.patch.object(os_platform, "write_state", side_effect=_grava), \
                self.assertLogs("sss_scheduler", "ERROR"):
            ex = self.start("sleep 300 & echo $! > %s; sleep 300" % grandchild, ticket_id=7)
        self.assertTrue(ex.failed_after_spawn)
        self.assertEqual(ex.spawn_error_info, "OSError")
        self.assertIn(ex.phase, (executor.PHASE_TERM, executor.PHASE_END), "encerramento ja iniciado")
        self.assertFalse(os.path.exists(os.path.join(ex.work_dir_ticket, executor.PROC)))
        # Acompanhada no mapa local ate o grupo acabar (SIGKILL quando o prazo vence).
        self.assertTrue(_wait(lambda: executor.advance_stop(ex, time.monotonic() + 60)))
        self.assertFalse(_alive(ex.pid))
        if _read(grandchild).strip().isdigit():
            self.assertTrue(_wait(lambda: not _alive(int(_read(grandchild).strip()))))
        self.assertIn("[SSS] falha ao iniciar: OSError (agente srv-01)", _read(ex.log_path))

    def test_falha_antes_do_spawn_fecha_e_renomeia_o_log(self):
        # Revisao F8.0-F8.2 (M2): falha entre open_log e iniciar (ex.: env_builder).
        fd, partial = executor.open_log(self.logs, "DEV", "Teste Script", STARTED_AT, 42)
        with self.assertLogs("sss_scheduler", "ERROR"):
            ex = executor.failure_before_spawn(fd, 42, ValueError("x"), "SSS-srv-01-42")
        self.assertEqual(ex.spawn_error_info, "ValueError")
        self.assertNotIn(fd, executor._open_logs)
        with self.assertRaises(OSError):
            os.fstat(fd)
        self.assertFalse(os.path.exists(partial))
        self.assertEqual(_read(os.path.join(self.dir_log(), "ticket_42_0.log")),
                         "[SSS] falha ao iniciar: ValueError (agente srv-01)\n")

    def test_excecao_que_nao_e_oserror_vira_spawn_error(self):
        error = UnicodeEncodeError("utf-8", "x", 0, 1, "surrogates not allowed")
        with mock.patch.object(os_platform, "start_process", side_effect=error), \
                self.assertLogs("sss_scheduler", "ERROR"):
            ex = self.start("echo nunca", ticket_id=12, label="SSS-srv-linux-prod-01-12")
        self.assertTrue(ex.spawn_error)
        self.assertFalse(ex.failed_after_spawn)
        self.assertIsNone(ex.process)
        self.assertEqual(ex.spawn_error_info, "UnicodeEncodeError")
        final = os.path.join(self.dir_log(), "ticket_12_0.log")
        self.assertEqual(ex.log_path, final)
        self.assertEqual(_read(final), "[SSS] falha ao iniciar: UnicodeEncodeError (agente srv-linux-prod-01)\n")
        self.assertFalse(os.path.exists(os.path.join(self.dir_log(), "ticket_12.log.parcial")))

    def test_falha_no_marcador_de_spawn_nao_inicia(self):
        with mock.patch.object(os_platform, "write_state", side_effect=PermissionError(13, "negado")), \
                mock.patch.object(os_platform, "start_process") as starts, \
                self.assertLogs("sss_scheduler", "ERROR"):
            ex = self.start("echo nunca", ticket_id=13)
        starts.assert_not_called()
        self.assertEqual(ex.spawn_error_info, "PermissionError")
        self.assertTrue(ex.log_path.endswith("ticket_13_0.log"))

    def test_falha_apos_popen_do_helper(self):
        leader = subprocess.Popen(["sleep", "300"], start_new_session=True)
        self.extras.append(leader)
        process = os_platform.Process(leader.pid, os_platform.process_identity(leader.pid), popen=leader)
        failure = os_platform.FailureAfterSpawn(process, BrokenPipeError(32, "Broken pipe"))
        with mock.patch.object(os_platform, "start_process", side_effect=failure), \
                self.assertLogs("sss_scheduler", "ERROR"):
            ex = self.start("ignorado", ticket_id=14)
        self.execs.remove(ex)
        self.assertTrue(ex.failed_after_spawn)
        self.assertEqual((ex.pid, ex.spawn_error_info, ex.phase), (leader.pid, "BrokenPipeError", executor.PHASE_TERM))
        self.assertEqual(leader.wait(5), -signal.SIGTERM)

    def test_especificacao_do_helper_com_usuario_de_execucao(self):
        captured = {}

        def _captura(spec, log_fd, user):
            captured.update(spec=spec, user=user)
            raise RuntimeError("sem sudo no teste")

        wd = executor.prepare_directory(self.work, 15)
        fd, _ = executor.open_log(self.logs, "DEV", "Teste Script", STARTED_AT, 15)
        with mock.patch.object(os_platform, "start_process", side_effect=_captura), \
                self.assertLogs("sss_scheduler", "ERROR"):
            ex = executor.start(15, ["/usr/bin/python3", "-I", "/opt/s.py"], fd, {"PATH": "/usr/bin:/bin"}, wd,
                                  "sssprd", "/srv/exec", os_platform.DEFAULT_RLIMITS, "SSS-srv-01-15")
        self.assertEqual(captured["user"], "sssprd")
        self.assertEqual(captured["spec"], {
            "ticket_id": 15, "argv": ["/usr/bin/python3", "-I", "/opt/s.py"], "env": {"PATH": "/usr/bin:/bin"},
            "rlimits": {"RLIMIT_CORE": [0, 0], "RLIMIT_NOFILE": [1024, 1024]}, "base_dir": "/srv/exec/sssprd"})
        self.assertFalse(os.path.exists(os.path.join(wd, "exec")), "fora de DEV o cwd e criado pelo helper")
        self.assertEqual((ex.base_dir, ex.spawn_error_info), ("/srv/exec/sssprd", "RuntimeError"))


    def test_cr014_entrada_na_especificacao_e_criada_em_dev(self):
        self.assertEqual(executor.build_spec(15, ["/bin/true"], {}, {}, "/srv/exec/sssprd",
                                                input_value=("/srv/sss/input/producao", "carga"))["input"],
                         {"base": "/srv/sss/input/producao", "relativo": "carga"})
        self.assertNotIn("input", executor.build_spec(15, ["/bin/true"], {}, {}, "/srv/exec/sssprd"))
        base = os.path.join(self.root, "input", "dev")
        wd = executor.prepare_directory(self.work, 16)
        fd, _ = executor.open_log(self.logs, "DEV", "Teste Script", STARTED_AT, 16)
        with mock.patch.object(os_platform, "start_process", side_effect=RuntimeError("parar")), \
                self.assertLogs("sss_scheduler", "ERROR"):
            executor.start(16, ["/bin/true"], fd, {}, wd, None, None, os_platform.DEFAULT_RLIMITS, "SSS-srv-01-16",
                             input_value=(base, "teste_script"))
        self.assertEqual(os.stat(os.path.join(base, "teste_script")).st_mode & 0o777, 0o700)

    def test_cr019_trabalho_na_especificacao_e_criado_em_dev(self):
        rel = "carga/2026/10/20/03/00/ticket_15"
        self.assertEqual(executor.build_spec(15, ["/bin/true"], {}, {}, "/srv/exec/sssprd",
                                                work=("/srv/sss/work/producao", rel))["work"],
                         {"base": "/srv/sss/work/producao", "relativo": rel})
        self.assertNotIn("work", executor.build_spec(15, ["/bin/true"], {}, {}, "/srv/exec/sssprd"))
        base = os.path.join(self.root, "work_scripts", "dev")
        rel = "teste_script/2026/10/20/03/00/ticket_17"
        wd = executor.prepare_directory(self.work, 17)
        fd, _ = executor.open_log(self.logs, "DEV", "Teste Script", STARTED_AT, 17)
        with mock.patch.object(os_platform, "start_process", side_effect=RuntimeError("parar")), \
                self.assertLogs("sss_scheduler", "ERROR"):
            executor.start(17, ["/bin/true"], fd, {}, wd, None, None, os_platform.DEFAULT_RLIMITS, "SSS-srv-01-17",
                             work=(base, rel))
        self.assertEqual(os.stat(os.path.join(base, rel)).st_mode & 0o777, 0o700)


class TestSnapshotV4(_Base):

    def setUp(self):
        _Base.setUp(self)
        self.base = os.path.join(self.root, "scripts")
        os.makedirs(os.path.join(self.base, "faturamento"))
        self.script = os.path.join(self.base, "faturamento", "carga.py")
        with open(self.script, "w") as f:
            f.write("import json, os, sys\n"
                    "json.dump([os.getcwd(), os.environ.get('SSS_SCRIPT_DIR'), os.environ.get('HOME'),\n"
                    "           sys.flags.isolated, sys.argv[1:],\n"
                    "           dict((k, v) for k, v in os.environ.items() if k.startswith('SSS_'))],\n"
                    "          open('saida.json', 'w'))\n")
        os.chmod(self.script, 0o444)
        os.chmod(os.path.join(self.base, "faturamento"), 0o555)
        os.chmod(self.base, 0o555)

    def test_argv_do_snapshot_e_sss_script_dir(self):
        snap_js = json.dumps({"version": 5, "script_id": 12, "script_name": "Carga Faturas", "interpreter": "PYTHON3",
                              "path_file": self.script, "param_type": "NAMED", "args": ["--data", "2026-10-13"],
                              "answers": {}, "sensitive": [], "compiled_at": "2026-10-13 10:47:00"},
                             ensure_ascii=False, sort_keys=True)
        snap, argv, script_real = pc.validate_snapshot(snap_js, _CfgSnap({"PYTHON3": sys.executable}))
        self.assertEqual(argv, [sys.executable, "-I", script_real, "--data", "2026-10-13"])
        wd = executor.prepare_directory(self.work, 21)
        cfg = _Cfg(_AgentStub("srv-01", "C.UTF-8", (), (), None))
        fd, partial = executor.open_log(self.logs, "DEV", snap["script_name"], STARTED_AT, 21, snap["script_id"])
        ticket = {"id": 21, "environment": "DEV", "schedule_id": 5, "parent_ticket_id": None, "priority": 3,
                  "started_at": STARTED_AT, "scheduled_at": STARTED_AT}
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = env_builder.build(cfg, Secrets("x" * 8, None, {}), ticket,
                                        {"name": "DEV", "connection": None, "description": "Desenvolvimento"},
                                        script_real, wd, {}, os_platform.NAME, snapshot=snap,
                                        schedule={"name": "Diario DEV", "recurrence_type": "DAILY"},
                                        log_path=partial, timeout_sec=60, hostname="host-dev", version="t")
        ex = executor.start(21, argv, fd, env, wd, None, None, os_platform.DEFAULT_RLIMITS, "SSS-srv-01-21")
        self.execs.append(ex)
        self.assertEqual(self.until_exit(ex), 0, _read(ex.log_path))
        cwd = os.path.join(wd, "exec")
        with open(os.path.join(cwd, "saida.json")) as f:
            output = json.load(f)
        self.assertEqual(output[:5], [cwd, os.path.dirname(script_real), cwd, 1, ["--data", "2026-10-13"]])
        # CR-010: o filho le os dados da execucao em SSS_*.
        sss = output[5]
        self.assertEqual((sss["SSS_TICKET_ID"], sss["SSS_EXECUTION_TYPE"], sss["SSS_RECURRENCE"]),
                         ("21", "AGENDADA", "DAILY"))
        self.assertEqual((sss["SSS_ENVIRONMENT"], sss["SSS_ENVIRONMENT_DESCRIPTION"]), ("DEV", "Desenvolvimento"))
        self.assertEqual(sss["SSS_STARTED_AT"], "2026-10-16 14:05:33")
        self.assertEqual(sss["SSS_SCRIPT_FILE"], script_real)
        self.assertEqual(os.path.join(sss["SSS_LOG_DIR"], sss["SSS_LOG_FILE"]), partial)
        self.assertEqual(os.path.dirname(ex.log_path), sss["SSS_LOG_DIR"])
        self.assertTrue(ex.log_path.startswith(os.path.join(self.logs, "dev", "carga_faturas", "2026")))
        self.stop(ex)


class TestSource(unittest.TestCase):

    def test_executor_sem_espera_pipe_shell_ou_environ(self):
        with open(executor.__file__, encoding="utf-8") as f:
            source = f.read()
        for forbidden in ("time.sleep", ".wait(", "PIPE", "shell=" + "True", "os.environ", "os.killpg", "subprocess",
                         "def encerrar("):
            self.assertFalse(forbidden in source, forbidden)


if __name__ == "__main__":
    unittest.main()
