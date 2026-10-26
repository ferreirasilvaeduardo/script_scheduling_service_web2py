# -*- coding: utf-8 -*-
"""F8.3d: dois agentes reais (scripts/run_scheduler.py) contra o Oracle do instance/config.ini.

Com SSS_TEST_ORACLE=1 (README §2.5): esquema validado por prepare_disposable_schema('agent') antes de DML;
ambiente, perfil, usuario, scripts e tickets so da fixture; cada agente com o proprio config.ini temporario
(agent_id, work_dir, log_dir e output_dir proprios). Confere: nunca mais de 2 RUNNING do script de teto 2
(polling no banco), todos SUCCESS, cada ticket executado uma vez, saida DISPONIVEL gravada pelo agente dono,
cancelamento pela web encerrado pelo agente dono, heartbeat e parada pelo .stop, e nenhum processo orfao.
Limpa so os IDs criados (tickets, saidas em cascata, cadastros, agentes de teste e a auditoria deles).
"""
from tests.support import _testenv  # noqa: F401

import configparser
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile

APP = _testenv.APP_DIR
RUN_SCHEDULER = os.path.join(APP, "scripts", "run_scheduler.py")
N_TICKETS = 10
CAP = 2
LONG_MARK = 3017  # sleep exclusivo do script longo, para achar orfaos pelo argv


class _TwoAgentsBase(unittest.TestCase):
    """Fixture de dois agentes reais (F8.3d, reaproveitada no F8.4e por test_ha_real_agents)."""

    AGENT_PREFIX = "tst-f83d"
    CONFIG_EXTRA = {}

    @classmethod
    def setUpClass(cls):
        from tests.unit.persistence import test_repo_contract as trc
        from tests.support._oracle_test_support import prepare_disposable_schema
        prepare_disposable_schema("agent")
        cls.trc = trc
        cls.contrato = trc._OracleContract
        cls.contrato.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.contrato.tearDownClass.__func__(cls)

    def obter_repo(self, name):
        return self.contrato.obter_repo(self, name)

    def _clean_fixtures(self):
        return self.contrato._clean_fixtures(self)

    # ------------------------------------------------------------------ fixture

    def setUp(self):
        self.contrato.setUp(self)
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="sss_f83d_"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.processes = []
        self.profile = None
        self._fixtures = self.trc._Fixtures(self.obter_repo)
        self.agents = []
        # Uma limpeza so, mesmo com falha no meio: agentes parados antes de apagar qualquer cadastro.
        self.addCleanup(self._clean_all)
        m = self._fixtures
        self.amb = m.environment("C")
        scripts_dir = os.path.join(self.root, "scripts")
        os.mkdir(scripts_dir, 0o755)
        self.execucoes = os.path.join(self.root, "execucoes.txt")
        short = self._file(scripts_dir, "curto.sh",
                              "echo \"$SSS_TICKET_ID $SSS_AGENT_ID\" >> %s\n"
                              "echo \"ticket $SSS_TICKET_ID\" > \"$SSS_OUTPUT_DIR/resultado.txt\"\n"
                              "sleep 2\necho fim\n" % self.execucoes)
        long = self._file(scripts_dir, "longo.sh", "echo inicio\nsleep %d\n" % LONG_MARK)
        self.scr = m.script("curto", path_file=short, max_parallel_env=CAP)
        self.scr_longo = m.script("longo", path_file=long, max_parallel_env=1)
        cat, rbac = self.obter_repo("catalog"), self.obter_repo("rbac")
        for s in (self.scr, self.scr_longo):
            cat.homologation_save(s["id"], [self.amb["id"]], actor=m.actor)
        self.profile = profile = m.profile("P")
        features = [f["id"] for f in rbac.features_list() if f["code"] in ("EXEC_SCRIPT", "VIEW_LOGS", "CANCEL_TICKET")]
        rbac.matrix_save(profile["id"], features, [self.amb["id"]], [self.scr["id"], self.scr_longo["id"]], actor=m.actor)
        self.login = m.usuario(profile["id"], "u")["login"]
        self.usuario_id = [u for u in m.created["users"]][-1]
        self.agents = ["%s-%s-a" % (self.AGENT_PREFIX, m.suf), "%s-%s-b" % (self.AGENT_PREFIX, m.suf)]

    def tearDown(self):
        pass  # a limpeza e o _clean_all (addCleanup), depois de derrubar os agentes

    def _clean_all(self):
        self._kill_agents()
        self._clean_agents()
        m = self._fixtures
        cat, rbac = self.obter_repo("catalog"), self.obter_repo("rbac")
        if self.profile is not None:
            rbac.matrix_save(self.profile["id"], [], [], [], actor=m.actor)
        for sid in m.created["scripts"]:
            cat.homologation_save(sid, [], actor=m.actor)
        # Tickets gerados pelo desdobro das regras da fixture (F8.4e) entram na limpeza antes do usuario.
        for rid in m.created["schedules"]:
            for (tid,) in self._query("SELECT id FROM {tck} WHERE schedule_id = :r", r=rid):
                if tid not in m.created["tickets"]:
                    m.note("tickets", tid)
        self._clean_fixtures()

    def _file(self, folder, name, body):
        path = os.path.join(folder, name)
        with open(path, "w") as f:
            f.write(body)
        os.chmod(path, 0o644)
        return path

    def _snapshot(self, scr):
        return json.dumps({"version": 5, "script_id": scr["id"], "script_name": scr["name"], "interpreter": "SH",
                           "path_file": scr["path_file"], "param_type": "NAMED", "args": [], "answers": {},
                           "sensitive": [], "compiled_at": "2026-10-20 10:00:00"})

    def _ticket(self, scr):
        tid = self.obter_repo("tickets").create({
            "script_id": scr["id"], "environment": self.amb["name"], "requested_by": self.login, "status": "PENDING",
            "priority": 2, "submitted_params": self._snapshot(scr)}, [], actor=self.login)
        return self._fixtures.note("tickets", tid)

    def _config(self, agent):
        base = os.path.join(self.root, agent)
        dirs = dict((n, os.path.join(base, n)) for n in ("work", "logs", "output", "input"))
        for p in dirs.values():
            os.makedirs(p, 0o750, exist_ok=True)
        cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
        cp.read(os.path.join(APP, "instance", "config.ini"), encoding="utf-8")
        cp["agent"].update({"agent_id": agent, "environments": self.amb["name"], "work_dir": dirs["work"],
                            "exec_users": "", "exec_work_dir": "",
                            "max_parallel_jobs": "4", "orchestrator_interval_s": "1", "cancel_poll_interval_s": "1",
                            "output_dir": dirs["output"], "input_dir": dirs["input"],
                            "log_dir_min_free_mb": "0"})
        for section, values in self.CONFIG_EXTRA.items():
            cp[section].update(values)
        cp["logging"]["log_dir"] = dirs["logs"]
        path = os.path.join(base, "config.ini")
        with open(path, "w", encoding="utf-8") as f:
            cp.write(f)
        return path, dirs

    def _start_agent(self, agent):
        path, dirs = self._config(agent)
        output = open(os.path.join(self.root, agent + ".out"), "w")
        self.addCleanup(output.close)
        p = subprocess.Popen([sys.executable, RUN_SCHEDULER, "--config", path], cwd=APP, stdout=output,
                             stderr=subprocess.STDOUT, start_new_session=True)
        self.processes.append((agent, p, dirs))
        return p, dirs

    def _kill_agents(self):
        for agent, p, dirs in self.processes:
            if p.poll() is None:
                open(os.path.join(dirs["work"], "sss-%s.stop" % agent), "w").close()
        for agent, p, _dirs in self.processes:
            try:
                p.wait(60)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, 9)
                p.wait(10)

    def _clean_agents(self):
        """Linhas de tbsss_agents dos agentes de teste e a auditoria deles (AGENT_START/AGENT_STOP)."""
        cat = self.obter_repo("catalog")
        conn = cat._obter_conexao()
        try:
            cur = conn.cursor()
            agt, aud = cat.qualify_table("agents"), cat.qualify_table("audit")
            for code in self.agents:
                cur.execute("SELECT id FROM " + agt + " WHERE code = :c", c=code)
                for (aid,) in cur.fetchall():
                    cur.execute("DELETE FROM " + aud + " WHERE entity = 'tbsss_agents' AND entity_id = :id", id=aid)
                    cur.execute("DELETE FROM " + agt + " WHERE id = :id", id=aid)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ leituras

    def _query(self, sql, **binds):
        cat = self.obter_repo("catalog")
        conn = cat._obter_conexao()
        try:
            cur = conn.cursor()
            cur.execute(sql.format(tck=cat.qualify_table("tickets"), agt=cat.qualify_table("agents"),
                                   sai=cat.qualify_table("ticket_output")), binds)
            return cur.fetchall()
        finally:
            conn.close()

    def _tickets(self, ids):
        rows = self._query("SELECT id, status, status_reason, return_code, agent_id, process_id FROM {tck}"
                                " WHERE script_id IN (:a, :b)", a=self.scr["id"], b=self.scr_longo["id"])
        return dict((r[0], r[1:]) for r in rows if r[0] in ids)

    def _output_dirs(self, ids):
        names = set("ticket_%d" % t for t in ids)
        return [os.path.join(r, d) for _a, _p, dirs in self.processes
                for r, ds, _arqs in os.walk(dirs["output"]) for d in ds if d in names]

    def _wait(self, condition, deadline, step=0.2):
        limit = time.monotonic() + deadline
        while time.monotonic() < limit:
            if condition():
                return True
            time.sleep(step)
        return condition()


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestTwoAgentsConcurrency(_TwoAgentsBase):

    def test_dois_agentes_teto_saida_cancelamento_e_parada(self):
        short = [self._ticket(self.scr) for _i in range(N_TICKETS)]
        long = self._ticket(self.scr_longo)
        for agent in self.agents:
            self._start_agent(agent)

        # 1. Teto entre agentes: polling no banco ate todos os curtos terminarem.
        max_running = 0
        limit = time.monotonic() + 180
        while time.monotonic() < limit:
            running = self._query("SELECT COUNT(*) FROM {tck} WHERE script_id = :s AND status = 'RUNNING'",
                                     s=self.scr["id"])[0][0]
            max_running = max(max_running, running)
            state = self._tickets(set(short))
            if all(e[0] in ("SUCCESS", "FAILED", "CANCELLED") for e in state.values()):
                break
            for agent, p, _dirs in self.processes:
                self.assertIsNone(p.poll(), "agente %s caiu (codigo %s)" % (agent, p.poll()))
            time.sleep(0.2)
        state = self._tickets(set(short))
        self.assertLessEqual(max_running, CAP, "teto de %d respeitado entre os dois agentes" % CAP)
        self.assertEqual(sorted(e[:3] for e in state.values()), [("SUCCESS", "EXIT_OK", 0)] * N_TICKETS)
        owners = dict((tid, e[3]) for tid, e in state.items())
        self.assertTrue(set(owners.values()) <= set(self.agents))

        # 2. Cada ticket executado uma unica vez, pelo agente dono.
        with open(self.execucoes) as f:
            executions = [line.split() for line in f.read().splitlines()]
        self.assertEqual(sorted(int(t) for t, _a in executions), sorted(short))
        self.assertEqual(dict((int(t), a) for t, a in executions), owners)
        distribution = dict((a, sum(1 for d in owners.values() if d == a)) for a in self.agents)
        print("\n[F8.3d] distribuicao: %s; maximo RUNNING simultaneos: %d" % (distribution, max_running))

        # 3. Saida (CR-012): DISPONIVEL para cada ticket, com o zip do proprio ticket e a pasta removida.
        self.assertTrue(self._wait(lambda: len(self._query(
            "SELECT ticket_id FROM {sai} WHERE ticket_id IN (%s) AND state = 'AVAILABLE'"
            % ", ".join(str(t) for t in short))) == N_TICKETS, 60), "saidas DISPONIVEL")
        tickets = self.obter_repo("tickets")
        for tid in short:
            meta = tickets.output_get(tid)
            self.assertEqual((meta["agent_id"], meta["file_count"]), (owners[tid], 1))
            data = tickets.output_read(tid, 0, meta["size_bytes"])
            self.assertEqual(zipfile.ZipFile(io.BytesIO(data)).read("resultado.txt"), b"ticket %d\n" % tid)
        self.assertEqual(self._output_dirs(set(short)), [], "pastas de saida dos curtos removidas")

        # 4. Cancelamento pela web: o agente dono encerra o ticket longo.
        self.assertTrue(self._wait(lambda: (self._tickets({long}).get(long) or ("",))[0] == "RUNNING"
                                      and self._tickets({long})[long][4] is not None, 60), "longo RUNNING com PID")
        owner_long = self._tickets({long})[long][3]
        self.assertIn(tickets.request_cancel(long, self.login, "127.0.0.1"), ("SINALIZADO", "CANCELADO"))
        self.assertTrue(self._wait(lambda: self._tickets({long})[long][0] == "CANCELLED", 60), "cancelado")
        self.assertEqual(self._tickets({long})[long][1:4], ("CANCEL_USER", -1, owner_long))
        # A saida do longo ficou vazia: nada gravado e a pasta removida (README §8.13).
        self.assertTrue(self._wait(lambda: self._output_dirs({long}) == [], 30), "pasta vazia removida")
        self.assertIsNone(tickets.output_get(long))

        # 5. Heartbeat e configuracao critica iguais nos dois agentes ativos.
        agents = self._query("SELECT code, status, heartbeat_at, critical_config FROM {agt}"
                                 " WHERE code IN (:a, :b)", a=self.agents[0], b=self.agents[1])
        self.assertEqual(sorted((r[0], r[1]) for r in agents), [(a, "ACTIVE") for a in sorted(self.agents)])
        now = self._query("SELECT SYSDATE FROM DUAL")[0][0]
        for code, _st, hb, _cc in agents:
            self.assertLess((now - hb).total_seconds(), 60, "heartbeat recente de %s" % code)
        self.assertEqual(len(set(r[3] for r in agents)), 1)

        # 6. Parada pelo .stop: os dois saem com 0 e ficam PARADO.
        for agent, _p, dirs in self.processes:
            open(os.path.join(dirs["work"], "sss-%s.stop" % agent), "w").close()
        for agent, p, _dirs in self.processes:
            self.assertEqual(p.wait(60), 0, "saida de %s" % agent)
        stopped = self._query("SELECT code, status FROM {agt} WHERE code IN (:a, :b)",
                                 a=self.agents[0], b=self.agents[1])
        self.assertEqual(sorted(stopped), [(a, "STOPPED") for a in sorted(self.agents)])

        # 7. Nenhum processo orfao dos scripts do teste.
        ps = subprocess.run(["ps", "-eo", "args"], stdout=subprocess.PIPE).stdout.decode("utf-8", "replace")
        rows = ps.splitlines()
        self.assertEqual([l for l in rows if l.strip() == "sleep %d" % LONG_MARK], [], "orfao do script longo")
        self.assertEqual([l for l in rows if self.root in l and "run_scheduler" in l], [], "agente vivo")


if __name__ == "__main__":
    unittest.main()
