# -*- coding: utf-8 -*-
"""Testes de conformidade e compatibilidade com Python 3.6 estrito.

Verifica conformidade com AGENTS.md §2.1, §2.3, §3.2 e §7.4:
1. Compila todos os arquivos .py de APP (exceto dev/scripts/) e bin/ sob Python 3.6;
2. Procura tokens proibidos por regex (recursos >= 3.7, chamadas inseguras de processo, XML e diretiva do Alpine);
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
TOKEN_EXCEPTION_FILES = {
    "test_py36_compat.py",
}

# Excecao por caminho (relativo a aplicacao) e so para o token indicado: o motor de templates e o
# unico lugar com exec, so para o codigo gerado de arquivos de views/ (CR-021, D2).
TOKEN_EXCEPTIONS_BY_PATH = {
    "modules/web/template.py": {"uso de 'exec()' proibido"},
}

# Tokens e chamadas proibidos em Python 3.6 / SSS (AGENTS §2.1, §3.2, §3.4)
FORBIDDEN_PATTERNS = [
    # Versoes de correcao da 3.6 (o minimo e o 3.6.0, AGENTS §2.1)
    (r"\bNoReturn\b", "'typing.NoReturn' proibido (Python >= 3.6.2)"),
    (r"\bAsyncGenerator\b", "'typing.AsyncGenerator' proibido (Python >= 3.6.1)"),
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
    # HTML montado em Python sem Alpine (CR-021b2); as views sao conferidas por test_frontend_components.
    (r"(?<![\w-])x-[a-z]+(?:[:.][\w.-]+)?=\"", "diretiva do Alpine proibida (CR-021: texto so por textContent)"),
]

_COMPILED_PATTERNS = [
    (re.compile(regex), desc) for regex, desc in FORBIDDEN_PATTERNS
]

_RE_URL_EXTERNA = re.compile(r"https?://", re.IGNORECASE)


def find_python_files(app_dir, repo_root):
    """Localiza fontes Python de APP e bin/, incluindo o helper sem extensao."""
    files_py = []
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
                files_py.append(os.path.join(root, f))

    # Varre diretorios bin/
    for bin_cand in [os.path.join(app_dir, "bin"), os.path.join(repo_root, "bin")]:
        if os.path.isdir(bin_cand):
            for root, dirs, files in os.walk(bin_cand):
                if "__pycache__" in dirs:
                    dirs.remove("__pycache__")
                for f in files:
                    if f.endswith(".py"):
                        p = os.path.join(root, f)
                        if p not in files_py:
                            files_py.append(p)

    helper = os.path.join(repo_root, "bin", "sss-helper")
    if os.path.isfile(helper) and helper not in files_py:
        files_py.append(helper)

    return sorted(files_py)


def check_os_primitives(path, app_dir, repo_root):
    """Rejeita primitivas POSIX fora da plataforma e da allowlist estrita do helper."""
    platform_dir = os.path.normpath(os.path.join(app_dir, "modules", "os_platform"))
    helper = os.path.normpath(os.path.join(repo_root, "bin", "sss-helper"))
    path = os.path.normpath(path)
    if os.path.commonpath([path, platform_dir]) == platform_dir:
        return []
    if os.path.basename(path).startswith("test_"):
        return []

    if path == helper:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        source_lines = source.splitlines()
        violations = []

        class HelperVisitor(ast.NodeVisitor):
            def __init__(self):
                self.functions = []

            def _add(self, node):
                line_number = getattr(node, "lineno", 1)
                line = source_lines[line_number - 1].strip()
                violations.append((path, line_number, line))

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
                # /proc/<pid>/cwd so em _stop_ticket; a leitura de /proc/<pid>/stat (identidade do
                # lider, README §8.0) so em _identity, usada por term/kill (AGENTS §3.2).
                if "/proc/" in node.s and function not in ("_stop_ticket", "_identity"):
                    self._add(node)
                elif "pwdx" in node.s and function != "_stop_ticket":
                    self._add(node)

        HelperVisitor().visit(ast.parse(source, filename=path))
        return violations

    patterns = [
        re.compile(r"\bos\.killpg\s*\("),
        re.compile(r"\bos\.setsid\s*\("),
        re.compile(r"\bresource\b"),
        re.compile(r"\bfcntl\b"),
        re.compile(r"/proc/"),
        re.compile(r"\bpwdx\b"),
        re.compile(r"\bsys\.platform\b"),
    ]
    found_violations = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for num_line, src_line in enumerate(f, start=1):
            for default in patterns:
                if default.search(src_line):
                    found_violations.append((path, num_line, src_line.strip()))
                    break
    return found_violations


def compile_py_file(path):
    """Compila codigo fonte garantindo compatibilidade com Python 3.6."""
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    # Quando interpretador >= 3.8, valida AST com feature_version 3.6
    if sys.version_info >= (3, 8):
        ast.parse(src, filename=path, feature_version=(3, 6))
    else:
        compile(src, path, "exec")


def check_forbidden_tokens_in_file(path):
    """Procura tokens proibidos em um arquivo fonte, retornando lista de violacoes."""
    name_base = os.path.basename(path)
    if name_base in TOKEN_EXCEPTION_FILES:
        return []
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    relative = os.path.relpath(os.path.abspath(path), app_dir).replace(os.sep, "/")
    allowed = TOKEN_EXCEPTIONS_BY_PATH.get(relative, set())

    violations = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for num_line, line in enumerate(f, start=1):
            for regex, desc in _COMPILED_PATTERNS:
                if regex.search(line) and desc not in allowed:
                    violations.append((path, num_line, desc, line.strip()))
    return violations


def check_external_urls_in_file(path):
    """Procura URLs http:// e https:// em arquivos estaticos e views."""
    violations = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for num_line, line in enumerate(f, start=1):
            if _RE_URL_EXTERNA.search(line):
                violations.append((path, num_line, line.strip()))
    return violations


def check_oracle_driver_imports(path, app_dir):
    """Verifica que apenas db_conn.py e probe_driver.py importam oracledb ou cx_Oracle (AGENTS §2.2)."""
    name = os.path.basename(path)
    if name in ("db_conn.py", "probe_driver.py") or name.startswith("test_"):
        return []

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            src = f.read()
        tree = ast.parse(src, filename=path)
    except Exception:
        return []

    violations = []
    lines = src.splitlines()

    class DriverImportVisitor(ast.NodeVisitor):
        def visit_Import(self, node):
            for alias in node.names:
                if alias.name in ("oracledb", "cx_Oracle"):
                    ln = getattr(node, "lineno", 1)
                    ltext = lines[ln - 1].strip() if ln <= len(lines) else ""
                    violations.append((path, ln, alias.name, ltext))
            self.generic_visit(node)

        def visit_ImportFrom(self, node):
            if node.module in ("oracledb", "cx_Oracle"):
                ln = getattr(node, "lineno", 1)
                ltext = lines[ln - 1].strip() if ln <= len(lines) else ""
                violations.append((path, ln, node.module, ltext))
            self.generic_visit(node)

    DriverImportVisitor().visit(tree)
    return violations


class TestPy36Compat(unittest.TestCase):
    """Testes automatizados de compatibilidade com Python 3.6 e hermeticidade."""

    def setUp(self):
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        self.app_dir = os.path.dirname(scripts_dir)
        self.repo_root = os.path.dirname(os.path.dirname(self.app_dir))

    def test_compilacao_python_36(self):
        """Compila todos os .py de APP e bin/ sob gramatica do Python 3.6."""
        files = find_python_files(self.app_dir, self.repo_root)
        self.assertGreater(len(files), 0, "Deve encontrar arquivos .py para testar")

        failures = []
        for path in files:
            try:
                compile_py_file(path)
            except Exception as e:
                failures.append("{}: {}".format(path, str(e)))

        self.assertEqual(
            len(failures),
            0,
            "Arquivos com falha de sintaxe/compilacao em Python 3.6:\n{}".format(
                "\n".join(failures)
            ),
        )

    def test_primitivas_so_fora_da_plataforma(self):
        """Permite apenas a allowlist de primitivas POSIX do helper isolado."""
        files = find_python_files(self.app_dir, self.repo_root)
        violations = []
        for path in files:
            violations.extend(check_os_primitives(path, self.app_dir, self.repo_root))

        message = "\n".join(
            ["{}:{}: {}".format(p, n, line) for p, n, line in violations]
        )
        self.assertEqual(
            len(violations), 0,
            "Primitivas POSIX fora da camada permitida:\n{}".format(message),
        )

    def test_tokens_proibidos_arquivos_reais(self):
        """Verifica ausencia de tokens proibidos de Python >= 3.7 e recursos restritos."""
        files = find_python_files(self.app_dir, self.repo_root)
        all_violations = []

        for path in files:
            violations = check_forbidden_tokens_in_file(path)
            all_violations.extend(violations)

        msg_violations = "\n".join(
            ["{}:{}: {} -> '{}'".format(p, n, d, l) for p, n, d, l in all_violations]
        )
        self.assertEqual(
            len(all_violations),
            0,
            "Tokens proibidos encontrados nos arquivos .py:\n{}".format(msg_violations),
        )

    def test_ausencia_urls_externas_frontend(self):
        """Verifica que static/js/app/, static/css/ e views/ nao contem http:// ou https://."""
        directories_target = [
            os.path.join(self.app_dir, "static", "js", "app"),
            os.path.join(self.app_dir, "static", "css"),
            os.path.join(self.app_dir, "views"),
        ]

        files_for_check = []
        for d in directories_target:
            if os.path.isdir(d):
                for root, _, files in os.walk(d):
                    for f in files:
                        if f == ".gitkeep":
                            continue
                        files_for_check.append(os.path.join(root, f))

        all_violations = []
        for path in files_for_check:
            violations = check_external_urls_in_file(path)
            all_violations.extend(violations)

        msg = "\n".join(
            ["{}:{}: URL externa -> '{}'".format(p, n, l) for p, n, l in all_violations]
        )
        self.assertEqual(
            len(all_violations),
            0,
            "URLs externas encontradas em ativos frontend hermeticos:\n{}".format(msg),
        )

    def test_exec_and_compile_only_in_template_engine(self):
        """CR-021 D2: exec() so no modules/web/template.py; compile() tambem, salvo nos testes.

        Teste pode usar compile() so para conferir sintaxe (ex.: test_sss_helper), sem executar.
        """
        found = []
        for path in find_python_files(self.app_dir, self.repo_root):
            if os.path.basename(path) in TOKEN_EXCEPTION_FILES:
                continue
            relative = os.path.relpath(path, self.app_dir).replace(os.sep, "/")
            is_test = relative.startswith("scripts/test_")
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                name = getattr(getattr(node, "func", None), "id", None) if isinstance(node, ast.Call) else None
                if name == "exec" or (name == "compile" and not is_test):
                    found.append((relative, name))
        self.assertEqual(sorted(found), [("modules/web/template.py", "compile"),
                                         ("modules/web/template.py", "exec")])

    def test_negativo_detector_tokens_proibidos(self):
        """Verifica se detector de tokens proibidos identifica casos sinteticos."""
        cases = [
            ("shell=True", "shell=True proibido"),
            ("x := 10", "walrus"),
            ("subprocess.getoutput('ls')", "getoutput"),
            ("os.system('id')", "os.system"),
            ("eval('1+1')", "eval"),
            ("XML(variavel)", "XML()"),
            ("from typing import NoReturn", "NoReturn"),
            ('<div x-html="msg"></div>', "x-html"),
            ('<span x-text="label"></span>', "x-text"),
            ('<div x-on:click.prevent="go"></div>', "x-on"),
        ]

        for line, desc in cases:
            detected = False
            for regex, d in _COMPILED_PATTERNS:
                if regex.search(line):
                    detected = True
                    break
            self.assertTrue(detected, "Linha sintetica '{}' ({}) deveria ser detectada".format(line, desc))

    def test_negativo_detector_urls_externas(self):
        """Verifica se regex de URLs externas detecta http e https."""
        self.assertTrue(_RE_URL_EXTERNA.search("https://cdn.jsdelivr.net/npm/bootstrap"))
        self.assertTrue(_RE_URL_EXTERNA.search("http://fonts.googleapis.com/css"))
        self.assertFalse(_RE_URL_EXTERNA.search("/static/js/app/bundle.js"))

    def test_negativo_detector_primitivas_so(self):
        """Detecta primitivas POSIX fora da plataforma e limita a excecao ao helper."""
        with tempfile.TemporaryDirectory() as root:
            app_dir = os.path.join(root, "app")
            repo_root = os.path.join(root, "web2py")
            path_bad = os.path.join(app_dir, "modules", "outro", "bad_source.py")
            helper = os.path.join(repo_root, "bin", "sss-helper")
            platform_value = os.path.join(app_dir, "modules", "os_platform", "posix.py")
            for path, content in (
                (path_bad, "os.killpg(1, 15)\nos.setsid()\nimport resource\nimport fcntl\nproc = '/proc/1/cwd'\nsubprocess.Popen(['pwdx', '1'])\nvalor = sys.platform\n"),
                (helper, "import os\nimport resource\nimport subprocess\ndef _run():\n    resource.setrlimit(1, (2, 3))\ndef _term():\n    os.killpg(1, 15)\ndef _kill():\n    os.killpg(1, 9)\ndef _stop_ticket():\n    proc = '/proc/1/cwd'\n    subprocess.Popen(['/usr/bin/pwdx', '1'])\n"),
                (platform_value, "os.killpg(1, 15)\n"),
            ):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    f.write(content)

            self.assertEqual(
                len(check_os_primitives(path_bad, app_dir, repo_root)), 7
            )
            self.assertEqual(check_os_primitives(helper, app_dir, repo_root), [])
            helper_bad = "import os\nimport resource\nimport subprocess\ndef _run():\n    os.killpg(1, 15)\ndef _term():\n    resource.setrlimit(1, (2, 3))\ndef _stop_ticket():\n    pass\ndef _clean():\n    proc = '/proc/1/cwd'\n    subprocess.Popen(['/usr/bin/pwdx', '1'])\n"
            with open(helper, "w") as f:
                f.write(helper_bad)
            self.assertEqual(
                len(check_os_primitives(helper, app_dir, repo_root)), 4,
                repr(check_os_primitives(helper, app_dir, repo_root)),
            )
            self.assertEqual(check_os_primitives(platform_value, app_dir, repo_root), [])

    def test_imports_driver_oracle_apenas_em_db_conn_e_sondar(self):
        """Garante que oracledb e cx_Oracle so sejam importados em db_conn.py, probe_driver.py e testes."""
        files = find_python_files(self.app_dir, self.repo_root)
        violations = []
        for path in files:
            violations.extend(check_oracle_driver_imports(path, self.app_dir))

        message = "\n".join(
            ["{}:{}: importou '{}' ({})".format(p, n, mod, line) for p, n, mod, line in violations]
        )
        self.assertEqual(
            len(violations),
            0,
            "Driver Oracle importado fora de db_conn.py e probe_driver.py:\n{}".format(message),
        )

    def test_negativo_detector_imports_driver_oracle(self):
        """Verifica se detector de imports de oracledb e cx_Oracle identifica violacoes e respeita allowlist."""
        with tempfile.TemporaryDirectory() as root:
            bad = os.path.join(root, "outro_modulo.py")
            with open(bad, "w", encoding="utf-8") as f:
                f.write("import oracledb\nfrom cx_Oracle import connect\n")

            violations = check_oracle_driver_imports(bad, root)
            self.assertEqual(len(violations), 2)
            self.assertEqual(violations[0][2], "oracledb")
            self.assertEqual(violations[1][2], "cx_Oracle")

            allowed1 = os.path.join(root, "db_conn.py")
            with open(allowed1, "w", encoding="utf-8") as f:
                f.write("import oracledb\n")
            self.assertEqual(check_oracle_driver_imports(allowed1, root), [])

            allowed2 = os.path.join(root, "probe_driver.py")
            with open(allowed2, "w", encoding="utf-8") as f:
                f.write("import cx_Oracle\n")
            self.assertEqual(check_oracle_driver_imports(allowed2, root), [])

            allowed3 = os.path.join(root, "test_algo.py")
            with open(allowed3, "w", encoding="utf-8") as f:
                f.write("import oracledb\n")
            self.assertEqual(check_oracle_driver_imports(allowed3, root), [])


if __name__ == "__main__":
    unittest.main()
