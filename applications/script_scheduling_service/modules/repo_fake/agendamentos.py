# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de agendamentos (README §2.5, §7, §10)."""
import copy

from repo_agendamentos import RepoAgendamentos
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao
from repo_fake.store import paginar


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

    def inserir(self, dados):
        """Insere novo agendamento com validacoes de CKs e integridade."""
        with self._store.lock_agendamentos:
            nome = dados.get("nome")
            if not nome:
                raise RepoViolacao("Nome de agendamento e obrigatorio")

            trec = dados.get("tipo_recorrencia")
            if trec not in ("UNICA", "DIARIA", "SEMANAL", "MENSAL", "CRON"):
                raise RepoViolacao("tipo_recorrencia invalido", constraint="ck_tbsss_agd_trec")

            prio = int(dados.get("prioridade", 2))
            if not (1 <= prio <= 4):
                raise RepoViolacao("prioridade deve estar entre 1 e 4", constraint="ck_tbsss_agd_prio")

            ativo = dados.get("ativo", "S")
            if ativo not in ("S", "N"):
                raise RepoViolacao("ativo deve ser 'S' ou 'N'", constraint="ck_tbsss_agd_ativo")

            aid = self._store.proximo_id("tbsss_agendamentos")
            agora = self._store.agora()
            novo = {
                "id": aid,
                "nome": nome,
                "script_id": int(dados["script_id"]),
                "ambiente": dados["ambiente"],
                "usuario_id": int(dados["usuario_id"]),
                "prioridade": prio,
                "tipo_recorrencia": trec,
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
                "ativo": ativo,
                "created_at": dados.get("created_at") or agora,
            }
            self._store.agendamentos[aid] = copy.deepcopy(novo)
            return copy.deepcopy(novo)

    def alterar(self, id, dados):
        """Altera agendamento atualizando usuario_id do editor (README §10)."""
        with self._store.lock_agendamentos:
            if id not in self._store.agendamentos:
                raise RepoNaoEncontrado("Agendamento ID %s nao encontrado" % id)

            atual = self._store.agendamentos[id]

            for k in ("nome", "script_id", "ambiente", "usuario_id", "prioridade",
                      "tipo_recorrencia", "expressao_cron", "hora_execucao", "dias_semana",
                      "dia_mes", "parametros_json", "data_inicio", "data_fim",
                      "proxima_execucao", "ultima_execucao", "ultimo_ticket_id",
                      "pausa_motivo", "ativo"):
                if k in dados:
                    atual[k] = dados[k]

            return copy.deepcopy(atual)

    def pausar(self, id, motivo, antiga_data=None):
        """Pausa agendamento de forma otimista, validando antiga_data se informada."""
        with self._store.lock_agendamentos:
            if id not in self._store.agendamentos:
                raise RepoNaoEncontrado("Agendamento ID %s nao encontrado" % id)

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

            self._store.registrar_auditoria_interno(
                ator="SYSTEM",
                ip=None,
                acao="AGD_PAUSAR",
                entidade="tbsss_agendamentos",
                entidade_id=id,
                detalhe="Agendamento pausado: motivo=%s" % motivo,
            )
            return copy.deepcopy(a)

    def retomar(self, id, nova_data):
        """Retoma agendamento pausado, limpando pausa_motivo e definindo proxima_execucao."""
        with self._store.lock_agendamentos:
            if id not in self._store.agendamentos:
                raise RepoNaoEncontrado("Agendamento ID %s nao encontrado" % id)

            a = self._store.agendamentos[id]
            a["ativo"] = "S"
            a["pausa_motivo"] = None
            a["proxima_execucao"] = nova_data

            self._store.registrar_auditoria_interno(
                ator="SYSTEM",
                ip=None,
                acao="CAD_ALTERAR",
                entidade="tbsss_agendamentos",
                entidade_id=id,
                detalhe="Agendamento retomado com proxima_execucao=%s" % nova_data,
            )
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
