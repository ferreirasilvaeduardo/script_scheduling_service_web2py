# -*- coding: utf-8 -*-
"""Fase de saida do ticket no agente (CR-012, README §8.7 e §8.13): maquina de estados sem espera.

Duas etapas:
  1. empacotar, depois do grupo encerrado e antes do flush final (o ticket ainda esta RUNNING): o helper
     empacotar roda num grupo proprio, acompanhado por poll() e com prazo fixo; a linha [SSS] de excesso ou
     falha vai para o arquivo de log local e chega ao banco no flush final;
  2. gravar, depois da finalizacao: a linha da saida (GRAVANDO, partes de 1 MiB, DISPONIVEL; ou EXCEDEU/FALHOU
     sem conteudo) pelo repo_oracle/scheduler_saida, com posse em toda gravacao e COMMIT por passo.
O resultado do ticket nunca muda por causa da saida. O conteudo da saida nunca vai para log nenhum.
Toda primitiva de SO vem de `os_platform`.
"""
import logging
import os
import signal
import zipfile

from repo_oracle import scheduler_output

_log = logging.getLogger("sss_scheduler")

PACK_DEADLINE_S = 120
PARTS_PER_ROUND = 4
PART_SIZE = scheduler_output.PART_MAX
ZIP_NAME = "output.zip"

# Resultados do empacotamento.
ZIP = "ZIP"
EMPTY = "EMPTY"
EXCEEDED = "EXCEEDED"
FAILED = "FAILED"
ABANDONED = "ABANDONED"

# Desfechos da gravacao.
CONTINUE = "CONTINUE"
DONE = "DONE"
OWNERSHIP_LOST = "OWNERSHIP_LOST"


class Output(object):
    """Pasta de saida de um ticket: base (output_dir/<ambiente>), relativo e o estado das duas etapas."""

    def __init__(self, ticket_id, base, relativo, usuario_execucao, work_dir_ticket):
        self.ticket_id = int(ticket_id)
        self.base = base
        self.relative = relativo
        self.exec_user = usuario_execucao
        self.zip_path = os.path.join(work_dir_ticket, ZIP_NAME)
        self.process = None
        self.deadline = None
        self.dead = False
        self.result = None
        self.reason = None
        self.file_count = None
        self.size = None
        # Gravacao
        self.started = False
        self.offset = 0
        self.next_attempt = 0.0
        self.pending_warned = False

    @property
    def folder(self):
        return os.path.join(self.base, self.relative)

    @property
    def packed(self):
        return self.result is not None


def start_pack(saida, plat, max_bytes, max_arquivos, agora):
    """Abre o zip local (0600, do agente) e inicia o helper empacotar sem esperar."""
    try:
        fd = os.open(saida.zip_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            saida.process = plat.start_pack(saida.base, saida.relative, max_bytes, max_arquivos, fd,
                                                    saida.exec_user)
        finally:
            os.close(fd)
    except Exception as exc:  # noqa: BLE001 - qualquer falha local: FALHOU (o ticket segue)
        _log.warning("empacotamento da saida nao iniciado (%s)", exc.__class__.__name__,
                     extra={"ticket": saida.ticket_id, "action": "SAIDA"})
        saida.result, saida.reason = FAILED, "ERROR"
        return
    saida.deadline = agora + PACK_DEADLINE_S


def advance_pack(saida, plat, agora):
    """Acompanha o empacotar sem esperar. True quando ha resultado (ZIP, VAZIA, EXCEDEU ou FALHOU)."""
    if saida.packed:
        return True
    rc = saida.process.popen.poll()
    if rc is None:
        if agora >= saida.deadline and not saida.dead:
            saida.dead = True
            plat.signal_group(saida.process, signal.SIGKILL)
            _log.warning("empacotamento da saida passou de %d s: encerrado", PACK_DEADLINE_S,
                         extra={"ticket": saida.ticket_id, "action": "SAIDA"})
        return False
    if saida.dead:
        saida.result, saida.reason = FAILED, "DEADLINE"
    elif rc == 0:
        _check_zip(saida)
    elif rc == plat.OUTPUT_EMPTY:
        saida.result = EMPTY
    elif rc == plat.OUTPUT_TOO_MANY_FILES:
        saida.result, saida.reason = EXCEEDED, "FILES"
    elif rc == plat.OUTPUT_TOO_MANY_BYTES:
        saida.result, saida.reason = EXCEEDED, "BYTES"
    else:
        _log.warning("empacotamento da saida terminou com codigo %s", rc,
                     extra={"ticket": saida.ticket_id, "action": "SAIDA"})
        saida.result, saida.reason = FAILED, "ERROR"
    return True


def _check_zip(saida):
    """Le so o indice do zip gerado (quantidade de arquivos) e o tamanho; zip ilegivel e FALHOU."""
    try:
        with zipfile.ZipFile(saida.zip_path) as z:
            saida.file_count = len(z.infolist())
        saida.size = os.path.getsize(saida.zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        _log.warning("zip da saida ilegivel (%s)", exc.__class__.__name__,
                     extra={"ticket": saida.ticket_id, "action": "SAIDA"})
        saida.result, saida.reason = FAILED, "ERROR"
        return
    if saida.file_count == 0 or saida.size == 0:
        saida.result, saida.reason = FAILED, "ERROR"
        return
    saida.result = ZIP


def abandon(saida, plat):
    """Parada do agente durante o empacotamento: encerra o helper; a pasta fica no disco (README §8.13)."""
    if saida.process is not None and not saida.packed and saida.process.popen.poll() is None:
        plat.signal_group(saida.process, signal.SIGKILL)
    saida.result, saida.reason = ABANDONED, None


def log_line(saida, agente_id, max_arquivos, max_bytes):
    """Texto da linha [SSS] para o log do ticket (sem caminho nem conteudo), ou None."""
    if saida.result == EXCEEDED:
        limite = ("%d arquivos" % max_arquivos) if saida.reason == "FILES" else \
            ("%d MiB" % (max_bytes // (1024 * 1024)))
        return "saida nao empacotada: excede o limite de %s (agente %s)" % (limite, agente_id)
    if saida.result == FAILED:
        return "saida nao empacotada: %s (agente %s)" % (
            "prazo de %d s esgotado" % PACK_DEADLINE_S if saida.reason == "DEADLINE" else "falha", agente_id)
    return None


def write(saida, conn, repo, agente_id):
    """Uma volta da gravacao: devolve CONTINUA, CONCLUIDA ou OWNERSHIP_LOST. Erro de banco: ROLLBACK e
    excecao (o chamador refaz a cada cancel_poll_interval_s). Nenhuma espera; ate PARTS_PER_ROUND partes."""
    if saida.result == EMPTY:
        return DONE
    try:
        if saida.result in (EXCEEDED, FAILED):
            ok = repo.register_without_content(conn, saida.ticket_id, agente_id, saida.result, saida.reason,
                                             saida.file_count)
            conn.commit()
            return DONE if ok or _already_written(conn, repo, saida, agente_id, saida.result) else OWNERSHIP_LOST
        if not saida.started:
            if not repo.start(conn, saida.ticket_id, agente_id):
                conn.rollback()
                return DONE if _already_written(conn, repo, saida, agente_id, "AVAILABLE") else OWNERSHIP_LOST
            conn.commit()
            saida.started, saida.offset = True, 0
        with open(saida.zip_path, "rb") as f:
            for _i in range(PARTS_PER_ROUND):
                if saida.offset >= saida.size:
                    break
                f.seek(saida.offset)
                parte = f.read(PART_SIZE)
                desfecho = repo.append_chunk(conn, saida.ticket_id, agente_id, saida.offset, parte)
                if desfecho == scheduler_output.OWNERSHIP_LOST:
                    conn.rollback()
                    return DONE if _already_written(conn, repo, saida, agente_id, "AVAILABLE") else OWNERSHIP_LOST
                conn.commit()
                saida.offset += len(parte)
        if saida.offset < saida.size:
            return CONTINUE
        if repo.complete(conn, saida.ticket_id, agente_id, saida.file_count, saida.size):
            conn.commit()
            return DONE
        conn.rollback()
        return DONE if _already_written(conn, repo, saida, agente_id, "AVAILABLE") else OWNERSHIP_LOST
    except scheduler_output.OutputOffsetMismatch:
        conn.rollback()
        saida.started = False  # o proximo iniciar zera a gravacao deste agente e recomeca do inicio
        raise
    except Exception:
        conn.rollback()
        raise


def _already_written(conn, repo, saida, agente_id, situacao):
    """COMMIT anterior sem resposta: a linha ja tem a situacao final deste agente?"""
    atual = repo.output_state(conn, saida.ticket_id)
    return atual == (situacao, agente_id)


def remove_dir(saida, plat):
    """Com o zip gravado (ou a pasta vazia), a pasta de saida sai pelo helper; as de cima ficam para o purge."""
    plat.clean_output(saida.base, saida.relative, saida.exec_user)


def should_remove_dir(saida):
    return saida.result in (ZIP, EMPTY)
