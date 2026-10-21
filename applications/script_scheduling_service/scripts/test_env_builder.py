# -*- coding: utf-8 -*-
"""Testes do env_builder (README §8.6, AGENTS §7.4; CR-007 R-17/R-32; CR-008 R-36): ambiente exato do filho
POSIX, sem heranca de os.environ, passthrough, bloqueio, omissao da conexao e mascaramento."""
import _testenv  # noqa: F401

import collections
import datetime
import os
import unittest
from unittest import mock

import env_builder
import masking
from sss_config import AmbienteSegredo, Segredos

_Agente = collections.namedtuple("_Agente", "agent_id child_locale env_passthrough usuarios_execucao exec_work_dir")
_Cfg = collections.namedtuple("_Cfg", "agent")

WORK = "/srv/sss/work/ticket_41"
SCRIPT = "/opt/automacoes/scripts/faturamento/carga.py"
DAEMON = {"PATH": "/opt/daemon/bin:/usr/bin", "HOME": "/home/sssagente", "TZ": "America/Sao_Paulo",
          "ORACLE_HOME": "/opt/oracle", "NLS_LANG": "AMERICAN_AMERICA.AL32UTF8", "SEGREDO_DAEMON": "nao-vaza",
          "LD_PRELOAD": "/tmp/x.so", "PYTHONPATH": "/tmp"}


def _cfg(passthrough=("ORACLE_HOME", "NLS_LANG", "TNS_ADMIN"), usuarios=(), exec_work_dir=None):
    return _Cfg(_Agente("srv-01", "C.UTF-8", tuple(passthrough), tuple(usuarios), exec_work_dir))


def _segredos(ambientes=None):
    return Segredos(oracle_password="x" * 8, cookie_key=None, ambientes=ambientes or {})


AMB = {"nome": "PRODUCAO", "conexao": "dbprod:1521/FAT"}
TICKET = {"id": 41, "ambiente": "PRODUCAO"}


class TestEnvBuilder(unittest.TestCase):

    def construir(self, cfg=None, segredos=None, ambiente=AMB, environ=DAEMON):
        return env_builder.construir(cfg or _cfg(), segredos or _segredos(), TICKET, ambiente, SCRIPT, WORK,
                                     dict(environ), "LINUX")

    def test_variaveis_exatas_dev(self):
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = self.construir()
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

    def test_sem_home_real_nem_path_do_daemon_nem_heranca(self):
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = self.construir()
        self.assertNotEqual(env["HOME"], DAEMON["HOME"])
        self.assertNotEqual(env["PATH"], DAEMON["PATH"])
        for nome in ("SEGREDO_DAEMON", "LD_PRELOAD", "PYTHONPATH", "TNS_ADMIN"):
            self.assertNotIn(nome, env)

    def test_nunca_le_os_environ(self):
        with mock.patch.dict(os.environ, {"ORACLE_HOME": "/do/os/environ", "TZ": "UTC"}, clear=False), \
                self.assertLogs("sss_scheduler", "WARNING"):
            env = self.construir(environ={})
        self.assertNotIn("ORACLE_HOME", env)
        self.assertNotIn("TZ", env)

    def test_home_com_usuario_de_execucao(self):
        cfg = _cfg(usuarios=(("PRODUCAO", "sssprd"),), exec_work_dir="/srv/sss/exec")
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = self.construir(cfg=cfg)
        self.assertEqual(env["HOME"], "/srv/sss/exec/sssprd/ticket_41")
        self.assertEqual(env["TMPDIR"], "/srv/sss/exec/sssprd/ticket_41/tmp")
        self.assertNotEqual(env["HOME"], env["SSS_SCRIPT_DIR"], "cwd/HOME nao e a pasta do script")

    def test_variaveis_bloqueadas_e_chaves_fixas_geram_erro(self):
        for nome in ("LD_PRELOAD", "LD_AUDIT", "BASH_FUNC_x%%", "MALLOC_ARENA_MAX", "PYTHONPATH", "BASH_ENV",
                     "IFS", "PATH", "HOME", "TZ", "LC_CTYPE", "SSS_TICKET_ID", "PYTHONIOENCODING",
                     "PADRAO_VALOR_RUN_CONEXAO_BD", "GLIBC_TUNABLES"):
            with self.assertRaises(ValueError, msg=nome):
                self.construir(cfg=_cfg(passthrough=(nome,)))
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = self.construir(cfg=_cfg(passthrough=("LD_LIBRARY_PATH",)),
                                 environ=dict(DAEMON, LD_LIBRARY_PATH="/opt/oracle/lib"))
        self.assertEqual(env["LD_LIBRARY_PATH"], "/opt/oracle/lib")

    def test_conexao_com_dsn_e_credencial_e_mascarador(self):
        cred = AmbienteSegredo("fat_app", "S3nh@Forte")
        with mock.patch.object(masking, "MASCARADOR", masking.Mascarador()) as masc:
            env = self.construir(segredos=_segredos({"PRODUCAO": cred}))
            self.assertEqual(env["PADRAO_VALOR_RUN_CONEXAO_BD"], "fat_app/S3nh@Forte@dbprod:1521/FAT")
            self.assertEqual(masc.mascarar("conexao fat_app/S3nh@Forte@dbprod:1521/FAT ok"), "conexao **** ok")
            self.assertNotIn("S3nh@Forte", masc.mascarar("senha S3nh@Forte"))

    def test_conexao_omitida_sem_secao_ou_sem_dsn(self):
        cred = AmbienteSegredo("fat_app", "S3nh@Forte")
        casos = ((_segredos(), AMB, "credencial"), (_segredos({"PRODUCAO": cred}), dict(AMB, conexao=None), "DSN"),
                 (_segredos({"PRODUCAO": cred}), dict(AMB, conexao="  "), "DSN"))
        for segredos, ambiente, motivo in casos:
            with self.assertLogs("sss_scheduler", "WARNING") as logs:
                env = self.construir(segredos=segredos, ambiente=ambiente)
            self.assertNotIn("PADRAO_VALOR_RUN_CONEXAO_BD", env)
            self.assertIn(motivo, logs.output[0])
            self.assertNotIn("S3nh@Forte", logs.output[0], "WARN sem valores")

    def test_cr010_execucao_agendada_completa(self):
        cred = AmbienteSegredo("fat_app", "S3nh@Forte")
        ticket = {"id": 41, "ambiente": "PRODUCAO", "parent_ticket_id": 7, "agendamento_id": 3, "prioridade": 2,
                  "started_at": datetime.datetime(2026, 10, 20, 3, 0, 5),
                  "scheduled_at": datetime.datetime(2026, 10, 20, 3, 0)}
        snap = {"script_id": 12, "script_nome": "Carga Faturas", "interpretador": "PYTHON3"}
        amb = dict(AMB, descricao="Produção faturamento")
        log = "/srv/sss/logs/producao/carga_faturas/2026/10/20/03/00/ticket_41.log.parcial"
        with mock.patch.object(masking, "MASCARADOR", masking.Mascarador()):
            env = env_builder.construir(_cfg(), _segredos({"PRODUCAO": cred}), ticket, amb, SCRIPT, WORK,
                                        dict(DAEMON), "LINUX", snapshot=snap,
                                        agendamento={"nome": "Carga noturna", "tipo_recorrencia": "MENSAL"},
                                        caminho_log=log, timeout_seg=3600, hostname="srv-linux-01", versao="1.0")
        sss = dict((k, v) for k, v in env.items() if k.startswith("SSS_"))
        self.assertEqual(sss, {
            "SSS_TICKET_ID": "41", "SSS_PARENT_TICKET_ID": "7", "SSS_EXECUTION_TYPE": "AGENDADA",
            "SSS_RECURRENCE": "MENSAL", "SSS_SCHEDULE_ID": "3", "SSS_SCHEDULE_NAME": "Carga noturna",
            "SSS_STARTED_AT": "2026-10-20 03:00:05", "SSS_SCHEDULED_AT": "2026-10-20 03:00:00",
            "SSS_PRIORITY": "2", "SSS_TIMEOUT_SECONDS": "3600",
            "SSS_ENVIRONMENT": "PRODUCAO", "SSS_ENVIRONMENT_DESCRIPTION": "Produção faturamento",
            "SSS_ENVIRONMENT_DSN": "dbprod:1521/FAT", "SSS_ENVIRONMENT_USER": "fat_app",
            "SSS_ENVIRONMENT_CONNECTION": "fat_app/S3nh@Forte@dbprod:1521/FAT",
            "SSS_SCRIPT_ID": "12", "SSS_SCRIPT_NAME": "Carga Faturas", "SSS_INTERPRETER": "PYTHON3",
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
        ticket = {"id": 41, "ambiente": "PRODUCAO", "parent_ticket_id": None, "agendamento_id": None,
                  "prioridade": None}
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = env_builder.construir(_cfg(), _segredos(), ticket, dict(AMB, descricao="  ", conexao=None),
                                        SCRIPT, WORK, {}, "UNIX", snapshot={"script_nome": ""},
                                        agendamento={"nome": "ignorado", "tipo_recorrencia": "DIARIA"},
                                        hostname="", versao=None)
        self.assertEqual(env["SSS_EXECUTION_TYPE"], "MANUAL")
        for ausente in ("SSS_RECURRENCE", "SSS_SCHEDULE_ID", "SSS_SCHEDULE_NAME", "SSS_PARENT_TICKET_ID",
                        "SSS_PRIORITY", "SSS_ENVIRONMENT_DESCRIPTION", "SSS_ENVIRONMENT_DSN", "SSS_ENVIRONMENT_USER",
                        "SSS_ENVIRONMENT_CONNECTION", "SSS_SCRIPT_NAME", "SSS_AGENT_HOST", "SSS_VERSION",
                        "SSS_LOG_DIR", "SSS_LOG_FILE", "SSS_STARTED_AT", "PADRAO_VALOR_RUN_CONEXAO_BD"):
            self.assertNotIn(ausente, env, ausente)
        self.assertEqual(env["SSS_PLATFORM"], "UNIX")

    def test_cr010_conexao_mascarada_nos_logs(self):
        cred = AmbienteSegredo("fat_app", "S3nh@Forte")
        with mock.patch.object(masking, "MASCARADOR", masking.Mascarador()) as masc:
            env = self.construir(segredos=_segredos({"PRODUCAO": cred}))
            self.assertEqual(masc.mascarar("SSS_ENVIRONMENT_CONNECTION=%s" % env["SSS_ENVIRONMENT_CONNECTION"]),
                             "SSS_ENVIRONMENT_CONNECTION=****")
        self.assertEqual(env["SSS_ENVIRONMENT_USER"], "fat_app")

    def test_cr011_link_no_caminho_cadastrado(self):
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = env_builder.construir(_cfg(), _segredos(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX",
                                        snapshot={"path_file": "/opt/automacoes/atual/carga.py"})
            sem_link = env_builder.construir(_cfg(), _segredos(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX",
                                             snapshot={"path_file": SCRIPT})
        self.assertEqual((env["SSS_SCRIPT_FILE"], env["SSS_SCRIPT_LINK"]), (SCRIPT, "/opt/automacoes/atual/carga.py"))
        self.assertNotIn("SSS_SCRIPT_LINK", sem_link)

    def test_cr012_pasta_de_saida_so_quando_informada(self):
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = env_builder.construir(_cfg(), _segredos(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX",
                                        pasta_saida="/srv/sss/saida/producao/carga/2026/10/20/03/00/ticket_41")
            sem = env_builder.construir(_cfg(), _segredos(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX")
        self.assertEqual(env["SSS_OUTPUT_DIR"], "/srv/sss/saida/producao/carga/2026/10/20/03/00/ticket_41")
        self.assertNotIn("SSS_OUTPUT_DIR", sem)

    def test_cr014_pasta_de_entrada_so_quando_informada(self):
        with self.assertLogs("sss_scheduler", "WARNING"):
            env = env_builder.construir(_cfg(), _segredos(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX",
                                        pasta_entrada="/srv/sss/entrada/producao/carga")
            sem = env_builder.construir(_cfg(), _segredos(), TICKET, AMB, SCRIPT, WORK, {}, "LINUX")
        self.assertEqual(env["SSS_INPUT_DIR"], "/srv/sss/entrada/producao/carga")
        self.assertNotIn("SSS_INPUT_DIR", sem)

    def test_cr015a_so_nomes_em_ingles(self):
        """Troca direta (CR-015a): nenhum nome antigo chega ao script, nem com todos os dados presentes."""
        antigos = ("SSS_TICKET_PAI_ID", "SSS_AMBIENTE", "SSS_AMBIENTE_DESCRICAO", "SSS_AMBIENTE_DSN",
                   "SSS_AMBIENTE_USUARIO", "SSS_AMBIENTE_CONEXAO", "SSS_AGENTE_ID", "SSS_AGENTE_HOST",
                   "SSS_PLATAFORMA", "SSS_VERSAO", "SSS_SCRIPT_NOME", "SSS_SCRIPT_ARQUIVO", "SSS_INTERPRETADOR",
                   "SSS_TIPO_EXECUCAO", "SSS_PRIORIDADE", "SSS_DATA_EXECUCAO", "SSS_DATA_AGENDADA", "SSS_TIMEOUT_SEG",
                   "SSS_AGENDAMENTO_ID", "SSS_AGENDAMENTO_NOME", "SSS_RECORRENCIA", "SSS_LOG_ARQUIVO",
                   "SSS_SAIDA_DIR", "SSS_ENTRADA_DIR")
        ticket = {"id": 41, "ambiente": "PRODUCAO", "parent_ticket_id": 7, "agendamento_id": 3, "prioridade": 2,
                  "started_at": datetime.datetime(2026, 10, 20, 3, 0, 5),
                  "scheduled_at": datetime.datetime(2026, 10, 20, 3, 0)}
        with mock.patch.object(masking, "MASCARADOR", masking.Mascarador()):
            env = env_builder.construir(_cfg(), _segredos({"PRODUCAO": AmbienteSegredo("fat_app", "S3nh@Forte")}),
                                        ticket, dict(AMB, descricao="x"), SCRIPT, WORK, dict(DAEMON), "LINUX",
                                        snapshot={"script_id": 12, "script_nome": "C", "interpretador": "SH",
                                                  "path_file": "/opt/automacoes/atual/carga.sh"},
                                        agendamento={"nome": "N", "tipo_recorrencia": "CRON"},
                                        caminho_log="/srv/sss/logs/x/ticket_41.log.parcial", timeout_seg=60,
                                        hostname="h", versao="1.0", pasta_saida="/srv/s", pasta_entrada="/srv/e")
        self.assertEqual([k for k in antigos if k in env], [])
        self.assertTrue(set(("SSS_ENVIRONMENT", "SSS_OUTPUT_DIR", "SSS_INPUT_DIR", "SSS_SCHEDULE_NAME")) <= set(env))

    def test_entradas_invalidas(self):
        with self.assertRaises(ValueError):
            env_builder.construir(_cfg(), _segredos(), TICKET, AMB, SCRIPT, WORK, {}, "WINDOWS")
        with self.assertRaises(ValueError):
            env_builder.construir(_cfg(), _segredos(), TICKET, AMB, "relativo/x.py", WORK, {}, "LINUX")

    def test_modulo_nao_le_os_environ(self):
        with open(env_builder.__file__, encoding="utf-8") as f:
            fonte = f.read()
        self.assertNotIn("os.environ", fonte)
        self.assertNotIn("import plataforma", fonte)


if __name__ == "__main__":
    unittest.main()
