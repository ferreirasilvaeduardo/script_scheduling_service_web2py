# -*- coding: utf-8 -*-
"""Testes de conformidade e compatibilidade com Python 3.6 estrito.

Verifica conformidade com AGENTS.md §2.1, §2.3, §3.2 e §7.4:
1. Compila todos os arquivos .py de APP (exceto dev/scripts/) e bin/ sob Python 3.6;
2. Procura tokens proibidos por regex (recursos >= 3.7, chamadas inseguras de processo, XML e x-html);
3. Procura URLs externas (http:// e https://) nos ativos frontend em static/js/app/, static/css/ e views/.
"""
import ast
import os
import re
import sys
import unittest

import _testenv  # noqa: F401 - ajusta sys.path sem importar gluon

# Lista explicita de arquivos de teste isentos da checagem de tokens proibidos (AGENTS §7.4)
ARQUIVOS_EXCECAO_TOKENS = {
    "test_py36_compat.py",
}

# Tokens e chamadas proibidos em Python 3.6 / SSS (AGENTS §2.1, §3.2, §3.4)
PADROES_PROIBIDOS = [
    # Python 3.7+
    (r"\bdataclasses\b", "modulo 'dataclasses' proibido (Python >= 3.7)"),
    (r"\bdataclass\b", "decorator 'dataclass' proibido (Python >= 3.7)"),
    (r"\bdatetime\.fromisoformat\b", "'datetime.fromisoformat' proibido (Python >= 3.7)"),
    (r"\basyncio\.run\b", "'asyncio.run' proibido (Python >= 3.7)"),
    (r"\bcontextlib\.nullcontext\b", "'contextlib.nullcontext' proibido (Python >= 3.7)"),
    (r"from\s+__future__\s+import\s+annotations", "'from __future__ import annotations' proibido (Python >= 3.7)"),
    (r"\btime\.time_ns\b", "'time.time_ns' proibido (Python >= 3.7)"),
    (r"\btime\.monotonic_ns\b", "'time.monotonic_ns' proibido (Python >= 3.7)"),
    (r"\bbreakpoint\s*\(", "funcao 'breakpoint()' proibida (Python >= 3.7)"),
    (r"\bcontextvars\b", "modulo 'contextvars' proibido (Python >= 3.7)"),
    (r"capture_output\s*=", "parametro 'capture_output' em subprocess proibido (Python >= 3.7)"),
    # Python 3.8+
    (r":=", "operador walrus ':=' proibido (Python >= 3.8)"),
    (r"\btyping\.Literal\b", "'typing.Literal' proibido (Python >= 3.8)"),
    (r"\btyping\.TypedDict\b", "'typing.TypedDict' proibido (Python >= 3.8)"),
    (r"\btyping\.Final\b", "'typing.Final' proibido (Python >= 3.8)"),
    (r"\btyping\.Protocol\b", "'typing.Protocol' proibido (Python >= 3.8)"),
    (r"\bcached_property\b", "'cached_property' proibido (Python >= 3.8)"),
    (r"\bmath\.prod\b", "'math.prod' proibido (Python >= 3.8)"),
    (r"\bshlex\.join\b", "'shlex.join' proibido (Python >= 3.8)"),
    # Python 3.9+
    (r"\.removeprefix\s*\(", "metodo 'removeprefix' proibido (Python >= 3.9)"),
    (r"\.removesuffix\s*\(", "metodo 'removesuffix' proibido (Python >= 3.9)"),
    (r"\bzoneinfo\b", "modulo 'zoneinfo' proibido (Python >= 3.9)"),
    (r"\bgraphlib\b", "modulo 'graphlib' proibido (Python >= 3.9)"),
    # Python 3.10+
    (r"\bitertools\.pairwise\b", "'itertools.pairwise' proibido (Python >= 3.10)"),
    # Processos e funcoes perigosas (AGENTS §3.2)
    (r"shell\s*=\s*True", "execucao com 'shell=True' proibida"),
    (r"\bos\.system\s*\(", "chamada a 'os.system' proibida"),
    (r"\bos\.popen\s*\(", "chamada a 'os.popen' proibida"),
    (r"\bsubprocess\.getoutput\s*\(", "chamada a 'subprocess.getoutput' proibida"),
    (r"\bsubprocess\.getstatusoutput\s*\(", "chamada a 'subprocess.getstatusoutput' proibida"),
    (r"\beval\s*\(", "uso de 'eval()' proibido"),
    (r"\bexec\s*\(", "uso de 'exec()' proibido"),
    (r"\bpickle\b", "modulo 'pickle' proibido"),
    (r"\bmarshal\b", "modulo 'marshal' proibido"),
    (r"\bshelve\b", "modulo 'shelve' proibido"),
    (r"yaml\.load\s*\(", "'yaml.load' inseguro proibido"),
    (r"\b__import__\s*\(", "'__import__' dinamico proibido"),
    (r"\bimportlib\b", "'importlib' dinamico com dado proibido"),
    # Web / Frontend (AGENTS §2.3, §3.4)
    (r"\bXML\s*\(", "escape 'XML()' inseguro com dados proibido"),
    (r"x-html", "diretiva 'x-html' proibida (use x-text)"),
]

_PADROES_COMPILADOS = [
    (re.compile(regex), desc) for regex, desc in PADROES_PROIBIDOS
]

_RE_URL_EXTERNA = re.compile(r"https?://", re.IGNORECASE)


def encontrar_arquivos_python(app_dir, web2py_root):
    """Localiza todos os arquivos .py de APP (exceto dev/scripts/) e bin/."""
    arquivos_py = []
    dev_scripts_dir = os.path.normpath(os.path.join(app_dir, "dev", "scripts"))

    # Varre a aplicacao
    for root, dirs, files in os.walk(app_dir):
        norm_root = os.path.normpath(root)
        if norm_root.startswith(dev_scripts_dir):
            continue
        if ".git" in dirs:
            dirs.remove(".git")
        if "__pycache__" in dirs:
            dirs.remove("__pycache__")

        for f in files:
            if f.endswith(".py"):
                arquivos_py.append(os.path.join(root, f))

    # Varre diretorios bin/
    for bin_cand in [os.path.join(app_dir, "bin"), os.path.join(web2py_root, "bin")]:
        if os.path.isdir(bin_cand):
            for root, dirs, files in os.walk(bin_cand):
                if "__pycache__" in dirs:
                    dirs.remove("__pycache__")
                for f in files:
                    if f.endswith(".py"):
                        p = os.path.join(root, f)
                        if p not in arquivos_py:
                            arquivos_py.append(p)

    return sorted(arquivos_py)


def compilar_arquivo_py(caminho):
    """Compila codigo fonte garantindo compatibilidade com Python 3.6."""
    with open(caminho, "r", encoding="utf-8") as f:
        src = f.read()

    # Quando interpretador >= 3.8, valida AST com feature_version 3.6
    if sys.version_info >= (3, 8):
        ast.parse(src, filename=caminho, feature_version=(3, 6))
    else:
        compile(src, caminho, "exec")


def verificar_tokens_proibidos_em_arquivo(caminho):
    """Procura tokens proibidos em um arquivo fonte, retornando lista de violacoes."""
    nome_base = os.path.basename(caminho)
    if nome_base in ARQUIVOS_EXCECAO_TOKENS:
        return []

    violacoes = []
    with open(caminho, "r", encoding="utf-8", errors="replace") as f:
        for num_linha, linha in enumerate(f, start=1):
            for regex, desc in _PADROES_COMPILADOS:
                if regex.search(linha):
                    violacoes.append((caminho, num_linha, desc, linha.strip()))
    return violacoes


def verificar_urls_externas_em_arquivo(caminho):
    """Procura URLs http:// e https:// em arquivos estaticos e views."""
    violacoes = []
    with open(caminho, "r", encoding="utf-8", errors="replace") as f:
        for num_linha, linha in enumerate(f, start=1):
            if _RE_URL_EXTERNA.search(linha):
                violacoes.append((caminho, num_linha, linha.strip()))
    return violacoes


class TestPy36Compat(unittest.TestCase):
    """Testes automatizados de compatibilidade com Python 3.6 e hermeticidade."""

    def setUp(self):
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        self.app_dir = os.path.dirname(scripts_dir)
        self.web2py_root = os.path.dirname(os.path.dirname(self.app_dir))

    def test_compilacao_python_36(self):
        """Compila todos os .py de APP e bin/ sob gramatica do Python 3.6."""
        arquivos = encontrar_arquivos_python(self.app_dir, self.web2py_root)
        self.assertGreater(len(arquivos), 0, "Deve encontrar arquivos .py para testar")

        falhas = []
        for caminho in arquivos:
            try:
                compilar_arquivo_py(caminho)
            except Exception as e:
                falhas.append("{}: {}".format(caminho, str(e)))

        self.assertEqual(
            len(falhas),
            0,
            "Arquivos com falha de sintaxe/compilacao em Python 3.6:\n{}".format(
                "\n".join(falhas)
            ),
        )

    def test_tokens_proibidos_arquivos_reais(self):
        """Verifica ausencia de tokens proibidos de Python >= 3.7 e recursos restritos."""
        arquivos = encontrar_arquivos_python(self.app_dir, self.web2py_root)
        todas_violacoes = []

        for caminho in arquivos:
            violacoes = verificar_tokens_proibidos_em_arquivo(caminho)
            todas_violacoes.extend(violacoes)

        msg_violacoes = "\n".join(
            ["{}:{}: {} -> '{}'".format(p, n, d, l) for p, n, d, l in todas_violacoes]
        )
        self.assertEqual(
            len(todas_violacoes),
            0,
            "Tokens proibidos encontrados nos arquivos .py:\n{}".format(msg_violacoes),
        )

    def test_ausencia_urls_externas_frontend(self):
        """Verifica que static/js/app/, static/css/ e views/ nao contem http:// ou https://."""
        diretorios_alvo = [
            os.path.join(self.app_dir, "static", "js", "app"),
            os.path.join(self.app_dir, "static", "css"),
            os.path.join(self.app_dir, "views"),
        ]

        arquivos_para_checar = []
        for d in diretorios_alvo:
            if os.path.isdir(d):
                for root, _, files in os.walk(d):
                    for f in files:
                        if f == ".gitkeep":
                            continue
                        arquivos_para_checar.append(os.path.join(root, f))

        todas_violacoes = []
        for caminho in arquivos_para_checar:
            violacoes = verificar_urls_externas_em_arquivo(caminho)
            todas_violacoes.extend(violacoes)

        msg = "\n".join(
            ["{}:{}: URL externa -> '{}'".format(p, n, l) for p, n, l in todas_violacoes]
        )
        self.assertEqual(
            len(todas_violacoes),
            0,
            "URLs externas encontradas em ativos frontend hermeticos:\n{}".format(msg),
        )

    def test_negativo_detector_tokens_proibidos(self):
        """Verifica se detector de tokens proibidos identifica casos sinteticos."""
        casos = [
            ("shell=True", "shell=True proibido"),
            ("x := 10", "walrus"),
            ("subprocess.getoutput('ls')", "getoutput"),
            ("os.system('id')", "os.system"),
            ("eval('1+1')", "eval"),
            ("XML(variavel)", "XML()"),
            ('<div x-html="msg"></div>', "x-html"),
        ]

        for linha, desc in casos:
            detectou = False
            for regex, d in _PADROES_COMPILADOS:
                if regex.search(linha):
                    detectou = True
                    break
            self.assertTrue(detectou, "Linha sintetica '{}' ({}) deveria ser detectada".format(linha, desc))

    def test_negativo_detector_urls_externas(self):
        """Verifica se regex de URLs externas detecta http e https."""
        self.assertTrue(_RE_URL_EXTERNA.search("https://cdn.jsdelivr.net/npm/bootstrap"))
        self.assertTrue(_RE_URL_EXTERNA.search("http://fonts.googleapis.com/css"))
        self.assertFalse(_RE_URL_EXTERNA.search("/static/js/app/bundle.js"))


if __name__ == "__main__":
    unittest.main()
