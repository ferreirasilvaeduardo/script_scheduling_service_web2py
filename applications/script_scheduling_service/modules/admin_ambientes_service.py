# -*- coding: utf-8 -*-
"""Cadastro de ambientes (README §4.1, §4.3.D CAD_AMBIENTES, §10 tabela 1).

Segue docs/PADRAO_CRUD_ADMIN.md. Recebe ctx e ip como parametros; o servico padrao do
processo web importa gluon apenas sob demanda (_servico).
"""
import re
import threading

import admin_crud
import pastas_log
import ui_helpers
from admin_crud import CAMPO_GERAL
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao

FUNCIONALIDADE = "CAD_AMBIENTES"
CAMPOS_EDITAVEIS = ("descricao", "conexao", "ativo")
CAMPOS_INSERCAO = ("nome", "descricao", "conexao")
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
    "uk_tbsss_amb_nome": ("nome", MSG_NOME_DUPLICADO),
    "ck_tbsss_amb_nome": ("nome", MSG_NOME_INVALIDO),
    "ck_tbsss_amb_conexao": ("conexao", MSG_CONEXAO_CREDENCIAL),
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
    nome = admin_crud.texto(entrada.get("nome"), 30)
    if nome and _RE_FILTRO_NOME.fullmatch(nome):
        filtros["nome"] = nome
    ativo = admin_crud.texto(entrada.get("ativo"), 1)
    if ativo in ("S", "N"):
        filtros["ativo"] = ativo
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
            raise RepoNaoEncontrado("ambiente invalido")
        return self._catalogo.ambientes_obter(aid)

    def agendamentos_ativos(self, nome):
        """Quantidade de agendamentos ativos do ambiente (pausados no proximo desdobro se desativado)."""
        return self._agendamentos.listar(filtros={"ambiente": nome, "ativo": "S"}, pagina=1,
                                         tamanho=_TAMANHO_CONTAGEM)["total"]

    def scripts_homologados(self, nome):
        """Quantidade de scripts homologados no ambiente (deixam de poder rodar nele se for desativado)."""
        total, pagina = 0, 1
        while True:
            itens = self._catalogo.scripts_listar(pagina=pagina, tamanho=_SCRIPTS_PAGINA)["itens"]
            total += sum(1 for s in itens if nome in (s.get("ambientes_homologados") or ()))
            if len(itens) < _SCRIPTS_PAGINA:
                return total
            pagina += 1

    def listar(self, ctx, filtros, pagina, tamanho):
        """Pagina de ambientes (ordem nome ASC) com a versao de cada linha."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        return self._catalogo.ambientes_listar(filtros=filtros, pagina=pagina, tamanho=tamanho)

    def formulario(self, ctx, ambiente_id=None):
        """Dados do formulario: vazio para inclusao; registro, versao e agendamentos ativos na edicao.

        Lanca RepoNaoEncontrado para id inexistente ou invalido.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        if ambiente_id in (None, ""):
            return {"id": None, "nome": "", "descricao": "", "conexao": "", "ativo": "S", "versao": "",
                    "agendamentos_ativos": 0, "scripts_homologados": 0, "registro": None}
        amb = self._obter(ambiente_id)
        return {
            "id": amb["id"],
            "nome": amb["nome"],
            "descricao": admin_crud.normalizar(amb.get("descricao")) or "",
            "conexao": admin_crud.normalizar(amb.get("conexao")) or "",
            "ativo": amb["ativo"],
            "versao": admin_crud.versao(amb, CAMPOS_EDITAVEIS),
            "agendamentos_ativos": self.agendamentos_ativos(amb["nome"]),
            "scripts_homologados": self.scripts_homologados(amb["nome"]),
            "registro": ui_helpers.registro(amb, ctx),
        }

    def _validar(self, dados, erros):
        descricao = admin_crud.texto_livre(dados.get("descricao"), erros, "descricao")
        if descricao is not None and len(descricao) > TAMANHO_DESCRICAO:
            erros["descricao"] = MSG_DESCRICAO_TAMANHO
        conexao = admin_crud.texto(dados.get("conexao"))
        erro_conexao = validar_conexao(conexao)
        if erro_conexao:
            erros["conexao"] = erro_conexao
        return descricao, conexao

    def _violacao(self, ctx, exc, erros):
        campo, mensagem = _CAMPO_POR_CONSTRAINT.get(exc.constraint, (CAMPO_GERAL, admin_crud.MSG_FALHA))
        erros[campo] = mensagem
        self._log.warning("cadastro de ambiente rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"acao": "CAD_AMBIENTES"})

    def salvar(self, ctx, ip, ambiente_id, dados):
        """Inclui (ambiente_id vazio) ou altera um ambiente.

        dados: nome, descricao, conexao e versao (edicao). Na edicao o nome enviado e ignorado.
        Retorna (id, erros); erros e dict campo -> mensagem (CAMPO_GERAL para conflito/falha).
        Lanca RepoNaoEncontrado (edicao de id inexistente) e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        erros = {}
        if ambiente_id in (None, ""):
            nome = admin_crud.identificador(dados.get("nome"), erros, "nome")
            if nome is None:
                erros["nome"] = MSG_NOME_OBRIGATORIO
            elif "nome" in erros:
                pass
            elif not _RE_NOME.fullmatch(nome):
                erros["nome"] = MSG_NOME_INVALIDO
            elif pastas_log.ambiente_reservado(nome):
                # CR-009: a pasta de log 'interno' e dos logs sem ambiente (aplicacao).
                erros["nome"] = MSG_NOME_RESERVADO
            descricao, conexao = self._validar(dados, erros)
            if erros:
                return None, erros
            novo = {"nome": nome, "descricao": descricao, "conexao": conexao, "ativo": "S"}
            auditoria = admin_crud.auditoria(ctx, ip, "CAD_INSERIR",
                                             admin_crud.detalhe_insercao(novo, CAMPOS_INSERCAO))
            try:
                criado = self._catalogo.ambientes_inserir(novo, auditoria=auditoria)
            except RepoViolacao as exc:
                self._violacao(ctx, exc, erros)
                return None, erros
            self._log.info("ambiente incluido (login=%s ambiente=%s)", ctx.get("login"), criado["nome"],
                           extra={"acao": "CAD_INSERIR"})
            return criado["id"], {}

        atual = self._obter(ambiente_id)
        descricao, conexao = self._validar(dados, erros)
        if erros:
            return atual["id"], erros
        if admin_crud.texto(dados.get("versao"), 64) != admin_crud.versao(atual, CAMPOS_EDITAVEIS):
            erros[CAMPO_GERAL] = admin_crud.MSG_CONFLITO
            return atual["id"], erros
        depois = dict(atual, descricao=descricao, conexao=conexao)
        detalhe = admin_crud.detalhe_alteracoes(atual, depois, CAMPOS_EDITAVEIS)
        if detalhe is None:
            return atual["id"], {}
        try:
            self._catalogo.ambientes_alterar(
                atual["id"], {"descricao": descricao, "conexao": conexao},
                esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
                auditoria=admin_crud.auditoria(ctx, ip, "CAD_ALTERAR", detalhe))
        except RepoConflito:
            erros[CAMPO_GERAL] = admin_crud.MSG_CONFLITO
            return atual["id"], erros
        except RepoViolacao as exc:
            self._violacao(ctx, exc, erros)
            return atual["id"], erros
        self._log.info("ambiente alterado (login=%s ambiente=%s)", ctx.get("login"), atual["nome"],
                       extra={"acao": "CAD_ALTERAR"})
        return atual["id"], {}

    def alternar_ativo(self, ctx, ip, ambiente_id, versao):
        """Desativa ou reativa o ambiente; retorna o registro alterado.

        Desativar audita CAD_DESATIVAR com a quantidade de agendamentos ativos afetados;
        reativar audita CAD_ALTERAR. Lanca RepoConflito (versao divergente),
        RepoNaoEncontrado e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = self._obter(ambiente_id)
        if admin_crud.texto(versao, 64) != admin_crud.versao(atual, CAMPOS_EDITAVEIS):
            raise RepoConflito("versao divergente")
        novo_ativo = "N" if atual["ativo"] == "S" else "S"
        detalhe = admin_crud.detalhe_alteracoes(atual, dict(atual, ativo=novo_ativo), ("ativo",))
        acao = "CAD_DESATIVAR" if novo_ativo == "N" else "CAD_ALTERAR"
        if novo_ativo == "N":
            detalhe = u"%s; agendamentos ativos afetados: %d; scripts homologados afetados: %d" % (
                detalhe, self.agendamentos_ativos(atual["nome"]), self.scripts_homologados(atual["nome"]))
        alterado = self._catalogo.ambientes_alterar(
            atual["id"], {"ativo": novo_ativo}, esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
            auditoria=admin_crud.auditoria(ctx, ip, acao, detalhe))
        self._log.info("ambiente %s (login=%s ambiente=%s)", "desativado" if novo_ativo == "N" else "reativado",
                       ctx.get("login"), atual["nome"], extra={"acao": acao})
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
                catalogo=fabrica.obter("catalogo"),
                agendamentos=fabrica.obter("agendamentos"),
                log=sss_logging.obter_logger("sss_web", current.sss_cfg),
            )
        return _padrao


def listar(ctx, filtros, pagina, tamanho):
    """Pagina de ambientes (servico padrao)."""
    return _servico().listar(ctx, filtros, pagina, tamanho)


def formulario(ctx, ambiente_id=None):
    """Dados do formulario de ambiente (servico padrao)."""
    return _servico().formulario(ctx, ambiente_id)


def salvar(ctx, ip, ambiente_id, dados):
    """Inclusao ou alteracao de ambiente (servico padrao)."""
    return _servico().salvar(ctx, ip, ambiente_id, dados)


def alternar_ativo(ctx, ip, ambiente_id, versao):
    """Desativacao/reativacao de ambiente (servico padrao)."""
    return _servico().alternar_ativo(ctx, ip, ambiente_id, versao)
