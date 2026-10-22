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

    def __init__(self, rbac_repo, catalogo, disparo, log):
        self._rbac = rbac_repo
        self._catalog = catalogo
        self._trigger_service = disparo
        self._log = log

    def _screens(self, ctx):
        admin = ctx.get("is_admin") is True
        rotas = {}
        for secao in ui_menu.montar_menu(ctx.get("features"), admin):
            for item in secao["itens"]:
                # Ultimo item vence: EXEC_SCRIPT ("Disparar Scripts") leva ao disparo, nao ao catalogo.
                rotas[item["code"]] = item["rota"]
        telas = []
        for f in self._rbac.features_list():
            if f.get("active") != "Y" or not (admin or f["code"] in (ctx.get("features") or ())):
                continue
            telas.append({"code": f["code"], "name": f["name"], "finalidade": f.get("description") or "",
                          "rota": rotas.get(f["code"])})
        return telas

    def _environments(self, ctx):
        admin = ctx.get("is_admin") is True
        meus = ctx.get("environments") or ()
        return [{"name": a["name"], "description": a.get("description") or ""}
                for a in self._catalog.environments_list(pagina=1, tamanho=_CATALOG_MAX)["itens"]
                if a["active"] == "Y" and (admin or a["name"] in meus)]

    def _scripts(self, ctx):
        scripts = []
        for grupo in self._trigger_service.available_scripts(ctx):
            for s in grupo["scripts"]:
                _script, ambientes = self._trigger_service.available_environments(ctx, s["id"])
                scripts.append({"id": s["id"], "name": s["name"], "description": s["description"],
                                "environments": [a["name"] for a in ambientes]})
        return scripts

    def _reason(self, ctx, script_id):
        """Motivo simples de um script do perfil nao aparecer (README §4.3.E)."""
        try:
            script = self._catalog.scripts_get(script_id)
        except RepoNotFound:
            return None, None
        if script.get("active") != "Y":
            return script, REASON_SCRIPT_INACTIVE
        meus = set(ctx.get("environments") or ())
        homologados = []
        for aid in self._catalog.homologation_get(script["id"]):
            try:
                homologados.append(self._catalog.environments_get(aid))
            except RepoNotFound:
                continue
        nos_meus = [a for a in homologados if a["name"] in meus]
        if not nos_meus:
            return script, REASON_NOT_HOMOLOGATED
        if all(a.get("active") != "Y" for a in nos_meus):
            return script, REASON_ENVIRONMENT_INACTIVE
        return script, REASON_SCRIPT_INACTIVE if script.get("active") != "Y" else None

    def build(self, ctx):
        """Dados da tela. Scripts fora do perfil nunca sao listados (nao revela o catalogo)."""
        admin = ctx.get("is_admin") is True
        pode_exec = rbac.has_feature(ctx, "EXEC_SCRIPT")
        scripts = self._scripts(ctx) if pode_exec else []
        disponiveis = set(s["id"] for s in scripts)
        ausentes = []
        if not admin:
            for sid in sorted(ctx.get("scripts") or ()):
                if sid in disponiveis:
                    continue
                script, motivo = self._reason(ctx, sid)
                if script is None:
                    continue
                ausentes.append({"name": script["name"],
                                 "reason": REASON_NO_FEATURE if not pode_exec else (motivo or REASON_NOT_HOMOLOGATED)})
        return {
            "perfil": ctx.get("perfil_nome"),
            "frase_admin": ADMIN_PHRASE if admin else None,
            "telas": self._screens(ctx),
            "environments": self._environments(ctx),
            "pode_executar": pode_exec,
            "frase_sem_exec": None if pode_exec else NO_EXEC_PHRASE,
            "scripts": scripts,
            "ausentes": ausentes,
            "frase_mais_acesso": MORE_ACCESS_PHRASE,
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
            fabrica = current.repo_factory
            _default = PermissionsService(
                rbac_repo=fabrica.get("rbac"),
                catalogo=fabrica.get("catalog"),
                disparo=ticket_service._service(),
                log=sss_logging.get_logger("sss_web", current.sss_cfg),
            )
        return _default


def build(ctx):
    """Dados da tela "O que eu posso fazer" (servico padrao)."""
    return _service().build(ctx)
