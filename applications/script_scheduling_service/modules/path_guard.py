# -*- coding: utf-8 -*-
"""Validacao de interpretador logico e caminho de script (README §6.4, §8.5, AGENTS §3.2, CR-001).

Modulo puro: nao importa gluon (AGENTS §7.1).
"""
import os

# Interpretadores logicos (CR-001, D1/D2): o catalogo guarda a chave; cada agente a mapeia para o
# executavel local ([agent] interpretadores). cmd.exe/.bat/.cmd sao proibidos (injecao de argumentos).
ALLOWLIST = ('PYTHON3', 'BASH', 'SH', 'POWERSHELL')
POR_PLATAFORMA = {
    'POSIX': ('PYTHON3', 'BASH', 'SH'),
    'WINDOWS': ('PYTHON3', 'POWERSHELL'),
}
# Argumentos fixos entre o executavel e o script (README §6.4); Python sempre com -I.
ARGS_FIXOS = {
    'PYTHON3': ('-I',),
    'BASH': (),
    'SH': (),
    'POWERSHELL': ('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File'),
}


class Codigo(object):
    """Codigos de rejeicao do path_guard."""
    FORA_DA_BASE = 'FORA_DA_BASE'
    NAO_E_ARQUIVO = 'NAO_E_ARQUIVO'
    IGUAL_A_BASE = 'IGUAL_A_BASE'
    CAMINHO_ABSOLUTO = 'CAMINHO_ABSOLUTO'
    CONTEM_PONTOS = 'CONTEM_PONTOS'
    DONO_INVALIDO = 'DONO_INVALIDO'
    GRAVAVEL_GRUPO_OUTROS = 'GRAVAVEL_GRUPO_OUTROS'
    GRAVAVEL_PELO_AGENTE = 'GRAVAVEL_PELO_AGENTE'
    INTERPRETADOR_NAO_PERMITIDO = 'INTERPRETADOR_NAO_PERMITIDO'


class PathGuardErro(Exception):
    """Rejeicao de caminho ou interpretador; a mensagem nunca inclui o caminho."""

    def __init__(self, codigo):
        Exception.__init__(self, codigo)
        self.codigo = codigo


def validar_interpretador(interpretador):
    """Exige que o interpretador logico seja exatamente um item da ALLOWLIST."""
    if interpretador not in ALLOWLIST:
        raise PathGuardErro(Codigo.INTERPRETADOR_NAO_PERMITIDO)


def validar_cadastro(path_file):
    """Checagens textuais equivalentes a ck_tbsss_scr_path (relativo e sem '..')."""
    if not isinstance(path_file, str) or path_file == '' or path_file[0] == '/':
        raise PathGuardErro(Codigo.CAMINHO_ABSOLUTO)
    if '..' in path_file:
        raise PathGuardErro(Codigo.CONTEM_PONTOS)


def _gravavel_pelo_agente(caminho, st, uid_agente):
    if uid_agente is None:
        return os.access(caminho, os.W_OK)
    # Escrita de grupo/outros ja foi rejeitada antes; resta dono ou root.
    return uid_agente == 0 or (st.st_uid == uid_agente and bool(st.st_mode & 0o200))


def _checar_dono_e_modo(caminho, owner_uids, uid_agente):
    st = os.stat(caminho)
    if st.st_uid not in owner_uids:
        raise PathGuardErro(Codigo.DONO_INVALIDO)
    if st.st_mode & 0o022:
        raise PathGuardErro(Codigo.GRAVAVEL_GRUPO_OUTROS)
    if _gravavel_pelo_agente(caminho, st, uid_agente):
        raise PathGuardErro(Codigo.GRAVAVEL_PELO_AGENTE)


def resolver(base_script_dir, path_file, owner_uids, uid_agente=None):
    """Resolve path_file sob a base e devolve script_real; lanca PathGuardErro.

    uid_agente=None avalia escrita com os.access do proprio processo (o agente).
    """
    validar_cadastro(path_file)
    owner_uids = tuple(owner_uids)

    base = os.path.realpath(base_script_dir)
    real = os.path.realpath(os.path.join(base, path_file))
    try:
        dentro = os.path.commonpath([base, real]) == base
    except ValueError:
        dentro = False
    if not dentro:
        raise PathGuardErro(Codigo.FORA_DA_BASE)
    if real == base:
        raise PathGuardErro(Codigo.IGUAL_A_BASE)
    if not os.path.isfile(real):
        raise PathGuardErro(Codigo.NAO_E_ARQUIVO)

    # real esta estritamente dentro de base: subir por dirname termina em base.
    _checar_dono_e_modo(real, owner_uids, uid_agente)
    atual = os.path.dirname(real)
    while atual != base:
        _checar_dono_e_modo(atual, owner_uids, uid_agente)
        atual = os.path.dirname(atual)
    _checar_dono_e_modo(base, owner_uids, uid_agente)
    return real
