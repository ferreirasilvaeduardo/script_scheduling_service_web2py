# -*- coding: utf-8 -*-
"""Testes de recurrence.py (F5.1): README §7.1-§7.5, AGENTS §7.4."""
import _testenv  # noqa: F401

import datetime
import timeit
import unittest

import recurrence as rec
from cron_parser import CronError

D = datetime.datetime
# Quinta-feira, com segundos e microssegundos de proposito.
NOW = D(2026, 10, 15, 10, 7, 30, 123456)
START = D(2026, 1, 1)


def rule(tipo, **extra):
    base = {'recurrence_type': tipo, 'start_date': START, 'end_date': None, 'run_time': None,
            'week_days': None, 'month_day': None, 'cron_expression': None, 'next_run_at': None}
    base.update(extra)
    return base


def daily(**extra):
    return rule('DAILY', run_time='03:00', **extra)


def without_micro(dt):
    return dt is None or dt.microsecond == 0


class TestUtilities(unittest.TestCase):

    def test_truncar_e_sem_microssegundos(self):
        self.assertEqual(rec.truncate_seconds(NOW), D(2026, 10, 15, 10, 7))
        self.assertEqual(rec.without_microseconds(NOW), D(2026, 10, 15, 10, 7, 30))
        self.assertIsNone(rec.truncate_seconds(None))
        self.assertIsNone(rec.without_microseconds(None))


class TestValidateRule(unittest.TestCase):

    def test_regras_validas(self):
        for r in (rule('ONCE'), daily(), rule('WEEKLY', run_time='23:59', week_days='1,3,5'),
                  rule('MONTHLY', run_time='00:00', month_day=31), rule('MONTHLY', run_time='00:00', month_day='15'),
                  rule('CRON', cron_expression='*/15 * * * *'), daily(end_date=START)):
            with self.subTest(tipo=r['recurrence_type']):
                self.assertEqual(dict(rec.validate_rule(r)), {})

    def test_ck_campos(self):
        self.assertIn('recurrence_type', rec.validate_rule(rule('ANUAL')))
        self.assertIn('run_time', rec.validate_rule(rule('DAILY')))
        erros = rec.validate_rule(rule('WEEKLY'))
        self.assertEqual(set(erros), {'run_time', 'week_days'})
        self.assertEqual(set(rec.validate_rule(rule('MONTHLY', run_time='01:00'))), {'month_day'})
        self.assertEqual(set(rec.validate_rule(rule('CRON', cron_expression='  '))), {'cron_expression'})
        self.assertIn('start_date', rec.validate_rule(rule('ONCE', start_date=None)))

    def test_ck_hora(self):
        for hora in ('24:00', '7:00', '12:60', '12h00', '12:00 ', 'ab:cd'):
            with self.subTest(hora=hora):
                self.assertIn('run_time', rec.validate_rule(rule('DAILY', run_time=hora)))

    def test_ck_dias_semana(self):
        for dsem in ('0', '8', '1,,2', '1-5', '1,2,3,4,5,6,7,1', ' 1'):
            with self.subTest(dsem=dsem):
                self.assertIn('week_days', rec.validate_rule(rule('WEEKLY', run_time='01:00', week_days=dsem)))

    def test_ck_dia_mes(self):
        for dia in (0, 32, -1, 'x', '1.5'):
            with self.subTest(dia=dia):
                self.assertIn('month_day', rec.validate_rule(rule('MONTHLY', run_time='01:00', month_day=dia)))

    def test_ck_fim(self):
        erros = rec.validate_rule(daily(end_date=START - datetime.timedelta(minutes=1)))
        self.assertEqual(list(erros), ['end_date'])

    def test_cron_invalido_ou_sem_ocorrencia(self):
        self.assertIn("'L'", rec.validate_rule(rule('CRON', cron_expression='0 0 L * *'))['cron_expression'])
        self.assertIn('não ocorre', rec.validate_rule(rule('CRON', cron_expression='0 0 30 2 *'))['cron_expression'])


class TestNextRun(unittest.TestCase):

    def test_diaria(self):
        self.assertEqual(rec.next_run(daily(), NOW), D(2026, 10, 16, 3, 0))
        self.assertEqual(rec.next_run(rule('DAILY', run_time='23:30'), NOW), D(2026, 10, 15, 23, 30))
        # Estritamente maior que apos.
        self.assertEqual(rec.next_run(daily(), D(2026, 10, 16, 3, 0)), D(2026, 10, 17, 3, 0))

    def test_piso_data_inicio_inclusivo(self):
        # Decisao 1: primeira ocorrencia >= data_inicio.
        self.assertEqual(rec.next_run(daily(start_date=D(2026, 11, 1, 10, 0)), NOW), D(2026, 11, 2, 3, 0))
        self.assertEqual(rec.next_run(daily(start_date=D(2026, 11, 1, 3, 0)), NOW), D(2026, 11, 1, 3, 0))
        # data_inicio com segundos tem precisao de minuto.
        self.assertEqual(rec.next_run(daily(start_date=D(2026, 11, 1, 3, 0, 45)), NOW), D(2026, 11, 1, 3, 0))

    def test_semanal_1_3_5(self):
        r = rule('WEEKLY', run_time='08:00', week_days='1,3,5')
        datas = rec.next_runs(r, NOW, 6)
        self.assertEqual(datas, [D(2026, 10, 16, 8), D(2026, 10, 19, 8), D(2026, 10, 21, 8),
                                 D(2026, 10, 23, 8), D(2026, 10, 26, 8), D(2026, 10, 28, 8)])
        self.assertEqual([d.isoweekday() for d in datas], [5, 1, 3, 5, 1, 3])
        self.assertEqual(rec.next_runs(rule('WEEKLY', run_time='08:00', week_days='7'), NOW, 1),
                         [D(2026, 10, 18, 8)])

    def test_mensal_dia_31_em_meses_curtos(self):
        r = rule('MONTHLY', run_time='06:00', month_day=31)
        self.assertEqual(rec.next_run(r, D(2027, 3, 31, 6)), D(2027, 4, 30, 6))
        self.assertEqual(rec.next_run(r, D(2027, 1, 31, 6)), D(2027, 2, 28, 6))
        self.assertEqual(rec.next_run(r, D(2028, 1, 31, 6)), D(2028, 2, 29, 6))
        self.assertEqual(rec.next_run(r, D(2027, 11, 30, 6)), D(2027, 12, 31, 6))
        # Sem deriva: depois de 28/02 volta ao dia 31.
        self.assertEqual(rec.next_runs(r, D(2027, 2, 1), 3), [D(2027, 2, 28, 6), D(2027, 3, 31, 6), D(2027, 4, 30, 6)])
        self.assertEqual(rec.next_run(rule('MONTHLY', run_time='06:00', month_day=30), D(2027, 2, 1)),
                         D(2027, 2, 28, 6))

    def test_cron(self):
        r = rule('CRON', cron_expression='*/15 * * * *')
        self.assertEqual(rec.next_runs(r, NOW, 2), [D(2026, 10, 15, 10, 15), D(2026, 10, 15, 10, 30)])
        self.assertEqual(rec.next_run(rule('CRON', cron_expression='0 0 29 2 *'), NOW), D(2028, 2, 29))
        with self.assertRaises(CronError):
            rec.next_run(rule('CRON', cron_expression='0 0 30 2 *'), NOW)
        with self.assertRaises(CronError):
            rec.next_run(rule('CRON', cron_expression='0 0 * * MON'), NOW)

    def test_cron_terminado_por_data_fim_nao_e_erro(self):
        r = rule('CRON', cron_expression='0 0 29 2 *', end_date=D(2027, 12, 31))
        self.assertIsNone(rec.next_run(r, NOW))

    def test_unica(self):
        futura = rule('ONCE', start_date=D(2026, 10, 20, 14, 30, 59))
        self.assertEqual(rec.next_run(futura, NOW), D(2026, 10, 20, 14, 30))
        self.assertIsNone(rec.next_run(rule('ONCE', start_date=D(2026, 10, 1)), NOW))
        self.assertIsNone(rec.next_run(futura, D(2026, 10, 20, 14, 30)))
        self.assertEqual(rec.next_runs(futura, NOW, 5), [D(2026, 10, 20, 14, 30)])

    def test_data_fim_teto_inclusivo(self):
        self.assertEqual(rec.next_run(daily(end_date=D(2026, 10, 16, 3, 0)), NOW), D(2026, 10, 16, 3, 0))
        self.assertIsNone(rec.next_run(daily(end_date=D(2026, 10, 16, 2, 59)), NOW))
        self.assertEqual(rec.next_runs(daily(end_date=D(2026, 10, 18, 12)), NOW, 10),
                         [D(2026, 10, 16, 3), D(2026, 10, 17, 3), D(2026, 10, 18, 3)])

    def test_nenhuma_saida_com_microssegundos(self):
        regras = (rule('ONCE', start_date=D(2026, 12, 1, 1, 2, 3, 999999)),
                  daily(start_date=D(2026, 1, 1, 0, 0, 0, 5)),
                  rule('WEEKLY', run_time='08:00', week_days='2'),
                  rule('MONTHLY', run_time='08:00', month_day=31),
                  rule('CRON', cron_expression='*/7 * * * *'))
        for r in regras:
            with self.subTest(tipo=r['recurrence_type']):
                for data in rec.next_runs(r, NOW, 5):
                    self.assertEqual((data.second, data.microsecond), (0, 0))
                r = dict(r, next_run_at=D(2026, 10, 15, 9, 0))
                decisao = rec.evaluate_trigger(r, NOW, 'RUN_ONCE', 300)
                self.assertTrue(without_micro(decisao.next_date))

    def test_desempenho(self):
        r = rule('CRON', cron_expression='0 0 29 2 1')
        segundos = min(timeit.repeat(lambda: rec.next_run(r, NOW), number=5, repeat=3)) / 5
        self.assertLess(segundos, 0.050)


class TestValidateCronWithEnd(unittest.TestCase):

    def test_cron_sem_ocorrencia_com_data_fim_no_horizonte(self):
        # CR-007, R-32: a mensagem fica com o servico ("sem proxima execucao"), nao "nao ocorre nos proximos".
        r = rule('CRON', cron_expression='0 0 1 1 *', start_date=D(2026, 10, 1), end_date=D(2026, 12, 1))
        self.assertNotIn('cron_expression', rec.validate_rule(r, 90))
        r = dict(r, end_date=None)
        self.assertIn('cron_expression', rec.validate_rule(r, 90))


class TestEvaluateTrigger(unittest.TestCase):

    def test_nao_vencida(self):
        r = daily(next_run_at=D(2026, 10, 16, 3))
        self.assertEqual(rec.evaluate_trigger(r, NOW, 'RUN_ONCE', 300), rec.Decision(False, D(2026, 10, 16, 3), 0, False))

    def test_no_horario(self):
        r = daily(next_run_at=D(2026, 10, 15, 3))
        decisao = rec.evaluate_trigger(r, D(2026, 10, 15, 3, 0, 4, 250), 'SKIP', 300)
        self.assertEqual(decisao, rec.Decision(True, D(2026, 10, 16, 3), 0, False, D(2026, 10, 15, 3)))

    def test_run_once_apos_3_dias_de_downtime(self):
        r = daily(next_run_at=D(2026, 10, 12, 3))
        decisao = rec.evaluate_trigger(r, NOW, 'RUN_ONCE', 300)
        # 12, 13, 14 e 15/10 venceram: 1 ticket coalescido e 3 perdidas.
        self.assertEqual(decisao, rec.Decision(True, D(2026, 10, 16, 3), 3, False, D(2026, 10, 15, 3)))
        self.assertGreater(decisao.next_date, NOW)

    def test_skip(self):
        r = daily(next_run_at=D(2026, 10, 12, 3))
        self.assertEqual(rec.evaluate_trigger(r, NOW, 'SKIP', 300), rec.Decision(False, D(2026, 10, 16, 3), 4, False))

    def test_skip_dentro_da_tolerancia_gera(self):
        r = daily(next_run_at=D(2026, 10, 15, 3))
        limite = D(2026, 10, 15, 3, 5)
        self.assertTrue(rec.evaluate_trigger(r, limite, 'SKIP', 300).create_ticket)
        self.assertFalse(rec.evaluate_trigger(r, limite + datetime.timedelta(seconds=1), 'SKIP', 300).create_ticket)

    def test_atraso_tolerado_com_varias_vencidas(self):
        # Decisao 5: CRON a cada minuto com 4 min de atraso gera 1 ticket; nova_data e a primeira > agora.
        r = rule('CRON', cron_expression='* * * * *', next_run_at=D(2026, 10, 15, 10, 3))
        self.assertEqual(rec.evaluate_trigger(r, NOW, 'SKIP', 300), rec.Decision(True, D(2026, 10, 15, 10, 8), 4, False, D(2026, 10, 15, 10, 7)))

    def test_unica_no_passado(self):
        r = rule('ONCE', start_date=D(2026, 10, 1, 9), next_run_at=D(2026, 10, 1, 9))
        self.assertEqual(rec.evaluate_trigger(r, NOW, 'RUN_ONCE', 300), rec.Decision(True, None, 0, True, D(2026, 10, 1, 9)))
        self.assertEqual(rec.evaluate_trigger(r, NOW, 'SKIP', 300), rec.Decision(False, None, 1, True))
        r = dict(r, next_run_at=D(2026, 10, 15, 10, 5))
        self.assertEqual(rec.evaluate_trigger(r, NOW, 'SKIP', 300), rec.Decision(True, None, 0, True, D(2026, 10, 15, 10, 5)))

    def test_data_fim_atingido(self):
        r = daily(next_run_at=D(2026, 10, 15, 3), end_date=D(2026, 10, 15, 23, 59))
        self.assertEqual(rec.evaluate_trigger(r, D(2026, 10, 15, 3), 'RUN_ONCE', 300),
                         rec.Decision(True, None, 0, True, D(2026, 10, 15, 3)))
        r = dict(r, end_date=D(2026, 10, 16, 3))
        self.assertEqual(rec.evaluate_trigger(r, D(2026, 10, 15, 3), 'RUN_ONCE', 300),
                         rec.Decision(True, D(2026, 10, 16, 3), 0, False, D(2026, 10, 15, 3)))

    def test_conclusao_sem_ticket_fora_da_unica(self):
        # CR-007, R-32: DIARIA com data_fim vencida durante a parada e SKIP conclui sem ticket.
        r = daily(next_run_at=D(2026, 10, 12, 3), end_date=D(2026, 10, 14, 4))
        self.assertEqual(rec.evaluate_trigger(r, NOW, 'SKIP', 300), rec.Decision(False, None, 3, True, None))

    def test_ocorrencia_nunca_no_futuro(self):
        r = rule('CRON', cron_expression='*/5 * * * *', next_run_at=D(2026, 10, 15, 9, 50))
        decisao = rec.evaluate_trigger(r, NOW, 'RUN_ONCE', 3600)
        self.assertEqual(decisao.occurrence, D(2026, 10, 15, 10, 5))
        self.assertLessEqual(decisao.occurrence, NOW)

    def test_perdidas_limitadas(self):
        r = rule('CRON', cron_expression='* * * * *', next_run_at=D(2026, 9, 1))
        decisao = rec.evaluate_trigger(r, NOW, 'SKIP', 300)
        # CR-008, R-21: a vencida mais recente (10:07) esta na tolerancia e gera o ticket.
        self.assertEqual((decisao.create_ticket, decisao.missed), (True, rec.MISSED_LIMIT))
        self.assertEqual(decisao.next_date, D(2026, 10, 15, 10, 8))
        decisao = rec.evaluate_trigger(r, D(2026, 10, 15, 10, 7, 50), 'SKIP', 30)
        self.assertEqual((decisao.create_ticket, decisao.missed), (False, rec.MISSED_LIMIT))

    def test_ocorrencia_mais_recente_apos_limite_de_contagem(self):
        for fim, esperado in ((None, D(2026, 10, 15, 10, 5)),
                              (D(2026, 10, 1, 10, 3), D(2026, 10, 1, 10, 0))):
            r = rule('CRON', cron_expression='*/5 * * * *',
                      next_run_at=START, end_date=fim)
            decisao = rec.evaluate_trigger(r, NOW, 'RUN_ONCE', 300)
            self.assertEqual(decisao.missed, rec.MISSED_LIMIT)
            self.assertEqual(decisao.occurrence, esperado)

    def test_cron_sem_ocorrencia_no_horizonte_vira_cron_erro(self):
        # CR-008, R-19: decisao completa com cron_erro; o daemon aplica sobreposicao e SKIP e pausa.
        r = rule('CRON', cron_expression='0 0 30 2 *', next_run_at=D(2026, 10, 1))
        decisao = rec.evaluate_trigger(r, NOW, 'RUN_ONCE', 300)
        self.assertEqual(decisao, rec.Decision(True, None, 0, False, D(2026, 10, 1), True))
        decisao = rec.evaluate_trigger(r, NOW, 'SKIP', 300)
        self.assertEqual(decisao, rec.Decision(False, None, 1, False, None, True))

    def test_cron_sintaxe_invalida_propaga(self):
        r = rule('CRON', cron_expression='0 0 99 2 *', next_run_at=D(2026, 10, 1))
        with self.assertRaises(CronError):
            rec.evaluate_trigger(r, NOW, 'RUN_ONCE', 300)

    def test_skip_mede_pela_vencida_mais_recente(self):
        # CR-008, R-21: */5 com proxima 10:00 e agora 10:06; a das 10:05 (1 min) gera o ticket.
        r = rule('CRON', cron_expression='*/5 * * * *', next_run_at=D(2026, 10, 15, 10, 0))
        decisao = rec.evaluate_trigger(r, D(2026, 10, 15, 10, 6), 'SKIP', 300)
        self.assertEqual(decisao, rec.Decision(True, D(2026, 10, 15, 10, 10), 1, False, D(2026, 10, 15, 10, 5)))

    def test_politica_invalida(self):
        with self.assertRaises(ValueError):
            rec.evaluate_trigger(daily(next_run_at=START), NOW, 'RUN_ALL', 300)


if __name__ == '__main__':
    unittest.main()
