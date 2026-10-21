# -*- coding: utf-8 -*-
"""Implementacao em memoria do repositorio de usuarios (README §2.5, §4.2, §10)."""
import copy
import datetime
import re

from repo_errors import RepoConflito, RepoNaoEncontrado, RepoViolacao
from repo_fake.store import paginar
from repo_users import RepoUsuarios

_RE_LOGIN = re.compile(r"^[a-z0-9._-]{3,30}$")



def _auditoria_falha(auditoria, tentativas, max_tentativas, bloqueou, auditoria_bloqueio):
    """Itens de auditoria da falha de login: a contagem vem do valor lido sob o lock (mesma regra do Oracle)."""
    itens = [] if not auditoria else ([auditoria] if isinstance(auditoria, dict) else list(auditoria))
    if max_tentativas is not None:
        itens = [dict(item, detail=u"%s (tentativa %d de %d)" % (item.get("detail") or u"", tentativas,
                                                                    int(max_tentativas)))
                 if isinstance(item, dict) and item.get("action") == "LOGIN_FAILED" else item for item in itens]
    if bloqueou and auditoria_bloqueio:
        itens.append(auditoria_bloqueio)
    return itens

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
                perfil_id = u["profile_id"]
                if perfil_id not in self._store.perfis:
                    raise RepoNaoEncontrado("Perfil ID %s nao encontrado" % perfil_id)
                p = self._store.perfis[perfil_id]

                return {
                    "user_id": u["id"],
                    "login": u["login"],
                    "name": u["name"],
                    "usuario_ativo": u["active"],
                    "profile_id": p["id"],
                    "perfil_nome": p["name"],
                    "perfil_ativo": p["active"],
                    "is_admin": p["is_admin"],
                    "perm_version": p["perm_version"],
                    "session_epoch": u.get("session_epoch", 0),
                }

    def listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista usuarios paginados com desempate por id."""
        filtros = filtros or {}
        with self._store.lock_usuarios:
            lista = list(self._store.usuarios.values())

            login_f = filtros.get("login")
            if login_f:
                lista = [u for u in lista if login_f.lower() in u["login"].lower()]

            nome_f = filtros.get("name")
            if nome_f:
                lista = [u for u in lista if nome_f.lower() in u["name"].lower()]

            perfil_f = filtros.get("profile_id")
            if perfil_f is not None:
                lista = [u for u in lista if u["profile_id"] == int(perfil_f)]

            ativo_f = filtros.get("active")
            if ativo_f:
                lista = [u for u in lista if u["active"] == ativo_f]

            bloq_f = filtros.get("bloqueado_em")
            if bloq_f is not None:
                lista = [u for u in lista if u.get("locked_until") is not None and u["locked_until"] > bloq_f]

            # Ordenacao estavel: login ASC, id ASC
            lista.sort(key=lambda x: (x.get("login", ""), x["id"]))
            return paginar(lista, pagina=pagina, tamanho=tamanho)

    def _auditar(self, auditoria, usuario_id):
        for item in ([auditoria] if isinstance(auditoria, dict) else (auditoria or ())):
            self._store.registrar_auditoria_interno(
                ator=item.get("actor"),
                ip=item.get("ip"),
                acao=item["action"],
                entidade="tbsss_users",
                entidade_id=usuario_id,
                detalhe=item.get("detail"),
            )

    def agora(self):
        """SYSDATE simulado pelo relogio do store."""
        return self._store.agora()

    def _eh_admin_ativo(self, usuario):
        p = self._store.perfis.get(usuario["profile_id"])
        return usuario["active"] == "Y" and p is not None and p["active"] == "Y" and p["is_admin"] == "Y"

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

                perfil_id = dados.get("profile_id")
                if perfil_id not in self._store.perfis:
                    raise RepoViolacao("Perfil ID %s nao existe" % perfil_id, constraint="fk_tbsss_usr_prf")

                ativo = dados.get("active", "Y")
                if ativo not in ("Y", "N"):
                    raise RepoViolacao("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_usr_active")

                tentativas = int(dados.get("failed_attempts", 0))
                if tentativas < 0:
                    raise RepoViolacao("Tentativas falhas nao podem ser negativas", constraint="ck_tbsss_usr_att")

                uid = self._store.proximo_id("tbsss_users")
                novo = {
                    "id": uid,
                    "login": login,
                    "name": dados.get("name", ""),
                    "password_hash": dados.get("password_hash", "!"),
                    "profile_id": perfil_id,
                    "failed_attempts": tentativas,
                    "locked_until": dados.get("locked_until"),
                    "last_login_at": dados.get("last_login_at"),
                    "password_changed_at": dados.get("password_changed_at"),
                    "session_epoch": 0,
                    "active": ativo,
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

                novo_perfil = dados.get("profile_id")
                if novo_perfil is not None and novo_perfil not in self._store.perfis:
                    raise RepoViolacao("Perfil ID %s nao existe" % novo_perfil, constraint="fk_tbsss_usr_prf")
                perfil_alterado = novo_perfil is not None and novo_perfil != atual["profile_id"]

                novo_ativo = dados.get("active")
                if novo_ativo is not None and novo_ativo not in ("Y", "N"):
                    raise RepoViolacao("Flag ativo deve ser 'Y' ou 'N'", constraint="ck_tbsss_usr_active")
                ativo_alterado = novo_ativo is not None and novo_ativo != atual["active"]

                mudancas = dict((k, v) for k, v in dados.items()
                                if k in ("name", "profile_id", "password_hash", "failed_attempts", "locked_until",
                                         "last_login_at", "password_changed_at", "active"))
                if int(mudancas.get("failed_attempts", 0) or 0) < 0:
                    raise RepoViolacao("Tentativas falhas nao podem ser negativas", constraint="ck_tbsss_usr_att")

                # README §4.3.B: lock dos admins e validacao do conjunto resultante na mesma operacao.
                if self._eh_admin_ativo(atual) and not self._eh_admin_ativo(dict(atual, **mudancas)):
                    restantes = [u for uid, u in self._store.usuarios.items()
                                 if uid != id and self._eh_admin_ativo(u)]
                    if not restantes:
                        raise RepoViolacao("Operacao deixaria o sistema sem administrador ativo",
                                           constraint="sss_ultimo_admin")

                anterior = atual["profile_id"]
                atual.update(mudancas)
                if perfil_alterado or ativo_alterado:
                    _revogar_sessoes(atual)
                self._store.carimbar_alteracao(atual, ator)

                # Incrementa perm_versao do perfil se houver alteracao de perfil ou ativo
                if perfil_alterado or ativo_alterado:
                    if anterior in self._store.perfis:
                        self._store.perfis[anterior]["perm_version"] += 1
                    if perfil_alterado:
                        self._store.perfis[novo_perfil]["perm_version"] += 1

                self._auditar(auditoria, id)
                return copy.deepcopy(atual)

    def _por_login(self, login):
        for u in self._store.usuarios.values():
            if u["login"] == login:
                return u
        raise RepoNaoEncontrado("Usuario com login '%s' nao encontrado" % login)

    def registrar_falha_login(self, login, bloqueio_s=None, auditoria=None, max_tentativas=None,
                              auditoria_bloqueio=None):
        """Incrementa as falhas e decide o bloqueio sob o lock (contrato em RepoUsuarios); auditoria junto."""
        with self._store.lock_usuarios:
            u = self._por_login(login)
            tentativas = int(u.get("failed_attempts", 0)) + 1
            if tentativas > 99:
                raise RepoViolacao("tentativas_falha excede NUMBER(2)", constraint="ck_tbsss_usr_att")
            bloquear = (tentativas >= int(max_tentativas)) if max_tentativas is not None else bloqueio_s is not None
            u["failed_attempts"] = tentativas
            if bloquear:
                u["locked_until"] = self._store.agora() + datetime.timedelta(seconds=int(bloqueio_s))
            self._auditar(_auditoria_falha(auditoria, tentativas, max_tentativas, bloquear, auditoria_bloqueio),
                          u["id"])
            registro = copy.deepcopy(u)
            registro["bloqueou"] = bool(bloquear)
            return registro

    def registrar_sucesso_login(self, login, novo_hash=None, auditoria=None):
        """Zera falhas, grava ultimo_login (SYSDATE) e o rehash, com a auditoria, numa operacao."""
        with self._store.lock_usuarios:
            u = self._por_login(login)
            u["failed_attempts"] = 0
            u["locked_until"] = None
            u["last_login_at"] = self._store.agora()
            if novo_hash is not None:
                u["password_hash"] = novo_hash
            self._auditar(auditoria, u["id"])
            return copy.deepcopy(u)

    def desbloquear(self, id, auditoria=None, ator=None):
        """Desbloqueia conta de usuario zerando tentativas (alteracao de negocio: grava updated_*)."""
        with self._store.lock_usuarios:
            ator = self._store.ator_registro(auditoria, ator)
            if id not in self._store.usuarios:
                raise RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)
            u = self._store.usuarios[id]
            u["failed_attempts"] = 0
            u["locked_until"] = None
            self._store.carimbar_alteracao(u, ator)
            self._auditar(auditoria, id)
            return copy.deepcopy(u)

    def reiniciar_tentativas(self, id):
        """Bloqueio vencido: novo ciclo de tentativas, sem updated_* nem auditoria (rotina tecnica)."""
        with self._store.lock_usuarios:
            if id not in self._store.usuarios:
                raise RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)
            u = self._store.usuarios[id]
            u["failed_attempts"] = 0
            u["locked_until"] = None
            return copy.deepcopy(u)

    def definir_senha(self, id, senha_hash, agora=None, auditoria=None, ator=None):
        """Atualiza a senha do usuario e zera contadores de bloqueio (grava updated_*)."""
        with self._store.lock_usuarios:
            ator = self._store.ator_registro(auditoria, ator)
            if id not in self._store.usuarios:
                raise RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)
            u = self._store.usuarios[id]
            u["password_hash"] = senha_hash
            u["password_changed_at"] = agora or self._store.agora()
            u["failed_attempts"] = 0
            u["locked_until"] = None
            _revogar_sessoes(u)
            self._store.carimbar_alteracao(u, ator)
            self._auditar(auditoria, id)
            return copy.deepcopy(u)

    def encerrar_sessoes(self, id, auditoria=None):
        """Logout: incrementa sessao_epoch (rotina tecnica, sem updated_*), com a auditoria na mesma operacao."""
        with self._store.lock_usuarios:
            if id not in self._store.usuarios:
                raise RepoNaoEncontrado("Usuario ID %s nao encontrado" % id)
            u = self._store.usuarios[id]
            _revogar_sessoes(u)
            self._auditar(auditoria, id)
            return copy.deepcopy(u)


def _revogar_sessoes(usuario):
    """Incrementa sessao_epoch: todas as sessoes abertas do usuario deixam de valer (CR-008, E2)."""
    novo = int(usuario.get("session_epoch") or 0) + 1
    if novo > 9999999999:
        raise RepoViolacao("sessao_epoch excede NUMBER(10)", constraint="ck_tbsss_usr_epoch")
    usuario["session_epoch"] = novo
