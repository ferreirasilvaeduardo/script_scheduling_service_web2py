# -*- coding: utf-8 -*-
"""Servidor HTTP da biblioteca padrao para o app WSGI (CR-021d1b, D5).

``wsgiref`` com uma thread por conexao e um semaforo de ``max_threads``: com todas ocupadas, o laco
de aceite espera em vez de abrir threads sem fim. Cada conexao tem ``socket_timeout_s`` (cliente
lento e derrubado). Cabecalho com '_' no nome e descartado: o wsgiref o confundiria com o de '-'
(``X_Forwarded_For`` viraria HTTP_X_FORWARDED_FOR e passaria por um proxy que so limpa o
X-Forwarded-For). Log pelo ``logging``, nunca no stderr. A parada e por flag (SIGTERM e SIGINT so a
acionam, no run_web.py): para de aceitar e espera as requisicoes em andamento ate ``grace_s``.
"""
import logging
import socket
import threading
import time
from socketserver import ThreadingMixIn
from typing import Any, Callable, Dict, Optional, Tuple
from wsgiref.simple_server import ServerHandler, WSGIRequestHandler, WSGIServer

ACCEPT_POLL_S = 0.5
SERVER_NAME = "SSS"


class _LogStream:
    """Destino de erro do wsgiref (no lugar do stderr), mandando cada linha para o log."""

    def __init__(self, log: logging.Logger) -> None:
        self._log = log

    def write(self, text: str) -> None:
        """Uma mensagem do wsgiref vira um WARN do log da aplicacao."""
        if text.strip():
            self._log.warning("servidor: %s", text.rstrip(), extra={"action": "HTTP"})

    def flush(self) -> None:
        """Nada a descarregar (o logging grava a cada mensagem)."""


class _ServerHandler(ServerHandler):
    """ServerHandler do wsgiref que se identifica so como SSS (sem Python nem versao)."""

    server_software = SERVER_NAME


class _Handler(WSGIRequestHandler):
    """Uma requisicao por conexao (HTTP/1.0), com timeout e sem cabecalhos com '_'."""

    server_version = SERVER_NAME
    sys_version = ""
    log: logging.Logger = logging.getLogger("sss_web")

    def get_environ(self) -> Dict[str, Any]:
        """Environ do wsgiref, refeito sem os cabecalhos que tem '_' no nome."""
        environ = super().get_environ()
        for key in [k for k in environ if k.startswith("HTTP_")]:
            del environ[key]
        for name, value in self.headers.items():
            if "_" in name:
                self.log.warning("cabecalho com '_' descartado (nome=%s ip=%s)", name[:60],
                                 self.client_address[0], extra={"action": "HTTP"})
                continue
            key = "HTTP_" + name.replace("-", "_").upper()
            if key in ("HTTP_CONTENT_TYPE", "HTTP_CONTENT_LENGTH"):
                continue
            environ[key] = f"{environ[key]},{value.strip()}" if key in environ else value.strip()
        return environ

    def handle(self) -> None:
        """Igual ao handle do wsgiref (3.6 a 3.13), com o _ServerHandler.

        ``multithread=True``: este servidor atende uma conexao por thread.
        """
        self.raw_requestline = self.rfile.readline(65537)
        if len(self.raw_requestline) > 65536:
            self.requestline = ""
            self.request_version = ""
            self.command = ""
            self.send_error(414)
            return
        if not self.parse_request():
            return
        handler = _ServerHandler(self.rfile, self.wfile, self.get_stderr(), self.get_environ(),
                                 multithread=True)
        # Referencia de volta que o proprio wsgiref grava e usa para o log de acesso.
        handler.request_handler = self  # pylint: disable=attribute-defined-outside-init
        handler.run(self.server.get_app())

    def get_stderr(self) -> _LogStream:
        """Erros do wsgiref vao para o log, nunca para o stderr."""
        return _LogStream(self.log)

    def log_message(self, format: str, *args: Any) -> None:  # pylint: disable=redefined-builtin
        """Linha de acesso em DEBUG (o log da aplicacao ja registra o que importa)."""
        self.log.debug("acesso %s: " + format, self.client_address[0], *args,
                       extra={"action": "HTTP"})


class Server(ThreadingMixIn, WSGIServer):
    """WSGIServer com uma thread por conexao, limitada por um semaforo."""

    daemon_threads = True

    def __init__(self, address: Tuple[str, int], handler: type, max_threads: int,
                 log: logging.Logger) -> None:
        if max_threads < 1:
            raise ValueError("max_threads precisa ser pelo menos 1")
        super().__init__(address, handler)
        self.max_threads = max_threads
        self.log = log
        self._slots = threading.BoundedSemaphore(max_threads)
        self.timeout = ACCEPT_POLL_S

    def process_request(self, request: Any, client_address: Any) -> None:
        """Espera uma vaga antes de abrir a thread da conexao.

        Enquanto espera, o laco de aceite fica parado (sem abrir threads sem fim).
        """
        self._slots.acquire()  # pylint: disable=consider-using-with
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        """Atende a conexao e devolve a vaga, aconteca o que acontecer."""
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Falha de conexao (cliente lento, desconexao) vai para o log, nunca para o stderr."""
        self.log.warning("conexao encerrada com erro (ip=%s)", client_address[0],
                         exc_info=True, extra={"action": "HTTP"})

    def wait_idle(self, grace_s: float) -> bool:
        """Espera as requisicoes em andamento ate ``grace_s``; True se todas terminaram."""
        deadline = time.monotonic() + grace_s
        taken = 0
        try:
            while taken < self.max_threads:
                left = deadline - time.monotonic()
                # Vaga tomada so para contar; devolvida no finally (sem with de proposito).
                acquired = left > 0 and self._slots.acquire(  # pylint: disable=R1732
                    timeout=left)
                if not acquired:
                    return False
                taken += 1
            return True
        finally:
            for _ in range(taken):
                self._slots.release()


def make_server(  # pylint: disable=too-many-arguments
        app: Callable[..., Any], host: str, port: int, *, max_threads: int,
        socket_timeout_s: float, log: logging.Logger) -> Server:
    """Servidor pronto para ``serve`` (porta 0 escolhe uma livre; ``server_address`` diz qual)."""
    handler = type("Handler", (_Handler,), {"timeout": socket_timeout_s, "log": log})
    server = Server((host, port), handler, max_threads, log)
    server.set_app(app)
    return server


def serve(server: Server, stop: threading.Event, grace_s: float,
          ready: Optional[Callable[[Tuple[str, int]], None]] = None) -> bool:
    """Atende ate ``stop`` ser acionada; para de aceitar e espera as requisicoes em andamento.

    Devolve True se tudo terminou dentro de ``grace_s``.
    """
    if ready is not None:
        ready(server.server_address)
    try:
        while not stop.is_set():
            try:
                server.handle_request()
            except (OSError, socket.timeout):
                if stop.is_set():
                    break
                server.log.warning("falha no aceite de conexao", exc_info=True,
                                   extra={"action": "HTTP"})
    finally:
        server.socket.close()
    idle = server.wait_idle(grace_s)
    server.server_close()
    return idle
