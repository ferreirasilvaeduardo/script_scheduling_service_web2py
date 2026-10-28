# -*- coding: utf-8 -*-
"""Validacao de interpretador e caminho de script (README §6.4, §8.5, AGENTS §3.2, CR-001, CR-005, CR-011).

CR-005: somente POSIX e caminho absoluto livre. CR-011: o ambiente controla o conteudo e a
versao dos scripts; o SSS confere so o essencial do arquivo real (pode haver link simbolico no caminho):
existe, e arquivo regular, nao e gravavel por grupo nem por outros e fica fora das pastas do sistema e do SSS.
CR-023: o caminho cadastrado tambem pode ser relativo a [agent] script_base_dir de cada agente, e nenhum
script fica dentro da pasta da aplicacao (salvo dev/ no DEV).
Modulo puro: nao importa gluon (AGENTS §7.1).
"""
import errno
import os
import re
import shutil
from typing import Iterable, Optional, Tuple

from sss.platform import os_platform

# Interpretador do cadastro (CR-026, D3): so o nome, procurado no PATH do agente. A ordem na execucao e o
# digitado no disparo, o #! do script e, por ultimo, o do cadastro (CR-027); quem nao existe e pulado.
ALLOWLIST = ('python', 'python3', 'sh', 'bash')
# Chaves logicas anteriores ao CR-026 (snapshots v5 e v6 ainda na fila): o nome equivalente.
LEGACY = {'PYTHON3': 'python3', 'PYTHON': 'python', 'BASH': 'bash', 'SH': 'sh',
          'PYTHON_SCRIPT': 'python3', 'SHELL_SCRIPT': 'sh'}
# Argumentos entre o executavel e o script (README §6.4, CR-026 D7): o python3 achado pelo cadastro (inclusive
# na troca python <-> python3, CR-027) roda com -I;
# os demais Python (python, que pode ser o 2, o do #! e o digitado) com -E -s, que existem no 2 e no 3.
PYTHON3_ARGS = ('-I',)
PYTHON_PORTABLE_ARGS = ('-E', '-s')
_RE_PYTHON = re.compile(r"^python[0-9.]*$")
# Interpretador digitado no disparo (CR-025): caminho absoluto ou so o nome, buscado no PATH do agente.
OVERRIDE_MAX_LENGTH = 500
_RE_INTERPRETER_NAME = re.compile(r"^[A-Za-z0-9._+-]{1,100}$")
# Bytes lidos do inicio do script para o #! (o Linux le ate 256).
SHEBANG_MAX_BYTES = 256
# Pastas do sistema onde nenhum script pode ficar (README §8.5, CR-005 D3).
SYSTEM_DIRS = os_platform.SYSTEM_DIRS
# Tamanho maximo de path_file (coluna VARCHAR2(500 CHAR)).
MAX_LENGTH = 500
# Pasta da aplicacao (src/sss/platform/ -> raiz), que a atualizacao troca inteira (CR-023, D8); a subpasta dev/
# guarda os scripts de exemplo e e a excecao onde existe (o repositorio; o pacote nao a leva; CR-032, D11).
APP_DIR = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
APP_DEV_DIR = os.path.join(APP_DIR, "dev")
# CR-028 (D3): scripts dos ambientes dentro do projeto, preservados pela atualizacao (bin/sss-update.sh), em
# DEV, HML e PROD.
APP_SCRIPTS_DIR = os.path.join(APP_DIR, "scripts_ambiente")


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
    # CR-025/CR-026: o interpretador escolhido (o digitado, se informado, senao o do cadastro) nao existe ou
    # nao e executavel; formato invalido do digitado; #! ausente ou invalido (so interno: a execucao segue
    # para o digitado e o cadastro).
    INTERPRETER_NOT_FOUND = 'INTERPRETER_NOT_FOUND'
    INTERPRETER_INVALID = 'INTERPRETER_INVALID'
    NO_SHEBANG = 'NO_SHEBANG'


class PathGuardError(Exception):
    """Rejeicao de caminho ou interpretador; a mensagem nunca inclui o caminho."""

    def __init__(self, code):
        Exception.__init__(self, code)
        self.code = code


def validate_interpreter(interpreter):
    """Exige que o interpretador do cadastro seja exatamente um item da ALLOWLIST (CR-026)."""
    if interpreter not in ALLOWLIST:
        raise PathGuardError(Code.INTERPRETER_NOT_ALLOWED)


def registered_name(interpreter: object) -> Optional[str]:
    """Nome do interpretador do cadastro guardado no snapshot (o atual ou a chave anterior ao CR-026)."""
    if interpreter in ALLOWLIST:
        return str(interpreter)
    return LEGACY.get(interpreter) if isinstance(interpreter, str) else None


def is_python(text: Optional[str]) -> bool:
    """True se o executavel (caminho ou nome) e um Python: python, python3, python3.13... (CR-026, D7)."""
    return bool(text) and bool(_RE_PYTHON.match(os.path.basename(str(text))))


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


def check_forbidden_dirs(path_file: str, sss_dirs: Iterable[Optional[str]] = ()) -> None:
    """Recusa pastas do sistema, as do SSS (log_dir, work_dir...) e a da aplicacao (salvo dev/ onde ela existe,
    CR-023 D8 e CR-032 D11), no caminho digitado e no resolvido (symlink). Caminho relativo: nada a conferir."""
    if is_relative(path_file):
        return
    sss = [os_platform.final_path(d) for d in sss_dirs if d]
    dev = os.path.isdir(APP_DEV_DIR)
    for target in (path_file, os_platform.final_path(path_file)):
        if any(_inside(target, d) for d in SYSTEM_DIRS):
            raise PathGuardError(Code.SYSTEM_DIR)
        if any(_inside(target, d) for d in sss):
            raise PathGuardError(Code.SSS_DIR)
        if _inside(target, APP_DIR) and not _inside(target, APP_SCRIPTS_DIR) \
                and not (dev and _inside(target, APP_DEV_DIR)):
            raise PathGuardError(Code.APP_DIR)


def _stat(path):
    """os.stat com EACCES -> NO_ACCESS e ausente -> NOT_FOUND (README §8.5)."""
    try:
        return os.stat(path)
    except OSError as e:
        if e.errno in (errno.EACCES, errno.EPERM):
            raise PathGuardError(Code.NO_ACCESS)
        raise PathGuardError(Code.NOT_FOUND)


def resolve(path_file: str, sss_dirs: Iterable[Optional[str]] = (), base_dir: Optional[str] = None) -> str:
    """Confere o script no servidor do agente e devolve o caminho real, que e o executado (README §8.5, CR-011).

    Formato do caminho cadastrado; o relativo vira base_dir/<relativo> (CR-023; sem base, NO_BASE_DIR) e o
    real pode ficar fora da base; pastas do sistema, do SSS e da aplicacao no caminho e no real; o arquivo
    real existe (NOT_FOUND; ciclo de links tambem), as pastas deixam passar (NO_ACCESS), e arquivo regular
    (NOT_A_FILE) e nao e gravavel por grupo nem por outros (GROUP_OTHER_WRITABLE).
    """
    validate_registration(path_file)
    target = join_base(path_file, base_dir)
    check_forbidden_dirs(target, sss_dirs)
    code = os_platform.validate_script_path(target)
    if code:
        raise PathGuardError(code)
    return os_platform.final_path(target)


def validate_override(text: object) -> None:
    """Formato do interpretador digitado no disparo (CR-025): caminho absoluto sem controle, ou so o nome
    (letras, numeros, '.', '_', '+', '-'). Nao confere se existe: isso e no agente. Formato: INTERPRETER_INVALID."""
    if not isinstance(text, str) or text == '' or len(text) > OVERRIDE_MAX_LENGTH:
        raise PathGuardError(Code.INTERPRETER_INVALID)
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise PathGuardError(Code.INTERPRETER_INVALID)
    if '/' in text:
        if text[:1] != '/':
            raise PathGuardError(Code.INTERPRETER_INVALID)
    elif not _RE_INTERPRETER_NAME.match(text):
        raise PathGuardError(Code.INTERPRETER_INVALID)


def find_executable(text: str, search_path: Optional[str]) -> str:
    """Executavel do interpretador digitado ou do #! (CR-025): caminho absoluto como esta, ou o nome buscado
    em search_path (o PATH do agente). Conferencia minima no caminho real: existe e e executavel; senao,
    INTERPRETER_NOT_FOUND. Devolve o caminho sem resolver links: o Python de um virtualenv
    (/opt/venv/bin/python3, link) acha o venv pelo caminho com que foi chamado."""
    validate_override(text)
    candidate = text if '/' in text else shutil.which(text, path=search_path or os.defpath)
    if not candidate:
        raise PathGuardError(Code.INTERPRETER_NOT_FOUND)
    real = os_platform.final_path(candidate)
    if not os.path.isfile(real) or not os.access(real, os.X_OK):
        raise PathGuardError(Code.INTERPRETER_NOT_FOUND)
    return candidate if "/" in text else os.path.abspath(candidate)


def read_shebang(script_real: str) -> Tuple[str, Optional[str]]:
    """(caminho, argumento opcional) do #! da primeira linha do script (CR-025), como o Linux interpreta:
    um caminho absoluto e, no maximo, um argumento. Sem #! valido: NO_SHEBANG."""
    try:
        with open(script_real, 'rb') as handle:
            head = handle.read(SHEBANG_MAX_BYTES)
    except OSError:
        raise PathGuardError(Code.NOT_FOUND)
    first = head.split(b'\n', 1)[0].rstrip(b'\r')
    if first[:2] != b'#!':
        raise PathGuardError(Code.NO_SHEBANG)
    try:
        rest = first[2:].decode('utf-8').strip()
    except UnicodeDecodeError:
        raise PathGuardError(Code.NO_SHEBANG)
    parts = rest.split(None, 1)
    if not parts or parts[0][:1] != '/':
        raise PathGuardError(Code.NO_SHEBANG)
    return parts[0], (parts[1].strip() if len(parts) > 1 else None)
