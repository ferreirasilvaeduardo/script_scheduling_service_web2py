# -*- coding: utf-8 -*-
"""Validacao de interpretador logico e caminho de script (README §6.4, §8.5, AGENTS §3.2, CR-001, CR-005).

CR-005: somente POSIX e caminho absoluto livre (sem pastas base). Modulo puro: nao importa gluon (AGENTS §7.1).
"""
import os

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
    PASTA_DO_SISTEMA = 'PASTA_DO_SISTEMA'
    PASTA_DO_SSS = 'PASTA_DO_SSS'
    NAO_ENCONTRADO = 'NAO_ENCONTRADO'
    NAO_E_ARQUIVO = 'NAO_E_ARQUIVO'
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


def _gravavel_pelo_agente(caminho, st, uid_agente):
    if uid_agente is None:
        return os.access(caminho, os.W_OK)
    # Escrita de grupo/outros ja foi rejeitada antes; resta dono ou root.
    return uid_agente == 0 or (st.st_uid == uid_agente and bool(st.st_mode & 0o200))


def _checar_dono_e_modo(caminho, donos, uid_agente):
    st = os.stat(caminho)
    if st.st_uid not in donos:
        raise PathGuardErro(Codigo.DONO_INVALIDO)
    if st.st_mode & 0o022:
        raise PathGuardErro(Codigo.GRAVAVEL_GRUPO_OUTROS)
    if _gravavel_pelo_agente(caminho, st, uid_agente):
        raise PathGuardErro(Codigo.GRAVAVEL_PELO_AGENTE)


def resolver(path_file, owner_uids, uid_agente=None, dirs_sss=(), parar_em='/'):
    """Confere o script no servidor local e devolve o caminho real (README §8.5, CR-005 D3).

    - formato e pastas proibidas (digitado e resolvido);
    - NAO_ENCONTRADO se nao existe; NAO_E_ARQUIVO se existe mas nao e arquivo regular;
    - dono do arquivo em owner_uids; cada diretorio ate '/' com dono root ou em owner_uids;
      arquivo e diretorios sem escrita de grupo/outros nem do agente.
    uid_agente=None avalia escrita com os.access do proprio processo (o agente).
    parar_em limita a subida da cadeia (so testes; producao usa sempre '/').
    """
    validar_cadastro(path_file)
    checar_pastas_proibidas(path_file, dirs_sss)
    real = os.path.realpath(path_file)
    if not os.path.lexists(real):
        raise PathGuardErro(Codigo.NAO_ENCONTRADO)
    if not os.path.isfile(real):
        raise PathGuardErro(Codigo.NAO_E_ARQUIVO)
    donos = tuple(owner_uids)
    donos_dir = donos + ((0,) if 0 not in donos else ())
    _checar_dono_e_modo(real, donos, uid_agente)
    limite = os.path.realpath(parar_em)
    atual = os.path.dirname(real)
    while True:
        _checar_dono_e_modo(atual, donos_dir, uid_agente)
        if atual == limite or atual == '/':
            break
        atual = os.path.dirname(atual)
    return real


def nome_exibicao(path_file, completo):
    """Caminho do script para a tela: completo para admin; '…/arquivo' para os demais (CR-005, R-f)."""
    if not path_file:
        return path_file
    return path_file if completo else u'…/' + os.path.basename(path_file)
