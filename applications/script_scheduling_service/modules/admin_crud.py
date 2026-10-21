# -*- coding: utf-8 -*-
"""Base comum dos cadastros administrativos (docs/ADMIN_CRUD_PATTERN.md, README §4.4, §10).

Modulo puro: nao importa gluon (testavel sem o framework).
"""
import hashlib
import json
import re

import masking
import rbac
import ui_helpers

CAMPO_GERAL = "_geral"
MSG_CONFLITO = ui_helpers.mensagem("conflito")
MSG_FALHA = u"Não foi possível salvar. Tente novamente em instantes."
LIMITE_DETALHE = 1000
_VAZIO = u"(vazio)"
_SETA = u" → "


class AcessoNegado(Exception):
    """Perfil sem a funcionalidade de cadastro exigida."""


class OperacaoNegada(Exception):
    """Regra de negocio impede a operacao; 'mensagem' e segura para exibicao."""

    def __init__(self, mensagem):
        Exception.__init__(self, mensagem)
        self.mensagem = mensagem


def exigir_func(ctx, codigo):
    """Defesa em profundidade: o controller ja exige a funcionalidade, o service reconfirma."""
    if not rbac.tem_func(ctx, codigo):
        raise AcessoNegado(codigo)


def exigir_admin(ctx, condicao, mensagem, log, operacao):
    """Administrador so por administrador (CR-008, E1): com 'condicao' verdadeira, so admin prossegue.

    Recusa com WARN no log (sem auditoria: nada foi gravado) e OperacaoNegada com 'mensagem'.
    """
    if condicao and ctx.get("is_admin") is not True:
        log.warning("operacao reservada a administrador negada (login=%s operacao=%s)", ctx.get("login"),
                    operacao, extra={"action": "ACESSO_NEGADO"})
        raise OperacaoNegada(mensagem)


def texto(valor, limite=None):
    """Valor de formulario como str sem espacos nas pontas; lista vale o ultimo; vazio vira None.

    Nunca trunca (README §10, AGENTS §3.4): acima de 'limite' devolve o valor inteiro, e a validacao
    de quem chamou o recusa. 'limite' fica so como documentacao do tamanho esperado.
    """
    if isinstance(valor, (list, tuple)):
        valor = valor[-1] if valor else None
    if not isinstance(valor, str):
        return None
    valor = valor.strip()
    if not valor:
        return None
    return valor


MSG_ESPACOS = u"Não use espaços no início nem no fim."
MSG_CONTROLE = u"O campo contém caracteres de controle (como quebra de linha ou tabulação), que não são permitidos."
_RE_CONTROLE = re.compile(u"[\x00-\x1f\x7f]")


def identificador(valor, erros, campo):
    """Identificador (nome de ambiente/perfil, login, codigo): sem strip; espaco nas pontas e recusado.

    README §10, "Texto nos cadastros". Devolve o valor como veio (ou None se vazio).
    """
    if isinstance(valor, (list, tuple)):
        valor = valor[-1] if valor else None
    if not isinstance(valor, str) or not valor.strip():
        return None
    if valor != valor.strip():
        erros[campo] = MSG_ESPACOS
    return valor


def texto_livre(valor, erros, campo):
    """Texto livre (label, descricao...): strip e recusa de caracteres de controle (README §10)."""
    valor = texto(valor)
    if valor is not None and _RE_CONTROLE.search(valor):
        erros[campo] = MSG_CONTROLE
    return valor


def normalizar(valor):
    # O Oracle grava '' como NULL: vazio e None sao o mesmo estado.
    return None if valor in (None, "") else valor


MARCADOR_PREENCHIDO = u"<sensivel:preenchido>"
MARCADOR_VAZIO = u"<sensivel:vazio>"


def marcador_sensivel(valor):
    """Marcador fixo que substitui um valor sensivel em tudo que vai ao HTML (README §10)."""
    return MARCADOR_VAZIO if normalizar(valor) is None else MARCADOR_PREENCHIDO


def versao(registro, campos, sensiveis=()):
    """Hash dos campos editaveis lidos agora; o formulario devolve-o para detectar edicao concorrente.

    Campos em 'sensiveis' entram pelo marcador, nunca pelo valor: a versao vai ao HTML e um sha256
    sem sal do segredo permitiria adivinha-lo. A troca concorrente so do segredo fica com o esperado.
    """
    estado = [[c, marcador_sensivel(registro.get(c)) if c in sensiveis else normalizar(registro.get(c))]
              for c in campos]
    return hash_estado(estado)


def hash_estado(estado):
    """sha256 do JSON deterministico de um estado serializavel."""
    bruto = json.dumps(estado, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def esperado(registro, campos):
    """Valores lidos que condicionam o UPDATE (o repositorio lanca RepoConflict se divergirem)."""
    return dict((c, registro.get(c)) for c in campos)


def _exibir(valor):
    valor = normalizar(valor)
    return _VAZIO if valor is None else masking.MASCARADOR.mascarar(str(valor))


def limitar(detalhe):
    """Corta o detalhe de auditoria em LIMITE_DETALHE caracteres (coluna VARCHAR2(1000 CHAR))."""
    if len(detalhe) <= LIMITE_DETALHE:
        return detalhe
    return detalhe[:LIMITE_DETALHE - 3] + u"..."


def detalhe_livre(texto):
    """Detalhe de auditoria montado pelo service, sempre mascarado e limitado (README §4.4)."""
    return limitar(masking.MASCARADOR.mascarar(texto))


def detalhe_alteracoes(antes, depois, campos):
    """'campo: antigo → novo' por campo alterado, mascarado e limitado a 1000 caracteres; None se nada mudou."""
    partes = []
    for c in campos:
        a, d = normalizar(antes.get(c)), normalizar(depois.get(c))
        if a != d:
            partes.append(u"%s: %s%s%s" % (c, _exibir(a), _SETA, _exibir(d)))
    return limitar(u"; ".join(partes)) if partes else None


def detalhe_insercao(registro, campos):
    """'campo: valor' so dos campos preenchidos na inclusao (vazios omitidos), mascarado e limitado (README §4.4)."""
    return limitar(u"; ".join(u"%s: %s" % (c, _exibir(registro.get(c))) for c in campos
                              if normalizar(registro.get(c)) is not None))


def auditoria(ctx, ip, acao, detalhe):
    """Dicionario de auditoria repassado ao repositorio (gravado na mesma operacao)."""
    return {"actor": ctx.get("login"), "ip": ip, "action": acao, "detail": detalhe}
