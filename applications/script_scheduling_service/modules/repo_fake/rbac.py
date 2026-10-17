# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de RBAC e perfis (README §2.5, §4.3, §10)."""
import copy

from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao
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

    def _auditar(self, auditoria, perfil_id):
        if auditoria:
            self._store.registrar_auditoria_interno(
                ator=auditoria.get("ator"),
                ip=auditoria.get("ip"),
                acao=auditoria["acao"],
                entidade="tbsss_perfis",
                entidade_id=perfil_id,
                detalhe=auditoria.get("detalhe"),
            )

    def perfis_inserir(self, dados, auditoria=None, ator=None):
        """Insere novo perfil com validacao de UK e CKs, auditando na mesma operacao."""
        with self._store.lock_rbac:
            ator = self._store.ator_registro(auditoria, ator)
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
            self._store.carimbar_inclusao(novo, ator)
            self._store.perfis[pid] = copy.deepcopy(novo)
            self._auditar(auditoria, pid)
            return copy.deepcopy(novo)

    def _admins_ativos(self, perfis):
        admin = set(pid for pid, p in perfis.items() if p["ativo"] == "S" and p["is_admin"] == "S")
        return sorted(u["id"] for u in self._store.usuarios.values()
                      if u["ativo"] == "S" and u["perfil_id"] in admin)

    def perfis_alterar(self, id, dados, esperado=None, auditoria=None, ator=None):
        """Altera perfil e incrementa perm_versao; protege o ultimo admin na mesma operacao (§4.3.B)."""
        # Ordem de locks igual a admins_ativos_bloquear: rbac e depois usuarios.
        with self._store.lock_rbac:
            with self._store.lock_usuarios:
                ator = self._store.ator_registro(auditoria, ator)
                if id not in self._store.perfis:
                    raise RepoNaoEncontrado("Perfil ID %s nao encontrado" % id)

                atual = self._store.perfis[id]
                for campo, valor in (esperado or {}).items():
                    if atual.get(campo) != valor:
                        raise RepoConflito("Perfil ID %s alterado por outra operacao (%s)" % (id, campo))

                mudancas = {}
                novo_nome = dados.get("nome")
                if novo_nome and novo_nome != atual["nome"]:
                    for pid, p in self._store.perfis.items():
                        if pid != id and p["nome"].upper() == novo_nome.upper():
                            raise RepoViolacao("Perfil com nome '%s' ja existe" % novo_nome,
                                               constraint="uk_tbsss_per_nome")
                    mudancas["nome"] = novo_nome

                if "descricao" in dados:
                    mudancas["descricao"] = dados["descricao"]

                for campo, ck in (("is_admin", "ck_tbsss_per_adm"), ("ativo", "ck_tbsss_per_ativo")):
                    if campo in dados:
                        if dados[campo] not in ("S", "N"):
                            raise RepoViolacao("Flag %s deve ser 'S' ou 'N'" % campo, constraint=ck)
                        mudancas[campo] = dados[campo]

                reduz_admin = atual["is_admin"] == "S" and atual["ativo"] == "S" and (
                    mudancas.get("is_admin") == "N" or mudancas.get("ativo") == "N")
                if reduz_admin:
                    resultantes = dict(self._store.perfis)
                    resultantes[id] = dict(atual, **mudancas)
                    if not self._admins_ativos(resultantes):
                        raise RepoViolacao("Operacao deixaria o sistema sem administrador ativo",
                                           constraint="sss_ultimo_admin")

                atual.update(mudancas)
                # Toda alteracao de perfil incrementa perm_versao (README §4.3.A)
                atual["perm_versao"] = int(atual.get("perm_versao", 1)) + 1
                self._store.carimbar_alteracao(atual, ator)
                self._auditar(auditoria, id)
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

    def matriz_salvar(self, perfil_id, funcs, ambs, scrs, perm_versao_esperada=None, auditoria=None, ator=None):
        """Substitui associacoes da matriz e incrementa perm_versao atomicamente (condicional a versao).

        Grava por diferenca: os vinculos que continuam mantem o created_*; havendo mudanca, o perfil
        recebe updated_* (CR-006, README §10).
        """
        with self._store.lock_rbac:
            with self._store.lock_catalogo:
                ator = self._store.ator_registro(auditoria, ator)
                if perfil_id not in self._store.perfis:
                    raise RepoNaoEncontrado("Perfil ID %s nao encontrado" % perfil_id)
                perfil = self._store.perfis[perfil_id]
                if perm_versao_esperada is not None and perfil["perm_versao"] != int(perm_versao_esperada):
                    raise RepoConflito("Matriz do perfil ID %s alterada por outra operacao" % perfil_id)

                # FKs (paridade com o Oracle): valida tudo antes de remover qualquer associacao.
                funcs = sorted(set(int(x) for x in (funcs or [])))
                ambs = sorted(set(int(x) for x in (ambs or [])))
                scrs = sorted(set(int(x) for x in (scrs or [])))
                for ids, tabela, fk in ((funcs, self._store.funcionalidades, "fk_tbsss_pfnc_fnc"),
                                        (ambs, self._store.ambientes, "fk_tbsss_pamb_amb"),
                                        (scrs, self._store.scripts, "fk_tbsss_pscr_scr")):
                    for x in ids:
                        if x not in tabela:
                            raise RepoViolacao("ID %s inexistente" % x, constraint=fk)

                mudou = False
                for assoc, seq, coluna, ids in (
                        (self._store.perfil_func, "tbsss_perfil_func", "funcionalidade_id", funcs),
                        (self._store.perfil_amb, "tbsss_perfil_amb", "ambiente_id", ambs),
                        (self._store.perfil_scr, "tbsss_perfil_scr", "script_id", scrs)):
                    atuais = dict((v[coluna], k) for k, v in assoc.items() if v["perfil_id"] == perfil_id)
                    for x, k in atuais.items():
                        if x not in ids:
                            del assoc[k]
                    for x in ids:
                        if x not in atuais:
                            nid = self._store.proximo_id(seq)
                            assoc[nid] = self._store.carimbar_inclusao(
                                {"id": nid, "perfil_id": perfil_id, coluna: x}, ator)
                    mudou = mudou or set(atuais) != set(ids)

                # Incrementa perm_versao atomicamente na mesma transacao
                perfil["perm_versao"] += 1
                if mudou:
                    self._store.carimbar_alteracao(perfil, ator)
                self._auditar(auditoria, perfil_id)
                return copy.deepcopy(self.matriz_obter(perfil_id))

    def admins_ativos_bloquear(self):
        """Retorna IDs dos administradores ativos conforme semantica do README §4.3.B."""
        with self._store.lock_rbac:
            with self._store.lock_usuarios:
                return self._admins_ativos(self._store.perfis)

    def funcionalidades_listar(self):
        """Retorna lista do catalogo canonico de funcionalidades."""
        with self._store.lock_rbac:
            lista = list(self._store.funcionalidades.values())
            lista.sort(key=lambda x: (x.get("modulo", ""), x.get("codigo", ""), x["id"]))
            return copy.deepcopy(lista)
