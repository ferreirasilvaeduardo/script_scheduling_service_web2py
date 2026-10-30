# -*- coding: utf-8 -*-
"""scripts/check_env.py: sondagem do driver com os segredos do papel do processo (CR-031),
sempre (CR-033, D6)."""
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
from sss.platform import os_platform


def _cfg(role, dsn="servidor:1521/servico"):
    oracle = types.SimpleNamespace(driver_mode="thick", dsn=dsn, call_timeout_ms=30000)
    return types.SimpleNamespace(app=types.SimpleNamespace(role=role), oracle=oracle,
                                 agent=types.SimpleNamespace(child_locale="C.UTF-8"))


class TestCheckEnvDriver(unittest.TestCase):

    def _run(self, role, probe, dsn="servidor:1521/servico", locale="C.UTF-8",
             interpreters=(("python", "/usr/bin/python", "3.12.3"),
                           ("python3", "/usr/bin/python3", "3.12.3"))):
        out = io.StringIO()
        secrets = mock.Mock(return_value=object())
        # CR-033 (D6): a sondagem nao depende mais do SSS_TEST_ORACLE (a variavel dos testes)
        env = dict((k, v) for k, v in os.environ.items() if k != "SSS_TEST_ORACLE")
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sss_config, "config_path", return_value="config-de-teste.ini"), \
                mock.patch.object(sss_config, "get_config", return_value=_cfg(role, dsn)), \
                mock.patch.object(sss_config, "get_secrets", secrets), \
                mock.patch.object(db_conn, "select_driver", probe), redirect_stdout(out), \
                mock.patch.object(os_platform, "pick_child_locale", return_value=locale), \
                mock.patch.object(os_platform, "interpreter_versions",
                                  return_value=list(interpreters)):
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

    def test_orcamento_da_conexao(self):
        # README §2.3 (CR-008, R-17): acima do call_timeout_s, AVISO com CONEXAO_ACIMA_DO_PRAZO,
        # sem reprovar
        sel = types.SimpleNamespace(candidate="thick", server_version="19", driver_version="1",
                                    client_version="19")
        _secrets, text = self._run("agent", mock.Mock(return_value=sel))
        line = [r for r in text.splitlines() if "Orcamento da conexao" in r][0]
        self.assertIn("| OK ", line)
        self.assertIn("30s (call_timeout_s 30s)", line)
        dsn = ("(DESCRIPTION=(CONNECT_TIMEOUT=20)(RETRY_COUNT=1)(ADDRESS_LIST="
               "(ADDRESS=(HOST=a)(PORT=1521))(ADDRESS=(HOST=b)(PORT=1521)))"
               "(CONNECT_DATA=(SERVICE_NAME=s)))")
        with mock.patch.object(db_conn, "_BUDGET_WARNING_EMITTED", False), \
                self.assertLogs(db_conn.logger, "WARNING") as logs:
            _secrets, text = self._run("agent", mock.Mock(return_value=sel), dsn=dsn)
        line = [r for r in text.splitlines() if "Orcamento da conexao" in r][0]
        self.assertIn("AVISO", line)
        self.assertIn("80s (call_timeout_s 30s): CONEXAO_ACIMA_DO_PRAZO", line)
        self.assertIn("CONEXAO_ACIMA_DO_PRAZO", logs.output[0])
        self.assertIn("Todos os pre-requisitos", text, "AVISO nao reprova o ambiente")

    def test_cliente_fora_do_19_e_aviso(self):
        # Decisao 10 A (2026-10-30): o cliente 12.2 do 3067 conecta; o 19 e so o recomendado.
        sel = types.SimpleNamespace(candidate="cx_oracle", server_version="19.0.0.0.0",
                                    driver_version="8.3.0", client_version="12.2.0.1.0")
        _secrets, text = self._run("agent", mock.Mock(return_value=sel))
        line = [r for r in text.splitlines() if "Cliente Oracle" in r][0]
        self.assertIn("AVISO", line)
        self.assertIn("cliente Oracle 12.2.0.1.0; o recomendado e o Instant Client 19", line)
        self.assertIn("Todos os pre-requisitos", text, "AVISO nao reprova o ambiente")
        sel.client_version = "19.27.0.0.0"
        _secrets, text = self._run("agent", mock.Mock(return_value=sel))
        self.assertNotIn("Cliente Oracle", text)

    def test_agente_mostra_locale_e_interpretadores(self):
        """Melhoria 1 (2026-10-30): o que a subida do agente avisa aparece antes, no check_env (so
        no agente)."""
        sel = types.SimpleNamespace(candidate="cx_oracle", server_version="19.0.0.0.0",
                                    driver_version="8.3.0", client_version="19.27.0.0.0")
        _secrets, text = self._run("agent", mock.Mock(return_value=sel))
        self.assertRegex(text, r"Locale dos scripts\s+\| OK\s+\| C\.UTF-8")
        self.assertRegex(text,
                         r"Interpretadores\s+\| OK\s+\| python -> /usr/bin/python \(3\.12\.3\)")
        _secrets, text = self._run("agent", mock.Mock(return_value=sel), locale="en_US.utf8",
                                   interpreters=(("python", "/usr/bin/python", "2.6.6"),
                                                 ("python3", None, None)))
        self.assertIn("C.UTF-8 nao consta em locale -a: os scripts usam en_US.utf8", text)
        self.assertIn("python e o Python 2.6.6: cadastre scripts Python 3 como python3", text)
        self.assertIn("python3 -> nao encontrado", text)
        self.assertIn("Todos os pre-requisitos", text, "AVISO nao reprova o ambiente")
        _secrets, text = self._run("agent", mock.Mock(return_value=sel), locale=None)
        self.assertRegex(text, r"Locale dos scripts\s+\| FALHA")
        _secrets, text = self._run("web", mock.Mock(return_value=sel))
        self.assertNotIn("Locale dos scripts", text, "o web nao roda scripts")

    def test_sem_processo_sai_com_2(self):
        # README §12.1: sem --name nem --config (CR-029, sem config padrao), codigo 2 antes
        # da tabela
        err = io.StringIO()
        probe = mock.Mock()
        with mock.patch.object(sss_config, "config_path",
                               side_effect=sss_config.ConfigError("informe o processo")), \
                mock.patch.object(db_conn, "select_driver", probe), \
                mock.patch("sys.stderr", err), \
                redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit) as ctx:
                check_env.main([])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("Configuracao invalida: informe o processo", err.getvalue())
        self.assertEqual(out.getvalue(), "", "nada da tabela antes da recusa")
        probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
