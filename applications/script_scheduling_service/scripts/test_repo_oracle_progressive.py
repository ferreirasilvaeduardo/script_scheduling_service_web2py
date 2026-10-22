# -*- coding: utf-8 -*-
"""Testes progressivos para os repositorios Oracle 11gR2 (F7.3).

Executa a validacao do agregado ativo selecionado por SSS_TEST_REPO_AGREGADO:
1. RBAC_USUARIOS -> TestOracleRbacUsers
2. CATALOGO -> TestOracleCatalog
3. TICKETS -> TestOracleTickets
4. AGENDAMENTOS -> TestOracleSchedules
5. AUDITORIA_AGENTES -> TestOracleAuditAgents
"""
import datetime
import os
import sys
import unittest
from unittest import mock

import _oracle_test_support
import _testenv  # noqa: F401
import db_conn
import repo_errors
import repo_factory
import sql_ident
from repo_catalog import RepoCatalog
from repo_oracle.catalog import RepoCatalogOracle
from repo_rbac import RepoRbac
from repo_oracle.agents import RepoAgentsOracle
from repo_oracle.audit import RepoAuditOracle
from repo_schedules import RepoSchedules
from repo_oracle.schedules import RepoSchedulesOracle
from repo_oracle.tickets import RepoTicketsOracle
from repo_tickets import RepoTickets
from repo_users import RepoUsers
from gluon import current


def _prepare_real_db(cls):
    """Valida o banco real (modo descartavel ou compartilhado) antes de qualquer DML.

    Com banco real, o cfg validado vai para current.sss_cfg durante a classe (os repositorios Oracle
    leem owner, prefixo, DSN e segredos dele) e e restaurado no tearDownClass.
    """
    cls.tem_banco_real = _oracle_test_support.real_db_configured()
    cls._tinha_sss_cfg = hasattr(current, "sss_cfg")
    cls._previous_sss_cfg = getattr(current, "sss_cfg", None)
    if cls.tem_banco_real:
        cls.cfg = _oracle_test_support.prepare_disposable_schema("web")
        current.sss_cfg = cls.cfg
    repo_factory.configure({"app": {"data_backend": "ORACLE", "sss_env": "DEV"}})


def _restore_real_db(cls):
    repo_factory.configure(None)
    repo_factory.reset_singletons()
    if cls._tinha_sss_cfg:
        current.sss_cfg = cls._previous_sss_cfg
    elif hasattr(current, "sss_cfg"):
        delattr(current, "sss_cfg")


class TestOracleRbacUsers(unittest.TestCase):
    """Testes de conformidade e integridade para o agregado RBAC_USUARIOS no Oracle."""

    @classmethod
    def setUpClass(cls):
        aggregate = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if aggregate != "RBAC_USUARIOS":
            raise unittest.SkipTest("Execucao restrita ao agregado RBAC_USUARIOS (atual: %s)" % aggregate)

        _prepare_real_db(cls)

    @classmethod
    def tearDownClass(cls):
        _restore_real_db(cls)

    def setUp(self):
        repo_factory.reset_singletons()
        self.usr = repo_factory.get("users")
        self.rbac = repo_factory.get("rbac")

    def test_instancias_corretas_do_agregado(self):
        """Valida que repo_factory devolve as implementacoes Oracle corretas."""
        self.assertIsInstance(self.usr, RepoUsers)
        self.assertIsInstance(self.rbac, RepoRbac)
        self.assertEqual(self.usr.__class__.__name__, "RepoUsersOracle")
        self.assertEqual(self.rbac.__class__.__name__, "RepoRbacOracle")


    def test_ator_obrigatorio_usuarios_e_perfis(self):
        """Valida que insercao e alteracao sem ator ou com ator longo lancam RepoViolation."""
        for actor_invalid in (None, "", "   ", "x" * 41):
            with self.assertRaises(repo_errors.RepoViolation):
                self.usr.insert({"login": "novo.user", "profile_id": 1}, actor=actor_invalid)
            with self.assertRaises(repo_errors.RepoViolation):
                self.rbac.profiles_insert({"name": "Novo Perfil"}, actor=actor_invalid)
            with self.assertRaises(repo_errors.RepoViolation):
                self.usr.unlock(1, actor=actor_invalid)

    def test_alterar_sem_data_nao_declara_bind_de_data_ausente(self):
        """Regressao (F7.3): alterar so o nome declarava bloqueado_ate/ultimo_login e caia em DPY-4008."""
        import repo_oracle.users as mod
        line = tuple(1 if c in ("id", "profile_id") else ("Y" if c == "active" else
                      ("tst.x" if c == "login" else (0 if c in ("failed_attempts", "session_epoch") else None)))
                      for c in mod._COLS_USER)
        conn = _ScriptedConnection([("FOR UPDATE OF u.active WAIT 5", 1, [line + ("Y", "N")]), ("UPDATE", 1, []),
                                    ("SELECT", 1, [line])])
        with mock.patch.object(self.usr, "_obter_conexao", return_value=conn):
            self.usr.update(1, {"name": "Novo nome"}, actor="ana")
        upd = [sql for sql, _b in conn.executed if sql.startswith("UPDATE")]
        self.assertTrue(upd and ":locked_until" not in upd[0])
        self.assertEqual(conn.commits, 1)

    def test_login_invalido_recusado(self):
        """Valida regex de login em tbsss_users."""
        for log_inv in ("ab", "AB_USER", "user com espaco", "u" * 31, "usr@dominio"):
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                self.usr.insert({"login": log_inv, "profile_id": 1}, actor="admin")
            self.assertEqual(ctx.exception.constraint, self.usr.constraint_name("ck", "users", "login"))

    def test_banco_real_rbac_usuarios(self):
        """Executa ciclo completo no banco Oracle real quando configurado em DEV descartavel."""
        if not self.tem_banco_real:
            self.skipTest("Banco descartavel real nao configurado (marcado como NAO TESTADO)")

        actor_test = "teste_agregado"
        prefix = "tst_%d" % int(datetime.datetime.now().strftime("%H%M%S"))

        # 1. Cria perfil
        name_profile = ("P_%s" % prefix)[:30]
        prf = self.rbac.profiles_insert({
            "name": name_profile,
            "description": "Perfil temporario de teste progressivo",
            "is_admin": "N",
            "active": "Y",
        }, actor=actor_test)
        self.assertIsNotNone(prf.get("id"))
        pid = prf["id"]

        try:
            # 2. Cria usuario associado
            login = ("u_%s" % prefix)[:30].lower()
            usr = self.usr.insert({
                "login": login,
                "name": "Usuario de Teste",
                "password_hash": "hash_fake_123",
                "profile_id": pid,
                "active": "Y",
            }, actor=actor_test)
            self.assertIsNotNone(usr.get("id"))
            uid = usr["id"]

            # 3. Teste do relogio do banco sem microssegundos
            dt_db = self.usr.now()
            self.assertEqual(dt_db.microsecond, 0)

            # 4. Estado da sessao
            sess = self.usr.get_session_state(uid)
            self.assertEqual(sess["login"], login)
            self.assertEqual(sess["profile_id"], pid)
            self.assertEqual(sess["session_epoch"], 0)

            # 5. Logout incrementa session_epoch
            self.usr.end_sessions(uid, audit={"actor": actor_test, "action": "LOGOUT"})
            sess2 = self.usr.get_session_state(uid)
            self.assertEqual(sess2["session_epoch"], 1)

            # 6. Falha e sucesso de login
            self.usr.register_login_failure(login, lockout_s=300)
            u_failure = self.usr.get_by_id(uid)
            self.assertEqual(u_failure["failed_attempts"], 1)
            self.assertIsNotNone(u_failure["locked_until"])

            self.usr.register_login_success(login, new_hash="hash_rehash_456")
            u_ok = self.usr.get_by_id(uid)
            self.assertEqual(u_ok["failed_attempts"], 0)
            self.assertIsNone(u_ok["locked_until"])
            self.assertEqual(u_ok["password_hash"], "hash_rehash_456")

            # 7. Imutabilidade do login
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                self.usr.update(uid, {"login": "outro_login"}, actor=actor_test)
            self.assertEqual(ctx.exception.constraint, "tr_tbsss_usr_bu")

            # 8. Unicidade de UKs
            with self.assertRaises(repo_errors.RepoViolation):
                self.usr.insert({"login": login, "profile_id": pid}, actor=actor_test)
            with self.assertRaises(repo_errors.RepoViolation):
                self.rbac.profiles_insert({"name": name_profile}, actor=actor_test)

        finally:
            # Limpeza cirurgica no schema descartavel
            conn = self.usr._obter_conexao()
            try:
                cur = conn.cursor()
                try:
                    cur.execute("DELETE FROM " + self.usr._tabela() + " WHERE id = :id", {"id": uid})
                    if _oracle_test_support.schema_mode() == _oracle_test_support.SHARED_MODE:
                        # encerrar_sessoes audita o LOGOUT do usuario do teste: so essa auditoria sai.
                        cur.execute("DELETE FROM " + self.rbac._tabela_auditoria() + " WHERE entity = "
                                    "'tbsss_users' AND entity_id = :id", {"id": uid})
                    cur.execute("DELETE FROM " + self.rbac._tabela_perfis() + " WHERE id = :id", {"id": pid})
                    conn.commit()
                finally:
                    cur.close()
            finally:
                conn.close()


class _RecordingCursor(object):
    """Cursor de mentira: registra o SQL e devolve as linhas programadas, sem banco."""

    def __init__(self, rows=None, once=None):
        self.executed = []
        self._lines = list(rows or [])
        self._uma = once
        self.rowcount = 1

    def execute(self, sql, binds=None):
        self.executed.append((sql, binds))

    def fetchall(self):
        return list(self._lines)

    def fetchone(self):
        return self._uma

    def close(self):
        pass


class _RecordingConnection(object):
    def __init__(self, cursor):
        self.cursor_ = cursor

    def cursor(self):
        return self.cursor_

    def close(self):
        pass


class TestOracleCatalog(unittest.TestCase):
    """Testes de conformidade e integridade para o agregado CATALOGO no Oracle (passo 2 do F7.3)."""

    @classmethod
    def setUpClass(cls):
        aggregate = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if aggregate != "CATALOGO":
            raise unittest.SkipTest("Execucao restrita ao agregado CATALOGO (atual: %s)" % aggregate)

        _prepare_real_db(cls)

    @classmethod
    def tearDownClass(cls):
        _restore_real_db(cls)

    def setUp(self):
        repo_factory.reset_singletons()
        self.cat = repo_factory.get("catalog")

    # ------------------------------------------------------------- sem banco

    def test_instancia_correta_do_agregado(self):
        """repo_factory devolve a implementacao Oracle do catalogo; RBAC_USUARIOS continua registrado."""
        self.assertIsInstance(self.cat, RepoCatalog)
        self.assertEqual(self.cat.__class__.__name__, "RepoCatalogOracle")
        self.assertEqual(repo_factory.get("users").__class__.__name__, "RepoUsersOracle")


    def test_sql_qualificado_sem_marcadores_pendentes(self):
        """Todo SQL montado na carga usa o owner qualificado e nenhum marcador sobra."""
        self.assertTrue(self.cat._sql)
        for name, sql in self.cat._sql.items():
            self.assertNotIn("{", sql, name)
            self.assertNotIn("SELECT *", sql, name)
            if "FOR UPDATE" in sql:
                self.assertIn("FOR UPDATE WAIT 5", sql, name)
        self.assertIn(self.cat.qualify_table("scripts"), self.cat._sql["SCR_GET"])

    def test_owner_e_prefixo_parametrizados(self):
        """Owner e table_prefix vem da configuracao: SQL, sequences e constraints seguem o prefixo."""
        cfg = mock.Mock()
        cfg.oracle.owner = "SSS_TEST_CAT"
        cfg.oracle.table_prefix = "abc_"
        repo = RepoCatalogOracle(cfg=cfg, secrets={})
        for name, sql in repo._sql.items():
            self.assertNotIn("tbsss_", sql, name)
        self.assertIn("SSS_TEST_CAT.abc_scripts", repo._sql["SCR_GET"])
        self.assertIn("SSS_TEST_CAT.abc_profile_script", repo._sql["EXEC_PROFILE"])
        self.assertEqual(repo._seq["script_param"], "SSS_TEST_CAT.sq_abc_script_param")
        with mock.patch.object(repo, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                repo.scripts_insert({"name": "s", "interpreter": "SH", "path_file": "x.sh"}, actor="t")
        self.assertEqual(ctx.exception.constraint, "ck_abc_scr_path")

    def test_ator_obrigatorio_antes_de_qualquer_sql(self):
        """Sem ator (ou com mais de 40 caracteres), RepoViolation sem abrir conexao."""
        with mock.patch.object(self.cat, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            for actor_invalid in (None, "", "   ", "x" * 41):
                for call in (
                    lambda a: self.cat.environments_insert({"name": "AMB_X"}, actor=a),
                    lambda a: self.cat.environments_update(1, {"description": "x"}, actor=a),
                    lambda a: self.cat.scripts_insert({"name": "s", "interpreter": "SH",
                                                        "path_file": "/opt/s.sh"}, actor=a),
                    lambda a: self.cat.scripts_update(1, {"description": "x"}, actor=a),
                    lambda a: self.cat.homologation_save(1, [1], actor=a),
                    lambda a: self.cat.parameters_insert({"code": "p", "component_type": "TEXT"}, actor=a),
                    lambda a: self.cat.parameters_update(1, {"label": "x"}, actor=a),
                    lambda a: self.cat.script_params_save(1, [], actor=a),
                ):
                    with self.assertRaises(repo_errors.RepoViolation):
                        call(actor_invalid)

    def test_cks_recusadas_antes_do_banco_com_nome_do_fake(self):
        """CKs de nome, caminho, interpretador, paralelismo e codigo devolvem o nome da constraint do FAKE."""
        n = self.cat.constraint_name
        with mock.patch.object(self.cat, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            cases = (
                (lambda: self.cat.environments_insert({"name": "minusculo"}, actor="t"), n("ck", "environments", "name")),
                (lambda: self.cat.scripts_insert({"name": "s", "interpreter": "SH",
                                                   "path_file": "relativo.sh"}, actor="t"), n("ck", "scripts", "path")),
                (lambda: self.cat.scripts_insert({"name": "s", "interpreter": "SH",
                                                   "path_file": "/opt/../x.sh"}, actor="t"), n("ck", "scripts", "path")),
                (lambda: self.cat.scripts_insert({"name": "s", "interpreter": "SH",
                                                   "path_file": "/" + "a" * 500}, actor="t"), n("ck", "scripts", "path")),
                (lambda: self.cat.scripts_insert({"name": "s", "interpreter": "PERL",
                                                   "path_file": "/opt/s.pl"}, actor="t"), n("ck", "scripts", "int")),
                (lambda: self.cat.scripts_insert({"name": "s", "interpreter": "SH", "path_file": "/opt/s.sh",
                                                   "max_parallel_env": 0}, actor="t"), n("ck", "scripts", "paral")),
                (lambda: self.cat.parameters_insert({"code": "Maiusc", "component_type": "TEXT"},
                                                     actor="t"), n("ck", "parameters", "code")),
            )
            for call, ck in cases:
                with self.assertRaises(repo_errors.RepoViolation) as ctx:
                    call()
                self.assertEqual(ctx.exception.constraint, ck)

    def test_scripts_executaveis_sem_exec_script_nao_consulta(self):
        """Nao admin sem EXEC_SCRIPT (ou sem perfil) recebe lista vazia sem ir ao banco."""
        with mock.patch.object(self.cat, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            self.assertEqual(self.cat.executable_scripts({"is_admin": False, "profile_id": 3,
                                                           "features": frozenset()}), [])
            self.assertEqual(self.cat.executable_scripts({"is_admin": False,
                                                           "features": frozenset(["EXEC_SCRIPT"])}), [])

    def test_scripts_executaveis_uma_consulta_por_perfil_ou_admin(self):
        """Uma unica consulta: EXISTS em perfil_scr/perfil_amb pelo perfil_id, ou o atalho do admin."""
        cur = _RecordingCursor()
        with mock.patch.object(self.cat, "_obter_conexao", return_value=_RecordingConnection(cur)):
            self.cat.executable_scripts({"is_admin": False, "profile_id": 7,
                                          "features": frozenset(["EXEC_SCRIPT"])})
            self.cat.executable_scripts({"is_admin": True})
        self.assertEqual(len(cur.executed), 2)
        sql_profile, binds_profile = cur.executed[0]
        self.assertIn(self.cat.qualify_table("profile_script"), sql_profile)
        self.assertIn(self.cat.qualify_table("profile_env"), sql_profile)
        self.assertEqual(binds_profile, {"profile_id": 7})
        sql_admin, binds_admin = cur.executed[1]
        self.assertNotIn(self.cat.qualify_table("profile_script"), sql_admin)
        self.assertIn(self.cat.qualify_table("script_env"), sql_admin)
        self.assertIsNone(binds_admin)

    def test_filtro_de_trecho_escapa_curingas(self):
        """'%' e '_' digitados no filtro sao literais (paridade com o 'in' do FAKE), sempre por bind."""
        cur = _RecordingCursor(once=(0,))
        with mock.patch.object(self.cat, "_obter_conexao", return_value=_RecordingConnection(cur)):
            self.cat.scripts_list(filters={"name": "carga_10%"})
        sql_count_tpl, binds = cur.executed[0]
        self.assertIn("ROWNUM <= 10001", sql_count_tpl)
        self.assertIn("ESCAPE", sql_count_tpl)
        self.assertEqual(binds["name_f"], "%carga\\_10\\%%")
        self.assertNotIn("carga", sql_count_tpl)

    # ------------------------------------------------------------- banco real

    def _clean(self, ids):
        """Remove somente os registros criados por este teste, em transacao propria."""
        conn = self.cat._obter_conexao()
        remaining = []
        try:
            cur = conn.cursor()
            try:
                for table, key in (("script_param", "script_id"), ("script_env", "script_id"),
                                      ("scripts", "id"), ("parameters", "id"), ("environments", "id")):
                    for value in ids.get(table, ()):
                        cur.execute("DELETE FROM " + self.cat.qualify_table(table) + " WHERE "
                                    + key + " = :v", {"v": value})
                conn.commit()
                for table in ("scripts", "parameters", "environments"):
                    for value in ids.get(table, ()):
                        cur.execute("SELECT id FROM " + self.cat.qualify_table(table) + " WHERE id = :v",
                                    {"v": value})
                        if cur.fetchone():
                            remaining.append((table, value))
            finally:
                cur.close()
        finally:
            conn.close()
        if remaining:
            self.fail("Limpeza incompleta no schema descartavel: %s" % remaining)

    def test_banco_real_catalogo(self):
        """Ciclo completo no Oracle descartavel: CRUD, esperado, UKs, vinculos por diferenca e executaveis."""
        if not self.tem_banco_real:
            self.skipTest("Banco descartavel real nao configurado (marcado como NAO TESTADO)")

        n = self.cat.constraint_name
        actor = "teste_catalogo"
        suffix = datetime.datetime.now().strftime("%H%M%S")
        ids = {"environments": [], "scripts": [], "parameters": []}
        ids["script_param"] = ids["scripts"]
        ids["script_env"] = ids["scripts"]
        try:
            # 1. Ambientes: inclusao, registro, UK, imutabilidade e esperado.
            env = self.cat.environments_insert({"name": "TST_" + suffix, "description": "a"}, actor=actor)
            ids["environments"].append(env["id"])
            self.assertEqual(env["created_by"], actor)
            self.assertIsNone(env["updated_at"])
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                self.cat.environments_insert({"name": "TST_" + suffix}, actor=actor)
            self.assertEqual(ctx.exception.constraint, n("uk", "environments", "name"))
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                self.cat.environments_update(env["id"], {"name": "OUTRO_" + suffix}, actor=actor)
            self.assertEqual(ctx.exception.constraint, self.cat.trigger_name("environments", "bu"))
            with self.assertRaises(repo_errors.RepoConflict):
                self.cat.environments_update(env["id"], {"description": "b"}, expected={"description": "z"}, actor=actor)
            alt = self.cat.environments_update(env["id"], {"description": "b"}, expected={"description": "a"}, actor="bia")
            self.assertEqual((alt["description"], alt["updated_by"], alt["created_by"]), ("b", "bia", actor))
            self.assertEqual(alt["created_at"].microsecond, 0)

            # 2. Scripts: UK sensivel a maiusculas, path_file absoluto e esperado nulo-seguro.
            name_scr = "Tst_Scr_" + suffix
            scr = self.cat.scripts_insert({"name": name_scr, "interpreter": "SH", "param_type": "NAMED",
                                            "path_file": "/opt/sss_teste/" + suffix + ".sh"}, actor=actor)
            ids["scripts"].append(scr["id"])
            other = self.cat.scripts_insert({"name": name_scr.lower(), "interpreter": "SH",
                                              "path_file": "/opt/sss_teste/b.sh"}, actor=actor)
            ids["scripts"].append(other["id"])
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                self.cat.scripts_insert({"name": name_scr, "interpreter": "SH",
                                          "path_file": "/opt/sss_teste/c.sh"}, actor=actor)
            self.assertEqual(ctx.exception.constraint, n("uk", "scripts", "name"))
            alt = self.cat.scripts_update(scr["id"], {"script_group": "G1"}, expected={"script_group": None,
                                                                                  "path_file": scr["path_file"]},
                                           actor=actor)
            self.assertEqual(alt["script_group"], "G1")
            self.assertEqual(alt["updated_by"], actor)

            # 3. Homologacao por diferenca: vinculo que continua mantem o created_*.
            self.assertEqual(self.cat.homologation_save(scr["id"], [env["id"]], expected=[], actor=actor),
                             [env["id"]])
            with self.assertRaises(repo_errors.RepoConflict):
                self.cat.homologation_save(scr["id"], [], expected=[], actor=actor)
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                self.cat.homologation_save(scr["id"], [env["id"], 999999999], actor=actor)
            self.assertEqual(ctx.exception.constraint, n("fk", "script_env", "env"))

            # 4. Parametros e vinculos: NOMEADO exige flag; created_* preservado; dependencias.
            without_flag = self.cat.parameters_insert({"code": "tst_sf_" + suffix, "label": "X",
                                                    "component_type": "TEXT"}, actor=actor)
            ids["parameters"].append(without_flag["id"])
            with_flag = self.cat.parameters_insert({"code": "tst_cf_" + suffix, "label": "Y",
                                                    "component_type": "TEXT", "param_flag": "--y"}, actor=actor)
            ids["parameters"].append(with_flag["id"])
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                self.cat.script_params_save(scr["id"], [{"parameter_id": without_flag["id"], "sort_order": 1}], actor=actor)
            self.assertEqual(ctx.exception.constraint, "sss_scr_nomeado_sem_flag")
            v1 = self.cat.script_params_save(scr["id"], [{"parameter_id": with_flag["id"], "sort_order": 1,
                                                            "required": "Y"}], expected=[], actor=actor)
            self.assertEqual([v["parameter_id"] for v in v1], [with_flag["id"]])
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                self.cat.parameters_update(with_flag["id"], {"component_type": "NUMBER"}, actor=actor)
            self.assertEqual(ctx.exception.constraint, "sss_prm_tipo_vinculado")
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                self.cat.parameters_update(with_flag["id"], {"active": "N"}, actor=actor)
            self.assertEqual(ctx.exception.constraint, "sss_prm_vinculo_ativo")
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                self.cat.scripts_update(scr["id"], {"param_type": "NONE"}, actor=actor)
            self.assertEqual(ctx.exception.constraint, "sss_scr_nenhum_vinculado")
            self.assertEqual(self.cat.scripts_get(scr["id"])["param_type"], "NAMED")

            conn = self.cat._obter_conexao()
            try:
                cur = conn.cursor()
                try:
                    sql = ("SELECT created_at, created_by FROM " + self.cat.qualify_table("script_param")
                           + " WHERE script_id = :s AND parameter_id = :p")
                    cur.execute(sql, {"s": scr["id"], "p": with_flag["id"]})
                    created_before = cur.fetchone()
                finally:
                    cur.close()
            finally:
                conn.close()
            self.cat.script_params_save(scr["id"], [{"parameter_id": with_flag["id"], "sort_order": 1,
                                                       "required": "Y"}],
                                          expected=[(with_flag["id"], 1, "Y", None)], actor="outro")
            conn = self.cat._obter_conexao()
            try:
                cur = conn.cursor()
                try:
                    cur.execute(sql, {"s": scr["id"], "p": with_flag["id"]})
                    self.assertEqual(cur.fetchone(), created_before)
                finally:
                    cur.close()
            finally:
                conn.close()

            # 5. Listagens: total limitado, contagens e homologados na mesma leitura.
            items = self.cat.scripts_list(filters={"name": name_scr})
            self.assertIn("total_capped", items)
            item = [i for i in items["items"] if i["id"] == scr["id"]][0]
            self.assertEqual(item["homologated_environments"], [env["name"]])
            self.assertEqual(item["param_count"], 1)
            prm = self.cat.parameters_list(filters={"code": "tst_cf_" + suffix})["items"][0]
            self.assertEqual(prm["script_count"], len(self.cat.parameter_links(with_flag["id"])))

            # 6. Executaveis do admin: script ativo homologado em ambiente ativo.
            executables = [s["id"] for s in self.cat.executable_scripts({"is_admin": True})]
            self.assertIn(scr["id"], executables)
            self.assertNotIn(other["id"], executables)
        finally:
            self._clean(ids)


class _ScriptedCursor(object):
    """Cursor de mentira que responde por trecho do SQL: roteiro = [(trecho, rowcount, linhas)]."""

    def __init__(self, connection):
        self._conexao = connection
        self.rowcount = 0
        self._lines = []

    def execute(self, sql, binds=None):
        # Como o python-oracledb (DPY-4008): tipo declarado para bind que nao existe no SQL.
        for name in getattr(self, "_tipos", {}):
            if ":" + name not in sql:
                raise RuntimeError("DPY-4008: no bind placeholder named \":%s\" was found in the SQL text" % name)
        self._tipos = {}
        self._conexao.executed.append((sql, binds))
        if ".NEXTVAL FROM DUAL" in sql:
            self._conexao.seq += 1
            self.rowcount, self._lines = 1, [(self._conexao.seq,)]
            return
        for snippet, rowcount, rows in self._conexao.script_steps:
            if snippet in sql:
                self.rowcount, self._lines = rowcount, list(rows)
                return
        self.rowcount, self._lines = 0, []

    def setinputsizes(self, **types):
        self._tipos = types

    def fetchone(self):
        return self._lines[0] if self._lines else None

    def fetchall(self):
        return list(self._lines)

    def fetchmany(self, n):
        batch, self._lines = self._lines[:n], self._lines[n:]
        return batch

    def close(self):
        pass


class _ScriptedConnection(object):
    def __init__(self, script_steps):
        self.script_steps = script_steps
        self.executed = []
        self.seq = 1000
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _ScriptedCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass

    def audits(self):
        return [b for sql, b in self.executed if sql.startswith("INSERT INTO") and "audit" in sql]


class TestOracleTickets(unittest.TestCase):
    """Testes de conformidade e integridade para o agregado TICKETS no Oracle (passo 3 do F7.3)."""

    @classmethod
    def setUpClass(cls):
        aggregate = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if aggregate != "TICKETS":
            raise unittest.SkipTest("Execucao restrita ao agregado TICKETS (atual: %s)" % aggregate)
        _prepare_real_db(cls)

    @classmethod
    def tearDownClass(cls):
        _restore_real_db(cls)

    def setUp(self):
        repo_factory.reset_singletons()
        self.tck = repo_factory.get("tickets")

    # ------------------------------------------------------------- sem banco

    def test_instancia_correta_do_agregado(self):
        """repo_factory devolve a implementacao Oracle de tickets; os agregados anteriores continuam."""
        self.assertIsInstance(self.tck, RepoTickets)
        self.assertEqual(self.tck.__class__.__name__, "RepoTicketsOracle")
        self.assertEqual(repo_factory.get("catalog").__class__.__name__, "RepoCatalogOracle")
        self.assertEqual(repo_factory.get("users").__class__.__name__, "RepoUsersOracle")


    def test_owner_e_prefixo_parametrizados(self):
        """SQL, sequences e constraints seguem owner e table_prefix da configuracao."""
        cfg = mock.Mock()
        cfg.oracle.owner = "SSS_TEST_TCK"
        cfg.oracle.table_prefix = "abc_"
        repo = RepoTicketsOracle(cfg=cfg, secrets={})
        for name, sql in repo._sql.items():
            self.assertNotIn("tbsss_", sql, name)
            self.assertNotIn("SELECT *", sql, name)
        self.assertIn("SSS_TEST_TCK.abc_tickets", repo._sql["GET"])
        self.assertEqual(repo._seq_tck, "SSS_TEST_TCK.sq_abc_tickets")
        with mock.patch.object(repo, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                repo.create({"script_id": 1, "environment": "X", "requested_by": "u", "priority": 9}, [])
        self.assertEqual(ctx.exception.constraint, "ck_abc_tck_prio")

    def test_cancelamento_usa_os_updates_literais_do_readme(self):
        """README §5.6: os dois UPDATEs e a leitura pela PK com FOR UPDATE WAIT 5."""
        tck = self.tck._idents["tck"]
        self.assertEqual(self.tck._sql["CANCEL_SIGNAL"],
                         "UPDATE " + tck + " SET cancel_requested = 'Y', updated_at = SYSDATE, updated_by = :actor "
                         "WHERE id = :id AND status IN ('PENDING', 'RUNNING') AND cancel_requested = 'N'")
        self.assertEqual(self.tck._sql["CANCEL_PENDING"],
                         "UPDATE " + tck + " SET status = 'CANCELLED', status_reason = 'CANCEL_USER', "
                         "return_code = -1, finished_at = SYSDATE, updated_at = SYSDATE, updated_by = :actor "
                         "WHERE id = :id AND status = 'PENDING'")
        self.assertTrue(self.tck._sql["CANCEL_READ"].endswith("WHERE id = :id FOR UPDATE WAIT 5"))

    def test_listagens_e_leituras_do_cr004_sem_clob(self):
        """Nenhuma listagem le CLOB; obter traz parametros_enviados mas nunca log_output."""
        for template in ("_SQL_LIST", "_SQL_COUNT", "_SQL_LAST", "_SQL_HISTORY", "_SQL_ANSWERS"):
            sql = getattr(sys.modules[RepoTicketsOracle.__module__], template)
            self.assertNotIn("log_output", sql, template)
            self.assertNotIn("submitted_params", sql, template)
        self.assertNotIn("log_output", self.tck._sql["GET"])
        self.assertIn("submitted_params", self.tck._sql["GET"])
        self.assertIn("ROW_NUMBER() OVER (PARTITION BY t.script_id ORDER BY t.created_at DESC, t.id DESC)",
                      sys.modules[RepoTicketsOracle.__module__]._SQL_LAST)

    def test_ator_obrigatorio_antes_de_qualquer_sql(self):
        with mock.patch.object(self.tck, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            for actor in (None, "", "   ", "x" * 41):
                with self.assertRaises(repo_errors.RepoViolation):
                    self.tck.create({"script_id": 1, "environment": "X", "requested_by": actor}, [], actor=actor)
                with self.assertRaises(repo_errors.RepoViolation):
                    self.tck.request_cancel(1, actor, "127.0.0.1")

    def _cancel_with(self, script_steps):
        conn = _ScriptedConnection(script_steps)
        with mock.patch.object(self.tck, "_obter_conexao", return_value=conn):
            return_value = self.tck.request_cancel(7, "ana", "10.0.0.1")
        return return_value, conn

    def test_cancelamento_nos_quatro_resultados_e_residuo_pending(self):
        """Cada desfecho do §5.6 audita TICKET_CANCEL com o resultado, numa transacao confirmada."""
        cases = (
            # PENDING: sinaliza e cancela.
            ([("cancel_requested = 'Y', updated_at", 1, []), ("SET status = 'CANCELLED'", 1, [])],
             "CANCELADO", u"resultado: cancelado"),
            # RUNNING: so sinaliza.
            ([("cancel_requested = 'Y', updated_at", 1, []), ("SET status = 'CANCELLED'", 0, [])],
             "SINALIZADO", u"resultado: sinalizado"),
            # RUNNING ja sinalizado.
            ([("FOR UPDATE WAIT 5", 1, [("RUNNING", "Y")])], "JA_SINALIZADO", u"resultado: já sinalizado"),
            # Terminal.
            ([("FOR UPDATE WAIT 5", 1, [("SUCCESS", "N")])], "TERMINAL",
             u"resultado: sem efeito: ticket encerrado"),
            # Residuo PENDING com cancel_requested = 'S' (CR-008, R-02): cancelado pelo segundo UPDATE.
            ([("FOR UPDATE WAIT 5", 1, [("PENDING", "Y")]), ("SET status = 'CANCELLED'", 1, [])],
             "CANCELADO", u"resultado: cancelado"),
        )
        for script_steps, expected, detail in cases:
            return_value, conn = self._cancel_with(script_steps)
            self.assertEqual(return_value, expected)
            auds = conn.audits()
            self.assertEqual(len(auds), 1)
            self.assertEqual((auds[0]["action"], auds[0]["detail"], auds[0]["actor"], auds[0]["entity_id"]),
                             ("TICKET_CANCEL", detail, "ana", 7))
            self.assertEqual((conn.commits, conn.rollbacks), (1, 0))

    def test_cancelamento_de_ticket_inexistente(self):
        conn = _ScriptedConnection([])
        with mock.patch.object(self.tck, "_obter_conexao", return_value=conn):
            with self.assertRaises(repo_errors.RepoNotFound):
                self.tck.request_cancel(7, "ana", "10.0.0.1")
        self.assertEqual(conn.audits(), [])
        self.assertEqual((conn.commits, conn.rollbacks), (0, 1))

    def test_criar_sem_gravacao_parcial_com_fk_ausente(self):
        """FK conferida antes de qualquer INSERT: nada e gravado e a transacao e desfeita."""
        script_steps = [("WHERE id = :id", 1, [(1,)]), ("WHERE name = :name", 0, [])]
        conn = _ScriptedConnection(script_steps)
        with mock.patch.object(self.tck, "_obter_conexao", return_value=conn):
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                self.tck.create({"script_id": 1, "environment": "NAO_EXISTE", "requested_by": "ana"}, [])
        self.assertEqual(ctx.exception.constraint, "fk_tbsss_tck_env")
        self.assertFalse([s for s, _b in conn.executed if s.startswith("INSERT")])
        self.assertEqual(conn.rollbacks, 1)

    def test_listar_filtros_por_bind_e_escopo_vazio(self):
        """Status e escopo por IN de placeholders; escopo vazio nao devolve nada; datas como bind."""
        conn = _ScriptedConnection([("SELECT COUNT(*)", 1, [(0,)])])
        with mock.patch.object(self.tck, "_obter_conexao", return_value=conn):
            self.tck.list({"status": ["RUNNING", "PENDING"], "source": "manual",
                             "created_from": datetime.datetime(2026, 1, 1)}, environment_scope=["HML", "PROD"])
            self.tck.list({}, environment_scope=[])
        sql, binds = conn.executed[0]
        self.assertIn("ROWNUM <= 10001", sql)
        self.assertIn("status IN (:s0, :s1)", sql)
        self.assertIn("environment IN (:e0, :e1)", sql)
        self.assertIn("schedule_id IS NULL", sql)
        self.assertIn("created_at >= :created_from", sql)
        self.assertNotIn("RUNNING", sql)
        self.assertEqual((binds["s0"], binds["s1"], binds["e0"]), ("PENDING", "RUNNING", "HML"))
        self.assertIn("1 = 0", conn.executed[2][0])

    # ------------------------------------------------------------- banco real

    def _seed_fixtures(self):
        """Cadastros existentes (somente leitura): um script, um ambiente, um parametro e um login."""
        c = self.tck._obter_conexao()
        try:
            cur = c.cursor()
            try:
                cur.execute("SELECT MIN(id) FROM " + self.tck._idents["scr"])
                script_id = cur.fetchone()[0]
                cur.execute("SELECT MIN(name) FROM " + self.tck._idents["env"])
                environment = cur.fetchone()[0]
                cur.execute("SELECT MIN(id), MAX(id) FROM " + self.tck._idents["prm"])
                prm1, prm2 = cur.fetchone()
                cur.execute("SELECT MIN(login) FROM " + self.tck._idents["usr"])
                login = cur.fetchone()[0]
            finally:
                cur.close()
        finally:
            c.close()
        if None in (script_id, environment, prm1, login) or prm1 == prm2:
            self.skipTest("Seed do catalogo ausente no banco real (implante o 01_deploy_sss.sql)")
        return script_id, environment, prm1, prm2, login

    def _clean(self, ids, ip_mark):
        """Remove so os tickets criados por este teste (respostas em cascata) e, no modo compartilhado,
        a auditoria deles; falha se sobrar algo."""
        c = self.tck._obter_conexao()
        try:
            cur = c.cursor()
            try:
                for tid in ids:
                    cur.execute("DELETE FROM " + self.tck._idents["tck"] + " WHERE id = :id", {"id": tid})
                    if _oracle_test_support.schema_mode() == _oracle_test_support.SHARED_MODE:
                        cur.execute("DELETE FROM " + self.tck._tbl_aud + " WHERE entity = 'tbsss_tickets' "
                                    "AND entity_id = :id AND action IN ('TICKET_CREATE', 'TICKET_RERUN', "
                                    "'TICKET_CANCEL')", {"id": tid})
                c.commit()
                cur.execute("SELECT COUNT(*) FROM " + self.tck._idents["tck"] + " WHERE source_ip = :ip",
                            {"ip": ip_mark})
                remaining = cur.fetchone()[0]
            finally:
                cur.close()
        finally:
            c.close()
        if remaining:
            self.fail("Limpeza incompleta: %d ticket(s) com ip_origem %s" % (remaining, ip_mark))

    def _count_by_ip(self, ip_mark):
        c = self.tck._obter_conexao()
        try:
            cur = c.cursor()
            try:
                cur.execute("SELECT COUNT(*) FROM " + self.tck._idents["tck"] + " WHERE source_ip = :ip",
                            {"ip": ip_mark})
                return cur.fetchone()[0]
            finally:
                cur.close()
        finally:
            c.close()

    def test_banco_real_tickets(self):
        """Ciclo no Oracle: criar com respostas, FKs sem gravacao parcial, cancelamento, log e leituras."""
        if not self.tem_banco_real:
            self.skipTest("Banco descartavel real nao configurado (marcado como NAO TESTADO)")
        n = self.tck.constraint_name
        script_id, environment, prm1, prm2, login = self._seed_fixtures()
        mark_ip = "tst-%s" % datetime.datetime.now().strftime("%H%M%S%f")
        base = {"script_id": script_id, "environment": environment, "requested_by": login, "source_ip": mark_ip,
                "submitted_params": '{"args": ["--x"]}'}
        ids = []
        try:
            now = self.tck.now()
            self.assertEqual(now.microsecond, 0)

            # 1. criar: ticket + respostas; created_by = solicitante; obter sem log_output.
            t1 = self.tck.create(dict(base), [{"parameter_id": prm1, "answer_value": "a"},
                                             {"parameter_id": prm2, "answer_value": "b"}])
            ids.append(t1)
            reg = self.tck.get(t1)
            self.assertNotIn("log_output", reg)
            self.assertEqual(reg["submitted_params"], base["submitted_params"])
            self.assertEqual((reg["status"], reg["created_by"], reg["updated_at"]), ("PENDING", login, None))
            self.assertEqual([r["answer_value"] for r in self.tck.answers(t1)], ["a", "b"])

            # 2. FKs e UK: nenhuma linha gravada em caso de violacao.
            before = self._count_by_ip(mark_ip)
            for date, resp, ck in (
                (dict(base, script_id=999999999), [], n("fk", "tickets", "scr")),
                (dict(base, environment="NAO_EXISTE_TST"), [], n("fk", "tickets", "env")),
                (dict(base, requested_by="nao.existe.tst"), [], n("fk", "tickets", "usr")),
                (dict(base, parent_ticket_id=999999999), [], n("fk", "tickets", "parent")),
                (dict(base), [{"parameter_id": 999999999}], n("fk", "ticket_answer", "prm")),
                (dict(base), [{"parameter_id": prm1}, {"parameter_id": prm1}], n("uk", "ticket_answer", "tck_prm")),
            ):
                with self.assertRaises(repo_errors.RepoViolation) as ctx:
                    self.tck.create(date, resp)
                self.assertEqual(ctx.exception.constraint, ck)
            self.assertEqual(self._count_by_ip(mark_ip), before)

            # 3. Cancelamento nos quatro resultados (README §5.6) e o residuo PENDING com 'S' (CR-008, R-02).
            self.assertEqual(self.tck.request_cancel(t1, "teste_tck", mark_ip), "CANCELADO")
            cancelled = self.tck.get(t1)
            self.assertEqual((cancelled["status"], cancelled["status_reason"], cancelled["return_code"]),
                             ("CANCELLED", "CANCEL_USER", -1))
            self.assertEqual((cancelled["updated_by"], cancelled["created_by"]), ("teste_tck", login))
            self.assertEqual(self.tck.request_cancel(t1, "teste_tck", mark_ip), "TERMINAL")
            t2 = self.tck.create(dict(base, status="RUNNING", agent_id="tst-agente", started_at=now), [])
            ids.append(t2)
            self.assertEqual(self.tck.request_cancel(t2, "teste_tck", mark_ip), "SINALIZADO")
            self.assertEqual(self.tck.request_cancel(t2, "teste_tck", mark_ip), "JA_SINALIZADO")
            self.assertEqual(self.tck.get(t2)["status"], "RUNNING")
            t3 = self.tck.create(dict(base, cancel_requested="Y"), [])
            ids.append(t3)
            self.assertEqual(self.tck.request_cancel(t3, "teste_tck", mark_ip), "CANCELADO")
            with self.assertRaises(repo_errors.RepoNotFound):
                self.tck.request_cancel(999999999, "teste_tck", mark_ip)

            # 4. log_ler por locator: base 0 na API, offset alem do fim, negativo e max_chars < 1.
            log = "".join("linha %03d ção\n" % i for i in range(40))
            t4 = self.tck.create(dict(base, status="SUCCESS", log_output=log, finished_at=now), [])
            ids.append(t4)
            text, next_value, terminal, truncated = self.tck.log_read(t4, 0, 20)
            self.assertEqual((text, next_value, terminal, truncated), (log[:20], 20, True, False))
            self.assertEqual(self.tck.log_read(t4, 20, 20)[0], log[20:40])
            self.assertEqual(self.tck.log_read(t4, -5, 10)[:2], (log[:10], 10))
            self.assertEqual(self.tck.log_read(t4, len(log) + 5, 10)[:2], ("", len(log) + 5))
            self.assertEqual(self.tck.log_read(t4, 0, 0)[0], log)
            self.assertEqual(self.tck.log_read(t1, 0, 10)[:3], ("", 0, True))

            # 5. Leituras: listar sem CLOB, ultima execucao e historico (os mais recentes, crescente).
            items = self.tck.list({"script_id": script_id, "created_from": now}, size=50)
            mine = [i["id"] for i in items["items"] if i["id"] in ids]
            self.assertEqual(sorted(mine, reverse=True), mine)
            self.assertEqual(set(mine), set(ids))
            for item in items["items"]:
                self.assertNotIn("log_output", item)
                self.assertNotIn("submitted_params", item)
            self.assertIn("total_capped", items)
            only_cancelled = self.tck.list({"script_id": script_id, "status": ["CANCELLED"],
                                             "created_from": now}, environment_scope=[environment])
            self.assertEqual(sorted(i["id"] for i in only_cancelled["items"] if i["id"] in ids), sorted([t1, t3]))
            self.assertEqual(self.tck.list({"script_id": script_id}, environment_scope=[])["total"], 0)
            last = self.tck.last_runs([script_id], environment_scope=[environment], requester=login)
            self.assertEqual(last[script_id]["id"], max(ids))
            self.assertEqual(sorted(last[script_id]), ["created_at", "finished_at", "id", "status", "status_reason"])
            self.assertEqual(self.tck.last_runs([script_id], environment_scope=[]), {})
            hist = self.tck.script_history(script_id, now, environment_scope=[environment], limit=2)
            self.assertEqual([h["id"] for h in hist], sorted(ids)[-2:])
            self.assertEqual(sorted(hist[0]), ["created_at", "finished_at", "id", "started_at", "status",
                                               "status_reason"])
        finally:
            self._clean(ids, mark_ip)


class TestOracleSchedules(unittest.TestCase):
    """Testes de conformidade e integridade para o agregado AGENDAMENTOS no Oracle (passo 4 do F7.3)."""

    @classmethod
    def setUpClass(cls):
        aggregate = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if aggregate != "AGENDAMENTOS":
            raise unittest.SkipTest("Execucao restrita ao agregado AGENDAMENTOS (atual: %s)" % aggregate)
        _prepare_real_db(cls)

    @classmethod
    def tearDownClass(cls):
        _restore_real_db(cls)

    def setUp(self):
        repo_factory.reset_singletons()
        self.agd = repo_factory.get("schedules")

    # ------------------------------------------------------------- sem banco

    def test_instancia_correta_do_agregado(self):
        self.assertIsInstance(self.agd, RepoSchedules)
        self.assertEqual(self.agd.__class__.__name__, "RepoSchedulesOracle")
        self.assertEqual(repo_factory.get("tickets").__class__.__name__, "RepoTicketsOracle")


    def test_owner_e_prefixo_parametrizados(self):
        cfg = mock.Mock()
        cfg.oracle.owner = "SSS_TEST_AGD"
        cfg.oracle.table_prefix = "abc_"
        repo = RepoSchedulesOracle(cfg=cfg, secrets={})
        for name, sql in repo._sql.items():
            self.assertNotIn("tbsss_", sql, name)
            self.assertNotIn("SELECT *", sql, name)
        self.assertIn("SSS_TEST_AGD.abc_schedules", repo._sql["GET"])
        self.assertEqual(repo._seq_sch, "SSS_TEST_AGD.sq_abc_schedules")
        with self.assertRaises(repo_errors.RepoViolation) as ctx:
            repo._checar_cks({"name": "x", "recurrence_type": "ANUAL"})
        self.assertEqual(ctx.exception.constraint, "ck_abc_sch_rtype")

    def test_pausar_condicional_a_regra_ativa_e_a_data_lida(self):
        """CR-007, R-19: o UPDATE exige active = 'Y' e, com antiga_data, a next_run_at lida."""
        self.assertTrue(self.agd._sql["PAUSE"].endswith("WHERE id = :id AND active = 'Y'"))
        self.assertTrue(self.agd._sql["PAUSE_OPTIMISTIC"].endswith(
            "WHERE id = :id AND active = 'Y' AND next_run_at = :old_date"))
        self.assertIn("updated_at = SYSDATE, updated_by = :actor", self.agd._sql["PAUSE"])
        self.assertIn("FOR UPDATE WAIT 5", self.agd._sql["GET_LOCK"])

    def test_cks_com_os_nomes_do_fake(self):
        n = lambda s: "ck_tbsss_sch_" + s  # noqa: E731
        base = {"name": "r", "recurrence_type": "DAILY", "priority": 2, "active": "Y", "run_time": "08:00",
                "start_date": datetime.datetime(2026, 1, 1), "next_run_at": datetime.datetime(2026, 1, 2)}
        cases = (
            ({"recurrence_type": "ANUAL"}, n("rtype")), ({"priority": 5}, n("prio")), ({"priority": True}, n("prio")),
            ({"active": "X"}, n("active")), ({"month_day": 32}, n("day")), ({"run_time": "24:00"}, n("time")),
            ({"week_days": "8"}, n("wday")), ({"end_date": datetime.datetime(2025, 1, 1)}, n("end")),
            ({"pause_reason": "OUTRO"}, n("pause")), ({"run_time": None}, n("fields")),
            ({"recurrence_type": "CRON"}, n("fields")),
        )
        for change, ck in cases:
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                self.agd._checar_cks(dict(base, **change))
            self.assertEqual(ctx.exception.constraint, ck, change)
        with self.assertRaises(repo_errors.RepoViolation):
            self.agd._checar_cks(dict(base, name="x" * 61))

    def test_ator_obrigatorio_antes_de_qualquer_sql(self):
        with mock.patch.object(self.agd, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            for actor in (None, "", "   ", "x" * 41):
                for call in (
                    lambda a: self.agd.insert({"script_id": 1, "environment": "X", "user_id": 1}, actor=a),
                    lambda a: self.agd.update(1, {"name": "y"}, actor=a),
                    lambda a: self.agd.pause(1, "MANUAL", actor=a),
                    lambda a: self.agd.resume(1, datetime.datetime(2026, 1, 1), actor=a),
                ):
                    with self.assertRaises(repo_errors.RepoViolation):
                        call(actor)

    def test_pausar_sem_linha_afetada_e_conflito(self):
        """Regra existente, mas nao ativa (ou com outra next_run): RepoConflict e ROLLBACK."""
        conn = _ScriptedConnection([("WHERE id = :id AND active = 'Y'", 0, []), ("SELECT id FROM", 1, [(7,)])])
        with mock.patch.object(self.agd, "_obter_conexao", return_value=conn):
            with self.assertRaises(repo_errors.RepoConflict):
                self.agd.pause(7, "MANUAL", old_date=datetime.datetime(2026, 1, 1, 8, 0, 0, 123456), actor="ana")
        self.assertEqual((conn.commits, conn.rollbacks), (0, 1))
        self.assertEqual(conn.audits(), [])

    def test_listar_escopo_vazio_e_filtros_por_bind(self):
        conn = _ScriptedConnection([("SELECT COUNT(*)", 1, [(0,)])])
        with mock.patch.object(self.agd, "_obter_conexao", return_value=conn):
            self.agd.list({"active": "Y", "name": "50%_x"}, environment_scope=["HML"])
            self.agd.list({}, environment_scope=[])
        sql, binds = conn.executed[0]
        self.assertIn("environment IN (:e0)", sql)
        self.assertIn("ROWNUM <= 10001", sql)
        self.assertEqual(binds["name_f"], "%50\\%\\_x%")
        self.assertIn("1 = 0", conn.executed[2][0])

    # ------------------------------------------------------------- banco real

    def _seed_fixtures(self):
        c = self.agd._obter_conexao()
        try:
            cur = c.cursor()
            try:
                cur.execute("SELECT MIN(id) FROM " + self.agd._idents["scr"])
                script_id = cur.fetchone()[0]
                cur.execute("SELECT MIN(name) FROM " + self.agd._idents["env"])
                environment = cur.fetchone()[0]
                cur.execute("SELECT MIN(id), MIN(login) FROM " + self.agd._idents["usr"])
                user_id, login = cur.fetchone()
            finally:
                cur.close()
        finally:
            c.close()
        if None in (script_id, environment, user_id):
            self.skipTest("Seed do catalogo ausente no banco real (implante o 01_deploy_sss.sql)")
        return script_id, environment, user_id, login

    def _clean(self, sch_ids, tck_ids, mark):
        """Remove so os registros criados por este teste e, no modo compartilhado, a auditoria deles."""
        shared = _oracle_test_support.schema_mode() == _oracle_test_support.SHARED_MODE
        tck = repo_factory.get("tickets")
        c = self.agd._obter_conexao()
        try:
            cur = c.cursor()
            try:
                for tid in tck_ids:
                    cur.execute("DELETE FROM " + tck._idents["tck"] + " WHERE id = :id", {"id": tid})
                    if shared:
                        cur.execute("DELETE FROM " + self.agd._tbl_aud + " WHERE entity = 'tbsss_tickets' "
                                    "AND entity_id = :id", {"id": tid})
                for aid in sch_ids:
                    cur.execute("DELETE FROM " + self.agd._idents["sch"] + " WHERE id = :id", {"id": aid})
                    if shared:
                        cur.execute("DELETE FROM " + self.agd._tbl_aud + " WHERE entity = 'tbsss_schedules' "
                                    "AND entity_id = :id", {"id": aid})
                c.commit()
                cur.execute("SELECT COUNT(*) FROM " + self.agd._idents["sch"] + " WHERE name LIKE :m",
                            {"m": mark + "%"})
                remaining = cur.fetchone()[0]
            finally:
                cur.close()
        finally:
            c.close()
        if remaining:
            self.fail("Limpeza incompleta: %d agendamento(s) com nome %s*" % (remaining, mark))

    def _contar(self, mark):
        c = self.agd._obter_conexao()
        try:
            cur = c.cursor()
            try:
                cur.execute("SELECT COUNT(*) FROM " + self.agd._idents["sch"] + " WHERE name LIKE :m",
                            {"m": mark + "%"})
                return cur.fetchone()[0]
            finally:
                cur.close()
        finally:
            c.close()

    def test_banco_real_agendamentos(self):
        """Ciclo no Oracle: CRUD, CKs e FKs sem gravacao parcial, pausa otimista, microssegundos e ocorrencia."""
        if not self.tem_banco_real:
            self.skipTest("Testes Oracle reais desligados (marcado como NAO TESTADO)")
        script_id, environment, user_id, login = self._seed_fixtures()
        mark = "TST_AGD_%s" % datetime.datetime.now().strftime("%H%M%S%f")
        now = self.agd.now() if hasattr(self.agd, "now") else repo_factory.get("tickets").now()
        tomorrow = now + datetime.timedelta(days=1)
        base = {"name": mark + "_1", "script_id": script_id, "environment": environment, "user_id": user_id,
                "recurrence_type": "DAILY", "run_time": "08:00", "start_date": now,
                "next_run_at": tomorrow, "params_json": '{"p": "v"}'}
        n = self.agd.constraint_name
        sch_ids, tck_ids = [], []
        try:
            # 1. inserir: created_* do criador; parametros_json no obter e no listar.
            r1 = self.agd.insert(dict(base), actor="teste_agd")
            sch_ids.append(r1["id"])
            self.assertEqual((r1["created_by"], r1["updated_at"], r1["params_json"]), ("teste_agd", None, '{"p": "v"}'))
            self.assertEqual(r1["next_run_at"], tomorrow.replace(microsecond=0))

            # 2. CKs e FKs: nada gravado em caso de violacao.
            before = self._contar(mark)
            for date, ck in (
                (dict(base, recurrence_type="ANUAL"), n("ck", "schedules", "rtype")),
                (dict(base, run_time=None), n("ck", "schedules", "fields")),
                (dict(base, end_date=now - datetime.timedelta(days=1)), n("ck", "schedules", "end")),
                (dict(base, script_id=999999999), n("fk", "schedules", "scr")),
                (dict(base, user_id=999999999), n("fk", "schedules", "usr")),
                (dict(base, environment="NAO_EXISTE_TST"), n("fk", "schedules", "env")),
            ):
                with self.assertRaises(repo_errors.RepoViolation) as ctx:
                    self.agd.insert(date, actor="teste_agd")
                self.assertEqual(ctx.exception.constraint, ck)
            self.assertEqual(self._contar(mark), before)

            # 3. alterar condicional ao esperado; created_* preservado, updated_* com o editor.
            with self.assertRaises(repo_errors.RepoConflict):
                self.agd.update(r1["id"], {"run_time": "09:00"}, expected={"run_time": "07:00"}, actor="bia")
            r1b = self.agd.update(r1["id"], {"run_time": "09:00"}, expected={"run_time": "08:00"}, actor="bia")
            self.assertEqual((r1b["run_time"], r1b["updated_by"], r1b["created_by"]), ("09:00", "bia", "teste_agd"))
            with self.assertRaises(repo_errors.RepoViolation):
                self.agd.update(r1["id"], {"week_days": "9"}, actor="bia")
            self.assertEqual(self.agd.get(r1["id"])["week_days"], None)

            # 4. pausar: microssegundos no bind nao dao conflito (README §7.5); regra ja pausada da conflito.
            read = self.agd.get(r1["id"])["next_run_at"]
            paused = self.agd.pause(r1["id"], "MANUAL", old_date=read.replace(microsecond=543210), actor="bia")
            self.assertEqual((paused["active"], paused["pause_reason"]), ("N", "MANUAL"))
            with self.assertRaises(repo_errors.RepoConflict):
                self.agd.pause(r1["id"], "MANUAL", actor="bia")
            r2 = self.agd.insert(dict(base, name=mark + "_2"), actor="teste_agd")
            sch_ids.append(r2["id"])
            with self.assertRaises(repo_errors.RepoConflict):
                self.agd.pause(r2["id"], "MANUAL", old_date=tomorrow + datetime.timedelta(minutes=5), actor="bia")
            with self.assertRaises(repo_errors.RepoNotFound):
                self.agd.pause(999999999, "MANUAL", actor="bia")
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                self.agd.pause(r2["id"], "OUTRO", actor="bia")
            self.assertEqual(ctx.exception.constraint, n("ck", "schedules", "pause"))

            # 5. retomar condicional ao esperado.
            new = tomorrow + datetime.timedelta(days=1)
            with self.assertRaises(repo_errors.RepoConflict):
                self.agd.resume(r1["id"], new, expected={"active": "Y"}, actor="bia")
            resumed = self.agd.resume(r1["id"], new, expected={"active": "N", "next_run_at": read}, actor="bia")
            self.assertEqual((resumed["active"], resumed["pause_reason"]), ("Y", None))
            self.assertEqual(resumed["next_run_at"], new.replace(microsecond=0))

            # 6. listar: filtro por trecho, escopo e parametros_json presente (excecao documentada).
            items = self.agd.list({"name": mark.lower()}, environment_scope=[environment])
            self.assertEqual(sorted(i["id"] for i in items["items"]), sorted(sch_ids))
            self.assertTrue(all(i["params_json"] == '{"p": "v"}' for i in items["items"]))
            self.assertEqual(self.agd.list({"name": mark.lower()}, environment_scope=[])["total"], 0)
            self.assertEqual([i["id"] for i in self.agd.list({"name": mark.lower(), "active": "N"})["items"]], [])

            # 7. ticket_status e a ocorrencia unica do agendamento (ix_<prefixo>tck_ocor, CR-007 R-27).
            tck = repo_factory.get("tickets")
            self.assertIsNone(self.agd.ticket_status(None))
            self.assertIsNone(self.agd.ticket_status(999999999))
            occurrence = tomorrow.replace(second=0, microsecond=0)
            t1 = tck.create({"script_id": script_id, "environment": environment, "requested_by": login,
                            "schedule_id": r1["id"], "scheduled_at": occurrence}, [])
            tck_ids.append(t1)
            self.assertEqual(self.agd.ticket_status(t1), "PENDING")
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                tck_ids.append(tck.create({"script_id": script_id, "environment": environment, "requested_by": login,
                                          "schedule_id": r1["id"], "scheduled_at": occurrence}, []))
            self.assertEqual(ctx.exception.constraint, tck.constraint_name("ix", "tickets", "occur"))
        finally:
            self._clean(sch_ids, tck_ids, mark)


class TestOracleAuditAgents(unittest.TestCase):
    """Testes de conformidade e integridade para o agregado AUDITORIA_AGENTES no Oracle (passo 5 do F7.3)."""

    @classmethod
    def setUpClass(cls):
        aggregate = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if aggregate != "AUDITORIA_AGENTES":
            raise unittest.SkipTest("Execucao restrita ao agregado AUDITORIA_AGENTES (atual: %s)" % aggregate)
        _prepare_real_db(cls)

    @classmethod
    def tearDownClass(cls):
        _restore_real_db(cls)

    def setUp(self):
        repo_factory.reset_singletons()
        self.aud = repo_factory.get("audit")
        self.agt = repo_factory.get("agents")

    # ------------------------------------------------------------- sem banco

    def test_todos_os_agregados_no_oracle(self):
        """Com o 5o agregado, a aplicacao resolve todos os repositorios para o Oracle (sem FAKE)."""
        expected = {"users": "RepoUsersOracle", "rbac": "RepoRbacOracle", "catalog": "RepoCatalogOracle",
                     "tickets": "RepoTicketsOracle", "schedules": "RepoSchedulesOracle",
                     "audit": "RepoAuditOracle", "agents": "RepoAgentsOracle"}
        for name, cls_name in expected.items():
            self.assertEqual(repo_factory.get(name).__class__.__name__, cls_name, name)
        with self.assertRaises(ValueError):
            repo_factory.get("inexistente")

    def test_owner_e_prefixo_parametrizados(self):
        cfg = mock.Mock()
        cfg.oracle.owner = "SSS_TEST_AUD"
        cfg.oracle.table_prefix = "abc_"
        aud = RepoAuditOracle(cfg=cfg, secrets={})
        agt = RepoAgentsOracle(cfg=cfg, secrets={})
        for name, sql in list(aud._sql.items()) + list(agt._sql.items()):
            self.assertNotIn("tbsss_", sql, name)
        self.assertIn("SSS_TEST_AUD.abc_audit", aud._sql["INSERT"])
        self.assertEqual(aud._seq_aud, "SSS_TEST_AUD.sq_abc_audit")
        self.assertIn("SSS_TEST_AUD.abc_scripts", agt._sql["QUEUE"])

    def test_painel_usa_as_expressoes_dos_indices_e_nenhum_clob(self):
        """AGENTS §4.8: CASE textualmente identico ao de ix_tck_run/ix_tck_fila; sem CLOB (CR-008, R-15)."""
        self.assertIn("(" + sql_ident.FBI_TCK_RUN_AGENT_CASE + ") = :code", self.agt._sql["TICKETS_RUNNING"])
        self.assertIn("(" + sql_ident.FBI_TCK_RUN_AGENT_CASE + ") >= CHR(1)", self.agt._sql["RUNNING_NO_PID"])
        # CR-013: so ix_tck_fila (status lider e o inicio da espera), agrupado por script antes do JOIN.
        self.assertIn("WHERE status = 'PENDING' AND " + sql_ident.FBI_TCK_QUEUE_START + " <= :now", self.agt._sql["QUEUE"])
        self.assertIn("JOIN " + self.agt._idents["scr"] + " s ON s.id = g.script_id", self.agt._sql["QUEUE"])
        for name in ("TICKETS_RUNNING", "QUEUE", "RUNNING_NO_PID"):
            self.assertNotIn("log_output", self.agt._sql[name])
            self.assertNotIn("submitted_params", self.agt._sql[name])

    def test_registrar_sem_corte_e_ator_obrigatorio_antes_do_sql(self):
        """test_06b: ator nulo, vazio ou longo e detalhe longo viram RepoViolation sem abrir conexao."""
        with mock.patch.object(self.aud, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            for actor, detail in ((None, None), ("", None), ("x" * 41, None), ("ana", "d" * 1001)):
                with self.assertRaises(repo_errors.RepoViolation):
                    self.aud.register(actor, "1.2.3.4", "UPDATE", "tbsss_scripts", 1, detail)

    def test_gravacao_de_auditoria_dos_outros_agregados_sem_corte(self):
        """base.write_audit recusa (nao corta) detalhe longo: a transacao toda e desfeita."""
        from repo_oracle import base
        with self.assertRaises(repo_errors.RepoViolation):
            base.write_audit(mock.MagicMock(), "t", "s", {"actor": "ana", "action": "X", "detail": "d" * 1001},
                                  "tbsss_scripts", 1)
        with self.assertRaises(repo_errors.RepoViolation):
            base.write_audit(mock.MagicMock(), "t", "s", {"actor": None, "action": "X"}, "tbsss_scripts", 1)

    def test_listar_e_iterar_por_bind_com_periodo_e_id_max(self):
        conn = _ScriptedConnection([("SELECT COUNT(*)", 1, [(0,)])])
        filters = {"actor": "Ana_1", "start_date": datetime.datetime(2026, 1, 1),
                   "end_date": datetime.datetime(2026, 1, 31, 23, 59, 59), "id_max": 99, "source_ip": "10.%"}
        with mock.patch.object(self.aud, "_obter_conexao", return_value=conn):
            self.aud.list(filters)
            list(self.aud.iterate(filters, limit=5))
        sql, binds = conn.executed[0]
        for snippet in ("LOWER(actor) LIKE :actor_f ESCAPE", "created_at >= :start_date", "created_at <= :end_date",
                       "id <= :id_max", "ROWNUM <= 10001"):
            self.assertIn(snippet, sql)
        self.assertNotIn("TRUNC", sql)
        self.assertEqual((binds["actor_f"], binds["ip_f"]), ("%ana\\_1%", "%10.\\%%"))
        sql_it, binds_it = conn.executed[-1]
        self.assertIn("WHERE ROWNUM <= :cutoff", sql_it)
        self.assertEqual(binds_it["cutoff"], 5)

    # ------------------------------------------------------------- banco real

    def _executar(self, sqls):
        c = self.aud._obter_conexao()
        try:
            cur = c.cursor()
            try:
                for sql, binds in sqls:
                    cur.execute(sql, binds)
                c.commit()
            finally:
                cur.close()
        finally:
            c.close()

    def test_banco_real_auditoria_e_agentes(self):
        """Ciclo no Oracle: trilha (reservar, registrar, listar, iterar) e as quatro leituras do painel."""
        if not self.tem_banco_real:
            self.skipTest("Testes Oracle reais desligados (marcado como NAO TESTADO)")
        tck = repo_factory.get("tickets")
        mark = "tst%s" % datetime.datetime.now().strftime("%H%M%S%f")
        aud_ids, tck_ids, agt_id = [], [], None
        tab_agt = self.agt._idents["agt"]
        try:
            now = tck.now()

            # 1. Trilha: id reservado, id repetido recusado com o nome da PK, listar e iterar com filtros.
            aid = self.aud.reserve_id()
            reg = self.aud.register("teste_" + mark, "10.0.0.1", "SCHEMA_MIGRATE", "tbsss_control", 1,
                                     u"versão 1 conferida", id=aid)
            aud_ids.append(aid)
            self.assertEqual((reg["id"], reg["actor"], reg["detail"]), (aid, "teste_" + mark, u"versão 1 conferida"))
            self.assertEqual(reg["created_at"].microsecond, 0)
            with self.assertRaises(repo_errors.RepoViolation) as ctx:
                self.aud.register("teste_" + mark, None, "UPDATE", "tbsss_control", 1, None, id=aid)
            self.assertEqual(ctx.exception.constraint, "pk_" + self.aud._prefixo + sql_ident.physical("audit"))
            for _ in range(2):
                aud_ids.append(self.aud.register("teste_" + mark, None, "UPDATE", "tbsss_control", 1)["id"])
            filters = {"actor": "TESTE_" + mark.upper(), "start_date": now - datetime.timedelta(minutes=5),
                       "end_date": now + datetime.timedelta(minutes=5)}
            items = self.aud.list(filters)
            self.assertEqual([i["id"] for i in items["items"]], sorted(aud_ids, reverse=True))
            self.assertEqual(self.aud.list(dict(filters, id_max=aid))["total"], 1)
            self.assertEqual(self.aud.list(dict(filters, action="SCHEMA_MIGRATE", entity="tbsss_control",
                                                  entity_id=1))["total"], 1)
            self.assertEqual([r["id"] for r in self.aud.iterate(filters, limit=2)], sorted(aud_ids, reverse=True)[:2])

            # 2. Painel: agente ATIVO com heartbeat agora atende (ambiente, interpretador) do proprio teste.
            script = repo_factory.get("catalog").scripts_list(size=1)["items"][0]
            environment = repo_factory.get("catalog").environments_list(size=1)["items"][0]["name"]
            login = repo_factory.get("users").list(size=1)["items"][0]["login"]
            c = self.aud._obter_conexao()
            try:
                agt_id = db_conn.next_id(c, self.agt.qualify_sequence("agents"))
            finally:
                c.close()
            self._executar([(
                "INSERT INTO " + tab_agt + " (id, code, hostname, status, environments, platform, interpreters, "
                "heartbeat_at, critical_config, created_at, created_by) VALUES (:id, :code, 'host-tst', 'ACTIVE', "
                ":env, 'LINUX', :interp, :hb, 'tst=1', SYSDATE, 'SYSTEM:teste')",
                {"id": agt_id, "code": mark, "env": environment, "interp": script["interpreter"], "hb": now})])
            ag = [a for a in self.agt.list() if a["code"] == mark][0]
            self.assertEqual((ag["platform"], ag["interpreters"], ag["critical_config"]),
                             ("LINUX", script["interpreter"], "tst=1"))

            old = now - datetime.timedelta(minutes=30)
            base = {"script_id": script["id"], "environment": environment, "requested_by": login, "source_ip": mark}
            t_run = tck.create(dict(base, status="RUNNING", agent_id=mark, started_at=old), [])
            tck_ids.append(t_run)
            t_pend = tck.create(dict(base, scheduled_at=old), [])
            tck_ids.append(t_pend)

            running = self.agt.tickets_running(mark)
            self.assertEqual([t["id"] for t in running], [t_run])
            self.assertNotIn("log_output", running[0])
            self.assertNotIn("submitted_params", running[0])
            without_pid = [t for t in self.agt.running_without_pid(now, 2) if t["id"] == t_run]
            self.assertEqual(sorted(without_pid[0]), ["agent_id", "environment", "id", "script_id", "started_at"])
            # Reservado ha 30 minutos: fica de fora com o limite de 60.
            self.assertNotIn(t_run, [t["id"] for t in self.agt.running_without_pid(now, 60)])

            thresholds = mock.Mock(heartbeat_interval_s=30, fence_timeout_s=120)
            key = (environment, script["interpreter"])
            self.assertNotIn(key, [(g["environment"], g["interpreter"]) for g in self.agt.unattended_queue(now, thresholds)])
            # Agent parado: o mesmo par passa a aparecer na fila sem atendente, com o PENDING do teste.
            self._executar([("UPDATE " + tab_agt + " SET status = 'STOPPED', updated_at = SYSDATE, "
                             "updated_by = 'SYSTEM:teste' WHERE id = :id", {"id": agt_id})])
            # Relogio novo: o PENDING entra na fila em GREATEST(scheduled_at, created_at) (CR-013), depois de `agora`.
            after = tck.now()
            groups = dict(((g["environment"], g["interpreter"]), g)
                          for g in self.agt.unattended_queue(after, thresholds))
            self.assertIn(key, groups)
            self.assertGreaterEqual(groups[key]["quantity"], 1)
            # scheduled_at no passado nao antecipa a espera: conta da criacao do ticket.
            self.assertLessEqual(groups[key]["oldest"], after)
        finally:
            cleanup = [("DELETE FROM " + self.aud._idents["aud"] + " WHERE id = :id", {"id": i}) for i in aud_ids]
            for tid in tck_ids:
                cleanup.append(("DELETE FROM " + tck._idents["tck"] + " WHERE id = :id", {"id": tid}))
                if _oracle_test_support.schema_mode() == _oracle_test_support.SHARED_MODE:
                    cleanup.append(("DELETE FROM " + self.aud._idents["aud"] + " WHERE entity = 'tbsss_tickets' "
                                    "AND entity_id = :id", {"id": tid}))
            if agt_id is not None:
                cleanup.append(("DELETE FROM " + tab_agt + " WHERE id = :id", {"id": agt_id}))
            self._executar(cleanup)


if __name__ == "__main__":
    unittest.main()
