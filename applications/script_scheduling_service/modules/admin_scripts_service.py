# -*- coding: utf-8 -*-
"""Cadastro de scripts, homologacao por ambiente e vinculo de parametros (README §4.3.A, §6.3, §8.5, §10).

Segue docs/ADMIN_CRUD_PATTERN.md. O cadastro confere so o formato do path_file e as pastas do sistema (CR-011,
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
import log_paths
import path_guard
import ui_helpers
from admin_crud import GENERAL_FIELD, OperationDenied
from params_compiler import ParamError, PARAM_TYPES
from path_guard import Code, PathGuardError
from repo_errors import RepoConflict, RepoNotFound, RepoViolation

FEATURE = "MANAGE_SCRIPTS"
EDITABLE_FIELDS = ("name", "description", "script_group", "category", "stage", "interpreter", "path_file",
                    "param_type", "max_parallel_env", "timeout_s", "active")
INSERT_FIELDS = ("name", "description", "script_group", "category", "stage", "interpreter", "path_file",
                   "param_type", "max_parallel_env", "timeout_s")



INTERPRETER_LABELS = (("PYTHON3", u"PYTHON3 — Python 3"),
                         ("BASH", u"BASH — Bash"),
                         ("SH", u"SH — Shell POSIX"))
PARAM_TYPE_LABELS = (("NAMED", u"Por flag (NOMEADO)"), ("POSITIONAL", u"Posicional (SEQUENCIAL)"),
                      ("NONE", u"Sem argumentos (NENHUM)"))
MAX_LENGTHS = {"name": 60, "description": 200, "script_group": 30, "category": 30, "stage": 30,
            "path_file": path_guard.MAX_LENGTH}
MAX_TIMEOUT = 9999999
MAX_LINKS = 200
SUB_DEFAULT_MAX_LENGTH = 100
MASK = params_compiler.MASK
_CATALOG_MAX = 1000
_COUNT_PAGE_SIZE = 1  # so o total interessa

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_INTEGER = re.compile(r"[0-9]{1,7}")
_RE_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_RE_FILTER = re.compile(r"[^\x00-\x1f\x7f<>]{1,60}")

PATH_MESSAGES = {
    Code.RELATIVE_PATH: u"Informe o caminho completo do arquivo, começando por / (ex.: /opt/automacoes/scripts/carga.py).",
    Code.PATH_NOT_NORMALIZED: u"Escreva o caminho sem // repetida, sem /./ e sem / no fim.",
    Code.HAS_DOTS: u"O caminho não pode conter '..'.",
    Code.INVALID_SEPARATOR: u"Use só / para separar pastas; não use \\.",
    Code.INVALID_CHARACTER: u"O caminho contém caracteres de controle não permitidos.",
    Code.SYSTEM_DIR: u"Scripts não podem ficar em pastas do sistema (/bin, /sbin, /usr, /lib, /etc, /boot, "
                             u"/proc, /sys, /dev, /root). Use outra pasta.",
    Code.SSS_DIR: u"Scripts não podem ficar nas pastas de log ou de trabalho do SSS. Use outra pasta.",
    Code.INTERPRETADOR_INSEGURO: u"O executável do interpretador não passou na checagem de segurança.",
    Code.INTERPRETADOR_NAO_PERMITIDO: u"Interpretador não permitido.",
}
VALIDATION_NOTE = (u"O arquivo é conferido pelo agente, no servidor onde o script roda, no momento da execução "
                 u"(pode ser link simbólico).")
MSG_NAME_REQUIRED = u"Informe o nome do script."
MSG_NAME_DUPLICATE = u"Já existe um script com este nome."
MSG_CONTROL_CHARS = u"O campo contém caracteres de controle não permitidos."
MSG_PATH_REQUIRED = u"Informe o caminho completo do arquivo do script."
MSG_NAME_RESERVED = u"Este nome é reservado pelo sistema. Escolha outro."
MSG_PARAM_TYPE = u"Selecione como os argumentos são montados."
MSG_PARALLEL = u"Informe um número de 1 a 999."
MSG_TIMEOUT = u"Informe um número de segundos entre 1 e %d, ou deixe em branco." % MAX_TIMEOUT
MSG_NONE_LINKED = u"Este script tem parâmetros vinculados: remova-os antes de usar \"Sem argumentos\"."
MSG_LINKS_INVALID = u"A lista de parâmetros enviada é inválida. Recarregue a página e tente novamente."
MSG_SENSITIVE_INVALID = (u"O valor sigiloso gravado não vale mais para este parâmetro. "
                         u"Informe um novo valor ou use \"Remover valor\".")
MSG_LINK_DUPLICATE = u"O parâmetro \"%s\" aparece mais de uma vez."
MSG_LINK_INACTIVE = u"O parâmetro \"%s\" está inativo e não pode ser vinculado."
MSG_LINK_NONE = u"Scripts \"Sem argumentos\" não aceitam parâmetros."
MSG_HOMOLOG_INVALID = u"A seleção de ambientes é inválida. Recarregue a página e tente novamente."
MSG_HOMOLOG_INACTIVE = u"Ambientes inativos não podem ser homologados."
DEACTIVATION_WARNING = u"Agendamentos que usam este script serão pausados no próximo ciclo."

_FIELD_BY_CONSTRAINT = {
    "uk_tbsss_scr_name": ("name", MSG_NAME_DUPLICATE),
    "ck_tbsss_scr_int": ("interpreter", PATH_MESSAGES[Code.INTERPRETADOR_NAO_PERMITIDO]),
    "ck_tbsss_scr_path": ("path_file", PATH_MESSAGES[Code.PATH_NOT_NORMALIZED]),
    "ck_tbsss_scr_paral": ("max_parallel_env", MSG_PARALLEL),
    "ck_tbsss_scr_tmout": ("timeout_s", MSG_TIMEOUT),
    "ck_tbsss_scr_ptype": ("param_type", MSG_PARAM_TYPE),
    "sss_scr_nenhum_vinculado": ("param_type", MSG_NONE_LINKED),
}


def _id(valor):
    valor = admin_crud.text(valor, 11)
    if valor is None or not _RE_ID.fullmatch(valor) or int(valor) < 1:
        return None
    return int(valor)


def msg_named_without_flag(codigos):
    """Mensagem do bloqueio NOMEADO com os parametros sem flag."""
    return (u"Montagem por flag exige flag em todo parâmetro: cadastre a flag de %s no dicionário de parâmetros."
            % u", ".join(codigos))


def normalize_filters(entrada):
    """Filtros da lista: nome (trecho), grupo, categoria, interpretador (allowlist logica) e ativo."""
    entrada = entrada or {}
    filtros = {}
    for chave in ("name", "script_group", "category"):
        valor = admin_crud.text(entrada.get(chave), 60)
        if valor and _RE_FILTER.fullmatch(valor):
            filtros[chave] = valor
    cmd = admin_crud.text(entrada.get("interpreter"), 60)
    if cmd in path_guard.ALLOWLIST:
        filtros["interpreter"] = cmd
    ativo = admin_crud.text(entrada.get("active"), 1)
    if ativo in ("Y", "N"):
        filtros["active"] = ativo
    return filtros


def _hash(obj):
    bruto = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _read_back(vinculos):
    return [(v["parameter_id"], v["sort_order"], v["required"], v.get("default_value_override")) for v in vinculos]


def _links_version(vinculos, dicionario):
    """Hash dos vinculos lidos; o sub de parametro sensivel entra pelo marcador (README §6.5, §10).

    O esperado do repositorio continua com _lidos (valores reais).
    """
    def sub(v):
        valor = v.get("default_value_override")
        if dicionario.get(v["parameter_id"], {}).get("sensitive") == "Y":
            return admin_crud.sensitive_marker(valor)
        return valor
    return _hash([(v["parameter_id"], v["sort_order"], v["required"], sub(v)) for v in vinculos])


class AdminScriptsService(object):
    """Regras do cadastro de scripts com repositorios, configuracao do agente, relogio e log injetados."""

    def __init__(self, catalogo, agendamentos, sss_env, log, relogio):
        self._catalogo = catalogo
        self._agendamentos = agendamentos
        self._env = sss_env
        self._log = log
        self._relogio = relogio

    def _get(self, script_id):
        sid = _id(script_id)
        if sid is None:
            raise RepoNotFound("script invalido")
        return self._catalogo.scripts_get(sid)

    def _active_schedules(self, **filtros):
        filtros["active"] = "Y"
        return self._agendamentos.list(filtros=filtros, pagina=1, tamanho=_COUNT_PAGE_SIZE)["total"]

    # ----------------------------------------------------------------- leitura

    def list(self, ctx, filtros, pagina, tamanho):
        """Pagina de scripts (nome ASC) com ambientes homologados e quantidade de parametros."""
        admin_crud.require_feature(ctx, FEATURE)
        return self._catalogo.scripts_list(filtros=filtros, pagina=pagina, tamanho=tamanho)

    def form(self, ctx, script_id=None):
        """Dados do formulario. Inclui agendamentos ativos na edicao."""
        admin_crud.require_feature(ctx, FEATURE)
        comum = {"obs_validacao": VALIDATION_NOTE}
        if script_id in (None, ""):
            return dict(comum, id=None, name="", description="", script_group="", category="", stage="",
                        interpreter=path_guard.ALLOWLIST[0], path_file="", param_type="NAMED",
                        max_parallel_env=1, timeout_s="", active="Y", version="", agendamentos_ativos=0,
                        registro=None)
        s = self._get(script_id)
        dados = dict((c, s.get(c)) for c in EDITABLE_FIELDS)
        for c in ("description", "script_group", "category", "stage"):
            dados[c] = admin_crud.normalize(dados[c]) or ""
        dados["timeout_s"] = "" if s.get("timeout_s") is None else s["timeout_s"]
        dados.update(comum, id=s["id"], version=admin_crud.version(s, EDITABLE_FIELDS),
                     agendamentos_ativos=self._active_schedules(script_id=s["id"]),
                     registro=ui_helpers.registro(s, ctx))
        return dados

    # ------------------------------------------------------------- validacao

    def _field_text(self, dados, campo, erros, obrigatorio=False):
        valor = admin_crud.text(dados.get(campo))
        if valor is None:
            if obrigatorio:
                erros[campo] = MSG_NAME_REQUIRED if campo == "name" else MSG_PATH_REQUIRED
            return None
        if _RE_CONTROL.search(valor):
            erros[campo] = MSG_CONTROL_CHARS
        elif len(valor) > MAX_LENGTHS[campo]:
            erros[campo] = u"Use no máximo %d caracteres." % MAX_LENGTHS[campo]
        return valor

    @staticmethod
    def _integer(dados, campo, minimo, maximo, erros, mensagem, opcional=False):
        valor = admin_crud.text(dados.get(campo), 10)
        if valor is None and opcional:
            return None
        if valor is None or not _RE_INTEGER.fullmatch(valor) or not minimo <= int(valor) <= maximo:
            erros[campo] = mensagem
            return None
        return int(valor)

    def _validate(self, dados, erros, atual=None):
        reg = {
            "name": self._field_text(dados, "name", erros, obrigatorio=True),
            "description": self._field_text(dados, "description", erros),
            "script_group": self._field_text(dados, "script_group", erros),
            "category": self._field_text(dados, "category", erros),
            "stage": self._field_text(dados, "stage", erros),
            "path_file": self._field_text(dados, "path_file", erros, obrigatorio=True),
            "max_parallel_env": self._integer(dados, "max_parallel_env", 1, 999, erros, MSG_PARALLEL),
            "timeout_s": self._integer(dados, "timeout_s", 1, MAX_TIMEOUT, erros, MSG_TIMEOUT, opcional=True),
        }
        # Valor exato da allowlist: um HTML adulterado nunca grava outro interpretador.
        cmd = dados.get("interpreter")
        try:
            path_guard.validate_interpreter(cmd)
        except PathGuardError as exc:
            erros["interpreter"] = PATH_MESSAGES[exc.codigo]
        reg["interpreter"] = cmd
        # D7 (README §8.5): a pasta de log do script nao pode ser a dos logs da aplicacao.
        if reg["name"] and "name" not in erros and log_paths.is_reserved_name(reg["name"]):
            erros["name"] = MSG_NAME_RESERVED
        tipo = admin_crud.text(dados.get("param_type"), 15)
        if tipo not in PARAM_TYPES:
            erros["param_type"] = MSG_PARAM_TYPE
        reg["param_type"] = tipo
        return reg

    def validate_path(self, path_file, erros):
        """Confere o formato de path_file e as pastas do sistema (README §8.5; CR-011, S1). O arquivo nao e
        conferido aqui: o web pode nem ter o arquivo; o agente confere no servidor onde o script roda."""
        if path_file is None or "path_file" in erros:
            return
        try:
            path_guard.validate_registration(path_file)
            path_guard.check_forbidden_dirs(path_file)
        except PathGuardError as exc:
            erros["path_file"] = PATH_MESSAGES[exc.codigo]

    def _param_type_precheck(self, script_id, tipo, erros):
        vinculos = self._catalogo.script_params_get(script_id)
        if tipo == "NONE" and vinculos:
            erros["param_type"] = MSG_NONE_LINKED
        elif tipo == "NAMED":
            sem_flag = [v["code"] for v in vinculos if not v.get("param_flag")]
            if sem_flag:
                erros["param_type"] = msg_named_without_flag(sem_flag)

    def _violation(self, ctx, exc, erros, script_id=None):
        if exc.constraint == "sss_scr_nomeado_sem_flag" and script_id:
            erros["param_type"] = msg_named_without_flag(
                [v["code"] for v in self._catalogo.script_params_get(script_id) if not v.get("param_flag")])
        else:
            campo, mensagem = _FIELD_BY_CONSTRAINT.get(exc.constraint, (GENERAL_FIELD, admin_crud.MSG_FAILURE))
            erros[campo] = mensagem
        self._log.warning("cadastro de script rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"action": FEATURE})

    # ----------------------------------------------------------------- escrita

    def save(self, ctx, ip, script_id, dados):
        """Inclui ou altera um script. Retorna (id, erros, aviso). Lanca RepoNotFound e AccessDenied."""
        admin_crud.require_feature(ctx, FEATURE)
        erros = {}
        atual = None if script_id in (None, "") else self._get(script_id)
        reg = self._validate(dados, erros, atual)
        self.validate_path(reg["path_file"], erros)
        aviso = None
        if script_id in (None, ""):
            if erros:
                return None, erros, None
            novo = dict(reg, active="Y")
            auditoria = admin_crud.audit_entry(ctx, ip, "CREATE", admin_crud.insert_detail(novo, INSERT_FIELDS))
            try:
                criado = self._catalogo.scripts_insert(novo, auditoria=auditoria)
            except RepoViolation as exc:
                self._violation(ctx, exc, erros)
                return None, erros, None
            self._log.info("script incluido (login=%s script=%s)", ctx.get("login"), criado["name"],
                           extra={"action": "CREATE"})
            return criado["id"], {}, aviso

        atual = self._get(script_id)
        if not erros and reg["param_type"] != atual["param_type"]:
            self._param_type_precheck(atual["id"], reg["param_type"], erros)
        if erros:
            return atual["id"], erros, None
        if admin_crud.text(dados.get("version"), 64) != admin_crud.version(atual, EDITABLE_FIELDS):
            return atual["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}, None
        alteracoes = dict((c, reg[c]) for c in EDITABLE_FIELDS if c != "active")

        detalhe = admin_crud.changes_detail(atual, dict(atual, **alteracoes), EDITABLE_FIELDS)
        if detalhe is None:
            return atual["id"], {}, aviso
        try:
            self._catalogo.scripts_update(atual["id"], alteracoes, esperado=admin_crud.expected(atual, EDITABLE_FIELDS),
                                           auditoria=admin_crud.audit_entry(ctx, ip, "UPDATE", detalhe))
        except RepoConflict:
            return atual["id"], {GENERAL_FIELD: admin_crud.MSG_CONFLICT}, None
        except RepoViolation as exc:
            self._violation(ctx, exc, erros, atual["id"])
            return atual["id"], erros, None
        self._log.info("script alterado (login=%s script=%s)", ctx.get("login"), reg["name"],
                       extra={"action": "UPDATE"})
        return atual["id"], {}, aviso

    def toggle_active(self, ctx, ip, script_id, versao):
        """Desativa (DEACTIVATE, com agendamentos ativos afetados) ou reativa (UPDATE) o script."""
        admin_crud.require_feature(ctx, FEATURE)
        atual = self._get(script_id)
        if admin_crud.text(versao, 64) != admin_crud.version(atual, EDITABLE_FIELDS):
            raise RepoConflict("versao divergente")
        novo_ativo = "N" if atual["active"] == "Y" else "Y"
        mudancas = {"active": novo_ativo}
        if novo_ativo == "Y":
            # Reativacao refaz as checagens de arquivo (README §8.5).
            erros = {}
            self.validate_path(atual["path_file"], erros)
            if erros:
                raise OperationDenied(u"Não foi possível reativar: %s" % u" ".join(erros.values()))
        detalhe = admin_crud.changes_detail(atual, dict(atual, **mudancas), EDITABLE_FIELDS)
        acao = "DEACTIVATE" if novo_ativo == "N" else "UPDATE"
        if novo_ativo == "N":
            detalhe = u"%s; agendamentos ativos afetados: %d" % (detalhe, self._active_schedules(script_id=atual["id"]))
        alterado = self._catalogo.scripts_update(atual["id"], mudancas,
                                                  esperado=admin_crud.expected(atual, EDITABLE_FIELDS),
                                                  auditoria=admin_crud.audit_entry(ctx, ip, acao, detalhe))
        self._log.info("script %s (login=%s script=%s)", "desativado" if novo_ativo == "N" else "reativado",
                       ctx.get("login"), atual["name"], extra={"action": acao})
        return alterado

    # ------------------------------------------------------------ homologacao

    def homologation(self, ctx, script_id):
        """Tela de homologacao: ambientes ativos e inativos ja homologados, com agendamentos ativos por ambiente."""
        admin_crud.require_feature(ctx, FEATURE)
        script = self._get(script_id)
        marcados = set(self._catalogo.homologation_get(script["id"]))
        ambientes = []
        for a in self._catalogo.environments_list(pagina=1, tamanho=_CATALOG_MAX)["itens"]:
            if a["active"] != "Y" and a["id"] not in marcados:
                continue
            ambientes.append({"id": a["id"], "name": a["name"], "description": a.get("description") or "",
                              "marcado": a["id"] in marcados, "inativo": a["active"] != "Y",
                              "agendamentos_ativos": self._active_schedules(script_id=script["id"],
                                                                               environment=a["name"])})
        return {"script": {"id": script["id"], "name": script["name"], "active": script["active"]},
                "environments": ambientes, "version": _hash(sorted(marcados))}

    def save_homologation(self, ctx, ip, script_id, ambiente_ids, versao):
        """Substitui a homologacao (so ambientes ativos podem ser adicionados; inativos existentes podem sair, D9).

        Retorna (diff ou None, erros). Auditoria UPDATE com +/- e agendamentos ativos afetados.
        """
        admin_crud.require_feature(ctx, FEATURE)
        script = self._get(script_id)
        enviados = set()
        for valor in (ambiente_ids if isinstance(ambiente_ids, (list, tuple)) else [ambiente_ids]):
            if valor in (None, ""):
                continue
            aid = _id(valor)
            if aid is None:
                return None, {GENERAL_FIELD: MSG_HOMOLOG_INVALID}
            enviados.add(aid)
        atuais = self._catalogo.homologation_get(script["id"])
        if admin_crud.text(versao, 64) != _hash(sorted(atuais)):
            return None, {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        ambientes = dict((a["id"], a) for a in self._catalogo.environments_list(pagina=1, tamanho=_CATALOG_MAX)["itens"])
        if enviados - set(ambientes):
            return None, {GENERAL_FIELD: MSG_HOMOLOG_INVALID}
        inativos = set(i for i, a in ambientes.items() if a["active"] != "Y")
        if (enviados - set(atuais)) & inativos:
            return None, {GENERAL_FIELD: MSG_HOMOLOG_INACTIVE}
        # D9 (README §4.3.A): inativo ja homologado pode sair (desmarcado); nunca entra de novo (checado acima).
        final = set(enviados)
        adicionados = sorted(ambientes[i]["name"] for i in final - set(atuais))
        removidos = sorted(ambientes[i]["name"] for i in set(atuais) - final)
        if not adicionados and not removidos:
            return None, {}
        partes = [u"+" + n for n in adicionados] + [u"-" + n for n in removidos]
        diff = u", ".join(partes)
        afetados = sum(self._active_schedules(script_id=script["id"], environment=n) for n in removidos)
        detalhe = admin_crud.free_detail(u"homologação: %s%s" % (
            diff, (u"; agendamentos ativos afetados: %d" % afetados) if removidos else u""))
        try:
            self._catalogo.homologation_save(script["id"], sorted(final), esperado=atuais,
                                              auditoria=admin_crud.audit_entry(ctx, ip, "UPDATE", detalhe))
        except RepoConflict:
            return None, {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        self._log.info("homologacao alterada (login=%s script=%s)", ctx.get("login"), script["name"],
                       extra={"action": "UPDATE"})
        return diff, {}

    # -------------------------------------------------------------- vinculos

    def _dictionary(self):
        return dict((p["id"], p) for p in self._catalogo.parameters_list(pagina=1, tamanho=_CATALOG_MAX)["itens"])

    def parameters(self, ctx, script_id):
        """Tela de vinculos: vinculos atuais (sub sigiloso nunca devolvido), dicionario para busca e versao."""
        admin_crud.require_feature(ctx, FEATURE)
        script = self._get(script_id)
        atuais = self._catalogo.script_params_get(script["id"])
        dicionario = self._dictionary()

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
                "vinculos": vinculos, "disponiveis": disponiveis, "version": _links_version(atuais, dicionario)}

    def _build_links(self, script, vinculos_json, atuais, erros):
        """Valida o JSON do cliente e devolve a lista final ordenada (dicts completos para o compilador)."""
        try:
            itens = json.loads(vinculos_json or "[]")
        except ValueError:
            itens = None
        if not isinstance(itens, list) or len(itens) > MAX_LINKS:
            erros[GENERAL_FIELD] = MSG_LINKS_INVALID
            return None
        dicionario = self._dictionary()
        atuais_por_id = dict((v["parameter_id"], v) for v in atuais)
        vistos = set()
        final = []
        for posicao, item in enumerate(itens, 1):
            pid = _id(str(item.get("parameter_id"))) if isinstance(item, dict) else None
            if pid is None or pid not in dicionario:
                erros[GENERAL_FIELD] = MSG_LINKS_INVALID
                return None
            p = dicionario[pid]
            if pid in vistos:
                erros[GENERAL_FIELD] = MSG_LINK_DUPLICATE % p["code"]
                return None
            vistos.add(pid)
            if p.get("active") != "Y" and pid not in atuais_por_id:
                erros[GENERAL_FIELD] = MSG_LINK_INACTIVE % p["code"]
                return None
            sub = item.get("default_value_override")
            sub = sub.strip() if isinstance(sub, str) else None
            if p.get("sensitive") == "Y" and not sub and item.get("manter_sigiloso") is True and pid in atuais_por_id:
                sub = atuais_por_id[pid].get("default_value_override")
                # O valor mantido tambem e revalidado contra a configuracao atual (README §6.5).
                if sub:
                    try:
                        params_compiler.validate_value(p, sub)
                    except ParamError:
                        erros["vinculo_%d" % pid] = MSG_SENSITIVE_INVALID
            elif sub:
                try:
                    sub = params_compiler.validate_value(p, sub)
                    sub = "true" if sub is True else ("false" if sub is False else sub)
                except ParamError as exc:
                    erros["vinculo_%d" % pid] = exc.mensagem
                    sub = None
                if sub is not None and len(sub) > SUB_DEFAULT_MAX_LENGTH:
                    erros["vinculo_%d" % pid] = u"O valor padrão específico aceita até %d caracteres." % SUB_DEFAULT_MAX_LENGTH
            else:
                sub = None
            v = dict(p, parameter_id=pid, sort_order=posicao, required="Y" if item.get("required") is True else "N",
                     default_value_override=sub)
            final.append(v)
        if script["param_type"] == "NONE" and final:
            erros[GENERAL_FIELD] = MSG_LINK_NONE
        elif script["param_type"] == "NAMED":
            sem_flag = [v["code"] for v in final if not v.get("param_flag")]
            if sem_flag:
                erros[GENERAL_FIELD] = msg_named_without_flag(sem_flag)
        return final

    @staticmethod
    def _describe(vinculos):
        partes = []
        for v in vinculos:
            texto = v["code"] + ("*" if v["required"] == "Y" else "")
            if v.get("default_value_override"):
                texto += "=" + (MASK if v.get("sensitive") == "Y" else str(v["default_value_override"]))
            partes.append(texto)
        return u", ".join(partes) or u"(nenhum)"

    def save_parameters(self, ctx, ip, script_id, vinculos_json, versao):
        """Substitui os vinculos (ordem renumerada pela posicao). Retorna (descricao ou None, erros por campo).

        erros usa GENERAL_FIELD ou 'vinculo_<parametro_id>' (valor padrao especifico invalido).
        """
        admin_crud.require_feature(ctx, FEATURE)
        script = self._get(script_id)
        atuais = self._catalogo.script_params_get(script["id"])
        if admin_crud.text(versao, 64) != _links_version(atuais, self._dictionary()):
            return None, {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        erros = {}
        final = self._build_links(script, vinculos_json, atuais, erros)
        if erros:
            return None, erros
        if _read_back(final) == _read_back(atuais):
            return None, {}
        antes, depois = self._describe(atuais), self._describe(final)
        detalhe = admin_crud.free_detail(u"vínculos: %s → %s" % (antes, depois))
        try:
            self._catalogo.script_params_save(
                script["id"], [dict((k, v[k]) for k in ("parameter_id", "sort_order", "required", "default_value_override"))
                               for v in final],
                esperado=_read_back(atuais), auditoria=admin_crud.audit_entry(ctx, ip, "UPDATE", detalhe))
        except RepoConflict:
            return None, {GENERAL_FIELD: admin_crud.MSG_CONFLICT}
        except RepoViolation as exc:
            self._log.warning("vinculos rejeitados pelo repositorio (login=%s script=%s constraint=%s)",
                              ctx.get("login"), script["name"], exc.constraint, extra={"action": FEATURE})
            if exc.constraint == "sss_scr_nomeado_sem_flag":
                return None, {GENERAL_FIELD: msg_named_without_flag([v["code"] for v in final if not v.get("param_flag")])}
            if exc.constraint == "sss_scr_nenhum_vinculado":
                return None, {GENERAL_FIELD: MSG_LINK_NONE}
            return None, {GENERAL_FIELD: admin_crud.MSG_FAILURE}
        self._log.info("vinculos alterados (login=%s script=%s)", ctx.get("login"), script["name"],
                       extra={"action": "UPDATE"})
        return depois, {}

    def preview(self, ctx, script_id, vinculos_json=None):
        """argv mascarado com os valores padrao (README §6.1), da configuracao em edicao ou da gravada.

        Retorna {argv: [...] | None, erros: {campo: msg}, aviso: str | None}. Nao grava nada.
        """
        admin_crud.require_feature(ctx, FEATURE)
        script = self._get(script_id)
        atuais = self._catalogo.script_params_get(script["id"])
        erros = {}
        if vinculos_json is None:
            vinculos = atuais
        else:
            vinculos = self._build_links(script, vinculos_json, atuais, erros)
            if erros:
                return {"argv": None, "erros": erros, "aviso": None}
        aviso = None
        snap, _resolvidos, erros = params_compiler.compile_snapshot(script, vinculos, {}, self._relogio())
        if snap is None:
            return {"argv": None, "erros": erros, "aviso": aviso}
        return {"argv": params_compiler.display_argv(json.loads(snap)),
                "erros": {}, "aviso": aviso}


_default = None
_default_lock = threading.Lock()


def _service():
    global _default
    with _default_lock:
        if _default is None:
            from gluon import current
            import sss_logging
            fabrica = current.repo_factory
            cfg = current.sss_cfg
            tickets = fabrica.get("tickets")
            _default = AdminScriptsService(
                catalogo=fabrica.get("catalog"),
                agendamentos=fabrica.get("schedules"),
                sss_env=cfg.app.sss_env,
                log=sss_logging.get_logger("sss_web", cfg),
                relogio=tickets.now,
            )
        return _default


def list_page(ctx, filtros, pagina, tamanho):
    """Pagina de scripts (servico padrao)."""
    return _service().list(ctx, filtros, pagina, tamanho)


def form(ctx, script_id=None):
    """Dados do formulario de script (servico padrao)."""
    return _service().form(ctx, script_id)


def save(ctx, ip, script_id, dados):
    """Inclusao ou alteracao de script (servico padrao)."""
    return _service().save(ctx, ip, script_id, dados)


def toggle_active(ctx, ip, script_id, versao):
    """Desativacao/reativacao de script (servico padrao)."""
    return _service().toggle_active(ctx, ip, script_id, versao)


def homologation(ctx, script_id):
    """Tela de homologacao (servico padrao)."""
    return _service().homologation(ctx, script_id)


def save_homologation(ctx, ip, script_id, ambiente_ids, versao):
    """Gravacao da homologacao (servico padrao)."""
    return _service().save_homologation(ctx, ip, script_id, ambiente_ids, versao)


def parameters(ctx, script_id):
    """Tela de vinculos de parametros (servico padrao)."""
    return _service().parameters(ctx, script_id)


def save_parameters(ctx, ip, script_id, vinculos_json, versao):
    """Gravacao dos vinculos (servico padrao)."""
    return _service().save_parameters(ctx, ip, script_id, vinculos_json, versao)


def preview(ctx, script_id, vinculos_json=None):
    """Previa do argv mascarado (servico padrao)."""
    return _service().preview(ctx, script_id, vinculos_json)
