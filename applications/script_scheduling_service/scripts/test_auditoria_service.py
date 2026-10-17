# -*- coding: utf-8 -*-
"""Testes de auditoria_service.py e agentes_service.py (F6.1) sobre o backend FAKE com relogio injetado."""
import _testenv  # noqa: F401

import csv
import datetime
import io
import logging
import os
import unittest
from unittest import mock

import agentes_service
import auditoria_service
import auth_service
import masking
import repo_factory
import security
from admin_crud import AcessoNegado
from agentes_service import ATRASADO, EM_RISCO, OFFLINE, OK, Limiares, ServicoAgentes
from auditoria_service import FiltrosInvalidos, ServicoAuditoria
from ticket_service import ServicoTicket

IP = "10.7.8.9"
SENHA_DEV = "senha-dev-de-teste-123"
SEGREDO = "tok-auditoria-secreto-91"
LIMIARES = Limiares(10, 90, 180)
HOJE = datetime.date(2026, 10, 15)


def _ler_csv(blocos):
    corpo = b"".join(blocos)
    texto = corpo.decode("utf-8")
    return corpo, list(csv.reader(io.StringIO(texto.lstrip(u"﻿")), delimiter=";"))


class _Base(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(security, "ITERACOES", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_SENHA_DEV: SENHA_DEV})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configurar, None)

        self.auditoria = repo_factory.obter("auditoria")
        self.agentes = repo_factory.obter("agentes")
        self.catalogo = repo_factory.obter("catalogo")
        self.tickets = repo_factory.obter("tickets")
        self.rbac = repo_factory.obter("rbac")
        self.store = repo_factory._fake_store
        # Instante da carga do seed: o agt-host02 nasce com heartbeat congelado 30 s antes dele.
        self.base = self.store.agentes[2]["heartbeat_at"] + datetime.timedelta(seconds=30)
        self.agora = self.base
        self.store.definir_relogio(lambda: self.agora)

        self.log = logging.getLogger("sss_teste_aud")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        auth = auth_service.ServicoAuth(
            repo_factory.obter("usuarios"), self.rbac, self.catalogo, self.auditoria, 5, 900, self.log)
        self.ctx = {}
        for uid, login, perfil_id in ((1, "admin", 1), (2, "op.prod", 2), (4, "consulta", 4)):
            sessao = {"usuario_id": uid, "login": login, "perfil_id": perfil_id,
                      "perm_versao": self.rbac.perfis_obter(perfil_id)["perm_versao"]}
            self.ctx[login] = auth.revalidar(sessao)
        self.svc = ServicoAuditoria(self.auditoria, lambda: self.agora, self.log)
        self.svc_agentes = ServicoAgentes(self.agentes, self.catalogo, lambda: self.agora, LIMIARES, self.log)

    def _inserir(self, created_at, ator="admin", acao="CAD_ALTERAR", entidade="tbsss_scripts",
                 entidade_id=1, detalhe="x", ip="127.0.0.1"):
        aid = self.store.proximo_id("tbsss_auditoria")
        self.store.auditoria[aid] = {"id": aid, "ator": ator, "ip_origem": ip, "acao": acao, "entidade": entidade,
                                     "entidade_id": entidade_id, "detalhe": detalhe, "created_at": created_at}
        return aid

    def _exportacoes(self):
        return self.auditoria.listar(filtros={"acao": "AUD_EXPORTAR"}, pagina=1, tamanho=100)["itens"]


class TestFiltros(unittest.TestCase):

    def test_periodo_padrao_ultimos_7_dias(self):
        filtros, erros = auditoria_service.normalizar_filtros({}, HOJE)
        self.assertEqual(erros, {})
        self.assertEqual((filtros["de"], filtros["ate"]), ("2026-10-09", "2026-10-15"))
        filtros, _ = auditoria_service.normalizar_filtros({"ate": "2026-09-30"}, HOJE)
        self.assertEqual(filtros["de"], "2026-09-24")

    def test_periodo_maximo_90_dias(self):
        ok, erros = auditoria_service.normalizar_filtros({"de": "2026-07-18", "ate": "2026-10-15"}, HOJE)
        self.assertEqual(erros, {})
        _, erros = auditoria_service.normalizar_filtros({"de": "2026-07-17", "ate": "2026-10-15"}, HOJE)
        self.assertEqual(erros, {"de": auditoria_service.MSG_PERIODO})

    def test_periodo_longo_exige_filtro_seletivo(self):
        longo = {"de": "2025-10-15", "ate": "2026-10-15"}  # 366 dias
        for extra in ({"ator": "admin"}, {"entidade": "tbsss_usuarios", "entidade_id": "6"}):
            with self.subTest(extra=extra):
                _, erros = auditoria_service.normalizar_filtros(dict(longo, **extra), HOJE)
                self.assertEqual(erros, {})
        _, erros = auditoria_service.normalizar_filtros(dict(longo, entidade="tbsss_usuarios"), HOJE)
        self.assertEqual(erros, {"de": auditoria_service.MSG_PERIODO})
        _, erros = auditoria_service.normalizar_filtros({"de": "2025-10-14", "ate": "2026-10-15", "ator": "admin"},
                                                        HOJE)
        self.assertEqual(erros, {"de": auditoria_service.MSG_PERIODO_SELETIVO})

    def test_datas_invalidas_ou_invertidas(self):
        _, erros = auditoria_service.normalizar_filtros({"de": "2026-02-30"}, HOJE)
        self.assertEqual(erros, {"de": auditoria_service.MSG_DATA})
        filtros, erros = auditoria_service.normalizar_filtros({"de": "2026-10-10", "ate": "2026-10-01"}, HOJE)
        self.assertEqual(erros, {"ate": auditoria_service.MSG_INTERVALO})
        self.assertEqual(filtros["ate"], "2026-10-01")

    def test_allowlist_dos_demais_filtros(self):
        entrada = {"ator": "SYSTEM:agt-host01", "acao": "LOGIN_OK", "entidade": "tbsss_agentes",
                   "entidade_id": "12", "ip": "10.0.", "outro": "x"}
        filtros, erros = auditoria_service.normalizar_filtros(entrada, HOJE)
        self.assertEqual(erros, {})
        self.assertEqual(list(filtros), ["de", "ate", "ator", "acao", "entidade", "entidade_id", "ip"])
        self.assertEqual(filtros["entidade_id"], 12)
        invalidos = {"ator": "a b", "acao": "DROP", "entidade": "dual", "entidade_id": "-1", "ip": "1.1;x"}
        _, erros = auditoria_service.normalizar_filtros(invalidos, HOJE)
        self.assertEqual(sorted(erros), ["acao", "ator", "entidade", "entidade_id", "ip"])

    def test_filtros_repo_periodo_inclusivo(self):
        filtros, _ = auditoria_service.normalizar_filtros({"de": "2026-10-01", "ate": "2026-10-02", "ip": "127"}, HOJE)
        repo = auditoria_service.filtros_repo(filtros)
        self.assertEqual(repo["data_inicio"], datetime.datetime(2026, 10, 1))
        self.assertEqual(repo["data_fim"], datetime.datetime(2026, 10, 2, 23, 59, 59))
        self.assertEqual(repo["ip_origem"], "127")

    def test_catalogo_de_acoes(self):
        for acao in ("LOGIN_OK", "PERM_ALTERAR", "AGENTE_FIM", "PURGE", "AUD_EXPORTAR"):
            self.assertIn(acao, auditoria_service.ACOES)
        self.assertTrue(all(len(a) <= 30 for a in auditoria_service.ACOES))


class TestNeutralizacaoCsv(unittest.TestCase):

    def test_prefixos_perigosos(self):
        for valor in ("=CMD()", "+1", "-2", "@SUM(A1)", "\tx", "\rx"):
            with self.subTest(valor=valor):
                self.assertEqual(auditoria_service.neutralizar_csv(valor), "'" + valor)

    def test_valores_inofensivos(self):
        for valor in ("a=b", "LOGIN_OK", "", 15, None):
            with self.subTest(valor=valor):
                self.assertEqual(auditoria_service.neutralizar_csv(valor), valor)


class TestListar(_Base):

    def test_seed_nos_ultimos_7_dias_e_ordenacao(self):
        res = self.svc.listar(self.ctx["admin"], {}, 1, 100)
        self.assertEqual(res["erros"], {})
        self.assertEqual(res["total"], 30)
        chaves = [(i["created_at"], i["id"]) for i in res["itens"]]
        self.assertEqual(chaves, sorted(chaves, reverse=True))

    def test_periodo_padrao_exclui_antigos(self):
        antigo = self._inserir(self.base - datetime.timedelta(days=8))
        ids = [i["id"] for i in self.svc.listar(self.ctx["admin"], {}, 1, 100)["itens"]]
        self.assertNotIn(antigo, ids)
        de = (self.base - datetime.timedelta(days=8)).strftime("%Y-%m-%d")
        ids = [i["id"] for i in self.svc.listar(self.ctx["admin"], {"de": de}, 1, 100)["itens"]]
        self.assertIn(antigo, ids)

    def test_filtros(self):
        casos = (
            ({"acao": "LOGIN_OK"}, 4),
            ({"ator": "op.prod"}, 3),
            ({"ator": "system:agt"}, 2),
            ({"entidade": "tbsss_usuarios", "entidade_id": "6"}, 3),
            ({"ip": "127.0"}, 30),
            ({"ip": "10.9"}, 0),
        )
        for entrada, total in casos:
            with self.subTest(entrada=entrada):
                self.assertEqual(self.svc.listar(self.ctx["admin"], entrada, 1, 100)["total"], total)

    def test_tamanho_maximo_100(self):
        for _ in range(130):
            self._inserir(self.base)
        res = self.svc.listar(self.ctx["admin"], {}, 1, 500)
        self.assertEqual((res["tamanho"], len(res["itens"])), (100, 100))

    def test_filtro_invalido_nao_consulta(self):
        with mock.patch.object(self.auditoria, "listar") as listar:
            res = self.svc.listar(self.ctx["admin"], {"acao": "XPTO"}, 1, 20)
        listar.assert_not_called()
        self.assertEqual((res["total"], sorted(res["erros"])), (0, ["acao"]))

    def test_rbac(self):
        for login in ("consulta", "op.prod"):
            with self.subTest(login=login):
                with self.assertRaises(AcessoNegado):
                    self.svc.listar(self.ctx[login], {}, 1, 20)

    def test_detalhe_truncado_e_mascarado(self):
        masking.registrar_segredo(SEGREDO)
        longo = u"campo: " + u"á" * 120
        aid_longo = self._inserir(self.base, detalhe=longo)
        aid_seg = self._inserir(self.base, detalhe=u"valor vazado %s" % SEGREDO)
        itens = dict((i["id"], i) for i in self.svc.listar(self.ctx["admin"], {}, 1, 100)["itens"])
        self.assertTrue(itens[aid_longo]["truncado"])
        self.assertEqual(len(itens[aid_longo]["detalhe_curto"]), auditoria_service.DETALHE_CURTO)
        self.assertEqual(itens[aid_longo]["detalhe"], longo)
        self.assertNotIn(SEGREDO, itens[aid_seg]["detalhe"])

    def test_seed_sem_segredos(self):
        res = self.svc.listar(self.ctx["admin"], {}, 1, 100)
        for item in res["itens"]:
            for valor in item.values():
                if isinstance(valor, str):
                    self.assertNotIn(SENHA_DEV, valor)
                    self.assertNotIn("pbkdf2", valor.lower())

    def test_link_entidade_respeita_permissao(self):
        admin, prod = self.ctx["admin"], self.ctx["op.prod"]
        link = auditoria_service.link_entidade
        self.assertEqual(link(admin, "tbsss_tickets", 11, True), ("tickets", "detalhe", [11]))
        self.assertEqual(link(admin, "tbsss_usuarios", 6, True), ("admin_usuarios", "form", [6]))
        self.assertIsNone(link(prod, "tbsss_usuarios", 6, True))
        self.assertIsNone(link(prod, "tbsss_tickets", 11, False))
        self.assertIsNone(link(admin, "tbsss_agentes", 1, True))
        self.assertIsNone(link(admin, "tbsss_tickets", None, True))


class TestExportar(_Base):

    def test_csv_injection_neutralizado(self):
        aid = self._inserir(self.base, detalhe="=CMD()", ator="admin")
        self._inserir(self.base, detalhe="-1+2", ip="@evil")
        _, linhas, blocos = self.svc.exportar_csv(self.ctx["admin"], IP, {})
        corpo, tabela = _ler_csv(blocos)
        self.assertTrue(corpo.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(tabela[0], list(auditoria_service.CABECALHO_CSV))
        por_id = dict((r[0], r) for r in tabela[1:])
        self.assertEqual(por_id[str(aid)][7], "'=CMD()")
        detalhes = [r[7] for r in tabela[1:]]
        self.assertIn("'-1+2", detalhes)
        self.assertIn("'@evil", [r[3] for r in tabela[1:]])
        self.assertEqual(len(tabela) - 1, linhas)

    def test_respeita_filtros(self):
        _, linhas, blocos = self.svc.exportar_csv(self.ctx["admin"], IP, {"acao": "LOGIN_OK"})
        _, tabela = _ler_csv(blocos)
        self.assertEqual(linhas, 4)
        self.assertEqual(set(r[4] for r in tabela[1:]), {"LOGIN_OK"})

    def test_exportacao_auditada_e_fora_do_proprio_arquivo(self):
        nome, linhas, blocos = self.svc.exportar_csv(self.ctx["admin"], IP, {"ator": "admin"})
        regs = self._exportacoes()
        self.assertEqual(len(regs), 1)
        reg = regs[0]
        self.assertEqual((reg["ator"], reg["ip_origem"], reg["entidade"], reg["entidade_id"]),
                         ("admin", IP, "tbsss_auditoria", None))
        self.assertIn("ator=admin", reg["detalhe"])
        self.assertIn("linhas: %d" % linhas, reg["detalhe"])
        self.assertTrue(nome.startswith("auditoria_") and nome.endswith(".csv"))
        _, tabela = _ler_csv(blocos)
        self.assertNotIn(str(reg["id"]), [r[0] for r in tabela[1:]])
        self.assertEqual(len(tabela) - 1, linhas)

    def test_quantidade_registrada_e_a_do_recorte_exportado(self):
        # CR-003 P9 (README §4.4): linhas gravadas depois da reserva do id nao entram nem na contagem nem no arquivo.
        _nome, linhas, blocos = self.svc.exportar_csv(self.ctx["admin"], IP, {"ator": "admin"})
        self.auditoria.registrar("admin", IP, "CAD_ALTERAR", "tbsss_ambientes", 1, "depois da exportacao")
        _, tabela = _ler_csv(blocos)
        self.assertEqual(len(tabela) - 1, linhas)
        self.assertIn("linhas: %d" % linhas, self._exportacoes()[0]["detalhe"])

    def test_limite_de_linhas(self):
        for _ in range(auditoria_service.LIMITE_EXPORTACAO + 20):
            self._inserir(self.base)
        resultado = self.auditoria.listar(tamanho=1)
        self.assertEqual(resultado["total"], 10001)
        self.assertTrue(resultado["total_limitado"])
        _, linhas, blocos = self.svc.exportar_csv(self.ctx["admin"], IP, {})
        _, tabela = _ler_csv(blocos)
        self.assertEqual(linhas, auditoria_service.LIMITE_EXPORTACAO)
        self.assertEqual(len(tabela) - 1, auditoria_service.LIMITE_EXPORTACAO)
        self.assertIn("limite %d" % auditoria_service.LIMITE_EXPORTACAO, self._exportacoes()[0]["detalhe"])

    def test_streaming_em_blocos(self):
        for _ in range(1200):
            self._inserir(self.base)
        _, _, blocos = self.svc.exportar_csv(self.ctx["admin"], IP, {})
        self.assertGreaterEqual(len(list(blocos)), 3)

    def test_rbac_e_filtros_invalidos_nao_auditam(self):
        with self.assertRaises(AcessoNegado):
            self.svc.exportar_csv(self.ctx["consulta"], IP, {})
        with self.assertRaises(FiltrosInvalidos) as cm:
            self.svc.exportar_csv(self.ctx["admin"], IP, {"de": "2020-01-01"})
        self.assertIn("de", cm.exception.erros)
        self.assertEqual(self._exportacoes(), [])


class TestSaudeAgente(unittest.TestCase):

    AGORA = datetime.datetime(2026, 10, 15, 12, 0, 0)

    def _saude(self, idade_s, status="ATIVO"):
        hb = None if idade_s is None else self.AGORA - datetime.timedelta(seconds=idade_s)
        return agentes_service.saude({"status": status, "heartbeat_at": hb}, self.AGORA, LIMIARES)

    def test_quatro_limiares(self):
        casos = ((0, OK), (19, OK), (20, ATRASADO), (90, ATRASADO), (91, EM_RISCO), (180, EM_RISCO),
                 (181, OFFLINE), (-5, OK))
        for idade, esperado in casos:
            with self.subTest(idade=idade):
                self.assertEqual(self._saude(idade), esperado)

    def test_parado_ou_sem_heartbeat_offline(self):
        self.assertEqual(self._saude(0, "PARADO"), OFFLINE)
        self.assertEqual(self._saude(None), OFFLINE)

    def test_info_e_legenda(self):
        self.assertEqual([i["codigo"] for i in agentes_service.legenda()], [OK, ATRASADO, EM_RISCO, OFFLINE])
        for info in agentes_service.legenda():
            self.assertTrue(info["rotulo"] and info["classe"] and info["icone"] and info["descricao"])

    def test_formatar_idade(self):
        self.assertEqual(agentes_service.formatar_idade(None), u"sem heartbeat")
        self.assertEqual(agentes_service.formatar_idade(42), u"há 42 s")
        self.assertEqual(agentes_service.formatar_idade(119), u"há 119 s")
        self.assertEqual(agentes_service.formatar_idade(600), u"há 10 min")
        self.assertEqual(agentes_service.formatar_idade(10800), u"há 3 h")
        self.assertEqual(agentes_service.formatar_idade(3 * 86400), u"há 3 dias")


class TestPainelAgentes(_Base):

    def _saudes(self, agora=None):
        painel = self.svc_agentes.painel(self.ctx["admin"], agora)
        return dict((a["codigo"], a["saude"]["codigo"]) for a in painel["agentes"])

    def test_seed_em_estados_diferentes_mudando_com_o_relogio(self):
        self.assertEqual(self._saudes(), {"agt-host01": OK, "agt-host02": ATRASADO})
        self.agora = self.base + datetime.timedelta(seconds=70)
        self.assertEqual(self._saudes(), {"agt-host01": OK, "agt-host02": EM_RISCO})
        self.agora = self.base + datetime.timedelta(seconds=160)
        self.assertEqual(self._saudes(), {"agt-host01": OK, "agt-host02": OFFLINE})

    def test_campos_e_tickets_running(self):
        painel = self.svc_agentes.painel(self.ctx["admin"])
        self.assertEqual(painel["agora"], self.base)
        ag = painel["agentes"][0]
        for campo in ("codigo", "hostname", "status", "versao", "ambientes", "iniciado_em", "heartbeat_at",
                      "saude", "running", "ha"):
            self.assertIn(campo, ag)
        for ag in painel["agentes"]:
            esperado = [t["id"] for t in self.agentes.tickets_running(ag["codigo"])]
            self.assertEqual([t["id"] for t in ag["tickets"]], esperado)
            self.assertEqual(ag["running"], len(esperado))
        self.assertEqual(sum(painel["resumo"].values()), 2)
        segundo = [a for a in painel["agentes"] if a["codigo"] == "agt-host02"][0]
        self.assertEqual((segundo["idade_s"], segundo["ha"]), (30, u"há 30 s"))

    def test_tickets_do_agente(self):
        itens = self.svc_agentes.tickets_do_agente(self.ctx["admin"], "agt-host01")
        self.assertEqual([t["id"] for t in itens], [11, 13, 15])
        self.assertTrue(all(t["script_nome"] for t in itens))
        self.assertEqual(self.svc_agentes.tickets_do_agente(self.ctx["admin"], "inexistente"), [])

    def test_somente_leitura_e_rbac(self):
        antes = [dict(a) for a in self.store.agentes.values() if a["codigo"] == "agt-host02"]
        self.svc_agentes.painel(self.ctx["admin"])
        depois = [dict(a) for a in self.store.agentes.values() if a["codigo"] == "agt-host02"]
        self.assertEqual(antes, depois)
        for login in ("consulta", "op.prod"):
            with self.subTest(login=login):
                with self.assertRaises(AcessoNegado):
                    self.svc_agentes.painel(self.ctx[login])
                with self.assertRaises(AcessoNegado):
                    self.svc_agentes.tickets_do_agente(self.ctx[login], "agt-host01")


class TestResumoInicial(_Base):

    def setUp(self):
        _Base.setUp(self)
        self.svc_tickets = ServicoTicket(self.catalogo, self.tickets, (0,), self.log)

    def test_escopo_por_perfil(self):
        admin = self.svc_tickets.resumo_inicial(self.ctx["admin"])
        prod = self.svc_tickets.resumo_inicial(self.ctx["op.prod"])
        consulta = self.svc_tickets.resumo_inicial(self.ctx["consulta"])
        self.assertEqual([s for s, _ in admin["contagem"]], ["PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED"])
        self.assertEqual(admin["desde"], self.base - datetime.timedelta(hours=24))
        total_admin = sum(q for _, q in admin["contagem"])
        self.assertGreater(total_admin, 0)
        self.assertLessEqual(sum(q for _, q in prod["contagem"]), total_admin)
        self.assertLessEqual(len(admin["meus"]), 5)
        self.assertTrue(all(t["solicitante"] == "admin" for t in admin["meus"]))
        self.assertTrue(all(t["solicitante"] == "op.prod" for t in prod["meus"]))
        self.assertEqual(consulta["meus"], [])

    def test_contagem_igual_a_lista(self):
        resumo = self.svc_tickets.resumo_inicial(self.ctx["op.prod"])
        desde = resumo["desde"]
        itens = self.tickets.listar(filtros={"criado_inicio": desde}, pagina=1, tamanho=1000,
                                    escopo_ambientes=["HOMOLOGACAO", "PRODUCAO"])["itens"]
        for status, qtd in resumo["contagem"]:
            with self.subTest(status=status):
                self.assertEqual(qtd, len([t for t in itens if t["status"] == status]))

    def test_sem_consulta_retorna_none(self):
        sem_func = dict(self.ctx["consulta"], funcionalidades=frozenset())
        self.assertIsNone(self.svc_tickets.resumo_inicial(sem_func))


if __name__ == "__main__":
    unittest.main()
