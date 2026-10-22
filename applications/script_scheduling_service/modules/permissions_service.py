# -*- coding: utf-8 -*-
"""Tela "O que eu posso fazer" (README §4.3.E, CR-004 T1): o que o perfil libera, em linguagem simples.

So leitura: nao grava nem audita. A regra de execucao e a do disparo (rbac.can_execute via
ticket_service), para que a tela nunca diga algo diferente do que o disparo faz.
Nao importa gluon fora de _servico.
"""
import threading

import rbac
import ui_menu
from repo_errors import RepoNotFound

ADMIN_PHRASE = (u"Seu perfil é de administrador: você pode usar todas as telas e rodar qualquer script ativo, "
               u"nos ambientes ativos onde ele foi liberado.")
NO_EXEC_PHRASE = u"Você ainda não pode rodar scripts. Peça ao administrador, se precisar."
MORE_ACCESS_PHRASE = u"Precisa de mais acesso? Fale com o administrador do sistema."
REASON_SCRIPT_INACTIVE = u"o script está desativado"
REASON_NOT_HOMOLOGATED = u"o script não foi liberado em nenhum dos seus ambientes"
REASON_ENVIRONMENT_INACTIVE = u"o ambiente está desativado"
REASON_NO_FEATURE = u"seu perfil não tem Disparar Scripts"
_CATALOG_MAX = 1000


class PermissionsService(object):
    """Monta a tela a partir do contexto revalidado da sessao e das leituras do catalogo."""

    def __init__(self, rbac_repo, catalog, trigger_service, log):
        self._rbac = rbac_repo
        self._catalog = catalog
        self._trigger_service = trigger_service
        self._log = log

    def _screens(self, ctx):
        admin = ctx.get("is_admin") is True
        routes = {}
        for section in ui_menu.build_menu(ctx.get("features"), admin):
            for item in section["items"]:
                # Ultimo item vence: EXEC_SCRIPT ("Disparar Scripts") leva ao disparo, nao ao catalogo.
                routes[item["code"]] = item["route"]
        screens = []
        for f in self._rbac.features_list():
            if f.get("active") != "Y" or not (admin or f["code"] in (ctx.get("features") or ())):
                continue
            screens.append({"code": f["code"], "name": f["name"], "purpose": f.get("description") or "",
                          "route": routes.get(f["code"])})
        return screens

    def _environments(self, ctx):
        admin = ctx.get("is_admin") is True
        mine = ctx.get("environments") or ()
        return [{"name": a["name"], "description": a.get("description") or ""}
                for a in self._catalog.environments_list(page=1, size=_CATALOG_MAX)["items"]
                if a["active"] == "Y" and (admin or a["name"] in mine)]

    def _scripts(self, ctx):
        scripts = []
        for group in self._trigger_service.available_scripts(ctx):
            for s in group["scripts"]:
                _script, environments = self._trigger_service.available_environments(ctx, s["id"])
                scripts.append({"id": s["id"], "name": s["name"], "description": s["description"],
                                "environments": [a["name"] for a in environments]})
        return scripts

    def _reason(self, ctx, script_id):
        """Motivo simples de um script do perfil nao aparecer (README §4.3.E)."""
        try:
            script = self._catalog.scripts_get(script_id)
        except RepoNotFound:
            return None, None
        if script.get("active") != "Y":
            return script, REASON_SCRIPT_INACTIVE
        mine = set(ctx.get("environments") or ())
        homologated = []
        for aid in self._catalog.homologation_get(script["id"]):
            try:
                homologated.append(self._catalog.environments_get(aid))
            except RepoNotFound:
                continue
        in_mine = [a for a in homologated if a["name"] in mine]
        if not in_mine:
            return script, REASON_NOT_HOMOLOGATED
        if all(a.get("active") != "Y" for a in in_mine):
            return script, REASON_ENVIRONMENT_INACTIVE
        return script, REASON_SCRIPT_INACTIVE if script.get("active") != "Y" else None

    def build(self, ctx):
        """Dados da tela. Scripts fora do perfil nunca sao listados (nao revela o catalogo)."""
        admin = ctx.get("is_admin") is True
        can_exec = rbac.has_feature(ctx, "EXEC_SCRIPT")
        scripts = self._scripts(ctx) if can_exec else []
        available = set(s["id"] for s in scripts)
        missing = []
        if not admin:
            for sid in sorted(ctx.get("scripts") or ()):
                if sid in available:
                    continue
                script, reason = self._reason(ctx, sid)
                if script is None:
                    continue
                missing.append({"name": script["name"],
                                 "reason": REASON_NO_FEATURE if not can_exec else (reason or REASON_NOT_HOMOLOGATED)})
        return {
            "profile": ctx.get("profile_name"),
            "admin_phrase": ADMIN_PHRASE if admin else None,
            "screens": self._screens(ctx),
            "environments": self._environments(ctx),
            "can_execute": can_exec,
            "no_runs_phrase": None if can_exec else NO_EXEC_PHRASE,
            "scripts": scripts,
            "absent": missing,
            "more_access_phrase": MORE_ACCESS_PHRASE,
        }


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from gluon import current
            import sss_logging
            import ticket_service
            factory = current.repo_factory
            _default = PermissionsService(
                rbac_repo=factory.get("rbac"),
                catalog=factory.get("catalog"),
                trigger_service=ticket_service._service(),
                log=sss_logging.get_logger("sss_web", current.sss_cfg),
            )
        return _default


def build(ctx):
    """Dados da tela "O que eu posso fazer" (servico padrao)."""
    return _service().build(ctx)
