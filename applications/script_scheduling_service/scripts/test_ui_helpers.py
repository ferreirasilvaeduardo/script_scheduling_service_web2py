# -*- coding: utf-8 -*-
"""Testes de ui_helpers e ui_menu (F1.1)."""
import _testenv  # noqa: F401

import datetime
import os
import re
import sys
import unittest

import ui_helpers
import ui_menu


_SPRITE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "static", "img", "icons.svg")


def _ids_sprite():
    with open(_SPRITE, "r", encoding="utf-8") as f:
        return set(re.findall(r'<symbol id="([^"]+)"', f.read()))


class TestStatusInfo(unittest.TestCase):

    def test_cinco_status_canonicos(self):
        esperados = {
            "PENDING": (u"Pendente", "sss-status-pending", "status-pending"),
            "RUNNING": (u"Em execução", "sss-status-running", "status-running"),
            "SUCCESS": (u"Sucesso", "sss-status-success", "status-success"),
            "FAILED": (u"Falha", "sss-status-failed", "status-failed"),
            "CANCELLED": (u"Cancelado", "sss-status-cancelled", "status-cancelled"),
        }
        for status, (rotulo, classe, icone) in esperados.items():
            with self.subTest(status=status):
                self.assertEqual(ui_helpers.status_info(status),
                                 {"rotulo": rotulo, "classe": classe, "icone": icone})

    def test_status_desconhecido(self):
        esperado = {"rotulo": u"Desconhecido", "classe": "sss-status-unknown", "icone": "status-unknown"}
        for status in ("EM_ANALISE", "pending", "", None, "<script>"):
            with self.subTest(status=status):
                self.assertEqual(ui_helpers.status_info(status), esperado)

    def test_retorno_nao_compartilha_estado(self):
        info = ui_helpers.status_info("FAILED")
        info["rotulo"] = "alterado"
        self.assertEqual(ui_helpers.status_info("FAILED")["rotulo"], u"Falha")

    def test_icones_existem_no_sprite(self):
        ids = _ids_sprite()
        for status in ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED", None):
            self.assertIn(ui_helpers.status_info(status)["icone"], ids)


class TestFormatarData(unittest.TestCase):

    def test_formato(self):
        self.assertEqual(ui_helpers.formatar_data(datetime.datetime(2026, 1, 5, 7, 3, 9)),
                         "05/01/2026 07:03:09")

    def test_none(self):
        self.assertEqual(ui_helpers.formatar_data(None), "-")


class TestFormatarDuracao(unittest.TestCase):
    T0 = datetime.datetime(2026, 10, 14, 10, 0, 0)

    def _dur(self, **delta):
        return ui_helpers.formatar_duracao(self.T0, self.T0 + datetime.timedelta(**delta))

    def test_segundos(self):
        self.assertEqual(self._dur(seconds=0), "0s")
        self.assertEqual(self._dur(seconds=42), "42s")
        self.assertEqual(self._dur(seconds=59), "59s")

    def test_minutos(self):
        self.assertEqual(self._dur(seconds=60), "1m 00s")
        self.assertEqual(self._dur(minutes=5, seconds=7), "5m 07s")
        self.assertEqual(self._dur(minutes=59, seconds=59), "59m 59s")

    def test_horas(self):
        self.assertEqual(self._dur(hours=1), "1h 00m 00s")
        self.assertEqual(self._dur(hours=2, minutes=15, seconds=30), "2h 15m 30s")
        self.assertEqual(self._dur(days=1, hours=1), "25h 00m 00s")

    def test_trunca_fracao_de_segundo(self):
        self.assertEqual(self._dur(seconds=42, microseconds=999999), "42s")

    def test_extremo_ausente(self):
        self.assertEqual(ui_helpers.formatar_duracao(None, self.T0), "-")
        self.assertEqual(ui_helpers.formatar_duracao(self.T0, None), "-")
        self.assertEqual(ui_helpers.formatar_duracao(None, None), "-")

    def test_fim_anterior_ao_inicio(self):
        self.assertEqual(self._dur(seconds=-1), "-")


class TestMontarMenu(unittest.TestCase):

    def _codigos(self, menu):
        return [(s["secao"], [i["codigo"] for i in s["itens"]]) for s in menu]

    def test_admin_ve_catalogo_completo_na_ordem(self):
        menu = ui_menu.montar_menu([], True)
        self.assertEqual(self._codigos(menu), [
            ("OPERACAO", ["EXEC_SCRIPT", "VER_LOGS"]),
            ("ADMIN", ["CAD_USUARIOS", "CAD_PERFIS", "CAD_AMBIENTES", "CAD_SCRIPTS",
                       "CAD_PARAMETROS", "CAD_AGENDAMENTOS", "VER_AUDITORIA"]),
        ])
        self.assertEqual(self._codigos(ui_menu.montar_menu(None, "S")), self._codigos(menu))

    def test_admin_somente_true_ou_s(self):
        for flag in (False, "N", "s", "", None, 1, "True"):
            with self.subTest(flag=flag):
                self.assertEqual(ui_menu.montar_menu([], flag), [])

    def test_filtra_por_funcionalidade_e_omite_secao_vazia(self):
        menu = ui_menu.montar_menu(["VER_LOGS", "CAD_AGENDAMENTOS"], False)
        self.assertEqual(self._codigos(menu), [
            ("OPERACAO", ["VER_LOGS"]),
            ("ADMIN", ["CAD_AGENDAMENTOS"]),
        ])
        self.assertEqual(self._codigos(ui_menu.montar_menu(["EXEC_SCRIPT"], False)),
                         [("OPERACAO", ["EXEC_SCRIPT"])])

    def test_codigo_desconhecido_ou_caixa_diferente_ignorado(self):
        self.assertEqual(ui_menu.montar_menu(["exec_script", "CANC_TICKET", "XYZ"], False), [])

    def test_item_completo_e_rota_ativa(self):
        menu = ui_menu.montar_menu(["EXEC_SCRIPT", "VER_LOGS"], False, ("tickets", "lista"))
        itens = menu[0]["itens"]
        self.assertEqual(menu[0]["titulo"], u"Operação")
        self.assertEqual(itens[0], {
            "codigo": "EXEC_SCRIPT",
            "rotulo": u"Disparar Scripts",
            "rota": ("tickets", "disparo"),
            "icone": "icon-play",
            "ativo": False,
        })
        self.assertTrue(itens[1]["ativo"])
        self.assertEqual(ui_menu.montar_menu(["EXEC_SCRIPT"], False)[0]["itens"][0]["ativo"], False)

    def test_rotulos_do_catalogo_canonico(self):
        rotulos = {i["codigo"]: i["rotulo"] for s in ui_menu.montar_menu([], True) for i in s["itens"]}
        self.assertEqual(rotulos["CAD_PARAMETROS"], u"Dicionário de Parâmetros")
        self.assertEqual(rotulos["CAD_USUARIOS"], u"Gestão de Usuários")
        self.assertEqual(ui_menu.montar_menu([], True)[1]["titulo"], u"Administração")

    def test_rotas_e_icones_ascii_e_icones_no_sprite(self):
        ids = _ids_sprite()
        for secao in ui_menu.montar_menu([], True):
            for item in secao["itens"]:
                for parte in item["rota"] + (item["icone"],):
                    self.assertTrue(re.match(r"^[a-z][a-z0-9_-]*$", parte), parte)
                self.assertIn(item["icone"], ids)

    def test_resultado_independente_entre_chamadas(self):
        menu = ui_menu.montar_menu([], True)
        menu[0]["itens"][0]["rotulo"] = "alterado"
        self.assertEqual(ui_menu.montar_menu([], True)[0]["itens"][0]["rotulo"], u"Disparar Scripts")


class TestModulosPurosSemGluon(unittest.TestCase):

    def test_nao_importam_gluon(self):
        for nome in ("ui_helpers", "ui_menu"):
            caminho = sys.modules[nome].__file__
            with open(caminho, "r", encoding="utf-8") as f:
                self.assertNotRegex(f.read(), r"^\s*(from|import)\s+gluon", nome)


if __name__ == "__main__":
    unittest.main()
