# -*- coding: utf-8 -*-
"""Cadastro de perfis e matriz de permissoes (README §4.3, §4.4, §10 tabelas 2-5 e 7).

Segue docs/PADRAO_CRUD_ADMIN.md. A protecao do ultimo administrador e a troca da matriz sao
operacoes unicas do repositorio (sem check-then-act aqui). Nao importa gluon fora de _servico.
"""
import collections
import re
import threading

import admin_crud
import ui_helpers
from admin_crud import CAMPO_GERAL, OperacaoNegada
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao

FUNCIONALIDADE = "CAD_PERFIS"
CAMPOS_EDITAVEIS = ("nome", "descricao", "is_admin", "ativo")
CAMPOS_INSERCAO = ("nome", "descricao", "is_admin")
TAMANHO_DESCRICAO = 100
_CATALOGO_MAX = 1000
_TAMANHO_CONTAGEM = 1  # so o total interessa
_SEM_GRUPO = u"Sem grupo"

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_NOME = re.compile(r"[A-Z0-9_]{1,30}")
_RE_FILTRO_NOME = re.compile(r"[A-Za-z0-9_]{1,30}")

MSG_NOME_OBRIGATORIO = u"Informe o nome do perfil."
MSG_NOME_INVALIDO = u"Use de 1 a 30 caracteres: letras maiúsculas, dígitos e _ (ex.: OPERADOR_PROD)."
MSG_NOME_DUPLICADO = u"Já existe um perfil com este nome."
MSG_DESCRICAO_TAMANHO = u"A descrição deve ter no máximo %d caracteres." % TAMANHO_DESCRICAO
MSG_ULTIMO_ADMIN = ui_helpers.mensagem("ultimo_admin")
MSG_AUTO_ADMIN = u"Você não pode remover o acesso administrativo do seu próprio perfil."
MSG_AUTO_DESATIVAR = u"Você não pode desativar o seu próprio perfil."
AFETADOS_MAX = 20
MSG_MATRIZ_ID_INVALIDO = u"A seleção contém itens inexistentes. Recarregue a página e tente novamente."
MSG_MATRIZ_INATIVO = u"Itens inativos não podem ser adicionados ao perfil. Recarregue a página e tente novamente."
AVISO_DESATIVACAO = u"Os usuários deste perfil perdem o acesso e têm a sessão encerrada no próximo clique."
AVISO_ADMIN = (u"Perfil administrativo: dispensa funcionalidades, ambientes e scripts, mas não a homologação "
               u"do script no ambiente nem as flags de ativo. A matriz abaixo fica registrada e passa a valer "
               u"se o perfil deixar de ser administrativo.")

_CAMPO_POR_CONSTRAINT = {
    "uk_tbsss_per_nome": ("nome", MSG_NOME_DUPLICADO),
}
# Prefixo de cada dimensao no diff auditado (README §4.4 PERM_ALTERAR).
_PREFIXOS = (("funcs", ""), ("ambs", "amb:"), ("scrs", "scr:"))


def _id(valor):
    valor = admin_crud.texto(valor, 11)
    if valor is None or not _RE_ID.fullmatch(valor) or int(valor) < 1:
        return None
    return int(valor)


def _ids(valores):
    """Lista de IDs enviada pelo formulario; qualquer valor nao numerico invalida o conjunto (None)."""
    if valores is None:
        return set()
    if not isinstance(valores, (list, tuple)):
        valores = [valores]
    ids = set()
    for v in valores:
        i = _id(v)
        if i is None:
            return None
        ids.add(i)
    return ids


def normalizar_filtros(entrada):
    """Filtros da lista vindos de request.vars: nome (trecho), ativo e is_admin ('S' | 'N')."""
    entrada = entrada or {}
    filtros = {}
    nome = admin_crud.texto(entrada.get("nome"), 30)
    if nome and _RE_FILTRO_NOME.fullmatch(nome):
        filtros["nome"] = nome
    for chave in ("ativo", "is_admin"):
        valor = admin_crud.texto(entrada.get(chave), 1)
        if valor in ("S", "N"):
            filtros[chave] = valor
    return filtros


def diff_matriz(antes, depois, rotulos):
    """'+EXEC_SCRIPT, -VER_LOGS, +amb:PRODUCAO, -scr:carga_diaria' (ordem: dimensao, rotulo); None se igual.

    antes/depois: {'funcs': set, 'ambs': set, 'scrs': set}; rotulos: {dimensao: {id: rotulo}}.
    """
    partes = []
    for dim, prefixo in _PREFIXOS:
        a, d = set(antes.get(dim) or ()), set(depois.get(dim) or ())
        nomes = rotulos.get(dim, {})
        mudancas = [(nomes.get(i, "#%s" % i), "+") for i in d - a] + [(nomes.get(i, "#%s" % i), "-") for i in a - d]
        for rotulo, sinal in sorted(mudancas):
            partes.append(u"%s%s%s" % (sinal, prefixo, rotulo))
    return admin_crud.detalhe_livre(u", ".join(partes)) if partes else None


class ServicoAdminPerfis(object):
    """Regras do cadastro de perfis e da matriz de permissoes com repositorios injetados."""

    def __init__(self, rbac_repo, catalogo, usuarios, log):
        self._rbac = rbac_repo
        self._catalogo = catalogo
        self._usuarios = usuarios
        self._log = log

    def _obter(self, perfil_id):
        pid = _id(perfil_id)
        if pid is None:
            raise RepoNaoEncontrado("perfil invalido")
        return self._rbac.perfis_obter(pid)

    def usuarios_ativos(self, perfil_id):
        """Quantidade de usuarios ativos do perfil (perdem o acesso se o perfil for desativado)."""
        return self._usuarios.listar(filtros={"perfil_id": perfil_id, "ativo": "S"}, pagina=1,
                                     tamanho=_TAMANHO_CONTAGEM)["total"]

    def usuarios_afetados(self, perfil_id):
        """(total, logins) dos usuarios ativos do perfil; no maximo AFETADOS_MAX logins (README §4.3.B.1)."""
        pagina = self._usuarios.listar(filtros={"perfil_id": perfil_id, "ativo": "S"}, pagina=1,
                                       tamanho=AFETADOS_MAX)
        return pagina["total"], [u["login"] for u in pagina["itens"]]

    # ------------------------------------------------------------- cadastro

    def listar(self, ctx, filtros, pagina, tamanho):
        """Pagina de perfis (ordem nome ASC)."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        return self._rbac.perfis_listar(filtros=filtros, pagina=pagina, tamanho=tamanho)

    def formulario(self, ctx, perfil_id=None):
        """Dados do formulario: vazio para inclusao; registro, versao e usuarios ativos na edicao."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        if perfil_id in (None, ""):
            return {"id": None, "nome": "", "descricao": "", "is_admin": "N", "ativo": "S", "versao": "",
                    "usuarios_ativos": 0, "usuarios_afetados": [], "proprio": False, "registro": None}
        perfil = self._obter(perfil_id)
        total, logins = self.usuarios_afetados(perfil["id"])
        return {
            "id": perfil["id"],
            "nome": perfil["nome"],
            "descricao": admin_crud.normalizar(perfil.get("descricao")) or "",
            "is_admin": perfil["is_admin"],
            "ativo": perfil["ativo"],
            "versao": admin_crud.versao(perfil, CAMPOS_EDITAVEIS),
            "usuarios_ativos": total,
            "usuarios_afetados": logins,
            "proprio": ctx.get("perfil_id") == perfil["id"],
            "registro": ui_helpers.registro(perfil),
        }

    def _validar(self, dados, erros):
        nome = admin_crud.identificador(dados.get("nome"), erros, "nome")
        if nome is None:
            erros["nome"] = MSG_NOME_OBRIGATORIO
        elif "nome" not in erros and not _RE_NOME.fullmatch(nome):
            erros["nome"] = MSG_NOME_INVALIDO
        descricao = admin_crud.texto_livre(dados.get("descricao"), erros, "descricao")
        if descricao is not None and len(descricao) > TAMANHO_DESCRICAO:
            erros["descricao"] = MSG_DESCRICAO_TAMANHO
        is_admin = "S" if admin_crud.texto(dados.get("is_admin"), 1) == "S" else "N"
        return nome, descricao, is_admin

    def _violacao(self, ctx, exc, erros):
        if exc.constraint == "sss_ultimo_admin":
            erros[CAMPO_GERAL] = MSG_ULTIMO_ADMIN
        else:
            campo, mensagem = _CAMPO_POR_CONSTRAINT.get(exc.constraint, (CAMPO_GERAL, admin_crud.MSG_FALHA))
            erros[campo] = mensagem
        self._log.warning("cadastro de perfil rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"acao": FUNCIONALIDADE})

    def salvar(self, ctx, ip, perfil_id, dados):
        """Inclui (perfil_id vazio) ou altera um perfil: nome, descricao, is_admin ('S' marcado).

        Retorna (id, erros). Remover is_admin do ultimo perfil admin ativo gera erro geral.
        Lanca RepoNaoEncontrado e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        erros = {}
        if perfil_id in (None, ""):
            nome, descricao, is_admin = self._validar(dados, erros)
            if erros:
                return None, erros
            novo = {"nome": nome, "descricao": descricao, "is_admin": is_admin, "ativo": "S"}
            auditoria = admin_crud.auditoria(ctx, ip, "CAD_INSERIR",
                                             admin_crud.detalhe_insercao(novo, CAMPOS_INSERCAO))
            try:
                criado = self._rbac.perfis_inserir(novo, auditoria=auditoria)
            except RepoViolacao as exc:
                self._violacao(ctx, exc, erros)
                return None, erros
            self._log.info("perfil incluido (login=%s perfil=%s)", ctx.get("login"), criado["nome"],
                           extra={"acao": "CAD_INSERIR"})
            return criado["id"], {}

        atual = self._obter(perfil_id)
        nome, descricao, is_admin = self._validar(dados, erros)
        if erros:
            return atual["id"], erros
        if admin_crud.texto(dados.get("versao"), 64) != admin_crud.versao(atual, CAMPOS_EDITAVEIS):
            erros[CAMPO_GERAL] = admin_crud.MSG_CONFLITO
            return atual["id"], erros
        if ctx.get("perfil_id") == atual["id"] and atual["is_admin"] == "S" and is_admin == "N":
            # Autoprotecao (README §4.3.B): vale mesmo havendo outros administradores.
            self._log.warning("remocao de is_admin do proprio perfil negada (login=%s perfil=%s)",
                              ctx.get("login"), atual["nome"], extra={"acao": "CAD_ALTERAR"})
            erros[CAMPO_GERAL] = MSG_AUTO_ADMIN
            return atual["id"], erros
        depois = dict(atual, nome=nome, descricao=descricao, is_admin=is_admin)
        detalhe = admin_crud.detalhe_alteracoes(atual, depois, CAMPOS_EDITAVEIS)
        if detalhe is None:
            return atual["id"], {}
        try:
            self._rbac.perfis_alterar(
                atual["id"], {"nome": nome, "descricao": descricao, "is_admin": is_admin},
                esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
                auditoria=admin_crud.auditoria(ctx, ip, "CAD_ALTERAR", detalhe))
        except RepoConflito:
            erros[CAMPO_GERAL] = admin_crud.MSG_CONFLITO
            return atual["id"], erros
        except RepoViolacao as exc:
            self._violacao(ctx, exc, erros)
            return atual["id"], erros
        self._log.info("perfil alterado (login=%s perfil=%s)", ctx.get("login"), nome, extra={"acao": "CAD_ALTERAR"})
        return atual["id"], {}

    def alternar_ativo(self, ctx, ip, perfil_id, versao):
        """Desativa (CAD_DESATIVAR, com usuarios afetados) ou reativa (CAD_ALTERAR) o perfil.

        Lanca OperacaoNegada (ultimo administrador), RepoConflito, RepoNaoEncontrado e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = self._obter(perfil_id)
        if admin_crud.texto(versao, 64) != admin_crud.versao(atual, CAMPOS_EDITAVEIS):
            raise RepoConflito("versao divergente")
        novo_ativo = "N" if atual["ativo"] == "S" else "S"
        if novo_ativo == "N" and ctx.get("perfil_id") == atual["id"]:
            self._log.warning("desativacao do proprio perfil negada (login=%s perfil=%s)",
                              ctx.get("login"), atual["nome"], extra={"acao": "CAD_DESATIVAR"})
            raise OperacaoNegada(MSG_AUTO_DESATIVAR)
        detalhe = admin_crud.detalhe_alteracoes(atual, dict(atual, ativo=novo_ativo), ("ativo",))
        acao = "CAD_DESATIVAR" if novo_ativo == "N" else "CAD_ALTERAR"
        if novo_ativo == "N":
            detalhe = u"%s; usuários ativos afetados: %d" % (detalhe, self.usuarios_ativos(atual["id"]))
        try:
            alterado = self._rbac.perfis_alterar(
                atual["id"], {"ativo": novo_ativo}, esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
                auditoria=admin_crud.auditoria(ctx, ip, acao, detalhe))
        except RepoViolacao as exc:
            if exc.constraint == "sss_ultimo_admin":
                self._log.warning("desativacao do ultimo perfil admin negada (login=%s perfil=%s)",
                                  ctx.get("login"), atual["nome"], extra={"acao": acao})
                raise OperacaoNegada(MSG_ULTIMO_ADMIN)
            raise
        self._log.info("perfil %s (login=%s perfil=%s)", "desativado" if novo_ativo == "N" else "reativado",
                       ctx.get("login"), atual["nome"], extra={"acao": acao})
        return alterado

    # ------------------------------------------------------------ quem pode

    def quem_pode(self, ctx, script_id=None, ambiente_id=None):
        """Consulta "Quem pode o que" (README §4.3.B.2, CR-004 T5): so leitura, sem metodo novo no contrato.

        Por script: perfis ativos que podem roda-lo e em quais ambientes (perfil_amb ∩ homologacao, so
        ambientes ativos; admin: todos os homologados ativos). Por ambiente: perfis que o acessam e os
        scripts homologados ali que podem rodar. Perfis inativos vao para 'inativos'.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        scripts = dict((s["id"], s) for s in self._catalogo.scripts_listar(pagina=1, tamanho=_CATALOGO_MAX)["itens"])
        ambientes = dict((a["id"], a) for a in self._catalogo.ambientes_listar(pagina=1, tamanho=_CATALOGO_MAX)["itens"])
        resultado = {"scripts": sorted(scripts.values(), key=lambda s: s["nome"]),
                     "ambientes": sorted(ambientes.values(), key=lambda a: a["nome"]),
                     "script": None, "ambiente": None, "perfis": [], "inativos": [], "aviso": None}
        sid, aid = _id(script_id), _id(ambiente_id)
        if sid is None and aid is None:
            return resultado
        exec_id = [f["id"] for f in self._rbac.funcionalidades_listar() if f["codigo"] == "EXEC_SCRIPT"]
        perfis = self._rbac.perfis_listar(pagina=1, tamanho=_CATALOGO_MAX)["itens"]
        homolog = {}

        def homologados(script):
            if script not in homolog:
                homolog[script] = set(i for i in self._catalogo.homologacao_obter(script)
                                      if ambientes.get(i, {}).get("ativo") == "S")
            return homolog[script]

        def linha(perfil, motivo, detalhes):
            return {"id": perfil["id"], "nome": perfil["nome"], "is_admin": perfil["is_admin"] == "S",
                    "motivo": motivo, "detalhes": detalhes, "usuarios_ativos": self.usuarios_ativos(perfil["id"])}

        if sid is not None and sid in scripts:
            script = scripts[sid]
            resultado["script"] = script
            if script.get("ativo") != "S":
                resultado["aviso"] = u"Este script está inativo: ninguém consegue rodá-lo agora."
            for p in perfis:
                m = self._rbac.matriz_obter(p["id"])
                if p["is_admin"] == "S":
                    ambs, motivo = homologados(sid), u"administrador"
                elif exec_id and exec_id[0] in m["funcs"] and sid in m["scrs"]:
                    ambs, motivo = homologados(sid) & set(m["ambs"]), u"tem Disparar Scripts, o ambiente e o script"
                else:
                    continue
                if not ambs:
                    continue
                item = linha(p, motivo, sorted(ambientes[a]["nome"] for a in ambs))
                resultado["perfis" if p["ativo"] == "S" else "inativos"].append(item)
        elif aid is not None and aid in ambientes:
            amb = ambientes[aid]
            resultado["ambiente"] = amb
            if amb.get("ativo") != "S":
                resultado["aviso"] = u"Este ambiente está inativo: nenhum script roda nele agora."
            ativos = [s for s in scripts.values() if s.get("ativo") == "S" and aid in homologados(s["id"])]
            for p in perfis:
                m = self._rbac.matriz_obter(p["id"])
                if p["is_admin"] == "S":
                    lista, motivo = ativos, u"administrador"
                elif exec_id and exec_id[0] in m["funcs"] and aid in m["ambs"]:
                    lista, motivo = [s for s in ativos if s["id"] in m["scrs"]], u"tem Disparar Scripts e o ambiente"
                else:
                    continue
                item = linha(p, motivo, sorted(s["nome"] for s in lista))
                resultado["perfis" if p["ativo"] == "S" else "inativos"].append(item)
        else:
            raise RepoNaoEncontrado("script ou ambiente inexistente")
        return resultado

    # --------------------------------------------------------------- matriz

    def _catalogo_matriz(self):
        funcs = self._rbac.funcionalidades_listar()
        ambs = self._catalogo.ambientes_listar(pagina=1, tamanho=_CATALOGO_MAX)["itens"]
        scrs = self._catalogo.scripts_listar(pagina=1, tamanho=_CATALOGO_MAX)["itens"]
        return {"funcs": dict((f["id"], f) for f in funcs), "ambs": dict((a["id"], a) for a in ambs),
                "scrs": dict((s["id"], s) for s in scrs)}

    @staticmethod
    def _rotulos(cat):
        return {"funcs": dict((i, f["codigo"]) for i, f in cat["funcs"].items()),
                "ambs": dict((i, a["nome"]) for i, a in cat["ambs"].items()),
                "scrs": dict((i, s["nome"]) for i, s in cat["scrs"].items())}

    def matriz(self, ctx, perfil_id):
        """Matriz do perfil para a tela: itens ativos e os inativos ja associados (somente leitura).

        Retorna {perfil, perm_versao, aviso_admin, funcs: [{grupo, itens}], ambs: [{grupo, itens}],
        scrs: [{grupo, itens}]}; cada item tem id, rotulo, detalhe, marcado, inativo e rotulo_diff.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        perfil = self._obter(perfil_id)
        atual = self._rbac.matriz_obter(perfil["id"])
        cat = self._catalogo_matriz()
        marcados = dict((dim, set(atual[dim])) for dim, _p in _PREFIXOS)

        def item(dim, reg, rotulo, detalhe, prefixo):
            return {"id": reg["id"], "rotulo": rotulo, "detalhe": detalhe or "",
                    "marcado": reg["id"] in marcados[dim], "inativo": reg.get("ativo") != "S",
                    "rotulo_diff": prefixo + rotulo}

        def agrupar(dim, chave_grupo, montar):
            grupos = collections.OrderedDict()
            regs = sorted(cat[dim].values(), key=lambda r: (chave_grupo(r), r.get("codigo") or r.get("nome"), r["id"]))
            for reg in regs:
                if reg.get("ativo") != "S" and reg["id"] not in marcados[dim]:
                    continue
                grupos.setdefault(chave_grupo(reg), []).append(montar(reg))
            return [{"grupo": g, "itens": itens} for g, itens in grupos.items()]

        return {
            "perfil": {"id": perfil["id"], "nome": perfil["nome"], "is_admin": perfil["is_admin"],
                       "ativo": perfil["ativo"]},
            "perm_versao": perfil["perm_versao"],
            "aviso_admin": AVISO_ADMIN if perfil["is_admin"] == "S" else None,
            "funcs": agrupar("funcs", lambda r: r.get("modulo") or _SEM_GRUPO,
                             lambda r: item("funcs", r, r["codigo"], r.get("nome"), "")),
            "ambs": agrupar("ambs", lambda r: u"Ambientes",
                            lambda r: item("ambs", r, r["nome"], r.get("descricao"), "amb:")),
            "scrs": agrupar("scrs", lambda r: u"%s / %s" % (r.get("grupo") or _SEM_GRUPO, r.get("categoria") or "-"),
                            lambda r: item("scrs", r, r["nome"], r.get("descricao"), "scr:")),
        }

    def salvar_matriz(self, ctx, ip, perfil_id, funcs, ambs, scrs, perm_versao):
        """Substitui a matriz do perfil (um unico POST com as tres listas) e audita PERM_ALTERAR com o diff.

        Associacoes existentes a itens inativos podem ser removidas, nunca readicionadas (README §4.3.B.1);
        so itens ativos podem ser adicionados; ID inexistente rejeita a operacao inteira. Retorna (diff ou None se nada mudou, erros).
        Lanca RepoNaoEncontrado e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        perfil = self._obter(perfil_id)
        enviados = {"funcs": _ids(funcs), "ambs": _ids(ambs), "scrs": _ids(scrs)}
        if any(v is None for v in enviados.values()):
            return None, {CAMPO_GERAL: MSG_MATRIZ_ID_INVALIDO}
        versao = _id(perm_versao)
        if versao is None or versao != perfil["perm_versao"]:
            return None, {CAMPO_GERAL: admin_crud.MSG_CONFLITO}

        cat = self._catalogo_matriz()
        atual = dict((dim, set(ids)) for dim, ids in self._rbac.matriz_obter(perfil["id"]).items())
        final = {}
        for dim, _prefixo in _PREFIXOS:
            desconhecidos = enviados[dim] - set(cat[dim])
            if desconhecidos:
                self._log.warning("matriz rejeitada: IDs inexistentes (login=%s perfil=%s dimensao=%s ids=%s)",
                                  ctx.get("login"), perfil["nome"], dim, sorted(desconhecidos),
                                  extra={"acao": "PERM_ALTERAR"})
                return None, {CAMPO_GERAL: MSG_MATRIZ_ID_INVALIDO}
            inativos = set(i for i, r in cat[dim].items() if r.get("ativo") != "S")
            if (enviados[dim] - atual[dim]) & inativos:
                return None, {CAMPO_GERAL: MSG_MATRIZ_INATIVO}
            # Inativo ja associado pode sair (desmarcado); nunca entra de novo (checado acima).
            final[dim] = set(enviados[dim])

        diff = diff_matriz(atual, final, self._rotulos(cat))
        if diff is None:
            return None, {}
        try:
            self._rbac.matriz_salvar(perfil["id"], sorted(final["funcs"]), sorted(final["ambs"]),
                                     sorted(final["scrs"]), perm_versao_esperada=versao,
                                     auditoria=admin_crud.auditoria(ctx, ip, "PERM_ALTERAR", diff))
        except RepoConflito:
            return None, {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        except RepoViolacao:
            self._log.warning("matriz rejeitada pelo repositorio (login=%s perfil=%s)", ctx.get("login"),
                              perfil["nome"], extra={"acao": "PERM_ALTERAR"})
            return None, {CAMPO_GERAL: MSG_MATRIZ_ID_INVALIDO}
        self._log.info("matriz de permissoes alterada (login=%s perfil=%s)", ctx.get("login"), perfil["nome"],
                       extra={"acao": "PERM_ALTERAR"})
        return diff, {}


_padrao = None
_lock_padrao = threading.Lock()


def _servico():
    global _padrao
    with _lock_padrao:
        if _padrao is None:
            from gluon import current
            import sss_logging
            fabrica = current.repo_factory
            _padrao = ServicoAdminPerfis(
                rbac_repo=fabrica.obter("rbac"),
                catalogo=fabrica.obter("catalogo"),
                usuarios=fabrica.obter("usuarios"),
                log=sss_logging.obter_logger("sss_web", current.sss_cfg),
            )
        return _padrao


def listar(ctx, filtros, pagina, tamanho):
    """Pagina de perfis (servico padrao)."""
    return _servico().listar(ctx, filtros, pagina, tamanho)


def formulario(ctx, perfil_id=None):
    """Dados do formulario de perfil (servico padrao)."""
    return _servico().formulario(ctx, perfil_id)


def salvar(ctx, ip, perfil_id, dados):
    """Inclusao ou alteracao de perfil (servico padrao)."""
    return _servico().salvar(ctx, ip, perfil_id, dados)


def alternar_ativo(ctx, ip, perfil_id, versao):
    """Desativacao/reativacao de perfil (servico padrao)."""
    return _servico().alternar_ativo(ctx, ip, perfil_id, versao)


def matriz(ctx, perfil_id):
    """Matriz de permissoes do perfil para a tela (servico padrao)."""
    return _servico().matriz(ctx, perfil_id)


def salvar_matriz(ctx, ip, perfil_id, funcs, ambs, scrs, perm_versao):
    """Gravacao da matriz de permissoes (servico padrao)."""
    return _servico().salvar_matriz(ctx, ip, perfil_id, funcs, ambs, scrs, perm_versao)


def quem_pode(ctx, script_id=None, ambiente_id=None):
    """Consulta "Quem pode o que" (servico padrao)."""
    return _servico().quem_pode(ctx, script_id, ambiente_id)
