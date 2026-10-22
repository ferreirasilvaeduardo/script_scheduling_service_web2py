# -*- coding: utf-8 -*-
"""Testes do log_pump e do repo_oracle.scheduler_log (README §8.10; AGENTS §4.13; CR-007 R-25; CR-008 R-11).

Sem banco: dubles do repositorio e da conexao. Com SSS_TEST_ORACLE=1: WRITEAPPEND real num ticket proprio
(criado e removido pelo teste) no owner e prefixo do instance/config.ini, com o driver do config e, em
processos separados, com cada combinacao de driver disponivel (Thin, Thick, cx_Oracle).
"""
import _testenv  # noqa: F401

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import db_conn
import log_pump
import masking
from log_pump import MARKER, Pump, Round
from repo_oracle import scheduler_log
from repo_oracle.scheduler_log import (WRITTEN, ALREADY_WRITTEN, OWNERSHIP_LOST, LogOffsetMismatch,
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

    def append_chunk(self, conn, ticket_id, agente_id, offset_esperado, bloco):
        self.calls.append((ticket_id, offset_esperado, bloco))
        conn.count()
        clob = conn.clobs[ticket_id]
        if clob.owner != (agente_id, "RUNNING"):
            return OWNERSHIP_LOST
        clob.start_tx()
        tam = log_pump.clob_units(bloco)
        if log_pump.clob_units(clob.text) != clob.offset:
            raise LogOffsetMismatch(ticket_id, offset_esperado, tam)
        if clob.offset == offset_esperado:
            clob.text += bloco
            clob.offset += tam
            return WRITTEN
        if clob.offset == offset_esperado + tam and clob.text.encode("utf-16-le")[2 * offset_esperado:] == \
                bloco.encode("utf-16-le"):
            return ALREADY_WRITTEN
        raise LogOffsetMismatch(ticket_id, offset_esperado, tam)

    def mark_truncated(self, conn, ticket_id, agente_id):
        clob = conn.clobs[ticket_id]
        if clob.owner != (agente_id, "RUNNING"):
            return False
        clob.start_tx()
        clob.truncated = "Y"
        return True


class _FakeConn(object):
    def __init__(self, clobs, relogio=None, falhar_commit=0):
        self.clobs = clobs
        self.clock = relogio
        self.fail_commit = falhar_commit
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

    def file(self, conteudo=b""):
        self.n += 1
        caminho = os.path.join(self.root, "ticket_%d.log" % self.n)
        with open(caminho, "wb") as f:
            f.write(conteudo)
        return caminho

    def append_bytes(self, caminho, dados):
        with open(caminho, "ab") as f:
            f.write(dados)

    def pump(self, caminho, mascarador=None, teto=LARGE, local=LARGE, ticket_id=1):
        return Pump(caminho, ticket_id, mascarador or masking.Masker(), teto, local)

    def drain(self, bomba, conn=None, repo=None):
        """Flush final num CLOB falso e devolve o texto do CLOB."""
        conn = conn or _FakeConn({bomba.ticket_id: _FakeClob()})
        repo = repo or _FakeRepo()
        self.assertEqual(log_pump.final_flush(bomba, conn, repo, "srv-01"), log_pump.OK)
        return conn.clobs[bomba.ticket_id]


class TestReadAndMask(_Base):

    def test_ascii(self):
        caminho = self.file(b"linha 1\nlinha 2\n")
        b = self.pump(caminho)
        self.assertEqual(b.collect(), "linha 1\nlinha 2\n")
        self.assertEqual(self.drain(b).text, "linha 1\nlinha 2\n")

    def test_multibyte_cortado_em_todas_as_posicoes(self):
        dados = MB_TEXT.encode("utf-8")
        for corte in range(len(dados) + 1):
            caminho = self.file(dados[:corte])
            b = self.pump(caminho)
            primeiro = b.collect()
            self.append_bytes(caminho, dados[corte:])
            segundo = b.collect(max_bytes_leitura=7)
            clob = self.drain(b)
            self.assertEqual(clob.text, MB_TEXT, "corte em %d" % corte)
            self.assertNotIn("�", primeiro + segundo, "corte em %d" % corte)
            self.assertEqual(clob.offset, log_pump.clob_units(MB_TEXT))

    def test_bytes_invalidos_viram_replacement(self):
        b = self.pump(self.file(b"ok \xff\xfe fim\n"))
        self.assertEqual(self.drain(b).text, "ok �� fim\n")

    def test_segredo_cortado_entre_leituras(self):
        m = masking.Masker()
        m.register("SenhaSuperSecreta")
        caminho = self.file(b"conectando com Senha")
        b = self.pump(caminho, m)
        b.collect()
        self.append_bytes(caminho, b"SuperSecreta e pronto\n")
        b.collect()
        texto = self.drain(b).text
        self.assertEqual(texto, "conectando com **** e pronto\n")

    def test_mascarador_por_ticket_isolado(self):
        snap1 = {"answers": {"token": "tok-ticket-um", "data": "2026-10-13"}, "sensitive": ["token"]}
        snap2 = {"answers": {"token": "tok-ticket-dois"}, "sensitive": ["token"]}
        m1 = log_pump.ticket_masker(["SegredoGlobal1"], "app/Pw1234@db:1521/X", snap1)
        m2 = log_pump.ticket_masker(["SegredoGlobal1"], None, snap2)
        linha = b"tok-ticket-um tok-ticket-dois SegredoGlobal1 app/Pw1234@db:1521/X 2026-10-13\n"
        t1 = self.drain(self.pump(self.file(linha), m1, ticket_id=1)).text
        t2 = self.drain(self.pump(self.file(linha), m2, ticket_id=2)).text
        self.assertEqual(t1, "**** tok-ticket-dois **** **** 2026-10-13\n")
        self.assertEqual(t2, "tok-ticket-um **** **** app/****@db:1521/X 2026-10-13\n")
        self.assertIsNone(masking.MASKER.regex and masking.MASKER.regex.search("tok-ticket-um"),
                          "o mascarador global nao recebe o sensivel do ticket")

    def test_segredo_curto_nao_e_mascarado(self):
        snap = {"answers": {"pin": "123", "senha": "4567"}, "sensitive": ["pin", "senha"]}
        m = log_pump.ticket_masker([], None, snap)
        texto = self.drain(self.pump(self.file(b"pin=123 senha=4567\n"), m)).text
        self.assertEqual(texto, "pin=123 senha=****\n")

    def test_arquivo_que_cresce_entre_coletas(self):
        caminho = self.file(b"a\n")
        b = self.pump(caminho)
        self.assertEqual(b.collect(), "a\n")
        self.assertEqual(b.collect(), "")
        self.append_bytes(caminho, b"b\n")
        self.assertEqual(b.collect(), "b\n")
        self.assertEqual(b.offset_bytes, 4)
        self.assertEqual(self.drain(b).text, "a\nb\n")

    def test_arquivo_escrito_por_outro_processo_durante_a_coleta(self):
        caminho = self.file()
        filho = subprocess.Popen([sys.executable, "-c",
                                  "import sys,time\nf=open(sys.argv[1],'ab',0)\n"
                                  "for i in range(200):\n    f.write(('linha %04d ação\\n' % i).encode('utf-8'))\n"
                                  "    time.sleep(0.002)\n", caminho])
        b = self.pump(caminho)
        coletado = []
        while filho.poll() is None:
            coletado.append(b.collect(max_bytes_leitura=37))
        filho.wait()
        texto = self.drain(b).text
        esperado = "".join("linha %04d ação\n" % i for i in range(200))
        self.assertEqual(texto, esperado)
        self.assertTrue(any(coletado), "houve coleta com o arquivo aberto pelo filho")


class TestLimits(_Base):

    def test_teto_que_cabe_exatamente_sem_marcador(self):
        teto = 2048
        conteudo = ("é" * 1024).encode("utf-8")
        self.assertEqual(len(conteudo), teto)
        b = self.pump(self.file(conteudo), teto=teto)
        b.collect()
        clob = self.drain(b)
        self.assertEqual(clob.text, conteudo.decode("utf-8"))
        self.assertEqual(clob.truncated, "N")
        self.assertFalse(b.truncated)

    def test_teto_excedido_por_um_byte_com_marcador(self):
        teto = 2048
        for conteudo in (("é" * 1024 + "x").encode("utf-8"), ("\U0001F600" * 600).encode("utf-8"),
                         ("a" * 5000).encode("utf-8")):
            b = self.pump(self.file(conteudo), teto=teto)
            with self.assertLogs("sss_scheduler", "WARNING"):
                b.collect(max_bytes_leitura=333)
                b.collect(max_bytes_leitura=MB)
                clob = self.drain(b)
            self.assertTrue(clob.text.endswith(MARKER))
            self.assertEqual(clob.text.count(MARKER), 1)
            self.assertLessEqual(len(clob.text.encode("utf-8")), teto)
            corpo = clob.text[:-len(MARKER)]
            self.assertTrue(conteudo.decode("utf-8").startswith(corpo), "corte em fronteira de caractere")
            self.assertGreater(len(corpo.encode("utf-8")), teto - len(MARKER.encode("utf-8")) - 4)
            self.assertEqual(clob.truncated, "Y")

    def test_aplicar_teto_banco_direto(self):
        teto = 1100
        marcador = len(MARKER.encode("utf-8"))
        b = self.pump(self.file(), teto=teto)
        enviar, truncou = b.apply_db_cap("a" * (teto - marcador))
        self.assertEqual((len(enviar), truncou), (teto - marcador, False))
        enviar, truncou = b.apply_db_cap("b" * marcador)
        self.assertEqual((enviar, truncou), ("", False), "sufixo retido ate a decisao")
        with self.assertLogs("sss_scheduler", "WARNING"):
            enviar, truncou = b.apply_db_cap("c")
        self.assertEqual((enviar, truncou), (MARKER, True))
        self.assertEqual(b.apply_db_cap("mais"), ("", True))

    def test_teto_local(self):
        caminho = self.file(b"x" * 1024)
        b = self.pump(caminho, local=1024)
        self.assertFalse(b.local_exceeded())
        self.append_bytes(caminho, b"y")
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
                  unidade_suplementar=1)
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
        conn = _FakeConn({1: _FakeClob()}, falhar_commit=1)
        repo = _FakeRepo()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(log_pump.final_flush(b, conn, repo, "srv-01"), log_pump.UNCERTAIN_CONNECTION)
        self.assertEqual(b.confirmed_offset_chars, 0, "nada confirmado antes do COMMIT conhecido")
        self.assertEqual(log_pump.final_flush(b, conn, repo, "srv-01"), log_pump.OK)
        self.assertEqual(conn.clobs[1].text, "x" * 8000 + "fim\n")
        self.assertEqual([c[1] for c in repo.calls], [0, 0, 8000], "mesma operacao reapresentada")

    def test_commit_que_falhou_sem_persistir_regrava(self):
        b = self.pump(self.file(b"abc\n"))
        conn = _FakeConn({1: _FakeClob()}, falhar_commit=1)
        conn.uncertain_commit_persisted = False
        repo = _FakeRepo()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(log_pump.final_flush(b, conn, repo, "srv-01"), log_pump.UNCERTAIN_CONNECTION)
        conn.rollback()
        self.assertEqual(log_pump.final_flush(b, conn, repo, "srv-01"), log_pump.OK)
        self.assertEqual(conn.clobs[1].text, "abc\n")

    def test_divergencia_interrompe_sem_alterar(self):
        for clob_texto, clob_offset in (("zzz", 3), ("abc", 2)):
            b = self.pump(self.file(b"abc\n"))
            clob = _FakeClob()
            clob.text, clob.offset = clob_texto, clob_offset
            with self.assertLogs("sss_scheduler", "ERROR"):
                self.assertEqual(log_pump.final_flush(b, _FakeConn({1: clob}), _FakeRepo(), "srv-01"),
                                 log_pump.INCONSISTENT)
            self.assertEqual((clob.text, clob.offset), (clob_texto, clob_offset))
            self.assertTrue(b.stopped)
            self.assertEqual(b.collect(), "", "pump do ticket interrompido")

    def test_orcamento_e_rodizio(self):
        relogio = _Clock()
        clobs = dict((t, _FakeClob()) for t in (1, 2, 3))
        conn = _FakeConn(clobs, relogio=relogio)
        caminhos = dict((t, self.file()) for t in (1, 2, 3))
        bombas = dict((t, self.pump(caminhos[t], ticket_id=t)) for t in (1, 2, 3))
        rodada = Round(bombas, relogio, orcamento_s=3)
        atendidos = []
        for _ in range(9):
            for t in (1, 2, 3):
                # Tickets verbosos: 3 blocos novos por rodada (cada envio custa 1 s no relogio simulado).
                self.append_bytes(caminhos[t], ("%d" % t * 8000 * 3).encode("ascii"))
            res = rodada.run(conn, _FakeRepo(), "srv-01")
            self.assertTrue(res.budget_exhausted)
            atendidos.append(set(res.served))
            relogio.advance(100)
        self.assertEqual(len(clobs[1].text) + len(clobs[2].text) + len(clobs[3].text) > 0, True)
        for i in range(len(atendidos) - 1):
            for t in (1, 2, 3):
                self.assertTrue(t in atendidos[i] or t in atendidos[i + 1],
                                "ticket %d sem coleta nas rodadas %d e %d: %s" % (t, i, i + 1, atendidos))
        # O orcamento (3 s, 1 s por bloco) cobre os blocos de um ticket so; ainda assim ha fila acumulada.
        self.assertTrue(any(b.pending() for b in bombas.values()))
        # Lidos e nao confirmados sobrevivem: drenando, cada CLOB tem tudo, sem perda nem duplicacao.
        for t in (1, 2, 3):
            self.assertEqual(log_pump.final_flush(bombas[t], conn, _FakeRepo(), "srv-01"), log_pump.OK)
            self.assertEqual(clobs[t].text, "%d" % t * 8000 * 3 * 9)

    def test_rodada_segue_com_arquivo_ausente(self):
        # Revisao F8.0-F8.2 (A1): um log ilegivel nao para a coleta dos outros tickets.
        clobs = {1: _FakeClob(), 2: _FakeClob()}
        conn = _FakeConn(clobs)
        bombas = {1: self.pump(os.path.join(self.root, "sumiu.log"), ticket_id=1),
                  2: self.pump(self.file(b"ok\n"), ticket_id=2)}
        rodada = Round(bombas, _Clock(), orcamento_s=100)
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            rodada.run(conn, _FakeRepo(), "srv-01")
            rodada.run(conn, _FakeRepo(), "srv-01")
        self.assertEqual(len([x for x in logs.output if "ilegivel" in x]), 1, "WARN uma vez")
        self.assertTrue(bombas[1].read_error)
        self.assertEqual(log_pump.final_flush(bombas[2], conn, _FakeRepo(), "srv-01"), log_pump.OK)
        self.assertEqual(clobs[2].text, "ok\n")
        self.assertEqual(log_pump.final_flush(bombas[1], conn, _FakeRepo(), "srv-01"), log_pump.OK)
        self.assertEqual(clobs[1].text, "")

    def test_flush_final_le_em_blocos_e_para_ao_truncar(self):
        # Revisao F8.0-F8.2 (M1): arquivo bem maior que o teto nao e lido inteiro para a memoria.
        caminho = self.file(b"x" * (5 * MB))
        b = self.pump(caminho, teto=4096)
        with self.assertLogs("sss_scheduler", "WARNING"):
            clob = self.drain(b)
        self.assertLessEqual(b.offset_bytes, log_pump.DEFAULT_READ, "parou de ler no primeiro bloco")
        self.assertTrue(clob.text.endswith(MARKER))
        self.assertLessEqual(len(clob.text.encode("utf-8")), 4096)

    def test_flush_final_sem_truncar_le_tudo_em_blocos(self):
        conteudo = b"".join(("linha ação %06d\n" % i).encode("utf-8") for i in range(150000))
        b = self.pump(self.file(conteudo))
        clob = self.drain(b)
        self.assertGreater(len(conteudo), 2 * log_pump.DEFAULT_READ)
        self.assertEqual(clob.text, conteudo.decode("utf-8"))

    def test_rodada_com_commit_incerto_preserva_e_retoma(self):
        relogio = _Clock()
        clobs = {1: _FakeClob()}
        conn = _FakeConn(clobs, relogio=relogio, falhar_commit=1)
        caminho = self.file(b"a" * 20000)
        bombas = {1: self.pump(caminho)}
        rodada = Round(bombas, relogio, orcamento_s=100)
        with self.assertLogs("sss_scheduler", "WARNING"):
            res = rodada.run(conn, _FakeRepo(), "srv-01")
        self.assertTrue(res.uncertain_connection)
        res = rodada.run(conn, _FakeRepo(), "srv-01")
        self.assertFalse(res.uncertain_connection)
        self.assertEqual(log_pump.final_flush(bombas[1], conn, _FakeRepo(), "srv-01"), log_pump.OK)
        self.assertEqual(clobs[1].text, "a" * 20000)


class _CursorAppend(object):
    """Duble de cursor: registra binds e simula o resultado ou um erro do bloco PL/SQL."""

    def __init__(self, conn):
        self.conn = conn
        self.inputs = None
        self.rowcount = 0

    def setinputsizes(self, **tipos):
        self.inputs = tipos

    def var(self, tipo, size=None):
        self.conn.vars.append((tipo, size))
        return mock.Mock(getvalue=mock.Mock(return_value=self.conn.result))

    def execute(self, sql, **binds):
        self.conn.executions.append((sql, binds, self.inputs))
        if self.conn.error is not None:
            raise self.conn.error
        self.rowcount = self.conn.rowcount

    def close(self):
        pass


class _ConnAppend(object):
    def __init__(self, resultado="WRITTEN", erro=None, rowcount=1):
        self.result = resultado
        self.error = erro
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
        sql, binds, tipos = conn.executions[0]
        # Literal do README §8.10, com o owner e o prefixo da configuracao no lugar de {owner}.tbsss_.
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md"),
                  encoding="utf-8") as f:
            readme = f.read()
        secao = readme[readme.index("### 8.10"):readme.index("### 8.11")]
        bloco = secao[secao.index("```sql\nDECLARE") + len("```sql\n"):]
        bloco = bloco[:bloco.index("\n```")]
        self.assertEqual(sql, bloco.replace("{owner}.tbsss_tickets", "OWN_X.pfx_tickets"))
        self.assertNotIn("tbsss_", sql)
        for trecho in ("FOR UPDATE WAIT 5", "DBMS_LOB.GETLENGTH(v_lob) <> v_offset", "DBMS_LOB.WRITEAPPEND",
                       "DBMS_LOB.COMPARE", "WHEN NO_DATA_FOUND", "RAISE_APPLICATION_ERROR(-20002"):
            self.assertIn(trecho, sql)
        self.assertNotIn("updated_", sql)
        self.assertEqual(set(binds), {"chunk", "ticket_id", "agent_id", "expected_offset", "result"})
        self.assertEqual(tipos, {"chunk": db_conn.get_driver_type(db_conn.TIPO_CLOB)})

    def test_resultados_e_posse_perdida(self):
        for r in (WRITTEN, ALREADY_WRITTEN, OWNERSHIP_LOST):
            self.assertEqual(self.repo.append_chunk(_ConnAppend(resultado=r), 7, "srv-01", 0, "abc"), r)
        with self.assertRaises(RuntimeError):
            self.repo.append_chunk(_ConnAppend(resultado=None), 7, "srv-01", 0, "abc")
        with self.assertRaises(ValueError):
            self.repo.append_chunk(_ConnAppend(), 7, "srv-01", 0, "")

    def test_ora_20002_vira_log_offset_inconsistente(self):
        erro = Exception("ORA-20002: LOG_OFFSET_DIVERGENTE\nORA-06512: at line 13")
        with self.assertRaises(LogOffsetMismatch):
            self.repo.append_chunk(_ConnAppend(erro=erro), 7, "srv-01", 0, "abc")
        with self.assertRaises(Exception) as ctx:
            self.repo.append_chunk(_ConnAppend(erro=Exception("ORA-00054: resource busy")), 7, "srv-01", 0, "abc")
        self.assertNotIsInstance(ctx.exception, LogOffsetMismatch)

    def test_bind_out_pelos_tres_drivers(self):
        """variavel_saida/valor_saida escolhem o tipo VARCHAR de cada combinacao (Thin/Thick: oracledb;
        cx_Oracle: STRING); o resultado lido e o mesmo."""
        oracledb = mock.Mock(__name__="oracledb", DB_TYPE_VARCHAR="ODB_VARCHAR", DB_TYPE_CLOB="ODB_CLOB")
        cx = mock.Mock(__name__="cx_Oracle", STRING="CX_STRING", CLOB="CX_CLOB")
        for candidato, driver, esperado, clob in (("thin", oracledb, "ODB_VARCHAR", "ODB_CLOB"),
                                                  ("thick", oracledb, "ODB_VARCHAR", "ODB_CLOB"),
                                                  ("cx_oracle", cx, "CX_STRING", "CX_CLOB")):
            selecao = mock.Mock(candidate=candidato)
            conn = _ConnAppend(resultado=ALREADY_WRITTEN)
            with mock.patch.object(db_conn, "_DRIVER_INITIALIZED", driver), \
                    mock.patch.object(db_conn, "_DRIVER_SELECTION", selecao):
                self.assertEqual(self.repo.append_chunk(conn, 7, "srv-01", 3, "abc"), ALREADY_WRITTEN, candidato)
            self.assertEqual(conn.vars, [(esperado, 20)], candidato)
            self.assertEqual(conn.executions[0][2], {"chunk": clob}, candidato)

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
                fonte = f.read()
            self.assertFalse("time.sleep" in fonte, mod.__name__)
        with open(scheduler_log.__file__, encoding="utf-8") as f:
            self.assertFalse(".commit(" in f.read(), "COMMIT e do chamador")


# -----------------------------------------------------------------------------
# Oracle real (SSS_TEST_ORACLE=1)
# -----------------------------------------------------------------------------

_CHILD = r'''
import json, sys, warnings
warnings.simplefilter("ignore")
sys.path.insert(0, sys.argv[1])
import sss_config, db_conn
from repo_oracle.scheduler_log import RepoSchedulerLog
cfg = sss_config.get_config()
cfg = cfg._replace(oracle=cfg.oracle._replace(driver_mode=sys.argv[2]))
seg = sss_config.load_secrets(cfg.secrets.secrets_file, cfg=cfg, papel="web")
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


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestSchedulerLogOracle(unittest.TestCase):
    """WRITEAPPEND real num ticket proprio (modo compartilhado ou descartavel), limpo no tearDown."""

    AGENT = "tst-pump-01"

    @classmethod
    def setUpClass(cls):
        import test_repo_contract as trc
        cls.trc = trc
        cls.contrato = trc._OracleContract
        cls.contrato.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.contrato.tearDownClass.__func__(cls)

    def setUp(self):
        self.contrato.setUp(self)
        self._fixtures = self.trc._Fixtures(self.obter_repo)
        c = self._fixtures.scenario()
        self.ticket_id = self._fixtures.ticket(actor="teste", script_id=c["scr"]["id"], environment=c["amb1"]["name"],
                                            requested_by=c["login"])
        self.catalog = self.obter_repo("catalog")
        self.repo = RepoSchedulerLog(self.catalog._owner, self.catalog._prefixo)
        self.tck = self.catalog.qualify_table("tickets")
        conn = self.catalog._obter_conexao()
        try:
            self.unit = self.repo.supplementary_unit(conn)
        finally:
            conn.close()
        # Estado que o claim (F8.3) deixa: RUNNING deste agente, CLOB vazio e offset 0.
        self._sql("UPDATE " + self.tck + " SET status = 'RUNNING', agent_id = :a, started_at = SYSDATE, "
                  "heartbeat_at = SYSDATE, log_output = EMPTY_CLOB(), log_offset_chars = 0 WHERE id = :id",
                  a=self.AGENT, id=self.ticket_id)

    def tearDown(self):
        self.contrato.tearDown(self)

    def obter_repo(self, nome):
        return self.contrato.obter_repo(self, nome)

    def _clean_fixtures(self):
        return self.contrato._clean_fixtures(self)

    def _sql(self, sql, **binds):
        conn = self.catalog._obter_conexao()
        try:
            cur = conn.cursor()
            cur.execute(sql, **binds)
            conn.commit()
        finally:
            conn.close()

    def _as_db(self, texto):
        """O texto como o charset do banco o guarda (caractere fora dele vira o de substituicao)."""
        conn = self.catalog._obter_conexao()
        try:
            cur = conn.cursor()
            db_conn.set_input_types(cur, x=db_conn.TIPO_CLOB)
            cur.execute("SELECT TO_CLOB(:x) FROM DUAL", x=texto)
            return cur.fetchone()[0].read()
        finally:
            conn.close()

    def _state(self):
        conn = self.catalog._obter_conexao()
        try:
            cur = conn.cursor()
            cur.execute("SELECT log_output, log_offset_chars, log_truncated FROM " + self.tck + " WHERE id = :id",
                        id=self.ticket_id)
            lob, off, trunc = cur.fetchone()
            return (lob.read() if lob is not None and lob.size() else ""), int(off), trunc
        finally:
            conn.close()

    def test_append_idempotente_rollback_e_divergencia(self):
        conn = self.catalog._obter_conexao()
        try:
            bloco = "ação \U0001F600 linha 1\n"
            unidades = log_pump.clob_units(bloco, self.unit)
            guardado = self._as_db(bloco)
            # Rollback antes do primeiro COMMIT: a nova tentativa grava (WRITTEN).
            self.assertEqual(self.repo.append_chunk(conn, self.ticket_id, self.AGENT, 0, bloco), WRITTEN)
            conn.rollback()
            self.assertEqual(self.repo.append_chunk(conn, self.ticket_id, self.AGENT, 0, bloco), WRITTEN)
            conn.commit()
            # Mesma operacao depois do COMMIT: ALREADY_WRITTEN, sem segundo WRITEAPPEND.
            self.assertEqual(self.repo.append_chunk(conn, self.ticket_id, self.AGENT, 0, bloco), ALREADY_WRITTEN)
            conn.commit()
            self.assertEqual(self._state(), (guardado, unidades, "N"))
            # Offset divergente e conteudo diferente: LogOffsetMismatch sem alterar o CLOB.
            for offset, outro in ((unidades + 5, "x"), (0, "ação \U0001F600 linha 2\n"), (1, bloco)):
                with self.assertRaises(LogOffsetMismatch):
                    self.repo.append_chunk(conn, self.ticket_id, self.AGENT, offset, outro)
                conn.rollback()
            self.assertEqual(self._state(), (guardado, unidades, "N"))
            # Outro agente: OWNERSHIP_LOST.
            self.assertEqual(self.repo.append_chunk(conn, self.ticket_id, "outro-agente", unidades, "z"), OWNERSHIP_LOST)
            conn.rollback()
            self.assertTrue(self.repo.mark_truncated(conn, self.ticket_id, self.AGENT))
            conn.commit()
            self.assertEqual(self._state()[2], "Y")
        finally:
            conn.close()

    def test_bomba_completa_mascarada_uma_vez(self):
        raiz = tempfile.mkdtemp(prefix="sss_pump_ora_")
        self.addCleanup(shutil.rmtree, raiz, True)
        caminho = os.path.join(raiz, "ticket.log")
        linhas = "".join("linha %05d ação \U0001F600 senha=SegredoDoTicket\n" % i for i in range(700))
        with open(caminho, "wb") as f:
            f.write(linhas.encode("utf-8"))
        m = log_pump.ticket_masker(["SegredoDoTicket"])
        b = Pump(caminho, self.ticket_id, m, 5 * MB, 50 * MB, unidade_suplementar=self.unit)
        conn = self.catalog._obter_conexao()
        try:
            self.assertEqual(log_pump.final_flush(b, conn, self.repo, self.AGENT), log_pump.OK)
        finally:
            conn.close()
        esperado = linhas.replace("SegredoDoTicket", "****")
        texto, offset, _trunc = self._state()
        self.assertEqual(texto, self._as_db(esperado))
        self.assertEqual(texto.count("****"), 700)
        self.assertNotIn("SegredoDoTicket", texto)
        self.assertEqual(offset, log_pump.clob_units(esperado, self.unit))
        self.assertGreater(len(esperado), 8000, "mais de um bloco")

    def test_combinacoes_de_driver(self):
        modulos = os.path.dirname(os.path.abspath(log_pump.__file__))
        offset = 0
        resultados = {}
        for modo in ("thin", "thick", "cx_oracle"):
            bloco = "driver %s ação \U0001F600\n" % modo
            p = subprocess.run([sys.executable, "-c", _CHILD, modulos, modo, str(self.ticket_id), self.AGENT,
                                str(offset), bloco], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=180, cwd=os.path.dirname(modulos),
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            saida_txt = p.stdout.decode("utf-8", "replace")
            linhas = [x for x in saida_txt.splitlines() if x.startswith("{")]
            self.assertTrue(linhas, "%s: %s" % (modo, p.stderr.decode("utf-8", "replace")[-500:]))
            saida = json.loads(linhas[-1])
            resultados[modo] = saida
            if "indisponivel" in saida:
                continue
            self.assertEqual((saida["candidate"], saida["r"]), (modo, [WRITTEN, ALREADY_WRITTEN]), modo)
            offset += log_pump.clob_units(bloco, self.unit)
        print("\n[log_pump] combinacoes de driver: %s" % json.dumps(resultados, ensure_ascii=False))
        texto, off, _trunc = self._state()
        esperado = "".join("driver %s ação \U0001F600\n" % m for m in ("thin", "thick", "cx_oracle")
                           if "indisponivel" not in resultados[m])
        self.assertEqual((texto, off), (self._as_db(esperado), offset), "cada bloco uma unica vez")
        self.assertNotIn("indisponivel", resultados["thin"], "Thin e o driver padrao do ambiente")


if __name__ == "__main__":
    unittest.main()
