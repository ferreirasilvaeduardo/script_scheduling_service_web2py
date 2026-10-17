# -*- coding: utf-8 -*-
"""Consulta e exportacao da trilha de auditoria (README §4.3.D VER_AUDITORIA, §4.4, §10 tabela 16).

O detalhe ja e gravado sem segredos (README §4.4); na leitura ele passa de novo pelo
mascarador do processo, como defesa em profundidade. A exportacao CSV usa os mesmos
filtros e o mesmo RBAC da tela, neutraliza CSV injection e e ela propria auditada.
"""
import collections
import csv
import datetime
import io
import re
import threading

import admin_crud
import masking
import rbac
import ui_helpers
from admin_crud import AcessoNegado  # noqa: F401  (reexportado para o controller)

FUNCIONALIDADE = "VER_AUDITORIA"

# Catalogo de acoes (README §10, tabela 16), mantido em codigo e sem CK para permitir extensao.
ACOES = (
    "LOGIN_OK", "LOGIN_FALHA", "LOGIN_BLOQUEIO", "LOGOUT",
    "TICKET_CRIAR", "TICKET_CANCELAR", "TICKET_REEXECUTAR",
    "CAD_INSERIR", "CAD_ALTERAR", "CAD_DESATIVAR", "PERM_ALTERAR",
    "AGD_PAUSAR", "AGENTE_INICIO", "AGENTE_FIM", "PURGE",
    "AUD_EXPORTAR",
)
ACAO_EXPORTAR = "AUD_EXPORTAR"
ENTIDADE_AUDITORIA = "tbsss_auditoria"

ENTIDADES = (
    "tbsss_agendamentos", "tbsss_agentes", "tbsss_ambientes", "tbsss_auditoria", "tbsss_parametros",
    "tbsss_perfis", "tbsss_scripts", "tbsss_tickets", "tbsss_usuarios",
)

# Rota da tela de cada entidade e funcionalidade exigida para exibir o link (decisao D6 do F6.1).
# None na funcionalidade: tela de tickets, cuja consulta exige VER_LOGS ou EXEC_SCRIPT.
TELAS_ENTIDADE = {
    "tbsss_tickets": ("tickets", "detalhe", None),
    "tbsss_agendamentos": ("agendamentos", "form", "CAD_AGENDAMENTOS"),
    "tbsss_usuarios": ("admin_usuarios", "form", "CAD_USUARIOS"),
    "tbsss_perfis": ("admin_perfis", "form", "CAD_PERFIS"),
    "tbsss_ambientes": ("admin_ambientes", "form", "CAD_AMBIENTES"),
    "tbsss_scripts": ("admin_scripts", "form", "CAD_SCRIPTS"),
    "tbsss_parametros": ("admin_parametros", "form", "CAD_PARAMETROS"),
}

TAMANHO_MAX = 100
PERIODO_PADRAO_DIAS = 7
PERIODO_MAX_DIAS = 90
# Acima de PERIODO_MAX_DIAS so com filtro seletivo (ator, ou entidade + ID), ate este teto (decisao D4).
PERIODO_MAX_SELETIVO_DIAS = 366
LIMITE_EXPORTACAO = 50000
DETALHE_CURTO = 80
_LINHAS_POR_BLOCO = 500

CAMPOS_FILTRO = ("de", "ate", "ator", "acao", "entidade", "entidade_id", "ip")
CABECALHO_CSV = (u"ID", u"Data/hora", u"Ator", u"IP de origem", u"Ação", u"Entidade", u"ID da entidade",
                 u"Detalhe")
# Prefixos que planilhas interpretam como formula (CSV injection).
_PREFIXOS_PERIGOSOS = ("=", "+", "-", "@", "\t", "\r")
_FORMATO_DIA = "%Y-%m-%d"
_FORMATO_CSV = "%Y-%m-%d %H:%M:%S"
_RE_DIA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_RE_ATOR = re.compile(r"[A-Za-z0-9._:@-]{1,40}")
_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_IP = re.compile(r"[0-9A-Fa-f.:]{1,45}")

MSG_DATA = u"Informe uma data válida (AAAA-MM-DD)."
MSG_INTERVALO = u"A data final deve ser igual ou posterior à inicial."
MSG_PERIODO = (u"O período máximo é de %d dias. Para consultar até %d dias, filtre também pelo ator "
               u"ou pela entidade e ID." % (PERIODO_MAX_DIAS, PERIODO_MAX_SELETIVO_DIAS))
MSG_PERIODO_SELETIVO = u"O período máximo, mesmo com filtro por ator ou entidade, é de %d dias." % (
    PERIODO_MAX_SELETIVO_DIAS)
MSG_ATOR = u"Use até 40 caracteres: letras, números e . _ : @ -"
MSG_ACAO = u"Ação desconhecida."
MSG_ENTIDADE = u"Entidade desconhecida."
MSG_ENTIDADE_ID = u"Informe um número inteiro positivo."
MSG_IP = u"Informe um endereço IPv4 ou IPv6 (ou parte dele)."


class FiltrosInvalidos(ValueError):
    """Filtros recusados; erros: dict campo -> mensagem segura para exibicao."""

    def __init__(self, erros):
        ValueError.__init__(self, ",".join(sorted(erros)))
        self.erros = erros


def _texto(valor, limite):
    return admin_crud.texto(valor, limite)


def _dia(valor):
    if not valor or not _RE_DIA.fullmatch(valor):
        return None
    try:
        return datetime.datetime.strptime(valor, _FORMATO_DIA).date()
    except ValueError:
        return None


def normalizar_filtros(entrada, hoje):
    """Allowlist dos filtros (querystring ou POST da exportacao).

    Retorna (filtros, erros): filtros e um OrderedDict na forma de exibicao/URL, sempre com
    'de' e 'ate' (padrao: os ultimos 7 dias ate `hoje`); erros mapeia campo -> mensagem.
    """
    entrada = entrada or {}
    filtros = collections.OrderedDict()
    erros = {}

    brutos = {}
    for chave in ("de", "ate"):
        brutos[chave] = _texto(entrada.get(chave), 10)
    de, ate = _dia(brutos["de"]), _dia(brutos["ate"])
    for chave, valor in (("de", de), ("ate", ate)):
        if brutos[chave] and valor is None:
            erros[chave] = MSG_DATA
    if ate is None:
        ate = hoje if de is None or de <= hoje else de
    if de is None:
        de = ate - datetime.timedelta(days=PERIODO_PADRAO_DIAS - 1)

    ator = _texto(entrada.get("ator"), 41)
    if ator:
        if _RE_ATOR.fullmatch(ator):
            filtros["ator"] = ator
        else:
            erros["ator"] = MSG_ATOR
    acao = _texto(entrada.get("acao"), 30)
    if acao:
        if acao in ACOES:
            filtros["acao"] = acao
        else:
            erros["acao"] = MSG_ACAO
    entidade = _texto(entrada.get("entidade"), 30)
    if entidade:
        if entidade in ENTIDADES:
            filtros["entidade"] = entidade
        else:
            erros["entidade"] = MSG_ENTIDADE
    entidade_id = _texto(entrada.get("entidade_id"), 11)
    if entidade_id:
        if _RE_ID.fullmatch(entidade_id) and int(entidade_id) > 0:
            filtros["entidade_id"] = int(entidade_id)
        else:
            erros["entidade_id"] = MSG_ENTIDADE_ID
    ip = _texto(entrada.get("ip"), 46)
    if ip:
        if _RE_IP.fullmatch(ip):
            filtros["ip"] = ip
        else:
            erros["ip"] = MSG_IP

    if "de" not in erros and "ate" not in erros:
        dias = (ate - de).days + 1
        seletivo = "ator" in filtros or ("entidade" in filtros and "entidade_id" in filtros)
        if dias < 1:
            erros["ate"] = MSG_INTERVALO
        elif dias > PERIODO_MAX_SELETIVO_DIAS:
            erros["de"] = MSG_PERIODO_SELETIVO
        elif dias > PERIODO_MAX_DIAS and not seletivo:
            erros["de"] = MSG_PERIODO

    resultado = collections.OrderedDict()
    resultado["de"] = brutos["de"] if "de" in erros and brutos["de"] else de.strftime(_FORMATO_DIA)
    resultado["ate"] = brutos["ate"] if "ate" in erros and brutos["ate"] else ate.strftime(_FORMATO_DIA)
    resultado.update(filtros)
    return resultado, erros


def filtros_repo(filtros):
    """Traduz filtros validos para o contrato: periodo vira [de 00:00:00, ate 23:59:59]."""
    de = datetime.datetime.strptime(filtros["de"], _FORMATO_DIA)
    ate = datetime.datetime.strptime(filtros["ate"], _FORMATO_DIA)
    repo = {"data_inicio": de, "data_fim": ate + datetime.timedelta(days=1, seconds=-1)}
    for chave, destino in (("ator", "ator"), ("acao", "acao"), ("entidade", "entidade"),
                           ("entidade_id", "entidade_id"), ("ip", "ip_origem")):
        if chave in filtros:
            repo[destino] = filtros[chave]
    return repo


def neutralizar_csv(valor):
    """Prefixa com ' o texto que uma planilha leria como formula (= + - @ TAB CR no inicio)."""
    if isinstance(valor, str) and valor.startswith(_PREFIXOS_PERIGOSOS):
        return u"'" + valor
    return valor


def _mascarar(texto):
    return masking.MASCARADOR.mascarar(texto) if texto else texto


def _linha_csv(reg):
    criado = reg.get("created_at")
    valores = (
        reg["id"],
        criado.strftime(_FORMATO_CSV) if criado else u"",
        reg.get("ator") or u"",
        reg.get("ip_origem") or u"",
        reg.get("acao") or u"",
        reg.get("entidade") or u"",
        u"" if reg.get("entidade_id") is None else reg["entidade_id"],
        _mascarar(reg.get("detalhe")) or u"",
    )
    return [neutralizar_csv(v) for v in valores]


def link_entidade(ctx, entidade, entidade_id, pode_ver_tickets):
    """(controller, funcao, args) da tela da entidade, ou None sem tela ou sem permissao (decisao D6)."""
    if entidade_id is None:
        return None
    tela = TELAS_ENTIDADE.get(entidade)
    if tela is None:
        return None
    controller, funcao, func = tela
    permitido = pode_ver_tickets if func is None else rbac.tem_func(ctx, func)
    if not permitido:
        return None
    return controller, funcao, [entidade_id]


def _descrever_filtros(filtros):
    return u", ".join(u"%s=%s" % (k, filtros[k]) for k in CAMPOS_FILTRO if k in filtros)


class ServicoAuditoria(object):
    """Consulta e exportacao da trilha, com repositorio, relogio e log injetados."""

    def __init__(self, auditoria, relogio, log):
        self._auditoria = auditoria
        self._relogio = relogio
        self._log = log

    def _hoje(self):
        return self._relogio().date()

    def normalizar_filtros(self, entrada):
        """Filtros e erros com o periodo padrao calculado pelo relogio do banco."""
        return normalizar_filtros(entrada, self._hoje())

    def listar(self, ctx, entrada, pagina, tamanho):
        """Pagina da trilha (tamanho <= 100), ordenada por created_at DESC, id DESC.

        Retorna dict com filtros, erros, itens, total, pagina e tamanho. Com erros de filtro
        nada e consultado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        tamanho = max(1, min(int(tamanho or 20), TAMANHO_MAX))
        filtros, erros = self.normalizar_filtros(entrada)
        vazio = {"filtros": filtros, "erros": erros, "itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        if erros:
            return vazio
        repo_filtros = filtros_repo(filtros)
        resultado = self._auditoria.listar(filtros=repo_filtros, pagina=pagina, tamanho=tamanho)
        info = ui_helpers.paginacao_info(pagina, tamanho, resultado["total"])
        if not resultado["itens"] and info["pagina"] != resultado["pagina"]:
            resultado = self._auditoria.listar(filtros=repo_filtros, pagina=info["pagina"], tamanho=tamanho)
        itens = []
        for reg in resultado["itens"]:
            detalhe = _mascarar(reg.get("detalhe")) or u""
            itens.append({
                "id": reg["id"],
                "created_at": reg.get("created_at"),
                "ator": reg.get("ator"),
                "ip_origem": reg.get("ip_origem"),
                "acao": reg.get("acao"),
                "entidade": reg.get("entidade"),
                "entidade_id": reg.get("entidade_id"),
                "detalhe": detalhe,
                "detalhe_curto": detalhe if len(detalhe) <= DETALHE_CURTO else detalhe[:DETALHE_CURTO - 1] + u"…",
                "truncado": len(detalhe) > DETALHE_CURTO,
            })
        return dict(vazio, itens=itens, total=resultado["total"], pagina=resultado["pagina"],
                    tamanho=resultado["tamanho"])

    def exportar_csv(self, ctx, ip, entrada):
        """Exportacao com os filtros e o RBAC da tela: retorna (nome_arquivo, linhas, blocos).

        blocos e um gerador de bytes UTF-8 (com BOM, separador ';') de no maximo
        LIMITE_EXPORTACAO linhas. A exportacao e auditada (AUD_EXPORTAR) antes do streaming,
        e o conjunto exportado para no ID anterior ao da propria linha de auditoria.
        Filtros invalidos levantam FiltrosInvalidos.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        filtros, erros = self.normalizar_filtros(entrada)
        if erros:
            raise FiltrosInvalidos(erros)
        repo_filtros = filtros_repo(filtros)
        # README §4.4 (D12): reserva o id, delimita id_max = id - 1, conta esse recorte e so entao grava a
        # linha; a quantidade registrada e o arquivo correspondem ao mesmo conjunto.
        aid = self._auditoria.reservar_id()
        repo_filtros["id_max"] = aid - 1
        total = sum(1 for _ in self._auditoria.iterar(filtros=repo_filtros, limite=LIMITE_EXPORTACAO))
        linhas = min(total, LIMITE_EXPORTACAO)
        detalhe = admin_crud.detalhe_livre(u"filtros: %s; linhas: %d (limite %d)" % (
            _descrever_filtros(filtros), linhas, LIMITE_EXPORTACAO))
        self._auditoria.registrar(ctx.get("login"), ip, ACAO_EXPORTAR, ENTIDADE_AUDITORIA, None, detalhe, id=aid)
        self._log.info("auditoria exportada (login=%s linhas=%d total=%d)", ctx.get("login"), linhas, total,
                       extra={"acao": ACAO_EXPORTAR})
        nome = "auditoria_%s.csv" % self._relogio().strftime("%Y%m%d_%H%M%S")
        return nome, linhas, self._blocos(repo_filtros, ctx.get("login"))

    def _blocos(self, repo_filtros, login):
        buffer = io.StringIO()
        escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        escritor.writerow(CABECALHO_CSV)
        yield (u"﻿" + buffer.getvalue()).encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)
        pendentes = 0
        try:
            for reg in self._auditoria.iterar(filtros=repo_filtros, limite=LIMITE_EXPORTACAO):
                escritor.writerow(_linha_csv(reg))
                pendentes += 1
                if pendentes >= _LINHAS_POR_BLOCO:
                    yield buffer.getvalue().encode("utf-8")
                    buffer.seek(0)
                    buffer.truncate(0)
                    pendentes = 0
        except Exception:
            # A resposta ja comecou: so resta registrar e encerrar o arquivo incompleto.
            self._log.exception("falha durante a exportacao da auditoria (login=%s)", login,
                                extra={"acao": ACAO_EXPORTAR})
            raise
        if pendentes:
            yield buffer.getvalue().encode("utf-8")


_padrao = None
_lock_padrao = threading.Lock()


def _servico():
    global _padrao
    with _lock_padrao:
        if _padrao is None:
            from gluon import current
            import sss_logging
            fabrica = current.repo_factory
            _padrao = ServicoAuditoria(
                auditoria=fabrica.obter("auditoria"),
                relogio=fabrica.obter("tickets").agora,
                log=sss_logging.obter_logger("sss_web", current.sss_cfg),
            )
        return _padrao


def filtros_padrao(entrada):
    """Filtros e erros normalizados com o relogio do banco (servico padrao)."""
    return _servico().normalizar_filtros(entrada)


def listar(ctx, entrada, pagina, tamanho):
    """Pagina da trilha de auditoria (servico padrao)."""
    return _servico().listar(ctx, entrada, pagina, tamanho)


def exportar_csv(ctx, ip, entrada):
    """Exportacao CSV auditada (servico padrao)."""
    return _servico().exportar_csv(ctx, ip, entrada)
