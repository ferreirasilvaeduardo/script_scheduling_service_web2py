# -*- coding: utf-8 -*-
"""Daemon do agente: inicializacao fail-fast, startup check e laco (README §8.1-§8.12; CR-007 R-01 a R-04, R-11,
R-17, R-23, R-28; CR-008 R-01, R-02, R-07, R-08, R-09, R-11, R-17, R-25, R-26, E4).

Laco single-threaded com tres prazos monotonicos e nenhuma espera dentro das operacoes: a unica espera e a
de entre iteracoes (injetada, no maximo 1 s). Encerramentos pela maquina de estados do executor. NODE_OFFLINE,
desdobro, fencing completo e DRAIN ficam para o F8.4 (pontos de extensao).
A pasta de saida do ticket (CR-012, README §8.13) passa pela maquina de output_phase: empacotar antes do flush
final e gravar depois da finalizacao, fora do mapa de execucoes.

Python puro (sem web2py): o processo inteiro precisa de uma unica thread antes do primeiro spawn, por causa
do preexec_fn (README §3.1, C10). Toda primitiva de SO vem de `os_platform`; o banco, do `db_conn` e dos
repositorios internos do daemon. Cada passo que falha registra CRITICAL e sai com um codigo proprio.
"""
import datetime
import json
import logging
import os
import socket
import threading
import time

from sss.persistence import db_conn
from sss.scheduler import schedule_expansion
from sss.scheduler import env_builder
from sss.scheduler import executor
from sss.scheduler import input_phase
from sss.scheduler import output_phase
from sss.scheduler import log_pump
from sss.core import params_compiler
from sss.config import log_paths
from sss.platform import os_platform
from sss.platform import path_guard
from sss.core import rbac
from sss.persistence.contracts import repo_inputs
from sss.config import sss_config
from sss.persistence.oracle.scheduler_schedules import RepoSchedulerSchedules
from sss.persistence.oracle.scheduler_queue import DuplicateAgent, RegistrationLost, RepoSchedulerQueue
from sss.persistence.oracle.scheduler_log import RepoSchedulerLog
from sss.persistence.oracle.scheduler_input import RepoSchedulerInput
from sss.persistence.oracle.scheduler_output import RepoSchedulerOutput

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

# Motivos de encerramento -> (status, status_reason, return_code) do README §5.2.
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

    def __init__(self, code, reason):
        SystemExit.__init__(self, code)
        self.code = code
        self.reason = reason


class _Log(logging.LoggerAdapter):
    """Toda linha com agente, ticket e acao (README §13)."""

    def process(self, msg, kwargs):
        extra = dict(self.extra)
        extra.update(kwargs.pop("extra", None) or {})
        kwargs["extra"] = extra
        return msg, kwargs


def _sss_dirs(cfg):
    """Pastas do SSS onde nenhum script pode ficar (SSS_DIR, README §8.5; o interpretador nao e conferido
    contra elas desde o CR-026, risco aceito, README §14). CR-014 e CR-019:
    inclui output_dir, input_dir e script_work_dir, que o usuario de execucao grava (um script ali poderia ser
    trocado por outro)."""
    agent = cfg.agent
    return tuple(d for d in (cfg.logging.log_dir, agent.work_dir, agent.exec_work_dir,
                             getattr(agent, "output_dir", None), getattr(agent, "input_dir", None),
                             getattr(agent, "script_work_dir", None)) if d)


def _read_state(folder, name, plat):
    try:
        return plat.read_state(os.path.join(folder, name))
    except (OSError, ValueError):  # estado ilegivel: tratado como ausente, com o rastro preservado
        return None


class Agent(object):
    """Daemon de um no agente. inicializar() executa os passos 1 a 9 do README §8.12, em ordem."""

    def __init__(self, cfg=None, secrets=None, plat=None, connection=None, repo=None, repo_log=None,
                 clock=None, wall_clock=None, hostname=None, pid=None, load_config=None,
                 load_secrets=None, repo_output=None, repo_schedules=None, repo_input=None):
        self.cfg = cfg
        self.secrets = secrets
        self.plat = plat or os_platform
        self.connection = connection
        self.repo = repo
        self.repo_log = repo_log
        self.repo_output = repo_output
        self.repo_schedules = repo_schedules
        # CR-020c: entregas da pasta de entrada pela tela e o retrato da pasta.
        self.repo_input = repo_input
        self.expansion = None
        self.clock = clock or time.monotonic
        self.wall_clock = wall_clock or time.time
        self.hostname = hostname or socket.gethostname()
        self.pid = pid or os.getpid()
        self._load_config = load_config or (lambda: sss_config.get_config(log_name="sss_scheduler"))
        self._load_secrets = load_secrets
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

    def _fail(self, code, reason, *args):
        text = reason % args if args else reason
        self.log.critical("Subida abortada: %s", text, extra={"action": "INICIO"})
        raise StartupFailure(code, text)

    @property
    def agent_id(self):
        return self.cfg.agent.agent_id

    def _conn(self):
        return self.connection.get_connection()

    def _exec_user(self, environment):
        return dict(self.cfg.agent.exec_users or ()).get(environment) or None

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
            except sss_config.ConfigError as exc:  # get_config ja registrou o CRITICAL (README §12.1)
                raise StartupFailure(EXIT_CONFIG, str(exc))
        agent = self.cfg.agent
        self.log.extra["agent"] = agent.agent_id
        try:
            sss_config.check_encoding()
        except sss_config.ConfigError as exc:
            self._fail(EXIT_CONFIG, "%s", exc)
        if not self.plat.locale_available(agent.child_locale):
            self._fail(EXIT_CONFIG, "child_locale %s nao consta em locale -a (CR-007, R-17)", agent.child_locale)
        db_conn.connection_budget_s(self.cfg.oracle.dsn, sss_config.call_timeout_s(self.cfg.oracle.call_timeout_ms))
        # Conferencia entre nos no E2E (README §8.9, "Mesmos tempos em todos os nos").
        self.log.info("tempos do fencing: fence_timeout_s=%s node_offline_timeout_s=%s",
                      agent.fence_timeout_s, agent.node_offline_timeout_s)

    def _step3_secrets(self):
        if self.secrets is not None:
            return
        try:
            load = self._load_secrets or (
                lambda: sss_config.load_secrets(self.cfg.secrets.secrets_file, cfg=self.cfg, role="agent"))
            self.secrets = load()
        except sss_config.ConfigError as exc:
            self._fail(EXIT_SECRETS, "secrets.cfg invalido: %s", exc)

    def _step4_directories(self):
        agent = self.cfg.agent
        for name, path in (("log_dir", self.cfg.logging.log_dir), ("work_dir", agent.work_dir)):
            code = self.plat.validate_restricted_dir(path)
            if code:
                self._fail(EXIT_DIRECTORIES, "%s %s recusado: %s", name, path, code)
        # CR-026: sem [agent] interpreters; o interpretador e conferido a cada ticket (#!, digitado, cadastro).
        # CR-028: [agent] helper_path vale para todas as chamadas do helper pelo sudo, inclusive no DEV com
        # exec_users (revisao do CR-028, M4); a conferencia do helper e do sudoers so roda fora de DEV.
        set_helper = getattr(self.plat, "set_helper", None)
        helper_path = getattr(agent, "helper_path", None)
        if set_helper and helper_path:
            set_helper(helper_path)
        if self.cfg.app.sss_env != "DEV":
            failures = self.plat.validate_execution(agent.exec_users, agent.exec_work_dir,
                                                    helper=agent.helper_path)
            for failure in failures:
                self.log.critical("execucao fora de DEV: %s", failure)
            if failures:
                self._fail(EXIT_DIRECTORIES, "%d falha(s) na conferencia do helper e do sudoers", len(failures))
        self._check_user_dir("output_dir", "pasta de saida", "pastas de saida (CR-012)")
        self._check_user_dir("input_dir", "pasta de entrada", "pastas de entrada (CR-014)")
        self._check_user_dir("script_work_dir", "pasta de trabalho", "pastas de trabalho (CR-019)")
        self._check_script_base_dir()

    def _check_script_base_dir(self) -> None:
        """CR-023 (D5): pasta base inexistente so e avisada; os tickets com caminho relativo dao NOT_FOUND."""
        base = getattr(self.cfg.agent, "script_base_dir", None)
        if not base:
            self.log.info("sem pasta base dos scripts ([agent] script_base_dir): so caminho absoluto",
                          extra={"action": "INICIO"})
        elif os.path.isdir(base):
            self.log.info("pasta base dos scripts: %s", base, extra={"action": "INICIO"})
        else:
            self.log.warning("pasta base dos scripts %s nao existe: scripts com caminho relativo vao terminar "
                             "em PRECHECK_FAILED (NOT_FOUND)", base, extra={"action": "INICIO"})

    def _check_user_dir(self, key, name, plural):
        """README §8.12 passo 4: a pasta da chave fora das pastas do sistema; fora de DEV, a pasta de cada
        ambiente atendido do usuario de execucao dele, sem escrita de grupo nem de outros (CR-012, CR-014, CR-019)."""
        agent = self.cfg.agent
        folder = getattr(agent, key, None)
        if not folder:
            return
        code = self.plat.validate_restricted_dir(folder)
        if code:
            self._fail(EXIT_DIRECTORIES, "%s %s recusado: %s", key, folder, code)
        if self.cfg.app.sss_env == "DEV" and not agent.exec_users:
            return
        pairs = [(os.path.join(folder, log_paths.environment_dir(env)), self._exec_user(env))
                 for env in agent.environments if self._exec_user(env)]
        failures = self.plat.validate_output_dirs(pairs)
        for failure in failures:
            self.log.critical("%s: %s", name, failure)
        if failures:
            self._fail(EXIT_DIRECTORIES, "%d falha(s) nas %s", len(failures), plural)

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
                selection = db_conn.select_driver(self.cfg, self.secrets)
                db_conn.initialize(selection, self.cfg)
                self.connection = db_conn.ResilientConnection(self.cfg, self.secrets, role="agent")
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
            if self.repo_input is None:
                self.repo_input = RepoSchedulerInput.from_config(self.cfg)
            now_db = db_conn.db_now(conn)
            local = self.wall_clock()
            divergence = abs((datetime.datetime.fromtimestamp(local) - now_db).total_seconds())
            if divergence > CLOCK_SKEW_S:
                self.log.warning("relogio local diverge do SYSDATE em %d s (README §7.1)", divergence)
            db_conn.check_schema_version(conn, owner=self.cfg.oracle.owner.strip(),
                                            prefix=self.cfg.oracle.table_prefix.strip())
            self.supplementary_unit = self.repo_log.supplementary_unit(conn)
        except StartupFailure:
            raise
        except Exception as exc:  # noqa: BLE001 - driver, versao do esquema ou leitura: CRITICAL
            self._fail(EXIT_DATABASE, "banco: %s", exc)

    def _step7_registration(self):
        agent = self.cfg.agent
        critical = sss_config.critical_config(self.cfg)
        start = self.clock()
        try:
            self.agent_db_id = self.repo.register_agent(self._conn(), {
                "code": agent.agent_id, "hostname": self.hostname, "pid": self.pid,
                "version": sss_config.SSS_VERSION, "environments": ",".join(agent.environments),
                "platform": self.plat.NAME,
                "script_base_dir": getattr(agent, "script_base_dir", None),
                "critical_config": critical, "node_offline_timeout_s": agent.node_offline_timeout_s,
            }, self.plat.process_exists)
            divergent = self.repo.check_config(self._conn(), agent.agent_id, critical,
                                                    agent.node_offline_timeout_s)
        except DuplicateAgent as exc:
            self._fail(EXIT_REGISTRATION, "agent_id duplicado: %s", exc)
        except Exception as exc:  # noqa: BLE001
            self._fail(EXIT_REGISTRATION, "registro do agente: %s", exc)
        if divergent:
            for code, other in divergent:
                self.log.critical("config_criticos diverge do agente %s: local=%s remoto=%s", code, critical, other)
            self._fail(EXIT_REGISTRATION, "configuracao critica diferente da dos outros agentes (CR-007, R-23)")
        self.last_hb_ok = start

    def _step8_environments(self):
        try:
            active, nonexistent = self.repo.active_environments(self._conn(), self.cfg.agent.environments)
        except Exception as exc:  # noqa: BLE001
            self._fail(EXIT_ENVIRONMENTS, "leitura dos ambientes: %s", exc)
        if nonexistent:
            self._fail(EXIT_ENVIRONMENTS, "ambientes atendidos inexistentes: %s", ", ".join(nonexistent))
        for name in sorted(set(self.cfg.agent.environments) - set(active)):
            self.log.warning("ambiente atendido %s inativo: ignorado ate ser reativado", name)
        self.active_environments = active

    def _check_single_thread(self):
        if threading.active_count() != 1:
            names = ", ".join(sorted(t.name for t in threading.enumerate()))
            self._fail(EXIT_THREADS, "o processo tem %d threads antes do primeiro spawn (%s); o preexec_fn "
                                       "exige thread unica (README §3.1)", threading.active_count(), names)

    # -------------------------------------------------------- startup check

    def _local_dirs(self):
        """{ticket_id: pasta} das pastas work_dir/ticket_<id> (nao segue links)."""
        work = self.cfg.agent.work_dir
        dirs = {}
        for name in sorted(os.listdir(work)):
            path = os.path.join(work, name)
            suffix = name[len(_DIR_PREFIX):]
            if name.startswith(_DIR_PREFIX) and suffix.isdigit() and os.path.isdir(path) \
                    and not os.path.islink(path):
                dirs[int(suffix)] = path
        return dirs

    def _step9_startup_check(self):
        """O disco do agente e a fonte de verdade sobre o que ele iniciou (README §8.12 passo 9)."""
        try:
            self._startup_check()
        except StartupFailure:
            raise
        except Exception as exc:  # noqa: BLE001
            self._fail(EXIT_STARTUP, "startup check: %s", exc)

    def _startup_check(self):
        agent = self.cfg.agent
        conn = self._conn()
        running = dict((t["id"], t) for t in self.repo.agent_running_tickets(conn, self.agent_id))
        dirs = self._local_dirs()
        results = {}
        for tid, dir_value in sorted(dirs.items()):
            log = _Log(_log, {"agent": self.agent_id, "ticket": tid, "action": "STARTUP"})
            proc = _read_state(dir_value, executor.PROC, self.plat)
            spawn = _read_state(dir_value, executor.SPAWN, self.plat)
            results[tid] = _read_state(dir_value, executor.RESULT, self.plat)
            user = (proc or spawn or {}).get("exec_user")
            if proc is not None:
                self._reopen(tid, dir_value, proc, user, log)
            elif spawn is not None:
                # Talvez iniciado (CR-008, R-01): nunca volta a fila. Unica espera da subida (kill_grace_s).
                base = os.path.join(agent.exec_work_dir, user) if user else agent.work_dir
                if self.plat.stop_ticket(base, tid, user, agent.kill_grace_s) == "UNSUPPORTED":
                    # O processo pode seguir vivo: a pasta fica como rastro (CR-008, R-26).
                    self.preserved.add(tid)
                    log.warning("TALVEZ_INICIADO sem meio de encerrar nesta plataforma: o processo fica com o "
                                "usuario de execucao")
                log.error("TALVEZ_INICIADO: .sss_spawn sem .sss_proc")
        for tid, ticket in sorted(running.items()):
            log = _Log(_log, {"agent": self.agent_id, "ticket": tid, "action": "STARTUP"})
            if tid in dirs:
                res = results.get(tid)
                if res is not None:
                    self._finalize(tid, res["status"], res["status_reason"], res["return_code"], log,
                                    "resultado local gravado antes da queda")
                else:
                    self._finalize(tid, "FAILED", "ORPHAN_PROCESS", -2, log, "processo sem acompanhamento")
            elif ticket["process_id"] is None:
                outcome = self.repo.return_to_queue(conn, tid, self.agent_id)
                (log.warning if outcome != "PERDIDO" else log.info)("ticket sem pasta local e sem PID: %s",
                                                                     outcome)
            else:
                self._finalize(tid, "FAILED", "ORPHAN_PROCESS", -2, log, "PID sem pasta local")
        for tid, dir_value in sorted(dirs.items()):
            if tid in self.stopping or tid in self.preserved:
                continue
            self._clean_dir(tid, dir_value)
        # CR-012 (README §8.13): saidas que ficaram em gravacao numa queda viram FALHOU; a pasta fica no disco.
        failed = self.repo_output.fail_agent_writing(conn, self.agent_id)
        conn.commit()
        if failed:
            self.log.warning("%d saida(s) em gravacao marcada(s) FALHOU na subida", failed,
                             extra={"action": "STARTUP"})
        # CR-020c (README §8.14): temporarios de entregas interrompidas; as entregas seguem PENDING.
        removed = input_phase.clean_leftovers(agent.work_dir)
        if removed:
            self.log.warning("%d temporario(s) de entrega da pasta de entrada removido(s) na subida", removed,
                             extra={"action": "STARTUP"})

    def _reopen(self, tid, folder, proc, user, log):
        process = self.plat.reopen_group(proc)
        if process is None:
            return
        execution = executor.Execution(tid, folder, user,
                                     os.path.join(self.cfg.agent.exec_work_dir, user) if user else None, None)
        execution.process = process
        execution.pid = process.pid
        execution.identity = process.identity
        executor.request_stop(execution, self.clock(), grace_s=self.cfg.agent.kill_grace_s)
        if execution.no_identity:
            self.preserved.add(tid)  # CR-008, R-26: o unico rastro do processo fica
        elif not executor.advance_stop(execution, self.clock()):
            self.stopping[tid] = execution  # o laco avanca o encerramento e limpa a pasta depois
            log.warning("grupo do ticket em encerramento na subida (pid %s)", process.pid)

    def _finalize(self, tid, status, reason, rc, log, detail):
        """Finaliza o ticket RUNNING deste agente com a linha [SSS] no log (README §5.2)."""
        conn = self._conn()
        self._linha_sss(conn, tid, "%s: %s (agente %s)" % (reason, detail, self.agent_id))
        if not self.repo.finalize(conn, tid, self.agent_id, status, reason, rc):
            log.warning("OWNERSHIP_LOST na subida: o ticket ja nao era deste agente")
        elif status == "SUCCESS":
            log.info("ticket finalizado na subida pelo resultado local: %s/%s", status, reason)
        else:
            log.error("ticket finalizado na subida: %s/%s (%s)", status, reason, detail)

    def _linha_sss(self, conn, tid, text):
        ticket = self.repo.get_ticket(conn, tid)
        if ticket is None:
            return
        try:
            self.repo_log.append_chunk(conn, tid, self.agent_id, int(ticket.get("log_offset_chars") or 0),
                                 "[SSS] %s\n" % text)
            conn.commit()
        except Exception as exc:  # noqa: BLE001 - a linha e informativa; a finalizacao segue
            conn.rollback()
            _log.warning("linha [SSS] nao gravada no log do ticket (%s)", exc.__class__.__name__,
                         extra={"agent": self.agent_id, "ticket": tid, "action": "STARTUP"})

    def _clean_dir(self, tid, folder):
        execution = executor.Execution(tid, folder, None, None, None)
        state = _read_state(folder, executor.PROC, self.plat) or _read_state(folder, executor.SPAWN, self.plat) or {}
        user = state.get("exec_user")
        if user:
            execution.exec_user = user
            execution.base_dir = os.path.join(self.cfg.agent.exec_work_dir, user)
        try:
            executor.clean(execution)
        except Exception as exc:  # noqa: BLE001 - a pasta fica para a proxima subida
            self.preserved.add(tid)
            _log.warning("pasta do ticket nao removida na subida (%s)", exc.__class__.__name__,
                         extra={"agent": self.agent_id, "ticket": tid, "action": "STARTUP"})

    # ======================================================================
    # Laco (README §8.1)
    # ======================================================================

    def prepare_loop(self, wait):
        """Estado do laco: mapa local, bombas do log, rodada do pump e os tres prazos.

        esperar(segundos): a unica espera do daemon, entre iteracoes (no maximo 1 s); o run_scheduler injeta a
        real e os testes, um duble. Nenhuma operacao do laco espera (CR-007, R-04)."""
        agent = self.cfg.agent
        self.executions = {}
        self.pumps = {}
        self.pending_returns = set()
        # CR-012: saidas a gravar depois da finalizacao do ticket {tid: (Saida, Execucao, log)}.
        self.outputs = {}
        # CR-020c: a entrega da pasta de entrada em andamento (input_phase.Delivery) e os retratos com falha.
        self.delivery = None
        self._listing_retry = {}
        self._input_warned_until = 0.0
        # Parada (README §8.11; F8.4d): _parando suspende claim e desdobro; _terminando abandona a saida em
        # andamento. DRAIN liga so o primeiro ate shutdown_grace_s; TERMINATE liga os dois.
        self._stopping = False
        self._terminating = False
        self._drain_until = None
        # Self-fencing e NODE_OFFLINE (F8.4c; README §8.8 e §8.9).
        self.fenced = False
        self._clock_ref = None          # (SYSDATE, monotonico) do ultimo SYSDATE lido
        self._node_offline_suspended_until = None
        self.round = log_pump.Round(self.pumps, self.clock, agent.heartbeat_interval_s / 2.0)
        self._wait = wait
        now = self.clock()
        self.deadlines = {"rapido": now, "heartbeat": now, "orquestrador": now}
        self._last_disk_warning = None
        self._fixed_masker = [v for v in self._secret_values() if v]
        self.exit_code = 0
        return self

    def _secret_values(self):
        seg = self.secrets
        values = [getattr(seg, "oracle_password", None), getattr(seg, "monitor_password", None)]
        for cred in (getattr(seg, "environments", None) or {}).values():
            values.append(getattr(cred, "password", None))
        return values

    def run(self, stop_event, wait=None, until=None, limit_s=None):
        """Laco principal ate a parada (flag com is_set() ou arquivo .stop). Devolve o codigo de saida.

        ate/limit_s: so para os testes (condicao de termino e prazo maximo do harness).
        """
        if not hasattr(self, "executions"):
            self.prepare_loop(wait)
        agent = self.cfg.agent
        stop = os.path.join(agent.work_dir, "sss-%s.stop" % self.agent_id)
        end = None if limit_s is None else self.clock() + limit_s
        while True:
            # Antes dos ciclos: com a parada ja pedida, o orquestrador desta volta nao pode fazer claim nem
            # desdobro (README §8.11).
            code = self._handle_stop(stop_event, stop)
            if code is not None:
                return code
            self._iteration()
            self._check_fence()
            now = self.clock()
            try:
                if now >= self.deadlines["rapido"]:
                    self.deadlines["rapido"] = now + agent.cancel_poll_interval_s
                    self._cycle("rapido", self._fast_cycle)
                    self._check_fence()
                if now >= self.deadlines["heartbeat"]:
                    self.deadlines["heartbeat"] = now + agent.heartbeat_interval_s
                    self._cycle("heartbeat", self._heartbeat_cycle)
                    self._check_fence()
                if now >= self.deadlines["orquestrador"]:
                    self.deadlines["orquestrador"] = now + agent.orchestrator_interval_s
                    if not self.fenced:
                        self._cycle("orquestrador", self._orchestrator_cycle)
                        self._check_fence()
            except RegistrationLost as exc:
                self.log.critical("REGISTRO_PERDIDO: %s; encerramento TERMINATE", exc, extra={"action": "HB"})
                self.stop_all("TERMINATE", registration_lost=True)
                return EXIT_REGISTRATION_LOST
            # Depois dos ciclos: um sinal que chegou durante eles e tratado sem esperar a proxima volta.
            code = self._handle_stop(stop_event, stop)
            if code is not None:
                return code
            if (until is not None and until()) or (end is not None and self.clock() >= end):
                return self.exit_code
            wait_s = min(self.deadlines.values()) - self.clock()
            self._wait(max(0.0, min(MAX_WAIT_INTERVAL_S, wait_s)))

    # ---------------------------------------------------- parada DRAIN (README §8.11)

    def _handle_stop(self, stop_event, stop_path):
        """Parada pedida (flag ou arquivo .stop): TERMINATE encerra ja; DRAIN suspende claim e desdobro e
        encerra ao drenar ou ao vencer shutdown_grace_s. Devolve o codigo de saida, ou None para seguir."""
        if not (stop_event.is_set() or os.path.exists(stop_path)):
            return None
        if self.cfg.agent.shutdown_mode != "DRAIN":
            return self.stop_all("TERMINATE")
        if self._drain_until is None:
            self._start_drain()
        if self._drained() or self.clock() >= self._drain_until:
            return self.stop_all("DRAIN")
        return None

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
        running = [item for item in self.executions.values() if item.phase == _Item.RODANDO]
        for item in running:
            self._stop(item, "FENCED")
        self.log.critical("FENCED: sem heartbeat confirmado ha %.0f s (fence_timeout_s %d); %d execucao(oes) "
                          "encerrada(s), claims e desdobro suspensos ate o banco voltar",
                          self.clock() - self.last_hb_ok, self.cfg.agent.fence_timeout_s, len(running),
                          extra={"action": "FENCE"})

    def _leave_fence(self):
        self.fenced = False
        self.log.warning("FENCED encerrado: heartbeat confirmado; os tickets que o agente possuia sao finalizados "
                         "pelo resultado local ou como FENCED", extra={"action": "FENCE"})

    def _clock_jump(self, sysdate):
        """CR-007 D3 / CR-008 R-10: True (e inicia a suspensao do NODE_OFFLINE) se o avanco do SYSDATE diferir do
        avanco do monotonico em mais de CLOCK_JUMP_S desde o ultimo SYSDATE lido."""
        now = self.clock()
        ref, self._clock_ref = self._clock_ref, (sysdate, now)
        if ref is None or sysdate is None:
            return False
        difference = (sysdate - ref[0]).total_seconds() - (now - ref[1])
        if abs(difference) <= CLOCK_JUMP_S:
            return False
        self._node_offline_suspended_until = now + self.cfg.agent.node_offline_timeout_s
        self.log.warning("SALTO_RELOGIO: o SYSDATE andou %.0f s diferente do relogio monotonico; NODE_OFFLINE "
                         "suspenso por %d s", difference, self.cfg.agent.node_offline_timeout_s, extra={"action": "HB"})
        return True

    def _cycle(self, name, function):
        """Um ciclo isolado: erro registrado com contexto; erro de rede descarta a conexao (reconexao no
        ciclo seguinte, uma tentativa por ciclo, sem esperar)."""
        if not self.connection.ensure():
            if name == "rapido":
                self._iteration_without_db()
            return
        try:
            function()
        except RegistrationLost:
            raise
        except Exception as exc:  # noqa: BLE001 - o laco nunca cai por um ciclo
            self.log.error("ciclo %s falhou: %s", name, exc, exc_info=not db_conn.is_network_error(exc),
                           extra={"action": name.upper()})
            self.connection.notify_error(exc)

    def _iteration_without_db(self):
        """Sem banco, os processos seguem acompanhados localmente (timeout e teto local)."""
        self._check_limits()

    # ---------------------------------------------------- toda iteracao

    def _iteration(self):
        """Maquinas de encerramento, coleta dos processos que terminaram e no maximo um flush final."""
        now = self.clock()
        for tid, ex in list(self.stopping.items()):
            if executor.advance_stop(ex, now):
                del self.stopping[tid]
                self._clean(tid, ex.work_dir_ticket)
        flush_done = False
        for tid, item in sorted(self.executions.items()):
            ex = item.execution
            if item.phase == _Item.RODANDO:
                if executor.check(ex) is not None:
                    # Terminou sozinho: o grupo e encerrado mesmo assim (R-02), prevalece o resultado real.
                    self._stop(item, None)
                continue
            if item.phase == _Item.ENCERRANDO:
                if executor.advance_stop(ex, now):
                    item.phase = _Item.FINALIZAR
                continue
            if item.phase == _Item.FINALIZAR and not self._pack(item, now):
                continue
            if item.phase == _Item.FINALIZAR and not flush_done:
                flush_done = self._finalize_execution(item)
        self._advance_outputs(now)
        self._advance_input(now)

    # ---------------------------------------------------- saida (CR-012)

    def _pack(self, item, now):
        """Etapa 1 da fase de saida, antes do flush final. True quando o ticket pode seguir para a finalizacao."""
        output = item.output
        if output is None or output.packed:
            return True
        if item.reason in ("OWNERSHIP_LOST", "SHUTDOWN") or self._terminating:
            output_phase.abandon(output, self.plat)
            return True
        agent = self.cfg.agent
        if output.process is None:
            output_phase.start_pack(output, self.plat, agent.output_max_bytes, agent.output_max_files, now)
            if not output.packed:
                return False
        elif not output_phase.advance_pack(output, self.plat, now):
            return False
        line = output_phase.log_line(output, self.agent_id, agent.output_max_files, agent.output_max_bytes)
        if line and item.execution is not None and item.execution.log_path:
            try:
                executor.append_local_line(item.execution, line)
            except OSError as exc:  # a linha e informativa; a fase segue
                item.log.warning("linha [SSS] da saida nao gravada (%s)", exc.__class__.__name__,
                                 extra={"action": "SAIDA"})
        if output.result == output_phase.EXCEEDED:
            item.log.warning("saida acima do limite (%s): a pasta fica no disco", output.reason, extra={"action": "SAIDA"})
        return True

    def _advance_outputs(self, now):
        """Etapa 2, depois da finalizacao: grava a saida sem esperar, refazendo erro de banco a cada
        cancel_poll_interval_s. Ao terminar, remove a pasta (ZIP ou vazia) e o work_dir do ticket."""
        if not self.outputs or self._terminating:
            return
        conn = self.connection.get_connection()
        if conn is None:
            return
        for tid, (output, ex, log) in sorted(self.outputs.items()):
            if now < output.next_attempt:
                continue
            try:
                outcome = output_phase.write(output, conn, self.repo_output, self.agent_id)
            except Exception as exc:  # noqa: BLE001 - pendencia refeita no proximo prazo
                output.next_attempt = now + self.cfg.agent.cancel_poll_interval_s
                if not output.pending_warned:
                    output.pending_warned = True
                    log.warning("gravacao da saida pendente (%s)", exc.__class__.__name__, extra={"action": "SAIDA"})
                self.connection.notify_error(exc)
                return
            if outcome == output_phase.CONTINUE:
                continue
            del self.outputs[tid]
            if outcome == output_phase.OWNERSHIP_LOST:
                log.error("OWNERSHIP_LOST na saida: nada gravado; a pasta fica no disco", extra={"action": "SAIDA"})
            else:
                log.info("saida %s", output.result, extra={"action": "SAIDA"})
                if output_phase.should_remove_dir(output):
                    try:
                        output_phase.remove_dir(output, self.plat)
                    except Exception as exc:  # noqa: BLE001 - fica no disco (limpeza manual, README §11.3)
                        log.warning("pasta de saida nao removida (%s)", exc.__class__.__name__,
                                    extra={"action": "SAIDA"})
            self._clean(tid, ex.work_dir_ticket, ex)

    def _stop(self, item, reason):
        """Pede o encerramento do grupo (SIGTERM, prazo, SIGKILL) sem esperar. motivo None: saida natural."""
        if item.phase != _Item.RODANDO:
            return
        ex = item.execution
        if reason is not None and executor.check(ex) is not None:
            reason = None  # o processo ja tinha terminado: prevalece o resultado real (README §5.6)
        item.reason = reason
        executor.request_stop(ex, self.clock(), grace_s=self.cfg.agent.kill_grace_s)
        item.phase = _Item.ENCERRANDO
        if reason is not None:
            item.log.warning("encerramento pedido: %s", reason, extra={"action": "ENCERRAR"})

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
        flushed = False
        if item.pump is not None and not item.flush_ok:
            flushed = True
            outcome = log_pump.final_flush(item.pump, conn, self.repo_log, self.agent_id)
            if outcome == log_pump.UNCERTAIN_CONNECTION:
                self.connection.close()
                return True
            if outcome == log_pump.OWNERSHIP_LOST:
                item.reason = "OWNERSHIP_LOST"
            item.flush_ok = True
        if item.reason == "OWNERSHIP_LOST":
            item.log.error("OWNERSHIP_LOST: o ticket ja nao e deste agente; nenhum status gravado",
                           extra={"action": "FINALIZAR"})
            self._remove(item)
            return flushed
        if item.result is None:
            item.result = self._result(item)
            executor.record_result(item.execution, *item.result)
        try:
            wrote = self.repo.finalize(conn, item.tid, self.agent_id, *item.result)
        except Exception as exc:  # noqa: BLE001 - finalizacao pendente (CR-007 R-03), refeita no ciclo rapido
            if not item.finalize_pending:
                item.log.warning("finalizacao pendente (%s)", exc.__class__.__name__, extra={"action": "FINALIZAR"})
            item.finalize_pending = True
            self.connection.notify_error(exc)
            return flushed
        if wrote:
            item.log.info("ticket finalizado: %s/%s rc=%s", *item.result, extra={"action": "FINALIZAR"})
            output = item.output
            if output is not None and output.result not in (None, output_phase.ABANDONED):
                # CR-012: a gravacao da saida segue fora do mapa de execucoes (nao ocupa vaga de claim).
                self.executions.pop(item.tid, None)
                self.pumps.pop(item.tid, None)
                self.outputs[item.tid] = (output, item.execution, item.log)
                return flushed
        else:
            item.log.error("OWNERSHIP_LOST na finalizacao: o resultado fica so no log local",
                           extra={"action": "FINALIZAR"})
        self._remove(item)
        return flushed

    def _remove(self, item):
        self.executions.pop(item.tid, None)
        self.pumps.pop(item.tid, None)
        self._clean(item.tid, item.execution.work_dir_ticket if item.execution else None,
                     item.execution)

    def _clean(self, tid, folder, execution=None):
        if not folder:
            return
        if execution is None:
            return self._clean_dir(tid, folder)
        try:
            executor.clean(execution)
        except Exception as exc:  # noqa: BLE001 - a pasta fica para a proxima subida
            _log.warning("pasta do ticket nao removida (%s)", exc.__class__.__name__,
                         extra={"agent": self.agent_id, "ticket": tid, "action": "LIMPEZA"})

    # ---------------------------------------------------- ciclo rapido

    def _fast_cycle(self):
        self._check_limits()
        if self.fenced:
            return  # em modo cercado, so o heartbeat tenta o banco (README §8.9)
        conn = self._conn()
        own = self.repo.own_sweep(conn, self.agent_id)
        for tid, item in list(self.executions.items()):
            if item.phase == _Item.RESERVADO:
                continue
            if tid not in own:
                if item.phase == _Item.RODANDO:
                    self._stop(item, "OWNERSHIP_LOST")
                elif item.phase in (_Item.ENCERRANDO, _Item.FINALIZAR) and item.reason != "OWNERSHIP_LOST" \
                        and not item.finalize_pending:
                    item.reason = "OWNERSHIP_LOST"
                continue
            if own[tid] == "Y" and item.phase == _Item.RODANDO:
                self._stop(item, "CANCEL")
        for tid in sorted(set(own) - set(self.executions) - set(self.stopping) - self.pending_returns):
            self._reconcile(tid)
        self._pending()
        if self.repo_input is not None:
            # A entrada pela tela nunca atrapalha os tickets: uma falha dela fica nela (rede segue o fluxo comum).
            try:
                self._input_cycle(conn)
            except Exception as exc:  # noqa: BLE001 - registrada no maximo uma vez por minuto
                if db_conn.is_network_error(exc):
                    raise
                now = self.clock()
                if now >= self._input_warned_until:
                    self._input_warned_until = now + 60
                    self.log.warning("ciclo da pasta de entrada falhou: %s", exc.__class__.__name__,
                                     extra={"action": "ENTRADA"})

    # ---------------------------------------------------- entrada pela tela (CR-020c)

    def _input_cycle(self, conn):
        """Atende os pedidos de retrato da pasta de entrada e pega a proxima entrega deste agente."""
        if self._stopping:
            return
        for due in self.repo_input.listings_due(self.agent_id, conn=conn):
            self._publish_listing(conn, due["environment"], due["script_id"], due["script_name"])
        if self.delivery is not None:
            return
        rows = self.repo_input.pending_deliveries(self.agent_id, limit=1, conn=conn)
        if not rows:
            return
        delivery = input_phase.Delivery(rows[0], self.cfg.agent.work_dir)
        if not self.cfg.agent.input_dir or delivery.environment not in self.cfg.agent.environments:
            self.log.error("entrega %s em %s sem pasta de entrada neste agente ([agent] input_dir ou ambiente)",
                           delivery.id, delivery.environment, extra={"action": "ENTRADA"})
            delivery.fail("ERROR")
        self.delivery = delivery

    def _input_place(self, environment, script_name, script_id):
        """(base, pasta do script, usuario de execucao); em DEV sem usuario, o agente cria a base e a pasta."""
        base, script_dir = log_paths.input_dir(self.cfg.agent.input_dir, environment, script_name, script_id)
        user = env_builder.exec_user(self.cfg, environment)
        if not user:
            self.plat.create_input_dir(base, script_dir)
        return base, script_dir, user

    def _publish_listing(self, conn, environment, script_id, script_name):
        """Retrato da pasta pelo helper list-input; falha registrada e nova tentativa so depois de um minuto."""
        key = (environment, script_id)
        now = self.clock()
        if self._listing_retry.get(key, 0) > now:
            return
        agent = self.cfg.agent
        if not agent.input_dir or environment not in agent.environments:
            result = {"files": [], "count": 0, "truncated": False}
        else:
            try:
                base, script_dir, user = self._input_place(environment, script_name, script_id)
                result = self.plat.list_input(base, script_dir, repo_inputs.LISTING_MAX_ITEMS, user)
            except Exception as exc:  # noqa: BLE001 - o pedido continua valendo; nova tentativa depois
                self._listing_retry[key] = now + 60
                self.log.warning("retrato da pasta de entrada de %s/%s falhou (%s)", environment, script_name,
                                 exc.__class__.__name__, extra={"action": "ENTRADA"})
                return
        self._listing_retry.pop(key, None)
        self.repo_input.save_listing(self.agent_id, environment, script_id, json.dumps(result["files"]),
                                     result["count"], "Y" if result["truncated"] else "N", conn=conn)

    def _advance_input(self, now):
        """Avanca a entrega em andamento sem esperar: baixar, gravar pelo helper e marcar (README §8.14)."""
        delivery = self.delivery
        if delivery is None or self._terminating or now < delivery.next_attempt:
            return
        try:
            if delivery.step == input_phase.DOWNLOAD:
                conn = self.connection.get_connection()
                if conn is None:
                    return
                input_phase.download(delivery, conn, self.repo_input)
            if delivery.step == input_phase.WRITE:
                if delivery.process is None:
                    try:
                        base, script_dir, user = self._input_place(delivery.environment, delivery.script_name,
                                                                   delivery.script_id)
                    except Exception as exc:  # noqa: BLE001 - pasta de entrada inutilizavel: FAILED ERROR
                        self.log.warning("entrega %s: pasta de entrada recusada (%s)", delivery.id,
                                         exc.__class__.__name__, extra={"action": "ENTRADA"})
                        delivery.fail("ERROR")
                    else:
                        input_phase.start_write(delivery, self.plat, base, script_dir, user, now)
                        if delivery.step == input_phase.WRITE:
                            return
                elif not input_phase.advance_write(delivery, self.plat, now):
                    return
            if delivery.step == input_phase.MARK:
                conn = self.connection.get_connection()
                if conn is None:
                    return
                marked = input_phase.mark(delivery, conn, self.repo_input, self.agent_id)
                input_phase.discard(delivery, self.plat)
                self.delivery = None
                if not marked:
                    self.log.error("entrega %s ja nao e deste agente: nada gravado", delivery.id,
                                   extra={"action": "ENTRADA"})
                    return
                self.log.info("entrega %s de %s em %s: %s%s", delivery.id, delivery.file_name, delivery.environment,
                              delivery.state, " (%s)" % delivery.reason if delivery.reason else "",
                              extra={"action": "ENTRADA"})
                if delivery.state == "DELIVERED":
                    self._publish_listing(conn, delivery.environment, delivery.script_id, delivery.script_name)
        except Exception as exc:  # noqa: BLE001 - entrega refeita no proximo prazo
            delivery.next_attempt = now + self.cfg.agent.cancel_poll_interval_s
            if not delivery.pending_warned:
                delivery.pending_warned = True
                self.log.warning("entrega %s pendente (%s)", delivery.id, exc.__class__.__name__,
                                 extra={"action": "ENTRADA"})
            self.connection.notify_error(exc)

    def _check_limits(self):
        now = self.clock()
        for item in list(self.executions.values()):
            if item.phase != _Item.RODANDO:
                continue
            if item.timeout_s and now - item.start > item.timeout_s:
                self._stop(item, "TIMEOUT")
            elif item.pump is not None and item.pump.local_exceeded():
                self._stop(item, "LOG_LIMIT")

    def _reconcile(self, tid):
        """Ticket RUNNING deste agente fora do mapa local (CR-007 R-03; CR-008 R-01, R-02): mesmo tratamento do
        startup check para esse ticket."""
        conn = self._conn()
        dir_value = os.path.join(self.cfg.agent.work_dir, "ticket_%d" % tid)
        log = _Log(_log, {"agent": self.agent_id, "ticket": tid, "action": "VARREDURA"})
        if os.path.isdir(dir_value) and not os.path.islink(dir_value):
            proc = _read_state(dir_value, executor.PROC, self.plat)
            spawn = _read_state(dir_value, executor.SPAWN, self.plat)
            res = _read_state(dir_value, executor.RESULT, self.plat)
            if proc is not None:
                self._reopen(tid, dir_value, proc, proc.get("exec_user"), log)
            elif spawn is not None:
                user = spawn.get("exec_user")
                base = os.path.join(self.cfg.agent.exec_work_dir, user) if user else self.cfg.agent.work_dir
                if self.plat.stop_ticket(base, tid, user, self.cfg.agent.kill_grace_s) == "UNSUPPORTED":
                    self.preserved.add(tid)
                    log.warning("TALVEZ_INICIADO sem meio de encerrar nesta plataforma")
                log.error("TALVEZ_INICIADO: .sss_spawn sem .sss_proc")
            if res is not None:
                self._finalize(tid, res["status"], res["status_reason"], res["return_code"], log,
                                "resultado local")
            else:
                self._finalize(tid, "FAILED", "ORPHAN_PROCESS", -2, log, "processo sem acompanhamento")
            if tid not in self.stopping and tid not in self.preserved:
                self._clean_dir(tid, dir_value)
            return
        ticket = self.repo.get_ticket(conn, tid)
        if ticket is not None and ticket.get("process_id") is None:
            self._return_to_queue(tid, log)
        else:
            self._finalize(tid, "FAILED", "ORPHAN_PROCESS", -2, log, "PID sem pasta local")

    def _return_to_queue(self, tid, log):
        try:
            outcome = self.repo.return_to_queue(self._conn(), tid, self.agent_id)
        except Exception as exc:  # noqa: BLE001 - devolucao pendente (CR-008, R-08)
            self.pending_returns.add(tid)
            log.warning("devolucao pendente (%s)", exc.__class__.__name__, extra={"action": "DEVOLVER"})
            self.connection.notify_error(exc)
            return
        self.pending_returns.discard(tid)
        if outcome == "DEVOLVIDO":
            log.info("devolucao: %s", outcome, extra={"action": "DEVOLVER"})
        else:
            log.warning("devolucao: %s", outcome, extra={"action": "DEVOLVER"})

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
        start = self.clock()  # CR-008, R-09: instante antes do primeiro UPDATE
        lost, sysdate = self.repo.heartbeat(conn, self.agent_id, self.hostname, self.pid, ids)
        self.last_hb_ok = start
        self._clock_jump(sysdate)
        if self.fenced:
            self._leave_fence()
        for tid in lost:
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
        agent = self.cfg.agent
        conn = self._conn()
        self.active_environments, _nonexistent = self.repo.active_environments(conn, agent.environments)
        critical = sss_config.critical_config(self.cfg)
        for code, other in self.repo.check_config(conn, self.agent_id, critical, agent.node_offline_timeout_s):
            self.log.error("CONFIG_DIVERGENTE: agente %s local=%s remoto=%s", code, critical, other,
                           extra={"action": "CONFIG"})
        self._node_offline()
        self._expansion()
        self._claims()

    def _node_offline(self):
        """Deteccao de no offline (README §8.8; F8.4c): so com o proprio heartbeat em dia (menos de
        fence_timeout_s / 2), fora do modo cercado e fora da suspensao por salto de relogio, que tambem e
        conferido na propria transacao (CR-008, R-10)."""
        agent = self.cfg.agent
        now = self.clock()
        if self.fenced or self.last_hb_ok is None or now - self.last_hb_ok >= agent.fence_timeout_s / 2.0:
            return
        if self._node_offline_suspended_until is not None:
            if now < self._node_offline_suspended_until:
                return
            self._node_offline_suspended_until = None
        marked = self.repo.mark_node_offline(self._conn(), self.agent_id, agent.node_offline_timeout_s,
                                                 self._clock_jump)
        if marked:
            self.log.info("NODE_OFFLINE: ticket(s) %s marcado(s) (heartbeat de outro agente vencido ha mais de %d s)",
                          ", ".join(str(i) for i in marked), agent.node_offline_timeout_s,
                          extra={"action": "NODE_OFFLINE"})

    def _expansion(self):
        """Desdobro dos agendamentos (README §7.5; F8.4b): uma transacao por regra, com orcamento de tempo.
        Suspenso na parada (e, no F8.4c, em modo cercado)."""
        if self._stopping or self.fenced:
            return
        if self.expansion is None:
            self.expansion = schedule_expansion.Expansion(self.repo_schedules, self.repo, self.agent_id, self.cfg.agent,
                                              self.clock)
        stats = self.expansion.run(self._conn(), keep_going=self._can_continue)
        if stats["regras"]:
            self.log.info("desdobro: %(regras)d regra(s), %(tickets)d ticket(s), %(pausas)d pausa(s), "
                          "%(puladas)d com outro agente", stats, extra={"action": "DESDOBRO"})

    def _can_continue(self):
        """Entre chamadas ao banco do desdobro e do claim: para se o fence venceu (e cerca) ou se ha parada."""
        self._check_fence()
        return not (self._stopping or self.fenced)

    def _claims(self):
        agent = self.cfg.agent
        slots = agent.max_parallel_jobs - len(self.executions)
        if slots <= 0 or not self.active_environments or not self._can_continue():
            return
        free = self.plat.free_space_mb(self.cfg.logging.log_dir)
        if free < agent.log_dir_min_free_mb:
            now = self.clock()
            if self._last_disk_warning is None or now - self._last_disk_warning >= DISK_WARNING_INTERVAL_S:
                self._last_disk_warning = now
                self.log.warning("DISCO_LOG: %d MB livres em log_dir (minimo %d): sem claim", free,
                                 agent.log_dir_min_free_mb, extra={"action": "CLAIM"})
            return
        if agent.output_dir:
            free_output = self.plat.free_space_mb(agent.output_dir)
            if free_output < agent.log_dir_min_free_mb:
                now = self.clock()
                if self._last_disk_warning is None or now - self._last_disk_warning >= DISK_WARNING_INTERVAL_S:
                    self._last_disk_warning = now
                    self.log.warning("DISCO_SAIDA: %d MB livres em output_dir (minimo %d): sem claim", free_output,
                                     agent.log_dir_min_free_mb, extra={"action": "CLAIM"})
                return
        start = self.clock()
        budget = agent.heartbeat_interval_s / 2.0
        conn = self._conn()
        # CR-026: o agente atende qualquer interpretador; a escolha e so pelo ambiente.
        for cand in self.repo.candidates(conn, self.active_environments, slots, agent.queue_aging_min):
            if len(self.executions) >= agent.max_parallel_jobs or self.clock() - start > budget \
                    or not self._can_continue():
                break
            ok, reason, started_at = self.repo.claim(conn, cand["id"], cand["script_id"], cand["environment"],
                                                     self.agent_id)
            if not ok:
                if reason == "LOCK":  # esperado e tratado: WARN com o codigo, sem stack trace (README §13, R-32)
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
        snap, argv, script_real, context = pre
        try:
            if self.repo.is_cancel_requested(self._conn(), item.tid):
                return self._finalize_without_spawn(item, ("CANCELLED", "CANCEL_USER", -1), None)
        except Exception as exc:  # noqa: BLE001
            return self._error_before_spawn(item, exc)
        self._spawn(item, snap, argv, script_real, context)

    def _prevalidate(self, item):
        """Devolve (snap, argv, script_real, contexto) ou None (ticket ja finalizado PRECHECK_FAILED).

        CR-011: o conteudo do arquivo nao e conferido (sem hash); o caminho pode ter link simbolico."""
        conn = self._conn()
        ticket = self.repo.get_ticket(conn, item.tid)
        item.ticket = ticket
        context = self.repo.execution_context(conn, ticket)
        script, environment = context["script"], context["environment"]
        notes = []
        try:
            snap, argv, script_real = params_compiler.validate_snapshot(ticket["submitted_params"],
                                                                       self._cfg_snapshot(), notes=notes)
        except params_compiler.SnapshotError as exc:
            code = exc.reason[len("PATH_GUARD_"):] if exc.reason.startswith("PATH_GUARD_") else exc.reason
            return self._refuse(item, code, notes)
        item.notes = notes
        # Snapshot v5/v6 guarda a chave logica anterior ao CR-026: compara pelo nome equivalente.
        if script is None or snap["path_file"] != script["path_file"] \
                or path_guard.registered_name(snap["interpreter"]) != script["interpreter"]:
            return self._refuse(item, "REGISTRATION_CHANGED")
        if script.get("active") != "Y":
            return self._refuse(item, "SCRIPT_INACTIVE")
        if not self.repo.active_homologated_script(conn, script["id"], ticket["environment"]):
            return self._refuse(item, "NOT_HOMOLOGATED")
        if environment is None or environment.get("active") != "Y":
            return self._refuse(item, "ENVIRONMENT_INACTIVE")
        ok, _reason = rbac.can_execute(context["ctx"], script, environment, context["homologations"])
        if not ok:
            return self._refuse(item, "NO_PERMISSION")
        return snap, argv, script_real, context

    def _cfg_snapshot(self):
        agent = self.cfg.agent

        class _Cfg(object):
            sss_dirs = _sss_dirs(self.cfg)
            script_base_dir = getattr(agent, "script_base_dir", None)
            dev = self.cfg.app.sss_env == "DEV"
            # CR-025/CR-026: os nomes (digitado e cadastro) sao buscados no PATH do proprio agente.
            search_path = os.environ.get("PATH", os.defpath)
        return _Cfg()

    def _refuse(self, item, code, notes=()):
        item.log.warning("pre-validacao recusada: %s", code, extra={"action": "PRECHECK"})
        # CR-027: as tentativas de interpretador puladas vem antes da recusa, cada uma na sua linha [SSS].
        lines = list(notes) + ["pre-validacao recusada: %s (agente %s)" % (code, self.agent_id)]
        self._finalize_without_spawn(item, _PRECHECK, "\n[SSS] ".join(lines))
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
            line = "DB_ERROR: %s-%05d" % (pfx, num)
        else:
            line = "pre-validacao recusada: %s (agente %s)" % (exc.__class__.__name__, self.agent_id)
        item.log.error("falha antes do spawn: %s", line, exc_info=not pfx, extra={"action": "PRECHECK"})
        self._finalize_without_spawn(item, _PRECHECK, line)
        return None

    def _finalize_without_spawn(self, item, result, sss_line):
        """Finaliza o ticket que nao chegou a iniciar (PRECHECK_FAILED ou CANCELLED), com a linha [SSS]."""
        conn = self._conn()
        if sss_line:
            self._linha_sss(conn, item.tid, sss_line)
        item.result = result
        item.phase = _Item.FINALIZAR
        item.flush_ok = True
        self._finalize_execution_without_process(item)

    def _finalize_execution_without_process(self, item):
        try:
            wrote = self.repo.finalize(self._conn(), item.tid, self.agent_id, *item.result)
        except Exception as exc:  # noqa: BLE001 - finalizacao pendente
            item.finalize_pending = True
            item.log.warning("finalizacao pendente (%s)", exc.__class__.__name__, extra={"action": "FINALIZAR"})
            self.connection.notify_error(exc)
            return
        if not wrote:
            item.log.error("OWNERSHIP_LOST: o ticket ja nao e deste agente", extra={"action": "FINALIZAR"})
        else:
            item.log.info("ticket finalizado sem execucao: %s/%s", item.result[0], item.result[1],
                          extra={"action": "FINALIZAR"})
        self.executions.pop(item.tid, None)
        if item.execution is not None:
            self._clean(item.tid, item.execution.work_dir_ticket, item.execution)

    def _spawn(self, item, snap, argv, script_real, context):
        agent = self.cfg.agent
        ticket = item.ticket
        item.script_path = script_real
        item.interpreter_used = argv[0] if argv else None
        user = env_builder.exec_user(self.cfg, ticket["environment"])
        label = "SSS-%s-%s" % (self.agent_id, item.tid)
        try:
            work_dir_ticket = executor.prepare_directory(agent.work_dir, item.tid, startup_concluido=True)
            fd, path = executor.open_log(self.cfg.logging.log_dir, ticket["environment"], snap["script_name"],
                                             item.started_at, item.tid, snap.get("script_id"))
        except Exception as exc:  # noqa: BLE001 - CR-007 R-17: sem arquivo de log, a causa vai para o CLOB
            item.log.error("falha antes do spawn: %s", exc, extra={"action": "SPAWN"})
            return self._finalize_without_spawn(item, _FINAL["SPAWN_ERROR"], "falha ao iniciar: %s (agente %s)" % (
                exc.__class__.__name__, self.agent_id))
        # CR-026/CR-027: as tentativas puladas (digitado, #!, troca python <-> python3) e o usado abrem o log.
        for note in getattr(item, "notes", None) or []:
            executor.sss_line(fd, note)
        executor.sss_line(fd, "interpretador usado: %s" % item.interpreter_used)
        timeout = context["script"].get("timeout_s") or agent.script_timeout_s
        connection = None
        output = None
        input_value = None
        work = None
        try:
            if agent.input_dir:
                # CR-014 (README §8.14): pasta permanente do script no ambiente, com o nome do snapshot.
                input_value = log_paths.input_dir(agent.input_dir, ticket["environment"], snap["script_name"],
                                                   snap.get("script_id"))
            if agent.output_dir:
                # CR-012 (README §8.13): pasta de saida com as partes do log e o mesmo minuto.
                base, relative = log_paths.output_dir(agent.output_dir, ticket["environment"], snap["script_name"],
                                                        item.started_at, item.tid, snap.get("script_id"))
                output = output_phase.Output(item.tid, base, relative, user, work_dir_ticket)
            if getattr(agent, "script_work_dir", None):
                # CR-019 (README §8.15): pasta de trabalho com as partes da pasta de saida e o mesmo minuto.
                work = log_paths.script_work_dir(agent.script_work_dir, ticket["environment"], snap["script_name"],
                                                 item.started_at, item.tid, snap.get("script_id"))
            ticket_env = dict(ticket, started_at=item.started_at)
            env = env_builder.build(self.cfg, self.secrets, ticket_env, context["environment"], script_real,
                                        work_dir_ticket, dict(os.environ), self.plat.NAME, snapshot=snap,
                                        schedule=context["schedule"], log_path=path,
                                        timeout_sec=timeout, hostname=self.hostname, version=sss_config.SSS_VERSION,
                                        output_dir=output.folder if output else None,
                                        input_dir=os.path.join(*input_value) if input_value else None,
                                        work_folder=os.path.join(*work) if work else None)
            connection = env.get(env_builder.CONNECTION_VAR)
        except Exception as exc:  # noqa: BLE001 - CR-007 R-17: SPAWN_ERROR
            ex = executor.failure_before_spawn(fd, item.tid, exc, label, work_dir_ticket)
            return self._after_start(item, ex, snap, connection)
        ex = executor.start(item.tid, argv, fd, env, work_dir_ticket, user, agent.exec_work_dir,
                              dict(self.plat.DEFAULT_RLIMITS), label,
                              output=(output.base, output.relative) if output else None, input_value=input_value,
                              work=work)
        if not ex.spawn_error:
            item.output = output
        item.timeout_s = timeout
        self._after_start(item, ex, snap, connection)

    def _after_start(self, item, ex, snap, connection):
        item.execution = ex
        item.start = self.clock()
        if ex.log_path:
            item.pump = log_pump.Pump(
                ex.log_path, item.tid, log_pump.ticket_masker(self._fixed_masker, connection, snap),
                self.cfg.logging.max_log_size_bytes, self.cfg.logging.max_local_log_size_bytes, 0,
                self.supplementary_unit)
            self.pumps[item.tid] = item.pump
        if ex.spawn_error and not ex.failed_after_spawn:
            item.reason = "SPAWN_ERROR"
            item.phase = _Item.FINALIZAR
            return
        if ex.failed_after_spawn:
            # CR-008, R-01: o grupo ja recebeu SIGTERM; acompanhado ate morrer, sem register_pid.
            item.reason = "SPAWN_ERROR"
            item.phase = _Item.ENCERRANDO
            return
        item.phase = _Item.RODANDO
        item.pid_pending = True
        self._register_pid(item)

    def _register_pid(self, item):
        ex = item.execution
        try:
            ok = self.repo.register_pid(self._conn(), item.tid, self.agent_id, ex.pid, ex.identity,
                                        script_path=item.script_path,
                                        interpreter_used=item.interpreter_used)
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

    def stop_all(self, mode, registration_lost=False):
        """Fim da parada (README §8.11): TERMINATE nos grupos que restarem (todos, no TERMINATE; os que passaram
        de shutdown_grace_s, no DRAIN), finalizados SHUTDOWN; flush dos logs, PARADO com AGENT_STOP, remocao
        do .stop, recursos liberados e saida 0."""
        self.log.warning("encerramento %s: %d execucao(oes) local(is)", mode, len(self.executions),
                         extra={"action": "PARADA"})
        # CR-012: a saida em andamento e abandonada (a pasta fica no disco; GRAVANDO vira FALHOU na subida).
        self._stopping = True
        self._terminating = True
        for tid, (_output, ex, log) in sorted(getattr(self, "outputs", {}).items()):
            log.warning("saida abandonada na parada", extra={"action": "PARADA"})
            self._clean(tid, ex.work_dir_ticket, ex)
        if hasattr(self, "outputs"):
            self.outputs.clear()
        # CR-020c: a entrega em andamento e abandonada sem marcar nada (segue PENDING para a proxima subida).
        if getattr(self, "delivery", None) is not None:
            input_phase.discard(self.delivery, self.plat)
            self.delivery = None
        for item in list(self.executions.values()):
            self._stop(item, "SHUTDOWN")
        limit = self.clock() + self.cfg.agent.kill_grace_s + 5
        while (self.executions or self.stopping) and self.clock() < limit:
            self._iteration()
            if self.executions or self.stopping:
                self._wait(0.05)
        conn = self._conn() if self.connection.ensure() else None
        if conn is not None and not registration_lost:
            try:
                self.repo.stop_agent(conn, self.agent_id, self.hostname, self.pid, mode)
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
        self.output = None  # CR-012: output_phase.Saida quando o agente tem output_dir
        self.script_path = None  # CR-023 (D6): caminho real executado, gravado junto com o PID
        self.interpreter_used = None  # CR-026: interpretador executado (argv[0]), gravado junto com o PID
        self.notes = []  # CR-026/CR-027: linhas [SSS] da pre-validacao (tentativas de interpretador puladas)
