# -*- coding: utf-8 -*-
"""Contrato de persistencia da pasta de entrada pela tela (CR-020b; tbsss_input_upload, tbsss_input_delivery e
tbsss_input_listing, README §10 tabelas 19 a 21).

O web grava o envio com uma entrega PENDING por agente vivo do ambiente; cada agente le as proprias entregas,
grava o arquivo na sua pasta de entrada e marca o resultado; o agente publica o retrato da pasta quando a tela
pede. O conteudo nunca entra em listagem: sai so em partes de ate 1 MiB.
"""
from sss.persistence.repo_errors import RepoError

DELIVERY_STATES = ("PENDING", "DELIVERED", "FAILED")
FAILURE_REASONS = ("EXISTS", "NAME", "SPACE", "HASH", "ERROR")
PART_MAX = 1024 * 1024
LISTING_MAX_ITEMS = 2000
AUDIT_ENTITY = "tbsss_input_upload"
ACTION_UPLOAD = "INPUT_UPLOAD"
ACTION_DELIVERY = "INPUT_DELIVERY"


class NoLiveAgent(RepoError):
    """Nenhum agente vivo atende o ambiente: o envio e recusado em vez de ficar parado na fila."""


class RepoInputs(object):
    """Interface comum ao FAKE e ao Oracle (README §2.5)."""

    # ------------------------------------------------------------------ web

    def create_upload(self, data, content, actor, ip, live_seconds):
        """Grava o envio e uma entrega PENDING por agente vivo do ambiente, com INPUT_UPLOAD na mesma transacao.

        data: environment, script_id, relative_dir (ou None), file_name, sha256 e replace_existing ('Y'/'N');
        size_bytes vem de len(content). Agente vivo: status ACTIVE, o ambiente na lista dele e heartbeat_at
        nos ultimos live_seconds (node_offline_timeout_s). Sem nenhum: NoLiveAgent, sem gravar nada.
        Retorna {id, agents: [agent_id, ...]}.
        """
        raise NotImplementedError

    def uploads(self, environment, script_id, page=1, size=20):
        """Envios da pasta (sem o conteudo), por created_at DESC, id DESC, cada um com 'deliveries':
        [{agent_id, state, reason, delivered_at}] por agent_id. Retorna {items, total, page, size}."""
        raise NotImplementedError

    def listings(self, environment, script_id):
        """Retratos da pasta, um por agente: [{agent_id, listing, file_count, truncated, listed_at,
        refresh_requested_at}] por agent_id; listing e o JSON publicado (ou None)."""
        raise NotImplementedError

    def request_listing(self, environment, script_id, actor, live_seconds):
        """Pede um retrato novo a cada agente vivo do ambiente (refresh_requested_at = agora), criando a linha
        do agente que ainda nao tem retrato. Retorna a quantidade de agentes avisados (0 = nenhum vivo)."""
        raise NotImplementedError

    # ------------------------------------------------------------------ agente

    def pending_deliveries(self, agent_id, limit=10):
        """Entregas PENDING deste agente, das mais antigas, sem o conteudo: [{id, upload_id, environment,
        script_id, script_name, relative_dir, file_name, size_bytes, sha256, replace_existing}] (o nome atual do
        script monta a pasta, como em log_paths.input_dir)."""
        raise NotImplementedError

    def read_content(self, upload_id, offset, size):
        """Parte do arquivo (bytes) a partir de offset (base 0), com 1 a 1 MiB; fim: b''. Sem conteudo
        (esvaziado pelo purge) ou envio inexistente: RepoNotFound."""
        raise NotImplementedError

    def mark_delivery(self, delivery_id, agent_id, state, reason=None):
        """PENDING -> DELIVERED ou FAILED (reason obrigatorio so em FAILED), so se a entrega for deste agente,
        com INPUT_DELIVERY (ator SYSTEM:<agent_id>) na mesma transacao. False: nao e deste agente ou ja marcada."""
        raise NotImplementedError

    def listings_due(self, agent_id):
        """Retratos pedidos a este agente e ainda nao atendidos (refresh_requested_at >= listed_at: DATE tem
        precisao de segundo, e um pedido no mesmo segundo do retrato nao se perde):
        [{environment, script_id, script_name}]."""
        raise NotImplementedError

    def save_listing(self, agent_id, environment, script_id, listing, file_count, truncated):
        """Publica o retrato da pasta (listing: JSON ja limitado a LISTING_MAX_ITEMS), com listed_at = agora.
        Rotina tecnica, sem auditoria."""
        raise NotImplementedError
