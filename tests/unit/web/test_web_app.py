# -*- coding: utf-8 -*-
"""Aplicacao WSGI (CR-021d1b): rota, hooks, action, sessao, erros e corpo em fluxo, sem socket."""
import io
import logging
import os
import shutil
import tempfile
import unittest
import wsgiref.util

from tests.support import _testenv  # noqa: F401 - ajusta sys.path sem importar gluon
from sss.web.framework.app import Application, Settings
from sss.web.framework.errors import HTTP, redirect
from sss.web.framework.session import COOKIE_NAME, SessionCodec

APP = "script_scheduling_service"
KEY = "chave-de-teste-com-mais-de-16-caracteres"
LOG = logging.getLogger("sss_test_web_app")
LOG.addHandler(logging.NullHandler())
LOG.propagate = False


class _Started:
    """start_response falso que guarda status e cabecalhos."""

    def __call__(self, status, headers, exc_info=None):
        self.status, self.headers = status, headers

    def header(self, name):
        values = [v for k, v in self.headers if k.lower() == name.lower()]
        return values[0] if values else None


def _environ(path, method="GET", body=b"", content_type="", cookie=None, latin1=False):
    environ = {}
    wsgiref.util.setup_testing_defaults(environ)
    raw = path.encode("utf-8").decode("latin-1") if not latin1 else path
    environ.update({"PATH_INFO": raw, "REQUEST_METHOD": method, "wsgi.input": io.BytesIO(body),
                    "CONTENT_LENGTH": str(len(body)), "CONTENT_TYPE": content_type,
                    "REMOTE_ADDR": "10.0.0.9"})
    if cookie:
        environ["HTTP_COOKIE"] = cookie
    return environ


class AppTest(unittest.TestCase):
    """Uma aplicacao de teste com actions que exercitam cada caminho."""

    def setUp(self):
        self.static_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.static_dir)
        with open(os.path.join(self.static_dir, "a.css"), "w") as handle:
            handle.write("body{}")
        self.codec = SessionCodec(KEY)
        self.closed = []
        self.app = self._app()

    def _app(self, **kwargs):
        settings = Settings(APP, self.static_dir, 4096, self.codec, lambda request: False)
        actions = {
            ("default", "index"): lambda ctx: "<p>início</p>",
            ("default", "login"): self._login,
            ("default", "who"): lambda ctx: str(ctx.session.login),
            ("default", "flash"): lambda ctx: repr(ctx.response.flash),
            ("default", "boom"): self._boom,
            ("default", "view"): lambda ctx: {"title": "SSS"},
            ("default", "stream"): self._stream,
            ("default", "inject"): self._inject,
            ("default", "upload"): self._upload,
        }
        hooks = dict(before=[self._guard], after=[self._headers])
        hooks.update(kwargs)
        return Application(settings, lambda route: actions.get((route.controller, route.function)),
                           LOG, error_page=lambda status, incident, ctx: "ERRO %d %s" % (status, incident),
                           **hooks)

    @staticmethod
    def _guard(ctx):
        if ctx.route.function == "secret":
            raise HTTP(403)

    @staticmethod
    def _headers(ctx):
        ctx.response.headers["X-Frame-Options"] = "DENY"

    @staticmethod
    def _login(ctx):
        ctx.session.login = "op.prod"
        ctx.session.flash = {"kind": "success", "message": "Bem-vindo"}
        redirect("/%s/default/index" % APP)

    @staticmethod
    def _boom(ctx):
        ctx.session.login = "nao-grava"
        raise RuntimeError("detalhe interno que nao pode vazar")

    def _stream(self, ctx):
        def chunks():
            try:
                yield "a"
                yield b"b"
            finally:
                self.closed.append("gerador")
        return chunks()

    @staticmethod
    def _inject(ctx):
        ctx.response.headers["X-Bad"] = "a\r\nSet-Cookie: x=1"
        return "ok"

    def _upload(self, ctx):
        self.upload = ctx.request.post_vars["file"]

        def chunks():
            yield b"ok"
        return chunks()

    def call(self, *args, **kwargs):
        started = _Started()
        result = self.app(_environ(*args, **kwargs), started)
        body = b"".join(result)
        if hasattr(result, "close"):
            result.close()
        return started, body

    def cookie_of(self, started):
        value = started.header("Set-Cookie")
        return value.split(";")[0] if value else None

    def test_action_text(self):
        """Texto vira HTML UTF-8 com tamanho; hook after aplica o cabecalho."""
        started, body = self.call("/%s/default/index" % APP)
        self.assertEqual((started.status, body.decode("utf-8")), ("200 OK", "<p>início</p>"))
        self.assertEqual(started.header("Content-Type"), "text/html; charset=utf-8")
        self.assertEqual(started.header("Content-Length"), str(len(body)))
        self.assertEqual(started.header("X-Frame-Options"), "DENY")
        self.assertIsNone(started.header("Set-Cookie"), "sessao sem mudanca nao regrava o cookie")

    def test_head_has_no_body(self):
        """HEAD roda a action e devolve so os cabecalhos."""
        started, body = self.call("/%s/default/index" % APP, method="HEAD")
        self.assertEqual((started.status, body), ("200 OK", b""))

    def test_server_and_application_root(self):
        """Raiz do servidor: 303 para a aplicacao; raiz da aplicacao: default/index (D4, como no web2py)."""
        started, _body = self.call("/")
        self.assertEqual((started.status, started.header("Location")), ("303 See Other", "/%s/" % APP))
        for path in ("/%s" % APP, "/%s/" % APP):
            with self.subTest(path=path):
                started, body = self.call(path)
                self.assertEqual((started.status, body.decode("utf-8")), ("200 OK", "<p>início</p>"))
        self.assertEqual(self.call("/outra_app/")[0].status, "404 Not Found")

    def test_not_found_and_invalid_paths(self):
        """Sem action, rota invalida e UTF-8 invalido: 404 com a pagina minima."""
        for path, latin1 in (("/%s/default/nada" % APP, False), ("/%s/default/_x" % APP, False),
                             ("/%s/static/../models/00_config.py" % APP, False),
                             ("/%s/default/index/\xff" % APP, True)):
            with self.subTest(path=path):
                started, body = self.call(path, latin1=latin1)
                self.assertEqual(started.status, "404 Not Found")
                self.assertIn(b"404", body)

    def test_before_hook_http_uses_error_page_and_after_hooks(self):
        """HTTP do hook before: status, pagina de erro da aplicacao e cabecalhos do after."""
        started, body = self.call("/%s/default/secret" % APP)
        self.assertEqual((started.status, body), ("403 Forbidden", b"ERRO 403 None"))
        self.assertEqual(started.header("X-Frame-Options"), "DENY")

    def test_redirect_saves_session_and_flash_moves(self):
        """Login grava a sessao no redirect; na volta a sessao e lida e o flash vai para a resposta."""
        started, body = self.call("/%s/default/login" % APP)
        self.assertEqual((started.status, started.header("Location"), body),
                         ("303 See Other", "/%s/default/index" % APP, b""))
        set_cookie = started.header("Set-Cookie")
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Lax", set_cookie)
        self.assertIn("Path=/%s/" % APP, set_cookie)
        cookie = self.cookie_of(started)
        started, body = self.call("/%s/default/who" % APP, cookie=cookie)
        self.assertEqual(body, b"op.prod")
        started, body = self.call("/%s/default/flash" % APP, cookie=cookie)
        self.assertIn(b"Bem-vindo", body)
        self.assertIsNotNone(started.header("Set-Cookie"), "cookie regravado sem o flash")
        started, body = self.call("/%s/default/flash" % APP, cookie=self.cookie_of(started))
        self.assertEqual(body, b"None", "flash mostrado uma vez so")

    def test_tampered_cookie_is_logged_and_replaced(self):
        """Cookie adulterado: sessao vazia, WARN com o motivo e cookie novo na resposta."""
        with self.assertLogs(LOG, "WARNING") as logs:
            started, body = self.call("/%s/default/who" % APP, cookie="%s=v1.e30.forjado" % COOKIE_NAME)
        self.assertEqual(body, b"None")
        self.assertIn("motivo=assinatura", logs.output[0])
        self.assertIsNotNone(started.header("Set-Cookie"))

    def test_unexpected_error_is_500_without_details(self):
        """Excecao: 500 com id da ocorrencia, sem detalhe no corpo, stack trace no log, sessao nao gravada."""
        with self.assertLogs(LOG, "ERROR") as logs:
            started, body = self.call("/%s/default/boom" % APP)
        self.assertEqual(started.status, "500 Internal Server Error")
        self.assertNotIn(b"detalhe interno", body)
        self.assertNotIn(b"Traceback", body)
        incident = body.decode().split()[-1]
        self.assertRegex(incident, r"^[0-9a-f]{12}$")
        self.assertIn(incident, logs.output[0])
        self.assertIn("RuntimeError: detalhe interno", logs.output[0], "stack trace no log")
        self.assertIsNone(started.header("Set-Cookie"))
        self.assertEqual(started.header("X-Frame-Options"), "DENY", "after roda tambem no 500")

    def test_dict_needs_renderer(self):
        """dict sem renderer e erro (500); com renderer, a view."""
        with self.assertLogs(LOG, "ERROR"):
            started, _body = self.call("/%s/default/view" % APP)
        self.assertEqual(started.status, "500 Internal Server Error")
        self.app = self._app(renderer=lambda ctx, data: "<h1>%s</h1>" % data["title"])
        started, body = self.call("/%s/default/view" % APP)
        self.assertEqual(body, b"<h1>SSS</h1>")

    def test_stream_is_closed(self):
        """Corpo em fluxo: blocos em bytes e o gerador fechado ao fim."""
        started, body = self.call("/%s/default/stream" % APP)
        self.assertEqual((started.status, body), ("200 OK", b"ab"))
        self.assertEqual(self.closed, ["gerador"])

    def test_upload_files_closed_after_stream(self):
        """Os temporarios do upload so fecham quando o servidor fecha o corpo."""
        boundary = "b0undary"
        body = (b"--b0undary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.txt\"\r\n\r\n"
                b"x\r\n--b0undary--\r\n")
        started, _body = self.call("/%s/default/upload" % APP, method="POST", body=body,
                                   content_type="multipart/form-data; boundary=%s" % boundary)
        self.assertEqual(started.status, "200 OK")
        self.assertTrue(self.upload.file.closed)

    def test_body_over_limit_is_413_page(self):
        """Corpo acima do limite: 413 com a pagina de erro, sem ler."""
        started, body = self.call("/%s/default/upload" % APP, method="POST", body=b"x" * 5000,
                                  content_type="application/x-www-form-urlencoded")
        self.assertEqual((started.status, body), ("413 Payload Too Large", b"ERRO 413 None"))

    def test_header_injection_is_500(self):
        """Cabecalho com quebra de linha vindo da action: 500 minimo, nada injetado."""
        with self.assertLogs(LOG, "ERROR"):
            started, _body = self.call("/%s/default/inject" % APP)
        self.assertEqual(started.status, "500 Internal Server Error")
        self.assertFalse(any("x=1" in v for _k, v in started.headers))

    def test_static_through_app(self):
        """Estatico pelo app, sem sessao e sem hooks; fora de static/, 404."""
        started, body = self.call("/%s/static/a.css" % APP)
        self.assertEqual((started.status, body), ("200 OK", b"body{}"))
        self.assertIsNone(started.header("Set-Cookie"))
        started, _body = self.call("/%s/static/b.css" % APP)
        self.assertEqual(started.status, "404 Not Found")


if __name__ == "__main__":
    unittest.main()
