# -*- coding: utf-8 -*-
"""Testes do repo_oracle.scheduler_output (CR-012; README §8.13 e §10, tabela 18).

Sem banco: conexao roteirizada do test_scheduler_queue (SQL, binds, posse e ausencia de COMMIT).
Com SSS_TEST_ORACLE=1: o ciclo real no owner e prefixo do instance/config.ini, com massa propria, e a
leitura pelo repositorio da web (output_get, output_read); tudo removido no fim (cascata do ticket).
"""
from tests.support import _testenv  # noqa: F401

import unittest
from unittest import mock

import db_conn

from repo_oracle import scheduler_output
from repo_oracle.scheduler_output import RepoSchedulerOutput, OutputOffsetMismatch
from tests.unit.persistence.test_scheduler_queue import _Conn, _Error

AGENT = "srv-01"


class TestWithoutDb(unittest.TestCase):

    def setUp(self):
        self.repo = RepoSchedulerOutput("openrisow", "tbsss_")
        # O cursor roteirizado devolve a variavel de saida em lista (formato do RETURNING).
        value = mock.patch.object(db_conn, "output_value", lambda var: var.getvalue()[0])
        value.start()
        self.addCleanup(value.stop)

    def test_iniciar_reinicia_a_propria_ou_inclui_com_posse_do_ticket(self):
        conn = _Conn([("SET content = EMPTY_BLOB()", (1, []))])
        self.assertTrue(self.repo.start(conn, 7, AGENT))
        self.assertEqual(conn.sql("INSERT"), [])
        conn = _Conn([("SET content = EMPTY_BLOB()", (0, [])), ("INSERT INTO", (1, []))])
        self.assertTrue(self.repo.start(conn, 7, AGENT))
        sql, binds = [e for e in conn.executed if "INSERT INTO" in e[0]][0]
        self.assertIn("FROM openrisow.tbsss_tickets t WHERE t.id = :ticket_id AND t.agent_id = :agent_id", sql)
        self.assertIn("NOT EXISTS", sql)
        self.assertIn("EMPTY_BLOB()", sql)
        self.assertEqual((binds["state"], binds["actor"], binds["id"]), ("WRITING", "SYSTEM:srv-01", 501))
        conn = _Conn([("SET content = EMPTY_BLOB()", (0, [])), ("INSERT INTO", (0, []))])
        self.assertFalse(self.repo.start(conn, 7, AGENT))
        self.assertEqual((conn.commits, conn.rollbacks), (0, 0), "sem COMMIT: a fase decide")

    def test_anexar_resultados_e_divergencia(self):
        for value in ("WRITTEN", "ALREADY_WRITTEN", "OWNERSHIP_LOST"):
            conn = _Conn([("DECLARE", (1, [], value))])
            self.assertEqual(self.repo.append_chunk(conn, 7, AGENT, 0, b"PK\x03\x04"), value)
        conn = _Conn([("DECLARE", (1, [], "WRITTEN"))])
        self.repo.append_chunk(conn, 7, AGENT, 1048576, b"x")
        sql, binds = conn.executed[0]
        self.assertIn("FOR UPDATE WAIT 5", sql)
        self.assertIn("DBMS_LOB.APPEND(v_lob, :part)", sql)
        self.assertIn("state = 'WRITING'", sql)
        self.assertEqual((binds["expected_offset"], binds["part"]), (1048576, b"x"))
        conn = _Conn([("DECLARE", _Error("ORA-20003: SAIDA_OFFSET_DIVERGENTE"))])
        with self.assertRaises(OutputOffsetMismatch):
            self.repo.append_chunk(conn, 7, AGENT, 0, b"x")
        for bad in (b"", b"x" * (scheduler_output.PART_MAX + 1)):
            with self.assertRaises(ValueError):
                self.repo.append_chunk(_Conn([]), 7, AGENT, 0, bad)

    def test_concluir_confere_o_tamanho_no_banco(self):
        conn = _Conn([("SET state = 'AVAILABLE'", (1, []))])
        self.assertTrue(self.repo.complete(conn, 7, AGENT, 3, 2048))
        sql, binds = conn.executed[0]
        self.assertIn("DBMS_LOB.GETLENGTH(content) = :size_bytes", sql)
        self.assertIn("updated_by = :actor", sql)
        self.assertFalse(self.repo.complete(_Conn([]), 7, AGENT, 3, 2048))

    def test_registrar_sem_conteudo(self):
        conn = _Conn([("SET state = :state", (1, []))])
        self.assertTrue(self.repo.register_without_content(conn, 7, AGENT, "EXCEEDED", "FILES", 1001))
        self.assertEqual(conn.sql("INSERT"), [])
        conn = _Conn([("SET state = :state", (0, [])), ("INSERT INTO", (1, []))])
        self.assertTrue(self.repo.register_without_content(conn, 7, AGENT, "FAILED", "DEADLINE"))
        sql, binds = [e for e in conn.executed if "INSERT INTO" in e[0]][0]
        self.assertIn(", NULL, SYSDATE", sql, "sem content")
        self.assertEqual((binds["state"], binds["reason"]), ("FAILED", "DEADLINE"))
        for state, reason in (("AVAILABLE", "ERROR"), ("FAILED", "OUTRO")):
            with self.assertRaises(ValueError):
                self.repo.register_without_content(_Conn([]), 7, AGENT, state, reason)

    def test_falhar_gravando_usa_o_indice_de_funcao(self):
        conn = _Conn([("SET state = 'FAILED'", (2, []))])
        self.assertEqual(self.repo.fail_agent_writing(conn, AGENT), 2)
        self.assertIn("(CASE WHEN state = 'WRITING' THEN agent_id END) = :agent_id", conn.executed[0][0])

    def test_situacao(self):
        self.assertEqual(self.repo.output_state(_Conn([("SELECT state", (1, [("AVAILABLE", AGENT)]))]), 7),
                         ("AVAILABLE", AGENT))
        self.assertIsNone(self.repo.output_state(_Conn([]), 7))

    def test_prefixo_e_owner_parametrizados(self):
        repo = RepoSchedulerOutput("outro", "abcdefg_")
        conn = _Conn([("SET content = EMPTY_BLOB()", (1, []))])
        repo.start(conn, 1, AGENT)
        self.assertIn("outro.abcdefg_ticket_output", conn.executed[0][0])
        self.assertNotIn("tbsss_", conn.executed[0][0])


# Processo filho com o driver forcado (o driver e escolhido uma vez por processo): BLOB por TIPO_BLOB.
_CHILD = r'''
import json, sys, warnings
warnings.simplefilter("ignore")
sys.path.insert(0, sys.argv[1])
import sss_config, db_conn
from repo_oracle.scheduler_output import RepoSchedulerOutput
cfg = sss_config.get_config()
cfg = cfg._replace(oracle=cfg.oracle._replace(driver_mode=sys.argv[2]))
seg = sss_config.load_secrets(cfg.secrets.secrets_file, cfg=cfg, role="web")
try:
    conn = db_conn.connect(cfg, seg, "web")
except Exception as e:
    print(json.dumps({"indisponivel": "%s: %s" % (e.__class__.__name__, str(e)[:120])}))
    sys.exit(0)
repo = RepoSchedulerOutput.from_config(cfg)
tid, agente = int(sys.argv[3]), sys.argv[4]
parte = bytes(bytearray(range(256))) * 1200
r = [repo.start(conn, tid, agente)]
conn.commit()
r.append(repo.append_chunk(conn, tid, agente, 0, parte))
conn.commit()
r.append(repo.append_chunk(conn, tid, agente, 0, parte))
r.append(repo.complete(conn, tid, agente, 1, len(parte)))
conn.commit()
print(json.dumps({"candidate": db_conn.get_selection().candidate, "r": r}))
conn.close()
'''


if __name__ == "__main__":
    unittest.main()
