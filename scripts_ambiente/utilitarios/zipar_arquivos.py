#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utilitario SSS: Compacta arquivo ou pasta em arquivo ZIP.

O nivel de compressao (--nivel, 1 a 9) vale em qualquer versao do Python: no 3.7+ pelo
``compresslevel`` do zipfile; no 3.6, cujo zipfile nao aceita o nivel, por um gravador proprio
(_GravadorZip36) que comprime em blocos com zlib.compressobj(nivel, DEFLATED, -15) e escreve os
cabecalhos do formato ZIP com struct (CRC32, tamanhos, ZIP_DEFLATED e zip64 quando preciso).
"""
import argparse
import os
import struct
import sys
import time
import zipfile
import zlib

NIVEL_MIN = 1
NIVEL_MAX = 9
_BLOCO = 1024 * 1024

# Formato ZIP (APPNOTE.TXT), os mesmos layouts do zipfile da biblioteca padrao
_LIMITE_ZIP64 = (1 << 31) - 1  # o zipfile passa para zip64 acima deste valor
_LIMITE_ENTRADAS = (1 << 16) - 1
_SIG_LOCAL = b"PK\x03\x04"
_SIG_CENTRAL = b"PK\x01\x02"
_SIG_FIM = b"PK\x05\x06"
_SIG_FIM64 = b"PK\x06\x06"
_SIG_LOCALIZADOR64 = b"PK\x06\x07"
_FMT_LOCAL = "<4s2B4HL2L2H"
_FMT_CENTRAL = "<4s4B4HL2L5H2L"
_FMT_FIM = "<4s4H2LH"
_FMT_FIM64 = "<4sQ2H2L4Q"
_FMT_LOCALIZADOR64 = "<4sLQL"
_VERSAO_DEFLATE = 20
_VERSAO_ZIP64 = 45
_SISTEMA_UNIX = 3
_FLAG_UTF8 = 0x800


def _nivel(valor):
    """Tipo do argparse para --nivel: inteiro de 1 a 9 (fora disso o argparse sai com 2)."""
    try:
        nivel = int(valor)
    except ValueError:
        nivel = None
    if nivel is None or not NIVEL_MIN <= nivel <= NIVEL_MAX:
        raise argparse.ArgumentTypeError(
            "nivel de compressao invalido: %r (use um inteiro de %d a %d)" % (valor, NIVEL_MIN, NIVEL_MAX))
    return nivel


def parse_args():
    parser = argparse.ArgumentParser(description="Compacta arquivos ou pastas em arquivo ZIP.")
    parser.add_argument("--origem", required=True, help="Caminho do arquivo ou diretorio a ser compactado")
    parser.add_argument("--destino", required=True, help="Caminho do arquivo .zip a ser criado")
    parser.add_argument("--nivel", type=_nivel, default=6, help="Nivel de compressao (1 a 9, padrao 6)")
    return parser.parse_args()


def _nome_no_zip(arcname):
    """Normaliza o nome da entrada como o zipfile: sem unidade, sem barra inicial, separador '/'."""
    nome = os.path.normpath(os.path.splitdrive(arcname)[1])
    while nome[0:1] in (os.sep, os.altsep):
        nome = nome[1:]
    if os.sep != "/":
        nome = nome.replace(os.sep, "/")
    if os.altsep:
        nome = nome.replace(os.altsep, "/")
    return nome


class _GravadorZip36(object):
    """Gravador ZIP minimo (so ZIP_DEFLATED) com nivel de compressao, para o Python 3.6.

    Cada entrada: cabecalho local provisorio, dados comprimidos em blocos (sem carregar o arquivo
    na memoria) e cabecalho local reescrito por seek com CRC32 e tamanhos. No fechamento, o
    diretorio central e o fim de arquivo, com os registros zip64 quando os limites sao passados.
    """

    def __init__(self, caminho, nivel):
        self._nivel = nivel
        self._entradas = []
        self._f = open(caminho, "wb")

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, tb):
        if tipo is None:
            self.close()
        else:
            self._f.close()
        return False

    def write(self, caminho, arcname):
        st = os.stat(caminho)
        nome = _nome_no_zip(arcname)
        try:
            nome_b = nome.encode("ascii")
            flags = 0
        except UnicodeEncodeError:
            nome_b = nome.encode("utf-8")
            flags = _FLAG_UTF8
        ano, mes, dia, hora, minuto, segundo = time.localtime(st.st_mtime)[0:6]
        if ano < 1980:
            raise ValueError("ZIP nao suporta datas anteriores a 1980: %s" % caminho)
        data_dos = (ano - 1980) << 9 | mes << 5 | dia
        hora_dos = hora << 11 | minuto << 5 | segundo // 2
        zip64 = st.st_size * 1.05 > _LIMITE_ZIP64
        offset = self._f.tell()
        self._f.write(self._cabecalho_local(nome_b, flags, hora_dos, data_dos, 0, 0, 0, zip64))

        crc = 0
        tam = 0
        tam_comp = 0
        compressor = zlib.compressobj(self._nivel, zlib.DEFLATED, -15)
        with open(caminho, "rb") as origem:
            while True:
                bloco = origem.read(_BLOCO)
                if not bloco:
                    break
                tam += len(bloco)
                crc = zlib.crc32(bloco, crc)
                dados = compressor.compress(bloco)
                tam_comp += len(dados)
                self._f.write(dados)
        dados = compressor.flush()
        tam_comp += len(dados)
        self._f.write(dados)
        crc &= 0xFFFFFFFF
        if not zip64 and (tam > _LIMITE_ZIP64 or tam_comp > _LIMITE_ZIP64):
            raise RuntimeError("arquivo cresceu durante a compactacao: %s" % caminho)

        fim = self._f.tell()
        self._f.seek(offset)
        self._f.write(self._cabecalho_local(nome_b, flags, hora_dos, data_dos, crc, tam_comp, tam, zip64))
        self._f.seek(fim)
        self._entradas.append((nome_b, flags, hora_dos, data_dos, crc, tam_comp, tam, offset,
                               (st.st_mode & 0xFFFF) << 16))

    @staticmethod
    def _cabecalho_local(nome_b, flags, hora_dos, data_dos, crc, tam_comp, tam, zip64):
        if zip64:
            extra = struct.pack("<HHQQ", 1, 16, tam, tam_comp)
            versao = _VERSAO_ZIP64
            tam_comp = tam = 0xFFFFFFFF
        else:
            extra = b""
            versao = _VERSAO_DEFLATE
        cab = struct.pack(_FMT_LOCAL, _SIG_LOCAL, versao, 0, flags, zipfile.ZIP_DEFLATED, hora_dos,
                          data_dos, crc, tam_comp, tam, len(nome_b), len(extra))
        return cab + nome_b + extra

    def close(self):
        inicio_central = self._f.tell()
        for nome_b, flags, hora_dos, data_dos, crc, tam_comp, tam, offset, attr in self._entradas:
            campos64 = []
            if tam > _LIMITE_ZIP64:
                campos64.append(tam)
                tam = 0xFFFFFFFF
            if tam_comp > _LIMITE_ZIP64:
                campos64.append(tam_comp)
                tam_comp = 0xFFFFFFFF
            if offset > _LIMITE_ZIP64:
                campos64.append(offset)
                offset = 0xFFFFFFFF
            if campos64:
                extra = struct.pack("<HH" + "Q" * len(campos64), 1, 8 * len(campos64), *campos64)
                versao = _VERSAO_ZIP64
            else:
                extra = b""
                versao = _VERSAO_DEFLATE
            self._f.write(struct.pack(_FMT_CENTRAL, _SIG_CENTRAL, versao, _SISTEMA_UNIX, versao, 0,
                                      flags, zipfile.ZIP_DEFLATED, hora_dos, data_dos, crc, tam_comp,
                                      tam, len(nome_b), len(extra), 0, 0, 0, attr, offset))
            self._f.write(nome_b)
            self._f.write(extra)
        fim_central = self._f.tell()
        total = len(self._entradas)
        tam_central = fim_central - inicio_central
        if total > _LIMITE_ENTRADAS or inicio_central > _LIMITE_ZIP64 or tam_central > _LIMITE_ZIP64:
            self._f.write(struct.pack(_FMT_FIM64, _SIG_FIM64, 44, _VERSAO_ZIP64, _VERSAO_ZIP64, 0, 0,
                                      total, total, tam_central, inicio_central))
            self._f.write(struct.pack(_FMT_LOCALIZADOR64, _SIG_LOCALIZADOR64, 0, fim_central, 1))
            total = min(total, 0xFFFF)
            tam_central = min(tam_central, 0xFFFFFFFF)
            inicio_central = min(inicio_central, 0xFFFFFFFF)
        self._f.write(struct.pack(_FMT_FIM, _SIG_FIM, 0, 0, total, total, tam_central, inicio_central, 0))
        self._f.close()


def _abrir_zip(destino, nivel):
    """Abre o ZIP de saida aplicando o nivel: compresslevel no 3.7+, gravador proprio no 3.6."""
    if sys.version_info >= (3, 7):
        return zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=nivel)
    return _GravadorZip36(destino, nivel)


def main():
    args = parse_args()
    origem = os.path.abspath(args.origem)
    destino = os.path.abspath(args.destino)

    if not os.path.exists(origem):
        sys.stderr.write("ERRO: Origem nao encontrada: %s\n" % origem)
        return 1

    dest_dir = os.path.dirname(destino)
    if dest_dir and not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    print("Iniciando compactacao ZIP:")
    print("  Origem:  %s" % origem)
    print("  Destino: %s" % destino)
    print("  Nivel:   %d" % args.nivel)

    inicio = time.time()
    total_arquivos = 0
    total_bytes_orig = 0

    try:
        with _abrir_zip(destino, args.nivel) as zf:
            if os.path.isfile(origem):
                nome_arc = os.path.basename(origem)
                zf.write(origem, arcname=nome_arc)
                total_arquivos = 1
                total_bytes_orig = os.path.getsize(origem)
            else:
                for raiz, _, arquivos in os.walk(origem):
                    for arq in arquivos:
                        caminho_completo = os.path.join(raiz, arq)
                        relativo = os.path.relpath(caminho_completo, origem)
                        zf.write(caminho_completo, arcname=relativo)
                        total_arquivos += 1
                        total_bytes_orig += os.path.getsize(caminho_completo)

        duracao = time.time() - inicio
        bytes_zip = os.path.getsize(destino)
        taxa = ((1.0 - (float(bytes_zip) / float(total_bytes_orig))) * 100.0) if total_bytes_orig > 0 else 0.0

        print("Compactacao concluida com sucesso!")
        print("  Arquivos arquivados: %d" % total_arquivos)
        print("  Tamanho original:    %d bytes" % total_bytes_orig)
        print("  Tamanho compactado:  %d bytes" % bytes_zip)
        print("  Reducao alcancada:   %.2f%%" % taxa)
        print("  Tempo decorrido:     %.2fs" % duracao)
        return 0
    except Exception as exc:
        sys.stderr.write("ERRO durante a compactacao: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
