# -*- coding: utf-8 -*-
"""Pagina generica de erro via routes_onerror: o reprocessamento roda os models, que aplicam os cabecalhos."""

_MENSAGENS = {
    400: u"A requisição é inválida.",
    403: u"Requisição recusada. Recarregue a página e tente novamente.",
    404: u"A página solicitada não existe.",
    405: u"Método não permitido para esta página.",
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
        mensagem=_MENSAGENS.get(codigo, u"Não foi possível concluir a operação. Tente novamente em instantes."),
    )
