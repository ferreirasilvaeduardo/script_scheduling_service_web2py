# -*- coding: utf-8 -*-
"""Mascaramento de segredos em texto, fluxos em blocos e logs (README §4.1, §8.10).

Modulo puro: nao importa gluon (AGENTS §7.1).
"""
import logging
import re
import threading

MASCARA = "****"
TAMANHO_MINIMO = 4

# usuario/senha@dsn -> usuario/****@dsn
_RE_CONNECT = re.compile(r"([A-Za-z0-9_$#.]+)/([^\s/@]+)@(?=\S)")
_MARCA_FILTRO = "_sss_filtro_masking"
_RE_TOKEN_FINAL = re.compile(r"\S+\Z")
MAX_TOKEN_RETIDO = 512


class Mascarador(object):
    """Substitui segredos registrados por '****' (o mais longo primeiro)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._segredos = []
        self._regex = None
        self.max_len = 0

    def registrar(self, valor):
        """Registra um segredo; valores nao str ou com menos de 4 caracteres sao ignorados."""
        if not isinstance(valor, str) or len(valor) < TAMANHO_MINIMO:
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

    def mascarar(self, texto):
        """Mascara segredos registrados e senhas em connect strings."""
        if not isinstance(texto, str) or not texto:
            return texto
        regex = self._regex
        if regex is not None:
            texto = regex.sub(MASCARA, texto)
        return _RE_CONNECT.sub(r"\1/" + MASCARA + "@", texto)


def _recuar_connect_string(texto, corte):
    # Um corte dentro de 'usuario/senha@dsn' emitiria parte da senha sem casar o padrao:
    # nunca corta um token sem espaco ainda nao terminado (limite de MAX_TOKEN_RETIDO caracteres).
    if corte < len(texto) and texto[corte].isspace():
        return corte
    m = _RE_TOKEN_FINAL.search(texto, max(0, corte - MAX_TOKEN_RETIDO), corte)
    return m.start() if m else corte


class MascaradorFluxo(object):
    """Mascara um fluxo em blocos retendo a cauda que pode conter um segredo cortado."""

    def __init__(self, mascarador):
        self._mascarador = mascarador
        self._pendente = ""

    def alimentar(self, bloco):
        """Recebe um bloco e devolve o texto ja seguro para emissao."""
        texto = self._pendente + (bloco or "")
        regex = self._mascarador.regex
        corte = len(texto)
        if regex is not None:
            corte = max(0, corte - (self._mascarador.max_len - 1))
        corte = _recuar_connect_string(texto, corte)
        if regex is None:
            self._pendente = texto[corte:]
            return self._mascarador.mascarar(texto[:corte])
        # Um segredo que comece antes do corte cabe inteiro no texto (len <= max_len);
        # se ele atravessa o corte, o corte avanca para o fim do match.
        pedacos = []
        pos = 0
        for m in regex.finditer(texto):
            if m.start() >= corte:
                break
            pedacos.append(texto[pos:m.start()])
            pedacos.append(MASCARA)
            pos = m.end()
            if pos > corte:
                corte = pos
        pedacos.append(texto[pos:corte])
        self._pendente = texto[corte:]
        return self._mascarador.mascarar("".join(pedacos))

    def finalizar(self):
        """Mascara e devolve o restante retido."""
        resto, self._pendente = self._pendente, ""
        return self._mascarador.mascarar(resto)


def _mascarar_arg(mascarador, valor):
    if valor is None or isinstance(valor, (bool, int, float)):
        return valor
    if isinstance(valor, str):
        return mascarador.mascarar(valor)
    return mascarador.mascarar(str(valor))


class _FiltroMascara(logging.Filter):

    def __init__(self, mascarador):
        super(_FiltroMascara, self).__init__()
        self.mascarador = mascarador

    def filter(self, record):
        m = self.mascarador
        if isinstance(record.msg, str):
            record.msg = m.mascarar(record.msg)
        else:
            record.msg = _mascarar_arg(m, record.msg)
        if isinstance(record.args, dict):
            record.args = dict((k, _mascarar_arg(m, v)) for k, v in record.args.items())
        elif record.args:
            record.args = tuple(_mascarar_arg(m, a) for a in record.args)
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = m.mascarar(record.exc_text)
        if record.stack_info:
            record.stack_info = m.mascarar(record.stack_info)
        return True


def filtro_logging(mascarador):
    """logging.Filter que mascara msg, args e traceback do registro."""
    return _FiltroMascara(mascarador)


MASCARADOR = Mascarador()


def registrar_segredo(valor):
    """Registra um segredo no mascarador global do processo."""
    MASCARADOR.registrar(valor)


def instalar_filtro_em_handlers(mascarador=None):
    """Instala (uma vez por handler) o filtro de mascaramento em todos os handlers de log."""
    mascarador = mascarador or MASCARADOR
    loggers = [logging.getLogger()]
    for lg in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(lg, logging.Logger):
            loggers.append(lg)
    for lg in loggers:
        for handler in list(lg.handlers):
            if getattr(handler, _MARCA_FILTRO, None) is mascarador:
                continue
            handler.addFilter(filtro_logging(mascarador))
            setattr(handler, _MARCA_FILTRO, mascarador)
