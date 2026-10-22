# -*- coding: utf-8 -*-
"""Parser CRON proprio, sem bibliotecas (README §7.3).

Modulo puro: nao importa gluon (AGENTS §7.1) e nunca chama datetime.now(); o instante de
referencia sempre chega por parametro (AGENTS §6).

Semantica de tempo: horario de parede, datetime naive, sem fuso nem tratamento de horario de
verao (README §7.1). Um horario inexistente no avanco do relogio cai no misfire do daemon; no
recuo, next_run ja aponta adiante e nao ha reexecucao.

Sintaxe: 5 campos `minuto hora dia_mes mes dia_semana`; cada campo e uma lista de itens
`*`, `*/n`, `a`, `a-b` ou `a-b/n`. dia_semana vai de 0 a 7 (0 e 7 = domingo). Nomes, `L`, `W`,
`#` e `?` sao rejeitados.

Dia do mes x dia da semana (Vixie cron): se os dois campos forem restritos, basta um deles
casar (OU). Um campo que comeca com `*` (inclusive `*/n`) conta como nao restrito, e entao os
dois precisam casar (E).
"""
import calendar
import datetime

DEFAULT_HORIZON = 1461
MAX_LENGTH = 60

_ONE_MINUTE = datetime.timedelta(minutes=1)
_RANGES = (
    ('minuto', 0, 59),
    ('hora', 0, 23),
    ('dia do mês', 1, 31),
    ('mês', 1, 12),
    ('dia da semana', 0, 7),
)
_ALLOWED = set('0123456789*,-/')
_SPECIAL = ('L', 'W', '#', '?')

_MONTHS = ('janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto',
          'setembro', 'outubro', 'novembro', 'dezembro')
_WEEKDAYS = ('domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado')
_WEEKDAYS_PLURAL = ('aos domingos', 'às segundas', 'às terças', 'às quartas', 'às quintas',
                       'às sextas', 'aos sábados')


class CronError(Exception):
    """Expressao CRON invalida; a mensagem e voltada ao usuario, em portugues."""

    def __init__(self, mensagem):
        Exception.__init__(self, mensagem)
        self.message = mensagem


def _integer(texto, campo, minimo, maximo):
    if not texto or not texto.isdigit():
        raise CronError("Campo %s: valor '%s' inválido." % (campo, texto))
    valor = int(texto)
    if valor < minimo or valor > maximo:
        raise CronError("Campo %s: %d fora da faixa %d–%d." % (campo, valor, minimo, maximo))
    return valor


def _item(texto, campo, minimo, maximo):
    """Converte um item em (tipo, inicio, fim, passo); tipo '*' (estrela), 'v' (valor) ou 'r' (intervalo)."""
    passo = 1
    if '/' in texto:
        base, _, txt_passo = texto.partition('/')
        if '/' in txt_passo:
            raise CronError("Campo %s: item '%s' inválido." % (campo, texto))
        if not txt_passo.isdigit():
            raise CronError("Campo %s: passo '%s' inválido." % (campo, txt_passo))
        passo = int(txt_passo)
        if passo == 0:
            raise CronError("Campo %s: o passo não pode ser 0." % campo)
        if base != '*' and '-' not in base:
            raise CronError("Campo %s: use passo apenas com '*' ou intervalo (ex.: */5 ou 0-30/5)." % campo)
    else:
        base = texto
    if base == '*':
        return ('*', minimo, maximo, passo)
    if '-' in base:
        txt_ini, _, txt_fim = base.partition('-')
        inicio = _integer(txt_ini, campo, minimo, maximo)
        fim = _integer(txt_fim, campo, minimo, maximo)
        if inicio > fim:
            raise CronError("Campo %s: intervalo %d-%d invertido." % (campo, inicio, fim))
        return ('r', inicio, fim, passo)
    valor = _integer(base, campo, minimo, maximo)
    return ('v', valor, valor, 1)


def _field(texto, campo, minimo, maximo):
    itens = []
    for parte in texto.split(','):
        if not parte:
            raise CronError("Campo %s: lista com item vazio." % campo)
        itens.append(_item(parte, campo, minimo, maximo))
    valores = set()
    for _, inicio, fim, passo in itens:
        valores.update(range(inicio, fim + 1, passo))
    return tuple(itens), valores


def parse(expr):
    """Valida a expressao e devolve um CronExpr; lanca CronError com mensagem em portugues."""
    if not isinstance(expr, str) or not expr.strip():
        raise CronError('Informe a expressão CRON.')
    texto = expr.strip()
    if len(texto) > MAX_LENGTH:
        raise CronError('A expressão CRON tem no máximo %d caracteres.' % MAX_LENGTH)
    campos = texto.split()
    if len(campos) != 5:
        raise CronError('A expressão CRON precisa de exatamente 5 campos '
                       '(minuto hora dia_mês mês dia_semana); recebidos %d.' % len(campos))
    for caractere in texto:
        if caractere in _SPECIAL or caractere.upper() in _SPECIAL:
            raise CronError("O caractere '%s' não é suportado (sem L, W, # ou ?)." % caractere)
        if caractere.isalpha():
            raise CronError('Nomes de mês ou dia da semana não são suportados; use números.')
        if not caractere.isspace() and caractere not in _ALLOWED:
            raise CronError("Caractere '%s' inválido na expressão CRON." % caractere)
    analisados = []
    for texto_campo, (campo, minimo, maximo) in zip(campos, _RANGES):
        analisados.append(_field(texto_campo, campo, minimo, maximo))
    return CronExpr(' '.join(campos), analisados)


def _last_day(ano, mes):
    return calendar.monthrange(ano, mes)[1]


def _next_month(ano, mes):
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


class CronExpr(object):
    """Expressao CRON ja validada; criada apenas por parse()."""

    def __init__(self, texto, analisados):
        self.text = texto
        (self._it_min, self.minutes), (self._it_hour, self.hours), (self._it_day, self.days), \
            (self._it_month, self.months), (self._it_wday, dsem) = analisados
        self.weekdays = set(d % 7 for d in dsem)
        # Vixie: o campo so e "estrela" (nao restrito) quando o texto comeca com '*'.
        campos = texto.split()
        self.day_restricted = not campos[2].startswith('*')
        self.wday_restricted = not campos[4].startswith('*')
        self._minute_list = sorted(self.minutes)
        self._hour_list = sorted(self.hours)

    def __repr__(self):
        return 'CronExpr(%r)' % self.text

    def _day_matches(self, data):
        casa_dia = data.day in self.days
        casa_dsem = (data.weekday() + 1) % 7 in self.weekdays
        if self.day_restricted and self.wday_restricted:
            return casa_dia or casa_dsem
        return casa_dia and casa_dsem

    def next(self, apos, horizonte_dias=DEFAULT_HORIZON):
        """Primeira ocorrencia estritamente maior que `apos` (segundos = 0) ou None alem do horizonte.

        Avanca campo a campo (mes -> dia -> hora -> minuto) com carry; nunca minuto a minuto.
        """
        limite = apos + datetime.timedelta(days=horizonte_dias)
        t = apos.replace(second=0, microsecond=0) + _ONE_MINUTE
        while t <= limite:
            if t.month not in self.months:
                ano, mes = _next_month(t.year, t.month)
                t = datetime.datetime(ano, mes, 1)
                continue
            if not self._day_matches(t.date()):
                t = datetime.datetime(t.year, t.month, t.day) + datetime.timedelta(days=1)
                continue
            if t.hour not in self.hours:
                hora = _next_value(self._hour_list, t.hour)
                if hora is None:
                    t = datetime.datetime(t.year, t.month, t.day) + datetime.timedelta(days=1)
                else:
                    t = t.replace(hour=hora, minute=0)
                continue
            if t.minute not in self.minutes:
                minuto = _next_value(self._minute_list, t.minute)
                if minuto is None:
                    t = t.replace(minute=0) + datetime.timedelta(hours=1)
                else:
                    t = t.replace(minute=minuto)
                continue
            return t
        return None

    def describe(self):
        """Descricao curta em portugues para a UI (ex.: 'às 02:30, de segunda a sexta')."""
        horario = _describe_time(self._it_min, self._it_hour)
        datas = _describe_dates(self)
        if datas:
            return '%s, %s' % (horario, datas)
        if horario.startswith('às '):
            return horario + ', todos os dias'
        return horario


def _next_value(lista_ordenada, atual):
    for valor in lista_ordenada:
        if valor > atual:
            return valor
    return None


def _join(partes):
    if len(partes) == 1:
        return partes[0]
    return '%s e %s' % (', '.join(partes[:-1]), partes[-1])


def _simple(itens):
    """Valores dos itens quando todos sao valores unicos; senao None."""
    if all(tipo == 'v' for tipo, _, _, _ in itens):
        return sorted(set(inicio for _, inicio, _, _ in itens))
    return None


def _star(itens):
    """Passo de um campo '*' ou '*/n' isolado; senao None."""
    if len(itens) == 1 and itens[0][0] == '*':
        return itens[0][3]
    return None


def _items_text(itens, nome):
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
    return _join(partes)


def _describe_time(it_min, it_hora):
    passo_min, passo_hora = _star(it_min), _star(it_hora)
    minutos, horas = _simple(it_min), _simple(it_hora)
    if passo_hora == 1:
        if passo_min == 1:
            return 'a cada minuto'
        if passo_min is not None:
            return 'a cada %d minutos' % passo_min
        if minutos is not None:
            return 'a cada hora, %s %s' % ('no minuto' if len(minutos) == 1 else 'nos minutos',
                                            _join(['%02d' % m for m in minutos]))
    if len(it_hora) == 1 and it_hora[0][0] == 'r' and it_hora[0][3] == 1:
        faixa = 'das %02d:00 às %02d:59' % (it_hora[0][1], it_hora[0][2])
        if passo_min is not None:
            return '%s, %s' % ('a cada minuto' if passo_min == 1 else 'a cada %d minutos' % passo_min, faixa)
        if minutos is not None and len(minutos) == 1:
            return 'a cada hora no minuto %02d, %s' % (minutos[0], faixa)
    if passo_hora is not None and minutos is not None and len(minutos) == 1:
        return 'a cada %d horas, no minuto %02d' % (passo_hora, minutos[0])
    if minutos is not None and horas is not None and len(minutos) * len(horas) <= 6:
        return 'às ' + _join(['%02d:%02d' % (h, m) for h in horas for m in minutos])
    return 'nos minutos %s das horas %s' % (_items_text(it_min, lambda v: '%02d' % v),
                                           _items_text(it_hora, lambda v: '%02d' % v))


def _describe_weekday(itens):
    valores = _simple(itens)
    if valores is not None:
        valores = sorted(set(v % 7 for v in valores))
        if len(valores) == 1:
            return _WEEKDAYS_PLURAL[valores[0]]
        return 'em ' + _join([_WEEKDAYS[v] for v in valores])
    if len(itens) == 1 and itens[0][0] == 'r' and itens[0][3] == 1:
        return 'de %s a %s' % (_WEEKDAYS[itens[0][1] % 7], _WEEKDAYS[itens[0][2] % 7])
    return 'nos dias da semana %s' % _items_text(itens, lambda v: _WEEKDAYS[v % 7])


def _weekday_when(itens, texto_dsem):
    valores = _simple(itens)
    if valores is not None and len(set(v % 7 for v in valores)) == 1:
        dia = valores[0] % 7
        return ('num ' if dia in (0, 6) else 'numa ') + _WEEKDAYS[dia]
    return texto_dsem


def _describe_dates(cron):
    meses = _simple(cron._it_month)
    if _star(cron._it_month) == 1:
        texto_mes = None
    elif meses is not None:
        texto_mes = _join([_MONTHS[m - 1] for m in meses])
    else:
        texto_mes = 'nos meses %s' % _items_text(cron._it_month, lambda v: _MONTHS[v - 1])

    texto_dia = None
    passo_dia = _star(cron._it_day)
    if passo_dia is not None and passo_dia > 1:
        # README §7.3: '*/n' no dia do mes e "a cada n dias a partir do dia 1" (sem "de cada mes").
        texto_dia = 'a cada %d dias a partir do dia 1' % passo_dia
    elif cron.day_restricted or passo_dia != 1:
        dias = _simple(cron._it_day)
        if dias is not None and len(dias) == 1:
            texto_dia = 'no dia %d' % dias[0]
        elif dias is not None:
            texto_dia = 'nos dias ' + _join([str(d) for d in dias])
        else:
            texto_dia = 'nos dias do mês %s' % _items_text(cron._it_day, str)
        if texto_mes is None:
            texto_dia += ' de cada mês'
        elif meses is not None:
            texto_dia += ' de ' + texto_mes
            texto_mes = None

    texto_dsem = None
    if cron.wday_restricted or _star(cron._it_wday) != 1:
        texto_dsem = _describe_weekday(cron._it_wday)

    partes = []
    if texto_dia and texto_dsem and passo_dia is not None and passo_dia > 1:
        # Semantica E do Vixie (dia comeca com '*'): "quando cair numa segunda".
        partes.append(texto_dia + ', quando cair ' + _weekday_when(cron._it_wday, texto_dsem))
    elif texto_dia and texto_dsem:
        conector = ' ou ' if cron.day_restricted and cron.wday_restricted else ' e '
        partes.append(texto_dia + conector + texto_dsem)
    elif texto_dia or texto_dsem:
        partes.append(texto_dia or texto_dsem)
    if texto_mes:
        partes.append(('em ' + texto_mes) if meses is not None else texto_mes)
    return ', '.join(partes)
