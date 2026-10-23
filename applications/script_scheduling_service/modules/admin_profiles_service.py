# -*- coding: utf-8 -*-
"""Cadastro de perfis e matriz de permissoes (README §4.3, §4.4, §10 tabelas 2-5 e 7).

Segue docs/ADMIN_CRUD_PATTERN.md. A protecao do ultimo administrador e a troca da matriz sao
operacoes unicas do repositorio (sem check-then-act aqui). Nao importa gluon fora de _servico.
"""
import collections
import re
import threading

import admin_crud
import ui_helpers
from admin_crud import GENERAL_FIELD, OperationDenied
from repo_errors import RepoConflict, RepoNotFound, RepoViolation

FEATURE = "MANAGE_PROFILES"
EDITABLE_FIELDS = ("name", "description", "is_admin", "active")
INSERT_FIELDS = ("name", "description", "is_admin")
DESCRIPTION_MAX_LENGTH = 100
_CATALOG_MAX = 1000
_COUNT_PAGE_SIZE = 1  # so o total interessa
_NO_GROUP = u"Sem grupo"

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_NAME = re.compile(r"[A-Z0-9_]{1,30}")
_RE_NAME_FILTER = re.compile(r"[A-Za-z0-9_]{1,30}")

MSG_NAME_REQUIRED = u"Informe o nome do perfil."
MSG_NAME_INVALID = u"Use de 1 a 30 caracteres: letras maiúsculas, dígitos e _ (ex.: OPERATOR_PROD)."
MSG_NAME_DUPLICATE = u"Já existe um perfil com este nome."
MSG_DESCRIPTION_LENGTH = u"A descrição deve ter no máximo %d caracteres." % DESCRIPTION_MAX_LENGTH
MSG_LAST_ADMIN = ui_helpers.message("last_admin")
MSG_SELF_ADMIN = u"Você não pode remover o acesso administrativo do seu próprio perfil."
MSG_SELF_DEACTIVATE = u"Você não pode desativar o seu próprio perfil."
MSG_ADMIN_ONLY = (u"Só um administrador pode alterar um perfil de administrador, mudar o seu próprio perfil ou "
                u"marcar um perfil como administrador. Peça a um administrador.")
AFFECTED_MAX = 20
MSG_MATRIX_ID_INVALID = u"A seleção contém itens inexistentes. Recarregue a página e tente novamente."
MSG_MATRIX_INACTIVE = u"Itens inativos não podem ser adicionados ao perfil. Recarregue a página e tente novamente."
DEACTIVATION_WARNING = u"Os usuários deste perfil perdem o acesso e têm a sessão encerrada no próximo clique."
ADMIN_WARNING = (u"Perfil administrativo: dispensa funcionalidades, ambientes e scripts, mas não a homologação "
               u"do script no ambiente nem as flags de ativo. A matriz abaixo fica registrada e passa a valer "
               u"se o perfil deixar de ser administrativo.")

_FIELD_BY_CONSTRAINT = {
    "uk_tbsss_prf_name": ("name", MSG_NAME_DUPLICATE),
}
# Prefixo de cada dimensao no diff auditado (README §4.4 PERM_UPDATE).
_PREFIXES = (("funcs", ""), ("ambs", "amb:"), ("scrs", "scr:"))


def _id(value):
    value = admin_crud.text(value, 11)
    if value is None or not _RE_ID.fullmatch(value) or int(value) < 1:
        return None
    return int(value)


def _ids(values):
    """Lista de IDs enviada pelo formulario; qualquer valor nao numerico invalida o conjunto (None)."""
    if values is None:
        return set()
    if not isinstance(values, (list, tuple)):
        values = [values]
    ids = set()
    for v in values:
        i = _id(v)
        if i is None:
            return None
        ids.add(i)
    return ids


def normalize_filters(input_value):
    """Filtros da lista vindos de request.vars: name (trecho), active e is_admin ('Y' | 'N')."""
    input_value = input_value or {}
    filters = {}
    name = admin_crud.text(input_value.get("name"), 30)
    if name and _RE_NAME_FILTER.fullmatch(name):
        filters["name"] = name
    for key in ("active", "is_admin"):
        value = admin_crud.text(input_value.get(key), 1)
        if value in ("Y", "N"):
            filters[key] = value
    return filters


def matrix_diff(before, after_value, labels):
    """'+EXEC_SCRIPT, -VIEW_LOGS, +amb:PRODUCAO, -scr:carga_diaria' (ordem: dimensao, rotulo); None se igual.

    before/after_value: {'funcs': set, 'ambs': set, 'scrs': set}; labels: {dimensao: {id: rotulo}}.
    """
    parts = []
    for dim, prefix in _PREFIXES:
        a, d = set(before.get(dim) or ()), set(after_value.get(dim) or ())
        names = labels.get(dim, {})
        changes = [(names.get(i, "#%s" % i), "+") for i in d - a] + [(names.get(i, "#%s" % i), "-") for i in a - d]
        for label, signal_value in sorted(changes):
            parts.append(u"%s%s%s" % (signal_value, prefix, label))
    return admin_crud.free_detail(u", ".join(parts)) if parts else None


class AdminProfilesService(object):
    """Regras do cadastro de perfis e da matriz de permissoes com repositorios injetados."""

    def __init__(self, rbac_repo, catalog, users, log):
        self._rbac = rbac_repo
        self._catalog = catalog
        self._users = users
        self._log = log

    def _get(self, profile_id):
        pid = _id(profile_id)
        if pid is None:
            raise RepoNotFound("perfil invalido")
        return self._rbac.profiles_get(pid)

    def active_users(self, profile_id):
        """Quantidade de usuarios ativos do perfil (perdem o acesso se o perfil for desativado)."""
        return self._users.list(filters={"profile_id": profile_id, "active": "Y"}, page=1,
                                     size=_COUNT_PAGE_SIZE)["total"]

    def affected_users(self, profile_id):
        """(total, logins) dos usuarios ativos do perfil; no maximo AFFECTED_MAX logins (README §4.3.B.1)."""
        page = self._users.list(filters={"profile_id": profile_id, "active": "Y"}, page=1,
                                       size=AFFECTED_MAX)
        return page["total"], [u["login"] for u in page["items"]]

    # ------------------------------------------------------------- cadastro

    def list(self, ctx, filters, page, size):
        """Pagina de perfis (ordem nome ASC)."""
        admin_crud.require_feature(ctx, FEATURE)
        return self._rbac.profiles_list(filters=filters, page=page, size=size)

    def form(self, ctx, profile_id=None):
        """Dados do formulario: vazio para inclusao; registro, versao e usuarios ativos na edicao."""
        admin_crud.require_feature(ctx, FEATURE)
        if profile_id in (None, ""):
            return {"id": None, "name": "", "description": "", "is_admin": "N", "active": "Y", "version": "",
                    "active_users": 0, "affected_users": [], "own": False, "record": None}
        profile = self._get(profile_id)
        total, logins = self.affected_users(profile["id"])
        return {
            "id": profile["id"],
            "name": profile["name"],
            "description": admin_crud.normalize(profile.get("description")) or "",
            "is_admin": profile["is_admin"],
            "active": profile["active"],
            "version": admin_crud.version(profile, EDITABLE_FIELDS),
            "active_users": total,
            "affected_users": logins,
            "own": ctx.get("profile_id") == profile["id"],
            "record": ui_helpers.record_info(profile, ctx),
        }

    def _validate(self, date, errors):
        name = admin_crud.identifier(date.get("name"), errors, "name")
        if name is None:
            errors["name"] = MSG_NAME_REQUIRED
        elif "name" not in errors and not _RE_NAME.fullmatch(name):
            errors["name"] = MSG_NAME_INVALID
        description = admin_crud.free_text(date.get("description"), errors, "description")
        if description is not None and len(description) > DESCRIPTION_MAX_LENGTH:
            errors["description"] = MSG_DESCRIPTION_LENGTH
        is_admin = "Y" if admin_crud.text(date.get("is_admin"), 1) == "Y" else "N"
        return name, description, is_admin

    def _violation(self, ctx, exc, errors):
        if exc.constraint == "sss_ultimo_admin":
            errors[GENERAL_FIELD] = MSG_LAST_ADMIN
        else:
            field, message = _FIELD_BY_CONSTRAINT.get(exc.constraint, (GENERAL_FIELD, admin_crud.MSG_FAILURE))
            errors[field] = message
        self._log.warning("cadastro de perfil rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"action": FEATURE})

    def _require_admin(self, ctx, condition, operation):
        admin_crud.require_admin(ctx, condition, MSG_ADMIN_ONLY, self._log, operation)

    def _reserved(self, ctx, profile):
        """Perfil que so admin altera (CR-008, E1): perfil de administrador ou o proprio perfil."""
        return profile["is_admin"] == "Y" or ctx.get("profile_id") == profile["id"]

    def save(self, ctx, ip, profile_id, date):
        """Inclui (profile_id vazio) ou altera um perfil: name, description, is_admin ('Y' marcado).

        Retorna (id, erros). Remover is_admin do ultimo perfil admin ativo gera erro geral.
        Lanca RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        errors = {}
        if profile_id in (None, ""):
            name, description, is_admin = self._validate(date, errors)
            if errors:
                return None, errors
            try:
                self._require_admin(ctx, is_admin == "Y", "CREATE")
            except OperationDenied as exc:
                return None, {GENERAL_FIELD: exc.message}
            new = {"name": name, "description": description, "is_admin": is_admin, "active": "Y"}
            audit = admin_crud.audit_entry(ctx, ip, "CREATE",
                                             admin_crud.insert_detail(new, INSERT_FIELDS))
            try:
                created = self._rbac.profiles_insert(new, audit=audit)
            except RepoViolation as exc:
                self._violation(ctx, exc, errors)
                return None, errors
            self._log.info("perfil incluido (login=%s perfil=%s)", ctx.get("login"), created["name"],
                           extra={"action": "CREATE"})
            return created["id"], {}

        current = self._get(profile_id)
        name, description, is_admin = self._validate(date, errors)
        if errors:
            return current["id"], errors
        if admin_crud.text(date.get("version"), 64) != admin_crud.version(current, EDITABLE_FIELDS):
            errors[GENERAL_FIELD] = admin_crud.MSG_CONFLICT
            return current["id"], errors
        try:
            self._require_admin(ctx, is_admin == "Y" or self._reserved(ctx, current), "UPDATE")
        except OperationDenied as exc:
            errors[GENERAL_FIELD] = exc.message
            return current["id"], errors
        if ctx.get("profile_id") == current["id"] and current["is_admin"] == "Y" and is_admin == "N":
            # Autoprotecao (README §4.3.B): vale mesmo havendo outros administradores.
            self._log.warning("remocao de is_admin do proprio perfil negada (login=%s perfil=%s)",
                              ctx.get("login"), current["name"], extra={"action": "UPDATE"})
            errors[GENERAL_FIELD] = MSG_SELF_ADMIN
            return current["id"], errors
        after = dict(current, name=name, description=description, is_admin=is_admin)
        detail = admin_crud.changes_detail(current, after, EDITABLE_FIELDS)
        if detail is None:
            return current["id"], {}
        try:
            self._rbac.profiles_update(
                current["id"], {"name": name, "description": description, "is_admin": is_admin},
                expected=admin_crud.expected(current, EDITABLE_FIELDS),
                audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detail))
        except RepoConflict:
            errors[GENERAL_FIELD] = admin_crud.MSG_CONFLICT
            return current["id"], errors
        except RepoViolation as exc:
            self._violation(ctx, exc, errors)
            return current["id"], errors
        self._log.info("perfil alterado (login=%s perfil=%s)", ctx.get("login"), name, extra={"action": "UPDATE"})
        return current["id"], {}

    def toggle_active(self, ctx, ip, profile_id, version):
        """Desativa (DEACTIVATE, com usuarios afetados) ou reativa (UPDATE) o perfil.

        Lanca OperationDenied (ultimo administrador), RepoConflict, RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        current = self._get(profile_id)
        if admin_crud.text(version, 64) != admin_crud.version(current, EDITABLE_FIELDS):
            raise RepoConflict("versao divergente")
        new_active = "N" if current["active"] == "Y" else "Y"
        self._require_admin(ctx, current["is_admin"] == "Y" and ctx.get("profile_id") != current["id"], "DEACTIVATE")
        if new_active == "N" and ctx.get("profile_id") == current["id"]:
            self._log.warning("desativacao do proprio perfil negada (login=%s perfil=%s)",
                              ctx.get("login"), current["name"], extra={"action": "DEACTIVATE"})
            raise OperationDenied(MSG_SELF_DEACTIVATE)
        detail = admin_crud.changes_detail(current, dict(current, active=new_active), ("active",))
        action = "DEACTIVATE" if new_active == "N" else "UPDATE"
        if new_active == "N":
            detail = u"%s; usuários ativos afetados: %d" % (detail, self.active_users(current["id"]))
        try:
            changed = self._rbac.profiles_update(
                current["id"], {"active": new_active}, expected=admin_crud.expected(current, EDITABLE_FIELDS),
                audit=admin_crud.audit_entry(ctx, ip, action, detail))
        except RepoViolation as exc:
            if exc.constraint == "sss_ultimo_admin":
                self._log.warning("desativacao do ultimo perfil admin negada (login=%s perfil=%s)",
                                  ctx.get("login"), current["name"], extra={"action": action})
                raise OperationDenied(MSG_LAST_ADMIN)
            raise
        self._log.info("perfil %s (login=%s perfil=%s)", "desativado" if new_active == "N" else "reativado",
                       ctx.get("login"), current["name"], extra={"action": action})
        return changed

    # ------------------------------------------------------------ quem pode

    def who_can(self, ctx, script_id=None, environment_id=None):
        """Consulta "Quem pode o que" (README §4.3.B.2, CR-004 T5): so leitura, sem metodo novo no contrato.

        Por script: perfis ativos que podem roda-lo e em quais ambientes (profile_env ∩ homologacao, so
        ambientes ativos; admin: todos os homologados ativos). Por ambiente: perfis que o acessam e os
        scripts homologados ali que podem rodar. Perfis inativos vao para 'inativos'.
        """
        admin_crud.require_feature(ctx, FEATURE)
        scripts = dict((s["id"], s) for s in self._catalog.scripts_list(page=1, size=_CATALOG_MAX)["items"])
        environments = dict((a["id"], a) for a in self._catalog.environments_list(page=1, size=_CATALOG_MAX)["items"])
        result = {"scripts": sorted(scripts.values(), key=lambda s: s["name"]),
                     "environments": sorted(environments.values(), key=lambda a: a["name"]),
                     "script": None, "environment": None, "profiles": [], "inactive_items": [], "warning": None}
        sid, aid = _id(script_id), _id(environment_id)
        if sid is None and aid is None:
            return result
        exec_id = [f["id"] for f in self._rbac.features_list() if f["code"] == "EXEC_SCRIPT"]
        profiles = self._rbac.profiles_list(page=1, size=_CATALOG_MAX)["items"]
        homolog = {}

        def homologados(script):
            if script not in homolog:
                homolog[script] = set(i for i in self._catalog.homologation_get(script)
                                      if environments.get(i, {}).get("active") == "Y")
            return homolog[script]

        def linha(profile, reason, details):
            return {"id": profile["id"], "name": profile["name"], "is_admin": profile["is_admin"] == "Y",
                    "reason": reason, "details": details, "active_users": self.active_users(profile["id"])}

        if sid is not None and sid in scripts:
            result.update(self._script_runners(scripts[sid], environments, exec_id, profiles, homologados, linha))
        elif aid is not None and aid in environments:
            env = environments[aid]
            result["environment"] = env
            if env.get("active") != "Y":
                result["warning"] = u"Este ambiente está inativo: nenhum script roda nele agora."
            active = [s for s in scripts.values() if s.get("active") == "Y" and aid in homologados(s["id"])]
            for p in profiles:
                m = self._rbac.matrix_get(p["id"])
                if p["is_admin"] == "Y":
                    items, reason_text = active, u"administrador"
                elif exec_id and exec_id[0] in m["funcs"] and aid in m["ambs"]:
                    items, reason_text = [s for s in active if s["id"] in m["scrs"]], u"tem Disparar Scripts e o ambiente"
                else:
                    continue
                item = linha(p, reason_text, sorted(s["name"] for s in items))
                result["profiles" if p["active"] == "Y" else "inactive_items"].append(item)
        else:
            raise RepoNotFound("script ou ambiente inexistente")
        return result

    def _script_runners(self, script, environments, exec_id, profiles, homologated, row):
        """Perfis que podem rodar o script (regra de rbac.can_execute por perfil), ativos e inativos."""
        sid = script["id"]
        found = {"script": script, "profiles": [], "inactive_items": [], "warning": None,
                 "homologated": sorted(environments[a]["name"] for a in homologated(sid))}
        if script.get("active") != "Y":
            found["warning"] = u"Este script está inativo: ninguém consegue rodá-lo agora."
        for p in profiles:
            m = self._rbac.matrix_get(p["id"])
            if p["is_admin"] == "Y":
                envs, reason_text = homologated(sid), u"administrador"
            elif exec_id and exec_id[0] in m["funcs"] and sid in m["scrs"]:
                envs, reason_text = homologated(sid) & set(m["ambs"]), u"tem Disparar Scripts, o ambiente e o script"
            else:
                continue
            if not envs:
                continue
            item = row(p, reason_text, sorted(environments[a]["name"] for a in envs))
            found["profiles" if p["active"] == "Y" else "inactive_items"].append(item)
        return found

    def script_runners(self, script_id):
        """Quem pode rodar o script, sem guarda de funcionalidade: a mesma conta de who_can por script.

        Usada pelo quadro "Quem pode rodar" do cadastro de scripts (CR-017d), que tem guarda propria.
        Lanca RepoNotFound para script inexistente.
        """
        script = self._catalog.scripts_get(script_id)
        environments = dict((a["id"], a) for a in self._catalog.environments_list(page=1, size=_CATALOG_MAX)["items"])
        exec_id = [f["id"] for f in self._rbac.features_list() if f["code"] == "EXEC_SCRIPT"]
        profiles = self._rbac.profiles_list(page=1, size=_CATALOG_MAX)["items"]

        def homologated(sid):
            return set(i for i in self._catalog.homologation_get(sid) if environments.get(i, {}).get("active") == "Y")

        def row(profile, reason, details):
            return {"id": profile["id"], "name": profile["name"], "is_admin": profile["is_admin"] == "Y",
                    "reason": reason, "details": details, "active_users": self.active_users(profile["id"])}

        return self._script_runners(script, environments, exec_id, profiles, homologated, row)

    # --------------------------------------------------------------- matriz

    def _matrix_catalog(self):
        features = self._rbac.features_list()
        envs = self._catalog.environments_list(page=1, size=_CATALOG_MAX)["items"]
        scrs = self._catalog.scripts_list(page=1, size=_CATALOG_MAX)["items"]
        return {"funcs": dict((f["id"], f) for f in features), "ambs": dict((a["id"], a) for a in envs),
                "scrs": dict((s["id"], s) for s in scrs)}

    @staticmethod
    def _labels(cat):
        return {"funcs": dict((i, f["code"]) for i, f in cat["funcs"].items()),
                "ambs": dict((i, a["name"]) for i, a in cat["ambs"].items()),
                "scrs": dict((i, s["name"]) for i, s in cat["scrs"].items())}

    def matrix(self, ctx, profile_id):
        """Matriz do perfil para a tela: itens ativos e os inativos ja associados (somente leitura).

        Retorna {profile, perm_version, admin_warning, funcs: [{script_group, items}], ambs: [...],
        scrs: [...]}; cada item tem id, label, detail, checked, inactive e diff_label.
        """
        admin_crud.require_feature(ctx, FEATURE)
        profile = self._get(profile_id)
        current = self._rbac.matrix_get(profile["id"])
        cat = self._matrix_catalog()
        marked = dict((dim, set(current[dim])) for dim, _p in _PREFIXES)

        def item(dim, reg, label, detail, prefix):
            return {"id": reg["id"], "label": label, "detail": detail or "",
                    "checked": reg["id"] in marked[dim], "inactive": reg.get("active") != "Y",
                    "diff_label": prefix + label}

        def agrupar(dim, group_key, build):
            groups = collections.OrderedDict()
            regs = sorted(cat[dim].values(), key=lambda r: (group_key(r), r.get("code") or r.get("name"), r["id"]))
            for reg in regs:
                if reg.get("active") != "Y" and reg["id"] not in marked[dim]:
                    continue
                groups.setdefault(group_key(reg), []).append(build(reg))
            return [{"script_group": g, "items": items} for g, items in groups.items()]

        return {
            "profile": {"id": profile["id"], "name": profile["name"], "is_admin": profile["is_admin"],
                       "active": profile["active"]},
            "perm_version": profile["perm_version"],
            "admin_warning": ADMIN_WARNING if profile["is_admin"] == "Y" else None,
            "funcs": agrupar("funcs", lambda r: r.get("module") or _NO_GROUP,
                             lambda r: item("funcs", r, r["code"], r.get("name"), "")),
            "ambs": agrupar("ambs", lambda r: u"Ambientes",
                            lambda r: item("ambs", r, r["name"], r.get("description"), "amb:")),
            "scrs": agrupar("scrs", lambda r: u"%s / %s" % (r.get("script_group") or _NO_GROUP, r.get("category") or "-"),
                            lambda r: item("scrs", r, r["name"], r.get("description"), "scr:")),
        }

    def save_matrix(self, ctx, ip, profile_id, features_ids, envs, scrs, perm_version):
        """Substitui a matriz do perfil (um unico POST com as tres listas) e audita PERM_UPDATE com o diff.

        Associacoes existentes a itens inativos podem ser removidas, nunca readicionadas (README §4.3.B.1);
        so itens ativos podem ser adicionados; ID inexistente rejeita a operacao inteira. Retorna (diff ou None se nada mudou, erros).
        Lanca RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        profile = self._get(profile_id)
        try:
            self._require_admin(ctx, self._reserved(ctx, profile), "PERM_UPDATE")
        except OperationDenied as exc:
            return None, {GENERAL_FIELD: exc.message}
        sent = {"funcs": _ids(features_ids), "ambs": _ids(envs), "scrs": _ids(scrs)}
        if any(v is None for v in sent.values()):
            return None, {GENERAL_FIELD: MSG_MATRIX_ID_INVALID}
        version = _id(perm_version)
        if version is None or version != profile["perm_version"]:
            return None, {GENERAL_FIELD: admin_crud.MSG_CONFLICT}

        cat = self._matrix_catalog()
        current = dict((dim, set(ids)) for dim, ids in self._rbac.matrix_get(profile["id"]).items())
        final = {}
        for dim, _prefix in _PREFIXES:
            unknown = sent[dim] - set(cat[dim])
            if unknown:
                self._log.warning("matriz rejeitada: IDs inexistentes (login=%s perfil=%s dimensao=%s ids=%s)",
                                  ctx.get("login"), profile["name"], dim, sorted(unknown),
                                  extra={"action": "PERM_UPDATE"})
                return None, {GENERAL_FIELD: MSG_MATRIX_ID_INVALID}
            inactive = set(i for i, r in cat[dim].items() if r.get("active") != "Y")
            if (sent[dim] - current[dim]) & inactive:
                return None, {GENERAL_FIELD: MSG_MATRIX_INACTIVE}
            # Inativo ja associado pode sair (desmarcado); nunca entra de novo (checado acima).
            final[dim] = set(sent[dim])

        diff = matrix_diff(current, final, self._labels(cat))
        if diff is None:
            return None, {}
        try:
            self._rbac.matrix_save(profile["id"], sorted(final["funcs"]), sorted(final["ambs"]),
                                     sorted(final["scrs"]), expected_perm_version=version,
                                     audit=admin_crud.audit_entry(ctx, ip, "PERM_UPDATE", diff))
        except RepoConflict:
            return None, {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        except RepoViolation:
            self._log.warning("matriz rejeitada pelo repositorio (login=%s perfil=%s)", ctx.get("login"),
                              profile["name"], extra={"action": "PERM_UPDATE"})
            return None, {GENERAL_FIELD: MSG_MATRIX_ID_INVALID}
        self._log.info("matriz de permissoes alterada (login=%s perfil=%s)", ctx.get("login"), profile["name"],
                       extra={"action": "PERM_UPDATE"})
        return diff, {}


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from gluon import current
            import sss_logging
            factory = current.repo_factory
            _default = AdminProfilesService(
                rbac_repo=factory.get("rbac"),
                catalog=factory.get("catalog"),
                users=factory.get("users"),
                log=sss_logging.get_logger("sss_web", current.sss_cfg),
            )
        return _default


def list_page(ctx, filters, page, size):
    """Pagina de perfis (servico padrao)."""
    return _service().list(ctx, filters, page, size)


def form(ctx, profile_id=None):
    """Dados do formulario de perfil (servico padrao)."""
    return _service().form(ctx, profile_id)


def save(ctx, ip, profile_id, date):
    """Inclusao ou alteracao de perfil (servico padrao)."""
    return _service().save(ctx, ip, profile_id, date)


def toggle_active(ctx, ip, profile_id, version):
    """Desativacao/reativacao de perfil (servico padrao)."""
    return _service().toggle_active(ctx, ip, profile_id, version)


def matrix(ctx, profile_id):
    """Matriz de permissoes do perfil para a tela (servico padrao)."""
    return _service().matrix(ctx, profile_id)


def save_matrix(ctx, ip, profile_id, features_ids, envs, scrs, perm_version):
    """Gravacao da matriz de permissoes (servico padrao)."""
    return _service().save_matrix(ctx, ip, profile_id, features_ids, envs, scrs, perm_version)


def who_can(ctx, script_id=None, environment_id=None):
    """Consulta "Quem pode o que" (servico padrao)."""
    return _service().who_can(ctx, script_id, environment_id)
