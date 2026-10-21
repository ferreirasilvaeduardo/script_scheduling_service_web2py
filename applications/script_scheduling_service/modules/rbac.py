# -*- coding: utf-8 -*-
"""Decisoes de autorizacao do SSS (README §4.3).

Modulo puro: nao importa gluon nem acessa repositorios (AGENTS §7.1). Os dados de
entrada (script, ambiente, ticket) devem vir do repositorio, nunca do cliente.
"""

PRIORIDADE_ADMIN = 1
PRIORIDADES = (1, 2, 3, 4)


class Motivo(object):
    """Motivos internos de negacao; destinados ao log, nunca ao usuario."""
    OK = "OK"
    DADO_INVALIDO = "DADO_INVALIDO"
    USER_INACTIVE = "USER_INACTIVE"
    PERFIL_INATIVO = "PERFIL_INATIVO"
    SCRIPT_INACTIVE = "SCRIPT_INACTIVE"
    ENVIRONMENT_INACTIVE = "ENVIRONMENT_INACTIVE"
    SEM_HOMOLOGACAO = "SEM_HOMOLOGACAO"
    SEM_FUNC = "SEM_FUNC"
    SEM_AMBIENTE = "SEM_AMBIENTE"
    SEM_SCRIPT = "SEM_SCRIPT"


def _flag(valor):
    # Somente 'S' ou True sao verdadeiros: 'N', '', None e afins negam.
    return valor is True or valor == "Y"


def _id_valido(valor):
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


def contexto_usuario(estado):
    """Monta o contexto de autorizacao a partir do estado de sessao e da matriz do perfil.

    estado: dict de RepoUsuarios.obter_estado_sessao acrescido de 'funcionalidades'
    (codigos), 'ambientes' (nomes) e 'scripts' (ids).
    """
    return {
        "user_id": estado["user_id"],
        "login": estado["login"],
        "name": estado.get("name") or estado["login"],
        "profile_id": estado["profile_id"],
        "perfil_nome": estado.get("perfil_nome") or "",
        "is_admin": _flag(estado.get("is_admin")),
        "usuario_ativo": _flag(estado.get("usuario_ativo")),
        "perfil_ativo": _flag(estado.get("perfil_ativo")),
        "funcionalidades": frozenset(estado.get("funcionalidades") or ()),
        "ambientes": frozenset(estado.get("ambientes") or ()),
        "scripts": frozenset(estado.get("scripts") or ()),
        "perm_version": estado["perm_version"],
        "session_epoch": estado.get("session_epoch", 0),
    }


def _ativo(ctx):
    return bool(ctx) and ctx.get("usuario_ativo") is True and ctx.get("perfil_ativo") is True


def tem_func(ctx, codigo):
    """True se o perfil concede a funcionalidade; admin tem todas, desde que ativo."""
    if not _ativo(ctx):
        return False
    if ctx.get("is_admin") is True:
        return True
    return codigo in ctx.get("funcionalidades", ())


def _nome_ambiente(ambiente):
    if isinstance(ambiente, dict):
        ambiente = ambiente.get("name")
    return ambiente if isinstance(ambiente, str) and ambiente else None


def pode_ver_ambiente(ctx, ambiente):
    """True se o perfil enxerga o ambiente (dict com 'nome' ou o proprio nome)."""
    if not _ativo(ctx):
        return False
    nome = _nome_ambiente(ambiente)
    if nome is None:
        return False
    if ctx.get("is_admin") is True:
        return True
    return nome in ctx.get("ambientes", ())


def pode_executar(ctx, script, ambiente, homologacoes):
    """Decisao composta de execucao (README §4.3.A). Retorna (bool, Motivo.*).

    script e ambiente sao dicts do repositorio (id, ativo, nome); homologacoes e o
    iteravel de ambiente_id homologados para o script (tbsss_script_env).
    """
    if not ctx or not isinstance(script, dict) or not isinstance(ambiente, dict):
        return False, Motivo.DADO_INVALIDO
    if not _id_valido(script.get("id")) or not _id_valido(ambiente.get("id")) \
            or _nome_ambiente(ambiente) is None:
        return False, Motivo.DADO_INVALIDO
    if ctx.get("usuario_ativo") is not True:
        return False, Motivo.USER_INACTIVE
    if ctx.get("perfil_ativo") is not True:
        return False, Motivo.PERFIL_INATIVO
    if not _flag(script.get("active")):
        return False, Motivo.SCRIPT_INACTIVE
    if not _flag(ambiente.get("active")):
        return False, Motivo.ENVIRONMENT_INACTIVE
    if ambiente["id"] not in frozenset(homologacoes or ()):
        return False, Motivo.SEM_HOMOLOGACAO
    if ctx.get("is_admin") is True:
        return True, Motivo.OK
    if "EXEC_SCRIPT" not in ctx.get("funcionalidades", ()):
        return False, Motivo.SEM_FUNC
    if ambiente["name"] not in ctx.get("ambientes", ()):
        return False, Motivo.SEM_AMBIENTE
    if script["id"] not in ctx.get("scripts", ()):
        return False, Motivo.SEM_SCRIPT
    return True, Motivo.OK


def motivo_pausa(motivo_rbac):
    """Motivo de pausa da regra (tbsss_schedules.pausa_motivo) para um motivo de pode_executar.

    Traducao unica para a web e o daemon (CR-008, R-33; README §7.5): USER_INACTIVE,
    SCRIPT_INACTIVE e ENVIRONMENT_INACTIVE passam direto; os demais viram NO_PERMISSION.
    """
    if motivo_rbac in (Motivo.USER_INACTIVE, Motivo.SCRIPT_INACTIVE, Motivo.ENVIRONMENT_INACTIVE):
        return motivo_rbac
    return "NO_PERMISSION"


def pode_ver_ticket(ctx, ticket):
    """VIEW_LOGS sobre ticket de ambiente autorizado (admin: todos) (README §4.3.C)."""
    if not isinstance(ticket, dict):
        return False
    return tem_func(ctx, "VIEW_LOGS") and pode_ver_ambiente(ctx, ticket.get("environment"))


def pode_cancelar(ctx, ticket):
    """CANCEL_TICKET em ambiente autorizado, ou EXEC_SCRIPT sobre ticket proprio (README §4.3.C)."""
    if not isinstance(ticket, dict) or not _ativo(ctx):
        return False
    if ctx.get("is_admin") is True:
        return True
    if tem_func(ctx, "CANCEL_TICKET") and pode_ver_ambiente(ctx, ticket.get("environment")):
        return True
    solicitante = ticket.get("requested_by")
    return tem_func(ctx, "EXEC_SCRIPT") and isinstance(solicitante, str) \
        and solicitante == ctx.get("login")


def prioridade_permitida(ctx, prioridade):
    """Prioridade entre 1 e 4; a prioridade 1 e exclusiva de admin (README §5.3)."""
    if not _ativo(ctx) or not _id_valido(prioridade) or prioridade not in PRIORIDADES:
        return False
    if prioridade == PRIORIDADE_ADMIN:
        return ctx.get("is_admin") is True
    return True
