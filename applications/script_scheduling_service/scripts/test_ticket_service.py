# -*- coding: utf-8 -*-
"""Testes de ticket_service.py (F3.2 disparo, F3.3 consulta) sobre o backend FAKE e uma arvore temporaria."""
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
import path_guard
import repo_factory
import security
import ticket_service
import ui_helpers
from repo_errors import RepoNaoEncontrado
from ticket_service import AcessoNegado, ErroReexecucao, ServicoTicket

# UID fictício do agente: o dono dos arquivos de teste é o usuário do teste (CR-007, R-15).
AGENTE_FALSO = 2 ** 31 - 3

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


_SKIP_ROOT = unittest.skipIf(os.geteuid() == 0, "path_guard rejeita qualquer arquivo quando executado como root")


class _BaseTicket(unittest.TestCase):

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
        for sid, nome in enumerate(ARQUIVOS, 1):
            self.catalogo.scripts_alterar(sid, {"path_file": os.path.join(self.base, nome)}, ator="teste")
        # A arvore fica sob /tmp (escrita para todos): a cadeia de pastas para na base travada. Os arquivos
        # sao do usuario do teste; o agente e simulado por outro UID (CR-007, R-15: o agente nunca e dono).
        original = path_guard.resolver
        patcher = mock.patch.object(path_guard, "resolver",
                                    lambda p, u, uid_agente=None, dirs_sss=(), parar_em="/", uids_proibidos=():
                                    original(p, u, AGENTE_FALSO if uid_agente is None else uid_agente,
                                             dirs_sss, self.base, uids_proibidos))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.svc = ServicoTicket(self.catalogo, self.tickets, (os.geteuid(),), self.log)

    def _total_tickets(self):
        return self.tickets.listar(pagina=1, tamanho=100)["total"]

    def _criar(self, login="op.hml", script_id="1", ambiente="HOMOLOGACAO", respostas=None,
               prioridade="2", scheduled_at=""):
        return self.svc.criar_ticket(self.ctx[login], IP, script_id, ambiente, respostas or {},
                                     prioridade, scheduled_at)


@_SKIP_ROOT
class TestTicketService(_BaseTicket):

    # ------------------------------------------------------------- sucesso

    def test_criacao_ok_com_snapshot_correto(self):
        respostas = {"data_ref": "2026-10-20", "modo_exec": "SIMULACAO", "documento_cliente": SEGREDO}
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
        self.assertEqual(snap["versao"], 4)
        self.assertEqual(snap["script_nome"], "carga_diaria")
        caminho_esperado = os.path.join(self.base, "carga_diaria.py")
        self.assertEqual((snap["interpretador"], snap["path_file"]),
                         ("PYTHON3", caminho_esperado))
        self.assertEqual(snap["tipo_param"], "NOMEADO")
        # Snapshot v4 (CR-005 D2): path_file e absoluto; sem pasta_base.
        self.assertNotIn("pasta_base", snap)
        self.assertIn(self.base, bruto)
        self.assertEqual(snap["args"], [
            "--data-ref", "2026-10-20", "-n", "5000", "--modo", "SIMULACAO",
            "--verbose", "--documento", SEGREDO,
        ])
        self.assertEqual(snap["respostas"], {"data_ref": "2026-10-20", "limite_linhas": "5000",
                                             "modo_exec": "SIMULACAO", "verbose": True,
                                             "documento_cliente": SEGREDO})
        self.assertEqual(snap["sensiveis"], ["documento_cliente"])
        datetime.datetime.strptime(snap["compilado_em"], "%Y-%m-%d %H:%M:%S")

    def test_ticket_resp_com_valores_resolvidos(self):
        tid, _ = self._criar(respostas={"data_ref": "2026-10-20", "documento_cliente": SEGREDO})
        valores = dict((r["parametro_id"], r["valor_resposta"]) for r in self.tickets.respostas(tid))
        # limite_linhas, modo_exec e verbose vieram dos padroes (precedencia §6.1).
        self.assertEqual(valores, {PRM_DATA_REF: "2026-10-20", PRM_LIMITE: "5000", PRM_MODO: "REAL",
                                   PRM_VERBOSE: "true", PRM_CHAVE_API: SEGREDO})

    def test_auditoria_gravada_sem_valor_sensivel(self):
        tid, _ = self._criar(respostas={"documento_cliente": SEGREDO})
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
        self.assertNotIn("--verbose", snap["args"])
        tid2, _ = self._criar(respostas={"verbose": ["false", "true"]})
        self.assertIn("--verbose", json.loads(self.tickets.obter(tid2)["parametros_enviados"])["args"])

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
        self.catalogo.script_params_salvar(1, vinculos, ator="teste")
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

    def test_scheduled_at_exato_sem_tolerancia_de_minuto(self):
        # CR-003 P5 (README §5.4): o minuto corrente, ja passado, e recusado.
        repo_factory._fake_store.definir_relogio(lambda: datetime.datetime(2026, 10, 16, 10, 5, 30))
        tid, erros = self._criar(scheduled_at="2026-10-16T10:05")
        self.assertIsNone(tid)
        self.assertIn(u"deixe em branco para rodar agora", erros["scheduled_at"])
        tid, erros = self._criar(scheduled_at="2026-10-16T10:06")
        self.assertEqual(erros, {})

    def test_scheduled_at_limite_366_dias(self):
        # CR-007 D2 (README §5.4): scheduled_at no maximo 366 dias no futuro.
        agora = self.tickets.agora()
        mais_366 = (agora + datetime.timedelta(days=366)).strftime("%Y-%m-%dT%H:%M")
        tid, erros = self._criar(scheduled_at=mais_366)
        self.assertEqual(erros, {})
        mais_367 = (agora + datetime.timedelta(days=367)).strftime("%Y-%m-%dT%H:%M")
        tid, erros = self._criar(scheduled_at=mais_367)
        self.assertIsNone(tid)
        self.assertIn(u"Escolha uma data até", erros.get("scheduled_at", ""))

    def test_path_guard_rejeita_script(self):
        os.chmod(self.base, 0o775)
        tid, erros = self._criar()
        self.assertIsNone(tid)
        self.assertEqual(erros, {ticket_service.CAMPO_GERAL: ticket_service.MSG_SCRIPT_INDISPONIVEL})

    # ----------------------------------------------------- previa e formulario

    def test_previa_mascara_sensivel(self):
        argv, erros = self.svc.previa(self.ctx["op.hml"], "1", "HOMOLOGACAO", {"documento_cliente": SEGREDO})
        self.assertEqual(erros, {})
        self.assertNotIn(SEGREDO, " ".join(argv))
        self.assertEqual(argv[argv.index("--documento") + 1], params_compiler.MASCARA)
        argv, erros = self.svc.previa(self.ctx["op.hml"], "1", "HOMOLOGACAO", {"modo_exec": "X"})
        self.assertIsNone(argv)
        self.assertIn("modo_exec", erros)

    def test_formulario_nao_expoe_sensivel(self):
        form = self.svc.preparar_formulario(self.ctx["op.hml"], "1", "HOMOLOGACAO",
                                            valores={"documento_cliente": SEGREDO, "data_ref": "2026-01-01"})
        campos = dict((c["codigo"], c) for c in form["campos"])
        self.assertEqual([c["codigo"] for c in form["campos"]],
                         ["data_ref", "limite_linhas", "modo_exec", "verbose", "documento_cliente"])
        self.assertIsNone(campos["documento_cliente"]["valor"])
        self.assertIsNone(campos["documento_cliente"]["padrao"])
        self.assertTrue(campos["documento_cliente"]["tem_padrao"])
        self.assertNotIn("00011122233", json.dumps(form, default=str))
        self.assertEqual(campos["data_ref"]["valor"], "2026-01-01")
        self.assertEqual(campos["modo_exec"]["padrao_texto"], "Execucao Real")
        self.assertTrue(campos["verbose"]["marcado"])


@_SKIP_ROOT
class TestClarezaDisparo(_BaseTicket):
    """CR-004 U4 (README §5.4, "Clareza no disparo")."""

    def test_resumo_em_frase_com_sensivel_mascarado(self):
        r = self.svc.resumo_disparo(self.ctx["op.hml"], "1", "HOMOLOGACAO",
                                    {"documento_cliente": "12345678900"}, "3", "")
        self.assertEqual(r["erros"], {})
        resumo = r["resumo"]
        self.assertEqual((resumo["script"], resumo["ambiente"], resumo["quando"], resumo["prioridade"]),
                         ("carga_diaria", "HOMOLOGACAO", u"agora", 3))
        self.assertTrue(resumo["frase"].startswith(u"Vamos rodar carga_diaria no ambiente HOMOLOGACAO agora, "
                                                   u"com prioridade 3."))
        valores = dict((x["rotulo"], x["valor"]) for x in resumo["respostas"])
        self.assertNotIn("12345678900", resumo["frase"])
        self.assertIn(params_compiler.MASCARA, valores.values())
        self.assertTrue(r["argv"])

    def test_resumo_com_horario_e_erros(self):
        futuro = (self.tickets.agora() + datetime.timedelta(days=1)).replace(second=0)
        r = self.svc.resumo_disparo(self.ctx["op.hml"], "1", "HOMOLOGACAO", {}, "2", futuro.strftime("%Y-%m-%dT%H:%M"))
        self.assertEqual(r["resumo"]["quando"], u"em %s às %s" % (futuro.strftime("%d/%m/%Y"), futuro.strftime("%H:%M")))
        r = self.svc.resumo_disparo(self.ctx["op.hml"], "1", "HOMOLOGACAO", {"data_ref": "31/12/2026"}, "2", "")
        self.assertIsNone(r["resumo"])
        self.assertIn("data_ref", r["erros"])

    def test_exemplo_por_tipo_no_formulario(self):
        form = self.svc.preparar_formulario(self.ctx["op.hml"], "1", "HOMOLOGACAO")
        exemplos = dict((c["codigo"], c["exemplo"]) for c in form["campos"])
        self.assertTrue(exemplos["data_ref"].startswith(u"Use o formato AAAA-MM-DD"))
        self.assertEqual(exemplos["modo_exec"], u"Escolha uma das opções da lista.")
        self.assertEqual(exemplos["verbose"], u"Marque para sim; deixe desmarcado para não.")

    def test_ultimas_respostas_sem_sensiveis(self):
        ctx = self.ctx["op.hml"]
        self.assertFalse(self.svc.tem_ultima_execucao(ctx, "1", "HOMOLOGACAO"))
        tid, erros = self._criar(respostas={"data_ref": "2026-11-30", "documento_cliente": "99988877766",
                                            "modo_exec": "SIMULACAO"})
        self.assertEqual(erros, {})
        self.assertTrue(self.svc.tem_ultima_execucao(ctx, "1", "HOMOLOGACAO"))
        valores, avisos = self.svc.ultimas_respostas(ctx, "1", "HOMOLOGACAO")
        self.assertEqual(valores["data_ref"], "2026-11-30")
        self.assertEqual(valores["modo_exec"], "SIMULACAO")
        self.assertNotIn("documento_cliente", valores)
        self.assertEqual(avisos["documento_cliente"], ticket_service.MSG_ULTIMA_SENSIVEL)
        # Opcao removida do catalogo: a resposta antiga deixa de valer e vem com aviso.
        self.catalogo.parametros_alterar(3, {"opcoes_json": '{"REAL":"Execucao Real"}', "valor_padrao": "REAL"}, ator="teste")
        valores, avisos = self.svc.ultimas_respostas(ctx, "1", "HOMOLOGACAO")
        self.assertNotIn("modo_exec", valores)
        self.assertEqual(avisos["modo_exec"], ticket_service.MSG_ULTIMA_MUDOU)


@_SKIP_ROOT
class TestTicketConsulta(_BaseTicket):
    """F3.3: escopo da lista, filtros, detalhe, cancelamento e reexecucao."""

    def _sem(self, login, *funcs):
        ctx = dict(self.ctx[login])
        ctx["funcionalidades"] = frozenset(ctx["funcionalidades"] - set(funcs))
        return ctx

    def _inserir(self, **campos):
        ticket = {"script_id": 1, "ambiente": "HOMOLOGACAO", "solicitante": "admin", "status": "PENDING",
                  "prioridade": 2, "parametros_enviados": "{}"}
        ticket.update(campos)
        return self.tickets.criar(ticket, [])

    def _ids(self, ctx, filtros=None):
        return set(t["id"] for t in self.svc.listar(ctx, filtros or {}, 1, 100)["itens"])

    # ------------------------------------------------------------- escopo

    def test_escopo_da_lista_por_perfil(self):
        desenv = self._inserir(ambiente="DESENV")
        por_amb = dict((t["id"], t["ambiente"]) for t in self.tickets.listar(pagina=1, tamanho=1000)["itens"])
        self.assertEqual(self._ids(self.ctx["admin"]), set(por_amb))
        consulta = self._ids(self.ctx["consulta"])
        self.assertNotIn(desenv, consulta)
        self.assertEqual(consulta, set(i for i, a in por_amb.items() if a in ("PRODUCAO", "HOMOLOGACAO")))
        op_hml = self._ids(self.ctx["op.hml"])
        self.assertIn(desenv, op_hml)
        self.assertEqual(op_hml, set(i for i, a in por_amb.items() if a in ("HOMOLOGACAO", "DESENV")))

    def test_sem_ver_logs_lista_apenas_proprios(self):
        ctx = self._sem("op.hml", "VER_LOGS")
        itens = self.svc.listar(ctx, {}, 1, 100)["itens"]
        self.assertTrue(itens)
        self.assertEqual(set(t["solicitante"] for t in itens), {"op.hml"})
        self.assertEqual(self.svc.listar(ctx, {"solicitante": "admin"}, 1, 100)["total"], 0)
        sem_nada = self._sem("consulta", "VER_LOGS")
        with self.assertRaises(AcessoNegado):
            self.svc.listar(sem_nada, {}, 1, 20)

    def test_detalhe_fora_do_escopo_e_inexistente(self):
        desenv = self._inserir(ambiente="DESENV")
        for login, tid in (("consulta", desenv), ("op.hml", 1), ("admin", 99999)):
            with self.assertRaises(RepoNaoEncontrado):
                self.svc.detalhe(self.ctx[login], str(tid))
        for invalido in ("abc", "-1", "0", None, "1; DROP"):
            with self.assertRaises(RepoNaoEncontrado):
                self.svc.detalhe(self.ctx["admin"], invalido)
        self.assertEqual(self.svc.detalhe(self.ctx["op.hml"], str(desenv))["id"], desenv)

    # ------------------------------------------------------------- filtros

    def test_normalizar_filtros_allowlist(self):
        limpos = ticket_service.normalizar_filtros({
            "status": ["RUNNING", "X", "PENDING", "RUNNING"], "ambiente": "producao", "script": "07",
            "solicitante": " OP.Hml ", "criado_de": "2026-02-30", "criado_ate": "2026-10-14",
            "origem": "agendamento", "ordem": "id; DROP TABLE", "created_at": "x"})
        self.assertEqual(list(limpos.items()), [
            ("status", ["PENDING", "RUNNING"]), ("script", 7), ("solicitante", "op.hml"),
            ("criado_ate", "2026-10-14"), ("origem", "agendamento")])
        self.assertEqual(ticket_service.normalizar_filtros({"status": "SUCCESS", "origem": "outro",
                                                            "script": "0", "solicitante": "a"}),
                         {"status": ["SUCCESS"]})

    def test_filtro_de_periodo_nos_limites(self):
        dia = datetime.datetime(2025, 3, 10)
        um_seg = datetime.timedelta(seconds=1)
        antes = self._inserir(ambiente="DESENV", created_at=dia - um_seg)
        inicio = self._inserir(ambiente="DESENV", created_at=dia)
        fim = self._inserir(ambiente="DESENV", created_at=dia + datetime.timedelta(days=1) - um_seg)
        depois = self._inserir(ambiente="DESENV", created_at=dia + datetime.timedelta(days=1))
        admin = self.ctx["admin"]
        base = {"ambiente": "DESENV"}
        self.assertEqual(self._ids(admin, dict(base, criado_de="2025-03-10", criado_ate="2025-03-10")),
                         {inicio, fim})
        self.assertEqual(self._ids(admin, dict(base, criado_de="2025-03-10")), {inicio, fim, depois})
        self.assertEqual(self._ids(admin, dict(base, criado_ate="2025-03-09")), {antes})
        self.assertEqual(self._ids(admin, dict(base, criado_de="2025-03-11", criado_ate="2025-03-10")), set())

    def test_filtros_combinados_e_paginacao(self):
        admin = self.ctx["admin"]
        rodando = self._ids(admin, {"status": ["RUNNING"], "ambiente": "PRODUCAO"})
        self.assertTrue(rodando)
        for t in self.svc.listar(admin, {"status": ["RUNNING"], "ambiente": "PRODUCAO"}, 1, 100)["itens"]:
            self.assertEqual((t["status"], t["ambiente"]), ("RUNNING", "PRODUCAO"))
        agend = self.svc.listar(admin, {"origem": "agendamento"}, 1, 100)["itens"]
        self.assertTrue(agend)
        self.assertTrue(all(t["origem"] == "agendamento" for t in agend))
        pagina2 = self.svc.listar(admin, {"status": ["SUCCESS"]}, 2, 5)
        self.assertEqual((pagina2["pagina"], len(pagina2["itens"])), (2, 5))
        alem = self.svc.listar(admin, {"status": ["SUCCESS"]}, 99, 5)
        self.assertEqual(alem["pagina"], (alem["total"] + 4) // 5)
        self.assertTrue(alem["itens"])

    # --------------------------------------------------------- cancelamento

    def test_cancelamento_nos_tres_resultados(self):
        ctx = self.ctx["op.hml"]
        pendente, _ = self._criar()
        self.assertEqual(self.svc.cancelar(ctx, IP, str(pendente)), "CANCELADO")
        t = self.tickets.obter(pendente)
        self.assertEqual((t["status"], t["status_motivo"], t["return_code"]), ("CANCELLED", "CANCEL_USER", -1))
        self.assertEqual(self.svc.cancelar(ctx, IP, str(pendente)), "TERMINAL")

        rodando = self._inserir(status="RUNNING", solicitante="op.hml", agente_id="agt-x")
        self.assertEqual(self.svc.cancelar(ctx, IP, str(rodando)), "SINALIZADO")
        t = self.tickets.obter(rodando)
        self.assertEqual((t["status"], t["cancel_requested"]), ("RUNNING", "S"))
        self.assertFalse(self.svc.detalhe(ctx, str(rodando))["pode_cancelar"])

        # CR-003 P5 (README §5.6): pedido repetido e ticket encerrado tambem sao auditados, com o resultado.
        self.assertEqual(self.svc.cancelar(ctx, IP, str(rodando)), "JA_SINALIZADO")
        regs = self.auditoria.listar(filtros={"acao": "TICKET_CANCELAR", "entidade_id": rodando})["itens"]
        self.assertEqual([(r["ator"], r["ip_origem"], r["detalhe"]) for r in regs],
                         [("op.hml", IP, u"resultado: já sinalizado"), ("op.hml", IP, u"resultado: sinalizado")])
        regs = self.auditoria.listar(filtros={"acao": "TICKET_CANCELAR", "entidade_id": pendente})["itens"]
        self.assertEqual([r["detalhe"] for r in regs],
                         [u"resultado: sem efeito: ticket encerrado", u"resultado: cancelado"])
        self.assertEqual(set(ticket_service.MSG_CANCELAMENTO),
                         {"TERMINAL", "CANCELADO", "SINALIZADO", "JA_SINALIZADO"})

    def test_canc_ticket_sem_ver_logs_cancela_ticket_de_terceiro(self):
        # CR-003 P5 (README §4.3.C): CANC_TICKET nao exige VER_LOGS.
        terceiro = self._inserir(solicitante="admin")
        ctx = self._sem("op.hml", "VER_LOGS")
        self.assertFalse(self.svc.visivel(ctx, str(terceiro)))
        self.assertEqual(self.svc.cancelar(ctx, IP, str(terceiro)), "CANCELADO")

    def test_cancelar_terceiro_sem_canc_ticket_negado(self):
        terceiro = self._inserir(solicitante="admin")
        ctx = self._sem("op.hml", "CANC_TICKET")
        self.assertFalse(self.svc.detalhe(ctx, str(terceiro))["pode_cancelar"])
        with self.assertRaises(AcessoNegado):
            self.svc.cancelar(ctx, IP, str(terceiro))
        self.assertEqual(self.tickets.obter(terceiro)["status"], "PENDING")
        proprio, _ = self._criar()
        self.assertEqual(self.svc.cancelar(ctx, IP, str(proprio)), "CANCELADO")
        self.assertEqual(self.svc.cancelar(self.ctx["op.hml"], IP, str(terceiro)), "CANCELADO")
        with self.assertRaises(RepoNaoEncontrado):
            self.svc.cancelar(self.ctx["op.hml"], IP, "1")

    # ---------------------------------------------------------- reexecucao

    def test_reexecucao_ok_com_parent_ticket_id(self):
        ctx = self.ctx["op.hml"]
        original, _ = self._criar(respostas={"data_ref": "2026-10-20", "documento_cliente": SEGREDO}, prioridade="3")
        with self.assertRaises(AcessoNegado):
            self.svc.reexecutar(ctx, IP, str(original))
        self.assertFalse(self.svc.detalhe(ctx, str(original))["pode_reexecutar"])
        self.svc.cancelar(ctx, IP, str(original))
        self.assertTrue(self.svc.detalhe(ctx, str(original))["pode_reexecutar"])

        novo = self.svc.reexecutar(ctx, IP, str(original))
        t_orig, t_novo = self.tickets.obter(original), self.tickets.obter(novo)
        self.assertEqual(t_novo["parent_ticket_id"], original)
        self.assertEqual((t_novo["status"], t_novo["prioridade"], t_novo["solicitante"]), ("PENDING", 3, "op.hml"))
        snap_orig, snap_novo = json.loads(t_orig["parametros_enviados"]), json.loads(t_novo["parametros_enviados"])
        self.assertEqual(snap_novo["args"], snap_orig["args"])
        self.assertEqual(snap_novo["respostas"], snap_orig["respostas"])
        regs = self.auditoria.listar(filtros={"acao": "TICKET_REEXECUTAR", "entidade_id": novo})["itens"]
        self.assertEqual(len(regs), 1)
        self.assertNotIn(SEGREDO, regs[0]["detalhe"] or "")

        self.assertEqual([f["id"] for f in self.svc.detalhe(ctx, str(original))["filhos"]], [novo])
        self.assertEqual(self.svc.detalhe(ctx, str(novo))["pai"]["id"], original)

    def test_reexecucao_de_terceiro_por_nao_admin_negada(self):
        terceiro = self._inserir(solicitante="admin", status="SUCCESS")
        with self.assertRaises(AcessoNegado):
            self.svc.reexecutar(self.ctx["op.hml"], IP, str(terceiro))
        self.assertFalse(self.svc.detalhe(self.ctx["op.hml"], str(terceiro))["pode_reexecutar"])
        with self.assertRaises(RepoNaoEncontrado):
            self.svc.reexecutar(self.ctx["consulta"], IP, str(self._inserir(ambiente="DESENV", status="FAILED")))

    def test_reexecucao_com_catalogo_alterado_gera_erro_tratado(self):
        ctx = self.ctx["op.hml"]
        original, _ = self._criar(respostas={"documento_cliente": SEGREDO})
        self.svc.cancelar(ctx, IP, str(original))
        vinculos = [{"parametro_id": v["parametro_id"], "ordem": v["ordem"], "obrigatorio": v["obrigatorio"],
                     "valor_padrao_sub": v["valor_padrao_sub"]} for v in self.catalogo.script_params_obter(1)]
        vinculos.append({"parametro_id": 10, "ordem": 6, "obrigatorio": "S", "valor_padrao_sub": None})
        self.catalogo.script_params_salvar(1, vinculos, ator="teste")
        antes = self._total_tickets()
        with self.assertRaises(ErroReexecucao) as cm:
            self.svc.reexecutar(ctx, IP, str(original))
        self.assertEqual(cm.exception.ticket_id, original)
        self.assertEqual(list(cm.exception.erros), ["descricao_lote"])
        self.assertEqual(self._total_tickets(), antes)

        prep = self.svc.preparar_reexecucao(ctx, str(original))
        self.assertEqual((prep["ticket_id"], prep["script_id"], prep["ambiente"]), (original, 1, "HOMOLOGACAO"))
        self.assertIn("descricao_lote", prep["erros"])
        self.assertNotIn("documento_cliente", prep["valores"])
        self.assertEqual(prep["valores"]["data_ref"], "2026-10-14")

        novo, erros = self.svc.criar_ticket(ctx, IP, "1", "HOMOLOGACAO", dict(prep["valores"], descricao_lote="x"),
                                            prep["prioridade"], "", reexecucao_de=str(original))
        self.assertEqual(erros, {})
        self.assertEqual(self.tickets.obter(novo)["parent_ticket_id"], original)
        with self.assertRaises(AcessoNegado):
            self.svc.criar_ticket(ctx, IP, "2", "HOMOLOGACAO", {}, "2", "", reexecucao_de=str(original))

    # ------------------------------------------------------------ sensiveis

    def test_sensiveis_mascarados_no_detalhe(self):
        tid, _ = self._criar(respostas={"documento_cliente": SEGREDO})
        for login in ("op.hml", "admin", "consulta"):
            if login == "consulta":
                det = self.svc.detalhe(self.ctx[login], "1")
            else:
                det = self.svc.detalhe(self.ctx[login], str(tid))
                respostas = dict((r["codigo"], r) for r in det["respostas"])
                self.assertEqual(respostas["documento_cliente"]["valor"], params_compiler.MASCARA)
                self.assertTrue(respostas["documento_cliente"]["sensivel"])
                self.assertEqual(respostas["data_ref"]["valor"], "2026-10-14")
                self.assertIn(params_compiler.MASCARA, det["argv_para_exibicao"])
            serial = json.dumps(det, default=str)
            self.assertNotIn(SEGREDO, serial)
            self.assertNotIn("00011122233", serial)

    def test_detalhe_campos_e_descricao_motivo(self):
        det = self.svc.detalhe(self.ctx["admin"], "30")
        self.assertEqual((det["status"], det["status_motivo"], det["return_code"]), ("FAILED", "TIMEOUT", -3))
        self.assertEqual(det["descricao_motivo"], ui_helpers.descricao_motivo("TIMEOUT"))
        self.assertNotEqual(det["duracao"], "-")
        self.assertEqual(self.svc.detalhe(self.ctx["admin"], "25")["pai"]["id"], 17)
        self.assertEqual([f["id"] for f in self.svc.detalhe(self.ctx["admin"], "17")["filhos"]], [25])

    def test_caminho_completo_para_quem_nao_e_admin(self):
        """CR-005 D8: quem nao e admin ve o caminho completo no detalhe, no comando e na previa."""
        tid, erros = self._criar(login="op.hml", respostas={"data_ref": "2026-10-20", "modo_exec": "SIMULACAO"})
        self.assertEqual(erros, {})
        caminho = os.path.join(self.base, "carga_diaria.py")
        det = self.svc.detalhe(self.ctx["op.hml"], str(tid))
        self.assertEqual(det["snapshot"]["path_file"], caminho)
        self.assertEqual(det["argv_para_exibicao"][2], caminho)
        self.assertIn(caminho, det["comando_exibicao"])
        argv, erros = self.svc.previa(self.ctx["op.hml"], "1", "HOMOLOGACAO",
                                      {"data_ref": "2026-10-20", "modo_exec": "SIMULACAO"})
        self.assertEqual(erros, {})
        self.assertEqual(argv[2], caminho)


if __name__ == "__main__":
    unittest.main()
