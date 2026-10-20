# -*- coding: utf-8 -*-
"""Implementacao Oracle 11gR2 do repositorio de tickets (F7.3, agregado TICKETS; AGENTS §4).

tbsss_tickets e tbsss_ticket_resp com a mesma semantica do repo_fake/tickets.py (README §2.5):
- SQL estatico com binds; os modelos ficam nas constantes abaixo e recebem, uma vez por instancia,
  somente identificadores qualificados por sql_ident (owner e prefixo validados);
- listagens e leituras do CR-004 nunca selecionam CLOB; obter traz parametros_enviados, nunca
  log_output, que so sai em fatias por log_ler (locator, offset base 0 na API e base 1 no LOB);
- cancelamento com os dois UPDATEs literais do README §5.6 e o residuo PENDING com cancel_requested
  = 'S' (CR-008, R-02), travando so a linha do proprio ticket (nao altera a ordem de locks do §8.3);
- binds de DATE declarados como TIPO_DATE (README §7.5) e "agora" pelo SYSDATE do banco.
"""
import db_conn
import repo_errors
from repo_oracle.base import BaseRepoOracle, gravar_auditoria, validar_ator_registro
from repo_tickets import RepoTickets

_LIMITE_TOTAL = 10001
_LOTE_IN = 500
_LOG_MAX_CHARS = 65536
_STATUS = ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED")
_TERMINAIS = ("SUCCESS", "FAILED", "CANCELLED")

# Colunas sem CLOB (listagens); obter acrescenta parametros_enviados.
_COLS_TCK = ("id", "script_id", "ambiente", "solicitante", "ip_origem", "agente_id", "process_id",
             "process_start", "status", "prioridade", "cancel_requested", "status_motivo",
             "parent_ticket_id", "agendamento_id", "log_offset_chars", "log_truncado", "return_code",
             "scheduled_at", "started_at", "heartbeat_at", "finished_at",
             "created_at", "created_by", "updated_at", "updated_by")
_COLS_RESP = ("id", "ticket_id", "parametro_id", "valor_resposta",
              "created_at", "created_by", "updated_at", "updated_by")
_COLS_ULTIMA = ("id", "script_id", "status", "status_motivo", "created_at", "finished_at")
_COLS_HIST = ("id", "status", "status_motivo", "created_at", "started_at", "finished_at")
_DATAS_TCK = ("scheduled_at", "started_at", "heartbeat_at", "finished_at")


def _lista(cols, alias=""):
    return ", ".join(alias + c for c in cols)


# -----------------------------------------------------------------------------
# SQL estatico. {tck}, {resp}, {scr}, {amb}, {usr} e {prm} recebem apenas nomes qualificados por
# sql_ident (validados); todo valor entra por bind.
# -----------------------------------------------------------------------------

_SQL_OBTER = (
    "SELECT " + _lista(_COLS_TCK) + ", parametros_enviados FROM {tck} WHERE id = :id"
)
_SQL_LISTAR = (
    "SELECT " + _lista(_COLS_TCK) + " FROM {tck}{where} ORDER BY created_at DESC, id DESC"
)
_SQL_CONTAR = "SELECT COUNT(*) FROM (SELECT id FROM {tck} WHERE {where_count})"
_SQL_ULTIMAS = (
    "SELECT " + _lista(_COLS_ULTIMA) + " FROM ("
    "SELECT " + _lista(_COLS_ULTIMA, "t.") + ", "
    "ROW_NUMBER() OVER (PARTITION BY t.script_id ORDER BY t.created_at DESC, t.id DESC) rn "
    "FROM {tck} t WHERE t.script_id IN ({ids}){escopo}"
    ") WHERE rn = 1"
)
_SQL_HISTORICO = (
    "SELECT " + _lista(_COLS_HIST) + " FROM {tck} t "
    "WHERE t.script_id = :script_id AND t.created_at >= :desde{escopo} "
    "ORDER BY t.created_at DESC, t.id DESC"
)
_SQL_RESPOSTAS = (
    "SELECT " + _lista(_COLS_RESP) + " FROM {resp} WHERE ticket_id = :ticket_id ORDER BY id"
)
_SQL_SCR_EXISTE = "SELECT id FROM {scr} WHERE id = :id"
_SQL_AMB_EXISTE = "SELECT id FROM {amb} WHERE nome = :nome"
_SQL_USR_EXISTE = "SELECT id FROM {usr} WHERE login = :login"
_SQL_PRM_EXISTE = "SELECT id FROM {prm} WHERE id = :id"
_SQL_TCK_EXISTE = "SELECT id FROM {tck} WHERE id = :id"
_SQL_INSERIR = (
    "INSERT INTO {tck} (id, script_id, ambiente, solicitante, ip_origem, agente_id, process_id, "
    "process_start, status, prioridade, cancel_requested, status_motivo, parent_ticket_id, agendamento_id, "
    "parametros_enviados, log_output, log_truncado, return_code, scheduled_at, started_at, "
    "heartbeat_at, finished_at, created_at, created_by, updated_at, updated_by) "
    "VALUES (:id, :script_id, :ambiente, :solicitante, :ip_origem, :agente_id, :process_id, "
    ":process_start, :status, :prioridade, :cancel_requested, :status_motivo, :parent_ticket_id, "
    ":agendamento_id, :parametros_enviados, :log_output, :log_truncado, :return_code, "
    "NVL(:scheduled_at, SYSDATE), :started_at, :heartbeat_at, :finished_at, SYSDATE, :ator, NULL, NULL)"
)
_SQL_INSERIR_RESP = (
    "INSERT INTO {resp} (id, ticket_id, parametro_id, valor_resposta, created_at, created_by, "
    "updated_at, updated_by) VALUES (:id, :ticket_id, :parametro_id, :valor_resposta, SYSDATE, :ator, NULL, NULL)"
)
# README §5.6, literais (no do web, uma transacao).
_SQL_CANCEL_SINALIZAR = (
    "UPDATE {tck} SET cancel_requested = 'S', updated_at = SYSDATE, updated_by = :ator "
    "WHERE id = :id AND status IN ('PENDING', 'RUNNING') AND cancel_requested = 'N'"
)
_SQL_CANCEL_PENDENTE = (
    "UPDATE {tck} SET status = 'CANCELLED', status_motivo = 'CANCEL_USER', return_code = -1, "
    "finished_at = SYSDATE, updated_at = SYSDATE, updated_by = :ator "
    "WHERE id = :id AND status = 'PENDING'"
)
_SQL_CANCEL_LER = "SELECT status, cancel_requested FROM {tck} WHERE id = :id FOR UPDATE WAIT 5"
_SQL_LOG = "SELECT status, log_truncado, log_output FROM {tck} WHERE id = :id"


def _ler_lob(valor):
    """CLOB lido pelo driver (locator) ou ja como texto."""
    if valor is None:
        return None
    if hasattr(valor, "read"):
        return valor.read()
    return valor


class RepoTicketsOracle(BaseRepoOracle, RepoTickets):
    """Repositorio de tickets com SQL Oracle 11gR2."""

    def __init__(self, cfg=None, segredos=None):
        super(RepoTicketsOracle, self).__init__(cfg=cfg, segredos=segredos)
        self._idents = {
            "tck": self.qualificar_tabela("tickets"),
            "resp": self.qualificar_tabela("ticket_resp"),
            "scr": self.qualificar_tabela("scripts"),
            "amb": self.qualificar_tabela("ambientes"),
            "usr": self.qualificar_tabela("usuarios"),
            "prm": self.qualificar_tabela("parametros"),
        }
        self._sql = {}
        for nome, modelo in globals().items():
            if nome.startswith("_SQL_") and "{where" not in modelo and "{ids}" not in modelo \
                    and "{escopo}" not in modelo:
                self._sql[nome[5:]] = modelo.format(**self._idents)
        self._tbl_aud = self.qualificar_tabela("auditoria")
        self._seq_aud = self.qualificar_sequence("auditoria")
        self._seq_tck = self.qualificar_sequence("tickets")
        self._seq_resp = self.qualificar_sequence("ticket_resp")

    # -------------------------------------------------------------------------
    # Utilitarios
    # -------------------------------------------------------------------------

    def _sql_dinamico(self, modelo, **partes):
        """Completa um modelo com identificadores e clausulas fixas (allowlist) montadas pelo codigo."""
        valores = dict(self._idents)
        valores.update(partes)
        return modelo.format(**valores)

    def _existe(self, conn, sql, binds):
        cur = conn.cursor()
        try:
            cur.execute(sql, binds)
            return cur.fetchone() is not None
        finally:
            cur.close()

    def _fk(self, existe, sufixo, entidade="tickets"):
        if not existe:
            constraint = self.nome_constraint("fk", entidade, sufixo)
            raise repo_errors.RepoViolacao("Referencia inexistente (%s)" % constraint, constraint=constraint)

    @staticmethod
    def _marcas(prefixo, valores, binds):
        """Placeholders :<prefixo>0..N por contagem controlada; os valores vao so como binds."""
        marcas = []
        for n, v in enumerate(valores):
            nome = "%s%d" % (prefixo, n)
            binds[nome] = v
            marcas.append(":" + nome)
        return ", ".join(marcas)

    def _escopo(self, alias, escopo_ambientes, solicitante, binds):
        """Clausulas de escopo (ambientes autorizados e solicitante), iguais as do listar."""
        clausulas = []
        if escopo_ambientes is not None:
            ambs = sorted(set(escopo_ambientes))
            if not ambs:
                clausulas.append("1 = 0")
            else:
                clausulas.append(alias + "ambiente IN (" + self._marcas("e", ambs, binds) + ")")
        if solicitante is not None:
            clausulas.append(alias + "solicitante = :solicitante")
            binds["solicitante"] = solicitante
        return clausulas

    # -------------------------------------------------------------------------
    # Leituras
    # -------------------------------------------------------------------------

    def agora(self):
        """Instante corrente do banco (SYSDATE), sem microssegundos."""
        with self.contexto_leitura() as conn:
            return db_conn.agora_banco(conn)

    def obter(self, id, conn=None):
        """Ticket pela PK, com parametros_enviados e sem log_output (que sai por log_ler)."""
        with self.contexto_leitura(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["OBTER"], {"id": int(id)})
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNaoEncontrado("Ticket ID %s nao encontrado" % id)
                reg = self.tupla_para_dict(_COLS_TCK, row[:len(_COLS_TCK)])
                reg["parametros_enviados"] = _ler_lob(row[len(_COLS_TCK)])
                return reg
            finally:
                cur.close()

    def listar(self, filtros=None, pagina=1, tamanho=20, escopo_ambientes=None, conn=None):
        """Lista tickets por created_at DESC, id DESC, sem CLOB, com total limitado a 10.001."""
        filtros = filtros or {}
        clausulas, binds, datas = [], {}, {}
        clausulas.extend(self._escopo("", escopo_ambientes, None, binds))

        stat_f = filtros.get("status")
        if stat_f:
            valores = sorted(set(stat_f)) if isinstance(stat_f, (list, tuple, set, frozenset)) else [stat_f]
            clausulas.append("status IN (" + self._marcas("s", valores, binds) + ")")
        if filtros.get("ambiente"):
            clausulas.append("ambiente = :ambiente_f")
            binds["ambiente_f"] = filtros["ambiente"]
        if filtros.get("script_id") is not None:
            clausulas.append("script_id = :script_id_f")
            binds["script_id_f"] = int(filtros["script_id"])
        if filtros.get("solicitante"):
            clausulas.append("solicitante = :solicitante_f")
            binds["solicitante_f"] = filtros["solicitante"]
        if filtros.get("parent_ticket_id") is not None:
            clausulas.append("parent_ticket_id = :parent_f")
            binds["parent_f"] = int(filtros["parent_ticket_id"])
        origem = filtros.get("origem")
        if origem == "manual":
            clausulas.append("agendamento_id IS NULL")
        elif origem == "agendamento":
            clausulas.append("agendamento_id IS NOT NULL")
        # Periodo sempre por intervalo, sem TRUNC (AGENTS §4.12); binds DATE (README §7.5).
        if filtros.get("criado_inicio"):
            clausulas.append("created_at >= :criado_inicio")
            binds["criado_inicio"] = filtros["criado_inicio"]
            datas["criado_inicio"] = db_conn.TIPO_DATE
        if filtros.get("criado_fim"):
            clausulas.append("created_at < :criado_fim")
            binds["criado_fim"] = filtros["criado_fim"]
            datas["criado_fim"] = db_conn.TIPO_DATE

        p = 1 if pagina is None else int(pagina)
        t = 20 if tamanho is None else int(tamanho)
        if p < 1:
            p = 1
        if t < 1:
            t = 20
        inicio = (p - 1) * t
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        where_count = " AND ".join(clausulas + ["ROWNUM <= " + str(_LIMITE_TOTAL)])
        sql_conta = self._sql_dinamico(_SQL_CONTAR, where_count=where_count)
        sql_pag = (
            "SELECT * FROM (SELECT a.*, ROWNUM rn FROM (" + self._sql_dinamico(_SQL_LISTAR, where=where) + ") a "
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
                itens = [self.tupla_para_dict(_COLS_TCK, r[:len(_COLS_TCK)]) for r in cur.fetchall()]
            finally:
                cur.close()
        return {
            "itens": itens,
            "total": min(bruto, _LIMITE_TOTAL),
            "pagina": p,
            "tamanho": t,
            "total_limitado": bruto >= _LIMITE_TOTAL,
        }

    def ultimas_execucoes(self, script_ids, escopo_ambientes=None, solicitante=None, conn=None):
        """Ticket mais recente de cada script no escopo, numa consulta por lote (ROW_NUMBER, sem LOB)."""
        ids = sorted(set(int(i) for i in script_ids))
        resultado = {}
        if not ids:
            return resultado
        with self.contexto_leitura(conn=conn) as c:
            for i in range(0, len(ids), _LOTE_IN):
                binds = {}
                marcas = self._marcas("s", ids[i:i + _LOTE_IN], binds)
                escopo = self._escopo("t.", escopo_ambientes, solicitante, binds)
                sql = self._sql_dinamico(_SQL_ULTIMAS, ids=marcas,
                                         escopo="".join(" AND " + x for x in escopo))
                cur = c.cursor()
                try:
                    cur.execute(sql, binds)
                    for r in cur.fetchall():
                        reg = self.tupla_para_dict(_COLS_ULTIMA, r)
                        sid = reg.pop("script_id")
                        resultado[sid] = reg
                finally:
                    cur.close()
        return resultado

    def historico_script(self, script_id, desde, escopo_ambientes=None, solicitante=None, limite=5000,
                         conn=None):
        """Tickets do script desde a data, no escopo, sem LOB: os `limite` mais recentes, em ordem crescente."""
        binds = {"script_id": int(script_id), "desde": desde}
        escopo = self._escopo("t.", escopo_ambientes, solicitante, binds)
        sql = self._sql_dinamico(_SQL_HISTORICO, escopo="".join(" AND " + x for x in escopo))
        if limite:
            sql = "SELECT " + _lista(_COLS_HIST) + " FROM (" + sql + ") WHERE ROWNUM <= :limite"
            binds["limite"] = int(limite)
        with self.contexto_leitura(conn=conn) as c:
            cur = c.cursor()
            try:
                db_conn.definir_tipos_entrada(cur, desde=db_conn.TIPO_DATE)
                cur.execute(sql, binds)
                linhas = [self.tupla_para_dict(_COLS_HIST, r) for r in cur.fetchall()]
            finally:
                cur.close()
        linhas.reverse()
        return linhas

    def respostas(self, ticket_id, conn=None):
        """Respostas resolvidas do ticket, por id."""
        with self.contexto_leitura(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["RESPOSTAS"], {"ticket_id": int(ticket_id)})
                return [self.tupla_para_dict(_COLS_RESP, r) for r in cur.fetchall()]
            finally:
                cur.close()

    def log_ler(self, id, offset, max_chars, conn=None):
        """Fatia do log por locator: offset base 0 na API, offset + 1 no LOB, ate 65.536 caracteres."""
        with self.contexto_leitura(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["LOG"], {"id": int(id)})
                row = cur.fetchone()
                if not row:
                    raise repo_errors.RepoNaoEncontrado("Ticket ID %s nao encontrado" % id)
                status, log_truncado, lob = row
                # Valor nao numerico propaga ValueError/TypeError, como no FAKE.
                off = int(offset)
                if off < 0:
                    off = 0
                mc = int(max_chars)
                if mc < 1:
                    mc = _LOG_MAX_CHARS
                texto = ""
                if lob is not None:
                    if hasattr(lob, "read"):
                        if off < lob.size():
                            texto = lob.read(off + 1, mc) or ""
                    else:
                        texto = lob[off:off + mc]
            finally:
                cur.close()
        return (texto, off + len(texto), (status or "").strip() in _TERMINAIS, (log_truncado or "").strip() == "S")

    # -------------------------------------------------------------------------
    # Gravacoes
    # -------------------------------------------------------------------------

    def criar(self, ticket, respostas, ator=None, conn=None):
        """Ticket, respostas e auditoria numa transacao, sem gravacao parcial; retorna o ID criado."""
        script_id = int(ticket.get("script_id", 0))
        ambiente = ticket.get("ambiente")
        solicitante = ticket.get("solicitante")
        ator_limpo = validar_ator_registro(ator=ator or solicitante)
        if not script_id:
            raise repo_errors.RepoViolacao("script_id e obrigatorio")
        if not ambiente:
            raise repo_errors.RepoViolacao("ambiente e obrigatorio")
        if not solicitante:
            raise repo_errors.RepoViolacao("solicitante e obrigatorio")
        prio = int(ticket.get("prioridade", 2))
        if not (1 <= prio <= 4):
            raise repo_errors.RepoViolacao("prioridade deve estar entre 1 e 4",
                                           constraint=self.nome_constraint("ck", "tickets", "prio"))
        status = ticket.get("status", "PENDING")
        if status not in _STATUS:
            raise repo_errors.RepoViolacao("Status invalido", constraint=self.nome_constraint("ck", "tickets", "stat"))
        parent_id = ticket.get("parent_ticket_id")
        agd_id = ticket.get("agendamento_id")

        with self.transacao_escrita(conn=conn) as c:
            # FKs e UK conferidas antes de gravar qualquer linha, na ordem do FAKE (README §2.5).
            if parent_id is not None:
                self._fk(self._existe(c, self._sql["TCK_EXISTE"], {"id": int(parent_id)}), "parent")
            self._fk(self._existe(c, self._sql["SCR_EXISTE"], {"id": script_id}), "scr")
            self._fk(self._existe(c, self._sql["AMB_EXISTE"], {"nome": ambiente}), "amb")
            self._fk(self._existe(c, self._sql["USR_EXISTE"], {"login": solicitante}), "usr")
            vistos = set()
            for resp in (respostas or []):
                pid = int(resp["parametro_id"])
                self._fk(self._existe(c, self._sql["PRM_EXISTE"], {"id": pid}), "prm", entidade="ticket_resp")
                if pid in vistos:
                    raise repo_errors.RepoViolacao(
                        "resposta repetida para o parametro %s" % pid,
                        constraint=self.nome_constraint("uk", "ticket_resp", "tck_prm"))
                vistos.add(pid)

            tid = db_conn.proximo_id(c, self._seq_tck)
            binds = {
                "id": tid, "script_id": script_id, "ambiente": ambiente, "solicitante": solicitante,
                "ip_origem": ticket.get("ip_origem"), "agente_id": ticket.get("agente_id"),
                "process_id": ticket.get("process_id"), "process_start": ticket.get("process_start"),
                "status": status, "prioridade": prio, "cancel_requested": ticket.get("cancel_requested", "N"),
                "status_motivo": ticket.get("status_motivo"),
                "parent_ticket_id": int(parent_id) if parent_id is not None else None,
                "agendamento_id": int(agd_id) if agd_id is not None else None,
                "parametros_enviados": ticket.get("parametros_enviados", "{}"),
                "log_output": ticket.get("log_output") or None,
                "log_truncado": ticket.get("log_truncado", "N"), "return_code": ticket.get("return_code"),
                "ator": ator_limpo,
            }
            for campo in _DATAS_TCK:
                binds[campo] = ticket.get(campo)
            tipos = dict((campo, db_conn.TIPO_DATE) for campo in _DATAS_TCK)
            tipos.update(parametros_enviados=db_conn.TIPO_CLOB, log_output=db_conn.TIPO_CLOB)
            cur = c.cursor()
            try:
                db_conn.definir_tipos_entrada(cur, **tipos)
                # Ocorrencia repetida do agendamento: ORA-00001 em ix_<prefixo>tck_ocor (RepoViolacao).
                cur.execute(self._sql["INSERIR"], binds)
            finally:
                cur.close()

            lote = []
            for resp in (respostas or []):
                lote.append({"id": db_conn.proximo_id(c, self._seq_resp), "ticket_id": tid,
                             "parametro_id": int(resp["parametro_id"]),
                             "valor_resposta": resp.get("valor_resposta"), "ator": ator_limpo})
            if lote:
                cur = c.cursor()
                try:
                    cur.executemany(self._sql["INSERIR_RESP"], lote)
                finally:
                    cur.close()

            if parent_id is None:
                acao, detalhe = "TICKET_CRIAR", "Ticket criado para script %s em %s" % (script_id, ambiente)
            else:
                acao = "TICKET_REEXECUTAR"
                detalhe = "Reexecucao do ticket %s para script %s em %s" % (parent_id, script_id, ambiente)
            gravar_auditoria(c, self._tbl_aud, self._seq_aud,
                             {"ator": solicitante, "ip": ticket.get("ip_origem"), "acao": acao, "detalhe": detalhe},
                             "tbsss_tickets", tid)
            return tid

    def solicitar_cancelamento(self, id, ator, ip, conn=None):
        """Os dois UPDATEs do README §5.6 e a auditoria TICKET_CANCELAR numa transacao."""
        ator_limpo = validar_ator_registro(ator=ator)
        tid = int(id)
        with self.transacao_escrita(conn=conn) as c:
            cur = c.cursor()
            try:
                cur.execute(self._sql["CANCEL_SINALIZAR"], {"id": tid, "ator": ator_limpo})
                sinalizou = cur.rowcount == 1
                if sinalizou:
                    cur.execute(self._sql["CANCEL_PENDENTE"], {"id": tid, "ator": ator_limpo})
                    retorno = "CANCELADO" if cur.rowcount == 1 else "SINALIZADO"
                else:
                    # Terminal, ja sinalizado ou PENDING residual com 'S' (CR-008, R-02): so a propria linha.
                    cur.execute(self._sql["CANCEL_LER"], {"id": tid})
                    row = cur.fetchone()
                    if not row:
                        raise repo_errors.RepoNaoEncontrado("Ticket ID %s nao encontrado" % id)
                    status, pedido = (row[0] or "").strip(), (row[1] or "").strip()
                    if status == "PENDING":
                        cur.execute(self._sql["CANCEL_PENDENTE"], {"id": tid, "ator": ator_limpo})
                        if cur.rowcount != 1:
                            raise repo_errors.RepoConflito("Ticket ID %s alterado por outra operacao" % id)
                        retorno = "CANCELADO"
                    elif status == "RUNNING" and pedido == "S":
                        retorno = "JA_SINALIZADO"
                    else:
                        retorno = "TERMINAL"
            finally:
                cur.close()
            resultado = {
                "CANCELADO": u"cancelado", "SINALIZADO": u"sinalizado",
                "JA_SINALIZADO": u"já sinalizado", "TERMINAL": u"sem efeito: ticket encerrado",
            }[retorno]
            gravar_auditoria(c, self._tbl_aud, self._seq_aud,
                             {"ator": ator_limpo, "ip": ip, "acao": "TICKET_CANCELAR",
                              "detalhe": u"resultado: %s" % resultado},
                             "tbsss_tickets", tid)
            return retorno
