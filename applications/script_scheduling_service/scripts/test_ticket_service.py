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
from repo_errors import RepoNotFound
from ticket_service import AcessoNegado, ErroReexecucao, ServicoTicket

# UID fictício do agente: o dono dos arquivos de teste é o usuário do teste (CR-007, R-15).
AGENTE_FALSO = 2 ** 31 - 3

IP = "10.1.2.3"
SEGREDO = "tok-ultra-secreto-42"
SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0},
    "op.hml": {"usuario_id": 3, "login": "op.hml", "perfil_id": 3, "perm_versao": 1, "sessao_epoch": 0},
    "consulta": {"usuario_id": 4, "login": "consulta", "perfil_id": 4, "perm_versao": 1, "sessao_epoch": 0},
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
        patcher = mock.patch.object(security, "ITERATIONS", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_DEV_PASSWORD: "senha-dev-de-teste-123"})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configure, None)

        self.catalog = repo_factory.get("catalog")
        self.tickets = repo_factory.get("tickets")
        self.audit = repo_factory.get("audit")
        self.log = logging.getLogger("sss_teste_ticket")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        auth = auth_service.ServicoAuth(
            repo_factory.get("users"), repo_factory.get("rbac"), self.catalog, self.audit,
            5, 900, self.log)
        self.ctx = dict((login, auth.revalidar(sessao)) for login, sessao in SESSOES.items())

        self.base = _criar_arvore()
        self.addCleanup(_remover_arvore, self.base)
        for sid, nome in enumerate(ARQUIVOS, 1):
            self.catalog.scripts_update(sid, {"path_file": os.path.join(self.base, nome)}, ator="teste")
        self.svc = ServicoTicket(self.catalog, self.tickets, self.log)

    def _total_tickets(self):
        return self.tickets.list(pagina=1, tamanho=100)["total"]

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

        ticket = self.tickets.get(tid)
        self.assertEqual(ticket["status"], "PENDING")
        self.assertEqual(ticket["script_id"], 1)
        self.assertEqual(ticket["environment"], "HOMOLOGACAO")
        self.assertEqual(ticket["requested_by"], "op.hml")
        self.assertEqual(ticket["source_ip"], IP)
        self.assertEqual(ticket["priority"], 2)

        bruto = ticket["submitted_params"]
        snap = json.loads(bruto)
        self.assertEqual(bruto, json.dumps(snap, ensure_ascii=False, sort_keys=True))
        self.assertEqual(sorted(snap), sorted(params_compiler._SNAPSHOT_KEYS))
        self.assertEqual(snap["version"], 4)
        self.assertEqual(snap["script_nome"], "carga_diaria")
        caminho_esperado = os.path.join(self.base, "carga_diaria.py")
        self.assertEqual((snap["interpreter"], snap["path_file"]),
                         ("PYTHON3", caminho_esperado))
        self.assertEqual(snap["param_type"], "NAMED")
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
        valores = dict((r["parameter_id"], r["answer_value"]) for r in self.tickets.answers(tid))
        # limite_linhas, modo_exec e verbose vieram dos padroes (precedencia §6.1).
        self.assertEqual(valores, {PRM_DATA_REF: "2026-10-20", PRM_LIMITE: "5000", PRM_MODO: "REAL",
                                   PRM_VERBOSE: "true", PRM_CHAVE_API: SEGREDO})

    def test_auditoria_gravada_sem_valor_sensivel(self):
        tid, _ = self._criar(respostas={"documento_cliente": SEGREDO})
        regs = self.audit.list(filtros={"action": "TICKET_CREATE", "entity_id": tid})["itens"]
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0]["actor"], "op.hml")
        self.assertEqual(regs[0]["source_ip"], IP)
        self.assertEqual(regs[0]["entity"], "tbsss_tickets")
        self.assertNotIn(SEGREDO, regs[0]["detail"] or "")

    def test_scheduled_at_futuro_e_admin_prioridade_1(self):
        futuro = (self.tickets.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        tid, erros = self._criar(login="admin", script_id="6", ambiente="PRODUCAO", prioridade="1",
                                 scheduled_at=futuro)
        self.assertEqual(erros, {})
        ticket = self.tickets.get(tid)
        self.assertEqual(ticket["priority"], 1)
        self.assertEqual(ticket["scheduled_at"], datetime.datetime.strptime(futuro, "%Y-%m-%dT%H:%M"))

    def test_checkbox_desmarcado_vence_padrao_verdadeiro(self):
        # hidden "false" + checkbox ausente: vale "false" e a flag e omitida.
        tid, _ = self._criar(respostas={"verbose": ["false"]})
        snap = json.loads(self.tickets.get(tid)["submitted_params"])
        self.assertNotIn("--verbose", snap["args"])
        tid2, _ = self._criar(respostas={"verbose": ["false", "true"]})
        self.assertIn("--verbose", json.loads(self.tickets.get(tid2)["submitted_params"])["args"])

    # ---------------------------------------------------------- autorizacao

    def test_sem_exec_script(self):
        antes = self._total_tickets()
        with self.assertRaises(AcessoNegado) as cm:
            self._criar(login="consulta", script_id="1", ambiente="PRODUCAO")
        self.assertEqual(cm.exception.motivo, "NO_FEATURE")
        self.assertEqual(self.svc.scripts_disponiveis(self.ctx["consulta"]), [])
        self.assertEqual(self._total_tickets(), antes)

    def test_script_nao_homologado_no_ambiente(self):
        # sync_tabelas (4) so e homologado em HOMOLOGACAO; admin nao dispensa a homologacao.
        with self.assertRaises(AcessoNegado) as cm:
            self._criar(login="admin", script_id="4", ambiente="PRODUCAO")
        self.assertEqual(cm.exception.motivo, "NOT_HOMOLOGATED")
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
        self.assertEqual([a["name"] for a in ambientes], ["HOMOLOGACAO"])

    # ------------------------------------------------------------ validacao

    def test_obrigatorio_faltando(self):
        vinculos = [{"parameter_id": v["parameter_id"], "sort_order": v["sort_order"], "required": v["required"],
                     "default_value_override": None if v["code"] == "data_ref" else v["default_value_override"]}
                    for v in self.catalog.script_params_get(1)]
        self.catalog.script_params_save(1, vinculos, ator="teste")
        antes = self._total_tickets()
        tid, erros = self._criar(respostas={"data_ref": "   "})
        self.assertIsNone(tid)
        self.assertIn("data_ref", erros)
        self.assertEqual(self._total_tickets(), antes)

    def test_regex_invalida_e_todos_os_erros_de_uma_vez(self):
        antes = self._total_tickets()
        passado = (self.tickets.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        tid, erros = self._criar(login="admin", script_id="6", ambiente="PRODUCAO",
                                 respostas={"codigo_filial": "ABC", "taxa_ajuste": "x"},
                                 prioridade="9", scheduled_at=passado)
        self.assertIsNone(tid)
        self.assertEqual(sorted(erros), ["codigo_filial", "priority", "scheduled_at", "taxa_ajuste"])
        self.assertEqual(self._total_tickets(), antes)

    def test_prioridade_1_por_nao_admin(self):
        tid, erros = self._criar(prioridade="1")
        self.assertIsNone(tid)
        self.assertEqual(list(erros), ["priority"])
        self.assertNotIn(1, [p for p, _ in self.svc.preparar_formulario(
            self.ctx["op.hml"], "1", "HOMOLOGACAO")["prioridades"]])

    def test_scheduled_at_no_passado(self):
        passado = (self.tickets.now() - datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
        tid, erros = self._criar(scheduled_at=passado)
        self.assertIsNone(tid)
        self.assertEqual(list(erros), ["scheduled_at"])
        tid, erros = self._criar(scheduled_at="31/12/2099")
        self.assertEqual(list(erros), ["scheduled_at"])

    def test_scheduled_at_exato_sem_tolerancia_de_minuto(self):
        # CR-003 P5 (README §5.4): o minuto corrente, ja passado, e recusado.
        repo_factory._fake_store.set_clock(lambda: datetime.datetime(2026, 10, 16, 10, 5, 30))
        tid, erros = self._criar(scheduled_at="2026-10-16T10:05")
        self.assertIsNone(tid)
        self.assertIn(u"deixe em branco para rodar agora", erros["scheduled_at"])
        tid, erros = self._criar(scheduled_at="2026-10-16T10:06")
        self.assertEqual(erros, {})

    def test_scheduled_at_limite_366_dias(self):
        # CR-007 D2 (README §5.4): scheduled_at no maximo 366 dias no futuro.
        agora = self.tickets.now()
        mais_366 = (agora + datetime.timedelta(days=366)).strftime("%Y-%m-%dT%H:%M")
        tid, erros = self._criar(scheduled_at=mais_366)
        self.assertEqual(erros, {})
        mais_367 = (agora + datetime.timedelta(days=367)).strftime("%Y-%m-%dT%H:%M")
        tid, erros = self._criar(scheduled_at=mais_367)
        self.assertIsNone(tid)
        self.assertIn(u"Escolha uma data até", erros.get("scheduled_at", ""))

    def test_caminho_em_pasta_do_sistema_rejeita_o_disparo(self):
        # CR-011 (S1): o web confere so o formato e as pastas do sistema; o arquivo e conferido pelo agente.
        self.catalog.scripts_update(1, {"path_file": "/etc/carga.py"}, ator="teste")
        tid, erros = self._criar()
        self.assertIsNone(tid)
        self.assertEqual(erros, {ticket_service.CAMPO_GERAL: ticket_service.MSG_SCRIPT_INDISPONIVEL})

    # ----------------------------------------------------- previa e formulario

    def test_previa_mascara_sensivel(self):
        argv, erros = self.svc.previa(self.ctx["op.hml"], "1", "HOMOLOGACAO", {"documento_cliente": SEGREDO})
        self.assertEqual(erros, {})
        self.assertNotIn(SEGREDO, " ".join(argv))
        self.assertEqual(argv[argv.index("--documento") + 1], params_compiler.MASK)
        argv, erros = self.svc.previa(self.ctx["op.hml"], "1", "HOMOLOGACAO", {"modo_exec": "X"})
        self.assertIsNone(argv)
        self.assertIn("modo_exec", erros)

    def test_formulario_nao_expoe_sensivel(self):
        form = self.svc.preparar_formulario(self.ctx["op.hml"], "1", "HOMOLOGACAO",
                                            valores={"documento_cliente": SEGREDO, "data_ref": "2026-01-01"})
        campos = dict((c["code"], c) for c in form["campos"])
        self.assertEqual([c["code"] for c in form["campos"]],
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
        self.assertEqual((resumo["script"], resumo["environment"], resumo["quando"], resumo["priority"]),
                         ("carga_diaria", "HOMOLOGACAO", u"agora", 3))
        self.assertTrue(resumo["frase"].startswith(u"Vamos rodar carga_diaria no ambiente HOMOLOGACAO agora, "
                                                   u"com prioridade 3."))
        valores = dict((x["rotulo"], x["valor"]) for x in resumo["respostas"])
        self.assertNotIn("12345678900", resumo["frase"])
        self.assertIn(params_compiler.MASK, valores.values())
        self.assertTrue(r["argv"])

    def test_resumo_com_horario_e_erros(self):
        futuro = (self.tickets.now() + datetime.timedelta(days=1)).replace(second=0)
        r = self.svc.resumo_disparo(self.ctx["op.hml"], "1", "HOMOLOGACAO", {}, "2", futuro.strftime("%Y-%m-%dT%H:%M"))
        self.assertEqual(r["resumo"]["quando"], u"em %s às %s" % (futuro.strftime("%d/%m/%Y"), futuro.strftime("%H:%M")))
        r = self.svc.resumo_disparo(self.ctx["op.hml"], "1", "HOMOLOGACAO", {"data_ref": "31/12/2026"}, "2", "")
        self.assertIsNone(r["resumo"])
        self.assertIn("data_ref", r["erros"])

    def test_exemplo_por_tipo_no_formulario(self):
        form = self.svc.preparar_formulario(self.ctx["op.hml"], "1", "HOMOLOGACAO")
        exemplos = dict((c["code"], c["exemplo"]) for c in form["campos"])
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
        self.catalog.parameters_update(3, {"options_json": '{"REAL":"Execucao Real"}', "default_value": "REAL"}, ator="teste")
        valores, avisos = self.svc.ultimas_respostas(ctx, "1", "HOMOLOGACAO")
        self.assertNotIn("modo_exec", valores)
        self.assertEqual(avisos["modo_exec"], ticket_service.MSG_ULTIMA_MUDOU)


@_SKIP_ROOT
class TestTicketConsulta(_BaseTicket):
    """F3.3: escopo da lista, filtros, detalhe, cancelamento e reexecucao."""

    def _sem(self, login, *funcs):
        ctx = dict(self.ctx[login])
        ctx["features"] = frozenset(ctx["features"] - set(funcs))
        return ctx

    def _inserir(self, **campos):
        ticket = {"script_id": 1, "environment": "HOMOLOGACAO", "requested_by": "admin", "status": "PENDING",
                  "priority": 2, "submitted_params": "{}"}
        ticket.update(campos)
        return self.tickets.create(ticket, [])

    def _ids(self, ctx, filtros=None):
        return set(t["id"] for t in self.svc.list(ctx, filtros or {}, 1, 100)["itens"])

    # ------------------------------------------------------------- escopo

    def test_escopo_da_lista_por_perfil(self):
        desenv = self._inserir(environment="DESENV")
        por_amb = dict((t["id"], t["environment"]) for t in self.tickets.list(pagina=1, tamanho=1000)["itens"])
        self.assertEqual(self._ids(self.ctx["admin"]), set(por_amb))
        consulta = self._ids(self.ctx["consulta"])
        self.assertNotIn(desenv, consulta)
        self.assertEqual(consulta, set(i for i, a in por_amb.items() if a in ("PRODUCAO", "HOMOLOGACAO")))
        op_hml = self._ids(self.ctx["op.hml"])
        self.assertIn(desenv, op_hml)
        self.assertEqual(op_hml, set(i for i, a in por_amb.items() if a in ("HOMOLOGACAO", "DESENV")))

    def test_sem_ver_logs_lista_apenas_proprios(self):
        ctx = self._sem("op.hml", "VIEW_LOGS")
        itens = self.svc.list(ctx, {}, 1, 100)["itens"]
        self.assertTrue(itens)
        # Sem VIEW_AUDIT o proprio login aparece como "você" (CR-008, E5).
        self.assertEqual(set(t["requested_by"] for t in itens), {u"você"})
        self.assertEqual(self.svc.list(ctx, {"requested_by": "admin"}, 1, 100)["total"], 0)

    def test_solicitante_mascarado_sem_auditoria(self):
        # CR-008, E5: consulta sem VIEW_AUDIT nao recebe login de terceiros; admin recebe.
        ctx = self._sem("consulta", "VIEW_AUDIT")
        itens = self.svc.list(ctx, {}, 1, 100)["itens"]
        self.assertTrue(itens)
        self.assertEqual(set(t["requested_by"] for t in itens), {u"outra pessoa"})
        self.assertEqual(self.svc.detalhe(ctx, 17)["requested_by"], u"outra pessoa")
        self.assertEqual(self.svc.detalhe(self.ctx["admin"], 17)["requested_by"], "op.prod")
        sem_nada = self._sem("consulta", "VIEW_LOGS")
        with self.assertRaises(AcessoNegado):
            self.svc.list(sem_nada, {}, 1, 20)

    def test_detalhe_fora_do_escopo_e_inexistente(self):
        desenv = self._inserir(environment="DESENV")
        for login, tid in (("consulta", desenv), ("op.hml", 1), ("admin", 99999)):
            with self.assertRaises(RepoNotFound):
                self.svc.detalhe(self.ctx[login], str(tid))
        for invalido in ("abc", "-1", "0", None, "1; DROP"):
            with self.assertRaises(RepoNotFound):
                self.svc.detalhe(self.ctx["admin"], invalido)
        self.assertEqual(self.svc.detalhe(self.ctx["op.hml"], str(desenv))["id"], desenv)

    # ------------------------------------------------------------- filtros

    def test_normalizar_filtros_allowlist(self):
        limpos = ticket_service.normalizar_filtros({
            "status": ["RUNNING", "X", "PENDING", "RUNNING"], "environment": "producao", "script": "07",
            "requested_by": " OP.Hml ", "criado_de": "2026-02-30", "criado_ate": "2026-10-14",
            "origem": "agendamento", "sort_order": "id; DROP TABLE", "created_at": "x"})
        self.assertEqual(list(limpos.items()), [
            ("status", ["PENDING", "RUNNING"]), ("script", 7), ("requested_by", "op.hml"),
            ("criado_ate", "2026-10-14"), ("origem", "agendamento")])
        self.assertEqual(ticket_service.normalizar_filtros({"status": "SUCCESS", "origem": "outro",
                                                            "script": "0", "requested_by": "a"}),
                         {"status": ["SUCCESS"]})

    def test_filtro_de_periodo_nos_limites(self):
        dia = datetime.datetime(2025, 3, 10)
        um_seg = datetime.timedelta(seconds=1)
        antes = self._inserir(environment="DESENV", created_at=dia - um_seg)
        inicio = self._inserir(environment="DESENV", created_at=dia)
        fim = self._inserir(environment="DESENV", created_at=dia + datetime.timedelta(days=1) - um_seg)
        depois = self._inserir(environment="DESENV", created_at=dia + datetime.timedelta(days=1))
        admin = self.ctx["admin"]
        base = {"environment": "DESENV"}
        self.assertEqual(self._ids(admin, dict(base, criado_de="2025-03-10", criado_ate="2025-03-10")),
                         {inicio, fim})
        self.assertEqual(self._ids(admin, dict(base, criado_de="2025-03-10")), {inicio, fim, depois})
        self.assertEqual(self._ids(admin, dict(base, criado_ate="2025-03-09")), {antes})
        self.assertEqual(self._ids(admin, dict(base, criado_de="2025-03-11", criado_ate="2025-03-10")), set())

    def test_filtros_combinados_e_paginacao(self):
        admin = self.ctx["admin"]
        rodando = self._ids(admin, {"status": ["RUNNING"], "environment": "PRODUCAO"})
        self.assertTrue(rodando)
        for t in self.svc.list(admin, {"status": ["RUNNING"], "environment": "PRODUCAO"}, 1, 100)["itens"]:
            self.assertEqual((t["status"], t["environment"]), ("RUNNING", "PRODUCAO"))
        agend = self.svc.list(admin, {"origem": "agendamento"}, 1, 100)["itens"]
        self.assertTrue(agend)
        self.assertTrue(all(t["origem"] == "agendamento" for t in agend))
        pagina2 = self.svc.list(admin, {"status": ["SUCCESS"]}, 2, 5)
        self.assertEqual((pagina2["pagina"], len(pagina2["itens"])), (2, 5))
        alem = self.svc.list(admin, {"status": ["SUCCESS"]}, 99, 5)
        self.assertEqual(alem["pagina"], (alem["total"] + 4) // 5)
        self.assertTrue(alem["itens"])

    # --------------------------------------------------------- cancelamento

    def test_cancelamento_nos_tres_resultados(self):
        ctx = self.ctx["op.hml"]
        pendente, _ = self._criar()
        self.assertEqual(self.svc.cancelar(ctx, IP, str(pendente)), "CANCELADO")
        t = self.tickets.get(pendente)
        self.assertEqual((t["status"], t["status_reason"], t["return_code"]), ("CANCELLED", "CANCEL_USER", -1))
        self.assertEqual(self.svc.cancelar(ctx, IP, str(pendente)), "TERMINAL")

        rodando = self._inserir(status="RUNNING", requested_by="op.hml", agent_id="agt-x")
        self.assertEqual(self.svc.cancelar(ctx, IP, str(rodando)), "SINALIZADO")
        t = self.tickets.get(rodando)
        self.assertEqual((t["status"], t["cancel_requested"]), ("RUNNING", "Y"))
        self.assertFalse(self.svc.detalhe(ctx, str(rodando))["pode_cancelar"])

        # CR-003 P5 (README §5.6): pedido repetido e ticket encerrado tambem sao auditados, com o resultado.
        self.assertEqual(self.svc.cancelar(ctx, IP, str(rodando)), "JA_SINALIZADO")
        regs = self.audit.list(filtros={"action": "TICKET_CANCEL", "entity_id": rodando})["itens"]
        self.assertEqual([(r["actor"], r["source_ip"], r["detail"]) for r in regs],
                         [("op.hml", IP, u"resultado: já sinalizado"), ("op.hml", IP, u"resultado: sinalizado")])
        regs = self.audit.list(filtros={"action": "TICKET_CANCEL", "entity_id": pendente})["itens"]
        self.assertEqual([r["detail"] for r in regs],
                         [u"resultado: sem efeito: ticket encerrado", u"resultado: cancelado"])
        self.assertEqual(set(ticket_service.MSG_CANCELAMENTO),
                         {"TERMINAL", "CANCELADO", "SINALIZADO", "JA_SINALIZADO"})

    def test_canc_ticket_sem_ver_logs_cancela_ticket_de_terceiro(self):
        # CR-003 P5 (README §4.3.C): CANCEL_TICKET nao exige VIEW_LOGS.
        terceiro = self._inserir(requested_by="admin")
        ctx = self._sem("op.hml", "VIEW_LOGS")
        self.assertFalse(self.svc.visivel(ctx, str(terceiro)))
        self.assertEqual(self.svc.cancelar(ctx, IP, str(terceiro)), "CANCELADO")

    def test_cancelar_terceiro_sem_canc_ticket_negado(self):
        terceiro = self._inserir(requested_by="admin")
        ctx = self._sem("op.hml", "CANCEL_TICKET")
        self.assertFalse(self.svc.detalhe(ctx, str(terceiro))["pode_cancelar"])
        with self.assertRaises(AcessoNegado):
            self.svc.cancelar(ctx, IP, str(terceiro))
        self.assertEqual(self.tickets.get(terceiro)["status"], "PENDING")
        proprio, _ = self._criar()
        self.assertEqual(self.svc.cancelar(ctx, IP, str(proprio)), "CANCELADO")
        self.assertEqual(self.svc.cancelar(self.ctx["op.hml"], IP, str(terceiro)), "CANCELADO")
        with self.assertRaises(RepoNotFound):
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
        t_orig, t_novo = self.tickets.get(original), self.tickets.get(novo)
        self.assertEqual(t_novo["parent_ticket_id"], original)
        self.assertEqual((t_novo["status"], t_novo["priority"], t_novo["requested_by"]), ("PENDING", 3, "op.hml"))
        snap_orig, snap_novo = json.loads(t_orig["submitted_params"]), json.loads(t_novo["submitted_params"])
        self.assertEqual(snap_novo["args"], snap_orig["args"])
        self.assertEqual(snap_novo["respostas"], snap_orig["respostas"])
        regs = self.audit.list(filtros={"action": "TICKET_RERUN", "entity_id": novo})["itens"]
        self.assertEqual(len(regs), 1)
        self.assertNotIn(SEGREDO, regs[0]["detail"] or "")

        self.assertEqual([f["id"] for f in self.svc.detalhe(ctx, str(original))["filhos"]], [novo])
        self.assertEqual(self.svc.detalhe(ctx, str(novo))["pai"]["id"], original)

    def test_reexecucao_de_terceiro_por_nao_admin_negada(self):
        terceiro = self._inserir(requested_by="admin", status="SUCCESS")
        with self.assertRaises(AcessoNegado):
            self.svc.reexecutar(self.ctx["op.hml"], IP, str(terceiro))
        self.assertFalse(self.svc.detalhe(self.ctx["op.hml"], str(terceiro))["pode_reexecutar"])
        with self.assertRaises(RepoNotFound):
            self.svc.reexecutar(self.ctx["consulta"], IP, str(self._inserir(environment="DESENV", status="FAILED")))

    def test_reexecucao_com_catalogo_alterado_gera_erro_tratado(self):
        ctx = self.ctx["op.hml"]
        original, _ = self._criar(respostas={"documento_cliente": SEGREDO})
        self.svc.cancelar(ctx, IP, str(original))
        vinculos = [{"parameter_id": v["parameter_id"], "sort_order": v["sort_order"], "required": v["required"],
                     "default_value_override": v["default_value_override"]} for v in self.catalog.script_params_get(1)]
        vinculos.append({"parameter_id": 10, "sort_order": 6, "required": "Y", "default_value_override": None})
        self.catalog.script_params_save(1, vinculos, ator="teste")
        antes = self._total_tickets()
        with self.assertRaises(ErroReexecucao) as cm:
            self.svc.reexecutar(ctx, IP, str(original))
        self.assertEqual(cm.exception.ticket_id, original)
        self.assertEqual(list(cm.exception.erros), ["descricao_lote"])
        self.assertEqual(self._total_tickets(), antes)

        prep = self.svc.preparar_reexecucao(ctx, str(original))
        self.assertEqual((prep["ticket_id"], prep["script_id"], prep["environment"]), (original, 1, "HOMOLOGACAO"))
        self.assertIn("descricao_lote", prep["erros"])
        self.assertNotIn("documento_cliente", prep["valores"])
        self.assertEqual(prep["valores"]["data_ref"], "2026-10-14")

        novo, erros = self.svc.criar_ticket(ctx, IP, "1", "HOMOLOGACAO", dict(prep["valores"], descricao_lote="x"),
                                            prep["priority"], "", reexecucao_de=str(original))
        self.assertEqual(erros, {})
        self.assertEqual(self.tickets.get(novo)["parent_ticket_id"], original)
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
                respostas = dict((r["code"], r) for r in det["respostas"])
                self.assertEqual(respostas["documento_cliente"]["valor"], params_compiler.MASK)
                self.assertTrue(respostas["documento_cliente"]["sensitive"])
                self.assertEqual(respostas["data_ref"]["valor"], "2026-10-14")
                self.assertIn(params_compiler.MASK, det["argv_para_exibicao"])
            serial = json.dumps(det, default=str)
            self.assertNotIn(SEGREDO, serial)
            self.assertNotIn("00011122233", serial)

    def test_detalhe_campos_e_descricao_motivo(self):
        det = self.svc.detalhe(self.ctx["admin"], "30")
        self.assertEqual((det["status"], det["status_reason"], det["return_code"]), ("FAILED", "TIMEOUT", -3))
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


class TestSaidaDoTicket(_BaseTicket):
    """CR-012 (README §8.13): quadro Saida e download do zip, com a regra de leitura do log."""

    def test_quadro_por_situacao(self):
        disponivel = self.svc.detalhe(self.ctx["admin"], 17)["saida"]
        self.assertEqual((disponivel["state"], disponivel["classe"], disponivel["pode_baixar"]),
                         ("AVAILABLE", "success", True))
        self.assertIn(u"2 arquivos", disponivel["aconteceu"])
        excedeu = self.svc.detalhe(self.ctx["admin"], 29)["saida"]
        self.assertFalse(excedeu["pode_baixar"])
        self.assertIn(u"quantidade de arquivos", excedeu["aconteceu"])
        self.assertIn(u"agente agt-host02", excedeu["fazer"])
        falhou = self.svc.detalhe(self.ctx["admin"], 30)["saida"]
        self.assertEqual((falhou["state"], falhou["pode_baixar"]), ("FAILED", False))
        self.assertIn(u"agente agt-host01", falhou["fazer"])
        self.assertIsNone(self.svc.detalhe(self.ctx["admin"], 18)["saida"], "sem saida, sem quadro")
        for campo in ("content", "base", "relativo"):
            self.assertNotIn(campo, disponivel)

    def test_gravando_ha_mais_de_uma_hora_e_tamanho_legivel(self):
        agora = datetime.datetime(2026, 10, 20, 12, 0, 0)
        recente = ui_helpers.quadro_saida({"state": "WRITING", "agent_id": "a1",
                                           "created_at": agora - datetime.timedelta(minutes=5)}, agora)
        self.assertEqual((recente["classe"], recente["pode_baixar"]), ("info", False))
        self.assertIn(u"em preparação", recente["aconteceu"])
        parada = ui_helpers.quadro_saida({"state": "WRITING", "agent_id": "a1",
                                          "created_at": agora - datetime.timedelta(hours=2)}, agora)
        self.assertIn(u"não foi concluída", parada["aconteceu"])
        self.assertIn(u"agente a1", parada["fazer"])
        bytes_ = ui_helpers.quadro_saida({"state": "EXCEEDED", "reason": "BYTES", "agent_id": "a1"}, agora)
        self.assertIn(u"limite de tamanho", bytes_["aconteceu"])
        self.assertIsNone(ui_helpers.quadro_saida(None, agora))
        self.assertEqual([ui_helpers.tamanho_legivel(n) for n in (None, 512, 12595, 4718592)],
                         [u"-", u"512 bytes", u"12,3 KB", u"4,5 MB"])
        um = ui_helpers.quadro_saida({"state": "AVAILABLE", "file_count": 1, "size_bytes": 10}, agora)
        self.assertIn(u"1 arquivo ", um["aconteceu"])

    def test_download_em_fatias_so_disponivel_e_no_escopo(self):
        import io
        import zipfile
        with mock.patch.object(ticket_service, "SAIDA_FATIA_BYTES", 100):
            tid, tamanho, partes = self.svc.blocos_saida(self.ctx["consulta"], "17")
            dados = b"".join(partes)
        self.assertEqual((tid, len(dados)), (17, tamanho))
        self.assertEqual(sorted(zipfile.ZipFile(io.BytesIO(dados)).namelist()),
                         ["rejeitados/linhas_rejeitadas.csv", "resumo.txt"])
        for login, alvo in (("op.hml", "17"), ("admin", "29"), ("admin", "30"), ("admin", "18"),
                            ("admin", "abc"), ("admin", "99999")):
            with self.assertRaises(RepoNotFound, msg=(login, alvo)):
                self.svc.blocos_saida(self.ctx[login], alvo)

    def test_falha_no_meio_do_download_encerra_sem_completar(self):
        from repo_errors import RepoError
        with mock.patch.object(ticket_service, "SAIDA_FATIA_BYTES", 100):
            _tid, tamanho, partes = self.svc.blocos_saida(self.ctx["admin"], 17)
            primeira = next(partes)
            with mock.patch.object(self.tickets, "output_read", side_effect=RepoError("ORA-03113")):
                resto = b"".join(partes)
        self.assertLess(len(primeira) + len(resto), tamanho)
