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

import log_paths
import os_platform

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

    def __init__(self, ticket_id, work_dir_ticket, usuario_execucao, pasta_base, caminho_log):
        self.ticket_id = ticket_id
        self.work_dir_ticket = work_dir_ticket
        self.exec_user = usuario_execucao
        self.base_dir = pasta_base
        self.log_path = caminho_log
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


def _agent_from_label(rotulo):
    # rotulo = 'SSS-<agent_id>-<ticket_id>' (F8.3); o agent_id pode ter '-'.
    texto = str(rotulo or "")
    if texto.startswith("SSS-"):
        texto = texto[4:]
    return texto.rsplit("-", 1)[0] if "-" in texto else texto


def _sss_line(log_fd, texto):
    try:
        os.write(log_fd, ("[SSS] %s\n" % texto).encode("utf-8", "replace"))
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
    caminho = os.path.join(work_dir, "ticket_%d" % int(ticket_id))
    if os.path.lexists(caminho):
        if not startup_concluido:
            raise PreservedDirectory("ticket %s: pasta preexistente antes do startup check" % ticket_id)
        if os.path.islink(caminho) or not os.path.isdir(caminho):
            raise PreservedDirectory("ticket %s: pasta de trabalho nao e um diretorio" % ticket_id)
        try:
            nomes = os.listdir(caminho)
        except OSError as e:
            raise PreservedDirectory("ticket %s: estado desconhecido (%s)" % (ticket_id, e.__class__.__name__))
        marcas = [m for m in MARKERS if m in nomes]
        if marcas:
            raise PreservedDirectory("ticket %s: pasta com estado local %s" % (ticket_id, ",".join(marcas)))
        base = os_platform.final_path(work_dir)
        real = os_platform.final_path(caminho)
        if real == base or os.path.commonpath([real, base]) != base:
            raise PreservedDirectory("ticket %s: pasta fora do work_dir" % ticket_id)
        _log.warning("pasta de trabalho sem estado removida", extra={"ticket": ticket_id, "action": "SPAWN"})
        shutil.rmtree(real)
    os_platform.create_work_dir(caminho)
    os_platform.create_work_dir(os.path.join(caminho, "tmp"))
    return caminho


def open_log(log_dir, ambiente, nome_script, started_at, ticket_id, script_id=None):
    """Abre log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>.log.parcial (O_EXCL, 0600)
    antes do spawn (CR-009: o ambiente do ticket e obrigatorio; vazio e ValueError).

    Cada pasta nova da cadeia recebe 0750 (log_paths.ensure_directory). nome_script e o script_nome do
    snapshot (README §6.5). Devolve (fd, caminho).
    """
    caminho = log_paths.partial_log_path(log_dir, ambiente, nome_script, started_at, ticket_id, script_id)
    log_paths.ensure_directory(os.path.dirname(caminho))
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
    _open_logs[fd] = caminho
    return fd, caminho


def build_spec(ticket_id, argv, env, rlimits, pasta_base, saida=None, entrada=None):
    """Especificacao do helper run (README §8.0), serializada em JSON pela plataforma.

    saida: (base, relativo) da pasta de saida do ticket (CR-012), que o helper cria antes do script.
    entrada: (base, relativo) da pasta de entrada do script (CR-014), que o helper cria se nao existir.
    """
    spec = {
        "ticket_id": int(ticket_id),
        "argv": list(argv),
        "env": dict(env),
        "rlimits": dict((nome, [int(par[0]), int(par[1])]) for nome, par in (rlimits or {}).items()),
        "base_dir": pasta_base,
    }
    if saida is not None:
        spec["output"] = {"base": saida[0], "relativo": saida[1]}
    if entrada is not None:
        spec["input"] = {"base": entrada[0], "relativo": entrada[1]}
    return spec


# -----------------------------------------------------------------------------
# Spawn
# -----------------------------------------------------------------------------

def _spawn_failure(execucao, log_fd, erro, agente):
    """SPAWN_ERROR sem processo: causa no log (sem segredos) e parcial renomeado para ticket_<id>_0.log."""
    execucao.spawn_error_info = erro.__class__.__name__
    _sss_line(log_fd, "falha ao iniciar: %s (agente %s)" % (execucao.spawn_error_info, agente))
    try:
        os.close(log_fd)
    except OSError:
        _log.warning("log_fd ja fechado", extra={"ticket": execucao.ticket_id, "action": "SPAWN"})
    if execucao.log_path:
        final = os.path.join(os.path.dirname(execucao.log_path),
                             log_paths.run_log_name(execucao.ticket_id, 0))
        try:
            os.rename(execucao.log_path, final)
            execucao.log_path = final
        except OSError as e:
            _log.error("rename do log de SPAWN_ERROR falhou (%s)", e.__class__.__name__,
                       extra={"ticket": execucao.ticket_id, "action": "SPAWN"})
    _log.error("SPAWN_ERROR: %s", execucao.spawn_error_info, extra={"ticket": execucao.ticket_id, "action": "SPAWN"})
    return execucao


def failure_before_spawn(log_fd, ticket_id, erro, rotulo, work_dir_ticket=None):
    """SPAWN_ERROR depois de open_log e antes de iniciar (ex.: excecao no env_builder): grava a linha [SSS],
    fecha o descritor e renomeia o parcial para ticket_<id>_0.log, como em iniciar (README §8.4, passo 3)."""
    execucao = Execution(int(ticket_id), work_dir_ticket, None, None, _open_logs.pop(log_fd, None))
    return _spawn_failure(execucao, log_fd, erro, _agent_from_label(rotulo))


def start(ticket_id, argv, log_fd, env, work_dir_ticket, usuario_execucao, exec_work_dir, rlimits, rotulo,
            saida=None, entrada=None):
    """Inicia o script e devolve a Execucao (README §8.4 passos 3 a 5; CR-008 R-01).

    Ordem: .sss_spawn -> os_platform.start_process -> rename do log para ticket_<id>_<PID>.log ->
    identidade -> .sss_proc -> os.close(log_fd). Qualquer excecao antes do processo: SPAWN_ERROR com o log
    ticket_<id>_0.log. Qualquer falha depois dele: failed_after_spawn e SIGTERM ao grupo (sem esperar); o
    chamador acompanha a execucao ate o grupo acabar e so entao finaliza SPAWN_ERROR.

    saida: (base, relativo) da pasta de saida (CR-012): o helper run a cria; em DEV, a plataforma.
    entrada: (base, relativo) da pasta de entrada (CR-014), permanente: idem, so se nao existir.
    """
    agente = _agent_from_label(rotulo)
    pasta_base = os.path.join(exec_work_dir, usuario_execucao) if usuario_execucao else None
    execucao = Execution(int(ticket_id), work_dir_ticket, usuario_execucao, pasta_base, _open_logs.pop(log_fd, None))
    try:
        if execucao.log_path is None:
            raise ValueError("log_fd nao foi aberto por abrir_log")
        if usuario_execucao:
            spec = build_spec(ticket_id, argv, env, rlimits, pasta_base, saida, entrada)
        else:
            # DEV sem usuario de execucao: o cwd e a pasta exec de work_dir/ticket_<id> (CR-008, R-36).
            cwd = os_platform.create_work_dir(os.path.join(work_dir_ticket, "exec"))
            os_platform.create_work_dir(os.path.join(cwd, "tmp"))
            spec = {"argv": list(argv), "cwd": cwd, "env": dict(env), "rlimits": dict(rlimits or {})}
            if saida is not None:
                os_platform.create_output_dir(saida[0], saida[1])
            if entrada is not None:
                os_platform.create_input_dir(entrada[0], entrada[1])
        os_platform.write_state(os.path.join(work_dir_ticket, SPAWN), {
            "ticket_id": int(ticket_id), "exec_user": usuario_execucao,
            "monotonic": time.monotonic(), "wall": time.time()})
    except Exception as e:  # noqa: BLE001 - CR-007 R-17: qualquer excecao no spawn e SPAWN_ERROR
        return _spawn_failure(execucao, log_fd, e, agente)

    try:
        processo = os_platform.start_process(spec, log_fd, usuario_execucao)
    except os_platform.FailureAfterSpawn as f:
        return _after_spawn_failed(execucao, f.process, log_fd, f.cause, agente)
    except Exception as e:  # noqa: BLE001
        return _spawn_failure(execucao, log_fd, e, agente)

    execucao.process = processo
    execucao.pid = processo.pid
    try:
        final = os.path.join(os.path.dirname(execucao.log_path),
                             log_paths.run_log_name(execucao.ticket_id, processo.pid))
        os.rename(execucao.log_path, final)
        execucao.log_path = final
        execucao.identity = os_platform.process_identity(processo.pid)
        processo.identity = execucao.identity
        os_platform.write_state(os.path.join(work_dir_ticket, PROC), {
            "ticket_id": execucao.ticket_id, "pid": processo.pid, "pgid": processo.pgid,
            "process_start": execucao.identity, "exec_user": usuario_execucao})
    except Exception as e:  # noqa: BLE001
        return _after_spawn_failed(execucao, processo, log_fd, e, agente)
    os.close(log_fd)
    return execucao


def _after_spawn_failed(execucao, processo, log_fd, erro, agente):
    """CR-008, R-01: o grupo existe sem .sss_proc; inicia o encerramento e devolve failed_after_spawn."""
    execucao.process = processo
    execucao.pid = processo.pid
    execucao.failed_after_spawn = True
    execucao.spawn_error_info = erro.__class__.__name__
    _sss_line(log_fd, "falha ao iniciar: %s (agente %s)" % (execucao.spawn_error_info, agente))
    try:
        os.close(log_fd)
    except OSError:
        _log.warning("log_fd ja fechado", extra={"ticket": execucao.ticket_id, "action": "SPAWN"})
    _log.error("falha depois do spawn (%s): encerrando o grupo", execucao.spawn_error_info,
               extra={"ticket": execucao.ticket_id, "action": "SPAWN"})
    request_stop(execucao, time.monotonic())
    return execucao


# -----------------------------------------------------------------------------
# Acompanhamento e encerramento (maquina de estados)
# -----------------------------------------------------------------------------

def check(execucao):
    """None enquanto o processo direto roda; o returncode quando terminou (Popen.poll, sem esperar)."""
    processo = execucao.process
    if processo is None or processo.popen is None:
        return execucao.returncode
    rc = processo.popen.poll()
    if rc is not None:
        execucao.returncode = rc
    return rc


def request_stop(execucao, agora_monotonico, grace_s=DEFAULT_GRACE_S):
    """SIGTERM ao grupo e prazo do SIGKILL (CR-007, R-04). Chamado em TODA finalizacao, mesmo com o lider
    ja terminado (R-02): grupo com membros nesse caso gera WARN NETOS_ENCERRADOS. Nao espera."""
    if execucao.phase is not None:
        return
    processo = execucao.process
    if processo is None or not os_platform.group_alive(processo):
        execucao.phase = PHASE_END
        return
    if processo.no_identity:
        # Sem identidade nao ha sinal seguro (PID pode ter sido reciclado): o chamador finaliza ORPHAN_PROCESS
        # e o limpar preserva a pasta enquanto o grupo existir (CR-008, R-26).
        _log.warning("ORFAO_SEM_IDENTIDADE: grupo vivo sem identidade, nenhum sinal enviado",
                     extra={"ticket": execucao.ticket_id, "action": "ENCERRAR"})
        execucao.phase = PHASE_NO_IDENTITY
        return
    if check(execucao) is not None:
        _log.warning("NETOS_ENCERRADOS: o grupo tinha processos depois da saida do principal",
                     extra={"ticket": execucao.ticket_id, "action": "ENCERRAR"})
    os_platform.signal_group(processo, signal.SIGTERM)
    execucao.phase = PHASE_TERM
    execucao.grace_s = grace_s
    execucao.kill_deadline = agora_monotonico + grace_s


def advance_stop(execucao, agora_monotonico):
    """Avanca o encerramento sem esperar: SIGKILL quando o prazo vence. True quando o grupo acabou ou
    quando nao ha mais o que fazer (PHASE_NO_IDENTITY). Grupo vivo depois do SIGKILL e de mais um prazo:
    ERROR GRUPO_NAO_ENCERRA uma vez (travado), e o laco segue tentando a cada chamada."""
    if execucao.phase is None:
        raise RuntimeError("encerramento nao foi pedido")
    if execucao.phase in (PHASE_END, PHASE_NO_IDENTITY):
        return True
    check(execucao)
    if not os_platform.group_alive(execucao.process):
        execucao.phase = PHASE_END
        return True
    if execucao.phase == PHASE_TERM and agora_monotonico >= execucao.kill_deadline:
        os_platform.signal_group(execucao.process, signal.SIGKILL)
        execucao.phase = PHASE_KILL
    elif execucao.phase == PHASE_KILL and not execucao.stuck \
            and agora_monotonico >= execucao.kill_deadline + (execucao.grace_s or 0):
        execucao.stuck = True
        _log.error("GRUPO_NAO_ENCERRA: grupo vivo depois do SIGKILL", extra={"ticket": execucao.ticket_id,
                                                                         "action": "ENCERRAR"})
        os_platform.signal_group(execucao.process, signal.SIGKILL)
    return False


def translate_return(returncode, plataforma_nome):
    """returncode -> (status, status_motivo, return_code) do README §5.2 (POSIX; sinal = 128 + signum)."""
    if plataforma_nome not in ("LINUX", "UNIX"):
        raise ValueError("Plataforma nao suportada: %s" % plataforma_nome)
    rc = int(returncode)
    if rc == 0:
        return "SUCCESS", "EXIT_OK", 0
    if rc > 0:
        return "FAILED", "EXIT_ERROR", rc
    return "FAILED", "KILLED_SIGNAL", 128 + abs(rc)


def record_result(execucao, status, motivo, rc):
    """Grava .sss_result antes do UPDATE de finalizacao (CR-007, R-01)."""
    os_platform.write_state(os.path.join(execucao.work_dir_ticket, RESULT), {
        "ticket_id": execucao.ticket_id, "status": status, "status_reason": motivo, "return_code": rc})


def append_local_line(execucao, texto):
    """Acrescenta uma linha [SSS] ao arquivo de log local (do agente), antes do flush final (CR-012)."""
    fd = os.open(execucao.log_path, os.O_WRONLY | os.O_APPEND)
    try:
        _sss_line(fd, texto)
    finally:
        os.close(fd)


def clean(execucao):
    """Remove work_dir/ticket_<id>/ e, pelo helper, o diretorio do script (CR-008, R-26 e R-36).

    So depois de o grupo estar vazio: com membros vivos, lanca RuntimeError e nada e apagado.
    """
    if execucao.process is not None and os_platform.group_alive(execucao.process):
        raise RuntimeError("ticket %s: grupo ainda tem processos" % execucao.ticket_id)
    if execucao.exec_user:
        os_platform.clean_script_dir(execucao.base_dir, execucao.ticket_id, execucao.exec_user)
    pasta = execucao.work_dir_ticket
    if os.path.basename(pasta) != "ticket_%d" % execucao.ticket_id or os.path.islink(pasta):
        raise RuntimeError("ticket %s: pasta de trabalho inesperada" % execucao.ticket_id)
    if os.path.isdir(pasta):
        shutil.rmtree(pasta)
