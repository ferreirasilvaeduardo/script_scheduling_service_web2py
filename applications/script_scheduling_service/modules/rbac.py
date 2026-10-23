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


def _flag(value):
    # Somente 'S' ou True sao verdadeiros: 'N', '', None e afins negam.
    return value is True or value == "Y"


def _valid_id(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def user_context(state):
    """Monta o contexto de autorizacao a partir do estado de sessao e da matriz do perfil.

    estado: dict de RepoUsers.obter_estado_sessao acrescido de 'features'
    (codigos), 'environments' (nomes) e 'scripts' (ids).
    """
    return {
        "user_id": state["user_id"],
        "login": state["login"],
        "name": state.get("name") or state["login"],
        "profile_id": state["profile_id"],
        "profile_name": state.get("profile_name") or "",
        "is_admin": _flag(state.get("is_admin")),
        "active_user": _flag(state.get("active_user")),
        "active_profile": _flag(state.get("active_profile")),
        "features": frozenset(state.get("features") or ()),
        "environments": frozenset(state.get("environments") or ()),
        "scripts": frozenset(state.get("scripts") or ()),
        "perm_version": state["perm_version"],
        "session_epoch": state.get("session_epoch", 0),
    }


def _active(ctx):
    return bool(ctx) and ctx.get("active_user") is True and ctx.get("active_profile") is True


def has_feature(ctx, code):
    """True se o perfil concede a funcionalidade; admin tem todas, desde que ativo."""
    if not _active(ctx):
        return False
    if ctx.get("is_admin") is True:
        return True
    return code in ctx.get("features", ())


def _environment_name(environment):
    if isinstance(environment, dict):
        environment = environment.get("name")
    return environment if isinstance(environment, str) and environment else None


def can_view_environment(ctx, environment):
    """True se o perfil enxerga o ambiente (dict com 'nome' ou o proprio nome)."""
    if not _active(ctx):
        return False
    name = _environment_name(environment)
    if name is None:
        return False
    if ctx.get("is_admin") is True:
        return True
    return name in ctx.get("environments", ())


def can_execute(ctx, script, environment, homologations):
    """Decisao composta de execucao (README §4.3.A). Retorna (bool, Reason.*).

    script e ambiente sao dicts do repositorio (id, ativo, nome); homologacoes e o
    iteravel de environment_id homologados para o script (tbsss_script_env).
    """
    if not ctx or not isinstance(script, dict) or not isinstance(environment, dict):
        return False, Reason.INVALID_DATA
    if not _valid_id(script.get("id")) or not _valid_id(environment.get("id")) \
            or _environment_name(environment) is None:
        return False, Reason.INVALID_DATA
    if ctx.get("active_user") is not True:
        return False, Reason.USER_INACTIVE
    if ctx.get("active_profile") is not True:
        return False, Reason.PROFILE_INACTIVE
    if not _flag(script.get("active")):
        return False, Reason.SCRIPT_INACTIVE
    if not _flag(environment.get("active")):
        return False, Reason.ENVIRONMENT_INACTIVE
    if environment["id"] not in frozenset(homologations or ()):
        return False, Reason.NOT_HOMOLOGATED
    if ctx.get("is_admin") is True:
        return True, Reason.OK
    if "EXEC_SCRIPT" not in ctx.get("features", ()):
        return False, Reason.NO_FEATURE
    if environment["name"] not in ctx.get("environments", ()):
        return False, Reason.NO_ENVIRONMENT
    if script["id"] not in ctx.get("scripts", ()):
        return False, Reason.NO_SCRIPT
    return True, Reason.OK


def pause_reason_for(rbac_reason):
    """Motivo de pausa da regra (tbsss_schedules.pausa_motivo) para um motivo de can_execute.

    Traducao unica para a web e o daemon (CR-008, R-33; README §7.5): USER_INACTIVE,
    SCRIPT_INACTIVE e ENVIRONMENT_INACTIVE passam direto; os demais viram NO_PERMISSION.
    """
    if rbac_reason in (Reason.USER_INACTIVE, Reason.SCRIPT_INACTIVE, Reason.ENVIRONMENT_INACTIVE):
        return rbac_reason
    return "NO_PERMISSION"


def can_view_ticket(ctx, ticket):
    """VIEW_LOGS sobre ticket de ambiente autorizado (admin: todos) (README §4.3.C)."""
    if not isinstance(ticket, dict):
        return False
    return has_feature(ctx, "VIEW_LOGS") and can_view_environment(ctx, ticket.get("environment"))


def can_cancel(ctx, ticket):
    """CANCEL_TICKET com VIEW_LOGS em ambiente autorizado, ou EXEC_SCRIPT sobre ticket proprio (README §4.3.C).

    CR-018a: o ticket de terceiro so e cancelado por quem o enxerga (lista e detalhe exigem VIEW_LOGS).
    """
    if not isinstance(ticket, dict) or not _active(ctx):
        return False
    if ctx.get("is_admin") is True:
        return True
    if has_feature(ctx, "CANCEL_TICKET") and can_view_ticket(ctx, ticket):
        return True
    requester = ticket.get("requested_by")
    return has_feature(ctx, "EXEC_SCRIPT") and isinstance(requester, str) \
        and requester == ctx.get("login")


def allowed_priority(ctx, priority):
    """Prioridade entre 1 e 4; a prioridade 1 e exclusiva de admin (README §5.3)."""
    if not _active(ctx) or not _valid_id(priority) or priority not in PRIORITIES:
        return False
    if priority == ADMIN_PRIORITY:
        return ctx.get("is_admin") is True
    return True
