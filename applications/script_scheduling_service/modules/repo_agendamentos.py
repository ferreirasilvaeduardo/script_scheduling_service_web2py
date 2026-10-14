# -*- coding: utf-8 -*-
"""Contrato de persistencia para regras de agendamento (tbsss_agendamentos)."""


class RepoAgendamentos(object):
    """Contrato abstrato para gestao de agendamentos e regras de recorrencia."""

    def listar(self, filtros=None, pagina=1, tamanho=20, escopo_ambientes=None):
        """Lista agendamentos paginados com formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}."""
        raise NotImplementedError

    def obter(self, id):
        """Retorna dict com dados do agendamento ou lanca RepoNaoEncontrado."""
        raise NotImplementedError

    def inserir(self, dados):
        """Insere novo agendamento e retorna dict com o registro criado."""
        raise NotImplementedError

    def alterar(self, id, dados):
        """Atualiza agendamento (com usuario_id do editor) e retorna dict atualizado."""
        raise NotImplementedError

    def pausar(self, id, motivo, antiga_data=None):
        """Pausa o agendamento de forma otimista, checando antiga_data se informada."""
        raise NotImplementedError

    def retomar(self, id, nova_data):
        """Retoma agendamento pausado, limpando pausa_motivo e definindo proxima_execucao."""
        raise NotImplementedError

    def ticket_status(self, ticket_id):
        """Retorna o status atual do ticket ou None se inexistente (README §7.5 passo 4)."""
        raise NotImplementedError
