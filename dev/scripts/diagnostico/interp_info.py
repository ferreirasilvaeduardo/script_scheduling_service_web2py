# -*- coding: utf-8 -*-
# Diagnostico do CR-025: mostra o interpretador que rodou o script (cadastrado ou informado no disparo).
import sys
print("Interpretador: %s %s" % (sys.executable, sys.version.split()[0]))
