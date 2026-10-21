# -*- coding: utf-8 -*-
"""Tela "O que eu posso fazer" (README §4.3.E, CR-004 T1): o que o perfil libera, em linguagem simples.

So leitura: nao grava nem audita. A regra de execucao e a do disparo (rbac.pode_executar via
ticket_service), para que a tela nunca diga algo diferente do que o disparo faz.
Nao importa gluon fora de _servico.
"""
import threading

import rbac
import ui_menu
from repo_errors import RepoNaoEncontrado

FRASE_ADMIN = (u"Seu perfil é de administrador: você pode usar todas as telas e rodar qualquer script ativo, "
               u"nos ambientes ativos onde ele foi liberado.")
FRASE_SEM_EXEC = u"Você ainda não pode rodar scripts. Peça ao administrador, se precisar."
FRASE_MAIS_ACESSO = u"Precisa de mais acesso? Fale com o administrador do sistema."
MOTIVO_SCRIPT_INATIVO = u"o script está desativado"
MOTIVO_SEM_HOMOLOGACAO = u"o script não foi liberado em nenhum dos seus ambientes"
MOTIVO_AMBIENTE_INATIVO = u"o ambiente está desativado"
MOTIVO_SEM_FUNC = u"seu perfil não tem Disparar Scripts"
_CATALOGO_MAX = 1000


class ServicoPermissoes(object):
    """Monta a tela a partir do contexto revalidado da sessao e das leituras do catalogo."""

    def __init__(self, rbac_repo, catalogo, disparo, log):
        self._rbac = rbac_repo
        self._catalogo = catalogo
        self._disparo = disparo
        self._log = log

    def _telas(self, ctx):
        admin = ctx.get("is_admin") is True
        rotas = {}
        for secao in ui_menu.montar_menu(ctx.get("funcionalidades"), admin):
            for item in secao["itens"]:
                # Ultimo item vence: EXEC_SCRIPT ("Disparar Scripts") leva ao disparo, nao ao catalogo.
                rotas[item["code"]] = item["rota"]
        telas = []
        for f in self._rbac.funcionalidades_listar():
            if f.get("active") != "Y" or not (admin or f["code"] in (ctx.get("funcionalidades") or ())):
                continue
            telas.append({"code": f["code"], "name": f["name"], "finalidade": f.get("description") or "",
                          "rota": rotas.get(f["code"])})
        return telas

    def _ambientes(self, ctx):
        admin = ctx.get("is_admin") is True
        meus = ctx.get("ambientes") or ()
        return [{"name": a["name"], "description": a.get("description") or ""}
                for a in self._catalogo.ambientes_listar(pagina=1, tamanho=_CATALOGO_MAX)["itens"]
                if a["active"] == "Y" and (admin or a["name"] in meus)]

    def _scripts(self, ctx):
        scripts = []
        for grupo in self._disparo.scripts_disponiveis(ctx):
            for s in grupo["scripts"]:
                _script, ambientes = self._disparo.ambientes_disponiveis(ctx, s["id"])
                scripts.append({"id": s["id"], "name": s["name"], "description": s["description"],
                                "ambientes": [a["name"] for a in ambientes]})
        return scripts

    def _motivo(self, ctx, script_id):
        """Motivo simples de um script do perfil nao aparecer (README §4.3.E)."""
        try:
            script = self._catalogo.scripts_obter(script_id)
        except RepoNaoEncontrado:
            return None, None
        if script.get("active") != "Y":
            return script, MOTIVO_SCRIPT_INATIVO
        meus = set(ctx.get("ambientes") or ())
        homologados = []
        for aid in self._catalogo.homologacao_obter(script["id"]):
            try:
                homologados.append(self._catalogo.ambientes_obter(aid))
            except RepoNaoEncontrado:
                continue
        nos_meus = [a for a in homologados if a["name"] in meus]
        if not nos_meus:
            return script, MOTIVO_SEM_HOMOLOGACAO
        if all(a.get("active") != "Y" for a in nos_meus):
            return script, MOTIVO_AMBIENTE_INATIVO
        return script, MOTIVO_SCRIPT_INATIVO if script.get("active") != "Y" else None

    def montar(self, ctx):
        """Dados da tela. Scripts fora do perfil nunca sao listados (nao revela o catalogo)."""
        admin = ctx.get("is_admin") is True
        pode_exec = rbac.tem_func(ctx, "EXEC_SCRIPT")
        scripts = self._scripts(ctx) if pode_exec else []
        disponiveis = set(s["id"] for s in scripts)
        ausentes = []
        if not admin:
            for sid in sorted(ctx.get("scripts") or ()):
                if sid in disponiveis:
                    continue
                script, motivo = self._motivo(ctx, sid)
                if script is None:
                    continue
                ausentes.append({"name": script["name"],
                                 "reason": MOTIVO_SEM_FUNC if not pode_exec else (motivo or MOTIVO_SEM_HOMOLOGACAO)})
        return {
            "perfil": ctx.get("perfil_nome"),
            "frase_admin": FRASE_ADMIN if admin else None,
            "telas": self._telas(ctx),
            "ambientes": self._ambientes(ctx),
            "pode_executar": pode_exec,
            "frase_sem_exec": None if pode_exec else FRASE_SEM_EXEC,
            "scripts": scripts,
            "ausentes": ausentes,
            "frase_mais_acesso": FRASE_MAIS_ACESSO,
        }


_padrao = None
_lock_padrao = threading.Lock()


def _servico():
    global _padrao
    with _lock_padrao:
        if _padrao is None:
            from gluon import current
            import sss_logging
            import ticket_service
            fabrica = current.repo_factory
            _padrao = ServicoPermissoes(
                rbac_repo=fabrica.obter("rbac"),
                catalogo=fabrica.obter("catalogo"),
                disparo=ticket_service._servico(),
                log=sss_logging.obter_logger("sss_web", current.sss_cfg),
            )
        return _padrao


def montar(ctx):
    """Dados da tela "O que eu posso fazer" (servico padrao)."""
    return _servico().montar(ctx)
