# -*- coding: utf-8 -*-
"""Repositorio interno do daemon para o desdobro dos agendamentos (README §7.5; F8.4; CR-003 D1, D2; CR-006;
CR-007 R-05, R-08, R-19, R-27; CR-008 R-03, R-19, R-22, R-31).

Fora do contrato da UI e sem gluon (processo batch, sem FAKE; README §2.5). SQL literal do README §7.5, com
owner e prefixo da configuracao e identificadores por sql_ident. **Nenhuma operacao faz COMMIT nem ROLLBACK:**
todas recebem a conexao da transacao da regra, e o COMMIT unico e do passo 8 (quem chama). Toda data vai
como TIPO_DATE e sem microssegundos; a antiga_data e usada exatamente como lida do banco.

Colunas de registro (CR-006): o ticket e o ticket_resp do desdobro nascem com created_by = 'SYSTEM:<agent_id>';
a reserva e o avanco sem ticket sao rotina tecnica (sem updated_*); pausa e conclusao gravam updated_*.
"""
import datetime

import db_conn
import sql_ident

# Primeira pagina (README §7.5): :ult_prox = DATE '0001-01-01' e :ult_id = 0.
DATA_INICIAL = datetime.datetime(1, 1, 1)
DETALHE_MAX = 1000
ATOR_MAX = 40
_ORA_DUPLICADO = 1

_COLS_REGRA = ("id", "name", "script_id", "environment", "user_id", "priority", "recurrence_type",
               "cron_expression", "run_time", "week_days", "month_day", "params_json", "start_date",
               "end_date", "next_run_at", "last_run_at", "last_ticket_id", "pause_reason", "active",
               "created_at", "created_by", "updated_at", "updated_by")
_COLS_SCRIPT = ("id", "name", "interpreter", "path_file", "param_type", "max_parallel_env", "timeout_s",
                "active")
_COLS_PRM = ("id", "code", "param_flag", "label", "description", "component_type", "options_json",
             "default_value", "validation_regex", "sensitive", "active")
_CHAR1 = ("active", "sensitive", "required")


class OcorrenciaDuplicada(RuntimeError):
    """ORA-00001 em ix_tck_ocor: outro caminho ja gerou o ticket desta ocorrencia (README §7.5 passo 6, R-31)."""


def ator_sistema(agente_id):
    return "SYSTEM:%s" % agente_id


def sem_microssegundos(valor):
    return valor.replace(microsecond=0) if valor is not None and hasattr(valor, "replace") else valor


def _ler_lob(valor):
    return valor.read() if hasattr(valor, "read") else valor


def _limpo(chave, valor):
    return valor.strip() if chave in _CHAR1 and isinstance(valor, str) else valor


class RepoSchedulerAgenda(object):
    """Owner e prefixo vem da configuracao (nunca fixos); os nomes passam por sql_ident."""

    def __init__(self, owner, prefixo):
        t = lambda nome: sql_ident.tabela(owner, prefixo, nome)  # noqa: E731
        s = lambda nome: sql_ident.sequence(owner, prefixo, nome)  # noqa: E731
        self._agd, self._tck, self._resp, self._aud = t("agendamentos"), t("tickets"), t("ticket_resp"), t("auditoria")
        self._scr, self._amb, self._usr, self._samb = t("scripts"), t("ambientes"), t("usuarios"), t("script_amb")
        self._sprm, self._prm = t("script_param"), t("parametros")
        self._seq_tck, self._seq_resp, self._seq_aud = s("tickets"), s("ticket_resp"), s("auditoria")
        self._ocor = "ix_%stck_occur" % prefixo

    @classmethod
    def da_config(cls, cfg):
        return cls(cfg.oracle.owner.strip(), cfg.oracle.table_prefix.strip())

    # ------------------------------------------------------------------ util

    def _executar(self, conn, sql, binds, datas=()):
        """Executa com os binds de data declarados como TIPO_DATE (README §7.5, "Bind de datas")."""
        cur = conn.cursor()
        try:
            if datas:
                db_conn.definir_tipos_entrada(cur, **dict((d, db_conn.TIPO_DATE) for d in datas))
            cur.execute(sql, binds)
            return cur.rowcount
        finally:
            cur.close()

    def _auditar(self, conn, ator, regra_id, detalhe):
        """SCHEDULE_PAUSE da pausa e da conclusao (README §4.4), na mesma transacao."""
        if not ator or len(ator) > ATOR_MAX or (detalhe is not None and len(detalhe) > DETALHE_MAX):
            raise ValueError("ator ou detalhe de auditoria fora do limite")
        self._executar(conn, "INSERT INTO " + self._aud + " (id, actor, source_ip, action, entity, entity_id, "
                       "detail, created_at) VALUES (:id, :actor, NULL, 'SCHEDULE_PAUSE', 'tbsss_schedules', :rid, "
                       ":detail, SYSDATE)",
                       {"id": db_conn.proximo_id(conn, self._seq_aud), "actor": ator, "rid": int(regra_id),
                        "detail": detalhe})

    # ------------------------------------------------------------------ leitura

    def regras_vencidas(self, conn, lote, ult_prox=None, ult_id=0):
        """Pagina de (id, proxima_execucao) vencidas, depois de (ult_prox, ult_id) (README §7.5, R-08)."""
        cur = conn.cursor()
        try:
            db_conn.definir_tipos_entrada(cur, ult_prox=db_conn.TIPO_DATE)
            cur.execute("SELECT id, next_run_at FROM ("
                        " SELECT id, next_run_at FROM " + self._agd +
                        " WHERE active = 'Y' AND next_run_at <= SYSDATE"
                        " AND (next_run_at > :ult_prox OR (next_run_at = :ult_prox AND id > :ult_id))"
                        " ORDER BY next_run_at, id"
                        ") WHERE ROWNUM <= :lote",
                        {"ult_prox": sem_microssegundos(ult_prox or DATA_INICIAL), "ult_id": int(ult_id),
                         "lote": int(lote)})
            return [(int(r[0]), r[1]) for r in cur.fetchall()]
        finally:
            cur.close()

    def travar_regra(self, conn, regra_id):
        """FOR UPDATE SKIP LOCKED: False = outro agente esta processando a regra (ou ela ja mudou)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT id FROM " + self._agd + " WHERE id = :id AND active = 'Y' AND next_run_at <= SYSDATE"
                        " FOR UPDATE SKIP LOCKED", {"id": int(regra_id)})
            return cur.fetchone() is not None
        finally:
            cur.close()

    def carregar_regra(self, conn, regra_id):
        """Regra completa (passo 1); proxima_execucao exatamente como o banco a devolveu (a antiga_data)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT " + ", ".join(_COLS_REGRA) + " FROM " + self._agd + " WHERE id = :id",
                        {"id": int(regra_id)})
            r = cur.fetchone()
        finally:
            cur.close()
        if r is None:
            return None
        regra = dict((c, _limpo(c, v)) for c, v in zip(_COLS_REGRA, r))
        regra["params_json"] = _ler_lob(regra["params_json"])
        for c in ("recurrence_type", "pause_reason"):
            if isinstance(regra.get(c), str):
                regra[c] = regra[c].strip()
        return regra

    def login_do_usuario(self, conn, usuario_id):
        cur = conn.cursor()
        try:
            cur.execute("SELECT login FROM " + self._usr + " WHERE id = :id", {"id": int(usuario_id)})
            r = cur.fetchone()
            return r[0] if r else None
        finally:
            cur.close()

    def script_e_vinculos(self, conn, script_id):
        """(script, vinculos) para a compilacao do snapshot v4 (README §6.5) e o teto/timeout do script."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT " + ", ".join(_COLS_SCRIPT) + " FROM " + self._scr + " WHERE id = :id",
                        {"id": int(script_id)})
            r = cur.fetchone()
            if r is None:
                return None, []
            script = dict((c, _limpo(c, v)) for c, v in zip(_COLS_SCRIPT, r))
            cur.execute("SELECT " + ", ".join("p." + c for c in _COLS_PRM) + ", sp.sort_order, sp.required,"
                        " sp.default_value_override FROM " + self._sprm + " sp JOIN " + self._prm + " p ON p.id = sp.parameter_id"
                        " WHERE sp.script_id = :id ORDER BY sp.sort_order, sp.id", {"id": int(script_id)})
            cols = _COLS_PRM + ("sort_order", "required", "default_value_override")
            vinculos = []
            for linha in cur.fetchall():
                v = dict((c, _limpo(c, _ler_lob(x))) for c, x in zip(cols, linha))
                v["parameter_id"] = v["id"]
                v["script_id"] = int(script_id)
                vinculos.append(v)
            return script, vinculos
        finally:
            cur.close()

    def status_ticket(self, conn, ticket_id):
        """(status, created_at) do ticket, ou None se inexistente (purgado = livre; README §7.5 passo 4)."""
        cur = conn.cursor()
        try:
            cur.execute("SELECT status, created_at FROM " + self._tck + " WHERE id = :id", {"id": int(ticket_id)})
            r = cur.fetchone()
            return ((r[0] or "").strip(), r[1]) if r else None
        finally:
            cur.close()

    def proximo_ticket_id(self, conn):
        return db_conn.proximo_id(conn, self._seq_tck)

    # ------------------------------------------------------------------ escrita do ticket

    def _inserir_ticket(self, conn, regra, ticket_id, ticket, respostas, ator):
        """INSERT do ticket e do ticket_resp (README §7.5 passo 6): schedule_id, source_ip NULL,
        scheduled_at = ocorrencia (CR-007 R-27, CR-008 R-03). ORA-00001 em ix_tck_ocor: OcorrenciaDuplicada."""
        cur = conn.cursor()
        try:
            db_conn.definir_tipos_entrada(cur, scheduled_at=db_conn.TIPO_DATE, parametros=db_conn.TIPO_CLOB)
            try:
                cur.execute("INSERT INTO " + self._tck + " (id, script_id, environment, requested_by, source_ip, status,"
                            " priority, cancel_requested, schedule_id, submitted_params, log_offset_chars,"
                            " log_truncated, scheduled_at, created_at, created_by)"
                            " VALUES (:id, :script_id, :environment, :requested_by, NULL, 'PENDING', :priority, 'N',"
                            " :schedule_id, :parametros, 0, 'N', :scheduled_at, SYSDATE, :actor)",
                            {"id": int(ticket_id), "script_id": int(regra["script_id"]), "environment": regra["environment"],
                             "requested_by": ticket["requested_by"], "priority": int(ticket["priority"]),
                             "schedule_id": int(regra["id"]), "parametros": ticket["submitted_params"],
                             "scheduled_at": sem_microssegundos(ticket["scheduled_at"]), "actor": ator})
            except Exception as exc:
                if db_conn.classificar_erro(exc) == ("ORA", _ORA_DUPLICADO) and self._ocor.upper() in str(exc).upper():
                    raise OcorrenciaDuplicada(str(exc))
                raise
        finally:
            cur.close()
        for linha in respostas or ():
            self._executar(conn, "INSERT INTO " + self._resp + " (id, ticket_id, parameter_id, answer_value,"
                           " created_at, created_by, updated_at, updated_by) VALUES (:id, :ticket_id, :parameter_id,"
                           " :valor, SYSDATE, :actor, NULL, NULL)",
                           {"id": db_conn.proximo_id(conn, self._seq_resp), "ticket_id": int(ticket_id),
                            "parameter_id": int(linha["parameter_id"]), "valor": linha["answer_value"],
                            "actor": ator})

    def reservar_e_criar_ticket(self, conn, regra, antiga, nova, ticket_id, ticket, respostas, agente_id):
        """Passo 6: reserva otimista (rotina tecnica, sem updated_*) e, com rowcount 1, o INSERT do ticket e do
        ticket_resp. False = outro no processou a regra (rowcount 0; quem chama faz ROLLBACK)."""
        n = self._executar(conn, "UPDATE " + self._agd + " SET next_run_at = :nova_data, last_run_at = SYSDATE,"
                           " last_ticket_id = :ticket_id WHERE id = :id AND active = 'Y'"
                           " AND next_run_at = :antiga_data",
                           {"nova_data": sem_microssegundos(nova), "ticket_id": int(ticket_id), "id": int(regra["id"]),
                            "antiga_data": antiga}, datas=("nova_data", "antiga_data"))
        if n != 1:
            return False
        self._inserir_ticket(conn, regra, ticket_id, ticket, respostas, ator_sistema(agente_id))
        return True

    def concluir_com_ticket(self, conn, regra, antiga, ticket_id, ticket, respostas, agente_id):
        """Conclusao (README §7.5, D1) com o ticket da ocorrencia atual: um UPDATE so, next_run_at mantida."""
        ator = ator_sistema(agente_id)
        n = self._executar(conn, "UPDATE " + self._agd + " SET active = 'N', pause_reason = 'COMPLETED',"
                           " last_run_at = SYSDATE, last_ticket_id = :ticket_id, updated_at = SYSDATE,"
                           " updated_by = :actor WHERE id = :id AND active = 'Y' AND next_run_at = :antiga_data",
                           {"ticket_id": int(ticket_id), "actor": ator, "id": int(regra["id"]), "antiga_data": antiga},
                           datas=("antiga_data",))
        if n != 1:
            return False
        self._inserir_ticket(conn, regra, ticket_id, ticket, respostas, ator)
        self._auditar(conn, ator, regra["id"], "pause_reason: COMPLETED")
        return True

    def concluir_sem_ticket(self, conn, regra_id, antiga, agente_id):
        """Conclusao sem ticket (SKIP fora da tolerancia em UNICA, ou sobreposicao): so ativo, pausa_motivo e
        updated_*; ultima_execucao e ultimo_ticket_id nao mudam."""
        ator = ator_sistema(agente_id)
        n = self._executar(conn, "UPDATE " + self._agd + " SET active = 'N', pause_reason = 'COMPLETED',"
                           " updated_at = SYSDATE, updated_by = :actor WHERE id = :id AND active = 'Y'"
                           " AND next_run_at = :antiga_data",
                           {"actor": ator, "id": int(regra_id), "antiga_data": antiga}, datas=("antiga_data",))
        if n != 1:
            return False
        self._auditar(conn, ator, regra_id, "pause_reason: COMPLETED")
        return True

    def avancar_sem_ticket(self, conn, regra_id, antiga, nova):
        """Avanco sem ticket (CR-007, R-05): so proxima_execucao, sem ultima_execucao, ultimo_ticket_id nem
        updated_* (rotina tecnica)."""
        return self._executar(conn, "UPDATE " + self._agd + " SET next_run_at = :nova_data WHERE id = :id"
                              " AND active = 'Y' AND next_run_at = :antiga_data",
                              {"nova_data": sem_microssegundos(nova), "id": int(regra_id), "antiga_data": antiga},
                              datas=("nova_data", "antiga_data")) == 1

    def pausar(self, conn, regra_id, antiga, motivo, detalhe, agente_id):
        """Passo 7: pausa otimista so de regra ativa (CR-007, R-19), com SCHEDULE_PAUSE. False = ja pausada ou
        concluida por outro caminho (sem auditoria)."""
        ator = ator_sistema(agente_id)
        n = self._executar(conn, "UPDATE " + self._agd + " SET active = 'N', pause_reason = :reason, updated_at = SYSDATE,"
                           " updated_by = :actor WHERE id = :id AND active = 'Y' AND next_run_at = :antiga_data",
                           {"reason": motivo, "actor": ator, "id": int(regra_id), "antiga_data": antiga},
                           datas=("antiga_data",))
        if n != 1:
            return False
        self._auditar(conn, ator, regra_id, "pause_reason: %s%s" % (motivo, "; " + detalhe if detalhe else ""))
        return True

    def pausar_cron_erro(self, conn, regra, antiga, ticket_id, ticket, respostas, detalhe, agente_id):
        """Variante cron_erro (CR-008, R-19): pausa INVALID_CRON no UPDATE otimista, mantendo next_run_at;
        com ticket (ticket_id nao nulo), o INSERT do ticket e do ticket_resp em seguida."""
        ator = ator_sistema(agente_id)
        n = self._executar(conn, "UPDATE " + self._agd + " SET active = 'N', pause_reason = 'INVALID_CRON',"
                           " last_run_at = CASE WHEN :ticket_id IS NULL THEN last_run_at ELSE SYSDATE END,"
                           " last_ticket_id = NVL(:ticket_id, last_ticket_id), updated_at = SYSDATE,"
                           " updated_by = :actor WHERE id = :id AND active = 'Y' AND next_run_at = :antiga_data",
                           {"ticket_id": None if ticket_id is None else int(ticket_id), "actor": ator,
                            "id": int(regra["id"]), "antiga_data": antiga}, datas=("antiga_data",))
        if n != 1:
            return False
        if ticket_id is not None:
            self._inserir_ticket(conn, regra, ticket_id, ticket, respostas, ator)
        self._auditar(conn, ator, regra["id"], "pause_reason: INVALID_CRON%s" % ("; " + detalhe if detalhe else ""))
        return True

    def pausar_erro_interno(self, conn, regra_id, detalhe, agente_id):
        """INTERNAL_ERROR (CR-007 R-08; CR-008 R-22) numa transacao separada, depois do ROLLBACK da regra: so
        regra ativa, sem conferir a data (a regra pode nem ter sido lida)."""
        ator = ator_sistema(agente_id)
        n = self._executar(conn, "UPDATE " + self._agd + " SET active = 'N', pause_reason = 'INTERNAL_ERROR',"
                           " updated_at = SYSDATE, updated_by = :actor WHERE id = :id AND active = 'Y'",
                           {"actor": ator, "id": int(regra_id)})
        if n != 1:
            return False
        self._auditar(conn, ator, regra_id, "pause_reason: INTERNAL_ERROR%s" % ("; " + detalhe if detalhe else ""))
        return True
