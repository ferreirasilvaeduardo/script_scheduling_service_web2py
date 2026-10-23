# -*- coding: utf-8 -*-
"""Bateria de testes de conformidade para contratos de repositorio e backend FAKE.

Valida requisitos do prompt F0.4, README §2.5 e AGENTS.md §4, §5.5, §7:
1. CRUD basico de todos os agregados;
2. Unicidade de UKs gerando RepoViolation;
3. CKs de connection com '@' gerando RepoViolation;
4. Imutabilidade de environments.name e usuarios.login;
5. Cascatas de associacao (matriz, script_param, homologacao);
6. request_cancel nos 3 retornos ('TERMINAL', 'CANCELADO', 'SINALIZADO');
7. Transicao concorrente perdida gerando RepoConflict; CKs, UPDATE condicional e auditoria de agendamentos;
8. perm_version incrementando em alteracoes de perfil, matriz e usuario;
9. Paginacao estavel e deterministica com desempate por id;
10. Escopo de environments na listagem de tickets;
11. repo_factory com trava de environment (sss_env != DEV com FAKE lanca RuntimeError);
12. repo_factory rejeita apenas o proximo agregado Oracle ainda nao implementado (F7.3 incremental);
13. Nenhum import repo_fake fora de repo_factory.py;
14. FAKE nao expos nenhum metodo publico alem dos definidos no contrato (paridade estrita);
15. Regressao fail-fast: repo_factory sem configuracao e FAKE com entrada nao numerica;
16. Colunas de registro (CR-006): inclusao, alteracao, actor required, rotina tecnica e vinculos por diferenca.
"""
import collections
import copy
import datetime
import os
import re
import time
import unittest
from unittest import mock

import _testenv  # noqa: F401
from gluon import current

import repo_factory
import sql_ident
from repo_schedules import RepoSchedules
from repo_agents import RepoAgents
from repo_audit import RepoAudit
from repo_catalog import RepoCatalog
from repo_errors import RepoConflict, RepoNotFound, RepoViolation
from repo_rbac import RepoRbac
from repo_tickets import RepoTickets
from repo_users import RepoUsers


class _Fixtures(object):
    """Dados proprios de um teste, criados pelos repositorios (sem depender do seed do FAKE).

    Os nomes levam um sufixo unico; os IDs criados ficam anotados por entidade, na ordem de
    remocao (tickets antes de agendamentos, usuarios antes de perfis, scripts antes de parametros).
    """

    ORDER = ("tickets", "schedules", "users", "profiles", "scripts", "parameters", "environments")

    def __init__(self, get_repo):
        self._r = get_repo
        self.suf = "%08d" % (int(time.time() * 1000000) % 100000000)
        self.actor = "tst" + self.suf
        self.created = collections.OrderedDict((ent, []) for ent in self.ORDER)
        self._scenario = None

    def note(self, entity, id):
        self.created[entity].append(id)
        return id

    def environment(self, label="A", **extra):
        data = dict({"name": "TST_%s_%s" % (self.suf, label), "description": "Ambiente de teste"}, **extra)
        env = self._r("catalog").environments_insert(data, actor=self.actor)
        self.note("environments", env["id"])
        return env

    def profile(self, label="P", **extra):
        prf = self._r("rbac").profiles_insert(dict({"name": "TST_%s_%s" % (self.suf, label), "is_admin": "N"}, **extra),
                                             actor=self.actor)
        self.note("profiles", prf["id"])
        return prf

    def usuario(self, profile_id, label="u", **extra):
        data = dict({"login": "tst.%s.%s" % (self.suf, label), "name": "Usuario de teste",
                      "password_hash": "pbkdf2_sha256$1$00$00", "profile_id": profile_id, "active": "Y"}, **extra)
        u = self._r("users").insert(data, actor=self.actor)
        self.note("users", u["id"])
        return u

    def parameter(self, label="a", **extra):
        data = dict({"code": "tst_%s_%s" % (self.suf, label), "label": "Parametro %s" % label,
                      "component_type": "TEXT", "param_flag": "--tst%s%s" % (self.suf, label)}, **extra)
        prm = self._r("catalog").parameters_insert(data, actor=self.actor)
        self.note("parameters", prm["id"])
        return prm

    def script(self, label="s", **extra):
        data = dict({"name": "tst_scr_%s_%s" % (self.suf, label), "interpreter": "SH", "param_type": "NAMED",
                      "path_file": "/opt/tst/%s_%s.sh" % (self.suf, label)}, **extra)
        scr = self._r("catalog").scripts_insert(data, actor=self.actor)
        self.note("scripts", scr["id"])
        return scr

    def schedule(self, script_id, environment, user_id, label="r", **extra):
        data = dict({"name": "TST %s %s" % (self.suf, label), "script_id": script_id, "environment": environment,
                      "user_id": user_id, "priority": 2, "recurrence_type": "DAILY",
                      "run_time": "03:00", "params_json": "{}",
                      "start_date": datetime.datetime(2026, 1, 15, 10, 0),
                      "next_run_at": datetime.datetime(2030, 1, 16, 3, 0)}, **extra)
        rule = self._r("schedules").insert(data, actor=self.actor)
        self.note("schedules", rule["id"])
        return rule

    def ticket(self, answers=(), actor=None, **data):
        tid = self._r("tickets").create(data, list(answers), actor=actor)
        return self.note("tickets", tid)

    def scenario(self):
        """Dois ambientes, um perfil comum com dois usuarios, dois parametros com flag e um script
        NOMEADO homologado no primeiro ambiente, com os dois parametros vinculados."""
        if self._scenario is None:
            c = {}
            c["amb1"], c["amb2"] = self.environment("A"), self.environment("B")
            c["profile"] = self.profile("P")
            c["u1"], c["u2"] = self.usuario(c["profile"]["id"], "u1"), self.usuario(c["profile"]["id"], "u2")
            c["prm_a"], c["prm_b"] = self.parameter("a"), self.parameter("b")
            c["scr"] = self.script("s")
            cat = self._r("catalog")
            cat.homologation_save(c["scr"]["id"], [c["amb1"]["id"]], actor=self.actor)
            cat.script_params_save(c["scr"]["id"], [
                {"parameter_id": c["prm_a"]["id"], "sort_order": 1, "required": "Y"},
                {"parameter_id": c["prm_b"]["id"], "sort_order": 2, "required": "N"}], actor=self.actor)
            c["login"] = c["u1"]["login"]
            c["ticket_base"] = {"script_id": c["scr"]["id"], "environment": c["amb1"]["name"],
                                "requested_by": c["login"], "status": "PENDING", "priority": 2}
            self._scenario = c
        return self._scenario


class BaseRepoContractTest(object):
    """Bateria agnostica a backend, executada contra FAKE e ORACLE com dados proprios de cada teste.

    Nenhum teste usa nomes ou IDs do seed nem altera cadastros que nao criou. As auditorias sao
    conferidas pela entidade e pelo id do proprio registro (imunes a outros usos do banco) e os nomes
    de constraint seguem o prefixo configurado.
    """

    @property
    def m(self):
        if getattr(self, "_fixtures", None) is None:
            self._fixtures = _Fixtures(self.obter_repo)
        return self._fixtures

    def cn(self, kind, entity, suffix):
        """Nome da constraint/indice/trigger com o prefixo do repositorio em uso (FAKE: tbsss_)."""
        prefix = getattr(self.obter_repo("catalog"), "_prefixo", None) or "tbsss_"
        return "%s_%s%s_%s" % (kind, prefix, sql_ident.TABLES[entity]["abrev"], suffix)

    def aud_total(self, action, entity, entity_id):
        return self.obter_repo("audit").list(
            filters={"action": action, "entity": entity, "entity_id": entity_id}, page=1, size=1)["total"]

    def aud_last(self, action, entity, entity_id):
        return self.obter_repo("audit").list(
            filters={"action": action, "entity": entity, "entity_id": entity_id}, page=1, size=1)["items"][0]

    def test_ocorrencia_duplicada_recusada_sem_alterar_ticket(self):
        c = self.m.scenario()
        tickets = self.obter_repo("tickets")
        rule = self.m.schedule(c["scr"]["id"], c["amb1"]["name"], c["u1"]["id"])
        data = {"script_id": c["scr"]["id"], "environment": c["amb1"]["name"], "requested_by": c["login"],
                 "schedule_id": rule["id"], "scheduled_at": datetime.datetime(2030, 1, 2)}
        first_id = self.m.ticket(actor="teste", **data)
        first = tickets.get(first_id)
        with self.assertRaises(RepoViolation) as error:
            self.m.ticket(actor="teste", **data)
        self.assertEqual(error.exception.constraint, self.cn("ix", "tickets", "occur"))
        self.assertEqual(tickets.get(first["id"]), first)
        self.m.ticket(actor="teste", **dict(data, scheduled_at=datetime.datetime(2030, 1, 3)))
        self.m.ticket(actor="teste", **dict(data, schedule_id=None))
        self.m.ticket(actor="teste", **dict(data, schedule_id=None))

    def test_01_crud_ambientes(self):
        cat = self.obter_repo("catalog")
        env = self.m.environment("CRUD", connection="db-teste.local:1521/svc")
        self.assertIsNotNone(env.get("id"))
        self.assertEqual(cat.environments_get(env["id"])["name"], env["name"])
        changed = cat.environments_update(env["id"], {"description": "Descricao alterada", "active": "N"}, actor="teste")
        self.assertEqual((changed["description"], changed["active"]), ("Descricao alterada", "N"))
        items = cat.environments_list(filters={"name": env["name"]})
        self.assertEqual(items["total"], 1)
        self.assertEqual(items["items"][0]["id"], env["id"])

    def test_02_uk_duplicada_ambiente_perfil_script_usuario(self):
        c = self.m.scenario()
        cat, rbac, usr = self.obter_repo("catalog"), self.obter_repo("rbac"), self.obter_repo("users")
        with self.assertRaises(RepoViolation) as ctx:
            cat.environments_insert({"name": c["amb1"]["name"], "connection": "db-prod2.local:1521/svc"}, actor="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("uk", "environments", "name"))
        with self.assertRaises(RepoViolation) as ctx:
            rbac.profiles_insert({"name": c["profile"]["name"], "is_admin": "N"}, actor="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("uk", "profiles", "name"))
        with self.assertRaises(RepoViolation) as ctx:
            cat.scripts_insert({"name": c["scr"]["name"], "interpreter": "PYTHON3",
                                 "path_file": "/opt/tst/dup.py"}, actor="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("uk", "scripts", "name"))
        # CK de path_file (CR-005 R-g): absoluto, sem '..', '//' nem '\'.
        with self.assertRaises(RepoViolation) as ctx:
            cat.scripts_insert({"name": "tst_%s_path" % self.m.suf, "interpreter": "PYTHON3",
                                 "path_file": "x.py"}, actor="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("ck", "scripts", "path"))
        with self.assertRaises(RepoViolation) as ctx:
            usr.insert({"login": c["login"], "name": "Duplicado", "password_hash": "h",
                         "profile_id": c["profile"]["id"]}, actor="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("uk", "users", "login"))

    def test_03_ck_conexao_com_arroba(self):
        cat = self.obter_repo("catalog")
        with self.assertRaises(RepoViolation) as ctx:
            cat.environments_insert({"name": "TST_%s_ARROBA" % self.m.suf, "connection": "usr:pwd@host:1521/svc"},
                                  actor="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("ck", "environments", "connection"))
        env = self.m.environment("ARR")
        with self.assertRaises(RepoViolation) as ctx:
            cat.environments_update(env["id"], {"connection": "app@host/svc"}, actor="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("ck", "environments", "connection"))

    def test_03c_contagem_da_auditoria_igual_ao_iterador(self):
        # CR-018c: count tem o filtro e o teto do iterate, sem ler as linhas (exportacao CSV).
        cat, aud = self.obter_repo("catalog"), self.obter_repo("audit")
        env = self.m.environment("CNT")
        for n in range(3):
            cat.environments_update(env["id"], {"description": "contagem %d" % n},
                                    audit={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "x"})
        filters = {"entity": "tbsss_environments", "entity_id": env["id"]}
        self.assertEqual(aud.count(filters=filters), len(list(aud.iterate(filters=filters))))
        self.assertEqual(aud.count(filters=filters), 3)
        self.assertEqual(aud.count(filters=filters, limit=2), 2)
        self.assertEqual(aud.count(filters=dict(filters, action="CREATE")), 0)

    def test_03b_ambiente_producao(self):
        # CR-017: is_production nasce 'N', aceita 'Y' na inclusao e na alteracao; outro valor viola a CK.
        cat = self.obter_repo("catalog")
        env = self.m.environment("PRD0")
        self.assertEqual(cat.environments_get(env["id"])["is_production"], "N")
        prod = cat.environments_insert({"name": "TST_%s_PRD1" % self.m.suf, "is_production": "Y"}, actor="teste")
        self.m.note("environments", prod["id"])
        self.assertEqual(cat.environments_get(prod["id"])["is_production"], "Y")
        changed = cat.environments_update(prod["id"], {"is_production": "N"}, actor="teste")
        self.assertEqual(changed["is_production"], "N")
        with self.assertRaises(RepoViolation) as ctx:
            cat.environments_update(prod["id"], {"is_production": "S"}, actor="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("ck", "environments", "prod"))

    def test_04_imutabilidade_nome_ambiente_e_login_usuario(self):
        c = self.m.scenario()
        with self.assertRaises(RepoViolation) as ctx:
            self.obter_repo("catalog").environments_update(c["amb1"]["id"], {"name": "TST_%s_NOVO" % self.m.suf},
                                                          actor="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("tr", "environments", "bu"))
        with self.assertRaises(RepoViolation) as ctx:
            self.obter_repo("users").update(c["u1"]["id"], {"login": "tst.%s.novo" % self.m.suf}, actor="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("tr", "users", "bu"))

    def test_04b_ambiente_alteracao_condicional_e_auditoria_na_mesma_operacao(self):
        cat = self.obter_repo("catalog")
        env = self.m.environment("AUD")
        read = {"description": env["description"], "connection": env["connection"], "active": env["active"]}
        changed = cat.environments_update(env["id"], {"description": "Contrato"}, expected=read,
                                         audit={"actor": "admin", "ip": "10.0.0.1", "action": "UPDATE",
                                                    "detail": "description: x -> Contrato"})
        self.assertEqual(changed["description"], "Contrato")
        self.assertEqual(self.aud_total("UPDATE", "tbsss_environments", env["id"]), 1)
        self.assertEqual(self.aud_last("UPDATE", "tbsss_environments", env["id"])["actor"], "admin")

        # 'lido' ficou obsoleto: o UPDATE condicional perde, nada muda e nada e auditado.
        with self.assertRaises(RepoConflict):
            cat.environments_update(env["id"], {"description": "Perdedor"}, expected=read,
                                  audit={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "x"})
        self.assertEqual(cat.environments_get(env["id"])["description"], "Contrato")
        # Violacao tambem nao grava auditoria nem altera colunas parcialmente.
        with self.assertRaises(RepoViolation):
            cat.environments_update(env["id"], {"description": "Parcial", "connection": "a@b"},
                                  audit={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "x"})
        self.assertEqual(cat.environments_get(env["id"])["description"], "Contrato")
        self.assertEqual(self.aud_total("UPDATE", "tbsss_environments", env["id"]), 1)

        new = cat.environments_insert({"name": "TST_%s_CAUD" % self.m.suf, "connection": "ALIAS"},
                                     audit={"actor": "admin", "ip": None, "action": "CREATE", "detail": "y"})
        self.m.note("environments", new["id"])
        self.assertEqual(self.aud_total("CREATE", "tbsss_environments", new["id"]), 1)

    def test_04c_perfil_conflito_e_matriz_condicional(self):
        """Conflito sem incremento e matriz condicional (o ultimo admin fica em TestLastAdmin*)."""
        c = self.m.scenario()
        rbac = self.obter_repo("rbac")
        prf = c["profile"]
        feature_ids = [f["id"] for f in rbac.features_list()][:2]
        rbac.matrix_save(prf["id"], feature_ids, [c["amb1"]["id"]], [c["scr"]["id"]], actor="teste")
        current = rbac.profiles_get(prf["id"])
        version = current["perm_version"]

        with self.assertRaises(RepoConflict):
            rbac.profiles_update(prf["id"], {"description": "x"}, expected={"description": "outra"}, actor="teste")
        self.assertEqual(rbac.profiles_get(prf["id"])["perm_version"], version)

        matrix = rbac.matrix_get(prf["id"])
        with self.assertRaises(RepoConflict):
            rbac.matrix_save(prf["id"], [], [], [], expected_perm_version=version + 7, actor="teste")
        with self.assertRaises(RepoViolation):
            rbac.matrix_save(prf["id"], [999999], matrix["ambs"], matrix["scrs"], expected_perm_version=version,
                               actor="teste")
        self.assertEqual(rbac.matrix_get(prf["id"]), matrix)
        self.assertEqual(rbac.profiles_get(prf["id"])["perm_version"], version)

        new = rbac.matrix_save(prf["id"], [], matrix["ambs"], matrix["scrs"], expected_perm_version=version,
                                  audit={"actor": "admin", "ip": None, "action": "PERM_UPDATE", "detail": "-VIEW_LOGS"})
        self.assertEqual(new["funcs"], [])
        self.assertEqual(rbac.profiles_get(prf["id"])["perm_version"], version + 1)
        self.assertEqual(self.aud_total("PERM_UPDATE", "tbsss_profiles", prf["id"]), 1)

    def test_04d_usuario_conflito_auditoria_login_e_filtro_bloqueio(self):
        """Conflito, auditoria, login e filtro de bloqueio (o ultimo admin fica em TestLastAdmin*)."""
        c = self.m.scenario()
        usr = self.obter_repo("users")
        target = c["u2"]
        with self.assertRaises(RepoConflict):
            usr.update(target["id"], {"name": "X"}, expected={"name": "outro"}, actor="teste")
        self.assertEqual(usr.get_by_id(target["id"])["name"], target["name"])

        usr.update(target["id"], {"name": "Consulta Contrato"}, expected={"name": target["name"]},
                    audit={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "name"})
        usr.set_password(target["id"], "pbkdf2_sha256$1$00$00",
                          audit={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "senha redefinida"})
        usr.unlock(target["id"], audit={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "d"})
        self.assertEqual(self.aud_total("UPDATE", "tbsss_users", target["id"]), 3)

        # CR-003 P3: falha/sucesso de login com auditoria na mesma operacao e bloqueio pelo relogio do banco.
        start = usr.now()
        reg = usr.register_login_failure(target["login"], lockout_s=60, audit=[
            {"actor": target["login"], "ip": None, "action": "LOGIN_FAILED", "detail": "f"},
            {"actor": target["login"], "ip": None, "action": "LOGIN_LOCKED", "detail": "b"}])
        self.assertGreaterEqual(reg["locked_until"], start + datetime.timedelta(seconds=60))
        self.assertEqual(self.aud_total("LOGIN_FAILED", "tbsss_users", target["id"]), 1)
        self.assertEqual(self.aud_total("LOGIN_LOCKED", "tbsss_users", target["id"]), 1)
        reg = usr.register_login_success(target["login"], new_hash="pbkdf2_sha256$2$00$00",
                                          audit={"actor": target["login"], "ip": None, "action": "LOGIN_OK", "detail": "ok"})
        self.assertEqual((reg["failed_attempts"], reg["locked_until"]), (0, None))
        self.assertEqual(reg["password_hash"], "pbkdf2_sha256$2$00$00")
        self.assertGreaterEqual(reg["last_login_at"], start)
        self.assertEqual(reg["last_login_at"].microsecond, 0)

        usr.update(target["id"], {"locked_until": datetime.datetime(2999, 1, 1)}, actor="teste")
        locked = usr.list(filters={"locked_at": datetime.datetime(2998, 1, 1)}, page=1, size=200)
        self.assertIn(target["login"], [u["login"] for u in locked["items"]])
        self.assertNotIn(c["u1"]["login"], [u["login"] for u in locked["items"]])

    def test_04e_parametro_dependencias_atomicas_qtd_scripts_e_auditoria(self):
        c = self.m.scenario()
        cat = self.obter_repo("catalog")
        prm = cat.parameters_list(filters={"code": c["prm_a"]["code"]})["items"][0]
        self.assertEqual(prm["script_count"], len(cat.parameter_links(prm["id"])))
        self.assertEqual(prm["script_count"], 1)
        for data, constraint in (({"component_type": "NUMBER"}, "sss_prm_tipo_vinculado"),
                                  ({"param_flag": "--outra-flag"}, "sss_prm_flag_nomeado"),
                                  ({"active": "N"}, "sss_prm_vinculo_ativo")):
            with self.assertRaises(RepoViolation) as ctx:
                cat.parameters_update(prm["id"], dict(data, label="Nao deve gravar"), actor="teste")
            self.assertEqual(ctx.exception.constraint, constraint)
        self.assertEqual(cat.parameters_get(prm["id"])["label"], prm["label"])
        with self.assertRaises(RepoConflict):
            cat.parameters_update(prm["id"], {"label": "x"}, expected={"label": "outro"}, actor="teste")

        new = cat.parameters_insert({"code": "tst_%s_novo" % self.m.suf, "label": "Contrato",
                                       "component_type": "TEXT"},
                                      audit={"actor": "admin", "ip": None, "action": "CREATE", "detail": "x"})
        self.m.note("parameters", new["id"])
        self.assertEqual(self.aud_total("CREATE", "tbsss_parameters", new["id"]), 1)
        # Sem vinculo, tipo e flag mudam e a desativacao passa.
        changed = cat.parameters_update(new["id"], {"component_type": "NUMBER", "param_flag": "--n",
                                                       "active": "N"}, actor="teste")
        self.assertEqual((changed["component_type"], changed["param_flag"], changed["active"]),
                         ("NUMBER", "--n", "N"))

    def test_04f_script_regras_de_tipo_param_homologacao_e_vinculos_condicionais(self):
        c = self.m.scenario()
        cat = self.obter_repo("catalog")
        scr = cat.scripts_list(filters={"name": c["scr"]["name"]})["items"][0]
        self.assertEqual(scr["param_count"], len(cat.script_params_get(scr["id"])))
        self.assertEqual(scr["homologated_environments"], [c["amb1"]["name"]])

        with self.assertRaises(RepoViolation) as ctx:
            cat.scripts_update(scr["id"], {"param_type": "NONE", "description": "Nao grava"}, actor="teste")
        self.assertEqual(ctx.exception.constraint, "sss_scr_nenhum_vinculado")
        self.assertEqual(cat.scripts_get(scr["id"])["param_type"], "NAMED")
        with self.assertRaises(RepoConflict):
            cat.scripts_update(scr["id"], {"description": "x"}, expected={"description": "outra"}, actor="teste")

        without_flag = self.m.parameter("semflag", param_flag=None)
        with self.assertRaises(RepoViolation) as ctx:
            cat.script_params_save(scr["id"], [{"parameter_id": without_flag["id"], "sort_order": 1, "required": "N"}],
                                     actor="teste")
        self.assertEqual(ctx.exception.constraint, "sss_scr_nomeado_sem_flag")

        homolog = cat.homologation_get(scr["id"])
        with self.assertRaises(RepoConflict):
            cat.homologation_save(scr["id"], [], expected=homolog + [999], actor="teste")
        cat.homologation_save(scr["id"], homolog, expected=homolog,
                               audit={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "h"})
        link = cat.script_params_get(scr["id"])
        read = [(v["parameter_id"], v["sort_order"], v["required"], v.get("default_value_override")) for v in link]
        with self.assertRaises(RepoConflict):
            cat.script_params_save(scr["id"], [], expected=read[1:], actor="teste")
        cat.script_params_save(scr["id"], [dict(parameter_id=x[0], sort_order=x[1], required=x[2],
                                                  default_value_override=x[3]) for x in read], expected=read,
                                 audit={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "v"})
        self.assertEqual(self.aud_total("UPDATE", "tbsss_scripts", scr["id"]), 2)

    def test_05_cascata_associacao(self):
        c = self.m.scenario()
        cat, rbac = self.obter_repo("catalog"), self.obter_repo("rbac")
        sid = c["scr"]["id"]
        cat.homologation_save(sid, [c["amb1"]["id"]], actor="teste")
        self.assertEqual(cat.homologation_get(sid), [c["amb1"]["id"]])
        cat.homologation_save(sid, [c["amb1"]["id"], c["amb2"]["id"]], actor="teste")
        self.assertEqual(sorted(cat.homologation_get(sid)), sorted([c["amb1"]["id"], c["amb2"]["id"]]))

        p = c["profile"]
        v_before = rbac.profiles_get(p["id"])["perm_version"]
        feature_ids = sorted(f["id"] for f in rbac.features_list())[:2]
        rbac.matrix_save(p["id"], features_ids=feature_ids, envs=[c["amb1"]["id"]], scrs=[sid], actor="teste")
        m = rbac.matrix_get(p["id"])
        self.assertEqual((sorted(m["funcs"]), m["ambs"], m["scrs"]), (feature_ids, [c["amb1"]["id"]], [sid]))
        self.assertGreater(rbac.profiles_get(p["id"])["perm_version"], v_before)

    def test_06_solicitar_cancelamento_nos_tres_retornos(self):
        c = self.m.scenario()
        tck = self.obter_repo("tickets")
        tid_pend = self.m.ticket(**c["ticket_base"])
        self.assertEqual(tck.request_cancel(tid_pend, "admin", "10.0.0.1"), "CANCELADO")
        t1 = tck.get(tid_pend)
        self.assertEqual((t1["status"], t1["cancel_requested"], t1["status_reason"]), ("CANCELLED", "Y", "CANCEL_USER"))
        self.assertEqual(tck.request_cancel(tid_pend, "admin", "10.0.0.1"), "TERMINAL")
        tid_run = self.m.ticket(**dict(c["ticket_base"], status="RUNNING"))
        self.assertEqual(tck.request_cancel(tid_run, "admin", "10.0.0.1"), "SINALIZADO")
        t3 = tck.get(tid_run)
        self.assertEqual((t3["status"], t3["cancel_requested"]), ("RUNNING", "Y"))

    def test_07_transicao_concorrente_perdida_gerando_repo_conflito(self):
        c = self.m.scenario()
        sch = self.obter_repo("schedules")
        rule = self.m.schedule(c["scr"]["id"], c["amb1"]["name"], c["u1"]["id"])
        date_correct = rule["next_run_at"]
        with self.assertRaises(RepoConflict):
            sch.pause(rule["id"], reason="MANUAL", old_date=date_correct + datetime.timedelta(days=10),
                       actor="teste")
        paused = sch.pause(rule["id"], reason="MANUAL", old_date=date_correct, actor="teste")
        self.assertEqual((paused["active"], paused["pause_reason"]), ("N", "MANUAL"))
        # Pausar uma regra ja pausada gera RepoConflict (CR-007 R-19).
        with self.assertRaises(RepoConflict):
            sch.pause(rule["id"], reason="MANUAL", old_date=date_correct, actor="teste")

    def test_06b_fks_e_limites_de_auditoria(self):
        """CR-003 P8 (README §2.5): FKs, UK de ticket_answer e limites da auditoria, sem gravacao parcial."""
        c = self.m.scenario()
        tck, sch, aud = self.obter_repo("tickets"), self.obter_repo("schedules"), self.obter_repo("audit")
        base = c["ticket_base"]
        mine = lambda: tck.list(filters={"requested_by": c["login"]}, page=1, size=1)["total"]  # noqa: E731
        total = mine()
        prm = c["prm_a"]["id"]
        cases = (
            (dict(base, script_id=999999999), [], self.cn("fk", "tickets", "scr")),
            (dict(base, environment="NAO_EXISTE_TST"), [], self.cn("fk", "tickets", "env")),
            (dict(base, requested_by="nao.existe.tst"), [], self.cn("fk", "tickets", "usr")),
            (base, [{"parameter_id": 999999999, "answer_value": "x"}], self.cn("fk", "ticket_answer", "prm")),
            (base, [{"parameter_id": prm, "answer_value": "a"}, {"parameter_id": prm, "answer_value": "b"}],
             self.cn("uk", "ticket_answer", "tck_prm")),
        )
        for ticket, answers, constraint in cases:
            with self.assertRaises(RepoViolation) as ctx:
                self.m.ticket(answers, **ticket)
            self.assertEqual(ctx.exception.constraint, constraint)
        self.assertEqual(mine(), total)

        for change, constraint in (({"script_id": 999999999}, self.cn("fk", "schedules", "scr")),
                                    ({"user_id": 999999999}, self.cn("fk", "schedules", "usr")),
                                    ({"environment": "NAO_EXISTE_TST"}, self.cn("fk", "schedules", "env"))):
            with self.assertRaises(RepoViolation) as ctx:
                self.m.schedule(**dict({"script_id": c["scr"]["id"], "environment": c["amb1"]["name"],
                                           "user_id": c["u1"]["id"]}, **change))
            self.assertEqual(ctx.exception.constraint, constraint)

        env_id = c["amb1"]["id"]
        for actor, detail in ((None, "x"), ("", "x"), ("a" * 41, "x"), ("admin", "d" * 1001)):
            with self.assertRaises(RepoViolation):
                aud.register(actor, None, "UPDATE", "tbsss_environments", env_id, detail)
        aud.register("a" * 40, None, "UPDATE", "tbsss_environments", env_id, "d" * 1000)

    def test_07b_agendamento_cks_condicional_e_auditoria_na_mesma_operacao(self):
        c = self.m.scenario()
        sch = self.obter_repo("schedules")
        start = datetime.datetime(2026, 1, 15, 10, 0)
        base = {"name": "TST %s CK" % self.m.suf, "script_id": c["scr"]["id"], "environment": c["amb1"]["name"],
                "user_id": c["u1"]["id"], "priority": 2, "recurrence_type": "DAILY", "run_time": "03:00",
                "params_json": "{}", "start_date": start, "next_run_at": datetime.datetime(2030, 1, 16, 3, 0)}
        ck = lambda s: self.cn("ck", "schedules", s)  # noqa: E731
        violations = [
            ({"recurrence_type": "ANUAL"}, ck("rtype")),
            ({"priority": 5}, ck("prio")),
            ({"active": "X"}, ck("active")),
            ({"recurrence_type": "MONTHLY", "month_day": 32}, ck("day")),
            ({"run_time": "24:00"}, ck("time")),
            ({"recurrence_type": "WEEKLY", "week_days": "1,8"}, ck("wday")),
            ({"end_date": start - datetime.timedelta(days=1)}, ck("end")),
            ({"pause_reason": "OUTRO"}, ck("pause")),
            ({"recurrence_type": "WEEKLY"}, ck("fields")),
            ({"recurrence_type": "CRON", "run_time": None}, ck("fields")),
        ]
        mine = lambda: sch.list(filters={"name": self.m.suf}, page=1, size=1)["total"]  # noqa: E731
        total_rules = mine()
        for extra, constraint in violations:
            with self.assertRaises(RepoViolation) as cm:
                sch.insert(dict(base, **extra),
                            audit={"actor": self.m.actor, "ip": None, "action": "CREATE", "detail": "x"})
            self.assertEqual(cm.exception.constraint, constraint, extra)
        self.assertEqual(mine(), total_rules)
        self.assertEqual(self.obter_repo("audit").list(
            filters={"action": "CREATE", "actor": self.m.actor}, page=1, size=1)["total"], 0)

        new = sch.insert(base, audit={"actor": "admin", "ip": "10.0.0.1", "action": "CREATE",
                                            "detail": "name: Contrato AGD"})
        self.m.note("schedules", new["id"])
        self.assertEqual(self.aud_last("CREATE", "tbsss_schedules", new["id"])["actor"], "admin")

        read = {"name": new["name"], "user_id": c["u1"]["id"], "next_run_at": new["next_run_at"]}
        changed = sch.update(new["id"], {"name": "TST %s CK2" % self.m.suf, "user_id": c["u2"]["id"]},
                               expected=read,
                               audit={"actor": "op.prod", "ip": None, "action": "UPDATE", "detail": "y"})
        self.assertEqual((changed["name"], changed["user_id"]), ("TST %s CK2" % self.m.suf, c["u2"]["id"]))
        self.assertEqual(self.aud_total("UPDATE", "tbsss_schedules", new["id"]), 1)
        with self.assertRaises(RepoConflict):
            sch.update(new["id"], {"name": "Perdedor"}, expected=read,
                        audit={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "z"})
        with self.assertRaises(RepoViolation):
            sch.update(new["id"], {"name": "Parcial", "recurrence_type": "MONTHLY"}, actor="teste")
        self.assertEqual(sch.get(new["id"])["name"], "TST %s CK2" % self.m.suf)
        self.assertEqual(self.aud_total("UPDATE", "tbsss_schedules", new["id"]), 1)

        sch.pause(new["id"], "MANUAL", old_date=new["next_run_at"],
                   audit={"actor": "admin", "ip": "10.0.0.2", "action": "SCHEDULE_PAUSE", "detail": "p"})
        pause = self.aud_last("SCHEDULE_PAUSE", "tbsss_schedules", new["id"])
        self.assertEqual((pause["actor"], pause["source_ip"]), ("admin", "10.0.0.2"))

        paused = {"active": "N", "pause_reason": "MANUAL", "next_run_at": new["next_run_at"]}
        new_value = datetime.datetime(2030, 1, 20, 3, 0)
        with self.assertRaises(RepoConflict):
            sch.resume(new["id"], new_value, expected=dict(paused, pause_reason="COMPLETED"),
                        audit={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "r"})
        self.assertEqual(sch.get(new["id"])["active"], "N")
        resumed = sch.resume(new["id"], new_value, expected=paused,
                               audit={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "r"})
        self.assertEqual((resumed["active"], resumed["pause_reason"], resumed["next_run_at"]), ("Y", None, new_value))
        self.assertEqual(self.aud_total("UPDATE", "tbsss_schedules", new["id"]), 2)

    def test_08_perm_versao_incrementando(self):
        c = self.m.scenario()
        rbac, usr = self.obter_repo("rbac"), self.obter_repo("users")
        p = c["profile"]
        v0 = rbac.profiles_get(p["id"])["perm_version"]
        rbac.profiles_update(p["id"], {"description": "Nova descricao"}, actor="teste")
        v1 = rbac.profiles_get(p["id"])["perm_version"]
        self.assertEqual(v1, v0 + 1)
        feature_ids = [f["id"] for f in rbac.features_list()][:1]
        rbac.matrix_save(p["id"], features_ids=feature_ids, envs=[c["amb1"]["id"]], scrs=[c["scr"]["id"]], actor="teste")
        v2 = rbac.profiles_get(p["id"])["perm_version"]
        self.assertEqual(v2, v1 + 1)
        usr.update(c["u1"]["id"], {"active": "N"}, actor="teste")
        self.assertGreaterEqual(rbac.profiles_get(p["id"])["perm_version"], v2 + 1)

    def test_09_paginacao_estavel_e_deterministica(self):
        c = self.m.scenario()
        tck = self.obter_repo("tickets")
        for _ in range(25):
            self.m.ticket(**c["ticket_base"])
        filters = {"script_id": c["scr"]["id"], "requested_by": c["login"]}
        pag1 = tck.list(filters=filters, page=1, size=10)
        pag2 = tck.list(filters=filters, page=2, size=10)
        self.assertEqual((pag1["page"], pag1["size"], pag1["total"]), (1, 10, 25))
        self.assertEqual((len(pag1["items"]), len(pag2["items"])), (10, 10))
        self.assertTrue({i["id"] for i in pag1["items"]}.isdisjoint({i["id"] for i in pag2["items"]}))
        order = [(i["created_at"], i["id"]) for i in pag1["items"] + pag2["items"]]
        self.assertEqual(order, sorted(order, reverse=True))
        self.assertEqual([i["id"] for i in pag1["items"]],
                         [i["id"] for i in tck.list(filters=filters, page=1, size=10)["items"]])

    def test_10_escopo_ambientes_na_listagem_tickets(self):
        c = self.m.scenario()
        tck = self.obter_repo("tickets")
        for _ in range(3):
            self.m.ticket(**c["ticket_base"])
        for _ in range(2):
            self.m.ticket(**dict(c["ticket_base"], environment=c["amb2"]["name"]))
        filters = {"script_id": c["scr"]["id"]}
        items_a = tck.list(filters=filters, environment_scope=[c["amb1"]["name"]], page=1, size=50)
        items_b = tck.list(filters=filters, environment_scope=[c["amb2"]["name"]], page=1, size=50)
        self.assertEqual({t["environment"] for t in items_a["items"]}, {c["amb1"]["name"]})
        self.assertEqual({t["environment"] for t in items_b["items"]}, {c["amb2"]["name"]})
        self.assertEqual((items_a["total"], items_b["total"]), (3, 2))
        self.assertEqual(tck.list(filters=filters, environment_scope=[], page=1, size=50)["total"], 0)

    def test_11_log_ler_incremental(self):
        c = self.m.scenario()
        tck = self.obter_repo("tickets")
        log = "".join("linha %02d do log\n" % i for i in range(10))
        tid = self.m.ticket(**dict(c["ticket_base"], status="RUNNING", log_output=log,
                                   started_at=datetime.datetime(2026, 1, 1, 8, 0)))
        text, next_off, terminal, truncated = tck.log_read(tid, offset=0, max_chars=20)
        self.assertEqual((text, next_off, terminal, truncated), (log[:20], 20, False, False))
        text2, next_off2, _, _ = tck.log_read(tid, offset=next_off, max_chars=20)
        self.assertEqual((text2, next_off2), (log[20:40], 40))

    # ------------------------------------------------------------------
    # Colunas de registro (CR-006, README §10, AGENTS §4.15)
    # ------------------------------------------------------------------

    def _check_insert(self, reg, actor):
        self.assertEqual(reg["created_by"], actor)
        self.assertIsNotNone(reg["created_at"])
        self.assertIsNone(reg["updated_at"])
        self.assertIsNone(reg["updated_by"])

    def _check_update(self, before, after_value, actor):
        self.assertEqual(after_value["updated_by"], actor)
        self.assertIsNotNone(after_value["updated_at"])
        self.assertGreaterEqual(after_value["updated_at"], after_value["created_at"])
        self.assertEqual((after_value["created_at"], after_value["created_by"]), (before["created_at"], before["created_by"]))

    def test_12_registro_inclusao_e_alteracao_nos_cadastros(self):
        c = self.m.scenario()
        cat, rbac, usr, sch = (self.obter_repo(n) for n in ("catalog", "rbac", "users", "schedules"))
        aud = {"actor": "carla", "ip": "10.0.0.9", "action": "UPDATE", "detail": "registro"}
        suf = self.m.suf

        env = cat.environments_insert({"name": "TST_%s_REG" % suf, "description": "d"}, actor="ana")
        self.m.note("environments", env["id"])
        self._check_insert(env, "ana")
        self._check_update(env, cat.environments_update(env["id"], {"description": "e"}, actor="bia"), "bia")
        self._check_update(env, cat.environments_update(env["id"], {"description": "f"}, audit=aud), "carla")
        self.assertEqual(cat.environments_get(env["id"])["updated_by"], "carla")

        scr = cat.scripts_insert({"name": "tst_%s_reg" % suf, "interpreter": "SH",
                                   "path_file": "/opt/tst/%s_reg.sh" % suf, "param_type": "NONE"}, actor="ana")
        self.m.note("scripts", scr["id"])
        self._check_insert(scr, "ana")
        self._check_update(scr, cat.scripts_update(scr["id"], {"active": "N"}, actor="bia"), "bia")

        prm = cat.parameters_insert({"code": "tst_%s_reg" % suf, "label": "Reg", "component_type": "TEXT"},
                                     actor="ana")
        self.m.note("parameters", prm["id"])
        self._check_insert(prm, "ana")
        self._check_update(prm, cat.parameters_update(prm["id"], {"label": "Outro"}, actor="bia"), "bia")

        prf = rbac.profiles_insert({"name": "TST_%s_REG" % suf}, actor="ana")
        self.m.note("profiles", prf["id"])
        self._check_insert(prf, "ana")
        self._check_update(prf, rbac.profiles_update(prf["id"], {"description": "x"}, actor="bia"), "bia")

        u = usr.insert({"login": "tst.%s.reg" % suf, "name": "Reg", "password_hash": "h", "profile_id": prf["id"]},
                        actor="ana")
        self.m.note("users", u["id"])
        self._check_insert(u, "ana")
        self._check_update(u, usr.update(u["id"], {"name": "Reg 2"}, actor="bia"), "bia")
        self._check_update(u, usr.set_password(u["id"], "hash-novo", actor="dora"), "dora")
        self._check_update(u, usr.unlock(u["id"], actor="eva"), "eva")

        rule = sch.insert({"name": "TST %s REG" % suf, "script_id": c["scr"]["id"], "environment": c["amb1"]["name"],
                             "user_id": c["u1"]["id"], "priority": 2, "recurrence_type": "DAILY",
                             "run_time": "03:00", "params_json": "{}",
                             "start_date": datetime.datetime(2026, 1, 15, 10, 0),
                             "next_run_at": datetime.datetime(2030, 1, 16, 3, 0)}, actor="ana")
        self.m.note("schedules", rule["id"])
        self._check_insert(rule, "ana")
        edited = sch.update(rule["id"], {"name": "TST %s REG2" % suf, "user_id": c["u2"]["id"]}, actor="op.hml")
        self._check_update(rule, edited, "op.hml")
        self.assertEqual(edited["created_by"], "ana", "o criador original nunca muda (R-g)")
        paused = sch.pause(rule["id"], "MANUAL", old_date=edited["next_run_at"], actor="bia")
        self._check_update(rule, paused, "bia")
        self._check_update(rule, sch.resume(rule["id"], edited["next_run_at"], actor="carla"), "carla")

    def test_12b_ator_obrigatorio_e_limitado_sem_gravacao_parcial(self):
        c = self.m.scenario()
        cat, usr, tck = self.obter_repo("catalog"), self.obter_repo("users"), self.obter_repo("tickets")
        for actor in (None, "", "x" * 41):
            with self.assertRaises(RepoViolation):
                cat.environments_insert({"name": "TST_%s_SEMATOR" % self.m.suf}, actor=actor)
        self.assertEqual(cat.environments_list(filters={"name": "TST_%s_SEMATOR" % self.m.suf})["total"], 0)
        before = cat.environments_get(c["amb1"]["id"])
        with self.assertRaises(RepoViolation):
            cat.environments_update(c["amb1"]["id"], {"description": "nao grava"})
        self.assertEqual(cat.environments_get(c["amb1"]["id"]), before)
        with self.assertRaises(RepoViolation):
            usr.unlock(c["u1"]["id"])
        tid = self.m.ticket(**c["ticket_base"])
        with self.assertRaises(RepoViolation):
            tck.request_cancel(tid, None, "10.0.0.1")
        self.assertEqual(tck.get(tid)["status"], "PENDING")
        amb40 = cat.environments_insert({"name": "TST_%s_ATOR40" % self.m.suf}, actor="y" * 40)
        self.m.note("environments", amb40["id"])
        self.assertEqual(amb40["created_by"], "y" * 40)

    def test_12c_rotina_tecnica_do_login_nao_grava_updated(self):
        c = self.m.scenario()
        usr = self.obter_repo("users")
        before = usr.get_by_login(c["login"])
        usr.register_login_failure(c["login"], lockout_s=60)
        usr.reset_attempts(before["id"])
        usr.register_login_success(c["login"], new_hash=before["password_hash"])
        after = usr.get_by_login(c["login"])
        self.assertEqual((after["updated_at"], after["updated_by"]), (before["updated_at"], before["updated_by"]))
        self.assertEqual(after["failed_attempts"], 0)

    def test_12d_tickets_criacao_e_cancelamento(self):
        c = self.m.scenario()
        tck = self.obter_repo("tickets")
        base = dict(c["ticket_base"], requested_by=c["u2"]["login"])
        tid = self.m.ticket([{"parameter_id": c["prm_a"]["id"], "answer_value": "2026-10-17"}], **base)
        t = tck.get(tid)
        self._check_insert(t, c["u2"]["login"])
        self.assertEqual([r["created_by"] for r in tck.answers(tid)], [c["u2"]["login"]])
        tid_sch = self.m.ticket(actor="SYSTEM:agt-host01", **base)
        self._check_insert(tck.get(tid_sch), "SYSTEM:agt-host01")

        self.assertEqual(tck.request_cancel(tid, "admin", "10.0.0.1"), "CANCELADO")
        self._check_update(t, tck.get(tid), "admin")
        self.assertEqual(tck.request_cancel(tid, "outro", "10.0.0.1"), "TERMINAL")
        self.assertEqual(tck.get(tid)["updated_by"], "admin", "solicitacao sem efeito nao altera o registro")

        tid_run = self.m.ticket(**dict(c["ticket_base"], status="RUNNING"))
        self.assertEqual(tck.request_cancel(tid_run, "admin", "10.0.0.1"), "SINALIZADO")
        self.assertEqual(tck.get(tid_run)["updated_by"], "admin")
        self.assertEqual(tck.request_cancel(tid_run, "outro", "10.0.0.1"), "JA_SINALIZADO")
        self.assertEqual(tck.get(tid_run)["updated_by"], "admin")


class BaseLastAdminTest(object):
    """Protecao do ultimo administrador (README §4.3.B): exige que nao haja outro admin ativo no banco.

    Roda no FAKE e no Oracle so com owner descartavel (SSS_TEST_*): num owner compartilhado ha admins
    reais, e desativa-los para o teste seria perigoso.
    """

    def test_perfil_ultimo_admin_recusado_sem_alterar(self):
        rbac = self.obter_repo("rbac")
        admin = rbac.profiles_list(filters={"name": "ADMINISTRATOR"})["items"][0]
        version = admin["perm_version"]
        for data in ({"active": "N"}, {"is_admin": "N"}):
            with self.assertRaises(RepoViolation) as ctx:
                rbac.profiles_update(admin["id"], data,
                                    audit={"actor": "admin", "ip": None, "action": "DEACTIVATE", "detail": "x"})
            self.assertEqual(ctx.exception.constraint, "sss_ultimo_admin")
        current = rbac.profiles_get(admin["id"])
        self.assertEqual((current["active"], current["is_admin"], current["perm_version"]), ("Y", "Y", version))

    def test_usuario_ultimo_admin_recusado_sem_alterar(self):
        usr = self.obter_repo("users")
        admin = usr.get_by_login("admin")
        query = usr.get_by_login("consulta")
        for data in ({"active": "N"}, {"profile_id": query["profile_id"]}):
            with self.assertRaises(RepoViolation) as ctx:
                usr.update(admin["id"], data, audit={"actor": "x", "ip": None, "action": "UPDATE", "detail": "x"})
            self.assertEqual(ctx.exception.constraint, "sss_ultimo_admin")
        current = usr.get_by_id(admin["id"])
        self.assertEqual((current["active"], current["profile_id"]), ("Y", admin["profile_id"]))


class TestRepoContractFake(unittest.TestCase, BaseRepoContractTest):
    """Executa a bateria de contratos contra o backend FAKE."""

    def setUp(self):
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()

    def obter_repo(self, name):
        return repo_factory.get(name)

    def test_saida_do_ticket_no_seed(self):
        """CR-012: metadados sem o conteudo; fatias so do DISPONIVEL; o Oracle e testado em test_scheduler_saida."""
        import io
        import zipfile
        tickets = self.obter_repo("tickets")
        self.assertIsNone(tickets.output_get(1))
        meta = tickets.output_get(17)
        self.assertEqual((meta["state"], meta["file_count"]), ("AVAILABLE", 2))
        self.assertNotIn("content", meta)
        read, off = b"", 0
        while True:
            part = tickets.output_read(17, off, 100)
            if not part:
                break
            read, off = read + part, off + len(part)
        self.assertEqual(len(read), meta["size_bytes"])
        self.assertEqual(sorted(zipfile.ZipFile(io.BytesIO(read)).namelist()),
                         ["rejeitados/linhas_rejeitadas.csv", "resumo.txt"])
        self.assertEqual((tickets.output_get(29)["state"], tickets.output_get(29)["reason"]), ("EXCEEDED", "FILES"))
        for tid in (29, 30, 1):
            with self.assertRaises(RepoNotFound):
                tickets.output_read(tid, 0, 10)
        for off, size in ((-1, 10), (0, 0), (0, 1024 * 1024 + 1)):
            with self.assertRaises(RepoViolation):
                tickets.output_read(17, off, size)

    # Vinculos por diferenca (CR-006, R-f): o contrato nao le as linhas de vinculo, entao o FAKE e
    # inspecionado direto; no Oracle, o F7.3 confere com SELECT nas tabelas de associacao.
    def _lines(self, table, **filter_value):
        store = self.obter_repo("catalog")._store
        return dict((tuple(v[c] for c in sorted(v) if c not in ("id", "created_at", "created_by",
                                                                  "updated_at", "updated_by")), v)
                    for v in getattr(store, table).values()
                    if all(v.get(k) == x for k, x in filter_value.items()))

    def test_12e_vinculos_por_diferenca_preservam_created(self):
        cat = self.obter_repo("catalog")
        rbac = self.obter_repo("rbac")
        sid = 1
        homolog = cat.homologation_get(sid)
        before = self._lines("script_env", script_id=sid)
        scr_before = cat.scripts_get(sid)
        cat.homologation_save(sid, homolog, actor="sem-mudanca")
        self.assertEqual(cat.scripts_get(sid)["updated_by"], scr_before["updated_by"])
        cat.homologation_save(sid, homolog + [3], actor="ana")
        after = self._lines("script_env", script_id=sid)
        for key, line in before.items():
            self.assertEqual((after[key]["created_at"], after[key]["created_by"]),
                             (line["created_at"], line["created_by"]))
        new = [v for k, v in after.items() if k not in before]
        self.assertEqual([v["created_by"] for v in new], ["ana"])
        self.assertEqual(cat.scripts_get(sid)["updated_by"], "ana")

        matrix = rbac.matrix_get(4)
        before = self._lines("profile_env", profile_id=4)
        rbac.matrix_save(4, matrix["funcs"], matrix["ambs"], matrix["scrs"] + [5], actor="bia")
        after = self._lines("profile_env", profile_id=4)
        self.assertEqual(after, before, "dimensao sem mudanca fica intacta")
        self.assertEqual(rbac.profiles_get(4)["updated_by"], "bia")
        self.assertEqual([v["created_by"] for k, v in self._lines("profile_script", profile_id=4).items()
                          if v["script_id"] == 5], ["bia"])

        links = cat.script_params_get(sid)
        self.assertGreaterEqual(len(links), 2)
        before = dict((v["parameter_id"], v) for v in self._lines("script_param", script_id=sid).values())
        swapped = [dict(parameter_id=v["parameter_id"], sort_order=v["sort_order"], required=v["required"],
                         default_value_override=v.get("default_value_override")) for v in links]
        swapped[0]["sort_order"], swapped[1]["sort_order"] = swapped[1]["sort_order"], swapped[0]["sort_order"]
        cat.script_params_save(sid, swapped, actor="carla")
        after = dict((v["parameter_id"], v) for v in self._lines("script_param", script_id=sid).values())
        for pid, line in before.items():
            self.assertEqual((after[pid]["created_at"], after[pid]["created_by"]),
                             (line["created_at"], line["created_by"]))
            changed = pid in (swapped[0]["parameter_id"], swapped[1]["parameter_id"])
            self.assertEqual(after[pid]["updated_by"], "carla" if changed else line["updated_by"])
        self.assertEqual(cat.scripts_get(sid)["updated_by"], "carla")

    def test_12f_finalizacao_simulada_e_do_agente(self):
        tck = self.obter_repo("tickets")
        store = tck._store
        before = tck.get(11)
        future = store.now() + datetime.timedelta(days=1)
        store.set_clock(lambda: future)
        tck.log_read(11, offset=0, max_chars=10)
        after = tck.get(11)
        self.assertEqual(after["status"], "SUCCESS")
        self.assertEqual(after["updated_by"], "SYSTEM:%s" % before["agent_id"])
        self.assertEqual(after["updated_at"], future)
        self.assertEqual(after["created_by"], before["created_by"])


class _OracleContract(object):
    """Preparo e limpeza comuns as classes da bateria contra o Oracle real (SSS_TEST_ORACLE=1)."""

    @classmethod
    def setUpClass(cls):
        from _oracle_test_support import prepare_disposable_schema
        cls._tinha_sss_cfg = hasattr(current, "sss_cfg")
        cls._previous_sss_cfg = getattr(current, "sss_cfg", None)
        cls.oracle_cfg = prepare_disposable_schema("web")
        current.sss_cfg = cls.oracle_cfg

    @classmethod
    def tearDownClass(cls):
        repo_factory.configure(None)
        repo_factory.reset_singletons()
        # O pool Thin do papel web mantem uma thread viva; os testes do agente exigem thread unica.
        from repo_oracle import base as base_oracle
        base_oracle.discard_pools()
        if cls._tinha_sss_cfg:
            current.sss_cfg = cls._previous_sss_cfg
        elif hasattr(current, "sss_cfg"):
            delattr(current, "sss_cfg")

    def setUp(self):
        repo_factory.configure({"app": {"sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self._fixtures = None

    def tearDown(self):
        self._clean_fixtures()

    def obter_repo(self, name):
        return repo_factory.get(name)

    def _clean_fixtures(self):
        """Remove so os registros criados pelo teste, em ordem de dependencia; no modo compartilhado,
        tambem a auditoria deles (README §2.5). Limpeza incompleta falha o teste com os IDs restantes."""
        import _oracle_test_support
        fixtures = getattr(self, "_fixtures", None)
        if fixtures is None or not any(fixtures.created.values()):
            return
        repo = self.obter_repo("catalog")
        shared = _oracle_test_support.schema_mode() == _oracle_test_support.SHARED_MODE
        tab_aud = repo.qualify_table("audit")
        conn = repo._obter_conexao()
        remaining = []
        try:
            cur = conn.cursor()
            try:
                for entity, ids in fixtures.created.items():
                    table = repo.qualify_table(entity)
                    for rid in ids:
                        cur.execute("DELETE FROM " + table + " WHERE id = :id", {"id": rid})
                        if shared:
                            cur.execute("DELETE FROM " + tab_aud + " WHERE entity = :ent AND entity_id = :id",
                                        {"ent": "tbsss_" + sql_ident.physical(entity), "id": rid})
                conn.commit()
                for entity, ids in fixtures.created.items():
                    table = repo.qualify_table(entity)
                    for rid in ids:
                        cur.execute("SELECT id FROM " + table + " WHERE id = :id", {"id": rid})
                        if cur.fetchone():
                            remaining.append((entity, rid))
            finally:
                cur.close()
        finally:
            conn.close()
        if remaining:
            self.fail("Limpeza incompleta no banco real: %s" % remaining)


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestRepoContractOracle(_OracleContract, unittest.TestCase, BaseRepoContractTest):
    """Executa a mesma bateria contra o Oracle do config.ini, com dados proprios de cada teste."""


class TestLastAdminFake(unittest.TestCase, BaseLastAdminTest):
    """Protecao do ultimo administrador no FAKE (seed com um unico admin ativo)."""

    def setUp(self):
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()

    def obter_repo(self, name):
        return repo_factory.get(name)


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestLastAdminOracle(_OracleContract, unittest.TestCase, BaseLastAdminTest):
    """Protecao do ultimo administrador no Oracle: so com owner descartavel (o teste e dono do banco)."""

    @classmethod
    def setUpClass(cls):
        super(TestLastAdminOracle, cls).setUpClass()
        import _oracle_test_support
        if _oracle_test_support.schema_mode() != _oracle_test_support.DISPOSABLE_MODE:
            raise unittest.SkipTest("Owner compartilhado: ha administradores reais; a protecao do ultimo admin "
                                    "so e exercida no FAKE e com owner SSS_TEST_* (README §2.5)")


class TestRepoFactoryAndIntegrity(unittest.TestCase):
    """Testes especificos da fabrica e regras estruturais do AGENTS.md."""

    def tearDown(self):
        repo_factory.configure(None)
        repo_factory.reset_singletons()

    def test_fake_fora_de_dev_lanca_runtime_error(self):
        # FAKE com HML deve abortar com RuntimeError (README §2.5)
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "HML"}})
        with self.assertRaises(RuntimeError) as ctx:
            repo_factory.get("users")
        self.assertIn("FAKE (so de teste) e proibido fora de DEV", str(ctx.exception))

        # FAKE com PROD tambem deve abortar
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "PROD"}})
        with self.assertRaises(RuntimeError):
            repo_factory.get("users")

    def test_oracle_integrado_exige_banco_autorizado(self):
        """A bateria Oracle so roda com SSS_TEST_ORACLE=1, DEV e o esquema validado (detalhes no test_db_conn)."""
        from _oracle_test_support import SchemaPreconditionError, prepare_disposable_schema

        cfg = mock.Mock()
        cfg.app.data_backend = "FAKE"
        cfg.app.sss_env = "DEV"
        cfg.oracle.owner = "SSS_TEST_APP"
        cfg.oracle.dsn = "dbtest.local/sss"
        cfg.oracle.user = "SSS_APP"
        cfg.oracle.table_prefix = "tbsss_"
        cfg.secrets.secrets_file = "/tmp/secrets.cfg"
        secrets_value = object()
        connection = mock.Mock()
        connection.cursor.return_value.fetchone.return_value = ("SSS_APP",)
        db_conn_mock = mock.Mock()
        db_conn_mock.connect.return_value = connection
        sss_config_mock = mock.Mock()
        sss_config_mock.get_config.return_value = cfg
        sss_config_mock.load_secrets.return_value = secrets_value

        def preparar(env):
            with mock.patch.dict(os.environ, env, clear=True):
                with mock.patch.dict("sys.modules", {"db_conn": db_conn_mock, "sss_config": sss_config_mock}):
                    return prepare_disposable_schema("web")

        # Ligado e autorizado: usa o config da aplicacao, confere a sessao e fecha a conexao.
        self.assertIs(preparar({"SSS_TEST_ORACLE": "1"}), cfg)
        db_conn_mock.connect.assert_called_once_with(cfg, secrets_value, "web")
        self.assertEqual(connection.cursor.return_value.execute.call_args[0][0], "SELECT USER FROM DUAL")
        connection.close.assert_called_once_with()

        # Desligado, variavel antiga ou fora de DEV: recusa antes de conectar.
        db_conn_mock.connect.reset_mock()
        for env in ({}, {"SSS_TEST_ORACLE": "1", "SSS_TEST_DSN": "dbtest.local/sss"}):
            with self.assertRaises(SchemaPreconditionError):
                preparar(env)
        cfg.app.sss_env = "HML"
        with self.assertRaises(SchemaPreconditionError):
            preparar({"SSS_TEST_ORACLE": "1"})
        db_conn_mock.connect.assert_not_called()

    def test_oracle_agregado_seguinte_ainda_nao_implementado(self):
        repo_factory.configure({"app": {"data_backend": "ORACLE", "sss_env": "DEV"}})
        aggregates = ("RBAC_USUARIOS", "CATALOGO", "TICKETS", "AGENDAMENTOS", "AUDITORIA_AGENTES")
        selected = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if selected not in aggregates:
            self.skipTest("Factory Oracle progressiva validada pelo prompt F7.3")
        index = aggregates.index(selected)
        if index == len(aggregates) - 1:
            self.skipTest("Todos os agregados estao registrados; rodar a bateria Oracle integrada")
        next_value = ("catalog", "tickets", "schedules", "audit")
        with self.assertRaises(NotImplementedError) as ctx:
            repo_factory.get(next_value[index])
        self.assertIn("Backend ORACLE ainda nao implementado", str(ctx.exception))

    def test_nenhum_import_repo_fake_fora_de_repo_factory(self):
        """Verifica que nenhum modulo ou script fora de repo_factory importa repo_fake."""
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pattern = re.compile(r"^\s*(from|import)\s+.*repo_fake.*", re.MULTILINE)

        files_violators = []
        for root, dirs, files in os.walk(app_dir):
            # Ignora o proprio diretorio modules/repo_fake e cache
            norm_root = os.path.normpath(root)
            if norm_root.endswith("modules/repo_fake") or "modules/repo_fake/" in norm_root:
                continue
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            if ".git" in dirs:
                dirs.remove(".git")

            for f in files:
                if not f.endswith(".py"):
                    continue
                path = os.path.join(root, f)
                rel_path = os.path.relpath(path, app_dir)
                if rel_path == "modules/repo_factory.py":
                    continue

                with open(path, "r", encoding="utf-8") as file:
                    content = file.read()
                    if pattern.search(content):
                        files_violators.append(rel_path)

        self.assertEqual(
            files_violators, [],
            "Arquivos fora de repo_factory.py importando repo_fake: %s" % files_violators
        )

    def test_paridade_estrita_sem_metodos_extras_no_fake(self):
        """Verifica que as classes Fake nao expõem metodos publicos alem dos contratos."""
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()

        pairs = [
            (RepoUsers, repo_factory.get("users")),
            (RepoRbac, repo_factory.get("rbac")),
            (RepoCatalog, repo_factory.get("catalog")),
            (RepoTickets, repo_factory.get("tickets")),
            (RepoSchedules, repo_factory.get("schedules")),
            (RepoAudit, repo_factory.get("audit")),
            (RepoAgents, repo_factory.get("agents")),
        ]

        for contract_cls, fake_inst in pairs:
            methods_contract = {
                m for m in dir(contract_cls)
                if not m.startswith("_") and callable(getattr(contract_cls, m))
            }
            methods_fake = {
                m for m in dir(fake_inst)
                if not m.startswith("_") and callable(getattr(fake_inst, m))
            }

            extras = methods_fake - methods_contract
            self.assertEqual(
                extras, set(),
                "Classe Fake %s expos metodos publicos fora do contrato: %s" % (
                    fake_inst.__class__.__name__, extras
                )
            )

    def test_retornos_nao_vazam_referencia_mutavel(self):
        """Verifica que o backend FAKE devolve copias independentes (deepcopy)."""
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()

        usr = repo_factory.get("users")
        u1 = usr.get_by_login("admin")
        u1["name"] = "Mutacao Indevida Externa"

        u2 = usr.get_by_login("admin")
        self.assertNotEqual(u2["name"], "Mutacao Indevida Externa")


class TestFailFastRegression(unittest.TestCase):
    """Regressao: fabrica sem padrao silencioso e FAKE sem coercao silenciosa de entrada."""

    def setUp(self):
        self._previous_sss_cfg = getattr(current, "sss_cfg", None)
        current.sss_cfg = None
        repo_factory.configure(None)
        repo_factory.reset_singletons()

    def tearDown(self):
        current.sss_cfg = self._previous_sss_cfg
        repo_factory.configure(None)
        repo_factory.reset_singletons()

    def test_sem_configuracao_falha_mesmo_com_variaveis_de_ambiente(self):
        with mock.patch.dict(os.environ, {"SSS_DATA_BACKEND": "FAKE", "SSS_ENV": "DEV"}):
            with self.assertRaises(RuntimeError) as ctx:
                repo_factory.get("users")
        self.assertIn("Configuracao ausente", str(ctx.exception))

    def test_configuracao_incompleta_falha(self):
        for cfg in ({}, {"app": {"data_backend": "FAKE"}}):
            with self.subTest(cfg=cfg):
                repo_factory.configure(cfg)
                with self.assertRaises(KeyError):
                    repo_factory.get("users")

    def test_sem_data_backend_a_aplicacao_e_oracle(self):
        """F7.3: o config.ini nao tem mais data_backend; so o dict de teste pode pedir o FAKE."""
        self.assertEqual(repo_factory._resolve_config({"app": {"sss_env": "DEV"}}), ("ORACLE", "DEV"))
        self.assertEqual(repo_factory._resolve_config({"app": {"sss_env": "DEV", "data_backend": "FAKE"}}),
                         ("FAKE", "DEV"))
        import sss_config
        cfg_app = sss_config.AppConfig(sss_env="PROD")
        self.assertEqual(repo_factory._resolve_config({"app": cfg_app}), ("ORACLE", "PROD"))

    def test_usa_current_sss_cfg_quando_sem_override(self):
        current.sss_cfg = {"app": {"data_backend": "FAKE", "sss_env": "DEV"}}
        self.assertIsInstance(repo_factory.get("users"), RepoUsers)

        repo_factory.reset_singletons()
        current.sss_cfg = {"app": {"data_backend": "FAKE", "sss_env": "PROD"}}
        with self.assertRaises(RuntimeError):
            repo_factory.get("users")

    def test_paginacao_rejeita_entrada_nao_numerica(self):
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        usr = repo_factory.get("users")
        with self.assertRaises(ValueError):
            usr.list(page="abc")
        with self.assertRaises(TypeError):
            usr.list(size=[])
        page = usr.list(page=None, size=None)
        self.assertEqual((page["page"], page["size"]), (1, 20))
        page = usr.list(page="0", size="-5")
        self.assertEqual((page["page"], page["size"]), (1, 20))

    def test_log_ler_rejeita_entrada_nao_numerica(self):
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        tck = repo_factory.get("tickets")
        with self.assertRaises(ValueError):
            tck.log_read(11, offset="x", max_chars=20)
        with self.assertRaises(TypeError):
            tck.log_read(11, offset=None, max_chars=20)
        with self.assertRaises(ValueError):
            tck.log_read(11, offset=0, max_chars="muito")
        self.assertEqual(tck.log_read(11, offset=-3, max_chars=5)[0],
                         tck.log_read(11, offset=0, max_chars=5)[0])
