# -*- coding: utf-8 -*-
"""Operacoes de arquivo da pasta de arquivos (CR-037, README §8.16 e §5.11), usadas pelo web.

So POSIX e so a biblioteca padrao. Nenhuma operacao segue link simbolico: cada nivel e conferido
com lstat (diretorio do proprio usuario) e os arquivos sao abertos com O_NOFOLLOW. O envio vai para
um temporario na pasta de destino (O_EXCL, 0600) e so aparece no nome final no fim: por link (sem
substituir; falha se o nome ja existe) ou por rename (substituindo). O conteudo nunca passa inteiro
pela memoria.
"""
import hashlib
import os
import stat
from typing import BinaryIO, Iterator, List, NamedTuple, Optional, Sequence, Tuple

CHUNK_BYTES = 1048576
_TMP_PREFIX = ".sss_files_"

Entry = NamedTuple("Entry", [("name", str), ("size", int), ("mtime", float)])


class AreaError(Exception):
    """Item fora do formato esperado (link, nao diretorio, de outro dono): a tela responde 404."""


class FileExists(Exception):
    """O nome final ja existe e o envio nao pediu para substituir."""


class TooLarge(Exception):
    """O arquivo passou do limite enquanto era copiado (o temporario foi apagado)."""


def _own_dir(path: str) -> bool:
    st = os.lstat(path)
    return stat.S_ISDIR(st.st_mode) and st.st_uid == os.geteuid()


def walk_dirs(root: str, parts: Sequence[str], create: bool = False) -> Optional[str]:
    """Caminho de root/parts, nivel a nivel, sem seguir link.

    root e criada (0700) com create; os niveis que faltam tambem; sem create, devolve None. Link,
    arquivo no lugar ou dono diferente: AreaError.
    """
    if not os.path.lexists(root):
        if not create:
            return None
        os.makedirs(root, 0o700, exist_ok=True)
    if not _own_dir(root):
        raise AreaError("raiz da pasta de arquivos fora do formato")
    current = root
    for part in parts:
        current = os.path.join(current, part)
        if not os.path.lexists(current):
            if not create:
                return None
            try:
                os.mkdir(current, 0o700)
            except FileExistsError:  # fluxo previsto: criada ao mesmo tempo por outro envio
                pass
        if not _own_dir(current):
            raise AreaError("nivel da pasta de arquivos fora do formato")
    return current


def list_dir(path: str) -> Tuple[List[str], List[Entry]]:
    """(subpastas, arquivos regulares) do diretorio, por nome.

    Links, temporarios do envio e itens especiais ficam fora.
    """
    folders: List[str] = []
    files: List[Entry] = []
    for name in sorted(os.listdir(path)):
        if name.startswith(_TMP_PREFIX):
            continue
        try:
            st = os.lstat(os.path.join(path, name))
        except FileNotFoundError:  # fluxo previsto: apagado durante a leitura
            continue
        if stat.S_ISDIR(st.st_mode):
            folders.append(name)
        elif stat.S_ISREG(st.st_mode):
            files.append(Entry(name, st.st_size, st.st_mtime))
    return folders, files


def write_file(folder: str, name: str, source: BinaryIO, max_bytes: int,
               replace: bool) -> Tuple[int, str]:
    """Copia source em blocos para folder/name e devolve (bytes, sha256).

    Sem substituir, o nome que ja existe da FileExists; acima de max_bytes, TooLarge. O temporario
    sai em qualquer falha.
    """
    final = os.path.join(folder, name)
    if os.path.lexists(final):
        if not stat.S_ISREG(os.lstat(final).st_mode):
            raise AreaError("o nome final nao e um arquivo comum")
        if not replace:
            raise FileExists(name)
    temp = os.path.join(folder, "%s%d_%s.tmp" % (_TMP_PREFIX, os.getpid(), os.urandom(6).hex()))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    digest = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = source.read(CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise TooLarge(name)
                digest.update(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        if replace:
            os.replace(temp, final)
        else:
            try:
                os.link(temp, final)
            except FileExistsError:  # fluxo previsto: o nome apareceu depois da conferencia
                raise FileExists(name)
            os.unlink(temp)
    except BaseException:
        try:
            os.unlink(temp)
        except FileNotFoundError:  # fluxo previsto: ja renomeado ou nunca criado por completo
            pass
        raise
    return size, digest.hexdigest()


def open_file(folder: str, name: str) -> Tuple[BinaryIO, int]:
    """(arquivo aberto, tamanho): so arquivo comum, sem seguir link; senao AreaError."""
    try:
        fd = os.open(os.path.join(folder, name), os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:  # fluxo previsto: inexistente ou link (O_NOFOLLOW); a tela da 404
        raise AreaError("arquivo inexistente ou link")
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        raise AreaError("nao e um arquivo comum")
    return os.fdopen(fd, "rb"), st.st_size


def tree_files(folder: str) -> Iterator[Tuple[str, str]]:
    """(caminho, nome relativo) dos arquivos comuns abaixo de folder, por nome.

    Nao segue links e pula os temporarios do envio.
    """
    for root, dirs, names in os.walk(folder, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not os.path.islink(os.path.join(root, d)))
        for name in sorted(names):
            path = os.path.join(root, name)
            if name.startswith(_TMP_PREFIX):
                continue
            try:
                if not stat.S_ISREG(os.lstat(path).st_mode):
                    continue
            except FileNotFoundError:  # fluxo previsto: apagado durante a varredura
                continue
            yield path, os.path.relpath(path, folder)
