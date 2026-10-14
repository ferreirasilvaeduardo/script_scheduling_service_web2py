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
import threading


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


def configurar(nome_log, cfg):
    """Cria um RotatingFileHandler em log_dir com o formato do README §13.

    Aplica o nivel configurado e cria log_dir com permissao 0o750 se necessario.
    Retorna o logger configurado.
    """
    log_dir = cfg.logging.log_dir
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, mode=0o750, exist_ok=True)
        # makedirs aplica a umask ao mode; o chmod garante 0o750. Falha aqui aborta a subida.
        os.chmod(log_dir, 0o750)

    filename = nome_log if nome_log.endswith(".log") else (nome_log + ".log")
    filepath = os.path.join(log_dir, filename)

    handler = logging.handlers.RotatingFileHandler(
        filepath,
        maxBytes=cfg.logging.app_log_max_bytes,
        backupCount=cfg.logging.app_log_backups,
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
        if isinstance(h, logging.handlers.RotatingFileHandler) and getattr(h, "_sss_path", None) == filepath:
            logger.removeHandler(h)

    handler._sss_path = filepath
    logger.addHandler(handler)

    return logger


_LOGGERS = {}
_LOCK_LOGGERS = threading.Lock()


def obter_logger(nome_log, cfg):
    """Retorna o logger configurado por configurar(), criando-o uma unica vez por processo."""
    with _LOCK_LOGGERS:
        logger = _LOGGERS.get(nome_log)
        if logger is None:
            logger = configurar(nome_log, cfg)
            _LOGGERS[nome_log] = logger
        return logger
