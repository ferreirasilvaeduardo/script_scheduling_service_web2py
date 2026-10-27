# -*- coding: utf-8 -*-
"""Testes unitarios para sss_logging e AppLogRotatingHandler (CR-005 D6, R-c, R-d, R-e, README §13)."""
import datetime
import os
import shutil
import stat
import tempfile
import unittest
from unittest import mock

from tests.support import _testenv  # noqa: F401
from sss.config import log_paths
from sss.config import sss_config
from sss.config import sss_logging


class TestSSSLogging(unittest.TestCase):

    def setUp(self):
        # Avisos pendentes de outro teste (CR-026f/CR-032) iriam para o log deste.
        sss_config.pending_warnings()
        self.tmp_dir = tempfile.mkdtemp(prefix="sss_test_logging_")
        self.addCleanup(shutil.rmtree, self.tmp_dir, True)

    def _create_cfg(self, log_dir, max_bytes=1048576, level="INFO"):
        logging_dict = {
            "log_dir": log_dir,
            "level": level,
            "app_log_max_bytes": max_bytes,
            "max_log_size_bytes": 5242880,
            "max_local_log_size_bytes": 52428800,
        }
        logging_cfg = sss_config.LoggingConfig(**logging_dict)
        cfg = mock.MagicMock()
        cfg.logging = logging_cfg
        cfg.agent.agent_id = "srv-test-01"
        return cfg

    def test_handler_cria_caminho_por_minuto_e_permissoes(self):
        """CR-005 D6 e CR-009: log em log_dir/internal/app/AAAA/MM/DD/HH/MI/<log_name>_<PID>.log com 0750 e 0640."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        cfg = self._create_cfg(log_dir)

        logger = sss_logging.configure("sss_web", cfg)
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

        # Diretorio: internal/app/AAAA/MM/DD/HH/MI (CR-009: log sem ambiente fica em 'internal')
        parts = os.path.relpath(os.path.dirname(log_path), log_dir).split(os.sep)
        self.assertEqual(parts[:2], ["internal", "app"])
        self.assertEqual(len(parts), 7)  # interno, app, AAAA, MM, DD, HH, MI

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
            process_name="sss_web",
            max_bytes=300,
            pid=9999
        )
        self.addCleanup(handler.close)
        formatter = sss_logging.SSSFormatter(sss_logging.FMT_SSS)
        handler.setFormatter(formatter)

        path_1 = handler.baseFilename
        self.assertTrue(path_1.endswith("sss_web_9999.log"))

        # Emite registros ate forcar rollover
        logger = sss_logging.logging.getLogger("teste_rollover_mesmo_minuto")
        logger.setLevel(sss_logging.logging.INFO)
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)

        while handler.baseFilename == path_1:
            logger.info("Mensagem de teste para encher o arquivo")

        path_2 = handler.baseFilename
        self.assertNotEqual(path_1, path_2)
        self.assertTrue(path_2.endswith("sss_web_9999_2.log"))
        self.assertTrue(os.path.exists(path_1))
        self.assertTrue(os.path.exists(path_2))

        # Mais mensagens ate provocar terceira rotacao (_3.log)
        while handler.baseFilename == path_2:
            logger.info("Mais mensagens para provocar terceira rotacao")

        path_3 = handler.baseFilename
        self.assertTrue(path_3.endswith("sss_web_9999_3.log"))
        self.assertTrue(os.path.exists(path_3))

    def test_troca_por_tamanho_em_minuto_diferente(self):
        """CR-005 D6: troca de arquivo em minuto novo abre na pasta do minuto atual."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        dt_t0 = datetime.datetime(2026, 10, 16, 8, 30, 0)
        dt_t1 = datetime.datetime(2026, 10, 16, 8, 31, 0)

        with mock.patch("sss.config.sss_logging.datetime.datetime") as mock_dt:
            mock_dt.now.return_value = dt_t0
            mock_dt.side_effect = lambda *args, **kw: datetime.datetime(*args, **kw)
            handler = sss_logging.AppLogRotatingHandler(
                log_dir=log_dir,
                process_name="sss_scheduler",
                max_bytes=200,
                pid=1234
            )
            self.addCleanup(handler.close)
            formatter = sss_logging.SSSFormatter(sss_logging.FMT_SSS)
            handler.setFormatter(formatter)

            path_0 = handler.baseFilename
            self.assertIn(os.path.join("2026", "10", "16", "08", "30"), path_0)
            self.assertTrue(path_0.endswith("sss_scheduler_1234.log"))

            logger = sss_logging.logging.getLogger("teste_rollover_outro_minuto")
            logger.setLevel(sss_logging.logging.INFO)
            logger.addHandler(handler)
            self.addCleanup(logger.removeHandler, handler)

            # Agora avancamos o relogio para t1
            mock_dt.now.return_value = dt_t1
            while handler.baseFilename == path_0:
                logger.info("Registro de teste para estourar tamanho")

            path_1 = handler.baseFilename
            self.assertIn(os.path.join("2026", "10", "16", "08", "31"), path_1)
            self.assertTrue(path_1.endswith("sss_scheduler_1234.log"))
            self.assertTrue(os.path.exists(path_0))
            self.assertTrue(os.path.exists(path_1))

    def test_todas_as_pastas_novas_com_0750_sob_umask_077(self):
        """Regressao (README §13): app/, ano, mes, dia, hora e minuto com 0750, mesmo com a umask 077 do launcher."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        os.makedirs(log_dir)
        umask_old = os.umask(0o077)
        try:
            logger = sss_logging.configure("sss_web", self._create_cfg(log_dir))
        finally:
            os.umask(umask_old)
        self.addCleanup(lambda: [h.close() for h in list(logger.handlers)])
        dir_value = os.path.dirname(logger.handlers[0].baseFilename)
        levels = []
        while dir_value != log_dir:
            levels.append(dir_value)
            dir_value = os.path.dirname(dir_value)
        self.assertEqual(len(levels), 7)  # interno, app, AAAA, MM, DD, HH, MI (CR-009)
        for level in levels:
            self.assertEqual(stat.S_IMODE(os.stat(level).st_mode), 0o750, level)

    def test_cr026_aviso_do_config_vai_para_o_log_da_aplicacao(self):
        """CR-026f: o aviso guardado pelo load() (ex.: linha [agent] interpreters) e gravado pelo configure()."""
        from sss.config import sss_config
        sss_config.pending_warnings()
        sss_config._PENDING_WARNINGS.append("config.ini: chave [agent] interpreters ignorada: teste")
        log_dir = os.path.join(self.tmp_dir, "logs")
        logger = sss_logging.configure("sss_web", self._create_cfg(log_dir))
        self.addCleanup(lambda: [h.close() for h in list(logger.handlers)])
        logger.handlers[0].flush()
        with open(logger.handlers[0].baseFilename, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("WARNING", text)
        self.assertIn("[action=INICIO] config.ini: chave [agent] interpreters ignorada: teste", text)
        self.assertEqual(sss_config.pending_warnings(), [])

    def test_agent_id_aparece_nas_linhas(self):
        """Regressao do R4: o agent_id do config.ini entra em [agent=...] (README §13)."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        logger = sss_logging.configure("sss_web", self._create_cfg(log_dir))
        self.addCleanup(lambda: [h.close() for h in list(logger.handlers)])
        logger.info("linha sem contexto")
        sss_logging.get_adapter(logger, agent="agt-explicito", ticket=7, action="CLAIM").info("com contexto")
        logger.handlers[0].flush()
        with open(logger.handlers[0].baseFilename, encoding="utf-8") as f:
            rows = f.read().splitlines()
        self.assertIn("[agent=srv-test-01] [ticket=-] [action=-] linha sem contexto", rows[0])
        self.assertIn("[agent=agt-explicito] [ticket=7] [action=CLAIM] com contexto", rows[1])

    def test_cr030_sem_retencao_automatica(self):
        """CR-030: o log da aplicacao nao apaga nada (limpeza manual, README §11.3)."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        old = os.path.join(log_dir, "internal", "app", "2000", "01", "01", "00", "00")
        os.makedirs(old)
        logger = sss_logging.configure("sss_web", self._create_cfg(log_dir))
        self.addCleanup(lambda: [h.close() for h in list(logger.handlers)])
        logger.info("primeira linha")
        self.assertTrue(os.path.isdir(old))
        self.assertFalse(hasattr(logger.handlers[0], "executar_retencao"))

    def test_reconfigurar_idempotente_nao_duplica_handlers(self):
        """Chamar configurar() varias vezes nao acumula AppLogRotatingHandler."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        cfg = self._create_cfg(log_dir)

        logger1 = sss_logging.configure("sss_web", cfg)
        self.assertEqual(len(logger1.handlers), 1)

        logger2 = sss_logging.configure("sss_web", cfg)
        self.assertIs(logger1, logger2)
        self.assertEqual(len(logger2.handlers), 1)

        # get_logger tambem devolve o mesmo singleton
        logger3 = sss_logging.get_logger("sss_web", cfg)
        self.assertIs(logger1, logger3)


if __name__ == "__main__":
    unittest.main()
