# -*- coding: utf-8 -*-
"""Aplicacao WSGI (CR-021d1b): caminho, rota, hooks, action, sessao e resposta.

Nao conhece regra de negocio: quem liga a aplicacao (CR-021e) passa o ``resolver`` das actions, os
hooks ``before`` (guardas, CSRF) e ``after`` (cabecalhos de seguranca, que rodam em toda resposta
dinamica, inclusive de erro), o ``renderer`` das views e a ``error_page``. Erro inesperado vira 500
com um id de ocorrencia: o stack trace vai so para o log (AGENTS §6), nunca para o corpo.
"""
import html
import logging
import uuid
from typing import (Any, Callable, Iterable, Iterator, List, Mapping,
                    NamedTuple, Optional, Sequence)

from . import static
from .errors import HTTP, status_line
from .request import Request
from .response import Response
from .routing import (InvalidPath, Route, StaticRoute, decode_path_info,
                      parse_path)
from .session import COOKIE_NAME, Session, SessionCodec, connect

Context = NamedTuple("Context", [("request", Request), ("response", Response),
                                 ("session", Session), ("route", Route)])
Action = Callable[[Context], Any]
Hook = Callable[[Context], None]
StartResponse = Callable[..., Any]

Settings = NamedTuple("Settings", [
    ("application", str),
    ("static_dir", str),
    ("max_body_bytes", int),
    ("session_codec", SessionCodec),
    ("secure_cookie", Callable[[Request], bool]),
])

_HTML = "text/html; charset=utf-8"


def default_error_page(status: int, incident: Optional[str]) -> str:
    """Pagina de erro minima, sem detalhe tecnico (usada sem error_page ou se ela falhar)."""
    text = html.escape(status_line(status))
    extra = f"<p>Ocorrencia {html.escape(incident)}.</p>" if incident else ""
    return (f"<!DOCTYPE html><html lang=\"pt-BR\"><title>{text}</title>"
            f"<h1>{text}</h1>{extra}</html>")


class _ClosingBody:
    """Corpo em fluxo que, ao fechar, fecha tambem o iteravel e os uploads da requisicao."""

    def __init__(self, body: Iterable[bytes], callbacks: Sequence[Callable[[], None]]) -> None:
        self._body = body
        self._callbacks = list(callbacks)

    def __iter__(self) -> Iterator[bytes]:
        """Os blocos do corpo, convertidos para bytes."""
        for chunk in self._body:
            yield chunk.encode("utf-8") if isinstance(chunk, str) else chunk

    def close(self) -> None:
        """Chamado pelo servidor WSGI no fim (inclusive quando o cliente desiste)."""
        close = getattr(self._body, "close", None)
        for callback in ([close] if close else []) + self._callbacks:
            callback()


# Um so metodo publico de proposito: o objeto e o callable WSGI.
class Application:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """Aplicacao WSGI do SSS; os detalhes da aplicacao entram pelo construtor."""

    def __init__(  # pylint: disable=too-many-arguments
            self, settings: Settings, resolver: Callable[[Route], Optional[Action]],
            log: logging.Logger, *, before: Sequence[Hook] = (), after: Sequence[Hook] = (),
            renderer: Optional[Callable[[Context, Mapping[str, Any]], str]] = None,
            error_page: Optional[Callable[[int, Optional[str], Context], str]] = None) -> None:
        self.settings = settings
        self._resolver = resolver
        self._log = log
        self._before = list(before)
        self._after = list(after)
        self._renderer = renderer
        self._error_page = error_page
        self._cookie_path = f"/{settings.application}/"

    def __call__(self, environ: Mapping[str, Any],
                 start_response: StartResponse) -> Iterable[bytes]:
        """Ponto de entrada WSGI."""
        try:
            path = decode_path_info(str(environ.get("PATH_INFO") or "/"))
            route = parse_path(path, self.settings.application)
        except InvalidPath:
            return self._plain(404, start_response)
        if isinstance(route, StaticRoute):
            return self._static(environ, route, start_response)
        return self._dynamic(environ, route, start_response)

    # ------------------------------------------------------------------ estaticos

    def _static(self, environ: Mapping[str, Any], route: StaticRoute,
                start_response: StartResponse) -> Iterable[bytes]:
        method = str(environ.get("REQUEST_METHOD") or "GET").upper()
        headers = {"if_none_match": environ.get("HTTP_IF_NONE_MATCH"),
                   "if_modified_since": environ.get("HTTP_IF_MODIFIED_SINCE")}
        try:
            response = static.serve(self.settings.static_dir, route.path, method, headers)
        except HTTP as exc:
            return self._plain(exc.status, start_response, exc.headers)
        start_response(status_line(response.status), response.wsgi_headers())
        body = response.body
        return body if hasattr(body, "close") else [body]

    def _plain(self, status: int, start_response: StartResponse,
               headers: Optional[Mapping[str, str]] = None) -> List[bytes]:
        """Erro fora de uma action (rota invalida, estatico): pagina minima."""
        body = default_error_page(status, None).encode("utf-8")
        response = Response()
        response.headers.update(headers or {})
        response.headers.update({"Content-Type": _HTML, "Content-Length": str(len(body)),
                                 "X-Content-Type-Options": "nosniff"})
        start_response(status_line(status), response.wsgi_headers())
        return [body]

    # ------------------------------------------------------------------ actions

    def _dynamic(self, environ: Mapping[str, Any], route: Route,
                 start_response: StartResponse) -> Iterable[bytes]:
        request = Request(environ, route, self.settings.max_body_bytes)
        response = Response()
        cookie = request.cookies.get(COOKIE_NAME)
        codec = self.settings.session_codec
        session, refused, snapshot = connect(cookie.value if cookie else None, codec, response)
        if refused:
            self._log.warning("cookie de sessao recusado (motivo=%s ip=%s caminho=%s)", refused,
                              request.env.remote_addr, request.env.path_info,
                              extra={"action": "SESSAO"})
        context = Context(request, response, session, route)
        body = self._run(context)
        if response.status != 500:
            self._save_session(context, snapshot, bool(refused))
        try:
            headers = response.wsgi_headers()
        except ValueError:
            self._log.exception("cabecalho invalido na resposta (caminho=%s)",
                                request.env.path_info, extra={"action": "HTTP"})
            request.close()
            return self._plain(500, start_response)
        start_response(status_line(response.status), headers)
        if request.method == "HEAD":
            if hasattr(body, "close"):
                body.close()
            request.close()
            return [b""]
        if isinstance(body, bytes):
            request.close()
            return [body]
        return _ClosingBody(body, [request.close])

    def _run(self, context: Context) -> Any:
        """Hooks e action; devolve o corpo (bytes ou iteravel) com status e cabecalhos prontos."""
        response = context.response
        try:
            for hook in self._before:
                hook(context)
            action = self._resolver(context.route)
            if action is None:
                raise HTTP(404)
            body = self._body(context, action(context))
            self._after_hooks(context)
            return body
        except HTTP as exc:
            response.status = exc.status
            response.headers.update(exc.headers)
            self._after_hooks(context)
            # Como o routes_onerror do web2py: todo erro 400+ sai com a pagina da aplicacao;
            # o texto do HTTP (mensagem tecnica) nunca vai para o usuario.
            if exc.status >= 400:
                return self._encoded(response, self._page(exc.status, None, context))
            return self._encoded(response, exc.body)
        except Exception:  # pylint: disable=broad-except
            return self._incident(context)

    def _after_hooks(self, context: Context) -> None:
        for hook in self._after:
            hook(context)

    def _incident(self, context: Context) -> bytes:
        """Erro inesperado: id da ocorrencia, stack trace no log, pagina sem detalhe tecnico."""
        incident = uuid.uuid4().hex[:12]
        request = context.request
        self._log.exception("erro inesperado (ocorrencia=%s metodo=%s caminho=%s)", incident,
                            request.method, request.env.path_info, extra={"action": "HTTP"})
        response = context.response
        response.status = 500
        response.headers.clear()
        response.cookies.clear()
        try:
            self._after_hooks(context)
        except Exception:  # pylint: disable=broad-except
            self._log.exception("hook after falhou no erro 500 (ocorrencia=%s)", incident,
                                extra={"action": "HTTP"})
        return self._encoded(response, self._page(500, incident, context))

    def _page(self, status: int, incident: Optional[str], context: Context) -> str:
        if self._error_page is None:
            return default_error_page(status, incident)
        try:
            return self._error_page(status, incident, context)
        except Exception:  # pylint: disable=broad-except
            self._log.exception("pagina de erro falhou (status=%d)", status,
                                extra={"action": "HTTP"})
            return default_error_page(status, incident)

    def _body(self, context: Context, result: Any) -> Any:
        """Converte o retorno da action: texto, bytes, dict (view), None ou iteravel em fluxo."""
        response = context.response
        if isinstance(result, dict):
            if self._renderer is None:
                raise TypeError("action devolveu dict sem renderer configurado")
            return self._encoded(response, self._renderer(context, result))
        if result is None or isinstance(result, (str, bytes)):
            return self._encoded(response, result or b"")
        if hasattr(result, "__iter__"):
            response.headers.setdefault("Content-Type", "application/octet-stream")
            return result
        raise TypeError(f"retorno de action nao suportado: {type(result).__name__}")

    @staticmethod
    def _encoded(response: Response, text: Any) -> bytes:
        data = text.encode("utf-8") if isinstance(text, str) else bytes(text)
        response.headers.setdefault("Content-Type", _HTML)
        response.headers["Content-Length"] = str(len(data))
        return data

    def _save_session(self, context: Context, snapshot: str, refused: bool) -> None:
        """Regrava o cookie so quando a sessao mudou (ou para trocar um cookie recusado)."""
        value = self.settings.session_codec.dumps(context.session)
        if value != snapshot or refused:
            context.response.set_cookie(COOKIE_NAME, value, path=self._cookie_path,
                                        secure=self.settings.secure_cookie(context.request))
