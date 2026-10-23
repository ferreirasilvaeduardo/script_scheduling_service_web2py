# -*- coding: utf-8 -*-
"""Painel somente leitura dos agentes executores (README §4.3.D VIEW_AUDIT, §8.7-8.9, §13).

A saude e derivada da idade do heartbeat medida pelo relogio do banco (SYSDATE), nunca
pelo relogio do no web, com os mesmos limiares do daemon (README §8.8 e §8.9).
"""
import collections
import threading

import admin_crud
import ui_helpers
from admin_crud import AccessDenied  # noqa: F401  (reexportado para o controller)

FEATURE = "VIEW_AUDIT"

OK = "OK"
DELAYED = "DELAYED"
AT_RISK = "AT_RISK"
OFFLINE = "OFFLINE"
HEALTH_ORDER = (OK, DELAYED, AT_RISK, OFFLINE)

# codigo -> (rotulo, classe do badge, icone, explicacao da legenda); cor + icone + texto.
_HEALTH = {
    OK: (u"OK", "sss-status-success", "status-success",
         u"Heartbeat recente: menos de 2 intervalos de heartbeat."),
    DELAYED: (u"Atrasado", "sss-status-pending", "status-pending",
               u"Heartbeat atrasado, ainda dentro do tempo de autoproteção (fence) do agente."),
    AT_RISK: (u"Em risco", "sss-status-failed", "icon-alert",
               u"O agente já deve ter se isolado (fence); se o atraso passar do limite de nó offline, "
               u"outro agente encerrará os tickets dele."),
    OFFLINE: (u"Offline", "sss-status-cancelled", "status-cancelled",
              u"Sem heartbeat além do limite de nó offline, ou agente parado."),
}

Thresholds = collections.namedtuple("Thresholds", "heartbeat_interval_s fence_timeout_s node_offline_timeout_s")


def health(agent, now, thresholds):
    """Codigo de saude do agente: OK, DELAYED, AT_RISK ou OFFLINE.

    OK: idade < 2 x heartbeat_interval_s; DELAYED: ate fence_timeout_s; AT_RISK: ate
    node_offline_timeout_s; OFFLINE: alem disso, sem heartbeat ou com status PARADO.
    """
    if agent.get("status") == "STOPPED":
        return OFFLINE
    hb = agent.get("heartbeat_at")
    if hb is None:
        return OFFLINE
    age = max(0, int((now - hb).total_seconds()))
    if age < 2 * thresholds.heartbeat_interval_s:
        return OK
    if age <= thresholds.fence_timeout_s:
        return DELAYED
    if age <= thresholds.node_offline_timeout_s:
        return AT_RISK
    return OFFLINE


def health_info(code):
    """{code, label, css_class, icon, description} da saude, para badge e legenda."""
    label, cls_name, icon, description = _HEALTH[code]
    return {"code": code, "label": label, "css_class": cls_name, "icon": icon, "description": description}


def legend():
    """Estados de saude na ordem do melhor para o pior."""
    return [health_info(c) for c in HEALTH_ORDER]


def format_age(seconds):
    """'há N s' ate 2 min; depois minutos, horas ou dias inteiros; None vira 'sem heartbeat'."""
    if seconds is None:
        return u"sem heartbeat"
    if seconds < 120:
        return u"há %d s" % seconds
    if seconds < 7200:
        return u"há %d min" % (seconds // 60)
    if seconds < 172800:
        return u"há %d h" % (seconds // 3600)
    return u"há %d dias" % (seconds // 86400)


class AgentsService(object):
    """Painel de agentes com repositorios, relogio, limiares e log injetados."""

    def __init__(self, agents, catalog, clock, thresholds, log, config_criticos):
        self._agents = agents
        self._catalog = catalog
        self._clock = clock
        self._thresholds = thresholds
        self._log = log
        self._critical_config = config_criticos

    def _script_names(self):
        page = self._catalog.scripts_list(page=1, size=1000)
        return dict((s["id"], s["name"]) for s in page["items"])

    def _tickets(self, code, now, names):
        items = []
        for t in self._agents.tickets_running(code):
            hb = t.get("heartbeat_at")
            items.append({
                "id": t["id"],
                "script_name": names.get(t.get("script_id"), u"#%s" % t.get("script_id")),
                "environment": t.get("environment"),
                "requested_by": t.get("requested_by"),
                "started_at": t.get("started_at"),
                "duration": ui_helpers.format_duration(t.get("started_at"), now),
                "heartbeat": format_age(None if hb is None else max(0, int((now - hb).total_seconds()))),
            })
        return items

    def agent_tickets(self, ctx, code, now=None):
        """Tickets RUNNING do agente, prontos para a lista com link para o detalhe."""
        admin_crud.require_feature(ctx, FEATURE)
        now = now or self._clock()
        return self._tickets(code, now, self._script_names())

    def dashboard(self, ctx, now=None):
        """Agentes com saude derivada, idade do heartbeat e tickets RUNNING (somente leitura).

        Retorna {"agents": [...], "summary": {codigo de saude: quantidade}, "now": datetime}.
        """
        admin_crud.require_feature(ctx, FEATURE)
        now = now or self._clock()
        names = self._script_names()
        summary = collections.OrderedDict((c, 0) for c in HEALTH_ORDER)
        agents = []
        divergent = []
        for ag in self._agents.list():
            if ag.get("status") == "ACTIVE" and ag.get("critical_config") != self._critical_config:
                divergent.append({"code": ag["code"], "critical_config": ag.get("critical_config")})
            hb = ag.get("heartbeat_at")
            age = None if hb is None else max(0, int((now - hb).total_seconds()))
            code_health = health(ag, now, self._thresholds)
            summary[code_health] += 1
            tickets = self._tickets(ag["code"], now, names)
            agents.append({
                "code": ag["code"],
                "hostname": ag.get("hostname"),
                "status": ag.get("status"),
                "version": ag.get("version"),
                "platform": ag.get("platform"),
                "environments": [a for a in (ag.get("environments") or "").split(",") if a],
                "interpreters": [i for i in (ag.get("interpreters") or "").split(",") if i],
                # So os nomes logicos: os caminhos locais nunca vao para a tela (README §13).
                "started_at": ag.get("started_at"),
                "heartbeat_at": hb,
                "age_s": age,
                "ago": format_age(age),
                "health": health_info(code_health),
                "running": len(tickets),
                "tickets": tickets,
            })
        return {"agents": agents, "summary": summary, "now": now,
                "unattended_queue": self._agents.unattended_queue(now, self._thresholds),
                "running_without_pid": self._agents.running_without_pid(now, 2),
                "config_mismatch": divergent, "config_web": self._critical_config}


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from gluon import current
            import sss_logging
            import sss_config
            factory = current.repo_factory
            cfg = current.sss_cfg
            _default = AgentsService(
                agents=factory.get("agents"),
                catalog=factory.get("catalog"),
                clock=factory.get("tickets").now,
                thresholds=Thresholds(cfg.agent.heartbeat_interval_s, cfg.agent.fence_timeout_s,
                                  cfg.agent.node_offline_timeout_s),
                log=sss_logging.get_logger("sss_web", cfg),
                config_criticos=sss_config.critical_config(cfg),
            )
        return _default


def dashboard(ctx, now=None):
    """Painel de agentes (servico padrao)."""
    return _service().dashboard(ctx, now)


def agent_tickets(ctx, code, now=None):
    """Tickets RUNNING do agente (servico padrao)."""
    return _service().agent_tickets(ctx, code, now)
