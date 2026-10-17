# -*- coding: utf-8 -*-
"""Testes de recurrence.py (F5.1): README §7.1-§7.5, AGENTS §7.4."""
import _testenv  # noqa: F401

import datetime
import timeit
import unittest

import recurrence as rec
from cron_parser import CronErro

D = datetime.datetime
# Quinta-feira, com segundos e microssegundos de proposito.
AGORA = D(2026, 10, 15, 10, 7, 30, 123456)
INICIO = D(2026, 1, 1)


def regra(tipo, **extra):
    base = {'tipo_recorrencia': tipo, 'data_inicio': INICIO, 'data_fim': None, 'hora_execucao': None,
            'dias_semana': None, 'dia_mes': None, 'expressao_cron': None, 'proxima_execucao': None}
    base.update(extra)
    return base


def diaria(**extra):
    return regra('DIARIA', hora_execucao='03:00', **extra)


def sem_micro(dt):
    return dt is None or dt.microsecond == 0


class TestUtilitarios(unittest.TestCase):

    def test_truncar_e_sem_microssegundos(self):
        self.assertEqual(rec.truncar_segundos(AGORA), D(2026, 10, 15, 10, 7))
        self.assertEqual(rec.sem_microssegundos(AGORA), D(2026, 10, 15, 10, 7, 30))
        self.assertIsNone(rec.truncar_segundos(None))
        self.assertIsNone(rec.sem_microssegundos(None))


class TestValidarRegra(unittest.TestCase):

    def test_regras_validas(self):
        for r in (regra('UNICA'), diaria(), regra('SEMANAL', hora_execucao='23:59', dias_semana='1,3,5'),
                  regra('MENSAL', hora_execucao='00:00', dia_mes=31), regra('MENSAL', hora_execucao='00:00', dia_mes='15'),
                  regra('CRON', expressao_cron='*/15 * * * *'), diaria(data_fim=INICIO)):
            with self.subTest(tipo=r['tipo_recorrencia']):
                self.assertEqual(dict(rec.validar_regra(r)), {})

    def test_ck_campos(self):
        self.assertIn('tipo_recorrencia', rec.validar_regra(regra('ANUAL')))
        self.assertIn('hora_execucao', rec.validar_regra(regra('DIARIA')))
        erros = rec.validar_regra(regra('SEMANAL'))
        self.assertEqual(set(erros), {'hora_execucao', 'dias_semana'})
        self.assertEqual(set(rec.validar_regra(regra('MENSAL', hora_execucao='01:00'))), {'dia_mes'})
        self.assertEqual(set(rec.validar_regra(regra('CRON', expressao_cron='  '))), {'expressao_cron'})
        self.assertIn('data_inicio', rec.validar_regra(regra('UNICA', data_inicio=None)))

    def test_ck_hora(self):
        for hora in ('24:00', '7:00', '12:60', '12h00', '12:00 ', 'ab:cd'):
            with self.subTest(hora=hora):
                self.assertIn('hora_execucao', rec.validar_regra(regra('DIARIA', hora_execucao=hora)))

    def test_ck_dias_semana(self):
        for dsem in ('0', '8', '1,,2', '1-5', '1,2,3,4,5,6,7,1', ' 1'):
            with self.subTest(dsem=dsem):
                self.assertIn('dias_semana', rec.validar_regra(regra('SEMANAL', hora_execucao='01:00', dias_semana=dsem)))

    def test_ck_dia_mes(self):
        for dia in (0, 32, -1, 'x', '1.5'):
            with self.subTest(dia=dia):
                self.assertIn('dia_mes', rec.validar_regra(regra('MENSAL', hora_execucao='01:00', dia_mes=dia)))

    def test_ck_fim(self):
        erros = rec.validar_regra(diaria(data_fim=INICIO - datetime.timedelta(minutes=1)))
        self.assertEqual(list(erros), ['data_fim'])

    def test_cron_invalido_ou_sem_ocorrencia(self):
        self.assertIn("'L'", rec.validar_regra(regra('CRON', expressao_cron='0 0 L * *'))['expressao_cron'])
        self.assertIn('não ocorre', rec.validar_regra(regra('CRON', expressao_cron='0 0 30 2 *'))['expressao_cron'])


class TestProximaExecucao(unittest.TestCase):

    def test_diaria(self):
        self.assertEqual(rec.proxima_execucao(diaria(), AGORA), D(2026, 10, 16, 3, 0))
        self.assertEqual(rec.proxima_execucao(regra('DIARIA', hora_execucao='23:30'), AGORA), D(2026, 10, 15, 23, 30))
        # Estritamente maior que apos.
        self.assertEqual(rec.proxima_execucao(diaria(), D(2026, 10, 16, 3, 0)), D(2026, 10, 17, 3, 0))

    def test_piso_data_inicio_inclusivo(self):
        # Decisao 1: primeira ocorrencia >= data_inicio.
        self.assertEqual(rec.proxima_execucao(diaria(data_inicio=D(2026, 11, 1, 10, 0)), AGORA), D(2026, 11, 2, 3, 0))
        self.assertEqual(rec.proxima_execucao(diaria(data_inicio=D(2026, 11, 1, 3, 0)), AGORA), D(2026, 11, 1, 3, 0))
        # data_inicio com segundos tem precisao de minuto.
        self.assertEqual(rec.proxima_execucao(diaria(data_inicio=D(2026, 11, 1, 3, 0, 45)), AGORA), D(2026, 11, 1, 3, 0))

    def test_semanal_1_3_5(self):
        r = regra('SEMANAL', hora_execucao='08:00', dias_semana='1,3,5')
        datas = rec.proximas(r, AGORA, 6)
        self.assertEqual(datas, [D(2026, 10, 16, 8), D(2026, 10, 19, 8), D(2026, 10, 21, 8),
                                 D(2026, 10, 23, 8), D(2026, 10, 26, 8), D(2026, 10, 28, 8)])
        self.assertEqual([d.isoweekday() for d in datas], [5, 1, 3, 5, 1, 3])
        self.assertEqual(rec.proximas(regra('SEMANAL', hora_execucao='08:00', dias_semana='7'), AGORA, 1),
                         [D(2026, 10, 18, 8)])

    def test_mensal_dia_31_em_meses_curtos(self):
        r = regra('MENSAL', hora_execucao='06:00', dia_mes=31)
        self.assertEqual(rec.proxima_execucao(r, D(2027, 3, 31, 6)), D(2027, 4, 30, 6))
        self.assertEqual(rec.proxima_execucao(r, D(2027, 1, 31, 6)), D(2027, 2, 28, 6))
        self.assertEqual(rec.proxima_execucao(r, D(2028, 1, 31, 6)), D(2028, 2, 29, 6))
        self.assertEqual(rec.proxima_execucao(r, D(2027, 11, 30, 6)), D(2027, 12, 31, 6))
        # Sem deriva: depois de 28/02 volta ao dia 31.
        self.assertEqual(rec.proximas(r, D(2027, 2, 1), 3), [D(2027, 2, 28, 6), D(2027, 3, 31, 6), D(2027, 4, 30, 6)])
        self.assertEqual(rec.proxima_execucao(regra('MENSAL', hora_execucao='06:00', dia_mes=30), D(2027, 2, 1)),
                         D(2027, 2, 28, 6))

    def test_cron(self):
        r = regra('CRON', expressao_cron='*/15 * * * *')
        self.assertEqual(rec.proximas(r, AGORA, 2), [D(2026, 10, 15, 10, 15), D(2026, 10, 15, 10, 30)])
        self.assertEqual(rec.proxima_execucao(regra('CRON', expressao_cron='0 0 29 2 *'), AGORA), D(2028, 2, 29))
        with self.assertRaises(CronErro):
            rec.proxima_execucao(regra('CRON', expressao_cron='0 0 30 2 *'), AGORA)
        with self.assertRaises(CronErro):
            rec.proxima_execucao(regra('CRON', expressao_cron='0 0 * * MON'), AGORA)

    def test_cron_terminado_por_data_fim_nao_e_erro(self):
        r = regra('CRON', expressao_cron='0 0 29 2 *', data_fim=D(2027, 12, 31))
        self.assertIsNone(rec.proxima_execucao(r, AGORA))

    def test_unica(self):
        futura = regra('UNICA', data_inicio=D(2026, 10, 20, 14, 30, 59))
        self.assertEqual(rec.proxima_execucao(futura, AGORA), D(2026, 10, 20, 14, 30))
        self.assertIsNone(rec.proxima_execucao(regra('UNICA', data_inicio=D(2026, 10, 1)), AGORA))
        self.assertIsNone(rec.proxima_execucao(futura, D(2026, 10, 20, 14, 30)))
        self.assertEqual(rec.proximas(futura, AGORA, 5), [D(2026, 10, 20, 14, 30)])

    def test_data_fim_teto_inclusivo(self):
        self.assertEqual(rec.proxima_execucao(diaria(data_fim=D(2026, 10, 16, 3, 0)), AGORA), D(2026, 10, 16, 3, 0))
        self.assertIsNone(rec.proxima_execucao(diaria(data_fim=D(2026, 10, 16, 2, 59)), AGORA))
        self.assertEqual(rec.proximas(diaria(data_fim=D(2026, 10, 18, 12)), AGORA, 10),
                         [D(2026, 10, 16, 3), D(2026, 10, 17, 3), D(2026, 10, 18, 3)])

    def test_nenhuma_saida_com_microssegundos(self):
        regras = (regra('UNICA', data_inicio=D(2026, 12, 1, 1, 2, 3, 999999)),
                  diaria(data_inicio=D(2026, 1, 1, 0, 0, 0, 5)),
                  regra('SEMANAL', hora_execucao='08:00', dias_semana='2'),
                  regra('MENSAL', hora_execucao='08:00', dia_mes=31),
                  regra('CRON', expressao_cron='*/7 * * * *'))
        for r in regras:
            with self.subTest(tipo=r['tipo_recorrencia']):
                for data in rec.proximas(r, AGORA, 5):
                    self.assertEqual((data.second, data.microsecond), (0, 0))
                r = dict(r, proxima_execucao=D(2026, 10, 15, 9, 0))
                decisao = rec.avaliar_disparo(r, AGORA, 'RUN_ONCE', 300)
                self.assertTrue(sem_micro(decisao.nova_data))

    def test_desempenho(self):
        r = regra('CRON', expressao_cron='0 0 29 2 1')
        segundos = min(timeit.repeat(lambda: rec.proxima_execucao(r, AGORA), number=5, repeat=3)) / 5
        self.assertLess(segundos, 0.050)


class TestValidarCronComFim(unittest.TestCase):

    def test_cron_sem_ocorrencia_com_data_fim_no_horizonte(self):
        # CR-007, R-32: a mensagem fica com o servico ("sem proxima execucao"), nao "nao ocorre nos proximos".
        r = regra('CRON', expressao_cron='0 0 1 1 *', data_inicio=D(2026, 10, 1), data_fim=D(2026, 12, 1))
        self.assertNotIn('expressao_cron', rec.validar_regra(r, 90))
        r = dict(r, data_fim=None)
        self.assertIn('expressao_cron', rec.validar_regra(r, 90))


class TestAvaliarDisparo(unittest.TestCase):

    def test_nao_vencida(self):
        r = diaria(proxima_execucao=D(2026, 10, 16, 3))
        self.assertEqual(rec.avaliar_disparo(r, AGORA, 'RUN_ONCE', 300), rec.Decisao(False, D(2026, 10, 16, 3), 0, False))

    def test_no_horario(self):
        r = diaria(proxima_execucao=D(2026, 10, 15, 3))
        decisao = rec.avaliar_disparo(r, D(2026, 10, 15, 3, 0, 4, 250), 'SKIP', 300)
        self.assertEqual(decisao, rec.Decisao(True, D(2026, 10, 16, 3), 0, False, D(2026, 10, 15, 3)))

    def test_run_once_apos_3_dias_de_downtime(self):
        r = diaria(proxima_execucao=D(2026, 10, 12, 3))
        decisao = rec.avaliar_disparo(r, AGORA, 'RUN_ONCE', 300)
        # 12, 13, 14 e 15/10 venceram: 1 ticket coalescido e 3 perdidas.
        self.assertEqual(decisao, rec.Decisao(True, D(2026, 10, 16, 3), 3, False, D(2026, 10, 15, 3)))
        self.assertGreater(decisao.nova_data, AGORA)

    def test_skip(self):
        r = diaria(proxima_execucao=D(2026, 10, 12, 3))
        self.assertEqual(rec.avaliar_disparo(r, AGORA, 'SKIP', 300), rec.Decisao(False, D(2026, 10, 16, 3), 4, False))

    def test_skip_dentro_da_tolerancia_gera(self):
        r = diaria(proxima_execucao=D(2026, 10, 15, 3))
        limite = D(2026, 10, 15, 3, 5)
        self.assertTrue(rec.avaliar_disparo(r, limite, 'SKIP', 300).gerar_ticket)
        self.assertFalse(rec.avaliar_disparo(r, limite + datetime.timedelta(seconds=1), 'SKIP', 300).gerar_ticket)

    def test_atraso_tolerado_com_varias_vencidas(self):
        # Decisao 5: CRON a cada minuto com 4 min de atraso gera 1 ticket; nova_data e a primeira > agora.
        r = regra('CRON', expressao_cron='* * * * *', proxima_execucao=D(2026, 10, 15, 10, 3))
        self.assertEqual(rec.avaliar_disparo(r, AGORA, 'SKIP', 300), rec.Decisao(True, D(2026, 10, 15, 10, 8), 4, False, D(2026, 10, 15, 10, 7)))

    def test_unica_no_passado(self):
        r = regra('UNICA', data_inicio=D(2026, 10, 1, 9), proxima_execucao=D(2026, 10, 1, 9))
        self.assertEqual(rec.avaliar_disparo(r, AGORA, 'RUN_ONCE', 300), rec.Decisao(True, None, 0, True, D(2026, 10, 1, 9)))
        self.assertEqual(rec.avaliar_disparo(r, AGORA, 'SKIP', 300), rec.Decisao(False, None, 1, True))
        r = dict(r, proxima_execucao=D(2026, 10, 15, 10, 5))
        self.assertEqual(rec.avaliar_disparo(r, AGORA, 'SKIP', 300), rec.Decisao(True, None, 0, True, D(2026, 10, 15, 10, 5)))

    def test_data_fim_atingido(self):
        r = diaria(proxima_execucao=D(2026, 10, 15, 3), data_fim=D(2026, 10, 15, 23, 59))
        self.assertEqual(rec.avaliar_disparo(r, D(2026, 10, 15, 3), 'RUN_ONCE', 300),
                         rec.Decisao(True, None, 0, True, D(2026, 10, 15, 3)))
        r = dict(r, data_fim=D(2026, 10, 16, 3))
        self.assertEqual(rec.avaliar_disparo(r, D(2026, 10, 15, 3), 'RUN_ONCE', 300),
                         rec.Decisao(True, D(2026, 10, 16, 3), 0, False, D(2026, 10, 15, 3)))

    def test_conclusao_sem_ticket_fora_da_unica(self):
        # CR-007, R-32: DIARIA com data_fim vencida durante a parada e SKIP conclui sem ticket.
        r = diaria(proxima_execucao=D(2026, 10, 12, 3), data_fim=D(2026, 10, 14, 4))
        self.assertEqual(rec.avaliar_disparo(r, AGORA, 'SKIP', 300), rec.Decisao(False, None, 3, True, None))

    def test_ocorrencia_nunca_no_futuro(self):
        r = regra('CRON', expressao_cron='*/5 * * * *', proxima_execucao=D(2026, 10, 15, 9, 50))
        decisao = rec.avaliar_disparo(r, AGORA, 'RUN_ONCE', 3600)
        self.assertEqual(decisao.ocorrencia, D(2026, 10, 15, 10, 5))
        self.assertLessEqual(decisao.ocorrencia, AGORA)

    def test_perdidas_limitadas(self):
        r = regra('CRON', expressao_cron='* * * * *', proxima_execucao=D(2026, 9, 1))
        decisao = rec.avaliar_disparo(r, AGORA, 'SKIP', 300)
        self.assertEqual((decisao.gerar_ticket, decisao.perdidas), (False, rec.LIMITE_PERDIDAS))
        self.assertEqual(decisao.nova_data, D(2026, 10, 15, 10, 8))

    def test_ocorrencia_mais_recente_apos_limite_de_contagem(self):
        for fim, esperado in ((None, D(2026, 10, 15, 10, 5)),
                              (D(2026, 10, 1, 10, 3), D(2026, 10, 1, 10, 0))):
            r = regra('CRON', expressao_cron='*/5 * * * *',
                      proxima_execucao=INICIO, data_fim=fim)
            decisao = rec.avaliar_disparo(r, AGORA, 'RUN_ONCE', 300)
            self.assertEqual(decisao.perdidas, rec.LIMITE_PERDIDAS)
            self.assertEqual(decisao.ocorrencia, esperado)

    def test_cron_invalido_propaga(self):
        r = regra('CRON', expressao_cron='0 0 30 2 *', proxima_execucao=D(2026, 10, 1))
        with self.assertRaises(CronErro):
            rec.avaliar_disparo(r, AGORA, 'RUN_ONCE', 300)

    def test_politica_invalida(self):
        with self.assertRaises(ValueError):
            rec.avaliar_disparo(diaria(proxima_execucao=INICIO), AGORA, 'RUN_ALL', 300)


if __name__ == '__main__':
    unittest.main()
