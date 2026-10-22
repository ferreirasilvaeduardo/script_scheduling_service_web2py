# -*- coding: utf-8 -*-
"""Contrato de persistencia para tickets e execucoes (tbsss_tickets, tbsss_ticket_answer, tbsss_ticket_output)."""


class RepoTickets(object):
    """Contrato abstrato para gestao do ciclo de vida e logs dos tickets.

    Colunas de registro (CR-006, README §10): toda gravacao de negocio exige o actor, por
    audit['actor'] ou pelo parametro actor=; o INSERT grava created_*, a alteracao grava updated_*.
    Sem actor, RepoViolation sem gravar nada.
    """

    def now(self):
        """Instante corrente do banco (SYSDATE), sem microssegundos, para regras de negocio."""
        raise NotImplementedError

    def create(self, ticket, answers, actor=None):
        """Cria ticket e respostas vinculadas em transacao unica e retorna o ID criado.

        Audita TICKET_CREATE, ou TICKET_RERUN quando ticket['parent_ticket_id'] e informado.
        created_by do ticket e das respostas: actor= ou, sem ele, o solicitante (CR-006).
        """
        raise NotImplementedError

    def get(self, id):
        """Retorna dict com dados do ticket pelo ID ou lanca RepoNotFound.

        Traz submitted_params (snapshot) e as colunas de registro, mas nunca log_output: o log so e
        lido em fatias por log_ler (README §8.10, AGENTS §4.13).
        """
        raise NotImplementedError

    def list(self, filters=None, page=1, size=20, environment_scope=None):
        """Lista tickets com paginacao e formato {'items': [...], 'total': n, 'page': p, 'size': t}.

        Os itens nunca trazem CLOB (sem log_output e sem submitted_params; AGENTS §4.13).

        Ordem: created_at DESC, id DESC. Chaves de filtros (todas opcionais, combinadas com E):
        status (lista), environment, script_id, requested_by (igualdade exata), source
        ('manual' | 'agendamento'), created_from (created_at >= valor), created_to
        (created_at < valor, extremo aberto) e parent_ticket_id. environment_scope (iteravel
        de nomes) restringe o ambiente; None nao restringe.
        """
        raise NotImplementedError

    def last_runs(self, script_ids, environment_scope=None, requester=None):
        """Ticket mais recente (created_at DESC, id DESC) de cada script no escopo (README §5.8, CR-004).

        Retorna {script_id: {id, status, status_reason, created_at, finished_at}}; scripts sem ticket no
        escopo ficam de fora. environment_scope None nao restringe; solicitante restringe ao login.
        Nunca le log_output (Oracle: ROW_NUMBER() por script sobre ix_tbsss_tck_scr).
        """
        raise NotImplementedError

    def script_history(self, script_id, since, environment_scope=None, requester=None, limit=5000):
        """Tickets do script com created_at >= desde, no escopo, por created_at (README §5.8, CR-004).

        Devolve no maximo `limite` itens (os mais recentes), cada um so com id, status, status_reason,
        created_at, started_at e finished_at, sem LOB, ordenados por created_at crescente.
        """
        raise NotImplementedError

    def answers(self, ticket_id):
        """Retorna lista de dicts com as respostas resolvidas do ticket."""
        raise NotImplementedError

    def request_cancel(self, id, actor, ip):
        """Cancelamento do no web (README §5.6) e auditoria TICKET_CANCEL na mesma transacao.

        Retorna 'TERMINAL' | 'CANCELADO' | 'SINALIZADO' | 'JA_SINALIZADO'. Toda solicitacao grava
        TICKET_CANCEL, inclusive as sem efeito, com detalhe 'resultado: <cancelado | sinalizado |
        ja sinalizado | sem efeito: ticket encerrado>'. Lanca RepoNotFound se nao existir.
        """
        raise NotImplementedError

    def log_read(self, id, offset, max_chars):
        """Leitura incremental de log, retornando (texto, new_offset, terminal, truncado)."""
        raise NotImplementedError

    def output_get(self, ticket_id):
        """Saida do ticket (CR-012, README §8.13) sem o conteudo, ou None se nao houver.

        Dict com situacao, motivo, agent_id, file_count, size_bytes e as colunas de registro.
        """
        raise NotImplementedError

    def output_read(self, ticket_id, offset, size):
        """Fatia do zip (bytes) a partir de offset (base 0), com ate `tamanho` bytes (1 a 1 MiB).

        So para situacao DISPONIVEL; outra situacao, ou sem saida, lanca RepoNotFound. Fim do zip: b''.
        """
        raise NotImplementedError
