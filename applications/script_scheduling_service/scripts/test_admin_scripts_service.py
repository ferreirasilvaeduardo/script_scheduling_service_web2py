# -*- coding: utf-8 -*-
"""Testes de admin_scripts_service.py (F4.5) sobre o backend FAKE e uma arvore temporaria de scripts."""
import _testenv  # noqa: F401

import datetime
import json
import logging
import os
import shutil
import stat
import tempfile
import unittest
from unittest import mock

import admin_crud
import path_guard
import admin_scripts_service as scr_mod
import auth_service
import repo_factory
import security
from admin_crud import CAMPO_GERAL, AcessoNegado, OperacaoNegada
from admin_scripts_service import ServicoAdminScripts
from path_guard import Codigo
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao

IP = "10.5.5.5"
AGORA = datetime.datetime(2026, 10, 15, 10, 0, 0)
SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1},
    "op.prod": {"usuario_id": 2, "login": "op.prod", "perfil_id": 2, "perm_versao": 1},
}
# Seed FAKE: script 1 carga_diaria (NOMEADO, python3, vinculos data_ref, limite_linhas, modo_exec, verbose,
# documento_cliente sensivel), 3 cleanup_tmp (NENHUM). Ambientes 1 PRODUCAO, 2 HOMOLOGACAO, 3 DESENV (inativo).
# Parametros: 1 data_ref (--data-ref), 5 codigo_filial (--filial), 10 descricao_lote (--descricao), sem flag: nenhum
# no seed, por isso o teste cria um.
S_CARGA, S_CLEANUP = 1, 3
AMB_PROD, AMB_HML, AMB_DESENV = 1, 2, 3
ARQUIVOS = ("carga_diaria.py", "relatorio_mensal.py", "cleanup_tmp.sh", "sync_tabelas.sh", "validacao_fiscal.py",
            "novo.py")


def _arvore():
    base = tempfile.mkdtemp(prefix="sss_scr_")
    os.mkdir(os.path.join(base, "sub"))
    for nome in ARQUIVOS:
        with open(os.path.join(base, nome), "w") as f:
            f.write("# teste\n")
        os.chmod(os.path.join(base, nome), 0o444)
    with open(os.path.join(base, "gravavel.py"), "w") as f:
        f.write("# teste\n")
    os.chmod(os.path.join(base, "gravavel.py"), 0o666)
    with open(os.path.join(base, "sub", "interno.sh"), "w") as f:
        f.write("# teste\n")
    os.chmod(os.path.join(base, "sub", "interno.sh"), 0o444)
    os.chmod(os.path.join(base, "sub"), 0o555)
    os.chmod(base, 0o555)
    return os.path.realpath(base)


def _remover(base):
    for raiz, dirs, _arqs in os.walk(base):
        for d in dirs:
            os.chmod(os.path.join(raiz, d), stat.S_IRWXU)
    os.chmod(base, stat.S_IRWXU)
    shutil.rmtree(base)


_SKIP_ROOT = unittest.skipIf(os.geteuid() == 0, "path_guard rejeita qualquer arquivo quando executado como root")


class _Base(unittest.TestCase):
    ENV = "DEV"

    def setUp(self):
        patcher = mock.patch.object(security, "ITERACOES", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_SENHA_DEV: "senha-dev-de-teste-123"})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configurar, None)

        self.catalogo = repo_factory.obter("catalogo")
        self.auditoria = repo_factory.obter("auditoria")
        self.log = logging.getLogger("sss_teste_scripts")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        auth = auth_service.ServicoAuth(repo_factory.obter("usuarios"), repo_factory.obter("rbac"), self.catalogo,
                                        self.auditoria, 5, 900, self.log)
        self.ctx = dict((login, auth.revalidar(sessao)) for login, sessao in SESSOES.items())
        self.ctx["gestor"] = dict(self.ctx["op.prod"], funcionalidades=frozenset(["CAD_SCRIPTS"]))
        self.base = _arvore()
        self.addCleanup(_remover, self.base)
        # A arvore fica sob /tmp (escrita para todos): a cadeia de pastas para na base travada.
        original = path_guard.resolver
        patcher = mock.patch.object(path_guard, "resolver",
                                    lambda p, u, uid_agente=None, dirs_sss=(), parar_em="/":
                                    original(p, u, uid_agente, dirs_sss, self.base))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.svc = self._servico(self.ENV)
        self.aud_base = max([a["id"] for a in self.auditoria.listar(pagina=1, tamanho=1000)["itens"]] or [0])

    def _servico(self, env, dirs_sss=()):
        return ServicoAdminScripts(self.catalogo, repo_factory.obter("agendamentos"), (os.geteuid(),), env,
                                   self.log, lambda: AGORA, dirs_sss)

    def _p(self, nome):
        return os.path.join(self.base, nome)

    def _auditorias(self, acao):
        return [a for a in self.auditoria.listar(filtros={"acao": acao}, pagina=1, tamanho=100)["itens"]
                if a["entidade"] == "tbsss_scripts" and a["id"] > self.aud_base]

    def _incluir(self, svc=None, **mudancas):
        dados = {"nome": "Novo script", "interpretador": "PYTHON3", "path_file": self._p("novo.py"),
                 "tipo_param": "SEQUENCIAL", "max_qtd_parallel_env": "2", "timeout_seg": ""}
        dados.update(mudancas)
        return (svc or self.svc).salvar(self.ctx["admin"], IP, None, dados)

    def _editar(self, sid, **mudancas):
        f = self.svc.formulario(self.ctx["admin"], str(sid))
        dados = dict((c, "" if f[c] is None else str(f[c])) for c in scr_mod.CAMPOS_EDITAVEIS)
        dados["versao"] = f["versao"]
        dados.update(mudancas)
        return self.svc.salvar(self.ctx["admin"], IP, str(sid), dados)

    def _vinculos_json(self, sid):
        tela = self.svc.parametros(self.ctx["admin"], str(sid))
        return tela, [{"parametro_id": v["id"], "obrigatorio": v["obrigatorio"],
                       "valor_padrao_sub": v["valor_padrao_sub"], "manter_sigiloso": v["sensivel"]}
                      for v in tela["vinculos"]]


@_SKIP_ROOT
class TestCadastro(_Base):

    def test_inclusao_ok_e_auditoria(self):
        sid, erros, aviso = self._incluir()
        self.assertEqual((erros, aviso), ({}, None))
        s = self.catalogo.scripts_obter(sid)
        self.assertEqual((s["interpretador"], s["path_file"], s["max_qtd_parallel_env"], s["timeout_seg"]),
                         ("PYTHON3", self._p("novo.py"), 2, None))
        self.assertNotIn("pasta_base", s)
        self.assertIn("path_file: %s" % self._p("novo.py"), self._auditorias("CAD_INSERIR")[0]["detalhe"])

    def test_interpretador_fora_da_allowlist(self):
        for cmd in ("/bin/ls", "/usr/bin/python3", "PYTHON3 -c", "python3", "CMD", "POWERSHELL", "", None):
            _sid, erros, _ = self._incluir(interpretador=cmd)
            self.assertEqual(erros.get("interpretador"), scr_mod.MENSAGENS_PATH[Codigo.INTERPRETADOR_NAO_PERMITIDO], cmd)

    def test_path_file_invalidos(self):
        # CR-005 (README §8.5): caminho absoluto, normalizado e fora das pastas do sistema; vale em qualquer sss_env.
        casos = (("novo.py", Codigo.CAMINHO_RELATIVO), ("/etc/passwd", Codigo.PASTA_DO_SISTEMA),
                 ("/usr/local/bin/x.py", Codigo.PASTA_DO_SISTEMA), ("/etc/nao_existe.py", Codigo.PASTA_DO_SISTEMA),
                 (self.base + "/../x.py", Codigo.CONTEM_PONTOS), (self.base + "//novo.py", Codigo.CAMINHO_NAO_NORMALIZADO),
                 ("/opt\\x.py", Codigo.SEPARADOR_INVALIDO), (self._p("gravavel.py"), Codigo.GRAVAVEL_GRUPO_OUTROS),
                 (self._p("sub"), Codigo.NAO_E_ARQUIVO))
        for env in ("DEV", "HML"):
            svc = self._servico(env)
            for path, codigo in casos:
                _sid, erros, _ = self._incluir(svc=svc, path_file=path)
                self.assertEqual(erros.get("path_file"), scr_mod.MENSAGENS_PATH[codigo], (env, path))
        _sid, erros, _ = self._incluir(path_file="/opt/" + "a" * 500)
        self.assertEqual(erros.get("path_file"), u"Use no máximo 500 caracteres.")

    def test_symlink_para_pasta_do_sistema(self):
        os.chmod(self.base, stat.S_IRWXU)
        os.symlink("/etc/hostname", self._p("fuga.py"))
        os.chmod(self.base, 0o555)
        _sid, erros, _ = self._incluir(path_file=self._p("fuga.py"))
        self.assertEqual(erros, {"path_file": scr_mod.MENSAGENS_PATH[Codigo.PASTA_DO_SISTEMA]})

    def test_arquivo_ausente_vira_aviso_em_qualquer_ambiente(self):
        # CR-005 D4: se o arquivo nao existe neste servidor, salva com aviso; o agente confere no claim.
        for env in ("DEV", "HML", "PROD"):
            sid, erros, aviso = self._incluir(svc=self._servico(env), nome="Sem arquivo %s" % env,
                                              path_file="/opt/automacoes/scripts/nao_existe_%s.py" % env)
            self.assertEqual((erros, aviso), ({}, scr_mod.AVISO_NAO_ENCONTRADO), env)
            self.assertIsNotNone(sid)

    def test_pastas_de_log_e_trabalho_do_sss(self):
        svc = self._servico("HML", dirs_sss=(self._p("sub"), "/var/lib/sss/work"))
        _sid, erros, _ = self._incluir(svc=svc, path_file=self._p("sub/interno.sh"))
        self.assertEqual(erros, {"path_file": scr_mod.MENSAGENS_PATH[Codigo.PASTA_DO_SSS]})

    def test_campos_numericos_e_nome(self):
        for valor in ("0", "1000", "x", ""):
            _sid, erros, _ = self._incluir(max_qtd_parallel_env=valor)
            self.assertEqual(erros.get("max_qtd_parallel_env"), scr_mod.MSG_PARALELO, valor)
        _sid, erros, _ = self._incluir(timeout_seg="0")
        self.assertEqual(erros.get("timeout_seg"), scr_mod.MSG_TIMEOUT)
        _sid, erros, _ = self._incluir(nome="carga_diaria")
        self.assertEqual(erros, {"nome": scr_mod.MSG_NOME_DUPLICADO})
        _sid, erros, _ = self._incluir(nome="nome\x07estranho")
        self.assertEqual(erros, {"nome": scr_mod.MSG_CONTROLE})
        # Nome unico diferencia maiusculas (README §8.5), como a UK no Oracle.
        _sid, erros, _a = self._incluir(nome="CARGA_DIARIA")
        self.assertNotIn("nome", erros)

    def test_nome_reservado_app(self):
        # CR-005 D7: a pasta de log do script nao pode ser 'app'.
        for nome in ("app", "APP", "App.", "_app_", u"Áṕp"):
            _sid, erros, _ = self._incluir(nome=nome)
            self.assertEqual(erros.get("nome"), scr_mod.MSG_NOME_RESERVADO, nome)
        for nome in ("app2", "minha app", "aplicacao"):
            _sid, erros, _ = self._incluir(nome=nome)
            self.assertNotIn("nome", erros, nome)

    def test_edicao_sem_mudar_caminho_nao_reconfere_arquivo_mas_reativacao_reconfere(self):
        # README §8.5: arquivo com problema nao impede editar a descricao nem desativar.
        svc = self._servico("HML")
        sid = self.catalogo.scripts_inserir({"nome": "Gravavel", "interpretador": "PYTHON3",
                                             "path_file": self._p("gravavel.py"), "tipo_param": "SEQUENCIAL"})["id"]
        f = svc.formulario(self.ctx["admin"], str(sid))
        dados = dict((c, "" if f[c] is None else str(f[c])) for c in scr_mod.CAMPOS_EDITAVEIS)
        _sid, erros, _a = svc.salvar(self.ctx["admin"], IP, str(sid), dict(dados, versao=f["versao"], descricao="Nova"))
        self.assertEqual(erros, {})
        _sid, erros, _a = svc.salvar(self.ctx["admin"], IP, str(sid),
                                     dict(dados, versao=svc.formulario(self.ctx["admin"], str(sid))["versao"],
                                          interpretador="BASH"))
        self.assertEqual(erros, {"path_file": scr_mod.MENSAGENS_PATH[Codigo.GRAVAVEL_GRUPO_OUTROS]})
        svc.alternar_ativo(self.ctx["admin"], IP, str(sid), svc.formulario(self.ctx["admin"], str(sid))["versao"])
        with self.assertRaises(OperacaoNegada):
            svc.alternar_ativo(self.ctx["admin"], IP, str(sid), svc.formulario(self.ctx["admin"], str(sid))["versao"])
        self.assertEqual(self.catalogo.scripts_obter(sid)["ativo"], "N")
        # Arquivo ausente nao impede reativar: o agente confere (D4).
        self.catalogo.scripts_alterar(sid, {"path_file": "/opt/automacoes/scripts/sumiu.py"})
        svc.alternar_ativo(self.ctx["admin"], IP, str(sid), svc.formulario(self.ctx["admin"], str(sid))["versao"])
        self.assertEqual(self.catalogo.scripts_obter(sid)["ativo"], "S")

    def test_troca_de_tipo_param_revalida_vinculos(self):
        _sid, erros, _ = self._editar(S_CARGA, tipo_param="NENHUM")
        self.assertEqual(erros, {"tipo_param": scr_mod.MSG_NENHUM_VINCULADO})
        # Script SEQUENCIAL com parametro sem flag nao pode virar NOMEADO.
        pid = self.catalogo.parametros_inserir({"codigo": "sem_flag", "label": "Sem flag", "tipo_componente": "TEXT"})["id"]
        sid, _e, _a = self._incluir()
        self.catalogo.script_params_salvar(sid, [{"parametro_id": pid, "ordem": 1, "obrigatorio": "N"}])
        _sid, erros, _ = self._editar(sid, tipo_param="NOMEADO")
        self.assertIn("sem_flag", erros["tipo_param"])
        with self.assertRaises(RepoViolacao) as cm:
            self.catalogo.scripts_alterar(sid, {"tipo_param": "NOMEADO"})
        self.assertEqual(cm.exception.constraint, "sss_scr_nomeado_sem_flag")

    def test_desativacao_com_agendamentos_e_conflito(self):
        f = self.svc.formulario(self.ctx["admin"], str(S_CARGA))
        self.assertEqual(f["agendamentos_ativos"], 2)
        self.assertEqual(self.svc.alternar_ativo(self.ctx["admin"], IP, str(S_CARGA), f["versao"])["ativo"], "N")
        self.assertIn("agendamentos ativos afetados: 2", self._auditorias("CAD_DESATIVAR")[0]["detalhe"])
        with self.assertRaises(RepoConflito):
            self.svc.alternar_ativo(self.ctx["admin"], IP, str(S_CARGA), f["versao"])

    def test_formulario_sem_pastas_base(self):
        f = self.svc.formulario(self.ctx["admin"])
        for chave in ("pasta_base", "pastas", "base_exibicao"):
            self.assertNotIn(chave, f)
        self.assertEqual(self.svc.formulario(self.ctx["gestor"], str(S_CARGA))["path_file"],
                         "/opt/automacoes/scripts/carga_diaria.py")


@_SKIP_ROOT
class TestHomologacao(_Base):

    def test_homologacao_com_auditoria_e_inativo(self):
        tela = self.svc.homologacao(self.ctx["admin"], str(S_CARGA))
        nomes = [a["nome"] for a in tela["ambientes"]]
        self.assertNotIn("DESENV", nomes)
        diff, erros = self.svc.salvar_homologacao(self.ctx["admin"], IP, str(S_CARGA), [str(AMB_PROD)], tela["versao"])
        self.assertEqual(erros, {})
        self.assertIn("-HOMOLOGACAO", diff)
        self.assertEqual(self.catalogo.homologacao_obter(S_CARGA), [AMB_PROD])
        self.assertIn(u"homologação:", self._auditorias("CAD_ALTERAR")[0]["detalhe"])
        tela = self.svc.homologacao(self.ctx["admin"], str(S_CARGA))
        _diff, erros = self.svc.salvar_homologacao(self.ctx["admin"], IP, str(S_CARGA),
                                                   [str(AMB_PROD), str(AMB_DESENV)], tela["versao"])
        self.assertEqual(erros, {CAMPO_GERAL: scr_mod.MSG_HOMOLOG_INATIVO})

    def test_homologacao_inativa_pode_sair_e_nao_volta(self):
        # CR-003 D9: inativo ja homologado pode ser removido; nunca readicionado.
        self.catalogo.homologacao_salvar(S_CARGA, [AMB_PROD, AMB_DESENV])
        tela = self.svc.homologacao(self.ctx["admin"], str(S_CARGA))
        desenv = [a for a in tela["ambientes"] if a["nome"] == "DESENV"][0]
        self.assertTrue(desenv["marcado"] and desenv["inativo"])
        diff, _ = self.svc.salvar_homologacao(self.ctx["admin"], IP, str(S_CARGA),
                                              [str(AMB_PROD), str(AMB_HML), str(AMB_DESENV)], tela["versao"])
        self.assertEqual(diff, "+HOMOLOGACAO")
        self.assertEqual(self.catalogo.homologacao_obter(S_CARGA), [AMB_PROD, AMB_HML, AMB_DESENV])
        tela = self.svc.homologacao(self.ctx["admin"], str(S_CARGA))
        diff, _ = self.svc.salvar_homologacao(self.ctx["admin"], IP, str(S_CARGA), [str(AMB_PROD), str(AMB_HML)],
                                              tela["versao"])
        self.assertEqual(diff, "-DESENV")
        self.assertEqual(self.catalogo.homologacao_obter(S_CARGA), [AMB_PROD, AMB_HML])
        tela = self.svc.homologacao(self.ctx["admin"], str(S_CARGA))
        _d, erros = self.svc.salvar_homologacao(self.ctx["admin"], IP, str(S_CARGA),
                                                [str(AMB_PROD), str(AMB_HML), str(AMB_DESENV)], tela["versao"])
        self.assertIn(CAMPO_GERAL, erros)

    def test_conflito_e_ids_invalidos(self):
        tela = self.svc.homologacao(self.ctx["admin"], str(S_CARGA))
        self.svc.salvar_homologacao(self.ctx["admin"], IP, str(S_CARGA), [str(AMB_PROD)], tela["versao"])
        _d, erros = self.svc.salvar_homologacao(self.ctx["admin"], IP, str(S_CARGA), [], tela["versao"])
        self.assertEqual(erros, {CAMPO_GERAL: admin_crud.MSG_CONFLITO})
        tela = self.svc.homologacao(self.ctx["admin"], str(S_CARGA))
        for ids in (["x"], ["999"]):
            _d, erros = self.svc.salvar_homologacao(self.ctx["admin"], IP, str(S_CARGA), ids, tela["versao"])
            self.assertEqual(erros, {CAMPO_GERAL: scr_mod.MSG_HOMOLOG_INVALIDA})


@_SKIP_ROOT
class TestVinculos(_Base):

    def test_sub_sigiloso_mantido_e_revalidado_e_pode_ser_removido(self):
        # CR-003 P6 (README §6.5).
        tela, itens = self._vinculos_json(S_CARGA)
        self.catalogo.parametros_alterar(6, {"regex_validacao": "^x$"})  # documento_cliente: o sub gravado deixa de valer
        _d, erros = self.svc.salvar_parametros(self.ctx["admin"], IP, str(S_CARGA), json.dumps(itens), tela["versao"])
        self.assertEqual(erros, {"vinculo_6": scr_mod.MSG_SIGILOSO_INVALIDO})
        for item in itens:
            if item["parametro_id"] == 6:
                item["manter_sigiloso"] = False  # "Remover valor"
        _d, erros = self.svc.salvar_parametros(self.ctx["admin"], IP, str(S_CARGA), json.dumps(itens), tela["versao"])
        self.assertEqual(erros, {})
        sub = [v for v in self.catalogo.script_params_obter(S_CARGA) if v["parametro_id"] == 6][0]["valor_padrao_sub"]
        self.assertIsNone(sub)

    def test_detalhe_dos_vinculos_passa_pelo_masking(self):
        import masking
        masking.MASCARADOR.registrar("SEGREDO-DE-INFRA-9")
        tela, itens = self._vinculos_json(S_CARGA)
        for item in itens:
            if item["parametro_id"] == 1:
                item["valor_padrao_sub"] = None
        itens.append({"parametro_id": 10, "obrigatorio": False, "valor_padrao_sub": "SEGREDO-DE-INFRA-9"})
        _d, erros = self.svc.salvar_parametros(self.ctx["admin"], IP, str(S_CARGA), json.dumps(itens), tela["versao"])
        self.assertEqual(erros, {})
        self.assertNotIn("SEGREDO-DE-INFRA-9", self._auditorias("CAD_ALTERAR")[0]["detalhe"])

    def test_versao_dos_vinculos_nao_deriva_do_sub_sensivel(self):
        # CR-003 P1: o sub sensivel entra na versao pelo marcador, nunca pelo valor.
        v1 = self.svc.parametros(self.ctx["admin"], str(S_CARGA))["versao"]
        vinc = self.catalogo.script_params_obter(S_CARGA)
        lidos = [dict((k, v[k]) for k in ("parametro_id", "ordem", "obrigatorio", "valor_padrao_sub")) for v in vinc]
        for v in lidos:
            if v["valor_padrao_sub"] == "00011122233":
                v["valor_padrao_sub"] = "outro-segredo-456"
        self.catalogo.script_params_salvar(S_CARGA, lidos)
        tela = self.svc.parametros(self.ctx["admin"], str(S_CARGA))
        self.assertEqual(tela["versao"], v1)
        self.assertNotEqual(tela["versao"], scr_mod._hash(scr_mod._lidos(self.catalogo.script_params_obter(S_CARGA))))
        self.assertNotIn("outro-segredo-456", repr(tela))

    def test_renumeracao_e_reordenacao(self):
        tela, itens = self._vinculos_json(S_CARGA)
        itens.reverse()
        desc, erros = self.svc.salvar_parametros(self.ctx["admin"], IP, str(S_CARGA), json.dumps(itens), tela["versao"])
        self.assertEqual(erros, {})
        vinc = self.catalogo.script_params_obter(S_CARGA)
        self.assertEqual([v["ordem"] for v in vinc], [1, 2, 3, 4, 5])
        self.assertEqual(vinc[0]["codigo"], "documento_cliente")
        # Sub sigiloso preservado ("manter") e mascarado na auditoria.
        self.assertEqual(vinc[0]["valor_padrao_sub"], "00011122233")
        detalhe = self._auditorias("CAD_ALTERAR")[0]["detalhe"]
        self.assertNotIn("00011122233", detalhe)
        self.assertIn("documento_cliente=****", detalhe)
        self.assertNotIn("00011122233", repr(self.svc.parametros(self.ctx["admin"], str(S_CARGA))))

    def test_vinculo_duplicado_inexistente_e_json_invalido(self):
        tela, itens = self._vinculos_json(S_CARGA)
        for corpo in (json.dumps(itens + [itens[0]]), json.dumps(itens + [{"parametro_id": 999}]), "{", '{"a": 1}'):
            _d, erros = self.svc.salvar_parametros(self.ctx["admin"], IP, str(S_CARGA), corpo, tela["versao"])
            self.assertIn(CAMPO_GERAL, erros, corpo[:30])

    def test_nomeado_com_parametro_sem_flag(self):
        pid = self.catalogo.parametros_inserir({"codigo": "sem_flag", "label": "Sem flag", "tipo_componente": "TEXT"})["id"]
        tela, itens = self._vinculos_json(S_CARGA)
        _d, erros = self.svc.salvar_parametros(self.ctx["admin"], IP, str(S_CARGA),
                                               json.dumps(itens + [{"parametro_id": pid}]), tela["versao"])
        self.assertIn("sem_flag", erros[CAMPO_GERAL])
        with self.assertRaises(RepoViolacao):
            self.catalogo.script_params_salvar(S_CARGA, [{"parametro_id": pid, "ordem": 1, "obrigatorio": "N"}])

    def test_nenhum_com_vinculo(self):
        tela = self.svc.parametros(self.ctx["admin"], str(S_CLEANUP))
        _d, erros = self.svc.salvar_parametros(self.ctx["admin"], IP, str(S_CLEANUP),
                                               json.dumps([{"parametro_id": 1}]), tela["versao"])
        self.assertEqual(erros, {CAMPO_GERAL: scr_mod.MSG_VINCULO_NENHUM})

    def test_valor_padrao_sub_validado_e_inativo_rejeitado(self):
        tela, itens = self._vinculos_json(S_CARGA)
        itens[0]["valor_padrao_sub"] = "31/12/2026"  # data_ref e DATE
        _d, erros = self.svc.salvar_parametros(self.ctx["admin"], IP, str(S_CARGA), json.dumps(itens), tela["versao"])
        self.assertIn("vinculo_1", erros)
        pid = self.catalogo.parametros_inserir({"codigo": "inativo_x", "label": "X", "tipo_componente": "TEXT",
                                                "param_nomeado": "--x", "ativo": "N"})["id"]
        tela, itens = self._vinculos_json(S_CARGA)
        _d, erros = self.svc.salvar_parametros(self.ctx["admin"], IP, str(S_CARGA),
                                               json.dumps(itens + [{"parametro_id": pid}]), tela["versao"])
        self.assertIn("inativo", erros[CAMPO_GERAL])

    def test_conflito_de_vinculos(self):
        tela, itens = self._vinculos_json(S_CARGA)
        self.svc.salvar_parametros(self.ctx["admin"], IP, str(S_CARGA), json.dumps(itens[:-1]), tela["versao"])
        _d, erros = self.svc.salvar_parametros(self.ctx["admin"], IP, str(S_CARGA), json.dumps(itens), tela["versao"])
        self.assertEqual(erros, {CAMPO_GERAL: admin_crud.MSG_CONFLITO})


@_SKIP_ROOT
class TestPrevia(_Base):

    def test_previa_do_seed_gera_argv_esperado_e_mascara_sensivel(self):
        r = self.svc.previa(self.ctx["admin"], str(S_CARGA))
        real = "/opt/automacoes/scripts/carga_diaria.py"
        self.assertEqual((r["erros"], r["aviso"]), ({}, scr_mod.AVISO_NAO_ENCONTRADO))
        self.assertEqual(r["argv"], ["PYTHON3", "-I", real, "--data-ref", "2026-10-14", "-n", "5000",
                                     "--modo", "REAL", "--verbose", "--documento", "****"])

    def test_previa_no_cadastro_mostra_o_caminho_e_reflete_edicao(self):
        # CR-005 R-f: no cadastro (CAD_SCRIPTS) o caminho aparece inteiro, porque e o que o usuario cadastra.
        _tela, itens = self._vinculos_json(S_CARGA)
        r = self.svc.previa(self.ctx["gestor"], str(S_CARGA), json.dumps(itens[:1]))
        self.assertEqual(r["argv"], ["PYTHON3", "-I", "/opt/automacoes/scripts/carga_diaria.py",
                                     "--data-ref", "2026-10-14"])

    def test_acesso_negado_e_nao_encontrado(self):
        for chamada in (lambda c: self.svc.listar(c, {}, 1, 20), lambda c: self.svc.homologacao(c, "1"),
                        lambda c: self.svc.parametros(c, "1"), lambda c: self.svc.previa(c, "1")):
            with self.assertRaises(AcessoNegado):
                chamada(self.ctx["op.prod"])
        with self.assertRaises(RepoNaoEncontrado):
            self.svc.formulario(self.ctx["admin"], "999")

    def test_lista_com_homologados_e_parametros(self):
        pagina = self.svc.listar(self.ctx["admin"], {"interpretador": "PYTHON3"}, 1, 20)
        carga = [s for s in pagina["itens"] if s["nome"] == "carga_diaria"][0]
        self.assertEqual(carga["qtd_parametros"], 5)
        self.assertIn("PRODUCAO", carga["ambientes_homologados"])
        self.assertTrue(all(s["interpretador"] == "PYTHON3" for s in pagina["itens"]))
        self.assertEqual(scr_mod.normalizar_filtros({"interpretador": "/bin/ls", "ativo": "S"}), {"ativo": "S"})
        self.assertEqual(scr_mod.normalizar_filtros({"interpretador": "POWERSHELL"}), {})


if __name__ == "__main__":
    unittest.main()
