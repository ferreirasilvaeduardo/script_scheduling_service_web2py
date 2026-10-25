# -*- coding: utf-8 -*-
"""Testes unitarios para ddl_builder.py, sql_ident.normalize_expression e scripts/init_db.py (F7.1)

Parte que precisa do Oracle real (SSS_TEST_ORACLE=1), separada de tests.unit.persistence.test_ddl_builder (CR-022b1)."""
import os
import unittest
from tests.support import _testenv  # noqa: F401


class TestInitDbReal(unittest.TestCase):
    """Teste com conexao Oracle real caso SSS_TEST_DSN e SSS_TEST_OWNER estejam definidos."""

    def test_execucao_real_condicionada(self):
        dsn = os.environ.get("SSS_TEST_DSN")
        owner = os.environ.get("SSS_TEST_OWNER")
        disposable = os.environ.get("SSS_TEST_SCHEMA_DISPOSABLE")
        if not dsn or not owner or disposable != "1":
            self.skipTest("Schema descartavel real nao configurado (SSS_TEST_DSN/OWNER/DISPOSABLE); marcado como NAO TESTADO")


if __name__ == "__main__":
    unittest.main()
