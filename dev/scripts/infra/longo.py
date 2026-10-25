# -*- coding: utf-8 -*-
"""Script de exemplo DEV (SSS): dorme em ciclos e imprime progresso (testes de timeout/cancelamento).

Uso: longo.py [ciclos=60] [intervalo_s=1]
"""
import sys
import time


def main():
    ciclos = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    intervalo = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    for i in range(1, ciclos + 1):
        print("progresso %d/%d" % (i, ciclos), flush=True)
        time.sleep(intervalo)
    print("concluido", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
