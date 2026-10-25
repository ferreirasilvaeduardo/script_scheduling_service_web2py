# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio da pasta de entrada (CR-020b; README §10 tabelas 19 a 21).

- SQL estatico com binds; identificadores qualificados por sql_ident (owner e prefixo da configuracao);
- o conteudo do envio nunca entra em listagem: e gravado num bind BLOB e lido em partes de ate 1 MiB;
- o lado do agente (entregas, conteudo, marcacao e retrato) fica em repo_oracle/scheduler_input, sem gluon;
- agente vivo: status ACTIVE e heartbeat recente no SQL; o ambiente e conferido em Python na lista CSV (um
  LIKE trataria o '_' dos nomes como curinga);
- aqui os metodos do agente so delegam a ele pelo pool da web (contrato comum com o FAKE).
"""
from sss.persistence import db_conn
from sss.persistence import repo_errors
from sss.persistence.contracts import repo_inputs
from sss.persistence.contracts.repo_inputs import NoLiveAgent, RepoInputs
from sss.persistence.oracle.base import BaseRepoOracle, write_audit
from sss.persistence.oracle.scheduler_input import RepoSchedulerInput

_COLS_UPLOAD = ("id", "environment", "script_id", "relative_dir", "file_name", "size_bytes", "sha256",
                "replace_existing", "source_ip", "created_at", "created_by", "updated_at", "updated_by")
_COLS_LISTING = ("agent_id", "listing", "file_count", "truncated", "listed_at", "refresh_requested_at")


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


def _read_lob(value):
    if value is None:
        return None
    return value.read() if hasattr(value, "read") else value



class RepoInputsOracle(BaseRepoOracle, RepoInputs):
    """Envios, entregas e retratos da pasta de entrada com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, secrets=None):
        super(RepoInputsOracle, self).__init__(cfg=cfg, secrets=secrets)
        self._idents = {
            "iup": self.qualify_table("input_upload"),
            "idl": self.qualify_table("input_delivery"),
            "ils": self.qualify_table("input_listing"),
            "agt": self.qualify_table("agents"),
            "scr": self.qualify_table("scripts"),
            "seq_idl": self.qualify_sequence("input_delivery"),
            "seq_ils": self.qualify_sequence("input_listing"),
        }
        self._sql = dict((name[5:], template.format(**self._idents))
                         for name, template in globals().items() if name.startswith("_SQL_"))
        self._seq_iup = self.qualify_sequence("input_upload")
        self._agent = RepoSchedulerInput(self._owner, self._prefixo)
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
    # O daemon usa repo_oracle/scheduler_input (sem gluon) com a propria conexao; aqui os mesmos metodos ficam
    # disponiveis pelo pool da web, para o contrato comum com o FAKE (README §2.5).

    def pending_deliveries(self, agent_id, limit=10, conn=None):
        with self.read_context(conn=conn) as c:
            return self._agent.pending_deliveries(agent_id, limit, conn=c)

    def read_content(self, upload_id, offset, size, conn=None):
        with self.read_context(conn=conn) as c:
            return self._agent.read_content(upload_id, offset, size, conn=c)

    def mark_delivery(self, delivery_id, agent_id, state, reason=None, conn=None):
        with self.read_context(conn=conn) as c:
            return self._agent.mark_delivery(delivery_id, agent_id, state, reason, conn=c)

    def listings_due(self, agent_id, conn=None):
        with self.read_context(conn=conn) as c:
            return self._agent.listings_due(agent_id, conn=c)

    def save_listing(self, agent_id, environment, script_id, listing, file_count, truncated, conn=None):
        with self.read_context(conn=conn) as c:
            return self._agent.save_listing(agent_id, environment, script_id, listing, file_count, truncated, conn=c)
