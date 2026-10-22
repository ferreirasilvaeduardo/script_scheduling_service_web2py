# -*- coding: utf-8 -*-
"""Testes de masking.py (F2.1): segredos, fluxo em blocos, connect string e filtro de logging."""
import _testenv  # noqa: F401

import io
import logging
import time
import unittest

import masking


def _stream(masker, chunks):
    f = masking.StreamMasker(masker)
    saida = [f.feed(b) for b in chunks]
    saida.append(f.finalize())
    return saida


class TestMasker(unittest.TestCase):

    def setUp(self):
        self.m = masking.Masker()

    def test_segredo_inteiro(self):
        self.m.register("S3gr3d0Forte")
        self.assertEqual(self.m.mask("senha=S3gr3d0Forte fim S3gr3d0Forte"), "senha=**** fim ****")

    def test_curto_e_nao_str_ignorados(self):
        self.m.register("abc")
        self.m.register(None)
        self.m.register(12345)
        self.assertEqual(self.m.mask("abc 12345"), "abc 12345")
        self.assertEqual(self.m.max_len, 0)

    def test_prefixo_comum_mais_longo_vence(self):
        for s in ("abcd", "abcdefgh", "abcdef"):
            self.m.register(s)
        self.assertEqual(self.m.mask("x abcdefgh y abcdef z abcd"), "x **** y **** z ****")
        self.assertEqual(self.m.mask("abcdefghij"), "****ij")

    def test_caracteres_especiais(self):
        self.m.register("a.b*c+(d)")
        self.assertEqual(self.m.mask("[a.b*c+(d)] axbbc"), "[****] axbbc")

    def test_connect_string(self):
        self.assertEqual(self.m.mask("conectando app_prod/Xyz#9@localhost:2424/svc"),
                         "conectando app_prod/****@localhost:2424/svc")
        self.assertEqual(self.m.mask("sqlplus -s scott/tiger@ORCL"), "sqlplus -s scott/****@ORCL")
        self.assertEqual(self.m.mask("/opt/sss/scripts/carga.py"), "/opt/sss/scripts/carga.py")

    def test_nao_str(self):
        self.assertIsNone(self.m.mask(None))
        self.assertEqual(self.m.mask(""), "")


class TestPerformance(unittest.TestCase):

    def test_linha_longa_sem_barra_em_tempo_linear(self):
        # Regressao F8.2: _RE_CONNECT tentava a partir de cada posicao de uma sequencia longa (quadratico).
        m = masking.Masker()
        for texto in ("x" * 1048576, "a/" + "b" * 1048576, "ab/" * 300000):
            inicio = time.monotonic()
            m.mask(texto)
            self.assertLess(time.monotonic() - inicio, 1.0)
        self.assertEqual(m.mask("u=app/Pw12@db:1521/X fat.app/s3nh@//h:1/s x/y"),
                         "u=app/****@db:1521/X fat.app/****@//h:1/s x/y")


class TestStreamMasker(unittest.TestCase):

    def setUp(self):
        self.m = masking.Masker()
        self.m.register("SEGREDO-123")

    def test_segredo_inteiro_em_um_bloco(self):
        self.assertEqual("".join(_stream(self.m, ["antes SEGREDO-123 depois"])), "antes **** depois")

    def test_cortado_entre_2_blocos(self):
        saida = _stream(self.m, ["log: SEGRE", "DO-123 ok"])
        self.assertEqual("".join(saida), "log: **** ok")
        for parte in saida:
            self.assertNotIn("SEGRE", parte)

    def test_cortado_entre_3_blocos(self):
        saida = _stream(self.m, ["x SEG", "REDO-", "123 y"])
        self.assertEqual("".join(saida), "x **** y")
        for parte in saida:
            self.assertNotIn("SEG", parte)

    def test_um_caractere_por_bloco(self):
        texto = "a SEGREDO-123 b SEGREDO-123"
        saida = _stream(self.m, list(texto))
        self.assertEqual("".join(saida), "a **** b ****")

    def test_varios_segredos_prefixo_comum(self):
        m = masking.Masker()
        for s in ("token", "token-longo-999"):
            m.register(s)
        saida = _stream(m, ["inicio token-lo", "ngo-999 meio tok", "en fim"])
        self.assertEqual("".join(saida), "inicio **** meio **** fim")

    def test_cauda_retida_e_finalizar(self):
        f = masking.StreamMasker(self.m)
        # max_len 11: retem 10 caracteres; o corte cai no espaco, fim de token.
        self.assertEqual(f.feed("aa bb 0123456789"), "aa bb ")
        self.assertEqual(f.finalize(), "0123456789")
        self.assertEqual(f.finalize(), "")

    def test_token_longo_retido_ate_o_limite(self):
        f = masking.StreamMasker(self.m)
        bloco = "x" * (masking.MAX_HELD_TOKEN * 3)
        emitido = f.feed(bloco)
        self.assertLessEqual(len(bloco) - len(emitido), masking.MAX_HELD_TOKEN + self.m.max_len)
        self.assertEqual(emitido + f.finalize(), bloco)

    def test_sem_segredos_emite_ate_o_ultimo_token(self):
        m = masking.Masker()
        f = masking.StreamMasker(m)
        self.assertEqual(f.feed("user/pwd@db fim\n"), "user/****@db fim\n")
        self.assertEqual(f.feed("parcial"), "")
        self.assertEqual(f.finalize(), "parcial")

    def test_connect_string_no_fluxo(self):
        saida = _stream(self.m, ["conn app/Senha1@HML ok\n"])
        self.assertEqual("".join(saida), "conn app/****@HML ok\n")

    def test_connect_string_cortada_entre_blocos(self):
        for blocos in (["conn app", "/Senha1@HML ok\n"], ["conn app/Sen", "ha1@HML ok\n"],
                       ["conn app/Senha1@", "HML ok\n"], ["conn app/", "Senha1", "@HML ok\n"]):
            for m in (self.m, masking.Masker()):
                saida = _stream(m, blocos)
                self.assertEqual("".join(saida), "conn app/****@HML ok\n", blocos)
                for parte in saida:
                    self.assertNotIn("Sen", parte, blocos)


class TestLoggingFilter(unittest.TestCase):

    def setUp(self):
        self.m = masking.Masker()
        self.m.register("chave-secreta-1")
        self.buf = io.StringIO()
        self.handler = logging.StreamHandler(self.buf)
        self.handler.setFormatter(logging.Formatter("%(message)s"))
        self.handler.addFilter(masking.logging_filter(self.m))
        self.log = logging.getLogger("test_masking_filtro")
        self.log.propagate = False
        self.log.setLevel(logging.DEBUG)
        self.log.addHandler(self.handler)

    def tearDown(self):
        self.log.removeHandler(self.handler)

    def test_msg(self):
        self.log.info("valor chave-secreta-1")
        self.assertEqual(self.buf.getvalue(), "valor ****\n")

    def test_args_tupla(self):
        self.log.info("a=%s n=%d u=%s", "chave-secreta-1", 7, "x/chave-secreta-1@db")
        self.assertEqual(self.buf.getvalue(), "a=**** n=7 u=x/****@db\n")

    def test_args_dict(self):
        self.log.info("a=%(a)s", {"a": "chave-secreta-1"})
        self.assertEqual(self.buf.getvalue(), "a=****\n")

    def test_arg_nao_str(self):
        self.log.info("erro: %s", ValueError("falhou com chave-secreta-1"))
        self.assertEqual(self.buf.getvalue(), "erro: falhou com ****\n")

    def test_traceback(self):
        try:
            raise RuntimeError("chave-secreta-1")
        except RuntimeError:
            self.log.exception("falha")
        saida = self.buf.getvalue()
        self.assertIn("RuntimeError: ****", saida)
        self.assertNotIn("chave-secreta-1", saida)

    def test_instalar_idempotente(self):
        lg = logging.getLogger("test_masking_instalar")
        h = logging.StreamHandler(io.StringIO())
        lg.addHandler(h)
        try:
            masking.install_filter_on_handlers(self.m)
            masking.install_filter_on_handlers(self.m)
            self.assertEqual(len(h.filters), 1)
        finally:
            lg.removeHandler(h)

    def test_registro_global(self):
        masking.register_secret("global-segredo-77")
        self.assertEqual(masking.MASKER.mask("x global-segredo-77"), "x ****")


if __name__ == "__main__":
    unittest.main()
