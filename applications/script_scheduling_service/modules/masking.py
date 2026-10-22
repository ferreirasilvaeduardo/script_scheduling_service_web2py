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
        self._secrets = []
        self._regex = None
        self.max_len = 0

    def register(self, value):
        """Registra um segredo; valores nao str ou com menos de 4 caracteres sao ignorados."""
        if not isinstance(value, str) or len(value) < MIN_LENGTH:
            return
        with self._lock:
            if value in self._secrets:
                return
            segredos = sorted(self._secrets + [value], key=len, reverse=True)
            self._regex = re.compile("|".join(re.escape(s) for s in segredos))
            self._secrets = segredos
            self.max_len = len(segredos[0])

    @property
    def regex(self):
        return self._regex

    def mask(self, text):
        """Mascara segredos registrados e senhas em connect strings."""
        if not isinstance(text, str) or not text:
            return text
        regex = self._regex
        if regex is not None:
            text = regex.sub(MASK, text)
        return _RE_CONNECT.sub(r"\1/" + MASK + "@", text)


def _trim_connect_string(text, cutoff):
    # Um corte dentro de 'usuario/senha@dsn' emitiria parte da senha sem casar o padrao:
    # nunca corta um token sem espaco ainda nao terminado (limite de MAX_HELD_TOKEN caracteres).
    if cutoff < len(text) and text[cutoff].isspace():
        return cutoff
    m = _RE_TOKEN_FINAL.search(text, max(0, cutoff - MAX_HELD_TOKEN), cutoff)
    return m.start() if m else cutoff


class StreamMasker(object):
    """Mascara um fluxo em blocos retendo a cauda que pode conter um segredo cortado."""

    def __init__(self, masker):
        self._masker = masker
        self._pending = ""

    def feed(self, chunk):
        """Recebe um bloco e devolve o texto ja seguro para emissao."""
        texto = self._pending + (chunk or "")
        regex = self._masker.regex
        corte = len(texto)
        if regex is not None:
            corte = max(0, corte - (self._masker.max_len - 1))
        corte = _trim_connect_string(texto, corte)
        if regex is None:
            self._pending = texto[corte:]
            return self._masker.mask(texto[:corte])
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
        self._pending = texto[corte:]
        return self._masker.mask("".join(pedacos))

    def finalize(self):
        """Mascara e devolve o restante retido."""
        resto, self._pending = self._pending, ""
        return self._masker.mask(resto)


def _mask_arg(masker, value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return masker.mask(value)
    return masker.mask(str(value))


class _MaskFilter(logging.Filter):

    def __init__(self, masker):
        super(_MaskFilter, self).__init__()
        self.masker = masker

    def filter(self, record):
        m = self.masker
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


def logging_filter(masker):
    """logging.Filter que mascara msg, args e traceback do registro."""
    return _MaskFilter(masker)


MASKER = Masker()


def register_secret(value):
    """Registra um segredo no mascarador global do processo."""
    MASKER.register(value)


def install_filter_on_handlers(masker=None):
    """Instala (uma vez por handler) o filtro de mascaramento em todos os handlers de log."""
    masker = masker or MASKER
    loggers = [logging.getLogger()]
    for lg in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(lg, logging.Logger):
            loggers.append(lg)
    for lg in loggers:
        for handler in list(lg.handlers):
            if getattr(handler, _FILTER_MARK, None) is masker:
                continue
            handler.addFilter(logging_filter(masker))
            setattr(handler, _FILTER_MARK, masker)
