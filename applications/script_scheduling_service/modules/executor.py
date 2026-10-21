# -*- coding: utf-8 -*-
"""Spawn e acompanhamento dos scripts (README §8.4, §8.7; CR-007 D1, R-01 a R-04, R-17; CR-008 R-01, R-26, R-36).

Unico chamador de plataforma.iniciar_processo. Nao conhece o SO (tudo vem de plataforma) nem o banco.
Nenhuma funcao espera: o encerramento e uma maquina de estados (pedir_encerramento/avancar_encerramento)
avancada pelo laco do daemon. Saida do script direto no arquivo de log (sem pipe de saida, AGENTS §3.2).
"""
import logging
import os
import shutil
import signal
import time

import pastas_log
import plataforma

_log = logging.getLogger("sss_scheduler")

SPAWN = ".sss_spawn"
PROC = ".sss_proc"
RESULT = ".sss_result"
MARCADORES = (SPAWN, PROC, RESULT)

RC_SPAWN_ERROR = -4
GRACE_PADRAO_S = 10

# Fases do encerramento (CR-007, R-04).
FASE_TERM = "TERM"
FASE_KILL = "KILL"
FASE_FIM = "FIM"
# Grupo vivo sem identidade legivel (ORFAO_SEM_IDENTIDADE): nunca recebe sinal; a pasta fica (CR-008, R-26).
FASE_SEM_IDENTIDADE = "SEM_IDENTIDADE"

# Logs abertos por abrir_log e ainda nao entregues a iniciar: fd -> caminho do .log.parcial.
_logs_abertos = {}


class DiretorioPreservado(RuntimeError):
    """work_dir/ticket_<id>/ ja existe com rastro de execucao (ou estado desconhecido): nada e apagado."""


class Execucao(object):
    """Um ticket em execucao (ou que falhou ao iniciar) no mapa local do agente."""

    def __init__(self, ticket_id, work_dir_ticket, usuario_execucao, pasta_base, caminho_log):
        self.ticket_id = ticket_id
        self.work_dir_ticket = work_dir_ticket
        self.usuario_execucao = usuario_execucao
        self.pasta_base = pasta_base
        self.caminho_log = caminho_log
        self.processo = None
        self.pid = None
        self.identidade = None
        # SPAWN_ERROR: sem processo (erro_spawn) ou com processo a encerrar (falhou_apos_spawn).
        self.erro_spawn = None
        self.falhou_apos_spawn = False
        self.returncode = None
        self.fase = None
        self.prazo_kill = None
        self.grace_s = None
        # GRUPO_NAO_ENCERRA ja registrado (grupo vivo depois do SIGKILL e de mais um prazo).
        self.travado = False

    @property
    def sem_identidade(self):
        return self.fase == FASE_SEM_IDENTIDADE

    @property
    def spawn_error(self):
        return self.erro_spawn is not None

    def __repr__(self):
        return "Execucao(ticket=%s, pid=%s, fase=%s, erro=%s)" % (self.ticket_id, self.pid, self.fase,
                                                                  self.erro_spawn)


def _agente_do_rotulo(rotulo):
    # rotulo = 'SSS-<agent_id>-<ticket_id>' (F8.3); o agent_id pode ter '-'.
    texto = str(rotulo or "")
    if texto.startswith("SSS-"):
        texto = texto[4:]
    return texto.rsplit("-", 1)[0] if "-" in texto else texto


def _linha_sss(log_fd, texto):
    try:
        os.write(log_fd, ("[SSS] %s\n" % texto).encode("utf-8", "replace"))
    except OSError as e:
        _log.warning("falha ao gravar a linha [SSS] no log (%s)", e.__class__.__name__, extra={"acao": "SPAWN"})


# -----------------------------------------------------------------------------
# Preparo
# -----------------------------------------------------------------------------

def preparar_diretorio(work_dir, ticket_id, startup_concluido=False):
    """Cria work_dir/ticket_<id>/ e tmp/ (0700, estado local do agente; README §8.4 passo 2).

    Pasta preexistente so e removida depois do startup check (startup_concluido) e sem nenhum marcador
    (.sss_spawn, .sss_proc, .sss_result): sem .sss_proc nao ha grupo de processo associado. Com marcador ou
    estado desconhecido, preserva a pasta e lanca DiretorioPreservado (falha fechada).
    """
    caminho = os.path.join(work_dir, "ticket_%d" % int(ticket_id))
    if os.path.lexists(caminho):
        if not startup_concluido:
            raise DiretorioPreservado("ticket %s: pasta preexistente antes do startup check" % ticket_id)
        if os.path.islink(caminho) or not os.path.isdir(caminho):
            raise DiretorioPreservado("ticket %s: pasta de trabalho nao e um diretorio" % ticket_id)
        try:
            nomes = os.listdir(caminho)
        except OSError as e:
            raise DiretorioPreservado("ticket %s: estado desconhecido (%s)" % (ticket_id, e.__class__.__name__))
        marcas = [m for m in MARCADORES if m in nomes]
        if marcas:
            raise DiretorioPreservado("ticket %s: pasta com estado local %s" % (ticket_id, ",".join(marcas)))
        base = plataforma.caminho_final(work_dir)
        real = plataforma.caminho_final(caminho)
        if real == base or os.path.commonpath([real, base]) != base:
            raise DiretorioPreservado("ticket %s: pasta fora do work_dir" % ticket_id)
        _log.warning("pasta de trabalho sem estado removida", extra={"ticket": ticket_id, "acao": "SPAWN"})
        shutil.rmtree(real)
    plataforma.criar_dir_trabalho(caminho)
    plataforma.criar_dir_trabalho(os.path.join(caminho, "tmp"))
    return caminho


def abrir_log(log_dir, ambiente, nome_script, started_at, ticket_id, script_id=None):
    """Abre log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>.log.parcial (O_EXCL, 0600)
    antes do spawn (CR-009: o ambiente do ticket e obrigatorio; vazio e ValueError).

    Cada pasta nova da cadeia recebe 0750 (pastas_log.garantir_diretorio). nome_script e o script_nome do
    snapshot (README §6.5). Devolve (fd, caminho).
    """
    caminho = pastas_log.caminho_log_parcial(log_dir, ambiente, nome_script, started_at, ticket_id, script_id)
    pastas_log.garantir_diretorio(os.path.dirname(caminho))
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
    _logs_abertos[fd] = caminho
    return fd, caminho


def especificacao(ticket_id, argv, env, rlimits, pasta_base, saida=None, entrada=None):
    """Especificacao do helper run (README §8.0), serializada em JSON pela plataforma.

    saida: (base, relativo) da pasta de saida do ticket (CR-012), que o helper cria antes do script.
    entrada: (base, relativo) da pasta de entrada do script (CR-014), que o helper cria se nao existir.
    """
    spec = {
        "ticket_id": int(ticket_id),
        "argv": list(argv),
        "env": dict(env),
        "rlimits": dict((nome, [int(par[0]), int(par[1])]) for nome, par in (rlimits or {}).items()),
        "pasta_base": pasta_base,
    }
    if saida is not None:
        spec["saida"] = {"base": saida[0], "relativo": saida[1]}
    if entrada is not None:
        spec["entrada"] = {"base": entrada[0], "relativo": entrada[1]}
    return spec


# -----------------------------------------------------------------------------
# Spawn
# -----------------------------------------------------------------------------

def _falha_spawn(execucao, log_fd, erro, agente):
    """SPAWN_ERROR sem processo: causa no log (sem segredos) e parcial renomeado para ticket_<id>_0.log."""
    execucao.erro_spawn = erro.__class__.__name__
    _linha_sss(log_fd, "falha ao iniciar: %s (agente %s)" % (execucao.erro_spawn, agente))
    try:
        os.close(log_fd)
    except OSError:
        _log.warning("log_fd ja fechado", extra={"ticket": execucao.ticket_id, "acao": "SPAWN"})
    if execucao.caminho_log:
        final = os.path.join(os.path.dirname(execucao.caminho_log),
                             pastas_log.nome_log_execucao(execucao.ticket_id, 0))
        try:
            os.rename(execucao.caminho_log, final)
            execucao.caminho_log = final
        except OSError as e:
            _log.error("rename do log de SPAWN_ERROR falhou (%s)", e.__class__.__name__,
                       extra={"ticket": execucao.ticket_id, "acao": "SPAWN"})
    _log.error("SPAWN_ERROR: %s", execucao.erro_spawn, extra={"ticket": execucao.ticket_id, "acao": "SPAWN"})
    return execucao


def falha_antes_do_spawn(log_fd, ticket_id, erro, rotulo, work_dir_ticket=None):
    """SPAWN_ERROR depois de abrir_log e antes de iniciar (ex.: excecao no env_builder): grava a linha [SSS],
    fecha o descritor e renomeia o parcial para ticket_<id>_0.log, como em iniciar (README §8.4, passo 3)."""
    execucao = Execucao(int(ticket_id), work_dir_ticket, None, None, _logs_abertos.pop(log_fd, None))
    return _falha_spawn(execucao, log_fd, erro, _agente_do_rotulo(rotulo))


def iniciar(ticket_id, argv, log_fd, env, work_dir_ticket, usuario_execucao, exec_work_dir, rlimits, rotulo,
            saida=None, entrada=None):
    """Inicia o script e devolve a Execucao (README §8.4 passos 3 a 5; CR-008 R-01).

    Ordem: .sss_spawn -> plataforma.iniciar_processo -> rename do log para ticket_<id>_<PID>.log ->
    identidade -> .sss_proc -> os.close(log_fd). Qualquer excecao antes do processo: SPAWN_ERROR com o log
    ticket_<id>_0.log. Qualquer falha depois dele: falhou_apos_spawn e SIGTERM ao grupo (sem esperar); o
    chamador acompanha a execucao ate o grupo acabar e so entao finaliza SPAWN_ERROR.

    saida: (base, relativo) da pasta de saida (CR-012): o helper run a cria; em DEV, a plataforma.
    entrada: (base, relativo) da pasta de entrada (CR-014), permanente: idem, so se nao existir.
    """
    agente = _agente_do_rotulo(rotulo)
    pasta_base = os.path.join(exec_work_dir, usuario_execucao) if usuario_execucao else None
    execucao = Execucao(int(ticket_id), work_dir_ticket, usuario_execucao, pasta_base, _logs_abertos.pop(log_fd, None))
    try:
        if execucao.caminho_log is None:
            raise ValueError("log_fd nao foi aberto por abrir_log")
        if usuario_execucao:
            spec = especificacao(ticket_id, argv, env, rlimits, pasta_base, saida, entrada)
        else:
            # DEV sem usuario de execucao: o cwd e a pasta exec de work_dir/ticket_<id> (CR-008, R-36).
            cwd = plataforma.criar_dir_trabalho(os.path.join(work_dir_ticket, "exec"))
            plataforma.criar_dir_trabalho(os.path.join(cwd, "tmp"))
            spec = {"argv": list(argv), "cwd": cwd, "env": dict(env), "rlimits": dict(rlimits or {})}
            if saida is not None:
                plataforma.criar_pasta_saida(saida[0], saida[1])
            if entrada is not None:
                plataforma.criar_pasta_entrada(entrada[0], entrada[1])
        plataforma.gravar_estado(os.path.join(work_dir_ticket, SPAWN), {
            "ticket_id": int(ticket_id), "usuario_execucao": usuario_execucao,
            "monotonico": time.monotonic(), "parede": time.time()})
    except Exception as e:  # noqa: BLE001 - CR-007 R-17: qualquer excecao no spawn e SPAWN_ERROR
        return _falha_spawn(execucao, log_fd, e, agente)

    try:
        processo = plataforma.iniciar_processo(spec, log_fd, usuario_execucao)
    except plataforma.FalhaAposSpawn as f:
        return _apos_spawn_falhou(execucao, f.processo, log_fd, f.causa, agente)
    except Exception as e:  # noqa: BLE001
        return _falha_spawn(execucao, log_fd, e, agente)

    execucao.processo = processo
    execucao.pid = processo.pid
    try:
        final = os.path.join(os.path.dirname(execucao.caminho_log),
                             pastas_log.nome_log_execucao(execucao.ticket_id, processo.pid))
        os.rename(execucao.caminho_log, final)
        execucao.caminho_log = final
        execucao.identidade = plataforma.identidade_processo(processo.pid)
        processo.identidade = execucao.identidade
        plataforma.gravar_estado(os.path.join(work_dir_ticket, PROC), {
            "ticket_id": execucao.ticket_id, "pid": processo.pid, "pgid": processo.pgid,
            "process_start": execucao.identidade, "usuario_execucao": usuario_execucao})
    except Exception as e:  # noqa: BLE001
        return _apos_spawn_falhou(execucao, processo, log_fd, e, agente)
    os.close(log_fd)
    return execucao


def _apos_spawn_falhou(execucao, processo, log_fd, erro, agente):
    """CR-008, R-01: o grupo existe sem .sss_proc; inicia o encerramento e devolve falhou_apos_spawn."""
    execucao.processo = processo
    execucao.pid = processo.pid
    execucao.falhou_apos_spawn = True
    execucao.erro_spawn = erro.__class__.__name__
    _linha_sss(log_fd, "falha ao iniciar: %s (agente %s)" % (execucao.erro_spawn, agente))
    try:
        os.close(log_fd)
    except OSError:
        _log.warning("log_fd ja fechado", extra={"ticket": execucao.ticket_id, "acao": "SPAWN"})
    _log.error("falha depois do spawn (%s): encerrando o grupo", execucao.erro_spawn,
               extra={"ticket": execucao.ticket_id, "acao": "SPAWN"})
    pedir_encerramento(execucao, time.monotonic())
    return execucao


# -----------------------------------------------------------------------------
# Acompanhamento e encerramento (maquina de estados)
# -----------------------------------------------------------------------------

def verificar(execucao):
    """None enquanto o processo direto roda; o returncode quando terminou (Popen.poll, sem esperar)."""
    processo = execucao.processo
    if processo is None or processo.popen is None:
        return execucao.returncode
    rc = processo.popen.poll()
    if rc is not None:
        execucao.returncode = rc
    return rc


def pedir_encerramento(execucao, agora_monotonico, grace_s=GRACE_PADRAO_S):
    """SIGTERM ao grupo e prazo do SIGKILL (CR-007, R-04). Chamado em TODA finalizacao, mesmo com o lider
    ja terminado (R-02): grupo com membros nesse caso gera WARN NETOS_ENCERRADOS. Nao espera."""
    if execucao.fase is not None:
        return
    processo = execucao.processo
    if processo is None or not plataforma.grupo_vivo(processo):
        execucao.fase = FASE_FIM
        return
    if processo.sem_identidade:
        # Sem identidade nao ha sinal seguro (PID pode ter sido reciclado): o chamador finaliza ORPHAN_PROCESS
        # e o limpar preserva a pasta enquanto o grupo existir (CR-008, R-26).
        _log.warning("ORFAO_SEM_IDENTIDADE: grupo vivo sem identidade, nenhum sinal enviado",
                     extra={"ticket": execucao.ticket_id, "acao": "ENCERRAR"})
        execucao.fase = FASE_SEM_IDENTIDADE
        return
    if verificar(execucao) is not None:
        _log.warning("NETOS_ENCERRADOS: o grupo tinha processos depois da saida do principal",
                     extra={"ticket": execucao.ticket_id, "acao": "ENCERRAR"})
    plataforma.sinalizar_grupo(processo, signal.SIGTERM)
    execucao.fase = FASE_TERM
    execucao.grace_s = grace_s
    execucao.prazo_kill = agora_monotonico + grace_s


def avancar_encerramento(execucao, agora_monotonico):
    """Avanca o encerramento sem esperar: SIGKILL quando o prazo vence. True quando o grupo acabou ou
    quando nao ha mais o que fazer (FASE_SEM_IDENTIDADE). Grupo vivo depois do SIGKILL e de mais um prazo:
    ERROR GRUPO_NAO_ENCERRA uma vez (travado), e o laco segue tentando a cada chamada."""
    if execucao.fase is None:
        raise RuntimeError("encerramento nao foi pedido")
    if execucao.fase in (FASE_FIM, FASE_SEM_IDENTIDADE):
        return True
    verificar(execucao)
    if not plataforma.grupo_vivo(execucao.processo):
        execucao.fase = FASE_FIM
        return True
    if execucao.fase == FASE_TERM and agora_monotonico >= execucao.prazo_kill:
        plataforma.sinalizar_grupo(execucao.processo, signal.SIGKILL)
        execucao.fase = FASE_KILL
    elif execucao.fase == FASE_KILL and not execucao.travado \
            and agora_monotonico >= execucao.prazo_kill + (execucao.grace_s or 0):
        execucao.travado = True
        _log.error("GRUPO_NAO_ENCERRA: grupo vivo depois do SIGKILL", extra={"ticket": execucao.ticket_id,
                                                                         "acao": "ENCERRAR"})
        plataforma.sinalizar_grupo(execucao.processo, signal.SIGKILL)
    return False


def traduzir_retorno(returncode, plataforma_nome):
    """returncode -> (status, status_motivo, return_code) do README §5.2 (POSIX; sinal = 128 + signum)."""
    if plataforma_nome not in ("LINUX", "UNIX"):
        raise ValueError("Plataforma nao suportada: %s" % plataforma_nome)
    rc = int(returncode)
    if rc == 0:
        return "SUCCESS", "EXIT_OK", 0
    if rc > 0:
        return "FAILED", "EXIT_ERROR", rc
    return "FAILED", "KILLED_SIGNAL", 128 + abs(rc)


def registrar_resultado(execucao, status, motivo, rc):
    """Grava .sss_result antes do UPDATE de finalizacao (CR-007, R-01)."""
    plataforma.gravar_estado(os.path.join(execucao.work_dir_ticket, RESULT), {
        "ticket_id": execucao.ticket_id, "status": status, "status_reason": motivo, "return_code": rc})


def anexar_linha_local(execucao, texto):
    """Acrescenta uma linha [SSS] ao arquivo de log local (do agente), antes do flush final (CR-012)."""
    fd = os.open(execucao.caminho_log, os.O_WRONLY | os.O_APPEND)
    try:
        _linha_sss(fd, texto)
    finally:
        os.close(fd)


def limpar(execucao):
    """Remove work_dir/ticket_<id>/ e, pelo helper, o diretorio do script (CR-008, R-26 e R-36).

    So depois de o grupo estar vazio: com membros vivos, lanca RuntimeError e nada e apagado.
    """
    if execucao.processo is not None and plataforma.grupo_vivo(execucao.processo):
        raise RuntimeError("ticket %s: grupo ainda tem processos" % execucao.ticket_id)
    if execucao.usuario_execucao:
        plataforma.limpar_dir_script(execucao.pasta_base, execucao.ticket_id, execucao.usuario_execucao)
    pasta = execucao.work_dir_ticket
    if os.path.basename(pasta) != "ticket_%d" % execucao.ticket_id or os.path.islink(pasta):
        raise RuntimeError("ticket %s: pasta de trabalho inesperada" % execucao.ticket_id)
    if os.path.isdir(pasta):
        shutil.rmtree(pasta)
