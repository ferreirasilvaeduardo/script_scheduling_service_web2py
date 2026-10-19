# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de catalogo (F7.3, agregado CATALOGO; AGENTS §4).

Ambientes, scripts, homologacoes (tbsss_script_amb), parametros e vinculos (tbsss_script_param),
com a mesma semantica do repo_fake/catalogo.py (README §2.5):
- SQL estatico com binds; os modelos ficam nas constantes abaixo e recebem, uma vez por instancia,
  somente identificadores qualificados por sql_ident (owner e prefixo validados);
- paginacao ROWNUM com total limitado a 10.001 (CR-007, R-29) e ordem binaria por nome/codigo e id;
- CKs, UKs, FKs e regras de dependencia validadas antes do DML, com os nomes do FAKE;
- colunas de registro (CR-006): created_* no INSERT, updated_* so na alteracao de negocio;
- vinculos por diferenca (R-f); script_param preserva o created_* de cada parametro que continua.
Ordem de locks: tbsss_scripts -> tbsss_parametros (nunca o inverso).
"""
import datetime
import re

import db_conn
import repo_errors
from repo_catalogo import RepoCatalogo
from repo_oracle.base import BaseRepoOracle, gravar_auditoria, validar_ator_registro

_RE_AMB_NOME = re.compile(r"^[A-Z0-9_]{1,30}$")
_RE_PRM_CODIGO = re.compile(r"^[a-z0-9_]{1,30}$")
_RE_PRM_FLAG = re.compile(r"^-{1,2}[A-Za-z0-9][A-Za-z0-9_-]{0,27}$")
_RE_SHA = re.compile(r"^[0-9a-f]{64}$")

_LIMITE_TOTAL = 10001
_LOTE_IN = 500

_COLS_AMB = ("id", "nome", "descricao", "conexao", "ativo",
             "created_at", "created_by", "updated_at", "updated_by")
_COLS_SCR = ("id", "nome", "descricao", "grupo", "categoria", "etapa", "interpretador", "path_file",
             "tipo_param", "max_qtd_parallel_env", "timeout_seg", "ativo", "sha256_homologado",
             "created_at", "created_by", "updated_at", "updated_by")
_COLS_PRM = ("id", "codigo", "param_nomeado", "label", "descricao", "tipo_componente", "opcoes_json",
             "valor_padrao", "regex_validacao", "sensivel", "ativo",
             "created_at", "created_by", "updated_at", "updated_by")
_COLS_SPRM = ("id", "parametro_id", "ordem", "obrigatorio", "valor_padrao_sub",
              "created_at", "created_by", "updated_at", "updated_by")

_CAMPOS_SCR_ALTERAVEIS = ("nome", "descricao", "grupo", "categoria", "etapa", "interpretador", "path_file",
                          "tipo_param", "max_qtd_parallel_env", "timeout_seg", "ativo", "sha256_homologado")


def _lista(cols, alias=""):
    return ", ".join(alias + c for c in cols)


# -----------------------------------------------------------------------------
# SQL estatico. {amb}, {scr}, {samb}, {prm}, {sprm}, {pscr} e {pamb} recebem apenas nomes
# qualificados por sql_ident (validados); todo valor entra por bind.
# -----------------------------------------------------------------------------

_SQL_AMB_OBTER = "SELECT " + _lista(_COLS_AMB) + " FROM {amb} WHERE id = :id"
_SQL_AMB_OBTER_LOCK = _SQL_AMB_OBTER + " FOR UPDATE WAIT 5"
_SQL_AMB_POR_NOME = "SELECT id FROM {amb} WHERE nome = :nome"
_SQL_AMB_EXISTE = "SELECT id FROM {amb} WHERE id = :id"
_SQL_AMB_LISTAR = (
    "SELECT " + _lista(_COLS_AMB) + " FROM {amb}{where} "
    "ORDER BY NLSSORT(nome, 'NLS_SORT=BINARY'), id"
)
_SQL_AMB_CONTAR = "SELECT COUNT(*) FROM (SELECT id FROM {amb} WHERE {where_count})"
_SQL_AMB_INSERIR = (
    "INSERT INTO {amb} (id, nome, descricao, conexao, ativo, created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :nome, :descricao, :conexao, :ativo, SYSDATE, :ator, NULL, NULL)"
)
_SQL_AMB_ALTERAR = (
    "UPDATE {amb} SET descricao = :descricao, conexao = :conexao, ativo = :ativo, "
    "updated_at = SYSDATE, updated_by = :ator WHERE id = :id"
)

_SQL_SCR_OBTER = "SELECT " + _lista(_COLS_SCR) + " FROM {scr} WHERE id = :id"
_SQL_SCR_OBTER_LOCK = _SQL_SCR_OBTER + " FOR UPDATE WAIT 5"
_SQL_SCR_LOCK = "SELECT id FROM {scr} WHERE id = :id FOR UPDATE WAIT 5"
# uk_tbsss_scr_nome diferencia maiusculas (README §8.5): comparacao exata, sem UPPER/LOWER.
_SQL_SCR_NOME_EM_USO = "SELECT id FROM {scr} WHERE nome = :nome AND id <> :id"
_SQL_SCR_LISTAR = (
    "SELECT " + _lista(_COLS_SCR, "s.") + ", "
    "(SELECT COUNT(*) FROM {sprm} sp WHERE sp.script_id = s.id) qtd_parametros "
    "FROM {scr} s{where} "
    "ORDER BY NLSSORT(s.nome, 'NLS_SORT=BINARY'), s.id"
)
_SQL_SCR_CONTAR = "SELECT COUNT(*) FROM (SELECT s.id FROM {scr} s WHERE {where_count})"
_SQL_SCR_INSERIR = (
    "INSERT INTO {scr} (id, nome, descricao, grupo, categoria, etapa, interpretador, path_file, tipo_param, "
    "max_qtd_parallel_env, timeout_seg, ativo, sha256_homologado, created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :nome, :descricao, :grupo, :categoria, :etapa, :interpretador, :path_file, :tipo_param, "
    ":max_qtd_parallel_env, :timeout_seg, :ativo, :sha256_homologado, SYSDATE, :ator, NULL, NULL)"
)
_SQL_SCR_ALTERAR = (
    "UPDATE {scr} SET nome = :nome, descricao = :descricao, grupo = :grupo, categoria = :categoria, "
    "etapa = :etapa, interpretador = :interpretador, path_file = :path_file, tipo_param = :tipo_param, "
    "max_qtd_parallel_env = :max_qtd_parallel_env, timeout_seg = :timeout_seg, ativo = :ativo, "
    "sha256_homologado = :sha256_homologado, updated_at = SYSDATE, updated_by = :ator WHERE id = :id"
)
_SQL_SCR_CARIMBAR = "UPDATE {scr} SET updated_at = SYSDATE, updated_by = :ator WHERE id = :id"
_SQL_SCR_HOMOLOGADOS = (
    "SELECT sa.script_id, a.nome FROM {samb} sa JOIN {amb} a ON a.id = sa.ambiente_id "
    "WHERE sa.script_id IN ({ids})"
)

_SQL_SAMB_DO_SCRIPT = "SELECT id, ambiente_id FROM {samb} WHERE script_id = :script_id"
_SQL_SAMB_EXCLUIR = "DELETE FROM {samb} WHERE id = :id"
_SQL_SAMB_INSERIR = (
    "INSERT INTO {samb} (id, script_id, ambiente_id, created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :script_id, :ambiente_id, SYSDATE, :ator, NULL, NULL)"
)

_SQL_PRM_OBTER = "SELECT " + _lista(_COLS_PRM) + " FROM {prm} WHERE id = :id"
_SQL_PRM_OBTER_LOCK = _SQL_PRM_OBTER + " FOR UPDATE WAIT 5"
_SQL_PRM_POR_CODIGO = "SELECT id FROM {prm} WHERE codigo = :codigo"
_SQL_PRM_EXISTE = "SELECT id FROM {prm} WHERE id = :id"
_SQL_PRM_LISTAR = (
    "SELECT " + _lista(_COLS_PRM, "p.") + ", "
    "(SELECT COUNT(*) FROM {sprm} sp WHERE sp.parametro_id = p.id) qtd_scripts "
    "FROM {prm} p{where} "
    "ORDER BY NLSSORT(p.codigo, 'NLS_SORT=BINARY'), p.id"
)
_SQL_PRM_CONTAR = "SELECT COUNT(*) FROM (SELECT p.id FROM {prm} p WHERE {where_count})"
_SQL_PRM_INSERIR = (
    "INSERT INTO {prm} (id, codigo, param_nomeado, label, descricao, tipo_componente, opcoes_json, "
    "valor_padrao, regex_validacao, sensivel, ativo, created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :codigo, :param_nomeado, :label, :descricao, :tipo_componente, :opcoes_json, "
    ":valor_padrao, :regex_validacao, :sensivel, :ativo, SYSDATE, :ator, NULL, NULL)"
)
_SQL_PRM_ALTERAR = (
    "UPDATE {prm} SET param_nomeado = :param_nomeado, label = :label, descricao = :descricao, "
    "tipo_componente = :tipo_componente, opcoes_json = :opcoes_json, valor_padrao = :valor_padrao, "
    "regex_validacao = :regex_validacao, sensivel = :sensivel, ativo = :ativo, "
    "updated_at = SYSDATE, updated_by = :ator WHERE id = :id"
)
_SQL_PRM_SCRIPTS_VINCULADOS = (
    "SELECT s.tipo_param, s.ativo FROM {sprm} sp JOIN {scr} s ON s.id = sp.script_id "
    "WHERE sp.parametro_id = :parametro_id"
)
_SQL_PRM_VINCULOS = (
    "SELECT " + _lista(_COLS_SCR, "s.") + " FROM {scr} s "
    "WHERE EXISTS (SELECT 1 FROM {sprm} sp WHERE sp.script_id = s.id AND sp.parametro_id = :parametro_id) "
    "ORDER BY NLSSORT(s.nome, 'NLS_SORT=BINARY'), s.id"
)
# Ordem de locks: o script dono ja esta travado; os parametros vem depois (scripts -> parametros).
_SQL_PRM_LOCK_FLAG = "SELECT id, param_nomeado FROM {prm} WHERE id = :id FOR UPDATE WAIT 5"

_SQL_SPRM_DO_SCRIPT = (
    "SELECT " + _lista(_COLS_SPRM) + " FROM {sprm} WHERE script_id = :script_id ORDER BY ordem, id"
)
_SQL_SPRM_PARAMETROS = (
    "SELECT sp.parametro_id FROM {sprm} sp WHERE sp.script_id = :script_id"
)
_SQL_SPRM_OBTER = (
    "SELECT " + _lista(_COLS_PRM, "p.") + ", sp.ordem, sp.obrigatorio, sp.valor_padrao_sub "
    "FROM {sprm} sp JOIN {prm} p ON p.id = sp.parametro_id "
    "WHERE sp.script_id = :script_id ORDER BY sp.ordem, sp.id"
)
_SQL_SPRM_EXCLUIR_DO_SCRIPT = "DELETE FROM {sprm} WHERE script_id = :script_id"
_SQL_SPRM_INSERIR = (
    "INSERT INTO {sprm} (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, "
    "created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :script_id, :parametro_id, :ordem, :obrigatorio, :valor_padrao_sub, "
    ":created_at, :created_by, :updated_at, :updated_by)"
)
# Vinculo novo ou alterado: o carimbo vem do relogio do banco (SYSDATE), nunca do no.
_SQL_SPRM_INSERIR_NOVO = (
    "INSERT INTO {sprm} (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, "
    "created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :script_id, :parametro_id, :ordem, :obrigatorio, :valor_padrao_sub, "
    "SYSDATE, :ator, NULL, NULL)"
)
_SQL_SPRM_INSERIR_ALTERADO = (
    "INSERT INTO {sprm} (id, script_id, parametro_id, ordem, obrigatorio, valor_padrao_sub, "
    "created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :script_id, :parametro_id, :ordem, :obrigatorio, :valor_padrao_sub, "
    ":created_at, :created_by, SYSDATE, :ator)"
)

# README §4.3.A: script ativo, homologado em ambiente ativo; o admin dispensa perfil_scr/perfil_amb.
_SQL_EXEC_ADMIN = (
    "SELECT " + _lista(_COLS_SCR, "s.") + " FROM {scr} s "
    "WHERE s.ativo = 'S' "
    "AND EXISTS (SELECT 1 FROM {samb} sa JOIN {amb} a ON a.id = sa.ambiente_id "
    "WHERE sa.script_id = s.id AND a.ativo = 'S') "
    "ORDER BY NLSSORT(s.nome, 'NLS_SORT=BINARY'), s.id"
)
_SQL_EXEC_PERFIL = (
    "SELECT " + _lista(_COLS_SCR, "s.") + " FROM {scr} s "
    "WHERE s.ativo = 'S' "
    "AND EXISTS (SELECT 1 FROM {pscr} ps WHERE ps.perfil_id = :perfil_id AND ps.script_id = s.id) "
    "AND EXISTS (SELECT 1 FROM {samb} sa JOIN {amb} a ON a.id = sa.ambiente_id "
    "JOIN {pamb} pa ON pa.ambiente_id = sa.ambiente_id AND pa.perfil_id = :perfil_id "
    "WHERE sa.script_id = s.id AND a.ativo = 'S') "
    "ORDER BY NLSSORT(s.nome, 'NLS_SORT=BINARY'), s.id"
)


def _like_contem(valor, maiusculas):
    """Trecho para LIKE ... ESCAPE '\\': '%' e '_' digitados contam como literais (como no FAKE)."""
    v = valor.upper() if maiusculas else valor.lower()
    v = v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + v + "%"


def _pagina_tamanho(pagina, tamanho):
    # Valor nao numerico propaga ValueError/TypeError, como no FAKE: o controller valida antes.
    p = 1 if pagina is None else int(pagina)
    t = 20 if tamanho is None else int(tamanho)
    if p < 1:
        p = 1
    if t < 1:
        t = 20
    return p, t


def _igual(atual, esperado):
    """Comparacao nula-segura do 'esperado' ('' e NULL no Oracle; DATE sem fracao)."""
    if atual == "":
        atual = None
    if esperado == "":
        esperado = None
    if isinstance(atual, datetime.datetime) and isinstance(esperado, datetime.datetime):
        return atual.replace(microsecond=0) == esperado.replace(microsecond=0)
    return atual == esperado


class RepoCatalogoOracle(BaseRepoOracle, RepoCatalogo):
    """Repositorio de catalogo com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, segredos=None):
        super(RepoCatalogoOracle, self).__init__(cfg=cfg, segredos=segredos)
        self._idents = {
            "amb": self.qualificar_tabela("ambientes"),
            "scr": self.qualificar_tabela("scripts"),
            "samb": self.qualificar_tabela("script_amb"),
            "prm": self.qualificar_tabela("parametros"),
            "sprm": self.qualificar_tabela("script_param"),
            "pscr": self.qualificar_tabela("perfil_scr"),
            "pamb": self.qualificar_tabela("perfil_amb"),
        }
        self._sql = {}
        for nome, modelo in globals().items():
            if nome.startswith("_SQL_") and "{where" not in modelo and "{ids}" not in modelo:
                self._sql[nome[5:]] = modelo.format(**self._idents)
        self._tbl_aud = self.qualificar_tabela("auditoria")
        self._seq_aud = self.qualificar_sequence("auditoria")
        self._seq = {
            "ambientes": self.qualificar_sequence("ambientes"),
            "scripts": self.qualificar_sequence("scripts"),
            "script_amb": self.qualificar_sequence("script_amb"),
            "parametros": self.qualificar_sequence("parametros"),
            "script_param": self.qualificar_sequence("script_param"),
        }

    # -------------------------------------------------------------------------
    # Utilitarios
    # -------------------------------------------------------------------------

    def _ck(self, entidade, sufixo):
        return self.nome_constraint("ck", entidade, sufixo)

    def _sql_dinamico(self, modelo, **partes):
        """Completa um modelo com identificadores e clausulas fixas (allowlist) montadas pelo codigo."""
        valores = dict(self._idents)
        valores.update(partes)
        return modelo.format(**valores)

    def _executar(self, cur, sql, binds=None):
        if binds is None:
            cur.execute(sql)
        else:
            cur.execute(sql, binds)

    def _uma(self, conn, sql, binds, cols):
        cur = conn.cursor()
        try:
            self._executar(cur, sql, binds)
            row = cur.fetchone()
            return self.tupla_para_dict(cols, row) if row else None
        finally:
            cur.close()

    def _existe(self, conn, sql, binds):
        cur = conn.cursor()
        try:
            self._executar(cur, sql, binds)
            return cur.fetchone() is not None
        finally:
            cur.close()

    def _listar(self, conn, modelo_lista, modelo_conta, cols, clausulas, binds, pagina, tamanho, extras=()):
        """Paginacao ROWNUM (AGENTS §4.4) e COUNT limitado a 10.001 na mesma leitura."""
        p, t = _pagina_tamanho(pagina, tamanho)
        inicio = (p - 1) * t
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        where_count = " AND ".join(list(clausulas) + ["ROWNUM <= " + str(_LIMITE_TOTAL)])
        sql_lista = self._sql_dinamico(modelo_lista, where=where)
        sql_pag = (
            "SELECT * FROM (SELECT a.*, ROWNUM rn FROM (" + sql_lista + ") a WHERE ROWNUM <= :fim) "
            "WHERE rn > :inicio"
        )
        sql_conta = self._sql_dinamico(modelo_conta, where_count=where_count)
        cur = conn.cursor()
        try:
            cur.execute(sql_conta, binds)
            bruto = cur.fetchone()[0]
            binds_pag = dict(binds)
            binds_pag["inicio"] = inicio
            binds_pag["fim"] = inicio + t
            cur.execute(sql_pag, binds_pag)
            todas = tuple(cols) + tuple(extras)
            itens = [self.tupla_para_dict(todas, r[:len(todas)]) for r in cur.fetchall()]
        finally:
            cur.close()
        return {
            "itens": itens,
            "total": min(bruto, _LIMITE_TOTAL),
            "pagina": p,
            "tamanho": t,
            "total_limitado": bruto >= _LIMITE_TOTAL,
        }

    def _auditar(self, conn, auditoria, entidade, entidade_id):
        gravar_auditoria(conn, self._tbl_aud, self._seq_aud, auditoria, entidade, entidade_id)

    def _conferir_esperado(self, atual, esperado, rotulo, id):
        for campo, valor in (esperado or {}).items():
            if not _igual(atual.get(campo), valor):
                raise repo_errors.RepoConflito("%s ID %s alterado por outra operacao (%s)" % (rotulo, id, campo))

    # -------------------------------------------------------------------------
    # Ambientes (tbsss_ambientes)
    # -------------------------------------------------------------------------

    def ambientes_listar(self, filtros=None, pagina=1, tamanho=20, conn=None):
        """Lista ambientes paginados por nome ASC, id ASC."""
        filtros = filtros or {}
        clausulas, binds = [], {}
        if filtros.get("nome"):
            clausulas.append("UPPER(nome) LIKE :nome_f ESCAPE '\\'")
            binds["nome_f"] = _like_contem(filtros["nome"], maiusculas=True)
        if filtros.get("ativo"):
            clausulas.append("ativo = :ativo_f")
            binds["ativo_f"] = filtros["ativo"]
        with self.contexto_leitura(conn=conn) as c:
            return self._listar(c, _SQL_AMB_LISTAR, _SQL_AMB_CONTAR, _COLS_AMB, clausulas, binds, pagina, tamanho)

    def ambientes_obter(self, id, conn=None):
        """Retorna dict do ambiente pelo ID ou lanca RepoNaoEncontrado."""
        with self.contexto_leitura(conn=conn) as c:
            reg = self._uma(c, self._sql["AMB_OBTER"], {"id": int(id)}, _COLS_AMB)
        if reg is None:
            raise repo_errors.RepoNaoEncontrado("Ambiente ID %s nao encontrado" % id)
        return reg

    def ambientes_inserir(self, dados, auditoria=None, ator=None, conn=None):
        """Insere ambiente (CKs, UK e DSN sem credencial) e audita na mesma transacao."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        nome = dados.get("nome")
        if not nome or not _RE_AMB_NOME.match(nome):
            raise repo_errors.RepoViolacao("Nome de ambiente invalido (esperado: 1-30 chars [A-Z0-9_])",
                                           constraint=self._ck("ambientes", "nome"))
        conexao = dados.get("conexao")
        ativo = dados.get("ativo", "S")

        with self.transacao_escrita(conn=conn) as c:
            # Mesma ordem do FAKE: UK antes das CKs. ck_..._amb_nome garante maiusculas, entao a
            # igualdade exata equivale a UK sem distincao de caixa.
            if self._existe(c, self._sql["AMB_POR_NOME"], {"nome": nome}):
                raise repo_errors.RepoViolacao("Ambiente com nome '%s' ja existe" % nome,
                                               constraint=self.nome_constraint("uk", "ambientes", "nome"))
            if conexao and "@" in conexao:
                raise repo_errors.RepoViolacao("Conexao nao pode conter credencial (@)",
                                               constraint=self._ck("ambientes", "conexao"))
            if ativo not in ("S", "N"):
                raise repo_errors.RepoViolacao("Flag ativo deve ser 'S' ou 'N'",
                                               constraint=self._ck("ambientes", "ativo"))
            aid = db_conn.proximo_id(c, self._seq["ambientes"])
            cur = c.cursor()
            try:
                cur.execute(self._sql["AMB_INSERIR"], {
                    "id": aid, "nome": nome, "descricao": dados.get("descricao", ""),
                    "conexao": conexao, "ativo": ativo, "ator": ator_limpo,
                })
            finally:
                cur.close()
            self._auditar(c, auditoria, "tbsss_ambientes", aid)
            return self.ambientes_obter(aid, conn=c)

    def ambientes_alterar(self, id, dados, esperado=None, auditoria=None, ator=None, conn=None):
        """Altera ambiente (nome imutavel, tr_tbsss_amb_bu), condicional a 'esperado'."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        with self.transacao_escrita(conn=conn) as c:
            atual = self._uma(c, self._sql["AMB_OBTER_LOCK"], {"id": int(id)}, _COLS_AMB)
            if atual is None:
                raise repo_errors.RepoNaoEncontrado("Ambiente ID %s nao encontrado" % id)
            self._conferir_esperado(atual, esperado, "Ambiente", id)

            novo_nome = dados.get("nome")
            if novo_nome is not None and novo_nome != atual["nome"]:
                raise repo_errors.RepoViolacao("Nome de ambiente e imutavel",
                                               constraint=self.nome_trigger("ambientes", "bu"))
            novo = dict(atual)
            novo_conexao = dados.get("conexao")
            if novo_conexao is not None:
                if "@" in novo_conexao:
                    raise repo_errors.RepoViolacao("Conexao nao pode conter credencial (@)",
                                                   constraint=self._ck("ambientes", "conexao"))
                novo["conexao"] = novo_conexao
            elif "conexao" in dados:
                novo["conexao"] = None
            if "descricao" in dados:
                novo["descricao"] = dados["descricao"]
            novo_ativo = dados.get("ativo")
            if novo_ativo is not None:
                if novo_ativo not in ("S", "N"):
                    raise repo_errors.RepoViolacao("Flag ativo deve ser 'S' ou 'N'",
                                                   constraint=self._ck("ambientes", "ativo"))
                novo["ativo"] = novo_ativo

            cur = c.cursor()
            try:
                cur.execute(self._sql["AMB_ALTERAR"], {
                    "id": int(id), "descricao": novo["descricao"], "conexao": novo["conexao"],
                    "ativo": novo["ativo"], "ator": ator_limpo,
                })
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflito("Ambiente ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, auditoria, "tbsss_ambientes", int(id))
            return self.ambientes_obter(id, conn=c)

    # -------------------------------------------------------------------------
    # Scripts (tbsss_scripts)
    # -------------------------------------------------------------------------

    def _homologados_por_script(self, conn, script_ids):
        """{script_id: [nomes em ordem alfabetica]} com IN por contagem controlada, em lotes."""
        resultado = dict((sid, []) for sid in script_ids)
        ids = list(script_ids)
        cur = conn.cursor()
        try:
            for i in range(0, len(ids), _LOTE_IN):
                lote = ids[i:i + _LOTE_IN]
                marcas = ", ".join(":s%d" % n for n in range(len(lote)))
                binds = dict(("s%d" % n, v) for n, v in enumerate(lote))
                cur.execute(self._sql_dinamico(_SQL_SCR_HOMOLOGADOS, ids=marcas), binds)
                for sid, nome in cur.fetchall():
                    resultado[sid].append(nome)
        finally:
            cur.close()
        for nomes in resultado.values():
            nomes.sort()
        return resultado

    def scripts_listar(self, filtros=None, pagina=1, tamanho=20, conn=None):
        """Lista scripts por nome ASC, id ASC, com ambientes_homologados e qtd_parametros."""
        filtros = filtros or {}
        clausulas, binds = [], {}
        if filtros.get("nome"):
            clausulas.append("LOWER(s.nome) LIKE :nome_f ESCAPE '\\'")
            binds["nome_f"] = _like_contem(filtros["nome"], maiusculas=False)
        for chave in ("grupo", "categoria", "interpretador", "ativo"):
            if filtros.get(chave):
                clausulas.append("s." + chave + " = :" + chave + "_f")
                binds[chave + "_f"] = filtros[chave]
        with self.contexto_leitura(conn=conn) as c:
            pagina_ = self._listar(c, _SQL_SCR_LISTAR, _SQL_SCR_CONTAR, _COLS_SCR, clausulas, binds,
                                   pagina, tamanho, extras=("qtd_parametros",))
            homolog = self._homologados_por_script(c, [it["id"] for it in pagina_["itens"]])
        for item in pagina_["itens"]:
            item["ambientes_homologados"] = homolog.get(item["id"], [])
        return pagina_

    def scripts_obter(self, id, conn=None):
        """Retorna dict do script pelo ID ou lanca RepoNaoEncontrado."""
        with self.contexto_leitura(conn=conn) as c:
            reg = self._uma(c, self._sql["SCR_OBTER"], {"id": int(id)}, _COLS_SCR)
        if reg is None:
            raise repo_errors.RepoNaoEncontrado("Script ID %s nao encontrado" % id)
        return reg

    def _validar_script(self, base):
        """CKs da tabela 6 sobre o registro resultante, na ordem do FAKE (sem cortar nada)."""
        if not base.get("nome"):
            raise repo_errors.RepoViolacao("Nome de script e obrigatorio")
        if base.get("tipo_param", "NOMEADO") not in ("NOMEADO", "SEQUENCIAL", "NENHUM"):
            raise repo_errors.RepoViolacao("Tipo de parametro invalido", constraint=self._ck("scripts", "tparam"))
        if base.get("ativo", "S") not in ("S", "N"):
            raise repo_errors.RepoViolacao("Flag ativo deve ser 'S' ou 'N'", constraint=self._ck("scripts", "ativo"))
        if base.get("interpretador") not in ("PYTHON3", "BASH", "SH"):
            raise repo_errors.RepoViolacao("Interpretador fora da allowlist", constraint=self._ck("scripts", "int"))
        pfile = base.get("path_file") or ""
        # ck_tbsss_scr_path (README §10, CR-005): absoluto, sem '..', '//' nem '\'; ate 500 caracteres.
        if (not pfile.startswith("/") or ".." in pfile or "//" in pfile or "\\" in pfile
                or len(pfile) > 500):
            raise repo_errors.RepoViolacao("path_file deve ser absoluto e sem '..'",
                                           constraint=self._ck("scripts", "path"))
        if not (1 <= int(base.get("max_qtd_parallel_env", 1)) <= 999):
            raise repo_errors.RepoViolacao("max_qtd_parallel_env deve estar entre 1 e 999",
                                           constraint=self._ck("scripts", "paral"))
        tmout = base.get("timeout_seg")
        if tmout is not None and int(tmout) <= 0:
            raise repo_errors.RepoViolacao("timeout_seg deve ser maior que zero",
                                           constraint=self._ck("scripts", "tmout"))
        sha = base.get("sha256_homologado")
        if sha is not None and not _RE_SHA.match(sha):
            raise repo_errors.RepoViolacao("sha256_homologado invalido", constraint=self._ck("scripts", "sha"))

    def _nome_script_livre(self, conn, nome, id_atual):
        if self._existe(conn, self._sql["SCR_NOME_EM_USO"], {"nome": nome, "id": id_atual}):
            raise repo_errors.RepoViolacao("Script com nome '%s' ja existe" % nome,
                                           constraint=self.nome_constraint("uk", "scripts", "nome"))

    def _flags_dos_parametros(self, conn, parametro_ids):
        """Trava os parametros (scripts -> parametros) e devolve {id: param_nomeado}; ausente = FK."""
        flags = {}
        for pid in parametro_ids:
            cur = conn.cursor()
            try:
                cur.execute(self._sql["PRM_LOCK_FLAG"], {"id": pid})
                row = cur.fetchone()
            finally:
                cur.close()
            if row is None:
                raise repo_errors.RepoViolacao("Parametro ID %s nao existe" % pid,
                                               constraint=self.nome_constraint("fk", "script_param", "prm"))
            flags[pid] = row[1]
        return flags

    def _regras_tipo_param(self, tipo_param, flags):
        # README §6.3: NENHUM nao aceita vinculos; NOMEADO exige flag em todo parametro vinculado.
        if tipo_param == "NENHUM" and flags:
            raise repo_errors.RepoViolacao("Script NENHUM com vinculos", constraint="sss_scr_nenhum_vinculado")
        if tipo_param == "NOMEADO":
            for pid in flags:
                if not flags[pid]:
                    raise repo_errors.RepoViolacao("Parametro sem flag em script NOMEADO",
                                                   constraint="sss_scr_nomeado_sem_flag")

    def _binds_script(self, reg, ator):
        tmout = reg.get("timeout_seg")
        return {
            "nome": reg["nome"], "descricao": reg.get("descricao"), "grupo": reg.get("grupo"),
            "categoria": reg.get("categoria"), "etapa": reg.get("etapa"),
            "interpretador": reg["interpretador"], "path_file": reg["path_file"],
            "tipo_param": reg.get("tipo_param", "NOMEADO"),
            "max_qtd_parallel_env": int(reg.get("max_qtd_parallel_env", 1)),
            "timeout_seg": int(tmout) if tmout is not None else None,
            "ativo": reg.get("ativo", "S"), "sha256_homologado": reg.get("sha256_homologado"),
            "ator": ator,
        }

    def scripts_inserir(self, dados, auditoria=None, ator=None, conn=None):
        """Insere script (CKs, UK sensivel a maiusculas) e audita na mesma transacao."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        base = dict(dados)
        base.setdefault("descricao", "")
        self._validar_script(base)
        with self.transacao_escrita(conn=conn) as c:
            self._nome_script_livre(c, base["nome"], 0)
            sid = db_conn.proximo_id(c, self._seq["scripts"])
            binds = self._binds_script(base, ator_limpo)
            binds["id"] = sid
            cur = c.cursor()
            try:
                cur.execute(self._sql["SCR_INSERIR"], binds)
            finally:
                cur.close()
            self._auditar(c, auditoria, "tbsss_scripts", sid)
            return self.scripts_obter(sid, conn=c)

    def scripts_alterar(self, id, dados, esperado=None, auditoria=None, ator=None, conn=None):
        """Altera script (CKs, esperado nulo-seguro e regras de tipo_param x vinculos)."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        with self.transacao_escrita(conn=conn) as c:
            atual = self._uma(c, self._sql["SCR_OBTER_LOCK"], {"id": int(id)}, _COLS_SCR)
            if atual is None:
                raise repo_errors.RepoNaoEncontrado("Script ID %s nao encontrado" % id)
            self._conferir_esperado(atual, esperado, "Script", id)

            mudancas = dict((k, dados[k]) for k in _CAMPOS_SCR_ALTERAVEIS if k in dados)
            novo = dict(atual)
            novo.update(mudancas)
            self._validar_script(novo)
            if novo["nome"] != atual["nome"]:
                self._nome_script_livre(c, novo["nome"], int(id))
            if novo["tipo_param"] != atual["tipo_param"]:
                cur = c.cursor()
                try:
                    cur.execute(self._sql["SPRM_PARAMETROS"], {"script_id": int(id)})
                    vinculados = [r[0] for r in cur.fetchall()]
                finally:
                    cur.close()
                self._regras_tipo_param(novo["tipo_param"], self._flags_dos_parametros(c, vinculados))

            binds = self._binds_script(novo, ator_limpo)
            binds["id"] = int(id)
            cur = c.cursor()
            try:
                cur.execute(self._sql["SCR_ALTERAR"], binds)
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflito("Script ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, auditoria, "tbsss_scripts", int(id))
            return self.scripts_obter(id, conn=c)

    # -------------------------------------------------------------------------
    # Homologacao de scripts por ambiente (tbsss_script_amb)
    # -------------------------------------------------------------------------

    def homologacao_obter(self, script_id, conn=None):
        """Retorna lista ordenada de ambiente_id homologados para o script."""
        with self.contexto_leitura(conn=conn) as c:
            if not self._existe(c, self._sql["SCR_OBTER"], {"id": int(script_id)}):
                raise repo_errors.RepoNaoEncontrado("Script ID %s nao encontrado" % script_id)
            cur = c.cursor()
            try:
                cur.execute(self._sql["SAMB_DO_SCRIPT"], {"script_id": int(script_id)})
                return sorted(r[1] for r in cur.fetchall())
            finally:
                cur.close()

    def homologacao_salvar(self, script_id, ambiente_ids, esperado=None, auditoria=None, ator=None, conn=None):
        """Substitui as homologacoes por diferenca (CR-006, R-f), sob o lock do script."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        sid = int(script_id)
        ids = sorted(set(int(x) for x in (ambiente_ids or [])))
        with self.transacao_escrita(conn=conn) as c:
            if not self._existe(c, self._sql["SCR_LOCK"], {"id": sid}):
                raise repo_errors.RepoNaoEncontrado("Script ID %s nao encontrado" % script_id)
            cur = c.cursor()
            try:
                cur.execute(self._sql["SAMB_DO_SCRIPT"], {"script_id": sid})
                atuais = dict((r[1], r[0]) for r in cur.fetchall())
            finally:
                cur.close()
            if esperado is not None and sorted(int(x) for x in esperado) != sorted(atuais):
                raise repo_errors.RepoConflito("Homologacao do script ID %s alterada por outra operacao" % script_id)
            for aid in ids:
                if not self._existe(c, self._sql["AMB_EXISTE"], {"id": aid}):
                    raise repo_errors.RepoViolacao("Ambiente ID %s nao existe" % aid,
                                                   constraint=self.nome_constraint("fk", "script_amb", "amb"))

            remover = [{"id": atuais[a]} for a in atuais if a not in ids]
            incluir = []
            for aid in ids:
                if aid not in atuais:
                    incluir.append({"id": db_conn.proximo_id(c, self._seq["script_amb"]),
                                    "script_id": sid, "ambiente_id": aid, "ator": ator_limpo})
            cur = c.cursor()
            try:
                if remover:
                    cur.executemany(self._sql["SAMB_EXCLUIR"], remover)
                if incluir:
                    cur.executemany(self._sql["SAMB_INSERIR"], incluir)
                if remover or incluir:
                    cur.execute(self._sql["SCR_CARIMBAR"], {"id": sid, "ator": ator_limpo})
            finally:
                cur.close()
            self._auditar(c, auditoria, "tbsss_scripts", sid)
            return self.homologacao_obter(sid, conn=c)

    # -------------------------------------------------------------------------
    # Parametros (tbsss_parametros)
    # -------------------------------------------------------------------------

    def parametros_listar(self, filtros=None, pagina=1, tamanho=20, conn=None):
        """Lista parametros por codigo ASC, id ASC, com qtd_scripts na mesma consulta."""
        filtros = filtros or {}
        clausulas, binds = [], {}
        if filtros.get("codigo"):
            clausulas.append("LOWER(p.codigo) LIKE :codigo_f ESCAPE '\\'")
            binds["codigo_f"] = _like_contem(filtros["codigo"], maiusculas=False)
        if filtros.get("label"):
            clausulas.append("LOWER(p.label) LIKE :label_f ESCAPE '\\'")
            binds["label_f"] = _like_contem(filtros["label"], maiusculas=False)
        for chave in ("tipo_componente", "ativo"):
            if filtros.get(chave):
                clausulas.append("p." + chave + " = :" + chave + "_f")
                binds[chave + "_f"] = filtros[chave]
        with self.contexto_leitura(conn=conn) as c:
            return self._listar(c, _SQL_PRM_LISTAR, _SQL_PRM_CONTAR, _COLS_PRM, clausulas, binds,
                                pagina, tamanho, extras=("qtd_scripts",))

    def parametros_obter(self, id, conn=None):
        """Retorna dict do parametro pelo ID ou lanca RepoNaoEncontrado."""
        with self.contexto_leitura(conn=conn) as c:
            reg = self._uma(c, self._sql["PRM_OBTER"], {"id": int(id)}, _COLS_PRM)
        if reg is None:
            raise repo_errors.RepoNaoEncontrado("Parametro ID %s nao encontrado" % id)
        return reg

    def _validar_flags_parametro(self, campo, valor):
        if valor not in ("S", "N"):
            sufixo = "sens" if campo == "sensivel" else "ativo"
            raise repo_errors.RepoViolacao("Flag %s deve ser 'S' ou 'N'" % campo,
                                           constraint=self._ck("parametros", sufixo))

    def _validar_tipo_componente(self, valor):
        if valor not in ("TEXT", "NUMBER", "DATE", "SELECT", "CHECKBOX"):
            raise repo_errors.RepoViolacao("Tipo de componente invalido", constraint=self._ck("parametros", "tcomp"))

    def _validar_flag_nomeado(self, flag):
        if flag is not None and not _RE_PRM_FLAG.match(flag):
            raise repo_errors.RepoViolacao("Flag param_nomeado invalida", constraint=self._ck("parametros", "flag"))

    def parametros_inserir(self, dados, auditoria=None, ator=None, conn=None):
        """Insere parametro (CKs e UK) e audita na mesma transacao."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        codigo = dados.get("codigo")
        if not codigo or not _RE_PRM_CODIGO.match(codigo):
            raise repo_errors.RepoViolacao("Codigo de parametro invalido (esperado: 1-30 chars [a-z0-9_])",
                                           constraint=self._ck("parametros", "codigo"))
        tcomp = dados.get("tipo_componente")
        flag = dados.get("param_nomeado") or None
        sens = dados.get("sensivel", "N")
        ativo = dados.get("ativo", "S")
        with self.transacao_escrita(conn=conn) as c:
            # Mesma ordem do FAKE: a UK e conferida antes das demais CKs.
            if self._existe(c, self._sql["PRM_POR_CODIGO"], {"codigo": codigo}):
                raise repo_errors.RepoViolacao("Parametro com codigo '%s' ja existe" % codigo,
                                               constraint=self.nome_constraint("uk", "parametros", "codigo"))
            self._validar_tipo_componente(tcomp)
            self._validar_flag_nomeado(flag)
            self._validar_flags_parametro("sensivel", sens)
            self._validar_flags_parametro("ativo", ativo)
            pid = db_conn.proximo_id(c, self._seq["parametros"])
            cur = c.cursor()
            try:
                cur.execute(self._sql["PRM_INSERIR"], {
                    "id": pid, "codigo": codigo, "param_nomeado": flag, "label": dados.get("label", ""),
                    "descricao": dados.get("descricao", ""), "tipo_componente": tcomp,
                    "opcoes_json": dados.get("opcoes_json"), "valor_padrao": dados.get("valor_padrao"),
                    "regex_validacao": dados.get("regex_validacao"), "sensivel": sens, "ativo": ativo,
                    "ator": ator_limpo,
                })
            finally:
                cur.close()
            self._auditar(c, auditoria, "tbsss_parametros", pid)
            return self.parametros_obter(pid, conn=c)

    def parametros_alterar(self, id, dados, esperado=None, auditoria=None, ator=None, conn=None):
        """Altera parametro com as regras de dependencia de vinculo na mesma transacao."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        with self.transacao_escrita(conn=conn) as c:
            atual = self._uma(c, self._sql["PRM_OBTER_LOCK"], {"id": int(id)}, _COLS_PRM)
            if atual is None:
                raise repo_errors.RepoNaoEncontrado("Parametro ID %s nao encontrado" % id)
            self._conferir_esperado(atual, esperado, "Parametro", id)

            mudancas = dict((k, dados[k]) for k in ("label", "descricao", "opcoes_json", "valor_padrao",
                                                    "regex_validacao") if k in dados)
            if "param_nomeado" in dados:
                flag = dados["param_nomeado"] or None
                self._validar_flag_nomeado(flag)
                mudancas["param_nomeado"] = flag
            if "tipo_componente" in dados:
                self._validar_tipo_componente(dados["tipo_componente"])
                mudancas["tipo_componente"] = dados["tipo_componente"]
            for campo in ("sensivel", "ativo"):
                if campo in dados:
                    self._validar_flags_parametro(campo, dados[campo])
                    mudancas[campo] = dados[campo]

            # Regras de dependencia (README §10) sob o lock do parametro.
            cur = c.cursor()
            try:
                cur.execute(self._sql["PRM_SCRIPTS_VINCULADOS"], {"parametro_id": int(id)})
                scripts = [{"tipo_param": r[0], "ativo": (r[1] or "").strip()} for r in cur.fetchall()]
            finally:
                cur.close()
            if scripts and mudancas.get("tipo_componente", atual["tipo_componente"]) != atual["tipo_componente"]:
                raise repo_errors.RepoViolacao("Tipo de componente com vinculos", constraint="sss_prm_tipo_vinculado")
            if "param_nomeado" in mudancas and mudancas["param_nomeado"] != atual["param_nomeado"] \
                    and any(s["tipo_param"] == "NOMEADO" for s in scripts):
                raise repo_errors.RepoViolacao("Flag com vinculo NOMEADO", constraint="sss_prm_flag_nomeado")
            if mudancas.get("ativo") == "N" and atual["ativo"] == "S" and any(s["ativo"] == "S" for s in scripts):
                raise repo_errors.RepoViolacao("Desativacao com vinculo a script ativo",
                                               constraint="sss_prm_vinculo_ativo")

            novo = dict(atual)
            novo.update(mudancas)
            cur = c.cursor()
            try:
                cur.execute(self._sql["PRM_ALTERAR"], {
                    "id": int(id), "param_nomeado": novo["param_nomeado"], "label": novo["label"],
                    "descricao": novo["descricao"], "tipo_componente": novo["tipo_componente"],
                    "opcoes_json": novo["opcoes_json"], "valor_padrao": novo["valor_padrao"],
                    "regex_validacao": novo["regex_validacao"], "sensivel": novo["sensivel"],
                    "ativo": novo["ativo"], "ator": ator_limpo,
                })
                if cur.rowcount != 1:
                    raise repo_errors.RepoConflito("Parametro ID %s alterado por outra operacao" % id)
            finally:
                cur.close()
            self._auditar(c, auditoria, "tbsss_parametros", int(id))
            return self.parametros_obter(id, conn=c)

    def parametro_vinculos(self, parametro_id, conn=None):
        """Retorna os scripts vinculados ao parametro (verificacao de desativacao)."""
        with self.contexto_leitura(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["PRM_VINCULOS"], {"parametro_id": int(parametro_id)})
                return [self.tupla_para_dict(_COLS_SCR, r) for r in cur.fetchall()]
            finally:
                cur.close()

    # -------------------------------------------------------------------------
    # Vinculos de parametros em scripts (tbsss_script_param)
    # -------------------------------------------------------------------------

    def script_params_obter(self, script_id, conn=None):
        """Retorna os parametros vinculados ao script, por ordem, com os dados do vinculo."""
        with self.contexto_leitura(conn=conn) as c:
            if not self._existe(c, self._sql["SCR_OBTER"], {"id": int(script_id)}):
                raise repo_errors.RepoNaoEncontrado("Script ID %s nao encontrado" % script_id)
            cur = c.cursor()
            try:
                cur.execute(self._sql["SPRM_OBTER"], {"script_id": int(script_id)})
                linhas = cur.fetchall()
            finally:
                cur.close()
        resultado = []
        cols = _COLS_PRM + ("ordem", "obrigatorio", "valor_padrao_sub")
        for r in linhas:
            item = self.tupla_para_dict(cols, r)
            item["script_id"] = int(script_id)
            item["parametro_id"] = item["id"]
            resultado.append(item)
        return resultado

    def script_params_salvar(self, script_id, vinculos, esperado=None, auditoria=None, ator=None, conn=None):
        """Substitui os vinculos do script, preservando o created_* de quem continua (CR-006, R-f)."""
        ator_limpo = validar_ator_registro(auditoria, ator)
        sid = int(script_id)
        with self.transacao_escrita(conn=conn) as c:
            script = self._uma(c, self._sql["SCR_OBTER_LOCK"], {"id": sid}, _COLS_SCR)
            if script is None:
                raise repo_errors.RepoNaoEncontrado("Script ID %s nao encontrado" % script_id)
            cur = c.cursor()
            try:
                cur.execute(self._sql["SPRM_DO_SCRIPT"], {"script_id": sid})
                anteriores_lista = [self.tupla_para_dict(_COLS_SPRM, r) for r in cur.fetchall()]
            finally:
                cur.close()
            if esperado is not None:
                lidos = [(v["parametro_id"], v["ordem"], v["obrigatorio"], v.get("valor_padrao_sub"))
                         for v in anteriores_lista]
                if [tuple(e) for e in esperado] != lidos:
                    raise repo_errors.RepoConflito("Vinculos do script ID %s alterados por outra operacao" % script_id)

            params_vistos, ordens_vistas, novos = set(), set(), []
            for item in (vinculos or []):
                pid = int(item["parametro_id"])
                if not self._existe(c, self._sql["PRM_EXISTE"], {"id": pid}):
                    raise repo_errors.RepoViolacao("Parametro ID %s nao existe" % pid,
                                                   constraint=self.nome_constraint("fk", "script_param", "prm"))
                if pid in params_vistos:
                    raise repo_errors.RepoViolacao("Parametro duplicado no script",
                                                   constraint=self.nome_constraint("uk", "script_param", "scr_prm"))
                params_vistos.add(pid)
                ordem = int(item["ordem"])
                if ordem < 1:
                    raise repo_errors.RepoViolacao("Ordem deve ser >= 1", constraint=self._ck("script_param", "ordem"))
                if ordem in ordens_vistas:
                    raise repo_errors.RepoViolacao("Ordem duplicada no script",
                                                   constraint=self.nome_constraint("uk", "script_param", "scr_ord"))
                ordens_vistas.add(ordem)
                obrig = item.get("obrigatorio", "S")
                if obrig not in ("S", "N"):
                    raise repo_errors.RepoViolacao("obrigatorio deve ser 'S' ou 'N'",
                                                   constraint=self._ck("script_param", "obrig"))
                novos.append({"parametro_id": pid, "ordem": ordem, "obrigatorio": obrig,
                              "valor_padrao_sub": item.get("valor_padrao_sub")})

            # Flags lidas sob lock (scripts -> parametros), em ordem de id para evitar deadlock.
            flags = self._flags_dos_parametros(c, sorted(params_vistos))
            self._regras_tipo_param(script["tipo_param"], flags)

            anteriores = dict((v["parametro_id"], v) for v in anteriores_lista)
            mudou = set(anteriores) != set(nv["parametro_id"] for nv in novos)
            lote_novo, lote_mantido, lote_alterado = [], [], []
            for nv in novos:
                binds = {"id": db_conn.proximo_id(c, self._seq["script_param"]), "script_id": sid,
                         "parametro_id": nv["parametro_id"], "ordem": nv["ordem"],
                         "obrigatorio": nv["obrigatorio"], "valor_padrao_sub": nv["valor_padrao_sub"]}
                velho = anteriores.get(nv["parametro_id"])
                if velho is None:
                    binds["ator"] = ator_limpo
                    lote_novo.append(binds)
                    continue
                binds["created_at"] = velho["created_at"]
                binds["created_by"] = velho["created_by"]
                if any(not _igual(nv[k], velho.get(k)) for k in ("ordem", "obrigatorio", "valor_padrao_sub")):
                    binds["ator"] = ator_limpo
                    lote_alterado.append(binds)
                    mudou = True
                else:
                    binds["updated_at"] = velho["updated_at"]
                    binds["updated_by"] = velho["updated_by"]
                    lote_mantido.append(binds)

            cur = c.cursor()
            try:
                cur.execute(self._sql["SPRM_EXCLUIR_DO_SCRIPT"], {"script_id": sid})
                if lote_novo:
                    cur.executemany(self._sql["SPRM_INSERIR_NOVO"], lote_novo)
                if mudou:
                    cur.execute(self._sql["SCR_CARIMBAR"], {"id": sid, "ator": ator_limpo})
            finally:
                cur.close()
            # Lotes com DATE lido do banco: bind TIPO_DATE (README §7.5), cada um no seu cursor para que
            # o setinputsizes nao alcance outro comando.
            for sql, lote, tipos in (
                (self._sql["SPRM_INSERIR_ALTERADO"], lote_alterado, {"created_at": db_conn.TIPO_DATE}),
                (self._sql["SPRM_INSERIR"], lote_mantido,
                 {"created_at": db_conn.TIPO_DATE, "updated_at": db_conn.TIPO_DATE}),
            ):
                if not lote:
                    continue
                cur = c.cursor()
                try:
                    db_conn.definir_tipos_entrada(cur, **tipos)
                    cur.executemany(sql, lote)
                finally:
                    cur.close()
            self._auditar(c, auditoria, "tbsss_scripts", sid)
            return self.script_params_obter(sid, conn=c)

    # -------------------------------------------------------------------------
    # Scripts executaveis (README §4.3.A)
    # -------------------------------------------------------------------------

    def scripts_executaveis(self, usuario_ctx, conn=None):
        """Scripts que o usuario pode executar em ao menos um ambiente, numa unica consulta.

        Admin dispensa perfil_scr/perfil_amb (dimensoes 1 a 3), nunca a homologacao em ambiente ativo.
        Os demais exigem EXEC_SCRIPT no contexto; a matriz vem do banco pelo perfil_id (README §4.3.A).
        """
        usuario_ctx = usuario_ctx or {}
        is_admin = usuario_ctx.get("is_admin") in ("S", True)
        if is_admin:
            sql, binds = self._sql["EXEC_ADMIN"], None
        else:
            funcs = usuario_ctx.get("funcionalidades") or set()
            perfil_id = usuario_ctx.get("perfil_id")
            if "EXEC_SCRIPT" not in funcs or perfil_id is None:
                return []
            sql, binds = self._sql["EXEC_PERFIL"], {"perfil_id": int(perfil_id)}
        with self.contexto_leitura(conn=conn) as c:
            cur = c.cursor()
            try:
                self._executar(cur, sql, binds)
                return [self.tupla_para_dict(_COLS_SCR, r) for r in cur.fetchall()]
            finally:
                cur.close()
