# -*- coding: utf-8 -*-
"""Mascaramento de segredos em texto, fluxos em blocos e logs (README §4.1, §8.10).

Modulo puro: nao importa gluon (AGENTS §7.1).
"""
import logging
import re
import threading

MASK = "****"
MIN_LENGTH = 4

# usuario/senha@dsn -> usuario/****@dsn. O lookbehind impede tentar a partir do meio de uma sequencia de
# caracteres do usuario: sem ele, uma linha longa sem '/' custava tempo quadratico (F8.2, log_pump). O
# resultado e o mesmo, porque o match mais a esquerda sempre comeca no inicio da sequencia.
_RE_CONNECT = re.compile(r"(?<![A-Za-z0-9_$#.])([A-Za-z0-9_$#.]+)/([^\s/@]+)@(?=\S)")
_FILTER_MARK = "_sss_filtro_masking"
_RE_TOKEN_FINAL = re.compile(r"\S+\Z")
MAX_HELD_TOKEN = 512


class Masker(object):
    """Substitui segredos registrados por '****' (o mais longo primeiro)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._segredos = []
        self._regex = None
        self.max_len = 0

    def register(self, valor):
        """Registra um segredo; valores nao str ou com menos de 4 caracteres sao ignorados."""
        if not isinstance(valor, str) or len(valor) < MIN_LENGTH:
            return
        with self._lock:
            if valor in self._segredos:
                return
            segredos = sorted(self._segredos + [valor], key=len, reverse=True)
            self._regex = re.compile("|".join(re.escape(s) for s in segredos))
            self._segredos = segredos
            self.max_len = len(segredos[0])

    @property
    def regex(self):
        return self._regex

    def mask(self, texto):
        """Mascara segredos registrados e senhas em connect strings."""
        if not isinstance(texto, str) or not texto:
            return texto
        regex = self._regex
        if regex is not None:
            texto = regex.sub(MASK, texto)
        return _RE_CONNECT.sub(r"\1/" + MASK + "@", texto)


def _trim_connect_string(texto, corte):
    # Um corte dentro de 'usuario/senha@dsn' emitiria parte da senha sem casar o padrao:
    # nunca corta um token sem espaco ainda nao terminado (limite de MAX_HELD_TOKEN caracteres).
    if corte < len(texto) and texto[corte].isspace():
        return corte
    m = _RE_TOKEN_FINAL.search(texto, max(0, corte - MAX_HELD_TOKEN), corte)
    return m.start() if m else corte


class StreamMasker(object):
    """Mascara um fluxo em blocos retendo a cauda que pode conter um segredo cortado."""

    def __init__(self, mascarador):
        self._mascarador = mascarador
        self._pendente = ""

    def feed(self, bloco):
        """Recebe um bloco e devolve o texto ja seguro para emissao."""
        texto = self._pendente + (bloco or "")
        regex = self._mascarador.regex
        corte = len(texto)
        if regex is not None:
            corte = max(0, corte - (self._mascarador.max_len - 1))
        corte = _trim_connect_string(texto, corte)
        if regex is None:
            self._pendente = texto[corte:]
            return self._mascarador.mask(texto[:corte])
        # Um segredo que comece antes do corte cabe inteiro no texto (len <= max_len);
        # se ele atravessa o corte, o corte avanca para o fim do match.
        pedacos = []
        pos = 0
        for m in regex.finditer(texto):
            if m.start() >= corte:
                break
            pedacos.append(texto[pos:m.start()])
            pedacos.append(MASK)
            pos = m.end()
            if pos > corte:
                corte = pos
        pedacos.append(texto[pos:corte])
        self._pendente = texto[corte:]
        return self._mascarador.mask("".join(pedacos))

    def finalize(self):
        """Mascara e devolve o restante retido."""
        resto, self._pendente = self._pendente, ""
        return self._mascarador.mask(resto)


def _mask_arg(mascarador, valor):
    if valor is None or isinstance(valor, (bool, int, float)):
        return valor
    if isinstance(valor, str):
        return mascarador.mask(valor)
    return mascarador.mask(str(valor))


class _MaskFilter(logging.Filter):

    def __init__(self, mascarador):
        super(_MaskFilter, self).__init__()
        self.mascarador = mascarador

    def filter(self, record):
        m = self.mascarador
        if isinstance(record.msg, str):
            record.msg = m.mask(record.msg)
        else:
            record.msg = _mask_arg(m, record.msg)
        if isinstance(record.args, dict):
            record.args = dict((k, _mask_arg(m, v)) for k, v in record.args.items())
        elif record.args:
            record.args = tuple(_mask_arg(m, a) for a in record.args)
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = m.mask(record.exc_text)
        if record.stack_info:
            record.stack_info = m.mask(record.stack_info)
        return True


def logging_filter(mascarador):
    """logging.Filter que mascara msg, args e traceback do registro."""
    return _MaskFilter(mascarador)


MASKER = Masker()


def register_secret(valor):
    """Registra um segredo no mascarador global do processo."""
    MASKER.register(valor)


def install_filter_on_handlers(mascarador=None):
    """Instala (uma vez por handler) o filtro de mascaramento em todos os handlers de log."""
    mascarador = mascarador or MASKER
    loggers = [logging.getLogger()]
    for lg in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(lg, logging.Logger):
            loggers.append(lg)
    for lg in loggers:
        for handler in list(lg.handlers):
            if getattr(handler, _FILTER_MARK, None) is mascarador:
                continue
            handler.addFilter(logging_filter(mascarador))
            setattr(handler, _FILTER_MARK, mascarador)
