# -*- coding: utf-8 -*-
"""Regras de agendamento recorrente (README §4.3.C CAD_AGENDAMENTOS, §7, §10 tabela 12).

Segue docs/PADRAO_CRUD_ADMIN.md: nao importa gluon, recebe ctx e ip por parametro e o servico
padrao do processo web e criado sob demanda (_servico). O relogio e injetado: na web, o
SYSDATE do repositorio de tickets; nos testes, um relogio fixo.

A regra roda sob os privilegios de quem a definiu por ultimo (README §10): toda inclusao ou
edicao grava usuario_id = editor, que precisa de pode_executar vigente para o script e o
ambiente. Valores de parametros sensiveis nunca vao para o log, a auditoria ou o HTML.
"""
import collections
import datetime
import json
import re
import threading

import admin_crud
import cron_parser
import params_compiler
import rbac
import recurrence
import ui_helpers
from admin_crud import CAMPO_GERAL, OperacaoNegada
from cron_parser import CronErro
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao
from ticket_service import AcessoNegado as DisparoNegado

FUNCIONALIDADE = "CAD_AGENDAMENTOS"
TAMANHO_NOME = 60
QTD_PREVIA = 5
PRIORIDADE_PADRAO = 2
MASCARA = u"******"
FORMATO_CAMPO_DATA = "%Y-%m-%dT%H:%M"

ROTULOS_TIPO = collections.OrderedDict((
    ("UNICA", u"Única"),
    ("DIARIA", u"Diária"),
    ("SEMANAL", u"Semanal"),
    ("MENSAL", u"Mensal"),
    ("CRON", u"Expressão CRON"),
))
# ISO 1-7 (1 = segunda), README §7.2.
DIAS_SEMANA = ((1, u"seg", u"Segunda"), (2, u"ter", u"Terça"), (3, u"qua", u"Quarta"),
               (4, u"qui", u"Quinta"), (5, u"sex", u"Sexta"), (6, u"sáb", u"Sábado"),
               (7, u"dom", u"Domingo"))
_ABREV_DIA = dict((n, abrev) for n, abrev, _nome in DIAS_SEMANA)

# Textos dos motivos de pausa (decisao D4 do F5.2; README §7.5).
MOTIVOS_PAUSA = {
    "MANUAL": u"Pausado manualmente",
    "CONCLUIDO": u"Concluída",
    "USUARIO_INATIVO": u"Responsável inativo",
    "SEM_PERMISSAO": u"Responsável sem permissão",
    "SCRIPT_INATIVO": u"Script inativo",
    "AMBIENTE_INATIVO": u"Ambiente inativo",
    "PARAM_INVALIDO": u"Parâmetros inválidos",
    "CRON_INVALIDO": u"Expressão CRON inválida",
}

MSG_NOME_OBRIGATORIO = u"Informe o nome da regra."
MSG_NOME_TAMANHO = u"O nome deve ter no máximo %d caracteres." % TAMANHO_NOME
MSG_TIPO = u"Selecione o tipo de recorrência."
MSG_DATA_INVALIDA = u"Informe uma data e hora válidas."
MSG_INICIO_UNICA = u"Informe a data e hora da execução."
MSG_PRIORIDADE = u"Selecione uma prioridade entre 1 e 4."
MSG_PRIORIDADE_ADMIN = u"A prioridade 1 é exclusiva de administradores."
MSG_SEM_PROXIMA = (u"A regra não tem próxima execução. Confira a data de início, a data de fim "
                   u"e a recorrência.")
MSG_SEM_PERMISSAO = (u"Você não tem permissão para executar este script neste ambiente. "
                     u"A regra roda com as permissões de quem a salva; ela não foi alterada.")
MSG_JA_PAUSADA = u"A regra já está pausada."
MSG_JA_ATIVA = u"A regra já está ativa."
MSG_RETOMAR_SEM_PROXIMA = (u"A regra não tem próxima execução e não pode ser retomada. "
                           u"Edite as datas ou a recorrência.")

# Campos editaveis que compoem a versao do formulario (concorrencia otimista, README §10).
CAMPOS_VERSAO = ("nome", "prioridade", "tipo_recorrencia", "expressao_cron", "hora_execucao",
                 "dias_semana", "dia_mes", "parametros_json", "data_inicio", "data_fim",
                 "usuario_id", "ativo", "pausa_motivo")
_CAMPOS_ESPERADO = CAMPOS_VERSAO + ("proxima_execucao",)
CAMPOS_AUDITORIA = ("nome", "script_id", "ambiente", "prioridade", "tipo_recorrencia",
                    "expressao_cron", "hora_execucao", "dias_semana", "dia_mes", "parametros",
                    "data_inicio", "data_fim")
_CAMPOS_INSERCAO = CAMPOS_AUDITORIA + ("usuario_id", "proxima_execucao")

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_AMBIENTE = re.compile(r"[A-Z0-9_]{1,30}")
# Precisao de minuto (README §7.2/§7.6): segundos ou fracoes sao recusados, nunca cortados.
_FORMATOS_DATA = ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M")
_SETA = u" → "


def _id(valor):
    valor = admin_crud.texto(valor, 11)
    if valor is None or not _RE_ID.fullmatch(valor) or int(valor) < 1:
        return None
    return int(valor)


def _ultimo(valor):
    if isinstance(valor, (list, tuple)):
        return valor[-1] if valor else None
    return valor


def _vazio(valor):
    return valor is None or (isinstance(valor, str) and valor.strip() == "")


def _data(valor):
    """(datetime sem microssegundos | None, invalido). Vazio e (None, False)."""
    texto = admin_crud.texto(valor)
    if texto is None:
        return None, False
    for formato in _FORMATOS_DATA:
        try:
            return datetime.datetime.strptime(texto, formato).replace(microsecond=0), False
        except ValueError:
            continue
    return None, True


def _dias_semana(valor):
    """Checkboxes (lista) ou texto '1,3,5' -> texto ISO ordenado sem repeticao; lixo segue para a validacao."""
    if isinstance(valor, (list, tuple)):
        itens = [v for v in valor if isinstance(v, str)]
    elif isinstance(valor, str):
        itens = valor.split(",")
    else:
        return None
    itens = [i.strip() for i in itens if i.strip()]
    if not itens:
        return None
    if all(i.isdigit() and len(i) == 1 for i in itens):
        return ",".join(str(n) for n in sorted(set(int(i) for i in itens)))
    return ",".join(itens)[:20]


def formatar_data(dt):
    """dd/mm/aaaa HH:MM; None vira '-'."""
    return dt.strftime("%d/%m/%Y %H:%M") if dt is not None else "-"


def formatar_previa(dt):
    """Data da previa com o dia da semana (ex.: 'qui, 30/04/2026 03:00')."""
    return u"%s, %s" % (_ABREV_DIA[dt.isoweekday()], formatar_data(dt))


def _valor_campo_data(dt):
    return dt.strftime(FORMATO_CAMPO_DATA) if dt is not None else ""


AGENDA_POR_REGRA = 20
AGENDA_TOTAL = 500
_AGENDA_PAGINA = 100
_AGENDA_CONTAGEM_MAX = 5000
_NOMES_DIA = (u"segunda-feira", u"terça-feira", u"quarta-feira", u"quinta-feira", u"sexta-feira", u"sábado",
              u"domingo")


def _rotulo_dia(dia, hoje):
    """'Hoje', 'Amanhã' ou 'sexta-feira, 18/10' (README §7.7)."""
    if dia == hoje:
        return u"Hoje"
    if dia == hoje + datetime.timedelta(days=1):
        return u"Amanhã"
    return u"%s, %s" % (_NOMES_DIA[dia.weekday()], dia.strftime("%d/%m"))


def descrever_regra(regra):
    """Descricao da recorrencia em portugues para a lista e a previa."""
    tipo = regra.get("tipo_recorrencia")
    hora = regra.get("hora_execucao")
    if tipo == "UNICA":
        return u"Uma vez, em %s" % formatar_data(regra.get("data_inicio"))
    if tipo == "DIARIA":
        return u"Todos os dias às %s" % hora
    if tipo == "SEMANAL":
        dias = [int(d) for d in (regra.get("dias_semana") or "").split(",") if d.strip().isdigit()]
        return u"Às %s, %s" % (hora, u", ".join(_ABREV_DIA.get(d, "?") for d in dias))
    if tipo == "MENSAL":
        return u"Às %s, no dia %s de cada mês" % (hora, regra.get("dia_mes"))
    if tipo == "CRON":
        try:
            texto = cron_parser.parse(regra.get("expressao_cron")).descrever()
        except CronErro:
            return MOTIVOS_PAUSA["CRON_INVALIDO"]
        return texto[:1].upper() + texto[1:]
    return u"-"


def situacao(registro):
    """(rotulo, motivo traduzido | None) da regra: Ativo ou Pausado + motivo."""
    if registro.get("ativo") == "S":
        return u"Ativo", None
    motivo = registro.get("pausa_motivo")
    if not motivo:
        return u"Pausado", None
    return u"Pausado", MOTIVOS_PAUSA.get(motivo, u"Motivo não catalogado (%s)" % motivo)


def normalizar_filtros(entrada):
    """Filtros da lista vindos de request.vars: nome (trecho), ambiente e ativo ('S' | 'N')."""
    entrada = entrada or {}
    filtros = {}
    nome = admin_crud.texto(entrada.get("nome"), TAMANHO_NOME)
    if nome:
        filtros["nome"] = nome
    ambiente = admin_crud.texto(entrada.get("ambiente"), 30)
    ambiente = ambiente.upper() if ambiente else None
    if ambiente and _RE_AMBIENTE.fullmatch(ambiente):
        filtros["ambiente"] = ambiente
    ativo = admin_crud.texto(entrada.get("ativo"), 1)
    if ativo in ("S", "N"):
        filtros["ativo"] = ativo
    return filtros


def _parametros(registro):
    try:
        obj = json.loads(registro.get("parametros_json") or "{}")
    except ValueError:
        return {}
    return obj if isinstance(obj, dict) else {}


def _serializar(resolvidos):
    """JSON objeto {codigo: valor} com sort_keys; CHECKBOX vira 'true'/'false', como o formulario envia."""
    obj = {}
    for codigo, valor in resolvidos.items():
        if valor is None:
            continue
        if isinstance(valor, bool):
            valor = "true" if valor else "false"
        obj[codigo] = valor
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _estado(registro, sensiveis=()):
    """Projecao serializavel dos campos da versao (datetime nao e serializavel em JSON).

    Respostas de parametros sensiveis em parametros_json entram pelo marcador (README §7.6, §10).
    """
    estado = {}
    for campo in CAMPOS_VERSAO:
        valor = registro.get(campo)
        if isinstance(valor, datetime.datetime):
            valor = valor.strftime("%Y-%m-%d %H:%M:%S")
        estado[campo] = valor
    if sensiveis:
        respostas = _parametros(registro)
        for codigo in sensiveis:
            if codigo in respostas:
                respostas[codigo] = admin_crud.marcador_sensivel(respostas[codigo])
        estado["parametros_json"] = json.dumps(respostas, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return estado


def versao(registro, sensiveis=()):
    """Versao do formulario de edicao (sha256 dos campos editaveis, sem valor sensivel)."""
    return admin_crud.versao(_estado(registro, sensiveis), CAMPOS_VERSAO)


class ServicoAgendamentos(object):
    """Regras de agendamento com repositorios, servico de disparo, relogio e log injetados."""

    def __init__(self, agendamentos, catalogo, usuarios, disparo, relogio, horizonte_dias, log):
        self._agendamentos = agendamentos
        self._catalogo = catalogo
        self._usuarios = usuarios
        self._disparo = disparo
        self._relogio = relogio
        self._horizonte = horizonte_dias
        self._log = log

    # ------------------------------------------------------------- apoio

    def _agora(self):
        return recurrence.sem_microssegundos(self._relogio())

    def _obter_visivel(self, ctx, agendamento_id):
        """Regra existente e de ambiente autorizado; fora do escopo e tratada como inexistente (404)."""
        aid = _id(agendamento_id)
        if aid is None:
            raise RepoNaoEncontrado("agendamento invalido")
        registro = self._agendamentos.obter(aid)
        if not rbac.pode_ver_ambiente(ctx, registro.get("ambiente")):
            self._log.warning("agendamento fora do escopo (login=%s agendamento=%s ambiente=%s)",
                              ctx.get("login"), aid, registro.get("ambiente"), extra={"acao": FUNCIONALIDADE})
            raise RepoNaoEncontrado("agendamento fora do escopo")
        return registro

    def _autorizar(self, ctx, script_id, ambiente):
        try:
            return self._disparo.autorizar(ctx, script_id, ambiente)
        except DisparoNegado as exc:
            self._log.warning("agendamento negado ao editor (login=%s script_id=%r ambiente=%r motivo=%s)",
                              ctx.get("login"), script_id, ambiente, exc.motivo, extra={"acao": FUNCIONALIDADE})
            raise OperacaoNegada(MSG_SEM_PERMISSAO)

    def _login(self, usuario_id, cache=None):
        if cache is not None and usuario_id in cache:
            return cache[usuario_id]
        try:
            login = self._usuarios.obter_por_id(usuario_id)["login"]
        except RepoNaoEncontrado:
            login = u"#%s" % usuario_id
        if cache is not None:
            cache[usuario_id] = login
        return login

    def _vinculos(self, script_id):
        return [v for v in self._catalogo.script_params_obter(script_id) if v.get("ativo") == "S"]

    def _codigos_sensiveis(self, script_id):
        # Todos os vinculos, ativos ou nao: parametros_json pode guardar resposta de parametro ja desativado.
        return frozenset(v["codigo"] for v in self._catalogo.script_params_obter(script_id)
                         if v.get("sensivel") == "S")

    def _regra(self, dados, agora, erros):
        """Campos de recorrencia validados (README §7.2); so os do tipo escolhido sao mantidos."""
        tipo = admin_crud.texto(dados.get("tipo_recorrencia"), 10)
        regra = {"tipo_recorrencia": tipo, "expressao_cron": None, "hora_execucao": None,
                 "dias_semana": None, "dia_mes": None}
        if tipo not in ROTULOS_TIPO:
            erros["tipo_recorrencia"] = MSG_TIPO
        if tipo in ("DIARIA", "SEMANAL", "MENSAL"):
            regra["hora_execucao"] = admin_crud.texto(dados.get("hora_execucao"), 5)
        if tipo == "SEMANAL":
            regra["dias_semana"] = _dias_semana(dados.get("dias_semana"))
        if tipo == "MENSAL":
            regra["dia_mes"] = admin_crud.texto(dados.get("dia_mes"), 2)
        if tipo == "CRON":
            regra["expressao_cron"] = admin_crud.texto(dados.get("expressao_cron"), 100)

        inicio, invalido = _data(dados.get("data_inicio"))
        if invalido:
            erros["data_inicio"] = MSG_DATA_INVALIDA
        elif inicio is None:
            if tipo == "UNICA":
                erros["data_inicio"] = MSG_INICIO_UNICA
            else:
                # Decisao D3 do F5.2: sem inicio informado, a regra vale a partir de agora.
                inicio = recurrence.truncar_segundos(agora)
        fim, invalido = _data(dados.get("data_fim"))
        if tipo == "UNICA":
            # data_fim nao se aplica a UNICA (README §7.2): ignorada e gravada nula.
            fim, invalido = None, False
        if invalido:
            erros["data_fim"] = MSG_DATA_INVALIDA
        regra["data_inicio"] = inicio
        regra["data_fim"] = fim

        if tipo in ROTULOS_TIPO:
            for campo, mensagem in recurrence.validar_regra(regra, self._horizonte).items():
                erros.setdefault(campo, mensagem)
        if regra["dia_mes"] is not None and "dia_mes" not in erros:
            regra["dia_mes"] = int(regra["dia_mes"])
        return regra

    def _proxima(self, regra, agora, erros):
        try:
            proxima = recurrence.proxima_execucao(regra, agora, self._horizonte)
        except CronErro as exc:
            erros["expressao_cron"] = exc.mensagem
            return None
        if proxima is None:
            erros[CAMPO_GERAL] = MSG_SEM_PROXIMA
        return proxima

    def _prioridade(self, ctx, valor, erros):
        texto = admin_crud.texto(_ultimo(valor), 2)
        if texto is None:
            prioridade = PRIORIDADE_PADRAO
        else:
            prioridade = int(texto) if texto.isdigit() else None
        if prioridade is not None and rbac.prioridade_permitida(ctx, prioridade):
            return prioridade
        erros["prioridade"] = MSG_PRIORIDADE_ADMIN if prioridade == rbac.PRIORIDADE_ADMIN else MSG_PRIORIDADE
        return None

    def _respostas(self, vinculos, respostas, anteriores):
        """Respostas dos vinculos ativos; na edicao, sensivel vazio mantem o valor salvo (requisito 2)."""
        codigos = set(v["codigo"] for v in vinculos)
        if not isinstance(respostas, dict):
            respostas = {}
        limpas = dict((k, _ultimo(v)) for k, v in respostas.items() if k in codigos)
        for v in vinculos:
            codigo = v["codigo"]
            if v.get("sensivel") == "S" and _vazio(limpas.get(codigo)) and codigo in anteriores:
                limpas[codigo] = anteriores[codigo]
        return limpas

    def _parametros_auditoria(self, registro, sensiveis, comparar_com=None):
        """Texto 'codigo=valor' ordenado com os sensiveis mascarados (README §4.4)."""
        params = _parametros(registro)
        anteriores = _parametros(comparar_com) if comparar_com is not None else None
        partes = []
        for codigo in sorted(params):
            valor = params[codigo]
            if codigo in sensiveis:
                alterado = anteriores is not None and anteriores.get(codigo) != valor
                valor = MASCARA + (u" (alterado)" if alterado else u"")
            partes.append(u"%s=%s" % (codigo, valor))
        return u", ".join(partes)

    def _auditavel(self, registro, sensiveis, comparar_com=None):
        aud = dict(registro)
        aud["parametros"] = self._parametros_auditoria(registro, sensiveis, comparar_com)
        for campo in ("data_inicio", "data_fim", "proxima_execucao"):
            if registro.get(campo) is not None:
                aud[campo] = formatar_data(registro[campo])
        return aud

    # ------------------------------------------------------------ consulta

    def agenda(self, ctx):
        """Agenda (README §7.7, CR-004 T3): o que vai rodar de agora ate o fim do 7o dia seguinte.

        Retorna {atrasados: [...], dias: [{rotulo, itens}], aviso_total, ocorrencias}. Cada item:
        hora, regra_id, nome, script, ambiente, recorrencia e, no ultimo item de uma regra com mais de
        AGENDA_POR_REGRA ocorrencias, 'mais' (quantas a mais no periodo). So leitura.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        agora = recurrence.truncar_segundos(self._agora())
        fim = datetime.datetime.combine(agora.date() + datetime.timedelta(days=8), datetime.time())
        escopo = None if ctx.get("is_admin") is True else sorted(ctx.get("ambientes") or ())
        regras, pagina = [], 1
        while escopo != []:
            res = self._agendamentos.listar(filtros={"ativo": "S"}, pagina=pagina, tamanho=_AGENDA_PAGINA,
                                            escopo_ambientes=escopo)
            regras.extend(res["itens"])
            if len(res["itens"]) < _AGENDA_PAGINA:
                break
            pagina += 1
        scripts = {}
        atrasados, ocorrencias = [], []
        for reg in regras:
            if reg["script_id"] not in scripts:
                try:
                    scripts[reg["script_id"]] = self._catalogo.scripts_obter(reg["script_id"])["nome"]
                except RepoNaoEncontrado:
                    scripts[reg["script_id"]] = u"#%s" % reg["script_id"]
            base = {"regra_id": reg["id"], "nome": reg["nome"], "script": scripts[reg["script_id"]],
                    "ambiente": reg["ambiente"], "recorrencia": descrever_regra(reg)}
            prox = reg.get("proxima_execucao")
            if prox is None:
                continue
            if prox < agora:
                atrasados.append(dict(base, hora=prox.strftime("%d/%m %H:%M"),
                                      frase=u"deveria ter rodado às %s; vai rodar assim que o servidor puder."
                                      % prox.strftime("%H:%M")))
            datas = []
            atual = prox if prox >= agora else None
            extra = 0
            try:
                if atual is None:
                    atual = recurrence.proxima_execucao(reg, agora, self._horizonte)
                while atual is not None and atual < fim:
                    if len(datas) < AGENDA_POR_REGRA:
                        datas.append(atual)
                    elif extra < _AGENDA_CONTAGEM_MAX:
                        extra += 1
                    else:
                        break
                    atual = recurrence.proxima_execucao(reg, atual, self._horizonte)
            except CronErro:
                continue
            for i, quando in enumerate(datas):
                item = dict(base, quando=quando, hora=quando.strftime("%H:%M"))
                if extra and i == len(datas) - 1:
                    item["mais"] = extra
                ocorrencias.append(item)
        ocorrencias.sort(key=lambda o: (o["quando"], o["regra_id"]))
        aviso_total = None
        if len(ocorrencias) > AGENDA_TOTAL:
            aviso_total = (u"Mostrando as primeiras %d execuções previstas; há mais no período." % AGENDA_TOTAL)
            ocorrencias = ocorrencias[:AGENDA_TOTAL]
        dias = collections.OrderedDict()
        for o in ocorrencias:
            dias.setdefault(o["quando"].date(), []).append(o)
        return {"atrasados": atrasados, "aviso_total": aviso_total, "total": len(ocorrencias),
                "dias": [{"rotulo": _rotulo_dia(d, agora.date()), "itens": itens} for d, itens in dias.items()]}

    def listar(self, ctx, filtros, pagina, tamanho):
        """Pagina de regras dos ambientes autorizados (admin: todos), pronta para a tabela."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        escopo = None
        if ctx.get("is_admin") is not True:
            escopo = sorted(ctx.get("ambientes") or ())
            if not escopo:
                return {"itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        resultado = self._agendamentos.listar(filtros=filtros, pagina=pagina, tamanho=tamanho,
                                              escopo_ambientes=escopo)
        scripts = {}
        logins = {}
        itens = []
        for reg in resultado["itens"]:
            sid = reg["script_id"]
            if sid not in scripts:
                try:
                    scripts[sid] = self._catalogo.scripts_obter(sid)["nome"]
                except RepoNaoEncontrado:
                    scripts[sid] = u"#%s" % sid
            rotulo, motivo = situacao(reg)
            itens.append({
                "id": reg["id"],
                "nome": reg["nome"],
                "script": scripts[sid],
                "ambiente": reg["ambiente"],
                "tipo": ROTULOS_TIPO.get(reg["tipo_recorrencia"], reg["tipo_recorrencia"]),
                "recorrencia": descrever_regra(reg),
                "expressao_cron": reg.get("expressao_cron") if reg["tipo_recorrencia"] == "CRON" else None,
                "proxima_execucao": formatar_data(reg.get("proxima_execucao")) if reg["ativo"] == "S" else "-",
                "ultima_execucao": formatar_data(reg.get("ultima_execucao")),
                "ultimo_ticket_id": reg.get("ultimo_ticket_id"),
                "responsavel": self._login(reg["usuario_id"], logins),
                "ativo": reg["ativo"],
                "situacao": rotulo,
                "motivo": motivo,
            })
        return dict(resultado, itens=itens)

    def formulario(self, ctx, agendamento_id=None, script_id=None, ambiente=None, enviados=None,
                   valores=None, erros=None):
        """Dados do formulario. Inclusao em etapas (script -> ambiente -> regra) com os filtros do F3.2;
        na edicao, script e ambiente sao fixos (decisao D2 do F5.2).

        enviados/valores/erros (opcionais) reapresentam um POST com erro: campos da regra,
        respostas do questionario e mensagens por campo. Lanca RepoNaoEncontrado, AcessoNegado
        e OperacaoNegada (editor sem pode_executar).
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        erros = erros or {}
        enviados = enviados or {}
        dados = {"edicao": False, "etapa": 1, "grupos": [], "script": None, "ambientes": [], "form": None,
                 "regra": None, "erros": erros}
        atual = None
        if agendamento_id not in (None, ""):
            atual = self._obter_visivel(ctx, agendamento_id)
            script_id, ambiente = atual["script_id"], atual["ambiente"]
            dados["edicao"] = True
        elif not script_id:
            dados["grupos"] = self._disparo.scripts_disponiveis(ctx)
            return dados
        try:
            if not dados["edicao"]:
                script, ambientes = self._disparo.ambientes_disponiveis(ctx, script_id)
                dados.update(etapa=2, script=script, ambientes=ambientes)
                if not ambiente:
                    return dados
            anteriores = _parametros(atual) if atual else {}
            if valores is None:
                valores = anteriores
            form = self._disparo.preparar_formulario(ctx, script_id, ambiente, valores, erros)
        except DisparoNegado as exc:
            if dados["edicao"]:
                self._log.warning("edicao de agendamento negada (login=%s agendamento=%s motivo=%s)",
                                  ctx.get("login"), atual["id"], exc.motivo, extra={"acao": FUNCIONALIDADE})
                raise OperacaoNegada(MSG_SEM_PERMISSAO)
            raise
        for campo in form["campos"]:
            campo["mantido"] = campo["sensivel"] and campo["codigo"] in anteriores
        dados.update(etapa=3, form=form, regra=self._regra_form(ctx, atual, enviados))
        return dados

    def _regra_form(self, ctx, atual, enviados):
        base = atual or {"tipo_recorrencia": "DIARIA", "prioridade": PRIORIDADE_PADRAO}
        regra = {
            "id": base.get("id"),
            "nome": base.get("nome") or "",
            "tipo_recorrencia": base.get("tipo_recorrencia"),
            "expressao_cron": base.get("expressao_cron") or "",
            "hora_execucao": base.get("hora_execucao") or "",
            "dias_semana": [int(d) for d in (base.get("dias_semana") or "").split(",") if d.isdigit()],
            "dia_mes": base.get("dia_mes") or "",
            "data_inicio": _valor_campo_data(base.get("data_inicio")) if atual else "",
            "data_fim": _valor_campo_data(base.get("data_fim")),
            "prioridade": base.get("prioridade") or PRIORIDADE_PADRAO,
            "versao": versao(atual, self._codigos_sensiveis(atual["script_id"])) if atual else "",
            "ativo": base.get("ativo", "S"),
            "situacao": situacao(atual) if atual else None,
            "responsavel": self._login(atual["usuario_id"]) if atual else None,
            "outro_responsavel": bool(atual) and atual["usuario_id"] != ctx.get("usuario_id"),
            "registro": ui_helpers.registro(atual) if atual else None,
        }
        for campo in ("nome", "tipo_recorrencia", "expressao_cron", "hora_execucao", "dia_mes",
                      "data_inicio", "data_fim", "prioridade", "versao"):
            if campo in enviados and enviados[campo] is not None:
                regra[campo] = enviados[campo]
        if "dias_semana" in enviados:
            texto = _dias_semana(enviados["dias_semana"]) or ""
            regra["dias_semana"] = [int(d) for d in texto.split(",") if d.isdigit()]
        return regra

    def previa(self, ctx, dados):
        """Proximas QTD_PREVIA execucoes e a descricao da regra, sem gravar.

        Retorna {datas: [texto], descricao: texto | None, erros: {campo: mensagem}}.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        erros = collections.OrderedDict()
        agora = self._agora()
        regra = self._regra(dados or {}, agora, erros)
        if erros:
            return {"datas": [], "descricao": None, "erros": dict(erros)}
        try:
            datas = recurrence.proximas(regra, agora, QTD_PREVIA, self._horizonte)
        except CronErro as exc:
            return {"datas": [], "descricao": None, "erros": {"expressao_cron": exc.mensagem}}
        if not datas:
            return {"datas": [], "descricao": descrever_regra(regra), "erros": {CAMPO_GERAL: MSG_SEM_PROXIMA}}
        return {"datas": [formatar_previa(d) for d in datas], "descricao": descrever_regra(regra), "erros": {}}

    # ----------------------------------------------------------- gravacao

    def salvar(self, ctx, ip, dados):
        """Inclui (sem 'id') ou altera uma regra. Retorna (id | None, erros_por_campo).

        dados: id, versao, nome, script_id e ambiente (so na inclusao), tipo_recorrencia,
        expressao_cron, hora_execucao, dias_semana, dia_mes, data_inicio, data_fim, prioridade e
        respostas ({codigo: valor}). Lanca RepoNaoEncontrado, AcessoNegado e OperacaoNegada
        (editor sem pode_executar).
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = None
        if dados.get("id") not in (None, ""):
            atual = self._obter_visivel(ctx, dados.get("id"))
            script, amb = self._autorizar(ctx, atual["script_id"], atual["ambiente"])
        else:
            script, amb = self._autorizar(ctx, admin_crud.texto(dados.get("script_id"), 10),
                                          admin_crud.texto(dados.get("ambiente"), 30))
        agora = self._agora()
        erros = collections.OrderedDict()

        nome = admin_crud.texto(dados.get("nome"))
        if nome is None:
            erros["nome"] = MSG_NOME_OBRIGATORIO
        elif len(nome) > TAMANHO_NOME:
            erros["nome"] = MSG_NOME_TAMANHO
        regra = self._regra(dados, agora, erros)
        prioridade = self._prioridade(ctx, dados.get("prioridade"), erros)

        vinculos = self._vinculos(script["id"])
        anteriores = _parametros(atual) if atual else {}
        respostas = self._respostas(vinculos, dados.get("respostas"), anteriores)
        # Compila o snapshot completo so para validar: o daemon recompila a cada desdobro (README §7.5 passo 5).
        _snapshot, resolvidos, erros_param = params_compiler.compilar_snapshot(script, vinculos, respostas, agora)
        for codigo, mensagem in erros_param.items():
            erros.setdefault(codigo, mensagem)

        proxima = None
        if not erros:
            proxima = self._proxima(regra, agora, erros)
        if erros:
            self._log.info("validacao do agendamento com erros (login=%s agendamento=%s campos=%s)",
                           ctx.get("login"), atual["id"] if atual else None, ",".join(sorted(erros)),
                           extra={"acao": FUNCIONALIDADE})
            return (atual["id"] if atual else None), dict(erros)

        registro = dict(regra, nome=nome, script_id=script["id"], ambiente=amb["nome"],
                        usuario_id=ctx["usuario_id"], prioridade=prioridade,
                        parametros_json=_serializar(resolvidos), proxima_execucao=proxima)
        sensiveis = set(v["codigo"] for v in vinculos if v.get("sensivel") == "S")
        if atual is None:
            return self._incluir(ctx, ip, registro, sensiveis)
        if admin_crud.texto(dados.get("versao"), 64) != versao(atual, self._codigos_sensiveis(atual["script_id"])):
            return atual["id"], {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        return self._alterar(ctx, ip, atual, registro, sensiveis)

    def _incluir(self, ctx, ip, registro, sensiveis):
        novo = dict(registro, ativo="S", pausa_motivo=None)
        detalhe = admin_crud.detalhe_insercao(self._auditavel(novo, sensiveis), _CAMPOS_INSERCAO)
        try:
            criado = self._agendamentos.inserir(novo, auditoria=admin_crud.auditoria(ctx, ip, "CAD_INSERIR", detalhe))
        except RepoViolacao as exc:
            self._log.error("agendamento rejeitado pelo repositorio (login=%s constraint=%s)",
                            ctx.get("login"), exc.constraint, extra={"acao": "CAD_INSERIR"})
            return None, {CAMPO_GERAL: admin_crud.MSG_FALHA}
        self._log.info("agendamento incluido (login=%s agendamento=%s script_id=%s ambiente=%s tipo=%s)",
                       ctx.get("login"), criado["id"], criado["script_id"], criado["ambiente"],
                       criado["tipo_recorrencia"], extra={"acao": "CAD_INSERIR"})
        return criado["id"], {}

    def _alterar(self, ctx, ip, atual, registro, sensiveis):
        depois = dict(atual, **registro)
        detalhe = admin_crud.detalhe_alteracoes(self._auditavel(atual, sensiveis),
                                                self._auditavel(depois, sensiveis, atual), CAMPOS_AUDITORIA)
        trocou_responsavel = atual["usuario_id"] != registro["usuario_id"]
        if detalhe is None and not trocou_responsavel:
            return atual["id"], {}
        # README §10: a edicao sempre registra o usuario_id anterior e o novo.
        responsavel = u"usuario_id: %s (%s)%s%s (%s)" % (
            atual["usuario_id"], self._login(atual["usuario_id"]), _SETA,
            registro["usuario_id"], ctx.get("login"))
        detalhe = admin_crud.detalhe_livre(responsavel if detalhe is None else u"%s; %s" % (responsavel, detalhe))
        try:
            self._agendamentos.alterar(atual["id"], registro,
                                       esperado=admin_crud.esperado(atual, _CAMPOS_ESPERADO),
                                       auditoria=admin_crud.auditoria(ctx, ip, "CAD_ALTERAR", detalhe))
        except RepoConflito:
            return atual["id"], {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        except RepoViolacao as exc:
            self._log.error("alteracao de agendamento rejeitada pelo repositorio (login=%s agendamento=%s "
                            "constraint=%s)", ctx.get("login"), atual["id"], exc.constraint,
                            extra={"acao": "CAD_ALTERAR"})
            return atual["id"], {CAMPO_GERAL: admin_crud.MSG_FALHA}
        self._log.info("agendamento alterado (login=%s agendamento=%s usuario_id=%s->%s)",
                       ctx.get("login"), atual["id"], atual["usuario_id"], registro["usuario_id"],
                       extra={"acao": "CAD_ALTERAR"})
        return atual["id"], {}

    def pausar(self, ctx, ip, agendamento_id):
        """Pausa manual (pausa_motivo = 'MANUAL'), otimista sobre proxima_execucao (README §7.5 passo 7).

        Audita AGD_PAUSAR. Lanca OperacaoNegada (ja pausada), RepoConflito, RepoNaoEncontrado e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = self._obter_visivel(ctx, agendamento_id)
        if atual["ativo"] != "S":
            raise OperacaoNegada(MSG_JA_PAUSADA)
        detalhe = admin_crud.detalhe_alteracoes(atual, dict(atual, ativo="N", pausa_motivo="MANUAL"),
                                                ("ativo", "pausa_motivo"))
        alterado = self._agendamentos.pausar(atual["id"], "MANUAL", antiga_data=atual["proxima_execucao"],
                                             auditoria=admin_crud.auditoria(ctx, ip, "AGD_PAUSAR", detalhe))
        self._log.info("agendamento pausado (login=%s agendamento=%s motivo=MANUAL)", ctx.get("login"),
                       atual["id"], extra={"acao": "AGD_PAUSAR"})
        return alterado

    def retomar(self, ctx, ip, agendamento_id):
        """Retoma a regra: revalida pode_executar de quem retoma, recalcula proxima_execucao a partir
        de agora, limpa pausa_motivo e reativa. O responsavel (usuario_id) nao muda.

        Audita CAD_ALTERAR. Lanca OperacaoNegada (ja ativa, sem permissao ou sem proxima execucao),
        RepoConflito, RepoNaoEncontrado e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = self._obter_visivel(ctx, agendamento_id)
        if atual["ativo"] == "S":
            raise OperacaoNegada(MSG_JA_ATIVA)
        self._autorizar(ctx, atual["script_id"], atual["ambiente"])
        try:
            proxima = recurrence.proxima_execucao(atual, self._agora(), self._horizonte)
        except CronErro as exc:
            raise OperacaoNegada(u"%s: %s" % (MOTIVOS_PAUSA["CRON_INVALIDO"], exc.mensagem))
        if proxima is None:
            raise OperacaoNegada(MSG_RETOMAR_SEM_PROXIMA)
        antes = {"ativo": atual["ativo"], "pausa_motivo": atual.get("pausa_motivo"),
                 "proxima_execucao": formatar_data(atual.get("proxima_execucao"))}
        depois = {"ativo": "S", "pausa_motivo": None, "proxima_execucao": formatar_data(proxima)}
        detalhe = admin_crud.detalhe_alteracoes(antes, depois, ("ativo", "pausa_motivo", "proxima_execucao"))
        alterado = self._agendamentos.retomar(
            atual["id"], proxima, esperado=admin_crud.esperado(atual, ("ativo", "pausa_motivo", "proxima_execucao")),
            auditoria=admin_crud.auditoria(ctx, ip, "CAD_ALTERAR", detalhe))
        self._log.info("agendamento retomado (login=%s agendamento=%s proxima=%s)", ctx.get("login"),
                       atual["id"], formatar_data(proxima), extra={"acao": "CAD_ALTERAR"})
        return alterado


_padrao = None
_lock_padrao = threading.Lock()


def _servico():
    global _padrao
    with _lock_padrao:
        if _padrao is None:
            from gluon import current
            import sss_logging
            import ticket_service
            fabrica = current.repo_factory
            cfg = current.sss_cfg
            tickets = fabrica.obter("tickets")
            _padrao = ServicoAgendamentos(
                agendamentos=fabrica.obter("agendamentos"),
                catalogo=fabrica.obter("catalogo"),
                usuarios=fabrica.obter("usuarios"),
                disparo=ticket_service._servico(),
                relogio=tickets.agora,
                horizonte_dias=cfg.agent.cron_horizon_days,
                log=sss_logging.obter_logger("sss_web", cfg),
            )
        return _padrao


def listar(ctx, filtros, pagina, tamanho):
    """Pagina de regras (servico padrao)."""
    return _servico().listar(ctx, filtros, pagina, tamanho)


def agenda(ctx):
    """Agenda dos proximos 7 dias (servico padrao)."""
    return _servico().agenda(ctx)


def formulario(ctx, agendamento_id=None, script_id=None, ambiente=None, enviados=None, valores=None, erros=None):
    """Dados do formulario de regra (servico padrao)."""
    return _servico().formulario(ctx, agendamento_id, script_id, ambiente, enviados, valores, erros)


def previa(ctx, dados):
    """Proximas execucoes e descricao da regra (servico padrao)."""
    return _servico().previa(ctx, dados)


def salvar(ctx, ip, dados):
    """Inclusao ou alteracao de regra (servico padrao)."""
    return _servico().salvar(ctx, ip, dados)


def pausar(ctx, ip, agendamento_id):
    """Pausa manual (servico padrao)."""
    return _servico().pausar(ctx, ip, agendamento_id)


def retomar(ctx, ip, agendamento_id):
    """Retomada (servico padrao)."""
    return _servico().retomar(ctx, ip, agendamento_id)
