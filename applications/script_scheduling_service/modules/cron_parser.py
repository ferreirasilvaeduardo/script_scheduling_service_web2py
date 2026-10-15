# -*- coding: utf-8 -*-
"""Parser CRON proprio, sem bibliotecas (README §7.3).

Modulo puro: nao importa gluon (AGENTS §7.1) e nunca chama datetime.now(); o instante de
referencia sempre chega por parametro (AGENTS §6).

Semantica de tempo: horario de parede, datetime naive, sem fuso nem tratamento de horario de
verao (README §7.1). Um horario inexistente no avanco do relogio cai no misfire do daemon; no
recuo, proxima_execucao ja aponta adiante e nao ha reexecucao.

Sintaxe: 5 campos `minuto hora dia_mes mes dia_semana`; cada campo e uma lista de itens
`*`, `*/n`, `a`, `a-b` ou `a-b/n`. dia_semana vai de 0 a 7 (0 e 7 = domingo). Nomes, `L`, `W`,
`#` e `?` sao rejeitados.

Dia do mes x dia da semana (Vixie cron): se os dois campos forem restritos, basta um deles
casar (OU). Um campo que comeca com `*` (inclusive `*/n`) conta como nao restrito, e entao os
dois precisam casar (E).
"""
import calendar
import datetime

HORIZONTE_PADRAO = 1461
TAMANHO_MAXIMO = 60

_UM_MINUTO = datetime.timedelta(minutes=1)
_FAIXAS = (
    ('minuto', 0, 59),
    ('hora', 0, 23),
    ('dia do mês', 1, 31),
    ('mês', 1, 12),
    ('dia da semana', 0, 7),
)
_PERMITIDOS = set('0123456789*,-/')
_ESPECIAIS = ('L', 'W', '#', '?')

_MESES = ('janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto',
          'setembro', 'outubro', 'novembro', 'dezembro')
_DIAS_SEMANA = ('domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado')
_DIAS_SEMANA_PLURAL = ('aos domingos', 'às segundas', 'às terças', 'às quartas', 'às quintas',
                       'às sextas', 'aos sábados')


class CronErro(Exception):
    """Expressao CRON invalida; a mensagem e voltada ao usuario, em portugues."""

    def __init__(self, mensagem):
        Exception.__init__(self, mensagem)
        self.mensagem = mensagem


def _inteiro(texto, campo, minimo, maximo):
    if not texto or not texto.isdigit():
        raise CronErro("Campo %s: valor '%s' inválido." % (campo, texto))
    valor = int(texto)
    if valor < minimo or valor > maximo:
        raise CronErro("Campo %s: %d fora da faixa %d–%d." % (campo, valor, minimo, maximo))
    return valor


def _item(texto, campo, minimo, maximo):
    """Converte um item em (tipo, inicio, fim, passo); tipo '*' (estrela), 'v' (valor) ou 'r' (intervalo)."""
    passo = 1
    if '/' in texto:
        base, _, txt_passo = texto.partition('/')
        if '/' in txt_passo:
            raise CronErro("Campo %s: item '%s' inválido." % (campo, texto))
        if not txt_passo.isdigit():
            raise CronErro("Campo %s: passo '%s' inválido." % (campo, txt_passo))
        passo = int(txt_passo)
        if passo == 0:
            raise CronErro("Campo %s: o passo não pode ser 0." % campo)
        if base != '*' and '-' not in base:
            raise CronErro("Campo %s: use passo apenas com '*' ou intervalo (ex.: */5 ou 0-30/5)." % campo)
    else:
        base = texto
    if base == '*':
        return ('*', minimo, maximo, passo)
    if '-' in base:
        txt_ini, _, txt_fim = base.partition('-')
        inicio = _inteiro(txt_ini, campo, minimo, maximo)
        fim = _inteiro(txt_fim, campo, minimo, maximo)
        if inicio > fim:
            raise CronErro("Campo %s: intervalo %d-%d invertido." % (campo, inicio, fim))
        return ('r', inicio, fim, passo)
    valor = _inteiro(base, campo, minimo, maximo)
    return ('v', valor, valor, 1)


def _campo(texto, campo, minimo, maximo):
    itens = []
    for parte in texto.split(','):
        if not parte:
            raise CronErro("Campo %s: lista com item vazio." % campo)
        itens.append(_item(parte, campo, minimo, maximo))
    valores = set()
    for _, inicio, fim, passo in itens:
        valores.update(range(inicio, fim + 1, passo))
    return tuple(itens), valores


def parse(expr):
    """Valida a expressao e devolve um CronExpr; lanca CronErro com mensagem em portugues."""
    if not isinstance(expr, str) or not expr.strip():
        raise CronErro('Informe a expressão CRON.')
    texto = expr.strip()
    if len(texto) > TAMANHO_MAXIMO:
        raise CronErro('A expressão CRON tem no máximo %d caracteres.' % TAMANHO_MAXIMO)
    campos = texto.split()
    if len(campos) != 5:
        raise CronErro('A expressão CRON precisa de exatamente 5 campos '
                       '(minuto hora dia_mês mês dia_semana); recebidos %d.' % len(campos))
    for caractere in texto:
        if caractere in _ESPECIAIS or caractere.upper() in _ESPECIAIS:
            raise CronErro("O caractere '%s' não é suportado (sem L, W, # ou ?)." % caractere)
        if caractere.isalpha():
            raise CronErro('Nomes de mês ou dia da semana não são suportados; use números.')
        if not caractere.isspace() and caractere not in _PERMITIDOS:
            raise CronErro("Caractere '%s' inválido na expressão CRON." % caractere)
    analisados = []
    for texto_campo, (campo, minimo, maximo) in zip(campos, _FAIXAS):
        analisados.append(_campo(texto_campo, campo, minimo, maximo))
    return CronExpr(' '.join(campos), analisados)


def _ultimo_dia(ano, mes):
    return calendar.monthrange(ano, mes)[1]


def _proximo_mes(ano, mes):
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


class CronExpr(object):
    """Expressao CRON ja validada; criada apenas por parse()."""

    def __init__(self, texto, analisados):
        self.texto = texto
        (self._it_min, self.minutos), (self._it_hora, self.horas), (self._it_dia, self.dias), \
            (self._it_mes, self.meses), (self._it_dsem, dsem) = analisados
        self.dias_semana = set(d % 7 for d in dsem)
        # Vixie: o campo so e "estrela" (nao restrito) quando o texto comeca com '*'.
        campos = texto.split()
        self.dia_restrito = not campos[2].startswith('*')
        self.dsem_restrito = not campos[4].startswith('*')
        self._lista_min = sorted(self.minutos)
        self._lista_hora = sorted(self.horas)

    def __repr__(self):
        return 'CronExpr(%r)' % self.texto

    def _dia_casa(self, data):
        casa_dia = data.day in self.dias
        casa_dsem = (data.weekday() + 1) % 7 in self.dias_semana
        if self.dia_restrito and self.dsem_restrito:
            return casa_dia or casa_dsem
        return casa_dia and casa_dsem

    def proxima(self, apos, horizonte_dias=HORIZONTE_PADRAO):
        """Primeira ocorrencia estritamente maior que `apos` (segundos = 0) ou None alem do horizonte.

        Avanca campo a campo (mes -> dia -> hora -> minuto) com carry; nunca minuto a minuto.
        """
        limite = apos + datetime.timedelta(days=horizonte_dias)
        t = apos.replace(second=0, microsecond=0) + _UM_MINUTO
        while t <= limite:
            if t.month not in self.meses:
                ano, mes = _proximo_mes(t.year, t.month)
                t = datetime.datetime(ano, mes, 1)
                continue
            if not self._dia_casa(t.date()):
                t = datetime.datetime(t.year, t.month, t.day) + datetime.timedelta(days=1)
                continue
            if t.hour not in self.horas:
                hora = _seguinte(self._lista_hora, t.hour)
                if hora is None:
                    t = datetime.datetime(t.year, t.month, t.day) + datetime.timedelta(days=1)
                else:
                    t = t.replace(hour=hora, minute=0)
                continue
            if t.minute not in self.minutos:
                minuto = _seguinte(self._lista_min, t.minute)
                if minuto is None:
                    t = t.replace(minute=0) + datetime.timedelta(hours=1)
                else:
                    t = t.replace(minute=minuto)
                continue
            return t
        return None

    def descrever(self):
        """Descricao curta em portugues para a UI (ex.: 'às 02:30, de segunda a sexta')."""
        horario = _descrever_horario(self._it_min, self._it_hora)
        datas = _descrever_datas(self)
        if datas:
            return '%s, %s' % (horario, datas)
        if horario.startswith('às '):
            return horario + ', todos os dias'
        return horario


def _seguinte(lista_ordenada, atual):
    for valor in lista_ordenada:
        if valor > atual:
            return valor
    return None


def _juntar(partes):
    if len(partes) == 1:
        return partes[0]
    return '%s e %s' % (', '.join(partes[:-1]), partes[-1])


def _simples(itens):
    """Valores dos itens quando todos sao valores unicos; senao None."""
    if all(tipo == 'v' for tipo, _, _, _ in itens):
        return sorted(set(inicio for _, inicio, _, _ in itens))
    return None


def _estrela(itens):
    """Passo de um campo '*' ou '*/n' isolado; senao None."""
    if len(itens) == 1 and itens[0][0] == '*':
        return itens[0][3]
    return None


def _texto_itens(itens, nome):
    partes = []
    for tipo, inicio, fim, passo in itens:
        if tipo == '*':
            partes.append('todos' if passo == 1 else 'a cada %d' % passo)
        elif tipo == 'v':
            partes.append(nome(inicio))
        elif passo == 1:
            partes.append('%s a %s' % (nome(inicio), nome(fim)))
        else:
            partes.append('de %s a %s a cada %d' % (nome(inicio), nome(fim), passo))
    return _juntar(partes)


def _descrever_horario(it_min, it_hora):
    passo_min, passo_hora = _estrela(it_min), _estrela(it_hora)
    minutos, horas = _simples(it_min), _simples(it_hora)
    if passo_hora == 1:
        if passo_min == 1:
            return 'a cada minuto'
        if passo_min is not None:
            return 'a cada %d minutos' % passo_min
        if minutos is not None:
            return 'a cada hora, %s %s' % ('no minuto' if len(minutos) == 1 else 'nos minutos',
                                            _juntar(['%02d' % m for m in minutos]))
    if len(it_hora) == 1 and it_hora[0][0] == 'r' and it_hora[0][3] == 1:
        faixa = 'das %02d:00 às %02d:59' % (it_hora[0][1], it_hora[0][2])
        if passo_min is not None:
            return '%s, %s' % ('a cada minuto' if passo_min == 1 else 'a cada %d minutos' % passo_min, faixa)
        if minutos is not None and len(minutos) == 1:
            return 'a cada hora no minuto %02d, %s' % (minutos[0], faixa)
    if passo_hora is not None and minutos is not None and len(minutos) == 1:
        return 'a cada %d horas, no minuto %02d' % (passo_hora, minutos[0])
    if minutos is not None and horas is not None and len(minutos) * len(horas) <= 6:
        return 'às ' + _juntar(['%02d:%02d' % (h, m) for h in horas for m in minutos])
    return 'nos minutos %s das horas %s' % (_texto_itens(it_min, lambda v: '%02d' % v),
                                           _texto_itens(it_hora, lambda v: '%02d' % v))


def _descrever_dsem(itens):
    valores = _simples(itens)
    if valores is not None:
        valores = sorted(set(v % 7 for v in valores))
        if len(valores) == 1:
            return _DIAS_SEMANA_PLURAL[valores[0]]
        return 'em ' + _juntar([_DIAS_SEMANA[v] for v in valores])
    if len(itens) == 1 and itens[0][0] == 'r' and itens[0][3] == 1:
        return 'de %s a %s' % (_DIAS_SEMANA[itens[0][1] % 7], _DIAS_SEMANA[itens[0][2] % 7])
    return 'nos dias da semana %s' % _texto_itens(itens, lambda v: _DIAS_SEMANA[v % 7])


def _descrever_datas(cron):
    meses = _simples(cron._it_mes)
    if _estrela(cron._it_mes) == 1:
        texto_mes = None
    elif meses is not None:
        texto_mes = _juntar([_MESES[m - 1] for m in meses])
    else:
        texto_mes = 'nos meses %s' % _texto_itens(cron._it_mes, lambda v: _MESES[v - 1])

    texto_dia = None
    if cron.dia_restrito or _estrela(cron._it_dia) != 1:
        dias = _simples(cron._it_dia)
        if dias is not None and len(dias) == 1:
            texto_dia = 'no dia %d' % dias[0]
        elif dias is not None:
            texto_dia = 'nos dias ' + _juntar([str(d) for d in dias])
        else:
            texto_dia = 'nos dias do mês %s' % _texto_itens(cron._it_dia, str)
        if texto_mes is None:
            texto_dia += ' de cada mês'
        elif meses is not None:
            texto_dia += ' de ' + texto_mes
            texto_mes = None

    texto_dsem = None
    if cron.dsem_restrito or _estrela(cron._it_dsem) != 1:
        texto_dsem = _descrever_dsem(cron._it_dsem)

    partes = []
    if texto_dia and texto_dsem:
        conector = ' ou ' if cron.dia_restrito and cron.dsem_restrito else ' e '
        partes.append(texto_dia + conector + texto_dsem)
    elif texto_dia or texto_dsem:
        partes.append(texto_dia or texto_dsem)
    if texto_mes:
        partes.append(('em ' + texto_mes) if meses is not None else texto_mes)
    return ', '.join(partes)
