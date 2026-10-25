# -*- coding: utf-8 -*-
"""Contrato do repositorio da pasta de entrada (CR-020b; README §10 tabelas 19 a 21), contra o FAKE (sempre) e o
Oracle real (SSS_TEST_ORACLE=1), com dados proprios de cada teste: ambientes, script e agentes de teste."""
from tests.support import _testenv  # noqa: F401
import hashlib
import json
import unittest

import repo_factory
import repo_inputs
from repo_errors import RepoNotFound, RepoViolation
from repo_inputs import NoLiveAgent
from tests.unit.persistence.test_repo_contract import _Fixtures

LIVE_S = 300
CONTENT = (b"linha;valor\n" + b"1;10\n" * 50000)  # ~250 KB: mais de uma parte com partes pequenas


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class BaseInputsContract(object):
    """Bateria agnostica ao backend; os agentes de teste sao criados por agent() e removidos no fim."""

    def setUp_scenario(self):
        self.m = _Fixtures(self.obter_repo)
        self.env = self.m.environment("A")["name"]
        self.other_env = self.m.environment("B")["name"]
        self.script = self.m.script("in")["id"]
        self.repo = self.obter_repo("inputs")
        self.a1 = "tst%s1" % self.m.suf
        self.a2 = "tst%s2" % self.m.suf
        self.agent(self.a1, "%s,%s" % (self.other_env, self.env))
        self.agent(self.a2, self.env)
        self.agent("tst%s3" % self.m.suf, self.other_env)  # outro ambiente
        self.agent("tst%s4" % self.m.suf, self.env, stale=True)  # sem heartbeat recente

    def data(self, **extra):
        return dict({"environment": self.env, "script_id": self.script, "relative_dir": "lotes/2026",
                     "file_name": u"relatório.csv", "sha256": _sha(CONTENT), "replace_existing": "N"}, **extra)

    def test_sem_agente_vivo_recusa_sem_gravar(self):
        self.agent("tst%s5" % self.m.suf, self.m.environment("C")["name"], stale=True)
        env_c = "TST_%s_C" % self.m.suf
        with self.assertRaises(NoLiveAgent):
            self.repo.create_upload(self.data(environment=env_c), CONTENT, self.m.actor, "10.0.0.1", LIVE_S)
        self.assertEqual(self.repo.uploads(env_c, self.script)["total"], 0)
        self.assertEqual(self.repo.request_listing(env_c, self.script, self.m.actor, LIVE_S), 0)

    def test_envio_com_uma_entrega_por_agente_vivo_e_auditoria(self):
        result = self.repo.create_upload(self.data(), CONTENT, self.m.actor, "10.0.0.1", LIVE_S)
        self.assertEqual(result["agents"], sorted([self.a1, self.a2]), "so os vivos do ambiente")
        page = self.repo.uploads(self.env, self.script)
        self.assertEqual(page["total"], 1)
        item = page["items"][0]
        self.assertNotIn("content", item)
        self.assertEqual((item["file_name"], item["relative_dir"], item["size_bytes"], item["replace_existing"],
                          item["created_by"]), (u"relatório.csv", "lotes/2026", len(CONTENT), "N", self.m.actor))
        self.assertEqual([(d["agent_id"], d["state"], d["reason"]) for d in item["deliveries"]],
                         [(self.a1, "PENDING", None), (self.a2, "PENDING", None)])
        audit = self.obter_repo("audit").list(filters={"action": "INPUT_UPLOAD", "entity": "tbsss_input_upload",
                                                       "entity_id": result["id"]}, page=1, size=1)["items"]
        self.assertEqual(len(audit), 1)
        self.assertIn(self.a2, audit[0]["detail"])
        # conteudo so em partes de ate 1 MiB
        read, off = b"", 0
        while True:
            part = self.repo.read_content(result["id"], off, 100000)
            if not part:
                break
            read, off = read + part, off + len(part)
        self.assertEqual(read, CONTENT)
        for off, size in ((-1, 10), (0, 0), (0, repo_inputs.PART_MAX + 1)):
            with self.assertRaises(RepoViolation):
                self.repo.read_content(result["id"], off, size)
        with self.assertRaises(RepoNotFound):
            self.repo.read_content(999999999, 0, 10)

    def test_script_inexistente_recusado_pela_fk(self):
        with self.assertRaises(RepoViolation):
            self.repo.create_upload(self.data(script_id=999999999), CONTENT, self.m.actor, None, LIVE_S)
        self.assertEqual(self.repo.uploads(self.env, self.script)["total"], 0)

    def test_entrega_so_pelo_proprio_agente(self):
        uid = self.repo.create_upload(self.data(), CONTENT, self.m.actor, None, LIVE_S)["id"]
        p1 = [d for d in self.repo.pending_deliveries(self.a1) if d["upload_id"] == uid]
        p2 = [d for d in self.repo.pending_deliveries(self.a2) if d["upload_id"] == uid]
        self.assertEqual(len(p1), 1)
        self.assertEqual((p1[0]["file_name"], p1[0]["sha256"], p1[0]["size_bytes"], p1[0]["environment"],
                          p1[0]["script_name"]),
                         (u"relatório.csv", _sha(CONTENT), len(CONTENT), self.env, "tst_scr_%s_in" % self.m.suf))
        self.assertNotIn("content", p1[0])
        self.assertFalse(self.repo.mark_delivery(p1[0]["id"], self.a2, "DELIVERED"), "entrega de outro agente")
        self.assertTrue(self.repo.mark_delivery(p1[0]["id"], self.a1, "DELIVERED"))
        self.assertFalse(self.repo.mark_delivery(p1[0]["id"], self.a1, "DELIVERED"), "ja marcada")
        for state, reason in (("FAILED", None), ("DELIVERED", "EXISTS"), ("FAILED", "OUTRO"), ("PENDING", None)):
            with self.assertRaises(RepoViolation):
                self.repo.mark_delivery(p2[0]["id"], self.a2, state, reason)
        self.assertTrue(self.repo.mark_delivery(p2[0]["id"], self.a2, "FAILED", "EXISTS"))
        self.assertEqual([d for d in self.repo.pending_deliveries(self.a1) if d["upload_id"] == uid], [])
        states = [(d["agent_id"], d["state"], d["reason"], d["delivered_at"] is not None)
                  for d in self.repo.uploads(self.env, self.script)["items"][0]["deliveries"]]
        self.assertEqual(states, [(self.a1, "DELIVERED", None, True), (self.a2, "FAILED", "EXISTS", True)])
        audits = self.obter_repo("audit").list(filters={"action": "INPUT_DELIVERY", "entity": "tbsss_input_upload",
                                                        "entity_id": uid}, page=1, size=10)["items"]
        self.assertEqual(sorted(a["actor"] for a in audits), ["SYSTEM:" + self.a1, "SYSTEM:" + self.a2])

    def test_retrato_pedido_publicado_e_pedido_de_novo(self):
        self.assertEqual(self.repo.listings(self.env, self.script), [])
        self.assertEqual(self.repo.request_listing(self.env, self.script, self.m.actor, LIVE_S), 2)
        rows = self.repo.listings(self.env, self.script)
        self.assertEqual([(r["agent_id"], r["listed_at"], r["refresh_requested_at"] is not None) for r in rows],
                         [(self.a1, None, True), (self.a2, None, True)])
        due = self.repo.listings_due(self.a1)
        self.assertIn({"environment": self.env, "script_id": self.script, "script_name": "tst_scr_%s_in" % self.m.suf},
                      due)
        listing = json.dumps([{"path": u"lotes/2026/relatório.csv", "size": 10, "mtime": "2026-10-23 10:00:00"}])
        self.repo.save_listing(self.a1, self.env, self.script, listing, 1, "N")
        rows = dict((r["agent_id"], r) for r in self.repo.listings(self.env, self.script))
        self.assertEqual(json.loads(rows[self.a1]["listing"])[0]["path"], u"lotes/2026/relatório.csv")
        self.assertEqual((rows[self.a1]["file_count"], rows[self.a1]["truncated"]), (1, "N"))
        self.assertIsNotNone(rows[self.a1]["listed_at"])
        self.assertIsNone(rows[self.a2]["listed_at"])
        # retrato sem pedido (o agente publica sozinho) e pedido de novo no mesmo segundo
        self.repo.save_listing(self.a2, self.env, self.script, "[]", 0, "Y")
        self.assertEqual(self.repo.listings(self.env, self.script)[1]["truncated"], "Y")
        self.repo.request_listing(self.env, self.script, self.m.actor, LIVE_S)
        self.assertIn(self.script, [d["script_id"] for d in self.repo.listings_due(self.a2)],
                      "pedido no mesmo segundo do retrato nao se perde")
        with self.assertRaises(RepoViolation):
            self.repo.save_listing(self.a1, self.env, self.script, "[]", 0, "X")


class TestRepoInputsFake(unittest.TestCase, BaseInputsContract):

    def setUp(self):
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configure, None)
        self.setUp_scenario()

    def obter_repo(self, name):
        return repo_factory.get(name)

    def agent(self, code, environments, stale=False):
        import datetime
        store = self.obter_repo("catalog")._store
        now = store.now()
        aid = store.next_id("tbsss_agents")
        store.agents[aid] = {"id": aid, "code": code, "hostname": "h", "environments": environments,
                             "status": "ACTIVE", "heartbeat_at": now - datetime.timedelta(seconds=3600 if stale else 5)}


if __name__ == "__main__":
    unittest.main()
