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
from _output_memory import RepoSaidaMemoria

AGENTE_FALSO = 2 ** 31 - 3
AMB = "DEV"
SENHA_AMB = "SenhaDoAmbiente#2026"

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


class _ErroRede(Exception):
    def __init__(self):
        Exception.__init__(self, "DPY-4011: the database or network closed the connection")


class _ErroPrivilegio(Exception):
    def __init__(self):
        Exception.__init__(self, "ORA-01031: insufficient privileges")


class _Banco(object):
    """Banco em memoria: tickets, scripts, ambiente, homologacao, contexto RBAC e o CLOB do log."""

    def __init__(self, raiz):
        self.lock = threading.Lock()
        self.tickets = {}
        self.scripts = {}
        self.ambiente = {"id": 1, "name": AMB, "description": "Desenvolvimento", "connection": "db:1521/dev", "active": "Y"}
        self.homologados = set()
        self.ctx = rbac.contexto_usuario({
            "user_id": 9, "login": "ana", "profile_id": 2, "usuario_ativo": "Y", "perfil_ativo": "Y",
            "is_admin": "N", "perm_version": 1, "features": ["EXEC_SCRIPT"], "environments": [AMB],
            "scripts": []})
        self.falhas = collections.defaultdict(list)
        self.chamadas = collections.defaultdict(int)
        self.claim_respostas = []
        self.heartbeats = []
        self.agente_ativo = True
        self.encerrou = None
        self.max_running = 0
        self.seq = 100
        self.unidade = 2
        # F8.4c: tickets de outro agente que o NODE_OFFLINE deve marcar, chamadas e o deslocamento do SYSDATE.
        self.offline = set()
        self.node_offline_chamadas = 0
        self.sysdate_deslocamento_s = 0

    def _falhar(self, metodo):
        self.chamadas[metodo] += 1
        if self.falhas[metodo]:
            erro = self.falhas[metodo].pop(0)
            if erro is not None:
                raise erro

    # -- massa

    def script(self, corpo, timeout=None, active="Y", max_par=5, interpreter="SH", homologar=True):
        self.seq += 1
        sid = self.seq
        caminho = os.path.join(self.base, "s%d.sh" % sid)
        with open(caminho, "w") as f:
            f.write(corpo)
        os.chmod(caminho, 0o444)
        self.scripts[sid] = {"id": sid, "name": "Script %d" % sid, "interpreter": interpreter,
                             "path_file": caminho, "active": active, "timeout_s": timeout,
                             "max_parallel_env": max_par}
        if homologar:
            self.homologados.add(sid)
        self.ctx = dict(self.ctx, scripts=frozenset(set(self.ctx["scripts"]) | {sid}))
        return sid

    def ticket(self, sid, version=4, args=(), path_file=None, interpretador=None, agendamento_id=None):
        self.seq += 1
        s = self.scripts[sid]
        snap = {"version": version, "script_id": sid, "script_nome": s["name"],
                "interpreter": interpretador or s["interpreter"], "path_file": path_file or s["path_file"],
                "param_type": "NAMED", "args": list(args), "respostas": {}, "sensiveis": [],
                "compilado_em": "2026-10-20 10:00:00"}
        self.tickets[self.seq] = {
            "id": self.seq, "script_id": sid, "environment": AMB, "requested_by": "ana", "status": "PENDING",
            "priority": 2, "cancel_requested": "N", "agent_id": None, "process_id": None, "process_start": None,
            "parent_ticket_id": None, "schedule_id": agendamento_id, "scheduled_at": None, "started_at": None,
            "created_at": None, "log_offset_chars": 0, "submitted_params": json.dumps(snap), "log": "",
            "status_reason": None, "return_code": None, "updated_by": None}
        return self.seq

    # -- contrato do RepoSchedulerQueue

    def active_environments(self, conn, atendidos):
        self._falhar("active_environments")
        return ([AMB] if self.ambiente["active"] == "Y" and AMB in atendidos else []), []

    def check_config(self, conn, agente_id, criticos, offline):
        self._falhar("check_config")
        return []

    def candidates(self, conn, ambientes, interpretadores, lote, env_min):
        self._falhar("candidates")
        with self.lock:
            return [{"id": t["id"], "script_id": t["script_id"], "environment": t["environment"]}
                    for t in sorted(self.tickets.values(), key=lambda x: x["id"])
                    if t["status"] == "PENDING" and t["cancel_requested"] == "N"
                    and self.scripts[t["script_id"]]["interpreter"] in interpretadores][:lote]

    def claim(self, conn, tid, sid, ambiente, agente_id):
        self._falhar("claim")
        if self.claim_respostas:
            resposta = self.claim_respostas.pop(0)
            if resposta is not None:
                return resposta
        with self.lock:
            t = self.tickets[tid]
            running = sum(1 for x in self.tickets.values() if x["status"] == "RUNNING" and x["script_id"] == sid)
            if running >= self.scripts[sid]["max_parallel_env"]:
                return False, "TETO", None
            if t["status"] != "PENDING" or t["cancel_requested"] != "N":
                return False, "PERDIDO", None
            t.update(status="RUNNING", agent_id=agente_id, started_at=datetime.datetime(2026, 10, 20, 14, 5),
                     log="", log_offset_chars=0, updated_by="SYSTEM:%s" % agente_id)
            self.max_running = max(self.max_running, sum(1 for x in self.tickets.values() if x["status"] == "RUNNING"))
            return True, None, t["started_at"]

    def get_ticket(self, conn, tid):
        self._falhar("get_ticket")
        return dict(self.tickets[tid]) if tid in self.tickets else None

    def execution_context(self, conn, ticket):
        self._falhar("execution_context")
        s = self.scripts.get(ticket["script_id"])
        return {"script": dict(s) if s else None, "environment": dict(self.ambiente),
                "homologacoes": frozenset({1}) if ticket["script_id"] in self.homologados else frozenset(),
                "ctx": self.ctx, "agendamento": None}

    def active_homologated_script(self, conn, sid, ambiente):
        return self.scripts[sid]["active"] == "Y" and sid in self.homologados

    def is_cancel_requested(self, conn, tid):
        self._falhar("is_cancel_requested")
        return self.tickets[tid]["cancel_requested"] == "Y"

    def register_pid(self, conn, tid, agente_id, pid, start):
        self._falhar("register_pid")
        t = self.tickets[tid]
        if t["status"] != "RUNNING" or t["agent_id"] != agente_id:
            return False
        t.update(process_id=pid, process_start=start)
        return True

    def return_to_queue(self, conn, tid, agente_id):
        self._falhar("return_to_queue")
        t = self.tickets[tid]
        if t["status"] == "RUNNING" and t["agent_id"] == agente_id and t["process_id"] is None:
            if t["cancel_requested"] == "N":
                t.update(status="PENDING", agent_id=None, log="", log_offset_chars=0)
                return "DEVOLVIDO"
            t.update(status="CANCELLED", status_reason="CANCEL_USER", return_code=-1)
            return "CANCELADO"
        return "PERDIDO"

    def finalize(self, conn, tid, agente_id, status, motivo, rc):
        self._falhar("finalize")
        t = self.tickets[tid]
        if t["status"] != "RUNNING" or t["agent_id"] != agente_id:
            return False
        t.update(status=status, status_reason=motivo, return_code=rc, updated_by="SYSTEM:%s" % agente_id)
        return True

    def own_sweep(self, conn, agente_id):
        self._falhar("own_sweep")
        return dict((t["id"], t["cancel_requested"]) for t in self.tickets.values()
                    if t["status"] == "RUNNING" and t["agent_id"] == agente_id)

    def tickets_running_do_agente(self, conn, agente_id):
        return [{"id": t["id"], "process_id": t["process_id"], "process_start": t["process_start"],
                 "cancel_requested": t["cancel_requested"]} for t in self.tickets.values()
                if t["status"] == "RUNNING" and t["agent_id"] == agente_id]

    def heartbeat(self, conn, agente_id, hostname, pid, ids):
        self._falhar("heartbeat")
        if not self.agente_ativo:
            raise RegistrationLost("registro assumido")
        self.heartbeats.append(list(ids))
        perdidos = [i for i in ids if self.tickets[i]["status"] != "RUNNING" or self.tickets[i]["agent_id"] != agente_id]
        return perdidos, self.sysdate()

    def sysdate(self):
        return datetime.datetime.now() + datetime.timedelta(seconds=self.sysdate_deslocamento_s)

    def mark_node_offline(self, conn, agente_id, timeout_s, salto_de_relogio):
        self._falhar("mark_node_offline")
        self.node_offline_chamadas += 1
        if salto_de_relogio(self.sysdate()):
            return None
        marcados = []
        for tid in sorted(self.offline):
            t = self.tickets[tid]
            if t["status"] == "RUNNING" and t["agent_id"] != agente_id:
                t.update(status="FAILED", status_reason="NODE_OFFLINE", return_code=-2,
                         updated_by="SYSTEM:%s" % agente_id)
                marcados.append(tid)
        return marcados

    def register_agent(self, conn, dados, processo_existe):
        return 1

    def stop_agent(self, conn, agente_id, hostname, pid, modo):
        self.encerrou = modo
        return True

    # -- contrato do RepoSchedulerLog

    def supplementary_unit(self, conn):
        return self.unidade

    def append_chunk(self, conn, tid, agente_id, offset, bloco):
        self._falhar("append_chunk")
        t = self.tickets[tid]
        if t["status"] != "RUNNING" or t["agent_id"] != agente_id:
            return "OWNERSHIP_LOST"
        if t["log_offset_chars"] != offset:
            return "ALREADY_WRITTEN"
        t["log"] += bloco
        t["log_offset_chars"] += log_pump.unidades_clob(bloco, self.unidade)
        return "WRITTEN"

    def mark_truncated(self, conn, tid, agente_id):
        return True


class _AgendaVazia(object):
    """Sem regras vencidas: o desdobro (F8.4b) e testado no test_scheduler_ha."""

    def due_rules(self, conn, lote, ult_prox=None, ult_id=0):
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


class _Conexao(object):
    def __init__(self):
        self.conn = _Conn()
        self.fora = False
        self.fechamentos = 0

    def ensure(self):
        return not self.fora

    def get_connection(self):
        return None if self.fora else self.conn

    def close(self):
        self.fechamentos += 1

    def notify_error(self, exc):
        pass


@unittest.skipIf(os.geteuid() == 0, "o agente nunca roda como root")
class _Base(unittest.TestCase):

    def setUp(self):
        self.raiz = os.path.realpath(tempfile.mkdtemp(prefix="sss_laco_"))
        self.work = os.path.join(self.raiz, "work")
        self.logs = os.path.join(self.raiz, "logs")
        os.mkdir(self.work, 0o700)
        os.mkdir(self.logs, 0o750)
        self.banco = _Banco(self.raiz)
        self.banco.base = os.path.join(self.raiz, "scripts")
        os.mkdir(self.banco.base)
        self.conexao = _Conexao()
        self.parada = threading.Event()
        self._espera = threading.Event()
        self.ag = None

    def tearDown(self):
        if self.ag is not None:
            for item in list(getattr(self.ag, "execucoes", {}).values()):
                if item.execucao is not None and item.execucao.processo is not None:
                    try:
                        os.killpg(item.execucao.pgid if hasattr(item.execucao, "pgid") else item.execucao.pid,
                                  signal.SIGKILL)
                    except OSError:
                        pass
                    if item.execucao.processo.popen is not None:
                        item.execucao.processo.popen.wait(5)
            self.ag.liberar_recursos()
        for atual, dirs, _arqs in os.walk(self.raiz):
            for d in dirs:
                os.chmod(os.path.join(atual, d), 0o700)
        shutil.rmtree(self.raiz, ignore_errors=True)

    def cfg(self, **mudancas):
        base = dict(agent_id="srv-t", environments=(AMB,), work_dir=self.work,
                    interpreters=(("SH", "/bin/sh"),), exec_users=(), exec_work_dir=None,
                    heartbeat_interval_s=0.2, fence_timeout_s=40, node_offline_timeout_s=120, kill_grace_s=1,
                    misfire_policy="RUN_ONCE", misfire_tolerance_s=300, cron_horizon_days=366,
                    queue_aging_min=30, child_locale="C.UTF-8",
                    cancel_poll_interval_s=0.05, orchestrator_interval_s=0.05, max_parallel_jobs=4,
                    log_dir_min_free_mb=1, script_timeout_s=60, env_passthrough=())
        local = mudancas.pop("max_local_log_size_bytes", 10 * 1024 * 1024)
        base.update(mudancas)
        return _Cfg(_Agent(**base), _Log(self.logs, 5 * 1024 * 1024, local), _App("DEV"),
                    _Oracle("db:1521/x", 30000, "OWN_X", "pfx_"), None)

    def subir(self, **mudancas):
        segredos = Secrets("SenhaOracle#1", None, {AMB: EnvironmentSecret("app_dev", SENHA_AMB)})
        plat = mudancas.pop("plat", None)
        with mock.patch.object(sl.os, "geteuid", return_value=AGENTE_FALSO):
            if getattr(self, "repo_saida", None) is None:
                self.repo_saida = RepoSaidaMemoria(self.banco.tickets)
            self.ag = sl.Agente(cfg=self.cfg(**mudancas), segredos=segredos, plat=plat, conexao=self.conexao,
                                repo=self.banco, repo_log=self.banco, hostname="host-t", pid=os.getpid(),
                                repo_saida=self.repo_saida, repo_agenda=_AgendaVazia())
            self.ag.inicializar()
        self.ag.preparar_laco(lambda s: self._espera.wait(min(s, 0.02)))
        return self.ag

    def rodar(self, ate, limite=15):
        with mock.patch.object(time, "sleep", side_effect=AssertionError("time.sleep dentro do laco")):
            codigo = self.ag.executar(self.parada, ate=ate, limite_s=limite)
        return codigo

    def terminado(self, tid):
        return lambda: self.banco.tickets[tid]["status"] not in ("PENDING", "RUNNING") and tid not in self.ag.execucoes

    def final(self, tid):
        t = self.banco.tickets[tid]
        return t["status"], t["status_reason"], t["return_code"]


class TestExecucao(_Base):

    def test_sucesso_com_log_mascarado_e_limpeza(self):
        sid = self.banco.script("echo inicio\necho \"connection=$PADRAO_VALOR_RUN_CONEXAO_BD\"\necho \"$SSS_TICKET_ID\"\n")
        tid = self.banco.ticket(sid)
        self.subir()
        self.rodar(self.terminado(tid))
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0))
        t = self.banco.tickets[tid]
        self.assertNotIn("sha256", t["log"], "CR-011: sem hash")
        self.assertIn("inicio\n", t["log"])
        self.assertIn("connection=****\n", t["log"], "a connect string inteira e segredo do ticket (README §8.10)")
        self.assertNotIn(SENHA_AMB, t["log"])
        self.assertIn("%d\n" % tid, t["log"])
        self.assertIsNotNone(t["process_id"])
        self.assertEqual(t["updated_by"], "SYSTEM:srv-t")
        self.assertFalse(os.path.exists(os.path.join(self.work, "ticket_%d" % tid)), "limpeza no fim")

    def test_script_cadastrado_por_link_executa_o_real(self):
        # CR-011: o caminho cadastrado e um link; o agente executa o arquivo real e informa os dois.
        sid = self.banco.script("echo \"$SSS_SCRIPT_FILE|$SSS_SCRIPT_LINK\"\n")
        real = self.banco.scripts[sid]["path_file"]
        os.chmod(self.banco.base, 0o755)
        link = os.path.join(self.banco.base, "atalho.sh")
        os.symlink(real, link)
        os.chmod(self.banco.base, 0o555)
        self.banco.scripts[sid]["path_file"] = link
        tid = self.banco.ticket(sid)
        self.subir()
        self.rodar(self.terminado(tid))
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0))
        self.assertIn("%s|%s\n" % (real, link), self.banco.tickets[tid]["log"])

    def test_cr014_pasta_de_entrada_permanente_por_ambiente_e_script(self):
        # CR-014 (README §8.14): SSS_INPUT_DIR = input_dir/<ambiente>/<script>, criada sob demanda e mantida.
        entrada = os.path.join(self.raiz, "input")
        os.mkdir(entrada, 0o700)
        sid = self.banco.script('n=$(ls "$SSS_INPUT_DIR" | wc -l)\n'
                                'echo "dir=$SSS_INPUT_DIR n=$n"\n'
                                'echo ok > "$SSS_INPUT_DIR/lote_$SSS_TICKET_ID.txt"\n')
        primeiro = self.banco.ticket(sid)
        self.subir(input_dir=entrada)
        self.rodar(self.terminado(primeiro))
        segundo = self.banco.ticket(sid)
        self.rodar(self.terminado(segundo))
        pasta = os.path.join(entrada, "dev", "script_%d" % sid)
        for tid, n in ((primeiro, 0), (segundo, 1)):
            self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0))
            self.assertIn("dir=%s n=%d" % (pasta, n), self.banco.tickets[tid]["log"])
        self.assertEqual(sorted(os.listdir(pasta)), ["lote_%d.txt" % primeiro, "lote_%d.txt" % segundo],
                         "o SSS nao limpa a pasta de entrada")
        self.assertEqual(os.stat(pasta).st_mode & 0o777, 0o700)

    def test_cr014_sem_entrada_dir_sem_variavel(self):
        tid = self.banco.ticket(self.banco.script('echo "entrada=[${SSS_INPUT_DIR:-}]"\n'))
        self.subir()
        self.rodar(self.terminado(tid))
        self.assertIn("entrada=[]", self.banco.tickets[tid]["log"])

    def test_exit_error(self):
        tid = self.banco.ticket(self.banco.script("echo falhou\nexit 3\n"))
        self.subir()
        self.rodar(self.terminado(tid))
        self.assertEqual(self.final(tid), ("FAILED", "EXIT_ERROR", 3))

    def test_timeout_mata_o_neto(self):
        neto = os.path.join(self.raiz, "neto.pid")
        tid = self.banco.ticket(self.banco.script("sleep 300 &\necho $! > %s\nsleep 300\n" % neto, timeout=1))
        self.subir()
        self.rodar(self.terminado(tid))
        self.assertEqual(self.final(tid), ("FAILED", "TIMEOUT", -3))
        pid_neto = int(open(neto).read().strip())
        self.assertFalse(_vivo(pid_neto))

    def test_cancelamento_durante_a_execucao(self):
        pronto = os.path.join(self.raiz, "pronto")
        tid = self.banco.ticket(self.banco.script("touch %s\nsleep 300\n" % pronto))
        self.subir()
        self.rodar(lambda: os.path.exists(pronto))
        self.banco.tickets[tid]["cancel_requested"] = "Y"
        self.rodar(self.terminado(tid))
        self.assertEqual(self.final(tid), ("CANCELLED", "CANCEL_USER", -1))

    def test_cancelamento_entre_o_claim_e_o_spawn(self):
        tid = self.banco.ticket(self.banco.script("echo nunca\n"))
        original = self.banco.is_cancel_requested
        def _pedido(conn, t):
            self.banco.tickets[t]["cancel_requested"] = "Y"
            return original(conn, t)
        self.banco.is_cancel_requested = _pedido
        self.subir()
        self.rodar(self.terminado(tid))
        self.assertEqual(self.final(tid), ("CANCELLED", "CANCEL_USER", -1))
        self.assertIsNone(self.banco.tickets[tid]["process_id"], "nenhum processo iniciado")

    def test_processo_que_terminou_antes_do_cancelamento_prevalece(self):
        self.subir()
        item = sl._Item(1, None, self.ag.log)
        item.fase = sl._Item.RODANDO
        p = subprocess.Popen(["true"], start_new_session=True)
        p.wait()
        item.execucao = executor.Execucao(1, self.work, None, None, None)
        item.execucao.processo = os_platform.Processo(p.pid, None, popen=p)
        item.execucao.pid = p.pid
        self.ag._encerrar(item, "CANCEL")
        self.assertIsNone(item.motivo)
        self.assertEqual(self.ag._resultado(item), ("SUCCESS", "EXIT_OK", 0))

    def test_log_limit(self):
        tid = self.banco.ticket(self.banco.script("head -c 5000 /dev/zero | tr '\\000' x\nsleep 300\n"))
        self.subir(max_local_log_size_bytes=2048)
        self.rodar(self.terminado(tid))
        self.assertEqual(self.final(tid), ("FAILED", "LOG_LIMIT", -5))

    def test_ownership_lost_na_varredura(self):
        pronto = os.path.join(self.raiz, "pronto")
        tid = self.banco.ticket(self.banco.script("touch %s\nsleep 300\n" % pronto))
        self.subir()
        self.rodar(lambda: os.path.exists(pronto))
        pid = self.banco.tickets[tid]["process_id"]
        self.banco.tickets[tid].update(status="FAILED", status_reason="NODE_OFFLINE", return_code=-2)
        with self.assertLogs("sss_scheduler", "ERROR") as logs:
            self.rodar(lambda: tid not in self.ag.execucoes)
        self.assertEqual(self.final(tid), ("FAILED", "NODE_OFFLINE", -2), "nenhum status gravado")
        self.assertTrue(any("OWNERSHIP_LOST" in x for x in logs.output))
        self.assertFalse(_vivo(pid))

    def test_teto_paralelo(self):
        sid = self.banco.script("sleep 0.5\n", max_par=10)
        tids = [self.banco.ticket(sid) for _ in range(5)]
        self.subir(max_parallel_jobs=2)
        self.rodar(lambda: all(self.terminado(t)() for t in tids), limite=30)
        self.assertEqual(self.banco.max_running, 2)
        self.assertEqual([self.final(t)[0] for t in tids], ["SUCCESS"] * 5)

    def test_lock_no_claim_tenta_de_novo(self):
        tid = self.banco.ticket(self.banco.script("echo ok\n"))
        self.banco.claim_respostas = [(False, "LOCK", "ORA-30006"), (False, "TETO", None)]
        self.subir()
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.rodar(self.terminado(tid))
        avisos = [r.getMessage() for r in logs.records if "pulado" in r.getMessage()]
        self.assertEqual(len(avisos), 1, "WARN so no LOCK, nao no TETO (README §13, CR-007 R-32)")
        self.assertIn("claim do ticket %d pulado: linha do script" % tid, avisos[0])
        self.assertIn("(ORA-30006, FOR UPDATE WAIT 5)", avisos[0])
        self.assertFalse([r for r in logs.records if "pulado" in r.getMessage() and r.exc_info], "sem stack trace")
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0))
        self.assertGreaterEqual(self.banco.chamadas["claim"], 3)


class TestPrevalidacao(_Base):

    def _recusa(self, tid, codigo, **subir):
        self.subir(**subir)
        self.rodar(self.terminado(tid))
        self.assertEqual(self.final(tid), ("FAILED", "PRECHECK_FAILED", -4))
        self.assertIn("[SSS] pre-validacao recusada: %s (agente srv-t)" % codigo, self.banco.tickets[tid]["log"])
        self.assertIsNone(self.banco.tickets[tid]["process_id"])

    def test_cr014_script_dentro_da_entrada_ou_da_saida_e_pasta_do_sss(self):
        # CR-014: o usuario de execucao grava em input_dir e output_dir; um script ali poderia ser trocado.
        for chave in ("input_dir", "output_dir"):
            pasta = os.path.join(self.raiz, chave)
            os.mkdir(pasta, 0o700)
            sid = self.banco.script("echo nao deveria rodar\n")
            caminho = os.path.join(pasta, "s%d.sh" % sid)
            os.rename(self.banco.scripts[sid]["path_file"], caminho)
            self.banco.scripts[sid]["path_file"] = caminho
            tid = self.banco.ticket(sid)
            self._recusa(tid, "PASTA_DO_SSS", **{chave: pasta})
            self.ag.liberar_recursos()

    def test_snapshots_antigos(self):
        sid = self.banco.script("echo x\n")
        tids = [self.banco.ticket(sid, version=versao) for versao in (1, 2, 3)]
        self.subir()
        self.rodar(lambda: all(self.terminado(t)() for t in tids))
        for tid in tids:
            self.assertEqual(self.final(tid), ("FAILED", "PRECHECK_FAILED", -4))
            self.assertIn("[SSS] pre-validacao recusada: VERSAO_NAO_SUPORTADA", self.banco.tickets[tid]["log"])

    def test_interpretador_nao_mapeado(self):
        # O script e BASH, mas este agente so mapeia SH; a fila de teste entrega o ticket mesmo assim.
        tid = self.banco.ticket(self.banco.script("echo x\n", interpreter="BASH"))
        self.banco.candidates = lambda conn, a, i, lote, env: [
            {"id": tid, "script_id": self.banco.tickets[tid]["script_id"], "environment": AMB}
        ] if self.banco.tickets[tid]["status"] == "PENDING" else []
        self._recusa(tid, "INTERPRETADOR_NAO_DISPONIVEL")

    def test_caminho_inexistente(self):
        sid = self.banco.script("echo x\n")
        t1 = self.banco.ticket(sid, path_file=os.path.join(self.banco.base, "nao.sh"))
        self._recusa(t1, "NAO_ENCONTRADO")

    def test_cadastro_mudou(self):
        sid = self.banco.script("echo x\n")
        outro = self.banco.script("echo y\n")
        tid = self.banco.ticket(sid, path_file=self.banco.scripts[outro]["path_file"])
        self._recusa(tid, "CADASTRO_MUDOU")

    def test_sem_permissao(self):
        sid = self.banco.script("echo x\n")
        tid = self.banco.ticket(sid)
        self.banco.ctx = dict(self.banco.ctx, scripts=frozenset())
        self._recusa(tid, "NO_PERMISSION")

    def test_script_inativo(self):
        tid = self.banco.ticket(self.banco.script("echo x\n", active="N"))
        self._recusa(tid, "SCRIPT_INACTIVE")

    def test_nao_homologado(self):
        tid = self.banco.ticket(self.banco.script("echo x\n", homologar=False))
        self._recusa(tid, "NAO_HOMOLOGADO")

    def test_erro_de_rede_antes_do_spawn_devolve(self):
        tid = self.banco.ticket(self.banco.script("echo x\n"))
        self.banco.falhas["execution_context"] = [_ErroRede()]
        self.subir()
        self.rodar(self.terminado(tid))
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0), "devolvido e executado no ciclo seguinte")
        self.assertGreaterEqual(self.banco.chamadas["return_to_queue"], 1)

    def test_erro_de_banco_nao_transitorio_e_precheck(self):
        tid = self.banco.ticket(self.banco.script("echo x\n"))
        self.banco.falhas["execution_context"] = [_ErroPrivilegio()]
        self.subir()
        with self.assertLogs("sss_scheduler", "ERROR"):
            self.rodar(self.terminado(tid))
        self.assertEqual(self.final(tid), ("FAILED", "PRECHECK_FAILED", -4))
        self.assertIn("[SSS] ERRO_BANCO: ORA-01031", self.banco.tickets[tid]["log"])


class TestPendencias(_Base):

    def test_finalizacao_pendente_ate_gravar(self):
        tid = self.banco.ticket(self.banco.script("echo ok\n"))
        self.banco.falhas["finalize"] = [_ErroRede(), _ErroRede()]
        self.subir()
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.rodar(self.terminado(tid))
        self.assertEqual(self.final(tid), ("SUCCESS", "EXIT_OK", 0))
        self.assertEqual(self.banco.chamadas["finalize"], 3)
        self.assertTrue(any("finalizacao pendente" in x for x in logs.output))

    def test_pid_pendente_recebe_heartbeat(self):
        pronto = os.path.join(self.raiz, "pronto")
        tid = self.banco.ticket(self.banco.script("touch %s\nsleep 1\n" % pronto))
        self.banco.falhas["register_pid"] = [_ErroRede()]
        self.subir()
        self.rodar(self.terminado(tid))
        self.assertEqual(self.final(tid)[0], "SUCCESS")
        self.assertIsNotNone(self.banco.tickets[tid]["process_id"])
        self.assertTrue(any(tid in ids for ids in self.banco.heartbeats))

    def test_posse_perdida_no_registrar_pid(self):
        tid = self.banco.ticket(self.banco.script("sleep 300\n"))
        original = self.banco.register_pid
        def _perdeu(conn, t, *a):
            self.banco.tickets[t]["agent_id"] = "outro"
            return original(conn, t, *a)
        self.banco.register_pid = _perdeu
        self.subir()
        with self.assertLogs("sss_scheduler", "ERROR"):
            self.rodar(lambda: tid not in self.ag.execucoes and self.banco.chamadas["own_sweep"] > 0)
        self.assertEqual(self.banco.tickets[tid]["status"], "RUNNING", "nenhum status gravado pelo agente")

    def test_falha_no_proc_depois_do_spawn_e_spawn_error(self):
        tid = self.banco.ticket(self.banco.script("sleep 300\n"))
        original = os_platform.gravar_estado
        def _grava(caminho, dados):
            if caminho.endswith(executor.PROC):
                raise OSError(28, "No space left on device")
            return original(caminho, dados)
        self.subir()
        with mock.patch.object(os_platform, "gravar_estado", side_effect=_grava), \
                self.assertLogs("sss_scheduler", "ERROR"):
            self.rodar(self.terminado(tid))
        self.assertEqual(self.final(tid), ("FAILED", "SPAWN_ERROR", -4))
        self.assertEqual(self.banco.chamadas["register_pid"], 0)
        self.assertIn("[SSS] falha ao iniciar: OSError (agente srv-t)", self.banco.tickets[tid]["log"])

    def test_reconciliacao_de_ticket_fora_do_mapa(self):
        sid = self.banco.script("echo x\n")
        sem_pid, com_pid = self.banco.ticket(sid), self.banco.ticket(sid)
        self.subir()
        for tid, pid in ((sem_pid, None), (com_pid, 4242)):
            self.banco.tickets[tid].update(status="RUNNING", agent_id="srv-t", process_id=pid)
        self.banco.candidates = lambda *a: []
        self.rodar(lambda: self.banco.tickets[com_pid]["status"] == "FAILED"
                   and self.banco.tickets[sem_pid]["status"] == "PENDING")
        self.assertEqual(self.final(com_pid), ("FAILED", "ORPHAN_PROCESS", -2))


class TestCiclos(_Base):

    def test_heartbeat_sem_tickets_e_instante_de_referencia(self):
        self.subir()
        instantes = []
        original = self.banco.heartbeat
        def _hb(*a):
            instantes.append(self.ag.relogio())
            time_ = original(*a)
            return time_
        self.banco.heartbeat = _hb
        self.rodar(lambda: len(instantes) >= 2)
        self.assertEqual(self.banco.heartbeats[-1], [])
        self.assertLessEqual(self.ag.ultimo_hb_ok, instantes[-1], "R-09: o instante e o de antes do UPDATE")

    def test_registro_perdido_sai_com_codigo_proprio(self):
        self.subir()
        self.banco.agente_ativo = False
        with self.assertLogs("sss_scheduler", "CRITICAL"):
            self.assertEqual(self.rodar(lambda: False, limite=5), sl.SAIDA_REGISTRO_PERDIDO)

    def test_disco_baixo_sem_claim(self):
        tid = self.banco.ticket(self.banco.script("echo x\n"))
        plat = _PlatDisco()
        self.subir(plat=plat, log_dir_min_free_mb=1024)
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.rodar(lambda: False, limite=0.5)
        self.assertEqual(self.banco.tickets[tid]["status"], "PENDING")
        self.assertEqual(self.banco.chamadas["candidates"], 0)
        self.assertEqual(len([x for x in logs.output if "DISCO_LOG" in x]), 1, "uma vez por minuto")

    def test_pump_com_tres_tickets_verbosos(self):
        sid = self.banco.script("i=0\nwhile [ $i -lt 400 ]; do echo \"linha $i $SSS_TICKET_ID xxxxxxxxxxxxxxxxxxxxxxxxxx\"; "
                                "i=$((i+1)); done\n", max_par=5)
        tids = [self.banco.ticket(sid) for _ in range(3)]
        self.subir()
        self.rodar(lambda: all(self.terminado(t)() for t in tids), limite=30)
        for t in tids:
            self.assertEqual(self.banco.tickets[t]["log"].count("linha "), 400)

    def test_parada_pelo_stop(self):
        pronto = os.path.join(self.raiz, "pronto")
        tid = self.banco.ticket(self.banco.script("touch %s\nsleep 300\n" % pronto))
        self.subir()
        self.rodar(lambda: os.path.exists(pronto))
        open(os.path.join(self.work, "sss-srv-t.stop"), "w").close()
        self.assertEqual(self.rodar(lambda: False, limite=15), 0)
        self.assertEqual(self.final(tid), ("FAILED", "SHUTDOWN", -6))
        self.assertEqual(self.banco.encerrou, "TERMINATE")
        self.assertFalse(os.path.exists(os.path.join(self.work, "sss-srv-t.stop")))

    def test_sem_banco_o_processo_segue_acompanhado(self):
        tid = self.banco.ticket(self.banco.script("sleep 300\n", timeout=1))
        self.subir()
        self.rodar(lambda: self.banco.tickets[tid]["process_id"] is not None)
        self.conexao.fora = True
        self.rodar(lambda: self.ag.execucoes[tid].fase != sl._Item.RODANDO, limite=10)
        self.conexao.fora = False
        self.rodar(self.terminado(tid))
        self.assertEqual(self.final(tid), ("FAILED", "TIMEOUT", -3))


class _PlatDisco(object):
    def __getattr__(self, nome):
        if nome == "espaco_livre_mb":
            return lambda caminho: 10
        return getattr(os_platform, nome)


def _vivo(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            conteudo = f.read()
    except OSError:
        return False
    return conteudo[conteudo.rindex(")") + 2:].split()[0] != "Z"


if __name__ == "__main__":
    unittest.main()
