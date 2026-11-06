#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utilitario SSS: Localiza e substitui texto em arquivo."""
import argparse
import os
import sys
import time


def parse_args():
    parser = argparse.ArgumentParser(description="Substitui ocorrencias de texto em arquivo.")
    parser.add_argument("--origem", required=True, help="Arquivo de entrada")
    parser.add_argument("--destino", required=True, help="Arquivo de saida modificado")
    parser.add_argument("--busca", required=True, help="Texto a ser localizado")
    parser.add_argument("--substituicao", required=True, help="Texto substituto")
    return parser.parse_args()


def main():
    args = parse_args()
    origem = os.path.abspath(args.origem)
    destino = os.path.abspath(args.destino)
    busca = args.busca
    subst = args.substituicao

    if not os.path.isfile(origem):
        sys.stderr.write("ERRO: Arquivo de origem nao encontrado: %s\n" % origem)
        return 1

    dest_dir = os.path.dirname(destino)
    if dest_dir and not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    print("Iniciando substituicao de texto:")
    print("  Origem:       %s" % origem)
    print("  Destino:      %s" % destino)
    print("  Busca:        %r" % busca)
    print("  Substituicao: %r" % subst)

    inicio = time.time()
    total_linhas = 0
    linhas_alteradas = 0
    total_ocorrencias = 0

    try:
        with open(origem, "r", encoding="utf-8", errors="replace") as f_in, \
             open(destino, "w", encoding="utf-8") as f_out:
            for linha in f_in:
                total_linhas += 1
                qtd = linha.count(busca)
                if qtd > 0:
                    total_ocorrencias += qtd
                    linhas_alteradas += 1
                    linha = linha.replace(busca, subst)
                f_out.write(linha)

        duracao = time.time() - inicio
        print("Substituicao concluida com sucesso!")
        print("  Total de linhas analisadas: %d" % total_linhas)
        print("  Linhas modificadas:         %d" % linhas_alteradas)
        print("  Ocorrencias substituidas:   %d" % total_ocorrencias)
        print("  Tempo decorrido:            %.2fs" % duracao)
        return 0
    except Exception as exc:
        sys.stderr.write("ERRO durante a substituicao: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
