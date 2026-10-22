# -*- coding: utf-8 -*-
"""Testes do scripts/purge.py e do repo_oracle/purge.py (README §11.3; F9.1a; CR-005; CR-007 R-21, R-22, R-32;
CR-008 R-16, R-27; CR-009; CR-012).

Com um banco simulado em memoria (o SQL e o do RepoPurge real): lotes ate rowcount = 0, so tickets terminais,
concessao tomada, renovada, liberada (dono e prazo), negada e perdida, PURGE com 0 linhas, --export-audit,
--dry-run so com SELECT e um agora_banco(), logs locais pela data do caminho (RUNNING mantido, internal/ intocada),
pastas de saida pelo helper, trava local e codigos de saida.

Com SSS_TEST_ORACLE=1 (decisao 1a do F9.1): o purge real roda com a conta do owner e so quando nenhum ticket ou
linha de auditoria fora da fixture seria elegivel; senao o teste e pulado.
"""
import _testenv  # noqa: F401

import csv
import datetime
import io
import logging
import os
import re
import shutil
import tempfile
import types
import unittest
from unittest import mock

import os_platform
import purge as purge_cli  # scripts/purge.py (o repositorio e repo_oracle.purge)
from repo_oracle.purge import RepoPurge

NOW = datetime.datetime(2026, 10, 21, 3, 0, 0)
NS = types.SimpleNamespace
TERMINAL_STATUSES = ("SUCCESS", "FAILED", "CANCELLED")


def _cfg(root, **extra):
    agente = dict(agent_id="srv-a", work_dir=os.path.join(root, "work"), output_dir=None,
                  environments=("PRODUCAO",), exec_users=())
    agente.update(extra.get("agent", {}))
    return NS(app=NS(sss_env="DEV"), oracle=NS(owner="openrisow", table_prefix="tbsss_"),
              secrets=NS(secrets_file=os.path.join(root, "secrets.cfg")), agent=NS(**agente),
              logging=NS(log_dir=os.path.join(root, "logs"), local_log_retention_days=30, output_retention_days=7),
              retention=NS(ticket_retention_days=90, audit_retention_days=365, purge_batch_size=2,
                          purge_user=extra.get("purge_user", "sss_purge")))


class _Db(object):
    """Tickets, auditoria e tbsss_control em memoria, respondendo ao SQL do RepoPurge."""

    def __init__(self, tickets=(), audit=(), owner=None, until=None, running=()):
        self.tickets = [dict(id=i, created_at=c, status=s) for i, c, s in tickets]
        self.audit = [dict(id=i, created_at=c, actor="admin", source_ip="10.0.0.1", action="LOGIN",
                               entity="tbsss_users", entity_id=7, detail="d%d" % i) for i, c in audit]
        self.ctl = {"dono": owner, "ate": until}
        self.running = list(running)
        self.sqls = []
        self.commits = self.rollbacks = self.closed = 0
        self.seq = 1000
        self.steal_on_renewal = None  # n-esima tomada da concessao que outro no ganha
        self.taken = 0
        self.fail_at = None  # trecho de SQL que levanta erro
        self.pending = []  # (lista, linha) apagadas e ainda nao confirmadas


class _Cursor(object):

    def __init__(self, db):
        self.b = db
        self.rowcount = 0
        self._lines = []

    def setinputsizes(self, **_types):
        pass

    def close(self):
        pass

    def fetchone(self):
        return self._lines[0] if self._lines else None

    def fetchall(self):
        return list(self._lines)

    def _eligible(self, table, limit, batch=None):
        if table == "tickets":
            linhas = [t for t in self.b.tickets if t["created_at"] < limit and t["status"] in TERMINAL_STATUSES]
        else:
            linhas = [a for a in self.b.audit if a["created_at"] < limit]
        return linhas if batch is None else linhas[:batch]

    def execute(self, sql, binds=None):
        b, binds = self.b, binds or {}
        b.sqls.append(sql)
        if b.fail_at and b.fail_at in sql:
            raise RuntimeError("ORA-03113: end-of-file on communication channel")
        tabela = "tickets" if "tbsss_tickets" in sql else "audit"
        self._lines, self.rowcount = [], 0
        if sql == "SELECT SYSDATE FROM DUAL":
            self._lines = [(NOW.replace(microsecond=123),)]
        elif "NEXTVAL" in sql:
            b.seq += 1
            self._lines = [(b.seq,)]
        elif "purge_lease_until = SYSDATE + 1/24" in sql:
            b.taken += 1
            if b.steal_on_renewal == b.taken:
                b.ctl = {"dono": "srv-outro", "ate": NOW + datetime.timedelta(hours=1)}
            livre = b.ctl["ate"] is None or b.ctl["ate"] < NOW or b.ctl["dono"] == binds["owner"]
            if livre:
                b.ctl = {"dono": binds["owner"], "ate": NOW + datetime.timedelta(hours=1)}
            self.rowcount = int(livre)
        elif "SET purge_owner = NULL" in sql:
            if b.ctl["dono"] == binds["owner"]:
                b.ctl = {"dono": None, "ate": None}
                self.rowcount = 1
        elif sql.startswith("SELECT COUNT(*)"):
            self._lines = [(len(self._eligible(tabela, binds["cutoff"])),)]
        elif sql.startswith("DELETE") and "ROWNUM <= :batch_size" in sql:
            alvo = self._eligible(tabela, binds["cutoff"], binds["batch_size"])
            lista = b.tickets if tabela == "tickets" else b.audit
            for linha in alvo:
                lista.remove(linha)
                b.pending.append((lista, linha))
            self.rowcount = len(alvo)
        elif "FOR UPDATE" in sql:
            cols = ("id", "created_at", "actor", "source_ip", "action", "entity", "entity_id", "detail")
            self._lines = [tuple(a[c] for c in cols) for a in self._eligible("audit", binds["cutoff"],
                                                                                  binds["batch_size"])]
        elif sql.startswith("INSERT INTO"):
            b.audit.append(dict(binds, created_at=NOW, action="PURGE", source_ip=None, entity_id=None))
            self.rowcount = 1
        elif sql.startswith("SELECT t.environment"):
            self._lines = list(b.running)
        else:
            raise AssertionError("SQL inesperado: %s" % sql)

    def executemany(self, sql, binds):
        self.b.sqls.append(sql)
        ids = set(x["id"] for x in binds)
        for linha in [a for a in self.b.audit if a["id"] in ids]:
            self.b.audit.remove(linha)
            self.b.pending.append((self.b.audit, linha))
        self.rowcount = len(ids)


class _Conn(object):

    def __init__(self, db):
        self.b = db

    def cursor(self):
        return _Cursor(self.b)

    def commit(self):
        self.b.commits += 1
        self.b.pending = []

    def rollback(self):
        self.b.rollbacks += 1
        for lista, linha in self.b.pending:
            lista.append(linha)
        lista_ordem = sorted(self.b.tickets, key=lambda t: t["id"])
        self.b.tickets[:] = lista_ordem
        self.b.pending = []

    def close(self):
        self.b.closed += 1


class _Plat(object):
    """Plataforma dos testes: final_path real; helper de saida, trava e liberacao registrados."""

    def __init__(self, count=0, fail=False):
        self.calls = []
        self.count, self.fail = count, fail
        self.locks = []
        self.final_path = os_platform.final_path

    def purge_output(self, base, days, exec_user=None, count_only=False):
        self.calls.append((base, days, exec_user, count_only))
        if self.fail:
            raise RuntimeError("helper purge-output falhou (codigo 4)")
        return self.count

    def lock_instance(self, path):
        self.locks.append(path)
        return os_platform.lock_instance(path)

    def release_instance(self, lock):
        os_platform.release_instance(lock)


def _days(n):
    return NOW - datetime.timedelta(days=n)


class _Base(unittest.TestCase):

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="sss_test_purge_"))
        self.addCleanup(shutil.rmtree, self.root, True)
        os.mkdir(os.path.join(self.root, "work"))
        os.mkdir(os.path.join(self.root, "logs"))
        self.cfg = _cfg(self.root)
        self.log = logging.getLogger("sss_test_purge")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False

    def _purge(self, db, plat=None, cfg=None):
        return purge_cli.Purge(cfg or self.cfg, _Conn(db), plat=plat or _Plat(), logger=self.log)

    def _minute(self, rel, files=("ticket_1_100.log",)):
        pasta = os.path.join(self.cfg.logging.log_dir, *rel.split("/"))
        os.makedirs(pasta)
        for nome in files:
            with open(os.path.join(pasta, nome), "w") as f:
                f.write("x")
        return pasta

    def _purges(self, db):
        return [a for a in db.audit if a["action"] == "PURGE"]


class TestTables(_Base):

    def test_lotes_ate_rowcount_zero_e_so_terminais(self):
        velhos = [(i, _days(100), s) for i, s in enumerate(TERMINAL_STATUSES * 2, 1)][:5]
        banco = _Db(tickets=velhos + [(10, _days(100), "PENDING"), (11, _days(100), "RUNNING"),
                                         (12, _days(10), "SUCCESS")])
        p = self._purge(banco)
        self.assertEqual(p.run(("tickets",)), purge_cli.EXIT_OK)
        self.assertEqual(sorted(t["id"] for t in banco.tickets), [10, 11, 12], "nunca um ticket nao terminal")
        lotes = [s for s in banco.sqls if s.startswith("DELETE")]
        self.assertEqual(len(lotes), 4, "2 + 2 + 1 e o lote vazio")
        self.assertEqual(lotes[0], "DELETE FROM openrisow.tbsss_tickets WHERE created_at < :cutoff"
                                   " AND status IN ('SUCCESS','FAILED','CANCELLED') AND ROWNUM <= :batch_size")
        self.assertIn("tickets: 5 linhas apagadas", p.summary)

    def test_purge_auditado_por_tabela_inclusive_com_zero(self):
        banco = _Db(tickets=[(1, _days(100), "FAILED")], audit=[(50, _days(10))])
        self.assertEqual(self._purge(banco).run(("tickets", "audit")), 0)
        purges = self._purges(banco)
        self.assertEqual([(a["entity"], a["detail"], a["actor"], a["entity_id"]) for a in purges],
                         [("tbsss_tickets", "1 linhas", "SYSTEM:purge", None),
                          ("tbsss_audit", "0 linhas", "SYSTEM:purge", None)])
        self.assertEqual([a["id"] for a in banco.audit if a["action"] != "PURGE"], [50], "recente fica")

    def test_limite_calculado_uma_vez_pelo_banco(self):
        banco = _Db(tickets=[(1, NOW - datetime.timedelta(days=90, seconds=1), "SUCCESS"),
                                (2, NOW - datetime.timedelta(days=90), "SUCCESS")])
        self._purge(banco).run(("tickets",))
        self.assertEqual([t["id"] for t in banco.tickets], [2], "created_at < SYSDATE - dias, estrito")
        self.assertEqual(banco.sqls.count("SELECT SYSDATE FROM DUAL"), 1)

    def test_concessao_tomada_renovada_e_liberada(self):
        banco = _Db(tickets=[(i, _days(100), "SUCCESS") for i in range(1, 6)])
        self._purge(banco).run(("tickets",))
        tomadas = [s for s in banco.sqls if "purge_lease_until = SYSDATE + 1/24" in s]
        self.assertEqual(len(tomadas), 1 + 3, "tomada e uma renovacao por lote nao vazio")
        self.assertEqual(banco.ctl, {"dono": None, "ate": None}, "dono e prazo zerados (CR-008, R-27)")
        self.assertIn("UPDATE openrisow.tbsss_control SET purge_owner = NULL, purge_lease_until = NULL"
                      " WHERE id = 1 AND purge_owner = :owner", banco.sqls)

    def test_concessao_de_outro_no_pula_tabelas_sem_auditar(self):
        ate = NOW + datetime.timedelta(minutes=30)
        banco = _Db(tickets=[(1, _days(100), "SUCCESS")], owner="srv-b", until=ate)
        p = self._purge(banco)
        self.assertEqual(p.run(("tickets", "audit")), purge_cli.EXIT_OK)
        self.assertEqual(len(banco.tickets), 1)
        self.assertEqual(self._purges(banco), [], "sem a concessao, outro no audita a sua execucao")
        self.assertFalse([s for s in banco.sqls if s.startswith("DELETE")])
        self.assertEqual(banco.ctl, {"dono": "srv-b", "ate": ate}, "concessao alheia intocada")
        self.assertIn("tickets: pulado (outro no esta purgando)", p.summary)

    def test_concessao_vencida_de_outro_no_e_tomada(self):
        banco = _Db(tickets=[(1, _days(100), "SUCCESS")], owner="srv-b", until=NOW - datetime.timedelta(minutes=1))
        self.assertEqual(self._purge(banco).run(("tickets",)), 0)
        self.assertEqual(banco.tickets, [])

    def test_concessao_perdida_no_meio(self):
        banco = _Db(tickets=[(i, _days(100), "SUCCESS") for i in range(1, 6)])
        banco.steal_on_renewal = 3  # tomada, 1a renovacao, 2a renovacao perdida
        self.assertEqual(self._purge(banco).run(("tickets",)), purge_cli.EXIT_DATABASE)
        self.assertEqual(len(banco.tickets), 3, "o 2o lote foi desfeito")
        self.assertEqual(banco.ctl["dono"], "srv-outro", "a concessao de quem tomou fica")
        self.assertEqual(self._purges(banco), [])

    def test_falha_de_banco(self):
        banco = _Db(tickets=[(1, _days(100), "SUCCESS")])
        banco.fail_at = "DELETE FROM"
        self.assertEqual(self._purge(banco).run(("tickets",)), purge_cli.EXIT_DATABASE)
        self.assertGreaterEqual(banco.rollbacks, 1)
        self.assertEqual(banco.ctl, {"dono": None, "ate": None}, "liberada mesmo na falha")

    def test_exportar_auditoria(self):
        pasta = os.path.join(self.root, "arquivo")
        os.mkdir(pasta)
        banco = _Db(audit=[(1, _days(400)), (2, _days(400)), (3, _days(380)), (4, _days(10))])
        p = self._purge(banco)
        self.assertEqual(p.run(("audit",), export=pasta), 0)
        arquivos = os.listdir(pasta)
        self.assertEqual(arquivos, ["auditoria_purge_20261021_030000.csv"])
        caminho = os.path.join(pasta, arquivos[0])
        self.assertEqual(os.stat(caminho).st_mode & 0o777, 0o600)
        with io.open(caminho, encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.reader(f, delimiter=";"))
        self.assertEqual(linhas[0][0], u"ID")
        self.assertEqual([l[0] for l in linhas[1:]], ["1", "2", "3"])
        self.assertEqual([a["id"] for a in banco.audit if a["action"] != "PURGE"], [4])
        self.assertEqual(self._purges(banco)[0]["detail"], "3 linhas")
        self.assertFalse([s for s in banco.sqls if s.startswith("DELETE") and "ROWNUM" in s],
                         "com exportacao, apaga pelo id das linhas gravadas")


class TestDryRun(_Base):

    def test_so_select_um_agora_e_nada_alterado(self):
        antigo = self._minute("producao/carga/2026/01/10/03/00")
        plat = _Plat(count=4)
        cfg = _cfg(self.root, agent={"output_dir": os.path.join(self.root, "saida")})
        os.makedirs(os.path.join(self.root, "saida", "producao"))
        banco = _Db(tickets=[(1, _days(100), "SUCCESS"), (2, _days(100), "PENDING")],
                       audit=[(5, _days(400))])
        p = self._purge(banco, plat=plat, cfg=cfg)
        self.assertEqual(p.run(purge_cli.TARGETS, dry_run=True), 0)
        self.assertTrue(all(s.startswith("SELECT") for s in banco.sqls), banco.sqls)
        self.assertEqual(banco.sqls.count("SELECT SYSDATE FROM DUAL"), 1)
        self.assertTrue(any(s.startswith("SELECT t.environment") for s in banco.sqls), "RUNNING tambem no dry-run")
        self.assertEqual((banco.commits, len(banco.tickets), len(banco.audit)), (0, 2, 1))
        self.assertEqual(banco.ctl, {"dono": None, "ate": None})
        self.assertTrue(os.path.isdir(antigo))
        self.assertEqual(plat.calls, [(os.path.join(self.root, "saida", "producao"), 7, None, True)])
        self.assertEqual(p.summary, ["tickets: 1 linhas elegiveis (estimativa)",
                                    "audit: 1 linhas elegiveis (estimativa)",
                                    "local_logs: 1 pastas de minuto elegiveis (estimativa)",
                                    "output: 4 pastas de minuto elegiveis (estimativa)"])


class TestLocalLogs(_Base):

    def test_pela_data_do_caminho_com_running_mantido(self):
        velho = self._minute("producao/carga/2026/09/01/10/00", ("ticket_1_100.log", "ticket_2.log.parcial"))
        recente = self._minute("producao/carga/2026/10/20/10/00")
        running = self._minute("producao/extrator/2026/09/01/23/59", ("ticket_3.log.parcial",))
        sozinho = self._minute("homologacao/outro/2025/12/31/08/15")
        internal = self._minute("internal/app/2020/01/01/00/00", ("sss_web_1.log",))
        estranho = os.path.join(self.cfg.logging.log_dir, "producao", "carga", "2026", "09", "lixo")
        os.makedirs(estranho)
        fora = os.path.join(self.root, "fora", "2026", "01", "01", "00", "00")
        os.makedirs(fora)
        os.symlink(os.path.join(self.root, "fora"), os.path.join(self.cfg.logging.log_dir, "producao", "ligado"))
        banco = _Db(running=[("PRODUCAO", 9, datetime.datetime(2026, 9, 1, 23, 59, 30),
                                 '{"version": 5, "script_name": "Extrator"}')])
        p = self._purge(banco)
        self.assertEqual(p.run(("local_logs",)), 0)
        self.assertFalse(os.path.exists(velho), "pasta de minuto inteira, com o .log.parcial")
        self.assertFalse(os.path.exists(os.path.join(self.cfg.logging.log_dir, "producao", "carga", "2026", "09", "01")),
                         "hora e dia vazios removidos")
        self.assertTrue(os.path.isdir(estranho), "fora do formato e ignorado")
        self.assertTrue(os.path.isdir(recente))
        self.assertTrue(os.path.isdir(running), "log de ticket RUNNING mantido (CR-007, R-32)")
        self.assertFalse(os.path.exists(os.path.join(self.cfg.logging.log_dir, "homologacao")),
                         "vazias ate o ambiente")
        self.assertTrue(os.path.isdir(internal), "internal/ intocada (CR-009)")
        self.assertTrue(os.path.isdir(fora), "link nao e seguido")
        self.assertEqual(p.summary, ["local_logs: 2 pastas de minuto removidas"])

    def test_falha_na_remocao_sai_com_3(self):
        self._minute("producao/carga/2026/01/01/10/00")
        with mock.patch("log_paths.shutil.rmtree", side_effect=OSError(13, "Permission denied")):
            self.assertEqual(self._purge(_Db()).run(("local_logs",)), purge_cli.EXIT_LOCAL)

    def test_caminho_real_fora_de_log_dir_nao_e_removido(self):
        velho = self._minute("producao/carga/2026/01/01/10/00")
        plat = _Plat()
        plat.final_path = lambda c: "/outro" + c if c != self.cfg.logging.log_dir else c
        self.assertEqual(self._purge(_Db(), plat=plat).run(("local_logs",)), purge_cli.EXIT_LOCAL)
        self.assertTrue(os.path.isdir(velho))


class TestOutput(_Base):

    def test_por_ambiente_com_o_usuario_de_execucao(self):
        base = os.path.join(self.root, "saida")
        os.makedirs(os.path.join(base, "producao"))
        cfg = _cfg(self.root, agent={"output_dir": base, "environments": ("PRODUCAO", "HOMOLOGACAO"),
                                     "exec_users": (("PRODUCAO", "sssprd"), ("HOMOLOGACAO", "ssshml"))})
        plat = _Plat(count=2)
        p = self._purge(_Db(), plat=plat, cfg=cfg)
        self.assertEqual(p.run(("output",)), 0)
        self.assertEqual(plat.calls, [(os.path.join(base, "producao"), 7, "sssprd", False)],
                         "ambiente sem pasta e pulado")
        self.assertEqual(p.summary, ["output: 2 pastas de minuto removidas"])

    def test_desligada_e_falha(self):
        p = self._purge(_Db())
        self.assertEqual(p.run(("output",)), 0)
        self.assertEqual(p.summary, ["output: desligada (output_dir vazio)"])
        base = os.path.join(self.root, "saida")
        os.makedirs(os.path.join(base, "producao"))
        cfg = _cfg(self.root, agent={"output_dir": base})
        self.assertEqual(self._purge(_Db(), plat=_Plat(fail=True), cfg=cfg).run(("output",)),
                         purge_cli.EXIT_LOCAL)


class TestMain(_Base):
    """A linha de comando: configuracao, trava local, conexao e resumo no stdout."""

    def _main(self, argv, db=None, cfg=None, plat=None, secrets_error_flag=False):
        cfg = cfg or self.cfg
        db = db if db is not None else _Db()
        self.connections = []

        def conectar(_cfg, _secrets):
            self.connections.append(1)
            return _Conn(db)
        saida = io.StringIO()
        carregar = mock.Mock(side_effect=purge_cli.sss_config.ConfigError(reason="x") if secrets_error_flag else None,
                             return_value=object())
        with mock.patch.object(purge_cli.sss_config, "get_config", return_value=cfg), \
                mock.patch.object(purge_cli.sss_config, "load_secrets", carregar), \
                mock.patch.object(purge_cli.sss_logging, "configure", return_value=self.log), \
                mock.patch.object(purge_cli.masking, "install_filter_on_handlers"):
            codigo = purge_cli.main(argv, connect=conectar, plat=plat or _Plat(), output=saida)
        self.load = carregar
        return codigo, saida.getvalue()

    def test_execucao_real_com_trava_e_resumo(self):
        plat = _Plat()
        banco = _Db(tickets=[(1, _days(100), "CANCELLED")])
        codigo, texto = self._main(["--target", "tickets"], db=banco, plat=plat)
        self.assertEqual(codigo, 0)
        self.assertEqual(plat.locks, [os.path.join(self.root, "work", "sss-purge.lock")])
        self.assertEqual(texto, "tickets: 1 linhas apagadas\n")
        self.assertEqual(banco.closed, 1)
        self.assertEqual(self.load.call_args[1]["role"], "agent", "[purge] password so no papel agente")

    def test_dry_run_sem_trava_e_com_aviso(self):
        plat = _Plat()
        codigo, texto = self._main(["--dry-run", "--target", "audit"], plat=plat)
        self.assertEqual(codigo, 0)
        self.assertEqual(plat.locks, [])
        self.assertFalse(os.path.exists(os.path.join(self.root, "work", "sss-purge.lock")))
        self.assertIn("dry-run: contagens estimadas", texto)

    def test_outro_purge_no_servidor(self):
        trava = os_platform.lock_instance(os.path.join(self.root, "work", "sss-purge.lock"))
        self.addCleanup(os_platform.release_instance, trava)
        codigo, texto = self._main([])
        self.assertEqual((codigo, texto, self.connections), (0, "", []))

    def test_configuracao_invalida(self):
        with mock.patch.object(purge_cli.sss_config, "get_config",
                               side_effect=purge_cli.sss_config.ConfigError(reason="x")):
            self.assertEqual(purge_cli.main([], connect=None), purge_cli.EXIT_CONFIG)
        self.assertEqual(self._main([], cfg=_cfg(self.root, purge_user=None))[0], purge_cli.EXIT_CONFIG)
        self.assertEqual(self._main(["--export-audit", os.path.join(self.root, "nao_existe")])[0],
                         purge_cli.EXIT_CONFIG)
        self.assertEqual(self._main([], secrets_error_flag=True)[0], purge_cli.EXIT_CONFIG)
        self.assertEqual(self.connections, [])

    def test_falha_ao_conectar(self):
        with mock.patch.object(purge_cli.sss_config, "get_config", return_value=self.cfg), \
                mock.patch.object(purge_cli.sss_config, "load_secrets", return_value=object()), \
                mock.patch.object(purge_cli.sss_logging, "configure", return_value=self.log), \
                mock.patch.object(purge_cli.masking, "install_filter_on_handlers"):
            codigo = purge_cli.main([], connect=mock.Mock(side_effect=RuntimeError("ORA-12541: no listener")),
                                    plat=_Plat(), output=io.StringIO())
        self.assertEqual(codigo, purge_cli.EXIT_DATABASE)

    def test_alvo_invalido(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
            purge_cli._arguments(["--target", "tudo"])


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestPurgeOracle(unittest.TestCase):
    """Purge real contra o Oracle (decisao 1a): conta do owner, so quando nada fora da fixture e elegivel."""

    DAYS = 30  # retencao dos tickets no teste; a auditoria usa o minimo, 365

    @classmethod
    def setUpClass(cls):
        import test_repo_contract as trc
        cls.trc = trc
        cls.contrato = trc._OracleContract
        cls.contrato.setUpClass.__func__(cls)
        from _oracle_test_support import prepare_disposable_schema
        prepare_disposable_schema("agent")

    @classmethod
    def tearDownClass(cls):
        cls.contrato.tearDownClass.__func__(cls)

    def obter_repo(self, name):
        return self.contrato.obter_repo(self, name)

    def setUp(self):
        self.contrato.setUp(self)
        self._fixtures = self.trc._Fixtures(self.obter_repo)
        self.cat = self.obter_repo("catalog")
        self.conn = self.cat._obter_conexao()
        self.addCleanup(self.conn.close)  # LIFO: fecha depois da limpeza
        self.addCleanup(self._clean)
        self.tck, self.aud = self.cat.qualify_table("tickets"), self.cat.qualify_table("audit")
        self.aud_fixture = []
        self.tck_fixture = []  # todos os tickets da fixture, inclusive o que o purge apaga (auditoria deles)
        self.purges = []

    def _clean(self):
        cur = self.conn.cursor()
        for aid in self.aud_fixture + self.purges:
            cur.execute("DELETE FROM " + self.aud + " WHERE id = :id", {"id": aid})
        # Auditoria dos tickets da fixture, inclusive o que o purge apagou (no compartilhado nao sobra nada).
        for tid in self.tck_fixture:
            cur.execute("DELETE FROM " + self.aud + " WHERE entity = 'tbsss_tickets' AND entity_id = :id", {"id": tid})
        self.conn.commit()
        self.contrato._clean_fixtures(self)

    def _one(self, sql, **binds):
        cur = self.conn.cursor()
        cur.execute(sql, binds)
        return cur.fetchone()[0]

    def _executar(self, sql, **binds):
        cur = self.conn.cursor()
        cur.execute(sql, binds)
        self.conn.commit()

    def test_purge_real_so_dos_tickets_e_auditoria_da_fixture(self):
        m = self._fixtures
        amb, scr = m.environment("P"), m.script("p")
        login = m.usuario(m.profile("P")["id"], "u")["login"]
        base = {"script_id": scr["id"], "environment": amb["name"], "requested_by": login, "priority": 2,
                "status": "PENDING", "submitted_params": "{}"}
        velho_ok, velho_pend, novo_ok = (m.ticket(actor=login, **base) for _ in range(3))
        self.tck_fixture = [velho_ok, velho_pend, novo_ok]
        for tid, status, dias in ((velho_ok, "SUCCESS", 40), (velho_pend, "PENDING", 40), (novo_ok, "SUCCESS", 5)):
            self._executar("UPDATE " + self.tck + " SET status = :s, created_at = SYSDATE - :d WHERE id = :id",
                           s=status, d=dias, id=tid)
        aid = self._one("SELECT " + RepoPurge.from_config(self.oracle_cfg)._seq_aud + ".NEXTVAL FROM DUAL")
        self._executar("INSERT INTO " + self.aud + " (id, actor, action, entity, detail, created_at)"
                       " VALUES (:id, :a, 'LOGIN', 'tbsss_users', 'fixture F9.1a', SYSDATE - 400)", id=aid, a=m.actor)
        self.aud_fixture.append(aid)
        # Guarda (decisao 1a): nada fora da fixture pode ser elegivel no esquema compartilhado.
        alheios_tck = self._one("SELECT COUNT(*) FROM " + self.tck + " WHERE created_at < SYSDATE - :d"
                               " AND status IN ('SUCCESS','FAILED','CANCELLED') AND id <> :id", d=self.DAYS, id=velho_ok)
        alheios_aud = self._one("SELECT COUNT(*) FROM " + self.aud + " WHERE created_at < SYSDATE - 365 AND id <> :id",
                               id=aid)
        if alheios_tck or alheios_aud:
            self.skipTest("%d tickets e %d linhas de auditoria fora da fixture seriam elegiveis"
                          % (alheios_tck, alheios_aud))
        cfg = self.oracle_cfg
        dono = "tst-f91a-%s" % m.suf
        cfg_purge = types.SimpleNamespace(
            agent=types.SimpleNamespace(agent_id=dono), oracle=cfg.oracle,
            retention=types.SimpleNamespace(ticket_retention_days=self.DAYS, audit_retention_days=365,
                                           purge_batch_size=1))
        marca = self._one("SELECT NVL(MAX(id), 0) FROM " + self.aud)
        logger = logging.getLogger("sss_test_purge_oracle")
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        # Dry-run primeiro: conta a fixture, nada muda.
        p = purge_cli.Purge(cfg_purge, self.conn, logger=logger)
        self.assertEqual(p.run(("tickets", "audit"), dry_run=True), 0)
        self.assertEqual(p.summary, ["tickets: 1 linhas elegiveis (estimativa)",
                                    "audit: 1 linhas elegiveis (estimativa)"])
        pasta = tempfile.mkdtemp(prefix="sss_test_purge_csv_")
        self.addCleanup(shutil.rmtree, pasta, True)
        p = purge_cli.Purge(cfg_purge, self.conn, logger=logger)
        codigo = p.run(("tickets", "audit"), export=pasta)
        self.purges = [r[0] for r in self.conn.cursor().execute(
            "SELECT id FROM " + self.aud + " WHERE id > :m AND actor = 'SYSTEM:purge'", {"m": marca}).fetchall()]
        if p.summary and "pulado" in p.summary[0]:
            self.skipTest("concessao com outro no: %s" % p.summary)
        self.assertEqual(codigo, 0)
        restantes = dict(self.conn.cursor().execute(
            "SELECT id, status FROM " + self.tck + " WHERE id IN (:a, :b, :c)",
            {"a": velho_ok, "b": velho_pend, "c": novo_ok}).fetchall())
        self.assertEqual(restantes, {velho_pend: "PENDING", novo_ok: "SUCCESS"})
        self.assertEqual(self._one("SELECT COUNT(*) FROM " + self.aud + " WHERE id = :id", id=aid), 0)
        with io.open(os.path.join(pasta, os.listdir(pasta)[0]), encoding="utf-8-sig", newline="") as f:
            self.assertEqual([l[0] for l in csv.reader(f, delimiter=";")][1:], [str(aid)], "exportada antes de sair")
        linhas = self.conn.cursor().execute(
            "SELECT entity, detail, entity_id FROM " + self.aud + " WHERE id > :m AND actor = 'SYSTEM:purge'"
            " ORDER BY id", {"m": marca}).fetchall()
        self.assertEqual(linhas, [("tbsss_tickets", "1 linhas", None), ("tbsss_audit", "1 linhas", None)])
        ctl = self.conn.cursor().execute("SELECT purge_owner, purge_lease_until FROM "
                                         + self.cat.qualify_table("control") + " WHERE id = 1").fetchone()
        self.assertEqual(tuple(ctl), (None, None), "concessao liberada (CR-008, R-27)")
        self._fixtures.created["tickets"].remove(velho_ok)
        self.aud_fixture.remove(aid)
        print("\n[F9.1a] purge real: %s" % "; ".join(p.summary))


if __name__ == "__main__":
    unittest.main()
