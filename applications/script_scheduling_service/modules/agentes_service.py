# -*- coding: utf-8 -*-
"""Painel somente leitura dos agentes executores (README §4.3.D VER_AUDITORIA, §8.7-8.9, §13).

A saude e derivada da idade do heartbeat medida pelo relogio do banco (SYSDATE), nunca
pelo relogio do no web, com os mesmos limiares do daemon (README §8.8 e §8.9).
"""
import collections
import threading

import admin_crud
import ui_helpers
from admin_crud import AcessoNegado  # noqa: F401  (reexportado para o controller)

FUNCIONALIDADE = "VER_AUDITORIA"

OK = "OK"
ATRASADO = "ATRASADO"
EM_RISCO = "EM_RISCO"
OFFLINE = "OFFLINE"
ORDEM_SAUDE = (OK, ATRASADO, EM_RISCO, OFFLINE)

# codigo -> (rotulo, classe do badge, icone, explicacao da legenda); cor + icone + texto.
_SAUDE = {
    OK: (u"OK", "sss-status-success", "status-success",
         u"Heartbeat recente: menos de 2 intervalos de heartbeat."),
    ATRASADO: (u"Atrasado", "sss-status-pending", "status-pending",
               u"Heartbeat atrasado, ainda dentro do tempo de autoproteção (fence) do agente."),
    EM_RISCO: (u"Em risco", "sss-status-failed", "icon-alert",
               u"O agente já deve ter se isolado (fence); se o atraso passar do limite de nó offline, "
               u"outro agente encerrará os tickets dele."),
    OFFLINE: (u"Offline", "sss-status-cancelled", "status-cancelled",
              u"Sem heartbeat além do limite de nó offline, ou agente parado."),
}

Limiares = collections.namedtuple("Limiares", "heartbeat_interval_s fence_timeout_s node_offline_timeout_s")


def saude(agente, agora, limiares):
    """Codigo de saude do agente: OK, ATRASADO, EM_RISCO ou OFFLINE.

    OK: idade < 2 x heartbeat_interval_s; ATRASADO: ate fence_timeout_s; EM_RISCO: ate
    node_offline_timeout_s; OFFLINE: alem disso, sem heartbeat ou com status PARADO.
    """
    if agente.get("status") == "PARADO":
        return OFFLINE
    hb = agente.get("heartbeat_at")
    if hb is None:
        return OFFLINE
    idade = max(0, int((agora - hb).total_seconds()))
    if idade < 2 * limiares.heartbeat_interval_s:
        return OK
    if idade <= limiares.fence_timeout_s:
        return ATRASADO
    if idade <= limiares.node_offline_timeout_s:
        return EM_RISCO
    return OFFLINE


def saude_info(codigo):
    """{codigo, rotulo, classe, icone, descricao} da saude, para badge e legenda."""
    rotulo, classe, icone, descricao = _SAUDE[codigo]
    return {"codigo": codigo, "rotulo": rotulo, "classe": classe, "icone": icone, "descricao": descricao}


def legenda():
    """Estados de saude na ordem do melhor para o pior."""
    return [saude_info(c) for c in ORDEM_SAUDE]


def formatar_idade(segundos):
    """'há N s' ate 2 min; depois minutos, horas ou dias inteiros; None vira 'sem heartbeat'."""
    if segundos is None:
        return u"sem heartbeat"
    if segundos < 120:
        return u"há %d s" % segundos
    if segundos < 7200:
        return u"há %d min" % (segundos // 60)
    if segundos < 172800:
        return u"há %d h" % (segundos // 3600)
    return u"há %d dias" % (segundos // 86400)


class ServicoAgentes(object):
    """Painel de agentes com repositorios, relogio, limiares e log injetados."""

    def __init__(self, agentes, catalogo, relogio, limiares, log):
        self._agentes = agentes
        self._catalogo = catalogo
        self._relogio = relogio
        self._limiares = limiares
        self._log = log

    def _nomes_scripts(self):
        pagina = self._catalogo.scripts_listar(pagina=1, tamanho=1000)
        return dict((s["id"], s["nome"]) for s in pagina["itens"])

    def _tickets(self, codigo, agora, nomes):
        itens = []
        for t in self._agentes.tickets_running(codigo):
            hb = t.get("heartbeat_at")
            itens.append({
                "id": t["id"],
                "script_nome": nomes.get(t.get("script_id"), u"#%s" % t.get("script_id")),
                "ambiente": t.get("ambiente"),
                "solicitante": t.get("solicitante"),
                "started_at": t.get("started_at"),
                "duracao": ui_helpers.formatar_duracao(t.get("started_at"), agora),
                "heartbeat": formatar_idade(None if hb is None else max(0, int((agora - hb).total_seconds()))),
            })
        return itens

    def tickets_do_agente(self, ctx, codigo, agora=None):
        """Tickets RUNNING do agente, prontos para a lista com link para o detalhe."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        agora = agora or self._relogio()
        return self._tickets(codigo, agora, self._nomes_scripts())

    def painel(self, ctx, agora=None):
        """Agentes com saude derivada, idade do heartbeat e tickets RUNNING (somente leitura).

        Retorna {"agentes": [...], "resumo": {codigo_saude: quantidade}, "agora": datetime}.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        agora = agora or self._relogio()
        nomes = self._nomes_scripts()
        resumo = collections.OrderedDict((c, 0) for c in ORDEM_SAUDE)
        agentes = []
        for ag in self._agentes.listar():
            hb = ag.get("heartbeat_at")
            idade = None if hb is None else max(0, int((agora - hb).total_seconds()))
            codigo_saude = saude(ag, agora, self._limiares)
            resumo[codigo_saude] += 1
            tickets = self._tickets(ag["codigo"], agora, nomes)
            agentes.append({
                "codigo": ag["codigo"],
                "hostname": ag.get("hostname"),
                "status": ag.get("status"),
                "versao": ag.get("versao"),
                "plataforma": ag.get("plataforma"),
                "ambientes": [a for a in (ag.get("ambientes") or "").split(",") if a],
                "iniciado_em": ag.get("iniciado_em"),
                "heartbeat_at": hb,
                "idade_s": idade,
                "ha": formatar_idade(idade),
                "saude": saude_info(codigo_saude),
                "running": len(tickets),
                "tickets": tickets,
            })
        return {"agentes": agentes, "resumo": resumo, "agora": agora}


_padrao = None
_lock_padrao = threading.Lock()


def _servico():
    global _padrao
    with _lock_padrao:
        if _padrao is None:
            from gluon import current
            import sss_logging
            fabrica = current.repo_factory
            cfg = current.sss_cfg
            _padrao = ServicoAgentes(
                agentes=fabrica.obter("agentes"),
                catalogo=fabrica.obter("catalogo"),
                relogio=fabrica.obter("tickets").agora,
                limiares=Limiares(cfg.agent.heartbeat_interval_s, cfg.agent.fence_timeout_s,
                                  cfg.agent.node_offline_timeout_s),
                log=sss_logging.obter_logger("sss_web", cfg),
            )
        return _padrao


def painel(ctx, agora=None):
    """Painel de agentes (servico padrao)."""
    return _servico().painel(ctx, agora)


def tickets_do_agente(ctx, codigo, agora=None):
    """Tickets RUNNING do agente (servico padrao)."""
    return _servico().tickets_do_agente(ctx, codigo, agora)
