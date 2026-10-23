# -*- coding: utf-8 -*-
"""Entrega de um envio da tela na pasta de entrada (CR-020c, README §8.14): maquina de estados sem espera.

Uma entrega por vez, avancada a cada volta do laco do agente:
  1. baixar: o arquivo sai do banco em partes de 1 MiB (ate PARTS_PER_ROUND por volta) para um temporario do
     agente (work_dir/input/delivery_<id>.part, 0600); no fim, tamanho e SHA-256 conferidos;
  2. gravar: o helper put-input roda num grupo proprio, como o usuario de execucao, com o temporario na entrada
     padrao (ele nunca le o work_dir), acompanhado por poll() e com prazo fixo;
  3. marcar: DELIVERED ou FAILED pelo repositorio (INPUT_DELIVERY na mesma transacao); o temporario e apagado.
O conteudo do arquivo nunca vai para log nenhum. Toda primitiva de SO vem de `os_platform`.
"""
import hashlib
import logging
import os
import signal

import repo_inputs
from repo_errors import RepoNotFound

_log = logging.getLogger("sss_scheduler")

PARTS_PER_ROUND = 4
PART_SIZE = repo_inputs.PART_MAX
PUT_DEADLINE_S = 120
INPUT_DIR = "input"

# Etapas
DOWNLOAD = "DOWNLOAD"
WRITE = "WRITE"
MARK = "MARK"


def work_folder(work_dir):
    """Pasta dos temporarios das entregas, dentro do work_dir do agente."""
    return os.path.join(work_dir, INPUT_DIR)


def clean_leftovers(work_dir):
    """Subida e parada: apaga os temporarios .part que sobraram (as entregas seguem PENDING e recomecam)."""
    folder = work_folder(work_dir)
    os.makedirs(folder, 0o700, exist_ok=True)
    removed = 0
    for name in os.listdir(folder):
        if name.startswith("delivery_") and name.endswith(".part"):
            os.unlink(os.path.join(folder, name))
            removed += 1
    return removed


class Delivery(object):
    """Uma entrega PENDING deste agente (linha de pending_deliveries) e o estado das tres etapas."""

    def __init__(self, row, work_dir):
        self.id = int(row["id"])
        self.upload_id = int(row["upload_id"])
        self.environment = row["environment"]
        self.script_id = int(row["script_id"])
        self.script_name = row["script_name"]
        self.relative_dir = row.get("relative_dir")
        self.file_name = row["file_name"]
        self.size = int(row["size_bytes"])
        self.sha256 = row["sha256"]
        self.replace = row["replace_existing"]
        self.part_path = os.path.join(work_folder(work_dir), "delivery_%d.part" % self.id)
        self.step = DOWNLOAD
        self.offset = 0
        self.process = None
        self.deadline = None
        self.dead = False
        self.state = None
        self.reason = None
        self.next_attempt = 0.0
        self.pending_warned = False

    def fail(self, reason):
        self.state, self.reason, self.step = "FAILED", reason, MARK


def download(delivery, conn, repo):
    """Baixa ate PARTS_PER_ROUND partes; no fim confere tamanho e hash (divergencia: FAILED HASH)."""
    mode = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if delivery.offset else os.O_TRUNC)
    fd = os.open(delivery.part_path, mode, 0o600)
    part = None
    try:
        for _n in range(PARTS_PER_ROUND):
            if delivery.offset >= delivery.size:
                break
            try:
                part = repo.read_content(delivery.upload_id, delivery.offset, PART_SIZE, conn=conn)
            except RepoNotFound:
                # Conteudo ja esvaziado pelo purge ou envio removido: nada a gravar.
                delivery.fail("ERROR")
                return
            if not part:
                break
            os.write(fd, part)
            delivery.offset += len(part)
    finally:
        os.close(fd)
    if delivery.offset < delivery.size and part:
        return
    digest = hashlib.sha256()
    with open(delivery.part_path, "rb") as f:
        for chunk in iter(lambda: f.read(PART_SIZE), b""):
            digest.update(chunk)
    if delivery.offset != delivery.size or digest.hexdigest() != delivery.sha256:
        _log.warning("entrega %s: o arquivo baixado do banco nao confere com o tamanho e o hash do envio",
                     delivery.id, extra={"action": "ENTRADA"})
        delivery.fail("HASH")
        return
    delivery.step = WRITE


def start_write(delivery, plat, base, script_dir, exec_user, now):
    """Inicia o helper put-input sem esperar, com o temporario na entrada padrao."""
    try:
        fd = os.open(delivery.part_path, os.O_RDONLY)
        try:
            delivery.process = plat.start_put_input(base, script_dir, delivery.relative_dir, delivery.file_name,
                                                    delivery.replace, delivery.sha256, delivery.size, fd, exec_user)
        finally:
            os.close(fd)
    except Exception as exc:  # noqa: BLE001 - qualquer falha local: FAILED ERROR
        _log.warning("entrega %s nao iniciada (%s)", delivery.id, exc.__class__.__name__,
                     extra={"action": "ENTRADA"})
        delivery.fail("ERROR")
        return
    delivery.deadline = now + PUT_DEADLINE_S


def advance_write(delivery, plat, now):
    """Acompanha o put-input sem esperar. True quando ha resultado (DELIVERED ou FAILED com motivo)."""
    rc = delivery.process.popen.poll()
    if rc is None:
        if now >= delivery.deadline and not delivery.dead:
            delivery.dead = True
            plat.signal_group(delivery.process, signal.SIGKILL)
            _log.warning("entrega %s passou de %d s: encerrada", delivery.id, PUT_DEADLINE_S,
                         extra={"action": "ENTRADA"})
        return False
    if delivery.dead:
        delivery.fail("ERROR")
    elif rc == 0:
        delivery.state, delivery.reason, delivery.step = "DELIVERED", None, MARK
    elif rc == plat.INPUT_EXISTS:
        delivery.fail("EXISTS")
    elif rc == plat.INPUT_SPACE:
        delivery.fail("SPACE")
    elif rc == plat.INPUT_HASH:
        delivery.fail("HASH")
    elif rc == 2:
        delivery.fail("NAME")
    else:
        _log.warning("entrega %s: helper put-input terminou com codigo %s", delivery.id, rc,
                     extra={"action": "ENTRADA"})
        delivery.fail("ERROR")
    return True


def mark(delivery, conn, repo, agent_id):
    """Grava o resultado (INPUT_DELIVERY na mesma transacao). False: a entrega nao e mais deste agente."""
    return repo.mark_delivery(delivery.id, agent_id, delivery.state, delivery.reason, conn=conn)


def discard(delivery, plat):
    """Fim da entrega (ou parada do agente): encerra o helper vivo e apaga o temporario."""
    if delivery.process is not None and delivery.process.popen.poll() is None:
        plat.signal_group(delivery.process, signal.SIGKILL)
    try:
        os.unlink(delivery.part_path)
    except FileNotFoundError:  # fluxo previsto: falhou antes de baixar ou ja apagado
        pass
