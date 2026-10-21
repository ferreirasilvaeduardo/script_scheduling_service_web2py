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
from admin_crud import CAMPO_GERAL
from repo_errors import RepoConflict, RepoNotFound, RepoViolation

FUNCIONALIDADE = "MANAGE_ENVIRONMENTS"
CAMPOS_EDITAVEIS = ("description", "connection", "active")
CAMPOS_INSERCAO = ("name", "description", "connection")
TAMANHO_DESCRICAO = 100
TAMANHO_CONEXAO = 250
_SCRIPTS_PAGINA = 500
_TAMANHO_CONTAGEM = 1  # so o total interessa

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_NOME = re.compile(r"[A-Z0-9_]{1,30}")
_RE_EASY_CONNECT = re.compile(r"[A-Za-z0-9._-]+:[0-9]{1,5}/[A-Za-z0-9._-]+")
_RE_ALIAS_TNS = re.compile(r"[A-Za-z0-9._-]{1,128}")
_RE_FILTRO_NOME = re.compile(r"[A-Za-z0-9_]{1,30}")

MSG_NOME_OBRIGATORIO = u"Informe o nome do ambiente."
MSG_NOME_INVALIDO = u"Use de 1 a 30 caracteres: letras maiúsculas, dígitos e _ (ex.: PRODUCAO)."
MSG_NOME_DUPLICADO = u"Já existe um ambiente com este nome."
MSG_NOME_RESERVADO = u"O nome INTERNO é reservado aos logs da aplicação. Escolha outro nome."
MSG_CONEXAO_CREDENCIAL = u"Informe apenas o DSN; credenciais ficam no secrets.cfg."
MSG_CONEXAO_INVALIDA = (u"Informe um DSN no formato host:porta/serviço (ex.: db01.local:1521/svc) "
                        u"ou um alias TNS.")
MSG_CONEXAO_TAMANHO = u"O DSN deve ter no máximo %d caracteres." % TAMANHO_CONEXAO
MSG_DESCRICAO_TAMANHO = u"A descrição deve ter no máximo %d caracteres." % TAMANHO_DESCRICAO
AVISO_DESATIVACAO = u"Agendamentos que usam este ambiente serão pausados no próximo ciclo."

_CAMPO_POR_CONSTRAINT = {
    "uk_tbsss_env_name": ("name", MSG_NOME_DUPLICADO),
    "ck_tbsss_env_name": ("name", MSG_NOME_INVALIDO),
    "ck_tbsss_env_connection": ("connection", MSG_CONEXAO_CREDENCIAL),
}


def _id(valor):
    valor = admin_crud.texto(valor, 11)
    if valor is None or not _RE_ID.fullmatch(valor) or int(valor) < 1:
        return None
    return int(valor)


def validar_conexao(valor):
    """Mensagem de erro do DSN (Easy Connect ou alias TNS, nunca credencial); None se valido ou vazio."""
    if valor is None:
        return None
    if "@" in valor:
        return MSG_CONEXAO_CREDENCIAL
    if len(valor) > TAMANHO_CONEXAO:
        return MSG_CONEXAO_TAMANHO
    if _RE_EASY_CONNECT.fullmatch(valor) or _RE_ALIAS_TNS.fullmatch(valor):
        return None
    return MSG_CONEXAO_INVALIDA


def normalizar_filtros(entrada):
    """Filtros da lista vindos de request.vars: nome (trecho) e ativo ('S' | 'N')."""
    entrada = entrada or {}
    filtros = {}
    nome = admin_crud.texto(entrada.get("name"), 30)
    if nome and _RE_FILTRO_NOME.fullmatch(nome):
        filtros["name"] = nome
    ativo = admin_crud.texto(entrada.get("active"), 1)
    if ativo in ("Y", "N"):
        filtros["active"] = ativo
    return filtros


class ServicoAdminAmbientes(object):
    """Regras do cadastro de ambientes com repositorios e log injetados."""

    def __init__(self, catalogo, agendamentos, log):
        self._catalogo = catalogo
        self._agendamentos = agendamentos
        self._log = log

    def _obter(self, ambiente_id):
        aid = _id(ambiente_id)
        if aid is None:
            raise RepoNotFound("ambiente invalido")
        return self._catalogo.environments_get(aid)

    def agendamentos_ativos(self, nome):
        """Quantidade de agendamentos ativos do ambiente (pausados no proximo desdobro se desativado)."""
        return self._agendamentos.list(filtros={"environment": nome, "active": "Y"}, pagina=1,
                                         tamanho=_TAMANHO_CONTAGEM)["total"]

    def scripts_homologados(self, nome):
        """Quantidade de scripts homologados no ambiente (deixam de poder rodar nele se for desativado)."""
        total, pagina = 0, 1
        while True:
            itens = self._catalogo.scripts_list(pagina=pagina, tamanho=_SCRIPTS_PAGINA)["itens"]
            total += sum(1 for s in itens if nome in (s.get("ambientes_homologados") or ()))
            if len(itens) < _SCRIPTS_PAGINA:
                return total
            pagina += 1

    def list(self, ctx, filtros, pagina, tamanho):
        """Pagina de ambientes (ordem nome ASC) com a versao de cada linha."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        return self._catalogo.environments_list(filtros=filtros, pagina=pagina, tamanho=tamanho)

    def formulario(self, ctx, ambiente_id=None):
        """Dados do formulario: vazio para inclusao; registro, versao e agendamentos ativos na edicao.

        Lanca RepoNotFound para id inexistente ou invalido.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        if ambiente_id in (None, ""):
            return {"id": None, "name": "", "description": "", "connection": "", "active": "Y", "version": "",
                    "agendamentos_ativos": 0, "scripts_homologados": 0, "registro": None}
        amb = self._obter(ambiente_id)
        return {
            "id": amb["id"],
            "name": amb["name"],
            "description": admin_crud.normalizar(amb.get("description")) or "",
            "connection": admin_crud.normalizar(amb.get("connection")) or "",
            "active": amb["active"],
            "version": admin_crud.versao(amb, CAMPOS_EDITAVEIS),
            "agendamentos_ativos": self.agendamentos_ativos(amb["name"]),
            "scripts_homologados": self.scripts_homologados(amb["name"]),
            "registro": ui_helpers.registro(amb, ctx),
        }

    def _validar(self, dados, erros):
        descricao = admin_crud.texto_livre(dados.get("description"), erros, "description")
        if descricao is not None and len(descricao) > TAMANHO_DESCRICAO:
            erros["description"] = MSG_DESCRICAO_TAMANHO
        conexao = admin_crud.texto(dados.get("connection"))
        erro_conexao = validar_conexao(conexao)
        if erro_conexao:
            erros["connection"] = erro_conexao
        return descricao, conexao

    def _violacao(self, ctx, exc, erros):
        campo, mensagem = _CAMPO_POR_CONSTRAINT.get(exc.constraint, (CAMPO_GERAL, admin_crud.MSG_FALHA))
        erros[campo] = mensagem
        self._log.warning("cadastro de ambiente rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"action": "MANAGE_ENVIRONMENTS"})

    def salvar(self, ctx, ip, ambiente_id, dados):
        """Inclui (ambiente_id vazio) ou altera um ambiente.

        dados: nome, descricao, conexao e versao (edicao). Na edicao o nome enviado e ignorado.
        Retorna (id, erros); erros e dict campo -> mensagem (CAMPO_GERAL para conflito/falha).
        Lanca RepoNotFound (edicao de id inexistente) e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        erros = {}
        if ambiente_id in (None, ""):
            nome = admin_crud.identificador(dados.get("name"), erros, "name")
            if nome is None:
                erros["name"] = MSG_NOME_OBRIGATORIO
            elif "name" in erros:
                pass
            elif not _RE_NOME.fullmatch(nome):
                erros["name"] = MSG_NOME_INVALIDO
            elif log_paths.ambiente_reservado(nome):
                # CR-009: a pasta de log 'interno' e dos logs sem ambiente (aplicacao).
                erros["name"] = MSG_NOME_RESERVADO
            descricao, conexao = self._validar(dados, erros)
            if erros:
                return None, erros
            novo = {"name": nome, "description": descricao, "connection": conexao, "active": "Y"}
            auditoria = admin_crud.auditoria(ctx, ip, "CREATE",
                                             admin_crud.detalhe_insercao(novo, CAMPOS_INSERCAO))
            try:
                criado = self._catalogo.environments_insert(novo, auditoria=auditoria)
            except RepoViolation as exc:
                self._violacao(ctx, exc, erros)
                return None, erros
            self._log.info("ambiente incluido (login=%s environment=%s)", ctx.get("login"), criado["name"],
                           extra={"action": "CREATE"})
            return criado["id"], {}

        atual = self._obter(ambiente_id)
        descricao, conexao = self._validar(dados, erros)
        if erros:
            return atual["id"], erros
        if admin_crud.texto(dados.get("version"), 64) != admin_crud.versao(atual, CAMPOS_EDITAVEIS):
            erros[CAMPO_GERAL] = admin_crud.MSG_CONFLITO
            return atual["id"], erros
        depois = dict(atual, description=descricao, connection=conexao)
        detalhe = admin_crud.detalhe_alteracoes(atual, depois, CAMPOS_EDITAVEIS)
        if detalhe is None:
            return atual["id"], {}
        try:
            self._catalogo.environments_update(
                atual["id"], {"description": descricao, "connection": conexao},
                esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
                auditoria=admin_crud.auditoria(ctx, ip, "UPDATE", detalhe))
        except RepoConflict:
            erros[CAMPO_GERAL] = admin_crud.MSG_CONFLITO
            return atual["id"], erros
        except RepoViolation as exc:
            self._violacao(ctx, exc, erros)
            return atual["id"], erros
        self._log.info("ambiente alterado (login=%s environment=%s)", ctx.get("login"), atual["name"],
                       extra={"action": "UPDATE"})
        return atual["id"], {}

    def alternar_ativo(self, ctx, ip, ambiente_id, versao):
        """Desativa ou reativa o ambiente; retorna o registro alterado.

        Desativar audita DEACTIVATE com a quantidade de agendamentos ativos afetados;
        reativar audita UPDATE. Lanca RepoConflict (versao divergente),
        RepoNotFound e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = self._obter(ambiente_id)
        if admin_crud.texto(versao, 64) != admin_crud.versao(atual, CAMPOS_EDITAVEIS):
            raise RepoConflict("versao divergente")
        novo_ativo = "N" if atual["active"] == "Y" else "Y"
        detalhe = admin_crud.detalhe_alteracoes(atual, dict(atual, active=novo_ativo), ("active",))
        acao = "DEACTIVATE" if novo_ativo == "N" else "UPDATE"
        if novo_ativo == "N":
            detalhe = u"%s; agendamentos ativos afetados: %d; scripts homologados afetados: %d" % (
                detalhe, self.agendamentos_ativos(atual["name"]), self.scripts_homologados(atual["name"]))
        alterado = self._catalogo.environments_update(
            atual["id"], {"active": novo_ativo}, esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
            auditoria=admin_crud.auditoria(ctx, ip, acao, detalhe))
        self._log.info("ambiente %s (login=%s environment=%s)", "desativado" if novo_ativo == "N" else "reativado",
                       ctx.get("login"), atual["name"], extra={"action": acao})
        return alterado


_padrao = None
_lock_padrao = threading.Lock()


def _servico():
    global _padrao
    with _lock_padrao:
        if _padrao is None:
            from gluon import current
            import sss_logging
            fabrica = current.repo_factory
            _padrao = ServicoAdminAmbientes(
                catalogo=fabrica.get("catalog"),
                agendamentos=fabrica.get("schedules"),
                log=sss_logging.get_logger("sss_web", current.sss_cfg),
            )
        return _padrao


def listar(ctx, filtros, pagina, tamanho):
    """Pagina de ambientes (servico padrao)."""
    return _servico().list(ctx, filtros, pagina, tamanho)


def formulario(ctx, ambiente_id=None):
    """Dados do formulario de ambiente (servico padrao)."""
    return _servico().formulario(ctx, ambiente_id)


def salvar(ctx, ip, ambiente_id, dados):
    """Inclusao ou alteracao de ambiente (servico padrao)."""
    return _servico().salvar(ctx, ip, ambiente_id, dados)


def alternar_ativo(ctx, ip, ambiente_id, versao):
    """Desativacao/reativacao de ambiente (servico padrao)."""
    return _servico().alternar_ativo(ctx, ip, ambiente_id, versao)
