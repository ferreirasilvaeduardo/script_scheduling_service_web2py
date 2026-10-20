# -*- coding: utf-8 -*-
"""Validacao de interpretador logico e caminho de script (README §6.4, §8.5, AGENTS §3.2, CR-001, CR-005).

CR-005: somente POSIX e caminho absoluto livre (sem pastas base). CR-007: sem link simbolico no caminho
do script, donos proibidos (agente e usuarios de execucao) e checagem de cadeia do executavel do interpretador.
Modulo puro: nao importa gluon (AGENTS §7.1).
"""
import errno
import os
import pwd

import plataforma

# Interpretadores logicos (CR-001, D1/D2; CR-005: somente POSIX): o catalogo guarda a chave; cada agente
# a mapeia para o executavel local ([agent] interpretadores).
ALLOWLIST = ('PYTHON3', 'BASH', 'SH')
# Argumentos fixos entre o executavel e o script (README §6.4); Python sempre com -I.
ARGS_FIXOS = {
    'PYTHON3': ('-I',),
    'BASH': (),
    'SH': (),
}
# Pastas do sistema onde nenhum script pode ficar (README §8.5, CR-005 D3).
PASTAS_DO_SISTEMA = plataforma.PASTAS_DO_SISTEMA
# Tamanho maximo de path_file (coluna VARCHAR2(500 CHAR)).
TAMANHO_MAXIMO = 500


class Codigo(object):
    """Codigos de rejeicao do path_guard (README §8.5)."""
    CAMINHO_RELATIVO = 'CAMINHO_RELATIVO'
    CAMINHO_NAO_NORMALIZADO = 'CAMINHO_NAO_NORMALIZADO'
    CONTEM_PONTOS = 'CONTEM_PONTOS'
    SEPARADOR_INVALIDO = 'SEPARADOR_INVALIDO'
    CARACTERE_INVALIDO = 'CARACTERE_INVALIDO'
    CAMINHO_COM_LINK = 'CAMINHO_COM_LINK'
    PASTA_DO_SISTEMA = 'PASTA_DO_SISTEMA'
    PASTA_DO_SSS = 'PASTA_DO_SSS'
    NAO_ENCONTRADO = 'NAO_ENCONTRADO'
    SEM_ACESSO = 'SEM_ACESSO'
    NAO_E_ARQUIVO = 'NAO_E_ARQUIVO'
    DONO_INVALIDO = 'DONO_INVALIDO'
    GRAVAVEL_GRUPO_OUTROS = 'GRAVAVEL_GRUPO_OUTROS'
    GRAVAVEL_PELO_AGENTE = 'GRAVAVEL_PELO_AGENTE'
    GRAVAVEL_PELO_EXECUTOR = 'GRAVAVEL_PELO_EXECUTOR'
    INTERPRETADOR_NAO_PERMITIDO = 'INTERPRETADOR_NAO_PERMITIDO'
    INTERPRETADOR_INSEGURO = 'INTERPRETADOR_INSEGURO'


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
    """Formato de path_file (README §8.5, ck_tbsss_scr_path): absoluto, normalizado, sem '..', '\\' e controle."""
    if not isinstance(path_file, str) or path_file[:1] != '/':
        raise PathGuardErro(Codigo.CAMINHO_RELATIVO)
    if any(ord(c) < 32 or ord(c) == 127 for c in path_file):
        raise PathGuardErro(Codigo.CARACTERE_INVALIDO)
    if '\\' in path_file:
        raise PathGuardErro(Codigo.SEPARADOR_INVALIDO)
    if '..' in path_file:
        raise PathGuardErro(Codigo.CONTEM_PONTOS)
    # normpath mantem '//' inicial (POSIX); a CK recusa '//' em qualquer ponto.
    if path_file == '/' or '//' in path_file or os.path.normpath(path_file) != path_file:
        raise PathGuardErro(Codigo.CAMINHO_NAO_NORMALIZADO)


def _dentro(caminho, pasta):
    """True se caminho e a propria pasta ou fica abaixo dela (por componente, nunca prefixo de texto)."""
    return os.path.commonpath([caminho, pasta]) == pasta


def checar_pastas_proibidas(path_file, dirs_sss=()):
    """Recusa pastas do sistema e log_dir/work_dir, no caminho digitado e no resolvido (symlink)."""
    sss = [plataforma.caminho_final(d) for d in dirs_sss if d]
    for alvo in (path_file, plataforma.caminho_final(path_file)):
        if any(_dentro(alvo, d) for d in PASTAS_DO_SISTEMA):
            raise PathGuardErro(Codigo.PASTA_DO_SISTEMA)
        if any(_dentro(alvo, d) for d in sss):
            raise PathGuardErro(Codigo.PASTA_DO_SSS)


def uids_de_usuarios(nomes):
    """UIDs dos usuarios do SO existentes neste servidor (usuarios de execucao, CR-007); ausentes sao ignorados."""
    uids = []
    for nome in nomes or ():
        try:
            uids.append(pwd.getpwnam(nome).pw_uid)
        except KeyError:
            continue
    return tuple(uids)


def _stat(caminho, lstat=False):
    """os.stat/lstat com EACCES -> SEM_ACESSO e ausente -> NAO_ENCONTRADO (README §8.5)."""
    try:
        return os.lstat(caminho) if lstat else os.stat(caminho)
    except OSError as e:
        if e.errno in (errno.EACCES, errno.EPERM):
            raise PathGuardErro(Codigo.SEM_ACESSO)
        raise PathGuardErro(Codigo.NAO_ENCONTRADO)


def _checar_cadeia(real, donos, uid_agente, uids_proibidos, parar_em):
    """Cadeia de dono e escrita ate '/' pela camada de plataforma (README §8.0); falha vira PathGuardErro."""
    codigo = plataforma.checar_cadeia(real, donos, uid_agente, uids_proibidos, parar_em)
    if codigo:
        raise PathGuardErro(codigo)


def resolver(path_file, owner_uids, uid_agente=None, dirs_sss=(), parar_em='/', uids_proibidos=()):
    """Confere o script no servidor local e devolve o caminho real (README §8.5, CR-005 D3, CR-007).

    - formato; sem link simbolico em nenhum componente (CAMINHO_COM_LINK); pastas proibidas;
    - NAO_ENCONTRADO se nao existe; SEM_ACESSO se uma pasta nao deixa passar; NAO_E_ARQUIVO se nao e arquivo;
    - dono do arquivo em owner_uids; cada diretorio ate '/' com dono root ou em owner_uids;
      arquivo e diretorios sem escrita de grupo/outros nem do agente, e sem pertencer ao agente
      nem a um uid de uids_proibidos (usuarios de execucao).
    uid_agente=None usa o proprio processo (o agente). parar_em limita a cadeia (so testes).
    """
    validar_cadastro(path_file)
    checar_pastas_proibidas(path_file, dirs_sss)
    codigo = plataforma.validar_caminho_script(path_file, tuple(owner_uids), tuple(uids_proibidos),
                                               uid_agente=uid_agente, parar_em=parar_em)
    if codigo:
        raise PathGuardErro(codigo)
    return plataforma.caminho_final(path_file)


def validar_executavel(caminho, owner_uids, uid_agente=None, uids_proibidos=(), dirs_sss=(), parar_em='/'):
    """Executavel de um interpretador de [agent] interpretadores (README §8.5, CR-007 R-15).

    Pode ser link simbolico (ex.: /usr/bin/python3): a cadeia do proprio caminho e a do destino passam pela
    mesma checagem do script (dono root ou de owner_uids, sem escrita de grupo/outros, sem pertencer ao agente
    nem a um usuario de execucao), mas pode ficar nas pastas do sistema. Fora de log_dir/work_dir/exec_work_dir.
    Devolve o caminho real; falha: NAO_ENCONTRADO ou INTERPRETADOR_INSEGURO.
    """
    if not isinstance(caminho, str) or caminho[:1] != '/' or os.path.normpath(caminho) != caminho:
        raise PathGuardErro(Codigo.INTERPRETADOR_INSEGURO)
    real = plataforma.caminho_final(caminho)
    donos = tuple(owner_uids) + ((0,) if 0 not in owner_uids else ())
    try:
        _stat(real)
        sss = [plataforma.caminho_final(d) for d in dirs_sss if d]
        if any(_dentro(alvo, d) for alvo in (caminho, real) for d in sss):
            raise PathGuardErro(Codigo.INTERPRETADOR_INSEGURO)
        if not os.path.isfile(real) or not os.access(real, os.X_OK):
            raise PathGuardErro(Codigo.INTERPRETADOR_INSEGURO)
        _checar_cadeia(real, donos, uid_agente, tuple(uids_proibidos), parar_em)
        if real != caminho:
            _checar_cadeia(os.path.dirname(caminho), donos, uid_agente, tuple(uids_proibidos), parar_em)
    except PathGuardErro as e:
        if e.codigo == Codigo.NAO_ENCONTRADO:
            raise
        raise PathGuardErro(Codigo.INTERPRETADOR_INSEGURO)
    return real

