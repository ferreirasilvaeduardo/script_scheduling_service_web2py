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
            "PENDING": (u"Esperando", "sss-status-pending", "status-pending"),
            "RUNNING": (u"Rodando", "sss-status-running", "status-running"),
            "SUCCESS": (u"Deu certo", "sss-status-success", "status-success"),
            "FAILED": (u"Deu erro", "sss-status-failed", "status-failed"),
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
        self.assertEqual(ui_helpers.status_info("FAILED")["rotulo"], u"Deu erro")

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


class TestQuadroRegistro(unittest.TestCase):
    """Quadro Registro (CR-006, README §10): ator em linguagem simples e as duas frases."""

    def test_nome_ator(self):
        self.assertEqual(ui_helpers.nome_ator("op.prod"), "op.prod")
        self.assertEqual(ui_helpers.nome_ator("SYSTEM:agt-host01"), u"Sistema (agente agt-host01)")
        self.assertEqual(ui_helpers.nome_ator("SYSTEM:init_db"), u"Sistema (instalação)")
        self.assertEqual(ui_helpers.nome_ator("SYSTEM:seed"), u"Sistema (dados de demonstração)")
        self.assertEqual(ui_helpers.nome_ator("SYSTEM"), u"Sistema")
        self.assertEqual(ui_helpers.nome_ator(None), "-")

    def test_registro_e_exibicao(self):
        criado = datetime.datetime(2026, 10, 17, 9, 5, 0)
        reg = ui_helpers.registro({"id": 1, "created_at": criado, "created_by": "SYSTEM:seed", "nome": "x"})
        self.assertEqual(reg, {"created_at": criado, "created_by": "SYSTEM:seed", "updated_at": None,
                               "updated_by": None})
        self.assertEqual(ui_helpers.registro_exibicao(reg), {
            "criado": u"17/10/2026 09:05:00 por Sistema (dados de demonstração)", "alterado": u"Nunca alterado"})
        reg.update(updated_at=criado + datetime.timedelta(hours=1), updated_by="admin")
        self.assertEqual(ui_helpers.registro_exibicao(reg)["alterado"], u"17/10/2026 10:05:00 por admin")
        self.assertEqual(ui_helpers.registro(None), dict.fromkeys(ui_helpers.COLUNAS_REGISTRO))


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
            ("OPERACAO", ["EXEC_SCRIPT", "EXEC_SCRIPT", "VER_LOGS"]),
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
                         [("OPERACAO", ["EXEC_SCRIPT", "EXEC_SCRIPT"])])

    def test_codigo_desconhecido_ou_caixa_diferente_ignorado(self):
        self.assertEqual(ui_menu.montar_menu(["exec_script", "CANC_TICKET", "XYZ"], False), [])

    def test_item_completo_e_rota_ativa(self):
        menu = ui_menu.montar_menu(["EXEC_SCRIPT", "VER_LOGS"], False, ("tickets", "lista"))
        itens = menu[0]["itens"]
        self.assertEqual(menu[0]["titulo"], u"Operação")
        # CR-004 U5 (README §5.8): "Rotinas disponíveis" vem antes de "Disparar Scripts".
        self.assertEqual(itens[0]["rota"], ("tickets", "catalogo"))
        self.assertEqual(itens[1], {
            "codigo": "EXEC_SCRIPT",
            "rotulo": u"Disparar Scripts",
            "rota": ("tickets", "novo"),
            "icone": "icon-play",
            "ativo": False,
        })
        self.assertTrue(itens[2]["ativo"])
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
        self.assertEqual(ui_menu.montar_menu([], True)[0]["itens"][0]["rotulo"], u"Rotinas disponíveis")


class TestModulosPurosSemGluon(unittest.TestCase):

    def test_nao_importam_gluon(self):
        for nome in ("ui_helpers", "ui_menu"):
            caminho = sys.modules[nome].__file__
            with open(caminho, "r", encoding="utf-8") as f:
                self.assertNotRegex(f.read(), r"^\s*(from|import)\s+gluon", nome)


class TestLinguagemClara(unittest.TestCase):
    """CR-004 U1 (README §2.4.2, §5.2.1)."""

    AGORA = datetime.datetime(2026, 10, 16, 10, 0, 0)

    def test_mensagens_padrao_em_duas_partes(self):
        for chave in ui_helpers.MENSAGENS:
            aconteceu, fazer = ui_helpers.mensagem_partes(chave, minutos=15)
            self.assertTrue(aconteceu and fazer, chave)
        self.assertEqual(ui_helpers.mensagem("conflito"),
                         u"Outra pessoa mudou este registro enquanto você editava. "
                         u"Recarregue a página para ver a versão nova e faça a sua alteração de novo.")

    def test_explicacao_por_situacao(self):
        e = ui_helpers.explicacao_ticket
        futuro = self.AGORA + datetime.timedelta(hours=2)
        self.assertEqual(e({"status": "PENDING", "scheduled_at": futuro}, self.AGORA)["aconteceu"],
                         u"Está agendado para começar em 16/10/2026 às 12:00.")
        self.assertEqual(e({"status": "PENDING", "scheduled_at": self.AGORA}, self.AGORA)["aconteceu"],
                         u"Está na fila, esperando um servidor livre.")
        rodando = {"status": "RUNNING", "started_at": self.AGORA - datetime.timedelta(minutes=4)}
        self.assertEqual(e(rodando, self.AGORA)["aconteceu"], u"Está rodando agora. Começou há 4 minutos.")
        self.assertIn(u"cancelamento foi pedido", e(dict(rodando, cancel_requested="S"), self.AGORA)["aconteceu"])
        erro = e({"status": "FAILED", "status_motivo": "EXIT_ERROR", "return_code": 3}, self.AGORA)
        self.assertEqual((erro["situacao"], erro["aconteceu"]),
                         (u"Deu erro", u"O script rodou, mas terminou avisando que algo deu errado (código 3)."))
        self.assertIn(u"6 horas", e({"status": "FAILED", "status_motivo": "TIMEOUT"}, self.AGORA, 21600)["aconteceu"])
        self.assertIsNone(e({"status": "SUCCESS", "status_motivo": "EXIT_OK"}, self.AGORA)["fazer"])
        self.assertIn("XYZ", e({"status": "FAILED", "status_motivo": "XYZ"}, self.AGORA)["aconteceu"])

    def test_etapas_do_ticket(self):
        # CR-004 U2 (README §5.7).
        criado = self.AGORA - datetime.timedelta(minutes=10)
        pend = ui_helpers.etapas_ticket({"status": "PENDING", "created_at": criado,
                                         "scheduled_at": self.AGORA + datetime.timedelta(hours=1)}, self.AGORA)
        self.assertEqual([e["estado"] for e in pend], ["feito", "atual", "pendente", "pendente"])
        self.assertTrue(pend[1]["quando"].startswith(u"agendado para"))
        rod = ui_helpers.etapas_ticket({"status": "RUNNING", "created_at": criado, "scheduled_at": criado,
                                        "started_at": self.AGORA - datetime.timedelta(minutes=2)}, self.AGORA)
        self.assertEqual([e["estado"] for e in rod], ["feito", "feito", "atual", "pendente"])
        self.assertEqual(rod[2]["quando"], u"há 2 minutos")
        canc = ui_helpers.etapas_ticket({"status": "CANCELLED", "created_at": criado, "scheduled_at": criado,
                                         "finished_at": self.AGORA}, self.AGORA)
        self.assertEqual([e["estado"] for e in canc], ["feito", "feito", "pulado", "atual"])
        self.assertEqual(canc[2]["quando"], u"não chegou a rodar")
        self.assertTrue(canc[3]["quando"].startswith(u"Cancelado"))
        ok = ui_helpers.etapas_ticket({"status": "SUCCESS", "created_at": criado, "scheduled_at": criado,
                                       "started_at": criado, "finished_at": self.AGORA}, self.AGORA)
        self.assertEqual([e["estado"] for e in ok], ["feito", "feito", "feito", "atual"])

    def test_tempo_simples(self):
        self.assertEqual(ui_helpers.tempo_simples(30), u"menos de 1 minuto")
        self.assertEqual(ui_helpers.tempo_simples(60), u"1 minuto")
        self.assertEqual(ui_helpers.tempo_simples(3600), u"1 hora")
        self.assertEqual(ui_helpers.tempo_simples(7500), u"2 horas e 5 minutos")


if __name__ == "__main__":
    unittest.main()
