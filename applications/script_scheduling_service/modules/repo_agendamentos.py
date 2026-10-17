# -*- coding: utf-8 -*-
"""Contrato de persistencia para regras de agendamento (tbsss_agendamentos)."""


class RepoAgendamentos(object):
    """Contrato abstrato para gestao de agendamentos e regras de recorrencia.

    Colunas de registro (CR-006, README §10): toda gravacao de negocio exige o ator, por
    auditoria['ator'] ou pelo parametro ator=; o INSERT grava created_*, a alteracao grava updated_*.
    Sem ator, RepoViolacao sem gravar nada.
    """

    def listar(self, filtros=None, pagina=1, tamanho=20, escopo_ambientes=None):
        """Lista agendamentos paginados com formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}."""
        raise NotImplementedError

    def obter(self, id):
        """Retorna dict com dados do agendamento ou lanca RepoNaoEncontrado."""
        raise NotImplementedError

    def inserir(self, dados, auditoria=None, ator=None):
        """Insere novo agendamento e retorna dict com o registro criado.

        Aplica as CKs da tabela (README §10, tabela 12) e grava `auditoria` (dict ator, ip, acao,
        detalhe) na mesma operacao.
        """
        raise NotImplementedError

    def alterar(self, id, dados, esperado=None, auditoria=None, ator=None):
        """Atualiza agendamento (com usuario_id do editor) e retorna dict atualizado.

        UPDATE condicional aos valores lidos em `esperado` (RepoConflito se divergirem), CKs
        aplicadas ao registro resultante e `auditoria` gravada na mesma operacao.
        """
        raise NotImplementedError

    def pausar(self, id, motivo, antiga_data=None, auditoria=None, ator=None):
        """Pausa o agendamento de forma otimista, checando antiga_data se informada (README §7.5 passo 7).

        Audita AGD_PAUSAR na mesma operacao: com `auditoria` (ator e ip da UI) ou, sem ela, como SYSTEM.
        """
        raise NotImplementedError

    def retomar(self, id, nova_data, esperado=None, auditoria=None, ator=None):
        """Retoma agendamento pausado: ativo = 'S', pausa_motivo nulo e proxima_execucao = nova_data.

        UPDATE condicional aos valores lidos em `esperado` (RepoConflito se divergirem) e `auditoria`
        gravada na mesma operacao.
        """
        raise NotImplementedError

    def ticket_status(self, ticket_id):
        """Retorna o status atual do ticket ou None se inexistente (README §7.5 passo 4)."""
        raise NotImplementedError
