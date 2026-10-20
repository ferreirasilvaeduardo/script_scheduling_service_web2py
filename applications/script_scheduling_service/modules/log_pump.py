# -*- coding: utf-8 -*-
"""Coleta do log local do ticket para tbsss_tickets.log_output (README §8.10; CR-007 R-25; CR-008 R-11).

Uma Bomba por ticket: le o arquivo em binario a partir do proprio offset (sem bloquear a escrita do filho),
decodifica UTF-8 de forma incremental (multibyte cortado fica para a proxima leitura), mascara com o
mascarador do ticket e aplica o teto do CLOB em bytes UTF-8, marcador incluido. O texto so sai da fila
depois do COMMIT do bloco (um bloco em voo por ticket). A Rodada coordena as bombas sob orcamento de tempo,
com rodizio, e o protocolo idempotente do repo_oracle.scheduler_log.anexar.

Nao conhece o SO nem abre conexoes: recebe a conexao e o repositorio. Relogio injetado; nada espera.
"""
import codecs
import logging
import os

import masking
from repo_oracle.scheduler_log import GRAVADO, JA_GRAVADO, POSSE_PERDIDA, LogOffsetInconsistente

_log = logging.getLogger("sss_scheduler")

MARCADOR = "[SSS] log truncado no banco; arquivo integral no agente"
TAMANHO_BLOCO = 8000
LEITURA_PADRAO = 1024 * 1024

# Desfechos de envio (Rodada e flush_final).
OK = "OK"
CONEXAO_INCERTA = "CONEXAO_INCERTA"
INCONSISTENTE = "INCONSISTENTE"


def unidades_clob(texto, unidade_suplementar=2):
    """Comprimento do texto como o CLOB o conta: caractere fora do BMP vale unidade_suplementar posicoes
    (2 em AL32UTF8, UTF-16 interno; 1 num charset de um byte, onde vira o caractere de substituicao).
    O agente mede a unidade no banco (RepoSchedulerLog.unidade_suplementar)."""
    if unidade_suplementar == 1:
        return len(texto)
    return len(texto.encode("utf-16-le")) // 2


def _bytes(texto):
    return len(texto.encode("utf-8"))


def _prefixo_em_bytes(texto, limite):
    """Maior prefixo de texto com ate limite bytes UTF-8, sem dividir caractere."""
    if limite <= 0:
        return ""
    return texto.encode("utf-8")[:limite].decode("utf-8", "ignore")


def blocos(texto, tamanho=TAMANHO_BLOCO):
    """Divide o texto em pedacos de ate tamanho caracteres para o WRITEAPPEND."""
    return [texto[i:i + tamanho] for i in range(0, len(texto), tamanho)]


def mascarador_do_ticket(segredos, conexao=None, snapshot=None):
    """Mascarador proprio do ticket (CR-007, R-25): segredos carregados, PADRAO_VALOR_RUN_CONEXAO_BD do
    ambiente e os valores de respostas cujos codigos estao em sensiveis no snapshot. Valores com menos
    de 4 caracteres nao sao registrados (regra do masking, README §4.1; risco aceito no §14)."""
    m = masking.Mascarador()
    for valor in segredos or ():
        m.registrar(valor)
    if conexao:
        m.registrar(conexao)
    snap = snapshot or {}
    respostas = snap.get("respostas") or {}
    for codigo in snap.get("sensiveis") or ():
        m.registrar(respostas.get(codigo))
    return m


class Bomba(object):
    """Estado da coleta de um ticket. Grandezas separadas: bytes lidos do arquivo, bytes UTF-8 aceitos para
    o CLOB (teto) e offset confirmado em unidades do CLOB (= tbsss_tickets.log_offset_chars)."""

    def __init__(self, caminho_log, ticket_id, mascarador, max_log_size_bytes, max_local_log_size_bytes,
                 offset_confirmado_chars=0, unidade_suplementar=2):
        self.caminho_log = caminho_log
        self.ticket_id = ticket_id
        self.max_log_size_bytes = int(max_log_size_bytes)
        self.max_local_log_size_bytes = int(max_local_log_size_bytes)
        self._bytes_marcador = _bytes(MARCADOR)
        if self.max_log_size_bytes <= self._bytes_marcador:
            raise ValueError("max_log_size_bytes menor que o marcador")
        # Leitura do arquivo.
        self.offset_bytes = 0
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._fluxo = masking.MascaradorFluxo(mascarador)
        # Teto do CLOB: bytes ja aceitos (confirmados + fila) e o sufixo retido ate a decisao.
        self._bytes_aceitos = 0
        self._retido = ""
        self.truncado = False
        self.truncado_gravado = False
        # Envio: fila mascarada ainda nao confirmada e no maximo um bloco em voo.
        self._fila = ""
        self._em_voo = None
        self.bytes_confirmados = 0
        self.offset_confirmado_chars = int(offset_confirmado_chars)
        self.unidade_suplementar = unidade_suplementar
        self.finalizada = False
        self.parada = False
        self.posse_perdida = False

    # -- leitura -------------------------------------------------------------

    def _ler(self, maximo):
        # open padrao do Python no POSIX nao bloqueia a escrita do filho (O_RDONLY, sem trava).
        with open(self.caminho_log, "rb") as f:
            f.seek(self.offset_bytes)
            dados = f.read(maximo) if maximo is not None else f.read()
        self.offset_bytes += len(dados)
        return dados

    def coletar(self, max_bytes_leitura=LEITURA_PADRAO):
        """Le ate max_bytes_leitura bytes novos, decodifica, mascara e enfileira. Devolve o texto seguro
        enfileirado (ja com o teto aplicado)."""
        if self.finalizada or self.parada or self.truncado:
            return ""
        texto = self._decoder.decode(self._ler(max_bytes_leitura))
        enviar, _truncou = self.aplicar_teto_banco(self._fluxo.alimentar(texto))
        self._fila += enviar
        return enviar

    def finalizar(self):
        """Depois do fim do processo: drena o arquivo, fecha decoder e mascarador e libera o sufixo retido
        (sem marcador, se o teto nao foi excedido). Idempotente. Devolve o texto enfileirado."""
        if self.finalizada or self.parada:
            return ""
        partes = []
        if not self.truncado:
            while True:
                dados = self._ler(LEITURA_PADRAO)
                partes.append(self._decoder.decode(dados))
                if not dados:
                    break
        texto = "".join(partes) + self._decoder.decode(b"", final=True)
        seguro = self._fluxo.alimentar(texto) + self._fluxo.finalizar()
        enviar, _truncou = self.aplicar_teto_banco(seguro)
        if not self.truncado:
            enviar += self._retido
            self._bytes_aceitos += _bytes(self._retido)
            self._retido = ""
        self._fila += enviar
        self.finalizada = True
        return enviar

    # -- limites -------------------------------------------------------------

    def excedeu_local(self):
        """Arquivo local acima de max_local_log_size_bytes (LOG_LIMIT, README §8.10)."""
        try:
            return os.path.getsize(self.caminho_log) > self.max_local_log_size_bytes
        except OSError:
            return False

    def aplicar_teto_banco(self, texto):
        """(texto_para_enviar, truncou). O total no CLOB, marcador incluido, nunca passa do teto.

        Enquanto cabe, envia ate max - bytes_do_marcador e retem o resto (no maximo o tamanho do marcador),
        para decidir no fim entre o conteudo integral e o corte com marcador. Ao exceder, envia o prefixo que
        cabe antes do marcador e o marcador, uma unica vez.
        """
        if self.truncado:
            return "", True
        buf = self._retido + (texto or "")
        disponivel = self.max_log_size_bytes - self._bytes_aceitos
        antes_do_marcador = self.max_log_size_bytes - self._bytes_marcador - self._bytes_aceitos
        prefixo = _prefixo_em_bytes(buf, antes_do_marcador)
        if _bytes(buf) <= disponivel:
            self._retido = buf[len(prefixo):]
            self._bytes_aceitos += _bytes(prefixo)
            return prefixo, False
        enviar = prefixo + MARCADOR
        self._retido = ""
        self._bytes_aceitos += _bytes(enviar)
        self.truncado = True
        _log.warning("log truncado no banco (max_log_size_bytes)", extra={"ticket": self.ticket_id,
                                                                          "acao": "LOG"})
        return enviar, True

    # -- envio ---------------------------------------------------------------

    def pendente(self):
        """Ha bloco a enviar ou marcacao de truncado a gravar."""
        return bool(self._em_voo or self._fila) or (self.truncado and not self.truncado_gravado)

    def proximo_bloco(self):
        """(bloco, offset_esperado) do bloco em voo, ou do proximo da fila; None se a fila esta vazia.
        Repetido ate confirmar: a mesma operacao e reapresentada depois de um COMMIT incerto."""
        if self._em_voo is None and self._fila:
            self._em_voo = (self._fila[:TAMANHO_BLOCO], self.offset_confirmado_chars)
        return self._em_voo

    def confirmar(self):
        """O bloco em voo foi confirmado (GRAVADO ou JA_GRAVADO seguido de COMMIT)."""
        bloco, _offset = self._em_voo
        self._fila = self._fila[len(bloco):]
        self.offset_confirmado_chars += unidades_clob(bloco, self.unidade_suplementar)
        self.bytes_confirmados += _bytes(bloco)
        self._em_voo = None


def _rollback(conn):
    try:
        conn.rollback()
    except Exception as e:  # noqa: BLE001 - a conexao sera tratada como incerta pelo chamador
        _log.warning("rollback falhou (%s)", e.__class__.__name__, extra={"acao": "LOG"})


def _enviar_um(bomba, conn, repo, agente_id):
    """Envia o proximo passo pendente da bomba: OK, POSSE_PERDIDA, INCONSISTENTE ou CONEXAO_INCERTA."""
    item = bomba.proximo_bloco()
    try:
        if item is not None:
            bloco, offset = item
            resultado = repo.anexar(conn, bomba.ticket_id, agente_id, offset, bloco)
        else:
            resultado = GRAVADO if repo.marcar_truncado(conn, bomba.ticket_id, agente_id) else POSSE_PERDIDA
    except LogOffsetInconsistente as e:
        _rollback(conn)
        bomba.parada = True
        _log.error("pump interrompido: %s", e, extra={"ticket": bomba.ticket_id, "acao": "LOG"})
        return INCONSISTENTE
    except Exception as e:  # noqa: BLE001 - erro de banco: mesmo bloco reapresentado numa conexao nova
        _rollback(conn)
        _log.warning("envio do log falhou (%s); bloco mantido", e.__class__.__name__,
                     extra={"ticket": bomba.ticket_id, "acao": "LOG"})
        return CONEXAO_INCERTA
    if resultado == POSSE_PERDIDA:
        _rollback(conn)
        bomba.posse_perdida = True
        return POSSE_PERDIDA
    try:
        conn.commit()
    except Exception as e:  # noqa: BLE001 - desfecho desconhecido: a repeticao reconcilia (JA_GRAVADO)
        _log.warning("COMMIT do log incerto (%s); bloco mantido", e.__class__.__name__,
                     extra={"ticket": bomba.ticket_id, "acao": "LOG"})
        return CONEXAO_INCERTA
    if item is not None:
        bomba.confirmar()
    else:
        bomba.truncado_gravado = True
    return OK


class ResultadoRodada(object):
    def __init__(self):
        self.atendidos = []
        self.posse_perdida = []
        self.inconsistentes = []
        self.conexao_incerta = False
        self.esgotou_orcamento = False


class Rodada(object):
    """Rodadas de coleta sob orcamento (CR-008, R-11). bombas: dict ticket_id -> Bomba, mantido pelo laco.

    Cada execucao coleta todas as bombas e envia um bloco por ticket em rodizio (por ticket_id), a partir do
    ticket seguinte ao ultimo atendido, ate a fila esvaziar ou o tempo gasto passar de orcamento_s
    (heartbeat_interval_s / 2), mesmo no meio da fila. O rodizio bloco a bloco impede que um ticket verboso
    deixe os outros sem envio. O primeiro bloco da rodada sempre sai. Erro de banco ou COMMIT incerto
    encerra a rodada com conexao_incerta: o laco reconecta e a mesma operacao e reapresentada.
    """

    def __init__(self, bombas, relogio_monotonico, orcamento_s):
        self.bombas = bombas
        self.relogio = relogio_monotonico
        self.orcamento_s = orcamento_s
        self._ultimo = None

    def _ordem(self):
        ids = sorted(self.bombas)
        if self._ultimo is None:
            return ids
        depois = [t for t in ids if t > self._ultimo]
        return depois + [t for t in ids if t <= self._ultimo]

    def executar(self, conn, repo, agente_id):
        res = ResultadoRodada()
        inicio = self.relogio()
        ativos = []
        for ticket_id in self._ordem():
            bomba = self.bombas[ticket_id]
            if bomba.parada or bomba.posse_perdida or bomba.finalizada:
                continue
            bomba.coletar()
            ativos.append(ticket_id)
        while True:
            com_pendencia = [t for t in ativos if self.bombas[t].pendente()]
            if not com_pendencia:
                return res
            for ticket_id in com_pendencia:
                if res.atendidos and self.relogio() - inicio > self.orcamento_s:
                    res.esgotou_orcamento = True
                    return res
                desfecho = _enviar_um(self.bombas[ticket_id], conn, repo, agente_id)
                if ticket_id not in res.atendidos:
                    res.atendidos.append(ticket_id)
                self._ultimo = ticket_id
                if desfecho == CONEXAO_INCERTA:
                    res.conexao_incerta = True
                    return res
                if desfecho in (POSSE_PERDIDA, INCONSISTENTE):
                    (res.posse_perdida if desfecho == POSSE_PERDIDA else res.inconsistentes).append(ticket_id)
                    ativos.remove(ticket_id)


def flush_final(bomba, conn, repo, agente_id):
    """Flush final de um ticket terminado, sem orcamento (o laco faz um por iteracao).

    Devolve OK (tudo confirmado), POSSE_PERDIDA, INCONSISTENTE ou CONEXAO_INCERTA (repetir na proxima
    iteracao com a mesma bomba: nada confirmado se perde nem se duplica).
    """
    if bomba.parada:
        return INCONSISTENTE
    if bomba.posse_perdida:
        return POSSE_PERDIDA
    bomba.finalizar()
    while bomba.pendente():
        desfecho = _enviar_um(bomba, conn, repo, agente_id)
        if desfecho != OK:
            return desfecho
    return OK
