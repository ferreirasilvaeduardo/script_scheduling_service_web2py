# -*- coding: utf-8 -*-
"""Duble em memoria do repo_oracle.scheduler_saida (CR-012) para os testes do agente."""
from repo_oracle import scheduler_saida


class RepoSaidaMemoria(object):
    """Contrato do RepoSchedulerSaida em memoria. tickets: {id: {'agente_id': ...}} para a posse."""

    def __init__(self, tickets=None):
        self.tickets = tickets if tickets is not None else {}
        self.linhas = {}
        self.falhas = []
        self.chamadas = []

    def _dono(self, tid, agente_id):
        t = self.tickets.get(tid)
        return t is not None and t.get("agente_id") == agente_id

    def _falhar(self, nome):
        self.chamadas.append(nome)
        if self.falhas and self.falhas[0][0] == nome:
            raise self.falhas.pop(0)[1]

    def iniciar(self, conn, tid, agente_id):
        self._falhar("iniciar")
        linha = self.linhas.get(tid)
        if linha is not None:
            if linha["situacao"] == "GRAVANDO" and linha["agente_id"] == agente_id:
                linha.update(conteudo=b"", qtd_arquivos=None, tamanho_bytes=None)
                return True
            return False
        if not self._dono(tid, agente_id):
            return False
        self.linhas[tid] = {"situacao": "GRAVANDO", "motivo": None, "agente_id": agente_id, "conteudo": b"",
                            "qtd_arquivos": None, "tamanho_bytes": None}
        return True

    def anexar(self, conn, tid, agente_id, offset, parte):
        self._falhar("anexar")
        linha = self.linhas.get(tid)
        if linha is None or linha["situacao"] != "GRAVANDO" or linha["agente_id"] != agente_id:
            return scheduler_saida.POSSE_PERDIDA
        atual = len(linha["conteudo"])
        if atual == offset:
            linha["conteudo"] += parte
            return scheduler_saida.GRAVADO
        if atual == offset + len(parte) and linha["conteudo"][offset:] == parte:
            return scheduler_saida.JA_GRAVADO
        raise scheduler_saida.SaidaOffsetInconsistente(tid, offset, len(parte))

    def concluir(self, conn, tid, agente_id, qtd, tamanho):
        self._falhar("concluir")
        linha = self.linhas.get(tid)
        if linha is None or linha["situacao"] != "GRAVANDO" or linha["agente_id"] != agente_id \
                or len(linha["conteudo"]) != tamanho:
            return False
        linha.update(situacao="DISPONIVEL", qtd_arquivos=qtd, tamanho_bytes=tamanho)
        return True

    def registrar_sem_conteudo(self, conn, tid, agente_id, situacao, motivo, qtd=None):
        self._falhar("registrar_sem_conteudo")
        linha = self.linhas.get(tid)
        if linha is not None:
            if linha["situacao"] != "GRAVANDO" or linha["agente_id"] != agente_id:
                return False
        elif not self._dono(tid, agente_id):
            return False
        self.linhas[tid] = {"situacao": situacao, "motivo": motivo, "agente_id": agente_id, "conteudo": None,
                            "qtd_arquivos": qtd, "tamanho_bytes": None}
        return True

    def falhar_gravando_do_agente(self, conn, agente_id):
        self._falhar("falhar_gravando_do_agente")
        n = 0
        for linha in self.linhas.values():
            if linha["situacao"] == "GRAVANDO" and linha["agente_id"] == agente_id:
                linha.update(situacao="FALHOU", motivo="ERRO", conteudo=None)
                n += 1
        return n

    def situacao(self, conn, tid):
        linha = self.linhas.get(tid)
        return (linha["situacao"], linha["agente_id"]) if linha else None
