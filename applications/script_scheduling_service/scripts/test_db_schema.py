# -*- coding: utf-8 -*-
"""Testes de conformidade do esquema Oracle e identificadores do SSS.

Cobertura obrigatoria (AGENTS.md §7.4):
- Todos os identificadores com len <= 30 com o prefixo configurado e com 'abcdefg_';
- Todos em ASCII casando ^[a-z][a-z0-9_]*$;
- Toda FK com indice ou UK cuja coluna lider e a FK;
- Toda tabela com sequence, trigger _bi e id NUMBER(10) NOT NULL;
- Toda coluna VARCHAR2 com CHAR explicito;
- Toda flag CHAR(1) com CK IN ('S','N');
- 18 tabelas exatas (CR-007: controle; CR-012: ticket_saida);
- Teste negativo de identificador com 31 caracteres;
- Colunas de registro do CR-006 e README §10 igual ao registro.
"""
import copy
import os
import re
import unittest

import _testenv  # noqa: F401 - ajusta sys.path sem importar gluon

import sql_ident
from sql_ident import (
    TABLES,
    FBI_TCK_QUEUE_EXPR,
    FBI_TCK_RUN_EXPR,
    names,
    qualify,
    all_identifiers,
    validate_name,
    validate_owner,
    validate_prefix,
    validate_registry,
)


class TestDbSchema(unittest.TestCase):
    """Bateria de testes de schema do modelo Oracle 11gR2."""

    def _obter_prefixo_config_example(self):
        """Le table_prefix diretamente de instance/config.ini.example."""
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg_path = os.path.join(app_dir, "instance", "config.ini.example")
        self.assertTrue(os.path.isfile(cfg_path), "config.ini.example deve existir")
        with open(cfg_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("table_prefix"):
                    partes = line.split("=", 1)
                    val = partes[1].split(";")[0].strip()
                    return val
        return "tbsss_"

    def test_dezessete_tabelas_exatas(self):
        """Verifica presenca e contagem exata das 18 tabelas do README §9.2 e §10 (CR-007: controle; CR-012: ticket_saida)."""
        entidades_esperadas = [
            "environments",
            "profiles",
            "features",
            "profile_feature",
            "profile_env",
            "scripts",
            "profile_script",
            "script_env",
            "users",
            "parameters",
            "script_param",
            "schedules",
            "tickets",
            "ticket_answer",
            "agents",
            "audit",
            "control",
            "ticket_output",
        ]
        self.assertEqual(len(TABLES), 18, "Devem existir exatamente 18 tabelas")
        self.assertEqual(list(TABLES.keys()), entidades_esperadas)

    def test_reproducao_exata_readme_9_2(self):
        """Verifica que nomes('tbsss_') reproduz exatamente a tabela do README §9.2."""
        esperado_readme = [
            # (entidade, abrev, sequence, trigger, pk)
            ("environments", "env", "sq_tbsss_environments", "tr_tbsss_env_bi", "pk_tbsss_environments"),
            ("profiles", "prf", "sq_tbsss_profiles", "tr_tbsss_prf_bi", "pk_tbsss_profiles"),
            ("features", "fea", "sq_tbsss_features", "tr_tbsss_fea_bi", "pk_tbsss_features"),
            ("profile_feature", "pfea", "sq_tbsss_profile_feature", "tr_tbsss_pfea_bi", "pk_tbsss_profile_feature"),
            ("profile_env", "penv", "sq_tbsss_profile_env", "tr_tbsss_penv_bi", "pk_tbsss_profile_env"),
            ("scripts", "scr", "sq_tbsss_scripts", "tr_tbsss_scr_bi", "pk_tbsss_scripts"),
            ("profile_script", "pscr", "sq_tbsss_profile_script", "tr_tbsss_pscr_bi", "pk_tbsss_profile_script"),
            ("script_env", "senv", "sq_tbsss_script_env", "tr_tbsss_senv_bi", "pk_tbsss_script_env"),
            ("users", "usr", "sq_tbsss_users", "tr_tbsss_usr_bi", "pk_tbsss_users"),
            ("parameters", "prm", "sq_tbsss_parameters", "tr_tbsss_prm_bi", "pk_tbsss_parameters"),
            ("script_param", "sprm", "sq_tbsss_script_param", "tr_tbsss_sprm_bi", "pk_tbsss_script_param"),
            ("schedules", "sch", "sq_tbsss_schedules", "tr_tbsss_sch_bi", "pk_tbsss_schedules"),
            ("tickets", "tck", "sq_tbsss_tickets", "tr_tbsss_tck_bi", "pk_tbsss_tickets"),
            ("ticket_answer", "tans", "sq_tbsss_ticket_answer", "tr_tbsss_tans_bi", "pk_tbsss_ticket_answer"),
            ("agents", "agt", "sq_tbsss_agents", "tr_tbsss_agt_bi", "pk_tbsss_agents"),
            ("audit", "aud", "sq_tbsss_audit", "tr_tbsss_aud_bi", "pk_tbsss_audit"),
            ("control", "ctl", "sq_tbsss_control", "tr_tbsss_ctl_bi", "pk_tbsss_control"),
            ("ticket_output", "tout", "sq_tbsss_ticket_output", "tr_tbsss_tout_bi", "pk_tbsss_ticket_output"),
        ]

        esquema = names("tbsss_")
        for ent, abrev, seq, trg, pk in esperado_readme:
            self.assertIn(ent, esquema, "Entidade '{}' ausente no resultado de nomes()".format(ent))
            t = esquema[ent]
            self.assertEqual(t["abrev"], abrev, "Abrev divergente em {}".format(ent))
            self.assertEqual(t["sequence"], seq, "Sequence divergente em {}".format(ent))
            self.assertEqual(t["trigger"], trg, "Trigger divergente em {}".format(ent))
            self.assertEqual(t["trigger_bi"], trg, "Trigger_bi divergente em {}".format(ent))
            self.assertEqual(t["pk"], pk, "PK divergente em {}".format(ent))
            self.assertEqual(t["tabela"], "tbsss_" + sql_ident.physical(ent), "Nome de tabela divergente em {}".format(ent))

    def test_limite_30_caracteres_config_example_e_pior_caso(self):
        """Valida len <= 30 para prefixo do config.ini.example e pior caso (8 chars)."""
        prefixo_cfg = self._obter_prefixo_config_example()
        prefixos_para_testar = [prefixo_cfg, "abcdefg_"]

        for pref in prefixos_para_testar:
            self.assertTrue(
                validate_registry(pref),
                "Registro deve ser valido com prefixo '{}'".format(pref),
            )
            todos = all_identifiers(pref)
            for ident in todos:
                self.assertLessEqual(
                    len(ident),
                    30,
                    "Identificador '{}' com prefixo '{}' excede 30 caracteres (len={})".format(
                        ident, pref, len(ident)
                    ),
                )

    def test_todos_identificadores_ascii_lowercase(self):
        """Verifica se todos os identificadores casam com ^[a-z][a-z0-9_]*$."""
        todos = all_identifiers("tbsss_")
        re_padrao = re.compile(r"^[a-z][a-z0-9_]*$")
        for ident in todos:
            self.assertIsNotNone(
                re_padrao.fullmatch(ident),
                "Identificador '{}' nao atende ao padrao ASCII lowercase ^[a-z][a-z0-9_]*$".format(
                    ident
                ),
            )

    def test_estrutura_padrao_id_sequence_trigger_bi(self):
        """Garante que toda tabela tem sequence, trigger _bi e coluna 'id NUMBER(10) NOT NULL'."""
        esquema = names("tbsss_")
        for entidade, t in esquema.items():
            cols = t["colunas"]
            self.assertIn("id", cols, "Tabela '{}' deve possuir coluna 'id'".format(entidade))
            id_col = cols["id"]
            self.assertEqual(id_col["tipo"], "NUMBER(10)", "id em '{}' deve ser NUMBER(10)".format(entidade))
            self.assertTrue(id_col["not_null"], "id em '{}' deve ser NOT NULL".format(entidade))
            self.assertEqual(t["pk"], "pk_tbsss_" + sql_ident.physical(entidade))
            self.assertEqual(t["sequence"], "sq_tbsss_" + sql_ident.physical(entidade))
            self.assertTrue(t["trigger_bi"].startswith("tr_tbsss_"))
            self.assertTrue(t["trigger_bi"].endswith("_bi"))

    def test_fks_possuem_indice_ou_uk_com_coluna_lider(self):
        """Garante que toda FK filha tem indice (ou UK/PK) cuja coluna lider e a FK (AGENTS §4.7)."""
        esquema = names("tbsss_")
        for entidade, t in esquema.items():
            for fk_nome, fk_info in t["fks"].items():
                fk_col_lider = fk_info["colunas"][0]
                coberta = False

                # Verifica se a PK cobre
                if TABLES[entidade]["pk"]["colunas"][0] == fk_col_lider:
                    coberta = True

                # Verifica se alguma UK cobre
                if not coberta:
                    for uk_info in t["uks"].values():
                        if uk_info["colunas"][0] == fk_col_lider:
                            coberta = True
                            break

                # Verifica se algum indice cobre
                if not coberta:
                    for ix_info in t["indices"].values():
                        if ix_info["colunas"] and ix_info["colunas"][0] == fk_col_lider:
                            coberta = True
                            break

                self.assertTrue(
                    coberta,
                    "FK '{}' em '{}' (coluna lider '{}') nao possui indice/UK/PK com coluna lider correspondente".format(
                        fk_nome, entidade, fk_col_lider
                    ),
                )

    def test_varchar2_com_char_explicito(self):
        """Garante que toda coluna VARCHAR2 declara 'CHAR' explicitamente (AGENTS §4.6)."""
        re_varchar = re.compile(r"^VARCHAR2\(\d+ CHAR\)$")
        for entidade, defn in TABLES.items():
            for col_nome, col_info in defn["colunas"].items():
                tipo = col_info["tipo"]
                if tipo.startswith("VARCHAR2"):
                    self.assertIsNotNone(
                        re_varchar.fullmatch(tipo),
                        "Coluna '{}.{}' tem tipo '{}' sem 'CHAR' explicito".format(
                            entidade, col_nome, tipo
                        ),
                    )

    def test_flags_char1_com_ck_sn(self):
        """Garante que toda coluna CHAR(1) possui CK IN ('Y','N') correspondente."""
        for entidade, defn in TABLES.items():
            cks_da_tabela = [ck["expr"] for ck in defn["cks"].values()]
            for col_nome, col_info in defn["colunas"].items():
                if col_info["tipo"] == "CHAR(1)":
                    tem_ck = False
                    for expr in cks_da_tabela:
                        if col_nome in expr and ("'Y'" in expr and "'N'" in expr):
                            tem_ck = True
                            break
                    self.assertTrue(
                        tem_ck,
                        "Coluna flag '{}.{}' CHAR(1) deve possuir CK IN ('Y','N')".format(
                            entidade, col_nome
                        ),
                    )

    def test_triggers_extras_imutabilidade(self):
        """Verifica configuracao de triggers _bu para chaves naturais imutaveis."""
        self.assertIsNotNone(TABLES["environments"]["trigger_bu"])
        self.assertEqual(TABLES["environments"]["trigger_bu"]["coluna_imutavel"], "name")
        self.assertIsNotNone(TABLES["users"]["trigger_bu"])
        self.assertEqual(TABLES["users"]["trigger_bu"]["coluna_imutavel"], "login")

        # Nenhuma outra tabela deve ter trigger_bu
        for ent, defn in TABLES.items():
            if ent not in ("environments", "users"):
                self.assertIsNone(
                    defn["trigger_bu"],
                    "Tabela '{}' nao deve possuir trigger_bu".format(ent),
                )

    def test_colunas_registro_cr006(self):
        """CR-006 (README §10): 15 tabelas com created/updated at/by no fim e CK _upd; auditoria sem."""
        esperado = [
            ("created_at", "DATE", True, "SYSDATE"),
            ("created_by", "VARCHAR2(40 CHAR)", True, None),
            ("updated_at", "DATE", False, None),
            ("updated_by", "VARCHAR2(40 CHAR)", False, None),
        ]
        esquema = names("tbsss_")
        for entidade, defn in TABLES.items():
            cols = list(defn["colunas"].items())
            if entidade in sql_ident.TABLES_WITHOUT_RECORD:
                nomes_cols = [c for c, _ in cols]
                for c in ("created_by", "updated_at", "updated_by"):
                    self.assertNotIn(c, nomes_cols, "{} nao recebe {}".format(entidade, c))
                self.assertNotIn("upd", defn["cks"])
                continue
            obtido = [(n, c["tipo"], c["not_null"], c["default"]) for n, c in cols[-4:]]
            self.assertEqual(obtido, esperado, "Colunas de registro em {}".format(entidade))
            self.assertEqual(defn["cks"]["upd"]["expr"], sql_ident.CK_RECORD_EXPR)
            abrev = defn["abrev"]
            self.assertIn("ck_tbsss_{}_upd".format(abrev), esquema[entidade]["cks"])
        self.assertEqual(sql_ident.TABLES_WITHOUT_RECORD, ("audit", "control"))
        self.assertEqual(
            sum(1 for e in TABLES if "upd" in TABLES[e]["cks"]), 16)

    def test_registro_cr007(self):
        """CR-007: versao do esquema, controle de linha unica, indice unico da ocorrencia, colunas e tamanhos."""
        self.assertIsInstance(sql_ident.SCHEMA_VERSION, int)
        self.assertGreaterEqual(sql_ident.SCHEMA_VERSION, 1)
        ctl = TABLES["control"]
        self.assertEqual(ctl["cks"]["id"]["expr"], "id = 1")
        self.assertEqual(list(ctl["colunas"]), ["id", "schema_version", "version_applied_at", "version_applied_by",
                                                 "purge_owner", "purge_lease_until"])
        esquema = names("tbsss_")
        ocor = esquema["tickets"]["indices"]["ix_tbsss_tck_occur"]
        self.assertTrue(ocor["unico"] and ocor["fbi"])
        self.assertEqual(ocor["expr"], sql_ident.FBI_TCK_OCCUR_EXPR)
        self.assertFalse(esquema["tickets"]["indices"]["ix_tbsss_tck_queue"]["unico"])
        self.assertEqual(esquema["tickets"]["indices"]["ix_tbsss_tck_hist"]["colunas"], ("script_id", "created_at"))
        self.assertEqual(esquema["schedules"]["indices"]["ix_tbsss_sch_next"]["colunas"],
                         ("active", "next_run_at", "id"))
        self.assertIn("'INTERNAL_ERROR'", TABLES["schedules"]["cks"]["pause"]["expr"])
        self.assertEqual(TABLES["tickets"]["colunas"]["process_id"]["tipo"], "NUMBER(10)")
        self.assertEqual(TABLES["agents"]["colunas"]["hostname"]["tipo"], "VARCHAR2(255 CHAR)")
        self.assertEqual(TABLES["agents"]["colunas"]["environments"]["tipo"], "VARCHAR2(1000 CHAR)")
        self.assertIn("critical_config", TABLES["agents"]["colunas"])
        # CR-011: sem hash do script.
        for ent, col in (("scripts", "sha256_homologado"), ("tickets", "arquivo_sha256")):
            self.assertNotIn(col, TABLES[ent]["colunas"])
            self.assertNotIn("sha", TABLES[ent]["cks"])

    def test_readme_10_colunas_iguais_ao_registro(self):
        """README §10 lista exatamente as colunas do registro, na mesma ordem (fonte unica)."""
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(app_dir, "README.md"), "r", encoding="utf-8") as f:
            texto = f.read()
        secao = texto[texto.index("## 10. Modelo de Dados"):texto.index("## 11. Bootstrap")]
        blocos = re.split(r"\n### \d+\. `tbsss_(\w+)`[^\n]*\n", secao)
        lidas = {}
        for i in range(1, len(blocos), 2):
            corpo = blocos[i + 1]
            m = re.search(r"\* \*\*Colunas:\*\*([^\n]*)\n((?:  \*[^\n]*\n)*)", corpo)
            self.assertIsNotNone(m, "Bloco de colunas ausente em {}".format(blocos[i]))
            if m.group(1).strip():
                cols = re.findall(r"`(\w+)(?: [^`]*)?`", m.group(1))
            else:
                cols = re.findall(r"^  \* `(\w+)", m.group(2), re.M)
            lidas[blocos[i]] = cols
        self.assertEqual(list(lidas.keys()), [defn["fisico"] for defn in TABLES.values()])
        for entidade, defn in TABLES.items():
            self.assertEqual(lidas[defn["fisico"]], list(defn["colunas"].keys()),
                             "README §10 diverge do registro em {}".format(entidade))

    def test_colunas_lob_declaradas(self):
        """Verifica catalogacao de colunas LOB (CLOB e, na saida do ticket, BLOB; CR-012)."""
        self.assertEqual(TABLES["schedules"]["colunas_lob"], ("params_json",))
        self.assertEqual(
            TABLES["tickets"]["colunas_lob"],
            ("submitted_params", "log_output"),
        )
        self.assertEqual(TABLES["ticket_output"]["colunas_lob"], ("content",))
        self.assertEqual(TABLES["ticket_output"]["colunas"]["content"]["tipo"], "BLOB")
        for ent, defn in TABLES.items():
            if ent not in ("schedules", "tickets", "ticket_output"):
                self.assertEqual(
                    defn["colunas_lob"],
                    (),
                    "Tabela '{}' nao deve possuir colunas LOB declaradas".format(ent),
                )

    def test_expressoes_fbi_literais(self):
        """Verifica que as constantes de FBI sao strings unicas identicas ao README."""
        # CR-013: colunas simples na frente e o inicio da espera (sem CASE: o Oracle elimina o sort).
        self.assertEqual(FBI_TCK_QUEUE_EXPR,
                         "(status, environment, priority, GREATEST(scheduled_at, created_at), id, script_id)")
        self.assertIn("CASE WHEN status = 'RUNNING' THEN agent_id END", FBI_TCK_RUN_EXPR)

        esquema = names("tbsss_")
        tck_indices = esquema["tickets"]["indices"]
        self.assertIn("ix_tbsss_tck_queue", tck_indices)
        self.assertEqual(tck_indices["ix_tbsss_tck_queue"]["expr"], FBI_TCK_QUEUE_EXPR)
        self.assertTrue(tck_indices["ix_tbsss_tck_queue"]["fbi"])

        self.assertIn("ix_tbsss_tck_run", tck_indices)
        self.assertEqual(tck_indices["ix_tbsss_tck_run"]["expr"], FBI_TCK_RUN_EXPR)
        self.assertTrue(tck_indices["ix_tbsss_tck_run"]["fbi"])

    def test_validadores_owner_prefixo_e_qualificar(self):
        """Testa validacoes de owner, prefixo e qualificacao com casos validos e invalidos."""
        # Casos validos
        self.assertEqual(validate_owner("openrisow"), "openrisow")
        self.assertEqual(validate_owner("OWNER_123"), "OWNER_123")
        self.assertEqual(validate_prefix("tbsss_"), "tbsss_")
        self.assertEqual(validate_prefix("a1_"), "a1_")
        self.assertEqual(qualify("openrisow", "tbsss_tickets"), "openrisow.tbsss_tickets")
        self.assertEqual(
            qualify("openrisow", "tbsss_tickets", prefixo="tbsss_"),
            "openrisow.tbsss_tickets",
        )

        # Casos invalidos em owner
        with self.assertRaises(ValueError):
            validate_owner("1owner")  # comeca com digito
        with self.assertRaises(ValueError):
            validate_owner("owner-invalido!")  # hifen/caractere especial
        with self.assertRaises(ValueError):
            validate_owner("a" * 31)  # excede 30 chars

        # Casos invalidos em prefixo
        with self.assertRaises(ValueError):
            validate_prefix("123456789")  # 9 caracteres excede 8
        with self.assertRaises(ValueError):
            validate_prefix("")  # vazio
        with self.assertRaises(ValueError):
            validate_prefix("tb-sss_")  # caractere especial

        # Casos invalidos em qualificar
        with self.assertRaises(ValueError):
            qualify("owner; DROP TABLE", "tbsss_tickets")
        with self.assertRaises(ValueError):
            qualify("openrisow", "tabela; DROP TABLE")

        # Nao ecoa se valor > 64 caracteres
        valor_longo = "x" * 70
        try:
            validate_owner(valor_longo)
            self.fail("Deveria lancar ValueError")
        except ValueError as e:
            self.assertNotIn(valor_longo, str(e), "Erro nao deve conter valor bruto longo")

    def test_negativo_identificador_31_caracteres_falha(self):
        """Prova deteccao: registro temporario com 31 caracteres faz validacao falhar."""
        # 1. Coluna com 31 caracteres
        reg_col_invalida = copy.deepcopy(TABLES)
        col_31 = "coluna_com_trinta_e_um_chars_xy"  # len = 31
        self.assertEqual(len(col_31), 31)
        reg_col_invalida["environments"]["colunas"][col_31] = {
            "name": col_31,
            "tipo": "VARCHAR2(10 CHAR)",
            "not_null": False,
            "default": None,
        }
        with self.assertRaises(ValueError) as ctx:
            validate_registry("tbsss_", tabelas=reg_col_invalida)
        self.assertIn("excede 30 caracteres", str(ctx.exception))

        # 2. Constraint UK que gera nome com 31 caracteres
        reg_uk_invalida = copy.deepcopy(TABLES)
        # uk_ + tbsss_ (6) + amb (3) + _ (1) = 13. Se sufixo tiver 18 chars -> total 31 chars
        sufixo_18 = "sufixo_com_18_char"  # len = 18
        self.assertEqual(len("uk_tbsss_amb_" + sufixo_18), 31)
        reg_uk_invalida["environments"]["uks"]["invalido"] = {
            "sufixo": sufixo_18,
            "colunas": ("name",),
        }
        with self.assertRaises(ValueError) as ctx:
            validate_registry("tbsss_", tabelas=reg_uk_invalida)
        self.assertIn("excede 30 caracteres", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
