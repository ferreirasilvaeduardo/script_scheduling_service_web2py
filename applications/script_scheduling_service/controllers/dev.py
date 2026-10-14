# -*- coding: utf-8 -*-
"""Vitrine do layout para desenvolvimento. Nao implantado em HML/PROD (README §12.2)."""
import datetime

from gluon import current

import ui_helpers
import ui_menu


def _exigir_dev():
    if current.sss_cfg.app.sss_env != "DEV":
        raise HTTP(404)


def shell():
    _exigir_dev()
    response.title = u"Shell de desenvolvimento — SSS"
    response.sss_menu = ui_menu.montar_menu(
        ["EXEC_SCRIPT", "VER_LOGS", "CAD_AGENDAMENTOS"],
        False,
        (request.controller, request.function),
    )

    base = datetime.datetime(2026, 10, 14, 9, 0, 0)
    amostras = (
        (1025, "carga_diaria.py", "PRODUCAO", "PENDING", None, None),
        (1024, "carga_diaria.py", "PRODUCAO", "RUNNING", base, None),
        (1023, "relatorio_mensal.py", "HOMOLOGACAO", "SUCCESS",
         base - datetime.timedelta(minutes=30), base - datetime.timedelta(minutes=27, seconds=15)),
        (1022, "sync_tabelas.sh", "PRODUCAO", "FAILED",
         base - datetime.timedelta(hours=3), base - datetime.timedelta(hours=1, minutes=44, seconds=18)),
        (1021, "limpeza_temp.sh", "HOMOLOGACAO", "CANCELLED",
         base - datetime.timedelta(hours=4), base - datetime.timedelta(hours=4) + datetime.timedelta(seconds=42)),
    )
    tickets = [{
        "id": tid,
        "script": script,
        "ambiente": amb,
        "status": ui_helpers.status_info(st),
        "inicio": ui_helpers.formatar_data(ini),
        "duracao": ui_helpers.formatar_duracao(ini, fim),
    } for tid, script, amb, st, ini, fim in amostras]

    return dict(tickets=tickets, status_desconhecido=ui_helpers.status_info("EM_ANALISE"))
