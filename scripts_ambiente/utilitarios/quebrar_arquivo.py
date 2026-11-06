#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utilitario SSS: Divide arquivo texto em multiplas partes por linhas."""
import argparse
import os
import sys
import time


def parse_args():
    parser = argparse.ArgumentParser(description="Divide arquivo texto em partes menores.")
    parser.add_argument("--origem", required=True, help="Arquivo de origem a ser dividido")
    parser.add_argument("--linhas-por-parte", type=int, default=1000, help="Quantidade de linhas por parte (padrao 1000)")
    parser.add_argument("--prefixo-saida", default="/tmp/parte_", help="Prefixo para os arquivos gerados")
    return parser.parse_args()


def main():
    args = parse_args()
    origem = os.path.abspath(args.origem)
    prefixo = os.path.abspath(args.prefixo_saida)
    linhas_limite = max(1, args.linhas_por_parte)

    if not os.path.isfile(origem):
        sys.stderr.write("ERRO: Arquivo de origem nao encontrado: %s\n" % origem)
        return 1

    diretorio_saida = os.path.dirname(prefixo)
    if diretorio_saida and not os.path.exists(diretorio_saida):
        os.makedirs(diretorio_saida)

    print("Iniciando divisao de arquivo:")
    print("  Origem:           %s" % origem)
    print("  Linhas por parte: %d" % linhas_limite)
    print("  Prefixo destino:  %s" % prefixo)

    inicio = time.time()
    num_parte = 1
    linhas_parte_atual = 0
    total_linhas = 0
    f_out = None

    try:
        with open(origem, "r", encoding="utf-8", errors="replace") as f_in:
            for linha in f_in:
                if f_out is None or linhas_parte_atual >= linhas_limite:
                    if f_out is not None:
                        f_out.close()
                    nome_parte = "%s%04d.txt" % (prefixo, num_parte)
                    f_out = open(nome_parte, "w", encoding="utf-8")
                    linhas_parte_atual = 0
                    num_parte += 1

                f_out.write(linha)
                linhas_parte_atual += 1
                total_linhas += 1

        if f_out is not None:
            f_out.close()

        total_partes = max(0, num_parte - 1)
        duracao = time.time() - inicio

        print("Divisao concluida com sucesso!")
        print("  Total de linhas lidas: %d" % total_linhas)
        print("  Partes geradas:        %d" % total_partes)
        print("  Tempo decorrido:       %.2fs" % duracao)
        return 0
    except Exception as exc:
        if f_out is not None and not f_out.closed:
            f_out.close()
        sys.stderr.write("ERRO durante a divisao: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
