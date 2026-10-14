# -*- coding: utf-8 -*-
"""Regressao: o Rocket embarcado (gluon/packages/rocket3) deve funcionar no Python 3.6.

Defeito: 'except ssl.SSLCertVerificationError' (classe do 3.7+) levantava AttributeError
ao avaliar o except, mascarando o SocketTimeout de conexoes ociosas (log ERROR com traceback).
"""
import _testenv  # noqa: F401

import os
import queue
import re
import socket
import sys
import unittest

_ROCKET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "gluon", "packages", "rocket3")
if _ROCKET_DIR not in sys.path:
    sys.path.insert(0, _ROCKET_DIR)

import rocket3  # noqa: E402


class _ArquivoOcioso(object):
    """Socket file de cliente que conecta e nunca envia a linha de requisicao."""

    def readline(self, *args):
        raise socket.timeout("timed out")

    def close(self):
        pass


class _ConexaoOciosa(object):

    def makefile(self, *args, **kwargs):
        return _ArquivoOcioso()


class TestRocketPy36(unittest.TestCase):

    def _worker(self):
        app_info = {"server_software": "teste", "wsgi_app": lambda environ, start_response: []}
        return rocket3.WSGIWorker(app_info, queue.Queue(), queue.Queue())

    def test_timeout_de_conexao_ociosa_propaga_socket_timeout(self):
        worker = self._worker()
        with self.assertRaises(rocket3.SocketTimeout):
            worker.run_app(_ConexaoOciosa())

    def test_worker_trata_timeout_sem_erro(self):
        worker = self._worker()
        worker.conn = _ConexaoOciosa()
        try:
            worker.run_app(worker.conn)
        except Exception:
            self.assertTrue(worker._handleError(*sys.exc_info()))
        self.assertEqual(worker.monitor_queue.qsize(), 1)

    def test_sem_classes_ssl_ausentes_no_36(self):
        with open(rocket3.__file__, encoding="utf-8") as f:
            codigo = f.read()
        self.assertIsNone(re.search(r"except\s+ssl\.SSLCertVerificationError", codigo))


if __name__ == "__main__":
    unittest.main()
