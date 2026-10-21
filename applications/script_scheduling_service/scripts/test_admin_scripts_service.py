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
from admin_crud import GENERAL_FIELD, AccessDenied, OperationDenied
from admin_scripts_service import AdminScriptsService
from path_guard import Code
from repo_errors import RepoConflict, RepoNotFound, RepoViolation

# UID fictício do agente: o dono dos arquivos de teste é o usuário do teste (CR-007, R-15).
AGENTE_FALSO = 2 ** 31 - 3

IP = "10.5.5.5"
AGORA = datetime.datetime(2026, 10, 15, 10, 0, 0)
SESSOES = {
    "admin": {"usuario_id": 1, "login": "admin", "perfil_id": 1, "perm_versao": 1, "sessao_epoch": 0},
    "op.prod": {"usuario_id": 2, "login": "op.prod", "perfil_id": 2, "perm_versao": 1, "sessao_epoch": 0},
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
        patcher = mock.patch.object(security, "ITERATIONS", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {repo_factory.ENV_DEV_PASSWORD: "senha-dev-de-teste-123"})
        env.start()
        self.addCleanup(env.stop)
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.addCleanup(repo_factory.reset_singletons)
        self.addCleanup(repo_factory.configure, None)

        self.catalog = repo_factory.get("catalog")
        self.audit = repo_factory.get("audit")
        self.log = logging.getLogger("sss_teste_scripts")
        self.log.addHandler(logging.NullHandler())
        self.log.propagate = False
        auth = auth_service.AuthService(repo_factory.get("users"), repo_factory.get("rbac"), self.catalog,
                                        self.audit, 5, 900, self.log)
        self.ctx = dict((login, auth.revalidate(sessao)) for login, sessao in SESSOES.items())
        self.ctx["gestor"] = dict(self.ctx["op.prod"], features=frozenset(["MANAGE_SCRIPTS"]))
        self.base = _arvore()
        self.addCleanup(_remover, self.base)
        self.svc = self._servico(self.ENV)
        self.aud_base = max([a["id"] for a in self.audit.list(pagina=1, tamanho=1000)["itens"]] or [0])

    def _servico(self, env):
        return AdminScriptsService(self.catalog, repo_factory.get("schedules"), env, self.log, lambda: AGORA)

    def _p(self, nome):
        return os.path.join(self.base, nome)

    def _auditorias(self, acao):
        return [a for a in self.audit.list(filtros={"action": acao}, pagina=1, tamanho=100)["itens"]
                if a["entity"] == "tbsss_scripts" and a["id"] > self.aud_base]

    def _insert(self, svc=None, **mudancas):
        dados = {"name": "Novo script", "interpreter": "PYTHON3", "path_file": self._p("novo.py"),
                 "param_type": "POSITIONAL", "max_parallel_env": "2", "timeout_s": ""}
        dados.update(mudancas)
        return (svc or self.svc).save(self.ctx["admin"], IP, None, dados)

    def _editar(self, sid, **mudancas):
        f = self.svc.form(self.ctx["admin"], str(sid))
        dados = dict((c, "" if f[c] is None else str(f[c])) for c in scr_mod.EDITABLE_FIELDS)
        dados["version"] = f["version"]
        dados.update(mudancas)
        return self.svc.save(self.ctx["admin"], IP, str(sid), dados)

    def _vinculos_json(self, sid):
        tela = self.svc.parameters(self.ctx["admin"], str(sid))
        return tela, [{"parameter_id": v["id"], "required": v["required"],
                       "default_value_override": v["default_value_override"], "manter_sigiloso": v["sensitive"]}
                      for v in tela["vinculos"]]


@_SKIP_ROOT
class TestCadastro(_Base):

    def test_inclusao_ok_e_auditoria(self):
        sid, erros, aviso = self._insert()
        self.assertEqual((erros, aviso), ({}, None))
        s = self.catalog.scripts_get(sid)
        self.assertEqual((s["interpreter"], s["path_file"], s["max_parallel_env"], s["timeout_s"]),
                         ("PYTHON3", self._p("novo.py"), 2, None))
        self.assertNotIn("pasta_base", s)
        self.assertIn("path_file: %s" % self._p("novo.py"), self._auditorias("CREATE")[0]["detail"])

    def test_interpretador_fora_da_allowlist(self):
        for cmd in ("/bin/ls", "/usr/bin/python3", "PYTHON3 -c", "python3", "CMD", "POWERSHELL", "", None):
            _sid, erros, _ = self._insert(interpreter=cmd)
            self.assertEqual(erros.get("interpreter"), scr_mod.PATH_MESSAGES[Code.INTERPRETADOR_NAO_PERMITIDO], cmd)

    def test_path_file_invalidos(self):
        # CR-005 (README §8.5): caminho absoluto, normalizado e fora das pastas do sistema; vale em qualquer sss_env.
        casos = (("novo.py", Code.RELATIVE_PATH), ("/etc/passwd", Code.SYSTEM_DIR),
                 ("/usr/local/bin/x.py", Code.SYSTEM_DIR), ("/etc/nao_existe.py", Code.SYSTEM_DIR),
                 (self.base + "/../x.py", Code.HAS_DOTS), (self.base + "//novo.py", Code.PATH_NOT_NORMALIZED),
                 ("/opt\\x.py", Code.INVALID_SEPARATOR))
        for env in ("DEV", "HML"):
            svc = self._servico(env)
            for path, codigo in casos:
                _sid, erros, _ = self._insert(svc=svc, path_file=path)
                self.assertEqual(erros.get("path_file"), scr_mod.PATH_MESSAGES[codigo], (env, path))
        _sid, erros, _ = self._insert(path_file="/opt/" + "a" * 500)
        self.assertEqual(erros.get("path_file"), u"Use no máximo 500 caracteres.")

    def test_symlink_para_pasta_do_sistema(self):
        os.chmod(self.base, stat.S_IRWXU)
        os.symlink("/etc/hostname", self._p("fuga.py"))
        os.chmod(self.base, 0o555)
        _sid, erros, _ = self._insert(path_file=self._p("fuga.py"))
        self.assertEqual(erros, {"path_file": scr_mod.PATH_MESSAGES[Code.SYSTEM_DIR]})

    def test_arquivo_nao_e_conferido_no_cadastro(self):
        # CR-011 (S1): ausente, gravavel ou pasta neste servidor nao importam aqui; o agente confere ao executar.
        for env in ("DEV", "HML", "PROD"):
            for i, caminho in enumerate(("/opt/automacoes/scripts/nao_existe.py", self._p("gravavel.py"), self._p("sub"))):
                sid, erros, aviso = self._insert(svc=self._servico(env), name="Sem conferencia %s %d" % (env, i),
                                                  path_file=caminho)
                self.assertEqual((erros, aviso), ({}, None), (env, caminho))
                self.assertIsNotNone(sid)

    def test_campos_numericos_e_nome(self):
        for valor in ("0", "1000", "x", ""):
            _sid, erros, _ = self._insert(max_parallel_env=valor)
            self.assertEqual(erros.get("max_parallel_env"), scr_mod.MSG_PARALLEL, valor)
        _sid, erros, _ = self._insert(timeout_s="0")
        self.assertEqual(erros.get("timeout_s"), scr_mod.MSG_TIMEOUT)
        _sid, erros, _ = self._insert(name="carga_diaria")
        self.assertEqual(erros, {"name": scr_mod.MSG_NAME_DUPLICATE})
        _sid, erros, _ = self._insert(name="nome\x07estranho")
        self.assertEqual(erros, {"name": scr_mod.MSG_CONTROL_CHARS})
        # Nome unico diferencia maiusculas (README §8.5), como a UK no Oracle.
        _sid, erros, _a = self._insert(name="CARGA_DIARIA")
        self.assertNotIn("name", erros)

    def test_nome_reservado_app(self):
        # CR-005 D7: a pasta de log do script nao pode ser 'app'.
        for nome in ("app", "APP", "App.", "_app_", u"Áṕp"):
            _sid, erros, _ = self._insert(name=nome)
            self.assertEqual(erros.get("name"), scr_mod.MSG_NAME_RESERVED, nome)
        for nome in ("app2", "minha app", "aplicacao"):
            _sid, erros, _ = self._insert(name=nome)
            self.assertNotIn("name", erros, nome)

    def test_edicao_e_reativacao_sem_conferir_o_arquivo(self):
        # CR-011 (S1): o estado do arquivo neste servidor nao impede editar, desativar nem reativar.
        svc = self._servico("HML")
        sid = self.catalog.scripts_insert({"name": "Gravavel", "interpreter": "PYTHON3",
                                             "path_file": self._p("gravavel.py"), "param_type": "POSITIONAL"}, ator="teste")["id"]
        f = svc.form(self.ctx["admin"], str(sid))
        dados = dict((c, "" if f[c] is None else str(f[c])) for c in scr_mod.EDITABLE_FIELDS)
        _sid, erros, _a = svc.save(self.ctx["admin"], IP, str(sid), dict(dados, version=f["version"], description="Nova"))
        self.assertEqual(erros, {})
        _sid, erros, _a = svc.save(self.ctx["admin"], IP, str(sid),
                                     dict(dados, version=svc.form(self.ctx["admin"], str(sid))["version"],
                                          interpreter="BASH"))
        self.assertEqual(erros, {})
        svc.toggle_active(self.ctx["admin"], IP, str(sid), svc.form(self.ctx["admin"], str(sid))["version"])
        self.assertEqual(self.catalog.scripts_get(sid)["active"], "N")
        svc.toggle_active(self.ctx["admin"], IP, str(sid), svc.form(self.ctx["admin"], str(sid))["version"])
        self.assertEqual(self.catalog.scripts_get(sid)["active"], "Y")
        # Reativar ainda confere o formato e as pastas do sistema.
        self.catalog.scripts_update(sid, {"path_file": "/etc/sumiu.py", "active": "N"}, ator="teste")
        with self.assertRaises(OperationDenied):
            svc.toggle_active(self.ctx["admin"], IP, str(sid), svc.form(self.ctx["admin"], str(sid))["version"])

    def test_troca_de_tipo_param_revalida_vinculos(self):
        _sid, erros, _ = self._editar(S_CARGA, param_type="NONE")
        self.assertEqual(erros, {"param_type": scr_mod.MSG_NONE_LINKED})
        # Script SEQUENCIAL com parametro sem flag nao pode virar NOMEADO.
        pid = self.catalog.parameters_insert({"code": "sem_flag", "label": "Sem flag", "component_type": "TEXT"}, ator="teste")["id"]
        sid, _e, _a = self._insert()
        self.catalog.script_params_save(sid, [{"parameter_id": pid, "sort_order": 1, "required": "N"}], ator="teste")
        _sid, erros, _ = self._editar(sid, param_type="NAMED")
        self.assertIn("sem_flag", erros["param_type"])
        with self.assertRaises(RepoViolation) as cm:
            self.catalog.scripts_update(sid, {"param_type": "NAMED"}, ator="teste")
        self.assertEqual(cm.exception.constraint, "sss_scr_nomeado_sem_flag")

    def test_desativacao_com_agendamentos_e_conflito(self):
        f = self.svc.form(self.ctx["admin"], str(S_CARGA))
        self.assertEqual(f["agendamentos_ativos"], 2)
        self.assertEqual(self.svc.toggle_active(self.ctx["admin"], IP, str(S_CARGA), f["version"])["active"], "N")
        self.assertIn("agendamentos ativos afetados: 2", self._auditorias("DEACTIVATE")[0]["detail"])
        with self.assertRaises(RepoConflict):
            self.svc.toggle_active(self.ctx["admin"], IP, str(S_CARGA), f["version"])

    def test_formulario_sem_pastas_base(self):
        f = self.svc.form(self.ctx["admin"])
        for chave in ("pasta_base", "pastas", "base_exibicao"):
            self.assertNotIn(chave, f)
        self.assertEqual(self.svc.form(self.ctx["gestor"], str(S_CARGA))["path_file"],
                         "/opt/automacoes/scripts/carga_diaria.py")


@_SKIP_ROOT
class TestHomologacao(_Base):

    def test_homologacao_com_auditoria_e_inativo(self):
        tela = self.svc.homologation(self.ctx["admin"], str(S_CARGA))
        nomes = [a["name"] for a in tela["environments"]]
        self.assertNotIn("DESENV", nomes)
        diff, erros = self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA), [str(AMB_PROD)], tela["version"])
        self.assertEqual(erros, {})
        self.assertIn("-HOMOLOGACAO", diff)
        self.assertEqual(self.catalog.homologation_get(S_CARGA), [AMB_PROD])
        self.assertIn(u"homologação:", self._auditorias("UPDATE")[0]["detail"])
        tela = self.svc.homologation(self.ctx["admin"], str(S_CARGA))
        _diff, erros = self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA),
                                                   [str(AMB_PROD), str(AMB_DESENV)], tela["version"])
        self.assertEqual(erros, {GENERAL_FIELD: scr_mod.MSG_HOMOLOG_INACTIVE})

    def test_homologacao_inativa_pode_sair_e_nao_volta(self):
        # CR-003 D9: inativo ja homologado pode ser removido; nunca readicionado.
        self.catalog.homologation_save(S_CARGA, [AMB_PROD, AMB_DESENV], ator="teste")
        tela = self.svc.homologation(self.ctx["admin"], str(S_CARGA))
        desenv = [a for a in tela["environments"] if a["name"] == "DESENV"][0]
        self.assertTrue(desenv["marcado"] and desenv["inativo"])
        diff, _ = self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA),
                                              [str(AMB_PROD), str(AMB_HML), str(AMB_DESENV)], tela["version"])
        self.assertEqual(diff, "+HOMOLOGACAO")
        self.assertEqual(self.catalog.homologation_get(S_CARGA), [AMB_PROD, AMB_HML, AMB_DESENV])
        tela = self.svc.homologation(self.ctx["admin"], str(S_CARGA))
        diff, _ = self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA), [str(AMB_PROD), str(AMB_HML)],
                                              tela["version"])
        self.assertEqual(diff, "-DESENV")
        self.assertEqual(self.catalog.homologation_get(S_CARGA), [AMB_PROD, AMB_HML])
        tela = self.svc.homologation(self.ctx["admin"], str(S_CARGA))
        _d, erros = self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA),
                                                [str(AMB_PROD), str(AMB_HML), str(AMB_DESENV)], tela["version"])
        self.assertIn(GENERAL_FIELD, erros)

    def test_conflito_e_ids_invalidos(self):
        tela = self.svc.homologation(self.ctx["admin"], str(S_CARGA))
        self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA), [str(AMB_PROD)], tela["version"])
        _d, erros = self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA), [], tela["version"])
        self.assertEqual(erros, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})
        tela = self.svc.homologation(self.ctx["admin"], str(S_CARGA))
        for ids in (["x"], ["999"]):
            _d, erros = self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA), ids, tela["version"])
            self.assertEqual(erros, {GENERAL_FIELD: scr_mod.MSG_HOMOLOG_INVALID})


@_SKIP_ROOT
class TestVinculos(_Base):

    def test_sub_sigiloso_mantido_e_revalidado_e_pode_ser_removido(self):
        # CR-003 P6 (README §6.5).
        tela, itens = self._vinculos_json(S_CARGA)
        self.catalog.parameters_update(6, {"validation_regex": "^x$"}, ator="teste")  # documento_cliente: o sub gravado deixa de valer
        _d, erros = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), json.dumps(itens), tela["version"])
        self.assertEqual(erros, {"vinculo_6": scr_mod.MSG_SENSITIVE_INVALID})
        for item in itens:
            if item["parameter_id"] == 6:
                item["manter_sigiloso"] = False  # "Remover valor"
        _d, erros = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), json.dumps(itens), tela["version"])
        self.assertEqual(erros, {})
        sub = [v for v in self.catalog.script_params_get(S_CARGA) if v["parameter_id"] == 6][0]["default_value_override"]
        self.assertIsNone(sub)

    def test_detalhe_dos_vinculos_passa_pelo_masking(self):
        import masking
        masking.MASKER.register("SEGREDO-DE-INFRA-9")
        tela, itens = self._vinculos_json(S_CARGA)
        for item in itens:
            if item["parameter_id"] == 1:
                item["default_value_override"] = None
        itens.append({"parameter_id": 10, "required": False, "default_value_override": "SEGREDO-DE-INFRA-9"})
        _d, erros = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), json.dumps(itens), tela["version"])
        self.assertEqual(erros, {})
        self.assertNotIn("SEGREDO-DE-INFRA-9", self._auditorias("UPDATE")[0]["detail"])

    def test_versao_dos_vinculos_nao_deriva_do_sub_sensivel(self):
        # CR-003 P1: o sub sensivel entra na versao pelo marcador, nunca pelo valor.
        v1 = self.svc.parameters(self.ctx["admin"], str(S_CARGA))["version"]
        vinc = self.catalog.script_params_get(S_CARGA)
        lidos = [dict((k, v[k]) for k in ("parameter_id", "sort_order", "required", "default_value_override")) for v in vinc]
        for v in lidos:
            if v["default_value_override"] == "00011122233":
                v["default_value_override"] = "outro-segredo-456"
        self.catalog.script_params_save(S_CARGA, lidos, ator="teste")
        tela = self.svc.parameters(self.ctx["admin"], str(S_CARGA))
        self.assertEqual(tela["version"], v1)
        self.assertNotEqual(tela["version"], scr_mod._hash(scr_mod._read_back(self.catalog.script_params_get(S_CARGA))))
        self.assertNotIn("outro-segredo-456", repr(tela))

    def test_renumeracao_e_reordenacao(self):
        tela, itens = self._vinculos_json(S_CARGA)
        itens.reverse()
        desc, erros = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), json.dumps(itens), tela["version"])
        self.assertEqual(erros, {})
        vinc = self.catalog.script_params_get(S_CARGA)
        self.assertEqual([v["sort_order"] for v in vinc], [1, 2, 3, 4, 5])
        self.assertEqual(vinc[0]["code"], "documento_cliente")
        # Sub sigiloso preservado ("manter") e mascarado na auditoria.
        self.assertEqual(vinc[0]["default_value_override"], "00011122233")
        detalhe = self._auditorias("UPDATE")[0]["detail"]
        self.assertNotIn("00011122233", detalhe)
        self.assertIn("documento_cliente=****", detalhe)
        self.assertNotIn("00011122233", repr(self.svc.parameters(self.ctx["admin"], str(S_CARGA))))

    def test_vinculo_duplicado_inexistente_e_json_invalido(self):
        tela, itens = self._vinculos_json(S_CARGA)
        for corpo in (json.dumps(itens + [itens[0]]), json.dumps(itens + [{"parameter_id": 999}]), "{", '{"a": 1}'):
            _d, erros = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), corpo, tela["version"])
            self.assertIn(GENERAL_FIELD, erros, corpo[:30])

    def test_nomeado_com_parametro_sem_flag(self):
        pid = self.catalog.parameters_insert({"code": "sem_flag", "label": "Sem flag", "component_type": "TEXT"}, ator="teste")["id"]
        tela, itens = self._vinculos_json(S_CARGA)
        _d, erros = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA),
                                               json.dumps(itens + [{"parameter_id": pid}]), tela["version"])
        self.assertIn("sem_flag", erros[GENERAL_FIELD])
        with self.assertRaises(RepoViolation):
            self.catalog.script_params_save(S_CARGA, [{"parameter_id": pid, "sort_order": 1, "required": "N"}], ator="teste")

    def test_nenhum_com_vinculo(self):
        tela = self.svc.parameters(self.ctx["admin"], str(S_CLEANUP))
        _d, erros = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CLEANUP),
                                               json.dumps([{"parameter_id": 1}]), tela["version"])
        self.assertEqual(erros, {GENERAL_FIELD: scr_mod.MSG_LINK_NONE})

    def test_valor_padrao_sub_validado_e_inativo_rejeitado(self):
        tela, itens = self._vinculos_json(S_CARGA)
        itens[0]["default_value_override"] = "31/12/2026"  # data_ref e DATE
        _d, erros = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), json.dumps(itens), tela["version"])
        self.assertIn("vinculo_1", erros)
        pid = self.catalog.parameters_insert({"code": "inativo_x", "label": "X", "component_type": "TEXT",
                                                "param_flag": "--x", "active": "N"}, ator="teste")["id"]
        tela, itens = self._vinculos_json(S_CARGA)
        _d, erros = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA),
                                               json.dumps(itens + [{"parameter_id": pid}]), tela["version"])
        self.assertIn("inativo", erros[GENERAL_FIELD])

    def test_conflito_de_vinculos(self):
        tela, itens = self._vinculos_json(S_CARGA)
        self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), json.dumps(itens[:-1]), tela["version"])
        _d, erros = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), json.dumps(itens), tela["version"])
        self.assertEqual(erros, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})


@_SKIP_ROOT
class TestPrevia(_Base):

    def test_previa_do_seed_gera_argv_esperado_e_mascara_sensivel(self):
        r = self.svc.preview(self.ctx["admin"], str(S_CARGA))
        real = "/opt/automacoes/scripts/carga_diaria.py"
        self.assertEqual((r["erros"], r["aviso"]), ({}, None))
        self.assertEqual(r["argv"], ["PYTHON3", "-I", real, "--data-ref", "2026-10-14", "-n", "5000",
                                     "--modo", "REAL", "--verbose", "--documento", "****"])

    def test_previa_no_cadastro_mostra_o_caminho_e_reflete_edicao(self):
        # CR-005 R-f: no cadastro (MANAGE_SCRIPTS) o caminho aparece inteiro, porque e o que o usuario cadastra.
        _tela, itens = self._vinculos_json(S_CARGA)
        r = self.svc.preview(self.ctx["gestor"], str(S_CARGA), json.dumps(itens[:1]))
        self.assertEqual(r["argv"], ["PYTHON3", "-I", "/opt/automacoes/scripts/carga_diaria.py",
                                     "--data-ref", "2026-10-14"])

    def test_acesso_negado_e_nao_encontrado(self):
        for chamada in (lambda c: self.svc.list(c, {}, 1, 20), lambda c: self.svc.homologation(c, "1"),
                        lambda c: self.svc.parameters(c, "1"), lambda c: self.svc.preview(c, "1")):
            with self.assertRaises(AccessDenied):
                chamada(self.ctx["op.prod"])
        with self.assertRaises(RepoNotFound):
            self.svc.form(self.ctx["admin"], "999")

    def test_lista_com_homologados_e_parametros(self):
        pagina = self.svc.list(self.ctx["admin"], {"interpreter": "PYTHON3"}, 1, 20)
        carga = [s for s in pagina["itens"] if s["name"] == "carga_diaria"][0]
        self.assertEqual(carga["qtd_parametros"], 5)
        self.assertIn("PRODUCAO", carga["ambientes_homologados"])
        self.assertTrue(all(s["interpreter"] == "PYTHON3" for s in pagina["itens"]))
        self.assertEqual(scr_mod.normalize_filters({"interpreter": "/bin/ls", "active": "Y"}), {"active": "Y"})
        self.assertEqual(scr_mod.normalize_filters({"interpreter": "POWERSHELL"}), {})


@_SKIP_ROOT
class TestSemHashELink(_Base):
    """CR-011: o cadastro nao calcula nem registra hash do arquivo, e o caminho pode ter link simbolico."""

    def test_inclusao_e_edicao_nao_registram_hash(self):
        sid, erros, _a = self._insert(path_file=self._p("novo.py"), sha256_informado="0" * 64,
                                       registrar_conteudo_atual="1")
        self.assertEqual(erros, {})
        self.assertIsNone(self.catalog.scripts_get(sid).get("sha256_homologado"))
        self.assertEqual(self._editar(sid, description="nova", registrar_conteudo_atual="1")[1], {})
        self.assertIsNone(self.catalog.scripts_get(sid).get("sha256_homologado"))
        self.assertNotIn("sha256_homologado", self.svc.form(self.ctx["admin"], str(sid)))
        for aud in self._auditorias("CREATE") + self._auditorias("UPDATE"):
            self.assertNotIn("sha256", aud["detail"])

    def test_caminho_com_link_simbolico_e_aceito(self):
        os.chmod(self.base, 0o755)
        link = self._p("atalho.py")
        os.symlink(self._p("novo.py"), link)
        os.chmod(self.base, 0o555)
        sid, erros, aviso = self._insert(path_file=link)
        self.assertEqual((erros, aviso), ({}, None))
        self.assertEqual(self.catalog.scripts_get(sid)["path_file"], link, "fica o caminho cadastrado")

    def test_link_para_pasta_do_sistema_e_recusado(self):
        os.chmod(self.base, 0o755)
        link = self._p("atalho_sistema.py")
        os.symlink("/etc/hostname", link)
        os.chmod(self.base, 0o555)
        _sid, erros, _a = self._insert(path_file=link)
        self.assertEqual(erros, {"path_file": scr_mod.PATH_MESSAGES[path_guard.Code.SYSTEM_DIR]})


if __name__ == "__main__":
    unittest.main()
