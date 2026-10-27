# -*- coding: utf-8 -*-
"""Testes de log_paths.py: README §8.4, §11.3, §13, AGENTS §7.4 e CR-005 (D5, D6, D7, R-a a R-e)."""
from tests.support import _testenv  # noqa: F401

import datetime
import os
import shutil
import tempfile
import unittest

from sss.config import log_paths


class TestLogDirs(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sss_test_plog_")
        self.addCleanup(shutil.rmtree, self.tmp)

    # -----------------------------------------------------------------------
    # 1. Pasta do script e nome reservado (CR-005 D7, R-a)
    # -----------------------------------------------------------------------

    def test_pasta_script_sanitizacao(self):
        # Acentos NFKD -> ASCII, minusculas, espacos e especiais viram '_'
        self.assertEqual(log_paths.script_dir(u"Carga Diária"), "carga_diaria")
        self.assertEqual(log_paths.script_dir(u"EXTRATOR DE RELATÓRIOS"), "extrator_de_relatorios")
        self.assertEqual(log_paths.script_dir(u"Carga / Processamento (v1.0)"), "carga_processamento_v1.0")

    def test_pasta_script_pontas_e_vazio(self):
        # Sem '.' ou '_' nas pontas
        self.assertEqual(log_paths.script_dir(u"..._carga_diaria_..."), "carga_diaria")
        self.assertEqual(log_paths.script_dir(u"___"), "script")
        self.assertEqual(log_paths.script_dir(u"", script_id=42), "script_42")
        self.assertEqual(log_paths.script_dir(None, script_id=10), "script_10")
        self.assertEqual(log_paths.script_dir(u""), "script")

    def test_nome_reservado_app(self):
        # D7: pasta 'app' e reservada para os logs da aplicacao
        self.assertTrue(log_paths.is_reserved_name("app"))
        self.assertTrue(log_paths.is_reserved_name("APP"))
        self.assertTrue(log_paths.is_reserved_name("App"))
        self.assertTrue(log_paths.is_reserved_name(u"  Ápp  "))
        self.assertTrue(log_paths.is_reserved_name("..app.."))
        self.assertFalse(log_paths.is_reserved_name("app_web"))
        self.assertFalse(log_paths.is_reserved_name("aplicacao"))
        self.assertFalse(log_paths.is_reserved_name("carga_diaria"))

    # -----------------------------------------------------------------------
    # 2. Logs de execucao de tickets (CR-005 D5, R-a, R-b, README §8.4)
    # -----------------------------------------------------------------------

    def test_diretorio_log_execucao(self):
        dt = datetime.datetime(2026, 4, 5, 8, 9, 30)
        d = log_paths.run_log_dir("/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs", "PRODUCAO", u"Carga Diária", dt)
        self.assertEqual(d, "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs/producao/carga_diaria/2026/04/05/08/09")

    def test_pasta_saida_com_as_partes_do_log(self):
        # CR-012 (README §8.13): base por ambiente e relativo no formato que o helper confere.
        dt = datetime.datetime(2026, 4, 5, 8, 9, 30)
        base, rel = log_paths.output_dir("/srv/sss/output", "PRODUCAO", u"Carga Diária", dt, 41)
        self.assertEqual((base, rel), ("/srv/sss/output/producao", "carga_diaria/2026/04/05/08/09/ticket_41"))
        self.assertEqual(os.path.join(base, os.path.dirname(rel)).replace("/srv/sss/output", "/x"),
                         log_paths.run_log_dir("/x", "PRODUCAO", u"Carga Diária", dt))
        self.assertEqual(log_paths.output_dir("/s", "HML", u"!!!", dt, 7, script_id=3)[1],
                         "script_3/2026/04/05/08/09/ticket_7")

    def test_cr019_pasta_de_trabalho_com_as_partes_da_saida(self):
        # CR-019 (README §8.15): mesmo formato da pasta de saida, sob a base propria.
        dt = datetime.datetime(2026, 4, 5, 8, 9, 30)
        self.assertEqual(log_paths.script_work_dir("/srv/sss/work", "PRODUCAO", u"Carga Diária", dt, 41),
                         ("/srv/sss/work/producao", "carga_diaria/2026/04/05/08/09/ticket_41"))
        self.assertEqual(log_paths.script_work_dir("/w", "HML", u"!!!", dt, 7, script_id=3)[1],
                         log_paths.output_dir("/s", "HML", u"!!!", dt, 7, script_id=3)[1])

    def test_pasta_entrada_so_ambiente_e_script(self):
        # CR-014 (README §8.14): permanente, sem data nem ticket; nome do script minusculo, sem acento nem espaco.
        self.assertEqual(log_paths.input_dir("/srv/sss/input", "PRODUCAO", u"Carga Diária"),
                         ("/srv/sss/input/producao", "carga_diaria"))
        self.assertEqual(log_paths.input_dir("/e", "HML", u"Extrator de Relatórios v2"),
                         ("/e/hml", "extrator_de_relatorios_v2"))
        self.assertEqual(log_paths.input_dir("/e", "HML", u"!!!", script_id=3), ("/e/hml", "script_3"))

    def test_ambiente_no_topo_obrigatorio_e_normalizado(self):
        # CR-009: pasta do ambiente antes de qualquer outra; minusculo, sem espaco nem especial.
        dt = datetime.datetime(2026, 4, 5, 8, 9, 30)
        self.assertEqual(log_paths.environment_dir("PRODUCAO"), "producao")
        self.assertEqual(log_paths.environment_dir("HOMOLOG_2"), "homolog_2")
        self.assertEqual(log_paths.environment_dir(u" Pré Produção! "), "pre_producao")
        for empty in (None, "", "   ", "!!!", u"\u00a7"):
            with self.assertRaises(ValueError):
                log_paths.environment_dir(empty)
            with self.assertRaises(ValueError):
                log_paths.run_log_dir("/l", empty, "carga", dt)
        for reserved in ("INTERNAL", "internal", " Internal "):
            with self.assertRaises(ValueError):
                log_paths.environment_dir(reserved)
            self.assertTrue(log_paths.is_reserved_environment(reserved))
        self.assertFalse(log_paths.is_reserved_environment("PRODUCAO"))
        self.assertFalse(log_paths.is_reserved_environment("INTERNAL_2"))
        self.assertFalse(log_paths.is_reserved_environment(""))

    def test_nomes_log_execucao_parcial_e_final(self):
        self.assertEqual(log_paths.partial_log_name(101), "ticket_101.log.parcial")
        # PID presente
        self.assertEqual(log_paths.run_log_name(101, pid=5432), "ticket_101_5432.log")
        # PID ausente ou zero (SPAWN_ERROR) -> ticket_<id>_0.log (R-b)
        self.assertEqual(log_paths.run_log_name(101, pid=0), "ticket_101_0.log")
        self.assertEqual(log_paths.run_log_name(101, pid=None), "ticket_101_0.log")

    def test_caminhos_completos_log_execucao(self):
        dt = datetime.datetime(2026, 10, 16, 14, 5, 0)
        c_partial = log_paths.partial_log_path("/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs", "DEV", "carga", dt, 77)
        self.assertEqual(c_partial, "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs/dev/carga/2026/10/16/14/05/ticket_77.log.parcial")

        c_final = log_paths.run_log_path("/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs", "DEV", "carga", dt, 77, pid=1234)
        self.assertEqual(c_final, "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs/dev/carga/2026/10/16/14/05/ticket_77_1234.log")

        c_error = log_paths.run_log_path("/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs", "DEV", "carga", dt, 77, pid=0)
        self.assertEqual(c_error, "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs/dev/carga/2026/10/16/14/05/ticket_77_0.log")

    # -----------------------------------------------------------------------
    # 3. Logs da aplicacao (CR-005 D6, R-c, R-d, R-e, README §13)
    # -----------------------------------------------------------------------

    def test_diretorio_e_nome_log_app(self):
        dt = datetime.datetime(2026, 10, 16, 8, 54, 0)
        d = log_paths.app_log_dir("/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs", dt)
        self.assertEqual(d, "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs/internal/app/2026/10/16/08/54")

        self.assertEqual(log_paths.app_log_name("sss_web", 4321), "sss_web_4321.log")
        self.assertEqual(log_paths.app_log_name("sss_web.log", 4321), "sss_web_4321.log")
        # Sufixo de rotacao dentro do mesmo minuto (R-c)
        self.assertEqual(log_paths.app_log_name("sss_web", 4321, seq=2), "sss_web_4321_2.log")
        self.assertEqual(log_paths.app_log_name("sss_web", 4321, seq=3), "sss_web_4321_3.log")

    def test_caminho_log_app(self):
        dt = datetime.datetime(2026, 10, 16, 8, 54, 12)
        c = log_paths.app_log_path("/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs", "sss_web", 4321, dt)
        self.assertEqual(c, "/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/logs/internal/app/2026/10/16/08/54/sss_web_4321.log")

    def test_proximo_caminho_log_app_com_sufixo_rotacao(self):
        # R-c: colisoes dentro do mesmo minuto e PID geram _2, _3, ...
        dt = datetime.datetime(2026, 10, 16, 8, 54, 0)
        d = log_paths.app_log_dir(self.tmp, dt)
        os.makedirs(d)

        # Sem arquivo existente -> nome padrao
        c1 = log_paths.next_app_log_path(self.tmp, "sss_web", 4321, dt)
        self.assertEqual(c1, os.path.join(d, "sss_web_4321.log"))

        # Cria o primeiro arquivo
        with open(c1, "w") as f:
            f.write("log 1\n")

        # Proximo deve ser _2
        c2 = log_paths.next_app_log_path(self.tmp, "sss_web", 4321, dt)
        self.assertEqual(c2, os.path.join(d, "sss_web_4321_2.log"))

        # Cria o segundo arquivo
        with open(c2, "w") as f:
            f.write("log 2\n")

        # Proximo deve ser _3
        c3 = log_paths.next_app_log_path(self.tmp, "sss_web", 4321, dt)
        self.assertEqual(c3, os.path.join(d, "sss_web_4321_3.log"))


if __name__ == "__main__":
    unittest.main()

