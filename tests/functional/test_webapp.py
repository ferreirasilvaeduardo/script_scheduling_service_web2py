# -*- coding: utf-8 -*-
"""Camada web da aplicacao (CR-021e): URL, registro e rotas expostas, hooks de seguranca e csrf_field.

As saidas esperadas do URL e do campo CSRF sao as do web2py, gravadas antes de o gluon sair do
repositorio (CR-021f1).
"""
import io
import logging
import os
import sys
import types
import unittest
from unittest import mock

from tests.support import _testenv  # noqa: F401 - ajusta sys.path (src/ e a raiz da aplicacao)

APP_DIR = _testenv.APP_DIR
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from sss.config import app_context  # noqa: E402
from sss.web.framework import HTTP, Context, Markup, Request, Response, Route, Session  # noqa: E402

from sss.web.app import bootstrap, context, security  # noqa: E402

LOG = logging.getLogger("sss_test_webapp")
LOG.addHandler(logging.NullHandler())
LOG.propagate = False


def _context(controller="tickets", function="index", extension="html", method="GET", body=b"",
             **environ):
    env = {"REQUEST_METHOD": method, "QUERY_STRING": "", "wsgi.input": io.BytesIO(body),
           "CONTENT_LENGTH": str(len(body)), "CONTENT_TYPE": "application/x-www-form-urlencoded",
           "wsgi.url_scheme": "http", "REMOTE_ADDR": "10.0.0.1",
           "PATH_INFO": "/%s/%s/%s" % (context.APPLICATION, controller, function)}
    env.update(environ)
    route = Route(controller, function, extension, [])
    return Context(Request(env, route, 1 << 20), Response(), Session(), route)


class UrlTest(unittest.TestCase):
    """URL da aplicacao: mesmas regras do web2py, Markup seguro."""

    # Saida do gluon.html.URL do web2py numa requisicao tickets/index; {ext} e '' em html e '.load'
    # numa requisicao .load (estatico e extension=False nunca levam extensao).
    CASES = (
        (("static", "img/icons.svg"), {}, "/script_scheduling_service/static/img/icons.svg"),
        (("dev", "components"), {}, "/script_scheduling_service/dev/components{ext}"),
        (("detail",), {}, "/script_scheduling_service/tickets/detail{ext}"),
        ((), dict(c="default", f="index"), "/script_scheduling_service/default/index{ext}"),
        ((), dict(c="tickets", f="detail", args=[17]), "/script_scheduling_service/tickets/detail{ext}/17"),
        ((), dict(c="tickets", f="index", vars={"page": 2, "status": ["A", "B"]}, anchor="x"),
         "/script_scheduling_service/tickets/index{ext}?page=2&status=A&status=B#x"),
        ((), dict(c="tickets", f="detail", args=[1], extension=False),
         "/script_scheduling_service/tickets/detail/1"),
    )

    def test_parity_with_web2py(self):
        """Posicionais, keywords e extensao herdada da requisicao, iguais ao gluon.html.URL."""
        for extension in ("html", "load"):
            context.bind(_context(extension=extension))
            suffix = "" if extension == "html" else "." + extension
            for args, kwargs, expected in self.CASES:
                with self.subTest(extension=extension, args=args, kwargs=kwargs):
                    self.assertEqual(context.URL(*args, **kwargs), expected.format(ext=suffix))

    def test_markup_is_safe_with_hostile_input(self):
        """Markup (como o SafeString do web2py), sem nada que exija escape nas partes variaveis."""
        context.bind(_context())
        hostile = '"><script>alert(1)</script>\'&#'
        value = context.URL(c="tickets", f="detail", args=[hostile], vars={hostile: hostile},
                            anchor=hostile)
        self.assertIsInstance(value, Markup)
        for char in '<>"\'':
            self.assertNotIn(char, value)
        self.assertEqual(value.count("#"), 1, "so o separador da ancora")

    def test_names_out_of_format_are_refused(self):
        """Controller, funcao ou caminho estatico fora do formato: ValueError (nunca Markup)."""
        context.bind(_context())
        cases = (
            (("static", "../x.js"), {}),
            (("static", 'a"b.js'), {}),
            ((), {"c": "Tickets", "f": "index"}),
            ((), {"c": "tickets", "f": "in dex"}),
            (("outra_app", "c", "f"), {}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs):
                with self.assertRaises(ValueError):
                    context.URL(*args, **kwargs)


class RegistryTest(unittest.TestCase):
    """Registro dos controllers e rotas expostas."""

    @staticmethod
    def _cfg():
        return types.SimpleNamespace(app=types.SimpleNamespace(name="web0001"))

    def test_registry_matches_files(self):
        """Todo controllers/*.py esta no registro, o dev inclusive quando o arquivo existe (CR-032, D11)."""
        files = {name[:-3] for name in os.listdir(os.path.join(_testenv.WEB_DIR, "controllers"))
                 if name.endswith(".py") and name != "__init__.py"}
        self.assertEqual(set(bootstrap.controllers(self._cfg())), files)

    def test_dev_without_file_is_not_registered(self):
        """Instalado pelo pacote (sem controllers/dev.py): o servidor sobe sem a rota dev."""
        with mock.patch.object(bootstrap, "DEV_CONTROLLER", os.path.join(APP_DIR, "nao_existe.py")):
            self.assertNotIn("dev", bootstrap.controllers(self._cfg()))

    def test_cr032_dev_screen_and_dev_marks(self):
        """CR-032 (D11): a tela /dev responde 404 sem a pasta dev/; o layout marca o DEV pelo <TIPO>
        (titulo [DEV] e cabecalho sss-header-dev), sem depender de sss_env (revisao do CR-032, achado 14)."""
        from sss.web.controllers import dev  # pylint: disable=import-outside-toplevel
        from sss.config import sss_config  # pylint: disable=import-outside-toplevel
        with mock.patch.object(sss_config, "has_dev_dir", return_value=False):
            with self.assertRaises(HTTP) as raised:
                dev._require_dev()
        self.assertEqual(raised.exception.status, 404)
        with mock.patch.object(sss_config, "has_dev_dir", return_value=True):
            self.assertIsNone(dev._require_dev())
        with open(os.path.join(_testenv.WEB_DIR, "templates", "layout.html"), encoding="utf-8") as f:
            layout = f.read()
        self.assertIn("{{if response.env_label == 'DEV':}}[DEV] {{pass}}", layout)
        self.assertIn("sss-header{{if response.env_label == 'DEV':}} sss-header-dev{{pass}}", layout)
        self.assertNotIn("sss_env", layout)

    def test_only_module_functions_are_actions(self):
        """Nome importado (redirect, URL, HTTP, guardas) nunca vira rota; privada e com parametro tambem nao."""
        registry = bootstrap.controllers(self._cfg())
        imported = {"redirect", "URL", "HTTP", "request", "response", "session"}
        for name, module in registry.items():
            exposed = bootstrap.actions(module)
            with self.subTest(controller=name):
                self.assertTrue(exposed, "controller sem action")
                self.assertFalse(imported & set(exposed))
                self.assertFalse([a for a in exposed if a.startswith("_")])
                for function in exposed.values():
                    self.assertEqual(function.__module__, module.__name__)

    def test_resolver(self):
        """Rota conhecida devolve a action sem argumentos; desconhecida, None."""
        with mock.patch.object(bootstrap, "DEV_CONTROLLER", os.path.join(APP_DIR, "nao_existe.py")):
            resolve = bootstrap.make_resolver(bootstrap.controllers(self._cfg()))
        self.assertIsNone(resolve(Route("default", "redirect", "html", [])))
        self.assertIsNone(resolve(Route("dev", "shell", "html", [])), "pacote sem controllers/dev.py")
        self.assertIsNone(resolve(Route("nada", "index", "html", [])))
        self.assertTrue(callable(resolve(Route("default", "login", "html", []))))


class SecurityHooksTest(unittest.TestCase):
    """Hooks de seguranca sem banco (sessao sem login)."""

    def setUp(self):
        previous = app_context.get_config()
        self.addCleanup(app_context.set_config, previous)
        self.cfg = types.SimpleNamespace(
            app=types.SimpleNamespace(name="web0001"),
            web=types.SimpleNamespace(input_upload_max_bytes=1000, files_upload_max_bytes=5000,
                                      allowed_origins=("https://sss",),
                                      trusted_proxies=(), session_idle_timeout_s=1800,
                                      session_max_hours=12))
        app_context.set_config(self.cfg)
        patcher = mock.patch.object(security, "log", return_value=LOG)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_headers_on_every_response(self):
        """after_request aplica CSP e os demais cabecalhos; sem usuario, sem no-store."""
        ctx = _context()
        security.before_request(ctx)
        security.after_request(ctx)
        for name, value in security.SECURITY_HEADERS.items():
            self.assertEqual(ctx.response.headers[name], value)
        self.assertNotIn("Cache-Control", ctx.response.headers)
        self.assertTrue(ctx.session.csrf_token, "token CSRF criado na primeira visita")
        from sss.config import sss_config  # pylint: disable=import-outside-toplevel
        self.assertEqual(ctx.response.sss_version, sss_config.SSS_VERSION, "rodape com a versao do pacote")
        self.assertEqual(ctx.response.env_label, sss_config.env_label(), "CR-028 (D12): faixa e rodape")

    def test_post_size_origin_and_csrf(self):
        """POST acima do limite: 413; Origin de fora: 403; token errado ou ausente: 403; certo passa."""
        ctx = _context(method="POST", CONTENT_LENGTH=str(1000 + security.POST_MARGIN_BYTES + 1))
        with self.assertRaises(HTTP) as raised:
            security.before_request(ctx)
        self.assertEqual(raised.exception.status, 413)
        for origin, token, status in (("https://outro", "t", 403), ("https://sss", "x", 403),
                                      ("https://sss", "", 403), ("https://sss", "t", None)):
            with self.subTest(origin=origin, token=token):
                ctx = _context(method="POST", body=("_csrf=%s" % token).encode(), HTTP_ORIGIN=origin)
                ctx.session.csrf_token = "t"
                if status is None:
                    security.before_request(ctx)
                    continue
                with self.assertRaises(HTTP) as raised:
                    security.before_request(ctx)
                self.assertEqual(raised.exception.status, status)

    def test_cr037_limite_grande_so_no_envio_da_pasta_de_arquivos(self):
        """CR-037 (D6): files/upload aceita files_upload_max_bytes; qualquer outra rota, o da Entrada."""
        margin = security.POST_MARGIN_BYTES
        self.assertEqual(security.max_body_bytes(), 5000 + margin)
        self.assertEqual(security.body_limit("files", "upload"), 5000 + margin)
        self.assertEqual(security.body_limit("inputs", "upload"), 1000 + margin)
        self.assertEqual(security.body_limit("default", "login"), 1000 + margin)
        self.assertEqual(security.body_limit("files", "upload", logged=False), 1000 + margin,
                         "sem login, o envio grande nem chega a ser lido (revisao do CR-037)")
        ctx = _context(controller="default", function="login", method="POST",
                       CONTENT_LENGTH=str(1000 + margin + 1))
        with self.assertRaises(HTTP) as raised:
            security.before_request(ctx)
        self.assertEqual(raised.exception.status, 413, "login nao herda o limite grande")
        ctx = _context(controller="files", function="upload", method="POST",
                       CONTENT_LENGTH=str(1000 + margin + 1))
        with self.assertRaises(HTTP) as raised:
            security.before_request(ctx)
        self.assertEqual(raised.exception.status, 413, "sem sessao logada: o limite da Entrada")
        logged = _context(controller="files", function="upload", method="POST",
                          CONTENT_LENGTH=str(1000 + margin + 1))
        logged.session.user_id = 7
        with mock.patch.object(security, "_revalidate"), self.assertRaises(HTTP) as raised:
            security.before_request(logged)
        self.assertEqual(raised.exception.status, 403, "logado: passa do tamanho e para no CSRF")
        ctx = _context(controller="files", function="upload", method="POST",
                       CONTENT_LENGTH=str(5000 + margin + 1))
        with self.assertRaises(HTTP) as raised:
            security.before_request(ctx)
        self.assertEqual(raised.exception.status, 413)
        self.assertEqual(security.upload_dir(self.cfg), os.path.join(
            security.sss_config.VAR_DIR, "web0001", "tmp"))

    def test_cr032_own_host_origin_and_secure_cookie_only_on_https(self):
        """CR-032 (D11): o proprio Host vale como origem, e o cookie e Secure so sob HTTPS, em DEV e PROD."""
        ctx = _context(method="POST", body=b"_csrf=t", HTTP_ORIGIN="http://sss-dev:18000", HTTP_HOST="sss-dev:18000")
        ctx.session.csrf_token = "t"
        security.before_request(ctx)
        ctx = _context(method="POST", body=b"_csrf=t", HTTP_ORIGIN="http://outro:18000", HTTP_HOST="sss-dev:18000")
        ctx.session.csrf_token = "t"
        with self.assertRaises(HTTP) as raised:
            security.before_request(ctx)
        self.assertEqual(raised.exception.status, 403)
        self.assertFalse(security.secure_cookie(types.SimpleNamespace(is_https=False)))
        self.assertTrue(security.secure_cookie(types.SimpleNamespace(is_https=True)))

    def test_csrf_header_for_fetch(self):
        """fetch manda o token no X-CSRF-Token (sem corpo de formulario)."""
        ctx = _context(method="POST", body=b"{}", CONTENT_TYPE="application/json",
                       HTTP_ORIGIN="https://sss", HTTP_X_CSRF_TOKEN="t")
        ctx.session.csrf_token = "t"
        security.before_request(ctx)

    def test_csrf_field_like_web2py(self):
        """Mesmo HTML do INPUT do web2py, com o token escapado, e como Markup."""
        ctx = _context()
        context.bind(ctx)
        ctx.session.csrf_token = 'a"b<c'
        field = security.csrf_field()
        self.assertIsInstance(field, Markup)
        # Saida do INPUT(_type="hidden", _name="_csrf", _value='a"b<c').xml() do web2py.
        self.assertEqual(field, '<input name="_csrf" type="hidden" value="a&quot;b&lt;c" />')

    def test_guards_without_login(self):
        """Sem usuario: require_login manda ao login (303) com next; text pega o ultimo valor."""
        ctx = _context(controller="tickets", function="index", QUERY_STRING="page=2")
        security.before_request(ctx)
        with self.assertRaises(HTTP) as raised:
            security.require_login()
        self.assertEqual(raised.exception.status, 303)
        self.assertIn("next=%2Fscript_scheduling_service%2Ftickets%2Findex%3Fpage%3D2",
                      raised.exception.headers["Location"])
        self.assertEqual(security.text(["a", "bcdef"], 3), "bcd")
        self.assertIsNone(security.text(None, 3))


class RunWebCheckTest(unittest.TestCase):
    """scripts/run_web.py --check: confere a configuracao sem abrir a porta (CR-021e2)."""

    def setUp(self):
        from sss.cli import run_web  # pylint: disable=import-outside-toplevel
        self.run_web = run_web
        cfg = types.SimpleNamespace(app=types.SimpleNamespace(name="web0001"))
        for name, value in (("load_config", mock.Mock(return_value=cfg)),
                            ("make_app", mock.Mock())):
            patcher = mock.patch.object(run_web.bootstrap, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(run_web, "make_server")
        self.make_server = patcher.start()
        self.addCleanup(patcher.stop)

    def test_check_prints_ok_and_never_opens_the_port(self):
        """Configuracao valida: CONFIG_OK com o ambiente, saida 0, make_server nunca chamado."""
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(self.run_web.main(["--check", "--config", "x.ini"]), 0)
        self.assertEqual(out.getvalue().strip(), "CONFIG_OK ambiente=%s" % self.run_web.sss_config.env_label())
        self.run_web.bootstrap.load_config.assert_called_once_with("x.ini")
        self.make_server.assert_not_called()

    def test_check_with_invalid_config(self):
        """Configuracao invalida: saida 2, sem CONFIG_OK."""
        self.run_web.bootstrap.load_config.side_effect = self.run_web.sss_config.ConfigError("x")
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(self.run_web.main(["--check"]), self.run_web.EXIT_CONFIG)
        self.assertNotIn("CONFIG_OK", out.getvalue())
        self.make_server.assert_not_called()


if __name__ == "__main__":
    unittest.main()
