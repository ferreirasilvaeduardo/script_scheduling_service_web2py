# -*- coding: utf-8 -*-
"""Daemon do agente: inicializacao fail-fast, startup check e laco (README §8.1-§8.12; CR-007 R-01 a R-04, R-11,
R-17, R-23, R-28; CR-008 R-01, R-02, R-07, R-08, R-09, R-11, R-17, R-25, R-26, E4).

Laco single-threaded com tres prazos monotonicos e nenhuma espera dentro das operacoes: a unica espera e a
de entre iteracoes (injetada, no maximo 1 s). Encerramentos pela maquina de estados do executor. NODE_OFFLINE,
desdobro, fencing completo e DRAIN ficam para o F8.4 (pontos de extensao).
A pasta de saida do ticket (CR-012, README §8.13) passa pela maquina de fase_saida: empacotar antes do flush
final e gravar depois da finalizacao, fora do mapa de execucoes.

Python puro (sem web2py): o processo inteiro precisa de uma unica thread antes do primeiro spawn, por causa
do preexec_fn (README §3.1, C10). Toda primitiva de SO vem de `os_platform`; o banco, do `db_conn` e dos
repositorios internos do daemon. Cada passo que falha registra CRITICAL e sai com um codigo proprio.
"""
import datetime
import logging
import os
import socket
import threading
import time

import db_conn
import schedule_expansion
import env_builder
import executor
import output_phase
import log_pump
import params_compiler
import log_paths
import os_platform
import rbac
import sss_config
from repo_oracle.scheduler_schedules import RepoSchedulerSchedules
from repo_oracle.scheduler_queue import DuplicateAgent, RegistrationLost, RepoSchedulerQueue
from repo_oracle.scheduler_log import RepoSchedulerLog
from repo_oracle.scheduler_output import RepoSchedulerOutput

_log = logging.getLogger("sss_scheduler")

# Codigos de saida por passo do README §8.12 (o 0 e a parada normal).
EXIT_USER = 10
EXIT_CONFIG = 11
EXIT_SECRETS = 12
EXIT_DIRECTORIES = 13
EXIT_INSTANCE = 14
EXIT_DATABASE = 15
EXIT_REGISTRATION = 16
EXIT_ENVIRONMENTS = 17
EXIT_STARTUP = 18
EXIT_THREADS = 19
EXIT_REGISTRATION_LOST = 20

# Motivos de encerramento -> (status, status_motivo, return_code) do README §5.2.
_FINAL = {
    "TIMEOUT": ("FAILED", "TIMEOUT", -3),
    "LOG_LIMIT": ("FAILED", "LOG_LIMIT", -5),
    "CANCEL": ("CANCELLED", "CANCEL_USER", -1),
    "SHUTDOWN": ("FAILED", "SHUTDOWN", -6),
    "SPAWN_ERROR": ("FAILED", "SPAWN_ERROR", -4),
    # Self-fencing (README §8.9): o encerramento pedido pelo fence. Quem ja tinha resultado (o .sss_result,
    # CR-008 R-12) ou outro motivo de encerramento fica com o seu.
    "FENCED": ("FAILED", "FENCED", -2),
}
_PRECHECK = ("FAILED", "PRECHECK_FAILED", -4)
MAX_WAIT_INTERVAL_S = 1.0
DISK_WARNING_INTERVAL_S = 60

CLOCK_SKEW_S = 60
# Salto de relogio (CR-007 D3, CR-008 R-10): avanco do SYSDATE diferente do monotonico em mais que isso.
CLOCK_JUMP_S = 30
_DIR_PREFIX = "ticket_"


class StartupFailure(SystemExit):
    """Falha de um passo da inicializacao: o CRITICAL ja foi registrado; o codigo identifica o passo."""

    def __init__(self, codigo, motivo):
        SystemExit.__init__(self, codigo)
        self.code = codigo
        self.reason = motivo


class _Log(logging.LoggerAdapter):
    """Toda linha com agente, ticket e acao (README §13)."""

    def process(self, msg, kwargs):
        extra = dict(self.extra)
        extra.update(kwargs.pop("extra", None) or {})
        kwargs["extra"] = extra
        return msg, kwargs


def _sss_dirs(cfg):
    """Pastas do SSS onde nenhum script nem interpretador pode ficar (SSS_DIR, README §8.5). CR-014: inclui
    output_dir e input_dir, que o usuario de execucao grava (um script ali poderia ser trocado por outro)."""
    agente = cfg.agent
    return tuple(d for d in (cfg.logging.log_dir, agente.work_dir, agente.exec_work_dir,
                             getattr(agente, "output_dir", None), getattr(agente, "input_dir", None)) if d)


def _read_state(pasta, nome, plat):
    try:
        return plat.read_state(os.path.join(pasta, nome))
    except (OSError, ValueError):  # estado ilegivel: tratado como ausente, com o rastro preservado
        return None


class Agent(object):
    """Daemon de um no agente. inicializar() executa os passos 1 a 9 do README §8.12, em ordem."""

    def __init__(self, cfg=None, segredos=None, plat=None, conexao=None, repo=None, repo_log=None,
                 relogio=None, relogio_parede=None, hostname=None, pid=None, carregar_config=None,
                 carregar_segredos=None, repo_saida=None, repo_agenda=None):
        self.cfg = cfg
        self.secrets = segredos
        self.plat = plat or os_platform
        self.connection = conexao
        self.repo = repo
        self.repo_log = repo_log
        self.repo_output = repo_saida
        self.repo_schedules = repo_agenda
        self.expansion = None
        self.clock = relogio or time.monotonic
        self.wall_clock = relogio_parede or time.time
        self.hostname = hostname or socket.gethostname()
        self.pid = pid or os.getpid()
        self._load_config = carregar_config or (lambda: sss_config.get_config(nome_log="sss_scheduler"))
        self._load_secrets = carregar_segredos
        self.log = _Log(_log, {"agent": "-", "ticket": "-", "action": "INICIO"})
        self.lock = None
        self.agent_db_id = None
        self.last_hb_ok = None
        self.supplementary_unit = 2
        self.active_environments = []
        # Startup check: grupos ainda em encerramento (o laco avanca e limpa) e pastas preservadas.
        self.stopping = {}
        self.preserved = set()

    # ------------------------------------------------------------------ util

    def _fail(self, codigo, motivo, *args):
        texto = motivo % args if args else motivo
        self.log.critical("Subida abortada: %s", texto, extra={"action": "INICIO"})
        raise StartupFailure(codigo, texto)

    @property
    def agent_id(self):
        return self.cfg.agent.agent_id

    def _conn(self):
        return self.connection.get_connection()

    def _exec_user(self, ambiente):
        return dict(self.cfg.agent.exec_users or ()).get(ambiente) or None

    # --------------------------------------------------------------- passos

    def initialize(self):
        """Passos 1 a 9 do README §8.12 e a checagem de thread unica. Falha: StartupFailure, com a trava
        de instancia e a conexao ja liberadas."""
        try:
            self._steps()
        except StartupFailure:
            self.release_resources()
            raise
        self.log.info("agente inicializado (versao %s, %d grupo(s) em encerramento, %d pasta(s) preservada(s))",
                      sss_config.SSS_VERSION, len(self.stopping), len(self.preserved))
        return self

    def release_resources(self):
        """Fecha a conexao e solta a trava de instancia (falha na subida e parada)."""
        if self.connection is not None and hasattr(self.connection, "close"):
            self.connection.close()
        if self.lock is not None:
            self.plat.release_instance(self.lock)
            self.lock = None

    def _steps(self):
        self._step1_user()
        self._step2_config()
        self._step3_secrets()
        self._step4_directories()
        self._step5_instance()
        self._step6_database()
        self._step7_registration()
        self._step8_environments()
        self._step9_startup_check()
        self._check_single_thread()

    def _step1_user(self):
        if self.plat.is_privileged_user():
            self._fail(EXIT_USER, "o agente nao pode rodar como root (README §8.12 passo 1)")

    def _step2_config(self):
        if self.cfg is None:
            try:
                self.cfg = self._load_config()
            except sss_config.ConfigError as exc:  # obter_config ja registrou o CRITICAL (README §12.1)
                raise StartupFailure(EXIT_CONFIG, str(exc))
        agente = self.cfg.agent
        self.log.extra["agent"] = agente.agent_id
        try:
            sss_config.check_encoding()
        except sss_config.ConfigError as exc:
            self._fail(EXIT_CONFIG, "%s", exc)
        if not self.plat.locale_available(agente.child_locale):
            self._fail(EXIT_CONFIG, "child_locale %s nao consta em locale -a (CR-007, R-17)", agente.child_locale)
        db_conn.connection_budget_s(self.cfg.oracle.dsn, sss_config.call_timeout_s(self.cfg.oracle.call_timeout_ms))
        # Conferencia entre nos no E2E (README §8.9, "Mesmos tempos em todos os nos").
        self.log.info("tempos do fencing: fence_timeout_s=%s node_offline_timeout_s=%s",
                      agente.fence_timeout_s, agente.node_offline_timeout_s)

    def _step3_secrets(self):
        if self.secrets is not None:
            return
        try:
            carregar = self._load_secrets or (
                lambda: sss_config.load_secrets(self.cfg.secrets.secrets_file, cfg=self.cfg, papel="agent"))
            self.secrets = carregar()
        except sss_config.ConfigError as exc:
            self._fail(EXIT_SECRETS, "secrets.cfg invalido: %s", exc)

    def _step4_directories(self):
        agente = self.cfg.agent
        for nome, caminho in (("log_dir", self.cfg.logging.log_dir), ("work_dir", agente.work_dir)):
            codigo = self.plat.validate_restricted_dir(caminho)
            if codigo:
                self._fail(EXIT_DIRECTORIES, "%s %s recusado: %s", nome, caminho, codigo)
        dirs_sss = _sss_dirs(self.cfg)
        if not agente.interpreters:
            self._fail(EXIT_DIRECTORIES, "[agent] interpreters vazio: o agente nao executaria nada")
        for logico, caminho in agente.interpreters:
            try:
                self.plat.validate_interpreter_executable(caminho, dirs_sss=dirs_sss)
            except Exception as exc:  # noqa: BLE001 - PathGuardError e afins: CRITICAL com o codigo
                self._fail(EXIT_DIRECTORIES, "interpretador %s (%s) recusado: %s", logico, caminho,
                             getattr(exc, "code", exc.__class__.__name__))
        if self.cfg.app.sss_env != "DEV":
            falhas = self.plat.validate_execution(agente.exec_users, agente.exec_work_dir)
            for falha in falhas:
                self.log.critical("execucao fora de DEV: %s", falha)
            if falhas:
                self._fail(EXIT_DIRECTORIES, "%d falha(s) na conferencia do helper e do sudoers", len(falhas))
        self._check_output_dir()
        self._check_input_dir()

    def _check_input_dir(self):
        """CR-014 (README §8.12 passo 4): input_dir fora das pastas do sistema; fora de DEV, a pasta de cada
        ambiente atendido do usuario de execucao dele, sem escrita de grupo nem de outros (como a de saida)."""
        agente = self.cfg.agent
        if not agente.input_dir:
            return
        codigo = self.plat.validate_restricted_dir(agente.input_dir)
        if codigo:
            self._fail(EXIT_DIRECTORIES, "input_dir %s recusado: %s", agente.input_dir, codigo)
        if self.cfg.app.sss_env == "DEV" and not agente.exec_users:
            return
        pares = [(os.path.join(agente.input_dir, log_paths.environment_dir(amb)), self._exec_user(amb))
                 for amb in agente.environments if self._exec_user(amb)]
        falhas = self.plat.validate_output_dirs(pares)
        for falha in falhas:
            self.log.critical("pasta de entrada: %s", falha)
        if falhas:
            self._fail(EXIT_DIRECTORIES, "%d falha(s) nas pastas de entrada (CR-014)", len(falhas))

    def _check_output_dir(self):
        """CR-012 (README §8.12 passo 4): output_dir fora das pastas do sistema; fora de DEV, a pasta de cada
        ambiente atendido do usuario de execucao dele, sem escrita de grupo nem de outros."""
        agente = self.cfg.agent
        if not agente.output_dir:
            return
        codigo = self.plat.validate_restricted_dir(agente.output_dir)
        if codigo:
            self._fail(EXIT_DIRECTORIES, "output_dir %s recusado: %s", agente.output_dir, codigo)
        if self.cfg.app.sss_env == "DEV" and not agente.exec_users:
            return
        pares = [(os.path.join(agente.output_dir, log_paths.environment_dir(amb)), self._exec_user(amb))
                 for amb in agente.environments if self._exec_user(amb)]
        falhas = self.plat.validate_output_dirs(pares)
        for falha in falhas:
            self.log.critical("pasta de saida: %s", falha)
        if falhas:
            self._fail(EXIT_DIRECTORIES, "%d falha(s) nas pastas de saida (CR-012)", len(falhas))

    def _step5_instance(self):
        work = self.cfg.agent.work_dir
        try:
            self.lock = self.plat.lock_instance(os.path.join(work, "sss-%s.lock" % self.agent_id))
        except self.plat.InstanceAlreadyRunning as exc:
            self._fail(EXIT_INSTANCE, "%s", exc)
        stop = os.path.join(work, "sss-%s.stop" % self.agent_id)
        if os.path.exists(stop):
            os.unlink(stop)
            self.log.warning("arquivo .stop antigo removido (CR-007, R-32)")

    def _step6_database(self):
        try:
            if self.connection is None:
                selecao = db_conn.select_driver(self.cfg, self.secrets)
                db_conn.initialize(selecao, self.cfg)
                self.connection = db_conn.ResilientConnection(self.cfg, self.secrets, papel="agent")
            if not self.connection.ensure():
                self._fail(EXIT_DATABASE, "sem conexao com o Oracle")
            conn = self._conn()
            if self.repo is None:
                self.repo = RepoSchedulerQueue.from_config(self.cfg)
            if self.repo_log is None:
                self.repo_log = RepoSchedulerLog.from_config(self.cfg)
            if self.repo_output is None:
                self.repo_output = RepoSchedulerOutput.from_config(self.cfg)
            if self.repo_schedules is None:
                self.repo_schedules = RepoSchedulerSchedules.from_config(self.cfg)
            agora_banco = db_conn.db_now(conn)
            local = self.wall_clock()
            divergencia = abs((datetime.datetime.fromtimestamp(local) - agora_banco).total_seconds())
            if divergencia > CLOCK_SKEW_S:
                self.log.warning("relogio local diverge do SYSDATE em %d s (README §7.1)", divergencia)
            db_conn.check_schema_version(conn, owner=self.cfg.oracle.owner.strip(),
                                            prefixo=self.cfg.oracle.table_prefix.strip())
            self.supplementary_unit = self.repo_log.supplementary_unit(conn)
        except StartupFailure:
            raise
        except Exception as exc:  # noqa: BLE001 - driver, versao do esquema ou leitura: CRITICAL
            self._fail(EXIT_DATABASE, "banco: %s", exc)

    def _step7_registration(self):
        agente = self.cfg.agent
        criticos = sss_config.critical_config(self.cfg)
        inicio = self.clock()
        try:
            self.agent_db_id = self.repo.register_agent(self._conn(), {
                "code": agente.agent_id, "hostname": self.hostname, "pid": self.pid,
                "version": sss_config.SSS_VERSION, "environments": ",".join(agente.environments),
                "platform": self.plat.NAME, "interpreters": ",".join(k for k, _v in agente.interpreters),
                "critical_config": criticos, "node_offline_timeout_s": agente.node_offline_timeout_s,
            }, self.plat.process_exists)
            divergentes = self.repo.check_config(self._conn(), agente.agent_id, criticos,
                                                    agente.node_offline_timeout_s)
        except DuplicateAgent as exc:
            self._fail(EXIT_REGISTRATION, "agent_id duplicado: %s", exc)
        except Exception as exc:  # noqa: BLE001
            self._fail(EXIT_REGISTRATION, "registro do agente: %s", exc)
        if divergentes:
            for codigo, outra in divergentes:
                self.log.critical("config_criticos diverge do agente %s: local=%s remoto=%s", codigo, criticos, outra)
            self._fail(EXIT_REGISTRATION, "configuracao critica diferente da dos outros agentes (CR-007, R-23)")
        self.last_hb_ok = inicio

    def _step8_environments(self):
        try:
            ativos, inexistentes = self.repo.active_environments(self._conn(), self.cfg.agent.environments)
        except Exception as exc:  # noqa: BLE001
            self._fail(EXIT_ENVIRONMENTS, "leitura dos ambientes: %s", exc)
        if inexistentes:
            self._fail(EXIT_ENVIRONMENTS, "ambientes atendidos inexistentes: %s", ", ".join(inexistentes))
        for nome in sorted(set(self.cfg.agent.environments) - set(ativos)):
            self.log.warning("ambiente atendido %s inativo: ignorado ate ser reativado", nome)
        self.active_environments = ativos

    def _check_single_thread(self):
        if threading.active_count() != 1:
            nomes = ", ".join(sorted(t.name for t in threading.enumerate()))
            self._fail(EXIT_THREADS, "o processo tem %d threads antes do primeiro spawn (%s); o preexec_fn "
                                       "exige thread unica (README §3.1)", threading.active_count(), nomes)

    # -------------------------------------------------------- startup check

    def _local_dirs(self):
        """{ticket_id: pasta} das pastas work_dir/ticket_<id> (nao segue links)."""
        work = self.cfg.agent.work_dir
        pastas = {}
        for nome in sorted(os.listdir(work)):
            caminho = os.path.join(work, nome)
            sufixo = nome[len(_DIR_PREFIX):]
            if nome.startswith(_DIR_PREFIX) and sufixo.isdigit() and os.path.isdir(caminho) \
                    and not os.path.islink(caminho):
                pastas[int(sufixo)] = caminho
        return pastas

    def _step9_startup_check(self):
        """O disco do agente e a fonte de verdade sobre o que ele iniciou (README §8.12 passo 9)."""
        try:
            self._startup_check()
        except StartupFailure:
            raise
        except Exception as exc:  # noqa: BLE001
            self._fail(EXIT_STARTUP, "startup check: %s", exc)

    def _startup_check(self):
        agente = self.cfg.agent
        conn = self._conn()
        running = dict((t["id"], t) for t in self.repo.tickets_running_do_agente(conn, self.agent_id))
        pastas = self._local_dirs()
        resultados = {}
        for tid, pasta in sorted(pastas.items()):
            log = _Log(_log, {"agent": self.agent_id, "ticket": tid, "action": "STARTUP"})
            proc = _read_state(pasta, executor.PROC, self.plat)
            spawn = _read_state(pasta, executor.SPAWN, self.plat)
            resultados[tid] = _read_state(pasta, executor.RESULT, self.plat)
            usuario = (proc or spawn or {}).get("exec_user")
            if proc is not None:
                self._reopen(tid, pasta, proc, usuario, log)
            elif spawn is not None:
                # Talvez iniciado (CR-008, R-01): nunca volta a fila. Unica espera da subida (kill_grace_s).
                base = os.path.join(agente.exec_work_dir, usuario) if usuario else agente.work_dir
                if self.plat.stop_ticket(base, tid, usuario, agente.kill_grace_s) == "NAO_SUPORTADO":
                    # O processo pode seguir vivo: a pasta fica como rastro (CR-008, R-26).
                    self.preserved.add(tid)
                    log.warning("TALVEZ_INICIADO sem meio de encerrar nesta plataforma: o processo fica com o "
                                "usuario de execucao")
                log.error("TALVEZ_INICIADO: .sss_spawn sem .sss_proc")
        for tid, ticket in sorted(running.items()):
            log = _Log(_log, {"agent": self.agent_id, "ticket": tid, "action": "STARTUP"})
            if tid in pastas:
                res = resultados.get(tid)
                if res is not None:
                    self._finalize(tid, res["status"], res["status_reason"], res["return_code"], log,
                                    "resultado local gravado antes da queda")
                else:
                    self._finalize(tid, "FAILED", "ORPHAN_PROCESS", -2, log, "processo sem acompanhamento")
            elif ticket["process_id"] is None:
                desfecho = self.repo.return_to_queue(conn, tid, self.agent_id)
                (log.warning if desfecho != "PERDIDO" else log.info)("ticket sem pasta local e sem PID: %s",
                                                                     desfecho)
            else:
                self._finalize(tid, "FAILED", "ORPHAN_PROCESS", -2, log, "PID sem pasta local")
        for tid, pasta in sorted(pastas.items()):
            if tid in self.stopping or tid in self.preserved:
                continue
            self._clean_dir(tid, pasta)
        # CR-012 (README §8.13): saidas que ficaram em gravacao numa queda viram FALHOU; a pasta fica no disco.
        falhadas = self.repo_output.fail_agent_writing(conn, self.agent_id)
        conn.commit()
        if falhadas:
            self.log.warning("%d saida(s) em gravacao marcada(s) FALHOU na subida", falhadas,
                             extra={"action": "STARTUP"})

    def _reopen(self, tid, pasta, proc, usuario, log):
        processo = self.plat.reopen_group(proc)
        if processo is None:
            return
        execucao = executor.Execution(tid, pasta, usuario,
                                     os.path.join(self.cfg.agent.exec_work_dir, usuario) if usuario else None, None)
        execucao.process = processo
        execucao.pid = processo.pid
        execucao.identity = processo.identity
        executor.request_stop(execucao, self.clock(), grace_s=self.cfg.agent.kill_grace_s)
        if execucao.no_identity:
            self.preserved.add(tid)  # CR-008, R-26: o unico rastro do processo fica
        elif not executor.advance_stop(execucao, self.clock()):
            self.stopping[tid] = execucao  # o laco avanca o encerramento e limpa a pasta depois
            log.warning("grupo do ticket em encerramento na subida (pid %s)", processo.pid)

    def _finalize(self, tid, status, motivo, rc, log, detalhe):
        """Finaliza o ticket RUNNING deste agente com a linha [SSS] no log (README §5.2)."""
        conn = self._conn()
        self._linha_sss(conn, tid, "%s: %s (agente %s)" % (motivo, detalhe, self.agent_id))
        if not self.repo.finalize(conn, tid, self.agent_id, status, motivo, rc):
            log.warning("OWNERSHIP_LOST na subida: o ticket ja nao era deste agente")
        elif status == "SUCCESS":
            log.info("ticket finalizado na subida pelo resultado local: %s/%s", status, motivo)
        else:
            log.error("ticket finalizado na subida: %s/%s (%s)", status, motivo, detalhe)

    def _linha_sss(self, conn, tid, texto):
        ticket = self.repo.get_ticket(conn, tid)
        if ticket is None:
            return
        try:
            self.repo_log.append_chunk(conn, tid, self.agent_id, int(ticket.get("log_offset_chars") or 0),
                                 "[SSS] %s\n" % texto)
            conn.commit()
        except Exception as exc:  # noqa: BLE001 - a linha e informativa; a finalizacao segue
            conn.rollback()
            _log.warning("linha [SSS] nao gravada no log do ticket (%s)", exc.__class__.__name__,
                         extra={"agent": self.agent_id, "ticket": tid, "action": "STARTUP"})

    def _clean_dir(self, tid, pasta):
        execucao = executor.Execution(tid, pasta, None, None, None)
        estado = _read_state(pasta, executor.PROC, self.plat) or _read_state(pasta, executor.SPAWN, self.plat) or {}
        usuario = estado.get("exec_user")
        if usuario:
            execucao.exec_user = usuario
            execucao.base_dir = os.path.join(self.cfg.agent.exec_work_dir, usuario)
        try:
            executor.clean(execucao)
        except Exception as exc:  # noqa: BLE001 - a pasta fica para a proxima subida
            self.preserved.add(tid)
            _log.warning("pasta do ticket nao removida na subida (%s)", exc.__class__.__name__,
                         extra={"agent": self.agent_id, "ticket": tid, "action": "STARTUP"})

    # ======================================================================
    # Laco (README §8.1)
    # ======================================================================

    def prepare_loop(self, esperar):
        """Estado do laco: mapa local, bombas do log, rodada do pump e os tres prazos.

        esperar(segundos): a unica espera do daemon, entre iteracoes (no maximo 1 s); o run_scheduler injeta a
        real e os testes, um duble. Nenhuma operacao do laco espera (CR-007, R-04)."""
        agente = self.cfg.agent
        self.executions = {}
        self.pumps = {}
        self.pending_returns = set()
        # CR-012: saidas a gravar depois da finalizacao do ticket {tid: (Saida, Execucao, log)}.
        self.outputs = {}
        # Parada (README §8.11; F8.4d): _parando suspende claim e desdobro; _terminando abandona a saida em
        # andamento. DRAIN liga so o primeiro ate shutdown_grace_s; TERMINATE liga os dois.
        self._stopping = False
        self._terminating = False
        self._drain_until = None
        # Self-fencing e NODE_OFFLINE (F8.4c; README §8.8 e §8.9).
        self.fenced = False
        self._clock_ref = None          # (SYSDATE, monotonico) do ultimo SYSDATE lido
        self._node_offline_suspended_until = None
        self.round = log_pump.Round(self.pumps, self.clock, agente.heartbeat_interval_s / 2.0)
        self._wait = esperar
        agora = self.clock()
        self.deadlines = {"rapido": agora, "heartbeat": agora, "orquestrador": agora}
        self._last_disk_warning = None
        self._fixed_masker = [v for v in self._secret_values() if v]
        self.exit_code = 0
        return self

    def _secret_values(self):
        seg = self.secrets
        valores = [getattr(seg, "oracle_password", None), getattr(seg, "purge_password", None),
                   getattr(seg, "monitor_password", None)]
        for cred in (getattr(seg, "environments", None) or {}).values():
            valores.append(getattr(cred, "password", None))
        return valores

    def run(self, parada, esperar=None, ate=None, limite_s=None):
        """Laco principal ate a parada (flag com is_set() ou arquivo .stop). Devolve o codigo de saida.

        ate/limite_s: so para os testes (condicao de termino e prazo maximo do harness).
        """
        if not hasattr(self, "executions"):
            self.prepare_loop(esperar)
        agente = self.cfg.agent
        stop = os.path.join(agente.work_dir, "sss-%s.stop" % self.agent_id)
        fim = None if limite_s is None else self.clock() + limite_s
        while True:
            self._iteration()
            self._check_fence()
            agora = self.clock()
            try:
                if agora >= self.deadlines["rapido"]:
                    self.deadlines["rapido"] = agora + agente.cancel_poll_interval_s
                    self._cycle("rapido", self._fast_cycle)
                    self._check_fence()
                if agora >= self.deadlines["heartbeat"]:
                    self.deadlines["heartbeat"] = agora + agente.heartbeat_interval_s
                    self._cycle("heartbeat", self._heartbeat_cycle)
                    self._check_fence()
                if agora >= self.deadlines["orquestrador"]:
                    self.deadlines["orquestrador"] = agora + agente.orchestrator_interval_s
                    if not self.fenced:
                        self._cycle("orquestrador", self._orchestrator_cycle)
                        self._check_fence()
            except RegistrationLost as exc:
                self.log.critical("REGISTRO_PERDIDO: %s; encerramento TERMINATE", exc, extra={"action": "HB"})
                self.stop_all("TERMINATE", registro_perdido=True)
                return EXIT_REGISTRATION_LOST
            if parada.is_set() or os.path.exists(stop):
                if agente.shutdown_mode != "DRAIN":
                    return self.stop_all("TERMINATE")
                if self._drain_until is None:
                    self._start_drain()
                if self._drained() or self.clock() >= self._drain_until:
                    return self.stop_all("DRAIN")
            if (ate is not None and ate()) or (fim is not None and self.clock() >= fim):
                return self.exit_code
            espera = min(self.deadlines.values()) - self.clock()
            self._wait(max(0.0, min(MAX_WAIT_INTERVAL_S, espera)))

    # ---------------------------------------------------- parada DRAIN (README §8.11)

    def _start_drain(self):
        """DRAIN: para claim e desdobro e aguarda os filhos por ate shutdown_grace_s, mantendo heartbeat,
        varredura, log pump, saida e fence pelo laco normal (CR-007, R-04)."""
        self._stopping = True
        self._drain_until = self.clock() + self.cfg.agent.shutdown_grace_s
        self.log.warning("DRAIN: parada pedida; sem claim nem desdobro, aguardando %d execucao(oes) por ate %d s",
                         len(self.executions), self.cfg.agent.shutdown_grace_s, extra={"action": "PARADA"})

    def _drained(self):
        return not (self.executions or self.stopping or getattr(self, "outputs", None))

    # ---------------------------------------------------- self-fencing (README §8.9)

    def _fence_expired(self):
        return self.last_hb_ok is not None and self.clock() - self.last_hb_ok > self.cfg.agent.fence_timeout_s

    def _check_fence(self):
        """A cada iteracao e depois de cada chamada ao banco (CR-007, R-04): sem heartbeat confirmado ha mais de
        fence_timeout_s (medido do inicio da transacao, CR-008 R-09), encerra TODAS as execucoes de uma vez pela
        maquina de estados (SIGTERM em todas, SIGKILL nas restantes depois de kill_grace_s), suspende claims,
        desdobro e NODE_OFFLINE e registra CRITICAL FENCED. Sai do modo cercado so com um heartbeat confirmado."""
        if self.fenced or not self._fence_expired():
            return
        self.fenced = True
        rodando = [item for item in self.executions.values() if item.phase == _Item.RODANDO]
        for item in rodando:
            self._stop(item, "FENCED")
        self.log.critical("FENCED: sem heartbeat confirmado ha %.0f s (fence_timeout_s %d); %d execucao(oes) "
                          "encerrada(s), claims e desdobro suspensos ate o banco voltar",
                          self.clock() - self.last_hb_ok, self.cfg.agent.fence_timeout_s, len(rodando),
                          extra={"action": "FENCE"})

    def _leave_fence(self):
        self.fenced = False
        self.log.warning("FENCED encerrado: heartbeat confirmado; os tickets que o agente possuia sao finalizados "
                         "pelo resultado local ou como FENCED", extra={"action": "FENCE"})

    def _clock_jump(self, sysdate):
        """CR-007 D3 / CR-008 R-10: True (e inicia a suspensao do NODE_OFFLINE) se o avanco do SYSDATE diferir do
        avanco do monotonico em mais de CLOCK_JUMP_S desde o ultimo SYSDATE lido."""
        agora = self.clock()
        ref, self._clock_ref = self._clock_ref, (sysdate, agora)
        if ref is None or sysdate is None:
            return False
        diferenca = (sysdate - ref[0]).total_seconds() - (agora - ref[1])
        if abs(diferenca) <= CLOCK_JUMP_S:
            return False
        self._node_offline_suspended_until = agora + self.cfg.agent.node_offline_timeout_s
        self.log.warning("SALTO_RELOGIO: o SYSDATE andou %.0f s diferente do relogio monotonico; NODE_OFFLINE "
                         "suspenso por %d s", diferenca, self.cfg.agent.node_offline_timeout_s, extra={"action": "HB"})
        return True

    def _cycle(self, nome, funcao):
        """Um ciclo isolado: erro registrado com contexto; erro de rede descarta a conexao (reconexao no
        ciclo seguinte, uma tentativa por ciclo, sem esperar)."""
        if not self.connection.ensure():
            if nome == "rapido":
                self._iteration_without_db()
            return
        try:
            funcao()
        except RegistrationLost:
            raise
        except Exception as exc:  # noqa: BLE001 - o laco nunca cai por um ciclo
            self.log.error("ciclo %s falhou: %s", nome, exc, exc_info=not db_conn.is_network_error(exc),
                           extra={"action": nome.upper()})
            self.connection.notify_error(exc)

    def _iteration_without_db(self):
        """Sem banco, os processos seguem acompanhados localmente (timeout e teto local)."""
        self._check_limits()

    # ---------------------------------------------------- toda iteracao

    def _iteration(self):
        """Maquinas de encerramento, coleta dos processos que terminaram e no maximo um flush final."""
        agora = self.clock()
        for tid, ex in list(self.stopping.items()):
            if executor.advance_stop(ex, agora):
                del self.stopping[tid]
                self._clean(tid, ex.work_dir_ticket)
        flush_feito = False
        for tid, item in sorted(self.executions.items()):
            ex = item.execution
            if item.phase == _Item.RODANDO:
                if executor.check(ex) is not None:
                    # Terminou sozinho: o grupo e encerrado mesmo assim (R-02), prevalece o resultado real.
                    self._stop(item, None)
                continue
            if item.phase == _Item.ENCERRANDO:
                if executor.advance_stop(ex, agora):
                    item.phase = _Item.FINALIZAR
                continue
            if item.phase == _Item.FINALIZAR and not self._pack(item, agora):
                continue
            if item.phase == _Item.FINALIZAR and not flush_feito:
                flush_feito = self._finalize_execution(item)
        self._advance_outputs(agora)

    # ---------------------------------------------------- saida (CR-012)

    def _pack(self, item, agora):
        """Etapa 1 da fase de saida, antes do flush final. True quando o ticket pode seguir para a finalizacao."""
        saida = item.output
        if saida is None or saida.packed:
            return True
        if item.reason in ("OWNERSHIP_LOST", "SHUTDOWN") or self._terminating:
            output_phase.abandon(saida, self.plat)
            return True
        agente = self.cfg.agent
        if saida.process is None:
            output_phase.start_pack(saida, self.plat, agente.output_max_bytes, agente.output_max_files, agora)
            if not saida.packed:
                return False
        elif not output_phase.advance_pack(saida, self.plat, agora):
            return False
        linha = output_phase.log_line(saida, self.agent_id, agente.output_max_files, agente.output_max_bytes)
        if linha and item.execution is not None and item.execution.log_path:
            try:
                executor.append_local_line(item.execution, linha)
            except OSError as exc:  # a linha e informativa; a fase segue
                item.log.warning("linha [SSS] da saida nao gravada (%s)", exc.__class__.__name__,
                                 extra={"action": "SAIDA"})
        if saida.result == output_phase.EXCEEDED:
            item.log.warning("saida acima do limite (%s): a pasta fica no disco", saida.reason, extra={"action": "SAIDA"})
        return True

    def _advance_outputs(self, agora):
        """Etapa 2, depois da finalizacao: grava a saida sem esperar, refazendo erro de banco a cada
        cancel_poll_interval_s. Ao terminar, remove a pasta (ZIP ou vazia) e o work_dir do ticket."""
        if not self.outputs or self._terminating:
            return
        conn = self.connection.get_connection()
        if conn is None:
            return
        for tid, (saida, ex, log) in sorted(self.outputs.items()):
            if agora < saida.next_attempt:
                continue
            try:
                desfecho = output_phase.write(saida, conn, self.repo_output, self.agent_id)
            except Exception as exc:  # noqa: BLE001 - pendencia refeita no proximo prazo
                saida.next_attempt = agora + self.cfg.agent.cancel_poll_interval_s
                if not saida.pending_warned:
                    saida.pending_warned = True
                    log.warning("gravacao da saida pendente (%s)", exc.__class__.__name__, extra={"action": "SAIDA"})
                self.connection.notify_error(exc)
                return
            if desfecho == output_phase.CONTINUE:
                continue
            del self.outputs[tid]
            if desfecho == output_phase.OWNERSHIP_LOST:
                log.error("OWNERSHIP_LOST na saida: nada gravado; a pasta fica no disco", extra={"action": "SAIDA"})
            else:
                log.info("saida %s", saida.result, extra={"action": "SAIDA"})
                if output_phase.should_remove_dir(saida):
                    try:
                        output_phase.remove_dir(saida, self.plat)
                    except Exception as exc:  # noqa: BLE001 - fica para o purge (output_retention_days)
                        log.warning("pasta de saida nao removida (%s)", exc.__class__.__name__,
                                    extra={"action": "SAIDA"})
            self._clean(tid, ex.work_dir_ticket, ex)

    def _stop(self, item, motivo):
        """Pede o encerramento do grupo (SIGTERM, prazo, SIGKILL) sem esperar. motivo None: saida natural."""
        if item.phase != _Item.RODANDO:
            return
        ex = item.execution
        if motivo is not None and executor.check(ex) is not None:
            motivo = None  # o processo ja tinha terminado: prevalece o resultado real (README §5.6)
        item.reason = motivo
        executor.request_stop(ex, self.clock(), grace_s=self.cfg.agent.kill_grace_s)
        item.phase = _Item.ENCERRANDO
        if motivo is not None:
            item.log.warning("encerramento pedido: %s", motivo, extra={"action": "ENCERRAR"})

    def _result(self, item):
        if item.reason in _FINAL:
            return _FINAL[item.reason]
        rc = executor.check(item.execution)
        if rc is None:
            # Lider reaberto ou coletado por outro caminho: sem returncode, o agente nao sabe o desfecho.
            return ("FAILED", "ORPHAN_PROCESS", -2)
        return executor.translate_return(rc, self.plat.NAME)

    def _finalize_execution(self, item):
        """Passos 2 a 6 da finalizacao (README §8.7). True se fez um flush final nesta iteracao."""
        conn = self._conn()
        if conn is None:
            return False
        fez_flush = False
        if item.pump is not None and not item.flush_ok:
            fez_flush = True
            desfecho = log_pump.final_flush(item.pump, conn, self.repo_log, self.agent_id)
            if desfecho == log_pump.UNCERTAIN_CONNECTION:
                self.connection.close()
                return True
            if desfecho == log_pump.OWNERSHIP_LOST:
                item.reason = "OWNERSHIP_LOST"
            item.flush_ok = True
        if item.reason == "OWNERSHIP_LOST":
            item.log.error("OWNERSHIP_LOST: o ticket ja nao e deste agente; nenhum status gravado",
                           extra={"action": "FINALIZAR"})
            self._remove(item)
            return fez_flush
        if item.result is None:
            item.result = self._result(item)
            executor.record_result(item.execution, *item.result)
        try:
            gravou = self.repo.finalize(conn, item.tid, self.agent_id, *item.result)
        except Exception as exc:  # noqa: BLE001 - finalizacao pendente (CR-007 R-03), refeita no ciclo rapido
            if not item.finalize_pending:
                item.log.warning("finalizacao pendente (%s)", exc.__class__.__name__, extra={"action": "FINALIZAR"})
            item.finalize_pending = True
            self.connection.notify_error(exc)
            return fez_flush
        if gravou:
            item.log.info("ticket finalizado: %s/%s rc=%s", *item.result, extra={"action": "FINALIZAR"})
            saida = item.output
            if saida is not None and saida.result not in (None, output_phase.ABANDONED):
                # CR-012: a gravacao da saida segue fora do mapa de execucoes (nao ocupa vaga de claim).
                self.executions.pop(item.tid, None)
                self.pumps.pop(item.tid, None)
                self.outputs[item.tid] = (saida, item.execution, item.log)
                return fez_flush
        else:
            item.log.error("OWNERSHIP_LOST na finalizacao: o resultado fica so no log local",
                           extra={"action": "FINALIZAR"})
        self._remove(item)
        return fez_flush

    def _remove(self, item):
        self.executions.pop(item.tid, None)
        self.pumps.pop(item.tid, None)
        self._clean(item.tid, item.execution.work_dir_ticket if item.execution else None,
                     item.execution)

    def _clean(self, tid, pasta, execucao=None):
        if not pasta:
            return
        if execucao is None:
            return self._clean_dir(tid, pasta)
        try:
            executor.clean(execucao)
        except Exception as exc:  # noqa: BLE001 - a pasta fica para a proxima subida
            _log.warning("pasta do ticket nao removida (%s)", exc.__class__.__name__,
                         extra={"agent": self.agent_id, "ticket": tid, "action": "LIMPEZA"})

    # ---------------------------------------------------- ciclo rapido

    def _fast_cycle(self):
        self._check_limits()
        if self.fenced:
            return  # em modo cercado, so o heartbeat tenta o banco (README §8.9)
        conn = self._conn()
        proprios = self.repo.own_sweep(conn, self.agent_id)
        for tid, item in list(self.executions.items()):
            if item.phase == _Item.RESERVADO:
                continue
            if tid not in proprios:
                if item.phase == _Item.RODANDO:
                    self._stop(item, "OWNERSHIP_LOST")
                elif item.phase in (_Item.ENCERRANDO, _Item.FINALIZAR) and item.reason != "OWNERSHIP_LOST" \
                        and not item.finalize_pending:
                    item.reason = "OWNERSHIP_LOST"
                continue
            if proprios[tid] == "Y" and item.phase == _Item.RODANDO:
                self._stop(item, "CANCEL")
        for tid in sorted(set(proprios) - set(self.executions) - set(self.stopping) - self.pending_returns):
            self._reconcile(tid)
        self._pending()

    def _check_limits(self):
        agora = self.clock()
        for item in list(self.executions.values()):
            if item.phase != _Item.RODANDO:
                continue
            if item.timeout_s and agora - item.start > item.timeout_s:
                self._stop(item, "TIMEOUT")
            elif item.pump is not None and item.pump.local_exceeded():
                self._stop(item, "LOG_LIMIT")

    def _reconcile(self, tid):
        """Ticket RUNNING deste agente fora do mapa local (CR-007 R-03; CR-008 R-01, R-02): mesmo tratamento do
        startup check para esse ticket."""
        conn = self._conn()
        pasta = os.path.join(self.cfg.agent.work_dir, "ticket_%d" % tid)
        log = _Log(_log, {"agent": self.agent_id, "ticket": tid, "action": "VARREDURA"})
        if os.path.isdir(pasta) and not os.path.islink(pasta):
            proc = _read_state(pasta, executor.PROC, self.plat)
            spawn = _read_state(pasta, executor.SPAWN, self.plat)
            res = _read_state(pasta, executor.RESULT, self.plat)
            if proc is not None:
                self._reopen(tid, pasta, proc, proc.get("exec_user"), log)
            elif spawn is not None:
                usuario = spawn.get("exec_user")
                base = os.path.join(self.cfg.agent.exec_work_dir, usuario) if usuario else self.cfg.agent.work_dir
                if self.plat.stop_ticket(base, tid, usuario, self.cfg.agent.kill_grace_s) == "NAO_SUPORTADO":
                    self.preserved.add(tid)
                    log.warning("TALVEZ_INICIADO sem meio de encerrar nesta plataforma")
                log.error("TALVEZ_INICIADO: .sss_spawn sem .sss_proc")
            if res is not None:
                self._finalize(tid, res["status"], res["status_reason"], res["return_code"], log,
                                "resultado local")
            else:
                self._finalize(tid, "FAILED", "ORPHAN_PROCESS", -2, log, "processo sem acompanhamento")
            if tid not in self.stopping and tid not in self.preserved:
                self._clean_dir(tid, pasta)
            return
        ticket = self.repo.get_ticket(conn, tid)
        if ticket is not None and ticket.get("process_id") is None:
            self._return_to_queue(tid, log)
        else:
            self._finalize(tid, "FAILED", "ORPHAN_PROCESS", -2, log, "PID sem pasta local")

    def _return_to_queue(self, tid, log):
        try:
            desfecho = self.repo.return_to_queue(self._conn(), tid, self.agent_id)
        except Exception as exc:  # noqa: BLE001 - devolucao pendente (CR-008, R-08)
            self.pending_returns.add(tid)
            log.warning("devolucao pendente (%s)", exc.__class__.__name__, extra={"action": "DEVOLVER"})
            self.connection.notify_error(exc)
            return
        self.pending_returns.discard(tid)
        if desfecho == "DEVOLVIDO":
            log.info("devolucao: %s", desfecho, extra={"action": "DEVOLVER"})
        else:
            log.warning("devolucao: %s", desfecho, extra={"action": "DEVOLVER"})

    def _pending(self):
        """Finalizacao, devolucao e PID pendentes (CR-007 R-03; CR-008 R-08), ate rowcount 1 ou 0."""
        for tid in sorted(self.pending_returns):
            self._return_to_queue(tid, _Log(_log, {"agent": self.agent_id, "ticket": tid, "action": "DEVOLVER"}))
        for item in list(self.executions.values()):
            if item.pid_pending:
                self._register_pid(item)
            if item.finalize_pending and item.phase == _Item.FINALIZAR:
                self._finalize_execution(item)

    # ---------------------------------------------------- heartbeat e pump

    def _heartbeat_cycle(self):
        conn = self._conn()
        ids = sorted(set(self.executions) | self.pending_returns)
        inicio = self.clock()  # CR-008, R-09: instante antes do primeiro UPDATE
        perdidos, sysdate = self.repo.heartbeat(conn, self.agent_id, self.hostname, self.pid, ids)
        self.last_hb_ok = inicio
        self._clock_jump(sysdate)
        if self.fenced:
            self._leave_fence()
        for tid in perdidos:
            item = self.executions.get(tid)
            if item is not None and item.phase == _Item.RODANDO:
                self._stop(item, "OWNERSHIP_LOST")
            elif item is not None:
                item.reason = "OWNERSHIP_LOST"
            self.pending_returns.discard(tid)
        res = self.round.run(conn, self.repo_log, self.agent_id)
        for tid in res.ownership_lost:
            item = self.executions.get(tid)
            if item is None:
                continue
            if item.phase == _Item.RODANDO:
                self._stop(item, "OWNERSHIP_LOST")
            item.reason = "OWNERSHIP_LOST"
        if res.uncertain_connection:
            self.connection.close()

    # ---------------------------------------------------- orquestrador e claim

    def _orchestrator_cycle(self):
        agente = self.cfg.agent
        conn = self._conn()
        self.active_environments, _inexistentes = self.repo.active_environments(conn, agente.environments)
        criticos = sss_config.critical_config(self.cfg)
        for codigo, outra in self.repo.check_config(conn, self.agent_id, criticos, agente.node_offline_timeout_s):
            self.log.error("CONFIG_DIVERGENTE: agente %s local=%s remoto=%s", codigo, criticos, outra,
                           extra={"action": "CONFIG"})
        self._node_offline()
        self._expansion()
        self._claims()

    def _node_offline(self):
        """Deteccao de no offline (README §8.8; F8.4c): so com o proprio heartbeat em dia (menos de
        fence_timeout_s / 2), fora do modo cercado e fora da suspensao por salto de relogio, que tambem e
        conferido na propria transacao (CR-008, R-10)."""
        agente = self.cfg.agent
        agora = self.clock()
        if self.fenced or self.last_hb_ok is None or agora - self.last_hb_ok >= agente.fence_timeout_s / 2.0:
            return
        if self._node_offline_suspended_until is not None:
            if agora < self._node_offline_suspended_until:
                return
            self._node_offline_suspended_until = None
        marcados = self.repo.mark_node_offline(self._conn(), self.agent_id, agente.node_offline_timeout_s,
                                                 self._clock_jump)
        if marcados:
            self.log.info("NODE_OFFLINE: ticket(s) %s marcado(s) (heartbeat de outro agente vencido ha mais de %d s)",
                          ", ".join(str(i) for i in marcados), agente.node_offline_timeout_s,
                          extra={"action": "NODE_OFFLINE"})

    def _expansion(self):
        """Desdobro dos agendamentos (README §7.5; F8.4b): uma transacao por regra, com orcamento de tempo.
        Suspenso na parada (e, no F8.4c, em modo cercado)."""
        if self._stopping or self.fenced:
            return
        if self.expansion is None:
            self.expansion = schedule_expansion.Expansion(self.repo_schedules, self.repo, self.agent_id, self.cfg.agent,
                                              self.clock)
        stats = self.expansion.run(self._conn(), continuar=self._can_continue)
        if stats["regras"]:
            self.log.info("desdobro: %(regras)d regra(s), %(tickets)d ticket(s), %(pausas)d pausa(s), "
                          "%(puladas)d com outro agente", stats, extra={"action": "DESDOBRO"})

    def _can_continue(self):
        """Entre chamadas ao banco do desdobro e do claim: para se o fence venceu (e cerca) ou se ha parada."""
        self._check_fence()
        return not (self._stopping or self.fenced)

    def _claims(self):
        agente = self.cfg.agent
        vagas = agente.max_parallel_jobs - len(self.executions)
        if vagas <= 0 or not self.active_environments or not self._can_continue():
            return
        livre = self.plat.free_space_mb(self.cfg.logging.log_dir)
        if livre < agente.log_dir_min_free_mb:
            agora = self.clock()
            if self._last_disk_warning is None or agora - self._last_disk_warning >= DISK_WARNING_INTERVAL_S:
                self._last_disk_warning = agora
                self.log.warning("DISCO_LOG: %d MB livres em log_dir (minimo %d): sem claim", livre,
                                 agente.log_dir_min_free_mb, extra={"action": "CLAIM"})
            return
        if agente.output_dir:
            livre_saida = self.plat.free_space_mb(agente.output_dir)
            if livre_saida < agente.log_dir_min_free_mb:
                agora = self.clock()
                if self._last_disk_warning is None or agora - self._last_disk_warning >= DISK_WARNING_INTERVAL_S:
                    self._last_disk_warning = agora
                    self.log.warning("DISCO_SAIDA: %d MB livres em output_dir (minimo %d): sem claim", livre_saida,
                                     agente.log_dir_min_free_mb, extra={"action": "CLAIM"})
                return
        inicio = self.clock()
        orcamento = agente.heartbeat_interval_s / 2.0
        conn = self._conn()
        interpretadores = [k for k, _v in agente.interpreters]
        for cand in self.repo.candidates(conn, self.active_environments, interpretadores, vagas,
                                         agente.queue_aging_min):
            if len(self.executions) >= agente.max_parallel_jobs or self.clock() - inicio > orcamento \
                    or not self._can_continue():
                break
            ok, motivo, started_at = self.repo.claim(conn, cand["id"], cand["script_id"], cand["environment"],
                                                     self.agent_id)
            if not ok:
                if motivo == "LOCK":  # esperado e tratado: WARN com o codigo, sem stack trace (README §13, R-32)
                    self.log.warning("claim do ticket %s pulado: linha do script %s travada por outra sessao (%s, "
                                     "FOR UPDATE WAIT 5)", cand["id"], cand["script_id"], started_at,
                                     extra={"action": "CLAIM"})
                continue
            # CR-007, R-03: no mapa local logo depois do COMMIT do claim, antes de qualquer outra operacao.
            item = _Item(cand["id"], started_at, _Log(_log, {"agent": self.agent_id, "ticket": cand["id"],
                                                             "action": "SPAWN"}))
            self.executions[item.tid] = item
            self._start(item)

    # ---------------------------------------------------- pre-validacao e spawn

    def _start(self, item):
        """Pre-validacao (README §8.4 passo 1), releitura do cancelamento, spawn e registro do PID."""
        try:
            pre = self._prevalidate(item)
        except Exception as exc:  # noqa: BLE001
            return self._error_before_spawn(item, exc)
        if pre is None:
            return
        snap, argv, script_real, contexto = pre
        try:
            if self.repo.is_cancel_requested(self._conn(), item.tid):
                return self._finalize_without_spawn(item, ("CANCELLED", "CANCEL_USER", -1), None)
        except Exception as exc:  # noqa: BLE001
            return self._error_before_spawn(item, exc)
        self._spawn(item, snap, argv, script_real, contexto)

    def _prevalidate(self, item):
        """Devolve (snap, argv, script_real, contexto) ou None (ticket ja finalizado PRECHECK_FAILED).

        CR-011: o conteudo do arquivo nao e conferido (sem hash); o caminho pode ter link simbolico."""
        conn = self._conn()
        ticket = self.repo.get_ticket(conn, item.tid)
        item.ticket = ticket
        contexto = self.repo.execution_context(conn, ticket)
        script, ambiente = contexto["script"], contexto["environment"]
        try:
            snap, argv, script_real = params_compiler.validate_snapshot(ticket["submitted_params"],
                                                                       self._cfg_snapshot())
        except params_compiler.SnapshotError as exc:
            codigo = exc.reason[len("PATH_GUARD_"):] if exc.reason.startswith("PATH_GUARD_") else exc.reason
            return self._refuse(item, codigo)
        if script is None or snap["path_file"] != script["path_file"] or snap["interpreter"] != script["interpreter"]:
            return self._refuse(item, "CADASTRO_MUDOU")
        if script.get("active") != "Y":
            return self._refuse(item, "SCRIPT_INACTIVE")
        if not self.repo.active_homologated_script(conn, script["id"], ticket["environment"]):
            return self._refuse(item, "NAO_HOMOLOGADO")
        if ambiente is None or ambiente.get("active") != "Y":
            return self._refuse(item, "ENVIRONMENT_INACTIVE")
        ok, _motivo = rbac.can_execute(contexto["ctx"], script, ambiente, contexto["homologacoes"])
        if not ok:
            return self._refuse(item, "NO_PERMISSION")
        return snap, argv, script_real, contexto

    def _cfg_snapshot(self):
        agente = self.cfg.agent

        class _Cfg(object):
            interpreters = dict(agente.interpreters)
            dirs_sss = _sss_dirs(self.cfg)
        return _Cfg()

    def _refuse(self, item, codigo):
        item.log.warning("pre-validacao recusada: %s", codigo, extra={"action": "PRECHECK"})
        self._finalize_without_spawn(item, _PRECHECK, "pre-validacao recusada: %s (agente %s)" % (codigo, self.agent_id))
        return None

    def _error_before_spawn(self, item, exc):
        """Erro de banco antes do spawn (CR-008, R-07): rede ou prazo devolvem; o resto e PRECHECK_FAILED."""
        if db_conn.is_network_error(exc) or db_conn.is_timeout(exc):
            item.log.warning("banco indisponivel antes do spawn: devolucao (%s)", exc.__class__.__name__,
                             extra={"action": "PRECHECK"})
            self.connection.notify_error(exc)
            self.executions.pop(item.tid, None)
            self.pending_returns.add(item.tid)
            if self.connection.get_connection() is not None:
                self._return_to_queue(item.tid, item.log)
            return None
        pfx, num = db_conn.classify_error(exc)
        if pfx:
            linha = "ERRO_BANCO: %s-%05d" % (pfx, num)
        else:
            linha = "pre-validacao recusada: %s (agente %s)" % (exc.__class__.__name__, self.agent_id)
        item.log.error("falha antes do spawn: %s", linha, exc_info=not pfx, extra={"action": "PRECHECK"})
        self._finalize_without_spawn(item, _PRECHECK, linha)
        return None

    def _finalize_without_spawn(self, item, resultado, linha_sss):
        """Finaliza o ticket que nao chegou a iniciar (PRECHECK_FAILED ou CANCELLED), com a linha [SSS]."""
        conn = self._conn()
        if linha_sss:
            self._linha_sss(conn, item.tid, linha_sss)
        item.result = resultado
        item.phase = _Item.FINALIZAR
        item.flush_ok = True
        self._finalize_execution_without_process(item)

    def _finalize_execution_without_process(self, item):
        try:
            gravou = self.repo.finalize(self._conn(), item.tid, self.agent_id, *item.result)
        except Exception as exc:  # noqa: BLE001 - finalizacao pendente
            item.finalize_pending = True
            item.log.warning("finalizacao pendente (%s)", exc.__class__.__name__, extra={"action": "FINALIZAR"})
            self.connection.notify_error(exc)
            return
        if not gravou:
            item.log.error("OWNERSHIP_LOST: o ticket ja nao e deste agente", extra={"action": "FINALIZAR"})
        else:
            item.log.info("ticket finalizado sem execucao: %s/%s", item.result[0], item.result[1],
                          extra={"action": "FINALIZAR"})
        self.executions.pop(item.tid, None)
        if item.execution is not None:
            self._clean(item.tid, item.execution.work_dir_ticket, item.execution)

    def _spawn(self, item, snap, argv, script_real, contexto):
        agente = self.cfg.agent
        ticket = item.ticket
        usuario = env_builder.exec_user(self.cfg, ticket["environment"])
        rotulo = "SSS-%s-%s" % (self.agent_id, item.tid)
        try:
            work_dir_ticket = executor.prepare_directory(agente.work_dir, item.tid, startup_concluido=True)
            fd, caminho = executor.open_log(self.cfg.logging.log_dir, ticket["environment"], snap["script_nome"],
                                             item.started_at, item.tid, snap.get("script_id"))
        except Exception as exc:  # noqa: BLE001 - CR-007 R-17: sem arquivo de log, a causa vai para o CLOB
            item.log.error("falha antes do spawn: %s", exc, extra={"action": "SPAWN"})
            return self._finalize_without_spawn(item, _FINAL["SPAWN_ERROR"], "falha ao iniciar: %s (agente %s)" % (
                exc.__class__.__name__, self.agent_id))
        timeout = contexto["script"].get("timeout_s") or agente.script_timeout_s
        conexao = None
        saida = None
        entrada = None
        try:
            if agente.input_dir:
                # CR-014 (README §8.14): pasta permanente do script no ambiente, com o nome do snapshot.
                entrada = log_paths.input_dir(agente.input_dir, ticket["environment"], snap["script_nome"],
                                                   snap.get("script_id"))
            if agente.output_dir:
                # CR-012 (README §8.13): pasta de saida com as partes do log e o mesmo minuto.
                base, relativo = log_paths.output_dir(agente.output_dir, ticket["environment"], snap["script_nome"],
                                                        item.started_at, item.tid, snap.get("script_id"))
                saida = output_phase.Output(item.tid, base, relativo, usuario, work_dir_ticket)
            ticket_env = dict(ticket, started_at=item.started_at)
            env = env_builder.build(self.cfg, self.secrets, ticket_env, contexto["environment"], script_real,
                                        work_dir_ticket, dict(os.environ), self.plat.NAME, snapshot=snap,
                                        agendamento=contexto["agendamento"], caminho_log=caminho,
                                        timeout_seg=timeout, hostname=self.hostname, versao=sss_config.SSS_VERSION,
                                        pasta_saida=saida.folder if saida else None,
                                        pasta_entrada=os.path.join(*entrada) if entrada else None)
            conexao = env.get(env_builder.CONNECTION_VAR)
        except Exception as exc:  # noqa: BLE001 - CR-007 R-17: SPAWN_ERROR
            ex = executor.failure_before_spawn(fd, item.tid, exc, rotulo, work_dir_ticket)
            return self._after_start(item, ex, snap, conexao)
        ex = executor.start(item.tid, argv, fd, env, work_dir_ticket, usuario, agente.exec_work_dir,
                              dict(self.plat.DEFAULT_RLIMITS), rotulo,
                              saida=(saida.base, saida.relative) if saida else None, entrada=entrada)
        if not ex.spawn_error:
            item.output = saida
        item.timeout_s = timeout
        self._after_start(item, ex, snap, conexao)

    def _after_start(self, item, ex, snap, conexao):
        item.execution = ex
        item.start = self.clock()
        if ex.log_path:
            item.pump = log_pump.Pump(
                ex.log_path, item.tid, log_pump.ticket_masker(self._fixed_masker, conexao, snap),
                self.cfg.logging.max_log_size_bytes, self.cfg.logging.max_local_log_size_bytes, 0,
                self.supplementary_unit)
            self.pumps[item.tid] = item.pump
        if ex.spawn_error and not ex.failed_after_spawn:
            item.reason = "SPAWN_ERROR"
            item.phase = _Item.FINALIZAR
            return
        if ex.failed_after_spawn:
            # CR-008, R-01: o grupo ja recebeu SIGTERM; acompanhado ate morrer, sem registrar_pid.
            item.reason = "SPAWN_ERROR"
            item.phase = _Item.ENCERRANDO
            return
        item.phase = _Item.RODANDO
        item.pid_pending = True
        self._register_pid(item)

    def _register_pid(self, item):
        ex = item.execution
        try:
            ok = self.repo.register_pid(self._conn(), item.tid, self.agent_id, ex.pid, ex.identity)
        except Exception as exc:  # noqa: BLE001 - PID pendente (CR-008, R-08)
            if not item.pid_warned:
                item.pid_warned = True
                item.log.warning("PID pendente (%s)", exc.__class__.__name__, extra={"action": "SPAWN"})
            self.connection.notify_error(exc)
            return
        item.pid_pending = False
        if not ok:
            self._stop(item, "OWNERSHIP_LOST")
        else:
            item.log.info("script iniciado (pid %s)", ex.pid, extra={"action": "SPAWN"})

    # ---------------------------------------------------- parada

    def stop_all(self, modo, registro_perdido=False):
        """Fim da parada (README §8.11): TERMINATE nos grupos que restarem (todos, no TERMINATE; os que passaram
        de shutdown_grace_s, no DRAIN), finalizados SHUTDOWN; flush dos logs, PARADO com AGENT_STOP, remocao
        do .stop, recursos liberados e saida 0."""
        self.log.warning("encerramento %s: %d execucao(oes) local(is)", modo, len(self.executions),
                         extra={"action": "PARADA"})
        # CR-012: a saida em andamento e abandonada (a pasta fica no disco; GRAVANDO vira FALHOU na subida).
        self._stopping = True
        self._terminating = True
        for tid, (_saida, ex, log) in sorted(getattr(self, "outputs", {}).items()):
            log.warning("saida abandonada na parada", extra={"action": "PARADA"})
            self._clean(tid, ex.work_dir_ticket, ex)
        if hasattr(self, "outputs"):
            self.outputs.clear()
        for item in list(self.executions.values()):
            self._stop(item, "SHUTDOWN")
        limite = self.clock() + self.cfg.agent.kill_grace_s + 5
        while (self.executions or self.stopping) and self.clock() < limite:
            self._iteration()
            if self.executions or self.stopping:
                self._wait(0.05)
        conn = self._conn() if self.connection.ensure() else None
        if conn is not None and not registro_perdido:
            try:
                self.repo.stop_agent(conn, self.agent_id, self.hostname, self.pid, modo)
            except Exception as exc:  # noqa: BLE001 - a parada segue
                self.log.error("registro de parada falhou: %s", exc, extra={"action": "PARADA"})
        stop = os.path.join(self.cfg.agent.work_dir, "sss-%s.stop" % self.agent_id)
        if os.path.exists(stop):
            os.unlink(stop)
        self.release_resources()
        return 0



class _Item(object):
    """Um ticket no mapa local do agente (README §8.7)."""

    RESERVADO = "RESERVADO"
    RODANDO = "RODANDO"
    ENCERRANDO = "ENCERRANDO"
    FINALIZAR = "FINALIZAR"

    def __init__(self, tid, started_at, log):
        self.tid = tid
        self.started_at = started_at
        self.log = log
        self.phase = _Item.RESERVADO
        self.ticket = None
        self.execution = None
        self.pump = None
        self.reason = None
        self.result = None
        self.start = None
        self.timeout_s = None
        self.flush_ok = False
        self.pid_pending = False
        self.pid_warned = False
        self.finalize_pending = False
        self.output = None  # CR-012: fase_saida.Saida quando o agente tem output_dir
