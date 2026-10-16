# -*- coding: utf-8 -*-
"""Testes de pastas_log.py: README §8.4, §11.3, §13, AGENTS §7.4 e CR-005 (D5, D6, D7, R-a a R-e)."""
import _testenv  # noqa: F401

import datetime
import os
import shutil
import tempfile
import unittest

import pastas_log


class TestPastasLog(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sss_test_plog_")
        self.addCleanup(shutil.rmtree, self.tmp)

    # -----------------------------------------------------------------------
    # 1. Pasta do script e nome reservado (CR-005 D7, R-a)
    # -----------------------------------------------------------------------

    def test_pasta_script_sanitizacao(self):
        # Acentos NFKD -> ASCII, minusculas, espacos e especiais viram '_'
        self.assertEqual(pastas_log.pasta_script(u"Carga Diária"), "carga_diaria")
        self.assertEqual(pastas_log.pasta_script(u"EXTRATOR DE RELATÓRIOS"), "extrator_de_relatorios")
        self.assertEqual(pastas_log.pasta_script(u"Carga / Processamento (v1.0)"), "carga_processamento_v1.0")

    def test_pasta_script_pontas_e_vazio(self):
        # Sem '.' ou '_' nas pontas
        self.assertEqual(pastas_log.pasta_script(u"..._carga_diaria_..."), "carga_diaria")
        self.assertEqual(pastas_log.pasta_script(u"___"), "script")
        self.assertEqual(pastas_log.pasta_script(u"", script_id=42), "script_42")
        self.assertEqual(pastas_log.pasta_script(None, script_id=10), "script_10")
        self.assertEqual(pastas_log.pasta_script(u""), "script")

    def test_nome_reservado_app(self):
        # D7: pasta 'app' e reservada para os logs da aplicacao
        self.assertTrue(pastas_log.nome_reservado("app"))
        self.assertTrue(pastas_log.nome_reservado("APP"))
        self.assertTrue(pastas_log.nome_reservado("App"))
        self.assertTrue(pastas_log.nome_reservado(u"  Ápp  "))
        self.assertTrue(pastas_log.nome_reservado("..app.."))
        self.assertFalse(pastas_log.nome_reservado("app_web"))
        self.assertFalse(pastas_log.nome_reservado("aplicacao"))
        self.assertFalse(pastas_log.nome_reservado("carga_diaria"))

    # -----------------------------------------------------------------------
    # 2. Logs de execucao de tickets (CR-005 D5, R-a, R-b, README §8.4)
    # -----------------------------------------------------------------------

    def test_diretorio_log_execucao(self):
        dt = datetime.datetime(2026, 4, 5, 8, 9, 30)
        d = pastas_log.diretorio_log_execucao("/var/log/sss", u"Carga Diária", dt)
        self.assertEqual(d, "/var/log/sss/carga_diaria/2026/04/05/08/09")

    def test_nomes_log_execucao_parcial_e_final(self):
        self.assertEqual(pastas_log.nome_log_parcial(101), "ticket_101.log.parcial")
        # PID presente
        self.assertEqual(pastas_log.nome_log_execucao(101, pid=5432), "ticket_101_5432.log")
        # PID ausente ou zero (SPAWN_ERROR) -> ticket_<id>_0.log (R-b)
        self.assertEqual(pastas_log.nome_log_execucao(101, pid=0), "ticket_101_0.log")
        self.assertEqual(pastas_log.nome_log_execucao(101, pid=None), "ticket_101_0.log")

    def test_caminhos_completos_log_execucao(self):
        dt = datetime.datetime(2026, 10, 16, 14, 5, 0)
        c_parcial = pastas_log.caminho_log_parcial("/var/log/sss", "carga", dt, 77)
        self.assertEqual(c_parcial, "/var/log/sss/carga/2026/10/16/14/05/ticket_77.log.parcial")

        c_final = pastas_log.caminho_log_execucao("/var/log/sss", "carga", dt, 77, pid=1234)
        self.assertEqual(c_final, "/var/log/sss/carga/2026/10/16/14/05/ticket_77_1234.log")

        c_erro = pastas_log.caminho_log_execucao("/var/log/sss", "carga", dt, 77, pid=0)
        self.assertEqual(c_erro, "/var/log/sss/carga/2026/10/16/14/05/ticket_77_0.log")

    # -----------------------------------------------------------------------
    # 3. Logs da aplicacao (CR-005 D6, R-c, R-d, R-e, README §13)
    # -----------------------------------------------------------------------

    def test_diretorio_e_nome_log_app(self):
        dt = datetime.datetime(2026, 10, 16, 8, 54, 0)
        d = pastas_log.diretorio_log_app("/var/log/sss", dt)
        self.assertEqual(d, "/var/log/sss/app/2026/10/16/08/54")

        self.assertEqual(pastas_log.nome_log_app("sss_web", 4321), "sss_web_4321.log")
        self.assertEqual(pastas_log.nome_log_app("sss_web.log", 4321), "sss_web_4321.log")
        # Sufixo de rotacao dentro do mesmo minuto (R-c)
        self.assertEqual(pastas_log.nome_log_app("sss_web", 4321, seq=2), "sss_web_4321_2.log")
        self.assertEqual(pastas_log.nome_log_app("sss_web", 4321, seq=3), "sss_web_4321_3.log")

    def test_caminho_log_app(self):
        dt = datetime.datetime(2026, 10, 16, 8, 54, 12)
        c = pastas_log.caminho_log_app("/var/log/sss", "sss_web", 4321, dt)
        self.assertEqual(c, "/var/log/sss/app/2026/10/16/08/54/sss_web_4321.log")

    def test_proximo_caminho_log_app_com_sufixo_rotacao(self):
        # R-c: colisoes dentro do mesmo minuto e PID geram _2, _3, ...
        dt = datetime.datetime(2026, 10, 16, 8, 54, 0)
        d = pastas_log.diretorio_log_app(self.tmp, dt)
        os.makedirs(d)

        # Sem arquivo existente -> nome padrao
        c1 = pastas_log.proximo_caminho_log_app(self.tmp, "sss_web", 4321, dt)
        self.assertEqual(c1, os.path.join(d, "sss_web_4321.log"))

        # Cria o primeiro arquivo
        with open(c1, "w") as f:
            f.write("log 1\n")

        # Proximo deve ser _2
        c2 = pastas_log.proximo_caminho_log_app(self.tmp, "sss_web", 4321, dt)
        self.assertEqual(c2, os.path.join(d, "sss_web_4321_2.log"))

        # Cria o segundo arquivo
        with open(c2, "w") as f:
            f.write("log 2\n")

        # Proximo deve ser _3
        c3 = pastas_log.proximo_caminho_log_app(self.tmp, "sss_web", 4321, dt)
        self.assertEqual(c3, os.path.join(d, "sss_web_4321_3.log"))

    # -----------------------------------------------------------------------
    # 4. Parsing e validacao de formato de data de pastas (README §11.3, §13)
    # -----------------------------------------------------------------------

    def test_parse_data_dia(self):
        self.assertEqual(pastas_log.parse_data_dia("2026", "10", "16"), datetime.date(2026, 10, 16))
        self.assertEqual(pastas_log.parse_data_dia("2026", "02", "28"), datetime.date(2026, 2, 28))
        # Formatos invalidos ou datas inexistentes
        self.assertIsNone(pastas_log.parse_data_dia("26", "10", "16"))
        self.assertIsNone(pastas_log.parse_data_dia("2026", "13", "01"))
        self.assertIsNone(pastas_log.parse_data_dia("2026", "02", "30"))
        self.assertIsNone(pastas_log.parse_data_dia("ano", "10", "16"))

    def test_parse_data_minuto(self):
        dt = pastas_log.parse_data_minuto("2026", "10", "16", "14", "05")
        self.assertEqual(dt, datetime.datetime(2026, 10, 16, 14, 5))
        # Invalidos
        self.assertIsNone(pastas_log.parse_data_minuto("2026", "10", "16", "25", "00"))
        self.assertIsNone(pastas_log.parse_data_minuto("2026", "10", "16", "14", "60"))
        self.assertIsNone(pastas_log.parse_data_minuto("2026", "10", "16", "14", "cinco"))


if __name__ == "__main__":
    unittest.main()
