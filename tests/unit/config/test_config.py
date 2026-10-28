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
        # CR-032 (D4): um modelo por processo, so para os testes.
        self.example_ini = os.path.join(self.app_dir, "tests", "support", "agente0001", "config.ini.example")
        self.example_web = os.path.join(self.app_dir, "tests", "support", "web0001", "config.ini.example")

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
        """Gera <tmp>/<nome>/config.ini a partir do modelo do agente ou, quando so [web] muda, do web
        (CR-032, D4: sem formato unico). O secrets.cfg compartilhado fica em <tmp>/ (D14)."""
        web = bool(changes) and "web" in changes and "agent" not in changes
        cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
        with open(self.example_web if web else self.example_ini, "r", encoding="utf-8") as f:
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

        folder = os.path.join(self.tmp_dir, "web0001" if web else "agente0001")
        os.makedirs(folder, exist_ok=True)
        path_dest = os.path.join(folder, "config.ini")
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
                         "call=30;misfire=RUN_ONCE")

    def test_config_valido(self):
        """Verifica carga do config.ini.example valido e integridade dos tipos."""
        cfg = sss_config.load(self.example_ini)

        # [app]
        self.assertFalse(hasattr(cfg.app, "sss_env"), "CR-032 (D11): sem sss_env")
        self.assertFalse(hasattr(cfg.app, "data_backend"))

        # [oracle]
        self.assertEqual(cfg.oracle.user, "sss_agente")
        self.assertEqual(cfg.oracle.dsn, "localhost:2424/servico_homolog")
        self.assertEqual(cfg.oracle.owner, "openrisow")
        self.assertEqual(cfg.oracle.table_prefix, "tbsss_")
        self.assertEqual(cfg.oracle.driver_mode, "thick")
        self.assertFalse(hasattr(cfg.oracle, "oracle_client_lib_dir"), "CR-032 (D1)")
        self.assertEqual(cfg.oracle.call_timeout_ms, 30000)
        self.assertEqual(cfg.oracle.pool_min, 1)
        self.assertEqual(cfg.oracle.pool_max, 4)

        # [secrets]
        self.assertEqual(cfg.secrets.secrets_file, os.path.join(self.app_dir, "tests", "support", "secrets.cfg"))

        # [agent]
        # CR-032 (D4): agent_id, work_dir e log_dir saem sempre do name.
        self.assertEqual((cfg.app.name, cfg.app.role, cfg.agent.agent_id), ("agente0001", "agent", "agente0001"))
        self.assertEqual(cfg.agent.environments, ("PRODUCAO", "HOMOLOGACAO"))
        self.assertFalse(hasattr(cfg.agent, "base_script_dirs"))
        self.assertEqual(cfg.agent.work_dir, os.path.join(sss_config.VAR_DIR, "agente0001", "work"))
        self.assertFalse(hasattr(cfg.agent, "script_owner_uids"), "CR-011")
        self.assertEqual(cfg.agent.max_parallel_jobs, 4)
        self.assertFalse(hasattr(cfg.agent, "max_parallel_hard_limit"), "CR-032 (D1)")
        self.assertFalse(hasattr(cfg.agent, "claim_batch_size"), "CR-032 (D1)")
        self.assertEqual(cfg.agent.schedule_batch_size, 50)
        self.assertEqual(cfg.agent.orchestrator_interval_s, 10)
        self.assertEqual(cfg.agent.cancel_poll_interval_s, 2)
        self.assertEqual(cfg.agent.heartbeat_interval_s, 10)
        self.assertEqual(cfg.agent.fence_timeout_s, 90)
        self.assertEqual(cfg.agent.node_offline_timeout_s, 180)
        self.assertEqual(cfg.agent.kill_grace_s, 5)
        self.assertEqual(cfg.agent.script_timeout_s, 604800)
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
        self.assertEqual(cfg.logging.log_dir, os.path.join(sss_config.VAR_DIR, "agente0001", "logs"))
        self.assertEqual(cfg.logging.level, "INFO")
        self.assertEqual(cfg.logging.app_log_max_bytes, 10485760)

        # [web]
        self.assertEqual(cfg.web.session_idle_timeout_s, 1800)
        self.assertEqual(cfg.web.login_max_attempts, 5)
        self.assertEqual(cfg.web.login_lockout_s, 900)
        self.assertEqual(cfg.web.log_poll_interval_s, 3)
        self.assertEqual(cfg.web.trusted_proxies, ())
        self.assertEqual(cfg.web.input_upload_max_bytes, 52428800)
        web = sss_config.load(self.example_web)
        self.assertEqual((web.app.role, web.web.allowed_origins, web.agent.agent_id),
                         ("web", ("http://127.0.0.1:18000",), None))

        # CR-030: sem [retention]
        self.assertFalse(hasattr(cfg, "retention"))

        # Acesso via indexacao estilo dict
        self.assertEqual(cfg["app"]["name"], "agente0001")
        self.assertEqual(cfg["oracle"]["owner"], "openrisow")

        # Imutabilidade estrita
        with self.assertRaises(AttributeError):
            cfg.app.name = "outro"

    def test_chave_ausente(self):
        """Verifica rejeicao fail-fast quando chave obrigatoria esta ausente."""
        ini = self._copy_and_edit_ini(keys_to_remove=[("oracle", "dsn")])
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(ini)
        self.assertEqual(ctx.exception.section, "oracle")
        self.assertEqual(ctx.exception.key, "dsn")

    def test_secao_ausente(self):
        """Verifica rejeicao fail-fast quando secao inteira esta ausente."""
        ini = self._copy_and_edit_ini(sections_to_remove=["oracle"])
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(ini)
        self.assertEqual(ctx.exception.section, "oracle")
        # CR-032 (D4): sem [web] nem [agent] (ou com os dois) nao ha processo.
        for remove in (["agent"],):
            with self.assertRaises(sss_config.ConfigError) as ctx:
                sss_config.load(self._copy_and_edit_ini(sections_to_remove=remove))
            self.assertIn("precisa ser de um processo", str(ctx.exception))
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(self._copy_and_edit_ini(changes={"agent": {"environments": "A"},
                                                             "web": {"allowed_origins": "http://x"}}))

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
        ini_int = self._copy_and_edit_ini(changes={"oracle": {"call_timeout_ms": "um"}})
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(ini_int)

        # driver_mode invalido
        ini_mode = self._copy_and_edit_ini(changes={"oracle": {"driver_mode": "invalido"}})
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(ini_mode)

        # enum invalido
        ini_enum = self._copy_and_edit_ini(changes={"agent": {"misfire_policy": "TALVEZ"}})
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

        # CR-030: [retencao] e [retention] sao ignoradas com aviso (o purge saiu).
        ini = self._copy_and_edit_ini()
        with open(ini, "a", encoding="utf-8") as f:
            f.write("\n[retencao]\npurge_user = x\n")
        sss_config.pending_warnings()
        sss_config.load(ini)
        self.assertTrue(any("[retencao] purge_user ignorada" in w for w in sss_config.pending_warnings()))

    def test_fora_da_faixa(self):
        """Verifica rejeicao de valores fora das faixas minimas/maximas."""
        # call_timeout_ms < 1
        ini = self._copy_and_edit_ini(changes={"oracle": {"call_timeout_ms": "0"}})
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

        # app_log_backups sai no CR-005 e passa a ser recusada como desconhecida
        ini_old = self._copy_and_edit_ini(changes={"logging": {"app_log_backups": "10"}})
        with self.assertRaises(sss_config.ConfigError) as ctx_old:
            sss_config.load(ini_old)
        self.assertEqual(ctx_old.exception.key, "app_log_backups")

    def test_cada_invariante(self):
        """CR-032 (D1, D2, D3): os tempos de saude, o teto e o pool sao fixos; as linhas antigas viram aviso
        e o valor fixo vale."""
        sss_config.pending_warnings()
        ini = self._copy_and_edit_ini(changes={
            "agent": {"max_parallel_hard_limit": "2", "fence_timeout_s": "100", "heartbeat_interval_s": "31",
                      "claim_batch_size": "1", "kill_grace_s": "60", "shutdown_mode": "DRAIN"},
            "oracle": {"pool_min": "5", "pool_max": "4", "oracle_client_lib_dir": "/opt/ic"}})
        cfg = sss_config.load(ini)
        web = sss_config.load(self._copy_and_edit_ini(changes={"web": {"max_threads": "1"}}))
        self.assertEqual((cfg.agent.fence_timeout_s, cfg.agent.heartbeat_interval_s, cfg.agent.kill_grace_s,
                          cfg.agent.shutdown_mode, cfg.oracle.pool_min, cfg.oracle.pool_max, web.web.max_threads),
                         (90, 10, 5, "TERMINATE", 1, 4, 16))
        warnings = "\n".join(sss_config.pending_warnings())
        for key in ("[agent] max_parallel_hard_limit", "[agent] fence_timeout_s", "[oracle] pool_min",
                    "[oracle] oracle_client_lib_dir", "[web] max_threads", "[agent] shutdown_mode"):
            self.assertIn(key, warnings)
        self.assertIn("valor fixo no codigo desde o CR-032 (90)", warnings)
        self.assertIn("sem efeito, retirada no CR-032", warnings)

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

    def _patch_var_dir(self, folder=None):
        """var/ do processo na pasta temporaria: o log nunca vai para o var/ real do DEV (CR-032, D4)."""
        patcher = mock.patch.object(sss_config, "VAR_DIR", folder or self.tmp_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _get_with_ini(self, ini, log_name="sss_web"):
        sss_config.reset_config_cache()
        self.addCleanup(sss_config.reset_config_cache)
        return sss_config.get_config(log_name, path=ini)

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
        # CR-032 (D4): o log_dir e var/<name>/logs; o VAR_DIR vai para a pasta temporaria.
        self._patch_var_dir()
        log_dir = os.path.join(self.tmp_dir, "web0001", "logs")
        os.makedirs(log_dir)
        ini = self._copy_and_edit_ini(changes={"web": {"login_max_attempts": "100"}})
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
        self._patch_var_dir(os.path.join(self.tmp_dir, "nao", "existe"))
        ini = self._copy_and_edit_ini(changes={"oracle": {"table_prefix": "1x_"}})
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            with self.assertRaises(sss_config.ConfigError):
                self._get_with_ini(ini)
        self.assertIn(" CRITICAL ", err.getvalue())
        self.assertIn("table_prefix", err.getvalue())

    def test_segredos_invalidos_geram_critical_sem_valor(self):
        """CR-003 P2: falha em secrets.cfg vira CRITICAL sem nenhum valor de segredo."""
        self._patch_var_dir()
        log_dir = os.path.join(self.tmp_dir, "agente0001", "logs")
        os.makedirs(log_dir)
        # CR-032 (D14): o secrets.cfg compartilhado fica na pasta de cima da do config (<tmp>/secrets.cfg).
        _path, tokens = self._create_temp_secrets(mode=0o644)
        ini = self._copy_and_edit_ini()
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

        # CR-032 (D4): o agent_id e o name; name com caractere proibido e recusado
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(self._copy_and_edit_ini(changes={"app": {"name": "srv linux prod"}}))

        # init_db, seed e purge sao atores reservados do sistema (CR-006, README §8.12)
        for reserved in ("init_db", "seed", "purge"):
            with self.assertRaises(sss_config.ConfigError) as ctx_res:
                sss_config.load(self._copy_and_edit_ini(changes={"app": {"name": reserved}}))
            self.assertEqual(ctx_res.exception.key, "name")
        ini_ok = self._copy_and_edit_ini(changes={"app": {"name": "seed01"}})
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
        # CR-032 (D14): o arquivo e compartilhado; o web le [web], o agente le os ambientes.
        agent_secrets = sss_config.load_secrets(path_sec, role="agent")

        repr_str = repr(secrets_value) + repr(agent_secrets)
        str_str = str(secrets_value) + str(agent_secrets)

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
        self.assertNotIn(tokens["prod_pwd"], repr(agent_secrets.get_environment("PRODUCAO")))

        # Os valores estao acessiveis pelas propriedades internas
        self.assertEqual(secrets_value.oracle_password, tokens["oracle_pwd"])
        self.assertEqual(secrets_value.cookie_key, tokens["cookie_key"])
        self.assertEqual(agent_secrets.get_environment("PRODUCAO").password, tokens["prod_pwd"])
        self.assertIsNone(secrets_value.get_environment("PRODUCAO"), "o web nao le os ambientes")

    def test_secrets_dev_fake_sem_oracle(self):
        """Verifica que [oracle] e opcional no secrets.cfg somente em DEV com FAKE."""
        path_sec, tokens = self._create_temp_secrets(mode=0o600, include_oracle=False)

        # Em DEV e FAKE -> sucesso
        seg_dev = sss_config.load_secrets(path_sec, data_backend="FAKE")
        self.assertIsNone(seg_dev.oracle_password)
        self.assertEqual(seg_dev.cookie_key, tokens["cookie_key"])

        # Em PROD e ORACLE -> erro por [oracle] ausente
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load_secrets(path_sec, data_backend="ORACLE")

    def test_segredos_carregados_sao_registrados_no_masking(self):
        """Regressao: todo segredo carregado e entregue a masking.register_secret (AGENTS §3.3)."""
        path_sec, tokens = self._create_temp_secrets(mode=0o600)
        # CR-032 (D14): cada papel registra o que le do arquivo compartilhado.
        sss_config.load_secrets(path_sec)
        self.assertEqual(sorted(self.masked), sorted([tokens["oracle_pwd"], tokens["cookie_key"]]))
        del self.masked[:]
        sss_config.load_secrets(path_sec, role="agent")
        self.assertEqual(sorted(self.masked), sorted([tokens["oracle_pwd"], tokens["prod_pwd"], tokens["hml_pwd"]]))

        del self.masked[:]
        path_sec, tokens = self._create_temp_secrets(mode=0o600, include_oracle=False)
        sss_config.load_secrets(path_sec, data_backend="FAKE")
        self.assertEqual(sorted(self.masked), [tokens["cookie_key"]])

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
        sss_config.pending_warnings()  # avisos de outros testes iriam para este log
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
        self.assertFalse(hasattr(cfg.agent, "exec_users"), "CR-032 (D7): sem usuario de execucao")
        self.assertEqual(cfg.agent.queue_aging_min, 60)

    def test_prefixo_so_minusculas_e_agent_id_purge_reservado(self):
        self._refusal("table_prefix", oracle={"table_prefix": "TBSSS_"})
        self._refusal("name", app={"name": "purge"})
        self.assertEqual(self._load(app={"name": "purge01"}).agent.agent_id, "purge01")

    def test_faixas_novas(self):
        # CR-008, R-32: minimo de 1461 dias (cobre o 29/02).
        self.assertEqual(self._load().agent.cron_horizon_days, 1461, "CR-032: fixo")
        self.assertEqual(self._load().agent.log_dir_min_free_mb, 1024)
        self.assertEqual(self._load(agent={"log_dir_min_free_mb": "0"}).agent.log_dir_min_free_mb, 0)
        self._refusal("log_dir_min_free_mb", agent={"log_dir_min_free_mb": "-1"})
        self._refusal("max_log_size_bytes", logging={"max_log_size_bytes": str(64 * 1024 * 1024 + 1)})
        self.assertEqual(self._load(agent={"queue_aging_min": "0"}).agent.queue_aging_min, 60, "CR-032: fixo")

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
        # <tmp>/proc/config.ini: o secrets.cfg compartilhado fica em <tmp>/ (CR-032, D14).
        os.makedirs(os.path.join(self.tmp_dir, "proc"), exist_ok=True)
        path = os.path.join(self.tmp_dir, "proc", "config.ini")
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
            "[agent]\nenvironments = PRODUCAO\nmax_parallel_jobs = 2\noutput_dir =\n"))
        base = os.path.join(var, "agente0001")
        self.assertEqual((agent.app.role, agent.agent.agent_id, agent.agent.work_dir, agent.logging.log_dir,
                          agent.agent.input_dir, agent.agent.script_work_dir,
                          agent.agent.script_base_dir, agent.agent.output_dir),
                         ("agent", "agente0001", os.path.join(base, "work"), os.path.join(base, "logs"),
                          os.path.join(base, "input"),
                          os.path.join(base, "script_work"), sss_config.SCRIPTS_DIR, None),
                         "output_dir escrito vazio desliga a funcao")
        self.assertEqual(agent.secrets.secrets_file, os.path.join(self.tmp_dir, "secrets.cfg"))

    def test_cr028_validacoes_por_papel(self):
        # CR-032 (D7): web e agente sobem sem usuario de execucao.
        sss_config.load(self._ini_text("[app]\nsss_env = PROD\nname = web0001\n" + self._ORACLE +
                                       "[web]\nallowed_origins = https://x\n"))
        sss_config.load(self._ini_text("[app]\nsss_env = PROD\nname = agente0001\n" + self._ORACLE +
                                       "[agent]\nenvironments = PRODUCAO\nmax_parallel_jobs = 2\n"))
        # CR-032 (D4): agent_id escrito e ignorado com aviso; vale o name.
        sss_config.pending_warnings()
        cfg = sss_config.load(self._ini_text("[app]\nsss_env = DEV\nname = agente0001\n" + self._ORACLE +
                                             "[agent]\nagent_id = outro\nenvironments = A\nmax_parallel_jobs = 1\n"))
        self.assertEqual(cfg.agent.agent_id, "agente0001")
        self.assertTrue(any("[agent] agent_id ignorada" in w for w in sss_config.pending_warnings()))
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(self._ini_text("[app]\nsss_env = DEV\nname = Agente 1\n" + self._ORACLE +
                                           "[web]\nallowed_origins = https://x\n"))
        # CR-032 (D4): sem name nao ha processo.
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(self._ini_text("[app]\nsss_env = DEV\n" + self._ORACLE +
                                           "[web]\nallowed_origins = https://x\n"))
        self.assertEqual(ctx.exception.key, "name")

    def test_cr028_web_com_agent_parcial(self):
        """Revisao do CR-028 (A1): o web aceita [agent] so com as chaves que usa, sem virar formato unico."""
        base = ("[app]\nsss_env = PROD\nname = web0001\n" + self._ORACLE +
                "[web]\nallowed_origins = https://x\n[agent]\n")
        web = sss_config.load(self._ini_text(base + "misfire_policy = SKIP\nqueue_aging_min = 15\n"))
        self.assertEqual((web.app.role, web.agent.misfire_policy, web.agent.queue_aging_min,
                          web.agent.heartbeat_interval_s), ("web", "SKIP", 60, 10), "CR-032: fixos, com aviso")
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(self._ini_text(base + "misfire_policy = SKIP\noutput_dir = /tmp/x\n"))
        self.assertEqual(ctx.exception.key, "output_dir")
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load(self._ini_text(base + "misfire_policy = TALVEZ\n"))

    def test_cr028_name_igual_a_pasta(self):
        """Revisao do CR-028 (A2): em instance/<pasta>/, o name diferente da pasta e recusado."""
        folder = os.path.join(sss_config.APP_DIR, "instance", "teste_a2")
        os.makedirs(folder)
        self.addCleanup(shutil.rmtree, folder, True)
        text = ("[app]\nsss_env = DEV\nname = %s\n" + self._ORACLE +
                "[agent]\nenvironments = A\nmax_parallel_jobs = 1\n")
        path = os.path.join(folder, "config.ini")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text % "agente0001")
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.load(path)
        self.assertEqual(ctx.exception.key, "name")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text % "teste_a2")
        self.assertEqual(sss_config.load(path).agent.agent_id, "teste_a2")

    def test_cr028_env_label(self):
        """CR-028 (D12), CR-032 (D11): a tela e a linha de subida mostram o nome da pasta <TIPO> acima da raiz."""
        for tipo, shown in (("PROD", "PROD"), ("dev", "DEV"), ("OUTRA", "OUTRA"), ("", "?")):
            self.assertEqual(sss_config.env_label(tipo), shown, tipo)
        self.assertEqual(sss_config.env_label(), sss_config.INSTALL_TYPE)
        self.assertTrue(sss_config.has_dev_dir(), "o repositorio tem a pasta dev/")
        self.assertEqual(sss_config.INSTALL_TYPE,
                         os.path.basename(os.path.dirname(sss_config.APP_DIR)).upper())

    def test_cr032_sem_usuario_de_execucao(self):
        """CR-032 (D7): exec_users, exec_work_dir e helper_path ficam so com aviso; a subida segue."""
        agent_ini = ("[app]\nsss_env = PROD\nname = agente0001\n" + self._ORACLE +
                     "[agent]\nenvironments = A\nmax_parallel_jobs = 1\n")
        sss_config.pending_warnings()
        cfg = sss_config.load(self._ini_text(agent_ini + "exec_users = A=sssprd\nexec_work_dir = /srv/exec\n"
                                             "helper_path = /opt/sss/bin/sss-helper\nusuarios_execucao = A=x\n"))
        for key in ("exec_users", "exec_work_dir", "helper_path"):
            self.assertFalse(hasattr(cfg.agent, key), key)
        warnings = "\n".join(sss_config.pending_warnings())
        for key in ("exec_users", "exec_work_dir", "helper_path", "usuarios_execucao"):
            self.assertIn("[agent] %s ignorada: sem usuario de execucao" % key, warnings)

    def test_cr028_caminho_pelo_nome_e_exemplos(self):
        self.assertEqual(sss_config.config_path(None, "agente0001"),
                         os.path.join(sss_config.APP_DIR, "instance", "agente0001", "config.ini"))
        self.assertEqual(sss_config.config_path("/x.ini", "agente0001"), "/x.ini")
        # CR-029 (D1, opcao A): sem --name nem --config, erro com a lista dos processos de instance/.
        with self.assertRaises(sss_config.ConfigError) as ctx:
            sss_config.config_path(None, None)
        self.assertIn("Informe o processo", str(ctx.exception))
        with mock.patch.object(sss_config, "APP_DIR", self.tmp_dir):
            os.makedirs(os.path.join(self.tmp_dir, "instance", "web0001"))
            os.makedirs(os.path.join(self.tmp_dir, "instance", "exemplos", "agente0001"))
            open(os.path.join(self.tmp_dir, "instance", "web0001", "config.ini"), "w").close()
            open(os.path.join(self.tmp_dir, "instance", "exemplos", "agente0001", "config.ini"), "w").close()
            self.assertEqual(sss_config.processes(), ["web0001"], "sem os modelos de exemplos/")
        sss_config.reset_config_cache()
        self.addCleanup(sss_config.reset_config_cache)
        with self.assertRaises(sss_config.ConfigError):
            sss_config.get_config()
        cfg = sss_config.load(self.example_ini)
        self.assertEqual(cfg.app.config_path, self.example_ini, "caminho repassado a sondagem do driver")
        for bad in ("Agente", "a/b", "../x", ""):
            if bad:
                with self.assertRaises(sss_config.ConfigError):
                    sss_config.config_path(None, bad)
        for name, role in (("web0001", "web"), ("agente0001", "agent")):
            example = os.path.join(self.app_dir, "instance", "exemplos", name, "config.ini.example")
            with open(example, encoding="utf-8") as handle:
                cfg = sss_config.load(self._ini_text(handle.read()))
            self.assertEqual((cfg.app.role, cfg.app.name), (role, name), example)

    def test_cr026_readme_tabela_igual_ao_schema(self):
        """CR-026: a tabela do README §12.1 lista toda chave do SCHEMA, com a obrigatoriedade e o padrao do codigo."""
        with open(os.path.join(self.app_dir, "README.md"), "r", encoding="utf-8") as f:
            text = f.read()
        section = text[text.index("### 12.1 `instance/<nome>/config.ini`"):text.index("### 12.2 Launchers")]
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
        ini = self._copy_and_edit_ini(keys_to_remove=optional)
        with open(ini, "r", encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("call_timeout_ms", text)
        cfg = sss_config.load(ini)
        self.assertEqual(cfg.secrets.secrets_file, os.path.join(self.tmp_dir, "secrets.cfg"))
        expected = {("oracle", "call_timeout_ms"): 30000, ("oracle", "pool_min"): 1, ("oracle", "pool_max"): 4,
                    ("agent", "schedule_batch_size"): 50, ("agent", "orchestrator_interval_s"): 10,
                    ("agent", "cancel_poll_interval_s"): 2, ("agent", "heartbeat_interval_s"): 10,
                    ("agent", "fence_timeout_s"): 90, ("agent", "node_offline_timeout_s"): 180,
                    ("agent", "kill_grace_s"): 5, ("agent", "script_timeout_s"): 604800,
                    ("agent", "shutdown_mode"): "TERMINATE", ("agent", "shutdown_grace_s"): 30,
                    ("agent", "misfire_policy"): "RUN_ONCE", ("agent", "misfire_tolerance_s"): 300,
                    ("agent", "cron_horizon_days"): 1461, ("agent", "child_locale"): "C.UTF-8",
                    ("logging", "level"): "INFO", ("logging", "app_log_max_bytes"): 10485760,
                    ("logging", "max_log_size_bytes"): 5242880,
                    ("logging", "max_local_log_size_bytes"): 52428800,
                    ("web", "session_idle_timeout_s"): 1800, ("web", "login_max_attempts"): 5,
                    ("web", "login_lockout_s"): 900, ("web", "log_poll_interval_s"): 3}
        for (sec, key), value in expected.items():
            self.assertEqual(getattr(getattr(cfg, sec), key), value, key)
        # Os obrigatorios: name, oracle (user, dsn, owner, table_prefix), environments,
        # max_parallel_jobs e allowed_origins (CR-032, D4: agent_id, work_dir e log_dir saem do name).
        required = sorted((sec, k) for sec, fields in sss_config.SCHEMA.items() for k, cdef in fields.items()
                          if cdef.required)
        self.assertEqual(required, sorted([
            ("app", "name"), ("oracle", "user"), ("oracle", "dsn"), ("oracle", "owner"),
            ("oracle", "table_prefix"), ("agent", "environments"), ("agent", "max_parallel_jobs"),
            ("web", "allowed_origins")]))

    def test_pasta_de_saida(self):
        # CR-012 (README §8.13): opcional, com limites e sem sobrepor as pastas do SSS.
        cfg = self._load()
        self.assertIsNone(cfg.agent.output_dir)
        self.assertEqual((cfg.agent.output_max_bytes, cfg.agent.output_max_files), (20971520, 1000))
        base = os.path.dirname(cfg.agent.work_dir)
        ok = self._load(agent={"output_dir": os.path.join(base, "saida_teste")})
        self.assertEqual(ok.agent.output_dir, os.path.join(base, "saida_teste"))
        self._refusal("output_dir", agent={"output_dir": "relativa/output"})
        self._refusal("output_dir", agent={"output_dir": os.path.join(cfg.agent.work_dir, "output")})
        self._refusal("output_dir", agent={"output_dir": os.path.join(cfg.logging.log_dir, "output")})
        self._refusal("output_dir", agent={"output_dir": os.path.dirname(cfg.logging.log_dir)})
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
        ok = self._load(agent={"script_work_dir": os.path.join(base, "trabalho_teste")})
        self.assertEqual(ok.agent.script_work_dir, os.path.join(base, "trabalho_teste"))
        self._refusal("script_work_dir", agent={"script_work_dir": "relativa/work"})
        self._refusal("script_work_dir", agent={"script_work_dir": os.path.join(cfg.agent.work_dir, "sw")})
        self._refusal("script_work_dir", agent={"script_work_dir": os.path.join(cfg.logging.log_dir, "sw")})
        self._refusal("script_work_dir", agent={"script_work_dir": os.path.dirname(cfg.logging.log_dir)})
        self._refusal("script_work_dir", agent={"script_work_dir": os.path.join(base, "s", "sw"),
                                                 "output_dir": os.path.join(base, "s")})
        self._refusal("script_work_dir", agent={"script_work_dir": os.path.join(base, "s"),
                                                 "input_dir": os.path.join(base, "s", "input")})
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
        # CR-020d: limite do envio pela tela de Entrada.
        for v in ("1048575", "209715201"):
            self._refusal("input_upload_max_bytes", web={"input_upload_max_bytes": v})
        self.assertEqual(self._load(web={"input_upload_max_bytes": "1048576"}).web.input_upload_max_bytes, 1048576)
        # CR-021e (D5): servidor web proprio.
        web_cfg = self._load().web
        self.assertEqual((web_cfg.max_threads, web_cfg.socket_timeout_s), (16, 30), "CR-032: fixos")
        for key, bad, good in (("output_max_bytes", ("1048575", "209715201"), ("1048576", "209715200")),
                                   ("output_max_files", ("0", "10001"), ("1", "10000"))):
            for v in bad:
                self._refusal(key, agent={key: v})
            for v in good:
                self.assertEqual(getattr(self._load(agent={key: v}).agent, key), int(v))

    def test_invariantes_i3_e_i4(self):
        # CR-032 (D3): com heartbeat 10, fence 90, offline 180 e kill 5 fixos, I3 limita o call_timeout_ms a 40 s.
        self._refusal("call_timeout_ms", oracle={"call_timeout_ms": "41000"})
        self.assertEqual(self._load(oracle={"call_timeout_ms": "40000"}).oracle.call_timeout_ms, 40000)
        self.assertEqual(sss_config.call_timeout_s(30001), 31)
        self._load()  # o exemplo atende I3 = 70 <= 90 e I4 = 127 <= 180

    def test_cr030_sem_purge_nem_retencao(self):
        """CR-030: [retention], as retencoes de [logging] e [purge] dos segredos sao ignoradas com aviso."""
        sss_config.pending_warnings()
        cfg = self._load(retention={"purge_user": "sss_purge", "ticket_retention_days": "0"},
                         logging={"app_log_retention_days": "0", "output_retention_days": "x"},
                         oracle={"user": "sss_web"})
        self.assertFalse(hasattr(cfg, "retention"))
        warnings = "\n".join(sss_config.pending_warnings())
        for key in ("[retention] purge_user", "[retention] ticket_retention_days", "[logging] app_log_retention_days",
                    "[logging] output_retention_days"):
            self.assertIn(key, warnings)
        with self.assertLogs("sss_config", level="WARNING") as logs:
            seg = sss_config.load_secrets(self._secrets([("oracle", {"password": "senha-agt-123"}),
                                                          ("purge", {"password": "senha-prg-123"})]),
                                          data_backend="ORACLE", role="agent")
        self.assertIn("secao [purge] ignorada", "\n".join(logs.output))
        self.assertNotIn("senha-prg-123", self.masked)
        self.assertFalse(hasattr(seg, "purge_password"))

    def test_cr032_conta_igual_ao_owner_e_sss_env_ignorado(self):
        """CR-032 (D11): a conta igual ao owner e aceita; o sss_env antigo so gera aviso e nao muda nada."""
        sss_config.pending_warnings()
        for env in ("DEV", "HML", "PROD"):
            cfg = self._load(app={"sss_env": env}, oracle={"user": "OPENRISOW"})
            self.assertEqual(cfg.oracle.user, "OPENRISOW")
            self.assertFalse(hasattr(cfg.app, "sss_env"))
        self.assertTrue(any("[app] sss_env ignorada" in w for w in sss_config.pending_warnings()))

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
            sss_config.load_secrets(self._secrets(old), data_backend="ORACLE", role="agent")
        self.assertIn("[ambiente:PRODUCAO] passou a se chamar [environment:PRODUCAO]", str(ctx.exception))
        self.assertNotIn("s-123", str(ctx.exception))

    def test_segredos_por_papel(self):
        web = [("oracle", {"password": "senha-web-123"}), ("web", {"cookie_key": "chave-cookie-123"})]
        agent = [("oracle", {"password": "senha-agt-123"}),
                  ("environment:PRODUCAO", {"user": "app", "password": "senha-amb-123"})]
        seg = sss_config.load_secrets(self._secrets(agent), data_backend="ORACLE", role="agent")
        self.assertIsNone(seg.cookie_key)
        self.assertIn("senha-amb-123", self.masked)
        self.assertNotIn("senha-amb-123", repr(seg))
        # CR-032 (D14): um secrets.cfg por servidor; a secao dos outros processos e ignorada sem aviso.
        shared = self._secrets(agent + [("web", {"cookie_key": "x" * 20})])
        self.assertIsNone(sss_config.load_secrets(shared, data_backend="ORACLE",
                                                  role="agent").cookie_key)
        seg_web = sss_config.load_secrets(self._secrets(web + agent[1:]), data_backend="ORACLE")
        self.assertEqual((seg_web.cookie_key, seg_web.environments), ("chave-cookie-123", {}))
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load_secrets(self._secrets(web), role="agente_x")

        # CR-032 (D8): sem papel monitor.
        with self.assertRaises(sss_config.ConfigError):
            sss_config.load_secrets(self._secrets(web), role="monitor")

    def test_segredos_do_agente_cobrem_os_ambientes(self):
        """CR-032 (D11): ambiente atendido sem credencial recusa a subida, em DEV e PROD."""
        cfg = self._load()
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
