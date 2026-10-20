# -*- coding: utf-8 -*-
"""Testes do repo_oracle.scheduler_saida (CR-012; README §8.13 e §10, tabela 18).

Sem banco: conexao roteirizada do test_scheduler_fila (SQL, binds, posse e ausencia de COMMIT).
Com SSS_TEST_ORACLE=1: o ciclo real no owner e prefixo do instance/config.ini, com massa propria, e a
leitura pelo repositorio da web (saida_obter, saida_ler); tudo removido no fim (cascata do ticket).
"""
import _testenv  # noqa: F401

import json
import os
import subprocess
import sys
import unittest
from unittest import mock

import db_conn

from repo_oracle import scheduler_saida
from repo_oracle.scheduler_saida import RepoSchedulerSaida, SaidaOffsetInconsistente
from test_scheduler_fila import _Conn, _Erro

AGENTE = "srv-01"


class TestSemBanco(unittest.TestCase):

    def setUp(self):
        self.repo = RepoSchedulerSaida("openrisow", "tbsss_")
        # O cursor roteirizado devolve a variavel de saida em lista (formato do RETURNING).
        valor = mock.patch.object(db_conn, "valor_saida", lambda var: var.getvalue()[0])
        valor.start()
        self.addCleanup(valor.stop)

    def test_iniciar_reinicia_a_propria_ou_inclui_com_posse_do_ticket(self):
        conn = _Conn([("SET conteudo = EMPTY_BLOB()", (1, []))])
        self.assertTrue(self.repo.iniciar(conn, 7, AGENTE))
        self.assertEqual(conn.sql("INSERT"), [])
        conn = _Conn([("SET conteudo = EMPTY_BLOB()", (0, [])), ("INSERT INTO", (1, []))])
        self.assertTrue(self.repo.iniciar(conn, 7, AGENTE))
        sql, binds = [e for e in conn.executados if "INSERT INTO" in e[0]][0]
        self.assertIn("FROM openrisow.tbsss_tickets t WHERE t.id = :ticket_id AND t.agente_id = :agente_id", sql)
        self.assertIn("NOT EXISTS", sql)
        self.assertIn("EMPTY_BLOB()", sql)
        self.assertEqual((binds["situacao"], binds["ator"], binds["id"]), ("GRAVANDO", "SYSTEM:srv-01", 501))
        conn = _Conn([("SET conteudo = EMPTY_BLOB()", (0, [])), ("INSERT INTO", (0, []))])
        self.assertFalse(self.repo.iniciar(conn, 7, AGENTE))
        self.assertEqual((conn.commits, conn.rollbacks), (0, 0), "sem COMMIT: a fase decide")

    def test_anexar_resultados_e_divergencia(self):
        for valor in ("GRAVADO", "JA_GRAVADO", "POSSE_PERDIDA"):
            conn = _Conn([("DECLARE", (1, [], valor))])
            self.assertEqual(self.repo.anexar(conn, 7, AGENTE, 0, b"PK\x03\x04"), valor)
        conn = _Conn([("DECLARE", (1, [], "GRAVADO"))])
        self.repo.anexar(conn, 7, AGENTE, 1048576, b"x")
        sql, binds = conn.executados[0]
        self.assertIn("FOR UPDATE WAIT 5", sql)
        self.assertIn("DBMS_LOB.APPEND(v_lob, :parte)", sql)
        self.assertIn("situacao = 'GRAVANDO'", sql)
        self.assertEqual((binds["offset_esperado"], binds["parte"]), (1048576, b"x"))
        conn = _Conn([("DECLARE", _Erro("ORA-20003: SAIDA_OFFSET_DIVERGENTE"))])
        with self.assertRaises(SaidaOffsetInconsistente):
            self.repo.anexar(conn, 7, AGENTE, 0, b"x")
        for ruim in (b"", b"x" * (scheduler_saida.PARTE_MAX + 1)):
            with self.assertRaises(ValueError):
                self.repo.anexar(_Conn([]), 7, AGENTE, 0, ruim)

    def test_concluir_confere_o_tamanho_no_banco(self):
        conn = _Conn([("SET situacao = 'DISPONIVEL'", (1, []))])
        self.assertTrue(self.repo.concluir(conn, 7, AGENTE, 3, 2048))
        sql, binds = conn.executados[0]
        self.assertIn("DBMS_LOB.GETLENGTH(conteudo) = :tamanho_bytes", sql)
        self.assertIn("updated_by = :ator", sql)
        self.assertFalse(self.repo.concluir(_Conn([]), 7, AGENTE, 3, 2048))

    def test_registrar_sem_conteudo(self):
        conn = _Conn([("SET situacao = :situacao", (1, []))])
        self.assertTrue(self.repo.registrar_sem_conteudo(conn, 7, AGENTE, "EXCEDEU", "ARQUIVOS", 1001))
        self.assertEqual(conn.sql("INSERT"), [])
        conn = _Conn([("SET situacao = :situacao", (0, [])), ("INSERT INTO", (1, []))])
        self.assertTrue(self.repo.registrar_sem_conteudo(conn, 7, AGENTE, "FALHOU", "PRAZO"))
        sql, binds = [e for e in conn.executados if "INSERT INTO" in e[0]][0]
        self.assertIn(", NULL, SYSDATE", sql, "sem conteudo")
        self.assertEqual((binds["situacao"], binds["motivo"]), ("FALHOU", "PRAZO"))
        for situacao, motivo in (("DISPONIVEL", "ERRO"), ("FALHOU", "OUTRO")):
            with self.assertRaises(ValueError):
                self.repo.registrar_sem_conteudo(_Conn([]), 7, AGENTE, situacao, motivo)

    def test_falhar_gravando_usa_o_indice_de_funcao(self):
        conn = _Conn([("SET situacao = 'FALHOU'", (2, []))])
        self.assertEqual(self.repo.falhar_gravando_do_agente(conn, AGENTE), 2)
        self.assertIn("(CASE WHEN situacao = 'GRAVANDO' THEN agente_id END) = :agente_id", conn.executados[0][0])

    def test_situacao(self):
        self.assertEqual(self.repo.situacao(_Conn([("SELECT situacao", (1, [("DISPONIVEL", AGENTE)]))]), 7),
                         ("DISPONIVEL", AGENTE))
        self.assertIsNone(self.repo.situacao(_Conn([]), 7))

    def test_prefixo_e_owner_parametrizados(self):
        repo = RepoSchedulerSaida("outro", "abcdefg_")
        conn = _Conn([("SET conteudo = EMPTY_BLOB()", (1, []))])
        repo.iniciar(conn, 1, AGENTE)
        self.assertIn("outro.abcdefg_ticket_saida", conn.executados[0][0])
        self.assertNotIn("tbsss_", conn.executados[0][0])


# Processo filho com o driver forcado (o driver e escolhido uma vez por processo): BLOB por TIPO_BLOB.
_FILHO = r'''
import json, sys, warnings
warnings.simplefilter("ignore")
sys.path.insert(0, sys.argv[1])
import sss_config, db_conn
from repo_oracle.scheduler_saida import RepoSchedulerSaida
cfg = sss_config.obter_config()
cfg = cfg._replace(oracle=cfg.oracle._replace(modo_driver=sys.argv[2]))
seg = sss_config.carregar_segredos(cfg.secrets.secrets_file, cfg=cfg, papel="web")
try:
    conn = db_conn.conectar(cfg, seg, "web")
except Exception as e:
    print(json.dumps({"indisponivel": "%s: %s" % (e.__class__.__name__, str(e)[:120])}))
    sys.exit(0)
repo = RepoSchedulerSaida.da_config(cfg)
tid, agente = int(sys.argv[3]), sys.argv[4]
parte = bytes(bytearray(range(256))) * 1200
r = [repo.iniciar(conn, tid, agente)]
conn.commit()
r.append(repo.anexar(conn, tid, agente, 0, parte))
conn.commit()
r.append(repo.anexar(conn, tid, agente, 0, parte))
r.append(repo.concluir(conn, tid, agente, 1, len(parte)))
conn.commit()
print(json.dumps({"candidato": db_conn.obter_selecao().candidato, "r": r}))
conn.close()
'''


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestSchedulerSaidaOracle(unittest.TestCase):
    """Ciclo real da saida com massa propria; a web le pelo repositorio de tickets."""

    @classmethod
    def setUpClass(cls):
        import test_repo_contract as trc
        cls.trc = trc
        cls.contrato = trc._OracleContrato
        cls.contrato.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.contrato.tearDownClass.__func__(cls)

    def obter_repo(self, nome):
        return self.contrato.obter_repo(self, nome)

    def _limpar_massa(self):
        return self.contrato._limpar_massa(self)

    def setUp(self):
        from repo_oracle.scheduler_fila import RepoSchedulerFila
        self.contrato.setUp(self)
        self._massa = self.trc._Massa(self.obter_repo)
        self.c = self._massa.cenario()
        cat = self.obter_repo("catalogo")
        self.fila = RepoSchedulerFila(cat._owner, cat._prefixo)
        self.repo = RepoSchedulerSaida(cat._owner, cat._prefixo)
        self.agente = "tst-sai-%s" % self._massa.suf
        self.amb = self.c["amb1"]["nome"]
        self.conn = cat._obter_conexao()
        self.addCleanup(self.conn.close)
        self.tickets = self.obter_repo("tickets")

    def tearDown(self):
        self.contrato.tearDown(self)

    def _ticket_do_agente(self):
        tid = self._massa.ticket(ator="teste", script_id=self.c["scr"]["id"], ambiente=self.amb,
                                 solicitante=self.c["login"])
        self.assertTrue(self.fila.claim(self.conn, tid, self.c["scr"]["id"], self.amb, self.agente)[0])
        self.assertTrue(self.fila.finalizar(self.conn, tid, self.agente, "SUCCESS", "EXIT_OK", 0))
        return tid

    def test_ciclo_disponivel_e_leitura_pela_web(self):
        tid = self._ticket_do_agente()
        self.assertIsNone(self.tickets.saida_obter(tid))
        self.assertFalse(self.repo.iniciar(self.conn, tid, "outro-agente"), "posse do ticket")
        self.conn.rollback()
        self.assertTrue(self.repo.iniciar(self.conn, tid, self.agente))
        self.conn.commit()
        zip_ = bytes(bytearray(range(256))) * 5000  # 1,28 MB: duas partes
        p1, p2 = zip_[:scheduler_saida.PARTE_MAX], zip_[scheduler_saida.PARTE_MAX:]
        self.assertEqual(self.repo.anexar(self.conn, tid, self.agente, 0, p1), "GRAVADO")
        self.conn.commit()
        # COMMIT sem resposta: a mesma parte de novo e reconhecida
        self.assertEqual(self.repo.anexar(self.conn, tid, self.agente, 0, p1), "JA_GRAVADO")
        with self.assertRaises(SaidaOffsetInconsistente):
            self.repo.anexar(self.conn, tid, self.agente, 10, p2)
        self.conn.rollback()
        self.assertEqual(self.repo.anexar(self.conn, tid, self.agente, len(p1), p2), "GRAVADO")
        self.assertEqual(self.tickets.saida_obter(tid)["situacao"], "GRAVANDO")
        with self.assertRaises(self.trc.RepoNaoEncontrado):
            self.tickets.saida_ler(tid, 0, 10)
        self.assertFalse(self.repo.concluir(self.conn, tid, self.agente, 2, len(zip_) + 1), "tamanho conferido")
        self.assertTrue(self.repo.concluir(self.conn, tid, self.agente, 2, len(zip_)))
        self.conn.commit()
        meta = self.tickets.saida_obter(tid)
        self.assertEqual((meta["situacao"], meta["qtd_arquivos"], meta["tamanho_bytes"], meta["agente_id"]),
                         ("DISPONIVEL", 2, len(zip_), self.agente))
        self.assertEqual(meta["updated_by"], "SYSTEM:%s" % self.agente)
        self.assertNotIn("conteudo", meta)
        lido, off = b"", 0
        while True:
            parte = self.tickets.saida_ler(tid, off, 300000)
            if not parte:
                break
            lido += parte
            off += len(parte)
        self.assertEqual(lido, zip_)
        self.assertEqual(self.repo.anexar(self.conn, tid, self.agente, len(zip_), b"x"), "POSSE_PERDIDA",
                         "fora de GRAVANDO nada e anexado")
        self.assertFalse(self.repo.iniciar(self.conn, tid, self.agente), "situacao final nao reabre")
        self.conn.rollback()

    def test_combinacoes_de_driver(self):
        modulos = os.path.dirname(os.path.abspath(scheduler_saida.__file__))
        modulos = os.path.dirname(modulos)
        parte = bytes(bytearray(range(256))) * 1200
        resultados = {}
        for modo in ("thin", "thick", "cx_oracle"):
            tid = self._ticket_do_agente()
            p = subprocess.run([sys.executable, "-c", _FILHO, modulos, modo, str(tid), self.agente],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
                               cwd=os.path.dirname(modulos))
            linhas = [x for x in p.stdout.decode("utf-8", "replace").splitlines() if x.startswith("{")]
            self.assertTrue(linhas, "%s: %s" % (modo, p.stderr.decode("utf-8", "replace")[-500:]))
            saida = json.loads(linhas[-1])
            resultados[modo] = saida
            if "indisponivel" in saida:
                continue
            self.assertEqual((saida["candidato"], saida["r"]), (modo, [True, "GRAVADO", "JA_GRAVADO", True]), modo)
            self.assertEqual(self.tickets.saida_ler(tid, 0, len(parte)), parte, modo)
        print("\n[saida] combinacoes de driver: %s" % json.dumps(resultados))
        self.assertNotIn("indisponivel", resultados["thin"], "Thin e o driver padrao do ambiente")

    def test_excedeu_falhou_e_startup_check(self):
        t1, t2, t3 = self._ticket_do_agente(), self._ticket_do_agente(), self._ticket_do_agente()
        self.assertTrue(self.repo.registrar_sem_conteudo(self.conn, t1, self.agente, "EXCEDEU", "ARQUIVOS", 1001))
        self.assertTrue(self.repo.iniciar(self.conn, t2, self.agente))
        self.assertTrue(self.repo.registrar_sem_conteudo(self.conn, t2, self.agente, "FALHOU", "PRAZO"))
        self.assertTrue(self.repo.iniciar(self.conn, t3, self.agente))
        self.conn.commit()
        self.assertEqual(self.repo.falhar_gravando_do_agente(self.conn, self.agente), 1)
        self.conn.commit()
        for tid, esperado in ((t1, ("EXCEDEU", "ARQUIVOS", 1001)), (t2, ("FALHOU", "PRAZO", None)),
                              (t3, ("FALHOU", "ERRO", None))):
            meta = self.tickets.saida_obter(tid)
            self.assertEqual((meta["situacao"], meta["motivo"], meta["qtd_arquivos"]), esperado)
            with self.assertRaises(self.trc.RepoNaoEncontrado):
                self.tickets.saida_ler(tid, 0, 10)
        self.assertEqual(self.repo.situacao(self.conn, t1), ("EXCEDEU", self.agente))
        self.assertFalse(self.repo.registrar_sem_conteudo(self.conn, t1, self.agente, "FALHOU", "ERRO"))
        self.conn.rollback()


if __name__ == "__main__":
    unittest.main()
