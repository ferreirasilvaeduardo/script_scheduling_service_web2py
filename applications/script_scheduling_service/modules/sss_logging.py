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

import log_paths


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

    - Caminho: log_dir/app/AAAA/MM/DD/HH/MI/<nome_log>_<PID>[_<n>].log
    - Nasce na pasta do minuto da subida pelo relogio local do processo.
    - Troca de arquivo ao atingir max_bytes, abrindo no minuto atual com sufixo _<n> em colisao.
    - Executa retencao apagando pastas app/AAAA/MM/DD anteriores a retention_days dias na subida
      e a cada troca de arquivo.
    - Diretorios sao criados com 0o750 e arquivos novos com 0o640.
    - Falhas de retencao, chmod ou fechamento viram WARN no proprio arquivo, antes do proximo registro.
    """

    def __init__(self, log_dir, nome_processo, max_bytes, retention_days,
                 encoding="utf-8", pid=None, delay=False, default_agent="-"):
        self.log_dir = log_dir
        self.nome_processo = nome_processo[:-4] if nome_processo.endswith(".log") else nome_processo
        self.max_bytes = max_bytes
        self.maxBytes = max_bytes
        self.retention_days = retention_days
        self.pid = pid if pid is not None else os.getpid()
        self.encoding = encoding
        self._delay = delay
        self._avisos = []

        agora = datetime.datetime.now()
        caminho_inicial = log_paths.next_app_log_path(
            self.log_dir, self.nome_processo, self.pid, agora
        )
        _ensure_directory(os.path.dirname(caminho_inicial), self._avisos)

        # Retencao na subida (CR-005, R-d)
        self.executar_retencao(agora)

        super(AppLogRotatingHandler, self).__init__(
            caminho_inicial, mode="a", encoding=encoding, delay=delay
        )
        # Filtro unico: um segundo SSSContextFilter depois deste nunca veria o agente vazio.
        self.addFilter(SSSContextFilter(default_agent=default_agent))

    def registrar_aviso(self, acao, mensagem):
        """Guarda um WARN para gravar neste arquivo antes do proximo registro."""
        self._avisos.append((acao, mensagem))

    def executar_retencao(self, ref_dt=None):
        falhas = []
        log_paths.clean_app_retention(self.log_dir, self.retention_days, ref_dt=ref_dt, falhas=falhas)
        for falha in falhas:
            self.registrar_aviso("RETENCAO", "retencao do log da aplicacao nao removeu %s" % falha)

    def _open(self):
        _ensure_directory(os.path.dirname(self.baseFilename), self._avisos)
        arquivo_novo = not os.path.exists(self.baseFilename)
        stream = open(self.baseFilename, self.mode, encoding=self.encoding)
        if arquivo_novo:
            _chmod(self.baseFilename, 0o640, self._avisos)
        return stream

    def emit(self, record):
        if self._avisos:
            pendentes, self._avisos = self._avisos, []
            for acao, mensagem in pendentes:
                aviso = logging.LogRecord(self.nome_processo, logging.WARNING, __file__, 0,
                                          mensagem, None, None)
                aviso.action = acao
                if aviso.levelno >= self.level and self.filter(aviso):
                    super(AppLogRotatingHandler, self).emit(aviso)
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
        agora = datetime.datetime.now()
        novo_caminho = log_paths.next_app_log_path(
            self.log_dir, self.nome_processo, self.pid, agora
        )
        self.baseFilename = os.path.abspath(novo_caminho)
        self.executar_retencao(agora)
        if not self.delay:
            self.stream = self._open()


def _chmod(caminho, modo, avisos):
    try:
        os.chmod(caminho, modo)
    except OSError as exc:
        avisos.append(("LOG", "chmod %o falhou em %s: %s" % (modo, caminho, exc)))


def _ensure_directory(diretorio, avisos):
    # Nivel a nivel com 0o750 (README §13): regra unica em pastas_log (F8.1).
    log_paths.ensure_directory(diretorio, avisos)


def configure(nome_log, cfg):
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
        nome_processo=nome_log,
        max_bytes=cfg.logging.app_log_max_bytes,
        retention_days=cfg.logging.app_log_retention_days,
        encoding="utf-8",
        default_agent=default_agent,
    )

    handler.setFormatter(SSSFormatter(FMT_SSS))

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
            except OSError as exc:
                handler.registrar_aviso("LOG", "fechamento do handler anterior falhou: %s" % exc)

    logger.addHandler(handler)

    return logger



_LOGGERS = {}
_LOGGERS_LOCK = threading.Lock()


def log_initial_critical(nome_log, mensagem, log_dir=None, stream=None):
    """CRITICAL de falha na subida, antes de haver configuracao valida (README §12.1).

    Grava no log da aplicacao do minuto atual (log_dir/app/AAAA/MM/DD/HH/MI/<nome_log>_<PID>.log,
    README §13) quando log_dir existe e aceita escrita; senao, no stderr, sempre no formato do
    README §13. Retorna o destino usado ('arquivo' ou 'stderr').
    """
    handler = None
    destino = "stderr"
    motivo_stderr = None
    avisos = []
    if log_dir and os.path.isdir(log_dir) and os.access(log_dir, os.W_OK):
        nome = nome_log[:-4] if nome_log.endswith(".log") else nome_log
        # Sem sufixo _<n>: falhas repetidas no mesmo minuto e processo vao para o mesmo arquivo.
        caminho = log_paths.app_log_path(log_dir, nome, os.getpid(), datetime.datetime.now())
        try:
            _ensure_directory(os.path.dirname(caminho), avisos)
            arquivo_novo = not os.path.exists(caminho)
            handler = logging.FileHandler(caminho, encoding="utf-8")
            if arquivo_novo:
                _chmod(caminho, 0o640, avisos)
            destino = "arquivo"
        except OSError as exc:
            handler = None
            motivo_stderr = "log da aplicacao indisponivel (%s): %s" % (caminho, exc)
    if handler is None:
        handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(SSSFormatter(FMT_SSS))
    handler.addFilter(SSSContextFilter(default_action="INICIO"))
    logger = logging.getLogger("%s.inicio" % nome_log)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        if motivo_stderr:
            logger.warning(motivo_stderr)
        for _acao, aviso in avisos:
            logger.warning(aviso)
        logger.critical(mensagem)
    finally:
        logger.removeHandler(handler)
        handler.close()
    return destino


def get_logger(nome_log, cfg):
    """Retorna o logger configurado por configurar(), criando-o uma unica vez por processo."""
    with _LOGGERS_LOCK:
        logger = _LOGGERS.get(nome_log)
        if logger is None:
            logger = configure(nome_log, cfg)
            _LOGGERS[nome_log] = logger
        return logger
