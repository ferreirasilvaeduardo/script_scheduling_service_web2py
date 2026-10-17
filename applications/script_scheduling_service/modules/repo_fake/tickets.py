# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de tickets (README §2.5, §5, §10)."""
import copy
import datetime

import masking
from repo_errors import RepoNaoEncontrado, RepoViolacao
from repo_fake.store import paginar
from repo_tickets import RepoTickets


_ETAPAS_SIMULADAS = 50
_ETAPA_SEGREDO = 3
_ETAPA_HTML = 5


def _mascarar_como_log_pump(texto, sensiveis):
    # README §8.10: segredos carregados e valores de parametros sensiveis antes de anexar ao CLOB.
    local = masking.Mascarador()
    for _codigo, valor in sensiveis:
        local.registrar(valor)
    return masking.MASCARADOR.mascarar(local.mascarar(texto))


def _linhas_etapa(n, quando, sensiveis):
    linhas = ["[%s] etapa %d/%d processada\n" % (quando, n, _ETAPAS_SIMULADAS)]
    if n == _ETAPA_SEGREDO:
        for codigo, valor in sensiveis:
            linhas.append("[%s] conectando com %s=%s\n" % (quando, codigo, valor))
    elif n == _ETAPA_HTML:
        linhas.append("[%s] saida bruta do script: <script>alert(1)</script> <b>negrito</b>\n" % quando)
    return linhas


class RepoTicketsFake(RepoTickets):
    """Implementacao em memoria com semantica Oracle para tickets."""

    def __init__(self, store):
        self._store = store

    def agora(self):
        """Emula SYSDATE com o relogio injetavel do armazem."""
        return self._store.agora()

    def criar(self, ticket, respostas, ator=None):
        """Cria ticket e respostas vinculadas atomicamente, com auditoria TICKET_CRIAR ou TICKET_REEXECUTAR.

        created_by do ticket e das respostas: ator= ou, sem ele, o solicitante (CR-006, README §10).
        """
        with self._store.lock_tickets:
            script_id = int(ticket.get("script_id", 0))
            ambiente = ticket.get("ambiente")
            solicitante = ticket.get("solicitante")
            ator = self._store.ator_registro(ator=ator or solicitante)

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

            parent_id = ticket.get("parent_ticket_id")
            if parent_id is not None and parent_id not in self._store.tickets:
                raise RepoViolacao("ticket pai inexistente", constraint="fk_tbsss_tck_parent")
            # FKs e UK checadas antes de gravar qualquer linha: a operacao e atomica como no Oracle.
            self._store.checar_fk(script_id in self._store.scripts, "fk_tbsss_tck_scr")
            self._store.checar_fk(self._store.ambiente_existe(ambiente), "fk_tbsss_tck_amb")
            self._store.checar_fk(self._store.login_existe(solicitante), "fk_tbsss_tck_usr")
            vistos = set()
            for resp in (respostas or []):
                pid = int(resp["parametro_id"])
                self._store.checar_fk(pid in self._store.parametros, "fk_tbsss_trsp_prm")
                if pid in vistos:
                    raise RepoViolacao("resposta repetida para o parametro %s" % pid, constraint="uk_tbsss_trsp_tck_prm")
                vistos.add(pid)

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
                "parent_ticket_id": parent_id,
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
            self._store.carimbar_inclusao(novo_ticket, ator)
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
                self._store.carimbar_inclusao(nresp, ator)
                self._store.ticket_resp[rid] = copy.deepcopy(nresp)

            # Auditoria na mesma transacao (lock)
            if parent_id is None:
                acao = "TICKET_CRIAR"
                detalhe = "Ticket criado para script %s em %s" % (script_id, ambiente)
            else:
                acao = "TICKET_REEXECUTAR"
                detalhe = "Reexecucao do ticket %s para script %s em %s" % (parent_id, script_id, ambiente)
            self._store.registrar_auditoria_interno(
                ator=solicitante,
                ip=ticket.get("ip_origem"),
                acao=acao,
                entidade="tbsss_tickets",
                entidade_id=tid,
                detalhe=detalhe,
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
                lista = [t for t in lista if t.get("solicitante") == usr_f]

            par_f = filtros.get("parent_ticket_id")
            if par_f is not None:
                lista = [t for t in lista if t.get("parent_ticket_id") == int(par_f)]

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
                lista = [t for t in lista if t.get("created_at") and t["created_at"] < dt_fim]

            # Ordenacao estavel padrao: created_at DESC, id DESC
            lista.sort(key=lambda x: (x.get("created_at") or self._store.agora(), x["id"]), reverse=True)
            return paginar(lista, pagina=pagina, tamanho=tamanho)

    def ultimas_execucoes(self, script_ids, escopo_ambientes=None, solicitante=None):
        """Ultimo ticket de cada script no escopo, sem LOB (contrato RepoTickets)."""
        ids = set(int(i) for i in script_ids)
        ambs = None if escopo_ambientes is None else set(escopo_ambientes)
        with self._store.lock_tickets:
            melhores = {}
            for t in self._store.tickets.values():
                if t["script_id"] not in ids or (ambs is not None and t["ambiente"] not in ambs):
                    continue
                if solicitante is not None and t["solicitante"] != solicitante:
                    continue
                chave = (t["created_at"], t["id"])
                atual = melhores.get(t["script_id"])
                if atual is None or chave > (atual["created_at"], atual["id"]):
                    melhores[t["script_id"]] = t
            return dict((sid, {"id": t["id"], "status": t["status"], "status_motivo": t.get("status_motivo"),
                               "created_at": t["created_at"], "finished_at": t.get("finished_at")})
                        for sid, t in melhores.items())

    def historico_script(self, script_id, desde, escopo_ambientes=None, solicitante=None, limite=5000):
        """Tickets do script desde a data, no escopo, sem LOB (contrato RepoTickets)."""
        ambs = None if escopo_ambientes is None else set(escopo_ambientes)
        with self._store.lock_tickets:
            lista = [t for t in self._store.tickets.values()
                     if t["script_id"] == int(script_id) and t["created_at"] >= desde
                     and (ambs is None or t["ambiente"] in ambs)
                     and (solicitante is None or t["solicitante"] == solicitante)]
            lista.sort(key=lambda t: (t["created_at"], t["id"]))
            lista = lista[-int(limite):] if limite else lista
            return [dict((k, t.get(k)) for k in ("id", "status", "status_motivo", "created_at", "started_at",
                                                 "finished_at")) for t in lista]

    def respostas(self, ticket_id):
        """Retorna lista de dicts com respostas do ticket."""
        with self._store.lock_tickets:
            resps = [
                r for r in self._store.ticket_resp.values()
                if r["ticket_id"] == ticket_id
            ]
            resps.sort(key=lambda x: x["id"])
            return copy.deepcopy(resps)

    def solicitar_cancelamento(self, id, ator, ip):
        """Logica de cancelamento do no web (README §5.6), auditada em nome de quem cancelou.

        Cancelar ou sinalizar grava updated_* com o ator; as solicitacoes sem efeito nao (CR-006).
        """
        with self._store.lock_tickets:
            ator = self._store.ator_registro(ator=ator)
            if id not in self._store.tickets:
                raise RepoNaoEncontrado("Ticket ID %s nao encontrado" % id)

            t = self._store.tickets[id]
            st = t.get("status")

            def auditar(resultado):
                self._store.registrar_auditoria_interno(
                    ator=ator, ip=ip, acao="TICKET_CANCELAR", entidade="tbsss_tickets", entidade_id=id,
                    detalhe=u"resultado: %s" % resultado)

            if st not in ("PENDING", "RUNNING"):
                auditar(u"sem efeito: ticket encerrado")
                return "TERMINAL"
            if st == "RUNNING" and t.get("cancel_requested") == "S":
                auditar(u"já sinalizado")
                return "JA_SINALIZADO"

            if st == "PENDING":
                t["cancel_requested"] = "S"
                t["status"] = "CANCELLED"
                t["status_motivo"] = "CANCEL_USER"
                t["return_code"] = -1
                t["finished_at"] = self._store.agora()
                self._store.carimbar_alteracao(t, ator)

                auditar(u"cancelado")
                return "CANCELADO"

            if st == "RUNNING":
                t["cancel_requested"] = "S"
                self._store.carimbar_alteracao(t, ator)

                auditar(u"sinalizado")
                return "SINALIZADO"

    def log_ler(self, id, offset, max_chars):
        """Leitura incremental de log por offset e tamanho maximo."""
        with self._store.lock_tickets:
            if id not in self._store.tickets:
                raise RepoNaoEncontrado("Ticket ID %s nao encontrado" % id)

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
            truncado = t.get("log_truncado") == "S"

            return (texto, novo_offset, terminal, truncado)

    def _simular_log(self, t, sim):
        """Emula o log_pump e a finalizacao pelo agente em funcao do relogio injetavel (somente FAKE)."""
        agora = self._store.agora()
        decorrido = int((agora - t["started_at"]).total_seconds())
        alvo = min(_ETAPAS_SIMULADAS, max(0, decorrido // sim["passo_s"]))
        cancelar = t.get("cancel_requested") == "S"
        if alvo <= sim["emitidos"] and not cancelar:
            return
        linhas = []
        for n in range(sim["emitidos"] + 1, alvo + 1):
            quando = t["started_at"] + datetime.timedelta(seconds=n * sim["passo_s"])
            linhas.extend(_linhas_etapa(n, quando, sim["sensiveis"]))
        sim["emitidos"] = alvo
        if cancelar:
            linhas.append("[%s] processo encerrado por cancelamento (SIGTERM)\n" % agora)
            t.update(status="CANCELLED", status_motivo="CANCEL_USER", return_code=-1)
        elif alvo >= _ETAPAS_SIMULADAS:
            linhas.append("[%s] Script concluido com retorno 0.\n" % agora)
            t.update(status="SUCCESS", status_motivo="EXIT_OK", return_code=0)
        if t["status"] != "RUNNING":
            t["finished_at"] = agora
            # A finalizacao e do agente dono (README §8.7); o heartbeat e o log nao gravam updated_*.
            self._store.carimbar_alteracao(t, "SYSTEM:%s" % t.get("agente_id"))
            self._store.log_sim.pop(t["id"], None)
        t["heartbeat_at"] = agora
        t["log_output"] = (t.get("log_output") or "") + _mascarar_como_log_pump("".join(linhas), sim["sensiveis"])
