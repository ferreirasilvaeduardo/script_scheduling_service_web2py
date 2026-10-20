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
    rotulo, classe, icone = _STATUS.get(status, _STATUS_DESCONHECIDO)
    return {"rotulo": rotulo, "classe": classe, "icone": icone}


_ATIVO = {
    "S": (u"Ativo", "sss-status-success", "status-success"),
    "N": (u"Inativo", "sss-status-cancelled", "status-cancelled"),
}


def ativo_info(flag):
    """Retorna {rotulo, classe, icone} da flag ativo ('S'/'N') dos cadastros; outro valor e desconhecido."""
    rotulo, classe, icone = _ATIVO.get(flag, _STATUS_DESCONHECIDO)
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


def tempo_simples(segundos):
    """Duracao em linguagem simples: 'menos de 1 minuto', '1 minuto', '4 minutos', '2 horas e 5 minutos'."""
    segundos = max(0, int(segundos or 0))
    if segundos < 60:
        return u"menos de 1 minuto"
    horas, resto = divmod(segundos // 60, 60)
    minutos = u"%d minuto%s" % (resto, "" if resto == 1 else "s")
    if not horas:
        return minutos
    texto = u"%d hora%s" % (horas, "" if horas == 1 else "s")
    return texto if not resto else u"%s e %s" % (texto, minutos)


def explicacao_ticket(ticket, agora, timeout_s=None):
    """{'situacao', 'aconteceu', 'fazer'} do ticket em linguagem simples (README §5.2.1, §5.7).

    agora: relogio do banco; timeout_s: tempo maximo do script (para a frase de TIMEOUT).
    """
    status = ticket.get("status")
    situacao = status_info(status)["rotulo"]
    if status == "PENDING":
        agendado = ticket.get("scheduled_at")
        if agendado is not None and agora is not None and agendado > agora:
            return {"situacao": situacao,
                    "aconteceu": u"Está agendado para começar em %s às %s." % (
                        agendado.strftime("%d/%m/%Y"), agendado.strftime("%H:%M")),
                    "fazer": u"Não precisa fazer nada. Se não quiser mais, cancele."}
        return {"situacao": situacao, "aconteceu": u"Está na fila, esperando um servidor livre.",
                "fazer": u"Não precisa fazer nada. Esta página se atualiza sozinha."}
    if status == "RUNNING":
        if ticket.get("cancel_requested") == "S":
            return {"situacao": situacao,
                    "aconteceu": u"O cancelamento foi pedido. O servidor está parando o script.",
                    "fazer": u"Espere alguns segundos."}
        inicio = ticket.get("started_at")
        decorrido = (agora - inicio).total_seconds() if inicio is not None and agora is not None else 0
        return {"situacao": situacao, "aconteceu": u"Está rodando agora. Começou há %s." % tempo_simples(decorrido),
                "fazer": u"Acompanhe o log abaixo."}
    motivo = ticket.get("status_motivo")
    if motivo not in _EXPLICACOES:
        return {"situacao": situacao,
                "aconteceu": u"Terminou com um motivo que o sistema não conhece (%s)." % (motivo or "-"),
                "fazer": u"Avise o suporte com o número deste ticket."}
    aconteceu, fazer = _EXPLICACOES[motivo]
    tempo = tempo_simples(timeout_s) if timeout_s else u"definido para o script"
    return {"situacao": situacao,
            "aconteceu": aconteceu.format(codigo=ticket.get("return_code"), tempo=tempo),
            "fazer": fazer}


def etapas_ticket(ticket, agora):
    """Barra de etapas do detalhe (README §5.7): Pedido criado -> Na fila -> Rodando -> Terminou.

    Cada etapa: {rotulo, quando, estado} com estado 'feito' | 'atual' | 'pendente' | 'pulado'.
    """
    status = ticket.get("status")
    terminal = status in ("SUCCESS", "FAILED", "CANCELLED")
    nunca_rodou = status == "CANCELLED" and ticket.get("started_at") is None
    agendado = ticket.get("scheduled_at")
    fila_quando = formatar_data(agendado)
    if status == "PENDING" and agendado is not None and agora is not None and agendado > agora:
        fila_quando = u"agendado para %s" % fila_quando
    if status == "RUNNING":
        inicio = ticket.get("started_at")
        decorrido = (agora - inicio).total_seconds() if inicio is not None and agora is not None else 0
        rodando_quando = u"há %s" % tempo_simples(decorrido)
    elif nunca_rodou:
        rodando_quando = u"não chegou a rodar"
    else:
        rodando_quando = formatar_data(ticket.get("started_at"))
    fim = formatar_data(ticket.get("finished_at"))
    if terminal:
        fim = u"%s — %s" % (status_info(status)["rotulo"], fim)
    estados = {
        "PENDING": ("feito", "atual", "pendente", "pendente"),
        "RUNNING": ("feito", "feito", "atual", "pendente"),
    }.get(status, ("feito", "feito", "pulado" if nunca_rodou else "feito", "atual"))
    rotulos = (u"Pedido criado", u"Na fila", u"Rodando", u"Terminou")
    quandos = (formatar_data(ticket.get("created_at")), fila_quando, rodando_quando,
               fim if terminal else u"-")
    return [{"rotulo": r, "quando": q, "estado": e} for r, q, e in zip(rotulos, quandos, estados)]


# Nomes curtos dos motivos de erro (historico do script, README §5.8).
NOMES_MOTIVO = {
    "EXIT_ERROR": u"O script avisou que algo deu errado", "KILLED_SIGNAL": u"Interrompido pelo servidor",
    "TIMEOUT": u"Passou do tempo máximo", "NODE_OFFLINE": u"Servidor parou de responder",
    "ORPHAN_PROCESS": u"Servidor reiniciado", "FENCED": u"Servidor sem contato com o banco",
    "PRECHECK_FAILED": u"Arquivo não encontrado ou não liberado", "SPAWN_ERROR": u"Não conseguiu iniciar",
    "LOG_LIMIT": u"Mensagens demais", "SHUTDOWN": u"Servidor desligado",
}

# Series do grafico do historico na ordem fixa de empilhamento (de baixo para cima).
SERIES_HISTORICO = (("certo", u"Deu certo"), ("erro", u"Deu erro"), ("cancelado", u"Cancelado"),
                    ("andamento", u"Esperando ou rodando"))


def barras_empilhadas(dias, largura=1000, altura=240, margem_esq=28, margem_inf=22, vao=2):
    """Geometria do grafico de barras empilhadas por dia (SVG gerado no servidor, README §5.8).

    dias: [{'rotulo': 'dd/mm', 'certo': n, 'erro': n, 'cancelado': n, 'andamento': n}].
    Retorna {largura, altura, base_y, maximo, grade: [{y, rotulo}], eixo_x: [{x, rotulo}],
    barras: [{x, y, largura, altura, classe, titulo}]}. Cores so por classe CSS (sem style inline);
    vao de 2px entre os segmentos; o titulo de cada segmento e a dica ao passar o mouse.
    """
    maximo = max([sum(d.get(c, 0) for c, _r in SERIES_HISTORICO) for d in dias] or [0])
    escala_max = max(maximo, 1)
    area_h = altura - margem_inf - 4
    base_y = altura - margem_inf
    n = max(len(dias), 1)
    passo = float(largura - margem_esq) / n
    larg_barra = max(2.0, passo * 0.7)
    barras, eixo_x = [], []
    for i, d in enumerate(dias):
        x = margem_esq + i * passo + (passo - larg_barra) / 2.0
        topo = base_y
        for chave, rotulo in SERIES_HISTORICO:
            qtd = d.get(chave, 0)
            if not qtd:
                continue
            h = area_h * qtd / float(escala_max)
            y = topo - h
            barras.append({"x": round(x, 1), "y": round(y, 1), "largura": round(larg_barra, 1),
                           "altura": round(max(h - vao, 1.0), 1), "classe": "sss-graf-" + chave,
                           "titulo": u"%s: %s — %d" % (d["rotulo"], rotulo, qtd)})
            topo = y
        if i % 5 == 0 or i == n - 1:
            eixo_x.append({"x": round(x + larg_barra / 2.0, 1), "rotulo": d["rotulo"]})
    grade = [{"y": round(base_y - area_h * f, 1), "rotulo": str(int(round(escala_max * f)))}
             for f in (0.5, 1.0) if maximo]
    return {"largura": largura, "altura": altura, "base_y": base_y, "maximo": maximo, "grade": grade,
            "eixo_x": eixo_x, "barras": barras, "margem_esq": margem_esq}


# Mensagens-padrao em duas partes: o que aconteceu + o que fazer agora (README §2.4.2, texto exato).
MENSAGENS = {
    "fila_sem_atendente": (u"Há pedidos vencidos sem servidor disponível para o ambiente e o interpretador.",
                           u"Confira os servidores e quais ambientes e interpretadores eles atendem."),
    "rodando_sem_pid": (u"Há pedidos reservados há mais de dois minutos sem processo registrado.",
                        u"Confira o servidor responsável e os logs antes de pedir outra execução."),
    "config_divergente": (u"Há servidores ativos com configuração diferente da configuração deste nó web.",
                          u"Peça ao administrador para conferir e igualar as configurações críticas dos nós."),
    "sem_permissao": (u"Você não tem permissão para abrir esta página.",
                      u"Veja em O que eu posso fazer o que já está liberado para você, ou peça acesso ao administrador."),
    "nao_encontrado": (u"Não encontramos o que você procurou.", u"Confira o número ou volte para a lista."),
    "falha_interna": (u"Algo deu errado do nosso lado.",
                      u"Tente de novo em alguns minutos. Se continuar, avise o suporte e informe o horário."),
    "conflito": (u"Outra pessoa mudou este registro enquanto você editava.",
                 u"Recarregue a página para ver a versão nova e faça a sua alteração de novo."),
    "sessao_expirada": (u"Você ficou um tempo sem usar o sistema e saiu por segurança.", u"Entre de novo."),
    "sessao_max": (u"A sua sessão chegou ao tempo máximo e foi encerrada por segurança.", u"Entre de novo."),
    "login_incorreto": (u"Usuário ou senha incorretos.", u"Confira o que digitou e tente de novo."),
    "conta_bloqueada": (u"Houve muitas tentativas com a senha errada.",
                        u"Espere {minutos} minutos ou peça ao administrador para desbloquear."),
    "formulario": (u"Alguns campos precisam de correção.",
                   u"Os campos estão marcados em vermelho, com a explicação embaixo de cada um."),
    "ultimo_admin": (u"Não pode ficar sem nenhum administrador ativo.",
                     u"Antes, dê acesso de administrador a outra pessoa."),
}


# Quadro Saida do detalhe do ticket (CR-012, README §8.13): o que aconteceu + o que fazer agora.
SAIDA_GRAVANDO_LIMITE_S = 3600
_SAIDA_MENSAGENS = {
    "GRAVANDO": (u"A saída está em preparação.", u"Atualize a página em alguns instantes."),
    "PARADA": (u"A saída não foi concluída.",
               u"Os arquivos ficaram temporariamente no servidor do agente {agente}. Peça a quem administra o servidor."),
    "DISPONIVEL": (u"O script deixou {qtd} na pasta de saída ({tamanho}).", u"Use o botão Baixar para salvar o zip."),
    "ARQUIVOS": (u"A saída passou do limite de quantidade de arquivos e não foi empacotada.",
                 u"Os arquivos ficaram temporariamente no servidor do agente {agente}. Peça a quem administra o servidor."),
    "BYTES": (u"A saída passou do limite de tamanho e não foi empacotada.",
              u"Os arquivos ficaram temporariamente no servidor do agente {agente}. Peça a quem administra o servidor."),
    "FALHOU": (u"A saída não foi gravada.",
               u"Os arquivos ficaram temporariamente no servidor do agente {agente}. Peça a quem administra o servidor."),
}
_SAIDA_CLASSE = {"GRAVANDO": "info", "PARADA": "warning", "DISPONIVEL": "success", "ARQUIVOS": "warning",
                 "BYTES": "warning", "FALHOU": "warning"}


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


def quadro_saida(saida, agora):
    """Quadro Saida (CR-012) a partir de saida_obter, ou None sem saida. Nunca leva o conteudo nem o caminho."""
    if not saida:
        return None
    situacao = saida.get("situacao")
    chave = situacao
    if situacao == "GRAVANDO":
        desde = saida.get("updated_at") or saida.get("created_at")
        if desde is not None and agora is not None and (agora - desde).total_seconds() > SAIDA_GRAVANDO_LIMITE_S:
            chave = "PARADA"
    elif situacao == "EXCEDEU":
        chave = "BYTES" if saida.get("motivo") == "BYTES" else "ARQUIVOS"
    elif situacao not in _SAIDA_MENSAGENS:
        chave = "FALHOU"
    qtd = saida.get("qtd_arquivos")
    valores = {"agente": saida.get("agente_id") or u"-", "tamanho": tamanho_legivel(saida.get("tamanho_bytes")),
               "qtd": (u"1 arquivo" if qtd == 1 else u"%s arquivos" % qtd)}
    aconteceu, fazer = _SAIDA_MENSAGENS[chave]
    return {"situacao": situacao, "classe": _SAIDA_CLASSE[chave], "aconteceu": aconteceu.format(**valores),
            "fazer": fazer.format(**valores), "pode_baixar": situacao == "DISPONIVEL"}


def mensagem(chave, **valores):
    """Mensagem-padrao completa ('o que aconteceu' + 'o que fazer agora')."""
    aconteceu, fazer = MENSAGENS[chave]
    return u"%s %s" % (aconteceu, fazer.format(**valores))


def mensagem_partes(chave, **valores):
    """(o que aconteceu, o que fazer agora) para telas que mostram as duas partes separadas."""
    aconteceu, fazer = MENSAGENS[chave]
    return aconteceu, fazer.format(**valores)


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


# Colunas de registro (CR-006, README §10) e nomes simples dos atores do sistema (README §2.4.2).
COLUNAS_REGISTRO = ("created_at", "created_by", "updated_at", "updated_by")
_PREFIXO_SISTEMA = "SYSTEM:"
_ATORES_SISTEMA = {"init_db": u"Sistema (instalação)", "seed": u"Sistema (dados de demonstração)",
                   "purge": u"Sistema (limpeza)"}


def ator_visivel(ator, ctx):
    """Login de pessoa como o contexto pode ver (CR-007 D6, CR-008 E5): sem VER_AUDITORIA nem admin,
    vira "você" ou "outra pessoa"; atores do sistema e vazio passam direto."""
    ctx = ctx or {}
    if not ator or ator == "SYSTEM" or ator.startswith(_PREFIXO_SISTEMA):
        return ator
    if ctx.get("is_admin") is True or "VER_AUDITORIA" in (ctx.get("funcionalidades") or ()):
        return ator
    return u"você" if ator == ctx.get("login") else u"outra pessoa"


def registro(reg, ctx):
    """Colunas de registro com os atores permitidos ao contexto da sessao."""
    dados = dict((c, (reg or {}).get(c)) for c in COLUNAS_REGISTRO)
    for campo in ("created_by", "updated_by"):
        dados[campo] = ator_visivel(dados[campo], ctx)
    return dados


def nome_ator(ator):
    """Ator em linguagem simples: login como esta; SYSTEM:<agent_id> vira 'Sistema (agente <agent_id>)'."""
    if not ator:
        return "-"
    if ator == "SYSTEM":
        return u"Sistema"
    if ator.startswith(_PREFIXO_SISTEMA):
        resto = ator[len(_PREFIXO_SISTEMA):]
        return _ATORES_SISTEMA.get(resto, u"Sistema (agente %s)" % resto)
    return ator


def registro_exibicao(reg):
    """Textos do quadro Registro: {'criado': '<data> por <ator>', 'alterado': ... | 'Nunca alterado'}."""
    reg = reg or {}
    criado = u"%s por %s" % (formatar_data(reg.get("created_at")), nome_ator(reg.get("created_by")))
    if reg.get("updated_at") is None:
        alterado = u"Nunca alterado"
    else:
        alterado = u"%s por %s" % (formatar_data(reg.get("updated_at")), nome_ator(reg.get("updated_by")))
    return {"criado": criado, "alterado": alterado}


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


def paginacao_info(pagina, tamanho, total, total_limitado=False, quantidade=None):
    """Navegacao por total exato ou por quantidade da pagina quando o total foi limitado.

    Com total 0 ha uma unica pagina, sem registros (faixa 0-0).
    """
    tamanho = _inteiro_positivo(tamanho) or 20
    total = total if isinstance(total, int) and not isinstance(total, bool) and total > 0 else 0
    total_paginas = max(1, (total + tamanho - 1) // tamanho)
    pagina = max(sanitizar_pagina(pagina), 1)
    if not total_limitado:
        pagina = min(pagina, total_paginas)
    if total:
        primeiro = (pagina - 1) * tamanho + 1
        ultimo = (primeiro + quantidade - 1 if total_limitado and quantidade is not None
                  else min(pagina * tamanho, total))
        if total_limitado and quantidade == 0:
            primeiro = ultimo = 0
    else:
        primeiro = ultimo = 0
    return {
        "pagina": pagina,
        "tamanho": tamanho,
        "total": total,
        "total_paginas": None if total_limitado else total_paginas,
        "total_limitado": bool(total_limitado),
        "tem_anterior": pagina > 1,
        "tem_proxima": (quantidade == tamanho if total_limitado and quantidade is not None
                        else pagina < total_paginas),
        "anterior": max(pagina - 1, 1),
        "proxima": pagina + 1 if total_limitado else min(pagina + 1, total_paginas),
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
