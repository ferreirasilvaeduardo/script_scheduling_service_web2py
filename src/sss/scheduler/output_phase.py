# -*- coding: utf-8 -*-
"""Fase de saida do ticket no agente (CR-012, README §8.7 e §8.13): maquina de estados sem espera.

Duas etapas:
  1. empacotar, depois do grupo encerrado e antes do flush final (o ticket ainda esta RUNNING): o helper
     empacotar roda num grupo proprio, acompanhado por poll() e com prazo fixo; a linha [SSS] de excesso ou
     falha vai para o arquivo de log local e chega ao banco no flush final;
  2. gravar, depois da finalizacao: a linha da saida (GRAVANDO, partes de 1 MiB, DISPONIVEL; ou EXCEDEU/FALHOU
     sem conteudo) pelo repo_oracle/scheduler_output, com posse em toda gravacao e COMMIT por passo.
O resultado do ticket nunca muda por causa da saida. O conteudo da saida nunca vai para log nenhum.
Toda primitiva de SO vem de `os_platform`.
"""
import logging
import os
import signal
import zipfile

from sss.persistence.oracle import scheduler_output

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

    def __init__(self, ticket_id, base, relative, exec_user, work_dir_ticket):
        self.ticket_id = int(ticket_id)
        self.base = base
        self.relative = relative
        self.exec_user = exec_user
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


def start_pack(output, plat, max_bytes, max_files, now):
    """Abre o zip local (0600, do agente) e inicia o helper empacotar sem esperar."""
    try:
        fd = os.open(output.zip_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            output.process = plat.start_pack(output.base, output.relative, max_bytes, max_files, fd,
                                                    output.exec_user)
        finally:
            os.close(fd)
    except Exception as exc:  # noqa: BLE001 - qualquer falha local: FALHOU (o ticket segue)
        _log.warning("empacotamento da saida nao iniciado (%s)", exc.__class__.__name__,
                     extra={"ticket": output.ticket_id, "action": "SAIDA"})
        output.result, output.reason = FAILED, "ERROR"
        return
    output.deadline = now + PACK_DEADLINE_S


def advance_pack(output, plat, now):
    """Acompanha o empacotar sem esperar. True quando ha resultado (ZIP, VAZIA, EXCEDEU ou FALHOU)."""
    if output.packed:
        return True
    rc = output.process.popen.poll()
    if rc is None:
        if now >= output.deadline and not output.dead:
            output.dead = True
            plat.signal_group(output.process, signal.SIGKILL)
            _log.warning("empacotamento da saida passou de %d s: encerrado", PACK_DEADLINE_S,
                         extra={"ticket": output.ticket_id, "action": "SAIDA"})
        return False
    if output.dead:
        output.result, output.reason = FAILED, "DEADLINE"
    elif rc == 0:
        _check_zip(output)
    elif rc == plat.OUTPUT_EMPTY:
        output.result = EMPTY
    elif rc == plat.OUTPUT_TOO_MANY_FILES:
        output.result, output.reason = EXCEEDED, "FILES"
    elif rc == plat.OUTPUT_TOO_MANY_BYTES:
        output.result, output.reason = EXCEEDED, "BYTES"
    else:
        _log.warning("empacotamento da saida terminou com codigo %s", rc,
                     extra={"ticket": output.ticket_id, "action": "SAIDA"})
        output.result, output.reason = FAILED, "ERROR"
    return True


def _check_zip(output):
    """Le so o indice do zip gerado (quantidade de arquivos) e o tamanho; zip ilegivel e FALHOU."""
    try:
        with zipfile.ZipFile(output.zip_path) as z:
            output.file_count = len(z.infolist())
        output.size = os.path.getsize(output.zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        _log.warning("zip da saida ilegivel (%s)", exc.__class__.__name__,
                     extra={"ticket": output.ticket_id, "action": "SAIDA"})
        output.result, output.reason = FAILED, "ERROR"
        return
    if output.file_count == 0 or output.size == 0:
        output.result, output.reason = FAILED, "ERROR"
        return
    output.result = ZIP


def abandon(output, plat):
    """Parada do agente durante o empacotamento: encerra o helper; a pasta fica no disco (README §8.13)."""
    if output.process is not None and not output.packed and output.process.popen.poll() is None:
        plat.signal_group(output.process, signal.SIGKILL)
    output.result, output.reason = ABANDONED, None


def log_line(output, agent_id, max_files, max_bytes):
    """Texto da linha [SSS] para o log do ticket (sem caminho nem conteudo), ou None."""
    if output.result == EXCEEDED:
        limit = ("%d arquivos" % max_files) if output.reason == "FILES" else \
            ("%d MiB" % (max_bytes // (1024 * 1024)))
        return "saida nao empacotada: excede o limite de %s (agente %s)" % (limit, agent_id)
    if output.result == FAILED:
        return "saida nao empacotada: %s (agente %s)" % (
            "prazo de %d s esgotado" % PACK_DEADLINE_S if output.reason == "DEADLINE" else "falha", agent_id)
    return None


def write(output, conn, repo, agent_id):
    """Uma volta da gravacao: devolve CONTINUA, CONCLUIDA ou OWNERSHIP_LOST. Erro de banco: ROLLBACK e
    excecao (o chamador refaz a cada cancel_poll_interval_s). Nenhuma espera; ate PARTS_PER_ROUND partes."""
    if output.result == EMPTY:
        return DONE
    try:
        if output.result in (EXCEEDED, FAILED):
            ok = repo.register_without_content(conn, output.ticket_id, agent_id, output.result, output.reason,
                                             output.file_count)
            conn.commit()
            return DONE if ok or _already_written(conn, repo, output, agent_id, output.result) else OWNERSHIP_LOST
        if not output.started:
            if not repo.start(conn, output.ticket_id, agent_id):
                conn.rollback()
                return DONE if _already_written(conn, repo, output, agent_id, "AVAILABLE") else OWNERSHIP_LOST
            conn.commit()
            output.started, output.offset = True, 0
        with open(output.zip_path, "rb") as f:
            for _i in range(PARTS_PER_ROUND):
                if output.offset >= output.size:
                    break
                f.seek(output.offset)
                part = f.read(PART_SIZE)
                outcome = repo.append_chunk(conn, output.ticket_id, agent_id, output.offset, part)
                if outcome == scheduler_output.OWNERSHIP_LOST:
                    conn.rollback()
                    return DONE if _already_written(conn, repo, output, agent_id, "AVAILABLE") else OWNERSHIP_LOST
                conn.commit()
                output.offset += len(part)
        if output.offset < output.size:
            return CONTINUE
        if repo.complete(conn, output.ticket_id, agent_id, output.file_count, output.size):
            conn.commit()
            return DONE
        conn.rollback()
        return DONE if _already_written(conn, repo, output, agent_id, "AVAILABLE") else OWNERSHIP_LOST
    except scheduler_output.OutputOffsetMismatch:
        conn.rollback()
        output.started = False  # o proximo iniciar zera a gravacao deste agente e recomeca do inicio
        raise
    except Exception:
        conn.rollback()
        raise


def _already_written(conn, repo, output, agent_id, state_value):
    """COMMIT anterior sem resposta: a linha ja tem a situacao final deste agente?"""
    current = repo.output_state(conn, output.ticket_id)
    return current == (state_value, agent_id)


def remove_dir(output, plat):
    """Com o zip gravado (ou a pasta vazia), a pasta de saida sai pelo helper; as de cima ficam (limpeza manual, README §11.3)."""
    plat.clean_output(output.base, output.relative, output.exec_user)


def should_remove_dir(output):
    return output.result in (ZIP, EMPTY)
