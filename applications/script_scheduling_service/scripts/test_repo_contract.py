# -*- coding: utf-8 -*-
"""Bateria de testes de conformidade para contratos de repositorio e backend FAKE.

Valida requisitos do prompt F0.4, README §2.5 e AGENTS.md §4, §5.5, §7:
1. CRUD basico de todos os agregados;
2. Unicidade de UKs gerando RepoViolacao;
3. CKs de conexao com '@' gerando RepoViolacao;
4. Imutabilidade de ambientes.nome e usuarios.login;
5. Cascatas de associacao (matriz, script_param, homologacao);
6. solicitar_cancelamento nos 3 retornos ('TERMINAL', 'CANCELADO', 'SINALIZADO');
7. Transicao concorrente perdida gerando RepoConflito;
8. perm_versao incrementando em alteracoes de perfil, matriz e usuario;
9. Paginacao estavel e deterministica com desempate por id;
10. Escopo de ambientes na listagem de tickets;
11. repo_factory com trava de ambiente (sss_env != DEV com FAKE lanca RuntimeError);
12. repo_factory com ORACLE lanca NotImplementedError;
13. Nenhum import repo_fake fora de repo_factory.py;
14. FAKE nao expos nenhum metodo publico alem dos definidos no contrato (paridade estrita);
15. Regressao fail-fast: repo_factory sem configuracao e FAKE com entrada nao numerica.
"""
import copy
import datetime
import os
import re
import unittest
from unittest import mock

import _testenv  # noqa: F401
from gluon import current

import repo_factory
from repo_agendamentos import RepoAgendamentos
from repo_agentes import RepoAgentes
from repo_auditoria import RepoAuditoria
from repo_catalogo import RepoCatalogo
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao
from repo_rbac import RepoRbac
from repo_tickets import RepoTickets
from repo_usuarios import RepoUsuarios


class BaseRepoContractTest(object):
    """Bateria de testes agnostica a backend, executada contra FAKE e ORACLE."""

    def test_01_crud_ambientes(self):
        cat = self.obter_repo("catalogo")
        # Insercao
        nome_amb = "TESTE_CRUD_%s" % int(datetime.datetime.now().timestamp() if hasattr(datetime.datetime.now(), 'timestamp') else 12345)
        amb = cat.ambientes_inserir({
            "nome": nome_amb,
            "descricao": "Ambiente de Teste CRUD",
            "conexao": "db-teste.local:1521/svc",
            "ativo": "S",
        })
        self.assertIsNotNone(amb.get("id"))
        self.assertEqual(amb["nome"], nome_amb)

        # Leitura
        obtido = cat.ambientes_obter(amb["id"])
        self.assertEqual(obtido["nome"], nome_amb)

        # Alteracao
        alterado = cat.ambientes_alterar(amb["id"], {
            "descricao": "Descricao alterada",
            "ativo": "N",
        })
        self.assertEqual(alterado["descricao"], "Descricao alterada")
        self.assertEqual(alterado["ativo"], "N")

        # Listagem
        lista = cat.ambientes_listar(filtros={"nome": nome_amb})
        self.assertEqual(lista["total"], 1)
        self.assertEqual(lista["itens"][0]["id"], amb["id"])

    def test_02_uk_duplicada_ambiente_perfil_script_usuario(self):
        cat = self.obter_repo("catalogo")
        rbac = self.obter_repo("rbac")
        usr = self.obter_repo("usuarios")

        # UK ambiente
        with self.assertRaises(RepoViolacao) as ctx:
            cat.ambientes_inserir({
                "nome": "PRODUCAO",
                "descricao": "Duplicado",
                "conexao": "db-prod2.local:1521/svc",
            })
        self.assertIn("uk_tbsss_amb_nome", str(ctx.exception.constraint or ""))

        # UK perfil
        with self.assertRaises(RepoViolacao) as ctx:
            rbac.perfis_inserir({
                "nome": "ADMINISTRADOR",
                "descricao": "Duplicado",
                "is_admin": "S",
            })
        self.assertIn("uk_tbsss_per_nome", str(ctx.exception.constraint or ""))

        # UK script
        with self.assertRaises(RepoViolacao) as ctx:
            cat.scripts_inserir({
                "nome": "carga_diaria",
                "descricao": "Duplicado",
                "comando_real": "/usr/bin/python3",
                "path_file": "carga_diaria.py",
            })
        self.assertIn("uk_tbsss_scr_nome", str(ctx.exception.constraint or ""))

        # UK usuario
        with self.assertRaises(RepoViolacao) as ctx:
            usr.inserir({
                "login": "admin",
                "nome": "Duplicado",
                "perfil_id": 1,
            })
        self.assertIn("uk_tbsss_usr_login", str(ctx.exception.constraint or ""))

    def test_03_ck_conexao_com_arroba(self):
        cat = self.obter_repo("catalogo")
        # Insercao com @ deve falhar (CK ck_tbsss_amb_conexao)
        with self.assertRaises(RepoViolacao) as ctx:
            cat.ambientes_inserir({
                "nome": "AMB_ARROBA",
                "descricao": "Invalido",
                "conexao": "usr:pwd@host:1521/svc",
            })
        self.assertIn("ck_tbsss_amb_conexao", str(ctx.exception.constraint or ""))

        # Alteracao com @ tambem deve falhar
        amb = cat.ambientes_listar(filtros={"nome": "HOMOLOGACAO"})["itens"][0]
        with self.assertRaises(RepoViolacao) as ctx:
            cat.ambientes_alterar(amb["id"], {"conexao": "app@host/svc"})
        self.assertIn("ck_tbsss_amb_conexao", str(ctx.exception.constraint or ""))

    def test_04_imutabilidade_nome_ambiente_e_login_usuario(self):
        cat = self.obter_repo("catalogo")
        usr = self.obter_repo("usuarios")

        amb = cat.ambientes_listar(filtros={"nome": "HOMOLOGACAO"})["itens"][0]
        with self.assertRaises(RepoViolacao) as ctx:
            cat.ambientes_alterar(amb["id"], {"nome": "NOVO_NOME_AMB"})
        self.assertIn("tr_tbsss_amb_bu", str(ctx.exception.constraint or ""))

        u = usr.obter_por_login("op.prod")
        with self.assertRaises(RepoViolacao) as ctx:
            usr.alterar(u["id"], {"login": "novo.login"})
        self.assertIn("tr_tbsss_usr_bu", str(ctx.exception.constraint or ""))

    def test_04b_ambiente_alteracao_condicional_e_auditoria_na_mesma_operacao(self):
        cat = self.obter_repo("catalogo")
        aud = self.obter_repo("auditoria")
        amb = cat.ambientes_listar(filtros={"nome": "HOMOLOGACAO"})["itens"][0]
        lido = {"descricao": amb["descricao"], "conexao": amb["conexao"], "ativo": amb["ativo"]}

        def total_aud():
            return aud.listar(filtros={"acao": "CAD_ALTERAR"}, pagina=1, tamanho=1)["total"]

        antes = total_aud()
        alterado = cat.ambientes_alterar(amb["id"], {"descricao": "Contrato"}, esperado=lido,
                                         auditoria={"ator": "admin", "ip": "10.0.0.1", "acao": "CAD_ALTERAR",
                                                    "detalhe": "descricao: x -> Contrato"})
        self.assertEqual(alterado["descricao"], "Contrato")
        self.assertEqual(total_aud(), antes + 1)
        ultimo = aud.listar(filtros={"acao": "CAD_ALTERAR"}, pagina=1, tamanho=1)["itens"][0]
        self.assertEqual((ultimo["entidade"], ultimo["entidade_id"], ultimo["ator"]),
                         ("tbsss_ambientes", amb["id"], "admin"))

        # 'lido' ficou obsoleto: o UPDATE condicional perde, nada muda e nada e auditado.
        with self.assertRaises(RepoConflito):
            cat.ambientes_alterar(amb["id"], {"descricao": "Perdedor"}, esperado=lido,
                                  auditoria={"ator": "admin", "ip": None, "acao": "CAD_ALTERAR", "detalhe": "x"})
        self.assertEqual(cat.ambientes_obter(amb["id"])["descricao"], "Contrato")
        self.assertEqual(total_aud(), antes + 1)

        # Violacao tambem nao grava auditoria nem altera colunas parcialmente.
        with self.assertRaises(RepoViolacao):
            cat.ambientes_alterar(amb["id"], {"descricao": "Parcial", "conexao": "a@b"},
                                  auditoria={"ator": "admin", "ip": None, "acao": "CAD_ALTERAR", "detalhe": "x"})
        self.assertEqual(cat.ambientes_obter(amb["id"])["descricao"], "Contrato")
        self.assertEqual(total_aud(), antes + 1)

        novo = cat.ambientes_inserir({"nome": "CONTRATO_AUD", "conexao": "ALIAS"},
                                     auditoria={"ator": "admin", "ip": None, "acao": "CAD_INSERIR", "detalhe": "y"})
        ins = aud.listar(filtros={"acao": "CAD_INSERIR"}, pagina=1, tamanho=1)["itens"][0]
        self.assertEqual((ins["entidade"], ins["entidade_id"]), ("tbsss_ambientes", novo["id"]))

    def test_05_cascata_associacao(self):
        cat = self.obter_repo("catalogo")
        rbac = self.obter_repo("rbac")

        # Homologacao de script
        s = cat.scripts_listar()["itens"][0]
        cat.homologacao_salvar(s["id"], [1])
        h1 = cat.homologacao_obter(s["id"])
        self.assertEqual(h1, [1])

        cat.homologacao_salvar(s["id"], [1, 2])
        h2 = cat.homologacao_obter(s["id"])
        self.assertEqual(sorted(h2), [1, 2])

        # Matriz de permissoes
        p = rbac.perfis_listar(filtros={"nome": "CONSULTA"})["itens"][0]
        v_antes = p["perm_versao"]
        rbac.matriz_salvar(p["id"], funcs=[1, 2], ambs=[1], scrs=[1, 2])
        m = rbac.matriz_obter(p["id"])
        self.assertEqual(sorted(m["funcs"]), [1, 2])
        self.assertEqual(sorted(m["ambs"]), [1])
        self.assertEqual(sorted(m["scrs"]), [1, 2])

        p_depois = rbac.perfis_obter(p["id"])
        self.assertGreater(p_depois["perm_versao"], v_antes)

    def test_06_solicitar_cancelamento_nos_tres_retornos(self):
        tck = self.obter_repo("tickets")

        # 1. PENDING -> CANCELADO
        tid_pend = tck.criar({
            "script_id": 1,
            "ambiente": "PRODUCAO",
            "solicitante": "admin",
            "status": "PENDING",
            "prioridade": 2,
        }, [])
        res1 = tck.solicitar_cancelamento(tid_pend, "admin", "10.0.0.1")
        self.assertEqual(res1, "CANCELADO")
        t1 = tck.obter(tid_pend)
        self.assertEqual(t1["status"], "CANCELLED")
        self.assertEqual(t1["cancel_requested"], "S")
        self.assertEqual(t1["status_motivo"], "CANCEL_USER")

        # 2. Já TERMINAL (CANCELLED) -> TERMINAL
        res2 = tck.solicitar_cancelamento(tid_pend, "admin", "10.0.0.1")
        self.assertEqual(res2, "TERMINAL")

        # 3. RUNNING -> SINALIZADO
        tid_run = tck.criar({
            "script_id": 1,
            "ambiente": "PRODUCAO",
            "solicitante": "admin",
            "status": "RUNNING",
            "prioridade": 2,
        }, [])
        res3 = tck.solicitar_cancelamento(tid_run, "admin", "10.0.0.1")
        self.assertEqual(res3, "SINALIZADO")
        t3 = tck.obter(tid_run)
        self.assertEqual(t3["status"], "RUNNING")
        self.assertEqual(t3["cancel_requested"], "S")

    def test_07_transicao_concorrente_perdida_gerando_repo_conflito(self):
        agd = self.obter_repo("agendamentos")
        regra = agd.listar()["itens"][0]
        data_correta = regra["proxima_execucao"]
        data_divergente = data_correta + datetime.timedelta(days=10)

        # Conflito otimista com proxima_execucao divergente
        with self.assertRaises(RepoConflito):
            agd.pausar(regra["id"], motivo="MANUAL", antiga_data=data_divergente)

        # Sucesso com proxima_execucao correta
        pausado = agd.pausar(regra["id"], motivo="MANUAL", antiga_data=data_correta)
        self.assertEqual(pausado["ativo"], "N")
        self.assertEqual(pausado["pausa_motivo"], "MANUAL")

    def test_08_perm_versao_incrementando(self):
        rbac = self.obter_repo("rbac")
        usr = self.obter_repo("usuarios")

        p = rbac.perfis_listar(filtros={"nome": "OPERADOR_PROD"})["itens"][0]
        v0 = p["perm_versao"]

        # Alteracao no perfil
        rbac.perfis_alterar(p["id"], {"descricao": "Nova descricao operacao"})
        v1 = rbac.perfis_obter(p["id"])["perm_versao"]
        self.assertEqual(v1, v0 + 1)

        # Alteracao na matriz
        rbac.matriz_salvar(p["id"], funcs=[1], ambs=[1], scrs=[1])
        v2 = rbac.perfis_obter(p["id"])["perm_versao"]
        self.assertEqual(v2, v1 + 1)

        # Alteracao de usuario trocando perfil ou desativando
        u = usr.obter_por_login("op.prod")
        usr.alterar(u["id"], {"ativo": "N"})
        v3 = rbac.perfis_obter(p["id"])["perm_versao"]
        self.assertGreaterEqual(v3, v2 + 1)

    def test_09_paginacao_estavel_e_deterministica(self):
        tck = self.obter_repo("tickets")
        pag1 = tck.listar(pagina=1, tamanho=10)
        pag2 = tck.listar(pagina=2, tamanho=10)

        self.assertEqual(pag1["pagina"], 1)
        self.assertEqual(pag1["tamanho"], 10)
        self.assertEqual(len(pag1["itens"]), 10)
        self.assertEqual(len(pag2["itens"]), 10)
        self.assertGreaterEqual(pag1["total"], 40)

        # Itens da pagina 1 nao devem sobrepor itens da pagina 2
        ids_p1 = {item["id"] for item in pag1["itens"]}
        ids_p2 = {item["id"] for item in pag2["itens"]}
        self.assertTrue(ids_p1.isdisjoint(ids_p2))

        # Repeticao da pagina 1 deve ser identica (estavel)
        pag1_repetida = tck.listar(pagina=1, tamanho=10)
        self.assertEqual(
            [i["id"] for i in pag1["itens"]],
            [i["id"] for i in pag1_repetida["itens"]]
        )

    def test_10_escopo_ambientes_na_listagem_tickets(self):
        tck = self.obter_repo("tickets")

        # Somente HOMOLOGACAO
        lista_hml = tck.listar(escopo_ambientes=["HOMOLOGACAO"], pagina=1, tamanho=50)
        for t in lista_hml["itens"]:
            self.assertEqual(t["ambiente"], "HOMOLOGACAO")

        # Somente PRODUCAO
        lista_prod = tck.listar(escopo_ambientes=["PRODUCAO"], pagina=1, tamanho=50)
        for t in lista_prod["itens"]:
            self.assertEqual(t["ambiente"], "PRODUCAO")

        # Total somado dos dois escopos disjuntos deve bater
        self.assertEqual(lista_hml["total"] + lista_prod["total"], 40)

    def test_11_log_ler_incremental(self):
        tck = self.obter_repo("tickets")
        # Ticket 11 possui log_output preenchido no seed
        texto, prox_off, terminal, truncado = tck.log_ler(11, offset=0, max_chars=20)
        self.assertEqual(len(texto), 20)
        self.assertEqual(prox_off, 20)
        self.assertFalse(terminal)
        self.assertFalse(truncado)

        # Leitura da segunda fatia
        texto2, prox_off2, _, _ = tck.log_ler(11, offset=prox_off, max_chars=20)
        self.assertNotEqual(texto, texto2)
        self.assertEqual(prox_off2, 40)


class TestRepoContractFake(unittest.TestCase, BaseRepoContractTest):
    """Executa a bateria de contratos contra o backend FAKE."""

    def setUp(self):
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()

    def obter_repo(self, nome):
        return repo_factory.obter(nome)


@unittest.skipUnless(os.environ.get("SSS_TEST_DSN"), "SSS_TEST_DSN nao configurado: teste contra ORACLE pulado")
class TestRepoContractOracle(unittest.TestCase, BaseRepoContractTest):
    """Executa a mesma bateria contra o backend ORACLE quando DSN fornecido."""

    def setUp(self):
        repo_factory.configurar({"app": {"data_backend": "ORACLE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()

    def obter_repo(self, nome):
        return repo_factory.obter(nome)


class TestRepoFactoryEIntegridade(unittest.TestCase):
    """Testes especificos da fabrica e regras estruturais do AGENTS.md."""

    def tearDown(self):
        repo_factory.configurar(None)
        repo_factory.reset_singletons()

    def test_fake_fora_de_dev_lanca_runtime_error(self):
        # FAKE com HML deve abortar com RuntimeError (README §2.5)
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "HML"}})
        with self.assertRaises(RuntimeError) as ctx:
            repo_factory.obter("usuarios")
        self.assertIn("data_backend FAKE e proibido fora de DEV", str(ctx.exception))

        # FAKE com PROD tambem deve abortar
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "PROD"}})
        with self.assertRaises(RuntimeError):
            repo_factory.obter("usuarios")

    def test_oracle_nao_implementado_lanca_not_implemented(self):
        repo_factory.configurar({"app": {"data_backend": "ORACLE", "sss_env": "DEV"}})
        with self.assertRaises(NotImplementedError) as ctx:
            repo_factory.obter("usuarios")
        self.assertIn("Backend ORACLE ainda nao implementado", str(ctx.exception))

    def test_nenhum_import_repo_fake_fora_de_repo_factory(self):
        """Verifica que nenhum modulo ou script fora de repo_factory importa repo_fake."""
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pattern = re.compile(r"^\s*(from|import)\s+.*repo_fake.*", re.MULTILINE)

        arquivos_violadores = []
        for root, dirs, files in os.walk(app_dir):
            # Ignora o proprio diretorio modules/repo_fake e cache
            norm_root = os.path.normpath(root)
            if norm_root.endswith("modules/repo_fake") or "modules/repo_fake/" in norm_root:
                continue
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            if ".git" in dirs:
                dirs.remove(".git")

            for f in files:
                if not f.endswith(".py"):
                    continue
                caminho = os.path.join(root, f)
                rel_path = os.path.relpath(caminho, app_dir)
                if rel_path == "modules/repo_factory.py":
                    continue

                with open(caminho, "r", encoding="utf-8") as arq:
                    conteudo = arq.read()
                    if pattern.search(conteudo):
                        arquivos_violadores.append(rel_path)

        self.assertEqual(
            arquivos_violadores, [],
            "Arquivos fora de repo_factory.py importando repo_fake: %s" % arquivos_violadores
        )

    def test_paridade_estrita_sem_metodos_extras_no_fake(self):
        """Verifica que as classes Fake nao expõem metodos publicos alem dos contratos."""
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()

        pares = [
            (RepoUsuarios, repo_factory.obter("usuarios")),
            (RepoRbac, repo_factory.obter("rbac")),
            (RepoCatalogo, repo_factory.obter("catalogo")),
            (RepoTickets, repo_factory.obter("tickets")),
            (RepoAgendamentos, repo_factory.obter("agendamentos")),
            (RepoAuditoria, repo_factory.obter("auditoria")),
            (RepoAgentes, repo_factory.obter("agentes")),
        ]

        for contrato_cls, fake_inst in pares:
            metodos_contrato = {
                m for m in dir(contrato_cls)
                if not m.startswith("_") and callable(getattr(contrato_cls, m))
            }
            metodos_fake = {
                m for m in dir(fake_inst)
                if not m.startswith("_") and callable(getattr(fake_inst, m))
            }

            extras = metodos_fake - metodos_contrato
            self.assertEqual(
                extras, set(),
                "Classe Fake %s expos metodos publicos fora do contrato: %s" % (
                    fake_inst.__class__.__name__, extras
                )
            )

    def test_retornos_nao_vazam_referencia_mutavel(self):
        """Verifica que o backend FAKE devolve copias independentes (deepcopy)."""
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()

        usr = repo_factory.obter("usuarios")
        u1 = usr.obter_por_login("admin")
        u1["nome"] = "Mutacao Indevida Externa"

        u2 = usr.obter_por_login("admin")
        self.assertNotEqual(u2["nome"], "Mutacao Indevida Externa")


class TestRegressaoFailFast(unittest.TestCase):
    """Regressao: fabrica sem padrao silencioso e FAKE sem coercao silenciosa de entrada."""

    def setUp(self):
        self._sss_cfg_anterior = getattr(current, "sss_cfg", None)
        current.sss_cfg = None
        repo_factory.configurar(None)
        repo_factory.reset_singletons()

    def tearDown(self):
        current.sss_cfg = self._sss_cfg_anterior
        repo_factory.configurar(None)
        repo_factory.reset_singletons()

    def test_sem_configuracao_falha_mesmo_com_variaveis_de_ambiente(self):
        with mock.patch.dict(os.environ, {"SSS_DATA_BACKEND": "FAKE", "SSS_ENV": "DEV"}):
            with self.assertRaises(RuntimeError) as ctx:
                repo_factory.obter("usuarios")
        self.assertIn("Configuracao ausente", str(ctx.exception))

    def test_configuracao_incompleta_falha(self):
        for cfg in ({}, {"app": {"sss_env": "DEV"}}, {"app": {"data_backend": "FAKE"}}):
            with self.subTest(cfg=cfg):
                repo_factory.configurar(cfg)
                with self.assertRaises(KeyError):
                    repo_factory.obter("usuarios")

    def test_usa_current_sss_cfg_quando_sem_override(self):
        current.sss_cfg = {"app": {"data_backend": "FAKE", "sss_env": "DEV"}}
        self.assertIsInstance(repo_factory.obter("usuarios"), RepoUsuarios)

        repo_factory.reset_singletons()
        current.sss_cfg = {"app": {"data_backend": "FAKE", "sss_env": "PROD"}}
        with self.assertRaises(RuntimeError):
            repo_factory.obter("usuarios")

    def test_paginacao_rejeita_entrada_nao_numerica(self):
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        usr = repo_factory.obter("usuarios")
        with self.assertRaises(ValueError):
            usr.listar(pagina="abc")
        with self.assertRaises(TypeError):
            usr.listar(tamanho=[])
        pag = usr.listar(pagina=None, tamanho=None)
        self.assertEqual((pag["pagina"], pag["tamanho"]), (1, 20))
        pag = usr.listar(pagina="0", tamanho="-5")
        self.assertEqual((pag["pagina"], pag["tamanho"]), (1, 20))

    def test_log_ler_rejeita_entrada_nao_numerica(self):
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        tck = repo_factory.obter("tickets")
        with self.assertRaises(ValueError):
            tck.log_ler(11, offset="x", max_chars=20)
        with self.assertRaises(TypeError):
            tck.log_ler(11, offset=None, max_chars=20)
        with self.assertRaises(ValueError):
            tck.log_ler(11, offset=0, max_chars="muito")
        self.assertEqual(tck.log_ler(11, offset=-3, max_chars=5)[0],
                         tck.log_ler(11, offset=0, max_chars=5)[0])
