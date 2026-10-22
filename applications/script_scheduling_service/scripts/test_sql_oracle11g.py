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

import _testenv  # noqa: F401

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
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        repo_oracle_dir = os.path.join(base_dir, "modules", "repo_oracle")
        arquivos = []
        for raiz, _, files in os.walk(repo_oracle_dir):
            for f in files:
                if f.endswith(".py") and f != "__init__.py":
                    arquivos.append(os.path.join(raiz, f))

        init_db = os.path.join(base_dir, "scripts", "init_db.py")
        if os.path.isfile(init_db):
            arquivos.append(init_db)
        return arquivos

    def test_padroes_12c_detectam_a_sintaxe_proibida(self):
        """Regressao: a regra de OFFSET pega a paginacao 12c e ignora o parametro offset do contrato."""
        def acusa(texto):
            return [d for p, d in _PATTERNS_12C if p.search(texto)]
        self.assertTrue(acusa("SELECT id FROM t ORDER BY id OFFSET 10 ROWS FETCH NEXT 5 ROWS ONLY"))
        self.assertTrue(acusa("SELECT id FROM t OFFSET :inicio ROWS"))
        self.assertTrue(acusa("select id from t offset 1 row"))
        self.assertEqual(acusa("def log_ler(self, id, offset, max_chars):\n    off = int(offset)"), [])

    def test_ausencia_sintaxe_12c(self):
        """Varre os arquivos do repositorio Oracle garantindo ausencia de recursos 12c+."""
        arquivos = self._get_sql_files()
        self.assertTrue(len(arquivos) > 0, "Nenhum arquivo encontrado em modules/repo_oracle/")

        violacoes = []
        for caminho in arquivos:
            with open(caminho, "r", encoding="utf-8") as fp:
                conteudo = fp.read()

            for padrao, desc in _PATTERNS_12C:
                m = padrao.search(conteudo)
                if m:
                    violacoes.append("%s: sintaxe proibida encontrada (%s)" % (os.path.basename(caminho), desc))

        self.assertEqual(violacoes, [], "Violacoes de sintaxe 12c+ encontradas:\n" + "\n".join(violacoes))

    def test_ausencia_select_star(self):
        """Proibe SELECT * direto da tabela em code de aplicacao (exceto subquery de paginacao)."""
        arquivos = self._get_sql_files()
        violacoes = []
        for caminho in arquivos:
            with open(caminho, "r", encoding="utf-8") as fp:
                linhas = fp.readlines()

            for i, linha in enumerate(linhas, 1):
                # Permite SELECT * FROM ( subquery de paginacao
                if "SELECT * FROM" in linha.upper() and "(" not in linha and "SUBQUERY" not in linha.upper():
                    violacoes.append("%s:%d: SELECT * proibido (deve especificar colunas)" % (os.path.basename(caminho), i))

        self.assertEqual(violacoes, [], "SELECT * proibido encontrado:\n" + "\n".join(violacoes))

    def test_for_update_com_wait_n_ou_skip_locked(self):
        """Garante que todo FOR UPDATE use WAIT n (n <= 5) ou SKIP LOCKED (AGENTS §4.10)."""
        arquivos = self._get_sql_files()
        violacoes = []
        for caminho in arquivos:
            with open(caminho, "r", encoding="utf-8") as fp:
                conteudo = fp.read()

            # Encontra todos os blocos contendo FOR UPDATE
            for m in re.finditer(r"\bFOR\s+UPDATE\b([^\";\n]*)", conteudo, re.IGNORECASE):
                clausula = m.group(0).upper()
                if "SKIP LOCKED" in clausula:
                    continue
                m_wait = re.search(r"\bWAIT\s+(\d+)\b", clausula)
                if not m_wait:
                    violacoes.append("%s: FOR UPDATE sem WAIT ou SKIP LOCKED: '%s'" % (os.path.basename(caminho), clausula))
                else:
                    n = int(m_wait.group(1))
                    if n > 5:
                        violacoes.append("%s: FOR UPDATE WAIT %d excede o maximo de 5s" % (os.path.basename(caminho), n))

        self.assertEqual(violacoes, [], "Violacoes de FOR UPDATE encontradas:\n" + "\n".join(violacoes))


if __name__ == "__main__":
    unittest.main()
