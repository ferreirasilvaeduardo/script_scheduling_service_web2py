# -*- coding: utf-8 -*-
"""Bateria de testes de conformidade para contratos de repositorio e backend FAKE.

Valida requisitos do prompt F0.4, README §2.5 e AGENTS.md §4, §5.5, §7:
1. CRUD basico de todos os agregados;
2. Unicidade de UKs gerando RepoViolation;
3. CKs de connection com '@' gerando RepoViolation;
4. Imutabilidade de environments.name e usuarios.login;
5. Cascatas de associacao (matriz, script_param, homologacao);
6. solicitar_cancelamento nos 3 retornos ('TERMINAL', 'CANCELADO', 'SINALIZADO');
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

    def __init__(self, obter_repo):
        self._r = obter_repo
        self.suf = "%08d" % (int(time.time() * 1000000) % 100000000)
        self.actor = "tst" + self.suf
        self.created = collections.OrderedDict((ent, []) for ent in self.ORDER)
        self._scenario = None

    def note(self, entidade, id):
        self.created[entidade].append(id)
        return id

    def environment(self, rotulo="A", **extra):
        dados = dict({"name": "TST_%s_%s" % (self.suf, rotulo), "description": "Ambiente de teste"}, **extra)
        amb = self._r("catalog").environments_insert(dados, ator=self.actor)
        self.note("environments", amb["id"])
        return amb

    def profile(self, rotulo="P", **extra):
        per = self._r("rbac").profiles_insert(dict({"name": "TST_%s_%s" % (self.suf, rotulo), "is_admin": "N"}, **extra),
                                             ator=self.actor)
        self.note("profiles", per["id"])
        return per

    def usuario(self, perfil_id, rotulo="u", **extra):
        dados = dict({"login": "tst.%s.%s" % (self.suf, rotulo), "name": "Usuario de teste",
                      "password_hash": "pbkdf2_sha256$1$00$00", "profile_id": perfil_id, "active": "Y"}, **extra)
        u = self._r("users").insert(dados, ator=self.actor)
        self.note("users", u["id"])
        return u

    def parameter(self, rotulo="a", **extra):
        dados = dict({"code": "tst_%s_%s" % (self.suf, rotulo), "label": "Parametro %s" % rotulo,
                      "component_type": "TEXT", "param_flag": "--tst%s%s" % (self.suf, rotulo)}, **extra)
        prm = self._r("catalog").parameters_insert(dados, ator=self.actor)
        self.note("parameters", prm["id"])
        return prm

    def script(self, rotulo="s", **extra):
        dados = dict({"name": "tst_scr_%s_%s" % (self.suf, rotulo), "interpreter": "SH", "param_type": "NAMED",
                      "path_file": "/opt/tst/%s_%s.sh" % (self.suf, rotulo)}, **extra)
        scr = self._r("catalog").scripts_insert(dados, ator=self.actor)
        self.note("scripts", scr["id"])
        return scr

    def schedule(self, script_id, environment, user_id, rotulo="r", **extra):
        dados = dict({"name": "TST %s %s" % (self.suf, rotulo), "script_id": script_id, "environment": environment,
                      "user_id": user_id, "priority": 2, "recurrence_type": "DAILY",
                      "run_time": "03:00", "params_json": "{}",
                      "start_date": datetime.datetime(2026, 1, 15, 10, 0),
                      "next_run_at": datetime.datetime(2030, 1, 16, 3, 0)}, **extra)
        regra = self._r("schedules").insert(dados, ator=self.actor)
        self.note("schedules", regra["id"])
        return regra

    def ticket(self, respostas=(), actor=None, **dados):
        tid = self._r("tickets").create(dados, list(respostas), ator=actor)
        return self.note("tickets", tid)

    def scenario(self):
        """Dois ambientes, um perfil comum com dois usuarios, dois parametros com flag e um script
        NOMEADO homologado no primeiro ambiente, com os dois parametros vinculados."""
        if self._scenario is None:
            c = {}
            c["amb1"], c["amb2"] = self.environment("A"), self.environment("B")
            c["perfil"] = self.profile("P")
            c["u1"], c["u2"] = self.usuario(c["perfil"]["id"], "u1"), self.usuario(c["perfil"]["id"], "u2")
            c["prm_a"], c["prm_b"] = self.parameter("a"), self.parameter("b")
            c["scr"] = self.script("s")
            cat = self._r("catalog")
            cat.homologation_save(c["scr"]["id"], [c["amb1"]["id"]], ator=self.actor)
            cat.script_params_save(c["scr"]["id"], [
                {"parameter_id": c["prm_a"]["id"], "sort_order": 1, "required": "Y"},
                {"parameter_id": c["prm_b"]["id"], "sort_order": 2, "required": "N"}], ator=self.actor)
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

    def cn(self, tipo, entidade, sufixo):
        """Nome da constraint/indice/trigger com o prefixo do repositorio em uso (FAKE: tbsss_)."""
        prefixo = getattr(self.obter_repo("catalog"), "_prefixo", None) or "tbsss_"
        return "%s_%s%s_%s" % (tipo, prefixo, sql_ident.TABLES[entidade]["abrev"], sufixo)

    def aud_total(self, acao, entidade, entidade_id):
        return self.obter_repo("audit").list(
            filtros={"action": acao, "entity": entidade, "entity_id": entidade_id}, pagina=1, tamanho=1)["total"]

    def aud_last(self, acao, entidade, entidade_id):
        return self.obter_repo("audit").list(
            filtros={"action": acao, "entity": entidade, "entity_id": entidade_id}, pagina=1, tamanho=1)["itens"][0]

    def test_ocorrencia_duplicada_recusada_sem_alterar_ticket(self):
        c = self.m.scenario()
        tickets = self.obter_repo("tickets")
        regra = self.m.schedule(c["scr"]["id"], c["amb1"]["name"], c["u1"]["id"])
        dados = {"script_id": c["scr"]["id"], "environment": c["amb1"]["name"], "requested_by": c["login"],
                 "schedule_id": regra["id"], "scheduled_at": datetime.datetime(2030, 1, 2)}
        primeiro_id = self.m.ticket(actor="teste", **dados)
        primeiro = tickets.get(primeiro_id)
        with self.assertRaises(RepoViolation) as erro:
            self.m.ticket(actor="teste", **dados)
        self.assertEqual(erro.exception.constraint, self.cn("ix", "tickets", "occur"))
        self.assertEqual(tickets.get(primeiro["id"]), primeiro)
        self.m.ticket(actor="teste", **dict(dados, scheduled_at=datetime.datetime(2030, 1, 3)))
        self.m.ticket(actor="teste", **dict(dados, schedule_id=None))
        self.m.ticket(actor="teste", **dict(dados, schedule_id=None))

    def test_01_crud_ambientes(self):
        cat = self.obter_repo("catalog")
        amb = self.m.environment("CRUD", connection="db-teste.local:1521/svc")
        self.assertIsNotNone(amb.get("id"))
        self.assertEqual(cat.environments_get(amb["id"])["name"], amb["name"])
        alterado = cat.environments_update(amb["id"], {"description": "Descricao alterada", "active": "N"}, ator="teste")
        self.assertEqual((alterado["description"], alterado["active"]), ("Descricao alterada", "N"))
        lista = cat.environments_list(filtros={"name": amb["name"]})
        self.assertEqual(lista["total"], 1)
        self.assertEqual(lista["itens"][0]["id"], amb["id"])

    def test_02_uk_duplicada_ambiente_perfil_script_usuario(self):
        c = self.m.scenario()
        cat, rbac, usr = self.obter_repo("catalog"), self.obter_repo("rbac"), self.obter_repo("users")
        with self.assertRaises(RepoViolation) as ctx:
            cat.environments_insert({"name": c["amb1"]["name"], "connection": "db-prod2.local:1521/svc"}, ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("uk", "environments", "name"))
        with self.assertRaises(RepoViolation) as ctx:
            rbac.profiles_insert({"name": c["perfil"]["name"], "is_admin": "N"}, ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("uk", "profiles", "name"))
        with self.assertRaises(RepoViolation) as ctx:
            cat.scripts_insert({"name": c["scr"]["name"], "interpreter": "PYTHON3",
                                 "path_file": "/opt/tst/dup.py"}, ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("uk", "scripts", "name"))
        # CK de path_file (CR-005 R-g): absoluto, sem '..', '//' nem '\'.
        with self.assertRaises(RepoViolation) as ctx:
            cat.scripts_insert({"name": "tst_%s_path" % self.m.suf, "interpreter": "PYTHON3",
                                 "path_file": "x.py"}, ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("ck", "scripts", "path"))
        with self.assertRaises(RepoViolation) as ctx:
            usr.insert({"login": c["login"], "name": "Duplicado", "password_hash": "h",
                         "profile_id": c["perfil"]["id"]}, ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("uk", "users", "login"))

    def test_03_ck_conexao_com_arroba(self):
        cat = self.obter_repo("catalog")
        with self.assertRaises(RepoViolation) as ctx:
            cat.environments_insert({"name": "TST_%s_ARROBA" % self.m.suf, "connection": "usr:pwd@host:1521/svc"},
                                  ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("ck", "environments", "connection"))
        amb = self.m.environment("ARR")
        with self.assertRaises(RepoViolation) as ctx:
            cat.environments_update(amb["id"], {"connection": "app@host/svc"}, ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("ck", "environments", "connection"))

    def test_04_imutabilidade_nome_ambiente_e_login_usuario(self):
        c = self.m.scenario()
        with self.assertRaises(RepoViolation) as ctx:
            self.obter_repo("catalog").environments_update(c["amb1"]["id"], {"name": "TST_%s_NOVO" % self.m.suf},
                                                          ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("tr", "environments", "bu"))
        with self.assertRaises(RepoViolation) as ctx:
            self.obter_repo("users").update(c["u1"]["id"], {"login": "tst.%s.novo" % self.m.suf}, ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("tr", "users", "bu"))

    def test_04b_ambiente_alteracao_condicional_e_auditoria_na_mesma_operacao(self):
        cat = self.obter_repo("catalog")
        amb = self.m.environment("AUD")
        lido = {"description": amb["description"], "connection": amb["connection"], "active": amb["active"]}
        alterado = cat.environments_update(amb["id"], {"description": "Contrato"}, esperado=lido,
                                         auditoria={"actor": "admin", "ip": "10.0.0.1", "action": "UPDATE",
                                                    "detail": "description: x -> Contrato"})
        self.assertEqual(alterado["description"], "Contrato")
        self.assertEqual(self.aud_total("UPDATE", "tbsss_environments", amb["id"]), 1)
        self.assertEqual(self.aud_last("UPDATE", "tbsss_environments", amb["id"])["actor"], "admin")

        # 'lido' ficou obsoleto: o UPDATE condicional perde, nada muda e nada e auditado.
        with self.assertRaises(RepoConflict):
            cat.environments_update(amb["id"], {"description": "Perdedor"}, esperado=lido,
                                  auditoria={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "x"})
        self.assertEqual(cat.environments_get(amb["id"])["description"], "Contrato")
        # Violacao tambem nao grava auditoria nem altera colunas parcialmente.
        with self.assertRaises(RepoViolation):
            cat.environments_update(amb["id"], {"description": "Parcial", "connection": "a@b"},
                                  auditoria={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "x"})
        self.assertEqual(cat.environments_get(amb["id"])["description"], "Contrato")
        self.assertEqual(self.aud_total("UPDATE", "tbsss_environments", amb["id"]), 1)

        novo = cat.environments_insert({"name": "TST_%s_CAUD" % self.m.suf, "connection": "ALIAS"},
                                     auditoria={"actor": "admin", "ip": None, "action": "CREATE", "detail": "y"})
        self.m.note("environments", novo["id"])
        self.assertEqual(self.aud_total("CREATE", "tbsss_environments", novo["id"]), 1)

    def test_04c_perfil_conflito_e_matriz_condicional(self):
        """Conflito sem incremento e matriz condicional (o ultimo admin fica em TestLastAdmin*)."""
        c = self.m.scenario()
        rbac = self.obter_repo("rbac")
        per = c["perfil"]
        func_ids = [f["id"] for f in rbac.features_list()][:2]
        rbac.matrix_save(per["id"], func_ids, [c["amb1"]["id"]], [c["scr"]["id"]], ator="teste")
        atual = rbac.profiles_get(per["id"])
        versao = atual["perm_version"]

        with self.assertRaises(RepoConflict):
            rbac.profiles_update(per["id"], {"description": "x"}, esperado={"description": "outra"}, ator="teste")
        self.assertEqual(rbac.profiles_get(per["id"])["perm_version"], versao)

        matriz = rbac.matrix_get(per["id"])
        with self.assertRaises(RepoConflict):
            rbac.matrix_save(per["id"], [], [], [], perm_versao_esperada=versao + 7, ator="teste")
        with self.assertRaises(RepoViolation):
            rbac.matrix_save(per["id"], [999999], matriz["ambs"], matriz["scrs"], perm_versao_esperada=versao,
                               ator="teste")
        self.assertEqual(rbac.matrix_get(per["id"]), matriz)
        self.assertEqual(rbac.profiles_get(per["id"])["perm_version"], versao)

        nova = rbac.matrix_save(per["id"], [], matriz["ambs"], matriz["scrs"], perm_versao_esperada=versao,
                                  auditoria={"actor": "admin", "ip": None, "action": "PERM_UPDATE", "detail": "-VIEW_LOGS"})
        self.assertEqual(nova["funcs"], [])
        self.assertEqual(rbac.profiles_get(per["id"])["perm_version"], versao + 1)
        self.assertEqual(self.aud_total("PERM_UPDATE", "tbsss_profiles", per["id"]), 1)

    def test_04d_usuario_conflito_auditoria_login_e_filtro_bloqueio(self):
        """Conflito, auditoria, login e filtro de bloqueio (o ultimo admin fica em TestLastAdmin*)."""
        c = self.m.scenario()
        usr = self.obter_repo("users")
        alvo = c["u2"]
        with self.assertRaises(RepoConflict):
            usr.update(alvo["id"], {"name": "X"}, esperado={"name": "outro"}, ator="teste")
        self.assertEqual(usr.get_by_id(alvo["id"])["name"], alvo["name"])

        usr.update(alvo["id"], {"name": "Consulta Contrato"}, esperado={"name": alvo["name"]},
                    auditoria={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "name"})
        usr.set_password(alvo["id"], "pbkdf2_sha256$1$00$00",
                          auditoria={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "senha redefinida"})
        usr.unlock(alvo["id"], auditoria={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "d"})
        self.assertEqual(self.aud_total("UPDATE", "tbsss_users", alvo["id"]), 3)

        # CR-003 P3: falha/sucesso de login com auditoria na mesma operacao e bloqueio pelo relogio do banco.
        inicio = usr.now()
        reg = usr.register_login_failure(alvo["login"], bloqueio_s=60, auditoria=[
            {"actor": alvo["login"], "ip": None, "action": "LOGIN_FAILED", "detail": "f"},
            {"actor": alvo["login"], "ip": None, "action": "LOGIN_LOCKED", "detail": "b"}])
        self.assertGreaterEqual(reg["locked_until"], inicio + datetime.timedelta(seconds=60))
        self.assertEqual(self.aud_total("LOGIN_FAILED", "tbsss_users", alvo["id"]), 1)
        self.assertEqual(self.aud_total("LOGIN_LOCKED", "tbsss_users", alvo["id"]), 1)
        reg = usr.register_login_success(alvo["login"], novo_hash="pbkdf2_sha256$2$00$00",
                                          auditoria={"actor": alvo["login"], "ip": None, "action": "LOGIN_OK", "detail": "ok"})
        self.assertEqual((reg["failed_attempts"], reg["locked_until"]), (0, None))
        self.assertEqual(reg["password_hash"], "pbkdf2_sha256$2$00$00")
        self.assertGreaterEqual(reg["last_login_at"], inicio)
        self.assertEqual(reg["last_login_at"].microsecond, 0)

        usr.update(alvo["id"], {"locked_until": datetime.datetime(2999, 1, 1)}, ator="teste")
        bloqueados = usr.list(filtros={"bloqueado_em": datetime.datetime(2998, 1, 1)}, pagina=1, tamanho=200)
        self.assertIn(alvo["login"], [u["login"] for u in bloqueados["itens"]])
        self.assertNotIn(c["u1"]["login"], [u["login"] for u in bloqueados["itens"]])

    def test_04e_parametro_dependencias_atomicas_qtd_scripts_e_auditoria(self):
        c = self.m.scenario()
        cat = self.obter_repo("catalog")
        prm = cat.parameters_list(filtros={"code": c["prm_a"]["code"]})["itens"][0]
        self.assertEqual(prm["qtd_scripts"], len(cat.parameter_links(prm["id"])))
        self.assertEqual(prm["qtd_scripts"], 1)
        for dados, constraint in (({"component_type": "NUMBER"}, "sss_prm_tipo_vinculado"),
                                  ({"param_flag": "--outra-flag"}, "sss_prm_flag_nomeado"),
                                  ({"active": "N"}, "sss_prm_vinculo_ativo")):
            with self.assertRaises(RepoViolation) as ctx:
                cat.parameters_update(prm["id"], dict(dados, label="Nao deve gravar"), ator="teste")
            self.assertEqual(ctx.exception.constraint, constraint)
        self.assertEqual(cat.parameters_get(prm["id"])["label"], prm["label"])
        with self.assertRaises(RepoConflict):
            cat.parameters_update(prm["id"], {"label": "x"}, esperado={"label": "outro"}, ator="teste")

        novo = cat.parameters_insert({"code": "tst_%s_novo" % self.m.suf, "label": "Contrato",
                                       "component_type": "TEXT"},
                                      auditoria={"actor": "admin", "ip": None, "action": "CREATE", "detail": "x"})
        self.m.note("parameters", novo["id"])
        self.assertEqual(self.aud_total("CREATE", "tbsss_parameters", novo["id"]), 1)
        # Sem vinculo, tipo e flag mudam e a desativacao passa.
        alterado = cat.parameters_update(novo["id"], {"component_type": "NUMBER", "param_flag": "--n",
                                                       "active": "N"}, ator="teste")
        self.assertEqual((alterado["component_type"], alterado["param_flag"], alterado["active"]),
                         ("NUMBER", "--n", "N"))

    def test_04f_script_regras_de_tipo_param_homologacao_e_vinculos_condicionais(self):
        c = self.m.scenario()
        cat = self.obter_repo("catalog")
        scr = cat.scripts_list(filtros={"name": c["scr"]["name"]})["itens"][0]
        self.assertEqual(scr["qtd_parametros"], len(cat.script_params_get(scr["id"])))
        self.assertEqual(scr["ambientes_homologados"], [c["amb1"]["name"]])

        with self.assertRaises(RepoViolation) as ctx:
            cat.scripts_update(scr["id"], {"param_type": "NONE", "description": "Nao grava"}, ator="teste")
        self.assertEqual(ctx.exception.constraint, "sss_scr_nenhum_vinculado")
        self.assertEqual(cat.scripts_get(scr["id"])["param_type"], "NAMED")
        with self.assertRaises(RepoConflict):
            cat.scripts_update(scr["id"], {"description": "x"}, esperado={"description": "outra"}, ator="teste")

        sem_flag = self.m.parameter("semflag", param_flag=None)
        with self.assertRaises(RepoViolation) as ctx:
            cat.script_params_save(scr["id"], [{"parameter_id": sem_flag["id"], "sort_order": 1, "required": "N"}],
                                     ator="teste")
        self.assertEqual(ctx.exception.constraint, "sss_scr_nomeado_sem_flag")

        homolog = cat.homologation_get(scr["id"])
        with self.assertRaises(RepoConflict):
            cat.homologation_save(scr["id"], [], esperado=homolog + [999], ator="teste")
        cat.homologation_save(scr["id"], homolog, esperado=homolog,
                               auditoria={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "h"})
        vinc = cat.script_params_get(scr["id"])
        lidos = [(v["parameter_id"], v["sort_order"], v["required"], v.get("default_value_override")) for v in vinc]
        with self.assertRaises(RepoConflict):
            cat.script_params_save(scr["id"], [], esperado=lidos[1:], ator="teste")
        cat.script_params_save(scr["id"], [dict(parameter_id=x[0], sort_order=x[1], required=x[2],
                                                  default_value_override=x[3]) for x in lidos], esperado=lidos,
                                 auditoria={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "v"})
        self.assertEqual(self.aud_total("UPDATE", "tbsss_scripts", scr["id"]), 2)

    def test_05_cascata_associacao(self):
        c = self.m.scenario()
        cat, rbac = self.obter_repo("catalog"), self.obter_repo("rbac")
        sid = c["scr"]["id"]
        cat.homologation_save(sid, [c["amb1"]["id"]], ator="teste")
        self.assertEqual(cat.homologation_get(sid), [c["amb1"]["id"]])
        cat.homologation_save(sid, [c["amb1"]["id"], c["amb2"]["id"]], ator="teste")
        self.assertEqual(sorted(cat.homologation_get(sid)), sorted([c["amb1"]["id"], c["amb2"]["id"]]))

        p = c["perfil"]
        v_antes = rbac.profiles_get(p["id"])["perm_version"]
        func_ids = sorted(f["id"] for f in rbac.features_list())[:2]
        rbac.matrix_save(p["id"], funcs=func_ids, ambs=[c["amb1"]["id"]], scrs=[sid], ator="teste")
        m = rbac.matrix_get(p["id"])
        self.assertEqual((sorted(m["funcs"]), m["ambs"], m["scrs"]), (func_ids, [c["amb1"]["id"]], [sid]))
        self.assertGreater(rbac.profiles_get(p["id"])["perm_version"], v_antes)

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
        agd = self.obter_repo("schedules")
        regra = self.m.schedule(c["scr"]["id"], c["amb1"]["name"], c["u1"]["id"])
        data_correta = regra["next_run_at"]
        with self.assertRaises(RepoConflict):
            agd.pause(regra["id"], motivo="MANUAL", antiga_data=data_correta + datetime.timedelta(days=10),
                       ator="teste")
        pausado = agd.pause(regra["id"], motivo="MANUAL", antiga_data=data_correta, ator="teste")
        self.assertEqual((pausado["active"], pausado["pause_reason"]), ("N", "MANUAL"))
        # Pausar uma regra ja pausada gera RepoConflict (CR-007 R-19).
        with self.assertRaises(RepoConflict):
            agd.pause(regra["id"], motivo="MANUAL", antiga_data=data_correta, ator="teste")

    def test_06b_fks_e_limites_de_auditoria(self):
        """CR-003 P8 (README §2.5): FKs, UK de ticket_resp e limites da auditoria, sem gravacao parcial."""
        c = self.m.scenario()
        tck, agd, aud = self.obter_repo("tickets"), self.obter_repo("schedules"), self.obter_repo("audit")
        base = c["ticket_base"]
        meus = lambda: tck.list(filtros={"requested_by": c["login"]}, pagina=1, tamanho=1)["total"]  # noqa: E731
        total = meus()
        prm = c["prm_a"]["id"]
        casos = (
            (dict(base, script_id=999999999), [], self.cn("fk", "tickets", "scr")),
            (dict(base, environment="NAO_EXISTE_TST"), [], self.cn("fk", "tickets", "env")),
            (dict(base, requested_by="nao.existe.tst"), [], self.cn("fk", "tickets", "usr")),
            (base, [{"parameter_id": 999999999, "answer_value": "x"}], self.cn("fk", "ticket_answer", "prm")),
            (base, [{"parameter_id": prm, "answer_value": "a"}, {"parameter_id": prm, "answer_value": "b"}],
             self.cn("uk", "ticket_answer", "tck_prm")),
        )
        for ticket, respostas, constraint in casos:
            with self.assertRaises(RepoViolation) as ctx:
                self.m.ticket(respostas, **ticket)
            self.assertEqual(ctx.exception.constraint, constraint)
        self.assertEqual(meus(), total)

        for mudanca, constraint in (({"script_id": 999999999}, self.cn("fk", "schedules", "scr")),
                                    ({"user_id": 999999999}, self.cn("fk", "schedules", "usr")),
                                    ({"environment": "NAO_EXISTE_TST"}, self.cn("fk", "schedules", "env"))):
            with self.assertRaises(RepoViolation) as ctx:
                self.m.schedule(**dict({"script_id": c["scr"]["id"], "environment": c["amb1"]["name"],
                                           "user_id": c["u1"]["id"]}, **mudanca))
            self.assertEqual(ctx.exception.constraint, constraint)

        amb_id = c["amb1"]["id"]
        for ator, detalhe in ((None, "x"), ("", "x"), ("a" * 41, "x"), ("admin", "d" * 1001)):
            with self.assertRaises(RepoViolation):
                aud.register(ator, None, "UPDATE", "tbsss_environments", amb_id, detalhe)
        aud.register("a" * 40, None, "UPDATE", "tbsss_environments", amb_id, "d" * 1000)

    def test_07b_agendamento_cks_condicional_e_auditoria_na_mesma_operacao(self):
        c = self.m.scenario()
        agd = self.obter_repo("schedules")
        inicio = datetime.datetime(2026, 1, 15, 10, 0)
        base = {"name": "TST %s CK" % self.m.suf, "script_id": c["scr"]["id"], "environment": c["amb1"]["name"],
                "user_id": c["u1"]["id"], "priority": 2, "recurrence_type": "DAILY", "run_time": "03:00",
                "params_json": "{}", "start_date": inicio, "next_run_at": datetime.datetime(2030, 1, 16, 3, 0)}
        ck = lambda s: self.cn("ck", "schedules", s)  # noqa: E731
        violacoes = [
            ({"recurrence_type": "ANUAL"}, ck("rtype")),
            ({"priority": 5}, ck("prio")),
            ({"active": "X"}, ck("active")),
            ({"recurrence_type": "MONTHLY", "month_day": 32}, ck("day")),
            ({"run_time": "24:00"}, ck("time")),
            ({"recurrence_type": "WEEKLY", "week_days": "1,8"}, ck("wday")),
            ({"end_date": inicio - datetime.timedelta(days=1)}, ck("end")),
            ({"pause_reason": "OUTRO"}, ck("pause")),
            ({"recurrence_type": "WEEKLY"}, ck("fields")),
            ({"recurrence_type": "CRON", "run_time": None}, ck("fields")),
        ]
        minhas = lambda: agd.list(filtros={"name": self.m.suf}, pagina=1, tamanho=1)["total"]  # noqa: E731
        total_regras = minhas()
        for extra, constraint in violacoes:
            with self.assertRaises(RepoViolation) as cm:
                agd.insert(dict(base, **extra),
                            auditoria={"actor": self.m.actor, "ip": None, "action": "CREATE", "detail": "x"})
            self.assertEqual(cm.exception.constraint, constraint, extra)
        self.assertEqual(minhas(), total_regras)
        self.assertEqual(self.obter_repo("audit").list(
            filtros={"action": "CREATE", "actor": self.m.actor}, pagina=1, tamanho=1)["total"], 0)

        novo = agd.insert(base, auditoria={"actor": "admin", "ip": "10.0.0.1", "action": "CREATE",
                                            "detail": "name: Contrato AGD"})
        self.m.note("schedules", novo["id"])
        self.assertEqual(self.aud_last("CREATE", "tbsss_schedules", novo["id"])["actor"], "admin")

        lido = {"name": novo["name"], "user_id": c["u1"]["id"], "next_run_at": novo["next_run_at"]}
        alterado = agd.update(novo["id"], {"name": "TST %s CK2" % self.m.suf, "user_id": c["u2"]["id"]},
                               esperado=lido,
                               auditoria={"actor": "op.prod", "ip": None, "action": "UPDATE", "detail": "y"})
        self.assertEqual((alterado["name"], alterado["user_id"]), ("TST %s CK2" % self.m.suf, c["u2"]["id"]))
        self.assertEqual(self.aud_total("UPDATE", "tbsss_schedules", novo["id"]), 1)
        with self.assertRaises(RepoConflict):
            agd.update(novo["id"], {"name": "Perdedor"}, esperado=lido,
                        auditoria={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "z"})
        with self.assertRaises(RepoViolation):
            agd.update(novo["id"], {"name": "Parcial", "recurrence_type": "MONTHLY"}, ator="teste")
        self.assertEqual(agd.get(novo["id"])["name"], "TST %s CK2" % self.m.suf)
        self.assertEqual(self.aud_total("UPDATE", "tbsss_schedules", novo["id"]), 1)

        agd.pause(novo["id"], "MANUAL", antiga_data=novo["next_run_at"],
                   auditoria={"actor": "admin", "ip": "10.0.0.2", "action": "SCHEDULE_PAUSE", "detail": "p"})
        pausa = self.aud_last("SCHEDULE_PAUSE", "tbsss_schedules", novo["id"])
        self.assertEqual((pausa["actor"], pausa["source_ip"]), ("admin", "10.0.0.2"))

        pausado = {"active": "N", "pause_reason": "MANUAL", "next_run_at": novo["next_run_at"]}
        nova = datetime.datetime(2030, 1, 20, 3, 0)
        with self.assertRaises(RepoConflict):
            agd.resume(novo["id"], nova, esperado=dict(pausado, pause_reason="COMPLETED"),
                        auditoria={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "r"})
        self.assertEqual(agd.get(novo["id"])["active"], "N")
        retomado = agd.resume(novo["id"], nova, esperado=pausado,
                               auditoria={"actor": "admin", "ip": None, "action": "UPDATE", "detail": "r"})
        self.assertEqual((retomado["active"], retomado["pause_reason"], retomado["next_run_at"]), ("Y", None, nova))
        self.assertEqual(self.aud_total("UPDATE", "tbsss_schedules", novo["id"]), 2)

    def test_08_perm_versao_incrementando(self):
        c = self.m.scenario()
        rbac, usr = self.obter_repo("rbac"), self.obter_repo("users")
        p = c["perfil"]
        v0 = rbac.profiles_get(p["id"])["perm_version"]
        rbac.profiles_update(p["id"], {"description": "Nova descricao"}, ator="teste")
        v1 = rbac.profiles_get(p["id"])["perm_version"]
        self.assertEqual(v1, v0 + 1)
        func_ids = [f["id"] for f in rbac.features_list()][:1]
        rbac.matrix_save(p["id"], funcs=func_ids, ambs=[c["amb1"]["id"]], scrs=[c["scr"]["id"]], ator="teste")
        v2 = rbac.profiles_get(p["id"])["perm_version"]
        self.assertEqual(v2, v1 + 1)
        usr.update(c["u1"]["id"], {"active": "N"}, ator="teste")
        self.assertGreaterEqual(rbac.profiles_get(p["id"])["perm_version"], v2 + 1)

    def test_09_paginacao_estavel_e_deterministica(self):
        c = self.m.scenario()
        tck = self.obter_repo("tickets")
        for _ in range(25):
            self.m.ticket(**c["ticket_base"])
        filtros = {"script_id": c["scr"]["id"], "requested_by": c["login"]}
        pag1 = tck.list(filtros=filtros, pagina=1, tamanho=10)
        pag2 = tck.list(filtros=filtros, pagina=2, tamanho=10)
        self.assertEqual((pag1["pagina"], pag1["tamanho"], pag1["total"]), (1, 10, 25))
        self.assertEqual((len(pag1["itens"]), len(pag2["itens"])), (10, 10))
        self.assertTrue({i["id"] for i in pag1["itens"]}.isdisjoint({i["id"] for i in pag2["itens"]}))
        ordem = [(i["created_at"], i["id"]) for i in pag1["itens"] + pag2["itens"]]
        self.assertEqual(ordem, sorted(ordem, reverse=True))
        self.assertEqual([i["id"] for i in pag1["itens"]],
                         [i["id"] for i in tck.list(filtros=filtros, pagina=1, tamanho=10)["itens"]])

    def test_10_escopo_ambientes_na_listagem_tickets(self):
        c = self.m.scenario()
        tck = self.obter_repo("tickets")
        for _ in range(3):
            self.m.ticket(**c["ticket_base"])
        for _ in range(2):
            self.m.ticket(**dict(c["ticket_base"], environment=c["amb2"]["name"]))
        filtros = {"script_id": c["scr"]["id"]}
        lista_a = tck.list(filtros=filtros, escopo_ambientes=[c["amb1"]["name"]], pagina=1, tamanho=50)
        lista_b = tck.list(filtros=filtros, escopo_ambientes=[c["amb2"]["name"]], pagina=1, tamanho=50)
        self.assertEqual({t["environment"] for t in lista_a["itens"]}, {c["amb1"]["name"]})
        self.assertEqual({t["environment"] for t in lista_b["itens"]}, {c["amb2"]["name"]})
        self.assertEqual((lista_a["total"], lista_b["total"]), (3, 2))
        self.assertEqual(tck.list(filtros=filtros, escopo_ambientes=[], pagina=1, tamanho=50)["total"], 0)

    def test_11_log_ler_incremental(self):
        c = self.m.scenario()
        tck = self.obter_repo("tickets")
        log = "".join("linha %02d do log\n" % i for i in range(10))
        tid = self.m.ticket(**dict(c["ticket_base"], status="RUNNING", log_output=log,
                                   started_at=datetime.datetime(2026, 1, 1, 8, 0)))
        texto, prox_off, terminal, truncado = tck.log_read(tid, offset=0, max_chars=20)
        self.assertEqual((texto, prox_off, terminal, truncado), (log[:20], 20, False, False))
        texto2, prox_off2, _, _ = tck.log_read(tid, offset=prox_off, max_chars=20)
        self.assertEqual((texto2, prox_off2), (log[20:40], 40))

    # ------------------------------------------------------------------
    # Colunas de registro (CR-006, README §10, AGENTS §4.15)
    # ------------------------------------------------------------------

    def _check_insert(self, reg, ator):
        self.assertEqual(reg["created_by"], ator)
        self.assertIsNotNone(reg["created_at"])
        self.assertIsNone(reg["updated_at"])
        self.assertIsNone(reg["updated_by"])

    def _check_update(self, antes, depois, ator):
        self.assertEqual(depois["updated_by"], ator)
        self.assertIsNotNone(depois["updated_at"])
        self.assertGreaterEqual(depois["updated_at"], depois["created_at"])
        self.assertEqual((depois["created_at"], depois["created_by"]), (antes["created_at"], antes["created_by"]))

    def test_12_registro_inclusao_e_alteracao_nos_cadastros(self):
        c = self.m.scenario()
        cat, rbac, usr, agd = (self.obter_repo(n) for n in ("catalog", "rbac", "users", "schedules"))
        aud = {"actor": "carla", "ip": "10.0.0.9", "action": "UPDATE", "detail": "registro"}
        suf = self.m.suf

        amb = cat.environments_insert({"name": "TST_%s_REG" % suf, "description": "d"}, ator="ana")
        self.m.note("environments", amb["id"])
        self._check_insert(amb, "ana")
        self._check_update(amb, cat.environments_update(amb["id"], {"description": "e"}, ator="bia"), "bia")
        self._check_update(amb, cat.environments_update(amb["id"], {"description": "f"}, auditoria=aud), "carla")
        self.assertEqual(cat.environments_get(amb["id"])["updated_by"], "carla")

        scr = cat.scripts_insert({"name": "tst_%s_reg" % suf, "interpreter": "SH",
                                   "path_file": "/opt/tst/%s_reg.sh" % suf, "param_type": "NONE"}, ator="ana")
        self.m.note("scripts", scr["id"])
        self._check_insert(scr, "ana")
        self._check_update(scr, cat.scripts_update(scr["id"], {"active": "N"}, ator="bia"), "bia")

        prm = cat.parameters_insert({"code": "tst_%s_reg" % suf, "label": "Reg", "component_type": "TEXT"},
                                     ator="ana")
        self.m.note("parameters", prm["id"])
        self._check_insert(prm, "ana")
        self._check_update(prm, cat.parameters_update(prm["id"], {"label": "Outro"}, ator="bia"), "bia")

        per = rbac.profiles_insert({"name": "TST_%s_REG" % suf}, ator="ana")
        self.m.note("profiles", per["id"])
        self._check_insert(per, "ana")
        self._check_update(per, rbac.profiles_update(per["id"], {"description": "x"}, ator="bia"), "bia")

        u = usr.insert({"login": "tst.%s.reg" % suf, "name": "Reg", "password_hash": "h", "profile_id": per["id"]},
                        ator="ana")
        self.m.note("users", u["id"])
        self._check_insert(u, "ana")
        self._check_update(u, usr.update(u["id"], {"name": "Reg 2"}, ator="bia"), "bia")
        self._check_update(u, usr.set_password(u["id"], "hash-novo", ator="dora"), "dora")
        self._check_update(u, usr.unlock(u["id"], ator="eva"), "eva")

        regra = agd.insert({"name": "TST %s REG" % suf, "script_id": c["scr"]["id"], "environment": c["amb1"]["name"],
                             "user_id": c["u1"]["id"], "priority": 2, "recurrence_type": "DAILY",
                             "run_time": "03:00", "params_json": "{}",
                             "start_date": datetime.datetime(2026, 1, 15, 10, 0),
                             "next_run_at": datetime.datetime(2030, 1, 16, 3, 0)}, ator="ana")
        self.m.note("schedules", regra["id"])
        self._check_insert(regra, "ana")
        editada = agd.update(regra["id"], {"name": "TST %s REG2" % suf, "user_id": c["u2"]["id"]}, ator="op.hml")
        self._check_update(regra, editada, "op.hml")
        self.assertEqual(editada["created_by"], "ana", "o criador original nunca muda (R-g)")
        pausada = agd.pause(regra["id"], "MANUAL", antiga_data=editada["next_run_at"], ator="bia")
        self._check_update(regra, pausada, "bia")
        self._check_update(regra, agd.resume(regra["id"], editada["next_run_at"], ator="carla"), "carla")

    def test_12b_ator_obrigatorio_e_limitado_sem_gravacao_parcial(self):
        c = self.m.scenario()
        cat, usr, tck = self.obter_repo("catalog"), self.obter_repo("users"), self.obter_repo("tickets")
        for ator in (None, "", "x" * 41):
            with self.assertRaises(RepoViolation):
                cat.environments_insert({"name": "TST_%s_SEMATOR" % self.m.suf}, ator=ator)
        self.assertEqual(cat.environments_list(filtros={"name": "TST_%s_SEMATOR" % self.m.suf})["total"], 0)
        antes = cat.environments_get(c["amb1"]["id"])
        with self.assertRaises(RepoViolation):
            cat.environments_update(c["amb1"]["id"], {"description": "nao grava"})
        self.assertEqual(cat.environments_get(c["amb1"]["id"]), antes)
        with self.assertRaises(RepoViolation):
            usr.unlock(c["u1"]["id"])
        tid = self.m.ticket(**c["ticket_base"])
        with self.assertRaises(RepoViolation):
            tck.request_cancel(tid, None, "10.0.0.1")
        self.assertEqual(tck.get(tid)["status"], "PENDING")
        amb40 = cat.environments_insert({"name": "TST_%s_ATOR40" % self.m.suf}, ator="y" * 40)
        self.m.note("environments", amb40["id"])
        self.assertEqual(amb40["created_by"], "y" * 40)

    def test_12c_rotina_tecnica_do_login_nao_grava_updated(self):
        c = self.m.scenario()
        usr = self.obter_repo("users")
        antes = usr.get_by_login(c["login"])
        usr.register_login_failure(c["login"], bloqueio_s=60)
        usr.reset_attempts(antes["id"])
        usr.register_login_success(c["login"], novo_hash=antes["password_hash"])
        depois = usr.get_by_login(c["login"])
        self.assertEqual((depois["updated_at"], depois["updated_by"]), (antes["updated_at"], antes["updated_by"]))
        self.assertEqual(depois["failed_attempts"], 0)

    def test_12d_tickets_criacao_e_cancelamento(self):
        c = self.m.scenario()
        tck = self.obter_repo("tickets")
        base = dict(c["ticket_base"], requested_by=c["u2"]["login"])
        tid = self.m.ticket([{"parameter_id": c["prm_a"]["id"], "answer_value": "2026-10-17"}], **base)
        t = tck.get(tid)
        self._check_insert(t, c["u2"]["login"])
        self.assertEqual([r["created_by"] for r in tck.answers(tid)], [c["u2"]["login"]])
        tid_agd = self.m.ticket(actor="SYSTEM:agt-host01", **base)
        self._check_insert(tck.get(tid_agd), "SYSTEM:agt-host01")

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
        admin = rbac.profiles_list(filtros={"name": "ADMINISTRATOR"})["itens"][0]
        versao = admin["perm_version"]
        for dados in ({"active": "N"}, {"is_admin": "N"}):
            with self.assertRaises(RepoViolation) as ctx:
                rbac.profiles_update(admin["id"], dados,
                                    auditoria={"actor": "admin", "ip": None, "action": "DEACTIVATE", "detail": "x"})
            self.assertEqual(ctx.exception.constraint, "sss_ultimo_admin")
        atual = rbac.profiles_get(admin["id"])
        self.assertEqual((atual["active"], atual["is_admin"], atual["perm_version"]), ("Y", "Y", versao))

    def test_usuario_ultimo_admin_recusado_sem_alterar(self):
        usr = self.obter_repo("users")
        admin = usr.get_by_login("admin")
        consulta = usr.get_by_login("consulta")
        for dados in ({"active": "N"}, {"profile_id": consulta["profile_id"]}):
            with self.assertRaises(RepoViolation) as ctx:
                usr.update(admin["id"], dados, auditoria={"actor": "x", "ip": None, "action": "UPDATE", "detail": "x"})
            self.assertEqual(ctx.exception.constraint, "sss_ultimo_admin")
        atual = usr.get_by_id(admin["id"])
        self.assertEqual((atual["active"], atual["profile_id"]), ("Y", admin["profile_id"]))


class TestRepoContractFake(unittest.TestCase, BaseRepoContractTest):
    """Executa a bateria de contratos contra o backend FAKE."""

    def setUp(self):
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()

    def obter_repo(self, nome):
        return repo_factory.get(nome)

    def test_saida_do_ticket_no_seed(self):
        """CR-012: metadados sem o conteudo; fatias so do DISPONIVEL; o Oracle e testado em test_scheduler_saida."""
        import io
        import zipfile
        tickets = self.obter_repo("tickets")
        self.assertIsNone(tickets.output_get(1))
        meta = tickets.output_get(17)
        self.assertEqual((meta["state"], meta["file_count"]), ("AVAILABLE", 2))
        self.assertNotIn("content", meta)
        lido, off = b"", 0
        while True:
            parte = tickets.output_read(17, off, 100)
            if not parte:
                break
            lido, off = lido + parte, off + len(parte)
        self.assertEqual(len(lido), meta["size_bytes"])
        self.assertEqual(sorted(zipfile.ZipFile(io.BytesIO(lido)).namelist()),
                         ["rejeitados/linhas_rejeitadas.csv", "resumo.txt"])
        self.assertEqual((tickets.output_get(29)["state"], tickets.output_get(29)["reason"]), ("EXCEEDED", "FILES"))
        for tid in (29, 30, 1):
            with self.assertRaises(RepoNotFound):
                tickets.output_read(tid, 0, 10)
        for off, tam in ((-1, 10), (0, 0), (0, 1024 * 1024 + 1)):
            with self.assertRaises(RepoViolation):
                tickets.output_read(17, off, tam)

    # Vinculos por diferenca (CR-006, R-f): o contrato nao le as linhas de vinculo, entao o FAKE e
    # inspecionado direto; no Oracle, o F7.3 confere com SELECT nas tabelas de associacao.
    def _lines(self, tabela, **filtro):
        store = self.obter_repo("catalog")._store
        return dict((tuple(v[c] for c in sorted(v) if c not in ("id", "created_at", "created_by",
                                                                  "updated_at", "updated_by")), v)
                    for v in getattr(store, tabela).values()
                    if all(v.get(k) == x for k, x in filtro.items()))

    def test_12e_vinculos_por_diferenca_preservam_created(self):
        cat = self.obter_repo("catalog")
        rbac = self.obter_repo("rbac")
        sid = 1
        homolog = cat.homologation_get(sid)
        antes = self._lines("script_env", script_id=sid)
        scr_antes = cat.scripts_get(sid)
        cat.homologation_save(sid, homolog, ator="sem-mudanca")
        self.assertEqual(cat.scripts_get(sid)["updated_by"], scr_antes["updated_by"])
        cat.homologation_save(sid, homolog + [3], ator="ana")
        depois = self._lines("script_env", script_id=sid)
        for chave, linha in antes.items():
            self.assertEqual((depois[chave]["created_at"], depois[chave]["created_by"]),
                             (linha["created_at"], linha["created_by"]))
        novo = [v for k, v in depois.items() if k not in antes]
        self.assertEqual([v["created_by"] for v in novo], ["ana"])
        self.assertEqual(cat.scripts_get(sid)["updated_by"], "ana")

        matriz = rbac.matrix_get(4)
        antes = self._lines("profile_env", profile_id=4)
        rbac.matrix_save(4, matriz["funcs"], matriz["ambs"], matriz["scrs"] + [5], ator="bia")
        depois = self._lines("profile_env", profile_id=4)
        self.assertEqual(depois, antes, "dimensao sem mudanca fica intacta")
        self.assertEqual(rbac.profiles_get(4)["updated_by"], "bia")
        self.assertEqual([v["created_by"] for k, v in self._lines("profile_script", profile_id=4).items()
                          if v["script_id"] == 5], ["bia"])

        vinculos = cat.script_params_get(sid)
        self.assertGreaterEqual(len(vinculos), 2)
        antes = dict((v["parameter_id"], v) for v in self._lines("script_param", script_id=sid).values())
        trocados = [dict(parameter_id=v["parameter_id"], sort_order=v["sort_order"], required=v["required"],
                         default_value_override=v.get("default_value_override")) for v in vinculos]
        trocados[0]["sort_order"], trocados[1]["sort_order"] = trocados[1]["sort_order"], trocados[0]["sort_order"]
        cat.script_params_save(sid, trocados, ator="carla")
        depois = dict((v["parameter_id"], v) for v in self._lines("script_param", script_id=sid).values())
        for pid, linha in antes.items():
            self.assertEqual((depois[pid]["created_at"], depois[pid]["created_by"]),
                             (linha["created_at"], linha["created_by"]))
            mudou = pid in (trocados[0]["parameter_id"], trocados[1]["parameter_id"])
            self.assertEqual(depois[pid]["updated_by"], "carla" if mudou else linha["updated_by"])
        self.assertEqual(cat.scripts_get(sid)["updated_by"], "carla")

    def test_12f_finalizacao_simulada_e_do_agente(self):
        tck = self.obter_repo("tickets")
        store = tck._store
        antes = tck.get(11)
        futuro = store.now() + datetime.timedelta(days=1)
        store.set_clock(lambda: futuro)
        tck.log_read(11, offset=0, max_chars=10)
        depois = tck.get(11)
        self.assertEqual(depois["status"], "SUCCESS")
        self.assertEqual(depois["updated_by"], "SYSTEM:%s" % antes["agent_id"])
        self.assertEqual(depois["updated_at"], futuro)
        self.assertEqual(depois["created_by"], antes["created_by"])


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

    def obter_repo(self, nome):
        return repo_factory.get(nome)

    def _clean_fixtures(self):
        """Remove so os registros criados pelo teste, em ordem de dependencia; no modo compartilhado,
        tambem a auditoria deles (README §2.5). Limpeza incompleta falha o teste com os IDs restantes."""
        import _oracle_test_support
        massa = getattr(self, "_fixtures", None)
        if massa is None or not any(massa.created.values()):
            return
        repo = self.obter_repo("catalog")
        compartilhado = _oracle_test_support.schema_mode() == _oracle_test_support.SHARED_MODE
        tab_aud = repo.qualify_table("audit")
        conn = repo._obter_conexao()
        restantes = []
        try:
            cur = conn.cursor()
            try:
                for entidade, ids in massa.created.items():
                    tabela = repo.qualify_table(entidade)
                    for rid in ids:
                        cur.execute("DELETE FROM " + tabela + " WHERE id = :id", {"id": rid})
                        if compartilhado:
                            cur.execute("DELETE FROM " + tab_aud + " WHERE entity = :ent AND entity_id = :id",
                                        {"ent": "tbsss_" + sql_ident.physical(entidade), "id": rid})
                conn.commit()
                for entidade, ids in massa.created.items():
                    tabela = repo.qualify_table(entidade)
                    for rid in ids:
                        cur.execute("SELECT id FROM " + tabela + " WHERE id = :id", {"id": rid})
                        if cur.fetchone():
                            restantes.append((entidade, rid))
            finally:
                cur.close()
        finally:
            conn.close()
        if restantes:
            self.fail("Limpeza incompleta no banco real: %s" % restantes)


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestRepoContractOracle(_OracleContract, unittest.TestCase, BaseRepoContractTest):
    """Executa a mesma bateria contra o Oracle do config.ini, com dados proprios de cada teste."""


class TestLastAdminFake(unittest.TestCase, BaseLastAdminTest):
    """Protecao do ultimo administrador no FAKE (seed com um unico admin ativo)."""

    def setUp(self):
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()

    def obter_repo(self, nome):
        return repo_factory.get(nome)


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
        segredos = object()
        conexao = mock.Mock()
        conexao.cursor.return_value.fetchone.return_value = ("SSS_APP",)
        db_conn_mock = mock.Mock()
        db_conn_mock.connect.return_value = conexao
        sss_config_mock = mock.Mock()
        sss_config_mock.get_config.return_value = cfg
        sss_config_mock.load_secrets.return_value = segredos

        def preparar(env):
            with mock.patch.dict(os.environ, env, clear=True):
                with mock.patch.dict("sys.modules", {"db_conn": db_conn_mock, "sss_config": sss_config_mock}):
                    return prepare_disposable_schema("web")

        # Ligado e autorizado: usa o config da aplicacao, confere a sessao e fecha a conexao.
        self.assertIs(preparar({"SSS_TEST_ORACLE": "1"}), cfg)
        db_conn_mock.connect.assert_called_once_with(cfg, segredos, "web")
        self.assertEqual(conexao.cursor.return_value.execute.call_args[0][0], "SELECT USER FROM DUAL")
        conexao.close.assert_called_once_with()

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
        agregados = ("RBAC_USUARIOS", "CATALOGO", "TICKETS", "AGENDAMENTOS", "AUDITORIA_AGENTES")
        selecionado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if selecionado not in agregados:
            self.skipTest("Factory Oracle progressiva validada pelo prompt F7.3")
        indice = agregados.index(selecionado)
        if indice == len(agregados) - 1:
            self.skipTest("Todos os agregados estao registrados; rodar a bateria Oracle integrada")
        proximos = ("catalog", "tickets", "schedules", "audit")
        with self.assertRaises(NotImplementedError) as ctx:
            repo_factory.get(proximos[indice])
        self.assertIn("Backend ORACLE ainda nao implementado", str(ctx.exception))

    def test_nenhum_import_repo_fake_fora_de_repo_factory(self):
        """Verifica que nenhum modulo ou script fora de repo_factory importa repo_fake."""
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pattern = re.compile(r"^\s*(from|import)\s+.*repo_fake.*", re.MULTILINE)

        arquivos_violadores = []
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
                caminho = os.path.join(root, f)
                rel_path = os.path.relpath(caminho, app_dir)
                if rel_path == "modules/repo_factory.py":
                    continue

                with open(caminho, "r", encoding="utf-8") as arq:
                    conteudo = arq.read()
                    if pattern.search(conteudo):
                        arquivos_violadores.append(rel_path)

        self.assertEqual(
            arquivos_violadores, [],
            "Arquivos fora de repo_factory.py importando repo_fake: %s" % arquivos_violadores
        )

    def test_paridade_estrita_sem_metodos_extras_no_fake(self):
        """Verifica que as classes Fake nao expõem metodos publicos alem dos contratos."""
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()

        pares = [
            (RepoUsers, repo_factory.get("users")),
            (RepoRbac, repo_factory.get("rbac")),
            (RepoCatalog, repo_factory.get("catalog")),
            (RepoTickets, repo_factory.get("tickets")),
            (RepoSchedules, repo_factory.get("schedules")),
            (RepoAudit, repo_factory.get("audit")),
            (RepoAgents, repo_factory.get("agents")),
        ]

        for contrato_cls, fake_inst in pares:
            metodos_contrato = {
                m for m in dir(contrato_cls)
                if not m.startswith("_") and callable(getattr(contrato_cls, m))
            }
            metodos_fake = {
                m for m in dir(fake_inst)
                if not m.startswith("_") and callable(getattr(fake_inst, m))
            }

            extras = metodos_fake - metodos_contrato
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
            usr.list(pagina="abc")
        with self.assertRaises(TypeError):
            usr.list(tamanho=[])
        pag = usr.list(pagina=None, tamanho=None)
        self.assertEqual((pag["pagina"], pag["tamanho"]), (1, 20))
        pag = usr.list(pagina="0", tamanho="-5")
        self.assertEqual((pag["pagina"], pag["tamanho"]), (1, 20))

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
