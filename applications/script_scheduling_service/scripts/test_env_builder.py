# -*- coding: utf-8 -*-
"""Testes do env_builder (README §8.6, AGENTS §7.4; CR-007 R-17/R-32; CR-008 R-36): ambiente exato do filho
POSIX, sem heranca de os.environ, passthrough, bloqueio, omissao da conexao e mascaramento."""
import _testenv  # noqa: F401

import collections
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
            "SSS_TICKET_ID": "41", "SSS_AMBIENTE": "PRODUCAO", "SSS_AGENTE_ID": "srv-01",
            "SSS_SCRIPT_DIR": "/opt/automacoes/scripts/faturamento",
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
