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

    def test_agregados_seguintes_ainda_nao_implementados(self):
        """Garante que tickets, agendamentos e auditoria continuam bloqueados (catalogo: agregado 2)."""
        for agg in ("tickets", "agendamentos", "auditoria", "agentes"):
            with self.assertRaises(NotImplementedError) as ctx:
                repo_factory.obter(agg)
            self.assertIn("Backend ORACLE ainda nao implementado", str(ctx.exception))

    def test_ator_obrigatorio_usuarios_e_perfis(self):
        """Valida que insercao e alteracao sem ator ou com ator longo lancam RepoViolacao."""
        for ator_invalido in (None, "", "   ", "x" * 41):
            with self.assertRaises(repo_errors.RepoViolacao):
                self.usr.inserir({"login": "novo.user", "perfil_id": 1}, ator=ator_invalido)
            with self.assertRaises(repo_errors.RepoViolacao):
                self.rbac.perfis_inserir({"nome": "Novo Perfil"}, ator=ator_invalido)
            with self.assertRaises(repo_errors.RepoViolacao):
                self.usr.desbloquear(1, ator=ator_invalido)

    def test_login_invalido_recusado(self):
        """Valida regex de login em tbsss_usuarios."""
        for log_inv in ("ab", "AB_USER", "user com espaco", "u" * 31, "usr@dominio"):
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.usr.inserir({"login": log_inv, "perfil_id": 1}, ator="admin")
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
            "nome": nome_perfil,
            "descricao": "Perfil temporario de teste progressivo",
            "is_admin": "N",
            "ativo": "S",
        }, ator=ator_teste)
        self.assertIsNotNone(per.get("id"))
        pid = per["id"]

        try:
            # 2. Cria usuario associado
            login = ("u_%s" % prefixo)[:30].lower()
            usr = self.usr.inserir({
                "login": login,
                "nome": "Usuario de Teste",
                "senha_hash": "hash_fake_123",
                "perfil_id": pid,
                "ativo": "S",
            }, ator=ator_teste)
            self.assertIsNotNone(usr.get("id"))
            uid = usr["id"]

            # 3. Teste do relogio do banco sem microssegundos
            dt_banco = self.usr.agora()
            self.assertEqual(dt_banco.microsecond, 0)

            # 4. Estado da sessao
            sess = self.usr.obter_estado_sessao(uid)
            self.assertEqual(sess["login"], login)
            self.assertEqual(sess["perfil_id"], pid)
            self.assertEqual(sess["sessao_epoch"], 0)

            # 5. Logout incrementa sessao_epoch
            self.usr.encerrar_sessoes(uid, auditoria={"ator": ator_teste, "acao": "LOGOUT"})
            sess2 = self.usr.obter_estado_sessao(uid)
            self.assertEqual(sess2["sessao_epoch"], 1)

            # 6. Falha e sucesso de login
            self.usr.registrar_falha_login(login, bloqueio_s=300)
            u_falha = self.usr.obter_por_id(uid)
            self.assertEqual(u_falha["tentativas_falha"], 1)
            self.assertIsNotNone(u_falha["bloqueado_ate"])

            self.usr.registrar_sucesso_login(login, novo_hash="hash_rehash_456")
            u_ok = self.usr.obter_por_id(uid)
            self.assertEqual(u_ok["tentativas_falha"], 0)
            self.assertIsNone(u_ok["bloqueado_ate"])
            self.assertEqual(u_ok["senha_hash"], "hash_rehash_456")

            # 7. Imutabilidade do login
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.usr.alterar(uid, {"login": "outro_login"}, ator=ator_teste)
            self.assertEqual(ctx.exception.constraint, "tr_tbsss_usr_bu")

            # 8. Unicidade de UKs
            with self.assertRaises(repo_errors.RepoViolacao):
                self.usr.inserir({"login": login, "perfil_id": pid}, ator=ator_teste)
            with self.assertRaises(repo_errors.RepoViolacao):
                self.rbac.perfis_inserir({"nome": nome_perfil}, ator=ator_teste)

        finally:
            # Limpeza cirurgica no schema descartavel
            conn = self.usr._obter_conexao()
            try:
                cur = conn.cursor()
                try:
                    cur.execute("DELETE FROM " + self.usr._tabela() + " WHERE id = :id", {"id": uid})
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

    def test_agregados_seguintes_ainda_nao_implementados(self):
        """Tickets, agendamentos, auditoria e agentes continuam indisponiveis no ORACLE."""
        for agg in ("tickets", "agendamentos", "auditoria", "agentes"):
            with self.assertRaises(NotImplementedError) as ctx:
                repo_factory.obter(agg)
            self.assertIn("Backend ORACLE ainda nao implementado", str(ctx.exception))

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
        self.assertIn("SSS_TEST_CAT.abc_perfil_scr", repo._sql["EXEC_PERFIL"])
        self.assertEqual(repo._seq["script_param"], "SSS_TEST_CAT.sq_abc_script_param")
        with mock.patch.object(repo, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                repo.scripts_inserir({"nome": "s", "interpretador": "SH", "path_file": "x.sh"}, ator="t")
        self.assertEqual(ctx.exception.constraint, "ck_abc_scr_path")

    def test_ator_obrigatorio_antes_de_qualquer_sql(self):
        """Sem ator (ou com mais de 40 caracteres), RepoViolacao sem abrir conexao."""
        with mock.patch.object(self.cat, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            for ator_invalido in (None, "", "   ", "x" * 41):
                for chamada in (
                    lambda a: self.cat.ambientes_inserir({"nome": "AMB_X"}, ator=a),
                    lambda a: self.cat.ambientes_alterar(1, {"descricao": "x"}, ator=a),
                    lambda a: self.cat.scripts_inserir({"nome": "s", "interpretador": "SH",
                                                        "path_file": "/opt/s.sh"}, ator=a),
                    lambda a: self.cat.scripts_alterar(1, {"descricao": "x"}, ator=a),
                    lambda a: self.cat.homologacao_salvar(1, [1], ator=a),
                    lambda a: self.cat.parametros_inserir({"codigo": "p", "tipo_componente": "TEXT"}, ator=a),
                    lambda a: self.cat.parametros_alterar(1, {"label": "x"}, ator=a),
                    lambda a: self.cat.script_params_salvar(1, [], ator=a),
                ):
                    with self.assertRaises(repo_errors.RepoViolacao):
                        chamada(ator_invalido)

    def test_cks_recusadas_antes_do_banco_com_nome_do_fake(self):
        """CKs de nome, caminho, interpretador, sha e codigo devolvem o nome da constraint do FAKE."""
        n = self.cat.nome_constraint
        with mock.patch.object(self.cat, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            casos = (
                (lambda: self.cat.ambientes_inserir({"nome": "minusculo"}, ator="t"), n("ck", "ambientes", "nome")),
                (lambda: self.cat.scripts_inserir({"nome": "s", "interpretador": "SH",
                                                   "path_file": "relativo.sh"}, ator="t"), n("ck", "scripts", "path")),
                (lambda: self.cat.scripts_inserir({"nome": "s", "interpretador": "SH",
                                                   "path_file": "/opt/../x.sh"}, ator="t"), n("ck", "scripts", "path")),
                (lambda: self.cat.scripts_inserir({"nome": "s", "interpretador": "SH",
                                                   "path_file": "/" + "a" * 500}, ator="t"), n("ck", "scripts", "path")),
                (lambda: self.cat.scripts_inserir({"nome": "s", "interpretador": "PERL",
                                                   "path_file": "/opt/s.pl"}, ator="t"), n("ck", "scripts", "int")),
                (lambda: self.cat.scripts_inserir({"nome": "s", "interpretador": "SH", "path_file": "/opt/s.sh",
                                                   "sha256_homologado": "ABC"}, ator="t"), n("ck", "scripts", "sha")),
                (lambda: self.cat.scripts_inserir({"nome": "s", "interpretador": "SH", "path_file": "/opt/s.sh",
                                                   "max_qtd_parallel_env": 0}, ator="t"), n("ck", "scripts", "paral")),
                (lambda: self.cat.parametros_inserir({"codigo": "Maiusc", "tipo_componente": "TEXT"},
                                                     ator="t"), n("ck", "parametros", "codigo")),
            )
            for chamada, ck in casos:
                with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                    chamada()
                self.assertEqual(ctx.exception.constraint, ck)

    def test_scripts_executaveis_sem_exec_script_nao_consulta(self):
        """Nao admin sem EXEC_SCRIPT (ou sem perfil) recebe lista vazia sem ir ao banco."""
        with mock.patch.object(self.cat, "_obter_conexao", side_effect=AssertionError("abriu conexao")):
            self.assertEqual(self.cat.scripts_executaveis({"is_admin": False, "perfil_id": 3,
                                                           "funcionalidades": frozenset()}), [])
            self.assertEqual(self.cat.scripts_executaveis({"is_admin": False,
                                                           "funcionalidades": frozenset(["EXEC_SCRIPT"])}), [])

    def test_scripts_executaveis_uma_consulta_por_perfil_ou_admin(self):
        """Uma unica consulta: EXISTS em perfil_scr/perfil_amb pelo perfil_id, ou o atalho do admin."""
        cur = _CursorGravador()
        with mock.patch.object(self.cat, "_obter_conexao", return_value=_ConexaoGravadora(cur)):
            self.cat.scripts_executaveis({"is_admin": False, "perfil_id": 7,
                                          "funcionalidades": frozenset(["EXEC_SCRIPT"])})
            self.cat.scripts_executaveis({"is_admin": True})
        self.assertEqual(len(cur.executados), 2)
        sql_perfil, binds_perfil = cur.executados[0]
        self.assertIn(self.cat.qualificar_tabela("perfil_scr"), sql_perfil)
        self.assertIn(self.cat.qualificar_tabela("perfil_amb"), sql_perfil)
        self.assertEqual(binds_perfil, {"perfil_id": 7})
        sql_admin, binds_admin = cur.executados[1]
        self.assertNotIn(self.cat.qualificar_tabela("perfil_scr"), sql_admin)
        self.assertIn(self.cat.qualificar_tabela("script_amb"), sql_admin)
        self.assertIsNone(binds_admin)

    def test_filtro_de_trecho_escapa_curingas(self):
        """'%' e '_' digitados no filtro sao literais (paridade com o 'in' do FAKE), sempre por bind."""
        cur = _CursorGravador(uma=(0,))
        with mock.patch.object(self.cat, "_obter_conexao", return_value=_ConexaoGravadora(cur)):
            self.cat.scripts_listar(filtros={"nome": "carga_10%"})
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
            amb = self.cat.ambientes_inserir({"nome": "TST_" + sufixo, "descricao": "a"}, ator=ator)
            ids["ambientes"].append(amb["id"])
            self.assertEqual(amb["created_by"], ator)
            self.assertIsNone(amb["updated_at"])
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.ambientes_inserir({"nome": "TST_" + sufixo}, ator=ator)
            self.assertEqual(ctx.exception.constraint, n("uk", "ambientes", "nome"))
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.ambientes_alterar(amb["id"], {"nome": "OUTRO_" + sufixo}, ator=ator)
            self.assertEqual(ctx.exception.constraint, self.cat.nome_trigger("ambientes", "bu"))
            with self.assertRaises(repo_errors.RepoConflito):
                self.cat.ambientes_alterar(amb["id"], {"descricao": "b"}, esperado={"descricao": "z"}, ator=ator)
            alt = self.cat.ambientes_alterar(amb["id"], {"descricao": "b"}, esperado={"descricao": "a"}, ator="bia")
            self.assertEqual((alt["descricao"], alt["updated_by"], alt["created_by"]), ("b", "bia", ator))
            self.assertEqual(alt["created_at"].microsecond, 0)

            # 2. Scripts: UK sensivel a maiusculas, path_file absoluto e esperado nulo-seguro.
            nome_scr = "Tst_Scr_" + sufixo
            scr = self.cat.scripts_inserir({"nome": nome_scr, "interpretador": "SH", "tipo_param": "NOMEADO",
                                            "path_file": "/opt/sss_teste/" + sufixo + ".sh"}, ator=ator)
            ids["scripts"].append(scr["id"])
            outro = self.cat.scripts_inserir({"nome": nome_scr.lower(), "interpretador": "SH",
                                              "path_file": "/opt/sss_teste/b.sh"}, ator=ator)
            ids["scripts"].append(outro["id"])
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.scripts_inserir({"nome": nome_scr, "interpretador": "SH",
                                          "path_file": "/opt/sss_teste/c.sh"}, ator=ator)
            self.assertEqual(ctx.exception.constraint, n("uk", "scripts", "nome"))
            alt = self.cat.scripts_alterar(scr["id"], {"grupo": "G1"}, esperado={"grupo": None,
                                                                                  "path_file": scr["path_file"]},
                                           ator=ator)
            self.assertEqual(alt["grupo"], "G1")
            self.assertEqual(alt["updated_by"], ator)

            # 3. Homologacao por diferenca: vinculo que continua mantem o created_*.
            self.assertEqual(self.cat.homologacao_salvar(scr["id"], [amb["id"]], esperado=[], ator=ator),
                             [amb["id"]])
            with self.assertRaises(repo_errors.RepoConflito):
                self.cat.homologacao_salvar(scr["id"], [], esperado=[], ator=ator)
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.homologacao_salvar(scr["id"], [amb["id"], 999999999], ator=ator)
            self.assertEqual(ctx.exception.constraint, n("fk", "script_amb", "amb"))

            # 4. Parametros e vinculos: NOMEADO exige flag; created_* preservado; dependencias.
            sem_flag = self.cat.parametros_inserir({"codigo": "tst_sf_" + sufixo, "label": "X",
                                                    "tipo_componente": "TEXT"}, ator=ator)
            ids["parametros"].append(sem_flag["id"])
            com_flag = self.cat.parametros_inserir({"codigo": "tst_cf_" + sufixo, "label": "Y",
                                                    "tipo_componente": "TEXT", "param_nomeado": "--y"}, ator=ator)
            ids["parametros"].append(com_flag["id"])
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.script_params_salvar(scr["id"], [{"parametro_id": sem_flag["id"], "ordem": 1}], ator=ator)
            self.assertEqual(ctx.exception.constraint, "sss_scr_nomeado_sem_flag")
            v1 = self.cat.script_params_salvar(scr["id"], [{"parametro_id": com_flag["id"], "ordem": 1,
                                                            "obrigatorio": "S"}], esperado=[], ator=ator)
            self.assertEqual([v["parametro_id"] for v in v1], [com_flag["id"]])
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.parametros_alterar(com_flag["id"], {"tipo_componente": "NUMBER"}, ator=ator)
            self.assertEqual(ctx.exception.constraint, "sss_prm_tipo_vinculado")
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.parametros_alterar(com_flag["id"], {"ativo": "N"}, ator=ator)
            self.assertEqual(ctx.exception.constraint, "sss_prm_vinculo_ativo")
            with self.assertRaises(repo_errors.RepoViolacao) as ctx:
                self.cat.scripts_alterar(scr["id"], {"tipo_param": "NENHUM"}, ator=ator)
            self.assertEqual(ctx.exception.constraint, "sss_scr_nenhum_vinculado")
            self.assertEqual(self.cat.scripts_obter(scr["id"])["tipo_param"], "NOMEADO")

            conn = self.cat._obter_conexao()
            try:
                cur = conn.cursor()
                try:
                    sql = ("SELECT created_at, created_by FROM " + self.cat.qualificar_tabela("script_param")
                           + " WHERE script_id = :s AND parametro_id = :p")
                    cur.execute(sql, {"s": scr["id"], "p": com_flag["id"]})
                    criado_antes = cur.fetchone()
                finally:
                    cur.close()
            finally:
                conn.close()
            self.cat.script_params_salvar(scr["id"], [{"parametro_id": com_flag["id"], "ordem": 1,
                                                       "obrigatorio": "S"}],
                                          esperado=[(com_flag["id"], 1, "S", None)], ator="outro")
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
            lista = self.cat.scripts_listar(filtros={"nome": nome_scr})
            self.assertIn("total_limitado", lista)
            item = [i for i in lista["itens"] if i["id"] == scr["id"]][0]
            self.assertEqual(item["ambientes_homologados"], [amb["nome"]])
            self.assertEqual(item["qtd_parametros"], 1)
            prm = self.cat.parametros_listar(filtros={"codigo": "tst_cf_" + sufixo})["itens"][0]
            self.assertEqual(prm["qtd_scripts"], len(self.cat.parametro_vinculos(com_flag["id"])))

            # 6. Executaveis do admin: script ativo homologado em ambiente ativo.
            executaveis = [s["id"] for s in self.cat.scripts_executaveis({"is_admin": True})]
            self.assertIn(scr["id"], executaveis)
            self.assertNotIn(outro["id"], executaveis)
        finally:
            self._limpar(ids)


class TestOracleTickets(unittest.TestCase):
    """Testes para o agregado TICKETS no Oracle (passo 3 do F7.3)."""

    def test_pendente(self):
        agregado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if agregado != "TICKETS":
            self.skipTest("Agregado TICKETS sera implementado no passo 3 do F7.3")


class TestOracleAgendamentos(unittest.TestCase):
    """Testes para o agregado AGENDAMENTOS no Oracle (passo 4 do F7.3)."""

    def test_pendente(self):
        agregado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if agregado != "AGENDAMENTOS":
            self.skipTest("Agregado AGENDAMENTOS sera implementado no passo 4 do F7.3")


class TestOracleAuditoriaAgentes(unittest.TestCase):
    """Testes para o agregado AUDITORIA_AGENTES no Oracle (passo 5 do F7.3)."""

    def test_pendente(self):
        agregado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if agregado != "AUDITORIA_AGENTES":
            self.skipTest("Agregado AUDITORIA_AGENTES sera implementado no passo 5 do F7.3")


if __name__ == "__main__":
    unittest.main()
