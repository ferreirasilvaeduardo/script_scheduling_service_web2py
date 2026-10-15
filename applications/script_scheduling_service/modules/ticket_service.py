# -*- coding: utf-8 -*-
"""Disparo manual de script e consulta de tickets (README §4.3.C, §5, §6).

O servidor e a autoridade: script, ambiente e homologacao sao sempre recarregados do
repositorio e reautorizados com rbac.pode_executar. Valores de parametros nunca vao para
o log; so codigos de campo.
"""
import collections
import datetime
import json
import os
import re
import shlex
import threading

import params_compiler
import path_guard
import rbac
import ui_helpers
from repo_errors import RepoErro, RepoNaoEncontrado

CAMPO_GERAL = params_compiler.CHAVE_GERAL
CAMPO_PRIORIDADE = "prioridade"
CAMPO_AGENDAMENTO = "scheduled_at"
PRIORIDADE_PADRAO = 2
AMBIENTE_PRODUCAO = "PRODUCAO"

MSG_SCRIPT_INDISPONIVEL = (u"O script não está disponível para execução neste servidor. "
                           u"Contate o administrador.")
MSG_FALHA_CRIAR = u"Não foi possível criar o ticket. Tente novamente em instantes."

ROTULOS_PRIORIDADE = {
    1: u"1 — Urgente (exclusiva de administradores)",
    2: u"2 — Normal (padrão)",
    3: u"3 — Baixa",
    4: u"4 — Mínima",
}

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_AMBIENTE = re.compile(r"[A-Z0-9_]{1,30}")
_FORMATOS_AGENDAMENTO = ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S")
_AMBIENTES_MAX = 1000
_SCRIPTS_MAX = 1000
_FILHOS_MAX = 100

STATUS_TICKET = ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED")
STATUS_TERMINAIS = ("SUCCESS", "FAILED", "CANCELLED")
STATUS_CANCELAVEIS = ("PENDING", "RUNNING")
ORIGENS = (("manual", u"Manual"), ("agendamento", u"Agendamento"))
FILTROS = ("status", "ambiente", "script", "solicitante", "criado_de", "criado_ate", "origem")

MSG_CANCELAMENTO = {
    "TERMINAL": u"O ticket já estava finalizado.",
    "CANCELADO": u"Ticket cancelado.",
    "SINALIZADO": u"Cancelamento solicitado; o agente encerrará a execução.",
}

_RE_LOGIN = re.compile(r"[a-z0-9._-]{3,30}")
_FORMATO_DIA = "%Y-%m-%d"

# Teto por chamada do visualizador e tamanho do bloco do download (README §8.10).
LOG_MAX_CHARS = 65536
_RE_OFFSET = re.compile(r"[0-9]{1,10}")
MARCADOR_DOWNLOAD_INTERROMPIDO = u"\n[SSS] download interrompido por falha na leitura do log\n"


class AcessoNegado(Exception):
    """Execucao nao autorizada; o motivo (rbac.Motivo) e destinado apenas ao log."""

    def __init__(self, motivo):
        Exception.__init__(self, motivo)
        self.motivo = motivo


class ErroReexecucao(Exception):
    """Reexecucao nao gravada (recompilacao invalida ou falha de persistencia).

    erros: dict codigo_campo -> mensagem, ja seguro para exibicao (sem valores).
    """

    def __init__(self, ticket_id, erros):
        Exception.__init__(self, ",".join(sorted(erros)))
        self.ticket_id = ticket_id
        self.erros = erros


class OffsetInvalido(ValueError):
    """Offset de leitura do log ausente, negativo ou nao inteiro."""


def _offset(valor):
    valor = _ultimo(valor)
    if isinstance(valor, int) and not isinstance(valor, bool) and 0 <= valor < 10 ** 10:
        return valor
    if isinstance(valor, str) and _RE_OFFSET.fullmatch(valor):
        return int(valor)
    raise OffsetInvalido("offset invalido")


def _id(valor):
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor if valor > 0 else None
    if isinstance(valor, str) and _RE_ID.fullmatch(valor):
        numero = int(valor)
        return numero if numero > 0 else None
    return None


def _ultimo(valor):
    # Campo repetido no POST (hidden + checkbox): vale o ultimo enviado.
    if isinstance(valor, (list, tuple)):
        return valor[-1] if valor else None
    return valor


def _opcoes(parametro):
    try:
        opcoes = json.loads(parametro.get("opcoes_json") or "", object_pairs_hook=collections.OrderedDict)
    except ValueError:
        return []
    if not isinstance(opcoes, dict):
        return []
    return [(str(k), str(v)) for k, v in opcoes.items()]


def _ordenados(vinculos):
    return sorted(vinculos, key=lambda v: int(v["ordem"]))


def _texto_resposta(valor):
    if valor is True:
        return "true"
    if valor is False:
        return "false"
    return valor


def _dia(valor):
    if not isinstance(valor, str):
        return None
    try:
        return datetime.datetime.strptime(valor.strip(), _FORMATO_DIA)
    except ValueError:
        return None


def normalizar_filtros(entrada):
    """Allowlist de chaves e valores dos filtros da lista de tickets (querystring).

    Retorna OrderedDict apenas com os filtros validos, na forma de exibicao/URL: status
    (lista na ordem canonica), ambiente, script (int), solicitante, criado_de/criado_ate
    ('YYYY-MM-DD') e origem. Chaves desconhecidas e valores invalidos sao descartados.
    """
    entrada = entrada or {}
    limpos = collections.OrderedDict()
    status = entrada.get("status")
    if isinstance(status, str):
        status = [status]
    if isinstance(status, (list, tuple)):
        marcados = [st for st in STATUS_TICKET if st in status]
        if marcados:
            limpos["status"] = marcados
    ambiente = _ultimo(entrada.get("ambiente"))
    if isinstance(ambiente, str) and _RE_AMBIENTE.fullmatch(ambiente):
        limpos["ambiente"] = ambiente
    script = _id(_ultimo(entrada.get("script")))
    if script is not None:
        limpos["script"] = script
    solicitante = _ultimo(entrada.get("solicitante"))
    if isinstance(solicitante, str):
        solicitante = solicitante.strip().lower()
        if _RE_LOGIN.fullmatch(solicitante):
            limpos["solicitante"] = solicitante
    for chave in ("criado_de", "criado_ate"):
        dia = _dia(_ultimo(entrada.get(chave)))
        if dia is not None:
            limpos[chave] = dia.strftime(_FORMATO_DIA)
    origem = _ultimo(entrada.get("origem"))
    if origem in dict(ORIGENS):
        limpos["origem"] = origem
    return limpos


def _filtros_repo(limpos):
    """Traduz filtros normalizados para as chaves do contrato; periodo vira [inicio, fim + 1 dia)."""
    repo = {}
    if "status" in limpos:
        repo["status"] = list(limpos["status"])
    if "ambiente" in limpos:
        repo["ambiente"] = limpos["ambiente"]
    if "script" in limpos:
        repo["script_id"] = limpos["script"]
    if "solicitante" in limpos:
        repo["solicitante"] = limpos["solicitante"]
    if "origem" in limpos:
        repo["origem"] = limpos["origem"]
    if "criado_de" in limpos:
        repo["criado_inicio"] = _dia(limpos["criado_de"])
    if "criado_ate" in limpos:
        repo["criado_fim"] = _dia(limpos["criado_ate"]) + datetime.timedelta(days=1)
    return repo


def _duracao(ticket, agora):
    fim = ticket.get("finished_at")
    if fim is None and ticket.get("status") == "RUNNING":
        fim = agora
    return ui_helpers.formatar_duracao(ticket.get("started_at"), fim)


def _snapshot(ticket):
    try:
        snap = json.loads(ticket.get("parametros_enviados") or "")
    except (TypeError, ValueError):
        return None
    return snap if isinstance(snap, dict) else None


def _argv_exibicao(snap, base=None):
    # Snapshot ilegivel ou de versao anterior ao CR-001 (v1) nao tem argv exibivel.
    if snap is None or snap.get("versao") != params_compiler.VERSAO_SNAPSHOT:
        return None
    try:
        return params_compiler.argv_para_exibicao(snap, base)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


class ServicoTicket(object):
    """Servico de disparo com dependencias injetadas (repositorios, arvore de scripts e log)."""

    def __init__(self, catalogo, tickets, base_script_dir, script_owner_uids, log):
        self._catalogo = catalogo
        self._tickets = tickets
        self._base = base_script_dir
        self._owner_uids = tuple(script_owner_uids)
        self._log = log

    # ------------------------------------------------------------ autorizacao

    def _negar(self, ctx, motivo, script_id, ambiente):
        self._log.warning("disparo negado (login=%s script_id=%r ambiente=%r motivo=%s)",
                          (ctx or {}).get("login"), script_id, ambiente, motivo,
                          extra={"acao": "RBAC"})
        raise AcessoNegado(motivo)

    def _script(self, ctx, script_id):
        sid = _id(script_id)
        if sid is None:
            self._negar(ctx, rbac.Motivo.DADO_INVALIDO, script_id, None)
        try:
            return self._catalogo.scripts_obter(sid)
        except RepoNaoEncontrado:
            self._negar(ctx, rbac.Motivo.DADO_INVALIDO, script_id, None)

    def _ambiente_por_nome(self, nome):
        if not isinstance(nome, str) or not _RE_AMBIENTE.fullmatch(nome):
            return None
        pagina = self._catalogo.ambientes_listar(filtros={"nome": nome}, pagina=1, tamanho=_AMBIENTES_MAX)
        for amb in pagina["itens"]:
            if amb.get("nome") == nome:
                return amb
        return None

    def _autorizar(self, ctx, script_id, ambiente):
        """Recarrega script, ambiente e homologacao do repositorio e aplica pode_executar."""
        script = self._script(ctx, script_id)
        amb = self._ambiente_por_nome(ambiente)
        if amb is None:
            self._negar(ctx, rbac.Motivo.DADO_INVALIDO, script_id, ambiente)
        homologacoes = self._catalogo.homologacao_obter(script["id"])
        ok, motivo = rbac.pode_executar(ctx, script, amb, homologacoes)
        if not ok:
            self._negar(ctx, motivo, script["id"], amb["nome"])
        return script, amb

    def _ambientes_executaveis(self, ctx, script):
        ambientes = []
        for aid in self._catalogo.homologacao_obter(script["id"]):
            try:
                amb = self._catalogo.ambientes_obter(aid)
            except RepoNaoEncontrado:
                continue
            ok, _motivo = rbac.pode_executar(ctx, script, amb, (aid,))
            if ok:
                ambientes.append(amb)
        ambientes.sort(key=lambda a: a["nome"])
        return ambientes

    # ----------------------------------------------------------- formulario

    def scripts_disponiveis(self, ctx):
        """Scripts executaveis pelo usuario em ao menos um ambiente, agrupados por grupo/categoria.

        Retorna lista ordenada de {grupo, categoria, scripts: [{id, nome, descricao, etapa}]}.
        """
        if not rbac.tem_func(ctx, "EXEC_SCRIPT"):
            return []
        grupos = collections.OrderedDict()
        candidatos = sorted(self._catalogo.scripts_executaveis(ctx),
                            key=lambda s: ((s.get("grupo") or ""), (s.get("categoria") or ""), s["nome"]))
        for script in candidatos:
            if not self._ambientes_executaveis(ctx, script):
                continue
            chave = (script.get("grupo") or u"Sem grupo", script.get("categoria") or u"Sem categoria")
            grupos.setdefault(chave, []).append({
                "id": script["id"],
                "nome": script["nome"],
                "descricao": script.get("descricao") or "",
                "etapa": script.get("etapa") or "",
            })
        return [{"grupo": g, "categoria": c, "scripts": itens} for (g, c), itens in grupos.items()]

    def ambientes_disponiveis(self, ctx, script_id):
        """Script e ambientes homologados E autorizados para ele; lanca AcessoNegado se nenhum."""
        script = self._script(ctx, script_id)
        ambientes = self._ambientes_executaveis(ctx, script)
        if not ambientes:
            self._negar(ctx, rbac.Motivo.SEM_AMBIENTE, script["id"], None)
        return script, [{"id": a["id"], "nome": a["nome"], "descricao": a.get("descricao") or ""}
                        for a in ambientes]

    def _vinculos(self, script_id):
        return [v for v in self._catalogo.script_params_obter(script_id) if v.get("ativo") == "S"]

    def _padrao_exibicao(self, vinculo):
        for fonte in (vinculo.get("valor_padrao_sub"), vinculo.get("valor_padrao")):
            if fonte is None or (isinstance(fonte, str) and fonte.strip() == ""):
                continue
            try:
                return params_compiler.validar_valor(vinculo, fonte)
            except params_compiler.ParamErro:
                return None
        return None

    def preparar_formulario(self, ctx, script_id, ambiente, valores=None, erros=None):
        """Vinculos ordenados com padroes resolvidos para exibicao; valida pode_executar.

        valores/erros (opcionais) reapresentam um POST com erro. Valores e padroes de
        parametros sensiveis nunca sao devolvidos.
        """
        script, amb = self._autorizar(ctx, script_id, ambiente)
        valores = valores or {}
        erros = erros or {}
        campos = []
        for v in _ordenados(self._vinculos(script["id"])):
            codigo = v["codigo"]
            sensivel = v.get("sensivel") == "S"
            tipo = v.get("tipo_componente")
            opcoes = _opcoes(v) if tipo == "SELECT" else []
            padrao_real = self._padrao_exibicao(v)
            padrao = None if sensivel else padrao_real
            enviado = _ultimo(valores.get(codigo))
            if tipo == "CHECKBOX":
                if codigo in valores:
                    marcado = isinstance(enviado, str) and enviado.strip().lower() in ("true", "1")
                else:
                    marcado = padrao is True
                padrao_texto = None if padrao is None else (u"Marcado" if padrao else u"Desmarcado")
                valor = None
            else:
                marcado = False
                padrao_texto = dict(opcoes).get(padrao, padrao) if padrao is not None else None
                valor = None if sensivel or not isinstance(enviado, str) else enviado
            campos.append({
                "codigo": codigo,
                "nome": "p_" + codigo,
                "label": v.get("label") or codigo,
                "descricao": v.get("descricao") or "",
                "tipo": tipo,
                "obrigatorio": v.get("obrigatorio") == "S",
                "sensivel": sensivel,
                "opcoes": opcoes,
                "padrao": padrao,
                "tem_padrao": padrao_real is not None,
                "padrao_texto": padrao_texto,
                "valor": valor,
                "marcado": marcado,
                "erro": erros.get(codigo),
            })
        prioridades = [(p, ROTULOS_PRIORIDADE[p]) for p in rbac.PRIORIDADES if rbac.prioridade_permitida(ctx, p)]
        return {
            "script": {"id": script["id"], "nome": script["nome"], "descricao": script.get("descricao") or "",
                       "tipo_param": script["tipo_param"]},
            "ambiente": {"id": amb["id"], "nome": amb["nome"], "descricao": amb.get("descricao") or "",
                         "producao": amb["nome"] == AMBIENTE_PRODUCAO},
            "campos": campos,
            "prioridades": prioridades,
        }

    # ------------------------------------------------------------- validacao

    def _prioridade(self, ctx, valor, erros):
        valor = _ultimo(valor)
        if valor is None or valor == "":
            prioridade = PRIORIDADE_PADRAO
        else:
            prioridade = _id(valor.strip() if isinstance(valor, str) else valor)
        if prioridade is not None and rbac.prioridade_permitida(ctx, prioridade):
            return prioridade
        if prioridade == rbac.PRIORIDADE_ADMIN:
            erros[CAMPO_PRIORIDADE] = u"A prioridade 1 é exclusiva de administradores."
        else:
            erros[CAMPO_PRIORIDADE] = u"Selecione uma prioridade entre 1 e 4."
        return None

    def _agendamento(self, valor, agora, erros):
        valor = _ultimo(valor)
        if valor is None or (isinstance(valor, str) and valor.strip() == ""):
            return None
        data = None
        if isinstance(valor, str):
            for formato in _FORMATOS_AGENDAMENTO:
                try:
                    data = datetime.datetime.strptime(valor.strip(), formato)
                    break
                except ValueError:
                    continue
        if data is None:
            erros[CAMPO_AGENDAMENTO] = u"Informe uma data e hora válidas para o agendamento."
            return None
        # O campo do navegador tem precisao de minuto: o minuto corrente conta como "agora".
        if data < agora.replace(second=0, microsecond=0):
            erros[CAMPO_AGENDAMENTO] = u"O agendamento não pode estar no passado."
            return None
        return data.replace(microsecond=0)

    def _base_exibicao(self, ctx):
        """Diretorio base exibido no argv: caminho real so para admin (README §8.5)."""
        return os.path.realpath(self._base) if ctx.get("is_admin") is True else None

    def _compilar(self, ctx, script, amb, respostas, agora, erros):
        """Valida o script no no web (path_guard) e compila o snapshot v2, acumulando erros por campo."""
        vinculos = self._vinculos(script["id"])
        codigos = set(v["codigo"] for v in vinculos)
        if not isinstance(respostas, dict):
            respostas = {}
        respostas = dict((k, _ultimo(v)) for k, v in respostas.items() if k in codigos)

        # A validacao definitiva repete-se no agente, contra o diretorio base dele (README §8.4).
        try:
            path_guard.resolver(self._base, script["path_file"], self._owner_uids)
        except (path_guard.PathGuardErro, OSError) as e:
            self._log.warning("path_guard rejeitou o script (login=%s script_id=%s codigo=%s)",
                              ctx["login"], script["id"], getattr(e, "codigo", type(e).__name__),
                              extra={"acao": "TICKET_CRIAR"})
            erros[CAMPO_GERAL] = MSG_SCRIPT_INDISPONIVEL

        snapshot, resolvidos, erros_param = params_compiler.compilar_snapshot(
            script, vinculos, respostas, agora)
        for codigo, mensagem in erros_param.items():
            erros.setdefault(codigo, mensagem)
        if erros:
            self._log.info("validacao do disparo com erros (login=%s script_id=%s ambiente=%s campos=%s)",
                           ctx["login"], script["id"], amb["nome"], ",".join(sorted(erros)),
                           extra={"acao": "TICKET_CRIAR"})
            return None, None, vinculos
        return snapshot, resolvidos, vinculos

    # --------------------------------------------------------------- acoes

    def previa(self, ctx, script_id, ambiente, respostas):
        """Compila sem gravar e devolve (argv_exibicao | None, erros_por_campo); sensiveis mascarados."""
        script, amb = self._autorizar(ctx, script_id, ambiente)
        erros = collections.OrderedDict()
        snapshot, _resolvidos, _vinculos = self._compilar(ctx, script, amb, respostas,
                                                          self._tickets.agora(), erros)
        if snapshot is None:
            return None, dict(erros)
        return params_compiler.argv_para_exibicao(json.loads(snapshot), self._base_exibicao(ctx)), {}

    def criar_ticket(self, ctx, ip, script_id, ambiente, respostas, prioridade, scheduled_at,
                     reexecucao_de=None):
        """Cria o ticket (README §5.4). Retorna (ticket_id | None, erros_por_campo).

        reexecucao_de (opcional) vincula o novo ticket ao original (README §5.5), exigindo
        as mesmas regras de reexecutar e o mesmo script/ambiente. Lanca AcessoNegado quando
        pode_executar nega. A auditoria e gravada pelo repositorio na mesma transacao do INSERT.
        """
        parent_id = None
        if reexecucao_de not in (None, ""):
            original = self._ticket_reexecutavel(ctx, reexecucao_de)
            if str(original["script_id"]) != str(script_id) or original["ambiente"] != ambiente:
                self._negar(ctx, "REEXECUCAO_DIVERGENTE", script_id, ambiente)
            parent_id = original["id"]
        script, amb = self._autorizar(ctx, script_id, ambiente)
        agora = self._tickets.agora()
        erros = collections.OrderedDict()
        prio = self._prioridade(ctx, prioridade, erros)
        sched = self._agendamento(scheduled_at, agora, erros)
        snapshot, resolvidos, vinculos = self._compilar(ctx, script, amb, respostas, agora, erros)
        if erros:
            return None, dict(erros)
        return self._gravar(ctx, ip, script, amb, prio, sched, snapshot, resolvidos, vinculos, parent_id)

    def _gravar(self, ctx, ip, script, amb, prio, sched, snapshot, resolvidos, vinculos, parent_id):
        acao = "TICKET_CRIAR" if parent_id is None else "TICKET_REEXECUTAR"
        ticket = {
            "script_id": script["id"],
            "ambiente": amb["nome"],
            "solicitante": ctx["login"],
            "ip_origem": ip,
            "status": "PENDING",
            "prioridade": prio,
            "parametros_enviados": snapshot,
            "scheduled_at": sched,
            "parent_ticket_id": parent_id,
        }
        linhas = []
        for v in _ordenados(vinculos):
            valor = resolvidos.get(v["codigo"])
            if valor is not None:
                linhas.append({"parametro_id": v["parametro_id"], "valor_resposta": _texto_resposta(valor)})
        try:
            ticket_id = self._tickets.criar(ticket, linhas)
        except RepoErro:
            self._log.exception("falha ao gravar ticket (login=%s script_id=%s ambiente=%s pai=%s)",
                                ctx["login"], script["id"], amb["nome"], parent_id, extra={"acao": acao})
            return None, {CAMPO_GERAL: MSG_FALHA_CRIAR}
        self._log.info("ticket criado (ticket=%s login=%s script_id=%s ambiente=%s prioridade=%s pai=%s ip=%s)",
                       ticket_id, ctx["login"], script["id"], amb["nome"], prio, parent_id, ip,
                       extra={"acao": acao})
        return ticket_id, {}

    # ------------------------------------------------------------ consulta

    def pode_consultar(self, ctx):
        """Acesso a lista de tickets: VER_LOGS (escopo de ambientes) ou EXEC_SCRIPT (proprios)."""
        return rbac.tem_func(ctx, "VER_LOGS") or rbac.tem_func(ctx, "EXEC_SCRIPT")

    def _proprio(self, ctx, ticket):
        return rbac.tem_func(ctx, "EXEC_SCRIPT") and ticket.get("solicitante") == ctx.get("login")

    def _pode_ver(self, ctx, ticket):
        return self._proprio(ctx, ticket) or rbac.pode_ver_ticket(ctx, ticket)

    def _ticket_visivel(self, ctx, ticket_id, acao):
        """Ticket existente e visivel; fora do escopo e tratado como inexistente (404, nao 403)."""
        tid = _id(ticket_id)
        if tid is None:
            raise RepoNaoEncontrado("ticket invalido")
        ticket = self._tickets.obter(tid)
        if not self._pode_ver(ctx, ticket):
            self._log.warning("ticket fora do escopo (login=%s ticket=%s ambiente=%s)",
                              ctx.get("login"), tid, ticket.get("ambiente"), extra={"acao": acao})
            raise RepoNaoEncontrado("ticket fora do escopo")
        return ticket

    def _nomes_scripts(self):
        pagina = self._catalogo.scripts_listar(pagina=1, tamanho=_SCRIPTS_MAX)
        return dict((s["id"], s["nome"]) for s in pagina["itens"])

    def opcoes_filtro(self, ctx):
        """Opcoes dos selects de filtro: ambientes visiveis ao perfil e scripts do catalogo."""
        if rbac.tem_func(ctx, "VER_LOGS") and ctx.get("is_admin") is True:
            pagina = self._catalogo.ambientes_listar(pagina=1, tamanho=_AMBIENTES_MAX)
            ambientes = sorted(a["nome"] for a in pagina["itens"])
        else:
            ambientes = sorted(ctx.get("ambientes") or ())
        scripts = sorted(self._nomes_scripts().items(), key=lambda par: (par[1], par[0]))
        return {"ambientes": ambientes, "scripts": scripts, "status": list(STATUS_TICKET),
                "origens": list(ORIGENS)}

    def listar(self, ctx, filtros, pagina, tamanho):
        """Lista paginada no escopo do perfil (README §4.3.C).

        Com VER_LOGS: ambientes autorizados (admin: todos). Sem VER_LOGS: apenas os
        tickets do proprio solicitante. filtros passa por normalizar_filtros.
        """
        if not self.pode_consultar(ctx):
            self._negar(ctx, rbac.Motivo.SEM_FUNC, None, None)
        repo_filtros = _filtros_repo(normalizar_filtros(filtros))
        escopo = None
        vazio = {"itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        if rbac.tem_func(ctx, "VER_LOGS"):
            if ctx.get("is_admin") is not True:
                escopo = sorted(ctx.get("ambientes") or ())
                if not escopo:
                    return vazio
        else:
            if repo_filtros.get("solicitante", ctx["login"]) != ctx["login"]:
                return vazio
            repo_filtros["solicitante"] = ctx["login"]
        resultado = self._tickets.listar(filtros=repo_filtros, pagina=pagina, tamanho=tamanho,
                                         escopo_ambientes=escopo)
        info = ui_helpers.paginacao_info(pagina, tamanho, resultado["total"])
        if not resultado["itens"] and info["pagina"] != resultado["pagina"]:
            resultado = self._tickets.listar(filtros=repo_filtros, pagina=info["pagina"], tamanho=tamanho,
                                             escopo_ambientes=escopo)
        agora = self._tickets.agora()
        nomes = self._nomes_scripts()
        itens = []
        for t in resultado["itens"]:
            itens.append({
                "id": t["id"],
                "script_nome": nomes.get(t["script_id"], "#%s" % t["script_id"]),
                "ambiente": t["ambiente"],
                "status": t["status"],
                "status_motivo": t.get("status_motivo"),
                "descricao_motivo": ui_helpers.descricao_motivo(t.get("status_motivo")),
                "cancel_requested": t.get("cancel_requested") == "S",
                "prioridade": t["prioridade"],
                "solicitante": t["solicitante"],
                "origem": "agendamento" if t.get("agendamento_id") is not None else "manual",
                "created_at": t.get("created_at"),
                "started_at": t.get("started_at"),
                "duracao": _duracao(t, agora),
            })
        return {"itens": itens, "total": resultado["total"], "pagina": resultado["pagina"],
                "tamanho": resultado["tamanho"]}

    def _respostas_exibicao(self, ticket_id, snap):
        sensiveis = set((snap or {}).get("sensiveis") or ())
        linhas = []
        for r in self._tickets.respostas(ticket_id):
            try:
                prm = self._catalogo.parametros_obter(r["parametro_id"])
                codigo, rotulo = prm["codigo"], prm.get("label") or prm["codigo"]
                sensivel = prm.get("sensivel") == "S" or codigo in sensiveis
            except RepoNaoEncontrado:
                codigo = rotulo = "#%s" % r["parametro_id"]
                sensivel = True
            valor = r.get("valor_resposta")
            linhas.append({"codigo": codigo, "rotulo": rotulo, "sensivel": sensivel,
                           "valor": params_compiler.MASCARA if sensivel and valor not in (None, "") else valor})
        return linhas

    def _pode_reexecutar_regra(self, ctx, ticket):
        # README §4.3.C: EXEC_SCRIPT reexecuta tickets proprios; admin, qualquer ticket visivel.
        return (ctx.get("is_admin") is True and rbac.tem_func(ctx, "EXEC_SCRIPT")) or self._proprio(ctx, ticket)

    def _pode_executar_vigente(self, ctx, ticket):
        try:
            script = self._catalogo.scripts_obter(ticket["script_id"])
        except RepoNaoEncontrado:
            return False
        amb = self._ambiente_por_nome(ticket["ambiente"])
        if amb is None:
            return False
        ok, _motivo = rbac.pode_executar(ctx, script, amb, self._catalogo.homologacao_obter(script["id"]))
        return ok

    def detalhe(self, ctx, ticket_id):
        """Ticket visivel com snapshot (sensiveis mascarados), respostas, cadeia e acoes permitidas.

        Lanca RepoNaoEncontrado se nao existir ou estiver fora do escopo do perfil.
        """
        ticket = self._ticket_visivel(ctx, ticket_id, "TICKET_DETALHE")
        snap = _snapshot(ticket)
        try:
            script_nome = self._catalogo.scripts_obter(ticket["script_id"])["nome"]
        except RepoNaoEncontrado:
            script_nome = (snap or {}).get("script_nome") or "#%s" % ticket["script_id"]

        pai = None
        if ticket.get("parent_ticket_id") is not None:
            try:
                original = self._tickets.obter(ticket["parent_ticket_id"])
            except RepoNaoEncontrado:
                original = None
            if original is not None and self._pode_ver(ctx, original):
                pai = {"id": original["id"], "status": original["status"]}
        filhos = [{"id": f["id"], "status": f["status"]}
                  for f in self._tickets.listar(filtros={"parent_ticket_id": ticket["id"]}, pagina=1,
                                                tamanho=_FILHOS_MAX)["itens"]
                  if self._pode_ver(ctx, f)]
        filhos.sort(key=lambda f: f["id"])

        status = ticket["status"]
        cancel_requested = ticket.get("cancel_requested") == "S"
        pode_cancelar = (status in STATUS_CANCELAVEIS and not cancel_requested
                         and rbac.pode_cancelar(ctx, ticket))
        pode_reexecutar = (status in STATUS_TERMINAIS and self._pode_reexecutar_regra(ctx, ticket)
                           and self._pode_executar_vigente(ctx, ticket))
        argv = _argv_exibicao(snap, self._base_exibicao(ctx))
        snapshot = None
        if snap is not None:
            snapshot = dict((k, snap.get(k)) for k in ("versao", "interpretador", "path_file", "tipo_param",
                                                       "compilado_em"))
        return {
            "id": ticket["id"],
            "script_id": ticket["script_id"],
            "script_nome": script_nome,
            "ambiente": ticket["ambiente"],
            "status": status,
            "status_motivo": ticket.get("status_motivo"),
            "descricao_motivo": ui_helpers.descricao_motivo(ticket.get("status_motivo")),
            "return_code": ticket.get("return_code"),
            "cancel_requested": cancel_requested,
            "prioridade": ticket["prioridade"],
            "solicitante": ticket["solicitante"],
            "origem": "agendamento" if ticket.get("agendamento_id") is not None else "manual",
            "agendamento_id": ticket.get("agendamento_id"),
            "agente_id": ticket.get("agente_id"),
            "process_id": ticket.get("process_id"),
            "created_at": ticket.get("created_at"),
            "scheduled_at": ticket.get("scheduled_at"),
            "started_at": ticket.get("started_at"),
            "heartbeat_at": ticket.get("heartbeat_at"),
            "finished_at": ticket.get("finished_at"),
            "duracao": _duracao(ticket, self._tickets.agora()),
            "log_truncado": ticket.get("log_truncado") == "S",
            "snapshot": snapshot,
            "argv_para_exibicao": argv,
            "comando_exibicao": " ".join(shlex.quote(str(t)) for t in argv) if argv else None,
            "respostas": self._respostas_exibicao(ticket["id"], snap),
            "pai": pai,
            "filhos": filhos,
            "pode_cancelar": pode_cancelar,
            "pode_reexecutar": pode_reexecutar,
        }

    # ------------------------------------------------------------------ log

    def ler_log(self, ctx, ticket_id, offset):
        """Bloco do log a partir de offset (caracteres, base 0), no maximo LOG_MAX_CHARS.

        Retorna {texto, proximo_offset, terminal, truncado, status}. Lanca OffsetInvalido e
        RepoNaoEncontrado (inexistente ou fora do escopo do perfil).
        """
        off = _offset(offset)
        ticket = self._ticket_visivel(ctx, ticket_id, "LOG_LER")
        texto, proximo, terminal, truncado = self._tickets.log_ler(ticket["id"], off, LOG_MAX_CHARS)
        status = ticket["status"]
        if terminal and status not in STATUS_TERMINAIS:
            # O ticket terminou entre a checagem de escopo e a leitura.
            status = self._tickets.obter(ticket["id"])["status"]
        return {"texto": texto, "proximo_offset": proximo, "terminal": bool(terminal),
                "truncado": bool(truncado), "status": status}

    def blocos_log(self, ctx, ticket_id):
        """Valida o escopo e retorna (id, gerador de blocos do log integral via log_ler).

        A validacao ocorre antes do streaming; uma falha de leitura no meio encerra o
        gerador com MARCADOR_DOWNLOAD_INTERROMPIDO, para o arquivo nao parecer completo.
        """
        ticket = self._ticket_visivel(ctx, ticket_id, "LOG_BAIXAR")
        tid = ticket["id"]
        self._log.info("download de log (login=%s ticket=%s)", ctx.get("login"), tid,
                       extra={"acao": "LOG_BAIXAR"})

        def gerar():
            off = 0
            while True:
                try:
                    texto, off, _terminal, _truncado = self._tickets.log_ler(tid, off, LOG_MAX_CHARS)
                except RepoErro:
                    self._log.exception("falha na leitura do log para download (ticket=%s offset=%s)", tid, off,
                                        extra={"acao": "LOG_BAIXAR"})
                    yield MARCADOR_DOWNLOAD_INTERROMPIDO
                    return
                if not texto:
                    return
                yield texto

        return tid, gerar()

    # --------------------------------------------------- cancelar/reexecutar

    def cancelar(self, ctx, ip, ticket_id):
        """Cancelamento pelo no web (README §5.6) com auditoria TICKET_CANCELAR no repositorio.

        Retorna 'TERMINAL' | 'CANCELADO' | 'SINALIZADO' (mensagens em MSG_CANCELAMENTO).
        Lanca RepoNaoEncontrado (fora do escopo) e AcessoNegado (sem CANC_TICKET/proprio).
        """
        ticket = self._ticket_visivel(ctx, ticket_id, "TICKET_CANCELAR")
        if not rbac.pode_cancelar(ctx, ticket):
            self._negar(ctx, "SEM_CANCELAMENTO", ticket["script_id"], ticket["ambiente"])
        try:
            resultado = self._tickets.solicitar_cancelamento(ticket["id"], ctx["login"], ip)
        except RepoErro:
            self._log.exception("falha ao cancelar ticket (ticket=%s login=%s)", ticket["id"], ctx["login"],
                                extra={"acao": "TICKET_CANCELAR"})
            raise
        self._log.info("cancelamento de ticket (ticket=%s login=%s resultado=%s ip=%s)",
                       ticket["id"], ctx["login"], resultado, ip, extra={"acao": "TICKET_CANCELAR"})
        return resultado

    def _ticket_reexecutavel(self, ctx, ticket_id):
        ticket = self._ticket_visivel(ctx, ticket_id, "TICKET_REEXECUTAR")
        if ticket["status"] not in STATUS_TERMINAIS:
            self._negar(ctx, "TICKET_NAO_TERMINAL", ticket["script_id"], ticket["ambiente"])
        if not self._pode_reexecutar_regra(ctx, ticket):
            self._negar(ctx, rbac.Motivo.SEM_FUNC, ticket["script_id"], ticket["ambiente"])
        return ticket

    def _respostas_originais(self, ticket, vinculos):
        """Respostas resolvidas do original (tbsss_ticket_resp) indexadas pelo codigo vigente."""
        codigos = dict((v["parametro_id"], v["codigo"]) for v in vinculos)
        respostas = {}
        for r in self._tickets.respostas(ticket["id"]):
            codigo = codigos.get(r["parametro_id"])
            if codigo is not None and r.get("valor_resposta") is not None:
                respostas[codigo] = r["valor_resposta"]
        return respostas

    def _recompilar(self, ctx, ticket):
        script, amb = self._autorizar(ctx, ticket["script_id"], ticket["ambiente"])
        respostas = self._respostas_originais(ticket, self._vinculos(script["id"]))
        agora = self._tickets.agora()
        erros = collections.OrderedDict()
        prio = self._prioridade(ctx, str(ticket["prioridade"]), erros)
        snapshot, resolvidos, vinculos = self._compilar(ctx, script, amb, respostas, agora, erros)
        return script, amb, prio, respostas, snapshot, resolvidos, vinculos, erros

    def reexecutar(self, ctx, ip, ticket_id):
        """Novo ticket com parent_ticket_id, recompilado contra o catalogo vigente (README §5.5).

        Retorna o novo ID. Lanca RepoNaoEncontrado (fora do escopo), AcessoNegado (regra de
        reexecucao ou pode_executar vigente) e ErroReexecucao (recompilacao ou gravacao).
        """
        original = self._ticket_reexecutavel(ctx, ticket_id)
        script, amb, prio, _resp, snapshot, resolvidos, vinculos, erros = self._recompilar(ctx, original)
        if erros:
            raise ErroReexecucao(original["id"], dict(erros))
        novo_id, erros = self._gravar(ctx, ip, script, amb, prio, None, snapshot, resolvidos, vinculos,
                                      original["id"])
        if novo_id is None:
            raise ErroReexecucao(original["id"], erros)
        return novo_id

    def preparar_reexecucao(self, ctx, ticket_id):
        """Dados para reabrir o questionario a partir de um ticket (fallback da reexecucao).

        Retorna {ticket_id, script_id, ambiente, prioridade, valores, erros}; valores de
        parametros sensiveis nunca sao devolvidos.
        """
        original = self._ticket_reexecutavel(ctx, ticket_id)
        script, amb, prio, respostas, _snap, _resolv, vinculos, erros = self._recompilar(ctx, original)
        sensiveis = set(v["codigo"] for v in vinculos if v.get("sensivel") == "S")
        return {
            "ticket_id": original["id"],
            "script_id": script["id"],
            "ambiente": amb["nome"],
            "prioridade": str(prio if prio is not None else PRIORIDADE_PADRAO),
            "valores": dict((k, v) for k, v in respostas.items() if k not in sensiveis),
            "erros": dict(erros),
        }

_padrao = None
_lock_padrao = threading.Lock()


def _servico():
    global _padrao
    with _lock_padrao:
        if _padrao is None:
            from gluon import current
            import sss_logging
            fabrica = current.repo_factory
            cfg = current.sss_cfg
            _padrao = ServicoTicket(
                catalogo=fabrica.obter("catalogo"),
                tickets=fabrica.obter("tickets"),
                base_script_dir=cfg.agent.base_script_dir,
                script_owner_uids=cfg.agent.script_owner_uids,
                log=sss_logging.obter_logger("sss_web", cfg),
            )
        return _padrao


def scripts_disponiveis(ctx):
    """Scripts executaveis agrupados (servico padrao do processo web)."""
    return _servico().scripts_disponiveis(ctx)


def ambientes_disponiveis(ctx, script_id):
    """Ambientes homologados e autorizados para o script (servico padrao)."""
    return _servico().ambientes_disponiveis(ctx, script_id)


def preparar_formulario(ctx, script_id, ambiente, valores=None, erros=None):
    """Questionario do script no ambiente (servico padrao)."""
    return _servico().preparar_formulario(ctx, script_id, ambiente, valores, erros)


def previa(ctx, script_id, ambiente, respostas):
    """Previa do argv mascarado (servico padrao)."""
    return _servico().previa(ctx, script_id, ambiente, respostas)


def criar_ticket(ctx, ip, script_id, ambiente, respostas, prioridade, scheduled_at, reexecucao_de=None):
    """Criacao do ticket (servico padrao)."""
    return _servico().criar_ticket(ctx, ip, script_id, ambiente, respostas, prioridade, scheduled_at,
                                   reexecucao_de)


def pode_consultar(ctx):
    """Acesso a lista de tickets (servico padrao)."""
    return _servico().pode_consultar(ctx)


def opcoes_filtro(ctx):
    """Opcoes dos filtros da lista de tickets (servico padrao)."""
    return _servico().opcoes_filtro(ctx)


def listar(ctx, filtros, pagina, tamanho):
    """Lista de tickets no escopo do perfil (servico padrao)."""
    return _servico().listar(ctx, filtros, pagina, tamanho)


def detalhe(ctx, ticket_id):
    """Detalhe do ticket visivel (servico padrao)."""
    return _servico().detalhe(ctx, ticket_id)


def cancelar(ctx, ip, ticket_id):
    """Cancelamento pelo no web (servico padrao)."""
    return _servico().cancelar(ctx, ip, ticket_id)


def reexecutar(ctx, ip, ticket_id):
    """Reexecucao do ticket (servico padrao)."""
    return _servico().reexecutar(ctx, ip, ticket_id)


def preparar_reexecucao(ctx, ticket_id):
    """Questionario pre-preenchido para reexecucao com erro (servico padrao)."""
    return _servico().preparar_reexecucao(ctx, ticket_id)


def ler_log(ctx, ticket_id, offset):
    """Bloco incremental do log do ticket visivel (servico padrao)."""
    return _servico().ler_log(ctx, ticket_id, offset)


def blocos_log(ctx, ticket_id):
    """Gerador do log integral do ticket visivel para download (servico padrao)."""
    return _servico().blocos_log(ctx, ticket_id)
