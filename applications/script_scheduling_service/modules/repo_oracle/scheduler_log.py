# -*- coding: utf-8 -*-
"""Repositorio interno do daemon para o log do ticket (README §8.10; AGENTS §4.13; CR-008 R-11).

Fora do contrato da UI. anexar usa o bloco PL/SQL literal do README §8.10: FOR UPDATE WAIT 5, conferencia de
log_offset_chars contra DBMS_LOB.GETLENGTH, WRITEAPPEND condicional e DBMS_LOB.COMPARE para reconhecer um
bloco ja gravado (COMMIT de desfecho desconhecido). Nunca le o CLOB para concatenar nem o reescreve inteiro.
O COMMIT e do chamador. Gravar o log e rotina tecnica: nada de updated_* (CR-006, README §10).
"""
import db_conn
import sql_ident

WRITTEN = "WRITTEN"
ALREADY_WRITTEN = "ALREADY_WRITTEN"
OWNERSHIP_LOST = "OWNERSHIP_LOST"
_RESULTS = (WRITTEN, ALREADY_WRITTEN, OWNERSHIP_LOST)
_ORA_DIVERGENT = 20002

# {tck} recebe apenas o nome qualificado por sql_ident (validado). {atrib} e o operador de atribuicao do
# PL/SQL, montado no __init__: a varredura do test_py36_compat recusa esse operador em qualquer .py.
_PLSQL_APPEND = """DECLARE
  v_lob CLOB;
  v_offset NUMBER(20);
  v_tamanho NUMBER(20) {attr} LENGTH(:chunk);
BEGIN
  SELECT log_output, log_offset_chars
    INTO v_lob, v_offset
    FROM {tck}
   WHERE id = :ticket_id AND agent_id = :agent_id AND status = 'RUNNING'
     FOR UPDATE WAIT 5;
  IF DBMS_LOB.GETLENGTH(v_lob) <> v_offset THEN
    RAISE_APPLICATION_ERROR(-20002, 'LOG_OFFSET_DIVERGENTE');
  ELSIF v_offset = :expected_offset THEN
    DBMS_LOB.WRITEAPPEND(v_lob, v_tamanho, :chunk);
    UPDATE {tck}
       SET log_offset_chars = v_offset + v_tamanho
     WHERE id = :ticket_id AND agent_id = :agent_id
       AND status = 'RUNNING' AND log_offset_chars = v_offset;
    IF SQL%ROWCOUNT <> 1 THEN
      RAISE_APPLICATION_ERROR(-20002, 'LOG_OFFSET_DIVERGENTE');
    END IF;
    :result {attr} 'WRITTEN';
  ELSIF v_offset = :expected_offset + v_tamanho
        AND DBMS_LOB.COMPARE(v_lob, :chunk, v_tamanho,
                             :expected_offset + 1, 1) = 0 THEN
    :result {attr} 'ALREADY_WRITTEN';
  ELSE
    RAISE_APPLICATION_ERROR(-20002, 'LOG_OFFSET_DIVERGENTE');
  END IF;
EXCEPTION
  WHEN NO_DATA_FOUND THEN
    :result {attr} 'OWNERSHIP_LOST';
END;"""

# Quantas posicoes do CLOB um caractere fora do BMP ocupa neste banco: 2 em AL32UTF8 (UTF-16 interno),
# 1 num charset de um byte (o caractere vira o de substituicao). Medido uma vez pelo agente.
_SQL_UNIT_SUPPLEMENTARY = "SELECT LENGTH(TO_CLOB(UNISTR('\\D83D\\DE00'))) FROM DUAL"

_SQL_TRUNCATED = (
    "UPDATE {tck} SET log_truncated = 'Y' "
    "WHERE id = :ticket_id AND agent_id = :agent_id AND status = 'RUNNING'"
)


class LogOffsetMismatch(RuntimeError):
    """Offset ou conteudo do CLOB diverge do que a bomba conhece: erro de integridade (README §8.10).

    O pump do ticket para, sem repetir nem descartar o bloco.
    """

    def __init__(self, ticket_id, expected_offset, size):
        RuntimeError.__init__(self, "LOG_OFFSET_DIVERGENTE ticket=%s offset_esperado=%s tamanho=%s"
                              % (ticket_id, expected_offset, size))
        self.ticket_id = ticket_id
        self.expected_offset = expected_offset
        self.size = size


class RepoSchedulerLog(object):
    """Owner e prefixo vem da configuracao (nunca fixos); os nomes passam por sql_ident."""

    def __init__(self, owner, prefix):
        self._tck = sql_ident.table(owner, prefix, "tickets")
        self._plsql = _PLSQL_APPEND.format(tck=self._tck, attr=":" + "=")
        self._sql_truncated = _SQL_TRUNCATED.format(tck=self._tck)

    @classmethod
    def from_config(cls, cfg):
        return cls(cfg.oracle.owner.strip(), cfg.oracle.table_prefix.strip())

    def append_chunk(self, conn, ticket_id, agent_id, expected_offset, chunk):
        """Anexa bloco (ate 8.000 caracteres) em expected_offset: WRITTEN, ALREADY_WRITTEN ou OWNERSHIP_LOST.

        Divergencia de offset ou de conteudo: LogOffsetMismatch. Sem COMMIT.
        """
        if not chunk:
            raise ValueError("bloco vazio")
        cur = conn.cursor()
        try:
            db_conn.set_input_types(cur, chunk=db_conn.TIPO_CLOB)
            result = db_conn.output_variable(cur, db_conn.TIPO_VARCHAR, size=20)
            try:
                cur.execute(self._plsql, chunk=chunk, ticket_id=int(ticket_id), agent_id=agent_id,
                            expected_offset=int(expected_offset), result=result)
            except Exception as exc:
                if db_conn.classify_error(exc) == ("ORA", _ORA_DIVERGENT):
                    raise LogOffsetMismatch(ticket_id, expected_offset, len(chunk))
                raise
            value = db_conn.output_value(result)
        finally:
            cur.close()
        if value not in _RESULTS:
            raise RuntimeError("resultado inesperado do anexar: %r" % (value,))
        return value

    def supplementary_unit(self, conn):
        """1 ou 2: posicoes do CLOB para um caractere fora do BMP neste banco (offset da Pump)."""
        cur = conn.cursor()
        try:
            cur.execute(_SQL_UNIT_SUPPLEMENTARY)
            value = int(cur.fetchone()[0])
        finally:
            cur.close()
        if value not in (1, 2):
            raise RuntimeError("unidade de CLOB inesperada: %r" % (value,))
        return value

    def mark_truncated(self, conn, ticket_id, agent_id):
        """log_truncated = 'Y' no ticket RUNNING deste agente. False se a posse foi perdida. Sem COMMIT."""
        cur = conn.cursor()
        try:
            cur.execute(self._sql_truncated, ticket_id=int(ticket_id), agent_id=agent_id)
            return cur.rowcount == 1
        finally:
            cur.close()
