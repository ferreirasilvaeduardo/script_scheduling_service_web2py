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
MSG_LAST_ADMIN = ui_helpers.mensagem("ultimo_admin")
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
    """Filtros da lista vindos de request.vars: nome (trecho), ativo e is_admin ('S' | 'N')."""
    input_value = input_value or {}
    filtros = {}
    nome = admin_crud.text(input_value.get("name"), 30)
    if nome and _RE_NAME_FILTER.fullmatch(nome):
        filtros["name"] = nome
    for chave in ("active", "is_admin"):
        valor = admin_crud.text(input_value.get(chave), 1)
        if valor in ("Y", "N"):
            filtros[chave] = valor
    return filtros


def matrix_diff(before, after_value, labels):
    """'+EXEC_SCRIPT, -VIEW_LOGS, +amb:PRODUCAO, -scr:carga_diaria' (ordem: dimensao, rotulo); None se igual.

    antes/depois: {'funcs': set, 'ambs': set, 'scrs': set}; rotulos: {dimensao: {id: rotulo}}.
    """
    partes = []
    for dim, prefixo in _PREFIXES:
        a, d = set(before.get(dim) or ()), set(after_value.get(dim) or ())
        nomes = labels.get(dim, {})
        mudancas = [(nomes.get(i, "#%s" % i), "+") for i in d - a] + [(nomes.get(i, "#%s" % i), "-") for i in a - d]
        for rotulo, sinal in sorted(mudancas):
            partes.append(u"%s%s%s" % (sinal, prefixo, rotulo))
    return admin_crud.free_detail(u", ".join(partes)) if partes else None


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
        pagina = self._users.list(filters={"profile_id": profile_id, "active": "Y"}, page=1,
                                       size=AFFECTED_MAX)
        return pagina["total"], [u["login"] for u in pagina["itens"]]

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
                    "usuarios_ativos": 0, "usuarios_afetados": [], "proprio": False, "registro": None}
        perfil = self._get(profile_id)
        total, logins = self.affected_users(perfil["id"])
        return {
            "id": perfil["id"],
            "name": perfil["name"],
            "description": admin_crud.normalize(perfil.get("description")) or "",
            "is_admin": perfil["is_admin"],
            "active": perfil["active"],
            "version": admin_crud.version(perfil, EDITABLE_FIELDS),
            "usuarios_ativos": total,
            "usuarios_afetados": logins,
            "proprio": ctx.get("profile_id") == perfil["id"],
            "registro": ui_helpers.registro(perfil, ctx),
        }

    def _validate(self, date, errors):
        nome = admin_crud.identifier(date.get("name"), errors, "name")
        if nome is None:
            errors["name"] = MSG_NAME_REQUIRED
        elif "name" not in errors and not _RE_NAME.fullmatch(nome):
            errors["name"] = MSG_NAME_INVALID
        descricao = admin_crud.free_text(date.get("description"), errors, "description")
        if descricao is not None and len(descricao) > DESCRIPTION_MAX_LENGTH:
            errors["description"] = MSG_DESCRIPTION_LENGTH
        is_admin = "Y" if admin_crud.text(date.get("is_admin"), 1) == "Y" else "N"
        return nome, descricao, is_admin

    def _violation(self, ctx, exc, errors):
        if exc.constraint == "sss_ultimo_admin":
            errors[GENERAL_FIELD] = MSG_LAST_ADMIN
        else:
            campo, mensagem = _FIELD_BY_CONSTRAINT.get(exc.constraint, (GENERAL_FIELD, admin_crud.MSG_FAILURE))
            errors[campo] = mensagem
        self._log.warning("cadastro de perfil rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"action": FEATURE})

    def _require_admin(self, ctx, condition, operation):
        admin_crud.require_admin(ctx, condition, MSG_ADMIN_ONLY, self._log, operation)

    def _reserved(self, ctx, profile):
        """Perfil que so admin altera (CR-008, E1): perfil de administrador ou o proprio perfil."""
        return profile["is_admin"] == "Y" or ctx.get("profile_id") == profile["id"]

    def save(self, ctx, ip, profile_id, date):
        """Inclui (perfil_id vazio) ou altera um perfil: nome, descricao, is_admin ('S' marcado).

        Retorna (id, erros). Remover is_admin do ultimo perfil admin ativo gera erro geral.
        Lanca RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        erros = {}
        if profile_id in (None, ""):
            nome, descricao, is_admin = self._validate(date, erros)
            if erros:
                return None, erros
            try:
                self._require_admin(ctx, is_admin == "Y", "CREATE")
            except OperationDenied as exc:
                return None, {GENERAL_FIELD: exc.message}
            novo = {"name": nome, "description": descricao, "is_admin": is_admin, "active": "Y"}
            auditoria = admin_crud.audit_entry(ctx, ip, "CREATE",
                                             admin_crud.insert_detail(novo, INSERT_FIELDS))
            try:
                criado = self._rbac.profiles_insert(novo, audit=auditoria)
            except RepoViolation as exc:
                self._violation(ctx, exc, erros)
                return None, erros
            self._log.info("perfil incluido (login=%s perfil=%s)", ctx.get("login"), criado["name"],
                           extra={"action": "CREATE"})
            return criado["id"], {}

        atual = self._get(profile_id)
        nome, descricao, is_admin = self._validate(date, erros)
        if erros:
            return atual["id"], erros
        if admin_crud.text(date.get("version"), 64) != admin_crud.version(atual, EDITABLE_FIELDS):
            erros[GENERAL_FIELD] = admin_crud.MSG_CONFLICT
            return atual["id"], erros
        try:
            self._require_admin(ctx, is_admin == "Y" or self._reserved(ctx, atual), "UPDATE")
        except OperationDenied as exc:
            erros[GENERAL_FIELD] = exc.message
            return atual["id"], erros
        if ctx.get("profile_id") == atual["id"] and atual["is_admin"] == "Y" and is_admin == "N":
            # Autoprotecao (README §4.3.B): vale mesmo havendo outros administradores.
            self._log.warning("remocao de is_admin do proprio perfil negada (login=%s perfil=%s)",
                              ctx.get("login"), atual["name"], extra={"action": "UPDATE"})
            erros[GENERAL_FIELD] = MSG_SELF_ADMIN
            return atual["id"], erros
        depois = dict(atual, name=nome, description=descricao, is_admin=is_admin)
        detalhe = admin_crud.changes_detail(atual, depois, EDITABLE_FIELDS)
        if detalhe is None:
            return atual["id"], {}
        try:
            self._rbac.profiles_update(
                atual["id"], {"name": nome, "description": descricao, "is_admin": is_admin},
                expected=admin_crud.expected(atual, EDITABLE_FIELDS),
                audit=admin_crud.audit_entry(ctx, ip, "UPDATE", detalhe))
        except RepoConflict:
            erros[GENERAL_FIELD] = admin_crud.MSG_CONFLICT
            return atual["id"], erros
        except RepoViolation as exc:
            self._violation(ctx, exc, erros)
            return atual["id"], erros
        self._log.info("perfil alterado (login=%s perfil=%s)", ctx.get("login"), nome, extra={"action": "UPDATE"})
        return atual["id"], {}

    def toggle_active(self, ctx, ip, profile_id, version):
        """Desativa (DEACTIVATE, com usuarios afetados) ou reativa (UPDATE) o perfil.

        Lanca OperationDenied (ultimo administrador), RepoConflict, RepoNotFound e AccessDenied.
        """
        admin_crud.require_feature(ctx, FEATURE)
        atual = self._get(profile_id)
        if admin_crud.text(version, 64) != admin_crud.version(atual, EDITABLE_FIELDS):
            raise RepoConflict("versao divergente")
        novo_ativo = "N" if atual["active"] == "Y" else "Y"
        self._require_admin(ctx, atual["is_admin"] == "Y" and ctx.get("profile_id") != atual["id"], "DEACTIVATE")
        if novo_ativo == "N" and ctx.get("profile_id") == atual["id"]:
            self._log.warning("desativacao do proprio perfil negada (login=%s perfil=%s)",
                              ctx.get("login"), atual["name"], extra={"action": "DEACTIVATE"})
            raise OperationDenied(MSG_SELF_DEACTIVATE)
        detalhe = admin_crud.changes_detail(atual, dict(atual, active=novo_ativo), ("active",))
        acao = "DEACTIVATE" if novo_ativo == "N" else "UPDATE"
        if novo_ativo == "N":
            detalhe = u"%s; usuários ativos afetados: %d" % (detalhe, self.active_users(atual["id"]))
        try:
            alterado = self._rbac.profiles_update(
                atual["id"], {"active": novo_ativo}, expected=admin_crud.expected(atual, EDITABLE_FIELDS),
                audit=admin_crud.audit_entry(ctx, ip, acao, detalhe))
        except RepoViolation as exc:
            if exc.constraint == "sss_ultimo_admin":
                self._log.warning("desativacao do ultimo perfil admin negada (login=%s perfil=%s)",
                                  ctx.get("login"), atual["name"], extra={"action": acao})
                raise OperationDenied(MSG_LAST_ADMIN)
            raise
        self._log.info("perfil %s (login=%s perfil=%s)", "desativado" if novo_ativo == "N" else "reativado",
                       ctx.get("login"), atual["name"], extra={"action": acao})
        return alterado

    # ------------------------------------------------------------ quem pode

    def who_can(self, ctx, script_id=None, environment_id=None):
        """Consulta "Quem pode o que" (README §4.3.B.2, CR-004 T5): so leitura, sem metodo novo no contrato.

        Por script: perfis ativos que podem roda-lo e em quais ambientes (perfil_amb ∩ homologacao, so
        ambientes ativos; admin: todos os homologados ativos). Por ambiente: perfis que o acessam e os
        scripts homologados ali que podem rodar. Perfis inativos vao para 'inativos'.
        """
        admin_crud.require_feature(ctx, FEATURE)
        scripts = dict((s["id"], s) for s in self._catalog.scripts_list(page=1, size=_CATALOG_MAX)["itens"])
        ambientes = dict((a["id"], a) for a in self._catalog.environments_list(page=1, size=_CATALOG_MAX)["itens"])
        resultado = {"scripts": sorted(scripts.values(), key=lambda s: s["name"]),
                     "environments": sorted(ambientes.values(), key=lambda a: a["name"]),
                     "script": None, "environment": None, "profiles": [], "inativos": [], "aviso": None}
        sid, aid = _id(script_id), _id(environment_id)
        if sid is None and aid is None:
            return resultado
        exec_id = [f["id"] for f in self._rbac.features_list() if f["code"] == "EXEC_SCRIPT"]
        perfis = self._rbac.profiles_list(page=1, size=_CATALOG_MAX)["itens"]
        homolog = {}

        def homologados(script):
            if script not in homolog:
                homolog[script] = set(i for i in self._catalog.homologation_get(script)
                                      if ambientes.get(i, {}).get("active") == "Y")
            return homolog[script]

        def linha(profile, reason, details):
            return {"id": profile["id"], "name": profile["name"], "is_admin": profile["is_admin"] == "Y",
                    "reason": reason, "detalhes": details, "usuarios_ativos": self.active_users(profile["id"])}

        if sid is not None and sid in scripts:
            script = scripts[sid]
            resultado["script"] = script
            if script.get("active") != "Y":
                resultado["aviso"] = u"Este script está inativo: ninguém consegue rodá-lo agora."
            for p in perfis:
                m = self._rbac.matrix_get(p["id"])
                if p["is_admin"] == "Y":
                    ambs, motivo = homologados(sid), u"administrador"
                elif exec_id and exec_id[0] in m["funcs"] and sid in m["scrs"]:
                    ambs, motivo = homologados(sid) & set(m["ambs"]), u"tem Disparar Scripts, o ambiente e o script"
                else:
                    continue
                if not ambs:
                    continue
                item = linha(p, motivo, sorted(ambientes[a]["name"] for a in ambs))
                resultado["profiles" if p["active"] == "Y" else "inativos"].append(item)
        elif aid is not None and aid in ambientes:
            amb = ambientes[aid]
            resultado["environment"] = amb
            if amb.get("active") != "Y":
                resultado["aviso"] = u"Este ambiente está inativo: nenhum script roda nele agora."
            ativos = [s for s in scripts.values() if s.get("active") == "Y" and aid in homologados(s["id"])]
            for p in perfis:
                m = self._rbac.matrix_get(p["id"])
                if p["is_admin"] == "Y":
                    lista, motivo = ativos, u"administrador"
                elif exec_id and exec_id[0] in m["funcs"] and aid in m["ambs"]:
                    lista, motivo = [s for s in ativos if s["id"] in m["scrs"]], u"tem Disparar Scripts e o ambiente"
                else:
                    continue
                item = linha(p, motivo, sorted(s["name"] for s in lista))
                resultado["profiles" if p["active"] == "Y" else "inativos"].append(item)
        else:
            raise RepoNotFound("script ou ambiente inexistente")
        return resultado

    # --------------------------------------------------------------- matriz

    def _matrix_catalog(self):
        funcs = self._rbac.features_list()
        ambs = self._catalog.environments_list(page=1, size=_CATALOG_MAX)["itens"]
        scrs = self._catalog.scripts_list(page=1, size=_CATALOG_MAX)["itens"]
        return {"funcs": dict((f["id"], f) for f in funcs), "ambs": dict((a["id"], a) for a in ambs),
                "scrs": dict((s["id"], s) for s in scrs)}

    @staticmethod
    def _labels(cat):
        return {"funcs": dict((i, f["code"]) for i, f in cat["funcs"].items()),
                "ambs": dict((i, a["name"]) for i, a in cat["ambs"].items()),
                "scrs": dict((i, s["name"]) for i, s in cat["scrs"].items())}

    def matrix(self, ctx, profile_id):
        """Matriz do perfil para a tela: itens ativos e os inativos ja associados (somente leitura).

        Retorna {perfil, perm_versao, aviso_admin, funcs: [{grupo, itens}], ambs: [{grupo, itens}],
        scrs: [{grupo, itens}]}; cada item tem id, rotulo, detalhe, marcado, inativo e rotulo_diff.
        """
        admin_crud.require_feature(ctx, FEATURE)
        perfil = self._get(profile_id)
        atual = self._rbac.matrix_get(perfil["id"])
        cat = self._matrix_catalog()
        marcados = dict((dim, set(atual[dim])) for dim, _p in _PREFIXES)

        def item(dim, reg, label, detail, prefix):
            return {"id": reg["id"], "rotulo": label, "detail": detail or "",
                    "marcado": reg["id"] in marcados[dim], "inativo": reg.get("active") != "Y",
                    "rotulo_diff": prefix + label}

        def agrupar(dim, group_key, build):
            grupos = collections.OrderedDict()
            regs = sorted(cat[dim].values(), key=lambda r: (group_key(r), r.get("code") or r.get("name"), r["id"]))
            for reg in regs:
                if reg.get("active") != "Y" and reg["id"] not in marcados[dim]:
                    continue
                grupos.setdefault(group_key(reg), []).append(build(reg))
            return [{"script_group": g, "itens": itens} for g, itens in grupos.items()]

        return {
            "perfil": {"id": perfil["id"], "name": perfil["name"], "is_admin": perfil["is_admin"],
                       "active": perfil["active"]},
            "perm_version": perfil["perm_version"],
            "aviso_admin": ADMIN_WARNING if perfil["is_admin"] == "Y" else None,
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
        perfil = self._get(profile_id)
        try:
            self._require_admin(ctx, self._reserved(ctx, perfil), "PERM_UPDATE")
        except OperationDenied as exc:
            return None, {GENERAL_FIELD: exc.message}
        enviados = {"funcs": _ids(features_ids), "ambs": _ids(envs), "scrs": _ids(scrs)}
        if any(v is None for v in enviados.values()):
            return None, {GENERAL_FIELD: MSG_MATRIX_ID_INVALID}
        versao = _id(perm_version)
        if versao is None or versao != perfil["perm_version"]:
            return None, {GENERAL_FIELD: admin_crud.MSG_CONFLICT}

        cat = self._matrix_catalog()
        atual = dict((dim, set(ids)) for dim, ids in self._rbac.matrix_get(perfil["id"]).items())
        final = {}
        for dim, _prefixo in _PREFIXES:
            desconhecidos = enviados[dim] - set(cat[dim])
            if desconhecidos:
                self._log.warning("matriz rejeitada: IDs inexistentes (login=%s perfil=%s dimensao=%s ids=%s)",
                                  ctx.get("login"), perfil["name"], dim, sorted(desconhecidos),
                                  extra={"action": "PERM_UPDATE"})
                return None, {GENERAL_FIELD: MSG_MATRIX_ID_INVALID}
            inativos = set(i for i, r in cat[dim].items() if r.get("active") != "Y")
            if (enviados[dim] - atual[dim]) & inativos:
                return None, {GENERAL_FIELD: MSG_MATRIX_INACTIVE}
            # Inativo ja associado pode sair (desmarcado); nunca entra de novo (checado acima).
            final[dim] = set(enviados[dim])

        diff = matrix_diff(atual, final, self._labels(cat))
        if diff is None:
            return None, {}
        try:
            self._rbac.matrix_save(perfil["id"], sorted(final["funcs"]), sorted(final["ambs"]),
                                     sorted(final["scrs"]), expected_perm_version=versao,
                                     audit=admin_crud.audit_entry(ctx, ip, "PERM_UPDATE", diff))
        except RepoConflict:
            return None, {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        except RepoViolation:
            self._log.warning("matriz rejeitada pelo repositorio (login=%s perfil=%s)", ctx.get("login"),
                              perfil["name"], extra={"action": "PERM_UPDATE"})
            return None, {GENERAL_FIELD: MSG_MATRIX_ID_INVALID}
        self._log.info("matriz de permissoes alterada (login=%s perfil=%s)", ctx.get("login"), perfil["name"],
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
            fabrica = current.repo_factory
            _default = AdminProfilesService(
                rbac_repo=fabrica.get("rbac"),
                catalog=fabrica.get("catalog"),
                users=fabrica.get("users"),
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
