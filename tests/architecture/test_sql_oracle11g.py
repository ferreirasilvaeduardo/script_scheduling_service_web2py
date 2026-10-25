# -*- coding: utf-8 -*-
"""Varredura estatica de conformidade SQL Oracle 11gR2 (F7.3, AGENTS §4.3).

Verifica que todos os arquivos em modules/repo_oracle/ e scripts/init_db.py:
1. Nao utilizam sintaxe Oracle 12c+ (OFFSET, FETCH FIRST, IDENTITY, JSON_*, APPLY, etc.);
2. Nao utilizam SELECT *;
3. Todo FOR UPDATE utiliza WAIT n (n <= 5) ou SKIP LOCKED.
"""
import os
import re
import unittest

from tests.support import _testenv  # noqa: F401

_PATTERNS_12C = [
    # Sintaxe 12c "OFFSET <n|:bind> ROW[S]"; a palavra solta e o parametro offset do contrato
    # RepoTickets.log_ler, nao SQL.
    (re.compile(r"\bOFFSET\s+(\d+|:\w+)\s+ROWS?\b", re.IGNORECASE), "OFFSET (paginacao 12c+)"),
    (re.compile(r"\bFETCH\s+(FIRST|NEXT)\b", re.IGNORECASE), "FETCH FIRST/NEXT (12c+)"),
    (re.compile(r"\bGENERATED\s+ALWAYS\s+AS\s+IDENTITY\b", re.IGNORECASE), "IDENTITY (12c+)"),
    (re.compile(r"\bDEFAULT\s+[A-Za-z0-9_.]+\.NEXTVAL\b", re.IGNORECASE), "DEFAULT seq.NEXTVAL (12c+)"),
    (re.compile(r"\bJSON_(VALUE|TABLE|QUERY|ARRAY|OBJECT)\b", re.IGNORECASE), "JSON_* nativo (12c+)"),
    (re.compile(r"\bIS\s+JSON\b", re.IGNORECASE), "IS JSON (12c+)"),
    (re.compile(r"\b(CROSS|OUTER)\s+APPLY\b", re.IGNORECASE), "APPLY (12c+)"),
    (re.compile(r"\bLATERAL\b", re.IGNORECASE), "LATERAL (12c+)"),
    (re.compile(r"\bVARCHAR2\s*\(\s*32767", re.IGNORECASE), "VARCHAR2(32767) (12c+)"),
    (re.compile(r"\bON\s+OVERFLOW\b", re.IGNORECASE), "LISTAGG ON OVERFLOW (12c+)"),
    (re.compile(r"\bWITH\s+FUNCTION\b", re.IGNORECASE), "WITH FUNCTION (12c+)"),
]

_RE_SELECT_STAR = re.compile(r"\bSELECT\s+\*\s+FROM\b", re.IGNORECASE)
_RE_FOR_UPDATE = re.compile(r"\bFOR\s+UPDATE\b.*?(?:;|\"|\')", re.IGNORECASE | re.DOTALL)


class TestSqlOracle11g(unittest.TestCase):
    """Garante conformidade do SQL com a especificacao Oracle 11gR2 do AGENTS §4.3."""

    def _get_sql_files(self):
        base_dir = _testenv.APP_DIR
        repo_oracle_dir = os.path.join(base_dir, "modules", "repo_oracle")
        file_paths = []
        for root, _, files in os.walk(repo_oracle_dir):
            for f in files:
                if f.endswith(".py") and f != "__init__.py":
                    file_paths.append(os.path.join(root, f))

        init_db = os.path.join(base_dir, "scripts", "init_db.py")
        if os.path.isfile(init_db):
            file_paths.append(init_db)
        return file_paths

    def test_padroes_12c_detectam_a_sintaxe_proibida(self):
        """Regressao: a regra de OFFSET pega a paginacao 12c e ignora o parametro offset do contrato."""
        def acusa(text):
            return [d for p, d in _PATTERNS_12C if p.search(text)]
        self.assertTrue(acusa("SELECT id FROM t ORDER BY id OFFSET 10 ROWS FETCH NEXT 5 ROWS ONLY"))
        self.assertTrue(acusa("SELECT id FROM t OFFSET :start_ts ROWS"))
        self.assertTrue(acusa("select id from t offset 1 row"))
        self.assertEqual(acusa("def log_ler(self, id, offset, max_chars):\n    off = int(offset)"), [])

    def test_ausencia_sintaxe_12c(self):
        """Varre os arquivos do repositorio Oracle garantindo ausencia de recursos 12c+."""
        files = self._get_sql_files()
        self.assertTrue(len(files) > 0, "Nenhum arquivo encontrado em modules/repo_oracle/")

        violations = []
        for path in files:
            with open(path, "r", encoding="utf-8") as fp:
                content = fp.read()

            for default, desc in _PATTERNS_12C:
                m = default.search(content)
                if m:
                    violations.append("%s: sintaxe proibida encontrada (%s)" % (os.path.basename(path), desc))

        self.assertEqual(violations, [], "Violacoes de sintaxe 12c+ encontradas:\n" + "\n".join(violations))

    def test_ausencia_select_star(self):
        """Proibe SELECT * direto da tabela em code de aplicacao (exceto subquery de paginacao)."""
        files = self._get_sql_files()
        violations = []
        for path in files:
            with open(path, "r", encoding="utf-8") as fp:
                rows = fp.readlines()

            for i, line in enumerate(rows, 1):
                # Permite SELECT * FROM ( subquery de paginacao
                if "SELECT * FROM" in line.upper() and "(" not in line and "SUBQUERY" not in line.upper():
                    violations.append("%s:%d: SELECT * proibido (deve especificar colunas)" % (os.path.basename(path), i))

        self.assertEqual(violations, [], "SELECT * proibido encontrado:\n" + "\n".join(violations))

    def test_for_update_com_wait_n_ou_skip_locked(self):
        """Garante que todo FOR UPDATE use WAIT n (n <= 5) ou SKIP LOCKED (AGENTS §4.10)."""
        files = self._get_sql_files()
        violations = []
        for path in files:
            with open(path, "r", encoding="utf-8") as fp:
                content = fp.read()

            # Encontra todos os blocos contendo FOR UPDATE
            for m in re.finditer(r"\bFOR\s+UPDATE\b([^\";\n]*)", content, re.IGNORECASE):
                clause = m.group(0).upper()
                if "SKIP LOCKED" in clause:
                    continue
                m_wait = re.search(r"\bWAIT\s+(\d+)\b", clause)
                if not m_wait:
                    violations.append("%s: FOR UPDATE sem WAIT ou SKIP LOCKED: '%s'" % (os.path.basename(path), clause))
                else:
                    n = int(m_wait.group(1))
                    if n > 5:
                        violations.append("%s: FOR UPDATE WAIT %d excede o maximo de 5s" % (os.path.basename(path), n))

        self.assertEqual(violations, [], "Violacoes de FOR UPDATE encontradas:\n" + "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
