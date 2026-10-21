# -*- coding: utf-8 -*-
"""Decisoes de autorizacao do SSS (README §4.3).

Modulo puro: nao importa gluon nem acessa repositorios (AGENTS §7.1). Os dados de
entrada (script, ambiente, ticket) devem vir do repositorio, nunca do cliente.
"""

ADMIN_PRIORITY = 1
PRIORITIES = (1, 2, 3, 4)


class Reason(object):
    """Motivos internos de negacao; destinados ao log, nunca ao usuario."""
    OK = "OK"
    INVALID_DATA = "INVALID_DATA"
    USER_INACTIVE = "USER_INACTIVE"
    PROFILE_INACTIVE = "PROFILE_INACTIVE"
    SCRIPT_INACTIVE = "SCRIPT_INACTIVE"
    ENVIRONMENT_INACTIVE = "ENVIRONMENT_INACTIVE"
    NOT_HOMOLOGATED = "NOT_HOMOLOGATED"
    NO_FEATURE = "NO_FEATURE"
    NO_ENVIRONMENT = "NO_ENVIRONMENT"
    NO_SCRIPT = "NO_SCRIPT"


def _flag(valor):
    # Somente 'S' ou True sao verdadeiros: 'N', '', None e afins negam.
    return valor is True or valor == "Y"


def _valid_id(valor):
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


def user_context(estado):
    """Monta o contexto de autorizacao a partir do estado de sessao e da matriz do perfil.

    estado: dict de RepoUsers.obter_estado_sessao acrescido de 'features'
    (codigos), 'environments' (nomes) e 'scripts' (ids).
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
        "features": frozenset(estado.get("features") or ()),
        "environments": frozenset(estado.get("environments") or ()),
        "scripts": frozenset(estado.get("scripts") or ()),
        "perm_version": estado["perm_version"],
        "session_epoch": estado.get("session_epoch", 0),
    }


def _active(ctx):
    return bool(ctx) and ctx.get("usuario_ativo") is True and ctx.get("perfil_ativo") is True


def has_feature(ctx, codigo):
    """True se o perfil concede a funcionalidade; admin tem todas, desde que ativo."""
    if not _active(ctx):
        return False
    if ctx.get("is_admin") is True:
        return True
    return codigo in ctx.get("features", ())


def _environment_name(ambiente):
    if isinstance(ambiente, dict):
        ambiente = ambiente.get("name")
    return ambiente if isinstance(ambiente, str) and ambiente else None


def can_view_environment(ctx, ambiente):
    """True se o perfil enxerga o ambiente (dict com 'nome' ou o proprio nome)."""
    if not _active(ctx):
        return False
    nome = _environment_name(ambiente)
    if nome is None:
        return False
    if ctx.get("is_admin") is True:
        return True
    return nome in ctx.get("environments", ())


def can_execute(ctx, script, ambiente, homologacoes):
    """Decisao composta de execucao (README §4.3.A). Retorna (bool, Reason.*).

    script e ambiente sao dicts do repositorio (id, ativo, nome); homologacoes e o
    iteravel de ambiente_id homologados para o script (tbsss_script_env).
    """
    if not ctx or not isinstance(script, dict) or not isinstance(ambiente, dict):
        return False, Reason.INVALID_DATA
    if not _valid_id(script.get("id")) or not _valid_id(ambiente.get("id")) \
            or _environment_name(ambiente) is None:
        return False, Reason.INVALID_DATA
    if ctx.get("usuario_ativo") is not True:
        return False, Reason.USER_INACTIVE
    if ctx.get("perfil_ativo") is not True:
        return False, Reason.PROFILE_INACTIVE
    if not _flag(script.get("active")):
        return False, Reason.SCRIPT_INACTIVE
    if not _flag(ambiente.get("active")):
        return False, Reason.ENVIRONMENT_INACTIVE
    if ambiente["id"] not in frozenset(homologacoes or ()):
        return False, Reason.NOT_HOMOLOGATED
    if ctx.get("is_admin") is True:
        return True, Reason.OK
    if "EXEC_SCRIPT" not in ctx.get("features", ()):
        return False, Reason.NO_FEATURE
    if ambiente["name"] not in ctx.get("environments", ()):
        return False, Reason.NO_ENVIRONMENT
    if script["id"] not in ctx.get("scripts", ()):
        return False, Reason.NO_SCRIPT
    return True, Reason.OK


def pause_reason_for(motivo_rbac):
    """Motivo de pausa da regra (tbsss_schedules.pausa_motivo) para um motivo de can_execute.

    Traducao unica para a web e o daemon (CR-008, R-33; README §7.5): USER_INACTIVE,
    SCRIPT_INACTIVE e ENVIRONMENT_INACTIVE passam direto; os demais viram NO_PERMISSION.
    """
    if motivo_rbac in (Reason.USER_INACTIVE, Reason.SCRIPT_INACTIVE, Reason.ENVIRONMENT_INACTIVE):
        return motivo_rbac
    return "NO_PERMISSION"


def can_view_ticket(ctx, ticket):
    """VIEW_LOGS sobre ticket de ambiente autorizado (admin: todos) (README §4.3.C)."""
    if not isinstance(ticket, dict):
        return False
    return has_feature(ctx, "VIEW_LOGS") and can_view_environment(ctx, ticket.get("environment"))


def can_cancel(ctx, ticket):
    """CANCEL_TICKET em ambiente autorizado, ou EXEC_SCRIPT sobre ticket proprio (README §4.3.C)."""
    if not isinstance(ticket, dict) or not _active(ctx):
        return False
    if ctx.get("is_admin") is True:
        return True
    if has_feature(ctx, "CANCEL_TICKET") and can_view_environment(ctx, ticket.get("environment")):
        return True
    solicitante = ticket.get("requested_by")
    return has_feature(ctx, "EXEC_SCRIPT") and isinstance(solicitante, str) \
        and solicitante == ctx.get("login")


def allowed_priority(ctx, prioridade):
    """Prioridade entre 1 e 4; a prioridade 1 e exclusiva de admin (README §5.3)."""
    if not _active(ctx) or not _valid_id(prioridade) or prioridade not in PRIORITIES:
        return False
    if prioridade == ADMIN_PRIORITY:
        return ctx.get("is_admin") is True
    return True
