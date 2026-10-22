# -*- coding: utf-8 -*-
"""Cadastro de usuarios (README §4.2, §4.3.B, §4.4, §10 tabela 9). Padrao em docs/ADMIN_CRUD_PATTERN.md.

Senha e hash nunca saem deste modulo: listagem e formulario devolvem registros sem senha_hash, e a
auditoria registra apenas o fato ('senha redefinida'). Nao importa gluon fora de _servico.
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
# Referencias aparecem pelo nome na auditoria de inclusao (README §4.4): perfil, nao perfil_id.
INSERT_FIELDS = ("login", "name", "perfil")
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
MSG_LAST_ADMIN = ui_helpers.mensagem("ultimo_admin")
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
    """Copia do usuario sem senha_hash (e sem qualquer campo nao listado)."""
    return dict((c, user.get(c)) for c in _PUBLIC_FIELDS)


def normalize_filters(input_value):
    """Filtros da lista: login, nome (trechos), perfil_id e situacao ('S' | 'N' | 'B' bloqueados)."""
    input_value = input_value or {}
    filtros = {}
    for chave in ("login", "name"):
        valor = admin_crud.text(input_value.get(chave), 60)
        if valor and _RE_FILTER.fullmatch(valor):
            filtros[chave] = valor
    perfil = _id(input_value.get("profile_id"))
    if perfil is not None:
        filtros["profile_id"] = perfil
    situacao = admin_crud.text(input_value.get("state"), 1)
    if situacao in ("Y", "N", "B"):
        filtros["state"] = situacao
    return filtros


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
        """Perfis para selecao: lista de {id, nome, is_admin, ativo} ordenada por nome."""
        itens = self._rbac.profiles_list(filters={"active": "Y"} if active_only else None, page=1,
                                         size=_PROFILES_MAX)["itens"]
        return [{"id": p["id"], "name": p["name"], "is_admin": p["is_admin"], "active": p["active"]} for p in itens]

    def _admin_profile(self, profile_id):
        try:
            return self._rbac.profiles_get(profile_id).get("is_admin") == "Y"
        except RepoNotFound:
            return False

    def _require_admin(self, ctx, condition, operation):
        admin_crud.require_admin(ctx, condition, MSG_ADMIN_ONLY, self._log, operation)

    def is_locked(self, user):
        """True se o bloqueio por tentativas ainda vale agora."""
        ate = user.get("locked_until")
        return ate is not None and ate > self._clock()

    # ----------------------------------------------------------------- leitura

    def list(self, ctx, filters, page, size):
        """Pagina de usuarios (login ASC) sem senha_hash, com perfil_nome e bloqueado."""
        admin_crud.require_feature(ctx, FEATURE)
        repo_filtros = dict((k, v) for k, v in filters.items() if k != "state")
        situacao = filters.get("state")
        if situacao in ("Y", "N"):
            repo_filtros["active"] = situacao
        elif situacao == "B":
            repo_filtros["bloqueado_em"] = self._clock()
        resultado = self._users.list(filters=repo_filtros, page=page, size=size)
        nomes = dict((p["id"], p["name"]) for p in self.profiles())
        itens = []
        for u in resultado["itens"]:
            item = public_view(u)
            item["perfil_nome"] = nomes.get(u["profile_id"], "#%s" % u["profile_id"])
            item["bloqueado"] = self.is_locked(u)
            itens.append(item)
        return dict(resultado, itens=itens)

    def form(self, ctx, user_id=None):
        """Dados do formulario sem senha_hash; na edicao inclui versao, bloqueio e se e o proprio usuario."""
        admin_crud.require_feature(ctx, FEATURE)
        if user_id in (None, ""):
            return {"id": None, "login": "", "name": "", "profile_id": None, "active": "Y", "version": "",
                    "bloqueado": False, "locked_until": None, "failed_attempts": 0, "proprio": False,
                    "registro": None}
        u = self._get(user_id)
        dados = public_view(u)
        dados.update(version=admin_crud.version(u, EDITABLE_FIELDS), bloqueado=self.is_locked(u),
                     proprio=u["id"] == ctx.get("user_id"), registro=ui_helpers.registro(u, ctx))
        return dados

    # ----------------------------------------------------------------- escrita

    def _violation(self, ctx, exc, errors):
        campo, mensagem = _FIELD_BY_CONSTRAINT.get(exc.constraint, (GENERAL_FIELD, admin_crud.MSG_FAILURE))
        errors[campo] = mensagem
        self._log.warning("cadastro de usuario rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"action": FEATURE})

    def _active_profile(self, value, errors, current_value=None):
        """Perfil escolhido: precisa estar ativo, exceto quando a edicao mantem o perfil atual."""
        pid = _id(value)
        todos = dict((p["id"], p) for p in self.profiles())
        if pid not in todos or (todos[pid]["active"] != "Y" and pid != current_value):
            errors["profile_id"] = MSG_PROFILE_INVALID
            return None, None
        return pid, todos[pid]

    def _password(self, password_value, confirmation, errors, field="senha"):
        if not isinstance(password_value, str) or not password_value:
            errors[field] = MSG_PASSWORD_REQUIRED
            return None
        if len(password_value) > auth_service.PASSWORD_MAX:
            errors[field] = MSG_PASSWORD_TOO_LONG
            return None
        problemas = security.validate_password_policy(password_value)
        if problemas:
            errors[field] = problemas[0]
            return None
        if confirmation != password_value:
            errors["confirmacao"] = MSG_CONFIRMATION
            return None
        return password_value

    def _name(self, value, errors):
        nome = admin_crud.free_text(value, errors, "name")
        if nome is None:
            errors["name"] = MSG_NAME_REQUIRED
        elif "name" not in errors and len(nome) > NAME_MAX_LENGTH:
            errors["name"] = MSG_NAME_LENGTH
        return nome

    def save(self, ctx, ip, user_id, date):
        """Inclui (login, nome, perfil_id, senha, confirmacao) ou altera (nome, perfil_id, versao).

        Retorna (id, erros). Na edicao o login e a senha enviados sao ignorados. Lanca
        RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        erros = {}
        if user_id in (None, ""):
            login = admin_crud.identifier(date.get("login"), erros, "login")
            if login is None:
                erros["login"] = MSG_LOGIN_REQUIRED
            elif "login" in erros:
                pass
            elif not _RE_LOGIN.fullmatch(login):
                erros["login"] = MSG_LOGIN_INVALID
            nome = self._name(date.get("name"), erros)
            perfil_id, perfil = self._active_profile(date.get("profile_id"), erros)
            senha = self._password(date.get("senha"), date.get("confirmacao"), erros)
            if erros:
                return None, erros
            try:
                self._require_admin(ctx, perfil["is_admin"] == "Y", "CREATE")
            except OperationDenied as exc:
                return None, {"profile_id": exc.message}
            agora = self._clock()
            novo = {"login": login, "name": nome, "profile_id": perfil_id, "active": "Y",
                    "password_hash": security.hash_password(senha), "password_changed_at": agora}
            auditoria = admin_crud.audit_entry(ctx, ip, "CREATE",
                                             admin_crud.insert_detail(dict(novo, perfil=perfil["name"]),
                                                                         INSERT_FIELDS))
            try:
                criado = self._users.insert(novo, audit=auditoria)
            except RepoViolation as exc:
                self._violation(ctx, exc, erros)
                return None, erros
            self._log.info("usuario incluido (login=%s usuario=%s)", ctx.get("login"), login,
                           extra={"action": "CREATE"})
            return criado["id"], {}

        atual = self._get(user_id)
        nome = self._name(date.get("name"), erros)
        perfil_id, perfil = self._active_profile(date.get("profile_id"), erros, atual["profile_id"])
        if erros:
            return atual["id"], erros
        if atual["id"] == ctx.get("user_id") and ctx.get("is_admin") is True and perfil["is_admin"] != "Y":
            return atual["id"], {GENERAL_FIELD: MSG_SELF_PROFILE}
        # Trocar o proprio perfil, mesmo por um nao administrativo, mudaria as proprias permissoes: so
        # administrador (CR-008 E1, revisao de 2026-10-20).
        troca_propria = atual["id"] == ctx.get("user_id") and perfil_id != atual["profile_id"]
        try:
            self._require_admin(ctx, perfil["is_admin"] == "Y" or self._admin_profile(atual["profile_id"])
                               or troca_propria, "UPDATE")
        except OperationDenied as exc:
            return atual["id"], {GENERAL_FIELD: exc.message}
        if admin_crud.text(date.get("version"), 64) != admin_crud.version(atual, EDITABLE_FIELDS):
            return atual["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        depois = dict(atual, name=nome, profile_id=perfil_id)
        detalhe = admin_crud.changes_detail(atual, depois, EDITABLE_FIELDS)
        if detalhe is None:
            return atual["id"], {}
        try:
            self._users.update(atual["id"], {"name": nome, "profile_id": perfil_id},
                                   expected=admin_crud.expected(atual, EDITABLE_FIELDS),
                                   audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detalhe))
        except RepoConflict:
            return atual["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        except RepoViolation as exc:
            self._violation(ctx, exc, erros)
            return atual["id"], erros
        self._log.info("usuario alterado (login=%s usuario=%s)", ctx.get("login"), atual["login"],
                       extra={"action": "UPDATE"})
        return atual["id"], {}

    def toggle_active(self, ctx, ip, user_id, version):
        """Desativa (DEACTIVATE) ou reativa (UPDATE) o usuario.

        Lanca OperationDenied (proprio usuario ou ultimo administrador), RepoConflict,
        RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        atual = self._get(user_id)
        novo_ativo = "N" if atual["active"] == "Y" else "Y"
        if novo_ativo == "N" and atual["id"] == ctx.get("user_id"):
            raise OperationDenied(MSG_SELF_DEACTIVATE)
        self._require_admin(ctx, self._admin_profile(atual["profile_id"]), "DEACTIVATE")
        if admin_crud.text(version, 64) != admin_crud.version(atual, EDITABLE_FIELDS):
            raise RepoConflict("versao divergente")
        detalhe = admin_crud.changes_detail(atual, dict(atual, active=novo_ativo), ("active",))
        acao = "DEACTIVATE" if novo_ativo == "N" else "UPDATE"
        try:
            alterado = self._users.update(atual["id"], {"active": novo_ativo},
                                              expected=admin_crud.expected(atual, EDITABLE_FIELDS),
                                              audit=admin_crud.audit_entry(ctx, ip, acao, detalhe))
        except RepoViolation as exc:
            if exc.constraint == "sss_ultimo_admin":
                self._log.warning("desativacao do ultimo admin negada (login=%s usuario=%s)", ctx.get("login"),
                                  atual["login"], extra={"action": acao})
                raise OperationDenied(MSG_LAST_ADMIN)
            raise
        self._log.info("usuario %s (login=%s usuario=%s)", "desativado" if novo_ativo == "N" else "reativado",
                       ctx.get("login"), atual["login"], extra={"action": acao})
        return public_view(alterado)

    def reset_password(self, ctx, ip, user_id, password_value, confirmation):
        """Define nova senha (politica + confirmacao), zera tentativas e bloqueio; audita sem o valor.

        Retorna erros por campo ({} no sucesso). Lanca OperationDenied (propria senha: usar
        'Minha senha'), RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        atual = self._get(user_id)
        if atual["id"] == ctx.get("user_id"):
            raise OperationDenied(MSG_SELF_PASSWORD)
        self._require_admin(ctx, self._admin_profile(atual["profile_id"]), "UPDATE")
        erros = {}
        password_value = self._password(password_value, confirmation, erros)
        if erros:
            return erros
        self._users.set_password(atual["id"], security.hash_password(password_value), self._clock(),
                                     audit=admin_crud.audit_entry(ctx, ip, "UPDATE", u"senha redefinida"))
        self._log.info("senha redefinida (login=%s usuario=%s)", ctx.get("login"), atual["login"],
                       extra={"action": "UPDATE"})
        return {}

    def unlock(self, ctx, ip, user_id):
        """Zera tentativas e bloqueio do usuario, com auditoria UPDATE."""
        admin_crud.require_feature(ctx, FEATURE)
        atual = self._get(user_id)
        self._require_admin(ctx, self._admin_profile(atual["profile_id"]), "UPDATE")
        detalhe = u"desbloqueado (failed_attempts: %s; locked_until: %s)" % (
            atual.get("failed_attempts") or 0, atual.get("locked_until") or u"(vazio)")
        alterado = self._users.unlock(atual["id"],
                                              audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detalhe))
        self._log.info("usuario desbloqueado (login=%s usuario=%s)", ctx.get("login"), atual["login"],
                       extra={"action": "UPDATE"})
        return public_view(alterado)


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from gluon import current
            import sss_logging
            fabrica = current.repo_factory
            _default = AdminUsersService(
                users=fabrica.get("users"),
                rbac_repo=fabrica.get("rbac"),
                log=sss_logging.get_logger("sss_web", current.sss_cfg),
            )
        return _default


def list_page(ctx, filters, page, size):
    """Pagina de usuarios sem senha_hash (servico padrao)."""
    return _service().list(ctx, filters, page, size)


def form(ctx, user_id=None):
    """Dados do formulario de usuario (servico padrao)."""
    return _service().form(ctx, user_id)


def profiles(active_only=False):
    """Perfis para selecao e filtro (servico padrao)."""
    return _service().profiles(active_only)


def save(ctx, ip, user_id, date):
    """Inclusao ou alteracao de usuario (servico padrao)."""
    return _service().save(ctx, ip, user_id, date)


def toggle_active(ctx, ip, user_id, version):
    """Desativacao/reativacao de usuario (servico padrao)."""
    return _service().toggle_active(ctx, ip, user_id, version)


def reset_password(ctx, ip, user_id, password_value, confirmation):
    """Redefinicao de senha pelo administrador (servico padrao)."""
    return _service().reset_password(ctx, ip, user_id, password_value, confirmation)


def unlock(ctx, ip, user_id):
    """Desbloqueio do usuario (servico padrao)."""
    return _service().unlock(ctx, ip, user_id)
