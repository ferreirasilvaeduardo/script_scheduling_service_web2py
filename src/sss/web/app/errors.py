# -*- coding: utf-8 -*-
"""Pagina de erro da aplicacao (CR-021e): era o controllers/error.py chamado pelo routes_onerror.

Mensagem em duas partes (README §2.4.2): o que aconteceu e o que fazer agora. No 500, o id da
ocorrencia aparece para o suporte achar o erro no log (o stack trace nunca vai para a pagina).
"""
from typing import Any, Callable, Dict, Optional

from sss.ui import ui_helpers
from sss.web.framework import Context

_MESSAGES = {
    400: ("O pedido enviado não é válido.", "Volte à página anterior e tente de novo."),
    403: ui_helpers.message_parts("no_permission"),
    404: ui_helpers.message_parts("not_found"),
    405: ("Esta página não aceita esse tipo de pedido.",
          "Volte à página anterior e use os botões da tela."),
}


def page_data(status: int, incident: Optional[str]) -> Dict[str, Any]:
    """Variaveis da view error/index.html para o ``status``."""
    happened, todo = _MESSAGES.get(status, ui_helpers.message_parts("internal_error"))
    return {"code": status, "happened": happened, "todo": todo, "permissions": status == 403,
            "incident": incident}


def make_error_page(render: Callable[[Context, str, Dict[str, Any]], str]
                    ) -> Callable[[int, Optional[str], Context], str]:
    """Pagina de erro para o Application, renderizada pela view error/index.html."""
    def error_page(status: int, incident: Optional[str], ctx: Context) -> str:
        return render(ctx, "error/index.html", page_data(status, incident))
    return error_page
