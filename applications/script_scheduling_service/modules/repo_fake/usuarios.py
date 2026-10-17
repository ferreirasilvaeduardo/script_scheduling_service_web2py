# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de usuarios (README §2.5, §4.2, §10)."""
import copy
import datetime
import re

from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao
from repo_fake.store import paginar
from repo_usuarios import RepoUsuarios

_RE_LOGIN = re.compile(r"^[a-z0-9._-]{3,30}$")


class RepoUsuariosFake(RepoUsuarios):
    """Implementacao em memoria com semantica Oracle para usuarios."""

    def __init__(self, store):
        self._store = store

    def obter_por_login(self, login):
        """Retorna dict com dados do usuario ou None se nao encontrado."""
        with self._store.lock_usuarios:
            for u in self._store.usuarios.values():
                if u["login"] == login:
                    return copy.deepcopy(u)
            return None

    def obter_por_id(self, id):
        """Retorna dict com dados do usuario pelo ID ou lanca RepoNaoEncontrado."""
        with self._store.lock_usuarios:
            if id not in self._store.usuarios:
                raise RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)
            return copy.deepcopy(self._store.usuarios[id])

    def obter_estado_sessao(self, usuario_id):
        """Retorna estado composto de sessao (usuario + perfil + perm_versao)."""
        with self._store.lock_rbac:
            with self._store.lock_usuarios:
                if usuario_id not in self._store.usuarios:
                    raise RepoNaoEncontrado("Usuario ID %s nao encontrado" % usuario_id)
                u = self._store.usuarios[usuario_id]
                perfil_id = u["perfil_id"]
                if perfil_id not in self._store.perfis:
                    raise RepoNaoEncontrado("Perfil ID %s nao encontrado" % perfil_id)
                p = self._store.perfis[perfil_id]

                return {
                    "usuario_id": u["id"],
                    "login": u["login"],
                    "nome": u["nome"],
                    "usuario_ativo": u["ativo"],
                    "perfil_id": p["id"],
                    "perfil_nome": p["nome"],
                    "perfil_ativo": p["ativo"],
                    "is_admin": p["is_admin"],
                    "perm_versao": p["perm_versao"],
                }

    def listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista usuarios paginados com desempate por id."""
        filtros = filtros or {}
        with self._store.lock_usuarios:
            lista = list(self._store.usuarios.values())

            login_f = filtros.get("login")
            if login_f:
                lista = [u for u in lista if login_f.lower() in u["login"].lower()]

            nome_f = filtros.get("nome")
            if nome_f:
                lista = [u for u in lista if nome_f.lower() in u["nome"].lower()]

            perfil_f = filtros.get("perfil_id")
            if perfil_f is not None:
                lista = [u for u in lista if u["perfil_id"] == int(perfil_f)]

            ativo_f = filtros.get("ativo")
            if ativo_f:
                lista = [u for u in lista if u["ativo"] == ativo_f]

            bloq_f = filtros.get("bloqueado_em")
            if bloq_f is not None:
                lista = [u for u in lista if u.get("bloqueado_ate") is not None and u["bloqueado_ate"] > bloq_f]

            # Ordenacao estavel: login ASC, id ASC
            lista.sort(key=lambda x: (x.get("login", ""), x["id"]))
            return paginar(lista, pagina=pagina, tamanho=tamanho)

    def _auditar(self, auditoria, usuario_id):
        for item in ([auditoria] if isinstance(auditoria, dict) else (auditoria or ())):
            self._store.registrar_auditoria_interno(
                ator=item.get("ator"),
                ip=item.get("ip"),
                acao=item["acao"],
                entidade="tbsss_usuarios",
                entidade_id=usuario_id,
                detalhe=item.get("detalhe"),
            )

    def agora(self):
        """SYSDATE simulado pelo relogio do store."""
        return self._store.agora()

    def _eh_admin_ativo(self, usuario):
        p = self._store.perfis.get(usuario["perfil_id"])
        return usuario["ativo"] == "S" and p is not None and p["ativo"] == "S" and p["is_admin"] == "S"

    def inserir(self, dados, auditoria=None, ator=None):
        """Insere novo usuario com validacoes de integridade, auditando na mesma operacao."""
        # Ordem de locks unica no FAKE: rbac e depois usuarios (como admins_ativos_bloquear).
        with self._store.lock_rbac:
            with self._store.lock_usuarios:
                ator = self._store.ator_registro(auditoria, ator)
                login = dados.get("login")
                if not login or not _RE_LOGIN.fullmatch(login):
                    raise RepoViolacao("Login invalido (esperado: 3-30 caracteres [a-z0-9._-])", constraint="ck_tbsss_usr_login")

                for u in self._store.usuarios.values():
                    if u["login"] == login:
                        raise RepoViolacao("Login '%s' ja existe" % login, constraint="uk_tbsss_usr_login")

                perfil_id = dados.get("perfil_id")
                if perfil_id not in self._store.perfis:
                    raise RepoViolacao("Perfil ID %s nao existe" % perfil_id, constraint="fk_tbsss_usr_per")

                ativo = dados.get("ativo", "S")
                if ativo not in ("S", "N"):
                    raise RepoViolacao("Flag ativo deve ser 'S' ou 'N'", constraint="ck_tbsss_usr_ativo")

                tentativas = int(dados.get("tentativas_falha", 0))
                if tentativas < 0:
                    raise RepoViolacao("Tentativas falhas nao podem ser negativas", constraint="ck_tbsss_usr_tent")

                uid = self._store.proximo_id("tbsss_usuarios")
                novo = {
                    "id": uid,
                    "login": login,
                    "nome": dados.get("nome", ""),
                    "senha_hash": dados.get("senha_hash", "!"),
                    "perfil_id": perfil_id,
                    "tentativas_falha": tentativas,
                    "bloqueado_ate": dados.get("bloqueado_ate"),
                    "ultimo_login": dados.get("ultimo_login"),
                    "senha_alterada_em": dados.get("senha_alterada_em"),
                    "ativo": ativo,
                    "created_at": dados.get("created_at"),
                }
                self._store.carimbar_inclusao(novo, ator)
                self._store.usuarios[uid] = copy.deepcopy(novo)
                self._auditar(auditoria, uid)
                return copy.deepcopy(novo)

    def alterar(self, id, dados, esperado=None, auditoria=None, ator=None):
        """Altera usuario (login imutavel), condicional a 'esperado' e com protecao do ultimo admin."""
        with self._store.lock_rbac:
            with self._store.lock_usuarios:
                ator = self._store.ator_registro(auditoria, ator)
                if id not in self._store.usuarios:
                    raise RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)

                atual = self._store.usuarios[id]
                for campo, valor in (esperado or {}).items():
                    if atual.get(campo) != valor:
                        raise RepoConflito("Usuario ID %s alterado por outra operacao (%s)" % (id, campo))

                # Imutabilidade do login (README §10 trigger tr_tbsss_usr_bu)
                novo_login = dados.get("login")
                if novo_login is not None and novo_login != atual["login"]:
                    raise RepoViolacao("Login de usuario e imutavel", constraint="tr_tbsss_usr_bu")

                novo_perfil = dados.get("perfil_id")
                if novo_perfil is not None and novo_perfil not in self._store.perfis:
                    raise RepoViolacao("Perfil ID %s nao existe" % novo_perfil, constraint="fk_tbsss_usr_per")
                perfil_alterado = novo_perfil is not None and novo_perfil != atual["perfil_id"]

                novo_ativo = dados.get("ativo")
                if novo_ativo is not None and novo_ativo not in ("S", "N"):
                    raise RepoViolacao("Flag ativo deve ser 'S' ou 'N'", constraint="ck_tbsss_usr_ativo")
                ativo_alterado = novo_ativo is not None and novo_ativo != atual["ativo"]

                mudancas = dict((k, v) for k, v in dados.items()
                                if k in ("nome", "perfil_id", "senha_hash", "tentativas_falha", "bloqueado_ate",
                                         "ultimo_login", "senha_alterada_em", "ativo"))
                if int(mudancas.get("tentativas_falha", 0) or 0) < 0:
                    raise RepoViolacao("Tentativas falhas nao podem ser negativas", constraint="ck_tbsss_usr_tent")

                # README §4.3.B: lock dos admins e validacao do conjunto resultante na mesma operacao.
                if self._eh_admin_ativo(atual) and not self._eh_admin_ativo(dict(atual, **mudancas)):
                    restantes = [u for uid, u in self._store.usuarios.items()
                                 if uid != id and self._eh_admin_ativo(u)]
                    if not restantes:
                        raise RepoViolacao("Operacao deixaria o sistema sem administrador ativo",
                                           constraint="sss_ultimo_admin")

                anterior = atual["perfil_id"]
                atual.update(mudancas)
                self._store.carimbar_alteracao(atual, ator)

                # Incrementa perm_versao do perfil se houver alteracao de perfil ou ativo
                if perfil_alterado or ativo_alterado:
                    if anterior in self._store.perfis:
                        self._store.perfis[anterior]["perm_versao"] += 1
                    if perfil_alterado:
                        self._store.perfis[novo_perfil]["perm_versao"] += 1

                self._auditar(auditoria, id)
                return copy.deepcopy(atual)

    def _por_login(self, login):
        for u in self._store.usuarios.values():
            if u["login"] == login:
                return u
        raise RepoNaoEncontrado("Usuario com login '%s' nao encontrado" % login)

    def registrar_falha_login(self, login, bloqueio_s=None, auditoria=None):
        """Incrementa as falhas e, se pedido, bloqueia pelo relogio do banco; auditoria na mesma operacao."""
        with self._store.lock_usuarios:
            u = self._por_login(login)
            tentativas = int(u.get("tentativas_falha", 0)) + 1
            if tentativas > 99:
                raise RepoViolacao("tentativas_falha excede NUMBER(2)", constraint="ck_tbsss_usr_tent")
            u["tentativas_falha"] = tentativas
            if bloqueio_s is not None:
                u["bloqueado_ate"] = self._store.agora() + datetime.timedelta(seconds=int(bloqueio_s))
            self._auditar(auditoria, u["id"])
            return copy.deepcopy(u)

    def registrar_sucesso_login(self, login, novo_hash=None, auditoria=None):
        """Zera falhas, grava ultimo_login (SYSDATE) e o rehash, com a auditoria, numa operacao."""
        with self._store.lock_usuarios:
            u = self._por_login(login)
            u["tentativas_falha"] = 0
            u["bloqueado_ate"] = None
            u["ultimo_login"] = self._store.agora()
            if novo_hash is not None:
                u["senha_hash"] = novo_hash
            self._auditar(auditoria, u["id"])
            return copy.deepcopy(u)

    def desbloquear(self, id, auditoria=None, ator=None):
        """Desbloqueia conta de usuario zerando tentativas (alteracao de negocio: grava updated_*)."""
        with self._store.lock_usuarios:
            ator = self._store.ator_registro(auditoria, ator)
            if id not in self._store.usuarios:
                raise RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)
            u = self._store.usuarios[id]
            u["tentativas_falha"] = 0
            u["bloqueado_ate"] = None
            self._store.carimbar_alteracao(u, ator)
            self._auditar(auditoria, id)
            return copy.deepcopy(u)

    def reiniciar_tentativas(self, id):
        """Bloqueio vencido: novo ciclo de tentativas, sem updated_* nem auditoria (rotina tecnica)."""
        with self._store.lock_usuarios:
            if id not in self._store.usuarios:
                raise RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)
            u = self._store.usuarios[id]
            u["tentativas_falha"] = 0
            u["bloqueado_ate"] = None
            return copy.deepcopy(u)

    def definir_senha(self, id, senha_hash, agora=None, auditoria=None, ator=None):
        """Atualiza a senha do usuario e zera contadores de bloqueio (grava updated_*)."""
        with self._store.lock_usuarios:
            ator = self._store.ator_registro(auditoria, ator)
            if id not in self._store.usuarios:
                raise RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)
            u = self._store.usuarios[id]
            u["senha_hash"] = senha_hash
            u["senha_alterada_em"] = agora or self._store.agora()
            u["tentativas_falha"] = 0
            u["bloqueado_ate"] = None
            self._store.carimbar_alteracao(u, ator)
            self._auditar(auditoria, id)
            return copy.deepcopy(u)
