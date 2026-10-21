# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de catalogo (README §2.5, §4.3.A, §6.3, §10)."""
import copy
import re

from repo_catalog import RepoCatalogo
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao
from repo_fake.store import paginar

_RE_AMB_NOME = re.compile(r"^[A-Z0-9_]{1,30}$")
_RE_PRM_CODIGO = re.compile(r"^[a-z0-9_]{1,30}$")
_RE_PRM_FLAG = re.compile(r"^-{1,2}[A-Za-z0-9][A-Za-z0-9_-]{0,27}$")


class RepoCatalogoFake(RepoCatalogo):
    """Implementacao em memoria com semantica Oracle para o catalogo."""

    def __init__(self, store):
        self._store = store

    # -------------------------------------------------------------------------
    # Ambientes (tbsss_environments)
    # -------------------------------------------------------------------------

    def ambientes_listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista ambientes com paginacao deterministica por nome ASC, id ASC."""
        filtros = filtros or {}
        with self._store.lock_catalogo:
            lista = list(self._store.ambientes.values())

            nome_f = filtros.get("name")
            if nome_f:
                lista = [a for a in lista if nome_f.upper() in a["name"].upper()]

            ativo_f = filtros.get("active")
            if ativo_f:
                lista = [a for a in lista if a["active"] == ativo_f]

            lista.sort(key=lambda x: (x.get("name", ""), x["id"]))
            return paginar(lista, pagina=pagina, tamanho=tamanho)

    def ambientes_obter(self, id):
        """Retorna dict do ambiente pelo ID ou lanca RepoNaoEncontrado."""
        with self._store.lock_catalogo:
            if id not in self._store.ambientes:
                raise RepoNaoEncontrado("Ambiente ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.ambientes[id])

    def _auditar_ambiente(self, auditoria, ambiente_id):
        if auditoria:
            self._store.registrar_auditoria_interno(
                ator=auditoria.get("actor"),
                ip=auditoria.get("ip"),
                acao=auditoria["action"],
                entidade="tbsss_environments",
                entidade_id=ambiente_id,
                detalhe=auditoria.get("detail"),
            )

    def ambientes_inserir(self, dados, auditoria=None, ator=None):
        """Insere novo ambiente com validacao de CKs, UK e DSN, auditando na mesma operacao."""
        with self._store.lock_catalogo:
            ator = self._store.ator_registro(auditoria, ator)
            nome = dados.get("name")
            if not nome or not _RE_AMB_NOME.fullmatch(nome):
                raise RepoViolacao("Nome de ambiente invalido (esperado: 1-30 chars [A-Z0-9_])", constraint="ck_tbsss_env_name")

            for a in self._store.ambientes.values():
                if a["name"].upper() == nome.upper():
                    raise RepoViolacao("Ambiente com nome '%s' ja existe" % nome, constraint="uk_tbsss_env_name")

            conexao = dados.get("connection")
            if conexao and "@" in conexao:
                raise RepoViolacao("Conexao nao pode conter credencial (@)", constraint="ck_tbsss_env_connection")

            ativo = dados.get("active", "Y")
            if ativo not in ("Y", "N"):
                raise RepoViolacao("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_env_active")

            aid = self._store.proximo_id("tbsss_environments")
            novo = {
                "id": aid,
                "name": nome,
                "description": dados.get("description", ""),
                "connection": conexao,
                "active": ativo,
                "created_at": dados.get("created_at"),
            }
            self._store.carimbar_inclusao(novo, ator)
            self._store.ambientes[aid] = copy.deepcopy(novo)
            self._auditar_ambiente(auditoria, aid)
            return copy.deepcopy(novo)

    def ambientes_alterar(self, id, dados, esperado=None, auditoria=None, ator=None):
        """Altera ambiente (nome imutavel, trigger tr_tbsss_env_bu), condicional a 'esperado'."""
        with self._store.lock_catalogo:
            ator = self._store.ator_registro(auditoria, ator)
            if id not in self._store.ambientes:
                raise RepoNaoEncontrado("Ambiente ID %s nao encontrado" % id)

            atual = self._store.ambientes[id]
            for campo, valor in (esperado or {}).items():
                if atual.get(campo) != valor:
                    raise RepoConflito("Ambiente ID %s alterado por outra operacao (%s)" % (id, campo))

            novo_nome = dados.get("name")
            if novo_nome is not None and novo_nome != atual["name"]:
                raise RepoViolacao("Nome de ambiente e imutavel", constraint="tr_tbsss_env_bu")

            mudancas = {}
            novo_conexao = dados.get("connection")
            if novo_conexao is not None:
                if "@" in novo_conexao:
                    raise RepoViolacao("Conexao nao pode conter credencial (@)", constraint="ck_tbsss_env_connection")
                mudancas["connection"] = novo_conexao
            elif "connection" in dados:
                mudancas["connection"] = None

            if "description" in dados:
                mudancas["description"] = dados["description"]

            novo_ativo = dados.get("active")
            if novo_ativo is not None:
                if novo_ativo not in ("Y", "N"):
                    raise RepoViolacao("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_env_active")
                mudancas["active"] = novo_ativo

            # Validacao completa antes de aplicar: um UPDATE rejeitado nao altera nenhuma coluna.
            atual.update(mudancas)
            self._store.carimbar_alteracao(atual, ator)
            self._auditar_ambiente(auditoria, id)
            return copy.deepcopy(atual)

    # -------------------------------------------------------------------------
    # Scripts (tbsss_scripts)
    # -------------------------------------------------------------------------

    def _auditar_script(self, auditoria, script_id):
        if auditoria:
            self._store.registrar_auditoria_interno(
                ator=auditoria.get("actor"),
                ip=auditoria.get("ip"),
                acao=auditoria["action"],
                entidade="tbsss_scripts",
                entidade_id=script_id,
                detalhe=auditoria.get("detail"),
            )

    def _vinculos_do_script(self, script_id):
        lista = [sp for sp in self._store.script_param.values() if sp["script_id"] == script_id]
        lista.sort(key=lambda x: x["sort_order"])
        return lista

    def _regras_tipo_param(self, tipo_param, parametro_ids):
        # README §6.3: NENHUM nao aceita vinculos; NOMEADO exige flag em todo parametro vinculado.
        if tipo_param == "NONE" and parametro_ids:
            raise RepoViolacao("Script NENHUM com vinculos", constraint="sss_scr_nenhum_vinculado")
        if tipo_param == "NAMED":
            for pid in parametro_ids:
                if not self._store.parametros[pid].get("param_flag"):
                    raise RepoViolacao("Parametro sem flag em script NOMEADO", constraint="sss_scr_nomeado_sem_flag")

    def scripts_listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista scripts com paginacao deterministica por nome ASC, id ASC, homologacoes e qtd de parametros."""
        filtros = filtros or {}
        with self._store.lock_catalogo:
            lista = list(self._store.scripts.values())

            nome_f = filtros.get("name")
            if nome_f:
                lista = [s for s in lista if nome_f.lower() in s["name"].lower()]
            for chave in ("script_group", "category", "interpreter", "active"):
                valor = filtros.get(chave)
                if valor:
                    lista = [s for s in lista if s.get(chave) == valor]

            lista.sort(key=lambda x: (x.get("name", ""), x["id"]))
            pagina_ = paginar(lista, pagina=pagina, tamanho=tamanho)
            for item in pagina_["itens"]:
                item["ambientes_homologados"] = sorted(
                    self._store.ambientes[sa["environment_id"]]["name"] for sa in self._store.script_amb.values()
                    if sa["script_id"] == item["id"] and sa["environment_id"] in self._store.ambientes)
                item["qtd_parametros"] = len(self._vinculos_do_script(item["id"]))
            return pagina_

    def scripts_obter(self, id):
        """Retorna dict do script pelo ID ou lanca RepoNaoEncontrado."""
        with self._store.lock_catalogo:
            if id not in self._store.scripts:
                raise RepoNaoEncontrado("Script ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.scripts[id])

    def _validar_script(self, dados, atual=None):
        """CKs da tabela 6 sobre o registro resultante (atual + dados); devolve as mudancas validadas."""
        base = dict(atual or {}, **dados)
        if not base.get("name"):
            raise RepoViolacao("Nome de script e obrigatorio")
        if base.get("param_type", "NAMED") not in ("NAMED", "POSITIONAL", "NONE"):
            raise RepoViolacao("Tipo de parametro invalido", constraint="ck_tbsss_scr_ptype")
        if base.get("active", "Y") not in ("Y", "N"):
            raise RepoViolacao("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_scr_active")
        if base.get("interpreter") not in ("PYTHON3", "BASH", "SH"):
            raise RepoViolacao("Interpretador fora da allowlist", constraint="ck_tbsss_scr_int")
        pfile = base.get("path_file") or ""
        # ck_tbsss_scr_path (README §10, CR-005): absoluto, sem '..', '//' nem '\\'; ate 500 caracteres.
        if (not pfile.startswith("/") or ".." in pfile or "//" in pfile or "\\" in pfile
                or len(pfile) > 500):
            raise RepoViolacao("path_file deve ser absoluto e sem '..'", constraint="ck_tbsss_scr_path")
        if not (1 <= int(base.get("max_parallel_env", 1)) <= 999):
            raise RepoViolacao("max_qtd_parallel_env deve estar entre 1 e 999", constraint="ck_tbsss_scr_paral")
        tmout = base.get("timeout_s")
        if tmout is not None and int(tmout) <= 0:
            raise RepoViolacao("timeout_seg deve ser maior que zero", constraint="ck_tbsss_scr_tmout")
        for sid, s in self._store.scripts.items():
            # UK do Oracle diferencia maiusculas (README §8.5): 'Carga' e 'carga' sao nomes distintos.
            if (atual is None or sid != atual["id"]) and s["name"] == base["name"]:
                raise RepoViolacao("Script com nome '%s' ja existe" % base["name"], constraint="uk_tbsss_scr_name")

    def scripts_inserir(self, dados, auditoria=None, ator=None):
        """Insere novo script com validacoes de seguranca e CKs, auditando na mesma operacao."""
        with self._store.lock_catalogo:
            ator = self._store.ator_registro(auditoria, ator)
            self._validar_script(dados)
            sid = self._store.proximo_id("tbsss_scripts")
            tmout = dados.get("timeout_s")
            novo = {
                "id": sid,
                "name": dados["name"],
                "description": dados.get("description", ""),
                "script_group": dados.get("script_group"),
                "category": dados.get("category"),
                "stage": dados.get("stage"),
                "interpreter": dados["interpreter"],
                "path_file": dados["path_file"],
                "param_type": dados.get("param_type", "NAMED"),
                "max_parallel_env": int(dados.get("max_parallel_env", 1)),
                "timeout_s": int(tmout) if tmout is not None else None,
                "active": dados.get("active", "Y"),
            }
            self._store.carimbar_inclusao(novo, ator)
            self._store.scripts[sid] = copy.deepcopy(novo)
            self._auditar_script(auditoria, sid)
            return copy.deepcopy(novo)

    def scripts_alterar(self, id, dados, esperado=None, auditoria=None, ator=None):
        """Altera script (CKs, esperado e regras de tipo_param x vinculos) na mesma operacao."""
        with self._store.lock_catalogo:
            ator = self._store.ator_registro(auditoria, ator)
            if id not in self._store.scripts:
                raise RepoNaoEncontrado("Script ID %s nao encontrado" % id)
            atual = self._store.scripts[id]
            for campo, valor in (esperado or {}).items():
                if atual.get(campo) != valor:
                    raise RepoConflito("Script ID %s alterado por outra operacao (%s)" % (id, campo))
            campos = ("name", "description", "script_group", "category", "stage", "interpreter", "path_file",
                      "param_type", "max_parallel_env", "timeout_s", "active")
            mudancas = dict((k, dados[k]) for k in campos if k in dados)
            self._validar_script(mudancas, atual)
            if "param_type" in mudancas and mudancas["param_type"] != atual["param_type"]:
                self._regras_tipo_param(mudancas["param_type"],
                                        [v["parameter_id"] for v in self._vinculos_do_script(id)])
            if "max_parallel_env" in mudancas:
                mudancas["max_parallel_env"] = int(mudancas["max_parallel_env"])
            if mudancas.get("timeout_s") is not None:
                mudancas["timeout_s"] = int(mudancas["timeout_s"])
            atual.update(mudancas)
            self._store.carimbar_alteracao(atual, ator)
            self._auditar_script(auditoria, id)
            return copy.deepcopy(atual)

    # -------------------------------------------------------------------------
    # Homologacao de Scripts por Ambiente (tbsss_script_env)
    # -------------------------------------------------------------------------

    def homologacao_obter(self, script_id):
        """Retorna lista de ambiente_id homologados para o script."""
        with self._store.lock_catalogo:
            if script_id not in self._store.scripts:
                raise RepoNaoEncontrado("Script ID %s nao encontrado" % script_id)
            ambs = [
                sa["environment_id"]
                for sa in self._store.script_amb.values()
                if sa["script_id"] == script_id
            ]
            ambs.sort()
            return copy.deepcopy(ambs)

    def homologacao_salvar(self, script_id, ambiente_ids, esperado=None, auditoria=None, ator=None):
        """Substitui homologacoes do script por diferenca (FK, esperado e auditoria na mesma operacao).

        Os vinculos que continuam mantem o created_*; havendo mudanca, o script recebe updated_* (CR-006).
        """
        with self._store.lock_catalogo:
            ator = self._store.ator_registro(auditoria, ator)
            if script_id not in self._store.scripts:
                raise RepoNaoEncontrado("Script ID %s nao encontrado" % script_id)
            if esperado is not None and sorted(int(x) for x in esperado) != self.homologacao_obter(script_id):
                raise RepoConflito("Homologacao do script ID %s alterada por outra operacao" % script_id)

            ids = sorted(set(int(x) for x in (ambiente_ids or [])))
            for aid in ids:
                if aid not in self._store.ambientes:
                    raise RepoViolacao("Ambiente ID %s nao existe" % aid, constraint="fk_tbsss_senv_env")

            atuais = dict((v["environment_id"], k) for k, v in self._store.script_amb.items()
                          if v["script_id"] == script_id)
            for aid, k in atuais.items():
                if aid not in ids:
                    del self._store.script_amb[k]
            for aid in ids:
                if aid not in atuais:
                    nid = self._store.proximo_id("tbsss_script_env")
                    self._store.script_amb[nid] = self._store.carimbar_inclusao(
                        {"id": nid, "script_id": script_id, "environment_id": aid}, ator)
            if set(atuais) != set(ids):
                self._store.carimbar_alteracao(self._store.scripts[script_id], ator)

            self._auditar_script(auditoria, script_id)
            return copy.deepcopy(self.homologacao_obter(script_id))

    # -------------------------------------------------------------------------
    # Parametros (tbsss_parameters)
    # -------------------------------------------------------------------------

    def parametros_listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista parametros com paginacao deterministica por codigo ASC, id ASC."""
        filtros = filtros or {}
        with self._store.lock_catalogo:
            lista = list(self._store.parametros.values())

            cod_f = filtros.get("code")
            if cod_f:
                lista = [p for p in lista if cod_f.lower() in p["code"].lower()]

            label_f = filtros.get("label")
            if label_f:
                lista = [p for p in lista if label_f.lower() in p["label"].lower()]

            tipo_f = filtros.get("component_type")
            if tipo_f:
                lista = [p for p in lista if p["component_type"] == tipo_f]

            ativo_f = filtros.get("active")
            if ativo_f:
                lista = [p for p in lista if p["active"] == ativo_f]

            lista.sort(key=lambda x: (x.get("code", ""), x["id"]))
            pagina_ = paginar(lista, pagina=pagina, tamanho=tamanho)
            for item in pagina_["itens"]:
                item["qtd_scripts"] = sum(1 for sp in self._store.script_param.values()
                                          if sp["parameter_id"] == item["id"])
            return pagina_

    def parametros_obter(self, id):
        """Retorna dict do parametro pelo ID ou lanca RepoNaoEncontrado."""
        with self._store.lock_catalogo:
            if id not in self._store.parametros:
                raise RepoNaoEncontrado("Parametro ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.parametros[id])

    def _auditar_parametro(self, auditoria, parametro_id):
        if auditoria:
            self._store.registrar_auditoria_interno(
                ator=auditoria.get("actor"),
                ip=auditoria.get("ip"),
                acao=auditoria["action"],
                entidade="tbsss_parameters",
                entidade_id=parametro_id,
                detalhe=auditoria.get("detail"),
            )

    def parametros_inserir(self, dados, auditoria=None, ator=None):
        """Insere novo parametro validando CKs e UK, auditando na mesma operacao."""
        with self._store.lock_catalogo:
            ator = self._store.ator_registro(auditoria, ator)
            codigo = dados.get("code")
            if not codigo or not _RE_PRM_CODIGO.fullmatch(codigo):
                raise RepoViolacao("Codigo de parametro invalido (esperado: 1-30 chars [a-z0-9_])", constraint="ck_tbsss_prm_code")

            for p in self._store.parametros.values():
                if p["code"] == codigo:
                    raise RepoViolacao("Parametro com codigo '%s' ja existe" % codigo, constraint="uk_tbsss_prm_code")

            tcomp = dados.get("component_type")
            if tcomp not in ("TEXT", "NUMBER", "DATE", "SELECT", "CHECKBOX"):
                raise RepoViolacao("Tipo de componente invalido", constraint="ck_tbsss_prm_ctype")

            flag = dados.get("param_flag")
            if flag is not None and flag != "":
                if not _RE_PRM_FLAG.fullmatch(flag):
                    raise RepoViolacao("Flag param_nomeado invalida", constraint="ck_tbsss_prm_flag")
            else:
                flag = None

            sens = dados.get("sensitive", "N")
            if sens not in ("Y", "N"):
                raise RepoViolacao("sensivel deve ser 'Y' ou 'N'", constraint="ck_tbsss_prm_sens")

            ativo = dados.get("active", "Y")
            if ativo not in ("Y", "N"):
                raise RepoViolacao("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_prm_active")

            pid = self._store.proximo_id("tbsss_parameters")
            novo = {
                "id": pid,
                "code": codigo,
                "param_flag": flag,
                "label": dados.get("label", ""),
                "description": dados.get("description", ""),
                "component_type": tcomp,
                "options_json": dados.get("options_json"),
                "default_value": dados.get("default_value"),
                "validation_regex": dados.get("validation_regex"),
                "sensitive": sens,
                "active": ativo,
            }
            self._store.carimbar_inclusao(novo, ator)
            self._store.parametros[pid] = copy.deepcopy(novo)
            self._auditar_parametro(auditoria, pid)
            return copy.deepcopy(novo)

    def parametros_alterar(self, id, dados, esperado=None, auditoria=None, ator=None):
        """Altera parametro (CKs, dependencias de vinculo e 'esperado') na mesma operacao."""
        with self._store.lock_catalogo:
            ator = self._store.ator_registro(auditoria, ator)
            if id not in self._store.parametros:
                raise RepoNaoEncontrado("Parametro ID %s nao encontrado" % id)

            atual = self._store.parametros[id]
            for campo, valor in (esperado or {}).items():
                if atual.get(campo) != valor:
                    raise RepoConflito("Parametro ID %s alterado por outra operacao (%s)" % (id, campo))

            mudancas = dict((k, dados[k]) for k in ("label", "description", "options_json", "default_value",
                                                    "validation_regex") if k in dados)
            if "param_flag" in dados:
                flag = dados["param_flag"] or None
                if flag is not None and not _RE_PRM_FLAG.fullmatch(flag):
                    raise RepoViolacao("Flag param_nomeado invalida", constraint="ck_tbsss_prm_flag")
                mudancas["param_flag"] = flag
            if "component_type" in dados:
                if dados["component_type"] not in ("TEXT", "NUMBER", "DATE", "SELECT", "CHECKBOX"):
                    raise RepoViolacao("Tipo de componente invalido", constraint="ck_tbsss_prm_ctype")
                mudancas["component_type"] = dados["component_type"]
            for campo, ck in (("sensitive", "ck_tbsss_prm_sens"), ("active", "ck_tbsss_prm_active")):
                if campo in dados:
                    if dados[campo] not in ("Y", "N"):
                        raise RepoViolacao("Flag %s deve ser 'Y' ou 'N'" % campo, constraint=ck)
                    mudancas[campo] = dados[campo]

            # Regras de dependencia (README §10) avaliadas sob o mesmo lock da alteracao.
            scripts = [self._store.scripts[sp["script_id"]] for sp in self._store.script_param.values()
                       if sp["parameter_id"] == id and sp["script_id"] in self._store.scripts]
            if scripts and mudancas.get("component_type", atual["component_type"]) != atual["component_type"]:
                raise RepoViolacao("Tipo de componente com vinculos", constraint="sss_prm_tipo_vinculado")
            if "param_flag" in mudancas and mudancas["param_flag"] != atual["param_flag"] \
                    and any(s.get("param_type") == "NAMED" for s in scripts):
                raise RepoViolacao("Flag com vinculo NOMEADO", constraint="sss_prm_flag_nomeado")
            if mudancas.get("active") == "N" and atual["active"] == "Y" and any(s.get("active") == "Y" for s in scripts):
                raise RepoViolacao("Desativacao com vinculo a script ativo", constraint="sss_prm_vinculo_ativo")

            atual.update(mudancas)
            self._store.carimbar_alteracao(atual, ator)
            self._auditar_parametro(auditoria, id)
            return copy.deepcopy(atual)

    def parametro_vinculos(self, parametro_id):
        """Retorna lista de scripts vinculados ao parametro para verificacao de desativacao."""
        with self._store.lock_catalogo:
            script_ids = {
                sp["script_id"]
                for sp in self._store.script_param.values()
                if sp["parameter_id"] == parametro_id
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

    def script_params_obter(self, script_id):
        """Retorna lista de parametros vinculados ao script ordenados por ordem."""
        with self._store.lock_catalogo:
            if script_id not in self._store.scripts:
                raise RepoNaoEncontrado("Script ID %s nao encontrado" % script_id)

            vinculos = [
                sp for sp in self._store.script_param.values()
                if sp["script_id"] == script_id
            ]
            vinculos.sort(key=lambda x: x["sort_order"])

            resultado = []
            for v in vinculos:
                param = self._store.parametros.get(v["parameter_id"])
                if param:
                    item = copy.deepcopy(param)
                    item["script_id"] = script_id
                    item["parameter_id"] = param["id"]
                    item["sort_order"] = v["sort_order"]
                    item["required"] = v["required"]
                    item["default_value_override"] = v.get("default_value_override")
                    resultado.append(item)
            return copy.deepcopy(resultado)

    def script_params_salvar(self, script_id, vinculos, esperado=None, auditoria=None, ator=None):
        """Substitui os vinculos do script (UKs, FK, regras de tipo_param, esperado e auditoria).

        Apaga e reinsere (UK script_id + ordem), mas cada parametro que continua leva o created_*;
        o updated_* do vinculo so muda se ordem, obrigatorio ou valor_padrao_sub mudar (CR-006).
        """
        with self._store.lock_catalogo:
            ator = self._store.ator_registro(auditoria, ator)
            if script_id not in self._store.scripts:
                raise RepoNaoEncontrado("Script ID %s nao encontrado" % script_id)
            if esperado is not None:
                lidos = [(v["parameter_id"], v["sort_order"], v["required"], v.get("default_value_override"))
                         for v in self._vinculos_do_script(script_id)]
                if [tuple(e) for e in esperado] != lidos:
                    raise RepoConflito("Vinculos do script ID %s alterados por outra operacao" % script_id)

            params_vistos = set()
            ordens_vistas = set()
            novos_vinculos = []
            for item in (vinculos or []):
                pid = int(item["parameter_id"])
                if pid not in self._store.parametros:
                    raise RepoViolacao("Parametro ID %s nao existe" % pid, constraint="fk_tbsss_sprm_prm")
                if pid in params_vistos:
                    raise RepoViolacao("Parametro duplicado no script", constraint="uk_tbsss_sprm_scr_prm")
                params_vistos.add(pid)

                ordem = int(item["sort_order"])
                if ordem < 1:
                    raise RepoViolacao("Ordem deve ser >= 1", constraint="ck_tbsss_sprm_sort_order")
                if ordem in ordens_vistas:
                    raise RepoViolacao("Ordem duplicada no script", constraint="uk_tbsss_sprm_scr_ord")
                ordens_vistas.add(ordem)

                obrig = item.get("required", "Y")
                if obrig not in ("Y", "N"):
                    raise RepoViolacao("obrigatorio deve ser 'Y' ou 'N'", constraint="ck_tbsss_sprm_req")

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
                nid = self._store.proximo_id("tbsss_script_param")
                nv["id"] = nid
                velho = anteriores.get(nv["parameter_id"])
                if velho is None:
                    self._store.carimbar_inclusao(nv, ator)
                else:
                    for campo in ("created_at", "created_by", "updated_at", "updated_by"):
                        nv[campo] = velho.get(campo)
                    if any(nv[c] != velho.get(c) for c in ("sort_order", "required", "default_value_override")):
                        self._store.carimbar_alteracao(nv, ator)
                        mudou = True
                self._store.script_param[nid] = nv
            if mudou:
                self._store.carimbar_alteracao(self._store.scripts[script_id], ator)

            self._auditar_script(auditoria, script_id)
            return copy.deepcopy(self.script_params_obter(script_id))

    # -------------------------------------------------------------------------
    # Scripts Executaveis (README §4.3.A)
    # -------------------------------------------------------------------------

    def scripts_executaveis(self, usuario_ctx):
        """Retorna lista filtrada de scripts que o usuario pode executar."""
        with self._store.lock_catalogo:
            usuario_ctx = usuario_ctx or {}
            is_admin = usuario_ctx.get("is_admin") in ("Y", True)

            # Mapeamento de ambientes ativos
            ambientes_ativos_ids = {
                aid for aid, a in self._store.ambientes.items()
                if a["active"] == "Y"
            }
            ambientes_ativos_nomes = {
                a["name"] for aid, a in self._store.ambientes.items()
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
                        for sa in self._store.script_amb.values()
                        if sa["script_id"] == s["id"] and sa["environment_id"] in ambientes_ativos_ids
                    ]
                    if ambs_homologados:
                        executaveis.append(s)
                executaveis.sort(key=lambda x: (x.get("name", ""), x["id"]))
                return copy.deepcopy(executaveis)

            # Nao admin: requer funcionalidade EXEC_SCRIPT
            funcs = usuario_ctx.get("funcionalidades") or set()
            if "EXEC_SCRIPT" not in funcs:
                return []

            ambs_permitidos = usuario_ctx.get("ambientes") or set()
            scrs_permitidos = usuario_ctx.get("scripts") or set()

            executaveis = []
            for s in scripts_candidatos:
                # Script autorizado na dimensao de perfil
                if s["id"] not in scrs_permitidos and s["name"] not in scrs_permitidos:
                    continue

                # Homologacao ativa e autorizada
                homologados_ativos = [
                    self._store.ambientes[sa["environment_id"]]
                    for sa in self._store.script_amb.values()
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
