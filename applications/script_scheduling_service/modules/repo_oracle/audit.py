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
        clausulas, binds, datas = [], {}, {}
        if filters.get("actor"):
            trecho = filters["actor"].lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clausulas.append("LOWER(actor) LIKE :actor_f ESCAPE '\\'")
            binds["actor_f"] = "%" + trecho + "%"
        if filters.get("action"):
            clausulas.append("action = :action_f")
            binds["action_f"] = filters["action"]
        if filters.get("entity"):
            clausulas.append("entity = :entity_f")
            binds["entity_f"] = filters["entity"]
        if filters.get("entity_id") is not None:
            clausulas.append("entity_id = :entity_id_f")
            binds["entity_id_f"] = int(filters["entity_id"])
        if filters.get("source_ip"):
            trecho = filters["source_ip"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clausulas.append("source_ip LIKE :ip_f ESCAPE '\\'")
            binds["ip_f"] = "%" + trecho + "%"
        # Periodo sempre por intervalo, sem TRUNC na coluna indexada (AGENTS §4.12).
        if filters.get("start_date"):
            clausulas.append("created_at >= :start_date")
            binds["start_date"] = filters["start_date"]
            datas["start_date"] = db_conn.TIPO_DATE
        if filters.get("end_date"):
            clausulas.append("created_at <= :end_date")
            binds["end_date"] = filters["end_date"]
            datas["end_date"] = db_conn.TIPO_DATE
        if filters.get("id_max") is not None:
            clausulas.append("id <= :id_max")
            binds["id_max"] = int(filters["id_max"])
        return clausulas, binds, datas

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
        clausulas, binds, datas = self._filtros(filters)
        p = 1 if page is None else int(page)
        t = 20 if size is None else int(size)
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
            "WHERE ROWNUM <= :end_ts) WHERE rn > :start_ts"
        )
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                if datas:
                    db_conn.set_input_types(cur, **datas)
                cur.execute(sql_conta, binds)
                bruto = cur.fetchone()[0]
            finally:
                cur.close()
            binds_pag = dict(binds)
            binds_pag["start_ts"] = inicio
            binds_pag["end_ts"] = inicio + t
            cur = c.cursor()
            try:
                if datas:
                    db_conn.set_input_types(cur, **datas)
                cur.execute(sql_pag, binds_pag)
                itens = [self.tuple_to_dict(_COLS, r[:len(_COLS)]) for r in cur.fetchall()]
            finally:
                cur.close()
        return {
            "itens": itens,
            "total": min(bruto, _LIMIT_TOTAL),
            "pagina": p,
            "tamanho": t,
            "total_limitado": bruto >= _LIMIT_TOTAL,
        }

    def iterate(self, filters=None, limit=50000):
        """Iterador de ate `limite` registros na ordem de listar, por cursor (arraysize), sem offset."""
        clausulas, binds, datas = self._filtros(filters)
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        sql = _SQL_ITERATE.format(items=_SQL_LIST.format(where=where, **self._idents))
        binds["cutoff"] = max(0, int(limit))
        return self._iterar(sql, binds, datas)

    def _iterar(self, sql, binds, dates):
        with self.read_context() as c:
            cur = c.cursor()
            try:
                cur.arraysize = _ARRAYSIZE
                if dates:
                    db_conn.set_input_types(cur, **dates)
                cur.execute(sql, binds)
                while True:
                    linhas = cur.fetchmany(_ARRAYSIZE)
                    if not linhas:
                        break
                    for r in linhas:
                        yield self.tuple_to_dict(_COLS, r)
            finally:
                cur.close()

