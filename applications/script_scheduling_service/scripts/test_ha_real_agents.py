# -*- coding: utf-8 -*-
"""F8.4e: alta disponibilidade com dois agentes reais (scripts/run_scheduler.py) contra o Oracle.

Com SSS_TEST_ORACLE=1, a fixture do F8.3d (_DoisAgentesBase: dados proprios, um config.ini por agente, limpeza
unica depois de derrubar os agentes) e tempos de fencing reduzidos dentro das invariantes I1 a I4 (README §8.9):
call 5 s, heartbeat 2 s, fence 12 s, kill_grace 2 s e node_offline 24 s.

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

from test_agents_concurrency import MARCA_LONGO, _DoisAgentesBase

MINUTOS = 3
NODE_OFFLINE_S = 24


def _vivo(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            conteudo = f.read()
    except OSError:
        return False
    return conteudo[conteudo.rindex(")") + 2:].split()[0] != "Z"


def _pids_do_longo():
    saida = subprocess.run(["ps", "-eo", "pid=,args="], stdout=subprocess.PIPE).stdout.decode("utf-8", "replace")
    return [int(l.split(None, 1)[0]) for l in saida.splitlines() if l.split(None, 1)[1:] == ["sleep %d" % MARCA_LONGO]]


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestHaDoisAgentes(_DoisAgentesBase):

    PREFIXO_AGENTE = "tst-f84e"
    CONFIG_EXTRA = {
        "oracle": {"call_timeout_ms": "5000"},
        "agent": {"heartbeat_interval_s": "2", "fence_timeout_s": "12", "kill_grace_s": "2",
                  "node_offline_timeout_s": str(NODE_OFFLINE_S)},
    }

    def test_cron_por_minuto_gera_um_ticket_por_minuto(self):
        agora = self._consulta("SELECT SYSDATE FROM DUAL")[0][0]
        primeira = agora.replace(second=0) + datetime.timedelta(minutes=1)
        regra = self._massa.agendamento(self.scr["id"], self.amb["name"], self.usuario_id, recurrence_type="CRON",
                                        cron_expression="* * * * *", run_time=None, params_json="{}",
                                        start_date=agora - datetime.timedelta(minutes=1), next_run_at=primeira)
        for agente in self.agents:
            self._subir(agente)
        fim = primeira + datetime.timedelta(minutes=MINUTOS - 1)

        def ocorrencias():
            return self._consulta("SELECT scheduled_at, COUNT(*) FROM {tck} WHERE schedule_id = :r"
                                  " GROUP BY scheduled_at ORDER BY scheduled_at", r=regra["id"])
        self.assertTrue(self._esperar(lambda: any(s >= fim for s, _n in ocorrencias()), MINUTOS * 60 + 60, passo=2),
                        "tickets das %d ocorrencias" % MINUTOS)
        for agente, p, _pastas in self.processos:
            self.assertIsNone(p.poll(), "agente %s caiu" % agente)
        linhas = [(s, n) for s, n in ocorrencias() if s <= fim]
        self.assertEqual([s for s, _n in linhas], [primeira + datetime.timedelta(minutes=i) for i in range(MINUTOS)],
                         "uma ocorrencia por minuto, sem buracos")
        self.assertEqual(set(n for _s, n in linhas), {1}, "sem duplicata entre os dois agentes")
        criadores = self._consulta("SELECT DISTINCT created_by FROM {tck} WHERE schedule_id = :r", r=regra["id"])
        self.assertTrue(set(c for (c,) in criadores) <= set("SYSTEM:%s" % a for a in self.agents))
        print("\n[F8.4e] CRON: %d ocorrencias, criadores %s" % (len(linhas), sorted(c for (c,) in criadores)))

    def test_kill_9_node_offline_e_orfao_encerrado_na_religacao(self):
        tid = self._ticket(self.scr_longo)
        for agente in self.agents:
            self._subir(agente)
        self.assertTrue(self._esperar(lambda: (self._tickets({tid}).get(tid) or ("",))[0] == "RUNNING"
                                      and self._tickets({tid})[tid][4] is not None, 60), "longo RUNNING com PID")
        dono = self._tickets({tid})[tid][3]
        outro = [a for a in self.agents if a != dono][0]
        orfaos = _pids_do_longo()
        self.assertEqual(len(orfaos), 1)
        agente_dono, processo_dono, _pastas = [x for x in self.processos if x[0] == dono][0]
        os.kill(processo_dono.pid, signal.SIGKILL)  # so o PID do agente criado pela fixture (POSIX)
        processo_dono.wait(10)
        inicio = time.monotonic()
        self.assertTrue(_vivo(orfaos[0]), "o filho sobrevive a morte do agente")
        self.assertTrue(self._esperar(lambda: self._tickets({tid})[tid][0] == "FAILED", NODE_OFFLINE_S + 60, passo=1),
                        "NODE_OFFLINE pelo outro agente")
        decorrido = time.monotonic() - inicio
        estado = self._tickets({tid})[tid]
        self.assertEqual(estado[:3], ("FAILED", "NODE_OFFLINE", -2))
        atualizado = self._consulta("SELECT updated_by FROM {tck} WHERE id = :id", id=tid)[0][0]
        self.assertEqual(atualizado, "SYSTEM:%s" % outro, "marcado pelo agente que detectou")
        self.assertGreaterEqual(decorrido, NODE_OFFLINE_S - 2 - 3, "so depois de node_offline_timeout_s")
        # Religacao do agente morto: o startup check acha o .sss_proc e encerra o filho (README §8.12, passo 9).
        self.processos = [x for x in self.processos if x[0] != dono]
        self._subir(dono)
        self.assertTrue(self._esperar(lambda: not _vivo(orfaos[0]), 60), "filho encerrado na religacao")
        ativos = self._consulta("SELECT code, status FROM {agt} WHERE code IN (:a, :b)",
                                a=self.agents[0], b=self.agents[1])
        self.assertEqual(sorted(ativos), [(a, "ACTIVE") for a in sorted(self.agents)], "religacao aceita (PID antigo morto)")
        print("\n[F8.4e] kill -9 em %s: NODE_OFFLINE por %s em %.0f s; filho %d encerrado na religacao"
              % (dono, outro, decorrido, orfaos[0]))
        self.assertEqual(_pids_do_longo(), [])


if __name__ == "__main__":
    unittest.main()
