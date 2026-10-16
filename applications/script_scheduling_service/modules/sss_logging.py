# -*- coding: utf-8 -*-
"""Configuracao de logging estruturado e rotativo do SSS.

Segue estritamente as especificacoes do README §13 e AGENTS.md §6.
Gera formato:
%(asctime)s %(levelname)s [pid=%(process)d] [agente=%(agente)s] [ticket=%(ticket)s] [acao=%(acao)s] %(message)s
com data ISO local e offset.
"""
import datetime
import logging
import logging.handlers
import os
import sys
import threading

import pastas_log


FMT_SSS = "%(asctime)s %(levelname)s [pid=%(process)d] [agente=%(agente)s] [ticket=%(ticket)s] [acao=%(acao)s] %(message)s"


class SSSFormatter(logging.Formatter):
    """Formatador que gera data ISO local com offset conforme README §13."""

    def formatTime(self, record, datefmt=None):
        dt = datetime.datetime.fromtimestamp(record.created).astimezone()
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


class SSSContextFilter(logging.Filter):
    """Filtro que injeta defaults ('-') para agente, ticket e acao."""

    def __init__(self, default_agente="-", default_ticket="-", default_acao="-"):
        super(SSSContextFilter, self).__init__()
        self.default_agente = default_agente or "-"
        self.default_ticket = default_ticket or "-"
        self.default_acao = default_acao or "-"

    def filter(self, record):
        if not hasattr(record, "agente") or record.agente is None:
            record.agente = self.default_agente
        if not hasattr(record, "ticket") or record.ticket is None:
            record.ticket = self.default_ticket
        if not hasattr(record, "acao") or record.acao is None:
            record.acao = self.default_acao
        return True


class SSSLoggerAdapter(logging.LoggerAdapter):
    """LoggerAdapter contextualizado com agente, ticket e acao."""

    def __init__(self, logger, agente="-", ticket="-", acao="-"):
        super(SSSLoggerAdapter, self).__init__(logger, {
            "agente": agente or "-",
            "ticket": ticket or "-",
            "acao": acao or "-"
        })

    def process(self, msg, kwargs):
        extra = dict(self.extra)
        if "extra" in kwargs and kwargs["extra"]:
            extra.update(kwargs["extra"])
        kwargs["extra"] = extra
        return msg, kwargs


def get_adapter(logger, agente="-", ticket="-", acao="-"):
    """Retorna um SSSLoggerAdapter com os atributos de contexto fornecidos."""
    return SSSLoggerAdapter(logger, agente=agente, ticket=ticket, acao=acao)


class AppLogRotatingHandler(logging.handlers.BaseRotatingHandler):
    """Handler rotativo para logs da aplicacao (CR-005 D6, R-c a R-e, README §13).

    - Caminho: log_dir/app/AAAA/MM/DD/HH/MI/<nome_log>_<PID>[_<n>].log
    - Nasce na pasta do minuto da subida pelo relogio local do processo.
    - Troca de arquivo ao atingir max_bytes, abrindo no minuto atual com sufixo _<n> em colisao.
    - Executa retencao apagando pastas app/AAAA/MM/DD anteriores a retention_days dias na subida
      e a cada troca de arquivo.
    - Diretorios sao criados com 0o750 e arquivos novos com 0o640.
    """

    def __init__(self, log_dir, nome_processo, max_bytes, retention_days,
                 encoding="utf-8", pid=None, delay=False):
        self.log_dir = log_dir
        self.nome_processo = nome_processo[:-4] if nome_processo.endswith(".log") else nome_processo
        self.max_bytes = max_bytes
        self.maxBytes = max_bytes
        self.retention_days = retention_days
        self.pid = pid if pid is not None else os.getpid()
        self.encoding = encoding
        self._delay = delay

        agora = datetime.datetime.now()
        caminho_inicial = pastas_log.proximo_caminho_log_app(
            self.log_dir, self.nome_processo, self.pid, agora
        )
        self._garantir_diretorio(os.path.dirname(caminho_inicial))

        # Retencao na subida (CR-005, R-d)
        self.executar_retencao(agora)

        super(AppLogRotatingHandler, self).__init__(
            caminho_inicial, mode="a", encoding=encoding, delay=delay
        )
        self.addFilter(SSSContextFilter())

    def _garantir_diretorio(self, diretorio):
        if not os.path.exists(diretorio):
            os.makedirs(diretorio, mode=0o750, exist_ok=True)
            try:
                os.chmod(diretorio, 0o750)
            except OSError:
                pass

    def executar_retencao(self, ref_dt=None):
        try:
            pastas_log.limpar_retencao_app(self.log_dir, self.retention_days, ref_dt=ref_dt)
        except Exception:
            pass

    def _open(self):
        self._garantir_diretorio(os.path.dirname(self.baseFilename))
        arquivo_novo = not os.path.exists(self.baseFilename)
        stream = open(self.baseFilename, self.mode, encoding=self.encoding)
        if arquivo_novo:
            try:
                os.chmod(self.baseFilename, 0o640)
            except OSError:
                pass
        return stream

    def shouldRollover(self, record):
        if self.stream is None:
            self.stream = self._open()
        if self.max_bytes > 0:
            for f in self.filters:
                f.filter(record)
            msg = "%s\n" % self.format(record)
            self.stream.seek(0, 2)
            if self.stream.tell() + len(msg.encode(self.encoding or "utf-8")) >= self.max_bytes:
                return 1
        return 0

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        agora = datetime.datetime.now()
        novo_caminho = pastas_log.proximo_caminho_log_app(
            self.log_dir, self.nome_processo, self.pid, agora
        )
        self.baseFilename = os.path.abspath(novo_caminho)
        self.executar_retencao(agora)
        if not self.delay:
            self.stream = self._open()


def configurar(nome_log, cfg):
    """Cria um AppLogRotatingHandler em log_dir/app/... com o formato do README §13.

    Aplica o nivel configurado e cria log_dir com permissao 0o750 se necessario.
    Retorna o logger configurado.
    """
    log_dir = cfg.logging.log_dir
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, mode=0o750, exist_ok=True)
        # makedirs aplica a umask ao mode; o chmod garante 0o750. Falha aqui aborta a subida.
        os.chmod(log_dir, 0o750)

    handler = AppLogRotatingHandler(
        log_dir=log_dir,
        nome_processo=nome_log,
        max_bytes=cfg.logging.app_log_max_bytes,
        retention_days=cfg.logging.app_log_retention_days,
        encoding="utf-8"
    )

    handler.setFormatter(SSSFormatter(FMT_SSS))

    default_agente = "-"
    if hasattr(cfg, "agent") and hasattr(cfg.agent, "agent_id") and cfg.agent.agent_id:
        default_agente = cfg.agent.agent_id

    handler.addFilter(SSSContextFilter(default_agente=default_agente))

    lvl_name = cfg.logging.level.upper()
    level = getattr(logging, lvl_name if lvl_name != "WARN" else "WARNING", logging.INFO)
    handler.setLevel(level)

    logger = logging.getLogger(nome_log)
    logger.setLevel(level)

    # Evita acumular handlers para o mesmo arquivo em reinicializacoes
    for h in list(logger.handlers):
        if isinstance(h, (AppLogRotatingHandler, logging.handlers.RotatingFileHandler)):
            logger.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass

    logger.addHandler(handler)

    return logger



_LOGGERS = {}
_LOCK_LOGGERS = threading.Lock()


def registrar_critico_inicial(nome_log, mensagem, log_dir=None, stream=None):
    """CRITICAL de falha na subida, antes de haver configuracao valida (README §12.1).

    Grava em log_dir/<nome_log>.log quando o diretorio existe e aceita escrita; senao, no stderr,
    sempre no formato do README §13. Retorna o destino usado ('arquivo' ou 'stderr').
    """
    filename = nome_log if nome_log.endswith(".log") else (nome_log + ".log")
    handler = None
    destino = "stderr"
    if log_dir and os.path.isdir(log_dir) and os.access(log_dir, os.W_OK):
        try:
            handler = logging.FileHandler(os.path.join(log_dir, filename), encoding="utf-8")
            destino = "arquivo"
        except OSError:
            handler = None
    if handler is None:
        handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(SSSFormatter(FMT_SSS))
    handler.addFilter(SSSContextFilter(default_acao="INICIO"))
    logger = logging.getLogger("%s.inicio" % nome_log)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        logger.critical(mensagem)
    finally:
        logger.removeHandler(handler)
        handler.close()
    return destino


def obter_logger(nome_log, cfg):
    """Retorna o logger configurado por configurar(), criando-o uma unica vez por processo."""
    with _LOCK_LOGGERS:
        logger = _LOGGERS.get(nome_log)
        if logger is None:
            logger = configurar(nome_log, cfg)
            _LOGGERS[nome_log] = logger
        return logger
