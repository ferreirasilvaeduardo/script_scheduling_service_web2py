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
from ticket_service import AccessDenied, RerunError, TicketService

# UID fictício do agente: o dono dos arquivos de teste é o usuário do teste (CR-007, R-15).
FAKE_AGENT = 2 ** 31 - 3

IP = "10.1.2.3"
SECRET = "tok-ultra-secreto-42"
SESSIONS = {
    "admin": {"user_id": 1, "login": "admin", "profile_id": 1, "perm_version": 1, "session_epoch": 0},
    "op.hml": {"user_id": 3, "login": "op.hml", "profile_id": 3, "perm_version": 1, "session_epoch": 0},
    "consulta": {"user_id": 4, "login": "consulta", "profile_id": 4, "perm_version": 1, "session_epoch": 0},
}
FILES = ("carga_diaria.py", "relatorio_mensal.py", "cleanup_tmp.sh", "sync_tabelas.sh",
            "validacao_fiscal.py")

# Parametros do seed FAKE (repo_fake/seed.py).
PRM_DATA_REF, PRM_LIMITE, PRM_MODO, PRM_VERBOSE, PRM_CHAVE_API = 1, 2, 3, 4, 6


def _create_tree():
    base = tempfile.mkdtemp(prefix="sss_tck_")
    for name in FILES:
        path = os.path.join(base, name)
        with open(path, "w") as f:
            f.write("# teste\n")
        os.chmod(path, 0o444)
    os.chmod(base, 0o555)
    return os.path.realpath(base)


def _remove_tree(base):
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
        auth = auth_service.AuthService(
            repo_factory.get("users"), repo_factory.get("rbac"), self.catalog, self.audit,
            5, 900, self.log)
        self.ctx = dict((login, auth.revalidate(session)) for login, session in SESSIONS.items())

        self.base = _create_tree()
        self.addCleanup(_remove_tree, self.base)
        for sid, name in enumerate(FILES, 1):
            self.catalog.scripts_update(sid, {"path_file": os.path.join(self.base, name)}, actor="teste")
        self.svc = TicketService(self.catalog, self.tickets, self.log)

    def _ticket_total(self):
        return self.tickets.list(page=1, size=100)["total"]

    def _create(self, login="op.hml", script_id="1", environment="HOMOLOGACAO", answers=None,
               priority="2", scheduled_at=""):
        return self.svc.create_ticket(self.ctx[login], IP, script_id, environment, answers or {},
                                     priority, scheduled_at)


@_SKIP_ROOT
class TestTicketService(_BaseTicket):

    # ------------------------------------------------------------- sucesso

    def test_criacao_ok_com_snapshot_correto(self):
        answers = {"data_ref": "2026-10-20", "modo_exec": "SIMULACAO", "documento_cliente": SECRET}
        tid, errors = self._create(answers=answers)
        self.assertEqual(errors, {})
        self.assertIsNotNone(tid)

        ticket = self.tickets.get(tid)
        self.assertEqual(ticket["status"], "PENDING")
        self.assertEqual(ticket["script_id"], 1)
        self.assertEqual(ticket["environment"], "HOMOLOGACAO")
        self.assertEqual(ticket["requested_by"], "op.hml")
        self.assertEqual(ticket["source_ip"], IP)
        self.assertEqual(ticket["priority"], 2)

        raw = ticket["submitted_params"]
        snap = json.loads(raw)
        self.assertEqual(raw, json.dumps(snap, ensure_ascii=False, sort_keys=True))
        self.assertEqual(sorted(snap), sorted(params_compiler._SNAPSHOT_KEYS))
        self.assertEqual(snap["version"], 5)
        self.assertEqual(snap["script_name"], "carga_diaria")
        path_expected = os.path.join(self.base, "carga_diaria.py")
        self.assertEqual((snap["interpreter"], snap["path_file"]),
                         ("PYTHON3", path_expected))
        self.assertEqual(snap["param_type"], "NAMED")
        # Snapshot v5 (CR-005 D2; chaves em ingles no CR-016c2): path_file e absoluto; sem base_dir.
        self.assertNotIn("pasta_base", snap)
        self.assertIn(self.base, raw)
        self.assertEqual(snap["args"], [
            "--data-ref", "2026-10-20", "-n", "5000", "--modo", "SIMULACAO",
            "--verbose", "--documento", SECRET,
        ])
        self.assertEqual(snap["answers"], {"data_ref": "2026-10-20", "limite_linhas": "5000",
                                             "modo_exec": "SIMULACAO", "verbose": True,
                                             "documento_cliente": SECRET})
        self.assertEqual(snap["sensitive"], ["documento_cliente"])
        datetime.datetime.strptime(snap["compiled_at"], "%Y-%m-%d %H:%M:%S")

    def test_ticket_resp_com_valores_resolvidos(self):
        tid, _ = self._create(answers={"data_ref": "2026-10-20", "documento_cliente": SECRET})
        values = dict((r["parameter_id"], r["answer_value"]) for r in self.tickets.answers(tid))
        # limite_linhas, modo_exec e verbose vieram dos padroes (precedencia §6.1).
        self.assertEqual(values, {PRM_DATA_REF: "2026-10-20", PRM_LIMITE: "5000", PRM_MODO: "REAL",
                                   PRM_VERBOSE: "true", PRM_CHAVE_API: SECRET})

    def test_auditoria_gravada_sem_valor_sensivel(self):
        tid, _ = self._create(answers={"documento_cliente": SECRET})
        regs = self.audit.list(filters={"action": "TICKET_CREATE", "entity_id": tid})["items"]
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0]["actor"], "op.hml")
        self.assertEqual(regs[0]["source_ip"], IP)
        self.assertEqual(regs[0]["entity"], "tbsss_tickets")
        self.assertNotIn(SECRET, regs[0]["detail"] or "")

    def test_scheduled_at_futuro_e_admin_prioridade_1(self):
        future = (self.tickets.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        tid, errors = self._create(login="admin", script_id="6", environment="PRODUCAO", priority="1",
                                 scheduled_at=future)
        self.assertEqual(errors, {})
        ticket = self.tickets.get(tid)
        self.assertEqual(ticket["priority"], 1)
        self.assertEqual(ticket["scheduled_at"], datetime.datetime.strptime(future, "%Y-%m-%dT%H:%M"))

    def test_checkbox_desmarcado_vence_padrao_verdadeiro(self):
        # hidden "false" + checkbox ausente: vale "false" e a flag e omitida.
        tid, _ = self._create(answers={"verbose": ["false"]})
        snap = json.loads(self.tickets.get(tid)["submitted_params"])
        self.assertNotIn("--verbose", snap["args"])
        tid2, _ = self._create(answers={"verbose": ["false", "true"]})
        self.assertIn("--verbose", json.loads(self.tickets.get(tid2)["submitted_params"])["args"])

    # ---------------------------------------------------------- autorizacao

    def test_sem_exec_script(self):
        before = self._ticket_total()
        with self.assertRaises(AccessDenied) as cm:
            self._create(login="consulta", script_id="1", environment="PRODUCAO")
        self.assertEqual(cm.exception.reason, "NO_FEATURE")
        self.assertEqual(self.svc.available_scripts(self.ctx["consulta"]), [])
        self.assertEqual(self._ticket_total(), before)

    def test_script_nao_homologado_no_ambiente(self):
        # sync_tabelas (4) so e homologado em HOMOLOGACAO; admin nao dispensa a homologacao.
        with self.assertRaises(AccessDenied) as cm:
            self._create(login="admin", script_id="4", environment="PRODUCAO")
        self.assertEqual(cm.exception.reason, "NOT_HOMOLOGATED")
        with self.assertRaises(AccessDenied):
            self.svc.trigger_summary(self.ctx["admin"], "4", "PRODUCAO", {})

    def test_script_forjado_e_ambiente_nao_autorizado(self):
        ctx = self.ctx["op.hml"]
        for script_id, environment in (("6", "PRODUCAO"), ("1", "PRODUCAO"), ("999", "HOMOLOGACAO"),
                                    ("abc", "HOMOLOGACAO"), ("1", "INEXISTENTE")):
            with self.assertRaises(AccessDenied):
                self.svc.prepare_form(ctx, script_id, environment)
        with self.assertRaises(AccessDenied):
            self.svc.available_environments(ctx, "6")

    def test_listas_filtradas_para_op_hml(self):
        ctx = self.ctx["op.hml"]
        ids = sorted(s["id"] for g in self.svc.available_scripts(ctx) for s in g["scripts"])
        self.assertEqual(ids, [1, 2, 3, 4])
        _script, environments = self.svc.available_environments(ctx, "1")
        self.assertEqual([a["name"] for a in environments], ["HOMOLOGACAO"])

    # ------------------------------------------------------------ validacao

    def test_obrigatorio_faltando(self):
        links = [{"parameter_id": v["parameter_id"], "sort_order": v["sort_order"], "required": v["required"],
                     "default_value_override": None if v["code"] == "data_ref" else v["default_value_override"]}
                    for v in self.catalog.script_params_get(1)]
        self.catalog.script_params_save(1, links, actor="teste")
        before = self._ticket_total()
        tid, errors = self._create(answers={"data_ref": "   "})
        self.assertIsNone(tid)
        self.assertIn("data_ref", errors)
        self.assertEqual(self._ticket_total(), before)

    def test_regex_invalida_e_todos_os_erros_de_uma_vez(self):
        before = self._ticket_total()
        past = (self.tickets.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        tid, errors = self._create(login="admin", script_id="6", environment="PRODUCAO",
                                 answers={"codigo_filial": "ABC", "taxa_ajuste": "x"},
                                 priority="9", scheduled_at=past)
        self.assertIsNone(tid)
        self.assertEqual(sorted(errors), ["codigo_filial", "priority", "scheduled_at", "taxa_ajuste"])
        self.assertEqual(self._ticket_total(), before)

    def test_prioridade_1_por_nao_admin(self):
        tid, errors = self._create(priority="1")
        self.assertIsNone(tid)
        self.assertEqual(list(errors), ["priority"])
        self.assertNotIn(1, [p for p, _ in self.svc.prepare_form(
            self.ctx["op.hml"], "1", "HOMOLOGACAO")["priorities"]])

    def test_scheduled_at_no_passado(self):
        past = (self.tickets.now() - datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
        tid, errors = self._create(scheduled_at=past)
        self.assertIsNone(tid)
        self.assertEqual(list(errors), ["scheduled_at"])
        tid, errors = self._create(scheduled_at="31/12/2099")
        self.assertEqual(list(errors), ["scheduled_at"])

    def test_scheduled_at_exato_sem_tolerancia_de_minuto(self):
        # CR-003 P5 (README §5.4): o minuto corrente, ja passado, e recusado.
        repo_factory._fake_store.set_clock(lambda: datetime.datetime(2026, 10, 16, 10, 5, 30))
        tid, errors = self._create(scheduled_at="2026-10-16T10:05")
        self.assertIsNone(tid)
        self.assertIn(u"deixe em branco para rodar agora", errors["scheduled_at"])
        tid, errors = self._create(scheduled_at="2026-10-16T10:06")
        self.assertEqual(errors, {})

    def test_scheduled_at_limite_366_dias(self):
        # CR-007 D2 (README §5.4): scheduled_at no maximo 366 dias no futuro.
        now = self.tickets.now()
        plus_366 = (now + datetime.timedelta(days=366)).strftime("%Y-%m-%dT%H:%M")
        tid, errors = self._create(scheduled_at=plus_366)
        self.assertEqual(errors, {})
        plus_367 = (now + datetime.timedelta(days=367)).strftime("%Y-%m-%dT%H:%M")
        tid, errors = self._create(scheduled_at=plus_367)
        self.assertIsNone(tid)
        self.assertIn(u"Escolha uma data até", errors.get("scheduled_at", ""))

    def test_caminho_em_pasta_do_sistema_rejeita_o_disparo(self):
        # CR-011 (S1): o web confere so o formato e as pastas do sistema; o arquivo e conferido pelo agente.
        self.catalog.scripts_update(1, {"path_file": "/etc/carga.py"}, actor="teste")
        tid, errors = self._create()
        self.assertIsNone(tid)
        self.assertEqual(errors, {ticket_service.GENERAL_FIELD: ticket_service.MSG_SCRIPT_UNAVAILABLE})

    # ----------------------------------------------------- previa e formulario

    def test_previa_mascara_sensivel(self):
        r = self.svc.trigger_summary(self.ctx["op.hml"], "1", "HOMOLOGACAO", {"documento_cliente": SECRET})
        self.assertEqual(r["errors"], {})
        argv = r["argv"]
        self.assertNotIn(SECRET, " ".join(argv))
        self.assertEqual(argv[argv.index("--documento") + 1], params_compiler.MASK)
        r = self.svc.trigger_summary(self.ctx["op.hml"], "1", "HOMOLOGACAO", {"modo_exec": "X"})
        self.assertIsNone(r["argv"])
        self.assertIn("modo_exec", r["errors"])

    def test_formulario_nao_expoe_sensivel(self):
        form = self.svc.prepare_form(self.ctx["op.hml"], "1", "HOMOLOGACAO",
                                            values={"documento_cliente": SECRET, "data_ref": "2026-01-01"})
        fields = dict((c["code"], c) for c in form["fields"])
        self.assertEqual([c["code"] for c in form["fields"]],
                         ["data_ref", "limite_linhas", "modo_exec", "verbose", "documento_cliente"])
        self.assertIsNone(fields["documento_cliente"]["value"])
        self.assertIsNone(fields["documento_cliente"]["default"])
        self.assertTrue(fields["documento_cliente"]["has_default"])
        self.assertNotIn("00011122233", json.dumps(form, default=str))
        self.assertEqual(fields["data_ref"]["value"], "2026-01-01")
        self.assertEqual(fields["modo_exec"]["default_text"], "Execucao Real")
        self.assertTrue(fields["verbose"]["checked"])


@_SKIP_ROOT
class TestTriggerClarity(_BaseTicket):
    """CR-004 U4 (README §5.4, "Clareza no disparo")."""

    def test_producao_vem_do_cadastro_e_nao_do_nome(self):
        # CR-017: o alerta de producao segue tbsss_environments.is_production.
        _script, envs = self.svc.available_environments(self.ctx["admin"], "1")
        self.assertEqual(dict((a["name"], a["production"]) for a in envs),
                         {"PRODUCAO": True, "HOMOLOGACAO": False})
        form = self.svc.prepare_form(self.ctx["op.hml"], "1", "HOMOLOGACAO")
        self.assertFalse(form["environment"]["production"])
        self.catalog.environments_update(2, {"is_production": "Y"}, actor="teste")
        form = self.svc.prepare_form(self.ctx["op.hml"], "1", "HOMOLOGACAO")
        self.assertTrue(form["environment"]["production"])

    def test_resumo_em_frase_com_sensivel_mascarado(self):
        r = self.svc.trigger_summary(self.ctx["op.hml"], "1", "HOMOLOGACAO",
                                    {"documento_cliente": "12345678900"}, "3", "")
        self.assertEqual(r["errors"], {})
        summary = r["summary"]
        self.assertEqual((summary["script"], summary["environment"], summary["when"], summary["priority"]),
                         ("carga_diaria", "HOMOLOGACAO", u"agora", 3))
        self.assertTrue(summary["phrase"].startswith(u"Vamos rodar carga_diaria no ambiente HOMOLOGACAO agora, "
                                                   u"com prioridade 3."))
        values = dict((x["label"], x["value"]) for x in summary["answers"])
        self.assertNotIn("12345678900", summary["phrase"])
        self.assertIn(params_compiler.MASK, values.values())
        self.assertTrue(r["argv"])

    def test_resumo_com_horario_e_erros(self):
        future = (self.tickets.now() + datetime.timedelta(days=1)).replace(second=0)
        r = self.svc.trigger_summary(self.ctx["op.hml"], "1", "HOMOLOGACAO", {}, "2", future.strftime("%Y-%m-%dT%H:%M"))
        self.assertEqual(r["summary"]["when"], u"em %s às %s" % (future.strftime("%d/%m/%Y"), future.strftime("%H:%M")))
        r = self.svc.trigger_summary(self.ctx["op.hml"], "1", "HOMOLOGACAO", {"data_ref": "31/12/2026"}, "2", "")
        self.assertIsNone(r["summary"])
        self.assertIn("data_ref", r["errors"])

    def test_exemplo_por_tipo_no_formulario(self):
        form = self.svc.prepare_form(self.ctx["op.hml"], "1", "HOMOLOGACAO")
        examples = dict((c["code"], c["example"]) for c in form["fields"])
        self.assertTrue(examples["data_ref"].startswith(u"Use o formato AAAA-MM-DD"))
        self.assertEqual(examples["modo_exec"], u"Escolha uma das opções da lista.")
        self.assertEqual(examples["verbose"], u"Marque para sim; deixe desmarcado para não.")

    def test_ultimas_respostas_sem_sensiveis(self):
        ctx = self.ctx["op.hml"]
        self.assertFalse(self.svc.has_last_run(ctx, "1", "HOMOLOGACAO"))
        tid, errors = self._create(answers={"data_ref": "2026-11-30", "documento_cliente": "99988877766",
                                            "modo_exec": "SIMULACAO"})
        self.assertEqual(errors, {})
        self.assertTrue(self.svc.has_last_run(ctx, "1", "HOMOLOGACAO"))
        values, warnings_value = self.svc.last_answers(ctx, "1", "HOMOLOGACAO")
        self.assertEqual(values["data_ref"], "2026-11-30")
        self.assertEqual(values["modo_exec"], "SIMULACAO")
        self.assertNotIn("documento_cliente", values)
        self.assertEqual(warnings_value["documento_cliente"], ticket_service.MSG_LAST_SENSITIVE)
        # Opcao removida do catalogo: a resposta antiga deixa de valer e vem com aviso.
        self.catalog.parameters_update(3, {"options_json": '{"REAL":"Execucao Real"}', "default_value": "REAL"}, actor="teste")
        values, warnings_value = self.svc.last_answers(ctx, "1", "HOMOLOGACAO")
        self.assertNotIn("modo_exec", values)
        self.assertEqual(warnings_value["modo_exec"], ticket_service.MSG_LAST_CHANGED)


@_SKIP_ROOT
class TestTicketQuery(_BaseTicket):
    """F3.3: escopo da lista, filtros, detalhe, cancelamento e reexecucao."""

    def _without(self, login, *features_ids):
        ctx = dict(self.ctx[login])
        ctx["features"] = frozenset(ctx["features"] - set(features_ids))
        return ctx

    def _insert_row(self, **fields):
        ticket = {"script_id": 1, "environment": "HOMOLOGACAO", "requested_by": "admin", "status": "PENDING",
                  "priority": 2, "submitted_params": "{}"}
        ticket.update(fields)
        return self.tickets.create(ticket, [])

    def _ids(self, ctx, filters=None):
        return set(t["id"] for t in self.svc.list(ctx, filters or {}, 1, 100)["items"])

    # ------------------------------------------------------------- escopo

    def test_escopo_da_lista_por_perfil(self):
        dev = self._insert_row(environment="DESENV")
        by_env = dict((t["id"], t["environment"]) for t in self.tickets.list(page=1, size=1000)["items"])
        self.assertEqual(self._ids(self.ctx["admin"]), set(by_env))
        query = self._ids(self.ctx["consulta"])
        self.assertNotIn(dev, query)
        self.assertEqual(query, set(i for i, a in by_env.items() if a in ("PRODUCAO", "HOMOLOGACAO")))
        op_hml = self._ids(self.ctx["op.hml"])
        self.assertIn(dev, op_hml)
        self.assertEqual(op_hml, set(i for i, a in by_env.items() if a in ("HOMOLOGACAO", "DESENV")))

    def test_lista_mostra_o_motivo_em_nome_simples(self):
        # CR-018b (README §2.4.2): a lista nao mostra o codigo tecnico; so o nome simples do motivo de erro.
        items = self.svc.list(self.ctx["admin"], {}, 1, 100)["items"]
        failed = [t for t in items if t["status_reason"] in ui_helpers.REASON_NAMES]
        self.assertTrue(failed)
        for t in items:
            self.assertEqual(t["reason_name"], ui_helpers.REASON_NAMES.get(t["status_reason"]))

    def test_filtro_por_solicitante_so_para_quem_ve_logins(self):
        # CR-018a: o consulta ve "outra pessoa" no lugar do login (CR-008 E5); filtrar por um login alheio
        # revelaria quem pediu, entao o filtro e ignorado. O proprio login continua aceito.
        theirs = self._insert_row(requested_by="op.prod", environment="HOMOLOGACAO")
        consulta = self.ctx["consulta"]
        self.assertEqual(self._ids(consulta, {"requested_by": "op.prod"}), self._ids(consulta))
        self.assertEqual(self.svc.allowed_filters(consulta, {"requested_by": "op.prod"}), {})
        self.assertEqual(self.svc.allowed_filters(consulta, {"requested_by": "consulta"}),
                         {"requested_by": "consulta"})
        admin = self._ids(self.ctx["admin"], {"requested_by": "op.prod"})
        self.assertIn(theirs, admin)
        self.assertTrue(all(self.tickets.get(i)["requested_by"] == "op.prod" for i in admin))

    def test_sem_ver_logs_lista_apenas_proprios(self):
        ctx = self._without("op.hml", "VIEW_LOGS")
        items = self.svc.list(ctx, {}, 1, 100)["items"]
        self.assertTrue(items)
        # Sem VIEW_AUDIT o proprio login aparece como "você" (CR-008, E5).
        self.assertEqual(set(t["requested_by"] for t in items), {u"você"})
        # Filtro por login alheio e ignorado (CR-018a): continua so com os proprios, nunca os do admin.
        others = self.svc.list(ctx, {"requested_by": "admin"}, 1, 100)["items"]
        self.assertEqual(set(t["requested_by"] for t in others), {u"você"})

    def test_solicitante_mascarado_sem_auditoria(self):
        # CR-008, E5: consulta sem VIEW_AUDIT nao recebe login de terceiros; admin recebe.
        ctx = self._without("consulta", "VIEW_AUDIT")
        items = self.svc.list(ctx, {}, 1, 100)["items"]
        self.assertTrue(items)
        self.assertEqual(set(t["requested_by"] for t in items), {u"outra pessoa"})
        self.assertEqual(self.svc.detail(ctx, 17)["requested_by"], u"outra pessoa")
        self.assertEqual(self.svc.detail(self.ctx["admin"], 17)["requested_by"], "op.prod")
        without_nothing = self._without("consulta", "VIEW_LOGS")
        with self.assertRaises(AccessDenied):
            self.svc.list(without_nothing, {}, 1, 20)

    def test_detalhe_fora_do_escopo_e_inexistente(self):
        dev = self._insert_row(environment="DESENV")
        for login, tid in (("consulta", dev), ("op.hml", 1), ("admin", 99999)):
            with self.assertRaises(RepoNotFound):
                self.svc.detail(self.ctx[login], str(tid))
        for invalid in ("abc", "-1", "0", None, "1; DROP"):
            with self.assertRaises(RepoNotFound):
                self.svc.detail(self.ctx["admin"], invalid)
        self.assertEqual(self.svc.detail(self.ctx["op.hml"], str(dev))["id"], dev)

    # ------------------------------------------------------------- filtros

    def test_normalizar_filtros_allowlist(self):
        cleaned = ticket_service.normalize_filters({
            "status": ["RUNNING", "X", "PENDING", "RUNNING"], "environment": "producao", "script": "07",
            "requested_by": " OP.Hml ", "created_from": "2026-02-30", "created_to": "2026-10-14",
            "source": "agendamento", "sort_order": "id; DROP TABLE", "created_at": "x"})
        self.assertEqual(list(cleaned.items()), [
            ("status", ["PENDING", "RUNNING"]), ("script", 7), ("requested_by", "op.hml"),
            ("created_to", "2026-10-14"), ("source", "agendamento")])
        self.assertEqual(ticket_service.normalize_filters({"status": "SUCCESS", "source": "outro",
                                                            "script": "0", "requested_by": "a"}),
                         {"status": ["SUCCESS"]})

    def test_filtro_de_periodo_nos_limites(self):
        day = datetime.datetime(2025, 3, 10)
        one_seg = datetime.timedelta(seconds=1)
        before = self._insert_row(environment="DESENV", created_at=day - one_seg)
        start = self._insert_row(environment="DESENV", created_at=day)
        end = self._insert_row(environment="DESENV", created_at=day + datetime.timedelta(days=1) - one_seg)
        after = self._insert_row(environment="DESENV", created_at=day + datetime.timedelta(days=1))
        admin = self.ctx["admin"]
        base = {"environment": "DESENV"}
        self.assertEqual(self._ids(admin, dict(base, created_from="2025-03-10", created_to="2025-03-10")),
                         {start, end})
        self.assertEqual(self._ids(admin, dict(base, created_from="2025-03-10")), {start, end, after})
        self.assertEqual(self._ids(admin, dict(base, created_to="2025-03-09")), {before})
        self.assertEqual(self._ids(admin, dict(base, created_from="2025-03-11", created_to="2025-03-10")), set())

    def test_filtros_combinados_e_paginacao(self):
        admin = self.ctx["admin"]
        running = self._ids(admin, {"status": ["RUNNING"], "environment": "PRODUCAO"})
        self.assertTrue(running)
        for t in self.svc.list(admin, {"status": ["RUNNING"], "environment": "PRODUCAO"}, 1, 100)["items"]:
            self.assertEqual((t["status"], t["environment"]), ("RUNNING", "PRODUCAO"))
        sched_value = self.svc.list(admin, {"source": "agendamento"}, 1, 100)["items"]
        self.assertTrue(sched_value)
        self.assertTrue(all(t["source"] == "agendamento" for t in sched_value))
        page2 = self.svc.list(admin, {"status": ["SUCCESS"]}, 2, 5)
        self.assertEqual((page2["page"], len(page2["items"])), (2, 5))
        beyond = self.svc.list(admin, {"status": ["SUCCESS"]}, 99, 5)
        self.assertEqual(beyond["page"], (beyond["total"] + 4) // 5)
        self.assertTrue(beyond["items"])

    # --------------------------------------------------------- cancelamento

    def test_cancelamento_nos_tres_resultados(self):
        ctx = self.ctx["op.hml"]
        pending, _ = self._create()
        self.assertEqual(self.svc.cancel(ctx, IP, str(pending)), "CANCELADO")
        t = self.tickets.get(pending)
        self.assertEqual((t["status"], t["status_reason"], t["return_code"]), ("CANCELLED", "CANCEL_USER", -1))
        self.assertEqual(self.svc.cancel(ctx, IP, str(pending)), "TERMINAL")

        running = self._insert_row(status="RUNNING", requested_by="op.hml", agent_id="agt-x")
        self.assertEqual(self.svc.cancel(ctx, IP, str(running)), "SINALIZADO")
        t = self.tickets.get(running)
        self.assertEqual((t["status"], t["cancel_requested"]), ("RUNNING", "Y"))
        self.assertFalse(self.svc.detail(ctx, str(running))["can_cancel"])

        # CR-003 P5 (README §5.6): pedido repetido e ticket encerrado tambem sao auditados, com o resultado.
        self.assertEqual(self.svc.cancel(ctx, IP, str(running)), "JA_SINALIZADO")
        regs = self.audit.list(filters={"action": "TICKET_CANCEL", "entity_id": running})["items"]
        self.assertEqual([(r["actor"], r["source_ip"], r["detail"]) for r in regs],
                         [("op.hml", IP, u"resultado: já sinalizado"), ("op.hml", IP, u"resultado: sinalizado")])
        regs = self.audit.list(filters={"action": "TICKET_CANCEL", "entity_id": pending})["items"]
        self.assertEqual([r["detail"] for r in regs],
                         [u"resultado: sem efeito: ticket encerrado", u"resultado: cancelado"])
        self.assertEqual(set(ticket_service.MSG_CANCEL),
                         {"TERMINAL", "CANCELADO", "SINALIZADO", "JA_SINALIZADO"})

    def test_canc_ticket_sem_ver_logs_nao_cancela_ticket_de_terceiro(self):
        # CR-018a (README §4.3.C): ticket de terceiro so e cancelado por quem o enxerga (VIEW_LOGS).
        third = self._insert_row(requested_by="admin")
        ctx = self._without("op.hml", "VIEW_LOGS")
        with self.assertRaises(RepoNotFound):
            self.svc.cancel(ctx, IP, str(third))
        self.assertEqual(self.tickets.get(third)["status"], "PENDING")
        self.assertEqual(self.svc.cancel(self.ctx["op.hml"], IP, str(third)), "CANCELADO")

    def test_cancelar_terceiro_sem_canc_ticket_negado(self):
        third = self._insert_row(requested_by="admin")
        ctx = self._without("op.hml", "CANCEL_TICKET")
        self.assertFalse(self.svc.detail(ctx, str(third))["can_cancel"])
        with self.assertRaises(AccessDenied):
            self.svc.cancel(ctx, IP, str(third))
        self.assertEqual(self.tickets.get(third)["status"], "PENDING")
        own, _ = self._create()
        self.assertEqual(self.svc.cancel(ctx, IP, str(own)), "CANCELADO")
        self.assertEqual(self.svc.cancel(self.ctx["op.hml"], IP, str(third)), "CANCELADO")
        with self.assertRaises(RepoNotFound):
            self.svc.cancel(self.ctx["op.hml"], IP, "1")

    # ---------------------------------------------------------- reexecucao

    def test_reexecucao_ok_com_parent_ticket_id(self):
        ctx = self.ctx["op.hml"]
        original, _ = self._create(answers={"data_ref": "2026-10-20", "documento_cliente": SECRET}, priority="3")
        with self.assertRaises(AccessDenied):
            self.svc.rerun(ctx, IP, str(original))
        self.assertFalse(self.svc.detail(ctx, str(original))["can_rerun"])
        self.svc.cancel(ctx, IP, str(original))
        self.assertTrue(self.svc.detail(ctx, str(original))["can_rerun"])

        new = self.svc.rerun(ctx, IP, str(original))
        t_orig, t_new = self.tickets.get(original), self.tickets.get(new)
        self.assertEqual(t_new["parent_ticket_id"], original)
        self.assertEqual((t_new["status"], t_new["priority"], t_new["requested_by"]), ("PENDING", 3, "op.hml"))
        snap_orig, snap_new = json.loads(t_orig["submitted_params"]), json.loads(t_new["submitted_params"])
        self.assertEqual(snap_new["args"], snap_orig["args"])
        self.assertEqual(snap_new["answers"], snap_orig["answers"])
        regs = self.audit.list(filters={"action": "TICKET_RERUN", "entity_id": new})["items"]
        self.assertEqual(len(regs), 1)
        self.assertNotIn(SECRET, regs[0]["detail"] or "")

        self.assertEqual([f["id"] for f in self.svc.detail(ctx, str(original))["children"]], [new])
        self.assertEqual(self.svc.detail(ctx, str(new))["parent"]["id"], original)

    def test_reexecucao_de_terceiro_por_nao_admin_negada(self):
        third = self._insert_row(requested_by="admin", status="SUCCESS")
        with self.assertRaises(AccessDenied):
            self.svc.rerun(self.ctx["op.hml"], IP, str(third))
        self.assertFalse(self.svc.detail(self.ctx["op.hml"], str(third))["can_rerun"])
        with self.assertRaises(RepoNotFound):
            self.svc.rerun(self.ctx["consulta"], IP, str(self._insert_row(environment="DESENV", status="FAILED")))

    def test_reexecucao_com_catalogo_alterado_gera_erro_tratado(self):
        ctx = self.ctx["op.hml"]
        original, _ = self._create(answers={"documento_cliente": SECRET})
        self.svc.cancel(ctx, IP, str(original))
        links = [{"parameter_id": v["parameter_id"], "sort_order": v["sort_order"], "required": v["required"],
                     "default_value_override": v["default_value_override"]} for v in self.catalog.script_params_get(1)]
        links.append({"parameter_id": 10, "sort_order": 6, "required": "Y", "default_value_override": None})
        self.catalog.script_params_save(1, links, actor="teste")
        before = self._ticket_total()
        with self.assertRaises(RerunError) as cm:
            self.svc.rerun(ctx, IP, str(original))
        self.assertEqual(cm.exception.ticket_id, original)
        self.assertEqual(list(cm.exception.errors), ["descricao_lote"])
        self.assertEqual(self._ticket_total(), before)

        prep = self.svc.prepare_rerun(ctx, str(original))
        self.assertEqual((prep["ticket_id"], prep["script_id"], prep["environment"]), (original, 1, "HOMOLOGACAO"))
        self.assertIn("descricao_lote", prep["errors"])
        self.assertNotIn("documento_cliente", prep["values"])
        self.assertEqual(prep["values"]["data_ref"], "2026-10-14")

        new, errors = self.svc.create_ticket(ctx, IP, "1", "HOMOLOGACAO", dict(prep["values"], descricao_lote="x"),
                                            prep["priority"], "", rerun_of=str(original))
        self.assertEqual(errors, {})
        self.assertEqual(self.tickets.get(new)["parent_ticket_id"], original)
        with self.assertRaises(AccessDenied):
            self.svc.create_ticket(ctx, IP, "2", "HOMOLOGACAO", {}, "2", "", rerun_of=str(original))

    # ------------------------------------------------------------ sensiveis

    def test_sensiveis_mascarados_no_detalhe(self):
        tid, _ = self._create(answers={"documento_cliente": SECRET})
        for login in ("op.hml", "admin", "consulta"):
            if login == "consulta":
                det = self.svc.detail(self.ctx[login], "1")
            else:
                det = self.svc.detail(self.ctx[login], str(tid))
                answers = dict((r["code"], r) for r in det["answers"])
                self.assertEqual(answers["documento_cliente"]["value"], params_compiler.MASK)
                self.assertTrue(answers["documento_cliente"]["sensitive"])
                self.assertEqual(answers["data_ref"]["value"], "2026-10-14")
                self.assertIn(params_compiler.MASK, det["display_argv"])
            serial = json.dumps(det, default=str)
            self.assertNotIn(SECRET, serial)
            self.assertNotIn("00011122233", serial)

    def test_detalhe_campos_e_descricao_motivo(self):
        det = self.svc.detail(self.ctx["admin"], "30")
        self.assertEqual((det["status"], det["status_reason"], det["return_code"]), ("FAILED", "TIMEOUT", -3))
        self.assertEqual(det["reason_description"], ui_helpers.reason_description("TIMEOUT"))
        self.assertNotEqual(det["duration"], "-")
        self.assertEqual(self.svc.detail(self.ctx["admin"], "25")["parent"]["id"], 17)
        self.assertEqual([f["id"] for f in self.svc.detail(self.ctx["admin"], "17")["children"]], [25])

    def test_caminho_completo_para_quem_nao_e_admin(self):
        """CR-005 D8: quem nao e admin ve o caminho completo no detalhe, no comando e na previa."""
        tid, errors = self._create(login="op.hml", answers={"data_ref": "2026-10-20", "modo_exec": "SIMULACAO"})
        self.assertEqual(errors, {})
        path = os.path.join(self.base, "carga_diaria.py")
        det = self.svc.detail(self.ctx["op.hml"], str(tid))
        self.assertEqual(det["snapshot"]["path_file"], path)
        self.assertEqual(det["display_argv"][2], path)
        self.assertIn(path, det["display_command"])
        r = self.svc.trigger_summary(self.ctx["op.hml"], "1", "HOMOLOGACAO",
                                     {"data_ref": "2026-10-20", "modo_exec": "SIMULACAO"})
        self.assertEqual(r["errors"], {})
        self.assertEqual(r["argv"][2], path)


if __name__ == "__main__":
    unittest.main()


class TestTicketOutput(_BaseTicket):
    """CR-012 (README §8.13): quadro Saida e download do zip, com a regra de leitura do log."""

    def test_quadro_por_situacao(self):
        available = self.svc.detail(self.ctx["admin"], 17)["output"]
        self.assertEqual((available["state"], available["css_class"], available["can_download"]),
                         ("AVAILABLE", "success", True))
        self.assertIn(u"2 arquivos", available["happened"])
        exceeded = self.svc.detail(self.ctx["admin"], 29)["output"]
        self.assertFalse(exceeded["can_download"])
        self.assertIn(u"quantidade de arquivos", exceeded["happened"])
        self.assertIn(u"agente agt-host02", exceeded["todo"])
        failed = self.svc.detail(self.ctx["admin"], 30)["output"]
        self.assertEqual((failed["state"], failed["can_download"]), ("FAILED", False))
        self.assertIn(u"agente agt-host01", failed["todo"])
        self.assertIsNone(self.svc.detail(self.ctx["admin"], 18)["output"], "sem saida, sem quadro")
        for field in ("content", "base", "relativo"):
            self.assertNotIn(field, available)

    def test_gravando_ha_mais_de_uma_hora_e_tamanho_legivel(self):
        now = datetime.datetime(2026, 10, 20, 12, 0, 0)
        recent = ui_helpers.output_panel({"state": "WRITING", "agent_id": "a1",
                                           "created_at": now - datetime.timedelta(minutes=5)}, now)
        self.assertEqual((recent["css_class"], recent["can_download"]), ("info", False))
        self.assertIn(u"em preparação", recent["happened"])
        stop = ui_helpers.output_panel({"state": "WRITING", "agent_id": "a1",
                                          "created_at": now - datetime.timedelta(hours=2)}, now)
        self.assertIn(u"não foi concluída", stop["happened"])
        self.assertIn(u"agente a1", stop["todo"])
        bytes_ = ui_helpers.output_panel({"state": "EXCEEDED", "reason": "BYTES", "agent_id": "a1"}, now)
        self.assertIn(u"limite de tamanho", bytes_["happened"])
        self.assertIsNone(ui_helpers.output_panel(None, now))
        self.assertEqual([ui_helpers.readable_size(n) for n in (None, 512, 12595, 4718592)],
                         [u"-", u"512 bytes", u"12,3 KB", u"4,5 MB"])
        one = ui_helpers.output_panel({"state": "AVAILABLE", "file_count": 1, "size_bytes": 10}, now)
        self.assertIn(u"1 arquivo ", one["happened"])

    def test_download_em_fatias_so_disponivel_e_no_escopo(self):
        import io
        import zipfile
        with mock.patch.object(ticket_service, "OUTPUT_SLICE_BYTES", 100):
            tid, size, parts = self.svc.output_chunks(self.ctx["consulta"], "17")
            data = b"".join(parts)
        self.assertEqual((tid, len(data)), (17, size))
        self.assertEqual(sorted(zipfile.ZipFile(io.BytesIO(data)).namelist()),
                         ["rejeitados/linhas_rejeitadas.csv", "resumo.txt"])
        for login, target in (("op.hml", "17"), ("admin", "29"), ("admin", "30"), ("admin", "18"),
                            ("admin", "abc"), ("admin", "99999")):
            with self.assertRaises(RepoNotFound, msg=(login, target)):
                self.svc.output_chunks(self.ctx[login], target)

    def test_falha_no_meio_do_download_encerra_sem_completar(self):
        from repo_errors import RepoError
        with mock.patch.object(ticket_service, "OUTPUT_SLICE_BYTES", 100):
            _tid, size, parts = self.svc.output_chunks(self.ctx["admin"], 17)
            first = next(parts)
            with mock.patch.object(self.tickets, "output_read", side_effect=RepoError("ORA-03113")):
                rest = b"".join(parts)
        self.assertLess(len(first) + len(rest), size)
