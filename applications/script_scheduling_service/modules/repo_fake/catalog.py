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
            lista = list(self._store.environments.values())

            nome_f = filters.get("name")
            if nome_f:
                lista = [a for a in lista if nome_f.upper() in a["name"].upper()]

            ativo_f = filters.get("active")
            if ativo_f:
                lista = [a for a in lista if a["active"] == ativo_f]

            lista.sort(key=lambda x: (x.get("name", ""), x["id"]))
            return paginate(lista, page=page, size=size)

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

    def environments_insert(self, date, audit=None, actor=None):
        """Insere novo ambiente com validacao de CKs, UK e DSN, auditando na mesma operacao."""
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            nome = date.get("name")
            if not nome or not _RE_ENV_NAME.fullmatch(nome):
                raise RepoViolation("Nome de ambiente invalido (esperado: 1-30 chars [A-Z0-9_])", constraint="ck_tbsss_env_name")

            for a in self._store.environments.values():
                if a["name"].upper() == nome.upper():
                    raise RepoViolation("Ambiente com nome '%s' ja existe" % nome, constraint="uk_tbsss_env_name")

            conexao = date.get("connection")
            if conexao and "@" in conexao:
                raise RepoViolation("Conexao nao pode conter credencial (@)", constraint="ck_tbsss_env_connection")

            ativo = date.get("active", "Y")
            if ativo not in ("Y", "N"):
                raise RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_env_active")

            aid = self._store.next_id("tbsss_environments")
            novo = {
                "id": aid,
                "name": nome,
                "description": date.get("description", ""),
                "connection": conexao,
                "active": ativo,
                "created_at": date.get("created_at"),
            }
            self._store.stamp_insert(novo, actor)
            self._store.environments[aid] = copy.deepcopy(novo)
            self._auditar_ambiente(audit, aid)
            return copy.deepcopy(novo)

    def environments_update(self, id, date, expected=None, audit=None, actor=None):
        """Altera ambiente (nome imutavel, trigger tr_tbsss_env_bu), condicional a 'esperado'."""
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            if id not in self._store.environments:
                raise RepoNotFound("Ambiente ID %s nao encontrado" % id)

            atual = self._store.environments[id]
            for campo, valor in (expected or {}).items():
                if atual.get(campo) != valor:
                    raise RepoConflict("Ambiente ID %s alterado por outra operacao (%s)" % (id, campo))

            novo_nome = date.get("name")
            if novo_nome is not None and novo_nome != atual["name"]:
                raise RepoViolation("Nome de ambiente e imutavel", constraint="tr_tbsss_env_bu")

            mudancas = {}
            novo_conexao = date.get("connection")
            if novo_conexao is not None:
                if "@" in novo_conexao:
                    raise RepoViolation("Conexao nao pode conter credencial (@)", constraint="ck_tbsss_env_connection")
                mudancas["connection"] = novo_conexao
            elif "connection" in date:
                mudancas["connection"] = None

            if "description" in date:
                mudancas["description"] = date["description"]

            novo_ativo = date.get("active")
            if novo_ativo is not None:
                if novo_ativo not in ("Y", "N"):
                    raise RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_env_active")
                mudancas["active"] = novo_ativo

            # Validacao completa antes de aplicar: um UPDATE rejeitado nao altera nenhuma coluna.
            atual.update(mudancas)
            self._store.stamp_update(atual, actor)
            self._auditar_ambiente(audit, id)
            return copy.deepcopy(atual)

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
        lista = [sp for sp in self._store.script_param.values() if sp["script_id"] == script_id]
        lista.sort(key=lambda x: x["sort_order"])
        return lista

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
            lista = list(self._store.scripts.values())

            nome_f = filters.get("name")
            if nome_f:
                lista = [s for s in lista if nome_f.lower() in s["name"].lower()]
            for chave in ("script_group", "category", "interpreter", "active"):
                valor = filters.get(chave)
                if valor:
                    lista = [s for s in lista if s.get(chave) == valor]

            lista.sort(key=lambda x: (x.get("name", ""), x["id"]))
            pagina_ = paginate(lista, page=page, size=size)
            for item in pagina_["itens"]:
                item["ambientes_homologados"] = sorted(
                    self._store.environments[sa["environment_id"]]["name"] for sa in self._store.script_env.values()
                    if sa["script_id"] == item["id"] and sa["environment_id"] in self._store.environments)
                item["qtd_parametros"] = len(self._vinculos_do_script(item["id"]))
            return pagina_

    def scripts_get(self, id):
        """Retorna dict do script pelo ID ou lanca RepoNotFound."""
        with self._store.lock_catalog:
            if id not in self._store.scripts:
                raise RepoNotFound("Script ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.scripts[id])

    def _validar_script(self, date, current_value=None):
        """CKs da tabela 6 sobre o registro resultante (atual + dados); devolve as mudancas validadas."""
        base = dict(current_value or {}, **date)
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

    def scripts_insert(self, date, audit=None, actor=None):
        """Insere novo script com validacoes de seguranca e CKs, auditando na mesma operacao."""
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            self._validar_script(date)
            sid = self._store.next_id("tbsss_scripts")
            tmout = date.get("timeout_s")
            novo = {
                "id": sid,
                "name": date["name"],
                "description": date.get("description", ""),
                "script_group": date.get("script_group"),
                "category": date.get("category"),
                "stage": date.get("stage"),
                "interpreter": date["interpreter"],
                "path_file": date["path_file"],
                "param_type": date.get("param_type", "NAMED"),
                "max_parallel_env": int(date.get("max_parallel_env", 1)),
                "timeout_s": int(tmout) if tmout is not None else None,
                "active": date.get("active", "Y"),
            }
            self._store.stamp_insert(novo, actor)
            self._store.scripts[sid] = copy.deepcopy(novo)
            self._auditar_script(audit, sid)
            return copy.deepcopy(novo)

    def scripts_update(self, id, date, expected=None, audit=None, actor=None):
        """Altera script (CKs, esperado e regras de tipo_param x vinculos) na mesma operacao."""
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            if id not in self._store.scripts:
                raise RepoNotFound("Script ID %s nao encontrado" % id)
            atual = self._store.scripts[id]
            for campo, valor in (expected or {}).items():
                if atual.get(campo) != valor:
                    raise RepoConflict("Script ID %s alterado por outra operacao (%s)" % (id, campo))
            campos = ("name", "description", "script_group", "category", "stage", "interpreter", "path_file",
                      "param_type", "max_parallel_env", "timeout_s", "active")
            mudancas = dict((k, date[k]) for k in campos if k in date)
            self._validar_script(mudancas, atual)
            if "param_type" in mudancas and mudancas["param_type"] != atual["param_type"]:
                self._regras_tipo_param(mudancas["param_type"],
                                        [v["parameter_id"] for v in self._vinculos_do_script(id)])
            if "max_parallel_env" in mudancas:
                mudancas["max_parallel_env"] = int(mudancas["max_parallel_env"])
            if mudancas.get("timeout_s") is not None:
                mudancas["timeout_s"] = int(mudancas["timeout_s"])
            atual.update(mudancas)
            self._store.stamp_update(atual, actor)
            self._auditar_script(audit, id)
            return copy.deepcopy(atual)

    # -------------------------------------------------------------------------
    # Homologacao de Scripts por Ambiente (tbsss_script_env)
    # -------------------------------------------------------------------------

    def homologation_get(self, script_id):
        """Retorna lista de ambiente_id homologados para o script."""
        with self._store.lock_catalog:
            if script_id not in self._store.scripts:
                raise RepoNotFound("Script ID %s nao encontrado" % script_id)
            ambs = [
                sa["environment_id"]
                for sa in self._store.script_env.values()
                if sa["script_id"] == script_id
            ]
            ambs.sort()
            return copy.deepcopy(ambs)

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

            atuais = dict((v["environment_id"], k) for k, v in self._store.script_env.items()
                          if v["script_id"] == script_id)
            for aid, k in atuais.items():
                if aid not in ids:
                    del self._store.script_env[k]
            for aid in ids:
                if aid not in atuais:
                    nid = self._store.next_id("tbsss_script_env")
                    self._store.script_env[nid] = self._store.stamp_insert(
                        {"id": nid, "script_id": script_id, "environment_id": aid}, actor)
            if set(atuais) != set(ids):
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
            lista = list(self._store.parameters.values())

            cod_f = filters.get("code")
            if cod_f:
                lista = [p for p in lista if cod_f.lower() in p["code"].lower()]

            label_f = filters.get("label")
            if label_f:
                lista = [p for p in lista if label_f.lower() in p["label"].lower()]

            tipo_f = filters.get("component_type")
            if tipo_f:
                lista = [p for p in lista if p["component_type"] == tipo_f]

            ativo_f = filters.get("active")
            if ativo_f:
                lista = [p for p in lista if p["active"] == ativo_f]

            lista.sort(key=lambda x: (x.get("code", ""), x["id"]))
            pagina_ = paginate(lista, page=page, size=size)
            for item in pagina_["itens"]:
                item["qtd_scripts"] = sum(1 for sp in self._store.script_param.values()
                                          if sp["parameter_id"] == item["id"])
            return pagina_

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

    def parameters_insert(self, date, audit=None, actor=None):
        """Insere novo parametro validando CKs e UK, auditando na mesma operacao."""
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            codigo = date.get("code")
            if not codigo or not _RE_PRM_CODE.fullmatch(codigo):
                raise RepoViolation("Codigo de parametro invalido (esperado: 1-30 chars [a-z0-9_])", constraint="ck_tbsss_prm_code")

            for p in self._store.parameters.values():
                if p["code"] == codigo:
                    raise RepoViolation("Parametro com codigo '%s' ja existe" % codigo, constraint="uk_tbsss_prm_code")

            tcomp = date.get("component_type")
            if tcomp not in ("TEXT", "NUMBER", "DATE", "SELECT", "CHECKBOX"):
                raise RepoViolation("Tipo de componente invalido", constraint="ck_tbsss_prm_ctype")

            flag = date.get("param_flag")
            if flag is not None and flag != "":
                if not _RE_PRM_FLAG.fullmatch(flag):
                    raise RepoViolation("Flag param_nomeado invalida", constraint="ck_tbsss_prm_flag")
            else:
                flag = None

            sens = date.get("sensitive", "N")
            if sens not in ("Y", "N"):
                raise RepoViolation("sensivel deve ser 'Y' ou 'N'", constraint="ck_tbsss_prm_sens")

            ativo = date.get("active", "Y")
            if ativo not in ("Y", "N"):
                raise RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_prm_active")

            pid = self._store.next_id("tbsss_parameters")
            novo = {
                "id": pid,
                "code": codigo,
                "param_flag": flag,
                "label": date.get("label", ""),
                "description": date.get("description", ""),
                "component_type": tcomp,
                "options_json": date.get("options_json"),
                "default_value": date.get("default_value"),
                "validation_regex": date.get("validation_regex"),
                "sensitive": sens,
                "active": ativo,
            }
            self._store.stamp_insert(novo, actor)
            self._store.parameters[pid] = copy.deepcopy(novo)
            self._auditar_parametro(audit, pid)
            return copy.deepcopy(novo)

    def parameters_update(self, id, date, expected=None, audit=None, actor=None):
        """Altera parametro (CKs, dependencias de vinculo e 'esperado') na mesma operacao."""
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            if id not in self._store.parameters:
                raise RepoNotFound("Parametro ID %s nao encontrado" % id)

            atual = self._store.parameters[id]
            for campo, valor in (expected or {}).items():
                if atual.get(campo) != valor:
                    raise RepoConflict("Parametro ID %s alterado por outra operacao (%s)" % (id, campo))

            mudancas = dict((k, date[k]) for k in ("label", "description", "options_json", "default_value",
                                                    "validation_regex") if k in date)
            if "param_flag" in date:
                flag = date["param_flag"] or None
                if flag is not None and not _RE_PRM_FLAG.fullmatch(flag):
                    raise RepoViolation("Flag param_nomeado invalida", constraint="ck_tbsss_prm_flag")
                mudancas["param_flag"] = flag
            if "component_type" in date:
                if date["component_type"] not in ("TEXT", "NUMBER", "DATE", "SELECT", "CHECKBOX"):
                    raise RepoViolation("Tipo de componente invalido", constraint="ck_tbsss_prm_ctype")
                mudancas["component_type"] = date["component_type"]
            for campo, ck in (("sensitive", "ck_tbsss_prm_sens"), ("active", "ck_tbsss_prm_active")):
                if campo in date:
                    if date[campo] not in ("Y", "N"):
                        raise RepoViolation("Flag %s deve ser 'Y' ou 'N'" % campo, constraint=ck)
                    mudancas[campo] = date[campo]

            # Regras de dependencia (README §10) avaliadas sob o mesmo lock da alteracao.
            scripts = [self._store.scripts[sp["script_id"]] for sp in self._store.script_param.values()
                       if sp["parameter_id"] == id and sp["script_id"] in self._store.scripts]
            if scripts and mudancas.get("component_type", atual["component_type"]) != atual["component_type"]:
                raise RepoViolation("Tipo de componente com vinculos", constraint="sss_prm_tipo_vinculado")
            if "param_flag" in mudancas and mudancas["param_flag"] != atual["param_flag"] \
                    and any(s.get("param_type") == "NAMED" for s in scripts):
                raise RepoViolation("Flag com vinculo NOMEADO", constraint="sss_prm_flag_nomeado")
            if mudancas.get("active") == "N" and atual["active"] == "Y" and any(s.get("active") == "Y" for s in scripts):
                raise RepoViolation("Desativacao com vinculo a script ativo", constraint="sss_prm_vinculo_ativo")

            atual.update(mudancas)
            self._store.stamp_update(atual, actor)
            self._auditar_parametro(audit, id)
            return copy.deepcopy(atual)

    def parameter_links(self, parameter_id):
        """Retorna lista de scripts vinculados ao parametro para verificacao de desativacao."""
        with self._store.lock_catalog:
            script_ids = {
                sp["script_id"]
                for sp in self._store.script_param.values()
                if sp["parameter_id"] == parameter_id
            }
            resultado = [
                s for sid, s in self._store.scripts.items()
                if sid in script_ids
            ]
            resultado.sort(key=lambda x: (x.get("name", ""), x["id"]))
            return copy.deepcopy(resultado)

    # -------------------------------------------------------------------------
    # Vinculos de Parametros em Scripts (tbsss_script_param)
    # -------------------------------------------------------------------------

    def script_params_get(self, script_id):
        """Retorna lista de parametros vinculados ao script ordenados por ordem."""
        with self._store.lock_catalog:
            if script_id not in self._store.scripts:
                raise RepoNotFound("Script ID %s nao encontrado" % script_id)

            vinculos = [
                sp for sp in self._store.script_param.values()
                if sp["script_id"] == script_id
            ]
            vinculos.sort(key=lambda x: x["sort_order"])

            resultado = []
            for v in vinculos:
                param = self._store.parameters.get(v["parameter_id"])
                if param:
                    item = copy.deepcopy(param)
                    item["script_id"] = script_id
                    item["parameter_id"] = param["id"]
                    item["sort_order"] = v["sort_order"]
                    item["required"] = v["required"]
                    item["default_value_override"] = v.get("default_value_override")
                    resultado.append(item)
            return copy.deepcopy(resultado)

    def script_params_save(self, script_id, links, expected=None, audit=None, actor=None):
        """Substitui os vinculos do script (UKs, FK, regras de tipo_param, esperado e auditoria).

        Apaga e reinsere (UK script_id + ordem), mas cada parametro que continua leva o created_*;
        o updated_* do vinculo so muda se ordem, obrigatorio ou valor_padrao_sub mudar (CR-006).
        """
        with self._store.lock_catalog:
            actor = self._store.record_actor(audit, actor)
            if script_id not in self._store.scripts:
                raise RepoNotFound("Script ID %s nao encontrado" % script_id)
            if expected is not None:
                lidos = [(v["parameter_id"], v["sort_order"], v["required"], v.get("default_value_override"))
                         for v in self._vinculos_do_script(script_id)]
                if [tuple(e) for e in expected] != lidos:
                    raise RepoConflict("Vinculos do script ID %s alterados por outra operacao" % script_id)

            params_vistos = set()
            ordens_vistas = set()
            novos_vinculos = []
            for item in (links or []):
                pid = int(item["parameter_id"])
                if pid not in self._store.parameters:
                    raise RepoViolation("Parametro ID %s nao existe" % pid, constraint="fk_tbsss_sprm_prm")
                if pid in params_vistos:
                    raise RepoViolation("Parametro duplicado no script", constraint="uk_tbsss_sprm_scr_prm")
                params_vistos.add(pid)

                ordem = int(item["sort_order"])
                if ordem < 1:
                    raise RepoViolation("Ordem deve ser >= 1", constraint="ck_tbsss_sprm_sort_order")
                if ordem in ordens_vistas:
                    raise RepoViolation("Ordem duplicada no script", constraint="uk_tbsss_sprm_scr_ord")
                ordens_vistas.add(ordem)

                obrig = item.get("required", "Y")
                if obrig not in ("Y", "N"):
                    raise RepoViolation("obrigatorio deve ser 'Y' ou 'N'", constraint="ck_tbsss_sprm_req")

                novos_vinculos.append({
                    "script_id": script_id,
                    "parameter_id": pid,
                    "sort_order": ordem,
                    "required": obrig,
                    "default_value_override": item.get("default_value_override"),
                })

            self._regras_tipo_param(self._store.scripts[script_id]["param_type"],
                                    [v["parameter_id"] for v in novos_vinculos])

            anteriores = dict((v["parameter_id"], v) for v in self._vinculos_do_script(script_id))
            for k in [k for k, v in self._store.script_param.items() if v["script_id"] == script_id]:
                del self._store.script_param[k]
            mudou = set(anteriores) != set(v["parameter_id"] for v in novos_vinculos)
            for nv in novos_vinculos:
                nid = self._store.next_id("tbsss_script_param")
                nv["id"] = nid
                velho = anteriores.get(nv["parameter_id"])
                if velho is None:
                    self._store.stamp_insert(nv, actor)
                else:
                    for campo in ("created_at", "created_by", "updated_at", "updated_by"):
                        nv[campo] = velho.get(campo)
                    if any(nv[c] != velho.get(c) for c in ("sort_order", "required", "default_value_override")):
                        self._store.stamp_update(nv, actor)
                        mudou = True
                self._store.script_param[nid] = nv
            if mudou:
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
            ambientes_ativos_ids = {
                aid for aid, a in self._store.environments.items()
                if a["active"] == "Y"
            }
            ambientes_ativos_nomes = {
                a["name"] for aid, a in self._store.environments.items()
                if a["active"] == "Y"
            }

            # Scripts ativos
            scripts_candidatos = [
                s for s in self._store.scripts.values()
                if s["active"] == "Y"
            ]

            if is_admin:
                # Admin dispensa dimensoes 1-3, mas exige homologacao em ambiente ativo
                executaveis = []
                for s in scripts_candidatos:
                    ambs_homologados = [
                        sa["environment_id"]
                        for sa in self._store.script_env.values()
                        if sa["script_id"] == s["id"] and sa["environment_id"] in ambientes_ativos_ids
                    ]
                    if ambs_homologados:
                        executaveis.append(s)
                executaveis.sort(key=lambda x: (x.get("name", ""), x["id"]))
                return copy.deepcopy(executaveis)

            # Nao admin: requer funcionalidade EXEC_SCRIPT
            funcs = user_ctx.get("features") or set()
            if "EXEC_SCRIPT" not in funcs:
                return []

            ambs_permitidos = user_ctx.get("environments") or set()
            scrs_permitidos = user_ctx.get("scripts") or set()

            executaveis = []
            for s in scripts_candidatos:
                # Script autorizado na dimensao de perfil
                if s["id"] not in scrs_permitidos and s["name"] not in scrs_permitidos:
                    continue

                # Homologacao ativa e autorizada
                homologados_ativos = [
                    self._store.environments[sa["environment_id"]]
                    for sa in self._store.script_env.values()
                    if sa["script_id"] == s["id"] and sa["environment_id"] in ambientes_ativos_ids
                ]

                # Deve haver ao menos um ambiente homologado que esteja nos ambientes autorizados
                pode_em_algum = False
                for a in homologados_ativos:
                    if a["id"] in ambs_permitidos or a["name"] in ambs_permitidos:
                        pode_em_algum = True
                        break

                if pode_em_algum:
                    executaveis.append(s)

            executaveis.sort(key=lambda x: (x.get("name", ""), x["id"]))
            return copy.deepcopy(executaveis)
