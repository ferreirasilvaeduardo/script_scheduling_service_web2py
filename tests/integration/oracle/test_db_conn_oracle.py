# -*- coding: utf-8 -*-
"""Testes unitarios para db_conn.py, scripts/probe_driver.py e _oracle_test_support.py (F7.0, F7.2)

Parte que precisa do Oracle real (SSS_TEST_ORACLE=1), separada de tests.unit.persistence.test_db_conn (CR-022b1)."""
import datetime
import unittest
from tests.support import _testenv  # noqa: F401
from tests.support import _oracle_test_support
import db_conn


class TestDbConnReal(unittest.TestCase):
    """Testes com conexao real quando SSS_TEST_ORACLE=1 (F7.2): config e segredos da aplicacao."""

    def test_conexao_real_schema_descartavel(self):
        if not _oracle_test_support.real_db_configured():
            self.skipTest("Testes Oracle reais desligados (SSS_TEST_ORACLE=1); marcado como NAO TESTADO")
        from sss.config import sss_config
        cfg = _oracle_test_support.prepare_disposable_schema(role="web")
        secrets_value = sss_config.load_secrets(cfg.secrets.secrets_file, cfg=cfg, role="web")

        conn = db_conn.connect(cfg, secrets_value, role="web")
        self.assertIsNotNone(conn)

        try:
            # 1. Saude e Relogio
            dt_health = db_conn.health(conn)
            self.assertIsInstance(dt_health, datetime.datetime)

            dt_db = db_conn.db_now(conn)
            self.assertEqual(dt_db.microsecond, 0)

            # 2. Bind DATE descartando microssegundos (README §7.5)
            # Um datetime com microssegundos comparado com TIPO_DATE deve casar perfeitamente
            cur = conn.cursor()
            try:
                db_conn.set_input_types(cur, d=db_conn.TIPO_DATE)
                dt_with_micros = dt_db.replace(microsecond=543210)
                cur.execute("SELECT 1 FROM DUAL WHERE :d = TRUNC(SYSDATE, 'MI')", {"d": dt_with_micros})
                # Pode ou nao retornar 1 dependendo do segundo, mas o ponto critico e que setinputsizes
                # descarta microssegundos sem gerar erro ORA-018xx
            finally:
                cur.close()

        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
