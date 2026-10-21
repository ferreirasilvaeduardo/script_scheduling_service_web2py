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
import tempfile
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
    (r"\bctypes\b", "modulo 'ctypes' proibido"),
    (r"\bmsvcrt\b", "modulo 'msvcrt' proibido"),
    # Web / Frontend (AGENTS §2.3, §3.4)
    (r"\bXML\s*\(", "escape 'XML()' inseguro com dados proibido"),
    (r"x-html", "diretiva 'x-html' proibida (use x-text)"),
]

_PADROES_COMPILADOS = [
    (re.compile(regex), desc) for regex, desc in PADROES_PROIBIDOS
]

_RE_URL_EXTERNA = re.compile(r"https?://", re.IGNORECASE)


def encontrar_arquivos_python(app_dir, web2py_root):
    """Localiza fontes Python de APP e bin/, incluindo o helper sem extensao."""
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

    helper = os.path.join(web2py_root, "bin", "sss-helper")
    if os.path.isfile(helper) and helper not in arquivos_py:
        arquivos_py.append(helper)

    return sorted(arquivos_py)


def verificar_primitivas_so(caminho, app_dir, web2py_root):
    """Rejeita primitivas POSIX fora da plataforma e da allowlist estrita do helper."""
    plataforma_dir = os.path.normpath(os.path.join(app_dir, "modules", "os_platform"))
    helper = os.path.normpath(os.path.join(web2py_root, "bin", "sss-helper"))
    caminho = os.path.normpath(caminho)
    if os.path.commonpath([caminho, plataforma_dir]) == plataforma_dir:
        return []
    if os.path.basename(caminho).startswith("test_"):
        return []

    if caminho == helper:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        source_lines = source.splitlines()
        violations = []

        class HelperVisitor(ast.NodeVisitor):
            def __init__(self):
                self.functions = []

            def _add(self, node):
                line_number = getattr(node, "lineno", 1)
                line = source_lines[line_number - 1].strip()
                violations.append((caminho, line_number, line))

            def visit_FunctionDef(self, node):
                self.functions.append(node.name)
                self.generic_visit(node)
                self.functions.pop()

            def visit_AsyncFunctionDef(self, node):
                self.functions.append(node.name)
                self.generic_visit(node)
                self.functions.pop()

            def visit_Import(self, node):
                if any(alias.name == "fcntl" for alias in node.names):
                    self._add(node)
                self.generic_visit(node)

            def visit_ImportFrom(self, node):
                if node.module == "fcntl" or node.module == "resource":
                    self._add(node)
                self.generic_visit(node)

            def visit_Attribute(self, node):
                if isinstance(node.value, ast.Name):
                    module = node.value.id
                    # Funcoes aninhadas contam como parte da funcao de topo que as define.
                    function = self.functions[0] if self.functions else None
                    if module == "os" and node.attr == "setsid":
                        self._add(node)
                    elif module == "os" and node.attr == "killpg" and function not in ("_term", "_kill"):
                        self._add(node)
                    elif module == "resource" and node.attr == "setrlimit" and function != "_run":
                        self._add(node)
                    elif module == "resource" and node.attr != "setrlimit":
                        self._add(node)
                    elif module == "sys" and node.attr == "platform":
                        self._add(node)
                self.generic_visit(node)

            def visit_Str(self, node):
                function = self.functions[0] if self.functions else None
                # /proc/<pid>/cwd so em _encerrar_ticket; a leitura de /proc/<pid>/stat (identidade do
                # lider, README §8.0) so em _identidade, usada por term/kill (AGENTS §3.2).
                if "/proc/" in node.s and function not in ("_encerrar_ticket", "_identidade"):
                    self._add(node)
                elif "pwdx" in node.s and function != "_encerrar_ticket":
                    self._add(node)

        HelperVisitor().visit(ast.parse(source, filename=caminho))
        return violations

    padroes = [
        re.compile(r"\bos\.killpg\s*\("),
        re.compile(r"\bos\.setsid\s*\("),
        re.compile(r"\bresource\b"),
        re.compile(r"\bfcntl\b"),
        re.compile(r"/proc/"),
        re.compile(r"\bpwdx\b"),
        re.compile(r"\bsys\.platform\b"),
    ]
    violacoes = []
    with open(caminho, "r", encoding="utf-8", errors="replace") as f:
        for num_linha, linha in enumerate(f, start=1):
            for padrao in padroes:
                if padrao.search(linha):
                    violacoes.append((caminho, num_linha, linha.strip()))
                    break
    return violacoes


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


def verificar_imports_driver_oracle(caminho, app_dir):
    """Verifica que apenas db_conn.py e probe_driver.py importam oracledb ou cx_Oracle (AGENTS §2.2)."""
    nome = os.path.basename(caminho)
    if nome in ("db_conn.py", "probe_driver.py") or nome.startswith("test_"):
        return []

    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            src = f.read()
        tree = ast.parse(src, filename=caminho)
    except Exception:
        return []

    violacoes = []
    lines = src.splitlines()

    class DriverImportVisitor(ast.NodeVisitor):
        def visit_Import(self, node):
            for alias in node.names:
                if alias.name in ("oracledb", "cx_Oracle"):
                    ln = getattr(node, "lineno", 1)
                    ltext = lines[ln - 1].strip() if ln <= len(lines) else ""
                    violacoes.append((caminho, ln, alias.name, ltext))
            self.generic_visit(node)

        def visit_ImportFrom(self, node):
            if node.module in ("oracledb", "cx_Oracle"):
                ln = getattr(node, "lineno", 1)
                ltext = lines[ln - 1].strip() if ln <= len(lines) else ""
                violacoes.append((caminho, ln, node.module, ltext))
            self.generic_visit(node)

    DriverImportVisitor().visit(tree)
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

    def test_primitivas_so_fora_da_plataforma(self):
        """Permite apenas a allowlist de primitivas POSIX do helper isolado."""
        arquivos = encontrar_arquivos_python(self.app_dir, self.web2py_root)
        violacoes = []
        for caminho in arquivos:
            violacoes.extend(verificar_primitivas_so(caminho, self.app_dir, self.web2py_root))

        mensagem = "\n".join(
            ["{}:{}: {}".format(p, n, linha) for p, n, linha in violacoes]
        )
        self.assertEqual(
            len(violacoes), 0,
            "Primitivas POSIX fora da camada permitida:\n{}".format(mensagem),
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

    def test_negativo_detector_primitivas_so(self):
        """Detecta primitivas POSIX fora da plataforma e limita a excecao ao helper."""
        with tempfile.TemporaryDirectory() as raiz:
            app_dir = os.path.join(raiz, "app")
            web2py_root = os.path.join(raiz, "web2py")
            caminho_ruim = os.path.join(app_dir, "modules", "outro", "bad_source.py")
            helper = os.path.join(web2py_root, "bin", "sss-helper")
            plataforma = os.path.join(app_dir, "modules", "os_platform", "posix.py")
            for caminho, conteudo in (
                (caminho_ruim, "os.killpg(1, 15)\nos.setsid()\nimport resource\nimport fcntl\nproc = '/proc/1/cwd'\nsubprocess.Popen(['pwdx', '1'])\nvalor = sys.platform\n"),
                (helper, "import os\nimport resource\nimport subprocess\ndef _run():\n    resource.setrlimit(1, (2, 3))\ndef _term():\n    os.killpg(1, 15)\ndef _kill():\n    os.killpg(1, 9)\ndef _encerrar_ticket():\n    proc = '/proc/1/cwd'\n    subprocess.Popen(['/usr/bin/pwdx', '1'])\n"),
                (plataforma, "os.killpg(1, 15)\n"),
            ):
                os.makedirs(os.path.dirname(caminho), exist_ok=True)
                with open(caminho, "w") as f:
                    f.write(conteudo)

            self.assertEqual(
                len(verificar_primitivas_so(caminho_ruim, app_dir, web2py_root)), 7
            )
            self.assertEqual(verificar_primitivas_so(helper, app_dir, web2py_root), [])
            helper_bad = "import os\nimport resource\nimport subprocess\ndef _run():\n    os.killpg(1, 15)\ndef _term():\n    resource.setrlimit(1, (2, 3))\ndef _encerrar_ticket():\n    pass\ndef _limpar():\n    proc = '/proc/1/cwd'\n    subprocess.Popen(['/usr/bin/pwdx', '1'])\n"
            with open(helper, "w") as f:
                f.write(helper_bad)
            self.assertEqual(
                len(verificar_primitivas_so(helper, app_dir, web2py_root)), 4,
                repr(verificar_primitivas_so(helper, app_dir, web2py_root)),
            )
            self.assertEqual(verificar_primitivas_so(plataforma, app_dir, web2py_root), [])

    def test_imports_driver_oracle_apenas_em_db_conn_e_sondar(self):
        """Garante que oracledb e cx_Oracle so sejam importados em db_conn.py, probe_driver.py e testes."""
        arquivos = encontrar_arquivos_python(self.app_dir, self.web2py_root)
        violacoes = []
        for caminho in arquivos:
            violacoes.extend(verificar_imports_driver_oracle(caminho, self.app_dir))

        mensagem = "\n".join(
            ["{}:{}: importou '{}' ({})".format(p, n, mod, linha) for p, n, mod, linha in violacoes]
        )
        self.assertEqual(
            len(violacoes),
            0,
            "Driver Oracle importado fora de db_conn.py e probe_driver.py:\n{}".format(mensagem),
        )

    def test_negativo_detector_imports_driver_oracle(self):
        """Verifica se detector de imports de oracledb e cx_Oracle identifica violacoes e respeita allowlist."""
        with tempfile.TemporaryDirectory() as raiz:
            ruim = os.path.join(raiz, "outro_modulo.py")
            with open(ruim, "w", encoding="utf-8") as f:
                f.write("import oracledb\nfrom cx_Oracle import connect\n")

            violacoes = verificar_imports_driver_oracle(ruim, raiz)
            self.assertEqual(len(violacoes), 2)
            self.assertEqual(violacoes[0][2], "oracledb")
            self.assertEqual(violacoes[1][2], "cx_Oracle")

            permitido1 = os.path.join(raiz, "db_conn.py")
            with open(permitido1, "w", encoding="utf-8") as f:
                f.write("import oracledb\n")
            self.assertEqual(verificar_imports_driver_oracle(permitido1, raiz), [])

            permitido2 = os.path.join(raiz, "probe_driver.py")
            with open(permitido2, "w", encoding="utf-8") as f:
                f.write("import cx_Oracle\n")
            self.assertEqual(verificar_imports_driver_oracle(permitido2, raiz), [])

            permitido3 = os.path.join(raiz, "test_algo.py")
            with open(permitido3, "w", encoding="utf-8") as f:
                f.write("import oracledb\n")
            self.assertEqual(verificar_imports_driver_oracle(permitido3, raiz), [])


if __name__ == "__main__":
    unittest.main()
