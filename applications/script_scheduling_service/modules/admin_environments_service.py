# -*- coding: utf-8 -*-
"""Cadastro de ambientes (README §4.1, §4.3.D MANAGE_ENVIRONMENTS, §10 tabela 1).

Segue docs/ADMIN_CRUD_PATTERN.md. Recebe ctx e ip como parametros; o servico padrao do
processo web le a configuracao do app_context (_service). Nao importa gluon.
"""
import re
import threading

import admin_crud
import log_paths
import ui_helpers
from admin_crud import GENERAL_FIELD
from repo_errors import RepoConflict, RepoNotFound, RepoViolation

FEATURE = "MANAGE_ENVIRONMENTS"
EDITABLE_FIELDS = ("description", "connection", "is_production", "active")
INSERT_FIELDS = ("name", "description", "connection", "is_production")
DESCRIPTION_MAX_LENGTH = 100
CONNECTION_MAX_LENGTH = 250
_SCRIPTS_PAGE = 500
_COUNT_PAGE_SIZE = 1  # so o total interessa

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_NAME = re.compile(r"[A-Z0-9_]{1,30}")
# Easy Connect host[:porta]/servico: sem a porta, o Oracle usa a 1521 (CR-018, DSN do seed).
_RE_EASY_CONNECT = re.compile(r"[A-Za-z0-9._-]+(?::[0-9]{1,5})?/[A-Za-z0-9._-]+")
_RE_TNS_ALIAS = re.compile(r"[A-Za-z0-9._-]{1,128}")
_RE_NAME_FILTER = re.compile(r"[A-Za-z0-9_]{1,30}")

MSG_NAME_REQUIRED = u"Informe o nome do ambiente."
MSG_NAME_INVALID = u"Use de 1 a 30 caracteres: letras maiúsculas, dígitos e _ (ex.: PRODUCAO)."
MSG_NAME_DUPLICATE = u"Já existe um ambiente com este nome."
MSG_NAME_RESERVED = u"O nome INTERNAL é reservado aos logs da aplicação. Escolha outro nome."
MSG_CONNECTION_CREDENTIAL = u"Informe apenas o DSN; credenciais ficam no secrets.cfg."
MSG_CONNECTION_INVALID = (u"Informe um DSN no formato host[:porta]/serviço (ex.: db01.local:1521/svc ou db01.local/svc) "
                        u"ou um alias TNS.")
MSG_CONNECTION_LENGTH = u"O DSN deve ter no máximo %d caracteres." % CONNECTION_MAX_LENGTH
MSG_DESCRIPTION_LENGTH = u"A descrição deve ter no máximo %d caracteres." % DESCRIPTION_MAX_LENGTH
DEACTIVATION_WARNING = u"Agendamentos que usam este ambiente serão pausados no próximo ciclo."

_FIELD_BY_CONSTRAINT = {
    "uk_tbsss_env_name": ("name", MSG_NAME_DUPLICATE),
    "ck_tbsss_env_name": ("name", MSG_NAME_INVALID),
    "ck_tbsss_env_connection": ("connection", MSG_CONNECTION_CREDENTIAL),
}


def _id(value):
    value = admin_crud.text(value, 11)
    if value is None or not _RE_ID.fullmatch(value) or int(value) < 1:
        return None
    return int(value)


def validate_connection(value):
    """Mensagem de erro do DSN (Easy Connect ou alias TNS, nunca credencial); None se valido ou vazio."""
    if value is None:
        return None
    if "@" in value:
        return MSG_CONNECTION_CREDENTIAL
    if len(value) > CONNECTION_MAX_LENGTH:
        return MSG_CONNECTION_LENGTH
    if _RE_EASY_CONNECT.fullmatch(value) or _RE_TNS_ALIAS.fullmatch(value):
        return None
    return MSG_CONNECTION_INVALID


def normalize_filters(input_value):
    """Filtros da lista vindos de request.vars: name (trecho) e active ('Y' | 'N')."""
    input_value = input_value or {}
    filters = {}
    name = admin_crud.text(input_value.get("name"), 30)
    if name and _RE_NAME_FILTER.fullmatch(name):
        filters["name"] = name
    active = admin_crud.text(input_value.get("active"), 1)
    if active in ("Y", "N"):
        filters["active"] = active
    return filters


class AdminEnvironmentsService(object):
    """Regras do cadastro de ambientes com repositorios e log injetados."""

    def __init__(self, catalog, schedules, log):
        self._catalog = catalog
        self._schedules = schedules
        self._log = log

    def _get(self, environment_id):
        aid = _id(environment_id)
        if aid is None:
            raise RepoNotFound("ambiente invalido")
        return self._catalog.environments_get(aid)

    def active_schedules(self, name):
        """Quantidade de agendamentos ativos do ambiente (pausados no proximo desdobro se desativado)."""
        return self._schedules.list(filters={"environment": name, "active": "Y"}, page=1,
                                         size=_COUNT_PAGE_SIZE)["total"]

    def homologated_scripts(self, name):
        """Quantidade de scripts homologados no ambiente (deixam de poder rodar nele se for desativado)."""
        total, page = 0, 1
        while True:
            items = self._catalog.scripts_list(page=page, size=_SCRIPTS_PAGE)["items"]
            total += sum(1 for s in items if name in (s.get("homologated_environments") or ()))
            if len(items) < _SCRIPTS_PAGE:
                return total
            page += 1

    def list(self, ctx, filters, page, size):
        """Pagina de ambientes (ordem nome ASC) com a versao de cada linha."""
        admin_crud.require_feature(ctx, FEATURE)
        return self._catalog.environments_list(filters=filters, page=page, size=size)

    def form(self, ctx, environment_id=None):
        """Dados do formulario: vazio para inclusao; registro, versao e agendamentos ativos na edicao.

        Lanca RepoNotFound para id inexistente ou invalido.
        """
        admin_crud.require_feature(ctx, FEATURE)
        if environment_id in (None, ""):
            return {"id": None, "name": "", "description": "", "connection": "", "is_production": "N",
                    "active": "Y", "version": "",
                    "active_schedules": 0, "homologated_scripts": 0, "record": None}
        env = self._get(environment_id)
        return {
            "id": env["id"],
            "name": env["name"],
            "description": admin_crud.normalize(env.get("description")) or "",
            "connection": admin_crud.normalize(env.get("connection")) or "",
            "is_production": env.get("is_production") or "N",
            "active": env["active"],
            "version": admin_crud.version(env, EDITABLE_FIELDS),
            "active_schedules": self.active_schedules(env["name"]),
            "homologated_scripts": self.homologated_scripts(env["name"]),
            "record": ui_helpers.record_info(env, ctx),
        }

    def _validate(self, data, errors):
        description = admin_crud.free_text(data.get("description"), errors, "description")
        if description is not None and len(description) > DESCRIPTION_MAX_LENGTH:
            errors["description"] = MSG_DESCRIPTION_LENGTH
        connection = admin_crud.text(data.get("connection"))
        error_connection = validate_connection(connection)
        if error_connection:
            errors["connection"] = error_connection
        # Caixa de marcar: so "Y" liga; qualquer outro valor (ou ausente) e "N" (CR-017).
        production = "Y" if admin_crud.text(data.get("is_production"), 1) == "Y" else "N"
        return description, connection, production

    def _violation(self, ctx, exc, errors):
        field, message = _FIELD_BY_CONSTRAINT.get(exc.constraint, (GENERAL_FIELD, admin_crud.MSG_FAILURE))
        errors[field] = message
        self._log.warning("cadastro de ambiente rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"action": "MANAGE_ENVIRONMENTS"})

    def save(self, ctx, ip, environment_id, data):
        """Inclui (environment_id vazio) ou altera um ambiente.

        dados: nome, descricao, conexao, is_production ('Y' marcado) e versao (edicao). Na edicao o nome enviado e ignorado.
        Retorna (id, erros); erros e dict campo -> mensagem (GENERAL_FIELD para conflito/falha).
        Lanca RepoNotFound (edicao de id inexistente) e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        errors = {}
        if environment_id in (None, ""):
            name = admin_crud.identifier(data.get("name"), errors, "name")
            if name is None:
                errors["name"] = MSG_NAME_REQUIRED
            elif "name" in errors:
                pass
            elif not _RE_NAME.fullmatch(name):
                errors["name"] = MSG_NAME_INVALID
            elif log_paths.is_reserved_environment(name):
                # CR-009: a pasta de log 'internal' e dos logs sem ambiente (aplicacao).
                errors["name"] = MSG_NAME_RESERVED
            description, connection, production = self._validate(data, errors)
            if errors:
                return None, errors
            new = {"name": name, "description": description, "connection": connection,
                   "is_production": production, "active": "Y"}
            audit = admin_crud.audit_entry(ctx, ip, "CREATE",
                                             admin_crud.insert_detail(new, INSERT_FIELDS))
            try:
                created = self._catalog.environments_insert(new, audit=audit)
            except RepoViolation as exc:
                self._violation(ctx, exc, errors)
                return None, errors
            self._log.info("ambiente incluido (login=%s environment=%s)", ctx.get("login"), created["name"],
                           extra={"action": "CREATE"})
            return created["id"], {}

        current = self._get(environment_id)
        description, connection, production = self._validate(data, errors)
        if errors:
            return current["id"], errors
        if admin_crud.text(data.get("version"), 64) != admin_crud.version(current, EDITABLE_FIELDS):
            errors[GENERAL_FIELD] = admin_crud.MSG_CONFLICT
            return current["id"], errors
        after = dict(current, description=description, connection=connection, is_production=production)
        detail = admin_crud.changes_detail(current, after, EDITABLE_FIELDS)
        if detail is None:
            return current["id"], {}
        try:
            self._catalog.environments_update(
                current["id"], {"description": description, "connection": connection,
                                "is_production": production},
                expected=admin_crud.expected(current, EDITABLE_FIELDS),
                audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detail))
        except RepoConflict:
            errors[GENERAL_FIELD] = admin_crud.MSG_CONFLICT
            return current["id"], errors
        except RepoViolation as exc:
            self._violation(ctx, exc, errors)
            return current["id"], errors
        self._log.info("ambiente alterado (login=%s environment=%s)", ctx.get("login"), current["name"],
                       extra={"action": "UPDATE"})
        return current["id"], {}

    def toggle_active(self, ctx, ip, environment_id, version):
        """Desativa ou reativa o ambiente; retorna o registro alterado.

        Desativar audita DEACTIVATE com a quantidade de agendamentos ativos afetados;
        reativar audita UPDATE. Lanca RepoConflict (versao divergente),
        RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        current = self._get(environment_id)
        if admin_crud.text(version, 64) != admin_crud.version(current, EDITABLE_FIELDS):
            raise RepoConflict("versao divergente")
        new_active = "N" if current["active"] == "Y" else "Y"
        detail = admin_crud.changes_detail(current, dict(current, active=new_active), ("active",))
        action = "DEACTIVATE" if new_active == "N" else "UPDATE"
        if new_active == "N":
            detail = u"%s; agendamentos ativos afetados: %d; scripts homologados afetados: %d" % (
                detail, self.active_schedules(current["name"]), self.homologated_scripts(current["name"]))
        changed = self._catalog.environments_update(
            current["id"], {"active": new_active}, expected=admin_crud.expected(current, EDITABLE_FIELDS),
            audit=admin_crud.audit_entry(ctx, ip, action, detail))
        self._log.info("ambiente %s (login=%s environment=%s)", "desativado" if new_active == "N" else "reativado",
                       ctx.get("login"), current["name"], extra={"action": action})
        return changed


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
            _default = AdminEnvironmentsService(
                catalog=factory.get("catalog"),
                schedules=factory.get("schedules"),
                log=sss_logging.get_logger("sss_web", app_context.require_config()),
            )
        return _default


def list_page(ctx, filters, page, size):
    """Pagina de ambientes (servico padrao)."""
    return _service().list(ctx, filters, page, size)


def form(ctx, environment_id=None):
    """Dados do formulario de ambiente (servico padrao)."""
    return _service().form(ctx, environment_id)


def save(ctx, ip, environment_id, data):
    """Inclusao ou alteracao de ambiente (servico padrao)."""
    return _service().save(ctx, ip, environment_id, data)


def toggle_active(ctx, ip, environment_id, version):
    """Desativacao/reativacao de ambiente (servico padrao)."""
    return _service().toggle_active(ctx, ip, environment_id, version)
