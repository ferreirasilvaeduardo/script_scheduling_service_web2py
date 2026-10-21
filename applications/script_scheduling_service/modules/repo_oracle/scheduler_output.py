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
  v_parte NUMBER(12) {atrib} DBMS_LOB.GETLENGTH(:parte);
BEGIN
  SELECT content INTO v_lob
    FROM {sai}
   WHERE ticket_id = :ticket_id AND agent_id = :agent_id AND state = 'WRITING'
     FOR UPDATE WAIT 5;
  v_atual {atrib} DBMS_LOB.GETLENGTH(v_lob);
  IF v_atual = :offset_esperado THEN
    DBMS_LOB.APPEND(v_lob, :parte);
    :resultado {atrib} 'WRITTEN';
  ELSIF v_atual = :offset_esperado + v_parte
        AND DBMS_LOB.COMPARE(v_lob, :parte, v_parte, :offset_esperado + 1, 1) = 0 THEN
    :resultado {atrib} 'ALREADY_WRITTEN';
  ELSE
    RAISE_APPLICATION_ERROR(-20003, 'SAIDA_OFFSET_DIVERGENTE');
  END IF;
EXCEPTION
  WHEN NO_DATA_FOUND THEN
    :resultado {atrib} 'OWNERSHIP_LOST';
END;"""

_SQL_RESTART = (
    "UPDATE {sai} SET content = EMPTY_BLOB(), file_count = NULL, size_bytes = NULL "
    "WHERE ticket_id = :ticket_id AND agent_id = :agent_id AND state = 'WRITING'"
)
_SQL_INSERT = (
    "INSERT INTO {sai} (id, ticket_id, state, reason, agent_id, file_count, content, created_at, created_by) "
    "SELECT :id, t.id, :state, :reason, :agent_id, :file_count, {content}, SYSDATE, :actor "
    "FROM {tck} t WHERE t.id = :ticket_id AND t.agent_id = :agent_id "
    "AND NOT EXISTS (SELECT 1 FROM {sai} s WHERE s.ticket_id = :ticket_id)"
)
_SQL_COMPLETE = (
    "UPDATE {sai} SET state = 'AVAILABLE', file_count = :file_count, size_bytes = :size_bytes, "
    "updated_at = SYSDATE, updated_by = :actor "
    "WHERE ticket_id = :ticket_id AND agent_id = :agent_id AND state = 'WRITING' "
    "AND DBMS_LOB.GETLENGTH(content) = :size_bytes"
)
_SQL_CLOSE_WRITING = (
    "UPDATE {sai} SET state = :state, reason = :reason, file_count = :file_count, "
    "size_bytes = NULL, content = NULL, updated_at = SYSDATE, updated_by = :actor "
    "WHERE ticket_id = :ticket_id AND agent_id = :agent_id AND state = 'WRITING'"
)
_SQL_FAIL_OF_AGENT = (
    "UPDATE {sai} SET state = 'FAILED', reason = 'ERROR', file_count = NULL, size_bytes = NULL, "
    "content = NULL, updated_at = SYSDATE, updated_by = :actor "
    "WHERE (" + sql_ident.FBI_TOUT_WRITE_CASE + ") = :agent_id"
)
_SQL_STATE = "SELECT state, agent_id FROM {sai} WHERE ticket_id = :ticket_id"


class OutputOffsetMismatch(RuntimeError):
    """O tamanho do zip no banco nao bate com o offset esperado nem com a parte ja gravada."""

    def __init__(self, ticket_id, offset_esperado, tamanho):
        RuntimeError.__init__(self, "saida do ticket %s: offset %d (+%d) divergente"
                              % (ticket_id, offset_esperado, tamanho))


def _actor(agente_id):
    return "SYSTEM:%s" % agente_id


class RepoSchedulerOutput(object):
    """Owner e prefixo vem da configuracao (nunca fixos); os nomes passam por sql_ident."""

    def __init__(self, owner, prefixo):
        sai, tck = sql_ident.table(owner, prefixo, "ticket_output"), sql_ident.table(owner, prefixo, "tickets")
        self._seq = sql_ident.sequence(owner, prefixo, "ticket_output")
        self._plsql = _PLSQL_APPEND.format(sai=sai, atrib=":" + "=")
        self._sql_reiniciar = _SQL_RESTART.format(sai=sai)
        self._sql_incluir_gravando = _SQL_INSERT.format(sai=sai, tck=tck, content="EMPTY_BLOB()")
        self._sql_incluir_sem_conteudo = _SQL_INSERT.format(sai=sai, tck=tck, content="NULL")
        self._sql_complete = _SQL_COMPLETE.format(sai=sai)
        self._sql_encerrar = _SQL_CLOSE_WRITING.format(sai=sai)
        self._sql_falhar = _SQL_FAIL_OF_AGENT.format(sai=sai)
        self._sql_situacao = _SQL_STATE.format(sai=sai)

    @classmethod
    def from_config(cls, cfg):
        return cls(cfg.oracle.owner.strip(), cfg.oracle.table_prefix.strip())

    def _proximo_id(self, cur):
        cur.execute("SELECT %s.NEXTVAL FROM DUAL" % self._seq)
        return int(cur.fetchone()[0])

    def _incluir(self, cur, sql, ticket_id, agente_id, situacao, reason=None, file_count=None):
        cur.execute(sql, id=self._proximo_id(cur), ticket_id=int(ticket_id), agent_id=agente_id,
                    state=situacao, reason=reason, file_count=file_count, actor=_actor(agente_id))
        return cur.rowcount == 1

    def start(self, conn, ticket_id, agente_id):
        """Linha GRAVANDO com o zip vazio: reinicia a deste agente ou inclui uma nova se o ticket for dele.

        False: o ticket nao e deste agente, ou a saida ja tem situacao final. Sem COMMIT.
        """
        cur = conn.cursor()
        try:
            cur.execute(self._sql_reiniciar, ticket_id=int(ticket_id), agent_id=agente_id)
            if cur.rowcount == 1:
                return True
            return self._incluir(cur, self._sql_incluir_gravando, ticket_id, agente_id, "WRITING")
        finally:
            cur.close()

    def append_chunk(self, conn, ticket_id, agente_id, offset_esperado, parte):
        """Anexa parte (bytes, ate 1 MiB) em offset_esperado: WRITTEN, ALREADY_WRITTEN ou OWNERSHIP_LOST.

        Divergencia de tamanho ou de conteudo: OutputOffsetMismatch. Sem COMMIT.
        """
        if not parte or len(parte) > PART_MAX:
            raise ValueError("parte da saida vazia ou acima de 1 MiB")
        cur = conn.cursor()
        try:
            db_conn.set_input_types(cur, parte=db_conn.TIPO_BLOB)
            resultado = db_conn.output_variable(cur, db_conn.TIPO_VARCHAR, tamanho=20)
            try:
                cur.execute(self._plsql, parte=bytes(parte), ticket_id=int(ticket_id), agent_id=agente_id,
                            offset_esperado=int(offset_esperado), resultado=resultado)
            except Exception as exc:
                if db_conn.classify_error(exc) == ("ORA", _ORA_DIVERGENT):
                    raise OutputOffsetMismatch(ticket_id, int(offset_esperado), len(parte))
                raise
            valor = db_conn.output_value(resultado)
        finally:
            cur.close()
        if valor not in _RESULTS:
            raise RuntimeError("resultado inesperado do anexar da saida: %r" % (valor,))
        return valor

    def complete(self, conn, ticket_id, agente_id, qtd_arquivos, tamanho_bytes):
        """GRAVANDO -> DISPONIVEL, so se o zip no banco tiver tamanho_bytes. False: posse perdida. Sem COMMIT."""
        cur = conn.cursor()
        try:
            cur.execute(self._sql_complete, ticket_id=int(ticket_id), agent_id=agente_id,
                        file_count=int(qtd_arquivos), size_bytes=int(tamanho_bytes), actor=_actor(agente_id))
            return cur.rowcount == 1
        finally:
            cur.close()

    def register_without_content(self, conn, ticket_id, agente_id, situacao, motivo, qtd_arquivos=None):
        """EXCEDEU ou FALHOU sem zip: encerra a linha GRAVANDO deste agente ou inclui uma nova.

        False: o ticket nao e deste agente, ou a saida ja tem situacao final. Sem COMMIT.
        """
        if situacao not in STATES_NO_CONTENT or motivo not in REASONS:
            raise ValueError("situacao ou motivo da saida invalido")
        cur = conn.cursor()
        try:
            cur.execute(self._sql_encerrar, ticket_id=int(ticket_id), agent_id=agente_id, state=situacao,
                        reason=motivo, file_count=qtd_arquivos, actor=_actor(agente_id))
            if cur.rowcount == 1:
                return True
            return self._incluir(cur, self._sql_incluir_sem_conteudo, ticket_id, agente_id, situacao,
                                 reason=motivo, file_count=qtd_arquivos)
        finally:
            cur.close()

    def fail_agent_writing(self, conn, agente_id):
        """Startup check (README §8.13): toda linha GRAVANDO deste agente vira FALHOU. Devolve a contagem."""
        cur = conn.cursor()
        try:
            cur.execute(self._sql_falhar, agent_id=agente_id, actor=_actor(agente_id))
            return cur.rowcount
        finally:
            cur.close()

    def output_state(self, conn, ticket_id):
        """(situacao, agente_id) da saida do ticket, ou None; desfaz a duvida de um COMMIT sem resposta."""
        cur = conn.cursor()
        try:
            cur.execute(self._sql_situacao, ticket_id=int(ticket_id))
            row = cur.fetchone()
        finally:
            cur.close()
        return (row[0].strip(), row[1]) if row else None
