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
FAKE_AGENT = 2 ** 31 - 3

IP = "10.5.5.5"
NOW = datetime.datetime(2026, 10, 15, 10, 0, 0)
SESSIONS = {
    "admin": {"user_id": 1, "login": "admin", "profile_id": 1, "perm_version": 1, "session_epoch": 0},
    "op.prod": {"user_id": 2, "login": "op.prod", "profile_id": 2, "perm_version": 1, "session_epoch": 0},
}
# Seed FAKE: script 1 carga_diaria (NOMEADO, python3, vinculos data_ref, limite_linhas, modo_exec, verbose,
# documento_cliente sensivel), 3 cleanup_tmp (NENHUM). Ambientes 1 PRODUCAO, 2 HOMOLOGACAO, 3 DESENV (inativo).
# Parametros: 1 data_ref (--data-ref), 5 codigo_filial (--filial), 10 descricao_lote (--descricao), sem flag: nenhum
# no seed, por isso o teste cria um.
S_CARGA, S_CLEANUP = 1, 3
AMB_PROD, AMB_HML, AMB_DESENV = 1, 2, 3
FILES = ("carga_diaria.py", "relatorio_mensal.py", "cleanup_tmp.sh", "sync_tabelas.sh", "validacao_fiscal.py",
            "novo.py")


def _tree():
    base = tempfile.mkdtemp(prefix="sss_scr_")
    os.mkdir(os.path.join(base, "sub"))
    for name in FILES:
        with open(os.path.join(base, name), "w") as f:
            f.write("# teste\n")
        os.chmod(os.path.join(base, name), 0o444)
    with open(os.path.join(base, "gravavel.py"), "w") as f:
        f.write("# teste\n")
    os.chmod(os.path.join(base, "gravavel.py"), 0o666)
    with open(os.path.join(base, "sub", "interno.sh"), "w") as f:
        f.write("# teste\n")
    os.chmod(os.path.join(base, "sub", "interno.sh"), 0o444)
    os.chmod(os.path.join(base, "sub"), 0o555)
    os.chmod(base, 0o555)
    return os.path.realpath(base)


def _remove(base):
    for root, dirs, _arqs in os.walk(base):
        for d in dirs:
            os.chmod(os.path.join(root, d), stat.S_IRWXU)
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
        self.ctx = dict((login, auth.revalidate(session)) for login, session in SESSIONS.items())
        self.ctx["gestor"] = dict(self.ctx["op.prod"], features=frozenset(["MANAGE_SCRIPTS"]))
        self.base = _tree()
        self.addCleanup(_remove, self.base)
        self.svc = self._service(self.ENV)
        self.aud_base = max([a["id"] for a in self.audit.list(page=1, size=1000)["itens"]] or [0])

    def _service(self, env):
        return AdminScriptsService(self.catalog, repo_factory.get("schedules"), env, self.log, lambda: NOW)

    def _p(self, name):
        return os.path.join(self.base, name)

    def _audits(self, action):
        return [a for a in self.audit.list(filters={"action": action}, page=1, size=100)["itens"]
                if a["entity"] == "tbsss_scripts" and a["id"] > self.aud_base]

    def _insert(self, svc=None, **changes):
        date = {"name": "Novo script", "interpreter": "PYTHON3", "path_file": self._p("novo.py"),
                 "param_type": "POSITIONAL", "max_parallel_env": "2", "timeout_s": ""}
        date.update(changes)
        return (svc or self.svc).save(self.ctx["admin"], IP, None, date)

    def _edit(self, sid, **changes):
        f = self.svc.form(self.ctx["admin"], str(sid))
        date = dict((c, "" if f[c] is None else str(f[c])) for c in scr_mod.EDITABLE_FIELDS)
        date["version"] = f["version"]
        date.update(changes)
        return self.svc.save(self.ctx["admin"], IP, str(sid), date)

    def _links_json(self, sid):
        screen = self.svc.parameters(self.ctx["admin"], str(sid))
        return screen, [{"parameter_id": v["id"], "required": v["required"],
                       "default_value_override": v["default_value_override"], "manter_sigiloso": v["sensitive"]}
                      for v in screen["vinculos"]]


@_SKIP_ROOT
class TestRegistration(_Base):

    def test_inclusao_ok_e_auditoria(self):
        sid, errors, warning = self._insert()
        self.assertEqual((errors, warning), ({}, None))
        s = self.catalog.scripts_get(sid)
        self.assertEqual((s["interpreter"], s["path_file"], s["max_parallel_env"], s["timeout_s"]),
                         ("PYTHON3", self._p("novo.py"), 2, None))
        self.assertNotIn("pasta_base", s)
        self.assertIn("path_file: %s" % self._p("novo.py"), self._audits("CREATE")[0]["detail"])

    def test_interpretador_fora_da_allowlist(self):
        for cmd in ("/bin/ls", "/usr/bin/python3", "PYTHON3 -c", "python3", "CMD", "POWERSHELL", "", None):
            _sid, errors, _ = self._insert(interpreter=cmd)
            self.assertEqual(errors.get("interpreter"), scr_mod.PATH_MESSAGES[Code.INTERPRETER_NOT_ALLOWED], cmd)

    def test_path_file_invalidos(self):
        # CR-005 (README §8.5): caminho absoluto, normalizado e fora das pastas do sistema; vale em qualquer sss_env.
        cases = (("novo.py", Code.RELATIVE_PATH), ("/etc/passwd", Code.SYSTEM_DIR),
                 ("/usr/local/bin/x.py", Code.SYSTEM_DIR), ("/etc/nao_existe.py", Code.SYSTEM_DIR),
                 (self.base + "/../x.py", Code.HAS_DOTS), (self.base + "//novo.py", Code.PATH_NOT_NORMALIZED),
                 ("/opt\\x.py", Code.INVALID_SEPARATOR))
        for env in ("DEV", "HML"):
            svc = self._service(env)
            for path, code in cases:
                _sid, errors, _ = self._insert(svc=svc, path_file=path)
                self.assertEqual(errors.get("path_file"), scr_mod.PATH_MESSAGES[code], (env, path))
        _sid, errors, _ = self._insert(path_file="/opt/" + "a" * 500)
        self.assertEqual(errors.get("path_file"), u"Use no máximo 500 caracteres.")

    def test_symlink_para_pasta_do_sistema(self):
        os.chmod(self.base, stat.S_IRWXU)
        os.symlink("/etc/hostname", self._p("fuga.py"))
        os.chmod(self.base, 0o555)
        _sid, errors, _ = self._insert(path_file=self._p("fuga.py"))
        self.assertEqual(errors, {"path_file": scr_mod.PATH_MESSAGES[Code.SYSTEM_DIR]})

    def test_arquivo_nao_e_conferido_no_cadastro(self):
        # CR-011 (S1): ausente, gravavel ou pasta neste servidor nao importam aqui; o agente confere ao executar.
        for env in ("DEV", "HML", "PROD"):
            for i, path in enumerate(("/opt/automacoes/scripts/nao_existe.py", self._p("gravavel.py"), self._p("sub"))):
                sid, errors, warning = self._insert(svc=self._service(env), name="Sem conferencia %s %d" % (env, i),
                                                  path_file=path)
                self.assertEqual((errors, warning), ({}, None), (env, path))
                self.assertIsNotNone(sid)

    def test_campos_numericos_e_nome(self):
        for value in ("0", "1000", "x", ""):
            _sid, errors, _ = self._insert(max_parallel_env=value)
            self.assertEqual(errors.get("max_parallel_env"), scr_mod.MSG_PARALLEL, value)
        _sid, errors, _ = self._insert(timeout_s="0")
        self.assertEqual(errors.get("timeout_s"), scr_mod.MSG_TIMEOUT)
        _sid, errors, _ = self._insert(name="carga_diaria")
        self.assertEqual(errors, {"name": scr_mod.MSG_NAME_DUPLICATE})
        _sid, errors, _ = self._insert(name="nome\x07estranho")
        self.assertEqual(errors, {"name": scr_mod.MSG_CONTROL_CHARS})
        # Nome unico diferencia maiusculas (README §8.5), como a UK no Oracle.
        _sid, errors, _a = self._insert(name="CARGA_DIARIA")
        self.assertNotIn("name", errors)

    def test_nome_reservado_app(self):
        # CR-005 D7: a pasta de log do script nao pode ser 'app'.
        for name in ("app", "APP", "App.", "_app_", u"Áṕp"):
            _sid, errors, _ = self._insert(name=name)
            self.assertEqual(errors.get("name"), scr_mod.MSG_NAME_RESERVED, name)
        for name in ("app2", "minha app", "aplicacao"):
            _sid, errors, _ = self._insert(name=name)
            self.assertNotIn("name", errors, name)

    def test_edicao_e_reativacao_sem_conferir_o_arquivo(self):
        # CR-011 (S1): o estado do arquivo neste servidor nao impede editar, desativar nem reativar.
        svc = self._service("HML")
        sid = self.catalog.scripts_insert({"name": "Gravavel", "interpreter": "PYTHON3",
                                             "path_file": self._p("gravavel.py"), "param_type": "POSITIONAL"}, actor="teste")["id"]
        f = svc.form(self.ctx["admin"], str(sid))
        date = dict((c, "" if f[c] is None else str(f[c])) for c in scr_mod.EDITABLE_FIELDS)
        _sid, errors, _a = svc.save(self.ctx["admin"], IP, str(sid), dict(date, version=f["version"], description="Nova"))
        self.assertEqual(errors, {})
        _sid, errors, _a = svc.save(self.ctx["admin"], IP, str(sid),
                                     dict(date, version=svc.form(self.ctx["admin"], str(sid))["version"],
                                          interpreter="BASH"))
        self.assertEqual(errors, {})
        svc.toggle_active(self.ctx["admin"], IP, str(sid), svc.form(self.ctx["admin"], str(sid))["version"])
        self.assertEqual(self.catalog.scripts_get(sid)["active"], "N")
        svc.toggle_active(self.ctx["admin"], IP, str(sid), svc.form(self.ctx["admin"], str(sid))["version"])
        self.assertEqual(self.catalog.scripts_get(sid)["active"], "Y")
        # Reativar ainda confere o formato e as pastas do sistema.
        self.catalog.scripts_update(sid, {"path_file": "/etc/sumiu.py", "active": "N"}, actor="teste")
        with self.assertRaises(OperationDenied):
            svc.toggle_active(self.ctx["admin"], IP, str(sid), svc.form(self.ctx["admin"], str(sid))["version"])

    def test_troca_de_tipo_param_revalida_vinculos(self):
        _sid, errors, _ = self._edit(S_CARGA, param_type="NONE")
        self.assertEqual(errors, {"param_type": scr_mod.MSG_NONE_LINKED})
        # Script SEQUENCIAL com parametro sem flag nao pode virar NOMEADO.
        pid = self.catalog.parameters_insert({"code": "sem_flag", "label": "Sem flag", "component_type": "TEXT"}, actor="teste")["id"]
        sid, _e, _a = self._insert()
        self.catalog.script_params_save(sid, [{"parameter_id": pid, "sort_order": 1, "required": "N"}], actor="teste")
        _sid, errors, _ = self._edit(sid, param_type="NAMED")
        self.assertIn("sem_flag", errors["param_type"])
        with self.assertRaises(RepoViolation) as cm:
            self.catalog.scripts_update(sid, {"param_type": "NAMED"}, actor="teste")
        self.assertEqual(cm.exception.constraint, "sss_scr_nomeado_sem_flag")

    def test_desativacao_com_agendamentos_e_conflito(self):
        f = self.svc.form(self.ctx["admin"], str(S_CARGA))
        self.assertEqual(f["agendamentos_ativos"], 2)
        self.assertEqual(self.svc.toggle_active(self.ctx["admin"], IP, str(S_CARGA), f["version"])["active"], "N")
        self.assertIn("agendamentos ativos afetados: 2", self._audits("DEACTIVATE")[0]["detail"])
        with self.assertRaises(RepoConflict):
            self.svc.toggle_active(self.ctx["admin"], IP, str(S_CARGA), f["version"])

    def test_formulario_sem_pastas_base(self):
        f = self.svc.form(self.ctx["admin"])
        for key in ("pasta_base", "pastas", "base_exibicao"):
            self.assertNotIn(key, f)
        self.assertEqual(self.svc.form(self.ctx["gestor"], str(S_CARGA))["path_file"],
                         "/opt/automacoes/scripts/carga_diaria.py")


@_SKIP_ROOT
class TestHomologation(_Base):

    def test_homologacao_com_auditoria_e_inativo(self):
        screen = self.svc.homologation(self.ctx["admin"], str(S_CARGA))
        names = [a["name"] for a in screen["environments"]]
        self.assertNotIn("DESENV", names)
        diff, errors = self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA), [str(AMB_PROD)], screen["version"])
        self.assertEqual(errors, {})
        self.assertIn("-HOMOLOGACAO", diff)
        self.assertEqual(self.catalog.homologation_get(S_CARGA), [AMB_PROD])
        self.assertIn(u"homologação:", self._audits("UPDATE")[0]["detail"])
        screen = self.svc.homologation(self.ctx["admin"], str(S_CARGA))
        _diff, errors = self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA),
                                                   [str(AMB_PROD), str(AMB_DESENV)], screen["version"])
        self.assertEqual(errors, {GENERAL_FIELD: scr_mod.MSG_HOMOLOG_INACTIVE})

    def test_homologacao_inativa_pode_sair_e_nao_volta(self):
        # CR-003 D9: inativo ja homologado pode ser removido; nunca readicionado.
        self.catalog.homologation_save(S_CARGA, [AMB_PROD, AMB_DESENV], actor="teste")
        screen = self.svc.homologation(self.ctx["admin"], str(S_CARGA))
        dev = [a for a in screen["environments"] if a["name"] == "DESENV"][0]
        self.assertTrue(dev["marcado"] and dev["inativo"])
        diff, _ = self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA),
                                              [str(AMB_PROD), str(AMB_HML), str(AMB_DESENV)], screen["version"])
        self.assertEqual(diff, "+HOMOLOGACAO")
        self.assertEqual(self.catalog.homologation_get(S_CARGA), [AMB_PROD, AMB_HML, AMB_DESENV])
        screen = self.svc.homologation(self.ctx["admin"], str(S_CARGA))
        diff, _ = self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA), [str(AMB_PROD), str(AMB_HML)],
                                              screen["version"])
        self.assertEqual(diff, "-DESENV")
        self.assertEqual(self.catalog.homologation_get(S_CARGA), [AMB_PROD, AMB_HML])
        screen = self.svc.homologation(self.ctx["admin"], str(S_CARGA))
        _d, errors = self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA),
                                                [str(AMB_PROD), str(AMB_HML), str(AMB_DESENV)], screen["version"])
        self.assertIn(GENERAL_FIELD, errors)

    def test_conflito_e_ids_invalidos(self):
        screen = self.svc.homologation(self.ctx["admin"], str(S_CARGA))
        self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA), [str(AMB_PROD)], screen["version"])
        _d, errors = self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA), [], screen["version"])
        self.assertEqual(errors, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})
        screen = self.svc.homologation(self.ctx["admin"], str(S_CARGA))
        for ids in (["x"], ["999"]):
            _d, errors = self.svc.save_homologation(self.ctx["admin"], IP, str(S_CARGA), ids, screen["version"])
            self.assertEqual(errors, {GENERAL_FIELD: scr_mod.MSG_HOMOLOG_INVALID})


@_SKIP_ROOT
class TestLinks(_Base):

    def test_sub_sigiloso_mantido_e_revalidado_e_pode_ser_removido(self):
        # CR-003 P6 (README §6.5).
        screen, items = self._links_json(S_CARGA)
        self.catalog.parameters_update(6, {"validation_regex": "^x$"}, actor="teste")  # documento_cliente: o sub gravado deixa de valer
        _d, errors = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), json.dumps(items), screen["version"])
        self.assertEqual(errors, {"vinculo_6": scr_mod.MSG_SENSITIVE_INVALID})
        for item in items:
            if item["parameter_id"] == 6:
                item["manter_sigiloso"] = False  # "Remover valor"
        _d, errors = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), json.dumps(items), screen["version"])
        self.assertEqual(errors, {})
        sub = [v for v in self.catalog.script_params_get(S_CARGA) if v["parameter_id"] == 6][0]["default_value_override"]
        self.assertIsNone(sub)

    def test_detalhe_dos_vinculos_passa_pelo_masking(self):
        import masking
        masking.MASKER.register("SEGREDO-DE-INFRA-9")
        screen, items = self._links_json(S_CARGA)
        for item in items:
            if item["parameter_id"] == 1:
                item["default_value_override"] = None
        items.append({"parameter_id": 10, "required": False, "default_value_override": "SEGREDO-DE-INFRA-9"})
        _d, errors = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), json.dumps(items), screen["version"])
        self.assertEqual(errors, {})
        self.assertNotIn("SEGREDO-DE-INFRA-9", self._audits("UPDATE")[0]["detail"])

    def test_versao_dos_vinculos_nao_deriva_do_sub_sensivel(self):
        # CR-003 P1: o sub sensivel entra na versao pelo marcador, nunca pelo valor.
        v1 = self.svc.parameters(self.ctx["admin"], str(S_CARGA))["version"]
        link = self.catalog.script_params_get(S_CARGA)
        read = [dict((k, v[k]) for k in ("parameter_id", "sort_order", "required", "default_value_override")) for v in link]
        for v in read:
            if v["default_value_override"] == "00011122233":
                v["default_value_override"] = "outro-segredo-456"
        self.catalog.script_params_save(S_CARGA, read, actor="teste")
        screen = self.svc.parameters(self.ctx["admin"], str(S_CARGA))
        self.assertEqual(screen["version"], v1)
        self.assertNotEqual(screen["version"], scr_mod._hash(scr_mod._read_back(self.catalog.script_params_get(S_CARGA))))
        self.assertNotIn("outro-segredo-456", repr(screen))

    def test_renumeracao_e_reordenacao(self):
        screen, items = self._links_json(S_CARGA)
        items.reverse()
        desc, errors = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), json.dumps(items), screen["version"])
        self.assertEqual(errors, {})
        link = self.catalog.script_params_get(S_CARGA)
        self.assertEqual([v["sort_order"] for v in link], [1, 2, 3, 4, 5])
        self.assertEqual(link[0]["code"], "documento_cliente")
        # Sub sigiloso preservado ("manter") e mascarado na auditoria.
        self.assertEqual(link[0]["default_value_override"], "00011122233")
        detail = self._audits("UPDATE")[0]["detail"]
        self.assertNotIn("00011122233", detail)
        self.assertIn("documento_cliente=****", detail)
        self.assertNotIn("00011122233", repr(self.svc.parameters(self.ctx["admin"], str(S_CARGA))))

    def test_vinculo_duplicado_inexistente_e_json_invalido(self):
        screen, items = self._links_json(S_CARGA)
        for body in (json.dumps(items + [items[0]]), json.dumps(items + [{"parameter_id": 999}]), "{", '{"a": 1}'):
            _d, errors = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), body, screen["version"])
            self.assertIn(GENERAL_FIELD, errors, body[:30])

    def test_nomeado_com_parametro_sem_flag(self):
        pid = self.catalog.parameters_insert({"code": "sem_flag", "label": "Sem flag", "component_type": "TEXT"}, actor="teste")["id"]
        screen, items = self._links_json(S_CARGA)
        _d, errors = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA),
                                               json.dumps(items + [{"parameter_id": pid}]), screen["version"])
        self.assertIn("sem_flag", errors[GENERAL_FIELD])
        with self.assertRaises(RepoViolation):
            self.catalog.script_params_save(S_CARGA, [{"parameter_id": pid, "sort_order": 1, "required": "N"}], actor="teste")

    def test_nenhum_com_vinculo(self):
        screen = self.svc.parameters(self.ctx["admin"], str(S_CLEANUP))
        _d, errors = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CLEANUP),
                                               json.dumps([{"parameter_id": 1}]), screen["version"])
        self.assertEqual(errors, {GENERAL_FIELD: scr_mod.MSG_LINK_NONE})

    def test_valor_padrao_sub_validado_e_inativo_rejeitado(self):
        screen, items = self._links_json(S_CARGA)
        items[0]["default_value_override"] = "31/12/2026"  # data_ref e DATE
        _d, errors = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), json.dumps(items), screen["version"])
        self.assertIn("vinculo_1", errors)
        pid = self.catalog.parameters_insert({"code": "inativo_x", "label": "X", "component_type": "TEXT",
                                                "param_flag": "--x", "active": "N"}, actor="teste")["id"]
        screen, items = self._links_json(S_CARGA)
        _d, errors = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA),
                                               json.dumps(items + [{"parameter_id": pid}]), screen["version"])
        self.assertIn("inativo", errors[GENERAL_FIELD])

    def test_conflito_de_vinculos(self):
        screen, items = self._links_json(S_CARGA)
        self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), json.dumps(items[:-1]), screen["version"])
        _d, errors = self.svc.save_parameters(self.ctx["admin"], IP, str(S_CARGA), json.dumps(items), screen["version"])
        self.assertEqual(errors, {GENERAL_FIELD: admin_crud.MSG_CONFLICT})


@_SKIP_ROOT
class TestPreview(_Base):

    def test_previa_do_seed_gera_argv_esperado_e_mascara_sensivel(self):
        r = self.svc.preview(self.ctx["admin"], str(S_CARGA))
        real = "/opt/automacoes/scripts/carga_diaria.py"
        self.assertEqual((r["erros"], r["aviso"]), ({}, None))
        self.assertEqual(r["argv"], ["PYTHON3", "-I", real, "--data-ref", "2026-10-14", "-n", "5000",
                                     "--modo", "REAL", "--verbose", "--documento", "****"])

    def test_previa_no_cadastro_mostra_o_caminho_e_reflete_edicao(self):
        # CR-005 R-f: no cadastro (MANAGE_SCRIPTS) o caminho aparece inteiro, porque e o que o usuario cadastra.
        _screen, items = self._links_json(S_CARGA)
        r = self.svc.preview(self.ctx["gestor"], str(S_CARGA), json.dumps(items[:1]))
        self.assertEqual(r["argv"], ["PYTHON3", "-I", "/opt/automacoes/scripts/carga_diaria.py",
                                     "--data-ref", "2026-10-14"])

    def test_acesso_negado_e_nao_encontrado(self):
        for call in (lambda c: self.svc.list(c, {}, 1, 20), lambda c: self.svc.homologation(c, "1"),
                        lambda c: self.svc.parameters(c, "1"), lambda c: self.svc.preview(c, "1")):
            with self.assertRaises(AccessDenied):
                call(self.ctx["op.prod"])
        with self.assertRaises(RepoNotFound):
            self.svc.form(self.ctx["admin"], "999")

    def test_lista_com_homologados_e_parametros(self):
        page = self.svc.list(self.ctx["admin"], {"interpreter": "PYTHON3"}, 1, 20)
        load = [s for s in page["itens"] if s["name"] == "carga_diaria"][0]
        self.assertEqual(load["qtd_parametros"], 5)
        self.assertIn("PRODUCAO", load["ambientes_homologados"])
        self.assertTrue(all(s["interpreter"] == "PYTHON3" for s in page["itens"]))
        self.assertEqual(scr_mod.normalize_filters({"interpreter": "/bin/ls", "active": "Y"}), {"active": "Y"})
        self.assertEqual(scr_mod.normalize_filters({"interpreter": "POWERSHELL"}), {})


@_SKIP_ROOT
class TestNoHashAndLink(_Base):
    """CR-011: o cadastro nao calcula nem registra hash do arquivo, e o caminho pode ter link simbolico."""

    def test_inclusao_e_edicao_nao_registram_hash(self):
        sid, errors, _a = self._insert(path_file=self._p("novo.py"), sha256_informado="0" * 64,
                                       registrar_conteudo_atual="1")
        self.assertEqual(errors, {})
        self.assertIsNone(self.catalog.scripts_get(sid).get("sha256_homologado"))
        self.assertEqual(self._edit(sid, description="nova", registrar_conteudo_atual="1")[1], {})
        self.assertIsNone(self.catalog.scripts_get(sid).get("sha256_homologado"))
        self.assertNotIn("sha256_homologado", self.svc.form(self.ctx["admin"], str(sid)))
        for aud in self._audits("CREATE") + self._audits("UPDATE"):
            self.assertNotIn("sha256", aud["detail"])

    def test_caminho_com_link_simbolico_e_aceito(self):
        os.chmod(self.base, 0o755)
        link = self._p("atalho.py")
        os.symlink(self._p("novo.py"), link)
        os.chmod(self.base, 0o555)
        sid, errors, warning = self._insert(path_file=link)
        self.assertEqual((errors, warning), ({}, None))
        self.assertEqual(self.catalog.scripts_get(sid)["path_file"], link, "fica o caminho cadastrado")

    def test_link_para_pasta_do_sistema_e_recusado(self):
        os.chmod(self.base, 0o755)
        link = self._p("atalho_sistema.py")
        os.symlink("/etc/hostname", link)
        os.chmod(self.base, 0o555)
        _sid, errors, _a = self._insert(path_file=link)
        self.assertEqual(errors, {"path_file": scr_mod.PATH_MESSAGES[path_guard.Code.SYSTEM_DIR]})


if __name__ == "__main__":
    unittest.main()
