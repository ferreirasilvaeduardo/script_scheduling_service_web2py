# -*- coding: utf-8 -*-
"""Desdobro dos agendamentos no agente (README §7.4 e §7.5; F8.4b; CR-003 D1-D3; CR-006; CR-007 R-05, R-08, R-19,
R-26, R-27; CR-008 R-03, R-19, R-21, R-22, R-31, R-33).

Uma transacao por regra, sem espera: trava (SKIP LOCKED), le, revalida o responsavel, decide (recurrence), confere
a sobreposicao, compila o snapshot v4 e reserva/conclui/pausa pelo repo_oracle/scheduler_agenda, com o COMMIT unico
aqui (passo 8). Uma regra com defeito nunca trava as demais: erro de banco conta falhas seguidas (3a pausa
INTERNAL_ERROR), outra excecao pausa INTERNAL_ERROR numa transacao separada. Paginacao com orcamento de tempo.
Python puro, sem gluon; o log permite reconstruir cada decisao sem o banco.
"""
import json
import logging

import db_conn
import params_compiler
import rbac
import recurrence
from repo_oracle.scheduler_schedules import DuplicateOccurrence

_log = logging.getLogger("sss_scheduler")

FAILURES_BEFORE_PAUSE = 3
_BUSY = ("PENDING", "RUNNING")
_DETAIL_MAX = 900


def _answer_text(value):
    """Mesma forma do ticket manual (ticket_service): CHECKBOX vira 'true'/'false'."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    return value


def _short(text):
    text = " ".join(str(text).split())
    return text if len(text) <= _DETAIL_MAX else text[:_DETAIL_MAX - 3] + "..."


def is_db_error(exc):
    """Erro do contrato do banco (ORA/DPY/DPI, rede ou prazo): nova tentativa no ciclo seguinte (R-22)."""
    pfx, _num = db_conn.classify_error(exc)
    return pfx is not None or db_conn.is_network_error(exc) or db_conn.is_timeout(exc)


class Expansion(object):
    """Ciclo de desdobro de um agente. As falhas seguidas por regra ficam em memoria (zeradas no sucesso)."""

    def __init__(self, schedule_repo, queue, agent_id, agent_cfg, clock, log=None, horizon_days=None):
        self.agenda = schedule_repo
        self.queue = queue
        self.agent_id = agent_id
        self.cfg = agent_cfg
        self.clock = clock
        self.log = log or _log
        self.horizon = horizon_days or agent_cfg.cron_horizon_days
        self.failures = {}

    # ------------------------------------------------------------------ ciclo

    def run(self, conn, keep_going=None):
        """Paginas de regras vencidas ate vir uma incompleta ou gastar heartbeat_interval_s / 2 (R-08).

        continuar(): False interrompe entre regras (fencing ou parada). Devolve contadores do ciclo.
        """
        inicio = self.clock()
        orcamento = self.cfg.heartbeat_interval_s / 2.0
        lote = self.cfg.schedule_batch_size
        ult_prox, ult_id = None, 0
        ignoradas = set()
        stats = {"regras": 0, "tickets": 0, "pausas": 0, "puladas": 0}
        while True:
            pagina = self.agenda.due_rules(conn, lote, ult_prox, ult_id)
            conn.rollback()  # a leitura nao trava nada; cada regra abre a propria transacao
            for regra_id, prox in pagina:
                if (keep_going is not None and not keep_going()) or self.clock() - inicio > orcamento:
                    return stats
                ult_prox, ult_id = prox, regra_id
                if regra_id in ignoradas:
                    continue
                stats["regras"] += 1
                desfecho = self.process(conn, regra_id)
                if desfecho == "IGNORAR":
                    ignoradas.add(regra_id)
                elif desfecho in ("TICKET", "CONCLUIDA_COM_TICKET", "CRON_INVALIDO_COM_TICKET"):
                    stats["tickets"] += 1
                if desfecho in ("PAUSADA", "INVALID_CRON", "CRON_INVALIDO_COM_TICKET", "INTERNAL_ERROR"):
                    stats["pausas"] += 1
                if desfecho == "OUTRO_AGENTE":
                    stats["puladas"] += 1
            if len(pagina) < lote or self.clock() - inicio > orcamento:
                return stats

    # ------------------------------------------------------------------ uma regra

    def process(self, conn, rule_id):
        """Passos 1 a 8 do README §7.5 numa transacao. Devolve o desfecho (texto, para o log e os testes)."""
        log = _RuleLog(self.log, self.agent_id, rule_id)
        self._current_rule = None
        try:
            desfecho = self._process(conn, rule_id, log)
        except DuplicateOccurrence:
            conn.rollback()
            return self._duplicate_occurrence(conn, rule_id, log)
        except Exception as exc:  # noqa: BLE001 - nenhuma regra derruba o ciclo (R-08, R-22)
            conn.rollback()
            return self._failure(conn, rule_id, exc, log)
        self.failures.pop(rule_id, None)
        return desfecho

    def _process(self, conn, rule_id, log):
        if not self.agenda.lock_rule(conn, rule_id):
            conn.rollback()
            return "OUTRO_AGENTE"
        regra = self.agenda.load_rule(conn, rule_id)
        if regra is None:
            conn.rollback()
            return "OUTRO_AGENTE"
        antiga = regra["next_run_at"]  # passo 1: exatamente como o banco devolveu
        agora = db_conn.db_now(conn)
        self._current_rule = regra

        # Passo 2: o responsavel ainda pode executar (motivo pela traducao unica, CR-008 R-33).
        login = self.agenda.user_login(conn, regra["user_id"])
        ctx_exec = self.queue.execution_context(conn, {"script_id": regra["script_id"], "environment": regra["environment"],
                                                      "requested_by": login})
        ok, motivo = rbac.can_execute(ctx_exec["ctx"], ctx_exec["script"], ctx_exec["environment"],
                                        ctx_exec["homologacoes"])
        if not ok:
            return self._pause(conn, regra, antiga, rbac.pause_reason_for(motivo), "rbac: %s" % motivo, log)
        prioridade = int(regra["priority"])
        if prioridade == 1 and not (ctx_exec["ctx"] or {}).get("is_admin"):
            prioridade = 2
            log.warning("PRIORIDADE_REBAIXADA: o responsavel %s deixou de ser admin; ticket com prioridade 2", login)

        # Passo 3: decisao (misfire pela vencida mais recente, CR-008 R-21).
        try:
            dec = recurrence.evaluate_trigger(regra, agora, self.cfg.misfire_policy, self.cfg.misfire_tolerance_s,
                                             self.horizon)
        except recurrence.CronError as exc:
            return self._pause(conn, regra, antiga, "INVALID_CRON", _short(exc), log)
        self._log_missed(dec, antiga, agora, log)

        # Passo 4: sobreposicao (ultimo ticket PENDING/RUNNING).
        if self._busy(conn, regra, ctx_exec["script"], agora, log):
            if dec.cron_error:
                return self._cron_error(conn, regra, antiga, None, None, [], log)
            if dec.complete:
                if not self.agenda.complete_without_ticket(conn, regra["id"], antiga, self.agent_id):
                    conn.rollback()
                    return "CORRIDA"
                conn.commit()
                log.info("SKIP_OVERLAP: regra concluida sem ticket; ocorrencias perdidas: %d", dec.missed + 1)
                return "CONCLUIDA_SEM_TICKET"
            return self._advance(conn, regra, antiga, dec.next_date, log, "SKIP_OVERLAP")

        if not dec.create_ticket:
            if dec.cron_error:
                return self._cron_error(conn, regra, antiga, None, None, [], log)
            if dec.complete:
                if not self.agenda.complete_without_ticket(conn, regra["id"], antiga, self.agent_id):
                    conn.rollback()
                    return "CORRIDA"
                conn.commit()
                log.info("regra concluida sem ticket (misfire SKIP fora da tolerancia)")
                return "CONCLUIDA_SEM_TICKET"
            return self._advance(conn, regra, antiga, dec.next_date, log, "MISFIRE_SKIP")

        # Passo 5: snapshot v4 (path_file absoluto, CR-005) a partir de parametros_json.
        script, vinculos = self.agenda.script_and_links(conn, regra["script_id"])
        ticket, linhas, erro = self._build_ticket(regra, script, vinculos, login, prioridade, dec.occurrence, agora)
        if erro is not None:
            return self._pause(conn, regra, antiga, "INVALID_PARAM", erro, log)

        # Passo 6: reserva + ticket (ou conclusao / variante cron_erro).
        ticket_id = self.agenda.next_ticket_id(conn)
        if dec.cron_error:
            return self._cron_error(conn, regra, antiga, ticket_id, ticket, linhas, log)
        if dec.complete:
            if not self.agenda.complete_with_ticket(conn, regra, antiga, ticket_id, ticket, linhas, self.agent_id):
                conn.rollback()
                return "CORRIDA"
            conn.commit()
            log.info("ticket %d gerado (ocorrencia %s, prioridade %d); regra concluida", ticket_id, dec.occurrence,
                     prioridade)
            return "CONCLUIDA_COM_TICKET"
        if not self.agenda.reserve_and_create_ticket(conn, regra, antiga, dec.next_date, ticket_id, ticket, linhas,
                                                   self.agent_id):
            conn.rollback()
            return "CORRIDA"
        conn.commit()
        log.info("ticket %d gerado (ocorrencia %s, prioridade %d); proxima execucao %s", ticket_id, dec.occurrence,
                 prioridade, dec.next_date)
        return "TICKET"

    # ------------------------------------------------------------------ passos auxiliares

    def _log_missed(self, decision, old, now, log):
        """README §7.4 (D3): WARN quando a vencida mais antiga (a next_run lida) passa da tolerancia
        (misfire de verdade, mesmo com a mais recente dentro dela); INFO quando coalescidas dentro da tolerancia."""
        if not decision.missed and decision.create_ticket:
            return
        if (now - old).total_seconds() > self.cfg.misfire_tolerance_s:
            log.warning("MISFIRE: %d ocorrencia(s) perdida(s) (politica %s, tolerancia %d s)", decision.missed,
                        self.cfg.misfire_policy, self.cfg.misfire_tolerance_s)
        else:
            log.info("%d ocorrencia(s) coalescida(s) dentro da tolerancia", decision.missed)

    def _busy(self, conn, rule, script, now, log):
        """ultimo_ticket_id PENDING/RUNNING bloqueia; nulo, inexistente (purgado) ou terminal e livre."""
        ultimo = rule.get("last_ticket_id")
        if ultimo is None:
            return False
        estado = self.agenda.get_ticket_status(conn, ultimo)
        if estado is None or estado[0] not in _BUSY:
            return False
        limite = (((script or {}).get("timeout_s") or self.cfg.script_timeout_s) + self.cfg.node_offline_timeout_s)
        criado = estado[1]
        if criado is not None and (now - criado).total_seconds() > limite:
            log.warning("SKIP_OVERLAP_PRESO: o ticket %d esta %s ha mais de %d s; precisa de atencao", ultimo,
                        estado[0], limite)
        else:
            log.info("SKIP_OVERLAP: o ticket %d ainda esta %s", ultimo, estado[0])
        return True

    def _build_ticket(self, rule, script, links, login, priority, occurrence, now):
        """(ticket, linhas_ticket_resp, None) ou (None, None, detalhe do INVALID_PARAM sem valores; R-26)."""
        if script is None:
            return None, None, "script inexistente"
        try:
            respostas = json.loads(rule.get("params_json") or "{}")
        except ValueError:
            return None, None, "parametros_json invalido"
        if not isinstance(respostas, dict):
            return None, None, "parametros_json invalido"
        ativos = sorted((v for v in links if v.get("active") == "Y"), key=lambda v: (v["sort_order"], v["parameter_id"]))
        snapshot, resolvidos, erros = params_compiler.compile_snapshot(script, ativos, respostas, now)
        if erros:
            return None, None, _short("; ".join("%s: %s" % (c, m) for c, m in sorted(erros.items())))
        linhas = [{"parameter_id": v["parameter_id"], "answer_value": _answer_text(resolvidos.get(v["code"]))}
                  for v in ativos if resolvidos.get(v["code"]) is not None]
        ticket = {"requested_by": login, "priority": priority, "submitted_params": snapshot,
                  "scheduled_at": occurrence}
        return ticket, linhas, None

    def _advance(self, conn, rule, old, new, log, reason):
        if not self.agenda.advance_without_ticket(conn, rule["id"], old, new):
            conn.rollback()
            return "CORRIDA"
        conn.commit()
        log.info("%s: sem ticket; proxima execucao %s", reason, new)
        return "AVANCADA"

    def _pause(self, conn, rule, old, reason, detail, log):
        if not self.agenda.pause(conn, rule["id"], old, reason, detail, self.agent_id):
            conn.rollback()
            return "CORRIDA"
        conn.commit()
        log.warning("regra pausada: %s (%s)", reason, detail)
        return "PAUSADA"

    def _cron_error(self, conn, rule, old, ticket_id, ticket, rows, log):
        if not self.agenda.pause_cron_error(conn, rule, old, ticket_id, ticket, rows,
                                            "sem proxima ocorrencia no horizonte", self.agent_id):
            conn.rollback()
            return "CORRIDA"
        conn.commit()
        if ticket_id is None:
            log.warning("regra pausada: INVALID_CRON (sem proxima ocorrencia no horizonte), sem ticket")
            return "INVALID_CRON"
        log.warning("ticket %d gerado e regra pausada: INVALID_CRON (sem proxima ocorrencia no horizonte)", ticket_id)
        return "CRON_INVALIDO_COM_TICKET"

    def _duplicate_occurrence(self, conn, rule_id, log):
        """R-31: ROLLBACK, WARN e, numa nova transacao, o avanco sem ticket com a mesma antiga e a nova da decisao."""
        log.warning("OCORRENCIA_DUPLICADA: outro caminho ja gerou o ticket desta ocorrencia")
        regra = getattr(self, "_current_rule", None)
        try:
            if regra is not None and regra["id"] == rule_id:
                dec = recurrence.evaluate_trigger(regra, db_conn.db_now(conn), self.cfg.misfire_policy,
                                                 self.cfg.misfire_tolerance_s, self.horizon)
                if dec.next_date is not None:
                    self.agenda.advance_without_ticket(conn, rule_id, regra["next_run_at"], dec.next_date)
            conn.commit()
        except Exception as exc:  # noqa: BLE001 - a regra volta no ciclo seguinte
            conn.rollback()
            log.warning("avanco apos OCORRENCIA_DUPLICADA falhou (%s)", exc.__class__.__name__)
        self.failures.pop(rule_id, None)
        return "OCORRENCIA_DUPLICADA"

    def _failure(self, conn, rule_id, exc, log):
        if is_db_error(exc):
            pfx, num = db_conn.classify_error(exc)
            n = self.failures.get(rule_id, 0) + 1
            self.failures[rule_id] = n
            log.warning("DESDOBRO_ERRO_BANCO: %s (falha %d de %d seguidas)",
                        "%s-%05d" % (pfx, num) if pfx else exc.__class__.__name__, n, FAILURES_BEFORE_PAUSE)
            if db_conn.is_network_error(exc):
                raise exc  # conexao perdida: o ciclo para e o agente reconecta (o laco trata)
            if n < FAILURES_BEFORE_PAUSE:
                return "ERRO_BANCO"
            detalhe = "%d falhas seguidas de banco (%s)" % (n, "%s-%05d" % (pfx, num) if pfx else exc.__class__.__name__)
        else:
            log.error("erro interno no desdobro: %s", exc.__class__.__name__, exc_info=True)
            detalhe = exc.__class__.__name__
        self.failures.pop(rule_id, None)
        try:
            pausou = self.agenda.pause_internal_error(conn, rule_id, detalhe, self.agent_id)
            conn.commit()
        except Exception as exc2:  # noqa: BLE001 - a regra fica ignorada ate o fim do ciclo (R-08)
            conn.rollback()
            log.error("pausa INTERNAL_ERROR falhou (%s): regra ignorada neste ciclo", exc2.__class__.__name__)
            return "IGNORAR"
        if pausou:
            log.warning("regra pausada: INTERNAL_ERROR (%s)", detalhe)
        return "INTERNAL_ERROR"


class _RuleLog(object):
    """Linhas do desdobro com agente, regra e acao DESDOBRO (README §13)."""

    def __init__(self, log, agent_id, rule_id):
        self._log = log
        self._extra = {"agent": agent_id, "ticket": "-", "action": "DESDOBRO"}
        self._pfx = "agendamento %d: " % int(rule_id)

    def info(self, msg, *args):
        self._log.info(self._pfx + msg, *args, extra=self._extra)

    def warning(self, msg, *args):
        self._log.warning(self._pfx + msg, *args, extra=self._extra)

    def error(self, msg, *args, **kw):
        self._log.error(self._pfx + msg, *args, extra=self._extra, **kw)
