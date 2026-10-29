# -*- coding: utf-8 -*-
"""Navegacao derivada das funcionalidades do perfil (README §4.3.D).

Funcao pura: nao importa gluon nem acessa repositorios.
"""

# CANCEL_TICKET e uma acao dentro das telas de tickets, nao uma tela propria; fica fora do menu.
# O codigo do item pode ser uma tupla: o item aparece com qualquer um deles. Tickets vale para
# EXEC_SCRIPT (proprios) e VIEW_LOGS (ambientes), como ticket_service.can_query (CR-017).
_CATALOG = (
    ("OPERATION", u"Operação", (
        # Um so caminho para rodar: os cartoes levam ao disparo ja com script e ambiente (CR-017b).
        ("EXEC_SCRIPT", u"Rodar um script", "tickets", "catalog", "icon-play"),
        (("VIEW_LOGS", "EXEC_SCRIPT"), u"Tickets", "tickets", "index", "icon-list"),
        # Navegacao pelas saidas guardadas no banco, com download do zip ou de um arquivo (CR-020a).
        ("DOWNLOAD_OUTPUT", u"Saídas", "outputs", "index", "icon-download"),
        # Envio de arquivos para a pasta de entrada dos scripts, entregue pelos agentes (CR-020d).
        ("UPLOAD_INPUT", u"Entrada", "inputs", "index", "icon-upload"),
        # Pasta de arquivos so em disco, por ambiente e script (CR-037): com qualquer das duas.
        (("FILES_UPLOAD", "FILES_DOWNLOAD"), u"Pasta de Arquivos", "files", "index", "icon-folder"),
        # Telas que antes so abriam por botao ou aba (CR-017c): o que vai rodar e a saude dos agentes.
        ("MANAGE_SCHEDULES", u"Agenda", "schedules", "agenda", "icon-calendar"),
        ("VIEW_AUDIT", u"Agentes", "audit", "agents", "icon-server"),
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
            codes = code if isinstance(code, tuple) else (code,)
            if not (admin or granted.intersection(codes)):
                continue
            visible.append({
                "code": codes[0],
                "label": label,
                "route": (controller, function),
                "icon": icon,
                "active": current == (controller, function),
            })
        if visible:
            menu.append({"section": section, "title": title, "items": visible})
    return menu
