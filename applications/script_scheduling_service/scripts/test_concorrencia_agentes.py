# -*- coding: utf-8 -*-
"""F8.3d: dois agentes reais (scripts/run_scheduler.py) contra o Oracle do instance/config.ini.

Com SSS_TEST_ORACLE=1 (README §2.5): esquema validado por preparar_schema_descartavel('agente') antes de DML;
ambiente, perfil, usuario, scripts e tickets so da fixture; cada agente com o proprio config.ini temporario
(agent_id, work_dir, log_dir e saida_dir proprios). Confere: nunca mais de 2 RUNNING do script de teto 2
(polling no banco), todos SUCCESS, cada ticket executado uma vez, saida DISPONIVEL gravada pelo agente dono,
cancelamento pela web encerrado pelo agente dono, heartbeat e parada pelo .stop, e nenhum processo orfao.
Limpa so os IDs criados (tickets, saidas em cascata, cadastros, agentes de teste e a auditoria deles).
"""
import _testenv  # noqa: F401

import configparser
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_SCHEDULER = os.path.join(APP, "scripts", "run_scheduler.py")
N_TICKETS = 10
TETO = 2
MARCA_LONGO = 3017  # sleep exclusivo do script longo, para achar orfaos pelo argv


class _DoisAgentesBase(unittest.TestCase):
    """Fixture de dois agentes reais (F8.3d, reaproveitada no F8.4e por test_ha_agentes_reais)."""

    PREFIXO_AGENTE = "tst-f83d"
    CONFIG_EXTRA = {}

    @classmethod
    def setUpClass(cls):
        import test_repo_contract as trc
        from _oracle_test_support import preparar_schema_descartavel
        preparar_schema_descartavel("agente")
        cls.trc = trc
        cls.contrato = trc._OracleContrato
        cls.contrato.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.contrato.tearDownClass.__func__(cls)

    def obter_repo(self, nome):
        return self.contrato.obter_repo(self, nome)

    def _limpar_massa(self):
        return self.contrato._limpar_massa(self)

    # ------------------------------------------------------------------ fixture

    def setUp(self):
        self.contrato.setUp(self)
        self.raiz = os.path.realpath(tempfile.mkdtemp(prefix="sss_f83d_"))
        self.addCleanup(shutil.rmtree, self.raiz, True)
        self.processos = []
        self.perfil = None
        self._massa = self.trc._Massa(self.obter_repo)
        self.agentes = []
        # Uma limpeza so, mesmo com falha no meio: agentes parados antes de apagar qualquer cadastro.
        self.addCleanup(self._limpar_tudo)
        m = self._massa
        self.amb = m.ambiente("C")
        scripts_dir = os.path.join(self.raiz, "scripts")
        os.mkdir(scripts_dir, 0o755)
        self.execucoes = os.path.join(self.raiz, "execucoes.txt")
        curto = self._arquivo(scripts_dir, "curto.sh",
                              "echo \"$SSS_TICKET_ID $SSS_AGENTE_ID\" >> %s\n"
                              "echo \"ticket $SSS_TICKET_ID\" > \"$SSS_SAIDA_DIR/resultado.txt\"\n"
                              "sleep 2\necho fim\n" % self.execucoes)
        longo = self._arquivo(scripts_dir, "longo.sh", "echo inicio\nsleep %d\n" % MARCA_LONGO)
        self.scr = m.script("curto", path_file=curto, max_qtd_parallel_env=TETO)
        self.scr_longo = m.script("longo", path_file=longo, max_qtd_parallel_env=1)
        cat, rbac = self.obter_repo("catalogo"), self.obter_repo("rbac")
        for s in (self.scr, self.scr_longo):
            cat.homologacao_salvar(s["id"], [self.amb["id"]], ator=m.ator)
        self.perfil = perfil = m.perfil("P")
        funcs = [f["id"] for f in rbac.funcionalidades_listar() if f["codigo"] in ("EXEC_SCRIPT", "VER_LOGS", "CANC_TICKET")]
        rbac.matriz_salvar(perfil["id"], funcs, [self.amb["id"]], [self.scr["id"], self.scr_longo["id"]], ator=m.ator)
        self.login = m.usuario(perfil["id"], "u")["login"]
        self.usuario_id = [u for u in m.criados["usuarios"]][-1]
        self.agentes = ["%s-%s-a" % (self.PREFIXO_AGENTE, m.suf), "%s-%s-b" % (self.PREFIXO_AGENTE, m.suf)]

    def tearDown(self):
        pass  # a limpeza e o _limpar_tudo (addCleanup), depois de derrubar os agentes

    def _limpar_tudo(self):
        self._derrubar_agentes()
        self._limpar_agentes()
        m = self._massa
        cat, rbac = self.obter_repo("catalogo"), self.obter_repo("rbac")
        if self.perfil is not None:
            rbac.matriz_salvar(self.perfil["id"], [], [], [], ator=m.ator)
        for sid in m.criados["scripts"]:
            cat.homologacao_salvar(sid, [], ator=m.ator)
        # Tickets gerados pelo desdobro das regras da fixture (F8.4e) entram na limpeza antes do usuario.
        for rid in m.criados["agendamentos"]:
            for (tid,) in self._consulta("SELECT id FROM {tck} WHERE agendamento_id = :r", r=rid):
                if tid not in m.criados["tickets"]:
                    m.anotar("tickets", tid)
        self._limpar_massa()

    def _arquivo(self, pasta, nome, corpo):
        caminho = os.path.join(pasta, nome)
        with open(caminho, "w") as f:
            f.write(corpo)
        os.chmod(caminho, 0o644)
        return caminho

    def _snapshot(self, scr):
        return json.dumps({"versao": 4, "script_id": scr["id"], "script_nome": scr["nome"], "interpretador": "SH",
                           "path_file": scr["path_file"], "tipo_param": "NOMEADO", "args": [], "respostas": {},
                           "sensiveis": [], "compilado_em": "2026-10-20 10:00:00"})

    def _ticket(self, scr):
        tid = self.obter_repo("tickets").criar({
            "script_id": scr["id"], "ambiente": self.amb["nome"], "solicitante": self.login, "status": "PENDING",
            "prioridade": 2, "parametros_enviados": self._snapshot(scr)}, [], ator=self.login)
        return self._massa.anotar("tickets", tid)

    def _config(self, agente):
        base = os.path.join(self.raiz, agente)
        pastas = dict((n, os.path.join(base, n)) for n in ("work", "logs", "saida"))
        for p in pastas.values():
            os.makedirs(p, 0o750, exist_ok=True)
        cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
        cp.read(os.path.join(APP, "instance", "config.ini"), encoding="utf-8")
        cp["agent"].update({"agent_id": agente, "ambientes_atendidos": self.amb["nome"], "work_dir": pastas["work"],
                            "usuarios_execucao": "", "exec_work_dir": "", "interpretadores": "SH=/bin/sh",
                            "max_parallel_jobs": "4", "orchestrator_interval_s": "1", "cancel_poll_interval_s": "1",
                            "saida_dir": pastas["saida"], "log_dir_min_livre_mb": "0"})
        for secao, valores in self.CONFIG_EXTRA.items():
            cp[secao].update(valores)
        cp["logging"]["log_dir"] = pastas["logs"]
        caminho = os.path.join(base, "config.ini")
        with open(caminho, "w", encoding="utf-8") as f:
            cp.write(f)
        return caminho, pastas

    def _subir(self, agente):
        caminho, pastas = self._config(agente)
        saida = open(os.path.join(self.raiz, agente + ".out"), "w")
        self.addCleanup(saida.close)
        p = subprocess.Popen([sys.executable, RUN_SCHEDULER, "--config", caminho], cwd=APP, stdout=saida,
                             stderr=subprocess.STDOUT, start_new_session=True)
        self.processos.append((agente, p, pastas))
        return p, pastas

    def _derrubar_agentes(self):
        for agente, p, pastas in self.processos:
            if p.poll() is None:
                open(os.path.join(pastas["work"], "sss-%s.stop" % agente), "w").close()
        for agente, p, _pastas in self.processos:
            try:
                p.wait(60)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, 9)
                p.wait(10)

    def _limpar_agentes(self):
        """Linhas de tbsss_agentes dos agentes de teste e a auditoria deles (AGENTE_INICIO/AGENTE_FIM)."""
        cat = self.obter_repo("catalogo")
        conn = cat._obter_conexao()
        try:
            cur = conn.cursor()
            agt, aud = cat.qualificar_tabela("agentes"), cat.qualificar_tabela("auditoria")
            for codigo in self.agentes:
                cur.execute("SELECT id FROM " + agt + " WHERE codigo = :c", c=codigo)
                for (aid,) in cur.fetchall():
                    cur.execute("DELETE FROM " + aud + " WHERE entidade = 'tbsss_agentes' AND entidade_id = :id", id=aid)
                    cur.execute("DELETE FROM " + agt + " WHERE id = :id", id=aid)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ leituras

    def _consulta(self, sql, **binds):
        cat = self.obter_repo("catalogo")
        conn = cat._obter_conexao()
        try:
            cur = conn.cursor()
            cur.execute(sql.format(tck=cat.qualificar_tabela("tickets"), agt=cat.qualificar_tabela("agentes"),
                                   sai=cat.qualificar_tabela("ticket_saida")), binds)
            return cur.fetchall()
        finally:
            conn.close()

    def _tickets(self, ids):
        linhas = self._consulta("SELECT id, status, status_motivo, return_code, agente_id, process_id FROM {tck}"
                                " WHERE script_id IN (:a, :b)", a=self.scr["id"], b=self.scr_longo["id"])
        return dict((r[0], r[1:]) for r in linhas if r[0] in ids)

    def _pastas_de_saida(self, ids):
        nomes = set("ticket_%d" % t for t in ids)
        return [os.path.join(r, d) for _a, _p, pastas in self.processos
                for r, ds, _arqs in os.walk(pastas["saida"]) for d in ds if d in nomes]

    def _esperar(self, condicao, prazo, passo=0.2):
        limite = time.monotonic() + prazo
        while time.monotonic() < limite:
            if condicao():
                return True
            time.sleep(passo)
        return condicao()


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestConcorrenciaDoisAgentes(_DoisAgentesBase):

    def test_dois_agentes_teto_saida_cancelamento_e_parada(self):
        curtos = [self._ticket(self.scr) for _i in range(N_TICKETS)]
        longo = self._ticket(self.scr_longo)
        for agente in self.agentes:
            self._subir(agente)

        # 1. Teto entre agentes: polling no banco ate todos os curtos terminarem.
        max_running = 0
        limite = time.monotonic() + 180
        while time.monotonic() < limite:
            rodando = self._consulta("SELECT COUNT(*) FROM {tck} WHERE script_id = :s AND status = 'RUNNING'",
                                     s=self.scr["id"])[0][0]
            max_running = max(max_running, rodando)
            estado = self._tickets(set(curtos))
            if all(e[0] in ("SUCCESS", "FAILED", "CANCELLED") for e in estado.values()):
                break
            for agente, p, _pastas in self.processos:
                self.assertIsNone(p.poll(), "agente %s caiu (codigo %s)" % (agente, p.poll()))
            time.sleep(0.2)
        estado = self._tickets(set(curtos))
        self.assertLessEqual(max_running, TETO, "teto de %d respeitado entre os dois agentes" % TETO)
        self.assertEqual(sorted(e[:3] for e in estado.values()), [("SUCCESS", "EXIT_OK", 0)] * N_TICKETS)
        donos = dict((tid, e[3]) for tid, e in estado.items())
        self.assertTrue(set(donos.values()) <= set(self.agentes))

        # 2. Cada ticket executado uma unica vez, pelo agente dono.
        with open(self.execucoes) as f:
            execucoes = [linha.split() for linha in f.read().splitlines()]
        self.assertEqual(sorted(int(t) for t, _a in execucoes), sorted(curtos))
        self.assertEqual(dict((int(t), a) for t, a in execucoes), donos)
        distribuicao = dict((a, sum(1 for d in donos.values() if d == a)) for a in self.agentes)
        print("\n[F8.3d] distribuicao: %s; maximo RUNNING simultaneos: %d" % (distribuicao, max_running))

        # 3. Saida (CR-012): DISPONIVEL para cada ticket, com o zip do proprio ticket e a pasta removida.
        self.assertTrue(self._esperar(lambda: len(self._consulta(
            "SELECT ticket_id FROM {sai} WHERE ticket_id IN (%s) AND situacao = 'DISPONIVEL'"
            % ", ".join(str(t) for t in curtos))) == N_TICKETS, 60), "saidas DISPONIVEL")
        tickets = self.obter_repo("tickets")
        for tid in curtos:
            meta = tickets.saida_obter(tid)
            self.assertEqual((meta["agente_id"], meta["qtd_arquivos"]), (donos[tid], 1))
            dados = tickets.saida_ler(tid, 0, meta["tamanho_bytes"])
            self.assertEqual(zipfile.ZipFile(io.BytesIO(dados)).read("resultado.txt"), b"ticket %d\n" % tid)
        self.assertEqual(self._pastas_de_saida(set(curtos)), [], "pastas de saida dos curtos removidas")

        # 4. Cancelamento pela web: o agente dono encerra o ticket longo.
        self.assertTrue(self._esperar(lambda: (self._tickets({longo}).get(longo) or ("",))[0] == "RUNNING"
                                      and self._tickets({longo})[longo][4] is not None, 60), "longo RUNNING com PID")
        dono_longo = self._tickets({longo})[longo][3]
        self.assertIn(tickets.solicitar_cancelamento(longo, self.login, "127.0.0.1"), ("SINALIZADO", "CANCELADO"))
        self.assertTrue(self._esperar(lambda: self._tickets({longo})[longo][0] == "CANCELLED", 60), "cancelado")
        self.assertEqual(self._tickets({longo})[longo][1:4], ("CANCEL_USER", -1, dono_longo))
        # A saida do longo ficou vazia: nada gravado e a pasta removida (README §8.13).
        self.assertTrue(self._esperar(lambda: self._pastas_de_saida({longo}) == [], 30), "pasta vazia removida")
        self.assertIsNone(tickets.saida_obter(longo))

        # 5. Heartbeat e configuracao critica iguais nos dois agentes ativos.
        agentes = self._consulta("SELECT codigo, status, heartbeat_at, config_criticos FROM {agt}"
                                 " WHERE codigo IN (:a, :b)", a=self.agentes[0], b=self.agentes[1])
        self.assertEqual(sorted((r[0], r[1]) for r in agentes), [(a, "ATIVO") for a in sorted(self.agentes)])
        agora = self._consulta("SELECT SYSDATE FROM DUAL")[0][0]
        for codigo, _st, hb, _cc in agentes:
            self.assertLess((agora - hb).total_seconds(), 60, "heartbeat recente de %s" % codigo)
        self.assertEqual(len(set(r[3] for r in agentes)), 1)

        # 6. Parada pelo .stop: os dois saem com 0 e ficam PARADO.
        for agente, _p, pastas in self.processos:
            open(os.path.join(pastas["work"], "sss-%s.stop" % agente), "w").close()
        for agente, p, _pastas in self.processos:
            self.assertEqual(p.wait(60), 0, "saida de %s" % agente)
        parados = self._consulta("SELECT codigo, status FROM {agt} WHERE codigo IN (:a, :b)",
                                 a=self.agentes[0], b=self.agentes[1])
        self.assertEqual(sorted(parados), [(a, "PARADO") for a in sorted(self.agentes)])

        # 7. Nenhum processo orfao dos scripts do teste.
        ps = subprocess.run(["ps", "-eo", "args"], stdout=subprocess.PIPE).stdout.decode("utf-8", "replace")
        linhas = ps.splitlines()
        self.assertEqual([l for l in linhas if l.strip() == "sleep %d" % MARCA_LONGO], [], "orfao do script longo")
        self.assertEqual([l for l in linhas if self.raiz in l and "run_scheduler" in l], [], "agente vivo")


if __name__ == "__main__":
    unittest.main()
