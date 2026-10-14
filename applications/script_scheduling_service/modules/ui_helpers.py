# -*- coding: utf-8 -*-
"""Formatacao de status, datas, duracoes, paginacao e alertas para as views.

Funcoes puras: nao importam gluon.
"""
import re

_STATUS = {
    "PENDING": (u"Pendente", "sss-status-pending", "status-pending"),
    "RUNNING": (u"Em execução", "sss-status-running", "status-running"),
    "SUCCESS": (u"Sucesso", "sss-status-success", "status-success"),
    "FAILED": (u"Falha", "sss-status-failed", "status-failed"),
    "CANCELLED": (u"Cancelado", "sss-status-cancelled", "status-cancelled"),
}
_STATUS_DESCONHECIDO = (u"Desconhecido", "sss-status-unknown", "status-unknown")


def status_info(status):
    """Retorna {rotulo, classe, icone} do status do ticket (README §5.1)."""
    rotulo, classe, icone = _STATUS.get(status, _STATUS_DESCONHECIDO)
    return {"rotulo": rotulo, "classe": classe, "icone": icone}


_MOTIVOS = {
    "EXIT_OK": u"Execução concluída com código de saída 0.",
    "EXIT_ERROR": u"O script terminou com código de saída diferente de zero.",
    "KILLED_SIGNAL": u"O processo foi encerrado por um sinal não solicitado (código 128 + número do sinal).",
    "TIMEOUT": u"A execução excedeu o tempo limite e foi encerrada.",
    "NODE_OFFLINE": u"O agente responsável ficou sem sinal de vida e o ticket foi encerrado por outro agente.",
    "ORPHAN_PROCESS": u"O processo não foi encontrado no agente dono (processo órfão).",
    "FENCED": u"O agente perdeu a conexão com o banco e interrompeu a execução para evitar duplicidade.",
    "PRECHECK_FAILED": u"A pré-validação do script falhou antes da execução.",
    "SPAWN_ERROR": u"Não foi possível iniciar o processo do script.",
    "LOG_LIMIT": u"A saída do script excedeu o limite de log e a execução foi encerrada.",
    "SHUTDOWN": u"O agente foi desligado durante a execução.",
    "CANCEL_USER": u"Execução cancelada por solicitação do usuário.",
}


def descricao_motivo(status_motivo):
    """Texto em portugues do status_motivo (README §5.2); None/vazio vira None, codigo desconhecido e citado."""
    if status_motivo is None or status_motivo == "":
        return None
    return _MOTIVOS.get(status_motivo, u"Motivo não catalogado (%s)." % status_motivo)


def formatar_data(dt):
    """Formata datetime como dd/mm/aaaa HH:MM:SS; None vira '-'."""
    if dt is None:
        return "-"
    return dt.strftime("%d/%m/%Y %H:%M:%S")


def formatar_duracao(inicio, fim):
    """Duracao entre dois datetimes ('42s', '5m 07s', '2h 15m 30s').

    Retorna '-' se algum extremo for None ou se fim < inicio.
    """
    if inicio is None or fim is None:
        return "-"
    total = int((fim - inicio).total_seconds())
    if total < 0:
        return "-"
    horas, resto = divmod(total, 3600)
    minutos, segundos = divmod(resto, 60)
    if horas:
        return "%dh %02dm %02ds" % (horas, minutos, segundos)
    if minutos:
        return "%dm %02ds" % (minutos, segundos)
    return "%ds" % segundos


_RE_INTEIRO = r"[0-9]{1,9}"


def _inteiro_positivo(valor):
    """int >= 1 a partir de int ou str ASCII de ate 9 digitos; None se invalido."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        n = valor
    elif isinstance(valor, str) and re.fullmatch(_RE_INTEIRO, valor):
        n = int(valor)
    else:
        return None
    return n if n >= 1 else None


def sanitizar_pagina(valor, padrao=1):
    """Pagina de request.vars; valor ausente, nao numerico ou < 1 vira `padrao`."""
    n = _inteiro_positivo(valor)
    return padrao if n is None else n


def sanitizar_tamanho(valor, permitidos=(20, 50, 100)):
    """Tamanho de pagina restrito a `permitidos`; fora da lista vira permitidos[0]."""
    n = _inteiro_positivo(valor)
    return n if n in permitidos else permitidos[0]


def paginacao_info(pagina, tamanho, total):
    """Dados de navegacao com a pagina limitada a [1, total_paginas].

    Com total 0 ha uma unica pagina, sem registros (faixa 0-0).
    """
    tamanho = _inteiro_positivo(tamanho) or 20
    total = total if isinstance(total, int) and not isinstance(total, bool) and total > 0 else 0
    total_paginas = max(1, (total + tamanho - 1) // tamanho)
    pagina = min(max(sanitizar_pagina(pagina), 1), total_paginas)
    if total:
        primeiro = (pagina - 1) * tamanho + 1
        ultimo = min(pagina * tamanho, total)
    else:
        primeiro = ultimo = 0
    return {
        "pagina": pagina,
        "tamanho": tamanho,
        "total": total,
        "total_paginas": total_paginas,
        "tem_anterior": pagina > 1,
        "tem_proxima": pagina < total_paginas,
        "anterior": max(pagina - 1, 1),
        "proxima": min(pagina + 1, total_paginas),
        "primeiro_registro": primeiro,
        "ultimo_registro": ultimo,
    }


def primeiro_campo_invalido(campos):
    """Nome do primeiro campo (na ordem dada) com 'erro' preenchido; None se nenhum."""
    for campo in campos or ():
        if campo.get("erro"):
            return campo.get("nome")
    return None


_ALERTAS = {
    "sucesso": ("alert-success", "status-success", "status"),
    "aviso": ("alert-warning", "icon-alert", "status"),
    "erro": ("alert-danger", "status-failed", "alert"),
}


def alerta_info(flash):
    """Normaliza response.flash para {tipo, mensagem, classe, icone, role}.

    Aceita {'tipo', 'mensagem'}, (tipo, mensagem) ou texto simples. Tipo ausente
    ou desconhecido vira 'aviso'. Retorna None quando nao ha mensagem.
    """
    if isinstance(flash, dict):
        tipo, mensagem = flash.get("tipo"), flash.get("mensagem")
    elif isinstance(flash, (tuple, list)) and len(flash) == 2:
        tipo, mensagem = flash
    else:
        tipo, mensagem = None, flash
    if mensagem is None or mensagem == "":
        return None
    if tipo not in _ALERTAS:
        tipo = "aviso"
    classe, icone, role = _ALERTAS[tipo]
    return {"tipo": tipo, "mensagem": mensagem, "classe": classe, "icone": icone, "role": role}
