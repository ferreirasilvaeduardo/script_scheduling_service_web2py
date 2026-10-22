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


class TestActiveInfo(unittest.TestCase):

    def test_flags(self):
        self.assertEqual(ui_helpers.ativo_info("Y"),
                         {"label": u"Ativo", "css_class": "sss-status-success", "icon": "status-success"})
        self.assertEqual(ui_helpers.ativo_info("N"),
                         {"label": u"Inativo", "css_class": "sss-status-cancelled", "icon": "status-cancelled"})

    def test_desconhecido(self):
        for flag in (None, "", "s", "X"):
            self.assertEqual(ui_helpers.ativo_info(flag)["label"], u"Desconhecido")


class TestStatusInfo(unittest.TestCase):

    def test_cinco_status_canonicos(self):
        expected = {
            "PENDING": (u"Esperando", "sss-status-pending", "status-pending"),
            "RUNNING": (u"Rodando", "sss-status-running", "status-running"),
            "SUCCESS": (u"Deu certo", "sss-status-success", "status-success"),
            "FAILED": (u"Deu erro", "sss-status-failed", "status-failed"),
            "CANCELLED": (u"Cancelado", "sss-status-cancelled", "status-cancelled"),
        }
        for status, (label, cls_name, icon) in expected.items():
            with self.subTest(status=status):
                self.assertEqual(ui_helpers.status_info(status),
                                 {"label": label, "css_class": cls_name, "icon": icon})

    def test_status_desconhecido(self):
        expected = {"label": u"Desconhecido", "css_class": "sss-status-unknown", "icon": "status-unknown"}
        for status in ("EM_ANALISE", "pending", "", None, "<script>"):
            with self.subTest(status=status):
                self.assertEqual(ui_helpers.status_info(status), expected)

    def test_retorno_nao_compartilha_estado(self):
        info = ui_helpers.status_info("FAILED")
        info["label"] = "alterado"
        self.assertEqual(ui_helpers.status_info("FAILED")["label"], u"Deu erro")

    def test_icones_existem_no_sprite(self):
        ids = _ids_sprite()
        for status in ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED", None):
            self.assertIn(ui_helpers.status_info(status)["icon"], ids)


class TestReasonDescription(unittest.TestCase):

    REASONS = ("EXIT_OK", "EXIT_ERROR", "KILLED_SIGNAL", "TIMEOUT", "NODE_OFFLINE", "ORPHAN_PROCESS", "FENCED",
               "PRECHECK_FAILED", "SPAWN_ERROR", "LOG_LIMIT", "SHUTDOWN", "CANCEL_USER")

    def test_catalogo_completo_do_readme(self):
        texts = [ui_helpers.descricao_motivo(m) for m in self.REASONS]
        self.assertTrue(all(texts))
        self.assertEqual(len(set(texts)), len(self.REASONS))

    def test_vazio_e_desconhecido(self):
        self.assertIsNone(ui_helpers.descricao_motivo(None))
        self.assertIsNone(ui_helpers.descricao_motivo(""))
        self.assertIn("OWNERSHIP_LOST", ui_helpers.descricao_motivo("OWNERSHIP_LOST"))


class TestRecordPanel(unittest.TestCase):
    """Quadro Registro (CR-006, README §10): ator em linguagem simples e as duas frases."""

    def test_nome_ator(self):
        self.assertEqual(ui_helpers.nome_ator("op.prod"), "op.prod")
        self.assertEqual(ui_helpers.nome_ator("SYSTEM:agt-host01"), u"Sistema (agente agt-host01)")
        self.assertEqual(ui_helpers.nome_ator("SYSTEM:init_db"), u"Sistema (instalação)")
        self.assertEqual(ui_helpers.nome_ator("SYSTEM:seed"), u"Sistema (dados de demonstração)")
        self.assertEqual(ui_helpers.nome_ator("SYSTEM"), u"Sistema")
        self.assertEqual(ui_helpers.nome_ator(None), "-")

    def test_registro_mascara_sem_mudar_origem(self):
        created = datetime.datetime(2026, 10, 17, 9, 5)
        raw = {"created_at": created, "created_by": "editor.privado",
                 "updated_at": created, "updated_by": "op.prod"}
        for ctx, expected in (({"login": "op.prod"}, (u"outra pessoa", u"você")),
                              ({"is_admin": True}, ("editor.privado", "op.prod")),
                              ({"features": {"VIEW_AUDIT"}}, ("editor.privado", "op.prod")),
                              (None, (u"outra pessoa", u"outra pessoa"))):
            reg = ui_helpers.registro(raw, ctx)
            self.assertEqual((reg["created_by"], reg["updated_by"]), expected)
            self.assertEqual(reg["created_at"], created)
        self.assertEqual(raw["created_by"], "editor.privado")
        self.assertEqual(ui_helpers.nome_ator("SYSTEM:purge"), u"Sistema (limpeza)")

    def test_registro_e_exibicao(self):
        created = datetime.datetime(2026, 10, 17, 9, 5, 0)
        reg = ui_helpers.registro({"id": 1, "created_at": created, "created_by": "SYSTEM:seed", "name": "x"}, {})
        self.assertEqual(reg, {"created_at": created, "created_by": "SYSTEM:seed", "updated_at": None,
                               "updated_by": None})
        self.assertEqual(ui_helpers.registro_exibicao(reg), {
            "created": u"17/10/2026 09:05:00 por Sistema (dados de demonstração)", "updated": u"Nunca alterado"})
        reg.update(updated_at=created + datetime.timedelta(hours=1), updated_by="admin")
        self.assertEqual(ui_helpers.registro_exibicao(reg)["updated"], u"17/10/2026 10:05:00 por admin")
        self.assertEqual(ui_helpers.registro(None, {}), dict.fromkeys(ui_helpers.COLUNAS_REGISTRO))


class TestFormatDate(unittest.TestCase):

    def test_formato(self):
        self.assertEqual(ui_helpers.formatar_data(datetime.datetime(2026, 1, 5, 7, 3, 9)),
                         "05/01/2026 07:03:09")

    def test_none(self):
        self.assertEqual(ui_helpers.formatar_data(None), "-")


class TestFormatDuration(unittest.TestCase):
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


class TestSanitizePage(unittest.TestCase):

    def test_validos(self):
        self.assertEqual(ui_helpers.sanitizar_pagina("3"), 3)
        self.assertEqual(ui_helpers.sanitizar_pagina(3), 3)
        self.assertEqual(ui_helpers.sanitizar_pagina("1"), 1)
        self.assertEqual(ui_helpers.sanitizar_pagina("007"), 7)
        self.assertEqual(ui_helpers.sanitizar_pagina("999999999"), 999999999)

    def test_invalidos_viram_padrao(self):
        for value in (None, "", " 3", "0", 0, "-1", -5, "abc", "1.5", 1.5, u"\u00b2", u"\u0663",
                      "1e3", True, False, ["2"], "1234567890"):
            with self.subTest(valor=value):
                self.assertEqual(ui_helpers.sanitizar_pagina(value), 1)

    def test_padrao_customizado(self):
        self.assertEqual(ui_helpers.sanitizar_pagina("x", default_value=4), 4)
        self.assertEqual(ui_helpers.sanitizar_pagina("2", default_value=4), 2)


class TestSanitizeSize(unittest.TestCase):

    def test_permitidos(self):
        for value, expected in (("20", 20), (20, 20), ("50", 50), (50, 50), ("100", 100), (100, 100)):
            with self.subTest(valor=value):
                self.assertEqual(ui_helpers.sanitizar_tamanho(value), expected)

    def test_fora_da_lista_vira_primeiro(self):
        for value in ("30", 30, 0, "0", -20, "-20", None, "", "abc", True, "1000", ["50"]):
            with self.subTest(valor=value):
                self.assertEqual(ui_helpers.sanitizar_tamanho(value), 20)

    def test_permitidos_customizados(self):
        self.assertEqual(ui_helpers.sanitizar_tamanho("10", allowed=(10, 25)), 10)
        self.assertEqual(ui_helpers.sanitizar_tamanho("25", allowed=(10, 25)), 25)
        self.assertEqual(ui_helpers.sanitizar_tamanho("20", allowed=(10, 25)), 10)


class TestPaginationInfo(unittest.TestCase):

    def _summary(self, info):
        return (info["pagina"], info["total_paginas"], info["tem_anterior"], info["tem_proxima"],
                info["anterior"], info["proxima"], info["primeiro_registro"], info["ultimo_registro"])

    def test_total_limitado_nao_corta_navegacao(self):
        info = ui_helpers.paginacao_info(502, 20, 10001, True, 20)
        self.assertTrue(info["total_limitado"])
        self.assertIsNone(info["total_paginas"])
        self.assertEqual(info["pagina"], 502)
        self.assertEqual(info["proxima"], 503)
        self.assertTrue(info["tem_proxima"])
        self.assertEqual((info["primeiro_registro"], info["ultimo_registro"]), (10021, 10040))
        end = ui_helpers.paginacao_info(503, 20, 10001, True, 7)
        self.assertFalse(end["tem_proxima"])
        self.assertEqual(end["ultimo_registro"], 10047)
        empty = ui_helpers.paginacao_info(504, 20, 10001, True, 0)
        self.assertFalse(empty["tem_proxima"])
        self.assertTrue(empty["tem_anterior"])
        self.assertEqual((empty["primeiro_registro"], empty["ultimo_registro"]), (0, 0))
        self.assertFalse(ui_helpers.paginacao_info(1, 20, 10000)["total_limitado"])

    def test_total_zero(self):
        info = ui_helpers.paginacao_info(1, 20, 0)
        self.assertEqual(self._summary(info), (1, 1, False, False, 1, 1, 0, 0))
        self.assertEqual(self._summary(ui_helpers.paginacao_info(5, 20, 0)), self._summary(info))

    def test_pagina_zero_e_negativa(self):
        for page in (0, -1, "0", "-3", None, "abc"):
            with self.subTest(pagina=page):
                self.assertEqual(self._summary(ui_helpers.paginacao_info(page, 20, 57)),
                                 (1, 3, False, True, 1, 2, 1, 20))

    def test_pagina_alem_do_total(self):
        self.assertEqual(self._summary(ui_helpers.paginacao_info(99, 20, 57)),
                         (3, 3, True, False, 2, 3, 41, 57))
        self.assertEqual(self._summary(ui_helpers.paginacao_info("4", 20, 57))[0], 3)

    def test_meio(self):
        self.assertEqual(self._summary(ui_helpers.paginacao_info(2, 20, 57)),
                         (2, 3, True, True, 1, 3, 21, 40))

    def test_ultima_exata(self):
        self.assertEqual(self._summary(ui_helpers.paginacao_info(2, 20, 40)),
                         (2, 2, True, False, 1, 2, 21, 40))
        self.assertEqual(ui_helpers.paginacao_info(1, 20, 20)["total_paginas"], 1)
        self.assertEqual(ui_helpers.paginacao_info(1, 20, 21)["total_paginas"], 2)

    def test_um_registro(self):
        self.assertEqual(self._summary(ui_helpers.paginacao_info(1, 50, 1)),
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
            "pagina", "tamanho", "total", "total_paginas", "total_limitado", "tem_anterior", "tem_proxima",
            "anterior", "proxima", "primeiro_registro", "ultimo_registro"]))


class TestFirstInvalidField(unittest.TestCase):

    def test_ordem(self):
        fields = [{"name": "a"}, {"name": "b", "error": u"Obrigatório."}, {"name": "c", "error": u"Inválido."}]
        self.assertEqual(ui_helpers.primeiro_campo_invalido(fields), "b")

    def test_sem_erro(self):
        self.assertIsNone(ui_helpers.primeiro_campo_invalido([{"name": "a", "error": ""}, {"name": "b"}]))
        self.assertIsNone(ui_helpers.primeiro_campo_invalido([]))
        self.assertIsNone(ui_helpers.primeiro_campo_invalido(None))


class TestAlertInfo(unittest.TestCase):

    def test_tipos(self):
        expected = {
            "success": ("alert-success", "status-success", "status"),
            "warning": ("alert-warning", "icon-alert", "status"),
            "error": ("alert-danger", "status-failed", "alert"),
        }
        for kind, (cls_name, icon, role) in expected.items():
            with self.subTest(tipo=kind):
                self.assertEqual(ui_helpers.alerta_info({"kind": kind, "message": u"Mensagem"}), {
                    "kind": kind, "message": u"Mensagem", "css_class": cls_name, "icon": icon, "role": role})

    def test_formatos_de_entrada(self):
        self.assertEqual(ui_helpers.alerta_info(("error", u"Falhou."))["kind"], "error")
        self.assertEqual(ui_helpers.alerta_info(["success", u"Ok."])["kind"], "success")
        info = ui_helpers.alerta_info(u"Texto simples")
        self.assertEqual((info["kind"], info["message"]), ("warning", u"Texto simples"))

    def test_tipo_desconhecido_vira_aviso(self):
        for kind in ("info", "ERRO", None, "<script>"):
            with self.subTest(tipo=kind):
                self.assertEqual(ui_helpers.alerta_info({"kind": kind, "message": "x"})["kind"], "warning")

    def test_sem_mensagem(self):
        for flash in (None, "", {}, {"kind": "error"}, {"kind": "error", "message": ""}, ("error", None)):
            with self.subTest(flash=flash):
                self.assertIsNone(ui_helpers.alerta_info(flash))

    def test_icones_existem_no_sprite(self):
        ids = _ids_sprite()
        for kind in ("success", "warning", "error"):
            self.assertIn(ui_helpers.alerta_info((kind, "x"))["icon"], ids)


class TestBuildMenu(unittest.TestCase):

    def _codes(self, menu):
        return [(s["secao"], [i["code"] for i in s["itens"]]) for s in menu]

    def test_admin_ve_catalogo_completo_na_ordem(self):
        menu = ui_menu.montar_menu([], True)
        self.assertEqual(self._codes(menu), [
            ("OPERATION", ["EXEC_SCRIPT", "EXEC_SCRIPT", "VIEW_LOGS"]),
            ("ADMIN", ["MANAGE_USERS", "MANAGE_PROFILES", "MANAGE_ENVIRONMENTS", "MANAGE_SCRIPTS",
                       "MANAGE_PARAMETERS", "MANAGE_SCHEDULES", "VIEW_AUDIT"]),
        ])
        self.assertEqual(self._codes(ui_menu.montar_menu(None, "Y")), self._codes(menu))

    def test_admin_somente_true_ou_s(self):
        for flag in (False, "N", "s", "", None, 1, "True"):
            with self.subTest(flag=flag):
                self.assertEqual(ui_menu.montar_menu([], flag), [])

    def test_filtra_por_funcionalidade_e_omite_secao_vazia(self):
        menu = ui_menu.montar_menu(["VIEW_LOGS", "MANAGE_SCHEDULES"], False)
        self.assertEqual(self._codes(menu), [
            ("OPERATION", ["VIEW_LOGS"]),
            ("ADMIN", ["MANAGE_SCHEDULES"]),
        ])
        self.assertEqual(self._codes(ui_menu.montar_menu(["EXEC_SCRIPT"], False)),
                         [("OPERATION", ["EXEC_SCRIPT", "EXEC_SCRIPT"])])

    def test_codigo_desconhecido_ou_caixa_diferente_ignorado(self):
        self.assertEqual(ui_menu.montar_menu(["exec_script", "CANCEL_TICKET", "XYZ"], False), [])

    def test_item_completo_e_rota_ativa(self):
        menu = ui_menu.montar_menu(["EXEC_SCRIPT", "VIEW_LOGS"], False, ("tickets", "index"))
        items = menu[0]["itens"]
        self.assertEqual(menu[0]["title"], u"Operação")
        # CR-004 U5 (README §5.8): "Rotinas disponíveis" vem antes de "Disparar Scripts".
        self.assertEqual(items[0]["rota"], ("tickets", "catalog"))
        self.assertEqual(items[1], {
            "code": "EXEC_SCRIPT",
            "label": u"Disparar Scripts",
            "rota": ("tickets", "new"),
            "icon": "icon-play",
            "active": False,
        })
        self.assertTrue(items[2]["active"])
        self.assertEqual(ui_menu.montar_menu(["EXEC_SCRIPT"], False)[0]["itens"][0]["active"], False)

    def test_rotulos_do_catalogo_canonico(self):
        labels = {i["code"]: i["label"] for s in ui_menu.montar_menu([], True) for i in s["itens"]}
        self.assertEqual(labels["MANAGE_PARAMETERS"], u"Dicionário de Parâmetros")
        self.assertEqual(labels["MANAGE_USERS"], u"Gestão de Usuários")
        self.assertEqual(ui_menu.montar_menu([], True)[1]["title"], u"Administração")

    def test_rotas_e_icones_ascii_e_icones_no_sprite(self):
        ids = _ids_sprite()
        for section in ui_menu.montar_menu([], True):
            for item in section["itens"]:
                for part in item["rota"] + (item["icon"],):
                    self.assertTrue(re.match(r"^[a-z][a-z0-9_-]*$", part), part)
                self.assertIn(item["icon"], ids)

    def test_resultado_independente_entre_chamadas(self):
        menu = ui_menu.montar_menu([], True)
        menu[0]["itens"][0]["label"] = "alterado"
        self.assertEqual(ui_menu.montar_menu([], True)[0]["itens"][0]["label"], u"Rotinas disponíveis")


class TestPureModulesWithoutGluon(unittest.TestCase):

    def test_nao_importam_gluon(self):
        for name in ("ui_helpers", "ui_menu"):
            path = sys.modules[name].__file__
            with open(path, "r", encoding="utf-8") as f:
                self.assertNotRegex(f.read(), r"^\s*(from|import)\s+gluon", name)


class TestPlainLanguage(unittest.TestCase):
    """CR-004 U1 (README §2.4.2, §5.2.1)."""

    NOW = datetime.datetime(2026, 10, 16, 10, 0, 0)

    def test_mensagens_padrao_em_duas_partes(self):
        for key in ui_helpers.MENSAGENS:
            happened, todo = ui_helpers.mensagem_partes(key, minutos=15)
            self.assertTrue(happened and todo, key)
        self.assertEqual(ui_helpers.mensagem("conflict"),
                         u"Outra pessoa mudou este registro enquanto você editava. "
                         u"Recarregue a página para ver a versão nova e faça a sua alteração de novo.")

    def test_explicacao_por_situacao(self):
        e = ui_helpers.explicacao_ticket
        future = self.NOW + datetime.timedelta(hours=2)
        self.assertEqual(e({"status": "PENDING", "scheduled_at": future}, self.NOW)["happened"],
                         u"Está agendado para começar em 16/10/2026 às 12:00.")
        self.assertEqual(e({"status": "PENDING", "scheduled_at": self.NOW}, self.NOW)["happened"],
                         u"Está na fila, esperando um servidor livre.")
        running = {"status": "RUNNING", "started_at": self.NOW - datetime.timedelta(minutes=4)}
        self.assertEqual(e(running, self.NOW)["happened"], u"Está rodando agora. Começou há 4 minutos.")
        self.assertIn(u"cancelamento foi pedido", e(dict(running, cancel_requested="Y"), self.NOW)["happened"])
        error = e({"status": "FAILED", "status_reason": "EXIT_ERROR", "return_code": 3}, self.NOW)
        self.assertEqual((error["state"], error["happened"]),
                         (u"Deu erro", u"O script rodou, mas terminou avisando que algo deu errado (código 3)."))
        self.assertIn(u"6 horas", e({"status": "FAILED", "status_reason": "TIMEOUT"}, self.NOW, 21600)["happened"])
        self.assertIsNone(e({"status": "SUCCESS", "status_reason": "EXIT_OK"}, self.NOW)["todo"])
        self.assertIn("XYZ", e({"status": "FAILED", "status_reason": "XYZ"}, self.NOW)["happened"])

    def test_etapas_do_ticket(self):
        # CR-004 U2 (README §5.7).
        created = self.NOW - datetime.timedelta(minutes=10)
        pend = ui_helpers.etapas_ticket({"status": "PENDING", "created_at": created,
                                         "scheduled_at": self.NOW + datetime.timedelta(hours=1)}, self.NOW)
        self.assertEqual([e["estado"] for e in pend], ["feito", "atual", "pendente", "pendente"])
        self.assertTrue(pend[1]["when"].startswith(u"agendado para"))
        run = ui_helpers.etapas_ticket({"status": "RUNNING", "created_at": created, "scheduled_at": created,
                                        "started_at": self.NOW - datetime.timedelta(minutes=2)}, self.NOW)
        self.assertEqual([e["estado"] for e in run], ["feito", "feito", "atual", "pendente"])
        self.assertEqual(run[2]["when"], u"há 2 minutos")
        cancel = ui_helpers.etapas_ticket({"status": "CANCELLED", "created_at": created, "scheduled_at": created,
                                         "finished_at": self.NOW}, self.NOW)
        self.assertEqual([e["estado"] for e in cancel], ["feito", "feito", "pulado", "atual"])
        self.assertEqual(cancel[2]["when"], u"não chegou a rodar")
        self.assertTrue(cancel[3]["when"].startswith(u"Cancelado"))
        ok = ui_helpers.etapas_ticket({"status": "SUCCESS", "created_at": created, "scheduled_at": created,
                                       "started_at": created, "finished_at": self.NOW}, self.NOW)
        self.assertEqual([e["estado"] for e in ok], ["feito", "feito", "feito", "atual"])

    def test_tempo_simples(self):
        self.assertEqual(ui_helpers.tempo_simples(30), u"menos de 1 minuto")
        self.assertEqual(ui_helpers.tempo_simples(60), u"1 minuto")
        self.assertEqual(ui_helpers.tempo_simples(3600), u"1 hora")
        self.assertEqual(ui_helpers.tempo_simples(7500), u"2 horas e 5 minutos")


if __name__ == "__main__":
    unittest.main()
