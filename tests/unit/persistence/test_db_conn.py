# -*- coding: utf-8 -*-
"""Testes unitarios para db_conn.py, scripts/probe_driver.py e _oracle_test_support.py (F7.0, F7.2).

Cobre a selecao adaptativa de driver, conexao por papel, pool, gerenciamento transacional,
classificacao de erros, tipos neutros, binds de data, orcamento de abertura de conexao,
reconexao resiliente sem sleep e schemas descartaveis em DEV.
"""
import collections
import datetime
import os
import sys
import unittest
from unittest import mock

from tests.support import _testenv  # noqa: F401
from tests.support import _oracle_test_support
from sss.persistence import db_conn
import probe_driver as sondar_driver
from sss.core import sql_ident


class _FakeOracleConfig(object):
    def __init__(self, driver_mode="auto", user="sss_web", dsn="localhost:2424/GFPR",
                 owner="openrisow", table_prefix="tbsss_", call_timeout_ms=5000,
                 oracle_client_lib_dir=None, pool_min=1, pool_max=4):
        self.driver_mode = driver_mode
        self.user = user
        self.dsn = dsn
        self.owner = owner
        self.table_prefix = table_prefix
        self.call_timeout_ms = call_timeout_ms
        self.oracle_client_lib_dir = oracle_client_lib_dir
        self.pool_min = pool_min
        self.pool_max = pool_max


class _FakeConfig(object):
    def __init__(self, driver_mode="auto", user="sss_web", dsn="localhost:2424/GFPR",
                 owner="openrisow", table_prefix="tbsss_", call_timeout_ms=5000,
                 oracle_client_lib_dir=None, sss_env="DEV", data_backend="ORACLE"):
        self.app = collections.namedtuple("AppConfig", ["sss_env", "data_backend"])(
            sss_env=sss_env, data_backend=data_backend
        )
        self.oracle = _FakeOracleConfig(
            driver_mode=driver_mode,
            user=user,
            dsn=dsn,
            owner=owner,
            table_prefix=table_prefix,
            call_timeout_ms=call_timeout_ms,
            oracle_client_lib_dir=oracle_client_lib_dir,
        )
        self.agent = collections.namedtuple("AgentConfig", ["agent_id"])(agent_id="srv-teste-01")
        self.file_path = None


class _FakeSecrets(object):
    def __init__(self, password="senha_super_secreta", purge_password="senha_purge_123",
                 monitor_user="sss_monitor", monitor_password="senha_mon_123"):
        self.oracle = collections.namedtuple("OracleSecret", ["password"])(password=password)
        self.purge = collections.namedtuple("PurgeSecret", ["password"])(password=purge_password)
        self.monitor = collections.namedtuple("MonitorSecret", ["user", "password"])(
            user=monitor_user, password=monitor_password
        )

    @property
    def oracle_password(self):
        return self.oracle.password

    @property
    def purge_password(self):
        return self.purge.password

    @property
    def monitor_user(self):
        return self.monitor.user

    @property
    def monitor_password(self):
        return self.monitor.password


class TestDbConnSelectionMocks(unittest.TestCase):
    """Testes unitarios da logica de selecao de driver com dubles (F7.0)."""

    def setUp(self):
        db_conn.reset_selection()
        self.cfg = _FakeConfig(driver_mode="auto")
        self.secrets = _FakeSecrets(password="teste_pwd_123")

    def tearDown(self):
        db_conn.reset_selection()

    def test_auto_escolhe_thin_quando_thin_conecta(self):
        """No modo 'auto', escolhe Thin logo de inicio quando a conexao Thin funciona."""
        calls = []

        def executor_sondagem(candidate, cfg, password_value):
            calls.append(candidate)
            if candidate == "thin":
                return {
                    "candidate": "thin",
                    "ok": True,
                    "server_version": "19.0.0.0.0",
                    "driver_version": "1.4.0",
                    "client_version": None,
                }
            return {"candidate": candidate, "ok": False}

        selection = db_conn.select_driver(self.cfg, self.secrets, probe_runner=executor_sondagem)
        self.assertEqual(selection.candidate, "thin")
        self.assertEqual(selection.server_version, "19.0.0.0.0")
        self.assertEqual(selection.driver_version, "1.4.0")
        self.assertIsNone(selection.client_version)
        self.assertEqual(calls, ["thin"])

    def test_thin_dpy_3010_thick_dpi_1047_cx_oracle(self):
        """Thin com DPY-3010 cai para Thick; Thick com DPI-1047 cai para cx_Oracle."""
        calls = []

        def executor_sondagem(candidate, cfg, password_value):
            calls.append(candidate)
            if candidate == "thin":
                return {"candidate": "thin", "ok": False, "error_code": "DPY-3010", "category": "INCOMPATIBLE"}
            elif candidate == "thick":
                return {"candidate": "thick", "ok": False, "error_code": "DPI-1047", "category": "LIBRARY"}
            elif candidate == "cx_oracle":
                return {
                    "candidate": "cx_oracle",
                    "ok": True,
                    "server_version": "11.2.0.4.0",
                    "driver_version": "8.3.0",
                    "client_version": "19.10",
                }
            return {"candidate": candidate, "ok": False}

        selection = db_conn.select_driver(self.cfg, self.secrets, probe_runner=executor_sondagem)
        self.assertEqual(selection.candidate, "cx_oracle")
        self.assertEqual(selection.server_version, "11.2.0.4.0")
        self.assertEqual(calls, ["thin", "thick", "cx_oracle"])

    def test_oracledb_ausente_escolhe_cx_oracle(self):
        """Quando oracledb nao esta instalado, cai para cx_Oracle."""
        calls = []

        def executor_sondagem(candidate, cfg, password_value):
            calls.append(candidate)
            if candidate in ("thin", "thick"):
                return {"candidate": candidate, "ok": False, "error_code": "NO_ORACLEDB", "category": "LIBRARY"}
            elif candidate == "cx_oracle":
                return {
                    "candidate": "cx_oracle",
                    "ok": True,
                    "server_version": "19.3.0.0.0",
                    "driver_version": "8.3.0",
                    "client_version": "19.10",
                }
            return {"candidate": candidate, "ok": False}

        selection = db_conn.select_driver(self.cfg, self.secrets, probe_runner=executor_sondagem)
        self.assertEqual(selection.candidate, "cx_oracle")
        self.assertEqual(calls, ["thin", "thick", "cx_oracle"])

    def test_erro_autenticacao_interrompe_cadeia(self):
        """Erro de autenticacao interrompe a cadeia imediatamente."""
        for code_error in ("ORA-01017", "ORA-28000"):
            db_conn.reset_selection()
            calls = []

            def executor_sondagem(candidate, cfg, password_value):
                calls.append(candidate)
                return {"candidate": candidate, "ok": False, "error_code": code_error, "category": "AUTHENTICATION"}

            with self.assertLogs("sss_db_conn", level="CRITICAL") as cm:
                with self.assertRaises(RuntimeError) as ctx:
                    db_conn.select_driver(self.cfg, self.secrets, probe_runner=executor_sondagem)

            self.assertIn("Falha fatal de autenticacao Oracle", str(ctx.exception))
            self.assertIn(code_error, str(ctx.exception))
            self.assertEqual(calls, ["thin"])
            self.assertTrue(any("CRITICAL" in msg and code_error in msg for msg in cm.output))

    def test_todos_falham_erro_fatal_critical(self):
        """Quando todos os candidatos falham, registra CRITICAL e lanca RuntimeError."""
        def executor_sondagem(candidate, cfg, password_value):
            errors = {
                "thin": ("DPY-4011", "NETWORK"),
                "thick": ("DPI-1047", "LIBRARY"),
                "cx_oracle": ("ORA-12541", "NETWORK"),
            }
            code, cat = errors[candidate]
            return {"candidate": candidate, "ok": False, "error_code": code, "category": cat}

        with self.assertLogs("sss_db_conn", level="CRITICAL") as cm:
            with self.assertRaises(RuntimeError) as ctx:
                db_conn.select_driver(self.cfg, self.secrets, probe_runner=executor_sondagem)

        msg_error = str(ctx.exception)
        self.assertIn("todos os candidatos de driver Oracle falharam", msg_error)
        self.assertIn("DPY-4011", msg_error)
        self.assertIn("DPI-1047", msg_error)
        self.assertIn("ORA-12541", msg_error)

    def test_candidato_forcado_falha_sem_sondar_outros(self):
        """Quando o candidato forcado falha, gera CRITICAL e nao testa os demais."""
        for mode in ("thin", "thick", "cx_oracle"):
            db_conn.reset_selection()
            cfg = _FakeConfig(driver_mode=mode)
            calls = []

            def executor_sondagem(candidate, cfg, password_value):
                calls.append(candidate)
                return {"candidate": candidate, "ok": False, "error_code": "FORCED_FAIL", "category": "INCOMPATIBLE"}

            with self.assertLogs("sss_db_conn", level="CRITICAL") as cm:
                with self.assertRaises(RuntimeError) as ctx:
                    db_conn.select_driver(cfg, self.secrets, probe_runner=executor_sondagem)

            self.assertIn("candidato forçado '%s' falhou" % mode, str(ctx.exception))
            self.assertEqual(calls, [mode])

    def test_valores_forcados_sucesso_nao_sondam_outros(self):
        """Quando candidato forcado tem sucesso, nao sonda outros."""
        for mode in ("thin", "thick", "cx_oracle"):
            db_conn.reset_selection()
            cfg = _FakeConfig(driver_mode=mode)
            calls = []

            def executor_sondagem(candidate, cfg, password_value):
                calls.append(candidate)
                return {
                    "candidate": candidate,
                    "ok": True,
                    "server_version": "19.0.0.0.0",
                    "driver_version": "2.0.0",
                    "client_version": "19.10" if candidate != "thin" else None,
                }

            selection = db_conn.select_driver(cfg, self.secrets, probe_runner=executor_sondagem)
            self.assertEqual(selection.candidate, mode)
            self.assertEqual(calls, [mode])

    def test_modo_driver_invalido_critical(self):
        """Modo driver invalido aborta com CRITICAL."""
        cfg = _FakeConfig(driver_mode="invalido_xyz")
        with self.assertLogs("sss_db_conn", level="CRITICAL") as cm:
            with self.assertRaises(RuntimeError) as ctx:
                db_conn.select_driver(cfg, self.secrets)
        self.assertIn("driver_mode 'invalido_xyz' invalido", str(ctx.exception))
        self.assertTrue(any("CRITICAL" in msg and "invalido_xyz" in msg for msg in cm.output))

    def test_cache_em_memoria_thread_safe(self):
        """Apos uma selecao bem-sucedida, chamadas subsequentes reutilizam o resultado."""
        executions = []

        def executor_sondagem(candidate, cfg, password_value):
            executions.append(candidate)
            return {"candidate": "thin", "ok": True, "server_version": "19.0.0.0.0", "driver_version": "1.4.0"}

        sel1 = db_conn.select_driver(self.cfg, self.secrets, probe_runner=executor_sondagem)
        sel2 = db_conn.select_driver(self.cfg, self.secrets, probe_runner=executor_sondagem)
        self.assertIs(sel1, sel2)
        self.assertEqual(len(executions), 1)


class TestDbConnApiAmpliadaMocks(unittest.TestCase):
    """Testes unitarios da API neutra, transacoes, binds, erros e pool (F7.2)."""

    def setUp(self):
        db_conn.reset_selection()
        self.cfg = _FakeConfig()
        self.secrets = _FakeSecrets()

    def tearDown(self):
        db_conn.reset_selection()

    def test_recusa_oracledb_2_no_python36(self):
        """python-oracledb 2.x e proibido no Python 3.6 (README §2.3)."""
        mock_oracledb = mock.MagicMock()
        mock_oracledb.__version__ = "2.0.1"

        with mock.patch.dict(sys.modules, {"oracledb": mock_oracledb}):
            with mock.patch.object(sys, "version_info", (3, 6, 8)):
                selection = db_conn.DriverSelection("thin", "19.0.0.0.0", "2.0.1", None)
                with self.assertLogs("sss_db_conn", level="CRITICAL") as cm:
                    with self.assertRaises(RuntimeError) as ctx:
                        db_conn.initialize(selection, cfg=self.cfg)
                self.assertIn("python-oracledb 2.x nao e compativel com Python 3.6", str(ctx.exception))
                self.assertTrue(any("CRITICAL" in m and "python-oracledb 2.x" in m for m in cm.output))

    def test_recusa_instant_client_diferente_de_19(self):
        """Thick e cx_Oracle recusam Instant Client diferente de 19 com CRITICAL (README §2.3)."""
        # Teste 1: oracledb Thick com IC 21
        mock_oracledb = mock.MagicMock()
        mock_oracledb.__version__ = "1.4.3"
        mock_oracledb.clientversion.return_value = (21, 3, 0, 0, 0)

        with mock.patch.dict(sys.modules, {"oracledb": mock_oracledb}):
            selection = db_conn.DriverSelection("thick", "19.0.0.0.0", "1.4.3", "21.3")
            with self.assertLogs("sss_db_conn", level="CRITICAL") as cm:
                with self.assertRaises(RuntimeError) as ctx:
                    db_conn.initialize(selection, cfg=self.cfg)
            self.assertIn("Exigido major 19", str(ctx.exception))
            self.assertTrue(any("CRITICAL" in m and "major 19" in m for m in cm.output))

        # Teste 2: cx_Oracle com IC 18
        db_conn.reset_selection()
        mock_cx = mock.MagicMock()
        mock_cx.clientversion.return_value = (18, 5, 0, 0, 0)

        with mock.patch.dict(sys.modules, {"cx_Oracle": mock_cx}):
            selection = db_conn.DriverSelection("cx_oracle", "11.2.0.4.0", "8.3.0", "18.5")
            with self.assertLogs("sss_db_conn", level="CRITICAL") as cm:
                with self.assertRaises(RuntimeError) as ctx:
                    db_conn.initialize(selection, cfg=self.cfg)
            self.assertIn("Exigido major 19", str(ctx.exception))

    def test_mesma_api_tres_combinacoes(self):
        """Valida que conectar() configura autocommit=False, call_timeout, module e action nos 3 modos."""
        modes = [
            ("thin", "oracledb", {"DB_TYPE_DATE": "DB_DATE"}),
            ("thick", "oracledb", {"DB_TYPE_DATE": "DB_DATE"}),
            ("cx_oracle", "cx_Oracle", {"DATETIME": "CX_DATETIME"}),
        ]
        for candidate, mod_name, kinds_extras in modes:
            db_conn.reset_selection()
            mock_drv = mock.MagicMock(__name__=mod_name)
            mock_drv.__version__ = "1.4.0" if mod_name == "oracledb" else "8.3.0"
            mock_drv.clientversion.return_value = (19, 10, 0, 0, 0)
            for k, v in kinds_extras.items():
                setattr(mock_drv, k, v)

            mock_conn = mock.MagicMock()
            mock_drv.connect.return_value = mock_conn

            with mock.patch.dict(sys.modules, {mod_name: mock_drv}):
                selection = db_conn.DriverSelection(candidate, "19.0.0.0.0", "1.4.0", "19.10" if candidate != "thin" else None)
                with mock.patch.object(db_conn, "select_driver", return_value=selection):
                    conn = db_conn.connect(self.cfg, self.secrets, role="web")
                    self.assertIs(conn, mock_conn)
                    self.assertFalse(mock_conn.autocommit)
                    self.assertEqual(mock_conn.call_timeout, 5000)
                    self.assertEqual(mock_conn.module, "SSS_WEB")
                    self.assertEqual(mock_conn.action, "INICIO")
                    self.assertEqual(mock_conn.client_identifier, "srv-teste-01")

    def test_transacao_commit_e_rollback(self):
        """transacao() faz commit no sucesso, rollback em erro e classifica WARN sem stack para timeout/lock."""
        mock_conn = mock.MagicMock()

        # 1. Sucesso: executa commit
        with db_conn.transaction(mock_conn):
            pass
        mock_conn.commit.assert_called_once()
        mock_conn.rollback.assert_not_called()

        # 2. Erro de lock ORA-00054: faz rollback, registra WARN sem stack trace
        mock_conn.reset_mock()
        with self.assertLogs("sss_db_conn", level="WARNING") as cm:
            with self.assertRaises(Exception):
                with db_conn.transaction(mock_conn):
                    raise Exception("ORA-00054: resource busy and acquire with NOWAIT specified")

        mock_conn.rollback.assert_called_once()
        self.assertTrue(any("Falha de concorrencia/lock/timeout" in m and "ORA-54" in m for m in cm.output))

        # 3. Erro generico: faz rollback, registra ERROR com stack trace
        mock_conn.reset_mock()
        with self.assertLogs("sss_db_conn", level="ERROR") as cm_err:
            with self.assertRaises(ValueError):
                with db_conn.transaction(mock_conn):
                    raise ValueError("falha de negocio qualquer")

        mock_conn.rollback.assert_called_once()
        self.assertTrue(any("Erro na transacao Oracle" in m for m in cm_err.output))

    def test_classificacao_erros_e_failover(self):
        """Valida classificacao de erros de rede/failover, timeout, lock e violacoes."""
        # Rede e failover (CR-007, R-12)
        errors_network = [
            "ORA-03113: end-of-file on communication channel",
            "ORA-03114: not connected to ORACLE",
            "ORA-03135: connection lost contact",
            "ORA-12541: TNS:no listener",
            "ORA-12170: TNS:Connect timeout occurred",
            "ORA-12514: TNS:listener does not currently know of service",
            "ORA-12528: TNS:listener: all appropriate instances are blocking new connections",
            "ORA-12537: TNS:connection closed",
            "ORA-01033: ORACLE initialization or shutdown in progress",
            "ORA-01034: ORACLE not available",
            "ORA-01089: immediate shutdown in progress",
            "ORA-00028: your session has been killed",
            "ORA-01012: not logged on",
            "ORA-02396: exceeded maximum idle time",
            "ORA-25408: can not safely replay call",
            "DPI-1080: connection was closed by server",
            "DPY-4011: the network connection was closed",
            "DPY-6000: cannot connect to database",
            "DPY-6005: cannot connect to database",
        ]
        for msg in errors_network:
            exc = Exception(msg)
            self.assertTrue(db_conn.is_network_error(exc), "Deveria ser erro de rede: %s" % msg)
            self.assertFalse(db_conn.is_lock(exc))
            self.assertFalse(db_conn.is_violation(exc))

        # Call timeout
        for msg in ("DPY-4024: call timeout of 5000 ms occurred", "DPI-1067: call timeout of 5000 ms occurred", "ORA-03156: OCI call timed out"):
            exc = Exception(msg)
            self.assertTrue(db_conn.is_timeout(exc), "Deveria ser call timeout: %s" % msg)

        # Lock e deadlock
        for msg in ("ORA-00054: resource busy", "ORA-30006: resource busy; acquire with WAIT timeout expired", "ORA-00060: deadlock detected"):
            exc = Exception(msg)
            self.assertTrue(db_conn.is_lock(exc), "Deveria ser erro de lock: %s" % msg)

        # Violacoes
        for msg in (
            "ORA-00001: unique constraint (OPENRISOW.UK_TBSSS_TCK) violated",
            "ORA-02290: check constraint (OPENRISOW.CK_TBSSS_TCK_ST) violated",
            "ORA-02291: integrity constraint (OPENRISOW.FK_TBSSS_TCK_SCR) violated - parent key not found",
            "ORA-02292: integrity constraint (OPENRISOW.FK_TBSSS_TCK_RESP) violated - child record found",
            "ORA-01400: cannot insert NULL into (OPENRISOW.TBSSS_SCRIPTS.PATH_FILE)",
            "ORA-12899: value too large for column OPENRISOW.TBSSS_AUDIT.ACTOR",
            "ORA-01438: value larger than specified precision allowed for this column",
        ):
            exc = Exception(msg)
            self.assertTrue(db_conn.is_violation(exc), "Deveria ser violacao: %s" % msg)

    def test_backoff_sem_sleep_em_garantir(self):
        """ConexaoResiliente gerencia backoff exponencial (1s a 60s) via monotonic() sem time.sleep."""
        resilient = db_conn.ResilientConnection(self.cfg, self.secrets, role="agent")
        self.assertIsNone(resilient.get_connection())

        t_current = 1000.0

        with mock.patch("time.monotonic", side_effect=lambda: t_current):
            with mock.patch.object(db_conn, "connect") as mock_connect:
                # 1. Primeira tentativa falha: backoff dobra de 1.0 para 2.0
                mock_connect.side_effect = Exception("ORA-12541: no listener")
                ok = resilient.ensure()
                self.assertFalse(ok)
                self.assertEqual(resilient.backoff_s, 2.0)
                self.assertEqual(resilient.next_attempt_monotonic, 1001.0)

                # 2. Chamada antes do prazo (t_current = 1000.5): retorna False imediatamente sem tentar conectar
                t_current = 1000.5
                mock_connect.reset_mock()
                ok = resilient.ensure()
                self.assertFalse(ok)
                mock_connect.assert_not_called()

                # 3. Chamada apos vencer o prazo (t_current = 1001.2): tenta novamente e tem sucesso
                t_current = 1001.2
                mock_conn = mock.MagicMock()
                mock_connect.side_effect = None
                mock_connect.return_value = mock_conn

                ok = resilient.ensure()
                self.assertTrue(ok)
                self.assertIs(resilient.get_connection(), mock_conn)
                self.assertEqual(resilient.backoff_s, 1.0)  # Resetado para 1.0

                # 4. Notificar erro de rede fecha conexao e reinicia backoff
                resilient.notify_error(Exception("ORA-03113: end-of-file"))
                self.assertIsNone(resilient.get_connection())
                self.assertTrue(resilient.failing)
                self.assertEqual(resilient.backoff_s, 2.0)

    def test_orcamento_conexao_s(self):
        """Valida connection_budget_s com Easy Connect e descritores TNS com aviso de timeout (CR-008, R-17)."""
        db_conn.reset_selection()

        # 1. Easy Connect: 1 endereco, retorna call_timeout_s
        budget = db_conn.connection_budget_s("localhost:2424/servico", 30.0)
        self.assertEqual(budget, 30)

        # 2. Descritor TNS 1 endereco: CONNECT_TIMEOUT=5, RETRY_COUNT=2 -> 5 * (2 + 1) * 1 = 15
        dsn1 = "(DESCRIPTION=(CONNECT_TIMEOUT=5)(RETRY_COUNT=2)(ADDRESS=(PROTOCOL=TCP)(HOST=host1)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=svc)))"
        orc1 = db_conn.connection_budget_s(dsn1, 30.0)
        self.assertEqual(orc1, 15)

        # 3. Descritor TNS 2 enderecos: CONNECT_TIMEOUT=10, RETRY_COUNT=1 -> 10 * 2 * 2 = 40 (> 30s)
        dsn2 = (
            "(DESCRIPTION=(CONNECT_TIMEOUT=10)(RETRY_COUNT=1)"
            "(ADDRESS_LIST=(ADDRESS=(PROTOCOL=TCP)(HOST=h1)(PORT=1521))(ADDRESS=(PROTOCOL=TCP)(HOST=h2)(PORT=1521)))"
            "(CONNECT_DATA=(SERVICE_NAME=svc)))"
        )
        with self.assertLogs("sss_db_conn", level="WARNING") as cm:
            orc2 = db_conn.connection_budget_s(dsn2, 30.0)
        self.assertEqual(orc2, 40)
        self.assertTrue(any("CONEXAO_ACIMA_DO_PRAZO" in m and "40s" in m for m in cm.output))

    def test_conferir_versao_esquema(self):
        """check_schema_version() valida schema_version da tabela controle contra sql_ident (CR-007, D4)."""
        mock_conn = mock.MagicMock()
        mock_cur = mock.MagicMock()
        mock_conn.cursor.return_value = mock_cur

        # 1. Versao igual
        mock_cur.fetchone.return_value = (sql_ident.SCHEMA_VERSION,)
        v = db_conn.check_schema_version(mock_conn, owner="openrisow")
        self.assertEqual(v, sql_ident.SCHEMA_VERSION)

        # 2. Versao incompativel
        mock_cur.fetchone.return_value = (sql_ident.SCHEMA_VERSION + 1,)
        with self.assertLogs("sss_db_conn", level="CRITICAL"):
            with self.assertRaises(db_conn.SchemaVersionError) as ctx:
                db_conn.check_schema_version(mock_conn, owner="openrisow")
        self.assertIn("Versao do esquema incompativel", str(ctx.exception))

        # 3. Linha ausente
        mock_cur.fetchone.return_value = None
        with self.assertLogs("sss_db_conn", level="CRITICAL"):
            with self.assertRaises(db_conn.SchemaVersionError) as ctx:
                db_conn.check_schema_version(mock_conn, owner="openrisow")
        self.assertIn("ausente na tabela de controle", str(ctx.exception))

    def test_definir_tipos_entrada_date_setinputsizes(self):
        """set_input_types converte TIPO_DATE para o tipo de data nativo do driver ativo."""
        mock_cur = mock.MagicMock()

        # Simulando oracledb
        mock_oracledb = mock.MagicMock(__name__="oracledb")
        mock_oracledb.DB_TYPE_DATE = "ORACLEDB_DATE_TYPE"
        selection_thin = db_conn.DriverSelection("thin", "19.0.0.0.0", "1.4.0", None)

        with mock.patch.object(db_conn, "_DRIVER_SELECTION", selection_thin):
            with mock.patch.object(db_conn, "_DRIVER_INITIALIZED", mock_oracledb):
                db_conn.set_input_types(mock_cur, dt=db_conn.TIPO_DATE, clob=db_conn.TIPO_CLOB)
                mock_cur.setinputsizes.assert_called_with(dt="ORACLEDB_DATE_TYPE", clob=mock_oracledb.DB_TYPE_CLOB)

        # Simulando cx_Oracle
        mock_cur.reset_mock()
        mock_cx = mock.MagicMock(__name__="cx_Oracle")
        mock_cx.DATETIME = "CX_DATETIME_TYPE"
        selection_cx = db_conn.DriverSelection("cx_oracle", "11.2.0.4.0", "8.3.0", "19.10")

        with mock.patch.object(db_conn, "_DRIVER_SELECTION", selection_cx):
            with mock.patch.object(db_conn, "_DRIVER_INITIALIZED", mock_cx):
                db_conn.set_input_types(mock_cur, dt=db_conn.TIPO_DATE)
                mock_cur.setinputsizes.assert_called_with(dt="CX_DATETIME_TYPE")

    def test_tipo_blob_por_driver(self):
        """TIPO_BLOB (CR-012): DB_TYPE_BLOB no python-oracledb e BLOB no cx_Oracle."""
        drv = mock.MagicMock(__name__="oracledb")
        self.assertIs(db_conn.get_driver_type(db_conn.TIPO_BLOB, driver=drv, candidate="thin"), drv.DB_TYPE_BLOB)
        cx = mock.MagicMock(__name__="cx_Oracle")
        self.assertIs(db_conn.get_driver_type(db_conn.TIPO_BLOB, driver=cx, candidate="cx_oracle"), cx.BLOB)
        self.assertIn(db_conn.TIPO_BLOB, db_conn.TIPOS_NEUTROS)

    def test_tipo_varchar_variavel_saida_e_valor_saida(self):
        """output_variable e output_value operam com OUT binds nos drivers sem expor cursor.var."""
        mock_cur = mock.MagicMock()
        mock_var = mock.MagicMock()
        mock_var.getvalue.return_value = "VALOR_RETORNADO_PLSQL"
        mock_cur.var.return_value = mock_var

        mock_oracledb = mock.MagicMock(__name__="oracledb")
        mock_oracledb.DB_TYPE_VARCHAR = "DB_VARCHAR_TYPE"
        selection = db_conn.DriverSelection("thin", "19.0.0.0.0", "1.4.0", None)

        with mock.patch.object(db_conn, "_DRIVER_SELECTION", selection):
            with mock.patch.object(db_conn, "_DRIVER_INITIALIZED", mock_oracledb):
                v = db_conn.output_variable(mock_cur, db_conn.TIPO_VARCHAR, size=100)
                mock_cur.var.assert_called_with("DB_VARCHAR_TYPE", size=100)
                res = db_conn.output_value(v)
                self.assertEqual(res, "VALOR_RETORNADO_PLSQL")

    def test_proximo_id_qualificado(self):
        """next_id executa NEXTVAL com o identificador qualificado e retorna int."""
        mock_conn = mock.MagicMock()
        mock_cur = mock.MagicMock()
        mock_cur.fetchone.return_value = (42,)
        mock_conn.cursor.return_value = mock_cur

        pid = db_conn.next_id(mock_conn, "openrisow.sq_tbsss_tck")
        self.assertEqual(pid, 42)
        mock_cur.execute.assert_called_with("SELECT openrisow.sq_tbsss_tck.NEXTVAL FROM DUAL")

    def test_agora_banco_sem_microssegundos(self):
        """agora_banco retorna o SYSDATE com microsecond==0."""
        mock_conn = mock.MagicMock()
        mock_cur = mock.MagicMock()
        dt_with_micro = datetime.datetime(2026, 10, 19, 12, 30, 45, 999999)
        mock_cur.fetchone.return_value = (dt_with_micro,)
        mock_conn.cursor.return_value = mock_cur

        res = db_conn.db_now(mock_conn)
        self.assertEqual(res.microsecond, 0)
        self.assertEqual(res, datetime.datetime(2026, 10, 19, 12, 30, 45, 0))

    def test_saude(self):
        """saude retorna o SYSDATE naive do banco."""
        mock_conn = mock.MagicMock()
        mock_cur = mock.MagicMock()
        dt_expected = datetime.datetime(2026, 10, 19, 12, 30, 45)
        mock_cur.fetchone.return_value = (dt_expected,)
        mock_conn.cursor.return_value = mock_cur

        self.assertEqual(db_conn.health(mock_conn), dt_expected)

    def test_ausencia_de_senha_em_logs(self):
        """A senha nunca deve aparecer em mensagens de log emitidas por db_conn."""
        password_super_secret = "minha_senha_super_secreta_999"
        seg = _FakeSecrets(password=password_super_secret)
        with self.assertLogs("sss_db_conn", level="INFO") as cm:
            mock_drv = mock.MagicMock(__name__="oracledb")
            mock_drv.__version__ = "1.4.0"
            mock_conn = mock.MagicMock()
            mock_drv.connect.return_value = mock_conn
            with mock.patch.dict(sys.modules, {"oracledb": mock_drv}):
                selection = db_conn.DriverSelection("thin", "19.0.0.0.0", "1.4.0", None)
                with mock.patch.object(db_conn, "select_driver", return_value=selection):
                    db_conn.connect(self.cfg, seg, role="web")

        for record in cm.output:
            self.assertNotIn(password_super_secret, record)

    def test_tipo_varchar_tres_modos(self):
        """TIPO_VARCHAR e output_variable/output_value operam identicamente nos tres modos."""
        modes = [
            ("thin", "oracledb", "DB_TYPE_VARCHAR"),
            ("thick", "oracledb", "DB_TYPE_VARCHAR"),
            ("cx_oracle", "cx_Oracle", "STRING"),
        ]
        for candidate, mod_name, attr_kind in modes:
            mock_cur = mock.MagicMock()
            mock_var = mock.MagicMock()
            mock_var.getvalue.return_value = "RESULTADO_OK"
            mock_cur.var.return_value = mock_var

            mock_drv = mock.MagicMock(__name__=mod_name)
            setattr(mock_drv, attr_kind, "TIPO_CONCRETO_VARCHAR")

            selection = db_conn.DriverSelection(candidate, "19.0.0.0.0", "1.4.0", None)
            with mock.patch.object(db_conn, "_DRIVER_SELECTION", selection):
                with mock.patch.object(db_conn, "_DRIVER_INITIALIZED", mock_drv):
                    v = db_conn.output_variable(mock_cur, db_conn.TIPO_VARCHAR, size=50)
                    mock_cur.var.assert_called_with("TIPO_CONCRETO_VARCHAR", size=50)
                    self.assertEqual(db_conn.output_value(v), "RESULTADO_OK")

    def test_traduzir_erro(self):
        """translate_error mapeia corretamente para RepoViolation, RepoConflict, RepoUnavailable e RepoError."""
        from sss.persistence import repo_errors
        # Violacao
        e1 = db_conn.translate_error(Exception("ORA-00001: unique constraint violated"))
        self.assertIsInstance(e1, repo_errors.RepoViolation)
        # Lock / Conflito
        e2 = db_conn.translate_error(Exception("ORA-00054: resource busy"))
        self.assertIsInstance(e2, repo_errors.RepoConflict)
        # Rede / Indisponivel
        e3 = db_conn.translate_error(Exception("ORA-03113: end-of-file"))
        self.assertIsInstance(e3, repo_errors.RepoUnavailable)
        # Generico
        e4 = db_conn.translate_error(Exception("ORA-00942: table does not exist"))
        self.assertIsInstance(e4, repo_errors.RepoError)

    def test_pool_web_ping_interval_60(self):
        """pool cria pool com ping_interval=60 para oracledb e cx_Oracle (CR-007, R-12)."""
        # oracledb create_pool
        mock_oracledb = mock.MagicMock(__name__="oracledb")
        selection = db_conn.DriverSelection("thin", "19.0.0.0.0", "1.4.0", None)
        with mock.patch.object(db_conn, "_DRIVER_SELECTION", selection):
            with mock.patch.object(db_conn, "_DRIVER_INITIALIZED", mock_oracledb):
                p = db_conn.pool(self.cfg, self.secrets, role="web")
                mock_oracledb.create_pool.assert_called_once()
                kw = mock_oracledb.create_pool.call_args[1]
                self.assertEqual(kw["ping_interval"], 60)
                self.assertEqual(kw["min"], 1)
                self.assertEqual(kw["max"], 4)


class TestOracleTestSupportMocks(unittest.TestCase):
    """Testes unitarios de scripts/_oracle_test_support.py (chave unica SSS_TEST_ORACLE=1) com dubles."""

    _ENABLED = {"SSS_TEST_ORACLE": "1"}

    def _cfg(self, owner="openrisow", user="openrisow", sss_env="DEV", dsn="localhost:2424/GFPR"):
        cfg = mock.MagicMock()
        cfg.app.sss_env = sss_env
        cfg.app.data_backend = "FAKE"
        cfg.oracle.owner = owner
        cfg.oracle.user = user
        cfg.oracle.dsn = dsn
        cfg.oracle.table_prefix = "tbsss_"
        cfg.secrets.secrets_file = "/tmp/fake_secrets.cfg"
        return cfg

    def _conn(self, user, version=None):
        mock_conn = mock.MagicMock()
        mock_cur = mock.MagicMock()
        mock_cur.fetchone.side_effect = [(user,)] + ([(version,)] if version is not None else [])
        mock_conn.cursor.return_value = mock_cur
        return mock_conn, mock_cur

    def test_desligado_sem_a_chave(self):
        for env in ({}, {"SSS_TEST_ORACLE": "0"}, {"SSS_TEST_ORACLE": "sim"}):
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertFalse(_oracle_test_support.real_db_configured())
                ok, reason = _oracle_test_support.check_environment_preconditions(cfg=self._cfg())
                self.assertFalse(ok)
                self.assertIn("SSS_TEST_ORACLE=1", reason)

    def test_variaveis_antigas_recusadas(self):
        """As variaveis da guarda anterior nao sao ignoradas em silencio."""
        for old in _oracle_test_support.OLD_VARIABLES:
            with mock.patch.dict(os.environ, dict(self._ENABLED, **{old: "x"}), clear=True):
                ok, reason = _oracle_test_support.check_environment_preconditions(cfg=self._cfg())
                self.assertFalse(ok)
                self.assertIn(old, reason)

    def test_modo_deduzido_do_owner(self):
        self.assertEqual(_oracle_test_support.owner_mode("SSS_TEST_DEV"), _oracle_test_support.DISPOSABLE_MODE)
        self.assertEqual(_oracle_test_support.owner_mode("sss_test_dev"), _oracle_test_support.DISPOSABLE_MODE)
        self.assertEqual(_oracle_test_support.owner_mode("openrisow"), _oracle_test_support.SHARED_MODE)

    def test_precondicoes_do_config(self):
        """DEV obrigatorio, DSN preenchido e owner valido; o data_backend nao importa."""
        with mock.patch.dict(os.environ, self._ENABLED, clear=True):
            self.assertEqual(_oracle_test_support.check_environment_preconditions(cfg=self._cfg()), (True, ""))
            for cfg, snippet in ((self._cfg(sss_env="HML"), "DEV"), (self._cfg(dsn=""), "dsn"),
                                (self._cfg(owner="openrisow;DROP"), "owner"),
                                (self._cfg(owner="SSS_TEST_"), "descartavel"), (self._cfg(owner="SSS_TEST_" + "X" * 25), "owner")):
                ok, reason = _oracle_test_support.check_environment_preconditions(cfg=cfg)
                self.assertFalse(ok)
                self.assertIn(snippet, reason)

    def test_descartavel_conta_igual_owner_recusada(self):
        mock_conn, _cur = self._conn("SSS_TEST_DEV")
        with self.assertRaises(_oracle_test_support.SchemaPreconditionError):
            _oracle_test_support.validate_disposable_schema(mock_conn, "SSS_TEST_DEV", "SSS_TEST_DEV")

    def test_descartavel_sessao_divergente_recusada(self):
        mock_conn, _cur = self._conn("USUARIO_QUALQUER")
        with self.assertRaises(_oracle_test_support.SchemaPreconditionError) as ctx:
            _oracle_test_support.validate_disposable_schema(mock_conn, "SSS_TEST_DEV", "SSS_TEST_WEB")
        self.assertIn("difere do esperado", str(ctx.exception))

    def test_descartavel_ok_sem_conferir_controle(self):
        mock_conn, mock_cur = self._conn("SSS_TEST_WEB")
        res = _oracle_test_support.validate_disposable_schema(mock_conn, "SSS_TEST_APP", "SSS_TEST_WEB")
        self.assertEqual(res, "SSS_TEST_APP")
        self.assertEqual(mock_cur.execute.call_count, 1)

    def test_compartilhado_conta_igual_owner_com_esquema_na_versao(self):
        from sss.core import sql_ident
        mock_conn, mock_cur = self._conn("OPENRISOW", sql_ident.SCHEMA_VERSION)
        res = _oracle_test_support.validate_disposable_schema(mock_conn, "openrisow", "openrisow", prefix="tbsss_")
        self.assertEqual(res, "OPENRISOW")
        self.assertEqual(mock_cur.execute.call_args_list[1][0][0],
                         "SELECT schema_version FROM OPENRISOW.tbsss_control")

    def test_compartilhado_versao_divergente_recusada(self):
        from sss.core import sql_ident
        mock_conn, _cur = self._conn("OPENRISOW", sql_ident.SCHEMA_VERSION + 1)
        with self.assertRaises(_oracle_test_support.SchemaPreconditionError) as ctx:
            _oracle_test_support.validate_disposable_schema(mock_conn, "OPENRISOW", "OPENRISOW")
        self.assertIn("difere da do codigo", str(ctx.exception))

    def test_compartilhado_sem_esquema_sss_recusado(self):
        mock_conn = mock.MagicMock()
        mock_cur = mock.MagicMock()
        mock_cur.fetchone.return_value = ("OPENRISOW",)
        mock_cur.execute.side_effect = [None, RuntimeError("ORA-00942")]
        mock_conn.cursor.return_value = mock_cur
        with self.assertRaises(_oracle_test_support.SchemaPreconditionError) as ctx:
            _oracle_test_support.validate_disposable_schema(mock_conn, "OPENRISOW", "OPENRISOW")
        self.assertIn("Esquema SSS ausente", str(ctx.exception))

    def test_compartilhado_sessao_de_outra_conta_recusada(self):
        from sss.core import sql_ident
        mock_conn, _cur = self._conn("OUTRA", sql_ident.SCHEMA_VERSION)
        with self.assertRaises(_oracle_test_support.SchemaPreconditionError):
            _oracle_test_support.validate_disposable_schema(mock_conn, "OPENRISOW", "OPENRISOW")

    def test_preparar_usa_o_config_da_aplicacao_e_registra_o_modo(self):
        """Sem cfg, usa sss_config.get_config() (instance/config.ini) e guarda o modo validado."""
        from sss.core import sql_ident
        mock_conn, _cur = self._conn("OPENRISOW", sql_ident.SCHEMA_VERSION)
        cfg = self._cfg()
        with mock.patch.dict(os.environ, self._ENABLED, clear=True):
            with mock.patch("sss.config.sss_config.get_config", return_value=cfg) as get:
                with mock.patch("sss.config.sss_config.load_secrets", return_value=mock.MagicMock()):
                    with mock.patch("sss.persistence.db_conn.connect", return_value=mock_conn):
                        self.assertIs(_oracle_test_support.prepare_disposable_schema("web"), cfg)
        get.assert_called_once_with()
        mock_conn.close.assert_called_once()
        self.assertEqual(_oracle_test_support.schema_mode(), _oracle_test_support.SHARED_MODE)

    def test_preparar_descartavel_recusa_conta_do_owner_sem_conectar(self):
        cfg = self._cfg(owner="SSS_TEST_APP", user="SSS_TEST_APP")
        with mock.patch.dict(os.environ, self._ENABLED, clear=True):
            with mock.patch("sss.persistence.db_conn.connect") as connect:
                with self.assertRaises(_oracle_test_support.SchemaPreconditionError):
                    _oracle_test_support.prepare_disposable_schema("web", cfg=cfg)
        connect.assert_not_called()

    def test_preparar_desligado_nao_le_config_nem_conecta(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("sss.config.sss_config.get_config") as get, mock.patch("sss.persistence.db_conn.connect") as connect:
                with self.assertRaises(_oracle_test_support.SchemaPreconditionError):
                    _oracle_test_support.prepare_disposable_schema("web")
        get.assert_not_called()
        connect.assert_not_called()


class TestFirstConnectionIsNotReconnection(unittest.TestCase):
    """F9.1d: a primeira conexao do ConexaoResiliente e INFO 'Conectando'/'Conexao estabelecida'; o WARN
    'Tentando reconexao' fica so para as reconexoes de verdade."""

    def test_primeira_conexao_e_depois_reconexao(self):
        resilient = db_conn.ResilientConnection(_FakeConfig(), _FakeSecrets(password="x"))
        with mock.patch.object(db_conn, "connect", return_value=mock.Mock()):
            with self.assertLogs("sss_db_conn", "INFO") as first:
                self.assertTrue(resilient.ensure())
            resilient.close()
            resilient.next_attempt_monotonic = 0.0
            with self.assertLogs("sss_db_conn", "INFO") as second:
                self.assertTrue(resilient.ensure())
        self.assertEqual([(r.levelname, r.getMessage()) for r in first.records],
                         [("INFO", "Conectando ao Oracle (papel=agent)..."),
                          ("INFO", "Conexao estabelecida (papel=agent)")])
        self.assertEqual([(r.levelname, r.getMessage()) for r in second.records],
                         [("WARNING", "Tentando reconexao com o Oracle (papel=agent)..."),
                          ("INFO", "Reconexao bem-sucedida (papel=agent)")])

    def test_falha_na_primeira_conexao(self):
        resilient = db_conn.ResilientConnection(_FakeConfig(), _FakeSecrets(password="x"))
        with mock.patch.object(db_conn, "connect", side_effect=RuntimeError("ORA-12541: TNS:no listener")):
            with self.assertLogs("sss_db_conn", "INFO") as logs:
                self.assertFalse(resilient.ensure())
        self.assertIn("Falha na tentativa de conexao: ORA-12541", logs.records[-1].getMessage())


class TestProbeWithRoleAccount(unittest.TestCase):
    """F9.1d (ensaio a partir do pacote): a sondagem usa a conta do papel que conecta (monitor, purge), nao a do
    [oracle]; o usuario vai no argv e a senha so pela entrada padrao."""

    def setUp(self):
        db_conn.reset_selection()
        self.addCleanup(db_conn.reset_selection)

    def test_subprocesso_recebe_o_usuario_no_argv_e_a_senha_no_stdin(self):
        process = mock.Mock(returncode=0)
        process.communicate.return_value = (b'{"candidate": "thin", "ok": true}', b"")
        with mock.patch.object(db_conn.subprocess, "Popen", return_value=process) as popen:
            db_conn.select_driver(_FakeConfig(driver_mode="thin"), _FakeSecrets(password="x"),
                                      user="sss_monitor", password_value="senha-mon-77")
        cmd = popen.call_args[0][0]
        self.assertEqual(cmd[-2:], ["--user", "sss_monitor"])
        self.assertNotIn("senha-mon-77", " ".join(cmd))
        self.assertEqual(process.communicate.call_args[1]["input"], b"senha-mon-77")

    def test_conectar_monitor_sonda_com_a_conta_do_monitor(self):
        secrets_value = mock.Mock(monitor=mock.Mock(user="sss_monitor", password="senha-mon-77"))
        captured = {}

        def selecionar(cfg, secrets_obj, user=None, password_value=None):
            captured.update(usuario=user, senha=password_value)
            raise RuntimeError("parar aqui")
        with mock.patch.object(db_conn, "select_driver", side_effect=selecionar), \
                mock.patch.object(db_conn, "connection_budget_s"):
            with self.assertRaises(RuntimeError):
                db_conn.connect(_FakeConfig(driver_mode="thin"), secrets_value, role="monitor")
        self.assertEqual(captured, {"usuario": "sss_monitor", "senha": "senha-mon-77"})

    def test_sondar_driver_usa_o_usuario_informado(self):
        cfg = _FakeConfig(driver_mode="thin")
        fake = mock.Mock()
        fake.connect.side_effect = RuntimeError("ORA-01017: invalid username/password")
        with mock.patch.dict(sys.modules, {"oracledb": fake}):
            sondar_driver.probe("thin", cfg, "s", user="sss_monitor")
        self.assertEqual(fake.connect.call_args[1]["user"], "sss_monitor")


class TestProbeDriverScript(unittest.TestCase):
    """Testes unitarios do scripts/probe_driver.py."""

    def test_categorizacao_erros(self):
        """Valida que codigos Oracle/DPY/DPI sao categorizados corretamente."""
        cases = [
            ("ORA-01017: invalid username/password", "ORA-01017", "AUTHENTICATION"),
            ("ORA-28000: the account is locked", "ORA-28000", "AUTHENTICATION"),
            ("DPY-3010: connections to this database server version are not supported", "DPY-3010", "INCOMPATIBLE"),
            ("DPI-1047: Cannot locate a 64-bit Oracle Client library", "DPI-1047", "LIBRARY"),
            (ImportError("No module named 'oracledb'"), "IMPORT_ERROR", "LIBRARY"),
            ("ORA-12170: TNS:Connect timeout occurred", "ORA-12170", "NETWORK"),
            ("ORA-12541: TNS:no listener", "ORA-12541", "NETWORK"),
            ("DPY-4011: the network connection was closed", "DPY-4011", "NETWORK"),
            ("ORA-00942: table or view does not exist", "ORA-00942", "OTHER"),
        ]
        for item, code_expected, cat_expected in cases:
            exc = item if isinstance(item, Exception) else Exception(item)
            code, cat = sondar_driver._classify_error(exc)
            self.assertEqual(code, code_expected, "Codigo incorreto para: %s" % item)
            self.assertEqual(cat, cat_expected, "Categoria incorreta para: %s" % item)


if __name__ == "__main__":
    unittest.main()
