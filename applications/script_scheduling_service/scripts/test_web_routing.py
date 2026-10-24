# -*- coding: utf-8 -*-
"""Rotas do nucleo web (CR-021d1): url() igual ao gluon.html.URL e parse_path recusando o que nao e rota.

A paridade com o gluon vale enquanto ele existir no repositorio (sai no CR-021f); as views geram os mesmos
links no servidor novo (CR-021e).
"""
import unittest

import _testenv  # noqa: F401 - ajusta sys.path (modules/ e a raiz do web2py)
from web import routing

APP = "script_scheduling_service"

# Formas de chamada usadas nas views e nos controllers (levantadas no CR-021d1).
PARITY_CASES = (
    dict(c="default", f="index"),
    dict(c="tickets", f="detail", args=[17]),
    dict(c="tickets", f="detail", args=17),
    dict(c="tickets", f="detail", args=["a b", "ç/x", "#?&"]),
    dict(c="tickets", f="index", vars={"b": "2", "a": "1"}),
    dict(c="tickets", f="index", vars={"q": "são paulo & x=1", "z": None}),
    dict(c="tickets", f="index", vars={"status": ["A", "B"], "page": 2}),
    dict(c="tickets", f="index", vars={"n": 5, "t": True}),
    dict(c="tickets", f="index", anchor="sec 1"),
    dict(c="tickets", f="index", vars={"a": "1"}, anchor="x"),
    dict(c="tickets", f="index", args=[], vars={}),
    dict(c="outputs", f="files", args=[30], vars={"page": 3}),
    dict(c="schedules", f="form", vars={"script_id": 1, "environment": "PRODUCAO"}),
)


def _gluon_url(request_extension, **kwargs):
    from gluon import current
    from gluon.globals import Request
    from gluon.html import URL
    request = Request({})
    request.application, request.controller, request.function = APP, "tickets", "index"
    request.extension = request_extension
    current.request = request
    return URL(**kwargs)


def _our_url(request_extension, c, f, args=None, vars=None, anchor="", **kwargs):
    extension = None if kwargs.get("extension") is False else request_extension
    return routing.url(APP, c, f, args, vars, anchor, extension)


class UrlParityTest(unittest.TestCase):
    """url() gera o mesmo texto que o gluon.html.URL nas formas usadas pela aplicacao."""

    def test_actions_match_gluon(self):
        """Cada forma, nas extensoes html, load e json, e com extension=False."""
        for extension in ("html", "load", "json"):
            for case in PARITY_CASES:
                for variant in (case, dict(case, extension=False)):
                    with self.subTest(extension=extension, case=variant):
                        self.assertEqual(_our_url(extension, **variant), _gluon_url(extension, **variant))

    def test_static_matches_gluon(self):
        """URL('static', ...) nunca leva extensao."""
        for extension in ("html", "load"):
            for path in ("img/icons.svg", "js/app/dom.js", "bootstrap/bootstrap.min.css"):
                with self.subTest(extension=extension, path=path):
                    self.assertEqual(routing.url(APP, "static", path, extension=extension),
                                     _gluon_url(extension, a="static", c=path))


class ParsePathTest(unittest.TestCase):
    """Leitura do PATH_INFO, que o servidor ja entrega decodificado (uma vez so)."""

    def test_route_with_extension_and_args(self):
        """Controller, funcao, extensao e args, sem decodificar de novo."""
        route = routing.parse_path("/%s/tickets/detail.load/17/a b" % APP, APP)
        self.assertEqual(route, routing.Route("tickets", "detail", "load", ["17", "a b"]))

    def test_defaults(self):
        """Sem funcao, index; sem extensao, html; barra final ignorada."""
        self.assertEqual(routing.parse_path("/%s/default/" % APP, APP),
                         routing.Route("default", "index", "html", []))

    def test_static(self):
        """Arquivo estatico com o caminho como veio."""
        self.assertEqual(routing.parse_path("/%s/static/js/app/dom.js" % APP, APP),
                         routing.StaticRoute("js/app/dom.js"))

    def test_no_double_decoding(self):
        """Regressao do CR-021d1b: %252e%252e chega do servidor como '%2e%2e' e fica literal.

        Antes o roteador decodificava de novo: '%2e%2e%2fmodels' virava '../models' (travessia).
        """
        self.assertEqual(routing.parse_path("/%s/static/%%2e%%2e/models/00_config.py" % APP, APP),
                         routing.StaticRoute("%2e%2e/models/00_config.py"))
        self.assertEqual(routing.parse_path("/%s/default/index/%%2e%%2e" % APP, APP).args, ["%2e%2e"])
        # O caso que abria a travessia: a barra codificada virava '../' dentro de um trecho so.
        self.assertEqual(
            routing.parse_path("/%s/static/%%2e%%2e%%2fmodels%%2f00_config.py" % APP, APP),
            routing.StaticRoute("%2e%2e%2fmodels%2f00_config.py"))

    def test_decode_path_info(self):
        """Latin-1 do WSGI vira UTF-8; UTF-8 invalido nao e rota."""
        raw = "/app/tickets/detail/ação".encode("utf-8").decode("latin-1")
        self.assertEqual(routing.decode_path_info(raw), "/app/tickets/detail/ação")
        with self.assertRaises(routing.InvalidPath):
            routing.decode_path_info(b"/app/\xff".decode("latin-1"))

    def test_rejects_what_is_not_a_route(self):
        """Travessia, funcao privada, formato, extensao e caracteres de controle nao sao rota."""
        bad = (
            "/outra_app/default/index", "/%s/" % APP, "/%s/default/_private" % APP,
            "/%s/Default/index" % APP, "/%s/default/index.php" % APP, "/%s/default/in-dex" % APP,
            "/%s/default/index/../x" % APP, "/%s/default/index/." % APP,
            "/%s/default/index/a\x00b" % APP, "/%s/default/index/a\nb" % APP,
            "/%s/default/index/a\\b" % APP, "/%s/default//index" % APP,
            "/%s/static/../models/00_config.py" % APP, "/%s/static/js/../../x" % APP,
        )
        for path in bad:
            with self.subTest(path=path):
                with self.assertRaises(routing.InvalidPath):
                    routing.parse_path(path, APP)


if __name__ == "__main__":
    unittest.main()
