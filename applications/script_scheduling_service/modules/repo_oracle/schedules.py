# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de agendamentos (F7.3, agregado AGENDAMENTOS; AGENTS §4).

tbsss_schedules com a mesma semantica do repo_fake/schedules.py (README §2.5):
- SQL estatico com binds; os modelos ficam nas constantes abaixo e recebem, uma vez por instancia,
  somente identificadores qualificados por sql_ident (owner e prefixo validados);
- CKs e FKs conferidas antes do DML, na ordem do FAKE e com os mesmos nomes (sem gravacao parcial);
- pausar condicional a ativo = 'S' e, quando informada, a proxima_execucao lida (CR-007, R-19):
  rowcount = 0 vira RepoConflict; binds de DATE como TIPO_DATE (README §7.5), sem microssegundos;
- colunas de registro (CR-006, R-g): created_* e o criador original; alterar, pausar e retomar
  gravam updated_* com o ator;
- listar traz parametros_json (CLOB pequeno com as respostas): excecao documentada no README §2.5,
  porque o service avalia cada regra com ele; log_output nunca entra em listagem.
"""
import datetime
import re

import db_conn
import repo_errors
from repo_schedules import RepoSchedules
from repo_oracle.base import BaseRepoOracle, write_audit, validate_record_actor

_LIMIT_TOTAL = 10001
_TYPES = ("ONCE", "DAILY", "WEEKLY", "MONTHLY", "CRON")
_REASONS_PAUSE = ("USER_INACTIVE", "NO_PERMISSION", "SCRIPT_INACTIVE", "ENVIRONMENT_INACTIVE",
                  "INVALID_PARAM", "INVALID_CRON", "COMPLETED", "MANUAL", "INTERNAL_ERROR")
_RE_TIME = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
_RE_WDAY = re.compile(r"^[1-7](,[1-7]){0,6}$")
_SIZE_NAME = 60

_COLS = ("id", "name", "script_id", "environment", "user_id", "priority", "recurrence_type",
         "cron_expression", "run_time", "week_days", "month_day", "params_json", "start_date",
         "end_date", "next_run_at", "last_run_at", "last_ticket_id", "pause_reason", "active",
         "created_at", "created_by", "updated_at", "updated_by")
_COLUMNS_UPDATABLE = ("name", "script_id", "environment", "user_id", "priority",
                       "recurrence_type", "cron_expression", "run_time", "week_days",
                       "month_day", "params_json", "start_date", "end_date",
                       "next_run_at", "last_run_at", "last_ticket_id",
                       "pause_reason", "active")
_DATES = ("start_date", "end_date", "next_run_at", "last_run_at")


def _column_list(cols, alias=""):
    return ", ".join(alias + c for c in cols)


# -----------------------------------------------------------------------------
# SQL estatico. {agd}, {scr}, {usr}, {amb} e {tck} recebem apenas nomes qualificados por sql_ident
# (validados); todo valor entra por bind.
# -----------------------------------------------------------------------------

_SQL_GET = "SELECT " + _column_list(_COLS) + " FROM {agd} WHERE id = :id"
_SQL_GET_LOCK = _SQL_GET + " FOR UPDATE WAIT 5"
_SQL_EXISTS = "SELECT id FROM {agd} WHERE id = :id"
_SQL_LIST = "SELECT " + _column_list(_COLS) + " FROM {agd}{where} ORDER BY next_run_at, id"
_SQL_COUNT = "SELECT COUNT(*) FROM (SELECT id FROM {agd} WHERE {where_count})"
_SQL_SCR_EXISTS = "SELECT id FROM {scr} WHERE id = :id"
_SQL_USR_EXISTS = "SELECT id FROM {usr} WHERE id = :id"
_SQL_ENV_EXISTS = "SELECT id FROM {amb} WHERE name = :name"
_SQL_TICKET_STATUS = "SELECT status FROM {tck} WHERE id = :id"
_SQL_INSERT = (
    "INSERT INTO {agd} (id, name, script_id, environment, user_id, priority, recurrence_type, "
    "cron_expression, run_time, week_days, month_day, params_json, start_date, end_date, "
    "next_run_at, last_run_at, last_ticket_id, pause_reason, active, "
    "created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :name, :script_id, :environment, :user_id, :priority, :recurrence_type, "
    ":cron_expression, :run_time, :week_days, :month_day, :params_json, :start_date, :end_date, "
    ":next_run_at, :last_run_at, :last_ticket_id, :pause_reason, :active, "
    "SYSDATE, :actor, NULL, NULL)"
)
_SQL_UPDATE = (
    "UPDATE {agd} SET name = :name, script_id = :script_id, environment = :environment, user_id = :user_id, "
    "priority = :priority, recurrence_type = :recurrence_type, cron_expression = :cron_expression, "
    "run_time = :run_time, week_days = :week_days, month_day = :month_day, "
    "params_json = :params_json, start_date = :start_date, end_date = :end_date, "
    "next_run_at = :next_run_at, last_run_at = :last_run_at, "
    "last_ticket_id = :last_ticket_id, pause_reason = :pause_reason, active = :active, "
    "updated_at = SYSDATE, updated_by = :actor WHERE id = :id"
)
# CR-007, R-19: so pausa regra ativa e, com antiga_data, so se a proxima_execucao lida nao mudou.
_SQL_PAUSE = (
    "UPDATE {agd} SET active = 'N', pause_reason = :reason, updated_at = SYSDATE, updated_by = :actor "
    "WHERE id = :id AND active = 'Y'"
)
_SQL_PAUSE_OPTIMISTIC = _SQL_PAUSE + " AND next_run_at = :antiga_data"
_SQL_RESUME = (
    "UPDATE {agd} SET active = 'Y', pause_reason = NULL, next_run_at = :nova_data, "
    "updated_at = SYSDATE, updated_by = :actor WHERE id = :id"
)


def _null(valor):
    # O Oracle grava '' como NULL.
    return valor is None or valor == ""


def _equal(atual, esperado):
    """Comparacao nula-segura do 'esperado' ('' e NULL no Oracle; DATE sem fracao)."""
    if atual == "":
        atual = None
    if esperado == "":
        esperado = None
    if isinstance(atual, datetime.datetime) and isinstance(esperado, datetime.datetime):
        return atual.replace(microsecond=0) == esperado.replace(microsecond=0)
    return atual == esperado


def _read_lob(valor):
    if valor is not None and hasattr(valor, "read"):
        return valor.read()
    return valor


class RepoSchedulesOracle(BaseRepoOracle, RepoSchedules):
    """Repositorio de agendamentos com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, segredos=None):
        super(RepoSchedulesOracle, self).__init__(cfg=cfg, segredos=segredos)
        self._idents = {
            "agd": self.qualify_table("schedules"),
            "scr": self.qualify_table("scripts"),
            "usr": self.qualify_table("users"),
            "amb": self.qualify_table("environments"),
            "tck": self.qualify_table("tickets"),
        }
        self._sql = {}
        for nome, modelo in globals().items():
            if nome.startswith("_SQL_") and "{where" not in modelo:
                self._sql[nome[5:]] = modelo.format(**self._idents)
        self._tbl_aud = self.qualify_table("audit")
        self._seq_aud = self.qualify_sequence("audit")
        self._seq_agd = self.qualify_sequence("schedules")

    # -------------------------------------------------------------------------
    # Utilitarios
    # -------------------------------------------------------------------------

    def _ck(self, sufixo):
        return self.constraint_name("ck", "schedules", sufixo)

    def _checar_cks(self, r):
        """Espelha NOT NULL e as CKs de tbsss_schedules (README §10, tabela 12), na ordem do FAKE."""
        nome = r.get("name")
        if _null(nome) or len(nome) > _SIZE_NAME:
            # NOT NULL e tamanho da coluna nao sao constraints nomeadas (ORA-01400 / ORA-12899).
            raise repo_errors.RepoViolation("nome obrigatorio com ate %d caracteres" % _SIZE_NAME)
        trec = r.get("recurrence_type")
        if trec not in _TYPES:
            raise repo_errors.RepoViolation("tipo_recorrencia invalido", constraint=self._ck("rtype"))
        prio = r.get("priority")
        if isinstance(prio, bool) or not isinstance(prio, int) or not (1 <= prio <= 4):
            raise repo_errors.RepoViolation("prioridade deve estar entre 1 e 4", constraint=self._ck("prio"))
        if r.get("active") not in ("Y", "N"):
            raise repo_errors.RepoViolation("ativo deve ser 'Y' ou 'N'", constraint=self._ck("active"))
        dia = r.get("month_day")
        if not _null(dia) and (isinstance(dia, bool) or not isinstance(dia, int) or not (1 <= dia <= 31)):
            raise repo_errors.RepoViolation("dia_mes deve estar entre 1 e 31", constraint=self._ck("day"))
        hora = r.get("run_time")
        if not _null(hora) and not _RE_TIME.match(hora):
            raise repo_errors.RepoViolation("hora_execucao fora do formato HH:MM", constraint=self._ck("time"))
        dsem = r.get("week_days")
        if not _null(dsem) and not _RE_WDAY.match(dsem):
            raise repo_errors.RepoViolation("dias_semana fora do formato ISO 1-7", constraint=self._ck("wday"))
        if r.get("start_date") is None or r.get("next_run_at") is None:
            raise repo_errors.RepoViolation("data_inicio e proxima_execucao sao obrigatorias")
        if r.get("end_date") is not None and r["end_date"] < r["start_date"]:
            raise repo_errors.RepoViolation("data_fim anterior a data_inicio", constraint=self._ck("end"))
        if not _null(r.get("pause_reason")) and r["pause_reason"] not in _REASONS_PAUSE:
            raise repo_errors.RepoViolation("pausa_motivo invalido", constraint=self._ck("pause"))
        exigidos = {"DAILY": ("run_time",), "WEEKLY": ("run_time", "week_days"),
                    "MONTHLY": ("run_time", "month_day"), "CRON": ("cron_expression",)}
        for coluna in exigidos.get(trec, ()):
            if _null(r.get(coluna)):
                raise repo_errors.RepoViolation("%s obrigatorio para %s" % (coluna, trec),
                                               constraint=self._ck("fields"))

    def _existe(self, conn, sql, binds):
        cur = conn.cursor()
        try:
            cur.execute(sql, binds)
            return cur.fetchone() is not None
        finally:
            cur.close()

    def _checar_fks(self, conn, reg):
        for existe, sufixo in (
            (self._existe(conn, self._sql["SCR_EXISTS"], {"id": int(reg["script_id"])}), "scr"),
            (self._existe(conn, self._sql["USR_EXISTS"], {"id": int(reg["user_id"])}), "usr"),
            (self._existe(conn, self._sql["ENV_EXISTS"], {"name": reg["environment"]}), "env"),
        ):
            if not existe:
                constraint = self.constraint_name("fk", "schedules", sufixo)
                raise repo_errors.RepoViolation("Referencia inexistente (%s)" % constraint, constraint=constraint)

    def _linha(self, row):
        reg = self.tuple_to_dict(_COLS, row[:len(_COLS)])
        reg["params_json"] = _read_lob(reg["params_json"])
        return reg

    def _uma(self, conn, sql, binds):
        cur = conn.cursor()
        try:
            cur.execute(sql, binds)
            row = cur.fetchone()
            return self._linha(row) if row else None
        finally:
            cur.close()

    def _binds_registro(self, reg, ator):
        binds = dict((c, reg.get(c)) for c in _COLUMNS_UPDATABLE)
        binds["script_id"] = int(reg["script_id"])
        binds["user_id"] = int(reg["user_id"])
        binds["actor"] = ator
        return binds

    @staticmethod
    def _tipos(cur):
        tipos = dict((c, db_conn.TIPO_DATE) for c in _DATES)
        tipos["params_json"] = db_conn.TIPO_CLOB
        db_conn.set_input_types(cur, **tipos)

    def _auditar(self, conn, auditoria, id, acao_padrao=None, detalhe_padrao=None, ator=None):
        if auditoria:
            write_audit(conn, self._tbl_aud, self._seq_aud, auditoria, "tbsss_schedules", id)
        elif acao_padrao:
            write_audit(conn, self._tbl_aud, self._seq_aud,
                             {"actor": ator, "ip": None, "action": acao_padrao, "detail": detalhe_padrao},
                             "tbsss_schedules", id)

    def _conferir_esperado(self, id, atual, esperado):
        for campo, valor in (esperado or {}).items():
            if not _equal(atual.get(campo), valor):
                raise repo_errors.RepoConflict("Agendamento ID %s alterado por outra operacao (%s)" % (id, campo))

    # -------------------------------------------------------------------------
    # Leituras
    # -------------------------------------------------------------------------

    def list(self, filtros=None, pagina=1, tamanho=20, escopo_ambientes=None, conn=None):
        """Lista por proxima_execucao, id, com total limitado a 10.001 (traz parametros_json, sem log)."""
        filtros = filtros or {}
        clausulas, binds = [], {}
        if escopo_ambientes is not None:
            ambs = sorted(set(escopo_ambientes))
            if not ambs:
                clausulas.append("1 = 0")
            else:
                marcas = []
                for n, amb in enumerate(ambs):
                    binds["e%d" % n] = amb
                    marcas.append(":e%d" % n)
                clausulas.append("environment IN (" + ", ".join(marcas) + ")")
        if filtros.get("active"):
            clausulas.append("active = :ativo_f")
            binds["ativo_f"] = filtros["active"]
        if filtros.get("script_id") is not None:
            clausulas.append("script_id = :script_id_f")
            binds["script_id_f"] = int(filtros["script_id"])
        if filtros.get("environment"):
            clausulas.append("environment = :ambiente_f")
            binds["ambiente_f"] = filtros["environment"]
        if filtros.get("user_id") is not None:
            clausulas.append("user_id = :usuario_id_f")
            binds["usuario_id_f"] = int(filtros["user_id"])
        if filtros.get("name"):
            # '%' e '_' digitados contam como literais, como o 'in' do FAKE.
            trecho = filtros["name"].lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clausulas.append("LOWER(name) LIKE :nome_f ESCAPE '\\'")
            binds["nome_f"] = "%" + trecho + "%"

        p = 1 if pagina is None else int(pagina)
        t = 20 if tamanho is None else int(tamanho)
        if p < 1:
            p = 1
        if t < 1:
            t = 20
        inicio = (p - 1) * t
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        where_count = " AND ".join(clausulas + ["ROWNUM <= " + str(_LIMIT_TOTAL)])
        sql_conta = _SQL_COUNT.format(where_count=where_count, **self._idents)
        sql_pag = (
            "SELECT * FROM (SELECT a.*, ROWNUM rn FROM (" + _SQL_LIST.format(where=where, **self._idents) + ") a "
            "WHERE ROWNUM <= :fim) WHERE rn > :inicio"
        )
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql_conta, binds)
                bruto = cur.fetchone()[0]
                binds_pag = dict(binds)
                binds_pag["inicio"] = inicio
                binds_pag["fim"] = inicio + t
                cur.execute(sql_pag, binds_pag)
                itens = [self._linha(r) for r in cur.fetchall()]
            finally:
                cur.close()
        return {
            "itens": itens,
            "total": min(bruto, _LIMIT_TOTAL),
            "pagina": p,
            "tamanho": t,
            "total_limitado": bruto >= _LIMIT_TOTAL,
        }

    def get(self, id, conn=None):
        """Agendamento pela PK ou RepoNotFound."""
        with self.read_context(conn=conn) as c:
            reg = self._uma(c, self._sql["GET"], {"id": int(id)})
        if reg is None:
            raise repo_errors.RepoNotFound("Agendamento ID %s nao encontrado" % id)
        return reg

    def ticket_status(self, ticket_id, conn=None):
        """Status atual do ticket ou None se inexistente (README §7.5 passo 4)."""
        if ticket_id is None:
            return None
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["TICKET_STATUS"], {"id": int(ticket_id)})
                row = cur.fetchone()
            finally:
                cur.close()
        return row[0].strip() if row and row[0] else None

    # -------------------------------------------------------------------------
    # Gravacoes
    # -------------------------------------------------------------------------

    def insert(self, dados, auditoria=None, ator=None, conn=None):
        """Insere com as CKs e FKs conferidas antes do INSERT e a auditoria na mesma transacao."""
        ator_limpo = validate_record_actor(auditoria, ator)
        with self.write_transaction(conn=conn) as c:
            agora = db_conn.db_now(c)
            novo = {
                "name": dados.get("name"),
                "script_id": int(dados["script_id"]),
                "environment": dados["environment"],
                "user_id": int(dados["user_id"]),
                "priority": dados.get("priority", 2),
                "recurrence_type": dados.get("recurrence_type"),
                "cron_expression": dados.get("cron_expression"),
                "run_time": dados.get("run_time"),
                "week_days": dados.get("week_days"),
                "month_day": dados.get("month_day"),
                "params_json": dados.get("params_json", "{}"),
                "start_date": dados.get("start_date") or agora,
                "end_date": dados.get("end_date"),
                "next_run_at": dados.get("next_run_at") or agora,
                "last_run_at": dados.get("last_run_at"),
                "last_ticket_id": dados.get("last_ticket_id"),
                "pause_reason": dados.get("pause_reason"),
                "active": dados.get("active", "Y"),
            }
            self._checar_cks(novo)
            self._checar_fks(c, novo)
            aid = db_conn.next_id(c, self._seq_agd)
            binds = self._binds_registro(novo, ator_limpo)
            binds["id"] = aid
            cur = c.cursor()
            try:
                self._tipos(cur)
                cur.execute(self._sql["INSERT"], binds)
            finally:
                cur.close()
            self._auditar(c, auditoria, aid)
            return self.get(aid, conn=c)

    def update(self, id, dados, esperado=None, auditoria=None, ator=None, conn=None):
        """Altera a regra (usuario_id do editor), condicional a 'esperado'; created_* nunca muda."""
        ator_limpo = validate_record_actor(auditoria, ator)
        with self.write_transaction(conn=conn) as c:
            atual = self._uma(c, self._sql["GET_LOCK"], {"id": int(id)})
            if atual is None:
                raise repo_errors.RepoNotFound("Agendamento ID %s nao encontrado" % id)
            self._conferir_esperado(id, atual, esperado)
            resultado = dict(atual)
            for k in _COLUMNS_UPDATABLE:
                if k in dados:
                    resultado[k] = dados[k]
            # Validacao completa antes do UPDATE: um UPDATE rejeitado nao altera nenhuma coluna.
            self._checar_cks(resultado)
            self._checar_fks(c, resultado)
            binds = self._binds_registro(resultado, ator_limpo)
            binds["id"] = int(id)
            cur = c.cursor()
            try:
                self._tipos(cur)
                cur.execute(self._sql["UPDATE"], binds)
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflict("Agendamento ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, auditoria, int(id))
            return self.get(id, conn=c)

    def pause(self, id, motivo, antiga_data=None, auditoria=None, ator=None, conn=None):
        """Pausa so regra ativa e, com antiga_data, so se a proxima_execucao nao mudou (CR-007, R-19)."""
        ator_limpo = validate_record_actor(auditoria, ator)
        with self.write_transaction(conn=conn) as c:
            if not self._existe(c, self._sql["EXISTS"], {"id": int(id)}):
                raise repo_errors.RepoNotFound("Agendamento ID %s nao encontrado" % id)
            if motivo not in _REASONS_PAUSE:
                raise repo_errors.RepoViolation("pausa_motivo invalido", constraint=self._ck("pause"))
            binds = {"id": int(id), "reason": motivo, "actor": ator_limpo}
            cur = c.cursor()
            try:
                if antiga_data is not None:
                    binds["antiga_data"] = antiga_data
                    # TIPO_DATE descarta a fracao: o valor lido mais microssegundos ainda casa (README §7.5).
                    db_conn.set_input_types(cur, antiga_data=db_conn.TIPO_DATE)
                    cur.execute(self._sql["PAUSE_OPTIMISTIC"], binds)
                else:
                    cur.execute(self._sql["PAUSE"], binds)
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflict(
                        "Agendamento %s nao esta ativo ou a proxima_execucao mudou (outra operacao)" % id)
            finally:
                cur.close()
            self._auditar(c, auditoria, int(id), "SCHEDULE_PAUSE", "Agendamento pausado: reason=%s" % motivo,
                          ator_limpo)
            return self.get(id, conn=c)

    def resume(self, id, nova_data, esperado=None, auditoria=None, ator=None, conn=None):
        """Retoma: ativo = 'S', pausa_motivo nulo e proxima_execucao = nova_data, condicional a 'esperado'."""
        ator_limpo = validate_record_actor(auditoria, ator)
        with self.write_transaction(conn=conn) as c:
            atual = self._uma(c, self._sql["GET_LOCK"], {"id": int(id)})
            if atual is None:
                raise repo_errors.RepoNotFound("Agendamento ID %s nao encontrado" % id)
            self._conferir_esperado(id, atual, esperado)
            if nova_data is None:
                raise repo_errors.RepoViolation("proxima_execucao e obrigatoria")
            cur = c.cursor()
            try:
                db_conn.set_input_types(cur, nova_data=db_conn.TIPO_DATE)
                cur.execute(self._sql["RESUME"], {"id": int(id), "nova_data": nova_data, "actor": ator_limpo})
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflict("Agendamento ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, auditoria, int(id), "UPDATE",
                          "Agendamento retomado com next_run_at=%s" % nova_data, ator_limpo)
            return self.get(id, conn=c)
