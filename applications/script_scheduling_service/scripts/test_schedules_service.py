# -*- coding: utf-8 -*-
"""Testes de schedules_service.py (F5.2) sobre o backend FAKE com relogio injetavel."""
import _testenv  # noqa: F401

import datetime
import json
import logging
import os
import unittest
from unittest import mock

import admin_crud
import schedules_service as svc_mod
import auth_service
import repo_factory
import security
from admin_crud import GENERAL_FIELD, AccessDenied, OperationDenied
from schedules_service import SchedulesService
from repo_errors import RepoConflict, RepoNotFound
from ticket_service import TicketService

IP = "10.4.5.6"
# Quinta-feira; os microssegundos provam que nenhuma data gravada os carrega (README §7.1).
NOW = datetime.datetime(2026, 1, 15, 10, 0, 0, 123456)
HORIZON = 1461
SECRET = "tok-ultra-secreto-77"
PERFIL_OP_PROD, PERFIL_OP_HML = 2, 3
FUNC_EXEC, FUNC_LOGS, FUNC_CANC, FUNC_CAD_AGD = 1, 2, 3, 9
ARROW = u" → "


class _Base(unittest.TestCase):

    def setUp(self):
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
        self.agd = repo_factory.get("schedules")
        self.audit = repo_factory.get("audit")
        self.rbac = repo_factory.get("rbac")
        self.log = logging.getLogger("sss_teste_agd")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        self.auth = auth_service.AuthService(
            repo_factory.get("users"), self.rbac, self.catalog, self.audit, 5, 900, self.log)

        # MANAGE_SCHEDULES para os operadores (no seed, so o admin a tem).
        self.rbac.matrix_save(PERFIL_OP_PROD, [FUNC_EXEC, FUNC_LOGS, FUNC_CANC, FUNC_CAD_AGD], [1, 2], [1, 2, 3, 6], actor="teste")
        self.rbac.matrix_save(PERFIL_OP_HML, [FUNC_EXEC, FUNC_LOGS, FUNC_CANC, FUNC_CAD_AGD], [2, 3], [1, 2, 3, 4], actor="teste")
        self.ctx = {
            "admin": self._ctx(1, "admin", 1),
            "op.prod": self._ctx(2, "op.prod", PERFIL_OP_PROD),
            "op.hml": self._ctx(3, "op.hml", PERFIL_OP_HML),
            "consulta": self._ctx(4, "consulta", 4),
        }
        self.now = NOW
        self.tickets = repo_factory.get("tickets")
        trigger = TicketService(self.catalog, self.tickets, self.log)
        self.svc = SchedulesService(self.agd, self.catalog, repo_factory.get("users"), trigger,
                                       lambda: self.now, HORIZON, self.log,
                                       tickets=self.tickets, rbac_repo=self.rbac)
        self.aud_base = max([a["id"] for a in self.audit.list(page=1, size=1000)["items"]] or [0])

    def _ctx(self, user_id, login, profile_id):
        session = {"user_id": user_id, "login": login, "profile_id": profile_id,
                  "perm_version": self.rbac.profiles_get(profile_id)["perm_version"], "session_epoch": 0}
        return self.auth.revalidate(session)

    def _audits(self, action=None):
        items = self.audit.list(filters={"action": action} if action else None, page=1, size=1000)["items"]
        return [a for a in items if a["entity"] == "tbsss_schedules" and a["id"] > self.aud_base]

    def _data(self, **extra):
        date = {"name": "Regra de teste", "script_id": "1", "environment": "HOMOLOGACAO",
                 "recurrence_type": "DAILY", "run_time": "03:00", "priority": "2",
                 "answers": {"data_ref": "2026-01-20", "modo_exec": "SIMULACAO"}}
        date.update(extra)
        return date

    def _save(self, login="admin", **extra):
        return self.svc.save(self.ctx[login], IP, self._data(**extra))

    def _version(self, reg):
        # Como a tela: as respostas sensiveis do script entram pelo marcador (CR-003 P1).
        sensitive = frozenset(v["code"] for v in repo_factory.get("catalog").script_params_get(reg["script_id"])
                              if v.get("sensitive") == "Y")
        return svc_mod.version(reg, sensitive)


class TestSaveTypes(_Base):

    def test_valores_fora_do_formato_sao_recusados_nunca_cortados(self):
        # CR-003 P7 / D11 (README §7.6).
        cases = (
            ({"recurrence_type": "MONTHLY", "run_time": "01:00", "month_day": "100"}, "month_day"),
            ({"recurrence_type": "MONTHLY", "run_time": "01:00", "month_day": "311"}, "month_day"),
            ({"recurrence_type": "DAILY", "run_time": "03:000"}, "run_time"),
            ({"recurrence_type": "DAILY", "run_time": "03:00", "start_date": "2026-02-01T10:00:00"},
             "start_date"),
            ({"recurrence_type": "DAILY", "run_time": "03:00", "start_date": "2026-02-01T10:00:00.999"},
             "start_date"),
        )
        for extra, field in cases:
            aid, errors = self._save(**extra)
            self.assertIsNone(aid, extra)
            self.assertIn(field, errors, extra)

    def test_data_fim_ignorada_em_unica(self):
        aid, errors = self._save(recurrence_type="ONCE", start_date="2026-02-01T08:30",
                                  end_date="2026-01-01T00:00")
        self.assertEqual(errors, {})
        self.assertIsNone(self.agd.get(aid)["end_date"])

    def test_salvar_cada_tipo(self):
        cases = [
            ({"recurrence_type": "ONCE", "start_date": "2026-02-01T08:30"}, datetime.datetime(2026, 2, 1, 8, 30)),
            ({"recurrence_type": "DAILY", "run_time": "03:00"}, datetime.datetime(2026, 1, 16, 3, 0)),
            ({"recurrence_type": "WEEKLY", "run_time": "04:00", "week_days": ["5", "1", "3"]},
             datetime.datetime(2026, 1, 16, 4, 0)),
            ({"recurrence_type": "MONTHLY", "run_time": "01:00", "month_day": "31"},
             datetime.datetime(2026, 1, 31, 1, 0)),
            ({"recurrence_type": "CRON", "cron_expression": "*/15 8-18 * * 1-5"},
             datetime.datetime(2026, 1, 15, 10, 15)),
        ]
        for extra, next_value in cases:
            aid, errors = self._save(**extra)
            self.assertEqual(errors, {}, extra)
            reg = self.agd.get(aid)
            self.assertEqual(reg["next_run_at"], next_value, extra)
            self.assertEqual(reg["user_id"], 1)
            self.assertEqual(reg["active"], "Y")
            self.assertIsNone(reg["pause_reason"])
            for field in ("start_date", "end_date", "next_run_at"):
                if reg[field] is not None:
                    self.assertEqual(reg[field].microsecond, 0, field)
        weekly = self.agd.list(filters={"name": "Regra de teste"}, size=100)["items"]
        self.assertIn("1,3,5", [r["week_days"] for r in weekly])

    def test_campos_de_outros_tipos_sao_descartados(self):
        aid, errors = self._save(recurrence_type="DAILY", run_time="03:00", month_day="5",
                                  cron_expression="* * * * *", week_days="1,2")
        self.assertEqual(errors, {})
        reg = self.agd.get(aid)
        self.assertEqual((reg["month_day"], reg["cron_expression"], reg["week_days"]), (None, None, None))

    def test_inicio_vazio_vale_agora_truncado(self):
        aid, _errors = self._save()
        self.assertEqual(self.agd.get(aid)["start_date"], datetime.datetime(2026, 1, 15, 10, 0))

    def test_parametros_json_ordenado_com_resolvidos(self):
        aid, _errors = self._save(answers={"modo_exec": "SIMULACAO", "data_ref": "2026-01-20",
                                              "verbose": ["false", "true"], "intruso": "x"})
        params = self.agd.get(aid)["params_json"]
        obj = json.loads(params)
        self.assertEqual(list(obj), sorted(obj))
        self.assertEqual(obj["data_ref"], "2026-01-20")
        self.assertEqual(obj["verbose"], "true")
        self.assertEqual(obj["limite_linhas"], "5000")
        self.assertNotIn("intruso", obj)


class TestValidation(_Base):

    def test_campos_obrigatorios_por_tipo(self):
        cases = [
            ({"recurrence_type": "ONCE", "start_date": ""}, "start_date"),
            ({"recurrence_type": "DAILY", "run_time": ""}, "run_time"),
            ({"recurrence_type": "WEEKLY", "run_time": "04:00", "week_days": []}, "week_days"),
            ({"recurrence_type": "MONTHLY", "run_time": "04:00", "month_day": ""}, "month_day"),
            ({"recurrence_type": "CRON", "cron_expression": ""}, "cron_expression"),
            ({"recurrence_type": "ANUAL"}, "recurrence_type"),
            ({"name": ""}, "name"),
            ({"name": "x" * 61}, "name"),
        ]
        for extra, field in cases:
            aid, errors = self._save(**extra)
            self.assertIsNone(aid, extra)
            self.assertIn(field, errors, extra)
        self.assertEqual(self._audits(), [])

    def test_formatos_invalidos(self):
        cases = [
            ({"run_time": "25:00"}, "run_time"),
            ({"recurrence_type": "WEEKLY", "week_days": ["1", "9"]}, "week_days"),
            ({"recurrence_type": "MONTHLY", "month_day": "32"}, "month_day"),
            ({"recurrence_type": "MONTHLY", "month_day": "x"}, "month_day"),
            ({"start_date": "15/01/2026"}, "start_date"),
            ({"start_date": "2026-01-20T10:00", "end_date": "2026-01-19T10:00"}, "end_date"),
        ]
        for extra, field in cases:
            _aid, errors = self._save(**extra)
            self.assertIn(field, errors, extra)

    def test_cron_invalido(self):
        for expr in ("0 0 * * MON", "* * *", "5/10 * * * *", "0 0 L * *", "61 * * * *"):
            aid, errors = self._save(recurrence_type="CRON", cron_expression=expr)
            self.assertIsNone(aid, expr)
            self.assertIn("cron_expression", errors, expr)

    def test_cron_sem_ocorrencia_no_horizonte(self):
        _aid, errors = self._save(recurrence_type="CRON", cron_expression="0 0 30 2 *")
        self.assertIn("cron_expression", errors)

    def test_sem_proxima_ocorrencia(self):
        aid, errors = self._save(recurrence_type="ONCE", start_date="2026-01-15T09:00")
        self.assertIsNone(aid)
        self.assertEqual(errors, {GENERAL_FIELD: svc_mod.MSG_NO_NEXT_RUN})
        _aid, errors = self._save(start_date="2026-01-01T00:00", end_date="2026-01-10T00:00")
        self.assertEqual(errors, {GENERAL_FIELD: svc_mod.MSG_NO_NEXT_RUN})

    def test_parametros_invalidos(self):
        aid, errors = self._save(answers={"data_ref": "20/01/2026", "modo_exec": "INEXISTENTE",
                                             "limite_linhas": "abc"})
        self.assertIsNone(aid)
        self.assertEqual(set(errors), {"data_ref", "modo_exec", "limite_linhas"})
        self.assertNotIn("abc", json.dumps(errors, ensure_ascii=False))

    def test_prioridade_1_exclusiva_de_admin(self):
        _aid, errors = self._save(login="op.hml", priority="1")
        self.assertEqual(errors, {"priority": svc_mod.MSG_PRIORITY_ADMIN})
        _aid, errors = self._save(login="op.hml", priority="7")
        self.assertEqual(errors, {"priority": svc_mod.MSG_PRIORITY})
        aid, errors = self._save(priority="1")
        self.assertEqual(errors, {})
        self.assertEqual(self.agd.get(aid)["priority"], 1)

    def test_script_ou_ambiente_nao_autorizado(self):
        with self.assertRaises(OperationDenied):
            self._save(login="op.hml", environment="PRODUCAO")
        with self.assertRaises(OperationDenied):
            self._save(login="op.prod", script_id="4")
        self.assertEqual(self._audits(), [])

    def test_perfil_sem_funcionalidade(self):
        with self.assertRaises(AccessDenied):
            self._save(login="consulta")
        with self.assertRaises(AccessDenied):
            self.svc.list(self.ctx["consulta"], {}, 1, 20)
        with self.assertRaises(AccessDenied):
            self.svc.preview(self.ctx["consulta"], {"recurrence_type": "DAILY", "run_time": "03:00"})


class TestEdit(_Base):

    def _edit(self, aid, login="admin", **extra):
        reg = self.agd.get(aid)
        date = self._data(id=str(aid), version=self._version(reg), **extra)
        return self.svc.save(self.ctx[login], IP, date)

    def test_edicao_troca_usuario_id_para_o_editor(self):
        aid, _errors = self._save(login="op.prod")
        self.assertEqual(self.agd.get(aid)["user_id"], 2)
        _id, errors = self._edit(aid, login="admin", name="Regra de teste")
        self.assertEqual(errors, {})
        self.assertEqual(self.agd.get(aid)["user_id"], 1)
        changes = self._audits("UPDATE")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["actor"], "admin")
        self.assertEqual(changes[0]["source_ip"], IP)
        self.assertIn(u"user_id: 2 (op.prod)%s1 (admin)" % ARROW, changes[0]["detail"])

    def test_edicao_de_regra_do_seed_por_outro_usuario(self):
        # Regra 4: MENSAL, script 2 em HOMOLOGACAO, criada por op.hml (id 3).
        reg = self.agd.get(4)
        date = {"id": "4", "version": self._version(reg), "name": reg["name"], "recurrence_type": "MONTHLY",
                 "run_time": "01:00", "month_day": "1", "priority": "3",
                 "start_date": reg["start_date"].strftime("%Y-%m-%dT%H:%M"),
                 "answers": {"formato_saida": "JSON"}}
        _id, errors = self.svc.save(self.ctx["op.prod"], IP, date)
        self.assertEqual(errors, {})
        self.assertEqual(self.agd.get(4)["user_id"], 2)
        self.assertIn(u"user_id: 3 (op.hml)%s2 (op.prod)" % ARROW, self._audits("UPDATE")[0]["detail"])

    def test_mesmo_editor_sem_mudanca_nao_audita(self):
        aid, _errors = self._save()
        _id, errors = self._edit(aid)
        self.assertEqual(errors, {})
        self.assertEqual(self._audits("UPDATE"), [])

    def test_mesmo_editor_com_mudanca_registra_usuario_id(self):
        aid, _errors = self._save()
        _id, errors = self._edit(aid, run_time="05:00")
        self.assertEqual(errors, {})
        detail = self._audits("UPDATE")[0]["detail"]
        self.assertIn(u"user_id: 1 (admin)%s1 (admin)" % ARROW, detail)
        self.assertIn(u"run_time: 03:00%s05:00" % ARROW, detail)
        self.assertEqual(self.agd.get(aid)["next_run_at"], datetime.datetime(2026, 1, 16, 5, 0))

    def test_editor_sem_permissao_e_negado(self):
        aid, _errors = self._save(script_id="4", answers={})
        before = self.agd.get(aid)
        with self.assertRaises(OperationDenied) as cm:
            self._edit(aid, login="op.prod", run_time="06:00", answers={})
        self.assertEqual(cm.exception.message, svc_mod.MSG_NO_PERMISSION)
        self.assertEqual(self.agd.get(aid), before)
        self.assertEqual(self._audits("UPDATE"), [])
        with self.assertRaises(OperationDenied):
            self.svc.form(self.ctx["op.prod"], str(aid))

    def test_regra_fora_do_escopo_e_inexistente(self):
        # Regra 1 e de PRODUCAO; op.hml so enxerga HOMOLOGACAO e DESENV.
        with self.assertRaises(RepoNotFound):
            self.svc.form(self.ctx["op.hml"], "1")
        with self.assertRaises(RepoNotFound):
            self.svc.pause(self.ctx["op.hml"], IP, "1")
        with self.assertRaises(RepoNotFound):
            self.svc.save(self.ctx["op.hml"], IP, self._data(id="1"))
        with self.assertRaises(RepoNotFound):
            self.svc.form(self.ctx["admin"], "999")

    def test_script_e_ambiente_fixos_na_edicao(self):
        aid, _errors = self._save()
        _id, errors = self._edit(aid, script_id="2", environment="PRODUCAO")
        self.assertEqual(errors, {})
        reg = self.agd.get(aid)
        self.assertEqual((reg["script_id"], reg["environment"]), (1, "HOMOLOGACAO"))

    def test_edicao_concorrente(self):
        aid, _errors = self._save()
        reg = self.agd.get(aid)
        version = self._version(reg)
        self.agd.update(aid, {"name": "Mudou por outro"}, actor="teste")
        _id, errors = self.svc.save(self.ctx["admin"], IP, self._data(id=str(aid), version=version, name="X"))
        self.assertEqual(errors, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})
        # Mudanca entre a leitura e a escrita: o 'esperado' do repositorio barra.
        reg = self.agd.get(aid)
        original = self.agd.update

        def alterar_com_corrida(id, date, expected=None, audit=None):
            original(id, {"run_time": "07:00"}, actor="teste")
            return original(id, date, expected=expected, audit=audit)

        with mock.patch.object(self.agd, "update", side_effect=alterar_com_corrida):
            _id, errors = self.svc.save(self.ctx["admin"], IP,
                                         self._data(id=str(aid), version=self._version(reg), name="Y"))
        self.assertEqual(errors, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})
        self.assertEqual(self.agd.get(aid)["name"], "Mudou por outro")
        self.assertEqual(self._audits("UPDATE"), [])

    def test_sensivel_nao_reexibido_e_vazio_mantem_valor(self):
        # CR-003 P1: a versao do formulario tambem nao deriva da resposta sensivel.
        aid0, _e = self._save(answers={"data_ref": "2026-01-20", "modo_exec": "REAL", "documento_cliente": "tok-um-111"})
        v1 = self.svc.form(self.ctx["admin"], str(aid0))["rule"]["version"]
        reg = self.agd.get(aid0)
        swapped = json.loads(reg["params_json"])
        swapped["documento_cliente"] = "tok-dois-222"
        self.assertEqual(svc_mod.version(dict(reg, params_json=json.dumps(swapped)), frozenset(["documento_cliente"])), v1)
        self.assertNotEqual(svc_mod.version(reg), v1)
        aid, errors = self._save(answers={"data_ref": "2026-01-20", "modo_exec": "REAL", "documento_cliente": SECRET})
        self.assertEqual(errors, {})
        date = self.svc.form(self.ctx["admin"], str(aid))
        field = [c for c in date["form"]["fields"] if c["code"] == "documento_cliente"][0]
        self.assertTrue(field["kept"])
        self.assertIsNone(field["value"])
        self.assertNotIn(SECRET, json.dumps(date, default=str))
        not_sensitive = [c for c in date["form"]["fields"] if c["code"] == "modo_exec"][0]
        self.assertEqual(not_sensitive["value"], "REAL")
        self.assertFalse(not_sensitive["kept"])

        _id, errors = self._edit(aid, run_time="05:00",
                                  respostas={"data_ref": "2026-01-20", "modo_exec": "REAL", "documento_cliente": ""})
        self.assertEqual(errors, {})
        self.assertEqual(json.loads(self.agd.get(aid)["params_json"])["documento_cliente"], SECRET)
        _id, errors = self._edit(aid, answers={"data_ref": "2026-01-20", "modo_exec": "REAL",
                                                  "documento_cliente": "outro-token-99"})
        self.assertEqual(json.loads(self.agd.get(aid)["params_json"])["documento_cliente"], "outro-token-99")
        for aud in self._audits():
            self.assertNotIn(SECRET, aud["detail"])
            self.assertNotIn("outro-token-99", aud["detail"])
        # A auditoria lista do mais novo para o mais antigo.
        self.assertIn(u"documento_cliente=%s (alterado)" % svc_mod.MASK, self._audits("UPDATE")[0]["detail"])


class TestAgenda(_Base):

    def test_cron_valido_fora_da_semana_nao_e_problema(self):
        aid, errors = self._save(recurrence_type="CRON", cron_expression="0 0 1 12 *")
        self.assertEqual(errors, {})
        agenda = self.svc.agenda(self.ctx["admin"])
        self.assertFalse(any(item["rule_id"] == aid for item in agenda["problems"]))

    """CR-004 U6 (README §7.7)."""

    def _rule(self, **fields):
        base = {"name": "Agenda teste", "script_id": 1, "environment": "HOMOLOGACAO", "user_id": 1, "priority": 2,
                "recurrence_type": "DAILY", "run_time": "03:00", "params_json": "{}",
                "start_date": datetime.datetime(2026, 1, 1, 0, 0),
                "next_run_at": datetime.datetime(2026, 1, 16, 3, 0)}
        base.update(fields)
        return self.agd.insert(base, actor="teste")["id"]

    def _items(self, date, rule_id):
        return [o for d in date["days"] for o in d["items"] if o["rule_id"] == rule_id]

    def test_diaria_sete_dias_com_rotulos(self):
        rid = self._rule()
        date = self.svc.agenda(self.ctx["admin"])
        items = self._items(date, rid)
        self.assertEqual(len(items), 7)  # 16/01 a 22/01: ate o fim do 7o dia seguinte a 15/01
        labels = [d["label"] for d in date["days"] if any(o["rule_id"] == rid for o in d["items"])]
        self.assertEqual(labels[0], u"Amanhã")
        self.assertTrue(labels[1].startswith(u"sábado, 17/01"))

    def test_cron_a_cada_minuto_limitado_a_20_com_mais(self):
        rid = self._rule(recurrence_type="CRON", run_time=None, cron_expression="* * * * *",
                          next_run_at=datetime.datetime(2026, 1, 15, 10, 1))
        items = self._items(self.svc.agenda(self.ctx["admin"]), rid)
        self.assertEqual(len(items), svc_mod.AGENDA_PER_RULE)
        self.assertGreater(items[-1]["more"], 0)

    def test_atrasada_pausada_e_escopo(self):
        late = self._rule(next_run_at=datetime.datetime(2026, 1, 15, 3, 0))
        paused = self._rule(active="N", pause_reason="MANUAL")
        in_prod = self._rule(environment="PRODUCAO")
        date = self.svc.agenda(self.ctx["admin"])
        self.assertIn(late, [a["rule_id"] for a in date["delayed"]])
        self.assertFalse(self._items(date, paused))
        self.assertTrue(self._items(date, in_prod))
        # op.hml nao enxerga PRODUCAO (README §7.6, lista por escopo).
        self.assertFalse(self._items(self.svc.agenda(self.ctx["op.hml"]), in_prod))

    def test_exige_cad_agendamentos(self):
        with self.assertRaises(AccessDenied):
            self.svc.agenda(self.ctx["consulta"])


class TestPauseResume(_Base):

    def test_falha_de_rbac_nao_retoma_nem_audita(self):
        aid, errors = self._save()
        self.assertEqual(errors, {})
        self.svc.pause(self.ctx["admin"], IP, str(aid))
        before = self.agd.get(aid)
        audits = self._audits()
        with mock.patch.object(self.rbac, "matrix_get", side_effect=RuntimeError("indisponivel")):
            with self.assertRaises(RuntimeError):
                self.svc.resume(self.ctx["admin"], IP, str(aid))
        self.assertEqual(self.agd.get(aid), before)
        self.assertEqual(self._audits(), audits)


    def test_pausar_e_retomar_com_recalculo(self):
        aid, _errors = self._save()
        self.svc.pause(self.ctx["admin"], IP, str(aid))
        reg = self.agd.get(aid)
        self.assertEqual((reg["active"], reg["pause_reason"]), ("N", "MANUAL"))
        pauses = self._audits("SCHEDULE_PAUSE")
        self.assertEqual(len(pauses), 1)
        self.assertEqual((pauses[0]["actor"], pauses[0]["source_ip"]), ("admin", IP))
        self.assertIn(u"pause_reason: (vazio)%sMANUAL" % ARROW, pauses[0]["detail"])

        self.now = datetime.datetime(2026, 1, 20, 4, 0, 0, 999)
        self.svc.resume(self.ctx["admin"], IP, str(aid))
        reg = self.agd.get(aid)
        self.assertEqual((reg["active"], reg["pause_reason"]), ("Y", None))
        self.assertEqual(reg["next_run_at"], datetime.datetime(2026, 1, 21, 3, 0))
        resumed = self._audits("UPDATE")
        self.assertEqual(len(resumed), 1)
        self.assertIn(u"active: N%sY" % ARROW, resumed[0]["detail"])
        self.assertIn(u"21/01/2026 03:00", resumed[0]["detail"])

    def test_pausar_ja_pausada_e_retomar_ativa(self):
        with self.assertRaises(OperationDenied):
            self.svc.pause(self.ctx["admin"], IP, "5")
        with self.assertRaises(OperationDenied):
            self.svc.resume(self.ctx["admin"], IP, "2")
        self.assertEqual(self._audits(), [])

    def test_pausa_otimista(self):
        aid, _errors = self._save()
        original = self.agd.pause

        def pausar_com_corrida(id, reason, old_date=None, audit=None):
            self.agd.update(id, {"next_run_at": datetime.datetime(2026, 1, 17, 3, 0)}, actor="teste")
            return original(id, reason, old_date=old_date, audit=audit)

        with mock.patch.object(self.agd, "pause", side_effect=pausar_com_corrida):
            with self.assertRaises(RepoConflict):
                self.svc.pause(self.ctx["admin"], IP, str(aid))
        self.assertEqual(self.agd.get(aid)["active"], "Y")
        self.assertEqual(self._audits("SCHEDULE_PAUSE"), [])

    def test_retomar_revalida_permissao(self):
        aid, _errors = self._save(script_id="4", answers={})
        self.svc.pause(self.ctx["admin"], IP, str(aid))
        with self.assertRaises(OperationDenied) as cm:
            self.svc.resume(self.ctx["op.prod"], IP, str(aid))
        self.assertEqual(cm.exception.message, svc_mod.MSG_NO_PERMISSION)
        self.assertEqual(self.agd.get(aid)["active"], "N")

    def test_retomar_sem_proxima_execucao(self):
        aid, _errors = self._save(recurrence_type="ONCE", start_date="2026-01-16T08:00")
        self.svc.pause(self.ctx["admin"], IP, str(aid))
        self.now = datetime.datetime(2026, 1, 17, 0, 0)
        with self.assertRaises(OperationDenied) as cm:
            self.svc.resume(self.ctx["admin"], IP, str(aid))
        self.assertEqual(cm.exception.message, svc_mod.MSG_RESUME_NO_NEXT_RUN)
        self.assertEqual(self.agd.get(aid)["active"], "N")

    def test_retomar_reavalia_usuario_responsavel_inativo(self):
        aid, _errors = self._save(login="op.hml", script_id="1",
                                   respostas={"data_ref": "2026-01-20", "modo_exec": "SIMULACAO"})
        self.svc.pause(self.ctx["admin"], IP, str(aid))
        users = repo_factory.get("users")
        users.update(3, {"active": "N"}, actor="teste")
        with self.assertRaises(OperationDenied) as cm:
            self.svc.resume(self.ctx["admin"], IP, str(aid))
        self.assertIn(svc_mod.PAUSE_REASONS["USER_INACTIVE"], cm.exception.message)
        self.assertIn(svc_mod.MSG_RESUME_GUIDANCE, cm.exception.message)

    def test_retomar_reavalia_script_inativo(self):
        aid, _errors = self._save(script_id="1", answers={"data_ref": "2026-01-20", "modo_exec": "SIMULACAO"})
        self.svc.pause(self.ctx["admin"], IP, str(aid))
        self.catalog.scripts_update(1, {"active": "N"}, actor="teste")
        with self.assertRaises(OperationDenied) as cm:
            self.svc.resume(self.ctx["admin"], IP, str(aid))
        self.assertIn(svc_mod.PAUSE_REASONS["SCRIPT_INACTIVE"], cm.exception.message)

    def test_retomar_reavalia_ambiente_inativo(self):
        aid, _errors = self._save(environment="HOMOLOGACAO", script_id="1",
                                   respostas={"data_ref": "2026-01-20", "modo_exec": "SIMULACAO"})
        self.svc.pause(self.ctx["admin"], IP, str(aid))
        self.catalog.environments_update(2, {"active": "N"}, actor="teste")
        with self.assertRaises(OperationDenied) as cm:
            self.svc.resume(self.ctx["admin"], IP, str(aid))
        self.assertIn(svc_mod.PAUSE_REASONS["ENVIRONMENT_INACTIVE"], cm.exception.message)

    def test_retomar_reavalia_parametros_invalidos(self):
        aid, _errors = self._save(script_id="1", answers={"data_ref": "2026-01-20", "modo_exec": "SIMULACAO"})
        self.svc.pause(self.ctx["admin"], IP, str(aid))
        self.agd.update(aid, {"params_json": json.dumps({"data_ref": "data-invalida"})}, actor="teste")
        with self.assertRaises(OperationDenied) as cm:
            self.svc.resume(self.ctx["admin"], IP, str(aid))
        self.assertIn(svc_mod.PAUSE_REASONS["INVALID_PARAM"], cm.exception.message)


class TestNewRuleSteps(_Base):
    """CR-017c (README §7.6): escolha como no disparo; um ambiente so vai direto ao formulario."""

    def test_sem_script_lista_os_grupos(self):
        data = self.svc.form(self.ctx["admin"])
        self.assertEqual(data["step"], 1)
        self.assertTrue(data["groups"])

    def test_varios_ambientes_param_na_etapa_2(self):
        data = self.svc.form(self.ctx["admin"], script_id="1")
        self.assertEqual(data["step"], 2)
        self.assertFalse(data["single_environment"])
        self.assertEqual(sorted(a["name"] for a in data["environments"]), ["HOMOLOGACAO", "PRODUCAO"])
        self.assertEqual([a["production"] for a in data["environments"] if a["name"] == "PRODUCAO"], [True])

    def test_um_ambiente_so_vai_direto_ao_formulario(self):
        # op.hml so tem HOMOLOGACAO entre os ambientes do script 1.
        data = self.svc.form(self.ctx["op.hml"], script_id="1")
        self.assertEqual(data["step"], 3)
        self.assertTrue(data["single_environment"])
        self.assertEqual(data["form"]["environment"]["name"], "HOMOLOGACAO")


class TestPreviewList(_Base):

    def test_lista_no_escopo_com_colunas(self):
        res = self.svc.list(self.ctx["op.hml"], {}, 1, 20)
        self.assertEqual(sorted(i["environment"] for i in res["items"]), ["HOMOLOGACAO", "HOMOLOGACAO"])
        all_value = self.svc.list(self.ctx["admin"], {}, 1, 20)
        self.assertEqual(all_value["total"], 5)
        paused = [i for i in all_value["items"] if i["id"] == 5][0]
        self.assertEqual((paused["state"], paused["reason"]), (u"Pausado", u"Pausado manualmente"))
        self.assertEqual(paused["cron_expression"], "0 */4 * * *")
        self.assertTrue(paused["recurrence"].startswith(u"A cada"))
        self.assertEqual(paused["next_run_at"], "-")
        self.assertEqual(paused["last_ticket_id"], 35)
        weekly = [i for i in all_value["items"] if i["id"] == 3][0]
        self.assertEqual(weekly["recurrence"], u"Às 04:00, seg, qua, sex")
        self.assertEqual(weekly["responsible"], "admin")
        self.assertEqual(weekly["script"], "relatorio_mensal")
        self.assertEqual([i for i in all_value["items"] if i["id"] == 4][0]["responsible"], "op.hml")

    def test_lista_filtros(self):
        filters = svc_mod.normalize_filters({"environment": "producao", "active": "N", "name": " Limpeza "})
        self.assertEqual(filters, {"environment": "PRODUCAO", "active": "N", "name": "Limpeza"})
        res = self.svc.list(self.ctx["admin"], filters, 1, 20)
        self.assertEqual([i["id"] for i in res["items"]], [5])
        self.assertEqual(svc_mod.normalize_filters({"environment": "x;drop", "active": "Z"}), {})

    def test_previa_mensal_dia_31(self):
        res = self.svc.preview(self.ctx["admin"], {"recurrence_type": "MONTHLY", "run_time": "03:00",
                                                  "month_day": "31"})
        self.assertEqual(res["errors"], {})
        self.assertEqual(res["dates"], [u"sáb, 31/01/2026 03:00", u"sáb, 28/02/2026 03:00",
                                        u"ter, 31/03/2026 03:00", u"qui, 30/04/2026 03:00",
                                        u"dom, 31/05/2026 03:00"])
        self.now = datetime.datetime(2028, 1, 15, 10, 0)
        res = self.svc.preview(self.ctx["admin"], {"recurrence_type": "MONTHLY", "run_time": "03:00",
                                                  "month_day": "31"})
        self.assertIn(u"29/02/2028 03:00", res["dates"][1])

    def test_previa_cron_descricao_e_datas(self):
        res = self.svc.preview(self.ctx["admin"], {"recurrence_type": "CRON",
                                                  "cron_expression": "*/15 8-18 * * 1-5"})
        self.assertEqual(res["errors"], {})
        self.assertEqual(res["description"], u"A cada 15 minutos, das 08:00 às 18:59, de segunda a sexta")
        self.assertEqual(res["dates"], [u"qui, 15/01/2026 10:15", u"qui, 15/01/2026 10:30",
                                        u"qui, 15/01/2026 10:45", u"qui, 15/01/2026 11:00",
                                        u"qui, 15/01/2026 11:15"])
        # Sexta 18:50 -> pula o fim de semana.
        self.now = datetime.datetime(2026, 1, 16, 18, 50)
        res = self.svc.preview(self.ctx["admin"], {"recurrence_type": "CRON",
                                                  "cron_expression": "*/15 8-18 * * 1-5"})
        self.assertEqual(res["dates"][:2], [u"seg, 19/01/2026 08:00", u"seg, 19/01/2026 08:15"])

    def test_previa_com_erros(self):
        res = self.svc.preview(self.ctx["admin"], {"recurrence_type": "CRON", "cron_expression": "0 0 L * *"})
        self.assertEqual(res["dates"], [])
        self.assertIn("cron_expression", res["errors"])
        res = self.svc.preview(self.ctx["admin"], {"recurrence_type": "ONCE", "start_date": "2026-01-01T00:00"})
        self.assertEqual(res["errors"], {GENERAL_FIELD: svc_mod.MSG_NO_NEXT_RUN})
        res = self.svc.preview(self.ctx["admin"], {"recurrence_type": "ONCE", "start_date": "2026-03-01T09:00"})
        self.assertEqual(res["dates"], [u"dom, 01/03/2026 09:00"])
        self.assertEqual(res["description"], u"Uma vez, em 01/03/2026 09:00")

    def test_lista_aviso_sobreposicao(self):
        tid = self.tickets.create({"script_id": 1, "environment": "PRODUCAO", "requested_by": "admin",
                                  "submitted_params": "{}", "priority": 2, "status": "PENDING"},
                                 [], actor="admin")
        self.agd.update(1, {"last_ticket_id": tid}, actor="teste")
        res = self.svc.list(self.ctx["admin"], {}, 1, 20)
        item1 = [i for i in res["items"] if i["id"] == 1][0]
        self.assertIsNotNone(item1.get("warning"))
        self.assertIn(u"pode ser pulada", item1["warning"])
        self.assertIn(str(tid), item1["warning"])

    def test_agenda_aviso_e_problemas(self):
        aid_active, errors = self._save()
        self.assertEqual(errors, {})
        self.catalog.scripts_update(1, {"active": "N"}, actor="teste")
        date = self.svc.agenda(self.ctx["admin"])
        items_r1 = [i for day in date["days"] for i in day["items"] if i["rule_id"] == aid_active]
        self.assertTrue(items_r1)
        self.assertIn(u"Será pausada", items_r1[0].get("warning", ""))
        aid = self.agd.insert({"name": "CRON Problematico", "user_id": 1, "script_id": 1,
                                "environment": "HOMOLOGACAO", "recurrence_type": "CRON",
                                "cron_expression": "0 0 31 2 *", "priority": 2, "active": "Y",
                                "params_json": "{}"}, actor="teste")["id"]
        data2 = self.svc.agenda(self.ctx["admin"])
        problems = data2.get("problems", [])
        self.assertIn(aid, [p["rule_id"] for p in problems])

    def test_formulario_regra_pausada_pausa_aviso(self):
        aid, _errors = self._save(script_id="1", answers={"data_ref": "2026-01-20", "modo_exec": "SIMULACAO"})
        self.svc.pause(self.ctx["admin"], IP, str(aid))
        f = self.svc.form(self.ctx["admin"], str(aid))
        self.assertIsNotNone(f["rule"].get("pause_warning"))
        self.assertIn(u"Pausada", f["rule"]["pause_warning"])


class TestAuditInsert(_Base):

    def test_inclusao_auditada_sem_valor_sensivel(self):
        aid, _errors = self._save(answers={"data_ref": "2026-01-20", "modo_exec": "REAL", "documento_cliente": SECRET})
        inserts = self._audits("CREATE")
        self.assertEqual(len(inserts), 1)
        aud = inserts[0]
        self.assertEqual((aud["actor"], aud["source_ip"], aud["entity_id"]), ("admin", IP, aid))
        self.assertNotIn(SECRET, aud["detail"])
        self.assertIn(u"documento_cliente=%s" % svc_mod.MASK, aud["detail"])
        self.assertIn(u"user_id: 1", aud["detail"])
        self.assertLessEqual(len(aud["detail"]), admin_crud.DETAIL_LIMIT)


if __name__ == "__main__":
    unittest.main()
