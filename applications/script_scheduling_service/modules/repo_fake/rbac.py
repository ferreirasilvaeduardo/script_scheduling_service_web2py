# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de RBAC e perfis (README §2.5, §4.3, §10)."""
import copy

from repo_errors import RepoConflict, RepoNotFound, RepoViolation
from repo_fake.store import paginate
from repo_rbac import RepoRbac


class RepoRbacFake(RepoRbac):
    """Implementacao em memoria com semantica Oracle para perfis e RBAC."""

    def __init__(self, store):
        self._store = store

    def profiles_list(self, filters=None, page=1, size=20):
        """Lista perfis com paginacao e desempate deterministico por id."""
        filters = filters or {}
        with self._store.lock_rbac:
            lista = list(self._store.profiles.values())

            nome_f = filters.get("name")
            if nome_f:
                lista = [p for p in lista if nome_f.lower() in p["name"].lower()]

            ativo_f = filters.get("active")
            if ativo_f:
                lista = [p for p in lista if p["active"] == ativo_f]

            is_admin_f = filters.get("is_admin")
            if is_admin_f:
                lista = [p for p in lista if p["is_admin"] == is_admin_f]

            lista.sort(key=lambda x: (x.get("name", ""), x["id"]))
            return paginate(lista, page=page, size=size)

    def profiles_get(self, id):
        """Retorna dict com dados do perfil pelo ID ou lanca RepoNotFound."""
        with self._store.lock_rbac:
            if id not in self._store.profiles:
                raise RepoNotFound("Perfil ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.profiles[id])

    def _auditar(self, audit, profile_id):
        if audit:
            self._store.register_internal_audit(
                actor=audit.get("actor"),
                ip=audit.get("ip"),
                action=audit["action"],
                entity="tbsss_profiles",
                entity_id=profile_id,
                detail=audit.get("detail"),
            )

    def profiles_insert(self, date, audit=None, actor=None):
        """Insere novo perfil com validacao de UK e CKs, auditando na mesma operacao."""
        with self._store.lock_rbac:
            actor = self._store.record_actor(audit, actor)
            nome = date.get("name")
            if not nome:
                raise RepoViolation("Nome de perfil e obrigatorio")

            for p in self._store.profiles.values():
                if p["name"].upper() == nome.upper():
                    raise RepoViolation("Perfil com nome '%s' ja existe" % nome, constraint="uk_tbsss_prf_name")

            is_admin = date.get("is_admin", "N")
            if is_admin not in ("Y", "N"):
                raise RepoViolation("Flag is_admin deve ser 'Y' ou 'N'", constraint="ck_tbsss_prf_adm")

            ativo = date.get("active", "Y")
            if ativo not in ("Y", "N"):
                raise RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_prf_active")

            pid = self._store.next_id("tbsss_profiles")
            novo = {
                "id": pid,
                "name": nome,
                "description": date.get("description", ""),
                "is_admin": is_admin,
                "perm_version": int(date.get("perm_version", 1)),
                "active": ativo,
            }
            self._store.stamp_insert(novo, actor)
            self._store.profiles[pid] = copy.deepcopy(novo)
            self._auditar(audit, pid)
            return copy.deepcopy(novo)

    def _admins_ativos(self, profiles):
        admin = set(pid for pid, p in profiles.items() if p["active"] == "Y" and p["is_admin"] == "Y")
        return sorted(u["id"] for u in self._store.users.values()
                      if u["active"] == "Y" and u["profile_id"] in admin)

    def profiles_update(self, id, date, expected=None, audit=None, actor=None):
        """Altera perfil e incrementa perm_versao; protege o ultimo admin na mesma operacao (§4.3.B)."""
        # Ordem de locks igual a admins_ativos_bloquear: rbac e depois usuarios.
        with self._store.lock_rbac:
            with self._store.lock_users:
                actor = self._store.record_actor(audit, actor)
                if id not in self._store.profiles:
                    raise RepoNotFound("Perfil ID %s nao encontrado" % id)

                atual = self._store.profiles[id]
                for campo, valor in (expected or {}).items():
                    if atual.get(campo) != valor:
                        raise RepoConflict("Perfil ID %s alterado por outra operacao (%s)" % (id, campo))

                mudancas = {}
                novo_nome = date.get("name")
                if novo_nome and novo_nome != atual["name"]:
                    for pid, p in self._store.profiles.items():
                        if pid != id and p["name"].upper() == novo_nome.upper():
                            raise RepoViolation("Perfil com nome '%s' ja existe" % novo_nome,
                                               constraint="uk_tbsss_prf_name")
                    mudancas["name"] = novo_nome

                if "description" in date:
                    mudancas["description"] = date["description"]

                for campo, ck in (("is_admin", "ck_tbsss_prf_adm"), ("active", "ck_tbsss_prf_active")):
                    if campo in date:
                        if date[campo] not in ("Y", "N"):
                            raise RepoViolation("Flag %s deve ser 'Y' ou 'N'" % campo, constraint=ck)
                        mudancas[campo] = date[campo]

                reduz_admin = atual["is_admin"] == "Y" and atual["active"] == "Y" and (
                    mudancas.get("is_admin") == "N" or mudancas.get("active") == "N")
                if reduz_admin:
                    resultantes = dict(self._store.profiles)
                    resultantes[id] = dict(atual, **mudancas)
                    if not self._admins_ativos(resultantes):
                        raise RepoViolation("Operacao deixaria o sistema sem administrador ativo",
                                           constraint="sss_ultimo_admin")

                atual.update(mudancas)
                # Toda alteracao de perfil incrementa perm_versao (README §4.3.A)
                atual["perm_version"] = int(atual.get("perm_version", 1)) + 1
                self._store.stamp_update(atual, actor)
                self._auditar(audit, id)
                return copy.deepcopy(atual)

    def matrix_get(self, profile_id):
        """Retorna {'funcs': [...], 'ambs': [...], 'scrs': [...]} com os IDs associados."""
        with self._store.lock_rbac:
            if profile_id not in self._store.profiles:
                raise RepoNotFound("Perfil ID %s nao encontrado" % profile_id)

            funcs = [
                v["feature_id"]
                for v in self._store.profile_feature.values()
                if v["profile_id"] == profile_id
            ]
            ambs = [
                v["environment_id"]
                for v in self._store.profile_env.values()
                if v["profile_id"] == profile_id
            ]
            scrs = [
                v["script_id"]
                for v in self._store.profile_script.values()
                if v["profile_id"] == profile_id
            ]
            return {
                "funcs": copy.deepcopy(funcs),
                "ambs": copy.deepcopy(ambs),
                "scrs": copy.deepcopy(scrs),
            }

    def matrix_save(self, profile_id, features_ids, envs, scrs, expected_perm_version=None, audit=None, actor=None):
        """Substitui associacoes da matriz e incrementa perm_versao atomicamente (condicional a versao).

        Grava por diferenca: os vinculos que continuam mantem o created_*; havendo mudanca, o perfil
        recebe updated_* (CR-006, README §10).
        """
        with self._store.lock_rbac:
            with self._store.lock_catalog:
                actor = self._store.record_actor(audit, actor)
                if profile_id not in self._store.profiles:
                    raise RepoNotFound("Perfil ID %s nao encontrado" % profile_id)
                perfil = self._store.profiles[profile_id]
                if expected_perm_version is not None and perfil["perm_version"] != int(expected_perm_version):
                    raise RepoConflict("Matriz do perfil ID %s alterada por outra operacao" % profile_id)

                # FKs (paridade com o Oracle): valida tudo antes de remover qualquer associacao.
                features_ids = sorted(set(int(x) for x in (features_ids or [])))
                envs = sorted(set(int(x) for x in (envs or [])))
                scrs = sorted(set(int(x) for x in (scrs or [])))
                for ids, tabela, fk in ((features_ids, self._store.features, "fk_tbsss_pfea_fea"),
                                        (envs, self._store.environments, "fk_tbsss_penv_env"),
                                        (scrs, self._store.scripts, "fk_tbsss_pscr_scr")):
                    for x in ids:
                        if x not in tabela:
                            raise RepoViolation("ID %s inexistente" % x, constraint=fk)

                mudou = False
                for assoc, seq, coluna, ids in (
                        (self._store.profile_feature, "tbsss_profile_feature", "feature_id", features_ids),
                        (self._store.profile_env, "tbsss_profile_env", "environment_id", envs),
                        (self._store.profile_script, "tbsss_profile_script", "script_id", scrs)):
                    atuais = dict((v[coluna], k) for k, v in assoc.items() if v["profile_id"] == profile_id)
                    for x, k in atuais.items():
                        if x not in ids:
                            del assoc[k]
                    for x in ids:
                        if x not in atuais:
                            nid = self._store.next_id(seq)
                            assoc[nid] = self._store.stamp_insert(
                                {"id": nid, "profile_id": profile_id, coluna: x}, actor)
                    mudou = mudou or set(atuais) != set(ids)

                # Incrementa perm_versao atomicamente na mesma transacao
                perfil["perm_version"] += 1
                if mudou:
                    self._store.stamp_update(perfil, actor)
                self._auditar(audit, profile_id)
                return copy.deepcopy(self.matrix_get(profile_id))

    def lock_active_admins(self):
        """Retorna IDs dos administradores ativos conforme semantica do README §4.3.B."""
        with self._store.lock_rbac:
            with self._store.lock_users:
                return self._admins_ativos(self._store.profiles)

    def features_list(self):
        """Retorna lista do catalogo canonico de funcionalidades."""
        with self._store.lock_rbac:
            lista = list(self._store.features.values())
            lista.sort(key=lambda x: (x.get("module", ""), x.get("code", ""), x["id"]))
            return copy.deepcopy(lista)
