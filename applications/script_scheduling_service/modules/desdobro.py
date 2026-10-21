# -*- coding: utf-8 -*-
"""Desdobro dos agendamentos no agente (README §7.4 e §7.5; F8.4b; CR-003 D1-D3; CR-006; CR-007 R-05, R-08, R-19,
R-26, R-27; CR-008 R-03, R-19, R-21, R-22, R-31, R-33).

Uma transacao por regra, sem espera: trava (SKIP LOCKED), le, revalida o responsavel, decide (recurrence), confere
a sobreposicao, compila o snapshot v4 e reserva/conclui/pausa pelo repo_oracle/scheduler_agenda, com o COMMIT unico
aqui (passo 8). Uma regra com defeito nunca trava as demais: erro de banco conta falhas seguidas (3a pausa
ERRO_INTERNO), outra excecao pausa ERRO_INTERNO numa transacao separada. Paginacao com orcamento de tempo.
Python puro, sem gluon; o log permite reconstruir cada decisao sem o banco.
"""
import json
import logging

import db_conn
import params_compiler
import rbac
import recurrence
from repo_oracle.scheduler_agenda import OcorrenciaDuplicada

_log = logging.getLogger("sss_scheduler")

FALHAS_ATE_PAUSAR = 3
_OCUPADO = ("PENDING", "RUNNING")
_DETALHE_MAX = 900


def _texto_resposta(valor):
    """Mesma forma do ticket manual (ticket_service): CHECKBOX vira 'true'/'false'."""
    if valor is True:
        return "true"
    if valor is False:
        return "false"
    return valor


def _curto(texto):
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= _DETALHE_MAX else texto[:_DETALHE_MAX - 3] + "..."


def eh_erro_banco(exc):
    """Erro do contrato do banco (ORA/DPY/DPI, rede ou prazo): nova tentativa no ciclo seguinte (R-22)."""
    pfx, _num = db_conn.classificar_erro(exc)
    return pfx is not None or db_conn.eh_erro_rede(exc) or db_conn.eh_tempo_esgotado(exc)


class Desdobro(object):
    """Ciclo de desdobro de um agente. As falhas seguidas por regra ficam em memoria (zeradas no sucesso)."""

    def __init__(self, agenda, fila, agente_id, cfg_agente, relogio, log=None, horizonte_dias=None):
        self.agenda = agenda
        self.fila = fila
        self.agente_id = agente_id
        self.cfg = cfg_agente
        self.relogio = relogio
        self.log = log or _log
        self.horizonte = horizonte_dias or cfg_agente.cron_horizon_days
        self.falhas = {}

    # ------------------------------------------------------------------ ciclo

    def executar(self, conn, continuar=None):
        """Paginas de regras vencidas ate vir uma incompleta ou gastar heartbeat_interval_s / 2 (R-08).

        continuar(): False interrompe entre regras (fencing ou parada). Devolve contadores do ciclo.
        """
        inicio = self.relogio()
        orcamento = self.cfg.heartbeat_interval_s / 2.0
        lote = self.cfg.schedule_batch_size
        ult_prox, ult_id = None, 0
        ignoradas = set()
        stats = {"regras": 0, "tickets": 0, "pausas": 0, "puladas": 0}
        while True:
            pagina = self.agenda.regras_vencidas(conn, lote, ult_prox, ult_id)
            conn.rollback()  # a leitura nao trava nada; cada regra abre a propria transacao
            for regra_id, prox in pagina:
                if (continuar is not None and not continuar()) or self.relogio() - inicio > orcamento:
                    return stats
                ult_prox, ult_id = prox, regra_id
                if regra_id in ignoradas:
                    continue
                stats["regras"] += 1
                desfecho = self.processar(conn, regra_id)
                if desfecho == "IGNORAR":
                    ignoradas.add(regra_id)
                elif desfecho in ("TICKET", "CONCLUIDA_COM_TICKET", "CRON_INVALIDO_COM_TICKET"):
                    stats["tickets"] += 1
                if desfecho in ("PAUSADA", "CRON_INVALIDO", "CRON_INVALIDO_COM_TICKET", "ERRO_INTERNO"):
                    stats["pausas"] += 1
                if desfecho == "OUTRO_AGENTE":
                    stats["puladas"] += 1
            if len(pagina) < lote or self.relogio() - inicio > orcamento:
                return stats

    # ------------------------------------------------------------------ uma regra

    def processar(self, conn, regra_id):
        """Passos 1 a 8 do README §7.5 numa transacao. Devolve o desfecho (texto, para o log e os testes)."""
        log = _LogRegra(self.log, self.agente_id, regra_id)
        self._regra_atual = None
        try:
            desfecho = self._processar(conn, regra_id, log)
        except OcorrenciaDuplicada:
            conn.rollback()
            return self._ocorrencia_duplicada(conn, regra_id, log)
        except Exception as exc:  # noqa: BLE001 - nenhuma regra derruba o ciclo (R-08, R-22)
            conn.rollback()
            return self._falha(conn, regra_id, exc, log)
        self.falhas.pop(regra_id, None)
        return desfecho

    def _processar(self, conn, regra_id, log):
        if not self.agenda.travar_regra(conn, regra_id):
            conn.rollback()
            return "OUTRO_AGENTE"
        regra = self.agenda.carregar_regra(conn, regra_id)
        if regra is None:
            conn.rollback()
            return "OUTRO_AGENTE"
        antiga = regra["proxima_execucao"]  # passo 1: exatamente como o banco devolveu
        agora = db_conn.agora_banco(conn)
        self._regra_atual = regra

        # Passo 2: o responsavel ainda pode executar (motivo pela traducao unica, CR-008 R-33).
        login = self.agenda.login_do_usuario(conn, regra["usuario_id"])
        ctx_exec = self.fila.contexto_execucao(conn, {"script_id": regra["script_id"], "ambiente": regra["ambiente"],
                                                      "solicitante": login})
        ok, motivo = rbac.pode_executar(ctx_exec["ctx"], ctx_exec["script"], ctx_exec["ambiente"],
                                        ctx_exec["homologacoes"])
        if not ok:
            return self._pausar(conn, regra, antiga, rbac.motivo_pausa(motivo), "rbac: %s" % motivo, log)
        prioridade = int(regra["prioridade"])
        if prioridade == 1 and not (ctx_exec["ctx"] or {}).get("is_admin"):
            prioridade = 2
            log.warning("PRIORIDADE_REBAIXADA: o responsavel %s deixou de ser admin; ticket com prioridade 2", login)

        # Passo 3: decisao (misfire pela vencida mais recente, CR-008 R-21).
        try:
            dec = recurrence.avaliar_disparo(regra, agora, self.cfg.misfire_policy, self.cfg.misfire_tolerance_s,
                                             self.horizonte)
        except recurrence.CronErro as exc:
            return self._pausar(conn, regra, antiga, "CRON_INVALIDO", _curto(exc), log)
        self._registrar_perdidas(dec, antiga, agora, log)

        # Passo 4: sobreposicao (ultimo ticket PENDING/RUNNING).
        if self._ocupado(conn, regra, ctx_exec["script"], agora, log):
            if dec.cron_erro:
                return self._cron_erro(conn, regra, antiga, None, None, [], log)
            if dec.concluir:
                if not self.agenda.concluir_sem_ticket(conn, regra["id"], antiga, self.agente_id):
                    conn.rollback()
                    return "CORRIDA"
                conn.commit()
                log.info("SKIP_OVERLAP: regra concluida sem ticket; ocorrencias perdidas: %d", dec.perdidas + 1)
                return "CONCLUIDA_SEM_TICKET"
            return self._avancar(conn, regra, antiga, dec.nova_data, log, "SKIP_OVERLAP")

        if not dec.gerar_ticket:
            if dec.cron_erro:
                return self._cron_erro(conn, regra, antiga, None, None, [], log)
            if dec.concluir:
                if not self.agenda.concluir_sem_ticket(conn, regra["id"], antiga, self.agente_id):
                    conn.rollback()
                    return "CORRIDA"
                conn.commit()
                log.info("regra concluida sem ticket (misfire SKIP fora da tolerancia)")
                return "CONCLUIDA_SEM_TICKET"
            return self._avancar(conn, regra, antiga, dec.nova_data, log, "MISFIRE_SKIP")

        # Passo 5: snapshot v4 (path_file absoluto, CR-005) a partir de parametros_json.
        script, vinculos = self.agenda.script_e_vinculos(conn, regra["script_id"])
        ticket, linhas, erro = self._montar_ticket(regra, script, vinculos, login, prioridade, dec.ocorrencia, agora)
        if erro is not None:
            return self._pausar(conn, regra, antiga, "PARAM_INVALIDO", erro, log)

        # Passo 6: reserva + ticket (ou conclusao / variante cron_erro).
        ticket_id = self.agenda.proximo_ticket_id(conn)
        if dec.cron_erro:
            return self._cron_erro(conn, regra, antiga, ticket_id, ticket, linhas, log)
        if dec.concluir:
            if not self.agenda.concluir_com_ticket(conn, regra, antiga, ticket_id, ticket, linhas, self.agente_id):
                conn.rollback()
                return "CORRIDA"
            conn.commit()
            log.info("ticket %d gerado (ocorrencia %s, prioridade %d); regra concluida", ticket_id, dec.ocorrencia,
                     prioridade)
            return "CONCLUIDA_COM_TICKET"
        if not self.agenda.reservar_e_criar_ticket(conn, regra, antiga, dec.nova_data, ticket_id, ticket, linhas,
                                                   self.agente_id):
            conn.rollback()
            return "CORRIDA"
        conn.commit()
        log.info("ticket %d gerado (ocorrencia %s, prioridade %d); proxima execucao %s", ticket_id, dec.ocorrencia,
                 prioridade, dec.nova_data)
        return "TICKET"

    # ------------------------------------------------------------------ passos auxiliares

    def _registrar_perdidas(self, dec, antiga, agora, log):
        """README §7.4 (D3): WARN quando a vencida mais antiga (a proxima_execucao lida) passa da tolerancia
        (misfire de verdade, mesmo com a mais recente dentro dela); INFO quando coalescidas dentro da tolerancia."""
        if not dec.perdidas and dec.gerar_ticket:
            return
        if (agora - antiga).total_seconds() > self.cfg.misfire_tolerance_s:
            log.warning("MISFIRE: %d ocorrencia(s) perdida(s) (politica %s, tolerancia %d s)", dec.perdidas,
                        self.cfg.misfire_policy, self.cfg.misfire_tolerance_s)
        else:
            log.info("%d ocorrencia(s) coalescida(s) dentro da tolerancia", dec.perdidas)

    def _ocupado(self, conn, regra, script, agora, log):
        """ultimo_ticket_id PENDING/RUNNING bloqueia; nulo, inexistente (purgado) ou terminal e livre."""
        ultimo = regra.get("ultimo_ticket_id")
        if ultimo is None:
            return False
        estado = self.agenda.status_ticket(conn, ultimo)
        if estado is None or estado[0] not in _OCUPADO:
            return False
        limite = (((script or {}).get("timeout_seg") or self.cfg.script_timeout_s) + self.cfg.node_offline_timeout_s)
        criado = estado[1]
        if criado is not None and (agora - criado).total_seconds() > limite:
            log.warning("SKIP_OVERLAP_PRESO: o ticket %d esta %s ha mais de %d s; precisa de atencao", ultimo,
                        estado[0], limite)
        else:
            log.info("SKIP_OVERLAP: o ticket %d ainda esta %s", ultimo, estado[0])
        return True

    def _montar_ticket(self, regra, script, vinculos, login, prioridade, ocorrencia, agora):
        """(ticket, linhas_ticket_resp, None) ou (None, None, detalhe do PARAM_INVALIDO sem valores; R-26)."""
        if script is None:
            return None, None, "script inexistente"
        try:
            respostas = json.loads(regra.get("parametros_json") or "{}")
        except ValueError:
            return None, None, "parametros_json invalido"
        if not isinstance(respostas, dict):
            return None, None, "parametros_json invalido"
        ativos = sorted((v for v in vinculos if v.get("ativo") == "S"), key=lambda v: (v["ordem"], v["parametro_id"]))
        snapshot, resolvidos, erros = params_compiler.compilar_snapshot(script, ativos, respostas, agora)
        if erros:
            return None, None, _curto("; ".join("%s: %s" % (c, m) for c, m in sorted(erros.items())))
        linhas = [{"parametro_id": v["parametro_id"], "valor_resposta": _texto_resposta(resolvidos.get(v["codigo"]))}
                  for v in ativos if resolvidos.get(v["codigo"]) is not None]
        ticket = {"solicitante": login, "prioridade": prioridade, "parametros_enviados": snapshot,
                  "scheduled_at": ocorrencia}
        return ticket, linhas, None

    def _avancar(self, conn, regra, antiga, nova, log, motivo):
        if not self.agenda.avancar_sem_ticket(conn, regra["id"], antiga, nova):
            conn.rollback()
            return "CORRIDA"
        conn.commit()
        log.info("%s: sem ticket; proxima execucao %s", motivo, nova)
        return "AVANCADA"

    def _pausar(self, conn, regra, antiga, motivo, detalhe, log):
        if not self.agenda.pausar(conn, regra["id"], antiga, motivo, detalhe, self.agente_id):
            conn.rollback()
            return "CORRIDA"
        conn.commit()
        log.warning("regra pausada: %s (%s)", motivo, detalhe)
        return "PAUSADA"

    def _cron_erro(self, conn, regra, antiga, ticket_id, ticket, linhas, log):
        if not self.agenda.pausar_cron_erro(conn, regra, antiga, ticket_id, ticket, linhas,
                                            "sem proxima ocorrencia no horizonte", self.agente_id):
            conn.rollback()
            return "CORRIDA"
        conn.commit()
        if ticket_id is None:
            log.warning("regra pausada: CRON_INVALIDO (sem proxima ocorrencia no horizonte), sem ticket")
            return "CRON_INVALIDO"
        log.warning("ticket %d gerado e regra pausada: CRON_INVALIDO (sem proxima ocorrencia no horizonte)", ticket_id)
        return "CRON_INVALIDO_COM_TICKET"

    def _ocorrencia_duplicada(self, conn, regra_id, log):
        """R-31: ROLLBACK, WARN e, numa nova transacao, o avanco sem ticket com a mesma antiga e a nova da decisao."""
        log.warning("OCORRENCIA_DUPLICADA: outro caminho ja gerou o ticket desta ocorrencia")
        regra = getattr(self, "_regra_atual", None)
        try:
            if regra is not None and regra["id"] == regra_id:
                dec = recurrence.avaliar_disparo(regra, db_conn.agora_banco(conn), self.cfg.misfire_policy,
                                                 self.cfg.misfire_tolerance_s, self.horizonte)
                if dec.nova_data is not None:
                    self.agenda.avancar_sem_ticket(conn, regra_id, regra["proxima_execucao"], dec.nova_data)
            conn.commit()
        except Exception as exc:  # noqa: BLE001 - a regra volta no ciclo seguinte
            conn.rollback()
            log.warning("avanco apos OCORRENCIA_DUPLICADA falhou (%s)", exc.__class__.__name__)
        self.falhas.pop(regra_id, None)
        return "OCORRENCIA_DUPLICADA"

    def _falha(self, conn, regra_id, exc, log):
        if eh_erro_banco(exc):
            pfx, num = db_conn.classificar_erro(exc)
            n = self.falhas.get(regra_id, 0) + 1
            self.falhas[regra_id] = n
            log.warning("DESDOBRO_ERRO_BANCO: %s (falha %d de %d seguidas)",
                        "%s-%05d" % (pfx, num) if pfx else exc.__class__.__name__, n, FALHAS_ATE_PAUSAR)
            if db_conn.eh_erro_rede(exc):
                raise exc  # conexao perdida: o ciclo para e o agente reconecta (o laco trata)
            if n < FALHAS_ATE_PAUSAR:
                return "ERRO_BANCO"
            detalhe = "%d falhas seguidas de banco (%s)" % (n, "%s-%05d" % (pfx, num) if pfx else exc.__class__.__name__)
        else:
            log.error("erro interno no desdobro: %s", exc.__class__.__name__, exc_info=True)
            detalhe = exc.__class__.__name__
        self.falhas.pop(regra_id, None)
        try:
            pausou = self.agenda.pausar_erro_interno(conn, regra_id, detalhe, self.agente_id)
            conn.commit()
        except Exception as exc2:  # noqa: BLE001 - a regra fica ignorada ate o fim do ciclo (R-08)
            conn.rollback()
            log.error("pausa ERRO_INTERNO falhou (%s): regra ignorada neste ciclo", exc2.__class__.__name__)
            return "IGNORAR"
        if pausou:
            log.warning("regra pausada: ERRO_INTERNO (%s)", detalhe)
        return "ERRO_INTERNO"


class _LogRegra(object):
    """Linhas do desdobro com agente, regra e acao DESDOBRO (README §13)."""

    def __init__(self, log, agente_id, regra_id):
        self._log = log
        self._extra = {"agente": agente_id, "ticket": "-", "acao": "DESDOBRO"}
        self._pfx = "agendamento %d: " % int(regra_id)

    def info(self, msg, *args):
        self._log.info(self._pfx + msg, *args, extra=self._extra)

    def warning(self, msg, *args):
        self._log.warning(self._pfx + msg, *args, extra=self._extra)

    def error(self, msg, *args, **kw):
        self._log.error(self._pfx + msg, *args, extra=self._extra, **kw)
