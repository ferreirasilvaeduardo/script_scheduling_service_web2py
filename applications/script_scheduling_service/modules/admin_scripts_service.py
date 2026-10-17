# -*- coding: utf-8 -*-
"""Cadastro de scripts, homologacao por ambiente e vinculo de parametros (README §4.3.A, §6.3, §8.5, §10).

Segue docs/PADRAO_CRUD_ADMIN.md. O executavel e validado pelo path_guard no cadastro (a validacao
definitiva repete-se no agente). Regras de tipo_param x vinculos sao reverificadas pelo repositorio na
mesma operacao. CR-005: path_file absoluto, em qualquer lugar fora das pastas do sistema; o arquivo ausente
neste no vira aviso (o agente confere no claim). Nao importa gluon fora de _servico.
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

FUNCIONALIDADE = "CAD_SCRIPTS"
CAMPOS_EDITAVEIS = ("nome", "descricao", "grupo", "categoria", "etapa", "interpretador", "path_file",
                    "tipo_param", "max_qtd_parallel_env", "timeout_seg", "ativo", "sha256_homologado")
CAMPOS_INSERCAO = ("nome", "descricao", "grupo", "categoria", "etapa", "interpretador", "path_file",
                   "tipo_param", "max_qtd_parallel_env", "timeout_seg", "sha256_homologado")


_RE_SHA256 = re.compile(r"[0-9a-f]{64}")
MSG_SHA256_FORMATO = (u"Informe os 64 caracteres hexadecimais do SHA-256 (a saída de sha256sum no servidor do agente).")
MSG_SHA256_DIVERGE = (u"O SHA-256 informado é diferente do arquivo presente neste servidor. Confira o arquivo "
                      u"ou deixe o campo vazio para usar o conteúdo daqui.")


def calcular_sha256_arquivo(caminho):
    """Calcula o SHA-256 do arquivo validado, em blocos de 64 KiB."""
    h = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        while True:
            bloco = arquivo.read(65536)
            if not bloco:
                break
            h.update(bloco)
    return h.hexdigest()


ROTULOS_INTERPRETADOR = (("PYTHON3", u"PYTHON3 — Python 3"),
                         ("BASH", u"BASH — Bash"),
                         ("SH", u"SH — Shell POSIX"))
ROTULOS_TIPO_PARAM = (("NOMEADO", u"Por flag (NOMEADO)"), ("SEQUENCIAL", u"Posicional (SEQUENCIAL)"),
                      ("NENHUM", u"Sem argumentos (NENHUM)"))
TAMANHOS = {"nome": 60, "descricao": 200, "grupo": 30, "categoria": 30, "etapa": 30,
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
    Codigo.CAMINHO_COM_LINK: u"O caminho passa por um link simbólico. Informe o caminho real do arquivo, sem links.",
    Codigo.SEM_ACESSO: u"Uma pasta do caminho não deixa o sistema passar; confira as permissões das pastas.",
    Codigo.PASTA_DO_SISTEMA: u"Scripts não podem ficar em pastas do sistema (/bin, /sbin, /usr, /lib, /etc, /boot, "
                             u"/proc, /sys, /dev, /root). Use outra pasta.",
    Codigo.PASTA_DO_SSS: u"Scripts não podem ficar nas pastas de log ou de trabalho do SSS. Use outra pasta.",
    Codigo.NAO_E_ARQUIVO: u"O caminho aponta para uma pasta ou algo que não é um arquivo comum.",
    Codigo.DONO_INVALIDO: u"O arquivo, ou uma pasta do caminho, pertence a um usuário não autorizado.",
    Codigo.GRAVAVEL_GRUPO_OUTROS: u"O arquivo, ou uma pasta do caminho, pode ser alterado por outros usuários "
                                  u"(ou pelo grupo); ajuste as permissões.",
    Codigo.GRAVAVEL_PELO_AGENTE: u"O arquivo, ou uma pasta do caminho, é gravável pelo usuário do sistema "
                                 u"ou pertence a ele; ajuste o dono e as permissões.",
    Codigo.GRAVAVEL_PELO_EXECUTOR: u"O arquivo, ou uma pasta do caminho, pertence ao usuário que executa os "
                                   u"scripts; o dono precisa ser outro usuário autorizado.",
    Codigo.INTERPRETADOR_INSEGURO: u"O executável do interpretador não passou na checagem de segurança.",
    Codigo.INTERPRETADOR_NAO_PERMITIDO: u"Interpretador não permitido.",
}
OBS_VALIDACAO = u"A validação definitiva ocorre também no agente executor no momento da execução."
AVISO_NAO_ENCONTRADO = (u"Arquivo não encontrado neste servidor: a validação ocorrerá no agente. "
                        u"Se o arquivo não existir lá, a execução será recusada.")
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
    "uk_tbsss_scr_nome": ("nome", MSG_NOME_DUPLICADO),
    "ck_tbsss_scr_int": ("interpretador", MENSAGENS_PATH[Codigo.INTERPRETADOR_NAO_PERMITIDO]),
    "ck_tbsss_scr_path": ("path_file", MENSAGENS_PATH[Codigo.CAMINHO_NAO_NORMALIZADO]),
    "ck_tbsss_scr_paral": ("max_qtd_parallel_env", MSG_PARALELO),
    "ck_tbsss_scr_tmout": ("timeout_seg", MSG_TIMEOUT),
    "ck_tbsss_scr_tparam": ("tipo_param", MSG_TIPO_PARAM),
    "sss_scr_nenhum_vinculado": ("tipo_param", MSG_NENHUM_VINCULADO),
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
    for chave in ("nome", "grupo", "categoria"):
        valor = admin_crud.texto(entrada.get(chave), 60)
        if valor and _RE_FILTRO.fullmatch(valor):
            filtros[chave] = valor
    cmd = admin_crud.texto(entrada.get("interpretador"), 60)
    if cmd in path_guard.ALLOWLIST:
        filtros["interpretador"] = cmd
    ativo = admin_crud.texto(entrada.get("ativo"), 1)
    if ativo in ("S", "N"):
        filtros["ativo"] = ativo
    return filtros


def _hash(obj):
    bruto = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _lidos(vinculos):
    return [(v["parametro_id"], v["ordem"], v["obrigatorio"], v.get("valor_padrao_sub")) for v in vinculos]


def _versao_vinculos(vinculos, dicionario):
    """Hash dos vinculos lidos; o sub de parametro sensivel entra pelo marcador (README §6.5, §10).

    O esperado do repositorio continua com _lidos (valores reais).
    """
    def sub(v):
        valor = v.get("valor_padrao_sub")
        if dicionario.get(v["parametro_id"], {}).get("sensivel") == "S":
            return admin_crud.marcador_sensivel(valor)
        return valor
    return _hash([(v["parametro_id"], v["ordem"], v["obrigatorio"], sub(v)) for v in vinculos])


class ServicoAdminScripts(object):
    """Regras do cadastro de scripts com repositorios, configuracao do agente, relogio e log injetados."""

    def __init__(self, catalogo, agendamentos, script_owner_uids, sss_env, log, relogio, dirs_sss=(),
                 uids_proibidos=()):
        self._catalogo = catalogo
        self._agendamentos = agendamentos
        self._owner_uids = tuple(script_owner_uids)
        # log_dir, work_dir e exec_work_dir deste no: nenhum script pode ficar dentro deles (README §8.5).
        self._dirs_sss = tuple(d for d in dirs_sss if d)
        # UIDs dos usuarios de execucao que existem neste no: nao podem ser donos do caminho (CR-007, R-15).
        self._uids_proibidos = tuple(uids_proibidos)
        self._env = sss_env
        self._log = log
        self._relogio = relogio

    def _obter(self, script_id):
        sid = _id(script_id)
        if sid is None:
            raise RepoNaoEncontrado("script invalido")
        return self._catalogo.scripts_obter(sid)

    def _agendamentos_ativos(self, **filtros):
        filtros["ativo"] = "S"
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
            return dict(comum, id=None, nome="", descricao="", grupo="", categoria="", etapa="",
                        interpretador=path_guard.ALLOWLIST[0], path_file="", tipo_param="NOMEADO",
                        max_qtd_parallel_env=1, timeout_seg="", ativo="S", versao="", agendamentos_ativos=0,
                        registro=None, sha256_homologado=None)
        s = self._obter(script_id)
        dados = dict((c, s.get(c)) for c in CAMPOS_EDITAVEIS)
        for c in ("descricao", "grupo", "categoria", "etapa"):
            dados[c] = admin_crud.normalizar(dados[c]) or ""
        dados["timeout_seg"] = "" if s.get("timeout_seg") is None else s["timeout_seg"]
        dados.update(comum, id=s["id"], versao=admin_crud.versao(s, CAMPOS_EDITAVEIS),
                     agendamentos_ativos=self._agendamentos_ativos(script_id=s["id"]),
                     registro=ui_helpers.registro(s, ctx),
                     sha256_homologado=s.get("sha256_homologado"))
        return dados

    # ------------------------------------------------------------- validacao

    def _texto_campo(self, dados, campo, erros, obrigatorio=False):
        valor = admin_crud.texto(dados.get(campo))
        if valor is None:
            if obrigatorio:
                erros[campo] = MSG_NOME_OBRIGATORIO if campo == "nome" else MSG_PATH_OBRIGATORIO
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
            "nome": self._texto_campo(dados, "nome", erros, obrigatorio=True),
            "descricao": self._texto_campo(dados, "descricao", erros),
            "grupo": self._texto_campo(dados, "grupo", erros),
            "categoria": self._texto_campo(dados, "categoria", erros),
            "etapa": self._texto_campo(dados, "etapa", erros),
            "path_file": self._texto_campo(dados, "path_file", erros, obrigatorio=True),
            "max_qtd_parallel_env": self._inteiro(dados, "max_qtd_parallel_env", 1, 999, erros, MSG_PARALELO),
            "timeout_seg": self._inteiro(dados, "timeout_seg", 1, TIMEOUT_MAXIMO, erros, MSG_TIMEOUT, opcional=True),
        }
        # Valor exato da allowlist: um HTML adulterado nunca grava outro interpretador.
        cmd = dados.get("interpretador")
        try:
            path_guard.validar_interpretador(cmd)
        except PathGuardErro as exc:
            erros["interpretador"] = MENSAGENS_PATH[exc.codigo]
        reg["interpretador"] = cmd
        # D7 (README §8.5): a pasta de log do script nao pode ser a dos logs da aplicacao.
        if reg["nome"] and "nome" not in erros and pastas_log.nome_reservado(reg["nome"]):
            erros["nome"] = MSG_NOME_RESERVADO
        tipo = admin_crud.texto(dados.get("tipo_param"), 15)
        if tipo not in TIPOS_PARAM:
            erros["tipo_param"] = MSG_TIPO_PARAM
        reg["tipo_param"] = tipo
        return reg

    def validar_caminho(self, path_file, erros, checar_arquivo=True):
        """Confere path_file neste no (README §8.5, CR-005 D3/D4). Retorna aviso (str) ou None.

        Formato e pastas proibidas valem sempre. Com checar_arquivo, se o arquivo existe aqui, dono e
        permissao bloqueiam; se nao existe, vira aviso e o agente confere no claim.
        """
        if path_file is None or "path_file" in erros:
            return None
        try:
            path_guard.validar_cadastro(path_file)
            path_guard.checar_pastas_proibidas(path_file, self._dirs_sss)
            if checar_arquivo:
                path_guard.resolver(path_file, self._owner_uids, dirs_sss=self._dirs_sss,
                                    uids_proibidos=self._uids_proibidos)
        except PathGuardErro as exc:
            if exc.codigo == Codigo.NAO_ENCONTRADO:
                return AVISO_NAO_ENCONTRADO
            erros["path_file"] = MENSAGENS_PATH[exc.codigo]
        return None

    @staticmethod
    def _sha256_informado(dados, erros):
        """SHA-256 digitado pelo administrador (CR-008, E4): None se vazio; formato invalido vira erro."""
        valor = admin_crud.texto(dados.get("sha256_informado"), 100)
        if not valor:
            return None
        valor = valor.strip().lower()
        if not _RE_SHA256.fullmatch(valor):
            erros["sha256_informado"] = MSG_SHA256_FORMATO
            return None
        return valor

    def _hash_homologado(self, caminho, aviso, informado, erros):
        """Hash calculado neste no ou, sem o arquivo aqui, o informado; divergencia entre os dois e erro."""
        sha = self._hash_validado(caminho, aviso)
        if sha is not None and informado is not None and sha != informado:
            erros["sha256_informado"] = MSG_SHA256_DIVERGE
            return None
        return sha if sha is not None else informado

    def _hash_validado(self, caminho, aviso):
        if aviso == AVISO_NAO_ENCONTRADO:
            return None
        try:
            return calcular_sha256_arquivo(caminho)
        except OSError:
            self._log.exception("falha ao registrar conteudo do script", extra={"acao": FUNCIONALIDADE})
            raise OperacaoNegada(admin_crud.MSG_FALHA)

    def _pre_tipo_param(self, script_id, tipo, erros):
        vinculos = self._catalogo.script_params_obter(script_id)
        if tipo == "NENHUM" and vinculos:
            erros["tipo_param"] = MSG_NENHUM_VINCULADO
        elif tipo == "NOMEADO":
            sem_flag = [v["codigo"] for v in vinculos if not v.get("param_nomeado")]
            if sem_flag:
                erros["tipo_param"] = msg_nomeado_sem_flag(sem_flag)

    def _violacao(self, ctx, exc, erros, script_id=None):
        if exc.constraint == "sss_scr_nomeado_sem_flag" and script_id:
            erros["tipo_param"] = msg_nomeado_sem_flag(
                [v["codigo"] for v in self._catalogo.script_params_obter(script_id) if not v.get("param_nomeado")])
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
        informado = self._sha256_informado(dados, erros)
        # Toda homologacao exige as checagens do caminho, inclusive a solicitada pelo checkbox.
        checar = (atual is None or bool(dados.get("registrar_conteudo_atual")) or informado is not None
                  or any(reg[c] != atual.get(c) for c in ("path_file", "interpretador")))
        aviso = self.validar_caminho(reg["path_file"], erros, checar)
        if script_id in (None, ""):
            if erros:
                return None, erros, None
            novo = dict(reg, ativo="S")
            sha = self._hash_homologado(reg["path_file"], aviso, informado, erros)
            if erros:
                return None, erros, None
            novo["sha256_homologado"] = sha
            auditoria = admin_crud.auditoria(ctx, ip, "CAD_INSERIR", admin_crud.detalhe_insercao(novo, CAMPOS_INSERCAO))
            try:
                criado = self._catalogo.scripts_inserir(novo, auditoria=auditoria)
            except RepoViolacao as exc:
                self._violacao(ctx, exc, erros)
                return None, erros, None
            self._log.info("script incluido (login=%s script=%s)", ctx.get("login"), criado["nome"],
                           extra={"acao": "CAD_INSERIR"})
            return criado["id"], {}, aviso

        atual = self._obter(script_id)
        if not erros and reg["tipo_param"] != atual["tipo_param"]:
            self._pre_tipo_param(atual["id"], reg["tipo_param"], erros)
        if erros:
            return atual["id"], erros, None
        if admin_crud.texto(dados.get("versao"), 64) != admin_crud.versao(atual, CAMPOS_EDITAVEIS):
            return atual["id"], {CAMPO_GERAL: admin_crud.MSG_CONFLITO}, None
        alteracoes = dict((c, reg[c]) for c in CAMPOS_EDITAVEIS if c not in ("ativo", "sha256_homologado"))
        registrar_atual = bool(dados.get("registrar_conteudo_atual"))
        mudou_arquivo = reg["path_file"] != atual.get("path_file") or reg["interpretador"] != atual.get("interpretador")
        alteracoes["sha256_homologado"] = atual.get("sha256_homologado")
        if mudou_arquivo or registrar_atual or informado is not None:
            sha = self._hash_homologado(reg["path_file"], aviso, informado, erros)
            if erros:
                return atual["id"], erros, None
            if sha is not None or mudou_arquivo:
                # Caminho novo sem hash calculado nem informado: o hash antigo nao vale mais (CR-008, R-24).
                alteracoes["sha256_homologado"] = sha

        detalhe = admin_crud.detalhe_alteracoes(atual, dict(atual, **alteracoes), CAMPOS_EDITAVEIS)
        if detalhe is None:
            return atual["id"], {}, aviso
        try:
            self._catalogo.scripts_alterar(atual["id"], alteracoes, esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
                                           auditoria=admin_crud.auditoria(ctx, ip, "CAD_ALTERAR", detalhe))
        except RepoConflito:
            return atual["id"], {CAMPO_GERAL: admin_crud.MSG_CONFLITO}, None
        except RepoViolacao as exc:
            self._violacao(ctx, exc, erros, atual["id"])
            return atual["id"], erros, None
        self._log.info("script alterado (login=%s script=%s)", ctx.get("login"), reg["nome"],
                       extra={"acao": "CAD_ALTERAR"})
        return atual["id"], {}, aviso

    def alternar_ativo(self, ctx, ip, script_id, versao):
        """Desativa (CAD_DESATIVAR, com agendamentos ativos afetados) ou reativa (CAD_ALTERAR) o script."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = self._obter(script_id)
        if admin_crud.texto(versao, 64) != admin_crud.versao(atual, CAMPOS_EDITAVEIS):
            raise RepoConflito("versao divergente")
        novo_ativo = "N" if atual["ativo"] == "S" else "S"
        mudancas = {"ativo": novo_ativo}
        if novo_ativo == "S":
            # Reativacao refaz as checagens de arquivo (README §8.5).
            erros = {}
            aviso = self.validar_caminho(atual["path_file"], erros)
            if erros:
                raise OperacaoNegada(u"Não foi possível reativar: %s" % u" ".join(erros.values()))
            sha = self._hash_validado(atual["path_file"], aviso)
            if sha:
                mudancas["sha256_homologado"] = sha
        detalhe = admin_crud.detalhe_alteracoes(atual, dict(atual, **mudancas), CAMPOS_EDITAVEIS)
        acao = "CAD_DESATIVAR" if novo_ativo == "N" else "CAD_ALTERAR"
        if novo_ativo == "N":
            detalhe = u"%s; agendamentos ativos afetados: %d" % (detalhe, self._agendamentos_ativos(script_id=atual["id"]))
        alterado = self._catalogo.scripts_alterar(atual["id"], mudancas,
                                                  esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
                                                  auditoria=admin_crud.auditoria(ctx, ip, acao, detalhe))
        self._log.info("script %s (login=%s script=%s)", "desativado" if novo_ativo == "N" else "reativado",
                       ctx.get("login"), atual["nome"], extra={"acao": acao})
        return alterado

    # ------------------------------------------------------------ homologacao

    def homologacao(self, ctx, script_id):
        """Tela de homologacao: ambientes ativos e inativos ja homologados, com agendamentos ativos por ambiente."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        script = self._obter(script_id)
        marcados = set(self._catalogo.homologacao_obter(script["id"]))
        ambientes = []
        for a in self._catalogo.ambientes_listar(pagina=1, tamanho=_CATALOGO_MAX)["itens"]:
            if a["ativo"] != "S" and a["id"] not in marcados:
                continue
            ambientes.append({"id": a["id"], "nome": a["nome"], "descricao": a.get("descricao") or "",
                              "marcado": a["id"] in marcados, "inativo": a["ativo"] != "S",
                              "agendamentos_ativos": self._agendamentos_ativos(script_id=script["id"],
                                                                               ambiente=a["nome"])})
        return {"script": {"id": script["id"], "nome": script["nome"], "ativo": script["ativo"]},
                "ambientes": ambientes, "versao": _hash(sorted(marcados))}

    def salvar_homologacao(self, ctx, ip, script_id, ambiente_ids, versao):
        """Substitui a homologacao (so ambientes ativos podem ser adicionados; inativos existentes podem sair, D9).

        Retorna (diff ou None, erros). Auditoria CAD_ALTERAR com +/- e agendamentos ativos afetados.
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
        inativos = set(i for i, a in ambientes.items() if a["ativo"] != "S")
        if (enviados - set(atuais)) & inativos:
            return None, {CAMPO_GERAL: MSG_HOMOLOG_INATIVO}
        # D9 (README §4.3.A): inativo ja homologado pode sair (desmarcado); nunca entra de novo (checado acima).
        final = set(enviados)
        adicionados = sorted(ambientes[i]["nome"] for i in final - set(atuais))
        removidos = sorted(ambientes[i]["nome"] for i in set(atuais) - final)
        if not adicionados and not removidos:
            return None, {}
        partes = [u"+" + n for n in adicionados] + [u"-" + n for n in removidos]
        diff = u", ".join(partes)
        afetados = sum(self._agendamentos_ativos(script_id=script["id"], ambiente=n) for n in removidos)
        detalhe = admin_crud.detalhe_livre(u"homologação: %s%s" % (
            diff, (u"; agendamentos ativos afetados: %d" % afetados) if removidos else u""))
        try:
            self._catalogo.homologacao_salvar(script["id"], sorted(final), esperado=atuais,
                                              auditoria=admin_crud.auditoria(ctx, ip, "CAD_ALTERAR", detalhe))
        except RepoConflito:
            return None, {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        self._log.info("homologacao alterada (login=%s script=%s)", ctx.get("login"), script["nome"],
                       extra={"acao": "CAD_ALTERAR"})
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
            return {"id": p["id"], "codigo": p["codigo"], "label": p.get("label") or "",
                    "tipo_componente": p["tipo_componente"], "param_nomeado": p.get("param_nomeado") or "",
                    "sensivel": p.get("sensivel") == "S", "ativo": p.get("ativo") == "S"}

        vinculos = []
        for v in atuais:
            item = resumo(dicionario.get(v["parametro_id"], v))
            sigiloso = item["sensivel"]
            item.update(obrigatorio=v["obrigatorio"] == "S",
                        valor_padrao_sub="" if sigiloso else (v.get("valor_padrao_sub") or ""),
                        tem_sub=bool(v.get("valor_padrao_sub")))
            vinculos.append(item)
        disponiveis = [resumo(p) for p in sorted(dicionario.values(), key=lambda p: p["codigo"]) if p.get("ativo") == "S"]
        return {"script": {"id": script["id"], "nome": script["nome"], "tipo_param": script["tipo_param"]},
                "vinculos": vinculos, "disponiveis": disponiveis, "versao": _versao_vinculos(atuais, dicionario)}

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
        atuais_por_id = dict((v["parametro_id"], v) for v in atuais)
        vistos = set()
        final = []
        for posicao, item in enumerate(itens, 1):
            pid = _id(str(item.get("parametro_id"))) if isinstance(item, dict) else None
            if pid is None or pid not in dicionario:
                erros[CAMPO_GERAL] = MSG_VINCULOS_INVALIDOS
                return None
            p = dicionario[pid]
            if pid in vistos:
                erros[CAMPO_GERAL] = MSG_VINCULO_DUPLICADO % p["codigo"]
                return None
            vistos.add(pid)
            if p.get("ativo") != "S" and pid not in atuais_por_id:
                erros[CAMPO_GERAL] = MSG_VINCULO_INATIVO % p["codigo"]
                return None
            sub = item.get("valor_padrao_sub")
            sub = sub.strip() if isinstance(sub, str) else None
            if p.get("sensivel") == "S" and not sub and item.get("manter_sigiloso") is True and pid in atuais_por_id:
                sub = atuais_por_id[pid].get("valor_padrao_sub")
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
            v = dict(p, parametro_id=pid, ordem=posicao, obrigatorio="S" if item.get("obrigatorio") is True else "N",
                     valor_padrao_sub=sub)
            final.append(v)
        if script["tipo_param"] == "NENHUM" and final:
            erros[CAMPO_GERAL] = MSG_VINCULO_NENHUM
        elif script["tipo_param"] == "NOMEADO":
            sem_flag = [v["codigo"] for v in final if not v.get("param_nomeado")]
            if sem_flag:
                erros[CAMPO_GERAL] = msg_nomeado_sem_flag(sem_flag)
        return final

    @staticmethod
    def _descrever(vinculos):
        partes = []
        for v in vinculos:
            texto = v["codigo"] + ("*" if v["obrigatorio"] == "S" else "")
            if v.get("valor_padrao_sub"):
                texto += "=" + (MASCARA if v.get("sensivel") == "S" else str(v["valor_padrao_sub"]))
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
                script["id"], [dict((k, v[k]) for k in ("parametro_id", "ordem", "obrigatorio", "valor_padrao_sub"))
                               for v in final],
                esperado=_lidos(atuais), auditoria=admin_crud.auditoria(ctx, ip, "CAD_ALTERAR", detalhe))
        except RepoConflito:
            return None, {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        except RepoViolacao as exc:
            self._log.warning("vinculos rejeitados pelo repositorio (login=%s script=%s constraint=%s)",
                              ctx.get("login"), script["nome"], exc.constraint, extra={"acao": FUNCIONALIDADE})
            if exc.constraint == "sss_scr_nomeado_sem_flag":
                return None, {CAMPO_GERAL: msg_nomeado_sem_flag([v["codigo"] for v in final if not v.get("param_nomeado")])}
            if exc.constraint == "sss_scr_nenhum_vinculado":
                return None, {CAMPO_GERAL: MSG_VINCULO_NENHUM}
            return None, {CAMPO_GERAL: admin_crud.MSG_FALHA}
        self._log.info("vinculos alterados (login=%s script=%s)", ctx.get("login"), script["nome"],
                       extra={"acao": "CAD_ALTERAR"})
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
        try:
            path_guard.resolver(script["path_file"], self._owner_uids, dirs_sss=self._dirs_sss,
                                uids_proibidos=self._uids_proibidos)
        except PathGuardErro as exc:
            aviso = AVISO_NAO_ENCONTRADO if exc.codigo == Codigo.NAO_ENCONTRADO else MENSAGENS_PATH[exc.codigo]
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
                script_owner_uids=cfg.agent.script_owner_uids,
                sss_env=cfg.app.sss_env,
                log=sss_logging.obter_logger("sss_web", cfg),
                relogio=tickets.agora,
                dirs_sss=(cfg.logging.log_dir, cfg.agent.work_dir, cfg.agent.exec_work_dir),
                uids_proibidos=path_guard.uids_de_usuarios(u for _a, u in cfg.agent.usuarios_execucao),
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
