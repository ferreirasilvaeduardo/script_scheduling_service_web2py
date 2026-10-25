# -*- coding: utf-8 -*-
"""Rotas do nucleo web (CR-021d1): url() igual ao gluon.html.URL e parse_path recusando o que nao e rota.

As URLs esperadas sao a saida do gluon.html.URL do web2py, gravada antes de o gluon sair do
repositorio (CR-021f1): as views geram os mesmos links que geravam no web2py.
"""
import unittest

from tests.support import _testenv  # noqa: F401 - ajusta sys.path (src/ e a raiz da aplicacao)
from sss.web.framework import routing

APP = "script_scheduling_service"

# Formas de chamada usadas nas views e nos controllers (levantadas no CR-021d1) e a saida do
# gluon.html.URL para cada uma. {ext} e '' em html e com extension=False; '.load' ou '.json' nas
# requisicoes com essa extensao (o web2py herdava a extensao da requisicao).
WEB2PY_URLS = (
    (dict(c="default", f="index"), "/script_scheduling_service/default/index{ext}"),
    (dict(c="tickets", f="detail", args=[17]), "/script_scheduling_service/tickets/detail{ext}/17"),
    (dict(c="tickets", f="detail", args=17), "/script_scheduling_service/tickets/detail{ext}/17"),
    (dict(c="tickets", f="detail", args=["a b", "ç/x", "#?&"]),
     "/script_scheduling_service/tickets/detail{ext}/a%20b/%C3%A7/x/%23%3F%26"),
    (dict(c="tickets", f="index", vars={"b": "2", "a": "1"}),
     "/script_scheduling_service/tickets/index{ext}?a=1&b=2"),
    (dict(c="tickets", f="index", vars={"q": "são paulo & x=1", "z": None}),
     "/script_scheduling_service/tickets/index{ext}?q=s%C3%A3o+paulo+%26+x%3D1&z=None"),
    (dict(c="tickets", f="index", vars={"status": ["A", "B"], "page": 2}),
     "/script_scheduling_service/tickets/index{ext}?page=2&status=A&status=B"),
    (dict(c="tickets", f="index", vars={"n": 5, "t": True}),
     "/script_scheduling_service/tickets/index{ext}?n=5&t=True"),
    (dict(c="tickets", f="index", anchor="sec 1"), "/script_scheduling_service/tickets/index{ext}#sec%201"),
    (dict(c="tickets", f="index", vars={"a": "1"}, anchor="x"),
     "/script_scheduling_service/tickets/index{ext}?a=1#x"),
    (dict(c="tickets", f="index", args=[], vars={}), "/script_scheduling_service/tickets/index{ext}"),
    (dict(c="outputs", f="files", args=[30], vars={"page": 3}),
     "/script_scheduling_service/outputs/files{ext}/30?page=3"),
    (dict(c="schedules", f="form", vars={"script_id": 1, "environment": "PRODUCAO"}),
     "/script_scheduling_service/schedules/form{ext}?environment=PRODUCAO&script_id=1"),
)


def _our_url(request_extension, c, f, args=None, vars=None, anchor="", **kwargs):
    extension = None if kwargs.get("extension") is False else request_extension
    return routing.url(APP, c, f, args, vars, anchor, extension)


class UrlParityTest(unittest.TestCase):
    """url() gera o mesmo texto que o gluon.html.URL gerava nas formas usadas pela aplicacao."""

    def test_actions_match_web2py(self):
        """Cada forma, nas extensoes html, load e json, e com extension=False."""
        for extension in ("html", "load", "json"):
            suffix = "" if extension == "html" else "." + extension
            for case, expected in WEB2PY_URLS:
                with self.subTest(extension=extension, case=case):
                    self.assertEqual(_our_url(extension, **case), expected.format(ext=suffix))
                    self.assertEqual(_our_url(extension, **dict(case, extension=False)),
                                     expected.format(ext=""))

    def test_static_never_has_extension(self):
        """URL('static', ...) nunca leva extensao, como no web2py."""
        for extension in ("html", "load"):
            for path in ("img/icons.svg", "js/app/dom.js", "bootstrap/bootstrap.min.css"):
                with self.subTest(extension=extension, path=path):
                    self.assertEqual(routing.url(APP, "static", path, extension=extension),
                                     "/script_scheduling_service/static/" + path)


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

    def test_application_root_is_default_index(self):
        """/<app> e /<app>/ sao default/index, como no web2py (D4); a raiz do servidor nao e rota."""
        for path in ("/%s" % APP, "/%s/" % APP):
            with self.subTest(path=path):
                self.assertEqual(routing.parse_path(path, APP), routing.Route("default", "index", "html", []))

    def test_rejects_what_is_not_a_route(self):
        """Travessia, funcao privada, formato, extensao e caracteres de controle nao sao rota."""
        bad = (
            "/outra_app/default/index", "/", "/%s//" % APP, "/%sx/" % APP, "/%s/default/_private" % APP,
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
