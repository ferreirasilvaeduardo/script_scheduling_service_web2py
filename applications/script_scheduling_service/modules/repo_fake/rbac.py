# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de RBAC e perfis (README §2.5, §4.3, §10)."""
import copy

from repo_errors import RepoNaoEncontrado, RepoViolacao
from repo_fake.store import paginar
from repo_rbac import RepoRbac


class RepoRbacFake(RepoRbac):
    """Implementacao em memoria com semantica Oracle para perfis e RBAC."""

    def __init__(self, store):
        self._store = store

    def perfis_listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista perfis com paginacao e desempate deterministico por id."""
        filtros = filtros or {}
        with self._store.lock_rbac:
            lista = list(self._store.perfis.values())

            nome_f = filtros.get("nome")
            if nome_f:
                lista = [p for p in lista if nome_f.lower() in p["nome"].lower()]

            ativo_f = filtros.get("ativo")
            if ativo_f:
                lista = [p for p in lista if p["ativo"] == ativo_f]

            is_admin_f = filtros.get("is_admin")
            if is_admin_f:
                lista = [p for p in lista if p["is_admin"] == is_admin_f]

            lista.sort(key=lambda x: (x.get("nome", ""), x["id"]))
            return paginar(lista, pagina=pagina, tamanho=tamanho)

    def perfis_obter(self, id):
        """Retorna dict com dados do perfil pelo ID ou lanca RepoNaoEncontrado."""
        with self._store.lock_rbac:
            if id not in self._store.perfis:
                raise RepoNaoEncontrado("Perfil ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.perfis[id])

    def perfis_inserir(self, dados):
        """Insere novo perfil com validacao de UK e CKs."""
        with self._store.lock_rbac:
            nome = dados.get("nome")
            if not nome:
                raise RepoViolacao("Nome de perfil e obrigatorio")

            for p in self._store.perfis.values():
                if p["nome"].upper() == nome.upper():
                    raise RepoViolacao("Perfil com nome '%s' ja existe" % nome, constraint="uk_tbsss_per_nome")

            is_admin = dados.get("is_admin", "N")
            if is_admin not in ("S", "N"):
                raise RepoViolacao("Flag is_admin deve ser 'S' ou 'N'", constraint="ck_tbsss_per_adm")

            ativo = dados.get("ativo", "S")
            if ativo not in ("S", "N"):
                raise RepoViolacao("Flag ativo deve ser 'S' ou 'N'", constraint="ck_tbsss_per_ativo")

            pid = self._store.proximo_id("tbsss_perfis")
            novo = {
                "id": pid,
                "nome": nome,
                "descricao": dados.get("descricao", ""),
                "is_admin": is_admin,
                "perm_versao": int(dados.get("perm_versao", 1)),
                "ativo": ativo,
            }
            self._store.perfis[pid] = copy.deepcopy(novo)
            return copy.deepcopy(novo)

    def perfis_alterar(self, id, dados):
        """Altera perfil e incrementa perm_versao atomicamente."""
        with self._store.lock_rbac:
            if id not in self._store.perfis:
                raise RepoNaoEncontrado("Perfil ID %s nao encontrado" % id)

            atual = self._store.perfis[id]

            novo_nome = dados.get("nome")
            if novo_nome and novo_nome.upper() != atual["nome"].upper():
                for pid, p in self._store.perfis.items():
                    if pid != id and p["nome"].upper() == novo_nome.upper():
                        raise RepoViolacao("Perfil com nome '%s' ja existe" % novo_nome, constraint="uk_tbsss_per_nome")
                atual["nome"] = novo_nome

            if "descricao" in dados:
                atual["descricao"] = dados["descricao"]

            if "is_admin" in dados:
                if dados["is_admin"] not in ("S", "N"):
                    raise RepoViolacao("Flag is_admin deve ser 'S' ou 'N'", constraint="ck_tbsss_per_adm")
                atual["is_admin"] = dados["is_admin"]

            if "ativo" in dados:
                if dados["ativo"] not in ("S", "N"):
                    raise RepoViolacao("Flag ativo deve ser 'S' ou 'N'", constraint="ck_tbsss_per_ativo")
                atual["ativo"] = dados["ativo"]

            # Toda alteracao de perfil incrementa perm_versao (README §4.3.A)
            atual["perm_versao"] = int(atual.get("perm_versao", 1)) + 1

            return copy.deepcopy(atual)

    def matriz_obter(self, perfil_id):
        """Retorna {'funcs': [...], 'ambs': [...], 'scrs': [...]} com os IDs associados."""
        with self._store.lock_rbac:
            if perfil_id not in self._store.perfis:
                raise RepoNaoEncontrado("Perfil ID %s nao encontrado" % perfil_id)

            funcs = [
                v["funcionalidade_id"]
                for v in self._store.perfil_func.values()
                if v["perfil_id"] == perfil_id
            ]
            ambs = [
                v["ambiente_id"]
                for v in self._store.perfil_amb.values()
                if v["perfil_id"] == perfil_id
            ]
            scrs = [
                v["script_id"]
                for v in self._store.perfil_scr.values()
                if v["perfil_id"] == perfil_id
            ]
            return {
                "funcs": copy.deepcopy(funcs),
                "ambs": copy.deepcopy(ambs),
                "scrs": copy.deepcopy(scrs),
            }

    def matriz_salvar(self, perfil_id, funcs, ambs, scrs):
        """Substitui associacoes da matriz e incrementa perm_versao atomicamente."""
        with self._store.lock_rbac:
            with self._store.lock_catalogo:
                if perfil_id not in self._store.perfis:
                    raise RepoNaoEncontrado("Perfil ID %s nao encontrado" % perfil_id)

                # Remove associacoes anteriores
                remover_f = [k for k, v in self._store.perfil_func.items() if v["perfil_id"] == perfil_id]
                for k in remover_f:
                    del self._store.perfil_func[k]

                remover_a = [k for k, v in self._store.perfil_amb.items() if v["perfil_id"] == perfil_id]
                for k in remover_a:
                    del self._store.perfil_amb[k]

                remover_s = [k for k, v in self._store.perfil_scr.items() if v["perfil_id"] == perfil_id]
                for k in remover_s:
                    del self._store.perfil_scr[k]

                # Insere novas associacoes
                for fid in (funcs or []):
                    nid = self._store.proximo_id("tbsss_perfil_func")
                    self._store.perfil_func[nid] = {
                        "id": nid,
                        "perfil_id": perfil_id,
                        "funcionalidade_id": int(fid),
                    }

                for aid in (ambs or []):
                    nid = self._store.proximo_id("tbsss_perfil_amb")
                    self._store.perfil_amb[nid] = {
                        "id": nid,
                        "perfil_id": perfil_id,
                        "ambiente_id": int(aid),
                    }

                for sid in (scrs or []):
                    nid = self._store.proximo_id("tbsss_perfil_scr")
                    self._store.perfil_scr[nid] = {
                        "id": nid,
                        "perfil_id": perfil_id,
                        "script_id": int(sid),
                    }

                # Incrementa perm_versao atomicamente na mesma transacao
                self._store.perfis[perfil_id]["perm_versao"] += 1
                return copy.deepcopy(self.matriz_obter(perfil_id))

    def admins_ativos_bloquear(self):
        """Retorna IDs dos administradores ativos conforme semantica do README §4.3.B."""
        with self._store.lock_rbac:
            with self._store.lock_usuarios:
                perfis_admin_ativos = {
                    pid for pid, p in self._store.perfis.items()
                    if p["ativo"] == "S" and p["is_admin"] == "S"
                }
                admin_user_ids = [
                    u["id"] for u in self._store.usuarios.values()
                    if u["ativo"] == "S" and u["perfil_id"] in perfis_admin_ativos
                ]
                admin_user_ids.sort()
                return copy.deepcopy(admin_user_ids)

    def funcionalidades_listar(self):
        """Retorna lista do catalogo canonico de funcionalidades."""
        with self._store.lock_rbac:
            lista = list(self._store.funcionalidades.values())
            lista.sort(key=lambda x: (x.get("modulo", ""), x.get("codigo", ""), x["id"]))
            return copy.deepcopy(lista)
