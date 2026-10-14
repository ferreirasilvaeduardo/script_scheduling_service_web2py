# -*- coding: utf-8 -*-
"""Disparo manual de script: formulario, previa e criacao de ticket (README §5.3, §5.4, §6).

O servidor e a autoridade: script, ambiente e homologacao sao sempre recarregados do
repositorio e reautorizados com rbac.pode_executar. Valores de parametros nunca vao para
o log; so codigos de campo.
"""
import collections
import datetime
import json
import re
import threading

import params_compiler
import path_guard
import rbac
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


class AcessoNegado(Exception):
    """Execucao nao autorizada; o motivo (rbac.Motivo) e destinado apenas ao log."""

    def __init__(self, motivo):
        Exception.__init__(self, motivo)
        self.motivo = motivo


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

    def _compilar(self, ctx, script, amb, respostas, agora, erros):
        """Resolve script_real e compila o snapshot, acumulando erros por campo."""
        vinculos = self._vinculos(script["id"])
        codigos = set(v["codigo"] for v in vinculos)
        if not isinstance(respostas, dict):
            respostas = {}
        respostas = dict((k, _ultimo(v)) for k, v in respostas.items() if k in codigos)

        script_real = None
        try:
            script_real = path_guard.resolver(self._base, script["path_file"], self._owner_uids)
        except (path_guard.PathGuardErro, OSError) as e:
            self._log.warning("path_guard rejeitou o script (login=%s script_id=%s codigo=%s)",
                              ctx["login"], script["id"], getattr(e, "codigo", type(e).__name__),
                              extra={"acao": "TICKET_CRIAR"})
            erros[CAMPO_GERAL] = MSG_SCRIPT_INDISPONIVEL

        snapshot, resolvidos, erros_param = params_compiler.compilar_snapshot(
            script, vinculos, respostas, script_real or "", agora)
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
        return params_compiler.argv_para_exibicao(json.loads(snapshot)), {}

    def criar_ticket(self, ctx, ip, script_id, ambiente, respostas, prioridade, scheduled_at):
        """Cria o ticket (README §5.4). Retorna (ticket_id | None, erros_por_campo).

        Lanca AcessoNegado quando pode_executar nega. A auditoria TICKET_CRIAR e gravada
        pelo repositorio na mesma transacao do INSERT.
        """
        script, amb = self._autorizar(ctx, script_id, ambiente)
        agora = self._tickets.agora()
        erros = collections.OrderedDict()
        prio = self._prioridade(ctx, prioridade, erros)
        sched = self._agendamento(scheduled_at, agora, erros)
        snapshot, resolvidos, vinculos = self._compilar(ctx, script, amb, respostas, agora, erros)
        if erros:
            return None, dict(erros)

        ticket = {
            "script_id": script["id"],
            "ambiente": amb["nome"],
            "solicitante": ctx["login"],
            "ip_origem": ip,
            "status": "PENDING",
            "prioridade": prio,
            "parametros_enviados": snapshot,
            "scheduled_at": sched,
        }
        linhas = []
        for v in _ordenados(vinculos):
            valor = resolvidos.get(v["codigo"])
            if valor is not None:
                linhas.append({"parametro_id": v["parametro_id"], "valor_resposta": _texto_resposta(valor)})
        try:
            ticket_id = self._tickets.criar(ticket, linhas)
        except RepoErro:
            self._log.exception("falha ao gravar ticket (login=%s script_id=%s ambiente=%s)",
                                ctx["login"], script["id"], amb["nome"], extra={"acao": "TICKET_CRIAR"})
            return None, {CAMPO_GERAL: MSG_FALHA_CRIAR}
        self._log.info("ticket criado (ticket=%s login=%s script_id=%s ambiente=%s prioridade=%s ip=%s)",
                       ticket_id, ctx["login"], script["id"], amb["nome"], prio, ip,
                       extra={"acao": "TICKET_CRIAR"})
        return ticket_id, {}

    def ticket_resumo(self, ctx, ticket_id):
        """Resumo do ticket para o placeholder de detalhe: VER_LOGS no ambiente ou ticket proprio.

        Lanca RepoNaoEncontrado se nao existir e AcessoNegado se nao puder ver.
        """
        tid = _id(ticket_id)
        if tid is None:
            raise RepoNaoEncontrado("ticket invalido")
        ticket = self._tickets.obter(tid)
        proprio = rbac.tem_func(ctx, "EXEC_SCRIPT") and ticket.get("solicitante") == ctx.get("login")
        if not (proprio or rbac.pode_ver_ticket(ctx, ticket)):
            self._negar(ctx, "SEM_VISAO_TICKET", ticket.get("script_id"), ticket.get("ambiente"))
        try:
            script_nome = self._catalogo.scripts_obter(ticket["script_id"])["nome"]
        except RepoNaoEncontrado:
            script_nome = "#%s" % ticket["script_id"]
        return {
            "id": ticket["id"],
            "script_nome": script_nome,
            "ambiente": ticket["ambiente"],
            "status": ticket["status"],
            "prioridade": ticket["prioridade"],
            "solicitante": ticket["solicitante"],
            "scheduled_at": ticket.get("scheduled_at"),
            "created_at": ticket.get("created_at"),
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


def criar_ticket(ctx, ip, script_id, ambiente, respostas, prioridade, scheduled_at):
    """Criacao do ticket (servico padrao)."""
    return _servico().criar_ticket(ctx, ip, script_id, ambiente, respostas, prioridade, scheduled_at)


def ticket_resumo(ctx, ticket_id):
    """Resumo do ticket para o placeholder de detalhe (servico padrao)."""
    return _servico().ticket_resumo(ctx, ticket_id)
