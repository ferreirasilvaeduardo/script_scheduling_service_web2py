# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de agendamentos (README §2.5, §7, §10)."""
import copy
import re

from repo_agendamentos import RepoAgendamentos
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao
from repo_fake.store import paginar

_TIPOS = ("UNICA", "DIARIA", "SEMANAL", "MENSAL", "CRON")
_MOTIVOS_PAUSA = ("USUARIO_INATIVO", "SEM_PERMISSAO", "SCRIPT_INATIVO", "AMBIENTE_INATIVO",
                  "PARAM_INVALIDO", "CRON_INVALIDO", "CONCLUIDO", "MANUAL")
_RE_HORA = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
_RE_DSEM = re.compile(r"^[1-7](,[1-7]){0,6}$")
_TAMANHO_NOME = 60
_COLUNAS_ALTERAVEIS = ("nome", "script_id", "ambiente", "usuario_id", "prioridade",
                       "tipo_recorrencia", "expressao_cron", "hora_execucao", "dias_semana",
                       "dia_mes", "parametros_json", "data_inicio", "data_fim",
                       "proxima_execucao", "ultima_execucao", "ultimo_ticket_id",
                       "pausa_motivo", "ativo")


def _nulo(valor):
    # O Oracle grava '' como NULL.
    return valor is None or valor == ""


def _checar_cks(r):
    """Espelha NOT NULL e as CKs de tbsss_agendamentos (README §10, tabela 12)."""
    nome = r.get("nome")
    if _nulo(nome) or len(nome) > _TAMANHO_NOME:
        # NOT NULL e tamanho da coluna nao sao constraints nomeadas (ORA-01400 / ORA-12899).
        raise RepoViolacao("nome obrigatorio com ate %d caracteres" % _TAMANHO_NOME)
    trec = r.get("tipo_recorrencia")
    if trec not in _TIPOS:
        raise RepoViolacao("tipo_recorrencia invalido", constraint="ck_tbsss_agd_trec")
    prio = r.get("prioridade")
    if isinstance(prio, bool) or not isinstance(prio, int) or not (1 <= prio <= 4):
        raise RepoViolacao("prioridade deve estar entre 1 e 4", constraint="ck_tbsss_agd_prio")
    if r.get("ativo") not in ("S", "N"):
        raise RepoViolacao("ativo deve ser 'S' ou 'N'", constraint="ck_tbsss_agd_ativo")
    dia = r.get("dia_mes")
    if not _nulo(dia) and (isinstance(dia, bool) or not isinstance(dia, int) or not (1 <= dia <= 31)):
        raise RepoViolacao("dia_mes deve estar entre 1 e 31", constraint="ck_tbsss_agd_dia")
    hora = r.get("hora_execucao")
    if not _nulo(hora) and not _RE_HORA.match(hora):
        raise RepoViolacao("hora_execucao fora do formato HH:MM", constraint="ck_tbsss_agd_hora")
    dsem = r.get("dias_semana")
    if not _nulo(dsem) and not _RE_DSEM.match(dsem):
        raise RepoViolacao("dias_semana fora do formato ISO 1-7", constraint="ck_tbsss_agd_dsem")
    if r.get("data_inicio") is None or r.get("proxima_execucao") is None:
        raise RepoViolacao("data_inicio e proxima_execucao sao obrigatorias")
    if r.get("data_fim") is not None and r["data_fim"] < r["data_inicio"]:
        raise RepoViolacao("data_fim anterior a data_inicio", constraint="ck_tbsss_agd_fim")
    if not _nulo(r.get("pausa_motivo")) and r["pausa_motivo"] not in _MOTIVOS_PAUSA:
        raise RepoViolacao("pausa_motivo invalido", constraint="ck_tbsss_agd_pausa")
    exigidos = {"DIARIA": ("hora_execucao",), "SEMANAL": ("hora_execucao", "dias_semana"),
                "MENSAL": ("hora_execucao", "dia_mes"), "CRON": ("expressao_cron",)}
    for coluna in exigidos.get(trec, ()):
        if _nulo(r.get(coluna)):
            raise RepoViolacao("%s obrigatorio para %s" % (coluna, trec), constraint="ck_tbsss_agd_campos")


class RepoAgendamentosFake(RepoAgendamentos):
    """Implementacao em memoria com semantica Oracle para agendamentos."""

    def __init__(self, store):
        self._store = store

    def listar(self, filtros=None, pagina=1, tamanho=20, escopo_ambientes=None):
        """Lista agendamentos paginados com desempate por id."""
        filtros = filtros or {}
        with self._store.lock_agendamentos:
            lista = list(self._store.agendamentos.values())

            if escopo_ambientes is not None:
                ambs_permitidos = set(escopo_ambientes)
                lista = [a for a in lista if a.get("ambiente") in ambs_permitidos]

            ativo_f = filtros.get("ativo")
            if ativo_f:
                lista = [a for a in lista if a.get("ativo") == ativo_f]

            sid_f = filtros.get("script_id")
            if sid_f is not None:
                lista = [a for a in lista if a.get("script_id") == int(sid_f)]

            amb_f = filtros.get("ambiente")
            if amb_f:
                lista = [a for a in lista if a.get("ambiente") == amb_f]

            usr_f = filtros.get("usuario_id")
            if usr_f is not None:
                lista = [a for a in lista if a.get("usuario_id") == int(usr_f)]

            nome_f = filtros.get("nome")
            if nome_f:
                lista = [a for a in lista if nome_f.lower() in a.get("nome", "").lower()]

            lista.sort(key=lambda x: (x.get("proxima_execucao") or self._store.agora(), x["id"]))
            return paginar(lista, pagina=pagina, tamanho=tamanho)

    def obter(self, id):
        """Retorna dict com dados do agendamento pelo ID ou lanca RepoNaoEncontrado."""
        with self._store.lock_agendamentos:
            if id not in self._store.agendamentos:
                raise RepoNaoEncontrado("Agendamento ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.agendamentos[id])

    def _auditar(self, auditoria, id, acao_padrao=None, detalhe_padrao=None):
        if auditoria:
            self._store.registrar_auditoria_interno(
                ator=auditoria.get("ator"),
                ip=auditoria.get("ip"),
                acao=auditoria["acao"],
                entidade="tbsss_agendamentos",
                entidade_id=id,
                detalhe=auditoria.get("detalhe"),
            )
        elif acao_padrao:
            self._store.registrar_auditoria_interno(
                ator="SYSTEM", ip=None, acao=acao_padrao, entidade="tbsss_agendamentos",
                entidade_id=id, detalhe=detalhe_padrao,
            )

    def _checar_fks(self, reg):
        self._store.checar_fk(reg["script_id"] in self._store.scripts, "fk_tbsss_agd_scr")
        self._store.checar_fk(reg["usuario_id"] in self._store.usuarios, "fk_tbsss_agd_usr")
        self._store.checar_fk(self._store.ambiente_existe(reg["ambiente"]), "fk_tbsss_agd_amb")

    def _conferir_esperado(self, id, atual, esperado):
        for campo, valor in (esperado or {}).items():
            if atual.get(campo) != valor:
                raise RepoConflito("Agendamento ID %s alterado por outra operacao (%s)" % (id, campo))

    def inserir(self, dados, auditoria=None):
        """Insere novo agendamento com as CKs da tabela e auditoria na mesma operacao."""
        with self._store.lock_agendamentos:
            agora = self._store.agora()
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
                "created_at": dados.get("created_at") or agora,
            }
            _checar_cks(novo)
            self._checar_fks(novo)
            aid = self._store.proximo_id("tbsss_agendamentos")
            novo["id"] = aid
            self._store.agendamentos[aid] = copy.deepcopy(novo)
            self._auditar(auditoria, aid)
            return copy.deepcopy(novo)

    def alterar(self, id, dados, esperado=None, auditoria=None):
        """Altera agendamento (usuario_id do editor, README §10), condicional a 'esperado'."""
        with self._store.lock_agendamentos:
            if id not in self._store.agendamentos:
                raise RepoNaoEncontrado("Agendamento ID %s nao encontrado" % id)

            atual = self._store.agendamentos[id]
            self._conferir_esperado(id, atual, esperado)
            resultado = dict(atual)
            for k in _COLUNAS_ALTERAVEIS:
                if k in dados:
                    resultado[k] = dados[k]
            # Validacao completa antes de aplicar: um UPDATE rejeitado nao altera nenhuma coluna.
            _checar_cks(resultado)
            self._checar_fks(resultado)
            atual.update(resultado)
            self._auditar(auditoria, id)
            return copy.deepcopy(atual)

    def pausar(self, id, motivo, antiga_data=None, auditoria=None):
        """Pausa agendamento de forma otimista, validando antiga_data se informada."""
        with self._store.lock_agendamentos:
            if id not in self._store.agendamentos:
                raise RepoNaoEncontrado("Agendamento ID %s nao encontrado" % id)
            if motivo not in _MOTIVOS_PAUSA:
                raise RepoViolacao("pausa_motivo invalido", constraint="ck_tbsss_agd_pausa")

            a = self._store.agendamentos[id]
            if antiga_data is not None:
                prox = a.get("proxima_execucao")
                if prox != antiga_data:
                    raise RepoConflito(
                        "Conflito otimista no agendamento %s: proxima_execucao divergiu (%s != %s)"
                        % (id, prox, antiga_data)
                    )

            a["ativo"] = "N"
            a["pausa_motivo"] = motivo
            self._auditar(auditoria, id, "AGD_PAUSAR", "Agendamento pausado: motivo=%s" % motivo)
            return copy.deepcopy(a)

    def retomar(self, id, nova_data, esperado=None, auditoria=None):
        """Retoma agendamento pausado, limpando pausa_motivo e definindo proxima_execucao."""
        with self._store.lock_agendamentos:
            if id not in self._store.agendamentos:
                raise RepoNaoEncontrado("Agendamento ID %s nao encontrado" % id)

            a = self._store.agendamentos[id]
            self._conferir_esperado(id, a, esperado)
            if nova_data is None:
                raise RepoViolacao("proxima_execucao e obrigatoria")
            a["ativo"] = "S"
            a["pausa_motivo"] = None
            a["proxima_execucao"] = nova_data
            self._auditar(auditoria, id, "CAD_ALTERAR",
                          "Agendamento retomado com proxima_execucao=%s" % nova_data)
            return copy.deepcopy(a)

    def ticket_status(self, ticket_id):
        """Retorna o status atual do ticket pelo ID ou None se inexistente."""
        if ticket_id is None:
            return None
        with self._store.lock_tickets:
            t = self._store.tickets.get(ticket_id)
            if t:
                return t.get("status")
            return None
