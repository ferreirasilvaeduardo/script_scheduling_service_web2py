# -*- coding: utf-8 -*-
"""Script de exemplo DEV (SSS): imprime os argumentos recebidos e sai com 0."""
import sys


def main():
    print("script=%s" % sys.argv[0])
    for i, arg in enumerate(sys.argv[1:], 1):
        print("arg[%d]=%r" % (i, arg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
