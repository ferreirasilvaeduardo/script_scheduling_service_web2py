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

import cron_parser
from cron_parser import CronError

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

    Devolve {campo: mensagem}; vazio quando a regra e valida.
    """
    erros = collections.OrderedDict()
    tipo = rule.get('recurrence_type')
    hora = rule.get('run_time')
    dsem = rule.get('week_days')
    dia = rule.get('month_day')
    cron = rule.get('cron_expression')
    inicio = rule.get('start_date')
    fim = rule.get('end_date')

    if tipo not in TYPES:
        erros['recurrence_type'] = 'Tipo de recorrência inválido.'
    if not isinstance(inicio, datetime.datetime):
        erros['start_date'] = 'Informe a data e hora de início.'
    if fim is not None:
        if not isinstance(fim, datetime.datetime):
            erros['end_date'] = 'Data de fim inválida.'
        elif isinstance(inicio, datetime.datetime) and fim < inicio:
            erros['end_date'] = 'A data de fim não pode ser anterior à de início.'
    if not _empty(hora) and not (isinstance(hora, str) and _RE_TIME.match(hora)):
        erros['run_time'] = 'Horário inválido; use HH:MM (00:00 a 23:59).'
    if not _empty(dsem) and not (isinstance(dsem, str) and _RE_WDAY.match(dsem)):
        erros['week_days'] = 'Dias da semana inválidos; use números de 1 (segunda) a 7 (domingo), ex.: 1,3,5.'
    if not _empty(dia):
        try:
            valido = 1 <= int(dia) <= 31 and str(dia).strip().isdigit()
        except (TypeError, ValueError):
            valido = False
        if not valido:
            erros['month_day'] = 'Dia do mês deve estar entre 1 e 31.'

    obrigatorios = {'DAILY': ('run_time',), 'WEEKLY': ('run_time', 'week_days'),
                    'MONTHLY': ('run_time', 'month_day'), 'CRON': ('cron_expression',)}
    for campo in obrigatorios.get(tipo, ()):
        if _empty(rule.get(campo)) and campo not in erros:
            erros[campo] = 'Campo obrigatório para recorrência %s.' % tipo

    if tipo == 'CRON' and not _empty(cron) and 'cron_expression' not in erros:
        try:
            expr = cron_parser.parse(cron)
            if isinstance(inicio, datetime.datetime):
                piso = truncate_seconds(inicio) - _ONE_MINUTE
                # Com data_fim dentro do horizonte, a falta de ocorrencia e "sem proxima execucao" (o servico
                # da a mensagem), e nao expressao invalida (README §7.3, CR-007 R-32).
                fim_no_horizonte = (isinstance(fim, datetime.datetime)
                                    and fim <= piso + datetime.timedelta(days=horizon_days))
                if expr.next(piso, horizon_days) is None and not fim_no_horizonte:
                    erros['cron_expression'] = ('A expressão não ocorre nos próximos %d dias a partir do início.'
                                               % horizon_days)
        except CronError as erro:
            erros['cron_expression'] = erro.message
    return erros


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
    candidato = datetime.datetime(ref.year, ref.month, ref.day, hh, mm)
    return candidato if candidato > ref else candidato + _ONE_DAY


def _weekly(ref, hour, weekdays):
    hh, mm = _hour_minute(hour)
    dias = set(int(d) for d in weekdays.split(','))
    base = datetime.datetime(ref.year, ref.month, ref.day, hh, mm)
    for desloc in range(8):
        candidato = base + datetime.timedelta(days=desloc)
        if candidato > ref and candidato.isoweekday() in dias:
            return candidato
    return None


def _monthly(ref, hour, month_day):
    hh, mm = _hour_minute(hour)
    dia = int(month_day)
    ano, mes = ref.year, ref.month
    for _ in range(2):
        ultimo = calendar.monthrange(ano, mes)[1]
        candidato = datetime.datetime(ano, mes, min(dia, ultimo), hh, mm)
        if candidato > ref:
            return candidato
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return None


def next_run(rule, after, horizon_days=DEFAULT_HORIZON):
    """Primeira ocorrencia > `apos`, respeitando o piso data_inicio e o teto data_fim; None se nao houver.

    Lanca CronError para expressao CRON invalida ou sem ocorrencia no horizonte (README §7.3).
    """
    tipo = rule['recurrence_type']
    piso = truncate_seconds(rule['start_date'])
    fim = rule.get('end_date')
    if tipo == 'ONCE':
        resultado = piso if piso > after else None
    else:
        # Ocorrencias tem precisao de minuto: ">= piso" equivale a "> piso - 1 minuto".
        ref = max(after, piso - _ONE_MINUTE)
        if tipo == 'DAILY':
            resultado = _daily(ref, rule['run_time'])
        elif tipo == 'WEEKLY':
            resultado = _weekly(ref, rule['run_time'], rule['week_days'])
        elif tipo == 'MONTHLY':
            resultado = _monthly(ref, rule['run_time'], rule['month_day'])
        elif tipo == 'CRON':
            resultado = _expression(rule['cron_expression']).next(ref, horizon_days)
            if resultado is None:
                if fim is not None and fim <= ref + datetime.timedelta(days=horizon_days):
                    return None
                raise CronError('A expressão não ocorre nos próximos %d dias.' % horizon_days)
        else:
            raise ValueError('tipo_recorrencia inválido: %r' % (tipo,))
    if resultado is not None and fim is not None and resultado > fim:
        return None
    return truncate_seconds(resultado)


def next_runs(rule, after, n, horizon_days=DEFAULT_HORIZON):
    """Ate `n` proximas ocorrencias depois de `apos` (previa da UI)."""
    lista = []
    atual = after
    while len(lista) < n:
        atual = next_run(rule, atual, horizon_days)
        if atual is None:
            break
        lista.append(atual)
    return lista


def _due(rule, start, now, horizon_days):
    """(quantidade, ultima) das ocorrencias em [inicio, agora], contando `inicio`; para em MISSED_LIMIT + 1."""
    total = 1
    ultima = start
    if rule['recurrence_type'] == 'ONCE':
        return total, ultima
    atual = start
    while total <= MISSED_LIMIT:
        try:
            atual = next_run(rule, atual, horizon_days)
        except CronError:
            break  # sem ocorrencia no horizonte depois de 'atual': nao ha mais vencidas (CR-008, R-19)
        if atual is None or atual > now:
            break
        total += 1
        ultima = atual
    if total > MISSED_LIMIT:
        # O limite da contagem nao pode limitar a ocorrencia coberta pelo ticket.
        teto = truncate_seconds(min(now, rule.get('end_date') or now))
        esquerda, direita = ultima, teto
        while esquerda < direita:
            minutos = int((direita - esquerda).total_seconds() // 60)
            meio = esquerda + datetime.timedelta(minutes=minutos // 2)
            try:
                seguinte = next_run(rule, meio, horizon_days)
            except CronError:
                seguinte = None
            if seguinte is not None and seguinte <= teto:
                ultima = seguinte
                esquerda = seguinte
            else:
                direita = meio
    return total, ultima


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
    prevista = rule.get('next_run_at')
    if prevista is None or prevista > now:
        return Decision(False, without_microseconds(prevista), 0, False, None)

    if rule['recurrence_type'] == 'CRON':
        _expression(rule['cron_expression'])  # expressao invalida: CronError (pausa INVALID_CRON)
    vencidas, ultima = _due(rule, prevista, now, horizon_days)
    atraso = (now - ultima).total_seconds()
    if atraso > misfire_tolerance_s and misfire_policy == 'SKIP':
        gerar, perdidas = False, vencidas
    else:
        gerar, perdidas = True, vencidas - 1

    cron_erro = False
    if rule['recurrence_type'] == 'ONCE':
        nova_data = None
    else:
        try:
            nova_data = next_run(rule, now, horizon_days)
        except CronError:
            nova_data, cron_erro = None, True
    return Decision(gerar, nova_data, min(perdidas, MISSED_LIMIT), nova_data is None and not cron_erro,
                   without_microseconds(ultima) if gerar else None, cron_erro)
