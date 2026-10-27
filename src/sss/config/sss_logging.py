# -*- coding: utf-8 -*-
"""Configuracao de logging estruturado e rotativo do SSS.

Segue estritamente as especificacoes do README §13 e AGENTS.md §6.
Gera formato:
%(asctime)s %(levelname)s [pid=%(process)d] [agent=%(agent)s] [ticket=%(ticket)s] [action=%(action)s] %(message)s
com data ISO local e offset.
"""
import datetime
import logging
import logging.handlers
import os
import sys
import threading

from sss.config import log_paths


FMT_SSS = "%(asctime)s %(levelname)s [pid=%(process)d] [agent=%(agent)s] [ticket=%(ticket)s] [action=%(action)s] %(message)s"


class SSSFormatter(logging.Formatter):
    """Formatador que gera data ISO local com offset conforme README §13."""

    def formatTime(self, record, datefmt=None):
        dt = datetime.datetime.fromtimestamp(record.created).astimezone()
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


class SSSContextFilter(logging.Filter):
    """Filtro que injeta defaults ('-') para agent, ticket e action."""

    def __init__(self, default_agent="-", default_ticket="-", default_action="-"):
        super(SSSContextFilter, self).__init__()
        self.default_agent = default_agent or "-"
        self.default_ticket = default_ticket or "-"
        self.default_action = default_action or "-"

    def filter(self, record):
        if not hasattr(record, "agent") or record.agent is None:
            record.agent = self.default_agent
        if not hasattr(record, "ticket") or record.ticket is None:
            record.ticket = self.default_ticket
        if not hasattr(record, "action") or record.action is None:
            record.action = self.default_action
        return True


class SSSLoggerAdapter(logging.LoggerAdapter):
    """LoggerAdapter contextualizado com agent, ticket e action."""

    def __init__(self, logger, agent="-", ticket="-", action="-"):
        super(SSSLoggerAdapter, self).__init__(logger, {
            "agent": agent or "-",
            "ticket": ticket or "-",
            "action": action or "-"
        })

    def process(self, msg, kwargs):
        extra = dict(self.extra)
        if "extra" in kwargs and kwargs["extra"]:
            extra.update(kwargs["extra"])
        kwargs["extra"] = extra
        return msg, kwargs


def get_adapter(logger, agent="-", ticket="-", action="-"):
    """Retorna um SSSLoggerAdapter com os atributos de contexto fornecidos."""
    return SSSLoggerAdapter(logger, agent=agent, ticket=ticket, action=action)


class AppLogRotatingHandler(logging.handlers.BaseRotatingHandler):
    """Handler rotativo para logs da aplicacao (CR-005 D6, R-c a R-e, README §13).

    - Caminho: log_dir/app/AAAA/MM/DD/HH/MI/<log_name>_<PID>[_<n>].log
    - Nasce na pasta do minuto da subida pelo relogio local do processo.
    - Troca de arquivo ao atingir max_bytes, abrindo no minuto atual com sufixo _<n> em colisao.
    - Nao apaga nada: a limpeza dos logs e manual (README §11.3, CR-030).
    - Diretorios sao criados com 0o750 e arquivos novos com 0o640.
    - Falhas de retencao, chmod ou fechamento viram WARN no proprio arquivo, antes do proximo registro.
    """

    def __init__(self, log_dir, process_name, max_bytes,
                 encoding="utf-8", pid=None, delay=False, default_agent="-"):
        self.log_dir = log_dir
        self.process_name = process_name[:-4] if process_name.endswith(".log") else process_name
        self.max_bytes = max_bytes
        self.maxBytes = max_bytes
        self.pid = pid if pid is not None else os.getpid()
        self.encoding = encoding
        self._delay = delay
        self._warnings = []

        now = datetime.datetime.now()
        path_initial = log_paths.next_app_log_path(
            self.log_dir, self.process_name, self.pid, now
        )
        _ensure_directory(os.path.dirname(path_initial), self._warnings)

        super(AppLogRotatingHandler, self).__init__(
            path_initial, mode="a", encoding=encoding, delay=delay
        )
        # Filtro unico: um segundo SSSContextFilter depois deste nunca veria o agente vazio.
        self.addFilter(SSSContextFilter(default_agent=default_agent))

    def registrar_aviso(self, action, message):
        """Guarda um WARN para gravar neste arquivo antes do proximo registro."""
        self._warnings.append((action, message))

    def _open(self):
        _ensure_directory(os.path.dirname(self.baseFilename), self._warnings)
        file_new = not os.path.exists(self.baseFilename)
        stream = open(self.baseFilename, self.mode, encoding=self.encoding)
        if file_new:
            _chmod(self.baseFilename, 0o640, self._warnings)
        return stream

    def emit(self, record):
        if self._warnings:
            pending, self._warnings = self._warnings, []
            for action, message in pending:
                warning = logging.LogRecord(self.process_name, logging.WARNING, __file__, 0,
                                          message, None, None)
                warning.action = action
                if warning.levelno >= self.level and self.filter(warning):
                    super(AppLogRotatingHandler, self).emit(warning)
        super(AppLogRotatingHandler, self).emit(record)

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
        now = datetime.datetime.now()
        new_path = log_paths.next_app_log_path(
            self.log_dir, self.process_name, self.pid, now
        )
        self.baseFilename = os.path.abspath(new_path)
        if not self.delay:
            self.stream = self._open()


def _chmod(path, mode, warnings):
    try:
        os.chmod(path, mode)
    except OSError as exc:
        warnings.append(("LOG", "chmod %o falhou em %s: %s" % (mode, path, exc)))


def _ensure_directory(directory, warnings):
    # Nivel a nivel com 0o750 (README §13): regra unica em log_paths (F8.1).
    log_paths.ensure_directory(directory, warnings)


def configure(log_name, cfg):
    """Cria um AppLogRotatingHandler em log_dir/app/... com o formato do README §13.

    Aplica o nivel configurado e cria log_dir com permissao 0o750 se necessario.
    Retorna o logger configurado.
    """
    log_dir = cfg.logging.log_dir
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, mode=0o750, exist_ok=True)
        # makedirs aplica a umask ao mode; o chmod garante 0o750. Falha aqui aborta a subida.
        os.chmod(log_dir, 0o750)

    default_agent = "-"
    if hasattr(cfg, "agent") and hasattr(cfg.agent, "agent_id") and cfg.agent.agent_id:
        default_agent = cfg.agent.agent_id

    handler = AppLogRotatingHandler(
        log_dir=log_dir,
        process_name=log_name,
        max_bytes=cfg.logging.app_log_max_bytes,
        encoding="utf-8",
        default_agent=default_agent,
    )

    handler.setFormatter(SSSFormatter(FMT_SSS))

    lvl_name = cfg.logging.level.upper()
    level = getattr(logging, lvl_name if lvl_name != "WARN" else "WARNING", logging.INFO)
    handler.setLevel(level)

    logger = logging.getLogger(log_name)
    logger.setLevel(level)

    # Evita acumular handlers para o mesmo arquivo em reinicializacoes
    for h in list(logger.handlers):
        if isinstance(h, (AppLogRotatingHandler, logging.handlers.RotatingFileHandler)):
            logger.removeHandler(h)
            try:
                h.close()
            except OSError as exc:
                handler.registrar_aviso("LOG", "fechamento do handler anterior falhou: %s" % exc)

    logger.addHandler(handler)
    # CR-026f: avisos do config.ini guardados pelo load(), que roda antes deste configure().
    from sss.config import sss_config  # pylint: disable=import-outside-toplevel
    for message in sss_config.pending_warnings():
        logger.warning(message, extra={"action": "INICIO"})

    return logger



_LOGGERS = {}
_LOGGERS_LOCK = threading.Lock()


def log_initial_critical(log_name, message, log_dir=None, stream=None):
    """CRITICAL de falha na subida, antes de haver configuracao valida (README §12.1).

    Grava no log da aplicacao do minuto atual (log_dir/app/AAAA/MM/DD/HH/MI/<log_name>_<PID>.log,
    README §13) quando log_dir existe e aceita escrita; senao, no stderr, sempre no formato do
    README §13. Retorna o destino usado ('arquivo' ou 'stderr').
    """
    handler = None
    destination = "stderr"
    reason_stderr = None
    warnings_value = []
    if log_dir and os.path.isdir(log_dir) and os.access(log_dir, os.W_OK):
        name = log_name[:-4] if log_name.endswith(".log") else log_name
        # Sem sufixo _<n>: falhas repetidas no mesmo minuto e processo vao para o mesmo arquivo.
        path = log_paths.app_log_path(log_dir, name, os.getpid(), datetime.datetime.now())
        try:
            _ensure_directory(os.path.dirname(path), warnings_value)
            file_new = not os.path.exists(path)
            handler = logging.FileHandler(path, encoding="utf-8")
            if file_new:
                _chmod(path, 0o640, warnings_value)
            destination = "arquivo"
        except OSError as exc:
            handler = None
            reason_stderr = "log da aplicacao indisponivel (%s): %s" % (path, exc)
    if handler is None:
        handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(SSSFormatter(FMT_SSS))
    handler.addFilter(SSSContextFilter(default_action="INICIO"))
    logger = logging.getLogger("%s.inicio" % log_name)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        if reason_stderr:
            logger.warning(reason_stderr)
        for _action, warning in warnings_value:
            logger.warning(warning)
        logger.critical(message)
    finally:
        logger.removeHandler(handler)
        handler.close()
    return destination


def get_logger(log_name, cfg):
    """Retorna o logger configurado por configurar(), criando-o uma unica vez por processo."""
    with _LOGGERS_LOCK:
        logger = _LOGGERS.get(log_name)
        if logger is None:
            logger = configure(log_name, cfg)
            _LOGGERS[log_name] = logger
        return logger
