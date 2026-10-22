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
            items = list(self._store.profiles.values())

            name_f = filters.get("name")
            if name_f:
                items = [p for p in items if name_f.lower() in p["name"].lower()]

            active_f = filters.get("active")
            if active_f:
                items = [p for p in items if p["active"] == active_f]

            is_admin_f = filters.get("is_admin")
            if is_admin_f:
                items = [p for p in items if p["is_admin"] == is_admin_f]

            items.sort(key=lambda x: (x.get("name", ""), x["id"]))
            return paginate(items, page=page, size=size)

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
            name = date.get("name")
            if not name:
                raise RepoViolation("Nome de perfil e obrigatorio")

            for p in self._store.profiles.values():
                if p["name"].upper() == name.upper():
                    raise RepoViolation("Perfil com nome '%s' ja existe" % name, constraint="uk_tbsss_prf_name")

            is_admin = date.get("is_admin", "N")
            if is_admin not in ("Y", "N"):
                raise RepoViolation("Flag is_admin deve ser 'Y' ou 'N'", constraint="ck_tbsss_prf_adm")

            active = date.get("active", "Y")
            if active not in ("Y", "N"):
                raise RepoViolation("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_prf_active")

            pid = self._store.next_id("tbsss_profiles")
            new = {
                "id": pid,
                "name": name,
                "description": date.get("description", ""),
                "is_admin": is_admin,
                "perm_version": int(date.get("perm_version", 1)),
                "active": active,
            }
            self._store.stamp_insert(new, actor)
            self._store.profiles[pid] = copy.deepcopy(new)
            self._auditar(audit, pid)
            return copy.deepcopy(new)

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

                current = self._store.profiles[id]
                for field, value in (expected or {}).items():
                    if current.get(field) != value:
                        raise RepoConflict("Perfil ID %s alterado por outra operacao (%s)" % (id, field))

                changes = {}
                new_name = date.get("name")
                if new_name and new_name != current["name"]:
                    for pid, p in self._store.profiles.items():
                        if pid != id and p["name"].upper() == new_name.upper():
                            raise RepoViolation("Perfil com nome '%s' ja existe" % new_name,
                                               constraint="uk_tbsss_prf_name")
                    changes["name"] = new_name

                if "description" in date:
                    changes["description"] = date["description"]

                for field, ck in (("is_admin", "ck_tbsss_prf_adm"), ("active", "ck_tbsss_prf_active")):
                    if field in date:
                        if date[field] not in ("Y", "N"):
                            raise RepoViolation("Flag %s deve ser 'Y' ou 'N'" % field, constraint=ck)
                        changes[field] = date[field]

                reduces_admin = current["is_admin"] == "Y" and current["active"] == "Y" and (
                    changes.get("is_admin") == "N" or changes.get("active") == "N")
                if reduces_admin:
                    resulting = dict(self._store.profiles)
                    resulting[id] = dict(current, **changes)
                    if not self._admins_ativos(resulting):
                        raise RepoViolation("Operacao deixaria o sistema sem administrador ativo",
                                           constraint="sss_ultimo_admin")

                current.update(changes)
                # Toda alteracao de perfil incrementa perm_versao (README §4.3.A)
                current["perm_version"] = int(current.get("perm_version", 1)) + 1
                self._store.stamp_update(current, actor)
                self._auditar(audit, id)
                return copy.deepcopy(current)

    def matrix_get(self, profile_id):
        """Retorna {'funcs': [...], 'ambs': [...], 'scrs': [...]} com os IDs associados."""
        with self._store.lock_rbac:
            if profile_id not in self._store.profiles:
                raise RepoNotFound("Perfil ID %s nao encontrado" % profile_id)

            features = [
                v["feature_id"]
                for v in self._store.profile_feature.values()
                if v["profile_id"] == profile_id
            ]
            envs = [
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
                "funcs": copy.deepcopy(features),
                "ambs": copy.deepcopy(envs),
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
                profile = self._store.profiles[profile_id]
                if expected_perm_version is not None and profile["perm_version"] != int(expected_perm_version):
                    raise RepoConflict("Matriz do perfil ID %s alterada por outra operacao" % profile_id)

                # FKs (paridade com o Oracle): valida tudo antes de remover qualquer associacao.
                features_ids = sorted(set(int(x) for x in (features_ids or [])))
                envs = sorted(set(int(x) for x in (envs or [])))
                scrs = sorted(set(int(x) for x in (scrs or [])))
                for ids, table, fk in ((features_ids, self._store.features, "fk_tbsss_pfea_fea"),
                                        (envs, self._store.environments, "fk_tbsss_penv_env"),
                                        (scrs, self._store.scripts, "fk_tbsss_pscr_scr")):
                    for x in ids:
                        if x not in table:
                            raise RepoViolation("ID %s inexistente" % x, constraint=fk)

                changed = False
                for assoc, seq, column, ids in (
                        (self._store.profile_feature, "tbsss_profile_feature", "feature_id", features_ids),
                        (self._store.profile_env, "tbsss_profile_env", "environment_id", envs),
                        (self._store.profile_script, "tbsss_profile_script", "script_id", scrs)):
                    current = dict((v[column], k) for k, v in assoc.items() if v["profile_id"] == profile_id)
                    for x, k in current.items():
                        if x not in ids:
                            del assoc[k]
                    for x in ids:
                        if x not in current:
                            nid = self._store.next_id(seq)
                            assoc[nid] = self._store.stamp_insert(
                                {"id": nid, "profile_id": profile_id, column: x}, actor)
                    changed = changed or set(current) != set(ids)

                # Incrementa perm_versao atomicamente na mesma transacao
                profile["perm_version"] += 1
                if changed:
                    self._store.stamp_update(profile, actor)
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
            items = list(self._store.features.values())
            items.sort(key=lambda x: (x.get("module", ""), x.get("code", ""), x["id"]))
            return copy.deepcopy(items)
