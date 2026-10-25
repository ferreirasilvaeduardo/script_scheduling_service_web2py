# -*- coding: utf-8 -*-
"""Dicionario de parametros (README §6.1-6.3, §6.5, §10 tabela 10). Padrao em docs/ADMIN_CRUD_PATTERN.md.

Validacao de cadastro forte: options_json e regex sao validadas no servidor (o editor do cliente e so
conveniencia) e a regex nunca roda no navegador. Regras de dependencia com vinculos sao reverificadas
pelo repositorio na mesma operacao. Nao importa gluon.
"""
import collections
import json
import re
import threading

import admin_crud
from sss.core import params_compiler
import ui_helpers
from sss.core import rbac
import schedules_service
from admin_crud import GENERAL_FIELD, OperationDenied
from sss.core.params_compiler import ParamError, COMPONENT_TYPES
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

MSG_RULES_NOTE = (u"Este parâmetro é usado por %d regra(s) de agendamento ativa(s). Mudar as opções, a regex, o tipo "
                  u"ou o padrão pode invalidar as respostas guardadas e pausar essas regras; o sistema avisa ao salvar.")
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
    """Filtros da lista: codigo e label (trechos), component_type e ativo ('S' | 'N')."""
    input_value = input_value or {}
    filters = {}
    for key in ("code", "label"):
        value = admin_crud.text(input_value.get(key), 60)
        if value and _RE_FILTER.fullmatch(value):
            filters[key] = value
    kind = admin_crud.text(input_value.get("component_type"), 20)
    if kind in COMPONENT_TYPES:
        filters["component_type"] = kind
    active = admin_crud.text(input_value.get("active"), 1)
    if active in ("Y", "N"):
        filters["active"] = active
    return filters


def options_as_pairs(text):
    """Lista ordenada de [valor, rotulo] do options_json (para a tela); None se o texto nao for um objeto JSON.

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
    sensitive = ("default_value",) if parameter.get("sensitive") == "Y" else ()
    return admin_crud.version(parameter, EDITABLE_FIELDS, sensitive=sensitive)


class AdminParametersService(object):
    """Regras do dicionario de parametros com repositorio e log injetados."""

    def __init__(self, catalog, log, rules=None):
        self._catalog = catalog
        self._log = log
        # Regras de agendamento dos scripts vinculados (CR-018a): aviso antes e depois de salvar.
        self._rules = rules

    def _get(self, parameter_id):
        pid = _id(parameter_id)
        if pid is None:
            raise RepoNotFound("parametro invalido")
        return self._catalog.parameters_get(pid)

    def links(self, parameter_id):
        """Scripts vinculados ao parametro: [{id, name, param_type, active}] por nome."""
        return [{"id": s["id"], "name": s["name"], "param_type": s.get("param_type"), "active": s.get("active")}
                for s in self._catalog.parameter_links(parameter_id)]

    # ----------------------------------------------------------------- leitura

    def list(self, ctx, filters, page, size):
        """Pagina de parametros (codigo ASC) com script_count; padrao de sensivel mascarado."""
        admin_crud.require_feature(ctx, FEATURE)
        result = self._catalog.parameters_list(filters=filters, page=page, size=size)
        items = []
        for p in result["items"]:
            item = dict(p)
            if p.get("sensitive") == "Y" and p.get("default_value"):
                item["default_value"] = MASK
            items.append(item)
        return dict(result, items=items)

    def form(self, ctx, parameter_id=None):
        """Dados do formulario. Padrao de parametro sensivel nunca e devolvido (apenas 'has_default')."""
        admin_crud.require_feature(ctx, FEATURE)
        can_regex = rbac.has_feature(ctx, FEATURE) and ctx.get("is_admin") is True
        if parameter_id in (None, ""):
            return {"id": None, "code": "", "param_flag": "", "label": "", "description": "",
                    "component_type": "TEXT", "options_json": "", "default_value": "", "has_default": False,
                    "validation_regex": "", "sensitive": "N", "active": "Y", "version": "", "links": [],
                    "can_regex": can_regex, "record": None}
        p = self._get(parameter_id)
        sensitive = p.get("sensitive") == "Y"
        return {
            "id": p["id"], "code": p["code"],
            "param_flag": admin_crud.normalize(p.get("param_flag")) or "",
            "label": p.get("label") or "", "description": admin_crud.normalize(p.get("description")) or "",
            "component_type": p["component_type"], "options_json": p.get("options_json") or "",
            "default_value": "" if sensitive else (p.get("default_value") or ""),
            "has_default": bool(p.get("default_value")),
            "validation_regex": p.get("validation_regex") or "", "sensitive": p.get("sensitive") or "N",
            "active": p["active"], "version": _version(p),
            "links": self.links(p["id"]), "can_regex": can_regex,
            "record": ui_helpers.record_info(p, ctx),
            "rules_note": self.rules_note(p["id"]),
        }

    def _linked_ids(self, parameter_id):
        return [s["id"] for s in self.links(parameter_id) if s.get("active") == "Y"]

    def rules_note(self, parameter_id):
        """Aviso fixo do formulario (CR-018a): regras ativas dos scripts que usam o parametro, ou None."""
        if self._rules is None:
            return None
        rules = self._rules.active_rules(self._linked_ids(parameter_id))
        if not rules:
            return None
        return MSG_RULES_NOTE % len(rules)

    def rules_warning(self, ctx, parameter_id):
        """Aviso depois de salvar (CR-018a): regras ativas que o proximo desdobro vai pausar, ou None."""
        admin_crud.require_feature(ctx, FEATURE)
        if self._rules is None:
            return None
        ids = self._linked_ids(self._get(parameter_id)["id"])
        return schedules_service.impact_warning(self._rules.rules_at_risk(ids), len(self._rules.active_rules(ids)))

    # ------------------------------------------------------------- validacao

    def _config(self, ctx, data, current_value, errors):
        """Tipo, opcoes e regex validados (a configuracao que valida valores); atual e None na inclusao."""
        admin = ctx.get("is_admin") is True
        kind = admin_crud.text(data.get("component_type"), 20)
        if kind not in COMPONENT_TYPES:
            errors["component_type"] = MSG_TYPE_INVALID
            kind = None

        options = admin_crud.text(data.get("options_json"))
        if kind == "SELECT":
            try:
                options = params_compiler.validate_registry_options(options)
            except ParamError as exc:
                errors["options_json"] = exc.message
                options = None
        elif options is not None:
            errors["options_json"] = MSG_OPTIONS_FORBIDDEN
            options = None

        regex_current = (current_value or {}).get("validation_regex") or None
        if admin:
            regex = admin_crud.text(data.get("validation_regex"))
        else:
            # Nao admin nunca altera a regex: o valor enviado e ignorado e a gravada e preservada.
            regex = regex_current
            if regex_current and kind is not None and kind != (current_value or {}).get("component_type"):
                errors["component_type"] = MSG_TYPE_WITH_REGEX
            elif admin_crud.text(data.get("validation_regex")) not in (None, regex_current):
                errors["validation_regex"] = MSG_REGEX_ADMIN_ONLY
        if regex is not None and kind not in (None, "TEXT"):
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
        return kind, options, regex

    def _validate(self, ctx, data, current_value, errors):
        """Registro candidato (campos editaveis + codigo na inclusao) e erros por campo."""
        reg = {}
        if current_value is None:
            code = admin_crud.identifier(data.get("code"), errors, "code")
            if code is None:
                errors["code"] = MSG_CODE_REQUIRED
            elif "code" in errors:
                pass
            elif not _RE_CODE.fullmatch(code):
                errors["code"] = MSG_CODE_INVALID
            reg["code"] = code
        else:
            reg["code"] = current_value["code"]

        flag = admin_crud.text(data.get("param_flag"))
        if flag is not None:
            try:
                params_compiler.validate_flag(flag)
            except ParamError as exc:
                errors["param_flag"] = exc.message
        label = admin_crud.free_text(data.get("label"), errors, "label")
        if label is None:
            errors["label"] = MSG_LABEL_REQUIRED
        elif "label" not in errors and len(label) > LABEL_MAX_LENGTH:
            errors["label"] = MSG_LABEL_LENGTH
        description = admin_crud.free_text(data.get("description"), errors, "description")
        if description is not None and len(description) > DESCRIPTION_MAX_LENGTH:
            errors["description"] = MSG_DESCRIPTION_LENGTH
        kind, options, regex = self._config(ctx, data, current_value, errors)
        sensitive = "Y" if admin_crud.text(data.get("sensitive"), 1) == "Y" else "N"
        reg.update(param_flag=flag, label=label, description=description, component_type=kind, options_json=options,
                   validation_regex=regex, sensitive=sensitive)

        raw = data.get("default_value")
        raw = raw if isinstance(raw, str) and raw.strip() else None
        if admin_crud.text(data.get("remove_default"), 1) == "Y":
            default = None
        elif raw is None and current_value is not None and (current_value.get("sensitive") == "Y" or sensitive == "Y"):
            # Padrao de sensivel e so de escrita: em branco mantem o gravado.
            default = current_value.get("default_value")
            raw = default
        else:
            default = None
        if current_value is not None and current_value.get("sensitive") == "Y" and sensitive == "N":
            # CR-007, R-20: S nunca volta para N (README §6.2).
            errors["sensitive"] = MSG_SENSITIVE_ONE_WAY
        if raw is not None and not any(k in errors for k in ("component_type", "options_json", "validation_regex")):
            try:
                default = _default_text(params_compiler.validate_value(dict(reg, code=reg["code"]), raw))
            except ParamError as exc:
                errors["default_value"] = exc.message
                default = None
            if default is not None and len(default) > DEFAULT_MAX_LENGTH:
                errors["default_value"] = MSG_DEFAULT_LENGTH
        reg["default_value"] = default
        return reg

    # ----------------------------------------------------------------- escrita

    @staticmethod
    def _for_audit(reg):
        # README §4.4: o detalhe nunca contem valor de parametro sensivel.
        if reg.get("sensitive") == "Y" and reg.get("default_value"):
            return dict(reg, default_value=MASK)
        return reg

    def _change_detail(self, current_value, after_value):
        detail = admin_crud.changes_detail(self._for_audit(current_value), self._for_audit(after_value),
                                                EDITABLE_FIELDS)
        default_changed = admin_crud.normalize(current_value.get("default_value")) != admin_crud.normalize(after_value.get("default_value"))
        if default_changed and (current_value.get("sensitive") == "Y" or after_value.get("sensitive") == "Y") \
                and (detail is None or "default_value" not in detail):
            extra = u"valor_padrao: alterado (sigiloso)"
            detail = admin_crud.free_detail(extra if detail is None else u"%s; %s" % (detail, extra))
        return detail

    def _dependencies(self, current_value, reg, errors):
        scripts = self.links(current_value["id"])
        if not scripts:
            return
        if reg["component_type"] is not None and reg["component_type"] != current_value["component_type"]:
            errors["component_type"] = msg_linked_type(scripts)
        named = [s for s in scripts if s["param_type"] == "NAMED"]
        if named and admin_crud.normalize(reg["param_flag"]) != admin_crud.normalize(current_value.get("param_flag")):
            errors["param_flag"] = msg_named_flag(named)

    def _violation(self, ctx, exc, errors, parameter_id=None):
        scripts = self.links(parameter_id) if parameter_id else []
        if exc.constraint == "sss_prm_tipo_vinculado":
            errors["component_type"] = msg_linked_type(scripts)
        elif exc.constraint == "sss_prm_flag_nomeado":
            errors["param_flag"] = msg_named_flag([s for s in scripts if s["param_type"] == "NAMED"])
        else:
            field, message = _FIELD_BY_CONSTRAINT.get(exc.constraint, (GENERAL_FIELD, admin_crud.MSG_FAILURE))
            errors[field] = message
        self._log.warning("cadastro de parametro rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"action": FEATURE})

    def save(self, ctx, ip, parameter_id, data):
        """Inclui ou altera um parametro. Retorna (id, erros). codigo e imutavel depois de criado.

        Lanca RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        errors = {}
        if parameter_id in (None, ""):
            reg = self._validate(ctx, data, None, errors)
            if errors:
                return None, errors
            new = dict(reg, active="Y")
            audit = admin_crud.audit_entry(ctx, ip, "CREATE",
                                             admin_crud.insert_detail(self._for_audit(new), INSERT_FIELDS))
            try:
                created = self._catalog.parameters_insert(new, audit=audit)
            except RepoViolation as exc:
                self._violation(ctx, exc, errors)
                return None, errors
            self._log.info("parametro incluido (login=%s code=%s)", ctx.get("login"), created["code"],
                           extra={"action": "CREATE"})
            return created["id"], {}

        current = self._get(parameter_id)
        reg = self._validate(ctx, data, current, errors)
        if not errors:
            self._dependencies(current, reg, errors)
        if errors:
            return current["id"], errors
        if admin_crud.text(data.get("version"), 64) != _version(current):
            return current["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        changes = dict((c, reg[c]) for c in EDITABLE_FIELDS if c != "active")
        after = dict(current, **changes)
        detail = self._change_detail(current, after)
        if detail is None:
            return current["id"], {}
        try:
            self._catalog.parameters_update(current["id"], changes,
                                              expected=admin_crud.expected(current, EDITABLE_FIELDS),
                                              audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detail))
        except RepoConflict:
            return current["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        except RepoViolation as exc:
            self._violation(ctx, exc, errors, current["id"])
            return current["id"], errors
        self._log.info("parametro alterado (login=%s code=%s)", ctx.get("login"), current["code"],
                       extra={"action": "UPDATE"})
        return current["id"], {}

    def toggle_active(self, ctx, ip, parameter_id, version):
        """Desativa (bloqueado com script ativo vinculado) ou reativa o parametro.

        Lanca OperationDenied (mensagem lista os scripts), RepoConflict, RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        current = self._get(parameter_id)
        if admin_crud.text(version, 64) != _version(current):
            raise RepoConflict("versao divergente")
        new_active = "N" if current["active"] == "Y" else "Y"
        if new_active == "N":
            active = [s for s in self.links(current["id"]) if s["active"] == "Y"]
            if active:
                raise OperationDenied(msg_active_link(active))
        detail = admin_crud.changes_detail(current, dict(current, active=new_active), ("active",))
        action = "DEACTIVATE" if new_active == "N" else "UPDATE"
        try:
            changed = self._catalog.parameters_update(
                current["id"], {"active": new_active}, expected=admin_crud.expected(current, EDITABLE_FIELDS),
                audit=admin_crud.audit_entry(ctx, ip, action, detail))
        except RepoViolation as exc:
            if exc.constraint == "sss_prm_vinculo_ativo":
                raise OperationDenied(msg_active_link([s for s in self.links(current["id"]) if s["active"] == "Y"]))
            raise
        self._log.info("parametro %s (login=%s code=%s)", "desativado" if new_active == "N" else "reativado",
                       ctx.get("login"), current["code"], extra={"action": action})
        return changed

    def test_regex(self, ctx, parameter_id, data, value):
        """Valida 'value' contra a configuracao em edicao (nao salva). Retorna {ok, value | error}.

        Regex na configuracao exige perfil admin. Parametro sensivel devolve o valor mascarado.
        Lanca RepoNotFound (id informado e inexistente) e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        current = self._get(parameter_id) if parameter_id not in (None, "") else None
        errors = {}
        kind, options, regex = self._config(ctx, data, current, errors)
        if regex and ctx.get("is_admin") is not True:
            return {"ok": False, "error": MSG_REGEX_TEST_ADMIN}
        if errors:
            return {"ok": False, "error": u"Corrija a configuração antes de testar: %s" % sorted(errors.values())[0]}
        config = {"code": (current or {}).get("code") or "teste",
                  "label": admin_crud.text(data.get("label")) or u"Valor de teste",
                  "component_type": kind, "options_json": options, "validation_regex": regex,
                  "sensitive": "Y" if admin_crud.text(data.get("sensitive"), 1) == "Y" else "N"}
        if not isinstance(value, str):
            return {"ok": False, "error": u"Informe um valor para testar."}
        try:
            normalized = _default_text(params_compiler.validate_value(config, value))
        except ParamError as exc:
            return {"ok": False, "error": exc.message}
        if admin_crud.text(data.get("sensitive"), 1) == "Y":
            normalized = MASK
        return {"ok": True, "value": normalized}


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from sss.config import app_context
            import repo_factory
            from sss.config import sss_logging
            _default = AdminParametersService(
                catalog=repo_factory.get("catalog"),
                log=sss_logging.get_logger("sss_web", app_context.require_config()),
                rules=schedules_service._service(),
            )
        return _default


def list_page(ctx, filters, page, size):
    """Pagina de parametros (servico padrao)."""
    return _service().list(ctx, filters, page, size)


def rules_warning(ctx, parameter_id):
    """Regras que vao ser pausadas depois de salvar o parametro (servico padrao)."""
    return _service().rules_warning(ctx, parameter_id)


def form(ctx, parameter_id=None):
    """Dados do formulario de parametro (servico padrao)."""
    return _service().form(ctx, parameter_id)


def save(ctx, ip, parameter_id, data):
    """Inclusao ou alteracao de parametro (servico padrao)."""
    return _service().save(ctx, ip, parameter_id, data)


def toggle_active(ctx, ip, parameter_id, version):
    """Desativacao/reativacao de parametro (servico padrao)."""
    return _service().toggle_active(ctx, ip, parameter_id, version)


def test_regex(ctx, parameter_id, data, value):
    """Teste de valor contra a configuracao em edicao (servico padrao)."""
    return _service().test_regex(ctx, parameter_id, data, value)
