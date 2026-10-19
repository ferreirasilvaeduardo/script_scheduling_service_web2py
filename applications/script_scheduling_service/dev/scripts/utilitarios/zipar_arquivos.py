#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utilitario SSS: Compacta arquivo ou pasta em arquivo ZIP."""
import argparse
import os
import sys
import time
import zipfile


def parse_args():
    parser = argparse.ArgumentParser(description="Compacta arquivos ou pastas em arquivo ZIP.")
    parser.add_argument("--origem", required=True, help="Caminho do arquivo ou diretorio a ser compactado")
    parser.add_argument("--destino", required=True, help="Caminho do arquivo .zip a ser criado")
    parser.add_argument("--nivel", type=int, default=6, help="Nivel de compressao (1 a 9, padrao 6)")
    return parser.parse_args()


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
        with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=args.nivel) as zf:
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
