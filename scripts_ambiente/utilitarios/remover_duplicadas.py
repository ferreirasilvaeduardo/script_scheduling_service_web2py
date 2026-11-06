#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utilitario SSS: Remove linhas duplicadas de arquivo texto."""
import argparse
import collections
import os
import sys
import time


def parse_args():
    parser = argparse.ArgumentParser(description="Remove linhas duplicadas preservando ordem ou ordenando.")
    parser.add_argument("--origem", required=True, help="Arquivo texto de entrada")
    parser.add_argument("--destino", required=True, help="Arquivo texto de saida sem duplicadas")
    parser.add_argument("--ordenar", default="S", help="Indica se deve ordenar (S) ou manter ordem original (N)")
    return parser.parse_args()


def main():
    args = parse_args()
    origem = os.path.abspath(args.origem)
    destino = os.path.abspath(args.destino)
    ordenar = (args.ordenar.strip().upper() == "S")

    if not os.path.isfile(origem):
        sys.stderr.write("ERRO: Arquivo de origem nao encontrado: %s\n" % origem)
        return 1

    dest_dir = os.path.dirname(destino)
    if dest_dir and not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    print("Iniciando remocao de linhas duplicadas:")
    print("  Origem:  %s" % origem)
    print("  Destino: %s" % destino)
    print("  Ordenar: %s" % ("Sim" if ordenar else "Nao (preservar ordem)"))

    inicio = time.time()
    total_linhas = 0
    linhas_unicas = collections.OrderedDict()

    try:
        with open(origem, "r", encoding="utf-8", errors="replace") as f_in:
            for linha in f_in:
                total_linhas += 1
                if linha not in linhas_unicas:
                    linhas_unicas[linha] = True

        lista_saida = list(linhas_unicas.keys())
        if ordenar:
            lista_saida.sort()

        with open(destino, "w", encoding="utf-8") as f_out:
            for linha in lista_saida:
                f_out.write(linha)

        duracao = time.time() - inicio
        descartadas = total_linhas - len(lista_saida)

        print("Processamento concluido com sucesso!")
        print("  Linhas lidas:       %d" % total_linhas)
        print("  Linhas unicas:      %d" % len(lista_saida))
        print("  Linhas descartadas: %d" % descartadas)
        print("  Tempo decorrido:    %.2fs" % duracao)
        return 0
    except Exception as exc:
        sys.stderr.write("ERRO durante a deduplicacao: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
