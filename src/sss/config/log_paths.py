# -*- coding: utf-8 -*-
"""Pastas e caminhos dos logs (README §8.4, §11.3, §13, CR-005 D5/D6/D7, R-a a R-e; CR-009).

Todo log fica sob uma pasta de ambiente no topo de log_dir (CR-009): a do ambiente do ticket, obrigatoria
nos logs de execucao dos scripts, ou 'internal' quando nao ha ambiente (logs da aplicacao).

Modulo puro: nao importa gluon (AGENTS §7.1). E o unico lugar que monta caminho de log (AGENTS §6).
"""
import os
import re
import unicodedata

# Pasta dos logs da aplicacao; nenhum script pode ter essa pasta de log (CR-005, D7).
APP_DIR = 'app'
# Pasta de ambiente dos logs sem ambiente (CR-009); nenhum ambiente pode se chamar INTERNAL.
INTERNAL_DIR = 'internal'
_RE_OUTSIDE = re.compile(r'[^a-z0-9._-]+')



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


def environment_dir(name: str) -> str:
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


def script_work_dir(script_work_dir, environment, script_name, started_at, ticket_id, script_id=None):
    """Pasta de trabalho do ticket (CR-019, README §8.15), com as mesmas partes da pasta de saida.

    Devolve (base, relativo) no formato de output_dir: base = script_work_dir/<ambiente> e relativo =
    <pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>.
    """
    return output_dir(script_work_dir, environment, script_name, started_at, ticket_id, script_id)


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
