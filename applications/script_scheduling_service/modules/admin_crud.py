# -*- coding: utf-8 -*-
"""Base comum dos cadastros administrativos (docs/PADRAO_CRUD_ADMIN.md, README §4.4, §10).

Modulo puro: nao importa gluon (testavel sem o framework).
"""
import hashlib
import json

import masking
import rbac

CAMPO_GERAL = "_geral"
MSG_CONFLITO = u"O registro foi alterado por outra pessoa. Recarregue a página."
MSG_FALHA = u"Não foi possível salvar. Tente novamente em instantes."
LIMITE_DETALHE = 1000
_VAZIO = u"(vazio)"
_SETA = u" → "


class AcessoNegado(Exception):
    """Perfil sem a funcionalidade de cadastro exigida."""


def exigir_func(ctx, codigo):
    """Defesa em profundidade: o controller ja exige a funcionalidade, o service reconfirma."""
    if not rbac.tem_func(ctx, codigo):
        raise AcessoNegado(codigo)


def texto(valor, limite=None):
    """Valor de formulario como str sem espacos nas pontas; lista vale o ultimo; vazio vira None."""
    if isinstance(valor, (list, tuple)):
        valor = valor[-1] if valor else None
    if not isinstance(valor, str):
        return None
    valor = valor.strip()
    if not valor:
        return None
    return valor[:limite] if limite else valor


def normalizar(valor):
    # O Oracle grava '' como NULL: vazio e None sao o mesmo estado.
    return None if valor in (None, "") else valor


def versao(registro, campos):
    """Hash dos campos editaveis lidos agora; o formulario devolve-o para detectar edicao concorrente."""
    estado = [[c, normalizar(registro.get(c))] for c in campos]
    bruto = json.dumps(estado, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def esperado(registro, campos):
    """Valores lidos que condicionam o UPDATE (o repositorio lanca RepoConflito se divergirem)."""
    return dict((c, registro.get(c)) for c in campos)


def _exibir(valor):
    valor = normalizar(valor)
    return _VAZIO if valor is None else masking.MASCARADOR.mascarar(str(valor))


def _limitar(detalhe):
    if len(detalhe) <= LIMITE_DETALHE:
        return detalhe
    return detalhe[:LIMITE_DETALHE - 3] + u"..."


def detalhe_alteracoes(antes, depois, campos):
    """'campo: antigo → novo' por campo alterado, mascarado e limitado a 1000 caracteres; None se nada mudou."""
    partes = []
    for c in campos:
        a, d = normalizar(antes.get(c)), normalizar(depois.get(c))
        if a != d:
            partes.append(u"%s: %s%s%s" % (c, _exibir(a), _SETA, _exibir(d)))
    return _limitar(u"; ".join(partes)) if partes else None


def detalhe_insercao(registro, campos):
    """'campo: valor' dos campos informados na inclusao, mascarado e limitado."""
    return _limitar(u"; ".join(u"%s: %s" % (c, _exibir(registro.get(c))) for c in campos))


def auditoria(ctx, ip, acao, detalhe):
    """Dicionario de auditoria repassado ao repositorio (gravado na mesma operacao)."""
    return {"ator": ctx.get("login"), "ip": ip, "acao": acao, "detalhe": detalhe}
