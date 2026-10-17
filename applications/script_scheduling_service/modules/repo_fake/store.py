# -*- coding: utf-8 -*-
"""Armazem em memoria compartilhado para o backend FAKE (README §2.5).

Mantem tabelas, sequencias, relogio injetavel e locks de sincronizacao por agregado.
"""
import collections
import copy
import datetime
import threading

from repo_errors import RepoViolacao
from sql_ident import ATOR_MAX

# Limites de tbsss_auditoria (README §4.4, §10 tabela 16).
_ATOR_MAX = 40
_DETALHE_MAX = 1000


class FakeDataStore(object):
    """Armazenamento central em memoria simulando as tabelas Oracle."""

    def __init__(self, relogio=None):
        self.lock_usuarios = threading.RLock()
        self.lock_rbac = threading.RLock()
        self.lock_catalogo = threading.RLock()
        self.lock_tickets = threading.RLock()
        self.lock_agendamentos = threading.RLock()
        self.lock_auditoria = threading.RLock()
        self.lock_agentes = threading.RLock()

        self._relogio_fn = relogio or (lambda: datetime.datetime.now().replace(microsecond=0))

        self.ambientes = collections.OrderedDict()
        self.perfis = collections.OrderedDict()
        self.funcionalidades = collections.OrderedDict()
        self.perfil_func = collections.OrderedDict()
        self.perfil_amb = collections.OrderedDict()
        self.perfil_scr = collections.OrderedDict()
        self.scripts = collections.OrderedDict()
        self.script_amb = collections.OrderedDict()
        self.usuarios = collections.OrderedDict()
        self.parametros = collections.OrderedDict()
        self.script_param = collections.OrderedDict()
        self.agendamentos = collections.OrderedDict()
        self.tickets = collections.OrderedDict()
        self.ticket_resp = collections.OrderedDict()
        self.agentes = collections.OrderedDict()
        self.auditoria = collections.OrderedDict()
        # Linha unica de controle (tabela 17, CR-007 D4): versao do esquema e concessao do purge.
        self.controle = collections.OrderedDict()

        self.seqs = collections.defaultdict(int)
        # Simulacao do log_pump por ticket RUNNING do seed: {ticket_id: {...}} (protegido por lock_tickets).
        self.log_sim = {}
        # Agentes "vivos" do seed: o heartbeat acompanha o relogio a cada leitura (protegido por lock_agentes).
        self.agentes_hb_sim = set()

    def agora(self):
        """Retorna o instante atual naive sem microssegundos conforme o relogio injetavel."""
        dt = self._relogio_fn()
        if hasattr(dt, "replace"):
            return dt.replace(microsecond=0)
        return dt

    def definir_relogio(self, relogio):
        """Atualiza a funcao de relogio injetavel."""
        self._relogio_fn = relogio

    def proximo_id(self, tabela):
        """Simula a obtencao de sequence.NEXTVAL do Oracle."""
        self.seqs[tabela] += 1
        return self.seqs[tabela]

    def registrar_auditoria_interno(self, ator, ip, acao, entidade, entidade_id=None, detalhe=None, id=None):
        """Grava registro de auditoria dentro do lock do agregado atual."""
        # Paridade com o Oracle (README §2.5): ator NOT NULL e limites de coluna, sem valor padrao.
        if not ator:
            raise RepoViolacao("ator da auditoria e obrigatorio")
        if len(ator) > _ATOR_MAX or (detalhe is not None and len(detalhe) > _DETALHE_MAX):
            raise RepoViolacao("auditoria excede o tamanho da coluna (ORA-12899)")
        with self.lock_auditoria:
            aid = id if id is not None else self.proximo_id("tbsss_auditoria")
            if aid in self.auditoria:
                raise RepoViolacao("id de auditoria ja usado", constraint="pk_tbsss_auditoria")
            reg = {
                "id": aid,
                "ator": ator,
                "ip_origem": ip,
                "acao": acao,
                "entidade": entidade,
                "entidade_id": entidade_id,
                "detalhe": detalhe,
                "created_at": self.agora(),
            }
            self.auditoria[aid] = copy.deepcopy(reg)
            return copy.deepcopy(reg)

    def ator_registro(self, auditoria=None, ator=None):
        """Ator das colunas de registro (CR-006, README §10): auditoria['ator'] ou ator=, obrigatorio.

        Chamado antes de qualquer gravacao: sem ator, nada e gravado (paridade com created_by NOT NULL).
        """
        valor = (auditoria or {}).get("ator") or ator
        if not valor:
            raise RepoViolacao("ator das colunas de registro e obrigatorio")
        if len(valor) > ATOR_MAX:
            raise RepoViolacao("ator excede o tamanho da coluna (ORA-12899)")
        return valor

    def carimbar_inclusao(self, reg, ator):
        """created_at (o informado ou SYSDATE) e created_by; updated_* nulos ate a 1a alteracao."""
        if not reg.get("created_at"):
            reg["created_at"] = self.agora()
        reg["created_by"] = ator
        reg["updated_at"] = None
        reg["updated_by"] = None
        return reg

    def carimbar_alteracao(self, reg, ator):
        """updated_at = SYSDATE e updated_by em toda alteracao de negocio; created_* nunca muda."""
        reg["updated_at"] = self.agora()
        reg["updated_by"] = ator
        return reg

    def checar_fk(self, existe, constraint):
        """FK do Oracle emulada: referencia inexistente vira RepoViolacao com o nome da FK (README §2.5)."""
        if not existe:
            raise RepoViolacao("Referencia inexistente (%s)" % constraint, constraint=constraint)

    def ambiente_existe(self, nome):
        return any(a["nome"] == nome for a in self.ambientes.values())

    def login_existe(self, login):
        return any(u["login"] == login for u in self.usuarios.values())

    def reset(self):
        """Limpa todas as colecoes e sequencias em memoria."""
        with self.lock_usuarios:
            with self.lock_rbac:
                with self.lock_catalogo:
                    with self.lock_tickets:
                        with self.lock_agendamentos:
                            with self.lock_auditoria:
                                with self.lock_agentes:
                                    self.ambientes.clear()
                                    self.perfis.clear()
                                    self.funcionalidades.clear()
                                    self.perfil_func.clear()
                                    self.perfil_amb.clear()
                                    self.perfil_scr.clear()
                                    self.scripts.clear()
                                    self.script_amb.clear()
                                    self.usuarios.clear()
                                    self.parametros.clear()
                                    self.script_param.clear()
                                    self.agendamentos.clear()
                                    self.tickets.clear()
                                    self.ticket_resp.clear()
                                    self.agentes.clear()
                                    self.auditoria.clear()
                                    self.controle.clear()
                                    self.seqs.clear()
                                    self.log_sim.clear()
                                    self.agentes_hb_sim.clear()


def paginar(itens, pagina=1, tamanho=20):
    """Utilitario padrao para paginacao deterministica com retorno em dict."""
    total = len(itens)
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
    }
