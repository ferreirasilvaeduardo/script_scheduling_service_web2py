# -*- coding: utf-8 -*-
"""Pastas e caminhos dos logs (README §8.4, §11.3, §13, CR-005 D5/D6/D7, R-a a R-e).

Modulo puro: nao importa gluon (AGENTS §7.1). E o unico lugar que monta caminho de log (AGENTS §6).
"""
import datetime
import os
import re
import shutil
import unicodedata

# Pasta dos logs da aplicacao; nenhum script pode ter essa pasta de log (CR-005, D7).
PASTA_APP = 'app'
_RE_FORA = re.compile(r'[^a-z0-9._-]+')

_RE_ANO = re.compile(r'^\d{4}$')
_RE_DOIS_DIGITOS = re.compile(r'^\d{2}$')


def pasta_script(nome, script_id=None):
    """Forma segura do nome do script para a pasta do log de execucao (CR-005, R-a).

    Sem acento (NFKD -> ASCII), minusculo, cada sequencia fora de [a-z0-9._-] vira '_',
    sem '.' ou '_' nas pontas. Vazio vira 'script_<id>' (ou 'script').
    """
    texto = unicodedata.normalize('NFKD', nome or u'')
    texto = texto.encode('ascii', 'ignore').decode('ascii').lower()
    texto = _RE_FORA.sub('_', texto).strip('._')
    if not texto:
        return 'script_%s' % script_id if script_id is not None else 'script'
    return texto


def nome_reservado(nome):
    """True se o nome do script geraria a pasta reservada 'app' (CR-005, D7)."""
    return pasta_script(nome) == PASTA_APP


def partes_minuto(dt):
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
#    log_dir/<pasta_do_script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log
# ---------------------------------------------------------------------------

def diretorio_log_execucao(log_dir, nome_script, started_at, script_id=None):
    """Diretorio do log de execucao do script conforme started_at (banco)."""
    pasta = pasta_script(nome_script, script_id)
    ano, mes, dia, hora, minuto = partes_minuto(started_at)
    return os.path.join(log_dir, pasta, ano, mes, dia, hora, minuto)


def garantir_diretorio(diretorio, avisos=None):
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


def nome_log_parcial(ticket_id):
    """Nome do log aberto antes do spawn: ticket_<id>.log.parcial (CR-005, R-b)."""
    return 'ticket_%s.log.parcial' % ticket_id


def nome_log_execucao(ticket_id, pid=None):
    """Nome final do log de execucao: ticket_<id>_<PID>.log ou ticket_<id>_0.log (CR-005, R-b)."""
    pid_val = pid if (pid is not None and pid > 0) else 0
    return 'ticket_%s_%s.log' % (ticket_id, pid_val)


def caminho_log_parcial(log_dir, nome_script, started_at, ticket_id, script_id=None):
    """Caminho completo do arquivo parcial pre-spawn."""
    diretorio = diretorio_log_execucao(log_dir, nome_script, started_at, script_id)
    return os.path.join(diretorio, nome_log_parcial(ticket_id))


def caminho_log_execucao(log_dir, nome_script, started_at, ticket_id, pid=None, script_id=None):
    """Caminho completo do arquivo de log final de execucao."""
    diretorio = diretorio_log_execucao(log_dir, nome_script, started_at, script_id)
    return os.path.join(diretorio, nome_log_execucao(ticket_id, pid))


# ---------------------------------------------------------------------------
# 2. Logs da aplicacao (CR-005 D6, R-c, R-d, R-e, README §13)
#    log_dir/app/AAAA/MM/DD/HH/MI/<nome_log>_<PID>[_<n>].log
# ---------------------------------------------------------------------------

def diretorio_log_app(log_dir, dt):
    """Diretorio de log da aplicacao no minuto de dt (relogio local do processo)."""
    ano, mes, dia, hora, minuto = partes_minuto(dt)
    return os.path.join(log_dir, PASTA_APP, ano, mes, dia, hora, minuto)


def nome_log_app(nome_processo, pid, seq=None):
    """Nome do arquivo de log da aplicacao. Com seq > 1 ganha sufixo _<n> (CR-005, R-c)."""
    base = nome_processo[:-4] if nome_processo.endswith('.log') else nome_processo
    if seq is not None and seq > 1:
        return '%s_%s_%s.log' % (base, pid, seq)
    return '%s_%s.log' % (base, pid)


def caminho_log_app(log_dir, nome_processo, pid, dt, seq=None):
    """Caminho completo do arquivo de log da aplicacao no minuto dt."""
    diretorio = diretorio_log_app(log_dir, dt)
    return os.path.join(diretorio, nome_log_app(nome_processo, pid, seq))


def proximo_caminho_log_app(log_dir, nome_processo, pid, dt):
    """Gera o proximo caminho disponivel para log da aplicacao, aplicando sufixo _<n> se colidir."""
    diretorio = diretorio_log_app(log_dir, dt)
    caminho = os.path.join(diretorio, nome_log_app(nome_processo, pid))
    if not os.path.exists(caminho):
        return caminho
    seq = 2
    while True:
        candidato = os.path.join(diretorio, nome_log_app(nome_processo, pid, seq))
        if not os.path.exists(candidato):
            return candidato
        seq += 1


# ---------------------------------------------------------------------------
# 3. Auxiliares de retencao e parsing de pastas de data (README §11.3, §13)
# ---------------------------------------------------------------------------

def parse_data_dia(ano_str, mes_str, dia_str):
    """Valida se ano/mes/dia sao numeros e representam uma data valida do calendario."""
    if not (_RE_ANO.match(ano_str) and _RE_DOIS_DIGITOS.match(mes_str) and _RE_DOIS_DIGITOS.match(dia_str)):
        return None
    try:
        return datetime.date(int(ano_str), int(mes_str), int(dia_str))
    except (ValueError, OverflowError):
        return None


def parse_data_minuto(ano_str, mes_str, dia_str, hora_str, min_str):
    """Valida se ano/mes/dia/hora/minuto representam um instante valido do calendario."""
    if not (_RE_ANO.match(ano_str) and _RE_DOIS_DIGITOS.match(mes_str) and _RE_DOIS_DIGITOS.match(dia_str)
            and _RE_DOIS_DIGITOS.match(hora_str) and _RE_DOIS_DIGITOS.match(min_str)):
        return None
    try:
        return datetime.datetime(int(ano_str), int(mes_str), int(dia_str), int(hora_str), int(min_str))
    except (ValueError, OverflowError):
        return None


def limpar_retencao_app(log_dir, retention_days, ref_dt=None, falhas=None):
    """Apaga as pastas log_dir/app/AAAA/MM/DD anteriores a retention_days dias (CR-005, R-d, README §13).

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
    pasta_app = os.path.join(log_dir, PASTA_APP)
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
                data_dia = parse_data_dia(ano_str, mes_str, dia_str)
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

