# -*- coding: utf-8 -*-
"""Dicionario de parametros (README §6.1-6.3, §6.5, §10 tabela 10). Padrao em docs/PADRAO_CRUD_ADMIN.md.

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
import rbac
from admin_crud import CAMPO_GERAL, OperacaoNegada
from params_compiler import ParamErro, TIPOS_COMPONENTE
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao

FUNCIONALIDADE = "CAD_PARAMETROS"
CAMPOS_EDITAVEIS = ("param_nomeado", "label", "descricao", "tipo_componente", "opcoes_json", "valor_padrao",
                    "regex_validacao", "sensivel", "ativo")
CAMPOS_INSERCAO = ("codigo", "param_nomeado", "label", "tipo_componente", "opcoes_json", "valor_padrao",
                   "regex_validacao", "sensivel")
TAMANHO_LABEL = 60
TAMANHO_DESCRICAO = 150
TAMANHO_PADRAO = 100
TAMANHO_REGEX = 150
ROTULOS_TIPO = (("TEXT", u"Texto"), ("NUMBER", u"Número"), ("DATE", u"Data"), ("SELECT", u"Lista de opções"),
                ("CHECKBOX", u"Sim/Não"))
MASCARA = params_compiler.MASCARA

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_CODIGO = re.compile(r"[a-z0-9_]{1,30}")
_RE_FILTRO = re.compile(r"[A-Za-z0-9_ .-]{1,60}")

MSG_CODIGO_OBRIGATORIO = u"Informe o código."
MSG_CODIGO_INVALIDO = u"Use de 1 a 30 caracteres: letras minúsculas, dígitos e _ (ex.: data_ref)."
MSG_CODIGO_DUPLICADO = u"Já existe um parâmetro com este código."
MSG_LABEL_OBRIGATORIO = u"Informe o rótulo exibido ao usuário."
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
    "uk_tbsss_prm_codigo": ("codigo", MSG_CODIGO_DUPLICADO),
    "ck_tbsss_prm_codigo": ("codigo", MSG_CODIGO_INVALIDO),
}


def _id(valor):
    valor = admin_crud.texto(valor, 11)
    if valor is None or not _RE_ID.fullmatch(valor) or int(valor) < 1:
        return None
    return int(valor)


def _lista_scripts(scripts):
    return u", ".join(s["nome"] for s in scripts)


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
    for chave in ("codigo", "label"):
        valor = admin_crud.texto(entrada.get(chave), 60)
        if valor and _RE_FILTRO.fullmatch(valor):
            filtros[chave] = valor
    tipo = admin_crud.texto(entrada.get("tipo_componente"), 20)
    if tipo in TIPOS_COMPONENTE:
        filtros["tipo_componente"] = tipo
    ativo = admin_crud.texto(entrada.get("ativo"), 1)
    if ativo in ("S", "N"):
        filtros["ativo"] = ativo
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
    sensiveis = ("valor_padrao",) if parametro.get("sensivel") == "S" else ()
    return admin_crud.versao(parametro, CAMPOS_EDITAVEIS, sensiveis=sensiveis)


class ServicoAdminParametros(object):
    """Regras do dicionario de parametros com repositorio e log injetados."""

    def __init__(self, catalogo, log):
        self._catalogo = catalogo
        self._log = log

    def _obter(self, parametro_id):
        pid = _id(parametro_id)
        if pid is None:
            raise RepoNaoEncontrado("parametro invalido")
        return self._catalogo.parametros_obter(pid)

    def vinculos(self, parametro_id):
        """Scripts vinculados ao parametro: [{id, nome, tipo_param, ativo}] por nome."""
        return [{"id": s["id"], "nome": s["nome"], "tipo_param": s.get("tipo_param"), "ativo": s.get("ativo")}
                for s in self._catalogo.parametro_vinculos(parametro_id)]

    # ----------------------------------------------------------------- leitura

    def listar(self, ctx, filtros, pagina, tamanho):
        """Pagina de parametros (codigo ASC) com qtd_scripts; padrao de sensivel mascarado."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        resultado = self._catalogo.parametros_listar(filtros=filtros, pagina=pagina, tamanho=tamanho)
        itens = []
        for p in resultado["itens"]:
            item = dict(p)
            if p.get("sensivel") == "S" and p.get("valor_padrao"):
                item["valor_padrao"] = MASCARA
            itens.append(item)
        return dict(resultado, itens=itens)

    def formulario(self, ctx, parametro_id=None):
        """Dados do formulario. Padrao de parametro sensivel nunca e devolvido (apenas 'tem_padrao')."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        pode_regex = rbac.tem_func(ctx, FUNCIONALIDADE) and ctx.get("is_admin") is True
        if parametro_id in (None, ""):
            return {"id": None, "codigo": "", "param_nomeado": "", "label": "", "descricao": "",
                    "tipo_componente": "TEXT", "opcoes_json": "", "valor_padrao": "", "tem_padrao": False,
                    "regex_validacao": "", "sensivel": "N", "ativo": "S", "versao": "", "vinculos": [],
                    "pode_regex": pode_regex}
        p = self._obter(parametro_id)
        sensivel = p.get("sensivel") == "S"
        return {
            "id": p["id"], "codigo": p["codigo"],
            "param_nomeado": admin_crud.normalizar(p.get("param_nomeado")) or "",
            "label": p.get("label") or "", "descricao": admin_crud.normalizar(p.get("descricao")) or "",
            "tipo_componente": p["tipo_componente"], "opcoes_json": p.get("opcoes_json") or "",
            "valor_padrao": "" if sensivel else (p.get("valor_padrao") or ""),
            "tem_padrao": bool(p.get("valor_padrao")),
            "regex_validacao": p.get("regex_validacao") or "", "sensivel": p.get("sensivel") or "N",
            "ativo": p["ativo"], "versao": _versao(p),
            "vinculos": self.vinculos(p["id"]), "pode_regex": pode_regex,
        }

    # ------------------------------------------------------------- validacao

    def _config(self, ctx, dados, atual, erros):
        """Tipo, opcoes e regex validados (a configuracao que valida valores); atual e None na inclusao."""
        admin = ctx.get("is_admin") is True
        tipo = admin_crud.texto(dados.get("tipo_componente"), 20)
        if tipo not in TIPOS_COMPONENTE:
            erros["tipo_componente"] = MSG_TIPO_INVALIDO
            tipo = None

        opcoes = admin_crud.texto(dados.get("opcoes_json"))
        if tipo == "SELECT":
            try:
                opcoes = params_compiler.validar_opcoes_cadastro(opcoes)
            except ParamErro as exc:
                erros["opcoes_json"] = exc.mensagem
                opcoes = None
        elif opcoes is not None:
            erros["opcoes_json"] = MSG_OPCOES_PROIBIDAS
            opcoes = None

        regex_atual = (atual or {}).get("regex_validacao") or None
        if admin:
            regex = admin_crud.texto(dados.get("regex_validacao"))
        else:
            # Nao admin nunca altera a regex: o valor enviado e ignorado e a gravada e preservada.
            regex = regex_atual
            if regex_atual and tipo is not None and tipo != (atual or {}).get("tipo_componente"):
                erros["tipo_componente"] = MSG_TIPO_COM_REGEX
            elif admin_crud.texto(dados.get("regex_validacao")) not in (None, regex_atual):
                erros["regex_validacao"] = MSG_REGEX_SO_ADMIN
        if regex is not None and tipo not in (None, "TEXT"):
            if admin:
                erros["regex_validacao"] = MSG_REGEX_SO_TEXTO
            regex = None
        elif regex is not None and admin:
            if len(regex) > TAMANHO_REGEX:
                erros["regex_validacao"] = MSG_REGEX_TAMANHO
            else:
                try:
                    params_compiler.validar_regex_cadastro(regex)
                except ParamErro as exc:
                    erros["regex_validacao"] = exc.mensagem
        return tipo, opcoes, regex

    def _validar(self, ctx, dados, atual, erros):
        """Registro candidato (campos editaveis + codigo na inclusao) e erros por campo."""
        reg = {}
        if atual is None:
            codigo = admin_crud.texto(dados.get("codigo"))
            if codigo is None:
                erros["codigo"] = MSG_CODIGO_OBRIGATORIO
            elif not _RE_CODIGO.fullmatch(codigo):
                erros["codigo"] = MSG_CODIGO_INVALIDO
            reg["codigo"] = codigo
        else:
            reg["codigo"] = atual["codigo"]

        flag = admin_crud.texto(dados.get("param_nomeado"))
        if flag is not None:
            try:
                params_compiler.validar_flag(flag)
            except ParamErro as exc:
                erros["param_nomeado"] = exc.mensagem
        label = admin_crud.texto(dados.get("label"))
        if label is None:
            erros["label"] = MSG_LABEL_OBRIGATORIO
        elif len(label) > TAMANHO_LABEL:
            erros["label"] = MSG_LABEL_TAMANHO
        descricao = admin_crud.texto(dados.get("descricao"))
        if descricao is not None and len(descricao) > TAMANHO_DESCRICAO:
            erros["descricao"] = MSG_DESCRICAO_TAMANHO
        tipo, opcoes, regex = self._config(ctx, dados, atual, erros)
        sensivel = "S" if admin_crud.texto(dados.get("sensivel"), 1) == "S" else "N"
        reg.update(param_nomeado=flag, label=label, descricao=descricao, tipo_componente=tipo, opcoes_json=opcoes,
                   regex_validacao=regex, sensivel=sensivel)

        bruto = dados.get("valor_padrao")
        bruto = bruto if isinstance(bruto, str) and bruto.strip() else None
        if admin_crud.texto(dados.get("remover_padrao"), 1) == "S":
            padrao = None
        elif bruto is None and atual is not None and (atual.get("sensivel") == "S" or sensivel == "S"):
            # Padrao de sensivel e so de escrita: em branco mantem o gravado.
            padrao = atual.get("valor_padrao")
            bruto = padrao
        else:
            padrao = None
        if bruto is not None and not any(k in erros for k in ("tipo_componente", "opcoes_json", "regex_validacao")):
            try:
                padrao = _padrao_texto(params_compiler.validar_valor(dict(reg, codigo=reg["codigo"]), bruto))
            except ParamErro as exc:
                erros["valor_padrao"] = exc.mensagem
                padrao = None
            if padrao is not None and len(padrao) > TAMANHO_PADRAO:
                erros["valor_padrao"] = MSG_PADRAO_TAMANHO
        reg["valor_padrao"] = padrao
        return reg

    # ----------------------------------------------------------------- escrita

    @staticmethod
    def _para_auditoria(reg):
        # README §4.4: o detalhe nunca contem valor de parametro sensivel.
        if reg.get("sensivel") == "S" and reg.get("valor_padrao"):
            return dict(reg, valor_padrao=MASCARA)
        return reg

    def _detalhe_alteracao(self, atual, depois):
        detalhe = admin_crud.detalhe_alteracoes(self._para_auditoria(atual), self._para_auditoria(depois),
                                                CAMPOS_EDITAVEIS)
        padrao_mudou = admin_crud.normalizar(atual.get("valor_padrao")) != admin_crud.normalizar(depois.get("valor_padrao"))
        if padrao_mudou and (atual.get("sensivel") == "S" or depois.get("sensivel") == "S") \
                and (detalhe is None or "valor_padrao" not in detalhe):
            extra = u"valor_padrao: alterado (sigiloso)"
            detalhe = admin_crud.limitar(extra if detalhe is None else u"%s; %s" % (detalhe, extra))
        return detalhe

    def _dependencias(self, atual, reg, erros):
        scripts = self.vinculos(atual["id"])
        if not scripts:
            return
        if reg["tipo_componente"] is not None and reg["tipo_componente"] != atual["tipo_componente"]:
            erros["tipo_componente"] = msg_tipo_vinculado(scripts)
        nomeados = [s for s in scripts if s["tipo_param"] == "NOMEADO"]
        if nomeados and admin_crud.normalizar(reg["param_nomeado"]) != admin_crud.normalizar(atual.get("param_nomeado")):
            erros["param_nomeado"] = msg_flag_nomeado(nomeados)

    def _violacao(self, ctx, exc, erros, parametro_id=None):
        scripts = self.vinculos(parametro_id) if parametro_id else []
        if exc.constraint == "sss_prm_tipo_vinculado":
            erros["tipo_componente"] = msg_tipo_vinculado(scripts)
        elif exc.constraint == "sss_prm_flag_nomeado":
            erros["param_nomeado"] = msg_flag_nomeado([s for s in scripts if s["tipo_param"] == "NOMEADO"])
        else:
            campo, mensagem = _CAMPO_POR_CONSTRAINT.get(exc.constraint, (CAMPO_GERAL, admin_crud.MSG_FALHA))
            erros[campo] = mensagem
        self._log.warning("cadastro de parametro rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"acao": FUNCIONALIDADE})

    def salvar(self, ctx, ip, parametro_id, dados):
        """Inclui ou altera um parametro. Retorna (id, erros). codigo e imutavel depois de criado.

        Lanca RepoNaoEncontrado e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        erros = {}
        if parametro_id in (None, ""):
            reg = self._validar(ctx, dados, None, erros)
            if erros:
                return None, erros
            novo = dict(reg, ativo="S")
            auditoria = admin_crud.auditoria(ctx, ip, "CAD_INSERIR",
                                             admin_crud.detalhe_insercao(self._para_auditoria(novo), CAMPOS_INSERCAO))
            try:
                criado = self._catalogo.parametros_inserir(novo, auditoria=auditoria)
            except RepoViolacao as exc:
                self._violacao(ctx, exc, erros)
                return None, erros
            self._log.info("parametro incluido (login=%s codigo=%s)", ctx.get("login"), criado["codigo"],
                           extra={"acao": "CAD_INSERIR"})
            return criado["id"], {}

        atual = self._obter(parametro_id)
        reg = self._validar(ctx, dados, atual, erros)
        if not erros:
            self._dependencias(atual, reg, erros)
        if erros:
            return atual["id"], erros
        if admin_crud.texto(dados.get("versao"), 64) != _versao(atual):
            return atual["id"], {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        alteracoes = dict((c, reg[c]) for c in CAMPOS_EDITAVEIS if c != "ativo")
        depois = dict(atual, **alteracoes)
        detalhe = self._detalhe_alteracao(atual, depois)
        if detalhe is None:
            return atual["id"], {}
        try:
            self._catalogo.parametros_alterar(atual["id"], alteracoes,
                                              esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
                                              auditoria=admin_crud.auditoria(ctx, ip, "CAD_ALTERAR", detalhe))
        except RepoConflito:
            return atual["id"], {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        except RepoViolacao as exc:
            self._violacao(ctx, exc, erros, atual["id"])
            return atual["id"], erros
        self._log.info("parametro alterado (login=%s codigo=%s)", ctx.get("login"), atual["codigo"],
                       extra={"acao": "CAD_ALTERAR"})
        return atual["id"], {}

    def alternar_ativo(self, ctx, ip, parametro_id, versao):
        """Desativa (bloqueado com script ativo vinculado) ou reativa o parametro.

        Lanca OperacaoNegada (mensagem lista os scripts), RepoConflito, RepoNaoEncontrado e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = self._obter(parametro_id)
        if admin_crud.texto(versao, 64) != _versao(atual):
            raise RepoConflito("versao divergente")
        novo_ativo = "N" if atual["ativo"] == "S" else "S"
        if novo_ativo == "N":
            ativos = [s for s in self.vinculos(atual["id"]) if s["ativo"] == "S"]
            if ativos:
                raise OperacaoNegada(msg_vinculo_ativo(ativos))
        detalhe = admin_crud.detalhe_alteracoes(atual, dict(atual, ativo=novo_ativo), ("ativo",))
        acao = "CAD_DESATIVAR" if novo_ativo == "N" else "CAD_ALTERAR"
        try:
            alterado = self._catalogo.parametros_alterar(
                atual["id"], {"ativo": novo_ativo}, esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
                auditoria=admin_crud.auditoria(ctx, ip, acao, detalhe))
        except RepoViolacao as exc:
            if exc.constraint == "sss_prm_vinculo_ativo":
                raise OperacaoNegada(msg_vinculo_ativo([s for s in self.vinculos(atual["id"]) if s["ativo"] == "S"]))
            raise
        self._log.info("parametro %s (login=%s codigo=%s)", "desativado" if novo_ativo == "N" else "reativado",
                       ctx.get("login"), atual["codigo"], extra={"acao": acao})
        return alterado

    def testar(self, ctx, parametro_id, dados, valor):
        """Valida 'valor' contra a configuracao em edicao (nao salva). Retorna {ok, valor | erro}.

        Regex na configuracao exige perfil admin. Parametro sensivel devolve o valor mascarado.
        Lanca RepoNaoEncontrado (id informado e inexistente) e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = self._obter(parametro_id) if parametro_id not in (None, "") else None
        erros = {}
        tipo, opcoes, regex = self._config(ctx, dados, atual, erros)
        if regex and ctx.get("is_admin") is not True:
            return {"ok": False, "erro": MSG_TESTE_REGEX_ADMIN}
        if erros:
            return {"ok": False, "erro": u"Corrija a configuração antes de testar: %s" % sorted(erros.values())[0]}
        config = {"codigo": (atual or {}).get("codigo") or "teste",
                  "label": admin_crud.texto(dados.get("label")) or u"Valor de teste",
                  "tipo_componente": tipo, "opcoes_json": opcoes, "regex_validacao": regex}
        if not isinstance(valor, str):
            return {"ok": False, "erro": u"Informe um valor para testar."}
        try:
            normalizado = _padrao_texto(params_compiler.validar_valor(config, valor))
        except ParamErro as exc:
            return {"ok": False, "erro": exc.mensagem}
        if admin_crud.texto(dados.get("sensivel"), 1) == "S":
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
                catalogo=current.repo_factory.obter("catalogo"),
                log=sss_logging.obter_logger("sss_web", current.sss_cfg),
            )
        return _padrao


def listar(ctx, filtros, pagina, tamanho):
    """Pagina de parametros (servico padrao)."""
    return _servico().listar(ctx, filtros, pagina, tamanho)


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
