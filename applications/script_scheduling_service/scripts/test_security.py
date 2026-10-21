# -*- coding: utf-8 -*-
"""Testes de security.py (F2.1): hash de senha, politica, CSRF, Origin, sessao e cookies."""
import _testenv  # noqa: F401

import ast
import os
import re
import unittest

import security

_MODULES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules")
_RE_FORMATO = re.compile(r"pbkdf2_sha256\$200000\$[0-9a-f]{32}\$[0-9a-f]{64}")


def _hash_com_iteracoes(senha, iteracoes):
    import hashlib
    salt = b"\x01" * 16
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, iteracoes)
    return "pbkdf2_sha256$%d$%s$%s" % (iteracoes, salt.hex(), dk.hex())


class TestHashSenha(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.senha = u"correta-horse-çã-12"
        cls.armazenado = security.hash_password(cls.senha)

    def test_formato(self):
        self.assertTrue(_RE_FORMATO.fullmatch(self.armazenado))

    def test_salt_aleatorio(self):
        self.assertNotEqual(self.armazenado, security.hash_password(self.senha))

    def test_verificacao_certa_e_errada(self):
        self.assertTrue(security.verify_password(self.senha, self.armazenado))
        self.assertFalse(security.verify_password(self.senha + "x", self.armazenado))
        self.assertFalse(security.verify_password("", self.armazenado))

    def test_senha_nao_str(self):
        self.assertFalse(security.verify_password(None, self.armazenado))
        self.assertFalse(security.verify_password(self.senha.encode("utf-8"), self.armazenado))
        with self.assertRaises(TypeError):
            security.hash_password(None)

    def test_bloqueado_exclamacao(self):
        self.assertFalse(security.verify_password(self.senha, "!"))
        self.assertFalse(security.verify_password("!", "!"))

    def test_formatos_invalidos(self):
        partes = self.armazenado.split("$")
        invalidos = [
            None, "", "lixo", self.armazenado + "$",
            "pbkdf2_sha1$" + "$".join(partes[1:]),
            "$".join([partes[0], "abc", partes[2], partes[3]]),
            "$".join([partes[0], "0", partes[2], partes[3]]),
            "$".join([partes[0], partes[1], partes[2][:-2], partes[3]]),
            "$".join([partes[0], partes[1], partes[2], partes[3].upper()]),
            "$".join([partes[0], partes[1], partes[2], partes[3][:-1] + "g"]),
        ]
        for inv in invalidos:
            self.assertFalse(security.verify_password(self.senha, inv), inv)
            self.assertFalse(security.needs_rehash(inv), inv)

    def test_iteracoes_antigas_verificam_e_pedem_rehash(self):
        antigo = _hash_com_iteracoes("senha-antiga-123", 1000)
        self.assertTrue(security.verify_password("senha-antiga-123", antigo))
        self.assertTrue(security.needs_rehash(antigo))
        self.assertFalse(security.needs_rehash(self.armazenado))
        self.assertFalse(security.needs_rehash("!"))

    def test_hash_ficticio(self):
        h = security.dummy_hash()
        self.assertTrue(_RE_FORMATO.fullmatch(h))
        self.assertEqual(h, security.dummy_hash())
        self.assertFalse(security.verify_password("qualquer-coisa-123", h))


class TestPoliticaSenha(unittest.TestCase):

    def test_minimo_12(self):
        self.assertEqual(len(security.validate_password_policy("a" * 11)), 1)
        self.assertEqual(security.validate_password_policy("a" * 12), [])
        self.assertEqual(security.validate_password_policy(u"ç" * 12), [])

    def test_nao_str_ou_vazia(self):
        self.assertTrue(security.validate_password_policy(None))
        self.assertTrue(security.validate_password_policy(""))


class TestRetirarSenhas(unittest.TestCase):

    def test_remove_de_todas_as_origens(self):
        post_vars = {"login": "admin", "senha": "Segredo-123456", "outra": "x"}
        todas = dict(post_vars, pagina="1")
        senhas = security.strip_passwords((post_vars, todas), ("senha", "confirmacao"))
        self.assertEqual(senhas, {"senha": "Segredo-123456", "confirmacao": None})
        self.assertNotIn("senha", post_vars)
        self.assertNotIn("senha", todas)
        self.assertEqual(post_vars, {"login": "admin", "outra": "x"})
        self.assertNotIn("Segredo", repr(post_vars) + repr(todas))

    def test_lista_vale_o_ultimo_e_nao_str_vira_none(self):
        self.assertEqual(security.strip_passwords(({"s": ["a", "b"]},), ("s",)), {"s": "b"})
        self.assertEqual(security.strip_passwords(({"s": []},), ("s",)), {"s": None})
        self.assertEqual(security.strip_passwords(({"s": 123},), ("s",)), {"s": None})

    def test_controllers_nao_leem_senha_direto_de_request(self):
        # Regressao: login lia request.post_vars.get("senha") e a senha ia parar no ticket de erro.
        raiz = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "controllers")
        padrao = re.compile(r"request\.(post_vars|vars)\.get\(\s*[\'\"](senha|senha_atual|nova|confirmacao)[\'\"]")
        for nome in sorted(os.listdir(raiz)):
            if nome.endswith(".py"):
                with open(os.path.join(raiz, nome), encoding="utf-8") as f:
                    self.assertIsNone(padrao.search(f.read()), nome)


class TestCsrf(unittest.TestCase):

    def test_token(self):
        t = security.generate_csrf_token()
        self.assertGreaterEqual(len(t), 43)
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9_\-]+", t))
        self.assertNotEqual(t, security.generate_csrf_token())

    def test_validacao(self):
        t = security.generate_csrf_token()
        self.assertTrue(security.validate_csrf_token(t, t))
        self.assertFalse(security.validate_csrf_token(t, t[:-1] + ("A" if t[-1] != "A" else "B")))
        self.assertFalse(security.validate_csrf_token(t, ""))
        self.assertFalse(security.validate_csrf_token(t, None))
        self.assertFalse(security.validate_csrf_token(None, None))
        self.assertFalse(security.validate_csrf_token("", ""))
        self.assertFalse(security.validate_csrf_token(t, [t]))
        self.assertFalse(security.validate_csrf_token(t, u"çãé"))


class TestOrigemPermitida(unittest.TestCase):

    PERMITIDAS = ["https://sss.empresa.local", "http://127.0.0.1:8000"]

    def _ok(self, origin, referer=None):
        return security.is_allowed_origin(origin, referer, self.PERMITIDAS)

    def test_origem_igual(self):
        self.assertTrue(self._ok("https://sss.empresa.local"))
        self.assertTrue(self._ok("HTTPS://SSS.Empresa.Local"))
        self.assertTrue(self._ok("http://127.0.0.1:8000"))

    def test_porta_padrao_implicita_e_explicita(self):
        self.assertTrue(self._ok("https://sss.empresa.local:443"))

    def test_porta_diferente(self):
        self.assertFalse(self._ok("https://sss.empresa.local:8443"))
        self.assertFalse(self._ok("http://127.0.0.1:8001"))

    def test_esquema_diferente(self):
        self.assertFalse(self._ok("http://sss.empresa.local"))
        self.assertFalse(self._ok("ftp://sss.empresa.local"))

    def test_host_diferente(self):
        self.assertFalse(self._ok("https://sss.empresa.local.evil.com"))
        self.assertFalse(self._ok("https://evil.com"))

    def test_so_referer(self):
        self.assertTrue(self._ok(None, "https://sss.empresa.local/script_scheduling_service/dev/componentes?x=1"))
        self.assertTrue(self._ok("", "http://127.0.0.1:8000/a/b"))
        self.assertFalse(self._ok(None, "https://evil.com/https://sss.empresa.local"))

    def test_nenhum_dos_dois(self):
        self.assertFalse(self._ok(None, None))
        self.assertFalse(self._ok("", ""))

    def test_null_e_userinfo(self):
        self.assertFalse(self._ok("null"))
        self.assertFalse(self._ok("https://user@sss.empresa.local"))
        self.assertFalse(self._ok(None, "https://sss.empresa.local@evil.com/"))

    def test_origin_invalido_nao_cai_para_referer(self):
        self.assertFalse(self._ok("https://evil.com", "https://sss.empresa.local/"))
        self.assertFalse(self._ok("null", "https://sss.empresa.local/"))

    def test_porta_invalida(self):
        self.assertFalse(self._ok("http://127.0.0.1:99999"))
        self.assertFalse(self._ok("http://127.0.0.1:abc"))

    def test_lista_vazia(self):
        self.assertFalse(security.is_allowed_origin("https://sss.empresa.local", None, []))


class TestSessaoExpirada(unittest.TestCase):

    def test_limites(self):
        self.assertFalse(security.is_session_expired(1000.0, 1000.0 + 1800, 1800))
        self.assertTrue(security.is_session_expired(1000.0, 1000.0 + 1801, 1800))

    def test_sem_marca(self):
        self.assertTrue(security.is_session_expired(None, 1000.0, 1800))
        self.assertTrue(security.is_session_expired("1000", 1000.0, 1800))
        self.assertTrue(security.is_session_expired(True, 1000.0, 1800))


class TestCookiesSeguros(unittest.TestCase):

    def test_httponly_e_secure(self):
        c = security.SecureCookies(secure=True)
        c["session_data_x"] = "valor"
        c["session_data_x"]["path"] = "/"
        saida = c["session_data_x"].OutputString()
        self.assertIn("HttpOnly", saida)
        self.assertIn("Secure", saida)

    def test_sem_secure(self):
        c = security.SecureCookies(secure=False)
        c["a"] = "1"
        saida = c["a"].OutputString()
        self.assertIn("HttpOnly", saida)
        self.assertNotIn("Secure", saida)

    def test_reatribuicao_mantem_atributos(self):
        c = security.SecureCookies(secure=True)
        c["a"] = "1"
        c.pop("a")
        c["a"] = "2"
        self.assertIn("HttpOnly", c["a"].OutputString())

    def test_valor_bytes_decodificado(self):
        c = security.SecureCookies(secure=False)
        c["s"] = b"hmac256:abc:ZGF0YQ=="
        self.assertEqual(c["s"].value, "hmac256:abc:ZGF0YQ==")
        self.assertNotIn("b'", c["s"].OutputString())

    def test_adaptar_cookie_sessao(self):
        import http.cookies
        r = http.cookies.SimpleCookie()
        r.load('s="hmac256:abc:ZGF0YQ=="; outro=1')
        security.adapt_session_cookie(r, "s")
        self.assertEqual(r["s"].value, b"hmac256:abc:ZGF0YQ==")
        security.adapt_session_cookie(r, "ausente")
        self.assertEqual(r["outro"].value, "1")

    def test_adaptar_cookie_sessao_nao_ascii_descartado(self):
        import http.cookies
        r = http.cookies.SimpleCookie()
        r["s"] = u"ção"
        security.adapt_session_cookie(r, "s")
        self.assertNotIn("s", r)

    def test_roundtrip_secure_dumps(self):
        """Regressao: cookie de sessao do web2py precisa sobreviver a ida e volta no Python 3."""
        import http.cookies
        from gluon.utils import secure_dumps, secure_loads
        chave = "k" * 32
        c = security.SecureCookies(secure=True)
        c["session_data_x"] = secure_dumps({"csrf_token": "t"}, chave)
        r = http.cookies.SimpleCookie()
        r.load(c["session_data_x"].OutputString().split(";")[0])
        security.adapt_session_cookie(r, "session_data_x")
        self.assertEqual(secure_loads(r["session_data_x"].value, chave, safe_unpickle=False), {"csrf_token": "t"})

    def test_adotar(self):
        import http.cookies
        origem = http.cookies.SimpleCookie()
        origem["b"] = "2"
        c = security.SecureCookies(secure=True)
        c.adopt(origem)
        saida = c["b"].OutputString()
        self.assertIn("HttpOnly", saida)
        self.assertIn("Secure", saida)


class TestModulosPuros(unittest.TestCase):

    def test_sem_gluon(self):
        for nome in ("security.py", "masking.py"):
            with open(os.path.join(_MODULES, nome), "r", encoding="utf-8") as f:
                arvore = ast.parse(f.read())
            for no in ast.walk(arvore):
                if isinstance(no, ast.Import):
                    nomes = [a.name for a in no.names]
                elif isinstance(no, ast.ImportFrom):
                    nomes = [no.module or ""]
                else:
                    continue
                for n in nomes:
                    self.assertFalse(n.split(".")[0] == "gluon", "%s importa %s" % (nome, n))



class TestValidarNext(unittest.TestCase):

    def test_validos(self):
        for v in ("/script_scheduling_service/default/index",
                  "/script_scheduling_service/dev/componentes?pagina=2&status=FAILED"):
            self.assertEqual(security.validate_next(v), v)

    def test_rejeitados(self):
        for v in (None, "", 123, "//evil.com", "//evil.com/script_scheduling_service/",
                  "/\\evil.com", "http://evil.com/script_scheduling_service/",
                  "https:/script_scheduling_service/", "/outra_app/default/index",
                  "/script_scheduling_service//evil.com", "/script_scheduling_service/../admin/",
                  "/script_scheduling_service/%2e%2e/admin", "/script_scheduling_service/%2F%2Fevil",
                  "/script_scheduling_service/a b", "/script_scheduling_service/\n",
                  "script_scheduling_service/default", "/script_scheduling_service/" + "a" * 600):
            self.assertIsNone(security.validate_next(v), repr(v))


class TestIpOrigem(unittest.TestCase):

    def test_sem_proxy(self):
        self.assertEqual(security.client_ip("10.0.0.5", "1.2.3.4", ()), "10.0.0.5")

    def test_xff_ignorado_de_nao_confiavel(self):
        self.assertEqual(security.client_ip("10.0.0.5", "1.2.3.4", ("10.0.0.9",)), "10.0.0.5")

    def test_xff_de_proxy_confiavel(self):
        self.assertEqual(security.client_ip("10.0.0.9", "6.6.6.6, 1.2.3.4", ("10.0.0.9",)), "1.2.3.4")
        self.assertEqual(security.client_ip("10.0.0.9", "1.2.3.4, 10.0.0.8", ("10.0.0.9", "10.0.0.8")),
                         "1.2.3.4")

    def test_xff_invalido(self):
        self.assertEqual(security.client_ip("10.0.0.9", "lixo", ("10.0.0.9",)), "10.0.0.9")
        self.assertIsNone(security.client_ip("nao-ip", None, ()))

    def test_ipv6(self):
        self.assertEqual(security.client_ip("::1", None, ()), "::1")


class TestCabecalhoReferrer(unittest.TestCase):
    """Regressao: 'no-referrer' faz o navegador enviar Origin: null e todo POST de formulario vira 403."""

    def test_referrer_policy_same_origin(self):
        caminho = os.path.join(os.path.dirname(_MODULES), "models", "10_security.py")
        with open(caminho, encoding="utf-8") as f:
            codigo = f.read()
        self.assertRegex(codigo, r'"Referrer-Policy":\s*"same-origin"')
        self.assertNotRegex(codigo, r'"Referrer-Policy":\s*"no-referrer"')

    def test_origin_null_continua_rejeitado(self):
        self.assertFalse(security.is_allowed_origin("null", None, ["http://127.0.0.1:8000"]))

if __name__ == "__main__":
    unittest.main()
