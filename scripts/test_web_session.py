# -*- coding: utf-8 -*-
"""Sessao em cookie assinado (CR-021, D1): ida e volta, ataques ao cookie e o flash como no web2py."""
import base64
import json
import unittest

import _testenv  # noqa: F401 - ajusta sys.path sem importar gluon
from web.response import Response
from web.session import MAX_COOKIE_BYTES, Session, SessionCodec, connect

KEY = "chave-de-teste-com-mais-de-16-caracteres"
DATA = {"user_id": 2, "login": "op.prod", "profile_id": 2, "perm_version": 1, "session_epoch": 3,
        "csrf_token": "tok", "login_at": 1729770000.5, "last_access": 1729770100.25}


def _b64(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


class RoundTripTest(unittest.TestCase):
    """Gravar e ler de volta."""

    def test_round_trip(self):
        """O que foi gravado volta igual, com o formato v1.<payload>.<assinatura>."""
        codec = SessionCodec(KEY)
        value = codec.dumps(DATA)
        self.assertEqual(value.count("."), 2)
        self.assertTrue(value.startswith("v1."))
        session, reason = codec.loads(value)
        self.assertEqual((dict(session), reason), (DATA, None))

    def test_no_cookie_is_empty_session_without_reason(self):
        """Sem cookie: sessao vazia e nenhum motivo (nao e ataque)."""
        self.assertEqual(SessionCodec(KEY).loads(None), (Session(), None))

    def test_short_key_is_refused(self):
        """cookie_key curto demais nao serve."""
        with self.assertRaises(ValueError):
            SessionCodec("curta")

    def test_oversized_session_is_a_programming_error(self):
        """Sessao maior que o cookie aguenta: ValueError ao gravar (nunca um cookie cortado)."""
        with self.assertRaises(ValueError):
            SessionCodec(KEY).dumps({"x": "a" * MAX_COOKIE_BYTES})


class AttackTest(unittest.TestCase):
    """Cookie forjado, adulterado ou estranho vira sessao vazia, com o motivo."""

    def setUp(self):
        self.codec = SessionCodec(KEY)
        self.value = self.codec.dumps(DATA)

    def test_tampered_payload(self):
        """Trocar o login no payload sem refazer a assinatura: recusado."""
        _version, _payload, signature = self.value.split(".")
        forged = dict(DATA, login="admin", user_id=1)
        payload = _b64(json.dumps(forged, sort_keys=True, separators=(",", ":")).encode())
        self.assertEqual(self.codec.loads("v1.%s.%s" % (payload, signature))[1], "assinatura")

    def test_signed_with_other_key(self):
        """Cookie assinado com outra chave (outro ambiente ou chave vazada antiga): recusado."""
        other = SessionCodec(KEY + "-outra").dumps(DATA)
        self.assertEqual(self.codec.loads(other)[1], "assinatura")

    def test_raw_cookie_key_is_not_the_signing_key(self):
        """Assinar com o cookie_key cru (sem a derivacao) nao passa: a chave do cookie e derivada."""
        import hashlib
        import hmac
        payload = _b64(json.dumps(DATA).encode())
        signature = _b64(hmac.new(KEY.encode(), ("v1.%s" % payload).encode(), hashlib.sha256).digest())
        self.assertEqual(self.codec.loads("v1.%s.%s" % (payload, signature))[1], "assinatura")

    def test_malformed_values(self):
        """Versao, partes, tamanho e assinatura vazia: recusados com o motivo."""
        cases = (("v2" + self.value[2:], "versao"), (self.value + ".x", "versao"), ("abc", "versao"),
                 ("v1.x." + "y" * MAX_COOKIE_BYTES, "tamanho"), (self.value.rsplit(".", 1)[0] + ".", "assinatura"),
                 (self.value[:-1] + ("A" if self.value[-1] != "A" else "B"), "assinatura"))
        for value, reason in cases:
            with self.subTest(reason=reason, value=value[:30]):
                session, got = self.codec.loads(value)
                self.assertEqual((dict(session), got), ({}, reason))

    def test_validly_signed_non_object_is_refused(self):
        """Assinatura certa sobre algo que nao e objeto JSON (so com a chave): recusado como conteudo."""
        payload = _b64(b"[1,2,3]")
        signature = self.codec._signature(payload)
        self.assertEqual(self.codec.loads("v1.%s.%s" % (payload, signature))[1], "conteudo")


class ConnectTest(unittest.TestCase):
    """Abertura da sessao na requisicao."""

    def test_flash_moves_to_response_like_web2py(self):
        """session.flash vai para response.flash e sai da sessao.

        Regressao do CR-021d1b: o retrato e do cookie como chegou (com o flash), para a sessao sem o
        flash ser diferente dele e o cookie ser regravado; antes o flash voltava a cada pagina.
        """
        codec = SessionCodec(KEY)
        response = Response()
        received = codec.dumps(dict(DATA, flash={"kind": "success", "message": "ok"}))
        session, reason, snapshot = connect(received, codec, response)
        self.assertEqual(response.flash, {"kind": "success", "message": "ok"})
        self.assertNotIn("flash", session)
        self.assertEqual((reason, snapshot), (None, received))
        self.assertNotEqual(codec.dumps(session), snapshot, "a sessao mudou: o cookie sera regravado")

    def test_renew_with_clear(self):
        """renew(clear_session=True) esvazia, como o web2py com sessao em cookie; sem clear, mantem."""
        session = Session(DATA)
        session.renew()
        self.assertEqual(dict(session), DATA)
        session.renew(clear_session=True)
        self.assertEqual(dict(session), {})


if __name__ == "__main__":
    unittest.main()
