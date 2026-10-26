#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Diagnostico do CR-025 ("Python, definido no script" com env): o env procura o python3 no PATH fixo do filho.
import sys
print("Interpretador: %s %s" % (sys.executable, sys.version.split()[0]))
print("Prefixo: %s" % sys.prefix)
