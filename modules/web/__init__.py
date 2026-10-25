# -*- coding: utf-8 -*-
"""Nucleo web proprio do SSS (CR-021d1), no lugar do web2py.

So a biblioteca padrao. Nao conhece regra de negocio: CSRF, guardas e cabecalhos de seguranca da
aplicacao entram por hooks (CR-021e). Nenhum modulo daqui importa gluon nem le request/session
globais.
"""
from .app import Application, Context, Settings
from .errors import HTTP, redirect
from .markup import Markup, escape
from .multipart import Limits, UploadedFile
from .request import Request
from .response import Response, json_for_html
from .routing import (InvalidPath, Route, StaticRoute, decode_path_info,
                      parse_path, url)
from .server import make_server, serve
from .session import Session, SessionCodec, connect
from .storage import Storage
from .template import TemplateError, Templates

__all__ = [
    "Application", "Context", "HTTP", "InvalidPath", "Limits", "Markup", "Request", "Response",
    "Route", "Session", "SessionCodec", "Settings", "StaticRoute", "Storage", "TemplateError",
    "Templates", "UploadedFile", "connect", "decode_path_info", "escape", "json_for_html",
    "make_server", "parse_path", "redirect", "serve", "url",
]
