# -*- coding: utf-8 -*-
"""Testes de cron_parser.py (F5.1): README §7.3, AGENTS §7.4."""
from tests.support import _testenv  # noqa: F401

import ast
import datetime
import os
import random
import timeit
import unittest

import cron_parser
from cron_parser import CronError

D = datetime.datetime
# Quinta-feira, com segundos e microssegundos de proposito.
NOW = D(2026, 10, 15, 10, 7, 30, 123456)


def next_run(expr, after=NOW, horizon=cron_parser.DEFAULT_HORIZON):
    return cron_parser.parse(expr).next(after, horizon)


def sequence(expr, after, n):
    cron = cron_parser.parse(expr)
    items = []
    for _ in range(n):
        after = cron.next(after)
        items.append(after)
    return items


def _raw_match(fields, t):
    """Referencia ingenua (minuto a minuto) para conferir o calculo campo a campo."""
    minutes, hours, days, months, wday, day_r, wday_r = fields
    if t.minute not in minutes or t.hour not in hours or t.month not in months:
        return False
    match_day = t.day in days
    match_wday = (t.weekday() + 1) % 7 in wday
    return (match_day or match_wday) if (day_r and wday_r) else (match_day and match_wday)


class TestSyntax(unittest.TestCase):

    def test_campos_basicos(self):
        cron = cron_parser.parse('  0,30   8-18/2 1-5,15 */3 1-5 ')
        self.assertEqual(cron.minutes, {0, 30})
        self.assertEqual(cron.hours, {8, 10, 12, 14, 16, 18})
        self.assertEqual(cron.days, {1, 2, 3, 4, 5, 15})
        self.assertEqual(cron.months, {1, 4, 7, 10})
        self.assertEqual(cron.weekdays, {1, 2, 3, 4, 5})
        self.assertEqual(cron.text, '0,30 8-18/2 1-5,15 */3 1-5')

    def test_dia_semana_7_e_domingo(self):
        self.assertEqual(cron_parser.parse('0 0 * * 7').weekdays, {0})
        self.assertEqual(cron_parser.parse('0 0 * * 5-7').weekdays, {5, 6, 0})

    def test_rejeicoes(self):
        cases = {
            'MON * * * *': 'Nomes', '0 0 * JAN *': 'Nomes', '0 0 * * mon': 'Nomes',
            '0 0 L * *': "'L'", '0 0 15W * *': "'W'", '0 0 * * 1#2': "'#'", '0 0 ? * *': "'?'",
            '* * * *': '5 campos', '* * * * * *': '5 campos', '': 'Informe', '   ': 'Informe',
            '60 * * * *': 'fora da faixa', '0 24 * * *': 'fora da faixa', '0 0 0 * *': 'fora da faixa',
            '0 0 32 * *': 'fora da faixa', '0 0 * 13 *': 'fora da faixa', '0 0 * 0 *': 'fora da faixa',
            '0 0 * * 8': 'fora da faixa', '*/0 * * * *': 'passo não pode ser 0',
            '0-30/0 * * * *': 'passo não pode ser 0', '30-10 * * * *': 'invertido',
            '1/5 * * * *': 'use passo', '1,,2 * * * *': 'item vazio', '*/5/2 * * * *': 'inválido',
            '-1 * * * *': 'inválido', '1- * * * *': 'inválido', '0 0 * * 1;2': 'inválido',
        }
        for expr, snippet in cases.items():
            with self.subTest(expr=expr):
                with self.assertRaises(CronError) as ctx:
                    cron_parser.parse(expr)
                self.assertIn(snippet, ctx.exception.message)
        with self.assertRaises(CronError):
            cron_parser.parse('0,' * 30 + '0 * * * *')
        with self.assertRaises(CronError):
            cron_parser.parse(None)

    def test_texto_com_espacos_dentro_do_limite(self):
        self.assertEqual(cron_parser.parse('0 0 1 1 1' + ' ' * 60).text, '0 0 1 1 1')


class TestNext(unittest.TestCase):

    def test_estritamente_maior_e_sem_segundos(self):
        self.assertEqual(next_run('* * * * *'), D(2026, 10, 15, 10, 8))
        self.assertEqual(next_run('* * * * *', D(2026, 10, 15, 10, 8)), D(2026, 10, 15, 10, 9))
        self.assertEqual(next_run('8 10 * * *'), D(2026, 10, 15, 10, 8))
        self.assertEqual(next_run('7 10 * * *'), D(2026, 10, 16, 10, 7))
        for expr in ('*/15 * * * *', '0 0 29 2 *', '30 2 * * 1-5'):
            r = next_run(expr)
            self.assertEqual((r.second, r.microsecond), (0, 0))

    def test_passo_15(self):
        self.assertEqual(sequence('*/15 * * * *', NOW, 4),
                         [D(2026, 10, 15, 10, 15), D(2026, 10, 15, 10, 30), D(2026, 10, 15, 10, 45),
                          D(2026, 10, 15, 11, 0)])

    def test_lista_intervalo_passo(self):
        self.assertEqual(sequence('0 8-12/2 * * *', NOW, 3),
                         [D(2026, 10, 15, 12, 0), D(2026, 10, 16, 8, 0), D(2026, 10, 16, 10, 0)])
        self.assertEqual(sequence('5,50 23 * * *', NOW, 3),
                         [D(2026, 10, 15, 23, 5), D(2026, 10, 15, 23, 50), D(2026, 10, 16, 23, 5)])

    def test_carry_de_ano(self):
        self.assertEqual(next_run('59 23 31 12 *', D(2026, 12, 31, 23, 59)), D(2027, 12, 31, 23, 59))
        self.assertEqual(next_run('0 0 1 1 *', D(2026, 12, 31, 23, 59, 59)), D(2027, 1, 1, 0, 0))

    def test_29_de_fevereiro_so_em_ano_bissexto(self):
        self.assertEqual(sequence('0 0 29 2 *', NOW, 3), [D(2028, 2, 29), D(2032, 2, 29), D(2036, 2, 29)])

    def test_dia_31_pula_meses_curtos(self):
        self.assertEqual(sequence('0 0 31 * *', NOW, 4),
                         [D(2026, 10, 31), D(2026, 12, 31), D(2027, 1, 31), D(2027, 3, 31)])

    def test_domingo_0_e_7_equivalentes(self):
        self.assertEqual(next_run('0 12 * * 0'), D(2026, 10, 18, 12, 0))
        self.assertEqual(sequence('0 12 * * 0', NOW, 5), sequence('0 12 * * 7', NOW, 5))

    def test_semantica_ou_vixie(self):
        # Dia 1 OU segunda-feira.
        self.assertEqual(sequence('0 0 1 * 1', NOW, 4),
                         [D(2026, 10, 19), D(2026, 10, 26), D(2026, 11, 1), D(2026, 11, 2)])
        # Campo iniciado por '*' nao e restrito: vale o E (dias impares que sejam segunda).
        for date in sequence('0 0 */2 * 1', NOW, 6):
            self.assertEqual((date.day % 2, date.weekday()), (1, 0))
        # So dia da semana restrito.
        for date in sequence('0 0 * * 1', NOW, 4):
            self.assertEqual(date.weekday(), 0)

    def test_sem_ocorrencia_no_horizonte(self):
        self.assertIsNone(next_run('0 0 30 2 *'))
        self.assertIsNone(next_run('0 0 31 4,6,9,11 *'))
        self.assertIsNone(next_run('0 0 29 2 *', D(2026, 10, 15), horizon=365))
        self.assertEqual(next_run('0 0 29 2 *', D(2026, 10, 15), horizon=503), D(2028, 2, 29))
        self.assertIsNone(next_run('0 0 29 2 *', D(2026, 10, 15), horizon=501))

    def test_confere_com_forca_bruta(self):
        draw = random.Random(20261015)
        start = D(2027, 2, 26, 22, 13, 40)
        window = 8 * 24 * 60
        for _ in range(40):
            expr = ' '.join((
                draw.choice(['*', '*/7', '0,30', '15-20', '%d' % draw.randint(0, 59)]),
                draw.choice(['*', '*/5', '0-3,22-23', '%d' % draw.randint(0, 23)]),
                draw.choice(['*', '*/3', '1,28,29', '%d-31' % draw.randint(25, 31)]),
                draw.choice(['*', '2,3', '2', '3-12/3']),
                draw.choice(['*', '0', '1-5', '6,7', '*/2']),
            ))
            cron = cron_parser.parse(expr)
            fields = (cron.minutes, cron.hours, cron.days, cron.months, cron.weekdays,
                      cron.day_restricted, cron.wday_restricted)
            t = start.replace(second=0) + datetime.timedelta(minutes=1)
            expected = None
            for _ in range(window):
                if _raw_match(fields, t):
                    expected = t
                    break
                t += datetime.timedelta(minutes=1)
            got = cron.next(start)
            with self.subTest(expr=expr):
                if expected is not None:
                    self.assertEqual(got, expected)
                else:
                    self.assertTrue(got is None or got >= t)

    def test_desempenho(self):
        exprs = ('0 0 30 2 *', '0 0 29 2 1', '59 23 31 12 *', '*/15 * * * *', '0 0 31 4,6,9,11 *',
                 '0-59/7 0-23/5 1-31/3 1-12/5 0-6/3')
        for expr in exprs:
            cron = cron_parser.parse(expr)
            seconds = min(timeit.repeat(lambda: cron.next(NOW), number=5, repeat=3)) / 5
            with self.subTest(expr=expr):
                self.assertLess(seconds, 0.050, '%s levou %.1f ms' % (expr, seconds * 1000))


class TestDescribe(unittest.TestCase):

    def test_expressoes_comuns(self):
        cases = (
            ('30 2 * * 1-5', 'às 02:30, de segunda a sexta'),
            ('*/15 * * * *', 'a cada 15 minutos'),
            ('0 3 * * *', 'às 03:00, todos os dias'),
            ('0 0 1 * *', 'às 00:00, no dia 1 de cada mês'),
            ('0 12 * * 0', 'às 12:00, aos domingos'),
            ('0 12 * * 7', 'às 12:00, aos domingos'),
            ('* * * * *', 'a cada minuto'),
            ('5 * * * *', 'a cada hora, no minuto 05'),
            ('0 */6 * * *', 'a cada 6 horas, no minuto 00'),
            ('0 8,18 * * 1,3,5', 'às 08:00 e 18:00, em segunda, quarta e sexta'),
            ('0 0 29 2 *', 'às 00:00, no dia 29 de fevereiro'),
            ('0 0 1 * 1', 'às 00:00, no dia 1 de cada mês ou às segundas'),
            # CR-003 P7 (README §7.3): passo no dia do mes.
            ('0 0 */2 * *', 'às 00:00, a cada 2 dias a partir do dia 1'),
            ('0 0 */2 * 1', 'às 00:00, a cada 2 dias a partir do dia 1, quando cair numa segunda'),
            ('0 0 */3 * 0', 'às 00:00, a cada 3 dias a partir do dia 1, quando cair num domingo'),
            ('*/10 9-17 * * 1-5', 'a cada 10 minutos, das 09:00 às 17:59, de segunda a sexta'),
        )
        for expr, text in cases:
            with self.subTest(expr=expr):
                self.assertEqual(cron_parser.parse(expr).describe(), text)

    def test_qualquer_expressao_valida_tem_descricao(self):
        for expr in ('0-59/7 0-23/5 1-31/3 1-12/5 0-6/3', '1,2 3,4 5-9 6-8 *', '0 0 */2 * 1'):
            with self.subTest(expr=expr):
                self.assertTrue(cron_parser.parse(expr).describe())


class TestPurity(unittest.TestCase):

    def test_sem_now_nem_gluon(self):
        modules = os.path.join(_testenv.APP_DIR, 'modules')
        for name in ('cron_parser.py', 'recurrence.py'):
            with open(os.path.join(modules, name), encoding='utf-8') as f:
                tree = ast.parse(f.read())
            calls = set(n.func.attr for n in ast.walk(tree)
                           if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute))
            imported = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    imported.update(a.name.split('.')[0] for a in n.names)
                elif isinstance(n, ast.ImportFrom):
                    imported.add((n.module or '').split('.')[0])
            with self.subTest(modulo=name):
                self.assertFalse(calls & {'now', 'utcnow', 'today', 'time'}, calls)
                self.assertNotIn('gluon', imported)

if __name__ == '__main__':
    unittest.main()
