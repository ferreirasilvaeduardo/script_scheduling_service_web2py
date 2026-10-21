# -*- coding: utf-8 -*-
"""Testes de rbac.py (F2.2): pode_executar, pode_cancelar, pode_ver_ticket, prioridade e tem_func."""
import _testenv  # noqa: F401

import logging
import os
import re
import unittest
from unittest import mock

import admin_crud
import admin_profiles_service as perfis_mod
import auth_service
import rbac
import repo_factory
import security
from admin_crud import CAMPO_GERAL, AcessoNegado, OperacaoNegada
from admin_profiles_service import ServicoAdminPerfis
from rbac import Motivo
from repo_errors import RepoConflict, RepoNotFound, RepoViolation


def _ctx(is_admin=False, usuario_ativo="Y", perfil_ativo="Y", funcs=("EXEC_SCRIPT",),
         ambs=("PRODUCAO",), scrs=(1,), login="op.prod"):
    return rbac.contexto_usuario({
        "user_id": 2, "login": login, "name": "Operador", "usuario_ativo": usuario_ativo,
        "profile_id": 2, "perfil_nome": "OPERADOR", "perfil_ativo": perfil_ativo,
        "is_admin": "Y" if is_admin else "N", "perm_version": 1,
        "features": funcs, "environments": ambs, "scripts": scrs,
    })


SCRIPT = {"id": 1, "name": "carga_diaria", "active": "Y"}
AMBIENTE = {"id": 1, "name": "PRODUCAO", "active": "Y"}
HOMOLOGACOES = [1, 2]


class TestContexto(unittest.TestCase):

    def test_formato(self):
        ctx = _ctx()
        for chave in ("user_id", "login", "profile_id", "is_admin", "features",
                      "environments", "scripts", "perm_version"):
            self.assertIn(chave, ctx)
        self.assertIsInstance(ctx["features"], frozenset)
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
                          Motivo.USER_INACTIVE)

    def test_script_inativo(self):
        script = dict(SCRIPT, active="N")
        self.assertNegado(rbac.pode_executar(_ctx(), script, AMBIENTE, HOMOLOGACOES), Motivo.SCRIPT_INACTIVE)
        self.assertNegado(rbac.pode_executar(_ctx(is_admin=True), script, AMBIENTE, HOMOLOGACOES),
                          Motivo.SCRIPT_INACTIVE)

    def test_ambiente_inativo(self):
        ambiente = dict(AMBIENTE, active="N")
        self.assertNegado(rbac.pode_executar(_ctx(), SCRIPT, ambiente, HOMOLOGACOES), Motivo.ENVIRONMENT_INACTIVE)
        self.assertNegado(rbac.pode_executar(_ctx(is_admin=True), SCRIPT, ambiente, HOMOLOGACOES),
                          Motivo.ENVIRONMENT_INACTIVE)

    def test_sem_homologacao(self):
        self.assertNegado(rbac.pode_executar(_ctx(), SCRIPT, AMBIENTE, [2]), Motivo.SEM_HOMOLOGACAO)
        self.assertNegado(rbac.pode_executar(_ctx(is_admin=True), SCRIPT, AMBIENTE, []), Motivo.SEM_HOMOLOGACAO)
        self.assertNegado(rbac.pode_executar(_ctx(), SCRIPT, AMBIENTE, None), Motivo.SEM_HOMOLOGACAO)

    def test_sem_exec_script(self):
        self.assertNegado(rbac.pode_executar(_ctx(funcs=("VIEW_LOGS",)), SCRIPT, AMBIENTE, HOMOLOGACOES),
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
            (SCRIPT, dict(AMBIENTE, name="")),
        ):
            self.assertNegado(rbac.pode_executar(_ctx(), script, ambiente, HOMOLOGACOES), Motivo.DADO_INVALIDO)
        self.assertNegado(rbac.pode_executar(None, SCRIPT, AMBIENTE, HOMOLOGACOES), Motivo.DADO_INVALIDO)

    def test_flag_ativo_somente_s(self):
        for flag in ("", "n", None, "s", "SIM"):
            self.assertNegado(rbac.pode_executar(_ctx(), dict(SCRIPT, active=flag), AMBIENTE, HOMOLOGACOES),
                              Motivo.SCRIPT_INACTIVE)


class TestTemFunc(unittest.TestCase):

    def test_admin_ativo(self):
        self.assertTrue(rbac.tem_func(_ctx(is_admin=True, funcs=()), "MANAGE_USERS"))

    def test_admin_perfil_inativo(self):
        self.assertFalse(rbac.tem_func(_ctx(is_admin=True, perfil_ativo="N"), "MANAGE_USERS"))

    def test_nao_admin(self):
        self.assertTrue(rbac.tem_func(_ctx(funcs=("VIEW_LOGS",)), "VIEW_LOGS"))
        self.assertFalse(rbac.tem_func(_ctx(funcs=("VIEW_LOGS",)), "MANAGE_USERS"))
        self.assertFalse(rbac.tem_func(None, "VIEW_LOGS"))


class TestTickets(unittest.TestCase):

    TICKET_PROPRIO = {"id": 10, "environment": "PRODUCAO", "requested_by": "op.prod"}
    TICKET_TERCEIRO = {"id": 11, "environment": "PRODUCAO", "requested_by": "outro"}
    TICKET_OUTRO_AMB = {"id": 12, "environment": "HOMOLOGACAO", "requested_by": "outro"}

    def test_cancelar_proprio_sem_canc_ticket(self):
        ctx = _ctx(funcs=("EXEC_SCRIPT",))
        self.assertTrue(rbac.pode_cancelar(ctx, self.TICKET_PROPRIO))
        self.assertFalse(rbac.pode_cancelar(ctx, self.TICKET_TERCEIRO))

    def test_cancelar_proprio_sem_exec_script(self):
        self.assertFalse(rbac.pode_cancelar(_ctx(funcs=("VIEW_LOGS",)), self.TICKET_PROPRIO))

    def test_cancelar_terceiro_com_canc_ticket(self):
        ctx = _ctx(funcs=("CANCEL_TICKET",))
        self.assertTrue(rbac.pode_cancelar(ctx, self.TICKET_TERCEIRO))
        self.assertFalse(rbac.pode_cancelar(ctx, self.TICKET_OUTRO_AMB))

    def test_cancelar_admin(self):
        self.assertTrue(rbac.pode_cancelar(_ctx(is_admin=True, funcs=(), ambs=()), self.TICKET_OUTRO_AMB))

    def test_cancelar_perfil_inativo(self):
        ctx = _ctx(funcs=("CANCEL_TICKET", "EXEC_SCRIPT"), perfil_ativo="N")
        self.assertFalse(rbac.pode_cancelar(ctx, self.TICKET_PROPRIO))

    def test_cancelar_ticket_invalido(self):
        self.assertFalse(rbac.pode_cancelar(_ctx(), None))
        self.assertFalse(rbac.pode_cancelar(_ctx(), {"environment": "PRODUCAO", "requested_by": None}))

    def test_ver_ticket(self):
        ctx = _ctx(funcs=("VIEW_LOGS",))
        self.assertTrue(rbac.pode_ver_ticket(ctx, self.TICKET_TERCEIRO))
        self.assertFalse(rbac.pode_ver_ticket(ctx, self.TICKET_OUTRO_AMB))
        self.assertFalse(rbac.pode_ver_ticket(_ctx(funcs=("EXEC_SCRIPT",)), self.TICKET_PROPRIO))
        self.assertTrue(rbac.pode_ver_ticket(_ctx(is_admin=True, ambs=()), self.TICKET_OUTRO_AMB))

    def test_ver_ambiente(self):
        self.assertTrue(rbac.pode_ver_ambiente(_ctx(), {"name": "PRODUCAO"}))
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
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0},
    "op.prod": {"usuario_id": 2, "login": "op.prod", "perfil_id": 2, "perm_versao": 1, "sessao_epoch": 0},
    "consulta": {"usuario_id": 4, "login": "consulta", "perfil_id": 4, "perm_versao": 1, "sessao_epoch": 0},
}
# Seed FAKE: perfil 1 ADMINISTRADOR (unico admin), 3 OPERATOR_HML (ambiente DESENV inativo associado),
# 4 CONSULTA (VIEW_LOGS; PRODUCAO e HOMOLOGACAO). Funcionalidades 1 EXEC_SCRIPT, 2 VIEW_LOGS, 3 CANCEL_TICKET.
PERFIL_ADMIN, PERFIL_HML, PERFIL_CONSULTA = 1, 3, 4
F_EXEC, F_VER_LOGS = 1, 2
AMB_PRODUCAO, AMB_HOMOLOGACAO, AMB_DESENV = 1, 2, 3


class _BasePerfis(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(security, "ITERACOES", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_DEV_PASSWORD: "senha-dev-de-teste-123"})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configure, None)

        self.rbac_repo = repo_factory.get("rbac")
        self.catalog = repo_factory.get("catalog")
        self.users = repo_factory.get("users")
        self.audit = repo_factory.get("audit")
        self.log = logging.getLogger("sss_teste_perfis")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        self.auth = auth_service.ServicoAuth(self.users, self.rbac_repo, self.catalog, self.audit,
                                             5, 900, self.log)
        self.ctx = dict((login, self.auth.revalidar(sessao)) for login, sessao in SESSOES.items())
        # Gestor: perfil nao admin com MANAGE_PROFILES; exercita o ultimo admin sem cair na autoprotecao.
        self.ctx["gestor"] = dict(self.ctx["op.prod"], features=frozenset(["MANAGE_PROFILES"]))
        # Administrador fora do perfil ADMINISTRADOR: exercita a protecao do ultimo admin pelo servico,
        # ja que quem nao e admin nao altera perfil de admin (CR-008, E1).
        self.ctx["admin_externo"] = dict(self.ctx["admin"], profile_id=999)
        self.svc = ServicoAdminPerfis(self.rbac_repo, self.catalog, self.users, self.log)
        self.aud_base = max([a["id"] for a in self.audit.list(pagina=1, tamanho=1000)["itens"]] or [0])

    def _auditorias(self, acao):
        return [a for a in self.audit.list(filtros={"action": acao}, pagina=1, tamanho=100)["itens"]
                if a["entity"] == "tbsss_profiles" and a["id"] > self.aud_base]

    def _versao(self, perfil_id):
        return self.rbac_repo.profiles_get(perfil_id)["perm_version"]

    def _salvar_matriz(self, perfil_id, funcs, ambs, scrs, versao=None):
        versao = self._versao(perfil_id) if versao is None else versao
        return self.svc.salvar_matriz(self.ctx["admin"], IP, str(perfil_id), [str(x) for x in funcs],
                                      [str(x) for x in ambs], [str(x) for x in scrs], str(versao))

    def _matriz(self, perfil_id):
        return self.rbac_repo.matrix_get(perfil_id)


class TestMatriz(_BasePerfis):

    def test_diff_formato(self):
        rotulos = {"funcs": {1: "EXEC_SCRIPT", 2: "VIEW_LOGS"}, "ambs": {1: "PRODUCAO"}, "scrs": {7: "carga"}}
        diff = perfis_mod.diff_matriz({"funcs": {2}, "ambs": set(), "scrs": {7}},
                                      {"funcs": {1}, "ambs": {1}, "scrs": set()}, rotulos)
        self.assertEqual(diff, "+EXEC_SCRIPT, -VIEW_LOGS, +amb:PRODUCAO, -scr:carga")
        self.assertIsNone(perfis_mod.diff_matriz({"funcs": {1}}, {"funcs": {1}}, rotulos))

    def test_salvar_matriz_incrementa_versao_e_audita_diff(self):
        antes = self._matriz(PERFIL_CONSULTA)
        versao = self._versao(PERFIL_CONSULTA)
        scrs = [x for x in antes["scrs"] if x != 3]
        diff, erros = self._salvar_matriz(PERFIL_CONSULTA, [F_EXEC], antes["ambs"], scrs)
        self.assertEqual(erros, {})
        self.assertEqual(diff, "+EXEC_SCRIPT, -VIEW_LOGS, -scr:cleanup_tmp")
        self.assertEqual(self._versao(PERFIL_CONSULTA), versao + 1)
        self.assertEqual(sorted(self._matriz(PERFIL_CONSULTA)["funcs"]), [F_EXEC])
        aud = self._auditorias("PERM_UPDATE")
        self.assertEqual(len(aud), 1)
        self.assertEqual((aud[0]["detail"], aud[0]["entity_id"], aud[0]["actor"]), (diff, PERFIL_CONSULTA, "admin"))

    def test_sem_mudanca_nao_incrementa_nem_audita(self):
        m = self._matriz(PERFIL_CONSULTA)
        versao = self._versao(PERFIL_CONSULTA)
        diff, erros = self._salvar_matriz(PERFIL_CONSULTA, m["funcs"], m["ambs"], m["scrs"])
        self.assertEqual((diff, erros), (None, {}))
        self.assertEqual(self._versao(PERFIL_CONSULTA), versao)
        self.assertEqual(self._auditorias("PERM_UPDATE"), [])

    def test_efeito_imediato_na_revalidacao(self):
        self.assertIn("VIEW_LOGS", self.ctx["consulta"]["features"])
        m = self._matriz(PERFIL_CONSULTA)
        self._salvar_matriz(PERFIL_CONSULTA, [], m["ambs"], m["scrs"])
        sessao = dict(SESSOES["consulta"])
        ctx = self.auth.revalidar(sessao)
        self.assertNotIn("VIEW_LOGS", ctx["features"])
        self.assertEqual(ctx["perm_version"], self._versao(PERFIL_CONSULTA))

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

    def test_inativo_associado_pode_sair_e_novo_inativo_rejeitado(self):
        # CR-003 D9: associacao a item inativo pode ser removida; nunca readicionada.
        m = self._matriz(PERFIL_HML)
        self.assertIn(AMB_DESENV, m["ambs"])
        diff, erros = self._salvar_matriz(PERFIL_HML, m["funcs"], m["ambs"] + [AMB_PRODUCAO], m["scrs"])
        self.assertEqual((diff, erros), ("+amb:PRODUCAO", {}))
        self.assertIn(AMB_DESENV, self._matriz(PERFIL_HML)["ambs"])
        m = self._matriz(PERFIL_HML)
        sem_desenv = [a for a in m["ambs"] if a != AMB_DESENV]
        diff, erros = self._salvar_matriz(PERFIL_HML, m["funcs"], sem_desenv, m["scrs"])
        self.assertEqual((diff, erros), ("-amb:DESENV", {}))
        self.assertNotIn(AMB_DESENV, self._matriz(PERFIL_HML)["ambs"])
        diff, erros = self._salvar_matriz(PERFIL_HML, m["funcs"], sem_desenv + [AMB_DESENV], m["scrs"])
        self.assertEqual(erros, {CAMPO_GERAL: perfis_mod.MSG_MATRIZ_INATIVO})
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
        self.assertEqual([g["script_group"] for g in tela["funcs"]], ["ADMIN", "OPERATION"])
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
            self.svc.alternar_ativo(self.ctx["admin_externo"], IP, str(PERFIL_ADMIN), form["version"])
        self.assertEqual(cm.exception.mensagem, perfis_mod.MSG_ULTIMO_ADMIN)
        perfil = self.rbac_repo.profiles_get(PERFIL_ADMIN)
        self.assertEqual((perfil["active"], perfil["perm_version"]), ("Y", 1))
        self.assertEqual(self._auditorias("DEACTIVATE"), [])

    def test_remover_is_admin_do_unico_perfil_admin_e_negado(self):
        form = self._form(PERFIL_ADMIN)
        _id, erros = self.svc.salvar(self.ctx["admin_externo"], IP, str(PERFIL_ADMIN),
                                     {"name": form["name"], "description": form["description"], "is_admin": None,
                                      "version": form["version"]})
        self.assertEqual(erros, {CAMPO_GERAL: perfis_mod.MSG_ULTIMO_ADMIN})
        self.assertEqual(self.rbac_repo.profiles_get(PERFIL_ADMIN)["is_admin"], "Y")

    def test_com_outro_admin_ativo_a_operacao_passa(self):
        novo_id, erros = self.svc.salvar(self.ctx["admin"], IP, None, {"name": "ADMIN_RESERVA", "is_admin": "Y"})
        self.assertEqual(erros, {})
        u = self.users.get_by_login("op.hml")
        self.users.update(u["id"], {"profile_id": novo_id}, ator="teste")
        form = self._form(PERFIL_ADMIN)
        alterado = self.svc.alternar_ativo(self.ctx["admin_externo"], IP, str(PERFIL_ADMIN), form["version"])
        self.assertEqual(alterado["active"], "N")
        aud = self._auditorias("DEACTIVATE")
        self.assertEqual(len(aud), 1)
        self.assertIn(u"usuários ativos afetados: 1", aud[0]["detail"])

    def test_perfil_admin_sem_usuarios_nao_conta_como_admin_ativo(self):
        # Um segundo perfil admin sem usuarios nao livra o ultimo admin real.
        self.svc.salvar(self.ctx["admin"], IP, None, {"name": "ADMIN_VAZIO", "is_admin": "Y"})
        form = self._form(PERFIL_ADMIN)
        with self.assertRaises(OperacaoNegada) as cm:
            self.svc.alternar_ativo(self.ctx["admin_externo"], IP, str(PERFIL_ADMIN), form["version"])
        self.assertEqual(cm.exception.mensagem, perfis_mod.MSG_ULTIMO_ADMIN)

    def test_quem_nao_e_admin_nao_altera_perfil_admin(self):
        form = self._form(PERFIL_ADMIN)
        with self.assertRaises(OperacaoNegada) as cm:
            self.svc.alternar_ativo(self.ctx["gestor"], IP, str(PERFIL_ADMIN), form["version"])
        self.assertEqual(cm.exception.mensagem, perfis_mod.MSG_SO_ADMIN)
        _id, erros = self.svc.salvar(self.ctx["gestor"], IP, str(PERFIL_ADMIN),
                                     {"name": form["name"], "description": form["description"], "is_admin": None,
                                      "version": form["version"]})
        self.assertEqual(erros, {CAMPO_GERAL: perfis_mod.MSG_SO_ADMIN})
        self.assertEqual(self.rbac_repo.profiles_get(PERFIL_ADMIN)["is_admin"], "Y")

    def test_protecao_e_atomica_no_repositorio(self):
        with self.assertRaises(RepoViolation) as cm:
            self.rbac_repo.profiles_update(PERFIL_ADMIN, {"active": "N"}, ator="teste")
        self.assertEqual(cm.exception.constraint, "sss_ultimo_admin")
        self.assertEqual(self.rbac_repo.lock_active_admins(), [1])


class TestCadastroPerfil(_BasePerfis):

    def test_inclusao_validacoes_e_auditoria(self):
        for nome, msg in (("", perfis_mod.MSG_NOME_OBRIGATORIO), ("auditor", perfis_mod.MSG_NOME_INVALIDO),
                          ("READ_ONLY", perfis_mod.MSG_NOME_DUPLICADO)):
            _id, erros = self.svc.salvar(self.ctx["admin"], IP, None, {"name": nome})
            self.assertEqual(erros, {"name": msg}, nome)
        pid, erros = self.svc.salvar(self.ctx["admin"], IP, None, {"name": "AUDITOR", "description": "Leitura"})
        self.assertEqual(erros, {})
        perfil = self.rbac_repo.profiles_get(pid)
        self.assertEqual((perfil["is_admin"], perfil["active"], perfil["perm_version"]), ("N", "Y", 1))
        self.assertIn("name: AUDITOR", self._auditorias("CREATE")[0]["detail"])

    def test_alteracao_concorrente_e_auditoria(self):
        aba1 = self.svc.formulario(self.ctx["admin"], str(PERFIL_CONSULTA))
        aba2 = self.svc.formulario(self.ctx["admin"], str(PERFIL_CONSULTA))
        self.assertEqual(aba1["usuarios_ativos"], 1)
        _id, erros = self.svc.salvar(self.ctx["admin"], IP, str(PERFIL_CONSULTA),
                                     {"name": "CONSULTA_GERAL", "description": aba2["description"], "version": aba2["version"]})
        self.assertEqual(erros, {})
        _id, erros = self.svc.salvar(self.ctx["admin"], IP, str(PERFIL_CONSULTA),
                                     {"name": "READ_ONLY", "description": "x", "version": aba1["version"]})
        self.assertEqual(erros, {CAMPO_GERAL: admin_crud.MSG_CONFLITO})
        aud = self._auditorias("UPDATE")
        self.assertEqual(len(aud), 1)
        self.assertIn(u"name: READ_ONLY \u2192 CONSULTA_GERAL", aud[0]["detail"])
        self.assertEqual(self._versao(PERFIL_CONSULTA), 2)

    def test_reativar(self):
        form = self.svc.formulario(self.ctx["admin"], str(PERFIL_CONSULTA))
        self.svc.alternar_ativo(self.ctx["admin"], IP, str(PERFIL_CONSULTA), form["version"])
        form = self.svc.formulario(self.ctx["admin"], str(PERFIL_CONSULTA))
        with self.assertRaises(RepoConflict):
            self.svc.alternar_ativo(self.ctx["admin"], IP, str(PERFIL_CONSULTA), "x")
        self.assertEqual(self.svc.alternar_ativo(self.ctx["admin"], IP, str(PERFIL_CONSULTA), form["version"])["active"], "Y")

    def test_acesso_negado_e_nao_encontrado(self):
        for chamada in (lambda c: self.svc.list(c, {}, 1, 20), lambda c: self.svc.matriz(c, "1"),
                        lambda c: self.svc.salvar_matriz(c, IP, "4", [], [], [], "1"),
                        lambda c: self.svc.alternar_ativo(c, IP, "4", "x")):
            with self.assertRaises(AcessoNegado):
                chamada(self.ctx["op.prod"])
        for pid in ("999", "abc", "0"):
            with self.assertRaises(RepoNotFound):
                self.svc.matriz(self.ctx["admin"], pid)

    def test_filtros(self):
        self.assertEqual(perfis_mod.normalizar_filtros({"name": "OPER", "active": "Y", "is_admin": "N"}),
                         {"name": "OPER", "active": "Y", "is_admin": "N"})
        self.assertEqual(perfis_mod.normalizar_filtros({"name": "<x>", "active": "?"}), {})


if __name__ == "__main__":
    unittest.main()
