# -*- coding: utf-8 -*-
"""Cadastro de ambientes (README §4.1, §4.3.D MANAGE_ENVIRONMENTS, §10 tabela 1).

Segue docs/ADMIN_CRUD_PATTERN.md. Recebe ctx e ip como parametros; o servico padrao do
processo web importa gluon apenas sob demanda (_servico).
"""
import re
import threading

import admin_crud
import log_paths
import ui_helpers
from admin_crud import GENERAL_FIELD
from repo_errors import RepoConflict, RepoNotFound, RepoViolation

FEATURE = "MANAGE_ENVIRONMENTS"
EDITABLE_FIELDS = ("description", "connection", "active")
INSERT_FIELDS = ("name", "description", "connection")
DESCRIPTION_MAX_LENGTH = 100
CONNECTION_MAX_LENGTH = 250
_SCRIPTS_PAGE = 500
_COUNT_PAGE_SIZE = 1  # so o total interessa

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_NAME = re.compile(r"[A-Z0-9_]{1,30}")
_RE_EASY_CONNECT = re.compile(r"[A-Za-z0-9._-]+:[0-9]{1,5}/[A-Za-z0-9._-]+")
_RE_TNS_ALIAS = re.compile(r"[A-Za-z0-9._-]{1,128}")
_RE_NAME_FILTER = re.compile(r"[A-Za-z0-9_]{1,30}")

MSG_NAME_REQUIRED = u"Informe o nome do ambiente."
MSG_NAME_INVALID = u"Use de 1 a 30 caracteres: letras maiúsculas, dígitos e _ (ex.: PRODUCAO)."
MSG_NAME_DUPLICATE = u"Já existe um ambiente com este nome."
MSG_NAME_RESERVED = u"O nome INTERNAL é reservado aos logs da aplicação. Escolha outro nome."
MSG_CONNECTION_CREDENTIAL = u"Informe apenas o DSN; credenciais ficam no secrets.cfg."
MSG_CONNECTION_INVALID = (u"Informe um DSN no formato host:porta/serviço (ex.: db01.local:1521/svc) "
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
    """Filtros da lista vindos de request.vars: nome (trecho) e ativo ('S' | 'N')."""
    input_value = input_value or {}
    filtros = {}
    nome = admin_crud.text(input_value.get("name"), 30)
    if nome and _RE_NAME_FILTER.fullmatch(nome):
        filtros["name"] = nome
    ativo = admin_crud.text(input_value.get("active"), 1)
    if ativo in ("Y", "N"):
        filtros["active"] = ativo
    return filtros


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
        total, pagina = 0, 1
        while True:
            itens = self._catalog.scripts_list(page=pagina, size=_SCRIPTS_PAGE)["itens"]
            total += sum(1 for s in itens if name in (s.get("ambientes_homologados") or ()))
            if len(itens) < _SCRIPTS_PAGE:
                return total
            pagina += 1

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
            return {"id": None, "name": "", "description": "", "connection": "", "active": "Y", "version": "",
                    "agendamentos_ativos": 0, "scripts_homologados": 0, "registro": None}
        amb = self._get(environment_id)
        return {
            "id": amb["id"],
            "name": amb["name"],
            "description": admin_crud.normalize(amb.get("description")) or "",
            "connection": admin_crud.normalize(amb.get("connection")) or "",
            "active": amb["active"],
            "version": admin_crud.version(amb, EDITABLE_FIELDS),
            "agendamentos_ativos": self.active_schedules(amb["name"]),
            "scripts_homologados": self.homologated_scripts(amb["name"]),
            "registro": ui_helpers.registro(amb, ctx),
        }

    def _validate(self, date, errors):
        descricao = admin_crud.free_text(date.get("description"), errors, "description")
        if descricao is not None and len(descricao) > DESCRIPTION_MAX_LENGTH:
            errors["description"] = MSG_DESCRIPTION_LENGTH
        conexao = admin_crud.text(date.get("connection"))
        erro_conexao = validate_connection(conexao)
        if erro_conexao:
            errors["connection"] = erro_conexao
        return descricao, conexao

    def _violation(self, ctx, exc, errors):
        campo, mensagem = _FIELD_BY_CONSTRAINT.get(exc.constraint, (GENERAL_FIELD, admin_crud.MSG_FAILURE))
        errors[campo] = mensagem
        self._log.warning("cadastro de ambiente rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"action": "MANAGE_ENVIRONMENTS"})

    def save(self, ctx, ip, environment_id, date):
        """Inclui (ambiente_id vazio) ou altera um ambiente.

        dados: nome, descricao, conexao e versao (edicao). Na edicao o nome enviado e ignorado.
        Retorna (id, erros); erros e dict campo -> mensagem (GENERAL_FIELD para conflito/falha).
        Lanca RepoNotFound (edicao de id inexistente) e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        erros = {}
        if environment_id in (None, ""):
            nome = admin_crud.identifier(date.get("name"), erros, "name")
            if nome is None:
                erros["name"] = MSG_NAME_REQUIRED
            elif "name" in erros:
                pass
            elif not _RE_NAME.fullmatch(nome):
                erros["name"] = MSG_NAME_INVALID
            elif log_paths.is_reserved_environment(nome):
                # CR-009: a pasta de log 'internal' e dos logs sem ambiente (aplicacao).
                erros["name"] = MSG_NAME_RESERVED
            descricao, conexao = self._validate(date, erros)
            if erros:
                return None, erros
            novo = {"name": nome, "description": descricao, "connection": conexao, "active": "Y"}
            auditoria = admin_crud.audit_entry(ctx, ip, "CREATE",
                                             admin_crud.insert_detail(novo, INSERT_FIELDS))
            try:
                criado = self._catalog.environments_insert(novo, audit=auditoria)
            except RepoViolation as exc:
                self._violation(ctx, exc, erros)
                return None, erros
            self._log.info("ambiente incluido (login=%s environment=%s)", ctx.get("login"), criado["name"],
                           extra={"action": "CREATE"})
            return criado["id"], {}

        atual = self._get(environment_id)
        descricao, conexao = self._validate(date, erros)
        if erros:
            return atual["id"], erros
        if admin_crud.text(date.get("version"), 64) != admin_crud.version(atual, EDITABLE_FIELDS):
            erros[GENERAL_FIELD] = admin_crud.MSG_CONFLICT
            return atual["id"], erros
        depois = dict(atual, description=descricao, connection=conexao)
        detalhe = admin_crud.changes_detail(atual, depois, EDITABLE_FIELDS)
        if detalhe is None:
            return atual["id"], {}
        try:
            self._catalog.environments_update(
                atual["id"], {"description": descricao, "connection": conexao},
                expected=admin_crud.expected(atual, EDITABLE_FIELDS),
                audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detalhe))
        except RepoConflict:
            erros[GENERAL_FIELD] = admin_crud.MSG_CONFLICT
            return atual["id"], erros
        except RepoViolation as exc:
            self._violation(ctx, exc, erros)
            return atual["id"], erros
        self._log.info("ambiente alterado (login=%s environment=%s)", ctx.get("login"), atual["name"],
                       extra={"action": "UPDATE"})
        return atual["id"], {}

    def toggle_active(self, ctx, ip, environment_id, version):
        """Desativa ou reativa o ambiente; retorna o registro alterado.

        Desativar audita DEACTIVATE com a quantidade de agendamentos ativos afetados;
        reativar audita UPDATE. Lanca RepoConflict (versao divergente),
        RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        atual = self._get(environment_id)
        if admin_crud.text(version, 64) != admin_crud.version(atual, EDITABLE_FIELDS):
            raise RepoConflict("versao divergente")
        novo_ativo = "N" if atual["active"] == "Y" else "Y"
        detalhe = admin_crud.changes_detail(atual, dict(atual, active=novo_ativo), ("active",))
        acao = "DEACTIVATE" if novo_ativo == "N" else "UPDATE"
        if novo_ativo == "N":
            detalhe = u"%s; agendamentos ativos afetados: %d; scripts homologados afetados: %d" % (
                detalhe, self.active_schedules(atual["name"]), self.homologated_scripts(atual["name"]))
        alterado = self._catalog.environments_update(
            atual["id"], {"active": novo_ativo}, expected=admin_crud.expected(atual, EDITABLE_FIELDS),
            audit=admin_crud.audit_entry(ctx, ip, acao, detalhe))
        self._log.info("ambiente %s (login=%s environment=%s)", "desativado" if novo_ativo == "N" else "reativado",
                       ctx.get("login"), atual["name"], extra={"action": acao})
        return alterado


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from gluon import current
            import sss_logging
            fabrica = current.repo_factory
            _default = AdminEnvironmentsService(
                catalog=fabrica.get("catalog"),
                schedules=fabrica.get("schedules"),
                log=sss_logging.get_logger("sss_web", current.sss_cfg),
            )
        return _default


def list_page(ctx, filters, page, size):
    """Pagina de ambientes (servico padrao)."""
    return _service().list(ctx, filters, page, size)


def form(ctx, environment_id=None):
    """Dados do formulario de ambiente (servico padrao)."""
    return _service().form(ctx, environment_id)


def save(ctx, ip, environment_id, date):
    """Inclusao ou alteracao de ambiente (servico padrao)."""
    return _service().save(ctx, ip, environment_id, date)


def toggle_active(ctx, ip, environment_id, version):
    """Desativacao/reativacao de ambiente (servico padrao)."""
    return _service().toggle_active(ctx, ip, environment_id, version)
