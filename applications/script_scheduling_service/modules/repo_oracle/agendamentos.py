# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de agendamentos (F7.3, agregado AGENDAMENTOS; AGENTS §4).

tbsss_agendamentos com a mesma semantica do repo_fake/agendamentos.py (README §2.5):
- SQL estatico com binds; os modelos ficam nas constantes abaixo e recebem, uma vez por instancia,
  somente identificadores qualificados por sql_ident (owner e prefixo validados);
- CKs e FKs conferidas antes do DML, na ordem do FAKE e com os mesmos nomes (sem gravacao parcial);
- pausar condicional a ativo = 'S' e, quando informada, a proxima_execucao lida (CR-007, R-19):
  rowcount = 0 vira RepoConflito; binds de DATE como TIPO_DATE (README §7.5), sem microssegundos;
- colunas de registro (CR-006, R-g): created_* e o criador original; alterar, pausar e retomar
  gravam updated_* com o ator;
- listar traz parametros_json (CLOB pequeno com as respostas): excecao documentada no README §2.5,
  porque o service avalia cada regra com ele; log_output nunca entra em listagem.
"""
import datetime
import re

import db_conn
import repo_errors
from repo_agendamentos import RepoAgendamentos
from repo_oracle.base import BaseRepoOracle, gravar_auditoria, validar_ator_registro

_LIMITE_TOTAL = 10001
_TIPOS = ("UNICA", "DIARIA", "SEMANAL", "MENSAL", "CRON")
_MOTIVOS_PAUSA = ("USUARIO_INATIVO", "SEM_PERMISSAO", "SCRIPT_INATIVO", "AMBIENTE_INATIVO",
                  "PARAM_INVALIDO", "CRON_INVALIDO", "CONCLUIDO", "MANUAL", "ERRO_INTERNO")
_RE_HORA = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
_RE_DSEM = re.compile(r"^[1-7](,[1-7]){0,6}$")
_TAMANHO_NOME = 60

_COLS = ("id", "nome", "script_id", "ambiente", "usuario_id", "prioridade", "tipo_recorrencia",
         "expressao_cron", "hora_execucao", "dias_semana", "dia_mes", "parametros_json", "data_inicio",
         "data_fim", "proxima_execucao", "ultima_execucao", "ultimo_ticket_id", "pausa_motivo", "ativo",
         "created_at", "created_by", "updated_at", "updated_by")
_COLUNAS_ALTERAVEIS = ("nome", "script_id", "ambiente", "usuario_id", "prioridade",
                       "tipo_recorrencia", "expressao_cron", "hora_execucao", "dias_semana",
                       "dia_mes", "parametros_json", "data_inicio", "data_fim",
                       "proxima_execucao", "ultima_execucao", "ultimo_ticket_id",
                       "pausa_motivo", "ativo")
_DATAS = ("data_inicio", "data_fim", "proxima_execucao", "ultima_execucao")


def _lista(cols, alias=""):
    return ", ".join(alias + c for c in cols)


# -----------------------------------------------------------------------------
# SQL estatico. {agd}, {scr}, {usr}, {amb} e {tck} recebem apenas nomes qualificados por sql_ident
# (validados); todo valor entra por bind.
# -----------------------------------------------------------------------------

_SQL_OBTER = "SELECT " + _lista(_COLS) + " FROM {agd} WHERE id = :id"
_SQL_OBTER_LOCK = _SQL_OBTER + " FOR UPDATE WAIT 5"
_SQL_EXISTE = "SELECT id FROM {agd} WHERE id = :id"
_SQL_LISTAR = "SELECT " + _lista(_COLS) + " FROM {agd}{where} ORDER BY proxima_execucao, id"
_SQL_CONTAR = "SELECT COUNT(*) FROM (SELECT id FROM {agd} WHERE {where_count})"
_SQL_SCR_EXISTE = "SELECT id FROM {scr} WHERE id = :id"
_SQL_USR_EXISTE = "SELECT id FROM {usr} WHERE id = :id"
_SQL_AMB_EXISTE = "SELECT id FROM {amb} WHERE nome = :nome"
_SQL_TICKET_STATUS = "SELECT status FROM {tck} WHERE id = :id"
_SQL_INSERIR = (
    "INSERT INTO {agd} (id, nome, script_id, ambiente, usuario_id, prioridade, tipo_recorrencia, "
    "expressao_cron, hora_execucao, dias_semana, dia_mes, parametros_json, data_inicio, data_fim, "
    "proxima_execucao, ultima_execucao, ultimo_ticket_id, pausa_motivo, ativo, "
    "created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :nome, :script_id, :ambiente, :usuario_id, :prioridade, :tipo_recorrencia, "
    ":expressao_cron, :hora_execucao, :dias_semana, :dia_mes, :parametros_json, :data_inicio, :data_fim, "
    ":proxima_execucao, :ultima_execucao, :ultimo_ticket_id, :pausa_motivo, :ativo, "
    "SYSDATE, :ator, NULL, NULL)"
)
_SQL_ALTERAR = (
    "UPDATE {agd} SET nome = :nome, script_id = :script_id, ambiente = :ambiente, usuario_id = :usuario_id, "
    "prioridade = :prioridade, tipo_recorrencia = :tipo_recorrencia, expressao_cron = :expressao_cron, "
    "hora_execucao = :hora_execucao, dias_semana = :dias_semana, dia_mes = :dia_mes, "
    "parametros_json = :parametros_json, data_inicio = :data_inicio, data_fim = :data_fim, "
    "proxima_execucao = :proxima_execucao, ultima_execucao = :ultima_execucao, "
    "ultimo_ticket_id = :ultimo_ticket_id, pausa_motivo = :pausa_motivo, ativo = :ativo, "
    "updated_at = SYSDATE, updated_by = :ator WHERE id = :id"
)
# CR-007, R-19: so pausa regra ativa e, com antiga_data, so se a proxima_execucao lida nao mudou.
_SQL_PAUSAR = (
    "UPDATE {agd} SET ativo = 'N', pausa_motivo = :motivo, updated_at = SYSDATE, updated_by = :ator "
    "WHERE id = :id AND ativo = 'S'"
)
_SQL_PAUSAR_OTIMISTA = _SQL_PAUSAR + " AND proxima_execucao = :antiga_data"
_SQL_RETOMAR = (
    "UPDATE {agd} SET ativo = 'S', pausa_motivo = NULL, proxima_execucao = :nova_data, "
    "updated_at = SYSDATE, updated_by = :ator WHERE id = :id"
)


def _nulo(valor):
    # O Oracle grava '' como NULL.
    return valor is None or valor == ""


def _igual(atual, esperado):
    """Comparacao nula-segura do 'esperado' ('' e NULL no Oracle; DATE sem fracao)."""
    if atual == "":
        atual = None
    if esperado == "":
        esperado = None
    if isinstance(atual, datetime.datetime) and isinstance(esperado, datetime.datetime):
        return atual.replace(microsecond=0) == esperado.replace(microsecond=0)
    return atual == esperado


def _ler_lob(valor):
    if valor is not None and hasattr(valor, "read"):
        return valor.read()
    return valor


class RepoAgendamentosOracle(BaseRepoOracle, RepoAgendamentos):
    """Repositorio de agendamentos com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, segredos=None):
        super(RepoAgendamentosOracle, self).__init__(cfg=cfg, segredos=segredos)
        self._idents = {
            "agd": self.qualificar_tabela("agendamentos"),
            "scr": self.qualificar_tabela("scripts"),
            "usr": self.qualificar_tabela("usuarios"),
            "amb": self.qualificar_tabela("ambientes"),
            "tck": self.qualificar_tabela("tickets"),
        }
        self._sql = {}
        for nome, modelo in globals().items():
            if nome.startswith("_SQL_") and "{where" not in modelo:
                self._sql[nome[5:]] = modelo.format(**self._idents)
        self._tbl_aud = self.qualificar_tabela("auditoria")
        self._seq_aud = self.qualificar_sequence("auditoria")
        self._seq_agd = self.qualificar_sequence("agendamentos")

    # -------------------------------------------------------------------------
    # Utilitarios
    # -------------------------------------------------------------------------

    def _ck(self, sufixo):
        return self.nome_constraint("ck", "agendamentos", sufixo)

    def _checar_cks(self, r):
        """Espelha NOT NULL e as CKs de tbsss_agendamentos (README §10, tabela 12), na ordem do FAKE."""
        nome = r.get("nome")
        if _nulo(nome) or len(nome) > _TAMANHO_NOME:
            # NOT NULL e tamanho da coluna nao sao constraints nomeadas (ORA-01400 / ORA-12899).
            raise repo_errors.RepoViolacao("nome obrigatorio com ate %d caracteres" % _TAMANHO_NOME)
        trec = r.get("tipo_recorrencia")
        if trec not in _TIPOS:
            raise repo_errors.RepoViolacao("tipo_recorrencia invalido", constraint=self._ck("trec"))
        prio = r.get("prioridade")
        if isinstance(prio, bool) or not isinstance(prio, int) or not (1 <= prio <= 4):
            raise repo_errors.RepoViolacao("prioridade deve estar entre 1 e 4", constraint=self._ck("prio"))
        if r.get("ativo") not in ("S", "N"):
            raise repo_errors.RepoViolacao("ativo deve ser 'S' ou 'N'", constraint=self._ck("ativo"))
        dia = r.get("dia_mes")
        if not _nulo(dia) and (isinstance(dia, bool) or not isinstance(dia, int) or not (1 <= dia <= 31)):
            raise repo_errors.RepoViolacao("dia_mes deve estar entre 1 e 31", constraint=self._ck("dia"))
        hora = r.get("hora_execucao")
        if not _nulo(hora) and not _RE_HORA.match(hora):
            raise repo_errors.RepoViolacao("hora_execucao fora do formato HH:MM", constraint=self._ck("hora"))
        dsem = r.get("dias_semana")
        if not _nulo(dsem) and not _RE_DSEM.match(dsem):
            raise repo_errors.RepoViolacao("dias_semana fora do formato ISO 1-7", constraint=self._ck("dsem"))
        if r.get("data_inicio") is None or r.get("proxima_execucao") is None:
            raise repo_errors.RepoViolacao("data_inicio e proxima_execucao sao obrigatorias")
        if r.get("data_fim") is not None and r["data_fim"] < r["data_inicio"]:
            raise repo_errors.RepoViolacao("data_fim anterior a data_inicio", constraint=self._ck("fim"))
        if not _nulo(r.get("pausa_motivo")) and r["pausa_motivo"] not in _MOTIVOS_PAUSA:
            raise repo_errors.RepoViolacao("pausa_motivo invalido", constraint=self._ck("pausa"))
        exigidos = {"DIARIA": ("hora_execucao",), "SEMANAL": ("hora_execucao", "dias_semana"),
                    "MENSAL": ("hora_execucao", "dia_mes"), "CRON": ("expressao_cron",)}
        for coluna in exigidos.get(trec, ()):
            if _nulo(r.get(coluna)):
                raise repo_errors.RepoViolacao("%s obrigatorio para %s" % (coluna, trec),
                                               constraint=self._ck("campos"))

    def _existe(self, conn, sql, binds):
        cur = conn.cursor()
        try:
            cur.execute(sql, binds)
            return cur.fetchone() is not None
        finally:
            cur.close()

    def _checar_fks(self, conn, reg):
        for existe, sufixo in (
            (self._existe(conn, self._sql["SCR_EXISTE"], {"id": int(reg["script_id"])}), "scr"),
            (self._existe(conn, self._sql["USR_EXISTE"], {"id": int(reg["usuario_id"])}), "usr"),
            (self._existe(conn, self._sql["AMB_EXISTE"], {"nome": reg["ambiente"]}), "amb"),
        ):
            if not existe:
                constraint = self.nome_constraint("fk", "agendamentos", sufixo)
                raise repo_errors.RepoViolacao("Referencia inexistente (%s)" % constraint, constraint=constraint)

    def _linha(self, row):
        reg = self.tupla_para_dict(_COLS, row[:len(_COLS)])
        reg["parametros_json"] = _ler_lob(reg["parametros_json"])
        return reg

    def _uma(self, conn, sql, binds):
        cur = conn.cursor()
        try:
            cur.execute(sql, binds)
            row = cur.fetchone()
            return self._linha(row) if row else None
        finally:
            cur.close()

    def _binds_registro(self, reg, ator):
        binds = dict((c, reg.get(c)) for c in _COLUNAS_ALTERAVEIS)
        binds["script_id"] = int(reg["script_id"])
        binds["usuario_id"] = int(reg["usuario_id"])
        binds["ator"] = ator
        return binds

    @staticmethod
    def _tipos(cur):
        tipos = dict((c, db_conn.TIPO_DATE) for c in _DATAS)
        tipos["parametros_json"] = db_conn.TIPO_CLOB
        db_conn.definir_tipos_entrada(cur, **tipos)

    def _auditar(self, conn, auditoria, id, acao_padrao=None, detalhe_padrao=None, ator=None):
        if auditoria:
            gravar_auditoria(conn, self._tbl_aud, self._seq_aud, auditoria, "tbsss_agendamentos", id)
        elif acao_padrao:
            gravar_auditoria(conn, self._tbl_aud, self._seq_aud,
                             {"ator": ator, "ip": None, "acao": acao_padrao, "detalhe": detalhe_padrao},
                             "tbsss_agendamentos", id)

    def _conferir_esperado(self, id, atual, esperado):
        for campo, valor in (esperado or {}).items():
            if not _igual(atual.get(campo), valor):
                raise repo_errors.RepoConflito("Agendamento ID %s alterado por outra operacao (%s)" % (id, campo))

    # -------------------------------------------------------------------------
    # Leituras
    # -------------------------------------------------------------------------

    def listar(self, filtros=None, pagina=1, tamanho=20, escopo_ambientes=None, conn=None):
        """Lista por proxima_execucao, id, com total limitado a 10.001 (traz parametros_json, sem log)."""
        filtros = filtros or {}
        clausulas, binds = [], {}
        if escopo_ambientes is not None:
            ambs = sorted(set(escopo_ambientes))
            if not ambs:
                clausulas.append("1 = 0")
            else:
                marcas = []
                for n, amb in enumerate(ambs):
                    binds["e%d" % n] = amb
                    marcas.append(":e%d" % n)
                clausulas.append("ambiente IN (" + ", ".join(marcas) + ")")
        if filtros.get("ativo"):
            clausulas.append("ativo = :ativo_f")
            binds["ativo_f"] = filtros["ativo"]
        if filtros.get("script_id") is not None:
            clausulas.append("script_id = :script_id_f")
            binds["script_id_f"] = int(filtros["script_id"])
        if filtros.get("ambiente"):
            clausulas.append("ambiente = :ambiente_f")
            binds["ambiente_f"] = filtros["ambiente"]
        if filtros.get("usuario_id") is not None:
            clausulas.append("usuario_id = :usuario_id_f")
            binds["usuario_id_f"] = int(filtros["usuario_id"])
        if filtros.get("nome"):
            # '%' e '_' digitados contam como literais, como o 'in' do FAKE.
            trecho = filtros["nome"].lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clausulas.append("LOWER(nome) LIKE :nome_f ESCAPE '\\'")
            binds["nome_f"] = "%" + trecho + "%"

        p = 1 if pagina is None else int(pagina)
        t = 20 if tamanho is None else int(tamanho)
        if p < 1:
            p = 1
        if t < 1:
            t = 20
        inicio = (p - 1) * t
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        where_count = " AND ".join(clausulas + ["ROWNUM <= " + str(_LIMITE_TOTAL)])
        sql_conta = _SQL_CONTAR.format(where_count=where_count, **self._idents)
        sql_pag = (
            "SELECT * FROM (SELECT a.*, ROWNUM rn FROM (" + _SQL_LISTAR.format(where=where, **self._idents) + ") a "
            "WHERE ROWNUM <= :fim) WHERE rn > :inicio"
        )
        with self.contexto_leitura(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(sql_conta, binds)
                bruto = cur.fetchone()[0]
                binds_pag = dict(binds)
                binds_pag["inicio"] = inicio
                binds_pag["fim"] = inicio + t
                cur.execute(sql_pag, binds_pag)
                itens = [self._linha(r) for r in cur.fetchall()]
            finally:
                cur.close()
        return {
            "itens": itens,
            "total": min(bruto, _LIMITE_TOTAL),
            "pagina": p,
            "tamanho": t,
            "total_limitado": bruto >= _LIMITE_TOTAL,
        }

    def obter(self, id, conn=None):
        """Agendamento pela PK ou RepoNaoEncontrado."""
        with self.contexto_leitura(conn=conn) as c:
            reg = self._uma(c, self._sql["OBTER"], {"id": int(id)})
        if reg is None:
            raise repo_errors.RepoNaoEncontrado("Agendamento ID %s nao encontrado" % id)
        return reg

    def ticket_status(self, ticket_id, conn=None):
        """Status atual do ticket ou None se inexistente (README §7.5 passo 4)."""
        if ticket_id is None:
            return None
        with self.contexto_leitura(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["TICKET_STATUS"], {"id": int(ticket_id)})
                row = cur.fetchone()
            finally:
                cur.close()
        return row[0].strip() if row and row[0] else None

    # -------------------------------------------------------------------------
    # Gravacoes
    # -------------------------------------------------------------------------

    def inserir(self, dados, auditoria=None, ator=None, conn=None):
        """Insere com as CKs e FKs conferidas antes do INSERT e a auditoria na mesma transacao."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        with self.transacao_escrita(conn=conn) as c:
            agora = db_conn.agora_banco(c)
            novo = {
                "nome": dados.get("nome"),
                "script_id": int(dados["script_id"]),
                "ambiente": dados["ambiente"],
                "usuario_id": int(dados["usuario_id"]),
                "prioridade": dados.get("prioridade", 2),
                "tipo_recorrencia": dados.get("tipo_recorrencia"),
                "expressao_cron": dados.get("expressao_cron"),
                "hora_execucao": dados.get("hora_execucao"),
                "dias_semana": dados.get("dias_semana"),
                "dia_mes": dados.get("dia_mes"),
                "parametros_json": dados.get("parametros_json", "{}"),
                "data_inicio": dados.get("data_inicio") or agora,
                "data_fim": dados.get("data_fim"),
                "proxima_execucao": dados.get("proxima_execucao") or agora,
                "ultima_execucao": dados.get("ultima_execucao"),
                "ultimo_ticket_id": dados.get("ultimo_ticket_id"),
                "pausa_motivo": dados.get("pausa_motivo"),
                "ativo": dados.get("ativo", "S"),
            }
            self._checar_cks(novo)
            self._checar_fks(c, novo)
            aid = db_conn.proximo_id(c, self._seq_agd)
            binds = self._binds_registro(novo, ator_limpo)
            binds["id"] = aid
            cur = c.cursor()
            try:
                self._tipos(cur)
                cur.execute(self._sql["INSERIR"], binds)
            finally:
                cur.close()
            self._auditar(c, auditoria, aid)
            return self.obter(aid, conn=c)

    def alterar(self, id, dados, esperado=None, auditoria=None, ator=None, conn=None):
        """Altera a regra (usuario_id do editor), condicional a 'esperado'; created_* nunca muda."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        with self.transacao_escrita(conn=conn) as c:
            atual = self._uma(c, self._sql["OBTER_LOCK"], {"id": int(id)})
            if atual is None:
                raise repo_errors.RepoNaoEncontrado("Agendamento ID %s nao encontrado" % id)
            self._conferir_esperado(id, atual, esperado)
            resultado = dict(atual)
            for k in _COLUNAS_ALTERAVEIS:
                if k in dados:
                    resultado[k] = dados[k]
            # Validacao completa antes do UPDATE: um UPDATE rejeitado nao altera nenhuma coluna.
            self._checar_cks(resultado)
            self._checar_fks(c, resultado)
            binds = self._binds_registro(resultado, ator_limpo)
            binds["id"] = int(id)
            cur = c.cursor()
            try:
                self._tipos(cur)
                cur.execute(self._sql["ALTERAR"], binds)
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflito("Agendamento ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, auditoria, int(id))
            return self.obter(id, conn=c)

    def pausar(self, id, motivo, antiga_data=None, auditoria=None, ator=None, conn=None):
        """Pausa so regra ativa e, com antiga_data, so se a proxima_execucao nao mudou (CR-007, R-19)."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        with self.transacao_escrita(conn=conn) as c:
            if not self._existe(c, self._sql["EXISTE"], {"id": int(id)}):
                raise repo_errors.RepoNaoEncontrado("Agendamento ID %s nao encontrado" % id)
            if motivo not in _MOTIVOS_PAUSA:
                raise repo_errors.RepoViolacao("pausa_motivo invalido", constraint=self._ck("pausa"))
            binds = {"id": int(id), "motivo": motivo, "ator": ator_limpo}
            cur = c.cursor()
            try:
                if antiga_data is not None:
                    binds["antiga_data"] = antiga_data
                    # TIPO_DATE descarta a fracao: o valor lido mais microssegundos ainda casa (README §7.5).
                    db_conn.definir_tipos_entrada(cur, antiga_data=db_conn.TIPO_DATE)
                    cur.execute(self._sql["PAUSAR_OTIMISTA"], binds)
                else:
                    cur.execute(self._sql["PAUSAR"], binds)
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflito(
                        "Agendamento %s nao esta ativo ou a proxima_execucao mudou (outra operacao)" % id)
            finally:
                cur.close()
            self._auditar(c, auditoria, int(id), "AGD_PAUSAR", "Agendamento pausado: motivo=%s" % motivo,
                          ator_limpo)
            return self.obter(id, conn=c)

    def retomar(self, id, nova_data, esperado=None, auditoria=None, ator=None, conn=None):
        """Retoma: ativo = 'S', pausa_motivo nulo e proxima_execucao = nova_data, condicional a 'esperado'."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        with self.transacao_escrita(conn=conn) as c:
            atual = self._uma(c, self._sql["OBTER_LOCK"], {"id": int(id)})
            if atual is None:
                raise repo_errors.RepoNaoEncontrado("Agendamento ID %s nao encontrado" % id)
            self._conferir_esperado(id, atual, esperado)
            if nova_data is None:
                raise repo_errors.RepoViolacao("proxima_execucao e obrigatoria")
            cur = c.cursor()
            try:
                db_conn.definir_tipos_entrada(cur, nova_data=db_conn.TIPO_DATE)
                cur.execute(self._sql["RETOMAR"], {"id": int(id), "nova_data": nova_data, "ator": ator_limpo})
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflito("Agendamento ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, auditoria, int(id), "CAD_ALTERAR",
                          "Agendamento retomado com proxima_execucao=%s" % nova_data, ator_limpo)
            return self.obter(id, conn=c)
