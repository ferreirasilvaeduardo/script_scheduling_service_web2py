# -*- coding: utf-8 -*-
"""Testes da inicializacao do agente (F8.3b; README §8.12 passos 1-9; CR-007 R-01, R-11, R-17, R-23; CR-008 R-01,
R-02, R-26, E4).

Plataforma real em DEV (pastas temporarias, /bin/sh, trava de instancia e processos de verdade) e banco simulado
(conexao, repositorio da fila e do log em memoria). Cada falha de passo sai com o proprio codigo e CRITICAL.
"""
from tests.support import _testenv  # noqa: F401

import collections
import datetime
import os
import shutil
import signal
import subprocess
import sys
import stat
import tempfile
import threading
import time
import unittest
from unittest import mock

from sss.scheduler import executor
from sss.platform import os_platform
from sss.scheduler import scheduler_loop as sl
from sss.core import sql_ident
from sss.config import sss_config
from sss.persistence.oracle.scheduler_queue import DuplicateAgent
from tests.support._output_memory import RepoOutputMemory

_Agent = collections.namedtuple("_Agent", (
    "agent_id", "environments", "work_dir", "heartbeat_interval_s", "fence_timeout_s", "node_offline_timeout_s", "kill_grace_s",
    "misfire_policy", "misfire_tolerance_s", "cron_horizon_days", "queue_aging_min", "child_locale",
    "output_dir", "input_dir", "script_work_dir", "files_dir"))
# CR-012, CR-014, CR-019 e CR-037: pastas opcionais desligadas.
_Agent.__new__.__defaults__ = (None, None, None, None)
_Cfg = collections.namedtuple("_Cfg", "agent logging app oracle secrets")
_NS = collections.namedtuple("_NS", "log_dir")
_App = collections.namedtuple("_App", "name")
_Oracle = collections.namedtuple("_Oracle", "dsn call_timeout_ms owner table_prefix")


class _Cursor(object):
    def __init__(self, conn):
        self.conn = conn
        self._linha = None

    def execute(self, sql, *a, **k):
        if "SYSDATE" in sql:
            self._linha = (datetime.datetime.now().replace(microsecond=0),)
        elif "schema_version" in sql:
            self._linha = (self.conn.version,)

    def fetchone(self):
        return self._linha

    def close(self):
        pass


class _Conn(object):
    def __init__(self):
        self.version = sql_ident.SCHEMA_VERSION
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _Connection(object):
    def __init__(self, ok=True):
        self.ok = ok
        self.conn = _Conn()

    def ensure(self):
        return self.ok

    def get_connection(self):
        return self.conn


class _Repo(object):
    """Fila em memoria: registra as chamadas do startup check."""

    def __init__(self):
        self.running = []
        self.calls = []
        self.duplicated = False
        self.divergent = []
        self.environments = None
        self.registro = None

    def register_agent(self, conn, data, process_exists):
        self.registro = data
        if self.duplicated:
            raise DuplicateAgent("agent_id ativo em outro-host")
        return 42

    def check_config(self, conn, agent_id, critical, offline):
        return self.divergent

    def active_environments(self, conn, served):
        return self.environments or (list(served), [])

    def agent_running_tickets(self, conn, agent_id):
        return list(self.running)

    def return_to_queue(self, conn, tid, agent_id):
        self.calls.append(("return_to_queue", tid))
        return "DEVOLVIDO"

    def finalize(self, conn, tid, agent_id, status, reason, rc):
        self.calls.append(("finalize", tid, status, reason, rc))
        return True

    def get_ticket(self, conn, tid):
        return {"id": tid, "log_offset_chars": 0}


class _RepoLog(object):
    def __init__(self):
        self.rows = []

    def supplementary_unit(self, conn):
        return 1

    def append_chunk(self, conn, tid, agent_id, offset, chunk):
        self.rows.append((tid, chunk))
        return "WRITTEN"


def _alive(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            content = f.read()
    except OSError:
        return False
    return content[content.rindex(")") + 2:].split()[0] != "Z"


@unittest.skipIf(os.geteuid() == 0, "o agente nunca roda como root")
class _Base(unittest.TestCase):

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="sss_init_"))
        self.work = os.path.join(self.root, "work")
        self.logs = os.path.join(self.root, "logs")
        os.mkdir(self.work, 0o700)
        os.mkdir(self.logs, 0o750)
        self.repo = _Repo()
        self.repo_log = _RepoLog()
        self.repo_output = RepoOutputMemory()
        self.connection = _Connection()
        self.popens = []
        self.agents = []

    def tearDown(self):
        for ag in self.agents:
            ag.release_resources()
        for p in self.popens:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            p.wait()
        for current, dirs, _arqs in os.walk(self.root):
            for d in dirs:
                os.chmod(os.path.join(current, d), 0o700)
        shutil.rmtree(self.root, ignore_errors=True)

    def cfg(self, **agent):
        base = dict(agent_id="srv-t", environments=("DEV",), work_dir=self.work,
                    heartbeat_interval_s=10, fence_timeout_s=40, node_offline_timeout_s=120, kill_grace_s=1,
                    misfire_policy="RUN_ONCE", misfire_tolerance_s=300, cron_horizon_days=366,
                    queue_aging_min=30, child_locale="C.UTF-8")
        log_dir = agent.pop("log_dir", self.logs)
        base.update(agent)
        return _Cfg(_Agent(**base), _NS(log_dir), _App("srv-t"),
                    _Oracle("db:1521/x", 30000, "OWN_X", "pfx_"), None)

    def agent(self, cfg=None, plat=None, **kw):
        kw.setdefault("repo_output", self.repo_output)
        ag = sl.Agent(cfg=cfg or self.cfg(), secrets=object(), plat=plat, connection=kw.pop("connection", self.connection),
                       repo=self.repo, repo_log=self.repo_log, hostname="host-t", pid=os.getpid(), **kw)
        self.agents.append(ag)
        return ag

    def failure(self, code, ag=None):
        ag = ag or self.agent()
        with self.assertLogs("sss_scheduler", "CRITICAL") as logs, self.assertRaises(sl.StartupFailure) as ctx:
            ag.initialize()
        self.assertEqual(ctx.exception.code, code)
        self.assertEqual(ctx.exception.code, code, "codigo de saida do processo")
        return logs.output


class _Plat(object):
    """A plataforma real com funcoes trocadas por teste."""

    def __init__(self, **overrides):
        self._overrides = overrides

    def __getattr__(self, name):
        return self._overrides[name] if name in self._overrides else getattr(os_platform, name)


class TestSteps(_Base):

    def test_subida_completa_em_dev(self):
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            ag = self.agent().initialize()
        self.assertEqual(ag.agent_db_id, 42)
        self.assertEqual(ag.supplementary_unit, 1)
        self.assertEqual(ag.active_environments, ["DEV"])
        self.assertIsNotNone(ag.last_hb_ok)
        text = "\n".join(logs.output)
        self.assertIn("fence_timeout_s=40 node_offline_timeout_s=120", text)
        self.assertNotIn("SEM_EXIGENCIA_HASH", text, "CR-011: sem hash")
        r = self.repo.registro
        self.assertEqual((r["code"], r["hostname"], r["version"], r["platform"]),
                         ("srv-t", "host-t", sss_config.SSS_VERSION, os_platform.NAME))
        self.assertNotIn("interpreters", r, "CR-026: o agente nao publica lista de interpretadores")
        self.assertEqual(r["critical_config"], "call=30;misfire=RUN_ONCE")
        self.assertTrue(os.path.exists(os.path.join(self.work, "sss-srv-t.lock")))

    def test_root_recusado(self):
        self.failure(sl.EXIT_USER, self.agent(plat=_Plat(is_privileged_user=lambda: True)))

    def test_codificacao_e_locale(self):
        with mock.patch.object(sss_config.sys, "getfilesystemencoding", return_value="ascii"):
            self.failure(sl.EXIT_CONFIG)
        self.failure(sl.EXIT_CONFIG, self.agent(cfg=self.cfg(child_locale="xx_YY.UTF-8")))

    def test_diretorios(self):
        # CR-026: sem [agent] interpreters, nao ha executavel a conferir na subida.
        self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=self.cfg(log_dir="/usr/local/sss-logs")))
        # CR-032 (D12): a pasta que falta e criada na subida, com o modo certo.
        created = os.path.join(self.root, "nao_work_dir")
        agent_created = self.agent(cfg=self.cfg(work_dir=created))
        agent_created.initialize()
        agent_created.release_resources()
        self.assertEqual(stat.S_IMODE(os.stat(created).st_mode), 0o700)
        blocked = os.path.join(self.root, "arquivo")
        open(blocked, "w").close()
        self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=self.cfg(work_dir=blocked)))

    def test_cr032_pastas_no_plural_renomeadas_na_subida(self):
        """CR-032 (032e, D21): var/<nome>/work, input, output e script_work viram works, inputs, outputs e
        script_works por rename, so quando a anterior existe e a nova nao; pasta escrita fora de var/<nome>/ fica."""
        var = os.path.join(self.root, "var")
        base = os.path.join(var, "srv-t")
        for old in ("work", "input", "output"):
            os.makedirs(os.path.join(base, old), 0o700)
        with open(os.path.join(base, "input", "lote.txt"), "w") as f:
            f.write("dados")
        os.makedirs(os.path.join(base, "script_work"))
        os.makedirs(os.path.join(base, "script_works"))   # a nova ja existe: nada e renomeado
        other = os.path.join(self.root, "fora", "work")
        os.makedirs(other)
        cfg = self.cfg(work_dir=os.path.join(base, "works"), input_dir=os.path.join(base, "inputs"),
                       output_dir=os.path.join(base, "outputs"), script_work_dir=os.path.join(base, "script_works"))
        with mock.patch.object(sss_config, "VAR_DIR", var), self.assertLogs("sss_scheduler", "INFO") as logs:
            agent = self.agent(cfg=cfg)
            agent.initialize()
            agent.release_resources()
        for old, new in (("work", "works"), ("input", "inputs"), ("output", "outputs")):
            self.assertFalse(os.path.exists(os.path.join(base, old)), old)
            self.assertTrue(os.path.isdir(os.path.join(base, new)), new)
        with open(os.path.join(base, "inputs", "lote.txt")) as f:
            self.assertEqual(f.read(), "dados", "o conteudo vai junto")
        self.assertTrue(os.path.isdir(os.path.join(base, "script_work")), "com a nova presente, a anterior fica")
        self.assertTrue(os.path.isdir(other), "pasta fora de var/<nome>/ nao e tocada")
        renamed = [line for line in logs.output if "pasta renomeada" in line]
        self.assertEqual(len(renamed), 3, renamed)

    def test_cr014_pasta_de_entrada_na_subida(self):
        # CR-014 (README §8.12 passo 4): input_dir fora das pastas do sistema e existente.
        self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=self.cfg(input_dir="/usr/local/sss-entrada")))
        # CR-032 (D12): a pasta que falta e criada na subida, com o modo certo.
        created = os.path.join(self.root, "nao_input_dir")
        agent_created = self.agent(cfg=self.cfg(input_dir=created))
        agent_created.initialize()
        agent_created.release_resources()
        self.assertEqual(stat.S_IMODE(os.stat(created).st_mode), 0o755)
        input_value = os.path.join(self.root, "entrada")
        os.mkdir(input_value, 0o755)
        self.agent(cfg=self.cfg(input_dir=input_value)).initialize()

    def test_cr019_pasta_de_trabalho_na_subida(self):
        # CR-019 (README §8.12 passo 4): script_work_dir como a de saida.
        self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=self.cfg(script_work_dir="/usr/local/sss-work")))
        # CR-032 (D12): a pasta que falta e criada na subida, com o modo certo.
        created = os.path.join(self.root, "nao_script_work_dir")
        agent_created = self.agent(cfg=self.cfg(script_work_dir=created))
        agent_created.initialize()
        agent_created.release_resources()
        self.assertEqual(stat.S_IMODE(os.stat(created).st_mode), 0o755)
        work = os.path.join(self.root, "trabalho")
        os.mkdir(work, 0o755)
        self.agent(cfg=self.cfg(script_work_dir=work)).initialize()
        self.assertIn(work, sl._sss_dirs(self.cfg(script_work_dir=work)), "script nem interpretador dentro dela (SSS_DIR)")

    def test_cr037_pasta_de_arquivos_criada_na_subida_e_sem_script(self):
        # CR-037: var/<agente>/files criada na subida (0755, linha "pasta criada") e fora do alcance de script.
        files = os.path.join(self.root, "files_do_agente")
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            ag = self.agent(cfg=self.cfg(files_dir=files))
            ag.initialize()
            ag.release_resources()
        self.assertEqual(stat.S_IMODE(os.stat(files).st_mode), 0o755)
        self.assertTrue(any("pasta criada: files_dir" in m for m in logs.output), logs.output)
        self.assertIn(files, sl._sss_dirs(self.cfg(files_dir=files)), "script nem interpretador dentro dela (SSS_DIR)")

    def test_pasta_de_saida_na_subida(self):
        # CR-012 (README §8.12 passo 4): output_dir fora das pastas do sistema e existente.
        self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=self.cfg(output_dir="/usr/local/sss-output")))
        # CR-032 (D12): a pasta que falta e criada na subida, com o modo certo.
        created = os.path.join(self.root, "nao_output_dir")
        agent_created = self.agent(cfg=self.cfg(output_dir=created))
        agent_created.initialize()
        agent_created.release_resources()
        self.assertEqual(stat.S_IMODE(os.stat(created).st_mode), 0o755)
        output = os.path.join(self.root, "saida")
        os.mkdir(output, 0o755)
        self.agent(cfg=self.cfg(output_dir=output)).initialize()

    def test_instancia_unica_e_stop_antigo(self):
        stop = os.path.join(self.work, "sss-srv-t.stop")
        open(stop, "w").close()
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.agent().initialize()
        self.assertFalse(os.path.exists(stop))
        self.assertTrue(any(".stop antigo" in x for x in logs.output))
        code = ("import sys\nsys.path.insert(0, %r)\nfrom sss.platform import os_platform\n"
                  "try:\n    os_platform.lock_instance(%r)\nexcept os_platform.InstanceAlreadyRunning:\n"
                  "    sys.exit(7)\n" % (os.path.join(_testenv.APP_DIR, "src"),
                                        os.path.join(self.work, "sss-srv-t.lock")))
        self.assertEqual(subprocess.call([sys.executable, "-c", code]), 7, "segunda instancia recusada")

    def test_segunda_instancia_no_mesmo_processo(self):
        self.agent().initialize()
        self.failure(sl.EXIT_INSTANCE)

    def test_banco(self):
        self.failure(sl.EXIT_DATABASE, self.agent(connection=_Connection(ok=False)))
        connection = _Connection()
        connection.conn.version = sql_ident.SCHEMA_VERSION + 1
        with mock.patch.object(sl.db_conn, "_log_critical"):
            self.failure(sl.EXIT_DATABASE, self.agent(connection=connection))

    def test_registro(self):
        self.repo.duplicated = True
        self.failure(sl.EXIT_REGISTRATION)
        self.repo.duplicated = False
        self.repo.divergent = [("srv-02", "hb=20;fence=40")]
        output = self.failure(sl.EXIT_REGISTRATION)
        self.assertTrue(any("srv-02" in x and "hb=20" in x for x in output), "as duas configuracoes no log")

    def test_ambientes(self):
        self.repo.environments = ([], ["DEV"])
        self.failure(sl.EXIT_ENVIRONMENTS)
        self.repo.environments = ([], [])
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            ag = self.agent().initialize()
        self.assertEqual(ag.active_environments, [])
        self.assertTrue(any("DEV inativo" in x for x in logs.output))

    def test_thread_unica(self):
        stop = threading.Event()
        t = threading.Thread(target=stop.wait, name="thread-intrusa")
        t.start()
        try:
            output = self.failure(sl.EXIT_THREADS)
        finally:
            stop.set()
            t.join()
        self.assertTrue(any("thread-intrusa" in x for x in output))


class TestStartupCheck(_Base):

    def test_saida_em_gravacao_vira_falhou(self):
        # CR-012 (README §8.13): queda durante a gravacao do zip; a pasta fica no disco.
        self.repo_output.rows = {5: {"state": "WRITING", "agent_id": "srv-t", "content": b"PK"},
                                  6: {"state": "WRITING", "agent_id": "outro", "content": b"PK"}}
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.agent().initialize()
        self.assertEqual(self.repo_output.rows[5]["state"], "FAILED")
        self.assertEqual(self.repo_output.rows[6]["state"], "WRITING", "so as deste agente")
        self.assertTrue(any("1 saida(s) em gravacao" in x for x in logs.output))


    def _dir(self, tid, **states):
        dir_value = executor.prepare_directory(self.work, tid)
        for name, data in states.items():
            os_platform.write_state(os.path.join(dir_value, "." + name), data)
        return dir_value

    def _group(self, command="sleep 300 & sleep 300"):
        p = subprocess.Popen(["/bin/sh", "-c", command], start_new_session=True)
        self.popens.append(p)
        time.sleep(0.2)
        return p

    def _start_agent(self, **kw):
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            ag = self.agent(**kw).initialize()
        return ag, "\n".join(logs.output)

    def test_grupo_vivo_e_encerrado_e_ticket_orfao(self):
        p = self._group()
        dir_value = self._dir(5, sss_proc={"ticket_id": 5, "pid": p.pid, "pgid": p.pid, "exec_user": None,
                                         "process_start": os_platform.process_identity(p.pid)})
        self.repo.running = [{"id": 5, "process_id": p.pid, "process_start": None, "cancel_requested": "N"}]
        ag, _logs = self._start_agent()
        self.assertIn(("finalize", 5, "FAILED", "ORPHAN_PROCESS", -2), self.repo.calls)
        self.assertTrue(self.repo_log.rows[0][1].startswith("[SSS] ORPHAN_PROCESS: "))
        self.assertIn(5, ag.stopping, "o laco termina o encerramento e so entao limpa")
        self.assertTrue(os.path.isdir(dir_value))
        ex = ag.stopping[5]
        limit = time.monotonic() + 5
        while not executor.advance_stop(ex, time.monotonic() + 10) and time.monotonic() < limit:
            time.sleep(0.05)
        self.assertEqual(p.wait(5), -signal.SIGTERM)

    def test_ticket_ja_finalizado_por_outro_no_com_filho_vivo(self):
        # NODE_OFFLINE no banco com o filho vivo: o disco manda; o grupo e encerrado e nada e finalizado.
        p = self._group()
        self._dir(6, sss_proc={"ticket_id": 6, "pid": p.pid, "pgid": p.pid, "exec_user": None,
                                 "process_start": os_platform.process_identity(p.pid)})
        ag, _logs = self._start_agent()
        self.assertEqual(self.repo.calls, [])
        self.assertIn(6, ag.stopping)
        self.assertEqual(ag.stopping[6].phase, executor.PHASE_TERM)

    def test_pid_reciclado_nao_recebe_sinal(self):
        p = self._group("sleep 300")
        dir_value = self._dir(7, sss_proc={"ticket_id": 7, "pid": p.pid, "pgid": p.pid, "exec_user": None,
                                         "process_start": os_platform.process_identity(p.pid) + 1})
        self.repo.running = [{"id": 7, "process_id": p.pid, "process_start": None, "cancel_requested": "N"}]
        ag, _logs = self._start_agent()
        self.assertTrue(_alive(p.pid), "PID reciclado: o processo de agora nao e o do ticket")
        self.assertIn(("finalize", 7, "FAILED", "ORPHAN_PROCESS", -2), self.repo.calls)
        self.assertFalse(os.path.exists(dir_value))

    def test_resultado_local_prevalece(self):
        dir_value = self._dir(8, sss_proc={"ticket_id": 8, "pid": 2 ** 31 - 2, "pgid": 2 ** 31 - 2,
                                         "exec_user": None, "process_start": 1},
                            sss_result={"ticket_id": 8, "status": "SUCCESS", "status_reason": "EXIT_OK",
                                        "return_code": 0})
        self.repo.running = [{"id": 8, "process_id": 1, "process_start": 1, "cancel_requested": "N"}]
        self._start_agent()
        self.assertIn(("finalize", 8, "SUCCESS", "EXIT_OK", 0), self.repo.calls)
        self.assertFalse(os.path.exists(dir_value))

    def test_sem_identidade_preserva_a_pasta(self):
        p = self._group("sleep 300")
        dir_value = self._dir(9, sss_proc={"ticket_id": 9, "pid": p.pid, "pgid": p.pid, "exec_user": None,
                                         "process_start": None})
        self.repo.running = [{"id": 9, "process_id": p.pid, "process_start": None, "cancel_requested": "N"}]
        plat = _Plat(reopen_group=lambda state: os_platform.Process(p.pid, None, no_identity=True))
        ag, logs = self._start_agent(plat=plat)
        self.assertIn("ORFAO_SEM_IDENTIDADE", logs)
        self.assertTrue(_alive(p.pid), "sem identidade nunca recebe sinal")
        self.assertIn(9, ag.preserved)
        self.assertTrue(os.path.isdir(dir_value), "CR-008, R-26: o unico rastro do processo fica")
        self.assertIn(("finalize", 9, "FAILED", "ORPHAN_PROCESS", -2), self.repo.calls)

    def test_talvez_iniciado_nunca_volta_a_fila(self):
        dir_value = self._dir(10, sss_spawn={"ticket_id": 10, "exec_user": None})
        grandchild = subprocess.Popen(["sleep", "300"], cwd=os.path.join(dir_value, "tmp"), start_new_session=True)
        self.popens.append(grandchild)
        self.repo.running = [{"id": 10, "process_id": None, "process_start": None, "cancel_requested": "N"}]
        _ag, logs = self._start_agent()
        self.assertIn("TALVEZ_INICIADO", logs)
        self.assertNotIn(("return_to_queue", 10), self.repo.calls)
        self.assertIn(("finalize", 10, "FAILED", "ORPHAN_PROCESS", -2), self.repo.calls)
        self.assertEqual(grandchild.wait(5), -signal.SIGTERM, "encerrado pelo diretorio atual na pasta do ticket")
        self.assertFalse(os.path.exists(dir_value))

    def test_talvez_iniciado_nao_suportado_preserva(self):
        dir_value = self._dir(11, sss_spawn={"ticket_id": 11, "exec_user": None})
        self.repo.running = [{"id": 11, "process_id": None, "process_start": None, "cancel_requested": "N"}]
        ag, logs = self._start_agent(plat=_Plat(stop_ticket=lambda *a: "UNSUPPORTED"))
        self.assertIn("sem meio de encerrar", logs)
        self.assertIn(11, ag.preserved)
        self.assertTrue(os.path.isdir(dir_value))
        self.assertIn(("finalize", 11, "FAILED", "ORPHAN_PROCESS", -2), self.repo.calls)

    def test_running_sem_pasta(self):
        self.repo.running = [{"id": 12, "process_id": None, "process_start": None, "cancel_requested": "N"},
                             {"id": 13, "process_id": 999, "process_start": 1, "cancel_requested": "N"}]
        self._start_agent()
        self.assertIn(("return_to_queue", 12), self.repo.calls)
        self.assertIn(("finalize", 13, "FAILED", "ORPHAN_PROCESS", -2), self.repo.calls)

    def test_pasta_vazia_e_removida_e_link_ignorado(self):
        dir_value = self._dir(14)
        outside = os.path.join(self.root, "fora")
        os.mkdir(outside)
        os.symlink(outside, os.path.join(self.work, "ticket_15"))
        self._start_agent()
        self.assertFalse(os.path.exists(dir_value))
        self.assertTrue(os.path.isdir(outside), "link simbolico nunca seguido")
        self.assertEqual(self.repo.calls, [])

    def test_falha_de_banco_no_startup_check(self):
        def _erro(*a):
            raise RuntimeError("ORA-03113: end-of-file on communication channel")
        self.repo.agent_running_tickets = _erro
        self.failure(sl.EXIT_STARTUP)


class TestSource(unittest.TestCase):

    def test_sem_primitivas_de_so_nem_gluon(self):
        with open(sl.__file__, encoding="utf-8") as f:
            source = f.read()
        for forbidden in ("os.killpg", "os.kill(", "time.sleep", "subprocess", "sys.platform", "gluon", "/proc/"):
            self.assertFalse(forbidden in source, forbidden)


if __name__ == "__main__":
    unittest.main()
