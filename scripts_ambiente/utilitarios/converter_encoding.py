#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utilitario SSS: Converte codificacao de caracteres de arquivo texto."""
import argparse
import os
import sys
import time


def parse_args():
    parser = argparse.ArgumentParser(description="Converte codificacao de arquivo texto.")
    parser.add_argument("--origem", required=True, help="Arquivo texto de origem")
    parser.add_argument("--destino", required=True, help="Arquivo texto de destino")
    parser.add_argument("--enc-origem", default="ISO-8859-1", help="Codificacao atual (ex: ISO-8859-1, UTF-8, CP1252)")
    parser.add_argument("--enc-destino", default="UTF-8", help="Nova codificacao (ex: UTF-8, ISO-8859-1)")
    return parser.parse_args()


def main():
    args = parse_args()
    origem = os.path.abspath(args.origem)
    destino = os.path.abspath(args.destino)
    enc_orig = args.enc_origem.strip()
    enc_dest = args.enc_destino.strip()

    if not os.path.isfile(origem):
        sys.stderr.write("ERRO: Arquivo de origem nao encontrado: %s\n" % origem)
        return 1

    dest_dir = os.path.dirname(destino)
    if dest_dir and not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    print("Iniciando conversao de codificacao:")
    print("  Origem: %s (encoding: %s)" % (origem, enc_orig))
    print("  Destino: %s (encoding: %s)" % (destino, enc_dest))

    inicio = time.time()
    linhas_processadas = 0

    try:
        with open(origem, "r", encoding=enc_orig, errors="replace") as f_in, \
             open(destino, "w", encoding=enc_dest, errors="replace") as f_out:
            for linha in f_in:
                f_out.write(linha)
                linhas_processadas += 1

        duracao = time.time() - inicio
        tam_orig = os.path.getsize(origem)
        tam_dest = os.path.getsize(destino)

        print("Conversao concluida com sucesso!")
        print("  Linhas convertidas:  %d" % linhas_processadas)
        print("  Tamanho original:    %d bytes" % tam_orig)
        print("  Tamanho final:       %d bytes" % tam_dest)
        print("  Tempo decorrido:     %.2fs" % duracao)
        return 0
    except Exception as exc:
        sys.stderr.write("ERRO durante a conversao: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
