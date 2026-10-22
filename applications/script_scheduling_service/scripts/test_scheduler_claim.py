# -*- coding: utf-8 -*-
"""Testes do laco do agente (F8.3c; README §5.6, §8.1-§8.7, §8.10, §8.11; CR-007 R-02 a R-04, R-24, R-28;
CR-008 R-01, R-02, R-07, R-08, R-09, R-11, R-25, E4).

Plataforma, executor, env_builder e log_pump reais em DEV (scripts /bin/sh numa arvore temporaria travada);
banco em memoria com o contrato do RepoSchedulerQueue e do RepoSchedulerLog e falhas injetaveis por metodo. A
unica espera e a do harness (Event.wait), injetada no laco: o dublê de time.sleep falha se o laco o chamar.
"""
import _testenv  # noqa: F401

import collections
import datetime
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

import executor
import log_pump
import path_guard
import os_platform
import rbac
import scheduler_loop as sl
import sql_ident
from repo_oracle.scheduler_queue import RegistrationLost
from sss_config import EnvironmentSecret, Secrets
from _output_memory import RepoOutputMemory

FAKE_AGENT = 2 ** 31 - 3
AMB = "DEV"
ENV_PASSWORD = "SenhaDoAmbiente#2026"

_Agent = collections.namedtuple("_Agent", (
    "agent_id", "environments", "work_dir", "interpreters", "exec_users",
    "exec_work_dir", "heartbeat_interval_s", "fence_timeout_s", "node_offline_timeout_s", "kill_grace_s",
    "misfire_policy", "misfire_tolerance_s", "cron_horizon_days", "queue_aging_min", "child_locale",
    "cancel_poll_interval_s", "orchestrator_interval_s", "max_parallel_jobs",
    "log_dir_min_free_mb", "script_timeout_s", "env_passthrough", "output_dir", "output_max_bytes",
    "output_max_files", "schedule_batch_size", "shutdown_mode", "shutdown_grace_s", "input_dir"))
# CR-012: sem output_dir por padrao; F8.4b: lote do desdobro; F8.4d: parada TERMINATE; CR-014: sem input_dir.
_Agent.__new__.__defaults__ = (None, 20971520, 1000, 50, "TERMINATE", 30, None)
_Log = collections.namedtuple("_Log", "log_dir max_log_size_bytes max_local_log_size_bytes")
_Cfg = collections.namedtuple("_Cfg", "agent logging app oracle secrets")
_App = collections.namedtuple("_App", "sss_env")
_Oracle = collections.namedtuple("_Oracle", "dsn call_timeout_ms owner table_prefix")


class _NetworkError(Exception):
    def __init__(self):
        Exception.__init__(self, "DPY-4011: the database or network closed the connection")


class _PrivilegeError(Exception):
    def __init__(self):
        Exception.__init__(self, "ORA-01031: insufficient privileges")


class _Db(object):
    """Banco em memoria: tickets, scripts, ambiente, homologacao, contexto RBAC e o CLOB do log."""

    def __init__(self, root):
        self.lock = threading.Lock()
        self.tickets = {}
        self.scripts = {}
        self.environment = {"id": 1, "name": AMB, "description": "Desenvolvimento", "connection": "db:1521/dev", "active": "Y"}
        self.homologados = set()
        self.ctx = rbac.user_context({
            "user_id": 9, "login": "ana", "profile_id": 2, "usuario_ativo": "Y", "perfil_ativo": "Y",
            "is_admin": "N", "perm_version": 1, "features": ["EXEC_SCRIPT"], "environments": [AMB],
            "scripts": []})
        self.failures = collections.defaultdict(list)
        self.calls = collections.defaultdict(int)
        self.claim_answers = []
        self.heartbeats = []
        self.active_agent = True
        self.stopped_flag = None
        self.max_running = 0
        self.seq = 100
        self.unit = 2
        # F8.4c: tickets de outro agente que o NODE_OFFLINE deve marcar, chamadas e o deslocamento do SYSDATE.
        self.offline = set()
        self.node_offline_calls = 0
        self.sysdate_offset_s = 0

    def _fail(self, method):
        self.calls[method] += 1
        if self.failures[method]:
            error = self.failures[method].pop(0)
            if error is not None:
                raise error

    # -- massa

    def script(self, body, timeout=None, active="Y", max_par=5, interpreter="SH", homologate=True):
        self.seq += 1
        sid = self.seq
        path = os.path.join(self.base, "s%d.sh" % sid)
        with open(path, "w") as f:
            f.write(body)
        os.chmod(path, 0o444)
        self.scripts[sid] = {"id": sid, "name": "Script %d" % sid, "interpreter": interpreter,
                             "path_file": path, "active": active, "timeout_s": timeout,
                             "max_parallel_env": max_par}
        if homologate:
            self.homologados.add(sid)
        self.ctx = dict(self.ctx, scripts=frozenset(set(self.ctx["scripts"]) | {sid}))
        return sid

    def ticket(self, sid, version=5, args=(), path_file=None, interpreter=None, schedule_id=None):
        self.seq += 1
        s = self.scripts[sid]
        snap = {"version": version, "script_id": sid, "script_name": s["name"],
                "interpreter": interpreter or s["interpreter"], "path_file": path_file or s["path_file"],
                "param_type": "NAMED", "args": list(args), "answers": {}, "sensitive": [],
                "compiled_at": "2026-10-20 10:00:00"}
        self.tickets[self.seq] = {
            "id": self.seq, "script_id": sid, "environment": AMB, "requested_by": "ana", "status": "PENDING",
            "priority": 2, "cancel_requested": "N", "agent_id": None, "process_id": None, "process_start": None,
            "parent_ticket_id": None, "schedule_id": schedule_id, "scheduled_at": None, "started_at": None,
            "created_at": None, "log_offset_chars": 0, "submitted_params": json.dumps(snap), "log": "",
            "status_reason": None, "return_code": None, "updated_by": None}
        return self.seq

    # -- contrato do RepoSchedulerQueue

    def active_environments(self, conn, served):
        self._fail("active_environments")
        return ([AMB] if self.environment["active"] == "Y" and AMB in served else []), []

    def check_config(self, conn, agent_id, critical, offline):
        self._fail("check_config")
        return []

    def candidates(self, conn, environments, interpreters, batch, env_min):
        self._fail("candidates")
        with self.lock:
            return [{"id": t["id"], "script_id": t["script_id"], "environment": t["environment"]}
                    for t in sorted(self.tickets.values(), key=lambda x: x["id"])
                    if t["status"] == "PENDING" and t["cancel_requested"] == "N"
                    and self.scripts[t["script_id"]]["interpreter"] in interpreters][:batch]

    def claim(self, conn, tid, sid, environment, agent_id):
        self._fail("claim")
        if self.claim_answers:
            answer = self.claim_answers.pop(0)
            if answer is not None:
                return answer
        with self.lock:
            t = self.tickets[tid]
            running = sum(1 for x in self.tickets.values() if x["status"] == "RUNNING" and x["script_id"] == sid)
            if running >= self.scripts[sid]["max_parallel_env"]:
                return False, "TETO", None
            if t["status"] != "PENDING" or t["cancel_requested"] != "N":
                return False, "PERDIDO", None
            t.update(status="RUNNING", agent_id=agent_id, started_at=datetime.datetime(2026, 10, 20, 14, 5),
                     log="", log_offset_chars=0, updated_by="SYSTEM:%s" % agent_id)
            self.max_running = max(self.max_running, sum(1 for x in self.tickets.values() if x["status"] == "RUNNING"))
            return True, None, t["started_at"]

    def get_ticket(self, conn, tid):
        self._fail("get_ticket")
        return dict(self.tickets[tid]) if tid in self.tickets else None

    def execution_context(self, conn, ticket):
        self._fail("execution_context")
        s = self.scripts.get(ticket["script_id"])
        return {"script": dict(s) if s else None, "environment": dict(self.environment),
                "homologacoes": frozenset({1}) if ticket["script_id"] in self.homologados else frozenset(),
                "ctx": self.ctx, "agendamento": None}

    def active_homologated_script(self, conn, sid, environment):
        return self.scripts[sid]["active"] == "Y" and sid in self.homologados

    def is_cancel_requested(self, conn, tid):
        self._fail("is_cancel_requested")
        return self.tickets[tid]["cancel_requested"] == "Y"

    def register_pid(self, conn, tid, agent_id, pid, start):
        self._fail("register_pid")
        t = self.tickets[tid]
        if t["status"] != "RUNNING" or t["agent_id"] != agent_id:
            return False
        t.update(process_id=pid, process_start=start)
        return True

    def return_to_queue(self, conn, tid, agent_id):
        self._fail("return_to_queue")
        t = self.tickets[tid]
        if t["status"] == "RUNNING" and t["agent_id"] == agent_id and t["process_id"] is None:
            if t["cancel_requested"] == "N":
                t.update(status="PENDING", agent_id=None, log="", log_offset_chars=0)
                return "DEVOLVIDO"
            t.update(status="CANCELLED", status_reason="CANCEL_USER", return_code=-1)
            return "CANCELADO"
        return "PERDIDO"

    def finalize(self, conn, tid, agent_id, status, reason, rc):
        self._fail("finalize")
        t = self.tickets[tid]
        if t["status"] != "RUNNING" or t["agent_id"] != agent_id:
            return False
        t.update(status=status, status_reason=reason, return_code=rc, updated_by="SYSTEM:%s" % agent_id)
        return True

    def own_sweep(self, conn, agent_id):
        self._fail("own_sweep")
        return dict((t["id"], t["cancel_requested"]) for t in self.tickets.values()
                    if t["status"] == "RUNNING" and t["agent_id"] == agent_id)

    def agent_running_tickets(self, conn, agent_id):
        return [{"id": t["id"], "process_id": t["process_id"], "process_start": t["process_start"],
                 "cancel_requested": t["cancel_requested"]} for t in self.tickets.values()
                if t["status"] == "RUNNING" and t["agent_id"] == agent_id]

    def heartbeat(self, conn, agent_id, hostname, pid, ids):
        self._fail("heartbeat")
        if not self.active_agent:
            raise RegistrationLost("registro assumido")
        self.heartbeats.append(list(ids))
        lost = [i for i in ids if self.tickets[i]["status"] != "RUNNING" or self.tickets[i]["agent_id"] != agent_id]
        return lost, self.sysdate()

    def sysdate(self):
        return datetime.datetime.now() + datetime.timedelta(seconds=self.sysdate_offset_s)

    def mark_node_offline(self, conn, agent_id, timeout_s, clock_jump):
        self._fail("mark_node_offline")
        self.node_offline_calls += 1
        if clock_jump(self.sysdate()):
            return None
        marked = []
        for tid in sorted(self.offline):
            t = self.tickets[tid]
            if t["status"] == "RUNNING" and t["agent_id"] != agent_id:
                t.update(status="FAILED", status_reason="NODE_OFFLINE", return_code=-2,
                         updated_by="SYSTEM:%s" % agent_id)
                marked.append(tid)
        return marked

    def register_agent(self, conn, date, process_exists):
        return 1

    def stop_agent(self, conn, agent_id, hostname, pid, mode):
        self.stopped_flag = mode
        return True

    # -- contrato do RepoSchedulerLog

    def supplementary_unit(self, conn):
        return self.unit

    def append_chunk(self, conn, tid, agent_id, offset, chunk):
        self._fail("append_chunk")
        t = self.tickets[tid]
        if t["status"] != "RUNNING" or t["agent_id"] != agent_id:
            return "OWNERSHIP_LOST"
        if t["log_offset_chars"] != offset:
            return "ALREADY_WRITTEN"
        t["log"] += chunk
        t["log_offset_chars"] += log_pump.clob_units(chunk, self.unit)
        return "WRITTEN"

    def mark_truncated(self, conn, tid, agent_id):
        return True


class _EmptyAgenda(object):
    """Sem regras vencidas: o desdobro (F8.4b) e testado no test_scheduler_ha."""

    def due_rules(self, conn, batch, last_next=None, last_id=0):
        return []


class _Conn(object):
    def cursor(self):
        return _Cursor()

    def commit(self):
        pass

    def rollback(self):
        pass


class _Cursor(object):
    def execute(self, sql, *a, **k):
        self._linha = (datetime.datetime.now().replace(microsecond=0),) if "SYSDATE" in sql else (sql_ident.SCHEMA_VERSION,)

    def fetchone(self):
        return self._linha

    def close(self):
        pass


class _Connection(object):
    def __init__(self):
        self.conn = _Conn()
        self.down = False
        self.closings = 0

    def ensure(self):
        return not self.down

    def get_connection(self):
        return None if self.down else self.conn

    def close(self):
        self.closings += 1

    def notify_error(self, exc):
        pass


@unittest.skipIf(os.geteuid() == 0, "o agente nunca roda como root")
class _Base(unittest.TestCase):

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="sss_laco_"))
        self.work = os.path.join(self.root, "work")
        self.logs = os.path.join(self.root, "logs")
        os.mkdir(self.work, 0o700)
        os.mkdir(self.logs, 0o750)
        self.db = _Db(self.root)
        self.db.base = os.path.join(self.root, "scripts")
        os.mkdir(self.db.base)
        self.connection = _Connection()
        self.stopped = threading.Event()
        self._wait_s = threading.Event()
        self.ag = None

    def tearDown(self):
        if self.ag is not None:
            for item in list(getattr(self.ag, "executions", {}).values()):
                if item.execution is not None and item.execution.process is not None:
                    try:
                        os.killpg(item.execution.pgid if hasattr(item.execution, "pgid") else item.execution.pid,
                                  signal.SIGKILL)
                    except OSError:
                        pass
                    if item.execution.process.popen is not None:
                        item.execution.process.popen.wait(5)
            self.ag.release_resources()
        for current, dirs, _arqs in os.walk(self.root):
            for d in dirs:
                os.chmod(os.path.join(current, d), 0o700)
        shutil.rmtree(self.root, ignore_errors=True)

    def cfg(self, **changes):
        base = dict(agent_id="srv-t", environments=(AMB,), work_dir=self.work,
                    interpreters=(("SH", "/bin/sh"),), exec_users=(), exec_work_dir=None,
                    heartbeat_interval_s=0.2, fence_timeout_s=40, node_offline_timeout_s=120, kill_grace_s=1,
                    misfire_policy="RUN_ONCE", misfire_tolerance_s=300, cron_horizon_days=366,
                    queue_aging_min=30, child_locale="C.UTF-8",
                    cancel_poll_interval_s=0.05, orchestrator_interval_s=0.05, max_parallel_jobs=4,
                    log_dir_min_free_mb=1, script_timeout_s=60, env_passthrough=())
        local = changes.pop("max_local_log_size_bytes", 10 * 1024 * 1024)
        base.update(changes)
        return _Cfg(_Agent(**base), _Log(self.logs, 5 * 1024 * 1024, local), _App("DEV"),
                    _Oracle("db:1521/x", 30000, "OWN_X", "pfx_"), None)

    def start_agent(self, **changes):
        secrets_value = Secrets("SenhaOracle#1", None, {AMB: EnvironmentSecret("app_dev", ENV_PASSWORD)})
        plat = changes.pop("plat", None)
        with mock.patch.object(sl.os, "geteuid", return_value=FAKE_AGENT):
            if getattr(self, "repo_output", None) is None:
                self.repo_output = RepoOutputMemory(self.db.tickets)
            self.ag = sl.Agent(cfg=self.cfg(**changes), secrets=secrets_value, plat=plat, connection=self.connection,
                                repo=self.db, repo_log=self.db, hostname="host-t", pid=os.getpid(),
                                repo_output=self.repo_output, repo_schedules=_EmptyAgenda())
            self.ag.initialize()
        self.ag.prepare_loop(lambda s: self._wait_s.wait(min(s, 0.02)))
        return self.ag

    def run_loop(self, until, limit=15):
        with mock.patch.object(time, "sleep", side_effect=AssertionError("time.sleep dentro do laco")):
            code = self.ag.run(self.stopped, until=until, limit_s=limit)
        return code

    def finished(self, tid):
        return lambda: self.db.tickets[tid]["status"] not in ("PENDING", "RUNNING") and tid not in self.ag.executions

    def final(self, tid):
        t = self.db.tickets[tid]
        return t["status"], t["status_reason"], t["return_code"]


class TestExecution(_Base):

    def test_sucesso_com_log_mascarado_e_limpeza(self):
        sid = self.db.script("echo inicio\necho \"connection=$PADRAO_VALOR_RUN_CONEXAO_BD\"\necho \"$SSS_TICKET_ID\"\n")
        tid = self.db.ticket(sid)
        self.start_agent()
        self.run_loop(self.finished(tid))
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0))
        t = self.db.tickets[tid]
        self.assertNotIn("sha256", t["log"], "CR-011: sem hash")
        self.assertIn("inicio\n", t["log"])
        self.assertIn("connection=****\n", t["log"], "a connect string inteira e segredo do ticket (README §8.10)")
        self.assertNotIn(ENV_PASSWORD, t["log"])
        self.assertIn("%d\n" % tid, t["log"])
        self.assertIsNotNone(t["process_id"])
        self.assertEqual(t["updated_by"], "SYSTEM:srv-t")
        self.assertFalse(os.path.exists(os.path.join(self.work, "ticket_%d" % tid)), "limpeza no fim")

    def test_script_cadastrado_por_link_executa_o_real(self):
        # CR-011: o caminho cadastrado e um link; o agente executa o arquivo real e informa os dois.
        sid = self.db.script("echo \"$SSS_SCRIPT_FILE|$SSS_SCRIPT_LINK\"\n")
        real = self.db.scripts[sid]["path_file"]
        os.chmod(self.db.base, 0o755)
        link = os.path.join(self.db.base, "atalho.sh")
        os.symlink(real, link)
        os.chmod(self.db.base, 0o555)
        self.db.scripts[sid]["path_file"] = link
        tid = self.db.ticket(sid)
        self.start_agent()
        self.run_loop(self.finished(tid))
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0))
        self.assertIn("%s|%s\n" % (real, link), self.db.tickets[tid]["log"])

    def test_cr014_pasta_de_entrada_permanente_por_ambiente_e_script(self):
        # CR-014 (README §8.14): SSS_INPUT_DIR = input_dir/<ambiente>/<script>, criada sob demanda e mantida.
        input_value = os.path.join(self.root, "input")
        os.mkdir(input_value, 0o700)
        sid = self.db.script('n=$(ls "$SSS_INPUT_DIR" | wc -l)\n'
                                'echo "dir=$SSS_INPUT_DIR n=$n"\n'
                                'echo ok > "$SSS_INPUT_DIR/lote_$SSS_TICKET_ID.txt"\n')
        first = self.db.ticket(sid)
        self.start_agent(input_dir=input_value)
        self.run_loop(self.finished(first))
        second = self.db.ticket(sid)
        self.run_loop(self.finished(second))
        dir_value = os.path.join(input_value, "dev", "script_%d" % sid)
        for tid, n in ((first, 0), (second, 1)):
            self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0))
            self.assertIn("dir=%s n=%d" % (dir_value, n), self.db.tickets[tid]["log"])
        self.assertEqual(sorted(os.listdir(dir_value)), ["lote_%d.txt" % first, "lote_%d.txt" % second],
                         "o SSS nao limpa a pasta de entrada")
        self.assertEqual(os.stat(dir_value).st_mode & 0o777, 0o700)

    def test_cr014_sem_entrada_dir_sem_variavel(self):
        tid = self.db.ticket(self.db.script('echo "entrada=[${SSS_INPUT_DIR:-}]"\n'))
        self.start_agent()
        self.run_loop(self.finished(tid))
        self.assertIn("entrada=[]", self.db.tickets[tid]["log"])

    def test_exit_error(self):
        tid = self.db.ticket(self.db.script("echo falhou\nexit 3\n"))
        self.start_agent()
        self.run_loop(self.finished(tid))
        self.assertEqual(self.final(tid), ("FAILED", "EXIT_ERROR", 3))

    def test_timeout_mata_o_neto(self):
        grandchild = os.path.join(self.root, "neto.pid")
        tid = self.db.ticket(self.db.script("sleep 300 &\necho $! > %s\nsleep 300\n" % grandchild, timeout=1))
        self.start_agent()
        self.run_loop(self.finished(tid))
        self.assertEqual(self.final(tid), ("FAILED", "TIMEOUT", -3))
        pid_grandchild = int(open(grandchild).read().strip())
        self.assertFalse(_alive(pid_grandchild))

    def test_cancelamento_durante_a_execucao(self):
        ready = os.path.join(self.root, "pronto")
        tid = self.db.ticket(self.db.script("touch %s\nsleep 300\n" % ready))
        self.start_agent()
        self.run_loop(lambda: os.path.exists(ready))
        self.db.tickets[tid]["cancel_requested"] = "Y"
        self.run_loop(self.finished(tid))
        self.assertEqual(self.final(tid), ("CANCELLED", "CANCEL_USER", -1))

    def test_cancelamento_entre_o_claim_e_o_spawn(self):
        tid = self.db.ticket(self.db.script("echo nunca\n"))
        original = self.db.is_cancel_requested
        def _pedido(conn, t):
            self.db.tickets[t]["cancel_requested"] = "Y"
            return original(conn, t)
        self.db.is_cancel_requested = _pedido
        self.start_agent()
        self.run_loop(self.finished(tid))
        self.assertEqual(self.final(tid), ("CANCELLED", "CANCEL_USER", -1))
        self.assertIsNone(self.db.tickets[tid]["process_id"], "nenhum processo iniciado")

    def test_processo_que_terminou_antes_do_cancelamento_prevalece(self):
        self.start_agent()
        item = sl._Item(1, None, self.ag.log)
        item.phase = sl._Item.RODANDO
        p = subprocess.Popen(["true"], start_new_session=True)
        p.wait()
        item.execution = executor.Execution(1, self.work, None, None, None)
        item.execution.process = os_platform.Process(p.pid, None, popen=p)
        item.execution.pid = p.pid
        self.ag._stop(item, "CANCEL")
        self.assertIsNone(item.reason)
        self.assertEqual(self.ag._result(item), ("SUCCESS", "EXIT_OK", 0))

    def test_log_limit(self):
        tid = self.db.ticket(self.db.script("head -c 5000 /dev/zero | tr '\\000' x\nsleep 300\n"))
        self.start_agent(max_local_log_size_bytes=2048)
        self.run_loop(self.finished(tid))
        self.assertEqual(self.final(tid), ("FAILED", "LOG_LIMIT", -5))

    def test_ownership_lost_na_varredura(self):
        ready = os.path.join(self.root, "pronto")
        tid = self.db.ticket(self.db.script("touch %s\nsleep 300\n" % ready))
        self.start_agent()
        self.run_loop(lambda: os.path.exists(ready))
        pid = self.db.tickets[tid]["process_id"]
        self.db.tickets[tid].update(status="FAILED", status_reason="NODE_OFFLINE", return_code=-2)
        with self.assertLogs("sss_scheduler", "ERROR") as logs:
            self.run_loop(lambda: tid not in self.ag.executions)
        self.assertEqual(self.final(tid), ("FAILED", "NODE_OFFLINE", -2), "nenhum status gravado")
        self.assertTrue(any("OWNERSHIP_LOST" in x for x in logs.output))
        self.assertFalse(_alive(pid))

    def test_teto_paralelo(self):
        sid = self.db.script("sleep 0.5\n", max_par=10)
        tids = [self.db.ticket(sid) for _ in range(5)]
        self.start_agent(max_parallel_jobs=2)
        self.run_loop(lambda: all(self.finished(t)() for t in tids), limit=30)
        self.assertEqual(self.db.max_running, 2)
        self.assertEqual([self.final(t)[0] for t in tids], ["SUCCESS"] * 5)

    def test_lock_no_claim_tenta_de_novo(self):
        tid = self.db.ticket(self.db.script("echo ok\n"))
        self.db.claim_answers = [(False, "LOCK", "ORA-30006"), (False, "TETO", None)]
        self.start_agent()
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.run_loop(self.finished(tid))
        warnings_value = [r.getMessage() for r in logs.records if "pulado" in r.getMessage()]
        self.assertEqual(len(warnings_value), 1, "WARN so no LOCK, nao no TETO (README §13, CR-007 R-32)")
        self.assertIn("claim do ticket %d pulado: linha do script" % tid, warnings_value[0])
        self.assertIn("(ORA-30006, FOR UPDATE WAIT 5)", warnings_value[0])
        self.assertFalse([r for r in logs.records if "pulado" in r.getMessage() and r.exc_info], "sem stack trace")
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0))
        self.assertGreaterEqual(self.db.calls["claim"], 3)


class TestPrevalidation(_Base):

    def _refusal(self, tid, code, **start_agent):
        self.start_agent(**start_agent)
        self.run_loop(self.finished(tid))
        self.assertEqual(self.final(tid), ("FAILED", "PRECHECK_FAILED", -4))
        self.assertIn("[SSS] pre-validacao recusada: %s (agente srv-t)" % code, self.db.tickets[tid]["log"])
        self.assertIsNone(self.db.tickets[tid]["process_id"])

    def test_cr014_script_dentro_da_entrada_ou_da_saida_e_pasta_do_sss(self):
        # CR-014: o usuario de execucao grava em input_dir e output_dir; um script ali poderia ser trocado.
        for key in ("input_dir", "output_dir"):
            dir_value = os.path.join(self.root, key)
            os.mkdir(dir_value, 0o700)
            sid = self.db.script("echo nao deveria rodar\n")
            path = os.path.join(dir_value, "s%d.sh" % sid)
            os.rename(self.db.scripts[sid]["path_file"], path)
            self.db.scripts[sid]["path_file"] = path
            tid = self.db.ticket(sid)
            self._refusal(tid, "SSS_DIR", **{key: dir_value})
            self.ag.release_resources()

    def test_snapshots_antigos(self):
        sid = self.db.script("echo x\n")
        tids = [self.db.ticket(sid, version=version) for version in (1, 2, 3, 4)]
        self.start_agent()
        self.run_loop(lambda: all(self.finished(t)() for t in tids))
        for tid in tids:
            self.assertEqual(self.final(tid), ("FAILED", "PRECHECK_FAILED", -4))
            self.assertIn("[SSS] pre-validacao recusada: UNSUPPORTED_VERSION", self.db.tickets[tid]["log"])

    def test_interpretador_nao_mapeado(self):
        # O script e BASH, mas este agente so mapeia SH; a fila de teste entrega o ticket mesmo assim.
        tid = self.db.ticket(self.db.script("echo x\n", interpreter="BASH"))
        self.db.candidates = lambda conn, a, i, batch, env: [
            {"id": tid, "script_id": self.db.tickets[tid]["script_id"], "environment": AMB}
        ] if self.db.tickets[tid]["status"] == "PENDING" else []
        self._refusal(tid, "INTERPRETER_UNAVAILABLE")

    def test_caminho_inexistente(self):
        sid = self.db.script("echo x\n")
        t1 = self.db.ticket(sid, path_file=os.path.join(self.db.base, "nao.sh"))
        self._refusal(t1, "NOT_FOUND")

    def test_cadastro_mudou(self):
        sid = self.db.script("echo x\n")
        other = self.db.script("echo y\n")
        tid = self.db.ticket(sid, path_file=self.db.scripts[other]["path_file"])
        self._refusal(tid, "REGISTRATION_CHANGED")

    def test_sem_permissao(self):
        sid = self.db.script("echo x\n")
        tid = self.db.ticket(sid)
        self.db.ctx = dict(self.db.ctx, scripts=frozenset())
        self._refusal(tid, "NO_PERMISSION")

    def test_script_inativo(self):
        tid = self.db.ticket(self.db.script("echo x\n", active="N"))
        self._refusal(tid, "SCRIPT_INACTIVE")

    def test_nao_homologado(self):
        tid = self.db.ticket(self.db.script("echo x\n", homologate=False))
        self._refusal(tid, "NOT_HOMOLOGATED")

    def test_erro_de_rede_antes_do_spawn_devolve(self):
        tid = self.db.ticket(self.db.script("echo x\n"))
        self.db.failures["execution_context"] = [_NetworkError()]
        self.start_agent()
        self.run_loop(self.finished(tid))
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0), "devolvido e executado no ciclo seguinte")
        self.assertGreaterEqual(self.db.calls["return_to_queue"], 1)

    def test_erro_de_banco_nao_transitorio_e_precheck(self):
        tid = self.db.ticket(self.db.script("echo x\n"))
        self.db.failures["execution_context"] = [_PrivilegeError()]
        self.start_agent()
        with self.assertLogs("sss_scheduler", "ERROR"):
            self.run_loop(self.finished(tid))
        self.assertEqual(self.final(tid), ("FAILED", "PRECHECK_FAILED", -4))
        self.assertIn("[SSS] DB_ERROR: ORA-01031", self.db.tickets[tid]["log"])


class TestPending(_Base):

    def test_finalizacao_pendente_ate_gravar(self):
        tid = self.db.ticket(self.db.script("echo ok\n"))
        self.db.failures["finalize"] = [_NetworkError(), _NetworkError()]
        self.start_agent()
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.run_loop(self.finished(tid))
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0))
        self.assertEqual(self.db.calls["finalize"], 3)
        self.assertTrue(any("finalizacao pendente" in x for x in logs.output))

    def test_pid_pendente_recebe_heartbeat(self):
        ready = os.path.join(self.root, "pronto")
        tid = self.db.ticket(self.db.script("touch %s\nsleep 1\n" % ready))
        self.db.failures["register_pid"] = [_NetworkError()]
        self.start_agent()
        self.run_loop(self.finished(tid))
        self.assertEqual(self.final(tid)[0], "SUCCESS")
        self.assertIsNotNone(self.db.tickets[tid]["process_id"])
        self.assertTrue(any(tid in ids for ids in self.db.heartbeats))

    def test_posse_perdida_no_registrar_pid(self):
        tid = self.db.ticket(self.db.script("sleep 300\n"))
        original = self.db.register_pid
        def _perdeu(conn, t, *a):
            self.db.tickets[t]["agent_id"] = "outro"
            return original(conn, t, *a)
        self.db.register_pid = _perdeu
        self.start_agent()
        with self.assertLogs("sss_scheduler", "ERROR"):
            self.run_loop(lambda: tid not in self.ag.executions and self.db.calls["own_sweep"] > 0)
        self.assertEqual(self.db.tickets[tid]["status"], "RUNNING", "nenhum status gravado pelo agente")

    def test_falha_no_proc_depois_do_spawn_e_spawn_error(self):
        tid = self.db.ticket(self.db.script("sleep 300\n"))
        original = os_platform.write_state
        def _grava(path, date):
            if path.endswith(executor.PROC):
                raise OSError(28, "No space left on device")
            return original(path, date)
        self.start_agent()
        with mock.patch.object(os_platform, "write_state", side_effect=_grava), \
                self.assertLogs("sss_scheduler", "ERROR"):
            self.run_loop(self.finished(tid))
        self.assertEqual(self.final(tid), ("FAILED", "SPAWN_ERROR", -4))
        self.assertEqual(self.db.calls["register_pid"], 0)
        self.assertIn("[SSS] falha ao iniciar: OSError (agente srv-t)", self.db.tickets[tid]["log"])

    def test_reconciliacao_de_ticket_fora_do_mapa(self):
        sid = self.db.script("echo x\n")
        without_pid, with_pid = self.db.ticket(sid), self.db.ticket(sid)
        self.start_agent()
        for tid, pid in ((without_pid, None), (with_pid, 4242)):
            self.db.tickets[tid].update(status="RUNNING", agent_id="srv-t", process_id=pid)
        self.db.candidates = lambda *a: []
        self.run_loop(lambda: self.db.tickets[with_pid]["status"] == "FAILED"
                   and self.db.tickets[without_pid]["status"] == "PENDING")
        self.assertEqual(self.final(with_pid), ("FAILED", "ORPHAN_PROCESS", -2))


class TestCycles(_Base):

    def test_heartbeat_sem_tickets_e_instante_de_referencia(self):
        self.start_agent()
        instants = []
        original = self.db.heartbeat
        def _hb(*a):
            instants.append(self.ag.clock())
            time_ = original(*a)
            return time_
        self.db.heartbeat = _hb
        self.run_loop(lambda: len(instants) >= 2)
        self.assertEqual(self.db.heartbeats[-1], [])
        self.assertLessEqual(self.ag.last_hb_ok, instants[-1], "R-09: o instante e o de antes do UPDATE")

    def test_registro_perdido_sai_com_codigo_proprio(self):
        self.start_agent()
        self.db.active_agent = False
        with self.assertLogs("sss_scheduler", "CRITICAL"):
            self.assertEqual(self.run_loop(lambda: False, limit=5), sl.EXIT_REGISTRATION_LOST)

    def test_disco_baixo_sem_claim(self):
        tid = self.db.ticket(self.db.script("echo x\n"))
        plat = _PlatDisk()
        self.start_agent(plat=plat, log_dir_min_free_mb=1024)
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.run_loop(lambda: False, limit=0.5)
        self.assertEqual(self.db.tickets[tid]["status"], "PENDING")
        self.assertEqual(self.db.calls["candidates"], 0)
        self.assertEqual(len([x for x in logs.output if "DISCO_LOG" in x]), 1, "uma vez por minuto")

    def test_pump_com_tres_tickets_verbosos(self):
        sid = self.db.script("i=0\nwhile [ $i -lt 400 ]; do echo \"linha $i $SSS_TICKET_ID xxxxxxxxxxxxxxxxxxxxxxxxxx\"; "
                                "i=$((i+1)); done\n", max_par=5)
        tids = [self.db.ticket(sid) for _ in range(3)]
        self.start_agent()
        self.run_loop(lambda: all(self.finished(t)() for t in tids), limit=30)
        for t in tids:
            self.assertEqual(self.db.tickets[t]["log"].count("linha "), 400)

    def test_parada_pelo_stop(self):
        ready = os.path.join(self.root, "pronto")
        tid = self.db.ticket(self.db.script("touch %s\nsleep 300\n" % ready))
        self.start_agent()
        self.run_loop(lambda: os.path.exists(ready))
        open(os.path.join(self.work, "sss-srv-t.stop"), "w").close()
        self.assertEqual(self.run_loop(lambda: False, limit=15), 0)
        self.assertEqual(self.final(tid), ("FAILED", "SHUTDOWN", -6))
        self.assertEqual(self.db.stopped_flag, "TERMINATE")
        self.assertFalse(os.path.exists(os.path.join(self.work, "sss-srv-t.stop")))

    def test_sem_banco_o_processo_segue_acompanhado(self):
        tid = self.db.ticket(self.db.script("sleep 300\n", timeout=1))
        self.start_agent()
        self.run_loop(lambda: self.db.tickets[tid]["process_id"] is not None)
        self.connection.down = True
        self.run_loop(lambda: self.ag.executions[tid].phase != sl._Item.RODANDO, limit=10)
        self.connection.down = False
        self.run_loop(self.finished(tid))
        self.assertEqual(self.final(tid), ("FAILED", "TIMEOUT", -3))


class _PlatDisk(object):
    def __getattr__(self, name):
        if name == "free_space_mb":
            return lambda path: 10
        return getattr(os_platform, name)


def _alive(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            content = f.read()
    except OSError:
        return False
    return content[content.rindex(")") + 2:].split()[0] != "Z"


if __name__ == "__main__":
    unittest.main()
