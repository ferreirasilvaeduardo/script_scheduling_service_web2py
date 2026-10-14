# -*- coding: utf-8 -*-
"""Regressao: check_env aprovava o build padrao do Alpine (AsyncFunction sem 'new Function')."""
import _testenv  # noqa: F401

import os
import unittest

import check_env


_ALPINE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "static", "js", "alpine.min.js")

# Forma minificada do avaliador padrao do Alpine 3.x (gt -> Ln -> kn -> AsyncFunction).
_PADRAO = (
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


def _bundle(*partes):
    return "(()=>{" + "".join(partes) + "})();"


class TestVerificarAlpineCsp(unittest.TestCase):

    def assertReprova(self, fonte, trecho):
        ok, detalhe = check_env.verificar_alpine_csp(fonte)
        self.assertFalse(ok, detalhe)
        self.assertIn(trecho, detalhe)

    def test_build_padrao_reprovado(self):
        self.assertReprova(_bundle(_PADRAO, _CSP, "B.setEvaluator(gt);"), "construtor dinâmico em 'kn'")

    def test_build_csp_com_avaliador_padrao_morto_aprovado(self):
        ok, detalhe = check_env.verificar_alpine_csp(_bundle(_PADRAO, _CSP, "B.setEvaluator(Jr);"))
        self.assertTrue(ok, detalhe)
        self.assertIn("código morto", detalhe)

    def test_build_csp_puro_aprovado(self):
        ok, detalhe = check_env.verificar_alpine_csp(_bundle(_CSP, "B.setEvaluator(Jr);"))
        self.assertTrue(ok, detalhe)

    def test_construtor_alcancado_indiretamente_ou_por_variante(self):
        variantes = (
            "Object.getPrototypeOf(async()=>{}).constructor",
            "(async function(){}).constructor",
            "(async()=>{}).constructor",
            "Object.getPrototypeOf(function*(){}).constructor",
        )
        for expr in variantes:
            with self.subTest(expr=expr):
                fonte = _bundle(_CSP.replace("let t={};", "let t={};let q=%s;" % expr), "B.setEvaluator(Jr);")
                self.assertReprova(fonte, "construtor dinâmico em 'fi'")

    def test_construtor_passado_como_valor_e_alcancado(self):
        fonte = _bundle(_PADRAO, "function Jr(e,t){return[t].map(kn)}", "B.setEvaluator(Jr);")
        self.assertReprova(fonte, "construtor dinâmico em 'kn'")

    def test_eval_direto_reprovado_em_qualquer_ponto(self):
        for codigo, rotulo in (("let f=new Function('a','return a');", "new Function"),
                               ("let f=Function('return 1');", "Function()"),
                               ("let f=" + "ev" + "al('1');", "Uso de eval ")):
            with self.subTest(rotulo=rotulo):
                self.assertReprova(_bundle(_CSP, "function zz(){%s}" % codigo, "B.setEvaluator(Jr);"), rotulo)

    def test_set_evaluator_ausente_ou_duplicado(self):
        self.assertReprova(_bundle(_CSP), "encontrados 0")
        self.assertReprova(_bundle(_CSP, "B.setEvaluator(Jr);B.setEvaluator(Jr);"), "encontrados 2")

    def test_avaliador_nao_declarado(self):
        self.assertReprova(_bundle(_CSP, "B.setEvaluator(Xy);"), "não declarado")

    def test_bundle_desbalanceado_reprovado(self):
        self.assertReprova(_bundle("function Jr(e){return{a:(e}", "B.setEvaluator(Jr);"), "não analisável")

    def test_delimitadores_em_strings_regex_e_comentarios(self):
        fonte = _bundle(
            'function Jr(e,t){let a="}{)(",b=\'{\',c=/[}{]\\//g,d=`${t.x?`}`:"{"}}`;/* } */return a+b+c+d}',
            "// }\n",
            _PADRAO,
            "B.setEvaluator(Jr);",
        )
        ok, detalhe = check_env.verificar_alpine_csp(fonte)
        self.assertTrue(ok, detalhe)

    def test_asset_instalado_e_build_csp(self):
        with open(_ALPINE, "r", encoding="utf-8") as f:
            ok, detalhe = check_env.verificar_alpine_csp(f.read())
        self.assertTrue(ok, detalhe)


if __name__ == "__main__":
    unittest.main()
