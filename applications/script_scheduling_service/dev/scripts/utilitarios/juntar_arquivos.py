#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utilitario SSS: Concatena multiplos arquivos ou blocos ordenados."""
import argparse
import glob
import os
import sys
import time


def parse_args():
    parser = argparse.ArgumentParser(description="Concatena blocos ou partes em um arquivo unico consolidado.")
    parser.add_argument("--padrao-origem", required=True, help="Padrao glob para partes (ex: /tmp/parte_*)")
    parser.add_argument("--destino", required=True, help="Arquivo final de destino")
    return parser.parse_args()


def main():
    args = parse_args()
    padrao = args.padrao_origem
    destino = os.path.abspath(args.destino)

    arquivos = sorted(glob.glob(padrao))
    if not arquivos:
        sys.stderr.write("ERRO: Nenhum arquivo encontrado correspondente ao padrao: %s\n" % padrao)
        return 1

    dest_dir = os.path.dirname(destino)
    if dest_dir and not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    print("Iniciando concatenacao de arquivos:")
    print("  Padrao:  %s" % padrao)
    print("  Destino: %s" % destino)
    print("  Total de partes encontradas: %d" % len(arquivos))

    inicio = time.time()
    total_bytes = 0
    buffer_size = 64 * 1024

    try:
        with open(destino, "wb") as f_out:
            for arq in arquivos:
                print("  Processando: %s" % arq)
                with open(arq, "rb") as f_in:
                    while True:
                        bloco = f_in.read(buffer_size)
                        if not bloco:
                            break
                        f_out.write(bloco)
                        total_bytes += len(bloco)

        duracao = time.time() - inicio
        print("Concatenacao concluida com sucesso!")
        print("  Partes consolidadas: %d" % len(arquivos))
        print("  Tamanho final:       %d bytes" % total_bytes)
        print("  Tempo decorrido:     %.2fs" % duracao)
        return 0
    except Exception as exc:
        sys.stderr.write("ERRO durante a concatenacao: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
