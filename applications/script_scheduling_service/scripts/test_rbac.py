# -*- coding: utf-8 -*-
"""Testes de rbac.py (F2.2): pode_executar, pode_cancelar, pode_ver_ticket, prioridade e tem_func."""
import _testenv  # noqa: F401

import logging
import os
import re
import unittest
from unittest import mock

import admin_crud
import admin_perfis_service as perfis_mod
import auth_service
import rbac
import repo_factory
import security
from admin_crud import CAMPO_GERAL, AcessoNegado, OperacaoNegada
from admin_perfis_service import ServicoAdminPerfis
from rbac import Motivo
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao


def _ctx(is_admin=False, usuario_ativo="S", perfil_ativo="S", funcs=("EXEC_SCRIPT",),
         ambs=("PRODUCAO",), scrs=(1,), login="op.prod"):
    return rbac.contexto_usuario({
        "usuario_id": 2, "login": login, "nome": "Operador", "usuario_ativo": usuario_ativo,
        "perfil_id": 2, "perfil_nome": "OPERADOR", "perfil_ativo": perfil_ativo,
        "is_admin": "S" if is_admin else "N", "perm_versao": 1,
        "funcionalidades": funcs, "ambientes": ambs, "scripts": scrs,
    })


SCRIPT = {"id": 1, "nome": "carga_diaria", "ativo": "S"}
AMBIENTE = {"id": 1, "nome": "PRODUCAO", "ativo": "S"}
HOMOLOGACOES = [1, 2]


class TestContexto(unittest.TestCase):

    def test_formato(self):
        ctx = _ctx()
        for chave in ("usuario_id", "login", "perfil_id", "is_admin", "funcionalidades",
                      "ambientes", "scripts", "perm_versao"):
            self.assertIn(chave, ctx)
        self.assertIsInstance(ctx["funcionalidades"], frozenset)
        self.assertIs(ctx["is_admin"], False)

    def test_flag_n_nao_e_verdadeira(self):
        self.assertIs(_ctx(is_admin=False)["is_admin"], False)
        self.assertIs(_ctx(usuario_ativo="N")["usuario_ativo"], False)

    def test_modulo_puro_sem_gluon(self):
        with open(rbac.__file__, encoding="utf-8") as f:
            self.assertIsNone(re.search(r"^\s*(from|import)\s+gluon", f.read(), re.MULTILINE))


class TestPodeExecutar(unittest.TestCase):

    def assertNegado(self, resultado, motivo):
        self.assertEqual(resultado, (False, motivo))

    def test_caso_ok(self):
        self.assertEqual(rbac.pode_executar(_ctx(), SCRIPT, AMBIENTE, HOMOLOGACOES), (True, Motivo.OK))

    def test_admin_dispensa_dimensoes(self):
        ctx = _ctx(is_admin=True, funcs=(), ambs=(), scrs=())
        self.assertEqual(rbac.pode_executar(ctx, SCRIPT, AMBIENTE, HOMOLOGACOES), (True, Motivo.OK))

    def test_admin_com_perfil_inativo(self):
        ctx = _ctx(is_admin=True, perfil_ativo="N")
        self.assertNegado(rbac.pode_executar(ctx, SCRIPT, AMBIENTE, HOMOLOGACOES), Motivo.PERFIL_INATIVO)

    def test_usuario_inativo(self):
        self.assertNegado(rbac.pode_executar(_ctx(usuario_ativo="N"), SCRIPT, AMBIENTE, HOMOLOGACOES),
                          Motivo.USUARIO_INATIVO)

    def test_script_inativo(self):
        script = dict(SCRIPT, ativo="N")
        self.assertNegado(rbac.pode_executar(_ctx(), script, AMBIENTE, HOMOLOGACOES), Motivo.SCRIPT_INATIVO)
        self.assertNegado(rbac.pode_executar(_ctx(is_admin=True), script, AMBIENTE, HOMOLOGACOES),
                          Motivo.SCRIPT_INATIVO)

    def test_ambiente_inativo(self):
        ambiente = dict(AMBIENTE, ativo="N")
        self.assertNegado(rbac.pode_executar(_ctx(), SCRIPT, ambiente, HOMOLOGACOES), Motivo.AMBIENTE_INATIVO)
        self.assertNegado(rbac.pode_executar(_ctx(is_admin=True), SCRIPT, ambiente, HOMOLOGACOES),
                          Motivo.AMBIENTE_INATIVO)

    def test_sem_homologacao(self):
        self.assertNegado(rbac.pode_executar(_ctx(), SCRIPT, AMBIENTE, [2]), Motivo.SEM_HOMOLOGACAO)
        self.assertNegado(rbac.pode_executar(_ctx(is_admin=True), SCRIPT, AMBIENTE, []), Motivo.SEM_HOMOLOGACAO)
        self.assertNegado(rbac.pode_executar(_ctx(), SCRIPT, AMBIENTE, None), Motivo.SEM_HOMOLOGACAO)

    def test_sem_exec_script(self):
        self.assertNegado(rbac.pode_executar(_ctx(funcs=("VER_LOGS",)), SCRIPT, AMBIENTE, HOMOLOGACOES),
                          Motivo.SEM_FUNC)

    def test_sem_ambiente(self):
        self.assertNegado(rbac.pode_executar(_ctx(ambs=("HOMOLOGACAO",)), SCRIPT, AMBIENTE, HOMOLOGACOES),
                          Motivo.SEM_AMBIENTE)

    def test_sem_script(self):
        self.assertNegado(rbac.pode_executar(_ctx(scrs=(2,)), SCRIPT, AMBIENTE, HOMOLOGACOES),
                          Motivo.SEM_SCRIPT)

    def test_dados_invalidos(self):
        for script, ambiente in (
            (None, AMBIENTE),
            (SCRIPT, None),
            (dict(SCRIPT, id="1"), AMBIENTE),
            (dict(SCRIPT, id=True), AMBIENTE),
            (SCRIPT, dict(AMBIENTE, id=0)),
            (SCRIPT, dict(AMBIENTE, nome="")),
        ):
            self.assertNegado(rbac.pode_executar(_ctx(), script, ambiente, HOMOLOGACOES), Motivo.DADO_INVALIDO)
        self.assertNegado(rbac.pode_executar(None, SCRIPT, AMBIENTE, HOMOLOGACOES), Motivo.DADO_INVALIDO)

    def test_flag_ativo_somente_s(self):
        for flag in ("", "n", None, "s", "SIM"):
            self.assertNegado(rbac.pode_executar(_ctx(), dict(SCRIPT, ativo=flag), AMBIENTE, HOMOLOGACOES),
                              Motivo.SCRIPT_INATIVO)


class TestTemFunc(unittest.TestCase):

    def test_admin_ativo(self):
        self.assertTrue(rbac.tem_func(_ctx(is_admin=True, funcs=()), "CAD_USUARIOS"))

    def test_admin_perfil_inativo(self):
        self.assertFalse(rbac.tem_func(_ctx(is_admin=True, perfil_ativo="N"), "CAD_USUARIOS"))

    def test_nao_admin(self):
        self.assertTrue(rbac.tem_func(_ctx(funcs=("VER_LOGS",)), "VER_LOGS"))
        self.assertFalse(rbac.tem_func(_ctx(funcs=("VER_LOGS",)), "CAD_USUARIOS"))
        self.assertFalse(rbac.tem_func(None, "VER_LOGS"))


class TestTickets(unittest.TestCase):

    TICKET_PROPRIO = {"id": 10, "ambiente": "PRODUCAO", "solicitante": "op.prod"}
    TICKET_TERCEIRO = {"id": 11, "ambiente": "PRODUCAO", "solicitante": "outro"}
    TICKET_OUTRO_AMB = {"id": 12, "ambiente": "HOMOLOGACAO", "solicitante": "outro"}

    def test_cancelar_proprio_sem_canc_ticket(self):
        ctx = _ctx(funcs=("EXEC_SCRIPT",))
        self.assertTrue(rbac.pode_cancelar(ctx, self.TICKET_PROPRIO))
        self.assertFalse(rbac.pode_cancelar(ctx, self.TICKET_TERCEIRO))

    def test_cancelar_proprio_sem_exec_script(self):
        self.assertFalse(rbac.pode_cancelar(_ctx(funcs=("VER_LOGS",)), self.TICKET_PROPRIO))

    def test_cancelar_terceiro_com_canc_ticket(self):
        ctx = _ctx(funcs=("CANC_TICKET",))
        self.assertTrue(rbac.pode_cancelar(ctx, self.TICKET_TERCEIRO))
        self.assertFalse(rbac.pode_cancelar(ctx, self.TICKET_OUTRO_AMB))

    def test_cancelar_admin(self):
        self.assertTrue(rbac.pode_cancelar(_ctx(is_admin=True, funcs=(), ambs=()), self.TICKET_OUTRO_AMB))

    def test_cancelar_perfil_inativo(self):
        ctx = _ctx(funcs=("CANC_TICKET", "EXEC_SCRIPT"), perfil_ativo="N")
        self.assertFalse(rbac.pode_cancelar(ctx, self.TICKET_PROPRIO))

    def test_cancelar_ticket_invalido(self):
        self.assertFalse(rbac.pode_cancelar(_ctx(), None))
        self.assertFalse(rbac.pode_cancelar(_ctx(), {"ambiente": "PRODUCAO", "solicitante": None}))

    def test_ver_ticket(self):
        ctx = _ctx(funcs=("VER_LOGS",))
        self.assertTrue(rbac.pode_ver_ticket(ctx, self.TICKET_TERCEIRO))
        self.assertFalse(rbac.pode_ver_ticket(ctx, self.TICKET_OUTRO_AMB))
        self.assertFalse(rbac.pode_ver_ticket(_ctx(funcs=("EXEC_SCRIPT",)), self.TICKET_PROPRIO))
        self.assertTrue(rbac.pode_ver_ticket(_ctx(is_admin=True, ambs=()), self.TICKET_OUTRO_AMB))

    def test_ver_ambiente(self):
        self.assertTrue(rbac.pode_ver_ambiente(_ctx(), {"nome": "PRODUCAO"}))
        self.assertTrue(rbac.pode_ver_ambiente(_ctx(), "PRODUCAO"))
        self.assertFalse(rbac.pode_ver_ambiente(_ctx(), "HOMOLOGACAO"))
        self.assertFalse(rbac.pode_ver_ambiente(_ctx(), None))


class TestPrioridade(unittest.TestCase):

    def test_admin(self):
        for p in (1, 2, 3, 4):
            self.assertTrue(rbac.prioridade_permitida(_ctx(is_admin=True), p))

    def test_nao_admin(self):
        self.assertFalse(rbac.prioridade_permitida(_ctx(), 1))
        for p in (2, 3, 4):
            self.assertTrue(rbac.prioridade_permitida(_ctx(), p))

    def test_invalidas(self):
        for p in (0, 5, -1, True, "2", None, 2.0):
            self.assertFalse(rbac.prioridade_permitida(_ctx(is_admin=True), p))

    def test_perfil_inativo(self):
        self.assertFalse(rbac.prioridade_permitida(_ctx(perfil_ativo="N"), 2))


# ---------------------------------------------------------------- F4.2: perfis e matriz (FAKE)

IP = "10.1.1.1"
SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1},
    "op.prod": {"usuario_id": 2, "login": "op.prod", "perfil_id": 2, "perm_versao": 1},
    "consulta": {"usuario_id": 4, "login": "consulta", "perfil_id": 4, "perm_versao": 1},
}
# Seed FAKE: perfil 1 ADMINISTRADOR (unico admin), 3 OPERADOR_HML (ambiente DESENV inativo associado),
# 4 CONSULTA (VER_LOGS; PRODUCAO e HOMOLOGACAO). Funcionalidades 1 EXEC_SCRIPT, 2 VER_LOGS, 3 CANC_TICKET.
PERFIL_ADMIN, PERFIL_HML, PERFIL_CONSULTA = 1, 3, 4
F_EXEC, F_VER_LOGS = 1, 2
AMB_PRODUCAO, AMB_HOMOLOGACAO, AMB_DESENV = 1, 2, 3


class _BasePerfis(unittest.TestCase):

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

        self.rbac_repo = repo_factory.obter("rbac")
        self.catalogo = repo_factory.obter("catalogo")
        self.usuarios = repo_factory.obter("usuarios")
        self.auditoria = repo_factory.obter("auditoria")
        self.log = logging.getLogger("sss_teste_perfis")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        self.auth = auth_service.ServicoAuth(self.usuarios, self.rbac_repo, self.catalogo, self.auditoria,
                                             5, 900, self.log)
        self.ctx = dict((login, self.auth.revalidar(sessao)) for login, sessao in SESSOES.items())
        self.svc = ServicoAdminPerfis(self.rbac_repo, self.catalogo, self.usuarios, self.log)
        self.aud_base = max([a["id"] for a in self.auditoria.listar(pagina=1, tamanho=1000)["itens"]] or [0])

    def _auditorias(self, acao):
        return [a for a in self.auditoria.listar(filtros={"acao": acao}, pagina=1, tamanho=100)["itens"]
                if a["entidade"] == "tbsss_perfis" and a["id"] > self.aud_base]

    def _versao(self, perfil_id):
        return self.rbac_repo.perfis_obter(perfil_id)["perm_versao"]

    def _salvar_matriz(self, perfil_id, funcs, ambs, scrs, versao=None):
        versao = self._versao(perfil_id) if versao is None else versao
        return self.svc.salvar_matriz(self.ctx["admin"], IP, str(perfil_id), [str(x) for x in funcs],
                                      [str(x) for x in ambs], [str(x) for x in scrs], str(versao))

    def _matriz(self, perfil_id):
        return self.rbac_repo.matriz_obter(perfil_id)


class TestMatriz(_BasePerfis):

    def test_diff_formato(self):
        rotulos = {"funcs": {1: "EXEC_SCRIPT", 2: "VER_LOGS"}, "ambs": {1: "PRODUCAO"}, "scrs": {7: "carga"}}
        diff = perfis_mod.diff_matriz({"funcs": {2}, "ambs": set(), "scrs": {7}},
                                      {"funcs": {1}, "ambs": {1}, "scrs": set()}, rotulos)
        self.assertEqual(diff, "+EXEC_SCRIPT, -VER_LOGS, +amb:PRODUCAO, -scr:carga")
        self.assertIsNone(perfis_mod.diff_matriz({"funcs": {1}}, {"funcs": {1}}, rotulos))

    def test_salvar_matriz_incrementa_versao_e_audita_diff(self):
        antes = self._matriz(PERFIL_CONSULTA)
        versao = self._versao(PERFIL_CONSULTA)
        scrs = [x for x in antes["scrs"] if x != 3]
        diff, erros = self._salvar_matriz(PERFIL_CONSULTA, [F_EXEC], antes["ambs"], scrs)
        self.assertEqual(erros, {})
        self.assertEqual(diff, "+EXEC_SCRIPT, -VER_LOGS, -scr:cleanup_tmp")
        self.assertEqual(self._versao(PERFIL_CONSULTA), versao + 1)
        self.assertEqual(sorted(self._matriz(PERFIL_CONSULTA)["funcs"]), [F_EXEC])
        aud = self._auditorias("PERM_ALTERAR")
        self.assertEqual(len(aud), 1)
        self.assertEqual((aud[0]["detalhe"], aud[0]["entidade_id"], aud[0]["ator"]), (diff, PERFIL_CONSULTA, "admin"))

    def test_sem_mudanca_nao_incrementa_nem_audita(self):
        m = self._matriz(PERFIL_CONSULTA)
        versao = self._versao(PERFIL_CONSULTA)
        diff, erros = self._salvar_matriz(PERFIL_CONSULTA, m["funcs"], m["ambs"], m["scrs"])
        self.assertEqual((diff, erros), (None, {}))
        self.assertEqual(self._versao(PERFIL_CONSULTA), versao)
        self.assertEqual(self._auditorias("PERM_ALTERAR"), [])

    def test_efeito_imediato_na_revalidacao(self):
        self.assertIn("VER_LOGS", self.ctx["consulta"]["funcionalidades"])
        m = self._matriz(PERFIL_CONSULTA)
        self._salvar_matriz(PERFIL_CONSULTA, [], m["ambs"], m["scrs"])
        sessao = dict(SESSOES["consulta"])
        ctx = self.auth.revalidar(sessao)
        self.assertNotIn("VER_LOGS", ctx["funcionalidades"])
        self.assertEqual(ctx["perm_versao"], self._versao(PERFIL_CONSULTA))

    def test_id_inexistente_ou_invalido_rejeita_tudo(self):
        m = self._matriz(PERFIL_CONSULTA)
        versao = self._versao(PERFIL_CONSULTA)
        for funcs, ambs, scrs in (([F_EXEC, 999], m["ambs"], m["scrs"]), (m["funcs"], [AMB_PRODUCAO, 77], m["scrs"]),
                                  (m["funcs"], m["ambs"], [1, 404])):
            diff, erros = self._salvar_matriz(PERFIL_CONSULTA, funcs, ambs, scrs)
            self.assertEqual((diff, erros), (None, {CAMPO_GERAL: perfis_mod.MSG_MATRIZ_ID_INVALIDO}))
        diff, erros = self.svc.salvar_matriz(self.ctx["admin"], IP, str(PERFIL_CONSULTA), ["1", "x"], [], [],
                                             str(versao))
        self.assertEqual(erros, {CAMPO_GERAL: perfis_mod.MSG_MATRIZ_ID_INVALIDO})
        self.assertEqual(self._matriz(PERFIL_CONSULTA), m)
        self.assertEqual(self._versao(PERFIL_CONSULTA), versao)

    def test_inativo_associado_e_preservado_e_novo_inativo_rejeitado(self):
        m = self._matriz(PERFIL_HML)
        self.assertIn(AMB_DESENV, m["ambs"])
        # A tela nao envia o DESENV (desabilitado): o servidor preserva a associacao.
        sem_desenv = [a for a in m["ambs"] if a != AMB_DESENV]
        diff, erros = self._salvar_matriz(PERFIL_HML, m["funcs"], sem_desenv + [AMB_PRODUCAO], m["scrs"])
        self.assertEqual((diff, erros), ("+amb:PRODUCAO", {}))
        self.assertIn(AMB_DESENV, self._matriz(PERFIL_HML)["ambs"])
        m = self._matriz(PERFIL_CONSULTA)
        diff, erros = self._salvar_matriz(PERFIL_CONSULTA, m["funcs"], m["ambs"] + [AMB_DESENV], m["scrs"])
        self.assertEqual(erros, {CAMPO_GERAL: perfis_mod.MSG_MATRIZ_INATIVO})

    def test_versao_desatualizada_gera_conflito(self):
        m = self._matriz(PERFIL_CONSULTA)
        antiga = self._versao(PERFIL_CONSULTA)
        self._salvar_matriz(PERFIL_CONSULTA, [F_EXEC, F_VER_LOGS], m["ambs"], m["scrs"])
        diff, erros = self._salvar_matriz(PERFIL_CONSULTA, [], m["ambs"], m["scrs"], versao=antiga)
        self.assertEqual(erros, {CAMPO_GERAL: admin_crud.MSG_CONFLITO})
        self.assertEqual(sorted(self._matriz(PERFIL_CONSULTA)["funcs"]), [F_EXEC, F_VER_LOGS])

    def test_tela_da_matriz(self):
        tela = self.svc.matriz(self.ctx["admin"], str(PERFIL_HML))
        ambs = [i for g in tela["ambs"] for i in g["itens"]]
        desenv = [i for i in ambs if i["rotulo"] == "DESENV"][0]
        self.assertTrue(desenv["marcado"] and desenv["inativo"])
        self.assertEqual([g["grupo"] for g in tela["funcs"]], ["ADMIN", "OPERACAO"])
        self.assertIsNone(tela["aviso_admin"])
        self.assertEqual(self.svc.matriz(self.ctx["admin"], str(PERFIL_ADMIN))["aviso_admin"], perfis_mod.AVISO_ADMIN)
        tela_consulta = self.svc.matriz(self.ctx["admin"], str(PERFIL_CONSULTA))
        self.assertNotIn("DESENV", [i["rotulo"] for g in tela_consulta["ambs"] for i in g["itens"]])


class TestUltimoAdmin(_BasePerfis):

    def _form(self, perfil_id):
        return self.svc.formulario(self.ctx["admin"], str(perfil_id))

    def test_desativar_unico_perfil_admin_e_negado(self):
        form = self._form(PERFIL_ADMIN)
        with self.assertRaises(OperacaoNegada) as cm:
            self.svc.alternar_ativo(self.ctx["admin"], IP, str(PERFIL_ADMIN), form["versao"])
        self.assertEqual(cm.exception.mensagem, perfis_mod.MSG_ULTIMO_ADMIN)
        perfil = self.rbac_repo.perfis_obter(PERFIL_ADMIN)
        self.assertEqual((perfil["ativo"], perfil["perm_versao"]), ("S", 1))
        self.assertEqual(self._auditorias("CAD_DESATIVAR"), [])

    def test_remover_is_admin_do_unico_perfil_admin_e_negado(self):
        form = self._form(PERFIL_ADMIN)
        _id, erros = self.svc.salvar(self.ctx["admin"], IP, str(PERFIL_ADMIN),
                                     {"nome": form["nome"], "descricao": form["descricao"], "is_admin": None,
                                      "versao": form["versao"]})
        self.assertEqual(erros, {CAMPO_GERAL: perfis_mod.MSG_ULTIMO_ADMIN})
        self.assertEqual(self.rbac_repo.perfis_obter(PERFIL_ADMIN)["is_admin"], "S")

    def test_com_outro_admin_ativo_a_operacao_passa(self):
        novo_id, erros = self.svc.salvar(self.ctx["admin"], IP, None, {"nome": "ADMIN_RESERVA", "is_admin": "S"})
        self.assertEqual(erros, {})
        u = self.usuarios.obter_por_login("op.hml")
        self.usuarios.alterar(u["id"], {"perfil_id": novo_id})
        form = self._form(PERFIL_ADMIN)
        alterado = self.svc.alternar_ativo(self.ctx["admin"], IP, str(PERFIL_ADMIN), form["versao"])
        self.assertEqual(alterado["ativo"], "N")
        aud = self._auditorias("CAD_DESATIVAR")
        self.assertEqual(len(aud), 1)
        self.assertIn(u"usuários ativos afetados: 1", aud[0]["detalhe"])

    def test_perfil_admin_sem_usuarios_nao_conta_como_admin_ativo(self):
        # Um segundo perfil admin sem usuarios nao livra o ultimo admin real.
        self.svc.salvar(self.ctx["admin"], IP, None, {"nome": "ADMIN_VAZIO", "is_admin": "S"})
        form = self._form(PERFIL_ADMIN)
        with self.assertRaises(OperacaoNegada):
            self.svc.alternar_ativo(self.ctx["admin"], IP, str(PERFIL_ADMIN), form["versao"])

    def test_protecao_e_atomica_no_repositorio(self):
        with self.assertRaises(RepoViolacao) as cm:
            self.rbac_repo.perfis_alterar(PERFIL_ADMIN, {"ativo": "N"})
        self.assertEqual(cm.exception.constraint, "sss_ultimo_admin")
        self.assertEqual(self.rbac_repo.admins_ativos_bloquear(), [1])


class TestCadastroPerfil(_BasePerfis):

    def test_inclusao_validacoes_e_auditoria(self):
        for nome, msg in (("", perfis_mod.MSG_NOME_OBRIGATORIO), ("auditor", perfis_mod.MSG_NOME_INVALIDO),
                          ("CONSULTA", perfis_mod.MSG_NOME_DUPLICADO)):
            _id, erros = self.svc.salvar(self.ctx["admin"], IP, None, {"nome": nome})
            self.assertEqual(erros, {"nome": msg}, nome)
        pid, erros = self.svc.salvar(self.ctx["admin"], IP, None, {"nome": "AUDITOR", "descricao": "Leitura"})
        self.assertEqual(erros, {})
        perfil = self.rbac_repo.perfis_obter(pid)
        self.assertEqual((perfil["is_admin"], perfil["ativo"], perfil["perm_versao"]), ("N", "S", 1))
        self.assertIn("nome: AUDITOR", self._auditorias("CAD_INSERIR")[0]["detalhe"])

    def test_alteracao_concorrente_e_auditoria(self):
        aba1 = self.svc.formulario(self.ctx["admin"], str(PERFIL_CONSULTA))
        aba2 = self.svc.formulario(self.ctx["admin"], str(PERFIL_CONSULTA))
        self.assertEqual(aba1["usuarios_ativos"], 1)
        _id, erros = self.svc.salvar(self.ctx["admin"], IP, str(PERFIL_CONSULTA),
                                     {"nome": "CONSULTA_GERAL", "descricao": aba2["descricao"], "versao": aba2["versao"]})
        self.assertEqual(erros, {})
        _id, erros = self.svc.salvar(self.ctx["admin"], IP, str(PERFIL_CONSULTA),
                                     {"nome": "CONSULTA", "descricao": "x", "versao": aba1["versao"]})
        self.assertEqual(erros, {CAMPO_GERAL: admin_crud.MSG_CONFLITO})
        aud = self._auditorias("CAD_ALTERAR")
        self.assertEqual(len(aud), 1)
        self.assertIn(u"nome: CONSULTA \u2192 CONSULTA_GERAL", aud[0]["detalhe"])
        self.assertEqual(self._versao(PERFIL_CONSULTA), 2)

    def test_reativar(self):
        form = self.svc.formulario(self.ctx["admin"], str(PERFIL_CONSULTA))
        self.svc.alternar_ativo(self.ctx["admin"], IP, str(PERFIL_CONSULTA), form["versao"])
        form = self.svc.formulario(self.ctx["admin"], str(PERFIL_CONSULTA))
        with self.assertRaises(RepoConflito):
            self.svc.alternar_ativo(self.ctx["admin"], IP, str(PERFIL_CONSULTA), "x")
        self.assertEqual(self.svc.alternar_ativo(self.ctx["admin"], IP, str(PERFIL_CONSULTA), form["versao"])["ativo"], "S")

    def test_acesso_negado_e_nao_encontrado(self):
        for chamada in (lambda c: self.svc.listar(c, {}, 1, 20), lambda c: self.svc.matriz(c, "1"),
                        lambda c: self.svc.salvar_matriz(c, IP, "4", [], [], [], "1"),
                        lambda c: self.svc.alternar_ativo(c, IP, "4", "x")):
            with self.assertRaises(AcessoNegado):
                chamada(self.ctx["op.prod"])
        for pid in ("999", "abc", "0"):
            with self.assertRaises(RepoNaoEncontrado):
                self.svc.matriz(self.ctx["admin"], pid)

    def test_filtros(self):
        self.assertEqual(perfis_mod.normalizar_filtros({"nome": "OPER", "ativo": "S", "is_admin": "N"}),
                         {"nome": "OPER", "ativo": "S", "is_admin": "N"})
        self.assertEqual(perfis_mod.normalizar_filtros({"nome": "<x>", "ativo": "?"}), {})


if __name__ == "__main__":
    unittest.main()
