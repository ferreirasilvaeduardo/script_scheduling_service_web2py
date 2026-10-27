# -*- coding: utf-8 -*-
"""Testes do scripts/health.py e do repo_oracle/health.py (README §13; F9.1b; CR-007 R-18; CR-008 E3, R-15, R-16).

Com repositorio simulado: cada verificacao no limiar e fora dele e o codigo Nagios agregado (o pior vence);
segredos pelo papel monitor; UNKNOWN em configuracao, conexao e erro de banco; o SQL do RepoHealth (indices da
fila e do RUNNING, sem LOB, interpretador do cadastro). Com SSS_TEST_ORACLE=1: as consultas rodam no Oracle real
pela conta do owner (so leitura; o GFPR nao tem a conta sss_monitor) e o EXPLAIN PLAN nao varre tickets nem
auditoria.
"""
from tests.support import _testenv  # noqa: F401

import datetime
import io
import os
import shutil
import tempfile
import types
import unittest
from unittest import mock

from sss.cli import health as saude_cli  # scripts/health.py (o repositorio e repo_oracle.health)
from sss.core import sql_ident
from sss.config import sss_config
from sss.persistence.oracle import health as saude_sql

NOW = datetime.datetime(2026, 10, 21, 10, 0, 0)
NS = types.SimpleNamespace


def _cfg():
    agent = NS(heartbeat_interval_s=10, fence_timeout_s=90, node_offline_timeout_s=180, kill_grace_s=5,
                misfire_policy="RUN_ONCE", misfire_tolerance_s=300, cron_horizon_days=1461,
                queue_aging_min=60)
    return NS(oracle=NS(owner="openrisow", table_prefix="tbsss_", call_timeout_ms=30000), agent=agent,
              secrets=NS(secrets_file="/x/secrets.cfg"))


CRITICAL = sss_config.critical_config(_cfg())


def _agent(code, age_s=5, status="ACTIVE", environments="PRODUCAO", cfg=CRITICAL):
    hb = None if age_s is None else NOW - datetime.timedelta(seconds=age_s)
    return {"code": code, "status": status, "heartbeat_at": hb, "environments": environments,
            "critical_config": cfg}


class _Repo(object):
    """RepoHealth simulado: tudo saudavel por padrao."""

    def __init__(self, **kw):
        self.d = dict(version=sql_ident.SCHEMA_VERSION, agents=[_agent("srv-a")], environments=["PRODUCAO"],
                      fila=[], vencida=(0, None), sem_pid=[])
        self.d.update(kw)
        self.calls = []

    def schema_version(self, conn):
        return self.d["version"]

    def agents(self, conn):
        return self.d["agents"]

    def active_environments(self, conn):
        return self.d["environments"]

    def queue_by_pair(self, conn, now):
        return self.d["fila"]

    def overdue_queue(self, conn, now):
        return self.d["vencida"]

    def running_without_pid(self, conn, now, minutes):
        self.calls.append(("sem_pid", minutes))
        return self.d["sem_pid"]


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


# CR-029: sem config padrao; os testes passam um --config qualquer (o get_config e substituido).
_CONFIG_ARGS = ["--config", "config-de-teste.ini"]


def _args(argv=()):
    return saude_cli._arguments(_CONFIG_ARGS + list(argv))


class TestChecks(unittest.TestCase):

    def _run_loop(self, argv=(), **kw):
        repo = _Repo(**kw)
        conn = _ConnNow()
        v = saude_cli.Check(_cfg(), conn, _args(argv), repo=repo)
        code = v.run()
        self.assertEqual(conn.nows, 1, "um unico agora_banco()")
        return code, v.output(code), repo

    def test_tudo_saudavel(self):
        code, text, repo = self._run_loop()
        self.assertEqual(code, saude_cli.OK)
        self.assertEqual(text, "SSS OK - 0 problemas | healthy_agents=1 overdue_queue=0;500;5000"
                                " max_wait_min=0;30;120\n")
        self.assertIn(("sem_pid", 2), repo.calls)

    def test_heartbeat_por_faixa(self):
        self.assertEqual(self._run_loop(agents=[_agent("srv-a", 90)])[0], saude_cli.OK, "DELAYED ainda atende")
        code, text, _r = self._run_loop(agents=[_agent("srv-a", 91), _agent("srv-b")])
        self.assertEqual(code, saude_cli.WARNING)
        self.assertIn("WARNING: agente srv-a em risco: heartbeat ha 91 s", text)
        code, text, _r = self._run_loop(agents=[_agent("srv-a", 181), _agent("srv-b")])
        self.assertEqual(code, saude_cli.CRITICAL)
        self.assertIn("CRITICAL: agente srv-a ATIVO sem heartbeat ha 181 s", text)
        code, text, _r = self._run_loop(agents=[_agent("srv-a", None), _agent("srv-b")])
        self.assertIn("agente srv-a ATIVO sem heartbeat ha -", text)
        self.assertEqual(self._run_loop(agents=[_agent("srv-a", None, status="STOPPED"), _agent("srv-b")])[0],
                         saude_cli.OK, "agente PARADO nao e problema")

    def test_ambiente_sem_agente_saudavel(self):
        code, text, _r = self._run_loop(environments=["PRODUCAO", "HOMOLOGACAO"],
                                        agents=[_agent("srv-a"), _agent("srv-b", 120, environments="HOMOLOGACAO")])
        self.assertEqual(code, saude_cli.CRITICAL)
        self.assertIn("CRITICAL: ambiente HOMOLOGACAO ativo sem nenhum agente saudavel", text)

    def test_fila_sem_atendente_pelo_ambiente(self):
        # CR-026: o agente atende qualquer interpretador; a linha mostra o do cadastro.
        old = datetime.datetime(2026, 10, 21, 9, 50, 0, 7)
        queue_value = [("PRODUCAO", "sh", 3, old), ("DESENV", "bash", 2, old)]
        code, text, _r = self._run_loop(fila=queue_value)
        self.assertEqual(code, saude_cli.CRITICAL)
        self.assertIn("CRITICAL: fila sem atendente: 2 tickets de DESENV/bash, o mais antigo desde 2026-10-21 09:50:00",
                      text)
        self.assertNotIn("PRODUCAO/sh", text, "PRODUCAO e atendido pelo srv-a")

    def test_fila_vencida_por_quantidade_e_espera(self):
        one_min = NOW - datetime.timedelta(minutes=1)
        self.assertEqual(self._run_loop(vencida=(499, one_min))[0], saude_cli.OK)
        self.assertEqual(self._run_loop(vencida=(500, one_min))[0], saude_cli.WARNING)
        code, text, _r = self._run_loop(vencida=(5000, one_min))
        self.assertEqual(code, saude_cli.CRITICAL)
        self.assertIn("overdue_queue=5000;500;5000", text)
        self.assertEqual(self._run_loop(vencida=(1, NOW - datetime.timedelta(minutes=30)))[0], saude_cli.WARNING)
        self.assertEqual(self._run_loop(vencida=(1, NOW - datetime.timedelta(minutes=120)))[0], saude_cli.CRITICAL)
        self.assertEqual(self._run_loop(["--queue-warn", "10"], vencida=(10, one_min))[0], saude_cli.WARNING)

    def test_rodando_sem_pid(self):
        without_pid = [{"id": 77, "script_id": 3, "environment": "PRODUCAO", "agent_id": "srv-a",
                    "started_at": datetime.datetime(2026, 10, 21, 9, 55)}]
        code, text, repo = self._run_loop(["--no-pid-min", "5"], sem_pid=without_pid)
        self.assertEqual(code, saude_cli.WARNING)
        self.assertIn("WARNING: ticket 77 RUNNING sem PID no agente srv-a desde 2026-10-21 09:55:00", text)
        self.assertIn(("sem_pid", 5), repo.calls)

    def test_configuracao_divergente(self):
        other = CRITICAL.replace("kill=5", "kill=10")
        code, text, _r = self._run_loop(agents=[_agent("srv-a"), _agent("srv-b", cfg=other),
                                                 _agent("srv-c", status="STOPPED", cfg=other)])
        self.assertEqual(code, saude_cli.WARNING)
        self.assertIn("agente srv-b com configuracao divergente", text)
        self.assertNotIn("srv-c", text, "so agentes ativos")

    def test_cr030_sem_checagem_de_purge(self):
        """CR-030: o purge saiu; nao ha aviso de PURGE nem a opcao --purge-days."""
        with self.assertRaises(SystemExit):
            with mock.patch("sys.stderr", new_callable=io.StringIO):
                _args(["--purge-days", "3"])
        self.assertFalse(hasattr(saude_sql.RepoHealth, "last_purge"))

    def test_versao_do_esquema(self):
        code, text, _r = self._run_loop(version=sql_ident.SCHEMA_VERSION - 1)
        self.assertEqual(code, saude_cli.CRITICAL)
        self.assertIn("versao do esquema %d" % (sql_ident.SCHEMA_VERSION - 1), text)

    def test_pior_nivel_vence_e_criticos_primeiro(self):
        code, text, _r = self._run_loop(version=None, sem_pid=[{"id": 9, "agent_id": "srv-a", "started_at": NOW}])
        self.assertEqual(code, saude_cli.CRITICAL)
        rows = text.splitlines()
        self.assertTrue(rows[0].startswith("SSS CRITICAL - 2 problemas | "), rows)
        self.assertTrue(rows[1].startswith("CRITICAL: versao do esquema None"))


class TestMain(unittest.TestCase):

    def _main(self, argv=(), connect=None, cfg_error=False, secrets_error=False):
        output = io.StringIO()
        get = mock.Mock(side_effect=sss_config.ConfigError(reason="faltou dsn") if cfg_error else None,
                          return_value=_cfg())
        load = mock.Mock(side_effect=sss_config.ConfigError(reason="sem [monitor]") if secrets_error else None,
                             return_value=object())
        with mock.patch.object(saude_cli.sss_config, "get_config", get), \
                mock.patch.object(saude_cli.sss_config, "load_secrets", load), \
                mock.patch.object(saude_cli.saude_sql.RepoHealth, "from_config", return_value=_Repo()):
            code = saude_cli.main(_CONFIG_ARGS + list(argv), connect=connect, output=output)
        self.load = load
        return code, output.getvalue()

    def test_ok_com_papel_monitor(self):
        conn = _ConnNow()
        roles = []

        def conectar(cfg, secrets):
            roles.append(secrets)
            return conn
        code, text = self._main(connect=conectar)
        self.assertEqual(code, 0)
        self.assertTrue(text.startswith("SSS OK - 0 problemas"))
        self.assertEqual(self.load.call_args[1]["role"], "monitor")
        self.assertTrue(conn.closed)

    def test_unknown(self):
        self.assertEqual(self._main(cfg_error=True), (3, "SSS UNKNOWN - configuracao invalida: faltou dsn\n"))
        code, text = self._main(secrets_error=True)
        self.assertEqual(code, 3)
        self.assertIn("sem [monitor]", text)
        code, text = self._main(connect=mock.Mock(side_effect=RuntimeError("ORA-12541: TNS:no listener")))
        self.assertEqual(code, 3)
        self.assertIn("falha ao conectar no Oracle", text)
        conn = _ConnNow()
        with mock.patch.object(_Repo, "agents", side_effect=RuntimeError("ORA-03113: end-of-file")):
            code, text = self._main(connect=lambda c, s: conn)
        self.assertEqual(code, 3)
        self.assertIn("falha de banco", text)
        self.assertTrue(conn.closed)

    def test_segredos_do_monitor_sem_os_outros_papeis(self):
        # Integracao com o sss_config real: o arquivo do servidor do agente, com [oracle] e [environment:*].
        dir_value = tempfile.mkdtemp(prefix="sss_test_saude_")
        self.addCleanup(shutil.rmtree, dir_value, True)
        path = os.path.join(dir_value, "secrets.cfg")
        with open(path, "w") as f:
            f.write("[oracle]\npassword = senha-agt-1\n"
                    "[environment:PRODUCAO]\nuser = app\npassword = senha-amb-1\n"
                    "[monitor]\nuser = sss_monitor\npassword = senha-mon-1\n")
        os.chmod(path, 0o600)
        registered = []
        with mock.patch("sss.core.masking.register_secret", side_effect=registered.append):
            seg = sss_config.load_secrets(path, sss_env="PROD", role="monitor")
        self.assertEqual((seg.monitor_user, seg.oracle_password, seg.environments), ("sss_monitor", None, {}))
        self.assertEqual(registered, ["senha-mon-1"])


class TestSqlRepoHealth(unittest.TestCase):

    def setUp(self):
        self.repo = saude_sql.RepoHealth("openrisow", "tbsss_")

    def test_indices_sem_lob_e_interpretador_do_cadastro(self):
        queue_value = self.repo.sql("queue")
        self.assertIn("JOIN openrisow.tbsss_scripts s ON s.id = g.script_id", queue_value)
        self.assertIn("status = 'PENDING' AND GREATEST(scheduled_at, created_at) <= :now", queue_value)
        self.assertIn("status = 'PENDING' AND GREATEST(scheduled_at, created_at) <= :now",
                      self.repo.sql("overdue_queue"))
        self.assertIn("(CASE WHEN status = 'RUNNING' THEN agent_id END) >= CHR(1)", self.repo.sql("running_no_pid"))
        for name in ("agents", "environments", "queue", "overdue_queue", "running_no_pid", "version"):
            sql = self.repo.sql(name)
            self.assertTrue(sql.startswith("SELECT "), name)
            self.assertNotIn("submitted_params", sql)
            self.assertNotIn("log_output", sql)
            self.assertNotIn("*", sql.replace("COUNT(*)", ""), name)

    def test_tela_de_agentes_usa_o_mesmo_sql(self):
        from sss.persistence.oracle import agents as agentes_oracle
        self.assertIs(agentes_oracle._SQL_QUEUE, saude_sql.SQL_QUEUE)
        self.assertIs(agentes_oracle._SQL_RUNNING_NO_PID, saude_sql.SQL_RUNNING_NO_PID)

    def test_ambientes_atendidos_ignoram_em_risco_e_parados(self):
        lim = saude_cli.agents_service.Thresholds(10, 90, 180)
        agents = [_agent("a", 5), _agent("b", 91, environments="DESENV"),
                   _agent("c", 5, status="STOPPED", environments="HOMOLOGACAO")]
        self.assertEqual(saude_sql.served_pairs(agents, NOW, lim), {"PRODUCAO"})
        rows = [("PRODUCAO", "python3", 2, NOW), ("DESENV", "bash", 1, NOW)]
        self.assertEqual([g["environment"] for g in saude_sql.unattended_queue(rows, {"PRODUCAO"})], ["DESENV"])


if __name__ == "__main__":
    unittest.main()
