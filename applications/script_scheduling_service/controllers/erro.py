# -*- coding: utf-8 -*-
"""Pagina generica de erro via routes_onerror: o reprocessamento roda os models, que aplicam os cabecalhos."""

import ui_helpers

# Mensagens em duas partes (README §2.4.2): o que aconteceu + o que fazer agora.
_MENSAGENS = {
    400: (u"O pedido enviado não é válido.", u"Volte à página anterior e tente de novo."),
    403: ui_helpers.mensagem_partes("sem_permissao"),
    404: ui_helpers.mensagem_partes("nao_encontrado"),
    405: (u"Esta página não aceita esse tipo de pedido.", u"Volte à página anterior e use os botões da tela."),
}


def index():
    if not request.env.get("__routes_onerror__"):
        raise HTTP(404)
    codigo = request.env.web2py_status_code
    if not isinstance(codigo, int) or not 400 <= codigo <= 599:
        codigo = 500
    response.status = codigo
    response.view = "erro/index.html"
    return dict(
        codigo=codigo,
        aconteceu=_MENSAGENS.get(codigo, ui_helpers.mensagem_partes("falha_interna"))[0],
        fazer=_MENSAGENS.get(codigo, ui_helpers.mensagem_partes("falha_interna"))[1],
        permissoes=codigo == 403,
    )
