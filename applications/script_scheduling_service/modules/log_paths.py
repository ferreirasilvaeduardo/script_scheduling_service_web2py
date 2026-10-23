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


def script_dir(name, script_id=None):
    """Forma segura do nome do script para a pasta do log de execucao (CR-005, R-a).

    Sem acento (NFKD -> ASCII), minusculo, cada sequencia fora de [a-z0-9._-] vira '_',
    sem '.' ou '_' nas pontas. Vazio vira 'script_<id>' (ou 'script').
    """
    text = unicodedata.normalize('NFKD', name or u'')
    text = text.encode('ascii', 'ignore').decode('ascii').lower()
    text = _RE_OUTSIDE.sub('_', text).strip('._')
    if not text:
        return 'script_%s' % script_id if script_id is not None else 'script'
    return text


def environment_dir(name):
    """Pasta do ambiente no topo do caminho do log (CR-009): minusculo, sem acento, sem espaco e sem
    caractere especial (mesma regra da pasta do script). Ambiente vazio ou sem nenhum caractere
    aproveitavel: ValueError (nos logs de script o ambiente e obrigatorio). 'internal' e reservado."""
    text = unicodedata.normalize('NFKD', name or u'')
    text = text.encode('ascii', 'ignore').decode('ascii').lower()
    text = _RE_OUTSIDE.sub('_', text).strip('._')
    if not text:
        raise ValueError("Ambiente obrigatorio no caminho do log de execucao")
    if text == INTERNAL_DIR:
        raise ValueError("O ambiente nao pode gerar a pasta reservada '%s'" % INTERNAL_DIR)
    return text


def is_reserved_environment(name):
    """True se o nome do ambiente geraria a pasta reservada 'internal' (CR-009)."""
    try:
        environment_dir(name)
    except ValueError:
        return bool((name or "").strip())
    return False


def is_reserved_name(name):
    """True se o nome do script geraria a pasta reservada 'app' (CR-005, D7)."""
    return script_dir(name) == APP_DIR


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
#    log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log (CR-009)
# ---------------------------------------------------------------------------

def run_log_dir(log_dir, environment, script_name, started_at, script_id=None):
    """Diretorio do log de execucao do script conforme o ambiente do ticket e started_at (banco)."""
    env = environment_dir(environment)
    dir_value = script_dir(script_name, script_id)
    year, month, day, hour, minute = minute_parts(started_at)
    return os.path.join(log_dir, env, dir_value, year, month, day, hour, minute)


def output_dir(output_dir, environment, script_name, started_at, ticket_id, script_id=None):
    """Pasta de saida do ticket (CR-012, README §8.13), com as mesmas partes do log de execucao.

    Devolve (base, relativo): base = output_dir/<ambiente> (do usuario de execucao fora de DEV) e
    relativo = <pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>, o formato que o helper confere.
    """
    base = os.path.join(output_dir, environment_dir(environment))
    relative = "/".join((script_dir(script_name, script_id),) + minute_parts(started_at)
                        + ("ticket_%d" % int(ticket_id),))
    return base, relative


def input_dir(input_dir, environment, script_name, script_id=None):
    """Pasta de entrada do script (CR-014, README §8.14): permanente, uma por ambiente e script, sem data nem ticket.

    Devolve (base, relativo): base = input_dir/<ambiente> (do usuario de execucao fora de DEV) e relativo =
    <pasta do script>, com a mesma regra da pasta do log (minusculo, sem acento e sem espaco).
    """
    return os.path.join(input_dir, environment_dir(environment)), script_dir(script_name, script_id)


def ensure_directory(directory, warnings=None):
    """Cria diretorio nivel a nivel com 0o750 em cada pasta nova (README §8.4 passo 3 e §13).

    O makedirs so aplica o modo a pasta final, e sempre sob a umask 077 do launcher: cada nivel novo
    (pasta do script ou app/, ano, mes, dia, hora e minuto) recebe chmod 0o750. Falha de chmod vai para
    avisos (lista de pares (acao, mensagem)) quando informada; sem avisos, a excecao sobe.
    """
    missing = []
    current = os.path.abspath(directory)
    while not os.path.isdir(current):
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    for dir_value in reversed(missing):
        try:
            os.mkdir(dir_value, 0o750)
        except FileExistsError:
            continue
        try:
            os.chmod(dir_value, 0o750)
        except OSError as exc:
            if warnings is None:
                raise
            warnings.append(("LOG", "chmod 750 falhou em %s: %s" % (dir_value, exc)))
    return directory


def partial_log_name(ticket_id):
    """Nome do log aberto antes do spawn: ticket_<id>.log.parcial (CR-005, R-b)."""
    return 'ticket_%s.log.parcial' % ticket_id


def run_log_name(ticket_id, pid=None):
    """Nome final do log de execucao: ticket_<id>_<PID>.log ou ticket_<id>_0.log (CR-005, R-b)."""
    pid_val = pid if (pid is not None and pid > 0) else 0
    return 'ticket_%s_%s.log' % (ticket_id, pid_val)


def partial_log_path(log_dir, environment, script_name, started_at, ticket_id, script_id=None):
    """Caminho completo do arquivo parcial pre-spawn."""
    directory = run_log_dir(log_dir, environment, script_name, started_at, script_id)
    return os.path.join(directory, partial_log_name(ticket_id))


def run_log_path(log_dir, environment, script_name, started_at, ticket_id, pid=None, script_id=None):
    """Caminho completo do arquivo de log final de execucao."""
    directory = run_log_dir(log_dir, environment, script_name, started_at, script_id)
    return os.path.join(directory, run_log_name(ticket_id, pid))


# ---------------------------------------------------------------------------
# 2. Logs da aplicacao (CR-005 D6, R-c, R-d, R-e, README §13)
#    log_dir/internal/app/AAAA/MM/DD/HH/MI/<log_name>_<PID>[_<n>].log (CR-009: sem ambiente)
# ---------------------------------------------------------------------------

def app_log_dir(log_dir, dt):
    """Diretorio de log da aplicacao no minuto de dt (relogio local do processo)."""
    year, month, day, hour, minute = minute_parts(dt)
    return os.path.join(log_dir, INTERNAL_DIR, APP_DIR, year, month, day, hour, minute)


def app_log_name(process_name, pid, seq=None):
    """Nome do arquivo de log da aplicacao. Com seq > 1 ganha sufixo _<n> (CR-005, R-c)."""
    base = process_name[:-4] if process_name.endswith('.log') else process_name
    if seq is not None and seq > 1:
        return '%s_%s_%s.log' % (base, pid, seq)
    return '%s_%s.log' % (base, pid)


def app_log_path(log_dir, process_name, pid, dt, seq=None):
    """Caminho completo do arquivo de log da aplicacao no minuto dt."""
    directory = app_log_dir(log_dir, dt)
    return os.path.join(directory, app_log_name(process_name, pid, seq))


def next_app_log_path(log_dir, process_name, pid, dt):
    """Gera o proximo caminho disponivel para log da aplicacao, aplicando sufixo _<n> se colidir."""
    directory = app_log_dir(log_dir, dt)
    path = os.path.join(directory, app_log_name(process_name, pid))
    if not os.path.exists(path):
        return path
    seq = 2
    while True:
        candidate = os.path.join(directory, app_log_name(process_name, pid, seq))
        if not os.path.exists(candidate):
            return candidate
        seq += 1


# ---------------------------------------------------------------------------
# 3. Auxiliares de retencao e parsing de pastas de data (README §11.3, §13)
# ---------------------------------------------------------------------------

def parse_day_date(year_str, month_str, day_str):
    """Valida se ano/mes/dia sao numeros e representam uma data valida do calendario."""
    if not (_RE_YEAR.match(year_str) and _RE_TWO_DIGITS.match(month_str) and _RE_TWO_DIGITS.match(day_str)):
        return None
    try:
        return datetime.date(int(year_str), int(month_str), int(day_str))
    except (ValueError, OverflowError):
        return None


def parse_minute_date(year_str, month_str, day_str, hour_str, min_str):
    """Valida se ano/mes/dia/hora/minuto representam um instante valido do calendario."""
    if not (_RE_YEAR.match(year_str) and _RE_TWO_DIGITS.match(month_str) and _RE_TWO_DIGITS.match(day_str)
            and _RE_TWO_DIGITS.match(hour_str) and _RE_TWO_DIGITS.match(min_str)):
        return None
    try:
        return datetime.datetime(int(year_str), int(month_str), int(day_str), int(hour_str), int(min_str))
    except (ValueError, OverflowError):
        return None


def clean_app_retention(log_dir, retention_days, ref_dt=None, failures=None):
    """Apaga as pastas log_dir/internal/app/AAAA/MM/DD anteriores a retention_days dias (CR-005, R-d, README §13).

    So remove pastas cujo caminho casa perfeitamente com ano/mes/dia valido do calendario.
    Apos remover os dias antigos, remove pastas de mes e ano que ficarem vazias.
    Retorna a lista dos caminhos de dia removidos. Cada falha de leitura ou remocao segue para a
    proxima pasta e, se `falhas` for uma lista, entra nela como texto (caminho e erro) para o log.
    """
    def _falhou(path, exc):
        if failures is not None:
            failures.append("%s: %s" % (path, exc))

    if retention_days is None or retention_days <= 0:
        return []
    dir_app = os.path.join(log_dir, INTERNAL_DIR, APP_DIR)
    if not os.path.isdir(dir_app):
        return []

    if ref_dt is None:
        ref_dt = datetime.datetime.now()
    if callable(getattr(ref_dt, "date", None)):
        ref_date = ref_dt.date()
    else:
        ref_date = ref_dt
    limit = ref_date - datetime.timedelta(days=retention_days)

    removed = []
    try:
        years = os.listdir(dir_app)
    except OSError as exc:
        _falhou(dir_app, exc)
        return []

    for year_str in sorted(years):
        path_year = os.path.join(dir_app, year_str)
        if not os.path.isdir(path_year):
            continue
        try:
            months = os.listdir(path_year)
        except OSError as exc:
            _falhou(path_year, exc)
            continue

        for month_str in sorted(months):
            path_month = os.path.join(path_year, month_str)
            if not os.path.isdir(path_month):
                continue
            try:
                days = os.listdir(path_month)
            except OSError as exc:
                _falhou(path_month, exc)
                continue

            for day_str in sorted(days):
                path_day = os.path.join(path_month, day_str)
                if not os.path.isdir(path_day):
                    continue
                date_day = parse_day_date(year_str, month_str, day_str)
                if date_day is None:
                    continue
                if date_day < limit:
                    try:
                        shutil.rmtree(path_day)
                        removed.append(path_day)
                    except OSError as exc:
                        _falhou(path_day, exc)

            try:
                if os.path.isdir(path_month) and not os.listdir(path_month):
                    os.rmdir(path_month)
            except OSError as exc:
                _falhou(path_month, exc)

        try:
            if os.path.isdir(path_year) and not os.listdir(path_year):
                os.rmdir(path_year)
        except OSError as exc:
            _falhou(path_year, exc)

    return removed



# ---------------------------------------------------------------------------
# 3. Retencao dos logs de execucao (purge.py, README §11.3; CR-005; CR-007 R-32; CR-009)
#    log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI, nunca log_dir/internal/
# ---------------------------------------------------------------------------

def _subdirs(folder, failures):
    try:
        names = sorted(os.listdir(folder))
    except OSError as exc:
        failures.append("%s: %s" % (folder, exc))
        return []
    return [(n, os.path.join(folder, n)) for n in names
            if os.path.isdir(os.path.join(folder, n)) and not os.path.islink(os.path.join(folder, n))]


def run_minutes(log_dir, failures=None):
    """[(caminho, datetime)] das pastas de minuto com o formato exato <ambiente>/<script>/AAAA/MM/DD/HH/MI.

    O resto e ignorado; links nao sao seguidos; a pasta internal/ (logs da aplicacao) nunca entra.
    """
    failures = failures if failures is not None else []
    found = []
    for env, p_env in _subdirs(log_dir, failures):
        if env == INTERNAL_DIR:
            continue
        for _scr, p_scr in _subdirs(p_env, failures):
            for a, p_a in _subdirs(p_scr, failures):
                for m, p_m in _subdirs(p_a, failures):
                    for d, p_d in _subdirs(p_m, failures):
                        for h, p_h in _subdirs(p_d, failures):
                            for mi, p_mi in _subdirs(p_h, failures):
                                instant = parse_minute_date(a, m, d, h, mi)
                                if instant is not None:
                                    found.append((p_mi, instant))
    return found


def clean_run_retention(log_dir, retention_days, ref_date, keep=(), dry_run=False, failures=None,
                             final_path=os.path.realpath):
    """Pastas de minuto anteriores a ref_date - retention_days (data tirada do caminho, nao do mtime), menos as de
    `manter` (log de ticket RUNNING); depois as pastas de hora, dia, mes, ano, script e ambiente vazias.

    Cada pasta e conferida sob log_dir pelo caminho real (final_path + commonpath). dry_run so lista.
    Devolve a lista das pastas de minuto removidas (ou elegiveis, no dry_run).
    """
    failures = failures if failures is not None else []
    if retention_days is None or retention_days <= 0 or not os.path.isdir(log_dir):
        return []
    limit = ref_date - datetime.timedelta(days=retention_days)
    if isinstance(limit, datetime.datetime):  # agora_banco() do purge: compara so a data do caminho
        limit = limit.date()
    root = final_path(log_dir)
    keep = set(os.path.normpath(p) for p in keep)
    removed = []
    for path, instant in run_minutes(log_dir, failures):
        if instant.date() >= limit or os.path.normpath(path) in keep:
            continue
        real = final_path(path)
        if os.path.commonpath([real, root]) != root or real == root:
            failures.append("%s: fora de log_dir" % path)
            continue
        if dry_run:
            removed.append(path)
            continue
        try:
            shutil.rmtree(path)
            removed.append(path)
        except OSError as exc:
            failures.append("%s: %s" % (path, exc))
            continue
        dir_value = os.path.dirname(path)
        for _level in range(6):  # hora, dia, mes, ano, script e ambiente
            try:
                if os.path.normpath(dir_value) == os.path.normpath(log_dir) or os.listdir(dir_value):
                    break
                os.rmdir(dir_value)
            except OSError as exc:
                failures.append("%s: %s" % (dir_value, exc))
                break
            dir_value = os.path.dirname(dir_value)
    return removed
