# -*- coding: utf-8 -*-
"""Autenticacao, bloqueio, revalidacao de sessao e logout (README §4.2, §4.4).

As mensagens devolvidas ao usuario sao sempre genericas; o motivo vai so para o log.
Senha e hash nunca sao registrados.
"""
import collections
import datetime
import re
import threading

import rbac
import security
from repo_errors import RepoNaoEncontrado

MSG_GENERICA = u"Usuário ou senha inválidos."
MSG_BLOQUEIO = u"Acesso temporariamente bloqueado por excesso de tentativas. Tente novamente mais tarde."

ENTIDADE = "tbsss_usuarios"
SENHA_MAX = 1024
CACHE_MATRIZ_MAX = 64
SIMULADOS_MAX = 1024

_RE_LOGIN = re.compile(r"[a-z0-9._-]{3,30}")


def relogio_local():
    """Relogio padrao do no web (sem microssegundos)."""
    return datetime.datetime.now().replace(microsecond=0)


class ServicoAuth(object):
    """Servico de autenticacao com dependencias injetadas (repositorios, limites, relogio e log)."""

    def __init__(self, usuarios, rbac_repo, catalogo, auditoria, max_tentativas, bloqueio_s,
                 log, relogio=None):
        self._usuarios = usuarios
        self._rbac = rbac_repo
        self._catalogo = catalogo
        self._auditoria = auditoria
        self._max = int(max_tentativas)
        self._bloqueio = datetime.timedelta(seconds=int(bloqueio_s))
        self._log = log
        self._relogio = relogio or relogio_local
        self._lock = threading.Lock()
        self._cache_matriz = collections.OrderedDict()
        # Falhas de logins inexistentes: replica o bloqueio para nao revelar a existencia da conta.
        self._simulados = collections.OrderedDict()

    # ------------------------------------------------------------------ login

    def autenticar(self, login, senha, ip):
        """Autentica login/senha. Retorna (ctx, None) no sucesso ou (None, mensagem_generica)."""
        agora = self._relogio()
        login_norm = login.strip().lower() if isinstance(login, str) else ""
        senha_ok_tipo = isinstance(senha, str) and 0 < len(senha) <= SENHA_MAX
        senha_txt = senha if senha_ok_tipo else ""
        login_valido = bool(_RE_LOGIN.fullmatch(login_norm))

        usuario = self._usuarios.obter_por_login(login_norm) if login_valido else None
        if usuario is None:
            security.verificar_senha(senha_txt, security.hash_ficticio())
            return self._falha_inexistente(login_norm if login_valido else "?", ip, agora)

        armazenado = usuario.get("senha_hash")
        if security.hash_reconhecido(armazenado):
            senha_confere = senha_ok_tipo and security.verificar_senha(senha_txt, armazenado)
        else:
            security.verificar_senha(senha_txt, security.hash_ficticio())
            senha_confere = False

        bloqueado_ate = usuario.get("bloqueado_ate")
        if bloqueado_ate is not None and bloqueado_ate > agora:
            self._registrar_falha(usuario, ip, "conta bloqueada")
            return None, MSG_BLOQUEIO
        if bloqueado_ate is not None or int(usuario.get("tentativas_falha") or 0) >= self._max:
            # Bloqueio expirado: novo ciclo de tentativas.
            usuario = self._usuarios.desbloquear(usuario["id"])

        if not senha_confere:
            return self._falha_senha(usuario, ip, agora)

        estado = self._usuarios.obter_estado_sessao(usuario["id"])
        if estado.get("usuario_ativo") != "S" or estado.get("perfil_ativo") != "S":
            self._registrar_falha(usuario, ip, "usuario ou perfil inativo")
            return None, MSG_GENERICA

        self._usuarios.registrar_sucesso_login(usuario["login"], agora)
        if security.precisa_rehash(armazenado):
            self._usuarios.alterar(usuario["id"], {"senha_hash": security.hash_senha(senha_txt)})
            self._log.info("hash de senha atualizado para as iteracoes vigentes (login=%s)",
                           usuario["login"], extra={"acao": "LOGIN"})
        self._auditoria.registrar(usuario["login"], ip, "LOGIN_OK", ENTIDADE, usuario["id"],
                                  "Login bem-sucedido")
        self._log.info("login ok (login=%s ip=%s)", usuario["login"], ip, extra={"acao": "LOGIN"})
        return self._montar_ctx(estado), None

    def _registrar_falha(self, usuario, ip, motivo):
        self._auditoria.registrar(usuario["login"], ip, "LOGIN_FALHA", ENTIDADE, usuario["id"],
                                  "Falha de login: %s" % motivo)
        self._log.warning("login falhou (login=%s ip=%s motivo=%s)", usuario["login"], ip, motivo,
                          extra={"acao": "LOGIN"})

    def _falha_senha(self, usuario, ip, agora):
        tentativas = int(usuario.get("tentativas_falha") or 0) + 1
        bloquear = tentativas >= self._max
        self._usuarios.registrar_falha_login(usuario["login"], agora + self._bloqueio if bloquear else None)
        self._registrar_falha(usuario, ip, "senha incorreta (tentativa %d de %d)" % (tentativas, self._max))
        if not bloquear:
            return None, MSG_GENERICA
        self._auditoria.registrar(usuario["login"], ip, "LOGIN_BLOQUEIO", ENTIDADE, usuario["id"],
                                  "Conta bloqueada por %d falhas consecutivas" % tentativas)
        self._log.warning("conta bloqueada (login=%s ip=%s)", usuario["login"], ip, extra={"acao": "LOGIN"})
        return None, MSG_BLOQUEIO

    def _falha_inexistente(self, login, ip, agora):
        with self._lock:
            falhas, bloqueado_ate = self._simulados.pop(login, (0, None))
            if bloqueado_ate is not None and bloqueado_ate > agora:
                self._simulados[login] = (falhas, bloqueado_ate)
                resultado = "bloqueado"
            else:
                if bloqueado_ate is not None:
                    falhas = 0
                falhas += 1
                bloqueado_ate = agora + self._bloqueio if falhas >= self._max else None
                self._simulados[login] = (falhas, bloqueado_ate)
                resultado = "bloqueou" if bloqueado_ate is not None else "falha"
            while len(self._simulados) > SIMULADOS_MAX:
                self._simulados.popitem(last=False)

        self._auditoria.registrar(login, ip, "LOGIN_FALHA", ENTIDADE, None,
                                  "Falha de login: usuario inexistente")
        self._log.warning("login falhou (login=%s ip=%s motivo=usuario inexistente)", login, ip,
                          extra={"acao": "LOGIN"})
        if resultado == "falha":
            return None, MSG_GENERICA
        if resultado == "bloqueou":
            self._auditoria.registrar(login, ip, "LOGIN_BLOQUEIO", ENTIDADE, None,
                                      "Bloqueio simulado de login inexistente")
        return None, MSG_BLOQUEIO

    # ------------------------------------------------------------ revalidacao

    def revalidar(self, sessao):
        """Reconsulta usuario e perfil (README §4.2). Retorna ctx ou None se a sessao deve encerrar."""
        usuario_id = sessao.get("usuario_id")
        if not isinstance(usuario_id, int) or isinstance(usuario_id, bool):
            return None
        try:
            estado = self._usuarios.obter_estado_sessao(usuario_id)
        except RepoNaoEncontrado:
            self._log.warning("sessao encerrada: usuario inexistente (usuario_id=%s)", usuario_id,
                              extra={"acao": "SESSAO"})
            return None
        if estado.get("login") != sessao.get("login"):
            self._log.warning("sessao encerrada: login divergente (usuario_id=%s)", usuario_id,
                              extra={"acao": "SESSAO"})
            return None
        if estado.get("usuario_ativo") != "S" or estado.get("perfil_ativo") != "S":
            self._log.info("sessao encerrada: usuario ou perfil inativo (login=%s)", estado.get("login"),
                           extra={"acao": "SESSAO"})
            return None
        if estado.get("perm_versao") != sessao.get("perm_versao") \
                or estado.get("perfil_id") != sessao.get("perfil_id"):
            self._log.info("permissoes recarregadas (login=%s perfil_id=%s perm_versao=%s)",
                           estado.get("login"), estado.get("perfil_id"), estado.get("perm_versao"),
                           extra={"acao": "SESSAO"})
        return self._montar_ctx(estado)

    def _montar_ctx(self, estado):
        funcs, ambs, scrs = self._matriz(estado["perfil_id"], estado["perm_versao"])
        dados = dict(estado)
        dados.update(funcionalidades=funcs, ambientes=ambs, scripts=scrs)
        return rbac.contexto_usuario(dados)

    def _matriz(self, perfil_id, perm_versao):
        # perm_versao muda em toda alteracao de matriz/perfil (README §4.3.A): a chave invalida o cache.
        chave = (perfil_id, perm_versao)
        with self._lock:
            if chave in self._cache_matriz:
                self._cache_matriz.move_to_end(chave)
                return self._cache_matriz[chave]

        matriz = self._rbac.matriz_obter(perfil_id)
        codigos = dict(
            (f["id"], f["codigo"]) for f in self._rbac.funcionalidades_listar() if f.get("ativo") == "S"
        )
        funcs = frozenset(codigos[fid] for fid in matriz.get("funcs", ()) if fid in codigos)
        nomes = []
        for aid in matriz.get("ambs", ()):
            try:
                nomes.append(self._catalogo.ambientes_obter(aid)["nome"])
            except RepoNaoEncontrado:
                self._log.warning("ambiente da matriz inexistente (perfil_id=%s ambiente_id=%s)",
                                  perfil_id, aid, extra={"acao": "SESSAO"})
        valor = (funcs, frozenset(nomes), frozenset(matriz.get("scrs", ())))

        with self._lock:
            self._cache_matriz[chave] = valor
            while len(self._cache_matriz) > CACHE_MATRIZ_MAX:
                self._cache_matriz.popitem(last=False)
        return valor

    # ----------------------------------------------------------------- logout

    def logout(self, ctx, ip):
        """Audita o encerramento voluntario da sessao."""
        if not ctx:
            return
        self._auditoria.registrar(ctx["login"], ip, "LOGOUT", ENTIDADE, ctx["usuario_id"], "Logout")
        self._log.info("logout (login=%s ip=%s)", ctx["login"], ip, extra={"acao": "LOGIN"})


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
            _padrao = ServicoAuth(
                usuarios=fabrica.obter("usuarios"),
                rbac_repo=fabrica.obter("rbac"),
                catalogo=fabrica.obter("catalogo"),
                auditoria=fabrica.obter("auditoria"),
                max_tentativas=cfg.web.login_max_tentativas,
                bloqueio_s=cfg.web.login_bloqueio_s,
                log=sss_logging.obter_logger("sss_web", cfg),
            )
        return _padrao


def autenticar(login, senha, ip):
    """Autentica pelo servico padrao do processo web."""
    return _servico().autenticar(login, senha, ip)


def revalidar(sessao):
    """Revalida a sessao pelo servico padrao do processo web."""
    return _servico().revalidar(sessao)


def logout(ctx, ip):
    """Audita o logout pelo servico padrao do processo web."""
    return _servico().logout(ctx, ip)
