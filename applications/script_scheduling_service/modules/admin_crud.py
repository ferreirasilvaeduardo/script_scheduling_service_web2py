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

    def __init__(self, message):
        Exception.__init__(self, message)
        self.message = message


def require_feature(ctx, code):
    """Defesa em profundidade: o controller ja exige a funcionalidade, o service reconfirma."""
    if not rbac.has_feature(ctx, code):
        raise AccessDenied(code)


def require_admin(ctx, condition, message, log, operation):
    """Administrador so por administrador (CR-008, E1): com 'condicao' verdadeira, so admin prossegue.

    Recusa com WARN no log (sem auditoria: nada foi gravado) e OperationDenied com 'mensagem'.
    """
    if condition and ctx.get("is_admin") is not True:
        log.warning("operacao reservada a administrador negada (login=%s operacao=%s)", ctx.get("login"),
                    operation, extra={"action": "ACESSO_NEGADO"})
        raise OperationDenied(message)


def text(value, limit=None):
    """Valor de formulario como str sem espacos nas pontas; lista vale o ultimo; vazio vira None.

    Nunca trunca (README §10, AGENTS §3.4): acima de 'limite' devolve o valor inteiro, e a validacao
    de quem chamou o recusa. 'limite' fica so como documentacao do tamanho esperado.
    """
    if isinstance(value, (list, tuple)):
        value = value[-1] if value else None
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    return value


MSG_SPACES = u"Não use espaços no início nem no fim."
MSG_CONTROL_CHARS = u"O campo contém caracteres de controle (como quebra de linha ou tabulação), que não são permitidos."
_RE_CONTROL = re.compile(u"[\x00-\x1f\x7f]")


def identifier(value, errors, field):
    """Identificador (nome de ambiente/perfil, login, codigo): sem strip; espaco nas pontas e recusado.

    README §10, "Texto nos cadastros". Devolve o valor como veio (ou None se vazio).
    """
    if isinstance(value, (list, tuple)):
        value = value[-1] if value else None
    if not isinstance(value, str) or not value.strip():
        return None
    if value != value.strip():
        errors[field] = MSG_SPACES
    return value


def free_text(value, errors, field):
    """Texto livre (label, descricao...): strip e recusa de caracteres de controle (README §10)."""
    value = text(value)
    if value is not None and _RE_CONTROL.search(value):
        errors[field] = MSG_CONTROL_CHARS
    return value


def normalize(value):
    # O Oracle grava '' como NULL: vazio e None sao o mesmo estado.
    return None if value in (None, "") else value


FILLED_MARKER = u"<sensivel:preenchido>"
EMPTY_MARKER = u"<sensivel:vazio>"


def sensitive_marker(value):
    """Marcador fixo que substitui um valor sensivel em tudo que vai ao HTML (README §10)."""
    return EMPTY_MARKER if normalize(value) is None else FILLED_MARKER


def version(record, fields, sensitive=()):
    """Hash dos campos editaveis lidos agora; o formulario devolve-o para detectar edicao concorrente.

    Campos em 'sensiveis' entram pelo marcador, nunca pelo valor: a versao vai ao HTML e um sha256
    sem sal do segredo permitiria adivinha-lo. A troca concorrente so do segredo fica com o esperado.
    """
    state = [[c, sensitive_marker(record.get(c)) if c in sensitive else normalize(record.get(c))]
              for c in fields]
    return state_hash(state)


def state_hash(state):
    """sha256 do JSON deterministico de um estado serializavel."""
    raw = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def expected(record, fields):
    """Valores lidos que condicionam o UPDATE (o repositorio lanca RepoConflict se divergirem)."""
    return dict((c, record.get(c)) for c in fields)


def _display(value):
    value = normalize(value)
    return _EMPTY if value is None else masking.MASKER.mask(str(value))


def truncate_detail(detail):
    """Corta o detalhe de auditoria em DETAIL_LIMIT caracteres (coluna VARCHAR2(1000 CHAR))."""
    if len(detail) <= DETAIL_LIMIT:
        return detail
    return detail[:DETAIL_LIMIT - 3] + u"..."


def free_detail(text):
    """Detalhe de auditoria montado pelo service, sempre mascarado e limitado (README §4.4)."""
    return truncate_detail(masking.MASKER.mask(text))


def changes_detail(before, after_value, fields):
    """'campo: antigo → novo' por campo alterado, mascarado e limitado a 1000 caracteres; None se nada mudou."""
    parts = []
    for c in fields:
        a, d = normalize(before.get(c)), normalize(after_value.get(c))
        if a != d:
            parts.append(u"%s: %s%s%s" % (c, _display(a), _ARROW, _display(d)))
    return truncate_detail(u"; ".join(parts)) if parts else None


def insert_detail(record, fields):
    """'campo: valor' so dos campos preenchidos na inclusao (vazios omitidos), mascarado e limitado (README §4.4)."""
    return truncate_detail(u"; ".join(u"%s: %s" % (c, _display(record.get(c))) for c in fields
                              if normalize(record.get(c)) is not None))


def audit_entry(ctx, ip, action, detail):
    """Dicionario de auditoria repassado ao repositorio (gravado na mesma operacao)."""
    return {"actor": ctx.get("login"), "ip": ip, "action": action, "detail": detail}
