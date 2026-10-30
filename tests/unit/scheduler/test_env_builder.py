# -*- coding: utf-8 -*-
"""Testes do env_builder (README §8.6, AGENTS §7.4; CR-007 R-17/R-32; CR-008 R-36): ambiente exato do filho
POSIX, sem heranca de os.environ, passthrough, bloqueio, omissao da conexao e mascaramento."""
from tests.support import _testenv  # noqa: F401

import collections
import datetime
import os
import unittest
from unittest import mock

from sss.scheduler import env_builder
from sss.core import masking
from sss.config.sss_config import EnvironmentSecret, Secrets

_AgentStub = collections.namedtuple("_Agente", "agent_id child_locale env_passthrough script_base_dir")
_Cfg = collections.namedtuple("_Cfg", "agent")

WORK = "/srv/sss/work/ticket_41"
SCRIPT = "/opt/automacoes/scripts/faturamento/carga.py"
DAEMON = {"PATH": "/opt/daemon/bin:/usr/bin", "HOME": "/home/sssagente", "TZ": "America/Sao_Paulo",
          "ORACLE_HOME": "/opt/oracle", "NLS_LANG": "AMERICAN_AMERICA.AL32UTF8", "SEGREDO_DAEMON": "nao-vaza",
          "LD_PRELOAD": "/tmp/x.so", "PYTHONPATH": "/tmp"}


def _cfg(passthrough=("ORACLE_HOME", "NLS_LANG", "TNS_ADMIN")):
    return _Cfg(_AgentStub("srv-01", "C.UTF-8", tuple(passthrough), None))


def _secrets(environments=None):
    return Secrets(oracle_password="x" * 8, cookie_key=None, environments=environments or {})


AMB = {"name": "PRODUCAO", "connection": "dbprod:1521/FAT"}
TICKET = {"id": 41, "environment": "PRODUCAO"}


class TestEnvBuilder(unittest.TestCase):

    def build(self, cfg=None, secrets=None, environment=AMB, environ=DAEMON):
        return env_builder.build(cfg or _cfg(), secrets or _secrets(), TICKET, environment, SCRIPT, WORK,
                                     dict(environ), "LINUX")

    def test_variaveis_exatas_dev(self):
        with self.assertLogs("sss_scheduler", "WARNING"), \
                mock.patch.object(env_builder.sys, "executable", "/usr/bin/python3"):
            env = self.build()
        home = os.path.join(WORK, "exec")
        self.assertEqual(env, {
            "PATH": "/usr/bin:/bin", "HOME": home, "TMPDIR": os.path.join(home, "tmp"),
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "America/Sao_Paulo",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
            "SSS_TICKET_ID": "41", "SSS_ENVIRONMENT": "PRODUCAO", "SSS_AGENT_ID": "srv-01",
            "SSS_SCRIPT_DIR": "/opt/automacoes/scripts/faturamento",
            "SSS_SCRIPT_FILE": SCRIPT, "SSS_PLATFORM": "LINUX", "SSS_EXECUTION_TYPE": "MANUAL",
            "SSS_ENVIRONMENT_DSN": "dbprod:1521/FAT",
            "ORACLE_HOME": "/opt/oracle", "NLS_LANG": "AMERICAN_AMERICA.AL32UTF8"})

    def test_path_com_a_pasta_do_python_do_agente_no_fim(self):
        """Decisao 13 A: a pasta do Python do agente entra no fim do PATH do filho, sem repetir /usr/bin."""
        sparta = "/portaloptrib/TESHUVA/sparta/python3.8/bin/python3"
        self.assertEqual(env_builder.child_path(sparta), "/usr/bin:/bin:/portaloptrib/TESHUVA/sparta/python3.8/bin")
        self.assertEqual(env_builder.child_path("/usr/bin/python3"), "/usr/bin:/bin")
        self.assertEqual(env_builder.child_path("/bin/python3"), "/usr/bin:/bin")
        self.assertEqual(env_builder.child_path(""), "/usr/bin:/bin")
        self.assertEqual(env_builder.child_path("python3"), "/usr/bin:/bin", "caminho relativo nao entra")
        with self.assertLogs("sss_scheduler", "WARNING"), mock.patch.object(env_builder.sys, "executable", sparta):
            env = self.build()
        self.assertEqual(env["PATH"], "/usr/bin:/bin:/portaloptrib/TESHUVA/sparta/python3.8/bin")

    def test_sem_home_real_nem_path_do_daemon_nem_heranca(self):
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = self.build()
        self.assertNotEqual(env["HOME"], DAEMON["HOME"])
        self.assertNotEqual(env["PATH"], DAEMON["PATH"])
        for name in ("SEGREDO_DAEMON", "LD_PRELOAD", "PYTHONPATH", "TNS_ADMIN"):
            self.assertNotIn(name, env)

    def test_nunca_le_os_environ(self):
        with mock.patch.dict(os.environ, {"ORACLE_HOME": "/do/os/environ", "TZ": "UTC"}, clear=False), \
                self.assertLogs("sss_scheduler", "WARNING"):
            env = self.build(environ={})
        self.assertNotIn("ORACLE_HOME", env)
        self.assertNotIn("TZ", env)

    def test_home_na_pasta_exec_do_ticket(self):
        """CR-032 (D7): sem usuario de execucao, o cwd/HOME e sempre work_dir/ticket_<id>/exec."""
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = self.build()
        self.assertEqual(env["HOME"], os.path.join(WORK, "exec"))
        self.assertEqual(env["TMPDIR"], os.path.join(WORK, "exec", "tmp"))
        self.assertNotEqual(env["HOME"], env["SSS_SCRIPT_DIR"], "cwd/HOME nao e a pasta do script")

    def test_variaveis_bloqueadas_e_chaves_fixas_geram_erro(self):
        for name in ("LD_PRELOAD", "LD_AUDIT", "BASH_FUNC_x%%", "MALLOC_ARENA_MAX", "PYTHONPATH", "BASH_ENV",
                     "IFS", "PATH", "HOME", "TZ", "LC_CTYPE", "SSS_TICKET_ID", "PYTHONIOENCODING",
                     "PADRAO_VALOR_RUN_CONEXAO_BD", "GLIBC_TUNABLES"):
            with self.assertRaises(ValueError, msg=name):
                self.build(cfg=_cfg(passthrough=(name,)))
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = self.build(cfg=_cfg(passthrough=("LD_LIBRARY_PATH",)),
                                 environ=dict(DAEMON, LD_LIBRARY_PATH="/opt/oracle/lib"))
        self.assertEqual(env["LD_LIBRARY_PATH"], "/opt/oracle/lib")

    def test_conexao_com_dsn_e_credencial_e_mascarador(self):
        cred = EnvironmentSecret("fat_app", "S3nh@Forte")
        with mock.patch.object(masking, "MASKER", masking.Masker()) as masker:
            env = self.build(secrets=_secrets({"PRODUCAO": cred}))
            self.assertEqual(env["PADRAO_VALOR_RUN_CONEXAO_BD"], "fat_app/S3nh@Forte@dbprod:1521/FAT")
            self.assertEqual(masker.mask("conexao fat_app/S3nh@Forte@dbprod:1521/FAT ok"), "conexao **** ok")
            self.assertNotIn("S3nh@Forte", masker.mask("senha S3nh@Forte"))

    def test_conexao_omitida_sem_secao_ou_sem_dsn(self):
        cred = EnvironmentSecret("fat_app", "S3nh@Forte")
        cases = ((_secrets(), AMB, "credencial"), (_secrets({"PRODUCAO": cred}), dict(AMB, connection=None), "DSN"),
                 (_secrets({"PRODUCAO": cred}), dict(AMB, connection="  "), "DSN"))
        for secrets_value, environment, reason in cases:
            with self.assertLogs("sss_scheduler", "WARNING") as logs:
                env = self.build(secrets=secrets_value, environment=environment)
            self.assertNotIn("PADRAO_VALOR_RUN_CONEXAO_BD", env)
            self.assertIn(reason, logs.output[0])
            self.assertNotIn("S3nh@Forte", logs.output[0], "WARN sem valores")

    def test_cr026_sss_interpreter_traduz_a_chave_anterior(self):
        # Ticket v5/v6 ainda na fila: PYTHON3 vira python3, como no cadastro (CR-026f).
        for old, new in (("PYTHON3", "python3"), ("SHELL_SCRIPT", "sh"), ("bash", "bash")):
            env = env_builder.build(_cfg(), _secrets({}), {"id": 1, "environment": "PRODUCAO"}, dict(AMB),
                                    SCRIPT, WORK, dict(DAEMON), "LINUX",
                                    snapshot={"script_id": 1, "script_name": "s", "interpreter": old})
            self.assertEqual(env["SSS_INTERPRETER"], new, old)

    def test_cr010_execucao_agendada_completa(self):
        cred = EnvironmentSecret("fat_app", "S3nh@Forte")
        ticket = {"id": 41, "environment": "PRODUCAO", "parent_ticket_id": 7, "schedule_id": 3, "priority": 2,
                  "started_at": datetime.datetime(2026, 10, 20, 3, 0, 5),
                  "scheduled_at": datetime.datetime(2026, 10, 20, 3, 0)}
        snap = {"script_id": 12, "script_name": "Carga Faturas", "interpreter": "python3"}
        env_name = dict(AMB, description="Produção faturamento")
        log = "/srv/sss/logs/producao/carga_faturas/2026/10/20/03/00/ticket_41.log.parcial"
        with mock.patch.object(masking, "MASKER", masking.Masker()):
            env = env_builder.build(_cfg(), _secrets({"PRODUCAO": cred}), ticket, env_name, SCRIPT, WORK,
                                        dict(DAEMON), "LINUX", snapshot=snap,
                                        schedule={"name": "Carga noturna", "recurrence_type": "MONTHLY"},
                                        log_path=log, timeout_sec=3600, hostname="srv-linux-01", version="1.0")
        sss = dict((k, v) for k, v in env.items() if k.startswith("SSS_"))
        self.assertEqual(sss, {
            "SSS_TICKET_ID": "41", "SSS_PARENT_TICKET_ID": "7", "SSS_EXECUTION_TYPE": "AGENDADA",
            "SSS_RECURRENCE": "MONTHLY", "SSS_SCHEDULE_ID": "3", "SSS_SCHEDULE_NAME": "Carga noturna",
            "SSS_STARTED_AT": "2026-10-20 03:00:05", "SSS_SCHEDULED_AT": "2026-10-20 03:00:00",
            "SSS_PRIORITY": "2", "SSS_TIMEOUT_SECONDS": "3600",
            "SSS_ENVIRONMENT": "PRODUCAO", "SSS_ENVIRONMENT_DESCRIPTION": "Produção faturamento",
            "SSS_ENVIRONMENT_DSN": "dbprod:1521/FAT", "SSS_ENVIRONMENT_USER": "fat_app",
            "SSS_ENVIRONMENT_CONNECTION": "fat_app/S3nh@Forte@dbprod:1521/FAT",
            "SSS_SCRIPT_ID": "12", "SSS_SCRIPT_NAME": "Carga Faturas", "SSS_INTERPRETER": "python3",
            "SSS_SCRIPT_FILE": SCRIPT, "SSS_SCRIPT_DIR": "/opt/automacoes/scripts/faturamento",
            "SSS_LOG_DIR": "/srv/sss/logs/producao/carga_faturas/2026/10/20/03/00",
            "SSS_LOG_FILE": "ticket_41.log.parcial",
            "SSS_AGENT_ID": "srv-01", "SSS_AGENT_HOST": "srv-linux-01", "SSS_PLATFORM": "LINUX",
            "SSS_VERSION": "1.0"})
        self.assertEqual(env["PADRAO_VALOR_RUN_CONEXAO_BD"], env["SSS_ENVIRONMENT_CONNECTION"],
                         "variavel antiga mantida")
        self.assertNotIn("SSS_SOLICITANTE", env)
        self.assertFalse([k for k in env if k.startswith("SSS_PARAM")])

    def test_cr010_manual_sem_dados_de_agendamento_e_valores_vazios_ausentes(self):
        ticket = {"id": 41, "environment": "PRODUCAO", "parent_ticket_id": None, "schedule_id": None,
                  "priority": None}
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = env_builder.build(_cfg(), _secrets(), ticket, dict(AMB, description="  ", connection=None),
                                        SCRIPT, WORK, {}, "UNIX", snapshot={"script_name": ""},
                                        schedule={"name": "ignorado", "recurrence_type": "DAILY"},
                                        hostname="", version=None)
        self.assertEqual(env["SSS_EXECUTION_TYPE"], "MANUAL")
        for missing in ("SSS_RECURRENCE", "SSS_SCHEDULE_ID", "SSS_SCHEDULE_NAME", "SSS_PARENT_TICKET_ID",
                        "SSS_PRIORITY", "SSS_ENVIRONMENT_DESCRIPTION", "SSS_ENVIRONMENT_DSN", "SSS_ENVIRONMENT_USER",
                        "SSS_ENVIRONMENT_CONNECTION", "SSS_SCRIPT_NAME", "SSS_AGENT_HOST", "SSS_VERSION",
                        "SSS_LOG_DIR", "SSS_LOG_FILE", "SSS_STARTED_AT", "PADRAO_VALOR_RUN_CONEXAO_BD"):
            self.assertNotIn(missing, env, missing)
        self.assertEqual(env["SSS_PLATFORM"], "UNIX")

    def test_cr010_conexao_mascarada_nos_logs(self):
        cred = EnvironmentSecret("fat_app", "S3nh@Forte")
        with mock.patch.object(masking, "MASKER", masking.Masker()) as masker:
            env = self.build(secrets=_secrets({"PRODUCAO": cred}))
            self.assertEqual(masker.mask("SSS_ENVIRONMENT_CONNECTION=%s" % env["SSS_ENVIRONMENT_CONNECTION"]),
                             "SSS_ENVIRONMENT_CONNECTION=****")
        self.assertEqual(env["SSS_ENVIRONMENT_USER"], "fat_app")

    def test_cr011_link_no_caminho_cadastrado(self):
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = env_builder.build(_cfg(), _secrets(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX",
                                        snapshot={"path_file": "/opt/automacoes/atual/carga.py"})
            without_link = env_builder.build(_cfg(), _secrets(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX",
                                             snapshot={"path_file": SCRIPT})
        self.assertEqual((env["SSS_SCRIPT_FILE"], env["SSS_SCRIPT_LINK"]), (SCRIPT, "/opt/automacoes/atual/carga.py"))
        self.assertNotIn("SSS_SCRIPT_LINK", without_link)

    def test_cr023_relativo_vira_absoluto_no_link(self):
        cfg = _cfg()
        cfg = cfg._replace(agent=cfg.agent._replace(script_base_dir="/opt/automacoes/scripts"))
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = env_builder.build(cfg, _secrets(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX",
                                    snapshot={"path_file": "relatorios/carga.py"})
        self.assertEqual(env["SSS_SCRIPT_LINK"], "/opt/automacoes/scripts/relatorios/carga.py")
        self.assertEqual(env["SSS_SCRIPT_FILE"], SCRIPT)

    def test_cr012_pasta_de_saida_so_quando_informada(self):
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = env_builder.build(_cfg(), _secrets(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX",
                                        output_dir="/srv/sss/output/producao/carga/2026/10/20/03/00/ticket_41")
            without = env_builder.build(_cfg(), _secrets(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX")
        self.assertEqual(env["SSS_OUTPUT_DIR"], "/srv/sss/output/producao/carga/2026/10/20/03/00/ticket_41")
        self.assertNotIn("SSS_OUTPUT_DIR", without)

    def test_cr014_pasta_de_entrada_so_quando_informada(self):
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = env_builder.build(_cfg(), _secrets(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX",
                                        input_dir="/srv/sss/input/producao/carga")
            without = env_builder.build(_cfg(), _secrets(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX")
        self.assertEqual(env["SSS_INPUT_DIR"], "/srv/sss/input/producao/carga")
        self.assertNotIn("SSS_INPUT_DIR", without)

    def test_cr019_pasta_de_trabalho_so_quando_informada(self):
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = env_builder.build(_cfg(), _secrets(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX",
                                        work_folder="/srv/sss/work/producao/carga/2026/10/20/03/00/ticket_41")
            without = env_builder.build(_cfg(), _secrets(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX")
        self.assertEqual(env["SSS_WORK_DIR"], "/srv/sss/work/producao/carga/2026/10/20/03/00/ticket_41")
        self.assertNotIn("SSS_WORK_DIR", without)
        self.assertNotEqual(env["HOME"], env["SSS_WORK_DIR"], "HOME e cwd continuam na pasta descartavel")

    def test_cr037_pasta_de_arquivos_so_quando_informada(self):
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = env_builder.build(_cfg(), _secrets(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX",
                                    files_inputs="/v/a/files/producao/carga/inputs",
                                    files_outputs="/v/a/files/producao/carga/outputs")
            without = env_builder.build(_cfg(), _secrets(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX")
        self.assertEqual((env["SSS_FILES_INPUTS_DIR"], env["SSS_FILES_OUTPUTS_DIR"]),
                         ("/v/a/files/producao/carga/inputs", "/v/a/files/producao/carga/outputs"))
        self.assertNotIn("SSS_FILES_INPUTS_DIR", without)
        self.assertNotIn("SSS_FILES_OUTPUTS_DIR", without)

    def test_cr015a_so_nomes_em_ingles(self):
        """Troca direta (CR-015a): nenhum nome antigo chega ao script, nem com todos os dados presentes."""
        old = ("SSS_TICKET_PAI_ID", "SSS_AMBIENTE", "SSS_AMBIENTE_DESCRICAO", "SSS_AMBIENTE_DSN",
                   "SSS_AMBIENTE_USUARIO", "SSS_AMBIENTE_CONEXAO", "SSS_AGENTE_ID", "SSS_AGENTE_HOST",
                   "SSS_PLATAFORMA", "SSS_VERSAO", "SSS_SCRIPT_NOME", "SSS_SCRIPT_ARQUIVO", "SSS_INTERPRETADOR",
                   "SSS_TIPO_EXECUCAO", "SSS_PRIORIDADE", "SSS_DATA_EXECUCAO", "SSS_DATA_AGENDADA", "SSS_TIMEOUT_SEG",
                   "SSS_AGENDAMENTO_ID", "SSS_AGENDAMENTO_NOME", "SSS_RECORRENCIA", "SSS_LOG_ARQUIVO",
                   "SSS_SAIDA_DIR", "SSS_ENTRADA_DIR")
        ticket = {"id": 41, "environment": "PRODUCAO", "parent_ticket_id": 7, "schedule_id": 3, "priority": 2,
                  "started_at": datetime.datetime(2026, 10, 20, 3, 0, 5),
                  "scheduled_at": datetime.datetime(2026, 10, 20, 3, 0)}
        with mock.patch.object(masking, "MASKER", masking.Masker()):
            env = env_builder.build(_cfg(), _secrets({"PRODUCAO": EnvironmentSecret("fat_app", "S3nh@Forte")}),
                                        ticket, dict(AMB, description="x"), SCRIPT, WORK, dict(DAEMON), "LINUX",
                                        snapshot={"script_id": 12, "script_name": "C", "interpreter": "sh",
                                                  "path_file": "/opt/automacoes/atual/carga.sh"},
                                        schedule={"name": "N", "recurrence_type": "CRON"},
                                        log_path="/srv/sss/logs/x/ticket_41.log.parcial", timeout_sec=60,
                                        hostname="h", version="1.0", output_dir="/srv/s", input_dir="/srv/e")
        self.assertEqual([k for k in old if k in env], [])
        self.assertTrue(set(("SSS_ENVIRONMENT", "SSS_OUTPUT_DIR", "SSS_INPUT_DIR", "SSS_SCHEDULE_NAME")) <= set(env))

    def test_entradas_invalidas(self):
        with self.assertRaises(ValueError):
            env_builder.build(_cfg(), _secrets(), TICKET, AMB, SCRIPT, WORK, {}, "WINDOWS")
        with self.assertRaises(ValueError):
            env_builder.build(_cfg(), _secrets(), TICKET, AMB, "relativo/x.py", WORK, {}, "LINUX")

    def test_modulo_nao_le_os_environ(self):
        with open(env_builder.__file__, encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("os.environ", source)
        self.assertNotIn("import os_platform", source)
        self.assertNotIn("sss.platform", source)


if __name__ == "__main__":
    unittest.main()
