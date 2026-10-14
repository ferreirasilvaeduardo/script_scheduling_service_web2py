# -*- coding: utf-8 -*-
"""Testes de params_compiler.py (F3.1): README §6 e §8.4 passo 1, AGENTS §7.4."""
import _testenv  # noqa: F401

import collections
import datetime
import json
import os
import shutil
import tempfile
import unittest

import params_compiler as pc
from params_compiler import ParamErro, SnapshotErro

AGORA = datetime.datetime(2026, 10, 13, 10, 47, 0, 123456)
CfgAgente = collections.namedtuple("CfgAgente", ["base_script_dir", "script_owner_uids"])
CHAVES_6_5 = {"versao", "script_id", "script_nome", "comando_real", "path_file", "script_real",
              "tipo_param", "argv", "respostas", "sensiveis", "compilado_em"}


def prm(codigo, tipo="TEXT", ordem=1, obrigatorio="N", flag=None, opcoes=None, padrao=None,
        padrao_sub=None, regex=None, sensivel="N"):
    return {"codigo": codigo, "label": codigo.upper(), "tipo_componente": tipo, "ordem": ordem,
            "obrigatorio": obrigatorio, "param_nomeado": flag, "opcoes_json": opcoes,
            "valor_padrao": padrao, "valor_padrao_sub": padrao_sub, "regex_validacao": regex,
            "sensivel": sensivel}


def script(tipo_param="NOMEADO", comando="/usr/bin/python3"):
    return {"id": 12, "nome": "carga_faturas", "comando_real": comando,
            "path_file": "faturamento/carga_faturas.py", "tipo_param": tipo_param}


REAL = "/opt/automacoes/scripts/faturamento/carga_faturas.py"


class TestValidarValor(unittest.TestCase):

    def _erro(self, p, valor):
        with self.assertRaises(ParamErro) as ctx:
            pc.validar_valor(p, valor)
        self.assertEqual(ctx.exception.codigo_param, p["codigo"])
        return ctx.exception

    def test_strip(self):
        self.assertEqual(pc.validar_valor(prm("t"), "  abc  "), "abc")

    def test_nul_e_controle(self):
        for valor in ("a\x00b", "a\x1bb", "a\x7fb", "a\nb", "a\tb", "\x01"):
            with self.subTest(valor=repr(valor)):
                self._erro(prm("t"), valor)

    def test_tamanho(self):
        self.assertEqual(len(pc.validar_valor(prm("t"), "x" * 500)), 500)
        self._erro(prm("t"), "x" * 501)

    def test_tipo_nao_str(self):
        self._erro(prm("t"), 10)
        self._erro(prm("n", "NUMBER"), 10)

    def test_text_regex_fullmatch(self):
        p = prm("f", regex=r"[0-9]{4}")
        self.assertEqual(pc.validar_valor(p, "0001"), "0001")
        # search casaria; fullmatch nao.
        self._erro(p, "00012")
        self._erro(p, "x0001")

    def test_text_regex_mal_configurada(self):
        self._erro(prm("f", regex=r"([0-9]"), "1")

    def test_number(self):
        p = prm("n", "NUMBER")
        for ok in ("0", "-5", "123456789012345678", "1.123456", "-0.5"):
            self.assertEqual(pc.validar_valor(p, ok), ok)
        for ruim in ("1e3", "1.1234567", "1234567890123456789", "+1", "1.", ".5", "abc", "1,5"):
            with self.subTest(valor=ruim):
                self._erro(p, ruim)

    def test_date(self):
        p = prm("d", "DATE")
        self.assertEqual(pc.validar_valor(p, "2026-10-13"), "2026-10-13")
        self.assertEqual(pc.validar_valor(p, "2026-1-5"), "2026-01-05")
        for ruim in ("2026-02-30", "13/10/2026", "2026-10-13 10:00", "x"):
            with self.subTest(valor=ruim):
                self._erro(p, ruim)

    def test_select(self):
        p = prm("s", "SELECT", opcoes='{"CSV": "Arquivo CSV", "JSON": "Arquivo JSON"}')
        self.assertEqual(pc.validar_valor(p, "CSV"), "CSV")
        self._erro(p, "XML")
        self._erro(p, "Arquivo CSV")
        self._erro(p, "csv")

    def test_select_opcoes_json_invalido(self):
        for opcoes in ("{nao json", '["CSV"]', "{}", None, '"CSV"'):
            with self.subTest(opcoes=opcoes):
                e = self._erro(prm("s", "SELECT", opcoes=opcoes), "CSV")
                self.assertIn("administrador", e.mensagem)

    def test_checkbox(self):
        p = prm("c", "CHECKBOX")
        for valor, esperado in (("true", True), ("TRUE", True), ("1", True), ("False", False),
                                ("0", False), (True, True), (False, False)):
            self.assertIs(pc.validar_valor(p, valor), esperado)
        for ruim in ("sim", "yes", "2", 1):
            with self.subTest(valor=ruim):
                self._erro(p, ruim)

    def test_tipo_componente_desconhecido(self):
        self._erro(prm("x", "FILE"), "a")

    def test_sensivel_nao_ecoa_valor(self):
        segredo = "Segr3d0-Muito-Secreto"
        for p in (prm("k", regex=r"[a-z]+", sensivel="S"), prm("k", "NUMBER", sensivel="S"),
                  prm("k", "SELECT", opcoes='{"A":"a"}', sensivel="S")):
            e = self._erro(p, segredo)
            self.assertNotIn(segredo, e.mensagem)
            self.assertNotIn(segredo, str(e))


class TestRegexCadastro(unittest.TestCase):

    def test_validas(self):
        for padrao in (r"^[0-9]{4}$", r"[A-Z]{2}-\d+", r"(abc)?x+"):
            pc.validar_regex_cadastro(padrao)

    def test_nao_compila(self):
        for padrao in (r"([0-9]", r"*a", None):
            with self.subTest(padrao=padrao):
                with self.assertRaises(ParamErro):
                    pc.validar_regex_cadastro(padrao)

    def test_redos_rejeitada(self):
        for padrao in (r"(a+)+", r"(a*)*", r"(\w+){2}", r"^(x+y*)+$", r"(.*a)+"):
            with self.subTest(padrao=padrao):
                with self.assertRaises(ParamErro) as ctx:
                    pc.validar_regex_cadastro(padrao)
                self.assertIn("ReDoS", ctx.exception.mensagem)


class TestPrecedencia(unittest.TestCase):

    def test_ordem_de_precedencia(self):
        v = [prm("a", ordem=1, padrao_sub="sub", padrao="glob")]
        self.assertEqual(pc.resolver_respostas(v, {"a": "resp"})["a"], "resp")
        self.assertEqual(pc.resolver_respostas(v, {})["a"], "sub")
        self.assertEqual(pc.resolver_respostas(v, {"a": "   "})["a"], "sub")
        v = [prm("a", ordem=1, padrao="glob")]
        self.assertEqual(pc.resolver_respostas(v, None)["a"], "glob")
        v = [prm("a", ordem=1)]
        self.assertIsNone(pc.resolver_respostas(v, {})["a"])

    def test_padrao_tambem_validado(self):
        v = [prm("n", "NUMBER", ordem=1, padrao_sub="abc", padrao="10")]
        with self.assertRaises(ParamErro) as ctx:
            pc.resolver_respostas(v, {})
        self.assertEqual(ctx.exception.codigo_param, "n")
        v = [prm("n", "NUMBER", ordem=1, padrao="abc")]
        with self.assertRaises(ParamErro):
            pc.resolver_respostas(v, {})

    def test_resposta_invalida_nao_cai_no_padrao(self):
        v = [prm("n", "NUMBER", ordem=1, padrao_sub="10")]
        with self.assertRaises(ParamErro):
            pc.resolver_respostas(v, {"n": "abc"})

    def test_obrigatorio_ausente(self):
        v = [prm("a", ordem=1, obrigatorio="S")]
        with self.assertRaises(ParamErro) as ctx:
            pc.resolver_respostas(v, {"a": ""})
        self.assertEqual(ctx.exception.codigo_param, "a")
        self.assertIn("obrigatório", ctx.exception.mensagem)

    def test_checkbox_falso_obrigatorio_e_valor(self):
        v = [prm("c", "CHECKBOX", ordem=1, obrigatorio="S")]
        self.assertIs(pc.resolver_respostas(v, {"c": "false"})["c"], False)

    def test_ordem_do_resultado(self):
        v = [prm("z", ordem=3), prm("a", ordem=1), prm("m", ordem=2)]
        self.assertEqual(list(pc.resolver_respostas(v, {}).keys()), ["a", "m", "z"])


class TestMontarArgs(unittest.TestCase):

    def _args(self, tipo_param, vinculos, respostas):
        return pc.montar_args(tipo_param, vinculos, pc.resolver_respostas(vinculos, respostas))

    def _erro(self, tipo_param, vinculos, respostas):
        with self.assertRaises(ParamErro) as ctx:
            self._args(tipo_param, vinculos, respostas)
        return ctx.exception

    def test_nomeado_flags(self):
        v = [prm("d", "DATE", ordem=2, flag="--data"), prm("n", "NUMBER", ordem=1, flag="-n")]
        self.assertEqual(self._args("NOMEADO", v, {"d": "2026-10-13", "n": "5"}),
                         ["-n", "5", "--data", "2026-10-13"])

    def test_nomeado_longa_valor_com_hifen(self):
        v = [prm("t", ordem=1, flag="--taxa"), prm("x", ordem=2, flag="--texto")]
        self.assertEqual(self._args("NOMEADO", v, {"t": "-1.5", "x": "--rm"}), ["--taxa=-1.5", "--texto=--rm"])

    def test_nomeado_curta_valor_com_hifen_rejeitado(self):
        for tipo, valor in (("NUMBER", "-5"), ("TEXT", "-rf")):
            with self.subTest(tipo=tipo):
                e = self._erro("NOMEADO", [prm("n", tipo, ordem=1, flag="-n")], {"n": valor})
                self.assertEqual(e.codigo_param, "n")
                self.assertNotIn(valor, e.mensagem)

    def test_nomeado_checkbox(self):
        v = [prm("v", "CHECKBOX", ordem=1, flag="--verbose"), prm("m", "CHECKBOX", ordem=2, flag="-m")]
        self.assertEqual(self._args("NOMEADO", v, {"v": "true", "m": "false"}), ["--verbose"])
        self.assertEqual(self._args("NOMEADO", v, {"v": "0", "m": "1"}), ["-m"])
        self.assertEqual(self._args("NOMEADO", v, {}), [])

    def test_nomeado_opcional_vazio_omitido(self):
        v = [prm("a", ordem=1, flag="--a"), prm("b", ordem=2, flag="--b")]
        self.assertEqual(self._args("NOMEADO", v, {"b": "x"}), ["--b", "x"])

    def test_nomeado_sem_flag(self):
        e = self._erro("NOMEADO", [prm("a", ordem=1)], {"a": "x"})
        self.assertEqual(e.codigo_param, "a")

    def test_sequencial(self):
        v = [prm("c", "CHECKBOX", ordem=4), prm("a", ordem=1, flag="--ignorada"),
             prm("b", ordem=2), prm("n", "NUMBER", ordem=3), prm("d", "CHECKBOX", ordem=5)]
        self.assertEqual(self._args("SEQUENCIAL", v, {"a": "x", "n": "-7", "c": "true", "d": "false"}),
                         ["x", "", "-7", "1", "0"])

    def test_sequencial_opcional_vazio_intermediario(self):
        v = [prm("a", ordem=1), prm("b", ordem=2), prm("c", "CHECKBOX", ordem=3), prm("d", ordem=4)]
        self.assertEqual(self._args("SEQUENCIAL", v, {"a": "x", "d": "y"}), ["x", "", "", "y"])

    def test_sequencial_hifen_rejeitado_exceto_number(self):
        for tipo, valor in (("TEXT", "-x"), ("SELECT", "-A")):
            with self.subTest(tipo=tipo):
                p = prm("t", tipo, ordem=1, opcoes='{"-A": "a"}')
                e = self._erro("SEQUENCIAL", [p], {"t": valor})
                self.assertEqual(e.codigo_param, "t")
        self.assertEqual(self._args("SEQUENCIAL", [prm("n", "NUMBER", ordem=1)], {"n": "-1.5"}), ["-1.5"])

    def test_nenhum(self):
        self.assertEqual(pc.montar_args("NENHUM", [], collections.OrderedDict()), [])
        e = self._erro("NENHUM", [prm("a", ordem=1)], {"a": "x"})
        self.assertIsNone(e.codigo_param)

    def test_tipo_param_desconhecido(self):
        e = self._erro("OUTRO", [prm("a", ordem=1)], {"a": "x"})
        self.assertIsNone(e.codigo_param)


class TestMontarArgv(unittest.TestCase):

    def test_interpretadores(self):
        self.assertEqual(pc.montar_argv("/usr/bin/python3", "/b/s.py", ["a"]), ["/usr/bin/python3", "-I", "/b/s.py", "a"])
        self.assertEqual(pc.montar_argv("/bin/bash", "/b/s.sh", ["a"]), ["/bin/bash", "/b/s.sh", "a"])
        self.assertEqual(pc.montar_argv("/bin/sh", "/b/s.sh", []), ["/bin/sh", "/b/s.sh"])

    def test_fora_da_allowlist(self):
        import path_guard
        with self.assertRaises(path_guard.PathGuardErro):
            pc.montar_argv("/usr/bin/perl", "/b/s.pl", [])


class TestCompilarSnapshot(unittest.TestCase):

    def _vinculos(self):
        return [prm("data_ref", "DATE", ordem=1, obrigatorio="S", flag="--data"),
                prm("token", ordem=2, flag="--token", sensivel="S"),
                prm("modo", "SELECT", ordem=3, flag="--modo", opcoes='{"A":"Ação","B":"Bê"}', padrao="A")]

    def test_formato_6_5(self):
        js, resolvidos, erros = pc.compilar_snapshot(script(), self._vinculos()[:1], {"data_ref": "2026-10-13"},
                                                     REAL, AGORA)
        self.assertEqual(erros, {})
        esperado = {
            "versao": 1, "script_id": 12, "script_nome": "carga_faturas", "comando_real": "/usr/bin/python3",
            "path_file": "faturamento/carga_faturas.py", "script_real": REAL, "tipo_param": "NOMEADO",
            "argv": ["/usr/bin/python3", "-I", REAL, "--data", "2026-10-13"],
            "respostas": {"data_ref": "2026-10-13"}, "sensiveis": [], "compilado_em": "2026-10-13 10:47:00",
        }
        self.assertEqual(json.loads(js), esperado)
        self.assertEqual(js, json.dumps(esperado, ensure_ascii=False, sort_keys=True))

    def test_determinismo(self):
        v = self._vinculos()
        r1 = collections.OrderedDict([("data_ref", "2026-10-13"), ("token", "abc123"), ("modo", "B")])
        r2 = collections.OrderedDict([("modo", "B"), ("token", "abc123"), ("data_ref", "2026-10-13")])
        js1 = pc.compilar_snapshot(script(), v, r1, REAL, AGORA)[0]
        js2 = pc.compilar_snapshot(script(), list(reversed(v)), r2, REAL, AGORA)[0]
        self.assertIsNotNone(js1)
        self.assertEqual(js1, js2)
        snap = json.loads(js1)
        self.assertEqual(snap["argv"][3:], ["--data", "2026-10-13", "--token", "abc123", "--modo", "B"])
        self.assertEqual(snap["sensiveis"], ["token"])

    def test_utf8_sem_escape(self):
        v = [prm("t", ordem=1, flag="--t")]
        js = pc.compilar_snapshot(script(), v, {"t": "ação"}, REAL, AGORA)[0]
        self.assertIn("ação", js)

    def test_respostas_tipadas(self):
        v = [prm("c", "CHECKBOX", ordem=1, flag="--c"), prm("o", ordem=2, flag="--o")]
        snap = json.loads(pc.compilar_snapshot(script(), v, {"c": "1"}, REAL, AGORA)[0])
        self.assertEqual(snap["respostas"], {"c": True, "o": None})

    def test_erros_acumulados(self):
        v = self._vinculos() + [prm("n", "NUMBER", ordem=4, flag="-n")]
        js, resolvidos, erros = pc.compilar_snapshot(
            script(), v, {"token": "a\x00b", "modo": "Z", "n": "-3"}, REAL, AGORA)
        self.assertIsNone(js)
        self.assertEqual(list(erros.keys()), ["data_ref", "token", "modo", "n"])
        for msg in erros.values():
            self.assertNotIn("a\x00b", msg)

    def test_erros_estruturais(self):
        js, _, erros = pc.compilar_snapshot(script("NENHUM"), [prm("a", ordem=1)], {"a": "x"}, REAL, AGORA)
        self.assertIsNone(js)
        self.assertIn(pc.CHAVE_GERAL, erros)
        js, _, erros = pc.compilar_snapshot(script(comando="/usr/bin/perl"), [], {}, REAL, AGORA)
        self.assertIsNone(js)
        self.assertIn(pc.CHAVE_GERAL, erros)

    def test_nenhum_sem_vinculos(self):
        js = pc.compilar_snapshot(script("NENHUM", "/bin/bash"), [], {}, "/b/x.sh", AGORA)[0]
        self.assertEqual(json.loads(js)["argv"], ["/bin/bash", "/b/x.sh"])

    def test_argv_para_exibicao(self):
        v = self._vinculos() + [prm("seq", ordem=4, flag="-s", sensivel="S")]
        snap = json.loads(pc.compilar_snapshot(
            script(), v, {"data_ref": "2026-10-13", "token": "-segredo", "seq": "outro_segredo"}, REAL, AGORA)[0])
        exib = pc.argv_para_exibicao(snap)
        self.assertEqual(exib, ["/usr/bin/python3", "-I", REAL, "--data", "2026-10-13",
                                "--token=****", "--modo", "A", "-s", "****"])
        self.assertNotIn("segredo", " ".join(exib))
        self.assertIn("-segredo", snap["argv"][5])

    def test_argv_para_exibicao_sem_sensiveis(self):
        snap = json.loads(pc.compilar_snapshot(script(), self._vinculos()[:1], {"data_ref": "2026-10-13"},
                                               REAL, AGORA)[0])
        self.assertEqual(pc.argv_para_exibicao(snap), snap["argv"])


@unittest.skipIf(os.geteuid() == 0, "root sempre passa em os.access(W_OK)")
class TestValidarSnapshot(unittest.TestCase):

    def setUp(self):
        self.raiz = tempfile.mkdtemp(prefix="sss_pc_")
        self.base = os.path.join(self.raiz, "scripts")
        os.makedirs(os.path.join(self.base, "faturamento"))
        self.arq = os.path.join(self.base, "faturamento", "carga_faturas.py")
        with open(self.arq, "w") as f:
            f.write("print(1)\n")
        os.chmod(self.arq, 0o444)
        os.chmod(os.path.join(self.base, "faturamento"), 0o555)
        os.chmod(self.base, 0o555)
        self.cfg = CfgAgente(self.base, (os.getuid(),))
        self.real = os.path.realpath(self.arq)
        v = [prm("data_ref", "DATE", ordem=1, obrigatorio="S", flag="--data")]
        self.js = pc.compilar_snapshot(script(), v, {"data_ref": "2026-10-13"}, self.real, AGORA)[0]

    def tearDown(self):
        for raiz, _, _ in os.walk(self.raiz):
            os.chmod(raiz, 0o755)
        shutil.rmtree(self.raiz)

    def _alterado(self, **mudancas):
        snap = json.loads(self.js)
        snap.update(mudancas)
        return json.dumps(snap)

    def _motivo(self, js, cfg=None):
        with self.assertRaises(SnapshotErro) as ctx:
            pc.validar_snapshot(js, cfg or self.cfg)
        return ctx.exception.motivo

    def test_ok(self):
        snap = pc.validar_snapshot(self.js, self.cfg)
        self.assertEqual(snap["script_real"], self.real)

    def test_json_e_estrutura(self):
        self.assertEqual(self._motivo("{x"), "JSON_INVALIDO")
        self.assertEqual(self._motivo(None), "JSON_INVALIDO")
        self.assertEqual(self._motivo("[]"), "ESTRUTURA_INVALIDA")
        self.assertEqual(self._motivo('{"versao": 1}'), "ESTRUTURA_INVALIDA")

    def test_versao(self):
        self.assertEqual(self._motivo(self._alterado(versao=2)), "VERSAO_NAO_SUPORTADA")

    def test_argv0(self):
        snap = json.loads(self.js)
        argv = ["/bin/sh"] + snap["argv"][1:]
        self.assertEqual(self._motivo(self._alterado(argv=argv)), "ARGV0_DIVERGENTE")
        self.assertEqual(self._motivo(self._alterado(argv=[])), "ARGV0_DIVERGENTE")

    def test_interpretador_fora_da_allowlist(self):
        snap = json.loads(self.js)
        argv = ["/usr/bin/perl"] + snap["argv"][1:]
        self.assertEqual(self._motivo(self._alterado(argv=argv, comando_real="/usr/bin/perl")),
                         "INTERPRETADOR_NAO_PERMITIDO")

    def test_path_guard_revalidado(self):
        self.assertEqual(self._motivo(self._alterado(path_file="../x.py")), "PATH_GUARD_CONTEM_PONTOS")
        outro = CfgAgente(self.base, (os.getuid() + 1,))
        self.assertEqual(self._motivo(self.js, outro), "PATH_GUARD_DONO_INVALIDO")

    def test_script_real_divergente(self):
        self.assertEqual(self._motivo(self._alterado(script_real="/tmp/outro.py")), "SCRIPT_REAL_DIVERGENTE")

    def test_prefixo_do_argv(self):
        snap = json.loads(self.js)
        sem_i = [snap["argv"][0]] + snap["argv"][2:]
        self.assertEqual(self._motivo(self._alterado(argv=sem_i)), "ARGV_PREFIXO_DIVERGENTE")
        trocado = snap["argv"][:2] + ["/tmp/outro.py"] + snap["argv"][3:]
        self.assertEqual(self._motivo(self._alterado(argv=trocado)), "ARGV_PREFIXO_DIVERGENTE")


class TestSeedFake(unittest.TestCase):
    """compilar_snapshot com o seed do FAKE (script 1, carga_diaria) gera o formato da §6.5."""

    def setUp(self):
        import repo_factory
        self.repo_factory = repo_factory
        repo_factory.configurar({"app": {"data_backend": "FAKE", "sss_env": "DEV"}})
        repo_factory.reset_singletons()
        self.catalogo = repo_factory.obter("catalogo")

    def tearDown(self):
        self.repo_factory.configurar(None)
        self.repo_factory.reset_singletons()

    def test_carga_diaria(self):
        scr = self.catalogo.scripts_obter(1)
        vinculos = self.catalogo.script_params_obter(1)
        real = "/opt/automacoes/scripts/" + scr["path_file"]
        js, resolvidos, erros = pc.compilar_snapshot(scr, vinculos, {}, real, AGORA)
        self.assertEqual(erros, {})
        snap = json.loads(js)
        self.assertEqual(set(snap.keys()), CHAVES_6_5)
        self.assertEqual(js, json.dumps(snap, ensure_ascii=False, sort_keys=True))
        self.assertEqual(snap["argv"], ["/usr/bin/python3", "-I", real, "--data-ref", "2026-10-14", "-n", "5000",
                                        "--modo", "REAL", "--verbose", "--api-key", "segredo_dev_123"])
        self.assertEqual(snap["sensiveis"], ["chave_api"])
        self.assertEqual(snap["respostas"]["verbose"], True)
        self.assertNotIn("segredo_dev_123", pc.argv_para_exibicao(snap))

    def test_todos_os_scripts_do_seed_compilam(self):
        for sid in (1, 2, 3, 4, 6):
            with self.subTest(script_id=sid):
                scr = self.catalogo.scripts_obter(sid)
                vinculos = self.catalogo.script_params_obter(sid)
                js, _, erros = pc.compilar_snapshot(scr, vinculos, {}, "/b/" + scr["path_file"], AGORA)
                self.assertEqual(erros, {})
                self.assertEqual(set(json.loads(js).keys()), CHAVES_6_5)


if __name__ == "__main__":
    unittest.main()
