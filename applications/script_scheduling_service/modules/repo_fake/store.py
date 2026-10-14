# -*- coding: utf-8 -*-
"""Armazem em memoria compartilhado para o backend FAKE (README §2.5).

Mantem tabelas, sequencias, relogio injetavel e locks de sincronizacao por agregado.
"""
import collections
import copy
import datetime
import threading


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

        self.seqs = collections.defaultdict(int)

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

    def registrar_auditoria_interno(self, ator, ip, acao, entidade, entidade_id=None, detalhe=None):
        """Grava registro de auditoria dentro do lock do agregado atual."""
        with self.lock_auditoria:
            aid = self.proximo_id("tbsss_auditoria")
            reg = {
                "id": aid,
                "ator": ator or "SYSTEM",
                "ip_origem": ip,
                "acao": acao,
                "entidade": entidade,
                "entidade_id": entidade_id,
                "detalhe": detalhe,
                "created_at": self.agora(),
            }
            self.auditoria[aid] = copy.deepcopy(reg)
            return copy.deepcopy(reg)

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
                                    self.seqs.clear()


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
