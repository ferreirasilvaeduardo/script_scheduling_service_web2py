# -*- coding: utf-8 -*-
"""Cadastro de scripts, homologacao por ambiente e vinculo de parametros (README §4.3.A, §6.3, §8.5, §10).

Segue docs/PADRAO_CRUD_ADMIN.md. O cadastro confere so o formato do path_file e as pastas do sistema (CR-011,
S1): o arquivo e conferido pelo agente, no servidor onde o script roda. Regras de tipo_param x vinculos sao
reverificadas pelo repositorio na mesma operacao. Nao importa gluon fora de _servico.
"""
import collections
import hashlib
import json
import re
import threading

import admin_crud
import params_compiler
import pastas_log
import path_guard
import ui_helpers
from admin_crud import CAMPO_GERAL, OperacaoNegada
from params_compiler import ParamErro, TIPOS_PARAM
from path_guard import Codigo, PathGuardErro
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao

FUNCIONALIDADE = "MANAGE_SCRIPTS"
CAMPOS_EDITAVEIS = ("name", "description", "script_group", "category", "stage", "interpreter", "path_file",
                    "param_type", "max_parallel_env", "timeout_s", "active")
CAMPOS_INSERCAO = ("name", "description", "script_group", "category", "stage", "interpreter", "path_file",
                   "param_type", "max_parallel_env", "timeout_s")



ROTULOS_INTERPRETADOR = (("PYTHON3", u"PYTHON3 — Python 3"),
                         ("BASH", u"BASH — Bash"),
                         ("SH", u"SH — Shell POSIX"))
ROTULOS_TIPO_PARAM = (("NAMED", u"Por flag (NOMEADO)"), ("POSITIONAL", u"Posicional (SEQUENCIAL)"),
                      ("NONE", u"Sem argumentos (NENHUM)"))
TAMANHOS = {"name": 60, "description": 200, "script_group": 30, "category": 30, "stage": 30,
            "path_file": path_guard.TAMANHO_MAXIMO}
TIMEOUT_MAXIMO = 9999999
VINCULOS_MAXIMO = 200
TAMANHO_PADRAO_SUB = 100
MASCARA = params_compiler.MASCARA
_CATALOGO_MAX = 1000
_TAMANHO_CONTAGEM = 1  # so o total interessa

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_INTEIRO = re.compile(r"[0-9]{1,7}")
_RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
_RE_FILTRO = re.compile(r"[^\x00-\x1f\x7f<>]{1,60}")

MENSAGENS_PATH = {
    Codigo.CAMINHO_RELATIVO: u"Informe o caminho completo do arquivo, começando por / (ex.: /opt/automacoes/scripts/carga.py).",
    Codigo.CAMINHO_NAO_NORMALIZADO: u"Escreva o caminho sem // repetida, sem /./ e sem / no fim.",
    Codigo.CONTEM_PONTOS: u"O caminho não pode conter '..'.",
    Codigo.SEPARADOR_INVALIDO: u"Use só / para separar pastas; não use \\.",
    Codigo.CARACTERE_INVALIDO: u"O caminho contém caracteres de controle não permitidos.",
    Codigo.PASTA_DO_SISTEMA: u"Scripts não podem ficar em pastas do sistema (/bin, /sbin, /usr, /lib, /etc, /boot, "
                             u"/proc, /sys, /dev, /root). Use outra pasta.",
    Codigo.PASTA_DO_SSS: u"Scripts não podem ficar nas pastas de log ou de trabalho do SSS. Use outra pasta.",
    Codigo.INTERPRETADOR_INSEGURO: u"O executável do interpretador não passou na checagem de segurança.",
    Codigo.INTERPRETADOR_NAO_PERMITIDO: u"Interpretador não permitido.",
}
OBS_VALIDACAO = (u"O arquivo é conferido pelo agente, no servidor onde o script roda, no momento da execução "
                 u"(pode ser link simbólico).")
MSG_NOME_OBRIGATORIO = u"Informe o nome do script."
MSG_NOME_DUPLICADO = u"Já existe um script com este nome."
MSG_CONTROLE = u"O campo contém caracteres de controle não permitidos."
MSG_PATH_OBRIGATORIO = u"Informe o caminho completo do arquivo do script."
MSG_NOME_RESERVADO = u"Este nome é reservado pelo sistema. Escolha outro."
MSG_TIPO_PARAM = u"Selecione como os argumentos são montados."
MSG_PARALELO = u"Informe um número de 1 a 999."
MSG_TIMEOUT = u"Informe um número de segundos entre 1 e %d, ou deixe em branco." % TIMEOUT_MAXIMO
MSG_NENHUM_VINCULADO = u"Este script tem parâmetros vinculados: remova-os antes de usar \"Sem argumentos\"."
MSG_VINCULOS_INVALIDOS = u"A lista de parâmetros enviada é inválida. Recarregue a página e tente novamente."
MSG_SIGILOSO_INVALIDO = (u"O valor sigiloso gravado não vale mais para este parâmetro. "
                         u"Informe um novo valor ou use \"Remover valor\".")
MSG_VINCULO_DUPLICADO = u"O parâmetro \"%s\" aparece mais de uma vez."
MSG_VINCULO_INATIVO = u"O parâmetro \"%s\" está inativo e não pode ser vinculado."
MSG_VINCULO_NENHUM = u"Scripts \"Sem argumentos\" não aceitam parâmetros."
MSG_HOMOLOG_INVALIDA = u"A seleção de ambientes é inválida. Recarregue a página e tente novamente."
MSG_HOMOLOG_INATIVO = u"Ambientes inativos não podem ser homologados."
AVISO_DESATIVACAO = u"Agendamentos que usam este script serão pausados no próximo ciclo."

_CAMPO_POR_CONSTRAINT = {
    "uk_tbsss_scr_name": ("name", MSG_NOME_DUPLICADO),
    "ck_tbsss_scr_int": ("interpreter", MENSAGENS_PATH[Codigo.INTERPRETADOR_NAO_PERMITIDO]),
    "ck_tbsss_scr_path": ("path_file", MENSAGENS_PATH[Codigo.CAMINHO_NAO_NORMALIZADO]),
    "ck_tbsss_scr_paral": ("max_parallel_env", MSG_PARALELO),
    "ck_tbsss_scr_tmout": ("timeout_s", MSG_TIMEOUT),
    "ck_tbsss_scr_ptype": ("param_type", MSG_TIPO_PARAM),
    "sss_scr_nenhum_vinculado": ("param_type", MSG_NENHUM_VINCULADO),
}


def _id(valor):
    valor = admin_crud.texto(valor, 11)
    if valor is None or not _RE_ID.fullmatch(valor) or int(valor) < 1:
        return None
    return int(valor)


def msg_nomeado_sem_flag(codigos):
    """Mensagem do bloqueio NOMEADO com os parametros sem flag."""
    return (u"Montagem por flag exige flag em todo parâmetro: cadastre a flag de %s no dicionário de parâmetros."
            % u", ".join(codigos))


def normalizar_filtros(entrada):
    """Filtros da lista: nome (trecho), grupo, categoria, interpretador (allowlist logica) e ativo."""
    entrada = entrada or {}
    filtros = {}
    for chave in ("name", "script_group", "category"):
        valor = admin_crud.texto(entrada.get(chave), 60)
        if valor and _RE_FILTRO.fullmatch(valor):
            filtros[chave] = valor
    cmd = admin_crud.texto(entrada.get("interpreter"), 60)
    if cmd in path_guard.ALLOWLIST:
        filtros["interpreter"] = cmd
    ativo = admin_crud.texto(entrada.get("active"), 1)
    if ativo in ("Y", "N"):
        filtros["active"] = ativo
    return filtros


def _hash(obj):
    bruto = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _lidos(vinculos):
    return [(v["parameter_id"], v["sort_order"], v["required"], v.get("default_value_override")) for v in vinculos]


def _versao_vinculos(vinculos, dicionario):
    """Hash dos vinculos lidos; o sub de parametro sensivel entra pelo marcador (README §6.5, §10).

    O esperado do repositorio continua com _lidos (valores reais).
    """
    def sub(v):
        valor = v.get("default_value_override")
        if dicionario.get(v["parameter_id"], {}).get("sensitive") == "Y":
            return admin_crud.marcador_sensivel(valor)
        return valor
    return _hash([(v["parameter_id"], v["sort_order"], v["required"], sub(v)) for v in vinculos])


class ServicoAdminScripts(object):
    """Regras do cadastro de scripts com repositorios, configuracao do agente, relogio e log injetados."""

    def __init__(self, catalogo, agendamentos, sss_env, log, relogio):
        self._catalogo = catalogo
        self._agendamentos = agendamentos
        self._env = sss_env
        self._log = log
        self._relogio = relogio

    def _obter(self, script_id):
        sid = _id(script_id)
        if sid is None:
            raise RepoNaoEncontrado("script invalido")
        return self._catalogo.scripts_obter(sid)

    def _agendamentos_ativos(self, **filtros):
        filtros["active"] = "Y"
        return self._agendamentos.listar(filtros=filtros, pagina=1, tamanho=_TAMANHO_CONTAGEM)["total"]

    # ----------------------------------------------------------------- leitura

    def listar(self, ctx, filtros, pagina, tamanho):
        """Pagina de scripts (nome ASC) com ambientes homologados e quantidade de parametros."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        return self._catalogo.scripts_listar(filtros=filtros, pagina=pagina, tamanho=tamanho)

    def formulario(self, ctx, script_id=None):
        """Dados do formulario. Inclui agendamentos ativos na edicao."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        comum = {"obs_validacao": OBS_VALIDACAO}
        if script_id in (None, ""):
            return dict(comum, id=None, name="", description="", script_group="", category="", stage="",
                        interpreter=path_guard.ALLOWLIST[0], path_file="", param_type="NAMED",
                        max_parallel_env=1, timeout_s="", active="Y", version="", agendamentos_ativos=0,
                        registro=None)
        s = self._obter(script_id)
        dados = dict((c, s.get(c)) for c in CAMPOS_EDITAVEIS)
        for c in ("description", "script_group", "category", "stage"):
            dados[c] = admin_crud.normalizar(dados[c]) or ""
        dados["timeout_s"] = "" if s.get("timeout_s") is None else s["timeout_s"]
        dados.update(comum, id=s["id"], version=admin_crud.versao(s, CAMPOS_EDITAVEIS),
                     agendamentos_ativos=self._agendamentos_ativos(script_id=s["id"]),
                     registro=ui_helpers.registro(s, ctx))
        return dados

    # ------------------------------------------------------------- validacao

    def _texto_campo(self, dados, campo, erros, obrigatorio=False):
        valor = admin_crud.texto(dados.get(campo))
        if valor is None:
            if obrigatorio:
                erros[campo] = MSG_NOME_OBRIGATORIO if campo == "name" else MSG_PATH_OBRIGATORIO
            return None
        if _RE_CONTROLE.search(valor):
            erros[campo] = MSG_CONTROLE
        elif len(valor) > TAMANHOS[campo]:
            erros[campo] = u"Use no máximo %d caracteres." % TAMANHOS[campo]
        return valor

    @staticmethod
    def _inteiro(dados, campo, minimo, maximo, erros, mensagem, opcional=False):
        valor = admin_crud.texto(dados.get(campo), 10)
        if valor is None and opcional:
            return None
        if valor is None or not _RE_INTEIRO.fullmatch(valor) or not minimo <= int(valor) <= maximo:
            erros[campo] = mensagem
            return None
        return int(valor)

    def _validar(self, dados, erros, atual=None):
        reg = {
            "name": self._texto_campo(dados, "name", erros, obrigatorio=True),
            "description": self._texto_campo(dados, "description", erros),
            "script_group": self._texto_campo(dados, "script_group", erros),
            "category": self._texto_campo(dados, "category", erros),
            "stage": self._texto_campo(dados, "stage", erros),
            "path_file": self._texto_campo(dados, "path_file", erros, obrigatorio=True),
            "max_parallel_env": self._inteiro(dados, "max_parallel_env", 1, 999, erros, MSG_PARALELO),
            "timeout_s": self._inteiro(dados, "timeout_s", 1, TIMEOUT_MAXIMO, erros, MSG_TIMEOUT, opcional=True),
        }
        # Valor exato da allowlist: um HTML adulterado nunca grava outro interpretador.
        cmd = dados.get("interpreter")
        try:
            path_guard.validar_interpretador(cmd)
        except PathGuardErro as exc:
            erros["interpreter"] = MENSAGENS_PATH[exc.codigo]
        reg["interpreter"] = cmd
        # D7 (README §8.5): a pasta de log do script nao pode ser a dos logs da aplicacao.
        if reg["name"] and "name" not in erros and pastas_log.nome_reservado(reg["name"]):
            erros["name"] = MSG_NOME_RESERVADO
        tipo = admin_crud.texto(dados.get("param_type"), 15)
        if tipo not in TIPOS_PARAM:
            erros["param_type"] = MSG_TIPO_PARAM
        reg["param_type"] = tipo
        return reg

    def validar_caminho(self, path_file, erros):
        """Confere o formato de path_file e as pastas do sistema (README §8.5; CR-011, S1). O arquivo nao e
        conferido aqui: o web pode nem ter o arquivo; o agente confere no servidor onde o script roda."""
        if path_file is None or "path_file" in erros:
            return
        try:
            path_guard.validar_cadastro(path_file)
            path_guard.checar_pastas_proibidas(path_file)
        except PathGuardErro as exc:
            erros["path_file"] = MENSAGENS_PATH[exc.codigo]

    def _pre_tipo_param(self, script_id, tipo, erros):
        vinculos = self._catalogo.script_params_obter(script_id)
        if tipo == "NONE" and vinculos:
            erros["param_type"] = MSG_NENHUM_VINCULADO
        elif tipo == "NAMED":
            sem_flag = [v["code"] for v in vinculos if not v.get("param_flag")]
            if sem_flag:
                erros["param_type"] = msg_nomeado_sem_flag(sem_flag)

    def _violacao(self, ctx, exc, erros, script_id=None):
        if exc.constraint == "sss_scr_nomeado_sem_flag" and script_id:
            erros["param_type"] = msg_nomeado_sem_flag(
                [v["code"] for v in self._catalogo.script_params_obter(script_id) if not v.get("param_flag")])
        else:
            campo, mensagem = _CAMPO_POR_CONSTRAINT.get(exc.constraint, (CAMPO_GERAL, admin_crud.MSG_FALHA))
            erros[campo] = mensagem
        self._log.warning("cadastro de script rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"acao": FUNCIONALIDADE})

    # ----------------------------------------------------------------- escrita

    def salvar(self, ctx, ip, script_id, dados):
        """Inclui ou altera um script. Retorna (id, erros, aviso). Lanca RepoNaoEncontrado e AcessoNegado."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        erros = {}
        atual = None if script_id in (None, "") else self._obter(script_id)
        reg = self._validar(dados, erros, atual)
        self.validar_caminho(reg["path_file"], erros)
        aviso = None
        if script_id in (None, ""):
            if erros:
                return None, erros, None
            novo = dict(reg, active="Y")
            auditoria = admin_crud.auditoria(ctx, ip, "CREATE", admin_crud.detalhe_insercao(novo, CAMPOS_INSERCAO))
            try:
                criado = self._catalogo.scripts_inserir(novo, auditoria=auditoria)
            except RepoViolacao as exc:
                self._violacao(ctx, exc, erros)
                return None, erros, None
            self._log.info("script incluido (login=%s script=%s)", ctx.get("login"), criado["name"],
                           extra={"acao": "CREATE"})
            return criado["id"], {}, aviso

        atual = self._obter(script_id)
        if not erros and reg["param_type"] != atual["param_type"]:
            self._pre_tipo_param(atual["id"], reg["param_type"], erros)
        if erros:
            return atual["id"], erros, None
        if admin_crud.texto(dados.get("version"), 64) != admin_crud.versao(atual, CAMPOS_EDITAVEIS):
            return atual["id"], {CAMPO_GERAL: admin_crud.MSG_CONFLITO}, None
        alteracoes = dict((c, reg[c]) for c in CAMPOS_EDITAVEIS if c != "active")

        detalhe = admin_crud.detalhe_alteracoes(atual, dict(atual, **alteracoes), CAMPOS_EDITAVEIS)
        if detalhe is None:
            return atual["id"], {}, aviso
        try:
            self._catalogo.scripts_alterar(atual["id"], alteracoes, esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
                                           auditoria=admin_crud.auditoria(ctx, ip, "UPDATE", detalhe))
        except RepoConflito:
            return atual["id"], {CAMPO_GERAL: admin_crud.MSG_CONFLITO}, None
        except RepoViolacao as exc:
            self._violacao(ctx, exc, erros, atual["id"])
            return atual["id"], erros, None
        self._log.info("script alterado (login=%s script=%s)", ctx.get("login"), reg["name"],
                       extra={"acao": "UPDATE"})
        return atual["id"], {}, aviso

    def alternar_ativo(self, ctx, ip, script_id, versao):
        """Desativa (DEACTIVATE, com agendamentos ativos afetados) ou reativa (UPDATE) o script."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = self._obter(script_id)
        if admin_crud.texto(versao, 64) != admin_crud.versao(atual, CAMPOS_EDITAVEIS):
            raise RepoConflito("versao divergente")
        novo_ativo = "N" if atual["active"] == "Y" else "Y"
        mudancas = {"active": novo_ativo}
        if novo_ativo == "Y":
            # Reativacao refaz as checagens de arquivo (README §8.5).
            erros = {}
            self.validar_caminho(atual["path_file"], erros)
            if erros:
                raise OperacaoNegada(u"Não foi possível reativar: %s" % u" ".join(erros.values()))
        detalhe = admin_crud.detalhe_alteracoes(atual, dict(atual, **mudancas), CAMPOS_EDITAVEIS)
        acao = "DEACTIVATE" if novo_ativo == "N" else "UPDATE"
        if novo_ativo == "N":
            detalhe = u"%s; agendamentos ativos afetados: %d" % (detalhe, self._agendamentos_ativos(script_id=atual["id"]))
        alterado = self._catalogo.scripts_alterar(atual["id"], mudancas,
                                                  esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
                                                  auditoria=admin_crud.auditoria(ctx, ip, acao, detalhe))
        self._log.info("script %s (login=%s script=%s)", "desativado" if novo_ativo == "N" else "reativado",
                       ctx.get("login"), atual["name"], extra={"acao": acao})
        return alterado

    # ------------------------------------------------------------ homologacao

    def homologacao(self, ctx, script_id):
        """Tela de homologacao: ambientes ativos e inativos ja homologados, com agendamentos ativos por ambiente."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        script = self._obter(script_id)
        marcados = set(self._catalogo.homologacao_obter(script["id"]))
        ambientes = []
        for a in self._catalogo.ambientes_listar(pagina=1, tamanho=_CATALOGO_MAX)["itens"]:
            if a["active"] != "Y" and a["id"] not in marcados:
                continue
            ambientes.append({"id": a["id"], "name": a["name"], "description": a.get("description") or "",
                              "marcado": a["id"] in marcados, "inativo": a["active"] != "Y",
                              "agendamentos_ativos": self._agendamentos_ativos(script_id=script["id"],
                                                                               environment=a["name"])})
        return {"script": {"id": script["id"], "name": script["name"], "active": script["active"]},
                "ambientes": ambientes, "version": _hash(sorted(marcados))}

    def salvar_homologacao(self, ctx, ip, script_id, ambiente_ids, versao):
        """Substitui a homologacao (so ambientes ativos podem ser adicionados; inativos existentes podem sair, D9).

        Retorna (diff ou None, erros). Auditoria UPDATE com +/- e agendamentos ativos afetados.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        script = self._obter(script_id)
        enviados = set()
        for valor in (ambiente_ids if isinstance(ambiente_ids, (list, tuple)) else [ambiente_ids]):
            if valor in (None, ""):
                continue
            aid = _id(valor)
            if aid is None:
                return None, {CAMPO_GERAL: MSG_HOMOLOG_INVALIDA}
            enviados.add(aid)
        atuais = self._catalogo.homologacao_obter(script["id"])
        if admin_crud.texto(versao, 64) != _hash(sorted(atuais)):
            return None, {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        ambientes = dict((a["id"], a) for a in self._catalogo.ambientes_listar(pagina=1, tamanho=_CATALOGO_MAX)["itens"])
        if enviados - set(ambientes):
            return None, {CAMPO_GERAL: MSG_HOMOLOG_INVALIDA}
        inativos = set(i for i, a in ambientes.items() if a["active"] != "Y")
        if (enviados - set(atuais)) & inativos:
            return None, {CAMPO_GERAL: MSG_HOMOLOG_INATIVO}
        # D9 (README §4.3.A): inativo ja homologado pode sair (desmarcado); nunca entra de novo (checado acima).
        final = set(enviados)
        adicionados = sorted(ambientes[i]["name"] for i in final - set(atuais))
        removidos = sorted(ambientes[i]["name"] for i in set(atuais) - final)
        if not adicionados and not removidos:
            return None, {}
        partes = [u"+" + n for n in adicionados] + [u"-" + n for n in removidos]
        diff = u", ".join(partes)
        afetados = sum(self._agendamentos_ativos(script_id=script["id"], environment=n) for n in removidos)
        detalhe = admin_crud.detalhe_livre(u"homologação: %s%s" % (
            diff, (u"; agendamentos ativos afetados: %d" % afetados) if removidos else u""))
        try:
            self._catalogo.homologacao_salvar(script["id"], sorted(final), esperado=atuais,
                                              auditoria=admin_crud.auditoria(ctx, ip, "UPDATE", detalhe))
        except RepoConflito:
            return None, {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        self._log.info("homologacao alterada (login=%s script=%s)", ctx.get("login"), script["name"],
                       extra={"acao": "UPDATE"})
        return diff, {}

    # -------------------------------------------------------------- vinculos

    def _dicionario(self):
        return dict((p["id"], p) for p in self._catalogo.parametros_listar(pagina=1, tamanho=_CATALOGO_MAX)["itens"])

    def parametros(self, ctx, script_id):
        """Tela de vinculos: vinculos atuais (sub sigiloso nunca devolvido), dicionario para busca e versao."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        script = self._obter(script_id)
        atuais = self._catalogo.script_params_obter(script["id"])
        dicionario = self._dicionario()

        def resumo(p):
            return {"id": p["id"], "code": p["code"], "label": p.get("label") or "",
                    "component_type": p["component_type"], "param_flag": p.get("param_flag") or "",
                    "sensitive": p.get("sensitive") == "Y", "active": p.get("active") == "Y"}

        vinculos = []
        for v in atuais:
            item = resumo(dicionario.get(v["parameter_id"], v))
            sigiloso = item["sensitive"]
            item.update(required=v["required"] == "Y",
                        default_value_override="" if sigiloso else (v.get("default_value_override") or ""),
                        tem_sub=bool(v.get("default_value_override")))
            vinculos.append(item)
        disponiveis = [resumo(p) for p in sorted(dicionario.values(), key=lambda p: p["code"]) if p.get("active") == "Y"]
        return {"script": {"id": script["id"], "name": script["name"], "param_type": script["param_type"]},
                "vinculos": vinculos, "disponiveis": disponiveis, "version": _versao_vinculos(atuais, dicionario)}

    def _montar_vinculos(self, script, vinculos_json, atuais, erros):
        """Valida o JSON do cliente e devolve a lista final ordenada (dicts completos para o compilador)."""
        try:
            itens = json.loads(vinculos_json or "[]")
        except ValueError:
            itens = None
        if not isinstance(itens, list) or len(itens) > VINCULOS_MAXIMO:
            erros[CAMPO_GERAL] = MSG_VINCULOS_INVALIDOS
            return None
        dicionario = self._dicionario()
        atuais_por_id = dict((v["parameter_id"], v) for v in atuais)
        vistos = set()
        final = []
        for posicao, item in enumerate(itens, 1):
            pid = _id(str(item.get("parameter_id"))) if isinstance(item, dict) else None
            if pid is None or pid not in dicionario:
                erros[CAMPO_GERAL] = MSG_VINCULOS_INVALIDOS
                return None
            p = dicionario[pid]
            if pid in vistos:
                erros[CAMPO_GERAL] = MSG_VINCULO_DUPLICADO % p["code"]
                return None
            vistos.add(pid)
            if p.get("active") != "Y" and pid not in atuais_por_id:
                erros[CAMPO_GERAL] = MSG_VINCULO_INATIVO % p["code"]
                return None
            sub = item.get("default_value_override")
            sub = sub.strip() if isinstance(sub, str) else None
            if p.get("sensitive") == "Y" and not sub and item.get("manter_sigiloso") is True and pid in atuais_por_id:
                sub = atuais_por_id[pid].get("default_value_override")
                # O valor mantido tambem e revalidado contra a configuracao atual (README §6.5).
                if sub:
                    try:
                        params_compiler.validar_valor(p, sub)
                    except ParamErro:
                        erros["vinculo_%d" % pid] = MSG_SIGILOSO_INVALIDO
            elif sub:
                try:
                    sub = params_compiler.validar_valor(p, sub)
                    sub = "true" if sub is True else ("false" if sub is False else sub)
                except ParamErro as exc:
                    erros["vinculo_%d" % pid] = exc.mensagem
                    sub = None
                if sub is not None and len(sub) > TAMANHO_PADRAO_SUB:
                    erros["vinculo_%d" % pid] = u"O valor padrão específico aceita até %d caracteres." % TAMANHO_PADRAO_SUB
            else:
                sub = None
            v = dict(p, parameter_id=pid, sort_order=posicao, required="Y" if item.get("required") is True else "N",
                     default_value_override=sub)
            final.append(v)
        if script["param_type"] == "NONE" and final:
            erros[CAMPO_GERAL] = MSG_VINCULO_NENHUM
        elif script["param_type"] == "NAMED":
            sem_flag = [v["code"] for v in final if not v.get("param_flag")]
            if sem_flag:
                erros[CAMPO_GERAL] = msg_nomeado_sem_flag(sem_flag)
        return final

    @staticmethod
    def _descrever(vinculos):
        partes = []
        for v in vinculos:
            texto = v["code"] + ("*" if v["required"] == "Y" else "")
            if v.get("default_value_override"):
                texto += "=" + (MASCARA if v.get("sensitive") == "Y" else str(v["default_value_override"]))
            partes.append(texto)
        return u", ".join(partes) or u"(nenhum)"

    def salvar_parametros(self, ctx, ip, script_id, vinculos_json, versao):
        """Substitui os vinculos (ordem renumerada pela posicao). Retorna (descricao ou None, erros por campo).

        erros usa CAMPO_GERAL ou 'vinculo_<parametro_id>' (valor padrao especifico invalido).
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        script = self._obter(script_id)
        atuais = self._catalogo.script_params_obter(script["id"])
        if admin_crud.texto(versao, 64) != _versao_vinculos(atuais, self._dicionario()):
            return None, {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        erros = {}
        final = self._montar_vinculos(script, vinculos_json, atuais, erros)
        if erros:
            return None, erros
        if _lidos(final) == _lidos(atuais):
            return None, {}
        antes, depois = self._descrever(atuais), self._descrever(final)
        detalhe = admin_crud.detalhe_livre(u"vínculos: %s → %s" % (antes, depois))
        try:
            self._catalogo.script_params_salvar(
                script["id"], [dict((k, v[k]) for k in ("parameter_id", "sort_order", "required", "default_value_override"))
                               for v in final],
                esperado=_lidos(atuais), auditoria=admin_crud.auditoria(ctx, ip, "UPDATE", detalhe))
        except RepoConflito:
            return None, {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        except RepoViolacao as exc:
            self._log.warning("vinculos rejeitados pelo repositorio (login=%s script=%s constraint=%s)",
                              ctx.get("login"), script["name"], exc.constraint, extra={"acao": FUNCIONALIDADE})
            if exc.constraint == "sss_scr_nomeado_sem_flag":
                return None, {CAMPO_GERAL: msg_nomeado_sem_flag([v["code"] for v in final if not v.get("param_flag")])}
            if exc.constraint == "sss_scr_nenhum_vinculado":
                return None, {CAMPO_GERAL: MSG_VINCULO_NENHUM}
            return None, {CAMPO_GERAL: admin_crud.MSG_FALHA}
        self._log.info("vinculos alterados (login=%s script=%s)", ctx.get("login"), script["name"],
                       extra={"acao": "UPDATE"})
        return depois, {}

    def previa(self, ctx, script_id, vinculos_json=None):
        """argv mascarado com os valores padrao (README §6.1), da configuracao em edicao ou da gravada.

        Retorna {argv: [...] | None, erros: {campo: msg}, aviso: str | None}. Nao grava nada.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        script = self._obter(script_id)
        atuais = self._catalogo.script_params_obter(script["id"])
        erros = {}
        if vinculos_json is None:
            vinculos = atuais
        else:
            vinculos = self._montar_vinculos(script, vinculos_json, atuais, erros)
            if erros:
                return {"argv": None, "erros": erros, "aviso": None}
        aviso = None
        snap, _resolvidos, erros = params_compiler.compilar_snapshot(script, vinculos, {}, self._relogio())
        if snap is None:
            return {"argv": None, "erros": erros, "aviso": aviso}
        return {"argv": params_compiler.argv_para_exibicao(json.loads(snap)),
                "erros": {}, "aviso": aviso}


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
            tickets = fabrica.obter("tickets")
            _padrao = ServicoAdminScripts(
                catalogo=fabrica.obter("catalogo"),
                agendamentos=fabrica.obter("agendamentos"),
                sss_env=cfg.app.sss_env,
                log=sss_logging.obter_logger("sss_web", cfg),
                relogio=tickets.agora,
            )
        return _padrao


def listar(ctx, filtros, pagina, tamanho):
    """Pagina de scripts (servico padrao)."""
    return _servico().listar(ctx, filtros, pagina, tamanho)


def formulario(ctx, script_id=None):
    """Dados do formulario de script (servico padrao)."""
    return _servico().formulario(ctx, script_id)


def salvar(ctx, ip, script_id, dados):
    """Inclusao ou alteracao de script (servico padrao)."""
    return _servico().salvar(ctx, ip, script_id, dados)


def alternar_ativo(ctx, ip, script_id, versao):
    """Desativacao/reativacao de script (servico padrao)."""
    return _servico().alternar_ativo(ctx, ip, script_id, versao)


def homologacao(ctx, script_id):
    """Tela de homologacao (servico padrao)."""
    return _servico().homologacao(ctx, script_id)


def salvar_homologacao(ctx, ip, script_id, ambiente_ids, versao):
    """Gravacao da homologacao (servico padrao)."""
    return _servico().salvar_homologacao(ctx, ip, script_id, ambiente_ids, versao)


def parametros(ctx, script_id):
    """Tela de vinculos de parametros (servico padrao)."""
    return _servico().parametros(ctx, script_id)


def salvar_parametros(ctx, ip, script_id, vinculos_json, versao):
    """Gravacao dos vinculos (servico padrao)."""
    return _servico().salvar_parametros(ctx, ip, script_id, vinculos_json, versao)


def previa(ctx, script_id, vinculos_json=None):
    """Previa do argv mascarado (servico padrao)."""
    return _servico().previa(ctx, script_id, vinculos_json)
