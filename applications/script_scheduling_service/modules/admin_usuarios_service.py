# -*- coding: utf-8 -*-
"""Cadastro de usuarios (README §4.2, §4.3.B, §4.4, §10 tabela 9). Padrao em docs/PADRAO_CRUD_ADMIN.md.

Senha e hash nunca saem deste modulo: listagem e formulario devolvem registros sem senha_hash, e a
auditoria registra apenas o fato ('senha redefinida'). Nao importa gluon fora de _servico.
"""
import re
import threading

import admin_crud
import auth_service
import security
import ui_helpers
from admin_crud import CAMPO_GERAL, OperacaoNegada
from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao

FUNCIONALIDADE = "CAD_USUARIOS"
CAMPOS_EDITAVEIS = ("nome", "perfil_id", "ativo")
# Referencias aparecem pelo nome na auditoria de inclusao (README §4.4): perfil, nao perfil_id.
CAMPOS_INSERCAO = ("login", "nome", "perfil")
TAMANHO_NOME = 60
_PERFIS_MAX = 1000
_CAMPOS_PUBLICOS = ("id", "login", "nome", "perfil_id", "tentativas_falha", "bloqueado_ate", "ultimo_login",
                    "senha_alterada_em", "ativo", "created_at")

_RE_ID = re.compile(r"[0-9]{1,10}")
_RE_LOGIN = re.compile(r"[a-z0-9._-]{3,30}")
_RE_FILTRO = re.compile(r"[A-Za-z0-9._ -]{1,60}")

MSG_LOGIN_OBRIGATORIO = u"Informe o login."
MSG_LOGIN_INVALIDO = u"Use de 3 a 30 caracteres: letras minúsculas, dígitos, ponto, _ ou - (ex.: maria.silva)."
MSG_LOGIN_DUPLICADO = u"Já existe um usuário com este login."
MSG_NOME_OBRIGATORIO = u"Informe o nome."
MSG_NOME_TAMANHO = u"O nome deve ter no máximo %d caracteres." % TAMANHO_NOME
MSG_PERFIL_INVALIDO = u"Selecione um perfil ativo."
MSG_SENHA_OBRIGATORIA = u"Informe a senha."
MSG_SENHA_LONGA = u"A senha deve ter no máximo %d caracteres." % auth_service.SENHA_MAX
MSG_CONFIRMACAO = auth_service.MSG_CONFIRMACAO
MSG_ULTIMO_ADMIN = ui_helpers.mensagem("ultimo_admin")
MSG_AUTO_DESATIVAR = u"Operação negada: você não pode desativar o próprio usuário."
MSG_AUTO_PERFIL = u"Operação negada: você não pode remover o próprio perfil administrativo."
MSG_AUTO_SENHA = u"Para trocar a sua própria senha, use \"Minha senha\" (exige a senha atual)."
MSG_SO_ADMIN = (u"Só um administrador pode alterar um usuário administrador ou dar o perfil de administrador. "
                u"Peça a um administrador.")
AJUDA_POLITICA = u"Mínimo de %d caracteres. A senha nunca é exibida nem registrada." % security.SENHA_MIN
AVISO_DESATIVACAO = u"O usuário perde o acesso e tem a sessão encerrada no próximo clique."

_CAMPO_POR_CONSTRAINT = {
    "uk_tbsss_usr_login": ("login", MSG_LOGIN_DUPLICADO),
    "ck_tbsss_usr_login": ("login", MSG_LOGIN_INVALIDO),
    "fk_tbsss_usr_per": ("perfil_id", MSG_PERFIL_INVALIDO),
    "sss_ultimo_admin": (CAMPO_GERAL, MSG_ULTIMO_ADMIN),
}


def _id(valor):
    valor = admin_crud.texto(valor, 11)
    if valor is None or not _RE_ID.fullmatch(valor) or int(valor) < 1:
        return None
    return int(valor)


def publico(usuario):
    """Copia do usuario sem senha_hash (e sem qualquer campo nao listado)."""
    return dict((c, usuario.get(c)) for c in _CAMPOS_PUBLICOS)


def normalizar_filtros(entrada):
    """Filtros da lista: login, nome (trechos), perfil_id e situacao ('S' | 'N' | 'B' bloqueados)."""
    entrada = entrada or {}
    filtros = {}
    for chave in ("login", "nome"):
        valor = admin_crud.texto(entrada.get(chave), 60)
        if valor and _RE_FILTRO.fullmatch(valor):
            filtros[chave] = valor
    perfil = _id(entrada.get("perfil_id"))
    if perfil is not None:
        filtros["perfil_id"] = perfil
    situacao = admin_crud.texto(entrada.get("situacao"), 1)
    if situacao in ("S", "N", "B"):
        filtros["situacao"] = situacao
    return filtros


class ServicoAdminUsuarios(object):
    """Regras do cadastro de usuarios com repositorios, relogio e log injetados."""

    def __init__(self, usuarios, rbac_repo, log, relogio=None):
        self._usuarios = usuarios
        self._rbac = rbac_repo
        self._log = log
        # Relogio do banco (README §4.2): bloqueio vigente e filtro "Bloqueados" comparam com SYSDATE.
        self._relogio = relogio or usuarios.agora

    def _obter(self, usuario_id):
        uid = _id(usuario_id)
        if uid is None:
            raise RepoNaoEncontrado("usuario invalido")
        return self._usuarios.obter_por_id(uid)

    def perfis(self, apenas_ativos=False):
        """Perfis para selecao: lista de {id, nome, is_admin, ativo} ordenada por nome."""
        itens = self._rbac.perfis_listar(filtros={"ativo": "S"} if apenas_ativos else None, pagina=1,
                                         tamanho=_PERFIS_MAX)["itens"]
        return [{"id": p["id"], "nome": p["nome"], "is_admin": p["is_admin"], "ativo": p["ativo"]} for p in itens]

    def _perfil_admin(self, perfil_id):
        try:
            return self._rbac.perfis_obter(perfil_id).get("is_admin") == "S"
        except RepoNaoEncontrado:
            return False

    def _exigir_admin(self, ctx, condicao, operacao):
        admin_crud.exigir_admin(ctx, condicao, MSG_SO_ADMIN, self._log, operacao)

    def bloqueado(self, usuario):
        """True se o bloqueio por tentativas ainda vale agora."""
        ate = usuario.get("bloqueado_ate")
        return ate is not None and ate > self._relogio()

    # ----------------------------------------------------------------- leitura

    def listar(self, ctx, filtros, pagina, tamanho):
        """Pagina de usuarios (login ASC) sem senha_hash, com perfil_nome e bloqueado."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        repo_filtros = dict((k, v) for k, v in filtros.items() if k != "situacao")
        situacao = filtros.get("situacao")
        if situacao in ("S", "N"):
            repo_filtros["ativo"] = situacao
        elif situacao == "B":
            repo_filtros["bloqueado_em"] = self._relogio()
        resultado = self._usuarios.listar(filtros=repo_filtros, pagina=pagina, tamanho=tamanho)
        nomes = dict((p["id"], p["nome"]) for p in self.perfis())
        itens = []
        for u in resultado["itens"]:
            item = publico(u)
            item["perfil_nome"] = nomes.get(u["perfil_id"], "#%s" % u["perfil_id"])
            item["bloqueado"] = self.bloqueado(u)
            itens.append(item)
        return dict(resultado, itens=itens)

    def formulario(self, ctx, usuario_id=None):
        """Dados do formulario sem senha_hash; na edicao inclui versao, bloqueio e se e o proprio usuario."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        if usuario_id in (None, ""):
            return {"id": None, "login": "", "nome": "", "perfil_id": None, "ativo": "S", "versao": "",
                    "bloqueado": False, "bloqueado_ate": None, "tentativas_falha": 0, "proprio": False,
                    "registro": None}
        u = self._obter(usuario_id)
        dados = publico(u)
        dados.update(versao=admin_crud.versao(u, CAMPOS_EDITAVEIS), bloqueado=self.bloqueado(u),
                     proprio=u["id"] == ctx.get("usuario_id"), registro=ui_helpers.registro(u, ctx))
        return dados

    # ----------------------------------------------------------------- escrita

    def _violacao(self, ctx, exc, erros):
        campo, mensagem = _CAMPO_POR_CONSTRAINT.get(exc.constraint, (CAMPO_GERAL, admin_crud.MSG_FALHA))
        erros[campo] = mensagem
        self._log.warning("cadastro de usuario rejeitado pelo repositorio (login=%s constraint=%s)",
                          ctx.get("login"), exc.constraint, extra={"acao": FUNCIONALIDADE})

    def _perfil_ativo(self, valor, erros, atual=None):
        """Perfil escolhido: precisa estar ativo, exceto quando a edicao mantem o perfil atual."""
        pid = _id(valor)
        todos = dict((p["id"], p) for p in self.perfis())
        if pid not in todos or (todos[pid]["ativo"] != "S" and pid != atual):
            erros["perfil_id"] = MSG_PERFIL_INVALIDO
            return None, None
        return pid, todos[pid]

    def _senha(self, senha, confirmacao, erros, campo="senha"):
        if not isinstance(senha, str) or not senha:
            erros[campo] = MSG_SENHA_OBRIGATORIA
            return None
        if len(senha) > auth_service.SENHA_MAX:
            erros[campo] = MSG_SENHA_LONGA
            return None
        problemas = security.validar_politica_senha(senha)
        if problemas:
            erros[campo] = problemas[0]
            return None
        if confirmacao != senha:
            erros["confirmacao"] = MSG_CONFIRMACAO
            return None
        return senha

    def _nome(self, valor, erros):
        nome = admin_crud.texto_livre(valor, erros, "nome")
        if nome is None:
            erros["nome"] = MSG_NOME_OBRIGATORIO
        elif "nome" not in erros and len(nome) > TAMANHO_NOME:
            erros["nome"] = MSG_NOME_TAMANHO
        return nome

    def salvar(self, ctx, ip, usuario_id, dados):
        """Inclui (login, nome, perfil_id, senha, confirmacao) ou altera (nome, perfil_id, versao).

        Retorna (id, erros). Na edicao o login e a senha enviados sao ignorados. Lanca
        RepoNaoEncontrado e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        erros = {}
        if usuario_id in (None, ""):
            login = admin_crud.identificador(dados.get("login"), erros, "login")
            if login is None:
                erros["login"] = MSG_LOGIN_OBRIGATORIO
            elif "login" in erros:
                pass
            elif not _RE_LOGIN.fullmatch(login):
                erros["login"] = MSG_LOGIN_INVALIDO
            nome = self._nome(dados.get("nome"), erros)
            perfil_id, perfil = self._perfil_ativo(dados.get("perfil_id"), erros)
            senha = self._senha(dados.get("senha"), dados.get("confirmacao"), erros)
            if erros:
                return None, erros
            try:
                self._exigir_admin(ctx, perfil["is_admin"] == "S", "CAD_INSERIR")
            except OperacaoNegada as exc:
                return None, {"perfil_id": exc.mensagem}
            agora = self._relogio()
            novo = {"login": login, "nome": nome, "perfil_id": perfil_id, "ativo": "S",
                    "senha_hash": security.hash_senha(senha), "senha_alterada_em": agora}
            auditoria = admin_crud.auditoria(ctx, ip, "CAD_INSERIR",
                                             admin_crud.detalhe_insercao(dict(novo, perfil=perfil["nome"]),
                                                                         CAMPOS_INSERCAO))
            try:
                criado = self._usuarios.inserir(novo, auditoria=auditoria)
            except RepoViolacao as exc:
                self._violacao(ctx, exc, erros)
                return None, erros
            self._log.info("usuario incluido (login=%s usuario=%s)", ctx.get("login"), login,
                           extra={"acao": "CAD_INSERIR"})
            return criado["id"], {}

        atual = self._obter(usuario_id)
        nome = self._nome(dados.get("nome"), erros)
        perfil_id, perfil = self._perfil_ativo(dados.get("perfil_id"), erros, atual["perfil_id"])
        if erros:
            return atual["id"], erros
        if atual["id"] == ctx.get("usuario_id") and ctx.get("is_admin") is True and perfil["is_admin"] != "S":
            return atual["id"], {CAMPO_GERAL: MSG_AUTO_PERFIL}
        try:
            self._exigir_admin(ctx, perfil["is_admin"] == "S" or self._perfil_admin(atual["perfil_id"]),
                               "CAD_ALTERAR")
        except OperacaoNegada as exc:
            return atual["id"], {CAMPO_GERAL: exc.mensagem}
        if admin_crud.texto(dados.get("versao"), 64) != admin_crud.versao(atual, CAMPOS_EDITAVEIS):
            return atual["id"], {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        depois = dict(atual, nome=nome, perfil_id=perfil_id)
        detalhe = admin_crud.detalhe_alteracoes(atual, depois, CAMPOS_EDITAVEIS)
        if detalhe is None:
            return atual["id"], {}
        try:
            self._usuarios.alterar(atual["id"], {"nome": nome, "perfil_id": perfil_id},
                                   esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
                                   auditoria=admin_crud.auditoria(ctx, ip, "CAD_ALTERAR", detalhe))
        except RepoConflito:
            return atual["id"], {CAMPO_GERAL: admin_crud.MSG_CONFLITO}
        except RepoViolacao as exc:
            self._violacao(ctx, exc, erros)
            return atual["id"], erros
        self._log.info("usuario alterado (login=%s usuario=%s)", ctx.get("login"), atual["login"],
                       extra={"acao": "CAD_ALTERAR"})
        return atual["id"], {}

    def alternar_ativo(self, ctx, ip, usuario_id, versao):
        """Desativa (CAD_DESATIVAR) ou reativa (CAD_ALTERAR) o usuario.

        Lanca OperacaoNegada (proprio usuario ou ultimo administrador), RepoConflito,
        RepoNaoEncontrado e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = self._obter(usuario_id)
        novo_ativo = "N" if atual["ativo"] == "S" else "S"
        if novo_ativo == "N" and atual["id"] == ctx.get("usuario_id"):
            raise OperacaoNegada(MSG_AUTO_DESATIVAR)
        self._exigir_admin(ctx, self._perfil_admin(atual["perfil_id"]), "CAD_DESATIVAR")
        if admin_crud.texto(versao, 64) != admin_crud.versao(atual, CAMPOS_EDITAVEIS):
            raise RepoConflito("versao divergente")
        detalhe = admin_crud.detalhe_alteracoes(atual, dict(atual, ativo=novo_ativo), ("ativo",))
        acao = "CAD_DESATIVAR" if novo_ativo == "N" else "CAD_ALTERAR"
        try:
            alterado = self._usuarios.alterar(atual["id"], {"ativo": novo_ativo},
                                              esperado=admin_crud.esperado(atual, CAMPOS_EDITAVEIS),
                                              auditoria=admin_crud.auditoria(ctx, ip, acao, detalhe))
        except RepoViolacao as exc:
            if exc.constraint == "sss_ultimo_admin":
                self._log.warning("desativacao do ultimo admin negada (login=%s usuario=%s)", ctx.get("login"),
                                  atual["login"], extra={"acao": acao})
                raise OperacaoNegada(MSG_ULTIMO_ADMIN)
            raise
        self._log.info("usuario %s (login=%s usuario=%s)", "desativado" if novo_ativo == "N" else "reativado",
                       ctx.get("login"), atual["login"], extra={"acao": acao})
        return publico(alterado)

    def redefinir_senha(self, ctx, ip, usuario_id, senha, confirmacao):
        """Define nova senha (politica + confirmacao), zera tentativas e bloqueio; audita sem o valor.

        Retorna erros por campo ({} no sucesso). Lanca OperacaoNegada (propria senha: usar
        'Minha senha'), RepoNaoEncontrado e AcessoNegado.
        """
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = self._obter(usuario_id)
        if atual["id"] == ctx.get("usuario_id"):
            raise OperacaoNegada(MSG_AUTO_SENHA)
        self._exigir_admin(ctx, self._perfil_admin(atual["perfil_id"]), "CAD_ALTERAR")
        erros = {}
        senha = self._senha(senha, confirmacao, erros)
        if erros:
            return erros
        self._usuarios.definir_senha(atual["id"], security.hash_senha(senha), self._relogio(),
                                     auditoria=admin_crud.auditoria(ctx, ip, "CAD_ALTERAR", u"senha redefinida"))
        self._log.info("senha redefinida (login=%s usuario=%s)", ctx.get("login"), atual["login"],
                       extra={"acao": "CAD_ALTERAR"})
        return {}

    def desbloquear(self, ctx, ip, usuario_id):
        """Zera tentativas e bloqueio do usuario, com auditoria CAD_ALTERAR."""
        admin_crud.exigir_func(ctx, FUNCIONALIDADE)
        atual = self._obter(usuario_id)
        self._exigir_admin(ctx, self._perfil_admin(atual["perfil_id"]), "CAD_ALTERAR")
        detalhe = u"desbloqueado (tentativas_falha: %s; bloqueado_ate: %s)" % (
            atual.get("tentativas_falha") or 0, atual.get("bloqueado_ate") or u"(vazio)")
        alterado = self._usuarios.desbloquear(atual["id"],
                                              auditoria=admin_crud.auditoria(ctx, ip, "CAD_ALTERAR", detalhe))
        self._log.info("usuario desbloqueado (login=%s usuario=%s)", ctx.get("login"), atual["login"],
                       extra={"acao": "CAD_ALTERAR"})
        return publico(alterado)


_padrao = None
_lock_padrao = threading.Lock()


def _servico():
    global _padrao
    with _lock_padrao:
        if _padrao is None:
            from gluon import current
            import sss_logging
            fabrica = current.repo_factory
            _padrao = ServicoAdminUsuarios(
                usuarios=fabrica.obter("usuarios"),
                rbac_repo=fabrica.obter("rbac"),
                log=sss_logging.obter_logger("sss_web", current.sss_cfg),
            )
        return _padrao


def listar(ctx, filtros, pagina, tamanho):
    """Pagina de usuarios sem senha_hash (servico padrao)."""
    return _servico().listar(ctx, filtros, pagina, tamanho)


def formulario(ctx, usuario_id=None):
    """Dados do formulario de usuario (servico padrao)."""
    return _servico().formulario(ctx, usuario_id)


def perfis(apenas_ativos=False):
    """Perfis para selecao e filtro (servico padrao)."""
    return _servico().perfis(apenas_ativos)


def salvar(ctx, ip, usuario_id, dados):
    """Inclusao ou alteracao de usuario (servico padrao)."""
    return _servico().salvar(ctx, ip, usuario_id, dados)


def alternar_ativo(ctx, ip, usuario_id, versao):
    """Desativacao/reativacao de usuario (servico padrao)."""
    return _servico().alternar_ativo(ctx, ip, usuario_id, versao)


def redefinir_senha(ctx, ip, usuario_id, senha, confirmacao):
    """Redefinicao de senha pelo administrador (servico padrao)."""
    return _servico().redefinir_senha(ctx, ip, usuario_id, senha, confirmacao)


def desbloquear(ctx, ip, usuario_id):
    """Desbloqueio do usuario (servico padrao)."""
    return _servico().desbloquear(ctx, ip, usuario_id)
