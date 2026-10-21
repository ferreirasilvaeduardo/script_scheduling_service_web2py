# -*- coding: utf-8 -*-
"""Validacao de interpretador logico e caminho de script (README §6.4, §8.5, AGENTS §3.2, CR-001, CR-005, CR-011).

CR-005: somente POSIX e caminho absoluto livre (sem pastas base). CR-011: o ambiente controla o conteudo e a
versao dos scripts; o SSS confere so o essencial do arquivo real (pode haver link simbolico no caminho):
existe, e arquivo regular, nao e gravavel por grupo nem por outros e fica fora das pastas do sistema e do SSS.
Modulo puro: nao importa gluon (AGENTS §7.1).
"""
import errno
import os

import plataforma

# Interpretadores logicos (CR-001, D1/D2; CR-005: somente POSIX): o catalogo guarda a chave; cada agente
# a mapeia para o executavel local ([agent] interpreters).
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
    PASTA_DO_SISTEMA = 'PASTA_DO_SISTEMA'
    PASTA_DO_SSS = 'PASTA_DO_SSS'
    NAO_ENCONTRADO = 'NAO_ENCONTRADO'
    SEM_ACESSO = 'SEM_ACESSO'
    NAO_E_ARQUIVO = 'NAO_E_ARQUIVO'
    GRAVAVEL_GRUPO_OUTROS = 'GRAVAVEL_GRUPO_OUTROS'
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


def _stat(caminho):
    """os.stat com EACCES -> SEM_ACESSO e ausente -> NAO_ENCONTRADO (README §8.5)."""
    try:
        return os.stat(caminho)
    except OSError as e:
        if e.errno in (errno.EACCES, errno.EPERM):
            raise PathGuardErro(Codigo.SEM_ACESSO)
        raise PathGuardErro(Codigo.NAO_ENCONTRADO)


def resolver(path_file, dirs_sss=()):
    """Confere o script no servidor do agente e devolve o caminho real, que e o executado (README §8.5, CR-011).

    Formato do caminho cadastrado; pastas do sistema e do SSS no cadastrado e no real; o arquivo real existe
    (NAO_ENCONTRADO; ciclo de links tambem), as pastas deixam passar (SEM_ACESSO), e arquivo regular
    (NAO_E_ARQUIVO) e nao e gravavel por grupo nem por outros (GRAVAVEL_GRUPO_OUTROS).
    """
    validar_cadastro(path_file)
    checar_pastas_proibidas(path_file, dirs_sss)
    codigo = plataforma.validar_caminho_script(path_file)
    if codigo:
        raise PathGuardErro(codigo)
    return plataforma.caminho_final(path_file)


def validar_executavel(caminho, dirs_sss=()):
    """Executavel de um interpretador de [agent] interpreters (README §8.5, CR-011): caminho absoluto e
    normalizado, existe, e arquivo executavel e fica fora de log_dir/work_dir/exec_work_dir. Pode ser link
    simbolico (ex.: /usr/bin/python3) e ficar nas pastas do sistema. Devolve o caminho real; falha:
    NAO_ENCONTRADO ou INTERPRETADOR_INSEGURO."""
    if not isinstance(caminho, str) or caminho[:1] != '/' or os.path.normpath(caminho) != caminho:
        raise PathGuardErro(Codigo.INTERPRETADOR_INSEGURO)
    real = plataforma.caminho_final(caminho)
    try:
        _stat(real)
    except PathGuardErro as e:
        if e.codigo == Codigo.NAO_ENCONTRADO:
            raise
        raise PathGuardErro(Codigo.INTERPRETADOR_INSEGURO)
    sss = [plataforma.caminho_final(d) for d in dirs_sss if d]
    if any(_dentro(alvo, d) for alvo in (caminho, real) for d in sss):
        raise PathGuardErro(Codigo.INTERPRETADOR_INSEGURO)
    if not os.path.isfile(real) or not os.access(real, os.X_OK):
        raise PathGuardErro(Codigo.INTERPRETADOR_INSEGURO)
    return real
