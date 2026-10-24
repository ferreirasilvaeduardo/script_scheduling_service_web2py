# -*- coding: utf-8 -*-
"""Contrato dos componentes em JavaScript puro (CR-021, D7; AGENTS §2.3).

Confere, sem navegador, que:
1. as views convertidas no CR-021a e no CR-021b1 nao usam mais a sintaxe do Alpine, e os componentes Alpine retirados
   nao aparecem em nenhuma view;
2. todo ``data-component`` das views tem registro em ``static/js/app/`` e todo registro e usado;
3. ``static/js/app/`` nao monta HTML a partir de texto nem avalia codigo;
4. o layout carrega o ``dom.js`` antes de qualquer outro script da aplicacao;
5. os tipos de notificacao aceitos pelo ``sss.js`` sao os modificadores ``.sss-toast-*`` do ``sss.css``.
"""
import io
import os
import re
import unittest

import _testenv  # noqa: F401 - ajusta sys.path sem importar gluon

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWS_DIR = os.path.join(APP_DIR, "views")
JS_DIR = os.path.join(APP_DIR, "static", "js", "app")
CSS_FILE = os.path.join(APP_DIR, "static", "css", "sss.css")

# Views sem nenhum Alpine depois do CR-021a e do CR-021b1.
CONVERTED_VIEWS = (
    "layout.html",
    "admin_parameters/form.html",
    "admin_users/form.html",
    "audit/agents.html",
    "components/confirm_modal.html",
    "components/filters.html",
    "dev/components.html",
    "dev/shell.html",
    "inputs/index.html",
    "tickets/catalog.html",
    "tickets/detail.html",
    "tickets/index.html",
)
# Componentes Alpine ja convertidos (o x-data deles nao pode reaparecer).
RETIRED_ALPINE_COMPONENTS = (
    "agentsRefresh", "copy", "filters", "inputUpload", "logViewer", "parameterForm", "scriptSearch",
    "ticketsRefresh", "toast", "toastDemo",
)
# O 'confirmation' do Alpine so sobrevive onde o modal usa o estado de outro componente Alpine (CR-021b).
ALPINE_CONFIRMATION_VIEWS = (
    "admin_profiles/matrix.html",
    "admin_scripts/homologation.html",
    "tickets/new.html",
)

_RE_TEMPLATE_CODE = re.compile(r"\{\{.*?\}\}", re.S)
_RE_ALPINE_SYNTAX = re.compile(r"(?<![\w-])(?:x-[a-z]+(?:[:.][\w.-]+)?|@[a-z][\w.-]*=|:[a-z][\w-]*=)")
_RE_X_DATA = re.compile(r"\bx-data=\"([A-Za-z]+)\"")
_RE_DATA_COMPONENT = re.compile(r"\bdata-component=\"([A-Za-z]+)\"")
_RE_REGISTRATION = re.compile(r"\bSSS\.component\(\s*'([A-Za-z]+)'")
_RE_JS_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
_FORBIDDEN_JS = (
    (re.compile(r"\.(?:innerHTML|outerHTML)\b"), "innerHTML/outerHTML"),
    (re.compile(r"\binsertAdjacentHTML\b"), "insertAdjacentHTML"),
    (re.compile(r"\bdocument\.write(?:ln)?\b"), "document.write"),
    (re.compile(r"\beval\s*\("), "eval"),
    (re.compile(r"\bnew\s+Function\b"), "new Function"),
)
_RE_SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc=\"\{\{=URL\('static',\s*'?([^')]+)'?\)\}\}\"")
_RE_TOAST_TYPES = re.compile(r"var TOAST_TYPES = \{([^}]*)\}")
_RE_TOAST_MODIFIER = re.compile(r"\.sss-toast-([a-z]+)\b")
# Partes estruturais do toast, nao tipos de notificacao.
_TOAST_PARTS = {"msg", "close"}


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _views():
    """Devolve {caminho relativo: conteudo} de todas as views."""
    result = {}
    for base, _dirs, files in os.walk(VIEWS_DIR):
        for name in files:
            if name.endswith(".html"):
                path = os.path.join(base, name)
                result[os.path.relpath(path, VIEWS_DIR).replace(os.sep, "/")] = _read(path)
    return result


def _scripts():
    """Devolve {nome do arquivo: codigo sem comentarios} de static/js/app/."""
    return dict(
        (name, _RE_JS_COMMENT.sub("", _read(os.path.join(JS_DIR, name))))
        for name in sorted(os.listdir(JS_DIR)) if name.endswith(".js")
    )


def _markup(content):
    """Tira os blocos de codigo do template, que tem ':' e '@' de Python."""
    return _RE_TEMPLATE_CODE.sub("", content)


class ConvertedViewsTest(unittest.TestCase):
    """Views convertidas sem Alpine e componentes Alpine retirados."""

    def test_converted_views_have_no_alpine_syntax(self):
        """Nenhuma diretiva, evento ou ligacao do Alpine nas views convertidas."""
        views = _views()
        for name in CONVERTED_VIEWS:
            found = _RE_ALPINE_SYNTAX.findall(_markup(views[name]))
            self.assertEqual(found, [], "%s ainda usa Alpine: %s" % (name, sorted(set(found))))

    def test_retired_alpine_components_are_gone(self):
        """Nenhuma view usa um componente Alpine ja convertido."""
        for name, content in _views().items():
            for component in _RE_X_DATA.findall(content):
                self.assertNotIn(component, RETIRED_ALPINE_COMPONENTS,
                                 "%s usa o componente Alpine retirado %s" % (name, component))

    def test_alpine_confirmation_only_in_coupled_views(self):
        """O 'confirmation' do Alpine sobrevive so nas tres telas acopladas."""
        users = sorted(name for name, content in _views().items()
                       if "confirmation" in _RE_X_DATA.findall(content))
        self.assertEqual(users, sorted(ALPINE_CONFIRMATION_VIEWS))


class ComponentRegistryTest(unittest.TestCase):
    """Views e registros de componentes em correspondencia."""

    def test_every_component_is_registered_and_used(self):
        """Todo data-component tem registro unico, e todo registro e usado."""
        used = set()
        for content in _views().values():
            used.update(_RE_DATA_COMPONENT.findall(content))
        registered = []
        for code in _scripts().values():
            registered.extend(_RE_REGISTRATION.findall(code))
        self.assertEqual(len(registered), len(set(registered)), "componente registrado duas vezes")
        self.assertEqual(sorted(used - set(registered)), [], "data-component sem registro")
        self.assertEqual(sorted(set(registered) - used), [], "registro sem data-component")


class ScriptSafetyTest(unittest.TestCase):
    """APIs proibidas em static/js/app/."""

    def test_no_html_from_text_nor_code_evaluation(self):
        """Sem montar HTML a partir de texto e sem avaliar codigo."""
        for name, code in _scripts().items():
            for pattern, label in _FORBIDDEN_JS:
                self.assertIsNone(pattern.search(code), "%s usa %s" % (name, label))


class LayoutOrderTest(unittest.TestCase):
    """Ordem dos scripts no layout."""

    def test_dom_js_loads_first(self):
        """O dom.js vem antes dos arquivos que registram componentes."""
        sources = _RE_SCRIPT_SRC.findall(_read(os.path.join(VIEWS_DIR, "layout.html")))
        self.assertTrue(sources, "nenhum script no layout")
        self.assertEqual(sources[0], "js/app/dom.js")
        self.assertIn("js/app/sss.js", sources)
        self.assertIn("js/app/components.js", sources)


class ToastTypesTest(unittest.TestCase):
    """Regressao do CR-021a: o tipo 'warning' caia em 'info'."""

    def test_toast_types_match_css_modifiers(self):
        """Os tipos aceitos pelo sss.js sao os modificadores do sss.css."""
        match = _RE_TOAST_TYPES.search(_read(os.path.join(JS_DIR, "sss.js")))
        self.assertIsNotNone(match, "TOAST_TYPES ausente do sss.js")
        js_types = set(re.findall(r"([a-z]+)\s*:", match.group(1)))
        css_types = set(_RE_TOAST_MODIFIER.findall(_read(CSS_FILE))) - _TOAST_PARTS
        self.assertEqual(js_types, css_types)


if __name__ == "__main__":
    unittest.main()
