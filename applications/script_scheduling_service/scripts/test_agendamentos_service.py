# -*- coding: utf-8 -*-
"""Testes de agendamentos_service.py (F5.2) sobre o backend FAKE com relogio injetavel."""
import _testenv  # noqa: F401

import datetime
import json
import logging
import os
import unittest
from unittest import mock

import admin_crud
import agendamentos_service as svc_mod
import auth_service
import repo_factory
import security
from admin_crud import CAMPO_GERAL, AcessoNegado, OperacaoNegada
from agendamentos_service import ServicoAgendamentos
from repo_errors import RepoConflito, RepoNaoEncontrado
from ticket_service import ServicoTicket

IP = "10.4.5.6"
# Quinta-feira; os microssegundos provam que nenhuma data gravada os carrega (README §7.1).
AGORA = datetime.datetime(2026, 1, 15, 10, 0, 0, 123456)
HORIZONTE = 1461
SEGREDO = "tok-ultra-secreto-77"
PERFIL_OP_PROD, PERFIL_OP_HML = 2, 3
FUNC_EXEC, FUNC_LOGS, FUNC_CANC, FUNC_CAD_AGD = 1, 2, 3, 9
SETA = u" → "


class _Base(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(security, "ITERACOES", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_SENHA_DEV: "senha-dev-de-teste-123"})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configurar, None)

        self.catalogo = repo_factory.obter("catalogo")
        self.agd = repo_factory.obter("agendamentos")
        self.auditoria = repo_factory.obter("auditoria")
        self.rbac = repo_factory.obter("rbac")
        self.log = logging.getLogger("sss_teste_agd")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        self.auth = auth_service.ServicoAuth(
            repo_factory.obter("usuarios"), self.rbac, self.catalogo, self.auditoria, 5, 900, self.log)

        # CAD_AGENDAMENTOS para os operadores (no seed, so o admin a tem).
        self.rbac.matriz_salvar(PERFIL_OP_PROD, [FUNC_EXEC, FUNC_LOGS, FUNC_CANC, FUNC_CAD_AGD], [1, 2], [1, 2, 3, 6], ator="teste")
        self.rbac.matriz_salvar(PERFIL_OP_HML, [FUNC_EXEC, FUNC_LOGS, FUNC_CANC, FUNC_CAD_AGD], [2, 3], [1, 2, 3, 4], ator="teste")
        self.ctx = {
            "admin": self._ctx(1, "admin", 1),
            "op.prod": self._ctx(2, "op.prod", PERFIL_OP_PROD),
            "op.hml": self._ctx(3, "op.hml", PERFIL_OP_HML),
            "consulta": self._ctx(4, "consulta", 4),
        }
        self.agora = AGORA
        self.tickets = repo_factory.obter("tickets")
        disparo = ServicoTicket(self.catalogo, self.tickets, (0,), self.log)
        self.svc = ServicoAgendamentos(self.agd, self.catalogo, repo_factory.obter("usuarios"), disparo,
                                       lambda: self.agora, HORIZONTE, self.log,
                                       tickets=self.tickets, rbac_repo=self.rbac)
        self.aud_base = max([a["id"] for a in self.auditoria.listar(pagina=1, tamanho=1000)["itens"]] or [0])

    def _ctx(self, usuario_id, login, perfil_id):
        sessao = {"usuario_id": usuario_id, "login": login, "perfil_id": perfil_id,
                  "perm_versao": self.rbac.perfis_obter(perfil_id)["perm_versao"]}
        return self.auth.revalidar(sessao)

    def _auditorias(self, acao=None):
        itens = self.auditoria.listar(filtros={"acao": acao} if acao else None, pagina=1, tamanho=1000)["itens"]
        return [a for a in itens if a["entidade"] == "tbsss_agendamentos" and a["id"] > self.aud_base]

    def _dados(self, **extra):
        dados = {"nome": "Regra de teste", "script_id": "1", "ambiente": "HOMOLOGACAO",
                 "tipo_recorrencia": "DIARIA", "hora_execucao": "03:00", "prioridade": "2",
                 "respostas": {"data_ref": "2026-01-20", "modo_exec": "SIMULACAO"}}
        dados.update(extra)
        return dados

    def _salvar(self, login="admin", **extra):
        return self.svc.salvar(self.ctx[login], IP, self._dados(**extra))

    def _versao(self, reg):
        # Como a tela: as respostas sensiveis do script entram pelo marcador (CR-003 P1).
        sensiveis = frozenset(v["codigo"] for v in repo_factory.obter("catalogo").script_params_obter(reg["script_id"])
                              if v.get("sensivel") == "S")
        return svc_mod.versao(reg, sensiveis)


class TestSalvarTipos(_Base):

    def test_valores_fora_do_formato_sao_recusados_nunca_cortados(self):
        # CR-003 P7 / D11 (README §7.6).
        casos = (
            ({"tipo_recorrencia": "MENSAL", "hora_execucao": "01:00", "dia_mes": "100"}, "dia_mes"),
            ({"tipo_recorrencia": "MENSAL", "hora_execucao": "01:00", "dia_mes": "311"}, "dia_mes"),
            ({"tipo_recorrencia": "DIARIA", "hora_execucao": "03:000"}, "hora_execucao"),
            ({"tipo_recorrencia": "DIARIA", "hora_execucao": "03:00", "data_inicio": "2026-02-01T10:00:00"},
             "data_inicio"),
            ({"tipo_recorrencia": "DIARIA", "hora_execucao": "03:00", "data_inicio": "2026-02-01T10:00:00.999"},
             "data_inicio"),
        )
        for extra, campo in casos:
            aid, erros = self._salvar(**extra)
            self.assertIsNone(aid, extra)
            self.assertIn(campo, erros, extra)

    def test_data_fim_ignorada_em_unica(self):
        aid, erros = self._salvar(tipo_recorrencia="UNICA", data_inicio="2026-02-01T08:30",
                                  data_fim="2026-01-01T00:00")
        self.assertEqual(erros, {})
        self.assertIsNone(self.agd.obter(aid)["data_fim"])

    def test_salvar_cada_tipo(self):
        casos = [
            ({"tipo_recorrencia": "UNICA", "data_inicio": "2026-02-01T08:30"}, datetime.datetime(2026, 2, 1, 8, 30)),
            ({"tipo_recorrencia": "DIARIA", "hora_execucao": "03:00"}, datetime.datetime(2026, 1, 16, 3, 0)),
            ({"tipo_recorrencia": "SEMANAL", "hora_execucao": "04:00", "dias_semana": ["5", "1", "3"]},
             datetime.datetime(2026, 1, 16, 4, 0)),
            ({"tipo_recorrencia": "MENSAL", "hora_execucao": "01:00", "dia_mes": "31"},
             datetime.datetime(2026, 1, 31, 1, 0)),
            ({"tipo_recorrencia": "CRON", "expressao_cron": "*/15 8-18 * * 1-5"},
             datetime.datetime(2026, 1, 15, 10, 15)),
        ]
        for extra, proxima in casos:
            aid, erros = self._salvar(**extra)
            self.assertEqual(erros, {}, extra)
            reg = self.agd.obter(aid)
            self.assertEqual(reg["proxima_execucao"], proxima, extra)
            self.assertEqual(reg["usuario_id"], 1)
            self.assertEqual(reg["ativo"], "S")
            self.assertIsNone(reg["pausa_motivo"])
            for campo in ("data_inicio", "data_fim", "proxima_execucao"):
                if reg[campo] is not None:
                    self.assertEqual(reg[campo].microsecond, 0, campo)
        semanal = self.agd.listar(filtros={"nome": "Regra de teste"}, tamanho=100)["itens"]
        self.assertIn("1,3,5", [r["dias_semana"] for r in semanal])

    def test_campos_de_outros_tipos_sao_descartados(self):
        aid, erros = self._salvar(tipo_recorrencia="DIARIA", hora_execucao="03:00", dia_mes="5",
                                  expressao_cron="* * * * *", dias_semana="1,2")
        self.assertEqual(erros, {})
        reg = self.agd.obter(aid)
        self.assertEqual((reg["dia_mes"], reg["expressao_cron"], reg["dias_semana"]), (None, None, None))

    def test_inicio_vazio_vale_agora_truncado(self):
        aid, _erros = self._salvar()
        self.assertEqual(self.agd.obter(aid)["data_inicio"], datetime.datetime(2026, 1, 15, 10, 0))

    def test_parametros_json_ordenado_com_resolvidos(self):
        aid, _erros = self._salvar(respostas={"modo_exec": "SIMULACAO", "data_ref": "2026-01-20",
                                              "verbose": ["false", "true"], "intruso": "x"})
        params = self.agd.obter(aid)["parametros_json"]
        obj = json.loads(params)
        self.assertEqual(list(obj), sorted(obj))
        self.assertEqual(obj["data_ref"], "2026-01-20")
        self.assertEqual(obj["verbose"], "true")
        self.assertEqual(obj["limite_linhas"], "5000")
        self.assertNotIn("intruso", obj)


class TestValidacao(_Base):

    def test_campos_obrigatorios_por_tipo(self):
        casos = [
            ({"tipo_recorrencia": "UNICA", "data_inicio": ""}, "data_inicio"),
            ({"tipo_recorrencia": "DIARIA", "hora_execucao": ""}, "hora_execucao"),
            ({"tipo_recorrencia": "SEMANAL", "hora_execucao": "04:00", "dias_semana": []}, "dias_semana"),
            ({"tipo_recorrencia": "MENSAL", "hora_execucao": "04:00", "dia_mes": ""}, "dia_mes"),
            ({"tipo_recorrencia": "CRON", "expressao_cron": ""}, "expressao_cron"),
            ({"tipo_recorrencia": "ANUAL"}, "tipo_recorrencia"),
            ({"nome": ""}, "nome"),
            ({"nome": "x" * 61}, "nome"),
        ]
        for extra, campo in casos:
            aid, erros = self._salvar(**extra)
            self.assertIsNone(aid, extra)
            self.assertIn(campo, erros, extra)
        self.assertEqual(self._auditorias(), [])

    def test_formatos_invalidos(self):
        casos = [
            ({"hora_execucao": "25:00"}, "hora_execucao"),
            ({"tipo_recorrencia": "SEMANAL", "dias_semana": ["1", "9"]}, "dias_semana"),
            ({"tipo_recorrencia": "MENSAL", "dia_mes": "32"}, "dia_mes"),
            ({"tipo_recorrencia": "MENSAL", "dia_mes": "x"}, "dia_mes"),
            ({"data_inicio": "15/01/2026"}, "data_inicio"),
            ({"data_inicio": "2026-01-20T10:00", "data_fim": "2026-01-19T10:00"}, "data_fim"),
        ]
        for extra, campo in casos:
            _aid, erros = self._salvar(**extra)
            self.assertIn(campo, erros, extra)

    def test_cron_invalido(self):
        for expr in ("0 0 * * MON", "* * *", "5/10 * * * *", "0 0 L * *", "61 * * * *"):
            aid, erros = self._salvar(tipo_recorrencia="CRON", expressao_cron=expr)
            self.assertIsNone(aid, expr)
            self.assertIn("expressao_cron", erros, expr)

    def test_cron_sem_ocorrencia_no_horizonte(self):
        _aid, erros = self._salvar(tipo_recorrencia="CRON", expressao_cron="0 0 30 2 *")
        self.assertIn("expressao_cron", erros)

    def test_sem_proxima_ocorrencia(self):
        aid, erros = self._salvar(tipo_recorrencia="UNICA", data_inicio="2026-01-15T09:00")
        self.assertIsNone(aid)
        self.assertEqual(erros, {CAMPO_GERAL: svc_mod.MSG_SEM_PROXIMA})
        _aid, erros = self._salvar(data_inicio="2026-01-01T00:00", data_fim="2026-01-10T00:00")
        self.assertEqual(erros, {CAMPO_GERAL: svc_mod.MSG_SEM_PROXIMA})

    def test_parametros_invalidos(self):
        aid, erros = self._salvar(respostas={"data_ref": "20/01/2026", "modo_exec": "INEXISTENTE",
                                             "limite_linhas": "abc"})
        self.assertIsNone(aid)
        self.assertEqual(set(erros), {"data_ref", "modo_exec", "limite_linhas"})
        self.assertNotIn("abc", json.dumps(erros, ensure_ascii=False))

    def test_prioridade_1_exclusiva_de_admin(self):
        _aid, erros = self._salvar(login="op.hml", prioridade="1")
        self.assertEqual(erros, {"prioridade": svc_mod.MSG_PRIORIDADE_ADMIN})
        _aid, erros = self._salvar(login="op.hml", prioridade="7")
        self.assertEqual(erros, {"prioridade": svc_mod.MSG_PRIORIDADE})
        aid, erros = self._salvar(prioridade="1")
        self.assertEqual(erros, {})
        self.assertEqual(self.agd.obter(aid)["prioridade"], 1)

    def test_script_ou_ambiente_nao_autorizado(self):
        with self.assertRaises(OperacaoNegada):
            self._salvar(login="op.hml", ambiente="PRODUCAO")
        with self.assertRaises(OperacaoNegada):
            self._salvar(login="op.prod", script_id="4")
        self.assertEqual(self._auditorias(), [])

    def test_perfil_sem_funcionalidade(self):
        with self.assertRaises(AcessoNegado):
            self._salvar(login="consulta")
        with self.assertRaises(AcessoNegado):
            self.svc.listar(self.ctx["consulta"], {}, 1, 20)
        with self.assertRaises(AcessoNegado):
            self.svc.previa(self.ctx["consulta"], {"tipo_recorrencia": "DIARIA", "hora_execucao": "03:00"})


class TestEdicao(_Base):

    def _editar(self, aid, login="admin", **extra):
        reg = self.agd.obter(aid)
        dados = self._dados(id=str(aid), versao=self._versao(reg), **extra)
        return self.svc.salvar(self.ctx[login], IP, dados)

    def test_edicao_troca_usuario_id_para_o_editor(self):
        aid, _erros = self._salvar(login="op.prod")
        self.assertEqual(self.agd.obter(aid)["usuario_id"], 2)
        _id, erros = self._editar(aid, login="admin", nome="Regra de teste")
        self.assertEqual(erros, {})
        self.assertEqual(self.agd.obter(aid)["usuario_id"], 1)
        alteracoes = self._auditorias("CAD_ALTERAR")
        self.assertEqual(len(alteracoes), 1)
        self.assertEqual(alteracoes[0]["ator"], "admin")
        self.assertEqual(alteracoes[0]["ip_origem"], IP)
        self.assertIn(u"usuario_id: 2 (op.prod)%s1 (admin)" % SETA, alteracoes[0]["detalhe"])

    def test_edicao_de_regra_do_seed_por_outro_usuario(self):
        # Regra 4: MENSAL, script 2 em HOMOLOGACAO, criada por op.hml (id 3).
        reg = self.agd.obter(4)
        dados = {"id": "4", "versao": self._versao(reg), "nome": reg["nome"], "tipo_recorrencia": "MENSAL",
                 "hora_execucao": "01:00", "dia_mes": "1", "prioridade": "3",
                 "data_inicio": reg["data_inicio"].strftime("%Y-%m-%dT%H:%M"),
                 "respostas": {"formato_saida": "JSON"}}
        _id, erros = self.svc.salvar(self.ctx["op.prod"], IP, dados)
        self.assertEqual(erros, {})
        self.assertEqual(self.agd.obter(4)["usuario_id"], 2)
        self.assertIn(u"usuario_id: 3 (op.hml)%s2 (op.prod)" % SETA, self._auditorias("CAD_ALTERAR")[0]["detalhe"])

    def test_mesmo_editor_sem_mudanca_nao_audita(self):
        aid, _erros = self._salvar()
        _id, erros = self._editar(aid)
        self.assertEqual(erros, {})
        self.assertEqual(self._auditorias("CAD_ALTERAR"), [])

    def test_mesmo_editor_com_mudanca_registra_usuario_id(self):
        aid, _erros = self._salvar()
        _id, erros = self._editar(aid, hora_execucao="05:00")
        self.assertEqual(erros, {})
        detalhe = self._auditorias("CAD_ALTERAR")[0]["detalhe"]
        self.assertIn(u"usuario_id: 1 (admin)%s1 (admin)" % SETA, detalhe)
        self.assertIn(u"hora_execucao: 03:00%s05:00" % SETA, detalhe)
        self.assertEqual(self.agd.obter(aid)["proxima_execucao"], datetime.datetime(2026, 1, 16, 5, 0))

    def test_editor_sem_permissao_e_negado(self):
        aid, _erros = self._salvar(script_id="4", respostas={})
        antes = self.agd.obter(aid)
        with self.assertRaises(OperacaoNegada) as cm:
            self._editar(aid, login="op.prod", hora_execucao="06:00", respostas={})
        self.assertEqual(cm.exception.mensagem, svc_mod.MSG_SEM_PERMISSAO)
        self.assertEqual(self.agd.obter(aid), antes)
        self.assertEqual(self._auditorias("CAD_ALTERAR"), [])
        with self.assertRaises(OperacaoNegada):
            self.svc.formulario(self.ctx["op.prod"], str(aid))

    def test_regra_fora_do_escopo_e_inexistente(self):
        # Regra 1 e de PRODUCAO; op.hml so enxerga HOMOLOGACAO e DESENV.
        with self.assertRaises(RepoNaoEncontrado):
            self.svc.formulario(self.ctx["op.hml"], "1")
        with self.assertRaises(RepoNaoEncontrado):
            self.svc.pausar(self.ctx["op.hml"], IP, "1")
        with self.assertRaises(RepoNaoEncontrado):
            self.svc.salvar(self.ctx["op.hml"], IP, self._dados(id="1"))
        with self.assertRaises(RepoNaoEncontrado):
            self.svc.formulario(self.ctx["admin"], "999")

    def test_script_e_ambiente_fixos_na_edicao(self):
        aid, _erros = self._salvar()
        _id, erros = self._editar(aid, script_id="2", ambiente="PRODUCAO")
        self.assertEqual(erros, {})
        reg = self.agd.obter(aid)
        self.assertEqual((reg["script_id"], reg["ambiente"]), (1, "HOMOLOGACAO"))

    def test_edicao_concorrente(self):
        aid, _erros = self._salvar()
        reg = self.agd.obter(aid)
        versao = self._versao(reg)
        self.agd.alterar(aid, {"nome": "Mudou por outro"}, ator="teste")
        _id, erros = self.svc.salvar(self.ctx["admin"], IP, self._dados(id=str(aid), versao=versao, nome="X"))
        self.assertEqual(erros, {CAMPO_GERAL: admin_crud.MSG_CONFLITO})
        # Mudanca entre a leitura e a escrita: o 'esperado' do repositorio barra.
        reg = self.agd.obter(aid)
        original = self.agd.alterar

        def alterar_com_corrida(id, dados, esperado=None, auditoria=None):
            original(id, {"hora_execucao": "07:00"}, ator="teste")
            return original(id, dados, esperado=esperado, auditoria=auditoria)

        with mock.patch.object(self.agd, "alterar", side_effect=alterar_com_corrida):
            _id, erros = self.svc.salvar(self.ctx["admin"], IP,
                                         self._dados(id=str(aid), versao=self._versao(reg), nome="Y"))
        self.assertEqual(erros, {CAMPO_GERAL: admin_crud.MSG_CONFLITO})
        self.assertEqual(self.agd.obter(aid)["nome"], "Mudou por outro")
        self.assertEqual(self._auditorias("CAD_ALTERAR"), [])

    def test_sensivel_nao_reexibido_e_vazio_mantem_valor(self):
        # CR-003 P1: a versao do formulario tambem nao deriva da resposta sensivel.
        aid0, _e = self._salvar(respostas={"data_ref": "2026-01-20", "modo_exec": "REAL", "documento_cliente": "tok-um-111"})
        v1 = self.svc.formulario(self.ctx["admin"], str(aid0))["regra"]["versao"]
        reg = self.agd.obter(aid0)
        trocado = json.loads(reg["parametros_json"])
        trocado["documento_cliente"] = "tok-dois-222"
        self.assertEqual(svc_mod.versao(dict(reg, parametros_json=json.dumps(trocado)), frozenset(["documento_cliente"])), v1)
        self.assertNotEqual(svc_mod.versao(reg), v1)
        aid, erros = self._salvar(respostas={"data_ref": "2026-01-20", "modo_exec": "REAL", "documento_cliente": SEGREDO})
        self.assertEqual(erros, {})
        dados = self.svc.formulario(self.ctx["admin"], str(aid))
        campo = [c for c in dados["form"]["campos"] if c["codigo"] == "documento_cliente"][0]
        self.assertTrue(campo["mantido"])
        self.assertIsNone(campo["valor"])
        self.assertNotIn(SEGREDO, json.dumps(dados, default=str))
        nao_sensivel = [c for c in dados["form"]["campos"] if c["codigo"] == "modo_exec"][0]
        self.assertEqual(nao_sensivel["valor"], "REAL")
        self.assertFalse(nao_sensivel["mantido"])

        _id, erros = self._editar(aid, hora_execucao="05:00",
                                  respostas={"data_ref": "2026-01-20", "modo_exec": "REAL", "documento_cliente": ""})
        self.assertEqual(erros, {})
        self.assertEqual(json.loads(self.agd.obter(aid)["parametros_json"])["documento_cliente"], SEGREDO)
        _id, erros = self._editar(aid, respostas={"data_ref": "2026-01-20", "modo_exec": "REAL",
                                                  "documento_cliente": "outro-token-99"})
        self.assertEqual(json.loads(self.agd.obter(aid)["parametros_json"])["documento_cliente"], "outro-token-99")
        for aud in self._auditorias():
            self.assertNotIn(SEGREDO, aud["detalhe"])
            self.assertNotIn("outro-token-99", aud["detalhe"])
        # A auditoria lista do mais novo para o mais antigo.
        self.assertIn(u"documento_cliente=%s (alterado)" % svc_mod.MASCARA, self._auditorias("CAD_ALTERAR")[0]["detalhe"])


class TestAgenda(_Base):

    def test_cron_valido_fora_da_semana_nao_e_problema(self):
        aid, erros = self._salvar(tipo_recorrencia="CRON", expressao_cron="0 0 1 12 *")
        self.assertEqual(erros, {})
        agenda = self.svc.agenda(self.ctx["admin"])
        self.assertFalse(any(item["regra_id"] == aid for item in agenda["problemas"]))

    """CR-004 U6 (README §7.7)."""

    def _regra(self, **campos):
        base = {"nome": "Agenda teste", "script_id": 1, "ambiente": "HOMOLOGACAO", "usuario_id": 1, "prioridade": 2,
                "tipo_recorrencia": "DIARIA", "hora_execucao": "03:00", "parametros_json": "{}",
                "data_inicio": datetime.datetime(2026, 1, 1, 0, 0),
                "proxima_execucao": datetime.datetime(2026, 1, 16, 3, 0)}
        base.update(campos)
        return self.agd.inserir(base, ator="teste")["id"]

    def _itens(self, dados, regra_id):
        return [o for d in dados["dias"] for o in d["itens"] if o["regra_id"] == regra_id]

    def test_diaria_sete_dias_com_rotulos(self):
        rid = self._regra()
        dados = self.svc.agenda(self.ctx["admin"])
        itens = self._itens(dados, rid)
        self.assertEqual(len(itens), 7)  # 16/01 a 22/01: ate o fim do 7o dia seguinte a 15/01
        rotulos = [d["rotulo"] for d in dados["dias"] if any(o["regra_id"] == rid for o in d["itens"])]
        self.assertEqual(rotulos[0], u"Amanhã")
        self.assertTrue(rotulos[1].startswith(u"sábado, 17/01"))

    def test_cron_a_cada_minuto_limitado_a_20_com_mais(self):
        rid = self._regra(tipo_recorrencia="CRON", hora_execucao=None, expressao_cron="* * * * *",
                          proxima_execucao=datetime.datetime(2026, 1, 15, 10, 1))
        itens = self._itens(self.svc.agenda(self.ctx["admin"]), rid)
        self.assertEqual(len(itens), svc_mod.AGENDA_POR_REGRA)
        self.assertGreater(itens[-1]["mais"], 0)

    def test_atrasada_pausada_e_escopo(self):
        atrasada = self._regra(proxima_execucao=datetime.datetime(2026, 1, 15, 3, 0))
        pausada = self._regra(ativo="N", pausa_motivo="MANUAL")
        em_prod = self._regra(ambiente="PRODUCAO")
        dados = self.svc.agenda(self.ctx["admin"])
        self.assertIn(atrasada, [a["regra_id"] for a in dados["atrasados"]])
        self.assertFalse(self._itens(dados, pausada))
        self.assertTrue(self._itens(dados, em_prod))
        # op.hml nao enxerga PRODUCAO (README §7.6, lista por escopo).
        self.assertFalse(self._itens(self.svc.agenda(self.ctx["op.hml"]), em_prod))

    def test_exige_cad_agendamentos(self):
        with self.assertRaises(AcessoNegado):
            self.svc.agenda(self.ctx["consulta"])


class TestPausaRetomada(_Base):

    def test_falha_de_rbac_nao_retoma_nem_audita(self):
        aid, erros = self._salvar()
        self.assertEqual(erros, {})
        self.svc.pausar(self.ctx["admin"], IP, str(aid))
        antes = self.agd.obter(aid)
        auditorias = self._auditorias()
        with mock.patch.object(self.rbac, "matriz_obter", side_effect=RuntimeError("indisponivel")):
            with self.assertRaises(RuntimeError):
                self.svc.retomar(self.ctx["admin"], IP, str(aid))
        self.assertEqual(self.agd.obter(aid), antes)
        self.assertEqual(self._auditorias(), auditorias)


    def test_pausar_e_retomar_com_recalculo(self):
        aid, _erros = self._salvar()
        self.svc.pausar(self.ctx["admin"], IP, str(aid))
        reg = self.agd.obter(aid)
        self.assertEqual((reg["ativo"], reg["pausa_motivo"]), ("N", "MANUAL"))
        pausas = self._auditorias("AGD_PAUSAR")
        self.assertEqual(len(pausas), 1)
        self.assertEqual((pausas[0]["ator"], pausas[0]["ip_origem"]), ("admin", IP))
        self.assertIn(u"pausa_motivo: (vazio)%sMANUAL" % SETA, pausas[0]["detalhe"])

        self.agora = datetime.datetime(2026, 1, 20, 4, 0, 0, 999)
        self.svc.retomar(self.ctx["admin"], IP, str(aid))
        reg = self.agd.obter(aid)
        self.assertEqual((reg["ativo"], reg["pausa_motivo"]), ("S", None))
        self.assertEqual(reg["proxima_execucao"], datetime.datetime(2026, 1, 21, 3, 0))
        retomadas = self._auditorias("CAD_ALTERAR")
        self.assertEqual(len(retomadas), 1)
        self.assertIn(u"ativo: N%sS" % SETA, retomadas[0]["detalhe"])
        self.assertIn(u"21/01/2026 03:00", retomadas[0]["detalhe"])

    def test_pausar_ja_pausada_e_retomar_ativa(self):
        with self.assertRaises(OperacaoNegada):
            self.svc.pausar(self.ctx["admin"], IP, "5")
        with self.assertRaises(OperacaoNegada):
            self.svc.retomar(self.ctx["admin"], IP, "2")
        self.assertEqual(self._auditorias(), [])

    def test_pausa_otimista(self):
        aid, _erros = self._salvar()
        original = self.agd.pausar

        def pausar_com_corrida(id, motivo, antiga_data=None, auditoria=None):
            self.agd.alterar(id, {"proxima_execucao": datetime.datetime(2026, 1, 17, 3, 0)}, ator="teste")
            return original(id, motivo, antiga_data=antiga_data, auditoria=auditoria)

        with mock.patch.object(self.agd, "pausar", side_effect=pausar_com_corrida):
            with self.assertRaises(RepoConflito):
                self.svc.pausar(self.ctx["admin"], IP, str(aid))
        self.assertEqual(self.agd.obter(aid)["ativo"], "S")
        self.assertEqual(self._auditorias("AGD_PAUSAR"), [])

    def test_retomar_revalida_permissao(self):
        aid, _erros = self._salvar(script_id="4", respostas={})
        self.svc.pausar(self.ctx["admin"], IP, str(aid))
        with self.assertRaises(OperacaoNegada) as cm:
            self.svc.retomar(self.ctx["op.prod"], IP, str(aid))
        self.assertEqual(cm.exception.mensagem, svc_mod.MSG_SEM_PERMISSAO)
        self.assertEqual(self.agd.obter(aid)["ativo"], "N")

    def test_retomar_sem_proxima_execucao(self):
        aid, _erros = self._salvar(tipo_recorrencia="UNICA", data_inicio="2026-01-16T08:00")
        self.svc.pausar(self.ctx["admin"], IP, str(aid))
        self.agora = datetime.datetime(2026, 1, 17, 0, 0)
        with self.assertRaises(OperacaoNegada) as cm:
            self.svc.retomar(self.ctx["admin"], IP, str(aid))
        self.assertEqual(cm.exception.mensagem, svc_mod.MSG_RETOMAR_SEM_PROXIMA)
        self.assertEqual(self.agd.obter(aid)["ativo"], "N")

    def test_retomar_reavalia_usuario_responsavel_inativo(self):
        aid, _erros = self._salvar(login="op.hml", script_id="1",
                                   respostas={"data_ref": "2026-01-20", "modo_exec": "SIMULACAO"})
        self.svc.pausar(self.ctx["admin"], IP, str(aid))
        usuarios = repo_factory.obter("usuarios")
        usuarios.alterar(3, {"ativo": "N"}, ator="teste")
        with self.assertRaises(OperacaoNegada) as cm:
            self.svc.retomar(self.ctx["admin"], IP, str(aid))
        self.assertIn(svc_mod.MOTIVOS_PAUSA["USUARIO_INATIVO"], cm.exception.mensagem)
        self.assertIn(svc_mod.MSG_ORIENTACAO_RETOMAR, cm.exception.mensagem)

    def test_retomar_reavalia_script_inativo(self):
        aid, _erros = self._salvar(script_id="1", respostas={"data_ref": "2026-01-20", "modo_exec": "SIMULACAO"})
        self.svc.pausar(self.ctx["admin"], IP, str(aid))
        self.catalogo.scripts_alterar(1, {"ativo": "N"}, ator="teste")
        with self.assertRaises(OperacaoNegada) as cm:
            self.svc.retomar(self.ctx["admin"], IP, str(aid))
        self.assertIn(svc_mod.MOTIVOS_PAUSA["SCRIPT_INATIVO"], cm.exception.mensagem)

    def test_retomar_reavalia_ambiente_inativo(self):
        aid, _erros = self._salvar(ambiente="HOMOLOGACAO", script_id="1",
                                   respostas={"data_ref": "2026-01-20", "modo_exec": "SIMULACAO"})
        self.svc.pausar(self.ctx["admin"], IP, str(aid))
        self.catalogo.ambientes_alterar(2, {"ativo": "N"}, ator="teste")
        with self.assertRaises(OperacaoNegada) as cm:
            self.svc.retomar(self.ctx["admin"], IP, str(aid))
        self.assertIn(svc_mod.MOTIVOS_PAUSA["AMBIENTE_INATIVO"], cm.exception.mensagem)

    def test_retomar_reavalia_parametros_invalidos(self):
        aid, _erros = self._salvar(script_id="1", respostas={"data_ref": "2026-01-20", "modo_exec": "SIMULACAO"})
        self.svc.pausar(self.ctx["admin"], IP, str(aid))
        self.agd.alterar(aid, {"parametros_json": json.dumps({"data_ref": "data-invalida"})}, ator="teste")
        with self.assertRaises(OperacaoNegada) as cm:
            self.svc.retomar(self.ctx["admin"], IP, str(aid))
        self.assertIn(svc_mod.MOTIVOS_PAUSA["PARAM_INVALIDO"], cm.exception.mensagem)


class TestListaPrevia(_Base):

    def test_lista_no_escopo_com_colunas(self):
        res = self.svc.listar(self.ctx["op.hml"], {}, 1, 20)
        self.assertEqual(sorted(i["ambiente"] for i in res["itens"]), ["HOMOLOGACAO", "HOMOLOGACAO"])
        todos = self.svc.listar(self.ctx["admin"], {}, 1, 20)
        self.assertEqual(todos["total"], 5)
        pausada = [i for i in todos["itens"] if i["id"] == 5][0]
        self.assertEqual((pausada["situacao"], pausada["motivo"]), (u"Pausado", u"Pausado manualmente"))
        self.assertEqual(pausada["expressao_cron"], "0 */4 * * *")
        self.assertTrue(pausada["recorrencia"].startswith(u"A cada"))
        self.assertEqual(pausada["proxima_execucao"], "-")
        self.assertEqual(pausada["ultimo_ticket_id"], 35)
        semanal = [i for i in todos["itens"] if i["id"] == 3][0]
        self.assertEqual(semanal["recorrencia"], u"Às 04:00, seg, qua, sex")
        self.assertEqual(semanal["responsavel"], "admin")
        self.assertEqual(semanal["script"], "relatorio_mensal")
        self.assertEqual([i for i in todos["itens"] if i["id"] == 4][0]["responsavel"], "op.hml")

    def test_lista_filtros(self):
        filtros = svc_mod.normalizar_filtros({"ambiente": "producao", "ativo": "N", "nome": " Limpeza "})
        self.assertEqual(filtros, {"ambiente": "PRODUCAO", "ativo": "N", "nome": "Limpeza"})
        res = self.svc.listar(self.ctx["admin"], filtros, 1, 20)
        self.assertEqual([i["id"] for i in res["itens"]], [5])
        self.assertEqual(svc_mod.normalizar_filtros({"ambiente": "x;drop", "ativo": "Z"}), {})

    def test_previa_mensal_dia_31(self):
        res = self.svc.previa(self.ctx["admin"], {"tipo_recorrencia": "MENSAL", "hora_execucao": "03:00",
                                                  "dia_mes": "31"})
        self.assertEqual(res["erros"], {})
        self.assertEqual(res["datas"], [u"sáb, 31/01/2026 03:00", u"sáb, 28/02/2026 03:00",
                                        u"ter, 31/03/2026 03:00", u"qui, 30/04/2026 03:00",
                                        u"dom, 31/05/2026 03:00"])
        self.agora = datetime.datetime(2028, 1, 15, 10, 0)
        res = self.svc.previa(self.ctx["admin"], {"tipo_recorrencia": "MENSAL", "hora_execucao": "03:00",
                                                  "dia_mes": "31"})
        self.assertIn(u"29/02/2028 03:00", res["datas"][1])

    def test_previa_cron_descricao_e_datas(self):
        res = self.svc.previa(self.ctx["admin"], {"tipo_recorrencia": "CRON",
                                                  "expressao_cron": "*/15 8-18 * * 1-5"})
        self.assertEqual(res["erros"], {})
        self.assertEqual(res["descricao"], u"A cada 15 minutos, das 08:00 às 18:59, de segunda a sexta")
        self.assertEqual(res["datas"], [u"qui, 15/01/2026 10:15", u"qui, 15/01/2026 10:30",
                                        u"qui, 15/01/2026 10:45", u"qui, 15/01/2026 11:00",
                                        u"qui, 15/01/2026 11:15"])
        # Sexta 18:50 -> pula o fim de semana.
        self.agora = datetime.datetime(2026, 1, 16, 18, 50)
        res = self.svc.previa(self.ctx["admin"], {"tipo_recorrencia": "CRON",
                                                  "expressao_cron": "*/15 8-18 * * 1-5"})
        self.assertEqual(res["datas"][:2], [u"seg, 19/01/2026 08:00", u"seg, 19/01/2026 08:15"])

    def test_previa_com_erros(self):
        res = self.svc.previa(self.ctx["admin"], {"tipo_recorrencia": "CRON", "expressao_cron": "0 0 L * *"})
        self.assertEqual(res["datas"], [])
        self.assertIn("expressao_cron", res["erros"])
        res = self.svc.previa(self.ctx["admin"], {"tipo_recorrencia": "UNICA", "data_inicio": "2026-01-01T00:00"})
        self.assertEqual(res["erros"], {CAMPO_GERAL: svc_mod.MSG_SEM_PROXIMA})
        res = self.svc.previa(self.ctx["admin"], {"tipo_recorrencia": "UNICA", "data_inicio": "2026-03-01T09:00"})
        self.assertEqual(res["datas"], [u"dom, 01/03/2026 09:00"])
        self.assertEqual(res["descricao"], u"Uma vez, em 01/03/2026 09:00")

    def test_lista_aviso_sobreposicao(self):
        tid = self.tickets.criar({"script_id": 1, "ambiente": "PRODUCAO", "solicitante": "admin",
                                  "parametros_enviados": "{}", "prioridade": 2, "status": "PENDING"},
                                 [], ator="admin")
        self.agd.alterar(1, {"ultimo_ticket_id": tid}, ator="teste")
        res = self.svc.listar(self.ctx["admin"], {}, 1, 20)
        item1 = [i for i in res["itens"] if i["id"] == 1][0]
        self.assertIsNotNone(item1.get("aviso"))
        self.assertIn(u"pode ser pulada", item1["aviso"])
        self.assertIn(str(tid), item1["aviso"])

    def test_agenda_aviso_e_problemas(self):
        aid_ativo, erros = self._salvar()
        self.assertEqual(erros, {})
        self.catalogo.scripts_alterar(1, {"ativo": "N"}, ator="teste")
        dados = self.svc.agenda(self.ctx["admin"])
        itens_r1 = [i for dia in dados["dias"] for i in dia["itens"] if i["regra_id"] == aid_ativo]
        self.assertTrue(itens_r1)
        self.assertIn(u"Será pausada", itens_r1[0].get("aviso", ""))
        aid = self.agd.inserir({"nome": "CRON Problematico", "usuario_id": 1, "script_id": 1,
                                "ambiente": "HOMOLOGACAO", "tipo_recorrencia": "CRON",
                                "expressao_cron": "0 0 31 2 *", "prioridade": 2, "ativo": "S",
                                "parametros_json": "{}"}, ator="teste")["id"]
        dados2 = self.svc.agenda(self.ctx["admin"])
        problemas = dados2.get("problemas", [])
        self.assertIn(aid, [p["regra_id"] for p in problemas])

    def test_formulario_regra_pausada_pausa_aviso(self):
        aid, _erros = self._salvar(script_id="1", respostas={"data_ref": "2026-01-20", "modo_exec": "SIMULACAO"})
        self.svc.pausar(self.ctx["admin"], IP, str(aid))
        f = self.svc.formulario(self.ctx["admin"], str(aid))
        self.assertIsNotNone(f["regra"].get("pausa_aviso"))
        self.assertIn(u"Pausada", f["regra"]["pausa_aviso"])


class TestAuditoriaInclusao(_Base):

    def test_inclusao_auditada_sem_valor_sensivel(self):
        aid, _erros = self._salvar(respostas={"data_ref": "2026-01-20", "modo_exec": "REAL", "documento_cliente": SEGREDO})
        inclusoes = self._auditorias("CAD_INSERIR")
        self.assertEqual(len(inclusoes), 1)
        aud = inclusoes[0]
        self.assertEqual((aud["ator"], aud["ip_origem"], aud["entidade_id"]), ("admin", IP, aid))
        self.assertNotIn(SEGREDO, aud["detalhe"])
        self.assertIn(u"documento_cliente=%s" % svc_mod.MASCARA, aud["detalhe"])
        self.assertIn(u"usuario_id: 1", aud["detalhe"])
        self.assertLessEqual(len(aud["detalhe"]), admin_crud.LIMITE_DETALHE)


if __name__ == "__main__":
    unittest.main()
