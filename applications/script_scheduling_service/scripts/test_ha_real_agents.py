# -*- coding: utf-8 -*-
"""F8.4e: alta disponibilidade com dois agentes reais (scripts/run_scheduler.py) contra o Oracle.

Com SSS_TEST_ORACLE=1, a fixture do F8.3d (_TwoAgentsBase: dados proprios, um config.ini por agente, limpeza
unica depois de derrubar os agentes) e tempos de fencing reduzidos dentro das invariantes I1 a I4 (README §8.9):
call 5 s, heartbeat 2 s, fence 12 s, kill_grace_s 2 s e node_offline 24 s.

* CRON '* * * * *' por 3 minutos com os dois agentes: exatamente 1 ticket por minuto, sem duplicata (README §7.5).
* kill -9 no agente dono durante uma execucao: o outro marca NODE_OFFLINE depois de node_offline_timeout_s
  (README §8.8); o filho que ficou vivo e encerrado pelo startup check quando o agente sobe de novo (§8.12).
"""
import _testenv  # noqa: F401

import datetime
import os
import signal
import subprocess
import time
import unittest

from test_agents_concurrency import LONG_MARK, _TwoAgentsBase

MINUTES = 3
NODE_OFFLINE_S = 24


def _alive(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            content = f.read()
    except OSError:
        return False
    return content[content.rindex(")") + 2:].split()[0] != "Z"


def _long_pids():
    output = subprocess.run(["ps", "-eo", "pid=,args="], stdout=subprocess.PIPE).stdout.decode("utf-8", "replace")
    return [int(l.split(None, 1)[0]) for l in output.splitlines() if l.split(None, 1)[1:] == ["sleep %d" % LONG_MARK]]


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestHaTwoAgents(_TwoAgentsBase):

    AGENT_PREFIX = "tst-f84e"
    CONFIG_EXTRA = {
        "oracle": {"call_timeout_ms": "5000"},
        "agent": {"heartbeat_interval_s": "2", "fence_timeout_s": "12", "kill_grace_s": "2",
                  "node_offline_timeout_s": str(NODE_OFFLINE_S)},
    }

    def test_cron_por_minuto_gera_um_ticket_por_minuto(self):
        now = self._query("SELECT SYSDATE FROM DUAL")[0][0]
        first = now.replace(second=0) + datetime.timedelta(minutes=1)
        rule = self._fixtures.schedule(self.scr["id"], self.amb["name"], self.usuario_id, recurrence_type="CRON",
                                        cron_expression="* * * * *", run_time=None, params_json="{}",
                                        start_date=now - datetime.timedelta(minutes=1), next_run_at=first)
        for agent in self.agents:
            self._start_agent(agent)
        end = first + datetime.timedelta(minutes=MINUTES - 1)

        def ocorrencias():
            return self._query("SELECT scheduled_at, COUNT(*) FROM {tck} WHERE schedule_id = :r"
                                  " GROUP BY scheduled_at ORDER BY scheduled_at", r=rule["id"])
        self.assertTrue(self._wait(lambda: any(s >= end for s, _n in ocorrencias()), MINUTES * 60 + 60, step=2),
                        "tickets das %d ocorrencias" % MINUTES)
        for agent, p, _dirs in self.processes:
            self.assertIsNone(p.poll(), "agente %s caiu" % agent)
        rows = [(s, n) for s, n in ocorrencias() if s <= end]
        self.assertEqual([s for s, _n in rows], [first + datetime.timedelta(minutes=i) for i in range(MINUTES)],
                         "uma ocorrencia por minuto, sem buracos")
        self.assertEqual(set(n for _s, n in rows), {1}, "sem duplicata entre os dois agentes")
        creators = self._query("SELECT DISTINCT created_by FROM {tck} WHERE schedule_id = :r", r=rule["id"])
        self.assertTrue(set(c for (c,) in creators) <= set("SYSTEM:%s" % a for a in self.agents))
        print("\n[F8.4e] CRON: %d ocorrencias, criadores %s" % (len(rows), sorted(c for (c,) in creators)))

    def test_kill_9_node_offline_e_orfao_encerrado_na_religacao(self):
        tid = self._ticket(self.scr_longo)
        for agent in self.agents:
            self._start_agent(agent)
        self.assertTrue(self._wait(lambda: (self._tickets({tid}).get(tid) or ("",))[0] == "RUNNING"
                                      and self._tickets({tid})[tid][4] is not None, 60), "longo RUNNING com PID")
        owner = self._tickets({tid})[tid][3]
        other = [a for a in self.agents if a != owner][0]
        orphans = _long_pids()
        self.assertEqual(len(orphans), 1)
        agent_owner, process_owner, _dirs = [x for x in self.processes if x[0] == owner][0]
        os.kill(process_owner.pid, signal.SIGKILL)  # so o PID do agente criado pela fixture (POSIX)
        process_owner.wait(10)
        start = time.monotonic()
        self.assertTrue(_alive(orphans[0]), "o filho sobrevive a morte do agente")
        self.assertTrue(self._wait(lambda: self._tickets({tid})[tid][0] == "FAILED", NODE_OFFLINE_S + 60, step=1),
                        "NODE_OFFLINE pelo outro agente")
        elapsed = time.monotonic() - start
        state = self._tickets({tid})[tid]
        self.assertEqual(state[:3], ("FAILED", "NODE_OFFLINE", -2))
        updated = self._query("SELECT updated_by FROM {tck} WHERE id = :id", id=tid)[0][0]
        self.assertEqual(updated, "SYSTEM:%s" % other, "marcado pelo agente que detectou")
        self.assertGreaterEqual(elapsed, NODE_OFFLINE_S - 2 - 3, "so depois de node_offline_timeout_s")
        # Religacao do agente morto: o startup check acha o .sss_proc e encerra o filho (README §8.12, passo 9).
        self.processes = [x for x in self.processes if x[0] != owner]
        self._start_agent(owner)
        self.assertTrue(self._wait(lambda: not _alive(orphans[0]), 60), "filho encerrado na religacao")
        active = self._query("SELECT code, status FROM {agt} WHERE code IN (:a, :b)",
                                a=self.agents[0], b=self.agents[1])
        self.assertEqual(sorted(active), [(a, "ACTIVE") for a in sorted(self.agents)], "religacao aceita (PID antigo morto)")
        print("\n[F8.4e] kill -9 em %s: NODE_OFFLINE por %s em %.0f s; filho %d encerrado na religacao"
              % (owner, other, elapsed, orphans[0]))
        self.assertEqual(_long_pids(), [])


if __name__ == "__main__":
    unittest.main()
