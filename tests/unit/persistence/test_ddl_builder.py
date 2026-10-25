# -*- coding: utf-8 -*-
"""Testes unitarios para ddl_builder.py, sql_ident.normalize_expression e scripts/init_db.py (F7.1).

Cobre a geracao de DDL Oracle 11gR2 fase a fase, triggers, restricoes de seguranca,
normalizacao de expressoes SQL contra textos reais do 11gR2, GRANTs por papel e CLI.
"""
import io
import os
import re
import tempfile
import unittest
from unittest import mock

from tests.support import _testenv  # noqa: F401
from sss.persistence import ddl_builder
from sss.cli import init_db
from sss.core import sql_ident


class TestDdlBuilder(unittest.TestCase):
    """Testes da geracao declarativa de DDL a partir de sql_ident."""

    def setUp(self):
        self.owner = "openrisow"
        self.prefixo = "tbsss_"
        self.statements = ddl_builder.build_ddl_statements(self.owner, self.prefixo)

    def test_ddl_contem_todos_os_nomes_do_registro(self):
        """O DDL gerado contem todos os nomes de objetos registrados em sql_ident."""
        names_expected = sql_ident.all_identifiers(self.prefixo, include_columns=False)
        names_generated = set(item.name for item in self.statements)

        for name in names_expected:
            self.assertIn(
                name, names_generated,
                "Objeto '%s' registrado em sql_ident nao foi gerado no DDL" % name
            )

    def test_proibicoes_sql_12c_e_tipos_estritos(self):
        """Garante ausencia de sintaxe 12c+ e presenca de VARCHAR2(n CHAR)."""
        forbidden = [
            re.compile(r"\bIDENTITY\b", re.IGNORECASE),
            re.compile(r"\bFETCH\s+FIRST\b", re.IGNORECASE),
            re.compile(r"\bOFFSET\b", re.IGNORECASE),
            re.compile(r"\bJSON_\w+", re.IGNORECASE),
            re.compile(r"\bIS\s+JSON\b", re.IGNORECASE),
            re.compile(r"VARCHAR2\(\d+\)(?! CHAR)", re.IGNORECASE),
        ]

        for item in self.statements:
            sql = item.sql
            for default in forbidden:
                self.assertIsNone(
                    default.search(sql),
                    "Padrao proibido '%s' encontrado no DDL de %s %s:\n%s"
                    % (default.pattern, item.kind, item.name, sql)
                )

    def test_rollback_cobre_todas_as_tabelas_do_registro(self):
        """Toda tabela do registro sai no 02_rollback (a lista e fixa, na ordem de dependencia; CR-020b)."""
        self.assertEqual(sorted(ddl_builder.ROLLBACK_ENTITY_ORDER), sorted(sql_ident.TABLES))
        self.assertEqual(len(set(ddl_builder.ROLLBACK_ENTITY_ORDER)), len(ddl_builder.ROLLBACK_ENTITY_ORDER))

    def test_triggers_bi_e_bu_literais(self):
        """Valida que toda trigger _bi segue o template do AGENTS §4.2 e _bu aplica imutabilidade."""
        triggers = [item for item in self.statements if item.kind == "TRIGGER"]
        self.assertEqual(len(triggers), 23, "Devem existir 21 triggers _bi e 2 _bu")

        bi_triggers = [t for t in triggers if t.name.endswith("_bi")]
        self.assertEqual(len(bi_triggers), 21)

        template_expected = (
            "BEGIN\n"
            "    IF :NEW.id IS NULL THEN\n"
            "        SELECT {owner}.{sequence_name}.NEXTVAL INTO :NEW.id FROM DUAL;\n"
            "    END IF;\n"
            "END;"
        )

        schema = sql_ident.names(self.prefixo)
        for t in bi_triggers:
            entity = t.entity
            seq = schema[entity]["sequence"]
            expected = template_expected.format(owner=self.owner, sequence_name=seq)
            self.assertIn(expected, t.sql)

        # Triggers _bu (ambientes e usuarios)
        bu_triggers = {t.name: t for t in triggers if t.name.endswith("_bu")}
        self.assertEqual(len(bu_triggers), 2)

        tr_env_bu = bu_triggers["tr_tbsss_env_bu"]
        self.assertIn(":NEW.name <> :OLD.name", tr_env_bu.sql)
        self.assertIn("RAISE_APPLICATION_ERROR(-20001, 'name é imutável')", tr_env_bu.sql)

        tr_usr_bu = bu_triggers["tr_tbsss_usr_bu"]
        self.assertIn(":NEW.login <> :OLD.login", tr_usr_bu.sql)
        self.assertIn("RAISE_APPLICATION_ERROR(-20001, 'login é imutável')", tr_usr_bu.sql)

    def test_ordem_estrita_das_fases(self):
        """As fases 1 a 6 respeitam a ordem estrita do README §11.1."""
        phases = [item.phase for item in self.statements]
        # Garante que a lista de fases e nao-decrescente
        for i in range(len(phases) - 1):
            self.assertLessEqual(phases[i], phases[i + 1])

        # Verifica tipo esperado por fase
        kinds_by_phase = {
            1: {"SEQUENCE"},
            2: {"TABLE"},
            3: {"CONSTRAINT"},
            4: {"CONSTRAINT"},
            5: {"INDEX"},
            6: {"TRIGGER"},
        }
        for item in self.statements:
            expected = kinds_by_phase[item.phase]
            self.assertIn(item.kind, expected)

    def test_cr005_path_file_e_cks(self):
        """Valida path_file VARCHAR2(500 CHAR) NOT NULL e CKs do CR-005."""
        tables = {item.name: item.sql for item in self.statements if item.kind == "TABLE"}
        self.assertIn("path_file VARCHAR2(500 CHAR) NOT NULL", tables["tbsss_scripts"])
        self.assertNotIn("pasta_base", tables["tbsss_scripts"])
        self.assertNotIn("pastas_base", tables["tbsss_agents"])

        constraints = {item.name: item.sql for item in self.statements if item.kind == "CONSTRAINT"}
        ck_path = constraints["ck_tbsss_scr_path"]
        self.assertIn("SUBSTR(path_file, 1, 1) = '/'", ck_path)
        self.assertIn("INSTR(path_file, '..') = 0", ck_path)
        self.assertIn("INSTR(path_file, '//') = 0", ck_path)
        self.assertIn("INSTR(path_file, '\\') = 0", ck_path)

        ck_plat = constraints["ck_tbsss_agt_plat"]
        self.assertIn("platform IS NULL OR platform IN ('LINUX','UNIX')", ck_plat)

    def test_cr006_colunas_registro_e_ck_upd(self):
        """Valida que as 15 tabelas (menos auditoria e controle) tem colunas de registro e ck_upd."""
        tables = {item.name: item.sql for item in self.statements if item.kind == "TABLE"}
        constraints = {item.name: item.sql for item in self.statements if item.kind == "CONSTRAINT"}

        schema = sql_ident.names(self.prefixo)
        for ent, t in schema.items():
            t_name = t["tabela"]
            abbr = t["abrev"]
            sql_t = tables[t_name]

            if ent in ("audit", "control"):
                self.assertNotIn("created_by", sql_t)
                self.assertNotIn("updated_at", sql_t)
                self.assertNotIn("updated_by", sql_t)
                self.assertNotIn("ck_{}{}_upd".format(self.prefixo, abbr), constraints)
            else:
                self.assertIn("created_at DATE DEFAULT SYSDATE NOT NULL", sql_t)
                self.assertIn("created_by VARCHAR2(40 CHAR) NOT NULL", sql_t)
                self.assertNotIn("created_by VARCHAR2(40 CHAR) DEFAULT", sql_t)
                self.assertIn("updated_at DATE", sql_t)
                self.assertIn("updated_by VARCHAR2(40 CHAR)", sql_t)

                ck_upd_name = "ck_{}{}_upd".format(self.prefixo, abbr)
                self.assertIn(ck_upd_name, constraints)
                self.assertIn("(updated_at IS NULL AND updated_by IS NULL)", constraints[ck_upd_name])

    def test_cr007_controle_fbi_unico_sha_e_lobs(self):
        """Valida objetos adicionados pelo CR-007 e suporte a SECUREFILE e BASICFILE."""
        constraints = {item.name: item.sql for item in self.statements if item.kind == "CONSTRAINT"}
        indexes = {item.name: item.sql for item in self.statements if item.kind == "INDEX"}
        tables = {item.name: item.sql for item in self.statements if item.kind == "TABLE"}

        # tbsss_control
        self.assertIn("ck_tbsss_ctl_id", constraints)
        self.assertIn("id = 1", constraints["ck_tbsss_ctl_id"])
        self.assertIn("schema_version >= 1", constraints["ck_tbsss_ctl_version"])

        # FBI unico ix_tbsss_tck_occur
        self.assertIn("ix_tbsss_tck_occur", indexes)
        self.assertTrue(indexes["ix_tbsss_tck_occur"].startswith("CREATE UNIQUE INDEX"))
        self.assertIn("schedule_id IS NOT NULL", indexes["ix_tbsss_tck_occur"])

        # CR-011: sem CKs de hash
        self.assertNotIn("ck_tbsss_scr_sha", constraints)
        self.assertNotIn("ck_tbsss_tck_sha", constraints)

        # LOB Securefile (padrao)
        self.assertIn("LOB (params_json) STORE AS SECUREFILE (CACHE)", tables["tbsss_schedules"])
        self.assertIn("LOB (submitted_params, log_output) STORE AS SECUREFILE (CACHE)", tables["tbsss_tickets"])

        # Fallback Basicfile
        ddl_basic = ddl_builder.build_ddl_statements(self.owner, self.prefixo, lob_storage="BASICFILE")
        tables_basic = {item.name: item.sql for item in ddl_basic if item.kind == "TABLE"}
        self.assertIn("LOB (params_json) STORE AS BASICFILE", tables_basic["tbsss_schedules"])
        self.assertIn("LOB (submitted_params, log_output) STORE AS BASICFILE", tables_basic["tbsss_tickets"])

    def test_cr008_sessao_epoch_pid_daemon_log_offset(self):
        """Valida campos adicionados e ajustados pelo CR-008."""
        tables = {item.name: item.sql for item in self.statements if item.kind == "TABLE"}
        constraints = {item.name: item.sql for item in self.statements if item.kind == "CONSTRAINT"}

        # tbsss_users.sessao_epoch e ck
        self.assertIn("session_epoch NUMBER(10) DEFAULT 0 NOT NULL", tables["tbsss_users"])
        self.assertIn("ck_tbsss_usr_epoch", constraints)
        self.assertIn("session_epoch >= 0", constraints["ck_tbsss_usr_epoch"])

        # tbsss_agents.daemon_pid
        self.assertIn("daemon_pid NUMBER(10)", tables["tbsss_agents"])

        # tbsss_tickets.log_offset_chars e ck
        self.assertIn("log_offset_chars NUMBER(20) DEFAULT 0 NOT NULL", tables["tbsss_tickets"])
        self.assertIn("ck_tbsss_tck_logoff", constraints)
        self.assertIn("log_offset_chars >= 0", constraints["ck_tbsss_tck_logoff"])


class TestGrantsByRole(unittest.TestCase):
    """Testes dos comandos GRANT gerados por papel (README §11.1)."""

    def setUp(self):
        self.roles = {
            "web": "sss_web",
            "agent": "sss_agente",
            "purge": "sss_purge",
            "monitor": "sss_monitor",
        }
        self.grants = ddl_builder.build_grants_by_role("openrisow", "tbsss_", self.roles)
        self.grants_text = "\n".join(self.grants)

    def test_auditoria_protegida_contra_update_e_delete(self):
        """Web e agente nunca tem UPDATE ou DELETE em tbsss_audit (CR-007, D1b)."""
        for g in self.grants:
            if "ON openrisow.tbsss_audit TO" in g:
                if "sss_web" in g or "sss_agente" in g:
                    self.assertNotIn("UPDATE", g)
                    self.assertNotIn("DELETE", g)
                if "sss_agente" in g:
                    self.assertTrue(g.startswith("GRANT INSERT ON"))

    def test_papel_monitor_apenas_select_7_tabelas(self):
        """Papel monitor (CR-008, E3) so tem SELECT nas 7 tabelas e zero sequences."""
        grants_monitor = [g for g in self.grants if "TO sss_monitor" in g]
        self.assertEqual(len(grants_monitor), 7, "Monitor deve ter acesso a exatamente 7 tabelas")

        for g in grants_monitor:
            self.assertTrue(g.startswith("GRANT SELECT ON"))
            self.assertNotIn("INSERT", g)
            self.assertNotIn("UPDATE", g)
            self.assertNotIn("DELETE", g)
            self.assertNotIn("sq_", g, "Monitor nao deve ter GRANT em sequences")

        tables_monitor = [
            "tbsss_agents", "tbsss_tickets", "tbsss_schedules", "tbsss_scripts",
            "tbsss_environments", "tbsss_control", "tbsss_audit"
        ]
        for t in tables_monitor:
            self.assertTrue(any(t in g for g in grants_monitor), "Faltou GRANT para %s" % t)

    def test_grants_da_saida_do_ticket(self):
        """CR-012: web so le o zip; agente le, inclui e altera (com a sequence); purge e monitor nada."""
        grants = ddl_builder.build_grants_by_role("openrisow", "tbsss_", dict(self.roles))
        of_output = [g for g in grants if "ticket_output" in g]
        self.assertEqual(sorted(of_output), sorted([
            "GRANT SELECT ON openrisow.tbsss_ticket_output TO %s;" % self.roles["web"],
            "GRANT SELECT, INSERT, UPDATE ON openrisow.tbsss_ticket_output TO %s;" % self.roles["agent"],
            "GRANT SELECT ON openrisow.sq_tbsss_ticket_output TO %s;" % self.roles["agent"],
        ]))

    def test_nunca_concede_a_public(self):
        """O script de implantacao nao concede nada a PUBLIC (tbsss_users guarda password_hash)."""
        script = ddl_builder.build_full_deploy_script("openrisow", "tbsss_", user_roles=self.roles)
        self.assertNotIn("PUBLIC", script.upper().replace("NENHUM GRANT A PUBLIC", ""))
        self.assertIn("GRANT SELECT ON openrisow.tbsss_agents TO sss_monitor;", script)
        self.assertFalse(hasattr(ddl_builder, "gerar_grants_public"))

    def test_conta_igual_ao_owner_nao_recebe_grant(self):
        """Papel que usa a conta dona do esquema vira comentario (GRANT a si mesmo e ORA-01749)."""
        grants = ddl_builder.build_grants_by_role(
            "openrisow", "tbsss_", {"web": "OPENRISOW", "agent": "openrisow", "purge": "sss_purge"})
        commands = [g for g in grants if not g.startswith("--")]
        self.assertTrue(commands)
        self.assertTrue(all(g.endswith("TO sss_purge;") for g in commands))
        self.assertIn("-- papel web: usa a conta dona do esquema (openrisow); nenhum GRANT necessario", grants)
        self.assertIn("-- papel monitor: conta nao informada; nenhum GRANT gerado", grants)

    def test_sem_contas_nenhum_grant(self):
        grants = ddl_builder.build_grants_by_role("openrisow", "tbsss_", {})
        self.assertEqual(len(grants), 4)
        self.assertTrue(all(g.startswith("-- papel ") for g in grants))

    def test_conta_ou_papel_invalidos_recusados(self):
        """A conta entra no texto do GRANT: so identificador Oracle valido; papel fora da lista e recusado."""
        for usr in ("sss_web; DROP TABLE x", "1abc", "a" * 31, "PUBLIC x", "PUBLIC", "public"):
            with self.assertRaises(ValueError):
                ddl_builder.build_grants_by_role("openrisow", "tbsss_", {"web": usr})
        with self.assertRaises(ValueError):
            ddl_builder.build_grants_by_role("openrisow", "tbsss_", {"dba": "sss_dba"})

    def test_papel_purge_concessao_controle(self):
        """Papel purge recebe SELECT e UPDATE em controle somente nas colunas de concessao."""
        grants_purge = [g for g in self.grants if "TO sss_purge" in g]
        self.assertTrue(any("UPDATE (purge_owner, purge_lease_until) ON openrisow.tbsss_control" in g for g in grants_purge))


class TestOracle11gExpressionNormalization(unittest.TestCase):
    """Testes de normalize_expression com textos reais do Oracle 11gR2 (CR-008, R-14)."""

    def test_fbi_texto_real_11g(self):
        """FBI com CASE e aspas duplas no 11gR2 bate normalizado contra o registro."""
        text_oracle = 'CASE WHEN "STATUS"=\'PENDING\' THEN "PRIORITY" END'
        normalized = sql_ident.normalize_expression(text_oracle)
        self.assertEqual(normalized, "CASE WHEN STATUS='PENDING' THEN PRIORITY END")

        # Texto do registro
        text_reg = "CASE WHEN status = 'PENDING' THEN priority END"
        norm_reg = sql_ident.normalize_expression(text_reg)
        self.assertEqual(normalized, norm_reg)

    def test_data_default_espacos_e_quebras(self):
        """DATA_DEFAULT com espacos e quebras no fim bate com o valor normalizado."""
        self.assertEqual(sql_ident.normalize_expression("'N' \n"), "'N'")
        self.assertEqual(sql_ident.normalize_expression("SYSDATE \n\t"), "SYSDATE")
        self.assertEqual(sql_ident.normalize_expression("0\n"), "0")

    def test_ck_not_null_sistema_ignorada(self):
        """CK de sistema SYS_C% que apenas checa IS NOT NULL eh identificada."""
        self.assertTrue(sql_ident.is_system_not_null_ck("SYS_C0012345", '"STATUS" IS NOT NULL'))
        self.assertTrue(sql_ident.is_system_not_null_ck("SYS_C99999", "NOME IS NOT NULL"))
        self.assertFalse(sql_ident.is_system_not_null_ck("ck_tbsss_tck_stat", "status IN ('PENDING')"))
        self.assertFalse(sql_ident.is_system_not_null_ck("SYS_C0012345", "status IN ('Y','N')"))


class TestInitDbCli(unittest.TestCase):
    """Testes do CLI scripts/init_db.py."""

    def test_dry_run_executavel_sem_conexao(self):
        """--dry-run imprime DDL completo e retorna codigo 0 sem abrir conexao."""
        with mock.patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = init_db.main(["--dry-run"])
        self.assertEqual(code, 0)
        output = mock_out.getvalue()
        self.assertIn("FASE 1: SEQUENCES", output)
        self.assertIn("CREATE SEQUENCE", output)
        self.assertIn("CREATE TABLE", output)
        self.assertIn("ALTER TABLE", output)
        self.assertIn("CREATE OR REPLACE TRIGGER", output)

    def test_argumento_desconhecido_recusado_codigo_2(self):
        """Argumento desconhecido como --recreate eh rejeitado com codigo 2."""
        with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = init_db.main(["--recreate"])
        self.assertEqual(code, 2)
        self.assertIn("Argumentos nao suportados", mock_err.getvalue())

    def test_prefixo_invalido_aborta_com_critical(self):
        """Prefixo que inicia com digito ou excede 8 chars gera log CRITICAL e codigo 2."""
        with tempfile.TemporaryDirectory() as tmp:
            ini_bad = os.path.join(tmp, "config.ini")
            with open(ini_bad, "w", encoding="utf-8") as f:
                f.write("[app]\nsss_env=DEV\ndata_backend=FAKE\n")
                f.write("[oracle]\nuser=u\ndsn=d\nowner=ow\ntable_prefix=1prefix_\nmodo_driver=auto\n")
                f.write("[secrets]\nsecrets_file=/tmp/secrets.cfg\n")

            with self.assertLogs("sss_init_db", level="CRITICAL") as cm:
                code = init_db.main(["--config", ini_bad, "--dry-run"])

            self.assertEqual(code, 2)
            self.assertTrue(any("CRITICAL" in msg for msg in cm.output))

    def test_cr016a_esquema_1_detectado_pela_tabela_de_controle_antiga(self):
        """CR-016a: tbsss_controle (esquema anterior, em portugues) no owner impede criar o novo ao lado dele."""
        for count, expected in ((1, True), (0, False)):
            conn = mock.MagicMock()
            cur = conn.cursor.return_value
            cur.fetchone.return_value = (count,)
            self.assertIs(init_db._schema_1_exists(conn, "openrisow", "tbsss_"), expected)
            _sql, binds = cur.execute.call_args[0][0], cur.execute.call_args[1]
            self.assertEqual(binds, {"o": "OPENRISOW", "t": "TBSSS_CONTROLE"})
            cur.close.assert_called_once_with()


class TestInitDbCheckMock(unittest.TestCase):
    """Testes da conferencia de esquema com conexao simulada."""

    def test_conferencia_detecta_divergencia_coluna_ausente(self):
        """Conferencia de esquema detecta se uma coluna esperada nao existe no banco."""
        mock_conn = mock.MagicMock()
        mock_cursor = mock.MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        def fake_fetchall():
            call = mock_cursor.execute.call_args[0][0]
            if "ALL_OBJECTS" in call:
                return []
            if "ALL_TAB_COLUMNS" in call:
                # Retorna apenas 'id', faltando 'created_by' e outras colunas
                return [("id", "NUMBER", None, 10, 0, "N", None)]
            return []

        mock_cursor.fetchall.side_effect = fake_fetchall
        mock_cursor.fetchone.return_value = None

        ok, divergences = init_db._check_schema(mock_conn, "openrisow", "tbsss_", log_fn=lambda x: None)
        self.assertFalse(ok)
        self.assertTrue(any("Coluna ausente" in d for d in divergences))

    def test_conferencia_detecta_objeto_invalido(self):
        """Conferencia de esquema detecta triggers ou objetos com status INVALID."""
        mock_conn = mock.MagicMock()
        mock_cursor = mock.MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        def fake_fetchall():
            call = mock_cursor.execute.call_args[0][0]
            if "ALL_OBJECTS" in call:
                return [("TRIGGER", "TR_TBSSS_TCK_BI")]
            if "ALL_ERRORS" in call:
                return [(10, 5, "PLS-00103: Encountered symbol")]
            return []

        mock_cursor.fetchall.side_effect = fake_fetchall
        mock_cursor.fetchone.return_value = None

        ok, divergences = init_db._check_schema(mock_conn, "openrisow", "tbsss_", log_fn=lambda x: None)
        self.assertFalse(ok)
        self.assertTrue(any("Objeto invalido" in d for d in divergences))


class TestInitDbSeedMock(unittest.TestCase):
    """Seed do init_db com conexao simulada: ordem dos MERGE e conclusao sem erro."""

    def test_seed_grava_ambientes_antes_de_ligar_aos_perfis(self):
        """A matriz perfil x ambiente liga pelo nome: o ambiente precisa existir antes (bug do seed desde a F7)."""
        mock_conn = mock.MagicMock()
        mock_cursor = mock.MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        init_db._run_seed(mock_conn, "openrisow", "tbsss_", log_fn=lambda x: None)
        mock_conn.commit.assert_called_once_with()
        mock_conn.rollback.assert_not_called()
        schema = sql_ident.names("tbsss_")
        tb_env = "openrisow." + schema["environments"]["tabela"]
        tb_penv = "openrisow." + schema["profile_env"]["tabela"]
        gravados = set()
        ligados = 0
        for chamada in mock_cursor.execute.call_args_list:
            sql, binds = chamada[0][0], (chamada[0][1] if len(chamada[0]) > 1 else {})
            if re.search(r"MERGE INTO %s dst" % re.escape(tb_env), sql):
                gravados.add(binds["name"])
            elif re.search(r"MERGE INTO %s dst" % re.escape(tb_penv), sql):
                self.assertIn(binds["env_name"], gravados)
                ligados += 1
        self.assertEqual(gravados, set(n for n, _d, _c, _p in ddl_builder.DEFAULT_ENVIRONMENTS))
        self.assertEqual(ligados, sum(len(p[4]) for p in ddl_builder.DEFAULT_PROFILES))


class TestDdlSeedAndRollback(unittest.TestCase):
    """Testes unitarios da geracao de scripts DML Seed, Rollback e CLI de geracao SQL."""

    def setUp(self):
        self.owner = "openrisow"
        self.prefixo = "tbsss_"

    def test_gerar_script_seed(self):
        """Script de seed contem MERGEs idempotentes, 5 ambientes, estatisticas e COMMIT."""
        sql_seed = ddl_builder.build_seed_script(self.owner, self.prefixo)

        self.assertIn("MERGE INTO openrisow.tbsss_features", sql_seed)
        self.assertIn("MERGE INTO openrisow.tbsss_profiles", sql_seed)
        self.assertIn("MERGE INTO openrisow.tbsss_profile_feature", sql_seed)
        self.assertIn("MERGE INTO openrisow.tbsss_environments", sql_seed)
        self.assertIn("MERGE INTO openrisow.tbsss_control", sql_seed)

        # 5 ambientes padrao
        for env in ("CLONE2", "CLONE1", "CLONE6", "CLONE7", "GFPREPROD"):
            self.assertIn("'%s'" % env, sql_seed)

        # Estatisticas e commit
        self.assertIn("DBMS_STATS.GATHER_TABLE_STATS", sql_seed)
        self.assertIn("COMMIT;", sql_seed)

    def test_gerar_script_rollback(self):
        """Script de rollback contem drop de 23 triggers, 21 tabelas CASCADE PURGE e 21 sequences."""
        sql_rb = ddl_builder.build_rollback_script(self.owner, self.prefixo)

        # 23 triggers
        self.assertEqual(sql_rb.count("DROP TRIGGER openrisow.tr_"), 23)

        # 21 tabelas
        self.assertEqual(sql_rb.count("CASCADE CONSTRAINTS PURGE;"), 21)

        # 21 sequences
        self.assertEqual(sql_rb.count("DROP SEQUENCE openrisow.sq_"), 21)

        # Ordem de remocao: ticket_answer e tickets antes de ambientes e perfis
        pos_tck = sql_rb.index("DROP TABLE openrisow.tbsss_tickets")
        pos_env = sql_rb.index("DROP TABLE openrisow.tbsss_environments")
        self.assertLess(pos_tck, pos_env)

    def test_hash_do_seed_confere_com_a_senha_documentada(self):
        """Regressao (F7.3): o hash do seed nao conferia com a senha do README §11.1 e nenhum usuario entrava."""
        from sss.core import security
        self.assertTrue(security.verify_password("Sss@Homolog2026!", ddl_builder.HOMOLOGATION_DEFAULT_PASSWORD_HASH))
        seed = "\n".join(ddl_builder.build_seed_statements(self.owner, self.prefixo))
        self.assertIn(ddl_builder.HOMOLOGATION_DEFAULT_PASSWORD_HASH, seed)

    def test_validacao_sem_hash_e_com_owner_prefixo_parametrizados(self):
        """99_validate_deploy: nao mostra password_hash, nao fixa owner/prefixo e respeita o limite de linha do SQL*Plus."""
        sql = ddl_builder.build_validation_script("SSS_APP", "abc_")
        self.assertNotIn("tbsss", sql.lower())
        self.assertNotIn("openrisow", sql.lower())
        self.assertNotIn("user_tables", sql.lower())
        self.assertIn("SSS_APP.abc_users", sql)
        self.assertIn("owner = 'SSS_APP'", sql)
        # password_hash so aparece dentro do CASE que diz se a senha esta definida (AGENTS §3.3).
        uses = [l for l in sql.splitlines() if "password_hash" in l]
        self.assertEqual(uses, ["       CASE WHEN u.password_hash IS NULL THEN 'N' ELSE 'Y' END AS senha_definida"])
        self.assertLessEqual(max(len(l) for l in sql.splitlines()), 2499)
        self.assertIn("GRANTS A PUBLIC", sql)
        self.assertNotIn("SELECT *", sql)

    def test_validacao_espera_o_registro_e_o_seed(self):
        """Os esperados vem do registro (objetos) e do proprio seed (minimo de linhas)."""
        sql = ddl_builder.build_validation_script(self.owner, self.prefixo)
        schema = sql_ident.names(self.prefixo)
        self.assertIn("'TABELAS' AS verificacao, '=' AS regra, {} AS esperado".format(len(schema)), sql)
        self.assertIn("'VERSAO DO ESQUEMA' AS verificacao, '=' AS regra, {} AS esperado".format(
            sql_ident.SCHEMA_VERSION), sql)
        seed = ddl_builder.build_seed_statements(self.owner, self.prefixo)
        count = ddl_builder._seed_rows_by_table(self.owner, self.prefixo)
        self.assertEqual(sum(count.values()), sum(1 for c in seed if c.lstrip().upper().startswith("MERGE INTO")))
        self.assertEqual(count["users"], 4)
        self.assertIn("'LINHAS TBSSS_SCRIPT_ENV' AS verificacao, '>=' AS regra, {} AS esperado".format(
            count["script_env"]), sql)
        # Resumo final com OK/FALHA em cada secao de verificacao.
        self.assertEqual(sql.count("'OK: nenhuma falha'"), 2)

    def test_gerar_scripts_sql_cli_e_init_db_flag(self):
        """CLI gerar_scripts_sql e init_db --generate-sql gravam arquivos validos em disco."""
        from sss.cli import generate_sql as gerar_scripts_sql

        with tempfile.TemporaryDirectory() as tmp_dir:
            ret = gerar_scripts_sql.main([
                "--owner", self.owner,
                "--prefix", self.prefixo,
                "--out-dir", tmp_dir,
            ])
            self.assertEqual(ret, 0)
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir, "01_deploy_sss.sql")))
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir, "02_rollback_sss.sql")))
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir, "99_validate_deploy.sql")))

        with tempfile.TemporaryDirectory() as tmp_dir2:
            ret = init_db.main([
                "--owner-user", self.owner,
                "--generate-sql", tmp_dir2,
            ])
            self.assertEqual(ret, 0)
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir2, "01_deploy_sss.sql")))
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir2, "02_rollback_sss.sql")))


if __name__ == "__main__":
    unittest.main()
