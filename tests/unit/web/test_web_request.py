# -*- coding: utf-8 -*-
"""Requisicao e resposta do nucleo web (CR-021d1): variaveis, corpo, limites, cookies e JSON seguro."""
import datetime
import decimal
import io
import json
import unittest

from tests.support import _testenv  # noqa: F401 - ajusta sys.path sem importar gluon
from web.errors import HTTP, redirect
from web.request import MAX_FIELDS, Request, parse_query
from web.response import Response, cookie_header, json_for_html
from web.routing import Route

ROUTE = Route("tickets", "index", "html", ["17"])


def _request(method="GET", query="", body=b"", content_type="application/x-www-form-urlencoded",
             length=None, max_body=1 << 20, **extra):
    environ = {"REQUEST_METHOD": method, "QUERY_STRING": query, "CONTENT_TYPE": content_type,
               "CONTENT_LENGTH": str(len(body) if length is None else length), "wsgi.input": io.BytesIO(body),
               "wsgi.url_scheme": "http", "REMOTE_ADDR": "10.0.0.1", "PATH_INFO": "/app/tickets/index/17"}
    environ.update(extra)
    return Request(environ, ROUTE, max_body)


class QueryTest(unittest.TestCase):
    """Consulta (GET)."""

    def test_repeated_keys_become_list_and_utf8(self):
        """Chave repetida vira lista na ordem; '+' e espaco; UTF-8 decodificado; valor vazio mantido."""
        result = parse_query("status=A&status=B&q=s%C3%A3o+paulo&empty=&flag")
        self.assertEqual(result, {"status": ["A", "B"], "q": "são paulo", "empty": "", "flag": ""})

    def test_semicolon_is_not_a_separator(self):
        """So '&' separa (igual do 3.6 ao 3.13; o ';' era separador antes do 3.6.13)."""
        self.assertEqual(parse_query("a=1;b=2"), {"a": "1;b=2"})

    def test_invalid_utf8_and_too_many_fields(self):
        """UTF-8 invalido: 400; campos demais: 413."""
        with self.assertRaises(HTTP) as ctx:
            parse_query("a=%ff")
        self.assertEqual(ctx.exception.status, 400)
        with self.assertRaises(HTTP) as ctx:
            parse_query("&".join("f%d=1" % i for i in range(MAX_FIELDS + 1)))
        self.assertEqual(ctx.exception.status, 413)


class BodyTest(unittest.TestCase):
    """Corpo do POST: so lido quando post_vars e usado."""

    def test_urlencoded_and_vars_merge_like_web2py(self):
        """GET e POST com a mesma chave viram lista em vars, GET primeiro."""
        request = _request("POST", "a=1&page=2", b"a=2&_csrf=t&id=7")
        self.assertEqual(request.post_vars, {"a": "2", "_csrf": "t", "id": "7"})
        self.assertEqual(request.vars, {"a": ["1", "2"], "page": "2", "_csrf": "t", "id": "7"})
        self.assertEqual((request.args, request.controller, request.extension), (["17"], "tickets", "html"))

    def test_json_object_goes_to_post_vars(self):
        """application/json com objeto vai para post_vars (previas do fetch); lista fica de fora."""
        body = json.dumps({"script_id": "1", "answers": {"data_ref": "2026-10-24"}}).encode()
        request = _request("POST", body=body, content_type="application/json; charset=utf-8")
        self.assertEqual(request.post_vars["answers"], {"data_ref": "2026-10-24"})
        self.assertEqual(_request("POST", body=b"[1,2]", content_type="application/json").post_vars, {})

    def test_bad_bodies(self):
        """JSON invalido, urlencoded fora de ASCII, corpo truncado e Content-Length invalido: 400."""
        cases = (dict(body=b"{x", content_type="application/json"), dict(body=b"a=\xff"),
                 dict(body=b"a=1", length=10), dict(body=b"a=1", length="abc"), dict(body=b"a=1", length=-1))
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(HTTP) as ctx:
                    _request("POST", **case).post_vars
                self.assertEqual(ctx.exception.status, 400)

    def test_body_above_limit_is_not_read(self):
        """Content-Length acima do limite: 413 sem ler o corpo."""
        request = _request("POST", body=b"a=1", length=100, max_body=10)
        with self.assertRaises(HTTP) as ctx:
            request.post_vars
        self.assertEqual(ctx.exception.status, 413)
        self.assertEqual(request.environ["wsgi.input"].tell(), 0)

    def test_get_has_no_post_vars_and_other_types_keep_body(self):
        """GET nao le corpo; tipo desconhecido fica em body com post_vars vazio."""
        self.assertEqual(_request("GET", body=b"a=1").post_vars, {})
        request = _request("POST", body=b"<x/>", content_type="text/xml")
        self.assertEqual((request.post_vars, request.body), ({}, b"<x/>"))

    def test_multipart_upload_and_close(self):
        """Upload chega com .file e .filename; close() fecha o temporario."""
        boundary = "b0undary"
        body = (b"--b0undary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.txt\"\r\n\r\n"
                b"conteudo\r\n--b0undary--\r\n")
        request = _request("POST", body=body, content_type="multipart/form-data; boundary=%s" % boundary)
        upload = request.post_vars["file"]
        self.assertEqual((upload.filename, upload.file.read()), ("a.txt", b"conteudo"))
        request.close()
        self.assertTrue(upload.file.closed)


class EnvironmentTest(unittest.TestCase):
    """env, cookies e HTTPS."""

    def test_env_names_like_web2py(self):
        """Chaves do environ em minusculas, com '.' trocado por '_'; ausente le None."""
        request = _request(HTTP_X_FORWARDED_FOR="1.2.3.4", HTTP_ORIGIN="https://sss")
        self.assertEqual((request.env.request_method, request.env.remote_addr, request.env.wsgi_url_scheme,
                          request.env.http_x_forwarded_for, request.env.http_origin, request.env.http_referer),
                         ("GET", "10.0.0.1", "http", "1.2.3.4", "https://sss", None))

    def test_malformed_cookie_header_gives_no_cookies(self):
        """Cabecalho de cookie quebrado nao derruba a requisicao: segue sem cookies."""
        self.assertEqual(len(_request(HTTP_COOKIE='a="b').cookies), 0)
        self.assertEqual(_request(HTTP_COOKIE="sss_session=v1.x.y").cookies["sss_session"].value, "v1.x.y")

    def test_is_https(self):
        """https pelo esquema, por HTTPS=on ou pelo X-Forwarded-Proto (como no web2py)."""
        self.assertFalse(_request().is_https)
        self.assertTrue(_request(**{"wsgi.url_scheme": "https"}).is_https)
        self.assertTrue(_request(HTTP_X_FORWARDED_PROTO="https").is_https)


class ResponseTest(unittest.TestCase):
    """Resposta: JSON seguro, cookies e cabecalhos."""

    def test_json_is_safe_inside_html(self):
        """'<', '>' e '&' escapados; datas no formato do web2py; Decimal e set."""
        text = json_for_html({"t": "</script><b>&", "d": datetime.datetime(2026, 10, 24, 9, 5, 7, 123),
                              "n": decimal.Decimal("1.5"), "s": {2, 1}})
        self.assertNotIn("<", text)
        self.assertNotIn(">", text)
        self.assertNotIn("&", text)
        self.assertEqual(json.loads(text), {"t": "</script><b>&", "d": "2026-10-24 09:05:07", "n": 1.5,
                                            "s": [1, 2]})

    def test_json_sets_content_type_once(self):
        """json() marca application/json sem trocar um tipo ja escolhido pela action."""
        response = Response()
        response.json({})
        self.assertEqual(response.headers["Content-Type"], "application/json")
        response.headers["Content-Type"] = "text/plain"
        response.json({})
        self.assertEqual(response.headers["Content-Type"], "text/plain")

    def test_cookie_attributes(self):
        """HttpOnly, SameSite e Secure no Set-Cookie; valor e nome fora do formato recusados."""
        self.assertEqual(cookie_header("sss_session", "v1.a.b", path="/app/", secure=True),
                         "sss_session=v1.a.b; Path=/app/; SameSite=Lax; HttpOnly; Secure")
        self.assertNotIn("Secure", cookie_header("s", "v", path="/", secure=False))
        for name, value in (("s;x", "v"), ("s", "v v"), ("s", 'a"b'), ("s", "a\r\nb")):
            with self.subTest(name=name, value=value):
                with self.assertRaises(ValueError):
                    cookie_header(name, value, path="/", secure=True)

    def test_header_injection_is_refused(self):
        """Quebra de linha em cabecalho: ValueError ao montar a resposta."""
        response = Response()
        response.headers["X-Test"] = "a\r\nSet-Cookie: x=1"
        with self.assertRaises(ValueError):
            response.wsgi_headers()

    def test_free_attributes(self):
        """Atributo livre le None quando ausente (response.title, response.flash, response.sss_*)."""
        response = Response()
        self.assertIsNone(response.flash)
        response.title = "SSS"
        self.assertEqual((response.title, response.status), ("SSS", 200))


class ErrorsTest(unittest.TestCase):
    """HTTP e redirect."""

    def test_redirect_is_303_with_location(self):
        """redirect levanta HTTP 303 com Location; quebra de linha no destino e recusada."""
        with self.assertRaises(HTTP) as ctx:
            redirect("/app/default/login?next=%2Fapp")
        self.assertEqual((ctx.exception.status, ctx.exception.headers["Location"]),
                         (303, "/app/default/login?next=%2Fapp"))
        with self.assertRaises(ValueError):
            redirect("/app\r\nSet-Cookie: x=1")

    def test_status_range(self):
        """Status fora de 100 a 599 e erro de programacao."""
        with self.assertRaises(ValueError):
            HTTP(99)


if __name__ == "__main__":
    unittest.main()
