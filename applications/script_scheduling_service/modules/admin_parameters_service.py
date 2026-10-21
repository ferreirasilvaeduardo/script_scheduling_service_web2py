# -*- coding: utf-8 -*-
"""Dicionario de parametros (README §6.1-6.3, §6.5, §10 tabela 10). Padrao em docs/ADMIN_CRUD_PATTERN.md.

Validacao de cadastro forte: opcoes_json e regex sao validadas no servidor (o editor do cliente e so
conveniencia) e a regex nunca roda no navegador. Regras de dependencia com vinculos sao reverificadas
pelo repositorio na mesma operacao. Nao importa gluon fora de _servico.
"""
import collections
import json
import re
import threading

import admin_crud
import params_compiler
import ui_helpers
import rbac
from admin_crud import CAMPO_GERAL, OperacaoNegada
from params_compiler import ParamError, COMPONENT_TYPES
from repo_errors import RepoConflict, RepoNotFound, RepoViolation

FUNCIONALIDADE = "MANAGE_PARAMETERS"
CAMPOS_EDITAVEIS = ("param_flag", "label", "description", "component_type", "options_json", "default_value",
                    "validation_regex", "sensitive", "active")
CAMPOS_INSERCAO = ("code", "param_flag", "label", "description", "component_type", "options_json", "default_value",
                   "validation_regex", "sensitive")
TAMANHO_LABEL = 60
TAMANHO_DESCRICAO = 150
TAMANHO_PADRAO = 100
TAMANHO_REGEX = 150
ROTULOS_TIPO = (("TEXT", u"Texto"), ("NUMBER", u"Número"), ("DATE", u"Data"), ("SELECT", u"Lista de opções"),
                ("CHECKBOX", u"Sim/Não"))
MASCARA = params_compiler.MASK

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_CODIGO = re.compile(r"[a-z0-9_]{1,30}")
_RE_FILTRO = re.compile(r"[A-Za-z0-9_ .-]{1,60}")

MSG_CODIGO_OBRIGATORIO = u"Informe o código."
MSG_CODIGO_INVALIDO = u"Use de 1 a 30 caracteres: letras minúsculas, dígitos e _ (ex.: data_ref)."
MSG_CODIGO_DUPLICADO = u"Já existe um parâmetro com este código."
MSG_LABEL_OBRIGATORIO = u"Informe o rótulo exibido ao usuário."
MSG_SENSIVEL_MONOTONICO = (u"Um parâmetro sigiloso não pode deixar de ser sigiloso: respostas já gravadas "
                           u"passariam a aparecer em claro. Se o dado não for mais sigiloso, crie outro parâmetro.")
MSG_LABEL_TAMANHO = u"O rótulo deve ter no máximo %d caracteres." % TAMANHO_LABEL
MSG_DESCRICAO_TAMANHO = u"A descrição deve ter no máximo %d caracteres." % TAMANHO_DESCRICAO
MSG_TIPO_INVALIDO = u"Selecione o tipo do componente."
MSG_OPCOES_PROIBIDAS = u"Opções só existem para o tipo Lista de opções."
MSG_REGEX_SO_TEXTO = u"A validação por expressão regular só existe para o tipo Texto."
MSG_REGEX_TAMANHO = u"A expressão regular deve ter no máximo %d caracteres." % TAMANHO_REGEX
MSG_REGEX_SO_ADMIN = u"Somente administradores podem cadastrar ou alterar expressões regulares."
MSG_TIPO_COM_REGEX = (u"Este parâmetro tem expressão regular; somente administradores podem trocar o tipo "
                      u"(a regex seria removida).")
MSG_PADRAO_TAMANHO = u"O valor padrão deve ter no máximo %d caracteres." % TAMANHO_PADRAO
MSG_TESTE_REGEX_ADMIN = u"Somente administradores podem testar valores contra expressões regulares."
AVISO_SENSIVEL = u"Não use parâmetros para senhas ou credenciais. Elas ficam visíveis no processo do servidor."

_CAMPO_POR_CONSTRAINT = {
    "uk_tbsss_prm_code": ("code", MSG_CODIGO_DUPLICADO),
    "ck_tbsss_prm_code": ("code", MSG_CODIGO_INVALIDO),
}


def _id(valor):
    valor = admin_crud.texto(valor, 11)
    if valor is None or not _RE_ID.fullmatch(valor) or int(valor) < 1:
        return None
    return int(valor)


def _lista_scripts(scripts):
    return u", ".join(s["name"] for s in scripts)


def msg_tipo_vinculado(scripts):
    """Mensagem de bloqueio da troca de tipo, com os scripts vinculados."""
    return u"O tipo não pode ser alterado: o parâmetro está vinculado aos scripts %s." % _lista_scripts(scripts)


def msg_flag_nomeado(scripts):
    """Mensagem de bloqueio da troca de flag, com os scripts NOMEADO vinculados."""
    return (u"A flag não pode ser alterada: os scripts %s montam o comando por flag (NOMEADO)."
            % _lista_scripts(scripts))


def msg_vinculo_ativo(scripts):
    """Mensagem de bloqueio da desativacao, com os scripts ativos vinculados."""
    return (u"Operação negada: o parâmetro está vinculado aos scripts ativos %s. Desvincule-o ou desative "
            u"os scripts antes." % _lista_scripts(scripts))


def normalizar_filtros(entrada):
    """Filtros da lista: codigo e label (trechos), tipo_componente e ativo ('S' | 'N')."""
    entrada = entrada or {}
    filtros = {}
    for chave in ("code", "label"):
        valor = admin_crud.texto(entrada.get(chave), 60)
        if valor and _RE_FILTRO.fullmatch(valor):
            filtros[chave] = valor
    tipo = admin_crud.texto(entrada.get("component_type"), 20)
    if tipo in COMPONENT_TYPES:
        filtros["component_type"] = tipo
    ativo = admin_crud.texto(entrada.get("active"), 1)
    if ativo in ("Y", "N"):
        filtros["active"] = ativo
    return filtros


def opcoes_em_pares(texto):
    """Lista ordenada de [valor, rotulo] do opcoes_json (para a tela); None se o texto nao for um objeto JSON.

    A tela recebe pares porque o JSON.parse do navegador reordena chaves numericas.
    """
    if not texto:
        return []
    try:
        obj = json.loads(texto, object_pairs_hook=collections.OrderedDict)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    return [[str(k), v if isinstance(v, str) else ""] for k, v in obj.items()]


def _padrao_texto(valor):
    # CHECKBOX normaliza para bool; a coluna guarda texto.
    if valor is True:
        return "true"
    if valor is False:
        return "false"
    return valor


def _versao(parametro):
    """Versao do formulario; o valor_padrao sensivel entra pelo marcador (README §6.2, §10)."""
    sensiveis = ("default_value",) if parametro.get("sensitive") == "Y" else ()
    return admin_crud.versao(parametro, CAMPOS_EDITAVEIS, sensiveis=sensiveis)


class ServicoAdminParametros(object):
    """Regras do dicionario de parametros com repositorio e log injetados."""

    def __init__(self, catalogo, log):
        self._catalogo = catalogo
        self._log = log

    def _obter(self, parametro_id):
        pid = _id(parametro_id)
        if pid is None:
            raise RepoNotFound("parametro invalido")
        return self._catalogo.parameters_get(pid)

    def vinculos(self, parametro_id):
        """Scripts vinculados ao parametro: [{id, nome, tipo_param, ativo}] por nome."""
        return [{"id": s["id"], "name": s["name"], "param_type": s.get("param_type"), "active": s.get("active")}
                for s in self._catalogo.parameter_links(parametro_id)]

    # ----------------------------------------------------------------- leitura

    def list(self, ctx, filtros, pagina, tamanho):
        """Pagina de parametros (codigo ASC) com qtd_scripts; padrao de sensivel mascarado."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        resultado = self._catalogo.parameters_list(filtros=filtros, pagina=pagina, tamanho=tamanho)
        itens = []
        for p in resultado["itens"]:
            item = dict(p)
            if p.get("sensitive") == "Y" and p.get("default_value"):
                item["default_value"] = MASCARA
            itens.append(item)
        return dict(resultado, itens=itens)

    def formulario(self, ctx, parametro_id=None):
        """Dados do formulario. Padrao de parametro sensivel nunca e devolvido (apenas 'tem_padrao')."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        pode_regex = rbac.has_feature(ctx, FUNCIONALIDADE) and ctx.get("is_admin") is True
        if parametro_id in (None, ""):
            return {"id": None, "code": "", "param_flag": "", "label": "", "description": "",
                    "component_type": "TEXT", "options_json": "", "default_value": "", "tem_padrao": False,
                    "validation_regex": "", "sensitive": "N", "active": "Y", "version": "", "vinculos": [],
                    "pode_regex": pode_regex, "registro": None}
        p = self._obter(parametro_id)
        sensivel = p.get("sensitive") == "Y"
        return {
            "id": p["id"], "code": p["code"],
            "param_flag": admin_crud.normalizar(p.get("param_flag")) or "",
            "label": p.get("label") or "", "description": admin_crud.normalizar(p.get("description")) or "",
            "component_type": p["component_type"], "options_json": p.get("options_json") or "",
            "default_value": "" if sensivel else (p.get("default_value") or ""),
            "tem_padrao": bool(p.get("default_value")),
            "validation_regex": p.get("validation_regex") or "", "sensitive": p.get("sensitive") or "N",
            "active": p["active"], "version": _versao(p),
            "vinculos": self.vinculos(p["id"]), "pode_regex": pode_regex,
            "registro": ui_helpers.registro(p, ctx),
        }

    # ------------------------------------------------------------- validacao

    def _config(self, ctx, dados, atual, erros):
        """Tipo, opcoes e regex validados (a configuracao que valida valores); atual e None na inclusao."""
        admin = ctx.get("is_admin") is True
        tipo = admin_crud.texto(dados.get("component_type"), 20)
        if tipo not in COMPONENT_TYPES:
            erros["component_type"] = MSG_TIPO_INVALIDO
            tipo = None

        opcoes = admin_crud.texto(dados.get("options_json"))
        if tipo == "SELECT":
            try:
                opcoes = params_compiler.validate_registry_options(opcoes)
            except ParamError as exc:
                erros["options_json"] = exc.mensagem
                opcoes = None
        elif opcoes is not None:
            erros["options_json"] = MSG_OPCOES_PROIBIDAS
            opcoes = None

        regex_atual = (atual or {}).get("validation_regex") or None
        if admin:
            regex = admin_crud.texto(dados.get("validation_regex"))
        else:
            # Nao admin nunca altera a regex: o valor enviado e ignorado e a gravada e preservada.
            regex = regex_atual
            if regex_atual and tipo is not None and tipo != (atual or {}).get("component_type"):
                erros["component_type"] = MSG_TIPO_COM_REGEX
            elif admin_crud.texto(dados.get("validation_regex")) not in (None, regex_atual):
                erros["validation_regex"] = MSG_REGEX_SO_ADMIN
        if regex is not None and tipo not in (None, "TEXT"):
            if admin:
                erros["validation_regex"] = MSG_REGEX_SO_TEXTO
            regex = None
        elif regex is not None and admin:
            if len(regex) > TAMANHO_REGEX:
                erros["validation_regex"] = MSG_REGEX_TAMANHO
            else:
                try:
                    params_compiler.validate_registry_regex(regex)
                except ParamError as exc:
                    erros["validation_regex"] = exc.mensagem
        return tipo, opcoes, regex

    def _validar(self, ctx, dados, atual, erros):
        """Registro candidato (campos editaveis + codigo na inclusao) e erros por campo."""
        reg = {}
        if atual is None:
            codigo = admin_crud.identificador(dados.get("code"), erros, "code")
            if codigo is None:
                erros["code"] = MSG_CODIGO_OBRIGATORIO
            elif "code" in erros:
                pass
            elif not _RE_CODIGO.fullmatch(codigo):
                erros["code"] = MSG_CODIGO_INVALIDO
            reg["code"] = codigo
        else:
            reg["code"] = atual["code"]

        flag = admin_crud.texto(dados.get("param_flag"))
        if flag is not None:
            try:
                params_compiler.validate_flag(flag)
            except ParamError as exc:
                erros["param_flag"] = exc.mensagem
        label = admin_crud.texto_livre(dados.get("label"), erros, "label")
        if label is None:
            erros["label"] = MSG_LABEL_OBRIGATORIO
        elif "label" not in erros and len(label) > TAMANHO_LABEL:
            erros["label"] = MSG_LABEL_TAMANHO
        descricao = admin_crud.texto_livre(dados.get("description"), erros, "description")
        if descricao is not None and len(descricao) > TAMANHO_DESCRICAO:
            erros["description"] = MSG_DESCRICAO_TAMANHO
        tipo, opcoes, regex = self._config(ctx, dados, atual, erros)
        sensivel = "Y" if admin_crud.texto(dados.get("sensitive"), 1) == "Y" else "N"
        reg.update(param_flag=flag, label=label, description=descricao, component_type=tipo, options_json=opcoes,
                   validation_regex=regex, sensitive=sensivel)

        bruto = dados.get("default_value")
        bruto = bruto if isinstance(bruto, str) and bruto.strip() else None
        if admin_crud.texto(dados.get("remover_padrao"), 1) == "Y":
            padrao = None
        elif bruto is None and atual is not None and (atual.get("sensitive") == "Y" or sensivel == "Y"):
            # Padrao de sensivel e so de escrita: em branco mantem o gravado.
            padrao = atual.get("default_value")
            bruto = padrao
        else:
            padrao = None
        if atual is not None and atual.get("sensitive") == "Y" and sensivel == "N":
            # CR-007, R-20: S nunca volta para N (README §6.2).
            erros["sensitive"] = MSG_SENSIVEL_MONOTONICO
        if bruto is not None and not any(k in erros for k in ("component_type", "options_json", "validation_regex")):
            try:
                padrao = _padrao_texto(params_compiler.validate_value(dict(reg, code=reg["code"]), bruto))
            except ParamError as exc:
                erros["default_value"] = exc.mensagem
                padrao = None
            if padrao is not None and len(padrao) > TAMANHO_PADRAO:
                erros["default_value"] = MSG_PADRAO_TAMANHO
        reg["default_value"] = padrao
        return reg

    # ----------------------------------------------------------------- escrita

    @staticmethod
    def _para_auditoria(reg):
        # README §4.4: o detalhe nunca contem valor de parametro sensivel.
        if reg.get("sensitive") == "Y" and reg.get("default_value"):
            return dict(reg, default_value=MASCARA)
        return reg

    def _detalhe_alteracao(self, atual, depois):
        detalhe = admin_crud.detalhe_alteracoes(self._para_auditoria(atual), self._para_auditoria(depois),
                                                CAMPOS_EDITAVEIS)
        padrao_mudou = admin_crud.normalizar(atual.get("default_value")) != admin_crud.normalizar(depois.get("default_value"))
        if padrao_mudou and (atual.get("sensitive") == "Y" or depois.get("sensitive") == "Y") \
                and (detalhe is None or "default_value" not in detalhe):
            extra = u"valor_padrao: alterado (sigiloso)"
            detalhe = admin_crud.detalhe_livre(extra if detalhe is None else u"%s; %s" % (detalhe, extra))
        return detalhe

    def _dependencias(self, atual, reg, erros):
        scripts = self.vinculos(atual["id"])
        if not scripts:
            return
        if reg["component_type"] is not None and reg["component_type"] != atual["component_type"]:
            erros["component_type"] = msg_tipo_vinculado(scripts)
        nomeados = [s for s in scripts if s["param_type"] == "NAMED"]
        if nomeados and admin_crud.normalizar(reg["param_flag"]) != admin_crud.normalizar(atual.get("param_flag")):
            erros["param_flag"] = msg_flag_nomeado(nomeados)

    def _violacao(self, ctx, exc, erros, parametro_id=None):
        scripts = self.vinculos(parametro_id) if parametro_id else []
        if exc.constraint == "sss_prm_tipo_vinculado":
            erros["component_type"] = msg_tipo_vinculado(scripts)
        elif exc.constraint == "sss_prm_flag_nomeado":
            erros["param_flag"] = msg_flag_nomeado([s for s in scripts if s["param_type"] == "NAMED"])
        else:
            campo, mensagem = _CAMPO_POR_CONSTRAINT.get(exc.constraint, (CAMPO_GERAL, admin_crud.MSG_FALHA))
            erros[campo] = mensagem
        self._log.warning("cadastro de parametro rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"action": FUNCIONALIDADE})

    def salvar(self, ctx, ip, parametro_id, dados):
        """Inclui ou altera um parametro. Retorna (id, erros). codigo e imutavel depois de criado.

        Lanca RepoNotFound e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        erros = {}
        if parametro_id in (None, ""):
            reg = self._validar(ctx, dados, None, erros)
            if erros:
                return None, erros
            novo = dict(reg, active="Y")
            auditoria = admin_crud.auditoria(ctx, ip, "CREATE",
                                             admin_crud.detalhe_insercao(self._para_auditoria(novo), CAMPOS_INSERCAO))
            try:
                criado = self._catalogo.parameters_insert(novo, auditoria=auditoria)
            except RepoViolation as exc:
                self._violacao(ctx, exc, erros)
                return None, erros
            self._log.info("parametro incluido (login=%s code=%s)", ctx.get("login"), criado["code"],
                           extra={"action": "CREATE"})
            return criado["id"], {}

        atual = self._obter(parametro_id)
        reg = self._validar(ctx, dados, atual, erros)
        if not erros:
            self._dependencias(atual, reg, erros)
        if erros:
            return atual["id"], erros
        if admin_crud.texto(dados.get("version"), 64) != _versao(atual):
            return atual["id"], {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        alteracoes = dict((c, reg[c]) for c in CAMPOS_EDITAVEIS if c != "active")
        depois = dict(atual, **alteracoes)
        detalhe = self._detalhe_alteracao(atual, depois)
        if detalhe is None:
            return atual["id"], {}
        try:
            self._catalogo.parameters_update(atual["id"], alteracoes,
                                              esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
                                              auditoria=admin_crud.auditoria(ctx, ip, "UPDATE", detalhe))
        except RepoConflict:
            return atual["id"], {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        except RepoViolation as exc:
            self._violacao(ctx, exc, erros, atual["id"])
            return atual["id"], erros
        self._log.info("parametro alterado (login=%s code=%s)", ctx.get("login"), atual["code"],
                       extra={"action": "UPDATE"})
        return atual["id"], {}

    def alternar_ativo(self, ctx, ip, parametro_id, versao):
        """Desativa (bloqueado com script ativo vinculado) ou reativa o parametro.

        Lanca OperacaoNegada (mensagem lista os scripts), RepoConflict, RepoNotFound e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = self._obter(parametro_id)
        if admin_crud.texto(versao, 64) != _versao(atual):
            raise RepoConflict("versao divergente")
        novo_ativo = "N" if atual["active"] == "Y" else "Y"
        if novo_ativo == "N":
            ativos = [s for s in self.vinculos(atual["id"]) if s["active"] == "Y"]
            if ativos:
                raise OperacaoNegada(msg_vinculo_ativo(ativos))
        detalhe = admin_crud.detalhe_alteracoes(atual, dict(atual, active=novo_ativo), ("active",))
        acao = "DEACTIVATE" if novo_ativo == "N" else "UPDATE"
        try:
            alterado = self._catalogo.parameters_update(
                atual["id"], {"active": novo_ativo}, esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
                auditoria=admin_crud.auditoria(ctx, ip, acao, detalhe))
        except RepoViolation as exc:
            if exc.constraint == "sss_prm_vinculo_ativo":
                raise OperacaoNegada(msg_vinculo_ativo([s for s in self.vinculos(atual["id"]) if s["active"] == "Y"]))
            raise
        self._log.info("parametro %s (login=%s code=%s)", "desativado" if novo_ativo == "N" else "reativado",
                       ctx.get("login"), atual["code"], extra={"action": acao})
        return alterado

    def testar(self, ctx, parametro_id, dados, valor):
        """Valida 'valor' contra a configuracao em edicao (nao salva). Retorna {ok, valor | erro}.

        Regex na configuracao exige perfil admin. Parametro sensivel devolve o valor mascarado.
        Lanca RepoNotFound (id informado e inexistente) e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = self._obter(parametro_id) if parametro_id not in (None, "") else None
        erros = {}
        tipo, opcoes, regex = self._config(ctx, dados, atual, erros)
        if regex and ctx.get("is_admin") is not True:
            return {"ok": False, "erro": MSG_TESTE_REGEX_ADMIN}
        if erros:
            return {"ok": False, "erro": u"Corrija a configuração antes de testar: %s" % sorted(erros.values())[0]}
        config = {"code": (atual or {}).get("code") or "teste",
                  "label": admin_crud.texto(dados.get("label")) or u"Valor de teste",
                  "component_type": tipo, "options_json": opcoes, "validation_regex": regex,
                  "sensitive": "Y" if admin_crud.texto(dados.get("sensitive"), 1) == "Y" else "N"}
        if not isinstance(valor, str):
            return {"ok": False, "erro": u"Informe um valor para testar."}
        try:
            normalizado = _padrao_texto(params_compiler.validate_value(config, valor))
        except ParamError as exc:
            return {"ok": False, "erro": exc.mensagem}
        if admin_crud.texto(dados.get("sensitive"), 1) == "Y":
            normalizado = MASCARA
        return {"ok": True, "valor": normalizado}


_padrao = None
_lock_padrao = threading.Lock()


def _servico():
    global _padrao
    with _lock_padrao:
        if _padrao is None:
            from gluon import current
            import sss_logging
            _padrao = ServicoAdminParametros(
                catalogo=current.repo_factory.get("catalog"),
                log=sss_logging.get_logger("sss_web", current.sss_cfg),
            )
        return _padrao


def listar(ctx, filtros, pagina, tamanho):
    """Pagina de parametros (servico padrao)."""
    return _servico().list(ctx, filtros, pagina, tamanho)


def formulario(ctx, parametro_id=None):
    """Dados do formulario de parametro (servico padrao)."""
    return _servico().formulario(ctx, parametro_id)


def salvar(ctx, ip, parametro_id, dados):
    """Inclusao ou alteracao de parametro (servico padrao)."""
    return _servico().salvar(ctx, ip, parametro_id, dados)


def alternar_ativo(ctx, ip, parametro_id, versao):
    """Desativacao/reativacao de parametro (servico padrao)."""
    return _servico().alternar_ativo(ctx, ip, parametro_id, versao)


def testar(ctx, parametro_id, dados, valor):
    """Teste de valor contra a configuracao em edicao (servico padrao)."""
    return _servico().testar(ctx, parametro_id, dados, valor)
