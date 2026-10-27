# -*- coding: utf-8 -*-
"""Testes unitarios para sss_config, sss_logging e launchers (F0.2).

Segue rigorosamente AGENTS.md (§2.1, §3.3, §6, §7 e §8).
Python 3.6 estrito, sem fixtures com segredos reais (usa secrets.token_hex).
"""
import configparser
import io
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

from tests.support import _testenv
from sss.config import sss_config
from sss.platform import path_guard
from sss.config import sss_logging


class TestConfig(unittest.TestCase):
    """Bateria de testes para validacao tipada de config.ini e secrets.cfg."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="sss_test_")
        self.app_dir = _testenv.APP_DIR
        self.repo_root = self.app_dir  # CR-022a: a aplicacao e a raiz do repositorio
        self.example_ini = os.path.join(self.app_dir, "instance", "config.ini.example")

        # O substituto registra o que load_secrets entrega (sss_config importa sss.core.masking dentro da funcao).
        self.masked = []
        masking_stub = types.ModuleType("sss.core.masking")
        masking_stub.register_secret = self.masked.append
        patcher = mock.patch.dict(sys.modules, {"sss.core.masking": masking_stub})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    def _copy_and_edit_ini(self, changes=None, sections_to_remove=None, keys_to_remove=None):
        """Gera arquivo temporario config.ini a partir do exemplo com modificacoes."""
        cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
        with open(self.example_ini, "r", encoding="utf-8") as f:
            cp.read_file(f)

        if changes:
            for sec, keys in changes.items():
                if not cp.has_section(sec):
                    cp.add_section(sec)
                for k, v in keys.items():
                    cp.set(sec, k, str(v))

        if keys_to_remove:
            for sec, k in keys_to_remove:
                if cp.has_section(sec) and cp.has_option(sec, k):
                    cp.remove_option(sec, k)

        if sections_to_remove:
            for sec in sections_to_remove:
                if cp.has_section(sec):
                    cp.remove_section(sec)

        path_dest = os.path.join(self.tmp_dir, "config_modificado.ini")
        with open(path_dest, "w", encoding="utf-8") as f:
            cp.write(f)
        return path_dest

    def _create_temp_secrets(self, mode=0o600, include_oracle=True, tokens=None):
        """Cria secrets.cfg com valores pseudo-aleatorios (secrets.token_hex)."""
        if tokens is None:
            tokens = {
                "oracle_pwd": secrets.token_hex(16),
                "cookie_key": secrets.token_hex(32),
                "prod_pwd": secrets.token_hex(16),
                "hml_pwd": secrets.token_hex(16),
            }

        path = os.path.join(self.tmp_dir, "secrets.cfg")
        rows = []
        if include_oracle:
            rows.extend([
                "[oracle]",
                "password = %s" % tokens["oracle_pwd"],
                ""
            ])
        rows.extend([
            "[web]",
            "cookie_key = %s" % tokens["cookie_key"],
            "",
            "[environment:PRODUCAO]",
            "user = app_prod",
            "password = %s" % tokens["prod_pwd"],
            "",
            "[environment:HOMOLOGACAO]",
            "user = app_hml",
            "password = %s" % tokens["hml_pwd"],
            ""
        ])

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(rows))

        os.chmod(path, mode)
        return path, tokens

    def test_config_criticos_canonica_com_timeout_oracle(self):
        cfg = sss_config.load(self.example_ini)
        self.assertEqual(sss_config.critical_config(cfg),
                         "hb=10;fence=90;offline=180;call=30;kill=5;"
                         "misfire=RUN_ONCE;tol=300;horizonte=1461;envelhecimento=60")

    def test_config_valido(self):
        """Verifica carga do config.ini.example valido e integridade dos tipos."""
        cfg = sss_config.load(self.example_ini)

        # [app]
        self.assertEqual(cfg.app.sss_env, "DEV")
        self.assertFalse(hasattr(cfg.app, "data_backend"))

        # [oracle]
        self.assertEqual(cfg.oracle.user, "sss_web")
        self.assertEqual(cfg.oracle.dsn, "localhost:2424/servico_homolog")
        self.assertEqual(cfg.oracle.owner, "openrisow")
        self.assertEqual(cfg.oracle.table_prefix, "tbsss_")
        self.assertEqual(cfg.oracle.driver_mode, "thick")
        self.assertIsNone(cfg.oracle.oracle_client_lib_dir)
        self.assertEqual(cfg.oracle.call_timeout_ms, 30000)
        self.assertEqual(cfg.oracle.pool_min, 1)
        self.assertEqual(cfg.oracle.pool_max, 4)

        # [secrets]
        self.assertEqual(cfg.secrets.secrets_file, "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/instance/secrets.cfg")

        # [agent]
        self.assertEqual(cfg.agent.agent_id, "srv-linux-prod-01")
        self.assertEqual(cfg.agent.environments, ("PRODUCAO", "HOMOLOGACAO"))
        self.assertFalse(hasattr(cfg.agent, "base_script_dirs"))
        self.assertEqual(cfg.agent.work_dir, "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/work")
        self.assertFalse(hasattr(cfg.agent, "script_owner_uids"), "CR-011")
        self.assertEqual(cfg.agent.max_parallel_jobs, 4)
        self.assertEqual(cfg.agent.max_parallel_hard_limit, 32)
        self.assertEqual(cfg.agent.claim_batch_size, 20)
        self.assertEqual(cfg.agent.schedule_batch_size, 50)
        self.assertEqual(cfg.agent.orchestrator_interval_s, 10)
        self.assertEqual(cfg.agent.cancel_poll_interval_s, 2)
        self.assertEqual(cfg.agent.heartbeat_interval_s, 10)
        self.assertEqual(cfg.agent.fence_timeout_s, 90)
        self.assertEqual(cfg.agent.node_offline_timeout_s, 180)
        self.assertEqual(cfg.agent.kill_grace_s, 5)
        self.assertEqual(cfg.agent.script_timeout_s, 21600)
        self.assertEqual(cfg.agent.shutdown_mode, "TERMINATE")
        self.assertEqual(cfg.agent.shutdown_grace_s, 30)
        self.assertEqual(cfg.agent.misfire_policy, "RUN_ONCE")
        self.assertEqual(cfg.agent.misfire_tolerance_s, 300)
        self.assertEqual(cfg.agent.cron_horizon_days, 1461)
        self.assertEqual(cfg.agent.child_locale, "C.UTF-8")
        self.assertEqual(
            cfg.agent.env_passthrough,
            ("ORACLE_HOME", "TNS_ADMIN", "NLS_LANG", "LD_LIBRARY_PATH")
        )

        # [logging]
        self.assertEqual(cfg.logging.log_dir, "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs")
        self.assertEqual(cfg.logging.level, "INFO")
        self.assertEqual(cfg.logging.app_log_max_bytes, 10485760)
        self.assertEqual(cfg.logging.app_log_retention_days, 30)

        # [web]
        self.assertEqual(cfg.web.session_idle_timeout_s, 1800)
        self.assertEqual(cfg.web.login_max_attempts, 5)
        self.assertEqual(cfg.web.login_lockout_s, 900)
        self.assertEqual(cfg.web.log_poll_interval_s, 3)
        self.assertEqual(cfg.web.trusted_proxies, ())
        self.assertEqual(cfg.web.allowed_origins, ("http://127.0.0.1:18000",))
        self.assertEqual(cfg.web.input_upload_max_bytes, 52428800)

        # [retention]
        self.assertEqual(cfg.retention.ticket_retention_days, 180)
        self.assertEqual(cfg.retention.audit_retention_days, 730)
        self.assertEqual(cfg.retention.purge_batch_size, 1000)

        # Acesso via indexacao estilo dict
        self.assertEqual(cfg["app"]["sss_env"], "DEV")
        self.assertEqual(cfg["oracle"]["owner"], "openrisow")

        # Imutabilidade estrita
        with self.assertRaises(AttributeError):
            cfg.app.sss_env = "PROD"

    def test_chave_ausente(self):
        """Verifica rejeicao fail-fast quando chave obrigatoria esta ausente."""
        ini = self._copy_and_edit_ini(keys_to_remove=[("oracle", "dsn")])
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(ini)
        self.assertEqual(ctx.exception.section, "oracle")
        self.assertEqual(ctx.exception.key, "dsn")

    def test_secao_ausente(self):
        """Verifica rejeicao fail-fast quando secao inteira esta ausente."""
        ini = self._copy_and_edit_ini(sections_to_remove=["logging"])
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(ini)
        self.assertEqual(ctx.exception.section, "logging")

    def test_chave_desconhecida(self):
        """Verifica rejeicao de chave desconhecida no config.ini."""
        ini = self._copy_and_edit_ini(changes={"oracle": {"chave_fantasma": "123"}})
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(ini)
        self.assertEqual(ctx.exception.section, "oracle")
        self.assertEqual(ctx.exception.key, "chave_fantasma")

        # Chaves legadas driver e use_thick_mode removidas no F7.0
        for key_legacy, val in (("driver", "oracledb"), ("use_thick_mode", "true")):
            ini_leg = self._copy_and_edit_ini(changes={"oracle": {key_legacy: val}})
            with self.assertRaises(sss_config.ConfigError) as ctx_leg:
                sss_config.load(ini_leg)
            self.assertEqual(ctx_leg.exception.section, "oracle")
            self.assertEqual(ctx_leg.exception.key, key_legacy)

    def test_secao_desconhecida(self):
        """Verifica rejeicao de secao nao documentada no config.ini."""
        ini = self._copy_and_edit_ini(changes={"secao_estranha": {"foo": "bar"}})
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(ini)
        self.assertEqual(ctx.exception.section, "secao_estranha")

    def test_tipo_invalido(self):
        """Verifica rejeicao de valores com tipo incompativel."""
        # int invalido
        ini_int = self._copy_and_edit_ini(changes={"oracle": {"pool_min": "um"}})
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(ini_int)

        # driver_mode invalido
        ini_mode = self._copy_and_edit_ini(changes={"oracle": {"driver_mode": "invalido"}})
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(ini_mode)

        # enum invalido
        ini_enum = self._copy_and_edit_ini(changes={"app": {"sss_env": "STAGING"}})
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(ini_enum)

        # Chaves removidas no CR-011: recusadas com orientacao, nunca ignoradas.
        for key in ("script_owner_uids", "ambientes_exigem_hash"):
            ini = self._copy_and_edit_ini(changes={"agent": {key: "0"}})
            with self.assertRaises(sss_config.ConfigError) as ctx:
                sss_config.load(ini)
            self.assertIn("apague a linha %s" % key, str(ctx.exception))

        # CR-015a: chaves com nome em ingles; a antiga e recusada com o nome novo, nunca aceita.
        for (section, old), new in sss_config.RENAMED_KEYS.items():
            ini = self._copy_and_edit_ini(changes={section: {old: "1"}})
            with self.assertRaises(sss_config.ConfigError) as ctx:
                sss_config.load(ini)
            self.assertIn("%s passou a se chamar %s" % (old, new), str(ctx.exception))

        # CR-016b: a secao [retencao] antiga e recusada com o nome novo.
        ini = self._copy_and_edit_ini()
        with open(ini, encoding="utf-8") as f:
            text = f.read().replace("[retention]", "[retencao]")
        with open(ini, "w", encoding="utf-8") as f:
            f.write(text)
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(ini)
        self.assertIn("[retencao] passou a se chamar [retention]", str(ctx.exception))

    def test_fora_da_faixa(self):
        """Verifica rejeicao de valores fora das faixas minimas/maximas."""
        # pool_min < 1
        ini = self._copy_and_edit_ini(changes={"oracle": {"pool_min": "0"}})
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(ini)

        # max_parallel_jobs > 999
        ini2 = self._copy_and_edit_ini(changes={"agent": {"max_parallel_jobs": "1000"}})
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(ini2)

        # app_log_max_bytes < 1024
        ini3 = self._copy_and_edit_ini(changes={"logging": {"app_log_max_bytes": "500"}})
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(ini3)

        # app_log_retention_days < 1
        ini_ret_min = self._copy_and_edit_ini(changes={"logging": {"app_log_retention_days": "0"}})
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(ini_ret_min)

        # app_log_retention_days > 3650
        ini_ret_max = self._copy_and_edit_ini(changes={"logging": {"app_log_retention_days": "3651"}})
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(ini_ret_max)

        # app_log_backups sai no CR-005 e passa a ser recusada como desconhecida
        ini_old = self._copy_and_edit_ini(changes={"logging": {"app_log_backups": "10"}})
        with self.assertRaises(sss_config.ConfigError) as ctx_old:
            sss_config.load(ini_old)
        self.assertEqual(ctx_old.exception.key, "app_log_backups")

    def test_cada_invariante(self):
        """Verifica a validacao de cada invariante de integridade operacional."""
        # 1. max_parallel_jobs <= max_parallel_hard_limit
        ini1 = self._copy_and_edit_ini(changes={
            "agent": {"max_parallel_jobs": "33", "max_parallel_hard_limit": "32"}
        })
        with self.assertRaises(sss_config.ConfigError) as ctx1:
            sss_config.load(ini1)
        self.assertEqual(ctx1.exception.key, "max_parallel_jobs")

        # 2. fence_timeout_s * 2 <= node_offline_timeout_s
        ini2 = self._copy_and_edit_ini(changes={
            "agent": {"fence_timeout_s": "100", "node_offline_timeout_s": "180"}
        })
        with self.assertRaises(sss_config.ConfigError) as ctx2:
            sss_config.load(ini2)
        self.assertEqual(ctx2.exception.key, "fence_timeout_s")

        # 3. heartbeat_interval_s * 3 <= fence_timeout_s
        ini3 = self._copy_and_edit_ini(changes={
            "agent": {"heartbeat_interval_s": "31", "fence_timeout_s": "90"}
        })
        with self.assertRaises(sss_config.ConfigError) as ctx3:
            sss_config.load(ini3)
        self.assertEqual(ctx3.exception.key, "heartbeat_interval_s")

        # 4. pool_min <= pool_max
        ini4 = self._copy_and_edit_ini(changes={
            "oracle": {"pool_min": "5", "pool_max": "4"}
        })
        with self.assertRaises(sss_config.ConfigError) as ctx4:
            sss_config.load(ini4)
        self.assertEqual(ctx4.exception.key, "pool_min")

    def test_data_backend_removida(self):
        """F7.3: a aplicacao usa sempre o Oracle; a chave antiga e recusada com mensagem clara."""
        for value in ("FAKE", "ORACLE"):
            ini = self._copy_and_edit_ini(changes={"app": {"data_backend": value}})
            with self.assertRaises(sss_config.ConfigError) as ctx:
                sss_config.load(ini)
            self.assertEqual(ctx.exception.key, "data_backend")
            self.assertIn("apague a linha data_backend", str(ctx.exception))

    def test_prefixo_comeca_com_letra(self):
        """CR-003 P2: prefixo iniciado por digito ou _ geraria nome Oracle invalido."""
        for prefix in ("1x_", "_x", "9"):
            ini = self._copy_and_edit_ini(changes={"oracle": {"table_prefix": prefix}})
            with self.assertRaises(sss_config.ConfigError) as ctx:
                sss_config.load(ini)
            self.assertEqual(ctx.exception.key, "table_prefix", prefix)
        ini_ok = self._copy_and_edit_ini(changes={"oracle": {"table_prefix": "a1_"}})
        self.assertEqual(sss_config.load(ini_ok).oracle.table_prefix, "a1_")

    def test_pastas_base_recusadas(self):
        """CR-005 (README §12.1): base_script_dirs e a antiga base_script_dir sao chaves desconhecidas."""
        for key, value in (("base_script_dirs", "ROTINAS=/opt/automacoes/scripts"),
                             ("base_script_dir", "/opt/automacoes/scripts"),
                             ("script_owner_sids", "S-1-5-32-544")):
            ini = self._copy_and_edit_ini(changes={"agent": {key: value}})
            with self.assertRaises(sss_config.ConfigError, msg=key) as ctx:
                sss_config.load(ini)
            self.assertEqual(ctx.exception.key, key)
            self.assertIn("desconhecida", ctx.exception.reason)

    def test_login_max_tentativas_cabe_em_number_2(self):
        """CR-003 P2: tentativas_falha e NUMBER(2), entao o teto e 99."""
        ini_100 = self._copy_and_edit_ini(changes={"web": {"login_max_attempts": "100"}})
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(ini_100)
        self.assertEqual(ctx.exception.key, "login_max_attempts")
        ini_99 = self._copy_and_edit_ini(changes={"web": {"login_max_attempts": "99"}})
        self.assertEqual(sss_config.load(ini_99).web.login_max_attempts, 99)

    def _get_with_ini(self, ini, log_name="sss_web"):
        sss_config.reset_config_cache()
        self.addCleanup(sss_config.reset_config_cache)
        with mock.patch.object(sss_config, "default_config_path", return_value=ini):
            return sss_config.get_config(log_name)

    def _read_app_log(self, log_dir, log_name):
        """CR-005 D6: o CRITICAL inicial fica em log_dir/app/AAAA/MM/DD/HH/MI/<log_name>_<PID>.log."""
        expected = "%s_%d.log" % (log_name, os.getpid())
        found = []
        for root, _dirs, files in os.walk(log_dir):
            found.extend(os.path.join(root, a) for a in files)
        self.assertFalse(os.path.exists(os.path.join(log_dir, log_name + ".log")))
        self.assertEqual(len(found), 1, found)
        self.assertEqual(os.path.basename(found[0]), expected)
        parts = os.path.relpath(os.path.dirname(found[0]), log_dir).split(os.sep)
        self.assertEqual(parts[:2], ["internal", "app"])  # CR-009
        self.assertEqual(len(parts), 7)
        self.assertEqual(stat.S_IMODE(os.stat(found[0]).st_mode), 0o640)
        with open(found[0], encoding="utf-8") as f:
            return f.read()

    def test_configuracao_invalida_gera_critical_no_log(self):
        """CR-003 P2: CRITICAL com secao, chave e motivo no log da aplicacao quando log_dir e utilizavel."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        os.makedirs(log_dir)
        ini = self._copy_and_edit_ini(changes={"logging": {"log_dir": log_dir},
                                                       "web": {"login_max_attempts": "100"}})
        with self.assertRaises(sss_config.ConfigError):
            self._get_with_ini(ini)
        content = self._read_app_log(log_dir, "sss_web")
        self.assertIn(" CRITICAL ", content)
        self.assertIn("login_max_attempts", content)
        self.assertIn("[action=INICIO]", content)
        # Falha repetida no mesmo minuto e processo (nova requisicao) vai para o mesmo arquivo.
        with self.assertRaises(sss_config.ConfigError):
            self._get_with_ini(ini)
        self.assertEqual(self._read_app_log(log_dir, "sss_web").count(" CRITICAL "), 2)

    def test_configuracao_invalida_sem_log_dir_vai_para_stderr(self):
        """CR-003 P2: sem log_dir utilizavel, o CRITICAL vai para o stderr no mesmo formato."""
        ini = self._copy_and_edit_ini(changes={"logging": {"log_dir": os.path.join(self.tmp_dir, "nao", "existe")},
                                                       "oracle": {"table_prefix": "1x_"}})
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            with self.assertRaises(sss_config.ConfigError):
                self._get_with_ini(ini)
        self.assertIn(" CRITICAL ", err.getvalue())
        self.assertIn("table_prefix", err.getvalue())

    def test_segredos_invalidos_geram_critical_sem_valor(self):
        """CR-003 P2: falha em secrets.cfg vira CRITICAL sem nenhum valor de segredo."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        os.makedirs(log_dir)
        path, tokens = self._create_temp_secrets(mode=0o644)
        ini = self._copy_and_edit_ini(changes={"logging": {"log_dir": log_dir},
                                                       "secrets": {"secrets_file": path}})
        self._get_with_ini(ini)
        sss_config.reset_secrets_cache()
        self.addCleanup(sss_config.reset_secrets_cache)
        with self.assertRaises(sss_config.ConfigError):
            sss_config.get_secrets("sss_web")
        content = self._read_app_log(log_dir, "sss_web")
        self.assertIn(" CRITICAL ", content)
        for value in tokens.values():
            self.assertNotIn(value, content)

    def test_prefixo_de_9_caracteres(self):
        """Verifica restricao de regex de table_prefix (max 8 chars)."""
        ini_9 = self._copy_and_edit_ini(changes={
            "oracle": {"table_prefix": "tbsss_123"}  # 9 caracteres
        })
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(ini_9)
        self.assertEqual(ctx.exception.key, "table_prefix")

        # Teste com owner invalido (iniciando com digito)
        ini_owner = self._copy_and_edit_ini(changes={
            "oracle": {"owner": "1_invalido"}
        })
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(ini_owner)

        # Teste com agent_id contendo caractere proibido
        ini_agent = self._copy_and_edit_ini(changes={
            "agent": {"agent_id": "srv linux prod"}
        })
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(ini_agent)

        # init_db e seed sao atores reservados do sistema (CR-006, README §8.12)
        for reserved in ("init_db", "seed"):
            ini_res = self._copy_and_edit_ini(changes={"agent": {"agent_id": reserved}})
            with self.assertRaises(sss_config.ConfigError) as ctx_res:
                sss_config.load(ini_res)
            self.assertEqual(ctx_res.exception.key, "agent_id")
        ini_ok = self._copy_and_edit_ini(changes={"agent": {"agent_id": "seed01"}})
        self.assertEqual(sss_config.load(ini_ok).agent.agent_id, "seed01")

    def test_env_passthrough_com_ld_preload(self):
        """Verifica rejeicao de variaveis perigosas bloqueadas no passthrough."""
        ini_preload = self._copy_and_edit_ini(changes={
            "agent": {"env_passthrough": "ORACLE_HOME,LD_PRELOAD"}
        })
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(ini_preload)
        self.assertEqual(ctx.exception.key, "env_passthrough")
        self.assertIn("LD_PRELOAD", str(ctx.exception))

        # Teste com PYTHONPATH
        ini_py = self._copy_and_edit_ini(changes={
            "agent": {"env_passthrough": "PYTHONPATH"}
        })
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(ini_py)

    def test_secrets_modo_0644(self):
        """Verifica que secrets.cfg com permissoes inseguras (ex: 0644) e rejeitado."""
        path_sec, _ = self._create_temp_secrets(mode=0o644)
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load_secrets(path_sec)
        self.assertIn("permissoes inseguras", str(ctx.exception))

        # Corrige permissao para 0600 e valida sucesso
        os.chmod(path_sec, 0o600)
        secrets_value = sss_config.load_secrets(path_sec)
        self.assertIsNotNone(secrets_value)

    def test_repr_segredos_sem_valores(self):
        """Verifica que repr() e str() de Segredos nunca vazam credenciais."""
        path_sec, tokens = self._create_temp_secrets(mode=0o600)
        secrets_value = sss_config.load_secrets(path_sec)

        repr_str = repr(secrets_value)
        str_str = str(secrets_value)

        # Nenhum token pode aparecer em repr ou str
        for name_tok, value_tok in tokens.items():
            self.assertNotIn(
                value_tok, repr_str,
                "Token %s vazou no repr(segredos)!" % name_tok
            )
            self.assertNotIn(
                value_tok, str_str,
                "Token %s vazou no str(segredos)!" % name_tok
            )

        # Checagem nos sub-objetos
        self.assertNotIn(tokens["oracle_pwd"], repr(secrets_value.oracle))
        self.assertNotIn(tokens["cookie_key"], repr(secrets_value.web))
        self.assertNotIn(tokens["prod_pwd"], repr(secrets_value.get_environment("PRODUCAO")))

        # Os valores estao acessiveis pelas propriedades internas
        self.assertEqual(secrets_value.oracle_password, tokens["oracle_pwd"])
        self.assertEqual(secrets_value.cookie_key, tokens["cookie_key"])
        self.assertEqual(secrets_value.get_environment("PRODUCAO").password, tokens["prod_pwd"])

    def test_secrets_dev_fake_sem_oracle(self):
        """Verifica que [oracle] e opcional no secrets.cfg somente em DEV com FAKE."""
        path_sec, tokens = self._create_temp_secrets(mode=0o600, include_oracle=False)

        # Em DEV e FAKE -> sucesso
        seg_dev = sss_config.load_secrets(path_sec, sss_env="DEV", data_backend="FAKE")
        self.assertIsNone(seg_dev.oracle_password)
        self.assertEqual(seg_dev.cookie_key, tokens["cookie_key"])

        # Em PROD e ORACLE -> erro por [oracle] ausente
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load_secrets(path_sec, sss_env="PROD", data_backend="ORACLE")

    def test_segredos_carregados_sao_registrados_no_masking(self):
        """Regressao: todo segredo carregado e entregue a masking.register_secret (AGENTS §3.3)."""
        path_sec, tokens = self._create_temp_secrets(mode=0o600)
        sss_config.load_secrets(path_sec)
        self.assertEqual(sorted(self.masked), sorted(tokens.values()))

        del self.masked[:]
        path_sec, tokens = self._create_temp_secrets(mode=0o600, include_oracle=False)
        sss_config.load_secrets(path_sec, sss_env="DEV", data_backend="FAKE")
        self.assertEqual(sorted(self.masked),
                         sorted([tokens["cookie_key"], tokens["prod_pwd"], tokens["hml_pwd"]]))

    def test_carga_de_segredos_sem_masking_falha(self):
        """Regressao: sem masking.py a carga falha, em vez de seguir sem mascaramento."""
        path_sec, _ = self._create_temp_secrets(mode=0o600)
        with mock.patch.dict(sys.modules, {"sss.core.masking": None}):
            with self.assertRaises(ImportError):
                sss_config.load_secrets(path_sec)

    def _cfg_with_log_dir(self, log_dir):
        cfg = sss_config.load(self.example_ini)
        return cfg._replace(logging=cfg.logging._replace(log_dir=log_dir))

    def test_log_dir_criado_com_0750_independente_da_umask(self):
        """O chmod apos makedirs garante 0o750 mesmo com umask restritiva."""
        log_dir = os.path.join(self.tmp_dir, "logs_novos")
        umask_previous = os.umask(0o077)
        try:
            logger = sss_logging.configure("teste_umask", self._cfg_with_log_dir(log_dir))
        finally:
            os.umask(umask_previous)
        for h in list(logger.handlers):
            logger.removeHandler(h)
            h.close()
        self.assertEqual(stat.S_IMODE(os.stat(log_dir).st_mode), 0o750)

    def test_falha_no_chmod_do_log_dir_propaga(self):
        """Regressao: falha no chmod do log_dir aborta a configuracao (antes: except OSError: pass)."""
        log_dir = os.path.join(self.tmp_dir, "logs_chmod")
        with mock.patch("sss.config.sss_logging.os.chmod", side_effect=PermissionError(1, "Operation not permitted")):
            with self.assertRaises(OSError):
                sss_logging.configure("teste_chmod", self._cfg_with_log_dir(log_dir))

    def test_formato_log_readme_13(self):
        """Valida que o log gerado segue fielmente o formato do README §13."""
        cfg = sss_config.load(self.example_ini)
        # Substitui log_dir para diretorio temporario do teste
        cfg_tmp = cfg._replace(logging=cfg.logging._replace(log_dir=self.tmp_dir))

        logger = sss_logging.configure("teste_formato", cfg_tmp)
        logger.info("Mensagem padrao sem contexto explicito")

        adapter = sss_logging.get_adapter(logger, agent="srv-prod-01", ticket="9876", action="SPAWN")
        adapter.info("Processo filho instanciado com sucesso")

        log_path = logger.handlers[0].baseFilename
        self.assertTrue(os.path.isfile(log_path))
        self.assertIn(os.path.join(self.tmp_dir, "internal", "app"), log_path)

        with open(log_path, "r", encoding="utf-8") as f:
            rows = [line.strip() for line in f if line.strip()]

        self.assertGreaterEqual(len(rows), 2)

        # Regex estrita do formato README §13:
        # %(asctime)s %(levelname)s [pid=%(process)d] [agent=<id>] [ticket=<id|->] [action=<CLAIM|SPAWN|HB|...>] %(message)s
        # asctime: data ISO local com offset: YYYY-MM-DDTHH:MM:SS(.microseconds)?(Z|[+-]HH:MM)
        default = (
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)\s+"
            r"(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL)\s+"
            r"\[pid=\d+\]\s+\[agent=[^\]]+\]\s+\[ticket=[^\]]+\]\s+\[action=[^\]]+\]\s+.*$"
        )

        for line in rows:
            self.assertRegex(line, default, "Linha de log fora do padrao README §13: %s" % line)

        # Verifica campos da linha emitida pelo adapter
        line_adapter = rows[1]
        self.assertIn("[agent=srv-prod-01]", line_adapter)
        self.assertIn("[ticket=9876]", line_adapter)
        self.assertIn("[action=SPAWN]", line_adapter)
        self.assertIn("Processo filho instanciado com sucesso", line_adapter)

    def test_launchers_syntax_bash_n(self):
        """Verifica a sintaxe dos launchers bin/sss-web.sh e bin/sss-scheduler.sh."""
        web_sh = os.path.join(self.repo_root, "bin", "sss-web.sh")
        scheduler_sh = os.path.join(self.repo_root, "bin", "sss-scheduler.sh")

        self.assertTrue(os.path.isfile(web_sh), "Arquivo ausente: %s" % web_sh)
        self.assertTrue(os.path.isfile(scheduler_sh), "Arquivo ausente: %s" % scheduler_sh)

        res_web = subprocess.run(["bash", "-n", web_sh])
        self.assertEqual(res_web.returncode, 0, "bash -n falhou em sss-web.sh")

        res_sched = subprocess.run(["bash", "-n", scheduler_sh])
        self.assertEqual(res_sched.returncode, 0, "bash -n falhou em sss-scheduler.sh")

    @unittest.skipIf(os.geteuid() == 0, "o launcher recusa root antes de checar os argumentos")
    def test_launcher_web_recusa_comando_arbitrario(self):
        """CR-003 P10 (README §12.2): so o processo Python do SSS; nada de exec de comando arbitrario."""
        web_sh = os.path.join(self.repo_root, "bin", "sss-web.sh")
        # CR-021e2: so o run_web.py; web2py.py e qualquer outro script sao recusados.
        for args in (["/bin/sh", "-c", "id"], ["/usr/bin/python3", "outro.py"], ["python3", "web2py.py"]):
            res = subprocess.run(["bash", web_sh] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertEqual(res.returncode, 2, args)


if __name__ == "__main__":
    unittest.main()


class TestConfigCR007(unittest.TestCase):
    """CR-007 (README §4.1, §8.6, §8.9, §12.1): chaves novas, invariantes I3/I4 e segredos por papel."""

    setUp = TestConfig.setUp
    tearDown = TestConfig.tearDown
    _copy_and_edit_ini = TestConfig._copy_and_edit_ini
    _create_temp_secrets = TestConfig._create_temp_secrets

    def _load(self, **changes):
        return sss_config.load(self._copy_and_edit_ini(changes=changes))

    def _refusal(self, key_name, **changes):
        with self.assertRaises(sss_config.ConfigError) as ctx:
            self._load(**changes)
        self.assertEqual(ctx.exception.key, key_name, str(ctx.exception))
        return ctx.exception

    def test_padroes_das_chaves_novas(self):
        cfg = self._load()
        self.assertEqual(cfg.agent.exec_users, ())
        self.assertIsNone(cfg.agent.exec_work_dir)
        self.assertEqual(cfg.agent.queue_aging_min, 60)
        self.assertIsNone(cfg.retention.purge_user)

    def test_prefixo_so_minusculas_e_agent_id_purge_reservado(self):
        self._refusal("table_prefix", oracle={"table_prefix": "TBSSS_"})
        self._refusal("agent_id", agent={"agent_id": "purge"})
        self.assertEqual(self._load(agent={"agent_id": "purge01"}).agent.agent_id, "purge01")

    def test_faixas_novas(self):
        # CR-008, R-32: minimo de 1461 dias (cobre o 29/02).
        self._refusal("cron_horizon_days", agent={"cron_horizon_days": "1460"})
        self.assertEqual(self._load(agent={"cron_horizon_days": "1461"}).agent.cron_horizon_days, 1461)
        self.assertEqual(self._load().agent.log_dir_min_free_mb, 1024)
        self.assertEqual(self._load(agent={"log_dir_min_free_mb": "0"}).agent.log_dir_min_free_mb, 0)
        self._refusal("log_dir_min_free_mb", agent={"log_dir_min_free_mb": "-1"})
        self._refusal("max_log_size_bytes", logging={"max_log_size_bytes": str(64 * 1024 * 1024 + 1)})
        self._refusal("audit_retention_days", retention={"audit_retention_days": "364"})
        self._refusal("audit_retention_days", retention={"audit_retention_days": "400", "ticket_retention_days": "500"})
        self._refusal("queue_aging_min", agent={"queue_aging_min": "1441"})
        self.assertEqual(self._load(agent={"queue_aging_min": "0"}).agent.queue_aging_min, 0)

    def test_cr026_interpreters_ignorado_com_aviso(self):
        """CR-026 (D1): a linha antiga nao impede a subida; o aviso espera o log da aplicacao (026f)."""
        sss_config.pending_warnings()
        for key in ("interpreters", "interpretadores"):
            ini = self._copy_and_edit_ini(changes={"agent": {key: "PYTHON3=/usr/bin/python3,SH=/bin/sh"}})
            cfg = sss_config.load(ini)
            warnings = sss_config.pending_warnings()
            self.assertEqual(len(warnings), 1, warnings)
            self.assertIn("[agent] %s ignorada" % key, warnings[0])
            self.assertEqual(sss_config.pending_warnings(), [], "entregue uma vez so")
            self.assertFalse(hasattr(cfg.agent, "interpreters"))

    def _ini_text(self, text):
        path = os.path.join(self.tmp_dir, "proc.ini")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    _ORACLE = "[oracle]\nuser = sss_app\ndsn = x:1/y\nowner = own\ntable_prefix = tbsss_\n"

    def test_cr028_papel_pelo_arquivo_e_pastas_pelo_nome(self):
        """CR-028 (D4, D5, D6): web sem [agent], agente sem [web]; pastas de var/<nome>/; agent_id = nome."""
        web = sss_config.load(self._ini_text("[app]\nsss_env = PROD\nname = web0001\n" + self._ORACLE +
                                             "[web]\nallowed_origins = https://x\n"))
        var = sss_config.VAR_DIR
        self.assertEqual((web.app.role, web.app.name, web.logging.log_dir, web.agent.agent_id),
                         ("web", "web0001", os.path.join(var, "web0001", "logs"), None))
        self.assertEqual(web.agent.heartbeat_interval_s, 10, "o web usa os padroes do agente (fila, saude)")
        agent = sss_config.load(self._ini_text(
            "[app]\nsss_env = PROD\nname = agente0001\n" + self._ORACLE +
            "[agent]\nenvironments = PRODUCAO\nmax_parallel_jobs = 2\nexec_users = PRODUCAO=sssprd\n"
            "output_dir =\n[retention]\npurge_user = sss_purge\n"))
        base = os.path.join(var, "agente0001")
        self.assertEqual((agent.app.role, agent.agent.agent_id, agent.agent.work_dir, agent.logging.log_dir,
                          agent.agent.exec_work_dir, agent.agent.input_dir, agent.agent.script_work_dir,
                          agent.agent.script_base_dir, agent.agent.output_dir),
                         ("agent", "agente0001", os.path.join(base, "work"), os.path.join(base, "logs"),
                          os.path.join(var, "exec"), os.path.join(base, "input"),
                          os.path.join(base, "script_work"), sss_config.SCRIPTS_DIR, None),
                         "output_dir escrito vazio desliga a funcao")
        self.assertEqual(agent.secrets.secrets_file, os.path.join(self.tmp_dir, "secrets.cfg"))

    def test_cr028_validacoes_por_papel(self):
        # Web fora de DEV nao precisa de exec_users nem de purge_user; o agente precisa.
        sss_config.load(self._ini_text("[app]\nsss_env = PROD\nname = web0001\n" + self._ORACLE +
                                       "[web]\nallowed_origins = https://x\n"))
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(self._ini_text("[app]\nsss_env = PROD\nname = agente0001\n" + self._ORACLE +
                                           "[agent]\nenvironments = PRODUCAO\nmax_parallel_jobs = 2\n"))
        self.assertEqual(ctx.exception.key, "exec_users")
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(self._ini_text("[app]\nsss_env = DEV\nname = agente0001\n" + self._ORACLE +
                                           "[agent]\nagent_id = outro\nenvironments = A\nmax_parallel_jobs = 1\n"))
        self.assertEqual(ctx.exception.key, "agent_id", "com name, o agent_id e o proprio nome")
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(self._ini_text("[app]\nsss_env = DEV\nname = Agente 1\n" + self._ORACLE +
                                           "[web]\nallowed_origins = https://x\n"))
        # Sem name, o agente continua exigindo agent_id e work_dir; o web, log_dir.
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(self._ini_text("[app]\nsss_env = DEV\n" + self._ORACLE +
                                           "[web]\nallowed_origins = https://x\n"))
        self.assertEqual(ctx.exception.section, "logging")

    def test_cr028_env_label(self):
        """CR-028 (D12): a tela mostra o <TIPO> da pasta acima da raiz; fora do padrao, o sss_env."""
        for tipo, shown in (("PROD", "PROD"), ("hom", "HOM"), ("DEV", "DEV"), ("OUTRA", "DEV"), ("", "DEV")):
            self.assertEqual(sss_config.env_label("DEV", tipo.upper()), shown, tipo)
        self.assertEqual(sss_config.INSTALL_TYPE,
                         os.path.basename(os.path.dirname(sss_config.APP_DIR)).upper())

    def test_cr028_helper_path(self):
        """CR-028: helper ao lado da raiz por padrao, configuravel, nunca numa pasta do usuario de servico."""
        agent_ini = ("[app]\nsss_env = DEV\nname = agente0001\n" + self._ORACLE +
                     "[agent]\nenvironments = A\nmax_parallel_jobs = 1\n")
        self.assertEqual(sss_config.load(self._ini_text(agent_ini)).agent.helper_path,
                         os.path.join(os.path.dirname(sss_config.APP_DIR), "sss-root", "bin", "sss-helper"))
        self.assertEqual(sss_config.load(self._ini_text(agent_ini + "helper_path = /opt/sss/bin/sss-helper\n"))
                         .agent.helper_path, "/opt/sss/bin/sss-helper")
        web = sss_config.load(self._ini_text("[app]\nsss_env = DEV\nname = web0001\n" + self._ORACLE +
                                             "[web]\nallowed_origins = https://x\n"))
        self.assertIsNone(web.agent.helper_path)
        for value in ("bin/sss-helper", os.path.join(sss_config.APP_DIR, "bin", "sss-helper"),
                      os.path.join(sss_config.VAR_DIR, "exec", "sss-helper")):
            with self.assertRaises(sss_config.ConfigError) as ctx:
                sss_config.load(self._ini_text(agent_ini + "helper_path = %s\n" % value))
            self.assertEqual(ctx.exception.key, "helper_path", value)

    def test_cr028_caminho_pelo_nome_e_exemplos(self):
        self.assertEqual(sss_config.config_path(None, "agente0001"),
                         os.path.join(sss_config.APP_DIR, "instance", "agente0001", "config.ini"))
        self.assertEqual(sss_config.config_path("/x.ini", "agente0001"), "/x.ini")
        self.assertIsNone(sss_config.config_path(None, None))
        for bad in ("Agente", "a/b", "../x", ""):
            if bad:
                with self.assertRaises(sss_config.ConfigError):
                    sss_config.config_path(None, bad)
        for name, role in (("web0001", "web"), ("agente0001", "agent")):
            example = os.path.join(self.app_dir, "instance", "exemplos", name, "config.ini.example")
            text = open(example, encoding="utf-8").read().replace("sss_env = PROD", "sss_env = DEV")
            cfg = sss_config.load(self._ini_text(text))
            self.assertEqual((cfg.app.role, cfg.app.name), (role, name), example)

    def test_cr026_readme_tabela_igual_ao_schema(self):
        """CR-026: a tabela do README §12.1 lista toda chave do SCHEMA, com a obrigatoriedade e o padrao do codigo."""
        with open(os.path.join(self.app_dir, "README.md"), "r", encoding="utf-8") as f:
            text = f.read()
        section = text[text.index("### 12.1 `instance/config.ini`"):text.index("### 12.2 Launchers")]
        rows = {}
        for line in section.splitlines():
            m = re.match(r"^\| `\[(\w+)\]` \| (.+?) \| (sim|não|fora de DEV) \| (.+?) \| .+ \|$", line)
            if not m:
                continue
            keys = re.findall(r"`(\w+)`", m.group(2).split(" (")[0])
            defaults = [d.strip().strip("`") for d in m.group(4).split(",")] if len(keys) > 1 else [m.group(4)]
            for i, key in enumerate(keys):
                rows[(m.group(1), key)] = (m.group(3), defaults[i] if i < len(defaults) else None)
        expected = set((sec, k) for sec, fields in sss_config.SCHEMA.items() for k in fields)
        self.assertEqual(set(rows), expected)
        for (sec, key), (required, default) in rows.items():
            cdef = sss_config.SCHEMA[sec][key]
            self.assertEqual(required == "sim", cdef.required, (sec, key))
            if cdef.default not in (None, ()) and key != "secrets_file":
                self.assertEqual(default.strip("`"), str(cdef.default), (sec, key))

    def test_cr026_config_minimo_com_padroes(self):
        """CR-026 (D8, D9): sem os ajustes finos nem [secrets], valem os padroes do config.ini.example."""
        optional = [(sec, k) for sec, fields in sss_config.SCHEMA.items() for k, cdef in fields.items()
                    if not cdef.required]
        ini = self._copy_and_edit_ini(keys_to_remove=optional, sections_to_remove=["secrets"])
        with open(ini, "r", encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("call_timeout_ms", text)
        cfg = sss_config.load(ini)
        self.assertEqual(cfg.secrets.secrets_file, os.path.join(self.tmp_dir, "secrets.cfg"))
        expected = {("oracle", "call_timeout_ms"): 30000, ("oracle", "pool_min"): 1, ("oracle", "pool_max"): 4,
                    ("agent", "max_parallel_hard_limit"): 32, ("agent", "claim_batch_size"): 20,
                    ("agent", "schedule_batch_size"): 50, ("agent", "orchestrator_interval_s"): 10,
                    ("agent", "cancel_poll_interval_s"): 2, ("agent", "heartbeat_interval_s"): 10,
                    ("agent", "fence_timeout_s"): 90, ("agent", "node_offline_timeout_s"): 180,
                    ("agent", "kill_grace_s"): 5, ("agent", "script_timeout_s"): 21600,
                    ("agent", "shutdown_mode"): "TERMINATE", ("agent", "shutdown_grace_s"): 30,
                    ("agent", "misfire_policy"): "RUN_ONCE", ("agent", "misfire_tolerance_s"): 300,
                    ("agent", "cron_horizon_days"): 1461, ("agent", "child_locale"): "C.UTF-8",
                    ("logging", "level"): "INFO", ("logging", "app_log_max_bytes"): 10485760,
                    ("logging", "app_log_retention_days"): 30, ("logging", "max_log_size_bytes"): 5242880,
                    ("logging", "max_local_log_size_bytes"): 52428800, ("logging", "local_log_retention_days"): 30,
                    ("web", "session_idle_timeout_s"): 1800, ("web", "login_max_attempts"): 5,
                    ("web", "login_lockout_s"): 900, ("web", "log_poll_interval_s"): 3,
                    ("retention", "ticket_retention_days"): 180, ("retention", "audit_retention_days"): 730,
                    ("retention", "purge_batch_size"): 1000}
        for (sec, key), value in expected.items():
            self.assertEqual(getattr(getattr(cfg, sec), key), value, key)
        # Os obrigatorios continuam: sss_env, oracle (user, dsn, owner, table_prefix), agent_id, environments,
        # work_dir, max_parallel_jobs, log_dir e allowed_origins.
        required = sorted((sec, k) for sec, fields in sss_config.SCHEMA.items() for k, cdef in fields.items()
                          if cdef.required)
        self.assertEqual(required, sorted([
            ("app", "sss_env"), ("oracle", "user"), ("oracle", "dsn"), ("oracle", "owner"),
            ("oracle", "table_prefix"), ("agent", "agent_id"), ("agent", "environments"), ("agent", "work_dir"),
            ("agent", "max_parallel_jobs"), ("logging", "log_dir"), ("web", "allowed_origins")]))

    def test_pasta_de_saida(self):
        # CR-012 (README §8.13): opcional, com limites e sem sobrepor as pastas do SSS.
        cfg = self._load()
        self.assertIsNone(cfg.agent.output_dir)
        self.assertEqual((cfg.agent.output_max_bytes, cfg.agent.output_max_files), (20971520, 1000))
        self.assertEqual(cfg.logging.output_retention_days, 7)
        base = os.path.dirname(cfg.agent.work_dir)
        ok = self._load(agent={"output_dir": os.path.join(base, "saida_teste")})
        self.assertEqual(ok.agent.output_dir, os.path.join(base, "saida_teste"))
        self._refusal("output_dir", agent={"output_dir": "relativa/output"})
        self._refusal("output_dir", agent={"output_dir": os.path.join(cfg.agent.work_dir, "output")})
        self._refusal("output_dir", agent={"output_dir": os.path.join(cfg.logging.log_dir, "output")})
        self._refusal("output_dir", agent={"output_dir": os.path.dirname(cfg.logging.log_dir)})
        self._refusal("output_dir", agent={"output_dir": os.path.join(base, "s"),
                                         "exec_work_dir": os.path.join(base, "s", "exec")})
        # CR-014 (README §8.14): input_dir opcional, sem sobrepor as pastas do SSS nem a de saida.
        self.assertIsNone(cfg.agent.input_dir)
        ok = self._load(agent={"input_dir": os.path.join(base, "entrada_teste")})
        self.assertEqual(ok.agent.input_dir, os.path.join(base, "entrada_teste"))
        self._refusal("input_dir", agent={"input_dir": "relativa/input"})
        self._refusal("input_dir", agent={"input_dir": os.path.join(cfg.agent.work_dir, "input")})
        self._refusal("input_dir", agent={"input_dir": os.path.join(cfg.logging.log_dir, "input")})
        self._refusal("input_dir", agent={"input_dir": os.path.dirname(cfg.logging.log_dir)})
        self._refusal("input_dir", agent={"input_dir": os.path.join(base, "s", "input"),
                                           "output_dir": os.path.join(base, "s")})
        # CR-019 (README §8.15): script_work_dir opcional, sem sobrepor as pastas do SSS, a de saida nem a de entrada.
        self.assertIsNone(cfg.agent.script_work_dir)
        self.assertEqual(cfg.logging.script_work_retention_days, 7)
        ok = self._load(agent={"script_work_dir": os.path.join(base, "trabalho_teste")})
        self.assertEqual(ok.agent.script_work_dir, os.path.join(base, "trabalho_teste"))
        self._refusal("script_work_dir", agent={"script_work_dir": "relativa/work"})
        self._refusal("script_work_dir", agent={"script_work_dir": os.path.join(cfg.agent.work_dir, "sw")})
        self._refusal("script_work_dir", agent={"script_work_dir": os.path.join(cfg.logging.log_dir, "sw")})
        self._refusal("script_work_dir", agent={"script_work_dir": os.path.dirname(cfg.logging.log_dir)})
        self._refusal("script_work_dir", agent={"script_work_dir": os.path.join(base, "s", "sw"),
                                                 "exec_work_dir": os.path.join(base, "s")})
        self._refusal("script_work_dir", agent={"script_work_dir": os.path.join(base, "s", "sw"),
                                                 "output_dir": os.path.join(base, "s")})
        self._refusal("script_work_dir", agent={"script_work_dir": os.path.join(base, "s"),
                                                 "input_dir": os.path.join(base, "s", "input")})
        for v in ("0", "366"):
            self._refusal("script_work_retention_days", logging={"script_work_retention_days": v})
        # CR-023 (README §8.5): script_base_dir opcional; a pasta pode nao existir (so aviso na subida).
        self.assertIsNone(cfg.agent.script_base_dir)
        ok = self._load(agent={"script_base_dir": "/opt/sss_teste/base_inexistente"})
        self.assertEqual(ok.agent.script_base_dir, "/opt/sss_teste/base_inexistente")
        app_dev = os.path.join(path_guard.APP_DIR, "dev", "scripts")
        self.assertEqual(self._load(agent={"script_base_dir": app_dev}).agent.script_base_dir, app_dev)
        # Como as demais pastas, o caminho e normalizado na carga.
        self.assertEqual(self._load(agent={"script_base_dir": "/opt//sss_teste/"}).agent.script_base_dir,
                         "/opt/sss_teste")
        for value in ("relativa/scripts", "/etc/sss",
                      os.path.join(cfg.agent.work_dir, "s"), os.path.join(cfg.logging.log_dir, "s"),
                      os.path.join(path_guard.APP_DIR, "src")):
            self._refusal("script_base_dir", agent={"script_base_dir": value})
        # CR-020e: retencao dos envios da tela de Entrada.
        self.assertEqual(self._load().retention.input_retention_days, 30)
        for v in ("0", "3651"):
            self._refusal("input_retention_days", retention={"input_retention_days": v})
        # CR-020d: limite do envio pela tela de Entrada.
        for v in ("1048575", "209715201"):
            self._refusal("input_upload_max_bytes", web={"input_upload_max_bytes": v})
        self.assertEqual(self._load(web={"input_upload_max_bytes": "1048576"}).web.input_upload_max_bytes, 1048576)
        # CR-021e (D5): servidor web proprio.
        web_cfg = self._load().web
        self.assertEqual((web_cfg.max_threads, web_cfg.socket_timeout_s), (16, 30))
        for key, bad, good in (("max_threads", ("0", "257"), ("1", "256")),
                               ("socket_timeout_s", ("4", "301"), ("5", "300"))):
            for v in bad:
                self._refusal(key, web={key: v})
            for v in good:
                self.assertEqual(getattr(self._load(web={key: v}).web, key), int(v))
        self.assertEqual(self._load(logging={"script_work_retention_days": "30"}).logging.script_work_retention_days, 30)
        for key, bad, good in (("output_max_bytes", ("1048575", "209715201"), ("1048576", "209715200")),
                                   ("output_max_files", ("0", "10001"), ("1", "10000"))):
            for v in bad:
                self._refusal(key, agent={key: v})
            for v in good:
                self.assertEqual(getattr(self._load(agent={key: v}).agent, key), int(v))
        self._refusal("output_retention_days", logging={"output_retention_days": "0"})
        self._refusal("output_retention_days", logging={"output_retention_days": "366"})

    def test_invariantes_i3_e_i4(self):
        # I3: heartbeat + 2*call <= fence (10 + 2*41 = 92 > 90).
        self._refusal("fence_timeout_s", oracle={"call_timeout_ms": "41000"})
        # I4: fence + call + kill + 2 <= offline (90 + 30 + 60 + 2 = 182 > 180).
        self._refusal("node_offline_timeout_s", agent={"kill_grace_s": "60"})
        self.assertEqual(sss_config.call_timeout_s(30001), 31)
        self._load()  # o exemplo atende I3 = 70 <= 90 e I4 = 127 <= 180

    def test_usuarios_execucao_e_exec_work_dir(self):
        cfg = self._load(agent={"exec_users": "PRODUCAO=sssprd, HOMOLOGACAO=ssshml"})
        self.assertEqual(cfg.agent.exec_users, (("PRODUCAO", "sssprd"), ("HOMOLOGACAO", "ssshml")))
        self._refusal("exec_users", agent={"exec_users": "PRODUCAO=root"})
        self._refusal("exec_users", agent={"exec_users": "OUTRO=sssx"})
        self._refusal("exec_users", agent={"exec_users": "PRODUCAO"})
        self._refusal("exec_users", agent={"exec_users": "PRODUCAO=a,PRODUCAO=b"})
        # Fora de DEV: todo ambiente atendido precisa de usuario e exec_work_dir e obrigatoria.
        base = {"sss_env": "HML"}
        ret = {"purge_user": "sss_purge"}
        self._refusal("exec_users", app=base, retention=ret, agent={"exec_users": "PRODUCAO=sssprd"})
        self._refusal("exec_work_dir", app=base, retention=ret,
                     agent={"exec_users": "PRODUCAO=sssprd,HOMOLOGACAO=ssshml"})
        self._refusal("exec_work_dir", app=base, retention=ret,
                     agent={"exec_users": "PRODUCAO=sssprd,HOMOLOGACAO=ssshml",
                            "exec_work_dir": "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/work/exec"})
        cfg = self._load(app=base, retention=ret, agent={"exec_users": "PRODUCAO=sssprd,HOMOLOGACAO=ssshml",
                                                            "exec_work_dir": "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/exec"})
        self.assertEqual(cfg.agent.exec_work_dir, "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/exec")

    def test_purge_user(self):
        """Vazio em DEV = purge desligado; fora de DEV e obrigatorio; nunca igual a conta ou ao owner."""
        self.assertFalse(self._load().retention.purge_user)
        self._refusal("purge_user", retention={"purge_user": "SSS_WEB"})
        self._refusal("purge_user", retention={"purge_user": "openrisow"})
        self.assertEqual(self._load(retention={"purge_user": "sss_purge"}).retention.purge_user, "sss_purge")
        agent = {"exec_users": "PRODUCAO=sssprd,HOMOLOGACAO=ssshml",
                 "exec_work_dir": "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/exec"}
        self._refusal("purge_user", app={"sss_env": "HML"}, agent=agent)

    def test_cr008_user_diferente_do_owner_fora_de_dev(self):
        ret = {"purge_user": "sss_purge"}
        agent = {"exec_users": "PRODUCAO=sssprd,HOMOLOGACAO=ssshml", "exec_work_dir": "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/exec"}
        self._refusal("user", app={"sss_env": "HML"}, retention=ret, agent=agent,
                     oracle={"user": "OPENRISOW"})
        cfg = self._load(app={"sss_env": "DEV"}, retention=ret,
                             oracle={"user": "openrisow"})
        self.assertEqual(cfg.oracle.user, "openrisow")

    def test_cr008_sessao_max_horas(self):
        self.assertEqual(self._load().web.session_max_hours, 12)
        self.assertEqual(self._load(web={"session_max_hours": "168"}).web.session_max_hours, 168)
        for value in ("0", "169", "x"):
            self._refusal("session_max_hours", web={"session_max_hours": value})

    def test_env_passthrough_lista_de_bloqueio_e_chaves_fixas(self):
        for var in ("BASH_FUNC_x%%", "LD_DEBUG", "MALLOC_ARENA_MAX", "GLIBC_TUNABLES", "PS4", "PATH", "LC_ALL",
                    "SSS_TICKET_ID", "PYTHONIOENCODING", "PADRAO_VALOR_RUN_CONEXAO_BD", "lang"):
            self._refusal("env_passthrough", agent={"env_passthrough": "ORACLE_HOME," + var})
        cfg = self._load(agent={"env_passthrough": "ORACLE_HOME,LD_LIBRARY_PATH,NLS_LANG,TNS_ADMIN"})
        self.assertIn("LD_LIBRARY_PATH", cfg.agent.env_passthrough)

    def test_ambientes_atendidos_cabem_na_coluna(self):
        names = ",".join("AMBIENTE_%04d_XXXXXXXXXXXXX" % i for i in range(40))
        self._refusal("environments", agent={"environments": names})

    def _secrets(self, sections):
        path = os.path.join(self.tmp_dir, "secrets_papel.cfg")
        with open(path, "w", encoding="utf-8") as f:
            for name, keys in sections:
                f.write("[%s]\n" % name)
                for k, v in keys.items():
                    f.write("%s = %s\n" % (k, v))
        os.chmod(path, 0o600)
        return path

    def test_cr016b_secao_ambiente_antiga_recusada(self):
        old = [("oracle", {"password": "senha-agt-123"}), ("ambiente:PRODUCAO", {"user": "app", "password": "s-123"})]
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load_secrets(self._secrets(old), sss_env="DEV", data_backend="ORACLE", role="agent")
        self.assertIn("[ambiente:PRODUCAO] passou a se chamar [environment:PRODUCAO]", str(ctx.exception))
        self.assertNotIn("s-123", str(ctx.exception))

    def test_segredos_por_papel(self):
        web = [("oracle", {"password": "senha-web-123"}), ("web", {"cookie_key": "chave-cookie-123"})]
        agent = [("oracle", {"password": "senha-agt-123"}), ("purge", {"password": "senha-prg-123"}),
                  ("environment:PRODUCAO", {"user": "app", "password": "senha-amb-123"})]
        seg = sss_config.load_secrets(self._secrets(agent), sss_env="PROD", data_backend="ORACLE", role="agent")
        self.assertIsNone(seg.cookie_key)
        self.assertEqual(seg.purge_password, "senha-prg-123")
        self.assertIn("senha-prg-123", self.masked)
        self.assertNotIn("senha-prg-123", repr(seg))
        # Secao de outro papel: recusada em HML/PROD, so WARN em DEV.
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load_secrets(self._secrets(agent + [("web", {"cookie_key": "x" * 20})]),
                                         sss_env="PROD", data_backend="ORACLE", role="agent")
        for extra in (("purge", {"password": "senha-prg-123"}), ("environment:PRODUCAO", {"user": "a", "password": "b"})):
            with self.assertRaises(sss_config.ConfigError):
                sss_config.load_secrets(self._secrets(web + [extra]), sss_env="HML", data_backend="ORACLE")
            with self.assertLogs("sss_config", level="WARNING"):
                sss_config.load_secrets(self._secrets(web + [extra]), sss_env="DEV", data_backend="ORACLE")
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load_secrets(self._secrets(web), role="agente_x")

        # Papel monitor (CR-008, E3):
        monitor = [("monitor", {"user": "sss_monitor", "password": "senha-mon-123"})]
        seg_mon = sss_config.load_secrets(self._secrets(monitor), sss_env="PROD", data_backend="ORACLE", role="monitor")
        self.assertEqual(seg_mon.monitor_user, "sss_monitor")
        self.assertEqual(seg_mon.monitor_password, "senha-mon-123")
        self.assertIn("senha-mon-123", self.masked)
        self.assertNotIn("senha-mon-123", repr(seg_mon))
        # F9.1b (README §4.1): no servidor do agente, as secoes dos outros papeis sao ignoradas, sem masking.
        others = [("oracle", {"password": "senha-agt-999"}), ("purge", {"password": "senha-prg-999"}),
                  ("environment:PRODUCAO", {"user": "app", "password": "senha-amb-999"})]
        seg_mon = sss_config.load_secrets(self._secrets(monitor + others), sss_env="PROD",
                                               data_backend="ORACLE", role="monitor")
        self.assertEqual((seg_mon.monitor_user, seg_mon.oracle_password, seg_mon.environments), ("sss_monitor", None, {}))
        for value in ("senha-agt-999", "senha-prg-999", "senha-amb-999"):
            self.assertNotIn(value, self.masked)
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load_secrets(self._secrets(monitor + [("web", {"cookie_key": "k" * 40})]),
                                         sss_env="PROD", data_backend="ORACLE", role="monitor")
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load_secrets(self._secrets([("oracle", {"password": "x"})]),
                                         sss_env="PROD", data_backend="ORACLE", role="monitor")

    def test_segredos_do_agente_cobrem_os_ambientes(self):
        cfg = self._load(app={"sss_env": "HML"}, retention={"purge_user": "sss_purge"},
                             agent={"exec_users": "PRODUCAO=sssprd,HOMOLOGACAO=ssshml",
                                    "exec_work_dir": "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/exec"})
        only_prod = [("oracle", {"password": "senha-agt-123"}),
                   ("environment:PRODUCAO", {"user": "app", "password": "senha-amb-123"})]
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load_secrets(self._secrets(only_prod), cfg=cfg, role="agent")
        self.assertIn("HOMOLOGACAO", str(ctx.exception))

    def test_codificacao_utf8_obrigatoria(self):
        with mock.patch.object(sss_config.sys, "getfilesystemencoding", return_value="ascii"):
            with self.assertRaises(sss_config.ConfigError) as ctx:
                sss_config.check_encoding()
        self.assertIn("UTF-8", str(ctx.exception))
        for code in ("utf-8", "UTF8"):
            with mock.patch.object(sss_config.sys, "getfilesystemencoding", return_value=code):
                sss_config.check_encoding()
