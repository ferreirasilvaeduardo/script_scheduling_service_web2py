#!/home/eduardof/.pyenv/versions/3.6.0/bin/python3.6
# -*- coding: utf-8 -*-
# Diagnostico do CR-025 ("Python, definido no script"): o #! acima (Python 3.6 do pyenv do DEV) escolhe o
# interpretador.
import sys
print("Interpretador: %s %s" % (sys.executable, sys.version.split()[0]))
