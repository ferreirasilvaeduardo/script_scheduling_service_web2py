# -*- coding: utf-8 -*-
"""Testes de cron_parser.py (F5.1): README §7.3, AGENTS §7.4."""
import _testenv  # noqa: F401

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
AGORA = D(2026, 10, 15, 10, 7, 30, 123456)


def prox(expr, apos=AGORA, horizonte=cron_parser.DEFAULT_HORIZON):
    return cron_parser.parse(expr).next(apos, horizonte)


def sequencia(expr, apos, n):
    cron = cron_parser.parse(expr)
    lista = []
    for _ in range(n):
        apos = cron.next(apos)
        lista.append(apos)
    return lista


def _casa_bruto(campos, t):
    """Referencia ingenua (minuto a minuto) para conferir o calculo campo a campo."""
    minutos, horas, dias, meses, dsem, dia_r, dsem_r = campos
    if t.minute not in minutos or t.hour not in horas or t.month not in meses:
        return False
    casa_dia = t.day in dias
    casa_dsem = (t.weekday() + 1) % 7 in dsem
    return (casa_dia or casa_dsem) if (dia_r and dsem_r) else (casa_dia and casa_dsem)


class TestSintaxe(unittest.TestCase):

    def test_campos_basicos(self):
        cron = cron_parser.parse('  0,30   8-18/2 1-5,15 */3 1-5 ')
        self.assertEqual(cron.minutos, {0, 30})
        self.assertEqual(cron.horas, {8, 10, 12, 14, 16, 18})
        self.assertEqual(cron.dias, {1, 2, 3, 4, 5, 15})
        self.assertEqual(cron.meses, {1, 4, 7, 10})
        self.assertEqual(cron.dias_semana, {1, 2, 3, 4, 5})
        self.assertEqual(cron.texto, '0,30 8-18/2 1-5,15 */3 1-5')

    def test_dia_semana_7_e_domingo(self):
        self.assertEqual(cron_parser.parse('0 0 * * 7').dias_semana, {0})
        self.assertEqual(cron_parser.parse('0 0 * * 5-7').dias_semana, {5, 6, 0})

    def test_rejeicoes(self):
        casos = {
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
        for expr, trecho in casos.items():
            with self.subTest(expr=expr):
                with self.assertRaises(CronError) as ctx:
                    cron_parser.parse(expr)
                self.assertIn(trecho, ctx.exception.mensagem)
        with self.assertRaises(CronError):
            cron_parser.parse('0,' * 30 + '0 * * * *')
        with self.assertRaises(CronError):
            cron_parser.parse(None)

    def test_texto_com_espacos_dentro_do_limite(self):
        self.assertEqual(cron_parser.parse('0 0 1 1 1' + ' ' * 60).texto, '0 0 1 1 1')


class TestProxima(unittest.TestCase):

    def test_estritamente_maior_e_sem_segundos(self):
        self.assertEqual(prox('* * * * *'), D(2026, 10, 15, 10, 8))
        self.assertEqual(prox('* * * * *', D(2026, 10, 15, 10, 8)), D(2026, 10, 15, 10, 9))
        self.assertEqual(prox('8 10 * * *'), D(2026, 10, 15, 10, 8))
        self.assertEqual(prox('7 10 * * *'), D(2026, 10, 16, 10, 7))
        for expr in ('*/15 * * * *', '0 0 29 2 *', '30 2 * * 1-5'):
            r = prox(expr)
            self.assertEqual((r.second, r.microsecond), (0, 0))

    def test_passo_15(self):
        self.assertEqual(sequencia('*/15 * * * *', AGORA, 4),
                         [D(2026, 10, 15, 10, 15), D(2026, 10, 15, 10, 30), D(2026, 10, 15, 10, 45),
                          D(2026, 10, 15, 11, 0)])

    def test_lista_intervalo_passo(self):
        self.assertEqual(sequencia('0 8-12/2 * * *', AGORA, 3),
                         [D(2026, 10, 15, 12, 0), D(2026, 10, 16, 8, 0), D(2026, 10, 16, 10, 0)])
        self.assertEqual(sequencia('5,50 23 * * *', AGORA, 3),
                         [D(2026, 10, 15, 23, 5), D(2026, 10, 15, 23, 50), D(2026, 10, 16, 23, 5)])

    def test_carry_de_ano(self):
        self.assertEqual(prox('59 23 31 12 *', D(2026, 12, 31, 23, 59)), D(2027, 12, 31, 23, 59))
        self.assertEqual(prox('0 0 1 1 *', D(2026, 12, 31, 23, 59, 59)), D(2027, 1, 1, 0, 0))

    def test_29_de_fevereiro_so_em_ano_bissexto(self):
        self.assertEqual(sequencia('0 0 29 2 *', AGORA, 3), [D(2028, 2, 29), D(2032, 2, 29), D(2036, 2, 29)])

    def test_dia_31_pula_meses_curtos(self):
        self.assertEqual(sequencia('0 0 31 * *', AGORA, 4),
                         [D(2026, 10, 31), D(2026, 12, 31), D(2027, 1, 31), D(2027, 3, 31)])

    def test_domingo_0_e_7_equivalentes(self):
        self.assertEqual(prox('0 12 * * 0'), D(2026, 10, 18, 12, 0))
        self.assertEqual(sequencia('0 12 * * 0', AGORA, 5), sequencia('0 12 * * 7', AGORA, 5))

    def test_semantica_ou_vixie(self):
        # Dia 1 OU segunda-feira.
        self.assertEqual(sequencia('0 0 1 * 1', AGORA, 4),
                         [D(2026, 10, 19), D(2026, 10, 26), D(2026, 11, 1), D(2026, 11, 2)])
        # Campo iniciado por '*' nao e restrito: vale o E (dias impares que sejam segunda).
        for data in sequencia('0 0 */2 * 1', AGORA, 6):
            self.assertEqual((data.day % 2, data.weekday()), (1, 0))
        # So dia da semana restrito.
        for data in sequencia('0 0 * * 1', AGORA, 4):
            self.assertEqual(data.weekday(), 0)

    def test_sem_ocorrencia_no_horizonte(self):
        self.assertIsNone(prox('0 0 30 2 *'))
        self.assertIsNone(prox('0 0 31 4,6,9,11 *'))
        self.assertIsNone(prox('0 0 29 2 *', D(2026, 10, 15), horizonte=365))
        self.assertEqual(prox('0 0 29 2 *', D(2026, 10, 15), horizonte=503), D(2028, 2, 29))
        self.assertIsNone(prox('0 0 29 2 *', D(2026, 10, 15), horizonte=501))

    def test_confere_com_forca_bruta(self):
        sorteio = random.Random(20261015)
        inicio = D(2027, 2, 26, 22, 13, 40)
        janela = 8 * 24 * 60
        for _ in range(40):
            expr = ' '.join((
                sorteio.choice(['*', '*/7', '0,30', '15-20', '%d' % sorteio.randint(0, 59)]),
                sorteio.choice(['*', '*/5', '0-3,22-23', '%d' % sorteio.randint(0, 23)]),
                sorteio.choice(['*', '*/3', '1,28,29', '%d-31' % sorteio.randint(25, 31)]),
                sorteio.choice(['*', '2,3', '2', '3-12/3']),
                sorteio.choice(['*', '0', '1-5', '6,7', '*/2']),
            ))
            cron = cron_parser.parse(expr)
            campos = (cron.minutos, cron.horas, cron.dias, cron.meses, cron.dias_semana,
                      cron.dia_restrito, cron.dsem_restrito)
            t = inicio.replace(second=0) + datetime.timedelta(minutes=1)
            esperado = None
            for _ in range(janela):
                if _casa_bruto(campos, t):
                    esperado = t
                    break
                t += datetime.timedelta(minutes=1)
            obtido = cron.next(inicio)
            with self.subTest(expr=expr):
                if esperado is not None:
                    self.assertEqual(obtido, esperado)
                else:
                    self.assertTrue(obtido is None or obtido >= t)

    def test_desempenho(self):
        exprs = ('0 0 30 2 *', '0 0 29 2 1', '59 23 31 12 *', '*/15 * * * *', '0 0 31 4,6,9,11 *',
                 '0-59/7 0-23/5 1-31/3 1-12/5 0-6/3')
        for expr in exprs:
            cron = cron_parser.parse(expr)
            segundos = min(timeit.repeat(lambda: cron.next(AGORA), number=5, repeat=3)) / 5
            with self.subTest(expr=expr):
                self.assertLess(segundos, 0.050, '%s levou %.1f ms' % (expr, segundos * 1000))


class TestDescrever(unittest.TestCase):

    def test_expressoes_comuns(self):
        casos = (
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
        for expr, texto in casos:
            with self.subTest(expr=expr):
                self.assertEqual(cron_parser.parse(expr).describe(), texto)

    def test_qualquer_expressao_valida_tem_descricao(self):
        for expr in ('0-59/7 0-23/5 1-31/3 1-12/5 0-6/3', '1,2 3,4 5-9 6-8 *', '0 0 */2 * 1'):
            with self.subTest(expr=expr):
                self.assertTrue(cron_parser.parse(expr).describe())


class TestPureza(unittest.TestCase):

    def test_sem_now_nem_gluon(self):
        modulos = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'modules')
        for nome in ('cron_parser.py', 'recurrence.py'):
            with open(os.path.join(modulos, nome), encoding='utf-8') as f:
                arvore = ast.parse(f.read())
            chamadas = set(n.func.attr for n in ast.walk(arvore)
                           if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute))
            importados = set()
            for n in ast.walk(arvore):
                if isinstance(n, ast.Import):
                    importados.update(a.name.split('.')[0] for a in n.names)
                elif isinstance(n, ast.ImportFrom):
                    importados.add((n.module or '').split('.')[0])
            with self.subTest(modulo=nome):
                self.assertFalse(chamadas & {'now', 'utcnow', 'today', 'time'}, chamadas)
                self.assertNotIn('gluon', importados)

if __name__ == '__main__':
    unittest.main()
