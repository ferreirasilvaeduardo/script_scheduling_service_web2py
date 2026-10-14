# -*- coding: utf-8 -*-
"""Testes de rbac.py (F2.2): pode_executar, pode_cancelar, pode_ver_ticket, prioridade e tem_func."""
import _testenv  # noqa: F401

import re
import unittest

import rbac
from rbac import Motivo


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


if __name__ == "__main__":
    unittest.main()
