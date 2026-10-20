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
from log_pump import MARCADOR, Bomba, Rodada
from repo_oracle import scheduler_log
from repo_oracle.scheduler_log import (GRAVADO, JA_GRAVADO, POSSE_PERDIDA, LogOffsetInconsistente,
                                       RepoSchedulerLog)

TEXTO_MB = "Ação concluída: café ☕ e emoji \U0001F600 \U0001F4A9 ok; ñ ü ß ç ã é\n" * 3
MB = 1024 * 1024
GRANDE = 10 * MB


class _ClobFalso(object):
    """CLOB de um ticket com o mesmo protocolo do bloco PL/SQL do README §8.10 (unidades UTF-16)."""

    def __init__(self):
        self.texto = ""
        self.offset = 0
        self.dono = ("srv-01", "RUNNING")
        self.truncado = "N"
        self.commits = 0
        self._snapshot = None

    def iniciar_tx(self):
        if self._snapshot is None:
            self._snapshot = (self.texto, self.offset, self.truncado)

    def commit(self):
        self._snapshot = None
        self.commits += 1

    def rollback(self):
        if self._snapshot is not None:
            self.texto, self.offset, self.truncado = self._snapshot
        self._snapshot = None


class _RepoFalso(object):
    """Mesma semantica de RepoSchedulerLog.anexar sobre _ClobFalso (conn = _ConnFalsa)."""

    def __init__(self):
        self.chamadas = []

    def anexar(self, conn, ticket_id, agente_id, offset_esperado, bloco):
        self.chamadas.append((ticket_id, offset_esperado, bloco))
        conn.contar()
        clob = conn.clobs[ticket_id]
        if clob.dono != (agente_id, "RUNNING"):
            return POSSE_PERDIDA
        clob.iniciar_tx()
        tam = log_pump.unidades_clob(bloco)
        if log_pump.unidades_clob(clob.texto) != clob.offset:
            raise LogOffsetInconsistente(ticket_id, offset_esperado, tam)
        if clob.offset == offset_esperado:
            clob.texto += bloco
            clob.offset += tam
            return GRAVADO
        if clob.offset == offset_esperado + tam and clob.texto.encode("utf-16-le")[2 * offset_esperado:] == \
                bloco.encode("utf-16-le"):
            return JA_GRAVADO
        raise LogOffsetInconsistente(ticket_id, offset_esperado, tam)

    def marcar_truncado(self, conn, ticket_id, agente_id):
        clob = conn.clobs[ticket_id]
        if clob.dono != (agente_id, "RUNNING"):
            return False
        clob.iniciar_tx()
        clob.truncado = "S"
        return True


class _ConnFalsa(object):
    def __init__(self, clobs, relogio=None, falhar_commit=0):
        self.clobs = clobs
        self.relogio = relogio
        self.falhar_commit = falhar_commit
        self.commit_incerto_persistiu = True

    def contar(self):
        if self.relogio is not None:
            self.relogio.avancar(1)

    def commit(self):
        if self.falhar_commit:
            self.falhar_commit -= 1
            if self.commit_incerto_persistiu:
                for c in self.clobs.values():
                    c.commit()
            raise RuntimeError("DPY-4011: connection closed (desfecho desconhecido)")
        for c in self.clobs.values():
            c.commit()

    def rollback(self):
        for c in self.clobs.values():
            c.rollback()


class _Relogio(object):
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def avancar(self, s):
        self.t += s


class _Base(unittest.TestCase):

    def setUp(self):
        self.raiz = tempfile.mkdtemp(prefix="sss_pump_")
        self.n = 0

    def tearDown(self):
        shutil.rmtree(self.raiz, ignore_errors=True)

    def arquivo(self, conteudo=b""):
        self.n += 1
        caminho = os.path.join(self.raiz, "ticket_%d.log" % self.n)
        with open(caminho, "wb") as f:
            f.write(conteudo)
        return caminho

    def anexar_bytes(self, caminho, dados):
        with open(caminho, "ab") as f:
            f.write(dados)

    def bomba(self, caminho, mascarador=None, teto=GRANDE, local=GRANDE, ticket_id=1):
        return Bomba(caminho, ticket_id, mascarador or masking.Mascarador(), teto, local)

    def drenar(self, bomba, conn=None, repo=None):
        """Flush final num CLOB falso e devolve o texto do CLOB."""
        conn = conn or _ConnFalsa({bomba.ticket_id: _ClobFalso()})
        repo = repo or _RepoFalso()
        self.assertEqual(log_pump.flush_final(bomba, conn, repo, "srv-01"), log_pump.OK)
        return conn.clobs[bomba.ticket_id]


class TestLeituraEMascara(_Base):

    def test_ascii(self):
        caminho = self.arquivo(b"linha 1\nlinha 2\n")
        b = self.bomba(caminho)
        self.assertEqual(b.coletar(), "linha 1\nlinha 2\n")
        self.assertEqual(self.drenar(b).texto, "linha 1\nlinha 2\n")

    def test_multibyte_cortado_em_todas_as_posicoes(self):
        dados = TEXTO_MB.encode("utf-8")
        for corte in range(len(dados) + 1):
            caminho = self.arquivo(dados[:corte])
            b = self.bomba(caminho)
            primeiro = b.coletar()
            self.anexar_bytes(caminho, dados[corte:])
            segundo = b.coletar(max_bytes_leitura=7)
            clob = self.drenar(b)
            self.assertEqual(clob.texto, TEXTO_MB, "corte em %d" % corte)
            self.assertNotIn("�", primeiro + segundo, "corte em %d" % corte)
            self.assertEqual(clob.offset, log_pump.unidades_clob(TEXTO_MB))

    def test_bytes_invalidos_viram_replacement(self):
        b = self.bomba(self.arquivo(b"ok \xff\xfe fim\n"))
        self.assertEqual(self.drenar(b).texto, "ok �� fim\n")

    def test_segredo_cortado_entre_leituras(self):
        m = masking.Mascarador()
        m.registrar("SenhaSuperSecreta")
        caminho = self.arquivo(b"conectando com Senha")
        b = self.bomba(caminho, m)
        b.coletar()
        self.anexar_bytes(caminho, b"SuperSecreta e pronto\n")
        b.coletar()
        texto = self.drenar(b).texto
        self.assertEqual(texto, "conectando com **** e pronto\n")

    def test_mascarador_por_ticket_isolado(self):
        snap1 = {"respostas": {"token": "tok-ticket-um", "data": "2026-10-13"}, "sensiveis": ["token"]}
        snap2 = {"respostas": {"token": "tok-ticket-dois"}, "sensiveis": ["token"]}
        m1 = log_pump.mascarador_do_ticket(["SegredoGlobal1"], "app/Pw1234@db:1521/X", snap1)
        m2 = log_pump.mascarador_do_ticket(["SegredoGlobal1"], None, snap2)
        linha = b"tok-ticket-um tok-ticket-dois SegredoGlobal1 app/Pw1234@db:1521/X 2026-10-13\n"
        t1 = self.drenar(self.bomba(self.arquivo(linha), m1, ticket_id=1)).texto
        t2 = self.drenar(self.bomba(self.arquivo(linha), m2, ticket_id=2)).texto
        self.assertEqual(t1, "**** tok-ticket-dois **** **** 2026-10-13\n")
        self.assertEqual(t2, "tok-ticket-um **** **** app/****@db:1521/X 2026-10-13\n")
        self.assertIsNone(masking.MASCARADOR.regex and masking.MASCARADOR.regex.search("tok-ticket-um"),
                          "o mascarador global nao recebe o sensivel do ticket")

    def test_segredo_curto_nao_e_mascarado(self):
        snap = {"respostas": {"pin": "123", "senha": "4567"}, "sensiveis": ["pin", "senha"]}
        m = log_pump.mascarador_do_ticket([], None, snap)
        texto = self.drenar(self.bomba(self.arquivo(b"pin=123 senha=4567\n"), m)).texto
        self.assertEqual(texto, "pin=123 senha=****\n")

    def test_arquivo_que_cresce_entre_coletas(self):
        caminho = self.arquivo(b"a\n")
        b = self.bomba(caminho)
        self.assertEqual(b.coletar(), "a\n")
        self.assertEqual(b.coletar(), "")
        self.anexar_bytes(caminho, b"b\n")
        self.assertEqual(b.coletar(), "b\n")
        self.assertEqual(b.offset_bytes, 4)
        self.assertEqual(self.drenar(b).texto, "a\nb\n")

    def test_arquivo_escrito_por_outro_processo_durante_a_coleta(self):
        caminho = self.arquivo()
        filho = subprocess.Popen([sys.executable, "-c",
                                  "import sys,time\nf=open(sys.argv[1],'ab',0)\n"
                                  "for i in range(200):\n    f.write(('linha %04d ação\\n' % i).encode('utf-8'))\n"
                                  "    time.sleep(0.002)\n", caminho])
        b = self.bomba(caminho)
        coletado = []
        while filho.poll() is None:
            coletado.append(b.coletar(max_bytes_leitura=37))
        filho.wait()
        texto = self.drenar(b).texto
        esperado = "".join("linha %04d ação\n" % i for i in range(200))
        self.assertEqual(texto, esperado)
        self.assertTrue(any(coletado), "houve coleta com o arquivo aberto pelo filho")


class TestLimites(_Base):

    def test_teto_que_cabe_exatamente_sem_marcador(self):
        teto = 2048
        conteudo = ("é" * 1024).encode("utf-8")
        self.assertEqual(len(conteudo), teto)
        b = self.bomba(self.arquivo(conteudo), teto=teto)
        b.coletar()
        clob = self.drenar(b)
        self.assertEqual(clob.texto, conteudo.decode("utf-8"))
        self.assertEqual(clob.truncado, "N")
        self.assertFalse(b.truncado)

    def test_teto_excedido_por_um_byte_com_marcador(self):
        teto = 2048
        for conteudo in (("é" * 1024 + "x").encode("utf-8"), ("\U0001F600" * 600).encode("utf-8"),
                         ("a" * 5000).encode("utf-8")):
            b = self.bomba(self.arquivo(conteudo), teto=teto)
            with self.assertLogs("sss_scheduler", "WARNING"):
                b.coletar(max_bytes_leitura=333)
                b.coletar(max_bytes_leitura=MB)
                clob = self.drenar(b)
            self.assertTrue(clob.texto.endswith(MARCADOR))
            self.assertEqual(clob.texto.count(MARCADOR), 1)
            self.assertLessEqual(len(clob.texto.encode("utf-8")), teto)
            corpo = clob.texto[:-len(MARCADOR)]
            self.assertTrue(conteudo.decode("utf-8").startswith(corpo), "corte em fronteira de caractere")
            self.assertGreater(len(corpo.encode("utf-8")), teto - len(MARCADOR.encode("utf-8")) - 4)
            self.assertEqual(clob.truncado, "S")

    def test_aplicar_teto_banco_direto(self):
        teto = 1100
        marcador = len(MARCADOR.encode("utf-8"))
        b = self.bomba(self.arquivo(), teto=teto)
        enviar, truncou = b.aplicar_teto_banco("a" * (teto - marcador))
        self.assertEqual((len(enviar), truncou), (teto - marcador, False))
        enviar, truncou = b.aplicar_teto_banco("b" * marcador)
        self.assertEqual((enviar, truncou), ("", False), "sufixo retido ate a decisao")
        with self.assertLogs("sss_scheduler", "WARNING"):
            enviar, truncou = b.aplicar_teto_banco("c")
        self.assertEqual((enviar, truncou), (MARCADOR, True))
        self.assertEqual(b.aplicar_teto_banco("mais"), ("", True))

    def test_teto_local(self):
        caminho = self.arquivo(b"x" * 1024)
        b = self.bomba(caminho, local=1024)
        self.assertFalse(b.excedeu_local())
        self.anexar_bytes(caminho, b"y")
        self.assertTrue(b.excedeu_local())

    def test_blocos_com_tamanho_exato(self):
        self.assertEqual([len(x) for x in log_pump.blocos("a" * 16001)], [8000, 8000, 1])
        self.assertEqual([len(x) for x in log_pump.blocos("a" * 8000)], [8000])
        self.assertEqual(log_pump.blocos(""), [])
        self.assertEqual([len(x) for x in log_pump.blocos("abcdefg", 3)], [3, 3, 1])

    def test_offset_em_unidades_do_clob(self):
        self.assertEqual(log_pump.unidades_clob("a\U0001F600é"), 4)
        self.assertEqual(log_pump.unidades_clob("a\U0001F600é", 2), 4)
        self.assertEqual(log_pump.unidades_clob("a\U0001F600é", 1), 3)

    def test_bomba_com_unidade_de_charset_de_um_byte(self):
        b = Bomba(self.arquivo("x\U0001F600y\n".encode("utf-8")), 1, masking.Mascarador(), GRANDE, GRANDE,
                  unidade_suplementar=1)
        conn = _ConnFalsa({1: _ClobFalso()})
        log_pump.flush_final(b, conn, _RepoFalso(), "srv-01")
        self.assertEqual(b.offset_confirmado_chars, 4)


class TestProtocolo(_Base):

    def test_posse_perdida_nao_avanca_o_confirmado(self):
        b = self.bomba(self.arquivo(b"texto\n"))
        clob = _ClobFalso()
        clob.dono = ("outro", "FAILED")
        conn = _ConnFalsa({1: clob})
        self.assertEqual(log_pump.flush_final(b, conn, _RepoFalso(), "srv-01"), POSSE_PERDIDA)
        self.assertEqual((b.offset_confirmado_chars, b.bytes_confirmados), (0, 0))
        self.assertTrue(b.posse_perdida)
        self.assertEqual(b.proximo_bloco(), ("texto\n", 0), "texto nao descartado como gravado")

    def test_commit_incerto_reconciliado_sem_duplicar(self):
        b = self.bomba(self.arquivo(("x" * 8000 + "fim\n").encode("utf-8")))
        conn = _ConnFalsa({1: _ClobFalso()}, falhar_commit=1)
        repo = _RepoFalso()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(log_pump.flush_final(b, conn, repo, "srv-01"), log_pump.CONEXAO_INCERTA)
        self.assertEqual(b.offset_confirmado_chars, 0, "nada confirmado antes do COMMIT conhecido")
        self.assertEqual(log_pump.flush_final(b, conn, repo, "srv-01"), log_pump.OK)
        self.assertEqual(conn.clobs[1].texto, "x" * 8000 + "fim\n")
        self.assertEqual([c[1] for c in repo.chamadas], [0, 0, 8000], "mesma operacao reapresentada")

    def test_commit_que_falhou_sem_persistir_regrava(self):
        b = self.bomba(self.arquivo(b"abc\n"))
        conn = _ConnFalsa({1: _ClobFalso()}, falhar_commit=1)
        conn.commit_incerto_persistiu = False
        repo = _RepoFalso()
        with self.assertLogs("sss_scheduler", "WARNING"):
            self.assertEqual(log_pump.flush_final(b, conn, repo, "srv-01"), log_pump.CONEXAO_INCERTA)
        conn.rollback()
        self.assertEqual(log_pump.flush_final(b, conn, repo, "srv-01"), log_pump.OK)
        self.assertEqual(conn.clobs[1].texto, "abc\n")

    def test_divergencia_interrompe_sem_alterar(self):
        for clob_texto, clob_offset in (("zzz", 3), ("abc", 2)):
            b = self.bomba(self.arquivo(b"abc\n"))
            clob = _ClobFalso()
            clob.texto, clob.offset = clob_texto, clob_offset
            with self.assertLogs("sss_scheduler", "ERROR"):
                self.assertEqual(log_pump.flush_final(b, _ConnFalsa({1: clob}), _RepoFalso(), "srv-01"),
                                 log_pump.INCONSISTENTE)
            self.assertEqual((clob.texto, clob.offset), (clob_texto, clob_offset))
            self.assertTrue(b.parada)
            self.assertEqual(b.coletar(), "", "pump do ticket interrompido")

    def test_orcamento_e_rodizio(self):
        relogio = _Relogio()
        clobs = dict((t, _ClobFalso()) for t in (1, 2, 3))
        conn = _ConnFalsa(clobs, relogio=relogio)
        caminhos = dict((t, self.arquivo()) for t in (1, 2, 3))
        bombas = dict((t, self.bomba(caminhos[t], ticket_id=t)) for t in (1, 2, 3))
        rodada = Rodada(bombas, relogio, orcamento_s=3)
        atendidos = []
        for _ in range(9):
            for t in (1, 2, 3):
                # Tickets verbosos: 3 blocos novos por rodada (cada envio custa 1 s no relogio simulado).
                self.anexar_bytes(caminhos[t], ("%d" % t * 8000 * 3).encode("ascii"))
            res = rodada.executar(conn, _RepoFalso(), "srv-01")
            self.assertTrue(res.esgotou_orcamento)
            atendidos.append(set(res.atendidos))
            relogio.avancar(100)
        self.assertEqual(len(clobs[1].texto) + len(clobs[2].texto) + len(clobs[3].texto) > 0, True)
        for i in range(len(atendidos) - 1):
            for t in (1, 2, 3):
                self.assertTrue(t in atendidos[i] or t in atendidos[i + 1],
                                "ticket %d sem coleta nas rodadas %d e %d: %s" % (t, i, i + 1, atendidos))
        # O orcamento (3 s, 1 s por bloco) cobre os blocos de um ticket so; ainda assim ha fila acumulada.
        self.assertTrue(any(b.pendente() for b in bombas.values()))
        # Lidos e nao confirmados sobrevivem: drenando, cada CLOB tem tudo, sem perda nem duplicacao.
        for t in (1, 2, 3):
            self.assertEqual(log_pump.flush_final(bombas[t], conn, _RepoFalso(), "srv-01"), log_pump.OK)
            self.assertEqual(clobs[t].texto, "%d" % t * 8000 * 3 * 9)

    def test_rodada_segue_com_arquivo_ausente(self):
        # Revisao F8.0-F8.2 (A1): um log ilegivel nao para a coleta dos outros tickets.
        clobs = {1: _ClobFalso(), 2: _ClobFalso()}
        conn = _ConnFalsa(clobs)
        bombas = {1: self.bomba(os.path.join(self.raiz, "sumiu.log"), ticket_id=1),
                  2: self.bomba(self.arquivo(b"ok\n"), ticket_id=2)}
        rodada = Rodada(bombas, _Relogio(), orcamento_s=100)
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            rodada.executar(conn, _RepoFalso(), "srv-01")
            rodada.executar(conn, _RepoFalso(), "srv-01")
        self.assertEqual(len([x for x in logs.output if "ilegivel" in x]), 1, "WARN uma vez")
        self.assertTrue(bombas[1].erro_leitura)
        self.assertEqual(log_pump.flush_final(bombas[2], conn, _RepoFalso(), "srv-01"), log_pump.OK)
        self.assertEqual(clobs[2].texto, "ok\n")
        self.assertEqual(log_pump.flush_final(bombas[1], conn, _RepoFalso(), "srv-01"), log_pump.OK)
        self.assertEqual(clobs[1].texto, "")

    def test_flush_final_le_em_blocos_e_para_ao_truncar(self):
        # Revisao F8.0-F8.2 (M1): arquivo bem maior que o teto nao e lido inteiro para a memoria.
        caminho = self.arquivo(b"x" * (5 * MB))
        b = self.bomba(caminho, teto=4096)
        with self.assertLogs("sss_scheduler", "WARNING"):
            clob = self.drenar(b)
        self.assertLessEqual(b.offset_bytes, log_pump.LEITURA_PADRAO, "parou de ler no primeiro bloco")
        self.assertTrue(clob.texto.endswith(MARCADOR))
        self.assertLessEqual(len(clob.texto.encode("utf-8")), 4096)

    def test_flush_final_sem_truncar_le_tudo_em_blocos(self):
        conteudo = b"".join(("linha ação %06d\n" % i).encode("utf-8") for i in range(150000))
        b = self.bomba(self.arquivo(conteudo))
        clob = self.drenar(b)
        self.assertGreater(len(conteudo), 2 * log_pump.LEITURA_PADRAO)
        self.assertEqual(clob.texto, conteudo.decode("utf-8"))

    def test_rodada_com_commit_incerto_preserva_e_retoma(self):
        relogio = _Relogio()
        clobs = {1: _ClobFalso()}
        conn = _ConnFalsa(clobs, relogio=relogio, falhar_commit=1)
        caminho = self.arquivo(b"a" * 20000)
        bombas = {1: self.bomba(caminho)}
        rodada = Rodada(bombas, relogio, orcamento_s=100)
        with self.assertLogs("sss_scheduler", "WARNING"):
            res = rodada.executar(conn, _RepoFalso(), "srv-01")
        self.assertTrue(res.conexao_incerta)
        res = rodada.executar(conn, _RepoFalso(), "srv-01")
        self.assertFalse(res.conexao_incerta)
        self.assertEqual(log_pump.flush_final(bombas[1], conn, _RepoFalso(), "srv-01"), log_pump.OK)
        self.assertEqual(clobs[1].texto, "a" * 20000)


class _CursorAnexar(object):
    """Duble de cursor: registra binds e simula o resultado ou um erro do bloco PL/SQL."""

    def __init__(self, conn):
        self.conn = conn
        self.entradas = None
        self.rowcount = 0

    def setinputsizes(self, **tipos):
        self.entradas = tipos

    def var(self, tipo, size=None):
        self.conn.vars.append((tipo, size))
        return mock.Mock(getvalue=mock.Mock(return_value=self.conn.resultado))

    def execute(self, sql, **binds):
        self.conn.execucoes.append((sql, binds, self.entradas))
        if self.conn.erro is not None:
            raise self.conn.erro
        self.rowcount = self.conn.rowcount

    def close(self):
        pass


class _ConnAnexar(object):
    def __init__(self, resultado="GRAVADO", erro=None, rowcount=1):
        self.resultado = resultado
        self.erro = erro
        self.rowcount = rowcount
        self.vars = []
        self.execucoes = []

    def cursor(self):
        return _CursorAnexar(self)


class TestRepoSchedulerLog(unittest.TestCase):

    def setUp(self):
        self.repo = RepoSchedulerLog("OWN_X", "pfx_")

    def test_bloco_plsql_literal_com_owner_e_prefixo(self):
        conn = _ConnAnexar()
        self.assertEqual(self.repo.anexar(conn, 7, "srv-01", 0, "abc"), GRAVADO)
        sql, binds, tipos = conn.execucoes[0]
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
        self.assertEqual(set(binds), {"chunk", "ticket_id", "agente_id", "offset_esperado", "resultado"})
        self.assertEqual(tipos, {"chunk": db_conn.obter_tipo_driver(db_conn.TIPO_CLOB)})

    def test_resultados_e_posse_perdida(self):
        for r in (GRAVADO, JA_GRAVADO, POSSE_PERDIDA):
            self.assertEqual(self.repo.anexar(_ConnAnexar(resultado=r), 7, "srv-01", 0, "abc"), r)
        with self.assertRaises(RuntimeError):
            self.repo.anexar(_ConnAnexar(resultado=None), 7, "srv-01", 0, "abc")
        with self.assertRaises(ValueError):
            self.repo.anexar(_ConnAnexar(), 7, "srv-01", 0, "")

    def test_ora_20002_vira_log_offset_inconsistente(self):
        erro = Exception("ORA-20002: LOG_OFFSET_DIVERGENTE\nORA-06512: at line 13")
        with self.assertRaises(LogOffsetInconsistente):
            self.repo.anexar(_ConnAnexar(erro=erro), 7, "srv-01", 0, "abc")
        with self.assertRaises(Exception) as ctx:
            self.repo.anexar(_ConnAnexar(erro=Exception("ORA-00054: resource busy")), 7, "srv-01", 0, "abc")
        self.assertNotIsInstance(ctx.exception, LogOffsetInconsistente)

    def test_bind_out_pelos_tres_drivers(self):
        """variavel_saida/valor_saida escolhem o tipo VARCHAR de cada combinacao (Thin/Thick: oracledb;
        cx_Oracle: STRING); o resultado lido e o mesmo."""
        oracledb = mock.Mock(__name__="oracledb", DB_TYPE_VARCHAR="ODB_VARCHAR", DB_TYPE_CLOB="ODB_CLOB")
        cx = mock.Mock(__name__="cx_Oracle", STRING="CX_STRING", CLOB="CX_CLOB")
        for candidato, driver, esperado, clob in (("thin", oracledb, "ODB_VARCHAR", "ODB_CLOB"),
                                                  ("thick", oracledb, "ODB_VARCHAR", "ODB_CLOB"),
                                                  ("cx_oracle", cx, "CX_STRING", "CX_CLOB")):
            selecao = mock.Mock(candidato=candidato)
            conn = _ConnAnexar(resultado=JA_GRAVADO)
            with mock.patch.object(db_conn, "_DRIVER_INICIALIZADO", driver), \
                    mock.patch.object(db_conn, "_SELECAO_DRIVER", selecao):
                self.assertEqual(self.repo.anexar(conn, 7, "srv-01", 3, "abc"), JA_GRAVADO, candidato)
            self.assertEqual(conn.vars, [(esperado, 20)], candidato)
            self.assertEqual(conn.execucoes[0][2], {"chunk": clob}, candidato)

    def test_marcar_truncado(self):
        conn = _ConnAnexar(rowcount=1)
        self.assertTrue(self.repo.marcar_truncado(conn, 7, "srv-01"))
        sql = conn.execucoes[0][0]
        self.assertIn("log_truncado = 'S'", sql)
        self.assertIn("OWN_X.pfx_tickets", sql)
        self.assertNotIn("updated_", sql)
        self.assertFalse(self.repo.marcar_truncado(_ConnAnexar(rowcount=0), 7, "srv-01"))

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

_FILHO = r'''
import json, sys, warnings
warnings.simplefilter("ignore")
sys.path.insert(0, sys.argv[1])
import sss_config, db_conn
from repo_oracle.scheduler_log import RepoSchedulerLog
cfg = sss_config.obter_config()
cfg = cfg._replace(oracle=cfg.oracle._replace(modo_driver=sys.argv[2]))
seg = sss_config.carregar_segredos(cfg.secrets.secrets_file, cfg=cfg, papel="web")
try:
    conn = db_conn.conectar(cfg, seg, "web")
except Exception as e:
    print(json.dumps({"indisponivel": "%s: %s" % (e.__class__.__name__, str(e)[:120])}))
    sys.exit(0)
repo = RepoSchedulerLog.da_config(cfg)
ticket_id, agente, offset, bloco = int(sys.argv[3]), sys.argv[4], int(sys.argv[5]), sys.argv[6]
r1 = repo.anexar(conn, ticket_id, agente, offset, bloco)
conn.commit()
r2 = repo.anexar(conn, ticket_id, agente, offset, bloco)
conn.commit()
print(json.dumps({"candidato": db_conn.obter_selecao().candidato, "r": [r1, r2]}))
conn.close()
'''


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestSchedulerLogOracle(unittest.TestCase):
    """WRITEAPPEND real num ticket proprio (modo compartilhado ou descartavel), limpo no tearDown."""

    AGENTE = "tst-pump-01"

    @classmethod
    def setUpClass(cls):
        import test_repo_contract as trc
        cls.trc = trc
        cls.contrato = trc._OracleContrato
        cls.contrato.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.contrato.tearDownClass.__func__(cls)

    def setUp(self):
        self.contrato.setUp(self)
        self._massa = self.trc._Massa(self.obter_repo)
        c = self._massa.cenario()
        self.ticket_id = self._massa.ticket(ator="teste", script_id=c["scr"]["id"], ambiente=c["amb1"]["nome"],
                                            solicitante=c["login"])
        self.catalogo = self.obter_repo("catalogo")
        self.repo = RepoSchedulerLog(self.catalogo._owner, self.catalogo._prefixo)
        self.tck = self.catalogo.qualificar_tabela("tickets")
        conn = self.catalogo._obter_conexao()
        try:
            self.unidade = self.repo.unidade_suplementar(conn)
        finally:
            conn.close()
        # Estado que o claim (F8.3) deixa: RUNNING deste agente, CLOB vazio e offset 0.
        self._sql("UPDATE " + self.tck + " SET status = 'RUNNING', agente_id = :a, started_at = SYSDATE, "
                  "heartbeat_at = SYSDATE, log_output = EMPTY_CLOB(), log_offset_chars = 0 WHERE id = :id",
                  a=self.AGENTE, id=self.ticket_id)

    def tearDown(self):
        self.contrato.tearDown(self)

    def obter_repo(self, nome):
        return self.contrato.obter_repo(self, nome)

    def _limpar_massa(self):
        return self.contrato._limpar_massa(self)

    def _sql(self, sql, **binds):
        conn = self.catalogo._obter_conexao()
        try:
            cur = conn.cursor()
            cur.execute(sql, **binds)
            conn.commit()
        finally:
            conn.close()

    def _como_banco(self, texto):
        """O texto como o charset do banco o guarda (caractere fora dele vira o de substituicao)."""
        conn = self.catalogo._obter_conexao()
        try:
            cur = conn.cursor()
            db_conn.definir_tipos_entrada(cur, x=db_conn.TIPO_CLOB)
            cur.execute("SELECT TO_CLOB(:x) FROM DUAL", x=texto)
            return cur.fetchone()[0].read()
        finally:
            conn.close()

    def _estado(self):
        conn = self.catalogo._obter_conexao()
        try:
            cur = conn.cursor()
            cur.execute("SELECT log_output, log_offset_chars, log_truncado FROM " + self.tck + " WHERE id = :id",
                        id=self.ticket_id)
            lob, off, trunc = cur.fetchone()
            return (lob.read() if lob is not None and lob.size() else ""), int(off), trunc
        finally:
            conn.close()

    def test_append_idempotente_rollback_e_divergencia(self):
        conn = self.catalogo._obter_conexao()
        try:
            bloco = "ação \U0001F600 linha 1\n"
            unidades = log_pump.unidades_clob(bloco, self.unidade)
            guardado = self._como_banco(bloco)
            # Rollback antes do primeiro COMMIT: a nova tentativa grava (GRAVADO).
            self.assertEqual(self.repo.anexar(conn, self.ticket_id, self.AGENTE, 0, bloco), GRAVADO)
            conn.rollback()
            self.assertEqual(self.repo.anexar(conn, self.ticket_id, self.AGENTE, 0, bloco), GRAVADO)
            conn.commit()
            # Mesma operacao depois do COMMIT: JA_GRAVADO, sem segundo WRITEAPPEND.
            self.assertEqual(self.repo.anexar(conn, self.ticket_id, self.AGENTE, 0, bloco), JA_GRAVADO)
            conn.commit()
            self.assertEqual(self._estado(), (guardado, unidades, "N"))
            # Offset divergente e conteudo diferente: LogOffsetInconsistente sem alterar o CLOB.
            for offset, outro in ((unidades + 5, "x"), (0, "ação \U0001F600 linha 2\n"), (1, bloco)):
                with self.assertRaises(LogOffsetInconsistente):
                    self.repo.anexar(conn, self.ticket_id, self.AGENTE, offset, outro)
                conn.rollback()
            self.assertEqual(self._estado(), (guardado, unidades, "N"))
            # Outro agente: POSSE_PERDIDA.
            self.assertEqual(self.repo.anexar(conn, self.ticket_id, "outro-agente", unidades, "z"), POSSE_PERDIDA)
            conn.rollback()
            self.assertTrue(self.repo.marcar_truncado(conn, self.ticket_id, self.AGENTE))
            conn.commit()
            self.assertEqual(self._estado()[2], "S")
        finally:
            conn.close()

    def test_bomba_completa_mascarada_uma_vez(self):
        raiz = tempfile.mkdtemp(prefix="sss_pump_ora_")
        self.addCleanup(shutil.rmtree, raiz, True)
        caminho = os.path.join(raiz, "ticket.log")
        linhas = "".join("linha %05d ação \U0001F600 senha=SegredoDoTicket\n" % i for i in range(700))
        with open(caminho, "wb") as f:
            f.write(linhas.encode("utf-8"))
        m = log_pump.mascarador_do_ticket(["SegredoDoTicket"])
        b = Bomba(caminho, self.ticket_id, m, 5 * MB, 50 * MB, unidade_suplementar=self.unidade)
        conn = self.catalogo._obter_conexao()
        try:
            self.assertEqual(log_pump.flush_final(b, conn, self.repo, self.AGENTE), log_pump.OK)
        finally:
            conn.close()
        esperado = linhas.replace("SegredoDoTicket", "****")
        texto, offset, _trunc = self._estado()
        self.assertEqual(texto, self._como_banco(esperado))
        self.assertEqual(texto.count("****"), 700)
        self.assertNotIn("SegredoDoTicket", texto)
        self.assertEqual(offset, log_pump.unidades_clob(esperado, self.unidade))
        self.assertGreater(len(esperado), 8000, "mais de um bloco")

    def test_combinacoes_de_driver(self):
        modulos = os.path.dirname(os.path.abspath(log_pump.__file__))
        offset = 0
        resultados = {}
        for modo in ("thin", "thick", "cx_oracle"):
            bloco = "driver %s ação \U0001F600\n" % modo
            p = subprocess.run([sys.executable, "-c", _FILHO, modulos, modo, str(self.ticket_id), self.AGENTE,
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
            self.assertEqual((saida["candidato"], saida["r"]), (modo, [GRAVADO, JA_GRAVADO]), modo)
            offset += log_pump.unidades_clob(bloco, self.unidade)
        print("\n[log_pump] combinacoes de driver: %s" % json.dumps(resultados, ensure_ascii=False))
        texto, off, _trunc = self._estado()
        esperado = "".join("driver %s ação \U0001F600\n" % m for m in ("thin", "thick", "cx_oracle")
                           if "indisponivel" not in resultados[m])
        self.assertEqual((texto, off), (self._como_banco(esperado), offset), "cada bloco uma unica vez")
        self.assertNotIn("indisponivel", resultados["thin"], "Thin e o driver padrao do ambiente")


if __name__ == "__main__":
    unittest.main()
