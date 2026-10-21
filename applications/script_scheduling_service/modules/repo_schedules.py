# -*- coding: utf-8 -*-
"""Contrato de persistencia para regras de agendamento (tbsss_schedules)."""


class RepoSchedules(object):
    """Contrato abstrato para gestao de agendamentos e regras de recorrencia.

    Colunas de registro (CR-006, README §10): toda gravacao de negocio exige o actor, por
    auditoria['actor'] ou pelo parametro actor=; o INSERT grava created_*, a alteracao grava updated_*.
    Sem actor, RepoViolation sem gravar nada.
    """

    def list(self, filtros=None, pagina=1, tamanho=20, escopo_ambientes=None):
        """Lista agendamentos paginados com formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}.

        Ordem: proxima_execucao ASC, id ASC. Os itens trazem parametros_json (excecao documentada no
        README §2.5: o service avalia cada regra com ele); nenhuma listagem traz log_output.
        """
        raise NotImplementedError

    def get(self, id):
        """Retorna dict com dados do agendamento ou lanca RepoNotFound."""
        raise NotImplementedError

    def insert(self, dados, auditoria=None, ator=None):
        """Insere novo agendamento e retorna dict com o registro criado.

        Aplica as CKs da tabela (README §10, tabela 12) e grava `auditoria` (dict ator, ip, acao,
        detalhe) na mesma operacao.
        """
        raise NotImplementedError

    def update(self, id, dados, esperado=None, auditoria=None, ator=None):
        """Atualiza agendamento (com user_id do editor) e retorna dict atualizado.

        UPDATE condicional aos valores lidos em `esperado` (RepoConflict se divergirem), CKs
        aplicadas ao registro resultante e `auditoria` gravada na mesma operacao.
        """
        raise NotImplementedError

    def pause(self, id, motivo, antiga_data=None, auditoria=None, ator=None):
        """Pausa o agendamento de forma otimista, checando antiga_data se informada (README §7.5 passo 7).

        Audita SCHEDULE_PAUSE na mesma operacao: com `auditoria` (ator e ip da UI) ou, sem ela, como SYSTEM.
        """
        raise NotImplementedError

    def resume(self, id, nova_data, esperado=None, auditoria=None, ator=None):
        """Retoma agendamento pausado: active = 'Y', pause_reason nulo e next_run_at = nova_data.

        UPDATE condicional aos valores lidos em `esperado` (RepoConflict se divergirem) e `auditoria`
        gravada na mesma operacao.
        """
        raise NotImplementedError

    def ticket_status(self, ticket_id):
        """Retorna o status atual do ticket ou None se inexistente (README §7.5 passo 4)."""
        raise NotImplementedError
