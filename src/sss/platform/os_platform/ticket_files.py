# -*- coding: utf-8 -*-
"""Operacoes de arquivo das pastas do ticket (CR-012, CR-014, CR-020c; README §8.13 e §8.14), rodadas pelo agente
num processo proprio, com a conta do agente (CR-032, D7: sem sudo nem usuario de execucao).

O agente chama "sys.executable -I <este arquivo> <subcomando>" sem esperar (o daemon nao pode ter threads) e
acompanha por popen.poll(). So biblioteca padrao: nao importa a aplicacao nem le o config.ini. Valida os proprios
argumentos.

Subcomandos:
  pack <base> <relativo> <max_bytes> <max_arquivos>
                                              zip da pasta de saida do ticket na saida padrao (CR-012)
  clean-output <base> <relativo>              remove a pasta de saida do ticket sem seguir links (CR-012)
  put-input <base> <script> <subpasta|-> <nome> <Y|N> <sha256> <bytes>
                                              grava o arquivo da entrada padrao na pasta de entrada do
                                              script (CR-020c): temporario no destino, hash conferido e
                                              publicacao atomica (sem substituir: link; substituindo: replace)
  list-input <base> <script> <max_itens>      retrato JSON da pasta de entrada do script, sem seguir links

Codigos de saida: 0 sucesso, 2 uso invalido, 4 erro do sistema, 6 pasta de saida vazia ou inexistente, 7 saida
acima do limite de arquivos, 8 saida acima do limite de bytes (pack), 9 arquivo ja existe, 10 sem espaco, 11 hash
ou tamanho divergente (put-input). Mensagens so no stderr, sem valores sensiveis.
"""
import datetime
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
import zipfile
from typing import Any, BinaryIO, Dict, List, Optional, Tuple

INVALID_USAGE = 2
SYSTEM_ERROR = 4
OUTPUT_EMPTY = 6
OUTPUT_TOO_MANY_FILES = 7
OUTPUT_TOO_MANY_BYTES = 8
INPUT_EXISTS = 9
INPUT_SPACE = 10
INPUT_HASH = 11

# Pasta de saida (CR-012, README §8.13): base = output_dir/<ambiente>; relativo = pasta do script (forma
# segura de pastas_log.pasta_script), AAAA/MM/DD/HH/MI e ticket_<id>.
_RE_SCRIPT_DIR = re.compile(r"^[a-z0-9-][a-z0-9._-]{0,199}$")
_RE_MINUTE_RELATIVE = re.compile(r"^\d{4}/\d{2}/\d{2}/\d{2}/\d{2}$")
_RE_TICKET = re.compile(r"^ticket_[1-9]\d{0,9}$")
_CHUNK = 64 * 1024
_MAX_OUTPUT_BYTES = 209715200
_MAX_OUTPUT_FILES = 10000
_MTIME_MIN = 315705600  # 1980-01-03 UTC: o zip nao aceita datas anteriores a 1980 em nenhum fuso

# Pasta de entrada pela tela (CR-020c): cada nivel da subpasta e o nome do arquivo.
_RE_INPUT_PART = re.compile(r"^[^/\x00-\x1f\x7f]{1,255}$")
_RE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_INPUT_MAX_DEPTH = 10
_INPUT_MAX_BYTES = 1073741824
_INPUT_MAX_ITEMS = 10000
_INPUT_COUNT_CAP = 100000
INPUT_TMP_PREFIX = ".sss_upload_"


class Failure(Exception):
    def __init__(self, code: int, message: str) -> None:
        Exception.__init__(self, message)
        self.code = code


def _error(code: int, message: str) -> Any:
    raise Failure(code, message)


def _integer(text: str, name: str, minimum: int = 0, maximum: Optional[int] = None) -> int:
    if not isinstance(text, str) or not text.isdigit():
        _error(INVALID_USAGE, "%s invalido" % name)
    value = int(text)
    if value < minimum or (maximum is not None and value > maximum):
        _error(INVALID_USAGE, "%s fora da faixa" % name)
    return value


def _base_dir(path: str, name: str = "base_dir") -> str:
    """output_dir/<ambiente> ou input_dir/<ambiente>: absoluta, normalizada, sem link e do proprio usuario
    (CR-008, R-36; CR-012)."""
    if not isinstance(path, str) or not path.startswith("/") or os.path.normpath(path) != path:
        _error(INVALID_USAGE, "%s deve ser absoluta e normalizada" % name)
    if os.path.realpath(path) != path:
        _error(INVALID_USAGE, "%s nao pode ter link simbolico" % name)
    try:
        st = os.lstat(path)
    except OSError:
        _error(INVALID_USAGE, "%s inexistente" % name)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid():
        _error(INVALID_USAGE, "%s deve ser um diretorio do proprio usuario" % name)
    return path


def _relative_parts(relative: str) -> List[str]:
    """<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id> com exatamente esse formato (CR-012)."""
    if not isinstance(relative, str):
        _error(INVALID_USAGE, "relativo invalido")
    parts = relative.split("/")
    if len(parts) != 7 or not _RE_SCRIPT_DIR.match(parts[0]) \
            or not _RE_MINUTE_RELATIVE.match("/".join(parts[1:6])) or not _RE_TICKET.match(parts[6]):
        _error(INVALID_USAGE, "relativo fora do formato <script>/AAAA/MM/DD/HH/MI/ticket_<id>")
    return parts


def _own_directory(path: str) -> bool:
    """True se caminho e diretorio do proprio usuario (sem seguir link); False se nao existe."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid():
        _error(INVALID_USAGE, "item do caminho da saida nao e diretorio do proprio usuario")
    return True


def _output_dir(base: str, relative: str, create: bool = False) -> Optional[str]:
    """Pasta de saida (ou de trabalho, CR-019) do ticket, conferida nivel a nivel sem seguir links; criar=True
    cria com 0700.

    Devolve o caminho, ou None se algum nivel nao existir (e criar=False).
    """
    current = _base_dir(base, "base")
    for part in _relative_parts(relative):
        current = os.path.join(current, part)
        if _own_directory(current):
            continue
        if not create:
            return None
        try:
            os.mkdir(current, 0o700)
        except FileExistsError:  # criado por outro caminho entre o lstat e o mkdir: conferido abaixo
            pass
        if not _own_directory(current):
            _error(SYSTEM_ERROR, "pasta de saida nao foi criada")
        os.chmod(current, 0o700)
    return current


# -----------------------------------------------------------------------------
# Pasta de saida (CR-012)
# -----------------------------------------------------------------------------

class _CountedOutput(object):
    """Saida padrao sem seek. Ao passar de max_bytes, marca excedeu e descarta o resto: o laco para e o zip
    fecha normalmente (o zipfile da 3.6 nao fecha com um handle de escrita aberto apos erro)."""

    def __init__(self, destination: BinaryIO, max_bytes: int) -> None:
        self.destination = destination
        self.max_bytes = max_bytes
        self.written = 0
        self.exceeded = False

    def write(self, date: bytes) -> int:
        if not self.exceeded:
            self.written += len(date)
            if self.written > self.max_bytes:
                self.exceeded = True
            else:
                self.destination.write(date)
        return len(date)

    def flush(self) -> None:
        self.destination.flush()


def _output_files(folder: str, max_files: int) -> List[Tuple[str, str]]:
    """[(caminho, nome_relativo)] dos arquivos regulares, sem seguir links; acima do limite: codigo 7."""
    files = []
    for root, dirs, names in os.walk(folder, followlinks=False):
        dirs.sort()
        for name in sorted(names):
            path = os.path.join(root, name)
            try:
                if not stat.S_ISREG(os.lstat(path).st_mode):
                    continue  # link, socket, fifo ou dispositivo: fora do zip
            except OSError:  # o script apagou o arquivo durante a varredura
                continue
            files.append((path, os.path.relpath(path, folder)))
            if len(files) > max_files:
                _error(OUTPUT_TOO_MANY_FILES, "saida acima do limite de arquivos")
    return files


def _pack(base: str, relative: str, max_bytes: int, max_files: int,
          destination: Optional[BinaryIO] = None) -> int:
    """Zip (ZIP_DEFLATED) da pasta de saida na saida padrao. Vazia: 6; arquivos: 7; bytes: 8."""
    dir_value = _output_dir(base, relative)
    if dir_value is None:
        raise Failure(OUTPUT_EMPTY, "pasta de saida inexistente")
    files = _output_files(dir_value, max_files)
    if not files:
        _error(OUTPUT_EMPTY, "pasta de saida vazia")
    output: Any = _CountedOutput(destination or sys.stdout.buffer, max_bytes)
    try:
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
            for path, name in files:
                try:
                    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                except OSError:  # apagado ou trocado por link depois da varredura: fica de fora
                    continue
                with os.fdopen(fd, "rb") as f:
                    st = os.fstat(f.fileno())
                    if not stat.S_ISREG(st.st_mode):
                        continue
                    info = zipfile.ZipInfo(name, time.localtime(max(st.st_mtime, _MTIME_MIN))[:6])
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o600 << 16
                    with z.open(info, "w") as dst:
                        while not output.exceeded:
                            chunk = f.read(_CHUNK)
                            if not chunk:
                                break
                            dst.write(chunk)
                if output.exceeded:
                    break
        output.flush()
    except OSError as e:
        _error(SYSTEM_ERROR, "empacotamento falhou (%s)" % e.__class__.__name__)
    if output.exceeded:
        _error(OUTPUT_TOO_MANY_BYTES, "saida acima do limite de bytes")
    return 0


def _clean_output(base: str, relative: str) -> int:
    """Remove a pasta de saida do ticket sem seguir links simbolicos (as pastas acima ficam; limpeza manual, README §11.3)."""
    dir_value = _output_dir(base, relative)
    if dir_value is None:
        return 0
    try:
        shutil.rmtree(dir_value)  # rmtree nao segue links simbolicos internos (remove o proprio link)
    except OSError as e:
        _error(SYSTEM_ERROR, "limpeza da saida falhou (%s)" % e.__class__.__name__)
    return 0


# -----------------------------------------------------------------------------
# put-input / list-input (CR-020c, README §8.14)
# -----------------------------------------------------------------------------

def _input_part(text: str) -> str:
    """Um nivel da subpasta ou o nome do arquivo: sem '/', controle, '.' no inicio nem mais de 255 caracteres."""
    if not isinstance(text, str) or not _RE_INPUT_PART.match(text) or text.startswith("."):
        _error(INVALID_USAGE, "nome ou subpasta fora do formato")
    return text


def _input_folder(base: str, script: str, relative: str, create: bool) -> Optional[str]:
    """Pasta do script e subpastas, conferidas nivel a nivel sem seguir links; create=True cria com 0700."""
    if not isinstance(script, str) or not _RE_SCRIPT_DIR.match(script):
        _error(INVALID_USAGE, "pasta do script fora do formato")
    parts = [] if relative == "-" else relative.split("/")
    if len(parts) > _INPUT_MAX_DEPTH:
        _error(INVALID_USAGE, "subpasta com niveis demais")
    current = _base_dir(base, "base")
    for part in [script] + [_input_part(p) for p in parts]:
        current = os.path.join(current, part)
        if _own_directory(current):
            continue
        if not create:
            return None
        try:
            os.mkdir(current, 0o700)
        except FileExistsError:  # criada por outro caminho entre o lstat e o mkdir: conferida abaixo
            pass
        if not _own_directory(current):
            _error(SYSTEM_ERROR, "pasta de entrada nao foi criada")
    return current


def _put_input(base: str, script: str, relative: str, name: str, replace: str, sha256: str, size: int,
               source: Optional[BinaryIO] = None) -> int:
    """Grava a entrada padrao em <base>/<script>/<subpasta>/<nome>: temporario O_EXCL no destino, hash e tamanho
    conferidos, publicacao atomica. Sem substituir, um item ja existente (de qualquer tipo) e INPUT_EXISTS."""
    _input_part(name)
    if replace not in ("Y", "N") or not isinstance(sha256, str) or not _RE_SHA256.match(sha256):
        _error(INVALID_USAGE, "substituicao ou hash fora do formato")
    folder = _input_folder(base, script, relative, create=True)
    if folder is None:
        raise Failure(SYSTEM_ERROR, "pasta de entrada nao foi criada")
    final = os.path.join(folder, name)
    tmp = os.path.join(folder, "%s%d.tmp" % (INPUT_TMP_PREFIX, os.getpid()))
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError as e:
        _error(SYSTEM_ERROR, "temporario nao foi criado (%s)" % e.__class__.__name__)
    digest, written = hashlib.sha256(), 0
    stream = source or sys.stdin.buffer
    try:
        try:
            while True:
                chunk = stream.read(_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                written += len(chunk)
                if written > size:
                    break
                os.write(fd, chunk)
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as e:
        os.unlink(tmp)
        if e.errno in (errno.ENOSPC, errno.EDQUOT):
            _error(INPUT_SPACE, "sem espaco na pasta de entrada")
        _error(SYSTEM_ERROR, "gravacao falhou (%s)" % e.__class__.__name__)
    if written != size or digest.hexdigest() != sha256:
        os.unlink(tmp)
        _error(INPUT_HASH, "tamanho ou hash divergente")
    if replace == "N":
        try:
            os.link(tmp, final)
        except FileExistsError:
            os.unlink(tmp)
            _error(INPUT_EXISTS, "o arquivo ja existe")
        os.unlink(tmp)
    else:
        try:
            st = os.lstat(final)
        except FileNotFoundError:
            st = None
        if st is not None and not stat.S_ISREG(st.st_mode):
            os.unlink(tmp)
            _error(INVALID_USAGE, "o destino existe e nao e arquivo regular")
        os.replace(tmp, final)
    sys.stdout.write("gravado=%d\n" % written)
    return 0


def _list_input(base: str, script: str, max_items: int) -> int:
    """Retrato JSON da pasta do script: {files: [{path, size, mtime}], count, truncated}, por caminho, sem seguir
    links e sem os temporarios do put-input. Pasta ainda inexistente: vazia."""
    folder = _input_folder(base, script, "-", create=False)
    files: List[Dict[str, Any]] = []
    count = 0
    pending = [(folder, "")] if folder else []
    while pending and count < _INPUT_COUNT_CAP:
        current, prefix = pending.pop()
        try:
            entries = sorted(os.scandir(current), key=lambda e: e.name)
        except OSError:  # pasta removida ou sem permissao durante a varredura
            continue
        for entry in entries:
            if entry.name.startswith(INPUT_TMP_PREFIX):
                continue
            rel = prefix + entry.name
            if entry.is_dir(follow_symlinks=False):
                pending.append((entry.path, rel + "/"))
            elif entry.is_file(follow_symlinks=False):
                count += 1
                if len(files) < max_items:
                    st = entry.stat(follow_symlinks=False)
                    files.append({"path": rel, "size": st.st_size,
                                  "mtime": datetime.datetime.fromtimestamp(int(st.st_mtime)).strftime("%Y-%m-%d %H:%M:%S")})
    files.sort(key=lambda f: f["path"])
    sys.stdout.write(json.dumps({"files": files, "count": count, "truncated": count > len(files)}) + "\n")
    return 0


def run_main(argv: List[str]) -> int:
    if not argv:
        _error(INVALID_USAGE, "subcomando ausente")
    sub, args = argv[0], argv[1:]
    if sub == "pack" and len(args) == 4:
        return _pack(args[0], args[1], _integer(args[2], "max_bytes", minimum=1, maximum=_MAX_OUTPUT_BYTES),
                          _integer(args[3], "max_arquivos", minimum=1, maximum=_MAX_OUTPUT_FILES))
    if sub == "clean-output" and len(args) == 2:
        return _clean_output(args[0], args[1])
    if sub == "put-input" and len(args) == 7:
        return _put_input(args[0], args[1], args[2], args[3], args[4], args[5],
                          _integer(args[6], "bytes", maximum=_INPUT_MAX_BYTES))
    if sub == "list-input" and len(args) == 3:
        return _list_input(args[0], args[1], _integer(args[2], "max_itens", minimum=1, maximum=_INPUT_MAX_ITEMS))
    raise Failure(INVALID_USAGE, "uso invalido")


def main() -> int:
    try:
        return run_main(sys.argv[1:])
    except Failure as f:
        sys.stderr.write("ticket_files: %s\n" % f)
        return f.code
    except Exception as e:  # noqa: BLE001 - nenhum traceback com dados sai daqui
        sys.stderr.write("ticket_files: erro inesperado (%s)\n" % e.__class__.__name__)
        return SYSTEM_ERROR


if __name__ == "__main__":
    sys.exit(main())
