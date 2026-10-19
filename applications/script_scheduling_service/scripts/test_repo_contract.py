# -*- coding: utf-8 -*-
"""Bateria de testes de conformidade para contratos de repositorio e backend FAKE.

Valida requisitos do prompt F0.4, README §2.5 e AGENTS.md §4, §5.5, §7:
1. CRUD basico de todos os agregados;
2. Unicidade de UKs gerando RepoViolacao;
3. CKs de conexao com '@' gerando RepoViolacao;
4. Imutabilidade de ambientes.nome e usuarios.login;
5. Cascatas de associacao (matriz, script_param, homologacao);
6. solicitar_cancelamento nos 3 retornos ('TERMINAL', 'CANCELADO', 'SINALIZADO');
7. Transicao concorrente perdida gerando RepoConflito; CKs, UPDATE condicional e auditoria de agendamentos;
8. perm_versao incrementando em alteracoes de perfil, matriz e usuario;
9. Paginacao estavel e deterministica com desempate por id;
10. Escopo de ambientes na listagem de tickets;
11. repo_factory com trava de ambiente (sss_env != DEV com FAKE lanca RuntimeError);
12. repo_factory rejeita apenas o proximo agregado Oracle ainda nao implementado (F7.3 incremental);
13. Nenhum import repo_fake fora de repo_factory.py;
14. FAKE nao expos nenhum metodo publico alem dos definidos no contrato (paridade estrita);
15. Regressao fail-fast: repo_factory sem configuracao e FAKE com entrada nao numerica;
16. Colunas de registro (CR-006): inclusao, alteracao, ator obrigatorio, rotina tecnica e vinculos por diferenca.
"""
import collections
import copy
import datetime
import os
import re
import time
import unittest
from unittest import mock

import _testenv  # noqa: F401
from gluon import current

import repo_factory
import sql_ident
from repo_agendamentos import RepoAgendamentos
from repo_agentes import RepoAgentes
from repo_auditoria import RepoAuditoria
from repo_catalogo import RepoCatalogo
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao
from repo_rbac import RepoRbac
from repo_tickets import RepoTickets
from repo_usuarios import RepoUsuarios


class _Massa(object):
    """Dados proprios de um teste, criados pelos repositorios (sem depender do seed do FAKE).

    Os nomes levam um sufixo unico; os IDs criados ficam anotados por entidade, na ordem de
    remocao (tickets antes de agendamentos, usuarios antes de perfis, scripts antes de parametros).
    """

    ORDEM = ("tickets", "agendamentos", "usuarios", "perfis", "scripts", "parametros", "ambientes")

    def __init__(self, obter_repo):
        self._r = obter_repo
        self.suf = "%08d" % (int(time.time() * 1000000) % 100000000)
        self.ator = "tst" + self.suf
        self.criados = collections.OrderedDict((ent, []) for ent in self.ORDEM)
        self._cenario = None

    def anotar(self, entidade, id):
        self.criados[entidade].append(id)
        return id

    def ambiente(self, rotulo="A", **extra):
        dados = dict({"nome": "TST_%s_%s" % (self.suf, rotulo), "descricao": "Ambiente de teste"}, **extra)
        amb = self._r("catalogo").ambientes_inserir(dados, ator=self.ator)
        self.anotar("ambientes", amb["id"])
        return amb

    def perfil(self, rotulo="P", **extra):
        per = self._r("rbac").perfis_inserir(dict({"nome": "TST_%s_%s" % (self.suf, rotulo), "is_admin": "N"}, **extra),
                                             ator=self.ator)
        self.anotar("perfis", per["id"])
        return per

    def usuario(self, perfil_id, rotulo="u", **extra):
        dados = dict({"login": "tst.%s.%s" % (self.suf, rotulo), "nome": "Usuario de teste",
                      "senha_hash": "pbkdf2_sha256$1$00$00", "perfil_id": perfil_id, "ativo": "S"}, **extra)
        u = self._r("usuarios").inserir(dados, ator=self.ator)
        self.anotar("usuarios", u["id"])
        return u

    def parametro(self, rotulo="a", **extra):
        dados = dict({"codigo": "tst_%s_%s" % (self.suf, rotulo), "label": "Parametro %s" % rotulo,
                      "tipo_componente": "TEXT", "param_nomeado": "--tst%s%s" % (self.suf, rotulo)}, **extra)
        prm = self._r("catalogo").parametros_inserir(dados, ator=self.ator)
        self.anotar("parametros", prm["id"])
        return prm

    def script(self, rotulo="s", **extra):
        dados = dict({"nome": "tst_scr_%s_%s" % (self.suf, rotulo), "interpretador": "SH", "tipo_param": "NOMEADO",
                      "path_file": "/opt/tst/%s_%s.sh" % (self.suf, rotulo)}, **extra)
        scr = self._r("catalogo").scripts_inserir(dados, ator=self.ator)
        self.anotar("scripts", scr["id"])
        return scr

    def agendamento(self, script_id, ambiente, usuario_id, rotulo="r", **extra):
        dados = dict({"nome": "TST %s %s" % (self.suf, rotulo), "script_id": script_id, "ambiente": ambiente,
                      "usuario_id": usuario_id, "prioridade": 2, "tipo_recorrencia": "DIARIA",
                      "hora_execucao": "03:00", "parametros_json": "{}",
                      "data_inicio": datetime.datetime(2026, 1, 15, 10, 0),
                      "proxima_execucao": datetime.datetime(2030, 1, 16, 3, 0)}, **extra)
        regra = self._r("agendamentos").inserir(dados, ator=self.ator)
        self.anotar("agendamentos", regra["id"])
        return regra

    def ticket(self, respostas=(), ator=None, **dados):
        tid = self._r("tickets").criar(dados, list(respostas), ator=ator)
        return self.anotar("tickets", tid)

    def cenario(self):
        """Dois ambientes, um perfil comum com dois usuarios, dois parametros com flag e um script
        NOMEADO homologado no primeiro ambiente, com os dois parametros vinculados."""
        if self._cenario is None:
            c = {}
            c["amb1"], c["amb2"] = self.ambiente("A"), self.ambiente("B")
            c["perfil"] = self.perfil("P")
            c["u1"], c["u2"] = self.usuario(c["perfil"]["id"], "u1"), self.usuario(c["perfil"]["id"], "u2")
            c["prm_a"], c["prm_b"] = self.parametro("a"), self.parametro("b")
            c["scr"] = self.script("s")
            cat = self._r("catalogo")
            cat.homologacao_salvar(c["scr"]["id"], [c["amb1"]["id"]], ator=self.ator)
            cat.script_params_salvar(c["scr"]["id"], [
                {"parametro_id": c["prm_a"]["id"], "ordem": 1, "obrigatorio": "S"},
                {"parametro_id": c["prm_b"]["id"], "ordem": 2, "obrigatorio": "N"}], ator=self.ator)
            c["login"] = c["u1"]["login"]
            c["ticket_base"] = {"script_id": c["scr"]["id"], "ambiente": c["amb1"]["nome"],
                                "solicitante": c["login"], "status": "PENDING", "prioridade": 2}
            self._cenario = c
        return self._cenario


class BaseRepoContractTest(object):
    """Bateria agnostica a backend, executada contra FAKE e ORACLE com dados proprios de cada teste.

    Nenhum teste usa nomes ou IDs do seed nem altera cadastros que nao criou. As auditorias sao
    conferidas pela entidade e pelo id do proprio registro (imunes a outros usos do banco) e os nomes
    de constraint seguem o prefixo configurado.
    """

    @property
    def m(self):
        if getattr(self, "_massa", None) is None:
            self._massa = _Massa(self.obter_repo)
        return self._massa

    def cn(self, tipo, entidade, sufixo):
        """Nome da constraint/indice/trigger com o prefixo do repositorio em uso (FAKE: tbsss_)."""
        prefixo = getattr(self.obter_repo("catalogo"), "_prefixo", None) or "tbsss_"
        return "%s_%s%s_%s" % (tipo, prefixo, sql_ident.TABELAS[entidade]["abrev"], sufixo)

    def aud_total(self, acao, entidade, entidade_id):
        return self.obter_repo("auditoria").listar(
            filtros={"acao": acao, "entidade": entidade, "entidade_id": entidade_id}, pagina=1, tamanho=1)["total"]

    def aud_ultima(self, acao, entidade, entidade_id):
        return self.obter_repo("auditoria").listar(
            filtros={"acao": acao, "entidade": entidade, "entidade_id": entidade_id}, pagina=1, tamanho=1)["itens"][0]

    def test_ocorrencia_duplicada_recusada_sem_alterar_ticket(self):
        c = self.m.cenario()
        tickets = self.obter_repo("tickets")
        regra = self.m.agendamento(c["scr"]["id"], c["amb1"]["nome"], c["u1"]["id"])
        dados = {"script_id": c["scr"]["id"], "ambiente": c["amb1"]["nome"], "solicitante": c["login"],
                 "agendamento_id": regra["id"], "scheduled_at": datetime.datetime(2030, 1, 2)}
        primeiro_id = self.m.ticket(ator="teste", **dados)
        primeiro = tickets.obter(primeiro_id)
        with self.assertRaises(RepoViolacao) as erro:
            self.m.ticket(ator="teste", **dados)
        self.assertEqual(erro.exception.constraint, self.cn("ix", "tickets", "ocor"))
        self.assertEqual(tickets.obter(primeiro["id"]), primeiro)
        self.m.ticket(ator="teste", **dict(dados, scheduled_at=datetime.datetime(2030, 1, 3)))
        self.m.ticket(ator="teste", **dict(dados, agendamento_id=None))
        self.m.ticket(ator="teste", **dict(dados, agendamento_id=None))

    def test_01_crud_ambientes(self):
        cat = self.obter_repo("catalogo")
        amb = self.m.ambiente("CRUD", conexao="db-teste.local:1521/svc")
        self.assertIsNotNone(amb.get("id"))
        self.assertEqual(cat.ambientes_obter(amb["id"])["nome"], amb["nome"])
        alterado = cat.ambientes_alterar(amb["id"], {"descricao": "Descricao alterada", "ativo": "N"}, ator="teste")
        self.assertEqual((alterado["descricao"], alterado["ativo"]), ("Descricao alterada", "N"))
        lista = cat.ambientes_listar(filtros={"nome": amb["nome"]})
        self.assertEqual(lista["total"], 1)
        self.assertEqual(lista["itens"][0]["id"], amb["id"])

    def test_02_uk_duplicada_ambiente_perfil_script_usuario(self):
        c = self.m.cenario()
        cat, rbac, usr = self.obter_repo("catalogo"), self.obter_repo("rbac"), self.obter_repo("usuarios")
        with self.assertRaises(RepoViolacao) as ctx:
            cat.ambientes_inserir({"nome": c["amb1"]["nome"], "conexao": "db-prod2.local:1521/svc"}, ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("uk", "ambientes", "nome"))
        with self.assertRaises(RepoViolacao) as ctx:
            rbac.perfis_inserir({"nome": c["perfil"]["nome"], "is_admin": "N"}, ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("uk", "perfis", "nome"))
        with self.assertRaises(RepoViolacao) as ctx:
            cat.scripts_inserir({"nome": c["scr"]["nome"], "interpretador": "PYTHON3",
                                 "path_file": "/opt/tst/dup.py"}, ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("uk", "scripts", "nome"))
        # CK de path_file (CR-005 R-g): absoluto, sem '..', '//' nem '\'.
        with self.assertRaises(RepoViolacao) as ctx:
            cat.scripts_inserir({"nome": "tst_%s_path" % self.m.suf, "interpretador": "PYTHON3",
                                 "path_file": "x.py"}, ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("ck", "scripts", "path"))
        with self.assertRaises(RepoViolacao) as ctx:
            usr.inserir({"login": c["login"], "nome": "Duplicado", "senha_hash": "h",
                         "perfil_id": c["perfil"]["id"]}, ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("uk", "usuarios", "login"))

    def test_03_ck_conexao_com_arroba(self):
        cat = self.obter_repo("catalogo")
        with self.assertRaises(RepoViolacao) as ctx:
            cat.ambientes_inserir({"nome": "TST_%s_ARROBA" % self.m.suf, "conexao": "usr:pwd@host:1521/svc"},
                                  ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("ck", "ambientes", "conexao"))
        amb = self.m.ambiente("ARR")
        with self.assertRaises(RepoViolacao) as ctx:
            cat.ambientes_alterar(amb["id"], {"conexao": "app@host/svc"}, ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("ck", "ambientes", "conexao"))

    def test_04_imutabilidade_nome_ambiente_e_login_usuario(self):
        c = self.m.cenario()
        with self.assertRaises(RepoViolacao) as ctx:
            self.obter_repo("catalogo").ambientes_alterar(c["amb1"]["id"], {"nome": "TST_%s_NOVO" % self.m.suf},
                                                          ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("tr", "ambientes", "bu"))
        with self.assertRaises(RepoViolacao) as ctx:
            self.obter_repo("usuarios").alterar(c["u1"]["id"], {"login": "tst.%s.novo" % self.m.suf}, ator="teste")
        self.assertEqual(ctx.exception.constraint, self.cn("tr", "usuarios", "bu"))

    def test_04b_ambiente_alteracao_condicional_e_auditoria_na_mesma_operacao(self):
        cat = self.obter_repo("catalogo")
        amb = self.m.ambiente("AUD")
        lido = {"descricao": amb["descricao"], "conexao": amb["conexao"], "ativo": amb["ativo"]}
        alterado = cat.ambientes_alterar(amb["id"], {"descricao": "Contrato"}, esperado=lido,
                                         auditoria={"ator": "admin", "ip": "10.0.0.1", "acao": "CAD_ALTERAR",
                                                    "detalhe": "descricao: x -> Contrato"})
        self.assertEqual(alterado["descricao"], "Contrato")
        self.assertEqual(self.aud_total("CAD_ALTERAR", "tbsss_ambientes", amb["id"]), 1)
        self.assertEqual(self.aud_ultima("CAD_ALTERAR", "tbsss_ambientes", amb["id"])["ator"], "admin")

        # 'lido' ficou obsoleto: o UPDATE condicional perde, nada muda e nada e auditado.
        with self.assertRaises(RepoConflito):
            cat.ambientes_alterar(amb["id"], {"descricao": "Perdedor"}, esperado=lido,
                                  auditoria={"ator": "admin", "ip": None, "acao": "CAD_ALTERAR", "detalhe": "x"})
        self.assertEqual(cat.ambientes_obter(amb["id"])["descricao"], "Contrato")
        # Violacao tambem nao grava auditoria nem altera colunas parcialmente.
        with self.assertRaises(RepoViolacao):
            cat.ambientes_alterar(amb["id"], {"descricao": "Parcial", "conexao": "a@b"},
                                  auditoria={"ator": "admin", "ip": None, "acao": "CAD_ALTERAR", "detalhe": "x"})
        self.assertEqual(cat.ambientes_obter(amb["id"])["descricao"], "Contrato")
        self.assertEqual(self.aud_total("CAD_ALTERAR", "tbsss_ambientes", amb["id"]), 1)

        novo = cat.ambientes_inserir({"nome": "TST_%s_CAUD" % self.m.suf, "conexao": "ALIAS"},
                                     auditoria={"ator": "admin", "ip": None, "acao": "CAD_INSERIR", "detalhe": "y"})
        self.m.anotar("ambientes", novo["id"])
        self.assertEqual(self.aud_total("CAD_INSERIR", "tbsss_ambientes", novo["id"]), 1)

    def test_04c_perfil_conflito_e_matriz_condicional(self):
        """Conflito sem incremento e matriz condicional (o ultimo admin fica em TestUltimoAdmin*)."""
        c = self.m.cenario()
        rbac = self.obter_repo("rbac")
        per = c["perfil"]
        func_ids = [f["id"] for f in rbac.funcionalidades_listar()][:2]
        rbac.matriz_salvar(per["id"], func_ids, [c["amb1"]["id"]], [c["scr"]["id"]], ator="teste")
        atual = rbac.perfis_obter(per["id"])
        versao = atual["perm_versao"]

        with self.assertRaises(RepoConflito):
            rbac.perfis_alterar(per["id"], {"descricao": "x"}, esperado={"descricao": "outra"}, ator="teste")
        self.assertEqual(rbac.perfis_obter(per["id"])["perm_versao"], versao)

        matriz = rbac.matriz_obter(per["id"])
        with self.assertRaises(RepoConflito):
            rbac.matriz_salvar(per["id"], [], [], [], perm_versao_esperada=versao + 7, ator="teste")
        with self.assertRaises(RepoViolacao):
            rbac.matriz_salvar(per["id"], [999999], matriz["ambs"], matriz["scrs"], perm_versao_esperada=versao,
                               ator="teste")
        self.assertEqual(rbac.matriz_obter(per["id"]), matriz)
        self.assertEqual(rbac.perfis_obter(per["id"])["perm_versao"], versao)

        nova = rbac.matriz_salvar(per["id"], [], matriz["ambs"], matriz["scrs"], perm_versao_esperada=versao,
                                  auditoria={"ator": "admin", "ip": None, "acao": "PERM_ALTERAR", "detalhe": "-VER_LOGS"})
        self.assertEqual(nova["funcs"], [])
        self.assertEqual(rbac.perfis_obter(per["id"])["perm_versao"], versao + 1)
        self.assertEqual(self.aud_total("PERM_ALTERAR", "tbsss_perfis", per["id"]), 1)

    def test_04d_usuario_conflito_auditoria_login_e_filtro_bloqueio(self):
        """Conflito, auditoria, login e filtro de bloqueio (o ultimo admin fica em TestUltimoAdmin*)."""
        c = self.m.cenario()
        usr = self.obter_repo("usuarios")
        alvo = c["u2"]
        with self.assertRaises(RepoConflito):
            usr.alterar(alvo["id"], {"nome": "X"}, esperado={"nome": "outro"}, ator="teste")
        self.assertEqual(usr.obter_por_id(alvo["id"])["nome"], alvo["nome"])

        usr.alterar(alvo["id"], {"nome": "Consulta Contrato"}, esperado={"nome": alvo["nome"]},
                    auditoria={"ator": "admin", "ip": None, "acao": "CAD_ALTERAR", "detalhe": "nome"})
        usr.definir_senha(alvo["id"], "pbkdf2_sha256$1$00$00",
                          auditoria={"ator": "admin", "ip": None, "acao": "CAD_ALTERAR", "detalhe": "senha redefinida"})
        usr.desbloquear(alvo["id"], auditoria={"ator": "admin", "ip": None, "acao": "CAD_ALTERAR", "detalhe": "d"})
        self.assertEqual(self.aud_total("CAD_ALTERAR", "tbsss_usuarios", alvo["id"]), 3)

        # CR-003 P3: falha/sucesso de login com auditoria na mesma operacao e bloqueio pelo relogio do banco.
        inicio = usr.agora()
        reg = usr.registrar_falha_login(alvo["login"], bloqueio_s=60, auditoria=[
            {"ator": alvo["login"], "ip": None, "acao": "LOGIN_FALHA", "detalhe": "f"},
            {"ator": alvo["login"], "ip": None, "acao": "LOGIN_BLOQUEIO", "detalhe": "b"}])
        self.assertGreaterEqual(reg["bloqueado_ate"], inicio + datetime.timedelta(seconds=60))
        self.assertEqual(self.aud_total("LOGIN_FALHA", "tbsss_usuarios", alvo["id"]), 1)
        self.assertEqual(self.aud_total("LOGIN_BLOQUEIO", "tbsss_usuarios", alvo["id"]), 1)
        reg = usr.registrar_sucesso_login(alvo["login"], novo_hash="pbkdf2_sha256$2$00$00",
                                          auditoria={"ator": alvo["login"], "ip": None, "acao": "LOGIN_OK", "detalhe": "ok"})
        self.assertEqual((reg["tentativas_falha"], reg["bloqueado_ate"]), (0, None))
        self.assertEqual(reg["senha_hash"], "pbkdf2_sha256$2$00$00")
        self.assertGreaterEqual(reg["ultimo_login"], inicio)
        self.assertEqual(reg["ultimo_login"].microsecond, 0)

        usr.alterar(alvo["id"], {"bloqueado_ate": datetime.datetime(2999, 1, 1)}, ator="teste")
        bloqueados = usr.listar(filtros={"bloqueado_em": datetime.datetime(2998, 1, 1)}, pagina=1, tamanho=200)
        self.assertIn(alvo["login"], [u["login"] for u in bloqueados["itens"]])
        self.assertNotIn(c["u1"]["login"], [u["login"] for u in bloqueados["itens"]])

    def test_04e_parametro_dependencias_atomicas_qtd_scripts_e_auditoria(self):
        c = self.m.cenario()
        cat = self.obter_repo("catalogo")
        prm = cat.parametros_listar(filtros={"codigo": c["prm_a"]["codigo"]})["itens"][0]
        self.assertEqual(prm["qtd_scripts"], len(cat.parametro_vinculos(prm["id"])))
        self.assertEqual(prm["qtd_scripts"], 1)
        for dados, constraint in (({"tipo_componente": "NUMBER"}, "sss_prm_tipo_vinculado"),
                                  ({"param_nomeado": "--outra-flag"}, "sss_prm_flag_nomeado"),
                                  ({"ativo": "N"}, "sss_prm_vinculo_ativo")):
            with self.assertRaises(RepoViolacao) as ctx:
                cat.parametros_alterar(prm["id"], dict(dados, label="Nao deve gravar"), ator="teste")
            self.assertEqual(ctx.exception.constraint, constraint)
        self.assertEqual(cat.parametros_obter(prm["id"])["label"], prm["label"])
        with self.assertRaises(RepoConflito):
            cat.parametros_alterar(prm["id"], {"label": "x"}, esperado={"label": "outro"}, ator="teste")

        novo = cat.parametros_inserir({"codigo": "tst_%s_novo" % self.m.suf, "label": "Contrato",
                                       "tipo_componente": "TEXT"},
                                      auditoria={"ator": "admin", "ip": None, "acao": "CAD_INSERIR", "detalhe": "x"})
        self.m.anotar("parametros", novo["id"])
        self.assertEqual(self.aud_total("CAD_INSERIR", "tbsss_parametros", novo["id"]), 1)
        # Sem vinculo, tipo e flag mudam e a desativacao passa.
        alterado = cat.parametros_alterar(novo["id"], {"tipo_componente": "NUMBER", "param_nomeado": "--n",
                                                       "ativo": "N"}, ator="teste")
        self.assertEqual((alterado["tipo_componente"], alterado["param_nomeado"], alterado["ativo"]),
                         ("NUMBER", "--n", "N"))

    def test_04f_script_regras_de_tipo_param_homologacao_e_vinculos_condicionais(self):
        c = self.m.cenario()
        cat = self.obter_repo("catalogo")
        scr = cat.scripts_listar(filtros={"nome": c["scr"]["nome"]})["itens"][0]
        self.assertEqual(scr["qtd_parametros"], len(cat.script_params_obter(scr["id"])))
        self.assertEqual(scr["ambientes_homologados"], [c["amb1"]["nome"]])

        with self.assertRaises(RepoViolacao) as ctx:
            cat.scripts_alterar(scr["id"], {"tipo_param": "NENHUM", "descricao": "Nao grava"}, ator="teste")
        self.assertEqual(ctx.exception.constraint, "sss_scr_nenhum_vinculado")
        self.assertEqual(cat.scripts_obter(scr["id"])["tipo_param"], "NOMEADO")
        with self.assertRaises(RepoConflito):
            cat.scripts_alterar(scr["id"], {"descricao": "x"}, esperado={"descricao": "outra"}, ator="teste")

        sem_flag = self.m.parametro("semflag", param_nomeado=None)
        with self.assertRaises(RepoViolacao) as ctx:
            cat.script_params_salvar(scr["id"], [{"parametro_id": sem_flag["id"], "ordem": 1, "obrigatorio": "N"}],
                                     ator="teste")
        self.assertEqual(ctx.exception.constraint, "sss_scr_nomeado_sem_flag")

        homolog = cat.homologacao_obter(scr["id"])
        with self.assertRaises(RepoConflito):
            cat.homologacao_salvar(scr["id"], [], esperado=homolog + [999], ator="teste")
        cat.homologacao_salvar(scr["id"], homolog, esperado=homolog,
                               auditoria={"ator": "admin", "ip": None, "acao": "CAD_ALTERAR", "detalhe": "h"})
        vinc = cat.script_params_obter(scr["id"])
        lidos = [(v["parametro_id"], v["ordem"], v["obrigatorio"], v.get("valor_padrao_sub")) for v in vinc]
        with self.assertRaises(RepoConflito):
            cat.script_params_salvar(scr["id"], [], esperado=lidos[1:], ator="teste")
        cat.script_params_salvar(scr["id"], [dict(parametro_id=x[0], ordem=x[1], obrigatorio=x[2],
                                                  valor_padrao_sub=x[3]) for x in lidos], esperado=lidos,
                                 auditoria={"ator": "admin", "ip": None, "acao": "CAD_ALTERAR", "detalhe": "v"})
        self.assertEqual(self.aud_total("CAD_ALTERAR", "tbsss_scripts", scr["id"]), 2)

    def test_05_cascata_associacao(self):
        c = self.m.cenario()
        cat, rbac = self.obter_repo("catalogo"), self.obter_repo("rbac")
        sid = c["scr"]["id"]
        cat.homologacao_salvar(sid, [c["amb1"]["id"]], ator="teste")
        self.assertEqual(cat.homologacao_obter(sid), [c["amb1"]["id"]])
        cat.homologacao_salvar(sid, [c["amb1"]["id"], c["amb2"]["id"]], ator="teste")
        self.assertEqual(sorted(cat.homologacao_obter(sid)), sorted([c["amb1"]["id"], c["amb2"]["id"]]))

        p = c["perfil"]
        v_antes = rbac.perfis_obter(p["id"])["perm_versao"]
        func_ids = sorted(f["id"] for f in rbac.funcionalidades_listar())[:2]
        rbac.matriz_salvar(p["id"], funcs=func_ids, ambs=[c["amb1"]["id"]], scrs=[sid], ator="teste")
        m = rbac.matriz_obter(p["id"])
        self.assertEqual((sorted(m["funcs"]), m["ambs"], m["scrs"]), (func_ids, [c["amb1"]["id"]], [sid]))
        self.assertGreater(rbac.perfis_obter(p["id"])["perm_versao"], v_antes)

    def test_06_solicitar_cancelamento_nos_tres_retornos(self):
        c = self.m.cenario()
        tck = self.obter_repo("tickets")
        tid_pend = self.m.ticket(**c["ticket_base"])
        self.assertEqual(tck.solicitar_cancelamento(tid_pend, "admin", "10.0.0.1"), "CANCELADO")
        t1 = tck.obter(tid_pend)
        self.assertEqual((t1["status"], t1["cancel_requested"], t1["status_motivo"]), ("CANCELLED", "S", "CANCEL_USER"))
        self.assertEqual(tck.solicitar_cancelamento(tid_pend, "admin", "10.0.0.1"), "TERMINAL")
        tid_run = self.m.ticket(**dict(c["ticket_base"], status="RUNNING"))
        self.assertEqual(tck.solicitar_cancelamento(tid_run, "admin", "10.0.0.1"), "SINALIZADO")
        t3 = tck.obter(tid_run)
        self.assertEqual((t3["status"], t3["cancel_requested"]), ("RUNNING", "S"))

    def test_07_transicao_concorrente_perdida_gerando_repo_conflito(self):
        c = self.m.cenario()
        agd = self.obter_repo("agendamentos")
        regra = self.m.agendamento(c["scr"]["id"], c["amb1"]["nome"], c["u1"]["id"])
        data_correta = regra["proxima_execucao"]
        with self.assertRaises(RepoConflito):
            agd.pausar(regra["id"], motivo="MANUAL", antiga_data=data_correta + datetime.timedelta(days=10),
                       ator="teste")
        pausado = agd.pausar(regra["id"], motivo="MANUAL", antiga_data=data_correta, ator="teste")
        self.assertEqual((pausado["ativo"], pausado["pausa_motivo"]), ("N", "MANUAL"))
        # Pausar uma regra ja pausada gera RepoConflito (CR-007 R-19).
        with self.assertRaises(RepoConflito):
            agd.pausar(regra["id"], motivo="MANUAL", antiga_data=data_correta, ator="teste")

    def test_06b_fks_e_limites_de_auditoria(self):
        """CR-003 P8 (README §2.5): FKs, UK de ticket_resp e limites da auditoria, sem gravacao parcial."""
        c = self.m.cenario()
        tck, agd, aud = self.obter_repo("tickets"), self.obter_repo("agendamentos"), self.obter_repo("auditoria")
        base = c["ticket_base"]
        meus = lambda: tck.listar(filtros={"solicitante": c["login"]}, pagina=1, tamanho=1)["total"]  # noqa: E731
        total = meus()
        prm = c["prm_a"]["id"]
        casos = (
            (dict(base, script_id=999999999), [], self.cn("fk", "tickets", "scr")),
            (dict(base, ambiente="NAO_EXISTE_TST"), [], self.cn("fk", "tickets", "amb")),
            (dict(base, solicitante="nao.existe.tst"), [], self.cn("fk", "tickets", "usr")),
            (base, [{"parametro_id": 999999999, "valor_resposta": "x"}], self.cn("fk", "ticket_resp", "prm")),
            (base, [{"parametro_id": prm, "valor_resposta": "a"}, {"parametro_id": prm, "valor_resposta": "b"}],
             self.cn("uk", "ticket_resp", "tck_prm")),
        )
        for ticket, respostas, constraint in casos:
            with self.assertRaises(RepoViolacao) as ctx:
                self.m.ticket(respostas, **ticket)
            self.assertEqual(ctx.exception.constraint, constraint)
        self.assertEqual(meus(), total)

        for mudanca, constraint in (({"script_id": 999999999}, self.cn("fk", "agendamentos", "scr")),
                                    ({"usuario_id": 999999999}, self.cn("fk", "agendamentos", "usr")),
                                    ({"ambiente": "NAO_EXISTE_TST"}, self.cn("fk", "agendamentos", "amb"))):
            with self.assertRaises(RepoViolacao) as ctx:
                self.m.agendamento(**dict({"script_id": c["scr"]["id"], "ambiente": c["amb1"]["nome"],
                                           "usuario_id": c["u1"]["id"]}, **mudanca))
            self.assertEqual(ctx.exception.constraint, constraint)

        amb_id = c["amb1"]["id"]
        for ator, detalhe in ((None, "x"), ("", "x"), ("a" * 41, "x"), ("admin", "d" * 1001)):
            with self.assertRaises(RepoViolacao):
                aud.registrar(ator, None, "CAD_ALTERAR", "tbsss_ambientes", amb_id, detalhe)
        aud.registrar("a" * 40, None, "CAD_ALTERAR", "tbsss_ambientes", amb_id, "d" * 1000)

    def test_07b_agendamento_cks_condicional_e_auditoria_na_mesma_operacao(self):
        c = self.m.cenario()
        agd = self.obter_repo("agendamentos")
        inicio = datetime.datetime(2026, 1, 15, 10, 0)
        base = {"nome": "TST %s CK" % self.m.suf, "script_id": c["scr"]["id"], "ambiente": c["amb1"]["nome"],
                "usuario_id": c["u1"]["id"], "prioridade": 2, "tipo_recorrencia": "DIARIA", "hora_execucao": "03:00",
                "parametros_json": "{}", "data_inicio": inicio, "proxima_execucao": datetime.datetime(2030, 1, 16, 3, 0)}
        ck = lambda s: self.cn("ck", "agendamentos", s)  # noqa: E731
        violacoes = [
            ({"tipo_recorrencia": "ANUAL"}, ck("trec")),
            ({"prioridade": 5}, ck("prio")),
            ({"ativo": "X"}, ck("ativo")),
            ({"tipo_recorrencia": "MENSAL", "dia_mes": 32}, ck("dia")),
            ({"hora_execucao": "24:00"}, ck("hora")),
            ({"tipo_recorrencia": "SEMANAL", "dias_semana": "1,8"}, ck("dsem")),
            ({"data_fim": inicio - datetime.timedelta(days=1)}, ck("fim")),
            ({"pausa_motivo": "OUTRO"}, ck("pausa")),
            ({"tipo_recorrencia": "SEMANAL"}, ck("campos")),
            ({"tipo_recorrencia": "CRON", "hora_execucao": None}, ck("campos")),
        ]
        minhas = lambda: agd.listar(filtros={"nome": self.m.suf}, pagina=1, tamanho=1)["total"]  # noqa: E731
        total_regras = minhas()
        for extra, constraint in violacoes:
            with self.assertRaises(RepoViolacao) as cm:
                agd.inserir(dict(base, **extra),
                            auditoria={"ator": self.m.ator, "ip": None, "acao": "CAD_INSERIR", "detalhe": "x"})
            self.assertEqual(cm.exception.constraint, constraint, extra)
        self.assertEqual(minhas(), total_regras)
        self.assertEqual(self.obter_repo("auditoria").listar(
            filtros={"acao": "CAD_INSERIR", "ator": self.m.ator}, pagina=1, tamanho=1)["total"], 0)

        novo = agd.inserir(base, auditoria={"ator": "admin", "ip": "10.0.0.1", "acao": "CAD_INSERIR",
                                            "detalhe": "nome: Contrato AGD"})
        self.m.anotar("agendamentos", novo["id"])
        self.assertEqual(self.aud_ultima("CAD_INSERIR", "tbsss_agendamentos", novo["id"])["ator"], "admin")

        lido = {"nome": novo["nome"], "usuario_id": c["u1"]["id"], "proxima_execucao": novo["proxima_execucao"]}
        alterado = agd.alterar(novo["id"], {"nome": "TST %s CK2" % self.m.suf, "usuario_id": c["u2"]["id"]},
                               esperado=lido,
                               auditoria={"ator": "op.prod", "ip": None, "acao": "CAD_ALTERAR", "detalhe": "y"})
        self.assertEqual((alterado["nome"], alterado["usuario_id"]), ("TST %s CK2" % self.m.suf, c["u2"]["id"]))
        self.assertEqual(self.aud_total("CAD_ALTERAR", "tbsss_agendamentos", novo["id"]), 1)
        with self.assertRaises(RepoConflito):
            agd.alterar(novo["id"], {"nome": "Perdedor"}, esperado=lido,
                        auditoria={"ator": "admin", "ip": None, "acao": "CAD_ALTERAR", "detalhe": "z"})
        with self.assertRaises(RepoViolacao):
            agd.alterar(novo["id"], {"nome": "Parcial", "tipo_recorrencia": "MENSAL"}, ator="teste")
        self.assertEqual(agd.obter(novo["id"])["nome"], "TST %s CK2" % self.m.suf)
        self.assertEqual(self.aud_total("CAD_ALTERAR", "tbsss_agendamentos", novo["id"]), 1)

        agd.pausar(novo["id"], "MANUAL", antiga_data=novo["proxima_execucao"],
                   auditoria={"ator": "admin", "ip": "10.0.0.2", "acao": "AGD_PAUSAR", "detalhe": "p"})
        pausa = self.aud_ultima("AGD_PAUSAR", "tbsss_agendamentos", novo["id"])
        self.assertEqual((pausa["ator"], pausa["ip_origem"]), ("admin", "10.0.0.2"))

        pausado = {"ativo": "N", "pausa_motivo": "MANUAL", "proxima_execucao": novo["proxima_execucao"]}
        nova = datetime.datetime(2030, 1, 20, 3, 0)
        with self.assertRaises(RepoConflito):
            agd.retomar(novo["id"], nova, esperado=dict(pausado, pausa_motivo="CONCLUIDO"),
                        auditoria={"ator": "admin", "ip": None, "acao": "CAD_ALTERAR", "detalhe": "r"})
        self.assertEqual(agd.obter(novo["id"])["ativo"], "N")
        retomado = agd.retomar(novo["id"], nova, esperado=pausado,
                               auditoria={"ator": "admin", "ip": None, "acao": "CAD_ALTERAR", "detalhe": "r"})
        self.assertEqual((retomado["ativo"], retomado["pausa_motivo"], retomado["proxima_execucao"]), ("S", None, nova))
        self.assertEqual(self.aud_total("CAD_ALTERAR", "tbsss_agendamentos", novo["id"]), 2)

    def test_08_perm_versao_incrementando(self):
        c = self.m.cenario()
        rbac, usr = self.obter_repo("rbac"), self.obter_repo("usuarios")
        p = c["perfil"]
        v0 = rbac.perfis_obter(p["id"])["perm_versao"]
        rbac.perfis_alterar(p["id"], {"descricao": "Nova descricao"}, ator="teste")
        v1 = rbac.perfis_obter(p["id"])["perm_versao"]
        self.assertEqual(v1, v0 + 1)
        func_ids = [f["id"] for f in rbac.funcionalidades_listar()][:1]
        rbac.matriz_salvar(p["id"], funcs=func_ids, ambs=[c["amb1"]["id"]], scrs=[c["scr"]["id"]], ator="teste")
        v2 = rbac.perfis_obter(p["id"])["perm_versao"]
        self.assertEqual(v2, v1 + 1)
        usr.alterar(c["u1"]["id"], {"ativo": "N"}, ator="teste")
        self.assertGreaterEqual(rbac.perfis_obter(p["id"])["perm_versao"], v2 + 1)

    def test_09_paginacao_estavel_e_deterministica(self):
        c = self.m.cenario()
        tck = self.obter_repo("tickets")
        for _ in range(25):
            self.m.ticket(**c["ticket_base"])
        filtros = {"script_id": c["scr"]["id"], "solicitante": c["login"]}
        pag1 = tck.listar(filtros=filtros, pagina=1, tamanho=10)
        pag2 = tck.listar(filtros=filtros, pagina=2, tamanho=10)
        self.assertEqual((pag1["pagina"], pag1["tamanho"], pag1["total"]), (1, 10, 25))
        self.assertEqual((len(pag1["itens"]), len(pag2["itens"])), (10, 10))
        self.assertTrue({i["id"] for i in pag1["itens"]}.isdisjoint({i["id"] for i in pag2["itens"]}))
        ordem = [(i["created_at"], i["id"]) for i in pag1["itens"] + pag2["itens"]]
        self.assertEqual(ordem, sorted(ordem, reverse=True))
        self.assertEqual([i["id"] for i in pag1["itens"]],
                         [i["id"] for i in tck.listar(filtros=filtros, pagina=1, tamanho=10)["itens"]])

    def test_10_escopo_ambientes_na_listagem_tickets(self):
        c = self.m.cenario()
        tck = self.obter_repo("tickets")
        for _ in range(3):
            self.m.ticket(**c["ticket_base"])
        for _ in range(2):
            self.m.ticket(**dict(c["ticket_base"], ambiente=c["amb2"]["nome"]))
        filtros = {"script_id": c["scr"]["id"]}
        lista_a = tck.listar(filtros=filtros, escopo_ambientes=[c["amb1"]["nome"]], pagina=1, tamanho=50)
        lista_b = tck.listar(filtros=filtros, escopo_ambientes=[c["amb2"]["nome"]], pagina=1, tamanho=50)
        self.assertEqual({t["ambiente"] for t in lista_a["itens"]}, {c["amb1"]["nome"]})
        self.assertEqual({t["ambiente"] for t in lista_b["itens"]}, {c["amb2"]["nome"]})
        self.assertEqual((lista_a["total"], lista_b["total"]), (3, 2))
        self.assertEqual(tck.listar(filtros=filtros, escopo_ambientes=[], pagina=1, tamanho=50)["total"], 0)

    def test_11_log_ler_incremental(self):
        c = self.m.cenario()
        tck = self.obter_repo("tickets")
        log = "".join("linha %02d do log\n" % i for i in range(10))
        tid = self.m.ticket(**dict(c["ticket_base"], status="RUNNING", log_output=log,
                                   started_at=datetime.datetime(2026, 1, 1, 8, 0)))
        texto, prox_off, terminal, truncado = tck.log_ler(tid, offset=0, max_chars=20)
        self.assertEqual((texto, prox_off, terminal, truncado), (log[:20], 20, False, False))
        texto2, prox_off2, _, _ = tck.log_ler(tid, offset=prox_off, max_chars=20)
        self.assertEqual((texto2, prox_off2), (log[20:40], 40))

    # ------------------------------------------------------------------
    # Colunas de registro (CR-006, README §10, AGENTS §4.15)
    # ------------------------------------------------------------------

    def _conferir_inclusao(self, reg, ator):
        self.assertEqual(reg["created_by"], ator)
        self.assertIsNotNone(reg["created_at"])
        self.assertIsNone(reg["updated_at"])
        self.assertIsNone(reg["updated_by"])

    def _conferir_alteracao(self, antes, depois, ator):
        self.assertEqual(depois["updated_by"], ator)
        self.assertIsNotNone(depois["updated_at"])
        self.assertGreaterEqual(depois["updated_at"], depois["created_at"])
        self.assertEqual((depois["created_at"], depois["created_by"]), (antes["created_at"], antes["created_by"]))

    def test_12_registro_inclusao_e_alteracao_nos_cadastros(self):
        c = self.m.cenario()
        cat, rbac, usr, agd = (self.obter_repo(n) for n in ("catalogo", "rbac", "usuarios", "agendamentos"))
        aud = {"ator": "carla", "ip": "10.0.0.9", "acao": "CAD_ALTERAR", "detalhe": "registro"}
        suf = self.m.suf

        amb = cat.ambientes_inserir({"nome": "TST_%s_REG" % suf, "descricao": "d"}, ator="ana")
        self.m.anotar("ambientes", amb["id"])
        self._conferir_inclusao(amb, "ana")
        self._conferir_alteracao(amb, cat.ambientes_alterar(amb["id"], {"descricao": "e"}, ator="bia"), "bia")
        self._conferir_alteracao(amb, cat.ambientes_alterar(amb["id"], {"descricao": "f"}, auditoria=aud), "carla")
        self.assertEqual(cat.ambientes_obter(amb["id"])["updated_by"], "carla")

        scr = cat.scripts_inserir({"nome": "tst_%s_reg" % suf, "interpretador": "SH",
                                   "path_file": "/opt/tst/%s_reg.sh" % suf, "tipo_param": "NENHUM"}, ator="ana")
        self.m.anotar("scripts", scr["id"])
        self._conferir_inclusao(scr, "ana")
        self._conferir_alteracao(scr, cat.scripts_alterar(scr["id"], {"ativo": "N"}, ator="bia"), "bia")

        prm = cat.parametros_inserir({"codigo": "tst_%s_reg" % suf, "label": "Reg", "tipo_componente": "TEXT"},
                                     ator="ana")
        self.m.anotar("parametros", prm["id"])
        self._conferir_inclusao(prm, "ana")
        self._conferir_alteracao(prm, cat.parametros_alterar(prm["id"], {"label": "Outro"}, ator="bia"), "bia")

        per = rbac.perfis_inserir({"nome": "TST_%s_REG" % suf}, ator="ana")
        self.m.anotar("perfis", per["id"])
        self._conferir_inclusao(per, "ana")
        self._conferir_alteracao(per, rbac.perfis_alterar(per["id"], {"descricao": "x"}, ator="bia"), "bia")

        u = usr.inserir({"login": "tst.%s.reg" % suf, "nome": "Reg", "senha_hash": "h", "perfil_id": per["id"]},
                        ator="ana")
        self.m.anotar("usuarios", u["id"])
        self._conferir_inclusao(u, "ana")
        self._conferir_alteracao(u, usr.alterar(u["id"], {"nome": "Reg 2"}, ator="bia"), "bia")
        self._conferir_alteracao(u, usr.definir_senha(u["id"], "hash-novo", ator="dora"), "dora")
        self._conferir_alteracao(u, usr.desbloquear(u["id"], ator="eva"), "eva")

        regra = agd.inserir({"nome": "TST %s REG" % suf, "script_id": c["scr"]["id"], "ambiente": c["amb1"]["nome"],
                             "usuario_id": c["u1"]["id"], "prioridade": 2, "tipo_recorrencia": "DIARIA",
                             "hora_execucao": "03:00", "parametros_json": "{}",
                             "data_inicio": datetime.datetime(2026, 1, 15, 10, 0),
                             "proxima_execucao": datetime.datetime(2030, 1, 16, 3, 0)}, ator="ana")
        self.m.anotar("agendamentos", regra["id"])
        self._conferir_inclusao(regra, "ana")
        editada = agd.alterar(regra["id"], {"nome": "TST %s REG2" % suf, "usuario_id": c["u2"]["id"]}, ator="op.hml")
        self._conferir_alteracao(regra, editada, "op.hml")
        self.assertEqual(editada["created_by"], "ana", "o criador original nunca muda (R-g)")
        pausada = agd.pausar(regra["id"], "MANUAL", antiga_data=editada["proxima_execucao"], ator="bia")
        self._conferir_alteracao(regra, pausada, "bia")
        self._conferir_alteracao(regra, agd.retomar(regra["id"], editada["proxima_execucao"], ator="carla"), "carla")

    def test_12b_ator_obrigatorio_e_limitado_sem_gravacao_parcial(self):
        c = self.m.cenario()
        cat, usr, tck = self.obter_repo("catalogo"), self.obter_repo("usuarios"), self.obter_repo("tickets")
        for ator in (None, "", "x" * 41):
            with self.assertRaises(RepoViolacao):
                cat.ambientes_inserir({"nome": "TST_%s_SEMATOR" % self.m.suf}, ator=ator)
        self.assertEqual(cat.ambientes_listar(filtros={"nome": "TST_%s_SEMATOR" % self.m.suf})["total"], 0)
        antes = cat.ambientes_obter(c["amb1"]["id"])
        with self.assertRaises(RepoViolacao):
            cat.ambientes_alterar(c["amb1"]["id"], {"descricao": "nao grava"})
        self.assertEqual(cat.ambientes_obter(c["amb1"]["id"]), antes)
        with self.assertRaises(RepoViolacao):
            usr.desbloquear(c["u1"]["id"])
        tid = self.m.ticket(**c["ticket_base"])
        with self.assertRaises(RepoViolacao):
            tck.solicitar_cancelamento(tid, None, "10.0.0.1")
        self.assertEqual(tck.obter(tid)["status"], "PENDING")
        amb40 = cat.ambientes_inserir({"nome": "TST_%s_ATOR40" % self.m.suf}, ator="y" * 40)
        self.m.anotar("ambientes", amb40["id"])
        self.assertEqual(amb40["created_by"], "y" * 40)

    def test_12c_rotina_tecnica_do_login_nao_grava_updated(self):
        c = self.m.cenario()
        usr = self.obter_repo("usuarios")
        antes = usr.obter_por_login(c["login"])
        usr.registrar_falha_login(c["login"], bloqueio_s=60)
        usr.reiniciar_tentativas(antes["id"])
        usr.registrar_sucesso_login(c["login"], novo_hash=antes["senha_hash"])
        depois = usr.obter_por_login(c["login"])
        self.assertEqual((depois["updated_at"], depois["updated_by"]), (antes["updated_at"], antes["updated_by"]))
        self.assertEqual(depois["tentativas_falha"], 0)

    def test_12d_tickets_criacao_e_cancelamento(self):
        c = self.m.cenario()
        tck = self.obter_repo("tickets")
        base = dict(c["ticket_base"], solicitante=c["u2"]["login"])
        tid = self.m.ticket([{"parametro_id": c["prm_a"]["id"], "valor_resposta": "2026-10-17"}], **base)
        t = tck.obter(tid)
        self._conferir_inclusao(t, c["u2"]["login"])
        self.assertEqual([r["created_by"] for r in tck.respostas(tid)], [c["u2"]["login"]])
        tid_agd = self.m.ticket(ator="SYSTEM:agt-host01", **base)
        self._conferir_inclusao(tck.obter(tid_agd), "SYSTEM:agt-host01")

        self.assertEqual(tck.solicitar_cancelamento(tid, "admin", "10.0.0.1"), "CANCELADO")
        self._conferir_alteracao(t, tck.obter(tid), "admin")
        self.assertEqual(tck.solicitar_cancelamento(tid, "outro", "10.0.0.1"), "TERMINAL")
        self.assertEqual(tck.obter(tid)["updated_by"], "admin", "solicitacao sem efeito nao altera o registro")

        tid_run = self.m.ticket(**dict(c["ticket_base"], status="RUNNING"))
        self.assertEqual(tck.solicitar_cancelamento(tid_run, "admin", "10.0.0.1"), "SINALIZADO")
        self.assertEqual(tck.obter(tid_run)["updated_by"], "admin")
        self.assertEqual(tck.solicitar_cancelamento(tid_run, "outro", "10.0.0.1"), "JA_SINALIZADO")
        self.assertEqual(tck.obter(tid_run)["updated_by"], "admin")


class BaseUltimoAdminTest(object):
    """Protecao do ultimo administrador (README §4.3.B): exige que nao haja outro admin ativo no banco.

    Roda no FAKE e no Oracle so com owner descartavel (SSS_TEST_*): num owner compartilhado ha admins
    reais, e desativa-los para o teste seria perigoso.
    """

    def test_perfil_ultimo_admin_recusado_sem_alterar(self):
        rbac = self.obter_repo("rbac")
        admin = rbac.perfis_listar(filtros={"nome": "ADMINISTRADOR"})["itens"][0]
        versao = admin["perm_versao"]
        for dados in ({"ativo": "N"}, {"is_admin": "N"}):
            with self.assertRaises(RepoViolacao) as ctx:
                rbac.perfis_alterar(admin["id"], dados,
                                    auditoria={"ator": "admin", "ip": None, "acao": "CAD_DESATIVAR", "detalhe": "x"})
            self.assertEqual(ctx.exception.constraint, "sss_ultimo_admin")
        atual = rbac.perfis_obter(admin["id"])
        self.assertEqual((atual["ativo"], atual["is_admin"], atual["perm_versao"]), ("S", "S", versao))

    def test_usuario_ultimo_admin_recusado_sem_alterar(self):
        usr = self.obter_repo("usuarios")
        admin = usr.obter_por_login("admin")
        consulta = usr.obter_por_login("consulta")
        for dados in ({"ativo": "N"}, {"perfil_id": consulta["perfil_id"]}):
            with self.assertRaises(RepoViolacao) as ctx:
                usr.alterar(admin["id"], dados, auditoria={"ator": "x", "ip": None, "acao": "CAD_ALTERAR", "detalhe": "x"})
            self.assertEqual(ctx.exception.constraint, "sss_ultimo_admin")
        atual = usr.obter_por_id(admin["id"])
        self.assertEqual((atual["ativo"], atual["perfil_id"]), ("S", admin["perfil_id"]))


class TestRepoContractFake(unittest.TestCase, BaseRepoContractTest):
    """Executa a bateria de contratos contra o backend FAKE."""

    def setUp(self):
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()

    def obter_repo(self, nome):
        return repo_factory.obter(nome)

    # Vinculos por diferenca (CR-006, R-f): o contrato nao le as linhas de vinculo, entao o FAKE e
    # inspecionado direto; no Oracle, o F7.3 confere com SELECT nas tabelas de associacao.
    def _linhas(self, tabela, **filtro):
        store = self.obter_repo("catalogo")._store
        return dict((tuple(v[c] for c in sorted(v) if c not in ("id", "created_at", "created_by",
                                                                  "updated_at", "updated_by")), v)
                    for v in getattr(store, tabela).values()
                    if all(v.get(k) == x for k, x in filtro.items()))

    def test_12e_vinculos_por_diferenca_preservam_created(self):
        cat = self.obter_repo("catalogo")
        rbac = self.obter_repo("rbac")
        sid = 1
        homolog = cat.homologacao_obter(sid)
        antes = self._linhas("script_amb", script_id=sid)
        scr_antes = cat.scripts_obter(sid)
        cat.homologacao_salvar(sid, homolog, ator="sem-mudanca")
        self.assertEqual(cat.scripts_obter(sid)["updated_by"], scr_antes["updated_by"])
        cat.homologacao_salvar(sid, homolog + [3], ator="ana")
        depois = self._linhas("script_amb", script_id=sid)
        for chave, linha in antes.items():
            self.assertEqual((depois[chave]["created_at"], depois[chave]["created_by"]),
                             (linha["created_at"], linha["created_by"]))
        novo = [v for k, v in depois.items() if k not in antes]
        self.assertEqual([v["created_by"] for v in novo], ["ana"])
        self.assertEqual(cat.scripts_obter(sid)["updated_by"], "ana")

        matriz = rbac.matriz_obter(4)
        antes = self._linhas("perfil_amb", perfil_id=4)
        rbac.matriz_salvar(4, matriz["funcs"], matriz["ambs"], matriz["scrs"] + [5], ator="bia")
        depois = self._linhas("perfil_amb", perfil_id=4)
        self.assertEqual(depois, antes, "dimensao sem mudanca fica intacta")
        self.assertEqual(rbac.perfis_obter(4)["updated_by"], "bia")
        self.assertEqual([v["created_by"] for k, v in self._linhas("perfil_scr", perfil_id=4).items()
                          if v["script_id"] == 5], ["bia"])

        vinculos = cat.script_params_obter(sid)
        self.assertGreaterEqual(len(vinculos), 2)
        antes = dict((v["parametro_id"], v) for v in self._linhas("script_param", script_id=sid).values())
        trocados = [dict(parametro_id=v["parametro_id"], ordem=v["ordem"], obrigatorio=v["obrigatorio"],
                         valor_padrao_sub=v.get("valor_padrao_sub")) for v in vinculos]
        trocados[0]["ordem"], trocados[1]["ordem"] = trocados[1]["ordem"], trocados[0]["ordem"]
        cat.script_params_salvar(sid, trocados, ator="carla")
        depois = dict((v["parametro_id"], v) for v in self._linhas("script_param", script_id=sid).values())
        for pid, linha in antes.items():
            self.assertEqual((depois[pid]["created_at"], depois[pid]["created_by"]),
                             (linha["created_at"], linha["created_by"]))
            mudou = pid in (trocados[0]["parametro_id"], trocados[1]["parametro_id"])
            self.assertEqual(depois[pid]["updated_by"], "carla" if mudou else linha["updated_by"])
        self.assertEqual(cat.scripts_obter(sid)["updated_by"], "carla")

    def test_12f_finalizacao_simulada_e_do_agente(self):
        tck = self.obter_repo("tickets")
        store = tck._store
        antes = tck.obter(11)
        futuro = store.agora() + datetime.timedelta(days=1)
        store.definir_relogio(lambda: futuro)
        tck.log_ler(11, offset=0, max_chars=10)
        depois = tck.obter(11)
        self.assertEqual(depois["status"], "SUCCESS")
        self.assertEqual(depois["updated_by"], "SYSTEM:%s" % antes["agente_id"])
        self.assertEqual(depois["updated_at"], futuro)
        self.assertEqual(depois["created_by"], antes["created_by"])


class _OracleContrato(object):
    """Preparo e limpeza comuns as classes da bateria contra o Oracle real (SSS_TEST_ORACLE=1)."""

    @classmethod
    def setUpClass(cls):
        from _oracle_test_support import preparar_schema_descartavel
        cls._tinha_sss_cfg = hasattr(current, "sss_cfg")
        cls._sss_cfg_anterior = getattr(current, "sss_cfg", None)
        cls.oracle_cfg = preparar_schema_descartavel("web")
        current.sss_cfg = cls.oracle_cfg

    @classmethod
    def tearDownClass(cls):
        repo_factory.configurar(None)
        repo_factory.reset_singletons()
        if cls._tinha_sss_cfg:
            current.sss_cfg = cls._sss_cfg_anterior
        elif hasattr(current, "sss_cfg"):
            delattr(current, "sss_cfg")

    def setUp(self):
        repo_factory.configurar({"app": {"sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self._massa = None

    def tearDown(self):
        self._limpar_massa()

    def obter_repo(self, nome):
        return repo_factory.obter(nome)

    def _limpar_massa(self):
        """Remove so os registros criados pelo teste, em ordem de dependencia; no modo compartilhado,
        tambem a auditoria deles (README §2.5). Limpeza incompleta falha o teste com os IDs restantes."""
        import _oracle_test_support
        massa = getattr(self, "_massa", None)
        if massa is None or not any(massa.criados.values()):
            return
        repo = self.obter_repo("catalogo")
        compartilhado = _oracle_test_support.modo_schema() == _oracle_test_support.MODO_COMPARTILHADO
        tab_aud = repo.qualificar_tabela("auditoria")
        conn = repo._obter_conexao()
        restantes = []
        try:
            cur = conn.cursor()
            try:
                for entidade, ids in massa.criados.items():
                    tabela = repo.qualificar_tabela(entidade)
                    for rid in ids:
                        cur.execute("DELETE FROM " + tabela + " WHERE id = :id", {"id": rid})
                        if compartilhado:
                            cur.execute("DELETE FROM " + tab_aud + " WHERE entidade = :ent AND entidade_id = :id",
                                        {"ent": "tbsss_" + entidade, "id": rid})
                conn.commit()
                for entidade, ids in massa.criados.items():
                    tabela = repo.qualificar_tabela(entidade)
                    for rid in ids:
                        cur.execute("SELECT id FROM " + tabela + " WHERE id = :id", {"id": rid})
                        if cur.fetchone():
                            restantes.append((entidade, rid))
            finally:
                cur.close()
        finally:
            conn.close()
        if restantes:
            self.fail("Limpeza incompleta no banco real: %s" % restantes)


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestRepoContractOracle(_OracleContrato, unittest.TestCase, BaseRepoContractTest):
    """Executa a mesma bateria contra o Oracle do config.ini, com dados proprios de cada teste."""


class TestUltimoAdminFake(unittest.TestCase, BaseUltimoAdminTest):
    """Protecao do ultimo administrador no FAKE (seed com um unico admin ativo)."""

    def setUp(self):
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()

    def obter_repo(self, nome):
        return repo_factory.obter(nome)


@unittest.skipUnless(os.environ.get("SSS_TEST_ORACLE") == "1", "Testes Oracle reais desligados (SSS_TEST_ORACLE=1)")
class TestUltimoAdminOracle(_OracleContrato, unittest.TestCase, BaseUltimoAdminTest):
    """Protecao do ultimo administrador no Oracle: so com owner descartavel (o teste e dono do banco)."""

    @classmethod
    def setUpClass(cls):
        super(TestUltimoAdminOracle, cls).setUpClass()
        import _oracle_test_support
        if _oracle_test_support.modo_schema() != _oracle_test_support.MODO_DESCARTAVEL:
            raise unittest.SkipTest("Owner compartilhado: ha administradores reais; a protecao do ultimo admin "
                                    "so e exercida no FAKE e com owner SSS_TEST_* (README §2.5)")


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
        self.assertIn("FAKE (so de teste) e proibido fora de DEV", str(ctx.exception))

        # FAKE com PROD tambem deve abortar
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "PROD"}})
        with self.assertRaises(RuntimeError):
            repo_factory.obter("usuarios")

    def test_oracle_integrado_exige_banco_autorizado(self):
        """A bateria Oracle so roda com SSS_TEST_ORACLE=1, DEV e o esquema validado (detalhes no test_db_conn)."""
        from _oracle_test_support import PrecondicaoSchemaErro, preparar_schema_descartavel

        cfg = mock.Mock()
        cfg.app.data_backend = "FAKE"
        cfg.app.sss_env = "DEV"
        cfg.oracle.owner = "SSS_TEST_APP"
        cfg.oracle.dsn = "dbtest.local/sss"
        cfg.oracle.user = "SSS_APP"
        cfg.oracle.table_prefix = "tbsss_"
        cfg.secrets.secrets_file = "/tmp/secrets.cfg"
        segredos = object()
        conexao = mock.Mock()
        conexao.cursor.return_value.fetchone.return_value = ("SSS_APP",)
        db_conn_mock = mock.Mock()
        db_conn_mock.conectar.return_value = conexao
        sss_config_mock = mock.Mock()
        sss_config_mock.obter_config.return_value = cfg
        sss_config_mock.carregar_segredos.return_value = segredos

        def preparar(env):
            with mock.patch.dict(os.environ, env, clear=True):
                with mock.patch.dict("sys.modules", {"db_conn": db_conn_mock, "sss_config": sss_config_mock}):
                    return preparar_schema_descartavel("web")

        # Ligado e autorizado: usa o config da aplicacao, confere a sessao e fecha a conexao.
        self.assertIs(preparar({"SSS_TEST_ORACLE": "1"}), cfg)
        db_conn_mock.conectar.assert_called_once_with(cfg, segredos, "web")
        self.assertEqual(conexao.cursor.return_value.execute.call_args[0][0], "SELECT USER FROM DUAL")
        conexao.close.assert_called_once_with()

        # Desligado, variavel antiga ou fora de DEV: recusa antes de conectar.
        db_conn_mock.conectar.reset_mock()
        for env in ({}, {"SSS_TEST_ORACLE": "1", "SSS_TEST_DSN": "dbtest.local/sss"}):
            with self.assertRaises(PrecondicaoSchemaErro):
                preparar(env)
        cfg.app.sss_env = "HML"
        with self.assertRaises(PrecondicaoSchemaErro):
            preparar({"SSS_TEST_ORACLE": "1"})
        db_conn_mock.conectar.assert_not_called()

    def test_oracle_agregado_seguinte_ainda_nao_implementado(self):
        repo_factory.configurar({"app": {"data_backend": "ORACLE", "sss_env": "DEV"}})
        agregados = ("RBAC_USUARIOS", "CATALOGO", "TICKETS", "AGENDAMENTOS", "AUDITORIA_AGENTES")
        selecionado = os.environ.get("SSS_TEST_REPO_AGREGADO")
        if selecionado not in agregados:
            self.skipTest("Factory Oracle progressiva validada pelo prompt F7.3")
        indice = agregados.index(selecionado)
        if indice == len(agregados) - 1:
            self.skipTest("Todos os agregados estao registrados; rodar a bateria Oracle integrada")
        proximos = ("catalogo", "tickets", "agendamentos", "auditoria")
        with self.assertRaises(NotImplementedError) as ctx:
            repo_factory.obter(proximos[indice])
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
        for cfg in ({}, {"app": {"data_backend": "FAKE"}}):
            with self.subTest(cfg=cfg):
                repo_factory.configurar(cfg)
                with self.assertRaises(KeyError):
                    repo_factory.obter("usuarios")

    def test_sem_data_backend_a_aplicacao_e_oracle(self):
        """F7.3: o config.ini nao tem mais data_backend; so o dict de teste pode pedir o FAKE."""
        self.assertEqual(repo_factory._resolver_config({"app": {"sss_env": "DEV"}}), ("ORACLE", "DEV"))
        self.assertEqual(repo_factory._resolver_config({"app": {"sss_env": "DEV", "data_backend": "FAKE"}}),
                         ("FAKE", "DEV"))
        import sss_config
        cfg_app = sss_config.AppConfig(sss_env="PROD")
        self.assertEqual(repo_factory._resolver_config({"app": cfg_app}), ("ORACLE", "PROD"))

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
