# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de auditoria (F7.3, agregado AUDITORIA_AGENTES; AGENTS §4).

tbsss_audit com a mesma semantica do repo_fake/audit.py (README §2.5, §4.4):
- reservar_id: NEXTVAL da sequence (README §2.7); registrar usa o id recebido ou um proprio;
- ator obrigatorio ate 40 e detalhe ate 1.000, sem corte nem valor padrao (test_06b);
- sem colunas de registro (CR-006, D1): so ator e created_at;
- listar paginado por created_at DESC, id DESC com periodo por intervalo (sem TRUNC, AGENTS §4.12) e
  id_max inclusivo; iterar por cursor com arraysize, sem paginacao por offset (exportacao).
"""
import db_conn
from repo_audit import RepoAudit
from repo_oracle.base import BaseRepoOracle, validate_audit_fields

_LIMIT_TOTAL = 10001
_ARRAYSIZE = 1000
_COLS = ("id", "actor", "source_ip", "action", "entity", "entity_id", "detail", "created_at")


def _column_list(cols):
    return ", ".join(cols)


# {aud} recebe apenas o nome qualificado por sql_ident (validado); todo valor entra por bind.
_SQL_INSERT = (
    "INSERT INTO {aud} (id, actor, source_ip, action, entity, entity_id, detail, created_at) "
    "VALUES (:id, :actor, :source_ip, :action, :entity, :entity_id, :detail, SYSDATE)"
)
_SQL_GET = "SELECT " + _column_list(_COLS) + " FROM {aud} WHERE id = :id"
_SQL_LIST = "SELECT " + _column_list(_COLS) + " FROM {aud}{where} ORDER BY created_at DESC, id DESC"
_SQL_COUNT = "SELECT COUNT(*) FROM (SELECT id FROM {aud} WHERE {where_count})"
_SQL_ITERATE = "SELECT " + _column_list(_COLS) + " FROM ({items}) WHERE ROWNUM <= :cutoff"


class RepoAuditOracle(BaseRepoOracle, RepoAudit):
    """Repositorio da trilha de auditoria com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, secrets=None):
        super(RepoAuditOracle, self).__init__(cfg=cfg, secrets=secrets)
        self._idents = {"aud": self.qualify_table("audit")}
        self._sql = {
            "INSERT": _SQL_INSERT.format(**self._idents),
            "GET": _SQL_GET.format(**self._idents),
        }
        self._seq_aud = self.qualify_sequence("audit")

    def _filtros(self, filters):
        """Clausulas fixas (allowlist) e binds; datas declaradas como TIPO_DATE (README §7.5)."""
        filters = filters or {}
        clauses, binds, dates = [], {}, {}
        if filters.get("actor"):
            snippet = filters["actor"].lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("LOWER(actor) LIKE :actor_f ESCAPE '\\'")
            binds["actor_f"] = "%" + snippet + "%"
        if filters.get("action"):
            clauses.append("action = :action_f")
            binds["action_f"] = filters["action"]
        if filters.get("entity"):
            clauses.append("entity = :entity_f")
            binds["entity_f"] = filters["entity"]
        if filters.get("entity_id") is not None:
            clauses.append("entity_id = :entity_id_f")
            binds["entity_id_f"] = int(filters["entity_id"])
        if filters.get("source_ip"):
            snippet = filters["source_ip"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("source_ip LIKE :ip_f ESCAPE '\\'")
            binds["ip_f"] = "%" + snippet + "%"
        # Periodo sempre por intervalo, sem TRUNC na coluna indexada (AGENTS §4.12).
        if filters.get("start_date"):
            clauses.append("created_at >= :start_date")
            binds["start_date"] = filters["start_date"]
            dates["start_date"] = db_conn.TIPO_DATE
        if filters.get("end_date"):
            clauses.append("created_at <= :end_date")
            binds["end_date"] = filters["end_date"]
            dates["end_date"] = db_conn.TIPO_DATE
        if filters.get("id_max") is not None:
            clauses.append("id <= :id_max")
            binds["id_max"] = int(filters["id_max"])
        return clauses, binds, dates

    def reserve_id(self, conn=None):
        """Proximo id da trilha (seq.NEXTVAL), usado antes de gravar a linha (README §4.4)."""
        with self.read_context(conn=conn) as c:
            return db_conn.next_id(c, self._seq_aud)

    def register(self, actor, ip, action, entity, entity_id=None, detail=None, id=None, conn=None):
        """Grava a linha (com o id reservado, se informado) e devolve o registro criado."""
        validate_audit_fields(actor, detail)
        with self.write_transaction(conn=conn) as c:
            aid = int(id) if id is not None else db_conn.next_id(c, self._seq_aud)
            cur = c.cursor()
            try:
                # id repetido: ORA-00001 em pk_<prefixo>auditoria (RepoViolation com o nome da PK).
                cur.execute(self._sql["INSERT"], {
                    "id": aid, "actor": actor, "source_ip": ip, "action": action, "entity": entity,
                    "entity_id": entity_id, "detail": detail,
                })
                cur.execute(self._sql["GET"], {"id": aid})
                return self.tuple_to_dict(_COLS, cur.fetchone())
            finally:
                cur.close()

    def list(self, filters=None, page=1, size=20, conn=None):
        """Lista por created_at DESC, id DESC, com total limitado a 10.001."""
        clauses, binds, dates = self._filtros(filters)
        p = 1 if page is None else int(page)
        t = 20 if size is None else int(size)
        if p < 1:
            p = 1
        if t < 1:
            t = 20
        start = (p - 1) * t
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        where_count = " AND ".join(clauses + ["ROWNUM <= " + str(_LIMIT_TOTAL)])
        sql_count_tpl = _SQL_COUNT.format(where_count=where_count, **self._idents)
        sql_page = (
            "SELECT * FROM (SELECT a.*, ROWNUM rn FROM (" + _SQL_LIST.format(where=where, **self._idents) + ") a "
            "WHERE ROWNUM <= :end_ts) WHERE rn > :start_ts"
        )
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                if dates:
                    db_conn.set_input_types(cur, **dates)
                cur.execute(sql_count_tpl, binds)
                raw = cur.fetchone()[0]
            finally:
                cur.close()
            binds_page = dict(binds)
            binds_page["start_ts"] = start
            binds_page["end_ts"] = start + t
            cur = c.cursor()
            try:
                if dates:
                    db_conn.set_input_types(cur, **dates)
                cur.execute(sql_page, binds_page)
                items = [self.tuple_to_dict(_COLS, r[:len(_COLS)]) for r in cur.fetchall()]
            finally:
                cur.close()
        return {
            "items": items,
            "total": min(raw, _LIMIT_TOTAL),
            "page": p,
            "size": t,
            "total_capped": raw >= _LIMIT_TOTAL,
        }

    def iterate(self, filters=None, limit=50000):
        """Iterador de ate `limite` registros na ordem de listar, por cursor (arraysize), sem offset."""
        clauses, binds, dates = self._filtros(filters)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = _SQL_ITERATE.format(items=_SQL_LIST.format(where=where, **self._idents))
        binds["cutoff"] = max(0, int(limit))
        return self._iterar(sql, binds, dates)

    def _iterar(self, sql, binds, dates):
        with self.read_context() as c:
            cur = c.cursor()
            try:
                cur.arraysize = _ARRAYSIZE
                if dates:
                    db_conn.set_input_types(cur, **dates)
                cur.execute(sql, binds)
                while True:
                    rows = cur.fetchmany(_ARRAYSIZE)
                    if not rows:
                        break
                    for r in rows:
                        yield self.tuple_to_dict(_COLS, r)
            finally:
                cur.close()

