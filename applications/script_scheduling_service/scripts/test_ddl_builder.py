# -*- coding: utf-8 -*-
"""Testes unitarios para ddl_builder.py, sql_ident.normalizar_expressao e scripts/init_db.py (F7.1).

Cobre a geracao de DDL Oracle 11gR2 fase a fase, triggers, restricoes de seguranca,
normalizacao de expressoes SQL contra textos reais do 11gR2, GRANTs por papel e CLI.
"""
import copy
import io
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

import _testenv  # noqa: F401
import ddl_builder
import init_db
import sql_ident
import sss_config


class TestDdlBuilder(unittest.TestCase):
    """Testes da geracao declarativa de DDL a partir de sql_ident."""

    def setUp(self):
        self.owner = "openrisow"
        self.prefixo = "tbsss_"
        self.instrucoes = ddl_builder.gerar_instrucoes_ddl(self.owner, self.prefixo)

    def test_ddl_contem_todos_os_nomes_do_registro(self):
        """O DDL gerado contem todos os nomes de objetos registrados em sql_ident."""
        nomes_esperados = sql_ident.todos_identificadores(self.prefixo, incluir_colunas=False)
        nomes_gerados = set(item.nome for item in self.instrucoes)

        for nome in nomes_esperados:
            self.assertIn(
                nome, nomes_gerados,
                "Objeto '%s' registrado em sql_ident nao foi gerado no DDL" % nome
            )

    def test_proibicoes_sql_12c_e_tipos_estritos(self):
        """Garante ausencia de sintaxe 12c+ e presenca de VARCHAR2(n CHAR)."""
        proibidos = [
            re.compile(r"\bIDENTITY\b", re.IGNORECASE),
            re.compile(r"\bFETCH\s+FIRST\b", re.IGNORECASE),
            re.compile(r"\bOFFSET\b", re.IGNORECASE),
            re.compile(r"\bJSON_\w+", re.IGNORECASE),
            re.compile(r"\bIS\s+JSON\b", re.IGNORECASE),
            re.compile(r"VARCHAR2\(\d+\)(?! CHAR)", re.IGNORECASE),
        ]

        for item in self.instrucoes:
            sql = item.sql
            for padrao in proibidos:
                self.assertIsNone(
                    padrao.search(sql),
                    "Padrao proibido '%s' encontrado no DDL de %s %s:\n%s"
                    % (padrao.pattern, item.tipo, item.nome, sql)
                )

    def test_triggers_bi_e_bu_literais(self):
        """Valida que toda trigger _bi segue o template do AGENTS §4.2 e _bu aplica imutabilidade."""
        triggers = [item for item in self.instrucoes if item.tipo == "TRIGGER"]
        self.assertEqual(len(triggers), 19, "Devem existir 17 triggers _bi e 2 _bu")

        bi_triggers = [t for t in triggers if t.nome.endswith("_bi")]
        self.assertEqual(len(bi_triggers), 17)

        template_esperado = (
            "BEGIN\n"
            "    IF :NEW.id IS NULL THEN\n"
            "        SELECT {owner}.{sequence_name}.NEXTVAL INTO :NEW.id FROM DUAL;\n"
            "    END IF;\n"
            "END;"
        )

        esquema = sql_ident.nomes(self.prefixo)
        for t in bi_triggers:
            entidade = t.entidade
            seq = esquema[entidade]["sequence"]
            esperado = template_esperado.format(owner=self.owner, sequence_name=seq)
            self.assertIn(esperado, t.sql)

        # Triggers _bu (ambientes e usuarios)
        bu_triggers = {t.nome: t for t in triggers if t.nome.endswith("_bu")}
        self.assertEqual(len(bu_triggers), 2)

        tr_amb_bu = bu_triggers["tr_tbsss_amb_bu"]
        self.assertIn(":NEW.nome <> :OLD.nome", tr_amb_bu.sql)
        self.assertIn("RAISE_APPLICATION_ERROR(-20001, 'nome é imutável')", tr_amb_bu.sql)

        tr_usr_bu = bu_triggers["tr_tbsss_usr_bu"]
        self.assertIn(":NEW.login <> :OLD.login", tr_usr_bu.sql)
        self.assertIn("RAISE_APPLICATION_ERROR(-20001, 'login é imutável')", tr_usr_bu.sql)

    def test_ordem_estrita_das_fases(self):
        """As fases 1 a 6 respeitam a ordem estrita do README §11.1."""
        fases = [item.fase for item in self.instrucoes]
        # Garante que a lista de fases e nao-decrescente
        for i in range(len(fases) - 1):
            self.assertLessEqual(fases[i], fases[i + 1])

        # Verifica tipo esperado por fase
        tipos_por_fase = {
            1: {"SEQUENCE"},
            2: {"TABLE"},
            3: {"CONSTRAINT"},
            4: {"CONSTRAINT"},
            5: {"INDEX"},
            6: {"TRIGGER"},
        }
        for item in self.instrucoes:
            esperados = tipos_por_fase[item.fase]
            self.assertIn(item.tipo, esperados)

    def test_cr005_path_file_e_cks(self):
        """Valida path_file VARCHAR2(500 CHAR) NOT NULL e CKs do CR-005."""
        tabelas = {item.nome: item.sql for item in self.instrucoes if item.tipo == "TABLE"}
        self.assertIn("path_file VARCHAR2(500 CHAR) NOT NULL", tabelas["tbsss_scripts"])
        self.assertNotIn("pasta_base", tabelas["tbsss_scripts"])
        self.assertNotIn("pastas_base", tabelas["tbsss_agentes"])

        constraints = {item.nome: item.sql for item in self.instrucoes if item.tipo == "CONSTRAINT"}
        ck_path = constraints["ck_tbsss_scr_path"]
        self.assertIn("SUBSTR(path_file, 1, 1) = '/'", ck_path)
        self.assertIn("INSTR(path_file, '..') = 0", ck_path)
        self.assertIn("INSTR(path_file, '//') = 0", ck_path)
        self.assertIn("INSTR(path_file, '\\') = 0", ck_path)

        ck_plat = constraints["ck_tbsss_agt_plat"]
        self.assertIn("plataforma IS NULL OR plataforma IN ('LINUX','UNIX')", ck_plat)

    def test_cr006_colunas_registro_e_ck_upd(self):
        """Valida que as 15 tabelas (menos auditoria e controle) tem colunas de registro e ck_upd."""
        tabelas = {item.nome: item.sql for item in self.instrucoes if item.tipo == "TABLE"}
        constraints = {item.nome: item.sql for item in self.instrucoes if item.tipo == "CONSTRAINT"}

        esquema = sql_ident.nomes(self.prefixo)
        for ent, t in esquema.items():
            t_nome = t["tabela"]
            abrev = t["abrev"]
            sql_t = tabelas[t_nome]

            if ent in ("auditoria", "controle"):
                self.assertNotIn("created_by", sql_t)
                self.assertNotIn("updated_at", sql_t)
                self.assertNotIn("updated_by", sql_t)
                self.assertNotIn("ck_{}{}_upd".format(self.prefixo, abrev), constraints)
            else:
                self.assertIn("created_at DATE DEFAULT SYSDATE NOT NULL", sql_t)
                self.assertIn("created_by VARCHAR2(40 CHAR) NOT NULL", sql_t)
                self.assertNotIn("created_by VARCHAR2(40 CHAR) DEFAULT", sql_t)
                self.assertIn("updated_at DATE", sql_t)
                self.assertIn("updated_by VARCHAR2(40 CHAR)", sql_t)

                ck_upd_nome = "ck_{}{}_upd".format(self.prefixo, abrev)
                self.assertIn(ck_upd_nome, constraints)
                self.assertIn("(updated_at IS NULL AND updated_by IS NULL)", constraints[ck_upd_nome])

    def test_cr007_controle_fbi_unico_sha_e_lobs(self):
        """Valida objetos adicionados pelo CR-007 e suporte a SECUREFILE e BASICFILE."""
        constraints = {item.nome: item.sql for item in self.instrucoes if item.tipo == "CONSTRAINT"}
        indices = {item.nome: item.sql for item in self.instrucoes if item.tipo == "INDEX"}
        tabelas = {item.nome: item.sql for item in self.instrucoes if item.tipo == "TABLE"}

        # tbsss_controle
        self.assertIn("ck_tbsss_ctl_id", constraints)
        self.assertIn("id = 1", constraints["ck_tbsss_ctl_id"])
        self.assertIn("versao_esquema >= 1", constraints["ck_tbsss_ctl_versao"])

        # FBI unico ix_tbsss_tck_ocor
        self.assertIn("ix_tbsss_tck_ocor", indices)
        self.assertTrue(indices["ix_tbsss_tck_ocor"].startswith("CREATE UNIQUE INDEX"))
        self.assertIn("agendamento_id IS NOT NULL", indices["ix_tbsss_tck_ocor"])

        # CKs _sha
        self.assertIn("ck_tbsss_scr_sha", constraints)
        self.assertIn("ck_tbsss_tck_sha", constraints)

        # LOB Securefile (padrao)
        self.assertIn("LOB (parametros_json) STORE AS SECUREFILE (CACHE)", tabelas["tbsss_agendamentos"])
        self.assertIn("LOB (parametros_enviados, log_output) STORE AS SECUREFILE (CACHE)", tabelas["tbsss_tickets"])

        # Fallback Basicfile
        ddl_basic = ddl_builder.gerar_instrucoes_ddl(self.owner, self.prefixo, lob_storage="BASICFILE")
        tabelas_basic = {item.nome: item.sql for item in ddl_basic if item.tipo == "TABLE"}
        self.assertIn("LOB (parametros_json) STORE AS BASICFILE", tabelas_basic["tbsss_agendamentos"])
        self.assertIn("LOB (parametros_enviados, log_output) STORE AS BASICFILE", tabelas_basic["tbsss_tickets"])

    def test_cr008_sessao_epoch_pid_daemon_log_offset(self):
        """Valida campos adicionados e ajustados pelo CR-008."""
        tabelas = {item.nome: item.sql for item in self.instrucoes if item.tipo == "TABLE"}
        constraints = {item.nome: item.sql for item in self.instrucoes if item.tipo == "CONSTRAINT"}

        # tbsss_usuarios.sessao_epoch e ck
        self.assertIn("sessao_epoch NUMBER(10) DEFAULT 0 NOT NULL", tabelas["tbsss_usuarios"])
        self.assertIn("ck_tbsss_usr_epoch", constraints)
        self.assertIn("sessao_epoch >= 0", constraints["ck_tbsss_usr_epoch"])

        # tbsss_agentes.pid_daemon
        self.assertIn("pid_daemon NUMBER(10)", tabelas["tbsss_agentes"])

        # tbsss_tickets.log_offset_chars e ck
        self.assertIn("log_offset_chars NUMBER(20) DEFAULT 0 NOT NULL", tabelas["tbsss_tickets"])
        self.assertIn("ck_tbsss_tck_logoff", constraints)
        self.assertIn("log_offset_chars >= 0", constraints["ck_tbsss_tck_logoff"])


class TestGrantsPorPapel(unittest.TestCase):
    """Testes dos comandos GRANT gerados por papel (README §11.1)."""

    def setUp(self):
        self.papeis = {
            "web": "sss_web",
            "agente": "sss_agente",
            "purge": "sss_purge",
            "monitor": "sss_monitor",
        }
        self.grants = ddl_builder.gerar_grants_por_papel("openrisow", "tbsss_", self.papeis)
        self.grants_texto = "\n".join(self.grants)

    def test_auditoria_protegida_contra_update_e_delete(self):
        """Web e agente nunca tem UPDATE ou DELETE em tbsss_auditoria (CR-007, D1b)."""
        for g in self.grants:
            if "ON openrisow.tbsss_auditoria TO" in g:
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

        tabelas_monitor = [
            "tbsss_agentes", "tbsss_tickets", "tbsss_agendamentos", "tbsss_scripts",
            "tbsss_ambientes", "tbsss_controle", "tbsss_auditoria"
        ]
        for t in tabelas_monitor:
            self.assertTrue(any(t in g for g in grants_monitor), "Faltou GRANT para %s" % t)

    def test_nunca_concede_a_public(self):
        """O script de implantacao nao concede nada a PUBLIC (tbsss_usuarios guarda senha_hash)."""
        script = ddl_builder.gerar_script_implantacao_completo("openrisow", "tbsss_", papeis_usuarios=self.papeis)
        self.assertNotIn("PUBLIC", script.upper().replace("NENHUM GRANT A PUBLIC", ""))
        self.assertIn("GRANT SELECT ON openrisow.tbsss_agentes TO sss_monitor;", script)
        self.assertFalse(hasattr(ddl_builder, "gerar_grants_public"))

    def test_conta_igual_ao_owner_nao_recebe_grant(self):
        """Papel que usa a conta dona do esquema vira comentario (GRANT a si mesmo e ORA-01749)."""
        grants = ddl_builder.gerar_grants_por_papel(
            "openrisow", "tbsss_", {"web": "OPENRISOW", "agente": "openrisow", "purge": "sss_purge"})
        comandos = [g for g in grants if not g.startswith("--")]
        self.assertTrue(comandos)
        self.assertTrue(all(g.endswith("TO sss_purge;") for g in comandos))
        self.assertIn("-- papel web: usa a conta dona do esquema (openrisow); nenhum GRANT necessario", grants)
        self.assertIn("-- papel monitor: conta nao informada; nenhum GRANT gerado", grants)

    def test_sem_contas_nenhum_grant(self):
        grants = ddl_builder.gerar_grants_por_papel("openrisow", "tbsss_", {})
        self.assertEqual(len(grants), 4)
        self.assertTrue(all(g.startswith("-- papel ") for g in grants))

    def test_conta_ou_papel_invalidos_recusados(self):
        """A conta entra no texto do GRANT: so identificador Oracle valido; papel fora da lista e recusado."""
        for usr in ("sss_web; DROP TABLE x", "1abc", "a" * 31, "PUBLIC x", "PUBLIC", "public"):
            with self.assertRaises(ValueError):
                ddl_builder.gerar_grants_por_papel("openrisow", "tbsss_", {"web": usr})
        with self.assertRaises(ValueError):
            ddl_builder.gerar_grants_por_papel("openrisow", "tbsss_", {"dba": "sss_dba"})

    def test_papel_purge_concessao_controle(self):
        """Papel purge recebe SELECT e UPDATE em controle somente nas colunas de concessao."""
        grants_purge = [g for g in self.grants if "TO sss_purge" in g]
        self.assertTrue(any("UPDATE (purge_dono, purge_concessao_ate) ON openrisow.tbsss_controle" in g for g in grants_purge))


class TestNormalizacaoExpressaoOracle11g(unittest.TestCase):
    """Testes de normalizar_expressao com textos reais do Oracle 11gR2 (CR-008, R-14)."""

    def test_fbi_texto_real_11g(self):
        """FBI com CASE e aspas duplas no 11gR2 bate normalizado contra o registro."""
        texto_oracle = 'CASE WHEN "STATUS"=\'PENDING\' THEN "PRIORIDADE" END'
        normalizado = sql_ident.normalizar_expressao(texto_oracle)
        self.assertEqual(normalizado, "CASE WHEN STATUS='PENDING' THEN PRIORIDADE END")

        # Texto do registro
        texto_reg = "CASE WHEN status = 'PENDING' THEN prioridade END"
        norm_reg = sql_ident.normalizar_expressao(texto_reg)
        self.assertEqual(normalizado, norm_reg)

    def test_data_default_espacos_e_quebras(self):
        """DATA_DEFAULT com espacos e quebras no fim bate com o valor normalizado."""
        self.assertEqual(sql_ident.normalizar_expressao("'N' \n"), "'N'")
        self.assertEqual(sql_ident.normalizar_expressao("SYSDATE \n\t"), "SYSDATE")
        self.assertEqual(sql_ident.normalizar_expressao("0\n"), "0")

    def test_ck_not_null_sistema_ignorada(self):
        """CK de sistema SYS_C% que apenas checa IS NOT NULL eh identificada."""
        self.assertTrue(sql_ident.eh_ck_not_null_sistema("SYS_C0012345", '"STATUS" IS NOT NULL'))
        self.assertTrue(sql_ident.eh_ck_not_null_sistema("SYS_C99999", "NOME IS NOT NULL"))
        self.assertFalse(sql_ident.eh_ck_not_null_sistema("ck_tbsss_tck_stat", "status IN ('PENDING')"))
        self.assertFalse(sql_ident.eh_ck_not_null_sistema("SYS_C0012345", "status IN ('S','N')"))


class TestInitDbCli(unittest.TestCase):
    """Testes do CLI scripts/init_db.py."""

    def test_dry_run_executavel_sem_conexao(self):
        """--dry-run imprime DDL completo e retorna codigo 0 sem abrir conexao."""
        with mock.patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = init_db.main(["--dry-run"])
        self.assertEqual(code, 0)
        saida = mock_out.getvalue()
        self.assertIn("FASE 1: SEQUENCES", saida)
        self.assertIn("CREATE SEQUENCE", saida)
        self.assertIn("CREATE TABLE", saida)
        self.assertIn("ALTER TABLE", saida)
        self.assertIn("CREATE OR REPLACE TRIGGER", saida)

    def test_argumento_desconhecido_recusado_codigo_2(self):
        """Argumento desconhecido como --recreate eh rejeitado com codigo 2."""
        with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = init_db.main(["--recreate"])
        self.assertEqual(code, 2)
        self.assertIn("Argumentos nao suportados", mock_err.getvalue())

    def test_prefixo_invalido_aborta_com_critical(self):
        """Prefixo que inicia com digito ou excede 8 chars gera log CRITICAL e codigo 2."""
        with tempfile.TemporaryDirectory() as tmp:
            ini_ruim = os.path.join(tmp, "config.ini")
            with open(ini_ruim, "w", encoding="utf-8") as f:
                f.write("[app]\nsss_env=DEV\ndata_backend=FAKE\n")
                f.write("[oracle]\nuser=u\ndsn=d\nowner=ow\ntable_prefix=1prefix_\nmodo_driver=auto\n")
                f.write("[secrets]\nsecrets_file=/tmp/secrets.cfg\n")

            with self.assertLogs("sss_init_db", level="CRITICAL") as cm:
                code = init_db.main(["--config", ini_ruim, "--dry-run"])

            self.assertEqual(code, 2)
            self.assertTrue(any("CRITICAL" in msg for msg in cm.output))


class TestInitDbConferenciaMock(unittest.TestCase):
    """Testes da conferencia de esquema com conexao simulada."""

    def test_conferencia_detecta_divergencia_coluna_ausente(self):
        """Conferencia de esquema detecta se uma coluna esperada nao existe no banco."""
        mock_conn = mock.MagicMock()
        mock_cursor = mock.MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        def fake_fetchall():
            chamada = mock_cursor.execute.call_args[0][0]
            if "ALL_OBJECTS" in chamada:
                return []
            if "ALL_TAB_COLUMNS" in chamada:
                # Retorna apenas 'id', faltando 'created_by' e outras colunas
                return [("id", "NUMBER", None, 10, 0, "N", None)]
            return []

        mock_cursor.fetchall.side_effect = fake_fetchall
        mock_cursor.fetchone.return_value = None

        ok, divergencias = init_db._conferir_esquema(mock_conn, "openrisow", "tbsss_", log_fn=lambda x: None)
        self.assertFalse(ok)
        self.assertTrue(any("Coluna ausente" in d for d in divergencias))

    def test_conferencia_detecta_objeto_invalido(self):
        """Conferencia de esquema detecta triggers ou objetos com status INVALID."""
        mock_conn = mock.MagicMock()
        mock_cursor = mock.MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        def fake_fetchall():
            chamada = mock_cursor.execute.call_args[0][0]
            if "ALL_OBJECTS" in chamada:
                return [("TRIGGER", "TR_TBSSS_TCK_BI")]
            if "ALL_ERRORS" in chamada:
                return [(10, 5, "PLS-00103: Encountered symbol")]
            return []

        mock_cursor.fetchall.side_effect = fake_fetchall
        mock_cursor.fetchone.return_value = None

        ok, divergencias = init_db._conferir_esquema(mock_conn, "openrisow", "tbsss_", log_fn=lambda x: None)
        self.assertFalse(ok)
        self.assertTrue(any("Objeto invalido" in d for d in divergencias))


class TestDdlSeedERollback(unittest.TestCase):
    """Testes unitarios da geracao de scripts DML Seed, Rollback e CLI de geracao SQL."""

    def setUp(self):
        self.owner = "openrisow"
        self.prefixo = "tbsss_"

    def test_gerar_script_seed(self):
        """Script de seed contem MERGEs idempotentes, 5 ambientes, estatisticas e COMMIT."""
        sql_seed = ddl_builder.gerar_script_seed(self.owner, self.prefixo)

        self.assertIn("MERGE INTO openrisow.tbsss_funcionalidades", sql_seed)
        self.assertIn("MERGE INTO openrisow.tbsss_perfis", sql_seed)
        self.assertIn("MERGE INTO openrisow.tbsss_perfil_func", sql_seed)
        self.assertIn("MERGE INTO openrisow.tbsss_ambientes", sql_seed)
        self.assertIn("MERGE INTO openrisow.tbsss_controle", sql_seed)

        # 5 ambientes padrao
        for amb in ("CLONE2", "CLONE1", "CLONE6", "CLONE7", "GFPREPROD"):
            self.assertIn("'%s'" % amb, sql_seed)

        # Estatisticas e commit
        self.assertIn("DBMS_STATS.GATHER_TABLE_STATS", sql_seed)
        self.assertIn("COMMIT;", sql_seed)

    def test_gerar_script_rollback(self):
        """Script de rollback contem drop de 19 triggers, 17 tabelas CASCADE PURGE e 17 sequences."""
        sql_rb = ddl_builder.gerar_script_rollback(self.owner, self.prefixo)

        # 19 triggers
        self.assertEqual(sql_rb.count("DROP TRIGGER openrisow.tr_"), 19)

        # 17 tabelas
        self.assertEqual(sql_rb.count("CASCADE CONSTRAINTS PURGE;"), 17)

        # 17 sequences
        self.assertEqual(sql_rb.count("DROP SEQUENCE openrisow.sq_"), 17)

        # Ordem de remocao: ticket_resp e tickets antes de ambientes e perfis
        pos_tck = sql_rb.index("DROP TABLE openrisow.tbsss_tickets")
        pos_amb = sql_rb.index("DROP TABLE openrisow.tbsss_ambientes")
        self.assertLess(pos_tck, pos_amb)

    def test_validacao_sem_hash_e_com_owner_prefixo_parametrizados(self):
        """99_validar: nao mostra senha_hash, nao fixa owner/prefixo e respeita o limite de linha do SQL*Plus."""
        sql = ddl_builder.gerar_script_validacao("SSS_APP", "abc_")
        self.assertNotIn("tbsss", sql.lower())
        self.assertNotIn("openrisow", sql.lower())
        self.assertNotIn("user_tables", sql.lower())
        self.assertIn("SSS_APP.abc_usuarios", sql)
        self.assertIn("owner = 'SSS_APP'", sql)
        # senha_hash so aparece dentro do CASE que diz se a senha esta definida (AGENTS §3.3).
        usos = [l for l in sql.splitlines() if "senha_hash" in l]
        self.assertEqual(usos, ["       CASE WHEN u.senha_hash IS NULL THEN 'N' ELSE 'S' END AS senha_definida"])
        self.assertLessEqual(max(len(l) for l in sql.splitlines()), 2499)
        self.assertIn("GRANTS A PUBLIC", sql)
        self.assertNotIn("SELECT *", sql)

    def test_validacao_espera_o_registro_e_o_seed(self):
        """Os esperados vem do registro (objetos) e do proprio seed (minimo de linhas)."""
        sql = ddl_builder.gerar_script_validacao(self.owner, self.prefixo)
        esquema = sql_ident.nomes(self.prefixo)
        self.assertIn("'TABELAS' AS verificacao, '=' AS regra, {} AS esperado".format(len(esquema)), sql)
        self.assertIn("'VERSAO DO ESQUEMA' AS verificacao, '=' AS regra, {} AS esperado".format(
            sql_ident.VERSAO_ESQUEMA), sql)
        seed = ddl_builder.gerar_instrucoes_seed(self.owner, self.prefixo)
        contagem = ddl_builder._linhas_seed_por_tabela(self.owner, self.prefixo)
        self.assertEqual(sum(contagem.values()), sum(1 for c in seed if c.lstrip().upper().startswith("MERGE INTO")))
        self.assertEqual(contagem["usuarios"], 4)
        self.assertIn("'LINHAS TBSSS_SCRIPT_AMB' AS verificacao, '>=' AS regra, {} AS esperado".format(
            contagem["script_amb"]), sql)
        # Resumo final com OK/FALHA em cada secao de verificacao.
        self.assertEqual(sql.count("'OK: nenhuma falha'"), 2)

    def test_gerar_scripts_sql_cli_e_init_db_flag(self):
        """CLI gerar_scripts_sql e init_db --gerar-sql gravam arquivos validos em disco."""
        import gerar_scripts_sql

        with tempfile.TemporaryDirectory() as tmp_dir:
            ret = gerar_scripts_sql.main([
                "--owner", self.owner,
                "--prefixo", self.prefixo,
                "--out-dir", tmp_dir,
            ])
            self.assertEqual(ret, 0)
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir, "01_implantar_sss.sql")))
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir, "02_rollback_sss.sql")))
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir, "99_validar_implantacao.sql")))

        with tempfile.TemporaryDirectory() as tmp_dir2:
            ret = init_db.main([
                "--usuario-dono", self.owner,
                "--gerar-sql", tmp_dir2,
            ])
            self.assertEqual(ret, 0)
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir2, "01_implantar_sss.sql")))
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir2, "02_rollback_sss.sql")))


class TestInitDbReal(unittest.TestCase):
    """Teste com conexao Oracle real caso SSS_TEST_DSN e SSS_TEST_OWNER estejam definidos."""

    def test_execucao_real_condicionada(self):
        dsn = os.environ.get("SSS_TEST_DSN")
        owner = os.environ.get("SSS_TEST_OWNER")
        disposable = os.environ.get("SSS_TEST_SCHEMA_DISPOSABLE")
        if not dsn or not owner or disposable != "1":
            self.skipTest("Schema descartavel real nao configurado (SSS_TEST_DSN/OWNER/DISPOSABLE); marcado como NAO TESTADO")

