# -*- coding: utf-8 -*-
"""Testes de ticket_service.py (F3.2) sobre o backend FAKE e uma arvore de scripts temporaria."""
import _testenv  # noqa: F401

import datetime
import json
import logging
import os
import shutil
import stat
import tempfile
import unittest
from unittest import mock

import auth_service
import params_compiler
import repo_factory
import security
import ticket_service
from ticket_service import AcessoNegado, ServicoTicket

IP = "10.1.2.3"
SEGREDO = "tok-ultra-secreto-42"
SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1},
    "op.hml": {"usuario_id": 3, "login": "op.hml", "perfil_id": 3, "perm_versao": 1},
    "consulta": {"usuario_id": 4, "login": "consulta", "perfil_id": 4, "perm_versao": 1},
}
ARQUIVOS = ("carga_diaria.py", "relatorio_mensal.py", "cleanup_tmp.sh", "sync_tabelas.sh",
            "validacao_fiscal.py")

# Parametros do seed FAKE (repo_fake/seed.py).
PRM_DATA_REF, PRM_LIMITE, PRM_MODO, PRM_VERBOSE, PRM_CHAVE_API = 1, 2, 3, 4, 6


def _criar_arvore():
    base = tempfile.mkdtemp(prefix="sss_tck_")
    for nome in ARQUIVOS:
        caminho = os.path.join(base, nome)
        with open(caminho, "w") as f:
            f.write("# teste\n")
        os.chmod(caminho, 0o444)
    os.chmod(base, 0o555)
    return os.path.realpath(base)


def _remover_arvore(base):
    os.chmod(base, stat.S_IRWXU)
    shutil.rmtree(base)


@unittest.skipIf(os.geteuid() == 0, "path_guard rejeita qualquer arquivo quando executado como root")
class TestTicketService(unittest.TestCase):

    def setUp(self):
        # Iteracoes reduzidas so para o hash das senhas do seed; nao afeta o fluxo testado.
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
        self.tickets = repo_factory.obter("tickets")
        self.auditoria = repo_factory.obter("auditoria")
        self.log = logging.getLogger("sss_teste_ticket")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        auth = auth_service.ServicoAuth(
            repo_factory.obter("usuarios"), repo_factory.obter("rbac"), self.catalogo, self.auditoria,
            5, 900, self.log)
        self.ctx = dict((login, auth.revalidar(sessao)) for login, sessao in SESSOES.items())

        self.base = _criar_arvore()
        self.addCleanup(_remover_arvore, self.base)
        self.svc = ServicoTicket(self.catalogo, self.tickets, self.base, (os.geteuid(),), self.log)

    def _total_tickets(self):
        return self.tickets.listar(pagina=1, tamanho=100)["total"]

    def _criar(self, login="op.hml", script_id="1", ambiente="HOMOLOGACAO", respostas=None,
               prioridade="2", scheduled_at=""):
        return self.svc.criar_ticket(self.ctx[login], IP, script_id, ambiente, respostas or {},
                                     prioridade, scheduled_at)

    # ------------------------------------------------------------- sucesso

    def test_criacao_ok_com_snapshot_correto(self):
        respostas = {"data_ref": "2026-10-20", "modo_exec": "SIMULACAO", "chave_api": SEGREDO}
        tid, erros = self._criar(respostas=respostas)
        self.assertEqual(erros, {})
        self.assertIsNotNone(tid)

        ticket = self.tickets.obter(tid)
        self.assertEqual(ticket["status"], "PENDING")
        self.assertEqual(ticket["script_id"], 1)
        self.assertEqual(ticket["ambiente"], "HOMOLOGACAO")
        self.assertEqual(ticket["solicitante"], "op.hml")
        self.assertEqual(ticket["ip_origem"], IP)
        self.assertEqual(ticket["prioridade"], 2)

        bruto = ticket["parametros_enviados"]
        snap = json.loads(bruto)
        self.assertEqual(bruto, json.dumps(snap, ensure_ascii=False, sort_keys=True))
        self.assertEqual(sorted(snap), sorted(params_compiler._CHAVES_SNAPSHOT))
        real = os.path.join(self.base, "carga_diaria.py")
        self.assertEqual(snap["versao"], 1)
        self.assertEqual(snap["script_nome"], "carga_diaria")
        self.assertEqual(snap["path_file"], "carga_diaria.py")
        self.assertEqual(snap["script_real"], real)
        self.assertEqual(snap["tipo_param"], "NOMEADO")
        self.assertEqual(snap["argv"], [
            "/usr/bin/python3", "-I", real,
            "--data-ref", "2026-10-20", "-n", "5000", "--modo", "SIMULACAO",
            "--verbose", "--api-key", SEGREDO,
        ])
        self.assertEqual(snap["respostas"], {"data_ref": "2026-10-20", "limite_linhas": "5000",
                                             "modo_exec": "SIMULACAO", "verbose": True,
                                             "chave_api": SEGREDO})
        self.assertEqual(snap["sensiveis"], ["chave_api"])
        datetime.datetime.strptime(snap["compilado_em"], "%Y-%m-%d %H:%M:%S")

    def test_ticket_resp_com_valores_resolvidos(self):
        tid, _ = self._criar(respostas={"data_ref": "2026-10-20", "chave_api": SEGREDO})
        valores = dict((r["parametro_id"], r["valor_resposta"]) for r in self.tickets.respostas(tid))
        # limite_linhas, modo_exec e verbose vieram dos padroes (precedencia §6.1).
        self.assertEqual(valores, {PRM_DATA_REF: "2026-10-20", PRM_LIMITE: "5000", PRM_MODO: "REAL",
                                   PRM_VERBOSE: "true", PRM_CHAVE_API: SEGREDO})

    def test_auditoria_gravada_sem_valor_sensivel(self):
        tid, _ = self._criar(respostas={"chave_api": SEGREDO})
        regs = self.auditoria.listar(filtros={"acao": "TICKET_CRIAR", "entidade_id": tid})["itens"]
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0]["ator"], "op.hml")
        self.assertEqual(regs[0]["ip_origem"], IP)
        self.assertEqual(regs[0]["entidade"], "tbsss_tickets")
        self.assertNotIn(SEGREDO, regs[0]["detalhe"] or "")

    def test_scheduled_at_futuro_e_admin_prioridade_1(self):
        futuro = (self.tickets.agora() + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        tid, erros = self._criar(login="admin", script_id="6", ambiente="PRODUCAO", prioridade="1",
                                 scheduled_at=futuro)
        self.assertEqual(erros, {})
        ticket = self.tickets.obter(tid)
        self.assertEqual(ticket["prioridade"], 1)
        self.assertEqual(ticket["scheduled_at"], datetime.datetime.strptime(futuro, "%Y-%m-%dT%H:%M"))

    def test_checkbox_desmarcado_vence_padrao_verdadeiro(self):
        # hidden "false" + checkbox ausente: vale "false" e a flag e omitida.
        tid, _ = self._criar(respostas={"verbose": ["false"]})
        snap = json.loads(self.tickets.obter(tid)["parametros_enviados"])
        self.assertNotIn("--verbose", snap["argv"])
        tid2, _ = self._criar(respostas={"verbose": ["false", "true"]})
        self.assertIn("--verbose", json.loads(self.tickets.obter(tid2)["parametros_enviados"])["argv"])

    # ---------------------------------------------------------- autorizacao

    def test_sem_exec_script(self):
        antes = self._total_tickets()
        with self.assertRaises(AcessoNegado) as cm:
            self._criar(login="consulta", script_id="1", ambiente="PRODUCAO")
        self.assertEqual(cm.exception.motivo, "SEM_FUNC")
        self.assertEqual(self.svc.scripts_disponiveis(self.ctx["consulta"]), [])
        self.assertEqual(self._total_tickets(), antes)

    def test_script_nao_homologado_no_ambiente(self):
        # sync_tabelas (4) so e homologado em HOMOLOGACAO; admin nao dispensa a homologacao.
        with self.assertRaises(AcessoNegado) as cm:
            self._criar(login="admin", script_id="4", ambiente="PRODUCAO")
        self.assertEqual(cm.exception.motivo, "SEM_HOMOLOGACAO")
        with self.assertRaises(AcessoNegado):
            self.svc.previa(self.ctx["admin"], "4", "PRODUCAO", {})

    def test_script_forjado_e_ambiente_nao_autorizado(self):
        ctx = self.ctx["op.hml"]
        for script_id, ambiente in (("6", "PRODUCAO"), ("1", "PRODUCAO"), ("999", "HOMOLOGACAO"),
                                    ("abc", "HOMOLOGACAO"), ("1", "INEXISTENTE")):
            with self.assertRaises(AcessoNegado):
                self.svc.preparar_formulario(ctx, script_id, ambiente)
        with self.assertRaises(AcessoNegado):
            self.svc.ambientes_disponiveis(ctx, "6")

    def test_listas_filtradas_para_op_hml(self):
        ctx = self.ctx["op.hml"]
        ids = sorted(s["id"] for g in self.svc.scripts_disponiveis(ctx) for s in g["scripts"])
        self.assertEqual(ids, [1, 2, 3, 4])
        _script, ambientes = self.svc.ambientes_disponiveis(ctx, "1")
        self.assertEqual([a["nome"] for a in ambientes], ["HOMOLOGACAO"])

    # ------------------------------------------------------------ validacao

    def test_obrigatorio_faltando(self):
        vinculos = [{"parametro_id": v["parametro_id"], "ordem": v["ordem"], "obrigatorio": v["obrigatorio"],
                     "valor_padrao_sub": None if v["codigo"] == "data_ref" else v["valor_padrao_sub"]}
                    for v in self.catalogo.script_params_obter(1)]
        self.catalogo.script_params_salvar(1, vinculos)
        antes = self._total_tickets()
        tid, erros = self._criar(respostas={"data_ref": "   "})
        self.assertIsNone(tid)
        self.assertIn("data_ref", erros)
        self.assertEqual(self._total_tickets(), antes)

    def test_regex_invalida_e_todos_os_erros_de_uma_vez(self):
        antes = self._total_tickets()
        passado = (self.tickets.agora() - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        tid, erros = self._criar(login="admin", script_id="6", ambiente="PRODUCAO",
                                 respostas={"codigo_filial": "ABC", "taxa_ajuste": "x"},
                                 prioridade="9", scheduled_at=passado)
        self.assertIsNone(tid)
        self.assertEqual(sorted(erros), ["codigo_filial", "prioridade", "scheduled_at", "taxa_ajuste"])
        self.assertEqual(self._total_tickets(), antes)

    def test_prioridade_1_por_nao_admin(self):
        tid, erros = self._criar(prioridade="1")
        self.assertIsNone(tid)
        self.assertEqual(list(erros), ["prioridade"])
        self.assertNotIn(1, [p for p, _ in self.svc.preparar_formulario(
            self.ctx["op.hml"], "1", "HOMOLOGACAO")["prioridades"]])

    def test_scheduled_at_no_passado(self):
        passado = (self.tickets.agora() - datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
        tid, erros = self._criar(scheduled_at=passado)
        self.assertIsNone(tid)
        self.assertEqual(list(erros), ["scheduled_at"])
        tid, erros = self._criar(scheduled_at="31/12/2099")
        self.assertEqual(list(erros), ["scheduled_at"])

    def test_path_guard_rejeita_script(self):
        os.chmod(self.base, 0o755)
        tid, erros = self._criar()
        self.assertIsNone(tid)
        self.assertEqual(erros, {ticket_service.CAMPO_GERAL: ticket_service.MSG_SCRIPT_INDISPONIVEL})

    # ----------------------------------------------------- previa e formulario

    def test_previa_mascara_sensivel(self):
        argv, erros = self.svc.previa(self.ctx["op.hml"], "1", "HOMOLOGACAO", {"chave_api": SEGREDO})
        self.assertEqual(erros, {})
        self.assertNotIn(SEGREDO, " ".join(argv))
        self.assertEqual(argv[argv.index("--api-key") + 1], params_compiler.MASCARA)
        argv, erros = self.svc.previa(self.ctx["op.hml"], "1", "HOMOLOGACAO", {"modo_exec": "X"})
        self.assertIsNone(argv)
        self.assertIn("modo_exec", erros)

    def test_formulario_nao_expoe_sensivel(self):
        form = self.svc.preparar_formulario(self.ctx["op.hml"], "1", "HOMOLOGACAO",
                                            valores={"chave_api": SEGREDO, "data_ref": "2026-01-01"})
        campos = dict((c["codigo"], c) for c in form["campos"])
        self.assertEqual([c["codigo"] for c in form["campos"]],
                         ["data_ref", "limite_linhas", "modo_exec", "verbose", "chave_api"])
        self.assertIsNone(campos["chave_api"]["valor"])
        self.assertIsNone(campos["chave_api"]["padrao"])
        self.assertTrue(campos["chave_api"]["tem_padrao"])
        self.assertNotIn("segredo_dev_123", json.dumps(form, default=str))
        self.assertEqual(campos["data_ref"]["valor"], "2026-01-01")
        self.assertEqual(campos["modo_exec"]["padrao_texto"], "Execucao Real")
        self.assertTrue(campos["verbose"]["marcado"])


if __name__ == "__main__":
    unittest.main()
