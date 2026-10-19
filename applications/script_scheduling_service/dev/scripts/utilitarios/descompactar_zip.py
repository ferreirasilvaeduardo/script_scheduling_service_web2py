#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utilitario SSS: Descompacta arquivo ZIP com protecao de seguranca."""
import argparse
import os
import sys
import time
import zipfile


def parse_args():
    parser = argparse.ArgumentParser(description="Extrai arquivos de pacote ZIP para pasta destino.")
    parser.add_argument("--arquivo-zip", required=True, help="Caminho do arquivo ZIP")
    parser.add_argument("--destino", required=True, help="Diretorio de destino para extracao")
    return parser.parse_args()


def main():
    args = parse_args()
    arq_zip = os.path.abspath(args.arquivo_zip)
    destino = os.path.abspath(args.destino)

    if not os.path.isfile(arq_zip):
        sys.stderr.write("ERRO: Arquivo ZIP nao encontrado: %s\n" % arq_zip)
        return 1

    if not os.path.exists(destino):
        os.makedirs(destino)

    print("Iniciando descompactacao ZIP:")
    print("  Arquivo: %s" % arq_zip)
    print("  Destino: %s" % destino)

    inicio = time.time()
    total_extraidos = 0
    total_bytes = 0

    try:
        with zipfile.ZipFile(arq_zip, "r") as zf:
            # Validacao previa contra zip slip
            for info in zf.infolist():
                alvo = os.path.abspath(os.path.join(destino, info.filename))
                if os.path.commonpath([destino, alvo]) != destino:
                    sys.stderr.write("ERRO DE SEGURANCA: Caminho malicioso detectado no ZIP: %s\n" % info.filename)
                    return 3

            for info in zf.infolist():
                zf.extract(info, path=destino)
                total_extraidos += 1
                total_bytes += info.file_size

        duracao = time.time() - inicio
        print("Descompactacao concluida com sucesso!")
        print("  Itens extraidos: %d" % total_extraidos)
        print("  Total extraido:  %d bytes" % total_bytes)
        print("  Tempo decorrido: %.2fs" % duracao)
        return 0
    except Exception as exc:
        sys.stderr.write("ERRO durante a descompactacao: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
