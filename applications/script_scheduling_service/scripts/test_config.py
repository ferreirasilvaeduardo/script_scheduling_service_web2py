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

import _testenv
import sss_config
import sss_logging


class TestConfig(unittest.TestCase):
    """Bateria de testes para validacao tipada de config.ini e secrets.cfg."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="sss_test_")
        self.app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.web2py_root = os.path.dirname(os.path.dirname(self.app_dir))
        self.example_ini = os.path.join(self.app_dir, "instance", "config.ini.example")

        # masking.py ainda nao existe; o substituto registra o que carregar_segredos entrega.
        self.mascarados = []
        masking_stub = types.ModuleType("masking")
        masking_stub.registrar_segredo = self.mascarados.append
        patcher = mock.patch.dict(sys.modules, {"masking": masking_stub})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    def _copiar_e_modificar_ini(self, alteracoes=None, secoes_remover=None, chaves_remover=None):
        """Gera arquivo temporario config.ini a partir do exemplo com modificacoes."""
        cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
        with open(self.example_ini, "r", encoding="utf-8") as f:
            cp.read_file(f)

        if alteracoes:
            for sec, chaves in alteracoes.items():
                if not cp.has_section(sec):
                    cp.add_section(sec)
                for k, v in chaves.items():
                    cp.set(sec, k, str(v))

        if chaves_remover:
            for sec, k in chaves_remover:
                if cp.has_section(sec) and cp.has_option(sec, k):
                    cp.remove_option(sec, k)

        if secoes_remover:
            for sec in secoes_remover:
                if cp.has_section(sec):
                    cp.remove_section(sec)

        caminho_dest = os.path.join(self.tmp_dir, "config_modificado.ini")
        with open(caminho_dest, "w", encoding="utf-8") as f:
            cp.write(f)
        return caminho_dest

    def _criar_secrets_temporario(self, modo=0o600, incluir_oracle=True, tokens=None):
        """Cria secrets.cfg com valores pseudo-aleatorios (secrets.token_hex)."""
        if tokens is None:
            tokens = {
                "oracle_pwd": secrets.token_hex(16),
                "cookie_key": secrets.token_hex(32),
                "prod_pwd": secrets.token_hex(16),
                "hml_pwd": secrets.token_hex(16),
            }

        caminho = os.path.join(self.tmp_dir, "secrets.cfg")
        linhas = []
        if incluir_oracle:
            linhas.extend([
                "[oracle]",
                "password = %s" % tokens["oracle_pwd"],
                ""
            ])
        linhas.extend([
            "[web]",
            "cookie_key = %s" % tokens["cookie_key"],
            "",
            "[ambiente:PRODUCAO]",
            "user = app_prod",
            "password = %s" % tokens["prod_pwd"],
            "",
            "[ambiente:HOMOLOGACAO]",
            "user = app_hml",
            "password = %s" % tokens["hml_pwd"],
            ""
        ])

        with open(caminho, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas))

        os.chmod(caminho, modo)
        return caminho, tokens

    def test_config_valido(self):
        """Verifica carga do config.ini.example valido e integridade dos tipos."""
        cfg = sss_config.carregar(self.example_ini)

        # [app]
        self.assertEqual(cfg.app.sss_env, "DEV")
        self.assertEqual(cfg.app.data_backend, "FAKE")

        # [oracle]
        self.assertEqual(cfg.oracle.user, "sss_web")
        self.assertEqual(cfg.oracle.dsn, "10.0.0.1:1521/servico_homolog")
        self.assertEqual(cfg.oracle.owner, "gfcadastro")
        self.assertEqual(cfg.oracle.table_prefix, "tbsss_")
        self.assertEqual(cfg.oracle.driver, "oracledb")
        self.assertTrue(cfg.oracle.use_thick_mode)
        self.assertIsNone(cfg.oracle.oracle_client_lib_dir)
        self.assertEqual(cfg.oracle.call_timeout_ms, 30000)
        self.assertEqual(cfg.oracle.pool_min, 1)
        self.assertEqual(cfg.oracle.pool_max, 4)

        # [secrets]
        self.assertEqual(cfg.secrets.secrets_file, "/etc/sss/secrets.cfg")

        # [agent]
        self.assertEqual(cfg.agent.agent_id, "srv-linux-prod-01")
        self.assertEqual(cfg.agent.ambientes_atendidos, ("PRODUCAO", "HOMOLOGACAO"))
        self.assertFalse(hasattr(cfg.agent, "base_script_dirs"))
        self.assertEqual(cfg.agent.work_dir, "/var/lib/sss/work")
        self.assertEqual(cfg.agent.script_owner_uids, (0,))
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
        self.assertEqual(cfg.logging.log_dir, "/var/log/sss")
        self.assertEqual(cfg.logging.level, "INFO")
        self.assertEqual(cfg.logging.app_log_max_bytes, 10485760)
        self.assertEqual(cfg.logging.app_log_retention_days, 30)

        # [web]
        self.assertEqual(cfg.web.session_idle_timeout_s, 1800)
        self.assertEqual(cfg.web.login_max_tentativas, 5)
        self.assertEqual(cfg.web.login_bloqueio_s, 900)
        self.assertEqual(cfg.web.log_poll_interval_s, 3)
        self.assertEqual(cfg.web.trusted_proxies, ())
        self.assertEqual(cfg.web.allowed_origins, ("https://sss.empresa.local",))

        # [retencao]
        self.assertEqual(cfg.retencao.ticket_retention_days, 180)
        self.assertEqual(cfg.retencao.audit_retention_days, 730)
        self.assertEqual(cfg.retencao.purge_batch_size, 1000)

        # Acesso via indexacao estilo dict
        self.assertEqual(cfg["app"]["sss_env"], "DEV")
        self.assertEqual(cfg["oracle"]["owner"], "gfcadastro")

        # Imutabilidade estrita
        with self.assertRaises(AttributeError):
            cfg.app.sss_env = "PROD"

    def test_chave_ausente(self):
        """Verifica rejeicao fail-fast quando chave obrigatoria esta ausente."""
        ini = self._copiar_e_modificar_ini(chaves_remover=[("oracle", "call_timeout_ms")])
        with self.assertRaises(sss_config.ConfigErro) as ctx:
            sss_config.carregar(ini)
        self.assertEqual(ctx.exception.secao, "oracle")
        self.assertEqual(ctx.exception.chave, "call_timeout_ms")

    def test_secao_ausente(self):
        """Verifica rejeicao fail-fast quando secao inteira esta ausente."""
        ini = self._copiar_e_modificar_ini(secoes_remover=["retencao"])
        with self.assertRaises(sss_config.ConfigErro) as ctx:
            sss_config.carregar(ini)
        self.assertEqual(ctx.exception.secao, "retencao")

    def test_chave_desconhecida(self):
        """Verifica rejeicao de chave desconhecida no config.ini."""
        ini = self._copiar_e_modificar_ini(alteracoes={"oracle": {"chave_fantasma": "123"}})
        with self.assertRaises(sss_config.ConfigErro) as ctx:
            sss_config.carregar(ini)
        self.assertEqual(ctx.exception.secao, "oracle")
        self.assertEqual(ctx.exception.chave, "chave_fantasma")

    def test_secao_desconhecida(self):
        """Verifica rejeicao de secao nao documentada no config.ini."""
        ini = self._copiar_e_modificar_ini(alteracoes={"secao_estranha": {"foo": "bar"}})
        with self.assertRaises(sss_config.ConfigErro) as ctx:
            sss_config.carregar(ini)
        self.assertEqual(ctx.exception.secao, "secao_estranha")

    def test_tipo_invalido(self):
        """Verifica rejeicao de valores com tipo incompativel."""
        # int invalido
        ini_int = self._copiar_e_modificar_ini(alteracoes={"oracle": {"pool_min": "um"}})
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar(ini_int)

        # bool invalido
        ini_bool = self._copiar_e_modificar_ini(alteracoes={"oracle": {"use_thick_mode": "talvez"}})
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar(ini_bool)

        # enum invalido
        ini_enum = self._copiar_e_modificar_ini(alteracoes={"app": {"sss_env": "STAGING"}})
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar(ini_enum)

        # UIDs invalidos
        ini_uid = self._copiar_e_modificar_ini(alteracoes={"agent": {"script_owner_uids": "root"}})
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar(ini_uid)

    def test_fora_da_faixa(self):
        """Verifica rejeicao de valores fora das faixas minimas/maximas."""
        # pool_min < 1
        ini = self._copiar_e_modificar_ini(alteracoes={"oracle": {"pool_min": "0"}})
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar(ini)

        # max_parallel_jobs > 999
        ini2 = self._copiar_e_modificar_ini(alteracoes={"agent": {"max_parallel_jobs": "1000"}})
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar(ini2)

        # app_log_max_bytes < 1024
        ini3 = self._copiar_e_modificar_ini(alteracoes={"logging": {"app_log_max_bytes": "500"}})
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar(ini3)

        # app_log_retention_days < 1
        ini_ret_min = self._copiar_e_modificar_ini(alteracoes={"logging": {"app_log_retention_days": "0"}})
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar(ini_ret_min)

        # app_log_retention_days > 3650
        ini_ret_max = self._copiar_e_modificar_ini(alteracoes={"logging": {"app_log_retention_days": "3651"}})
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar(ini_ret_max)

        # app_log_backups sai no CR-005 e passa a ser recusada como desconhecida
        ini_antigo = self._copiar_e_modificar_ini(alteracoes={"logging": {"app_log_backups": "10"}})
        with self.assertRaises(sss_config.ConfigErro) as ctx_antigo:
            sss_config.carregar(ini_antigo)
        self.assertEqual(ctx_antigo.exception.chave, "app_log_backups")

    def test_cada_invariante(self):
        """Verifica a validacao de cada invariante de integridade operacional."""
        # 1. max_parallel_jobs <= max_parallel_hard_limit
        ini1 = self._copiar_e_modificar_ini(alteracoes={
            "agent": {"max_parallel_jobs": "33", "max_parallel_hard_limit": "32"}
        })
        with self.assertRaises(sss_config.ConfigErro) as ctx1:
            sss_config.carregar(ini1)
        self.assertEqual(ctx1.exception.chave, "max_parallel_jobs")

        # 2. fence_timeout_s * 2 <= node_offline_timeout_s
        ini2 = self._copiar_e_modificar_ini(alteracoes={
            "agent": {"fence_timeout_s": "100", "node_offline_timeout_s": "180"}
        })
        with self.assertRaises(sss_config.ConfigErro) as ctx2:
            sss_config.carregar(ini2)
        self.assertEqual(ctx2.exception.chave, "fence_timeout_s")

        # 3. heartbeat_interval_s * 3 <= fence_timeout_s
        ini3 = self._copiar_e_modificar_ini(alteracoes={
            "agent": {"heartbeat_interval_s": "31", "fence_timeout_s": "90"}
        })
        with self.assertRaises(sss_config.ConfigErro) as ctx3:
            sss_config.carregar(ini3)
        self.assertEqual(ctx3.exception.chave, "heartbeat_interval_s")

        # 4. pool_min <= pool_max
        ini4 = self._copiar_e_modificar_ini(alteracoes={
            "oracle": {"pool_min": "5", "pool_max": "4"}
        })
        with self.assertRaises(sss_config.ConfigErro) as ctx4:
            sss_config.carregar(ini4)
        self.assertEqual(ctx4.exception.chave, "pool_min")

    def test_fake_com_hml(self):
        """Verifica a invariante: data_backend=FAKE exige sss_env=DEV."""
        ini_hml = self._copiar_e_modificar_ini(alteracoes={
            "app": {"sss_env": "HML", "data_backend": "FAKE"}
        })
        with self.assertRaises(sss_config.ConfigErro) as ctx_hml:
            sss_config.carregar(ini_hml)
        self.assertIn("data_backend=FAKE exige sss_env=DEV", str(ctx_hml.exception))

        ini_prod = self._copiar_e_modificar_ini(alteracoes={
            "app": {"sss_env": "PROD", "data_backend": "FAKE"}
        })
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar(ini_prod)

    def test_prefixo_comeca_com_letra(self):
        """CR-003 P2: prefixo iniciado por digito ou _ geraria nome Oracle invalido."""
        for prefixo in ("1x_", "_x", "9"):
            ini = self._copiar_e_modificar_ini(alteracoes={"oracle": {"table_prefix": prefixo}})
            with self.assertRaises(sss_config.ConfigErro) as ctx:
                sss_config.carregar(ini)
            self.assertEqual(ctx.exception.chave, "table_prefix", prefixo)
        ini_ok = self._copiar_e_modificar_ini(alteracoes={"oracle": {"table_prefix": "a1_"}})
        self.assertEqual(sss_config.carregar(ini_ok).oracle.table_prefix, "a1_")

    def test_pastas_base_recusadas(self):
        """CR-005 (README §12.1): base_script_dirs e a antiga base_script_dir sao chaves desconhecidas."""
        for chave, valor in (("base_script_dirs", "ROTINAS=/opt/automacoes/scripts"),
                             ("base_script_dir", "/opt/automacoes/scripts"),
                             ("script_owner_sids", "S-1-5-32-544")):
            ini = self._copiar_e_modificar_ini(alteracoes={"agent": {chave: valor}})
            with self.assertRaises(sss_config.ConfigErro, msg=chave) as ctx:
                sss_config.carregar(ini)
            self.assertEqual(ctx.exception.chave, chave)
            self.assertIn("desconhecida", ctx.exception.motivo)

    def test_login_max_tentativas_cabe_em_number_2(self):
        """CR-003 P2: tentativas_falha e NUMBER(2), entao o teto e 99."""
        ini_100 = self._copiar_e_modificar_ini(alteracoes={"web": {"login_max_tentativas": "100"}})
        with self.assertRaises(sss_config.ConfigErro) as ctx:
            sss_config.carregar(ini_100)
        self.assertEqual(ctx.exception.chave, "login_max_tentativas")
        ini_99 = self._copiar_e_modificar_ini(alteracoes={"web": {"login_max_tentativas": "99"}})
        self.assertEqual(sss_config.carregar(ini_99).web.login_max_tentativas, 99)

    def _obter_com_ini(self, ini, nome_log="sss_web"):
        sss_config.reset_config_cache()
        self.addCleanup(sss_config.reset_config_cache)
        with mock.patch.object(sss_config, "caminho_config_padrao", return_value=ini):
            return sss_config.obter_config(nome_log)

    def _ler_log_app(self, log_dir, nome_log):
        """CR-005 D6: o CRITICAL inicial fica em log_dir/app/AAAA/MM/DD/HH/MI/<nome_log>_<PID>.log."""
        esperado = "%s_%d.log" % (nome_log, os.getpid())
        achados = []
        for raiz, _dirs, arquivos in os.walk(log_dir):
            achados.extend(os.path.join(raiz, a) for a in arquivos)
        self.assertFalse(os.path.exists(os.path.join(log_dir, nome_log + ".log")))
        self.assertEqual(len(achados), 1, achados)
        self.assertEqual(os.path.basename(achados[0]), esperado)
        partes = os.path.relpath(os.path.dirname(achados[0]), log_dir).split(os.sep)
        self.assertEqual(partes[0], "app")
        self.assertEqual(len(partes), 6)
        self.assertEqual(stat.S_IMODE(os.stat(achados[0]).st_mode), 0o640)
        with open(achados[0], encoding="utf-8") as f:
            return f.read()

    def test_configuracao_invalida_gera_critical_no_log(self):
        """CR-003 P2: CRITICAL com secao, chave e motivo no log da aplicacao quando log_dir e utilizavel."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        os.makedirs(log_dir)
        ini = self._copiar_e_modificar_ini(alteracoes={"logging": {"log_dir": log_dir},
                                                       "web": {"login_max_tentativas": "100"}})
        with self.assertRaises(sss_config.ConfigErro):
            self._obter_com_ini(ini)
        conteudo = self._ler_log_app(log_dir, "sss_web")
        self.assertIn(" CRITICAL ", conteudo)
        self.assertIn("login_max_tentativas", conteudo)
        self.assertIn("[acao=INICIO]", conteudo)
        # Falha repetida no mesmo minuto e processo (nova requisicao) vai para o mesmo arquivo.
        with self.assertRaises(sss_config.ConfigErro):
            self._obter_com_ini(ini)
        self.assertEqual(self._ler_log_app(log_dir, "sss_web").count(" CRITICAL "), 2)

    def test_configuracao_invalida_sem_log_dir_vai_para_stderr(self):
        """CR-003 P2: sem log_dir utilizavel, o CRITICAL vai para o stderr no mesmo formato."""
        ini = self._copiar_e_modificar_ini(alteracoes={"logging": {"log_dir": os.path.join(self.tmp_dir, "nao", "existe")},
                                                       "oracle": {"table_prefix": "1x_"}})
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            with self.assertRaises(sss_config.ConfigErro):
                self._obter_com_ini(ini)
        self.assertIn(" CRITICAL ", err.getvalue())
        self.assertIn("table_prefix", err.getvalue())

    def test_segredos_invalidos_geram_critical_sem_valor(self):
        """CR-003 P2: falha em secrets.cfg vira CRITICAL sem nenhum valor de segredo."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        os.makedirs(log_dir)
        caminho, tokens = self._criar_secrets_temporario(modo=0o644)
        ini = self._copiar_e_modificar_ini(alteracoes={"logging": {"log_dir": log_dir},
                                                       "secrets": {"secrets_file": caminho}})
        self._obter_com_ini(ini)
        sss_config.reset_segredos_cache()
        self.addCleanup(sss_config.reset_segredos_cache)
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.obter_segredos("sss_web")
        conteudo = self._ler_log_app(log_dir, "sss_web")
        self.assertIn(" CRITICAL ", conteudo)
        for valor in tokens.values():
            self.assertNotIn(valor, conteudo)

    def test_prefixo_de_9_caracteres(self):
        """Verifica restricao de regex de table_prefix (max 8 chars)."""
        ini_9 = self._copiar_e_modificar_ini(alteracoes={
            "oracle": {"table_prefix": "tbsss_123"}  # 9 caracteres
        })
        with self.assertRaises(sss_config.ConfigErro) as ctx:
            sss_config.carregar(ini_9)
        self.assertEqual(ctx.exception.chave, "table_prefix")

        # Teste com owner invalido (iniciando com digito)
        ini_owner = self._copiar_e_modificar_ini(alteracoes={
            "oracle": {"owner": "1_invalido"}
        })
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar(ini_owner)

        # Teste com agent_id contendo caractere proibido
        ini_agent = self._copiar_e_modificar_ini(alteracoes={
            "agent": {"agent_id": "srv linux prod"}
        })
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar(ini_agent)

        # init_db e seed sao atores reservados do sistema (CR-006, README §8.12)
        for reservado in ("init_db", "seed"):
            ini_res = self._copiar_e_modificar_ini(alteracoes={"agent": {"agent_id": reservado}})
            with self.assertRaises(sss_config.ConfigErro) as ctx_res:
                sss_config.carregar(ini_res)
            self.assertEqual(ctx_res.exception.chave, "agent_id")
        ini_ok = self._copiar_e_modificar_ini(alteracoes={"agent": {"agent_id": "seed01"}})
        self.assertEqual(sss_config.carregar(ini_ok).agent.agent_id, "seed01")

    def test_env_passthrough_com_ld_preload(self):
        """Verifica rejeicao de variaveis perigosas bloqueadas no passthrough."""
        ini_preload = self._copiar_e_modificar_ini(alteracoes={
            "agent": {"env_passthrough": "ORACLE_HOME,LD_PRELOAD"}
        })
        with self.assertRaises(sss_config.ConfigErro) as ctx:
            sss_config.carregar(ini_preload)
        self.assertEqual(ctx.exception.chave, "env_passthrough")
        self.assertIn("LD_PRELOAD", str(ctx.exception))

        # Teste com PYTHONPATH
        ini_py = self._copiar_e_modificar_ini(alteracoes={
            "agent": {"env_passthrough": "PYTHONPATH"}
        })
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar(ini_py)

    def test_secrets_modo_0644(self):
        """Verifica que secrets.cfg com permissoes inseguras (ex: 0644) e rejeitado."""
        caminho_sec, _ = self._criar_secrets_temporario(modo=0o644)
        with self.assertRaises(sss_config.ConfigErro) as ctx:
            sss_config.carregar_segredos(caminho_sec)
        self.assertIn("permissoes inseguras", str(ctx.exception))

        # Corrige permissao para 0600 e valida sucesso
        os.chmod(caminho_sec, 0o600)
        segredos = sss_config.carregar_segredos(caminho_sec)
        self.assertIsNotNone(segredos)

    def test_repr_segredos_sem_valores(self):
        """Verifica que repr() e str() de Segredos nunca vazam credenciais."""
        caminho_sec, tokens = self._criar_secrets_temporario(modo=0o600)
        segredos = sss_config.carregar_segredos(caminho_sec)

        repr_str = repr(segredos)
        str_str = str(segredos)

        # Nenhum token pode aparecer em repr ou str
        for nome_tok, valor_tok in tokens.items():
            self.assertNotIn(
                valor_tok, repr_str,
                "Token %s vazou no repr(segredos)!" % nome_tok
            )
            self.assertNotIn(
                valor_tok, str_str,
                "Token %s vazou no str(segredos)!" % nome_tok
            )

        # Checagem nos sub-objetos
        self.assertNotIn(tokens["oracle_pwd"], repr(segredos.oracle))
        self.assertNotIn(tokens["cookie_key"], repr(segredos.web))
        self.assertNotIn(tokens["prod_pwd"], repr(segredos.get_ambiente("PRODUCAO")))

        # Os valores estao acessiveis pelas propriedades internas
        self.assertEqual(segredos.oracle_password, tokens["oracle_pwd"])
        self.assertEqual(segredos.cookie_key, tokens["cookie_key"])
        self.assertEqual(segredos.get_ambiente("PRODUCAO").password, tokens["prod_pwd"])

    def test_secrets_dev_fake_sem_oracle(self):
        """Verifica que [oracle] e opcional no secrets.cfg somente em DEV com FAKE."""
        caminho_sec, tokens = self._criar_secrets_temporario(modo=0o600, incluir_oracle=False)

        # Em DEV e FAKE -> sucesso
        seg_dev = sss_config.carregar_segredos(caminho_sec, sss_env="DEV", data_backend="FAKE")
        self.assertIsNone(seg_dev.oracle_password)
        self.assertEqual(seg_dev.cookie_key, tokens["cookie_key"])

        # Em PROD e ORACLE -> erro por [oracle] ausente
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar_segredos(caminho_sec, sss_env="PROD", data_backend="ORACLE")

    def test_segredos_carregados_sao_registrados_no_masking(self):
        """Regressao: todo segredo carregado e entregue a masking.registrar_segredo (AGENTS §3.3)."""
        caminho_sec, tokens = self._criar_secrets_temporario(modo=0o600)
        sss_config.carregar_segredos(caminho_sec)
        self.assertEqual(sorted(self.mascarados), sorted(tokens.values()))

        del self.mascarados[:]
        caminho_sec, tokens = self._criar_secrets_temporario(modo=0o600, incluir_oracle=False)
        sss_config.carregar_segredos(caminho_sec, sss_env="DEV", data_backend="FAKE")
        self.assertEqual(sorted(self.mascarados),
                         sorted([tokens["cookie_key"], tokens["prod_pwd"], tokens["hml_pwd"]]))

    def test_carga_de_segredos_sem_masking_falha(self):
        """Regressao: sem masking.py a carga falha, em vez de seguir sem mascaramento."""
        caminho_sec, _ = self._criar_secrets_temporario(modo=0o600)
        with mock.patch.dict(sys.modules, {"masking": None}):
            with self.assertRaises(ImportError):
                sss_config.carregar_segredos(caminho_sec)

    def _cfg_com_log_dir(self, log_dir):
        cfg = sss_config.carregar(self.example_ini)
        return cfg._replace(logging=cfg.logging._replace(log_dir=log_dir))

    def test_log_dir_criado_com_0750_independente_da_umask(self):
        """O chmod apos makedirs garante 0o750 mesmo com umask restritiva."""
        log_dir = os.path.join(self.tmp_dir, "logs_novos")
        umask_anterior = os.umask(0o077)
        try:
            logger = sss_logging.configurar("teste_umask", self._cfg_com_log_dir(log_dir))
        finally:
            os.umask(umask_anterior)
        for h in list(logger.handlers):
            logger.removeHandler(h)
            h.close()
        self.assertEqual(stat.S_IMODE(os.stat(log_dir).st_mode), 0o750)

    def test_falha_no_chmod_do_log_dir_propaga(self):
        """Regressao: falha no chmod do log_dir aborta a configuracao (antes: except OSError: pass)."""
        log_dir = os.path.join(self.tmp_dir, "logs_chmod")
        with mock.patch("sss_logging.os.chmod", side_effect=PermissionError(1, "Operation not permitted")):
            with self.assertRaises(OSError):
                sss_logging.configurar("teste_chmod", self._cfg_com_log_dir(log_dir))

    def test_formato_log_readme_13(self):
        """Valida que o log gerado segue fielmente o formato do README §13."""
        cfg = sss_config.carregar(self.example_ini)
        # Substitui log_dir para diretorio temporario do teste
        cfg_tmp = cfg._replace(logging=cfg.logging._replace(log_dir=self.tmp_dir))

        logger = sss_logging.configurar("teste_formato", cfg_tmp)
        logger.info("Mensagem padrao sem contexto explicito")

        adapter = sss_logging.get_adapter(logger, agente="srv-prod-01", ticket="9876", acao="SPAWN")
        adapter.info("Processo filho instanciado com sucesso")

        log_path = logger.handlers[0].baseFilename
        self.assertTrue(os.path.isfile(log_path))
        self.assertIn(os.path.join(self.tmp_dir, "app"), log_path)

        with open(log_path, "r", encoding="utf-8") as f:
            linhas = [linha.strip() for linha in f if linha.strip()]

        self.assertGreaterEqual(len(linhas), 2)

        # Regex estrita do formato README §13:
        # %(asctime)s %(levelname)s [pid=%(process)d] [agente=<id>] [ticket=<id|->] [acao=<CLAIM|SPAWN|HB|...>] %(message)s
        # asctime: data ISO local com offset: YYYY-MM-DDTHH:MM:SS(.microseconds)?(Z|[+-]HH:MM)
        padrao = (
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)\s+"
            r"(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL)\s+"
            r"\[pid=\d+\]\s+\[agente=[^\]]+\]\s+\[ticket=[^\]]+\]\s+\[acao=[^\]]+\]\s+.*$"
        )

        for linha in linhas:
            self.assertRegex(linha, padrao, "Linha de log fora do padrao README §13: %s" % linha)

        # Verifica campos da linha emitida pelo adapter
        linha_adapter = linhas[1]
        self.assertIn("[agente=srv-prod-01]", linha_adapter)
        self.assertIn("[ticket=9876]", linha_adapter)
        self.assertIn("[acao=SPAWN]", linha_adapter)
        self.assertIn("Processo filho instanciado com sucesso", linha_adapter)

    def test_launchers_syntax_bash_n(self):
        """Verifica a sintaxe dos launchers bin/sss-web.sh e bin/sss-scheduler.sh."""
        web_sh = os.path.join(self.web2py_root, "bin", "sss-web.sh")
        scheduler_sh = os.path.join(self.web2py_root, "bin", "sss-scheduler.sh")

        self.assertTrue(os.path.isfile(web_sh), "Arquivo ausente: %s" % web_sh)
        self.assertTrue(os.path.isfile(scheduler_sh), "Arquivo ausente: %s" % scheduler_sh)

        res_web = subprocess.run(["bash", "-n", web_sh])
        self.assertEqual(res_web.returncode, 0, "bash -n falhou em sss-web.sh")

        res_sched = subprocess.run(["bash", "-n", scheduler_sh])
        self.assertEqual(res_sched.returncode, 0, "bash -n falhou em sss-scheduler.sh")

    @unittest.skipIf(os.geteuid() == 0, "o launcher recusa root antes de checar os argumentos")
    def test_launcher_web_recusa_comando_arbitrario(self):
        """CR-003 P10 (README §12.2): so o processo Python do SSS; nada de exec de comando arbitrario."""
        web_sh = os.path.join(self.web2py_root, "bin", "sss-web.sh")
        for args in (["/bin/sh", "-c", "id"], ["/usr/bin/python3", "outro.py"], ["python3"]):
            res = subprocess.run(["bash", web_sh] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertEqual(res.returncode, 2, args)


if __name__ == "__main__":
    unittest.main()


class TestConfigCR007(unittest.TestCase):
    """CR-007 (README §4.1, §8.6, §8.9, §12.1): chaves novas, invariantes I3/I4 e segredos por papel."""

    setUp = TestConfig.setUp
    tearDown = TestConfig.tearDown
    _copiar_e_modificar_ini = TestConfig._copiar_e_modificar_ini
    _criar_secrets_temporario = TestConfig._criar_secrets_temporario

    def _carregar(self, **alteracoes):
        return sss_config.carregar(self._copiar_e_modificar_ini(alteracoes=alteracoes))

    def _recusa(self, chave, **alteracoes):
        with self.assertRaises(sss_config.ConfigErro) as ctx:
            self._carregar(**alteracoes)
        self.assertEqual(ctx.exception.chave, chave, str(ctx.exception))
        return ctx.exception

    def test_padroes_das_chaves_novas(self):
        cfg = self._carregar()
        self.assertEqual(cfg.agent.usuarios_execucao, ())
        self.assertIsNone(cfg.agent.exec_work_dir)
        self.assertEqual(cfg.agent.fila_envelhecimento_min, 60)
        self.assertIsNone(cfg.retencao.purge_user)

    def test_prefixo_so_minusculas_e_agent_id_purge_reservado(self):
        self._recusa("table_prefix", oracle={"table_prefix": "TBSSS_"})
        self._recusa("agent_id", agent={"agent_id": "purge"})
        self.assertEqual(self._carregar(agent={"agent_id": "purge01"}).agent.agent_id, "purge01")

    def test_faixas_novas(self):
        self._recusa("cron_horizon_days", agent={"cron_horizon_days": "365"})
        self.assertEqual(self._carregar(agent={"cron_horizon_days": "366"}).agent.cron_horizon_days, 366)
        self._recusa("max_log_size_bytes", logging={"max_log_size_bytes": str(64 * 1024 * 1024 + 1)})
        self._recusa("audit_retention_days", retencao={"audit_retention_days": "364"})
        self._recusa("audit_retention_days", retencao={"audit_retention_days": "400", "ticket_retention_days": "500"})
        self._recusa("fila_envelhecimento_min", agent={"fila_envelhecimento_min": "1441"})
        self.assertEqual(self._carregar(agent={"fila_envelhecimento_min": "0"}).agent.fila_envelhecimento_min, 0)

    def test_invariantes_i3_e_i4(self):
        # I3: heartbeat + 2*call <= fence (10 + 2*41 = 92 > 90).
        self._recusa("fence_timeout_s", oracle={"call_timeout_ms": "41000"})
        # I4: fence + call + kill + 2 <= offline (90 + 30 + 60 + 2 = 182 > 180).
        self._recusa("node_offline_timeout_s", agent={"kill_grace_s": "60"})
        self.assertEqual(sss_config.call_timeout_s(30001), 31)
        self._carregar()  # o exemplo atende I3 = 70 <= 90 e I4 = 127 <= 180

    def test_usuarios_execucao_e_exec_work_dir(self):
        cfg = self._carregar(agent={"usuarios_execucao": "PRODUCAO=sssprd, HOMOLOGACAO=ssshml"})
        self.assertEqual(cfg.agent.usuarios_execucao, (("PRODUCAO", "sssprd"), ("HOMOLOGACAO", "ssshml")))
        self._recusa("usuarios_execucao", agent={"usuarios_execucao": "PRODUCAO=root"})
        self._recusa("usuarios_execucao", agent={"usuarios_execucao": "OUTRO=sssx"})
        self._recusa("usuarios_execucao", agent={"usuarios_execucao": "PRODUCAO"})
        self._recusa("usuarios_execucao", agent={"usuarios_execucao": "PRODUCAO=a,PRODUCAO=b"})
        # Fora de DEV: todo ambiente atendido precisa de usuario e exec_work_dir e obrigatoria.
        base = {"sss_env": "HML", "data_backend": "ORACLE"}
        ret = {"purge_user": "sss_purge"}
        self._recusa("usuarios_execucao", app=base, retencao=ret, agent={"usuarios_execucao": "PRODUCAO=sssprd"})
        self._recusa("exec_work_dir", app=base, retencao=ret,
                     agent={"usuarios_execucao": "PRODUCAO=sssprd,HOMOLOGACAO=ssshml"})
        self._recusa("exec_work_dir", app=base, retencao=ret,
                     agent={"usuarios_execucao": "PRODUCAO=sssprd,HOMOLOGACAO=ssshml",
                            "exec_work_dir": "/var/lib/sss/work/exec"})
        cfg = self._carregar(app=base, retencao=ret, agent={"usuarios_execucao": "PRODUCAO=sssprd,HOMOLOGACAO=ssshml",
                                                            "exec_work_dir": "/var/lib/sss/exec"})
        self.assertEqual(cfg.agent.exec_work_dir, "/var/lib/sss/exec")

    def test_purge_user_com_oracle(self):
        base = {"sss_env": "DEV", "data_backend": "ORACLE"}
        self._recusa("purge_user", app=base)
        self._recusa("purge_user", app=base, retencao={"purge_user": "SSS_WEB"})
        self._recusa("purge_user", app=base, retencao={"purge_user": "gfcadastro"})
        self.assertEqual(self._carregar(app=base, retencao={"purge_user": "sss_purge"}).retencao.purge_user, "sss_purge")

    def test_env_passthrough_lista_de_bloqueio_e_chaves_fixas(self):
        for var in ("BASH_FUNC_x%%", "LD_DEBUG", "MALLOC_ARENA_MAX", "GLIBC_TUNABLES", "PS4", "PATH", "LC_ALL",
                    "SSS_TICKET_ID", "PYTHONIOENCODING", "PADRAO_VALOR_RUN_CONEXAO_BD", "lang"):
            self._recusa("env_passthrough", agent={"env_passthrough": "ORACLE_HOME," + var})
        cfg = self._carregar(agent={"env_passthrough": "ORACLE_HOME,LD_LIBRARY_PATH,NLS_LANG,TNS_ADMIN"})
        self.assertIn("LD_LIBRARY_PATH", cfg.agent.env_passthrough)

    def test_ambientes_atendidos_cabem_na_coluna(self):
        nomes = ",".join("AMBIENTE_%04d_XXXXXXXXXXXXX" % i for i in range(40))
        self._recusa("ambientes_atendidos", agent={"ambientes_atendidos": nomes})

    def _secrets(self, secoes):
        caminho = os.path.join(self.tmp_dir, "secrets_papel.cfg")
        with open(caminho, "w", encoding="utf-8") as f:
            for nome, chaves in secoes:
                f.write("[%s]\n" % nome)
                for k, v in chaves.items():
                    f.write("%s = %s\n" % (k, v))
        os.chmod(caminho, 0o600)
        return caminho

    def test_segredos_por_papel(self):
        web = [("oracle", {"password": "senha-web-123"}), ("web", {"cookie_key": "chave-cookie-123"})]
        agente = [("oracle", {"password": "senha-agt-123"}), ("purge", {"password": "senha-prg-123"}),
                  ("ambiente:PRODUCAO", {"user": "app", "password": "senha-amb-123"})]
        seg = sss_config.carregar_segredos(self._secrets(agente), sss_env="PROD", data_backend="ORACLE", papel="agente")
        self.assertIsNone(seg.cookie_key)
        self.assertEqual(seg.purge_password, "senha-prg-123")
        self.assertIn("senha-prg-123", self.mascarados)
        self.assertNotIn("senha-prg-123", repr(seg))
        # Secao de outro papel: recusada em HML/PROD, so WARN em DEV.
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar_segredos(self._secrets(agente + [("web", {"cookie_key": "x" * 20})]),
                                         sss_env="PROD", data_backend="ORACLE", papel="agente")
        for extra in (("purge", {"password": "senha-prg-123"}), ("ambiente:PRODUCAO", {"user": "a", "password": "b"})):
            with self.assertRaises(sss_config.ConfigErro):
                sss_config.carregar_segredos(self._secrets(web + [extra]), sss_env="HML", data_backend="ORACLE")
            with self.assertLogs("sss_config", level="WARNING"):
                sss_config.carregar_segredos(self._secrets(web + [extra]), sss_env="DEV", data_backend="ORACLE")
        with self.assertRaises(sss_config.ConfigErro):
            sss_config.carregar_segredos(self._secrets(web), papel="agente_x")

    def test_segredos_do_agente_cobrem_os_ambientes(self):
        cfg = self._carregar(app={"sss_env": "HML", "data_backend": "ORACLE"}, retencao={"purge_user": "sss_purge"},
                             agent={"usuarios_execucao": "PRODUCAO=sssprd,HOMOLOGACAO=ssshml",
                                    "exec_work_dir": "/var/lib/sss/exec"})
        so_prod = [("oracle", {"password": "senha-agt-123"}),
                   ("ambiente:PRODUCAO", {"user": "app", "password": "senha-amb-123"})]
        with self.assertRaises(sss_config.ConfigErro) as ctx:
            sss_config.carregar_segredos(self._secrets(so_prod), cfg=cfg, papel="agente")
        self.assertIn("HOMOLOGACAO", str(ctx.exception))

    def test_codificacao_utf8_obrigatoria(self):
        with mock.patch.object(sss_config.sys, "getfilesystemencoding", return_value="ascii"):
            with self.assertRaises(sss_config.ConfigErro) as ctx:
                sss_config.verificar_codificacao()
        self.assertIn("UTF-8", str(ctx.exception))
        for cod in ("utf-8", "UTF8"):
            with mock.patch.object(sss_config.sys, "getfilesystemencoding", return_value=cod):
                sss_config.verificar_codificacao()
