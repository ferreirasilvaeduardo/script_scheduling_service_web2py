# -*- coding: utf-8 -*-
"""Testes de ui_helpers e ui_menu (F1.1, F1.2)."""
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


class TestAtivoInfo(unittest.TestCase):

    def test_flags(self):
        self.assertEqual(ui_helpers.ativo_info("S"),
                         {"rotulo": u"Ativo", "classe": "sss-status-success", "icone": "status-success"})
        self.assertEqual(ui_helpers.ativo_info("N"),
                         {"rotulo": u"Inativo", "classe": "sss-status-cancelled", "icone": "status-cancelled"})

    def test_desconhecido(self):
        for flag in (None, "", "s", "X"):
            self.assertEqual(ui_helpers.ativo_info(flag)["rotulo"], u"Desconhecido")


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


class TestDescricaoMotivo(unittest.TestCase):

    MOTIVOS = ("EXIT_OK", "EXIT_ERROR", "KILLED_SIGNAL", "TIMEOUT", "NODE_OFFLINE", "ORPHAN_PROCESS", "FENCED",
               "PRECHECK_FAILED", "SPAWN_ERROR", "LOG_LIMIT", "SHUTDOWN", "CANCEL_USER")

    def test_catalogo_completo_do_readme(self):
        textos = [ui_helpers.descricao_motivo(m) for m in self.MOTIVOS]
        self.assertTrue(all(textos))
        self.assertEqual(len(set(textos)), len(self.MOTIVOS))

    def test_vazio_e_desconhecido(self):
        self.assertIsNone(ui_helpers.descricao_motivo(None))
        self.assertIsNone(ui_helpers.descricao_motivo(""))
        self.assertIn("OWNERSHIP_LOST", ui_helpers.descricao_motivo("OWNERSHIP_LOST"))


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


class TestSanitizarPagina(unittest.TestCase):

    def test_validos(self):
        self.assertEqual(ui_helpers.sanitizar_pagina("3"), 3)
        self.assertEqual(ui_helpers.sanitizar_pagina(3), 3)
        self.assertEqual(ui_helpers.sanitizar_pagina("1"), 1)
        self.assertEqual(ui_helpers.sanitizar_pagina("007"), 7)
        self.assertEqual(ui_helpers.sanitizar_pagina("999999999"), 999999999)

    def test_invalidos_viram_padrao(self):
        for valor in (None, "", " 3", "0", 0, "-1", -5, "abc", "1.5", 1.5, u"\u00b2", u"\u0663",
                      "1e3", True, False, ["2"], "1234567890"):
            with self.subTest(valor=valor):
                self.assertEqual(ui_helpers.sanitizar_pagina(valor), 1)

    def test_padrao_customizado(self):
        self.assertEqual(ui_helpers.sanitizar_pagina("x", padrao=4), 4)
        self.assertEqual(ui_helpers.sanitizar_pagina("2", padrao=4), 2)


class TestSanitizarTamanho(unittest.TestCase):

    def test_permitidos(self):
        for valor, esperado in (("20", 20), (20, 20), ("50", 50), (50, 50), ("100", 100), (100, 100)):
            with self.subTest(valor=valor):
                self.assertEqual(ui_helpers.sanitizar_tamanho(valor), esperado)

    def test_fora_da_lista_vira_primeiro(self):
        for valor in ("30", 30, 0, "0", -20, "-20", None, "", "abc", True, "1000", ["50"]):
            with self.subTest(valor=valor):
                self.assertEqual(ui_helpers.sanitizar_tamanho(valor), 20)

    def test_permitidos_customizados(self):
        self.assertEqual(ui_helpers.sanitizar_tamanho("10", permitidos=(10, 25)), 10)
        self.assertEqual(ui_helpers.sanitizar_tamanho("25", permitidos=(10, 25)), 25)
        self.assertEqual(ui_helpers.sanitizar_tamanho("20", permitidos=(10, 25)), 10)


class TestPaginacaoInfo(unittest.TestCase):

    def _resumo(self, info):
        return (info["pagina"], info["total_paginas"], info["tem_anterior"], info["tem_proxima"],
                info["anterior"], info["proxima"], info["primeiro_registro"], info["ultimo_registro"])

    def test_total_zero(self):
        info = ui_helpers.paginacao_info(1, 20, 0)
        self.assertEqual(self._resumo(info), (1, 1, False, False, 1, 1, 0, 0))
        self.assertEqual(self._resumo(ui_helpers.paginacao_info(5, 20, 0)), self._resumo(info))

    def test_pagina_zero_e_negativa(self):
        for pagina in (0, -1, "0", "-3", None, "abc"):
            with self.subTest(pagina=pagina):
                self.assertEqual(self._resumo(ui_helpers.paginacao_info(pagina, 20, 57)),
                                 (1, 3, False, True, 1, 2, 1, 20))

    def test_pagina_alem_do_total(self):
        self.assertEqual(self._resumo(ui_helpers.paginacao_info(99, 20, 57)),
                         (3, 3, True, False, 2, 3, 41, 57))
        self.assertEqual(self._resumo(ui_helpers.paginacao_info("4", 20, 57))[0], 3)

    def test_meio(self):
        self.assertEqual(self._resumo(ui_helpers.paginacao_info(2, 20, 57)),
                         (2, 3, True, True, 1, 3, 21, 40))

    def test_ultima_exata(self):
        self.assertEqual(self._resumo(ui_helpers.paginacao_info(2, 20, 40)),
                         (2, 2, True, False, 1, 2, 21, 40))
        self.assertEqual(ui_helpers.paginacao_info(1, 20, 20)["total_paginas"], 1)
        self.assertEqual(ui_helpers.paginacao_info(1, 20, 21)["total_paginas"], 2)

    def test_um_registro(self):
        self.assertEqual(self._resumo(ui_helpers.paginacao_info(1, 50, 1)),
                         (1, 1, False, False, 1, 1, 1, 1))

    def test_tamanho_e_total_invalidos(self):
        info = ui_helpers.paginacao_info(1, 0, 57)
        self.assertEqual((info["tamanho"], info["total_paginas"]), (20, 3))
        self.assertEqual(ui_helpers.paginacao_info(1, -5, 57)["tamanho"], 20)
        info = ui_helpers.paginacao_info(3, 20, -1)
        self.assertEqual((info["total"], info["pagina"], info["total_paginas"]), (0, 1, 1))
        self.assertEqual(ui_helpers.paginacao_info(1, 20, None)["total"], 0)

    def test_chaves(self):
        self.assertEqual(sorted(ui_helpers.paginacao_info(1, 20, 5)), sorted([
            "pagina", "tamanho", "total", "total_paginas", "tem_anterior", "tem_proxima",
            "anterior", "proxima", "primeiro_registro", "ultimo_registro"]))


class TestPrimeiroCampoInvalido(unittest.TestCase):

    def test_ordem(self):
        campos = [{"nome": "a"}, {"nome": "b", "erro": u"Obrigatório."}, {"nome": "c", "erro": u"Inválido."}]
        self.assertEqual(ui_helpers.primeiro_campo_invalido(campos), "b")

    def test_sem_erro(self):
        self.assertIsNone(ui_helpers.primeiro_campo_invalido([{"nome": "a", "erro": ""}, {"nome": "b"}]))
        self.assertIsNone(ui_helpers.primeiro_campo_invalido([]))
        self.assertIsNone(ui_helpers.primeiro_campo_invalido(None))


class TestAlertaInfo(unittest.TestCase):

    def test_tipos(self):
        esperados = {
            "sucesso": ("alert-success", "status-success", "status"),
            "aviso": ("alert-warning", "icon-alert", "status"),
            "erro": ("alert-danger", "status-failed", "alert"),
        }
        for tipo, (classe, icone, role) in esperados.items():
            with self.subTest(tipo=tipo):
                self.assertEqual(ui_helpers.alerta_info({"tipo": tipo, "mensagem": u"Mensagem"}), {
                    "tipo": tipo, "mensagem": u"Mensagem", "classe": classe, "icone": icone, "role": role})

    def test_formatos_de_entrada(self):
        self.assertEqual(ui_helpers.alerta_info(("erro", u"Falhou."))["tipo"], "erro")
        self.assertEqual(ui_helpers.alerta_info(["sucesso", u"Ok."])["tipo"], "sucesso")
        info = ui_helpers.alerta_info(u"Texto simples")
        self.assertEqual((info["tipo"], info["mensagem"]), ("aviso", u"Texto simples"))

    def test_tipo_desconhecido_vira_aviso(self):
        for tipo in ("info", "ERRO", None, "<script>"):
            with self.subTest(tipo=tipo):
                self.assertEqual(ui_helpers.alerta_info({"tipo": tipo, "mensagem": "x"})["tipo"], "aviso")

    def test_sem_mensagem(self):
        for flash in (None, "", {}, {"tipo": "erro"}, {"tipo": "erro", "mensagem": ""}, ("erro", None)):
            with self.subTest(flash=flash):
                self.assertIsNone(ui_helpers.alerta_info(flash))

    def test_icones_existem_no_sprite(self):
        ids = _ids_sprite()
        for tipo in ("sucesso", "aviso", "erro"):
            self.assertIn(ui_helpers.alerta_info((tipo, "x"))["icone"], ids)


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
            "rota": ("tickets", "novo"),
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
