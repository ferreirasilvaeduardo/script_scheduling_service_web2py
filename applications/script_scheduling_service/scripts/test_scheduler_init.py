# -*- coding: utf-8 -*-
"""Testes da inicializacao do agente (F8.3b; README §8.12 passos 1-9; CR-007 R-01, R-11, R-17, R-23; CR-008 R-01,
R-02, R-26, E4).

Plataforma real em DEV (pastas temporarias, /bin/sh, trava de instancia e processos de verdade) e banco simulado
(conexao, repositorio da fila e do log em memoria). Cada falha de passo sai com o proprio codigo e CRITICAL.
"""
import _testenv  # noqa: F401

import collections
import datetime
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import executor
import os_platform
import scheduler_loop as sl
import sql_ident
import sss_config
from repo_oracle.scheduler_queue import DuplicateAgent
from _output_memory import RepoOutputMemory

_Agent = collections.namedtuple("_Agent", (
    "agent_id", "environments", "work_dir", "interpreters", "exec_users",
    "exec_work_dir", "heartbeat_interval_s", "fence_timeout_s", "node_offline_timeout_s", "kill_grace_s",
    "misfire_policy", "misfire_tolerance_s", "cron_horizon_days", "queue_aging_min", "child_locale",
    "output_dir", "input_dir"))
_Agent.__new__.__defaults__ = (None, None)  # CR-012 e CR-014: sem output_dir nem input_dir por padrao
_Cfg = collections.namedtuple("_Cfg", "agent logging app oracle secrets")
_NS = collections.namedtuple("_NS", "log_dir")
_App = collections.namedtuple("_App", "sss_env")
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

    def register_agent(self, conn, date, process_exists):
        self.registro = date
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
            conteudo = f.read()
    except OSError:
        return False
    return conteudo[conteudo.rindex(")") + 2:].split()[0] != "Z"


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
        for atual, dirs, _arqs in os.walk(self.root):
            for d in dirs:
                os.chmod(os.path.join(atual, d), 0o700)
        shutil.rmtree(self.root, ignore_errors=True)

    def cfg(self, **agent):
        base = dict(agent_id="srv-t", environments=("DEV",), work_dir=self.work,
                    interpreters=(("SH", "/bin/sh"),), exec_users=(), exec_work_dir=None,
                    heartbeat_interval_s=10, fence_timeout_s=40, node_offline_timeout_s=120, kill_grace_s=1,
                    misfire_policy="RUN_ONCE", misfire_tolerance_s=300, cron_horizon_days=366,
                    queue_aging_min=30, child_locale="C.UTF-8")
        env = agent.pop("sss_env", "DEV")
        log_dir = agent.pop("log_dir", self.logs)
        base.update(agent)
        return _Cfg(_Agent(**base), _NS(log_dir), _App(env),
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
        texto = "\n".join(logs.output)
        self.assertIn("fence_timeout_s=40 node_offline_timeout_s=120", texto)
        self.assertNotIn("SEM_EXIGENCIA_HASH", texto, "CR-011: sem hash")
        r = self.repo.registro
        self.assertEqual((r["code"], r["hostname"], r["version"], r["platform"], r["interpreters"]),
                         ("srv-t", "host-t", sss_config.SSS_VERSION, os_platform.NAME, "SH"))
        self.assertEqual(r["critical_config"], "hb=10;fence=40;offline=120;call=30;kill=1;misfire=RUN_ONCE;tol=300;"
                                               "horizonte=366;envelhecimento=30")
        self.assertTrue(os.path.exists(os.path.join(self.work, "sss-srv-t.lock")))

    def test_root_recusado(self):
        self.failure(sl.EXIT_USER, self.agent(plat=_Plat(is_privileged_user=lambda: True)))

    def test_codificacao_e_locale(self):
        with mock.patch.object(sss_config.sys, "getfilesystemencoding", return_value="ascii"):
            self.failure(sl.EXIT_CONFIG)
        self.failure(sl.EXIT_CONFIG, self.agent(cfg=self.cfg(child_locale="xx_YY.UTF-8")))

    def test_diretorios_e_interpretadores(self):
        self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=self.cfg(log_dir="/usr/local/sss-logs")))
        self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=self.cfg(work_dir=os.path.join(self.root, "nao"))))
        self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=self.cfg(interpreters=(("SH", "bin/sh"),))))
        self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=self.cfg(interpreters=())))

    def test_validar_execucao_fora_de_dev(self):
        cfg = self.cfg(sss_env="PROD", exec_work_dir=self.root)
        plat = _Plat(validate_execution=lambda *a, **k: ["helper /opt/sss/bin/sss-helper nao encontrado"])
        saida = self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=cfg, plat=plat))
        self.assertTrue(any("helper /opt/sss/bin/sss-helper nao encontrado" in x for x in saida))

    def test_cr014_pasta_de_entrada_na_subida(self):
        # CR-014 (README §8.12 passo 4): input_dir fora das pastas do sistema e existente; fora de DEV, a pasta
        # de cada ambiente atendido do usuario de execucao dele.
        self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=self.cfg(input_dir="/usr/local/sss-entrada")))
        self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=self.cfg(input_dir=os.path.join(self.root, "nao"))))
        entrada = os.path.join(self.root, "entrada")
        os.mkdir(entrada, 0o755)
        self.agent(cfg=self.cfg(input_dir=entrada)).initialize()
        vistos = []

        def _pastas(pairs):
            vistos.extend(pairs)
            return ["%s deve ser diretorio de exec1 sem escrita de grupo nem de outros" % pairs[0][0]]
        plat = _Plat(validate_execution=lambda *a, **k: [], validate_output_dirs=_pastas)
        cfg = self.cfg(sss_env="PROD", exec_work_dir=self.root, exec_users=(("DEV", "exec1"),),
                       input_dir=entrada)
        logs = self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=cfg, plat=plat))
        self.assertEqual(vistos, [(os.path.join(entrada, "dev"), "exec1")])
        self.assertTrue(any("pasta de entrada:" in x for x in logs))

    def test_pasta_de_saida_na_subida(self):
        # CR-012 (README §8.12 passo 4): output_dir fora das pastas do sistema e existente.
        self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=self.cfg(output_dir="/usr/local/sss-saida")))
        self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=self.cfg(output_dir=os.path.join(self.root, "nao"))))
        saida = os.path.join(self.root, "saida")
        os.mkdir(saida, 0o755)
        self.agent(cfg=self.cfg(output_dir=saida)).initialize()
        # Fora de DEV: a pasta de cada ambiente atendido, do usuario de execucao dele.
        vistos = []

        def _pastas(pairs):
            vistos.extend(pairs)
            return ["%s deve ser diretorio de exec1 sem escrita de grupo nem de outros" % pairs[0][0]]
        plat = _Plat(validate_execution=lambda *a, **k: [], validate_output_dirs=_pastas)
        cfg = self.cfg(sss_env="PROD", exec_work_dir=self.root, exec_users=(("DEV", "exec1"),),
                       output_dir=saida)
        logs = self.failure(sl.EXIT_DIRECTORIES, self.agent(cfg=cfg, plat=plat))
        self.assertEqual(vistos, [(os.path.join(saida, "dev"), "exec1")])
        self.assertTrue(any("pasta de saida:" in x for x in logs))

    def test_instancia_unica_e_stop_antigo(self):
        stop = os.path.join(self.work, "sss-srv-t.stop")
        open(stop, "w").close()
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.agent().initialize()
        self.assertFalse(os.path.exists(stop))
        self.assertTrue(any(".stop antigo" in x for x in logs.output))
        codigo = ("import sys\nsys.path.insert(0, %r)\nimport os_platform\n"
                  "try:\n    os_platform.lock_instance(%r)\nexcept os_platform.InstanceAlreadyRunning:\n"
                  "    sys.exit(7)\n" % (os.path.dirname(os.path.abspath(os_platform.__file__)) + "/..",
                                        os.path.join(self.work, "sss-srv-t.lock")))
        self.assertEqual(subprocess.call([sys.executable, "-c", codigo]), 7, "segunda instancia recusada")

    def test_segunda_instancia_no_mesmo_processo(self):
        self.agent().initialize()
        self.failure(sl.EXIT_INSTANCE)

    def test_banco(self):
        self.failure(sl.EXIT_DATABASE, self.agent(connection=_Connection(ok=False)))
        conexao = _Connection()
        conexao.conn.version = sql_ident.SCHEMA_VERSION + 1
        with mock.patch.object(sl.db_conn, "_log_critical"):
            self.failure(sl.EXIT_DATABASE, self.agent(connection=conexao))

    def test_registro(self):
        self.repo.duplicated = True
        self.failure(sl.EXIT_REGISTRATION)
        self.repo.duplicated = False
        self.repo.divergent = [("srv-02", "hb=20;fence=40")]
        saida = self.failure(sl.EXIT_REGISTRATION)
        self.assertTrue(any("srv-02" in x and "hb=20" in x for x in saida), "as duas configuracoes no log")

    def test_ambientes(self):
        self.repo.environments = ([], ["DEV"])
        self.failure(sl.EXIT_ENVIRONMENTS)
        self.repo.environments = ([], [])
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            ag = self.agent().initialize()
        self.assertEqual(ag.active_environments, [])
        self.assertTrue(any("DEV inativo" in x for x in logs.output))

    def test_thread_unica(self):
        parar = threading.Event()
        t = threading.Thread(target=parar.wait, name="thread-intrusa")
        t.start()
        try:
            saida = self.failure(sl.EXIT_THREADS)
        finally:
            parar.set()
            t.join()
        self.assertTrue(any("thread-intrusa" in x for x in saida))


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
        pasta = executor.prepare_directory(self.work, tid)
        for nome, dados in states.items():
            os_platform.write_state(os.path.join(pasta, "." + nome), dados)
        return pasta

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
        pasta = self._dir(5, sss_proc={"ticket_id": 5, "pid": p.pid, "pgid": p.pid, "exec_user": None,
                                         "process_start": os_platform.process_identity(p.pid)})
        self.repo.running = [{"id": 5, "process_id": p.pid, "process_start": None, "cancel_requested": "N"}]
        ag, _logs = self._start_agent()
        self.assertIn(("finalize", 5, "FAILED", "ORPHAN_PROCESS", -2), self.repo.calls)
        self.assertTrue(self.repo_log.rows[0][1].startswith("[SSS] ORPHAN_PROCESS: "))
        self.assertIn(5, ag.stopping, "o laco termina o encerramento e so entao limpa")
        self.assertTrue(os.path.isdir(pasta))
        ex = ag.stopping[5]
        limite = time.monotonic() + 5
        while not executor.advance_stop(ex, time.monotonic() + 10) and time.monotonic() < limite:
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
        pasta = self._dir(7, sss_proc={"ticket_id": 7, "pid": p.pid, "pgid": p.pid, "exec_user": None,
                                         "process_start": os_platform.process_identity(p.pid) + 1})
        self.repo.running = [{"id": 7, "process_id": p.pid, "process_start": None, "cancel_requested": "N"}]
        ag, _logs = self._start_agent()
        self.assertTrue(_alive(p.pid), "PID reciclado: o processo de agora nao e o do ticket")
        self.assertIn(("finalize", 7, "FAILED", "ORPHAN_PROCESS", -2), self.repo.calls)
        self.assertFalse(os.path.exists(pasta))

    def test_resultado_local_prevalece(self):
        pasta = self._dir(8, sss_proc={"ticket_id": 8, "pid": 2 ** 31 - 2, "pgid": 2 ** 31 - 2,
                                         "exec_user": None, "process_start": 1},
                            sss_result={"ticket_id": 8, "status": "SUCCESS", "status_reason": "EXIT_OK",
                                        "return_code": 0})
        self.repo.running = [{"id": 8, "process_id": 1, "process_start": 1, "cancel_requested": "N"}]
        self._start_agent()
        self.assertIn(("finalize", 8, "SUCCESS", "EXIT_OK", 0), self.repo.calls)
        self.assertFalse(os.path.exists(pasta))

    def test_sem_identidade_preserva_a_pasta(self):
        p = self._group("sleep 300")
        pasta = self._dir(9, sss_proc={"ticket_id": 9, "pid": p.pid, "pgid": p.pid, "exec_user": None,
                                         "process_start": None})
        self.repo.running = [{"id": 9, "process_id": p.pid, "process_start": None, "cancel_requested": "N"}]
        plat = _Plat(reopen_group=lambda estado: os_platform.Process(p.pid, None, no_identity=True))
        ag, logs = self._start_agent(plat=plat)
        self.assertIn("ORFAO_SEM_IDENTIDADE", logs)
        self.assertTrue(_alive(p.pid), "sem identidade nunca recebe sinal")
        self.assertIn(9, ag.preserved)
        self.assertTrue(os.path.isdir(pasta), "CR-008, R-26: o unico rastro do processo fica")
        self.assertIn(("finalize", 9, "FAILED", "ORPHAN_PROCESS", -2), self.repo.calls)

    def test_talvez_iniciado_nunca_volta_a_fila(self):
        pasta = self._dir(10, sss_spawn={"ticket_id": 10, "exec_user": None})
        neto = subprocess.Popen(["sleep", "300"], cwd=os.path.join(pasta, "tmp"), start_new_session=True)
        self.popens.append(neto)
        self.repo.running = [{"id": 10, "process_id": None, "process_start": None, "cancel_requested": "N"}]
        _ag, logs = self._start_agent()
        self.assertIn("TALVEZ_INICIADO", logs)
        self.assertNotIn(("return_to_queue", 10), self.repo.calls)
        self.assertIn(("finalize", 10, "FAILED", "ORPHAN_PROCESS", -2), self.repo.calls)
        self.assertEqual(neto.wait(5), -signal.SIGTERM, "encerrado pelo diretorio atual na pasta do ticket")
        self.assertFalse(os.path.exists(pasta))

    def test_talvez_iniciado_nao_suportado_preserva(self):
        pasta = self._dir(11, sss_spawn={"ticket_id": 11, "exec_user": None})
        self.repo.running = [{"id": 11, "process_id": None, "process_start": None, "cancel_requested": "N"}]
        ag, logs = self._start_agent(plat=_Plat(stop_ticket=lambda *a: "NAO_SUPORTADO"))
        self.assertIn("sem meio de encerrar", logs)
        self.assertIn(11, ag.preserved)
        self.assertTrue(os.path.isdir(pasta))
        self.assertIn(("finalize", 11, "FAILED", "ORPHAN_PROCESS", -2), self.repo.calls)

    def test_running_sem_pasta(self):
        self.repo.running = [{"id": 12, "process_id": None, "process_start": None, "cancel_requested": "N"},
                             {"id": 13, "process_id": 999, "process_start": 1, "cancel_requested": "N"}]
        self._start_agent()
        self.assertIn(("return_to_queue", 12), self.repo.calls)
        self.assertIn(("finalize", 13, "FAILED", "ORPHAN_PROCESS", -2), self.repo.calls)

    def test_pasta_vazia_e_removida_e_link_ignorado(self):
        pasta = self._dir(14)
        fora = os.path.join(self.root, "fora")
        os.mkdir(fora)
        os.symlink(fora, os.path.join(self.work, "ticket_15"))
        self._start_agent()
        self.assertFalse(os.path.exists(pasta))
        self.assertTrue(os.path.isdir(fora), "link simbolico nunca seguido")
        self.assertEqual(self.repo.calls, [])

    def test_falha_de_banco_no_startup_check(self):
        def _erro(*a):
            raise RuntimeError("ORA-03113: end-of-file on communication channel")
        self.repo.agent_running_tickets = _erro
        self.failure(sl.EXIT_STARTUP)


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestStartupOracle(_Base):
    """Subida real no owner do config.ini, com agent_id de teste e pastas temporarias; registro removido no fim."""

    def setUp(self):
        _Base.setUp(self)
        from _oracle_test_support import prepare_disposable_schema
        self.cfg_real = prepare_disposable_schema("agent")
        self.code = "tst-f83b-%d" % (int(time.time() * 1000) % 100000000)
        self.addCleanup(self._clean_registration)

    def _clean_registration(self):
        import db_conn
        import sql_ident
        seg = sss_config.load_secrets(self.cfg_real.secrets.secrets_file, cfg=self.cfg_real, role="agent")
        conn = db_conn.connect(self.cfg_real, seg, "agent")
        try:
            o, p = self.cfg_real.oracle.owner.strip(), self.cfg_real.oracle.table_prefix.strip()
            agt = sql_ident.table(o, p, "agents")
            aud = sql_ident.table(o, p, "audit")
            cur = conn.cursor()
            cur.execute("SELECT id FROM " + agt + " WHERE code = :c", c=self.code)
            for (aid,) in cur.fetchall():
                cur.execute("DELETE FROM " + aud + " WHERE entity = 'tbsss_agents' AND entity_id = :id", id=aid)
                cur.execute("DELETE FROM " + agt + " WHERE id = :id", id=aid)
            conn.commit()
        finally:
            conn.close()

    def test_subida_real_e_parada(self):
        import db_conn
        from repo_oracle.scheduler_queue import RepoSchedulerQueue
        cfg = self.cfg_real
        seg = sss_config.load_secrets(cfg.secrets.secrets_file, cfg=cfg, role="agent")
        conn = db_conn.connect(cfg, seg, "agent")
        try:
            import ddl_builder
            ativos, _ = RepoSchedulerQueue.from_config(cfg).active_environments(
                conn, [a[0] for a in ddl_builder.DEFAULT_ENVIRONMENTS])
        finally:
            conn.close()
        self.assertTrue(ativos, "o seed precisa de um ambiente ativo")
        agente = cfg.agent._replace(agent_id=self.code, environments=tuple(ativos[:1]), work_dir=self.work,
                                    interpreters=(("SH", "/bin/sh"),))
        cfg = cfg._replace(agent=agente, logging=cfg.logging._replace(log_dir=self.logs))
        ag = sl.Agent(cfg=cfg, secrets=seg, hostname="host-tst", pid=os.getpid())
        self.agents.append(ag)
        with self.assertLogs("sss_scheduler", "INFO"):
            ag.initialize()
        self.assertIsInstance(ag.agent_db_id, int)
        self.assertIn(ag.supplementary_unit, (1, 2))
        self.assertEqual(ag.active_environments, list(ativos[:1]))
        # Segunda subida do mesmo agent_id, de outro host, enquanto o primeiro esta ativo: recusada.
        outro = sl.Agent(cfg=cfg._replace(agent=agente._replace(work_dir=self.root)), secrets=seg,
                          hostname="outro-host", pid=os.getpid())
        self.agents.append(outro)
        os.makedirs(os.path.join(self.root, "logs2"), exist_ok=True)
        self.failure(sl.EXIT_REGISTRATION, outro)
        self.assertTrue(ag.repo.stop_agent(ag.connection.get_connection(), self.code, "host-tst", os.getpid(),
                                                "TERMINATE"))


class TestSource(unittest.TestCase):

    def test_sem_primitivas_de_so_nem_gluon(self):
        with open(sl.__file__, encoding="utf-8") as f:
            fonte = f.read()
        for proibido in ("os.killpg", "os.kill(", "time.sleep", "subprocess", "sys.platform", "gluon", "/proc/"):
            self.assertFalse(proibido in fonte, proibido)


if __name__ == "__main__":
    unittest.main()
