# -*- coding: utf-8 -*-
"""Testes de ui_helpers e ui_menu (F1.1, F1.2)."""
from tests.support import _testenv  # noqa: F401

import datetime
import os
import re
import sys
import unittest

import ui_helpers
import ui_menu


_SPRITE = os.path.join(_testenv.APP_DIR,
                       "static", "img", "icons.svg")


def _ids_sprite():
    with open(_SPRITE, "r", encoding="utf-8") as f:
        return set(re.findall(r'<symbol id="([^"]+)"', f.read()))


class TestActiveInfo(unittest.TestCase):

    def test_flags(self):
        self.assertEqual(ui_helpers.active_info("Y"),
                         {"label": u"Ativo", "css_class": "sss-status-success", "icon": "status-success"})
        self.assertEqual(ui_helpers.active_info("N"),
                         {"label": u"Inativo", "css_class": "sss-status-cancelled", "icon": "status-cancelled"})

    def test_desconhecido(self):
        for flag in (None, "", "s", "X"):
            self.assertEqual(ui_helpers.active_info(flag)["label"], u"Desconhecido")


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
        texts = [ui_helpers.reason_description(m) for m in self.REASONS]
        self.assertTrue(all(texts))
        self.assertEqual(len(set(texts)), len(self.REASONS))

    def test_vazio_e_desconhecido(self):
        self.assertIsNone(ui_helpers.reason_description(None))
        self.assertIsNone(ui_helpers.reason_description(""))
        self.assertIn("OWNERSHIP_LOST", ui_helpers.reason_description("OWNERSHIP_LOST"))


class TestRecordPanel(unittest.TestCase):
    """Quadro Registro (CR-006, README §10): ator em linguagem simples e as duas frases."""

    def test_nome_ator(self):
        self.assertEqual(ui_helpers.actor_name("op.prod"), "op.prod")
        self.assertEqual(ui_helpers.actor_name("SYSTEM:agt-host01"), u"Sistema (agente agt-host01)")
        self.assertEqual(ui_helpers.actor_name("SYSTEM:init_db"), u"Sistema (instalação)")
        self.assertEqual(ui_helpers.actor_name("SYSTEM:seed"), u"Sistema (dados de demonstração)")
        self.assertEqual(ui_helpers.actor_name("SYSTEM"), u"Sistema")
        self.assertEqual(ui_helpers.actor_name(None), "-")

    def test_registro_mascara_sem_mudar_origem(self):
        created = datetime.datetime(2026, 10, 17, 9, 5)
        raw = {"created_at": created, "created_by": "editor.privado",
                 "updated_at": created, "updated_by": "op.prod"}
        for ctx, expected in (({"login": "op.prod"}, (u"outra pessoa", u"você")),
                              ({"is_admin": True}, ("editor.privado", "op.prod")),
                              ({"features": {"VIEW_AUDIT"}}, ("editor.privado", "op.prod")),
                              (None, (u"outra pessoa", u"outra pessoa"))):
            reg = ui_helpers.record_info(raw, ctx)
            self.assertEqual((reg["created_by"], reg["updated_by"]), expected)
            self.assertEqual(reg["created_at"], created)
        self.assertEqual(raw["created_by"], "editor.privado")
        self.assertEqual(ui_helpers.actor_name("SYSTEM:purge"), u"Sistema (limpeza)")

    def test_registro_e_exibicao(self):
        created = datetime.datetime(2026, 10, 17, 9, 5, 0)
        reg = ui_helpers.record_info({"id": 1, "created_at": created, "created_by": "SYSTEM:seed", "name": "x"}, {})
        self.assertEqual(reg, {"created_at": created, "created_by": "SYSTEM:seed", "updated_at": None,
                               "updated_by": None})
        self.assertEqual(ui_helpers.record_display(reg), {
            "created": u"17/10/2026 09:05:00 por Sistema (dados de demonstração)", "updated": u"Nunca alterado"})
        reg.update(updated_at=created + datetime.timedelta(hours=1), updated_by="admin")
        self.assertEqual(ui_helpers.record_display(reg)["updated"], u"17/10/2026 10:05:00 por admin")
        self.assertEqual(ui_helpers.record_info(None, {}), dict.fromkeys(ui_helpers.RECORD_COLUMNS))


class TestFormatDate(unittest.TestCase):

    def test_formato(self):
        self.assertEqual(ui_helpers.format_date(datetime.datetime(2026, 1, 5, 7, 3, 9)),
                         "05/01/2026 07:03:09")

    def test_none(self):
        self.assertEqual(ui_helpers.format_date(None), "-")


class TestFormatDuration(unittest.TestCase):
    T0 = datetime.datetime(2026, 10, 14, 10, 0, 0)

    def _dur(self, **delta):
        return ui_helpers.format_duration(self.T0, self.T0 + datetime.timedelta(**delta))

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
        self.assertEqual(ui_helpers.format_duration(None, self.T0), "-")
        self.assertEqual(ui_helpers.format_duration(self.T0, None), "-")
        self.assertEqual(ui_helpers.format_duration(None, None), "-")

    def test_fim_anterior_ao_inicio(self):
        self.assertEqual(self._dur(seconds=-1), "-")


class TestSanitizePage(unittest.TestCase):

    def test_validos(self):
        self.assertEqual(ui_helpers.sanitize_page("3"), 3)
        self.assertEqual(ui_helpers.sanitize_page(3), 3)
        self.assertEqual(ui_helpers.sanitize_page("1"), 1)
        self.assertEqual(ui_helpers.sanitize_page("007"), 7)
        self.assertEqual(ui_helpers.sanitize_page("999999999"), 999999999)

    def test_invalidos_viram_padrao(self):
        for value in (None, "", " 3", "0", 0, "-1", -5, "abc", "1.5", 1.5, u"\u00b2", u"\u0663",
                      "1e3", True, False, ["2"], "1234567890"):
            with self.subTest(valor=value):
                self.assertEqual(ui_helpers.sanitize_page(value), 1)

    def test_padrao_customizado(self):
        self.assertEqual(ui_helpers.sanitize_page("x", default_value=4), 4)
        self.assertEqual(ui_helpers.sanitize_page("2", default_value=4), 2)


class TestSanitizeSize(unittest.TestCase):

    def test_permitidos(self):
        for value, expected in (("20", 20), (20, 20), ("50", 50), (50, 50), ("100", 100), (100, 100)):
            with self.subTest(valor=value):
                self.assertEqual(ui_helpers.sanitize_size(value), expected)

    def test_fora_da_lista_vira_primeiro(self):
        for value in ("30", 30, 0, "0", -20, "-20", None, "", "abc", True, "1000", ["50"]):
            with self.subTest(valor=value):
                self.assertEqual(ui_helpers.sanitize_size(value), 20)

    def test_permitidos_customizados(self):
        self.assertEqual(ui_helpers.sanitize_size("10", allowed=(10, 25)), 10)
        self.assertEqual(ui_helpers.sanitize_size("25", allowed=(10, 25)), 25)
        self.assertEqual(ui_helpers.sanitize_size("20", allowed=(10, 25)), 10)


class TestPaginationInfo(unittest.TestCase):

    def _summary(self, info):
        return (info["page"], info["total_pages"], info["has_previous"], info["has_next"],
                info["previous_page"], info["next_page"], info["first_record"], info["last_record"])

    def test_total_limitado_nao_corta_navegacao(self):
        info = ui_helpers.pagination_info(502, 20, 10001, True, 20)
        self.assertTrue(info["total_capped"])
        self.assertIsNone(info["total_pages"])
        self.assertEqual(info["page"], 502)
        self.assertEqual(info["next_page"], 503)
        self.assertTrue(info["has_next"])
        self.assertEqual((info["first_record"], info["last_record"]), (10021, 10040))
        end = ui_helpers.pagination_info(503, 20, 10001, True, 7)
        self.assertFalse(end["has_next"])
        self.assertEqual(end["last_record"], 10047)
        empty = ui_helpers.pagination_info(504, 20, 10001, True, 0)
        self.assertFalse(empty["has_next"])
        self.assertTrue(empty["has_previous"])
        self.assertEqual((empty["first_record"], empty["last_record"]), (0, 0))
        self.assertFalse(ui_helpers.pagination_info(1, 20, 10000)["total_capped"])

    def test_total_zero(self):
        info = ui_helpers.pagination_info(1, 20, 0)
        self.assertEqual(self._summary(info), (1, 1, False, False, 1, 1, 0, 0))
        self.assertEqual(self._summary(ui_helpers.pagination_info(5, 20, 0)), self._summary(info))

    def test_pagina_zero_e_negativa(self):
        for page in (0, -1, "0", "-3", None, "abc"):
            with self.subTest(pagina=page):
                self.assertEqual(self._summary(ui_helpers.pagination_info(page, 20, 57)),
                                 (1, 3, False, True, 1, 2, 1, 20))

    def test_pagina_alem_do_total(self):
        self.assertEqual(self._summary(ui_helpers.pagination_info(99, 20, 57)),
                         (3, 3, True, False, 2, 3, 41, 57))
        self.assertEqual(self._summary(ui_helpers.pagination_info("4", 20, 57))[0], 3)

    def test_meio(self):
        self.assertEqual(self._summary(ui_helpers.pagination_info(2, 20, 57)),
                         (2, 3, True, True, 1, 3, 21, 40))

    def test_ultima_exata(self):
        self.assertEqual(self._summary(ui_helpers.pagination_info(2, 20, 40)),
                         (2, 2, True, False, 1, 2, 21, 40))
        self.assertEqual(ui_helpers.pagination_info(1, 20, 20)["total_pages"], 1)
        self.assertEqual(ui_helpers.pagination_info(1, 20, 21)["total_pages"], 2)

    def test_um_registro(self):
        self.assertEqual(self._summary(ui_helpers.pagination_info(1, 50, 1)),
                         (1, 1, False, False, 1, 1, 1, 1))

    def test_tamanho_e_total_invalidos(self):
        info = ui_helpers.pagination_info(1, 0, 57)
        self.assertEqual((info["size"], info["total_pages"]), (20, 3))
        self.assertEqual(ui_helpers.pagination_info(1, -5, 57)["size"], 20)
        info = ui_helpers.pagination_info(3, 20, -1)
        self.assertEqual((info["total"], info["page"], info["total_pages"]), (0, 1, 1))
        self.assertEqual(ui_helpers.pagination_info(1, 20, None)["total"], 0)

    def test_chaves(self):
        self.assertEqual(sorted(ui_helpers.pagination_info(1, 20, 5)), sorted([
            "page", "size", "total", "total_pages", "total_capped", "has_previous", "has_next",
            "previous_page", "next_page", "first_record", "last_record"]))


class TestFirstInvalidField(unittest.TestCase):

    def test_ordem(self):
        fields = [{"name": "a"}, {"name": "b", "error": u"Obrigatório."}, {"name": "c", "error": u"Inválido."}]
        self.assertEqual(ui_helpers.first_invalid_field(fields), "b")

    def test_sem_erro(self):
        self.assertIsNone(ui_helpers.first_invalid_field([{"name": "a", "error": ""}, {"name": "b"}]))
        self.assertIsNone(ui_helpers.first_invalid_field([]))
        self.assertIsNone(ui_helpers.first_invalid_field(None))


class TestAlertInfo(unittest.TestCase):

    def test_tipos(self):
        expected = {
            "success": ("alert-success", "status-success", "status"),
            "warning": ("alert-warning", "icon-alert", "status"),
            "error": ("alert-danger", "status-failed", "alert"),
        }
        for kind, (cls_name, icon, role) in expected.items():
            with self.subTest(tipo=kind):
                self.assertEqual(ui_helpers.alert_info({"kind": kind, "message": u"Mensagem"}), {
                    "kind": kind, "message": u"Mensagem", "css_class": cls_name, "icon": icon, "role": role})

    def test_formatos_de_entrada(self):
        self.assertEqual(ui_helpers.alert_info(("error", u"Falhou."))["kind"], "error")
        self.assertEqual(ui_helpers.alert_info(["success", u"Ok."])["kind"], "success")
        info = ui_helpers.alert_info(u"Texto simples")
        self.assertEqual((info["kind"], info["message"]), ("warning", u"Texto simples"))

    def test_tipo_desconhecido_vira_aviso(self):
        for kind in ("info", "ERRO", None, "<script>"):
            with self.subTest(tipo=kind):
                self.assertEqual(ui_helpers.alert_info({"kind": kind, "message": "x"})["kind"], "warning")

    def test_sem_mensagem(self):
        for flash in (None, "", {}, {"kind": "error"}, {"kind": "error", "message": ""}, ("error", None)):
            with self.subTest(flash=flash):
                self.assertIsNone(ui_helpers.alert_info(flash))

    def test_icones_existem_no_sprite(self):
        ids = _ids_sprite()
        for kind in ("success", "warning", "error"):
            self.assertIn(ui_helpers.alert_info((kind, "x"))["icon"], ids)


class TestBuildMenu(unittest.TestCase):

    def _codes(self, menu):
        return [(s["section"], [i["code"] for i in s["items"]]) for s in menu]

    def test_admin_ve_catalogo_completo_na_ordem(self):
        menu = ui_menu.build_menu([], True)
        self.assertEqual(self._codes(menu), [
            ("OPERATION", ["EXEC_SCRIPT", "VIEW_LOGS", "DOWNLOAD_OUTPUT", "UPLOAD_INPUT", "MANAGE_SCHEDULES",
                           "VIEW_AUDIT"]),
            ("ADMIN", ["MANAGE_USERS", "MANAGE_PROFILES", "MANAGE_ENVIRONMENTS", "MANAGE_SCRIPTS",
                       "MANAGE_PARAMETERS", "MANAGE_SCHEDULES", "VIEW_AUDIT"]),
        ])
        self.assertEqual(self._codes(ui_menu.build_menu(None, "Y")), self._codes(menu))

    def test_admin_somente_true_ou_s(self):
        for flag in (False, "N", "s", "", None, 1, "True"):
            with self.subTest(flag=flag):
                self.assertEqual(ui_menu.build_menu([], flag), [])

    def test_filtra_por_funcionalidade_e_omite_secao_vazia(self):
        menu = ui_menu.build_menu(["VIEW_LOGS", "MANAGE_SCHEDULES"], False)
        self.assertEqual(self._codes(menu), [
            ("OPERATION", ["VIEW_LOGS", "MANAGE_SCHEDULES"]),
            ("ADMIN", ["MANAGE_SCHEDULES"]),
        ])
        self.assertEqual(self._codes(ui_menu.build_menu(["EXEC_SCRIPT"], False)),
                         [("OPERATION", ["EXEC_SCRIPT", "VIEW_LOGS"])])

    def test_tickets_aparece_com_exec_script_ou_view_logs(self):
        # CR-017: a lista de tickets aceita EXEC_SCRIPT (proprios), entao o menu tambem.
        for features in (["EXEC_SCRIPT"], ["VIEW_LOGS"]):
            with self.subTest(features=features):
                routes = [i["route"] for s in ui_menu.build_menu(features, False) for i in s["items"]]
                self.assertIn(("tickets", "index"), routes)
        item = [i for s in ui_menu.build_menu(["EXEC_SCRIPT"], False) for i in s["items"]
                if i["route"] == ("tickets", "index")][0]
        self.assertEqual(item["label"], u"Tickets")

    def test_agenda_e_agentes_no_menu_operacao(self):
        # CR-017c: Agenda (MANAGE_SCHEDULES) e Agentes (VIEW_AUDIT) deixam de depender de botao ou aba.
        menu = ui_menu.build_menu(["MANAGE_SCHEDULES", "VIEW_AUDIT"], False, ("audit", "agents"))
        ops = [i for s in menu if s["section"] == "OPERATION" for i in s["items"]]
        self.assertEqual([(i["label"], i["route"]) for i in ops],
                         [(u"Agenda", ("schedules", "agenda")), (u"Agentes", ("audit", "agents"))])
        self.assertEqual([i["active"] for i in ops], [False, True])
        admin = [i for s in menu if s["section"] == "ADMIN" for i in s["items"]]
        self.assertFalse(any(i["active"] for i in admin))

    def test_codigo_desconhecido_ou_caixa_diferente_ignorado(self):
        self.assertEqual(ui_menu.build_menu(["exec_script", "CANCEL_TICKET", "XYZ"], False), [])

    def test_item_completo_e_rota_ativa(self):
        menu = ui_menu.build_menu(["EXEC_SCRIPT", "VIEW_LOGS"], False, ("tickets", "index"))
        items = menu[0]["items"]
        self.assertEqual(menu[0]["title"], u"Operação")
        # CR-017b (README §5.8): um so item para rodar, que abre os cartoes; o disparo sai do menu.
        self.assertEqual(items[0], {
            "code": "EXEC_SCRIPT",
            "label": u"Rodar um script",
            "route": ("tickets", "catalog"),
            "icon": "icon-play",
            "active": False,
        })
        self.assertNotIn(("tickets", "new"), [i["route"] for i in items])
        self.assertTrue(items[1]["active"])
        self.assertEqual(ui_menu.build_menu(["EXEC_SCRIPT"], False)[0]["items"][0]["active"], False)

    def test_rotulos_do_catalogo_canonico(self):
        labels = {i["code"]: i["label"] for s in ui_menu.build_menu([], True) for i in s["items"]}
        self.assertEqual(labels["MANAGE_PARAMETERS"], u"Dicionário de Parâmetros")
        self.assertEqual(labels["MANAGE_USERS"], u"Gestão de Usuários")
        self.assertEqual(ui_menu.build_menu([], True)[1]["title"], u"Administração")

    def test_rotas_e_icones_ascii_e_icones_no_sprite(self):
        ids = _ids_sprite()
        for section in ui_menu.build_menu([], True):
            for item in section["items"]:
                for part in item["route"] + (item["icon"],):
                    self.assertTrue(re.match(r"^[a-z][a-z0-9_-]*$", part), part)
                self.assertIn(item["icon"], ids)

    def test_resultado_independente_entre_chamadas(self):
        menu = ui_menu.build_menu([], True)
        menu[0]["items"][0]["label"] = "alterado"
        self.assertEqual(ui_menu.build_menu([], True)[0]["items"][0]["label"], u"Rodar um script")


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
        for key in ui_helpers.MESSAGES:
            happened, todo = ui_helpers.message_parts(key, minutos=15)
            self.assertTrue(happened and todo, key)
        self.assertEqual(ui_helpers.message("conflict"),
                         u"Outra pessoa mudou este registro enquanto você editava. "
                         u"Recarregue a página para ver a versão nova e faça a sua alteração de novo.")

    def test_explicacao_por_situacao(self):
        e = ui_helpers.ticket_explanation
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
        pend = ui_helpers.ticket_steps({"status": "PENDING", "created_at": created,
                                         "scheduled_at": self.NOW + datetime.timedelta(hours=1)}, self.NOW)
        self.assertEqual([e["state_info"] for e in pend], ["done", "current", "pending", "pending"])
        self.assertTrue(pend[1]["when"].startswith(u"agendado para"))
        run = ui_helpers.ticket_steps({"status": "RUNNING", "created_at": created, "scheduled_at": created,
                                        "started_at": self.NOW - datetime.timedelta(minutes=2)}, self.NOW)
        self.assertEqual([e["state_info"] for e in run], ["done", "done", "current", "pending"])
        self.assertEqual(run[2]["when"], u"há 2 minutos")
        cancel = ui_helpers.ticket_steps({"status": "CANCELLED", "created_at": created, "scheduled_at": created,
                                         "finished_at": self.NOW}, self.NOW)
        self.assertEqual([e["state_info"] for e in cancel], ["done", "done", "skipped", "current"])
        self.assertEqual(cancel[2]["when"], u"não chegou a rodar")
        self.assertTrue(cancel[3]["when"].startswith(u"Cancelado"))
        ok = ui_helpers.ticket_steps({"status": "SUCCESS", "created_at": created, "scheduled_at": created,
                                       "started_at": created, "finished_at": self.NOW}, self.NOW)
        self.assertEqual([e["state_info"] for e in ok], ["done", "done", "done", "current"])

    def test_tempo_simples(self):
        self.assertEqual(ui_helpers.simple_time(30), u"menos de 1 minuto")
        self.assertEqual(ui_helpers.simple_time(60), u"1 minuto")
        self.assertEqual(ui_helpers.simple_time(3600), u"1 hora")
        self.assertEqual(ui_helpers.simple_time(7500), u"2 horas e 5 minutos")


if __name__ == "__main__":
    unittest.main()
