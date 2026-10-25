# -*- coding: utf-8 -*-
"""Renderizacao real dos quadros e da paginacao do CR-007 R5.

Usa o motor de templates proprio (CR-021f1), no lugar do gluon.template.
"""
from tests.support import _testenv  # noqa: F401

import datetime
import os
import unittest
from urllib.parse import urlencode

from sss.ui import ui_helpers
from web.response import Response
from web.template import Templates

_VIEWS = os.path.join(_testenv.APP_DIR, "views")
_TEMPLATES = Templates(_VIEWS)


def _url(*args, **kwargs):
    return "/consulta?" + urlencode(kwargs.get("vars", {}))


def _render(view, **context):
    context.update(URL=_url, ui_helpers=ui_helpers, response=Response())
    return _TEMPLATES.render(view, context)


class TestViewsCR007(unittest.TestCase):

    def test_paginacao_limitada_preserva_filtro_sem_ultima(self):
        html = _render("components/pagination.html", page=502, size=20, total=10001,
                       total_capped=True, page_count=20, url_base=("tickets", "index"),
                       query_params={"environment": "HOMOLOGACAO", "page": 1})
        self.assertIn("mais de 10.000 registros", html)
        self.assertNotIn("Última", html)
        self.assertNotIn("502 de", html)
        self.assertIn("Página 502", html)
        self.assertIn("page=503", html)
        self.assertIn("environment=HOMOLOGACAO", html)
        exact = _render("components/pagination.html", page=1, size=20, total=10000,
                        total_capped=False, page_count=20, url_base=("tickets", "index"),
                        query_params={})
        self.assertIn("Última", exact)
        self.assertNotIn("mais de", exact)

    def test_registro_nao_inclui_ator_oculto_no_html(self):
        reg = {"created_at": datetime.datetime(2026, 10, 17), "created_by": "editor.privado",
               "updated_at": datetime.datetime(2026, 10, 17), "updated_by": "operador"}
        html = _render("components/record.html", record=ui_helpers.record_info(reg, {"login": "operador"}))
        self.assertNotIn("editor.privado", html)
        self.assertNotIn("operador", html)
        self.assertIn("outra pessoa", html)
        self.assertIn("você", html)
        html = _render("components/record.html", record=ui_helpers.record_info(reg, {"is_admin": True}))
        self.assertIn("editor.privado", html)

    def test_diagnosticos_aparecem_sem_agentes_e_escapam_conteudo(self):
        now = datetime.datetime(2026, 10, 17)
        dashboard = {"agents": [], "summary": {}, "now": now, "config_web": "hb=10",
                  "unattended_queue": [{"environment": "HOMOLOGACAO", "interpreter": "BASH",
                                          "quantity": 2, "oldest": now}],
                  "running_without_pid": [{"id": 1, "environment": "HOMOLOGACAO", "agent_id": "agt01",
                                       "started_at": now}],
                  "config_mismatch": [{"code": "agt01", "critical_config": "<script>intruso</script>"}]}
        html = _render("audit/agents.load", dashboard=dashboard, error=None)
        for title in ("Fila sem atendente", "Rodando sem PID", "Configuração divergente"):
            self.assertIn(title, html)
        self.assertNotIn("<script>intruso</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Nenhum agente registrado", html)
        dashboard.update(unattended_queue=[], running_without_pid=[], config_mismatch=[])
        html = _render("audit/agents.load", dashboard=dashboard, error=None)
        self.assertNotIn("Fila sem atendente", html)
        self.assertNotIn("Rodando sem PID", html)
        self.assertNotIn("Configuração divergente", html)


if __name__ == "__main__":
    unittest.main()
