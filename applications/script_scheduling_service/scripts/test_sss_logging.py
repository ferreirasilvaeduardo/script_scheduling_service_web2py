# -*- coding: utf-8 -*-
"""Testes unitarios para sss_logging e AppLogRotatingHandler (CR-005 D6, R-c, R-d, R-e, README §13)."""
import datetime
import os
import shutil
import stat
import tempfile
import unittest
from unittest import mock

import _testenv  # noqa: F401
import pastas_log
import sss_config
import sss_logging


class TestSSSLogging(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="sss_test_logging_")
        self.addCleanup(shutil.rmtree, self.tmp_dir, True)

    def _criar_cfg(self, log_dir, max_bytes=1048576, retention_days=30, level="INFO"):
        logging_dict = {
            "log_dir": log_dir,
            "level": level,
            "app_log_max_bytes": max_bytes,
            "app_log_retention_days": retention_days,
            "max_log_size_bytes": 5242880,
            "max_local_log_size_bytes": 52428800,
            "local_log_retention_days": 30,
            "output_retention_days": 7,
        }
        logging_cfg = sss_config.LoggingConfig(**logging_dict)
        cfg = mock.MagicMock()
        cfg.logging = logging_cfg
        cfg.agent.agent_id = "srv-test-01"
        return cfg

    def test_handler_cria_caminho_por_minuto_e_permissoes(self):
        """CR-005 D6 e CR-009: log em log_dir/interno/app/AAAA/MM/DD/HH/MI/<nome_log>_<PID>.log com 0750 e 0640."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        cfg = self._criar_cfg(log_dir)

        logger = sss_logging.configurar("sss_web", cfg)
        self.addCleanup(lambda: [h.close() for h in list(logger.handlers)])

        logger.info("Teste de subida do log")

        self.assertEqual(len(logger.handlers), 1)
        handler = logger.handlers[0]
        self.assertIsInstance(handler, sss_logging.AppLogRotatingHandler)

        log_path = handler.baseFilename
        self.assertTrue(os.path.isfile(log_path))

        pid = os.getpid()
        self.assertTrue(os.path.basename(log_path).startswith("sss_web_%d" % pid))
        self.assertTrue(log_path.endswith(".log"))

        # Diretorio: interno/app/AAAA/MM/DD/HH/MI (CR-009: log sem ambiente fica em 'interno')
        partes = os.path.relpath(os.path.dirname(log_path), log_dir).split(os.sep)
        self.assertEqual(partes[:2], ["interno", "app"])
        self.assertEqual(len(partes), 7)  # interno, app, AAAA, MM, DD, HH, MI

        # Permissoes: diretorio 0o750 e arquivo 0o640
        dir_stat = os.stat(os.path.dirname(log_path))
        self.assertEqual(stat.S_IMODE(dir_stat.st_mode), 0o750)
        file_stat = os.stat(log_path)
        self.assertEqual(stat.S_IMODE(file_stat.st_mode), 0o640)

    def test_troca_por_tamanho_no_mesmo_minuto_ganha_sufixo(self):
        """CR-005 R-c: troca por tamanho dentro do mesmo minuto gera sufixo _<n>."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        # max_bytes pequeno para forcar rollover rapido
        handler = sss_logging.AppLogRotatingHandler(
            log_dir=log_dir,
            nome_processo="sss_web",
            max_bytes=300,
            retention_days=30,
            pid=9999
        )
        self.addCleanup(handler.close)
        formatter = sss_logging.SSSFormatter(sss_logging.FMT_SSS)
        handler.setFormatter(formatter)

        caminho_1 = handler.baseFilename
        self.assertTrue(caminho_1.endswith("sss_web_9999.log"))

        # Emite registros ate forcar rollover
        logger = sss_logging.logging.getLogger("teste_rollover_mesmo_minuto")
        logger.setLevel(sss_logging.logging.INFO)
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)

        while handler.baseFilename == caminho_1:
            logger.info("Mensagem de teste para encher o arquivo")

        caminho_2 = handler.baseFilename
        self.assertNotEqual(caminho_1, caminho_2)
        self.assertTrue(caminho_2.endswith("sss_web_9999_2.log"))
        self.assertTrue(os.path.exists(caminho_1))
        self.assertTrue(os.path.exists(caminho_2))

        # Mais mensagens ate provocar terceira rotacao (_3.log)
        while handler.baseFilename == caminho_2:
            logger.info("Mais mensagens para provocar terceira rotacao")

        caminho_3 = handler.baseFilename
        self.assertTrue(caminho_3.endswith("sss_web_9999_3.log"))
        self.assertTrue(os.path.exists(caminho_3))

    def test_troca_por_tamanho_em_minuto_diferente(self):
        """CR-005 D6: troca de arquivo em minuto novo abre na pasta do minuto atual."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        dt_t0 = datetime.datetime(2026, 10, 16, 8, 30, 0)
        dt_t1 = datetime.datetime(2026, 10, 16, 8, 31, 0)

        with mock.patch("sss_logging.datetime.datetime") as mock_dt, mock.patch("pastas_log.datetime.datetime", mock_dt):
            mock_dt.now.return_value = dt_t0
            mock_dt.side_effect = lambda *args, **kw: datetime.datetime(*args, **kw)
            handler = sss_logging.AppLogRotatingHandler(
                log_dir=log_dir,
                nome_processo="sss_scheduler",
                max_bytes=200,
                retention_days=30,
                pid=1234
            )
            self.addCleanup(handler.close)
            formatter = sss_logging.SSSFormatter(sss_logging.FMT_SSS)
            handler.setFormatter(formatter)

            caminho_0 = handler.baseFilename
            self.assertIn(os.path.join("2026", "10", "16", "08", "30"), caminho_0)
            self.assertTrue(caminho_0.endswith("sss_scheduler_1234.log"))

            logger = sss_logging.logging.getLogger("teste_rollover_outro_minuto")
            logger.setLevel(sss_logging.logging.INFO)
            logger.addHandler(handler)
            self.addCleanup(logger.removeHandler, handler)

            # Agora avancamos o relogio para t1
            mock_dt.now.return_value = dt_t1
            while handler.baseFilename == caminho_0:
                logger.info("Registro de teste para estourar tamanho")

            caminho_1 = handler.baseFilename
            self.assertIn(os.path.join("2026", "10", "16", "08", "31"), caminho_1)
            self.assertTrue(caminho_1.endswith("sss_scheduler_1234.log"))
            self.assertTrue(os.path.exists(caminho_0))
            self.assertTrue(os.path.exists(caminho_1))

    def test_retencao_na_subida_e_na_troca(self):
        """CR-005 R-d: apaga pastas interno/app/AAAA/MM/DD anteriores a retention_days dias."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        hoje = datetime.datetime(2026, 10, 16, 12, 0, 0)

        # Cria estrutura de pastas antigas e recentes em log_dir/interno/app/
        # Limite de 30 dias a partir de 2026-10-16 e 2026-09-16
        pasta_expirada_1 = os.path.join(log_dir, "interno", "app", "2026", "08", "15", "10", "00")
        pasta_expirada_2 = os.path.join(log_dir, "interno", "app", "2026", "09", "15", "23", "59")
        pasta_limite = os.path.join(log_dir, "interno", "app", "2026", "09", "16", "00", "00")
        pasta_recente = os.path.join(log_dir, "interno", "app", "2026", "10", "10", "12", "00")
        pasta_nao_data = os.path.join(log_dir, "interno", "app", "2026", "temp", "teste")

        for p in (pasta_expirada_1, pasta_expirada_2, pasta_limite, pasta_recente, pasta_nao_data):
            os.makedirs(p, exist_ok=True)
            with open(os.path.join(p, "dummy.log"), "w", encoding="utf-8") as f:
                f.write("log antigo")

        with mock.patch("sss_logging.datetime.datetime") as mock_dt, mock.patch("pastas_log.datetime.datetime", mock_dt):
            mock_dt.now.return_value = hoje
            mock_dt.side_effect = lambda *args, **kw: datetime.datetime(*args, **kw)

            # Subida do handler deve executar a retencao
            handler = sss_logging.AppLogRotatingHandler(
                log_dir=log_dir,
                nome_processo="sss_web",
                max_bytes=1048576,
                retention_days=30,
                pid=5000
            )
            self.addCleanup(handler.close)

            # Expiradas devem ter sido apagadas
            self.assertFalse(os.path.exists(pasta_expirada_1))
            self.assertFalse(os.path.exists(pasta_expirada_2))
            # Mes 08 ficou vazio, entao o diretorio do mes 08 deve sumir
            self.assertFalse(os.path.exists(os.path.join(log_dir, "interno", "app", "2026", "08")))

            # Limite (30 dias exatos) e recente devem permanecer
            self.assertTrue(os.path.exists(pasta_limite))
            self.assertTrue(os.path.exists(pasta_recente))

            # Pasta sem formato de data (temp) deve ser ignorada
            self.assertTrue(os.path.exists(pasta_nao_data))

    def test_todas_as_pastas_novas_com_0750_sob_umask_077(self):
        """Regressao (README §13): app/, ano, mes, dia, hora e minuto com 0750, mesmo com a umask 077 do launcher."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        os.makedirs(log_dir)
        umask_antiga = os.umask(0o077)
        try:
            logger = sss_logging.configurar("sss_web", self._criar_cfg(log_dir))
        finally:
            os.umask(umask_antiga)
        self.addCleanup(lambda: [h.close() for h in list(logger.handlers)])
        pasta = os.path.dirname(logger.handlers[0].baseFilename)
        niveis = []
        while pasta != log_dir:
            niveis.append(pasta)
            pasta = os.path.dirname(pasta)
        self.assertEqual(len(niveis), 7)  # interno, app, AAAA, MM, DD, HH, MI (CR-009)
        for nivel in niveis:
            self.assertEqual(stat.S_IMODE(os.stat(nivel).st_mode), 0o750, nivel)

    def test_agent_id_aparece_nas_linhas(self):
        """Regressao do R4: o agent_id do config.ini entra em [agente=...] (README §13)."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        logger = sss_logging.configurar("sss_web", self._criar_cfg(log_dir))
        self.addCleanup(lambda: [h.close() for h in list(logger.handlers)])
        logger.info("linha sem contexto")
        sss_logging.get_adapter(logger, agente="agt-explicito", ticket=7, acao="CLAIM").info("com contexto")
        logger.handlers[0].flush()
        with open(logger.handlers[0].baseFilename, encoding="utf-8") as f:
            linhas = f.read().splitlines()
        self.assertIn("[agente=srv-test-01] [ticket=-] [acao=-] linha sem contexto", linhas[0])
        self.assertIn("[agente=agt-explicito] [ticket=7] [acao=CLAIM] com contexto", linhas[1])

    def test_falha_na_retencao_vira_warn_no_log(self):
        """Regressao (AGENTS §6): falha da retencao nao e engolida; vira WARN [acao=RETENCAO]."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        antiga = os.path.join(log_dir, "interno", "app", "2000", "01", "01", "00", "00")
        os.makedirs(antiga)
        with mock.patch("pastas_log.shutil.rmtree", side_effect=PermissionError(13, "Permission denied")):
            logger = sss_logging.configurar("sss_web", self._criar_cfg(log_dir))
        self.addCleanup(lambda: [h.close() for h in list(logger.handlers)])
        logger.info("primeira linha")
        logger.handlers[0].flush()
        with open(logger.handlers[0].baseFilename, encoding="utf-8") as f:
            linhas = f.read().splitlines()
        self.assertEqual(len(linhas), 2)
        self.assertIn(" WARNING ", linhas[0])
        self.assertIn("[agente=srv-test-01] [ticket=-] [acao=RETENCAO]", linhas[0])
        self.assertIn(os.path.join(log_dir, "interno", "app", "2000", "01", "01"), linhas[0])
        self.assertIn("primeira linha", linhas[1])
        self.assertTrue(os.path.isdir(antiga))

    def test_reconfigurar_idempotente_nao_duplica_handlers(self):
        """Chamar configurar() varias vezes nao acumula AppLogRotatingHandler."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        cfg = self._criar_cfg(log_dir)

        logger1 = sss_logging.configurar("sss_web", cfg)
        self.assertEqual(len(logger1.handlers), 1)

        logger2 = sss_logging.configurar("sss_web", cfg)
        self.assertIs(logger1, logger2)
        self.assertEqual(len(logger2.handlers), 1)

        # obter_logger tambem devolve o mesmo singleton
        logger3 = sss_logging.obter_logger("sss_web", cfg)
        self.assertIs(logger1, logger3)


if __name__ == "__main__":
    unittest.main()
