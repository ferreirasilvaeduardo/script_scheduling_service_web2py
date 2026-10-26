# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de tickets (README §2.5, §5, §10)."""
import copy
import datetime

from sss.core import masking
from sss.persistence.repo_errors import RepoNotFound, RepoViolation
from sss.persistence.fake.store import paginate
from sss.persistence.contracts.repo_tickets import RepoTickets


_STAGES_SIMULATED = 50
_STAGE_SECRET = 3
_STAGE_HTML = 5


def _mask_like_log_pump(text, sensitive):
    # README §8.10: segredos carregados e valores de parametros sensiveis antes de anexar ao CLOB.
    local = masking.Masker()
    for _code, value in sensitive:
        local.register(value)
    return masking.MASKER.mask(local.mask(text))


def _stage_lines(n, when, sensitive):
    rows = ["[%s] etapa %d/%d processada\n" % (when, n, _STAGES_SIMULATED)]
    if n == _STAGE_SECRET:
        for code, value in sensitive:
            rows.append("[%s] conectando com %s=%s\n" % (when, code, value))
    elif n == _STAGE_HTML:
        rows.append("[%s] saida bruta do script: <script>alert(1)</script> <b>negrito</b>\n" % when)
    return rows


_COLUMNS_CLOB = ("submitted_params", "log_output")


def _without(record, columns):
    """Copia do registro sem as colunas indicadas (paridade com o Oracle, que nao as seleciona)."""
    return dict((k, copy.deepcopy(v)) for k, v in record.items() if k not in columns)


class RepoTicketsFake(RepoTickets):
    """Implementacao em memoria com semantica Oracle para tickets."""

    def __init__(self, store):
        self._store = store

    def now(self):
        """Emula SYSDATE com o relogio injetavel do armazem."""
        return self._store.now()

    def create(self, ticket, answers, actor=None):
        """Cria ticket e respostas vinculadas atomicamente, com auditoria TICKET_CREATE ou TICKET_RERUN.

        created_by do ticket e das respostas: actor= ou, sem ele, o solicitante (CR-006, README §10).
        """
        with self._store.lock_tickets:
            script_id = int(ticket.get("script_id", 0))
            environment = ticket.get("environment")
            requester = ticket.get("requested_by")
            actor = self._store.record_actor(actor=actor or requester)

            if not script_id:
                raise RepoViolation("script_id e obrigatorio")
            if not environment:
                raise RepoViolation("ambiente e obrigatorio")
            if not requester:
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
            self._store.check_fk(self._store.environment_exists(environment), "fk_tbsss_tck_env")
            self._store.check_fk(self._store.login_exists(requester), "fk_tbsss_tck_usr")
            seen = set()
            for resp in (answers or []):
                pid = int(resp["parameter_id"])
                self._store.check_fk(pid in self._store.parameters, "fk_tbsss_tans_prm")
                if pid in seen:
                    raise RepoViolation("resposta repetida para o parametro %s" % pid, constraint="uk_tbsss_tans_tck_prm")
                seen.add(pid)

            tid = self._store.next_id("tbsss_tickets")
            now = self._store.now()
            sched = ticket.get("scheduled_at") or now

            if ticket.get("schedule_id") is not None:
                sch_id = int(ticket["schedule_id"])
                for t in self._store.tickets.values():
                    if t.get("schedule_id") == sch_id and t.get("scheduled_at") == sched:
                        raise RepoViolation("ocorrencia duplicada para este agendamento", constraint="ix_tbsss_tck_occur")

            new_ticket = {
                "id": tid,
                "script_id": script_id,
                "environment": environment,
                "requested_by": requester,
                "source_ip": ticket.get("source_ip"),
                "agent_id": ticket.get("agent_id"),
                "process_id": ticket.get("process_id"),
                "process_start": ticket.get("process_start"),
                "script_path": ticket.get("script_path"),
                "interpreter_path": ticket.get("interpreter_path"),
                "interpreter_used": ticket.get("interpreter_used"),
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
                "created_at": ticket.get("created_at") or now,
            }
            self._store.stamp_insert(new_ticket, actor)
            self._store.tickets[tid] = copy.deepcopy(new_ticket)

            # Insercao das respostas
            for resp in (answers or []):
                rid = self._store.next_id("tbsss_ticket_answer")
                nresp = {
                    "id": rid,
                    "ticket_id": tid,
                    "parameter_id": int(resp["parameter_id"]),
                    "answer_value": resp.get("answer_value"),
                    "created_at": now,
                }
                self._store.stamp_insert(nresp, actor)
                self._store.ticket_answer[rid] = copy.deepcopy(nresp)

            # Auditoria na mesma transacao (lock)
            if parent_id is None:
                action = "TICKET_CREATE"
                detail = "Ticket criado para script %s em %s" % (script_id, environment)
            else:
                action = "TICKET_RERUN"
                detail = "Reexecucao do ticket %s para script %s em %s" % (parent_id, script_id, environment)
            if ticket.get("interpreter_override"):
                # CR-025: o interpretador digitado no disparo fica na trilha.
                detail += "; interpretador informado: %s" % ticket["interpreter_override"]
            self._store.register_internal_audit(
                actor=requester,
                ip=ticket.get("source_ip"),
                action=action,
                entity="tbsss_tickets",
                entity_id=tid,
                detail=detail,
            )

            return tid

    def get(self, id):
        """Retorna dict com dados do ticket pelo ID ou lanca RepoNotFound."""
        with self._store.lock_tickets:
            if id not in self._store.tickets:
                raise RepoNotFound("Ticket ID %s nao encontrado" % id)
            # O log so sai em fatias por log_ler (contrato RepoTickets.obter).
            return _without(self._store.tickets[id], ("log_output",))

    def list(self, filters=None, page=1, size=20, environment_scope=None):
        """Lista tickets com paginacao, filtros e escopo de ambientes."""
        filters = filters or {}
        with self._store.lock_tickets:
            items = list(self._store.tickets.values())

            # Escopo de ambientes autorizados ao perfil
            if environment_scope is not None:
                envs_allowed = set(environment_scope)
                items = [t for t in items if t.get("environment") in envs_allowed]

            stat_f = filters.get("status")
            if stat_f:
                if isinstance(stat_f, (list, tuple, set)):
                    stat_set = set(stat_f)
                    items = [t for t in items if t.get("status") in stat_set]
                else:
                    items = [t for t in items if t.get("status") == stat_f]

            env_f = filters.get("environment")
            if env_f:
                items = [t for t in items if t.get("environment") == env_f]

            sid_f = filters.get("script_id")
            if sid_f is not None:
                items = [t for t in items if t.get("script_id") == int(sid_f)]

            usr_f = filters.get("requested_by")
            if usr_f:
                items = [t for t in items if t.get("requested_by") == usr_f]

            pair_f = filters.get("parent_ticket_id")
            if pair_f is not None:
                items = [t for t in items if t.get("parent_ticket_id") == int(pair_f)]

            source_f = filters.get("source")
            if source_f == "manual":
                items = [t for t in items if t.get("schedule_id") is None]
            elif source_f == "agendamento":
                items = [t for t in items if t.get("schedule_id") is not None]

            dt_ini = filters.get("created_from")
            if dt_ini:
                items = [t for t in items if t.get("created_at") and t["created_at"] >= dt_ini]

            dt_end = filters.get("created_to")
            if dt_end:
                items = [t for t in items if t.get("created_at") and t["created_at"] < dt_end]

            # Ordenacao estavel padrao: created_at DESC, id DESC
            items.sort(key=lambda x: (x.get("created_at") or self._store.now(), x["id"]), reverse=True)
            # Listagens nunca trazem CLOB (contrato RepoTickets.listar).
            return paginate([_without(t, _COLUMNS_CLOB) for t in items], page=page, size=size)

    def last_runs(self, script_ids, environment_scope=None, requester=None):
        """Ultimo ticket de cada script no escopo, sem LOB (contrato RepoTickets)."""
        ids = set(int(i) for i in script_ids)
        envs = None if environment_scope is None else set(environment_scope)
        with self._store.lock_tickets:
            best = {}
            for t in self._store.tickets.values():
                if t["script_id"] not in ids or (envs is not None and t["environment"] not in envs):
                    continue
                if requester is not None and t["requested_by"] != requester:
                    continue
                key = (t["created_at"], t["id"])
                current = best.get(t["script_id"])
                if current is None or key > (current["created_at"], current["id"]):
                    best[t["script_id"]] = t
            return dict((sid, {"id": t["id"], "status": t["status"], "status_reason": t.get("status_reason"),
                               "created_at": t["created_at"], "finished_at": t.get("finished_at")})
                        for sid, t in best.items())

    def script_history(self, script_id, since, environment_scope=None, requester=None, limit=5000):
        """Tickets do script desde a data, no escopo, sem LOB (contrato RepoTickets)."""
        envs = None if environment_scope is None else set(environment_scope)
        with self._store.lock_tickets:
            items = [t for t in self._store.tickets.values()
                     if t["script_id"] == int(script_id) and t["created_at"] >= since
                     and (envs is None or t["environment"] in envs)
                     and (requester is None or t["requested_by"] == requester)]
            items.sort(key=lambda t: (t["created_at"], t["id"]))
            items = items[-int(limit):] if limit else items
            return [dict((k, t.get(k)) for k in ("id", "status", "status_reason", "created_at", "started_at",
                                                 "finished_at")) for t in items]

    def answers(self, ticket_id):
        """Retorna lista de dicts com respostas do ticket."""
        with self._store.lock_tickets:
            resps = [
                r for r in self._store.ticket_answer.values()
                if r["ticket_id"] == ticket_id
            ]
            resps.sort(key=lambda x: x["id"])
            return copy.deepcopy(resps)

    def request_cancel(self, id, actor, ip):
        """Logica de cancelamento do no web (README §5.6), auditada em nome de quem cancelou.

        Cancelar ou sinalizar grava updated_* com o ator; as solicitacoes sem efeito nao (CR-006).
        """
        with self._store.lock_tickets:
            actor = self._store.record_actor(actor=actor)
            if id not in self._store.tickets:
                raise RepoNotFound("Ticket ID %s nao encontrado" % id)

            t = self._store.tickets[id]
            st = t.get("status")

            def auditar(result):
                self._store.register_internal_audit(
                    actor=actor, ip=ip, action="TICKET_CANCEL", entity="tbsss_tickets", entity_id=id,
                    detail=u"resultado: %s" % result)

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
                self._store.stamp_update(t, actor)

                auditar(u"cancelado")
                return "CANCELADO"

            if st == "RUNNING":
                t["cancel_requested"] = "Y"
                self._store.stamp_update(t, actor)

                auditar(u"sinalizado")
                return "SINALIZADO"

    def log_read(self, id, offset, max_chars):
        """Leitura incremental de log por offset e tamanho maximo."""
        with self._store.lock_tickets:
            if id not in self._store.tickets:
                raise RepoNotFound("Ticket ID %s nao encontrado" % id)

            t = self._store.tickets[id]
            yes = self._store.log_simulated.get(id)
            if yes is not None and t.get("status") == "RUNNING":
                self._simular_log(t, yes)
            log_output = t.get("log_output") or ""

            # Valor nao numerico propaga ValueError/TypeError, como o bind NUMBER no Oracle.
            off = int(offset)
            if off < 0:
                off = 0

            mc = int(max_chars)
            if mc < 1:
                mc = 65536

            text = log_output[off:off + mc]
            new_offset = off + len(text)
            terminal = t.get("status") in ("SUCCESS", "FAILED", "CANCELLED")
            truncated = t.get("log_truncated") == "Y"

            return (text, new_offset, terminal, truncated)

    def output_get(self, ticket_id):
        """Metadados da saida do ticket (CR-012), sem o conteudo; None sem saida."""
        with self._store.lock_tickets:
            for s in self._store.ticket_output.values():
                if s["ticket_id"] == int(ticket_id):
                    return dict((k, v) for k, v in s.items() if k not in ("id", "ticket_id", "content"))
        return None

    def _available_outputs(self, environment_scope):
        """[(ticket, saida)] com saida AVAILABLE no escopo de ambientes (CR-020a)."""
        allowed = None if environment_scope is None else set(environment_scope)
        by_ticket = dict((s["ticket_id"], s) for s in self._store.ticket_output.values() if s["state"] == "AVAILABLE")
        pairs = []
        for t in self._store.tickets.values():
            out = by_ticket.get(t["id"])
            if out is None or (allowed is not None and t.get("environment") not in allowed):
                continue
            pairs.append((t, out))
        return pairs

    def output_summary(self, level, environment_scope=None, environment=None, script_id=None):
        """Resumo das saidas AVAILABLE por ambiente, script ou dia (CR-020a), como no Oracle."""
        if level not in ("environment", "script", "day"):
            raise RepoViolation("Nivel do resumo de saidas invalido")
        with self._store.lock_tickets:
            pairs = self._available_outputs(environment_scope)
            groups = {}
            for t, _out in pairs:
                if level == "environment":
                    key = t["environment"]
                elif t["environment"] != environment:
                    continue
                elif level == "script":
                    key = t["script_id"]
                elif t["script_id"] != int(script_id):
                    continue
                else:
                    key = t["started_at"].replace(hour=0, minute=0, second=0, microsecond=0)
                g = groups.setdefault(key, {"count": 0, "last_at": None})
                g["count"] += 1
                if g["last_at"] is None or t["started_at"] > g["last_at"]:
                    g["last_at"] = t["started_at"]
        if level == "environment":
            return [{"environment": k, "count": g["count"], "last_at": g["last_at"]} for k, g in sorted(groups.items())]
        if level == "script":
            names = dict((sid, (self._store.scripts.get(sid) or {}).get("name")) for sid in groups)
            return [{"script_id": k, "script_name": names[k], "count": g["count"], "last_at": g["last_at"]}
                    for k, g in sorted(groups.items(), key=lambda kv: (names[kv[0]] or "", kv[0]))]
        return [{"day": k, "count": g["count"]} for k, g in sorted(groups.items(), reverse=True)]

    def output_tickets(self, environment, script_id, day_from, day_to, page=1, size=20, environment_scope=None):
        """Tickets com saida AVAILABLE do ambiente e script no intervalo de started_at (CR-020a)."""
        with self._store.lock_tickets:
            rows = []
            for t, out in self._available_outputs(environment_scope):
                if t["environment"] != environment or t["script_id"] != int(script_id):
                    continue
                if not (day_from <= t["started_at"] < day_to):
                    continue
                item = dict((k, t.get(k)) for k in ("id", "environment", "script_id", "requested_by", "status",
                                                    "started_at", "finished_at"))
                item.update(file_count=out.get("file_count"), size_bytes=out.get("size_bytes"))
                rows.append(item)
        rows.sort(key=lambda r: (r["started_at"], r["id"]), reverse=True)
        p = max(1, int(page or 1))
        t = int(size or 20)
        t = 20 if t < 1 else t
        return {"items": rows[(p - 1) * t:p * t], "total": len(rows), "page": p, "size": t}

    def output_read(self, ticket_id, offset, size):
        """Fatia do zip (offset base 0); so DISPONIVEL, como no Oracle."""
        off = int(offset)
        size_n = int(size)
        if off < 0 or size_n < 1 or size_n > 1024 * 1024:
            raise RepoViolation("Fatia da saida invalida")
        with self._store.lock_tickets:
            for s in self._store.ticket_output.values():
                if s["ticket_id"] == int(ticket_id) and s["state"] == "AVAILABLE" and s["content"] is not None:
                    return bytes(s["content"][off:off + size_n])
        raise RepoNotFound("Saida do ticket %s indisponivel" % ticket_id)

    def _simular_log(self, t, sim):
        """Emula o log_pump e a finalizacao pelo agente em funcao do relogio injetavel (somente FAKE)."""
        now = self._store.now()
        elapsed = int((now - t["started_at"]).total_seconds())
        target = min(_STAGES_SIMULATED, max(0, elapsed // sim["step_s"]))
        cancel = t.get("cancel_requested") == "Y"
        if target <= sim["issued"] and not cancel:
            return
        rows = []
        for n in range(sim["issued"] + 1, target + 1):
            when = t["started_at"] + datetime.timedelta(seconds=n * sim["step_s"])
            rows.extend(_stage_lines(n, when, sim["sensitive_codes"]))
        sim["issued"] = target
        if cancel:
            rows.append("[%s] processo encerrado por cancelamento (SIGTERM)\n" % now)
            t.update(status="CANCELLED", status_reason="CANCEL_USER", return_code=-1)
        elif target >= _STAGES_SIMULATED:
            rows.append("[%s] Script concluido com retorno 0.\n" % now)
            t.update(status="SUCCESS", status_reason="EXIT_OK", return_code=0)
        if t["status"] != "RUNNING":
            t["finished_at"] = now
            # A finalizacao e do agente dono (README §8.7); o heartbeat e o log nao gravam updated_*.
            self._store.stamp_update(t, "SYSTEM:%s" % t.get("agent_id"))
            self._store.log_simulated.pop(t["id"], None)
        t["heartbeat_at"] = now
        t["log_output"] = (t.get("log_output") or "") + _mask_like_log_pump("".join(rows), sim["sensitive_codes"])
