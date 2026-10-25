# -*- coding: utf-8 -*-
"""Spawn e acompanhamento dos scripts (README §8.4, §8.7; CR-007 D1, R-01 a R-04, R-17; CR-008 R-01, R-26, R-36).

Unico chamador de os_platform.start_process. Nao conhece o SO (tudo vem de plataforma) nem o banco.
Nenhuma funcao espera: o encerramento e uma maquina de estados (request_stop/advance_stop)
avancada pelo laco do daemon. Saida do script direto no arquivo de log (sem pipe de saida, AGENTS §3.2).
"""
import logging
import os
import shutil
import signal
import time

from sss.config import log_paths
from sss.platform import os_platform

_log = logging.getLogger("sss_scheduler")

SPAWN = ".sss_spawn"
PROC = ".sss_proc"
RESULT = ".sss_result"
MARKERS = (SPAWN, PROC, RESULT)

RC_SPAWN_ERROR = -4
DEFAULT_GRACE_S = 10

# Fases do encerramento (CR-007, R-04).
PHASE_TERM = "TERM"
PHASE_KILL = "KILL"
PHASE_END = "END"
# Grupo vivo sem identidade legivel (ORFAO_SEM_IDENTIDADE): nunca recebe sinal; a pasta fica (CR-008, R-26).
PHASE_NO_IDENTITY = "NO_IDENTITY"

# Logs abertos por open_log e ainda nao entregues a iniciar: fd -> caminho do .log.parcial.
_open_logs = {}


class PreservedDirectory(RuntimeError):
    """work_dir/ticket_<id>/ ja existe com rastro de execucao (ou estado desconhecido): nada e apagado."""


class Execution(object):
    """Um ticket em execucao (ou que falhou ao iniciar) no mapa local do agente."""

    def __init__(self, ticket_id, work_dir_ticket, exec_user, base_dir, log_path):
        self.ticket_id = ticket_id
        self.work_dir_ticket = work_dir_ticket
        self.exec_user = exec_user
        self.base_dir = base_dir
        self.log_path = log_path
        self.process = None
        self.pid = None
        self.identity = None
        # SPAWN_ERROR: sem processo (spawn_error_info) ou com processo a encerrar (failed_after_spawn).
        self.spawn_error_info = None
        self.failed_after_spawn = False
        self.returncode = None
        self.phase = None
        self.kill_deadline = None
        self.grace_s = None
        # GRUPO_NAO_ENCERRA ja registrado (grupo vivo depois do SIGKILL e de mais um prazo).
        self.stuck = False

    @property
    def no_identity(self):
        return self.phase == PHASE_NO_IDENTITY

    @property
    def spawn_error(self):
        return self.spawn_error_info is not None

    def __repr__(self):
        return "Execucao(ticket=%s, pid=%s, fase=%s, erro=%s)" % (self.ticket_id, self.pid, self.phase,
                                                                  self.spawn_error_info)


def _agent_from_label(label):
    # rotulo = 'SSS-<agent_id>-<ticket_id>' (F8.3); o agent_id pode ter '-'.
    text = str(label or "")
    if text.startswith("SSS-"):
        text = text[4:]
    return text.rsplit("-", 1)[0] if "-" in text else text


def _sss_line(log_fd, text):
    try:
        os.write(log_fd, ("[SSS] %s\n" % text).encode("utf-8", "replace"))
    except OSError as e:
        _log.warning("falha ao gravar a linha [SSS] no log (%s)", e.__class__.__name__, extra={"action": "SPAWN"})


# -----------------------------------------------------------------------------
# Preparo
# -----------------------------------------------------------------------------

def prepare_directory(work_dir, ticket_id, startup_concluido=False):
    """Cria work_dir/ticket_<id>/ e tmp/ (0700, estado local do agente; README §8.4 passo 2).

    Pasta preexistente so e removida depois do startup check (startup_concluido) e sem nenhum marcador
    (.sss_spawn, .sss_proc, .sss_result): sem .sss_proc nao ha grupo de processo associado. Com marcador ou
    estado desconhecido, preserva a pasta e lanca PreservedDirectory (falha fechada).
    """
    path = os.path.join(work_dir, "ticket_%d" % int(ticket_id))
    if os.path.lexists(path):
        if not startup_concluido:
            raise PreservedDirectory("ticket %s: pasta preexistente antes do startup check" % ticket_id)
        if os.path.islink(path) or not os.path.isdir(path):
            raise PreservedDirectory("ticket %s: pasta de trabalho nao e um diretorio" % ticket_id)
        try:
            names = os.listdir(path)
        except OSError as e:
            raise PreservedDirectory("ticket %s: estado desconhecido (%s)" % (ticket_id, e.__class__.__name__))
        marks = [m for m in MARKERS if m in names]
        if marks:
            raise PreservedDirectory("ticket %s: pasta com estado local %s" % (ticket_id, ",".join(marks)))
        base = os_platform.final_path(work_dir)
        real = os_platform.final_path(path)
        if real == base or os.path.commonpath([real, base]) != base:
            raise PreservedDirectory("ticket %s: pasta fora do work_dir" % ticket_id)
        _log.warning("pasta de trabalho sem estado removida", extra={"ticket": ticket_id, "action": "SPAWN"})
        shutil.rmtree(real)
    os_platform.create_work_dir(path)
    os_platform.create_work_dir(os.path.join(path, "tmp"))
    return path


def open_log(log_dir, environment, script_name, started_at, ticket_id, script_id=None):
    """Abre log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>.log.parcial (O_EXCL, 0600)
    antes do spawn (CR-009: o ambiente do ticket e obrigatorio; vazio e ValueError).

    Cada pasta nova da cadeia recebe 0750 (log_paths.ensure_directory). script_name e o script_name do
    snapshot (README §6.5). Devolve (fd, caminho).
    """
    path = log_paths.partial_log_path(log_dir, environment, script_name, started_at, ticket_id, script_id)
    log_paths.ensure_directory(os.path.dirname(path))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
    _open_logs[fd] = path
    return fd, path


def build_spec(ticket_id, argv, env, rlimits, base_dir, output=None, input_value=None, work=None):
    """Especificacao do helper run (README §8.0), serializada em JSON pela plataforma.

    saida: (base, relativo) da pasta de saida do ticket (CR-012), que o helper cria antes do script.
    entrada: (base, relativo) da pasta de entrada do script (CR-014), que o helper cria se nao existir.
    work: (base, relativo) da pasta de trabalho do ticket (CR-019), que o helper cria antes do script.
    """
    spec = {
        "ticket_id": int(ticket_id),
        "argv": list(argv),
        "env": dict(env),
        "rlimits": dict((name, [int(pair[0]), int(pair[1])]) for name, pair in (rlimits or {}).items()),
        "base_dir": base_dir,
    }
    if output is not None:
        spec["output"] = {"base": output[0], "relativo": output[1]}
    if input_value is not None:
        spec["input"] = {"base": input_value[0], "relativo": input_value[1]}
    if work is not None:
        spec["work"] = {"base": work[0], "relativo": work[1]}
    return spec


# -----------------------------------------------------------------------------
# Spawn
# -----------------------------------------------------------------------------

def _spawn_failure(execution, log_fd, error, agent):
    """SPAWN_ERROR sem processo: causa no log (sem segredos) e parcial renomeado para ticket_<id>_0.log."""
    execution.spawn_error_info = error.__class__.__name__
    _sss_line(log_fd, "falha ao iniciar: %s (agente %s)" % (execution.spawn_error_info, agent))
    try:
        os.close(log_fd)
    except OSError:
        _log.warning("log_fd ja fechado", extra={"ticket": execution.ticket_id, "action": "SPAWN"})
    if execution.log_path:
        final = os.path.join(os.path.dirname(execution.log_path),
                             log_paths.run_log_name(execution.ticket_id, 0))
        try:
            os.rename(execution.log_path, final)
            execution.log_path = final
        except OSError as e:
            _log.error("rename do log de SPAWN_ERROR falhou (%s)", e.__class__.__name__,
                       extra={"ticket": execution.ticket_id, "action": "SPAWN"})
    _log.error("SPAWN_ERROR: %s", execution.spawn_error_info, extra={"ticket": execution.ticket_id, "action": "SPAWN"})
    return execution


def failure_before_spawn(log_fd, ticket_id, error, label, work_dir_ticket=None):
    """SPAWN_ERROR depois de open_log e antes de iniciar (ex.: excecao no env_builder): grava a linha [SSS],
    fecha o descritor e renomeia o parcial para ticket_<id>_0.log, como em iniciar (README §8.4, passo 3)."""
    execution = Execution(int(ticket_id), work_dir_ticket, None, None, _open_logs.pop(log_fd, None))
    return _spawn_failure(execution, log_fd, error, _agent_from_label(label))


def start(ticket_id, argv, log_fd, env, work_dir_ticket, exec_user, exec_work_dir, rlimits, label,
            output=None, input_value=None, work=None):
    """Inicia o script e devolve a Execucao (README §8.4 passos 3 a 5; CR-008 R-01).

    Ordem: .sss_spawn -> os_platform.start_process -> rename do log para ticket_<id>_<PID>.log ->
    identidade -> .sss_proc -> os.close(log_fd). Qualquer excecao antes do processo: SPAWN_ERROR com o log
    ticket_<id>_0.log. Qualquer falha depois dele: failed_after_spawn e SIGTERM ao grupo (sem esperar); o
    chamador acompanha a execucao ate o grupo acabar e so entao finaliza SPAWN_ERROR.

    saida: (base, relativo) da pasta de saida (CR-012): o helper run a cria; em DEV, a plataforma.
    entrada: (base, relativo) da pasta de entrada (CR-014), permanente: idem, so se nao existir.
    work: (base, relativo) da pasta de trabalho (CR-019): como a saida, mas fica no disco depois do ticket.
    """
    agent = _agent_from_label(label)
    dir_base = os.path.join(exec_work_dir, exec_user) if exec_user else None
    execution = Execution(int(ticket_id), work_dir_ticket, exec_user, dir_base, _open_logs.pop(log_fd, None))
    try:
        if execution.log_path is None:
            raise ValueError("log_fd nao foi aberto por abrir_log")
        if exec_user:
            spec = build_spec(ticket_id, argv, env, rlimits, dir_base, output, input_value, work)
        else:
            # DEV sem usuario de execucao: o cwd e a pasta exec de work_dir/ticket_<id> (CR-008, R-36).
            cwd = os_platform.create_work_dir(os.path.join(work_dir_ticket, "exec"))
            os_platform.create_work_dir(os.path.join(cwd, "tmp"))
            spec = {"argv": list(argv), "cwd": cwd, "env": dict(env), "rlimits": dict(rlimits or {})}
            if output is not None:
                os_platform.create_output_dir(output[0], output[1])
            if input_value is not None:
                os_platform.create_input_dir(input_value[0], input_value[1])
            if work is not None:
                os_platform.create_script_work_dir(work[0], work[1])
        os_platform.write_state(os.path.join(work_dir_ticket, SPAWN), {
            "ticket_id": int(ticket_id), "exec_user": exec_user,
            "monotonic": time.monotonic(), "wall": time.time()})
    except Exception as e:  # noqa: BLE001 - CR-007 R-17: qualquer excecao no spawn e SPAWN_ERROR
        return _spawn_failure(execution, log_fd, e, agent)

    try:
        process = os_platform.start_process(spec, log_fd, exec_user)
    except os_platform.FailureAfterSpawn as f:
        return _after_spawn_failed(execution, f.process, log_fd, f.cause, agent)
    except Exception as e:  # noqa: BLE001
        return _spawn_failure(execution, log_fd, e, agent)

    execution.process = process
    execution.pid = process.pid
    try:
        final = os.path.join(os.path.dirname(execution.log_path),
                             log_paths.run_log_name(execution.ticket_id, process.pid))
        os.rename(execution.log_path, final)
        execution.log_path = final
        execution.identity = os_platform.process_identity(process.pid)
        process.identity = execution.identity
        os_platform.write_state(os.path.join(work_dir_ticket, PROC), {
            "ticket_id": execution.ticket_id, "pid": process.pid, "pgid": process.pgid,
            "process_start": execution.identity, "exec_user": exec_user})
    except Exception as e:  # noqa: BLE001
        return _after_spawn_failed(execution, process, log_fd, e, agent)
    os.close(log_fd)
    return execution


def _after_spawn_failed(execution, process, log_fd, error, agent):
    """CR-008, R-01: o grupo existe sem .sss_proc; inicia o encerramento e devolve failed_after_spawn."""
    execution.process = process
    execution.pid = process.pid
    execution.failed_after_spawn = True
    execution.spawn_error_info = error.__class__.__name__
    _sss_line(log_fd, "falha ao iniciar: %s (agente %s)" % (execution.spawn_error_info, agent))
    try:
        os.close(log_fd)
    except OSError:
        _log.warning("log_fd ja fechado", extra={"ticket": execution.ticket_id, "action": "SPAWN"})
    _log.error("falha depois do spawn (%s): encerrando o grupo", execution.spawn_error_info,
               extra={"ticket": execution.ticket_id, "action": "SPAWN"})
    request_stop(execution, time.monotonic())
    return execution


# -----------------------------------------------------------------------------
# Acompanhamento e encerramento (maquina de estados)
# -----------------------------------------------------------------------------

def check(execution):
    """None enquanto o processo direto roda; o returncode quando terminou (Popen.poll, sem esperar)."""
    process = execution.process
    if process is None or process.popen is None:
        return execution.returncode
    rc = process.popen.poll()
    if rc is not None:
        execution.returncode = rc
    return rc


def request_stop(execution, now_monotonic, grace_s=DEFAULT_GRACE_S):
    """SIGTERM ao grupo e prazo do SIGKILL (CR-007, R-04). Chamado em TODA finalizacao, mesmo com o lider
    ja terminado (R-02): grupo com membros nesse caso gera WARN NETOS_ENCERRADOS. Nao espera."""
    if execution.phase is not None:
        return
    process = execution.process
    if process is None or not os_platform.group_alive(process):
        execution.phase = PHASE_END
        return
    if process.no_identity:
        # Sem identidade nao ha sinal seguro (PID pode ter sido reciclado): o chamador finaliza ORPHAN_PROCESS
        # e o limpar preserva a pasta enquanto o grupo existir (CR-008, R-26).
        _log.warning("ORFAO_SEM_IDENTIDADE: grupo vivo sem identidade, nenhum sinal enviado",
                     extra={"ticket": execution.ticket_id, "action": "ENCERRAR"})
        execution.phase = PHASE_NO_IDENTITY
        return
    if check(execution) is not None:
        _log.warning("NETOS_ENCERRADOS: o grupo tinha processos depois da saida do principal",
                     extra={"ticket": execution.ticket_id, "action": "ENCERRAR"})
    os_platform.signal_group(process, signal.SIGTERM)
    execution.phase = PHASE_TERM
    execution.grace_s = grace_s
    execution.kill_deadline = now_monotonic + grace_s


def advance_stop(execution, now_monotonic):
    """Avanca o encerramento sem esperar: SIGKILL quando o prazo vence. True quando o grupo acabou ou
    quando nao ha mais o que fazer (PHASE_NO_IDENTITY). Grupo vivo depois do SIGKILL e de mais um prazo:
    ERROR GRUPO_NAO_ENCERRA uma vez (travado), e o laco segue tentando a cada chamada."""
    if execution.phase is None:
        raise RuntimeError("encerramento nao foi pedido")
    if execution.phase in (PHASE_END, PHASE_NO_IDENTITY):
        return True
    check(execution)
    if not os_platform.group_alive(execution.process):
        execution.phase = PHASE_END
        return True
    if execution.phase == PHASE_TERM and now_monotonic >= execution.kill_deadline:
        os_platform.signal_group(execution.process, signal.SIGKILL)
        execution.phase = PHASE_KILL
    elif execution.phase == PHASE_KILL and not execution.stuck \
            and now_monotonic >= execution.kill_deadline + (execution.grace_s or 0):
        execution.stuck = True
        _log.error("GRUPO_NAO_ENCERRA: grupo vivo depois do SIGKILL", extra={"ticket": execution.ticket_id,
                                                                         "action": "ENCERRAR"})
        os_platform.signal_group(execution.process, signal.SIGKILL)
    return False


def translate_return(returncode, platform_name):
    """returncode -> (status, status_reason, return_code) do README §5.2 (POSIX; sinal = 128 + signum)."""
    if platform_name not in ("LINUX", "UNIX"):
        raise ValueError("Plataforma nao suportada: %s" % platform_name)
    rc = int(returncode)
    if rc == 0:
        return "SUCCESS", "EXIT_OK", 0
    if rc > 0:
        return "FAILED", "EXIT_ERROR", rc
    return "FAILED", "KILLED_SIGNAL", 128 + abs(rc)


def record_result(execution, status, reason, rc):
    """Grava .sss_result antes do UPDATE de finalizacao (CR-007, R-01)."""
    os_platform.write_state(os.path.join(execution.work_dir_ticket, RESULT), {
        "ticket_id": execution.ticket_id, "status": status, "status_reason": reason, "return_code": rc})


def append_local_line(execution, text):
    """Acrescenta uma linha [SSS] ao arquivo de log local (do agente), antes do flush final (CR-012)."""
    fd = os.open(execution.log_path, os.O_WRONLY | os.O_APPEND)
    try:
        _sss_line(fd, text)
    finally:
        os.close(fd)


def clean(execution):
    """Remove work_dir/ticket_<id>/ e, pelo helper, o diretorio do script (CR-008, R-26 e R-36).

    So depois de o grupo estar vazio: com membros vivos, lanca RuntimeError e nada e apagado.
    """
    if execution.process is not None and os_platform.group_alive(execution.process):
        raise RuntimeError("ticket %s: grupo ainda tem processos" % execution.ticket_id)
    if execution.exec_user:
        os_platform.clean_script_dir(execution.base_dir, execution.ticket_id, execution.exec_user)
    dir_value = execution.work_dir_ticket
    if os.path.basename(dir_value) != "ticket_%d" % execution.ticket_id or os.path.islink(dir_value):
        raise RuntimeError("ticket %s: pasta de trabalho inesperada" % execution.ticket_id)
    if os.path.isdir(dir_value):
        shutil.rmtree(dir_value)
