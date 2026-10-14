# -*- coding: utf-8 -*-
# Erros da aplicacao SSS sao reprocessados em erro/index, que passa pelos models
# (models/10_security.py) e recebe os cabecalhos de seguranca do README §4.2.
routes_onerror = [
    ("script_scheduling_service/*", "/script_scheduling_service/erro/index"),
]
