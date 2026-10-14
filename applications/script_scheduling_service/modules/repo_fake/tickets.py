# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de tickets (README §2.5, §5, §10)."""
import copy

from repo_errors import RepoNaoEncontrado, RepoViolacao
from repo_fake.store import paginar
from repo_tickets import RepoTickets


class RepoTicketsFake(RepoTickets):
    """Implementacao em memoria com semantica Oracle para tickets."""

    def __init__(self, store):
        self._store = store

    def criar(self, ticket, respostas):
        """Cria ticket e respostas vinculadas atomicamente, com auditoria TICKET_CRIAR."""
        with self._store.lock_tickets:
            script_id = int(ticket.get("script_id", 0))
            ambiente = ticket.get("ambiente")
            solicitante = ticket.get("solicitante")

            if not script_id:
                raise RepoViolacao("script_id e obrigatorio")
            if not ambiente:
                raise RepoViolacao("ambiente e obrigatorio")
            if not solicitante:
                raise RepoViolacao("solicitante e obrigatorio")

            prio = int(ticket.get("prioridade", 2))
            if not (1 <= prio <= 4):
                raise RepoViolacao("prioridade deve estar entre 1 e 4", constraint="ck_tbsss_tck_prio")

            status = ticket.get("status", "PENDING")
            if status not in ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED"):
                raise RepoViolacao("Status invalido", constraint="ck_tbsss_tck_stat")

            tid = self._store.proximo_id("tbsss_tickets")
            agora = self._store.agora()
            sched = ticket.get("scheduled_at") or agora

            novo_ticket = {
                "id": tid,
                "script_id": script_id,
                "ambiente": ambiente,
                "solicitante": solicitante,
                "ip_origem": ticket.get("ip_origem"),
                "agente_id": ticket.get("agente_id"),
                "process_id": ticket.get("process_id"),
                "process_start": ticket.get("process_start"),
                "status": status,
                "prioridade": prio,
                "cancel_requested": ticket.get("cancel_requested", "N"),
                "status_motivo": ticket.get("status_motivo"),
                "parent_ticket_id": ticket.get("parent_ticket_id"),
                "agendamento_id": ticket.get("agendamento_id"),
                "parametros_enviados": ticket.get("parametros_enviados", "{}"),
                "log_output": ticket.get("log_output", ""),
                "log_truncado": ticket.get("log_truncado", "N"),
                "return_code": ticket.get("return_code"),
                "scheduled_at": sched,
                "started_at": ticket.get("started_at"),
                "heartbeat_at": ticket.get("heartbeat_at"),
                "finished_at": ticket.get("finished_at"),
                "created_at": ticket.get("created_at") or agora,
            }
            self._store.tickets[tid] = copy.deepcopy(novo_ticket)

            # Insercao das respostas
            for resp in (respostas or []):
                rid = self._store.proximo_id("tbsss_ticket_resp")
                nresp = {
                    "id": rid,
                    "ticket_id": tid,
                    "parametro_id": int(resp["parametro_id"]),
                    "valor_resposta": resp.get("valor_resposta"),
                    "created_at": agora,
                }
                self._store.ticket_resp[rid] = copy.deepcopy(nresp)

            # Auditoria na mesma transacao (lock)
            self._store.registrar_auditoria_interno(
                ator=solicitante,
                ip=ticket.get("ip_origem"),
                acao="TICKET_CRIAR",
                entidade="tbsss_tickets",
                entidade_id=tid,
                detalhe="Ticket criado para script %s em %s" % (script_id, ambiente),
            )

            return tid

    def obter(self, id):
        """Retorna dict com dados do ticket pelo ID ou lanca RepoNaoEncontrado."""
        with self._store.lock_tickets:
            if id not in self._store.tickets:
                raise RepoNaoEncontrado("Ticket ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.tickets[id])

    def listar(self, filtros=None, pagina=1, tamanho=20, escopo_ambientes=None):
        """Lista tickets com paginacao, filtros e escopo de ambientes."""
        filtros = filtros or {}
        with self._store.lock_tickets:
            lista = list(self._store.tickets.values())

            # Escopo de ambientes autorizados ao perfil
            if escopo_ambientes is not None:
                ambs_permitidos = set(escopo_ambientes)
                lista = [t for t in lista if t.get("ambiente") in ambs_permitidos]

            stat_f = filtros.get("status")
            if stat_f:
                if isinstance(stat_f, (list, tuple, set)):
                    stat_set = set(stat_f)
                    lista = [t for t in lista if t.get("status") in stat_set]
                else:
                    lista = [t for t in lista if t.get("status") == stat_f]

            amb_f = filtros.get("ambiente")
            if amb_f:
                lista = [t for t in lista if t.get("ambiente") == amb_f]

            sid_f = filtros.get("script_id")
            if sid_f is not None:
                lista = [t for t in lista if t.get("script_id") == int(sid_f)]

            usr_f = filtros.get("solicitante")
            if usr_f:
                lista = [t for t in lista if usr_f.lower() in t.get("solicitante", "").lower()]

            origem_f = filtros.get("origem")
            if origem_f == "manual":
                lista = [t for t in lista if t.get("agendamento_id") is None]
            elif origem_f == "agendamento":
                lista = [t for t in lista if t.get("agendamento_id") is not None]

            dt_ini = filtros.get("criado_inicio")
            if dt_ini:
                lista = [t for t in lista if t.get("created_at") and t["created_at"] >= dt_ini]

            dt_fim = filtros.get("criado_fim")
            if dt_fim:
                lista = [t for t in lista if t.get("created_at") and t["created_at"] <= dt_fim]

            # Ordenacao estavel padrao: created_at DESC, id DESC
            lista.sort(key=lambda x: (x.get("created_at") or self._store.agora(), x["id"]), reverse=True)
            return paginar(lista, pagina=pagina, tamanho=tamanho)

    def respostas(self, ticket_id):
        """Retorna lista de dicts com respostas do ticket."""
        with self._store.lock_tickets:
            resps = [
                r for r in self._store.ticket_resp.values()
                if r["ticket_id"] == ticket_id
            ]
            resps.sort(key=lambda x: x["id"])
            return copy.deepcopy(resps)

    def solicitar_cancelamento(self, id):
        """Logica de cancelamento do no web (README §5.6)."""
        with self._store.lock_tickets:
            if id not in self._store.tickets:
                raise RepoNaoEncontrado("Ticket ID %s nao encontrado" % id)

            t = self._store.tickets[id]
            st = t.get("status")

            if st not in ("PENDING", "RUNNING"):
                return "TERMINAL"

            if st == "PENDING":
                t["cancel_requested"] = "S"
                t["status"] = "CANCELLED"
                t["status_motivo"] = "CANCEL_USER"
                t["return_code"] = -1
                t["finished_at"] = self._store.agora()

                self._store.registrar_auditoria_interno(
                    ator=t.get("solicitante", "SYSTEM"),
                    ip=t.get("ip_origem"),
                    acao="TICKET_CANCELAR",
                    entidade="tbsss_tickets",
                    entidade_id=id,
                    detalhe="Cancelamento de ticket PENDING realizado pelo no web",
                )
                return "CANCELADO"

            if st == "RUNNING":
                t["cancel_requested"] = "S"

                self._store.registrar_auditoria_interno(
                    ator=t.get("solicitante", "SYSTEM"),
                    ip=t.get("ip_origem"),
                    acao="TICKET_CANCELAR",
                    entidade="tbsss_tickets",
                    entidade_id=id,
                    detalhe="Sinalizado cancelamento de ticket RUNNING para o agente dono",
                )
                return "SINALIZADO"

    def log_ler(self, id, offset, max_chars):
        """Leitura incremental de log por offset e tamanho maximo."""
        with self._store.lock_tickets:
            if id not in self._store.tickets:
                raise RepoNaoEncontrado("Ticket ID %s nao encontrado" % id)

            t = self._store.tickets[id]
            log_output = t.get("log_output") or ""

            # Valor nao numerico propaga ValueError/TypeError, como o bind NUMBER no Oracle.
            off = int(offset)
            if off < 0:
                off = 0

            mc = int(max_chars)
            if mc < 1:
                mc = 65536

            texto = log_output[off:off + mc]
            novo_offset = off + len(texto)
            terminal = t.get("status") in ("SUCCESS", "FAILED", "CANCELLED")
            truncado = t.get("log_truncado") == "S"

            return (texto, novo_offset, terminal, truncado)
