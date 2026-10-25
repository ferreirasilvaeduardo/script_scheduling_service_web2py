# -*- coding: utf-8 -*-
"""Calculo de recorrencia e politica de misfire dos agendamentos (README §7.1-§7.5).

Modulo puro: nao importa gluon (AGENTS §7.1) e nunca chama datetime.now(); o "agora" sempre
chega por parametro (no daemon, SYSDATE do banco; AGENTS §6).

Semantica de tempo: horario de parede, datetime naive, sem fuso nem tratamento de horario de
verao (README §7.1). Saltos do relogio seguem a politica de misfire; o banco deve operar sem
horario de verao. Toda data devolvida tem
segundos e microssegundos zerados.

Regras (decisoes do F5.1, README §7.2):
* `data_inicio` e o piso inclusivo, com precisao de minuto: a primeira ocorrencia e a primeira
  >= data_inicio (truncada), alem de > `apos`.
* `data_fim` e o teto inclusivo: uma ocorrencia exatamente em data_fim ainda vale.
* UNICA ocorre em data_inicio (truncada); so e devolvida se for > `apos`.
* MENSAL com dia inexistente no mes cai no ultimo dia do mes.
* CRON sem ocorrencia no horizonte lanca CronError (o daemon pausa com INVALID_CRON), exceto
  quando data_fim cai dentro do horizonte: ai a regra apenas terminou (None).
"""
import calendar
import collections
import datetime
import re

from sss.core import cron_parser
from sss.core.cron_parser import CronError

TYPES = ('ONCE', 'DAILY', 'WEEKLY', 'MONTHLY', 'CRON')
MISFIRE_POLICIES = ('RUN_ONCE', 'SKIP')
MISSED_LIMIT = 10000
DEFAULT_HORIZON = cron_parser.DEFAULT_HORIZON

_RE_TIME = re.compile(r'^([01][0-9]|2[0-3]):[0-5][0-9]$')
_RE_WDAY = re.compile(r'^[1-7](,[1-7]){0,6}$')
_ONE_MINUTE = datetime.timedelta(minutes=1)
_ONE_DAY = datetime.timedelta(days=1)
_CACHE_CRON = {}
_CACHE_MAX = 256

# occurrence (CR-007, R-27): a vencida mais recente coberta pelo ticket; None quando nao ha ticket.
# cron_error (CR-008, R-19): a proxima ocorrencia nao existe no horizonte; next_date fica None e o daemon
# aplica sobreposicao e SKIP normalmente antes de pausar a regra com INVALID_CRON.
Decision = collections.namedtuple('Decision', ['create_ticket', 'next_date', 'missed', 'complete', 'occurrence',
                                               'cron_error'])
Decision.__new__.__defaults__ = (None, False)


def truncate_seconds(dt):
    """Zera segundos e microssegundos (None passa direto)."""
    if dt is None:
        return None
    return dt.replace(second=0, microsecond=0)


def without_microseconds(dt):
    """Zera microssegundos: nenhum datetime com microssegundos e comparado a coluna DATE (README §7.5)."""
    if dt is None:
        return None
    return dt.replace(microsecond=0)


def _empty(value):
    return value is None or (isinstance(value, str) and not value.strip())


def validate_rule(rule, horizon_days=DEFAULT_HORIZON):
    """Espelha as CKs de tbsss_schedules (_trec, _campos, _hora, _dsem, _dia, _fim) e valida o CRON.

    Devolve {campo: mensagem} (nome do campo do formulario: texto do erro); vazio quando a regra e valida.
    """
    errors = collections.OrderedDict()
    kind = rule.get('recurrence_type')
    hour = rule.get('run_time')
    wday = rule.get('week_days')
    day = rule.get('month_day')
    cron = rule.get('cron_expression')
    start = rule.get('start_date')
    end = rule.get('end_date')

    if kind not in TYPES:
        errors['recurrence_type'] = 'Tipo de recorrência inválido.'
    if not isinstance(start, datetime.datetime):
        errors['start_date'] = 'Informe a data e hora de início.'
    if end is not None:
        if not isinstance(end, datetime.datetime):
            errors['end_date'] = 'Data de fim inválida.'
        elif isinstance(start, datetime.datetime) and end < start:
            errors['end_date'] = 'A data de fim não pode ser anterior à de início.'
    if not _empty(hour) and not (isinstance(hour, str) and _RE_TIME.match(hour)):
        errors['run_time'] = 'Horário inválido; use HH:MM (00:00 a 23:59).'
    if not _empty(wday) and not (isinstance(wday, str) and _RE_WDAY.match(wday)):
        errors['week_days'] = 'Dias da semana inválidos; use números de 1 (segunda) a 7 (domingo), ex.: 1,3,5.'
    if not _empty(day):
        try:
            valid = 1 <= int(day) <= 31 and str(day).strip().isdigit()
        except (TypeError, ValueError):
            valid = False
        if not valid:
            errors['month_day'] = 'Dia do mês deve estar entre 1 e 31.'

    required = {'DAILY': ('run_time',), 'WEEKLY': ('run_time', 'week_days'),
                    'MONTHLY': ('run_time', 'month_day'), 'CRON': ('cron_expression',)}
    for field in required.get(kind, ()):
        if _empty(rule.get(field)) and field not in errors:
            errors[field] = 'Campo obrigatório para recorrência %s.' % kind

    if kind == 'CRON' and not _empty(cron) and 'cron_expression' not in errors:
        try:
            expr = cron_parser.parse(cron)
            if isinstance(start, datetime.datetime):
                floor = truncate_seconds(start) - _ONE_MINUTE
                # Com data_fim dentro do horizonte, a falta de ocorrencia e "sem proxima execucao" (o servico
                # da a mensagem), e nao expressao invalida (README §7.3, CR-007 R-32).
                end_no_horizon = (isinstance(end, datetime.datetime)
                                    and end <= floor + datetime.timedelta(days=horizon_days))
                if expr.next(floor, horizon_days) is None and not end_no_horizon:
                    errors['cron_expression'] = ('A expressão não ocorre nos próximos %d dias a partir do início.'
                                               % horizon_days)
        except CronError as error:
            errors['cron_expression'] = error.message
    return errors


def _expression(text):
    """parse() com cache pequeno: o calculo de vencidas chama next_run em laco."""
    expr = _CACHE_CRON.get(text)
    if expr is None:
        expr = cron_parser.parse(text)
        if len(_CACHE_CRON) >= _CACHE_MAX:
            _CACHE_CRON.clear()
        _CACHE_CRON[text] = expr
    return expr


def _hour_minute(hour):
    hh, mm = hour.split(':')
    return int(hh), int(mm)


def _daily(ref, hour):
    hh, mm = _hour_minute(hour)
    candidate = datetime.datetime(ref.year, ref.month, ref.day, hh, mm)
    return candidate if candidate > ref else candidate + _ONE_DAY


def _weekly(ref, hour, weekdays):
    hh, mm = _hour_minute(hour)
    days = set(int(d) for d in weekdays.split(','))
    base = datetime.datetime(ref.year, ref.month, ref.day, hh, mm)
    for offset in range(8):
        candidate = base + datetime.timedelta(days=offset)
        if candidate > ref and candidate.isoweekday() in days:
            return candidate
    return None


def _monthly(ref, hour, month_day):
    hh, mm = _hour_minute(hour)
    day = int(month_day)
    year, month = ref.year, ref.month
    for _ in range(2):
        last = calendar.monthrange(year, month)[1]
        candidate = datetime.datetime(year, month, min(day, last), hh, mm)
        if candidate > ref:
            return candidate
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return None


def next_run(rule, after, horizon_days=DEFAULT_HORIZON):
    """Primeira ocorrencia > `apos`, respeitando o piso data_inicio e o teto data_fim; None se nao houver.

    Lanca CronError para expressao CRON invalida ou sem ocorrencia no horizonte (README §7.3).
    """
    kind = rule['recurrence_type']
    floor = truncate_seconds(rule['start_date'])
    end = rule.get('end_date')
    if kind == 'ONCE':
        result = floor if floor > after else None
    else:
        # Ocorrencias tem precisao de minuto: ">= piso" equivale a "> piso - 1 minuto".
        ref = max(after, floor - _ONE_MINUTE)
        if kind == 'DAILY':
            result = _daily(ref, rule['run_time'])
        elif kind == 'WEEKLY':
            result = _weekly(ref, rule['run_time'], rule['week_days'])
        elif kind == 'MONTHLY':
            result = _monthly(ref, rule['run_time'], rule['month_day'])
        elif kind == 'CRON':
            result = _expression(rule['cron_expression']).next(ref, horizon_days)
            if result is None:
                if end is not None and end <= ref + datetime.timedelta(days=horizon_days):
                    return None
                raise CronError('A expressão não ocorre nos próximos %d dias.' % horizon_days)
        else:
            raise ValueError('tipo_recorrencia inválido: %r' % (kind,))
    if result is not None and end is not None and result > end:
        return None
    return truncate_seconds(result)


def next_runs(rule, after, n, horizon_days=DEFAULT_HORIZON):
    """Ate `n` proximas ocorrencias depois de `apos` (previa da UI)."""
    items = []
    current = after
    while len(items) < n:
        current = next_run(rule, current, horizon_days)
        if current is None:
            break
        items.append(current)
    return items


def _due(rule, start, now, horizon_days):
    """(quantidade, ultima) das ocorrencias em [inicio, agora], contando `inicio`; para em MISSED_LIMIT + 1."""
    total = 1
    last = start
    if rule['recurrence_type'] == 'ONCE':
        return total, last
    current = start
    while total <= MISSED_LIMIT:
        try:
            current = next_run(rule, current, horizon_days)
        except CronError:
            break  # sem ocorrencia no horizonte depois de 'atual': nao ha mais vencidas (CR-008, R-19)
        if current is None or current > now:
            break
        total += 1
        last = current
    if total > MISSED_LIMIT:
        # O limite da contagem nao pode limitar a ocorrencia coberta pelo ticket.
        cap = truncate_seconds(min(now, rule.get('end_date') or now))
        left, right = last, cap
        while left < right:
            minutes = int((right - left).total_seconds() // 60)
            middle = left + datetime.timedelta(minutes=minutes // 2)
            try:
                next_value = next_run(rule, middle, horizon_days)
            except CronError:
                next_value = None
            if next_value is not None and next_value <= cap:
                last = next_value
                left = next_value
            else:
                right = middle
    return total, last


def evaluate_trigger(rule, now, misfire_policy, misfire_tolerance_s, horizon_days=DEFAULT_HORIZON):
    """Decide o disparo de uma regra vencida (README §7.4 e passos 3-4 do §7.5).

    * next_date: sempre a primeira ocorrencia > agora (None quando a regra terminou);
    * create_ticket: um ticket coalescendo as vencidas, exceto SKIP com a vencida mais recente atrasada
      acima da tolerancia (CR-008, R-21: o atraso e medido pela mais recente);
    * missed: vencidas que nao viraram ticket, limitada a MISSED_LIMIT;
    * complete: UNICA apos a decisao, ou sem proxima ocorrencia ate data_fim (sem ticket quando
      create_ticket e falso);
    * occurrence: a vencida mais recente, coberta pelo ticket (scheduled_at do ticket, CR-007 R-27);
    * cron_error: CRON sem proxima ocorrencia no horizonte (CR-008, R-19); next_date None, complete falso.
    Lanca CronError so se a expressao CRON for invalida.
    """
    if misfire_policy not in MISFIRE_POLICIES:
        raise ValueError('misfire_policy inválida: %r' % (misfire_policy,))
    now = without_microseconds(now)
    expected = rule.get('next_run_at')
    if expected is None or expected > now:
        return Decision(False, without_microseconds(expected), 0, False, None)

    if rule['recurrence_type'] == 'CRON':
        _expression(rule['cron_expression'])  # expressao invalida: CronError (pausa INVALID_CRON)
    due, last = _due(rule, expected, now, horizon_days)
    delay = (now - last).total_seconds()
    if delay > misfire_tolerance_s and misfire_policy == 'SKIP':
        generate, missed = False, due
    else:
        generate, missed = True, due - 1

    cron_error = False
    if rule['recurrence_type'] == 'ONCE':
        new_date = None
    else:
        try:
            new_date = next_run(rule, now, horizon_days)
        except CronError:
            new_date, cron_error = None, True
    return Decision(generate, new_date, min(missed, MISSED_LIMIT), new_date is None and not cron_error,
                   without_microseconds(last) if generate else None, cron_error)
