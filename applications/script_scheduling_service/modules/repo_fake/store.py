# -*- coding: utf-8 -*-
"""Armazem em memoria compartilhado para o backend FAKE (README §2.5).

Mantem tabelas, sequencias, relogio injetavel e locks de sincronizacao por agregado.
"""
import collections
import copy
import datetime
import threading

from repo_errors import RepoViolation
from sql_ident import ACTOR_MAX

# Limites de tbsss_audit (README §4.4, §10 tabela 16).
_ACTOR_MAX = 40
_DETAIL_MAX = 1000


class FakeDataStore(object):
    """Armazenamento central em memoria simulando as tabelas Oracle."""

    def __init__(self, relogio=None):
        self.lock_users = threading.RLock()
        self.lock_rbac = threading.RLock()
        self.lock_catalog = threading.RLock()
        self.lock_tickets = threading.RLock()
        self.lock_schedules = threading.RLock()
        self.lock_audit = threading.RLock()
        self.lock_agents = threading.RLock()

        self._clock_fn = relogio or (lambda: datetime.datetime.now().replace(microsecond=0))

        self.environments = collections.OrderedDict()
        self.profiles = collections.OrderedDict()
        self.features = collections.OrderedDict()
        self.profile_feature = collections.OrderedDict()
        self.profile_env = collections.OrderedDict()
        self.profile_script = collections.OrderedDict()
        self.scripts = collections.OrderedDict()
        self.script_env = collections.OrderedDict()
        self.users = collections.OrderedDict()
        self.parameters = collections.OrderedDict()
        self.script_param = collections.OrderedDict()
        self.schedules = collections.OrderedDict()
        self.tickets = collections.OrderedDict()
        self.ticket_answer = collections.OrderedDict()
        # Saida do ticket (tabela 18, CR-012): {id: linha}, com o zip em bytes em 'conteudo'.
        self.ticket_output = collections.OrderedDict()
        self.agents = collections.OrderedDict()
        self.audit = collections.OrderedDict()
        # Linha unica de controle (tabela 17, CR-007 D4): versao do esquema e concessao do purge.
        self.control = collections.OrderedDict()

        self.seqs = collections.defaultdict(int)
        # Simulacao do log_pump por ticket RUNNING do seed: {ticket_id: {...}} (protegido por lock_tickets).
        self.log_simulated = {}
        # Agentes "vivos" do seed: o heartbeat acompanha o relogio a cada leitura (protegido por lock_agents).
        self.agents_hb_simulated = set()

    def now(self):
        """Retorna o instante atual naive sem microssegundos conforme o relogio injetavel."""
        dt = self._clock_fn()
        if hasattr(dt, "replace"):
            return dt.replace(microsecond=0)
        return dt

    def set_clock(self, relogio):
        """Atualiza a funcao de relogio injetavel."""
        self._clock_fn = relogio

    def next_id(self, tabela):
        """Simula a obtencao de sequence.NEXTVAL do Oracle."""
        self.seqs[tabela] += 1
        return self.seqs[tabela]

    def register_internal_audit(self, ator, ip, acao, entidade, entidade_id=None, detalhe=None, id=None):
        """Grava registro de auditoria dentro do lock do agregado atual."""
        # Paridade com o Oracle (README §2.5): ator NOT NULL e limites de coluna, sem valor padrao.
        if not ator:
            raise RepoViolation("ator da auditoria e obrigatorio")
        if len(ator) > _ACTOR_MAX or (detalhe is not None and len(detalhe) > _DETAIL_MAX):
            raise RepoViolation("auditoria excede o tamanho da coluna (ORA-12899)")
        with self.lock_audit:
            aid = id if id is not None else self.next_id("tbsss_audit")
            if aid in self.audit:
                raise RepoViolation("id de auditoria ja usado", constraint="pk_tbsss_audit")
            reg = {
                "id": aid,
                "actor": ator,
                "source_ip": ip,
                "action": acao,
                "entity": entidade,
                "entity_id": entidade_id,
                "detail": detalhe,
                "created_at": self.now(),
            }
            self.audit[aid] = copy.deepcopy(reg)
            return copy.deepcopy(reg)

    def record_actor(self, auditoria=None, ator=None):
        """Ator das colunas de registro (CR-006, README §10): auditoria['ator'] ou ator=, obrigatorio.

        Chamado antes de qualquer gravacao: sem ator, nada e gravado (paridade com created_by NOT NULL).
        """
        valor = (auditoria or {}).get("actor") or ator
        if not valor:
            raise RepoViolation("ator das colunas de registro e obrigatorio")
        if len(valor) > ACTOR_MAX:
            raise RepoViolation("ator excede o tamanho da coluna (ORA-12899)")
        return valor

    def stamp_insert(self, reg, ator):
        """created_at (o informado ou SYSDATE) e created_by; updated_* nulos ate a 1a alteracao."""
        if not reg.get("created_at"):
            reg["created_at"] = self.now()
        reg["created_by"] = ator
        reg["updated_at"] = None
        reg["updated_by"] = None
        return reg

    def stamp_update(self, reg, ator):
        """updated_at = SYSDATE e updated_by em toda alteracao de negocio; created_* nunca muda."""
        reg["updated_at"] = self.now()
        reg["updated_by"] = ator
        return reg

    def check_fk(self, existe, constraint):
        """FK do Oracle emulada: referencia inexistente vira RepoViolation com o nome da FK (README §2.5)."""
        if not existe:
            raise RepoViolation("Referencia inexistente (%s)" % constraint, constraint=constraint)

    def environment_exists(self, nome):
        return any(a["name"] == nome for a in self.environments.values())

    def login_exists(self, login):
        return any(u["login"] == login for u in self.users.values())

    def reset(self):
        """Limpa todas as colecoes e sequencias em memoria."""
        with self.lock_users:
            with self.lock_rbac:
                with self.lock_catalog:
                    with self.lock_tickets:
                        with self.lock_schedules:
                            with self.lock_audit:
                                with self.lock_agents:
                                    self.environments.clear()
                                    self.profiles.clear()
                                    self.features.clear()
                                    self.profile_feature.clear()
                                    self.profile_env.clear()
                                    self.profile_script.clear()
                                    self.scripts.clear()
                                    self.script_env.clear()
                                    self.users.clear()
                                    self.parameters.clear()
                                    self.script_param.clear()
                                    self.schedules.clear()
                                    self.tickets.clear()
                                    self.ticket_answer.clear()
                                    self.ticket_output.clear()
                                    self.agents.clear()
                                    self.audit.clear()
                                    self.control.clear()
                                    self.seqs.clear()
                                    self.log_simulated.clear()
                                    self.agents_hb_simulated.clear()


LIMIT_TOTAL_PAGINATION = 10001


def paginate(itens, pagina=1, tamanho=20):
    """Pagina deterministica com total limitado a 10.001 (README §10)."""
    total_limitado = len(itens) >= LIMIT_TOTAL_PAGINATION
    total = min(len(itens), LIMIT_TOTAL_PAGINATION)
    # Valor nao numerico propaga ValueError/TypeError: o controller valida a entrada antes.
    p = 1 if pagina is None else int(pagina)
    t = 20 if tamanho is None else int(tamanho)

    if p < 1:
        p = 1
    if t < 1:
        t = 20

    inicio = (p - 1) * t
    fim = inicio + t
    fatia = itens[inicio:fim]
    return {
        "itens": copy.deepcopy(fatia),
        "total": total,
        "pagina": p,
        "tamanho": t,
        "total_limitado": total_limitado,
    }
