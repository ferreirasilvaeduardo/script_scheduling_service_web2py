# -*- coding: utf-8 -*-
"""Testes de admin_usuarios_service.py e auth_service.trocar_senha (F4.3) sobre o backend FAKE."""
import _testenv  # noqa: F401

import datetime
import logging
import os
import unittest
from unittest import mock

import admin_crud
import admin_usuarios_service as usr_mod
import auth_service
import repo_factory
import security
from admin_crud import CAMPO_GERAL, AcessoNegado, OperacaoNegada
from admin_usuarios_service import ServicoAdminUsuarios
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao

IP = "10.2.2.2"
SENHA_DEV = "senha-dev-de-teste-123"
SENHA_NOVA = "Nova-Senha-Forte-2026"
SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0},
    "op.prod": {"usuario_id": 2, "login": "op.prod", "perfil_id": 2, "perm_versao": 1, "sessao_epoch": 0},
}
# Seed FAKE: admin (1, perfil ADMINISTRADOR, unico admin), op.prod (2), op.hml (3), consulta (4),
# inativo (5) e bloqueado (6, 5 tentativas, bloqueado por 30 min). Perfis 1-4 ativos.
U_ADMIN, U_OPPROD, U_BLOQUEADO = 1, 2, 6
P_ADMIN, P_OPPROD, P_CONSULTA = 1, 2, 4
AGORA = datetime.datetime(2026, 10, 15, 9, 0, 0)


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

        self.usuarios = repo_factory.obter("usuarios")
        self.rbac_repo = repo_factory.obter("rbac")
        self.auditoria = repo_factory.obter("auditoria")
        self.log = logging.getLogger("sss_teste_usuarios")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        self.auth = auth_service.ServicoAuth(self.usuarios, self.rbac_repo, repo_factory.obter("catalogo"),
                                             self.auditoria, 5, 900, self.log, relogio=lambda: AGORA)
        self.ctx = dict((login, self.auth.revalidar(sessao)) for login, sessao in SESSOES.items())
        # O seed usa o relogio real: o bloqueio do usuario 'bloqueado' e reposicionado a partir de AGORA.
        self.usuarios.alterar(U_BLOQUEADO, {"bloqueado_ate": AGORA + datetime.timedelta(minutes=30)}, ator="teste")
        self.svc = ServicoAdminUsuarios(self.usuarios, self.rbac_repo, self.log, relogio=lambda: AGORA)
        self.aud_base = max([a["id"] for a in self.auditoria.listar(pagina=1, tamanho=1000)["itens"]] or [0])

    def _auditorias(self, acao=None):
        filtros = {"acao": acao} if acao else None
        return [a for a in self.auditoria.listar(filtros=filtros, pagina=1, tamanho=200)["itens"]
                if a["entidade"] == "tbsss_usuarios" and a["id"] > self.aud_base]

    def _incluir(self, **mudancas):
        dados = {"login": "maria.silva", "nome": "Maria Silva", "perfil_id": str(P_CONSULTA),
                 "senha": SENHA_NOVA, "confirmacao": SENHA_NOVA}
        dados.update(mudancas)
        return self.svc.salvar(self.ctx["admin"], IP, None, dados)

    def _form(self, uid, ator="admin"):
        return self.svc.formulario(self.ctx[ator], str(uid))

    def _editar(self, uid, ator="admin", **mudancas):
        f = self._form(uid, ator)
        dados = {"nome": f["nome"], "perfil_id": str(f["perfil_id"]), "versao": f["versao"]}
        dados.update(mudancas)
        return self.svc.salvar(self.ctx[ator], IP, str(uid), dados)

    def _sem_segredo(self, texto, *segredos):
        for s in segredos:
            self.assertNotIn(s, texto)
        self.assertNotIn("pbkdf2", texto)


class TestInclusao(_Base):

    def test_auditoria_mostra_perfil_pelo_nome_e_login_sem_espacos(self):
        # CR-003 P6 (README §4.4) e C2.
        _id, erros = self._incluir(login=" maria.silva")
        self.assertEqual(erros, {"login": admin_crud.MSG_ESPACOS})
        uid, erros = self._incluir()
        self.assertEqual(erros, {})
        detalhe = [a for a in self._auditorias("CAD_INSERIR") if a["entidade_id"] == uid][0]["detalhe"]
        self.assertIn("perfil: CONSULTA", detalhe)
        self.assertNotIn("perfil_id", detalhe)

    def test_inclusao_ok_com_hash_e_auditoria_sem_senha(self):
        uid, erros = self._incluir()
        self.assertEqual(erros, {})
        u = self.usuarios.obter_por_id(uid)
        self.assertEqual((u["login"], u["nome"], u["perfil_id"], u["ativo"]), ("maria.silva", "Maria Silva", P_CONSULTA, "S"))
        self.assertTrue(security.verificar_senha(SENHA_NOVA, u["senha_hash"]))
        self.assertEqual(u["senha_alterada_em"], AGORA)
        aud = self._auditorias("CAD_INSERIR")
        self.assertEqual(len(aud), 1)
        self.assertIn("login: maria.silva", aud[0]["detalhe"])
        self._sem_segredo(aud[0]["detalhe"], SENHA_NOVA, u["senha_hash"])

    def test_login_invalido_ou_duplicado(self):
        for login in ("Maria", "ab", "a" * 31, "maria silva", u"joão"):
            _uid, erros = self._incluir(login=login)
            self.assertEqual(erros.get("login"), usr_mod.MSG_LOGIN_INVALIDO, login)
        _uid, erros = self._incluir(login="op.prod")
        self.assertEqual(erros, {"login": usr_mod.MSG_LOGIN_DUPLICADO})
        self.assertEqual(self._auditorias("CAD_INSERIR"), [])

    def test_senha_fraca_e_confirmacao_divergente(self):
        _uid, erros = self._incluir(senha="curta", confirmacao="curta")
        self.assertEqual(erros, {"senha": security.validar_politica_senha("curta")[0]})
        _uid, erros = self._incluir(confirmacao=SENHA_NOVA + "x")
        self.assertEqual(erros, {"confirmacao": usr_mod.MSG_CONFIRMACAO})
        _uid, erros = self._incluir(senha="", confirmacao="")
        self.assertEqual(erros, {"senha": usr_mod.MSG_SENHA_OBRIGATORIA})

    def test_perfil_inativo_ou_inexistente(self):
        form = self.rbac_repo.perfis_obter(P_CONSULTA)
        self.rbac_repo.perfis_alterar(P_CONSULTA, {"ativo": "N"}, ator="teste")
        _uid, erros = self._incluir()
        self.assertEqual(erros, {"perfil_id": usr_mod.MSG_PERFIL_INVALIDO})
        _uid, erros = self._incluir(perfil_id="999")
        self.assertEqual(erros, {"perfil_id": usr_mod.MSG_PERFIL_INVALIDO})
        self.assertEqual(form["nome"], "CONSULTA")


class TestEdicaoEUltimoAdmin(_Base):

    def test_edicao_ignora_login_e_audita(self):
        _uid, erros = self._editar(U_OPPROD, nome="Operador Prod Novo", login="hacker")
        self.assertEqual(erros, {})
        u = self.usuarios.obter_por_id(U_OPPROD)
        self.assertEqual((u["login"], u["nome"]), ("op.prod", "Operador Prod Novo"))
        self.assertIn("nome: Operador Producao", self._auditorias("CAD_ALTERAR")[0]["detalhe"])

    def test_nao_admin_nao_troca_o_proprio_perfil(self):
        # Revisao de 2026-10-20 (CR-008 E1): CAD_USUARIOS sem admin nao muda as proprias permissoes.
        gestor = dict(self.ctx["op.prod"], funcionalidades=frozenset({"CAD_USUARIOS"}))
        f = self.svc.formulario(gestor, str(U_OPPROD))
        _uid, erros = self.svc.salvar(gestor, IP, str(U_OPPROD),
                                      {"nome": f["nome"], "perfil_id": str(P_CONSULTA), "versao": f["versao"]})
        self.assertEqual(erros, {usr_mod.CAMPO_GERAL: usr_mod.MSG_SO_ADMIN})
        self.assertEqual(self.usuarios.obter_por_id(U_OPPROD)["perfil_id"], P_OPPROD)
        # O proprio nome, sem trocar de perfil, continua permitido.
        _uid, erros = self.svc.salvar(gestor, IP, str(U_OPPROD),
                                      {"nome": "Operador Producao", "perfil_id": str(P_OPPROD), "versao": f["versao"]})
        self.assertEqual(erros, {})
        # O administrador continua trocando o perfil de outros usuarios.
        self.assertEqual(self._editar(U_BLOQUEADO, perfil_id=str(P_CONSULTA))[1], {})

    def test_troca_de_perfil_do_ultimo_admin_negada(self):
        # Outro administrador nao pode tirar o unico admin do perfil admin: novo admin cria o cenario.
        novo, _ = self._incluir(login="admin2", perfil_id=str(P_ADMIN))
        self.usuarios.alterar(novo, {"ativo": "N"}, ator="teste")
        ctx2 = dict(self.ctx["admin"], usuario_id=novo, login="admin2")
        f = self.svc.formulario(ctx2, str(U_ADMIN))
        _uid, erros = self.svc.salvar(ctx2, IP, str(U_ADMIN), {"nome": f["nome"], "perfil_id": str(P_CONSULTA),
                                                               "versao": f["versao"]})
        self.assertEqual(erros, {CAMPO_GERAL: usr_mod.MSG_ULTIMO_ADMIN})
        self.assertEqual(self.usuarios.obter_por_id(U_ADMIN)["perfil_id"], P_ADMIN)

    def test_desativacao_do_ultimo_admin_negada(self):
        novo, _ = self._incluir(login="gestor", perfil_id=str(P_OPPROD))
        ctx_gestor = dict(self.ctx["admin"], usuario_id=novo, login="gestor")
        f = self.svc.formulario(ctx_gestor, str(U_ADMIN))
        with self.assertRaises(OperacaoNegada) as cm:
            self.svc.alternar_ativo(ctx_gestor, IP, str(U_ADMIN), f["versao"])
        self.assertEqual(cm.exception.mensagem, usr_mod.MSG_ULTIMO_ADMIN)
        self.assertEqual(self.usuarios.obter_por_id(U_ADMIN)["ativo"], "S")
        self.assertEqual(self._auditorias("CAD_DESATIVAR"), [])

    def test_com_dois_admins_desativar_um_passa(self):
        novo, _ = self._incluir(login="admin2", perfil_id=str(P_ADMIN))
        f = self._form(novo)
        alterado = self.svc.alternar_ativo(self.ctx["admin"], IP, str(novo), f["versao"])
        self.assertEqual(alterado["ativo"], "N")
        self.assertNotIn("senha_hash", alterado)
        self.assertEqual(len(self._auditorias("CAD_DESATIVAR")), 1)

    def test_autodesativacao_e_autoperfil_negados(self):
        novo, _ = self._incluir(login="admin2", perfil_id=str(P_ADMIN))
        with self.assertRaises(OperacaoNegada) as cm:
            self.svc.alternar_ativo(self.ctx["admin"], IP, str(U_ADMIN), self._form(U_ADMIN)["versao"])
        self.assertEqual(cm.exception.mensagem, usr_mod.MSG_AUTO_DESATIVAR)
        _uid, erros = self._editar(U_ADMIN, perfil_id=str(P_CONSULTA))
        self.assertEqual(erros, {CAMPO_GERAL: usr_mod.MSG_AUTO_PERFIL})
        _uid, erros = self._editar(U_ADMIN, nome="Admin Renomeado")
        self.assertEqual(erros, {})
        self.assertEqual(novo, self.usuarios.obter_por_login("admin2")["id"])

    def test_desativado_tem_sessao_encerrada_na_revalidacao(self):
        f = self._form(U_OPPROD)
        self.svc.alternar_ativo(self.ctx["admin"], IP, str(U_OPPROD), f["versao"])
        self.assertIsNone(self.auth.revalidar(dict(SESSOES["op.prod"])))

    def test_conflito_de_edicao(self):
        f = self._form(U_OPPROD)
        self._editar(U_OPPROD, nome="Primeira")
        _uid, erros = self.svc.salvar(self.ctx["admin"], IP, str(U_OPPROD),
                                      {"nome": "Segunda", "perfil_id": str(P_OPPROD), "versao": f["versao"]})
        self.assertEqual(erros, {CAMPO_GERAL: admin_crud.MSG_CONFLITO})
        with self.assertRaises(RepoConflito):
            self.svc.alternar_ativo(self.ctx["admin"], IP, str(U_OPPROD), f["versao"])

    def test_ultimo_admin_atomico_no_repositorio(self):
        with self.assertRaises(RepoViolacao) as cm:
            self.usuarios.alterar(U_ADMIN, {"perfil_id": P_CONSULTA}, ator="teste")
        self.assertEqual(cm.exception.constraint, "sss_ultimo_admin")
        with self.assertRaises(RepoViolacao):
            self.usuarios.alterar(U_ADMIN, {"ativo": "N"}, ator="teste")


class TestSenhaEBloqueio(_Base):

    def test_redefinicao_zera_bloqueio_e_audita_sem_senha(self):
        self.assertTrue(self._form(U_BLOQUEADO)["bloqueado"])
        erros = self.svc.redefinir_senha(self.ctx["admin"], IP, str(U_BLOQUEADO), SENHA_NOVA, SENHA_NOVA)
        self.assertEqual(erros, {})
        u = self.usuarios.obter_por_id(U_BLOQUEADO)
        self.assertEqual((u["tentativas_falha"], u["bloqueado_ate"], u["senha_alterada_em"]), (0, None, AGORA))
        self.assertTrue(security.verificar_senha(SENHA_NOVA, u["senha_hash"]))
        aud = self._auditorias("CAD_ALTERAR")
        self.assertEqual([a["detalhe"] for a in aud], ["senha redefinida"])
        self._sem_segredo(repr(self.auditoria.listar(pagina=1, tamanho=1000)), SENHA_NOVA, u["senha_hash"])

    def test_redefinicao_valida_politica_e_confirmacao(self):
        self.assertEqual(self.svc.redefinir_senha(self.ctx["admin"], IP, str(U_OPPROD), "fraca", "fraca"),
                         {"senha": security.validar_politica_senha("fraca")[0]})
        self.assertEqual(self.svc.redefinir_senha(self.ctx["admin"], IP, str(U_OPPROD), SENHA_NOVA, "x"),
                         {"confirmacao": usr_mod.MSG_CONFIRMACAO})

    def test_redefinir_a_propria_senha_pela_administracao_negado(self):
        with self.assertRaises(OperacaoNegada) as cm:
            self.svc.redefinir_senha(self.ctx["admin"], IP, str(U_ADMIN), SENHA_NOVA, SENHA_NOVA)
        self.assertEqual(cm.exception.mensagem, usr_mod.MSG_AUTO_SENHA)

    def test_desbloquear(self):
        alterado = self.svc.desbloquear(self.ctx["admin"], IP, str(U_BLOQUEADO))
        self.assertEqual((alterado["tentativas_falha"], alterado["bloqueado_ate"]), (0, None))
        self.assertTrue(self._auditorias("CAD_ALTERAR")[0]["detalhe"].startswith("desbloqueado"))

    def test_minha_senha_com_atual_errada(self):
        res, erros = self.auth.trocar_senha(self.ctx["op.prod"], IP, "errada-errada-1", SENHA_NOVA, SENHA_NOVA)
        self.assertEqual((res, erros), ("ERRO", {"senha_atual": auth_service.MSG_SENHA_ATUAL}))
        u = self.usuarios.obter_por_id(U_OPPROD)
        self.assertEqual(u["tentativas_falha"], 1)
        self.assertTrue(security.verificar_senha(SENHA_DEV, u["senha_hash"]))
        falhas = [a for a in self.auditoria.listar(filtros={"acao": "LOGIN_FALHA"}, pagina=1, tamanho=50)["itens"]
                  if a["id"] > self.aud_base]
        self.assertEqual(len(falhas), 1)

    def test_minha_senha_bloqueia_apos_limite(self):
        for _ in range(4):
            self.assertEqual(self.auth.trocar_senha(self.ctx["op.prod"], IP, "errada-errada-1", SENHA_NOVA,
                                                    SENHA_NOVA)[0], "ERRO")
        res, _erros = self.auth.trocar_senha(self.ctx["op.prod"], IP, "errada-errada-1", SENHA_NOVA, SENHA_NOVA)
        self.assertEqual(res, "BLOQUEADO")
        self.assertIsNotNone(self.usuarios.obter_por_id(U_OPPROD)["bloqueado_ate"])
        # Mesmo com a senha certa, a conta bloqueada nao troca a senha.
        self.assertEqual(self.auth.trocar_senha(self.ctx["op.prod"], IP, SENHA_DEV, SENHA_NOVA, SENHA_NOVA)[0],
                         "BLOQUEADO")

    def test_minha_senha_ok_e_validacoes(self):
        res, erros = self.auth.trocar_senha(self.ctx["op.prod"], IP, SENHA_DEV, "curta", "curta")
        self.assertEqual(res, "ERRO")
        self.assertIn("nova", erros)
        res, erros = self.auth.trocar_senha(self.ctx["op.prod"], IP, SENHA_DEV, SENHA_NOVA, "outra")
        self.assertEqual(erros, {"confirmacao": auth_service.MSG_CONFIRMACAO})
        res, erros = self.auth.trocar_senha(self.ctx["op.prod"], IP, SENHA_DEV, SENHA_NOVA, SENHA_NOVA)
        self.assertEqual((res, erros), ("OK", {}))
        u = self.usuarios.obter_por_id(U_OPPROD)
        self.assertTrue(security.verificar_senha(SENHA_NOVA, u["senha_hash"]))
        aud = self._auditorias("CAD_ALTERAR")
        self.assertEqual((aud[0]["ator"], aud[0]["detalhe"]), ("op.prod", u"senha alterada pelo próprio usuário"))


class TestListaEAcesso(_Base):

    def test_relogio_padrao_e_o_do_banco(self):
        # CR-003 P3: sem relogio injetado, o service usa o SYSDATE do repositorio (nunca o do no web).
        svc = ServicoAdminUsuarios(self.usuarios, self.rbac_repo, self.log)
        futuro = self.usuarios.agora() + datetime.timedelta(minutes=5)
        self.assertTrue(svc.bloqueado({"bloqueado_ate": futuro}))
        self.assertFalse(svc.bloqueado({"bloqueado_ate": self.usuarios.agora() - datetime.timedelta(seconds=1)}))

    def test_lista_sem_hash_com_bloqueio_e_filtros(self):
        pagina = self.svc.listar(self.ctx["admin"], {}, 1, 20)
        self.assertEqual(pagina["total"], 6)
        for item in pagina["itens"]:
            self.assertNotIn("senha_hash", item)
        bloq = [i for i in pagina["itens"] if i["login"] == "bloqueado"][0]
        self.assertTrue(bloq["bloqueado"])
        self.assertEqual(bloq["perfil_nome"], "OPERADOR_PROD")
        self.assertEqual([i["login"] for i in self.svc.listar(self.ctx["admin"], {"situacao": "B"}, 1, 20)["itens"]],
                         ["bloqueado"])
        self.assertEqual([i["login"] for i in self.svc.listar(self.ctx["admin"], {"situacao": "N"}, 1, 20)["itens"]],
                         ["inativo"])
        self.assertNotIn("senha_hash", self._form(U_OPPROD))
        self.assertEqual(usr_mod.normalizar_filtros({"login": "op", "perfil_id": "2", "situacao": "B"}),
                         {"login": "op", "perfil_id": 2, "situacao": "B"})
        self.assertEqual(usr_mod.normalizar_filtros({"login": "<x>", "perfil_id": "a", "situacao": "Z"}), {})

    def test_acesso_negado_e_nao_encontrado(self):
        ctx = self.ctx["op.prod"]
        for chamada in (lambda: self.svc.listar(ctx, {}, 1, 20), lambda: self.svc.formulario(ctx),
                        lambda: self.svc.salvar(ctx, IP, None, {}), lambda: self.svc.desbloquear(ctx, IP, "6"),
                        lambda: self.svc.redefinir_senha(ctx, IP, "6", SENHA_NOVA, SENHA_NOVA),
                        lambda: self.svc.alternar_ativo(ctx, IP, "6", "x")):
            with self.assertRaises(AcessoNegado):
                chamada()
        for uid in ("999", "abc", "0"):
            with self.assertRaises(RepoNaoEncontrado):
                self.svc.formulario(self.ctx["admin"], uid)


if __name__ == "__main__":
    unittest.main()
