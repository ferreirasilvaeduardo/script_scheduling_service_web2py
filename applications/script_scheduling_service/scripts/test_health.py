# -*- coding: utf-8 -*-
"""Testes do scripts/health.py e do repo_oracle/health.py (README §13; F9.1b; CR-007 R-18; CR-008 E3, R-15, R-16).

Com repositorio simulado: cada verificacao no limiar e fora dele e o codigo Nagios agregado (o pior vence);
segredos pelo papel monitor; UNKNOWN em configuracao, conexao e erro de banco; o SQL do RepoHealth (indices da
fila e do RUNNING, sem LOB, interpretador do cadastro). Com SSS_TEST_ORACLE=1: as consultas rodam no Oracle real
pela conta do owner (so leitura; o GFPR nao tem a conta sss_monitor) e o EXPLAIN PLAN nao varre tickets nem
auditoria.
"""
import _testenv  # noqa: F401

import datetime
import io
import os
import shutil
import tempfile
import types
import unittest
from unittest import mock

import health as saude_cli  # scripts/health.py (o repositorio e repo_oracle.health)
import sql_ident
import sss_config
from repo_oracle import health as saude_sql

NOW = datetime.datetime(2026, 10, 21, 10, 0, 0)
NS = types.SimpleNamespace


def _cfg():
    agente = NS(heartbeat_interval_s=10, fence_timeout_s=90, node_offline_timeout_s=180, kill_grace_s=5,
                misfire_policy="RUN_ONCE", misfire_tolerance_s=300, cron_horizon_days=1461,
                queue_aging_min=60)
    return NS(oracle=NS(owner="openrisow", table_prefix="tbsss_", call_timeout_ms=30000), agent=agente,
              secrets=NS(secrets_file="/x/secrets.cfg"))


CRITICAL = sss_config.critical_config(_cfg())


def _agent(codigo, idade_s=5, status="ACTIVE", ambientes="PRODUCAO", interpreters="SH,PYTHON3", cfg=CRITICAL):
    hb = None if idade_s is None else NOW - datetime.timedelta(seconds=idade_s)
    return {"code": codigo, "status": status, "heartbeat_at": hb, "environments": ambientes,
            "interpreters": interpreters, "critical_config": cfg}


class _Repo(object):
    """RepoHealth simulado: tudo saudavel por padrao."""

    def __init__(self, **kw):
        self.d = dict(version=sql_ident.SCHEMA_VERSION, agents=[_agent("srv-a")], environments=["PRODUCAO"],
                      fila=[], vencida=(0, None), sem_pid=[], purge=NOW - datetime.timedelta(hours=20))
        self.d.update(kw)
        self.calls = []

    def schema_version(self, conn):
        return self.d["version"]

    def agents(self, conn):
        return self.d["agents"]

    def active_environments(self, conn):
        return self.d["environments"]

    def queue_by_pair(self, conn, agora):
        return self.d["fila"]

    def overdue_queue(self, conn, agora):
        return self.d["vencida"]

    def running_without_pid(self, conn, agora, minutos):
        self.calls.append(("sem_pid", minutos))
        return self.d["sem_pid"]

    def last_purge(self, conn, agora, dias):
        self.calls.append(("purge", dias))
        return self.d["purge"]


class _ConnNow(object):
    """So o SELECT SYSDATE do agora_banco()."""

    def __init__(self):
        self.nows = 0
        self.closed = False

    def cursor(self):
        conn = self

        class _C(object):
            def execute(self, sql, binds=None):
                assert sql == "SELECT SYSDATE FROM DUAL", sql
                conn.nows += 1

            def fetchone(self):
                return (NOW,)

            def close(self):
                pass
        return _C()

    def close(self):
        self.closed = True


def _args(argv=()):
    return saude_cli._arguments(list(argv))


class TestChecks(unittest.TestCase):

    def _run_loop(self, argv=(), **kw):
        repo = _Repo(**kw)
        conn = _ConnNow()
        v = saude_cli.Check(_cfg(), conn, _args(argv), repo=repo)
        codigo = v.run()
        self.assertEqual(conn.nows, 1, "um unico agora_banco()")
        return codigo, v.output(codigo), repo

    def test_tudo_saudavel(self):
        codigo, texto, repo = self._run_loop()
        self.assertEqual(codigo, saude_cli.OK)
        self.assertEqual(texto, "SSS OK - 0 problemas | healthy_agents=1 overdue_queue=0;500;5000"
                                " max_wait_min=0;30;120\n")
        self.assertIn(("sem_pid", 2), repo.calls)
        self.assertIn(("purge", 2), repo.calls)

    def test_heartbeat_por_faixa(self):
        self.assertEqual(self._run_loop(agents=[_agent("srv-a", 90)])[0], saude_cli.OK, "DELAYED ainda atende")
        codigo, texto, _r = self._run_loop(agents=[_agent("srv-a", 91), _agent("srv-b")])
        self.assertEqual(codigo, saude_cli.WARNING)
        self.assertIn("WARNING: agente srv-a em risco: heartbeat ha 91 s", texto)
        codigo, texto, _r = self._run_loop(agents=[_agent("srv-a", 181), _agent("srv-b")])
        self.assertEqual(codigo, saude_cli.CRITICAL)
        self.assertIn("CRITICAL: agente srv-a ATIVO sem heartbeat ha 181 s", texto)
        codigo, texto, _r = self._run_loop(agents=[_agent("srv-a", None), _agent("srv-b")])
        self.assertIn("agente srv-a ATIVO sem heartbeat ha -", texto)
        self.assertEqual(self._run_loop(agents=[_agent("srv-a", None, status="STOPPED"), _agent("srv-b")])[0],
                         saude_cli.OK, "agente PARADO nao e problema")

    def test_ambiente_sem_agente_saudavel(self):
        codigo, texto, _r = self._run_loop(environments=["PRODUCAO", "HOMOLOGACAO"],
                                        agents=[_agent("srv-a"), _agent("srv-b", 120, ambientes="HOMOLOGACAO")])
        self.assertEqual(codigo, saude_cli.CRITICAL)
        self.assertIn("CRITICAL: ambiente HOMOLOGACAO ativo sem nenhum agente saudavel", texto)

    def test_fila_sem_atendente_pelo_interpretador_do_cadastro(self):
        antigo = datetime.datetime(2026, 10, 21, 9, 50, 0, 7)
        fila = [("PRODUCAO", "SH", 3, antigo), ("PRODUCAO", "BASH", 2, antigo)]
        codigo, texto, _r = self._run_loop(fila=fila)
        self.assertEqual(codigo, saude_cli.CRITICAL)
        self.assertIn("CRITICAL: fila sem atendente: 2 tickets de PRODUCAO/BASH, o mais antigo desde 2026-10-21 09:50:00",
                      texto)
        self.assertNotIn("PRODUCAO/SH", texto, "SH e atendido pelo srv-a")

    def test_fila_vencida_por_quantidade_e_espera(self):
        um_min = NOW - datetime.timedelta(minutes=1)
        self.assertEqual(self._run_loop(vencida=(499, um_min))[0], saude_cli.OK)
        self.assertEqual(self._run_loop(vencida=(500, um_min))[0], saude_cli.WARNING)
        codigo, texto, _r = self._run_loop(vencida=(5000, um_min))
        self.assertEqual(codigo, saude_cli.CRITICAL)
        self.assertIn("overdue_queue=5000;500;5000", texto)
        self.assertEqual(self._run_loop(vencida=(1, NOW - datetime.timedelta(minutes=30)))[0], saude_cli.WARNING)
        self.assertEqual(self._run_loop(vencida=(1, NOW - datetime.timedelta(minutes=120)))[0], saude_cli.CRITICAL)
        self.assertEqual(self._run_loop(["--queue-warn", "10"], vencida=(10, um_min))[0], saude_cli.WARNING)

    def test_rodando_sem_pid(self):
        sem_pid = [{"id": 77, "script_id": 3, "environment": "PRODUCAO", "agent_id": "srv-a",
                    "started_at": datetime.datetime(2026, 10, 21, 9, 55)}]
        codigo, texto, repo = self._run_loop(["--no-pid-min", "5"], sem_pid=sem_pid)
        self.assertEqual(codigo, saude_cli.WARNING)
        self.assertIn("WARNING: ticket 77 RUNNING sem PID no agente srv-a desde 2026-10-21 09:55:00", texto)
        self.assertIn(("sem_pid", 5), repo.calls)

    def test_configuracao_divergente(self):
        outro = CRITICAL.replace("kill=5", "kill=10")
        codigo, texto, _r = self._run_loop(agents=[_agent("srv-a"), _agent("srv-b", cfg=outro),
                                                 _agent("srv-c", status="STOPPED", cfg=outro)])
        self.assertEqual(codigo, saude_cli.WARNING)
        self.assertIn("agente srv-b com configuracao divergente", texto)
        self.assertNotIn("srv-c", texto, "so agentes ativos")

    def test_purge_ausente(self):
        codigo, texto, repo = self._run_loop(["--purge-days", "3"], purge=None)
        self.assertEqual(codigo, saude_cli.WARNING)
        self.assertIn("nenhum PURGE auditado nos ultimos 3 dias", texto)
        self.assertIn(("purge", 3), repo.calls)

    def test_versao_do_esquema(self):
        codigo, texto, _r = self._run_loop(version=sql_ident.SCHEMA_VERSION - 1)
        self.assertEqual(codigo, saude_cli.CRITICAL)
        self.assertIn("versao do esquema %d" % (sql_ident.SCHEMA_VERSION - 1), texto)

    def test_pior_nivel_vence_e_criticos_primeiro(self):
        codigo, texto, _r = self._run_loop(purge=None, version=None)
        self.assertEqual(codigo, saude_cli.CRITICAL)
        linhas = texto.splitlines()
        self.assertTrue(linhas[0].startswith("SSS CRITICAL - 2 problemas | "))
        self.assertTrue(linhas[1].startswith("CRITICAL: versao do esquema None"))
        self.assertTrue(linhas[2].startswith("WARNING: nenhum PURGE"))


class TestMain(unittest.TestCase):

    def _main(self, argv=(), conectar=None, cfg_erro=False, seg_erro=False):
        saida = io.StringIO()
        obter = mock.Mock(side_effect=sss_config.ConfigError(reason="faltou dsn") if cfg_erro else None,
                          return_value=_cfg())
        carregar = mock.Mock(side_effect=sss_config.ConfigError(reason="sem [monitor]") if seg_erro else None,
                             return_value=object())
        with mock.patch.object(saude_cli.sss_config, "get_config", obter), \
                mock.patch.object(saude_cli.sss_config, "load_secrets", carregar), \
                mock.patch.object(saude_cli.saude_sql.RepoHealth, "from_config", return_value=_Repo()):
            codigo = saude_cli.main(list(argv), conectar=conectar, saida=saida)
        self.load = carregar
        return codigo, saida.getvalue()

    def test_ok_com_papel_monitor(self):
        conn = _ConnNow()
        papeis = []

        def conectar(cfg, segredos):
            papeis.append(segredos)
            return conn
        codigo, texto = self._main(conectar=conectar)
        self.assertEqual(codigo, 0)
        self.assertTrue(texto.startswith("SSS OK - 0 problemas"))
        self.assertEqual(self.load.call_args[1]["papel"], "monitor")
        self.assertTrue(conn.closed)

    def test_unknown(self):
        self.assertEqual(self._main(cfg_erro=True), (3, "SSS UNKNOWN - configuracao invalida: faltou dsn\n"))
        codigo, texto = self._main(seg_erro=True)
        self.assertEqual(codigo, 3)
        self.assertIn("sem [monitor]", texto)
        codigo, texto = self._main(conectar=mock.Mock(side_effect=RuntimeError("ORA-12541: TNS:no listener")))
        self.assertEqual(codigo, 3)
        self.assertIn("falha ao conectar no Oracle", texto)
        conn = _ConnNow()
        with mock.patch.object(_Repo, "agents", side_effect=RuntimeError("ORA-03113: end-of-file")):
            codigo, texto = self._main(conectar=lambda c, s: conn)
        self.assertEqual(codigo, 3)
        self.assertIn("falha de banco", texto)
        self.assertTrue(conn.closed)

    def test_segredos_do_monitor_sem_os_outros_papeis(self):
        # Integracao com o sss_config real: o arquivo do servidor do agente, com [oracle], [purge] e [environment:*].
        pasta = tempfile.mkdtemp(prefix="sss_test_saude_")
        self.addCleanup(shutil.rmtree, pasta, True)
        caminho = os.path.join(pasta, "secrets.cfg")
        with open(caminho, "w") as f:
            f.write("[oracle]\npassword = senha-agt-1\n[purge]\npassword = senha-prg-1\n"
                    "[environment:PRODUCAO]\nuser = app\npassword = senha-amb-1\n"
                    "[monitor]\nuser = sss_monitor\npassword = senha-mon-1\n")
        os.chmod(caminho, 0o600)
        registrados = []
        with mock.patch("masking.register_secret", side_effect=registrados.append):
            seg = sss_config.load_secrets(caminho, sss_env="PROD", papel="monitor")
        self.assertEqual((seg.monitor_user, seg.oracle_password, seg.purge_password, seg.environments),
                         ("sss_monitor", None, None, {}))
        self.assertEqual(registrados, ["senha-mon-1"])


class TestSqlRepoHealth(unittest.TestCase):

    def setUp(self):
        self.repo = saude_sql.RepoHealth("openrisow", "tbsss_")

    def test_indices_sem_lob_e_interpretador_do_cadastro(self):
        fila = self.repo.sql("queue")
        self.assertIn("JOIN openrisow.tbsss_scripts s ON s.id = g.script_id", fila)
        self.assertIn("status = 'PENDING' AND GREATEST(scheduled_at, created_at) <= :agora", fila)
        self.assertIn("status = 'PENDING' AND GREATEST(scheduled_at, created_at) <= :agora",
                      self.repo.sql("overdue_queue"))
        self.assertIn("(CASE WHEN status = 'RUNNING' THEN agent_id END) >= CHR(1)", self.repo.sql("running_no_pid"))
        self.assertIn("actor = 'SYSTEM:purge' AND action = 'PURGE'", self.repo.sql("purge"))
        for nome in ("agents", "environments", "queue", "overdue_queue", "running_no_pid", "purge", "version"):
            sql = self.repo.sql(nome)
            self.assertTrue(sql.startswith("SELECT "), nome)
            self.assertNotIn("submitted_params", sql)
            self.assertNotIn("log_output", sql)
            self.assertNotIn("*", sql.replace("COUNT(*)", ""), nome)

    def test_tela_de_agentes_usa_o_mesmo_sql(self):
        import repo_oracle.agents as agentes_oracle
        self.assertIs(agentes_oracle._SQL_QUEUE, saude_sql.SQL_QUEUE)
        self.assertIs(agentes_oracle._SQL_RUNNING_NO_PID, saude_sql.SQL_RUNNING_NO_PID)

    def test_pares_atendidos_ignoram_em_risco_e_parados(self):
        lim = saude_cli.agents_service.Thresholds(10, 90, 180)
        agentes = [_agent("a", 5, interpreters="SH"), _agent("b", 91, interpreters="BASH"),
                   _agent("c", 5, status="STOPPED", interpreters="PYTHON3")]
        self.assertEqual(saude_sql.served_pairs(agentes, NOW, lim), {("PRODUCAO", "SH")})


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestHealthOracle(unittest.TestCase):
    """As consultas do RepoHealth no Oracle real, so leitura, pela conta do owner (decisao 1a do F9.1)."""

    @classmethod
    def setUpClass(cls):
        from _oracle_test_support import prepare_disposable_schema
        import db_conn
        cls.cfg = prepare_disposable_schema("agent")
        segredos = sss_config.load_secrets(cls.cfg.secrets.secrets_file, cfg=cls.cfg, papel="agent")
        cls.conn = db_conn.connect(cls.cfg, segredos, papel="agent")
        cls.repo = saude_sql.RepoHealth.from_config(cls.cfg)

    @classmethod
    def tearDownClass(cls):
        cls.conn.rollback()
        cls.conn.close()

    def test_consultas_e_verificacao_completa(self):
        import db_conn
        agora = db_conn.db_now(self.conn)
        self.assertEqual(self.repo.schema_version(self.conn), sql_ident.SCHEMA_VERSION)
        self.assertIsInstance(self.repo.agents(self.conn), list)
        self.assertIsInstance(self.repo.active_environments(self.conn), list)
        qtd, _antigo = self.repo.overdue_queue(self.conn, agora)
        self.assertEqual(qtd, sum(int(r[2]) for r in self.repo.queue_by_pair(self.conn, agora)))
        self.repo.running_without_pid(self.conn, agora, 2)
        self.repo.last_purge(self.conn, agora, 2)
        v = saude_cli.Check(self.cfg, self.conn, _args(), repo=self.repo)
        codigo = v.run()
        self.assertIn(codigo, (0, 1, 2))
        print("\n[F9.1b] saude no GFPR: %s" % v.output(codigo).splitlines()[0])

    def test_explain_sem_varredura_de_tickets_e_auditoria(self):
        import db_conn
        agora = db_conn.db_now(self.conn)
        binds = {"queue": {"agora": agora}, "overdue_queue": {"agora": agora}, "running_no_pid": {"limite": agora},
                 "purge": {"limite": agora}}
        for nome, valores in binds.items():
            cur = self.conn.cursor()
            stmt = "SSS_F91B_%s" % nome.upper()
            cur.execute("DELETE FROM plan_table WHERE statement_id = :s", {"s": stmt})
            db_conn.set_input_types(cur, **dict((k, db_conn.TIPO_DATE) for k in valores))
            cur.execute("EXPLAIN PLAN SET STATEMENT_ID = '%s' FOR %s" % (stmt, self.repo.sql(nome)), valores)
            cur.execute("SELECT operation, options, object_name FROM plan_table WHERE statement_id = :s",
                        {"s": stmt})
            plano = cur.fetchall()
            cur.execute("DELETE FROM plan_table WHERE statement_id = :s", {"s": stmt})
            self.conn.commit()
            varreduras = [o for op, opt, o in plano if op == "TABLE ACCESS" and opt == "FULL"
                          and (o or "").upper() in ("TBSSS_TICKETS", "TBSSS_AUDIT")]
            self.assertEqual(varreduras, [], "%s: %s" % (nome, plano))
            print("\n[F9.1b] EXPLAIN %s: %s" % (nome, ", ".join("%s %s %s" % (op, opt or "", o or "")
                                                               for op, opt, o in plano)))


if __name__ == "__main__":
    unittest.main()
