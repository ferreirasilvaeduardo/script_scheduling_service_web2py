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
MSG_SENHA_ATUAL = u"A senha atual está incorreta."
MSG_CONFIRMACAO = u"A confirmação não confere com a nova senha."
SENHA_MAX = 1024
CACHE_MATRIZ_MAX = 64
SIMULADOS_MAX = 1024

_RE_LOGIN = re.compile(r"[a-z0-9._-]{3,30}")


def _aud(login, ip, acao, detalhe):
    return {"ator": login, "ip": ip, "acao": acao, "detalhe": detalhe}


class ServicoAuth(object):
    """Servico de autenticacao com dependencias injetadas (repositorios, limites, relogio e log)."""

    def __init__(self, usuarios, rbac_repo, catalogo, auditoria, max_tentativas, bloqueio_s,
                 log, relogio=None):
        self._usuarios = usuarios
        self._rbac = rbac_repo
        self._catalogo = catalogo
        self._auditoria = auditoria
        self._max = int(max_tentativas)
        self._bloqueio_s = int(bloqueio_s)
        self._bloqueio = datetime.timedelta(seconds=self._bloqueio_s)
        self._log = log
        # Relogio do banco (README §4.2): o bloqueio nunca depende do relogio do no web.
        self._relogio = relogio or usuarios.agora
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

        if self._bloqueado(usuario, agora):
            self._registrar_falha(usuario, ip, "conta bloqueada")
            return None, MSG_BLOQUEIO
        usuario = self._reiniciar_se_expirado(usuario)

        if not senha_confere:
            return self._falha_senha(usuario, ip)

        estado = self._usuarios.obter_estado_sessao(usuario["id"])
        if estado.get("usuario_ativo") != "S" or estado.get("perfil_ativo") != "S":
            self._registrar_falha(usuario, ip, "usuario ou perfil inativo")
            return None, MSG_GENERICA

        novo_hash = security.hash_senha(senha_txt) if security.precisa_rehash(armazenado) else None
        # Sucesso, rehash e auditoria numa unica operacao do repositorio (README §4.2, §4.4).
        self._usuarios.registrar_sucesso_login(
            usuario["login"], novo_hash=novo_hash,
            auditoria=_aud(usuario["login"], ip, "LOGIN_OK", "Login bem-sucedido"))
        if novo_hash is not None:
            self._log.info("hash de senha atualizado para as iteracoes vigentes (login=%s)",
                           usuario["login"], extra={"acao": "LOGIN"})
        self._log.info("login ok (login=%s ip=%s)", usuario["login"], ip, extra={"acao": "LOGIN"})
        return self._montar_ctx(estado), None

    @staticmethod
    def _bloqueado(usuario, agora):
        bloqueado_ate = usuario.get("bloqueado_ate")
        return bloqueado_ate is not None and bloqueado_ate > agora

    def _reiniciar_se_expirado(self, usuario):
        # Bloqueio expirado (ou contador no limite): novo ciclo de tentativas, no login e na troca de senha.
        if usuario.get("bloqueado_ate") is not None or int(usuario.get("tentativas_falha") or 0) >= self._max:
            return self._usuarios.desbloquear(usuario["id"])
        return usuario

    def _registrar_falha(self, usuario, ip, motivo):
        self._auditoria.registrar(usuario["login"], ip, "LOGIN_FALHA", ENTIDADE, usuario["id"],
                                  "Falha de login: %s" % motivo)
        self._log.warning("login falhou (login=%s ip=%s motivo=%s)", usuario["login"], ip, motivo,
                          extra={"acao": "LOGIN"})

    def _falha_senha(self, usuario, ip):
        tentativas = int(usuario.get("tentativas_falha") or 0) + 1
        bloquear = tentativas >= self._max
        motivo = "senha incorreta (tentativa %d de %d)" % (tentativas, self._max)
        auditorias = [_aud(usuario["login"], ip, "LOGIN_FALHA", "Falha de login: %s" % motivo)]
        if bloquear:
            auditorias.append(_aud(usuario["login"], ip, "LOGIN_BLOQUEIO",
                                   "Conta bloqueada por %d falhas consecutivas" % tentativas))
        # Falha, bloqueio (SYSDATE + segundos) e auditoria numa unica operacao do repositorio.
        self._usuarios.registrar_falha_login(usuario["login"], self._bloqueio_s if bloquear else None,
                                             auditoria=auditorias)
        self._log.warning("login falhou (login=%s ip=%s motivo=%s)", usuario["login"], ip, motivo,
                          extra={"acao": "LOGIN"})
        if not bloquear:
            return None, MSG_GENERICA
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

    def revalidar(self, sessao, ip=None):
        """Reconsulta usuario e perfil (README §4.2). Retorna ctx ou None se a sessao deve encerrar.

        Encerramento por usuario ou perfil inativo e auditado como LOGOUT (README §4.2, D13).
        """
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
            motivo = u"usuário inativo" if estado.get("usuario_ativo") != "S" else u"perfil inativo"
            self._auditoria.registrar(estado.get("login"), ip, "LOGOUT", ENTIDADE, usuario_id,
                                      u"sessão encerrada pela revalidação: %s" % motivo)
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

    # ------------------------------------------------------- troca de senha

    def trocar_senha(self, ctx, ip, atual, nova, confirmacao):
        """Troca da propria senha (exige a atual). Retorna (resultado, erros por campo).

        resultado: 'OK' | 'ERRO' | 'BLOQUEADO'. Senha atual errada conta como falha de login
        (mesmo limite e bloqueio do §4.2); ao bloquear, o chamador encerra a sessao.
        """
        agora = self._relogio()
        usuario = self._usuarios.obter_por_id(ctx["usuario_id"])
        if self._bloqueado(usuario, agora):
            self._registrar_falha(usuario, ip, "troca de senha com conta bloqueada")
            return "BLOQUEADO", {"senha_atual": MSG_BLOQUEIO}
        usuario = self._reiniciar_se_expirado(usuario)
        armazenado = usuario.get("senha_hash")
        atual_ok = (isinstance(atual, str) and 0 < len(atual) <= SENHA_MAX
                    and security.hash_reconhecido(armazenado) and security.verificar_senha(atual, armazenado))
        if not atual_ok:
            _ctx, mensagem = self._falha_senha(usuario, ip)
            if mensagem == MSG_BLOQUEIO:
                return "BLOQUEADO", {"senha_atual": MSG_BLOQUEIO}
            return "ERRO", {"senha_atual": MSG_SENHA_ATUAL}
        erros = {}
        problemas = security.validar_politica_senha(nova) if isinstance(nova, str) and len(nova) <= SENHA_MAX \
            else [u"Informe a nova senha."]
        if problemas:
            erros["nova"] = problemas[0]
        elif confirmacao != nova:
            erros["confirmacao"] = MSG_CONFIRMACAO
        if erros:
            return "ERRO", erros
        self._usuarios.definir_senha(usuario["id"], security.hash_senha(nova), agora,
                                     auditoria={"ator": usuario["login"], "ip": ip, "acao": "CAD_ALTERAR",
                                                "detalhe": u"senha alterada pelo próprio usuário"})
        self._log.info("senha alterada pelo proprio usuario (login=%s ip=%s)", usuario["login"], ip,
                       extra={"acao": "CAD_ALTERAR"})
        return "OK", {}

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


def revalidar(sessao, ip=None):
    """Revalida a sessao pelo servico padrao do processo web."""
    return _servico().revalidar(sessao, ip)


def logout(ctx, ip):
    """Audita o logout pelo servico padrao do processo web."""
    return _servico().logout(ctx, ip)


def trocar_senha(ctx, ip, atual, nova, confirmacao):
    """Troca da propria senha pelo servico padrao do processo web."""
    return _servico().trocar_senha(ctx, ip, atual, nova, confirmacao)
