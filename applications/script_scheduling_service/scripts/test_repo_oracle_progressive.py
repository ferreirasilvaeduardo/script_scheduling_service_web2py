# -*- coding: utf-8 -*-
"""Testes progressivos para os repositorios Oracle 11gR2 (F7.3).

Executa a validacao do agregado ativo selecionado por SSS_TEST_REPO_AGREGADO:
1. RBAC_USUARIOS -> TestOracleRbacUsuarios
2. CATALOGO -> TestOracleCatalogo
3. TICKETS -> TestOracleTickets
4. AGENDAMENTOS -> TestOracleAgendamentos
5. AUDITORIA_AGENTES -> TestOracleAuditoriaAgentes
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
from repo_catalogo import RepoCatalogo
from repo_oracle.catalogo import RepoCatalogoOracle
from repo_rbac import RepoRbac
from repo_oracle.agentes import RepoAgentesOracle
from repo_oracle.auditoria import RepoAuditoriaOracle
from repo_agendamentos import RepoAgendamentos
from repo_oracle.agendamentos import RepoAgendamentosOracle
from repo_oracle.tickets import RepoTicketsOracle
from repo_tickets import RepoTickets
from repo_usuarios import RepoUsuarios
from gluon import current


def _preparar_banco_real(cls):
    """Valida o banco real (modo descartavel ou compartilhado) antes de qualquer DML.

    Com banco real, o cfg validado vai para current.sss_cfg durante a classe (os repositorios Oracle
    leem owner, prefixo, DSN e segredos dele) e e restaurado no tearDownClass.
    """
    cls.tem_banco_real = _oracle_test_support.banco_real_configurado()
    cls._tinha_sss_cfg = hasattr(current, "sss_cfg")
    cls._sss_cfg_anterior = getattr(current, "sss_cfg", None)
    if cls.tem_banco_real:
        cls.cfg = _oracle_test_support.preparar_schema_descartavel("web")
        current.sss_cfg = cls.cfg
    repo_factory.configurar({"app": {"data_backend": "ORACLE", "sss_env": "DEV"}})


def _restaurar_banco_real(cls):
    repo_factory.configurar(None)
    repo_factory.reset_singletons()
    if cls._tinha_sss_cfg:
        current.sss_cfg = cls._sss_cfg_anterior
    elif hasattr(current, "sss_cfg"):
        delattr(current, "sss_cfg")


class TestOracleRbacUsuarios(unittest.TestCase):
    """Testes de conformidade e integridade para o agregado RBAC_USUARIOS no Oracle."""

    @classmethod
    def setUpClass(cls):
        agregado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if agregado != "RBAC_USUARIOS":
            raise unittest.SkipTest("Execucao restrita ao agregado RBAC_USUARIOS (atual: %s)" % agregado)

        _preparar_banco_real(cls)

    @classmethod
    def tearDownClass(cls):
        _restaurar_banco_real(cls)

    def setUp(self):
        repo_factory.reset_singletons()
        self.usr = repo_factory.obter("usuarios")
        self.rbac = repo_factory.obter("rbac")

    def test_instancias_corretas_do_agregado(self):
        """Valida que repo_factory devolve as implementacoes Oracle corretas."""
        self.assertIsInstance(self.usr, RepoUsuarios)
        self.assertIsInstance(self.rbac, RepoRbac)
        self.assertEqual(self.usr.__class__.__name__, "RepoUsuariosOracle")
        self.assertEqual(self.rbac.__class__.__name__, "RepoRbacOracle")


    def test_ator_obrigatorio_usuarios_e_perfis(self):
        """Valida que insercao e alteracao sem ator ou com ator longo lancam RepoViolacao."""
        for ator_invalido in (None, "", "   ", "x" * 41):
            with self.assertRaises(repo_errors.RepoViolacao):
                self.usr.inserir({"login": "novo.user", "profile_id": 1}, ator=ator_invalido)
            with self.assertRaises(repo_errors.RepoViolacao):
                self.rbac.perfis_inserir({"name": "Novo Perfil"}, ator=ator_invalido)
            with self.assertRaises(repo_errors.RepoViolacao):
                self.usr.desbloquear(1, ator=ator_invalido)

    def test_alterar_sem_data_nao_declara_bind_de_data_ausente(self):
        """Regressao (F7.3): alterar so o nome declarava bloqueado_ate/ultimo_login e caia em DPY-4008."""
        import repo_oracle.usuarios as mod
        linha = tuple(1 if c in ("id", "profile_id") else ("Y" if c == "active" else
                      ("tst.x" if c == "login" else (0 if c in ("failed_attempts", "session_epoch") else None)))
                      for c in mod._COLS_USUARIO)
        conn = _ConexaoRoteirizada([("FOR UPDATE OF u.active WAIT 5", 1, [linha + ("Y", "N")]), ("UPDATE", 1, []),
                                    ("SELECT", 1, [linha])])
        with mock.patch.object(self.usr, "_obter_conexao", return_value=conn):
            self.usr.alterar(1, {"name": "Novo nome"}, ator="ana")
        upd = [sql for sql, _b in conn.executados if sql.startswith("UPDATE")]
        self.assertTrue(upd and ":locked_until" not in upd[0])
        self.assertEqual(conn.commits, 1)

    def test_login_invalido_recusado(self):
        """Valida regex de login em tbsss_users."""
        for log_inv in ("ab", "AB_USER", "user com espaco", "u" * 31, "usr@dominio"):
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.usr.inserir({"login": log_inv, "profile_id": 1}, ator="admin")
            self.assertEqual(ctx.exception.constraint, self.usr.nome_constraint("ck", "usuarios", "login"))

    def test_banco_real_rbac_usuarios(self):
        """Executa ciclo completo no banco Oracle real quando configurado em DEV descartavel."""
        if not self.tem_banco_real:
            self.skipTest("Banco descartavel real nao configurado (marcado como NAO TESTADO)")

        ator_teste = "teste_agregado"
        prefixo = "tst_%d" % int(datetime.datetime.now().strftime("%H%M%S"))

        # 1. Cria perfil
        nome_perfil = ("P_%s" % prefixo)[:30]
        per = self.rbac.perfis_inserir({
            "name": nome_perfil,
            "description": "Perfil temporario de teste progressivo",
            "is_admin": "N",
            "active": "Y",
        }, ator=ator_teste)
        self.assertIsNotNone(per.get("id"))
        pid = per["id"]

        try:
            # 2. Cria usuario associado
            login = ("u_%s" % prefixo)[:30].lower()
            usr = self.usr.inserir({
                "login": login,
                "name": "Usuario de Teste",
                "password_hash": "hash_fake_123",
                "profile_id": pid,
                "active": "Y",
            }, ator=ator_teste)
            self.assertIsNotNone(usr.get("id"))
            uid = usr["id"]

            # 3. Teste do relogio do banco sem microssegundos
            dt_banco = self.usr.agora()
            self.assertEqual(dt_banco.microsecond, 0)

            # 4. Estado da sessao
            sess = self.usr.obter_estado_sessao(uid)
            self.assertEqual(sess["login"], login)
            self.assertEqual(sess["profile_id"], pid)
            self.assertEqual(sess["session_epoch"], 0)

            # 5. Logout incrementa sessao_epoch
            self.usr.encerrar_sessoes(uid, auditoria={"actor": ator_teste, "action": "LOGOUT"})
            sess2 = self.usr.obter_estado_sessao(uid)
            self.assertEqual(sess2["session_epoch"], 1)

            # 6. Falha e sucesso de login
            self.usr.registrar_falha_login(login, bloqueio_s=300)
            u_falha = self.usr.obter_por_id(uid)
            self.assertEqual(u_falha["failed_attempts"], 1)
            self.assertIsNotNone(u_falha["locked_until"])

            self.usr.registrar_sucesso_login(login, novo_hash="hash_rehash_456")
            u_ok = self.usr.obter_por_id(uid)
            self.assertEqual(u_ok["failed_attempts"], 0)
            self.assertIsNone(u_ok["locked_until"])
            self.assertEqual(u_ok["password_hash"], "hash_rehash_456")

            # 7. Imutabilidade do login
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.usr.alterar(uid, {"login": "outro_login"}, ator=ator_teste)
            self.assertEqual(ctx.exception.constraint, "tr_tbsss_usr_bu")

            # 8. Unicidade de UKs
            with self.assertRaises(repo_errors.RepoViolacao):
                self.usr.inserir({"login": login, "profile_id": pid}, ator=ator_teste)
            with self.assertRaises(repo_errors.RepoViolacao):
                self.rbac.perfis_inserir({"name": nome_perfil}, ator=ator_teste)

        finally:
            # Limpeza cirurgica no schema descartavel
            conn = self.usr._obter_conexao()
            try:
                cur = conn.cursor()
                try:
                    cur.execute("DELETE FROM " + self.usr._tabela() + " WHERE id = :id", {"id": uid})
                    if _oracle_test_support.modo_schema() == _oracle_test_support.MODO_COMPARTILHADO:
                        # encerrar_sessoes audita o LOGOUT do usuario do teste: so essa auditoria sai.
                        cur.execute("DELETE FROM " + self.rbac._tabela_auditoria() + " WHERE entity = "
                                    "'tbsss_users' AND entity_id = :id", {"id": uid})
                    cur.execute("DELETE FROM " + self.rbac._tabela_perfis() + " WHERE id = :id", {"id": pid})
                    conn.commit()
                finally:
                    cur.close()
            finally:
                conn.close()


class _CursorGravador(object):
    """Cursor de mentira: registra o SQL e devolve as linhas programadas, sem banco."""

    def __init__(self, linhas=None, uma=None):
        self.executados = []
        self._linhas = list(linhas or [])
        self._uma = uma
        self.rowcount = 1

    def execute(self, sql, binds=None):
        self.executados.append((sql, binds))

    def fetchall(self):
        return list(self._linhas)

    def fetchone(self):
        return self._uma

    def close(self):
        pass


class _ConexaoGravadora(object):
    def __init__(self, cursor):
        self.cursor_ = cursor

    def cursor(self):
        return self.cursor_

    def close(self):
        pass


class TestOracleCatalogo(unittest.TestCase):
    """Testes de conformidade e integridade para o agregado CATALOGO no Oracle (passo 2 do F7.3)."""

    @classmethod
    def setUpClass(cls):
        agregado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if agregado != "CATALOGO":
            raise unittest.SkipTest("Execucao restrita ao agregado CATALOGO (atual: %s)" % agregado)

        _preparar_banco_real(cls)

    @classmethod
    def tearDownClass(cls):
        _restaurar_banco_real(cls)

    def setUp(self):
        repo_factory.reset_singletons()
        self.cat = repo_factory.obter("catalogo")

    # ------------------------------------------------------------- sem banco

    def test_instancia_correta_do_agregado(self):
        """repo_factory devolve a implementacao Oracle do catalogo; RBAC_USUARIOS continua registrado."""
        self.assertIsInstance(self.cat, RepoCatalogo)
        self.assertEqual(self.cat.__class__.__name__, "RepoCatalogoOracle")
        self.assertEqual(repo_factory.obter("usuarios").__class__.__name__, "RepoUsuariosOracle")


    def test_sql_qualificado_sem_marcadores_pendentes(self):
        """Todo SQL montado na carga usa o owner qualificado e nenhum marcador sobra."""
        self.assertTrue(self.cat._sql)
        for nome, sql in self.cat._sql.items():
            self.assertNotIn("{", sql, nome)
            self.assertNotIn("SELECT *", sql, nome)
            if "FOR UPDATE" in sql:
                self.assertIn("FOR UPDATE WAIT 5", sql, nome)
        self.assertIn(self.cat.qualificar_tabela("scripts"), self.cat._sql["SCR_OBTER"])

    def test_owner_e_prefixo_parametrizados(self):
        """Owner e table_prefix vem da configuracao: SQL, sequences e constraints seguem o prefixo."""
        cfg = mock.Mock()
        cfg.oracle.owner = "SSS_TEST_CAT"
        cfg.oracle.table_prefix = "abc_"
        repo = RepoCatalogoOracle(cfg=cfg, segredos={})
        for nome, sql in repo._sql.items():
            self.assertNotIn("tbsss_", sql, nome)
        self.assertIn("SSS_TEST_CAT.abc_scripts", repo._sql["SCR_OBTER"])
        self.assertIn("SSS_TEST_CAT.abc_profile_script", repo._sql["EXEC_PERFIL"])
        self.assertEqual(repo._seq["script_param"], "SSS_TEST_CAT.sq_abc_script_param")
        with mock.patch.object(repo, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                repo.scripts_inserir({"name": "s", "interpreter": "SH", "path_file": "x.sh"}, ator="t")
        self.assertEqual(ctx.exception.constraint, "ck_abc_scr_path")

    def test_ator_obrigatorio_antes_de_qualquer_sql(self):
        """Sem ator (ou com mais de 40 caracteres), RepoViolacao sem abrir conexao."""
        with mock.patch.object(self.cat, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            for ator_invalido in (None, "", "   ", "x" * 41):
                for chamada in (
                    lambda a: self.cat.ambientes_inserir({"name": "AMB_X"}, ator=a),
                    lambda a: self.cat.ambientes_alterar(1, {"description": "x"}, ator=a),
                    lambda a: self.cat.scripts_inserir({"name": "s", "interpreter": "SH",
                                                        "path_file": "/opt/s.sh"}, ator=a),
                    lambda a: self.cat.scripts_alterar(1, {"description": "x"}, ator=a),
                    lambda a: self.cat.homologacao_salvar(1, [1], ator=a),
                    lambda a: self.cat.parametros_inserir({"code": "p", "component_type": "TEXT"}, ator=a),
                    lambda a: self.cat.parametros_alterar(1, {"label": "x"}, ator=a),
                    lambda a: self.cat.script_params_salvar(1, [], ator=a),
                ):
                    with self.assertRaises(repo_errors.RepoViolacao):
                        chamada(ator_invalido)

    def test_cks_recusadas_antes_do_banco_com_nome_do_fake(self):
        """CKs de nome, caminho, interpretador, paralelismo e codigo devolvem o nome da constraint do FAKE."""
        n = self.cat.nome_constraint
        with mock.patch.object(self.cat, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            casos = (
                (lambda: self.cat.ambientes_inserir({"name": "minusculo"}, ator="t"), n("ck", "ambientes", "name")),
                (lambda: self.cat.scripts_inserir({"name": "s", "interpreter": "SH",
                                                   "path_file": "relativo.sh"}, ator="t"), n("ck", "scripts", "path")),
                (lambda: self.cat.scripts_inserir({"name": "s", "interpreter": "SH",
                                                   "path_file": "/opt/../x.sh"}, ator="t"), n("ck", "scripts", "path")),
                (lambda: self.cat.scripts_inserir({"name": "s", "interpreter": "SH",
                                                   "path_file": "/" + "a" * 500}, ator="t"), n("ck", "scripts", "path")),
                (lambda: self.cat.scripts_inserir({"name": "s", "interpreter": "PERL",
                                                   "path_file": "/opt/s.pl"}, ator="t"), n("ck", "scripts", "int")),
                (lambda: self.cat.scripts_inserir({"name": "s", "interpreter": "SH", "path_file": "/opt/s.sh",
                                                   "max_parallel_env": 0}, ator="t"), n("ck", "scripts", "paral")),
                (lambda: self.cat.parametros_inserir({"code": "Maiusc", "component_type": "TEXT"},
                                                     ator="t"), n("ck", "parametros", "code")),
            )
            for chamada, ck in casos:
                with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                    chamada()
                self.assertEqual(ctx.exception.constraint, ck)

    def test_scripts_executaveis_sem_exec_script_nao_consulta(self):
        """Nao admin sem EXEC_SCRIPT (ou sem perfil) recebe lista vazia sem ir ao banco."""
        with mock.patch.object(self.cat, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            self.assertEqual(self.cat.scripts_executaveis({"is_admin": False, "profile_id": 3,
                                                           "funcionalidades": frozenset()}), [])
            self.assertEqual(self.cat.scripts_executaveis({"is_admin": False,
                                                           "funcionalidades": frozenset(["EXEC_SCRIPT"])}), [])

    def test_scripts_executaveis_uma_consulta_por_perfil_ou_admin(self):
        """Uma unica consulta: EXISTS em perfil_scr/perfil_amb pelo perfil_id, ou o atalho do admin."""
        cur = _CursorGravador()
        with mock.patch.object(self.cat, "_obter_conexao", return_value=_ConexaoGravadora(cur)):
            self.cat.scripts_executaveis({"is_admin": False, "profile_id": 7,
                                          "funcionalidades": frozenset(["EXEC_SCRIPT"])})
            self.cat.scripts_executaveis({"is_admin": True})
        self.assertEqual(len(cur.executados), 2)
        sql_perfil, binds_perfil = cur.executados[0]
        self.assertIn(self.cat.qualificar_tabela("perfil_scr"), sql_perfil)
        self.assertIn(self.cat.qualificar_tabela("perfil_amb"), sql_perfil)
        self.assertEqual(binds_perfil, {"profile_id": 7})
        sql_admin, binds_admin = cur.executados[1]
        self.assertNotIn(self.cat.qualificar_tabela("perfil_scr"), sql_admin)
        self.assertIn(self.cat.qualificar_tabela("script_amb"), sql_admin)
        self.assertIsNone(binds_admin)

    def test_filtro_de_trecho_escapa_curingas(self):
        """'%' e '_' digitados no filtro sao literais (paridade com o 'in' do FAKE), sempre por bind."""
        cur = _CursorGravador(uma=(0,))
        with mock.patch.object(self.cat, "_obter_conexao", return_value=_ConexaoGravadora(cur)):
            self.cat.scripts_listar(filtros={"name": "carga_10%"})
        sql_conta, binds = cur.executados[0]
        self.assertIn("ROWNUM <= 10001", sql_conta)
        self.assertIn("ESCAPE", sql_conta)
        self.assertEqual(binds["nome_f"], "%carga\\_10\\%%")
        self.assertNotIn("carga", sql_conta)

    # ------------------------------------------------------------- banco real

    def _limpar(self, ids):
        """Remove somente os registros criados por este teste, em transacao propria."""
        conn = self.cat._obter_conexao()
        restantes = []
        try:
            cur = conn.cursor()
            try:
                for tabela, chave in (("script_param", "script_id"), ("script_amb", "script_id"),
                                      ("scripts", "id"), ("parametros", "id"), ("ambientes", "id")):
                    for valor in ids.get(tabela, ()):
                        cur.execute("DELETE FROM " + self.cat.qualificar_tabela(tabela) + " WHERE "
                                    + chave + " = :v", {"v": valor})
                conn.commit()
                for tabela in ("scripts", "parametros", "ambientes"):
                    for valor in ids.get(tabela, ()):
                        cur.execute("SELECT id FROM " + self.cat.qualificar_tabela(tabela) + " WHERE id = :v",
                                    {"v": valor})
                        if cur.fetchone():
                            restantes.append((tabela, valor))
            finally:
                cur.close()
        finally:
            conn.close()
        if restantes:
            self.fail("Limpeza incompleta no schema descartavel: %s" % restantes)

    def test_banco_real_catalogo(self):
        """Ciclo completo no Oracle descartavel: CRUD, esperado, UKs, vinculos por diferenca e executaveis."""
        if not self.tem_banco_real:
            self.skipTest("Banco descartavel real nao configurado (marcado como NAO TESTADO)")

        n = self.cat.nome_constraint
        ator = "teste_catalogo"
        sufixo = datetime.datetime.now().strftime("%H%M%S")
        ids = {"ambientes": [], "scripts": [], "parametros": []}
        ids["script_param"] = ids["scripts"]
        ids["script_amb"] = ids["scripts"]
        try:
            # 1. Ambientes: inclusao, registro, UK, imutabilidade e esperado.
            amb = self.cat.ambientes_inserir({"name": "TST_" + sufixo, "description": "a"}, ator=ator)
            ids["ambientes"].append(amb["id"])
            self.assertEqual(amb["created_by"], ator)
            self.assertIsNone(amb["updated_at"])
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.ambientes_inserir({"name": "TST_" + sufixo}, ator=ator)
            self.assertEqual(ctx.exception.constraint, n("uk", "ambientes", "name"))
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.ambientes_alterar(amb["id"], {"name": "OUTRO_" + sufixo}, ator=ator)
            self.assertEqual(ctx.exception.constraint, self.cat.nome_trigger("ambientes", "bu"))
            with self.assertRaises(repo_errors.RepoConflito):
                self.cat.ambientes_alterar(amb["id"], {"description": "b"}, esperado={"description": "z"}, ator=ator)
            alt = self.cat.ambientes_alterar(amb["id"], {"description": "b"}, esperado={"description": "a"}, ator="bia")
            self.assertEqual((alt["description"], alt["updated_by"], alt["created_by"]), ("b", "bia", ator))
            self.assertEqual(alt["created_at"].microsecond, 0)

            # 2. Scripts: UK sensivel a maiusculas, path_file absoluto e esperado nulo-seguro.
            nome_scr = "Tst_Scr_" + sufixo
            scr = self.cat.scripts_inserir({"name": nome_scr, "interpreter": "SH", "param_type": "NAMED",
                                            "path_file": "/opt/sss_teste/" + sufixo + ".sh"}, ator=ator)
            ids["scripts"].append(scr["id"])
            outro = self.cat.scripts_inserir({"name": nome_scr.lower(), "interpreter": "SH",
                                              "path_file": "/opt/sss_teste/b.sh"}, ator=ator)
            ids["scripts"].append(outro["id"])
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.scripts_inserir({"name": nome_scr, "interpreter": "SH",
                                          "path_file": "/opt/sss_teste/c.sh"}, ator=ator)
            self.assertEqual(ctx.exception.constraint, n("uk", "scripts", "name"))
            alt = self.cat.scripts_alterar(scr["id"], {"script_group": "G1"}, esperado={"script_group": None,
                                                                                  "path_file": scr["path_file"]},
                                           ator=ator)
            self.assertEqual(alt["script_group"], "G1")
            self.assertEqual(alt["updated_by"], ator)

            # 3. Homologacao por diferenca: vinculo que continua mantem o created_*.
            self.assertEqual(self.cat.homologacao_salvar(scr["id"], [amb["id"]], esperado=[], ator=ator),
                             [amb["id"]])
            with self.assertRaises(repo_errors.RepoConflito):
                self.cat.homologacao_salvar(scr["id"], [], esperado=[], ator=ator)
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.homologacao_salvar(scr["id"], [amb["id"], 999999999], ator=ator)
            self.assertEqual(ctx.exception.constraint, n("fk", "script_amb", "env"))

            # 4. Parametros e vinculos: NOMEADO exige flag; created_* preservado; dependencias.
            sem_flag = self.cat.parametros_inserir({"code": "tst_sf_" + sufixo, "label": "X",
                                                    "component_type": "TEXT"}, ator=ator)
            ids["parametros"].append(sem_flag["id"])
            com_flag = self.cat.parametros_inserir({"code": "tst_cf_" + sufixo, "label": "Y",
                                                    "component_type": "TEXT", "param_flag": "--y"}, ator=ator)
            ids["parametros"].append(com_flag["id"])
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.script_params_salvar(scr["id"], [{"parameter_id": sem_flag["id"], "sort_order": 1}], ator=ator)
            self.assertEqual(ctx.exception.constraint, "sss_scr_nomeado_sem_flag")
            v1 = self.cat.script_params_salvar(scr["id"], [{"parameter_id": com_flag["id"], "sort_order": 1,
                                                            "required": "Y"}], esperado=[], ator=ator)
            self.assertEqual([v["parameter_id"] for v in v1], [com_flag["id"]])
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.parametros_alterar(com_flag["id"], {"component_type": "NUMBER"}, ator=ator)
            self.assertEqual(ctx.exception.constraint, "sss_prm_tipo_vinculado")
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.parametros_alterar(com_flag["id"], {"active": "N"}, ator=ator)
            self.assertEqual(ctx.exception.constraint, "sss_prm_vinculo_ativo")
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.scripts_alterar(scr["id"], {"param_type": "NONE"}, ator=ator)
            self.assertEqual(ctx.exception.constraint, "sss_scr_nenhum_vinculado")
            self.assertEqual(self.cat.scripts_obter(scr["id"])["param_type"], "NAMED")

            conn = self.cat._obter_conexao()
            try:
                cur = conn.cursor()
                try:
                    sql = ("SELECT created_at, created_by FROM " + self.cat.qualificar_tabela("script_param")
                           + " WHERE script_id = :s AND parameter_id = :p")
                    cur.execute(sql, {"s": scr["id"], "p": com_flag["id"]})
                    criado_antes = cur.fetchone()
                finally:
                    cur.close()
            finally:
                conn.close()
            self.cat.script_params_salvar(scr["id"], [{"parameter_id": com_flag["id"], "sort_order": 1,
                                                       "required": "Y"}],
                                          esperado=[(com_flag["id"], 1, "Y", None)], ator="outro")
            conn = self.cat._obter_conexao()
            try:
                cur = conn.cursor()
                try:
                    cur.execute(sql, {"s": scr["id"], "p": com_flag["id"]})
                    self.assertEqual(cur.fetchone(), criado_antes)
                finally:
                    cur.close()
            finally:
                conn.close()

            # 5. Listagens: total limitado, contagens e homologados na mesma leitura.
            lista = self.cat.scripts_listar(filtros={"name": nome_scr})
            self.assertIn("total_limitado", lista)
            item = [i for i in lista["itens"] if i["id"] == scr["id"]][0]
            self.assertEqual(item["ambientes_homologados"], [amb["name"]])
            self.assertEqual(item["qtd_parametros"], 1)
            prm = self.cat.parametros_listar(filtros={"code": "tst_cf_" + sufixo})["itens"][0]
            self.assertEqual(prm["qtd_scripts"], len(self.cat.parametro_vinculos(com_flag["id"])))

            # 6. Executaveis do admin: script ativo homologado em ambiente ativo.
            executaveis = [s["id"] for s in self.cat.scripts_executaveis({"is_admin": True})]
            self.assertIn(scr["id"], executaveis)
            self.assertNotIn(outro["id"], executaveis)
        finally:
            self._limpar(ids)


class _CursorRoteirizado(object):
    """Cursor de mentira que responde por trecho do SQL: roteiro = [(trecho, rowcount, linhas)]."""

    def __init__(self, conexao):
        self._conexao = conexao
        self.rowcount = 0
        self._linhas = []

    def execute(self, sql, binds=None):
        # Como o python-oracledb (DPY-4008): tipo declarado para bind que nao existe no SQL.
        for nome in getattr(self, "_tipos", {}):
            if ":" + nome not in sql:
                raise RuntimeError("DPY-4008: no bind placeholder named \":%s\" was found in the SQL text" % nome)
        self._tipos = {}
        self._conexao.executados.append((sql, binds))
        if ".NEXTVAL FROM DUAL" in sql:
            self._conexao.seq += 1
            self.rowcount, self._linhas = 1, [(self._conexao.seq,)]
            return
        for trecho, rowcount, linhas in self._conexao.roteiro:
            if trecho in sql:
                self.rowcount, self._linhas = rowcount, list(linhas)
                return
        self.rowcount, self._linhas = 0, []

    def setinputsizes(self, **tipos):
        self._tipos = tipos

    def fetchone(self):
        return self._linhas[0] if self._linhas else None

    def fetchall(self):
        return list(self._linhas)

    def fetchmany(self, n):
        lote, self._linhas = self._linhas[:n], self._linhas[n:]
        return lote

    def close(self):
        pass


class _ConexaoRoteirizada(object):
    def __init__(self, roteiro):
        self.roteiro = roteiro
        self.executados = []
        self.seq = 1000
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _CursorRoteirizado(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass

    def auditorias(self):
        return [b for sql, b in self.executados if sql.startswith("INSERT INTO") and "auditoria" in sql]


class TestOracleTickets(unittest.TestCase):
    """Testes de conformidade e integridade para o agregado TICKETS no Oracle (passo 3 do F7.3)."""

    @classmethod
    def setUpClass(cls):
        agregado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if agregado != "TICKETS":
            raise unittest.SkipTest("Execucao restrita ao agregado TICKETS (atual: %s)" % agregado)
        _preparar_banco_real(cls)

    @classmethod
    def tearDownClass(cls):
        _restaurar_banco_real(cls)

    def setUp(self):
        repo_factory.reset_singletons()
        self.tck = repo_factory.obter("tickets")

    # ------------------------------------------------------------- sem banco

    def test_instancia_correta_do_agregado(self):
        """repo_factory devolve a implementacao Oracle de tickets; os agregados anteriores continuam."""
        self.assertIsInstance(self.tck, RepoTickets)
        self.assertEqual(self.tck.__class__.__name__, "RepoTicketsOracle")
        self.assertEqual(repo_factory.obter("catalogo").__class__.__name__, "RepoCatalogoOracle")
        self.assertEqual(repo_factory.obter("usuarios").__class__.__name__, "RepoUsuariosOracle")


    def test_owner_e_prefixo_parametrizados(self):
        """SQL, sequences e constraints seguem owner e table_prefix da configuracao."""
        cfg = mock.Mock()
        cfg.oracle.owner = "SSS_TEST_TCK"
        cfg.oracle.table_prefix = "abc_"
        repo = RepoTicketsOracle(cfg=cfg, segredos={})
        for nome, sql in repo._sql.items():
            self.assertNotIn("tbsss_", sql, nome)
            self.assertNotIn("SELECT *", sql, nome)
        self.assertIn("SSS_TEST_TCK.abc_tickets", repo._sql["OBTER"])
        self.assertEqual(repo._seq_tck, "SSS_TEST_TCK.sq_abc_tickets")
        with mock.patch.object(repo, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                repo.criar({"script_id": 1, "environment": "X", "requested_by": "u", "priority": 9}, [])
        self.assertEqual(ctx.exception.constraint, "ck_abc_tck_prio")

    def test_cancelamento_usa_os_updates_literais_do_readme(self):
        """README §5.6: os dois UPDATEs e a leitura pela PK com FOR UPDATE WAIT 5."""
        tck = self.tck._idents["tck"]
        self.assertEqual(self.tck._sql["CANCEL_SINALIZAR"],
                         "UPDATE " + tck + " SET cancel_requested = 'Y', updated_at = SYSDATE, updated_by = :actor "
                         "WHERE id = :id AND status IN ('PENDING', 'RUNNING') AND cancel_requested = 'N'")
        self.assertEqual(self.tck._sql["CANCEL_PENDENTE"],
                         "UPDATE " + tck + " SET status = 'CANCELLED', status_reason = 'CANCEL_USER', "
                         "return_code = -1, finished_at = SYSDATE, updated_at = SYSDATE, updated_by = :actor "
                         "WHERE id = :id AND status = 'PENDING'")
        self.assertTrue(self.tck._sql["CANCEL_LER"].endswith("WHERE id = :id FOR UPDATE WAIT 5"))

    def test_listagens_e_leituras_do_cr004_sem_clob(self):
        """Nenhuma listagem le CLOB; obter traz parametros_enviados mas nunca log_output."""
        for modelo in ("_SQL_LISTAR", "_SQL_CONTAR", "_SQL_ULTIMAS", "_SQL_HISTORICO", "_SQL_RESPOSTAS"):
            sql = getattr(sys.modules[RepoTicketsOracle.__module__], modelo)
            self.assertNotIn("log_output", sql, modelo)
            self.assertNotIn("submitted_params", sql, modelo)
        self.assertNotIn("log_output", self.tck._sql["OBTER"])
        self.assertIn("submitted_params", self.tck._sql["OBTER"])
        self.assertIn("ROW_NUMBER() OVER (PARTITION BY t.script_id ORDER BY t.created_at DESC, t.id DESC)",
                      sys.modules[RepoTicketsOracle.__module__]._SQL_ULTIMAS)

    def test_ator_obrigatorio_antes_de_qualquer_sql(self):
        with mock.patch.object(self.tck, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            for ator in (None, "", "   ", "x" * 41):
                with self.assertRaises(repo_errors.RepoViolacao):
                    self.tck.criar({"script_id": 1, "environment": "X", "requested_by": ator}, [], ator=ator)
                with self.assertRaises(repo_errors.RepoViolacao):
                    self.tck.solicitar_cancelamento(1, ator, "127.0.0.1")

    def _cancelar_com(self, roteiro):
        conn = _ConexaoRoteirizada(roteiro)
        with mock.patch.object(self.tck, "_obter_conexao", return_value=conn):
            retorno = self.tck.solicitar_cancelamento(7, "ana", "10.0.0.1")
        return retorno, conn

    def test_cancelamento_nos_quatro_resultados_e_residuo_pending(self):
        """Cada desfecho do §5.6 audita TICKET_CANCEL com o resultado, numa transacao confirmada."""
        casos = (
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
        for roteiro, esperado, detalhe in casos:
            retorno, conn = self._cancelar_com(roteiro)
            self.assertEqual(retorno, esperado)
            auds = conn.auditorias()
            self.assertEqual(len(auds), 1)
            self.assertEqual((auds[0]["action"], auds[0]["detail"], auds[0]["actor"], auds[0]["entity_id"]),
                             ("TICKET_CANCEL", detalhe, "ana", 7))
            self.assertEqual((conn.commits, conn.rollbacks), (1, 0))

    def test_cancelamento_de_ticket_inexistente(self):
        conn = _ConexaoRoteirizada([])
        with mock.patch.object(self.tck, "_obter_conexao", return_value=conn):
            with self.assertRaises(repo_errors.RepoNaoEncontrado):
                self.tck.solicitar_cancelamento(7, "ana", "10.0.0.1")
        self.assertEqual(conn.auditorias(), [])
        self.assertEqual((conn.commits, conn.rollbacks), (0, 1))

    def test_criar_sem_gravacao_parcial_com_fk_ausente(self):
        """FK conferida antes de qualquer INSERT: nada e gravado e a transacao e desfeita."""
        roteiro = [("WHERE id = :id", 1, [(1,)]), ("WHERE name = :name", 0, [])]
        conn = _ConexaoRoteirizada(roteiro)
        with mock.patch.object(self.tck, "_obter_conexao", return_value=conn):
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.tck.criar({"script_id": 1, "environment": "NAO_EXISTE", "requested_by": "ana"}, [])
        self.assertEqual(ctx.exception.constraint, "fk_tbsss_tck_env")
        self.assertFalse([s for s, _b in conn.executados if s.startswith("INSERT")])
        self.assertEqual(conn.rollbacks, 1)

    def test_listar_filtros_por_bind_e_escopo_vazio(self):
        """Status e escopo por IN de placeholders; escopo vazio nao devolve nada; datas como bind."""
        conn = _ConexaoRoteirizada([("SELECT COUNT(*)", 1, [(0,)])])
        with mock.patch.object(self.tck, "_obter_conexao", return_value=conn):
            self.tck.listar({"status": ["RUNNING", "PENDING"], "origem": "manual",
                             "criado_inicio": datetime.datetime(2026, 1, 1)}, escopo_ambientes=["HML", "PROD"])
            self.tck.listar({}, escopo_ambientes=[])
        sql, binds = conn.executados[0]
        self.assertIn("ROWNUM <= 10001", sql)
        self.assertIn("status IN (:s0, :s1)", sql)
        self.assertIn("environment IN (:e0, :e1)", sql)
        self.assertIn("schedule_id IS NULL", sql)
        self.assertIn("created_at >= :criado_inicio", sql)
        self.assertNotIn("RUNNING", sql)
        self.assertEqual((binds["s0"], binds["s1"], binds["e0"]), ("PENDING", "RUNNING", "HML"))
        self.assertIn("1 = 0", conn.executados[2][0])

    # ------------------------------------------------------------- banco real

    def _fixtures_do_seed(self):
        """Cadastros existentes (somente leitura): um script, um ambiente, um parametro e um login."""
        c = self.tck._obter_conexao()
        try:
            cur = c.cursor()
            try:
                cur.execute("SELECT MIN(id) FROM " + self.tck._idents["scr"])
                script_id = cur.fetchone()[0]
                cur.execute("SELECT MIN(name) FROM " + self.tck._idents["amb"])
                ambiente = cur.fetchone()[0]
                cur.execute("SELECT MIN(id), MAX(id) FROM " + self.tck._idents["prm"])
                prm1, prm2 = cur.fetchone()
                cur.execute("SELECT MIN(login) FROM " + self.tck._idents["usr"])
                login = cur.fetchone()[0]
            finally:
                cur.close()
        finally:
            c.close()
        if None in (script_id, ambiente, prm1, login) or prm1 == prm2:
            self.skipTest("Seed do catalogo ausente no banco real (implante o 01_deploy_sss.sql)")
        return script_id, ambiente, prm1, prm2, login

    def _limpar(self, ids, marca_ip):
        """Remove so os tickets criados por este teste (respostas em cascata) e, no modo compartilhado,
        a auditoria deles; falha se sobrar algo."""
        c = self.tck._obter_conexao()
        try:
            cur = c.cursor()
            try:
                for tid in ids:
                    cur.execute("DELETE FROM " + self.tck._idents["tck"] + " WHERE id = :id", {"id": tid})
                    if _oracle_test_support.modo_schema() == _oracle_test_support.MODO_COMPARTILHADO:
                        cur.execute("DELETE FROM " + self.tck._tbl_aud + " WHERE entity = 'tbsss_tickets' "
                                    "AND entity_id = :id AND action IN ('TICKET_CREATE', 'TICKET_RERUN', "
                                    "'TICKET_CANCEL')", {"id": tid})
                c.commit()
                cur.execute("SELECT COUNT(*) FROM " + self.tck._idents["tck"] + " WHERE source_ip = :ip",
                            {"ip": marca_ip})
                restantes = cur.fetchone()[0]
            finally:
                cur.close()
        finally:
            c.close()
        if restantes:
            self.fail("Limpeza incompleta: %d ticket(s) com ip_origem %s" % (restantes, marca_ip))

    def _contar_por_ip(self, marca_ip):
        c = self.tck._obter_conexao()
        try:
            cur = c.cursor()
            try:
                cur.execute("SELECT COUNT(*) FROM " + self.tck._idents["tck"] + " WHERE source_ip = :ip",
                            {"ip": marca_ip})
                return cur.fetchone()[0]
            finally:
                cur.close()
        finally:
            c.close()

    def test_banco_real_tickets(self):
        """Ciclo no Oracle: criar com respostas, FKs sem gravacao parcial, cancelamento, log e leituras."""
        if not self.tem_banco_real:
            self.skipTest("Banco descartavel real nao configurado (marcado como NAO TESTADO)")
        n = self.tck.nome_constraint
        script_id, ambiente, prm1, prm2, login = self._fixtures_do_seed()
        marca_ip = "tst-%s" % datetime.datetime.now().strftime("%H%M%S%f")
        base = {"script_id": script_id, "environment": ambiente, "requested_by": login, "source_ip": marca_ip,
                "submitted_params": '{"args": ["--x"]}'}
        ids = []
        try:
            agora = self.tck.agora()
            self.assertEqual(agora.microsecond, 0)

            # 1. criar: ticket + respostas; created_by = solicitante; obter sem log_output.
            t1 = self.tck.criar(dict(base), [{"parameter_id": prm1, "answer_value": "a"},
                                             {"parameter_id": prm2, "answer_value": "b"}])
            ids.append(t1)
            reg = self.tck.obter(t1)
            self.assertNotIn("log_output", reg)
            self.assertEqual(reg["submitted_params"], base["submitted_params"])
            self.assertEqual((reg["status"], reg["created_by"], reg["updated_at"]), ("PENDING", login, None))
            self.assertEqual([r["answer_value"] for r in self.tck.respostas(t1)], ["a", "b"])

            # 2. FKs e UK: nenhuma linha gravada em caso de violacao.
            antes = self._contar_por_ip(marca_ip)
            for dados, resp, ck in (
                (dict(base, script_id=999999999), [], n("fk", "tickets", "scr")),
                (dict(base, environment="NAO_EXISTE_TST"), [], n("fk", "tickets", "env")),
                (dict(base, requested_by="nao.existe.tst"), [], n("fk", "tickets", "usr")),
                (dict(base, parent_ticket_id=999999999), [], n("fk", "tickets", "parent")),
                (dict(base), [{"parameter_id": 999999999}], n("fk", "ticket_resp", "prm")),
                (dict(base), [{"parameter_id": prm1}, {"parameter_id": prm1}], n("uk", "ticket_resp", "tck_prm")),
            ):
                with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                    self.tck.criar(dados, resp)
                self.assertEqual(ctx.exception.constraint, ck)
            self.assertEqual(self._contar_por_ip(marca_ip), antes)

            # 3. Cancelamento nos quatro resultados (README §5.6) e o residuo PENDING com 'S' (CR-008, R-02).
            self.assertEqual(self.tck.solicitar_cancelamento(t1, "teste_tck", marca_ip), "CANCELADO")
            cancelado = self.tck.obter(t1)
            self.assertEqual((cancelado["status"], cancelado["status_reason"], cancelado["return_code"]),
                             ("CANCELLED", "CANCEL_USER", -1))
            self.assertEqual((cancelado["updated_by"], cancelado["created_by"]), ("teste_tck", login))
            self.assertEqual(self.tck.solicitar_cancelamento(t1, "teste_tck", marca_ip), "TERMINAL")
            t2 = self.tck.criar(dict(base, status="RUNNING", agent_id="tst-agente", started_at=agora), [])
            ids.append(t2)
            self.assertEqual(self.tck.solicitar_cancelamento(t2, "teste_tck", marca_ip), "SINALIZADO")
            self.assertEqual(self.tck.solicitar_cancelamento(t2, "teste_tck", marca_ip), "JA_SINALIZADO")
            self.assertEqual(self.tck.obter(t2)["status"], "RUNNING")
            t3 = self.tck.criar(dict(base, cancel_requested="Y"), [])
            ids.append(t3)
            self.assertEqual(self.tck.solicitar_cancelamento(t3, "teste_tck", marca_ip), "CANCELADO")
            with self.assertRaises(repo_errors.RepoNaoEncontrado):
                self.tck.solicitar_cancelamento(999999999, "teste_tck", marca_ip)

            # 4. log_ler por locator: base 0 na API, offset alem do fim, negativo e max_chars < 1.
            log = "".join("linha %03d ção\n" % i for i in range(40))
            t4 = self.tck.criar(dict(base, status="SUCCESS", log_output=log, finished_at=agora), [])
            ids.append(t4)
            texto, prox, terminal, truncado = self.tck.log_ler(t4, 0, 20)
            self.assertEqual((texto, prox, terminal, truncado), (log[:20], 20, True, False))
            self.assertEqual(self.tck.log_ler(t4, 20, 20)[0], log[20:40])
            self.assertEqual(self.tck.log_ler(t4, -5, 10)[:2], (log[:10], 10))
            self.assertEqual(self.tck.log_ler(t4, len(log) + 5, 10)[:2], ("", len(log) + 5))
            self.assertEqual(self.tck.log_ler(t4, 0, 0)[0], log)
            self.assertEqual(self.tck.log_ler(t1, 0, 10)[:3], ("", 0, True))

            # 5. Leituras: listar sem CLOB, ultima execucao e historico (os mais recentes, crescente).
            lista = self.tck.listar({"script_id": script_id, "criado_inicio": agora}, tamanho=50)
            meus = [i["id"] for i in lista["itens"] if i["id"] in ids]
            self.assertEqual(sorted(meus, reverse=True), meus)
            self.assertEqual(set(meus), set(ids))
            for item in lista["itens"]:
                self.assertNotIn("log_output", item)
                self.assertNotIn("submitted_params", item)
            self.assertIn("total_limitado", lista)
            so_cancelados = self.tck.listar({"script_id": script_id, "status": ["CANCELLED"],
                                             "criado_inicio": agora}, escopo_ambientes=[ambiente])
            self.assertEqual(sorted(i["id"] for i in so_cancelados["itens"] if i["id"] in ids), sorted([t1, t3]))
            self.assertEqual(self.tck.listar({"script_id": script_id}, escopo_ambientes=[])["total"], 0)
            ultima = self.tck.ultimas_execucoes([script_id], escopo_ambientes=[ambiente], solicitante=login)
            self.assertEqual(ultima[script_id]["id"], max(ids))
            self.assertEqual(sorted(ultima[script_id]), ["created_at", "finished_at", "id", "status", "status_reason"])
            self.assertEqual(self.tck.ultimas_execucoes([script_id], escopo_ambientes=[]), {})
            hist = self.tck.historico_script(script_id, agora, escopo_ambientes=[ambiente], limite=2)
            self.assertEqual([h["id"] for h in hist], sorted(ids)[-2:])
            self.assertEqual(sorted(hist[0]), ["created_at", "finished_at", "id", "started_at", "status",
                                               "status_reason"])
        finally:
            self._limpar(ids, marca_ip)


class TestOracleAgendamentos(unittest.TestCase):
    """Testes de conformidade e integridade para o agregado AGENDAMENTOS no Oracle (passo 4 do F7.3)."""

    @classmethod
    def setUpClass(cls):
        agregado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if agregado != "AGENDAMENTOS":
            raise unittest.SkipTest("Execucao restrita ao agregado AGENDAMENTOS (atual: %s)" % agregado)
        _preparar_banco_real(cls)

    @classmethod
    def tearDownClass(cls):
        _restaurar_banco_real(cls)

    def setUp(self):
        repo_factory.reset_singletons()
        self.agd = repo_factory.obter("agendamentos")

    # ------------------------------------------------------------- sem banco

    def test_instancia_correta_do_agregado(self):
        self.assertIsInstance(self.agd, RepoAgendamentos)
        self.assertEqual(self.agd.__class__.__name__, "RepoAgendamentosOracle")
        self.assertEqual(repo_factory.obter("tickets").__class__.__name__, "RepoTicketsOracle")


    def test_owner_e_prefixo_parametrizados(self):
        cfg = mock.Mock()
        cfg.oracle.owner = "SSS_TEST_AGD"
        cfg.oracle.table_prefix = "abc_"
        repo = RepoAgendamentosOracle(cfg=cfg, segredos={})
        for nome, sql in repo._sql.items():
            self.assertNotIn("tbsss_", sql, nome)
            self.assertNotIn("SELECT *", sql, nome)
        self.assertIn("SSS_TEST_AGD.abc_schedules", repo._sql["OBTER"])
        self.assertEqual(repo._seq_agd, "SSS_TEST_AGD.sq_abc_schedules")
        with self.assertRaises(repo_errors.RepoViolacao) as ctx:
            repo._checar_cks({"name": "x", "recurrence_type": "ANUAL"})
        self.assertEqual(ctx.exception.constraint, "ck_abc_sch_rtype")

    def test_pausar_condicional_a_regra_ativa_e_a_data_lida(self):
        """CR-007, R-19: o UPDATE exige active = 'Y' e, com antiga_data, a next_run_at lida."""
        self.assertTrue(self.agd._sql["PAUSAR"].endswith("WHERE id = :id AND active = 'Y'"))
        self.assertTrue(self.agd._sql["PAUSAR_OTIMISTA"].endswith(
            "WHERE id = :id AND active = 'Y' AND next_run_at = :antiga_data"))
        self.assertIn("updated_at = SYSDATE, updated_by = :actor", self.agd._sql["PAUSAR"])
        self.assertIn("FOR UPDATE WAIT 5", self.agd._sql["OBTER_LOCK"])

    def test_cks_com_os_nomes_do_fake(self):
        n = lambda s: "ck_tbsss_agd_" + s  # noqa: E731
        base = {"name": "r", "recurrence_type": "DAILY", "priority": 2, "active": "Y", "run_time": "08:00",
                "start_date": datetime.datetime(2026, 1, 1), "next_run_at": datetime.datetime(2026, 1, 2)}
        casos = (
            ({"recurrence_type": "ANUAL"}, n("trec")), ({"priority": 5}, n("prio")), ({"priority": True}, n("prio")),
            ({"active": "X"}, n("active")), ({"month_day": 32}, n("dia")), ({"run_time": "24:00"}, n("hora")),
            ({"week_days": "8"}, n("dsem")), ({"end_date": datetime.datetime(2025, 1, 1)}, n("fim")),
            ({"pause_reason": "OUTRO"}, n("pausa")), ({"run_time": None}, n("campos")),
            ({"recurrence_type": "CRON"}, n("campos")),
        )
        for mudanca, ck in casos:
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.agd._checar_cks(dict(base, **mudanca))
            self.assertEqual(ctx.exception.constraint, ck, mudanca)
        with self.assertRaises(repo_errors.RepoViolacao):
            self.agd._checar_cks(dict(base, name="x" * 61))

    def test_ator_obrigatorio_antes_de_qualquer_sql(self):
        with mock.patch.object(self.agd, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            for ator in (None, "", "   ", "x" * 41):
                for chamada in (
                    lambda a: self.agd.inserir({"script_id": 1, "environment": "X", "user_id": 1}, ator=a),
                    lambda a: self.agd.alterar(1, {"name": "y"}, ator=a),
                    lambda a: self.agd.pausar(1, "MANUAL", ator=a),
                    lambda a: self.agd.retomar(1, datetime.datetime(2026, 1, 1), ator=a),
                ):
                    with self.assertRaises(repo_errors.RepoViolacao):
                        chamada(ator)

    def test_pausar_sem_linha_afetada_e_conflito(self):
        """Regra existente, mas nao ativa (ou com outra proxima_execucao): RepoConflito e ROLLBACK."""
        conn = _ConexaoRoteirizada([("WHERE id = :id AND active = 'Y'", 0, []), ("SELECT id FROM", 1, [(7,)])])
        with mock.patch.object(self.agd, "_obter_conexao", return_value=conn):
            with self.assertRaises(repo_errors.RepoConflito):
                self.agd.pausar(7, "MANUAL", antiga_data=datetime.datetime(2026, 1, 1, 8, 0, 0, 123456), ator="ana")
        self.assertEqual((conn.commits, conn.rollbacks), (0, 1))
        self.assertEqual(conn.auditorias(), [])

    def test_listar_escopo_vazio_e_filtros_por_bind(self):
        conn = _ConexaoRoteirizada([("SELECT COUNT(*)", 1, [(0,)])])
        with mock.patch.object(self.agd, "_obter_conexao", return_value=conn):
            self.agd.listar({"active": "Y", "name": "50%_x"}, escopo_ambientes=["HML"])
            self.agd.listar({}, escopo_ambientes=[])
        sql, binds = conn.executados[0]
        self.assertIn("environment IN (:e0)", sql)
        self.assertIn("ROWNUM <= 10001", sql)
        self.assertEqual(binds["nome_f"], "%50\\%\\_x%")
        self.assertIn("1 = 0", conn.executados[2][0])

    # ------------------------------------------------------------- banco real

    def _fixtures_do_seed(self):
        c = self.agd._obter_conexao()
        try:
            cur = c.cursor()
            try:
                cur.execute("SELECT MIN(id) FROM " + self.agd._idents["scr"])
                script_id = cur.fetchone()[0]
                cur.execute("SELECT MIN(name) FROM " + self.agd._idents["amb"])
                ambiente = cur.fetchone()[0]
                cur.execute("SELECT MIN(id), MIN(login) FROM " + self.agd._idents["usr"])
                usuario_id, login = cur.fetchone()
            finally:
                cur.close()
        finally:
            c.close()
        if None in (script_id, ambiente, usuario_id):
            self.skipTest("Seed do catalogo ausente no banco real (implante o 01_deploy_sss.sql)")
        return script_id, ambiente, usuario_id, login

    def _limpar(self, agd_ids, tck_ids, marca):
        """Remove so os registros criados por este teste e, no modo compartilhado, a auditoria deles."""
        compartilhado = _oracle_test_support.modo_schema() == _oracle_test_support.MODO_COMPARTILHADO
        tck = repo_factory.obter("tickets")
        c = self.agd._obter_conexao()
        try:
            cur = c.cursor()
            try:
                for tid in tck_ids:
                    cur.execute("DELETE FROM " + tck._idents["tck"] + " WHERE id = :id", {"id": tid})
                    if compartilhado:
                        cur.execute("DELETE FROM " + self.agd._tbl_aud + " WHERE entity = 'tbsss_tickets' "
                                    "AND entity_id = :id", {"id": tid})
                for aid in agd_ids:
                    cur.execute("DELETE FROM " + self.agd._idents["agd"] + " WHERE id = :id", {"id": aid})
                    if compartilhado:
                        cur.execute("DELETE FROM " + self.agd._tbl_aud + " WHERE entity = 'tbsss_schedules' "
                                    "AND entity_id = :id", {"id": aid})
                c.commit()
                cur.execute("SELECT COUNT(*) FROM " + self.agd._idents["agd"] + " WHERE name LIKE :m",
                            {"m": marca + "%"})
                restantes = cur.fetchone()[0]
            finally:
                cur.close()
        finally:
            c.close()
        if restantes:
            self.fail("Limpeza incompleta: %d agendamento(s) com nome %s*" % (restantes, marca))

    def _contar(self, marca):
        c = self.agd._obter_conexao()
        try:
            cur = c.cursor()
            try:
                cur.execute("SELECT COUNT(*) FROM " + self.agd._idents["agd"] + " WHERE name LIKE :m",
                            {"m": marca + "%"})
                return cur.fetchone()[0]
            finally:
                cur.close()
        finally:
            c.close()

    def test_banco_real_agendamentos(self):
        """Ciclo no Oracle: CRUD, CKs e FKs sem gravacao parcial, pausa otimista, microssegundos e ocorrencia."""
        if not self.tem_banco_real:
            self.skipTest("Testes Oracle reais desligados (marcado como NAO TESTADO)")
        script_id, ambiente, usuario_id, login = self._fixtures_do_seed()
        marca = "TST_AGD_%s" % datetime.datetime.now().strftime("%H%M%S%f")
        agora = self.agd.agora() if hasattr(self.agd, "agora") else repo_factory.obter("tickets").agora()
        amanha = agora + datetime.timedelta(days=1)
        base = {"name": marca + "_1", "script_id": script_id, "environment": ambiente, "user_id": usuario_id,
                "recurrence_type": "DAILY", "run_time": "08:00", "start_date": agora,
                "next_run_at": amanha, "params_json": '{"p": "v"}'}
        n = self.agd.nome_constraint
        agd_ids, tck_ids = [], []
        try:
            # 1. inserir: created_* do criador; parametros_json no obter e no listar.
            r1 = self.agd.inserir(dict(base), ator="teste_agd")
            agd_ids.append(r1["id"])
            self.assertEqual((r1["created_by"], r1["updated_at"], r1["params_json"]), ("teste_agd", None, '{"p": "v"}'))
            self.assertEqual(r1["next_run_at"], amanha.replace(microsecond=0))

            # 2. CKs e FKs: nada gravado em caso de violacao.
            antes = self._contar(marca)
            for dados, ck in (
                (dict(base, recurrence_type="ANUAL"), n("ck", "agendamentos", "rtype")),
                (dict(base, run_time=None), n("ck", "agendamentos", "fields")),
                (dict(base, end_date=agora - datetime.timedelta(days=1)), n("ck", "agendamentos", "end")),
                (dict(base, script_id=999999999), n("fk", "agendamentos", "scr")),
                (dict(base, user_id=999999999), n("fk", "agendamentos", "usr")),
                (dict(base, environment="NAO_EXISTE_TST"), n("fk", "agendamentos", "env")),
            ):
                with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                    self.agd.inserir(dados, ator="teste_agd")
                self.assertEqual(ctx.exception.constraint, ck)
            self.assertEqual(self._contar(marca), antes)

            # 3. alterar condicional ao esperado; created_* preservado, updated_* com o editor.
            with self.assertRaises(repo_errors.RepoConflito):
                self.agd.alterar(r1["id"], {"run_time": "09:00"}, esperado={"run_time": "07:00"}, ator="bia")
            r1b = self.agd.alterar(r1["id"], {"run_time": "09:00"}, esperado={"run_time": "08:00"}, ator="bia")
            self.assertEqual((r1b["run_time"], r1b["updated_by"], r1b["created_by"]), ("09:00", "bia", "teste_agd"))
            with self.assertRaises(repo_errors.RepoViolacao):
                self.agd.alterar(r1["id"], {"week_days": "9"}, ator="bia")
            self.assertEqual(self.agd.obter(r1["id"])["week_days"], None)

            # 4. pausar: microssegundos no bind nao dao conflito (README §7.5); regra ja pausada da conflito.
            lida = self.agd.obter(r1["id"])["next_run_at"]
            pausado = self.agd.pausar(r1["id"], "MANUAL", antiga_data=lida.replace(microsecond=543210), ator="bia")
            self.assertEqual((pausado["active"], pausado["pause_reason"]), ("N", "MANUAL"))
            with self.assertRaises(repo_errors.RepoConflito):
                self.agd.pausar(r1["id"], "MANUAL", ator="bia")
            r2 = self.agd.inserir(dict(base, name=marca + "_2"), ator="teste_agd")
            agd_ids.append(r2["id"])
            with self.assertRaises(repo_errors.RepoConflito):
                self.agd.pausar(r2["id"], "MANUAL", antiga_data=amanha + datetime.timedelta(minutes=5), ator="bia")
            with self.assertRaises(repo_errors.RepoNaoEncontrado):
                self.agd.pausar(999999999, "MANUAL", ator="bia")
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.agd.pausar(r2["id"], "OUTRO", ator="bia")
            self.assertEqual(ctx.exception.constraint, n("ck", "agendamentos", "pause"))

            # 5. retomar condicional ao esperado.
            nova = amanha + datetime.timedelta(days=1)
            with self.assertRaises(repo_errors.RepoConflito):
                self.agd.retomar(r1["id"], nova, esperado={"active": "Y"}, ator="bia")
            retomado = self.agd.retomar(r1["id"], nova, esperado={"active": "N", "next_run_at": lida}, ator="bia")
            self.assertEqual((retomado["active"], retomado["pause_reason"]), ("Y", None))
            self.assertEqual(retomado["next_run_at"], nova.replace(microsecond=0))

            # 6. listar: filtro por trecho, escopo e parametros_json presente (excecao documentada).
            lista = self.agd.listar({"name": marca.lower()}, escopo_ambientes=[ambiente])
            self.assertEqual(sorted(i["id"] for i in lista["itens"]), sorted(agd_ids))
            self.assertTrue(all(i["params_json"] == '{"p": "v"}' for i in lista["itens"]))
            self.assertEqual(self.agd.listar({"name": marca.lower()}, escopo_ambientes=[])["total"], 0)
            self.assertEqual([i["id"] for i in self.agd.listar({"name": marca.lower(), "active": "N"})["itens"]], [])

            # 7. ticket_status e a ocorrencia unica do agendamento (ix_<prefixo>tck_ocor, CR-007 R-27).
            tck = repo_factory.obter("tickets")
            self.assertIsNone(self.agd.ticket_status(None))
            self.assertIsNone(self.agd.ticket_status(999999999))
            ocorrencia = amanha.replace(second=0, microsecond=0)
            t1 = tck.criar({"script_id": script_id, "environment": ambiente, "requested_by": login,
                            "schedule_id": r1["id"], "scheduled_at": ocorrencia}, [])
            tck_ids.append(t1)
            self.assertEqual(self.agd.ticket_status(t1), "PENDING")
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                tck_ids.append(tck.criar({"script_id": script_id, "environment": ambiente, "requested_by": login,
                                          "schedule_id": r1["id"], "scheduled_at": ocorrencia}, []))
            self.assertEqual(ctx.exception.constraint, tck.nome_constraint("ix", "tickets", "occur"))
        finally:
            self._limpar(agd_ids, tck_ids, marca)


class TestOracleAuditoriaAgentes(unittest.TestCase):
    """Testes de conformidade e integridade para o agregado AUDITORIA_AGENTES no Oracle (passo 5 do F7.3)."""

    @classmethod
    def setUpClass(cls):
        agregado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if agregado != "AUDITORIA_AGENTES":
            raise unittest.SkipTest("Execucao restrita ao agregado AUDITORIA_AGENTES (atual: %s)" % agregado)
        _preparar_banco_real(cls)

    @classmethod
    def tearDownClass(cls):
        _restaurar_banco_real(cls)

    def setUp(self):
        repo_factory.reset_singletons()
        self.aud = repo_factory.obter("auditoria")
        self.agt = repo_factory.obter("agentes")

    # ------------------------------------------------------------- sem banco

    def test_todos_os_agregados_no_oracle(self):
        """Com o 5o agregado, a aplicacao resolve todos os repositorios para o Oracle (sem FAKE)."""
        esperados = {"usuarios": "RepoUsuariosOracle", "rbac": "RepoRbacOracle", "catalogo": "RepoCatalogoOracle",
                     "tickets": "RepoTicketsOracle", "agendamentos": "RepoAgendamentosOracle",
                     "auditoria": "RepoAuditoriaOracle", "agentes": "RepoAgentesOracle"}
        for nome, classe in esperados.items():
            self.assertEqual(repo_factory.obter(nome).__class__.__name__, classe, nome)
        with self.assertRaises(ValueError):
            repo_factory.obter("inexistente")

    def test_owner_e_prefixo_parametrizados(self):
        cfg = mock.Mock()
        cfg.oracle.owner = "SSS_TEST_AUD"
        cfg.oracle.table_prefix = "abc_"
        aud = RepoAuditoriaOracle(cfg=cfg, segredos={})
        agt = RepoAgentesOracle(cfg=cfg, segredos={})
        for nome, sql in list(aud._sql.items()) + list(agt._sql.items()):
            self.assertNotIn("tbsss_", sql, nome)
        self.assertIn("SSS_TEST_AUD.abc_audit", aud._sql["INSERIR"])
        self.assertEqual(aud._seq_aud, "SSS_TEST_AUD.sq_abc_audit")
        self.assertIn("SSS_TEST_AUD.abc_scripts", agt._sql["FILA"])

    def test_painel_usa_as_expressoes_dos_indices_e_nenhum_clob(self):
        """AGENTS §4.8: CASE textualmente identico ao de ix_tck_run/ix_tck_fila; sem CLOB (CR-008, R-15)."""
        import sql_ident
        self.assertIn("(" + sql_ident.FBI_TCK_RUN_AGENTE_CASE + ") = :code", self.agt._sql["TICKETS_RUNNING"])
        self.assertIn("(" + sql_ident.FBI_TCK_RUN_AGENTE_CASE + ") >= CHR(1)", self.agt._sql["RODANDO_SEM_PID"])
        # CR-013: so ix_tck_fila (status lider e o inicio da espera), agrupado por script antes do JOIN.
        self.assertIn("WHERE status = 'PENDING' AND " + sql_ident.FBI_TCK_FILA_INICIO + " <= :agora", self.agt._sql["FILA"])
        self.assertIn("JOIN " + self.agt._idents["scr"] + " s ON s.id = g.script_id", self.agt._sql["FILA"])
        for nome in ("TICKETS_RUNNING", "FILA", "RODANDO_SEM_PID"):
            self.assertNotIn("log_output", self.agt._sql[nome])
            self.assertNotIn("submitted_params", self.agt._sql[nome])

    def test_registrar_sem_corte_e_ator_obrigatorio_antes_do_sql(self):
        """test_06b: ator nulo, vazio ou longo e detalhe longo viram RepoViolacao sem abrir conexao."""
        with mock.patch.object(self.aud, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            for ator, detalhe in ((None, None), ("", None), ("x" * 41, None), ("ana", "d" * 1001)):
                with self.assertRaises(repo_errors.RepoViolacao):
                    self.aud.registrar(ator, "1.2.3.4", "UPDATE", "tbsss_scripts", 1, detalhe)

    def test_gravacao_de_auditoria_dos_outros_agregados_sem_corte(self):
        """base.gravar_auditoria recusa (nao corta) detalhe longo: a transacao toda e desfeita."""
        from repo_oracle import base
        with self.assertRaises(repo_errors.RepoViolacao):
            base.gravar_auditoria(mock.MagicMock(), "t", "s", {"actor": "ana", "action": "X", "detail": "d" * 1001},
                                  "tbsss_scripts", 1)
        with self.assertRaises(repo_errors.RepoViolacao):
            base.gravar_auditoria(mock.MagicMock(), "t", "s", {"actor": None, "action": "X"}, "tbsss_scripts", 1)

    def test_listar_e_iterar_por_bind_com_periodo_e_id_max(self):
        conn = _ConexaoRoteirizada([("SELECT COUNT(*)", 1, [(0,)])])
        filtros = {"actor": "Ana_1", "start_date": datetime.datetime(2026, 1, 1),
                   "end_date": datetime.datetime(2026, 1, 31, 23, 59, 59), "id_max": 99, "source_ip": "10.%"}
        with mock.patch.object(self.aud, "_obter_conexao", return_value=conn):
            self.aud.listar(filtros)
            list(self.aud.iterar(filtros, limite=5))
        sql, binds = conn.executados[0]
        for trecho in ("LOWER(actor) LIKE :ator_f ESCAPE", "created_at >= :start_date", "created_at <= :end_date",
                       "id <= :id_max", "ROWNUM <= 10001"):
            self.assertIn(trecho, sql)
        self.assertNotIn("TRUNC", sql)
        self.assertEqual((binds["ator_f"], binds["ip_f"]), ("%ana\\_1%", "%10.\\%%"))
        sql_it, binds_it = conn.executados[-1]
        self.assertIn("WHERE ROWNUM <= :limite", sql_it)
        self.assertEqual(binds_it["limite"], 5)

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
        tck = repo_factory.obter("tickets")
        marca = "tst%s" % datetime.datetime.now().strftime("%H%M%S%f")
        aud_ids, tck_ids, agt_id = [], [], None
        tab_agt = self.agt._idents["agt"]
        try:
            agora = tck.agora()

            # 1. Trilha: id reservado, id repetido recusado com o nome da PK, listar e iterar com filtros.
            aid = self.aud.reservar_id()
            reg = self.aud.registrar("teste_" + marca, "10.0.0.1", "SCHEMA_MIGRATE", "tbsss_control", 1,
                                     u"versão 1 conferida", id=aid)
            aud_ids.append(aid)
            self.assertEqual((reg["id"], reg["actor"], reg["detail"]), (aid, "teste_" + marca, u"versão 1 conferida"))
            self.assertEqual(reg["created_at"].microsecond, 0)
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.aud.registrar("teste_" + marca, None, "UPDATE", "tbsss_control", 1, None, id=aid)
            self.assertEqual(ctx.exception.constraint, "pk_" + self.aud._prefixo + sql_ident.fisico("auditoria"))
            for _ in range(2):
                aud_ids.append(self.aud.registrar("teste_" + marca, None, "UPDATE", "tbsss_control", 1)["id"])
            filtros = {"actor": "TESTE_" + marca.upper(), "start_date": agora - datetime.timedelta(minutes=5),
                       "end_date": agora + datetime.timedelta(minutes=5)}
            lista = self.aud.listar(filtros)
            self.assertEqual([i["id"] for i in lista["itens"]], sorted(aud_ids, reverse=True))
            self.assertEqual(self.aud.listar(dict(filtros, id_max=aid))["total"], 1)
            self.assertEqual(self.aud.listar(dict(filtros, action="SCHEMA_MIGRATE", entity="tbsss_control",
                                                  entity_id=1))["total"], 1)
            self.assertEqual([r["id"] for r in self.aud.iterar(filtros, limite=2)], sorted(aud_ids, reverse=True)[:2])

            # 2. Painel: agente ATIVO com heartbeat agora atende (ambiente, interpretador) do proprio teste.
            script = repo_factory.obter("catalogo").scripts_listar(tamanho=1)["itens"][0]
            ambiente = repo_factory.obter("catalogo").ambientes_listar(tamanho=1)["itens"][0]["name"]
            login = repo_factory.obter("usuarios").listar(tamanho=1)["itens"][0]["login"]
            c = self.aud._obter_conexao()
            try:
                agt_id = db_conn.proximo_id(c, self.agt.qualificar_sequence("agentes"))
            finally:
                c.close()
            self._executar([(
                "INSERT INTO " + tab_agt + " (id, code, hostname, status, environments, platform, interpreters, "
                "heartbeat_at, critical_config, created_at, created_by) VALUES (:id, :code, 'host-tst', 'ACTIVE', "
                ":amb, 'LINUX', :interp, :hb, 'tst=1', SYSDATE, 'SYSTEM:teste')",
                {"id": agt_id, "code": marca, "amb": ambiente, "interp": script["interpreter"], "hb": agora})])
            ag = [a for a in self.agt.listar() if a["code"] == marca][0]
            self.assertEqual((ag["platform"], ag["interpreters"], ag["critical_config"]),
                             ("LINUX", script["interpreter"], "tst=1"))

            antigo = agora - datetime.timedelta(minutes=30)
            base = {"script_id": script["id"], "environment": ambiente, "requested_by": login, "source_ip": marca}
            t_run = tck.criar(dict(base, status="RUNNING", agent_id=marca, started_at=antigo), [])
            tck_ids.append(t_run)
            t_pend = tck.criar(dict(base, scheduled_at=antigo), [])
            tck_ids.append(t_pend)

            rodando = self.agt.tickets_running(marca)
            self.assertEqual([t["id"] for t in rodando], [t_run])
            self.assertNotIn("log_output", rodando[0])
            self.assertNotIn("submitted_params", rodando[0])
            sem_pid = [t for t in self.agt.rodando_sem_pid(agora, 2) if t["id"] == t_run]
            self.assertEqual(sorted(sem_pid[0]), ["agent_id", "environment", "id", "script_id", "started_at"])
            # Reservado ha 30 minutos: fica de fora com o limite de 60.
            self.assertNotIn(t_run, [t["id"] for t in self.agt.rodando_sem_pid(agora, 60)])

            limiares = mock.Mock(heartbeat_interval_s=30, fence_timeout_s=120)
            chave = (ambiente, script["interpreter"])
            self.assertNotIn(chave, [(g["environment"], g["interpreter"]) for g in self.agt.fila_sem_atendente(agora, limiares)])
            # Agente parado: o mesmo par passa a aparecer na fila sem atendente, com o PENDING do teste.
            self._executar([("UPDATE " + tab_agt + " SET status = 'STOPPED', updated_at = SYSDATE, "
                             "updated_by = 'SYSTEM:teste' WHERE id = :id", {"id": agt_id})])
            grupos = dict(((g["environment"], g["interpreter"]), g) for g in self.agt.fila_sem_atendente(agora, limiares))
            self.assertIn(chave, grupos)
            self.assertGreaterEqual(grupos[chave]["quantidade"], 1)
            self.assertLessEqual(grupos[chave]["mais_antigo"], antigo.replace(microsecond=0))
        finally:
            limpeza = [("DELETE FROM " + self.aud._idents["aud"] + " WHERE id = :id", {"id": i}) for i in aud_ids]
            for tid in tck_ids:
                limpeza.append(("DELETE FROM " + tck._idents["tck"] + " WHERE id = :id", {"id": tid}))
                if _oracle_test_support.modo_schema() == _oracle_test_support.MODO_COMPARTILHADO:
                    limpeza.append(("DELETE FROM " + self.aud._idents["aud"] + " WHERE entity = 'tbsss_tickets' "
                                    "AND entity_id = :id", {"id": tid}))
            if agt_id is not None:
                limpeza.append(("DELETE FROM " + tab_agt + " WHERE id = :id", {"id": agt_id}))
            self._executar(limpeza)


if __name__ == "__main__":
    unittest.main()
