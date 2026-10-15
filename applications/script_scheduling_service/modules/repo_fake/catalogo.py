# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de catalogo (README §2.5, §4.3.A, §6.3, §10)."""
import copy
import re

from repo_catalogo import RepoCatalogo
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
    # Ambientes (tbsss_ambientes)
    # -------------------------------------------------------------------------

    def ambientes_listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista ambientes com paginacao deterministica por nome ASC, id ASC."""
        filtros = filtros or {}
        with self._store.lock_catalogo:
            lista = list(self._store.ambientes.values())

            nome_f = filtros.get("nome")
            if nome_f:
                lista = [a for a in lista if nome_f.upper() in a["nome"].upper()]

            ativo_f = filtros.get("ativo")
            if ativo_f:
                lista = [a for a in lista if a["ativo"] == ativo_f]

            lista.sort(key=lambda x: (x.get("nome", ""), x["id"]))
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
                ator=auditoria.get("ator"),
                ip=auditoria.get("ip"),
                acao=auditoria["acao"],
                entidade="tbsss_ambientes",
                entidade_id=ambiente_id,
                detalhe=auditoria.get("detalhe"),
            )

    def ambientes_inserir(self, dados, auditoria=None):
        """Insere novo ambiente com validacao de CKs, UK e DSN, auditando na mesma operacao."""
        with self._store.lock_catalogo:
            nome = dados.get("nome")
            if not nome or not _RE_AMB_NOME.fullmatch(nome):
                raise RepoViolacao("Nome de ambiente invalido (esperado: 1-30 chars [A-Z0-9_])", constraint="ck_tbsss_amb_nome")

            for a in self._store.ambientes.values():
                if a["nome"].upper() == nome.upper():
                    raise RepoViolacao("Ambiente com nome '%s' ja existe" % nome, constraint="uk_tbsss_amb_nome")

            conexao = dados.get("conexao")
            if conexao and "@" in conexao:
                raise RepoViolacao("Conexao nao pode conter credencial (@)", constraint="ck_tbsss_amb_conexao")

            ativo = dados.get("ativo", "S")
            if ativo not in ("S", "N"):
                raise RepoViolacao("Flag ativo deve ser 'S' ou 'N'", constraint="ck_tbsss_amb_ativo")

            aid = self._store.proximo_id("tbsss_ambientes")
            novo = {
                "id": aid,
                "nome": nome,
                "descricao": dados.get("descricao", ""),
                "conexao": conexao,
                "ativo": ativo,
                "created_at": dados.get("created_at") or self._store.agora(),
            }
            self._store.ambientes[aid] = copy.deepcopy(novo)
            self._auditar_ambiente(auditoria, aid)
            return copy.deepcopy(novo)

    def ambientes_alterar(self, id, dados, esperado=None, auditoria=None):
        """Altera ambiente (nome imutavel, trigger tr_tbsss_amb_bu), condicional a 'esperado'."""
        with self._store.lock_catalogo:
            if id not in self._store.ambientes:
                raise RepoNaoEncontrado("Ambiente ID %s nao encontrado" % id)

            atual = self._store.ambientes[id]
            for campo, valor in (esperado or {}).items():
                if atual.get(campo) != valor:
                    raise RepoConflito("Ambiente ID %s alterado por outra operacao (%s)" % (id, campo))

            novo_nome = dados.get("nome")
            if novo_nome is not None and novo_nome != atual["nome"]:
                raise RepoViolacao("Nome de ambiente e imutavel", constraint="tr_tbsss_amb_bu")

            mudancas = {}
            novo_conexao = dados.get("conexao")
            if novo_conexao is not None:
                if "@" in novo_conexao:
                    raise RepoViolacao("Conexao nao pode conter credencial (@)", constraint="ck_tbsss_amb_conexao")
                mudancas["conexao"] = novo_conexao
            elif "conexao" in dados:
                mudancas["conexao"] = None

            if "descricao" in dados:
                mudancas["descricao"] = dados["descricao"]

            novo_ativo = dados.get("ativo")
            if novo_ativo is not None:
                if novo_ativo not in ("S", "N"):
                    raise RepoViolacao("Flag ativo deve ser 'S' ou 'N'", constraint="ck_tbsss_amb_ativo")
                mudancas["ativo"] = novo_ativo

            # Validacao completa antes de aplicar: um UPDATE rejeitado nao altera nenhuma coluna.
            atual.update(mudancas)
            self._auditar_ambiente(auditoria, id)
            return copy.deepcopy(atual)

    # -------------------------------------------------------------------------
    # Scripts (tbsss_scripts)
    # -------------------------------------------------------------------------

    def scripts_listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista scripts com paginacao deterministica por nome ASC, id ASC."""
        filtros = filtros or {}
        with self._store.lock_catalogo:
            lista = list(self._store.scripts.values())

            nome_f = filtros.get("nome")
            if nome_f:
                lista = [s for s in lista if nome_f.lower() in s["nome"].lower()]

            grupo_f = filtros.get("grupo")
            if grupo_f:
                lista = [s for s in lista if s.get("grupo") == grupo_f]

            categoria_f = filtros.get("categoria")
            if categoria_f:
                lista = [s for s in lista if s.get("categoria") == categoria_f]

            ativo_f = filtros.get("ativo")
            if ativo_f:
                lista = [s for s in lista if s["ativo"] == ativo_f]

            lista.sort(key=lambda x: (x.get("nome", ""), x["id"]))
            return paginar(lista, pagina=pagina, tamanho=tamanho)

    def scripts_obter(self, id):
        """Retorna dict do script pelo ID ou lanca RepoNaoEncontrado."""
        with self._store.lock_catalogo:
            if id not in self._store.scripts:
                raise RepoNaoEncontrado("Script ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.scripts[id])

    def scripts_inserir(self, dados):
        """Insere novo script com validacoes de seguranca e CKs."""
        with self._store.lock_catalogo:
            nome = dados.get("nome")
            if not nome:
                raise RepoViolacao("Nome de script e obrigatorio")

            for s in self._store.scripts.values():
                if s["nome"].lower() == nome.lower():
                    raise RepoViolacao("Script com nome '%s' ja existe" % nome, constraint="uk_tbsss_scr_nome")

            tparam = dados.get("tipo_param", "NOMEADO")
            if tparam not in ("NOMEADO", "SEQUENCIAL", "NENHUM"):
                raise RepoViolacao("Tipo de parametro invalido", constraint="ck_tbsss_scr_tparam")

            ativo = dados.get("ativo", "S")
            if ativo not in ("S", "N"):
                raise RepoViolacao("Flag ativo deve ser 'S' ou 'N'", constraint="ck_tbsss_scr_ativo")

            cmd = dados.get("comando_real")
            if cmd not in ("/usr/bin/python3", "/bin/bash", "/bin/sh"):
                raise RepoViolacao("Comando real fora da allowlist", constraint="ck_tbsss_scr_cmd")

            pfile = dados.get("path_file", "")
            if not pfile or pfile.startswith("/") or ".." in pfile:
                raise RepoViolacao("path_file deve ser relativo e sem '..'", constraint="ck_tbsss_scr_path")

            paral = int(dados.get("max_qtd_parallel_env", 1))
            if not (1 <= paral <= 999):
                raise RepoViolacao("max_qtd_parallel_env deve estar entre 1 e 999", constraint="ck_tbsss_scr_paral")

            tmout = dados.get("timeout_seg")
            if tmout is not None:
                tmout = int(tmout)
                if tmout <= 0:
                    raise RepoViolacao("timeout_seg deve ser maior que zero", constraint="ck_tbsss_scr_tmout")

            sid = self._store.proximo_id("tbsss_scripts")
            novo = {
                "id": sid,
                "nome": nome,
                "descricao": dados.get("descricao", ""),
                "grupo": dados.get("grupo"),
                "categoria": dados.get("categoria"),
                "etapa": dados.get("etapa"),
                "comando_real": cmd,
                "path_file": pfile,
                "tipo_param": tparam,
                "max_qtd_parallel_env": paral,
                "timeout_seg": tmout,
                "ativo": ativo,
            }
            self._store.scripts[sid] = copy.deepcopy(novo)
            return copy.deepcopy(novo)

    def scripts_alterar(self, id, dados):
        """Altera script aplicando validacoes de integridade."""
        with self._store.lock_catalogo:
            if id not in self._store.scripts:
                raise RepoNaoEncontrado("Script ID %s nao encontrado" % id)

            atual = self._store.scripts[id]

            novo_nome = dados.get("nome")
            if novo_nome and novo_nome.lower() != atual["nome"].lower():
                for sid, s in self._store.scripts.items():
                    if sid != id and s["nome"].lower() == novo_nome.lower():
                        raise RepoViolacao("Script com nome '%s' ja existe" % novo_nome, constraint="uk_tbsss_scr_nome")
                atual["nome"] = novo_nome

            if "descricao" in dados:
                atual["descricao"] = dados["descricao"]
            if "grupo" in dados:
                atual["grupo"] = dados["grupo"]
            if "categoria" in dados:
                atual["categoria"] = dados["categoria"]
            if "etapa" in dados:
                atual["etapa"] = dados["etapa"]

            if "comando_real" in dados:
                cmd = dados["comando_real"]
                if cmd not in ("/usr/bin/python3", "/bin/bash", "/bin/sh"):
                    raise RepoViolacao("Comando real fora da allowlist", constraint="ck_tbsss_scr_cmd")
                atual["comando_real"] = cmd

            if "path_file" in dados:
                pfile = dados["path_file"]
                if not pfile or pfile.startswith("/") or ".." in pfile:
                    raise RepoViolacao("path_file deve ser relativo e sem '..'", constraint="ck_tbsss_scr_path")
                atual["path_file"] = pfile

            if "tipo_param" in dados:
                tp = dados["tipo_param"]
                if tp not in ("NOMEADO", "SEQUENCIAL", "NENHUM"):
                    raise RepoViolacao("Tipo de parametro invalido", constraint="ck_tbsss_scr_tparam")
                atual["tipo_param"] = tp

            if "max_qtd_parallel_env" in dados:
                paral = int(dados["max_qtd_parallel_env"])
                if not (1 <= paral <= 999):
                    raise RepoViolacao("max_qtd_parallel_env deve estar entre 1 e 999", constraint="ck_tbsss_scr_paral")
                atual["max_qtd_parallel_env"] = paral

            if "timeout_seg" in dados:
                tmout = dados["timeout_seg"]
                if tmout is not None:
                    tmout = int(tmout)
                    if tmout <= 0:
                        raise RepoViolacao("timeout_seg deve ser maior que zero", constraint="ck_tbsss_scr_tmout")
                atual["timeout_seg"] = tmout

            if "ativo" in dados:
                ativo = dados["ativo"]
                if ativo not in ("S", "N"):
                    raise RepoViolacao("Flag ativo deve ser 'S' ou 'N'", constraint="ck_tbsss_scr_ativo")
                atual["ativo"] = ativo

            return copy.deepcopy(atual)

    # -------------------------------------------------------------------------
    # Homologacao de Scripts por Ambiente (tbsss_script_amb)
    # -------------------------------------------------------------------------

    def homologacao_obter(self, script_id):
        """Retorna lista de ambiente_id homologados para o script."""
        with self._store.lock_catalogo:
            if script_id not in self._store.scripts:
                raise RepoNaoEncontrado("Script ID %s nao encontrado" % script_id)
            ambs = [
                sa["ambiente_id"]
                for sa in self._store.script_amb.values()
                if sa["script_id"] == script_id
            ]
            ambs.sort()
            return copy.deepcopy(ambs)

    def homologacao_salvar(self, script_id, ambiente_ids):
        """Atualiza homologacoes do script."""
        with self._store.lock_catalogo:
            if script_id not in self._store.scripts:
                raise RepoNaoEncontrado("Script ID %s nao encontrado" % script_id)

            for aid in (ambiente_ids or []):
                if aid not in self._store.ambientes:
                    raise RepoViolacao("Ambiente ID %s nao existe" % aid, constraint="fk_tbsss_samb_amb")

            # Remove anteriores
            remover = [k for k, v in self._store.script_amb.items() if v["script_id"] == script_id]
            for k in remover:
                del self._store.script_amb[k]

            for aid in set(ambiente_ids or []):
                nid = self._store.proximo_id("tbsss_script_amb")
                self._store.script_amb[nid] = {
                    "id": nid,
                    "script_id": script_id,
                    "ambiente_id": int(aid),
                }

            return copy.deepcopy(self.homologacao_obter(script_id))

    # -------------------------------------------------------------------------
    # Parametros (tbsss_parametros)
    # -------------------------------------------------------------------------

    def parametros_listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista parametros com paginacao deterministica por codigo ASC, id ASC."""
        filtros = filtros or {}
        with self._store.lock_catalogo:
            lista = list(self._store.parametros.values())

            cod_f = filtros.get("codigo")
            if cod_f:
                lista = [p for p in lista if cod_f.lower() in p["codigo"].lower()]

            label_f = filtros.get("label")
            if label_f:
                lista = [p for p in lista if label_f.lower() in p["label"].lower()]

            tipo_f = filtros.get("tipo_componente")
            if tipo_f:
                lista = [p for p in lista if p["tipo_componente"] == tipo_f]

            ativo_f = filtros.get("ativo")
            if ativo_f:
                lista = [p for p in lista if p["ativo"] == ativo_f]

            lista.sort(key=lambda x: (x.get("codigo", ""), x["id"]))
            return paginar(lista, pagina=pagina, tamanho=tamanho)

    def parametros_obter(self, id):
        """Retorna dict do parametro pelo ID ou lanca RepoNaoEncontrado."""
        with self._store.lock_catalogo:
            if id not in self._store.parametros:
                raise RepoNaoEncontrado("Parametro ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.parametros[id])

    def parametros_inserir(self, dados):
        """Insere novo parametro validando CKs e UK."""
        with self._store.lock_catalogo:
            codigo = dados.get("codigo")
            if not codigo or not _RE_PRM_CODIGO.fullmatch(codigo):
                raise RepoViolacao("Codigo de parametro invalido (esperado: 1-30 chars [a-z0-9_])", constraint="ck_tbsss_prm_codigo")

            for p in self._store.parametros.values():
                if p["codigo"] == codigo:
                    raise RepoViolacao("Parametro com codigo '%s' ja existe" % codigo, constraint="uk_tbsss_prm_codigo")

            tcomp = dados.get("tipo_componente")
            if tcomp not in ("TEXT", "NUMBER", "DATE", "SELECT", "CHECKBOX"):
                raise RepoViolacao("Tipo de componente invalido", constraint="ck_tbsss_prm_tcomp")

            flag = dados.get("param_nomeado")
            if flag is not None and flag != "":
                if not _RE_PRM_FLAG.fullmatch(flag):
                    raise RepoViolacao("Flag param_nomeado invalida", constraint="ck_tbsss_prm_flag")
            else:
                flag = None

            sens = dados.get("sensivel", "N")
            if sens not in ("S", "N"):
                raise RepoViolacao("sensivel deve ser 'S' ou 'N'", constraint="ck_tbsss_prm_sens")

            ativo = dados.get("ativo", "S")
            if ativo not in ("S", "N"):
                raise RepoViolacao("Flag ativo deve ser 'S' ou 'N'", constraint="ck_tbsss_prm_ativo")

            pid = self._store.proximo_id("tbsss_parametros")
            novo = {
                "id": pid,
                "codigo": codigo,
                "param_nomeado": flag,
                "label": dados.get("label", ""),
                "descricao": dados.get("descricao", ""),
                "tipo_componente": tcomp,
                "opcoes_json": dados.get("opcoes_json"),
                "valor_padrao": dados.get("valor_padrao"),
                "regex_validacao": dados.get("regex_validacao"),
                "sensivel": sens,
                "ativo": ativo,
            }
            self._store.parametros[pid] = copy.deepcopy(novo)
            return copy.deepcopy(novo)

    def parametros_alterar(self, id, dados):
        """Altera parametro aplicando validacoes de integridade."""
        with self._store.lock_catalogo:
            if id not in self._store.parametros:
                raise RepoNaoEncontrado("Parametro ID %s nao encontrado" % id)

            atual = self._store.parametros[id]

            if "label" in dados:
                atual["label"] = dados["label"]
            if "descricao" in dados:
                atual["descricao"] = dados["descricao"]

            if "param_nomeado" in dados:
                flag = dados["param_nomeado"]
                if flag is not None and flag != "":
                    if not _RE_PRM_FLAG.fullmatch(flag):
                        raise RepoViolacao("Flag param_nomeado invalida", constraint="ck_tbsss_prm_flag")
                    atual["param_nomeado"] = flag
                else:
                    atual["param_nomeado"] = None

            if "tipo_componente" in dados:
                tcomp = dados["tipo_componente"]
                if tcomp not in ("TEXT", "NUMBER", "DATE", "SELECT", "CHECKBOX"):
                    raise RepoViolacao("Tipo de componente invalido", constraint="ck_tbsss_prm_tcomp")
                atual["tipo_componente"] = tcomp

            if "opcoes_json" in dados:
                atual["opcoes_json"] = dados["opcoes_json"]
            if "valor_padrao" in dados:
                atual["valor_padrao"] = dados["valor_padrao"]
            if "regex_validacao" in dados:
                atual["regex_validacao"] = dados["regex_validacao"]

            if "sensivel" in dados:
                sens = dados["sensivel"]
                if sens not in ("S", "N"):
                    raise RepoViolacao("sensivel deve ser 'S' ou 'N'", constraint="ck_tbsss_prm_sens")
                atual["sensivel"] = sens

            if "ativo" in dados:
                ativo = dados["ativo"]
                if ativo not in ("S", "N"):
                    raise RepoViolacao("Flag ativo deve ser 'S' ou 'N'", constraint="ck_tbsss_prm_ativo")
                atual["ativo"] = ativo

            return copy.deepcopy(atual)

    def parametro_vinculos(self, parametro_id):
        """Retorna lista de scripts vinculados ao parametro para verificacao de desativacao."""
        with self._store.lock_catalogo:
            script_ids = {
                sp["script_id"]
                for sp in self._store.script_param.values()
                if sp["parametro_id"] == parametro_id
            }
            resultado = [
                s for sid, s in self._store.scripts.items()
                if sid in script_ids
            ]
            resultado.sort(key=lambda x: (x.get("nome", ""), x["id"]))
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
            vinculos.sort(key=lambda x: x["ordem"])

            resultado = []
            for v in vinculos:
                param = self._store.parametros.get(v["parametro_id"])
                if param:
                    item = copy.deepcopy(param)
                    item["script_id"] = script_id
                    item["parametro_id"] = param["id"]
                    item["ordem"] = v["ordem"]
                    item["obrigatorio"] = v["obrigatorio"]
                    item["valor_padrao_sub"] = v.get("valor_padrao_sub")
                    resultado.append(item)
            return copy.deepcopy(resultado)

    def script_params_salvar(self, script_id, vinculos):
        """Salva vinculos de parametros com validacao de ordem e unicidade."""
        with self._store.lock_catalogo:
            if script_id not in self._store.scripts:
                raise RepoNaoEncontrado("Script ID %s nao encontrado" % script_id)

            params_vistos = set()
            ordens_vistas = set()

            novos_vinculos = []
            for item in (vinculos or []):
                pid = int(item["parametro_id"])
                if pid not in self._store.parametros:
                    raise RepoViolacao("Parametro ID %s nao existe" % pid, constraint="fk_tbsss_sprm_prm")

                if pid in params_vistos:
                    raise RepoViolacao("Parametro duplicado no script", constraint="uk_tbsss_sprm_scr_prm")
                params_vistos.add(pid)

                ordem = int(item["ordem"])
                if ordem < 1:
                    raise RepoViolacao("Ordem deve ser >= 1", constraint="ck_tbsss_sprm_ordem")
                if ordem in ordens_vistas:
                    raise RepoViolacao("Ordem duplicada no script", constraint="uk_tbsss_sprm_scr_ord")
                ordens_vistas.add(ordem)

                obrig = item.get("obrigatorio", "S")
                if obrig not in ("S", "N"):
                    raise RepoViolacao("obrigatorio deve ser 'S' ou 'N'", constraint="ck_tbsss_sprm_obrig")

                novos_vinculos.append({
                    "script_id": script_id,
                    "parametro_id": pid,
                    "ordem": ordem,
                    "obrigatorio": obrig,
                    "valor_padrao_sub": item.get("valor_padrao_sub"),
                })

            # Remove anteriores
            remover = [k for k, v in self._store.script_param.items() if v["script_id"] == script_id]
            for k in remover:
                del self._store.script_param[k]

            for nv in novos_vinculos:
                nid = self._store.proximo_id("tbsss_script_param")
                nv["id"] = nid
                self._store.script_param[nid] = nv

            return copy.deepcopy(self.script_params_obter(script_id))

    # -------------------------------------------------------------------------
    # Scripts Executaveis (README §4.3.A)
    # -------------------------------------------------------------------------

    def scripts_executaveis(self, usuario_ctx):
        """Retorna lista filtrada de scripts que o usuario pode executar."""
        with self._store.lock_catalogo:
            usuario_ctx = usuario_ctx or {}
            is_admin = usuario_ctx.get("is_admin") in ("S", True)

            # Mapeamento de ambientes ativos
            ambientes_ativos_ids = {
                aid for aid, a in self._store.ambientes.items()
                if a["ativo"] == "S"
            }
            ambientes_ativos_nomes = {
                a["nome"] for aid, a in self._store.ambientes.items()
                if a["ativo"] == "S"
            }

            # Scripts ativos
            scripts_candidatos = [
                s for s in self._store.scripts.values()
                if s["ativo"] == "S"
            ]

            if is_admin:
                # Admin dispensa dimensoes 1-3, mas exige homologacao em ambiente ativo
                executaveis = []
                for s in scripts_candidatos:
                    ambs_homologados = [
                        sa["ambiente_id"]
                        for sa in self._store.script_amb.values()
                        if sa["script_id"] == s["id"] and sa["ambiente_id"] in ambientes_ativos_ids
                    ]
                    if ambs_homologados:
                        executaveis.append(s)
                executaveis.sort(key=lambda x: (x.get("nome", ""), x["id"]))
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
                if s["id"] not in scrs_permitidos and s["nome"] not in scrs_permitidos:
                    continue

                # Homologacao ativa e autorizada
                homologados_ativos = [
                    self._store.ambientes[sa["ambiente_id"]]
                    for sa in self._store.script_amb.values()
                    if sa["script_id"] == s["id"] and sa["ambiente_id"] in ambientes_ativos_ids
                ]

                # Deve haver ao menos um ambiente homologado que esteja nos ambientes autorizados
                pode_em_algum = False
                for a in homologados_ativos:
                    if a["id"] in ambs_permitidos or a["nome"] in ambs_permitidos:
                        pode_em_algum = True
                        break

                if pode_em_algum:
                    executaveis.append(s)

            executaveis.sort(key=lambda x: (x.get("nome", ""), x["id"]))
            return copy.deepcopy(executaveis)
