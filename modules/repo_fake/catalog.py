# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de catalogo (README §2.5, §4.3.A, §6.3, §10)."""
import copy
import re

from repo_catalog import RepoCatalog
from repo_errors import RepoConflict, RepoNotFound, RepoViolation
from repo_fake.store import paginate

_RE_ENV_NAME = re.compile(r"^[A-Z0-9_]{1,30}$")
_RE_PRM_CODE = re.compile(r"^[a-z0-9_]{1,30}$")
_RE_PRM_FLAG = re.compile(r"^-{1,2}[A-Za-z0-9][A-Za-z0-9_-]{0,27}$")


class RepoCatalogFake(RepoCatalog):
    """Implementacao em memoria com semantica Oracle para o catalogo."""

    def __init__(self, store):
        self._store = store

    # -------------------------------------------------------------------------
    # Ambientes (tbsss_environments)
    # -------------------------------------------------------------------------

    def environments_list(self, filters=None, page=1, size=20):
        """Lista ambientes com paginacao deterministica por nome ASC, id ASC."""
        filters = filters or {}
        with self._store.lock_catalog:
            items = list(self._store.environments.values())

            name_f = filters.get("name")
            if name_f:
                items = [a for a in items if name_f.upper() in a["name"].upper()]

            active_f = filters.get("active")
            if active_f:
                items = [a for a in items if a["active"] == active_f]

            items.sort(key=lambda x: (x.get("name", ""), x["id"]))
            return paginate(items, page=page, size=size)

    def environments_get(self, id):
        """Retorna dict do ambiente pelo ID ou lanca RepoNotFound."""
        with self._store.lock_catalog:
            if id not in self._store.environments:
                raise RepoNotFound("Ambiente ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.environments[id])

    def _auditar_ambiente(self, audit, environment_id):
        if audit:
            self._store.register_internal_audit(
                actor=audit.get("actor"),
                ip=audit.get("ip"),
                action=audit["action"],
                entity="tbsss_environments",
                entity_id=environment_id,
                detail=audit.get("detail"),
            )

    def environments_insert(self, data, audit=None, actor=None):
        """Insere novo ambiente com validacao de CKs, UK e DSN, auditando na mesma operacao."""
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            name = data.get("name")
            if not name or not _RE_ENV_NAME.fullmatch(name):
                raise RepoViolation("Nome de ambiente invalido (esperado: 1-30 chars [A-Z0-9_])", constraint="ck_tbsss_env_name")

            for a in self._store.environments.values():
                if a["name"].upper() == name.upper():
                    raise RepoViolation("Ambiente com nome '%s' ja existe" % name, constraint="uk_tbsss_env_name")

            connection = data.get("connection")
            if connection and "@" in connection:
                raise RepoViolation("Conexao nao pode conter credencial (@)", constraint="ck_tbsss_env_connection")

            active = data.get("active", "Y")
            if active not in ("Y", "N"):
                raise RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_env_active")
            production = data.get("is_production", "N")
            if production not in ("Y", "N"):
                raise RepoViolation("Flag producao deve ser 'Y' ou 'N'", constraint="ck_tbsss_env_prod")

            aid = self._store.next_id("tbsss_environments")
            new = {
                "id": aid,
                "name": name,
                "description": data.get("description", ""),
                "connection": connection,
                "active": active,
                "is_production": production,
                "created_at": data.get("created_at"),
            }
            self._store.stamp_insert(new, actor)
            self._store.environments[aid] = copy.deepcopy(new)
            self._auditar_ambiente(audit, aid)
            return copy.deepcopy(new)

    def environments_update(self, id, data, expected=None, audit=None, actor=None):
        """Altera ambiente (nome imutavel, trigger tr_tbsss_env_bu), condicional a 'esperado'."""
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            if id not in self._store.environments:
                raise RepoNotFound("Ambiente ID %s nao encontrado" % id)

            current = self._store.environments[id]
            for field, value in (expected or {}).items():
                if current.get(field) != value:
                    raise RepoConflict("Ambiente ID %s alterado por outra operacao (%s)" % (id, field))

            new_name = data.get("name")
            if new_name is not None and new_name != current["name"]:
                raise RepoViolation("Nome de ambiente e imutavel", constraint="tr_tbsss_env_bu")

            changes = {}
            new_connection = data.get("connection")
            if new_connection is not None:
                if "@" in new_connection:
                    raise RepoViolation("Conexao nao pode conter credencial (@)", constraint="ck_tbsss_env_connection")
                changes["connection"] = new_connection
            elif "connection" in data:
                changes["connection"] = None

            if "description" in data:
                changes["description"] = data["description"]

            new_active = data.get("active")
            if new_active is not None:
                if new_active not in ("Y", "N"):
                    raise RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_env_active")
                changes["active"] = new_active

            new_production = data.get("is_production")
            if new_production is not None:
                if new_production not in ("Y", "N"):
                    raise RepoViolation("Flag producao deve ser 'Y' ou 'N'", constraint="ck_tbsss_env_prod")
                changes["is_production"] = new_production

            # Validacao completa antes de aplicar: um UPDATE rejeitado nao altera nenhuma coluna.
            current.update(changes)
            self._store.stamp_update(current, actor)
            self._auditar_ambiente(audit, id)
            return copy.deepcopy(current)

    # -------------------------------------------------------------------------
    # Scripts (tbsss_scripts)
    # -------------------------------------------------------------------------

    def _auditar_script(self, audit, script_id):
        if audit:
            self._store.register_internal_audit(
                actor=audit.get("actor"),
                ip=audit.get("ip"),
                action=audit["action"],
                entity="tbsss_scripts",
                entity_id=script_id,
                detail=audit.get("detail"),
            )

    def _vinculos_do_script(self, script_id):
        items = [sp for sp in self._store.script_param.values() if sp["script_id"] == script_id]
        items.sort(key=lambda x: x["sort_order"])
        return items

    def _regras_tipo_param(self, param_type, parameter_ids):
        # README §6.3: NENHUM nao aceita vinculos; NOMEADO exige flag em todo parametro vinculado.
        if param_type == "NONE" and parameter_ids:
            raise RepoViolation("Script NENHUM com vinculos", constraint="sss_scr_nenhum_vinculado")
        if param_type == "NAMED":
            for pid in parameter_ids:
                if not self._store.parameters[pid].get("param_flag"):
                    raise RepoViolation("Parametro sem flag em script NOMEADO", constraint="sss_scr_nomeado_sem_flag")

    def scripts_list(self, filters=None, page=1, size=20):
        """Lista scripts com paginacao deterministica por nome ASC, id ASC, homologacoes e qtd de parametros."""
        filters = filters or {}
        with self._store.lock_catalog:
            items = list(self._store.scripts.values())

            name_f = filters.get("name")
            if name_f:
                items = [s for s in items if name_f.lower() in s["name"].lower()]
            for key in ("script_group", "category", "interpreter", "active"):
                value = filters.get(key)
                if value:
                    items = [s for s in items if s.get(key) == value]

            items.sort(key=lambda x: (x.get("name", ""), x["id"]))
            page_ = paginate(items, page=page, size=size)
            for item in page_["items"]:
                item["homologated_environments"] = sorted(
                    self._store.environments[sa["environment_id"]]["name"] for sa in self._store.script_env.values()
                    if sa["script_id"] == item["id"] and sa["environment_id"] in self._store.environments)
                item["param_count"] = len(self._vinculos_do_script(item["id"]))
            return page_

    def scripts_get(self, id):
        """Retorna dict do script pelo ID ou lanca RepoNotFound."""
        with self._store.lock_catalog:
            if id not in self._store.scripts:
                raise RepoNotFound("Script ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.scripts[id])

    def _validar_script(self, data, current_value=None):
        """CKs da tabela 6 sobre o registro resultante (atual + dados); devolve as mudancas validadas."""
        base = dict(current_value or {}, **data)
        if not base.get("name"):
            raise RepoViolation("Nome de script e obrigatorio")
        if base.get("param_type", "NAMED") not in ("NAMED", "POSITIONAL", "NONE"):
            raise RepoViolation("Tipo de parametro invalido", constraint="ck_tbsss_scr_ptype")
        if base.get("active", "Y") not in ("Y", "N"):
            raise RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_scr_active")
        if base.get("interpreter") not in ("PYTHON3", "BASH", "SH"):
            raise RepoViolation("Interpretador fora da allowlist", constraint="ck_tbsss_scr_int")
        pfile = base.get("path_file") or ""
        # ck_tbsss_scr_path (README §10, CR-005): absoluto, sem '..', '//' nem '\\'; ate 500 caracteres.
        if (not pfile.startswith("/") or ".." in pfile or "//" in pfile or "\\" in pfile
                or len(pfile) > 500):
            raise RepoViolation("path_file deve ser absoluto e sem '..'", constraint="ck_tbsss_scr_path")
        if not (1 <= int(base.get("max_parallel_env", 1)) <= 999):
            raise RepoViolation("max_qtd_parallel_env deve estar entre 1 e 999", constraint="ck_tbsss_scr_paral")
        tmout = base.get("timeout_s")
        if tmout is not None and int(tmout) <= 0:
            raise RepoViolation("timeout_seg deve ser maior que zero", constraint="ck_tbsss_scr_tmout")
        for sid, s in self._store.scripts.items():
            # UK do Oracle diferencia maiusculas (README §8.5): 'Carga' e 'carga' sao nomes distintos.
            if (current_value is None or sid != current_value["id"]) and s["name"] == base["name"]:
                raise RepoViolation("Script com nome '%s' ja existe" % base["name"], constraint="uk_tbsss_scr_name")

    def scripts_insert(self, data, audit=None, actor=None):
        """Insere novo script com validacoes de seguranca e CKs, auditando na mesma operacao."""
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            self._validar_script(data)
            sid = self._store.next_id("tbsss_scripts")
            tmout = data.get("timeout_s")
            new = {
                "id": sid,
                "name": data["name"],
                "description": data.get("description", ""),
                "script_group": data.get("script_group"),
                "category": data.get("category"),
                "stage": data.get("stage"),
                "interpreter": data["interpreter"],
                "path_file": data["path_file"],
                "param_type": data.get("param_type", "NAMED"),
                "max_parallel_env": int(data.get("max_parallel_env", 1)),
                "timeout_s": int(tmout) if tmout is not None else None,
                "active": data.get("active", "Y"),
            }
            self._store.stamp_insert(new, actor)
            self._store.scripts[sid] = copy.deepcopy(new)
            self._auditar_script(audit, sid)
            return copy.deepcopy(new)

    def scripts_update(self, id, data, expected=None, audit=None, actor=None):
        """Altera script (CKs, esperado e regras de param_type x vinculos) na mesma operacao."""
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            if id not in self._store.scripts:
                raise RepoNotFound("Script ID %s nao encontrado" % id)
            current = self._store.scripts[id]
            for field, value in (expected or {}).items():
                if current.get(field) != value:
                    raise RepoConflict("Script ID %s alterado por outra operacao (%s)" % (id, field))
            fields = ("name", "description", "script_group", "category", "stage", "interpreter", "path_file",
                      "param_type", "max_parallel_env", "timeout_s", "active")
            changes = dict((k, data[k]) for k in fields if k in data)
            self._validar_script(changes, current)
            if "param_type" in changes and changes["param_type"] != current["param_type"]:
                self._regras_tipo_param(changes["param_type"],
                                        [v["parameter_id"] for v in self._vinculos_do_script(id)])
            if "max_parallel_env" in changes:
                changes["max_parallel_env"] = int(changes["max_parallel_env"])
            if changes.get("timeout_s") is not None:
                changes["timeout_s"] = int(changes["timeout_s"])
            current.update(changes)
            self._store.stamp_update(current, actor)
            self._auditar_script(audit, id)
            return copy.deepcopy(current)

    # -------------------------------------------------------------------------
    # Homologacao de Scripts por Ambiente (tbsss_script_env)
    # -------------------------------------------------------------------------

    def homologation_get(self, script_id):
        """Retorna lista de environment_id homologados para o script."""
        with self._store.lock_catalog:
            if script_id not in self._store.scripts:
                raise RepoNotFound("Script ID %s nao encontrado" % script_id)
            envs = [
                sa["environment_id"]
                for sa in self._store.script_env.values()
                if sa["script_id"] == script_id
            ]
            envs.sort()
            return copy.deepcopy(envs)

    def homologation_save(self, script_id, environment_ids, expected=None, audit=None, actor=None):
        """Substitui homologacoes do script por diferenca (FK, esperado e auditoria na mesma operacao).

        Os vinculos que continuam mantem o created_*; havendo mudanca, o script recebe updated_* (CR-006).
        """
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            if script_id not in self._store.scripts:
                raise RepoNotFound("Script ID %s nao encontrado" % script_id)
            if expected is not None and sorted(int(x) for x in expected) != self.homologation_get(script_id):
                raise RepoConflict("Homologacao do script ID %s alterada por outra operacao" % script_id)

            ids = sorted(set(int(x) for x in (environment_ids or [])))
            for aid in ids:
                if aid not in self._store.environments:
                    raise RepoViolation("Ambiente ID %s nao existe" % aid, constraint="fk_tbsss_senv_env")

            current = dict((v["environment_id"], k) for k, v in self._store.script_env.items()
                          if v["script_id"] == script_id)
            for aid, k in current.items():
                if aid not in ids:
                    del self._store.script_env[k]
            for aid in ids:
                if aid not in current:
                    nid = self._store.next_id("tbsss_script_env")
                    self._store.script_env[nid] = self._store.stamp_insert(
                        {"id": nid, "script_id": script_id, "environment_id": aid}, actor)
            if set(current) != set(ids):
                self._store.stamp_update(self._store.scripts[script_id], actor)

            self._auditar_script(audit, script_id)
            return copy.deepcopy(self.homologation_get(script_id))

    # -------------------------------------------------------------------------
    # Parametros (tbsss_parameters)
    # -------------------------------------------------------------------------

    def parameters_list(self, filters=None, page=1, size=20):
        """Lista parametros com paginacao deterministica por codigo ASC, id ASC."""
        filters = filters or {}
        with self._store.lock_catalog:
            items = list(self._store.parameters.values())

            code_f = filters.get("code")
            if code_f:
                items = [p for p in items if code_f.lower() in p["code"].lower()]

            label_f = filters.get("label")
            if label_f:
                items = [p for p in items if label_f.lower() in p["label"].lower()]

            kind_f = filters.get("component_type")
            if kind_f:
                items = [p for p in items if p["component_type"] == kind_f]

            active_f = filters.get("active")
            if active_f:
                items = [p for p in items if p["active"] == active_f]

            items.sort(key=lambda x: (x.get("code", ""), x["id"]))
            page_ = paginate(items, page=page, size=size)
            for item in page_["items"]:
                item["script_count"] = sum(1 for sp in self._store.script_param.values()
                                          if sp["parameter_id"] == item["id"])
            return page_

    def parameters_get(self, id):
        """Retorna dict do parametro pelo ID ou lanca RepoNotFound."""
        with self._store.lock_catalog:
            if id not in self._store.parameters:
                raise RepoNotFound("Parametro ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.parameters[id])

    def _auditar_parametro(self, audit, parameter_id):
        if audit:
            self._store.register_internal_audit(
                actor=audit.get("actor"),
                ip=audit.get("ip"),
                action=audit["action"],
                entity="tbsss_parameters",
                entity_id=parameter_id,
                detail=audit.get("detail"),
            )

    def parameters_insert(self, data, audit=None, actor=None):
        """Insere novo parametro validando CKs e UK, auditando na mesma operacao."""
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            code = data.get("code")
            if not code or not _RE_PRM_CODE.fullmatch(code):
                raise RepoViolation("Codigo de parametro invalido (esperado: 1-30 chars [a-z0-9_])", constraint="ck_tbsss_prm_code")

            for p in self._store.parameters.values():
                if p["code"] == code:
                    raise RepoViolation("Parametro com codigo '%s' ja existe" % code, constraint="uk_tbsss_prm_code")

            tcomp = data.get("component_type")
            if tcomp not in ("TEXT", "NUMBER", "DATE", "SELECT", "CHECKBOX"):
                raise RepoViolation("Tipo de componente invalido", constraint="ck_tbsss_prm_ctype")

            flag = data.get("param_flag")
            if flag is not None and flag != "":
                if not _RE_PRM_FLAG.fullmatch(flag):
                    raise RepoViolation("Flag param_nomeado invalida", constraint="ck_tbsss_prm_flag")
            else:
                flag = None

            sens = data.get("sensitive", "N")
            if sens not in ("Y", "N"):
                raise RepoViolation("sensivel deve ser 'Y' ou 'N'", constraint="ck_tbsss_prm_sens")

            active = data.get("active", "Y")
            if active not in ("Y", "N"):
                raise RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_prm_active")

            pid = self._store.next_id("tbsss_parameters")
            new = {
                "id": pid,
                "code": code,
                "param_flag": flag,
                "label": data.get("label", ""),
                "description": data.get("description", ""),
                "component_type": tcomp,
                "options_json": data.get("options_json"),
                "default_value": data.get("default_value"),
                "validation_regex": data.get("validation_regex"),
                "sensitive": sens,
                "active": active,
            }
            self._store.stamp_insert(new, actor)
            self._store.parameters[pid] = copy.deepcopy(new)
            self._auditar_parametro(audit, pid)
            return copy.deepcopy(new)

    def parameters_update(self, id, data, expected=None, audit=None, actor=None):
        """Altera parametro (CKs, dependencias de vinculo e 'esperado') na mesma operacao."""
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            if id not in self._store.parameters:
                raise RepoNotFound("Parametro ID %s nao encontrado" % id)

            current = self._store.parameters[id]
            for field, value in (expected or {}).items():
                if current.get(field) != value:
                    raise RepoConflict("Parametro ID %s alterado por outra operacao (%s)" % (id, field))

            changes = dict((k, data[k]) for k in ("label", "description", "options_json", "default_value",
                                                    "validation_regex") if k in data)
            if "param_flag" in data:
                flag = data["param_flag"] or None
                if flag is not None and not _RE_PRM_FLAG.fullmatch(flag):
                    raise RepoViolation("Flag param_nomeado invalida", constraint="ck_tbsss_prm_flag")
                changes["param_flag"] = flag
            if "component_type" in data:
                if data["component_type"] not in ("TEXT", "NUMBER", "DATE", "SELECT", "CHECKBOX"):
                    raise RepoViolation("Tipo de componente invalido", constraint="ck_tbsss_prm_ctype")
                changes["component_type"] = data["component_type"]
            for field, ck in (("sensitive", "ck_tbsss_prm_sens"), ("active", "ck_tbsss_prm_active")):
                if field in data:
                    if data[field] not in ("Y", "N"):
                        raise RepoViolation("Flag %s deve ser 'Y' ou 'N'" % field, constraint=ck)
                    changes[field] = data[field]

            # Regras de dependencia (README §10) avaliadas sob o mesmo lock da alteracao.
            scripts = [self._store.scripts[sp["script_id"]] for sp in self._store.script_param.values()
                       if sp["parameter_id"] == id and sp["script_id"] in self._store.scripts]
            if scripts and changes.get("component_type", current["component_type"]) != current["component_type"]:
                raise RepoViolation("Tipo de componente com vinculos", constraint="sss_prm_tipo_vinculado")
            if "param_flag" in changes and changes["param_flag"] != current["param_flag"] \
                    and any(s.get("param_type") == "NAMED" for s in scripts):
                raise RepoViolation("Flag com vinculo NOMEADO", constraint="sss_prm_flag_nomeado")
            if changes.get("active") == "N" and current["active"] == "Y" and any(s.get("active") == "Y" for s in scripts):
                raise RepoViolation("Desativacao com vinculo a script ativo", constraint="sss_prm_vinculo_ativo")

            current.update(changes)
            self._store.stamp_update(current, actor)
            self._auditar_parametro(audit, id)
            return copy.deepcopy(current)

    def parameter_links(self, parameter_id):
        """Retorna lista de scripts vinculados ao parametro para verificacao de desativacao."""
        with self._store.lock_catalog:
            script_ids = {
                sp["script_id"]
                for sp in self._store.script_param.values()
                if sp["parameter_id"] == parameter_id
            }
            result = [
                s for sid, s in self._store.scripts.items()
                if sid in script_ids
            ]
            result.sort(key=lambda x: (x.get("name", ""), x["id"]))
            return copy.deepcopy(result)

    # -------------------------------------------------------------------------
    # Vinculos de Parametros em Scripts (tbsss_script_param)
    # -------------------------------------------------------------------------

    def script_params_get(self, script_id):
        """Retorna lista de parametros vinculados ao script ordenados por ordem."""
        with self._store.lock_catalog:
            if script_id not in self._store.scripts:
                raise RepoNotFound("Script ID %s nao encontrado" % script_id)

            links = [
                sp for sp in self._store.script_param.values()
                if sp["script_id"] == script_id
            ]
            links.sort(key=lambda x: x["sort_order"])

            result = []
            for v in links:
                param = self._store.parameters.get(v["parameter_id"])
                if param:
                    item = copy.deepcopy(param)
                    item["script_id"] = script_id
                    item["parameter_id"] = param["id"]
                    item["sort_order"] = v["sort_order"]
                    item["required"] = v["required"]
                    item["default_value_override"] = v.get("default_value_override")
                    result.append(item)
            return copy.deepcopy(result)

    def script_params_save(self, script_id, links, expected=None, audit=None, actor=None):
        """Substitui os vinculos do script (UKs, FK, regras de param_type, esperado e auditoria).

        Apaga e reinsere (UK script_id + ordem), mas cada parametro que continua leva o created_*;
        o updated_* do vinculo so muda se ordem, obrigatorio ou default_value_override mudar (CR-006).
        """
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            if script_id not in self._store.scripts:
                raise RepoNotFound("Script ID %s nao encontrado" % script_id)
            if expected is not None:
                read = [(v["parameter_id"], v["sort_order"], v["required"], v.get("default_value_override"))
                         for v in self._vinculos_do_script(script_id)]
                if [tuple(e) for e in expected] != read:
                    raise RepoConflict("Vinculos do script ID %s alterados por outra operacao" % script_id)

            params_seen = set()
            orders_seen = set()
            new_links = []
            for item in (links or []):
                pid = int(item["parameter_id"])
                if pid not in self._store.parameters:
                    raise RepoViolation("Parametro ID %s nao existe" % pid, constraint="fk_tbsss_sprm_prm")
                if pid in params_seen:
                    raise RepoViolation("Parametro duplicado no script", constraint="uk_tbsss_sprm_scr_prm")
                params_seen.add(pid)

                order = int(item["sort_order"])
                if order < 1:
                    raise RepoViolation("Ordem deve ser >= 1", constraint="ck_tbsss_sprm_sort_order")
                if order in orders_seen:
                    raise RepoViolation("Ordem duplicada no script", constraint="uk_tbsss_sprm_scr_ord")
                orders_seen.add(order)

                req = item.get("required", "Y")
                if req not in ("Y", "N"):
                    raise RepoViolation("obrigatorio deve ser 'Y' ou 'N'", constraint="ck_tbsss_sprm_req")

                new_links.append({
                    "script_id": script_id,
                    "parameter_id": pid,
                    "sort_order": order,
                    "required": req,
                    "default_value_override": item.get("default_value_override"),
                })

            self._regras_tipo_param(self._store.scripts[script_id]["param_type"],
                                    [v["parameter_id"] for v in new_links])

            previous = dict((v["parameter_id"], v) for v in self._vinculos_do_script(script_id))
            for k in [k for k, v in self._store.script_param.items() if v["script_id"] == script_id]:
                del self._store.script_param[k]
            changed = set(previous) != set(v["parameter_id"] for v in new_links)
            for nv in new_links:
                nid = self._store.next_id("tbsss_script_param")
                nv["id"] = nid
                old = previous.get(nv["parameter_id"])
                if old is None:
                    self._store.stamp_insert(nv, actor)
                else:
                    for field in ("created_at", "created_by", "updated_at", "updated_by"):
                        nv[field] = old.get(field)
                    if any(nv[c] != old.get(c) for c in ("sort_order", "required", "default_value_override")):
                        self._store.stamp_update(nv, actor)
                        changed = True
                self._store.script_param[nid] = nv
            if changed:
                self._store.stamp_update(self._store.scripts[script_id], actor)

            self._auditar_script(audit, script_id)
            return copy.deepcopy(self.script_params_get(script_id))

    # -------------------------------------------------------------------------
    # Scripts Executaveis (README §4.3.A)
    # -------------------------------------------------------------------------

    def executable_scripts(self, user_ctx):
        """Retorna lista filtrada de scripts que o usuario pode executar."""
        with self._store.lock_catalog:
            user_ctx = user_ctx or {}
            is_admin = user_ctx.get("is_admin") in ("Y", True)

            # Mapeamento de ambientes ativos
            environments_active_ids = {
                aid for aid, a in self._store.environments.items()
                if a["active"] == "Y"
            }
            environments_active_names = {
                a["name"] for aid, a in self._store.environments.items()
                if a["active"] == "Y"
            }

            # Scripts ativos
            scripts_candidates = [
                s for s in self._store.scripts.values()
                if s["active"] == "Y"
            ]

            if is_admin:
                # Admin dispensa dimensoes 1-3, mas exige homologacao em ambiente ativo
                executables = []
                for s in scripts_candidates:
                    envs_homologated = [
                        sa["environment_id"]
                        for sa in self._store.script_env.values()
                        if sa["script_id"] == s["id"] and sa["environment_id"] in environments_active_ids
                    ]
                    if envs_homologated:
                        executables.append(s)
                executables.sort(key=lambda x: (x.get("name", ""), x["id"]))
                return copy.deepcopy(executables)

            # Nao admin: requer funcionalidade EXEC_SCRIPT
            features = user_ctx.get("features") or set()
            if "EXEC_SCRIPT" not in features:
                return []

            envs_allowed = user_ctx.get("environments") or set()
            scrs_allowed = user_ctx.get("scripts") or set()

            executables = []
            for s in scripts_candidates:
                # Script autorizado na dimensao de perfil
                if s["id"] not in scrs_allowed and s["name"] not in scrs_allowed:
                    continue

                # Homologacao ativa e autorizada
                homologated_active = [
                    self._store.environments[sa["environment_id"]]
                    for sa in self._store.script_env.values()
                    if sa["script_id"] == s["id"] and sa["environment_id"] in environments_active_ids
                ]

                # Deve haver ao menos um ambiente homologado que esteja nos ambientes autorizados
                can_in_any = False
                for a in homologated_active:
                    if a["id"] in envs_allowed or a["name"] in envs_allowed:
                        can_in_any = True
                        break

                if can_in_any:
                    executables.append(s)

            executables.sort(key=lambda x: (x.get("name", ""), x["id"]))
            return copy.deepcopy(executables)
