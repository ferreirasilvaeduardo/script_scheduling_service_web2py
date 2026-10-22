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
    granted = frozenset(features or ())
    current = tuple(current_route) if current_route else None

    menu = []
    for section, title, items in _CATALOGO:
        visible = []
        for code, label, controller, function, icon in items:
            if not (admin or code in granted):
                continue
            visible.append({
                "code": code,
                "rotulo": label,
                "rota": (controller, function),
                "icone": icon,
                "active": current == (controller, function),
            })
        if visible:
            menu.append({"secao": section, "titulo": title, "itens": visible})
    return menu
