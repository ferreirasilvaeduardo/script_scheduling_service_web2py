# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de tickets (README §2.5, §5, §10)."""
import copy
import datetime

import masking
from repo_errors import RepoNotFound, RepoViolation
from repo_fake.store import paginate
from repo_tickets import RepoTickets


_STAGES_SIMULATED = 50
_STAGE_SECRET = 3
_STAGE_HTML = 5


def _mask_like_log_pump(texto, sensiveis):
    # README §8.10: segredos carregados e valores de parametros sensiveis antes de anexar ao CLOB.
    local = masking.Mascarador()
    for _codigo, valor in sensiveis:
        local.register(valor)
    return masking.MASCARADOR.mascarar(local.mascarar(texto))


def _stage_lines(n, quando, sensiveis):
    linhas = ["[%s] etapa %d/%d processada\n" % (quando, n, _STAGES_SIMULATED)]
    if n == _STAGE_SECRET:
        for codigo, valor in sensiveis:
            linhas.append("[%s] conectando com %s=%s\n" % (quando, codigo, valor))
    elif n == _STAGE_HTML:
        linhas.append("[%s] saida bruta do script: <script>alert(1)</script> <b>negrito</b>\n" % quando)
    return linhas


_COLUMNS_CLOB = ("submitted_params", "log_output")


def _without(registro, colunas):
    """Copia do registro sem as colunas indicadas (paridade com o Oracle, que nao as seleciona)."""
    return dict((k, copy.deepcopy(v)) for k, v in registro.items() if k not in colunas)


class RepoTicketsFake(RepoTickets):
    """Implementacao em memoria com semantica Oracle para tickets."""

    def __init__(self, store):
        self._store = store

    def now(self):
        """Emula SYSDATE com o relogio injetavel do armazem."""
        return self._store.now()

    def create(self, ticket, respostas, ator=None):
        """Cria ticket e respostas vinculadas atomicamente, com auditoria TICKET_CREATE ou TICKET_RERUN.

        created_by do ticket e das respostas: ator= ou, sem ele, o solicitante (CR-006, README §10).
        """
        with self._store.lock_tickets:
            script_id = int(ticket.get("script_id", 0))
            ambiente = ticket.get("environment")
            solicitante = ticket.get("requested_by")
            ator = self._store.record_actor(ator=ator or solicitante)

            if not script_id:
                raise RepoViolation("script_id e obrigatorio")
            if not ambiente:
                raise RepoViolation("ambiente e obrigatorio")
            if not solicitante:
                raise RepoViolation("solicitante e obrigatorio")

            prio = int(ticket.get("priority", 2))
            if not (1 <= prio <= 4):
                raise RepoViolation("prioridade deve estar entre 1 e 4", constraint="ck_tbsss_tck_prio")

            status = ticket.get("status", "PENDING")
            if status not in ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED"):
                raise RepoViolation("Status invalido", constraint="ck_tbsss_tck_stat")

            parent_id = ticket.get("parent_ticket_id")
            if parent_id is not None and parent_id not in self._store.tickets:
                raise RepoViolation("ticket pai inexistente", constraint="fk_tbsss_tck_parent")
            # FKs e UK checadas antes de gravar qualquer linha: a operacao e atomica como no Oracle.
            self._store.check_fk(script_id in self._store.scripts, "fk_tbsss_tck_scr")
            self._store.check_fk(self._store.environment_exists(ambiente), "fk_tbsss_tck_env")
            self._store.check_fk(self._store.login_exists(solicitante), "fk_tbsss_tck_usr")
            vistos = set()
            for resp in (respostas or []):
                pid = int(resp["parameter_id"])
                self._store.check_fk(pid in self._store.parameters, "fk_tbsss_tans_prm")
                if pid in vistos:
                    raise RepoViolation("resposta repetida para o parametro %s" % pid, constraint="uk_tbsss_tans_tck_prm")
                vistos.add(pid)

            tid = self._store.next_id("tbsss_tickets")
            agora = self._store.now()
            sched = ticket.get("scheduled_at") or agora

            if ticket.get("schedule_id") is not None:
                agd_id = int(ticket["schedule_id"])
                for t in self._store.tickets.values():
                    if t.get("schedule_id") == agd_id and t.get("scheduled_at") == sched:
                        raise RepoViolation("ocorrencia duplicada para este agendamento", constraint="ix_tbsss_tck_occur")

            novo_ticket = {
                "id": tid,
                "script_id": script_id,
                "environment": ambiente,
                "requested_by": solicitante,
                "source_ip": ticket.get("source_ip"),
                "agent_id": ticket.get("agent_id"),
                "process_id": ticket.get("process_id"),
                "process_start": ticket.get("process_start"),
                "status": status,
                "priority": prio,
                "cancel_requested": ticket.get("cancel_requested", "N"),
                "status_reason": ticket.get("status_reason"),
                "parent_ticket_id": parent_id,
                "schedule_id": ticket.get("schedule_id"),
                "submitted_params": ticket.get("submitted_params", "{}"),
                "log_output": ticket.get("log_output", ""),
                "log_truncated": ticket.get("log_truncated", "N"),
                "return_code": ticket.get("return_code"),
                "scheduled_at": sched,
                "started_at": ticket.get("started_at"),
                "heartbeat_at": ticket.get("heartbeat_at"),
                "finished_at": ticket.get("finished_at"),
                "created_at": ticket.get("created_at") or agora,
            }
            self._store.stamp_insert(novo_ticket, ator)
            self._store.tickets[tid] = copy.deepcopy(novo_ticket)

            # Insercao das respostas
            for resp in (respostas or []):
                rid = self._store.next_id("tbsss_ticket_answer")
                nresp = {
                    "id": rid,
                    "ticket_id": tid,
                    "parameter_id": int(resp["parameter_id"]),
                    "answer_value": resp.get("answer_value"),
                    "created_at": agora,
                }
                self._store.stamp_insert(nresp, ator)
                self._store.ticket_answer[rid] = copy.deepcopy(nresp)

            # Auditoria na mesma transacao (lock)
            if parent_id is None:
                acao = "TICKET_CREATE"
                detalhe = "Ticket criado para script %s em %s" % (script_id, ambiente)
            else:
                acao = "TICKET_RERUN"
                detalhe = "Reexecucao do ticket %s para script %s em %s" % (parent_id, script_id, ambiente)
            self._store.register_internal_audit(
                ator=solicitante,
                ip=ticket.get("source_ip"),
                acao=acao,
                entidade="tbsss_tickets",
                entidade_id=tid,
                detalhe=detalhe,
            )

            return tid

    def get(self, id):
        """Retorna dict com dados do ticket pelo ID ou lanca RepoNotFound."""
        with self._store.lock_tickets:
            if id not in self._store.tickets:
                raise RepoNotFound("Ticket ID %s nao encontrado" % id)
            # O log so sai em fatias por log_ler (contrato RepoTickets.obter).
            return _without(self._store.tickets[id], ("log_output",))

    def list(self, filtros=None, pagina=1, tamanho=20, escopo_ambientes=None):
        """Lista tickets com paginacao, filtros e escopo de ambientes."""
        filtros = filtros or {}
        with self._store.lock_tickets:
            lista = list(self._store.tickets.values())

            # Escopo de ambientes autorizados ao perfil
            if escopo_ambientes is not None:
                ambs_permitidos = set(escopo_ambientes)
                lista = [t for t in lista if t.get("environment") in ambs_permitidos]

            stat_f = filtros.get("status")
            if stat_f:
                if isinstance(stat_f, (list, tuple, set)):
                    stat_set = set(stat_f)
                    lista = [t for t in lista if t.get("status") in stat_set]
                else:
                    lista = [t for t in lista if t.get("status") == stat_f]

            amb_f = filtros.get("environment")
            if amb_f:
                lista = [t for t in lista if t.get("environment") == amb_f]

            sid_f = filtros.get("script_id")
            if sid_f is not None:
                lista = [t for t in lista if t.get("script_id") == int(sid_f)]

            usr_f = filtros.get("requested_by")
            if usr_f:
                lista = [t for t in lista if t.get("requested_by") == usr_f]

            par_f = filtros.get("parent_ticket_id")
            if par_f is not None:
                lista = [t for t in lista if t.get("parent_ticket_id") == int(par_f)]

            origem_f = filtros.get("origem")
            if origem_f == "manual":
                lista = [t for t in lista if t.get("schedule_id") is None]
            elif origem_f == "agendamento":
                lista = [t for t in lista if t.get("schedule_id") is not None]

            dt_ini = filtros.get("criado_inicio")
            if dt_ini:
                lista = [t for t in lista if t.get("created_at") and t["created_at"] >= dt_ini]

            dt_fim = filtros.get("criado_fim")
            if dt_fim:
                lista = [t for t in lista if t.get("created_at") and t["created_at"] < dt_fim]

            # Ordenacao estavel padrao: created_at DESC, id DESC
            lista.sort(key=lambda x: (x.get("created_at") or self._store.now(), x["id"]), reverse=True)
            # Listagens nunca trazem CLOB (contrato RepoTickets.listar).
            return paginate([_without(t, _COLUMNS_CLOB) for t in lista], pagina=pagina, tamanho=tamanho)

    def last_runs(self, script_ids, escopo_ambientes=None, solicitante=None):
        """Ultimo ticket de cada script no escopo, sem LOB (contrato RepoTickets)."""
        ids = set(int(i) for i in script_ids)
        ambs = None if escopo_ambientes is None else set(escopo_ambientes)
        with self._store.lock_tickets:
            melhores = {}
            for t in self._store.tickets.values():
                if t["script_id"] not in ids or (ambs is not None and t["environment"] not in ambs):
                    continue
                if solicitante is not None and t["requested_by"] != solicitante:
                    continue
                chave = (t["created_at"], t["id"])
                atual = melhores.get(t["script_id"])
                if atual is None or chave > (atual["created_at"], atual["id"]):
                    melhores[t["script_id"]] = t
            return dict((sid, {"id": t["id"], "status": t["status"], "status_reason": t.get("status_reason"),
                               "created_at": t["created_at"], "finished_at": t.get("finished_at")})
                        for sid, t in melhores.items())

    def script_history(self, script_id, desde, escopo_ambientes=None, solicitante=None, limite=5000):
        """Tickets do script desde a data, no escopo, sem LOB (contrato RepoTickets)."""
        ambs = None if escopo_ambientes is None else set(escopo_ambientes)
        with self._store.lock_tickets:
            lista = [t for t in self._store.tickets.values()
                     if t["script_id"] == int(script_id) and t["created_at"] >= desde
                     and (ambs is None or t["environment"] in ambs)
                     and (solicitante is None or t["requested_by"] == solicitante)]
            lista.sort(key=lambda t: (t["created_at"], t["id"]))
            lista = lista[-int(limite):] if limite else lista
            return [dict((k, t.get(k)) for k in ("id", "status", "status_reason", "created_at", "started_at",
                                                 "finished_at")) for t in lista]

    def answers(self, ticket_id):
        """Retorna lista de dicts com respostas do ticket."""
        with self._store.lock_tickets:
            resps = [
                r for r in self._store.ticket_answer.values()
                if r["ticket_id"] == ticket_id
            ]
            resps.sort(key=lambda x: x["id"])
            return copy.deepcopy(resps)

    def request_cancel(self, id, ator, ip):
        """Logica de cancelamento do no web (README §5.6), auditada em nome de quem cancelou.

        Cancelar ou sinalizar grava updated_* com o ator; as solicitacoes sem efeito nao (CR-006).
        """
        with self._store.lock_tickets:
            ator = self._store.record_actor(ator=ator)
            if id not in self._store.tickets:
                raise RepoNotFound("Ticket ID %s nao encontrado" % id)

            t = self._store.tickets[id]
            st = t.get("status")

            def auditar(resultado):
                self._store.register_internal_audit(
                    ator=ator, ip=ip, acao="TICKET_CANCEL", entidade="tbsss_tickets", entidade_id=id,
                    detalhe=u"resultado: %s" % resultado)

            if st not in ("PENDING", "RUNNING"):
                auditar(u"sem efeito: ticket encerrado")
                return "TERMINAL"
            if st == "RUNNING" and t.get("cancel_requested") == "Y":
                auditar(u"já sinalizado")
                return "JA_SINALIZADO"

            if st == "PENDING":
                t["cancel_requested"] = "Y"
                t["status"] = "CANCELLED"
                t["status_reason"] = "CANCEL_USER"
                t["return_code"] = -1
                t["finished_at"] = self._store.now()
                self._store.stamp_update(t, ator)

                auditar(u"cancelado")
                return "CANCELADO"

            if st == "RUNNING":
                t["cancel_requested"] = "Y"
                self._store.stamp_update(t, ator)

                auditar(u"sinalizado")
                return "SINALIZADO"

    def log_read(self, id, offset, max_chars):
        """Leitura incremental de log por offset e tamanho maximo."""
        with self._store.lock_tickets:
            if id not in self._store.tickets:
                raise RepoNotFound("Ticket ID %s nao encontrado" % id)

            t = self._store.tickets[id]
            sim = self._store.log_sim.get(id)
            if sim is not None and t.get("status") == "RUNNING":
                self._simular_log(t, sim)
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
            truncado = t.get("log_truncated") == "Y"

            return (texto, novo_offset, terminal, truncado)

    def output_get(self, ticket_id):
        """Metadados da saida do ticket (CR-012), sem o conteudo; None sem saida."""
        with self._store.lock_tickets:
            for s in self._store.ticket_output.values():
                if s["ticket_id"] == int(ticket_id):
                    return dict((k, v) for k, v in s.items() if k not in ("id", "ticket_id", "content"))
        return None

    def output_read(self, ticket_id, offset, tamanho):
        """Fatia do zip (offset base 0); so DISPONIVEL, como no Oracle."""
        off = int(offset)
        tam = int(tamanho)
        if off < 0 or tam < 1 or tam > 1024 * 1024:
            raise RepoViolation("Fatia da saida invalida")
        with self._store.lock_tickets:
            for s in self._store.ticket_output.values():
                if s["ticket_id"] == int(ticket_id) and s["state"] == "AVAILABLE" and s["content"] is not None:
                    return bytes(s["content"][off:off + tam])
        raise RepoNotFound("Saida do ticket %s indisponivel" % ticket_id)

    def _simular_log(self, t, sim):
        """Emula o log_pump e a finalizacao pelo agente em funcao do relogio injetavel (somente FAKE)."""
        agora = self._store.now()
        decorrido = int((agora - t["started_at"]).total_seconds())
        alvo = min(_STAGES_SIMULATED, max(0, decorrido // sim["passo_s"]))
        cancelar = t.get("cancel_requested") == "Y"
        if alvo <= sim["emitidos"] and not cancelar:
            return
        linhas = []
        for n in range(sim["emitidos"] + 1, alvo + 1):
            quando = t["started_at"] + datetime.timedelta(seconds=n * sim["passo_s"])
            linhas.extend(_stage_lines(n, quando, sim["sensiveis"]))
        sim["emitidos"] = alvo
        if cancelar:
            linhas.append("[%s] processo encerrado por cancelamento (SIGTERM)\n" % agora)
            t.update(status="CANCELLED", status_reason="CANCEL_USER", return_code=-1)
        elif alvo >= _STAGES_SIMULATED:
            linhas.append("[%s] Script concluido com retorno 0.\n" % agora)
            t.update(status="SUCCESS", status_reason="EXIT_OK", return_code=0)
        if t["status"] != "RUNNING":
            t["finished_at"] = agora
            # A finalizacao e do agente dono (README §8.7); o heartbeat e o log nao gravam updated_*.
            self._store.stamp_update(t, "SYSTEM:%s" % t.get("agent_id"))
            self._store.log_sim.pop(t["id"], None)
        t["heartbeat_at"] = agora
        t["log_output"] = (t.get("log_output") or "") + _mask_like_log_pump("".join(linhas), sim["sensiveis"])
