# -*- coding: utf-8 -*-
"""Pastas e caminhos dos logs (README §8.4, §11.3, §13, CR-005 D5/D6/D7, R-a a R-e; CR-009).

Todo log fica sob uma pasta de ambiente no topo de log_dir (CR-009): a do ambiente do ticket, obrigatoria
nos logs de execucao dos scripts, ou 'internal' quando nao ha ambiente (logs da aplicacao).

Modulo puro: nao importa gluon (AGENTS §7.1). E o unico lugar que monta caminho de log (AGENTS §6).
"""
import datetime
import os
import re
import shutil
import unicodedata

# Pasta dos logs da aplicacao; nenhum script pode ter essa pasta de log (CR-005, D7).
APP_DIR = 'app'
# Pasta de ambiente dos logs sem ambiente (CR-009); nenhum ambiente pode se chamar INTERNAL.
INTERNAL_DIR = 'internal'
_RE_OUTSIDE = re.compile(r'[^a-z0-9._-]+')

_RE_YEAR = re.compile(r'^\d{4}$')
_RE_TWO_DIGITS = re.compile(r'^\d{2}$')


def script_dir(nome, script_id=None):
    """Forma segura do nome do script para a pasta do log de execucao (CR-005, R-a).

    Sem acento (NFKD -> ASCII), minusculo, cada sequencia fora de [a-z0-9._-] vira '_',
    sem '.' ou '_' nas pontas. Vazio vira 'script_<id>' (ou 'script').
    """
    texto = unicodedata.normalize('NFKD', nome or u'')
    texto = texto.encode('ascii', 'ignore').decode('ascii').lower()
    texto = _RE_OUTSIDE.sub('_', texto).strip('._')
    if not texto:
        return 'script_%s' % script_id if script_id is not None else 'script'
    return texto


def environment_dir(nome):
    """Pasta do ambiente no topo do caminho do log (CR-009): minusculo, sem acento, sem espaco e sem
    caractere especial (mesma regra da pasta do script). Ambiente vazio ou sem nenhum caractere
    aproveitavel: ValueError (nos logs de script o ambiente e obrigatorio). 'internal' e reservado."""
    texto = unicodedata.normalize('NFKD', nome or u'')
    texto = texto.encode('ascii', 'ignore').decode('ascii').lower()
    texto = _RE_OUTSIDE.sub('_', texto).strip('._')
    if not texto:
        raise ValueError("Ambiente obrigatorio no caminho do log de execucao")
    if texto == INTERNAL_DIR:
        raise ValueError("O ambiente nao pode gerar a pasta reservada '%s'" % INTERNAL_DIR)
    return texto


def is_reserved_environment(nome):
    """True se o nome do ambiente geraria a pasta reservada 'internal' (CR-009)."""
    try:
        environment_dir(nome)
    except ValueError:
        return bool((nome or "").strip())
    return False


def is_reserved_name(nome):
    """True se o nome do script geraria a pasta reservada 'app' (CR-005, D7)."""
    return script_dir(nome) == APP_DIR


def minute_parts(dt):
    """Devolve tupla de strings (AAAA, MM, DD, HH, MI) com zeros a esquerda."""
    return (
        '%04d' % dt.year,
        '%02d' % dt.month,
        '%02d' % dt.day,
        '%02d' % dt.hour,
        '%02d' % dt.minute,
    )


# ---------------------------------------------------------------------------
# 1. Logs de execucao de cada ticket (CR-005 D5, R-a, R-b, README §8.4)
#    log_dir/<ambiente>/<pasta_do_script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log (CR-009)
# ---------------------------------------------------------------------------

def run_log_dir(log_dir, ambiente, nome_script, started_at, script_id=None):
    """Diretorio do log de execucao do script conforme o ambiente do ticket e started_at (banco)."""
    amb = environment_dir(ambiente)
    pasta = script_dir(nome_script, script_id)
    ano, mes, dia, hora, minuto = minute_parts(started_at)
    return os.path.join(log_dir, amb, pasta, ano, mes, dia, hora, minuto)


def output_dir(output_dir, ambiente, nome_script, started_at, ticket_id, script_id=None):
    """Pasta de saida do ticket (CR-012, README §8.13), com as mesmas partes do log de execucao.

    Devolve (base, relativo): base = output_dir/<ambiente> (do usuario de execucao fora de DEV) e
    relativo = <pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>, o formato que o helper confere.
    """
    base = os.path.join(output_dir, environment_dir(ambiente))
    relativo = "/".join((script_dir(nome_script, script_id),) + minute_parts(started_at)
                        + ("ticket_%d" % int(ticket_id),))
    return base, relativo


def input_dir(input_dir, ambiente, nome_script, script_id=None):
    """Pasta de entrada do script (CR-014, README §8.14): permanente, uma por ambiente e script, sem data nem ticket.

    Devolve (base, relativo): base = input_dir/<ambiente> (do usuario de execucao fora de DEV) e relativo =
    <pasta do script>, com a mesma regra da pasta do log (minusculo, sem acento e sem espaco).
    """
    return os.path.join(input_dir, environment_dir(ambiente)), script_dir(nome_script, script_id)


def ensure_directory(diretorio, avisos=None):
    """Cria diretorio nivel a nivel com 0o750 em cada pasta nova (README §8.4 passo 3 e §13).

    O makedirs so aplica o modo a pasta final, e sempre sob a umask 077 do launcher: cada nivel novo
    (pasta do script ou app/, ano, mes, dia, hora e minuto) recebe chmod 0o750. Falha de chmod vai para
    avisos (lista de pares (acao, mensagem)) quando informada; sem avisos, a excecao sobe.
    """
    faltando = []
    atual = os.path.abspath(diretorio)
    while not os.path.isdir(atual):
        faltando.append(atual)
        pai = os.path.dirname(atual)
        if pai == atual:
            break
        atual = pai
    for pasta in reversed(faltando):
        try:
            os.mkdir(pasta, 0o750)
        except FileExistsError:
            continue
        try:
            os.chmod(pasta, 0o750)
        except OSError as exc:
            if avisos is None:
                raise
            avisos.append(("LOG", "chmod 750 falhou em %s: %s" % (pasta, exc)))
    return diretorio


def partial_log_name(ticket_id):
    """Nome do log aberto antes do spawn: ticket_<id>.log.parcial (CR-005, R-b)."""
    return 'ticket_%s.log.parcial' % ticket_id


def run_log_name(ticket_id, pid=None):
    """Nome final do log de execucao: ticket_<id>_<PID>.log ou ticket_<id>_0.log (CR-005, R-b)."""
    pid_val = pid if (pid is not None and pid > 0) else 0
    return 'ticket_%s_%s.log' % (ticket_id, pid_val)


def partial_log_path(log_dir, ambiente, nome_script, started_at, ticket_id, script_id=None):
    """Caminho completo do arquivo parcial pre-spawn."""
    diretorio = run_log_dir(log_dir, ambiente, nome_script, started_at, script_id)
    return os.path.join(diretorio, partial_log_name(ticket_id))


def run_log_path(log_dir, ambiente, nome_script, started_at, ticket_id, pid=None, script_id=None):
    """Caminho completo do arquivo de log final de execucao."""
    diretorio = run_log_dir(log_dir, ambiente, nome_script, started_at, script_id)
    return os.path.join(diretorio, run_log_name(ticket_id, pid))


# ---------------------------------------------------------------------------
# 2. Logs da aplicacao (CR-005 D6, R-c, R-d, R-e, README §13)
#    log_dir/internal/app/AAAA/MM/DD/HH/MI/<nome_log>_<PID>[_<n>].log (CR-009: sem ambiente)
# ---------------------------------------------------------------------------

def app_log_dir(log_dir, dt):
    """Diretorio de log da aplicacao no minuto de dt (relogio local do processo)."""
    ano, mes, dia, hora, minuto = minute_parts(dt)
    return os.path.join(log_dir, INTERNAL_DIR, APP_DIR, ano, mes, dia, hora, minuto)


def app_log_name(nome_processo, pid, seq=None):
    """Nome do arquivo de log da aplicacao. Com seq > 1 ganha sufixo _<n> (CR-005, R-c)."""
    base = nome_processo[:-4] if nome_processo.endswith('.log') else nome_processo
    if seq is not None and seq > 1:
        return '%s_%s_%s.log' % (base, pid, seq)
    return '%s_%s.log' % (base, pid)


def app_log_path(log_dir, nome_processo, pid, dt, seq=None):
    """Caminho completo do arquivo de log da aplicacao no minuto dt."""
    diretorio = app_log_dir(log_dir, dt)
    return os.path.join(diretorio, app_log_name(nome_processo, pid, seq))


def next_app_log_path(log_dir, nome_processo, pid, dt):
    """Gera o proximo caminho disponivel para log da aplicacao, aplicando sufixo _<n> se colidir."""
    diretorio = app_log_dir(log_dir, dt)
    caminho = os.path.join(diretorio, app_log_name(nome_processo, pid))
    if not os.path.exists(caminho):
        return caminho
    seq = 2
    while True:
        candidato = os.path.join(diretorio, app_log_name(nome_processo, pid, seq))
        if not os.path.exists(candidato):
            return candidato
        seq += 1


# ---------------------------------------------------------------------------
# 3. Auxiliares de retencao e parsing de pastas de data (README §11.3, §13)
# ---------------------------------------------------------------------------

def parse_day_date(ano_str, mes_str, dia_str):
    """Valida se ano/mes/dia sao numeros e representam uma data valida do calendario."""
    if not (_RE_YEAR.match(ano_str) and _RE_TWO_DIGITS.match(mes_str) and _RE_TWO_DIGITS.match(dia_str)):
        return None
    try:
        return datetime.date(int(ano_str), int(mes_str), int(dia_str))
    except (ValueError, OverflowError):
        return None


def parse_minute_date(ano_str, mes_str, dia_str, hora_str, min_str):
    """Valida se ano/mes/dia/hora/minuto representam um instante valido do calendario."""
    if not (_RE_YEAR.match(ano_str) and _RE_TWO_DIGITS.match(mes_str) and _RE_TWO_DIGITS.match(dia_str)
            and _RE_TWO_DIGITS.match(hora_str) and _RE_TWO_DIGITS.match(min_str)):
        return None
    try:
        return datetime.datetime(int(ano_str), int(mes_str), int(dia_str), int(hora_str), int(min_str))
    except (ValueError, OverflowError):
        return None


def clean_app_retention(log_dir, retention_days, ref_dt=None, falhas=None):
    """Apaga as pastas log_dir/internal/app/AAAA/MM/DD anteriores a retention_days dias (CR-005, R-d, README §13).

    So remove pastas cujo caminho casa perfeitamente com ano/mes/dia valido do calendario.
    Apos remover os dias antigos, remove pastas de mes e ano que ficarem vazias.
    Retorna a lista dos caminhos de dia removidos. Cada falha de leitura ou remocao segue para a
    proxima pasta e, se `falhas` for uma lista, entra nela como texto (caminho e erro) para o log.
    """
    def _falhou(caminho, exc):
        if falhas is not None:
            falhas.append("%s: %s" % (caminho, exc))

    if retention_days is None or retention_days <= 0:
        return []
    pasta_app = os.path.join(log_dir, INTERNAL_DIR, APP_DIR)
    if not os.path.isdir(pasta_app):
        return []

    if ref_dt is None:
        ref_dt = datetime.datetime.now()
    if callable(getattr(ref_dt, "date", None)):
        ref_date = ref_dt.date()
    else:
        ref_date = ref_dt
    limite = ref_date - datetime.timedelta(days=retention_days)

    removidos = []
    try:
        anos = os.listdir(pasta_app)
    except OSError as exc:
        _falhou(pasta_app, exc)
        return []

    for ano_str in sorted(anos):
        caminho_ano = os.path.join(pasta_app, ano_str)
        if not os.path.isdir(caminho_ano):
            continue
        try:
            meses = os.listdir(caminho_ano)
        except OSError as exc:
            _falhou(caminho_ano, exc)
            continue

        for mes_str in sorted(meses):
            caminho_mes = os.path.join(caminho_ano, mes_str)
            if not os.path.isdir(caminho_mes):
                continue
            try:
                dias = os.listdir(caminho_mes)
            except OSError as exc:
                _falhou(caminho_mes, exc)
                continue

            for dia_str in sorted(dias):
                caminho_dia = os.path.join(caminho_mes, dia_str)
                if not os.path.isdir(caminho_dia):
                    continue
                data_dia = parse_day_date(ano_str, mes_str, dia_str)
                if data_dia is None:
                    continue
                if data_dia < limite:
                    try:
                        shutil.rmtree(caminho_dia)
                        removidos.append(caminho_dia)
                    except OSError as exc:
                        _falhou(caminho_dia, exc)

            try:
                if os.path.isdir(caminho_mes) and not os.listdir(caminho_mes):
                    os.rmdir(caminho_mes)
            except OSError as exc:
                _falhou(caminho_mes, exc)

        try:
            if os.path.isdir(caminho_ano) and not os.listdir(caminho_ano):
                os.rmdir(caminho_ano)
        except OSError as exc:
            _falhou(caminho_ano, exc)

    return removidos



# ---------------------------------------------------------------------------
# 3. Retencao dos logs de execucao (purge.py, README §11.3; CR-005; CR-007 R-32; CR-009)
#    log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI, nunca log_dir/internal/
# ---------------------------------------------------------------------------

def _subdirs(pasta, falhas):
    try:
        nomes = sorted(os.listdir(pasta))
    except OSError as exc:
        falhas.append("%s: %s" % (pasta, exc))
        return []
    return [(n, os.path.join(pasta, n)) for n in nomes
            if os.path.isdir(os.path.join(pasta, n)) and not os.path.islink(os.path.join(pasta, n))]


def run_minutes(log_dir, falhas=None):
    """[(caminho, datetime)] das pastas de minuto com o formato exato <ambiente>/<script>/AAAA/MM/DD/HH/MI.

    O resto e ignorado; links nao sao seguidos; a pasta internal/ (logs da aplicacao) nunca entra.
    """
    falhas = falhas if falhas is not None else []
    achados = []
    for amb, p_amb in _subdirs(log_dir, falhas):
        if amb == INTERNAL_DIR:
            continue
        for _scr, p_scr in _subdirs(p_amb, falhas):
            for a, p_a in _subdirs(p_scr, falhas):
                for m, p_m in _subdirs(p_a, falhas):
                    for d, p_d in _subdirs(p_m, falhas):
                        for h, p_h in _subdirs(p_d, falhas):
                            for mi, p_mi in _subdirs(p_h, falhas):
                                instante = parse_minute_date(a, m, d, h, mi)
                                if instante is not None:
                                    achados.append((p_mi, instante))
    return achados


def clean_run_retention(log_dir, retention_days, ref_date, manter=(), dry_run=False, falhas=None,
                             caminho_final=os.path.realpath):
    """Pastas de minuto anteriores a ref_date - retention_days (data tirada do caminho, nao do mtime), menos as de
    `manter` (log de ticket RUNNING); depois as pastas de hora, dia, mes, ano, script e ambiente vazias.

    Cada pasta e conferida sob log_dir pelo caminho real (final_path + commonpath). dry_run so lista.
    Devolve a lista das pastas de minuto removidas (ou elegiveis, no dry_run).
    """
    falhas = falhas if falhas is not None else []
    if retention_days is None or retention_days <= 0 or not os.path.isdir(log_dir):
        return []
    limite = ref_date - datetime.timedelta(days=retention_days)
    if isinstance(limite, datetime.datetime):  # agora_banco() do purge: compara so a data do caminho
        limite = limite.date()
    raiz = caminho_final(log_dir)
    manter = set(os.path.normpath(p) for p in manter)
    removidas = []
    for caminho, instante in run_minutes(log_dir, falhas):
        if instante.date() >= limite or os.path.normpath(caminho) in manter:
            continue
        real = caminho_final(caminho)
        if os.path.commonpath([real, raiz]) != raiz or real == raiz:
            falhas.append("%s: fora de log_dir" % caminho)
            continue
        if dry_run:
            removidas.append(caminho)
            continue
        try:
            shutil.rmtree(caminho)
            removidas.append(caminho)
        except OSError as exc:
            falhas.append("%s: %s" % (caminho, exc))
            continue
        pasta = os.path.dirname(caminho)
        for _nivel in range(6):  # hora, dia, mes, ano, script e ambiente
            try:
                if os.path.normpath(pasta) == os.path.normpath(log_dir) or os.listdir(pasta):
                    break
                os.rmdir(pasta)
            except OSError as exc:
                falhas.append("%s: %s" % (pasta, exc))
                break
            pasta = os.path.dirname(pasta)
    return removidas
