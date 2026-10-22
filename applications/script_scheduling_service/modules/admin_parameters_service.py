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
from admin_crud import GENERAL_FIELD, OperationDenied
from params_compiler import ParamError, COMPONENT_TYPES
from repo_errors import RepoConflict, RepoNotFound, RepoViolation

FEATURE = "MANAGE_PARAMETERS"
EDITABLE_FIELDS = ("param_flag", "label", "description", "component_type", "options_json", "default_value",
                    "validation_regex", "sensitive", "active")
INSERT_FIELDS = ("code", "param_flag", "label", "description", "component_type", "options_json", "default_value",
                   "validation_regex", "sensitive")
LABEL_MAX_LENGTH = 60
DESCRIPTION_MAX_LENGTH = 150
DEFAULT_MAX_LENGTH = 100
REGEX_MAX_LENGTH = 150
TYPE_LABELS = (("TEXT", u"Texto"), ("NUMBER", u"Número"), ("DATE", u"Data"), ("SELECT", u"Lista de opções"),
                ("CHECKBOX", u"Sim/Não"))
MASK = params_compiler.MASK

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_CODE = re.compile(r"[a-z0-9_]{1,30}")
_RE_FILTER = re.compile(r"[A-Za-z0-9_ .-]{1,60}")

MSG_CODE_REQUIRED = u"Informe o código."
MSG_CODE_INVALID = u"Use de 1 a 30 caracteres: letras minúsculas, dígitos e _ (ex.: data_ref)."
MSG_CODE_DUPLICATE = u"Já existe um parâmetro com este código."
MSG_LABEL_REQUIRED = u"Informe o rótulo exibido ao usuário."
MSG_SENSITIVE_ONE_WAY = (u"Um parâmetro sigiloso não pode deixar de ser sigiloso: respostas já gravadas "
                           u"passariam a aparecer em claro. Se o dado não for mais sigiloso, crie outro parâmetro.")
MSG_LABEL_LENGTH = u"O rótulo deve ter no máximo %d caracteres." % LABEL_MAX_LENGTH
MSG_DESCRIPTION_LENGTH = u"A descrição deve ter no máximo %d caracteres." % DESCRIPTION_MAX_LENGTH
MSG_TYPE_INVALID = u"Selecione o tipo do componente."
MSG_OPTIONS_FORBIDDEN = u"Opções só existem para o tipo Lista de opções."
MSG_REGEX_TEXT_ONLY = u"A validação por expressão regular só existe para o tipo Texto."
MSG_REGEX_LENGTH = u"A expressão regular deve ter no máximo %d caracteres." % REGEX_MAX_LENGTH
MSG_REGEX_ADMIN_ONLY = u"Somente administradores podem cadastrar ou alterar expressões regulares."
MSG_TYPE_WITH_REGEX = (u"Este parâmetro tem expressão regular; somente administradores podem trocar o tipo "
                      u"(a regex seria removida).")
MSG_DEFAULT_LENGTH = u"O valor padrão deve ter no máximo %d caracteres." % DEFAULT_MAX_LENGTH
MSG_REGEX_TEST_ADMIN = u"Somente administradores podem testar valores contra expressões regulares."
SENSITIVE_WARNING = u"Não use parâmetros para senhas ou credenciais. Elas ficam visíveis no processo do servidor."

_FIELD_BY_CONSTRAINT = {
    "uk_tbsss_prm_code": ("code", MSG_CODE_DUPLICATE),
    "ck_tbsss_prm_code": ("code", MSG_CODE_INVALID),
}


def _id(value):
    value = admin_crud.text(value, 11)
    if value is None or not _RE_ID.fullmatch(value) or int(value) < 1:
        return None
    return int(value)


def _script_list(scripts):
    return u", ".join(s["name"] for s in scripts)


def msg_linked_type(scripts):
    """Mensagem de bloqueio da troca de tipo, com os scripts vinculados."""
    return u"O tipo não pode ser alterado: o parâmetro está vinculado aos scripts %s." % _script_list(scripts)


def msg_named_flag(scripts):
    """Mensagem de bloqueio da troca de flag, com os scripts NOMEADO vinculados."""
    return (u"A flag não pode ser alterada: os scripts %s montam o comando por flag (NOMEADO)."
            % _script_list(scripts))


def msg_active_link(scripts):
    """Mensagem de bloqueio da desativacao, com os scripts ativos vinculados."""
    return (u"Operação negada: o parâmetro está vinculado aos scripts ativos %s. Desvincule-o ou desative "
            u"os scripts antes." % _script_list(scripts))


def normalize_filters(input_value):
    """Filtros da lista: codigo e label (trechos), tipo_componente e ativo ('S' | 'N')."""
    input_value = input_value or {}
    filtros = {}
    for chave in ("code", "label"):
        valor = admin_crud.text(input_value.get(chave), 60)
        if valor and _RE_FILTER.fullmatch(valor):
            filtros[chave] = valor
    tipo = admin_crud.text(input_value.get("component_type"), 20)
    if tipo in COMPONENT_TYPES:
        filtros["component_type"] = tipo
    ativo = admin_crud.text(input_value.get("active"), 1)
    if ativo in ("Y", "N"):
        filtros["active"] = ativo
    return filtros


def options_as_pairs(text):
    """Lista ordenada de [valor, rotulo] do opcoes_json (para a tela); None se o texto nao for um objeto JSON.

    A tela recebe pares porque o JSON.parse do navegador reordena chaves numericas.
    """
    if not text:
        return []
    try:
        obj = json.loads(text, object_pairs_hook=collections.OrderedDict)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    return [[str(k), v if isinstance(v, str) else ""] for k, v in obj.items()]


def _default_text(value):
    # CHECKBOX normaliza para bool; a coluna guarda texto.
    if value is True:
        return "true"
    if value is False:
        return "false"
    return value


def _version(parameter):
    """Versao do formulario; o valor_padrao sensivel entra pelo marcador (README §6.2, §10)."""
    sensiveis = ("default_value",) if parameter.get("sensitive") == "Y" else ()
    return admin_crud.version(parameter, EDITABLE_FIELDS, sensitive=sensiveis)


class AdminParametersService(object):
    """Regras do dicionario de parametros com repositorio e log injetados."""

    def __init__(self, catalog, log):
        self._catalog = catalog
        self._log = log

    def _get(self, parameter_id):
        pid = _id(parameter_id)
        if pid is None:
            raise RepoNotFound("parametro invalido")
        return self._catalog.parameters_get(pid)

    def links(self, parameter_id):
        """Scripts vinculados ao parametro: [{id, nome, tipo_param, ativo}] por nome."""
        return [{"id": s["id"], "name": s["name"], "param_type": s.get("param_type"), "active": s.get("active")}
                for s in self._catalog.parameter_links(parameter_id)]

    # ----------------------------------------------------------------- leitura

    def list(self, ctx, filters, page, size):
        """Pagina de parametros (codigo ASC) com qtd_scripts; padrao de sensivel mascarado."""
        admin_crud.require_feature(ctx, FEATURE)
        resultado = self._catalog.parameters_list(filters=filters, page=page, size=size)
        itens = []
        for p in resultado["itens"]:
            item = dict(p)
            if p.get("sensitive") == "Y" and p.get("default_value"):
                item["default_value"] = MASK
            itens.append(item)
        return dict(resultado, itens=itens)

    def form(self, ctx, parameter_id=None):
        """Dados do formulario. Padrao de parametro sensivel nunca e devolvido (apenas 'tem_padrao')."""
        admin_crud.require_feature(ctx, FEATURE)
        pode_regex = rbac.has_feature(ctx, FEATURE) and ctx.get("is_admin") is True
        if parameter_id in (None, ""):
            return {"id": None, "code": "", "param_flag": "", "label": "", "description": "",
                    "component_type": "TEXT", "options_json": "", "default_value": "", "tem_padrao": False,
                    "validation_regex": "", "sensitive": "N", "active": "Y", "version": "", "vinculos": [],
                    "pode_regex": pode_regex, "registro": None}
        p = self._get(parameter_id)
        sensivel = p.get("sensitive") == "Y"
        return {
            "id": p["id"], "code": p["code"],
            "param_flag": admin_crud.normalize(p.get("param_flag")) or "",
            "label": p.get("label") or "", "description": admin_crud.normalize(p.get("description")) or "",
            "component_type": p["component_type"], "options_json": p.get("options_json") or "",
            "default_value": "" if sensivel else (p.get("default_value") or ""),
            "tem_padrao": bool(p.get("default_value")),
            "validation_regex": p.get("validation_regex") or "", "sensitive": p.get("sensitive") or "N",
            "active": p["active"], "version": _version(p),
            "vinculos": self.links(p["id"]), "pode_regex": pode_regex,
            "registro": ui_helpers.registro(p, ctx),
        }

    # ------------------------------------------------------------- validacao

    def _config(self, ctx, date, current_value, errors):
        """Tipo, opcoes e regex validados (a configuracao que valida valores); atual e None na inclusao."""
        admin = ctx.get("is_admin") is True
        tipo = admin_crud.text(date.get("component_type"), 20)
        if tipo not in COMPONENT_TYPES:
            errors["component_type"] = MSG_TYPE_INVALID
            tipo = None

        opcoes = admin_crud.text(date.get("options_json"))
        if tipo == "SELECT":
            try:
                opcoes = params_compiler.validate_registry_options(opcoes)
            except ParamError as exc:
                errors["options_json"] = exc.message
                opcoes = None
        elif opcoes is not None:
            errors["options_json"] = MSG_OPTIONS_FORBIDDEN
            opcoes = None

        regex_atual = (current_value or {}).get("validation_regex") or None
        if admin:
            regex = admin_crud.text(date.get("validation_regex"))
        else:
            # Nao admin nunca altera a regex: o valor enviado e ignorado e a gravada e preservada.
            regex = regex_atual
            if regex_atual and tipo is not None and tipo != (current_value or {}).get("component_type"):
                errors["component_type"] = MSG_TYPE_WITH_REGEX
            elif admin_crud.text(date.get("validation_regex")) not in (None, regex_atual):
                errors["validation_regex"] = MSG_REGEX_ADMIN_ONLY
        if regex is not None and tipo not in (None, "TEXT"):
            if admin:
                errors["validation_regex"] = MSG_REGEX_TEXT_ONLY
            regex = None
        elif regex is not None and admin:
            if len(regex) > REGEX_MAX_LENGTH:
                errors["validation_regex"] = MSG_REGEX_LENGTH
            else:
                try:
                    params_compiler.validate_registry_regex(regex)
                except ParamError as exc:
                    errors["validation_regex"] = exc.message
        return tipo, opcoes, regex

    def _validate(self, ctx, date, current_value, errors):
        """Registro candidato (campos editaveis + codigo na inclusao) e erros por campo."""
        reg = {}
        if current_value is None:
            codigo = admin_crud.identifier(date.get("code"), errors, "code")
            if codigo is None:
                errors["code"] = MSG_CODE_REQUIRED
            elif "code" in errors:
                pass
            elif not _RE_CODE.fullmatch(codigo):
                errors["code"] = MSG_CODE_INVALID
            reg["code"] = codigo
        else:
            reg["code"] = current_value["code"]

        flag = admin_crud.text(date.get("param_flag"))
        if flag is not None:
            try:
                params_compiler.validate_flag(flag)
            except ParamError as exc:
                errors["param_flag"] = exc.message
        label = admin_crud.free_text(date.get("label"), errors, "label")
        if label is None:
            errors["label"] = MSG_LABEL_REQUIRED
        elif "label" not in errors and len(label) > LABEL_MAX_LENGTH:
            errors["label"] = MSG_LABEL_LENGTH
        descricao = admin_crud.free_text(date.get("description"), errors, "description")
        if descricao is not None and len(descricao) > DESCRIPTION_MAX_LENGTH:
            errors["description"] = MSG_DESCRIPTION_LENGTH
        tipo, opcoes, regex = self._config(ctx, date, current_value, errors)
        sensivel = "Y" if admin_crud.text(date.get("sensitive"), 1) == "Y" else "N"
        reg.update(param_flag=flag, label=label, description=descricao, component_type=tipo, options_json=opcoes,
                   validation_regex=regex, sensitive=sensivel)

        bruto = date.get("default_value")
        bruto = bruto if isinstance(bruto, str) and bruto.strip() else None
        if admin_crud.text(date.get("remover_padrao"), 1) == "Y":
            padrao = None
        elif bruto is None and current_value is not None and (current_value.get("sensitive") == "Y" or sensivel == "Y"):
            # Padrao de sensivel e so de escrita: em branco mantem o gravado.
            padrao = current_value.get("default_value")
            bruto = padrao
        else:
            padrao = None
        if current_value is not None and current_value.get("sensitive") == "Y" and sensivel == "N":
            # CR-007, R-20: S nunca volta para N (README §6.2).
            errors["sensitive"] = MSG_SENSITIVE_ONE_WAY
        if bruto is not None and not any(k in errors for k in ("component_type", "options_json", "validation_regex")):
            try:
                padrao = _default_text(params_compiler.validate_value(dict(reg, code=reg["code"]), bruto))
            except ParamError as exc:
                errors["default_value"] = exc.message
                padrao = None
            if padrao is not None and len(padrao) > DEFAULT_MAX_LENGTH:
                errors["default_value"] = MSG_DEFAULT_LENGTH
        reg["default_value"] = padrao
        return reg

    # ----------------------------------------------------------------- escrita

    @staticmethod
    def _for_audit(reg):
        # README §4.4: o detalhe nunca contem valor de parametro sensivel.
        if reg.get("sensitive") == "Y" and reg.get("default_value"):
            return dict(reg, default_value=MASK)
        return reg

    def _change_detail(self, current_value, after_value):
        detalhe = admin_crud.changes_detail(self._for_audit(current_value), self._for_audit(after_value),
                                                EDITABLE_FIELDS)
        padrao_mudou = admin_crud.normalize(current_value.get("default_value")) != admin_crud.normalize(after_value.get("default_value"))
        if padrao_mudou and (current_value.get("sensitive") == "Y" or after_value.get("sensitive") == "Y") \
                and (detalhe is None or "default_value" not in detalhe):
            extra = u"valor_padrao: alterado (sigiloso)"
            detalhe = admin_crud.free_detail(extra if detalhe is None else u"%s; %s" % (detalhe, extra))
        return detalhe

    def _dependencies(self, current_value, reg, errors):
        scripts = self.links(current_value["id"])
        if not scripts:
            return
        if reg["component_type"] is not None and reg["component_type"] != current_value["component_type"]:
            errors["component_type"] = msg_linked_type(scripts)
        nomeados = [s for s in scripts if s["param_type"] == "NAMED"]
        if nomeados and admin_crud.normalize(reg["param_flag"]) != admin_crud.normalize(current_value.get("param_flag")):
            errors["param_flag"] = msg_named_flag(nomeados)

    def _violation(self, ctx, exc, errors, parameter_id=None):
        scripts = self.links(parameter_id) if parameter_id else []
        if exc.constraint == "sss_prm_tipo_vinculado":
            errors["component_type"] = msg_linked_type(scripts)
        elif exc.constraint == "sss_prm_flag_nomeado":
            errors["param_flag"] = msg_named_flag([s for s in scripts if s["param_type"] == "NAMED"])
        else:
            campo, mensagem = _FIELD_BY_CONSTRAINT.get(exc.constraint, (GENERAL_FIELD, admin_crud.MSG_FAILURE))
            errors[campo] = mensagem
        self._log.warning("cadastro de parametro rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"action": FEATURE})

    def save(self, ctx, ip, parameter_id, date):
        """Inclui ou altera um parametro. Retorna (id, erros). codigo e imutavel depois de criado.

        Lanca RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        erros = {}
        if parameter_id in (None, ""):
            reg = self._validate(ctx, date, None, erros)
            if erros:
                return None, erros
            novo = dict(reg, active="Y")
            auditoria = admin_crud.audit_entry(ctx, ip, "CREATE",
                                             admin_crud.insert_detail(self._for_audit(novo), INSERT_FIELDS))
            try:
                criado = self._catalog.parameters_insert(novo, audit=auditoria)
            except RepoViolation as exc:
                self._violation(ctx, exc, erros)
                return None, erros
            self._log.info("parametro incluido (login=%s code=%s)", ctx.get("login"), criado["code"],
                           extra={"action": "CREATE"})
            return criado["id"], {}

        atual = self._get(parameter_id)
        reg = self._validate(ctx, date, atual, erros)
        if not erros:
            self._dependencies(atual, reg, erros)
        if erros:
            return atual["id"], erros
        if admin_crud.text(date.get("version"), 64) != _version(atual):
            return atual["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        alteracoes = dict((c, reg[c]) for c in EDITABLE_FIELDS if c != "active")
        depois = dict(atual, **alteracoes)
        detalhe = self._change_detail(atual, depois)
        if detalhe is None:
            return atual["id"], {}
        try:
            self._catalog.parameters_update(atual["id"], alteracoes,
                                              expected=admin_crud.expected(atual, EDITABLE_FIELDS),
                                              audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detalhe))
        except RepoConflict:
            return atual["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        except RepoViolation as exc:
            self._violation(ctx, exc, erros, atual["id"])
            return atual["id"], erros
        self._log.info("parametro alterado (login=%s code=%s)", ctx.get("login"), atual["code"],
                       extra={"action": "UPDATE"})
        return atual["id"], {}

    def toggle_active(self, ctx, ip, parameter_id, version):
        """Desativa (bloqueado com script ativo vinculado) ou reativa o parametro.

        Lanca OperationDenied (mensagem lista os scripts), RepoConflict, RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        atual = self._get(parameter_id)
        if admin_crud.text(version, 64) != _version(atual):
            raise RepoConflict("versao divergente")
        novo_ativo = "N" if atual["active"] == "Y" else "Y"
        if novo_ativo == "N":
            ativos = [s for s in self.links(atual["id"]) if s["active"] == "Y"]
            if ativos:
                raise OperationDenied(msg_active_link(ativos))
        detalhe = admin_crud.changes_detail(atual, dict(atual, active=novo_ativo), ("active",))
        acao = "DEACTIVATE" if novo_ativo == "N" else "UPDATE"
        try:
            alterado = self._catalog.parameters_update(
                atual["id"], {"active": novo_ativo}, expected=admin_crud.expected(atual, EDITABLE_FIELDS),
                audit=admin_crud.audit_entry(ctx, ip, acao, detalhe))
        except RepoViolation as exc:
            if exc.constraint == "sss_prm_vinculo_ativo":
                raise OperationDenied(msg_active_link([s for s in self.links(atual["id"]) if s["active"] == "Y"]))
            raise
        self._log.info("parametro %s (login=%s code=%s)", "desativado" if novo_ativo == "N" else "reativado",
                       ctx.get("login"), atual["code"], extra={"action": acao})
        return alterado

    def test_regex(self, ctx, parameter_id, date, value):
        """Valida 'valor' contra a configuracao em edicao (nao salva). Retorna {ok, valor | erro}.

        Regex na configuracao exige perfil admin. Parametro sensivel devolve o valor mascarado.
        Lanca RepoNotFound (id informado e inexistente) e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        atual = self._get(parameter_id) if parameter_id not in (None, "") else None
        erros = {}
        tipo, opcoes, regex = self._config(ctx, date, atual, erros)
        if regex and ctx.get("is_admin") is not True:
            return {"ok": False, "erro": MSG_REGEX_TEST_ADMIN}
        if erros:
            return {"ok": False, "erro": u"Corrija a configuração antes de testar: %s" % sorted(erros.values())[0]}
        config = {"code": (atual or {}).get("code") or "teste",
                  "label": admin_crud.text(date.get("label")) or u"Valor de teste",
                  "component_type": tipo, "options_json": opcoes, "validation_regex": regex,
                  "sensitive": "Y" if admin_crud.text(date.get("sensitive"), 1) == "Y" else "N"}
        if not isinstance(value, str):
            return {"ok": False, "erro": u"Informe um valor para testar."}
        try:
            normalizado = _default_text(params_compiler.validate_value(config, value))
        except ParamError as exc:
            return {"ok": False, "erro": exc.message}
        if admin_crud.text(date.get("sensitive"), 1) == "Y":
            normalizado = MASK
        return {"ok": True, "valor": normalizado}


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from gluon import current
            import sss_logging
            _default = AdminParametersService(
                catalog=current.repo_factory.get("catalog"),
                log=sss_logging.get_logger("sss_web", current.sss_cfg),
            )
        return _default


def list_page(ctx, filters, page, size):
    """Pagina de parametros (servico padrao)."""
    return _service().list(ctx, filters, page, size)


def form(ctx, parameter_id=None):
    """Dados do formulario de parametro (servico padrao)."""
    return _service().form(ctx, parameter_id)


def save(ctx, ip, parameter_id, date):
    """Inclusao ou alteracao de parametro (servico padrao)."""
    return _service().save(ctx, ip, parameter_id, date)


def toggle_active(ctx, ip, parameter_id, version):
    """Desativacao/reativacao de parametro (servico padrao)."""
    return _service().toggle_active(ctx, ip, parameter_id, version)


def test_regex(ctx, parameter_id, date, value):
    """Teste de valor contra a configuracao em edicao (servico padrao)."""
    return _service().test_regex(ctx, parameter_id, date, value)
