# -*- coding: utf-8 -*-
"""Contrato de persistencia para tickets e execucoes (tbsss_tickets, tbsss_ticket_resp)."""


class RepoTickets(object):
    """Contrato abstrato para gestao do ciclo de vida e logs dos tickets."""

    def criar(self, ticket, respostas):
        """Cria ticket e respostas vinculadas em transacao unica e retorna o ID criado."""
        raise NotImplementedError

    def obter(self, id):
        """Retorna dict com dados do ticket pelo ID ou lanca RepoNaoEncontrado."""
        raise NotImplementedError

    def listar(self, filtros=None, pagina=1, tamanho=20, escopo_ambientes=None):
        """Lista tickets com paginacao e formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}."""
        raise NotImplementedError

    def respostas(self, ticket_id):
        """Retorna lista de dicts com as respostas resolvidas do ticket."""
        raise NotImplementedError

    def solicitar_cancelamento(self, id):
        """Executa a logica de cancelamento do no web e retorna 'TERMINAL'|'CANCELADO'|'SINALIZADO'."""
        raise NotImplementedError

    def log_ler(self, id, offset, max_chars):
        """Leitura incremental de log, retornando (texto, novo_offset, terminal, truncado)."""
        raise NotImplementedError
