# -*- coding: utf-8 -*-
"""Testes do scripts/purge.py e do repo_oracle/purge.py (README §11.3; F9.1a; CR-005; CR-007 R-21, R-22, R-32;
CR-008 R-16, R-27; CR-009; CR-012).

Com um banco simulado em memoria (o SQL e o do RepoPurge real): lotes ate rowcount = 0, so tickets terminais,
concessao tomada, renovada, liberada (dono e prazo), negada e perdida, PURGE com 0 linhas, --export-audit,
--dry-run so com SELECT e um agora_banco(), logs locais pela data do caminho (RUNNING mantido, interno/ intocada),
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

AGORA = datetime.datetime(2026, 10, 21, 3, 0, 0)
NS = types.SimpleNamespace
TERMINAIS = ("SUCCESS", "FAILED", "CANCELLED")


def _cfg(raiz, **extra):
    agente = dict(agent_id="srv-a", work_dir=os.path.join(raiz, "work"), output_dir=None,
                  environments=("PRODUCAO",), exec_users=())
    agente.update(extra.get("agent", {}))
    return NS(app=NS(sss_env="DEV"), oracle=NS(owner="openrisow", table_prefix="tbsss_"),
              secrets=NS(secrets_file=os.path.join(raiz, "secrets.cfg")), agent=NS(**agente),
              logging=NS(log_dir=os.path.join(raiz, "logs"), local_log_retention_days=30, output_retention_days=7),
              retention=NS(ticket_retention_days=90, audit_retention_days=365, purge_batch_size=2,
                          purge_user=extra.get("purge_user", "sss_purge")))


class _Banco(object):
    """Tickets, auditoria e tbsss_control em memoria, respondendo ao SQL do RepoPurge."""

    def __init__(self, tickets=(), auditoria=(), dono=None, ate=None, running=()):
        self.tickets = [dict(id=i, created_at=c, status=s) for i, c, s in tickets]
        self.auditoria = [dict(id=i, created_at=c, actor="admin", source_ip="10.0.0.1", action="LOGIN",
                               entity="tbsss_users", entity_id=7, detail="d%d" % i) for i, c in auditoria]
        self.ctl = {"dono": dono, "ate": ate}
        self.running = list(running)
        self.sqls = []
        self.commits = self.rollbacks = self.fechada = 0
        self.seq = 1000
        self.roubar_na_renovacao = None  # n-esima tomada da concessao que outro no ganha
        self.tomadas = 0
        self.falhar_em = None  # trecho de SQL que levanta erro
        self.pendentes = []  # (lista, linha) apagadas e ainda nao confirmadas


class _Cursor(object):

    def __init__(self, banco):
        self.b = banco
        self.rowcount = 0
        self._linhas = []

    def setinputsizes(self, **_tipos):
        pass

    def close(self):
        pass

    def fetchone(self):
        return self._linhas[0] if self._linhas else None

    def fetchall(self):
        return list(self._linhas)

    def _elegiveis(self, tabela, limite, lote=None):
        if tabela == "tickets":
            linhas = [t for t in self.b.tickets if t["created_at"] < limite and t["status"] in TERMINAIS]
        else:
            linhas = [a for a in self.b.auditoria if a["created_at"] < limite]
        return linhas if lote is None else linhas[:lote]

    def execute(self, sql, binds=None):
        b, binds = self.b, binds or {}
        b.sqls.append(sql)
        if b.falhar_em and b.falhar_em in sql:
            raise RuntimeError("ORA-03113: end-of-file on communication channel")
        tabela = "tickets" if "tbsss_tickets" in sql else "auditoria"
        self._linhas, self.rowcount = [], 0
        if sql == "SELECT SYSDATE FROM DUAL":
            self._linhas = [(AGORA.replace(microsecond=123),)]
        elif "NEXTVAL" in sql:
            b.seq += 1
            self._linhas = [(b.seq,)]
        elif "purge_lease_until = SYSDATE + 1/24" in sql:
            b.tomadas += 1
            if b.roubar_na_renovacao == b.tomadas:
                b.ctl = {"dono": "srv-outro", "ate": AGORA + datetime.timedelta(hours=1)}
            livre = b.ctl["ate"] is None or b.ctl["ate"] < AGORA or b.ctl["dono"] == binds["dono"]
            if livre:
                b.ctl = {"dono": binds["dono"], "ate": AGORA + datetime.timedelta(hours=1)}
            self.rowcount = int(livre)
        elif "SET purge_owner = NULL" in sql:
            if b.ctl["dono"] == binds["dono"]:
                b.ctl = {"dono": None, "ate": None}
                self.rowcount = 1
        elif sql.startswith("SELECT COUNT(*)"):
            self._linhas = [(len(self._elegiveis(tabela, binds["limite"])),)]
        elif sql.startswith("DELETE") and "ROWNUM <= :lote" in sql:
            alvo = self._elegiveis(tabela, binds["limite"], binds["lote"])
            lista = b.tickets if tabela == "tickets" else b.auditoria
            for linha in alvo:
                lista.remove(linha)
                b.pendentes.append((lista, linha))
            self.rowcount = len(alvo)
        elif "FOR UPDATE" in sql:
            cols = ("id", "created_at", "actor", "source_ip", "action", "entity", "entity_id", "detail")
            self._linhas = [tuple(a[c] for c in cols) for a in self._elegiveis("auditoria", binds["limite"],
                                                                                  binds["lote"])]
        elif sql.startswith("INSERT INTO"):
            b.auditoria.append(dict(binds, created_at=AGORA, action="PURGE", source_ip=None, entity_id=None))
            self.rowcount = 1
        elif sql.startswith("SELECT t.environment"):
            self._linhas = list(b.running)
        else:
            raise AssertionError("SQL inesperado: %s" % sql)

    def executemany(self, sql, binds):
        self.b.sqls.append(sql)
        ids = set(x["id"] for x in binds)
        for linha in [a for a in self.b.auditoria if a["id"] in ids]:
            self.b.auditoria.remove(linha)
            self.b.pendentes.append((self.b.auditoria, linha))
        self.rowcount = len(ids)


class _Conn(object):

    def __init__(self, banco):
        self.b = banco

    def cursor(self):
        return _Cursor(self.b)

    def commit(self):
        self.b.commits += 1
        self.b.pendentes = []

    def rollback(self):
        self.b.rollbacks += 1
        for lista, linha in self.b.pendentes:
            lista.append(linha)
        lista_ordem = sorted(self.b.tickets, key=lambda t: t["id"])
        self.b.tickets[:] = lista_ordem
        self.b.pendentes = []

    def close(self):
        self.b.fechada += 1


class _Plat(object):
    """Plataforma dos testes: caminho_final real; helper de saida, trava e liberacao registrados."""

    def __init__(self, contagem=0, falhar=False):
        self.chamadas = []
        self.contagem, self.falhar = contagem, falhar
        self.travas = []
        self.caminho_final = os_platform.caminho_final

    def purgar_saida(self, base, dias, usuario_execucao=None, contar=False):
        self.chamadas.append((base, dias, usuario_execucao, contar))
        if self.falhar:
            raise RuntimeError("helper purge-output falhou (codigo 4)")
        return self.contagem

    def travar_instancia(self, caminho):
        self.travas.append(caminho)
        return os_platform.travar_instancia(caminho)

    def liberar_instancia(self, trava):
        os_platform.liberar_instancia(trava)


def _dias(n):
    return AGORA - datetime.timedelta(days=n)


class _Base(unittest.TestCase):

    def setUp(self):
        self.raiz = os.path.realpath(tempfile.mkdtemp(prefix="sss_test_purge_"))
        self.addCleanup(shutil.rmtree, self.raiz, True)
        os.mkdir(os.path.join(self.raiz, "work"))
        os.mkdir(os.path.join(self.raiz, "logs"))
        self.cfg = _cfg(self.raiz)
        self.log = logging.getLogger("sss_test_purge")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False

    def _purge(self, banco, plat=None, cfg=None):
        return purge_cli.Purge(cfg or self.cfg, _Conn(banco), plat=plat or _Plat(), logger=self.log)

    def _minuto(self, rel, arquivos=("ticket_1_100.log",)):
        pasta = os.path.join(self.cfg.logging.log_dir, *rel.split("/"))
        os.makedirs(pasta)
        for nome in arquivos:
            with open(os.path.join(pasta, nome), "w") as f:
                f.write("x")
        return pasta

    def _purges(self, banco):
        return [a for a in banco.auditoria if a["action"] == "PURGE"]


class TestTabelas(_Base):

    def test_lotes_ate_rowcount_zero_e_so_terminais(self):
        velhos = [(i, _dias(100), s) for i, s in enumerate(TERMINAIS * 2, 1)][:5]
        banco = _Banco(tickets=velhos + [(10, _dias(100), "PENDING"), (11, _dias(100), "RUNNING"),
                                         (12, _dias(10), "SUCCESS")])
        p = self._purge(banco)
        self.assertEqual(p.executar(("tickets",)), purge_cli.SAIDA_OK)
        self.assertEqual(sorted(t["id"] for t in banco.tickets), [10, 11, 12], "nunca um ticket nao terminal")
        lotes = [s for s in banco.sqls if s.startswith("DELETE")]
        self.assertEqual(len(lotes), 4, "2 + 2 + 1 e o lote vazio")
        self.assertEqual(lotes[0], "DELETE FROM openrisow.tbsss_tickets WHERE created_at < :limite"
                                   " AND status IN ('SUCCESS','FAILED','CANCELLED') AND ROWNUM <= :lote")
        self.assertIn("tickets: 5 linhas apagadas", p.resumo)

    def test_purge_auditado_por_tabela_inclusive_com_zero(self):
        banco = _Banco(tickets=[(1, _dias(100), "FAILED")], auditoria=[(50, _dias(10))])
        self.assertEqual(self._purge(banco).executar(("tickets", "auditoria")), 0)
        purges = self._purges(banco)
        self.assertEqual([(a["entity"], a["detail"], a["actor"], a["entity_id"]) for a in purges],
                         [("tbsss_tickets", "1 linhas", "SYSTEM:purge", None),
                          ("tbsss_audit", "0 linhas", "SYSTEM:purge", None)])
        self.assertEqual([a["id"] for a in banco.auditoria if a["action"] != "PURGE"], [50], "recente fica")

    def test_limite_calculado_uma_vez_pelo_banco(self):
        banco = _Banco(tickets=[(1, AGORA - datetime.timedelta(days=90, seconds=1), "SUCCESS"),
                                (2, AGORA - datetime.timedelta(days=90), "SUCCESS")])
        self._purge(banco).executar(("tickets",))
        self.assertEqual([t["id"] for t in banco.tickets], [2], "created_at < SYSDATE - dias, estrito")
        self.assertEqual(banco.sqls.count("SELECT SYSDATE FROM DUAL"), 1)

    def test_concessao_tomada_renovada_e_liberada(self):
        banco = _Banco(tickets=[(i, _dias(100), "SUCCESS") for i in range(1, 6)])
        self._purge(banco).executar(("tickets",))
        tomadas = [s for s in banco.sqls if "purge_lease_until = SYSDATE + 1/24" in s]
        self.assertEqual(len(tomadas), 1 + 3, "tomada e uma renovacao por lote nao vazio")
        self.assertEqual(banco.ctl, {"dono": None, "ate": None}, "dono e prazo zerados (CR-008, R-27)")
        self.assertIn("UPDATE openrisow.tbsss_control SET purge_owner = NULL, purge_lease_until = NULL"
                      " WHERE id = 1 AND purge_owner = :dono", banco.sqls)

    def test_concessao_de_outro_no_pula_tabelas_sem_auditar(self):
        ate = AGORA + datetime.timedelta(minutes=30)
        banco = _Banco(tickets=[(1, _dias(100), "SUCCESS")], dono="srv-b", ate=ate)
        p = self._purge(banco)
        self.assertEqual(p.executar(("tickets", "auditoria")), purge_cli.SAIDA_OK)
        self.assertEqual(len(banco.tickets), 1)
        self.assertEqual(self._purges(banco), [], "sem a concessao, outro no audita a sua execucao")
        self.assertFalse([s for s in banco.sqls if s.startswith("DELETE")])
        self.assertEqual(banco.ctl, {"dono": "srv-b", "ate": ate}, "concessao alheia intocada")
        self.assertIn("tickets: pulado (outro no esta purgando)", p.resumo)

    def test_concessao_vencida_de_outro_no_e_tomada(self):
        banco = _Banco(tickets=[(1, _dias(100), "SUCCESS")], dono="srv-b", ate=AGORA - datetime.timedelta(minutes=1))
        self.assertEqual(self._purge(banco).executar(("tickets",)), 0)
        self.assertEqual(banco.tickets, [])

    def test_concessao_perdida_no_meio(self):
        banco = _Banco(tickets=[(i, _dias(100), "SUCCESS") for i in range(1, 6)])
        banco.roubar_na_renovacao = 3  # tomada, 1a renovacao, 2a renovacao perdida
        self.assertEqual(self._purge(banco).executar(("tickets",)), purge_cli.SAIDA_BANCO)
        self.assertEqual(len(banco.tickets), 3, "o 2o lote foi desfeito")
        self.assertEqual(banco.ctl["dono"], "srv-outro", "a concessao de quem tomou fica")
        self.assertEqual(self._purges(banco), [])

    def test_falha_de_banco(self):
        banco = _Banco(tickets=[(1, _dias(100), "SUCCESS")])
        banco.falhar_em = "DELETE FROM"
        self.assertEqual(self._purge(banco).executar(("tickets",)), purge_cli.SAIDA_BANCO)
        self.assertGreaterEqual(banco.rollbacks, 1)
        self.assertEqual(banco.ctl, {"dono": None, "ate": None}, "liberada mesmo na falha")

    def test_exportar_auditoria(self):
        pasta = os.path.join(self.raiz, "arquivo")
        os.mkdir(pasta)
        banco = _Banco(auditoria=[(1, _dias(400)), (2, _dias(400)), (3, _dias(380)), (4, _dias(10))])
        p = self._purge(banco)
        self.assertEqual(p.executar(("auditoria",), exportar=pasta), 0)
        arquivos = os.listdir(pasta)
        self.assertEqual(arquivos, ["auditoria_purge_20261021_030000.csv"])
        caminho = os.path.join(pasta, arquivos[0])
        self.assertEqual(os.stat(caminho).st_mode & 0o777, 0o600)
        with io.open(caminho, encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.reader(f, delimiter=";"))
        self.assertEqual(linhas[0][0], u"ID")
        self.assertEqual([l[0] for l in linhas[1:]], ["1", "2", "3"])
        self.assertEqual([a["id"] for a in banco.auditoria if a["action"] != "PURGE"], [4])
        self.assertEqual(self._purges(banco)[0]["detail"], "3 linhas")
        self.assertFalse([s for s in banco.sqls if s.startswith("DELETE") and "ROWNUM" in s],
                         "com exportacao, apaga pelo id das linhas gravadas")


class TestDryRun(_Base):

    def test_so_select_um_agora_e_nada_alterado(self):
        antigo = self._minuto("producao/carga/2026/01/10/03/00")
        plat = _Plat(contagem=4)
        cfg = _cfg(self.raiz, agent={"output_dir": os.path.join(self.raiz, "saida")})
        os.makedirs(os.path.join(self.raiz, "saida", "producao"))
        banco = _Banco(tickets=[(1, _dias(100), "SUCCESS"), (2, _dias(100), "PENDING")],
                       auditoria=[(5, _dias(400))])
        p = self._purge(banco, plat=plat, cfg=cfg)
        self.assertEqual(p.executar(purge_cli.ALVOS, dry_run=True), 0)
        self.assertTrue(all(s.startswith("SELECT") for s in banco.sqls), banco.sqls)
        self.assertEqual(banco.sqls.count("SELECT SYSDATE FROM DUAL"), 1)
        self.assertTrue(any(s.startswith("SELECT t.environment") for s in banco.sqls), "RUNNING tambem no dry-run")
        self.assertEqual((banco.commits, len(banco.tickets), len(banco.auditoria)), (0, 2, 1))
        self.assertEqual(banco.ctl, {"dono": None, "ate": None})
        self.assertTrue(os.path.isdir(antigo))
        self.assertEqual(plat.chamadas, [(os.path.join(self.raiz, "saida", "producao"), 7, None, True)])
        self.assertEqual(p.resumo, ["tickets: 1 linhas elegiveis (estimativa)",
                                    "auditoria: 1 linhas elegiveis (estimativa)",
                                    "logs_locais: 1 pastas de minuto elegiveis (estimativa)",
                                    "saida: 4 pastas de minuto elegiveis (estimativa)"])


class TestLogsLocais(_Base):

    def test_pela_data_do_caminho_com_running_mantido(self):
        velho = self._minuto("producao/carga/2026/09/01/10/00", ("ticket_1_100.log", "ticket_2.log.parcial"))
        recente = self._minuto("producao/carga/2026/10/20/10/00")
        running = self._minuto("producao/extrator/2026/09/01/23/59", ("ticket_3.log.parcial",))
        sozinho = self._minuto("homologacao/outro/2025/12/31/08/15")
        interno = self._minuto("interno/app/2020/01/01/00/00", ("sss_web_1.log",))
        estranho = os.path.join(self.cfg.logging.log_dir, "producao", "carga", "2026", "09", "lixo")
        os.makedirs(estranho)
        fora = os.path.join(self.raiz, "fora", "2026", "01", "01", "00", "00")
        os.makedirs(fora)
        os.symlink(os.path.join(self.raiz, "fora"), os.path.join(self.cfg.logging.log_dir, "producao", "ligado"))
        banco = _Banco(running=[("PRODUCAO", 9, datetime.datetime(2026, 9, 1, 23, 59, 30),
                                 '{"versao": 4, "script_nome": "Extrator"}')])
        p = self._purge(banco)
        self.assertEqual(p.executar(("logs_locais",)), 0)
        self.assertFalse(os.path.exists(velho), "pasta de minuto inteira, com o .log.parcial")
        self.assertFalse(os.path.exists(os.path.join(self.cfg.logging.log_dir, "producao", "carga", "2026", "09", "01")),
                         "hora e dia vazios removidos")
        self.assertTrue(os.path.isdir(estranho), "fora do formato e ignorado")
        self.assertTrue(os.path.isdir(recente))
        self.assertTrue(os.path.isdir(running), "log de ticket RUNNING mantido (CR-007, R-32)")
        self.assertFalse(os.path.exists(os.path.join(self.cfg.logging.log_dir, "homologacao")),
                         "vazias ate o ambiente")
        self.assertTrue(os.path.isdir(interno), "interno/ intocada (CR-009)")
        self.assertTrue(os.path.isdir(fora), "link nao e seguido")
        self.assertEqual(p.resumo, ["logs_locais: 2 pastas de minuto removidas"])

    def test_falha_na_remocao_sai_com_3(self):
        self._minuto("producao/carga/2026/01/01/10/00")
        with mock.patch("log_paths.shutil.rmtree", side_effect=OSError(13, "Permission denied")):
            self.assertEqual(self._purge(_Banco()).executar(("logs_locais",)), purge_cli.SAIDA_LOCAIS)

    def test_caminho_real_fora_de_log_dir_nao_e_removido(self):
        velho = self._minuto("producao/carga/2026/01/01/10/00")
        plat = _Plat()
        plat.caminho_final = lambda c: "/outro" + c if c != self.cfg.logging.log_dir else c
        self.assertEqual(self._purge(_Banco(), plat=plat).executar(("logs_locais",)), purge_cli.SAIDA_LOCAIS)
        self.assertTrue(os.path.isdir(velho))


class TestSaida(_Base):

    def test_por_ambiente_com_o_usuario_de_execucao(self):
        base = os.path.join(self.raiz, "saida")
        os.makedirs(os.path.join(base, "producao"))
        cfg = _cfg(self.raiz, agent={"output_dir": base, "environments": ("PRODUCAO", "HOMOLOGACAO"),
                                     "exec_users": (("PRODUCAO", "sssprd"), ("HOMOLOGACAO", "ssshml"))})
        plat = _Plat(contagem=2)
        p = self._purge(_Banco(), plat=plat, cfg=cfg)
        self.assertEqual(p.executar(("saida",)), 0)
        self.assertEqual(plat.chamadas, [(os.path.join(base, "producao"), 7, "sssprd", False)],
                         "ambiente sem pasta e pulado")
        self.assertEqual(p.resumo, ["saida: 2 pastas de minuto removidas"])

    def test_desligada_e_falha(self):
        p = self._purge(_Banco())
        self.assertEqual(p.executar(("saida",)), 0)
        self.assertEqual(p.resumo, ["saida: desligada (output_dir vazio)"])
        base = os.path.join(self.raiz, "saida")
        os.makedirs(os.path.join(base, "producao"))
        cfg = _cfg(self.raiz, agent={"output_dir": base})
        self.assertEqual(self._purge(_Banco(), plat=_Plat(falhar=True), cfg=cfg).executar(("saida",)),
                         purge_cli.SAIDA_LOCAIS)


class TestMain(_Base):
    """A linha de comando: configuracao, trava local, conexao e resumo no stdout."""

    def _main(self, argv, banco=None, cfg=None, plat=None, segredos_erro=False):
        cfg = cfg or self.cfg
        banco = banco if banco is not None else _Banco()
        self.conexoes = []

        def conectar(_cfg, _segredos):
            self.conexoes.append(1)
            return _Conn(banco)
        saida = io.StringIO()
        carregar = mock.Mock(side_effect=purge_cli.sss_config.ConfigErro(motivo="x") if segredos_erro else None,
                             return_value=object())
        with mock.patch.object(purge_cli.sss_config, "obter_config", return_value=cfg), \
                mock.patch.object(purge_cli.sss_config, "carregar_segredos", carregar), \
                mock.patch.object(purge_cli.sss_logging, "configurar", return_value=self.log), \
                mock.patch.object(purge_cli.masking, "instalar_filtro_em_handlers"):
            codigo = purge_cli.main(argv, conectar=conectar, plat=plat or _Plat(), saida=saida)
        self.carregar = carregar
        return codigo, saida.getvalue()

    def test_execucao_real_com_trava_e_resumo(self):
        plat = _Plat()
        banco = _Banco(tickets=[(1, _dias(100), "CANCELLED")])
        codigo, texto = self._main(["--target", "tickets"], banco=banco, plat=plat)
        self.assertEqual(codigo, 0)
        self.assertEqual(plat.travas, [os.path.join(self.raiz, "work", "sss-purge.lock")])
        self.assertEqual(texto, "tickets: 1 linhas apagadas\n")
        self.assertEqual(banco.fechada, 1)
        self.assertEqual(self.carregar.call_args[1]["papel"], "agent", "[purge] password so no papel agente")

    def test_dry_run_sem_trava_e_com_aviso(self):
        plat = _Plat()
        codigo, texto = self._main(["--dry-run", "--target", "audit"], plat=plat)
        self.assertEqual(codigo, 0)
        self.assertEqual(plat.travas, [])
        self.assertFalse(os.path.exists(os.path.join(self.raiz, "work", "sss-purge.lock")))
        self.assertIn("dry-run: contagens estimadas", texto)

    def test_outro_purge_no_servidor(self):
        trava = os_platform.travar_instancia(os.path.join(self.raiz, "work", "sss-purge.lock"))
        self.addCleanup(os_platform.liberar_instancia, trava)
        codigo, texto = self._main([])
        self.assertEqual((codigo, texto, self.conexoes), (0, "", []))

    def test_configuracao_invalida(self):
        with mock.patch.object(purge_cli.sss_config, "obter_config",
                               side_effect=purge_cli.sss_config.ConfigErro(motivo="x")):
            self.assertEqual(purge_cli.main([], conectar=None), purge_cli.SAIDA_CONFIG)
        self.assertEqual(self._main([], cfg=_cfg(self.raiz, purge_user=None))[0], purge_cli.SAIDA_CONFIG)
        self.assertEqual(self._main(["--export-audit", os.path.join(self.raiz, "nao_existe")])[0],
                         purge_cli.SAIDA_CONFIG)
        self.assertEqual(self._main([], segredos_erro=True)[0], purge_cli.SAIDA_CONFIG)
        self.assertEqual(self.conexoes, [])

    def test_falha_ao_conectar(self):
        with mock.patch.object(purge_cli.sss_config, "obter_config", return_value=self.cfg), \
                mock.patch.object(purge_cli.sss_config, "carregar_segredos", return_value=object()), \
                mock.patch.object(purge_cli.sss_logging, "configurar", return_value=self.log), \
                mock.patch.object(purge_cli.masking, "instalar_filtro_em_handlers"):
            codigo = purge_cli.main([], conectar=mock.Mock(side_effect=RuntimeError("ORA-12541: no listener")),
                                    plat=_Plat(), saida=io.StringIO())
        self.assertEqual(codigo, purge_cli.SAIDA_BANCO)

    def test_alvo_invalido(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
            purge_cli._argumentos(["--target", "tudo"])


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestPurgeOracle(unittest.TestCase):
    """Purge real contra o Oracle (decisao 1a): conta do owner, so quando nada fora da fixture e elegivel."""

    DIAS = 30  # retencao dos tickets no teste; a auditoria usa o minimo, 365

    @classmethod
    def setUpClass(cls):
        import test_repo_contract as trc
        cls.trc = trc
        cls.contrato = trc._OracleContrato
        cls.contrato.setUpClass.__func__(cls)
        from _oracle_test_support import preparar_schema_descartavel
        preparar_schema_descartavel("agent")

    @classmethod
    def tearDownClass(cls):
        cls.contrato.tearDownClass.__func__(cls)

    def obter_repo(self, nome):
        return self.contrato.obter_repo(self, nome)

    def setUp(self):
        self.contrato.setUp(self)
        self._massa = self.trc._Massa(self.obter_repo)
        self.cat = self.obter_repo("catalogo")
        self.conn = self.cat._obter_conexao()
        self.addCleanup(self.conn.close)  # LIFO: fecha depois da limpeza
        self.addCleanup(self._limpar)
        self.tck, self.aud = self.cat.qualificar_tabela("tickets"), self.cat.qualificar_tabela("auditoria")
        self.aud_fixture = []
        self.tck_fixture = []  # todos os tickets da fixture, inclusive o que o purge apaga (auditoria deles)
        self.purges = []

    def _limpar(self):
        cur = self.conn.cursor()
        for aid in self.aud_fixture + self.purges:
            cur.execute("DELETE FROM " + self.aud + " WHERE id = :id", {"id": aid})
        # Auditoria dos tickets da fixture, inclusive o que o purge apagou (no compartilhado nao sobra nada).
        for tid in self.tck_fixture:
            cur.execute("DELETE FROM " + self.aud + " WHERE entity = 'tbsss_tickets' AND entity_id = :id", {"id": tid})
        self.conn.commit()
        self.contrato._limpar_massa(self)

    def _um(self, sql, **binds):
        cur = self.conn.cursor()
        cur.execute(sql, binds)
        return cur.fetchone()[0]

    def _executar(self, sql, **binds):
        cur = self.conn.cursor()
        cur.execute(sql, binds)
        self.conn.commit()

    def test_purge_real_so_dos_tickets_e_auditoria_da_fixture(self):
        m = self._massa
        amb, scr = m.ambiente("P"), m.script("p")
        login = m.usuario(m.perfil("P")["id"], "u")["login"]
        base = {"script_id": scr["id"], "environment": amb["name"], "requested_by": login, "priority": 2,
                "status": "PENDING", "submitted_params": "{}"}
        velho_ok, velho_pend, novo_ok = (m.ticket(actor=login, **base) for _ in range(3))
        self.tck_fixture = [velho_ok, velho_pend, novo_ok]
        for tid, status, dias in ((velho_ok, "SUCCESS", 40), (velho_pend, "PENDING", 40), (novo_ok, "SUCCESS", 5)):
            self._executar("UPDATE " + self.tck + " SET status = :s, created_at = SYSDATE - :d WHERE id = :id",
                           s=status, d=dias, id=tid)
        aid = self._um("SELECT " + RepoPurge.da_config(self.oracle_cfg)._seq_aud + ".NEXTVAL FROM DUAL")
        self._executar("INSERT INTO " + self.aud + " (id, actor, action, entity, detail, created_at)"
                       " VALUES (:id, :a, 'LOGIN', 'tbsss_users', 'fixture F9.1a', SYSDATE - 400)", id=aid, a=m.ator)
        self.aud_fixture.append(aid)
        # Guarda (decisao 1a): nada fora da fixture pode ser elegivel no esquema compartilhado.
        alheios_tck = self._um("SELECT COUNT(*) FROM " + self.tck + " WHERE created_at < SYSDATE - :d"
                               " AND status IN ('SUCCESS','FAILED','CANCELLED') AND id <> :id", d=self.DIAS, id=velho_ok)
        alheios_aud = self._um("SELECT COUNT(*) FROM " + self.aud + " WHERE created_at < SYSDATE - 365 AND id <> :id",
                               id=aid)
        if alheios_tck or alheios_aud:
            self.skipTest("%d tickets e %d linhas de auditoria fora da fixture seriam elegiveis"
                          % (alheios_tck, alheios_aud))
        cfg = self.oracle_cfg
        dono = "tst-f91a-%s" % m.suf
        cfg_purge = types.SimpleNamespace(
            agent=types.SimpleNamespace(agent_id=dono), oracle=cfg.oracle,
            retention=types.SimpleNamespace(ticket_retention_days=self.DIAS, audit_retention_days=365,
                                           purge_batch_size=1))
        marca = self._um("SELECT NVL(MAX(id), 0) FROM " + self.aud)
        logger = logging.getLogger("sss_test_purge_oracle")
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        # Dry-run primeiro: conta a fixture, nada muda.
        p = purge_cli.Purge(cfg_purge, self.conn, logger=logger)
        self.assertEqual(p.executar(("tickets", "auditoria"), dry_run=True), 0)
        self.assertEqual(p.resumo, ["tickets: 1 linhas elegiveis (estimativa)",
                                    "auditoria: 1 linhas elegiveis (estimativa)"])
        pasta = tempfile.mkdtemp(prefix="sss_test_purge_csv_")
        self.addCleanup(shutil.rmtree, pasta, True)
        p = purge_cli.Purge(cfg_purge, self.conn, logger=logger)
        codigo = p.executar(("tickets", "auditoria"), exportar=pasta)
        self.purges = [r[0] for r in self.conn.cursor().execute(
            "SELECT id FROM " + self.aud + " WHERE id > :m AND actor = 'SYSTEM:purge'", {"m": marca}).fetchall()]
        if p.resumo and "pulado" in p.resumo[0]:
            self.skipTest("concessao com outro no: %s" % p.resumo)
        self.assertEqual(codigo, 0)
        restantes = dict(self.conn.cursor().execute(
            "SELECT id, status FROM " + self.tck + " WHERE id IN (:a, :b, :c)",
            {"a": velho_ok, "b": velho_pend, "c": novo_ok}).fetchall())
        self.assertEqual(restantes, {velho_pend: "PENDING", novo_ok: "SUCCESS"})
        self.assertEqual(self._um("SELECT COUNT(*) FROM " + self.aud + " WHERE id = :id", id=aid), 0)
        with io.open(os.path.join(pasta, os.listdir(pasta)[0]), encoding="utf-8-sig", newline="") as f:
            self.assertEqual([l[0] for l in csv.reader(f, delimiter=";")][1:], [str(aid)], "exportada antes de sair")
        linhas = self.conn.cursor().execute(
            "SELECT entity, detail, entity_id FROM " + self.aud + " WHERE id > :m AND actor = 'SYSTEM:purge'"
            " ORDER BY id", {"m": marca}).fetchall()
        self.assertEqual(linhas, [("tbsss_tickets", "1 linhas", None), ("tbsss_audit", "1 linhas", None)])
        ctl = self.conn.cursor().execute("SELECT purge_owner, purge_lease_until FROM "
                                         + self.cat.qualificar_tabela("controle") + " WHERE id = 1").fetchone()
        self.assertEqual(tuple(ctl), (None, None), "concessao liberada (CR-008, R-27)")
        self._massa.criados["tickets"].remove(velho_ok)
        self.aud_fixture.remove(aid)
        print("\n[F9.1a] purge real: %s" % "; ".join(p.resumo))


if __name__ == "__main__":
    unittest.main()
