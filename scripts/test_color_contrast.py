# -*- coding: utf-8 -*-
"""Contraste WCAG 2.1 dos tokens de cor de static/css/sss.css (identidade Kyros, modos claro e escuro).

Texto: >= 4.5:1 (AA). Indicadores nao textuais (foco, faixas, bordas de destaque): >= 3:1.
"""
import _testenv  # noqa: F401

import os
import re
import unittest

CSS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "css", "sss.css")
_RE_TOKEN = re.compile(r"--(sss-[a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;")

# Pares (texto, fundo) efetivamente usados pela interface.
TEXT_PAIRS = (
    ("sss-text", "sss-bg"), ("sss-text", "sss-surface"), ("sss-text", "sss-surface-alt"),
    ("sss-text-muted", "sss-surface"), ("sss-text-muted", "sss-bg"),
    ("sss-accent-text", "sss-accent"), ("sss-accent-text", "sss-accent-hover"),
    ("sss-link", "sss-surface"), ("sss-link", "sss-bg"),
    ("sss-header-text", "sss-header-bg"), ("sss-header-muted", "sss-header-bg"),
    ("sss-header-active-text", "sss-header-active-bg"),
    ("sss-banner-text", "sss-banner-bg"),
    ("sss-status-pending-fg", "sss-status-pending-bg"), ("sss-status-running-fg", "sss-status-running-bg"),
    ("sss-status-success-fg", "sss-status-success-bg"), ("sss-status-failed-fg", "sss-status-failed-bg"),
    ("sss-status-cancelled-fg", "sss-status-cancelled-bg"), ("sss-status-unknown-fg", "sss-status-unknown-bg"),
)
INDICATOR_PAIRS = (
    ("sss-focus", "sss-surface"), ("sss-focus", "sss-bg"), ("sss-header-focus", "sss-header-bg"),
    ("sss-header-stripe", "sss-header-bg"),
)
KYROS_PALETTE = {"#4daf9a", "#68d8bd", "#38977f", "#5f0684", "#831fb2", "#430463", "#faba00", "#ffce55", "#f8a600"}


def _luminance(hexa):
    channels = []
    for i in (1, 3, 5):
        c = int(hexa[i:i + 2], 16) / 255.0
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(a, b):
    """Razao de contraste WCAG entre duas cores #rrggbb."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _chunks():
    with open(CSS, encoding="utf-8") as f:
        css = f.read()
    ini = css.index(":root {")
    dark = css.index("@media (prefers-color-scheme: dark)")
    light = dict(_RE_TOKEN.findall(css[ini:dark]))
    end_dark = css.index("/* Base */", dark)
    tokens_dark = dict(light, **dict(_RE_TOKEN.findall(css[dark:end_dark])))
    return {"claro": light, "escuro": tokens_dark}


class TestColorContrast(unittest.TestCase):

    def setUp(self):
        self.themes = _chunks()

    def test_formula(self):
        self.assertAlmostEqual(contrast("#000000", "#ffffff"), 21.0, places=2)
        self.assertAlmostEqual(contrast("#ffffff", "#ffffff"), 1.0, places=2)
        # Fato que orienta a paleta: azul esverdeado sobre branco nao serve para texto.
        self.assertLess(contrast("#4daf9a", "#ffffff"), 4.5)

    def test_texto_aa(self):
        for theme, tokens in self.themes.items():
            for fg, bg in TEXT_PAIRS:
                with self.subTest(tema=theme, par=(fg, bg)):
                    r = contrast(tokens[fg], tokens[bg])
                    self.assertGreaterEqual(r, 4.5, "%s: %s %s / %s %s = %.2f" % (
                        theme, fg, tokens[fg], bg, tokens[bg], r))

    def test_indicadores_nao_textuais(self):
        for theme, tokens in self.themes.items():
            for fg, bg in INDICATOR_PAIRS:
                with self.subTest(tema=theme, par=(fg, bg)):
                    self.assertGreaterEqual(contrast(tokens[fg], tokens[bg]), 3.0)

    def test_cores_principais_sao_da_paleta_kyros(self):
        for theme, tokens in self.themes.items():
            for token in ("sss-accent", "sss-header-stripe", "sss-header-active-bg", "sss-banner-bg"):
                with self.subTest(tema=theme, token=token):
                    self.assertIn(tokens[token].lower(), KYROS_PALETTE)
        light = self.themes["claro"]
        self.assertEqual((light["sss-brand-green"], light["sss-brand-purple"], light["sss-brand-yellow"]),
                         ("#4daf9a", "#5f0684", "#faba00"))

    def test_fontes_locais(self):
        with open(CSS, encoding="utf-8") as f:
            css = f.read()
        sources = re.findall(r'url\("\.\./fonts/montserrat/([^"]+)"\)', css)
        self.assertEqual(len(sources), 10)
        base = os.path.join(os.path.dirname(CSS), "..", "fonts", "montserrat")
        for name in sources:
            self.assertTrue(os.path.isfile(os.path.join(base, name)), name)
        self.assertTrue(os.path.isfile(os.path.join(base, "OFL.txt")))


if __name__ == "__main__":
    unittest.main()
