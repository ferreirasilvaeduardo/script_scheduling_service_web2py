# -*- coding: utf-8 -*-
"""Testes de params_compiler.py (F3.1): README §6 e §8.4 passo 1, AGENTS §7.4."""
import _testenv  # noqa: F401

import collections
import datetime
import json
import re
import os
import shutil
import tempfile
import unittest
from unittest import mock

import params_compiler as pc
import path_guard
from params_compiler import ParamError, SnapshotError

# UID fictício do agente: o dono dos arquivos de teste é o usuário do teste (CR-007, R-15).
FAKE_AGENT = 2 ** 31 - 3

NOW = datetime.datetime(2026, 10, 13, 10, 47, 0, 123456)
AgentCfg = collections.namedtuple("CfgAgente", ["interpreters"])
KEYS_6_5 = {"version", "script_id", "script_name", "interpreter", "path_file", "param_type", "args",
              "answers", "sensitive", "compiled_at"}
EXE_PY = "/usr/bin/python3"


def prm(code, kind="TEXT", order=1, required_flag="N", flag=None, options=None, default_value=None,
        default_override=None, regex=None, sensitive_flag="N"):
    return {"code": code, "label": code.upper(), "component_type": kind, "sort_order": order,
            "required": required_flag, "param_flag": flag, "options_json": options,
            "default_value": default_value, "default_value_override": default_override, "validation_regex": regex,
            "sensitive": sensitive_flag}


def script(param_type="NAMED", interpreter="PYTHON3"):
    return {"id": 12, "name": "carga_faturas", "interpreter": interpreter,
            "path_file": REAL, "param_type": param_type}


REAL = "/opt/automacoes/scripts/faturamento/carga_faturas.py"


class TestValidateValue(unittest.TestCase):

    def _error(self, p, value):
        with self.assertRaises(ParamError) as ctx:
            pc.validate_value(p, value)
        self.assertEqual(ctx.exception.param_code, p["code"])
        return ctx.exception

    def test_strip(self):
        self.assertEqual(pc.validate_value(prm("t"), "  abc  "), "abc")

    def test_nul_e_controle(self):
        for value in ("a\x00b", "a\x1bb", "a\x7fb", "a\nb", "a\tb", "\x01"):
            with self.subTest(valor=repr(value)):
                self._error(prm("t"), value)

    def test_strip_antes_de_controle_e_tamanho(self):
        # CR-003 P5 (README §6.2): strip primeiro; controle so nas pontas nao rejeita.
        self.assertEqual(pc.validate_value(prm("t"), "\tabc\n"), "abc")
        self.assertEqual(len(pc.validate_value(prm("t"), "x" * 500 + "  ")), 500)
        self._error(prm("t"), "\ta\tb\n")

    def test_tamanho(self):
        self.assertEqual(len(pc.validate_value(prm("t"), "x" * 500)), 500)
        self._error(prm("t"), "x" * 501)

    def test_tipo_nao_str(self):
        self._error(prm("t"), 10)
        self._error(prm("n", "NUMBER"), 10)

    def test_text_regex_fullmatch(self):
        p = prm("f", regex=r"[0-9]{4}")
        self.assertEqual(pc.validate_value(p, "0001"), "0001")
        # search casaria; fullmatch nao.
        self._error(p, "00012")
        self._error(p, "x0001")

    def test_text_regex_mal_configurada(self):
        self._error(prm("f", regex=r"([0-9]"), "1")

    def test_number(self):
        p = prm("n", "NUMBER")
        for ok in ("0", "-5", "123456789012345678", "1.123456", "-0.5"):
            self.assertEqual(pc.validate_value(p, ok), ok)
        for bad in ("1e3", "1.1234567", "1234567890123456789", "+1", "1.", ".5", "abc", "1,5"):
            with self.subTest(valor=bad):
                self._error(p, bad)

    def test_date(self):
        p = prm("d", "DATE")
        self.assertEqual(pc.validate_value(p, "2026-10-13"), "2026-10-13")
        self.assertEqual(pc.validate_value(p, "2026-1-5"), "2026-01-05")
        for bad in ("2026-02-30", "13/10/2026", "2026-10-13 10:00", "x"):
            with self.subTest(valor=bad):
                self._error(p, bad)

    def test_select(self):
        p = prm("s", "SELECT", options='{"CSV": "Arquivo CSV", "JSON": "Arquivo JSON"}')
        self.assertEqual(pc.validate_value(p, "CSV"), "CSV")
        self._error(p, "XML")
        self._error(p, "Arquivo CSV")
        self._error(p, "csv")

    def test_select_opcoes_json_invalido(self):
        for options in ("{nao json", '["CSV"]', "{}", None, '"CSV"'):
            with self.subTest(opcoes=options):
                e = self._error(prm("s", "SELECT", options=options), "CSV")
                self.assertIn("administrador", e.message)

    def test_checkbox(self):
        p = prm("c", "CHECKBOX")
        for value, expected in (("true", True), ("TRUE", True), ("1", True), ("False", False),
                                ("0", False), (True, True), (False, False)):
            self.assertIs(pc.validate_value(p, value), expected)
        for bad in ("sim", "yes", "2", 1):
            with self.subTest(valor=bad):
                self._error(p, bad)

    def test_tipo_componente_desconhecido(self):
        self._error(prm("x", "FILE"), "a")

    def test_sensivel_nao_ecoa_valor(self):
        secret = "Segr3d0-Muito-Secreto"
        for p in (prm("k", regex=r"[a-z]+", sensitive_flag="Y"), prm("k", "NUMBER", sensitive_flag="Y"),
                  prm("k", "SELECT", options='{"A":"a"}', sensitive_flag="Y")):
            e = self._error(p, secret)
            self.assertNotIn(secret, e.message)
            self.assertNotIn(secret, str(e))


class TestRegistrationRegex(unittest.TestCase):

    def test_validas(self):
        for default in (r"^[0-9]{4}$", r"[A-Z]{2}-\d+", r"(abc)?x+"):
            pc.validate_registry_regex(default)

    def test_nao_compila(self):
        for default in (r"([0-9]", r"*a", None):
            with self.subTest(padrao=default):
                with self.assertRaises(ParamError):
                    pc.validate_registry_regex(default)

    def test_redos_rejeitada(self):
        for default in (r"(a+)+", r"(a*)*", r"(\w+){2}", r"^(x+y*)+$", r"(.*a)+"):
            with self.subTest(padrao=default):
                with self.assertRaises(ParamError) as ctx:
                    pc.validate_registry_regex(default)
                self.assertIn("README §6.2", ctx.exception.message)

    def test_subconjunto_seguro_cr007(self):
        """CR-007, D5: exemplos do README §6.2 e limite de tempo de fullmatch das regex aceitas."""
        import time
        accepted = (r"^[A-Z]{2}\d{6}$", r"^\d{3}\.\d{3}\.\d{3}-\d{2}$", r"^(PF|PJ)$", r"^\d+(\.\d{1,2})?$",
                   r"a+?b", r"(?P<n>a)b", r"[)a]+b", "a?" * 6 + "a" * 6, r"^(a|aa|aaa)?(a|aa)?\w+\w*!$")
        refused = (r"(a|a)*b", r"^(\w|\d)+$", r"(a+)+", r"a{2}{3}", r"\d+\d+\d+x", r"(a)\1", r"(?=a)a",
                     r"(?<!a)b", r"(?P<n>a)(?P=n)", r"(\d{2}){3}", r"(?:\w|\d)+x", r"([)a]+)+b",
                     "a?" * 7 + "a" * 7, r"(?(1)a|b)", "x" * 151)
        for default in accepted:
            with self.subTest(aceita=default):
                pc.validate_registry_regex(default)
                for value in ("a" * 500, "a" * 499 + "!"):
                    start = time.time()
                    re.fullmatch(default, value)
                    self.assertLess(time.time() - start, 0.5)
        for default in refused:
            with self.subTest(recusada=default):
                with self.assertRaises(ParamError):
                    pc.validate_registry_regex(default)

    def test_valor_sensivel_minimo_de_4(self):
        prm_s = {"code": "doc", "label": "Doc", "component_type": "TEXT", "sensitive": "Y"}
        with self.assertRaises(ParamError) as ctx:
            pc.validate_value(prm_s, "abc")
        self.assertIn("pelo menos 4", ctx.exception.message)
        self.assertEqual(pc.validate_value(prm_s, "abcd"), "abcd")
        self.assertEqual(pc.validate_value(prm_s, "  "), "")
        self.assertEqual(pc.validate_value(dict(prm_s, sensitive="N"), "abc"), "abc")


class TestRegistrationOptionsAndFlag(unittest.TestCase):

    def test_opcoes_validas_preservam_ordem_e_normalizam(self):
        self.assertEqual(pc.validate_registry_options(' { "Z": " Último ", "A": "Primeiro" } '),
                         u'{"Z":"Último","A":"Primeiro"}')

    def test_opcoes_invalidas(self):
        for text in (None, "", "   ", "{", "[]", '"x"', "{}", '{"a": 1}', '{"": "x"}', '{"a": " "}',
                      '{"a": "x", "a": "y"}', '{"a": "x", " a": "y"}', '{"a\\u0001": "x"}',
                      '{"%s": "x"}' % ("k" * 101)):
            with self.assertRaises(pc.ParamError, msg=repr(text)) as cm:
                pc.validate_registry_options(text)
            self.assertEqual(cm.exception.param_code, "options_json")

    def test_opcoes_acima_de_500_caracteres(self):
        large = "{" + ",".join('"k%02d": "%s"' % (i, "r" * 20) for i in range(25)) + "}"
        with self.assertRaises(pc.ParamError):
            pc.validate_registry_options(large)

    def test_flag(self):
        for ok in ("--data-ref", "-n", "--a_b", "-X1"):
            pc.validate_flag(ok)
        for bad in ("data", "---x", "--", "-", "--x y", "--" + "a" * 29, "-_x", None):
            with self.assertRaises(pc.ParamError, msg=repr(bad)):
                pc.validate_flag(bad)


class TestPrecedence(unittest.TestCase):

    def test_ordem_de_precedencia(self):
        v = [prm("a", order=1, default_override="sub", default_value="glob")]
        self.assertEqual(pc.resolve_answers(v, {"a": "resp"})["a"], "resp")
        self.assertEqual(pc.resolve_answers(v, {})["a"], "sub")
        self.assertEqual(pc.resolve_answers(v, {"a": "   "})["a"], "sub")
        v = [prm("a", order=1, default_value="glob")]
        self.assertEqual(pc.resolve_answers(v, None)["a"], "glob")
        v = [prm("a", order=1)]
        self.assertIsNone(pc.resolve_answers(v, {})["a"])

    def test_padrao_tambem_validado(self):
        v = [prm("n", "NUMBER", order=1, default_override="abc", default_value="10")]
        with self.assertRaises(ParamError) as ctx:
            pc.resolve_answers(v, {})
        self.assertEqual(ctx.exception.param_code, "n")
        v = [prm("n", "NUMBER", order=1, default_value="abc")]
        with self.assertRaises(ParamError):
            pc.resolve_answers(v, {})

    def test_resposta_invalida_nao_cai_no_padrao(self):
        v = [prm("n", "NUMBER", order=1, default_override="10")]
        with self.assertRaises(ParamError):
            pc.resolve_answers(v, {"n": "abc"})

    def test_obrigatorio_ausente(self):
        v = [prm("a", order=1, required_flag="Y")]
        with self.assertRaises(ParamError) as ctx:
            pc.resolve_answers(v, {"a": ""})
        self.assertEqual(ctx.exception.param_code, "a")
        self.assertIn("obrigatório", ctx.exception.message)

    def test_checkbox_falso_obrigatorio_e_valor(self):
        v = [prm("c", "CHECKBOX", order=1, required_flag="Y")]
        self.assertIs(pc.resolve_answers(v, {"c": "false"})["c"], False)

    def test_ordem_do_resultado(self):
        v = [prm("z", order=3), prm("a", order=1), prm("m", order=2)]
        self.assertEqual(list(pc.resolve_answers(v, {}).keys()), ["a", "m", "z"])


class TestBuildArgs(unittest.TestCase):

    def _args(self, param_type, links, answers):
        return pc.build_args(param_type, links, pc.resolve_answers(links, answers))

    def _error(self, param_type, links, answers):
        with self.assertRaises(ParamError) as ctx:
            self._args(param_type, links, answers)
        return ctx.exception

    def test_nomeado_flags(self):
        v = [prm("d", "DATE", order=2, flag="--data"), prm("n", "NUMBER", order=1, flag="-n")]
        self.assertEqual(self._args("NAMED", v, {"d": "2026-10-13", "n": "5"}),
                         ["-n", "5", "--data", "2026-10-13"])

    def test_nomeado_longa_valor_com_hifen(self):
        v = [prm("t", order=1, flag="--taxa"), prm("x", order=2, flag="--texto")]
        self.assertEqual(self._args("NAMED", v, {"t": "-1.5", "x": "--rm"}), ["--taxa=-1.5", "--texto=--rm"])

    def test_nomeado_curta_valor_com_hifen_rejeitado(self):
        for kind, value in (("NUMBER", "-5"), ("TEXT", "-rf")):
            with self.subTest(tipo=kind):
                e = self._error("NAMED", [prm("n", kind, order=1, flag="-n")], {"n": value})
                self.assertEqual(e.param_code, "n")
                self.assertNotIn(value, e.message)

    def test_nomeado_checkbox(self):
        v = [prm("v", "CHECKBOX", order=1, flag="--verbose"), prm("m", "CHECKBOX", order=2, flag="-m")]
        self.assertEqual(self._args("NAMED", v, {"v": "true", "m": "false"}), ["--verbose"])
        self.assertEqual(self._args("NAMED", v, {"v": "0", "m": "1"}), ["-m"])
        self.assertEqual(self._args("NAMED", v, {}), [])

    def test_nomeado_opcional_vazio_omitido(self):
        v = [prm("a", order=1, flag="--a"), prm("b", order=2, flag="--b")]
        self.assertEqual(self._args("NAMED", v, {"b": "x"}), ["--b", "x"])

    def test_nomeado_sem_flag(self):
        e = self._error("NAMED", [prm("a", order=1)], {"a": "x"})
        self.assertEqual(e.param_code, "a")

    def test_sequencial(self):
        v = [prm("c", "CHECKBOX", order=4), prm("a", order=1, flag="--ignorada"),
             prm("b", order=2), prm("n", "NUMBER", order=3), prm("d", "CHECKBOX", order=5)]
        self.assertEqual(self._args("POSITIONAL", v, {"a": "x", "n": "-7", "c": "true", "d": "false"}),
                         ["x", "", "-7", "1", "0"])

    def test_sequencial_opcional_vazio_intermediario(self):
        v = [prm("a", order=1), prm("b", order=2), prm("c", "CHECKBOX", order=3), prm("d", order=4)]
        self.assertEqual(self._args("POSITIONAL", v, {"a": "x", "d": "y"}), ["x", "", "", "y"])

    def test_sequencial_hifen_rejeitado_exceto_number(self):
        for kind, value in (("TEXT", "-x"), ("SELECT", "-A")):
            with self.subTest(tipo=kind):
                p = prm("t", kind, order=1, options='{"-A": "a"}')
                e = self._error("POSITIONAL", [p], {"t": value})
                self.assertEqual(e.param_code, "t")
        self.assertEqual(self._args("POSITIONAL", [prm("n", "NUMBER", order=1)], {"n": "-1.5"}), ["-1.5"])

    def test_nenhum(self):
        self.assertEqual(pc.build_args("NONE", [], collections.OrderedDict()), [])
        e = self._error("NONE", [prm("a", order=1)], {"a": "x"})
        self.assertIsNone(e.param_code)

    def test_tipo_param_desconhecido(self):
        e = self._error("OUTRO", [prm("a", order=1)], {"a": "x"})
        self.assertIsNone(e.param_code)


class TestBuildAgentArgv(unittest.TestCase):

    def test_interpretadores(self):
        self.assertEqual(pc.build_agent_argv("PYTHON3", EXE_PY, "/b/s.py", ["a"]), [EXE_PY, "-I", "/b/s.py", "a"])
        self.assertEqual(pc.build_agent_argv("BASH", "/bin/bash", "/b/s.sh", ["a"]), ["/bin/bash", "/b/s.sh", "a"])
        self.assertEqual(pc.build_agent_argv("SH", "/bin/sh", "/b/s.sh", []), ["/bin/sh", "/b/s.sh"])

    def test_fora_da_allowlist(self):
        import path_guard
        for interp in ("/usr/bin/python3", "PERL", "CMD", "cmd.exe", ""):
            with self.assertRaises(path_guard.PathGuardError, msg=interp):
                pc.build_agent_argv(interp, "/x", "/b/s", [])


class TestCompileSnapshot(unittest.TestCase):

    def _links(self):
        return [prm("data_ref", "DATE", order=1, required_flag="Y", flag="--data"),
                prm("token", order=2, flag="--token", sensitive_flag="Y"),
                prm("modo", "SELECT", order=3, flag="--modo", options='{"A":"Ação","B":"Bê"}', default_value="A")]

    def test_formato_6_5(self):
        js, resolved, errors = pc.compile_snapshot(script(), self._links()[:1], {"data_ref": "2026-10-13"}, NOW)
        self.assertEqual(errors, {})
        expected = {
            "version": 5, "script_id": 12, "script_name": "carga_faturas", "interpreter": "PYTHON3",
            "path_file": REAL, "param_type": "NAMED",
            "args": ["--data", "2026-10-13"],
            "answers": {"data_ref": "2026-10-13"}, "sensitive": [], "compiled_at": "2026-10-13 10:47:00",
        }
        self.assertEqual(json.loads(js), expected)
        self.assertEqual(js, json.dumps(expected, ensure_ascii=False, sort_keys=True))
        self.assertNotIn("pasta_base", js)

    def test_determinismo(self):
        v = self._links()
        r1 = collections.OrderedDict([("data_ref", "2026-10-13"), ("token", "abc123"), ("modo", "B")])
        r2 = collections.OrderedDict([("modo", "B"), ("token", "abc123"), ("data_ref", "2026-10-13")])
        js1 = pc.compile_snapshot(script(), v, r1, NOW)[0]
        js2 = pc.compile_snapshot(script(), list(reversed(v)), r2, NOW)[0]
        self.assertIsNotNone(js1)
        self.assertEqual(js1, js2)
        snap = json.loads(js1)
        self.assertEqual(snap["args"], ["--data", "2026-10-13", "--token", "abc123", "--modo", "B"])
        self.assertEqual(snap["sensitive"], ["token"])

    def test_utf8_sem_escape(self):
        js = pc.compile_snapshot(script(), [prm("t", order=1, flag="--t")], {"t": "ação"}, NOW)[0]
        self.assertIn("ação", js)

    def test_respostas_tipadas(self):
        v = [prm("c", "CHECKBOX", order=1, flag="--c"), prm("o", order=2, flag="--o")]
        snap = json.loads(pc.compile_snapshot(script(), v, {"c": "1"}, NOW)[0])
        self.assertEqual(snap["answers"], {"c": True, "o": None})

    def test_erros_acumulados(self):
        v = self._links() + [prm("n", "NUMBER", order=4, flag="-n")]
        js, resolved, errors = pc.compile_snapshot(script(), v, {"token": "a\x00b", "modo": "Z", "n": "-3"}, NOW)
        self.assertIsNone(js)
        self.assertEqual(list(errors.keys()), ["data_ref", "token", "modo", "n"])
        for msg in errors.values():
            self.assertNotIn("a\x00b", msg)

    def test_erros_estruturais(self):
        js, _, errors = pc.compile_snapshot(script("NONE"), [prm("a", order=1)], {"a": "x"}, NOW)
        self.assertIsNone(js)
        self.assertIn(pc.GENERAL_KEY, errors)
        for interp in ("/usr/bin/python3", "PERL", "CMD"):
            js, _, errors = pc.compile_snapshot(script(interpreter=interp), [], {}, NOW)
            self.assertIsNone(js, interp)
            self.assertIn(pc.GENERAL_KEY, errors)

    def test_nenhum_sem_vinculos(self):
        js = pc.compile_snapshot(script("NONE", "BASH"), [], {}, NOW)[0]
        snap = json.loads(js)
        self.assertEqual((snap["interpreter"], snap["args"]), ("BASH", []))

    def test_argv_para_exibicao(self):
        v = self._links() + [prm("seq", order=4, flag="-s", sensitive_flag="Y")]
        snap = json.loads(pc.compile_snapshot(
            script(), v, {"data_ref": "2026-10-13", "token": "-segredo", "seq": "outro_segredo"}, NOW)[0])
        disp = pc.display_argv(snap)
        # CR-005 D8: caminho completo para todos.
        self.assertEqual(disp, ["PYTHON3", "-I", REAL, "--data", "2026-10-13",
                                "--token=****", "--modo", "A", "-s", "****"])
        self.assertNotIn("segredo", " ".join(disp))
        self.assertIn("-segredo", snap["args"][2])

    def test_argv_para_exibicao_sem_sensiveis(self):
        snap = json.loads(pc.compile_snapshot(script("POSITIONAL", "SH"), [prm("a", order=1)], {"a": "x"}, NOW)[0])
        self.assertEqual(pc.display_argv(snap), ["SH", REAL, "x"])


@unittest.skipIf(os.geteuid() == 0, "root sempre passa em os.access(W_OK)")
class TestValidateSnapshot(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sss_pc_")
        self.base = os.path.join(self.root, "scripts")
        os.makedirs(os.path.join(self.base, "faturamento"))
        self.arq = os.path.join(self.base, "faturamento", "carga_faturas.py")
        with open(self.arq, "w") as f:
            f.write("print(1)\n")
        os.chmod(self.arq, 0o444)
        os.chmod(os.path.join(self.base, "faturamento"), 0o555)
        os.chmod(self.base, 0o555)
        self.cfg = AgentCfg({"PYTHON3": EXE_PY, "SH": "/bin/sh"})
        self.real = os.path.realpath(self.arq)
        v = [prm("data_ref", "DATE", order=1, required_flag="Y", flag="--data")]
        scr = dict(script(), path_file=self.arq)
        self.js = pc.compile_snapshot(scr, v, {"data_ref": "2026-10-13"}, NOW)[0]

    def tearDown(self):
        for root, _, _ in os.walk(self.root):
            os.chmod(root, 0o755)
        shutil.rmtree(self.root)

    def _changed(self, **changes):
        snap = json.loads(self.js)
        snap.update(changes)
        return json.dumps(snap)

    def test_argumento_com_controle_no_snapshot(self):
        # CR-007, R-32: o snapshot vem do banco; NUL ou controle nos args nunca chegam ao argv.
        for bad in ("a\x00b", "linha\nnova"):
            with self.subTest(arg=repr(bad)):
                self.assertEqual(self._reason(self._changed(args=["--data", bad])), "INVALID_ARGS")

    def _reason(self, js, cfg=None):
        with self.assertRaises(SnapshotError) as ctx:
            pc.validate_snapshot(js, cfg or self.cfg)
        return ctx.exception.reason

    def test_ok_monta_argv_com_executavel_e_base_do_agente(self):
        snap, argv, script_real = pc.validate_snapshot(self.js, self.cfg)
        self.assertEqual(argv, [EXE_PY, "-I", self.real, "--data", "2026-10-13"])
        self.assertEqual(script_real, self.real)
        self.assertEqual(snap["interpreter"], "PYTHON3")

    def test_json_e_estrutura(self):
        self.assertEqual(self._reason("{x"), "INVALID_JSON")
        self.assertEqual(self._reason(None), "INVALID_JSON")
        self.assertEqual(self._reason("[]"), "INVALID_STRUCTURE")
        self.assertEqual(self._reason('{"versao": 3}'), "INVALID_STRUCTURE")

    def test_versoes_1_a_3_rejeitadas(self):
        # CR-005: path_file absoluto desde o v4; CR-016c2 (D20): chaves em ingles no v5. v1 a v4 sao recusados.
        for version in (1, 2, 3, 4):
            self.assertEqual(self._reason(self._changed(version=version)), "UNSUPPORTED_VERSION")

    def test_interpretador_fora_da_allowlist_ou_indisponivel_no_agente(self):
        self.assertEqual(self._reason(self._changed(interpreter="/usr/bin/perl")), "INTERPRETER_NOT_ALLOWED")
        self.assertEqual(self._reason(self._changed(interpreter="BASH")), "INTERPRETER_UNAVAILABLE")
        # CR-005: POWERSHELL saiu da allowlist (somente POSIX).
        self.assertEqual(self._reason(self._changed(interpreter="POWERSHELL")), "INTERPRETER_NOT_ALLOWED")

    def test_args_invalidos(self):
        self.assertEqual(self._reason(self._changed(args="--data x")), "INVALID_ARGS")
        self.assertEqual(self._reason(self._changed(args=["--n", 1])), "INVALID_ARGS")

    def test_path_guard_revalidado_no_agente(self):
        self.assertEqual(self._reason(self._changed(path_file="x.py")), "PATH_GUARD_RELATIVE_PATH")
        self.assertEqual(self._reason(self._changed(path_file="/opt/../x.py")), "PATH_GUARD_HAS_DOTS")
        self.assertEqual(self._reason(self._changed(path_file="/etc/passwd")), "PATH_GUARD_SYSTEM_DIR")
        self.assertEqual(self._reason(self._changed(path_file=os.path.join(self.base, "nao_existe.py"))),
                         "PATH_GUARD_NOT_FOUND")
        self.assertEqual(self._reason(self._changed(path_file=os.path.join(self.base, "faturamento"))),
                         "PATH_GUARD_NOT_A_FILE")

    def test_log_dir_e_work_dir_do_agente(self):
        cfg = collections.namedtuple("CfgDirs", ["interpreters", "sss_dirs"])(
            self.cfg.interpreters, (os.path.join(self.base, "faturamento"),))
        self.assertEqual(self._reason(self.js, cfg), "PATH_GUARD_SSS_DIR")


class TestSeedFake(unittest.TestCase):
    """compilar_snapshot com o seed do FAKE (script 1, carga_diaria) gera o formato da §6.5."""

    def setUp(self):
        import repo_factory
        self.repo_factory = repo_factory
        repo_factory.configure({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.catalog = repo_factory.get("catalog")

    def tearDown(self):
        self.repo_factory.configure(None)
        self.repo_factory.reset_singletons()

    def test_carga_diaria(self):
        scr = self.catalog.scripts_get(1)
        links = self.catalog.script_params_get(1)
        js, resolved, errors = pc.compile_snapshot(scr, links, {}, NOW)
        self.assertEqual(errors, {})
        snap = json.loads(js)
        self.assertEqual(set(snap.keys()), KEYS_6_5)
        self.assertEqual(js, json.dumps(snap, ensure_ascii=False, sort_keys=True))
        self.assertEqual(snap["args"], ["--data-ref", "2026-10-14", "-n", "5000", "--modo", "REAL", "--verbose",
                                        "--documento", "00011122233"])
        self.assertEqual(snap["sensitive"], ["documento_cliente"])
        self.assertEqual(snap["answers"]["verbose"], True)
        self.assertNotIn("00011122233", pc.display_argv(snap))

    def test_todos_os_scripts_do_seed_compilam(self):
        for sid in (1, 2, 3, 4, 6):
            with self.subTest(script_id=sid):
                scr = self.catalog.scripts_get(sid)
                links = self.catalog.script_params_get(sid)
                js, _, errors = pc.compile_snapshot(scr, links, {}, NOW)
                self.assertEqual(errors, {})
                self.assertEqual(set(json.loads(js).keys()), KEYS_6_5)

    def test_snapshots_do_seed_sao_v5(self):
        tickets = self.repo_factory.get("tickets")
        for tid in (1, 11, 17, 37):
            snap = json.loads(tickets.get(tid)["submitted_params"])
            self.assertEqual((snap["version"], set(snap.keys())), (5, KEYS_6_5), tid)
            self.assertTrue(snap["path_file"].startswith("/opt/automacoes/scripts/"), tid)


if __name__ == "__main__":
    unittest.main()
