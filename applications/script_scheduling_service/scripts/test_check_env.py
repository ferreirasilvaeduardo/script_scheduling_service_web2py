# -*- coding: utf-8 -*-
"""Regressao: check_env aprovava o build padrao do Alpine (AsyncFunction sem 'new Function')."""
import _testenv  # noqa: F401

import os
import unittest

import check_env


_ALPINE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "static", "js", "alpine.min.js")

# Forma minificada do avaliador padrao do Alpine 3.x (gt -> Ln -> kn -> AsyncFunction).
_PATTERN = (
    'function gt(e,t){let r={};return Ln([r],t,e)}'
    'function Ln(e,t,r){let n=kn(t,r);return(i=()=>{},{scope:o={}}={})=>n(n,o)}'
    'function kn(e,t){let r=Object.getPrototypeOf(async function(){}).constructor;'
    'return new r(["__self","scope"],`with (scope) { __self.result = ${e} }`)}'
)
# Avaliador do build CSP: apenas caminho por ponto, com aviso em template literal.
_CSP = (
    'function Jr(e,t){let r=fi(e);return di(e,t,r)}'
    'function fi(e){let t={};return[t]}'
    'function di(e,t,r){return(n=()=>{},{scope:i={}}={})=>{let a=t.split(".")'
    '.reduce((c,l)=>(c[l]===void 0&&pi(e,t),c[l]),i);n(a)}}'
    'function pi(e,t){console.warn(`Alpine Error: unable to interpret "${t}" {x}`,e)}'
)


def _bundle(*parts):
    return "(()=>{" + "".join(parts) + "})();"


class TestCheckAlpineCsp(unittest.TestCase):

    def assertRejects(self, source, snippet):
        ok, detail = check_env.check_alpine_csp(source)
        self.assertFalse(ok, detail)
        self.assertIn(snippet, detail)

    def test_build_padrao_reprovado(self):
        self.assertRejects(_bundle(_PATTERN, _CSP, "B.setEvaluator(gt);"), "construtor dinâmico em 'kn'")

    def test_build_csp_com_avaliador_padrao_morto_aprovado(self):
        ok, detail = check_env.check_alpine_csp(_bundle(_PATTERN, _CSP, "B.setEvaluator(Jr);"))
        self.assertTrue(ok, detail)
        self.assertIn("código morto", detail)

    def test_build_csp_puro_aprovado(self):
        ok, detail = check_env.check_alpine_csp(_bundle(_CSP, "B.setEvaluator(Jr);"))
        self.assertTrue(ok, detail)

    def test_construtor_alcancado_indiretamente_ou_por_variante(self):
        variants = (
            "Object.getPrototypeOf(async()=>{}).constructor",
            "(async function(){}).constructor",
            "(async()=>{}).constructor",
            "Object.getPrototypeOf(function*(){}).constructor",
        )
        for expr in variants:
            with self.subTest(expr=expr):
                source = _bundle(_CSP.replace("let t={};", "let t={};let q=%s;" % expr), "B.setEvaluator(Jr);")
                self.assertRejects(source, "construtor dinâmico em 'fi'")

    def test_construtor_passado_como_valor_e_alcancado(self):
        source = _bundle(_PATTERN, "function Jr(e,t){return[t].map(kn)}", "B.setEvaluator(Jr);")
        self.assertRejects(source, "construtor dinâmico em 'kn'")

    def test_eval_direto_reprovado_em_qualquer_ponto(self):
        for code, label in (("let f=new Function('a','return a');", "new Function"),
                               ("let f=Function('return 1');", "Function()"),
                               ("let f=" + "ev" + "al('1');", "Uso de eval ")):
            with self.subTest(rotulo=label):
                self.assertRejects(_bundle(_CSP, "function zz(){%s}" % code, "B.setEvaluator(Jr);"), label)

    def test_set_evaluator_ausente_ou_duplicado(self):
        self.assertRejects(_bundle(_CSP), "encontrados 0")
        self.assertRejects(_bundle(_CSP, "B.setEvaluator(Jr);B.setEvaluator(Jr);"), "encontrados 2")

    def test_avaliador_nao_declarado(self):
        self.assertRejects(_bundle(_CSP, "B.setEvaluator(Xy);"), "não declarado")

    def test_bundle_desbalanceado_reprovado(self):
        self.assertRejects(_bundle("function Jr(e){return{a:(e}", "B.setEvaluator(Jr);"), "não analisável")

    def test_delimitadores_em_strings_regex_e_comentarios(self):
        source = _bundle(
            'function Jr(e,t){let a="}{)(",b=\'{\',c=/[}{]\\//g,d=`${t.x?`}`:"{"}}`;/* } */return a+b+c+d}',
            "// }\n",
            _PATTERN,
            "B.setEvaluator(Jr);",
        )
        ok, detail = check_env.check_alpine_csp(source)
        self.assertTrue(ok, detail)

    def test_asset_instalado_e_build_csp(self):
        with open(_ALPINE, "r", encoding="utf-8") as f:
            ok, detail = check_env.check_alpine_csp(f.read())
        self.assertTrue(ok, detail)


if __name__ == "__main__":
    unittest.main()
