# -*- coding: utf-8 -*-
"""Navegacao derivada das funcionalidades do perfil (README §4.3.D).

Funcao pura: nao importa gluon nem acessa repositorios.
"""

# CANC_TICKET e uma acao dentro das telas de tickets, nao uma tela propria; fica fora do menu.
_CATALOGO = (
    ("OPERACAO", u"Operação", (
        ("EXEC_SCRIPT", u"Rotinas disponíveis", "tickets", "catalogo", "icon-file-code"),
        ("EXEC_SCRIPT", u"Disparar Scripts", "tickets", "novo", "icon-play"),
        ("VER_LOGS", u"Consultar Logs", "tickets", "lista", "icon-list"),
    )),
    ("ADMIN", u"Administração", (
        ("CAD_USUARIOS", u"Gestão de Usuários", "admin_usuarios", "lista", "icon-users"),
        ("CAD_PERFIS", u"Gestão de Perfis", "admin_perfis", "lista", "icon-shield"),
        ("CAD_AMBIENTES", u"Gestão de Ambientes", "admin_ambientes", "lista", "icon-server"),
        ("CAD_SCRIPTS", u"Gestão de Scripts", "admin_scripts", "lista", "icon-file-code"),
        ("CAD_PARAMETROS", u"Dicionário de Parâmetros", "admin_parametros", "lista", "icon-sliders"),
        ("CAD_AGENDAMENTOS", u"Regras de Agendamento", "agendamentos", "lista", "icon-calendar"),
        ("VER_AUDITORIA", u"Auditoria", "auditoria", "lista", "icon-audit"),
    )),
)


def montar_menu(funcionalidades, is_admin, rota_atual=None):
    """Monta as secoes OPERACAO e ADMIN visiveis ao perfil.

    funcionalidades: iteravel de codigos concedidos ao perfil.
    is_admin: perfil administrativo (True ou 'S') ve todo o catalogo.
    rota_atual: tupla (controller, function) para marcar o item ativo.
    Retorna lista de {secao, titulo, itens: [{codigo, rotulo, rota, icone, ativo}]},
    omitindo secoes sem itens.
    """
    admin = is_admin is True or is_admin == "S"
    concedidas = frozenset(funcionalidades or ())
    atual = tuple(rota_atual) if rota_atual else None

    menu = []
    for secao, titulo, itens in _CATALOGO:
        visiveis = []
        for codigo, rotulo, controller, function, icone in itens:
            if not (admin or codigo in concedidas):
                continue
            visiveis.append({
                "codigo": codigo,
                "rotulo": rotulo,
                "rota": (controller, function),
                "icone": icone,
                "ativo": atual == (controller, function),
            })
        if visiveis:
            menu.append({"secao": secao, "titulo": titulo, "itens": visiveis})
    return menu
