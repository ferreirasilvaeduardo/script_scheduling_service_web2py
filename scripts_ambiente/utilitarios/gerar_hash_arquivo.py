#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utilitario SSS: Calcula hash criptografico para verificacao de integridade."""
import argparse
import hashlib
import os
import sys
import time


def parse_args():
    parser = argparse.ArgumentParser(description="Calcula hash SHA256, MD5 ou SHA1 de arquivo.")
    parser.add_argument("--origem", required=True, help="Arquivo a ser verificado")
    parser.add_argument("--algoritmo", default="sha256", choices=["sha256", "md5", "sha1"], help="Algoritmo de hash")
    return parser.parse_args()


def main():
    args = parse_args()
    origem = os.path.abspath(args.origem)
    algo_nome = args.algoritmo.lower().strip()

    if not os.path.isfile(origem):
        sys.stderr.write("ERRO: Arquivo de origem nao encontrado: %s\n" % origem)
        return 1

    print("Iniciando calculo de hash:")
    print("  Arquivo:   %s" % origem)
    print("  Algoritmo: %s" % algo_nome.upper())

    inicio = time.time()
    hasher = getattr(hashlib, algo_nome)()
    total_bytes = 0
    bloco_tam = 64 * 1024

    try:
        with open(origem, "rb") as f_in:
            while True:
                bloco = f_in.read(bloco_tam)
                if not bloco:
                    break
                hasher.update(bloco)
                total_bytes += len(bloco)

        digest = hasher.hexdigest()
        duracao = time.time() - inicio

        print("Calculo concluido com sucesso!")
        print("  Tamanho do arquivo: %d bytes" % total_bytes)
        print("  Hash (%s): %s" % (algo_nome.upper(), digest))
        print("  Tempo decorrido:    %.2fs" % duracao)
        return 0
    except Exception as exc:
        sys.stderr.write("ERRO durante o calculo do hash: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
