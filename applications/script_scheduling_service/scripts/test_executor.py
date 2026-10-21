# -*- coding: utf-8 -*-
"""Testes do executor (README §8.4, §8.7; AGENTS §3.2 e §7.4; CR-007 R-01 a R-04, R-17; CR-008 R-01, R-26, R-36).

Spawn real (POSIX, DEV sem usuario de execucao) em diretorio temporario. As esperas deste arquivo sao so do
harness de teste (_esperar): o executor nunca espera. Todo processo e encerrado no tearDown pela mesma
maquina de estados (pedir_encerramento/avancar_encerramento).
"""
import _testenv  # noqa: F401

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
import params_compiler as pc
import path_guard
import plataforma
from sss_config import Segredos

AGENTE_FALSO = 2 ** 31 - 3
STARTED_AT = datetime.datetime(2026, 10, 16, 14, 5, 33)
SH = "/bin/sh"

_Agente = collections.namedtuple("_Agente", "agent_id child_locale env_passthrough usuarios_execucao exec_work_dir")
_Cfg = collections.namedtuple("_Cfg", "agent")
_CfgSnap = collections.namedtuple("_CfgSnap", "interpretadores")


def _esperar(condicao, prazo=10.0):
    """So do harness de teste."""
    limite = time.monotonic() + prazo
    while time.monotonic() < limite:
        if condicao():
            return True
        time.sleep(0.02)
    return condicao()


def _vivo(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            conteudo = f.read()
    except OSError:
        return False
    return conteudo[conteudo.rindex(")") + 2:].split()[0] != "Z"


def _ler(caminho):
    try:
        with open(caminho) as f:
            return f.read()
    except OSError:
        return ""


@unittest.skipIf(os.geteuid() == 0, "o agente nunca roda como root")
class _Base(unittest.TestCase):

    def setUp(self):
        self.raiz = os.path.realpath(tempfile.mkdtemp(prefix="sss_exec_"))
        self.work = os.path.join(self.raiz, "work")
        self.logs = os.path.join(self.raiz, "logs")
        os.mkdir(self.work, 0o700)
        os.mkdir(self.logs, 0o750)
        self.execs = []
        self.extras = []

    def tearDown(self):
        for ex in self.execs:
            if ex.processo is None:
                continue
            ex.fase = None if ex.fase == executor.FASE_FIM else ex.fase
            executor.pedir_encerramento(ex, time.monotonic(), grace_s=0)
            _esperar(lambda: executor.avancar_encerramento(ex, time.monotonic()), 5)
            if ex.processo.popen is not None:
                ex.processo.popen.wait(5)
        for p in self.extras:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            p.wait()
        for atual, dirs, _arqs in os.walk(self.raiz):
            for d in dirs:
                os.chmod(os.path.join(atual, d), 0o700)
        shutil.rmtree(self.raiz, ignore_errors=True)

    def iniciar(self, comando, ticket_id=1, argv=None, env=None, rotulo=None):
        wd = executor.preparar_diretorio(self.work, ticket_id)
        fd, _parcial = executor.abrir_log(self.logs, "DEV", "Teste Script", STARTED_AT, ticket_id)
        ex = executor.iniciar(ticket_id, argv or [SH, "-c", comando], fd, env or {"PATH": "/usr/bin:/bin"}, wd,
                              None, None, plataforma.RLIMITS_PADRAO, rotulo or "SSS-srv-01-%d" % ticket_id)
        self.execs.append(ex)
        return ex

    def dir_log(self):
        return os.path.join(self.logs, "dev", "teste_script", "2026", "10", "16", "14", "05")

    def ate_sair(self, ex, prazo=10):
        self.assertTrue(_esperar(lambda: executor.verificar(ex) is not None, prazo), "o script nao terminou")
        return ex.returncode

    def encerrar(self, ex, grace_s=1, prazo=10):
        """Ciclo do laco do daemon: cada chamada volta logo; o harness so repete ate o grupo acabar."""
        inicio = time.monotonic()
        executor.pedir_encerramento(ex, time.monotonic(), grace_s=grace_s)
        self.assertLess(time.monotonic() - inicio, 0.5)

        def _passo():
            t = time.monotonic()
            fim = executor.avancar_encerramento(ex, time.monotonic())
            self.assertLess(time.monotonic() - t, 0.5, "avancar_encerramento nao pode bloquear")
            return fim
        self.assertTrue(_esperar(_passo, prazo), "o grupo nao acabou")
        return time.monotonic() - inicio


class TestLogESaida(_Base):

    def test_log_por_minuto_rename_e_permissoes(self):
        antiga = os.umask(0o077)
        try:
            ex = self.iniciar("echo ola")
        finally:
            os.umask(antiga)
        self.assertEqual(self.ate_sair(ex), 0)
        final = os.path.join(self.dir_log(), "ticket_1_%d.log" % ex.pid)
        self.assertEqual(ex.caminho_log, final)
        self.assertEqual(_ler(final), "ola\n")
        self.assertFalse(os.path.exists(os.path.join(self.dir_log(), "ticket_1.log.parcial")), "rename atomico")
        self.assertEqual(os.stat(final).st_mode & 0o777, 0o600)
        pasta = self.logs
        for nivel in ("dev", "teste_script", "2026", "10", "16", "14", "05"):
            pasta = os.path.join(pasta, nivel)
            self.assertEqual(os.stat(pasta).st_mode & 0o777, 0o750, pasta)
        self.encerrar(ex)

    def test_log_com_o_excl(self):
        fd, caminho = executor.abrir_log(self.logs, "DEV", "Teste Script", STARTED_AT, 9)
        try:
            with self.assertRaises(FileExistsError):
                executor.abrir_log(self.logs, "DEV", "Teste Script", STARTED_AT, 9)
        finally:
            executor._logs_abertos.pop(fd, None)
            os.close(fd)
        self.assertTrue(caminho.endswith("/ticket_9.log.parcial"))

    def test_saida_de_2_mb_sem_travar(self):
        ex = self.iniciar("head -c 2097152 /dev/zero | tr '\\000' a")
        self.assertEqual(self.ate_sair(ex, 20), 0)
        self.assertEqual(os.path.getsize(ex.caminho_log), 2097152)
        self.encerrar(ex)

    def test_abrir_log_exige_ambiente(self):
        for vazio in (None, "", "INTERNO"):
            with self.assertRaises(ValueError):
                executor.abrir_log(self.logs, vazio, "Teste Script", STARTED_AT, 30)
        self.assertEqual(os.listdir(self.logs), [], "nada criado sem ambiente")

    def test_stdin_nulo(self):
        ex = self.iniciar("cat; echo fim")
        self.assertEqual(self.ate_sair(ex), 0)
        self.assertEqual(_ler(ex.caminho_log), "fim\n")
        self.encerrar(ex)


class TestEncerramento(_Base):

    def test_neto_morre_com_o_principal_ja_terminado(self):
        neto = os.path.join(self.raiz, "neto.pid")
        ex = self.iniciar("sleep 300 & echo $! > %s" % neto)
        self.assertEqual(self.ate_sair(ex), 0)
        pid_neto = int(_ler(neto).strip())
        self.assertTrue(_vivo(pid_neto))
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.encerrar(ex)
        self.assertIn("NETOS_ENCERRADOS", logs.output[0])
        self.assertTrue(_esperar(lambda: not _vivo(pid_neto)))

    def test_neto_morre_com_o_principal_vivo(self):
        neto = os.path.join(self.raiz, "neto.pid")
        ex = self.iniciar("sleep 300 & echo $! > %s; sleep 300" % neto)
        self.assertTrue(_esperar(lambda: _ler(neto).strip().isdigit()))
        pid_neto = int(_ler(neto).strip())
        self.encerrar(ex)
        self.assertFalse(_vivo(ex.pid))
        self.assertTrue(_esperar(lambda: not _vivo(pid_neto)))
        self.assertEqual(executor.verificar(ex), -signal.SIGTERM)

    def test_grupo_que_ignora_sigterm_morre_dentro_de_grace_mais_1(self):
        pronto = os.path.join(self.raiz, "pronto")
        ex = self.iniciar("trap '' TERM; touch %s; sleep 300 & sleep 300" % pronto)
        self.assertTrue(_esperar(lambda: os.path.exists(pronto)))
        duracao = self.encerrar(ex, grace_s=1, prazo=5)
        self.assertLess(duracao, 2.0)
        self.assertEqual(ex.fase, executor.FASE_FIM)
        self.assertEqual(executor.verificar(ex), -signal.SIGKILL)

    def test_timeout_pelo_laco(self):
        ex = self.iniciar("sleep 300")
        limite = time.monotonic() + 0.3
        # Laco do daemon: verificar a cada volta; passou do tempo, pede o encerramento.
        while executor.verificar(ex) is None and ex.fase is None:
            if time.monotonic() >= limite:
                executor.pedir_encerramento(ex, time.monotonic(), grace_s=1)
            time.sleep(0.02)
        self.assertTrue(_esperar(lambda: executor.avancar_encerramento(ex, time.monotonic())))
        self.assertEqual(executor.verificar(ex), -signal.SIGTERM)

    def test_avancar_sem_pedido(self):
        ex = self.iniciar("sleep 300")
        with self.assertRaises(RuntimeError):
            executor.avancar_encerramento(ex, time.monotonic())

    def test_sem_identidade_nao_recebe_sinal_e_termina_a_maquina(self):
        # Revisao F8.0-F8.2 (A2): ORFAO_SEM_IDENTIDADE nao fica preso em KILL; a pasta e preservada.
        ex = self.iniciar("sleep 300", ticket_id=40)
        ex.processo.sem_identidade = True
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            executor.pedir_encerramento(ex, time.monotonic(), grace_s=0)
        self.assertIn("ORFAO_SEM_IDENTIDADE", logs.output[0])
        self.assertTrue(ex.sem_identidade)
        self.assertTrue(executor.avancar_encerramento(ex, time.monotonic() + 100))
        self.assertTrue(_vivo(ex.pid), "nenhum sinal enviado")
        with self.assertRaises(RuntimeError):
            executor.limpar(ex)
        self.assertTrue(os.path.isdir(ex.work_dir_ticket), "pasta preservada (CR-008, R-26)")
        ex.processo.sem_identidade = False
        ex.fase = None

    def test_grupo_que_nao_morre_gera_erro_uma_vez(self):
        # Revisao F8.0-F8.2 (M3): grupo vivo depois do SIGKILL e de mais um prazo.
        ex = self.iniciar("sleep 300", ticket_id=41)
        with mock.patch.object(plataforma, "grupo_vivo", return_value=True), \
                mock.patch.object(plataforma, "sinalizar_grupo", return_value=True):
            executor.pedir_encerramento(ex, 0.0, grace_s=2)
            self.assertFalse(executor.avancar_encerramento(ex, 2.0))
            self.assertEqual(ex.fase, executor.FASE_KILL)
            self.assertFalse(executor.avancar_encerramento(ex, 3.0))
            self.assertFalse(ex.travado)
            with self.assertLogs("sss_scheduler", "ERROR") as logs:
                self.assertFalse(executor.avancar_encerramento(ex, 4.0))
                self.assertFalse(executor.avancar_encerramento(ex, 9.0))
        self.assertEqual(len(logs.output), 1)
        self.assertIn("GRUPO_NAO_ENCERRA", logs.output[0])
        self.assertTrue(ex.travado)
        ex.fase = None

    def test_traduzir_retorno(self):
        self.assertEqual(executor.traduzir_retorno(0, "LINUX"), ("SUCCESS", "EXIT_OK", 0))
        self.assertEqual(executor.traduzir_retorno(3, "LINUX"), ("FAILED", "EXIT_ERROR", 3))
        self.assertEqual(executor.traduzir_retorno(-9, "UNIX"), ("FAILED", "KILLED_SIGNAL", 137))
        self.assertEqual(executor.traduzir_retorno(-15, "LINUX"), ("FAILED", "KILLED_SIGNAL", 143))
        with self.assertRaises(ValueError):
            executor.traduzir_retorno(0, "WINDOWS")


class TestEstadoLocal(_Base):

    def test_marcadores_spawn_proc_result(self):
        original = plataforma.iniciar_processo
        vistos = {}

        def _confere(spec, log_fd, usuario):
            wd = os.path.join(self.work, "ticket_3")
            vistos["spawn"] = plataforma.ler_estado(os.path.join(wd, executor.SPAWN))
            vistos["proc"] = os.path.exists(os.path.join(wd, executor.PROC))
            vistos["spec"] = spec
            return original(spec, log_fd, usuario)

        with mock.patch.object(plataforma, "iniciar_processo", side_effect=_confere):
            ex = self.iniciar("sleep 300", ticket_id=3)
        self.assertEqual((vistos["spawn"]["ticket_id"], vistos["spawn"]["usuario_execucao"]), (3, None))
        self.assertIn("monotonico", vistos["spawn"])
        self.assertFalse(vistos["proc"], ".sss_proc so depois do Popen")
        self.assertEqual(vistos["spec"]["cwd"], os.path.join(self.work, "ticket_3", "exec"))
        proc = plataforma.ler_estado(os.path.join(ex.work_dir_ticket, executor.PROC))
        self.assertEqual(proc, {"ticket_id": 3, "pid": ex.pid, "pgid": ex.pid, "process_start": ex.identidade,
                                "usuario_execucao": None})
        self.assertIsNotNone(ex.identidade)
        self.encerrar(ex)
        self.assertFalse(os.path.exists(os.path.join(ex.work_dir_ticket, executor.RESULT)))
        executor.registrar_resultado(ex, "FAILED", "TIMEOUT", -3)
        self.assertEqual(plataforma.ler_estado(os.path.join(ex.work_dir_ticket, executor.RESULT)),
                         {"ticket_id": 3, "status": "FAILED", "status_motivo": "TIMEOUT", "return_code": -3})
        executor.limpar(ex)
        self.assertFalse(os.path.exists(ex.work_dir_ticket))

    def test_diretorio_com_marcador_e_preservado(self):
        wd = os.path.join(self.work, "ticket_5")
        for marcador in executor.MARCADORES:
            os.makedirs(wd, exist_ok=True)
            with open(os.path.join(wd, marcador), "w") as f:
                f.write("{}")
            for startup in (False, True):
                with self.assertRaises(executor.DiretorioPreservado):
                    executor.preparar_diretorio(self.work, 5, startup_concluido=startup)
            self.assertTrue(os.path.exists(os.path.join(wd, marcador)), "rastro nunca apagado")
            os.unlink(os.path.join(wd, marcador))

    def test_diretorio_sem_marcador_so_apos_startup(self):
        wd = os.path.join(self.work, "ticket_6")
        os.makedirs(os.path.join(wd, "exec"))
        with open(os.path.join(wd, "exec", "velho.txt"), "w") as f:
            f.write("x")
        with self.assertRaises(executor.DiretorioPreservado):
            executor.preparar_diretorio(self.work, 6)
        self.assertTrue(os.path.exists(os.path.join(wd, "exec", "velho.txt")))
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(executor.preparar_diretorio(self.work, 6, startup_concluido=True), wd)
        self.assertEqual(sorted(os.listdir(wd)), ["tmp"])
        self.assertEqual(os.stat(wd).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(os.path.join(wd, "tmp")).st_mode & 0o777, 0o700)

    def test_diretorio_que_e_link_e_preservado(self):
        fora = os.path.join(self.raiz, "fora")
        os.mkdir(fora)
        os.symlink(fora, os.path.join(self.work, "ticket_8"))
        with self.assertRaises(executor.DiretorioPreservado):
            executor.preparar_diretorio(self.work, 8, startup_concluido=True)
        self.assertTrue(os.path.isdir(fora))

    def test_limpar_com_grupo_vivo_recusa(self):
        ex = self.iniciar("sleep 300", ticket_id=4)
        with self.assertRaises(RuntimeError):
            executor.limpar(ex)
        self.assertTrue(os.path.isdir(ex.work_dir_ticket))
        self.encerrar(ex)
        executor.limpar(ex)
        self.assertFalse(os.path.exists(ex.work_dir_ticket))

    def test_limpar_com_usuario_chama_o_helper(self):
        wd = executor.preparar_diretorio(self.work, 11)
        ex = executor.Execucao(11, wd, "sssprd", "/srv/exec/sssprd", None)
        with mock.patch.object(plataforma, "limpar_dir_script") as helper:
            executor.limpar(ex)
        helper.assert_called_once_with("/srv/exec/sssprd", 11, "sssprd")
        self.assertFalse(os.path.exists(wd))


class TestFalhasDeSpawn(_Base):

    def test_falha_no_proc_depois_do_popen_real(self):
        neto = os.path.join(self.raiz, "neto.pid")
        original = plataforma.gravar_estado

        def _grava(caminho, dados):
            if caminho.endswith(executor.PROC):
                raise OSError(28, "No space left on device")
            return original(caminho, dados)

        with mock.patch.object(plataforma, "gravar_estado", side_effect=_grava), \
                self.assertLogs("sss_scheduler", "ERROR"):
            ex = self.iniciar("sleep 300 & echo $! > %s; sleep 300" % neto, ticket_id=7)
        self.assertTrue(ex.falhou_apos_spawn)
        self.assertEqual(ex.erro_spawn, "OSError")
        self.assertIn(ex.fase, (executor.FASE_TERM, executor.FASE_FIM), "encerramento ja iniciado")
        self.assertFalse(os.path.exists(os.path.join(ex.work_dir_ticket, executor.PROC)))
        # Acompanhada no mapa local ate o grupo acabar (SIGKILL quando o prazo vence).
        self.assertTrue(_esperar(lambda: executor.avancar_encerramento(ex, time.monotonic() + 60)))
        self.assertFalse(_vivo(ex.pid))
        if _ler(neto).strip().isdigit():
            self.assertTrue(_esperar(lambda: not _vivo(int(_ler(neto).strip()))))
        self.assertIn("[SSS] falha ao iniciar: OSError (agente srv-01)", _ler(ex.caminho_log))

    def test_falha_antes_do_spawn_fecha_e_renomeia_o_log(self):
        # Revisao F8.0-F8.2 (M2): falha entre abrir_log e iniciar (ex.: env_builder).
        fd, parcial = executor.abrir_log(self.logs, "DEV", "Teste Script", STARTED_AT, 42)
        with self.assertLogs("sss_scheduler", "ERROR"):
            ex = executor.falha_antes_do_spawn(fd, 42, ValueError("x"), "SSS-srv-01-42")
        self.assertEqual(ex.erro_spawn, "ValueError")
        self.assertNotIn(fd, executor._logs_abertos)
        with self.assertRaises(OSError):
            os.fstat(fd)
        self.assertFalse(os.path.exists(parcial))
        self.assertEqual(_ler(os.path.join(self.dir_log(), "ticket_42_0.log")),
                         "[SSS] falha ao iniciar: ValueError (agente srv-01)\n")

    def test_excecao_que_nao_e_oserror_vira_spawn_error(self):
        erro = UnicodeEncodeError("utf-8", "x", 0, 1, "surrogates not allowed")
        with mock.patch.object(plataforma, "iniciar_processo", side_effect=erro), \
                self.assertLogs("sss_scheduler", "ERROR"):
            ex = self.iniciar("echo nunca", ticket_id=12, rotulo="SSS-srv-linux-prod-01-12")
        self.assertTrue(ex.spawn_error)
        self.assertFalse(ex.falhou_apos_spawn)
        self.assertIsNone(ex.processo)
        self.assertEqual(ex.erro_spawn, "UnicodeEncodeError")
        final = os.path.join(self.dir_log(), "ticket_12_0.log")
        self.assertEqual(ex.caminho_log, final)
        self.assertEqual(_ler(final), "[SSS] falha ao iniciar: UnicodeEncodeError (agente srv-linux-prod-01)\n")
        self.assertFalse(os.path.exists(os.path.join(self.dir_log(), "ticket_12.log.parcial")))

    def test_falha_no_marcador_de_spawn_nao_inicia(self):
        with mock.patch.object(plataforma, "gravar_estado", side_effect=PermissionError(13, "negado")), \
                mock.patch.object(plataforma, "iniciar_processo") as inicia, \
                self.assertLogs("sss_scheduler", "ERROR"):
            ex = self.iniciar("echo nunca", ticket_id=13)
        inicia.assert_not_called()
        self.assertEqual(ex.erro_spawn, "PermissionError")
        self.assertTrue(ex.caminho_log.endswith("ticket_13_0.log"))

    def test_falha_apos_popen_do_helper(self):
        lider = subprocess.Popen(["sleep", "300"], start_new_session=True)
        self.extras.append(lider)
        processo = plataforma.Processo(lider.pid, plataforma.identidade_processo(lider.pid), popen=lider)
        falha = plataforma.FalhaAposSpawn(processo, BrokenPipeError(32, "Broken pipe"))
        with mock.patch.object(plataforma, "iniciar_processo", side_effect=falha), \
                self.assertLogs("sss_scheduler", "ERROR"):
            ex = self.iniciar("ignorado", ticket_id=14)
        self.execs.remove(ex)
        self.assertTrue(ex.falhou_apos_spawn)
        self.assertEqual((ex.pid, ex.erro_spawn, ex.fase), (lider.pid, "BrokenPipeError", executor.FASE_TERM))
        self.assertEqual(lider.wait(5), -signal.SIGTERM)

    def test_especificacao_do_helper_com_usuario_de_execucao(self):
        capturado = {}

        def _captura(spec, log_fd, usuario):
            capturado.update(spec=spec, usuario=usuario)
            raise RuntimeError("sem sudo no teste")

        wd = executor.preparar_diretorio(self.work, 15)
        fd, _ = executor.abrir_log(self.logs, "DEV", "Teste Script", STARTED_AT, 15)
        with mock.patch.object(plataforma, "iniciar_processo", side_effect=_captura), \
                self.assertLogs("sss_scheduler", "ERROR"):
            ex = executor.iniciar(15, ["/usr/bin/python3", "-I", "/opt/s.py"], fd, {"PATH": "/usr/bin:/bin"}, wd,
                                  "sssprd", "/srv/exec", plataforma.RLIMITS_PADRAO, "SSS-srv-01-15")
        self.assertEqual(capturado["usuario"], "sssprd")
        self.assertEqual(capturado["spec"], {
            "ticket_id": 15, "argv": ["/usr/bin/python3", "-I", "/opt/s.py"], "env": {"PATH": "/usr/bin:/bin"},
            "rlimits": {"RLIMIT_CORE": [0, 0], "RLIMIT_NOFILE": [1024, 1024]}, "pasta_base": "/srv/exec/sssprd"})
        self.assertFalse(os.path.exists(os.path.join(wd, "exec")), "fora de DEV o cwd e criado pelo helper")
        self.assertEqual((ex.pasta_base, ex.erro_spawn), ("/srv/exec/sssprd", "RuntimeError"))


    def test_cr014_entrada_na_especificacao_e_criada_em_dev(self):
        self.assertEqual(executor.especificacao(15, ["/bin/true"], {}, {}, "/srv/exec/sssprd",
                                                entrada=("/srv/sss/entrada/producao", "carga"))["entrada"],
                         {"base": "/srv/sss/entrada/producao", "relativo": "carga"})
        self.assertNotIn("entrada", executor.especificacao(15, ["/bin/true"], {}, {}, "/srv/exec/sssprd"))
        base = os.path.join(self.raiz, "entrada", "dev")
        wd = executor.preparar_diretorio(self.work, 16)
        fd, _ = executor.abrir_log(self.logs, "DEV", "Teste Script", STARTED_AT, 16)
        with mock.patch.object(plataforma, "iniciar_processo", side_effect=RuntimeError("parar")), \
                self.assertLogs("sss_scheduler", "ERROR"):
            executor.iniciar(16, ["/bin/true"], fd, {}, wd, None, None, plataforma.RLIMITS_PADRAO, "SSS-srv-01-16",
                             entrada=(base, "teste_script"))
        self.assertEqual(os.stat(os.path.join(base, "teste_script")).st_mode & 0o777, 0o700)


class TestSnapshotV4(_Base):

    def setUp(self):
        _Base.setUp(self)
        self.base = os.path.join(self.raiz, "scripts")
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
        snap_js = json.dumps({"versao": 4, "script_id": 12, "script_nome": "Carga Faturas", "interpretador": "PYTHON3",
                              "path_file": self.script, "tipo_param": "NOMEADO", "args": ["--data", "2026-10-13"],
                              "respostas": {}, "sensiveis": [], "compilado_em": "2026-10-13 10:47:00"},
                             ensure_ascii=False, sort_keys=True)
        snap, argv, script_real = pc.validar_snapshot(snap_js, _CfgSnap({"PYTHON3": sys.executable}))
        self.assertEqual(argv, [sys.executable, "-I", script_real, "--data", "2026-10-13"])
        wd = executor.preparar_diretorio(self.work, 21)
        cfg = _Cfg(_Agente("srv-01", "C.UTF-8", (), (), None))
        fd, parcial = executor.abrir_log(self.logs, "DEV", snap["script_nome"], STARTED_AT, 21, snap["script_id"])
        ticket = {"id": 21, "ambiente": "DEV", "agendamento_id": 5, "parent_ticket_id": None, "prioridade": 3,
                  "started_at": STARTED_AT, "scheduled_at": STARTED_AT}
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = env_builder.construir(cfg, Segredos("x" * 8, None, {}), ticket,
                                        {"nome": "DEV", "conexao": None, "descricao": "Desenvolvimento"},
                                        script_real, wd, {}, plataforma.NOME, snapshot=snap,
                                        agendamento={"nome": "Diario DEV", "tipo_recorrencia": "DIARIA"},
                                        caminho_log=parcial, timeout_seg=60, hostname="host-dev", versao="t")
        ex = executor.iniciar(21, argv, fd, env, wd, None, None, plataforma.RLIMITS_PADRAO, "SSS-srv-01-21")
        self.execs.append(ex)
        self.assertEqual(self.ate_sair(ex), 0, _ler(ex.caminho_log))
        cwd = os.path.join(wd, "exec")
        with open(os.path.join(cwd, "saida.json")) as f:
            saida = json.load(f)
        self.assertEqual(saida[:5], [cwd, os.path.dirname(script_real), cwd, 1, ["--data", "2026-10-13"]])
        # CR-010: o filho le os dados da execucao em SSS_*.
        sss = saida[5]
        self.assertEqual((sss["SSS_TICKET_ID"], sss["SSS_TIPO_EXECUCAO"], sss["SSS_RECORRENCIA"]),
                         ("21", "AGENDADA", "DIARIA"))
        self.assertEqual((sss["SSS_AMBIENTE"], sss["SSS_AMBIENTE_DESCRICAO"]), ("DEV", "Desenvolvimento"))
        self.assertEqual(sss["SSS_DATA_EXECUCAO"], "2026-10-16 14:05:33")
        self.assertEqual(sss["SSS_SCRIPT_ARQUIVO"], script_real)
        self.assertEqual(os.path.join(sss["SSS_LOG_DIR"], sss["SSS_LOG_ARQUIVO"]), parcial)
        self.assertEqual(os.path.dirname(ex.caminho_log), sss["SSS_LOG_DIR"])
        self.assertTrue(ex.caminho_log.startswith(os.path.join(self.logs, "dev", "carga_faturas", "2026")))
        self.encerrar(ex)


class TestFonte(unittest.TestCase):

    def test_executor_sem_espera_pipe_shell_ou_environ(self):
        with open(executor.__file__, encoding="utf-8") as f:
            fonte = f.read()
        for proibido in ("time.sleep", ".wait(", "PIPE", "shell=" + "True", "os.environ", "os.killpg", "subprocess",
                         "def encerrar("):
            self.assertFalse(proibido in fonte, proibido)


if __name__ == "__main__":
    unittest.main()
