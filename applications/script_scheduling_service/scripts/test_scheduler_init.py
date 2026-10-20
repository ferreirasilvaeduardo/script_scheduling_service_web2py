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
import plataforma
import scheduler_loop as sl
import sss_config
from repo_oracle.scheduler_fila import AgenteDuplicado

_Agent = collections.namedtuple("_Agent", (
    "agent_id", "ambientes_atendidos", "work_dir", "interpretadores", "usuarios_execucao",
    "exec_work_dir", "heartbeat_interval_s", "fence_timeout_s", "node_offline_timeout_s", "kill_grace_s",
    "misfire_policy", "misfire_tolerance_s", "cron_horizon_days", "fila_envelhecimento_min", "child_locale"))
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
        elif "versao_esquema" in sql:
            self._linha = (self.conn.versao,)

    def fetchone(self):
        return self._linha

    def close(self):
        pass


class _Conn(object):
    def __init__(self):
        self.versao = 1
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _Conexao(object):
    def __init__(self, ok=True):
        self.ok = ok
        self.conn = _Conn()

    def garantir(self):
        return self.ok

    def obter_conexao(self):
        return self.conn


class _Repo(object):
    """Fila em memoria: registra as chamadas do startup check."""

    def __init__(self):
        self.running = []
        self.chamadas = []
        self.duplicado = False
        self.divergentes = []
        self.ambientes = None
        self.registro = None

    def registrar_agente(self, conn, dados, processo_existe):
        self.registro = dados
        if self.duplicado:
            raise AgenteDuplicado("agent_id ativo em outro-host")
        return 42

    def conferir_config(self, conn, agente_id, criticos, offline):
        return self.divergentes

    def ambientes_ativos(self, conn, atendidos):
        return self.ambientes or (list(atendidos), [])

    def tickets_running_do_agente(self, conn, agente_id):
        return list(self.running)

    def devolver(self, conn, tid, agente_id):
        self.chamadas.append(("devolver", tid))
        return "DEVOLVIDO"

    def finalizar(self, conn, tid, agente_id, status, motivo, rc):
        self.chamadas.append(("finalizar", tid, status, motivo, rc))
        return True

    def obter_ticket(self, conn, tid):
        return {"id": tid, "log_offset_chars": 0}


class _RepoLog(object):
    def __init__(self):
        self.linhas = []

    def unidade_suplementar(self, conn):
        return 1

    def anexar(self, conn, tid, agente_id, offset, bloco):
        self.linhas.append((tid, bloco))
        return "GRAVADO"


def _vivo(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            conteudo = f.read()
    except OSError:
        return False
    return conteudo[conteudo.rindex(")") + 2:].split()[0] != "Z"


@unittest.skipIf(os.geteuid() == 0, "o agente nunca roda como root")
class _Base(unittest.TestCase):

    def setUp(self):
        self.raiz = os.path.realpath(tempfile.mkdtemp(prefix="sss_init_"))
        self.work = os.path.join(self.raiz, "work")
        self.logs = os.path.join(self.raiz, "logs")
        os.mkdir(self.work, 0o700)
        os.mkdir(self.logs, 0o750)
        self.repo = _Repo()
        self.repo_log = _RepoLog()
        self.conexao = _Conexao()
        self.popens = []
        self.agentes = []

    def tearDown(self):
        for ag in self.agentes:
            ag.liberar_recursos()
        for p in self.popens:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            p.wait()
        for atual, dirs, _arqs in os.walk(self.raiz):
            for d in dirs:
                os.chmod(os.path.join(atual, d), 0o700)
        shutil.rmtree(self.raiz, ignore_errors=True)

    def cfg(self, **agente):
        base = dict(agent_id="srv-t", ambientes_atendidos=("DEV",), work_dir=self.work,
                    interpretadores=(("SH", "/bin/sh"),), usuarios_execucao=(), exec_work_dir=None,
                    heartbeat_interval_s=10, fence_timeout_s=40, node_offline_timeout_s=120, kill_grace_s=1,
                    misfire_policy="RUN_ONCE", misfire_tolerance_s=300, cron_horizon_days=366,
                    fila_envelhecimento_min=30, child_locale="C.UTF-8")
        env = agente.pop("sss_env", "DEV")
        log_dir = agente.pop("log_dir", self.logs)
        base.update(agente)
        return _Cfg(_Agent(**base), _NS(log_dir), _App(env),
                    _Oracle("db:1521/x", 30000, "OWN_X", "pfx_"), None)

    def agente(self, cfg=None, plat=None, **kw):
        ag = sl.Agente(cfg=cfg or self.cfg(), segredos=object(), plat=plat, conexao=kw.pop("conexao", self.conexao),
                       repo=self.repo, repo_log=self.repo_log, hostname="host-t", pid=os.getpid(), **kw)
        self.agentes.append(ag)
        return ag

    def falha(self, codigo, ag=None):
        ag = ag or self.agente()
        with self.assertLogs("sss_scheduler", "CRITICAL") as logs, self.assertRaises(sl.FalhaInicializacao) as ctx:
            ag.inicializar()
        self.assertEqual(ctx.exception.codigo, codigo)
        self.assertEqual(ctx.exception.code, codigo, "codigo de saida do processo")
        return logs.output


class _Plat(object):
    """A plataforma real com funcoes trocadas por teste."""

    def __init__(self, **troca):
        self._troca = troca

    def __getattr__(self, nome):
        return self._troca[nome] if nome in self._troca else getattr(plataforma, nome)


class TestPassos(_Base):

    def test_subida_completa_em_dev(self):
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            ag = self.agente().inicializar()
        self.assertEqual(ag.agente_db_id, 42)
        self.assertEqual(ag.unidade_suplementar, 1)
        self.assertEqual(ag.ambientes_ativos, ["DEV"])
        self.assertIsNotNone(ag.ultimo_hb_ok)
        texto = "\n".join(logs.output)
        self.assertIn("fence_timeout_s=40 node_offline_timeout_s=120", texto)
        self.assertNotIn("SEM_EXIGENCIA_HASH", texto, "CR-011: sem hash")
        r = self.repo.registro
        self.assertEqual((r["codigo"], r["hostname"], r["versao"], r["plataforma"], r["interpretadores"]),
                         ("srv-t", "host-t", sss_config.VERSAO_SSS, plataforma.NOME, "SH"))
        self.assertEqual(r["config_criticos"], "hb=10;fence=40;offline=120;call=30;kill=1;misfire=RUN_ONCE;tol=300;"
                                               "horizonte=366;envelhecimento=30")
        self.assertTrue(os.path.exists(os.path.join(self.work, "sss-srv-t.lock")))

    def test_root_recusado(self):
        self.falha(sl.SAIDA_USUARIO, self.agente(plat=_Plat(usuario_privilegiado=lambda: True)))

    def test_codificacao_e_locale(self):
        with mock.patch.object(sss_config.sys, "getfilesystemencoding", return_value="ascii"):
            self.falha(sl.SAIDA_CONFIG)
        self.falha(sl.SAIDA_CONFIG, self.agente(cfg=self.cfg(child_locale="xx_YY.UTF-8")))

    def test_diretorios_e_interpretadores(self):
        self.falha(sl.SAIDA_DIRETORIOS, self.agente(cfg=self.cfg(log_dir="/usr/local/sss-logs")))
        self.falha(sl.SAIDA_DIRETORIOS, self.agente(cfg=self.cfg(work_dir=os.path.join(self.raiz, "nao"))))
        self.falha(sl.SAIDA_DIRETORIOS, self.agente(cfg=self.cfg(interpretadores=(("SH", "bin/sh"),))))
        self.falha(sl.SAIDA_DIRETORIOS, self.agente(cfg=self.cfg(interpretadores=())))

    def test_validar_execucao_fora_de_dev(self):
        cfg = self.cfg(sss_env="PROD", exec_work_dir=self.raiz)
        plat = _Plat(validar_execucao=lambda *a, **k: ["helper /opt/sss/bin/sss-helper nao encontrado"])
        saida = self.falha(sl.SAIDA_DIRETORIOS, self.agente(cfg=cfg, plat=plat))
        self.assertTrue(any("helper /opt/sss/bin/sss-helper nao encontrado" in x for x in saida))

    def test_instancia_unica_e_stop_antigo(self):
        stop = os.path.join(self.work, "sss-srv-t.stop")
        open(stop, "w").close()
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            self.agente().inicializar()
        self.assertFalse(os.path.exists(stop))
        self.assertTrue(any(".stop antigo" in x for x in logs.output))
        codigo = ("import sys\nsys.path.insert(0, %r)\nimport plataforma\n"
                  "try:\n    plataforma.travar_instancia(%r)\nexcept plataforma.InstanciaJaEmExecucao:\n"
                  "    sys.exit(7)\n" % (os.path.dirname(os.path.abspath(plataforma.__file__)) + "/..",
                                        os.path.join(self.work, "sss-srv-t.lock")))
        self.assertEqual(subprocess.call([sys.executable, "-c", codigo]), 7, "segunda instancia recusada")

    def test_segunda_instancia_no_mesmo_processo(self):
        self.agente().inicializar()
        self.falha(sl.SAIDA_INSTANCIA)

    def test_banco(self):
        self.falha(sl.SAIDA_BANCO, self.agente(conexao=_Conexao(ok=False)))
        conexao = _Conexao()
        conexao.conn.versao = 2
        with mock.patch.object(sl.db_conn, "_registrar_critico"):
            self.falha(sl.SAIDA_BANCO, self.agente(conexao=conexao))

    def test_registro(self):
        self.repo.duplicado = True
        self.falha(sl.SAIDA_REGISTRO)
        self.repo.duplicado = False
        self.repo.divergentes = [("srv-02", "hb=20;fence=40")]
        saida = self.falha(sl.SAIDA_REGISTRO)
        self.assertTrue(any("srv-02" in x and "hb=20" in x for x in saida), "as duas configuracoes no log")

    def test_ambientes(self):
        self.repo.ambientes = ([], ["DEV"])
        self.falha(sl.SAIDA_AMBIENTES)
        self.repo.ambientes = ([], [])
        with self.assertLogs("sss_scheduler", "WARNING") as logs:
            ag = self.agente().inicializar()
        self.assertEqual(ag.ambientes_ativos, [])
        self.assertTrue(any("DEV inativo" in x for x in logs.output))

    def test_thread_unica(self):
        parar = threading.Event()
        t = threading.Thread(target=parar.wait, name="thread-intrusa")
        t.start()
        try:
            saida = self.falha(sl.SAIDA_THREADS)
        finally:
            parar.set()
            t.join()
        self.assertTrue(any("thread-intrusa" in x for x in saida))


class TestStartupCheck(_Base):

    def _pasta(self, tid, **estados):
        pasta = executor.preparar_diretorio(self.work, tid)
        for nome, dados in estados.items():
            plataforma.gravar_estado(os.path.join(pasta, "." + nome), dados)
        return pasta

    def _grupo(self, comando="sleep 300 & sleep 300"):
        p = subprocess.Popen(["/bin/sh", "-c", comando], start_new_session=True)
        self.popens.append(p)
        time.sleep(0.2)
        return p

    def _subir(self, **kw):
        with self.assertLogs("sss_scheduler", "INFO") as logs:
            ag = self.agente(**kw).inicializar()
        return ag, "\n".join(logs.output)

    def test_grupo_vivo_e_encerrado_e_ticket_orfao(self):
        p = self._grupo()
        pasta = self._pasta(5, sss_proc={"ticket_id": 5, "pid": p.pid, "pgid": p.pid, "usuario_execucao": None,
                                         "process_start": plataforma.identidade_processo(p.pid)})
        self.repo.running = [{"id": 5, "process_id": p.pid, "process_start": None, "cancel_requested": "N"}]
        ag, _logs = self._subir()
        self.assertIn(("finalizar", 5, "FAILED", "ORPHAN_PROCESS", -2), self.repo.chamadas)
        self.assertTrue(self.repo_log.linhas[0][1].startswith("[SSS] ORPHAN_PROCESS: "))
        self.assertIn(5, ag.encerrando, "o laco termina o encerramento e so entao limpa")
        self.assertTrue(os.path.isdir(pasta))
        ex = ag.encerrando[5]
        limite = time.monotonic() + 5
        while not executor.avancar_encerramento(ex, time.monotonic() + 10) and time.monotonic() < limite:
            time.sleep(0.05)
        self.assertEqual(p.wait(5), -signal.SIGTERM)

    def test_ticket_ja_finalizado_por_outro_no_com_filho_vivo(self):
        # NODE_OFFLINE no banco com o filho vivo: o disco manda; o grupo e encerrado e nada e finalizado.
        p = self._grupo()
        self._pasta(6, sss_proc={"ticket_id": 6, "pid": p.pid, "pgid": p.pid, "usuario_execucao": None,
                                 "process_start": plataforma.identidade_processo(p.pid)})
        ag, _logs = self._subir()
        self.assertEqual(self.repo.chamadas, [])
        self.assertIn(6, ag.encerrando)
        self.assertEqual(ag.encerrando[6].fase, executor.FASE_TERM)

    def test_pid_reciclado_nao_recebe_sinal(self):
        p = self._grupo("sleep 300")
        pasta = self._pasta(7, sss_proc={"ticket_id": 7, "pid": p.pid, "pgid": p.pid, "usuario_execucao": None,
                                         "process_start": plataforma.identidade_processo(p.pid) + 1})
        self.repo.running = [{"id": 7, "process_id": p.pid, "process_start": None, "cancel_requested": "N"}]
        ag, _logs = self._subir()
        self.assertTrue(_vivo(p.pid), "PID reciclado: o processo de agora nao e o do ticket")
        self.assertIn(("finalizar", 7, "FAILED", "ORPHAN_PROCESS", -2), self.repo.chamadas)
        self.assertFalse(os.path.exists(pasta))

    def test_resultado_local_prevalece(self):
        pasta = self._pasta(8, sss_proc={"ticket_id": 8, "pid": 2 ** 31 - 2, "pgid": 2 ** 31 - 2,
                                         "usuario_execucao": None, "process_start": 1},
                            sss_result={"ticket_id": 8, "status": "SUCCESS", "status_motivo": "EXIT_OK",
                                        "return_code": 0})
        self.repo.running = [{"id": 8, "process_id": 1, "process_start": 1, "cancel_requested": "N"}]
        self._subir()
        self.assertIn(("finalizar", 8, "SUCCESS", "EXIT_OK", 0), self.repo.chamadas)
        self.assertFalse(os.path.exists(pasta))

    def test_sem_identidade_preserva_a_pasta(self):
        p = self._grupo("sleep 300")
        pasta = self._pasta(9, sss_proc={"ticket_id": 9, "pid": p.pid, "pgid": p.pid, "usuario_execucao": None,
                                         "process_start": None})
        self.repo.running = [{"id": 9, "process_id": p.pid, "process_start": None, "cancel_requested": "N"}]
        plat = _Plat(reabrir_grupo=lambda estado: plataforma.Processo(p.pid, None, sem_identidade=True))
        ag, logs = self._subir(plat=plat)
        self.assertIn("ORFAO_SEM_IDENTIDADE", logs)
        self.assertTrue(_vivo(p.pid), "sem identidade nunca recebe sinal")
        self.assertIn(9, ag.preservadas)
        self.assertTrue(os.path.isdir(pasta), "CR-008, R-26: o unico rastro do processo fica")
        self.assertIn(("finalizar", 9, "FAILED", "ORPHAN_PROCESS", -2), self.repo.chamadas)

    def test_talvez_iniciado_nunca_volta_a_fila(self):
        pasta = self._pasta(10, sss_spawn={"ticket_id": 10, "usuario_execucao": None})
        neto = subprocess.Popen(["sleep", "300"], cwd=os.path.join(pasta, "tmp"), start_new_session=True)
        self.popens.append(neto)
        self.repo.running = [{"id": 10, "process_id": None, "process_start": None, "cancel_requested": "N"}]
        _ag, logs = self._subir()
        self.assertIn("TALVEZ_INICIADO", logs)
        self.assertNotIn(("devolver", 10), self.repo.chamadas)
        self.assertIn(("finalizar", 10, "FAILED", "ORPHAN_PROCESS", -2), self.repo.chamadas)
        self.assertEqual(neto.wait(5), -signal.SIGTERM, "encerrado pelo diretorio atual na pasta do ticket")
        self.assertFalse(os.path.exists(pasta))

    def test_talvez_iniciado_nao_suportado_preserva(self):
        pasta = self._pasta(11, sss_spawn={"ticket_id": 11, "usuario_execucao": None})
        self.repo.running = [{"id": 11, "process_id": None, "process_start": None, "cancel_requested": "N"}]
        ag, logs = self._subir(plat=_Plat(encerrar_ticket=lambda *a: "NAO_SUPORTADO"))
        self.assertIn("sem meio de encerrar", logs)
        self.assertIn(11, ag.preservadas)
        self.assertTrue(os.path.isdir(pasta))
        self.assertIn(("finalizar", 11, "FAILED", "ORPHAN_PROCESS", -2), self.repo.chamadas)

    def test_running_sem_pasta(self):
        self.repo.running = [{"id": 12, "process_id": None, "process_start": None, "cancel_requested": "N"},
                             {"id": 13, "process_id": 999, "process_start": 1, "cancel_requested": "N"}]
        self._subir()
        self.assertIn(("devolver", 12), self.repo.chamadas)
        self.assertIn(("finalizar", 13, "FAILED", "ORPHAN_PROCESS", -2), self.repo.chamadas)

    def test_pasta_vazia_e_removida_e_link_ignorado(self):
        pasta = self._pasta(14)
        fora = os.path.join(self.raiz, "fora")
        os.mkdir(fora)
        os.symlink(fora, os.path.join(self.work, "ticket_15"))
        self._subir()
        self.assertFalse(os.path.exists(pasta))
        self.assertTrue(os.path.isdir(fora), "link simbolico nunca seguido")
        self.assertEqual(self.repo.chamadas, [])

    def test_falha_de_banco_no_startup_check(self):
        def _erro(*a):
            raise RuntimeError("ORA-03113: end-of-file on communication channel")
        self.repo.tickets_running_do_agente = _erro
        self.falha(sl.SAIDA_STARTUP)


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestSubidaOracle(_Base):
    """Subida real no owner do config.ini, com agent_id de teste e pastas temporarias; registro removido no fim."""

    def setUp(self):
        _Base.setUp(self)
        from _oracle_test_support import preparar_schema_descartavel
        self.cfg_real = preparar_schema_descartavel("agente")
        self.codigo = "tst-f83b-%d" % (int(time.time() * 1000) % 100000000)
        self.addCleanup(self._limpar_registro)

    def _limpar_registro(self):
        import db_conn
        import sql_ident
        seg = sss_config.carregar_segredos(self.cfg_real.secrets.secrets_file, cfg=self.cfg_real, papel="agente")
        conn = db_conn.conectar(self.cfg_real, seg, "agente")
        try:
            o, p = self.cfg_real.oracle.owner.strip(), self.cfg_real.oracle.table_prefix.strip()
            agt = sql_ident.qualificar(o, p + "agentes", prefixo=p)
            aud = sql_ident.qualificar(o, p + "auditoria", prefixo=p)
            cur = conn.cursor()
            cur.execute("SELECT id FROM " + agt + " WHERE codigo = :c", c=self.codigo)
            for (aid,) in cur.fetchall():
                cur.execute("DELETE FROM " + aud + " WHERE entidade = 'tbsss_agentes' AND entidade_id = :id", id=aid)
                cur.execute("DELETE FROM " + agt + " WHERE id = :id", id=aid)
            conn.commit()
        finally:
            conn.close()

    def test_subida_real_e_parada(self):
        import db_conn
        from repo_oracle.scheduler_fila import RepoSchedulerFila
        cfg = self.cfg_real
        seg = sss_config.carregar_segredos(cfg.secrets.secrets_file, cfg=cfg, papel="agente")
        conn = db_conn.conectar(cfg, seg, "agente")
        try:
            import ddl_builder
            ativos, _ = RepoSchedulerFila.da_config(cfg).ambientes_ativos(
                conn, [a[0] for a in ddl_builder.CATALOGO_AMBIENTES_PADRAO])
        finally:
            conn.close()
        self.assertTrue(ativos, "o seed precisa de um ambiente ativo")
        agente = cfg.agent._replace(agent_id=self.codigo, ambientes_atendidos=tuple(ativos[:1]), work_dir=self.work,
                                    interpretadores=(("SH", "/bin/sh"),))
        cfg = cfg._replace(agent=agente, logging=cfg.logging._replace(log_dir=self.logs))
        ag = sl.Agente(cfg=cfg, segredos=seg, hostname="host-tst", pid=os.getpid())
        self.agentes.append(ag)
        with self.assertLogs("sss_scheduler", "INFO"):
            ag.inicializar()
        self.assertIsInstance(ag.agente_db_id, int)
        self.assertIn(ag.unidade_suplementar, (1, 2))
        self.assertEqual(ag.ambientes_ativos, list(ativos[:1]))
        # Segunda subida do mesmo agent_id, de outro host, enquanto o primeiro esta ativo: recusada.
        outro = sl.Agente(cfg=cfg._replace(agent=agente._replace(work_dir=self.raiz)), segredos=seg,
                          hostname="outro-host", pid=os.getpid())
        self.agentes.append(outro)
        os.makedirs(os.path.join(self.raiz, "logs2"), exist_ok=True)
        self.falha(sl.SAIDA_REGISTRO, outro)
        self.assertTrue(ag.repo.encerrar_agente(ag.conexao.obter_conexao(), self.codigo, "host-tst", os.getpid(),
                                                "TERMINATE"))


class TestFonte(unittest.TestCase):

    def test_sem_primitivas_de_so_nem_gluon(self):
        with open(sl.__file__, encoding="utf-8") as f:
            fonte = f.read()
        for proibido in ("os.killpg", "os.kill(", "time.sleep", "subprocess", "sys.platform", "gluon", "/proc/"):
            self.assertFalse(proibido in fonte, proibido)


if __name__ == "__main__":
    unittest.main()
