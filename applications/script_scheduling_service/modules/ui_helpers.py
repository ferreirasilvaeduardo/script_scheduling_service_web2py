# -*- coding: utf-8 -*-
"""Formatacao de status, datas e duracoes para as views.

Funcoes puras: nao importam gluon.
"""

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
