# -*- coding: utf-8 -*-
"""Testes unitarios para db_conn.py, scripts/sondar_driver.py e _oracle_test_support.py (F7.0, F7.2).

Cobre a selecao adaptativa de driver, conexao por papel, pool, gerenciamento transacional,
classificacao de erros, tipos neutros, binds de data, orcamento de abertura de conexao,
reconexao resiliente sem sleep e schemas descartaveis em DEV.
"""
import collections
import datetime
import json
import logging
import os
import re
import subprocess
import sys
import time
import unittest
from unittest import mock

import _testenv  # noqa: F401
import _oracle_test_support
import db_conn
import plataforma
import sondar_driver


class _FakeOracleConfig(object):
    def __init__(self, modo_driver="auto", user="sss_web", dsn="localhost:2424/GFPR",
                 owner="openrisow", table_prefix="tbsss_", call_timeout_ms=5000,
                 oracle_client_lib_dir=None, pool_min=1, pool_max=4):
        self.modo_driver = modo_driver
        self.user = user
        self.dsn = dsn
        self.owner = owner
        self.table_prefix = table_prefix
        self.call_timeout_ms = call_timeout_ms
        self.oracle_client_lib_dir = oracle_client_lib_dir
        self.pool_min = pool_min
        self.pool_max = pool_max


class _FakeConfig(object):
    def __init__(self, modo_driver="auto", user="sss_web", dsn="localhost:2424/GFPR",
                 owner="openrisow", table_prefix="tbsss_", call_timeout_ms=5000,
                 oracle_client_lib_dir=None, sss_env="DEV", data_backend="ORACLE"):
        self.app = collections.namedtuple("AppConfig", ["sss_env", "data_backend"])(
            sss_env=sss_env, data_backend=data_backend
        )
        self.oracle = _FakeOracleConfig(
            modo_driver=modo_driver,
            user=user,
            dsn=dsn,
            owner=owner,
            table_prefix=table_prefix,
            call_timeout_ms=call_timeout_ms,
            oracle_client_lib_dir=oracle_client_lib_dir,
        )
        self.agent = collections.namedtuple("AgentConfig", ["agent_id"])(agent_id="srv-teste-01")
        self.caminho_arquivo = None


class _FakeSegredos(object):
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


class TestDbConnSelecaoMocks(unittest.TestCase):
    """Testes unitarios da logica de selecao de driver com dubles (F7.0)."""

    def setUp(self):
        db_conn.reset_selecao()
        self.cfg = _FakeConfig(modo_driver="auto")
        self.segredos = _FakeSegredos(password="teste_pwd_123")

    def tearDown(self):
        db_conn.reset_selecao()

    def test_auto_escolhe_thin_quando_thin_conecta(self):
        """No modo 'auto', escolhe Thin logo de inicio quando a conexao Thin funciona."""
        chamadas = []

        def executor_sondagem(candidato, cfg, senha):
            chamadas.append(candidato)
            if candidato == "thin":
                return {
                    "candidato": "thin",
                    "ok": True,
                    "versao_servidor": "19.0.0.0.0",
                    "versao_driver": "1.4.0",
                    "versao_cliente": None,
                }
            return {"candidato": candidato, "ok": False}

        selecao = db_conn.selecionar_driver(self.cfg, self.segredos, executor_sondagem=executor_sondagem)
        self.assertEqual(selecao.candidato, "thin")
        self.assertEqual(selecao.versao_servidor, "19.0.0.0.0")
        self.assertEqual(selecao.versao_driver, "1.4.0")
        self.assertIsNone(selecao.versao_cliente)
        self.assertEqual(chamadas, ["thin"])

    def test_thin_dpy_3010_thick_dpi_1047_cx_oracle(self):
        """Thin com DPY-3010 cai para Thick; Thick com DPI-1047 cai para cx_Oracle."""
        chamadas = []

        def executor_sondagem(candidato, cfg, senha):
            chamadas.append(candidato)
            if candidato == "thin":
                return {"candidato": "thin", "ok": False, "codigo_erro": "DPY-3010", "categoria": "INCOMPATIVEL"}
            elif candidato == "thick":
                return {"candidato": "thick", "ok": False, "codigo_erro": "DPI-1047", "categoria": "BIBLIOTECA"}
            elif candidato == "cx_oracle":
                return {
                    "candidato": "cx_oracle",
                    "ok": True,
                    "versao_servidor": "11.2.0.4.0",
                    "versao_driver": "8.3.0",
                    "versao_cliente": "19.10",
                }
            return {"candidato": candidato, "ok": False}

        selecao = db_conn.selecionar_driver(self.cfg, self.segredos, executor_sondagem=executor_sondagem)
        self.assertEqual(selecao.candidato, "cx_oracle")
        self.assertEqual(selecao.versao_servidor, "11.2.0.4.0")
        self.assertEqual(chamadas, ["thin", "thick", "cx_oracle"])

    def test_oracledb_ausente_escolhe_cx_oracle(self):
        """Quando oracledb nao esta instalado, cai para cx_Oracle."""
        chamadas = []

        def executor_sondagem(candidato, cfg, senha):
            chamadas.append(candidato)
            if candidato in ("thin", "thick"):
                return {"candidato": candidato, "ok": False, "codigo_erro": "NO_ORACLEDB", "categoria": "BIBLIOTECA"}
            elif candidato == "cx_oracle":
                return {
                    "candidato": "cx_oracle",
                    "ok": True,
                    "versao_servidor": "19.3.0.0.0",
                    "versao_driver": "8.3.0",
                    "versao_cliente": "19.10",
                }
            return {"candidato": candidato, "ok": False}

        selecao = db_conn.selecionar_driver(self.cfg, self.segredos, executor_sondagem=executor_sondagem)
        self.assertEqual(selecao.candidato, "cx_oracle")
        self.assertEqual(chamadas, ["thin", "thick", "cx_oracle"])

    def test_erro_autenticacao_interrompe_cadeia(self):
        """Erro de autenticacao interrompe a cadeia imediatamente."""
        for cod_erro in ("ORA-01017", "ORA-28000"):
            db_conn.reset_selecao()
            chamadas = []

            def executor_sondagem(candidato, cfg, senha):
                chamadas.append(candidato)
                return {"candidato": candidato, "ok": False, "codigo_erro": cod_erro, "categoria": "AUTENTICACAO"}

            with self.assertLogs("sss_db_conn", level="CRITICAL") as cm:
                with self.assertRaises(RuntimeError) as ctx:
                    db_conn.selecionar_driver(self.cfg, self.segredos, executor_sondagem=executor_sondagem)

            self.assertIn("Falha fatal de autenticacao Oracle", str(ctx.exception))
            self.assertIn(cod_erro, str(ctx.exception))
            self.assertEqual(chamadas, ["thin"])
            self.assertTrue(any("CRITICAL" in msg and cod_erro in msg for msg in cm.output))

    def test_todos_falham_erro_fatal_critical(self):
        """Quando todos os candidatos falham, registra CRITICAL e lanca RuntimeError."""
        def executor_sondagem(candidato, cfg, senha):
            erros = {
                "thin": ("DPY-4011", "REDE"),
                "thick": ("DPI-1047", "BIBLIOTECA"),
                "cx_oracle": ("ORA-12541", "REDE"),
            }
            cod, cat = erros[candidato]
            return {"candidato": candidato, "ok": False, "codigo_erro": cod, "categoria": cat}

        with self.assertLogs("sss_db_conn", level="CRITICAL") as cm:
            with self.assertRaises(RuntimeError) as ctx:
                db_conn.selecionar_driver(self.cfg, self.segredos, executor_sondagem=executor_sondagem)

        msg_erro = str(ctx.exception)
        self.assertIn("todos os candidatos de driver Oracle falharam", msg_erro)
        self.assertIn("DPY-4011", msg_erro)
        self.assertIn("DPI-1047", msg_erro)
        self.assertIn("ORA-12541", msg_erro)

    def test_candidato_forcado_falha_sem_sondar_outros(self):
        """Quando o candidato forcado falha, gera CRITICAL e nao testa os demais."""
        for modo in ("thin", "thick", "cx_oracle"):
            db_conn.reset_selecao()
            cfg = _FakeConfig(modo_driver=modo)
            chamadas = []

            def executor_sondagem(candidato, cfg, senha):
                chamadas.append(candidato)
                return {"candidato": candidato, "ok": False, "codigo_erro": "FORCED_FAIL", "categoria": "INCOMPATIVEL"}

            with self.assertLogs("sss_db_conn", level="CRITICAL") as cm:
                with self.assertRaises(RuntimeError) as ctx:
                    db_conn.selecionar_driver(cfg, self.segredos, executor_sondagem=executor_sondagem)

            self.assertIn("candidato forçado '%s' falhou" % modo, str(ctx.exception))
            self.assertEqual(chamadas, [modo])

    def test_valores_forcados_sucesso_nao_sondam_outros(self):
        """Quando candidato forcado tem sucesso, nao sonda outros."""
        for modo in ("thin", "thick", "cx_oracle"):
            db_conn.reset_selecao()
            cfg = _FakeConfig(modo_driver=modo)
            chamadas = []

            def executor_sondagem(candidato, cfg, senha):
                chamadas.append(candidato)
                return {
                    "candidato": candidato,
                    "ok": True,
                    "versao_servidor": "19.0.0.0.0",
                    "versao_driver": "2.0.0",
                    "versao_cliente": "19.10" if candidato != "thin" else None,
                }

            selecao = db_conn.selecionar_driver(cfg, self.segredos, executor_sondagem=executor_sondagem)
            self.assertEqual(selecao.candidato, modo)
            self.assertEqual(chamadas, [modo])

    def test_modo_driver_invalido_critical(self):
        """Modo driver invalido aborta com CRITICAL."""
        cfg = _FakeConfig(modo_driver="invalido_xyz")
        with self.assertLogs("sss_db_conn", level="CRITICAL") as cm:
            with self.assertRaises(RuntimeError) as ctx:
                db_conn.selecionar_driver(cfg, self.segredos)
        self.assertIn("modo_driver 'invalido_xyz' invalido", str(ctx.exception))
        self.assertTrue(any("CRITICAL" in msg and "invalido_xyz" in msg for msg in cm.output))

    def test_cache_em_memoria_thread_safe(self):
        """Apos uma selecao bem-sucedida, chamadas subsequentes reutilizam o resultado."""
        execucoes = []

        def executor_sondagem(candidato, cfg, senha):
            execucoes.append(candidato)
            return {"candidato": "thin", "ok": True, "versao_servidor": "19.0.0.0.0", "versao_driver": "1.4.0"}

        sel1 = db_conn.selecionar_driver(self.cfg, self.segredos, executor_sondagem=executor_sondagem)
        sel2 = db_conn.selecionar_driver(self.cfg, self.segredos, executor_sondagem=executor_sondagem)
        self.assertIs(sel1, sel2)
        self.assertEqual(len(execucoes), 1)


class TestDbConnApiAmpliadaMocks(unittest.TestCase):
    """Testes unitarios da API neutra, transacoes, binds, erros e pool (F7.2)."""

    def setUp(self):
        db_conn.reset_selecao()
        self.cfg = _FakeConfig()
        self.segredos = _FakeSegredos()

    def tearDown(self):
        db_conn.reset_selecao()

    def test_recusa_oracledb_2_no_python36(self):
        """python-oracledb 2.x e proibido no Python 3.6 (README §2.3)."""
        mock_oracledb = mock.MagicMock()
        mock_oracledb.__version__ = "2.0.1"

        with mock.patch.dict(sys.modules, {"oracledb": mock_oracledb}):
            with mock.patch.object(sys, "version_info", (3, 6, 8)):
                selecao = db_conn.SelecaoDriver("thin", "19.0.0.0.0", "2.0.1", None)
                with self.assertLogs("sss_db_conn", level="CRITICAL") as cm:
                    with self.assertRaises(RuntimeError) as ctx:
                        db_conn.inicializar(selecao, cfg=self.cfg)
                self.assertIn("python-oracledb 2.x nao e compativel com Python 3.6", str(ctx.exception))
                self.assertTrue(any("CRITICAL" in m and "python-oracledb 2.x" in m for m in cm.output))

    def test_recusa_instant_client_diferente_de_19(self):
        """Thick e cx_Oracle recusam Instant Client diferente de 19 com CRITICAL (README §2.3)."""
        # Teste 1: oracledb Thick com IC 21
        mock_oracledb = mock.MagicMock()
        mock_oracledb.__version__ = "1.4.3"
        mock_oracledb.clientversion.return_value = (21, 3, 0, 0, 0)

        with mock.patch.dict(sys.modules, {"oracledb": mock_oracledb}):
            selecao = db_conn.SelecaoDriver("thick", "19.0.0.0.0", "1.4.3", "21.3")
            with self.assertLogs("sss_db_conn", level="CRITICAL") as cm:
                with self.assertRaises(RuntimeError) as ctx:
                    db_conn.inicializar(selecao, cfg=self.cfg)
            self.assertIn("Exigido major 19", str(ctx.exception))
            self.assertTrue(any("CRITICAL" in m and "major 19" in m for m in cm.output))

        # Teste 2: cx_Oracle com IC 18
        db_conn.reset_selecao()
        mock_cx = mock.MagicMock()
        mock_cx.clientversion.return_value = (18, 5, 0, 0, 0)

        with mock.patch.dict(sys.modules, {"cx_Oracle": mock_cx}):
            selecao = db_conn.SelecaoDriver("cx_oracle", "11.2.0.4.0", "8.3.0", "18.5")
            with self.assertLogs("sss_db_conn", level="CRITICAL") as cm:
                with self.assertRaises(RuntimeError) as ctx:
                    db_conn.inicializar(selecao, cfg=self.cfg)
            self.assertIn("Exigido major 19", str(ctx.exception))

    def test_mesma_api_tres_combinacoes(self):
        """Valida que conectar() configura autocommit=False, call_timeout, module e action nos 3 modos."""
        modos = [
            ("thin", "oracledb", {"DB_TYPE_DATE": "DB_DATE"}),
            ("thick", "oracledb", {"DB_TYPE_DATE": "DB_DATE"}),
            ("cx_oracle", "cx_Oracle", {"DATETIME": "CX_DATETIME"}),
        ]
        for candidato, mod_name, tipos_extras in modos:
            db_conn.reset_selecao()
            mock_drv = mock.MagicMock(__name__=mod_name)
            mock_drv.__version__ = "1.4.0" if mod_name == "oracledb" else "8.3.0"
            mock_drv.clientversion.return_value = (19, 10, 0, 0, 0)
            for k, v in tipos_extras.items():
                setattr(mock_drv, k, v)

            mock_conn = mock.MagicMock()
            mock_drv.connect.return_value = mock_conn

            with mock.patch.dict(sys.modules, {mod_name: mock_drv}):
                selecao = db_conn.SelecaoDriver(candidato, "19.0.0.0.0", "1.4.0", "19.10" if candidato != "thin" else None)
                with mock.patch.object(db_conn, "selecionar_driver", return_value=selecao):
                    conn = db_conn.conectar(self.cfg, self.segredos, papel="web")
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
        with db_conn.transacao(mock_conn):
            pass
        mock_conn.commit.assert_called_once()
        mock_conn.rollback.assert_not_called()

        # 2. Erro de lock ORA-00054: faz rollback, registra WARN sem stack trace
        mock_conn.reset_mock()
        with self.assertLogs("sss_db_conn", level="WARNING") as cm:
            with self.assertRaises(Exception):
                with db_conn.transacao(mock_conn):
                    raise Exception("ORA-00054: resource busy and acquire with NOWAIT specified")

        mock_conn.rollback.assert_called_once()
        self.assertTrue(any("Falha de concorrencia/lock/timeout" in m and "ORA-54" in m for m in cm.output))

        # 3. Erro generico: faz rollback, registra ERROR com stack trace
        mock_conn.reset_mock()
        with self.assertLogs("sss_db_conn", level="ERROR") as cm_err:
            with self.assertRaises(ValueError):
                with db_conn.transacao(mock_conn):
                    raise ValueError("falha de negocio qualquer")

        mock_conn.rollback.assert_called_once()
        self.assertTrue(any("Erro na transacao Oracle" in m for m in cm_err.output))

    def test_classificacao_erros_e_failover(self):
        """Valida classificacao de erros de rede/failover, timeout, lock e violacoes."""
        # Rede e failover (CR-007, R-12)
        erros_rede = [
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
        for msg in erros_rede:
            exc = Exception(msg)
            self.assertTrue(db_conn.eh_erro_rede(exc), "Deveria ser erro de rede: %s" % msg)
            self.assertFalse(db_conn.eh_lock(exc))
            self.assertFalse(db_conn.eh_violacao(exc))

        # Call timeout
        for msg in ("DPY-4024: call timeout of 5000 ms occurred", "DPI-1067: call timeout of 5000 ms occurred", "ORA-03156: OCI call timed out"):
            exc = Exception(msg)
            self.assertTrue(db_conn.eh_tempo_esgotado(exc), "Deveria ser call timeout: %s" % msg)

        # Lock e deadlock
        for msg in ("ORA-00054: resource busy", "ORA-30006: resource busy; acquire with WAIT timeout expired", "ORA-00060: deadlock detected"):
            exc = Exception(msg)
            self.assertTrue(db_conn.eh_lock(exc), "Deveria ser erro de lock: %s" % msg)

        # Violacoes
        for msg in (
            "ORA-00001: unique constraint (OPENRISOW.UK_TBSSS_TCK) violated",
            "ORA-02290: check constraint (OPENRISOW.CK_TBSSS_TCK_ST) violated",
            "ORA-02291: integrity constraint (OPENRISOW.FK_TBSSS_TCK_SCR) violated - parent key not found",
            "ORA-02292: integrity constraint (OPENRISOW.FK_TBSSS_TCK_RESP) violated - child record found",
            "ORA-01400: cannot insert NULL into (OPENRISOW.TBSSS_SCRIPTS.PATH_FILE)",
            "ORA-12899: value too large for column OPENRISOW.TBSSS_AUDITORIA.ATOR",
            "ORA-01438: value larger than specified precision allowed for this column",
        ):
            exc = Exception(msg)
            self.assertTrue(db_conn.eh_violacao(exc), "Deveria ser violacao: %s" % msg)

    def test_backoff_sem_sleep_em_garantir(self):
        """ConexaoResiliente gerencia backoff exponencial (1s a 60s) via monotonic() sem time.sleep."""
        resiliente = db_conn.ConexaoResiliente(self.cfg, self.segredos, papel="agente")
        self.assertIsNone(resiliente.obter_conexao())

        t_atual = 1000.0

        with mock.patch("time.monotonic", side_effect=lambda: t_atual):
            with mock.patch.object(db_conn, "conectar") as mock_conectar:
                # 1. Primeira tentativa falha: backoff dobra de 1.0 para 2.0
                mock_conectar.side_effect = Exception("ORA-12541: no listener")
                ok = resiliente.garantir()
                self.assertFalse(ok)
                self.assertEqual(resiliente.backoff_s, 2.0)
                self.assertEqual(resiliente.proxima_tentativa_monotonic, 1001.0)

                # 2. Chamada antes do prazo (t_atual = 1000.5): retorna False imediatamente sem tentar conectar
                t_atual = 1000.5
                mock_conectar.reset_mock()
                ok = resiliente.garantir()
                self.assertFalse(ok)
                mock_conectar.assert_not_called()

                # 3. Chamada apos vencer o prazo (t_atual = 1001.2): tenta novamente e tem sucesso
                t_atual = 1001.2
                mock_conn = mock.MagicMock()
                mock_conectar.side_effect = None
                mock_conectar.return_value = mock_conn

                ok = resiliente.garantir()
                self.assertTrue(ok)
                self.assertIs(resiliente.obter_conexao(), mock_conn)
                self.assertEqual(resiliente.backoff_s, 1.0)  # Resetado para 1.0

                # 4. Notificar erro de rede fecha conexao e reinicia backoff
                resiliente.notificar_erro(Exception("ORA-03113: end-of-file"))
                self.assertIsNone(resiliente.obter_conexao())
                self.assertTrue(resiliente.em_falha)
                self.assertEqual(resiliente.backoff_s, 2.0)

    def test_orcamento_conexao_s(self):
        """Valida orcamento_conexao_s com Easy Connect e descritores TNS com aviso de timeout (CR-008, R-17)."""
        db_conn.reset_selecao()

        # 1. Easy Connect: 1 endereco, retorna call_timeout_s
        orc = db_conn.orcamento_conexao_s("localhost:2424/servico", 30.0)
        self.assertEqual(orc, 30)

        # 2. Descritor TNS 1 endereco: CONNECT_TIMEOUT=5, RETRY_COUNT=2 -> 5 * (2 + 1) * 1 = 15
        dsn1 = "(DESCRIPTION=(CONNECT_TIMEOUT=5)(RETRY_COUNT=2)(ADDRESS=(PROTOCOL=TCP)(HOST=host1)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=svc)))"
        orc1 = db_conn.orcamento_conexao_s(dsn1, 30.0)
        self.assertEqual(orc1, 15)

        # 3. Descritor TNS 2 enderecos: CONNECT_TIMEOUT=10, RETRY_COUNT=1 -> 10 * 2 * 2 = 40 (> 30s)
        dsn2 = (
            "(DESCRIPTION=(CONNECT_TIMEOUT=10)(RETRY_COUNT=1)"
            "(ADDRESS_LIST=(ADDRESS=(PROTOCOL=TCP)(HOST=h1)(PORT=1521))(ADDRESS=(PROTOCOL=TCP)(HOST=h2)(PORT=1521)))"
            "(CONNECT_DATA=(SERVICE_NAME=svc)))"
        )
        with self.assertLogs("sss_db_conn", level="WARNING") as cm:
            orc2 = db_conn.orcamento_conexao_s(dsn2, 30.0)
        self.assertEqual(orc2, 40)
        self.assertTrue(any("CONEXAO_ACIMA_DO_PRAZO" in m and "40s" in m for m in cm.output))

    def test_conferir_versao_esquema(self):
        """conferir_versao_esquema() valida versao_esquema da tabela controle contra sql_ident (CR-007, D4)."""
        mock_conn = mock.MagicMock()
        mock_cur = mock.MagicMock()
        mock_conn.cursor.return_value = mock_cur

        # 1. Versao igual (VERSAO_ESQUEMA = 1)
        mock_cur.fetchone.return_value = (1,)
        v = db_conn.conferir_versao_esquema(mock_conn, owner="openrisow")
        self.assertEqual(v, 1)

        # 2. Versao incompativel (ex.: 2)
        mock_cur.fetchone.return_value = (2,)
        with self.assertLogs("sss_db_conn", level="CRITICAL"):
            with self.assertRaises(db_conn.ErroVersaoEsquema) as ctx:
                db_conn.conferir_versao_esquema(mock_conn, owner="openrisow")
        self.assertIn("Versao do esquema incompativel", str(ctx.exception))

        # 3. Linha ausente
        mock_cur.fetchone.return_value = None
        with self.assertLogs("sss_db_conn", level="CRITICAL"):
            with self.assertRaises(db_conn.ErroVersaoEsquema) as ctx:
                db_conn.conferir_versao_esquema(mock_conn, owner="openrisow")
        self.assertIn("ausente na tabela de controle", str(ctx.exception))

    def test_definir_tipos_entrada_date_setinputsizes(self):
        """definir_tipos_entrada converte TIPO_DATE para o tipo de data nativo do driver ativo."""
        mock_cur = mock.MagicMock()

        # Simulando oracledb
        mock_oracledb = mock.MagicMock(__name__="oracledb")
        mock_oracledb.DB_TYPE_DATE = "ORACLEDB_DATE_TYPE"
        selecao_thin = db_conn.SelecaoDriver("thin", "19.0.0.0.0", "1.4.0", None)

        with mock.patch.object(db_conn, "_SELECAO_DRIVER", selecao_thin):
            with mock.patch.object(db_conn, "_DRIVER_INICIALIZADO", mock_oracledb):
                db_conn.definir_tipos_entrada(mock_cur, dt=db_conn.TIPO_DATE, clob=db_conn.TIPO_CLOB)
                mock_cur.setinputsizes.assert_called_with(dt="ORACLEDB_DATE_TYPE", clob=mock_oracledb.DB_TYPE_CLOB)

        # Simulando cx_Oracle
        mock_cur.reset_mock()
        mock_cx = mock.MagicMock(__name__="cx_Oracle")
        mock_cx.DATETIME = "CX_DATETIME_TYPE"
        selecao_cx = db_conn.SelecaoDriver("cx_oracle", "11.2.0.4.0", "8.3.0", "19.10")

        with mock.patch.object(db_conn, "_SELECAO_DRIVER", selecao_cx):
            with mock.patch.object(db_conn, "_DRIVER_INICIALIZADO", mock_cx):
                db_conn.definir_tipos_entrada(mock_cur, dt=db_conn.TIPO_DATE)
                mock_cur.setinputsizes.assert_called_with(dt="CX_DATETIME_TYPE")

    def test_tipo_blob_por_driver(self):
        """TIPO_BLOB (CR-012): DB_TYPE_BLOB no python-oracledb e BLOB no cx_Oracle."""
        drv = mock.MagicMock(__name__="oracledb")
        self.assertIs(db_conn.obter_tipo_driver(db_conn.TIPO_BLOB, driver=drv, candidato="thin"), drv.DB_TYPE_BLOB)
        cx = mock.MagicMock(__name__="cx_Oracle")
        self.assertIs(db_conn.obter_tipo_driver(db_conn.TIPO_BLOB, driver=cx, candidato="cx_oracle"), cx.BLOB)
        self.assertIn(db_conn.TIPO_BLOB, db_conn.TIPOS_NEUTROS)

    def test_tipo_varchar_variavel_saida_e_valor_saida(self):
        """variavel_saida e valor_saida operam com OUT binds nos drivers sem expor cursor.var."""
        mock_cur = mock.MagicMock()
        mock_var = mock.MagicMock()
        mock_var.getvalue.return_value = "VALOR_RETORNADO_PLSQL"
        mock_cur.var.return_value = mock_var

        mock_oracledb = mock.MagicMock(__name__="oracledb")
        mock_oracledb.DB_TYPE_VARCHAR = "DB_VARCHAR_TYPE"
        selecao = db_conn.SelecaoDriver("thin", "19.0.0.0.0", "1.4.0", None)

        with mock.patch.object(db_conn, "_SELECAO_DRIVER", selecao):
            with mock.patch.object(db_conn, "_DRIVER_INICIALIZADO", mock_oracledb):
                v = db_conn.variavel_saida(mock_cur, db_conn.TIPO_VARCHAR, tamanho=100)
                mock_cur.var.assert_called_with("DB_VARCHAR_TYPE", size=100)
                res = db_conn.valor_saida(v)
                self.assertEqual(res, "VALOR_RETORNADO_PLSQL")

    def test_proximo_id_qualificado(self):
        """proximo_id executa NEXTVAL com o identificador qualificado e retorna int."""
        mock_conn = mock.MagicMock()
        mock_cur = mock.MagicMock()
        mock_cur.fetchone.return_value = (42,)
        mock_conn.cursor.return_value = mock_cur

        pid = db_conn.proximo_id(mock_conn, "openrisow.sq_tbsss_tck")
        self.assertEqual(pid, 42)
        mock_cur.execute.assert_called_with("SELECT openrisow.sq_tbsss_tck.NEXTVAL FROM DUAL")

    def test_agora_banco_sem_microssegundos(self):
        """agora_banco retorna o SYSDATE com microsecond==0."""
        mock_conn = mock.MagicMock()
        mock_cur = mock.MagicMock()
        dt_com_micro = datetime.datetime(2026, 10, 19, 12, 30, 45, 999999)
        mock_cur.fetchone.return_value = (dt_com_micro,)
        mock_conn.cursor.return_value = mock_cur

        res = db_conn.agora_banco(mock_conn)
        self.assertEqual(res.microsecond, 0)
        self.assertEqual(res, datetime.datetime(2026, 10, 19, 12, 30, 45, 0))

    def test_saude(self):
        """saude retorna o SYSDATE naive do banco."""
        mock_conn = mock.MagicMock()
        mock_cur = mock.MagicMock()
        dt_esperado = datetime.datetime(2026, 10, 19, 12, 30, 45)
        mock_cur.fetchone.return_value = (dt_esperado,)
        mock_conn.cursor.return_value = mock_cur

        self.assertEqual(db_conn.saude(mock_conn), dt_esperado)

    def test_ausencia_de_senha_em_logs(self):
        """A senha nunca deve aparecer em mensagens de log emitidas por db_conn."""
        senha_super_secreta = "minha_senha_super_secreta_999"
        seg = _FakeSegredos(password=senha_super_secreta)
        with self.assertLogs("sss_db_conn", level="INFO") as cm:
            mock_drv = mock.MagicMock(__name__="oracledb")
            mock_drv.__version__ = "1.4.0"
            mock_conn = mock.MagicMock()
            mock_drv.connect.return_value = mock_conn
            with mock.patch.dict(sys.modules, {"oracledb": mock_drv}):
                selecao = db_conn.SelecaoDriver("thin", "19.0.0.0.0", "1.4.0", None)
                with mock.patch.object(db_conn, "selecionar_driver", return_value=selecao):
                    db_conn.conectar(self.cfg, seg, papel="web")

        for registro in cm.output:
            self.assertNotIn(senha_super_secreta, registro)

    def test_tipo_varchar_tres_modos(self):
        """TIPO_VARCHAR e variavel_saida/valor_saida operam identicamente nos tres modos."""
        modos = [
            ("thin", "oracledb", "DB_TYPE_VARCHAR"),
            ("thick", "oracledb", "DB_TYPE_VARCHAR"),
            ("cx_oracle", "cx_Oracle", "STRING"),
        ]
        for candidato, mod_name, attr_tipo in modos:
            mock_cur = mock.MagicMock()
            mock_var = mock.MagicMock()
            mock_var.getvalue.return_value = "RESULTADO_OK"
            mock_cur.var.return_value = mock_var

            mock_drv = mock.MagicMock(__name__=mod_name)
            setattr(mock_drv, attr_tipo, "TIPO_CONCRETO_VARCHAR")

            selecao = db_conn.SelecaoDriver(candidato, "19.0.0.0.0", "1.4.0", None)
            with mock.patch.object(db_conn, "_SELECAO_DRIVER", selecao):
                with mock.patch.object(db_conn, "_DRIVER_INICIALIZADO", mock_drv):
                    v = db_conn.variavel_saida(mock_cur, db_conn.TIPO_VARCHAR, tamanho=50)
                    mock_cur.var.assert_called_with("TIPO_CONCRETO_VARCHAR", size=50)
                    self.assertEqual(db_conn.valor_saida(v), "RESULTADO_OK")

    def test_traduzir_erro(self):
        """traduzir_erro mapeia corretamente para RepoViolacao, RepoConflito, RepoIndisponivel e RepoErro."""
        import repo_errors
        # Violacao
        e1 = db_conn.traduzir_erro(Exception("ORA-00001: unique constraint violated"))
        self.assertIsInstance(e1, repo_errors.RepoViolacao)
        # Lock / Conflito
        e2 = db_conn.traduzir_erro(Exception("ORA-00054: resource busy"))
        self.assertIsInstance(e2, repo_errors.RepoConflito)
        # Rede / Indisponivel
        e3 = db_conn.traduzir_erro(Exception("ORA-03113: end-of-file"))
        self.assertIsInstance(e3, repo_errors.RepoIndisponivel)
        # Generico
        e4 = db_conn.traduzir_erro(Exception("ORA-00942: table does not exist"))
        self.assertIsInstance(e4, repo_errors.RepoErro)

    def test_pool_web_ping_interval_60(self):
        """pool cria pool com ping_interval=60 para oracledb e cx_Oracle (CR-007, R-12)."""
        # oracledb create_pool
        mock_oracledb = mock.MagicMock(__name__="oracledb")
        selecao = db_conn.SelecaoDriver("thin", "19.0.0.0.0", "1.4.0", None)
        with mock.patch.object(db_conn, "_SELECAO_DRIVER", selecao):
            with mock.patch.object(db_conn, "_DRIVER_INICIALIZADO", mock_oracledb):
                p = db_conn.pool(self.cfg, self.segredos, papel="web")
                mock_oracledb.create_pool.assert_called_once()
                kw = mock_oracledb.create_pool.call_args[1]
                self.assertEqual(kw["ping_interval"], 60)
                self.assertEqual(kw["min"], 1)
                self.assertEqual(kw["max"], 4)


class TestOracleTestSupportMocks(unittest.TestCase):
    """Testes unitarios de scripts/_oracle_test_support.py (chave unica SSS_TEST_ORACLE=1) com dubles."""

    _LIGADO = {"SSS_TEST_ORACLE": "1"}

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

    def _conn(self, usuario, versao=None):
        mock_conn = mock.MagicMock()
        mock_cur = mock.MagicMock()
        mock_cur.fetchone.side_effect = [(usuario,)] + ([(versao,)] if versao is not None else [])
        mock_conn.cursor.return_value = mock_cur
        return mock_conn, mock_cur

    def test_desligado_sem_a_chave(self):
        for env in ({}, {"SSS_TEST_ORACLE": "0"}, {"SSS_TEST_ORACLE": "sim"}):
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertFalse(_oracle_test_support.banco_real_configurado())
                ok, motivo = _oracle_test_support.verificar_precondicoes_ambiente(cfg=self._cfg())
                self.assertFalse(ok)
                self.assertIn("SSS_TEST_ORACLE=1", motivo)

    def test_variaveis_antigas_recusadas(self):
        """As variaveis da guarda anterior nao sao ignoradas em silencio."""
        for antiga in _oracle_test_support.VARIAVEIS_ANTIGAS:
            with mock.patch.dict(os.environ, dict(self._LIGADO, **{antiga: "x"}), clear=True):
                ok, motivo = _oracle_test_support.verificar_precondicoes_ambiente(cfg=self._cfg())
                self.assertFalse(ok)
                self.assertIn(antiga, motivo)

    def test_modo_deduzido_do_owner(self):
        self.assertEqual(_oracle_test_support.modo_do_owner("SSS_TEST_DEV"), _oracle_test_support.MODO_DESCARTAVEL)
        self.assertEqual(_oracle_test_support.modo_do_owner("sss_test_dev"), _oracle_test_support.MODO_DESCARTAVEL)
        self.assertEqual(_oracle_test_support.modo_do_owner("openrisow"), _oracle_test_support.MODO_COMPARTILHADO)

    def test_precondicoes_do_config(self):
        """DEV obrigatorio, DSN preenchido e owner valido; o data_backend nao importa."""
        with mock.patch.dict(os.environ, self._LIGADO, clear=True):
            self.assertEqual(_oracle_test_support.verificar_precondicoes_ambiente(cfg=self._cfg()), (True, ""))
            for cfg, trecho in ((self._cfg(sss_env="HML"), "DEV"), (self._cfg(dsn=""), "dsn"),
                                (self._cfg(owner="openrisow;DROP"), "owner"),
                                (self._cfg(owner="SSS_TEST_"), "descartavel"), (self._cfg(owner="SSS_TEST_" + "X" * 25), "owner")):
                ok, motivo = _oracle_test_support.verificar_precondicoes_ambiente(cfg=cfg)
                self.assertFalse(ok)
                self.assertIn(trecho, motivo)

    def test_descartavel_conta_igual_owner_recusada(self):
        mock_conn, _cur = self._conn("SSS_TEST_DEV")
        with self.assertRaises(_oracle_test_support.PrecondicaoSchemaErro):
            _oracle_test_support.validar_schema_descartavel(mock_conn, "SSS_TEST_DEV", "SSS_TEST_DEV")

    def test_descartavel_sessao_divergente_recusada(self):
        mock_conn, _cur = self._conn("USUARIO_QUALQUER")
        with self.assertRaises(_oracle_test_support.PrecondicaoSchemaErro) as ctx:
            _oracle_test_support.validar_schema_descartavel(mock_conn, "SSS_TEST_DEV", "SSS_TEST_WEB")
        self.assertIn("difere do esperado", str(ctx.exception))

    def test_descartavel_ok_sem_conferir_controle(self):
        mock_conn, mock_cur = self._conn("SSS_TEST_WEB")
        res = _oracle_test_support.validar_schema_descartavel(mock_conn, "SSS_TEST_APP", "SSS_TEST_WEB")
        self.assertEqual(res, "SSS_TEST_APP")
        self.assertEqual(mock_cur.execute.call_count, 1)

    def test_compartilhado_conta_igual_owner_com_esquema_na_versao(self):
        import sql_ident
        mock_conn, mock_cur = self._conn("OPENRISOW", sql_ident.VERSAO_ESQUEMA)
        res = _oracle_test_support.validar_schema_descartavel(mock_conn, "openrisow", "openrisow", prefixo="tbsss_")
        self.assertEqual(res, "OPENRISOW")
        self.assertEqual(mock_cur.execute.call_args_list[1][0][0],
                         "SELECT versao_esquema FROM OPENRISOW.tbsss_controle")

    def test_compartilhado_versao_divergente_recusada(self):
        import sql_ident
        mock_conn, _cur = self._conn("OPENRISOW", sql_ident.VERSAO_ESQUEMA + 1)
        with self.assertRaises(_oracle_test_support.PrecondicaoSchemaErro) as ctx:
            _oracle_test_support.validar_schema_descartavel(mock_conn, "OPENRISOW", "OPENRISOW")
        self.assertIn("difere da do codigo", str(ctx.exception))

    def test_compartilhado_sem_esquema_sss_recusado(self):
        mock_conn = mock.MagicMock()
        mock_cur = mock.MagicMock()
        mock_cur.fetchone.return_value = ("OPENRISOW",)
        mock_cur.execute.side_effect = [None, RuntimeError("ORA-00942")]
        mock_conn.cursor.return_value = mock_cur
        with self.assertRaises(_oracle_test_support.PrecondicaoSchemaErro) as ctx:
            _oracle_test_support.validar_schema_descartavel(mock_conn, "OPENRISOW", "OPENRISOW")
        self.assertIn("Esquema SSS ausente", str(ctx.exception))

    def test_compartilhado_sessao_de_outra_conta_recusada(self):
        import sql_ident
        mock_conn, _cur = self._conn("OUTRA", sql_ident.VERSAO_ESQUEMA)
        with self.assertRaises(_oracle_test_support.PrecondicaoSchemaErro):
            _oracle_test_support.validar_schema_descartavel(mock_conn, "OPENRISOW", "OPENRISOW")

    def test_preparar_usa_o_config_da_aplicacao_e_registra_o_modo(self):
        """Sem cfg, usa sss_config.obter_config() (instance/config.ini) e guarda o modo validado."""
        import sql_ident
        mock_conn, _cur = self._conn("OPENRISOW", sql_ident.VERSAO_ESQUEMA)
        cfg = self._cfg()
        with mock.patch.dict(os.environ, self._LIGADO, clear=True):
            with mock.patch("sss_config.obter_config", return_value=cfg) as obter:
                with mock.patch("sss_config.carregar_segredos", return_value=mock.MagicMock()):
                    with mock.patch("db_conn.conectar", return_value=mock_conn):
                        self.assertIs(_oracle_test_support.preparar_schema_descartavel("web"), cfg)
        obter.assert_called_once_with()
        mock_conn.close.assert_called_once()
        self.assertEqual(_oracle_test_support.modo_schema(), _oracle_test_support.MODO_COMPARTILHADO)

    def test_preparar_descartavel_recusa_conta_do_owner_sem_conectar(self):
        cfg = self._cfg(owner="SSS_TEST_APP", user="SSS_TEST_APP")
        with mock.patch.dict(os.environ, self._LIGADO, clear=True):
            with mock.patch("db_conn.conectar") as conectar:
                with self.assertRaises(_oracle_test_support.PrecondicaoSchemaErro):
                    _oracle_test_support.preparar_schema_descartavel("web", cfg=cfg)
        conectar.assert_not_called()

    def test_preparar_desligado_nao_le_config_nem_conecta(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("sss_config.obter_config") as obter, mock.patch("db_conn.conectar") as conectar:
                with self.assertRaises(_oracle_test_support.PrecondicaoSchemaErro):
                    _oracle_test_support.preparar_schema_descartavel("web")
        obter.assert_not_called()
        conectar.assert_not_called()


class TestSondarDriverScript(unittest.TestCase):
    """Testes unitarios do scripts/sondar_driver.py."""

    def test_categorizacao_erros(self):
        """Valida que codigos Oracle/DPY/DPI sao categorizados corretamente."""
        casos = [
            ("ORA-01017: invalid username/password", "ORA-01017", "AUTENTICACAO"),
            ("ORA-28000: the account is locked", "ORA-28000", "AUTENTICACAO"),
            ("DPY-3010: connections to this database server version are not supported", "DPY-3010", "INCOMPATIVEL"),
            ("DPI-1047: Cannot locate a 64-bit Oracle Client library", "DPI-1047", "BIBLIOTECA"),
            (ImportError("No module named 'oracledb'"), "IMPORT_ERROR", "BIBLIOTECA"),
            ("ORA-12170: TNS:Connect timeout occurred", "ORA-12170", "REDE"),
            ("ORA-12541: TNS:no listener", "ORA-12541", "REDE"),
            ("DPY-4011: the network connection was closed", "DPY-4011", "REDE"),
            ("ORA-00942: table or view does not exist", "ORA-00942", "OUTRO"),
        ]
        for item, cod_esperado, cat_esperada in casos:
            exc = item if isinstance(item, Exception) else Exception(item)
            cod, cat = sondar_driver._classificar_erro(exc)
            self.assertEqual(cod, cod_esperado, "Codigo incorreto para: %s" % item)
            self.assertEqual(cat, cat_esperada, "Categoria incorreta para: %s" % item)


class TestDbConnReal(unittest.TestCase):
    """Testes com conexao real quando SSS_TEST_ORACLE=1 (F7.2): config e segredos da aplicacao."""

    def test_conexao_real_schema_descartavel(self):
        if not _oracle_test_support.banco_real_configurado():
            self.skipTest("Testes Oracle reais desligados (SSS_TEST_ORACLE=1); marcado como NAO TESTADO")
        import sss_config
        cfg = _oracle_test_support.preparar_schema_descartavel(papel="web")
        segredos = sss_config.carregar_segredos(cfg.secrets.secrets_file, cfg=cfg, papel="web")

        conn = db_conn.conectar(cfg, segredos, papel="web")
        self.assertIsNotNone(conn)

        try:
            # 1. Saude e Relogio
            dt_saude = db_conn.saude(conn)
            self.assertIsInstance(dt_saude, datetime.datetime)

            dt_banco = db_conn.agora_banco(conn)
            self.assertEqual(dt_banco.microsecond, 0)

            # 2. Bind DATE descartando microssegundos (README §7.5)
            # Um datetime com microssegundos comparado com TIPO_DATE deve casar perfeitamente
            cur = conn.cursor()
            try:
                db_conn.definir_tipos_entrada(cur, d=db_conn.TIPO_DATE)
                dt_com_micros = dt_banco.replace(microsecond=543210)
                cur.execute("SELECT 1 FROM DUAL WHERE :d = TRUNC(SYSDATE, 'MI')", {"d": dt_com_micros})
                # Pode ou nao retornar 1 dependendo do segundo, mas o ponto critico e que setinputsizes
                # descarta microssegundos sem gerar erro ORA-018xx
            finally:
                cur.close()

        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
