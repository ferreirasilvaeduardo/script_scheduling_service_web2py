# -*- coding: utf-8 -*-
"""Validacao de interpretador logico e caminho de script (README §6.4, §8.5, AGENTS §3.2, CR-001, CR-005, CR-011).

CR-005: somente POSIX e caminho absoluto livre. CR-011: o ambiente controla o conteudo e a
versao dos scripts; o SSS confere so o essencial do arquivo real (pode haver link simbolico no caminho):
existe, e arquivo regular, nao e gravavel por grupo nem por outros e fica fora das pastas do sistema e do SSS.
CR-023: o caminho cadastrado tambem pode ser relativo a [agent] script_base_dir de cada agente, e nenhum
script fica dentro da pasta da aplicacao (salvo dev/ no DEV).
Modulo puro: nao importa gluon (AGENTS §7.1).
"""
import errno
import os
from typing import Iterable, Optional

from sss.platform import os_platform

# Interpretadores logicos (CR-001, D1/D2; CR-005: somente POSIX): o catalogo guarda a chave; cada agente
# a mapeia para o executavel local ([agent] interpreters).
ALLOWLIST = ('PYTHON3', 'BASH', 'SH')
# Argumentos fixos entre o executavel e o script (README §6.4); Python sempre com -I.
FIXED_ARGS = {
    'PYTHON3': ('-I',),
    'BASH': (),
    'SH': (),
}
# Pastas do sistema onde nenhum script pode ficar (README §8.5, CR-005 D3).
SYSTEM_DIRS = os_platform.SYSTEM_DIRS
# Tamanho maximo de path_file (coluna VARCHAR2(500 CHAR)).
MAX_LENGTH = 500
# Pasta da aplicacao (src/sss/platform/ -> raiz), que a atualizacao troca inteira (CR-023, D8);
# no DEV, a subpasta dev/ guarda os scripts de exemplo e e a excecao.
APP_DIR = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
APP_DEV_DIR = os.path.join(APP_DIR, "dev")


class Code(object):
    """Codigos de rejeicao do path_guard (README §8.5)."""
    # Agente anterior ao CR-023 diante de caminho relativo; o atual nao o usa mais.
    RELATIVE_PATH = 'RELATIVE_PATH'
    NO_BASE_DIR = 'NO_BASE_DIR'
    APP_DIR = 'APP_DIR'
    PATH_NOT_NORMALIZED = 'PATH_NOT_NORMALIZED'
    HAS_DOTS = 'HAS_DOTS'
    INVALID_SEPARATOR = 'INVALID_SEPARATOR'
    INVALID_CHARACTER = 'INVALID_CHARACTER'
    SYSTEM_DIR = 'SYSTEM_DIR'
    SSS_DIR = 'SSS_DIR'
    NOT_FOUND = 'NOT_FOUND'
    NO_ACCESS = 'NO_ACCESS'
    NOT_A_FILE = 'NOT_A_FILE'
    GROUP_OTHER_WRITABLE = 'GROUP_OTHER_WRITABLE'
    INTERPRETER_NOT_ALLOWED = 'INTERPRETER_NOT_ALLOWED'
    INTERPRETER_UNSAFE = 'INTERPRETER_UNSAFE'


class PathGuardError(Exception):
    """Rejeicao de caminho ou interpretador; a mensagem nunca inclui o caminho."""

    def __init__(self, code):
        Exception.__init__(self, code)
        self.code = code


def validate_interpreter(interpreter):
    """Exige que o interpretador logico seja exatamente um item da ALLOWLIST."""
    if interpreter not in ALLOWLIST:
        raise PathGuardError(Code.INTERPRETER_NOT_ALLOWED)


def is_relative(path_file: object) -> bool:
    """True se o caminho cadastrado e relativo a [agent] script_base_dir (CR-023, D2)."""
    return isinstance(path_file, str) and path_file != '' and path_file[:1] != '/'


def validate_registration(path_file: object) -> None:
    """Formato de path_file (README §8.5, ck_tbsss_scr_path): absoluto ou relativo (CR-023), normalizado,
    sem '..', '//', '\\' nem controle."""
    if not isinstance(path_file, str) or path_file == '':
        raise PathGuardError(Code.PATH_NOT_NORMALIZED)
    if any(ord(c) < 32 or ord(c) == 127 for c in path_file):
        raise PathGuardError(Code.INVALID_CHARACTER)
    if '\\' in path_file:
        raise PathGuardError(Code.INVALID_SEPARATOR)
    if '..' in path_file:
        raise PathGuardError(Code.HAS_DOTS)
    # normpath mantem '//' inicial (POSIX); a CK recusa '//' em qualquer ponto. No relativo, recusa './'
    # no inicio, '.' sozinho e barra no fim.
    if path_file == '/' or '//' in path_file or os.path.normpath(path_file) != path_file:
        raise PathGuardError(Code.PATH_NOT_NORMALIZED)
    if path_file == '.':
        raise PathGuardError(Code.PATH_NOT_NORMALIZED)


def join_base(path_file: str, base_dir: Optional[str]) -> str:
    """Caminho no servidor do agente: o absoluto como esta; o relativo junto de script_base_dir (CR-023, D3).
    Relativo sem pasta base: NO_BASE_DIR."""
    if not is_relative(path_file):
        return path_file
    if not base_dir:
        raise PathGuardError(Code.NO_BASE_DIR)
    return os.path.join(base_dir, path_file)


def _inside(path, folder):
    """True se caminho e a propria pasta ou fica abaixo dela (por componente, nunca prefixo de texto)."""
    return os.path.commonpath([path, folder]) == folder


def check_forbidden_dirs(path_file: str, sss_dirs: Iterable[Optional[str]] = (), dev: bool = False) -> None:
    """Recusa pastas do sistema, as do SSS (log_dir, work_dir...) e a da aplicacao (salvo dev/ no DEV,
    CR-023 D8), no caminho digitado e no resolvido (symlink). Caminho relativo: nada a conferir aqui."""
    if is_relative(path_file):
        return
    sss = [os_platform.final_path(d) for d in sss_dirs if d]
    for target in (path_file, os_platform.final_path(path_file)):
        if any(_inside(target, d) for d in SYSTEM_DIRS):
            raise PathGuardError(Code.SYSTEM_DIR)
        if any(_inside(target, d) for d in sss):
            raise PathGuardError(Code.SSS_DIR)
        if _inside(target, APP_DIR) and not (dev and _inside(target, APP_DEV_DIR)):
            raise PathGuardError(Code.APP_DIR)


def _stat(path):
    """os.stat com EACCES -> NO_ACCESS e ausente -> NOT_FOUND (README §8.5)."""
    try:
        return os.stat(path)
    except OSError as e:
        if e.errno in (errno.EACCES, errno.EPERM):
            raise PathGuardError(Code.NO_ACCESS)
        raise PathGuardError(Code.NOT_FOUND)


def resolve(path_file: str, sss_dirs: Iterable[Optional[str]] = (), base_dir: Optional[str] = None,
            dev: bool = False) -> str:
    """Confere o script no servidor do agente e devolve o caminho real, que e o executado (README §8.5, CR-011).

    Formato do caminho cadastrado; o relativo vira base_dir/<relativo> (CR-023; sem base, NO_BASE_DIR) e o
    real pode ficar fora da base; pastas do sistema, do SSS e da aplicacao no caminho e no real; o arquivo
    real existe (NOT_FOUND; ciclo de links tambem), as pastas deixam passar (NO_ACCESS), e arquivo regular
    (NOT_A_FILE) e nao e gravavel por grupo nem por outros (GROUP_OTHER_WRITABLE).
    """
    validate_registration(path_file)
    target = join_base(path_file, base_dir)
    check_forbidden_dirs(target, sss_dirs, dev=dev)
    code = os_platform.validate_script_path(target)
    if code:
        raise PathGuardError(code)
    return os_platform.final_path(target)


def validate_executable(path, sss_dirs=()):
    """Executavel de um interpretador de [agent] interpreters (README §8.5, CR-011): caminho absoluto e
    normalizado, existe, e arquivo executavel e fica fora de log_dir/work_dir/exec_work_dir. Pode ser link
    simbolico (ex.: /usr/bin/python3) e ficar nas pastas do sistema. Devolve o caminho real; falha:
    NOT_FOUND ou INTERPRETER_UNSAFE."""
    if not isinstance(path, str) or path[:1] != '/' or os.path.normpath(path) != path:
        raise PathGuardError(Code.INTERPRETER_UNSAFE)
    real = os_platform.final_path(path)
    try:
        _stat(real)
    except PathGuardError as e:
        if e.code == Code.NOT_FOUND:
            raise
        raise PathGuardError(Code.INTERPRETER_UNSAFE)
    sss = [os_platform.final_path(d) for d in sss_dirs if d]
    if any(_inside(target, d) for target in (path, real) for d in sss):
        raise PathGuardError(Code.INTERPRETER_UNSAFE)
    if not os.path.isfile(real) or not os.access(real, os.X_OK):
        raise PathGuardError(Code.INTERPRETER_UNSAFE)
    return real
