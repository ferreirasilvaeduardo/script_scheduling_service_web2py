# -*- coding: utf-8 -*-
"""Navegacao derivada das funcionalidades do perfil (README §4.3.D).

Funcao pura: nao importa gluon nem acessa repositorios.
"""

# CANCEL_TICKET e uma acao dentro das telas de tickets, nao uma tela propria; fica fora do menu.
_CATALOG = (
    ("OPERATION", u"Operação", (
        ("EXEC_SCRIPT", u"Rotinas disponíveis", "tickets", "catalog", "icon-file-code"),
        ("EXEC_SCRIPT", u"Disparar Scripts", "tickets", "new", "icon-play"),
        ("VIEW_LOGS", u"Consultar Logs", "tickets", "index", "icon-list"),
    )),
    ("ADMIN", u"Administração", (
        ("MANAGE_USERS", u"Gestão de Usuários", "admin_users", "index", "icon-users"),
        ("MANAGE_PROFILES", u"Gestão de Perfis", "admin_profiles", "index", "icon-shield"),
        ("MANAGE_ENVIRONMENTS", u"Gestão de Ambientes", "admin_environments", "index", "icon-server"),
        ("MANAGE_SCRIPTS", u"Gestão de Scripts", "admin_scripts", "index", "icon-file-code"),
        ("MANAGE_PARAMETERS", u"Dicionário de Parâmetros", "admin_parameters", "index", "icon-sliders"),
        ("MANAGE_SCHEDULES", u"Regras de Agendamento", "schedules", "index", "icon-calendar"),
        ("VIEW_AUDIT", u"Auditoria", "audit", "index", "icon-audit"),
    )),
)


def build_menu(features, is_admin, current_route=None):
    """Monta as secoes OPERACAO e ADMIN visiveis ao perfil.

    features: iteravel de codigos concedidos ao perfil.
    is_admin: perfil administrativo (True ou 'Y') ve todo o catalogo.
    current_route: tupla (controller, function) para marcar o item ativo.
    Retorna lista de {section, title, items: [{code, label, route, icon, active}]},
    omitindo secoes sem itens.
    """
    admin = is_admin is True or is_admin == "Y"
    granted = frozenset(features or ())
    current = tuple(current_route) if current_route else None

    menu = []
    for section, title, items in _CATALOG:
        visible = []
        for code, label, controller, function, icon in items:
            if not (admin or code in granted):
                continue
            visible.append({
                "code": code,
                "label": label,
                "route": (controller, function),
                "icon": icon,
                "active": current == (controller, function),
            })
        if visible:
            menu.append({"section": section, "title": title, "items": visible})
    return menu
