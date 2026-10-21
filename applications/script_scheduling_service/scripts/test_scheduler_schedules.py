# -*- coding: utf-8 -*-
"""Testes do repo_oracle.scheduler_schedules e das operacoes de no offline e fencing do scheduler_fila (F8.4a;
README §7.5, §8.8, §8.9; CR-006; CR-007 R-05, R-08, R-12, R-19, R-27; CR-008 R-03, R-10, R-19, R-31).

Sem banco: conexao roteirizada do test_scheduler_fila (SQL literal, binds de data sem microssegundos e com
TIPO_DATE, nenhuma operacao do agenda faz COMMIT/ROLLBACK). Com SSS_TEST_ORACLE=1: as operacoes reais no
owner do instance/config.ini com massa propria (inclusive o teste obrigatorio de microssegundos).
"""
import _testenv  # noqa: F401

import datetime
import os
import unittest
from unittest import mock

import db_conn
from repo_oracle import scheduler_schedules
from repo_oracle.scheduler_schedules import OcorrenciaDuplicada, RepoSchedulerAgenda
from repo_oracle.scheduler_queue import RepoSchedulerFila
from test_scheduler_queue import _Conn, _Erro

AGENTE = "srv-01"
ATOR = "SYSTEM:srv-01"
ANTIGA = datetime.datetime(2026, 10, 20, 3, 0, 0)
NOVA = datetime.datetime(2026, 10, 21, 3, 0, 0, 123456)
REGRA = {"id": 9, "script_id": 3, "environment": "PRD"}
TICKET = {"requested_by": "ana", "priority": 2, "submitted_params": "{\"versao\": 4}",
          "scheduled_at": datetime.datetime(2026, 10, 20, 3, 0, 0, 999999)}


class _Tipos(object):
    """Captura os setinputsizes por cursor (definir_tipos_entrada)."""

    def __init__(self):
        self.chamadas = []

    def __call__(self, cursor, **mapa):
        self.chamadas.append(dict(mapa))


class TestAgendaSemBanco(unittest.TestCase):

    def setUp(self):
        self.repo = RepoSchedulerAgenda("OWN_X", "pfx_")
        self.tipos = _Tipos()
        p = mock.patch.object(db_conn, "definir_tipos_entrada", self.tipos)
        p.start()
        self.addCleanup(p.stop)

    def _sem_transacao(self, conn):
        self.assertEqual((conn.commits, conn.rollbacks), (0, 0), "o COMMIT unico e de quem chama (passo 8)")

    def test_pagina_e_trava(self):
        conn = _Conn([("ROWNUM <= :lote", (2, [(5, ANTIGA), (7, ANTIGA)])), ("SKIP LOCKED", (1, [(5,)]))])
        self.assertEqual(self.repo.regras_vencidas(conn, 50), [(5, ANTIGA), (7, ANTIGA)])
        sql, binds = conn.executados[0]
        for trecho in ("WHERE active = 'Y' AND next_run_at <= SYSDATE",
                       "(next_run_at > :ult_prox OR (next_run_at = :ult_prox AND id > :ult_id))",
                       "ORDER BY next_run_at, id", "OWN_X.pfx_schedules"):
            self.assertIn(trecho, sql)
        self.assertEqual(binds, {"ult_prox": scheduler_schedules.DATA_INICIAL, "ult_id": 0, "lote": 50})
        self.repo.regras_vencidas(conn, 50, ult_prox=NOVA, ult_id=5)
        self.assertEqual(conn.executados[1][1]["ult_prox"], NOVA.replace(microsecond=0))
        self.assertEqual(self.tipos.chamadas[0], {"ult_prox": db_conn.TIPO_DATE})
        self.assertTrue(self.repo.travar_regra(conn, 5))
        self.assertIn("FOR UPDATE SKIP LOCKED", conn.executados[-1][0])
        self.assertFalse(self.repo.travar_regra(_Conn([]), 5), "sem linha: outro agente a processa")
        self._sem_transacao(conn)

    def test_reserva_sem_updated_e_ticket_com_ocorrencia(self):
        conn = _Conn([("SET next_run_at = :nova_data, last_run_at = SYSDATE", (1, []))])
        self.assertTrue(self.repo.reservar_e_criar_ticket(conn, REGRA, ANTIGA, NOVA, 501, TICKET,
                                                          [{"parameter_id": 4, "answer_value": "x"}], AGENTE))
        upd, b_upd = conn.executados[0]
        self.assertNotIn("updated_", upd, "a reserva e rotina tecnica (CR-006)")
        self.assertIn("WHERE id = :id AND active = 'Y' AND next_run_at = :antiga_data", upd)
        self.assertEqual((b_upd["nova_data"], b_upd["antiga_data"], b_upd["ticket_id"]),
                         (NOVA.replace(microsecond=0), ANTIGA, 501))
        self.assertIn({"nova_data": db_conn.TIPO_DATE, "antiga_data": db_conn.TIPO_DATE}, self.tipos.chamadas)
        ins = [e for e in conn.executados if e[0].startswith("INSERT INTO OWN_X.pfx_tickets")][0]
        self.assertIn("NULL, 'PENDING'", ins[0], "ip_origem nulo")
        self.assertEqual((ins[1]["scheduled_at"], ins[1]["actor"], ins[1]["schedule_id"], ins[1]["id"]),
                         (TICKET["scheduled_at"].replace(microsecond=0), ATOR, 9, 501))
        resp = [e for e in conn.executados if e[0].startswith("INSERT INTO OWN_X.pfx_ticket_answer")][0]
        self.assertEqual((resp[1]["ticket_id"], resp[1]["actor"], resp[1]["valor"]), (501, ATOR, "x"))
        self._sem_transacao(conn)
        corrida = _Conn([])
        self.assertFalse(self.repo.reservar_e_criar_ticket(corrida, REGRA, ANTIGA, NOVA, 502, TICKET, [], AGENTE))
        self.assertEqual(corrida.sql("INSERT"), [], "rowcount 0: nenhum ticket")

    def test_ocorrencia_duplicada(self):
        erro = _Erro("ORA-00001: unique constraint (OWN_X.IX_PFX_TCK_OCCUR) violated")
        conn = _Conn([("SET next_run_at = :nova_data", (1, [])), ("INSERT INTO OWN_X.pfx_tickets", erro)])
        with self.assertRaises(OcorrenciaDuplicada):
            self.repo.reservar_e_criar_ticket(conn, REGRA, ANTIGA, NOVA, 503, TICKET, [], AGENTE)
        outro = _Erro("ORA-00001: unique constraint (OWN_X.PK_PFX_TICKETS) violated")
        conn = _Conn([("SET next_run_at = :nova_data", (1, [])), ("INSERT INTO OWN_X.pfx_tickets", outro)])
        with self.assertRaises(_Erro):
            self.repo.reservar_e_criar_ticket(conn, REGRA, ANTIGA, NOVA, 503, TICKET, [], AGENTE)

    def test_conclusoes_mantem_proxima_execucao(self):
        conn = _Conn([("pause_reason = 'COMPLETED'", (1, []))])
        self.assertTrue(self.repo.concluir_com_ticket(conn, REGRA, ANTIGA, 601, TICKET, [], AGENTE))
        upd, b = conn.executados[0]
        self.assertIn("last_run_at = SYSDATE, last_ticket_id = :ticket_id, updated_at = SYSDATE", upd)
        self.assertNotIn("next_run_at =", upd.split("WHERE")[0], "nao grava NULL nem muda a data (D1)")
        self.assertEqual((b["antiga_data"], b["actor"]), (ANTIGA, ATOR))
        aud = [e for e in conn.executados if "SCHEDULE_PAUSE" in e[0]][0]
        self.assertEqual(aud[1]["detail"], "pause_reason: COMPLETED")
        self.assertTrue(conn.sql("INSERT INTO OWN_X.pfx_tickets"))
        conn = _Conn([("pause_reason = 'COMPLETED'", (1, []))])
        self.assertTrue(self.repo.concluir_sem_ticket(conn, 9, ANTIGA, AGENTE))
        upd = conn.executados[0][0]
        self.assertNotIn("last_run_at", upd)
        self.assertNotIn("last_ticket_id", upd)
        self.assertEqual(conn.sql("INSERT INTO OWN_X.pfx_tickets"), [])
        self.assertFalse(self.repo.concluir_sem_ticket(_Conn([]), 9, ANTIGA, AGENTE))
        self._sem_transacao(conn)

    def test_avanco_pausa_cron_erro_e_erro_interno(self):
        conn = _Conn([("SET next_run_at = :nova_data WHERE id", (1, []))])
        self.assertTrue(self.repo.avancar_sem_ticket(conn, 9, ANTIGA, NOVA))
        upd = conn.executados[0][0]
        for ausente in ("last_run_at", "last_ticket_id", "updated_"):
            self.assertNotIn(ausente, upd, "R-05")
        conn = _Conn([("pause_reason = :reason", (1, []))])
        self.assertTrue(self.repo.pausar(conn, 9, ANTIGA, "NO_PERMISSION", "solicitante sem acesso", AGENTE))
        self.assertIn("AND active = 'Y' AND next_run_at = :antiga_data", conn.executados[0][0], "R-19")
        aud = [e for e in conn.executados if "SCHEDULE_PAUSE" in e[0]][0][1]
        self.assertEqual((aud["detail"], aud["rid"], aud["actor"]),
                         ("pause_reason: NO_PERMISSION; solicitante sem acesso", 9, ATOR))
        ja = _Conn([])
        self.assertFalse(self.repo.pausar(ja, 9, ANTIGA, "NO_PERMISSION", None, AGENTE))
        self.assertEqual(ja.sql("SCHEDULE_PAUSE"), [], "rowcount 0: sem auditoria")
        for ticket_id in (None, 701):
            conn = _Conn([("pause_reason = 'INVALID_CRON'", (1, []))])
            self.assertTrue(self.repo.pausar_cron_erro(conn, REGRA, ANTIGA, ticket_id, TICKET, [], "horizonte", AGENTE))
            upd, b = conn.executados[0]
            self.assertIn("NVL(:ticket_id, last_ticket_id)", upd)
            self.assertNotIn("SET next_run_at", upd)
            self.assertEqual(b["ticket_id"], ticket_id)
            self.assertEqual(bool(conn.sql("INSERT INTO OWN_X.pfx_tickets")), ticket_id is not None)
        conn = _Conn([("pause_reason = 'INTERNAL_ERROR'", (1, []))])
        self.assertTrue(self.repo.pausar_erro_interno(conn, 9, "ValueError", AGENTE))
        self.assertIn("WHERE id = :id AND active = 'Y'", conn.executados[0][0])
        with self.assertRaises(ValueError):
            self.repo.pausar(_Conn([("pause_reason = :reason", (1, []))]), 9, ANTIGA, "INVALID_PARAM", "x" * 1000,
                             AGENTE)
        self._sem_transacao(conn)

    def test_prefixo_e_owner_parametrizados(self):
        conn = _Conn([])
        RepoSchedulerAgenda("outro", "abcdefg_").regras_vencidas(conn, 10)
        self.assertIn("outro.abcdefg_schedules", conn.executados[0][0])
        self.assertNotIn("tbsss_", conn.executados[0][0])


class TestFilaNodeOfflineSemBanco(unittest.TestCase):

    def setUp(self):
        self.repo = RepoSchedulerFila("OWN_X", "pfx_")

    def test_duas_etapas_sem_os_proprios_e_com_ator(self):
        conn = _Conn([("SELECT SYSDATE FROM DUAL", (1, [(ANTIGA,)])), ("FOR UPDATE SKIP LOCKED", (2, [(4,), (5,)]))],
                     contagens={4: 1, 5: 0})
        vistos = []
        ids = self.repo.marcar_node_offline(conn, AGENTE, 180, lambda agora: vistos.append(agora) or False)
        self.assertEqual((ids, vistos), ([4], [ANTIGA]), "a linha ja finalizada (rowcount 0) nao conta")
        sel = [s for s in conn.sql("SKIP LOCKED")][0]
        self.assertIn("<> :agent_id", sel)
        self.assertIn("heartbeat_at < SYSDATE - :node_offline_timeout_s * INTERVAL '1' SECOND", sel)
        upd, linhas = [e for e in conn.executados if "NODE_OFFLINE" in e[0]][0]
        self.assertIn("updated_at = SYSDATE, updated_by = :actor", upd)
        self.assertEqual(linhas[0], {"actor": ATOR, "id": 4})
        self.assertEqual(conn.commits, 1)

    def test_salto_de_relogio_aborta_sem_marcar(self):
        conn = _Conn([("SELECT SYSDATE FROM DUAL", (1, [(ANTIGA,)]))])
        self.assertIsNone(self.repo.marcar_node_offline(conn, AGENTE, 180, lambda agora: True))
        self.assertEqual(conn.sql("SKIP LOCKED"), [], "R-10: nada lido nem marcado")

    def test_finalizar_fenced(self):
        conn = _Conn([("status_reason = :reason", (1, []))])
        self.assertTrue(self.repo.finalizar_fenced(conn, 7, AGENTE))
        self.assertEqual(conn.executados[0][1]["reason"], "FENCED")
        self.assertFalse(self.repo.finalizar_fenced(_Conn([]), 7, AGENTE), "ja NODE_OFFLINE: rowcount 0")


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestAgendaOracle(unittest.TestCase):
    """Operacoes reais com massa propria (README §2.5)."""

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
        self.contrato.setUp(self)
        self._massa = self.trc._Massa(self.obter_repo)
        self.c = self._massa.cenario()
        cat = self.obter_repo("catalogo")
        self.cat = cat
        self.repo = RepoSchedulerAgenda(cat._owner, cat._prefixo)
        self.fila = RepoSchedulerFila(cat._owner, cat._prefixo)
        self.conn = cat._obter_conexao()
        self.addCleanup(self.conn.close)
        self.agente = "tst-agd-%s" % self._massa.suf
        self.ator = "SYSTEM:%s" % self.agente

    def tearDown(self):
        self.conn.rollback()
        cur = self.conn.cursor()
        aud = self.cat.qualificar_tabela("auditoria")
        for rid in self._massa.criados["agendamentos"]:
            cur.execute("DELETE FROM " + aud + " WHERE entity = 'tbsss_schedules' AND entity_id = :id", id=rid)
        self.conn.commit()
        self.contrato.tearDown(self)

    def _regra(self, minutos_atras=10, **extra):
        proxima = datetime.datetime.now().replace(second=0, microsecond=0) - datetime.timedelta(minutes=minutos_atras)
        return self._massa.agendamento(self.c["scr"]["id"], self.c["amb1"]["name"], self.c["u1"]["id"],
                                       next_run_at=proxima, **extra)

    def _ticket(self, regra, scheduled):
        return {"requested_by": self.c["login"], "priority": 2, "submitted_params": "{\"versao\": 4}",
                "scheduled_at": scheduled}

    def _linha(self, rid):
        return self.repo.carregar_regra(self.conn, rid)

    def test_microssegundos_nao_travam_a_reserva(self):
        """Teste obrigatorio (README §7.5): antiga/nova com microssegundos nao resultam em rowcount 0."""
        regra = self._regra()
        lida = self._linha(regra["id"])
        antiga = lida["next_run_at"].replace(microsecond=654321)
        nova = (lida["next_run_at"] + datetime.timedelta(days=1)).replace(microsecond=123456)
        tid = self.repo.proximo_ticket_id(self.conn)
        self.assertIn((regra["id"], lida["next_run_at"]), self.repo.regras_vencidas(self.conn, 1000))
        self.assertTrue(self.repo.travar_regra(self.conn, regra["id"]))
        self.assertTrue(self.repo.reservar_e_criar_ticket(self.conn, lida, antiga, nova, tid,
                                                          self._ticket(lida, antiga), [], self.agente))
        self.conn.commit()
        self._massa.anotar("tickets", tid)
        depois = self._linha(regra["id"])
        self.assertEqual((depois["next_run_at"], depois["last_ticket_id"]), (nova.replace(microsecond=0), tid))
        self.assertIsNone(depois["updated_at"], "reserva sem updated_* (CR-006)")
        t = self.obter_repo("tickets").obter(tid)
        self.assertEqual((t["schedule_id"], t["created_by"], t["scheduled_at"], t["source_ip"]),
                         (regra["id"], self.ator, antiga.replace(microsecond=0), None))
        # A mesma ocorrencia de novo: ix_tck_ocor recusa (CR-008, R-31).
        tid2 = self.repo.proximo_ticket_id(self.conn)
        with self.assertRaises(OcorrenciaDuplicada):
            self.repo._inserir_ticket(self.conn, lida, tid2, self._ticket(lida, antiga), [], self.ator)
        self.conn.rollback()

    def test_unica_concluida_mantem_a_data(self):
        regra = self._regra(recurrence_type="ONCE", run_time=None)
        lida = self._linha(regra["id"])
        tid = self.repo.proximo_ticket_id(self.conn)
        self.assertTrue(self.repo.travar_regra(self.conn, regra["id"]))
        self.assertTrue(self.repo.concluir_com_ticket(self.conn, lida, lida["next_run_at"], tid,
                                                      self._ticket(lida, lida["next_run_at"]), [], self.agente))
        self.conn.commit()
        self._massa.anotar("tickets", tid)
        depois = self._linha(regra["id"])
        self.assertEqual((depois["active"], depois["pause_reason"], depois["next_run_at"], depois["last_ticket_id"]),
                         ("N", "COMPLETED", lida["next_run_at"], tid))
        self.assertEqual(depois["updated_by"], self.ator)
        self.assertFalse(self.repo.pausar(self.conn, regra["id"], lida["next_run_at"], "NO_PERMISSION", None,
                                          self.agente), "pausa sobre regra concluida: rowcount 0")
        self.conn.rollback()

    def test_pausa_avanco_cron_erro_e_erro_interno(self):
        r1, r2, r3, r4 = self._regra(), self._regra(), self._regra(), self._regra()
        l1, l2, l3 = self._linha(r1["id"]), self._linha(r2["id"]), self._linha(r3["id"])
        nova = l2["next_run_at"] + datetime.timedelta(days=1)
        self.assertTrue(self.repo.pausar(self.conn, r1["id"], l1["next_run_at"], "INVALID_PARAM",
                                         "data_ref: formato", self.agente))
        self.assertTrue(self.repo.avancar_sem_ticket(self.conn, r2["id"], l2["next_run_at"], nova))
        self.assertTrue(self.repo.pausar_cron_erro(self.conn, l3, l3["next_run_at"], None, None, [], "horizonte",
                                                   self.agente))
        self.assertTrue(self.repo.pausar_erro_interno(self.conn, r4["id"], "ValueError", self.agente))
        self.conn.commit()
        d1, d2, d3, d4 = (self._linha(r["id"]) for r in (r1, r2, r3, r4))
        self.assertEqual((d1["active"], d1["pause_reason"], d1["updated_by"]), ("N", "INVALID_PARAM", self.ator))
        self.assertEqual((d2["active"], d2["next_run_at"], d2["updated_at"], d2["last_ticket_id"]),
                         ("Y", nova, None, l2["last_ticket_id"]))
        self.assertEqual((d3["pause_reason"], d3["next_run_at"]), ("INVALID_CRON", l3["next_run_at"]))
        self.assertEqual(d4["pause_reason"], "INTERNAL_ERROR")
        cur = self.conn.cursor()
        cur.execute("SELECT detail FROM " + self.cat.qualificar_tabela("auditoria") + " WHERE action = 'SCHEDULE_PAUSE'"
                    " AND entity_id = :id", id=r1["id"])
        self.assertEqual([x[0] for x in cur.fetchall()], ["pause_reason: INVALID_PARAM; data_ref: formato"])

    def test_node_offline_e_fenced(self):
        outro, meu = "tst-agd-%s-o" % self._massa.suf, self.agente
        t_outro, t_meu = (self._massa.ticket(actor="teste", script_id=self.c["scr"]["id"], environment=self.c["amb1"]["name"],
                                             requested_by=self.c["login"]) for _i in range(2))
        cur = self.conn.cursor()
        tck = self.cat.qualificar_tabela("tickets")
        for tid, ag in ((t_outro, outro), (t_meu, meu)):
            cur.execute("UPDATE " + tck + " SET status = 'RUNNING', agent_id = :a, heartbeat_at = SYSDATE - 1"
                        " WHERE id = :id", a=ag, id=tid)
        self.conn.commit()
        self.assertIsNone(self.fila.marcar_node_offline(self.conn, meu, 180, lambda agora: True), "salto: nada")
        marcados = self.fila.marcar_node_offline(self.conn, meu, 180, lambda agora: False)
        self.assertIn(t_outro, marcados)
        self.assertNotIn(t_meu, marcados, "nunca os proprios")
        t = self.obter_repo("tickets").obter(t_outro)
        self.assertEqual((t["status"], t["status_reason"], t["return_code"], t["updated_by"]),
                         ("FAILED", "NODE_OFFLINE", -2, "SYSTEM:%s" % meu))
        self.assertTrue(self.fila.finalizar_fenced(self.conn, t_meu, meu))
        self.assertEqual(self.obter_repo("tickets").obter(t_meu)["status_reason"], "FENCED")
        self.assertFalse(self.fila.finalizar_fenced(self.conn, t_outro, outro), "ja NODE_OFFLINE")


if __name__ == "__main__":
    unittest.main()
