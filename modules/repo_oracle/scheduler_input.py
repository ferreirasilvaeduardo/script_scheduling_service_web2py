# -*- coding: utf-8 -*-
"""Repositorio interno do daemon para a entrada pela tela (CR-020c; README §8.14 e §10, tabelas 19 a 21).

Fora do contrato da UI e sem gluon (o daemon nao carrega o web2py). Owner e prefixo vem da configuracao e todo
identificador passa por sql_ident. A conexao e sempre a do agente (conn=, obrigatoria). Marcar a entrega e
gravar o retrato fazem COMMIT (uma transacao por passo, como a fase de saida); as leituras nao gravam nada.
A entrega so e marcada pelo proprio agente (agent_id = :agent_id), com INPUT_DELIVERY na mesma transacao.
"""
import db_conn
import repo_errors
import repo_inputs
import sql_ident

ACTOR_MAX = sql_ident.ACTOR_MAX
DETAIL_MAX = 1000

COLS_PENDING = ("id", "upload_id", "environment", "script_id", "script_name", "relative_dir", "file_name",
                "size_bytes", "sha256", "replace_existing")

_SQL_PENDING = (
    "SELECT d.id, u.id AS upload_id, u.environment, u.script_id, s.name AS script_name, u.relative_dir, "
    "u.file_name, u.size_bytes, u.sha256, u.replace_existing "
    "FROM (SELECT id, upload_id FROM {idl} WHERE (" + sql_ident.FBI_IDL_PEND_CASE + ") = :agent_id) d "
    "JOIN {iup} u ON u.id = d.upload_id JOIN {scr} s ON s.id = u.script_id ORDER BY d.id"
)
_SQL_CONTENT = "SELECT content FROM {iup} WHERE id = :id"
_SQL_MARK = (
    "UPDATE {idl} SET state = :state, reason = :reason, delivered_at = SYSDATE, updated_at = SYSDATE, "
    "updated_by = :actor WHERE id = :id AND agent_id = :agent_id AND state = 'PENDING'"
)
_SQL_DELIVERY_UPLOAD = "SELECT u.id, u.file_name FROM {idl} d JOIN {iup} u ON u.id = d.upload_id WHERE d.id = :id"
_SQL_AUDIT = (
    "INSERT INTO {aud} (id, actor, source_ip, action, entity, entity_id, detail, created_at) "
    "VALUES (:id, :actor, NULL, :action, :entity, :entity_id, :detail, SYSDATE)"
)
_SQL_LISTINGS_DUE = (
    "SELECT l.environment, l.script_id, s.name FROM {ils} l JOIN {scr} s ON s.id = l.script_id "
    "WHERE l.agent_id = :agent_id AND l.refresh_requested_at IS NOT NULL "
    "AND (l.listed_at IS NULL OR l.refresh_requested_at >= l.listed_at) ORDER BY l.id"
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


def _actor(agent_id):
    return "SYSTEM:%s" % agent_id


def _need(conn):
    if conn is None:
        raise ValueError("a conexao do agente e obrigatoria")
    return conn


class RepoSchedulerInput(object):
    """Owner e prefixo vem da configuracao (nunca fixos); os nomes passam por sql_ident."""

    def __init__(self, owner, prefix):
        self._prefix = prefix
        idents = {
            "iup": sql_ident.table(owner, prefix, "input_upload"),
            "idl": sql_ident.table(owner, prefix, "input_delivery"),
            "ils": sql_ident.table(owner, prefix, "input_listing"),
            "scr": sql_ident.table(owner, prefix, "scripts"),
            "aud": sql_ident.table(owner, prefix, "audit"),
            "seq_ils": sql_ident.sequence(owner, prefix, "input_listing"),
        }
        self._sql = dict((name[5:], template.format(**idents))
                         for name, template in globals().items() if name.startswith("_SQL_"))
        self._seq_aud = sql_ident.sequence(owner, prefix, "audit")

    @classmethod
    def from_config(cls, cfg):
        return cls(cfg.oracle.owner.strip(), cfg.oracle.table_prefix.strip())

    def _constraint(self, entity, suffix):
        return "ck_%s%s_%s" % (self._prefix, sql_ident.TABLES[entity]["abrev"], suffix)

    def pending_deliveries(self, agent_id, limit=10, conn=None):
        """Entregas PENDING deste agente pela expressao de ix_<prefixo>idl_pend, das mais antigas, sem conteudo."""
        cur = _need(conn).cursor()
        try:
            cur.execute(self._sql["PENDING"], {"agent_id": agent_id})
            return [dict(zip(COLS_PENDING, row)) for row in cur.fetchmany(int(limit))]
        finally:
            cur.close()

    def read_content(self, upload_id, offset, size, conn=None):
        """Parte do arquivo (offset base 0 na API, + 1 no LOB), de 1 a 1 MiB; sem conteudo: RepoNotFound."""
        off, size_n = int(offset), int(size)
        if off < 0 or size_n < 1 or size_n > repo_inputs.PART_MAX:
            raise repo_errors.RepoViolation("Parte do envio invalida")
        cur = _need(conn).cursor()
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
        """PENDING -> DELIVERED ou FAILED deste agente, com INPUT_DELIVERY; COMMIT. False: nao e deste agente."""
        if state not in ("DELIVERED", "FAILED") or (state == "FAILED") != (reason is not None) \
                or (reason is not None and reason not in repo_inputs.FAILURE_REASONS):
            raise repo_errors.RepoViolation("Situacao ou motivo da entrega invalido",
                                            constraint=self._constraint("input_delivery", "rsn"))
        conn = _need(conn)
        actor = _actor(agent_id)
        with db_conn.transaction(conn):
            cur = conn.cursor()
            try:
                cur.execute(self._sql["MARK"], {"state": state, "reason": reason, "actor": actor,
                                                "id": int(delivery_id), "agent_id": agent_id})
                if cur.rowcount != 1:
                    return False
                cur.execute(self._sql["DELIVERY_UPLOAD"], {"id": int(delivery_id)})
                upload_id, file_name = cur.fetchone()
                detail = u"entrega de %s em %s: %s%s" % (file_name, agent_id, state,
                                                         " (%s)" % reason if reason else "")
                cur.execute(self._sql["AUDIT"], {"id": db_conn.next_id(conn, self._seq_aud), "actor": actor[:ACTOR_MAX],
                                                 "action": repo_inputs.ACTION_DELIVERY,
                                                 "entity": repo_inputs.AUDIT_ENTITY, "entity_id": upload_id,
                                                 "detail": detail[:DETAIL_MAX]})
            finally:
                cur.close()
        return True

    def listings_due(self, agent_id, conn=None):
        """Retratos pedidos a este agente e ainda nao atendidos: [{environment, script_id, script_name}]."""
        cur = _need(conn).cursor()
        try:
            cur.execute(self._sql["LISTINGS_DUE"], {"agent_id": agent_id})
            return [{"environment": e, "script_id": s, "script_name": n} for e, s, n in cur.fetchall()]
        finally:
            cur.close()

    def save_listing(self, agent_id, environment, script_id, listing, file_count, truncated, conn=None):
        """Publica o retrato da pasta (rotina tecnica, sem auditoria); COMMIT."""
        if truncated not in ("Y", "N"):
            raise repo_errors.RepoViolation("truncated invalido", constraint=self._constraint("input_listing", "trunc"))
        conn = _need(conn)
        with db_conn.transaction(conn):
            cur = conn.cursor()
            try:
                db_conn.set_input_types(cur, listing=db_conn.TIPO_CLOB)
                cur.execute(self._sql["SAVE_LISTING"], {
                    "agent_id": agent_id, "environment": environment, "script_id": int(script_id),
                    "listing": listing, "file_count": int(file_count), "truncated": truncated,
                    "actor": _actor(agent_id)})
            finally:
                cur.close()
