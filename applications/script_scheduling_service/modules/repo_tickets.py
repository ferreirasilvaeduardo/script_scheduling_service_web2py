# -*- coding: utf-8 -*-
"""Contrato de persistencia para tickets e execucoes (tbsss_tickets, tbsss_ticket_resp)."""


class RepoTickets(object):
    """Contrato abstrato para gestao do ciclo de vida e logs dos tickets."""

    def agora(self):
        """Instante corrente do banco (SYSDATE), sem microssegundos, para regras de negocio."""
        raise NotImplementedError

    def criar(self, ticket, respostas):
        """Cria ticket e respostas vinculadas em transacao unica e retorna o ID criado.

        Audita TICKET_CRIAR, ou TICKET_REEXECUTAR quando ticket['parent_ticket_id'] e informado.
        """
        raise NotImplementedError

    def obter(self, id):
        """Retorna dict com dados do ticket pelo ID ou lanca RepoNaoEncontrado."""
        raise NotImplementedError

    def listar(self, filtros=None, pagina=1, tamanho=20, escopo_ambientes=None):
        """Lista tickets com paginacao e formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}.

        Ordem: created_at DESC, id DESC. Chaves de filtros (todas opcionais, combinadas com E):
        status (lista), ambiente, script_id, solicitante (igualdade exata), origem
        ('manual' | 'agendamento'), criado_inicio (created_at >= valor), criado_fim
        (created_at < valor, extremo aberto) e parent_ticket_id. escopo_ambientes (iteravel
        de nomes) restringe o ambiente; None nao restringe.
        """
        raise NotImplementedError

    def respostas(self, ticket_id):
        """Retorna lista de dicts com as respostas resolvidas do ticket."""
        raise NotImplementedError

    def solicitar_cancelamento(self, id, ator, ip):
        """Cancelamento do no web (README §5.6) e auditoria TICKET_CANCELAR na mesma transacao.

        Retorna 'TERMINAL' | 'CANCELADO' | 'SINALIZADO' | 'JA_SINALIZADO'. Toda solicitacao grava
        TICKET_CANCELAR, inclusive as sem efeito, com detalhe 'resultado: <cancelado | sinalizado |
        ja sinalizado | sem efeito: ticket encerrado>'. Lanca RepoNaoEncontrado se nao existir.
        """
        raise NotImplementedError

    def log_ler(self, id, offset, max_chars):
        """Leitura incremental de log, retornando (texto, novo_offset, terminal, truncado)."""
        raise NotImplementedError
