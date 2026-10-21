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


def _id(valor):
    valor = admin_crud.text(valor, 11)
    if valor is None or not _RE_ID.fullmatch(valor) or int(valor) < 1:
        return None
    return int(valor)


def public_view(usuario):
    """Copia do usuario sem senha_hash (e sem qualquer campo nao listado)."""
    return dict((c, usuario.get(c)) for c in _PUBLIC_FIELDS)


def normalize_filters(entrada):
    """Filtros da lista: login, nome (trechos), perfil_id e situacao ('S' | 'N' | 'B' bloqueados)."""
    entrada = entrada or {}
    filtros = {}
    for chave in ("login", "name"):
        valor = admin_crud.text(entrada.get(chave), 60)
        if valor and _RE_FILTER.fullmatch(valor):
            filtros[chave] = valor
    perfil = _id(entrada.get("profile_id"))
    if perfil is not None:
        filtros["profile_id"] = perfil
    situacao = admin_crud.text(entrada.get("state"), 1)
    if situacao in ("Y", "N", "B"):
        filtros["state"] = situacao
    return filtros


class AdminUsersService(object):
    """Regras do cadastro de usuarios com repositorios, relogio e log injetados."""

    def __init__(self, usuarios, rbac_repo, log, relogio=None):
        self._usuarios = usuarios
        self._rbac = rbac_repo
        self._log = log
        # Relogio do banco (README §4.2): bloqueio vigente e filtro "Bloqueados" comparam com SYSDATE.
        self._relogio = relogio or usuarios.now

    def _get(self, usuario_id):
        uid = _id(usuario_id)
        if uid is None:
            raise RepoNotFound("usuario invalido")
        return self._usuarios.get_by_id(uid)

    def profiles(self, apenas_ativos=False):
        """Perfis para selecao: lista de {id, nome, is_admin, ativo} ordenada por nome."""
        itens = self._rbac.profiles_list(filtros={"active": "Y"} if apenas_ativos else None, pagina=1,
                                         tamanho=_PROFILES_MAX)["itens"]
        return [{"id": p["id"], "name": p["name"], "is_admin": p["is_admin"], "active": p["active"]} for p in itens]

    def _admin_profile(self, perfil_id):
        try:
            return self._rbac.profiles_get(perfil_id).get("is_admin") == "Y"
        except RepoNotFound:
            return False

    def _require_admin(self, ctx, condicao, operacao):
        admin_crud.require_admin(ctx, condicao, MSG_ADMIN_ONLY, self._log, operacao)

    def is_locked(self, usuario):
        """True se o bloqueio por tentativas ainda vale agora."""
        ate = usuario.get("locked_until")
        return ate is not None and ate > self._relogio()

    # ----------------------------------------------------------------- leitura

    def list(self, ctx, filtros, pagina, tamanho):
        """Pagina de usuarios (login ASC) sem senha_hash, com perfil_nome e bloqueado."""
        admin_crud.require_feature(ctx, FEATURE)
        repo_filtros = dict((k, v) for k, v in filtros.items() if k != "state")
        situacao = filtros.get("state")
        if situacao in ("Y", "N"):
            repo_filtros["active"] = situacao
        elif situacao == "B":
            repo_filtros["bloqueado_em"] = self._relogio()
        resultado = self._usuarios.list(filtros=repo_filtros, pagina=pagina, tamanho=tamanho)
        nomes = dict((p["id"], p["name"]) for p in self.profiles())
        itens = []
        for u in resultado["itens"]:
            item = public_view(u)
            item["perfil_nome"] = nomes.get(u["profile_id"], "#%s" % u["profile_id"])
            item["bloqueado"] = self.is_locked(u)
            itens.append(item)
        return dict(resultado, itens=itens)

    def form(self, ctx, usuario_id=None):
        """Dados do formulario sem senha_hash; na edicao inclui versao, bloqueio e se e o proprio usuario."""
        admin_crud.require_feature(ctx, FEATURE)
        if usuario_id in (None, ""):
            return {"id": None, "login": "", "name": "", "profile_id": None, "active": "Y", "version": "",
                    "bloqueado": False, "locked_until": None, "failed_attempts": 0, "proprio": False,
                    "registro": None}
        u = self._get(usuario_id)
        dados = public_view(u)
        dados.update(version=admin_crud.version(u, EDITABLE_FIELDS), bloqueado=self.is_locked(u),
                     proprio=u["id"] == ctx.get("user_id"), registro=ui_helpers.registro(u, ctx))
        return dados

    # ----------------------------------------------------------------- escrita

    def _violation(self, ctx, exc, erros):
        campo, mensagem = _FIELD_BY_CONSTRAINT.get(exc.constraint, (GENERAL_FIELD, admin_crud.MSG_FAILURE))
        erros[campo] = mensagem
        self._log.warning("cadastro de usuario rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"action": FEATURE})

    def _active_profile(self, valor, erros, atual=None):
        """Perfil escolhido: precisa estar ativo, exceto quando a edicao mantem o perfil atual."""
        pid = _id(valor)
        todos = dict((p["id"], p) for p in self.profiles())
        if pid not in todos or (todos[pid]["active"] != "Y" and pid != atual):
            erros["profile_id"] = MSG_PROFILE_INVALID
            return None, None
        return pid, todos[pid]

    def _password(self, senha, confirmacao, erros, campo="senha"):
        if not isinstance(senha, str) or not senha:
            erros[campo] = MSG_PASSWORD_REQUIRED
            return None
        if len(senha) > auth_service.PASSWORD_MAX:
            erros[campo] = MSG_PASSWORD_TOO_LONG
            return None
        problemas = security.validate_password_policy(senha)
        if problemas:
            erros[campo] = problemas[0]
            return None
        if confirmacao != senha:
            erros["confirmacao"] = MSG_CONFIRMATION
            return None
        return senha

    def _name(self, valor, erros):
        nome = admin_crud.free_text(valor, erros, "name")
        if nome is None:
            erros["name"] = MSG_NAME_REQUIRED
        elif "name" not in erros and len(nome) > NAME_MAX_LENGTH:
            erros["name"] = MSG_NAME_LENGTH
        return nome

    def save(self, ctx, ip, usuario_id, dados):
        """Inclui (login, nome, perfil_id, senha, confirmacao) ou altera (nome, perfil_id, versao).

        Retorna (id, erros). Na edicao o login e a senha enviados sao ignorados. Lanca
        RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        erros = {}
        if usuario_id in (None, ""):
            login = admin_crud.identifier(dados.get("login"), erros, "login")
            if login is None:
                erros["login"] = MSG_LOGIN_REQUIRED
            elif "login" in erros:
                pass
            elif not _RE_LOGIN.fullmatch(login):
                erros["login"] = MSG_LOGIN_INVALID
            nome = self._name(dados.get("name"), erros)
            perfil_id, perfil = self._active_profile(dados.get("profile_id"), erros)
            senha = self._password(dados.get("senha"), dados.get("confirmacao"), erros)
            if erros:
                return None, erros
            try:
                self._require_admin(ctx, perfil["is_admin"] == "Y", "CREATE")
            except OperationDenied as exc:
                return None, {"profile_id": exc.mensagem}
            agora = self._relogio()
            novo = {"login": login, "name": nome, "profile_id": perfil_id, "active": "Y",
                    "password_hash": security.hash_password(senha), "password_changed_at": agora}
            auditoria = admin_crud.audit_entry(ctx, ip, "CREATE",
                                             admin_crud.insert_detail(dict(novo, perfil=perfil["name"]),
                                                                         INSERT_FIELDS))
            try:
                criado = self._usuarios.insert(novo, auditoria=auditoria)
            except RepoViolation as exc:
                self._violation(ctx, exc, erros)
                return None, erros
            self._log.info("usuario incluido (login=%s usuario=%s)", ctx.get("login"), login,
                           extra={"action": "CREATE"})
            return criado["id"], {}

        atual = self._get(usuario_id)
        nome = self._name(dados.get("name"), erros)
        perfil_id, perfil = self._active_profile(dados.get("profile_id"), erros, atual["profile_id"])
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
            return atual["id"], {GENERAL_FIELD: exc.mensagem}
        if admin_crud.text(dados.get("version"), 64) != admin_crud.version(atual, EDITABLE_FIELDS):
            return atual["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        depois = dict(atual, name=nome, profile_id=perfil_id)
        detalhe = admin_crud.changes_detail(atual, depois, EDITABLE_FIELDS)
        if detalhe is None:
            return atual["id"], {}
        try:
            self._usuarios.update(atual["id"], {"name": nome, "profile_id": perfil_id},
                                   esperado=admin_crud.expected(atual, EDITABLE_FIELDS),
                                   auditoria=admin_crud.audit_entry(ctx, ip, "UPDATE", detalhe))
        except RepoConflict:
            return atual["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        except RepoViolation as exc:
            self._violation(ctx, exc, erros)
            return atual["id"], erros
        self._log.info("usuario alterado (login=%s usuario=%s)", ctx.get("login"), atual["login"],
                       extra={"action": "UPDATE"})
        return atual["id"], {}

    def toggle_active(self, ctx, ip, usuario_id, versao):
        """Desativa (DEACTIVATE) ou reativa (UPDATE) o usuario.

        Lanca OperationDenied (proprio usuario ou ultimo administrador), RepoConflict,
        RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        atual = self._get(usuario_id)
        novo_ativo = "N" if atual["active"] == "Y" else "Y"
        if novo_ativo == "N" and atual["id"] == ctx.get("user_id"):
            raise OperationDenied(MSG_SELF_DEACTIVATE)
        self._require_admin(ctx, self._admin_profile(atual["profile_id"]), "DEACTIVATE")
        if admin_crud.text(versao, 64) != admin_crud.version(atual, EDITABLE_FIELDS):
            raise RepoConflict("versao divergente")
        detalhe = admin_crud.changes_detail(atual, dict(atual, active=novo_ativo), ("active",))
        acao = "DEACTIVATE" if novo_ativo == "N" else "UPDATE"
        try:
            alterado = self._usuarios.update(atual["id"], {"active": novo_ativo},
                                              esperado=admin_crud.expected(atual, EDITABLE_FIELDS),
                                              auditoria=admin_crud.audit_entry(ctx, ip, acao, detalhe))
        except RepoViolation as exc:
            if exc.constraint == "sss_ultimo_admin":
                self._log.warning("desativacao do ultimo admin negada (login=%s usuario=%s)", ctx.get("login"),
                                  atual["login"], extra={"action": acao})
                raise OperationDenied(MSG_LAST_ADMIN)
            raise
        self._log.info("usuario %s (login=%s usuario=%s)", "desativado" if novo_ativo == "N" else "reativado",
                       ctx.get("login"), atual["login"], extra={"action": acao})
        return public_view(alterado)

    def reset_password(self, ctx, ip, usuario_id, senha, confirmacao):
        """Define nova senha (politica + confirmacao), zera tentativas e bloqueio; audita sem o valor.

        Retorna erros por campo ({} no sucesso). Lanca OperationDenied (propria senha: usar
        'Minha senha'), RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        atual = self._get(usuario_id)
        if atual["id"] == ctx.get("user_id"):
            raise OperationDenied(MSG_SELF_PASSWORD)
        self._require_admin(ctx, self._admin_profile(atual["profile_id"]), "UPDATE")
        erros = {}
        senha = self._password(senha, confirmacao, erros)
        if erros:
            return erros
        self._usuarios.set_password(atual["id"], security.hash_password(senha), self._relogio(),
                                     auditoria=admin_crud.audit_entry(ctx, ip, "UPDATE", u"senha redefinida"))
        self._log.info("senha redefinida (login=%s usuario=%s)", ctx.get("login"), atual["login"],
                       extra={"action": "UPDATE"})
        return {}

    def unlock(self, ctx, ip, usuario_id):
        """Zera tentativas e bloqueio do usuario, com auditoria UPDATE."""
        admin_crud.require_feature(ctx, FEATURE)
        atual = self._get(usuario_id)
        self._require_admin(ctx, self._admin_profile(atual["profile_id"]), "UPDATE")
        detalhe = u"desbloqueado (failed_attempts: %s; locked_until: %s)" % (
            atual.get("failed_attempts") or 0, atual.get("locked_until") or u"(vazio)")
        alterado = self._usuarios.unlock(atual["id"],
                                              auditoria=admin_crud.audit_entry(ctx, ip, "UPDATE", detalhe))
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
                usuarios=fabrica.get("users"),
                rbac_repo=fabrica.get("rbac"),
                log=sss_logging.get_logger("sss_web", current.sss_cfg),
            )
        return _default


def list_page(ctx, filtros, pagina, tamanho):
    """Pagina de usuarios sem senha_hash (servico padrao)."""
    return _service().list(ctx, filtros, pagina, tamanho)


def form(ctx, usuario_id=None):
    """Dados do formulario de usuario (servico padrao)."""
    return _service().form(ctx, usuario_id)


def profiles(apenas_ativos=False):
    """Perfis para selecao e filtro (servico padrao)."""
    return _service().profiles(apenas_ativos)


def save(ctx, ip, usuario_id, dados):
    """Inclusao ou alteracao de usuario (servico padrao)."""
    return _service().save(ctx, ip, usuario_id, dados)


def toggle_active(ctx, ip, usuario_id, versao):
    """Desativacao/reativacao de usuario (servico padrao)."""
    return _service().toggle_active(ctx, ip, usuario_id, versao)


def reset_password(ctx, ip, usuario_id, senha, confirmacao):
    """Redefinicao de senha pelo administrador (servico padrao)."""
    return _service().reset_password(ctx, ip, usuario_id, senha, confirmacao)


def unlock(ctx, ip, usuario_id):
    """Desbloqueio do usuario (servico padrao)."""
    return _service().unlock(ctx, ip, usuario_id)
