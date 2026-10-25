# -*- coding: utf-8 -*-
"""Servidor da biblioteca padrao (CR-021d1b, D5) com socket real.

Limite de threads, cliente lento, cabecalho com '_' descartado, log fora do stderr e parada limpa.
Cada teste termina sem thread sobrando (os testes do agente exigem processo de uma thread so).
"""
import http.client
import io
import logging
import socket
import sys
import threading
import time
import unittest

from tests.support import _testenv  # noqa: F401 - ajusta sys.path sem importar gluon
from web.server import make_server, serve

LOG = logging.getLogger("sss_test_web_server")
LOG.addHandler(logging.NullHandler())
LOG.propagate = False
TIMEOUT_S = 0.5


class ServerTest(unittest.TestCase):
    """Servidor em uma thread do teste, numa porta livre de 127.0.0.1."""

    def setUp(self):
        self.threads_before = threading.active_count()
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.inside = 0
        self.peak = 0
        self.stop = threading.Event()
        self.server = make_server(self.app, "127.0.0.1", 0, max_threads=2,
                                  socket_timeout_s=TIMEOUT_S, log=LOG)
        self.port = self.server.server_address[1]
        self.result = {}
        self.thread = threading.Thread(target=lambda: self.result.update(
            idle=serve(self.server, self.stop, grace_s=5)))
        self.thread.start()

    def tearDown(self):
        self.release.set()
        self.stop.set()
        self.thread.join(10)
        self.assertFalse(self.thread.is_alive(), "o laco do servidor parou")
        deadline = time.monotonic() + 5
        while threading.active_count() > self.threads_before and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(threading.active_count(), self.threads_before, "nenhuma thread sobrando")

    def app(self, environ, start_response):
        path = environ["PATH_INFO"]
        if path == "/wait":
            with self.lock:
                self.inside += 1
                self.peak = max(self.peak, self.inside)
            self.release.wait(10)
            with self.lock:
                self.inside -= 1
        body = repr(environ.get("HTTP_X_FORWARDED_FOR")).encode() if path == "/xff" else b"ok"
        start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))])
        return [body]

    def get(self, path, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("GET", path, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read(), response.getheader("Server")
        finally:
            connection.close()

    def raw(self, data, wait_s=10):
        with socket.create_connection(("127.0.0.1", self.port), timeout=wait_s) as sock:
            sock.sendall(data)
            chunks = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)

    def test_request_and_server_header(self):
        """Resposta normal; o cabecalho Server nao revela Python nem versao."""
        status, body, server = self.get("/x")
        self.assertEqual((status, body), (200, b"ok"))
        self.assertEqual(server, "SSS")

    def test_threads_are_bounded(self):
        """Com max_threads=2, a terceira conexao espera: nunca mais de 2 na aplicacao."""
        results = []
        clients = [threading.Thread(target=lambda: results.append(self.get("/wait")[0])) for _ in range(3)]
        for client in clients:
            client.start()
        deadline = time.monotonic() + 5
        while self.inside < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
        time.sleep(0.3)
        self.assertEqual((self.inside, self.peak), (2, 2))
        self.release.set()
        for client in clients:
            client.join(10)
        self.assertEqual(results, [200, 200, 200])
        self.assertEqual(self.peak, 2)

    def test_slow_client_is_dropped_and_logged_not_printed(self):
        """Pedido pela metade: a conexao cai no timeout, sem nada no stderr, e o servidor segue."""
        stderr, sys.stderr = sys.stderr, io.StringIO()
        try:
            started = time.monotonic()
            answer = self.raw(b"GET /x HTTP/1.0\r\nHost: a", wait_s=10)
            elapsed = time.monotonic() - started
            printed = sys.stderr.getvalue()
        finally:
            sys.stderr = stderr
        self.assertLess(elapsed, TIMEOUT_S * 6)
        self.assertNotIn(b"200 OK", answer)
        self.assertEqual(printed, "")
        self.assertEqual(self.get("/x")[0], 200)

    def test_underscore_header_is_dropped(self):
        """X_Forwarded_For nao vira HTTP_X_FORWARDED_FOR; o X-Forwarded-For legitimo passa."""
        self.assertEqual(self.get("/xff", {"X_Forwarded_For": "6.6.6.6"})[1], b"None")
        self.assertEqual(self.get("/xff", {"X-Forwarded-For": "1.2.3.4"})[1], b"'1.2.3.4'")
        both = self.raw(b"GET /xff HTTP/1.0\r\nX-Forwarded-For: 1.2.3.4\r\nX_Forwarded_For: 6.6.6.6\r\n\r\n")
        self.assertTrue(both.endswith(b"'1.2.3.4'"), both[-40:])

    def test_stop_finishes_in_flight_requests(self):
        """Parada com requisicao em andamento: ela termina e serve() informa que ficou ocioso."""
        results = []
        client = threading.Thread(target=lambda: results.append(self.get("/wait")[0]))
        client.start()
        deadline = time.monotonic() + 5
        while self.inside < 1 and time.monotonic() < deadline:
            time.sleep(0.02)
        self.stop.set()
        time.sleep(TIMEOUT_S + 0.2)
        self.release.set()
        client.join(10)
        self.thread.join(10)
        self.assertEqual((results, self.result.get("idle")), ([200], True))
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", self.port), timeout=1).close()


if __name__ == "__main__":
    unittest.main()
