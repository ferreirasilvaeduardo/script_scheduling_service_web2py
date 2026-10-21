# -*- coding: utf-8 -*-
"""Renderizacao real dos quadros e da paginacao do CR-007 R5."""
import _testenv  # noqa: F401

import datetime
import os
import unittest
from urllib.parse import urlencode

from gluon.template import render
import ui_helpers

_VIEWS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "views")


def _url(*args, **kwargs):
    return "/consulta?" + urlencode(kwargs.get("vars", {}))


def _render(view, **contexto):
    contexto.update(URL=_url, ui_helpers=ui_helpers)
    return render(filename=os.path.join(_VIEWS, view), path=_VIEWS, context=contexto)


class TestViewsCR007(unittest.TestCase):

    def test_paginacao_limitada_preserva_filtro_sem_ultima(self):
        html = _render("components/paginacao.html", pagina=502, tamanho=20, total=10001,
                       total_limitado=True, quantidade_pagina=20, url_base=("tickets", "lista"),
                       query_params={"environment": "HOMOLOGACAO", "pagina": 1})
        self.assertIn("mais de 10.000 registros", html)
        self.assertNotIn("Última", html)
        self.assertNotIn("502 de", html)
        self.assertIn("Página 502", html)
        self.assertIn("pagina=503", html)
        self.assertIn("environment=HOMOLOGACAO", html)
        exato = _render("components/paginacao.html", pagina=1, tamanho=20, total=10000,
                        total_limitado=False, quantidade_pagina=20, url_base=("tickets", "lista"),
                        query_params={})
        self.assertIn("Última", exato)
        self.assertNotIn("mais de", exato)

    def test_registro_nao_inclui_ator_oculto_no_html(self):
        reg = {"created_at": datetime.datetime(2026, 10, 17), "created_by": "editor.privado",
               "updated_at": datetime.datetime(2026, 10, 17), "updated_by": "operador"}
        html = _render("components/registro.html", registro=ui_helpers.registro(reg, {"login": "operador"}))
        self.assertNotIn("editor.privado", html)
        self.assertNotIn("operador", html)
        self.assertIn("outra pessoa", html)
        self.assertIn("você", html)
        html = _render("components/registro.html", registro=ui_helpers.registro(reg, {"is_admin": True}))
        self.assertIn("editor.privado", html)

    def test_diagnosticos_aparecem_sem_agentes_e_escapam_conteudo(self):
        agora = datetime.datetime(2026, 10, 17)
        painel = {"agents": [], "resumo": {}, "agora": agora, "config_web": "hb=10",
                  "fila_sem_atendente": [{"environment": "HOMOLOGACAO", "interpreter": "BASH",
                                          "quantidade": 2, "mais_antigo": agora}],
                  "rodando_sem_pid": [{"id": 1, "environment": "HOMOLOGACAO", "agent_id": "agt01",
                                       "started_at": agora}],
                  "config_divergente": [{"code": "agt01", "critical_config": "<script>intruso</script>"}]}
        html = _render("auditoria/agentes.load", painel=painel, erro=None)
        for titulo in ("Fila sem atendente", "Rodando sem PID", "Configuração divergente"):
            self.assertIn(titulo, html)
        self.assertNotIn("<script>intruso</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Nenhum agente registrado", html)
        painel.update(fila_sem_atendente=[], rodando_sem_pid=[], config_divergente=[])
        html = _render("auditoria/agentes.load", painel=painel, erro=None)
        self.assertNotIn("Fila sem atendente", html)
        self.assertNotIn("Rodando sem PID", html)
        self.assertNotIn("Configuração divergente", html)


if __name__ == "__main__":
    unittest.main()
