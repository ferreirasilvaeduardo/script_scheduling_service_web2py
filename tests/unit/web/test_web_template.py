# -*- coding: utf-8 -*-
"""Motor de templates (CR-021d2, D2): paridade com o web2py, seguranca, erros e cache.

O codigo gerado foi conferido view a view contra o yatl do web2py enquanto ele existia (CR-021d2 a
021e); a saida do template sintetico abaixo e a do render do web2py, gravada antes de o gluon sair do
repositorio (CR-021f1). Toda view real precisa compilar.
"""
import glob
import io
import os
import shutil
import tempfile
import time
import unittest

from tests.support import _testenv  # noqa: F401 - ajusta sys.path (src/ e a raiz da aplicacao)
from sss.web.framework import template
from sss.web.framework.markup import Markup, escape
from sss.web.framework.response import Response

APP_DIR = _testenv.APP_DIR
VIEWS_DIR = os.path.join(_testenv.WEB_DIR, "templates")


def _views():
    for path in sorted(glob.glob(os.path.join(VIEWS_DIR, "**", "*.*"), recursive=True)):
        yield os.path.relpath(path, VIEWS_DIR).replace(os.sep, "/")


class RealViewsTest(unittest.TestCase):
    """Toda view real gera codigo que compila (include, extend e pass conferidos)."""

    def test_all_views_compile(self):
        """Nenhuma view com include/extend invalido, pass faltando ou erro de sintaxe."""
        templates = template.Templates(VIEWS_DIR)
        checked = 0
        for name in _views():
            with self.subTest(view=name):
                templates._compiled(name)  # noqa: SLF001 pylint: disable=protected-access
                checked += 1
        self.assertGreaterEqual(checked, 40, "as views foram encontradas")


class _ViewsCase(unittest.TestCase):
    """Pasta de views temporaria."""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base)
        self.views = os.path.join(self.base, "views")
        os.makedirs(os.path.join(self.views, "components"))
        self.templates = template.Templates(self.views)

    def write(self, name, text):
        path = os.path.join(self.views, *name.split("/"))
        with io.open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def render(self, name, **context):
        context["response"] = Response()
        return self.templates.render(name, context)


SYNTHETIC = {
    "layout.html": "<html>\n<title>{{=title}}</title>\n{{include}}\n<footer>{{=n}}</footer>\n</html>\n",
    "components/item.html": "<li>{{=item}}</li>\n",
    "page.html": (
        "{{extend 'layout.html'}}\n"
        "{{# comentario}}\n"
        "<ul>\n{{for item in items:}}\n  {{include 'components/item.html'}}\n{{pass}}\n</ul>\n"
        "{{if n > 2:}}grande{{elif n == 2:}}dois{{else:}}pequeno{{pass}}\n"
        "{{\n"
        "def label(x):\n"
        "    if x is None:\n"
        "        return '-'\n"
        "    return str(x).upper()\n"
        "total = 0\n"
        "for v in [1, 2, 3]:\n"
        "    total += v\n"
        "pass\n"
        "}}\n"
        "<p>{{=label(None)}} {{=label('ok')}} {{=total}}</p>\n"
        "<p>{{=none}}|{{=num}}|{{=flag}}|{{=text}}</p>\n"
        "{{try:}}{{=1 / zero}}{{except ZeroDivisionError:}}div{{pass}}\n"
        "{{=\"\"\"linha 1\nlinha 2\"\"\"}}\n"
    ),
}


# Saida do gluon.template.render do web2py para o SYNTHETIC com o contexto do teste.
WEB2PY_OUTPUT = (
    "<html>\n"
    "<title>A &amp; B &lt;i&gt;</title>\n"
    "\n"
    "\n"
    "<ul>\n"
    "\n"
    "  <li>&lt;x&gt;</li>\n"
    "\n"
    "\n"
    "  <li>y&#x27;z</li>\n"
    "\n"
    "\n"
    "</ul>\n"
    "grande\n"
    "\n"
    "<p>- OK 6</p>\n"
    "<p>|1.5|True|&quot;aspas&quot; &amp; &#x27;apostrofo&#x27;</p>\n"
    "div\n"
    "linha 1\n"
    "linha 2\n"
    "\n"
    "<footer>3</footer>\n"
    "</html>\n"
)


class OutputParityTest(_ViewsCase):
    """Saida igual a do render do web2py, byte a byte, num template que usa cada construcao."""

    def test_synthetic_page(self):
        """extend, include em laco, if/elif/else, def/return, for, try/except, escape e texto."""
        for name, text in SYNTHETIC.items():
            self.write(name, text)
        context = dict(title="A & B <i>", n=3, items=["<x>", "y'z"], none=None, num=1.5, flag=True,
                       text='"aspas" & \'apostrofo\'', zero=0)
        ours = self.render("page.html", **dict(context))
        self.assertEqual(ours, WEB2PY_OUTPUT)
        self.assertIn("&lt;x&gt;", ours)
        self.assertIn("<footer>3</footer>", ours)


class EscapeTest(unittest.TestCase):
    """Escape do {{=x}} e o Markup."""

    def test_escape_like_web2py(self):
        """None vazio; numero e bool por str; texto com quote=True; Markup cru."""
        self.assertEqual(escape(None), "")
        self.assertEqual(escape(1.5), "1.5")
        self.assertEqual(escape(True), "True")
        self.assertEqual(escape("<script>alert('x')</script>&\""),
                         "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;&amp;&quot;")
        self.assertEqual(escape(Markup('<input type="hidden">')), '<input type="hidden">')

    def test_xml_method_is_not_trusted(self):
        """O .xml() do web2py nao passa cru: so Markup ou __html__."""
        class Helper:
            def xml(self):
                return "<b>cru</b>"

            def __str__(self):
                return "<b>cru</b>"
        self.assertEqual(escape(Helper()), "&lt;b&gt;cru&lt;/b&gt;")


class SecurityTest(_ViewsCase):
    """include/extend so por nome literal e so dentro de views/."""

    def assertRefused(self, text, fragment):
        self.write("bad.html", text)
        with self.assertRaises(template.TemplateError) as ctx:
            self.render("bad.html")
        self.assertIn(fragment, str(ctx.exception))

    def test_include_and_extend_refusals(self):
        """Travessia, absoluto, expressao, formato e inexistente: recusados sem ler nada."""
        with io.open(os.path.join(self.base, "secret.html"), "w") as handle:
            handle.write("SEGREDO FORA DE VIEWS")
        for text, fragment in (("{{include '../secret.html'}}", "fora do formato"),
                               ("{{include '/etc/passwd'}}", "fora do formato"),
                               ("{{include 'x' + '.html'}}", "so nome literal"),
                               ("{{include name}}", "so nome literal"),
                               ("{{extend response.view}}", "so nome literal"),
                               ("{{include 'Maiuscula.html'}}", "fora do formato"),
                               ("{{include 'nao_existe.html'}}", "inexistente")):
            with self.subTest(text=text):
                self.assertRefused(text, fragment)

    def test_symlink_out_of_views_is_refused(self):
        """Link dentro de views/ para fora: recusado pelo caminho real."""
        outside = os.path.join(self.base, "fora.html")
        with io.open(outside, "w") as handle:
            handle.write("fora")
        os.symlink(outside, os.path.join(self.views, "link.html"))
        self.assertRefused("{{include 'link.html'}}", "fora de templates/")

    def test_unsupported_tags(self):
        """block, end e super nao sao usados e sao recusados."""
        for word in ("block", "end", "super"):
            with self.subTest(word=word):
                self.assertRefused("{{%s x}}" % word, "nao e suportado")

    def test_data_is_escaped(self):
        """Dado com HTML sai escapado; so o Markup do codigo sai cru."""
        self.write("v.html", "{{=data}}|{{=safe}}")
        self.assertEqual(self.render("v.html", data="<script>x</script>", safe=Markup("<br>")),
                         "&lt;script&gt;x&lt;/script&gt;|<br>")


class ErrorsAndCacheTest(_ViewsCase):
    """Erros de compilacao e cache por data de modificacao."""

    def test_pass_errors_and_syntax(self):
        """pass faltando ou sobrando e sintaxe invalida: TemplateError com o nome da view."""
        for text, fragment in (("{{if x:}}a", "falta 'pass'"), ("a{{pass}}", "'pass' demais"),
                               ("{{x = = 1}}", "erro de sintaxe")):
            with self.subTest(text=text):
                self.write("e.html", text)
                self.templates = template.Templates(self.views)
                with self.assertRaises(template.TemplateError) as ctx:
                    self.render("e.html", x=1)
                self.assertIn("e.html", str(ctx.exception))
                self.assertIn(fragment, str(ctx.exception))

    def test_cache_follows_file_and_includes(self):
        """Mudar a view ou um arquivo incluido recompila; sem mudanca, usa o cache."""
        path = self.write("p.html", "A{{include 'components/i.html'}}")
        inner = self.write("components/i.html", "1")
        self.assertEqual(self.render("p.html"), "A1")
        cached = self.templates._cache["p.html"][1]  # noqa: SLF001
        self.assertEqual(self.render("p.html"), "A1")
        self.assertIs(self.templates._cache["p.html"][1], cached, "sem mudanca, mesmo codigo")
        for target, text, expected in ((inner, "2", "A2"), (path, "B{{include 'components/i.html'}}", "B2")):
            with self.subTest(target=os.path.basename(target)):
                with io.open(target, "w", encoding="utf-8") as handle:
                    handle.write(text)
                stamp = time.time() + 5
                os.utime(target, (stamp, stamp))
                self.assertEqual(self.render("p.html"), expected)


if __name__ == "__main__":
    unittest.main()
