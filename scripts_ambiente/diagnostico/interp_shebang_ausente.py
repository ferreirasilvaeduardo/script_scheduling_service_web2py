#!/nao/existe/python3
# -*- coding: utf-8 -*-
# Diagnostico do CR-026: o #! aponta para um executavel que nao existe; o agente o ignora (linha [SSS] no
# log) e usa o digitado no disparo ou o interpretador do cadastro.
import sys
print("Interpretador: %s %s" % (sys.executable, sys.version.split()[0]))
