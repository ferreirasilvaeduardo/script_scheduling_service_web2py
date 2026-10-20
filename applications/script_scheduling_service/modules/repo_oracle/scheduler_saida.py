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

GRAVADO = "GRAVADO"
JA_GRAVADO = "JA_GRAVADO"
POSSE_PERDIDA = "POSSE_PERDIDA"
_RESULTADOS = (GRAVADO, JA_GRAVADO, POSSE_PERDIDA)
_ORA_DIVERGENTE = 20003

PARTE_MAX = 1024 * 1024
SITUACOES_SEM_CONTEUDO = ("EXCEDEU", "FALHOU")
MOTIVOS = ("ARQUIVOS", "BYTES", "PRAZO", "ERRO")

# Mesmo protocolo do log (README §8.10): FOR UPDATE WAIT 5, tamanho atual contra o offset esperado e
# DBMS_LOB.COMPARE para reconhecer uma parte ja gravada (COMMIT de desfecho desconhecido). {atrib} e o
# operador de atribuicao do PL/SQL, montado no __init__ (a varredura do test_py36_compat o recusa nos .py).
_PLSQL_ANEXAR = """DECLARE
  v_lob BLOB;
  v_atual NUMBER(12);
  v_parte NUMBER(12) {atrib} DBMS_LOB.GETLENGTH(:parte);
BEGIN
  SELECT conteudo INTO v_lob
    FROM {sai}
   WHERE ticket_id = :ticket_id AND agente_id = :agente_id AND situacao = 'GRAVANDO'
     FOR UPDATE WAIT 5;
  v_atual {atrib} DBMS_LOB.GETLENGTH(v_lob);
  IF v_atual = :offset_esperado THEN
    DBMS_LOB.APPEND(v_lob, :parte);
    :resultado {atrib} 'GRAVADO';
  ELSIF v_atual = :offset_esperado + v_parte
        AND DBMS_LOB.COMPARE(v_lob, :parte, v_parte, :offset_esperado + 1, 1) = 0 THEN
    :resultado {atrib} 'JA_GRAVADO';
  ELSE
    RAISE_APPLICATION_ERROR(-20003, 'SAIDA_OFFSET_DIVERGENTE');
  END IF;
EXCEPTION
  WHEN NO_DATA_FOUND THEN
    :resultado {atrib} 'POSSE_PERDIDA';
END;"""

_SQL_REINICIAR = (
    "UPDATE {sai} SET conteudo = EMPTY_BLOB(), qtd_arquivos = NULL, tamanho_bytes = NULL "
    "WHERE ticket_id = :ticket_id AND agente_id = :agente_id AND situacao = 'GRAVANDO'"
)
_SQL_INCLUIR = (
    "INSERT INTO {sai} (id, ticket_id, situacao, motivo, agente_id, qtd_arquivos, conteudo, created_at, created_by) "
    "SELECT :id, t.id, :situacao, :motivo, :agente_id, :qtd_arquivos, {conteudo}, SYSDATE, :ator "
    "FROM {tck} t WHERE t.id = :ticket_id AND t.agente_id = :agente_id "
    "AND NOT EXISTS (SELECT 1 FROM {sai} s WHERE s.ticket_id = :ticket_id)"
)
_SQL_CONCLUIR = (
    "UPDATE {sai} SET situacao = 'DISPONIVEL', qtd_arquivos = :qtd_arquivos, tamanho_bytes = :tamanho_bytes, "
    "updated_at = SYSDATE, updated_by = :ator "
    "WHERE ticket_id = :ticket_id AND agente_id = :agente_id AND situacao = 'GRAVANDO' "
    "AND DBMS_LOB.GETLENGTH(conteudo) = :tamanho_bytes"
)
_SQL_ENCERRAR_GRAVANDO = (
    "UPDATE {sai} SET situacao = :situacao, motivo = :motivo, qtd_arquivos = :qtd_arquivos, "
    "tamanho_bytes = NULL, conteudo = NULL, updated_at = SYSDATE, updated_by = :ator "
    "WHERE ticket_id = :ticket_id AND agente_id = :agente_id AND situacao = 'GRAVANDO'"
)
_SQL_FALHAR_DO_AGENTE = (
    "UPDATE {sai} SET situacao = 'FALHOU', motivo = 'ERRO', qtd_arquivos = NULL, tamanho_bytes = NULL, "
    "conteudo = NULL, updated_at = SYSDATE, updated_by = :ator "
    "WHERE (" + sql_ident.FBI_TSAI_GRAV_CASE + ") = :agente_id"
)
_SQL_SITUACAO = "SELECT situacao, agente_id FROM {sai} WHERE ticket_id = :ticket_id"


class SaidaOffsetInconsistente(RuntimeError):
    """O tamanho do zip no banco nao bate com o offset esperado nem com a parte ja gravada."""

    def __init__(self, ticket_id, offset_esperado, tamanho):
        RuntimeError.__init__(self, "saida do ticket %s: offset %d (+%d) divergente"
                              % (ticket_id, offset_esperado, tamanho))


def _ator(agente_id):
    return "SYSTEM:%s" % agente_id


class RepoSchedulerSaida(object):
    """Owner e prefixo vem da configuracao (nunca fixos); os nomes passam por sql_ident."""

    def __init__(self, owner, prefixo):
        q = lambda nome: sql_ident.qualificar(owner, nome, prefixo=prefixo)  # noqa: E731
        sai, tck = q(prefixo + "ticket_saida"), q(prefixo + "tickets")
        self._seq = q("sq_%sticket_saida" % prefixo)
        self._plsql = _PLSQL_ANEXAR.format(sai=sai, atrib=":" + "=")
        self._sql_reiniciar = _SQL_REINICIAR.format(sai=sai)
        self._sql_incluir_gravando = _SQL_INCLUIR.format(sai=sai, tck=tck, conteudo="EMPTY_BLOB()")
        self._sql_incluir_sem_conteudo = _SQL_INCLUIR.format(sai=sai, tck=tck, conteudo="NULL")
        self._sql_concluir = _SQL_CONCLUIR.format(sai=sai)
        self._sql_encerrar = _SQL_ENCERRAR_GRAVANDO.format(sai=sai)
        self._sql_falhar = _SQL_FALHAR_DO_AGENTE.format(sai=sai)
        self._sql_situacao = _SQL_SITUACAO.format(sai=sai)

    @classmethod
    def da_config(cls, cfg):
        return cls(cfg.oracle.owner.strip(), cfg.oracle.table_prefix.strip())

    def _proximo_id(self, cur):
        cur.execute("SELECT %s.NEXTVAL FROM DUAL" % self._seq)
        return int(cur.fetchone()[0])

    def _incluir(self, cur, sql, ticket_id, agente_id, situacao, motivo=None, qtd_arquivos=None):
        cur.execute(sql, id=self._proximo_id(cur), ticket_id=int(ticket_id), agente_id=agente_id,
                    situacao=situacao, motivo=motivo, qtd_arquivos=qtd_arquivos, ator=_ator(agente_id))
        return cur.rowcount == 1

    def iniciar(self, conn, ticket_id, agente_id):
        """Linha GRAVANDO com o zip vazio: reinicia a deste agente ou inclui uma nova se o ticket for dele.

        False: o ticket nao e deste agente, ou a saida ja tem situacao final. Sem COMMIT.
        """
        cur = conn.cursor()
        try:
            cur.execute(self._sql_reiniciar, ticket_id=int(ticket_id), agente_id=agente_id)
            if cur.rowcount == 1:
                return True
            return self._incluir(cur, self._sql_incluir_gravando, ticket_id, agente_id, "GRAVANDO")
        finally:
            cur.close()

    def anexar(self, conn, ticket_id, agente_id, offset_esperado, parte):
        """Anexa parte (bytes, ate 1 MiB) em offset_esperado: GRAVADO, JA_GRAVADO ou POSSE_PERDIDA.

        Divergencia de tamanho ou de conteudo: SaidaOffsetInconsistente. Sem COMMIT.
        """
        if not parte or len(parte) > PARTE_MAX:
            raise ValueError("parte da saida vazia ou acima de 1 MiB")
        cur = conn.cursor()
        try:
            db_conn.definir_tipos_entrada(cur, parte=db_conn.TIPO_BLOB)
            resultado = db_conn.variavel_saida(cur, db_conn.TIPO_VARCHAR, tamanho=20)
            try:
                cur.execute(self._plsql, parte=bytes(parte), ticket_id=int(ticket_id), agente_id=agente_id,
                            offset_esperado=int(offset_esperado), resultado=resultado)
            except Exception as exc:
                if db_conn.classificar_erro(exc) == ("ORA", _ORA_DIVERGENTE):
                    raise SaidaOffsetInconsistente(ticket_id, int(offset_esperado), len(parte))
                raise
            valor = db_conn.valor_saida(resultado)
        finally:
            cur.close()
        if valor not in _RESULTADOS:
            raise RuntimeError("resultado inesperado do anexar da saida: %r" % (valor,))
        return valor

    def concluir(self, conn, ticket_id, agente_id, qtd_arquivos, tamanho_bytes):
        """GRAVANDO -> DISPONIVEL, so se o zip no banco tiver tamanho_bytes. False: posse perdida. Sem COMMIT."""
        cur = conn.cursor()
        try:
            cur.execute(self._sql_concluir, ticket_id=int(ticket_id), agente_id=agente_id,
                        qtd_arquivos=int(qtd_arquivos), tamanho_bytes=int(tamanho_bytes), ator=_ator(agente_id))
            return cur.rowcount == 1
        finally:
            cur.close()

    def registrar_sem_conteudo(self, conn, ticket_id, agente_id, situacao, motivo, qtd_arquivos=None):
        """EXCEDEU ou FALHOU sem zip: encerra a linha GRAVANDO deste agente ou inclui uma nova.

        False: o ticket nao e deste agente, ou a saida ja tem situacao final. Sem COMMIT.
        """
        if situacao not in SITUACOES_SEM_CONTEUDO or motivo not in MOTIVOS:
            raise ValueError("situacao ou motivo da saida invalido")
        cur = conn.cursor()
        try:
            cur.execute(self._sql_encerrar, ticket_id=int(ticket_id), agente_id=agente_id, situacao=situacao,
                        motivo=motivo, qtd_arquivos=qtd_arquivos, ator=_ator(agente_id))
            if cur.rowcount == 1:
                return True
            return self._incluir(cur, self._sql_incluir_sem_conteudo, ticket_id, agente_id, situacao,
                                 motivo=motivo, qtd_arquivos=qtd_arquivos)
        finally:
            cur.close()

    def falhar_gravando_do_agente(self, conn, agente_id):
        """Startup check (README §8.13): toda linha GRAVANDO deste agente vira FALHOU. Devolve a contagem."""
        cur = conn.cursor()
        try:
            cur.execute(self._sql_falhar, agente_id=agente_id, ator=_ator(agente_id))
            return cur.rowcount
        finally:
            cur.close()

    def situacao(self, conn, ticket_id):
        """(situacao, agente_id) da saida do ticket, ou None; desfaz a duvida de um COMMIT sem resposta."""
        cur = conn.cursor()
        try:
            cur.execute(self._sql_situacao, ticket_id=int(ticket_id))
            row = cur.fetchone()
        finally:
            cur.close()
        return (row[0].strip(), row[1]) if row else None
