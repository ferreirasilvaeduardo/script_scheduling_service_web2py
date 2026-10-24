# -*- coding: utf-8 -*-
"""Nucleo web proprio do SSS (CR-021d1), no lugar do web2py.

So a biblioteca padrao. Nao conhece regra de negocio: CSRF, guardas e cabecalhos de seguranca da
aplicacao entram por hooks (CR-021e). Nenhum modulo daqui importa gluon nem le request/session
globais.
"""
from .errors import HTTP, redirect
from .multipart import Limits, UploadedFile
from .request import Request
from .response import Response, json_for_html
from .routing import InvalidPath, Route, StaticRoute, parse_path, url
from .session import Session, SessionCodec, connect
from .storage import Storage

__all__ = [
    "HTTP", "InvalidPath", "Limits", "Request", "Response", "Route", "Session", "SessionCodec",
    "StaticRoute", "Storage", "UploadedFile", "connect", "json_for_html", "parse_path", "redirect",
    "url",
]
