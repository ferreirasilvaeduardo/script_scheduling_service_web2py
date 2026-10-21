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
* CRON sem ocorrencia no horizonte lanca CronErro (o daemon pausa com INVALID_CRON), exceto
  quando data_fim cai dentro do horizonte: ai a regra apenas terminou (None).
"""
import calendar
import collections
import datetime
import re

import cron_parser
from cron_parser import CronErro

TIPOS = ('ONCE', 'DAILY', 'WEEKLY', 'MONTHLY', 'CRON')
POLITICAS_MISFIRE = ('RUN_ONCE', 'SKIP')
LIMITE_PERDIDAS = 10000
HORIZONTE_PADRAO = cron_parser.HORIZONTE_PADRAO

_RE_TIME = re.compile(r'^([01][0-9]|2[0-3]):[0-5][0-9]$')
_RE_WDAY = re.compile(r'^[1-7](,[1-7]){0,6}$')
_UM_MINUTO = datetime.timedelta(minutes=1)
_UM_DIA = datetime.timedelta(days=1)
_CACHE_CRON = {}
_CACHE_MAXIMO = 256

# ocorrencia (CR-007, R-27): a vencida mais recente coberta pelo ticket; None quando nao ha ticket.
# cron_erro (CR-008, R-19): a proxima ocorrencia nao existe no horizonte; nova_data fica None e o daemon
# aplica sobreposicao e SKIP normalmente antes de pausar a regra com INVALID_CRON.
Decisao = collections.namedtuple('Decisao', ['gerar_ticket', 'nova_data', 'perdidas', 'concluir', 'ocorrencia',
                                             'cron_erro'])
Decisao.__new__.__defaults__ = (None, False)


def truncar_segundos(dt):
    """Zera segundos e microssegundos (None passa direto)."""
    if dt is None:
        return None
    return dt.replace(second=0, microsecond=0)


def sem_microssegundos(dt):
    """Zera microssegundos: nenhum datetime com microssegundos e comparado a coluna DATE (README §7.5)."""
    if dt is None:
        return None
    return dt.replace(microsecond=0)


def _vazio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def validar_regra(regra, horizonte_dias=HORIZONTE_PADRAO):
    """Espelha as CKs de tbsss_schedules (_trec, _campos, _hora, _dsem, _dia, _fim) e valida o CRON.

    Devolve {campo: mensagem}; vazio quando a regra e valida.
    """
    erros = collections.OrderedDict()
    tipo = regra.get('recurrence_type')
    hora = regra.get('run_time')
    dsem = regra.get('week_days')
    dia = regra.get('month_day')
    cron = regra.get('cron_expression')
    inicio = regra.get('start_date')
    fim = regra.get('end_date')

    if tipo not in TIPOS:
        erros['recurrence_type'] = 'Tipo de recorrência inválido.'
    if not isinstance(inicio, datetime.datetime):
        erros['start_date'] = 'Informe a data e hora de início.'
    if fim is not None:
        if not isinstance(fim, datetime.datetime):
            erros['end_date'] = 'Data de fim inválida.'
        elif isinstance(inicio, datetime.datetime) and fim < inicio:
            erros['end_date'] = 'A data de fim não pode ser anterior à de início.'
    if not _vazio(hora) and not (isinstance(hora, str) and _RE_TIME.match(hora)):
        erros['run_time'] = 'Horário inválido; use HH:MM (00:00 a 23:59).'
    if not _vazio(dsem) and not (isinstance(dsem, str) and _RE_WDAY.match(dsem)):
        erros['week_days'] = 'Dias da semana inválidos; use números de 1 (segunda) a 7 (domingo), ex.: 1,3,5.'
    if not _vazio(dia):
        try:
            valido = 1 <= int(dia) <= 31 and str(dia).strip().isdigit()
        except (TypeError, ValueError):
            valido = False
        if not valido:
            erros['month_day'] = 'Dia do mês deve estar entre 1 e 31.'

    obrigatorios = {'DAILY': ('run_time',), 'WEEKLY': ('run_time', 'week_days'),
                    'MONTHLY': ('run_time', 'month_day'), 'CRON': ('cron_expression',)}
    for campo in obrigatorios.get(tipo, ()):
        if _vazio(regra.get(campo)) and campo not in erros:
            erros[campo] = 'Campo obrigatório para recorrência %s.' % tipo

    if tipo == 'CRON' and not _vazio(cron) and 'cron_expression' not in erros:
        try:
            expr = cron_parser.parse(cron)
            if isinstance(inicio, datetime.datetime):
                piso = truncar_segundos(inicio) - _UM_MINUTO
                # Com data_fim dentro do horizonte, a falta de ocorrencia e "sem proxima execucao" (o servico
                # da a mensagem), e nao expressao invalida (README §7.3, CR-007 R-32).
                fim_no_horizonte = (isinstance(fim, datetime.datetime)
                                    and fim <= piso + datetime.timedelta(days=horizonte_dias))
                if expr.proxima(piso, horizonte_dias) is None and not fim_no_horizonte:
                    erros['cron_expression'] = ('A expressão não ocorre nos próximos %d dias a partir do início.'
                                               % horizonte_dias)
        except CronErro as erro:
            erros['cron_expression'] = erro.mensagem
    return erros


def _expressao(texto):
    """parse() com cache pequeno: o calculo de vencidas chama proxima_execucao em laco."""
    expr = _CACHE_CRON.get(texto)
    if expr is None:
        expr = cron_parser.parse(texto)
        if len(_CACHE_CRON) >= _CACHE_MAXIMO:
            _CACHE_CRON.clear()
        _CACHE_CRON[texto] = expr
    return expr


def _hora_minuto(hora):
    hh, mm = hora.split(':')
    return int(hh), int(mm)


def _diaria(ref, hora):
    hh, mm = _hora_minuto(hora)
    candidato = datetime.datetime(ref.year, ref.month, ref.day, hh, mm)
    return candidato if candidato > ref else candidato + _UM_DIA


def _semanal(ref, hora, dias_semana):
    hh, mm = _hora_minuto(hora)
    dias = set(int(d) for d in dias_semana.split(','))
    base = datetime.datetime(ref.year, ref.month, ref.day, hh, mm)
    for desloc in range(8):
        candidato = base + datetime.timedelta(days=desloc)
        if candidato > ref and candidato.isoweekday() in dias:
            return candidato
    return None


def _mensal(ref, hora, dia_mes):
    hh, mm = _hora_minuto(hora)
    dia = int(dia_mes)
    ano, mes = ref.year, ref.month
    for _ in range(2):
        ultimo = calendar.monthrange(ano, mes)[1]
        candidato = datetime.datetime(ano, mes, min(dia, ultimo), hh, mm)
        if candidato > ref:
            return candidato
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return None


def proxima_execucao(regra, apos, horizonte_dias=HORIZONTE_PADRAO):
    """Primeira ocorrencia > `apos`, respeitando o piso data_inicio e o teto data_fim; None se nao houver.

    Lanca CronErro para expressao CRON invalida ou sem ocorrencia no horizonte (README §7.3).
    """
    tipo = regra['recurrence_type']
    piso = truncar_segundos(regra['start_date'])
    fim = regra.get('end_date')
    if tipo == 'ONCE':
        resultado = piso if piso > apos else None
    else:
        # Ocorrencias tem precisao de minuto: ">= piso" equivale a "> piso - 1 minuto".
        ref = max(apos, piso - _UM_MINUTO)
        if tipo == 'DAILY':
            resultado = _diaria(ref, regra['run_time'])
        elif tipo == 'WEEKLY':
            resultado = _semanal(ref, regra['run_time'], regra['week_days'])
        elif tipo == 'MONTHLY':
            resultado = _mensal(ref, regra['run_time'], regra['month_day'])
        elif tipo == 'CRON':
            resultado = _expressao(regra['cron_expression']).proxima(ref, horizonte_dias)
            if resultado is None:
                if fim is not None and fim <= ref + datetime.timedelta(days=horizonte_dias):
                    return None
                raise CronErro('A expressão não ocorre nos próximos %d dias.' % horizonte_dias)
        else:
            raise ValueError('tipo_recorrencia inválido: %r' % (tipo,))
    if resultado is not None and fim is not None and resultado > fim:
        return None
    return truncar_segundos(resultado)


def proximas(regra, apos, n, horizonte_dias=HORIZONTE_PADRAO):
    """Ate `n` proximas ocorrencias depois de `apos` (previa da UI)."""
    lista = []
    atual = apos
    while len(lista) < n:
        atual = proxima_execucao(regra, atual, horizonte_dias)
        if atual is None:
            break
        lista.append(atual)
    return lista


def _vencidas(regra, inicio, agora, horizonte_dias):
    """(quantidade, ultima) das ocorrencias em [inicio, agora], contando `inicio`; para em LIMITE_PERDIDAS + 1."""
    total = 1
    ultima = inicio
    if regra['recurrence_type'] == 'ONCE':
        return total, ultima
    atual = inicio
    while total <= LIMITE_PERDIDAS:
        try:
            atual = proxima_execucao(regra, atual, horizonte_dias)
        except CronErro:
            break  # sem ocorrencia no horizonte depois de 'atual': nao ha mais vencidas (CR-008, R-19)
        if atual is None or atual > agora:
            break
        total += 1
        ultima = atual
    if total > LIMITE_PERDIDAS:
        # O limite da contagem nao pode limitar a ocorrencia coberta pelo ticket.
        teto = truncar_segundos(min(agora, regra.get('end_date') or agora))
        esquerda, direita = ultima, teto
        while esquerda < direita:
            minutos = int((direita - esquerda).total_seconds() // 60)
            meio = esquerda + datetime.timedelta(minutes=minutos // 2)
            try:
                seguinte = proxima_execucao(regra, meio, horizonte_dias)
            except CronErro:
                seguinte = None
            if seguinte is not None and seguinte <= teto:
                ultima = seguinte
                esquerda = seguinte
            else:
                direita = meio
    return total, ultima


def avaliar_disparo(regra, agora, misfire_policy, misfire_tolerance_s, horizonte_dias=HORIZONTE_PADRAO):
    """Decide o disparo de uma regra vencida (README §7.4 e passos 3-4 do §7.5).

    * nova_data: sempre a primeira ocorrencia > agora (None quando a regra terminou);
    * gerar_ticket: um ticket coalescendo as vencidas, exceto SKIP com a vencida mais recente atrasada
      acima da tolerancia (CR-008, R-21: o atraso e medido pela mais recente);
    * perdidas: vencidas que nao viraram ticket, limitada a LIMITE_PERDIDAS;
    * concluir: UNICA apos a decisao, ou sem proxima ocorrencia ate data_fim (sem ticket quando
      gerar_ticket e falso);
    * ocorrencia: a vencida mais recente, coberta pelo ticket (scheduled_at do ticket, CR-007 R-27);
    * cron_erro: CRON sem proxima ocorrencia no horizonte (CR-008, R-19); nova_data None, concluir falso.
    Lanca CronErro so se a expressao CRON for invalida.
    """
    if misfire_policy not in POLITICAS_MISFIRE:
        raise ValueError('misfire_policy inválida: %r' % (misfire_policy,))
    agora = sem_microssegundos(agora)
    prevista = regra.get('next_run_at')
    if prevista is None or prevista > agora:
        return Decisao(False, sem_microssegundos(prevista), 0, False, None)

    if regra['recurrence_type'] == 'CRON':
        _expressao(regra['cron_expression'])  # expressao invalida: CronErro (pausa INVALID_CRON)
    vencidas, ultima = _vencidas(regra, prevista, agora, horizonte_dias)
    atraso = (agora - ultima).total_seconds()
    if atraso > misfire_tolerance_s and misfire_policy == 'SKIP':
        gerar, perdidas = False, vencidas
    else:
        gerar, perdidas = True, vencidas - 1

    cron_erro = False
    if regra['recurrence_type'] == 'ONCE':
        nova_data = None
    else:
        try:
            nova_data = proxima_execucao(regra, agora, horizonte_dias)
        except CronErro:
            nova_data, cron_erro = None, True
    return Decisao(gerar, nova_data, min(perdidas, LIMITE_PERDIDAS), nova_data is None and not cron_erro,
                   sem_microssegundos(ultima) if gerar else None, cron_erro)
