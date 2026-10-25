# -*- coding: utf-8 -*-
"""Arquivos estaticos (CR-021d1b): so dentro de static/, sem listagem, com revalidacao (304)."""
import email.utils
import os
import shutil
import tempfile
import unittest

from tests.support import _testenv  # noqa: F401 - ajusta sys.path sem importar gluon
from sss.web.framework import static
from sss.web.framework.errors import HTTP


class StaticTest(unittest.TestCase):
    """serve() sobre uma pasta estatica temporaria, com um segredo ao lado dela."""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base)
        self.root = os.path.join(self.base, "static")
        os.makedirs(os.path.join(self.root, "js", "app"))
        with open(os.path.join(self.root, "js", "app", "dom.js"), "w") as handle:
            handle.write("var x = 1;\n")
        with open(os.path.join(self.root, ".gitkeep"), "w") as handle:
            handle.write("")
        with open(os.path.join(self.base, "secrets.cfg"), "w") as handle:
            handle.write("cookie_key = segredo\n")

    def serve(self, relative, method="GET", **headers):
        return static.serve(self.root, relative, method, headers)

    def assertStatus(self, status, relative, method="GET"):
        with self.assertRaises(HTTP) as ctx:
            self.serve(relative, method)
        self.assertEqual(ctx.exception.status, status)

    def test_get_streams_file_with_headers(self):
        """Conteudo em blocos, tipo certo, tamanho, nosniff, no-cache e validadores."""
        response = self.serve("js/app/dom.js")
        body = b"".join(response.body)
        response.body.close()
        self.assertEqual(body, b"var x = 1;\n")
        headers = response.headers
        self.assertEqual((headers["Content-Type"], headers["Content-Length"]),
                         ("application/javascript; charset=utf-8", str(len(body))))
        self.assertEqual((headers["X-Content-Type-Options"], headers["Cache-Control"]),
                         ("nosniff", "no-cache"))
        self.assertTrue(headers["ETag"].startswith('"'))
        self.assertTrue(headers["Last-Modified"].endswith("GMT"))

    def test_head_has_length_without_body(self):
        """HEAD: mesmos cabecalhos, corpo vazio."""
        response = self.serve("js/app/dom.js", "HEAD")
        self.assertEqual((response.body, response.headers["Content-Length"]), (b"", "11"))

    def test_revalidation(self):
        """ETag igual ou data nao anterior: 304 sem corpo; ETag diferente: 200."""
        first = self.serve("js/app/dom.js")
        first.body.close()
        etag, modified = first.headers["ETag"], first.headers["Last-Modified"]
        self.assertEqual(self.serve("js/app/dom.js", if_none_match=etag).status, 304)
        self.assertEqual(self.serve("js/app/dom.js", if_none_match='"x", ' + etag).status, 304)
        self.assertEqual(self.serve("js/app/dom.js", if_modified_since=modified).status, 304)
        changed = self.serve("js/app/dom.js", if_none_match='"outra"')
        changed.body.close()
        self.assertEqual(changed.status, 200)
        older = email.utils.formatdate(0, usegmt=True)
        stale = self.serve("js/app/dom.js", if_modified_since=older)
        stale.body.close()
        self.assertEqual(stale.status, 200)

    def test_close_before_reading_closes_the_file(self):
        """Fechar o corpo sem ler (cliente desistiu) fecha o arquivo."""
        response = self.serve("js/app/dom.js")
        handle = response.body._handle  # pylint: disable=protected-access
        response.body.close()
        self.assertTrue(handle.closed)

    def test_only_get_and_head(self):
        """POST e outros metodos: 405 com Allow."""
        with self.assertRaises(HTTP) as ctx:
            self.serve("js/app/dom.js", "POST")
        self.assertEqual((ctx.exception.status, ctx.exception.headers["Allow"]), (405, "GET, HEAD"))

    def test_refusals(self):
        """Fora de static/, oculto, pasta, inexistente e vazio: 404."""
        for relative in ("../secrets.cfg", "js/../../secrets.cfg", ".gitkeep", "js/.hidden", "js",
                         "js/app", "nada.js", "", "js//app/dom.js"):
            with self.subTest(relative=relative):
                self.assertStatus(404, relative)

    def test_symlink_out_of_static_is_refused(self):
        """Link dentro de static/ apontando para fora: 404 (o caminho real decide)."""
        os.symlink(os.path.join(self.base, "secrets.cfg"), os.path.join(self.root, "leak.txt"))
        self.assertStatus(404, "leak.txt")

    def test_symlink_inside_static_is_served(self):
        """Link que continua dentro de static/ funciona."""
        os.symlink(os.path.join(self.root, "js", "app", "dom.js"), os.path.join(self.root, "alias.js"))
        response = self.serve("alias.js")
        self.assertEqual(b"".join(response.body), b"var x = 1;\n")
        response.body.close()

    def test_content_types(self):
        """Tipos dos ativos do SSS; desconhecido e octet-stream."""
        self.assertEqual(static.content_type("a.css"), "text/css; charset=utf-8")
        self.assertEqual(static.content_type("a.svg"), "image/svg+xml")
        self.assertEqual(static.content_type("a.woff2"), "font/woff2")
        self.assertEqual(static.content_type("a.png"), "image/png")
        self.assertEqual(static.content_type("a.xyz123"), "application/octet-stream")


if __name__ == "__main__":
    unittest.main()
