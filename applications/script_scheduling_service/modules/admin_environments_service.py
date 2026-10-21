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
MSG_NAME_RESERVED = u"O nome INTERNO é reservado aos logs da aplicação. Escolha outro nome."
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


def _id(valor):
    valor = admin_crud.text(valor, 11)
    if valor is None or not _RE_ID.fullmatch(valor) or int(valor) < 1:
        return None
    return int(valor)


def validate_connection(valor):
    """Mensagem de erro do DSN (Easy Connect ou alias TNS, nunca credencial); None se valido ou vazio."""
    if valor is None:
        return None
    if "@" in valor:
        return MSG_CONNECTION_CREDENTIAL
    if len(valor) > CONNECTION_MAX_LENGTH:
        return MSG_CONNECTION_LENGTH
    if _RE_EASY_CONNECT.fullmatch(valor) or _RE_TNS_ALIAS.fullmatch(valor):
        return None
    return MSG_CONNECTION_INVALID


def normalize_filters(entrada):
    """Filtros da lista vindos de request.vars: nome (trecho) e ativo ('S' | 'N')."""
    entrada = entrada or {}
    filtros = {}
    nome = admin_crud.text(entrada.get("name"), 30)
    if nome and _RE_NAME_FILTER.fullmatch(nome):
        filtros["name"] = nome
    ativo = admin_crud.text(entrada.get("active"), 1)
    if ativo in ("Y", "N"):
        filtros["active"] = ativo
    return filtros


class AdminEnvironmentsService(object):
    """Regras do cadastro de ambientes com repositorios e log injetados."""

    def __init__(self, catalogo, agendamentos, log):
        self._catalogo = catalogo
        self._agendamentos = agendamentos
        self._log = log

    def _get(self, ambiente_id):
        aid = _id(ambiente_id)
        if aid is None:
            raise RepoNotFound("ambiente invalido")
        return self._catalogo.environments_get(aid)

    def active_schedules(self, nome):
        """Quantidade de agendamentos ativos do ambiente (pausados no proximo desdobro se desativado)."""
        return self._agendamentos.list(filtros={"environment": nome, "active": "Y"}, pagina=1,
                                         tamanho=_COUNT_PAGE_SIZE)["total"]

    def homologated_scripts(self, nome):
        """Quantidade de scripts homologados no ambiente (deixam de poder rodar nele se for desativado)."""
        total, pagina = 0, 1
        while True:
            itens = self._catalogo.scripts_list(pagina=pagina, tamanho=_SCRIPTS_PAGE)["itens"]
            total += sum(1 for s in itens if nome in (s.get("ambientes_homologados") or ()))
            if len(itens) < _SCRIPTS_PAGE:
                return total
            pagina += 1

    def list(self, ctx, filtros, pagina, tamanho):
        """Pagina de ambientes (ordem nome ASC) com a versao de cada linha."""
        admin_crud.require_feature(ctx, FEATURE)
        return self._catalogo.environments_list(filtros=filtros, pagina=pagina, tamanho=tamanho)

    def form(self, ctx, ambiente_id=None):
        """Dados do formulario: vazio para inclusao; registro, versao e agendamentos ativos na edicao.

        Lanca RepoNotFound para id inexistente ou invalido.
        """
        admin_crud.require_feature(ctx, FEATURE)
        if ambiente_id in (None, ""):
            return {"id": None, "name": "", "description": "", "connection": "", "active": "Y", "version": "",
                    "agendamentos_ativos": 0, "scripts_homologados": 0, "registro": None}
        amb = self._get(ambiente_id)
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

    def _validate(self, dados, erros):
        descricao = admin_crud.free_text(dados.get("description"), erros, "description")
        if descricao is not None and len(descricao) > DESCRIPTION_MAX_LENGTH:
            erros["description"] = MSG_DESCRIPTION_LENGTH
        conexao = admin_crud.text(dados.get("connection"))
        erro_conexao = validate_connection(conexao)
        if erro_conexao:
            erros["connection"] = erro_conexao
        return descricao, conexao

    def _violation(self, ctx, exc, erros):
        campo, mensagem = _FIELD_BY_CONSTRAINT.get(exc.constraint, (GENERAL_FIELD, admin_crud.MSG_FAILURE))
        erros[campo] = mensagem
        self._log.warning("cadastro de ambiente rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"action": "MANAGE_ENVIRONMENTS"})

    def save(self, ctx, ip, ambiente_id, dados):
        """Inclui (ambiente_id vazio) ou altera um ambiente.

        dados: nome, descricao, conexao e versao (edicao). Na edicao o nome enviado e ignorado.
        Retorna (id, erros); erros e dict campo -> mensagem (GENERAL_FIELD para conflito/falha).
        Lanca RepoNotFound (edicao de id inexistente) e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        erros = {}
        if ambiente_id in (None, ""):
            nome = admin_crud.identifier(dados.get("name"), erros, "name")
            if nome is None:
                erros["name"] = MSG_NAME_REQUIRED
            elif "name" in erros:
                pass
            elif not _RE_NAME.fullmatch(nome):
                erros["name"] = MSG_NAME_INVALID
            elif log_paths.ambiente_reservado(nome):
                # CR-009: a pasta de log 'interno' e dos logs sem ambiente (aplicacao).
                erros["name"] = MSG_NAME_RESERVED
            descricao, conexao = self._validate(dados, erros)
            if erros:
                return None, erros
            novo = {"name": nome, "description": descricao, "connection": conexao, "active": "Y"}
            auditoria = admin_crud.audit_entry(ctx, ip, "CREATE",
                                             admin_crud.insert_detail(novo, INSERT_FIELDS))
            try:
                criado = self._catalogo.environments_insert(novo, auditoria=auditoria)
            except RepoViolation as exc:
                self._violation(ctx, exc, erros)
                return None, erros
            self._log.info("ambiente incluido (login=%s environment=%s)", ctx.get("login"), criado["name"],
                           extra={"action": "CREATE"})
            return criado["id"], {}

        atual = self._get(ambiente_id)
        descricao, conexao = self._validate(dados, erros)
        if erros:
            return atual["id"], erros
        if admin_crud.text(dados.get("version"), 64) != admin_crud.version(atual, EDITABLE_FIELDS):
            erros[GENERAL_FIELD] = admin_crud.MSG_CONFLICT
            return atual["id"], erros
        depois = dict(atual, description=descricao, connection=conexao)
        detalhe = admin_crud.changes_detail(atual, depois, EDITABLE_FIELDS)
        if detalhe is None:
            return atual["id"], {}
        try:
            self._catalogo.environments_update(
                atual["id"], {"description": descricao, "connection": conexao},
                esperado=admin_crud.expected(atual, EDITABLE_FIELDS),
                auditoria=admin_crud.audit_entry(ctx, ip, "UPDATE", detalhe))
        except RepoConflict:
            erros[GENERAL_FIELD] = admin_crud.MSG_CONFLICT
            return atual["id"], erros
        except RepoViolation as exc:
            self._violation(ctx, exc, erros)
            return atual["id"], erros
        self._log.info("ambiente alterado (login=%s environment=%s)", ctx.get("login"), atual["name"],
                       extra={"action": "UPDATE"})
        return atual["id"], {}

    def toggle_active(self, ctx, ip, ambiente_id, versao):
        """Desativa ou reativa o ambiente; retorna o registro alterado.

        Desativar audita DEACTIVATE com a quantidade de agendamentos ativos afetados;
        reativar audita UPDATE. Lanca RepoConflict (versao divergente),
        RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        atual = self._get(ambiente_id)
        if admin_crud.text(versao, 64) != admin_crud.version(atual, EDITABLE_FIELDS):
            raise RepoConflict("versao divergente")
        novo_ativo = "N" if atual["active"] == "Y" else "Y"
        detalhe = admin_crud.changes_detail(atual, dict(atual, active=novo_ativo), ("active",))
        acao = "DEACTIVATE" if novo_ativo == "N" else "UPDATE"
        if novo_ativo == "N":
            detalhe = u"%s; agendamentos ativos afetados: %d; scripts homologados afetados: %d" % (
                detalhe, self.active_schedules(atual["name"]), self.homologated_scripts(atual["name"]))
        alterado = self._catalogo.environments_update(
            atual["id"], {"active": novo_ativo}, esperado=admin_crud.expected(atual, EDITABLE_FIELDS),
            auditoria=admin_crud.audit_entry(ctx, ip, acao, detalhe))
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
                catalogo=fabrica.get("catalog"),
                agendamentos=fabrica.get("schedules"),
                log=sss_logging.get_logger("sss_web", current.sss_cfg),
            )
        return _default


def list_page(ctx, filtros, pagina, tamanho):
    """Pagina de ambientes (servico padrao)."""
    return _service().list(ctx, filtros, pagina, tamanho)


def form(ctx, ambiente_id=None):
    """Dados do formulario de ambiente (servico padrao)."""
    return _service().form(ctx, ambiente_id)


def save(ctx, ip, ambiente_id, dados):
    """Inclusao ou alteracao de ambiente (servico padrao)."""
    return _service().save(ctx, ip, ambiente_id, dados)


def toggle_active(ctx, ip, ambiente_id, versao):
    """Desativacao/reativacao de ambiente (servico padrao)."""
    return _service().toggle_active(ctx, ip, ambiente_id, versao)
