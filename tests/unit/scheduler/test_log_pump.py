# -*- coding: utf-8 -*-
"""Testes do log_pump e do repo_oracle.scheduler_log (README §8.10; AGENTS §4.13; CR-007 R-25; CR-008 R-11).

Sem banco: dubles do repositorio e da conexao. Com SSS_TEST_ORACLE=1: WRITEAPPEND real num ticket proprio
(criado e removido pelo teste) no owner e prefixo do instance/config.ini, com o driver do config e, em
processos separados, com cada combinacao de driver disponivel (Thin, Thick, cx_Oracle).
"""
from tests.support import _testenv  # noqa: F401

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from sss.persistence import db_conn
from sss.scheduler import log_pump
from sss.core import masking
from sss.scheduler.log_pump import MARKER, Pump, Round
from sss.persistence.oracle import scheduler_log
from sss.persistence.oracle.scheduler_log import (WRITTEN, ALREADY_WRITTEN, OWNERSHIP_LOST, LogOffsetMismatch,
                                                  RepoSchedulerLog)

MB_TEXT = "Ação concluída: café ☕ e emoji \U0001F600 \U0001F4A9 ok; ñ ü ß ç ã é\n" * 3
MB = 1024 * 1024
LARGE = 10 * MB


class _FakeClob(object):
    """CLOB de um ticket com o mesmo protocolo do bloco PL/SQL do README §8.10 (unidades UTF-16)."""

    def __init__(self):
        self.text = ""
        self.offset = 0
        self.owner = ("srv-01", "RUNNING")
        self.truncated = "N"
        self.commits = 0
        self._snapshot = None

    def start_tx(self):
        if self._snapshot is None:
            self._snapshot = (self.text, self.offset, self.truncated)

    def commit(self):
        self._snapshot = None
        self.commits += 1

    def rollback(self):
        if self._snapshot is not None:
            self.text, self.offset, self.truncated = self._snapshot
        self._snapshot = None


class _FakeRepo(object):
    """Mesma semantica de RepoSchedulerLog.append_chunk sobre _FakeClob (conn = _FakeConn)."""

    def __init__(self):
        self.calls = []

    def append_chunk(self, conn, ticket_id, agent_id, expected_offset, chunk):
        self.calls.append((ticket_id, expected_offset, chunk))
        conn.count()
        clob = conn.clobs[ticket_id]
        if clob.owner != (agent_id, "RUNNING"):
            return OWNERSHIP_LOST
        clob.start_tx()
        size = log_pump.clob_units(chunk)
        if log_pump.clob_units(clob.text) != clob.offset:
            raise LogOffsetMismatch(ticket_id, expected_offset, size)
        if clob.offset == expected_offset:
            clob.text += chunk
            clob.offset += size
            return WRITTEN
        if clob.offset == expected_offset + size and clob.text.encode("utf-16-le")[2 * expected_offset:] == \
                chunk.encode("utf-16-le"):
            return ALREADY_WRITTEN
        raise LogOffsetMismatch(ticket_id, expected_offset, size)

    def mark_truncated(self, conn, ticket_id, agent_id):
        clob = conn.clobs[ticket_id]
        if clob.owner != (agent_id, "RUNNING"):
            return False
        clob.start_tx()
        clob.truncated = "Y"
        return True


class _FakeConn(object):
    def __init__(self, clobs, clock=None, fail_commit=0):
        self.clobs = clobs
        self.clock = clock
        self.fail_commit = fail_commit
        self.uncertain_commit_persisted = True

    def count(self):
        if self.clock is not None:
            self.clock.advance(1)

    def commit(self):
        if self.fail_commit:
            self.fail_commit -= 1
            if self.uncertain_commit_persisted:
                for c in self.clobs.values():
                    c.commit()
            raise RuntimeError("DPY-4011: connection closed (desfecho desconhecido)")
        for c in self.clobs.values():
            c.commit()

    def rollback(self):
        for c in self.clobs.values():
            c.rollback()


class _Clock(object):
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class _Base(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sss_pump_")
        self.n = 0

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def file(self, content=b""):
        self.n += 1
        path = os.path.join(self.root, "ticket_%d.log" % self.n)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def append_bytes(self, path, data):
        with open(path, "ab") as f:
            f.write(data)

    def pump(self, path, masker=None, cap=LARGE, local_value=LARGE, ticket_id=1):
        return Pump(path, ticket_id, masker or masking.Masker(), cap, local_value)

    def drain(self, pump, conn=None, repo=None):
        """Flush final num CLOB falso e devolve o texto do CLOB."""
        conn = conn or _FakeConn({pump.ticket_id: _FakeClob()})
        repo = repo or _FakeRepo()
        self.assertEqual(log_pump.final_flush(pump, conn, repo, "srv-01"), log_pump.OK)
        return conn.clobs[pump.ticket_id]


class TestReadAndMask(_Base):

    def test_ascii(self):
        path = self.file(b"linha 1\nlinha 2\n")
        b = self.pump(path)
        self.assertEqual(b.collect(), "linha 1\nlinha 2\n")
        self.assertEqual(self.drain(b).text, "linha 1\nlinha 2\n")

    def test_multibyte_cortado_em_todas_as_posicoes(self):
        data = MB_TEXT.encode("utf-8")
        for cutoff in range(len(data) + 1):
            path = self.file(data[:cutoff])
            b = self.pump(path)
            first = b.collect()
            self.append_bytes(path, data[cutoff:])
            second = b.collect(max_bytes_leitura=7)
            clob = self.drain(b)
            self.assertEqual(clob.text, MB_TEXT, "corte em %d" % cutoff)
            self.assertNotIn("�", first + second, "corte em %d" % cutoff)
            self.assertEqual(clob.offset, log_pump.clob_units(MB_TEXT))

    def test_bytes_invalidos_viram_replacement(self):
        b = self.pump(self.file(b"ok \xff\xfe fim\n"))
        self.assertEqual(self.drain(b).text, "ok �� fim\n")

    def test_segredo_cortado_entre_leituras(self):
        m = masking.Masker()
        m.register("SenhaSuperSecreta")
        path = self.file(b"conectando com Senha")
        b = self.pump(path, m)
        b.collect()
        self.append_bytes(path, b"SuperSecreta e pronto\n")
        b.collect()
        text = self.drain(b).text
        self.assertEqual(text, "conectando com **** e pronto\n")

    def test_mascarador_por_ticket_isolado(self):
        snap1 = {"answers": {"token": "tok-ticket-um", "data": "2026-10-13"}, "sensitive": ["token"]}
        snap2 = {"answers": {"token": "tok-ticket-dois"}, "sensitive": ["token"]}
        m1 = log_pump.ticket_masker(["SegredoGlobal1"], "app/Pw1234@db:1521/X", snap1)
        m2 = log_pump.ticket_masker(["SegredoGlobal1"], None, snap2)
        line = b"tok-ticket-um tok-ticket-dois SegredoGlobal1 app/Pw1234@db:1521/X 2026-10-13\n"
        t1 = self.drain(self.pump(self.file(line), m1, ticket_id=1)).text
        t2 = self.drain(self.pump(self.file(line), m2, ticket_id=2)).text
        self.assertEqual(t1, "**** tok-ticket-dois **** **** 2026-10-13\n")
        self.assertEqual(t2, "tok-ticket-um **** **** app/****@db:1521/X 2026-10-13\n")
        self.assertIsNone(masking.MASKER.regex and masking.MASKER.regex.search("tok-ticket-um"),
                          "o mascarador global nao recebe o sensivel do ticket")

    def test_segredo_curto_nao_e_mascarado(self):
        snap = {"answers": {"pin": "123", "senha": "4567"}, "sensitive": ["pin", "senha"]}
        m = log_pump.ticket_masker([], None, snap)
        text = self.drain(self.pump(self.file(b"pin=123 senha=4567\n"), m)).text
        self.assertEqual(text, "pin=123 senha=****\n")

    def test_arquivo_que_cresce_entre_coletas(self):
        path = self.file(b"a\n")
        b = self.pump(path)
        self.assertEqual(b.collect(), "a\n")
        self.assertEqual(b.collect(), "")
        self.append_bytes(path, b"b\n")
        self.assertEqual(b.collect(), "b\n")
        self.assertEqual(b.offset_bytes, 4)
        self.assertEqual(self.drain(b).text, "a\nb\n")

    def test_arquivo_escrito_por_outro_processo_durante_a_coleta(self):
        path = self.file()
        child = subprocess.Popen([sys.executable, "-c",
                                  "import sys,time\nf=open(sys.argv[1],'ab',0)\n"
                                  "for i in range(200):\n    f.write(('linha %04d ação\\n' % i).encode('utf-8'))\n"
                                  "    time.sleep(0.002)\n", path])
        b = self.pump(path)
        collected = []
        while child.poll() is None:
            collected.append(b.collect(max_bytes_leitura=37))
        child.wait()
        text = self.drain(b).text
        expected = "".join("linha %04d ação\n" % i for i in range(200))
        self.assertEqual(text, expected)
        self.assertTrue(any(collected), "houve coleta com o arquivo aberto pelo filho")


class TestLimits(_Base):

    def test_teto_que_cabe_exatamente_sem_marcador(self):
        cap = 2048
        content = ("é" * 1024).encode("utf-8")
        self.assertEqual(len(content), cap)
        b = self.pump(self.file(content), cap=cap)
        b.collect()
        clob = self.drain(b)
        self.assertEqual(clob.text, content.decode("utf-8"))
        self.assertEqual(clob.truncated, "N")
        self.assertFalse(b.truncated)

    def test_teto_excedido_por_um_byte_com_marcador(self):
        cap = 2048
        for content in (("é" * 1024 + "x").encode("utf-8"), ("\U0001F600" * 600).encode("utf-8"),
                         ("a" * 5000).encode("utf-8")):
            b = self.pump(self.file(content), cap=cap)
            with self.assertLogs("sss_scheduler", "WARNING"):
                b.collect(max_bytes_leitura=333)
                b.collect(max_bytes_leitura=MB)
                clob = self.drain(b)
            self.assertTrue(clob.text.endswith(MARKER))
            self.assertEqual(clob.text.count(MARKER), 1)
            self.assertLessEqual(len(clob.text.encode("utf-8")), cap)
            body = clob.text[:-len(MARKER)]
            self.assertTrue(content.decode("utf-8").startswith(body), "corte em fronteira de caractere")
            self.assertGreater(len(body.encode("utf-8")), cap - len(MARKER.encode("utf-8")) - 4)
            self.assertEqual(clob.truncated, "Y")

    def test_aplicar_teto_banco_direto(self):
        cap = 1100
        marker = len(MARKER.encode("utf-8"))
        b = self.pump(self.file(), cap=cap)
        send, truncated = b.apply_db_cap("a" * (cap - marker))
        self.assertEqual((len(send), truncated), (cap - marker, False))
        send, truncated = b.apply_db_cap("b" * marker)
        self.assertEqual((send, truncated), ("", False), "sufixo retido ate a decisao")
        with self.assertLogs("sss_scheduler", "WARNING"):
            send, truncated = b.apply_db_cap("c")
        self.assertEqual((send, truncated), (MARKER, True))
        self.assertEqual(b.apply_db_cap("mais"), ("", True))

    def test_teto_local(self):
        path = self.file(b"x" * 1024)
        b = self.pump(path, local_value=1024)
        self.assertFalse(b.local_exceeded())
        self.append_bytes(path, b"y")
        self.assertTrue(b.local_exceeded())

    def test_blocos_com_tamanho_exato(self):
        self.assertEqual([len(x) for x in log_pump.chunks("a" * 16001)], [8000, 8000, 1])
        self.assertEqual([len(x) for x in log_pump.chunks("a" * 8000)], [8000])
        self.assertEqual(log_pump.chunks(""), [])
        self.assertEqual([len(x) for x in log_pump.chunks("abcdefg", 3)], [3, 3, 1])

    def test_offset_em_unidades_do_clob(self):
        self.assertEqual(log_pump.clob_units("a\U0001F600é"), 4)
        self.assertEqual(log_pump.clob_units("a\U0001F600é", 2), 4)
        self.assertEqual(log_pump.clob_units("a\U0001F600é", 1), 3)

    def test_bomba_com_unidade_de_charset_de_um_byte(self):
        b = Pump(self.file("x\U0001F600y\n".encode("utf-8")), 1, masking.Masker(), LARGE, LARGE,
                  supplementary_unit=1)
        conn = _FakeConn({1: _FakeClob()})
        log_pump.final_flush(b, conn, _FakeRepo(), "srv-01")
        self.assertEqual(b.confirmed_offset_chars, 4)


class TestProtocol(_Base):

    def test_posse_perdida_nao_avanca_o_confirmado(self):
        b = self.pump(self.file(b"texto\n"))
        clob = _FakeClob()
        clob.owner = ("outro", "FAILED")
        conn = _FakeConn({1: clob})
        self.assertEqual(log_pump.final_flush(b, conn, _FakeRepo(), "srv-01"), OWNERSHIP_LOST)
        self.assertEqual((b.confirmed_offset_chars, b.confirmed_bytes), (0, 0))
        self.assertTrue(b.ownership_lost)
        self.assertEqual(b.next_chunk(), ("texto\n", 0), "texto nao descartado como gravado")

    def test_commit_incerto_reconciliado_sem_duplicar(self):
        b = self.pump(self.file(("x" * 8000 + "fim\n").encode("utf-8")))
        conn = _FakeConn({1: _FakeClob()}, fail_commit=1)
        repo = _FakeRepo()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(log_pump.final_flush(b, conn, repo, "srv-01"), log_pump.UNCERTAIN_CONNECTION)
        self.assertEqual(b.confirmed_offset_chars, 0, "nada confirmado antes do COMMIT conhecido")
        self.assertEqual(log_pump.final_flush(b, conn, repo, "srv-01"), log_pump.OK)
        self.assertEqual(conn.clobs[1].text, "x" * 8000 + "fim\n")
        self.assertEqual([c[1] for c in repo.calls], [0, 0, 8000], "mesma operacao reapresentada")

    def test_commit_que_falhou_sem_persistir_regrava(self):
        b = self.pump(self.file(b"abc\n"))
        conn = _FakeConn({1: _FakeClob()}, fail_commit=1)
        conn.uncertain_commit_persisted = False
        repo = _FakeRepo()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(log_pump.final_flush(b, conn, repo, "srv-01"), log_pump.UNCERTAIN_CONNECTION)
        conn.rollback()
        self.assertEqual(log_pump.final_flush(b, conn, repo, "srv-01"), log_pump.OK)
        self.assertEqual(conn.clobs[1].text, "abc\n")

    def test_divergencia_interrompe_sem_alterar(self):
        for clob_text, clob_offset in (("zzz", 3), ("abc", 2)):
            b = self.pump(self.file(b"abc\n"))
            clob = _FakeClob()
            clob.text, clob.offset = clob_text, clob_offset
            with self.assertLogs("sss_scheduler", "ERROR"):
                self.assertEqual(log_pump.final_flush(b, _FakeConn({1: clob}), _FakeRepo(), "srv-01"),
                                 log_pump.INCONSISTENT)
            self.assertEqual((clob.text, clob.offset), (clob_text, clob_offset))
            self.assertTrue(b.stopped)
            self.assertEqual(b.collect(), "", "pump do ticket interrompido")

    def test_orcamento_e_rodizio(self):
        clock = _Clock()
        clobs = dict((t, _FakeClob()) for t in (1, 2, 3))
        conn = _FakeConn(clobs, clock=clock)
        paths = dict((t, self.file()) for t in (1, 2, 3))
        pumps = dict((t, self.pump(paths[t], ticket_id=t)) for t in (1, 2, 3))
        round_value = Round(pumps, clock, budget_s=3)
        served = []
        for _ in range(9):
            for t in (1, 2, 3):
                # Tickets verbosos: 3 blocos novos por rodada (cada envio custa 1 s no relogio simulado).
                self.append_bytes(paths[t], ("%d" % t * 8000 * 3).encode("ascii"))
            res = round_value.run(conn, _FakeRepo(), "srv-01")
            self.assertTrue(res.budget_exhausted)
            served.append(set(res.served))
            clock.advance(100)
        self.assertEqual(len(clobs[1].text) + len(clobs[2].text) + len(clobs[3].text) > 0, True)
        for i in range(len(served) - 1):
            for t in (1, 2, 3):
                self.assertTrue(t in served[i] or t in served[i + 1],
                                "ticket %d sem coleta nas rodadas %d e %d: %s" % (t, i, i + 1, served))
        # O orcamento (3 s, 1 s por bloco) cobre os blocos de um ticket so; ainda assim ha fila acumulada.
        self.assertTrue(any(b.pending() for b in pumps.values()))
        # Lidos e nao confirmados sobrevivem: drenando, cada CLOB tem tudo, sem perda nem duplicacao.
        for t in (1, 2, 3):
            self.assertEqual(log_pump.final_flush(pumps[t], conn, _FakeRepo(), "srv-01"), log_pump.OK)
            self.assertEqual(clobs[t].text, "%d" % t * 8000 * 3 * 9)

    def test_rodada_segue_com_arquivo_ausente(self):
        # Revisao F8.0-F8.2 (A1): um log ilegivel nao para a coleta dos outros tickets.
        clobs = {1: _FakeClob(), 2: _FakeClob()}
        conn = _FakeConn(clobs)
        pumps = {1: self.pump(os.path.join(self.root, "sumiu.log"), ticket_id=1),
                  2: self.pump(self.file(b"ok\n"), ticket_id=2)}
        round_value = Round(pumps, _Clock(), budget_s=100)
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            round_value.run(conn, _FakeRepo(), "srv-01")
            round_value.run(conn, _FakeRepo(), "srv-01")
        self.assertEqual(len([x for x in logs.output if "ilegivel" in x]), 1, "WARN uma vez")
        self.assertTrue(pumps[1].read_error)
        self.assertEqual(log_pump.final_flush(pumps[2], conn, _FakeRepo(), "srv-01"), log_pump.OK)
        self.assertEqual(clobs[2].text, "ok\n")
        self.assertEqual(log_pump.final_flush(pumps[1], conn, _FakeRepo(), "srv-01"), log_pump.OK)
        self.assertEqual(clobs[1].text, "")

    def test_flush_final_le_em_blocos_e_para_ao_truncar(self):
        # Revisao F8.0-F8.2 (M1): arquivo bem maior que o teto nao e lido inteiro para a memoria.
        path = self.file(b"x" * (5 * MB))
        b = self.pump(path, cap=4096)
        with self.assertLogs("sss_scheduler", "WARNING"):
            clob = self.drain(b)
        self.assertLessEqual(b.offset_bytes, log_pump.DEFAULT_READ, "parou de ler no primeiro bloco")
        self.assertTrue(clob.text.endswith(MARKER))
        self.assertLessEqual(len(clob.text.encode("utf-8")), 4096)

    def test_flush_final_sem_truncar_le_tudo_em_blocos(self):
        content = b"".join(("linha ação %06d\n" % i).encode("utf-8") for i in range(150000))
        b = self.pump(self.file(content))
        clob = self.drain(b)
        self.assertGreater(len(content), 2 * log_pump.DEFAULT_READ)
        self.assertEqual(clob.text, content.decode("utf-8"))

    def test_rodada_com_commit_incerto_preserva_e_retoma(self):
        clock = _Clock()
        clobs = {1: _FakeClob()}
        conn = _FakeConn(clobs, clock=clock, fail_commit=1)
        path = self.file(b"a" * 20000)
        pumps = {1: self.pump(path)}
        round_value = Round(pumps, clock, budget_s=100)
        with self.assertLogs("sss_scheduler", "WARNING"):
            res = round_value.run(conn, _FakeRepo(), "srv-01")
        self.assertTrue(res.uncertain_connection)
        res = round_value.run(conn, _FakeRepo(), "srv-01")
        self.assertFalse(res.uncertain_connection)
        self.assertEqual(log_pump.final_flush(pumps[1], conn, _FakeRepo(), "srv-01"), log_pump.OK)
        self.assertEqual(clobs[1].text, "a" * 20000)


class _CursorAppend(object):
    """Duble de cursor: registra binds e simula o resultado ou um erro do bloco PL/SQL."""

    def __init__(self, conn):
        self.conn = conn
        self.inputs = None
        self.rowcount = 0

    def setinputsizes(self, **types):
        self.inputs = types

    def var(self, kind, size=None):
        self.conn.vars.append((kind, size))
        return mock.Mock(getvalue=mock.Mock(return_value=self.conn.result))

    def execute(self, sql, **binds):
        self.conn.executions.append((sql, binds, self.inputs))
        if self.conn.error is not None:
            raise self.conn.error
        self.rowcount = self.conn.rowcount

    def close(self):
        pass


class _ConnAppend(object):
    def __init__(self, result="WRITTEN", error=None, rowcount=1):
        self.result = result
        self.error = error
        self.rowcount = rowcount
        self.vars = []
        self.executions = []

    def cursor(self):
        return _CursorAppend(self)


class TestRepoSchedulerLog(unittest.TestCase):

    def setUp(self):
        self.repo = RepoSchedulerLog("OWN_X", "pfx_")

    def test_bloco_plsql_literal_com_owner_e_prefixo(self):
        conn = _ConnAppend()
        self.assertEqual(self.repo.append_chunk(conn, 7, "srv-01", 0, "abc"), WRITTEN)
        sql, binds, kinds = conn.executions[0]
        # Literal do README §8.10, com o owner e o prefixo da configuracao no lugar de {owner}.tbsss_.
        with open(os.path.join(_testenv.APP_DIR, "README.md"),
                  encoding="utf-8") as f:
            readme = f.read()
        section = readme[readme.index("### 8.10"):readme.index("### 8.11")]
        chunk = section[section.index("```sql\nDECLARE") + len("```sql\n"):]
        chunk = chunk[:chunk.index("\n```")]
        self.assertEqual(sql, chunk.replace("{owner}.tbsss_tickets", "OWN_X.pfx_tickets"))
        self.assertNotIn("tbsss_", sql)
        for snippet in ("FOR UPDATE WAIT 5", "DBMS_LOB.GETLENGTH(v_lob) <> v_offset", "DBMS_LOB.WRITEAPPEND",
                       "DBMS_LOB.COMPARE", "WHEN NO_DATA_FOUND", "RAISE_APPLICATION_ERROR(-20002"):
            self.assertIn(snippet, sql)
        self.assertNotIn("updated_", sql)
        self.assertEqual(set(binds), {"chunk", "ticket_id", "agent_id", "expected_offset", "result"})
        self.assertEqual(kinds, {"chunk": db_conn.get_driver_type(db_conn.TIPO_CLOB)})

    def test_resultados_e_posse_perdida(self):
        for r in (WRITTEN, ALREADY_WRITTEN, OWNERSHIP_LOST):
            self.assertEqual(self.repo.append_chunk(_ConnAppend(result=r), 7, "srv-01", 0, "abc"), r)
        with self.assertRaises(RuntimeError):
            self.repo.append_chunk(_ConnAppend(result=None), 7, "srv-01", 0, "abc")
        with self.assertRaises(ValueError):
            self.repo.append_chunk(_ConnAppend(), 7, "srv-01", 0, "")

    def test_ora_20002_vira_log_offset_inconsistente(self):
        error = Exception("ORA-20002: LOG_OFFSET_DIVERGENTE\nORA-06512: at line 13")
        with self.assertRaises(LogOffsetMismatch):
            self.repo.append_chunk(_ConnAppend(error=error), 7, "srv-01", 0, "abc")
        with self.assertRaises(Exception) as ctx:
            self.repo.append_chunk(_ConnAppend(error=Exception("ORA-00054: resource busy")), 7, "srv-01", 0, "abc")
        self.assertNotIsInstance(ctx.exception, LogOffsetMismatch)

    def test_bind_out_pelos_tres_drivers(self):
        """output_variable/output_value escolhem o tipo VARCHAR de cada combinacao (Thin/Thick: oracledb;
        cx_Oracle: STRING); o resultado lido e o mesmo."""
        oracledb = mock.Mock(__name__="oracledb", DB_TYPE_VARCHAR="ODB_VARCHAR", DB_TYPE_CLOB="ODB_CLOB")
        cx = mock.Mock(__name__="cx_Oracle", STRING="CX_STRING", CLOB="CX_CLOB")
        for candidate, driver, expected, clob in (("thin", oracledb, "ODB_VARCHAR", "ODB_CLOB"),
                                                  ("thick", oracledb, "ODB_VARCHAR", "ODB_CLOB"),
                                                  ("cx_oracle", cx, "CX_STRING", "CX_CLOB")):
            selection = mock.Mock(candidate=candidate)
            conn = _ConnAppend(result=ALREADY_WRITTEN)
            with mock.patch.object(db_conn, "_DRIVER_INITIALIZED", driver), \
                    mock.patch.object(db_conn, "_DRIVER_SELECTION", selection):
                self.assertEqual(self.repo.append_chunk(conn, 7, "srv-01", 3, "abc"), ALREADY_WRITTEN, candidate)
            self.assertEqual(conn.vars, [(expected, 20)], candidate)
            self.assertEqual(conn.executions[0][2], {"chunk": clob}, candidate)

    def test_marcar_truncado(self):
        conn = _ConnAppend(rowcount=1)
        self.assertTrue(self.repo.mark_truncated(conn, 7, "srv-01"))
        sql = conn.executions[0][0]
        self.assertIn("log_truncated = 'Y'", sql)
        self.assertIn("OWN_X.pfx_tickets", sql)
        self.assertNotIn("updated_", sql)
        self.assertFalse(self.repo.mark_truncated(_ConnAppend(rowcount=0), 7, "srv-01"))

    def test_modulos_sem_commit_nem_sleep(self):
        for mod in (scheduler_log, log_pump):
            with open(mod.__file__, encoding="utf-8") as f:
                source = f.read()
            self.assertFalse("time.sleep" in source, mod.__name__)
        with open(scheduler_log.__file__, encoding="utf-8") as f:
            self.assertFalse(".commit(" in f.read(), "COMMIT e do chamador")


# -----------------------------------------------------------------------------
# Oracle real (SSS_TEST_ORACLE=1)
# -----------------------------------------------------------------------------

_CHILD = r'''
import json, os, sys, warnings
warnings.simplefilter("ignore")
sys.path[:0] = [sys.argv[1], os.path.join(os.path.dirname(sys.argv[1]), "src")]
from sss.persistence import db_conn
from sss.config import sss_config
from sss.persistence.oracle.scheduler_log import RepoSchedulerLog
cfg = sss_config.get_config()
cfg = cfg._replace(oracle=cfg.oracle._replace(driver_mode=sys.argv[2]))
seg = sss_config.load_secrets(cfg.secrets.secrets_file, cfg=cfg, role="web")
try:
    conn = db_conn.connect(cfg, seg, "web")
except Exception as e:
    print(json.dumps({"indisponivel": "%s: %s" % (e.__class__.__name__, str(e)[:120])}))
    sys.exit(0)
repo = RepoSchedulerLog.from_config(cfg)
ticket_id, agente, offset, bloco = int(sys.argv[3]), sys.argv[4], int(sys.argv[5]), sys.argv[6]
r1 = repo.append_chunk(conn, ticket_id, agente, offset, bloco)
conn.commit()
r2 = repo.append_chunk(conn, ticket_id, agente, offset, bloco)
conn.commit()
print(json.dumps({"candidate": db_conn.get_selection().candidate, "r": [r1, r2]}))
conn.close()
'''


if __name__ == "__main__":
    unittest.main()
