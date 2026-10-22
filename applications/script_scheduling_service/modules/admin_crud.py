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

GENERAL_FIELD = "_geral"
MSG_CONFLICT = ui_helpers.mensagem("conflito")
MSG_FAILURE = u"Não foi possível salvar. Tente novamente em instantes."
DETAIL_LIMIT = 1000
_EMPTY = u"(vazio)"
_ARROW = u" → "


class AccessDenied(Exception):
    """Perfil sem a funcionalidade de cadastro exigida."""


class OperationDenied(Exception):
    """Regra de negocio impede a operacao; 'mensagem' e segura para exibicao."""

    def __init__(self, mensagem):
        Exception.__init__(self, mensagem)
        self.message = mensagem


def require_feature(ctx, codigo):
    """Defesa em profundidade: o controller ja exige a funcionalidade, o service reconfirma."""
    if not rbac.has_feature(ctx, codigo):
        raise AccessDenied(codigo)


def require_admin(ctx, condicao, mensagem, log, operacao):
    """Administrador so por administrador (CR-008, E1): com 'condicao' verdadeira, so admin prossegue.

    Recusa com WARN no log (sem auditoria: nada foi gravado) e OperationDenied com 'mensagem'.
    """
    if condicao and ctx.get("is_admin") is not True:
        log.warning("operacao reservada a administrador negada (login=%s operacao=%s)", ctx.get("login"),
                    operacao, extra={"action": "ACESSO_NEGADO"})
        raise OperationDenied(mensagem)


def text(valor, limite=None):
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


MSG_SPACES = u"Não use espaços no início nem no fim."
MSG_CONTROL_CHARS = u"O campo contém caracteres de controle (como quebra de linha ou tabulação), que não são permitidos."
_RE_CONTROL = re.compile(u"[\x00-\x1f\x7f]")


def identifier(valor, erros, campo):
    """Identificador (nome de ambiente/perfil, login, codigo): sem strip; espaco nas pontas e recusado.

    README §10, "Texto nos cadastros". Devolve o valor como veio (ou None se vazio).
    """
    if isinstance(valor, (list, tuple)):
        valor = valor[-1] if valor else None
    if not isinstance(valor, str) or not valor.strip():
        return None
    if valor != valor.strip():
        erros[campo] = MSG_SPACES
    return valor


def free_text(valor, erros, campo):
    """Texto livre (label, descricao...): strip e recusa de caracteres de controle (README §10)."""
    valor = text(valor)
    if valor is not None and _RE_CONTROL.search(valor):
        erros[campo] = MSG_CONTROL_CHARS
    return valor


def normalize(valor):
    # O Oracle grava '' como NULL: vazio e None sao o mesmo estado.
    return None if valor in (None, "") else valor


FILLED_MARKER = u"<sensivel:preenchido>"
EMPTY_MARKER = u"<sensivel:vazio>"


def sensitive_marker(valor):
    """Marcador fixo que substitui um valor sensivel em tudo que vai ao HTML (README §10)."""
    return EMPTY_MARKER if normalize(valor) is None else FILLED_MARKER


def version(registro, campos, sensiveis=()):
    """Hash dos campos editaveis lidos agora; o formulario devolve-o para detectar edicao concorrente.

    Campos em 'sensiveis' entram pelo marcador, nunca pelo valor: a versao vai ao HTML e um sha256
    sem sal do segredo permitiria adivinha-lo. A troca concorrente so do segredo fica com o esperado.
    """
    estado = [[c, sensitive_marker(registro.get(c)) if c in sensiveis else normalize(registro.get(c))]
              for c in campos]
    return state_hash(estado)


def state_hash(estado):
    """sha256 do JSON deterministico de um estado serializavel."""
    bruto = json.dumps(estado, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def expected(registro, campos):
    """Valores lidos que condicionam o UPDATE (o repositorio lanca RepoConflict se divergirem)."""
    return dict((c, registro.get(c)) for c in campos)


def _display(valor):
    valor = normalize(valor)
    return _EMPTY if valor is None else masking.MASKER.mask(str(valor))


def truncate_detail(detalhe):
    """Corta o detalhe de auditoria em DETAIL_LIMIT caracteres (coluna VARCHAR2(1000 CHAR))."""
    if len(detalhe) <= DETAIL_LIMIT:
        return detalhe
    return detalhe[:DETAIL_LIMIT - 3] + u"..."


def free_detail(texto):
    """Detalhe de auditoria montado pelo service, sempre mascarado e limitado (README §4.4)."""
    return truncate_detail(masking.MASKER.mask(texto))


def changes_detail(antes, depois, campos):
    """'campo: antigo → novo' por campo alterado, mascarado e limitado a 1000 caracteres; None se nada mudou."""
    partes = []
    for c in campos:
        a, d = normalize(antes.get(c)), normalize(depois.get(c))
        if a != d:
            partes.append(u"%s: %s%s%s" % (c, _display(a), _ARROW, _display(d)))
    return truncate_detail(u"; ".join(partes)) if partes else None


def insert_detail(registro, campos):
    """'campo: valor' so dos campos preenchidos na inclusao (vazios omitidos), mascarado e limitado (README §4.4)."""
    return truncate_detail(u"; ".join(u"%s: %s" % (c, _display(registro.get(c))) for c in campos
                              if normalize(registro.get(c)) is not None))


def audit_entry(ctx, ip, acao, detalhe):
    """Dicionario de auditoria repassado ao repositorio (gravado na mesma operacao)."""
    return {"actor": ctx.get("login"), "ip": ip, "action": acao, "detail": detalhe}
