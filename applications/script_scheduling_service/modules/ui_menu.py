# -*- coding: utf-8 -*-
"""Navegacao derivada das funcionalidades do perfil (README §4.3.D).

Funcao pura: nao importa gluon nem acessa repositorios.
"""

# CANCEL_TICKET e uma acao dentro das telas de tickets, nao uma tela propria; fica fora do menu.
_CATALOGO = (
    ("OPERATION", u"Operação", (
        ("EXEC_SCRIPT", u"Rotinas disponíveis", "tickets", "catalogo", "icon-file-code"),
        ("EXEC_SCRIPT", u"Disparar Scripts", "tickets", "novo", "icon-play"),
        ("VIEW_LOGS", u"Consultar Logs", "tickets", "lista", "icon-list"),
    )),
    ("ADMIN", u"Administração", (
        ("MANAGE_USERS", u"Gestão de Usuários", "admin_usuarios", "lista", "icon-users"),
        ("MANAGE_PROFILES", u"Gestão de Perfis", "admin_perfis", "lista", "icon-shield"),
        ("MANAGE_ENVIRONMENTS", u"Gestão de Ambientes", "admin_ambientes", "lista", "icon-server"),
        ("MANAGE_SCRIPTS", u"Gestão de Scripts", "admin_scripts", "lista", "icon-file-code"),
        ("MANAGE_PARAMETERS", u"Dicionário de Parâmetros", "admin_parametros", "lista", "icon-sliders"),
        ("MANAGE_SCHEDULES", u"Regras de Agendamento", "agendamentos", "lista", "icon-calendar"),
        ("VIEW_AUDIT", u"Auditoria", "auditoria", "lista", "icon-audit"),
    )),
)


def montar_menu(features, is_admin, current_route=None):
    """Monta as secoes OPERACAO e ADMIN visiveis ao perfil.

    funcionalidades: iteravel de codigos concedidos ao perfil.
    is_admin: perfil administrativo (True ou 'S') ve todo o catalogo.
    rota_atual: tupla (controller, function) para marcar o item ativo.
    Retorna lista de {secao, titulo, itens: [{codigo, rotulo, rota, icone, ativo}]},
    omitindo secoes sem itens.
    """
    admin = is_admin is True or is_admin == "Y"
    concedidas = frozenset(features or ())
    atual = tuple(current_route) if current_route else None

    menu = []
    for secao, titulo, itens in _CATALOGO:
        visiveis = []
        for codigo, rotulo, controller, function, icone in itens:
            if not (admin or codigo in concedidas):
                continue
            visiveis.append({
                "code": codigo,
                "rotulo": rotulo,
                "rota": (controller, function),
                "icone": icone,
                "active": atual == (controller, function),
            })
        if visiveis:
            menu.append({"secao": secao, "titulo": titulo, "itens": visiveis})
    return menu
