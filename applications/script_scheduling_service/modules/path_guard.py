# -*- coding: utf-8 -*-
"""Validacao de interpretador logico e caminho de script (README §6.4, §8.5, AGENTS §3.2, CR-001, CR-005).

CR-005: somente POSIX e caminho absoluto livre (sem pastas base). CR-007: sem link simbolico no caminho
do script, donos proibidos (agente e usuarios de execucao) e checagem de cadeia do executavel do interpretador.
Modulo puro: nao importa gluon (AGENTS §7.1).
"""
import errno
import os
import pwd

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
PASTAS_DO_SISTEMA = ('/bin', '/sbin', '/usr', '/lib', '/lib32', '/lib64', '/libx32',
                     '/etc', '/boot', '/proc', '/sys', '/dev', '/root')
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
    sss = [os.path.realpath(d) for d in dirs_sss if d]
    for alvo in (path_file, os.path.realpath(path_file)):
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


def _gravavel_pelo_agente(caminho, st, uid_agente):
    if uid_agente is None:
        return os.access(caminho, os.W_OK)
    # Escrita de grupo/outros ja foi rejeitada antes; resta dono ou root.
    return uid_agente == 0 or (st.st_uid == uid_agente and bool(st.st_mode & 0o200))


def _checar_dono_e_modo(caminho, donos, uid_agente, uids_proibidos=()):
    st = _stat(caminho)
    if st.st_uid not in donos:
        raise PathGuardErro(Codigo.DONO_INVALIDO)
    if st.st_mode & 0o022:
        raise PathGuardErro(Codigo.GRAVAVEL_GRUPO_OUTROS)
    # CR-007, R-15: o dono pode mudar o modo a qualquer momento, entao pertencer ao agente ja e proibido.
    agente = os.geteuid() if uid_agente is None else uid_agente
    if st.st_uid == agente or _gravavel_pelo_agente(caminho, st, uid_agente):
        raise PathGuardErro(Codigo.GRAVAVEL_PELO_AGENTE)
    if st.st_uid in uids_proibidos:
        raise PathGuardErro(Codigo.GRAVAVEL_PELO_EXECUTOR)


def _checar_cadeia(real, donos, uid_agente, uids_proibidos, parar_em):
    donos_dir = donos + ((0,) if 0 not in donos else ())
    _checar_dono_e_modo(real, donos, uid_agente, uids_proibidos)
    limite = os.path.realpath(parar_em)
    atual = os.path.dirname(real)
    while True:
        _checar_dono_e_modo(atual, donos_dir, uid_agente, uids_proibidos)
        if atual == limite or atual == '/':
            break
        atual = os.path.dirname(atual)


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
    real = os.path.realpath(path_file)
    if real != path_file:
        raise PathGuardErro(Codigo.CAMINHO_COM_LINK)
    st = _stat(real, lstat=True)
    if not os.path.isfile(real) or os.path.islink(real):
        raise PathGuardErro(Codigo.NAO_E_ARQUIVO)
    del st
    _checar_cadeia(real, tuple(owner_uids), uid_agente, tuple(uids_proibidos), parar_em)
    return real


def validar_executavel(caminho, owner_uids, uid_agente=None, uids_proibidos=(), dirs_sss=(), parar_em='/'):
    """Executavel de um interpretador de [agent] interpretadores (README §8.5, CR-007 R-15).

    Pode ser link simbolico (ex.: /usr/bin/python3): a cadeia do proprio caminho e a do destino passam pela
    mesma checagem do script (dono root ou de owner_uids, sem escrita de grupo/outros, sem pertencer ao agente
    nem a um usuario de execucao), mas pode ficar nas pastas do sistema. Fora de log_dir/work_dir/exec_work_dir.
    Devolve o caminho real; falha: NAO_ENCONTRADO ou INTERPRETADOR_INSEGURO.
    """
    if not isinstance(caminho, str) or caminho[:1] != '/' or os.path.normpath(caminho) != caminho:
        raise PathGuardErro(Codigo.INTERPRETADOR_INSEGURO)
    real = os.path.realpath(caminho)
    donos = tuple(owner_uids) + ((0,) if 0 not in owner_uids else ())
    try:
        _stat(real)
        sss = [os.path.realpath(d) for d in dirs_sss if d]
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

