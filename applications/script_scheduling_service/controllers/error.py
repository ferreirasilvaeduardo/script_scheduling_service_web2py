# -*- coding: utf-8 -*-
"""Pagina generica de erro via routes_onerror: o reprocessamento roda os models, que aplicam os cabecalhos."""

import ui_helpers

# Mensagens em duas partes (README §2.4.2): o que aconteceu + o que fazer agora.
_MESSAGES = {
    400: (u"O pedido enviado não é válido.", u"Volte à página anterior e tente de novo."),
    403: ui_helpers.message_parts("no_permission"),
    404: ui_helpers.message_parts("not_found"),
    405: (u"Esta página não aceita esse tipo de pedido.", u"Volte à página anterior e use os botões da tela."),
}


def index():
    if not request.env.get("__routes_onerror__"):
        raise HTTP(404)
    code = request.env.web2py_status_code
    if not isinstance(code, int) or not 400 <= code <= 599:
        code = 500
    response.status = code
    response.view = "error/index.html"
    return dict(
        code=code,
        happened=_MESSAGES.get(code, ui_helpers.message_parts("internal_error"))[0],
        todo=_MESSAGES.get(code, ui_helpers.message_parts("internal_error"))[1],
        permissions=code == 403,
    )
