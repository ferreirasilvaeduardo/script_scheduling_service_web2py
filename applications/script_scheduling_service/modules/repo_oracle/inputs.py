# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio da pasta de entrada (CR-020b; README §10 tabelas 19 a 21).

- SQL estatico com binds; identificadores qualificados por sql_ident (owner e prefixo da configuracao);
- o conteudo do envio nunca entra em listagem: e gravado num bind BLOB e lido em partes de ate 1 MiB;
- as entregas pendentes do agente sao lidas pela expressao textualmente identica a de ix_tbsss_idl_pend;
- agente vivo: status ACTIVE e heartbeat recente no SQL; o ambiente e conferido em Python na lista CSV (um
  LIKE trataria o '_' dos nomes como curinga);
- os metodos do agente aceitam a conexao do daemon (conn=); cada gravacao e uma transacao com COMMIT.
"""
import db_conn
import repo_errors
import repo_inputs
import sql_ident
from repo_inputs import NoLiveAgent, RepoInputs
from repo_oracle.base import BaseRepoOracle, write_audit

_COLS_UPLOAD = ("id", "environment", "script_id", "relative_dir", "file_name", "size_bytes", "sha256",
                "replace_existing", "source_ip", "created_at", "created_by", "updated_at", "updated_by")
_COLS_LISTING = ("agent_id", "listing", "file_count", "truncated", "listed_at", "refresh_requested_at")
_COLS_PENDING = ("id", "upload_id", "environment", "script_id", "relative_dir", "file_name", "size_bytes",
                 "sha256", "replace_existing")


def _cols(cols, alias=""):
    return ", ".join(alias + c for c in cols)


_SQL_LIVE_AGENTS = (
    "SELECT code, environments FROM {agt} WHERE status = 'ACTIVE' AND heartbeat_at >= SYSDATE - :live_s / 86400 "
    "ORDER BY code"
)
_SQL_INSERT_UPLOAD = (
    "INSERT INTO {iup} (id, environment, script_id, relative_dir, file_name, size_bytes, sha256, replace_existing, "
    "source_ip, content, created_at, created_by) VALUES (:id, :environment, :script_id, :relative_dir, :file_name, "
    ":size_bytes, :sha256, :replace_existing, :source_ip, :content, SYSDATE, :actor)"
)
_SQL_INSERT_DELIVERY = (
    "INSERT INTO {idl} (id, upload_id, agent_id, state, created_at, created_by) "
    "VALUES ({seq_idl}.NEXTVAL, :upload_id, :agent_id, 'PENDING', SYSDATE, :actor)"
)
_SQL_UPLOADS_COUNT = "SELECT COUNT(*) FROM {iup} WHERE environment = :environment AND script_id = :script_id"
_SQL_UPLOADS = (
    "SELECT " + _cols(_COLS_UPLOAD) + " FROM {iup} WHERE environment = :environment AND script_id = :script_id "
    "ORDER BY created_at DESC, id DESC"
)
_SQL_LISTINGS = (
    "SELECT " + _cols(_COLS_LISTING) + " FROM {ils} WHERE environment = :environment AND script_id = :script_id "
    "ORDER BY agent_id"
)
_SQL_REQUEST_LISTING = (
    "MERGE INTO {ils} dst USING (SELECT :agent_id AS agent_id, :environment AS environment, "
    ":script_id AS script_id FROM DUAL) src "
    "ON (dst.agent_id = src.agent_id AND dst.environment = src.environment AND dst.script_id = src.script_id) "
    "WHEN MATCHED THEN UPDATE SET dst.refresh_requested_at = SYSDATE "
    "WHEN NOT MATCHED THEN INSERT (id, agent_id, environment, script_id, truncated, refresh_requested_at, "
    "created_at, created_by) VALUES ({seq_ils}.NEXTVAL, src.agent_id, src.environment, src.script_id, 'N', SYSDATE, "
    "SYSDATE, :actor)"
)
_SQL_PENDING = (
    "SELECT " + _cols(_COLS_PENDING) + " FROM (SELECT d.id, u.id AS upload_id, u.environment, u.script_id, "
    "u.relative_dir, u.file_name, u.size_bytes, u.sha256, u.replace_existing "
    "FROM (SELECT id, upload_id FROM {idl} WHERE (" + sql_ident.FBI_IDL_PEND_CASE + ") = :agent_id) d "
    "JOIN {iup} u ON u.id = d.upload_id ORDER BY d.id) WHERE ROWNUM <= :limit_n"
)
_SQL_CONTENT = "SELECT content FROM {iup} WHERE id = :id"
_SQL_MARK = (
    "UPDATE {idl} SET state = :state, reason = :reason, delivered_at = SYSDATE, updated_at = SYSDATE, "
    "updated_by = :actor WHERE id = :id AND agent_id = :agent_id AND state = 'PENDING'"
)
_SQL_DELIVERY_UPLOAD = (
    "SELECT u.id, u.file_name FROM {idl} d JOIN {iup} u ON u.id = d.upload_id WHERE d.id = :id"
)
_SQL_LISTINGS_DUE = (
    "SELECT environment, script_id FROM {ils} WHERE agent_id = :agent_id AND refresh_requested_at IS NOT NULL "
    "AND (listed_at IS NULL OR refresh_requested_at >= listed_at) ORDER BY id"
)
_SQL_SAVE_LISTING = (
    "MERGE INTO {ils} dst USING (SELECT :agent_id AS agent_id, :environment AS environment, "
    ":script_id AS script_id FROM DUAL) src "
    "ON (dst.agent_id = src.agent_id AND dst.environment = src.environment AND dst.script_id = src.script_id) "
    "WHEN MATCHED THEN UPDATE SET dst.listing = :listing, dst.file_count = :file_count, "
    "dst.truncated = :truncated, dst.listed_at = SYSDATE "
    "WHEN NOT MATCHED THEN INSERT (id, agent_id, environment, script_id, listing, file_count, truncated, listed_at, "
    "created_at, created_by) VALUES ({seq_ils}.NEXTVAL, src.agent_id, src.environment, src.script_id, :listing, "
    ":file_count, :truncated, SYSDATE, SYSDATE, :actor)"
)


def _read_lob(value):
    if value is None:
        return None
    return value.read() if hasattr(value, "read") else value


def _actor_agent(agent_id):
    return "SYSTEM:%s" % agent_id


class RepoInputsOracle(BaseRepoOracle, RepoInputs):
    """Envios, entregas e retratos da pasta de entrada com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, secrets=None):
        super(RepoInputsOracle, self).__init__(cfg=cfg, secrets=secrets)
        self._idents = {
            "iup": self.qualify_table("input_upload"),
            "idl": self.qualify_table("input_delivery"),
            "ils": self.qualify_table("input_listing"),
            "agt": self.qualify_table("agents"),
            "seq_idl": self.qualify_sequence("input_delivery"),
            "seq_ils": self.qualify_sequence("input_listing"),
        }
        self._sql = dict((name[5:], template.format(**self._idents))
                         for name, template in globals().items() if name.startswith("_SQL_"))
        self._seq_iup = self.qualify_sequence("input_upload")
        self._tbl_aud = self.qualify_table("audit")
        self._seq_aud = self.qualify_sequence("audit")

    # ------------------------------------------------------------------ apoio

    def _live_agents(self, conn, environment, live_seconds):
        cur = conn.cursor()
        try:
            cur.execute(self._sql["LIVE_AGENTS"], {"live_s": int(live_seconds)})
            rows = cur.fetchall()
        finally:
            cur.close()
        return [code for code, envs in rows if environment in [e.strip() for e in (envs or "").split(",")]]

    # ------------------------------------------------------------------ web

    def create_upload(self, data, content, actor, ip, live_seconds, conn=None):
        if not actor:
            raise repo_errors.RepoViolation("ator das colunas de registro e obrigatorio")
        content = bytes(content or b"")
        # Recusa de negocio fora da transacao (sem log de erro de transacao); dentro, a conferencia se repete.
        with self.read_context(conn=conn) as c:
            if not self._live_agents(c, data["environment"], live_seconds):
                raise NoLiveAgent("nenhum agente vivo atende o ambiente %s" % data["environment"])
        with self.write_transaction(conn=conn) as c:
            agents = self._live_agents(c, data["environment"], live_seconds)
            if not agents:
                raise NoLiveAgent("nenhum agente vivo atende o ambiente %s" % data["environment"])
            uid = db_conn.next_id(c, self._seq_iup)
            cur = c.cursor()
            try:
                db_conn.set_input_types(cur, content=db_conn.TIPO_BLOB)
                cur.execute(self._sql["INSERT_UPLOAD"], {
                    "id": uid, "environment": data["environment"], "script_id": int(data["script_id"]),
                    "relative_dir": data.get("relative_dir") or None, "file_name": data["file_name"],
                    "size_bytes": len(content), "sha256": data["sha256"],
                    "replace_existing": data["replace_existing"], "source_ip": ip, "content": content,
                    "actor": actor})
            finally:
                cur.close()
            cur = c.cursor()
            try:
                for code in agents:
                    cur.execute(self._sql["INSERT_DELIVERY"], {"upload_id": uid, "agent_id": code, "actor": actor})
            finally:
                cur.close()
            detail = u"envio de %s (%d bytes) para %s/script %s; agentes: %s" % (
                data["file_name"], len(content), data["environment"], data["script_id"], ", ".join(agents))
            write_audit(c, self._tbl_aud, self._seq_aud,
                        {"actor": actor, "ip": ip, "action": repo_inputs.ACTION_UPLOAD, "detail": detail[:1000]},
                        repo_inputs.AUDIT_ENTITY, uid)
        return {"id": uid, "agents": agents}

    def uploads(self, environment, script_id, page=1, size=20, conn=None):
        p = max(1, int(page or 1))
        t = int(size or 20)
        t = 20 if t < 1 else t
        binds = {"environment": environment, "script_id": int(script_id)}
        sql_page = ("SELECT * FROM (SELECT a.*, ROWNUM rn FROM (" + self._sql["UPLOADS"] + ") a "
                    "WHERE ROWNUM <= :end_ts) WHERE rn > :start_ts")
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["UPLOADS_COUNT"], binds)
                total = cur.fetchone()[0]
                cur.execute(sql_page, dict(binds, start_ts=(p - 1) * t, end_ts=p * t))
                items = [self.tuple_to_dict(_COLS_UPLOAD, r[:len(_COLS_UPLOAD)]) for r in cur.fetchall()]
            finally:
                cur.close()
            deliveries = {}
            if items:
                marks, dbinds = [], {}
                for n, item in enumerate(items):
                    dbinds["u%d" % n] = item["id"]
                    marks.append(":u%d" % n)
                cur = c.cursor()
                try:
                    cur.execute("SELECT upload_id, agent_id, state, reason, delivered_at FROM " + self._idents["idl"]
                                + " WHERE upload_id IN (" + ", ".join(marks) + ") ORDER BY upload_id, agent_id",
                                dbinds)
                    for row in cur.fetchall():
                        d = self.tuple_to_dict(("upload_id", "agent_id", "state", "reason", "delivered_at"), row)
                        deliveries.setdefault(d.pop("upload_id"), []).append(d)
                finally:
                    cur.close()
        for item in items:
            item["deliveries"] = deliveries.get(item["id"], [])
        return {"items": items, "total": total, "page": p, "size": t}

    def listings(self, environment, script_id, conn=None):
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["LISTINGS"], {"environment": environment, "script_id": int(script_id)})
                rows = cur.fetchall()
                result = []
                for r in rows:
                    item = self.tuple_to_dict(_COLS_LISTING, r)
                    item["listing"] = _read_lob(item["listing"])
                    result.append(item)
            finally:
                cur.close()
        return result

    def request_listing(self, environment, script_id, actor, live_seconds, conn=None):
        if not actor:
            raise repo_errors.RepoViolation("ator das colunas de registro e obrigatorio")
        with self.write_transaction(conn=conn) as c:
            agents = self._live_agents(c, environment, live_seconds)
            cur = c.cursor()
            try:
                for code in agents:
                    cur.execute(self._sql["REQUEST_LISTING"], {"agent_id": code, "environment": environment,
                                                               "script_id": int(script_id), "actor": actor})
            finally:
                cur.close()
        return len(agents)

    # ------------------------------------------------------------------ agente

    def pending_deliveries(self, agent_id, limit=10, conn=None):
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["PENDING"], {"agent_id": agent_id, "limit_n": int(limit)})
                return [self.tuple_to_dict(_COLS_PENDING, r) for r in cur.fetchall()]
            finally:
                cur.close()

    def read_content(self, upload_id, offset, size, conn=None):
        off, size_n = int(offset), int(size)
        if off < 0 or size_n < 1 or size_n > repo_inputs.PART_MAX:
            raise repo_errors.RepoViolation("Parte do envio invalida")
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["CONTENT"], {"id": int(upload_id)})
                row = cur.fetchone()
                if not row or row[0] is None:
                    raise repo_errors.RepoNotFound("Conteudo do envio %s indisponivel" % upload_id)
                lob = row[0]
                if hasattr(lob, "read"):
                    return (lob.read(off + 1, size_n) or b"") if off < lob.size() else b""
                return bytes(lob[off:off + size_n])
            finally:
                cur.close()

    def mark_delivery(self, delivery_id, agent_id, state, reason=None, conn=None):
        if state not in ("DELIVERED", "FAILED") or (state == "FAILED") != (reason is not None) \
                or (reason is not None and reason not in repo_inputs.FAILURE_REASONS):
            raise repo_errors.RepoViolation("Situacao ou motivo da entrega invalido",
                                            constraint=self.constraint_name("ck", "input_delivery", "rsn"))
        actor = _actor_agent(agent_id)
        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["MARK"], {"state": state, "reason": reason, "actor": actor,
                                                "id": int(delivery_id), "agent_id": agent_id})
                if cur.rowcount != 1:
                    return False
                cur.execute(self._sql["DELIVERY_UPLOAD"], {"id": int(delivery_id)})
                upload_id, file_name = cur.fetchone()
            finally:
                cur.close()
            detail = u"entrega de %s em %s: %s%s" % (file_name, agent_id, state, " (%s)" % reason if reason else "")
            write_audit(c, self._tbl_aud, self._seq_aud,
                        {"actor": actor, "ip": None, "action": repo_inputs.ACTION_DELIVERY, "detail": detail[:1000]},
                        repo_inputs.AUDIT_ENTITY, upload_id)
        return True

    def listings_due(self, agent_id, conn=None):
        with self.read_context(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["LISTINGS_DUE"], {"agent_id": agent_id})
                return [{"environment": e, "script_id": s} for e, s in cur.fetchall()]
            finally:
                cur.close()

    def save_listing(self, agent_id, environment, script_id, listing, file_count, truncated, conn=None):
        if truncated not in ("Y", "N"):
            raise repo_errors.RepoViolation("truncated invalido",
                                            constraint=self.constraint_name("ck", "input_listing", "trunc"))
        with self.write_transaction(conn=conn) as c:
            cur = c.cursor()
            try:
                db_conn.set_input_types(cur, listing=db_conn.TIPO_CLOB)
                cur.execute(self._sql["SAVE_LISTING"], {
                    "agent_id": agent_id, "environment": environment, "script_id": int(script_id),
                    "listing": listing, "file_count": int(file_count), "truncated": truncated,
                    "actor": _actor_agent(agent_id)})
            finally:
                cur.close()
