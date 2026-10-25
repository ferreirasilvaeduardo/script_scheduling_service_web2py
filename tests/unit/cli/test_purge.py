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
from tests.support import _testenv  # noqa: F401

import csv
import datetime
import io
import logging
import os
import shutil
import tempfile
import types
import unittest
from unittest import mock

import os_platform
import purge as purge_cli  # scripts/purge.py (o repositorio e repo_oracle.purge)

NOW = datetime.datetime(2026, 10, 21, 3, 0, 0)
NS = types.SimpleNamespace
TERMINAL_STATUSES = ("SUCCESS", "FAILED", "CANCELLED")


def _cfg(root, **extra):
    agent = dict(agent_id="srv-a", work_dir=os.path.join(root, "work"), output_dir=None,
                  script_work_dir=None, environments=("PRODUCAO",), exec_users=())
    agent.update(extra.get("agent", {}))
    return NS(app=NS(sss_env="DEV"), oracle=NS(owner="openrisow", table_prefix="tbsss_"),
              secrets=NS(secrets_file=os.path.join(root, "secrets.cfg")), agent=NS(**agent),
              logging=NS(log_dir=os.path.join(root, "logs"), local_log_retention_days=30, output_retention_days=7,
                         script_work_retention_days=7),
              retention=NS(ticket_retention_days=90, audit_retention_days=365, purge_batch_size=2, input_retention_days=30,
                          purge_user=extra.get("purge_user", "sss_purge")))


class _Db(object):
    """Tickets, auditoria e tbsss_control em memoria, respondendo ao SQL do RepoPurge."""

    def __init__(self, tickets=(), audit=(), owner=None, until=None, running=(), inputs=()):
        self.tickets = [dict(id=i, created_at=c, status=s) for i, c, s in tickets]
        self.audit = [dict(id=i, created_at=c, actor="admin", source_ip="10.0.0.1", action="LOGIN",
                               entity="tbsss_users", entity_id=7, detail="d%d" % i) for i, c in audit]
        self.ctl = {"dono": owner, "ate": until}
        self.running = list(running)
        # Envios da tela de Entrada (CR-020e): (id, created_at, tem conteudo, tem entrega PENDING).
        self.inputs = [dict(id=i, created_at=c, content=ct, pending=pd) for i, c, ct, pd in inputs]
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
            rows = [t for t in self.b.tickets if t["created_at"] < limit and t["status"] in TERMINAL_STATUSES]
        else:
            rows = [a for a in self.b.audit if a["created_at"] < limit]
        return rows if batch is None else rows[:batch]

    def execute(self, sql, binds=None):
        b, binds = self.b, binds or {}
        b.sqls.append(sql)
        if b.fail_at and b.fail_at in sql:
            raise RuntimeError("ORA-03113: end-of-file on communication channel")
        table = "tickets" if "tbsss_tickets" in sql else "audit"
        self._lines, self.rowcount = [], 0
        if "tbsss_input_upload" in sql and not sql.startswith("INSERT"):
            done = [u for u in b.inputs if u["content"] and not u["pending"]]
            if sql.startswith("SELECT COUNT(*)"):
                rows = done if "content IS NOT NULL" in sql else [u for u in b.inputs if u["created_at"] < binds["cutoff"]]
                self._lines = [(len(rows),)]
            elif sql.startswith("UPDATE") and "content = NULL" in sql:
                for u in done[:binds["batch_size"]]:
                    u["content"] = False
                    b.pending.append((None, u))
                self.rowcount = min(len(done), binds["batch_size"])
            elif sql.startswith("DELETE"):
                target = [u for u in b.inputs if u["created_at"] < binds["cutoff"]][:binds["batch_size"]]
                for u in target:
                    b.inputs.remove(u)
                    b.pending.append((b.inputs, u))
                self.rowcount = len(target)
            else:
                raise AssertionError("SQL inesperado: %s" % sql)
            return
        if sql == "SELECT SYSDATE FROM DUAL":
            self._lines = [(NOW.replace(microsecond=123),)]
        elif "NEXTVAL" in sql:
            b.seq += 1
            self._lines = [(b.seq,)]
        elif "purge_lease_until = SYSDATE + 1/24" in sql:
            b.taken += 1
            if b.steal_on_renewal == b.taken:
                b.ctl = {"dono": "srv-outro", "ate": NOW + datetime.timedelta(hours=1)}
            free = b.ctl["ate"] is None or b.ctl["ate"] < NOW or b.ctl["dono"] == binds["owner"]
            if free:
                b.ctl = {"dono": binds["owner"], "ate": NOW + datetime.timedelta(hours=1)}
            self.rowcount = int(free)
        elif "SET purge_owner = NULL" in sql:
            if b.ctl["dono"] == binds["owner"]:
                b.ctl = {"dono": None, "ate": None}
                self.rowcount = 1
        elif sql.startswith("SELECT COUNT(*)"):
            self._lines = [(len(self._eligible(table, binds["cutoff"])),)]
        elif sql.startswith("DELETE") and "ROWNUM <= :batch_size" in sql:
            target = self._eligible(table, binds["cutoff"], binds["batch_size"])
            items = b.tickets if table == "tickets" else b.audit
            for line in target:
                items.remove(line)
                b.pending.append((items, line))
            self.rowcount = len(target)
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
        for line in [a for a in self.b.audit if a["id"] in ids]:
            self.b.audit.remove(line)
            self.b.pending.append((self.b.audit, line))
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
        for items, line in self.b.pending:
            if items is None:
                line["content"] = True  # o UPDATE do conteudo e desfeito
            else:
                items.append(line)
        items_order = sorted(self.b.tickets, key=lambda t: t["id"])
        self.b.tickets[:] = items_order
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
        dir_value = os.path.join(self.cfg.logging.log_dir, *rel.split("/"))
        os.makedirs(dir_value)
        for name in files:
            with open(os.path.join(dir_value, name), "w") as f:
                f.write("x")
        return dir_value

    def _purges(self, db):
        return [a for a in db.audit if a["action"] == "PURGE"]


class TestTables(_Base):

    def test_lotes_ate_rowcount_zero_e_so_terminais(self):
        old = [(i, _days(100), s) for i, s in enumerate(TERMINAL_STATUSES * 2, 1)][:5]
        db = _Db(tickets=old + [(10, _days(100), "PENDING"), (11, _days(100), "RUNNING"),
                                         (12, _days(10), "SUCCESS")])
        p = self._purge(db)
        self.assertEqual(p.run(("tickets",)), purge_cli.EXIT_OK)
        self.assertEqual(sorted(t["id"] for t in db.tickets), [10, 11, 12], "nunca um ticket nao terminal")
        batches = [s for s in db.sqls if s.startswith("DELETE")]
        self.assertEqual(len(batches), 4, "2 + 2 + 1 e o lote vazio")
        self.assertEqual(batches[0], "DELETE FROM openrisow.tbsss_tickets WHERE created_at < :cutoff"
                                   " AND status IN ('SUCCESS','FAILED','CANCELLED') AND ROWNUM <= :batch_size")
        self.assertIn("tickets: 5 linhas apagadas", p.summary)

    def test_purge_auditado_por_tabela_inclusive_com_zero(self):
        db = _Db(tickets=[(1, _days(100), "FAILED")], audit=[(50, _days(10))])
        self.assertEqual(self._purge(db).run(("tickets", "audit")), 0)
        purges = self._purges(db)
        self.assertEqual([(a["entity"], a["detail"], a["actor"], a["entity_id"]) for a in purges],
                         [("tbsss_tickets", "1 linhas", "SYSTEM:purge", None),
                          ("tbsss_audit", "0 linhas", "SYSTEM:purge", None)])
        self.assertEqual([a["id"] for a in db.audit if a["action"] != "PURGE"], [50], "recente fica")

    def test_limite_calculado_uma_vez_pelo_banco(self):
        db = _Db(tickets=[(1, NOW - datetime.timedelta(days=90, seconds=1), "SUCCESS"),
                                (2, NOW - datetime.timedelta(days=90), "SUCCESS")])
        self._purge(db).run(("tickets",))
        self.assertEqual([t["id"] for t in db.tickets], [2], "created_at < SYSDATE - dias, estrito")
        self.assertEqual(db.sqls.count("SELECT SYSDATE FROM DUAL"), 1)

    def test_concessao_tomada_renovada_e_liberada(self):
        db = _Db(tickets=[(i, _days(100), "SUCCESS") for i in range(1, 6)])
        self._purge(db).run(("tickets",))
        taken = [s for s in db.sqls if "purge_lease_until = SYSDATE + 1/24" in s]
        self.assertEqual(len(taken), 1 + 3, "tomada e uma renovacao por lote nao vazio")
        self.assertEqual(db.ctl, {"dono": None, "ate": None}, "dono e prazo zerados (CR-008, R-27)")
        self.assertIn("UPDATE openrisow.tbsss_control SET purge_owner = NULL, purge_lease_until = NULL"
                      " WHERE id = 1 AND purge_owner = :owner", db.sqls)

    def test_concessao_de_outro_no_pula_tabelas_sem_auditar(self):
        until = NOW + datetime.timedelta(minutes=30)
        db = _Db(tickets=[(1, _days(100), "SUCCESS")], owner="srv-b", until=until)
        p = self._purge(db)
        self.assertEqual(p.run(("tickets", "audit")), purge_cli.EXIT_OK)
        self.assertEqual(len(db.tickets), 1)
        self.assertEqual(self._purges(db), [], "sem a concessao, outro no audita a sua execucao")
        self.assertFalse([s for s in db.sqls if s.startswith("DELETE")])
        self.assertEqual(db.ctl, {"dono": "srv-b", "ate": until}, "concessao alheia intocada")
        self.assertIn("tickets: pulado (outro no esta purgando)", p.summary)

    def test_concessao_vencida_de_outro_no_e_tomada(self):
        db = _Db(tickets=[(1, _days(100), "SUCCESS")], owner="srv-b", until=NOW - datetime.timedelta(minutes=1))
        self.assertEqual(self._purge(db).run(("tickets",)), 0)
        self.assertEqual(db.tickets, [])

    def test_concessao_perdida_no_meio(self):
        db = _Db(tickets=[(i, _days(100), "SUCCESS") for i in range(1, 6)])
        db.steal_on_renewal = 3  # tomada, 1a renovacao, 2a renovacao perdida
        self.assertEqual(self._purge(db).run(("tickets",)), purge_cli.EXIT_DATABASE)
        self.assertEqual(len(db.tickets), 3, "o 2o lote foi desfeito")
        self.assertEqual(db.ctl["dono"], "srv-outro", "a concessao de quem tomou fica")
        self.assertEqual(self._purges(db), [])

    def test_falha_de_banco(self):
        db = _Db(tickets=[(1, _days(100), "SUCCESS")])
        db.fail_at = "DELETE FROM"
        self.assertEqual(self._purge(db).run(("tickets",)), purge_cli.EXIT_DATABASE)
        self.assertGreaterEqual(db.rollbacks, 1)
        self.assertEqual(db.ctl, {"dono": None, "ate": None}, "liberada mesmo na falha")

    def test_exportar_auditoria(self):
        dir_value = os.path.join(self.root, "arquivo")
        os.mkdir(dir_value)
        db = _Db(audit=[(1, _days(400)), (2, _days(400)), (3, _days(380)), (4, _days(10))])
        p = self._purge(db)
        self.assertEqual(p.run(("audit",), export=dir_value), 0)
        files = os.listdir(dir_value)
        self.assertEqual(files, ["auditoria_purge_20261021_030000.csv"])
        path = os.path.join(dir_value, files[0])
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        with io.open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f, delimiter=";"))
        self.assertEqual(rows[0][0], u"ID")
        self.assertEqual([l[0] for l in rows[1:]], ["1", "2", "3"])
        self.assertEqual([a["id"] for a in db.audit if a["action"] != "PURGE"], [4])
        self.assertEqual(self._purges(db)[0]["detail"], "3 linhas")
        self.assertFalse([s for s in db.sqls if s.startswith("DELETE") and "ROWNUM" in s],
                         "com exportacao, apaga pelo id das linhas gravadas")


class TestDryRun(_Base):

    def test_so_select_um_agora_e_nada_alterado(self):
        old = self._minute("producao/carga/2026/01/10/03/00")
        plat = _Plat(count=4)
        cfg = _cfg(self.root, agent={"output_dir": os.path.join(self.root, "saida")})
        os.makedirs(os.path.join(self.root, "saida", "producao"))
        db = _Db(tickets=[(1, _days(100), "SUCCESS"), (2, _days(100), "PENDING")],
                       audit=[(5, _days(400))])
        p = self._purge(db, plat=plat, cfg=cfg)
        self.assertEqual(p.run(purge_cli.TARGETS, dry_run=True), 0)
        self.assertTrue(all(s.startswith("SELECT") for s in db.sqls), db.sqls)
        self.assertEqual(db.sqls.count("SELECT SYSDATE FROM DUAL"), 1)
        self.assertTrue(any(s.startswith("SELECT t.environment") for s in db.sqls), "RUNNING tambem no dry-run")
        self.assertEqual((db.commits, len(db.tickets), len(db.audit)), (0, 2, 1))
        self.assertEqual(db.ctl, {"dono": None, "ate": None})
        self.assertTrue(os.path.isdir(old))
        self.assertEqual(plat.calls, [(os.path.join(self.root, "saida", "producao"), 7, None, True)])
        self.assertEqual(p.summary, ["tickets: 1 linhas elegiveis (estimativa)",
                                    "audit: 1 linhas elegiveis (estimativa)",
                                    "inputs: 0 conteudos a esvaziar e 0 envios elegiveis (estimativa)",
                                    "local_logs: 1 pastas de minuto elegiveis (estimativa)",
                                    "output: 4 pastas de minuto elegiveis (estimativa)",
                                    "script_work: desligada (script_work_dir vazio)"])


class TestLocalLogs(_Base):

    def test_pela_data_do_caminho_com_running_mantido(self):
        old = self._minute("producao/carga/2026/09/01/10/00", ("ticket_1_100.log", "ticket_2.log.parcial"))
        recent = self._minute("producao/carga/2026/10/20/10/00")
        running = self._minute("producao/extrator/2026/09/01/23/59", ("ticket_3.log.parcial",))
        alone = self._minute("homologacao/outro/2025/12/31/08/15")
        internal = self._minute("internal/app/2020/01/01/00/00", ("sss_web_1.log",))
        odd = os.path.join(self.cfg.logging.log_dir, "producao", "carga", "2026", "09", "lixo")
        os.makedirs(odd)
        outside = os.path.join(self.root, "fora", "2026", "01", "01", "00", "00")
        os.makedirs(outside)
        os.symlink(os.path.join(self.root, "fora"), os.path.join(self.cfg.logging.log_dir, "producao", "ligado"))
        db = _Db(running=[("PRODUCAO", 9, datetime.datetime(2026, 9, 1, 23, 59, 30),
                                 '{"version": 5, "script_name": "Extrator"}')])
        p = self._purge(db)
        self.assertEqual(p.run(("local_logs",)), 0)
        self.assertFalse(os.path.exists(old), "pasta de minuto inteira, com o .log.parcial")
        self.assertFalse(os.path.exists(os.path.join(self.cfg.logging.log_dir, "producao", "carga", "2026", "09", "01")),
                         "hora e dia vazios removidos")
        self.assertTrue(os.path.isdir(odd), "fora do formato e ignorado")
        self.assertTrue(os.path.isdir(recent))
        self.assertTrue(os.path.isdir(running), "log de ticket RUNNING mantido (CR-007, R-32)")
        self.assertFalse(os.path.exists(os.path.join(self.cfg.logging.log_dir, "homologacao")),
                         "vazias ate o ambiente")
        self.assertTrue(os.path.isdir(internal), "internal/ intocada (CR-009)")
        self.assertTrue(os.path.isdir(outside), "link nao e seguido")
        self.assertEqual(p.summary, ["local_logs: 2 pastas de minuto removidas"])

    def test_falha_na_remocao_sai_com_3(self):
        self._minute("producao/carga/2026/01/01/10/00")
        with mock.patch("sss.config.log_paths.shutil.rmtree", side_effect=OSError(13, "Permission denied")):
            self.assertEqual(self._purge(_Db()).run(("local_logs",)), purge_cli.EXIT_LOCAL)

    def test_caminho_real_fora_de_log_dir_nao_e_removido(self):
        old = self._minute("producao/carga/2026/01/01/10/00")
        plat = _Plat()
        plat.final_path = lambda c: "/outro" + c if c != self.cfg.logging.log_dir else c
        self.assertEqual(self._purge(_Db(), plat=plat).run(("local_logs",)), purge_cli.EXIT_LOCAL)
        self.assertTrue(os.path.isdir(old))


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


class TestInputs(_Base):
    """CR-020e (README §11.3): conteudo dos envios ja entregues esvaziado; envios alem da retencao apagados."""

    def _db(self):
        return _Db(inputs=[(1, _days(40), True, False), (2, _days(2), True, False), (3, _days(1), True, True),
                           (4, _days(50), True, True), (5, _days(3), False, False)])

    def test_esvazia_entregues_apaga_antigos_e_audita(self):
        db = self._db()
        p = self._purge(db)
        self.assertEqual(p.run(("inputs",)), 0)
        remaining = dict((u["id"], (u["content"], u["pending"])) for u in db.inputs)
        self.assertEqual(remaining, {2: (False, False), 3: (True, True), 5: (False, False)},
                         "pendente mantem o conteudo; alem de 30 dias sai inteiro")
        purge = [a for a in db.audit if a.get("action") == "PURGE"]
        self.assertEqual([(a["entity"], a["detail"]) for a in purge],
                         [("tbsss_input_upload", "2 conteudos esvaziados; 2 envios apagados")])
        self.assertEqual(p.summary, ["inputs: 2 conteudos esvaziados, 2 envios apagados"])
        self.assertIsNone(db.ctl["dono"], "concessao liberada")

    def test_auditado_com_zero_e_dry_run_so_conta(self):
        db = _Db()
        p = self._purge(db)
        self.assertEqual(p.run(("inputs",)), 0)
        self.assertEqual([a["detail"] for a in db.audit if a.get("action") == "PURGE"],
                         ["0 conteudos esvaziados; 0 envios apagados"])
        db = self._db()
        p = self._purge(db)
        self.assertEqual(p.run(("inputs",), dry_run=True), 0)
        self.assertEqual(p.summary[0], "inputs: 2 conteudos a esvaziar e 2 envios elegiveis (estimativa)")
        self.assertTrue(all(s.startswith("SELECT") for s in db.sqls))
        self.assertEqual(len(db.inputs), 5)

    def test_concessao_de_outro_no_pula_os_envios(self):
        db = self._db()
        db.ctl = {"dono": "srv-outro", "ate": NOW + datetime.timedelta(minutes=30)}
        p = self._purge(db)
        self.assertEqual(p.run(("inputs",)), 0)
        self.assertEqual(len(db.inputs), 5)
        self.assertEqual(p.summary, ["inputs: pulado (outro no esta purgando)"])


class TestScriptWork(_Base):
    """CR-019 (README §8.15 e §11.3): pastas de trabalho pelo mesmo purge-output, com a retencao propria."""

    def test_por_ambiente_com_a_retencao_propria(self):
        base = os.path.join(self.root, "trabalho")
        os.makedirs(os.path.join(base, "producao"))
        cfg = _cfg(self.root, agent={"script_work_dir": base, "exec_users": (("PRODUCAO", "sssprd"),)})
        cfg.logging.script_work_retention_days = 15
        plat = _Plat(count=3)
        p = self._purge(_Db(), plat=plat, cfg=cfg)
        self.assertEqual(p.run(("script_work",)), 0)
        self.assertEqual(plat.calls, [(os.path.join(base, "producao"), 15, "sssprd", False)])
        self.assertEqual(p.summary, ["script_work: 3 pastas de minuto removidas"])
        plat = _Plat(count=3)
        p = self._purge(_Db(), plat=plat, cfg=cfg)
        self.assertEqual(p.run(("script_work",), dry_run=True), 0)
        self.assertEqual(plat.calls, [(os.path.join(base, "producao"), 15, "sssprd", True)], "dry-run so conta")

    def test_desligada_e_falha(self):
        p = self._purge(_Db())
        self.assertEqual(p.run(("script_work",)), 0)
        self.assertEqual(p.summary, ["script_work: desligada (script_work_dir vazio)"])
        base = os.path.join(self.root, "trabalho")
        os.makedirs(os.path.join(base, "producao"))
        cfg = _cfg(self.root, agent={"script_work_dir": base})
        self.assertEqual(self._purge(_Db(), plat=_Plat(fail=True), cfg=cfg).run(("script_work",)),
                         purge_cli.EXIT_LOCAL)
        self.assertEqual("script_work" in purge_cli.CLI_TARGETS, True)


class TestMain(_Base):
    """A linha de comando: configuracao, trava local, conexao e resumo no stdout."""

    def _main(self, argv, db=None, cfg=None, plat=None, secrets_error_flag=False):
        cfg = cfg or self.cfg
        db = db if db is not None else _Db()
        self.connections = []

        def conectar(_cfg, _secrets):
            self.connections.append(1)
            return _Conn(db)
        output = io.StringIO()
        load = mock.Mock(side_effect=purge_cli.sss_config.ConfigError(reason="x") if secrets_error_flag else None,
                             return_value=object())
        with mock.patch.object(purge_cli.sss_config, "get_config", return_value=cfg), \
                mock.patch.object(purge_cli.sss_config, "load_secrets", load), \
                mock.patch.object(purge_cli.sss_logging, "configure", return_value=self.log), \
                mock.patch.object(purge_cli.masking, "install_filter_on_handlers"):
            code = purge_cli.main(argv, connect=conectar, plat=plat or _Plat(), output=output)
        self.load = load
        return code, output.getvalue()

    def test_execucao_real_com_trava_e_resumo(self):
        plat = _Plat()
        db = _Db(tickets=[(1, _days(100), "CANCELLED")])
        code, text = self._main(["--target", "tickets"], db=db, plat=plat)
        self.assertEqual(code, 0)
        self.assertEqual(plat.locks, [os.path.join(self.root, "work", "sss-purge.lock")])
        self.assertEqual(text, "tickets: 1 linhas apagadas\n")
        self.assertEqual(db.closed, 1)
        self.assertEqual(self.load.call_args[1]["role"], "agent", "[purge] password so no papel agente")

    def test_dry_run_sem_trava_e_com_aviso(self):
        plat = _Plat()
        code, text = self._main(["--dry-run", "--target", "audit"], plat=plat)
        self.assertEqual(code, 0)
        self.assertEqual(plat.locks, [])
        self.assertFalse(os.path.exists(os.path.join(self.root, "work", "sss-purge.lock")))
        self.assertIn("dry-run: contagens estimadas", text)

    def test_outro_purge_no_servidor(self):
        lock = os_platform.lock_instance(os.path.join(self.root, "work", "sss-purge.lock"))
        self.addCleanup(os_platform.release_instance, lock)
        code, text = self._main([])
        self.assertEqual((code, text, self.connections), (0, "", []))

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
            code = purge_cli.main([], connect=mock.Mock(side_effect=RuntimeError("ORA-12541: no listener")),
                                    plat=_Plat(), output=io.StringIO())
        self.assertEqual(code, purge_cli.EXIT_DATABASE)

    def test_alvo_invalido(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
            purge_cli._arguments(["--target", "tudo"])


if __name__ == "__main__":
    unittest.main()
