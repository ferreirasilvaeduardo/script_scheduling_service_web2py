# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de agendamentos (README §2.5, §7, §10)."""
import copy
import re

from repo_schedules import RepoSchedules
from repo_errors import RepoConflict, RepoNotFound, RepoViolation
from repo_fake.store import paginate

_TYPES = ("ONCE", "DAILY", "WEEKLY", "MONTHLY", "CRON")
_REASONS_PAUSE = ("USER_INACTIVE", "NO_PERMISSION", "SCRIPT_INACTIVE", "ENVIRONMENT_INACTIVE",
                  "INVALID_PARAM", "INVALID_CRON", "COMPLETED", "MANUAL", "INTERNAL_ERROR")
_RE_TIME = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
_RE_WDAY = re.compile(r"^[1-7](,[1-7]){0,6}$")
_SIZE_NAME = 60
_COLUMNS_UPDATABLE = ("name", "script_id", "environment", "user_id", "priority",
                       "recurrence_type", "cron_expression", "run_time", "week_days",
                       "month_day", "params_json", "start_date", "end_date",
                       "next_run_at", "last_run_at", "last_ticket_id",
                       "pause_reason", "active")


def _null(value):
    # O Oracle grava '' como NULL.
    return value is None or value == ""


def _check_cks(r):
    """Espelha NOT NULL e as CKs de tbsss_schedules (README §10, tabela 12)."""
    nome = r.get("name")
    if _null(nome) or len(nome) > _SIZE_NAME:
        # NOT NULL e tamanho da coluna nao sao constraints nomeadas (ORA-01400 / ORA-12899).
        raise RepoViolation("nome obrigatorio com ate %d caracteres" % _SIZE_NAME)
    trec = r.get("recurrence_type")
    if trec not in _TYPES:
        raise RepoViolation("tipo_recorrencia invalido", constraint="ck_tbsss_sch_rtype")
    prio = r.get("priority")
    if isinstance(prio, bool) or not isinstance(prio, int) or not (1 <= prio <= 4):
        raise RepoViolation("prioridade deve estar entre 1 e 4", constraint="ck_tbsss_sch_prio")
    if r.get("active") not in ("Y", "N"):
        raise RepoViolation("ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_sch_active")
    dia = r.get("month_day")
    if not _null(dia) and (isinstance(dia, bool) or not isinstance(dia, int) or not (1 <= dia <= 31)):
        raise RepoViolation("dia_mes deve estar entre 1 e 31", constraint="ck_tbsss_sch_day")
    hora = r.get("run_time")
    if not _null(hora) and not _RE_TIME.match(hora):
        raise RepoViolation("hora_execucao fora do formato HH:MM", constraint="ck_tbsss_sch_time")
    dsem = r.get("week_days")
    if not _null(dsem) and not _RE_WDAY.match(dsem):
        raise RepoViolation("dias_semana fora do formato ISO 1-7", constraint="ck_tbsss_sch_wday")
    if r.get("start_date") is None or r.get("next_run_at") is None:
        raise RepoViolation("data_inicio e proxima_execucao sao obrigatorias")
    if r.get("end_date") is not None and r["end_date"] < r["start_date"]:
        raise RepoViolation("data_fim anterior a data_inicio", constraint="ck_tbsss_sch_end")
    if not _null(r.get("pause_reason")) and r["pause_reason"] not in _REASONS_PAUSE:
        raise RepoViolation("pausa_motivo invalido", constraint="ck_tbsss_sch_pause")
    exigidos = {"DAILY": ("run_time",), "WEEKLY": ("run_time", "week_days"),
                "MONTHLY": ("run_time", "month_day"), "CRON": ("cron_expression",)}
    for coluna in exigidos.get(trec, ()):
        if _null(r.get(coluna)):
            raise RepoViolation("%s obrigatorio para %s" % (coluna, trec), constraint="ck_tbsss_sch_fields")


class RepoSchedulesFake(RepoSchedules):
    """Implementacao em memoria com semantica Oracle para agendamentos."""

    def __init__(self, store):
        self._store = store

    def list(self, filters=None, page=1, size=20, environment_scope=None):
        """Lista agendamentos paginados com desempate por id."""
        filters = filters or {}
        with self._store.lock_schedules:
            lista = list(self._store.schedules.values())

            if environment_scope is not None:
                ambs_permitidos = set(environment_scope)
                lista = [a for a in lista if a.get("environment") in ambs_permitidos]

            ativo_f = filters.get("active")
            if ativo_f:
                lista = [a for a in lista if a.get("active") == ativo_f]

            sid_f = filters.get("script_id")
            if sid_f is not None:
                lista = [a for a in lista if a.get("script_id") == int(sid_f)]

            amb_f = filters.get("environment")
            if amb_f:
                lista = [a for a in lista if a.get("environment") == amb_f]

            usr_f = filters.get("user_id")
            if usr_f is not None:
                lista = [a for a in lista if a.get("user_id") == int(usr_f)]

            nome_f = filters.get("name")
            if nome_f:
                lista = [a for a in lista if nome_f.lower() in a.get("name", "").lower()]

            lista.sort(key=lambda x: (x.get("next_run_at") or self._store.now(), x["id"]))
            return paginate(lista, page=page, size=size)

    def get(self, id):
        """Retorna dict com dados do agendamento pelo ID ou lanca RepoNotFound."""
        with self._store.lock_schedules:
            if id not in self._store.schedules:
                raise RepoNotFound("Agendamento ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.schedules[id])

    def _auditar(self, audit, id, default_action=None, default_detail=None, actor=None):
        if audit:
            self._store.register_internal_audit(
                actor=audit.get("actor"),
                ip=audit.get("ip"),
                action=audit["action"],
                entity="tbsss_schedules",
                entity_id=id,
                detail=audit.get("detail"),
            )
        elif default_action:
            self._store.register_internal_audit(
                actor=actor, ip=None, action=default_action, entity="tbsss_schedules",
                entity_id=id, detail=default_detail,
            )

    def _checar_fks(self, reg):
        self._store.check_fk(reg["script_id"] in self._store.scripts, "fk_tbsss_sch_scr")
        self._store.check_fk(reg["user_id"] in self._store.users, "fk_tbsss_sch_usr")
        self._store.check_fk(self._store.environment_exists(reg["environment"]), "fk_tbsss_sch_env")

    def _conferir_esperado(self, id, current_value, expected):
        for campo, valor in (expected or {}).items():
            if current_value.get(campo) != valor:
                raise RepoConflict("Agendamento ID %s alterado por outra operacao (%s)" % (id, campo))

    def insert(self, date, audit=None, actor=None):
        """Insere novo agendamento com as CKs da tabela e auditoria na mesma operacao."""
        with self._store.lock_schedules:
            actor = self._store.record_actor(audit, actor)
            agora = self._store.now()
            novo = {
                "name": date.get("name"),
                "script_id": int(date["script_id"]),
                "environment": date["environment"],
                "user_id": int(date["user_id"]),
                "priority": date.get("priority", 2),
                "recurrence_type": date.get("recurrence_type"),
                "cron_expression": date.get("cron_expression"),
                "run_time": date.get("run_time"),
                "week_days": date.get("week_days"),
                "month_day": date.get("month_day"),
                "params_json": date.get("params_json", "{}"),
                "start_date": date.get("start_date") or agora,
                "end_date": date.get("end_date"),
                "next_run_at": date.get("next_run_at") or agora,
                "last_run_at": date.get("last_run_at"),
                "last_ticket_id": date.get("last_ticket_id"),
                "pause_reason": date.get("pause_reason"),
                "active": date.get("active", "Y"),
                "created_at": date.get("created_at") or agora,
            }
            self._store.stamp_insert(novo, actor)
            _check_cks(novo)
            self._checar_fks(novo)
            aid = self._store.next_id("tbsss_schedules")
            novo["id"] = aid
            self._store.schedules[aid] = copy.deepcopy(novo)
            self._auditar(audit, aid)
            return copy.deepcopy(novo)

    def update(self, id, date, expected=None, audit=None, actor=None):
        """Altera agendamento (usuario_id do editor, README §10), condicional a 'esperado'.

        created_by guarda o criador original e nunca muda; updated_* recebe o editor (CR-006).
        """
        with self._store.lock_schedules:
            actor = self._store.record_actor(audit, actor)
            if id not in self._store.schedules:
                raise RepoNotFound("Agendamento ID %s nao encontrado" % id)

            atual = self._store.schedules[id]
            self._conferir_esperado(id, atual, expected)
            resultado = dict(atual)
            for k in _COLUMNS_UPDATABLE:
                if k in date:
                    resultado[k] = date[k]
            # Validacao completa antes de aplicar: um UPDATE rejeitado nao altera nenhuma coluna.
            _check_cks(resultado)
            self._checar_fks(resultado)
            atual.update(resultado)
            self._store.stamp_update(atual, actor)
            self._auditar(audit, id)
            return copy.deepcopy(atual)

    def pause(self, id, reason, old_date=None, audit=None, actor=None):
        """Pausa agendamento de forma otimista, validando antiga_data se informada."""
        with self._store.lock_schedules:
            actor = self._store.record_actor(audit, actor)
            if id not in self._store.schedules:
                raise RepoNotFound("Agendamento ID %s nao encontrado" % id)
            if reason not in _REASONS_PAUSE:
                raise RepoViolation("pausa_motivo invalido", constraint="ck_tbsss_sch_pause")

            a = self._store.schedules[id]
            if a.get("active") != "Y":
                raise RepoConflict("Agendamento %s nao esta ativo (ja pausado ou concluido)" % id)
            if old_date is not None:
                prox = a.get("next_run_at")
                if prox != old_date:
                    raise RepoConflict(
                        "Conflito otimista no agendamento %s: proxima_execucao divergiu (%s != %s)"
                        % (id, prox, old_date)
                    )

            a["active"] = "N"
            a["pause_reason"] = reason
            self._store.stamp_update(a, actor)
            self._auditar(audit, id, "SCHEDULE_PAUSE", "Agendamento pausado: reason=%s" % reason, actor)
            return copy.deepcopy(a)

    def resume(self, id, new_date, expected=None, audit=None, actor=None):
        """Retoma agendamento pausado, limpando pausa_motivo e definindo next_run."""
        with self._store.lock_schedules:
            actor = self._store.record_actor(audit, actor)
            if id not in self._store.schedules:
                raise RepoNotFound("Agendamento ID %s nao encontrado" % id)

            a = self._store.schedules[id]
            self._conferir_esperado(id, a, expected)
            if new_date is None:
                raise RepoViolation("proxima_execucao e obrigatoria")
            a["active"] = "Y"
            a["pause_reason"] = None
            a["next_run_at"] = new_date
            self._store.stamp_update(a, actor)
            self._auditar(audit, id, "UPDATE",
                          "Agendamento retomado com next_run_at=%s" % new_date, actor)
            return copy.deepcopy(a)

    def ticket_status(self, ticket_id):
        """Retorna o status atual do ticket pelo ID ou None se inexistente."""
        if ticket_id is None:
            return None
        with self._store.lock_tickets:
            t = self._store.tickets.get(ticket_id)
            if t:
                return t.get("status")
            return None
