# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de auditoria (F7.3, agregado AUDITORIA_AGENTES; AGENTS §4).

tbsss_auditoria com a mesma semantica do repo_fake/auditoria.py (README §2.5, §4.4):
- reservar_id: NEXTVAL da sequence (README §2.7); registrar usa o id recebido ou um proprio;
- ator obrigatorio ate 40 e detalhe ate 1.000, sem corte nem valor padrao (test_06b);
- sem colunas de registro (CR-006, D1): so ator e created_at;
- listar paginado por created_at DESC, id DESC com periodo por intervalo (sem TRUNC, AGENTS §4.12) e
  id_max inclusivo; iterar por cursor com arraysize, sem paginacao por offset (exportacao).
"""
import db_conn
from repo_auditoria import RepoAuditoria
from repo_oracle.base import BaseRepoOracle, validar_campos_auditoria

_LIMITE_TOTAL = 10001
_ARRAYSIZE = 1000
_COLS = ("id", "ator", "ip_origem", "acao", "entidade", "entidade_id", "detalhe", "created_at")


def _lista(cols):
    return ", ".join(cols)


# {aud} recebe apenas o nome qualificado por sql_ident (validado); todo valor entra por bind.
_SQL_INSERIR = (
    "INSERT INTO {aud} (id, ator, ip_origem, acao, entidade, entidade_id, detalhe, created_at) "
    "VALUES (:id, :ator, :ip_origem, :acao, :entidade, :entidade_id, :detalhe, SYSDATE)"
)
_SQL_OBTER = "SELECT " + _lista(_COLS) + " FROM {aud} WHERE id = :id"
_SQL_LISTAR = "SELECT " + _lista(_COLS) + " FROM {aud}{where} ORDER BY created_at DESC, id DESC"
_SQL_CONTAR = "SELECT COUNT(*) FROM (SELECT id FROM {aud} WHERE {where_count})"
_SQL_ITERAR = "SELECT " + _lista(_COLS) + " FROM ({lista}) WHERE ROWNUM <= :limite"


class RepoAuditoriaOracle(BaseRepoOracle, RepoAuditoria):
    """Repositorio da trilha de auditoria com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, segredos=None):
        super(RepoAuditoriaOracle, self).__init__(cfg=cfg, segredos=segredos)
        self._idents = {"aud": self.qualificar_tabela("auditoria")}
        self._sql = {
            "INSERIR": _SQL_INSERIR.format(**self._idents),
            "OBTER": _SQL_OBTER.format(**self._idents),
        }
        self._seq_aud = self.qualificar_sequence("auditoria")

    def _filtros(self, filtros):
        """Clausulas fixas (allowlist) e binds; datas declaradas como TIPO_DATE (README §7.5)."""
        filtros = filtros or {}
        clausulas, binds, datas = [], {}, {}
        if filtros.get("ator"):
            trecho = filtros["ator"].lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clausulas.append("LOWER(ator) LIKE :ator_f ESCAPE '\\'")
            binds["ator_f"] = "%" + trecho + "%"
        if filtros.get("acao"):
            clausulas.append("acao = :acao_f")
            binds["acao_f"] = filtros["acao"]
        if filtros.get("entidade"):
            clausulas.append("entidade = :entidade_f")
            binds["entidade_f"] = filtros["entidade"]
        if filtros.get("entidade_id") is not None:
            clausulas.append("entidade_id = :entidade_id_f")
            binds["entidade_id_f"] = int(filtros["entidade_id"])
        if filtros.get("ip_origem"):
            trecho = filtros["ip_origem"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clausulas.append("ip_origem LIKE :ip_f ESCAPE '\\'")
            binds["ip_f"] = "%" + trecho + "%"
        # Periodo sempre por intervalo, sem TRUNC na coluna indexada (AGENTS §4.12).
        if filtros.get("data_inicio"):
            clausulas.append("created_at >= :data_inicio")
            binds["data_inicio"] = filtros["data_inicio"]
            datas["data_inicio"] = db_conn.TIPO_DATE
        if filtros.get("data_fim"):
            clausulas.append("created_at <= :data_fim")
            binds["data_fim"] = filtros["data_fim"]
            datas["data_fim"] = db_conn.TIPO_DATE
        if filtros.get("id_max") is not None:
            clausulas.append("id <= :id_max")
            binds["id_max"] = int(filtros["id_max"])
        return clausulas, binds, datas

    def reservar_id(self, conn=None):
        """Proximo id da trilha (seq.NEXTVAL), usado antes de gravar a linha (README §4.4)."""
        with self.contexto_leitura(conn=conn) as c:
            return db_conn.proximo_id(c, self._seq_aud)

    def registrar(self, ator, ip, acao, entidade, entidade_id=None, detalhe=None, id=None, conn=None):
        """Grava a linha (com o id reservado, se informado) e devolve o registro criado."""
        validar_campos_auditoria(ator, detalhe)
        with self.transacao_escrita(conn=conn) as c:
            aid = int(id) if id is not None else db_conn.proximo_id(c, self._seq_aud)
            cur = c.cursor()
            try:
                # id repetido: ORA-00001 em pk_<prefixo>auditoria (RepoViolacao com o nome da PK).
                cur.execute(self._sql["INSERIR"], {
                    "id": aid, "ator": ator, "ip_origem": ip, "acao": acao, "entidade": entidade,
                    "entidade_id": entidade_id, "detalhe": detalhe,
                })
                cur.execute(self._sql["OBTER"], {"id": aid})
                return self.tupla_para_dict(_COLS, cur.fetchone())
            finally:
                cur.close()

    def listar(self, filtros=None, pagina=1, tamanho=20, conn=None):
        """Lista por created_at DESC, id DESC, com total limitado a 10.001."""
        clausulas, binds, datas = self._filtros(filtros)
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
                if datas:
                    db_conn.definir_tipos_entrada(cur, **datas)
                cur.execute(sql_conta, binds)
                bruto = cur.fetchone()[0]
            finally:
                cur.close()
            binds_pag = dict(binds)
            binds_pag["inicio"] = inicio
            binds_pag["fim"] = inicio + t
            cur = c.cursor()
            try:
                if datas:
                    db_conn.definir_tipos_entrada(cur, **datas)
                cur.execute(sql_pag, binds_pag)
                itens = [self.tupla_para_dict(_COLS, r[:len(_COLS)]) for r in cur.fetchall()]
            finally:
                cur.close()
        return {
            "itens": itens,
            "total": min(bruto, _LIMITE_TOTAL),
            "pagina": p,
            "tamanho": t,
            "total_limitado": bruto >= _LIMITE_TOTAL,
        }

    def iterar(self, filtros=None, limite=50000):
        """Iterador de ate `limite` registros na ordem de listar, por cursor (arraysize), sem offset."""
        clausulas, binds, datas = self._filtros(filtros)
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        sql = _SQL_ITERAR.format(lista=_SQL_LISTAR.format(where=where, **self._idents))
        binds["limite"] = max(0, int(limite))
        return self._iterar(sql, binds, datas)

    def _iterar(self, sql, binds, datas):
        with self.contexto_leitura() as c:
            cur = c.cursor()
            try:
                cur.arraysize = _ARRAYSIZE
                if datas:
                    db_conn.definir_tipos_entrada(cur, **datas)
                cur.execute(sql, binds)
                while True:
                    linhas = cur.fetchmany(_ARRAYSIZE)
                    if not linhas:
                        break
                    for r in linhas:
                        yield self.tupla_para_dict(_COLS, r)
            finally:
                cur.close()

