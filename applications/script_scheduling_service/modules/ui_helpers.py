# -*- coding: utf-8 -*-
"""Formatacao de status, datas, duracoes, paginacao e alertas para as views.

Funcoes puras: nao importam gluon.
"""
import re

# Nomes simples da situacao (README §2.4.2, §5.2.1); o codigo tecnico fica so como detalhe.
_STATUS = {
    "PENDING": (u"Esperando", "sss-status-pending", "status-pending"),
    "RUNNING": (u"Rodando", "sss-status-running", "status-running"),
    "SUCCESS": (u"Deu certo", "sss-status-success", "status-success"),
    "FAILED": (u"Deu erro", "sss-status-failed", "status-failed"),
    "CANCELLED": (u"Cancelado", "sss-status-cancelled", "status-cancelled"),
}
_STATUS_DESCONHECIDO = (u"Desconhecido", "sss-status-unknown", "status-unknown")


def status_info(status):
    """Retorna {rotulo, classe, icone} do status do ticket (README §5.1)."""
    label, cls_name, icon = _STATUS.get(status, _STATUS_DESCONHECIDO)
    return {"label": label, "css_class": cls_name, "icon": icon}


_ATIVO = {
    "Y": (u"Ativo", "sss-status-success", "status-success"),
    "N": (u"Inativo", "sss-status-cancelled", "status-cancelled"),
}


def ativo_info(flag):
    """Retorna {rotulo, classe, icone} da flag ativo ('S'/'N') dos cadastros; outro valor e desconhecido."""
    label, cls_name, icon = _ATIVO.get(flag, _STATUS_DESCONHECIDO)
    return {"label": label, "css_class": cls_name, "icon": icon}


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


# Frases "o que aconteceu" / "o que fazer agora" por status_motivo (README §5.2.1, texto exato).
_EXPLICACOES = {
    "EXIT_OK": (u"Terminou e deu certo.", None),
    "EXIT_ERROR": (u"O script rodou, mas terminou avisando que algo deu errado (código {codigo}).",
                   u"Veja o fim do log para entender o erro. Se não souber resolver, envie o número deste ticket "
                   u"ao responsável pelo script."),
    "KILLED_SIGNAL": (u"O script foi interrompido de repente pelo servidor.",
                      u"Tente de novo. Se acontecer outra vez, avise o suporte com o número deste ticket."),
    "TIMEOUT": (u"O script demorou mais do que o tempo máximo ({tempo}) e foi parado.",
                u"Confira se as respostas estão certas e tente de novo. Se o script costuma demorar mais, "
                u"peça ao administrador para aumentar o tempo máximo."),
    "NODE_OFFLINE": (u"O servidor que rodava o script parou de responder.",
                     u"Tente de novo: outro servidor pode assumir."),
    "ORPHAN_PROCESS": (u"O servidor foi reiniciado e perdeu o controle do script.", u"Tente de novo."),
    "FENCED": (u"O servidor perdeu contato com o banco de dados e parou o script por segurança.",
               u"Tente de novo em alguns minutos."),
    "PRECHECK_FAILED": (u"O script não pôde começar: o servidor não encontrou o arquivo, ou ele não está liberado.",
                        u"Avise o administrador com o número deste ticket."),
    "SPAWN_ERROR": (u"O servidor não conseguiu iniciar o script.", u"Avise o administrador com o número deste ticket."),
    "LOG_LIMIT": (u"O script escreveu mensagens demais e foi parado, para não lotar o disco.",
                  u"Avise o responsável pelo script."),
    "SHUTDOWN": (u"O servidor foi desligado enquanto o script rodava.", u"Tente de novo."),
    "CANCEL_USER": (u"A execução foi cancelada a pedido.", None),
}


def tempo_simples(seconds):
    """Duracao em linguagem simples: 'menos de 1 minuto', '1 minuto', '4 minutos', '2 horas e 5 minutos'."""
    seconds = max(0, int(seconds or 0))
    if seconds < 60:
        return u"menos de 1 minuto"
    hours, rest = divmod(seconds // 60, 60)
    minutes = u"%d minuto%s" % (rest, "" if rest == 1 else "s")
    if not hours:
        return minutes
    text = u"%d hora%s" % (hours, "" if hours == 1 else "s")
    return text if not rest else u"%s e %s" % (text, minutes)


def explicacao_ticket(ticket, now, timeout_s=None):
    """{'situacao', 'aconteceu', 'fazer'} do ticket em linguagem simples (README §5.2.1, §5.7).

    agora: relogio do banco; timeout_s: tempo maximo do script (para a frase de TIMEOUT).
    """
    status = ticket.get("status")
    state = status_info(status)["label"]
    if status == "PENDING":
        scheduled = ticket.get("scheduled_at")
        if scheduled is not None and now is not None and scheduled > now:
            return {"state": state,
                    "happened": u"Está agendado para começar em %s às %s." % (
                        scheduled.strftime("%d/%m/%Y"), scheduled.strftime("%H:%M")),
                    "todo": u"Não precisa fazer nada. Se não quiser mais, cancele."}
        return {"state": state, "happened": u"Está na fila, esperando um servidor livre.",
                "todo": u"Não precisa fazer nada. Esta página se atualiza sozinha."}
    if status == "RUNNING":
        if ticket.get("cancel_requested") == "Y":
            return {"state": state,
                    "happened": u"O cancelamento foi pedido. O servidor está parando o script.",
                    "todo": u"Espere alguns segundos."}
        start = ticket.get("started_at")
        elapsed = (now - start).total_seconds() if start is not None and now is not None else 0
        return {"state": state, "happened": u"Está rodando agora. Começou há %s." % tempo_simples(elapsed),
                "todo": u"Acompanhe o log abaixo."}
    reason = ticket.get("status_reason")
    if reason not in _EXPLICACOES:
        return {"state": state,
                "happened": u"Terminou com um motivo que o sistema não conhece (%s)." % (reason or "-"),
                "todo": u"Avise o suporte com o número deste ticket."}
    happened, todo = _EXPLICACOES[reason]
    time_value = tempo_simples(timeout_s) if timeout_s else u"definido para o script"
    return {"state": state,
            "happened": happened.format(codigo=ticket.get("return_code"), tempo=time_value),
            "todo": todo}


def etapas_ticket(ticket, now):
    """Barra de etapas do detalhe (README §5.7): Pedido criado -> Na fila -> Rodando -> Terminou.

    Cada etapa: {rotulo, quando, estado} com estado 'done' | 'current' | 'pending' | 'skipped'.
    """
    status = ticket.get("status")
    terminal = status in ("SUCCESS", "FAILED", "CANCELLED")
    never_ran = status == "CANCELLED" and ticket.get("started_at") is None
    scheduled = ticket.get("scheduled_at")
    queue_when = formatar_data(scheduled)
    if status == "PENDING" and scheduled is not None and now is not None and scheduled > now:
        queue_when = u"agendado para %s" % queue_when
    if status == "RUNNING":
        start = ticket.get("started_at")
        elapsed = (now - start).total_seconds() if start is not None and now is not None else 0
        running_when = u"há %s" % tempo_simples(elapsed)
    elif never_ran:
        running_when = u"não chegou a rodar"
    else:
        running_when = formatar_data(ticket.get("started_at"))
    end = formatar_data(ticket.get("finished_at"))
    if terminal:
        end = u"%s — %s" % (status_info(status)["label"], end)
    states = {
        "PENDING": ("done", "current", "pending", "pending"),
        "RUNNING": ("done", "done", "current", "pending"),
    }.get(status, ("done", "done", "skipped" if never_ran else "done", "current"))
    labels = (u"Pedido criado", u"Na fila", u"Rodando", u"Terminou")
    whens = (formatar_data(ticket.get("created_at")), queue_when, running_when,
               end if terminal else u"-")
    return [{"label": r, "when": q, "state_info": e} for r, q, e in zip(labels, whens, states)]


# Nomes curtos dos motivos de erro (historico do script, README §5.8).
NOMES_MOTIVO = {
    "EXIT_ERROR": u"O script avisou que algo deu errado", "KILLED_SIGNAL": u"Interrompido pelo servidor",
    "TIMEOUT": u"Passou do tempo máximo", "NODE_OFFLINE": u"Servidor parou de responder",
    "ORPHAN_PROCESS": u"Servidor reiniciado", "FENCED": u"Servidor sem contato com o banco",
    "PRECHECK_FAILED": u"Arquivo não encontrado ou não liberado", "SPAWN_ERROR": u"Não conseguiu iniciar",
    "LOG_LIMIT": u"Mensagens demais", "SHUTDOWN": u"Servidor desligado",
}

# Series do grafico do historico na ordem fixa de empilhamento (de baixo para cima).
SERIES_HISTORICO = (("succeeded", u"Deu certo"), ("error", u"Deu erro"), ("cancelled", u"Cancelado"),
                    ("in_progress", u"Esperando ou rodando"))


def barras_empilhadas(days, width=1000, height=240, left_margin=28, bottom_margin=22, gap=2):
    """Geometria do grafico de barras empilhadas por dia (SVG gerado no servidor, README §5.8).

    dias: [{'label': 'dd/mm', 'succeeded': n, 'error': n, 'cancelled': n, 'in_progress': n}].
    Retorna {largura, altura, base_y, maximo, grade: [{y, rotulo}], eixo_x: [{x, rotulo}],
    barras: [{x, y, largura, altura, classe, titulo}]}. Cores so por classe CSS (sem style inline);
    vao de 2px entre os segmentos; o titulo de cada segmento e a dica ao passar o mouse.
    """
    max_value = max([sum(d.get(c, 0) for c, _r in SERIES_HISTORICO) for d in days] or [0])
    scale_max = max(max_value, 1)
    area_h = height - bottom_margin - 4
    base_y = height - bottom_margin
    n = max(len(days), 1)
    step = float(width - left_margin) / n
    width_bar = max(2.0, step * 0.7)
    bars, axis_x = [], []
    for i, d in enumerate(days):
        x = left_margin + i * step + (step - width_bar) / 2.0
        top = base_y
        for key, label in SERIES_HISTORICO:
            count = d.get(key, 0)
            if not count:
                continue
            h = area_h * count / float(scale_max)
            y = top - h
            bars.append({"x": round(x, 1), "y": round(y, 1), "width": round(width_bar, 1),
                           "height": round(max(h - gap, 1.0), 1), "css_class": "sss-graf-" + key,
                           "title": u"%s: %s — %d" % (d["label"], label, count)})
            top = y
        if i % 5 == 0 or i == n - 1:
            axis_x.append({"x": round(x + width_bar / 2.0, 1), "label": d["label"]})
    grid = [{"y": round(base_y - area_h * f, 1), "label": str(int(round(scale_max * f)))}
             for f in (0.5, 1.0) if max_value]
    return {"width": width, "height": height, "base_y": base_y, "maximum": max_value, "grid": grid,
            "x_axis": axis_x, "bars": bars, "left_margin": left_margin}


# Mensagens-padrao em duas partes: o que aconteceu + o que fazer agora (README §2.4.2, texto exato).
MENSAGENS = {
    "unattended_queue": (u"Há pedidos vencidos sem servidor disponível para o ambiente e o interpretador.",
                           u"Confira os servidores e quais ambientes e interpretadores eles atendem."),
    "running_without_pid": (u"Há pedidos reservados há mais de dois minutos sem processo registrado.",
                        u"Confira o servidor responsável e os logs antes de pedir outra execução."),
    "config_mismatch": (u"Há servidores ativos com configuração diferente da configuração deste nó web.",
                          u"Peça ao administrador para conferir e igualar as configurações críticas dos nós."),
    "no_permission": (u"Você não tem permissão para abrir esta página.",
                      u"Veja em O que eu posso fazer o que já está liberado para você, ou peça acesso ao administrador."),
    "not_found": (u"Não encontramos o que você procurou.", u"Confira o número ou volte para a lista."),
    "internal_error": (u"Algo deu errado do nosso lado.",
                      u"Tente de novo em alguns minutos. Se continuar, avise o suporte e informe o horário."),
    "conflict": (u"Outra pessoa mudou este registro enquanto você editava.",
                 u"Recarregue a página para ver a versão nova e faça a sua alteração de novo."),
    "session_expired": (u"Você ficou um tempo sem usar o sistema e saiu por segurança.", u"Entre de novo."),
    "session_max_age": (u"A sua sessão chegou ao tempo máximo e foi encerrada por segurança.", u"Entre de novo."),
    "login_failed": (u"Usuário ou senha incorretos.", u"Confira o que digitou e tente de novo."),
    "account_locked": (u"Houve muitas tentativas com a senha errada.",
                        u"Espere {minutos} minutos ou peça ao administrador para desbloquear."),
    "form_errors": (u"Alguns campos precisam de correção.",
                   u"Os campos estão marcados em vermelho, com a explicação embaixo de cada um."),
    "last_admin": (u"Não pode ficar sem nenhum administrador ativo.",
                     u"Antes, dê acesso de administrador a outra pessoa."),
}


# Quadro Saida do detalhe do ticket (CR-012, README §8.13): o que aconteceu + o que fazer agora.
SAIDA_GRAVANDO_LIMITE_S = 3600
_SAIDA_MENSAGENS = {
    "WRITING": (u"A saída está em preparação.", u"Atualize a página em alguns instantes."),
    "STALLED": (u"A saída não foi concluída.",
               u"Os arquivos ficaram temporariamente no servidor do agente {agent}. Peça a quem administra o servidor."),
    "AVAILABLE": (u"O script deixou {count} na pasta de saída ({size}).", u"Use o botão Baixar para salvar o zip."),
    "FILES": (u"A saída passou do limite de quantidade de arquivos e não foi empacotada.",
                 u"Os arquivos ficaram temporariamente no servidor do agente {agent}. Peça a quem administra o servidor."),
    "BYTES": (u"A saída passou do limite de tamanho e não foi empacotada.",
              u"Os arquivos ficaram temporariamente no servidor do agente {agent}. Peça a quem administra o servidor."),
    "FAILED": (u"A saída não foi gravada.",
               u"Os arquivos ficaram temporariamente no servidor do agente {agent}. Peça a quem administra o servidor."),
}
_SAIDA_CLASSE = {"WRITING": "info", "STALLED": "warning", "AVAILABLE": "success", "FILES": "warning",
                 "BYTES": "warning", "FAILED": "warning"}


def tamanho_legivel(nbytes):
    """Bytes em texto curto: '512 bytes', '12,3 KB', '4,5 MB' (virgula decimal, README §2.4.2)."""
    if nbytes is None:
        return u"-"
    n = int(nbytes)
    if n < 1024:
        return u"%d bytes" % n
    if n < 1024 * 1024:
        return (u"%.1f KB" % (n / 1024.0)).replace(".", ",")
    return (u"%.1f MB" % (n / (1024.0 * 1024.0))).replace(".", ",")


def quadro_saida(output, now):
    """Quadro Saida (CR-012) a partir de saida_obter, ou None sem saida. Nunca leva o conteudo nem o caminho."""
    if not output:
        return None
    state = output.get("state")
    key = state
    if state == "WRITING":
        since = output.get("updated_at") or output.get("created_at")
        if since is not None and now is not None and (now - since).total_seconds() > SAIDA_GRAVANDO_LIMITE_S:
            key = "STALLED"
    elif state == "EXCEEDED":
        key = "BYTES" if output.get("reason") == "BYTES" else "FILES"
    elif state not in _SAIDA_MENSAGENS:
        key = "FAILED"
    count = output.get("file_count")
    values = {"agent": output.get("agent_id") or u"-", "size": tamanho_legivel(output.get("size_bytes")),
               "count": (u"1 arquivo" if count == 1 else u"%s arquivos" % count)}
    happened, todo = _SAIDA_MENSAGENS[key]
    return {"state": state, "css_class": _SAIDA_CLASSE[key], "happened": happened.format(**values),
            "todo": todo.format(**values), "can_download": state == "AVAILABLE"}


def mensagem(key_name, **values):
    """Mensagem-padrao completa ('o que aconteceu' + 'o que fazer agora')."""
    happened, todo = MENSAGENS[key_name]
    return u"%s %s" % (happened, todo.format(**values))


def mensagem_partes(key_name, **values):
    """(o que aconteceu, o que fazer agora) para telas que mostram as duas partes separadas."""
    happened, todo = MENSAGENS[key_name]
    return happened, todo.format(**values)


def descricao_motivo(status_reason):
    """Texto em portugues do status_motivo (README §5.2); None/vazio vira None, codigo desconhecido e citado."""
    if status_reason is None or status_reason == "":
        return None
    return _MOTIVOS.get(status_reason, u"Motivo não catalogado (%s)." % status_reason)


def formatar_data(dt):
    """Formata datetime como dd/mm/aaaa HH:MM:SS; None vira '-'."""
    if dt is None:
        return "-"
    return dt.strftime("%d/%m/%Y %H:%M:%S")


# Colunas de registro (CR-006, README §10) e nomes simples dos atores do sistema (README §2.4.2).
COLUNAS_REGISTRO = ("created_at", "created_by", "updated_at", "updated_by")
_PREFIXO_SISTEMA = "SYSTEM:"
_ATORES_SISTEMA = {"init_db": u"Sistema (instalação)", "seed": u"Sistema (dados de demonstração)",
                   "purge": u"Sistema (limpeza)"}


def ator_visivel(actor, ctx):
    """Login de pessoa como o contexto pode ver (CR-007 D6, CR-008 E5): sem VIEW_AUDIT nem admin,
    vira "você" ou "outra pessoa"; atores do sistema e vazio passam direto."""
    ctx = ctx or {}
    if not actor or actor == "SYSTEM" or actor.startswith(_PREFIXO_SISTEMA):
        return actor
    if ctx.get("is_admin") is True or "VIEW_AUDIT" in (ctx.get("features") or ()):
        return actor
    return u"você" if actor == ctx.get("login") else u"outra pessoa"


def registro(reg, ctx):
    """Colunas de registro com os atores permitidos ao contexto da sessao."""
    date = dict((c, (reg or {}).get(c)) for c in COLUNAS_REGISTRO)
    for field in ("created_by", "updated_by"):
        date[field] = ator_visivel(date[field], ctx)
    return date


def nome_ator(actor):
    """Ator em linguagem simples: login como esta; SYSTEM:<agent_id> vira 'Sistema (agente <agent_id>)'."""
    if not actor:
        return "-"
    if actor == "SYSTEM":
        return u"Sistema"
    if actor.startswith(_PREFIXO_SISTEMA):
        rest = actor[len(_PREFIXO_SISTEMA):]
        return _ATORES_SISTEMA.get(rest, u"Sistema (agente %s)" % rest)
    return actor


def registro_exibicao(reg):
    """Textos do quadro Registro: {'created': '<data> por <ator>', 'updated': ... | 'Nunca alterado'}."""
    reg = reg or {}
    created = u"%s por %s" % (formatar_data(reg.get("created_at")), nome_ator(reg.get("created_by")))
    if reg.get("updated_at") is None:
        changed = u"Nunca alterado"
    else:
        changed = u"%s por %s" % (formatar_data(reg.get("updated_at")), nome_ator(reg.get("updated_by")))
    return {"created": created, "updated": changed}


def formatar_duracao(start, end):
    """Duracao entre dois datetimes ('42s', '5m 07s', '2h 15m 30s').

    Retorna '-' se algum extremo for None ou se fim < inicio.
    """
    if start is None or end is None:
        return "-"
    total = int((end - start).total_seconds())
    if total < 0:
        return "-"
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return "%dh %02dm %02ds" % (hours, minutes, seconds)
    if minutes:
        return "%dm %02ds" % (minutes, seconds)
    return "%ds" % seconds


_RE_INTEIRO = r"[0-9]{1,9}"


def _inteiro_positivo(value):
    """int >= 1 a partir de int ou str ASCII de ate 9 digitos; None se invalido."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        n = value
    elif isinstance(value, str) and re.fullmatch(_RE_INTEIRO, value):
        n = int(value)
    else:
        return None
    return n if n >= 1 else None


def sanitizar_pagina(value, default_value=1):
    """Pagina de request.vars; valor ausente, nao numerico ou < 1 vira `padrao`."""
    n = _inteiro_positivo(value)
    return default_value if n is None else n


def sanitizar_tamanho(value, allowed=(20, 50, 100)):
    """Tamanho de pagina restrito a `permitidos`; fora da lista vira permitidos[0]."""
    n = _inteiro_positivo(value)
    return n if n in allowed else allowed[0]


def paginacao_info(page, size, total, capped_total=False, quantity=None):
    """Navegacao por total exato ou por quantidade da pagina quando o total foi limitado.

    Com total 0 ha uma unica pagina, sem registros (faixa 0-0).
    """
    size = _inteiro_positivo(size) or 20
    total = total if isinstance(total, int) and not isinstance(total, bool) and total > 0 else 0
    total_pages = max(1, (total + size - 1) // size)
    page = max(sanitizar_pagina(page), 1)
    if not capped_total:
        page = min(page, total_pages)
    if total:
        first = (page - 1) * size + 1
        last = (first + quantity - 1 if capped_total and quantity is not None
                  else min(page * size, total))
        if capped_total and quantity == 0:
            first = last = 0
    else:
        first = last = 0
    return {
        "page": page,
        "size": size,
        "total": total,
        "total_pages": None if capped_total else total_pages,
        "total_capped": bool(capped_total),
        "has_previous": page > 1,
        "has_next": (quantity == size if capped_total and quantity is not None
                        else page < total_pages),
        "previous_page": max(page - 1, 1),
        "next_page": page + 1 if capped_total else min(page + 1, total_pages),
        "first_record": first,
        "last_record": last,
    }


def primeiro_campo_invalido(fields):
    """Nome do primeiro campo (na ordem dada) com 'error' preenchido; None se nenhum."""
    for field in fields or ():
        if field.get("error"):
            return field.get("name")
    return None


_ALERTAS = {
    "success": ("alert-success", "status-success", "status"),
    "warning": ("alert-warning", "icon-alert", "status"),
    "error": ("alert-danger", "status-failed", "alert"),
}


def alerta_info(flash):
    """Normaliza response.flash para {tipo, mensagem, classe, icone, role}.

    Aceita {'tipo', 'mensagem'}, (tipo, mensagem) ou texto simples. Tipo ausente
    ou desconhecido vira 'warning'. Retorna None quando nao ha mensagem.
    """
    if isinstance(flash, dict):
        kind, message = flash.get("kind"), flash.get("message")
    elif isinstance(flash, (tuple, list)) and len(flash) == 2:
        kind, message = flash
    else:
        kind, message = None, flash
    if message is None or message == "":
        return None
    if kind not in _ALERTAS:
        kind = "warning"
    cls_name, icon, role = _ALERTAS[kind]
    return {"kind": kind, "message": message, "css_class": cls_name, "icon": icon, "role": role}
