# -*- coding: utf-8 -*-
"""Contrato dos componentes em JavaScript puro (CR-021, D7; AGENTS §2.3).

Confere, sem navegador, que:
1. nenhuma view usa a sintaxe do Alpine, e o Alpine nao esta mais em static/js/;
2. todo ``data-component`` das views tem registro em ``static/js/app/`` e todo registro e usado;
3. ``static/js/app/`` nao monta HTML a partir de texto nem avalia codigo;
4. o layout carrega o ``dom.js`` antes de qualquer outro script da aplicacao;
5. os tipos de notificacao aceitos pelo ``sss.js`` sao os modificadores ``.sss-toast-*`` do ``sss.css``;
6. os blocos condicionais da regra de agendamento (``data-types``) citam so tipos de recorrencia do servico;
7. todo atributo ``data-*`` dos seletores do roteiro de homologacao existe nas views, nos JS ou nos helpers.
"""
import io
import os
import re
import unittest

from tests.support import _testenv  # noqa: F401 - ajusta sys.path sem importar gluon
from sss.services import schedules_service

APP_DIR = _testenv.APP_DIR
VIEWS_DIR = os.path.join(APP_DIR, "views")
JS_DIR = os.path.join(APP_DIR, "static", "js", "app")
CSS_FILE = os.path.join(APP_DIR, "static", "css", "sss.css")
EVIDENCE_SCRIPT = os.path.join(APP_DIR, "dev", "homologation", "tools", "capture_evidence.js")
UI_DIR = os.path.join(APP_DIR, "src", "sss", "ui")

_RE_TEMPLATE_CODE = re.compile(r"\{\{.*?\}\}", re.S)
_RE_ALPINE_SYNTAX = re.compile(r"(?<![\w-])(?:x-[a-z]+(?:[:.][\w.-]+)?|@[a-z][\w.-]*=|:[a-z][\w-]*=)")
_RE_DATA_COMPONENT = re.compile(r"\bdata-component=\"([A-Za-z]+)\"")
_RE_REGISTRATION = re.compile(r"\bSSS\.component\(\s*'([A-Za-z]+)'")
_RE_JS_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
_FORBIDDEN_JS = (
    (re.compile(r"\.(?:innerHTML|outerHTML)\b"), "innerHTML/outerHTML"),
    (re.compile(r"\binsertAdjacentHTML\b"), "insertAdjacentHTML"),
    (re.compile(r"\bdocument\.write(?:ln)?\b"), "document.write"),
    (re.compile(r"\beval\s*\("), "eval"),
    (re.compile(r"\bnew\s+Function\b"), "new Function"),
    (re.compile(r"\bAlpine\b|alpine:"), "Alpine"),
)
_RE_SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc=\"\{\{=URL\('static',\s*'?([^')]+)'?\)\}\}\"")
_RE_TOAST_TYPES = re.compile(r"var TOAST_TYPES = \{([^}]*)\}")
_RE_TOAST_MODIFIER = re.compile(r"\.sss-toast-([a-z]+)\b")
_RE_DATA_TYPES = re.compile(r"\bdata-types=\"([^\"]*)\"")
_RE_SELECTOR_DATA_ATTR = re.compile(r"\[(data-[a-z0-9-]+)")
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
            if name.endswith((".html", ".load")):
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


class NoAlpineTest(unittest.TestCase):
    """O Alpine saiu do projeto (CR-021b2)."""

    def test_views_have_no_alpine_syntax(self):
        """Nenhuma diretiva, evento ou ligacao do Alpine em nenhuma view."""
        for name, content in sorted(_views().items()):
            found = _RE_ALPINE_SYNTAX.findall(_markup(content))
            self.assertEqual(found, [], "%s usa Alpine: %s" % (name, sorted(set(found))))

    def test_alpine_bundle_is_gone(self):
        """O bundle do Alpine nao volta para static/js/."""
        self.assertFalse(os.path.exists(os.path.join(APP_DIR, "static", "js", "alpine.min.js")))


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
        """Sem montar HTML a partir de texto, sem avaliar codigo e sem Alpine."""
        for name, code in _scripts().items():
            for pattern, label in _FORBIDDEN_JS:
                self.assertIsNone(pattern.search(code), "%s usa %s" % (name, label))


class LayoutOrderTest(unittest.TestCase):
    """Ordem dos scripts no layout."""

    def test_dom_js_loads_first(self):
        """O dom.js vem antes dos arquivos que registram componentes, e o Alpine nao e carregado."""
        sources = _RE_SCRIPT_SRC.findall(_read(os.path.join(VIEWS_DIR, "layout.html")))
        self.assertTrue(sources, "nenhum script no layout")
        self.assertEqual(sources[0], "js/app/dom.js")
        self.assertIn("js/app/sss.js", sources)
        self.assertIn("js/app/components.js", sources)
        self.assertNotIn("js/alpine.min.js", sources)


class ToastTypesTest(unittest.TestCase):
    """Regressao do CR-021a: o tipo 'warning' caia em 'info'."""

    def test_toast_types_match_css_modifiers(self):
        """Os tipos aceitos pelo sss.js sao os modificadores do sss.css."""
        match = _RE_TOAST_TYPES.search(_read(os.path.join(JS_DIR, "sss.js")))
        self.assertIsNotNone(match, "TOAST_TYPES ausente do sss.js")
        js_types = set(re.findall(r"([a-z]+)\s*:", match.group(1)))
        css_types = set(_RE_TOAST_MODIFIER.findall(_read(CSS_FILE))) - _TOAST_PARTS
        self.assertEqual(js_types, css_types)


class ScheduleRuleTypesTest(unittest.TestCase):
    """Blocos condicionais da regra de agendamento (componente scheduleRule)."""

    def test_data_types_are_recurrence_types(self):
        """Todo data-types cita so tipos de schedules_service.TYPE_LABELS, e todo tipo tem bloco."""
        blocks = _RE_DATA_TYPES.findall(_read(os.path.join(VIEWS_DIR, "schedules", "form.html")))
        self.assertTrue(blocks, "nenhum bloco condicional na regra de agendamento")
        mentioned = set()
        for block in blocks:
            types = block.split(" ")
            self.assertTrue(set(types) <= set(schedules_service.TYPE_LABELS), "tipo desconhecido em %r" % block)
            mentioned.update(types)
        self.assertEqual(mentioned, set(schedules_service.TYPE_LABELS))


class EvidenceScriptContractTest(unittest.TestCase):
    """Regressao do CR-021b2: o roteiro clicava em button[data-summary-trigger], que saiu com o Alpine, e a
    homologacao real nao criava nenhum ticket."""

    def test_selector_data_attributes_exist(self):
        """Todo [data-*] dos seletores do capture_evidence.js aparece no HTML ou no JS da aplicacao."""
        markup = "".join(_views().values()) + "".join(_scripts().values())
        for name in sorted(os.listdir(UI_DIR)):
            if name.startswith("ui_") and name.endswith(".py"):
                markup += _read(os.path.join(UI_DIR, name))
        used = set(_RE_SELECTOR_DATA_ATTR.findall(_read(EVIDENCE_SCRIPT)))
        self.assertTrue(used, "nenhum seletor data-* no roteiro")
        self.assertEqual(sorted(a for a in used if a not in markup), [])


if __name__ == "__main__":
    unittest.main()
