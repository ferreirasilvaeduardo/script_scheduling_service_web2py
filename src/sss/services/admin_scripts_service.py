# -*- coding: utf-8 -*-
"""Cadastro de scripts, homologacao por ambiente e vinculo de parametros (README §4.3.A, §6.3, §8.5, §10).

Segue docs/ADMIN_CRUD_PATTERN.md. O cadastro confere so o formato do path_file e as pastas do sistema (CR-011,
S1): o arquivo e conferido pelo agente, no servidor onde o script roda. Regras de param_type x vinculos sao
reverificadas pelo repositorio na mesma operacao. Nao importa gluon.
"""
import collections
import hashlib
import json
import re
import threading

from sss.services import admin_crud
from sss.core import params_compiler
from sss.config import log_paths
from sss.platform import path_guard
from sss.services import schedules_service
from sss.ui import ui_helpers
from sss.services.admin_crud import GENERAL_FIELD, OperationDenied
from sss.core.params_compiler import ParamError, PARAM_TYPES
from sss.platform.path_guard import Code, PathGuardError
from sss.persistence.repo_errors import RepoConflict, RepoNotFound, RepoViolation

FEATURE = "MANAGE_SCRIPTS"
EDITABLE_FIELDS = ("name", "description", "script_group", "category", "stage", "interpreter", "path_file",
                    "param_type", "max_parallel_env", "timeout_s", "active")
INSERT_FIELDS = ("name", "description", "script_group", "category", "stage", "interpreter", "path_file",
                   "param_type", "max_parallel_env", "timeout_s")



# CR-026 (D3): o nome do interpretador, procurado no PATH do agente quando o script nao tem #! valido nem
# interpretador digitado no disparo.
INTERPRETER_LABELS = (("python3", u"python3"),
                      ("python", u"python"),
                      ("bash", u"bash"),
                      ("sh", u"sh"))
PARAM_TYPE_LABELS = (("NAMED", u"Por flag (NOMEADO)"), ("POSITIONAL", u"Posicional (SEQUENCIAL)"),
                      ("NONE", u"Sem argumentos (NENHUM)"))
MAX_LENGTHS = {"name": 60, "description": 200, "script_group": 30, "category": 30, "stage": 30,
            "path_file": path_guard.MAX_LENGTH}
MAX_TIMEOUT = 9999999
MAX_LINKS = 200
SUB_DEFAULT_MAX_LENGTH = 100
MASK = params_compiler.MASK
_CATALOG_MAX = 1000
_COUNT_PAGE_SIZE = 1  # so o total interessa

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_INTEGER = re.compile(r"[0-9]{1,7}")
_RE_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_RE_FILTER = re.compile(r"[^\x00-\x1f\x7f<>]{1,60}")

PATH_MESSAGES = {
    Code.RELATIVE_PATH: u"Informe o caminho completo do arquivo, começando por / (ex.: /opt/automacoes/scripts/carga.py).",
    Code.PATH_NOT_NORMALIZED: u"Escreva o caminho sem // repetida, sem ./ e sem / no fim.",
    Code.HAS_DOTS: u"O caminho não pode conter '..'.",
    Code.INVALID_SEPARATOR: u"Use só / para separar pastas; não use \\.",
    Code.INVALID_CHARACTER: u"O caminho contém caracteres de controle não permitidos.",
    Code.SYSTEM_DIR: u"Scripts não podem ficar em pastas do sistema (/bin, /sbin, /usr, /lib, /etc, /boot, "
                             u"/proc, /sys, /dev, /root). Use outra pasta.",
    Code.SSS_DIR: u"Scripts não podem ficar nas pastas de log ou de trabalho do SSS. Use outra pasta.",
    Code.APP_DIR: u"Scripts não podem ficar na pasta da aplicação do SSS, que é trocada a cada "
                  u"atualização. Use outra pasta.",
    Code.INTERPRETER_NOT_ALLOWED: u"Interpretador não permitido.",
}
VALIDATION_NOTE = (u"O arquivo é conferido pelo agente, no servidor onde o script roda, no momento da execução "
                 u"(pode ser link simbólico).")
MSG_QUEUED_CHANGED = (u"Atenção: %d ticket(s) na fila (%s%s) foram criados com o arquivo ou o interpretador "
                      u"anterior e vão ser recusados na hora de rodar. Cancele e crie de novo, se ainda precisar.")
_QUEUED_IDS = 10
MSG_NAME_REQUIRED = u"Informe o nome do script."
MSG_NAME_DUPLICATE = u"Já existe um script com este nome."
MSG_CONTROL_CHARS = u"O campo contém caracteres de controle não permitidos."
MSG_PATH_REQUIRED = u"Informe o caminho completo do arquivo do script."
MSG_NAME_RESERVED = u"Este nome é reservado pelo sistema. Escolha outro."
MSG_PARAM_TYPE = u"Selecione como os argumentos são montados."
MSG_PARALLEL = u"Informe um número de 1 a 999."
MSG_TIMEOUT = u"Informe um número de segundos entre 1 e %d, ou deixe em branco." % MAX_TIMEOUT
MSG_NONE_LINKED = u"Este script tem parâmetros vinculados: remova-os antes de usar \"Sem argumentos\"."
MSG_LINKS_INVALID = u"A lista de parâmetros enviada é inválida. Recarregue a página e tente novamente."
MSG_SENSITIVE_INVALID = (u"O valor sigiloso gravado não vale mais para este parâmetro. "
                         u"Informe um novo valor ou use \"Remover valor\".")
MSG_LINK_DUPLICATE = u"O parâmetro \"%s\" aparece mais de uma vez."
MSG_LINK_INACTIVE = u"O parâmetro \"%s\" está inativo e não pode ser vinculado."
MSG_LINK_NONE = u"Scripts \"Sem argumentos\" não aceitam parâmetros."
MSG_HOMOLOG_INVALID = u"A seleção de ambientes é inválida. Recarregue a página e tente novamente."
MSG_HOMOLOG_INACTIVE = u"Ambientes inativos não podem ser liberados."
DEACTIVATION_WARNING = u"Agendamentos que usam este script serão pausados no próximo ciclo."

_FIELD_BY_CONSTRAINT = {
    "uk_tbsss_scr_name": ("name", MSG_NAME_DUPLICATE),
    "ck_tbsss_scr_int": ("interpreter", PATH_MESSAGES[Code.INTERPRETER_NOT_ALLOWED]),
    "ck_tbsss_scr_path": ("path_file", PATH_MESSAGES[Code.PATH_NOT_NORMALIZED]),
    "ck_tbsss_scr_paral": ("max_parallel_env", MSG_PARALLEL),
    "ck_tbsss_scr_tmout": ("timeout_s", MSG_TIMEOUT),
    "ck_tbsss_scr_ptype": ("param_type", MSG_PARAM_TYPE),
    "sss_scr_nenhum_vinculado": ("param_type", MSG_NONE_LINKED),
}


def _id(value):
    value = admin_crud.text(value, 11)
    if value is None or not _RE_ID.fullmatch(value) or int(value) < 1:
        return None
    return int(value)


def msg_named_without_flag(codes):
    """Mensagem do bloqueio NOMEADO com os parametros sem flag."""
    return (u"Montagem por flag exige flag em todo parâmetro: cadastre a flag de %s no dicionário de parâmetros."
            % u", ".join(codes))


def normalize_filters(input_value):
    """Filtros da lista: nome (trecho), grupo, categoria, interpretador (os quatro nomes, CR-026) e ativo."""
    input_value = input_value or {}
    filters = {}
    for key in ("name", "script_group", "category"):
        value = admin_crud.text(input_value.get(key), 60)
        if value and _RE_FILTER.fullmatch(value):
            filters[key] = value
    cmd = admin_crud.text(input_value.get("interpreter"), 60)
    if cmd in path_guard.ALLOWLIST:
        filters["interpreter"] = cmd
    active = admin_crud.text(input_value.get("active"), 1)
    if active in ("Y", "N"):
        filters["active"] = active
    return filters


def _hash(obj):
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_back(links):
    return [(v["parameter_id"], v["sort_order"], v["required"], v.get("default_value_override")) for v in links]


def _links_version(links, mapping):
    """Hash dos vinculos lidos; o sub de parametro sensivel entra pelo marcador (README §6.5, §10).

    O esperado do repositorio continua com _lidos (valores reais).
    """
    def sub(v):
        value = v.get("default_value_override")
        if mapping.get(v["parameter_id"], {}).get("sensitive") == "Y":
            return admin_crud.sensitive_marker(value)
        return value
    return _hash([(v["parameter_id"], v["sort_order"], v["required"], sub(v)) for v in links])


class AdminScriptsService(object):
    """Regras do cadastro de scripts com repositorios, configuracao do agente, relogio e log injetados."""

    def __init__(self, catalog, schedules, log, clock, rules=None, tickets=None, rbac=None):
        self._catalog = catalog
        self._schedules = schedules
        self._log = log
        self._clock = clock
        # Aviso depois de salvar (CR-018a): regras que o desdobro vai pausar e tickets na fila.
        self._rules = rules
        self._tickets = tickets
        self._rbac = rbac

    def _get(self, script_id):
        sid = _id(script_id)
        if sid is None:
            raise RepoNotFound("script invalido")
        return self._catalog.scripts_get(sid)

    def _active_schedules(self, **filters):
        filters["active"] = "Y"
        return self._schedules.list(filters=filters, page=1, size=_COUNT_PAGE_SIZE)["total"]

    def _profiles_selection(self, script_id=None):
        """Lista de perfis para selecao na tela (id, name, description, is_admin, active, checked)."""
        if self._rbac is None:
            return []
        try:
            items = self._rbac.profiles_list(page=1, size=_CATALOG_MAX)["items"]
        except Exception:
            return []
        linked_ids = set()
        sid = _id(script_id)
        if sid is not None:
            try:
                linked_ids = set(self._rbac.script_profiles_get(sid))
            except Exception:
                linked_ids = set()
        result = []
        for p in items:
            is_linked = p["id"] in linked_ids
            if p.get("active") == "Y" or is_linked:
                result.append({
                    "id": p["id"],
                    "name": p["name"],
                    "description": p.get("description") or "",
                    "is_admin": p.get("is_admin") == "Y",
                    "active": p.get("active") == "Y",
                    "inactive": p.get("active") != "Y",
                    "checked": is_linked,
                })
        result.sort(key=lambda x: (0 if x["is_admin"] else 1, x["name"].upper()))
        return result

    def _environments_selection(self, script_id=None):
        """Lista de ambientes para selecao na tela (id, name, description, checked, inactive)."""
        marked = set()
        sid = _id(script_id)
        if sid is not None:
            try:
                marked = set(self._catalog.homologation_get(sid))
            except Exception:
                marked = set()
        try:
            items = self._catalog.environments_list(page=1, size=_CATALOG_MAX)["items"]
        except Exception:
            return []
        result = []
        for a in items:
            is_linked = a["id"] in marked
            if a.get("active") == "Y" or is_linked:
                result.append({
                    "id": a["id"],
                    "name": a["name"],
                    "description": a.get("description") or "",
                    "active": a.get("active") == "Y",
                    "inactive": a.get("active") != "Y",
                    "checked": is_linked,
                })
        result.sort(key=lambda x: x["name"].upper())
        return result

    def _parameters_selection(self, script_id=None):
        mapping = self._dictionary()

        def resumo(p):
            return {"id": p["id"], "code": p["code"], "label": p.get("label") or "",
                    "component_type": p["component_type"], "param_flag": p.get("param_flag") or "",
                    "sensitive": p.get("sensitive") == "Y", "active": p.get("active") == "Y"}

        if script_id in (None, ""):
            current = []
        else:
            current = self._catalog.script_params_get(_id(str(script_id)))

        links = []
        for v in current:
            item = resumo(mapping.get(v["parameter_id"], v))
            sensitive = item["sensitive"]
            item.update(required=v["required"] == "Y",
                        default_value_override="" if sensitive else (v.get("default_value_override") or ""),
                        has_override=bool(v.get("default_value_override")))
            links.append(item)
        available = [resumo(p) for p in sorted(mapping.values(), key=lambda p: p["code"])
                     if p.get("active") == "Y"]
        return links, available, _links_version(current, mapping)

    # ----------------------------------------------------------------- leitura

    def list(self, ctx, filters, page, size):
        """Pagina de scripts (nome ASC) com ambientes homologados e quantidade de parametros."""
        admin_crud.require_feature(ctx, FEATURE)
        return self._catalog.scripts_list(filters=filters, page=page, size=size)

    def form(self, ctx, script_id=None):
        """Dados do formulario. Inclui agendamentos ativos na edicao."""
        admin_crud.require_feature(ctx, FEATURE)
        p_links, p_available, p_ver = self._parameters_selection(script_id)
        common = {"validation_note": VALIDATION_NOTE,
                  "profiles_selection": self._profiles_selection(script_id),
                  "environments_selection": self._environments_selection(script_id),
                  "parameters_links": p_links,
                  "parameters_available": p_available,
                  "parameters_version": p_ver}

        if script_id in (None, ""):
            return dict(common, id=None, name="", description="", script_group="", category="", stage="",
                        interpreter=path_guard.ALLOWLIST[0], path_file="", param_type="NAMED",
                        max_parallel_env=1, timeout_s="", active="Y", version="", active_schedules=0,
                        record=None)
        s = self._get(script_id)
        data = dict((c, s.get(c)) for c in EDITABLE_FIELDS)
        for c in ("description", "script_group", "category", "stage"):
            data[c] = admin_crud.normalize(data[c]) or ""
        data["timeout_s"] = "" if s.get("timeout_s") is None else s["timeout_s"]
        data.update(common, id=s["id"], version=admin_crud.version(s, EDITABLE_FIELDS),
                     active_schedules=self._active_schedules(script_id=s["id"]),
                     record=ui_helpers.record_info(s, ctx))
        return data

    # ------------------------------------------------------------- validacao

    def _field_text(self, data, field, errors, required_flag=False):
        value = admin_crud.text(data.get(field))
        if value is None:
            if required_flag:
                errors[field] = MSG_NAME_REQUIRED if field == "name" else MSG_PATH_REQUIRED
            return None
        if _RE_CONTROL.search(value):
            errors[field] = MSG_CONTROL_CHARS
        elif len(value) > MAX_LENGTHS[field]:
            errors[field] = u"Use no máximo %d caracteres." % MAX_LENGTHS[field]
        return value

    @staticmethod
    def _integer(data, field, minimum, maximum, errors, message, optional=False):
        value = admin_crud.text(data.get(field), 10)
        if value is None and optional:
            return None
        if value is None or not _RE_INTEGER.fullmatch(value) or not minimum <= int(value) <= maximum:
            errors[field] = message
            return None
        return int(value)

    def _validate(self, data, errors, current_value=None):
        reg = {
            "name": self._field_text(data, "name", errors, required_flag=True),
            "description": self._field_text(data, "description", errors),
            "script_group": self._field_text(data, "script_group", errors),
            "category": self._field_text(data, "category", errors),
            "stage": self._field_text(data, "stage", errors),
            "path_file": self._field_text(data, "path_file", errors, required_flag=True),
            "max_parallel_env": self._integer(data, "max_parallel_env", 1, 999, errors, MSG_PARALLEL),
            "timeout_s": self._integer(data, "timeout_s", 1, MAX_TIMEOUT, errors, MSG_TIMEOUT, optional=True),
        }
        # Valor exato da allowlist: um HTML adulterado nunca grava outro interpretador.
        cmd = data.get("interpreter")
        try:
            path_guard.validate_interpreter(cmd)
        except PathGuardError as exc:
            errors["interpreter"] = PATH_MESSAGES[exc.code]
        reg["interpreter"] = cmd
        # D7 (README §8.5): a pasta de log do script nao pode ser a dos logs da aplicacao.
        if reg["name"] and "name" not in errors and log_paths.is_reserved_name(reg["name"]):
            errors["name"] = MSG_NAME_RESERVED
        kind = admin_crud.text(data.get("param_type"), 15)
        if kind not in PARAM_TYPES:
            errors["param_type"] = MSG_PARAM_TYPE
        reg["param_type"] = kind
        return reg

    def validate_path(self, path_file, errors):
        """Confere o formato de path_file e as pastas do sistema (README §8.5; CR-011, S1). O arquivo nao e
        conferido aqui: o web pode nem ter o arquivo; o agente confere no servidor onde o script roda."""
        if path_file is None or "path_file" in errors:
            return
        try:
            path_guard.validate_registration(path_file)
            path_guard.check_forbidden_dirs(path_file)
        except PathGuardError as exc:
            errors["path_file"] = PATH_MESSAGES[exc.code]

    def _param_type_precheck(self, script_id, kind, errors):
        links = self._catalog.script_params_get(script_id)
        if kind == "NONE" and links:
            errors["param_type"] = MSG_NONE_LINKED
        elif kind == "NAMED":
            without_flag = [v["code"] for v in links if not v.get("param_flag")]
            if without_flag:
                errors["param_type"] = msg_named_without_flag(without_flag)

    def _violation(self, ctx, exc, errors, script_id=None):
        if exc.constraint == "sss_scr_nomeado_sem_flag" and script_id:
            errors["param_type"] = msg_named_without_flag(
                [v["code"] for v in self._catalog.script_params_get(script_id) if not v.get("param_flag")])
        else:
            field, message = _FIELD_BY_CONSTRAINT.get(exc.constraint, (GENERAL_FIELD, admin_crud.MSG_FAILURE))
            errors[field] = message
        self._log.warning("cadastro de script rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"action": FEATURE})

    # ----------------------------------------------------------------- escrita

    def _save_profiles_link(self, ctx, ip, script_id, profile_ids):
        """Salva a associacao de perfis ao script e audita a diferenca."""
        if self._rbac is None or profile_ids is None:
            return
        target_ids = []
        for x in profile_ids:
            if x not in (None, "") and _RE_ID.fullmatch(str(x)):
                target_ids.append(int(x))
        target_set = set(target_ids)
        try:
            current = set(self._rbac.script_profiles_get(script_id))
        except Exception:
            current = set()
        if target_set == current:
            return
        try:
            all_profiles = dict(
                (p["id"], p["name"])
                for p in self._rbac.profiles_list(page=1, size=_CATALOG_MAX)["items"]
            )
        except Exception:
            all_profiles = {}
        added = sorted(all_profiles.get(i, str(i)) for i in (target_set - current))
        removed = sorted(all_profiles.get(i, str(i)) for i in (current - target_set))
        diff_parts = [u"+" + n for n in added] + [u"-" + n for n in removed]
        detail = admin_crud.free_detail(u"perfis: %s" % u", ".join(diff_parts))
        audit = admin_crud.audit_entry(ctx, ip, "UPDATE", detail)
        self._rbac.script_profiles_save(script_id, sorted(target_set), audit=audit)
        self._log.info("perfis do script alterados (login=%s script_id=%s diff=%s)",
                       ctx.get("login"), script_id, u", ".join(diff_parts),
                       extra={"action": "UPDATE"})

    def _save_environments_link(self, ctx, ip, script_id, environment_ids):
        """Salva a homologacao de ambientes ao script e audita a diferenca."""
        if environment_ids is None:
            return
        target_ids = []
        for x in environment_ids:
            if x not in (None, "") and _RE_ID.fullmatch(str(x)):
                target_ids.append(int(x))
        target_set = set(target_ids)
        try:
            current = set(self._catalog.homologation_get(script_id))
        except Exception:
            current = set()
        if target_set == current:
            return
        try:
            all_envs = dict(
                (a["id"], a)
                for a in self._catalog.environments_list(page=1, size=_CATALOG_MAX)["items"]
            )
        except Exception:
            all_envs = {}
        # D9: inativo ja homologado pode sair, nunca entrar
        inactive_ids = set(i for i, a in all_envs.items() if a.get("active") != "Y")
        if (target_set - current) & inactive_ids:
            target_set = target_set - inactive_ids
        added = sorted(all_envs[i]["name"] for i in (target_set - current) if i in all_envs)
        removed = sorted(all_envs[i]["name"] for i in (current - target_set) if i in all_envs)
        if not added and not removed:
            return
        diff_parts = [u"+" + n for n in added] + [u"-" + n for n in removed]
        affected = sum(self._active_schedules(script_id=script_id, environment=n) for n in removed)
        detail = admin_crud.free_detail(u"homologação: %s%s" % (
            u", ".join(diff_parts),
            (u"; agendamentos ativos afetados: %d" % affected) if removed else u""))
        audit = admin_crud.audit_entry(ctx, ip, "UPDATE", detail)
        self._catalog.homologation_save(script_id, sorted(target_set), audit=audit)
        self._log.info("homologacao do script alterada (login=%s script_id=%s diff=%s)",
                       ctx.get("login"), script_id, u", ".join(diff_parts),
                       extra={"action": "UPDATE"})

    def save(self, ctx, ip, script_id, data, profile_ids=None, environment_ids=None,
             links_json=None, parameters_version=None):
        """Inclui ou altera um script. Retorna (id, erros, aviso). Lanca RepoNotFound e AccessDenied."""
        admin_crud.require_feature(ctx, FEATURE)
        errors = {}
        current = None if script_id in (None, "") else self._get(script_id)
        reg = self._validate(data, errors, current)
        self.validate_path(reg["path_file"], errors)
        warning = None

        final_links = None
        current_links = []
        if current is not None:
            current_links = self._catalog.script_params_get(current["id"])

        if links_json is not None:
            final_links = self._build_links(reg, links_json, current_links, errors)
            if current is not None and parameters_version:
                expected_ver = _links_version(current_links, self._dictionary())
                if admin_crud.text(parameters_version, 64) != expected_ver:
                    errors[GENERAL_FIELD] = admin_crud.MSG_CONFLICT

        if script_id in (None, ""):
            if errors:
                return None, errors, None
            new = dict(reg, active="Y")
            audit = admin_crud.audit_entry(ctx, ip, "CREATE", admin_crud.insert_detail(new, INSERT_FIELDS))
            try:
                created = self._catalog.scripts_insert(new, audit=audit)
            except RepoViolation as exc:
                self._violation(ctx, exc, errors)
                return None, errors, None
            self._log.info("script incluido (login=%s script=%s)", ctx.get("login"), created["name"],
                           extra={"action": "CREATE"})
            self._save_profiles_link(ctx, ip, created["id"], profile_ids)
            self._save_environments_link(ctx, ip, created["id"], environment_ids)
            if final_links:
                detail_p = admin_crud.free_detail(
                    u"vínculos: %s → %s" % (u"(nenhum)", self._describe(final_links))
                )
                audit_p = admin_crud.audit_entry(ctx, ip, "CREATE", detail_p)
                self._catalog.script_params_save(
                    created["id"],
                    [dict((k, v[k]) for k in ("parameter_id", "sort_order", "required",
                                              "default_value_override"))
                     for v in final_links],
                    expected=[], audit=audit_p
                )
            return created["id"], {}, warning

        current = self._get(script_id)
        if links_json is None and not errors and reg["param_type"] != current["param_type"]:
            self._param_type_precheck(current["id"], reg["param_type"], errors)
        if errors:
            return current["id"], errors, None
        if admin_crud.text(data.get("version"), 64) != admin_crud.version(current, EDITABLE_FIELDS):
            return current["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}, None
        changes = dict((c, reg[c]) for c in EDITABLE_FIELDS if c != "active")

        detail = admin_crud.changes_detail(current, dict(current, **changes), EDITABLE_FIELDS)
        if detail is not None:
            try:
                self._catalog.scripts_update(
                    current["id"], changes,
                    expected=admin_crud.expected(current, EDITABLE_FIELDS),
                    audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detail)
                )
            except RepoConflict:
                return current["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}, None
            except RepoViolation as exc:
                self._violation(ctx, exc, errors, current["id"])
                return current["id"], errors, None
            self._log.info("script alterado (login=%s script=%s)", ctx.get("login"), reg["name"],
                           extra={"action": "UPDATE"})
            if changes["path_file"] != current["path_file"] or changes["interpreter"] != current["interpreter"]:
                warning = self.queued_warning(current["id"])
        self._save_profiles_link(ctx, ip, current["id"], profile_ids)
        self._save_environments_link(ctx, ip, current["id"], environment_ids)

        if final_links is not None and _read_back(final_links) != _read_back(current_links):
            before, after = self._describe(current_links), self._describe(final_links)
            detail_p = admin_crud.free_detail(u"vínculos: %s → %s" % (before, after))
            try:
                self._catalog.script_params_save(
                    current["id"],
                    [dict((k, v[k]) for k in ("parameter_id", "sort_order", "required",
                                              "default_value_override"))
                     for v in final_links],
                    expected=_read_back(current_links),
                    audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detail_p)
                )
                self._log.info("vinculos alterados (login=%s script=%s)", ctx.get("login"),
                               current["name"], extra={"action": "UPDATE"})
            except RepoConflict:
                return current["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}, None
            except RepoViolation as exc:
                self._log.warning(
                    "vinculos rejeitados pelo repositorio (login=%s script=%s constraint=%s)",
                    ctx.get("login"), current["name"], exc.constraint, extra={"action": FEATURE})
                if exc.constraint == "sss_scr_nomeado_sem_flag":
                    return current["id"], {GENERAL_FIELD: msg_named_without_flag([v["code"] for v in final_links if not v.get("param_flag")])}, None
                if exc.constraint == "sss_scr_nenhum_vinculado":
                    return current["id"], {GENERAL_FIELD: MSG_LINK_NONE}, None
                return current["id"], {GENERAL_FIELD: admin_crud.MSG_FAILURE}, None

        return current["id"], {}, warning



    def queued_warning(self, script_id):
        """Tickets na fila criados com o arquivo ou o interpretador anterior (CR-018a, README §8.4).

        A pre-validacao do agente recusa esses tickets (REGISTRATION_CHANGED); o aviso diz quais sao.
        """
        if self._tickets is None:
            return None
        result = self._tickets.list(filters={"status": ["PENDING"], "script_id": int(script_id)}, page=1,
                                    size=_QUEUED_IDS)
        if not result["total"]:
            return None
        ids = u", ".join(u"#%s" % t["id"] for t in result["items"])
        more = u" e outros" if result["total"] > len(result["items"]) else u""
        return MSG_QUEUED_CHANGED % (result["total"], ids, more)

    def rules_warning(self, ctx, script_id):
        """Aviso depois de salvar os vinculos (CR-018a): regras ativas que vao ser pausadas, ou None."""
        admin_crud.require_feature(ctx, FEATURE)
        if self._rules is None:
            return None
        sid = self._get(script_id)["id"]
        return schedules_service.impact_warning(self._rules.rules_at_risk([sid]),
                                                len(self._rules.active_rules([sid])))

    def toggle_active(self, ctx, ip, script_id, version):
        """Desativa (DEACTIVATE, com agendamentos ativos afetados) ou reativa (UPDATE) o script."""
        admin_crud.require_feature(ctx, FEATURE)
        current = self._get(script_id)
        if admin_crud.text(version, 64) != admin_crud.version(current, EDITABLE_FIELDS):
            raise RepoConflict("versao divergente")
        new_active = "N" if current["active"] == "Y" else "Y"
        changes = {"active": new_active}
        if new_active == "Y":
            # Reativacao refaz as checagens de arquivo (README §8.5).
            errors = {}
            self.validate_path(current["path_file"], errors)
            if errors:
                raise OperationDenied(u"Não foi possível reativar: %s" % u" ".join(errors.values()))
        detail = admin_crud.changes_detail(current, dict(current, **changes), EDITABLE_FIELDS)
        action = "DEACTIVATE" if new_active == "N" else "UPDATE"
        if new_active == "N":
            detail = u"%s; agendamentos ativos afetados: %d" % (detail, self._active_schedules(script_id=current["id"]))
        changed = self._catalog.scripts_update(current["id"], changes,
                                                  expected=admin_crud.expected(current, EDITABLE_FIELDS),
                                                  audit=admin_crud.audit_entry(ctx, ip, action, detail))
        self._log.info("script %s (login=%s script=%s)", "desativado" if new_active == "N" else "reativado",
                       ctx.get("login"), current["name"], extra={"action": action})
        return changed

    # ------------------------------------------------------------ homologacao

    def homologation(self, ctx, script_id):
        """Tela de homologacao: ambientes ativos e inativos ja homologados, com agendamentos ativos por ambiente."""
        admin_crud.require_feature(ctx, FEATURE)
        script = self._get(script_id)
        marked = set(self._catalog.homologation_get(script["id"]))
        environments = []
        for a in self._catalog.environments_list(page=1, size=_CATALOG_MAX)["items"]:
            if a["active"] != "Y" and a["id"] not in marked:
                continue
            environments.append({"id": a["id"], "name": a["name"], "description": a.get("description") or "",
                              "checked": a["id"] in marked, "inactive": a["active"] != "Y",
                              "active_schedules": self._active_schedules(script_id=script["id"],
                                                                               environment=a["name"])})
        return {"script": {"id": script["id"], "name": script["name"], "active": script["active"]},
                "environments": environments, "version": _hash(sorted(marked))}

    def save_homologation(self, ctx, ip, script_id, environment_ids, version):
        """Substitui a homologacao (so ambientes ativos podem ser adicionados; inativos existentes podem sair, D9).

        Retorna (diff ou None, erros). Auditoria UPDATE com +/- e agendamentos ativos afetados.
        """
        admin_crud.require_feature(ctx, FEATURE)
        script = self._get(script_id)
        sent = set()
        for value in (environment_ids if isinstance(environment_ids, (list, tuple)) else [environment_ids]):
            if value in (None, ""):
                continue
            aid = _id(value)
            if aid is None:
                return None, {GENERAL_FIELD: MSG_HOMOLOG_INVALID}
            sent.add(aid)
        current = self._catalog.homologation_get(script["id"])
        if admin_crud.text(version, 64) != _hash(sorted(current)):
            return None, {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        environments = dict((a["id"], a) for a in self._catalog.environments_list(page=1, size=_CATALOG_MAX)["items"])
        if sent - set(environments):
            return None, {GENERAL_FIELD: MSG_HOMOLOG_INVALID}
        inactive = set(i for i, a in environments.items() if a["active"] != "Y")
        if (sent - set(current)) & inactive:
            return None, {GENERAL_FIELD: MSG_HOMOLOG_INACTIVE}
        # D9 (README §4.3.A): inativo ja homologado pode sair (desmarcado); nunca entra de novo (checado acima).
        final = set(sent)
        added = sorted(environments[i]["name"] for i in final - set(current))
        removed = sorted(environments[i]["name"] for i in set(current) - final)
        if not added and not removed:
            return None, {}
        parts = [u"+" + n for n in added] + [u"-" + n for n in removed]
        diff = u", ".join(parts)
        affected = sum(self._active_schedules(script_id=script["id"], environment=n) for n in removed)
        detail = admin_crud.free_detail(u"homologação: %s%s" % (
            diff, (u"; agendamentos ativos afetados: %d" % affected) if removed else u""))
        try:
            self._catalog.homologation_save(script["id"], sorted(final), expected=current,
                                              audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detail))
        except RepoConflict:
            return None, {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        self._log.info("homologacao alterada (login=%s script=%s)", ctx.get("login"), script["name"],
                       extra={"action": "UPDATE"})
        return diff, {}

    # -------------------------------------------------------------- vinculos

    def _dictionary(self):
        return dict((p["id"], p) for p in self._catalog.parameters_list(page=1, size=_CATALOG_MAX)["items"])

    def parameters(self, ctx, script_id):
        """Tela de vinculos: vinculos atuais (sub sigiloso nunca devolvido), dicionario para busca e versao."""
        admin_crud.require_feature(ctx, FEATURE)
        script = self._get(script_id)
        current = self._catalog.script_params_get(script["id"])
        mapping = self._dictionary()

        def resumo(p):
            return {"id": p["id"], "code": p["code"], "label": p.get("label") or "",
                    "component_type": p["component_type"], "param_flag": p.get("param_flag") or "",
                    "sensitive": p.get("sensitive") == "Y", "active": p.get("active") == "Y"}

        links = []
        for v in current:
            item = resumo(mapping.get(v["parameter_id"], v))
            sensitive = item["sensitive"]
            item.update(required=v["required"] == "Y",
                        default_value_override="" if sensitive else (v.get("default_value_override") or ""),
                        has_override=bool(v.get("default_value_override")))
            links.append(item)
        available = [resumo(p) for p in sorted(mapping.values(), key=lambda p: p["code"]) if p.get("active") == "Y"]
        return {"script": {"id": script["id"], "name": script["name"], "param_type": script["param_type"]},
                "links": links, "available": available, "version": _links_version(current, mapping)}

    def _build_links(self, script, links_json, current, errors):
        """Valida o JSON do cliente e devolve a lista final ordenada (dicts completos para o compilador)."""
        try:
            items = json.loads(links_json or "[]")
        except ValueError:
            items = None
        if not isinstance(items, list) or len(items) > MAX_LINKS:
            errors[GENERAL_FIELD] = MSG_LINKS_INVALID
            return None
        mapping = self._dictionary()
        current_by_id = dict((v["parameter_id"], v) for v in current)
        seen = set()
        final = []
        for position, item in enumerate(items, 1):
            pid = _id(str(item.get("parameter_id"))) if isinstance(item, dict) else None
            if pid is None or pid not in mapping:
                errors[GENERAL_FIELD] = MSG_LINKS_INVALID
                return None
            p = mapping[pid]
            if pid in seen:
                errors[GENERAL_FIELD] = MSG_LINK_DUPLICATE % p["code"]
                return None
            seen.add(pid)
            if p.get("active") != "Y" and pid not in current_by_id:
                errors[GENERAL_FIELD] = MSG_LINK_INACTIVE % p["code"]
                return None
            sub = item.get("default_value_override")
            sub = sub.strip() if isinstance(sub, str) else None
            if p.get("sensitive") == "Y" and not sub and item.get("keep_secret") is True and pid in current_by_id:
                sub = current_by_id[pid].get("default_value_override")
                # O valor mantido tambem e revalidado contra a configuracao atual (README §6.5).
                if sub:
                    try:
                        params_compiler.validate_value(p, sub)
                    except ParamError:
                        errors["vinculo_%d" % pid] = MSG_SENSITIVE_INVALID
            elif sub:
                try:
                    sub = params_compiler.validate_value(p, sub)
                    sub = "true" if sub is True else ("false" if sub is False else sub)
                except ParamError as exc:
                    errors["vinculo_%d" % pid] = exc.message
                    sub = None
                if sub is not None and len(sub) > SUB_DEFAULT_MAX_LENGTH:
                    errors["vinculo_%d" % pid] = u"O valor padrão específico aceita até %d caracteres." % SUB_DEFAULT_MAX_LENGTH
            else:
                sub = None
            v = dict(p, parameter_id=pid, sort_order=position, required="Y" if item.get("required") is True else "N",
                     default_value_override=sub)
            final.append(v)
        if script["param_type"] == "NONE" and final:
            errors[GENERAL_FIELD] = MSG_LINK_NONE
        elif script["param_type"] == "NAMED":
            without_flag = [v["code"] for v in final if not v.get("param_flag")]
            if without_flag:
                errors[GENERAL_FIELD] = msg_named_without_flag(without_flag)
        return final

    @staticmethod
    def _describe(links):
        parts = []
        for v in links:
            text = v["code"] + ("*" if v["required"] == "Y" else "")
            if v.get("default_value_override"):
                text += "=" + (MASK if v.get("sensitive") == "Y" else str(v["default_value_override"]))
            parts.append(text)
        return u", ".join(parts) or u"(nenhum)"

    def save_parameters(self, ctx, ip, script_id, links_json, version):
        """Substitui os vinculos (ordem renumerada pela posicao). Retorna (descricao ou None, erros por campo).

        erros usa GENERAL_FIELD ou 'vinculo_<parameter_id>' (valor padrao especifico invalido).
        """
        admin_crud.require_feature(ctx, FEATURE)
        script = self._get(script_id)
        current = self._catalog.script_params_get(script["id"])
        if admin_crud.text(version, 64) != _links_version(current, self._dictionary()):
            return None, {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        errors = {}
        final = self._build_links(script, links_json, current, errors)
        if errors:
            return None, errors
        if _read_back(final) == _read_back(current):
            return None, {}
        before, after = self._describe(current), self._describe(final)
        detail = admin_crud.free_detail(u"vínculos: %s → %s" % (before, after))
        try:
            self._catalog.script_params_save(
                script["id"], [dict((k, v[k]) for k in ("parameter_id", "sort_order", "required", "default_value_override"))
                               for v in final],
                expected=_read_back(current), audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detail))
        except RepoConflict:
            return None, {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        except RepoViolation as exc:
            self._log.warning("vinculos rejeitados pelo repositorio (login=%s script=%s constraint=%s)",
                              ctx.get("login"), script["name"], exc.constraint, extra={"action": FEATURE})
            if exc.constraint == "sss_scr_nomeado_sem_flag":
                return None, {GENERAL_FIELD: msg_named_without_flag([v["code"] for v in final if not v.get("param_flag")])}
            if exc.constraint == "sss_scr_nenhum_vinculado":
                return None, {GENERAL_FIELD: MSG_LINK_NONE}
            return None, {GENERAL_FIELD: admin_crud.MSG_FAILURE}
        self._log.info("vinculos alterados (login=%s script=%s)", ctx.get("login"), script["name"],
                       extra={"action": "UPDATE"})
        return after, {}

    def preview(self, ctx, script_id, links_json=None, param_type=None):
        """argv mascarado com os valores padrao (README §6.1), da configuracao em edicao ou da gravada.

        Retorna {argv: [...] | None, erros: {campo: msg}, aviso: str | None}. Nao grava nada.
        """
        admin_crud.require_feature(ctx, FEATURE)
        if script_id in (None, "", 0):
            script = {"id": 0, "name": "novo", "param_type": param_type or "NAMED",
                      "path_file": "script.py", "interpreter": "python3"}
            current = []
        else:
            script = self._get(script_id)
            if param_type:
                script = dict(script, param_type=param_type)
            current = self._catalog.script_params_get(script["id"])
        errors = {}
        if links_json is None:
            links = current
        else:
            links = self._build_links(script, links_json, current, errors)
            if errors:
                return {"argv": None, "errors": errors, "warning": None}
        warning = None
        snap, _resolved, errors = params_compiler.compile_snapshot(script, links, {}, self._clock())
        if snap is None:
            return {"argv": None, "errors": errors, "warning": warning}
        return {"argv": params_compiler.display_argv(json.loads(snap)),
                "errors": {}, "warning": warning}


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from sss.config import app_context
            from sss.persistence import repo_factory
            from sss.config import sss_logging
            factory = repo_factory
            cfg = app_context.require_config()
            tickets = factory.get("tickets")
            _default = AdminScriptsService(
                catalog=factory.get("catalog"),
                schedules=factory.get("schedules"),
                log=sss_logging.get_logger("sss_web", cfg),
                clock=tickets.now,
                rules=schedules_service._service(),
                tickets=tickets,
                rbac=factory.get("rbac"),
            )
        return _default


def list_page(ctx, filters, page, size):
    """Pagina de scripts (servico padrao)."""
    return _service().list(ctx, filters, page, size)


def rules_warning(ctx, script_id):
    """Regras que vao ser pausadas depois de salvar os vinculos (servico padrao)."""
    return _service().rules_warning(ctx, script_id)


def form(ctx, script_id=None):
    """Dados do formulario de script (servico padrao)."""
    return _service().form(ctx, script_id)


def parameters_selection(script_id=None):
    """Selecao de parametros para o formulario de script (servico padrao)."""
    return _service()._parameters_selection(script_id)


def save(ctx, ip, script_id, data, profile_ids=None, environment_ids=None,
         links_json=None, parameters_version=None):
    """Inclusao ou alteracao de script (servico padrao)."""
    return _service().save(ctx, ip, script_id, data, profile_ids=profile_ids,
                           environment_ids=environment_ids,
                           links_json=links_json,
                           parameters_version=parameters_version)


def toggle_active(ctx, ip, script_id, version):
    """Desativacao/reativacao de script (servico padrao)."""
    return _service().toggle_active(ctx, ip, script_id, version)


def homologation(ctx, script_id):
    """Tela de homologacao (servico padrao)."""
    return _service().homologation(ctx, script_id)


def save_homologation(ctx, ip, script_id, environment_ids, version):
    """Gravacao da homologacao (servico padrao)."""
    return _service().save_homologation(ctx, ip, script_id, environment_ids, version)


def parameters(ctx, script_id):
    """Tela de vinculos de parametros (servico padrao)."""
    return _service().parameters(ctx, script_id)


def save_parameters(ctx, ip, script_id, links_json, version):
    """Gravacao dos vinculos (servico padrao)."""
    return _service().save_parameters(ctx, ip, script_id, links_json, version)


def preview(ctx, script_id, links_json=None, param_type=None):
    """Previa do argv mascarado (servico padrao)."""
    return _service().preview(ctx, script_id, links_json, param_type=param_type)
