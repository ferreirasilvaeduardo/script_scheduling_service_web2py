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

PRAZO_EMPACOTAR_S = 120
PARTES_POR_VOLTA = 4
TAMANHO_PARTE = scheduler_output.PART_MAX
NOME_ZIP = "saida.zip"

# Resultados do empacotamento.
ZIP = "ZIP"
VAZIA = "VAZIA"
EXCEDEU = "EXCEEDED"
FALHOU = "FAILED"
ABANDONADA = "ABANDONADA"

# Desfechos da gravacao.
CONTINUA = "CONTINUA"
CONCLUIDA = "CONCLUIDA"
OWNERSHIP_LOST = "OWNERSHIP_LOST"


class Saida(object):
    """Pasta de saida de um ticket: base (output_dir/<ambiente>), relativo e o estado das duas etapas."""

    def __init__(self, ticket_id, base, relativo, usuario_execucao, work_dir_ticket):
        self.ticket_id = int(ticket_id)
        self.base = base
        self.relativo = relativo
        self.usuario_execucao = usuario_execucao
        self.caminho_zip = os.path.join(work_dir_ticket, NOME_ZIP)
        self.processo = None
        self.prazo = None
        self.morto = False
        self.resultado = None
        self.motivo = None
        self.qtd_arquivos = None
        self.tamanho = None
        # Gravacao
        self.iniciada = False
        self.offset = 0
        self.proxima_tentativa = 0.0
        self.avisou_pendencia = False

    @property
    def pasta(self):
        return os.path.join(self.base, self.relativo)

    @property
    def empacotada(self):
        return self.resultado is not None


def iniciar_empacotar(saida, plat, max_bytes, max_arquivos, agora):
    """Abre o zip local (0600, do agente) e inicia o helper empacotar sem esperar."""
    try:
        fd = os.open(saida.caminho_zip, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            saida.processo = plat.iniciar_empacotar(saida.base, saida.relativo, max_bytes, max_arquivos, fd,
                                                    saida.usuario_execucao)
        finally:
            os.close(fd)
    except Exception as exc:  # noqa: BLE001 - qualquer falha local: FALHOU (o ticket segue)
        _log.warning("empacotamento da saida nao iniciado (%s)", exc.__class__.__name__,
                     extra={"ticket": saida.ticket_id, "action": "SAIDA"})
        saida.resultado, saida.motivo = FALHOU, "ERROR"
        return
    saida.prazo = agora + PRAZO_EMPACOTAR_S


def avancar_empacotar(saida, plat, agora):
    """Acompanha o empacotar sem esperar. True quando ha resultado (ZIP, VAZIA, EXCEDEU ou FALHOU)."""
    if saida.empacotada:
        return True
    rc = saida.processo.popen.poll()
    if rc is None:
        if agora >= saida.prazo and not saida.morto:
            saida.morto = True
            plat.sinalizar_grupo(saida.processo, signal.SIGKILL)
            _log.warning("empacotamento da saida passou de %d s: encerrado", PRAZO_EMPACOTAR_S,
                         extra={"ticket": saida.ticket_id, "action": "SAIDA"})
        return False
    if saida.morto:
        saida.resultado, saida.motivo = FALHOU, "DEADLINE"
    elif rc == 0:
        _conferir_zip(saida)
    elif rc == plat.SAIDA_VAZIA:
        saida.resultado = VAZIA
    elif rc == plat.SAIDA_EXCEDE_ARQUIVOS:
        saida.resultado, saida.motivo = EXCEDEU, "FILES"
    elif rc == plat.SAIDA_EXCEDE_BYTES:
        saida.resultado, saida.motivo = EXCEDEU, "BYTES"
    else:
        _log.warning("empacotamento da saida terminou com codigo %s", rc,
                     extra={"ticket": saida.ticket_id, "action": "SAIDA"})
        saida.resultado, saida.motivo = FALHOU, "ERROR"
    return True


def _conferir_zip(saida):
    """Le so o indice do zip gerado (quantidade de arquivos) e o tamanho; zip ilegivel e FALHOU."""
    try:
        with zipfile.ZipFile(saida.caminho_zip) as z:
            saida.qtd_arquivos = len(z.infolist())
        saida.tamanho = os.path.getsize(saida.caminho_zip)
    except (OSError, zipfile.BadZipFile) as exc:
        _log.warning("zip da saida ilegivel (%s)", exc.__class__.__name__,
                     extra={"ticket": saida.ticket_id, "action": "SAIDA"})
        saida.resultado, saida.motivo = FALHOU, "ERROR"
        return
    if saida.qtd_arquivos == 0 or saida.tamanho == 0:
        saida.resultado, saida.motivo = FALHOU, "ERROR"
        return
    saida.resultado = ZIP


def abandonar(saida, plat):
    """Parada do agente durante o empacotamento: encerra o helper; a pasta fica no disco (README §8.13)."""
    if saida.processo is not None and not saida.empacotada and saida.processo.popen.poll() is None:
        plat.sinalizar_grupo(saida.processo, signal.SIGKILL)
    saida.resultado, saida.motivo = ABANDONADA, None


def linha_log(saida, agente_id, max_arquivos, max_bytes):
    """Texto da linha [SSS] para o log do ticket (sem caminho nem conteudo), ou None."""
    if saida.resultado == EXCEDEU:
        limite = ("%d arquivos" % max_arquivos) if saida.motivo == "FILES" else \
            ("%d MiB" % (max_bytes // (1024 * 1024)))
        return "saida nao empacotada: excede o limite de %s (agente %s)" % (limite, agente_id)
    if saida.resultado == FALHOU:
        return "saida nao empacotada: %s (agente %s)" % (
            "prazo de %d s esgotado" % PRAZO_EMPACOTAR_S if saida.motivo == "DEADLINE" else "falha", agente_id)
    return None


def gravar(saida, conn, repo, agente_id):
    """Uma volta da gravacao: devolve CONTINUA, CONCLUIDA ou OWNERSHIP_LOST. Erro de banco: ROLLBACK e
    excecao (o chamador refaz a cada cancel_poll_interval_s). Nenhuma espera; ate PARTES_POR_VOLTA partes."""
    if saida.resultado == VAZIA:
        return CONCLUIDA
    try:
        if saida.resultado in (EXCEDEU, FALHOU):
            ok = repo.register_without_content(conn, saida.ticket_id, agente_id, saida.resultado, saida.motivo,
                                             saida.qtd_arquivos)
            conn.commit()
            return CONCLUIDA if ok or _ja_esta(conn, repo, saida, agente_id, saida.resultado) else OWNERSHIP_LOST
        if not saida.iniciada:
            if not repo.start(conn, saida.ticket_id, agente_id):
                conn.rollback()
                return CONCLUIDA if _ja_esta(conn, repo, saida, agente_id, "AVAILABLE") else OWNERSHIP_LOST
            conn.commit()
            saida.iniciada, saida.offset = True, 0
        with open(saida.caminho_zip, "rb") as f:
            for _i in range(PARTES_POR_VOLTA):
                if saida.offset >= saida.tamanho:
                    break
                f.seek(saida.offset)
                parte = f.read(TAMANHO_PARTE)
                desfecho = repo.append_chunk(conn, saida.ticket_id, agente_id, saida.offset, parte)
                if desfecho == scheduler_output.OWNERSHIP_LOST:
                    conn.rollback()
                    return CONCLUIDA if _ja_esta(conn, repo, saida, agente_id, "AVAILABLE") else OWNERSHIP_LOST
                conn.commit()
                saida.offset += len(parte)
        if saida.offset < saida.tamanho:
            return CONTINUA
        if repo.complete(conn, saida.ticket_id, agente_id, saida.qtd_arquivos, saida.tamanho):
            conn.commit()
            return CONCLUIDA
        conn.rollback()
        return CONCLUIDA if _ja_esta(conn, repo, saida, agente_id, "AVAILABLE") else OWNERSHIP_LOST
    except scheduler_output.OutputOffsetMismatch:
        conn.rollback()
        saida.iniciada = False  # o proximo iniciar zera a gravacao deste agente e recomeca do inicio
        raise
    except Exception:
        conn.rollback()
        raise


def _ja_esta(conn, repo, saida, agente_id, situacao):
    """COMMIT anterior sem resposta: a linha ja tem a situacao final deste agente?"""
    atual = repo.output_state(conn, saida.ticket_id)
    return atual == (situacao, agente_id)


def remover_pasta(saida, plat):
    """Com o zip gravado (ou a pasta vazia), a pasta de saida sai pelo helper; as de cima ficam para o purge."""
    plat.limpar_saida(saida.base, saida.relativo, saida.usuario_execucao)


def deve_remover_pasta(saida):
    return saida.resultado in (ZIP, VAZIA)
