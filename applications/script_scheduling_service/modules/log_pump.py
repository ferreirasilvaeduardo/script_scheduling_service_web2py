# -*- coding: utf-8 -*-
"""Coleta do log local do ticket para tbsss_tickets.log_output (README §8.10; CR-007 R-25; CR-008 R-11).

Uma Pump por ticket: le o arquivo em binario a partir do proprio offset (sem bloquear a escrita do filho),
decodifica UTF-8 de forma incremental (multibyte cortado fica para a proxima leitura), mascara com o
mascarador do ticket e aplica o teto do CLOB em bytes UTF-8, marcador incluido. O texto so sai da fila
depois do COMMIT do bloco (um bloco em voo por ticket). A Round coordena as bombas sob orcamento de tempo,
com rodizio, e o protocolo idempotente do repo_oracle.scheduler_log.anexar.

Nao conhece o SO nem abre conexoes: recebe a conexao e o repositorio. Relogio injetado; nada espera.
"""
import codecs
import logging
import os

import masking
from repo_oracle.scheduler_log import WRITTEN, ALREADY_WRITTEN, OWNERSHIP_LOST, LogOffsetMismatch

_log = logging.getLogger("sss_scheduler")

MARKER = "[SSS] log truncado no banco; arquivo integral no agente"
CHUNK_SIZE = 8000
DEFAULT_READ = 1024 * 1024

# Desfechos de envio (Round e final_flush).
OK = "OK"
UNCERTAIN_CONNECTION = "UNCERTAIN_CONNECTION"
INCONSISTENT = "INCONSISTENT"


def clob_units(text, supplementary_unit=2):
    """Comprimento do texto como o CLOB o conta: caractere fora do BMP vale unidade_suplementar posicoes
    (2 em AL32UTF8, UTF-16 interno; 1 num charset de um byte, onde vira o caractere de substituicao).
    O agente mede a unidade no banco (RepoSchedulerLog.unidade_suplementar)."""
    if supplementary_unit == 1:
        return len(text)
    return len(text.encode("utf-16-le")) // 2


def _bytes(text):
    return len(text.encode("utf-8"))


def _prefix_in_bytes(text, limit):
    """Maior prefixo de texto com ate limite bytes UTF-8, sem dividir caractere."""
    if limit <= 0:
        return ""
    return text.encode("utf-8")[:limit].decode("utf-8", "ignore")


def chunks(text, size=CHUNK_SIZE):
    """Divide o texto em pedacos de ate tamanho caracteres para o WRITEAPPEND."""
    return [text[i:i + size] for i in range(0, len(text), size)]


def ticket_masker(secrets, connection=None, snapshot=None):
    """Mascarador proprio do ticket (CR-007, R-25): segredos carregados, PADRAO_VALOR_RUN_CONEXAO_BD do
    ambiente e os valores de respostas cujos codigos estao em sensiveis no snapshot. Valores com menos
    de 4 caracteres nao sao registrados (regra do masking, README §4.1; risco aceito no §14)."""
    m = masking.Masker()
    for valor in secrets or ():
        m.register(valor)
    if connection:
        m.register(connection)
    snap = snapshot or {}
    respostas = snap.get("answers") or {}
    for codigo in snap.get("sensitive") or ():
        m.register(respostas.get(codigo))
    return m


class Pump(object):
    """Estado da coleta de um ticket. Grandezas separadas: bytes lidos do arquivo, bytes UTF-8 aceitos para
    o CLOB (teto) e offset confirmado em unidades do CLOB (= tbsss_tickets.log_offset_chars)."""

    def __init__(self, log_path, ticket_id, masker, max_log_size_bytes, max_local_log_size_bytes,
                 confirmed_offset_chars=0, supplementary_unit=2):
        self.log_path = log_path
        self.ticket_id = ticket_id
        self.max_log_size_bytes = int(max_log_size_bytes)
        self.max_local_log_size_bytes = int(max_local_log_size_bytes)
        self._marker_bytes = _bytes(MARKER)
        if self.max_log_size_bytes <= self._marker_bytes:
            raise ValueError("max_log_size_bytes menor que o marcador")
        # Leitura do arquivo.
        self.offset_bytes = 0
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._stream = masking.StreamMasker(masker)
        # Teto do CLOB: bytes ja aceitos (confirmados + fila) e o sufixo retido ate a decisao.
        self._accepted_bytes = 0
        self._held = ""
        self.truncated = False
        self.truncated_written = False
        # Envio: fila mascarada ainda nao confirmada e no maximo um bloco em voo.
        self._queue = ""
        self._in_flight = None
        self.confirmed_bytes = 0
        self.confirmed_offset_chars = int(confirmed_offset_chars)
        self.supplementary_unit = supplementary_unit
        self.finished = False
        self.stopped = False
        self.ownership_lost = False
        self.read_error = False

    # -- leitura -------------------------------------------------------------

    def _read(self, maximum):
        # open padrao do Python no POSIX nao bloqueia a escrita do filho (O_RDONLY, sem trava).
        with open(self.log_path, "rb") as f:
            f.seek(self.offset_bytes)
            dados = f.read(maximum) if maximum is not None else f.read()
        self.offset_bytes += len(dados)
        return dados

    def collect(self, max_bytes_leitura=DEFAULT_READ):
        """Le ate max_bytes_leitura bytes novos, decodifica, mascara e enfileira. Devolve o texto seguro
        enfileirado (ja com o teto aplicado)."""
        if self.finished or self.stopped or self.truncated:
            return ""
        texto = self._decoder.decode(self._read(max_bytes_leitura))
        enviar, _truncou = self.apply_db_cap(self._stream.feed(texto))
        self._queue += enviar
        return enviar

    def finalize(self):
        """Depois do fim do processo: drena o arquivo em blocos de 1 MiB (parando de ler ao truncar), fecha
        decoder e mascarador e libera o sufixo retido (sem marcador, se o teto nao foi excedido).
        Idempotente. Arquivo ilegivel: WARN e envia o que ja foi lido. Devolve o texto enfileirado."""
        if self.finished or self.stopped:
            return ""
        enfileirado = []
        while not self.truncated:
            try:
                dados = self._read(DEFAULT_READ)
            except OSError as e:
                self._warn_read(e)
                break
            if not dados:
                break
            enviar, _truncou = self.apply_db_cap(self._stream.feed(self._decoder.decode(dados)))
            enfileirado.append(enviar)
        resto = self._decoder.decode(b"", final=True)
        enviar, _truncou = self.apply_db_cap(self._stream.feed(resto) + self._stream.finalize())
        if not self.truncated:
            enviar += self._held
            self._accepted_bytes += _bytes(self._held)
            self._held = ""
        enfileirado.append(enviar)
        texto = "".join(enfileirado)
        self._queue += texto
        self.finished = True
        return texto

    def _warn_read(self, error):
        """WARN uma vez por bomba quando o arquivo de log some ou fica ilegivel."""
        if not self.read_error:
            self.read_error = True
            _log.warning("log local ilegivel (%s); coleta do ticket suspensa", error.__class__.__name__,
                         extra={"ticket": self.ticket_id, "action": "LOG"})

    # -- limites -------------------------------------------------------------

    def local_exceeded(self):
        """Arquivo local acima de max_local_log_size_bytes (LOG_LIMIT, README §8.10)."""
        try:
            return os.path.getsize(self.log_path) > self.max_local_log_size_bytes
        except OSError:  # arquivo ausente: nada a medir; a leitura registra o WARN
            return False

    def apply_db_cap(self, text):
        """(texto_para_enviar, truncou). O total no CLOB, marcador incluido, nunca passa do teto.

        Enquanto cabe, envia ate max - bytes_do_marcador e retem o resto (no maximo o tamanho do marcador),
        para decidir no fim entre o conteudo integral e o corte com marcador. Ao exceder, envia o prefixo que
        cabe antes do marcador e o marcador, uma unica vez.
        """
        if self.truncated:
            return "", True
        buf = self._held + (text or "")
        disponivel = self.max_log_size_bytes - self._accepted_bytes
        antes_do_marcador = self.max_log_size_bytes - self._marker_bytes - self._accepted_bytes
        prefixo = _prefix_in_bytes(buf, antes_do_marcador)
        if _bytes(buf) <= disponivel:
            self._held = buf[len(prefixo):]
            self._accepted_bytes += _bytes(prefixo)
            return prefixo, False
        enviar = prefixo + MARKER
        self._held = ""
        self._accepted_bytes += _bytes(enviar)
        self.truncated = True
        _log.warning("log truncado no banco (max_log_size_bytes)", extra={"ticket": self.ticket_id,
                                                                          "action": "LOG"})
        return enviar, True

    # -- envio ---------------------------------------------------------------

    def pending(self):
        """Ha bloco a enviar ou marcacao de truncado a gravar."""
        return bool(self._in_flight or self._queue) or (self.truncated and not self.truncated_written)

    def next_chunk(self):
        """(bloco, expected_offset) do bloco em voo, ou do proximo da fila; None se a fila esta vazia.
        Repetido ate confirmar: a mesma operacao e reapresentada depois de um COMMIT incerto."""
        if self._in_flight is None and self._queue:
            self._in_flight = (self._queue[:CHUNK_SIZE], self.confirmed_offset_chars)
        return self._in_flight

    def confirm(self):
        """O bloco em voo foi confirmado (WRITTEN ou ALREADY_WRITTEN seguido de COMMIT)."""
        bloco, _offset = self._in_flight
        self._queue = self._queue[len(bloco):]
        self.confirmed_offset_chars += clob_units(bloco, self.supplementary_unit)
        self.confirmed_bytes += _bytes(bloco)
        self._in_flight = None


def _rollback(conn):
    try:
        conn.rollback()
    except Exception as e:  # noqa: BLE001 - a conexao sera tratada como incerta pelo chamador
        _log.warning("rollback falhou (%s)", e.__class__.__name__, extra={"action": "LOG"})


def _send_one(pump, conn, repo, agent_id):
    """Envia o proximo passo pendente da bomba: OK, OWNERSHIP_LOST, INCONSISTENTE ou UNCERTAIN_CONNECTION."""
    item = pump.next_chunk()
    try:
        if item is not None:
            bloco, offset = item
            resultado = repo.append_chunk(conn, pump.ticket_id, agent_id, offset, bloco)
        else:
            resultado = WRITTEN if repo.mark_truncated(conn, pump.ticket_id, agent_id) else OWNERSHIP_LOST
    except LogOffsetMismatch as e:
        _rollback(conn)
        pump.stopped = True
        _log.error("pump interrompido: %s", e, extra={"ticket": pump.ticket_id, "action": "LOG"})
        return INCONSISTENT
    except Exception as e:  # noqa: BLE001 - erro de banco: mesmo bloco reapresentado numa conexao nova
        _rollback(conn)
        _log.warning("envio do log falhou (%s); bloco mantido", e.__class__.__name__,
                     extra={"ticket": pump.ticket_id, "action": "LOG"})
        return UNCERTAIN_CONNECTION
    if resultado == OWNERSHIP_LOST:
        _rollback(conn)
        pump.ownership_lost = True
        return OWNERSHIP_LOST
    try:
        conn.commit()
    except Exception as e:  # noqa: BLE001 - desfecho desconhecido: a repeticao reconcilia (ALREADY_WRITTEN)
        _log.warning("COMMIT do log incerto (%s); bloco mantido", e.__class__.__name__,
                     extra={"ticket": pump.ticket_id, "action": "LOG"})
        return UNCERTAIN_CONNECTION
    if item is not None:
        pump.confirm()
    else:
        pump.truncated_written = True
    return OK


class RoundResult(object):
    def __init__(self):
        self.served = []
        self.ownership_lost = []
        self.inconsistent = []
        self.uncertain_connection = False
        self.budget_exhausted = False


class Round(object):
    """Rodadas de coleta sob orcamento (CR-008, R-11). bombas: dict ticket_id -> Pump, mantido pelo laco.

    Cada execucao coleta todas as bombas e envia um bloco por ticket em rodizio (por ticket_id), a partir do
    ticket seguinte ao ultimo atendido, ate a fila esvaziar ou o tempo gasto passar de budget_s
    (heartbeat_interval_s / 2), mesmo no meio da fila. O rodizio bloco a bloco impede que um ticket verboso
    deixe os outros sem envio. O primeiro bloco da rodada sempre sai. Erro de banco ou COMMIT incerto
    encerra a rodada com uncertain_connection: o laco reconecta e a mesma operacao e reapresentada.
    """

    def __init__(self, pumps, monotonic_clock, budget_s):
        self.pumps = pumps
        self.clock = monotonic_clock
        self.budget_s = budget_s
        self._last = None

    def _order(self):
        ids = sorted(self.pumps)
        if self._last is None:
            return ids
        depois = [t for t in ids if t > self._last]
        return depois + [t for t in ids if t <= self._last]

    def run(self, conn, repo, agent_id):
        res = RoundResult()
        inicio = self.clock()
        ativos = []
        for ticket_id in self._order():
            bomba = self.pumps[ticket_id]
            if bomba.stopped or bomba.ownership_lost or bomba.finished:
                continue
            try:
                bomba.collect()
            except OSError as e:
                # Um arquivo ilegivel nao para a coleta dos outros tickets; o envio do que ja foi lido segue.
                bomba._warn_read(e)
            ativos.append(ticket_id)
        while True:
            com_pendencia = [t for t in ativos if self.pumps[t].pending()]
            if not com_pendencia:
                return res
            for ticket_id in com_pendencia:
                if res.served and self.clock() - inicio > self.budget_s:
                    res.budget_exhausted = True
                    return res
                desfecho = _send_one(self.pumps[ticket_id], conn, repo, agent_id)
                if ticket_id not in res.served:
                    res.served.append(ticket_id)
                self._last = ticket_id
                if desfecho == UNCERTAIN_CONNECTION:
                    res.uncertain_connection = True
                    return res
                if desfecho in (OWNERSHIP_LOST, INCONSISTENT):
                    (res.ownership_lost if desfecho == OWNERSHIP_LOST else res.inconsistent).append(ticket_id)
                    ativos.remove(ticket_id)


def final_flush(pump, conn, repo, agent_id):
    """Flush final de um ticket terminado, sem orcamento (o laco faz um por iteracao).

    Devolve OK (tudo confirmado), OWNERSHIP_LOST, INCONSISTENTE ou UNCERTAIN_CONNECTION (repetir na proxima
    iteracao com a mesma bomba: nada confirmado se perde nem se duplica).
    """
    if pump.stopped:
        return INCONSISTENT
    if pump.ownership_lost:
        return OWNERSHIP_LOST
    pump.finalize()
    while pump.pending():
        desfecho = _send_one(pump, conn, repo, agent_id)
        if desfecho != OK:
            return desfecho
    return OK
