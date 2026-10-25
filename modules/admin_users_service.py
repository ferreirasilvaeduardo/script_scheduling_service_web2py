# -*- coding: utf-8 -*-
"""Cadastro de usuarios (README §4.2, §4.3.B, §4.4, §10 tabela 9). Padrao em docs/ADMIN_CRUD_PATTERN.md.

Senha e hash nunca saem deste modulo: listagem e formulario devolvem registros sem password_hash, e a
auditoria registra apenas o fato ('senha redefinida'). Nao importa gluon.
"""
import re
import threading

import admin_crud
import auth_service
import security
import ui_helpers
from admin_crud import GENERAL_FIELD, OperationDenied
from repo_errors import RepoConflict, RepoNotFound, RepoViolation

FEATURE = "MANAGE_USERS"
EDITABLE_FIELDS = ("name", "profile_id", "active")
# Referencias aparecem pelo nome na auditoria de inclusao (README §4.4): perfil, nao profile_id.
INSERT_FIELDS = ("login", "name", "profile")
NAME_MAX_LENGTH = 60
_PROFILES_MAX = 1000
_PUBLIC_FIELDS = ("id", "login", "name", "profile_id", "failed_attempts", "locked_until", "last_login_at",
                    "password_changed_at", "active", "created_at")

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_LOGIN = re.compile(r"[a-z0-9._-]{3,30}")
_RE_FILTER = re.compile(r"[A-Za-z0-9._ -]{1,60}")

MSG_LOGIN_REQUIRED = u"Informe o login."
MSG_LOGIN_INVALID = u"Use de 3 a 30 caracteres: letras minúsculas, dígitos, ponto, _ ou - (ex.: maria.silva)."
MSG_LOGIN_DUPLICATE = u"Já existe um usuário com este login."
MSG_NAME_REQUIRED = u"Informe o nome."
MSG_NAME_LENGTH = u"O nome deve ter no máximo %d caracteres." % NAME_MAX_LENGTH
MSG_PROFILE_INVALID = u"Selecione um perfil ativo."
MSG_PASSWORD_REQUIRED = u"Informe a senha."
MSG_PASSWORD_TOO_LONG = u"A senha deve ter no máximo %d caracteres." % auth_service.PASSWORD_MAX
MSG_CONFIRMATION = auth_service.MSG_CONFIRMATION
MSG_LAST_ADMIN = ui_helpers.message("last_admin")
MSG_SELF_DEACTIVATE = u"Operação negada: você não pode desativar o próprio usuário."
MSG_SELF_PROFILE = u"Operação negada: você não pode remover o próprio perfil administrativo."
MSG_SELF_PASSWORD = u"Para trocar a sua própria senha, use \"Minha senha\" (exige a senha atual)."
MSG_ADMIN_ONLY = (u"Só um administrador pode alterar um usuário administrador ou dar o perfil de administrador. "
                u"Peça a um administrador.")
POLICY_HELP = u"Mínimo de %d caracteres. A senha nunca é exibida nem registrada." % security.PASSWORD_MIN
DEACTIVATION_WARNING = u"O usuário perde o acesso e tem a sessão encerrada no próximo clique."

_FIELD_BY_CONSTRAINT = {
    "uk_tbsss_usr_login": ("login", MSG_LOGIN_DUPLICATE),
    "ck_tbsss_usr_login": ("login", MSG_LOGIN_INVALID),
    "fk_tbsss_usr_prf": ("profile_id", MSG_PROFILE_INVALID),
    "sss_ultimo_admin": (GENERAL_FIELD, MSG_LAST_ADMIN),
}


def _id(value):
    value = admin_crud.text(value, 11)
    if value is None or not _RE_ID.fullmatch(value) or int(value) < 1:
        return None
    return int(value)


def public_view(user):
    """Copia do usuario sem password_hash (e sem qualquer campo nao listado)."""
    return dict((c, user.get(c)) for c in _PUBLIC_FIELDS)


def normalize_filters(input_value):
    """Filtros da lista: login, name (trechos), profile_id e state ('Y' | 'N' | 'B' bloqueados)."""
    input_value = input_value or {}
    filters = {}
    for key in ("login", "name"):
        value = admin_crud.text(input_value.get(key), 60)
        if value and _RE_FILTER.fullmatch(value):
            filters[key] = value
    profile = _id(input_value.get("profile_id"))
    if profile is not None:
        filters["profile_id"] = profile
    state = admin_crud.text(input_value.get("state"), 1)
    if state in ("Y", "N", "B"):
        filters["state"] = state
    return filters


class AdminUsersService(object):
    """Regras do cadastro de usuarios com repositorios, relogio e log injetados."""

    def __init__(self, users, rbac_repo, log, clock=None):
        self._users = users
        self._rbac = rbac_repo
        self._log = log
        # Relogio do banco (README §4.2): bloqueio vigente e filtro "Bloqueados" comparam com SYSDATE.
        self._clock = clock or users.now

    def _get(self, user_id):
        uid = _id(user_id)
        if uid is None:
            raise RepoNotFound("usuario invalido")
        return self._users.get_by_id(uid)

    def profiles(self, active_only=False):
        """Perfis para selecao: lista de {id, name, is_admin, active} ordenada por nome."""
        items = self._rbac.profiles_list(filters={"active": "Y"} if active_only else None, page=1,
                                         size=_PROFILES_MAX)["items"]
        return [{"id": p["id"], "name": p["name"], "is_admin": p["is_admin"], "active": p["active"]} for p in items]

    def _admin_profile(self, profile_id):
        try:
            return self._rbac.profiles_get(profile_id).get("is_admin") == "Y"
        except RepoNotFound:
            return False

    def _require_admin(self, ctx, condition, operation):
        admin_crud.require_admin(ctx, condition, MSG_ADMIN_ONLY, self._log, operation)

    def is_locked(self, user):
        """True se o bloqueio por tentativas ainda vale agora."""
        until = user.get("locked_until")
        return until is not None and until > self._clock()

    # ----------------------------------------------------------------- leitura

    def list(self, ctx, filters, page, size):
        """Pagina de usuarios (login ASC) sem password_hash, com profile_name e locked."""
        admin_crud.require_feature(ctx, FEATURE)
        repo_filters = dict((k, v) for k, v in filters.items() if k != "state")
        state = filters.get("state")
        if state in ("Y", "N"):
            repo_filters["active"] = state
        elif state == "B":
            repo_filters["locked_at"] = self._clock()
        result = self._users.list(filters=repo_filters, page=page, size=size)
        names = dict((p["id"], p["name"]) for p in self.profiles())
        items = []
        for u in result["items"]:
            item = public_view(u)
            item["profile_name"] = names.get(u["profile_id"], "#%s" % u["profile_id"])
            item["locked"] = self.is_locked(u)
            items.append(item)
        return dict(result, items=items)

    def form(self, ctx, user_id=None):
        """Dados do formulario sem password_hash; na edicao inclui versao, bloqueio e se e o proprio usuario."""
        admin_crud.require_feature(ctx, FEATURE)
        if user_id in (None, ""):
            return {"id": None, "login": "", "name": "", "profile_id": None, "active": "Y", "version": "",
                    "locked": False, "locked_until": None, "failed_attempts": 0, "own": False,
                    "record": None}
        u = self._get(user_id)
        data = public_view(u)
        data.update(version=admin_crud.version(u, EDITABLE_FIELDS), locked=self.is_locked(u),
                     own=u["id"] == ctx.get("user_id"), record=ui_helpers.record_info(u, ctx))
        return data

    # ----------------------------------------------------------------- escrita

    def _violation(self, ctx, exc, errors):
        field, message = _FIELD_BY_CONSTRAINT.get(exc.constraint, (GENERAL_FIELD, admin_crud.MSG_FAILURE))
        errors[field] = message
        self._log.warning("cadastro de usuario rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"action": FEATURE})

    def _active_profile(self, value, errors, current_value=None):
        """Perfil escolhido: precisa estar ativo, exceto quando a edicao mantem o perfil atual."""
        pid = _id(value)
        all_value = dict((p["id"], p) for p in self.profiles())
        if pid not in all_value or (all_value[pid]["active"] != "Y" and pid != current_value):
            errors["profile_id"] = MSG_PROFILE_INVALID
            return None, None
        return pid, all_value[pid]

    def _password(self, password_value, confirmation, errors, field="password"):
        if not isinstance(password_value, str) or not password_value:
            errors[field] = MSG_PASSWORD_REQUIRED
            return None
        if len(password_value) > auth_service.PASSWORD_MAX:
            errors[field] = MSG_PASSWORD_TOO_LONG
            return None
        problems = security.validate_password_policy(password_value)
        if problems:
            errors[field] = problems[0]
            return None
        if confirmation != password_value:
            errors["confirmation"] = MSG_CONFIRMATION
            return None
        return password_value

    def _name(self, value, errors):
        name = admin_crud.free_text(value, errors, "name")
        if name is None:
            errors["name"] = MSG_NAME_REQUIRED
        elif "name" not in errors and len(name) > NAME_MAX_LENGTH:
            errors["name"] = MSG_NAME_LENGTH
        return name

    def save(self, ctx, ip, user_id, data):
        """Inclui (login, nome, profile_id, senha, confirmacao) ou altera (nome, profile_id, versao).

        Retorna (id, erros). Na edicao o login e a senha enviados sao ignorados. Lanca
        RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        errors = {}
        if user_id in (None, ""):
            login = admin_crud.identifier(data.get("login"), errors, "login")
            if login is None:
                errors["login"] = MSG_LOGIN_REQUIRED
            elif "login" in errors:
                pass
            elif not _RE_LOGIN.fullmatch(login):
                errors["login"] = MSG_LOGIN_INVALID
            name = self._name(data.get("name"), errors)
            profile_id, profile = self._active_profile(data.get("profile_id"), errors)
            password = self._password(data.get("password"), data.get("confirmation"), errors)
            if errors:
                return None, errors
            try:
                self._require_admin(ctx, profile["is_admin"] == "Y", "CREATE")
            except OperationDenied as exc:
                return None, {"profile_id": exc.message}
            now = self._clock()
            new = {"login": login, "name": name, "profile_id": profile_id, "active": "Y",
                    "password_hash": security.hash_password(password), "password_changed_at": now}
            audit = admin_crud.audit_entry(ctx, ip, "CREATE",
                                             admin_crud.insert_detail(dict(new, profile=profile["name"]),
                                                                         INSERT_FIELDS))
            try:
                created = self._users.insert(new, audit=audit)
            except RepoViolation as exc:
                self._violation(ctx, exc, errors)
                return None, errors
            self._log.info("usuario incluido (login=%s usuario=%s)", ctx.get("login"), login,
                           extra={"action": "CREATE"})
            return created["id"], {}

        current = self._get(user_id)
        name = self._name(data.get("name"), errors)
        profile_id, profile = self._active_profile(data.get("profile_id"), errors, current["profile_id"])
        if errors:
            return current["id"], errors
        if current["id"] == ctx.get("user_id") and ctx.get("is_admin") is True and profile["is_admin"] != "Y":
            return current["id"], {GENERAL_FIELD: MSG_SELF_PROFILE}
        # Trocar o proprio perfil, mesmo por um nao administrativo, mudaria as proprias permissoes: so
        # administrador (CR-008 E1, revisao de 2026-10-20).
        swap_own = current["id"] == ctx.get("user_id") and profile_id != current["profile_id"]
        try:
            self._require_admin(ctx, profile["is_admin"] == "Y" or self._admin_profile(current["profile_id"])
                               or swap_own, "UPDATE")
        except OperationDenied as exc:
            return current["id"], {GENERAL_FIELD: exc.message}
        if admin_crud.text(data.get("version"), 64) != admin_crud.version(current, EDITABLE_FIELDS):
            return current["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        after = dict(current, name=name, profile_id=profile_id)
        detail = admin_crud.changes_detail(current, after, EDITABLE_FIELDS)
        if detail is None:
            return current["id"], {}
        try:
            self._users.update(current["id"], {"name": name, "profile_id": profile_id},
                                   expected=admin_crud.expected(current, EDITABLE_FIELDS),
                                   audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detail))
        except RepoConflict:
            return current["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        except RepoViolation as exc:
            self._violation(ctx, exc, errors)
            return current["id"], errors
        self._log.info("usuario alterado (login=%s usuario=%s)", ctx.get("login"), current["login"],
                       extra={"action": "UPDATE"})
        return current["id"], {}

    def toggle_active(self, ctx, ip, user_id, version):
        """Desativa (DEACTIVATE) ou reativa (UPDATE) o usuario.

        Lanca OperationDenied (proprio usuario ou ultimo administrador), RepoConflict,
        RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        current = self._get(user_id)
        new_active = "N" if current["active"] == "Y" else "Y"
        if new_active == "N" and current["id"] == ctx.get("user_id"):
            raise OperationDenied(MSG_SELF_DEACTIVATE)
        self._require_admin(ctx, self._admin_profile(current["profile_id"]), "DEACTIVATE")
        if admin_crud.text(version, 64) != admin_crud.version(current, EDITABLE_FIELDS):
            raise RepoConflict("versao divergente")
        detail = admin_crud.changes_detail(current, dict(current, active=new_active), ("active",))
        action = "DEACTIVATE" if new_active == "N" else "UPDATE"
        try:
            changed = self._users.update(current["id"], {"active": new_active},
                                              expected=admin_crud.expected(current, EDITABLE_FIELDS),
                                              audit=admin_crud.audit_entry(ctx, ip, action, detail))
        except RepoViolation as exc:
            if exc.constraint == "sss_ultimo_admin":
                self._log.warning("desativacao do ultimo admin negada (login=%s usuario=%s)", ctx.get("login"),
                                  current["login"], extra={"action": action})
                raise OperationDenied(MSG_LAST_ADMIN)
            raise
        self._log.info("usuario %s (login=%s usuario=%s)", "desativado" if new_active == "N" else "reativado",
                       ctx.get("login"), current["login"], extra={"action": action})
        return public_view(changed)

    def reset_password(self, ctx, ip, user_id, password_value, confirmation):
        """Define nova senha (politica + confirmacao), zera tentativas e bloqueio; audita sem o valor.

        Retorna erros por campo ({} no sucesso). Lanca OperationDenied (propria senha: usar
        'Minha senha'), RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        current = self._get(user_id)
        if current["id"] == ctx.get("user_id"):
            raise OperationDenied(MSG_SELF_PASSWORD)
        self._require_admin(ctx, self._admin_profile(current["profile_id"]), "UPDATE")
        errors = {}
        password_value = self._password(password_value, confirmation, errors)
        if errors:
            return errors
        self._users.set_password(current["id"], security.hash_password(password_value), self._clock(),
                                     audit=admin_crud.audit_entry(ctx, ip, "UPDATE", u"senha redefinida"))
        self._log.info("senha redefinida (login=%s usuario=%s)", ctx.get("login"), current["login"],
                       extra={"action": "UPDATE"})
        return {}

    def unlock(self, ctx, ip, user_id):
        """Zera tentativas e bloqueio do usuario, com auditoria UPDATE."""
        admin_crud.require_feature(ctx, FEATURE)
        current = self._get(user_id)
        self._require_admin(ctx, self._admin_profile(current["profile_id"]), "UPDATE")
        detail = u"desbloqueado (failed_attempts: %s; locked_until: %s)" % (
            current.get("failed_attempts") or 0, current.get("locked_until") or u"(vazio)")
        changed = self._users.unlock(current["id"],
                                              audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detail))
        self._log.info("usuario desbloqueado (login=%s usuario=%s)", ctx.get("login"), current["login"],
                       extra={"action": "UPDATE"})
        return public_view(changed)


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            import app_context
            import repo_factory
            import sss_logging
            factory = repo_factory
            _default = AdminUsersService(
                users=factory.get("users"),
                rbac_repo=factory.get("rbac"),
                log=sss_logging.get_logger("sss_web", app_context.require_config()),
            )
        return _default


def list_page(ctx, filters, page, size):
    """Pagina de usuarios sem password_hash (servico padrao)."""
    return _service().list(ctx, filters, page, size)


def form(ctx, user_id=None):
    """Dados do formulario de usuario (servico padrao)."""
    return _service().form(ctx, user_id)


def profiles(active_only=False):
    """Perfis para selecao e filtro (servico padrao)."""
    return _service().profiles(active_only)


def save(ctx, ip, user_id, data):
    """Inclusao ou alteracao de usuario (servico padrao)."""
    return _service().save(ctx, ip, user_id, data)


def toggle_active(ctx, ip, user_id, version):
    """Desativacao/reativacao de usuario (servico padrao)."""
    return _service().toggle_active(ctx, ip, user_id, version)


def reset_password(ctx, ip, user_id, password_value, confirmation):
    """Redefinicao de senha pelo administrador (servico padrao)."""
    return _service().reset_password(ctx, ip, user_id, password_value, confirmation)


def unlock(ctx, ip, user_id):
    """Desbloqueio do usuario (servico padrao)."""
    return _service().unlock(ctx, ip, user_id)
