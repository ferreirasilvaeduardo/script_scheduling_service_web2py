# -*- coding: utf-8 -*-
"""Repositorio interno do daemon para a saida do ticket (CR-012; README §8.13 e §10, tabela 18).

Fora do contrato da UI e sem gluon. Owner e prefixo vem da configuracao e todo identificador passa por
sql_ident. Nenhuma operacao faz COMMIT: a fase de saida do agente decide a transacao (como scheduler_log).
Toda gravacao exige que a linha (ou, na inclusao, o ticket) seja deste agente; rowcount 0 e posse perdida.
Ator: 'SYSTEM:<agent_id>'. Trocar a situacao e alteracao de negocio (updated_*); anexar partes do zip e
reiniciar uma gravacao interrompida sao rotina tecnica (README §10, CR-006).
"""
import db_conn
import sql_ident

WRITTEN = "WRITTEN"
ALREADY_WRITTEN = "ALREADY_WRITTEN"
OWNERSHIP_LOST = "OWNERSHIP_LOST"
_RESULTS = (WRITTEN, ALREADY_WRITTEN, OWNERSHIP_LOST)
_ORA_DIVERGENT = 20003

PART_MAX = 1024 * 1024
STATES_NO_CONTENT = ("EXCEEDED", "FAILED")
REASONS = ("FILES", "BYTES", "DEADLINE", "ERROR")

# Mesmo protocolo do log (README §8.10): FOR UPDATE WAIT 5, tamanho atual contra o offset esperado e
# DBMS_LOB.COMPARE para reconhecer uma parte ja gravada (COMMIT de desfecho desconhecido). {atrib} e o
# operador de atribuicao do PL/SQL, montado no __init__ (a varredura do test_py36_compat o recusa nos .py).
_PLSQL_APPEND = """DECLARE
  v_lob BLOB;
  v_atual NUMBER(12);
  v_parte NUMBER(12) {attr} DBMS_LOB.GETLENGTH(:part);
BEGIN
  SELECT content INTO v_lob
    FROM {tout}
   WHERE ticket_id = :ticket_id AND agent_id = :agent_id AND state = 'WRITING'
     FOR UPDATE WAIT 5;
  v_atual {attr} DBMS_LOB.GETLENGTH(v_lob);
  IF v_atual = :expected_offset THEN
    DBMS_LOB.APPEND(v_lob, :part);
    :result {attr} 'WRITTEN';
  ELSIF v_atual = :expected_offset + v_parte
        AND DBMS_LOB.COMPARE(v_lob, :part, v_parte, :expected_offset + 1, 1) = 0 THEN
    :result {attr} 'ALREADY_WRITTEN';
  ELSE
    RAISE_APPLICATION_ERROR(-20003, 'SAIDA_OFFSET_DIVERGENTE');
  END IF;
EXCEPTION
  WHEN NO_DATA_FOUND THEN
    :result {attr} 'OWNERSHIP_LOST';
END;"""

_SQL_RESTART = (
    "UPDATE {tout} SET content = EMPTY_BLOB(), file_count = NULL, size_bytes = NULL "
    "WHERE ticket_id = :ticket_id AND agent_id = :agent_id AND state = 'WRITING'"
)
_SQL_INSERT = (
    "INSERT INTO {tout} (id, ticket_id, state, reason, agent_id, file_count, content, created_at, created_by) "
    "SELECT :id, t.id, :state, :reason, :agent_id, :file_count, {content}, SYSDATE, :actor "
    "FROM {tck} t WHERE t.id = :ticket_id AND t.agent_id = :agent_id "
    "AND NOT EXISTS (SELECT 1 FROM {tout} s WHERE s.ticket_id = :ticket_id)"
)
_SQL_COMPLETE = (
    "UPDATE {tout} SET state = 'AVAILABLE', file_count = :file_count, size_bytes = :size_bytes, "
    "updated_at = SYSDATE, updated_by = :actor "
    "WHERE ticket_id = :ticket_id AND agent_id = :agent_id AND state = 'WRITING' "
    "AND DBMS_LOB.GETLENGTH(content) = :size_bytes"
)
_SQL_CLOSE_WRITING = (
    "UPDATE {tout} SET state = :state, reason = :reason, file_count = :file_count, "
    "size_bytes = NULL, content = NULL, updated_at = SYSDATE, updated_by = :actor "
    "WHERE ticket_id = :ticket_id AND agent_id = :agent_id AND state = 'WRITING'"
)
_SQL_FAIL_OF_AGENT = (
    "UPDATE {tout} SET state = 'FAILED', reason = 'ERROR', file_count = NULL, size_bytes = NULL, "
    "content = NULL, updated_at = SYSDATE, updated_by = :actor "
    "WHERE (" + sql_ident.FBI_TOUT_WRITE_CASE + ") = :agent_id"
)
_SQL_STATE = "SELECT state, agent_id FROM {tout} WHERE ticket_id = :ticket_id"


class OutputOffsetMismatch(RuntimeError):
    """O tamanho do zip no banco nao bate com o offset esperado nem com a parte ja gravada."""

    def __init__(self, ticket_id, expected_offset, size):
        RuntimeError.__init__(self, "saida do ticket %s: offset %d (+%d) divergente"
                              % (ticket_id, expected_offset, size))


def _actor(agent_id):
    return "SYSTEM:%s" % agent_id


class RepoSchedulerOutput(object):
    """Owner e prefixo vem da configuracao (nunca fixos); os nomes passam por sql_ident."""

    def __init__(self, owner, prefix):
        sai, tck = sql_ident.table(owner, prefix, "ticket_output"), sql_ident.table(owner, prefix, "tickets")
        self._seq = sql_ident.sequence(owner, prefix, "ticket_output")
        self._plsql = _PLSQL_APPEND.format(tout=sai, attr=":" + "=")
        self._sql_restart = _SQL_RESTART.format(tout=sai)
        self._sql_insert_writing = _SQL_INSERT.format(tout=sai, tck=tck, content="EMPTY_BLOB()")
        self._sql_insert_without_content = _SQL_INSERT.format(tout=sai, tck=tck, content="NULL")
        self._sql_complete = _SQL_COMPLETE.format(tout=sai)
        self._sql_finish = _SQL_CLOSE_WRITING.format(tout=sai)
        self._sql_fail = _SQL_FAIL_OF_AGENT.format(tout=sai)
        self._sql_state = _SQL_STATE.format(tout=sai)

    @classmethod
    def from_config(cls, cfg):
        return cls(cfg.oracle.owner.strip(), cfg.oracle.table_prefix.strip())

    def _proximo_id(self, cur):
        cur.execute("SELECT %s.NEXTVAL FROM DUAL" % self._seq)
        return int(cur.fetchone()[0])

    def _insert(self, cur, sql, ticket_id, agent_id, state_value, reason=None, file_count=None):
        cur.execute(sql, id=self._proximo_id(cur), ticket_id=int(ticket_id), agent_id=agent_id,
                    state=state_value, reason=reason, file_count=file_count, actor=_actor(agent_id))
        return cur.rowcount == 1

    def start(self, conn, ticket_id, agent_id):
        """Linha GRAVANDO com o zip vazio: reinicia a deste agente ou inclui uma nova se o ticket for dele.

        False: o ticket nao e deste agente, ou a saida ja tem situacao final. Sem COMMIT.
        """
        cur = conn.cursor()
        try:
            cur.execute(self._sql_restart, ticket_id=int(ticket_id), agent_id=agent_id)
            if cur.rowcount == 1:
                return True
            return self._insert(cur, self._sql_insert_writing, ticket_id, agent_id, "WRITING")
        finally:
            cur.close()

    def append_chunk(self, conn, ticket_id, agent_id, expected_offset, part):
        """Anexa parte (bytes, ate 1 MiB) em expected_offset: WRITTEN, ALREADY_WRITTEN ou OWNERSHIP_LOST.

        Divergencia de tamanho ou de conteudo: OutputOffsetMismatch. Sem COMMIT.
        """
        if not part or len(part) > PART_MAX:
            raise ValueError("parte da saida vazia ou acima de 1 MiB")
        cur = conn.cursor()
        try:
            db_conn.set_input_types(cur, part=db_conn.TIPO_BLOB)
            resultado = db_conn.output_variable(cur, db_conn.TIPO_VARCHAR, size=20)
            try:
                cur.execute(self._plsql, part=bytes(part), ticket_id=int(ticket_id), agent_id=agent_id,
                            expected_offset=int(expected_offset), result=resultado)
            except Exception as exc:
                if db_conn.classify_error(exc) == ("ORA", _ORA_DIVERGENT):
                    raise OutputOffsetMismatch(ticket_id, int(expected_offset), len(part))
                raise
            valor = db_conn.output_value(resultado)
        finally:
            cur.close()
        if valor not in _RESULTS:
            raise RuntimeError("resultado inesperado do anexar da saida: %r" % (valor,))
        return valor

    def complete(self, conn, ticket_id, agent_id, file_count, size_bytes):
        """GRAVANDO -> DISPONIVEL, so se o zip no banco tiver tamanho_bytes. False: posse perdida. Sem COMMIT."""
        cur = conn.cursor()
        try:
            cur.execute(self._sql_complete, ticket_id=int(ticket_id), agent_id=agent_id,
                        file_count=int(file_count), size_bytes=int(size_bytes), actor=_actor(agent_id))
            return cur.rowcount == 1
        finally:
            cur.close()

    def register_without_content(self, conn, ticket_id, agent_id, state_value, reason, file_count=None):
        """EXCEDEU ou FALHOU sem zip: encerra a linha GRAVANDO deste agente ou inclui uma nova.

        False: o ticket nao e deste agente, ou a saida ja tem situacao final. Sem COMMIT.
        """
        if state_value not in STATES_NO_CONTENT or reason not in REASONS:
            raise ValueError("situacao ou motivo da saida invalido")
        cur = conn.cursor()
        try:
            cur.execute(self._sql_finish, ticket_id=int(ticket_id), agent_id=agent_id, state=state_value,
                        reason=reason, file_count=file_count, actor=_actor(agent_id))
            if cur.rowcount == 1:
                return True
            return self._insert(cur, self._sql_insert_without_content, ticket_id, agent_id, state_value,
                                 reason=reason, file_count=file_count)
        finally:
            cur.close()

    def fail_agent_writing(self, conn, agent_id):
        """Startup check (README §8.13): toda linha GRAVANDO deste agente vira FALHOU. Devolve a contagem."""
        cur = conn.cursor()
        try:
            cur.execute(self._sql_fail, agent_id=agent_id, actor=_actor(agent_id))
            return cur.rowcount
        finally:
            cur.close()

    def output_state(self, conn, ticket_id):
        """(situacao, agent_id) da saida do ticket, ou None; desfaz a duvida de um COMMIT sem resposta."""
        cur = conn.cursor()
        try:
            cur.execute(self._sql_state, ticket_id=int(ticket_id))
            row = cur.fetchone()
        finally:
            cur.close()
        return (row[0].strip(), row[1]) if row else None
