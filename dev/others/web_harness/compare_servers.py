# -*- coding: utf-8 -*-
"""Paridade de HTML entre dois servidores do SSS com o backend FAKE (somente DEV, CR-021e).

Uso: SSS_DEV_SEED_PASSWORD=<senha> python dev/others/web_harness/compare_servers.py <url_referencia> <url_nova>

Cada URL e a raiz da aplicacao (ex.: http://127.0.0.1:8791/script_scheduling_service). Entra como
admin, op.prod e consulta nos dois, busca as mesmas paginas GET e compara o HTML (sem o token CSRF e
sem carimbos de hora, que mudam a cada requisicao) e os cabecalhos de seguranca. Saida 0 se tudo for
igual; 1 com o diff de cada diferenca.
"""
import difflib
import http.cookiejar
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

USERS = ("admin", "op.prod", "consulta")
# Paginas GET com os IDs do seed FAKE (perfil 2, script 1, ticket 17, ambiente PRODUCAO).
PAGES = (
    "/default/index", "/default/permissions", "/default/my_password", "/tickets/catalog",
    "/tickets/index", "/tickets/index?status=RUNNING", "/tickets/detail/17", "/tickets/detail/3",
    "/tickets/new?script_id=1&environment=PRODUCAO", "/tickets/history/1", "/schedules/index",
    "/schedules/form", "/schedules/form?script_id=1&environment=PRODUCAO", "/audit/index",
    "/audit/agents", "/outputs/index", "/outputs/index?environment=PRODUCAO", "/inputs/index",
    "/inputs/index?environment=PRODUCAO&script_id=1", "/admin_users/index", "/admin_users/form",
    "/admin_users/form/2", "/admin_profiles/index", "/admin_profiles/form/2",
    "/admin_profiles/matrix/2", "/admin_environments/index", "/admin_environments/form/1",
    "/admin_scripts/index", "/admin_scripts/form/1", "/admin_scripts/homologation/1",
    "/admin_scripts/parameters/1", "/admin_parameters/index", "/admin_parameters/form",
    "/dev/shell", "/dev/components", "/default/nada_aqui", "/tickets/detail/999999",
)
# Unica diferenca aceita (CR-021d2): o template do web2py descartava o include de um arquivo que o
# layout tambem inclui, e a vitrine de DEV saia sem os alertas de demonstracao; o motor novo os
# mostra. Aceita so se o servidor novo apenas ACRESCENTA blocos de alerta (e espacos).
KNOWN_ALERT_PAGES = ("/dev/components",)
_ALERT_LINE = re.compile(r'^\s*(<div class="alert [^"]*" role="(status|alert)">|<svg class="sss-icon"'
                         r'.*</svg>|<span>.*</span>|</div>)?\s*$')
HEADERS = ("Content-Type", "Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options",
           "Referrer-Policy", "Cache-Control")
_VOLATILE = (
    (re.compile(r'(name="_csrf" type="hidden" value=")[^"]*"'), r'\1CSRF"'),
    (re.compile(r'(<meta name="csrf-token" content=")[^"]*"'), r'\1CSRF"'),
    (re.compile(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}(:\d{2})?"), "DATA-HORA"),
    (re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?"), "DATA-HORA"),
    (re.compile(r"\b\d{2}:\d{2}:\d{2}\b"), "HORA"),
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # pylint: disable=arguments-differ
        return None


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                       _NoRedirect())


def _get(opener: urllib.request.OpenerDirector, url: str) -> Tuple[int, Dict[str, str], str]:
    try:
        with opener.open(url, timeout=30) as reply:
            return reply.status, dict(reply.headers), reply.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read().decode("utf-8", "replace")


def _login(base: str, user: str, password: str) -> urllib.request.OpenerDirector:
    opener = _opener()
    _status, _headers, page = _get(opener, base + "/default/login")
    token = re.search(r'name="_csrf" type="hidden" value="([^"]+)"', page)
    if token is None:
        raise SystemExit(f"{base}: pagina de login sem token CSRF")
    data = urllib.parse.urlencode({"_csrf": token.group(1), "login": user,
                                   "password": password}).encode()
    request = urllib.request.Request(base + "/default/login", data=data,
                                     headers={"Origin": urllib.parse.urlsplit(base)._replace(
                                         path="").geturl()})
    status, _headers, _body = _get_request(opener, request)
    if status != 303:
        raise SystemExit(f"{base}: login de {user} falhou (status {status})")
    return opener


def _get_request(opener: urllib.request.OpenerDirector,
                 request: urllib.request.Request) -> Tuple[int, Dict[str, str], str]:
    try:
        with opener.open(request, timeout=30) as reply:
            return reply.status, dict(reply.headers), reply.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read().decode("utf-8", "replace")


def _normalized(text: str) -> str:
    for pattern, replacement in _VOLATILE:
        text = pattern.sub(replacement, text)
    return text


def _only_added_alerts(old_text: str, new_text: str) -> bool:
    """True se a versao nova so acrescenta blocos de alerta e espacos a referencia."""
    for line in difflib.ndiff(old_text.splitlines(), new_text.splitlines()):
        if line.startswith("- ") and line[2:].strip():
            return False
        if line.startswith("+ ") and not _ALERT_LINE.match(line[2:]):
            return False
    return True


def compare(reference: str, new: str, password: str) -> List[str]:
    """Diferencas encontradas, uma entrada por pagina e usuario."""
    problems = []
    for user in USERS:
        old_opener, new_opener = _login(reference, user, password), _login(new, user, password)
        for page in PAGES:
            old_status, old_headers, old_body = _get(old_opener, reference + page)
            new_status, new_headers, new_body = _get(new_opener, new + page)
            where = f"{user} {page}"
            if old_status != new_status:
                problems.append(f"{where}: status {old_status} != {new_status}")
            for name in HEADERS:
                if old_headers.get(name) != new_headers.get(name):
                    problems.append(f"{where}: cabecalho {name}: {old_headers.get(name)!r} != "
                                    f"{new_headers.get(name)!r}")
            old_text, new_text = _normalized(old_body), _normalized(new_body)
            if page in KNOWN_ALERT_PAGES and _only_added_alerts(old_text, new_text):
                continue
            if old_text != new_text:
                diff = difflib.unified_diff(old_text.splitlines(), new_text.splitlines(),
                                            "referencia", "nova", lineterm="", n=1)
                problems.append(f"{where}: HTML diferente\n" + "\n".join(list(diff)[:40]))
    return problems


def main(argv: Optional[List[str]] = None) -> int:
    """Compara as paginas e imprime o resultado."""
    args = sys.argv[1:] if argv is None else argv
    password = os.environ.get("SSS_DEV_SEED_PASSWORD")
    if len(args) != 2 or not password:
        sys.stderr.write(__doc__)
        return 2
    problems = compare(args[0].rstrip("/"), args[1].rstrip("/"), password)
    for problem in problems:
        print(problem)
    print(f"\n{len(USERS) * len(PAGES)} paginas comparadas, {len(problems)} diferenca(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
