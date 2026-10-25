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

    def __init__(self, message):
        Exception.__init__(self, message)
        self.message = message


def _integer(text, field, minimum, maximum):
    if not text or not text.isdigit():
        raise CronError("Campo %s: valor '%s' inválido." % (field, text))
    value = int(text)
    if value < minimum or value > maximum:
        raise CronError("Campo %s: %d fora da faixa %d–%d." % (field, value, minimum, maximum))
    return value


def _item(text, field, minimum, maximum):
    """Converte um item em (tipo, inicio, fim, passo); tipo '*' (estrela), 'v' (valor) ou 'r' (intervalo)."""
    step = 1
    if '/' in text:
        base, _, txt_step = text.partition('/')
        if '/' in txt_step:
            raise CronError("Campo %s: item '%s' inválido." % (field, text))
        if not txt_step.isdigit():
            raise CronError("Campo %s: passo '%s' inválido." % (field, txt_step))
        step = int(txt_step)
        if step == 0:
            raise CronError("Campo %s: o passo não pode ser 0." % field)
        if base != '*' and '-' not in base:
            raise CronError("Campo %s: use passo apenas com '*' ou intervalo (ex.: */5 ou 0-30/5)." % field)
    else:
        base = text
    if base == '*':
        return ('*', minimum, maximum, step)
    if '-' in base:
        txt_ini, _, txt_end = base.partition('-')
        start = _integer(txt_ini, field, minimum, maximum)
        end = _integer(txt_end, field, minimum, maximum)
        if start > end:
            raise CronError("Campo %s: intervalo %d-%d invertido." % (field, start, end))
        return ('r', start, end, step)
    value = _integer(base, field, minimum, maximum)
    return ('v', value, value, 1)


def _field(text, field, minimum, maximum):
    items = []
    for part in text.split(','):
        if not part:
            raise CronError("Campo %s: lista com item vazio." % field)
        items.append(_item(part, field, minimum, maximum))
    values = set()
    for _, start, end, step in items:
        values.update(range(start, end + 1, step))
    return tuple(items), values


def parse(expr):
    """Valida a expressao e devolve um CronExpr; lanca CronError com mensagem em portugues."""
    if not isinstance(expr, str) or not expr.strip():
        raise CronError('Informe a expressão CRON.')
    text = expr.strip()
    if len(text) > MAX_LENGTH:
        raise CronError('A expressão CRON tem no máximo %d caracteres.' % MAX_LENGTH)
    fields = text.split()
    if len(fields) != 5:
        raise CronError('A expressão CRON precisa de exatamente 5 campos '
                       '(minuto hora dia_mês mês dia_semana); recebidos %d.' % len(fields))
    for character in text:
        if character in _SPECIAL or character.upper() in _SPECIAL:
            raise CronError("O caractere '%s' não é suportado (sem L, W, # ou ?)." % character)
        if character.isalpha():
            raise CronError('Nomes de mês ou dia da semana não são suportados; use números.')
        if not character.isspace() and character not in _ALLOWED:
            raise CronError("Caractere '%s' inválido na expressão CRON." % character)
    analyzed = []
    for text_field, (field, min_value, max_value) in zip(fields, _RANGES):
        analyzed.append(_field(text_field, field, min_value, max_value))
    return CronExpr(' '.join(fields), analyzed)


def _last_day(year, month):
    return calendar.monthrange(year, month)[1]


def _next_month(year, month):
    return (year + 1, 1) if month == 12 else (year, month + 1)


class CronExpr(object):
    """Expressao CRON ja validada; criada apenas por parse()."""

    def __init__(self, text, analyzed):
        self.text = text
        (self._it_min, self.minutes), (self._it_hour, self.hours), (self._it_day, self.days), \
            (self._it_month, self.months), (self._it_wday, wday) = analyzed
        self.weekdays = set(d % 7 for d in wday)
        # Vixie: o campo so e "estrela" (nao restrito) quando o texto comeca com '*'.
        fields = text.split()
        self.day_restricted = not fields[2].startswith('*')
        self.wday_restricted = not fields[4].startswith('*')
        self._minute_list = sorted(self.minutes)
        self._hour_list = sorted(self.hours)

    def __repr__(self):
        return 'CronExpr(%r)' % self.text

    def _day_matches(self, date):
        match_day = date.day in self.days
        match_wday = (date.weekday() + 1) % 7 in self.weekdays
        if self.day_restricted and self.wday_restricted:
            return match_day or match_wday
        return match_day and match_wday

    def next(self, after, horizon_days=DEFAULT_HORIZON):
        """Primeira ocorrencia estritamente maior que `apos` (segundos = 0) ou None alem do horizonte.

        Avanca campo a campo (mes -> dia -> hora -> minuto) com carry; nunca minuto a minuto.
        """
        limit = after + datetime.timedelta(days=horizon_days)
        t = after.replace(second=0, microsecond=0) + _ONE_MINUTE
        while t <= limit:
            if t.month not in self.months:
                year, month = _next_month(t.year, t.month)
                t = datetime.datetime(year, month, 1)
                continue
            if not self._day_matches(t.date()):
                t = datetime.datetime(t.year, t.month, t.day) + datetime.timedelta(days=1)
                continue
            if t.hour not in self.hours:
                hour = _next_value(self._hour_list, t.hour)
                if hour is None:
                    t = datetime.datetime(t.year, t.month, t.day) + datetime.timedelta(days=1)
                else:
                    t = t.replace(hour=hour, minute=0)
                continue
            if t.minute not in self.minutes:
                minute = _next_value(self._minute_list, t.minute)
                if minute is None:
                    t = t.replace(minute=0) + datetime.timedelta(hours=1)
                else:
                    t = t.replace(minute=minute)
                continue
            return t
        return None

    def describe(self):
        """Descricao curta em portugues para a UI (ex.: 'às 02:30, de segunda a sexta')."""
        schedule_time = _describe_time(self._it_min, self._it_hour)
        dates = _describe_dates(self)
        if dates:
            return '%s, %s' % (schedule_time, dates)
        if schedule_time.startswith('às '):
            return schedule_time + ', todos os dias'
        return schedule_time


def _next_value(sorted_list, current_value):
    for value in sorted_list:
        if value > current_value:
            return value
    return None


def _join(parts):
    if len(parts) == 1:
        return parts[0]
    return '%s e %s' % (', '.join(parts[:-1]), parts[-1])


def _simple(items):
    """Valores dos itens quando todos sao valores unicos; senao None."""
    if all(kind == 'v' for kind, _, _, _ in items):
        return sorted(set(start for _, start, _, _ in items))
    return None


def _star(items):
    """Passo de um campo '*' ou '*/n' isolado; senao None."""
    if len(items) == 1 and items[0][0] == '*':
        return items[0][3]
    return None


def _items_text(items, name):
    parts = []
    for kind, start, end, step in items:
        if kind == '*':
            parts.append('todos' if step == 1 else 'a cada %d' % step)
        elif kind == 'v':
            parts.append(name(start))
        elif step == 1:
            parts.append('%s a %s' % (name(start), name(end)))
        else:
            parts.append('de %s a %s a cada %d' % (name(start), name(end), step))
    return _join(parts)


def _describe_time(it_min, it_hour):
    step_min, step_hour = _star(it_min), _star(it_hour)
    minutes, hours = _simple(it_min), _simple(it_hour)
    if step_hour == 1:
        if step_min == 1:
            return 'a cada minuto'
        if step_min is not None:
            return 'a cada %d minutos' % step_min
        if minutes is not None:
            return 'a cada hora, %s %s' % ('no minuto' if len(minutes) == 1 else 'nos minutos',
                                            _join(['%02d' % m for m in minutes]))
    if len(it_hour) == 1 and it_hour[0][0] == 'r' and it_hour[0][3] == 1:
        span = 'das %02d:00 às %02d:59' % (it_hour[0][1], it_hour[0][2])
        if step_min is not None:
            return '%s, %s' % ('a cada minuto' if step_min == 1 else 'a cada %d minutos' % step_min, span)
        if minutes is not None and len(minutes) == 1:
            return 'a cada hora no minuto %02d, %s' % (minutes[0], span)
    if step_hour is not None and minutes is not None and len(minutes) == 1:
        return 'a cada %d horas, no minuto %02d' % (step_hour, minutes[0])
    if minutes is not None and hours is not None and len(minutes) * len(hours) <= 6:
        return 'às ' + _join(['%02d:%02d' % (h, m) for h in hours for m in minutes])
    return 'nos minutos %s das horas %s' % (_items_text(it_min, lambda v: '%02d' % v),
                                           _items_text(it_hour, lambda v: '%02d' % v))


def _describe_weekday(items):
    values = _simple(items)
    if values is not None:
        values = sorted(set(v % 7 for v in values))
        if len(values) == 1:
            return _WEEKDAYS_PLURAL[values[0]]
        return 'em ' + _join([_WEEKDAYS[v] for v in values])
    if len(items) == 1 and items[0][0] == 'r' and items[0][3] == 1:
        return 'de %s a %s' % (_WEEKDAYS[items[0][1] % 7], _WEEKDAYS[items[0][2] % 7])
    return 'nos dias da semana %s' % _items_text(items, lambda v: _WEEKDAYS[v % 7])


def _weekday_when(items, weekday_text):
    values = _simple(items)
    if values is not None and len(set(v % 7 for v in values)) == 1:
        day = values[0] % 7
        return ('num ' if day in (0, 6) else 'numa ') + _WEEKDAYS[day]
    return weekday_text


def _describe_dates(cron):
    months = _simple(cron._it_month)
    if _star(cron._it_month) == 1:
        text_month = None
    elif months is not None:
        text_month = _join([_MONTHS[m - 1] for m in months])
    else:
        text_month = 'nos meses %s' % _items_text(cron._it_month, lambda v: _MONTHS[v - 1])

    text_day = None
    step_day = _star(cron._it_day)
    if step_day is not None and step_day > 1:
        # README §7.3: '*/n' no dia do mes e "a cada n dias a partir do dia 1" (sem "de cada mes").
        text_day = 'a cada %d dias a partir do dia 1' % step_day
    elif cron.day_restricted or step_day != 1:
        days = _simple(cron._it_day)
        if days is not None and len(days) == 1:
            text_day = 'no dia %d' % days[0]
        elif days is not None:
            text_day = 'nos dias ' + _join([str(d) for d in days])
        else:
            text_day = 'nos dias do mês %s' % _items_text(cron._it_day, str)
        if text_month is None:
            text_day += ' de cada mês'
        elif months is not None:
            text_day += ' de ' + text_month
            text_month = None

    text_wday = None
    if cron.wday_restricted or _star(cron._it_wday) != 1:
        text_wday = _describe_weekday(cron._it_wday)

    parts = []
    if text_day and text_wday and step_day is not None and step_day > 1:
        # Semantica E do Vixie (dia comeca com '*'): "quando cair numa segunda".
        parts.append(text_day + ', quando cair ' + _weekday_when(cron._it_wday, text_wday))
    elif text_day and text_wday:
        connector = ' ou ' if cron.day_restricted and cron.wday_restricted else ' e '
        parts.append(text_day + connector + text_wday)
    elif text_day or text_wday:
        parts.append(text_day or text_wday)
    if text_month:
        parts.append(('em ' + text_month) if months is not None else text_month)
    return ', '.join(parts)
