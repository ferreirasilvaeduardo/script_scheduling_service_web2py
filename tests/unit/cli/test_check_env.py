# -*- coding: utf-8 -*-
"""scripts/check_env.py: sondagem do driver com os segredos do papel do processo (CR-031)."""
import io
import os
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests.support import _testenv  # noqa: F401
from sss.cli import check_env
from sss.config import sss_config
from sss.persistence import db_conn


def _cfg(role):
    return types.SimpleNamespace(app=types.SimpleNamespace(role=role),
                                 oracle=types.SimpleNamespace(driver_mode="thick"))


class TestCheckEnvDriver(unittest.TestCase):

    def _run(self, role, probe):
        out = io.StringIO()
        secrets = mock.Mock(return_value=object())
        with mock.patch.dict(os.environ, {"SSS_TEST_ORACLE": "1"}), \
                mock.patch.object(sss_config, "get_config", return_value=_cfg(role)), \
                mock.patch.object(sss_config, "get_secrets", secrets), \
                mock.patch.object(db_conn, "select_driver", probe), redirect_stdout(out):
            try:
                check_env.main(["--config", "config-de-teste.ini"])
            except SystemExit:
                pass
        return secrets, out.getvalue()

    def test_agente_usa_os_segredos_do_agente(self):
        sel = types.SimpleNamespace(candidate="thick", server_version="19", driver_version="1",
                                    client_version="19")
        secrets, text = self._run("agent", mock.Mock(return_value=sel))
        secrets.assert_called_once_with(role="agent")
        self.assertIn("modo=thick", text)
        secrets, _text = self._run("web", mock.Mock(return_value=sel))
        secrets.assert_called_once_with(role="web")

    def test_sondagem_que_falha_e_falha(self):
        _secrets, text = self._run("agent", mock.Mock(side_effect=RuntimeError("sem banco")))
        line = [r for r in text.splitlines() if "Driver Oracle" in r][0]
        self.assertIn("FALHA", line)
        self.assertIn("sondagem falhou: sem banco", line)


if __name__ == "__main__":
    unittest.main()
