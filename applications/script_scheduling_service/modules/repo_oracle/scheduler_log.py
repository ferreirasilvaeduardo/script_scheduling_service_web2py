# -*- coding: utf-8 -*-
"""Repositorio interno do daemon para o log do ticket (README §8.10; AGENTS §4.13; CR-008 R-11).

Fora do contrato da UI. anexar usa o bloco PL/SQL literal do README §8.10: FOR UPDATE WAIT 5, conferencia de
log_offset_chars contra DBMS_LOB.GETLENGTH, WRITEAPPEND condicional e DBMS_LOB.COMPARE para reconhecer um
bloco ja gravado (COMMIT de desfecho desconhecido). Nunca le o CLOB para concatenar nem o reescreve inteiro.
O COMMIT e do chamador. Gravar o log e rotina tecnica: nada de updated_* (CR-006, README §10).
"""
import db_conn
import sql_ident

GRAVADO = "GRAVADO"
JA_GRAVADO = "JA_GRAVADO"
POSSE_PERDIDA = "POSSE_PERDIDA"
_RESULTADOS = (GRAVADO, JA_GRAVADO, POSSE_PERDIDA)
_ORA_DIVERGENTE = 20002

# {tck} recebe apenas o nome qualificado por sql_ident (validado). {atrib} e o operador de atribuicao do
# PL/SQL, montado no __init__: a varredura do test_py36_compat recusa esse operador em qualquer .py.
_PLSQL_ANEXAR = """DECLARE
  v_lob CLOB;
  v_offset NUMBER(20);
  v_tamanho NUMBER(20) {atrib} LENGTH(:chunk);
BEGIN
  SELECT log_output, log_offset_chars
    INTO v_lob, v_offset
    FROM {tck}
   WHERE id = :ticket_id AND agent_id = :agent_id AND status = 'RUNNING'
     FOR UPDATE WAIT 5;
  IF DBMS_LOB.GETLENGTH(v_lob) <> v_offset THEN
    RAISE_APPLICATION_ERROR(-20002, 'LOG_OFFSET_DIVERGENTE');
  ELSIF v_offset = :offset_esperado THEN
    DBMS_LOB.WRITEAPPEND(v_lob, v_tamanho, :chunk);
    UPDATE {tck}
       SET log_offset_chars = v_offset + v_tamanho
     WHERE id = :ticket_id AND agent_id = :agent_id
       AND status = 'RUNNING' AND log_offset_chars = v_offset;
    IF SQL%ROWCOUNT <> 1 THEN
      RAISE_APPLICATION_ERROR(-20002, 'LOG_OFFSET_DIVERGENTE');
    END IF;
    :resultado {atrib} 'GRAVADO';
  ELSIF v_offset = :offset_esperado + v_tamanho
        AND DBMS_LOB.COMPARE(v_lob, :chunk, v_tamanho,
                             :offset_esperado + 1, 1) = 0 THEN
    :resultado {atrib} 'JA_GRAVADO';
  ELSE
    RAISE_APPLICATION_ERROR(-20002, 'LOG_OFFSET_DIVERGENTE');
  END IF;
EXCEPTION
  WHEN NO_DATA_FOUND THEN
    :resultado {atrib} 'POSSE_PERDIDA';
END;"""

# Quantas posicoes do CLOB um caractere fora do BMP ocupa neste banco: 2 em AL32UTF8 (UTF-16 interno),
# 1 num charset de um byte (o caractere vira o de substituicao). Medido uma vez pelo agente.
_SQL_UNIDADE_SUPLEMENTAR = "SELECT LENGTH(TO_CLOB(UNISTR('\\D83D\\DE00'))) FROM DUAL"

_SQL_TRUNCADO = (
    "UPDATE {tck} SET log_truncated = 'Y' "
    "WHERE id = :ticket_id AND agent_id = :agent_id AND status = 'RUNNING'"
)


class LogOffsetInconsistente(RuntimeError):
    """Offset ou conteudo do CLOB diverge do que a bomba conhece: erro de integridade (README §8.10).

    O pump do ticket para, sem repetir nem descartar o bloco.
    """

    def __init__(self, ticket_id, offset_esperado, tamanho):
        RuntimeError.__init__(self, "LOG_OFFSET_DIVERGENTE ticket=%s offset_esperado=%s tamanho=%s"
                              % (ticket_id, offset_esperado, tamanho))
        self.ticket_id = ticket_id
        self.offset_esperado = offset_esperado
        self.tamanho = tamanho


class RepoSchedulerLog(object):
    """Owner e prefixo vem da configuracao (nunca fixos); os nomes passam por sql_ident."""

    def __init__(self, owner, prefixo):
        self._tck = sql_ident.tabela(owner, prefixo, "tickets")
        self._plsql = _PLSQL_ANEXAR.format(tck=self._tck, atrib=":" + "=")
        self._sql_truncado = _SQL_TRUNCADO.format(tck=self._tck)

    @classmethod
    def da_config(cls, cfg):
        return cls(cfg.oracle.owner.strip(), cfg.oracle.table_prefix.strip())

    def anexar(self, conn, ticket_id, agente_id, offset_esperado, bloco):
        """Anexa bloco (ate 8.000 caracteres) em offset_esperado: GRAVADO, JA_GRAVADO ou POSSE_PERDIDA.

        Divergencia de offset ou de conteudo: LogOffsetInconsistente. Sem COMMIT.
        """
        if not bloco:
            raise ValueError("bloco vazio")
        cur = conn.cursor()
        try:
            db_conn.definir_tipos_entrada(cur, chunk=db_conn.TIPO_CLOB)
            resultado = db_conn.variavel_saida(cur, db_conn.TIPO_VARCHAR, tamanho=20)
            try:
                cur.execute(self._plsql, chunk=bloco, ticket_id=int(ticket_id), agent_id=agente_id,
                            offset_esperado=int(offset_esperado), resultado=resultado)
            except Exception as exc:
                if db_conn.classificar_erro(exc) == ("ORA", _ORA_DIVERGENTE):
                    raise LogOffsetInconsistente(ticket_id, offset_esperado, len(bloco))
                raise
            valor = db_conn.valor_saida(resultado)
        finally:
            cur.close()
        if valor not in _RESULTADOS:
            raise RuntimeError("resultado inesperado do anexar: %r" % (valor,))
        return valor

    def unidade_suplementar(self, conn):
        """1 ou 2: posicoes do CLOB para um caractere fora do BMP neste banco (offset da Bomba)."""
        cur = conn.cursor()
        try:
            cur.execute(_SQL_UNIDADE_SUPLEMENTAR)
            valor = int(cur.fetchone()[0])
        finally:
            cur.close()
        if valor not in (1, 2):
            raise RuntimeError("unidade de CLOB inesperada: %r" % (valor,))
        return valor

    def marcar_truncado(self, conn, ticket_id, agente_id):
        """log_truncado = 'S' no ticket RUNNING deste agente. False se a posse foi perdida. Sem COMMIT."""
        cur = conn.cursor()
        try:
            cur.execute(self._sql_truncado, ticket_id=int(ticket_id), agent_id=agente_id)
            return cur.rowcount == 1
        finally:
            cur.close()
