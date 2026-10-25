# -*- coding: utf-8 -*-
"""Bateria de testes de conformidade para contratos de repositorio e backend FAKE

Parte que precisa do Oracle real (SSS_TEST_ORACLE=1), separada de tests.unit.persistence.test_repo_contract (CR-022b1)."""
import os
import unittest
from tests.support import _testenv  # noqa: F401
from tests.unit.persistence.test_repo_contract import BaseLastAdminTest, BaseRepoContractTest, _OracleContract  # noqa: F401


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestRepoContractOracle(_OracleContract, unittest.TestCase, BaseRepoContractTest):
    """Executa a mesma bateria contra o Oracle do config.ini, com dados proprios de cada teste."""


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestLastAdminOracle(_OracleContract, unittest.TestCase, BaseLastAdminTest):
    """Protecao do ultimo administrador no Oracle: so com owner descartavel (o teste e dono do banco)."""

    @classmethod
    def setUpClass(cls):
        super(TestLastAdminOracle, cls).setUpClass()
        from tests.support import _oracle_test_support
        if _oracle_test_support.schema_mode() != _oracle_test_support.DISPOSABLE_MODE:
            raise unittest.SkipTest("Owner compartilhado: ha administradores reais; a protecao do ultimo admin "
                                    "so e exercida no FAKE e com owner SSS_TEST_* (README §2.5)")


if __name__ == "__main__":
    unittest.main()
